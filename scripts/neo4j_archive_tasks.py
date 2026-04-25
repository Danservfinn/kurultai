#!/usr/bin/env python3
"""Archive old tasks from Neo4j to JSONL cold storage.

Cleans up COMPLETED/FAILED tasks older than retention period,
writing them to JSONL files for cold storage. Also cleans up
orphaned FailureReport nodes.

Usage:
    python3 neo4j_archive_tasks.py --dry-run       # Preview what would be archived
    python3 neo4j_archive_tasks.py --execute        # Archive and delete
    python3 neo4j_archive_tasks.py --execute --days 60   # Custom retention
"""
from __future__ import annotations

import os
import sys
import json
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import get_driver, close_driver

RETENTION_DAYS = 30
BATCH_SIZE = 100
ARCHIVE_DIR = os.path.expanduser("~/.openclaw/archives/tasks")


def _neo4j_to_serializable(obj):
    """Convert Neo4j types to JSON-serializable types."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return {k: _neo4j_to_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_neo4j_to_serializable(v) for v in obj]
    if hasattr(obj, 'iso_format'):
        return obj.iso_format()
    if hasattr(obj, 'to_native'):
        return obj.to_native()
    try:
        # Neo4j integers
        return int(obj)
    except (TypeError, ValueError):
        pass
    return obj


def archive_tasks(driver, retention_days=RETENTION_DAYS, dry_run=True):
    """Archive old COMPLETED/FAILED tasks to JSONL cold storage."""
    print(f"\n=== Task Archival (retention: {retention_days} days) ===")

    with driver.session() as session:
        # Count candidates
        result = session.run("""
            MATCH (t:Task)
            WHERE t.status IN ['COMPLETED', 'FAILED']
              AND t.updated_at < datetime() - duration({days: $days})
            RETURN count(t) AS cnt
        """, days=retention_days)
        count = result.single()['cnt']
        if hasattr(count, '__int__'):
            count = int(count)
        print(f"  Tasks to archive: {count}")

        if dry_run or count == 0:
            if dry_run and count > 0:
                print(f"  [DRY RUN] Would archive {count} tasks")
            return count

        # Ensure archive directory exists
        os.makedirs(ARCHIVE_DIR, exist_ok=True)
        archive_file = os.path.join(ARCHIVE_DIR, f"{datetime.now().strftime('%Y-%m-%d')}.jsonl")

        archived = 0
        while archived < count:
            batch = session.run("""
                MATCH (t:Task)
                WHERE t.status IN ['COMPLETED', 'FAILED']
                  AND t.updated_at < datetime() - duration({days: $days})
                WITH t LIMIT $batch
                OPTIONAL MATCH (t)-[:HAS_OUTPUT]->(o:TaskOutput)
                OPTIONAL MATCH (t)-[:HAS_FAILURE]->(f:FailureReport)
                WITH t, o, collect(f {.*}) AS failures
                WITH t {.*, output: CASE WHEN o IS NOT NULL THEN o {.*} ELSE null END, failures: failures} AS data, t, o
                FOREACH (x IN CASE WHEN o IS NOT NULL THEN [o] ELSE [] END | DETACH DELETE x)
                DETACH DELETE t
                RETURN data AS archived
            """, days=retention_days, batch=BATCH_SIZE)

            records = list(batch)
            if not records:
                break

            with open(archive_file, 'a') as fh:
                for rec in records:
                    task_data = _neo4j_to_serializable(dict(rec['archived']))
                    fh.write(json.dumps(task_data) + '\n')
                    archived += 1

        print(f"  Archived {archived} tasks to {archive_file}")
        return archived


def cleanup_failure_reports(driver, retention_days=RETENTION_DAYS, dry_run=True):
    """Clean up orphaned FailureReport nodes older than retention period."""
    print(f"\n=== FailureReport Cleanup (retention: {retention_days} days) ===")

    with driver.session() as session:
        # Count orphaned FailureReports (no parent Task)
        result = session.run("""
            MATCH (fr:FailureReport)
            WHERE NOT ()-[:HAS_FAILURE]->(fr)
              OR fr.created_at < datetime() - duration({days: $days})
            RETURN count(fr) AS cnt
        """, days=retention_days)
        count = result.single()['cnt']
        if hasattr(count, '__int__'):
            count = int(count)
        print(f"  FailureReports to clean: {count}")

        if not dry_run and count > 0:
            session.run("""
                MATCH (fr:FailureReport)
                WHERE NOT ()-[:HAS_FAILURE]->(fr)
                  OR fr.created_at < datetime() - duration({days: $days})
                DETACH DELETE fr
            """, days=retention_days)
            print(f"  Cleaned {count} FailureReports")
        elif dry_run and count > 0:
            print(f"  [DRY RUN] Would clean {count} FailureReports")

    return count


def main():
    parser = argparse.ArgumentParser(description="Archive old Neo4j tasks to JSONL cold storage")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Preview without changes")
    group.add_argument("--execute", action="store_true", help="Archive and delete")
    parser.add_argument("--days", type=int, default=RETENTION_DAYS,
                        help=f"Retention period in days (default: {RETENTION_DAYS})")
    args = parser.parse_args()

    dry_run = args.dry_run

    driver = get_driver()
    try:
        archive_tasks(driver, retention_days=args.days, dry_run=dry_run)
        cleanup_failure_reports(driver, retention_days=args.days, dry_run=dry_run)
    finally:
        close_driver()


if __name__ == "__main__":
    main()
