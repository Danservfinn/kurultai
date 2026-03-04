#!/usr/bin/env python3
"""
Heartbeat Task Executor

Executes pending agent tasks during heartbeat cycles.
Called by heartbeat-watchdog cron job every 5 minutes.

Usage:
    python3 scripts/heartbeat-task-executor.py [--agent <agent>] [--timeout <seconds>]
"""

import os
import sys
import subprocess
import time
from pathlib import Path
from datetime import datetime

# Configuration
AGENTS_DIR = Path("/Users/kublai/.openclaw/agents/main/agent")
TIMEOUT_DEFAULT = 240  # 4 minutes (heartbeat runs every 5 min)

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
    
    # Read task content to determine agent
    try:
        content = executing_file.read_text()
    except Exception as e:
        return False, f"Failed to read task: {e}"
    
    # Determine agent from path
    agent = executing_file.parent.parent.name
    
    # Execute via OpenClaw spawn
    # This launches a subagent session to execute the task
    cmd = [
        "openclaw",
        "agent",
        "--agent", agent,
        "--message", f"Execute this task: {executing_file.read_text()[:500]}",
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
        executing_file.rename(task_file)
        return False, f"Task timed out after {timeout}s"
    except Exception as e:
        # Revert to pending on error
        try:
            executing_file.rename(task_file)
        except:
            pass
        return False, f"Execution error: {e}"

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Execute pending agent tasks during heartbeat')
    parser.add_argument('--agent', type=str, help='Specific agent to process (default: all)')
    parser.add_argument('--timeout', type=int, default=TIMEOUT_DEFAULT, help=f'Task timeout in seconds (default: {TIMEOUT_DEFAULT})')
    parser.add_argument('--max-tasks', type=int, default=1, help='Max tasks per agent per cycle (default: 1)')
    args = parser.parse_args()
    
    results = []
    tasks_executed = 0
    
    # Get list of agents to process
    if args.agent:
        agents = [args.agent]
    else:
        agents = [d.name for d in AGENTS_DIR.iterdir() if d.is_dir() and d.name != 'main']
    
    for agent in sorted(agents):
        agent_dir = AGENTS_DIR / agent
        if not agent_dir.exists():
            continue
        
        pending = list_pending_tasks(agent_dir)
        if not pending:
            continue
        
        # Execute up to max-tasks per agent
        for task_file in pending[:args.max_tasks]:
            print(f"[{datetime.now().isoformat()}] Executing: {task_file.name}")
            success, output = execute_task(task_file, args.timeout)
            
            status = "✓" if success else "✗"
            print(f"  {status} {task_file.name}: {'Completed' if success else 'Failed'}")
            
            results.append({
                'agent': agent,
                'task': task_file.name,
                'success': success,
                'output': output[:200] if output else None
            })
            tasks_executed += 1
    
    # Summary
    print(f"\n=== TASK EXECUTION SUMMARY ===")
    print(f"Tasks executed: {tasks_executed}")
    print(f"Results: {len([r for r in results if r['success']])} succeeded, {len([r for r in results if not r['success']])} failed")
    
    # Output JSON for cron job consumption
    import json
    print(f"\n=== JSON OUTPUT ===")
    print(json.dumps({
        'tasks_executed': tasks_executed,
        'results': results
    }, indent=2))

if __name__ == "__main__":
    main()
