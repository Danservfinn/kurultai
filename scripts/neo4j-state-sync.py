#!/usr/bin/env python3
"""
neo4j-state-sync.py — Reconcile filesystem task state with Neo4j.

================================================================================
SOFT DEPRECATED (2026-03-09) — still invoked by tock-gather.sh for emergency reconciliation
================================================================================
This script is no longer needed as Neo4j is now the SINGLE SOURCE OF TRUTH
for task state. All state transitions happen in Neo4j first, then the
filesystem is updated as a materialized view.

Migration completed: 2026-03-09 (Phase 2 of Kurultai Task System Overhaul)

New architecture:
- Task creation: Neo4j first, filesystem second
- Task discovery: Query Neo4j for PENDING tasks
- State transitions: Atomic CAS in Neo4j, then filesystem update
- Filesystem is a cache/backward-compat layer

Kept for:
- Emergency reconciliation if drift detected
- One-time migration of legacy tasks
- Manual repair operations

Replacement: Use neo4j-backfill-filesystem.py to rebuild filesystem from Neo4j.
================================================================================

Problem: task-watcher.py executes tasks and renames files (.executing, .completed.done,
.failed.done) but NEVER updates Neo4j. This causes Neo4j task nodes to stay at
PENDING/ready forever while the filesystem shows completion.

This script:
1. Scans all agent task directories for files with task_id in frontmatter
2. Derives status from filename suffixes
3. Updates Neo4j to match filesystem (filesystem is source of truth for execution)
4. Backfills tasks that exist only on filesystem (no task_id) into Neo4j

Usage:
    python3 neo4j-state-sync.py             # Dry run (report only)
    python3 neo4j-state-sync.py --apply     # Apply fixes to Neo4j
    python3 neo4j-state-sync.py --verbose   # Show all scanned files

Can be run via cron (e.g., every 30 min with tock) or manually.
"""

import os
import re
import sys
import glob
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from neo4j_task_tracker import neo4j_session
from kurultai_paths import AGENTS_DIR
AGENTS = ["kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei", "tolui"]


def derive_status_from_filename(filename):
    """Derive task status from filesystem filename conventions.

    Conventions used by task-watcher.py and agent-task-handler.py:
    - .completed.done.md / .md.completed.done -> COMPLETED
    - .failed.done.md / .failed.done -> FAILED
    - .executing.md -> EXECUTING
    - .stale.done.md / .obsolete.done.md / .resolved.done.md -> COMPLETED (terminal)
    - .retry-N.* -> check further suffix
    - plain .md (no special suffix) -> PENDING
    """
    name = filename.lower()
    if '.completed.done' in name:
        return 'COMPLETED'
    if '.failed.done' in name:
        return 'FAILED'
    if '.stale' in name and '.done' in name:
        return 'COMPLETED'
    if '.obsolete' in name and '.done' in name:
        return 'COMPLETED'
    if '.resolved' in name and '.done' in name:
        return 'COMPLETED'
    if '.executing' in name:
        return 'EXECUTING'
    if '.done-' in name or '.done.' in name:
        return 'COMPLETED'
    if name.endswith('.done'):
        return 'COMPLETED'
    return 'PENDING'


def extract_frontmatter(filepath):
    """Extract frontmatter fields from a task file."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read(1000)
    except Exception:
        return {}

    if not content.startswith('---'):
        return {}

    parts = content.split('---', 2)
    if len(parts) < 3:
        return {}

    fm = {}
    for line in parts[1].strip().splitlines():
        if ':' in line:
            key, _, value = line.partition(':')
            fm[key.strip()] = value.strip()
    return fm


def extract_title(filepath):
    """Extract title from # Task: heading."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read(2000)
        match = re.search(r'^#\s*Task:\s*(.+)', content, re.MULTILINE)
        return match.group(1).strip() if match else Path(filepath).stem[:60]
    except Exception:
        return Path(filepath).stem[:60]


def scan_filesystem():
    """Scan all agent task directories and return task state info."""
    tasks = []
    for agent in AGENTS:
        task_dir = AGENTS_DIR / agent / "tasks"
        if not task_dir.is_dir():
            continue
        for fpath in task_dir.glob("*.md"):
            if fpath.is_dir():
                continue
            fm = extract_frontmatter(str(fpath))
            file_status = derive_status_from_filename(fpath.name)
            tasks.append({
                'agent': agent,
                'file': fpath.name,
                'path': str(fpath),
                'task_id': fm.get('task_id'),
                'priority': fm.get('priority', 'normal'),
                'source': fm.get('source', 'unknown'),
                'created': fm.get('created', ''),
                'file_status': file_status,
                'title': extract_title(str(fpath)),
            })
        # Also check for .done files without .md extension
        for fpath in task_dir.iterdir():
            if fpath.suffix == '.done' and not fpath.name.endswith('.md'):
                fm = extract_frontmatter(str(fpath))
                file_status = derive_status_from_filename(fpath.name)
                tasks.append({
                    'agent': agent,
                    'file': fpath.name,
                    'path': str(fpath),
                    'task_id': fm.get('task_id'),
                    'priority': fm.get('priority', 'normal'),
                    'source': fm.get('source', 'unknown'),
                    'created': fm.get('created', ''),
                    'file_status': file_status,
                    'title': extract_title(str(fpath)),
                })
    return tasks


def get_neo4j_tasks():
    """Get all tasks from Neo4j indexed by task_id."""
    neo4j_tasks = {}
    with neo4j_session() as session:
        result = session.run("""
            MATCH (t:Task)
            WHERE t.task_id IS NOT NULL
            RETURN t.task_id AS task_id, t.status AS status,
                   t.agent AS agent, t.label AS label
        """)
        for r in result:
            neo4j_tasks[r['task_id']] = {
                'status': r['status'],
                'agent': r['agent'],
                'label': r['label'],
            }
    return neo4j_tasks


def sync(apply=False, verbose=False):
    """Main sync logic. Returns summary dict."""
    fs_tasks = scan_filesystem()
    neo4j_tasks = get_neo4j_tasks()

    stats = {
        'scanned': len(fs_tasks),
        'with_task_id': 0,
        'neo4j_matched': 0,
        'status_drift': 0,
        'updated': 0,
        'missing_from_neo4j': 0,
        'backfilled': 0,
        'no_task_id': 0,
        'errors': 0,
    }

    drifted = []

    for task in fs_tasks:
        tid = task['task_id']

        if not tid:
            stats['no_task_id'] += 1
            if verbose:
                print(f"  [skip] {task['agent']}/{task['file']} — no task_id")
            continue

        stats['with_task_id'] += 1
        neo_entry = neo4j_tasks.get(tid)

        if not neo_entry:
            stats['missing_from_neo4j'] += 1
            if verbose:
                print(f"  [missing] {task['agent']}/{task['file']} task_id={tid} not in Neo4j")
            if apply:
                try:
                    with neo4j_session() as session:
                        session.run("""
                            MERGE (a:Agent {name: $agent})
                            CREATE (t:Task {
                                task_id: $task_id,
                                label: $label,
                                agent: $agent,
                                title: $title,
                                priority: $priority,
                                source: $source,
                                status: $status,
                                created: datetime($created),
                                updated: datetime(),
                                synced_from_fs: true,
                                retry_count: 0,
                                max_retries: 3
                            })
                            CREATE (a)-[:EXECUTED]->(t)
                        """, task_id=tid, label=f"{task['agent']}-{tid}",
                            agent=task['agent'], title=task['title'],
                            priority=task['priority'], source=task['source'],
                            status=task['file_status'],
                            created=task['created'] or datetime.now().isoformat())
                        # Set completed timestamp for terminal states
                        if task['file_status'] in ('COMPLETED', 'FAILED'):
                            session.run("""
                                MATCH (t:Task {task_id: $task_id})
                                SET t.completed = datetime()
                            """, task_id=tid)
                    stats['backfilled'] += 1
                    print(f"  [BACKFILL] {task['agent']}/{task['file']} -> {task['file_status']}")
                except Exception as e:
                    stats['errors'] += 1
                    print(f"  [BACKFILL-ERR] {task['agent']}/{task['file']}: {e}")
            continue

        stats['neo4j_matched'] += 1

        # Check for status drift
        # Normalize Neo4j status for comparison
        neo_status = (neo_entry['status'] or 'PENDING').upper()
        fs_status = task['file_status']

        if neo_status == fs_status:
            if verbose:
                print(f"  [ok] {task['agent']}/{task['file']} — {fs_status}")
            continue

        stats['status_drift'] += 1
        drifted.append({
            'task_id': tid,
            'agent': task['agent'],
            'file': task['file'],
            'neo4j_status': neo_status,
            'fs_status': fs_status,
        })

        print(f"  [DRIFT] {task['agent']}/{task['file']}: Neo4j={neo_status} FS={fs_status}")

        if apply:
            try:
                with neo4j_session() as session:
                    session.run("""
                        MATCH (t:Task {task_id: $task_id})
                        SET t.status = $new_status,
                            t.updated = datetime(),
                            t.synced_from_fs = true
                    """, task_id=tid, new_status=fs_status)
                    # Set completed timestamp for terminal states
                    if fs_status in ('COMPLETED', 'FAILED'):
                        session.run("""
                            MATCH (t:Task {task_id: $task_id})
                            SET t.completed = CASE WHEN t.completed IS NULL
                                THEN datetime() ELSE t.completed END
                        """, task_id=tid)
                stats['updated'] += 1
                print(f"    -> Updated to {fs_status}")
            except Exception as e:
                stats['errors'] += 1
                print(f"    -> ERROR: {e}")

    # --- Reverse sync: find Neo4j PENDING/EXECUTING tasks with no filesystem file ---
    # These are "orphans" — tasks whose files were deleted/archived but Neo4j wasn't updated.
    orphan_stats = {'found': 0, 'resolved': 0, 'errors': 0}

    # Build set of all task_ids found on filesystem
    fs_task_ids = {t['task_id'] for t in fs_tasks if t['task_id']}

    # Query Neo4j for non-terminal tasks
    with neo4j_session() as session:
        result = session.run("""
            MATCH (t:Task)
            WHERE t.status IN ['PENDING', 'EXECUTING', 'FAILED', 'pending', 'executing', 'ready', 'failed']
              AND t.task_id IS NOT NULL
            RETURN t.task_id AS task_id, t.status AS status,
                   t.agent AS agent, t.title AS title
        """)
        orphans = []
        for r in result:
            tid = r['task_id']
            if tid not in fs_task_ids:
                # Double-check: look for any file matching this task_id on disk
                agent = r['agent'] or 'unknown'
                task_dir = AGENTS_DIR / agent / "tasks"
                found_on_disk = False
                if task_dir.is_dir():
                    for fpath in task_dir.iterdir():
                        if tid in fpath.name:
                            found_on_disk = True
                            break
                    if not found_on_disk:
                        # Also check frontmatter of remaining files
                        for fpath in task_dir.glob("*.md"):
                            fm = extract_frontmatter(str(fpath))
                            if fm.get('task_id') == tid:
                                found_on_disk = True
                                break
                if not found_on_disk:
                    orphans.append({
                        'task_id': tid,
                        'agent': agent,
                        'status': r['status'],
                        'title': str(r.get('title', ''))[:60],
                    })

    orphan_stats['found'] = len(orphans)

    for orph in orphans:
        print(f"  [ORPHAN] {orph['agent']}/{orph['task_id']}: Neo4j={orph['status']} — no file on disk — {orph['title']}")
        if apply:
            try:
                # Preserve FAILED status for failed orphans; resolve others as COMPLETED
                resolved_status = 'FAILED' if orph['status'].upper() == 'FAILED' else 'COMPLETED'
                with neo4j_session() as session:
                    session.run("""
                        MATCH (t:Task {task_id: $task_id})
                        SET t.status = $resolved_status,
                            t.updated = datetime(),
                            t.completed = CASE WHEN t.completed IS NULL THEN datetime() ELSE t.completed END,
                            t.synced_from_fs = true,
                            t.orphan_resolved = true
                    """, task_id=orph['task_id'], resolved_status=resolved_status)
                orphan_stats['resolved'] += 1
                print(f"    -> Resolved as {resolved_status} (orphan)")
            except Exception as e:
                orphan_stats['errors'] += 1
                print(f"    -> ERROR: {e}")

    # Summary
    print(f"\n{'='*50}")
    print(f"Neo4j State Sync {'(DRY RUN)' if not apply else '(APPLIED)'}")
    print(f"{'='*50}")
    print(f"  Files scanned:      {stats['scanned']}")
    print(f"  With task_id:       {stats['with_task_id']}")
    print(f"  Matched in Neo4j:   {stats['neo4j_matched']}")
    print(f"  Status drift:       {stats['status_drift']}")
    if apply:
        print(f"  Updated:            {stats['updated']}")
        print(f"  Backfilled:         {stats['backfilled']}")
        print(f"  Errors:             {stats['errors']}")
    print(f"  No task_id:         {stats['no_task_id']}")
    print(f"  Missing from Neo4j: {stats['missing_from_neo4j']}")
    print(f"  Neo4j orphans:      {orphan_stats['found']}")
    if apply and orphan_stats['found'] > 0:
        print(f"  Orphans resolved:   {orphan_stats['resolved']}")
        print(f"  Orphan errors:      {orphan_stats['errors']}")

    fixable = stats['status_drift'] + stats['missing_from_neo4j'] + orphan_stats['found']
    if fixable > 0 and not apply:
        print(f"\nRun with --apply to fix {stats['status_drift']} drifted + {stats['missing_from_neo4j']} missing + {orphan_stats['found']} orphan tasks.")

    return stats


if __name__ == '__main__':
    apply = '--apply' in sys.argv
    verbose = '--verbose' in sys.argv
    sync(apply=apply, verbose=verbose)
