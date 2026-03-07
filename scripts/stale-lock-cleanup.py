#!/usr/bin/env python3
"""
Stale Lock Cleanup — Proactive session lock file recovery

Scans agent session directories for stale lock files and removes them.
A lock is considered stale if:
1. The PID in the lock file is not running
2. The lock file is older than STALE_LOCK_AGE_SECONDS

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
    Check if a lock file is stale.
    
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

def cleanup_stale_locks(agent_id=None, dry_run=False):
    """
    Scan and clean stale lock files.
    
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

def main():
    parser = argparse.ArgumentParser(description='Clean stale session lock files')
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
        print(f"Scanned:       {results['scanned']}")
        print(f"Stale found:   {results['stale_found']}")
        print(f"Stale removed: {results['stale_removed']}")
        print(f"Errors:        {results['errors']}")
        
        if results['details']:
            print(f"\nDetails:")
            for d in results['details']:
                status = "STALE" if d['stale'] else "OK"
                print(f"  [{status}] {d['file']}")
                if d['stale']:
                    print(f"         Reason: {d['reason']}")
                    if 'action' in d:
                        print(f"         Action: {d['action']}")
    
    return 0 if results['errors'] == 0 else 1

if __name__ == "__main__":
    sys.exit(main())

# Appendix: Cron job registration helper
if __name__ == "__main__":
    # This section runs when called with --register-cron
    pass
