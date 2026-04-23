#!/usr/bin/env python3
"""
Stale Lock Cleanup — Proactive session, task, and experiment lock recovery

Scans for stale lock files in four locations:
1. Agent session directories (.jsonl.lock files)
2. Agent task directories (.pid and .executing.pid files)
3. Empty/corrupted task files (*.md that are 0 bytes or missing frontmatter)
4. Experiment locks (/tmp/kurultai-exp-*.lock)

A lock is considered stale if:
1. The PID in the lock file is not running
2. The lock file is older than STALE_LOCK_AGE_SECONDS

Empty task files are cleaned because they cause EXECUTING_NO_OUTPUT escalations:
- task_executor picks up empty .md files
- Creates empty .executing.md and spawns claude-agent
- Agent hangs because source has no content
- Process never completes, triggering throughput anomalies

For task locks, also removes the corresponding .executing.md file.
For experiment locks, includes timeout-based auto-release (2x expected duration).
For empty tasks, also terminates orphaned task_executor processes.

Run periodically via cron or as part of heartbeat checks.

Usage:
    python3 stale-lock-cleanup.py [--dry-run] [--agent AGENT] [--experiment-only]
    python3 stale-lock-cleanup.py --check-experiment AGENT EXPERIMENT_ID  # Pre-flight check
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

AGENT_SESSIONS_DIR = Path.home() / ".openclaw/agents"
STALE_LOCK_AGE_SECONDS = 300  # 5 minutes

# Experiment lock configuration
EXPERIMENT_LOCK_DIR = Path("/tmp")
EXPERIMENT_LOCK_PREFIX = "kurultai-exp-"
EXPERIMENT_LOCK_SUFFIX = ".lock"
# Default expected experiment duration: 30 minutes
# Timeout is 2x expected duration for safety margin
DEFAULT_EXPERIMENT_TIMEOUT_SECONDS = 3600  # 60 minutes

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

def check_experiment_lock_stale(lock_path):
    """
    Check if an experiment lock file is stale.

    Experiment lock format:
    {
        "pid": 12345,
        "agent": "mongke",
        "experiment_id": "exp-20260308-001",
        "createdAt": "2026-03-08T12:00:00Z",
        "expected_duration_seconds": 1800,
        "timeout": 3600
    }

    Returns: (is_stale, reason, lock_data)
    """
    try:
        with open(lock_path, 'r') as f:
            lock_data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        return True, f"invalid lock file: {e}", {}

    reasons = []
    pid = lock_data.get('pid')
    created_at = lock_data.get('createdAt')
    timeout = lock_data.get('timeout', DEFAULT_EXPERIMENT_TIMEOUT_SECONDS)

    # Check if PID is alive
    if pid and not is_pid_alive(pid):
        reasons.append(f"pid {pid} is dead")

    # Check lock age against timeout (not just STALE_LOCK_AGE_SECONDS)
    if created_at:
        try:
            created = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            age = (datetime.now(timezone.utc) - created).total_seconds()
            if age > timeout:
                reasons.append(f"experiment timeout: {age:.0f}s > {timeout}s")
            elif age > STALE_LOCK_AGE_SECONDS:
                reasons.append(f"lock is {age:.0f}s old (threshold: {timeout}s)")
        except (ValueError, TypeError) as e:
            reasons.append(f"invalid createdAt timestamp: {e}")

    is_stale = len(reasons) > 0
    return is_stale, ", ".join(reasons) if reasons else "not stale", lock_data

def check_experiment_lock(agent: str, experiment_id: str) -> dict:
    """
    Pre-flight check: Determine if an experiment lock is valid (process still running).

    Use this BEFORE starting a new experiment to prevent collisions.

    Args:
        agent: Agent name (e.g., "mongke")
        experiment_id: Experiment ID (e.g., "exp-20260308-001")

    Returns:
        {
            "locked": bool,           # True if experiment is locked and running
            "lock_file": str | None,  # Path to lock file if exists
            "stale": bool,            # True if lock exists but is stale
            "pid": int | None,        # PID if lock exists
            "action": str             # "safe_to_start", "wait", "cleaned"
        }
    """
    lock_file = EXPERIMENT_LOCK_DIR / f"{EXPERIMENT_LOCK_PREFIX}{agent}-{experiment_id}{EXPERIMENT_LOCK_SUFFIX}"

    result = {
        "locked": False,
        "lock_file": str(lock_file),
        "stale": False,
        "pid": None,
        "action": "safe_to_start"
    }

    if not lock_file.exists():
        return result

    # Lock exists - check if valid
    is_stale, reason, lock_data = check_experiment_lock_stale(lock_file)

    result["pid"] = lock_data.get("pid")

    if is_stale:
        result["stale"] = True
        result["action"] = "cleaned"
        # Auto-clean stale lock
        try:
            lock_file.unlink()
            result["locked"] = False
        except OSError as e:
            result["action"] = f"error_cleaning: {e}"
            result["locked"] = True  # Assume locked if we can't clean it
    else:
        result["locked"] = True
        result["action"] = "wait"

    return result

def create_experiment_lock(agent: str, experiment_id: str,
                          expected_duration_seconds: int = 1800,
                          timeout_multiplier: float = 2.0) -> dict:
    """
    Create a new experiment lock file.

    Args:
        agent: Agent name
        experiment_id: Experiment ID
        expected_duration_seconds: Expected duration of experiment (default: 30 min)
        timeout_multiplier: Safety multiplier for timeout (default: 2x)

    Returns:
        {
            "success": bool,
            "lock_file": str,
            "pid": int,
            "timeout": int,
            "error": str | None
        }
    """
    import os as os_module
    lock_file = EXPERIMENT_LOCK_DIR / f"{EXPERIMENT_LOCK_PREFIX}{agent}-{experiment_id}{EXPERIMENT_LOCK_SUFFIX}"
    pid = os_module.getpid()
    timeout = int(expected_duration_seconds * timeout_multiplier)

    lock_data = {
        "pid": pid,
        "agent": agent,
        "experiment_id": experiment_id,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "expected_duration_seconds": expected_duration_seconds,
        "timeout": timeout
    }

    result = {
        "success": False,
        "lock_file": str(lock_file),
        "pid": pid,
        "timeout": timeout,
        "error": None
    }

    # Check if lock already exists
    if lock_file.exists():
        check_result = check_experiment_lock(agent, experiment_id)
        if check_result["locked"] and not check_result["stale"]:
            result["error"] = f"Experiment locked by active process pid={check_result['pid']}"
            return result

    try:
        with open(lock_file, 'w') as f:
            json.dump(lock_data, f, indent=2)
        result["success"] = True
    except OSError as e:
        result["error"] = str(e)

    return result

def release_experiment_lock(agent: str, experiment_id: str) -> bool:
    """
    Release an experiment lock file (e.g., on successful completion).

    Args:
        agent: Agent name
        experiment_id: Experiment ID

    Returns:
        True if lock was removed, False if it didn't exist or couldn't be removed
    """
    lock_file = EXPERIMENT_LOCK_DIR / f"{EXPERIMENT_LOCK_PREFIX}{agent}-{experiment_id}{EXPERIMENT_LOCK_SUFFIX}"

    if not lock_file.exists():
        return False

    try:
        lock_file.unlink()
        return True
    except OSError:
        return False

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

def cleanup_empty_task_files(agent_id=None, dry_run=False, min_bytes=50):
    """
    Scan and clean empty/corrupted task files.

    Empty task files cause EXECUTING_NO_OUTPUT escalations because:
    1. task-watcher picks up the empty .md file
    2. Creates .executing.md (also empty) and spawns agent-task-handler
    3. Agent hangs because source file has no content
    4. Process never completes, triggering throughput anomalies

    A task file is considered empty if:
    - File size < min_bytes (default 50, enough for basic frontmatter)
    - Has no frontmatter (doesn't start with '---')
    - Has .executing.md but source .md is missing/empty

    When cleaning empty tasks:
    - Removes the empty .md file
    - Removes corresponding .executing.md if exists
    - Removes corresponding .pid and .executing.pid files
    - Terminates orphaned agent-task-handler processes

    Returns: dict with counts
    """
    results = {
        'scanned': 0,
        'empty_found': 0,
        'empty_removed': 0,
        'processes_killed': 0,
        'errors': 0,
        'details': []
    }

    agents = []
    if agent_id:
        agents = [agent_id]
    else:
        agents = [d.name for d in AGENT_SESSIONS_DIR.iterdir()
                  if d.is_dir() and d.name != 'main']

    for agent in agents:
        tasks_dir = AGENT_SESSIONS_DIR / agent / "tasks"
        if not tasks_dir.exists():
            continue

        for task_file in tasks_dir.glob("*.md"):
            # Skip done files (already completed/failed)
            if '.done.md' in task_file.name:
                continue

            results['scanned'] += 1

            # Check if file is empty or too small
            is_empty = False
            reason = None

            try:
                file_size = task_file.stat().st_size
                if file_size < min_bytes:
                    # Check if it has valid frontmatter
                    try:
                        with open(task_file, 'r') as f:
                            first_line = f.readline()
                            if not first_line.strip().startswith('---'):
                                is_empty = True
                                reason = f"File too small ({file_size} bytes) and missing frontmatter"
                            else:
                                # Has frontmatter but still tiny - might be corrupted
                                if file_size == 0:
                                    is_empty = True
                                    reason = f"Completely empty file (0 bytes)"
                    except Exception:
                        is_empty = True
                        reason = f"Cannot read file (size: {file_size} bytes)"
            except Exception as e:
                results['errors'] += 1
                continue

            # Special case: .executing.md with no corresponding source
            if task_file.name.endswith('.executing.md'):
                # Extract base name to find source
                base_name = task_file.name.replace('.executing.md', '')
                source_file = task_file.parent / f"{base_name}.md"

                if not source_file.exists():
                    is_empty = True
                    reason = "Orphaned .executing.md (source file missing)"

            if not is_empty:
                continue

            # Found an empty/corrupted task - clean it up
            results['empty_found'] += 1

            detail = {
                'file': str(task_file),
                'agent': agent,
                'type': 'empty_task',
                'reason': reason,
                'size': task_file.stat().st_size if task_file.exists() else 0
            }

            if not dry_run:
                try:
                    # Find related files to clean up
                    base_name = task_file.name.replace('.executing.md', '').replace('.md', '')
                    related_files = [task_file]

                    # Find .executing.md
                    executing_md = task_file.parent / f"{base_name}.executing.md"
                    if executing_md.exists() and executing_md != task_file:
                        related_files.append(executing_md)

                    # Find .pid files
                    for pid_file in task_file.parent.glob(f"{base_name}*.pid"):
                        related_files.append(pid_file)

                    # Check for orphaned agent-task-handler processes
                    killed_pids = []
                    for pid_file in task_file.parent.glob(f"{base_name}*.pid"):
                        try:
                            with open(pid_file, 'r') as f:
                                lines = f.read().strip().split('\n')
                                if lines:
                                    pid = int(lines[0].strip())
                                    # Try to kill the process
                                    try:
                                        os.kill(pid, 9)  # SIGKILL
                                        killed_pids.append(pid)
                                        results['processes_killed'] += 1
                                    except (ProcessLookupError, PermissionError):
                                        pass  # Process already dead or can't kill
                        except (ValueError, IndexError, IOError):
                            pass

                    # Remove all related files
                    for f in related_files:
                        if f.exists():
                            f.unlink()

                    results['empty_removed'] += 1
                    detail['action'] = 'removed'
                    detail['files_removed'] = len(related_files)
                    if killed_pids:
                        detail['pids_killed'] = killed_pids

                except OSError as e:
                    results['errors'] += 1
                    detail['error'] = str(e)
            else:
                detail['action'] = 'would_remove'

            results['details'].append(detail)

    return results

def cleanup_experiment_locks(agent_id=None, dry_run=False):
    """
    Scan and clean stale experiment lock files (/tmp/kurultai-exp-*.lock).

    Returns: dict with counts
    """
    results = {
        'scanned': 0,
        'stale_found': 0,
        'stale_removed': 0,
        'errors': 0,
        'details': []
    }

    # Find all experiment lock files
    pattern = f"{EXPERIMENT_LOCK_PREFIX}*{EXPERIMENT_LOCK_SUFFIX}"
    lock_files = list(EXPERIMENT_LOCK_DIR.glob(pattern))

    for lock_file in lock_files:
        # Parse agent and experiment_id from filename
        # Format: kurultai-exp-{agent}-{experiment_id}.lock
        name = lock_file.stem  # Remove .lock suffix
        name = name.replace(EXPERIMENT_LOCK_PREFIX, "")  # Remove prefix

        parts = name.split("-", 1)
        if len(parts) < 2:
            # Invalid filename format
            continue

        lock_agent = parts[0]
        lock_experiment_id = parts[1]

        # Filter by agent if specified
        if agent_id and lock_agent != agent_id:
            continue

        results['scanned'] += 1
        is_stale, reason, lock_data = check_experiment_lock_stale(lock_file)

        detail = {
            'file': str(lock_file),
            'agent': lock_agent,
            'experiment_id': lock_experiment_id,
            'type': 'experiment',
            'stale': is_stale,
            'reason': reason,
            'pid': lock_data.get('pid'),
            'timeout': lock_data.get('timeout', DEFAULT_EXPERIMENT_TIMEOUT_SECONDS)
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

def cleanup_stale_locks(agent_id=None, dry_run=False, experiment_only=False):
    """
    Scan and clean session, task, and experiment stale lock files.

    Args:
        agent_id: Specific agent to check (default: all)
        dry_run: Show what would be removed without actually removing
        experiment_only: Only check experiment locks

    Returns: dict with combined counts
    """
    if experiment_only:
        exp_results = cleanup_experiment_locks(agent_id, dry_run)
        return {
            'experiment': exp_results,
            'total': {
                'scanned': exp_results['scanned'],
                'stale_found': exp_results['stale_found'],
                'stale_removed': exp_results['stale_removed'],
                'errors': exp_results['errors'],
            },
            'all_details': exp_results['details']
        }

    session_results = cleanup_session_locks(agent_id, dry_run)
    task_results = cleanup_task_pid_files(agent_id, dry_run)
    empty_results = cleanup_empty_task_files(agent_id, dry_run)
    exp_results = cleanup_experiment_locks(agent_id, dry_run)

    # Combine results
    combined = {
        'session': session_results,
        'task': task_results,
        'empty_tasks': empty_results,
        'experiment': exp_results,
        'total': {
            'scanned': session_results['scanned'] + task_results['scanned'] + exp_results['scanned'] + empty_results['scanned'],
            'stale_found': session_results['stale_found'] + task_results['stale_found'] + exp_results['stale_found'] + empty_results['empty_found'],
            'stale_removed': session_results['stale_removed'] + task_results['stale_removed'] + exp_results['stale_removed'] + empty_results['empty_removed'],
            'executing_md_removed': task_results['executing_md_removed'],
            'processes_killed': empty_results['processes_killed'],
            'errors': session_results['errors'] + task_results['errors'] + exp_results['errors'] + empty_results['errors'],
        }
    }
    combined['all_details'] = session_results['details'] + task_results['details'] + exp_results['details'] + empty_results['details']

    return combined

def main():
    parser = argparse.ArgumentParser(
        description='Clean stale session, task, and experiment lock files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 stale-lock-cleanup.py                      # Clean all locks
  python3 stale-lock-cleanup.py --dry-run            # Show what would be cleaned
  python3 stale-lock-cleanup.py --agent mongke       # Clean only mongke's locks
  python3 stale-lock-cleanup.py --experiment-only    # Clean only experiment locks
  python3 stale-lock-cleanup.py --check-experiment mongke exp-20260308-001  # Pre-flight check
        """
    )
    parser.add_argument('--dry-run', action='store_true', help='Show what would be removed')
    parser.add_argument('--agent', help='Specific agent to check (default: all)')
    parser.add_argument('--experiment-only', action='store_true', help='Only check experiment locks')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    parser.add_argument('--check-experiment', nargs=2, metavar=('AGENT', 'EXPERIMENT_ID'),
                        help='Pre-flight check: is this experiment locked? Auto-cleans stale locks.')

    args = parser.parse_args()

    # Handle pre-flight experiment check
    if args.check_experiment:
        agent, experiment_id = args.check_experiment
        result = check_experiment_lock(agent, experiment_id)

        if args.json:
            print(json.dumps(result, indent=2))
        else:
            status = "LOCKED" if result['locked'] else "FREE"
            if result['stale']:
                status = "WAS STALE - CLEANED"
            print(f"Experiment Lock Status: {status}")
            print(f"  Agent:         {agent}")
            print(f"  Experiment ID: {experiment_id}")
            print(f"  Lock file:     {result['lock_file']}")
            if result['pid']:
                print(f"  PID:           {result['pid']}")
            print(f"  Action:        {result['action']}")

            # Exit code: 0 if safe to start, 1 if locked
            return 0 if result['action'] in ('safe_to_start', 'cleaned') else 1

    results = cleanup_stale_locks(agent_id=args.agent, dry_run=args.dry_run, experiment_only=args.experiment_only)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        mode = "[DRY RUN] " if args.dry_run else ""
        print(f"{mode}Stale Lock Cleanup Results")
        print(f"=" * 40)

        # Session locks
        if not args.experiment_only:
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

            # Empty task files
            print(f"\nEmpty Task Files (*.md):")
            print(f"  Scanned:           {results['empty_tasks']['scanned']}")
            print(f"  Empty found:       {results['empty_tasks']['empty_found']}")
            print(f"  Empty removed:     {results['empty_tasks']['empty_removed']}")
            print(f"  Processes killed:  {results['empty_tasks']['processes_killed']}")
            print(f"  Errors:            {results['empty_tasks']['errors']}")

        # Experiment locks
        print(f"\nExperiment Locks ({EXPERIMENT_LOCK_PREFIX}*{EXPERIMENT_LOCK_SUFFIX}):")
        print(f"  Scanned:       {results['experiment']['scanned']}")
        print(f"  Stale found:   {results['experiment']['stale_found']}")
        print(f"  Stale removed: {results['experiment']['stale_removed']}")
        print(f"  Errors:        {results['experiment']['errors']}")

        # Totals
        print(f"\n{'=' * 40}")
        print(f"TOTAL:")
        print(f"  Scanned:       {results['total']['scanned']}")
        print(f"  Stale found:   {results['total']['stale_found']}")
        print(f"  Stale removed: {results['total']['stale_removed']}")
        print(f"  Errors:        {results['total']['errors']}")
        if results['total'].get('processes_killed', 0) > 0:
            print(f"  Processes killed: {results['total']['processes_killed']}")

        # Details
        if results['all_details']:
            print(f"\nDetails:")
            for d in results['all_details']:
                status = "STALE" if d.get('stale', d.get('reason')) else "OK"
                type_label = d.get('type', 'unknown')
                if type_label == 'session':
                    type_label = "Session"
                elif type_label == 'task_pid':
                    type_label = "Task"
                elif type_label == 'experiment':
                    type_label = "Experiment"
                elif type_label == 'empty_task':
                    type_label = "EmptyTask"

                print(f"  [{status}] [{type_label}] {d.get('file', 'unknown')}")
                if d.get('stale') or d.get('reason'):
                    reason = d.get('reason', 'stale')
                    print(f"         Reason: {reason}")
                    if 'action' in d:
                        print(f"         Action: {d['action']}")
                    if 'pids_killed' in d:
                        print(f"         PIDs killed: {d['pids_killed']}")
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
