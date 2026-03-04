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

# Configuration
AGENTS_DIR = Path("/Users/kublai/.openclaw/agents/main/agent")
STATE_FILE = Path("/Users/kublai/.openclaw/agents/main/logs/task-watcher-state.json")
POLL_INTERVAL_DEFAULT = 15  # seconds
TIMEOUT_DEFAULT = 240  # 4 minutes

# Global state for daemon mode
stop_event = Event()

def load_state():
    """Load previously seen tasks from state file."""
    if not STATE_FILE.exists():
        return {}
    try:
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_state(state):
    """Save current state to file."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

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
    """Execute a single task file. Returns (success, output)."""
    # Mark as executing
    executing_file = task_file.with_suffix(task_file.suffix + '.executing')
    try:
        task_file.rename(executing_file)
    except Exception as e:
        return False, f"Failed to mark task as executing: {e}"
    
    # Determine agent from path
    agent = executing_file.parent.parent.name
    
    # Read task content
    try:
        content = executing_file.read_text()[:2000]
    except Exception as e:
        return False, f"Failed to read task: {e}"
    
    # Execute via OpenClaw spawn
    # This launches a subagent session using the agent's configured model from openclaw.json
    # All Kurultai agents use CLOUD LLMs (bailian/*), NOT local LLMs:
    #   - Kublai: bailian/qwen3.5-plus
    #   - Möngke: bailian/MiniMax-M2.5
    #   - Chagatai: bailian/kimi-k2.5
    #   - Temüjin: bailian/MiniMax-M2.5
    #   - Jochi: bailian/qwen3.5-plus
    #   - Ögedei: bailian/qwen3.5-plus
    # The --agent flag automatically uses the agent's default model configuration.
    cmd = [
        "openclaw",
        "agent",
        "--agent", agent,
        "--message", f"Execute this task immediately: {content}",
        "--thinking", "high"
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(executing_file.parent.parent.parent)
        )
        
        if result.returncode == 0:
            # Mark as completed
            completed_file = executing_file.with_suffix(executing_file.suffix + '.completed.done')
            executing_file.rename(completed_file)
            return True, result.stdout[:1000]
        else:
            # Mark as completed with failure
            completed_file = executing_file.with_suffix(executing_file.suffix + '.completed.done')
            executing_file.rename(completed_file)
            return False, result.stderr[:1000]
            
    except subprocess.TimeoutExpired:
        # Revert to pending on timeout
        try:
            executing_file.rename(task_file)
        except:
            pass
        return False, f"Task timed out after {timeout}s"
    except Exception as e:
        # Revert to pending on error
        try:
            executing_file.rename(task_file)
        except:
            pass
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
        
        for task_file in pending[:max_tasks_per_cycle]:
            task_key = f"{agent}/{task_file.name}"
            
            # Check if this is a genuinely new task (not seen before)
            if task_key in state:
                continue
            
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

def daemon_loop(poll_interval):
    """Main daemon loop."""
    print(f"[{datetime.now().isoformat()}] Task Watcher starting (poll interval: {poll_interval}s)")
    print(f"Watching: {AGENTS_DIR}")
    print(f"State file: {STATE_FILE}")
    
    while not stop_event.is_set():
        try:
            executed = watch_cycle(poll_interval)
            if executed > 0:
                print(f"[{datetime.now().isoformat()}] Executed {executed} tasks")
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] Error in watch cycle: {e}")
        
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
