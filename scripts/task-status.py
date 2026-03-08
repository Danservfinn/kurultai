#!/usr/bin/env python3
"""
Task Status - Query executing tasks and correlate with claude-agent processes

Usage:
    python3 scripts/task-status.py [--active] [--all] [--json] [--agent <name>]

Examples:
    python3 scripts/task-status.py --active    # Show only currently executing tasks
    python3 scripts/task-status.py --all       # Show all tasks (pending + executing + done)
    python3 scripts/task-status.py --json      # Output as JSON
    python3 scripts/task-status.py --agent temujin  # Filter by agent
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

AGENTS_DIR = Path.home() / ".openclaw" / "agents"
VALID_AGENTS = {"temujin", "mongke", "chagatai", "jochi", "ogedei", "kublai"}


def is_pid_alive(pid):
    """Check if a process PID is alive."""
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def extract_task_id(content):
    """Extract task_id from task file frontmatter."""
    match = re.search(r'^task_id:\s*(\S+)', content, re.MULTILINE)
    return match.group(1) if match else None


def extract_skill_hint(content):
    """Extract skill_hint from task file frontmatter."""
    match = re.search(r'^skill_hint:\s*(\S+)', content, re.MULTILINE)
    return match.group(1) if match else None


def extract_priority(filename):
    """Extract priority from filename."""
    name = filename.lower()
    if name.startswith('critical-'):
        return 'critical'
    elif name.startswith('high-'):
        return 'high'
    elif name.startswith('normal-'):
        return 'normal'
    elif name.startswith('low-'):
        return 'low'
    return 'unknown'


def read_pid_file(pid_path):
    """Read PID and start timestamp from .executing.pid file."""
    try:
        content = pid_path.read_text().strip()
        lines = content.split('\n', 1)
        pid = int(lines[0])
        start_ts = float(lines[1]) if len(lines) > 1 else None
        return pid, start_ts
    except (ValueError, IndexError, FileNotFoundError):
        return None, None


def get_claude_agent_processes():
    """Get all claude-agent processes with their PIDs and parent PIDs."""
    try:
        result = subprocess.run(
            ['ps', '-eo', 'pid,ppid,command'],
            capture_output=True, text=True
        )
        processes = []
        for line in result.stdout.strip().split('\n')[1:]:  # Skip header
            parts = line.split(None, 2)
            if len(parts) >= 3 and 'claude-agent' in parts[2]:
                processes.append({
                    'pid': int(parts[0]),
                    'ppid': int(parts[1]),
                    'command': parts[2]
                })
        return processes
    except Exception:
        return []


def scan_agent_tasks(agent, status_filter=None):
    """Scan an agent's task directory for tasks."""
    tasks_dir = AGENTS_DIR / agent / "tasks"
    if not tasks_dir.exists():
        return []

    tasks = []
    for f in tasks_dir.iterdir():
        if not f.is_file() or not f.name.endswith('.md'):
            continue

        # Filter by status
        is_executing = '.executing.md' in f.name and '.done' not in f.name
        is_done = '.done.md' in f.name
        is_pending = not is_executing and not is_done

        if status_filter == 'executing' and not is_executing:
            continue
        if status_filter == 'done' and not is_done:
            continue
        if status_filter == 'pending' and not is_pending:
            continue

        # Read task metadata
        try:
            content = f.read_text()[:2000]
        except Exception:
            content = ""

        task_info = {
            'agent': agent,
            'file': f.name,
            'path': str(f),
            'status': 'executing' if is_executing else ('done' if is_done else 'pending'),
            'priority': extract_priority(f.name),
            'task_id': extract_task_id(content),
            'skill_hint': extract_skill_hint(content),
            'pid': None,
            'pid_alive': None,
            'age_seconds': None,
        }

        # For executing tasks, check PID
        if is_executing:
            pid_file = f.parent / f.name.replace('.executing.md', '.executing.pid')
            if pid_file.exists():
                pid, start_ts = read_pid_file(pid_file)
                task_info['pid'] = pid
                task_info['pid_alive'] = is_pid_alive(pid) if pid else False
                if start_ts:
                    task_info['age_seconds'] = int(datetime.now().timestamp() - start_ts)

        tasks.append(task_info)

    return tasks


def main():
    parser = argparse.ArgumentParser(description='Query task execution status')
    parser.add_argument('--active', action='store_true', help='Show only executing tasks')
    parser.add_argument('--all', action='store_true', help='Show all tasks')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    parser.add_argument('--agent', choices=list(VALID_AGENTS), help='Filter by agent')
    args = parser.parse_args()

    # Determine status filter
    if args.active:
        status_filter = 'executing'
    elif args.all:
        status_filter = None  # No filter
    else:
        status_filter = 'executing'  # Default to active

    # Scan all agents
    all_tasks = []
    agents_to_scan = [args.agent] if args.agent else list(VALID_AGENTS)

    for agent in sorted(agents_to_scan):
        tasks = scan_agent_tasks(agent, status_filter)
        all_tasks.extend(tasks)

    # Sort by priority and age
    priority_order = {'critical': 0, 'high': 1, 'normal': 2, 'low': 3, 'unknown': 4}
    all_tasks.sort(key=lambda t: (priority_order.get(t['priority'], 4), -(t.get('age_seconds') or 0)))

    # Output
    if args.json:
        print(json.dumps(all_tasks, indent=2))
    else:
        # Human-readable output
        if not all_tasks:
            print("No tasks found.")
            return

        # Summary
        executing = sum(1 for t in all_tasks if t['status'] == 'executing')
        anomalies = sum(1 for t in all_tasks if t['status'] == 'executing' and (t['pid'] is None or t['pid_alive'] is False))

        print(f"{'='*80}")
        print(f"TASK STATUS REPORT - {datetime.now().isoformat()}")
        print(f"{'='*80}")
        print(f"Total: {len(all_tasks)} | Executing: {executing} | Anomalies: {anomalies}")
        print(f"{'='*80}\n")

        for task in all_tasks:
            status_icon = {
                'executing': '🔄',
                'done': '✅',
                'pending': '⏳'
            }.get(task['status'], '❓')

            pid_status = ""
            if task['status'] == 'executing':
                if task['pid'] is None:
                    pid_status = " [NO PID FILE]"
                elif task['pid_alive']:
                    age = f"{task['age_seconds']}s" if task['age_seconds'] else "unknown"
                    pid_status = f" [PID {task['pid']} alive, age: {age}]"
                else:
                    age = f"{task['age_seconds']}s" if task['age_seconds'] else "unknown"
                    pid_status = f" [PID {task['pid']} DEAD, age: {age}] ⚠️"

            skill = f" ({task['skill_hint']})" if task['skill_hint'] else ""
            task_id = f" [{task['task_id'][:12]}...]" if task['task_id'] else ""

            print(f"{status_icon} {task['agent']:10} | {task['priority']:8} | {task['file'][:50]}{skill}{task_id}{pid_status}")

        if anomalies > 0:
            print(f"\n⚠️  {anomalies} anomaly(ies) detected - check task-watcher recovery")


if __name__ == "__main__":
    main()
