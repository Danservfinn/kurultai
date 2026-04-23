"""context_profile.py — Neo4j-maximized context profile builder.

Replaces the flat 4000-token context block previously produced by
context_assembler.py with a structured, graph-native 2500-token profile.

Architecture
------------
1. Multi-label message classifier  → determine which sections are relevant
2. Section inclusion matrix        → union mask across all detected message types
3. Per-section TTL cache           → avoid redundant Cypher round-trips
4. Parameterized Cypher queries    → one function per section (S1/S3-S9 + instructions)
5. Profile renderer                → XML-delimited output ready for LLM injection

Key design choices
------------------
- Multi-label classification: a single message can be both a question and a
  task_request, so we union the section masks rather than picking one type.
- Graceful degradation: build_context_profile() always returns a string (empty
  string on any Neo4j or unexpected error) — it never raises.
- S8 (Relevant Memory) delegates to parallel_memory_search.search_memory()
  which runs its own connection lifecycle.
- Window function (max() OVER ()) in Q3 requires Neo4j 5.x+.  If you are on
  4.x, replace the OVER clause with a separate aggregation subquery.
"""
from __future__ import annotations

import os
import sys
import re
import json
import time
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import get_driver, close_driver

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Component 1: Multi-label message classifier
# ---------------------------------------------------------------------------

def classify_message(text: str, has_thread: bool = False) -> List[str]:
    """Classify a message into one or more semantic types.

    Returns a list of type strings rather than a single label so that mixed
    messages (e.g. a question that is also a task request) receive the union
    of relevant sections.

    "actually" is only treated as a correction marker when it appears at the
    start of a sentence or after sentence-ending punctuation, to reduce false
    positives from phrases like "I actually like this".

    Args:
        text:       Raw inbound message text.
        has_thread: True when the message arrives inside an existing thread.

    Returns:
        Non-empty list of type strings from:
        {'correction', 'scheduling', 'question', 'task_request', 'greeting', 'followup'}
    """
    types: List[str] = []

    if re.search(
        r'(?:^|[.!?]\s+)actually\b|correction:|update:|no longer|changed to|is now',
        text, re.I
    ):
        types.append('correction')

    if re.search(r'when|meeting|schedule|calendar|appointment|deadline', text, re.I):
        types.append('scheduling')

    if re.search(r'\?|how|what|why|explain|tell me', text, re.I):
        types.append('question')

    if re.search(r'can you|please|do this|create|build|implement', text, re.I):
        types.append('task_request')

    if re.search(r"^(hey|hi|hello|good morning|what'?s up)", text, re.I):
        types.append('greeting')

    if has_thread and not types:
        types.append('followup')

    if not types:
        types.append('question')

    return types


# ---------------------------------------------------------------------------
# Component 2: Section inclusion matrix
# ---------------------------------------------------------------------------

# Section ordering used throughout this module (S2 merged into 'instructions').
SECTION_KEYS: List[str] = ['S1', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8', 'S9', 'instructions']

# Row values: True = always include, False = never include, 'C' = conditional
# (include when data is actually present after the query).
#
#                         S1    S3    S4    S5    S6    S7    S8    S9    Inst
SECTION_MATRIX: Dict[str, List] = {
    'greeting':     [True,  False, 'C',   False, 'C',   False, False, False, True],
    'question':     [True,  True,  'C',   'C',   'C',   True,  True,  'C',   True],
    'scheduling':   [True,  False, False, False, True,  'C',   False, False, True],
    'correction':   [True,  False, False, True,  False, 'C',   False, False, True],
    'followup':     [True,  'C',   False, 'C',   False, True,  True,  'C',   True],
    'task_request': [True,  'C',   False, False, 'C',   True,  True,  'C',   True],
}


def compute_section_mask(msg_types: List[str]) -> Dict[str, bool]:
    """Union the section masks for all detected message types.

    A section is included (True) when *any* matched type specifies True or 'C'
    for that column.  Because 'C' means "include if data exists", we set it to
    True here and let the query layer produce an empty string when there is
    nothing to show — the renderer then skips empty sections.

    Args:
        msg_types: List returned by classify_message().

    Returns:
        Dict mapping each SECTION_KEYS entry to a bool.
    """
    mask: Dict[str, bool] = {k: False for k in SECTION_KEYS}
    for mt in msg_types:
        row = SECTION_MATRIX.get(mt, SECTION_MATRIX['question'])
        for i, key in enumerate(SECTION_KEYS):
            cell = row[i]
            if cell is True:
                mask[key] = True
            elif cell == 'C' and not mask[key]:
                # Conditional: mark True now; empty query result will suppress it
                mask[key] = True
    return mask


# ---------------------------------------------------------------------------
# Component 3: Section cache (module-level singleton)
# ---------------------------------------------------------------------------

# Per-section TTLs in seconds.  0 = never cache (always re-query).
SECTION_TTLS: Dict[str, int] = {
    'S1': 3600,        # Identity facts: very stable
    'S3': 1800,        # Topics: changes slowly
    'S4': 7200,        # Social graph: changes rarely
    'S5': 900,         # Recent state changes: moderately volatile
    'S6': 300,         # Schedule / open items: highly volatile
    'S7': 0,           # Thread trajectory: always fresh
    'S8': 0,           # Relevant memory: query-dependent, always fresh
    'S9': 0,           # Group context: always fresh
    'instructions': 3600,  # Behavioral prefs: stable
}


class SectionCache:
    """In-memory cache with per-section TTLs.

    Thread-safety note: this is a lightweight in-process dict; it is not safe
    for concurrent multi-threaded writes.  For a multi-threaded context server,
    wrap mutations in a threading.Lock.
    """

    def __init__(self) -> None:
        self._cache: Dict[tuple, tuple] = {}

    def get(self, human_id: str, section: str) -> Optional[str]:
        """Return cached data if still valid, else None."""
        key = (human_id, section)
        if key not in self._cache:
            return None
        data, ts = self._cache[key]
        ttl = SECTION_TTLS.get(section, 0)
        if ttl == 0 or (time.monotonic() - ts) > ttl:
            self._cache.pop(key, None)
            return None
        return data  # type: ignore[return-value]

    def set(self, human_id: str, section: str, data: str) -> None:
        """Store data with the current monotonic timestamp."""
        self._cache[(human_id, section)] = (data, time.monotonic())

    def invalidate_all(self, human_id: str) -> None:
        """Force-invalidate all sections for a given human (e.g. on correction)."""
        keys = [k for k in self._cache if k[0] == human_id]
        for k in keys:
            del self._cache[k]


# Module-level singleton — shared across all calls in the same process.
_cache = SectionCache()


# ---------------------------------------------------------------------------
# Component 4: Cypher query functions
# ---------------------------------------------------------------------------

def _query_identity(session: Any, hid: str, scope: str = 'dm') -> str:
    """S1 — PersonalFact nodes (active, non-superseded) + interaction rhythm.

    Parameterized on $hid and $scope.  Filters out superseded facts and
    respects the scope hierarchy (dm < channel).
    """
    facts = session.run("""
        MATCH (pf:PersonalFact {humanId: $hid, active: true})
        WHERE NOT coalesce(pf.superseded, false)
          AND (pf.scope = 'dm' OR pf.scope = $scope)
        OPTIONAL MATCH (pf)<-[sup:SUPERSEDES]-(newer:Inference)
        WHERE sup.detected_at >= datetime() - duration('P30D')
        RETURN pf.category AS category,
               pf.key AS key,
               pf.value AS value,
               pf.confidence AS conf,
               sup.old_value AS changed_from,
               toString(sup.detected_at) AS changed_at
        ORDER BY pf.category, pf.confidence DESC
    """, hid=hid, scope=scope)

    lines: List[str] = []
    for r in facts:
        line = f"- {r['key']}: {r['value']}"
        if r['changed_from']:
            line += f" (was: {r['changed_from']})"
        lines.append(line)

    # Interaction rhythm derived from inbound Message nodes in the last 7 days.
    rhythm = session.run("""
        MATCH (m:Message {humanId: $hid, direction: 'inbound'})
        WHERE m.timestamp >= datetime() - duration('P7D')
        WITH count(m) AS cnt, max(m.timestamp) AS last_msg
        RETURN cnt,
               duration.between(last_msg, datetime()).hours AS hours_ago
    """, hid=hid).single()

    if rhythm and rhythm['cnt']:
        cnt = rhythm['cnt']
        hours = rhythm['hours_ago'] or 0
        freq = 'Active daily' if cnt >= 7 else ('Weekly' if cnt >= 2 else 'Occasional')
        last_str = f"{hours}h ago" if hours < 24 else f"{hours // 24}d ago"
        lines.append(f"- Rhythm: {freq} | Last seen: {last_str} | {cnt} msgs/7d")

    return "\n".join(lines) if lines else ""


def _query_topics(session: Any, hid: str) -> str:
    """S3 — Topic landscape: TemporalMarker signals × Topic PageRank × DISCUSSED count.

    Composite score = 0.4*signal + 0.4*pagerank + 0.2*normalised_discussion_count.

    NOTE: The `max(discussed) OVER ()` window function requires Neo4j 5.x.
    On Neo4j 4.x, replace with a separate WITH clause to compute the maximum.
    """
    # Fixed: replaced max() OVER () with subquery for Neo4j Community compatibility
    result = session.run("""
        CALL {
            MATCH (h:Human {id: $hid})-[d:DISCUSSED]->(t:Topic)
            RETURN max(d.count) AS max_d
        }
        WITH max_d
        MATCH (h:Human {id: $hid})-[d:DISCUSSED]->(t:Topic)
        OPTIONAL MATCH (tm:TemporalMarker {humanId: $hid, topicLabel: t.label})
        WHERE tm.detectedAt >= datetime() - duration('P14D')
        WITH t.label AS topic,
             t.domain AS domain,
             coalesce(tm.signal, 'STABLE') AS signal,
             coalesce(t.pagerank_score, 0) AS pr,
             d.count AS discussed,
             max_d,
             CASE tm.signal
               WHEN 'RISING'  THEN 1.0
               WHEN 'STABLE'  THEN 0.5
               ELSE 0.0
             END AS sig_score
        WITH *,
             (  0.4 * sig_score
              + 0.4 * pr
              + 0.2 * toFloat(discussed) / CASE WHEN max_d > 0 THEN max_d ELSE 1 END
             ) AS composite
        ORDER BY composite DESC
        LIMIT 8
    """, hid=hid)

    lines: List[str] = []
    for r in result:
        sig = r['signal']
        arrow = '\u2191' if sig == 'RISING' else ('\u2193' if sig == 'FADING' else '\u2192')
        composite = r['composite'] or 0.0
        lines.append(f"- [{sig}] {r['topic']} {arrow} (score: {composite:.2f})")
    return "\n".join(lines) if lines else ""


def _query_social(session: Any, hid: str, query_topic: str = '') -> str:
    """S4 — Direct connections + shared-topic connections (bounded with LIMIT).

    Both sub-queries are bounded to prevent unbounded graph traversal.
    Parameterized on $hid and $topic.
    """
    result = session.run("""
        MATCH (h:Human {id: $hid})-[r:KNOWN_THROUGH|RELATED_TO]->(other:Human)
        RETURN other.displayName AS name, type(r) AS rel_type
        LIMIT 5
    """, hid=hid)

    lines: List[str] = []
    for r in result:
        lines.append(f"- {r['name']} ({r['rel_type']})")

    # Only run the shared-topic sub-query when we have a topic hint to filter on.
    if query_topic:
        shared = session.run("""
            MATCH (h:Human {id: $hid})-[:DISCUSSED]->(t:Topic)<-[:DISCUSSED]-(other:Human)
            WHERE t.label CONTAINS $topic AND other.id <> $hid
            RETURN other.displayName AS name, count(*) AS shared_count
            ORDER BY shared_count DESC
            LIMIT 3
        """, hid=hid, topic=query_topic)
        for r in shared:
            lines.append(
                f"- {r['name']} (shared topic: {query_topic}, {r['shared_count']} discussions)"
            )

    return "\n".join(lines) if lines else ""


def _query_changes(session: Any, hid: str) -> str:
    """S5 — Recent state changes via TemporalSeq chains (last 30 days).

    Only current, non-superseded nodes.  Includes previous value when a
    SUPERSEDES relationship exists, giving the before/after context.
    Parameterized on $hid.
    """
    result = session.run("""
        MATCH (ts:TemporalSeq {humanId: $hid, isCurrent: true})
        WHERE ts.createdAt >= datetime() - duration('P30D')
          AND NOT coalesce(ts.superseded, false)
        OPTIONAL MATCH (ts)-[:SUPERSEDES]->(prior:TemporalSeq)
        RETURN ts.subject AS subject,
               ts.value AS current_val,
               prior.value AS previous_val,
               toString(ts.validFrom) AS since
        LIMIT 5
    """, hid=hid)

    lines: List[str] = []
    for r in result:
        line = f"- {r['subject']}: {r['current_val']}"
        if r['previous_val']:
            line += f" (was: {r['previous_val']})"
        lines.append(line)
    return "\n".join(lines) if lines else ""


def _query_schedule(session: Any, hid: str) -> str:
    """S6 — CalendarEvent + ActionItem + PendingQuestion, urgency-ordered.

    Three separate queries to keep each MATCH clause focused.
    Parameterized on $hid throughout.
    """
    lines: List[str] = []

    # Upcoming calendar events.
    events = session.run("""
        MATCH (ce:CalendarEvent {humanId: $hid})
        WHERE ce.status IN ['PENDING', 'CONFIRMED']
          AND NOT coalesce(ce.superseded, false)
        RETURN ce.title AS title, ce.startTime AS start, ce.eventType AS etype
        ORDER BY ce.startTime
        LIMIT 5
    """, hid=hid)
    for r in events:
        lines.append(f"- [{r['etype']}] {r['title']}: {r['start']}")

    # Open action items, high-priority first.
    actions = session.run("""
        MATCH (ai:ActionItem {humanId: $hid, status: 'OPEN'})
        WHERE NOT coalesce(ai.superseded, false)
        RETURN ai.description AS desc,
               ai.priority AS priority,
               ai.deadline AS deadline
        ORDER BY CASE ai.priority
                   WHEN 'high'   THEN 0
                   WHEN 'medium' THEN 1
                   ELSE               2
                 END
        LIMIT 5
    """, hid=hid)
    for r in actions:
        dl = f" (deadline: {r['deadline']})" if r['deadline'] else ""
        lines.append(f"- [ACTION {r['priority']}] {r['desc']}{dl}")

    # Pending questions awaiting a response.
    questions = session.run("""
        MATCH (pq:PendingQuestion {humanId: $hid, status: 'pending'})
        RETURN pq.question AS q
        LIMIT 3
    """, hid=hid)
    for r in questions:
        lines.append(f"- [QUESTION] {r['q']}")

    return "\n".join(lines) if lines else ""


def _query_thread(session: Any, hid: str, scope: str) -> str:
    """S7 — Conversation trajectory: thread stats, recent messages, episode arcs.

    Parameterized on $hid and $scope.
    """
    lines: List[str] = []

    # Aggregate thread-level statistics.
    stats = session.run("""
        MATCH (m:Message {humanId: $hid, scope: $scope})
        RETURN count(m) AS msg_count,
               toString(min(m.timestamp)) AS started,
               avg(m.sentiment) AS avg_sentiment
    """, hid=hid, scope=scope).single()

    if stats and stats['msg_count'] and stats['msg_count'] > 0:
        sent_str = ""
        if stats['avg_sentiment'] is not None:
            sent_str = f" (sentiment: {stats['avg_sentiment']:.1f})"
        lines.append(f"Thread: {stats['msg_count']} messages, started {stats['started']}{sent_str}")

    # Most recent inbound messages (truncated to 100 chars for token budget).
    recent = session.run("""
        MATCH (m:Message {humanId: $hid, scope: $scope, direction: 'inbound'})
        RETURN m.contentScrubbed AS text, toString(m.timestamp) AS ts
        ORDER BY m.timestamp DESC
        LIMIT 5
    """, hid=hid, scope=scope)
    for r in recent:
        text = (r['text'] or '')[:100]
        lines.append(f'- "{text}"')

    return "\n".join(lines) if lines else ""


def _query_group_context(session: Any, hid: str, scope: str) -> str:
    """S9 — Recent messages from other participants in the same group scope.

    Returns an empty string (and skips the section) for DM scopes.
    Parameterized on $hid and $scope.
    """
    if not scope or scope == 'dm':
        return ""

    result = session.run("""
        MATCH (m:Message {scope: $scope, direction: 'inbound'})
        WHERE m.humanId <> $hid
        OPTIONAL MATCH (h:Human {id: m.humanId})
        RETURN coalesce(h.displayName, 'Unknown') AS sender,
               m.contentScrubbed AS text,
               toString(m.timestamp) AS ts
        ORDER BY m.timestamp DESC
        LIMIT 8
    """, hid=hid, scope=scope)

    lines: List[str] = []
    for r in result:
        text = (r['text'] or '')[:80]
        lines.append(f'- {r["sender"]}: "{text}"')
    return "\n".join(lines) if lines else ""


def _build_goals_section(driver: Any, human_id: str) -> str:
    """Build Goals section from active Goal nodes."""
    try:
        with driver.session() as s:
            result = s.run("""
                MATCH (g:Goal {humanId: $hid})
                WHERE NOT coalesce(g.superseded, false)
                  AND g.status = 'active'
                RETURN g.title AS title, g.priority AS priority,
                       g.domain AS domain, g.deadline AS deadline
                ORDER BY CASE g.priority
                    WHEN 'high' THEN 0
                    WHEN 'medium' THEN 1
                    WHEN 'low' THEN 2
                    ELSE 3
                END
            """, hid=human_id)
            goals = [dict(r) for r in result]

        if not goals:
            return ""

        lines = ["## Goals"]
        for g in goals:
            priority = g.get('priority', 'medium').upper()
            domain = g.get('domain', '')
            deadline = g.get('deadline', '')
            detail = f" ({domain}" if domain else ""
            if deadline:
                detail += f", deadline: {deadline}"
            if detail:
                detail += ")"
            lines.append(f"- [{priority}] {g['title']}{detail}")

        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"Goals section failed: {e}")
        return ""


def _build_knowledge_section(driver: Any, human_id: str) -> str:
    """Build Knowledge section from KnowledgeLevel nodes."""
    try:
        with driver.session() as s:
            result = s.run("""
                MATCH (k:KnowledgeLevel {humanId: $hid})
                WHERE NOT coalesce(k.superseded, false)
                RETURN k.domain AS domain, k.level AS level
                ORDER BY CASE k.level
                    WHEN 'expert' THEN 0
                    WHEN 'proficient' THEN 1
                    WHEN 'learning' THEN 2
                    WHEN 'aware' THEN 3
                    ELSE 4
                END
            """, hid=human_id)
            levels = [dict(r) for r in result]

        if not levels:
            return ""

        # Group by level
        by_level = {}
        for item in levels:
            lvl = item.get('level', 'unknown').capitalize()
            by_level.setdefault(lvl, []).append(item['domain'])

        lines = ["## Knowledge"]
        for level, domains in by_level.items():
            lines.append(f"- {level}: {', '.join(domains)}")

        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"Knowledge section failed: {e}")
        return ""


def _build_boundaries_section(driver: Any, human_id: str) -> str:
    """Build Boundaries section from EmotionalTrigger nodes."""
    try:
        with driver.session() as s:
            result = s.run("""
                MATCH (et:EmotionalTrigger {humanId: $hid})
                WHERE NOT coalesce(et.superseded, false)
                RETURN et.trigger AS trigger, et.reaction AS reaction,
                       et.context AS context
            """, hid=human_id)
            triggers = [dict(r) for r in result]

        if not triggers:
            return ""

        lines = ["## Boundaries"]
        for t in triggers:
            reaction = t.get('reaction', '')
            trigger = t.get('trigger', '')
            if reaction in ('frustrated', 'uncomfortable', 'boundary'):
                lines.append(f"- AVOID: {trigger} (triggers {reaction})")
            elif reaction == 'energized':
                lines.append(f"- DO: {trigger} (energizes them)")

        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"Boundaries section failed: {e}")
        return ""


def _build_instructions(session: Any, hid: str, scope: str = 'dm') -> str:
    """Instructions section — S2 merged in.

    Combines ASSISTANT_PREF PersonalFact nodes (direct behavioral imperatives)
    with Preference nodes (DO/AVOID directives derived from valence).
    Parameterized on $hid and $scope.
    """
    lines: List[str] = []

    # Imperative commands stored as ASSISTANT_PREF personal facts.
    prefs = session.run("""
        MATCH (pf:PersonalFact {humanId: $hid, category: 'ASSISTANT_PREF', active: true})
        WHERE NOT coalesce(pf.superseded, false)
        RETURN pf.value AS instruction
        ORDER BY pf.confidence DESC
    """, hid=hid)
    for r in prefs:
        lines.append(f"- {r['instruction']}")

    # Communication preferences converted to directive language.
    comm = session.run("""
        MATCH (p:Preference {humanId: $hid, active: true})
        WHERE NOT coalesce(p.superseded, false)
          AND (p.scope = 'dm' OR p.scope = $scope)
        RETURN p.valence AS valence, p.preference AS pref, p.strength AS strength
        ORDER BY p.strength DESC
        LIMIT 8
    """, hid=hid, scope=scope)
    for r in comm:
        valence = r['valence']
        if valence == 'LIKE':
            lines.append(f"- DO: {r['pref']}")
        elif valence == 'DISLIKE':
            lines.append(f"- AVOID: {r['pref']}")

    return "\n".join(lines) if lines else ""


# ---------------------------------------------------------------------------
# Component 5: Query dispatcher
# ---------------------------------------------------------------------------

# Maps section key → callable(session, hid, scope, query_topic) → str.
# S8 is None here because it is handled via parallel_memory_search (no session).
QUERY_MAP: Dict[str, Any] = {
    'S1':           lambda s, hid, scope, qt: _query_identity(s, hid, scope),
    'S3':           lambda s, hid, scope, qt: _query_topics(s, hid),
    'S4':           lambda s, hid, scope, qt: _query_social(s, hid, qt),
    'S5':           lambda s, hid, scope, qt: _query_changes(s, hid),
    'S6':           lambda s, hid, scope, qt: _query_schedule(s, hid),
    'S7':           lambda s, hid, scope, qt: _query_thread(s, hid, scope),
    'S8':           None,   # Handled separately via parallel_memory_search
    'S9':           lambda s, hid, scope, qt: _query_group_context(s, hid, scope),
    'instructions': lambda s, hid, scope, qt: _build_instructions(s, hid, scope),
}


# ---------------------------------------------------------------------------
# Component 6: Profile renderer
# ---------------------------------------------------------------------------

SECTION_HEADERS: Dict[str, str] = {
    'S1': '## Who',
    'S3': '## Topics',
    'S4': '## Connections',
    'S5': '## Recent Changes',
    'S6': '## Schedule',
    'S7': '## This Thread',
    'S8': '## Relevant Memory',
    'S9': '## Group Context',
    'goals': '## Goals',
    'knowledge': '## Knowledge',
    'boundaries': '## Boundaries',
}


def render_profile(sections: Dict[str, str], human_name: str) -> str:
    """Assemble the final context string from populated section data.

    Sections are emitted in canonical order (S1 → S9), skipping any that are
    empty.  The instructions block is appended outside the <context> tag so
    that the LLM treats it as a system-level directive rather than user data.

    Args:
        sections:   Dict of section_key → content string (empty strings skipped).
        human_name: Display name used in the opening XML tag.

    Returns:
        Formatted multi-section context string, ready for LLM prompt injection.
    """
    parts: List[str] = [f'<context human="{human_name}">']

    for key in ['S1', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8', 'S9', 'goals', 'knowledge', 'boundaries']:
        if key in sections and sections[key]:
            parts.append(f"{SECTION_HEADERS[key]}\n{sections[key]}")

    parts.append('</context>')

    if 'instructions' in sections and sections['instructions']:
        parts.append(f'\n<instructions>\n{sections["instructions"]}\n</instructions>')

    return '\n\n'.join(parts)


# ---------------------------------------------------------------------------
# Component 7: Topic hint extractor
# ---------------------------------------------------------------------------

# Common English stopwords excluded from topic hint extraction.
_STOPWORDS = frozenset({
    'the', 'a', 'an', 'is', 'are', 'was', 'were', 'do', 'does',
    'did', 'has', 'have', 'had', 'be', 'been', 'being', 'will',
    'would', 'could', 'should', 'may', 'might', 'can', 'to',
    'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from', 'about',
    'what', 'how', 'when', 'where', 'why', 'who', 'which',
    'this', 'that', 'these', 'those', 'my', 'your', 'his', 'her',
    'its', 'our', 'their', 'i', 'you', 'he', 'she', 'it', 'we', 'they',
    'me', 'him', 'us', 'them', 'and', 'or', 'but', 'not', 'no', 'yes',
    'hey', 'hi', 'hello', 'please', 'thanks', 'thank',
})


def _extract_topic_hint(text: str) -> str:
    """Extract a single topic keyword from the message for social graph filtering.

    Intentionally simple — picks the longest non-stopword token of 3+ chars.
    No LLM call; purely lexical.  Returns an empty string when no content word
    is found (the social graph query then skips the shared-topic sub-query).

    Args:
        text: Raw message text.

    Returns:
        A single lowercase word, or '' if none found.
    """
    words = re.findall(r'\b\w{3,}\b', text.lower())
    content_words = [w for w in words if w not in _STOPWORDS]
    if content_words:
        return max(content_words, key=len)
    return ""


# ---------------------------------------------------------------------------
# Component 8: Main orchestrator
# ---------------------------------------------------------------------------

def build_context_profile(
    human_id: str,
    message_text: str,
    scope: str = 'dm',
    has_thread: bool = False,
) -> str:
    """Build a structured context profile for a given human and inbound message.

    Pipeline:
      1. Classify message into one or more types (multi-label).
      2. Force-invalidate the section cache when a correction is detected.
      3. Compute the union section mask across all detected types.
      4. Look up the human's display name from Neo4j.
      5. For each active section: check cache → run Cypher → populate cache.
         S8 (Relevant Memory) is delegated to parallel_memory_search.
      6. Render the populated sections into the final XML-wrapped string.

    This function never raises.  Any Neo4j connectivity issue or unexpected
    exception causes it to log the error and return an empty string, allowing
    the caller to proceed without context (graceful degradation).

    Args:
        human_id:     Unique identifier for the Human node in Neo4j.
        message_text: Raw inbound message text used for classification and
                      topic hint extraction.
        scope:        Message scope — 'dm' for direct message, or a group/channel
                      identifier.  Affects which S9 group-context data is fetched
                      and which Preference nodes are included.
        has_thread:   True when the message is part of an existing conversation
                      thread (used to trigger the 'followup' message type).

    Returns:
        Rendered context profile string (may be empty on error or no data).
    """
    global _cache

    try:
        # Step 1: Classify (multi-label)
        msg_types = classify_message(message_text, has_thread)
        logger.debug("classify_message(%r) → %s", message_text[:60], msg_types)

        # Step 2: Force-invalidate cache on correction
        if 'correction' in msg_types:
            _cache.invalidate_all(human_id)
            logger.debug("Cache invalidated for %s (correction detected)", human_id)

        # Step 3: Compute section mask (union across all types)
        mask = compute_section_mask(msg_types)
        logger.debug("Section mask for %s: %s", human_id, mask)

        # Step 4: Resolve human display name
        driver = get_driver()
        human_name = human_id  # Fallback to ID if no displayName stored
        with driver.session() as session:
            name_result = session.run(
                "MATCH (h:Human {id: $hid}) RETURN h.displayName",
                hid=human_id,
            ).single()
            if name_result and name_result[0]:
                human_name = name_result[0]

        # Step 5: Query each active section
        sections: Dict[str, str] = {}
        query_topic = _extract_topic_hint(message_text)

        with driver.session() as session:
            for section_key in SECTION_KEYS:
                if not mask.get(section_key):
                    continue

                # Cache hit
                cached = _cache.get(human_id, section_key)
                if cached is not None:
                    sections[section_key] = cached
                    logger.debug("Cache hit: %s / %s", human_id, section_key)
                    continue

                # S8: delegated to parallel_memory_search (manages its own connection)
                if section_key == 'S8':
                    try:
                        from parallel_memory_search import search_memory  # noqa: PLC0415
                        result = search_memory(message_text, human_id)
                        # Use as_profile_string() for [fact]/[msg] format
                        # matching the structured profile spec (revision #9).
                        data = result.as_profile_string(max_chars=1200)
                    except Exception as exc:
                        logger.warning("parallel_memory_search failed for S8: %s", exc)
                        data = ""

                elif section_key in QUERY_MAP and QUERY_MAP[section_key] is not None:
                    try:
                        data = QUERY_MAP[section_key](session, human_id, scope, query_topic)
                    except Exception as exc:
                        logger.warning("Query failed for %s: %s", section_key, exc)
                        data = ""

                else:
                    data = ""

                # Only store and cache non-empty results (conditional sections
                # that returned nothing are naturally excluded from the output).
                if data:
                    sections[section_key] = data
                    _cache.set(human_id, section_key, data)

        # Step 5b: Build deep vector sections (Goals, Knowledge, Boundaries)
        # These use their own driver sessions and never raise.
        goals_data = _build_goals_section(driver, human_id)
        if goals_data:
            sections['goals'] = goals_data

        knowledge_data = _build_knowledge_section(driver, human_id)
        if knowledge_data:
            # Strip the "## Knowledge" header since render_profile adds it
            klines = knowledge_data.split("\n")
            sections['knowledge'] = "\n".join(klines[1:]) if len(klines) > 1 else knowledge_data

        boundaries_data = _build_boundaries_section(driver, human_id)
        if boundaries_data:
            # Strip the "## Boundaries" header since render_profile adds it
            blines = boundaries_data.split("\n")
            sections['boundaries'] = "\n".join(blines[1:]) if len(blines) > 1 else boundaries_data

        # Also strip "## Goals" header from goals_data for consistency
        if 'goals' in sections:
            glines = sections['goals'].split("\n")
            if glines and glines[0].startswith("## "):
                sections['goals'] = "\n".join(glines[1:])

        # Step 6: Render
        profile = render_profile(sections, human_name)
        logger.debug(
            "build_context_profile: %d sections, ~%d chars for %s",
            len(sections), len(profile), human_id,
        )
        return profile

    except Exception as exc:
        logger.error("build_context_profile failed for %s: %s", human_id, exc, exc_info=True)
        return ""  # Graceful degradation — never crash the caller
