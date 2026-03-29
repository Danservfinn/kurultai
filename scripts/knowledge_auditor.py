#!/usr/bin/env python3
"""
Knowledge Auditor — Knowledge quality auditing and topic kill switch
for the General Curiosity Engine.

Weekly cron job that:
  1. Flags stale/tentative knowledge answers
  2. Auto-deletes low-confidence unverified answers older than 30 days
  3. Manages the topic kill switch (suppress/restore topics)
  4. Auto-kills topics that generate many questions but no answers

Usage:
    python3 knowledge_auditor.py                              # Full audit
    python3 knowledge_auditor.py --kill-topic "weather" --reason "testing"
    python3 knowledge_auditor.py --kill-topic "weather" --reason "temp" --days 7
    python3 knowledge_auditor.py --list-killed                # List killed topics
    python3 knowledge_auditor.py --unkill "weather"           # Restore a topic
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import neo4j_session

LOCAL_TZ = ZoneInfo("America/New_York")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def audit_knowledge() -> dict:
    """Main audit function. Returns report dict.

    1. Flag tentative KnowledgeAnswers older than 14 days with
       verification='unverified' -> SET audit_flag = 'stale_tentative'
    2. Flag answers with no sources -> SET audit_flag = 'no_source'
    3. Auto-delete KnowledgeAnswers that are confidence < 0.6,
       verification = 'unverified', and created_at > 30 days ago
    4. Flag answers past their stale_at datetime -> SET audit_flag = 'stale'

    Returns dict with counts for each category plus total_answers.
    """
    now_iso = datetime.now(ZoneInfo("UTC")).isoformat()
    cutoff_14d = (datetime.now(ZoneInfo("UTC")) - timedelta(days=14)).isoformat()
    cutoff_30d = (datetime.now(ZoneInfo("UTC")) - timedelta(days=30)).isoformat()

    report = {
        "stale_tentative": 0,
        "no_source": 0,
        "auto_deleted": 0,
        "stale": 0,
        "total_answers": 0,
    }

    with neo4j_session() as session:
        # Total count
        result = session.run("MATCH (ka:KnowledgeAnswer) RETURN count(ka) AS cnt")
        record = result.single()
        report["total_answers"] = record["cnt"] if record else 0

        # 1. Stale tentative: unverified and older than 14 days
        result = session.run(
            """
            MATCH (ka:KnowledgeAnswer)
            WHERE ka.verification = 'unverified'
              AND ka.created_at < $cutoff
            SET ka.audit_flag = 'stale_tentative'
            RETURN count(ka) AS cnt
            """,
            cutoff=cutoff_14d,
        )
        record = result.single()
        report["stale_tentative"] = record["cnt"] if record else 0

        # 2. No sources
        result = session.run(
            """
            MATCH (ka:KnowledgeAnswer)
            WHERE ka.sources IS NULL
               OR ka.sources = '[]'
               OR ka.sources = ''
            SET ka.audit_flag = 'no_source'
            RETURN count(ka) AS cnt
            """,
        )
        record = result.single()
        report["no_source"] = record["cnt"] if record else 0

        # 3. Auto-delete: low confidence + unverified + older than 30 days
        result = session.run(
            """
            MATCH (ka:KnowledgeAnswer)
            WHERE ka.confidence < 0.6
              AND ka.verification = 'unverified'
              AND ka.created_at < $cutoff
            DETACH DELETE ka
            RETURN count(ka) AS cnt
            """,
            cutoff=cutoff_30d,
        )
        record = result.single()
        report["auto_deleted"] = record["cnt"] if record else 0

        # 4. Stale: past stale_at
        result = session.run(
            """
            MATCH (ka:KnowledgeAnswer)
            WHERE ka.stale_at IS NOT NULL
              AND ka.stale_at < $now
            SET ka.audit_flag = 'stale'
            RETURN count(ka) AS cnt
            """,
            now=now_iso,
        )
        record = result.single()
        report["stale"] = record["cnt"] if record else 0

    logger.info("Audit complete: %s", json.dumps(report))
    return report


# ---------------------------------------------------------------------------
# Topic kill switch
# ---------------------------------------------------------------------------


def kill_topic(topic_label: str, reason: str = "manual", days: int = 0) -> bool:
    """Suppress a topic. days=0 means permanent kill.

    Sets on KnowledgeTopic:
      - status = 'KILLED'
      - kill_reason = reason
      - kill_until = datetime + days (or NULL for permanent)

    Returns True if topic found and killed.
    """
    norm = topic_label.strip().lower()
    now = datetime.now(ZoneInfo("UTC"))
    kill_until = (now + timedelta(days=days)).isoformat() if days > 0 else None

    with neo4j_session() as session:
        result = session.run(
            """
            MATCH (kt:KnowledgeTopic {label: $label})
            SET kt.status = 'KILLED',
                kt.kill_reason = $reason,
                kt.kill_until = $kill_until
            RETURN kt.label AS label
            """,
            label=norm,
            reason=reason,
            kill_until=kill_until,
        )
        record = result.single()

    if record:
        duration = f"{days} days" if days > 0 else "permanent"
        logger.info("Killed topic '%s' (%s, reason=%s)", norm, duration, reason)
        return True
    logger.warning("Topic '%s' not found — cannot kill", norm)
    return False


def unkill_topic(topic_label: str) -> bool:
    """Restore a killed topic to ACTIVE."""
    norm = topic_label.strip().lower()

    with neo4j_session() as session:
        result = session.run(
            """
            MATCH (kt:KnowledgeTopic {label: $label})
            WHERE kt.status = 'KILLED'
            SET kt.status = 'ACTIVE',
                kt.kill_reason = null,
                kt.kill_until = null
            RETURN kt.label AS label
            """,
            label=norm,
        )
        record = result.single()

    if record:
        logger.info("Restored topic '%s' to ACTIVE", norm)
        return True
    logger.warning("Topic '%s' not found or not killed", norm)
    return False


def check_topic_killswitch(topic_label: str) -> bool:
    """Returns True if topic is killed (should NOT be investigated).

    Also checks if kill_until has passed -- if so, auto-restores to ACTIVE.
    """
    norm = topic_label.strip().lower()
    now_iso = datetime.now(ZoneInfo("UTC")).isoformat()

    with neo4j_session() as session:
        result = session.run(
            """
            MATCH (kt:KnowledgeTopic {label: $label})
            RETURN kt.status AS status,
                   kt.kill_until AS kill_until
            """,
            label=norm,
        )
        record = result.single()

    if not record:
        return False  # Topic not found => not killed

    status = record["status"]
    kill_until = record["kill_until"]

    if status != "KILLED":
        return False

    # Check if temporary kill has expired
    if kill_until is not None and kill_until < now_iso:
        unkill_topic(topic_label)
        logger.info("Topic '%s' auto-restored (kill_until expired)", norm)
        return False

    return True


def auto_kill_stale_topics() -> int:
    """Kill topics with 3+ ResearchQuestions in last 7 days but 0 RESOLVED.

    Kills for 30 days with reason='auto_stale'.
    Returns count of killed topics.
    """
    cutoff_7d = (datetime.now(ZoneInfo("UTC")) - timedelta(days=7)).isoformat()
    now = datetime.now(ZoneInfo("UTC"))
    kill_until = (now + timedelta(days=30)).isoformat()

    with neo4j_session() as session:
        result = session.run(
            """
            MATCH (rq:ResearchQuestion)-[:ABOUT_TOPIC]->(kt:KnowledgeTopic)
            WHERE rq.created_at >= $cutoff
              AND kt.status <> 'KILLED'
            WITH kt, collect(rq) AS questions
            WHERE size(questions) >= 3
              AND size([q IN questions WHERE q.status = 'RESOLVED']) = 0
            SET kt.status = 'KILLED',
                kt.kill_reason = 'auto_stale',
                kt.kill_until = $kill_until
            RETURN count(kt) AS cnt
            """,
            cutoff=cutoff_7d,
            kill_until=kill_until,
        )
        record = result.single()
        count = record["cnt"] if record else 0

    if count > 0:
        logger.info("Auto-killed %d stale topics (30-day suppression)", count)
    return count


def get_killed_topics() -> list:
    """List all killed topics with their kill_reason and kill_until."""
    with neo4j_session() as session:
        result = session.run(
            """
            MATCH (kt:KnowledgeTopic)
            WHERE kt.status = 'KILLED'
            RETURN kt.label AS label,
                   kt.display_label AS display_label,
                   kt.kill_reason AS kill_reason,
                   kt.kill_until AS kill_until
            ORDER BY kt.label
            """
        )
        return [dict(record) for record in result]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Knowledge quality auditor and topic kill switch",
    )
    parser.add_argument(
        "--kill-topic",
        metavar="LABEL",
        help="Kill (suppress) a topic by label",
    )
    parser.add_argument(
        "--reason",
        default="manual",
        help="Reason for killing a topic (default: manual)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=0,
        help="Days to kill topic for (0 = permanent, default: 0)",
    )
    parser.add_argument(
        "--unkill",
        metavar="LABEL",
        help="Restore a killed topic to ACTIVE",
    )
    parser.add_argument(
        "--list-killed",
        action="store_true",
        help="List all killed topics",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # --- Kill topic ---
    if args.kill_topic:
        ok = kill_topic(args.kill_topic, reason=args.reason, days=args.days)
        if ok:
            duration = f"{args.days} days" if args.days > 0 else "permanent"
            print(f"Killed topic '{args.kill_topic}' ({duration}, reason={args.reason})")
        else:
            print(f"Topic '{args.kill_topic}' not found")
            sys.exit(1)
        return

    # --- Unkill topic ---
    if args.unkill:
        ok = unkill_topic(args.unkill)
        if ok:
            print(f"Restored topic '{args.unkill}' to ACTIVE")
        else:
            print(f"Topic '{args.unkill}' not found or not killed")
            sys.exit(1)
        return

    # --- List killed ---
    if args.list_killed:
        killed = get_killed_topics()
        if not killed:
            print("No killed topics.")
            return
        print(f"{'Label':<30} {'Reason':<20} {'Kill Until'}")
        print("-" * 80)
        for t in killed:
            label = t.get("display_label") or t.get("label", "?")
            reason = t.get("kill_reason") or "—"
            until = t.get("kill_until") or "permanent"
            print(f"{label:<30} {reason:<20} {until}")
        return

    # --- Full audit (default) ---
    print("Running knowledge audit...")
    report = audit_knowledge()
    print()
    print(f"  Total answers:       {report['total_answers']}")
    print(f"  Stale tentative:     {report['stale_tentative']}  (unverified > 14 days)")
    print(f"  No source:           {report['no_source']}  (missing sources)")
    print(f"  Auto-deleted:        {report['auto_deleted']}  (low confidence + unverified > 30 days)")
    print(f"  Stale:               {report['stale']}  (past stale_at)")
    print()

    print("Running auto-kill on stale topics...")
    killed = auto_kill_stale_topics()
    print(f"  Auto-killed topics:  {killed}  (3+ questions, 0 resolved in 7 days)")
    print()
    print("Audit complete.")


if __name__ == "__main__":
    main()
