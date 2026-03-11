#!/usr/bin/env python3
"""
Session Lock Cleaner — Proactively remove stale session lock files.

This script scans the OpenClaw sessions directories for .jsonl.lock files
and removes them if the holding PID is dead. This prevents the "session file
locked (timeout 10000ms)" errors that occur when a process crashes without
releasing its lock.

The OpenClaw gateway has built-in stale lock detection, but it only triggers
after a 30-minute age threshold OR during lock acquisition retries. This script
provides proactive cleanup to prevent timeouts in the first place.

Usage:
    python3 session-lock-cleaner.py [--dry-run] [--verbose]

Run via cron every 5 minutes:
    */5 * * * * python3 ~/.openclaw/agents/main/scripts/session-lock-cleaner.py
"""

import json
import os
import sys
import argparse
from pathlib import Path
from datetime import datetime

SESSIONS_DIRS = [
    Path.home() / ".openclaw" / "agents" / "main" / "sessions",
    Path.home() / ".openclaw" / "agents" / "temujin" / "sessions",
    Path.home() / ".openclaw" / "agents" / "mongke" / "sessions",
    Path.home() / ".openclaw" / "agents" / "chagatai" / "sessions",
    Path.home() / ".openclaw" / "agents" / "jochi" / "sessions",
    Path.home() / ".openclaw" / "agents" / "ogedei" / "sessions",
    Path.home() / ".openclaw" / "agents" / "tolui" / "sessions",
    Path.home() / ".openclaw" / "agents" / "kublai" / "sessions",
]


def is_pid_alive(pid: int) -> bool:
    """Check if a process with the given PID is still running."""
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False
    except OSError:
        return False


def read_lock_file(lock_path: Path) -> dict | None:
    """Read and parse a lock file. Returns None if unreadable."""
    try:
        with open(lock_path, 'r') as f:
            content = f.read().strip()
            if not content:
                return None
            return json.loads(content)
    except (json.JSONDecodeError, IOError, OSError):
        return None


def get_lock_age_ms(lock_path: Path) -> int | None:
    """Get the age of a lock file in milliseconds based on mtime."""
    try:
        mtime = lock_path.stat().st_mtime
        now = datetime.now().timestamp()
        return int((now - mtime) * 1000)
    except OSError:
        return None


def clean_stale_locks(dry_run: bool = False, verbose: bool = False) -> dict:
    """
    Scan all session directories for stale lock files and remove them.
    
    A lock is considered stale if:
    1. The PID in the lock file is dead, OR
    2. The lock file is older than 30 minutes (1800000ms)
    
    Returns a summary dict with counts.
    """
    summary = {
        'scanned_dirs': 0,
        'locks_found': 0,
        'locks_removed': 0,
        'dead_pid_locks': 0,
        'age_stale_locks': 0,
        'errors': 0,
        'details': []
    }
    
    STALE_AGE_MS = 30 * 60 * 1000  # 30 minutes
    
    for sessions_dir in SESSIONS_DIRS:
        if not sessions_dir.exists():
            continue
        
        summary['scanned_dirs'] += 1
        
        for lock_file in sessions_dir.glob("*.jsonl.lock"):
            summary['locks_found'] += 1
            
            lock_info = {
                'path': str(lock_file),
                'reason': None,
                'removed': False,
                'error': None
            }
            
            # Read lock payload
            payload = read_lock_file(lock_file)
            
            if payload is None:
                # Can't read lock file - remove it
                lock_info['reason'] = 'unreadable'
                if not dry_run:
                    try:
                        lock_file.unlink()
                        lock_info['removed'] = True
                        summary['locks_removed'] += 1
                    except OSError as e:
                        lock_info['error'] = str(e)
                        summary['errors'] += 1
                else:
                    lock_info['removed'] = 'dry-run'
                summary['details'].append(lock_info)
                if verbose:
                    print(f"  [DRY-RUN] Remove unreadable: {lock_file}" if dry_run else f"  [REMOVED] Unreadable: {lock_file}")
                continue
            
            # Check if PID is alive
            pid = payload.get('pid')
            pid_alive = False
            if isinstance(pid, int) and pid > 0:
                pid_alive = is_pid_alive(pid)
            
            if not pid_alive:
                # Dead PID - remove lock
                lock_info['reason'] = f'dead-pid (pid={pid})'
                lock_info['pid'] = pid
                summary['dead_pid_locks'] += 1
                if not dry_run:
                    try:
                        lock_file.unlink()
                        lock_info['removed'] = True
                        summary['locks_removed'] += 1
                    except OSError as e:
                        lock_info['error'] = str(e)
                        summary['errors'] += 1
                else:
                    lock_info['removed'] = 'dry-run'
                summary['details'].append(lock_info)
                if verbose:
                    print(f"  [DRY-RUN] Remove dead PID {pid}: {lock_file}" if dry_run else f"  [REMOVED] Dead PID {pid}: {lock_file}")
                continue
            
            # Check lock age
            age_ms = get_lock_age_ms(lock_file)
            if age_ms is not None and age_ms > STALE_AGE_MS:
                # Too old - remove lock
                lock_info['reason'] = f'age-stale ({age_ms/1000:.0f}s > {STALE_AGE_MS/1000:.0f}s)'
                lock_info['age_ms'] = age_ms
                summary['age_stale_locks'] += 1
                if not dry_run:
                    try:
                        lock_file.unlink()
                        lock_info['removed'] = True
                        summary['locks_removed'] += 1
                    except OSError as e:
                        lock_info['error'] = str(e)
                        summary['errors'] += 1
                else:
                    lock_info['removed'] = 'dry-run'
                summary['details'].append(lock_info)
                if verbose:
                    print(f"  [DRY-RUN] Remove age-stale ({age_ms/1000:.0f}s): {lock_file}" if dry_run else f"  [REMOVED] Age-stale ({age_ms/1000:.0f}s): {lock_file}")
                continue
            
            # Lock is valid - skip
            if verbose:
                print(f"  [SKIP] Valid lock (pid={pid}, age={age_ms/1000:.0f}s): {lock_file}")
    
    return summary


def format_summary(summary: dict) -> str:
    """Format the summary dict as a human-readable string."""
    lines = [
        "Session Lock Cleaner — Summary",
        "=" * 40,
        f"  Directories scanned: {summary['scanned_dirs']}",
        f"  Lock files found:    {summary['locks_found']}",
        f"  Locks removed:       {summary['locks_removed']}",
        f"    - Dead PID:        {summary['dead_pid_locks']}",
        f"    - Age stale:       {summary['age_stale_locks']}",
        f"  Errors:              {summary['errors']}",
    ]
    
    if summary['details']:
        lines.append("")
        lines.append("Details:")
        for detail in summary['details'][:10]:  # Limit to first 10
            status = "REMOVED" if detail['removed'] else "ERROR" if detail['error'] else "SKIP"
            reason = detail['reason'] or detail.get('error', 'unknown')
            lines.append(f"  [{status}] {detail['path']}: {reason}")
        if len(summary['details']) > 10:
            lines.append(f"  ... and {len(summary['details']) - 10} more")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Clean stale session lock files")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be removed without actually removing")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print detailed output")
    parser.add_argument("--json", action="store_true", help="Output summary as JSON")
    args = parser.parse_args()
    
    summary = clean_stale_locks(dry_run=args.dry_run, verbose=args.verbose)
    
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(format_summary(summary))
    
    # Exit with error code if there were errors
    sys.exit(1 if summary['errors'] > 0 else 0)


if __name__ == "__main__":
    main()
