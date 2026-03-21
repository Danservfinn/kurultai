#!/usr/bin/env python3
"""
Neo4j Data Integrity Fixes

Phases:
1. Status Normalization - Normalize all task status values
2. Invalid Task ID Cleanup - Fix or remove invalid task IDs
3. Orphan Handling - Resolve tasks without filesystem files
4. Verification - Confirm all fixes applied correctly

Usage:
    python3 neo4j-fix-data-integrity.py --phase 1    # Normalize statuses
    python3 neo4j-fix-data-integrity.py --phase 2    # Fix invalid task IDs
    python3 neo4j-fix-data-integrity.py --phase 3    # Handle orphans
    python3 neo4j-fix-data-integrity.py --phase 4    # Verify
    python3 neo4j-fix-data-integrity.py --all        # Run all phases
    python3 neo4j-fix-data-integrity.py --dry-run    # Preview changes
"""

import os
import sys
import uuid
import argparse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from neo4j_task_tracker import neo4j_session

# Status mapping for normalization
STATUS_MAP = {
    # verified -> COMPLETED (terminal success state)
    'verified': 'COMPLETED',
    # done -> COMPLETED (terminal success state)
    'done': 'COMPLETED',
    # no_output -> COMPLETED (terminal, just no output)
    'no_output': 'COMPLETED',
    # pending -> PENDING
    'pending': 'PENDING',
    # ready -> PENDING (ready to execute)
    'ready': 'PENDING',
    # executing -> EXECUTING
    'executing': 'EXECUTING',
    # failed -> FAILED
    'failed': 'FAILED',
    # PAUSED -> PENDING (paused tasks are resumable)
    'PAUSED': 'PENDING',
}

VALID_STATUSES = {'PENDING', 'EXECUTING', 'COMPLETED', 'FAILED'}


def normalize_statuses(dry_run=False):
    """Phase 1: Normalize all task status values."""
    print("\n" + "=" * 60)
    print("PHASE 1: STATUS NORMALIZATION")
    print("=" * 60)

    stats = {'total': 0, 'normalized': 0, 'already_valid': 0, 'errors': 0}
    changes = []

    with neo4j_session() as session:
        # Get all tasks with their current status
        result = session.run("""
            MATCH (t:Task)
            RETURN elementId(t) AS eid, t.task_id AS task_id, t.status AS status, t.label AS label
        """)

        for r in result:
            stats['total'] += 1
            current_status = (r['status'] or 'PENDING').strip()
            task_id = r['task_id']
            label = r['label'] or 'unknown'
            eid = r['eid']

            if current_status in VALID_STATUSES:
                stats['already_valid'] += 1
                continue

            # Map to normalized status
            new_status = STATUS_MAP.get(current_status.lower(), 'PENDING')
            changes.append({
                'eid': eid,
                'task_id': task_id,
                'label': label,
                'old_status': current_status,
                'new_status': new_status
            })

    print(f"Total tasks: {stats['total']}")
    print(f"Already valid: {stats['already_valid']}")
    print(f"Need normalization: {len(changes)}")

    if not changes:
        print("No changes needed.")
        return stats

    print("\nChanges to apply:")
    for c in changes[:20]:  # Show first 20
        print(f"  [{c['label']}] '{c['old_status']}' -> '{c['new_status']}'")
    if len(changes) > 20:
        print(f"  ... and {len(changes) - 20} more")

    if dry_run:
        print("\n[DRY RUN] Would apply these changes.")
        return stats

    # Apply changes
    print("\nApplying changes...")
    with neo4j_session() as session:
        for c in changes:
            try:
                session.run("""
                    MATCH (t:Task)
                    WHERE elementId(t) = $eid
                    SET t.status = $new_status,
                        t.updated = datetime(),
                        t.status_normalized = true
                """, eid=c['eid'], new_status=c['new_status'])
                stats['normalized'] += 1
            except Exception as e:
                print(f"  ERROR updating {c['label']}: {e}")
                stats['errors'] += 1

    print(f"\nNormalized: {stats['normalized']}")
    print(f"Errors: {stats['errors']}")
    return stats


def fix_invalid_task_ids(dry_run=False):
    """Phase 2: Fix or remove tasks with invalid task IDs."""
    print("\n" + "=" * 60)
    print("PHASE 2: INVALID TASK ID CLEANUP")
    print("=" * 60)

    stats = {'total_invalid': 0, 'generated': 0, 'removed': 0, 'errors': 0}
    invalid_tasks = []

    with neo4j_session() as session:
        # Find tasks with invalid task_id
        result = session.run("""
            MATCH (t:Task)
            WHERE t.task_id IS NULL
               OR t.task_id = ""
               OR NOT t.task_id =~ "^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$"
            RETURN elementId(t) AS eid, t.task_id AS task_id, t.status AS status,
                   t.label AS label, t.agent AS agent, t.title AS title
        """)

        for r in result:
            stats['total_invalid'] += 1
            invalid_tasks.append({
                'eid': r['eid'],
                'task_id': r['task_id'],
                'status': r['status'],
                'label': r['label'],
                'agent': r['agent'],
                'title': r['title']
            })

    print(f"Found {stats['total_invalid']} tasks with invalid task_id")

    if not invalid_tasks:
        print("No invalid task IDs found.")
        return stats

    print("\nInvalid tasks:")
    for t in invalid_tasks[:20]:
        tid_display = t['task_id'] if t['task_id'] else 'NULL'
        print(f"  [{t['label']}] task_id={tid_display} status={t['status']}")

    if dry_run:
        print("\n[DRY RUN] Would fix these task IDs.")
        return stats

    # Fix each invalid task
    print("\nFixing task IDs...")
    with neo4j_session() as session:
        for t in invalid_tasks:
            try:
                # Check if task is in terminal state (COMPLETED/FAILED)
                if t['status'] in ('COMPLETED', 'FAILED', 'done', 'verified', 'no_output', 'failed'):
                    # For terminal tasks, just generate a UUID if missing
                    new_uuid = str(uuid.uuid4())
                    session.run("""
                        MATCH (t:Task)
                        WHERE elementId(t) = $eid
                        SET t.task_id = $new_uuid,
                            t.updated = datetime(),
                            t.task_id_fixed = true
                    """, eid=t['eid'], new_uuid=new_uuid)
                    stats['generated'] += 1
                    print(f"  Generated UUID for [{t['label']}]: {new_uuid}")
                else:
                    # For non-terminal tasks, generate UUID
                    new_uuid = str(uuid.uuid4())
                    session.run("""
                        MATCH (t:Task)
                        WHERE elementId(t) = $eid
                        SET t.task_id = $new_uuid,
                            t.updated = datetime(),
                            t.task_id_fixed = true
                    """, eid=t['eid'], new_uuid=new_uuid)
                    stats['generated'] += 1
                    print(f"  Generated UUID for [{t['label']}]: {new_uuid}")
            except Exception as e:
                print(f"  ERROR fixing {t['label']}: {e}")
                stats['errors'] += 1

    print(f"\nGenerated UUIDs: {stats['generated']}")
    print(f"Errors: {stats['errors']}")
    return stats


def handle_orphans(dry_run=False):
    """Phase 3: Resolve orphan tasks (in Neo4j but not on filesystem)."""
    print("\n" + "=" * 60)
    print("PHASE 3: ORPHAN HANDLING")
    print("=" * 60)

    from kurultai_paths import AGENTS_DIR
    AGENTS = ["kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei", "tolui"]

    stats = {'total_orphans': 0, 'resolved': 0, 'errors': 0}
    orphans = []

    # Get all task_ids from filesystem
    fs_task_ids = set()
    for agent in AGENTS:
        task_dir = AGENTS_DIR / agent / "tasks"
        if not task_dir.is_dir():
            continue
        for fpath in task_dir.glob("*.md"):
            # Try to extract task_id from frontmatter
            try:
                with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read(1000)
                if 'task_id:' in content.lower():
                    for line in content.split('---')[1].split('\n') if '---' in content[:100] else []:
                        if 'task_id:' in line.lower():
                            tid = line.split(':', 1)[1].strip().strip('"\'')
                            if tid:
                                fs_task_ids.add(tid)
            except:
                pass

    print(f"Found {len(fs_task_ids)} task_ids on filesystem")

    # Find orphans in Neo4j
    with neo4j_session() as session:
        result = session.run("""
            MATCH (t:Task)
            WHERE t.status IN ['PENDING', 'EXECUTING', 'pending', 'executing', 'ready', 'PAUSED']
              AND t.task_id IS NOT NULL
            RETURN t.task_id AS task_id, t.status AS status, t.agent AS agent, t.title AS title
        """)

        for r in result:
            tid = r['task_id']
            if tid and tid not in fs_task_ids:
                orphans.append({
                    'task_id': tid,
                    'status': r['status'],
                    'agent': r['agent'],
                    'title': str(r.get('title', ''))[:60]
                })

    stats['total_orphans'] = len(orphans)
    print(f"Found {stats['total_orphans']} orphan tasks in Neo4j (not on filesystem)")

    if not orphans:
        print("No orphans found.")
        return stats

    print("\nOrphans:")
    for o in orphans[:20]:
        print(f"  [{o['agent']}] {o['task_id']}: {o['status']} - {o['title']}")

    if dry_run:
        print("\n[DRY RUN] Would resolve these orphans as COMPLETED.")
        return stats

    # Resolve orphans
    print("\nResolving orphans...")
    with neo4j_session() as session:
        for o in orphans:
            try:
                session.run("""
                    MATCH (t:Task {task_id: $task_id})
                    SET t.status = 'COMPLETED',
                        t.updated = datetime(),
                        t.completed = CASE WHEN t.completed IS NULL THEN datetime() ELSE t.completed END,
                        t.orphan_resolved = true
                """, task_id=o['task_id'])
                stats['resolved'] += 1
                print(f"  Resolved [{o['agent']}] {o['task_id'][:8]}... as COMPLETED")
            except Exception as e:
                print(f"  ERROR resolving {o['task_id']}: {e}")
                stats['errors'] += 1

    print(f"\nResolved: {stats['resolved']}")
    print(f"Errors: {stats['errors']}")
    return stats


def verify_integrity():
    """Phase 4: Verify data integrity after fixes."""
    print("\n" + "=" * 60)
    print("PHASE 4: VERIFICATION")
    print("=" * 60)

    all_passed = True

    # Check 1: All statuses are valid
    print("\n[CHECK 1] Status values...")
    with neo4j_session() as session:
        result = session.run("""
            MATCH (t:Task)
            RETURN t.status AS status, count(*) AS count
            ORDER BY count DESC
        """)
        invalid_found = False
        for r in result:
            status = r['status']
            count = r['count']
            if status not in VALID_STATUSES:
                print(f"  FAIL: Found invalid status '{status}' ({count} tasks)")
                invalid_found = True
                all_passed = False
            else:
                print(f"  OK: {status}: {count}")
        if not invalid_found:
            print("  All statuses are valid!")

    # Check 2: All task_ids are valid UUIDs
    print("\n[CHECK 2] Task ID format...")
    with neo4j_session() as session:
        result = session.run("""
            MATCH (t:Task)
            WHERE t.task_id IS NULL
               OR t.task_id = ""
               OR NOT t.task_id =~ "^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$"
            RETURN count(*) AS count
        """)
        count = result.single()['count']
        if count == 0:
            print("  OK: All task_ids are valid UUIDs")
        else:
            print(f"  FAIL: {count} tasks still have invalid task_id")
            all_passed = False

    # Check 3: No orphan PENDING/EXECUTING tasks
    print("\n[CHECK 3] Orphan check...")
    with neo4j_session() as session:
        result = session.run("""
            MATCH (t:Task)
            WHERE t.status IN ['PENDING', 'EXECUTING']
            RETURN count(*) AS count
        """)
        count = result.single()['count']
        print(f"  Active (PENDING/EXECUTING) tasks: {count}")
        if count > 20:
            print("  WARNING: More than 20 active tasks may indicate orphans")

    # Summary
    print("\n" + "=" * 60)
    if all_passed:
        print("✓ ALL CHECKS PASSED")
    else:
        print("✗ SOME CHECKS FAILED")
    print("=" * 60)

    return all_passed


def main():
    parser = argparse.ArgumentParser(description='Neo4j Data Integrity Fixes')
    parser.add_argument('--phase', type=int, choices=[1, 2, 3, 4],
                        help='Run specific phase (1-4)')
    parser.add_argument('--all', action='store_true', help='Run all phases')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without applying')
    args = parser.parse_args()

    if not args.phase and not args.all:
        parser.print_help()
        print("\nExample: python3 neo4j-fix-data-integrity.py --all --dry-run")
        return 1

    if args.dry_run:
        print("=" * 60)
        print("DRY RUN MODE - No changes will be made")
        print("=" * 60)

    if args.all or args.phase == 1:
        normalize_statuses(args.dry_run)

    if args.all or args.phase == 2:
        fix_invalid_task_ids(args.dry_run)

    if args.all or args.phase == 3:
        handle_orphans(args.dry_run)

    if args.all or args.phase == 4:
        verify_integrity()

    return 0


if __name__ == '__main__':
    sys.exit(main() or 0)
