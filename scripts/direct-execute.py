#!/usr/bin/env python3
"""
Direct Task Executor

Executes tasks immediately without queue wait.
Bypasses the 5-minute cron delay.

Usage:
    python3 direct-execute.py --agent temujin --task "Build a login feature"
    python3 direct-execute.py --classify "Build a login feature"  # Just classify
"""

import argparse
import json
import os
import sys
from datetime import datetime

SCRIPTS_DIR = "/Users/kublai/.openclaw/agents/main/scripts"
AGENTS_DIR = "/Users/kublai/.openclaw/agents"

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
task_router = load_module('task_router', f'{SCRIPTS_DIR}/task-router.py')
agent_handler = load_module('agent_handler', f'{SCRIPTS_DIR}/agent-task-handler.py')

def classify_task(task_text):
    """Classify task using unified router"""
    return task_router.classify_task(task_text)

def execute_with_agent(agent_name, task_text, priority="normal"):
    """Execute task directly with agent (no queue wait)"""
    import tempfile
    import os
    
    # Create temporary task file
    timestamp = int(datetime.now().timestamp())
    task_dir = f"{AGENTS_DIR}/{agent_name}/tasks"
    task_file = f"{task_dir}/direct-{timestamp}.md"
    
    os.makedirs(task_dir, exist_ok=True)
    
    with open(task_file, 'w') as f:
        f.write(f"""---
agent: {agent_name}
priority: {priority}
created: {datetime.now().isoformat()}
source: direct_execute
---

# Task: {task_text}

Routed by direct-execute.py
""")
    
    # Execute immediately
    print(f"  Executing with {agent_name}...")
    result = agent_handler.execute_single_task(agent_name, task_file)
    
    # Mark as completed
    completed_file = f"{task_dir}/direct-{timestamp}.completed.done.md"
    if os.path.exists(task_file):
        try:
            os.rename(task_file, completed_file)
        except:
            pass
    
    return result
    
    # Create temporary task file
    timestamp = int(datetime.now().timestamp())
    task_dir = f"{AGENTS_DIR}/{agent_name}/tasks"
    task_file = f"{task_dir}/direct-{timestamp}.md"
    
    os.makedirs(task_dir, exist_ok=True)
    
    with open(task_file, 'w') as f:
        f.write(f"""---
agent: {agent_name}
priority: {priority}
created: {datetime.now().isoformat()}
source: direct_execute
---

# Task: {task_text}

Routed by direct-execute.py
""")
    
    # Execute immediately
    print(f"  Executing with {agent_name}...")
    result = execute_single_task(agent_name, task_file)
    
    # Clean up task file
    completed_file = f"{task_dir}/direct-{timestamp}.completed.done.md"
    if os.path.exists(task_file):
        os.rename(task_file, completed_file)
    
    return result

def execute_subagent(task_text, priority="normal"):
    """Execute task via subagent spawn"""
    import subprocess
    
    SPAWN_QUEUE = "/Users/kublai/.openclaw/agents/main/logs/spawn-pending.json"
    
    spawn_request = {
        "agent": "subagent",
        "model": "qwen3.5-plus",
        "task": task_text,
        "priority": priority,
        "label": f"direct-sub-{int(datetime.now().timestamp())}",
        "source": "direct_execute"
    }
    
    # Add to spawn queue
    os.makedirs(os.path.dirname(SPAWN_QUEUE), exist_ok=True)
    
    existing = []
    if os.path.exists(SPAWN_QUEUE):
        try:
            with open(SPAWN_QUEUE, 'r') as f:
                data = json.load(f)
                existing = data.get('spawns', [])
        except:
            pass
    
    existing.append(spawn_request)
    
    with open(SPAWN_QUEUE, 'w') as f:
        json.dump({'spawns': existing, 'updated': datetime.now().timestamp()}, f, indent=2)
    
    print(f"  Spawning subagent: {spawn_request['label']}")
    
    return {"success": True, "subagent": spawn_request['label']}

def execute_task(message, priority="normal"):
    """Classify and execute in one call"""
    # Classify
    classification = classify_task(message)
    destination = classification['destination']
    
    print(f"Task: {message[:80]}...")
    print(f"Classification: {classification['complexity']} → {destination}")
    
    # Execute immediately
    if destination == 'subagent':
        result = execute_subagent(message, priority)
    else:
        result = execute_with_agent(destination, message, priority)
    
    return result

def main():
    parser = argparse.ArgumentParser(description='Direct task executor')
    parser.add_argument('--task', help='Task to execute immediately')
    parser.add_argument('--classify', help='Just classify, don\'t execute')
    parser.add_argument('--priority', default='normal', choices=['high', 'normal', 'low'])
    
    args = parser.parse_args()
    
    if not args.task and not args.classify:
        print("Usage: python3 direct-execute.py --task <text> OR --classify <text>")
        sys.exit(1)
    
    task_text = args.task or args.classify
    
    if args.classify:
        # Just classify
        classification = classify_task(task_text)
        print(json.dumps(classification, indent=2))
    else:
        # Execute immediately
        print("=== Direct Task Execution ===")
        result = execute_task(task_text, args.priority)
        print(f"\n✓ Execution complete: {result}")

if __name__ == "__main__":
    main()
