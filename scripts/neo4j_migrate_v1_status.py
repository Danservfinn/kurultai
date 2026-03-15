#!/usr/bin/env python3
"""One-time migration: normalize V1 lowercase statuses to V2 uppercase.

Also cleans up orphaned EXECUTED relationship edges that V1 created
at task creation time (V2 creates them on completion).

Usage:
    python3 neo4j_migrate_v1_status.py --dry-run   # Preview changes
    python3 neo4j_migrate_v1_status.py --execute    # Apply changes
"""

import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import get_driver, close_driver

STATUS_MAP = {
    'ready': 'PENDING',
    'running': 'WORKING',
    'completed': 'COMPLETED',
    'failed': 'FAILED',
    'killed': 'FAILED',
}


def migrate_statuses(driver, dry_run=True):
    """Normalize V1 lowercase statuses to V2 uppercase."""
    print("\n=== Status Normalization ===")
    total_migrated = 0
    with driver.session() as session:
        for old, new in STATUS_MAP.items():
            result = session.run("""
                MATCH (t:Task) WHERE t.status = $old
                RETURN count(t) AS cnt
            """, old=old)
            count = result.single()['cnt']
            print(f"  {old} -> {new}: {count} tasks")
            if not dry_run and count > 0:
                session.run("""
                    MATCH (t:Task) WHERE t.status = $old
                    SET t.status = $new, t.updated_at = datetime()
                """, old=old, new=new)
                print(f"    Migrated {count} tasks")
                total_migrated += count

    if dry_run:
        print(f"\n  [DRY RUN] Would migrate statuses (no changes made)")
    else:
        print(f"\n  Migrated {total_migrated} tasks total")

    return total_migrated


def fix_executed_edges(driver, dry_run=True):
    """Remove orphaned EXECUTED edges on non-completed tasks.

    V1 creates Agent-[:EXECUTED]->Task at task creation (meaning "assigned").
    V2 creates it on completion (meaning "executed").
    This removes V1 artifacts: EXECUTED edges on non-COMPLETED tasks
    that lack a completed_at property.
    """
    print("\n=== EXECUTED Edge Cleanup ===")
    with driver.session() as session:
        result = session.run("""
            MATCH (a:Agent)-[r:EXECUTED]->(t:Task)
            WHERE t.status IN ['PENDING', 'WORKING', 'FAILED']
              AND r.completed_at IS NULL
            RETURN count(r) AS cnt
        """)
        count = result.single()['cnt']
        print(f"  Orphaned EXECUTED edges (V1 creation-time): {count}")

        if not dry_run and count > 0:
            session.run("""
                MATCH (a:Agent)-[r:EXECUTED]->(t:Task)
                WHERE t.status IN ['PENDING', 'WORKING', 'FAILED']
                  AND r.completed_at IS NULL
                DELETE r
            """)
            print(f"    Removed {count} orphaned EXECUTED edges")
        elif dry_run:
            print(f"  [DRY RUN] Would remove {count} orphaned EXECUTED edges")

    return count


def verify_migration(driver):
    """Post-migration verification: no lowercase statuses remain."""
    print("\n=== Verification ===")
    with driver.session() as session:
        result = session.run("""
            MATCH (t:Task) WHERE t.status =~ '[a-z]+'
            RETURN count(t) AS cnt
        """)
        count = result.single()['cnt']
        if count == 0:
            print("  [OK] No lowercase statuses found")
        else:
            print(f"  [WARN] {count} tasks still have lowercase statuses")

        result2 = session.run("""
            MATCH (a:Agent)-[r:EXECUTED]->(t:Task)
            WHERE t.status <> 'COMPLETED' AND r.completed_at IS NULL
            RETURN count(r) AS cnt
        """)
        edge_count = result2.single()['cnt']
        if edge_count == 0:
            print("  [OK] No orphaned EXECUTED edges")
        else:
            print(f"  [WARN] {edge_count} orphaned EXECUTED edges remain")

    return count == 0 and edge_count == 0


def main():
    parser = argparse.ArgumentParser(description="Migrate V1 statuses to V2 uppercase")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Preview changes without applying")
    group.add_argument("--execute", action="store_true", help="Apply migration")
    args = parser.parse_args()

    dry_run = args.dry_run

    driver = get_driver()
    try:
        migrate_statuses(driver, dry_run=dry_run)
        fix_executed_edges(driver, dry_run=dry_run)
        if not dry_run:
            verify_migration(driver)
    finally:
        close_driver()


if __name__ == "__main__":
    main()
