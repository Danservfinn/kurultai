#!/usr/bin/env python3
"""
Stale Lock Cleanup — Proactive session and task lock recovery

Scans for stale lock files in two locations:
1. Agent session directories (.jsonl.lock files)
2. Agent task directories (.pid and .executing.pid files)

A lock is considered stale if:
1. The PID in the lock file is not running
2. The lock file is older than STALE_LOCK_AGE_SECONDS

For task locks, also removes the corresponding .executing.md file.

Run periodically via cron or as part of heartbeat checks.

Usage:
    python3 stale-lock-cleanup.py [--dry-run] [--agent AGENT]
"""

import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

AGENT_SESSIONS_DIR = Path.home() / ".openclaw/agents"
STALE_LOCK_AGE_SECONDS = 300  # 5 minutes

def is_pid_alive(pid):
    """Check if a process with given PID is running."""
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False

def check_lock_stale(lock_path):
    """
    Check if a session lock file (JSON format) is stale.

    Returns: (is_stale, reason)
    """
    try:
        with open(lock_path, 'r') as f:
            lock_data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        return True, f"invalid lock file: {e}"

    pid = lock_data.get('pid')
    created_at = lock_data.get('createdAt')

    reasons = []

    # Check if PID is alive
    if pid and not is_pid_alive(pid):
        reasons.append(f"pid {pid} is dead")

    # Check lock age
    if created_at:
        try:
            # Parse ISO timestamp
            created = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            age = (datetime.now(timezone.utc) - created).total_seconds()
            if age > STALE_LOCK_AGE_SECONDS:
                reasons.append(f"lock is {age:.0f}s old (threshold: {STALE_LOCK_AGE_SECONDS}s)")
        except (ValueError, TypeError):
            reasons.append("invalid createdAt timestamp")

    is_stale = len(reasons) > 0
    return is_stale, ", ".join(reasons) if reasons else "not stale"

def check_task_pid_stale(pid_path):
    """
    Check if a task PID file (plain text format) is stale.

    Task PID files have format:
        Line 1: PID
        Line 2: Unix timestamp

    Returns: (is_stale, reason, pid, timestamp)
    """
    try:
        with open(pid_path, 'r') as f:
            lines = f.read().strip().split('\n')
            pid = int(lines[0].strip())
            timestamp = float(lines[1].strip()) if len(lines) > 1 else None
    except (FileNotFoundError, ValueError, IndexError) as e:
        return True, f"invalid pid file: {e}", None, None

    reasons = []

    # Check if PID is alive
    if not is_pid_alive(pid):
        reasons.append(f"pid {pid} is dead")

    # Check lock age using timestamp
    if timestamp:
        try:
            age = (datetime.now(timezone.utc).timestamp() - timestamp)
            if age > STALE_LOCK_AGE_SECONDS:
                reasons.append(f"lock is {age:.0f}s old (threshold: {STALE_LOCK_AGE_SECONDS}s)")
        except (ValueError, TypeError):
            reasons.append("invalid timestamp")

    is_stale = len(reasons) > 0
    return is_stale, ", ".join(reasons) if reasons else "not stale", pid, timestamp

def cleanup_session_locks(agent_id=None, dry_run=False):
    """
    Scan and clean stale session lock files (.jsonl.lock).

    Returns: dict with counts
    """
    results = {
        'scanned': 0,
        'stale_found': 0,
        'stale_removed': 0,
        'errors': 0,
        'details': []
    }

    # Find all agent directories
    agents = []
    if agent_id:
        agents = [agent_id]
    else:
        agents = [d.name for d in AGENT_SESSIONS_DIR.iterdir()
                  if d.is_dir()]

    for agent in agents:
        sessions_dir = AGENT_SESSIONS_DIR / agent / "sessions"
        if not sessions_dir.exists():
            continue

        for lock_file in sessions_dir.glob("*.lock"):
            results['scanned'] += 1
            is_stale, reason = check_lock_stale(lock_file)

            detail = {
                'file': str(lock_file),
                'agent': agent,
                'type': 'session',
                'stale': is_stale,
                'reason': reason
            }

            if is_stale:
                results['stale_found'] += 1
                detail['action'] = 'removed' if not dry_run else 'would_remove'

                if not dry_run:
                    try:
                        lock_file.unlink()
                        results['stale_removed'] += 1
                    except OSError as e:
                        results['errors'] += 1
                        detail['error'] = str(e)

            results['details'].append(detail)

    return results

def cleanup_task_pid_files(agent_id=None, dry_run=False):
    """
    Scan and clean stale task PID files (.pid, .executing.pid).

    Also removes corresponding .executing.md files when stale.

    Returns: dict with counts
    """
    results = {
        'scanned': 0,
        'stale_found': 0,
        'stale_removed': 0,
        'executing_md_removed': 0,
        'errors': 0,
        'details': []
    }

    # Find all agent directories
    agents = []
    if agent_id:
        agents = [agent_id]
    else:
        agents = [d.name for d in AGENT_SESSIONS_DIR.iterdir()
                  if d.is_dir()]

    for agent in agents:
        tasks_dir = AGENT_SESSIONS_DIR / agent / "tasks"
        if not tasks_dir.exists():
            continue

        # Find all PID files (*.pid and *.executing.pid)
        for pid_file in tasks_dir.glob("*.pid"):
            results['scanned'] += 1
            is_stale, reason, pid, timestamp = check_task_pid_stale(pid_file)

            detail = {
                'file': str(pid_file),
                'agent': agent,
                'type': 'task_pid',
                'pid': pid,
                'stale': is_stale,
                'reason': reason
            }

            if is_stale:
                results['stale_found'] += 1
                detail['action'] = 'removed' if not dry_run else 'would_remove'

                # Find corresponding .executing.md file
                # For *.pid -> base_name.pid
                # For *.executing.pid -> base_name.executing.md
                if pid_file.name.endswith('.executing.pid'):
                    base_name = pid_file.name.replace('.executing.pid', '')
                    executing_md = pid_file.parent / f"{base_name}.executing.md"
                else:
                    # Regular *.pid file -> check for corresponding .executing.md
                    base_name = pid_file.stem
                    executing_md = pid_file.parent / f"{base_name}.executing.md"

                if not dry_run:
                    try:
                        pid_file.unlink()
                        results['stale_removed'] += 1

                        # Also remove .executing.md if it exists
                        if executing_md.exists():
                            executing_md.unlink()
                            results['executing_md_removed'] += 1
                            detail['executing_md_removed'] = str(executing_md)

                    except OSError as e:
                        results['errors'] += 1
                        detail['error'] = str(e)
                else:
                    # Dry run: report what would happen
                    if executing_md.exists():
                        detail['would_also_remove'] = str(executing_md)

            results['details'].append(detail)

    return results

def cleanup_stale_locks(agent_id=None, dry_run=False):
    """
    Scan and clean both session and task stale lock files.

    Returns: dict with combined counts
    """
    session_results = cleanup_session_locks(agent_id, dry_run)
    task_results = cleanup_task_pid_files(agent_id, dry_run)

    # Combine results
    combined = {
        'session': session_results,
        'task': task_results,
        'total': {
            'scanned': session_results['scanned'] + task_results['scanned'],
            'stale_found': session_results['stale_found'] + task_results['stale_found'],
            'stale_removed': session_results['stale_removed'] + task_results['stale_removed'],
            'executing_md_removed': task_results['executing_md_removed'],
            'errors': session_results['errors'] + task_results['errors'],
        }
    }
    combined['all_details'] = session_results['details'] + task_results['details']

    return combined

def main():
    parser = argparse.ArgumentParser(description='Clean stale session and task lock files')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be removed')
    parser.add_argument('--agent', help='Specific agent to check (default: all)')
    parser.add_argument('--json', action='store_true', help='Output as JSON')

    args = parser.parse_args()

    results = cleanup_stale_locks(agent_id=args.agent, dry_run=args.dry_run)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        mode = "[DRY RUN] " if args.dry_run else ""
        print(f"{mode}Stale Lock Cleanup Results")
        print(f"=" * 40)

        # Session locks
        print(f"\nSession Locks (.jsonl.lock):")
        print(f"  Scanned:       {results['session']['scanned']}")
        print(f"  Stale found:   {results['session']['stale_found']}")
        print(f"  Stale removed: {results['session']['stale_removed']}")
        print(f"  Errors:        {results['session']['errors']}")

        # Task PID files
        print(f"\nTask PID Files (*.pid):")
        print(f"  Scanned:           {results['task']['scanned']}")
        print(f"  Stale found:       {results['task']['stale_found']}")
        print(f"  Stale removed:     {results['task']['stale_removed']}")
        print(f"  Executing MD removed: {results['task']['executing_md_removed']}")
        print(f"  Errors:            {results['task']['errors']}")

        # Totals
        print(f"\n{'=' * 40}")
        print(f"TOTAL:")
        print(f"  Scanned:       {results['total']['scanned']}")
        print(f"  Stale found:   {results['total']['stale_found']}")
        print(f"  Stale removed: {results['total']['stale_removed']}")
        print(f"  Errors:        {results['total']['errors']}")

        # Details
        if results['all_details']:
            print(f"\nDetails:")
            for d in results['all_details']:
                status = "STALE" if d['stale'] else "OK"
                type_label = "Session" if d.get('type') == 'session' else "Task"
                print(f"  [{status}] [{type_label}] {d['file']}")
                if d['stale']:
                    print(f"         Reason: {d['reason']}")
                    if 'action' in d:
                        print(f"         Action: {d['action']}")
                    if 'executing_md_removed' in d:
                        print(f"         Also removed: {d['executing_md_removed']}")
                    elif 'would_also_remove' in d:
                        print(f"         Would also remove: {d['would_also_remove']}")

    return 0 if results['total']['errors'] == 0 else 1

if __name__ == "__main__":
    sys.exit(main())

# Appendix: Cron job registration helper
if __name__ == "__main__":
    # This section runs when called with --register-cron
    pass
