#!/usr/bin/env python3
"""
Curiosity Scheduler — Periodic sweep for proactive curiosity questions.

For each active human with proactive_engagement consent, checks if Kublai
should ask a question to fill knowledge gaps.

Usage:
    python3 curiosity_scheduler.py             # Run a sweep
    python3 curiosity_scheduler.py --dry-run   # Preview without sending

Schedule: every 4 hours during 9am-9pm (in each human's timezone, or default ET).
"""

import argparse
import logging
import sys
import os
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from curiosity_engine import send_curiosity_question, identify_knowledge_gaps, should_ask_now
from consent_decorator import check_consent
from neo4j_task_tracker import neo4j_session
from pending_question import expire_old_questions

logger = logging.getLogger(__name__)

LOCAL_TZ = ZoneInfo("America/New_York")

# Max proactive questions per sweep (global cap to avoid spam)
MAX_QUESTIONS_PER_SWEEP = 3


def get_active_humans_with_consent(category: str = "proactive_engagement") -> list:
    """Return human IDs that have granted a specific consent category."""
    try:
        with neo4j_session() as session:
            result = session.run(
                """
                MATCH (h:Human {status: 'active'})-[r:HAS_CONSENT]->(c:ConsentCategory {name: $cat})
                WHERE r.revokedAt IS NULL
                RETURN h.id AS id, h.timezone AS tz
                """,
                cat=category,
            )
            return [{"id": r["id"], "timezone": r["tz"]} for r in result]
    except Exception as e:
        logger.error(f"get_active_humans_with_consent failed: {e}")
        return []


def is_waking_hours(tz_str: str = None) -> bool:
    """Check if it's currently between 9am-9pm in the given timezone."""
    try:
        tz = ZoneInfo(tz_str) if tz_str else LOCAL_TZ
    except Exception:
        tz = LOCAL_TZ

    now = datetime.now(tz)
    return 9 <= now.hour < 21


def run_curiosity_sweep(dry_run: bool = False) -> dict:
    """For each active human, check if we should ask a proactive question.

    Args:
        dry_run: If True, only preview — don't actually send questions.

    Returns:
        dict with: humans_checked, questions_sent, gaps_found
    """
    results = {"humans_checked": 0, "questions_sent": 0, "gaps_found": 0}

    # Expire stale questions first
    expired = expire_old_questions()
    if expired:
        logger.info(f"Expired {expired} stale questions")

    humans = get_active_humans_with_consent("proactive_engagement")
    logger.info(f"Found {len(humans)} humans with proactive_engagement consent")

    asked = 0
    for human_info in humans:
        human_id = human_info["id"]
        tz = human_info.get("timezone")

        results["humans_checked"] += 1

        # Skip if outside waking hours for this human
        if not is_waking_hours(tz):
            continue

        # Check gaps (for reporting)
        gaps = identify_knowledge_gaps(human_id)
        results["gaps_found"] += len(gaps)

        if dry_run:
            if gaps and should_ask_now(human_id):
                logger.info(f"[DRY RUN] Would ask {human_id[:8]}: {gaps[0]['field']} — {gaps[0]['question']}")
                asked += 1
        else:
            if send_curiosity_question(human_id):
                asked += 1
                results["questions_sent"] += 1

        if asked >= MAX_QUESTIONS_PER_SWEEP:
            logger.info(f"Hit max questions per sweep ({MAX_QUESTIONS_PER_SWEEP})")
            break

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Curiosity Scheduler")
    parser.add_argument("--dry-run", action="store_true", help="Preview without sending")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    print("Running curiosity sweep...")
    result = run_curiosity_sweep(dry_run=args.dry_run)
    print(f"  Humans checked: {result['humans_checked']}")
    print(f"  Gaps found: {result['gaps_found']}")
    print(f"  Questions sent: {result['questions_sent']}")
