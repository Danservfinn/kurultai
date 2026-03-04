#!/usr/bin/env python3
"""
Task Queue Monitor

Continuously monitors task queues and executes pending tasks automatically.
Runs as a background daemon.

Usage:
    python3 task-queue-monitor.py --daemon  # Run continuously
    python3 task-queue-monitor.py --check   # Single check
"""

import argparse
import glob
import json
import os
import sys
import time
from datetime import datetime

SCRIPTS_DIR = "/Users/kublai/.openclaw/agents/main/scripts"
AGENTS_DIR = "/Users/kublai/.openclaw/agents"
LOG_FILE = "/Users/kublai/.openclaw/agents/main/logs/task-queue-monitor.log"

sys.path.insert(0, SCRIPTS_DIR)

# Import with hyphenated filenames
import importlib.util

def load_module(name, path):
    """Load module from path with hyphens"""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

# Load modules
agent_handler = load_module('agent_handler', f'{SCRIPTS_DIR}/agent-task-handler.py')

def log(msg):
    """Log message"""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, 'a') as f:
        f.write(f"[{ts}] {msg}\n")

def get_pending_tasks():
    """Get all pending tasks across all agents"""
    pending = []
    
    for agent in ['kublai', 'temujin', 'mongke', 'chagatai', 'jochi', 'ogedei']:
        task_dir = f"{AGENTS_DIR}/{agent}/tasks"
        if not os.path.exists(task_dir):
            continue
        
        # Find pending tasks (not .executing, not .done)
        for pattern in ['high-*.md', 'normal-*.md', 'low-*.md']:
            for task_file in glob.glob(f"{task_dir}/{pattern}"):
                if '.executing' not in task_file and '.done' not in task_file:
                    # Read task description
                    with open(task_file, 'r') as f:
                        content = f.read()
                        task_desc = content
                        for line in content.split('\n'):
                            if line.startswith('# Task:'):
                                task_desc = line.replace('# Task:', '').strip()
                                break
                    
                    pending.append({
                        'agent': agent,
                        'file': task_file,
                        'task': task_desc,
                        'priority': 'high' if 'high-' in task_file else 'normal' if 'normal-' in task_file else 'low'
                    })
    
    # Sort by priority
    priority_order = {'high': 0, 'normal': 1, 'low': 2}
    pending.sort(key=lambda x: priority_order.get(x['priority'], 1))
    
    return pending

def execute_pending_tasks():
    """Execute all pending tasks"""
    pending = get_pending_tasks()
    
    if not pending:
        log("No pending tasks")
        return 0
    
    log(f"Found {len(pending)} pending task(s)")
    
    completed = 0
    for task in pending:
        log(f"Executing: {task['agent']} - {task['task'][:50]}...")
        
        try:
            # Execute task
            result = agent_handler.execute_single_task(task['agent'], task['file'])
            
            if result:
                # Mark as completed
                completed_file = task['file'].replace('.md', '.completed.done.md')
                if os.path.exists(task['file']):
                    os.rename(task['file'], completed_file)
                
                log(f"✓ Completed: {task['agent']} - {task['task'][:50]}...")
                completed += 1
            else:
                log(f"✗ Failed: {task['agent']} - {task['task'][:50]}...")
        except Exception as e:
            log(f"✗ Error: {task['agent']} - {str(e)}")
    
    log(f"Completed {completed}/{len(pending)} task(s)")
    return completed

def main():
    parser = argparse.ArgumentParser(description='Task queue monitor')
    parser.add_argument('--daemon', action='store_true', help='Run continuously')
    parser.add_argument('--interval', type=int, default=30, help='Check interval in seconds')
    parser.add_argument('--check', action='store_true', help='Single check')
    
    args = parser.parse_args()
    
    log("=== Task Queue Monitor Started ===")
    
    if args.daemon:
        log(f"Running in daemon mode (checking every {args.interval}s)")
        try:
            while True:
                execute_pending_tasks()
                time.sleep(args.interval)
        except KeyboardInterrupt:
            log("\nStopping monitor...")
    elif args.check:
        log("Running single check...")
        execute_pending_tasks()
    else:
        log("Running single check...")
        execute_pending_tasks()

if __name__ == "__main__":
    main()
