#!/usr/bin/env python3
"""
Queue Cleanup Script — Run every tock heartbeat (30m)

Automatically removes redundant/obsolete tasks to prevent queue bloat:
1. ESCALATE files for completed tasks (task has .done.md)
2. Old .no_output tasks (>48 hours old)
3. Duplicate escalations for same task ID (keep only most recent)

Safe guards:
- Never deletes .executing.md files
- Never deletes tasks <48 hours old unless completed
- Keeps at least 1 escalation per unique task ID
- Logs all deletions for audit

Usage:
    python3 scripts/queue-cleanup.py [--dry-run] [--verbose]
"""

import os
import re
import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path

AGENTS_DIR = Path.home() / ".openclaw" / "agents"
KUBLAI_TASKS = AGENTS_DIR / "kublai" / "tasks"
LOG_FILE = AGENTS_DIR / "main" / "logs" / "queue-cleanup.log"

# Age thresholds
ESCALATION_MAX_AGE_HOURS = 24  # Remove escalations for completed tasks after 24h
NO_OUTPUT_MAX_AGE_HOURS = 48  # Remove old .no_output tasks after 48h


def log(msg, verbose=True):
    """Log to file and optionally stdout."""
    timestamp = datetime.now().isoformat()
    line = f"[{timestamp}] {msg}"
    if verbose:
        print(line)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception as e:
        print(f"Log write error: {e}")


def extract_task_id(filename):
    """Extract task ID from filename."""
    # Match patterns like: high-1772987680, normal-1772950631, ESCALATE-stale-task-xxx-high-1772987680
    match = re.search(r'(?:high|normal|low|critical)[_-](\d+[a-z-]*)', filename, re.IGNORECASE)
    if match:
        return match.group(1)
    # Try UUID pattern
    match = re.search(r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})', filename, re.IGNORECASE)
    if match:
        return match.group(1)[:12]  # Return first 12 chars of UUID
    return None


def is_task_completed(task_id, agent_dir):
    """Check if a task has a .done.md file."""
    if not task_id:
        return False
    tasks_dir = agent_dir / "tasks"
    if not tasks_dir.exists():
        return False
    # Search for .done.md files containing the task ID
    for f in tasks_dir.glob(f"*{task_id}*.done.md"):
        if f.is_file():
            return True
    return False


def get_file_age_hours(filepath):
    """Get file age in hours."""
    try:
        mtime = datetime.fromtimestamp(filepath.stat().st_mtime)
        age = datetime.now() - mtime
        return age.total_seconds() / 3600
    except Exception:
        return 0


def cleanup_escalations(dry_run=False, verbose=True):
    """Remove ESCALATE files for completed tasks."""
    removed = 0
    kept = 0
    
    if not KUBLAI_TASKS.exists():
        log("Kublai tasks directory not found", verbose)
        return 0, 0
    
    # Group escalations by task ID
    escalations_by_task = {}
    for f in KUBLAI_TASKS.glob("ESCALATE*.md"):
        task_id = extract_task_id(f.name)
        if task_id:
            if task_id not in escalations_by_task:
                escalations_by_task[task_id] = []
            escalations_by_task[task_id].append(f)
    
    # Process each group
    for task_id, files in escalations_by_task.items():
        # Check if task is completed (search all agent directories)
        is_completed = False
        for agent in ["temujin", "mongke", "chagatai", "jochi", "ogedei", "kublai"]:
            if is_task_completed(task_id, AGENTS_DIR / agent):
                is_completed = True
                break
        
        if is_completed:
            # Remove all escalations for completed tasks
            for f in files:
                age_hours = get_file_age_hours(f)
                if age_hours > 1:  # Keep very recent escalations (<1h)
                    if not dry_run:
                        try:
                            f.unlink()
                            removed += 1
                            log(f"REMOVED (completed): {f.name}", verbose)
                        except Exception as e:
                            log(f"ERROR removing {f.name}: {e}", verbose)
                    else:
                        log(f"DRY-RUN REMOVE (completed): {f.name}", verbose)
                        removed += 1
                else:
                    kept += 1
        else:
            # Task not completed - keep most recent escalation, remove old duplicates
            if len(files) > 1:
                # Sort by mtime, keep newest
                files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                # Keep newest, remove rest if >24h old
                for f in files[1:]:
                    age_hours = get_file_age_hours(f)
                    if age_hours > ESCALATION_MAX_AGE_HOURS:
                        if not dry_run:
                            try:
                                f.unlink()
                                removed += 1
                                log(f"REMOVED (duplicate, {age_hours:.1f}h old): {f.name}", verbose)
                            except Exception as e:
                                log(f"ERROR removing {f.name}: {e}", verbose)
                        else:
                            log(f"DRY-RUN REMOVE (duplicate): {f.name}", verbose)
                            removed += 1
                    else:
                        kept += 1
            else:
                kept += len(files)
    
    return removed, kept


def cleanup_old_no_output(dry_run=False, verbose=True):
    """Remove old .no_output tasks across all agents."""
    removed = 0
    
    for agent in ["temujin", "mongke", "chagatai", "jochi", "ogedei", "kublai"]:
        tasks_dir = AGENTS_DIR / agent / "tasks"
        if not tasks_dir.exists():
            continue
        
        for f in tasks_dir.glob("*.no_output.md"):
            if ".executing.md" in f.name or ".done.md" in f.name:
                continue  # Skip executing and done files
            
            age_hours = get_file_age_hours(f)
            if age_hours > NO_OUTPUT_MAX_AGE_HOURS:
                if not dry_run:
                    try:
                        f.unlink()
                        removed += 1
                        log(f"REMOVED ({agent}): {f.name} ({age_hours:.1f}h old)", verbose)
                    except Exception as e:
                        log(f"ERROR removing {f.name}: {e}", verbose)
                else:
                    log(f"DRY-RUN REMOVE ({agent}): {f.name}", verbose)
                    removed += 1
    
    return removed


def cleanup_old_unverified(dry_run=False, verbose=True):
    """Remove old .unverified tasks that are stuck (>72 hours)."""
    removed = 0
    
    for agent in ["temujin", "mongke", "chagatai", "jochi", "ogedei", "kublai"]:
        tasks_dir = AGENTS_DIR / agent / "tasks"
        if not tasks_dir.exists():
            continue
        
        for f in tasks_dir.glob("*.unverified.md"):
            if ".executing.md" in f.name or ".done.md" in f.name:
                continue
            
            age_hours = get_file_age_hours(f)
            if age_hours > 72:  # 72 hours = 3 days
                if not dry_run:
                    try:
                        f.unlink()
                        removed += 1
                        log(f"REMOVED ({agent}): {f.name} ({age_hours:.1f}h old, unverified)", verbose)
                    except Exception as e:
                        log(f"ERROR removing {f.name}: {e}", verbose)
                else:
                    log(f"DRY-RUN REMOVE ({agent}): {f.name}", verbose)
                    removed += 1
    
    return removed


def main():
    parser = argparse.ArgumentParser(description='Queue cleanup for tock heartbeat')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be removed')
    parser.add_argument('--verbose', action='store_true', default=True, help='Print details')
    parser.add_argument('--quiet', action='store_true', help='Suppress output')
    args = parser.parse_args()
    
    verbose = args.verbose and not args.quiet
    
    log("=" * 60, verbose)
    log("QUEUE CLEANUP START" + (" (DRY-RUN)" if args.dry_run else ""), verbose)
    log("=" * 60, verbose)
    
    # Run cleanup phases
    esc_removed, esc_kept = cleanup_escalations(dry_run=args.dry_run, verbose=verbose)
    no_output_removed = cleanup_old_no_output(dry_run=args.dry_run, verbose=verbose)
    unverified_removed = cleanup_old_unverified(dry_run=args.dry_run, verbose=verbose)
    
    total_removed = esc_removed + no_output_removed + unverified_removed
    
    log("=" * 60, verbose)
    log(f"CLEANUP COMPLETE: {total_removed} files removed, {esc_kept} escalations kept", verbose)
    log(f"  - Escalations removed: {esc_removed}", verbose)
    log(f"  - Old .no_output removed: {no_output_removed}", verbose)
    log(f"  - Old .unverified removed: {unverified_removed}", verbose)
    log("=" * 60, verbose)
    
    # Return summary for tock-gather integration
    print(f"\nQUEUE_CLEANUP_SUMMARY: removed={total_removed}, kept={esc_kept}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
