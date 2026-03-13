#!/usr/bin/env python3
"""
Clear Stale Task Claims — Fix for PENDING_NO_DISPATCH

When tasks are claimed but the handler crashes or times out, the session_key
remains set in Neo4j. This causes PENDING tasks to be rejected with
"already_claimed" even though no handler is running.

This script clears session_keys for PENDING tasks with stale claims (>10 min old),
allowing them to be re-dispatched.

Usage:
    python3 scripts/clear_stale_claims.py [--dry-run]
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).parent))
from neo4j_task_tracker import get_driver


def clear_stale_claims(dry_run: bool = False, age_minutes: int = 10) -> dict:
    """Clear stale session_keys from PENDING and FAILED tasks.

    Args:
        dry_run: If True, report what would be done without making changes
        age_minutes: Only clear claims older than this many minutes (ignored for FAILED tasks)

    Returns:
        dict with statistics about what was cleared
    """
    driver = get_driver()
    if not driver:
        return {"error": "Neo4j driver unavailable"}

    stats = {
        "cleared": 0,
        "skipped": 0,
        "failed": 0,
        "started_cleared": 0,
        "failed_cleared": 0,
        "tasks": []
    }

    with driver.session() as session:
        # Find PENDING tasks with stale session_keys
        stuck = session.run("""
            MATCH (t:Task)
            WHERE t.status = 'PENDING'
            AND t.session_key IS NOT NULL
            AND t.session_key <> ''
            AND t.started < datetime() - duration('PT' + $age_minutes + 'M')
            RETURN t.task_id as task_id, t.agent as agent, t.session_key as session_key,
                   t.started as started, t.title as title
            ORDER BY t.started DESC
        """, age_minutes=age_minutes)

        tasks_to_clear = list(stuck)

        for task in tasks_to_clear:
            task_id = task["task_id"]
            agent = task["agent"]
            session_key = task["session_key"]
            started = task["started"]

            if dry_run:
                stats["skipped"] += 1
                stats["tasks"].append({
                    "task_id": task_id,
                    "agent": agent,
                    "action": "would_clear"
                })
                print(f"[DRY RUN] Would clear: {agent}/{task_id} (session={session_key[:20]}... started={started})")
                continue

            # Clear the session_key
            result = session.run("""
                MATCH (t:Task {task_id: $task_id})
                SET t.session_key = null,
                    t.started = null,
                    t.claimed_by = null,
                    t.updated = datetime()
                RETURN count(t) as updated
            """, task_id=task_id)

            if result.single()["updated"] > 0:
                stats["cleared"] += 1
                stats["tasks"].append({
                    "task_id": task_id,
                    "agent": agent,
                    "action": "cleared"
                })
                print(f"Cleared: {agent}/{task_id}")
            else:
                stats["failed"] += 1
                print(f"Failed to clear: {agent}/{task_id}")

        # ALSO clear stale started timestamps for PENDING tasks with NULL session_key
        # This happens when a claim fails partway through
        stale_started = session.run("""
            MATCH (t:Task)
            WHERE t.status = 'PENDING'
            AND (t.session_key IS NULL OR t.session_key = '')
            AND t.started IS NOT NULL
            AND t.started < datetime() - duration('PT' + $age_minutes + 'M')
            RETURN t.task_id as task_id, t.agent as agent, t.started as started
        """, age_minutes=age_minutes)

        for task in stale_started:
            task_id = task["task_id"]
            agent = task["agent"]
            started = task["started"]

            if dry_run:
                print(f"[DRY RUN] Would clear started: {agent}/{task_id} (started={started})")
                continue

            result = session.run("""
                MATCH (t:Task {task_id: $task_id})
                SET t.started = null,
                    t.updated = datetime()
                RETURN count(t) as updated
            """, task_id=task_id)

            if result.single()["updated"] > 0:
                stats["started_cleared"] += 1
                print(f"Cleared started timestamp: {agent}/{task_id}")

        # ALSO clear session_keys from FAILED tasks (regardless of age - they're done)
        # FAILED tasks with stale claims block new task dispatch
        failed_stuck = session.run("""
            MATCH (t:Task)
            WHERE t.status = 'FAILED'
            AND t.session_key IS NOT NULL
            AND t.session_key <> ''
            RETURN t.task_id as task_id, t.agent as agent, t.session_key as session_key
        """)

        for task in failed_stuck:
            task_id = task["task_id"]
            agent = task["agent"]
            session_key = task["session_key"]

            if dry_run:
                stats["skipped"] += 1
                print(f"[DRY RUN] Would clear FAILED task claim: {agent}/{task_id}")
                continue

            result = session.run("""
                MATCH (t:Task {task_id: $task_id})
                SET t.session_key = null,
                    t.started = null,
                    t.claimed_by = null,
                    t.updated = datetime()
                RETURN count(t) as updated
            """, task_id=task_id)

            if result.single()["updated"] > 0:
                stats["failed_cleared"] += 1
                print(f"Cleared FAILED task claim: {agent}/{task_id}")

    return stats


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Clear stale task claims")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    parser.add_argument("--age-minutes", type=int, default=10, help="Age threshold in minutes (default: 10)")
    args = parser.parse_args()

    print(f"Clearing stale claims older than {args.age_minutes} minutes...")
    if args.dry_run:
        print("DRY RUN MODE - no changes will be made")

    stats = clear_stale_claims(dry_run=args.dry_run, age_minutes=args.age_minutes)

    if stats.get("error"):
        print(f"Error: {stats['error']}")
        sys.exit(1)

    print(f"\nResults: cleared={stats['cleared']} skipped={stats['skipped']} failed={stats['failed']} failed_cleared={stats['failed_cleared']} started_cleared={stats['started_cleared']}")


if __name__ == "__main__":
    main()
