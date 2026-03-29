#!/usr/bin/env python3
"""
stale-task-archiver.py — Archive stale-resolved and quarantine tasks to prevent hot-potato loops.

Usage:
    python3 scripts/stale-task-archiver.py [--dry-run] [--max-age-hours N] [--log PATH]

Options:
    --dry-run           Show what would be archived without moving
    --max-age-hours N   Archive tasks older than N hours (default: 4)
    --log PATH          Path to log file for archive report (JSONL)

This utility implements recommendation #3 from task normal-1774002689-188154db:
- Auto-archive tasks marked .stale-resolved to prevent them from bouncing
- Archive quarantine tasks that have exceeded max redispatch count
- Run periodically (hourly recommended) via cron

Exit codes:
    0 - Success (tasks archived or nothing to do)
    1 - Error
"""

import os
import sys
import re
import shutil
import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kurultai_paths import AGENTS_DIR

# Archive directory pattern
ARCHIVE_DIR_NAME = "_archive-{date}"

# Task patterns that indicate terminal/stale states needing archival
STALE_PATTERNS = [
    r'\.stale-resolved',           # Stale but resolved - shouldn't be re-dispatched
    r'\.quarantine(?!\.)',         # Quarantined tasks (max redispatch exceeded)
    r'\.archived-hotpotato',       # Already archived hot-potato tasks (cleanup duplicate markers)
]

# Minimum age before archival (prevents archiving freshly created tasks)
DEFAULT_MAX_AGE_HOURS = 4

# Terminal markers that indicate task is done (not just stale)
TERMINAL_DONE_MARKERS = ['.done.md', '.completed.md', '.failed.md']


def get_archive_dir(agent_dir: Path) -> Path:
    """Get or create monthly archive directory for an agent."""
    date_str = datetime.now().strftime("%Y%m")
    archive_dir = agent_dir / "tasks" / f"_archive-{date_str}"
    archive_dir.mkdir(parents=True, exist_ok=True)
    return archive_dir


def get_file_age_hours(file_path: Path) -> float:
    """Get file age in hours from modification time."""
    mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
    age = datetime.now() - mtime
    return age.total_seconds() / 3600


def is_stale_task(filename: str) -> tuple[bool, str]:
    """Check if filename matches a stale pattern.

    Returns (is_stale, reason).
    """
    for pattern in STALE_PATTERNS:
        if re.search(pattern, filename):
            # Extract reason from pattern
            if 'stale-resolved' in pattern:
                return True, "stale-resolved"
            elif 'quarantine' in pattern:
                return True, "quarantine"
            elif 'hotpotato' in pattern:
                return True, "hotpotato"
    return False, ""


def is_terminal_done(filename: str) -> bool:
    """Check if task already has a terminal done marker."""
    return any(marker in filename for marker in TERMINAL_DONE_MARKERS)


def find_stale_tasks(agents_dir: Path, max_age_hours: float) -> list[tuple[Path, str, float]]:
    """Find all stale tasks across all agents.

    Returns list of (file_path, reason, age_hours) tuples.
    """
    stale_tasks = []

    for agent_dir in agents_dir.iterdir():
        if not agent_dir.is_dir():
            continue

        tasks_dir = agent_dir / "tasks"
        if not tasks_dir.exists():
            continue

        for task_file in tasks_dir.iterdir():
            if not task_file.is_file():
                continue
            if task_file.name.startswith('.'):
                continue
            if '_archive-' in str(task_file):
                continue

            is_stale, reason = is_stale_task(task_file.name)
            if is_stale:
                age_hours = get_file_age_hours(task_file)
                if age_hours >= max_age_hours:
                    stale_tasks.append((task_file, reason, age_hours))

    return stale_tasks


def archive_task(task_path: Path, dry_run: bool = False) -> tuple[bool, str]:
    """Archive a task file to the agent's archive directory.

    Returns (success, destination_path or error_message).
    """
    agent_dir = task_path.parent.parent
    archive_dir = get_archive_dir(agent_dir)

    dest_path = archive_dir / task_path.name

    # Handle name collisions
    if dest_path.exists():
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        stem = task_path.stem
        suffix = task_path.suffix
        dest_path = archive_dir / f"{stem}-{timestamp}{suffix}"

    if dry_run:
        return True, str(dest_path)

    try:
        shutil.move(str(task_path), str(dest_path))
        return True, str(dest_path)
    except Exception as e:
        return False, str(e)


def main():
    parser = argparse.ArgumentParser(
        description="Archive stale-resolved and quarantine tasks to prevent hot-potato loops"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be archived without moving")
    parser.add_argument("--max-age-hours", type=float, default=DEFAULT_MAX_AGE_HOURS,
                        help=f"Archive tasks older than N hours (default: {DEFAULT_MAX_AGE_HOURS})")
    parser.add_argument("--log", type=str, default=None,
                        help="Path to log file for archive report (JSONL)")
    args = parser.parse_args()

    log_file = Path(args.log) if args.log else Path("/Users/kublai/.openclaw/logs/stale-archive.jsonl")

    print("=" * 60)
    print("Stale Task Archiver")
    print("=" * 60)
    print()

    # Find stale tasks
    stale_tasks = find_stale_tasks(AGENTS_DIR, args.max_age_hours)

    if not stale_tasks:
        print("No stale tasks found matching criteria.")
        return 0

    print(f"Found {len(stale_tasks)} stale task(s) older than {args.max_age_hours}h:")
    print()

    # Group by reason
    by_reason = {}
    for task_path, reason, age in stale_tasks:
        if reason not in by_reason:
            by_reason[reason] = []
        by_reason[reason].append((task_path, age))

    for reason, tasks in by_reason.items():
        print(f"  {reason}: {len(tasks)} task(s)")
        for task_path, age in tasks[:5]:  # Show first 5
            print(f"    - {task_path.name} ({age:.1f}h old)")
        if len(tasks) > 5:
            print(f"    ... and {len(tasks) - 5} more")
    print()

    if args.dry_run:
        print("DRY RUN MODE - No tasks will be archived")
        print()

    # Archive tasks
    archived = []
    failed = []

    for task_path, reason, age in stale_tasks:
        success, result = archive_task(task_path, args.dry_run)
        if success:
            archived.append({
                "path": str(task_path),
                "reason": reason,
                "age_hours": age,
                "destination": result
            })
            print(f"  {'[DRY-RUN] ' if args.dry_run else ''}Archived: {task_path.name}")
        else:
            failed.append({
                "path": str(task_path),
                "reason": reason,
                "error": result
            })
            print(f"  FAILED: {task_path.name} - {result}")

    # Write log
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "dry_run": args.dry_run,
        "max_age_hours": args.max_age_hours,
        "total_found": len(stale_tasks),
        "archived": archived,
        "failed": failed
    }

    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
        print(f"\nLog written to: {log_file}")
    except Exception as e:
        print(f"\nFailed to write log: {e}")

    print(f"\nTotal: {len(archived)} archived, {len(failed)} failed")

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
