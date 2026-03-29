#!/usr/bin/env python3
"""
Knowledge Graph — CRUD module for the General Curiosity Engine's Neo4j layer.

Manages three node types:
  - ResearchQuestion: questions the system wants answered
  - KnowledgeAnswer: verified answers with staleness policies
  - KnowledgeTopic: categorical labels linking questions and answers

Relationships:
  (ResearchQuestion)-[:ANSWERED_BY]->(KnowledgeAnswer)
  (ResearchQuestion)-[:ABOUT_TOPIC]->(KnowledgeTopic)
  (ResearchQuestion)-[:TRIGGERED_BY]->(Human)
  (KnowledgeAnswer)-[:ABOUT_TOPIC]->(KnowledgeTopic)
  (KnowledgeAnswer)-[:ABOUT_HUMAN]->(Human)
  (KnowledgeAnswer)-[:SUPERSEDES]->(KnowledgeAnswer)
  (KnowledgeTopic)-[:SUBTOPIC_OF]->(KnowledgeTopic)

Usage:
    from knowledge_graph import (
        create_research_question, update_question_status,
        create_knowledge_answer, get_or_create_topic,
        link_answer_to_topic, link_answer_to_human,
        link_question_to_human, query_knowledge,
        get_stale_answers, get_recent_questions, check_conflicts,
    )
"""

import json
import logging
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import neo4j_session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Staleness policies
# ---------------------------------------------------------------------------

STALENESS_POLICIES = {
    "weather": {"policy": "fixed_ttl", "ttl_days": 1},
    "timezone": {"policy": "never", "ttl_days": 0},
    "news": {"policy": "fixed_ttl", "ttl_days": 3},
    "pricing": {"policy": "fixed_ttl", "ttl_days": 7},
    "event_detail": {"policy": "event_driven", "ttl_days": 0},
    "personal_fact": {"policy": "never", "ttl_days": 0},
    "research": {"policy": "fixed_ttl", "ttl_days": 30},
    "default": {"policy": "fixed_ttl", "ttl_days": 14},
}


def _compute_stale_at(
    staleness_policy: str, ttl_days: Optional[int], now: datetime
) -> Optional[str]:
    """Return ISO-formatted stale_at or None if answer never expires."""
    spec = STALENESS_POLICIES.get(staleness_policy, STALENESS_POLICIES["default"])
    policy = spec["policy"]
    days = ttl_days if ttl_days is not None else spec["ttl_days"]

    if policy == "never":
        return None
    if policy == "event_driven":
        # Event-driven answers don't have a fixed TTL; staleness is
        # triggered externally.  Store None so the field exists but
        # doesn't fire in get_stale_answers().
        return None
    # fixed_ttl
    if days <= 0:
        return None
    return (now + timedelta(days=days)).isoformat()


# ---------------------------------------------------------------------------
# ResearchQuestion CRUD
# ---------------------------------------------------------------------------


def create_research_question(
    text: str,
    category: str,
    target: str,
    method: str,
    priority: float,
    origin: str,
    chain_depth: int = 0,
    chain_id: Optional[str] = None,
    parent_question_id: Optional[str] = None,
    canonical_hash: Optional[str] = None,
    reasoning: str = "",
) -> str:
    """Create a ResearchQuestion node. Returns question_id (UUID)."""
    question_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    cid = chain_id or str(uuid.uuid4())

    with neo4j_session() as session:
        session.run(
            """
            CREATE (rq:ResearchQuestion {
                question_id: $qid,
                question_text: $text,
                category: $category,
                target: $target,
                research_method: $method,
                status: 'CANDIDATE',
                priority: $priority,
                canonical_hash: $canonical_hash,
                chain_id: $chain_id,
                chain_depth: $chain_depth,
                parent_question_id: $parent_qid,
                reasoning: $reasoning,
                answer: null,
                origin: $origin,
                created_at: $now,
                dispatched_at: null,
                answered_at: null,
                expires_at: null
            })
            """,
            qid=question_id,
            text=text,
            category=category,
            target=target,
            method=method,
            priority=priority,
            canonical_hash=canonical_hash,
            chain_id=cid,
            chain_depth=chain_depth,
            parent_qid=parent_question_id,
            reasoning=reasoning,
            origin=origin,
            now=now,
        )

    logger.info("Created ResearchQuestion %s: %s", question_id, text[:80])
    return question_id


def update_question_status(
    question_id: str, status: str, answer_text: Optional[str] = None
) -> bool:
    """Update status field. If RESOLVED, set answered_at and answer."""
    now = datetime.now(timezone.utc).isoformat()

    with neo4j_session() as session:
        params: Dict[str, Any] = {
            "qid": question_id,
            "status": status,
            "now": now,
        }
        set_clauses = ["rq.status = $status"]

        if status == "RESOLVED":
            set_clauses.append("rq.answered_at = $now")
            if answer_text is not None:
                set_clauses.append("rq.answer = $answer_text")
                params["answer_text"] = answer_text
        elif status == "DISPATCHED":
            set_clauses.append("rq.dispatched_at = $now")

        query = (
            "MATCH (rq:ResearchQuestion {question_id: $qid}) "
            f"SET {', '.join(set_clauses)} "
            "RETURN rq.question_id AS qid"
        )
        result = session.run(query, **params)
        record = result.single()

    if record:
        logger.info("Updated question %s -> %s", question_id, status)
        return True
    logger.warning("Question %s not found for status update", question_id)
    return False


# ---------------------------------------------------------------------------
# KnowledgeAnswer CRUD
# ---------------------------------------------------------------------------


def create_knowledge_answer(
    question_id: str,
    answer_text: str,
    summary: str,
    confidence: float,
    method: str,
    sources: list,
    staleness_policy: str = "default",
    ttl_days: Optional[int] = None,
    verification: str = "unverified",
) -> str:
    """Create KnowledgeAnswer, link to question via ANSWERED_BY.

    Auto-computes stale_at from staleness_policy / ttl_days.
    Returns answer_id (UUID).
    """
    answer_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    stale_at = _compute_stale_at(staleness_policy, ttl_days, now)
    sources_json = json.dumps(sources) if isinstance(sources, list) else str(sources)

    spec = STALENESS_POLICIES.get(staleness_policy, STALENESS_POLICIES["default"])
    effective_ttl = ttl_days if ttl_days is not None else spec["ttl_days"]

    with neo4j_session() as session:
        session.run(
            """
            MATCH (rq:ResearchQuestion {question_id: $qid})
            CREATE (ka:KnowledgeAnswer {
                answer_id: $aid,
                answer_text: $answer_text,
                summary: $summary,
                confidence: $confidence,
                method: $method,
                sources: $sources,
                verification: $verification,
                staleness_policy: $staleness_policy,
                ttl_days: $ttl_days,
                created_at: $now,
                stale_at: $stale_at
            })
            CREATE (rq)-[:ANSWERED_BY]->(ka)
            """,
            qid=question_id,
            aid=answer_id,
            answer_text=answer_text,
            summary=summary,
            confidence=confidence,
            method=method,
            sources=sources_json,
            verification=verification,
            staleness_policy=staleness_policy,
            ttl_days=effective_ttl,
            now=now_iso,
            stale_at=stale_at,
        )

    logger.info("Created KnowledgeAnswer %s for question %s", answer_id, question_id)
    return answer_id


# ---------------------------------------------------------------------------
# KnowledgeTopic CRUD
# ---------------------------------------------------------------------------


def get_or_create_topic(label: str, description: Optional[str] = None) -> str:
    """MERGE on lowercase label. Returns label. Increments query_count on match."""
    norm_label = label.strip().lower()
    now = datetime.now(timezone.utc).isoformat()

    with neo4j_session() as session:
        session.run(
            """
            MERGE (kt:KnowledgeTopic {label: $label})
            ON CREATE SET
                kt.display_label = $display_label,
                kt.description = $description,
                kt.created_at = $now,
                kt.last_queried = $now,
                kt.query_count = 1,
                kt.status = 'ACTIVE',
                kt.kill_until = null,
                kt.investigation_count = 0,
                kt.facts_produced = 0,
                kt.kill_reason = null
            ON MATCH SET
                kt.query_count = kt.query_count + 1,
                kt.last_queried = $now,
                kt.description = CASE
                    WHEN $description IS NOT NULL THEN $description
                    ELSE kt.description
                END
            """,
            label=norm_label,
            display_label=label.strip(),
            description=description,
            now=now,
        )

    logger.debug("get_or_create_topic: %s", norm_label)
    return norm_label


# ---------------------------------------------------------------------------
# Relationship helpers
# ---------------------------------------------------------------------------


def link_answer_to_topic(answer_id: str, topic_label: str) -> bool:
    """Create (KnowledgeAnswer)-[:ABOUT_TOPIC]->(KnowledgeTopic)."""
    norm_label = topic_label.strip().lower()
    with neo4j_session() as session:
        result = session.run(
            """
            MATCH (ka:KnowledgeAnswer {answer_id: $aid})
            MATCH (kt:KnowledgeTopic {label: $label})
            MERGE (ka)-[:ABOUT_TOPIC]->(kt)
            RETURN ka.answer_id AS aid
            """,
            aid=answer_id,
            label=norm_label,
        )
        record = result.single()
    if record:
        logger.debug("Linked answer %s -> topic %s", answer_id, norm_label)
        return True
    logger.warning(
        "link_answer_to_topic failed: answer=%s topic=%s", answer_id, norm_label
    )
    return False


def link_answer_to_human(answer_id: str, human_id: str) -> bool:
    """Create (KnowledgeAnswer)-[:ABOUT_HUMAN]->(Human)."""
    with neo4j_session() as session:
        result = session.run(
            """
            MATCH (ka:KnowledgeAnswer {answer_id: $aid})
            MATCH (h:Human {id: $hid})
            MERGE (ka)-[:ABOUT_HUMAN]->(h)
            RETURN ka.answer_id AS aid
            """,
            aid=answer_id,
            hid=human_id,
        )
        record = result.single()
    if record:
        logger.debug("Linked answer %s -> human %s", answer_id, human_id)
        return True
    logger.warning(
        "link_answer_to_human failed: answer=%s human=%s", answer_id, human_id
    )
    return False


def link_question_to_human(question_id: str, human_id: str) -> bool:
    """Create (ResearchQuestion)-[:TRIGGERED_BY]->(Human)."""
    with neo4j_session() as session:
        result = session.run(
            """
            MATCH (rq:ResearchQuestion {question_id: $qid})
            MATCH (h:Human {id: $hid})
            MERGE (rq)-[:TRIGGERED_BY]->(h)
            RETURN rq.question_id AS qid
            """,
            qid=question_id,
            hid=human_id,
        )
        record = result.single()
    if record:
        logger.debug("Linked question %s -> human %s", question_id, human_id)
        return True
    logger.warning(
        "link_question_to_human failed: question=%s human=%s",
        question_id,
        human_id,
    )
    return False


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------


def query_knowledge(search_term: str, limit: int = 10) -> list:
    """Fulltext search on knowledge_answer_search index.

    Returns list of dicts: answer_id, answer_text, summary, confidence,
    verification, score.
    """
    with neo4j_session() as session:
        result = session.run(
            """
            CALL db.index.fulltext.queryNodes('knowledge_answer_search', $term)
            YIELD node, score
            RETURN node.answer_id AS answer_id,
                   node.answer_text AS answer_text,
                   node.summary AS summary,
                   node.confidence AS confidence,
                   node.verification AS verification,
                   score
            ORDER BY score DESC
            LIMIT $limit
            """,
            term=search_term,
            limit=limit,
        )
        return [dict(r) for r in result]


def get_stale_answers(limit: int = 20) -> list:
    """Find answers past their stale_at datetime.

    Returns list of dicts: answer_id, answer_text, summary, staleness_policy,
    stale_at, confidence.
    """
    now = datetime.now(timezone.utc).isoformat()
    with neo4j_session() as session:
        result = session.run(
            """
            MATCH (ka:KnowledgeAnswer)
            WHERE ka.stale_at IS NOT NULL AND ka.stale_at < $now
            RETURN ka.answer_id AS answer_id,
                   ka.answer_text AS answer_text,
                   ka.summary AS summary,
                   ka.staleness_policy AS staleness_policy,
                   ka.stale_at AS stale_at,
                   ka.confidence AS confidence
            ORDER BY ka.stale_at ASC
            LIMIT $limit
            """,
            now=now,
            limit=limit,
        )
        return [dict(r) for r in result]


def get_recent_questions(days: int = 30, limit: int = 20) -> list:
    """Get recent ResearchQuestion nodes for dedup context.

    Returns list of dicts: question_id, question_text, category, status,
    canonical_hash, created_at.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with neo4j_session() as session:
        result = session.run(
            """
            MATCH (rq:ResearchQuestion)
            WHERE rq.created_at >= $cutoff
            RETURN rq.question_id AS question_id,
                   rq.question_text AS question_text,
                   rq.category AS category,
                   rq.status AS status,
                   rq.canonical_hash AS canonical_hash,
                   rq.created_at AS created_at
            ORDER BY rq.created_at DESC
            LIMIT $limit
            """,
            cutoff=cutoff,
            limit=limit,
        )
        return [dict(r) for r in result]


def check_conflicts(new_claim: str, domain: Optional[str] = None) -> list:
    """Fulltext search existing KnowledgeAnswer for potential contradictions.

    Returns matching answers so the caller can decide whether a conflict
    exists (semantic comparison is left to the LLM layer).

    If domain is provided, only returns answers linked to that topic.
    """
    with neo4j_session() as session:
        if domain:
            norm_domain = domain.strip().lower()
            result = session.run(
                """
                CALL db.index.fulltext.queryNodes('knowledge_answer_search', $claim)
                YIELD node, score
                WHERE score > 0.5
                WITH node, score
                MATCH (node)-[:ABOUT_TOPIC]->(kt:KnowledgeTopic {label: $domain})
                RETURN node.answer_id AS answer_id,
                       node.answer_text AS answer_text,
                       node.summary AS summary,
                       node.confidence AS confidence,
                       score
                ORDER BY score DESC
                LIMIT 10
                """,
                claim=new_claim,
                domain=norm_domain,
            )
        else:
            result = session.run(
                """
                CALL db.index.fulltext.queryNodes('knowledge_answer_search', $claim)
                YIELD node, score
                WHERE score > 0.5
                RETURN node.answer_id AS answer_id,
                       node.answer_text AS answer_text,
                       node.summary AS summary,
                       node.confidence AS confidence,
                       score
                ORDER BY score DESC
                LIMIT 10
                """,
                claim=new_claim,
            )
        return [dict(r) for r in result]


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import traceback

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    TEST_PREFIX = "__kgtest__"
    errors = []

    def _cleanup(session):
        """Remove all test nodes and relationships."""
        session.run(
            """
            MATCH (rq:ResearchQuestion)
            WHERE rq.question_id STARTS WITH $prefix
            DETACH DELETE rq
            """,
            prefix=TEST_PREFIX,
        )
        session.run(
            """
            MATCH (ka:KnowledgeAnswer)
            WHERE ka.answer_id STARTS WITH $prefix
            DETACH DELETE ka
            """,
            prefix=TEST_PREFIX,
        )
        session.run(
            """
            MATCH (kt:KnowledgeTopic {label: $label})
            DETACH DELETE kt
            """,
            label=f"{TEST_PREFIX}topic",
        )

    # Pre-clean in case a previous run left artifacts
    with neo4j_session() as s:
        _cleanup(s)

    try:
        # ---- 1. Create a research question ----
        print("[1/8] Creating research question...")
        qid = create_research_question(
            text="What is the capital of Mongolia?",
            category="world",
            target="world",
            method="web_search",
            priority=5.0,
            origin="scheduled",
            reasoning="General knowledge test",
        )
        # Override question_id for deterministic cleanup
        with neo4j_session() as s:
            s.run(
                """
                MATCH (rq:ResearchQuestion {question_id: $old})
                SET rq.question_id = $new
                """,
                old=qid,
                new=f"{TEST_PREFIX}{qid}",
            )
        qid = f"{TEST_PREFIX}{qid}"
        print(f"  -> question_id = {qid}")

        # ---- 2. Update status to DISPATCHED ----
        print("[2/8] Updating status to DISPATCHED...")
        ok = update_question_status(qid, "DISPATCHED")
        assert ok, "update_question_status returned False"
        print("  -> OK")

        # ---- 3. Create a knowledge answer ----
        print("[3/8] Creating knowledge answer...")
        aid = create_knowledge_answer(
            question_id=qid,
            answer_text="The capital of Mongolia is Ulaanbaatar.",
            summary="Mongolia's capital is Ulaanbaatar.",
            confidence=0.95,
            method="web_search",
            sources=["https://en.wikipedia.org/wiki/Mongolia"],
            staleness_policy="research",
            verification="single_source",
        )
        with neo4j_session() as s:
            s.run(
                """
                MATCH (ka:KnowledgeAnswer {answer_id: $old})
                SET ka.answer_id = $new
                """,
                old=aid,
                new=f"{TEST_PREFIX}{aid}",
            )
        aid = f"{TEST_PREFIX}{aid}"
        # Re-link after id change (ANSWERED_BY already exists, just need matching ids)
        print(f"  -> answer_id = {aid}")

        # ---- 4. Resolve question ----
        print("[4/8] Resolving question...")
        ok = update_question_status(
            qid, "RESOLVED", answer_text="Ulaanbaatar"
        )
        assert ok, "resolve returned False"
        print("  -> OK")

        # ---- 5. Create topic and link ----
        print("[5/8] Creating topic and linking...")
        topic = get_or_create_topic(f"{TEST_PREFIX}topic", "Test geography topic")
        assert topic == f"{TEST_PREFIX}topic"
        link_ok = link_answer_to_topic(aid, topic)
        assert link_ok, "link_answer_to_topic returned False"
        print(f"  -> topic = {topic}, linked = {link_ok}")

        # ---- 6. Query knowledge ----
        print("[6/8] Querying knowledge (fulltext)...")
        results = query_knowledge("Ulaanbaatar")
        print(f"  -> {len(results)} result(s)")
        # The test answer might or might not appear depending on index
        # refresh timing, so we don't assert on count.

        # ---- 7. Get recent questions ----
        print("[7/8] Getting recent questions...")
        recent = get_recent_questions(days=1, limit=50)
        found = any(r["question_id"] == qid for r in recent)
        assert found, f"Test question {qid} not in recent results"
        print(f"  -> found test question in {len(recent)} recent result(s)")

        # ---- 8. Check conflicts ----
        print("[8/8] Checking conflicts...")
        conflicts = check_conflicts("capital of Mongolia")
        print(f"  -> {len(conflicts)} potential conflict(s)")

        print("\nAll self-tests passed.")

    except Exception as e:
        errors.append(traceback.format_exc())
        print(f"\nSelf-test FAILED: {e}")
        traceback.print_exc()

    finally:
        # Always clean up test data
        print("\nCleaning up test nodes...")
        with neo4j_session() as s:
            _cleanup(s)
        print("Cleanup done.")

    if errors:
        sys.exit(1)
