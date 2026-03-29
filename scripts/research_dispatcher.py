#!/usr/bin/env python3
"""
Research Dispatcher — Routes curiosity questions to research methods and executes them.

Takes a ResearchQuestion (from knowledge_graph.py) and resolves it via the
appropriate method: ask_human, web_search, neo4j_query, or agent_delegation.

Usage:
    from research_dispatcher import dispatch, classify_method, ResearchMethod
"""

import json
import logging
import os
import re
import sys
import uuid
from dataclasses import dataclass, field as dc_field
from datetime import datetime
from enum import Enum
from typing import Optional
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import neo4j_session

from knowledge_graph import (
    create_knowledge_answer,
    update_question_status,
    get_or_create_topic,
    link_answer_to_topic,
    link_answer_to_human,
)
from curiosity_engine import _send_signal_dm, _is_valid_signal_phone
from pending_question import create_question as create_pending_question
from consent_decorator import check_consent
from curiosity_budget import record_spend, complete_spend

logger = logging.getLogger(__name__)
LOCAL_TZ = ZoneInfo("America/New_York")


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


class ResearchMethod(Enum):
    ASK_HUMAN = "ask_human"
    WEB_SEARCH = "web_search"
    NEO4J_QUERY = "neo4j_query"
    AGENT_DELEGATION = "agent_delegation"


@dataclass
class ResearchResult:
    answer_text: str
    confidence: float       # 0-1
    sources: list           # URLs, human IDs, etc.
    method: str
    success: bool = True


# ---------------------------------------------------------------------------
# Rule-based routing patterns
# ---------------------------------------------------------------------------

ASK_HUMAN_PATTERNS = [
    r"what (do|does|did) .+ (think|feel|prefer|want)",
    r"(are|is) .+ (free|available|coming|going)",
    r"how (do|does|did) .+ (like|feel about)",
    r"where (did|does|do) .+ (grow up|live|come from|work)",
    r"what should i call",
    r"what timezone",
]

WEB_SEARCH_PATTERNS = [
    r"weather|forecast|temperature",
    r"(latest|recent|current|news) .+ (about|in|on|for)",
    r"what is .+ (population|capital|currency|language)",
    r"how (much|many|far|long|old)",
    r"when (was|is|did|does|will)",
    r"(price|cost|rate) of",
]

NEO4J_QUERY_PATTERNS = [
    r"(task|tasks).*(fail|complet|score|rate|success|performance)",
    r"(skill|skills).*(invoc|usage|success|fail)",
    r"(agent|agents).*(status|health|performance|load)",
    r"how (well|often|many).*(rout|dispatch|assign)",
    r"(blind spot|gap|missing|lacking)",
]


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def classify_method(question_text: str, category: str, target: str) -> ResearchMethod:
    """Two-tier classification: rules first, then heuristic fallback.

    Tier 1 — Structural rules:
      - If target is a human_id and category is 'human' or 'contextual' -> ASK_HUMAN
      - If category is 'self' -> NEO4J_QUERY

    Tier 2 — Regex pattern matching against question_text:
      - Check ASK_HUMAN_PATTERNS
      - Check NEO4J_QUERY_PATTERNS
      - Check WEB_SEARCH_PATTERNS

    Default: WEB_SEARCH
    """
    q = question_text.lower().strip()

    # Tier 1: structural rules
    if target and category in ("human", "contextual"):
        # Non-empty target with human/contextual category -> asking a person
        return ResearchMethod.ASK_HUMAN

    if category == "self":
        return ResearchMethod.NEO4J_QUERY

    # Tier 2: regex pattern matching
    for pattern in ASK_HUMAN_PATTERNS:
        if re.search(pattern, q, re.IGNORECASE):
            return ResearchMethod.ASK_HUMAN

    for pattern in NEO4J_QUERY_PATTERNS:
        if re.search(pattern, q, re.IGNORECASE):
            return ResearchMethod.NEO4J_QUERY

    for pattern in WEB_SEARCH_PATTERNS:
        if re.search(pattern, q, re.IGNORECASE):
            return ResearchMethod.WEB_SEARCH

    # Default fallback
    return ResearchMethod.WEB_SEARCH


# ---------------------------------------------------------------------------
# Main dispatch
# ---------------------------------------------------------------------------


def dispatch(question: dict, config: dict = None) -> ResearchResult:
    """Main entry: classify method, execute research, return result.

    Args:
        question: dict with keys: question_id, question_text, category,
                  target, research_method, priority
        config: optional config dict (unused currently, reserved for future)

    Returns:
        ResearchResult with answer, confidence, sources, method, success
    """
    question_id = question["question_id"]
    question_text = question["question_text"]
    category = question.get("category", "world")
    target = question.get("target", "")
    priority = question.get("priority", 0.5)

    # 1. Classify method (or use pre-set value)
    if question.get("research_method") and question["research_method"] != "auto":
        try:
            method = ResearchMethod(question["research_method"])
        except ValueError:
            method = classify_method(question_text, category, target)
    else:
        method = classify_method(question_text, category, target)

    logger.info(
        "Dispatching question %s via %s: %s",
        question_id[:8], method.value, question_text[:60],
    )

    # 2. Update question status to DISPATCHED
    update_question_status(question_id, "DISPATCHED")

    # 3. Record spend cycle
    cycle_id = f"research-{question_id[:12]}"
    record_spend(
        cycle_id=cycle_id,
        category=category,
        question=question_text[:200],
    )

    # 4. Execute via appropriate method
    result = None
    try:
        if method == ResearchMethod.ASK_HUMAN:
            result = _execute_ask_human(question)
        elif method == ResearchMethod.WEB_SEARCH:
            result = _execute_web_search(question)
        elif method == ResearchMethod.NEO4J_QUERY:
            result = _execute_neo4j_query(question)
        elif method == ResearchMethod.AGENT_DELEGATION:
            result = _execute_agent_delegation(question)
        else:
            result = ResearchResult(
                answer_text="Unknown research method",
                confidence=0.0,
                sources=[],
                method=method.value,
                success=False,
            )
    except Exception as e:
        logger.error("Research execution failed for %s: %s", question_id[:8], e)
        result = ResearchResult(
            answer_text=f"Research failed: {e}",
            confidence=0.0,
            sources=[],
            method=method.value,
            success=False,
        )

    # 5/6. Create KnowledgeAnswer on success, update question status
    if result.success and result.confidence > 0:
        # Synchronous answer available — persist it
        answer_id = create_knowledge_answer(
            question_id=question_id,
            answer_text=result.answer_text,
            summary=result.answer_text[:200],
            confidence=result.confidence,
            method=result.method,
            sources=result.sources,
        )
        update_question_status(question_id, "RESOLVED", answer_text=result.answer_text)

        # Link answer to topic if category maps to a topic
        if category and category != "world":
            topic_label = get_or_create_topic(category)
            link_answer_to_topic(answer_id, topic_label)

        # Link answer to human if target is a human_id
        if target and category in ("human", "contextual"):
            link_answer_to_human(answer_id, target)

        logger.info("Resolved question %s with confidence %.2f", question_id[:8], result.confidence)

    elif result.success and result.confidence == 0:
        # Async answer (ask_human, agent_delegation) — stays DISPATCHED
        logger.info("Question %s dispatched async via %s", question_id[:8], result.method)

    else:
        # Failure
        update_question_status(question_id, "UNRESOLVED")
        logger.warning("Question %s unresolved: %s", question_id[:8], result.answer_text[:100])

    # 7. Complete spend record
    outcome = "resolved" if (result.success and result.confidence > 0) else (
        "dispatched_async" if (result.success and result.confidence == 0) else "failed"
    )
    complete_spend(cycle_id, outcome)

    return result


# ---------------------------------------------------------------------------
# Method implementations
# ---------------------------------------------------------------------------


def _execute_ask_human(question: dict) -> ResearchResult:
    """Send question via Signal DM using existing PendingQuestion system.

    Pre-checks:
    - Human has displayName (skip if not)
    - Human has valid phone (use _is_valid_signal_phone)
    - Consent check for general_curiosity or personal_curiosity

    Creates PendingQuestion with qtype='general_curiosity',
    sends via _send_signal_dm, returns pending result.

    NOTE: Returns success=True but confidence=0 because the actual answer
    arrives asynchronously (human replies later). The answer processing
    pipeline in general_curiosity.py handles that.
    """
    target = question.get("target", "")
    question_text = question["question_text"]
    question_id = question["question_id"]
    category = question.get("category", "human")

    if not target:
        return ResearchResult(
            answer_text="No target human specified",
            confidence=0.0,
            sources=[],
            method=ResearchMethod.ASK_HUMAN.value,
            success=False,
        )

    # Fetch human profile
    try:
        with neo4j_session() as session:
            result = session.run(
                """
                MATCH (h:Human {id: $hid})
                OPTIONAL MATCH (h)-[:IDENTIFIED_BY]->(i:Identifier {type: 'SIGNAL_PHONE'})
                RETURN h.displayName AS displayName, i.value AS phone
                """,
                hid=target,
            )
            record = result.single()
    except Exception as e:
        logger.error("Failed to fetch human %s: %s", target[:8], e)
        return ResearchResult(
            answer_text=f"Failed to look up human: {e}",
            confidence=0.0,
            sources=[],
            method=ResearchMethod.ASK_HUMAN.value,
            success=False,
        )

    if not record:
        return ResearchResult(
            answer_text=f"Human {target[:8]} not found in graph",
            confidence=0.0,
            sources=[],
            method=ResearchMethod.ASK_HUMAN.value,
            success=False,
        )

    display_name = record["displayName"]
    phone = record["phone"]

    # Pre-check: displayName
    if not display_name:
        return ResearchResult(
            answer_text=f"Human {target[:8]} has no displayName, skipping",
            confidence=0.0,
            sources=[],
            method=ResearchMethod.ASK_HUMAN.value,
            success=False,
        )

    # Pre-check: valid phone
    if not phone or not _is_valid_signal_phone(phone):
        return ResearchResult(
            answer_text=f"Human {target[:8]} has no valid phone number",
            confidence=0.0,
            sources=[],
            method=ResearchMethod.ASK_HUMAN.value,
            success=False,
        )

    # Pre-check: consent
    consent_category = "personal_curiosity" if category == "human" else "general_curiosity"
    if not check_consent(target, consent_category):
        return ResearchResult(
            answer_text=f"No {consent_category} consent for {target[:8]}",
            confidence=0.0,
            sources=[],
            method=ResearchMethod.ASK_HUMAN.value,
            success=False,
        )

    # Create PendingQuestion
    try:
        pq_id = create_pending_question(
            human_id=target,
            question=question_text,
            field="curiosity_research",
            qtype="general_curiosity",
            context={
                "research_question_id": question_id,
                "category": category,
                "source": "research_dispatcher",
            },
            ttl_minutes=60 * 24,  # 24 hours
        )
    except Exception as e:
        logger.warning("Could not create PendingQuestion for %s: %s", target[:8], e)
        return ResearchResult(
            answer_text=f"Could not create pending question: {e}",
            confidence=0.0,
            sources=[],
            method=ResearchMethod.ASK_HUMAN.value,
            success=False,
        )

    # Send via Signal DM
    sent = _send_signal_dm(phone, question_text)
    if not sent:
        logger.warning("Signal send failed for %s", target[:8])
        # Mark the PendingQuestion as SEND_FAILED
        try:
            with neo4j_session() as session:
                session.run(
                    """
                    MATCH (pq:PendingQuestion {id: $qid})
                    WHERE pq.status = 'PENDING'
                    SET pq.status = 'SEND_FAILED', pq.answeredAt = datetime()
                    """,
                    qid=pq_id,
                )
        except Exception:
            pass

        return ResearchResult(
            answer_text="Signal DM send failed",
            confidence=0.0,
            sources=[],
            method=ResearchMethod.ASK_HUMAN.value,
            success=False,
        )

    logger.info("Asked human %s (%s): %s", display_name, target[:8], question_text[:60])

    # Async: answer comes later via reply pipeline
    return ResearchResult(
        answer_text=f"Question sent to {display_name} via Signal DM (pending reply)",
        confidence=0.0,  # Async — no answer yet
        sources=[target],
        method=ResearchMethod.ASK_HUMAN.value,
        success=True,
    )


def _execute_web_search(question: dict) -> ResearchResult:
    """Search the web and summarize the answer.

    If TAVILY_API_KEY is set, use Tavily search API.
    Otherwise, return ResearchResult with success=False.
    """
    question_text = question["question_text"]
    tavily_key = os.environ.get("TAVILY_API_KEY")

    if not tavily_key:
        return ResearchResult(
            answer_text="Web search unavailable: TAVILY_API_KEY not set",
            confidence=0.0,
            sources=[],
            method=ResearchMethod.WEB_SEARCH.value,
            success=False,
        )

    import requests

    try:
        resp = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": tavily_key,
                "query": question_text,
                "search_depth": "basic",
                "max_results": 5,
                "include_answer": True,
            },
            timeout=(5, 30),
        )
        resp.raise_for_status()
        data = resp.json()

        answer = data.get("answer", "")
        results = data.get("results", [])
        sources = [r.get("url", "") for r in results if r.get("url")]

        if not answer and results:
            # Synthesize from top results
            snippets = [r.get("content", "")[:200] for r in results[:3]]
            answer = " | ".join(s for s in snippets if s)

        if not answer:
            return ResearchResult(
                answer_text="Web search returned no results",
                confidence=0.0,
                sources=sources,
                method=ResearchMethod.WEB_SEARCH.value,
                success=False,
            )

        return ResearchResult(
            answer_text=answer,
            confidence=0.7,
            sources=sources,
            method=ResearchMethod.WEB_SEARCH.value,
            success=True,
        )

    except Exception as e:
        logger.error("Web search failed: %s", e)
        return ResearchResult(
            answer_text=f"Web search error: {e}",
            confidence=0.0,
            sources=[],
            method=ResearchMethod.WEB_SEARCH.value,
            success=False,
        )


# ---------------------------------------------------------------------------
# Neo4j query templates
# ---------------------------------------------------------------------------

_NEO4J_QUERY_TEMPLATES = {
    "task_performance": {
        "patterns": [r"task.*(?:fail|complet|success|rate|performance)", r"how.*tasks"],
        "query": """
            MATCH (t:Task)
            WHERE t.created >= datetime() - duration('P7D')
            RETURN t.status AS status, count(*) AS count
            ORDER BY count DESC
        """,
        "format": "Task performance (last 7 days): {results}",
    },
    "skill_usage": {
        "patterns": [r"skill.*(?:invoc|usage|success|fail)", r"which.*skills"],
        "query": """
            MATCH (t:Task)
            WHERE t.created >= datetime() - duration('P7D')
              AND t.skill IS NOT NULL
            RETURN t.skill AS skill, count(*) AS count,
                   avg(t.score) AS avg_score
            ORDER BY count DESC
            LIMIT 10
        """,
        "format": "Skill usage (last 7 days): {results}",
    },
    "agent_health": {
        "patterns": [r"agent.*(?:status|health|performance|load)", r"how.*agents"],
        "query": """
            MATCH (t:Task)
            WHERE t.created >= datetime() - duration('P1D')
            RETURN t.agent AS agent, t.status AS status, count(*) AS count
            ORDER BY agent, count DESC
        """,
        "format": "Agent status (last 24h): {results}",
    },
    "routing_metrics": {
        "patterns": [r"rout.*(?:dispatch|assign)", r"how.*rout"],
        "query": """
            MATCH (t:Task)
            WHERE t.created >= datetime() - duration('P7D')
            RETURN t.agent AS agent, count(*) AS tasks_assigned
            ORDER BY tasks_assigned DESC
        """,
        "format": "Routing distribution (last 7 days): {results}",
    },
    "blind_spots": {
        "patterns": [r"blind spot|gap|missing|lacking"],
        "query": """
            MATCH (t:Task)
            WHERE t.status = 'FAILED'
              AND t.created >= datetime() - duration('P14D')
            RETURN t.description AS description, t.agent AS agent,
                   toString(t.created) AS created
            ORDER BY t.created DESC
            LIMIT 10
        """,
        "format": "Recent failures (potential blind spots): {results}",
    },
}


def _execute_neo4j_query(question: dict) -> ResearchResult:
    """Run internal Neo4j queries for self-reflection.

    Selects the best query template based on question text pattern matching,
    runs the query, and formats results as natural text.
    """
    question_text = question["question_text"].lower()

    # Find the best matching template
    best_template = None
    for name, template in _NEO4J_QUERY_TEMPLATES.items():
        for pattern in template["patterns"]:
            if re.search(pattern, question_text, re.IGNORECASE):
                best_template = template
                break
        if best_template:
            break

    if not best_template:
        # Fallback: general task summary
        best_template = _NEO4J_QUERY_TEMPLATES["task_performance"]

    try:
        with neo4j_session() as session:
            result = session.run(best_template["query"])
            records = [dict(r) for r in result]

        if not records:
            return ResearchResult(
                answer_text="Query returned no results",
                confidence=0.3,
                sources=["neo4j"],
                method=ResearchMethod.NEO4J_QUERY.value,
                success=True,
            )

        # Format results as readable text
        formatted_rows = []
        for rec in records:
            parts = [f"{k}={v}" for k, v in rec.items()]
            formatted_rows.append(", ".join(parts))
        results_text = "; ".join(formatted_rows)

        answer = best_template["format"].format(results=results_text)

        return ResearchResult(
            answer_text=answer,
            confidence=0.9,
            sources=["neo4j"],
            method=ResearchMethod.NEO4J_QUERY.value,
            success=True,
        )

    except Exception as e:
        logger.error("Neo4j query failed: %s", e)
        return ResearchResult(
            answer_text=f"Neo4j query error: {e}",
            confidence=0.0,
            sources=[],
            method=ResearchMethod.NEO4J_QUERY.value,
            success=False,
        )


def _execute_agent_delegation(question: dict) -> ResearchResult:
    """Create a Kurultai Task for deep research.

    Creates a Task node in Neo4j with:
    - source: 'curiosity_engine'
    - priority: 'low'
    - assigned_to: best-fit agent (mongke for research, temujin for code analysis)
    - description: the question text
    - metadata: curiosity_question_id linking back

    Returns success=True but confidence=0 (async, answer comes later).
    """
    question_text = question["question_text"]
    question_id = question["question_id"]
    category = question.get("category", "world")

    # Route to best-fit agent
    if category == "self" or re.search(r"code|script|implement|debug", question_text, re.IGNORECASE):
        agent = "temujin"
    else:
        agent = "mongke"

    task_id = f"research-{str(uuid.uuid4())[:8]}"
    now = datetime.now(LOCAL_TZ).isoformat()

    try:
        with neo4j_session() as session:
            session.run(
                """
                CREATE (t:Task {
                    label: $label,
                    description: $description,
                    status: 'QUEUED',
                    priority: 'low',
                    source: 'curiosity_engine',
                    assigned_to: $agent,
                    created: datetime($now),
                    metadata: $metadata
                })
                """,
                label=task_id,
                description=question_text,
                agent=agent,
                now=now,
                metadata=json.dumps({
                    "curiosity_question_id": question_id,
                    "category": category,
                    "origin": "research_dispatcher",
                }),
            )

        logger.info(
            "Delegated question %s to agent %s as task %s",
            question_id[:8], agent, task_id,
        )

        return ResearchResult(
            answer_text=f"Delegated to agent {agent} as task {task_id} (async)",
            confidence=0.0,  # Async — no answer yet
            sources=[f"task:{task_id}", f"agent:{agent}"],
            method=ResearchMethod.AGENT_DELEGATION.value,
            success=True,
        )

    except Exception as e:
        logger.error("Agent delegation failed: %s", e)
        return ResearchResult(
            answer_text=f"Agent delegation failed: {e}",
            confidence=0.0,
            sources=[],
            method=ResearchMethod.AGENT_DELEGATION.value,
            success=False,
        )


# ---------------------------------------------------------------------------
# CLI self-test
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    test_cases = [
        # (question_text, category, target, expected_method)
        # ASK_HUMAN — structural rule: human category + target
        ("What does Alex think about the new schedule?", "human", "uuid-alex-123", ResearchMethod.ASK_HUMAN),
        ("Where did Marco grow up?", "contextual", "uuid-marco-456", ResearchMethod.ASK_HUMAN),
        # ASK_HUMAN — regex pattern
        ("What timezone are you in?", "world", "", ResearchMethod.ASK_HUMAN),
        ("How does Sarah feel about hiking?", "world", "", ResearchMethod.ASK_HUMAN),
        ("Is everyone free on Saturday?", "world", "", ResearchMethod.ASK_HUMAN),
        # NEO4J_QUERY — structural rule: self category
        ("How well am I performing?", "self", "", ResearchMethod.NEO4J_QUERY),
        # NEO4J_QUERY — regex pattern
        ("What is the task completion rate?", "world", "", ResearchMethod.NEO4J_QUERY),
        ("Which skills have the highest invocation count?", "world", "", ResearchMethod.NEO4J_QUERY),
        ("Are there any agent health issues?", "world", "", ResearchMethod.NEO4J_QUERY),
        ("What are our blind spots?", "world", "", ResearchMethod.NEO4J_QUERY),
        # WEB_SEARCH — regex pattern
        ("What's the weather in New York this weekend?", "world", "", ResearchMethod.WEB_SEARCH),
        ("What is the population of Tokyo?", "world", "", ResearchMethod.WEB_SEARCH),
        ("When was the Eiffel Tower built?", "world", "", ResearchMethod.WEB_SEARCH),
        ("How much does a Tesla Model 3 cost?", "world", "", ResearchMethod.WEB_SEARCH),
        # WEB_SEARCH — default fallback
        ("Tell me something interesting about octopuses", "world", "", ResearchMethod.WEB_SEARCH),
    ]

    passed = 0
    failed = 0
    for q_text, cat, tgt, expected in test_cases:
        result = classify_method(q_text, cat, tgt)
        status = "PASS" if result == expected else "FAIL"
        if status == "PASS":
            passed += 1
        else:
            failed += 1
        print(f"  [{status}] classify_method(\"{q_text[:50]}...\", {cat}, {tgt!r})")
        print(f"         expected={expected.value}, got={result.value}")

    print(f"\n{passed}/{passed + failed} tests passed")
    if failed > 0:
        sys.exit(1)
