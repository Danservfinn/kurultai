#!/usr/bin/env python3
"""
Task Watcher - Immediate Task Execution

Watches agent task directories for new tasks and executes them immediately
(within seconds of creation), without waiting for the next heartbeat cycle.

Usage:
    python3 scripts/task-watcher.py [--poll-interval <seconds>] [--daemon]

Run as daemon:
    nohup python3 scripts/task-watcher.py --daemon > logs/task-watcher.log 2>&1 &
    
Or via launchd (recommended for macOS):
    launchctl load ~/Library/LaunchAgents/com.kurultai.task-watcher.plist
"""

import os
import sys
import time
import subprocess
import signal
import json
from pathlib import Path
from datetime import datetime
from threading import Thread, Event

sys.path.insert(0, str(Path(__file__).parent))
from json_state import locked_json_read, locked_json_update

# Force unbuffered output for launchd (stdout goes to file)
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# Configuration
AGENTS_DIR = Path("/Users/kublai/.openclaw/agents")
STATE_FILE = Path("/Users/kublai/.openclaw/agents/main/logs/task-watcher-state.json")
POLL_INTERVAL_DEFAULT = 15  # seconds
TIMEOUT_DEFAULT = 600  # 10 minutes for Claude Code execution
CLEANUP_INTERVAL = 3600  # Run cleanup every hour
DONE_FILE_MAX_AGE = 48 * 3600  # 48 hours in seconds

# Global state for daemon mode
stop_event = Event()

def load_state():
    """Load previously seen tasks from state file."""
    return locked_json_read(str(STATE_FILE), default={})

def save_state(state):
    """Save current state to file."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with locked_json_update(str(STATE_FILE)) as data:
        data.clear()
        data.update(state)

def list_pending_tasks(agent_dir):
    """List pending tasks for an agent, sorted by priority."""
    tasks_dir = agent_dir / "tasks"
    if not tasks_dir.exists():
        return []
    
    pending = []
    for f in tasks_dir.glob("*.md"):
        # Skip completed/executing tasks
        if any(x in f.name for x in ['.executing', '.completed', '.done']):
            continue
        pending.append(f)
    
    # Sort by priority: high-* > normal-* > low-*
    def priority_key(path):
        name = path.name.lower()
        if name.startswith('high-'):
            return (0, path.stat().st_mtime)
        elif name.startswith('normal-'):
            return (1, path.stat().st_mtime)
        elif name.startswith('low-'):
            return (2, path.stat().st_mtime)
        return (3, path.stat().st_mtime)
    
    return sorted(pending, key=priority_key)

def execute_task(task_file, timeout):
    """Execute a single task file via agent-task-handler.py. Returns (success, output)."""
    # Determine agent from path
    agent = task_file.parent.parent.name

    # agent-task-handler.py handles the full lifecycle:
    # marking as executing, calling the LLM, marking as completed/failed,
    # and updating Neo4j state.
    cmd = [
        "python3",
        str(Path(__file__).parent / "agent-task-handler.py"),
        "--agent", agent,
        "--task-file", str(task_file),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(task_file.parent.parent.parent)
        )

        if result.returncode == 0:
            return True, result.stdout[:1000]
        else:
            return False, result.stderr[:1000] or result.stdout[:1000]

    except subprocess.TimeoutExpired:
        return False, f"Task timed out after {timeout}s"
    except Exception as e:
        return False, f"Execution error: {e}"

def watch_cycle(poll_interval, max_tasks_per_cycle=1):
    """Single watch cycle - check for new tasks and execute immediately."""
    state = load_state()
    tasks_executed = 0
    
    for agent_dir in AGENTS_DIR.iterdir():
        if not agent_dir.is_dir() or agent_dir.name == 'main':
            continue
        
        agent = agent_dir.name
        pending = list_pending_tasks(agent_dir)
        
        # Filter out already-seen tasks, but detect re-queued ones
        # A task is "new" if not in state, or if file was modified after
        # state timestamp (re-queued by queue-audit.py)
        new_tasks = []
        for f in pending:
            key = f"{agent}/{f.name}"
            if key not in state:
                new_tasks.append(f)
            else:
                # Check if file was modified after execution (re-queued)
                try:
                    exec_time = datetime.fromisoformat(state[key]['executed'])
                    file_mtime = datetime.fromtimestamp(f.stat().st_mtime)
                    if file_mtime > exec_time:
                        new_tasks.append(f)
                except (KeyError, ValueError, OSError):
                    pass

        for task_file in new_tasks[:max_tasks_per_cycle]:
            task_key = f"{agent}/{task_file.name}"

            # New task detected - execute immediately
            print(f"[{datetime.now().isoformat()}] NEW TASK: {task_key}")
            success, output = execute_task(task_file, TIMEOUT_DEFAULT)

            status = "✓" if success else "✗"
            print(f"  {status} {task_key}: {'Completed' if success else 'Failed'}")

            # Update state
            state[task_key] = {
                'executed': datetime.now().isoformat(),
                'success': success
            }
            tasks_executed += 1
    
    # Save state
    save_state(state)
    
    return tasks_executed

def cleanup_done_files():
    """Remove .done task files older than 48 hours."""
    now = time.time()
    removed = 0
    for agent_dir in AGENTS_DIR.iterdir():
        if not agent_dir.is_dir() or agent_dir.name == 'main':
            continue
        tasks_dir = agent_dir / "tasks"
        if not tasks_dir.exists():
            continue
        for f in tasks_dir.iterdir():
            if '.done' not in f.name:
                continue
            try:
                age = now - f.stat().st_mtime
                if age > DONE_FILE_MAX_AGE:
                    f.unlink()
                    removed += 1
            except OSError:
                continue
    if removed > 0:
        print(f"[{datetime.now().isoformat()}] Cleaned up {removed} done task file(s)")
    return removed


def daemon_loop(poll_interval):
    """Main daemon loop."""
    print(f"[{datetime.now().isoformat()}] Task Watcher starting (poll interval: {poll_interval}s)")
    print(f"Watching: {AGENTS_DIR}")
    print(f"State file: {STATE_FILE}")
    
    last_cleanup = 0

    while not stop_event.is_set():
        try:
            executed = watch_cycle(poll_interval)
            if executed > 0:
                print(f"[{datetime.now().isoformat()}] Executed {executed} tasks")
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] Error in watch cycle: {e}")

        # Periodic cleanup of old .done files
        if time.time() - last_cleanup > CLEANUP_INTERVAL:
            try:
                cleanup_done_files()
            except Exception as e:
                print(f"[{datetime.now().isoformat()}] Cleanup error: {e}")
            last_cleanup = time.time()
        
        # Sleep in small increments to respond to stop_event quickly
        for _ in range(poll_interval):
            if stop_event.is_set():
                break
            time.sleep(1)
    
    print(f"[{datetime.now().isoformat()}] Task Watcher stopped")

def signal_handler(sig, frame):
    """Handle shutdown signals."""
    print(f"\n[{datetime.now().isoformat()}] Received signal {sig}, shutting down...")
    stop_event.set()

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Watch for new tasks and execute immediately')
    parser.add_argument('--poll-interval', type=int, default=POLL_INTERVAL_DEFAULT, 
                        help=f'Poll interval in seconds (default: {POLL_INTERVAL_DEFAULT})')
    parser.add_argument('--daemon', action='store_true', help='Run as daemon')
    parser.add_argument('--once', action='store_true', help='Run single cycle and exit')
    args = parser.parse_args()
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    if args.once:
        # Single cycle mode (for testing or cron)
        executed = watch_cycle(args.poll_interval)
        print(f"\nExecuted {executed} tasks")
        sys.exit(0 if executed == 0 else 0)
    
    if args.daemon:
        # Daemon mode
        daemon_loop(args.poll_interval)
    else:
        # Interactive mode (same as daemon but with more output)
        daemon_loop(args.poll_interval)

if __name__ == "__main__":
    main()
