#!/usr/bin/env python3
"""
parallel_memory_search.py — ASMR-style 3-agent parallel memory retrieval.

Replaces the single-pass context_assembler.assemble() hot path with three
specialized agents that run concurrently via asyncio.gather, then merge their
results through a scored aggregation step.

ASMR Agent roles
----------------
Agent 1 — DirectFacts
    Finds explicit statements, named facts, action items, and high-confidence
    inferences.  Uses full-text search + structured Cypher on Inference and
    ActionItem nodes.

Agent 2 — Context
    Finds related topics, community clusters, social cues, and semantically
    similar messages.  Uses vector search + graph topology (PageRank, Louvain,
    betweenness).

Agent 3 — Timeline
    Reconstructs temporal sequences, detects drift, and surfaces how opinions
    or facts have *changed* over time.  Uses timestamp ordering + TemporalMarker
    nodes.

Aggregation
-----------
Results from all three agents are deduplicated by content hash and re-ranked
by a composite score (agent confidence × source weight).  Contradictions
between agents are flagged rather than silently dropped.

Public interface
----------------
    # Async — preferred for gateway use
    result = await parallel_memory_search(query, human_id)

    # Sync wrapper — drop-in replacement for existing search_memory()
    result = search_memory(query, human_id)

Performance
-----------
Three agents run in parallel.  Wall-clock time ≈ slowest single agent, not
the sum of all three.  Target: ≤ 10 s total.  Each agent has an independent
8-second timeout; if it fires, that agent is skipped and the aggregator works
with whatever partial results arrived.

Cost model (2026-03-22)
-----------------------
This module does NOT make LLM calls.  All query formulation is done with
deterministic Cypher, not an LLM.  Cost = Neo4j query overhead only.
LLM-call variant (query_reformulation=True) is opt-in and adds ~$0.001/search.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Path bootstrap (mirrors the rest of the scripts in this directory)
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from neo4j_task_tracker import get_driver  # type: ignore[import]
from embedding_generator import generate_embedding  # type: ignore[import]

# Optional fallback dependency — imported at module level so tests can patch it
try:
    from context_assembler import assemble_context  # type: ignore[import]
except ImportError:
    assemble_context = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public configuration knobs
# ---------------------------------------------------------------------------
AGENT_TIMEOUT_S: float = float(os.getenv("ASMR_AGENT_TIMEOUT", "8.0"))
TOP_K_VECTOR: int = int(os.getenv("ASMR_TOP_K_VECTOR", "10"))
TOP_K_FACTS: int = int(os.getenv("ASMR_TOP_K_FACTS", "15"))
TOP_K_TIMELINE: int = int(os.getenv("ASMR_TOP_K_TIMELINE", "12"))
DEDUP_SIMILARITY_THRESHOLD: float = 0.85  # content overlap for dedup
MIN_CONFIDENCE_INCLUDE: float = 0.4  # below this, results are discarded


# ---------------------------------------------------------------------------
# Result data types
# ---------------------------------------------------------------------------


@dataclass
class MemoryFragment:
    """A single retrieved memory unit, normalised across all three agents."""

    text: str
    source: str          # "direct_facts" | "context" | "timeline"
    score: float         # 0.0–1.0 composite relevance
    node_type: str       # "Message" | "Inference" | "ActionItem" | "Topic" | "TemporalMarker"
    timestamp: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Derived during aggregation
    content_hash: str = ""
    contradiction_flag: bool = False

    def __post_init__(self) -> None:
        if not self.content_hash:
            self.content_hash = _content_hash(self.text)


@dataclass
class AgentResult:
    """Output from a single search agent."""

    agent_name: str
    fragments: List[MemoryFragment]
    duration_ms: int
    error: Optional[str] = None


@dataclass
class MemoryResult:
    """Aggregated output returned to callers."""

    query: str
    human_id: str
    fragments: List[MemoryFragment]   # Ranked, deduplicated
    agent_results: List[AgentResult]  # Raw per-agent output for debugging
    total_ms: int
    fallback_used: bool = False
    contradictions: List[Tuple[MemoryFragment, MemoryFragment]] = field(
        default_factory=list
    )

    # Convenience views
    @property
    def top_texts(self) -> List[str]:
        """Return the text of the top-ranked fragments."""
        return [f.text for f in self.fragments]

    def as_context_string(self, max_fragments: int = 20) -> str:
        """Render fragments as a flat string suitable for LLM context injection."""
        lines: List[str] = []
        for i, frag in enumerate(self.fragments[:max_fragments], 1):
            prefix = f"[{frag.node_type}]"
            ts = f" ({frag.timestamp})" if frag.timestamp else ""
            lines.append(f"{i}. {prefix}{ts} {frag.text}")
        return "\n".join(lines)

    def as_profile_string(self, max_chars: int = 1500) -> str:
        """Format search results for context profile S8 section.

        Produces [fact]/[msg]/[topic] format for the structured profile.
        Does NOT modify existing as_context_string() (backward compatible).
        """
        fact_types = {"Inference", "PersonalFact", "Preference"}
        lines: List[str] = []
        chars = 0
        for frag in self.fragments:
            prefix = "[fact]" if frag.node_type in fact_types else f"[{frag.node_type.lower()}]"
            line = f"{prefix} {frag.text}"
            if frag.score >= 0.7:
                line += f" (conf: {frag.score:.2f})"
            if chars + len(line) > max_chars:
                break
            lines.append(line)
            chars += len(line) + 1
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _content_hash(text: str) -> str:
    """Stable 8-char hash of stripped, lowercased content."""
    normalised = " ".join(text.lower().split())
    return hashlib.md5(normalised.encode()).hexdigest()[:8]


def _overlap_ratio(a: str, b: str) -> float:
    """Jaccard overlap on word tokens.  Fast proxy for semantic dedup."""
    sa = set(a.lower().split())
    sb = set(b.lower().split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _is_duplicate(frag: MemoryFragment, seen: List[MemoryFragment]) -> bool:
    """Return True if frag is substantially covered by any fragment already in seen."""
    for s in seen:
        if s.content_hash == frag.content_hash:
            return True
        if _overlap_ratio(s.text, frag.text) >= DEDUP_SIMILARITY_THRESHOLD:
            return True
    return False


def _are_contradictory(a: MemoryFragment, b: MemoryFragment) -> bool:
    """
    Naive contradiction detector: same topic keywords but opposite polarity
    signals.  This is intentionally conservative — prefer false negatives over
    false positives.
    """
    negations = {"not", "no", "never", "wasn't", "isn't", "don't", "doesn't",
                 "didn't", "can't", "cannot", "won't", "wouldn't"}
    a_words = set(a.text.lower().split())
    b_words = set(b.text.lower().split())
    shared = a_words & b_words - negations
    if len(shared) < 3:
        return False
    a_neg = bool(a_words & negations)
    b_neg = bool(b_words & negations)
    return a_neg != b_neg


# ---------------------------------------------------------------------------
# Agent 1 — DirectFacts
# ---------------------------------------------------------------------------


def _run_direct_facts(
    human_id: str,
    query: str,
    session: Any,
    scope: str = "dm",
) -> List[MemoryFragment]:
    """
    Find explicit statements and facts stored as Inference and ActionItem nodes,
    plus full-text matched Messages.

    Cypher strategy
    ~~~~~~~~~~~~~~~
    1. Full-text search on message_text_search index → recent explicit messages.
    2. High-confidence Inferences for this human → stated facts and beliefs.
    3. Open ActionItems → commitments and obligations.
    """
    fragments: List[MemoryFragment] = []

    # --- 1a. Full-text message search ---
    try:
        result = session.run(
            """
            CALL db.index.fulltext.queryNodes('message_text_search', $query)
            YIELD node AS m, score
            WHERE m.humanId = $human_id
              AND m.scope = 'dm'
            RETURN m.contentScrubbed AS text,
                   toString(m.timestamp) AS timestamp,
                   m.direction AS direction,
                   score
            ORDER BY score DESC
            LIMIT $k
            """,
            query=query,
            human_id=human_id,
            k=TOP_K_FACTS,
        )
        for r in result:
            if r["text"]:
                fragments.append(MemoryFragment(
                    text=r["text"],
                    source="direct_facts",
                    score=float(r["score"]) / 10.0,  # normalise Lucene score
                    node_type="Message",
                    timestamp=r["timestamp"],
                    metadata={"direction": r["direction"]},
                ))
    except Exception as exc:
        logger.debug(f"DirectFacts full-text search failed: {exc}")

    # --- 1b. High-confidence inferences ---
    try:
        result = session.run(
            """
            MATCH (i:Inference {humanId: $human_id})
            WHERE i.confidence >= $min_confidence
              AND NOT coalesce(i.superseded, false)
            RETURN i.content AS text,
                   i.type AS inf_type,
                   i.confidence AS confidence,
                   toString(i.createdAt) AS timestamp
            ORDER BY i.confidence DESC
            LIMIT $k
            """,
            human_id=human_id,
            min_confidence=0.65,
            k=TOP_K_FACTS,
        )
        for r in result:
            if r["text"]:
                fragments.append(MemoryFragment(
                    text=r["text"],
                    source="direct_facts",
                    score=float(r["confidence"]),
                    node_type="Inference",
                    timestamp=r["timestamp"],
                    metadata={"type": r["inf_type"]},
                ))
    except Exception as exc:
        logger.debug(f"DirectFacts inference search failed: {exc}")

    # --- 1b2. PersonalFact nodes (ASMR 6-Vector) ---
    try:
        result = session.run(
            """
            MATCH (pf:PersonalFact {humanId: $human_id, active: true})
            WHERE NOT coalesce(pf.superseded, false)
              AND pf.scope IN ['dm', $scope]
            RETURN pf.key AS key, pf.value AS value,
                   pf.confidence AS confidence,
                   toString(pf.createdAt) AS timestamp
            ORDER BY pf.confidence DESC
            LIMIT 10
            """,
            human_id=human_id,
            scope=scope if scope else "dm",
        )
        for r in result:
            if r["value"]:
                fragments.append(MemoryFragment(
                    text=f"{r['key']}: {r['value']}",
                    source="direct_facts",
                    score=float(r["confidence"]) + 0.05,  # slight boost for structured facts
                    node_type="PersonalFact",
                    timestamp=r["timestamp"],
                    metadata={"key": r["key"]},
                ))
    except Exception as exc:
        logger.debug(f"DirectFacts PersonalFact search failed: {exc}")

    # --- 1b3. Preference nodes (ASMR 6-Vector) ---
    try:
        result = session.run(
            """
            MATCH (p:Preference {humanId: $human_id, active: true})
            WHERE NOT coalesce(p.superseded, false)
              AND p.scope IN ['dm', $scope]
            RETURN p.preference AS text, p.domain AS domain,
                   p.valence AS valence, p.strength AS strength,
                   toString(p.createdAt) AS timestamp
            ORDER BY p.strength DESC
            LIMIT 8
            """,
            human_id=human_id,
            scope=scope if scope else "dm",
        )
        for r in result:
            if r["text"]:
                fragments.append(MemoryFragment(
                    text=f"[{r['valence']}] {r['text']}",
                    source="direct_facts",
                    score=float(r["strength"]) * 0.9,
                    node_type="Preference",
                    timestamp=r["timestamp"],
                    metadata={"domain": r["domain"], "valence": r["valence"]},
                ))
    except Exception as exc:
        logger.debug(f"DirectFacts Preference search failed: {exc}")

    # --- 1b4. Goal nodes (active, non-superseded) ---
    try:
        result = session.run(
            """
            MATCH (g:Goal {humanId: $human_id, status: 'active'})
            WHERE NOT coalesce(g.superseded, false)
            RETURN g.title AS title, g.priority AS priority,
                   g.domain AS domain, g.deadline AS deadline,
                   toString(g.createdAt) AS timestamp
            ORDER BY CASE g.priority
                WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END
            LIMIT 10
            """,
            human_id=human_id,
        )
        for r in result:
            if r["title"]:
                priority_score = {"high": 0.95, "medium": 0.8, "low": 0.6}.get(
                    str(r["priority"]).lower(), 0.7
                )
                detail = r["domain"] or ""
                if r["deadline"]:
                    detail += f", deadline: {r['deadline']}" if detail else f"deadline: {r['deadline']}"
                detail_str = f" ({detail})" if detail else ""
                fragments.append(MemoryFragment(
                    text=f"[Goal] {r['title']}{detail_str}",
                    source="direct_facts",
                    score=priority_score,
                    node_type="Goal",
                    timestamp=r["timestamp"],
                    metadata={
                        "priority": r["priority"],
                        "domain": r["domain"],
                        "deadline": r["deadline"],
                    },
                ))
    except Exception as exc:
        logger.debug(f"DirectFacts Goal search failed: {exc}")

    # --- 1c. Open action items ---
    try:
        result = session.run(
            """
            MATCH (ai:ActionItem {humanId: $human_id, status: 'OPEN'})
            RETURN ai.description AS text,
                   ai.priority AS priority,
                   ai.assignee AS assignee,
                   ai.deadline AS deadline,
                   toString(ai.createdAt) AS timestamp
            ORDER BY CASE ai.priority
                WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END
            LIMIT $k
            """,
            human_id=human_id,
            k=TOP_K_FACTS // 2,
        )
        for r in result:
            if r["text"]:
                # Priority → score mapping
                priority_score = {"high": 0.9, "medium": 0.7, "low": 0.5}.get(
                    str(r["priority"]).lower(), 0.5
                )
                fragments.append(MemoryFragment(
                    text=r["text"],
                    source="direct_facts",
                    score=priority_score,
                    node_type="ActionItem",
                    timestamp=r["timestamp"],
                    metadata={
                        "priority": r["priority"],
                        "assignee": r["assignee"],
                        "deadline": r["deadline"],
                    },
                ))
    except Exception as exc:
        logger.debug(f"DirectFacts action-item search failed: {exc}")

    return fragments


# ---------------------------------------------------------------------------
# Agent 2 — Context
# ---------------------------------------------------------------------------


def _run_context_agent(
    human_id: str,
    query: str,
    embedding: Optional[List[float]],
    session: Any,
) -> List[MemoryFragment]:
    """
    Find related context via graph topology + vector similarity.

    Cypher strategy
    ~~~~~~~~~~~~~~~
    1. Vector search against message_embedding index → semantically near messages.
    2. Top PageRank topics for this human → topic landscape.
    3. Bridge topics (betweenness) that connect topic clusters.
    4. Social context (KNOWN_THROUGH, RELATED_TO) — who matters to this person.
    """
    fragments: List[MemoryFragment] = []

    # --- 2a. Vector similarity search ---
    if embedding:
        try:
            internal_k = TOP_K_VECTOR * 5
            result = session.run(
                """
                CALL db.index.vector.queryNodes('message_embedding', $internal_k, $embedding)
                YIELD node AS m, score
                WHERE m.humanId = $human_id
                  AND m.scope = 'dm'
                RETURN m.contentScrubbed AS text,
                       toString(m.timestamp) AS timestamp,
                       m.direction AS direction,
                       score
                ORDER BY score DESC
                LIMIT $k
                """,
                human_id=human_id,
                embedding=embedding,
                internal_k=internal_k,
                k=TOP_K_VECTOR,
            )
            for r in result:
                if r["text"]:
                    fragments.append(MemoryFragment(
                        text=r["text"],
                        source="context",
                        score=float(r["score"]),
                        node_type="Message",
                        timestamp=r["timestamp"],
                        metadata={"direction": r["direction"], "retrieval": "vector"},
                    ))
        except Exception as exc:
            logger.debug(f"Context vector search failed: {exc}")

    # --- 2b. Top PageRank topics → messages in those topics ---
    try:
        result = session.run(
            """
            MATCH (h:Human {id: $human_id})-[d:DISCUSSED]->(t:Topic)
            WHERE EXISTS {
                MATCH (m:Message {humanId: $human_id})-[:HAS_TOPIC]->(t)
                WHERE m.scope = 'dm'
            }
            WITH t, coalesce(d.pagerank_score, toFloat(d.count)/10.0) AS tScore
            ORDER BY tScore DESC LIMIT 5
            MATCH (m:Message {humanId: $human_id})-[:HAS_TOPIC]->(t)
            WHERE m.scope = 'dm'
            RETURN DISTINCT m.contentScrubbed AS text,
                   toString(m.timestamp) AS timestamp,
                   t.label AS topicLabel,
                   tScore * 0.8 AS score
            ORDER BY score DESC, m.timestamp DESC
            LIMIT $k
            """,
            human_id=human_id,
            k=TOP_K_VECTOR,
        )
        for r in result:
            if r["text"]:
                fragments.append(MemoryFragment(
                    text=r["text"],
                    source="context",
                    score=float(r["score"]),
                    node_type="Message",
                    timestamp=r["timestamp"],
                    metadata={"topic": r["topicLabel"], "retrieval": "pagerank"},
                ))
    except Exception as exc:
        logger.debug(f"Context PageRank topic search failed: {exc}")

    # --- 2c. Bridge topics (betweenness centrality) as Topic fragments ---
    try:
        result = session.run(
            """
            MATCH (h:Human {id: $human_id})-[:DISCUSSED]->(t:Topic)
            WHERE t.betweenness_score IS NOT NULL AND t.betweenness_score > 0
            RETURN t.label AS text,
                   t.domain AS domain,
                   t.betweenness_score AS score
            ORDER BY t.betweenness_score DESC
            LIMIT 5
            """,
            human_id=human_id,
        )
        for r in result:
            if r["text"]:
                fragments.append(MemoryFragment(
                    text=f"[Bridge topic] {r['text']}",
                    source="context",
                    score=min(float(r["score"]) * 0.5, 0.9),
                    node_type="Topic",
                    metadata={"domain": r["domain"]},
                ))
    except Exception as exc:
        logger.debug(f"Context bridge-topic search failed: {exc}")

    # --- 2c2. KnowledgeLevel nodes ---
    try:
        result = session.run(
            """
            MATCH (k:KnowledgeLevel {humanId: $human_id})
            WHERE NOT coalesce(k.superseded, false)
            RETURN k.domain AS domain, k.level AS level
            """,
            human_id=human_id,
        )
        for r in result:
            if r["domain"]:
                level = r["level"] or "unknown"
                level_score = {"expert": 0.8, "proficient": 0.7, "learning": 0.6, "aware": 0.5}.get(
                    level.lower(), 0.5
                )
                fragments.append(MemoryFragment(
                    text=f"[Knowledge] {r['domain']}: {level}",
                    source="context",
                    score=level_score,
                    node_type="KnowledgeLevel",
                    metadata={"domain": r["domain"], "level": level},
                ))
    except Exception as exc:
        logger.debug(f"Context KnowledgeLevel search failed: {exc}")

    # --- 2d. Social context ---
    try:
        result = session.run(
            """
            MATCH (h:Human {id: $human_id})-[r:KNOWN_THROUGH|RELATED_TO]->(other:Human)
            RETURN other.displayName AS name,
                   type(r) AS relType,
                   coalesce(r.relationship, r.context, '') AS context
            LIMIT 8
            """,
            human_id=human_id,
        )
        for r in result:
            if r["name"]:
                rel_text = f"{r['name']} ({r['relType']}" + (
                    f": {r['context']}" if r["context"] else ""
                ) + ")"
                fragments.append(MemoryFragment(
                    text=rel_text,
                    source="context",
                    score=0.6,
                    node_type="Human",
                    metadata={"rel_type": r["relType"]},
                ))
    except Exception as exc:
        logger.debug(f"Context social search failed: {exc}")

    return fragments


# ---------------------------------------------------------------------------
# Agent 3 — Timeline
# ---------------------------------------------------------------------------


def _run_timeline_agent(
    human_id: str,
    session: Any,
) -> List[MemoryFragment]:
    """
    Reconstruct temporal sequences and surface how facts change over time.

    Cypher strategy
    ~~~~~~~~~~~~~~~
    1. TemporalMarker nodes (rising/fading topics) → drift signals.
    2. Chronological message slice (most recent 15 DMs) → recency context.
    3. Inference history sorted by createdAt → belief evolution.
    4. Episode-level summaries (if Episode nodes exist) → macro-level arcs.
    """
    fragments: List[MemoryFragment] = []

    # --- 3a. Drift signals (TemporalMarker) ---
    try:
        result = session.run(
            """
            MATCH (tm:TemporalMarker {humanId: $human_id})
            WHERE tm.detectedAt > datetime() - duration('P14D')
            RETURN tm.signal AS signal,
                   tm.topicLabel AS topic,
                   tm.recentCount AS recent,
                   tm.longtermCount AS longterm,
                   toString(tm.detectedAt) AS timestamp
            ORDER BY tm.detectedAt DESC
            LIMIT $k
            """,
            human_id=human_id,
            k=TOP_K_TIMELINE // 2,
        )
        for r in result:
            signal = r["signal"] or "unknown"
            topic = r["topic"] or "unknown"
            recent = r["recent"] or 0
            longterm = r["longterm"] or 0
            text = (
                f"[{signal.upper()}] Topic '{topic}': "
                f"{recent} mentions recently vs {longterm} historically"
            )
            # RISING topics are more relevant
            score = 0.75 if "rising" in signal.lower() else 0.55
            fragments.append(MemoryFragment(
                text=text,
                source="timeline",
                score=score,
                node_type="TemporalMarker",
                timestamp=r["timestamp"],
                metadata={"signal": signal, "topic": topic},
            ))
    except Exception as exc:
        logger.debug(f"Timeline drift-signal search failed: {exc}")

    # --- 3b. Chronological recency slice (last 15 DMs) ---
    try:
        result = session.run(
            """
            MATCH (m:Message {humanId: $human_id})
            WHERE m.scope = 'dm'
              AND m.contentScrubbed IS NOT NULL
            RETURN m.contentScrubbed AS text,
                   toString(m.timestamp) AS timestamp,
                   m.direction AS direction
            ORDER BY m.timestamp DESC
            LIMIT $k
            """,
            human_id=human_id,
            k=TOP_K_TIMELINE,
        )
        records = list(result)
        # Score decays linearly from 0.8 to 0.4 across the recency window
        total = len(records)
        for idx, r in enumerate(records):
            if r["text"]:
                score = 0.8 - (0.4 * idx / max(total - 1, 1))
                fragments.append(MemoryFragment(
                    text=r["text"],
                    source="timeline",
                    score=round(score, 3),
                    node_type="Message",
                    timestamp=r["timestamp"],
                    metadata={"direction": r["direction"], "retrieval": "recency"},
                ))
    except Exception as exc:
        logger.debug(f"Timeline recency search failed: {exc}")

    # --- 3c. Inference history (belief evolution) ---
    try:
        result = session.run(
            """
            MATCH (i:Inference {humanId: $human_id})
            WHERE NOT coalesce(i.superseded, false)
            RETURN i.content AS text,
                   i.type AS inf_type,
                   i.confidence AS confidence,
                   toString(i.createdAt) AS timestamp
            ORDER BY i.createdAt DESC
            LIMIT $k
            """,
            human_id=human_id,
            k=8,
        )
        for r in result:
            if r["text"]:
                fragments.append(MemoryFragment(
                    text=r["text"],
                    source="timeline",
                    score=float(r["confidence"]) * 0.75,
                    node_type="Inference",
                    timestamp=r["timestamp"],
                    metadata={"type": r["inf_type"], "retrieval": "temporal_belief"},
                ))
    except Exception as exc:
        logger.debug(f"Timeline inference history failed: {exc}")

    # --- 3d. Episode summaries ---
    try:
        result = session.run(
            """
            MATCH (e:Episode {humanId: $human_id})
            RETURN e.summary AS text,
                   toString(e.startedAt) AS timestamp,
                   e.topicLabel AS topic
            ORDER BY e.startedAt DESC
            LIMIT 5
            """,
            human_id=human_id,
        )
        for r in result:
            if r["text"]:
                fragments.append(MemoryFragment(
                    text=f"[Episode: {r['topic'] or 'general'}] {r['text']}",
                    source="timeline",
                    score=0.65,
                    node_type="Episode",
                    timestamp=r["timestamp"],
                ))
    except Exception as exc:
        logger.debug(f"Timeline episode search failed: {exc}")

    # --- 3e. TemporalSeq chains (ASMR 6-Vector: state changes) ---
    try:
        result = session.run(
            """
            MATCH (ts:TemporalSeq {humanId: $human_id, isCurrent: true})
            WHERE NOT coalesce(ts.superseded, false)
            OPTIONAL MATCH (ts)-[:SUPERSEDES*1..3]->(prior:TemporalSeq)
            RETURN ts.subject AS subject, ts.value AS current_value,
                   collect(prior.value)[..3] AS prior_values,
                   toString(ts.createdAt) AS timestamp
            LIMIT 8
            """,
            human_id=human_id,
        )
        for r in result:
            prior = r["prior_values"] or []
            history = f" (was: {', '.join(prior)})" if prior else ""
            fragments.append(MemoryFragment(
                text=f"{r['subject']}: {r['current_value']}{history}",
                source="timeline",
                score=0.75,
                node_type="TemporalSeq",
                timestamp=r["timestamp"],
                metadata={"subject": r["subject"], "prior_values": prior},
            ))
    except Exception as exc:
        logger.debug(f"Timeline TemporalSeq search failed: {exc}")

    # --- 3f. CalendarEvent nodes (ASMR 6-Vector: upcoming events) ---
    try:
        result = session.run(
            """
            MATCH (ce:CalendarEvent {humanId: $human_id})
            WHERE ce.status IN ['PENDING', 'CONFIRMED']
              AND NOT coalesce(ce.superseded, false)
            RETURN ce.title AS title, ce.startTime AS start_time,
                   ce.eventType AS event_type,
                   ce.participants AS participants,
                   toString(ce.createdAt) AS timestamp
            ORDER BY ce.startTime
            LIMIT 5
            """,
            human_id=human_id,
        )
        for r in result:
            parts = f" with {', '.join(r['participants'])}" if r["participants"] else ""
            fragments.append(MemoryFragment(
                text=f"[{r['event_type']}] {r['title']} at {r['start_time']}{parts}",
                source="timeline",
                score=0.7,
                node_type="CalendarEvent",
                timestamp=r["timestamp"],
                metadata={"event_type": r["event_type"]},
            ))
    except Exception as exc:
        logger.debug(f"Timeline CalendarEvent search failed: {exc}")

    # --- 3g. UnresolvedThread nodes (active, non-superseded) ---
    try:
        result = session.run(
            """
            MATCH (u:UnresolvedThread {humanId: $human_id, status: 'active'})
            WHERE NOT coalesce(u.superseded, false)
            RETURN u.topic AS topic, u.relatedGoal AS related_goal
            """,
            human_id=human_id,
        )
        for r in result:
            if r["topic"]:
                goal_str = f" (related goal: {r['related_goal']})" if r["related_goal"] else ""
                fragments.append(MemoryFragment(
                    text=f"[Unresolved] {r['topic']}{goal_str}",
                    source="timeline",
                    score=0.7,
                    node_type="UnresolvedThread",
                    metadata={"topic": r["topic"], "related_goal": r["related_goal"]},
                ))
    except Exception as exc:
        logger.debug(f"Timeline UnresolvedThread search failed: {exc}")

    return fragments


# ---------------------------------------------------------------------------
# Async agent runners  (each wraps a blocking Neo4j session in a thread)
# ---------------------------------------------------------------------------


async def _agent_direct_facts(
    human_id: str, query: str
) -> AgentResult:
    t0 = time.monotonic()
    try:
        driver = get_driver()
        loop = asyncio.get_running_loop()
        fragments = await loop.run_in_executor(
            None,
            lambda: _run_direct_facts_session(driver, human_id, query),
        )
        return AgentResult(
            agent_name="direct_facts",
            fragments=fragments,
            duration_ms=round((time.monotonic() - t0) * 1000),
        )
    except Exception as exc:
        logger.warning(f"direct_facts agent error: {exc}")
        return AgentResult(
            agent_name="direct_facts",
            fragments=[],
            duration_ms=round((time.monotonic() - t0) * 1000),
            error=str(exc),
        )


def _run_direct_facts_session(driver: Any, human_id: str, query: str) -> List[MemoryFragment]:
    with driver.session() as session:
        return _run_direct_facts(human_id, query, session)


async def _agent_context(
    human_id: str, query: str, embedding: Optional[List[float]]
) -> AgentResult:
    t0 = time.monotonic()
    try:
        driver = get_driver()
        loop = asyncio.get_running_loop()
        fragments = await loop.run_in_executor(
            None,
            lambda: _run_context_session(driver, human_id, query, embedding),
        )
        return AgentResult(
            agent_name="context",
            fragments=fragments,
            duration_ms=round((time.monotonic() - t0) * 1000),
        )
    except Exception as exc:
        logger.warning(f"context agent error: {exc}")
        return AgentResult(
            agent_name="context",
            fragments=[],
            duration_ms=round((time.monotonic() - t0) * 1000),
            error=str(exc),
        )


def _run_context_session(
    driver: Any, human_id: str, query: str, embedding: Optional[List[float]]
) -> List[MemoryFragment]:
    with driver.session() as session:
        return _run_context_agent(human_id, query, embedding, session)


async def _agent_timeline(human_id: str) -> AgentResult:
    t0 = time.monotonic()
    try:
        driver = get_driver()
        loop = asyncio.get_running_loop()
        fragments = await loop.run_in_executor(
            None,
            lambda: _run_timeline_session(driver, human_id),
        )
        return AgentResult(
            agent_name="timeline",
            fragments=fragments,
            duration_ms=round((time.monotonic() - t0) * 1000),
        )
    except Exception as exc:
        logger.warning(f"timeline agent error: {exc}")
        return AgentResult(
            agent_name="timeline",
            fragments=[],
            duration_ms=round((time.monotonic() - t0) * 1000),
            error=str(exc),
        )


def _run_timeline_session(driver: Any, human_id: str) -> List[MemoryFragment]:
    with driver.session() as session:
        return _run_timeline_agent(human_id, session)


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------

# Per-source weights: DirectFacts is the most precise, Context adds breadth,
# Timeline adds recency — slightly lower weight because it may duplicate recent
# messages already found by DirectFacts.
_SOURCE_WEIGHT: Dict[str, float] = {
    "direct_facts": 1.0,
    "context": 0.95,
    "timeline": 0.85,
}

# Node-type boosts applied on top of the source weight
_NODE_TYPE_BOOST: Dict[str, float] = {
    "ActionItem": 0.10,
    "Inference": 0.05,
    "TemporalMarker": 0.05,
    "Episode": 0.0,
    "Message": 0.0,
    "Topic": -0.05,
    "Human": -0.05,
}


def _composite_score(frag: MemoryFragment) -> float:
    """Final ranking score incorporating source weight and node-type boost."""
    base = frag.score * _SOURCE_WEIGHT.get(frag.source, 0.8)
    boost = _NODE_TYPE_BOOST.get(frag.node_type, 0.0)
    return min(1.0, max(0.0, base + boost))


def _aggregate(
    agent_results: List[AgentResult],
    max_fragments: int = 40,
) -> Tuple[List[MemoryFragment], List[Tuple[MemoryFragment, MemoryFragment]]]:
    """
    Merge agent results into a ranked, deduplicated list.

    Steps
    -----
    1. Collect all fragments, drop those below MIN_CONFIDENCE_INCLUDE.
    2. Compute composite scores.
    3. Sort by composite score descending.
    4. Deduplicate: first occurrence of a content hash wins; skip near-duplicates.
    5. Detect contradictions between surviving fragments.
    6. Return (ranked_fragments, contradictions).
    """
    all_fragments: List[MemoryFragment] = []
    for ar in agent_results:
        for frag in ar.fragments:
            if frag.score >= MIN_CONFIDENCE_INCLUDE:
                all_fragments.append(frag)

    # Re-score with composite formula
    for frag in all_fragments:
        frag.score = _composite_score(frag)

    all_fragments.sort(key=lambda f: f.score, reverse=True)

    # Deduplicate
    kept: List[MemoryFragment] = []
    for frag in all_fragments:
        if not _is_duplicate(frag, kept):
            kept.append(frag)
            if len(kept) >= max_fragments:
                break

    # Detect contradictions among surviving fragments
    contradictions: List[Tuple[MemoryFragment, MemoryFragment]] = []
    for i, a in enumerate(kept):
        for b in kept[i + 1:]:
            if _are_contradictory(a, b):
                a.contradiction_flag = True
                b.contradiction_flag = True
                contradictions.append((a, b))

    return kept, contradictions


# ---------------------------------------------------------------------------
# Single-agent fallback  (uses existing context_assembler logic)
# ---------------------------------------------------------------------------


def _fallback_search(query: str, human_id: str) -> MemoryResult:
    """
    Invoke the existing ContextAssembler as a single-agent fallback.

    Converts the dict returned by assemble_context() into a MemoryResult so
    callers get a consistent type regardless of which path was taken.
    """
    t0 = time.monotonic()
    try:
        if assemble_context is None:
            raise ImportError("context_assembler not available")
        ctx = assemble_context(human_id, query)
        fragments: List[MemoryFragment] = []

        for msg in ctx.get("similar_messages", []):
            if msg.get("text"):
                fragments.append(MemoryFragment(
                    text=msg["text"],
                    source="direct_facts",
                    score=float(msg.get("score", 0.5)),
                    node_type="Message",
                    timestamp=msg.get("timestamp"),
                ))
        for msg in ctx.get("thread_messages", []):
            if msg.get("text"):
                fragments.append(MemoryFragment(
                    text=msg["text"],
                    source="timeline",
                    score=0.6,
                    node_type="Message",
                    timestamp=msg.get("timestamp"),
                ))
        for inf in ctx.get("inferences", []):
            if inf.get("content"):
                fragments.append(MemoryFragment(
                    text=inf["content"],
                    source="direct_facts",
                    score=float(inf.get("confidence", 0.5)),
                    node_type="Inference",
                ))

        return MemoryResult(
            query=query,
            human_id=human_id,
            fragments=fragments,
            agent_results=[],
            total_ms=round((time.monotonic() - t0) * 1000),
            fallback_used=True,
        )
    except Exception as exc:
        logger.error(f"Fallback search also failed: {exc}")
        return MemoryResult(
            query=query,
            human_id=human_id,
            fragments=[],
            agent_results=[],
            total_ms=round((time.monotonic() - t0) * 1000),
            fallback_used=True,
        )


# ---------------------------------------------------------------------------
# Public async API
# ---------------------------------------------------------------------------


async def parallel_memory_search(
    query: str,
    human_id: str,
    *,
    scope: str = "dm",
    max_fragments: int = 40,
    precomputed_embedding: Optional[List[float]] = None,
) -> MemoryResult:
    """
    Run three specialised search agents in parallel and merge their results.

    Parameters
    ----------
    query:
        The search query string (usually the current inbound message or a
        reformulated intent string).
    human_id:
        The UUID of the :Human node in Neo4j.
    scope:
        Message scope filter.  Currently only "dm" is implemented; group
        scope support can be added by passing scope through to each agent.
    max_fragments:
        Maximum number of fragments to return after deduplication.
    precomputed_embedding:
        If the caller already computed an embedding for the query, pass it
        here to avoid a second Ollama round-trip inside the context agent.

    Returns
    -------
    MemoryResult
        Always succeeds — falls back to single-agent on any error.
    """
    t0 = time.monotonic()

    # Generate embedding once, shared by the context agent
    loop = asyncio.get_running_loop()
    if precomputed_embedding is not None:
        embedding = precomputed_embedding
    else:
        try:
            embedding = await asyncio.wait_for(
                loop.run_in_executor(None, generate_embedding, query),
                timeout=AGENT_TIMEOUT_S,
            )
        except Exception as exc:
            logger.warning(f"Embedding generation failed, context agent will skip vector search: {exc}")
            embedding = None

    # Dispatch all three agents in parallel with individual timeouts
    async def _guarded(coro: Any, agent_name: str) -> AgentResult:
        try:
            return await asyncio.wait_for(coro, timeout=AGENT_TIMEOUT_S)
        except asyncio.TimeoutError:
            logger.warning(f"{agent_name} agent timed out after {AGENT_TIMEOUT_S}s")
            return AgentResult(
                agent_name=agent_name,
                fragments=[],
                duration_ms=round(AGENT_TIMEOUT_S * 1000),
                error="timeout",
            )
        except Exception as exc:
            logger.warning(f"{agent_name} agent failed: {exc}")
            return AgentResult(
                agent_name=agent_name,
                fragments=[],
                duration_ms=0,
                error=str(exc),
            )

    results: List[AgentResult] = await asyncio.gather(
        _guarded(_agent_direct_facts(human_id, query), "direct_facts"),
        _guarded(_agent_context(human_id, query, embedding), "context"),
        _guarded(_agent_timeline(human_id), "timeline"),
    )

    # Count successful agents
    successful = [r for r in results if not r.error]
    if not successful:
        logger.warning(
            "All three agents failed — falling back to single-agent search"
        )
        return _fallback_search(query, human_id)

    # Aggregate
    fragments, contradictions = _aggregate(results, max_fragments=max_fragments)

    if contradictions:
        logger.info(
            f"parallel_memory_search: {len(contradictions)} contradiction(s) detected "
            f"for human={human_id[:8]}"
        )

    total_ms = round((time.monotonic() - t0) * 1000)
    logger.info(
        f"parallel_memory_search: {len(fragments)} fragments in {total_ms}ms "
        f"(agents: {[r.duration_ms for r in results]}ms)"
    )

    return MemoryResult(
        query=query,
        human_id=human_id,
        fragments=fragments,
        agent_results=results,
        total_ms=total_ms,
        contradictions=contradictions,
    )


# ---------------------------------------------------------------------------
# Public sync wrapper — drop-in replacement for search_memory()
# ---------------------------------------------------------------------------


def search_memory(query: str, human_id: str) -> MemoryResult:
    """
    Synchronous entry point.  Drop-in replacement for any existing
    ``search_memory(query, human_id)`` call sites.

    This function handles its own event loop lifecycle correctly whether it is
    called from:
      - A plain synchronous script (no existing loop)
      - A FastAPI / uvicorn worker (existing loop running in another thread)
      - A Jupyter notebook (IPython has its own loop)

    Returns a MemoryResult in all cases; never raises.
    """
    try:
        # Python 3.10+ deprecated asyncio.get_event_loop() when there is no
        # running loop.  Use asyncio.run() which always creates a fresh loop
        # unless we are already inside a running loop (e.g. FastAPI/Jupyter),
        # in which case we dispatch to a separate thread to avoid deadlock.
        try:
            loop = asyncio.get_running_loop()
            running = True
        except RuntimeError:
            running = False

        if running:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    asyncio.run, parallel_memory_search(query, human_id)
                )
                return future.result(timeout=AGENT_TIMEOUT_S * 2)
        else:
            return asyncio.run(parallel_memory_search(query, human_id))
    except Exception as exc:
        logger.error(f"search_memory sync wrapper failed: {exc}")
        return _fallback_search(query, human_id)


# ---------------------------------------------------------------------------
# CLI for manual testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import json

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(
        description="Parallel ASMR memory search — test harness"
    )
    parser.add_argument("human_id", help="Human UUID")
    parser.add_argument("query", help="Search query")
    parser.add_argument(
        "--max-fragments", type=int, default=20,
        help="Maximum fragments to display (default: 20)"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output raw JSON instead of formatted text"
    )
    args = parser.parse_args()

    result = search_memory(args.query, args.human_id)

    if args.json:
        import dataclasses
        print(json.dumps(dataclasses.asdict(result), indent=2, default=str))
    else:
        print(f"\n=== Parallel Memory Search Results ===")
        print(f"Query      : {result.query}")
        print(f"Human      : {result.human_id[:8]}...")
        print(f"Total time : {result.total_ms}ms")
        print(f"Fallback   : {result.fallback_used}")
        print(f"Fragments  : {len(result.fragments)}")
        if result.contradictions:
            print(f"Contradictions flagged: {len(result.contradictions)}")
        print()
        print("--- Per-agent timings ---")
        for ar in result.agent_results:
            status = f"ERROR: {ar.error}" if ar.error else f"{len(ar.fragments)} frags"
            print(f"  {ar.agent_name:<16} {ar.duration_ms:>5}ms  {status}")
        print()
        print(f"--- Top {args.max_fragments} fragments ---")
        print(result.as_context_string(args.max_fragments))
