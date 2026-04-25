#!/usr/bin/env python3
"""
General Curiosity Engine — CLI tool for agent-driven curiosity.

The agent (Claude Code via agentTurn cron) is the brain. This script is the hands.
It provides 4 modes the agent calls during a curiosity sweep:

    --context          Print what Kublai knows (humans, stats, quotas, recent questions)
    --store JSON       Store a researched question + answer in the knowledge graph
    --ask-human JSON   Send a curiosity question to a human via Signal DM
    --process-answers  Pick up human replies and store as knowledge
    --stats            Print today's budget stats

Usage by the agent:
    # 1. Read context
    python3 general_curiosity.py --context

    # 2. Research and store findings
    python3 general_curiosity.py --store '{"question":"...","answer":"...","category":"self",...}'

    # 3. Ask a human something
    python3 general_curiosity.py --ask-human '{"human_id":"...","question":"..."}'

    # 4. Process any replies from previous sweeps
    python3 general_curiosity.py --process-answers
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import os
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from curiosity_context import assemble_context, summarize_for_prompt
from curiosity_dedup import is_duplicate_question, get_canonical_hash
from curiosity_budget import load_config, get_budget_stage, record_spend, complete_spend, get_stats
from knowledge_graph import (
    create_research_question,
    update_question_status,
    create_knowledge_answer,
    get_or_create_topic,
    link_answer_to_topic,
    link_answer_to_human,
)
from neo4j_task_tracker import neo4j_session

LOCAL_TZ = ZoneInfo("America/New_York")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# --context: Print curiosity context for the agent
# ---------------------------------------------------------------------------

def cmd_context():
    """Print formatted context so the agent knows what to be curious about."""
    config = load_config()

    if not config.get("enabled", True):
        print("Curiosity engine is DISABLED. Enable it in ~/.openclaw/config/curiosity.json")
        return

    stage = get_budget_stage("human")
    if stage == "suspend":
        print("Budget EXHAUSTED for today. No curiosity questions should be generated.")
        return

    ctx = assemble_context()
    print(summarize_for_prompt(ctx))


# ---------------------------------------------------------------------------
# --store: Store a researched question + answer
# ---------------------------------------------------------------------------

def cmd_store(json_str: str):
    """Store a curiosity finding in the knowledge graph.

    Expected JSON:
    {
        "question": "Why is kublai failing 54% of tasks?",
        "answer": "12 of 12 failures were routing timeouts",
        "category": "self",           # human|self|world|contextual
        "target": "self",             # human_id, "self", or "world"
        "method": "neo4j_query",      # neo4j_query|web_search|ask_human|agent_delegation
        "confidence": 0.9,            # 0.0-1.0
        "sources": ["neo4j"],         # list of source identifiers
        "related_to": "task performance"  # optional topic name
    }
    """
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON: {e}")
        sys.exit(1)

    # Validate required fields
    for field in ("question", "answer", "category", "confidence"):
        if field not in data:
            print(f"ERROR: Missing required field: {field}")
            sys.exit(1)

    question = data["question"]
    answer = data["answer"]
    category = data.get("category", "world")
    target = data.get("target", "world")
    method = data.get("method", "neo4j_query")
    confidence = float(data["confidence"])
    sources = data.get("sources", [])
    related_to = data.get("related_to", "")

    # Check config
    config = load_config()
    min_conf = config.get("limits", {}).get("minConfidenceToStore", 0.6)

    if confidence < min_conf:
        print(f"SKIPPED: Confidence {confidence} below threshold {min_conf}")
        return

    # Check dedup
    if is_duplicate_question(question, target):
        print(f"SKIPPED: Duplicate question (already asked recently)")
        return

    # Check budget
    stage = get_budget_stage(category)
    if stage == "suspend":
        print(f"SKIPPED: Budget exhausted for category '{category}'")
        return

    # Create ResearchQuestion
    canonical_hash = get_canonical_hash(question, target)
    cycle_id = str(uuid.uuid4())

    record_spend(cycle_id, category, question=question)

    question_id = create_research_question(
        text=question,
        category=category,
        target=target,
        method=method,
        priority=confidence * 10,
        origin="scheduled",
        canonical_hash=canonical_hash,
        reasoning=f"Agent-driven curiosity (confidence={confidence})",
    )

    # Create KnowledgeAnswer
    staleness = "default"
    if related_to:
        # Use topic-based staleness if we recognize the topic type
        topic_staleness_map = {
            "weather": "weather", "forecast": "weather",
            "news": "news", "current events": "news",
            "timezone": "timezone", "time zone": "timezone",
            "performance": "research", "task": "research",
        }
        for keyword, policy in topic_staleness_map.items():
            if keyword in related_to.lower():
                staleness = policy
                break

    answer_id = create_knowledge_answer(
        question_id=question_id,
        answer_text=answer,
        summary=answer[:200],
        confidence=confidence,
        method=method,
        sources=sources,
        staleness_policy=staleness,
    )

    update_question_status(question_id, "RESOLVED", answer[:500])

    # Link to topic
    if related_to:
        topic_label = get_or_create_topic(related_to)
        link_answer_to_topic(answer_id, topic_label)

    # Link to human if target is a human ID
    if target not in ("self", "world", ""):
        link_answer_to_human(answer_id, target)

    complete_spend(cycle_id, "stored")

    print(f"STORED: [{category}] {question[:60]}")
    print(f"  Answer: {answer[:80]}")
    print(f"  Confidence: {confidence}, Topic: {related_to or '(none)'}")
    print(f"  Question ID: {question_id}")


# ---------------------------------------------------------------------------
# --ask-human: Send a curiosity question via Signal DM
# ---------------------------------------------------------------------------

def cmd_ask_human(json_str: str):
    """Send a curiosity question to a human via Signal.

    Expected JSON:
    {
        "human_id": "e5372f96-...",
        "question": "Hey Danny, what timezone are you in?"
    }
    """
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON: {e}")
        sys.exit(1)

    human_id = data.get("human_id", "")
    question_text = data.get("question", "")

    if not human_id or not question_text:
        print("ERROR: human_id and question are required")
        sys.exit(1)

    # Import Signal helpers
    from curiosity_engine import _send_signal_dm, _is_valid_signal_phone
    from pending_question import create_question as create_pending_question
    from consent_decorator import check_consent

    # Look up human
    with neo4j_session() as session:
        result = session.run("""
            MATCH (h:Human {id: $hid})
            OPTIONAL MATCH (h)-[:IDENTIFIED_BY]->(i:Identifier {type: 'SIGNAL_PHONE'})
            RETURN h.displayName AS displayName, i.value AS phone
        """, hid=human_id)
        record = result.single()

    if not record:
        # Try prefix match
        with neo4j_session() as session:
            result = session.run("""
                MATCH (h:Human) WHERE h.id STARTS WITH $prefix
                OPTIONAL MATCH (h)-[:IDENTIFIED_BY]->(i:Identifier {type: 'SIGNAL_PHONE'})
                RETURN h.id AS id, h.displayName AS displayName, i.value AS phone
                LIMIT 1
            """, prefix=human_id)
            record = result.single()
            if record:
                human_id = record["id"]

    if not record:
        print(f"ERROR: Human not found: {human_id}")
        return

    display_name = record["displayName"]
    phone = record["phone"]

    if not display_name:
        print(f"SKIPPED: Human {human_id[:8]} has no displayName")
        return

    if not phone or not _is_valid_signal_phone(phone):
        print(f"SKIPPED: Human {human_id[:8]} has no valid phone ({phone})")
        return

    # Check consent
    if not check_consent(human_id, "general_curiosity"):
        print(f"SKIPPED: Human {human_id[:8]} has not consented to general_curiosity")
        return

    # Create PendingQuestion
    try:
        pq_id = create_pending_question(
            human_id=human_id,
            question=question_text,
            field="general_curiosity",
            qtype="general_curiosity",
            context={"source": "curiosity_sweep"},
            ttl_minutes=60 * 24,
        )
    except Exception as e:
        print(f"SKIPPED: {e}")
        return

    # Send via Signal
    sent = _send_signal_dm(phone, question_text)

    if not sent:
        # Mark as SEND_FAILED
        with neo4j_session() as session:
            session.run("""
                MATCH (pq:PendingQuestion {id: $qid})
                WHERE pq.status = 'PENDING'
                SET pq.status = 'SEND_FAILED', pq.answeredAt = datetime()
            """, qid=pq_id)
        print(f"FAILED: Signal send failed for {display_name}")
        return

    # Create ResearchQuestion node (status: DISPATCHED)
    canonical_hash = get_canonical_hash(question_text, human_id)
    question_id = create_research_question(
        text=question_text,
        category="human",
        target=human_id,
        method="ask_human",
        priority=5.0,
        origin="scheduled",
        canonical_hash=canonical_hash,
        reasoning="Agent asked human via Signal DM",
    )
    update_question_status(question_id, "DISPATCHED")

    # Update lastProactiveAt
    with neo4j_session() as session:
        session.run(
            "MATCH (h:Human {id: $hid}) SET h.lastProactiveAt = datetime()",
            hid=human_id,
        )

    print(f"SENT: Asked {display_name}: {question_text[:60]}")
    print(f"  PendingQuestion: {pq_id}")
    print(f"  ResearchQuestion: {question_id}")


# ---------------------------------------------------------------------------
# --process-answers: Pick up human replies
# ---------------------------------------------------------------------------

def cmd_process_answers():
    """Process answered PendingQuestions and store as knowledge."""
    count = 0
    try:
        with neo4j_session() as session:
            result = session.run("""
                MATCH (pq:PendingQuestion)
                WHERE pq.status = 'ANSWERED'
                  AND pq.type IN ['general_curiosity', 'personal_curiosity', 'profile_curiosity']
                  AND pq.answer IS NOT NULL
                RETURN pq.id AS pqid, pq.question AS question, pq.answer AS answer,
                       pq.humanId AS humanId, pq.field AS field
                LIMIT 10
            """)
            records = list(result)

        for rec in records:
            # Check if already stored
            with neo4j_session() as session:
                existing = session.run("""
                    MATCH (rq:ResearchQuestion {status: 'RESOLVED'})
                    WHERE rq.question_text = $question
                    RETURN rq.question_id AS qid LIMIT 1
                """, question=rec["question"])
                if existing.single():
                    continue

            # Find matching dispatched ResearchQuestion
            rq_id = None
            with neo4j_session() as session:
                rq_result = session.run("""
                    MATCH (rq:ResearchQuestion)
                    WHERE rq.question_text = $question AND rq.status IN ['DISPATCHED', 'QUEUED']
                    RETURN rq.question_id AS qid LIMIT 1
                """, question=rec["question"])
                rq_rec = rq_result.single()
                if rq_rec:
                    rq_id = rq_rec["qid"]

            if not rq_id:
                # Create a new ResearchQuestion for this answered question
                canonical_hash = get_canonical_hash(rec["question"], rec["humanId"])
                rq_id = create_research_question(
                    text=rec["question"],
                    category="human",
                    target=rec["humanId"],
                    method="ask_human",
                    priority=5.0,
                    origin="scheduled",
                    canonical_hash=canonical_hash,
                    reasoning="Retroactive — human answered a curiosity question",
                )

            # Store answer as knowledge
            create_knowledge_answer(
                question_id=rq_id,
                answer_text=rec["answer"],
                summary=rec["answer"][:200],
                confidence=0.85,
                method="ask_human",
                sources=[rec["humanId"]],
                verification="human_confirmed",
                staleness_policy="personal_fact",
            )
            update_question_status(rq_id, "RESOLVED", rec["answer"])
            count += 1
            print(f"  Processed: {rec['question'][:60]} -> {rec['answer'][:40]}")

    except Exception as e:
        logger.error("process_answers failed: %s", e)
        print(f"ERROR: {e}")

    print(f"\nProcessed {count} pending answers")


# ---------------------------------------------------------------------------
# --stats: Budget stats
# ---------------------------------------------------------------------------

def cmd_stats(as_json: bool = False):
    """Print today's curiosity budget stats."""
    stats = get_stats()

    if as_json:
        print(json.dumps(stats, default=str))
        return

    print("=== Curiosity Engine Stats ===\n")
    print(f"  Tokens used:      {stats.get('tokens_used', 0):,} / {stats.get('tokens_budget', 0):,}")
    print(f"  Tokens remaining: {stats.get('tokens_remaining', 0):,}")
    print(f"  Questions today:  {stats.get('questions_generated', 0)}")
    print(f"  DMs sent:         {stats.get('dms_sent', 0)}")
    print(f"  Budget stage:     {stats.get('budget_stage', 'unknown')}")
    print()
    print("  By category:")
    for cat, info in stats.get("by_category", {}).items():
        print(f"    {cat:12s}  used={info.get('used', 0):,}  quota={info.get('quota', 0)}  "
              f"remaining={info.get('remaining', 0)}  stage={info.get('stage', '?')}")
    print()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="General Curiosity Engine — CLI for agent-driven curiosity",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --context                    Show what Kublai knows
  %(prog)s --store '{"question":"...","answer":"...","category":"self","confidence":0.9}'
  %(prog)s --ask-human '{"human_id":"e5372f96","question":"Hey Danny, what timezone?"}'
  %(prog)s --process-answers            Pick up human replies
  %(prog)s --stats                      Today's budget stats
        """,
    )
    parser.add_argument("--context", action="store_true", help="Print curiosity context")
    parser.add_argument("--store", type=str, metavar="JSON", help="Store a question + answer")
    parser.add_argument("--ask-human", type=str, metavar="JSON", help="Send a question to a human via Signal")
    parser.add_argument("--process-answers", action="store_true", help="Process pending human replies")
    parser.add_argument("--stats", action="store_true", help="Show today's budget stats")
    parser.add_argument("--stats-json", action="store_true", help="Stats as JSON (for API)")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    # Suppress noisy Neo4j warnings
    logging.getLogger("neo4j").setLevel(logging.ERROR)

    if args.context:
        cmd_context()
    elif args.store:
        cmd_store(args.store)
    elif args.ask_human:
        cmd_ask_human(args.ask_human)
    elif args.process_answers:
        cmd_process_answers()
    elif args.stats:
        cmd_stats()
    elif args.stats_json:
        cmd_stats(as_json=True)
    else:
        parser.print_help()
