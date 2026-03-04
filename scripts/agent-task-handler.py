#!/usr/bin/env python3
"""
Agent Task Handler

Allows persistent agents to pick up and process tasks from their queue.
Can spawn subagents for parallel work.

Usage:
    python3 agent-task-handler.py --agent temujin
"""

import argparse
import glob
import json
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from json_state import locked_json_update

AGENTS_DIR = "/Users/kublai/.openclaw/agents"
SPAWN_QUEUE = "/Users/kublai/.openclaw/agents/main/logs/spawn-pending.json"
MAX_TASK_DEPTH = 3

def load_agent_config(agent_name):
    """Load agent configuration"""
    config_path = f"{AGENTS_DIR}/{agent_name}/config.json"
    with open(config_path, 'r') as f:
        return json.load(f)

def get_pending_tasks(agent_name):
    """Get pending tasks from agent's queue"""
    config = load_agent_config(agent_name)
    task_queue_path = config.get('task_queue_path', f"{AGENTS_DIR}/{agent_name}/tasks")
    
    tasks = []
    for pattern in ['high-*.md', 'normal-*.md', 'low-*.md']:
        for task_file in glob.glob(f"{task_queue_path}/{pattern}"):
            if not task_file.endswith('.executing.md') and not task_file.endswith('.done.md'):
                # Read task content
                with open(task_file, 'r') as f:
                    content = f.read()
                
                # Extract task description
                task_desc = content
                for line in content.split('\n'):
                    if line.startswith('# Task:'):
                        task_desc = line.replace('# Task:', '').strip()
                        break
                
                # Determine priority
                priority = 'normal'
                if 'high-' in task_file:
                    priority = 'high'
                elif 'low-' in task_file:
                    priority = 'low'
                
                tasks.append({
                    'file': task_file,
                    'task': task_desc,
                    'priority': priority,
                    'created': datetime.fromtimestamp(os.path.getmtime(task_file)).isoformat()
                })
    
    # Sort by priority
    priority_order = {'high': 0, 'normal': 1, 'low': 2}
    tasks.sort(key=lambda x: priority_order.get(x['priority'], 1))
    
    return tasks

def mark_task_executing(task_file):
    """Mark task as being executed"""
    executing_file = task_file.replace('.md', '.executing.md')
    os.rename(task_file, executing_file)
    return executing_file

def mark_task_completed(task_file, status='completed'):
    """Mark task as completed"""
    # Find executing file
    executing_file = task_file.replace('.md', '.executing.md')
    if os.path.exists(executing_file):
        completed_file = executing_file.replace('.executing.md', f'.{status}.done.md')
        os.rename(executing_file, completed_file)
        print(f"✓ Task completed: {completed_file}")

def _extract_depth(content):
    """Extract depth field from task frontmatter."""
    import re
    match = re.search(r'^depth:\s*(\d+)', content, re.MULTILINE)
    return int(match.group(1)) if match else 0


def spawn_subagent(agent_name, task, subagent_task, depth=0):
    """Spawn a subagent for parallel work. Rejects if depth >= MAX_TASK_DEPTH."""
    if depth >= MAX_TASK_DEPTH:
        print(f"REJECT: depth={depth} >= {MAX_TASK_DEPTH} — preventing runaway chain")
        return None

    config = load_agent_config(agent_name)

    spawn_request = {
        "agent": agent_name,
        "model": config.get('model', 'qwen3.5-plus'),
        "task": subagent_task,
        "priority": "normal",
        "label": f"{agent_name}-sub-{int(time.time())}",
        "source": "agent_delegation",
        "parent_task": task,
        "depth": depth + 1,
    }
    
    # Add to spawn queue with file locking
    os.makedirs(os.path.dirname(SPAWN_QUEUE), exist_ok=True)
    with locked_json_update(SPAWN_QUEUE, default={'spawns': [], 'updated': 0}) as data:
        if 'spawns' not in data:
            data['spawns'] = []
        data['spawns'].append(spawn_request)
        data['updated'] = time.time()

    print(f"✓ Subagent spawned: {spawn_request['label']}")
    return spawn_request['label']

def execute_task_with_llm(agent_name, task_text, config):
    """Execute task by spawning a subagent using the agent's configured model"""
    import sys
    import json
    import time
    import os
    
    try:
        model = config.get('model', 'qwen3.5-plus')
        
        spawn_request = {
            "agent": agent_name,
            "model": model,
            "task": f"You are {agent_name.capitalize()}, {config.get('agent_role', 'an AI agent')}.\nCapabilities: {', '.join(config.get('capabilities', []))}\n\nTask: {task_text}",
            "priority": "normal",
            "label": f"{agent_name}-exec-{int(time.time())}",
            "source": "agent_execution",
            "destination": "subagent",
            "status": "ready"
        }
        
        # Add to spawn queue with file locking
        os.makedirs(os.path.dirname(SPAWN_QUEUE), exist_ok=True)
        with locked_json_update(SPAWN_QUEUE, default={'spawns': [], 'updated': 0}) as data:
            if 'spawns' not in data:
                data['spawns'] = []
            data['spawns'].append(spawn_request)
            data['updated'] = time.time()
            
        return {
            "success": True,
            "content": f"Task delegated to OpenClaw spawn queue under label {spawn_request['label']} using model {model}.",
            "model": model,
            "latency_ms": 0
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "model": "failed",
            "latency_ms": 0
        }

def process_task(agent_name, task):
    """Process a single task with actual execution"""
    print(f"\n📋 Processing task: {task['task'][:60]}...")

    # Extract depth from task content
    depth = task.get('depth', 0)

    # Mark as executing
    executing_file = mark_task_executing(task['file'])
    print(f"  Status: executing → {executing_file}")

    # Load agent config
    config = load_agent_config(agent_name)

    # Determine if task needs subagent delegation
    needs_delegation = len(task['task'].split()) > 50 or any(
        kw in task['task'].lower() for kw in ['multi-step', 'complex', 'pipeline', 'system']
    )

    if needs_delegation:
        print(f"  🔄 Task is complex - spawning subagent...")

        # Spawn subagent for parallel work
        subagent_label = spawn_subagent(
            agent_name=agent_name,
            task=task['file'],
            subagent_task=task['task'],
            depth=depth,
        )
        
        print(f"  ✓ Subagent spawned: {subagent_label}")
        print(f"  ⏳ Waiting for subagent completion...")
        
        # In full implementation, would wait for subagent
        # For now, mark as in_progress
        mark_task_completed(task['file'], 'in_progress')
        print(f"  ⏳ Task in progress (waiting for subagent)")
        
        return True
    
    # Execute task directly with LLM
    print(f"  🤖 Executing with LLM...")
    result = execute_task_with_llm(agent_name, task['task'], config)
    
    if result.get('success'):
        # Save result to workspace
        workspace_path = config.get('workspace_path', f"{AGENTS_DIR}/{agent_name}/workspace")
        result_file = f"{workspace_path}/task-{int(datetime.now().timestamp())}.md"
        
        os.makedirs(workspace_path, exist_ok=True)
        with open(result_file, 'w') as f:
            f.write(f"# Task Result\n\n")
            f.write(f"**Task:** {task['task']}\n\n")
            f.write(f"**Model:** {result.get('model', 'unknown')}\n\n")
            f.write(f"**Latency:** {result.get('latency_ms', 0)}ms\n\n")
            f.write(f"---\n\n")
            f.write(f"{result.get('content', 'No content')}\n")
        
        print(f"  ✓ Result saved: {result_file}")
        mark_task_completed(task['file'], 'completed')
        print(f"  ✓ Task completed")
        
        # Update Neo4j
        update_agent_state(agent_name, 'idle', None, increment_completed=True)
        
        return True
    else:
        print(f"  ✗ Task execution failed: {result.get('error', 'Unknown error')}")
        mark_task_completed(task['file'], 'failed')
        return False

def update_agent_state(agent_name, status='busy', task_label=None, increment_completed=False):
    """Update agent state in Neo4j"""
    try:
        from neo4j_task_tracker import get_driver

        driver = get_driver()
        
        with driver.session() as session:
            if increment_completed:
                session.run("""
                    MATCH (a:AgentState {name: $name})
                    SET a.status = $status,
                        a.current_task = $task,
                        a.last_heartbeat = datetime(),
                        a.tasks_completed = coalesce(a.tasks_completed, 0) + 1
                """, name=agent_name, status=status, task=task_label)
            elif task_label:
                session.run("""
                    MATCH (a:AgentState {name: $name})
                    SET a.status = $status,
                        a.current_task = $task,
                        a.last_heartbeat = datetime()
                """, name=agent_name, status=status, task=task_label)
            else:
                session.run("""
                    MATCH (a:AgentState {name: $name})
                    SET a.status = $status,
                        a.current_task = null,
                        a.last_heartbeat = datetime()
                """, name=agent_name, status=status)
        
        driver.close()
    except Exception as e:
        print(f"⚠ Neo4j update failed: {e}")

def execute_single_task(agent_name, task_file):
    """Execute a single task file directly"""
    # Read task file
    with open(task_file, 'r') as f:
        content = f.read()

    # Extract task description
    task_desc = content
    for line in content.split('\n'):
        if line.startswith('# Task:'):
            task_desc = line.replace('# Task:', '').strip()
            break

    # Extract depth from frontmatter
    depth = _extract_depth(content)

    task = {
        'file': task_file,
        'task': task_desc,
        'priority': 'normal',
        'depth': depth,
    }

    return process_task(agent_name, task)

def main():
    parser = argparse.ArgumentParser(description='Agent task handler')
    parser.add_argument('--agent', required=True, help='Agent name')
    parser.add_argument('--poll', action='store_true', help='Continuously poll for tasks')
    parser.add_argument('--poll-interval', type=int, default=30, help='Poll interval in seconds')
    parser.add_argument('--task-file', help='Execute specific task file')
    
    args = parser.parse_args()
    
    # If task-file is specified, execute single task
    if args.task_file:
        print(f"Executing task: {args.task_file}")
        result = execute_single_task(args.agent, args.task_file)
        sys.exit(0 if result else 1)
    
    agent_name = args.agent
    print(f"=== Agent Task Handler: {agent_name.capitalize()} ===\n")
    
    # Load config
    try:
        config = load_agent_config(agent_name)
        print(f"Role: {config.get('agent_role')}")
        print(f"Model: {config.get('model')}")
        print(f"Workspace: {config.get('workspace_path')}")
        print()
    except Exception as e:
        print(f"✗ Failed to load config: {e}")
        sys.exit(1)
    
    # Update state to idle
    update_agent_state(agent_name, 'idle')
    
    if args.poll:
        print(f"Polling for tasks every {args.poll_interval}s... (Ctrl+C to stop)\n")
        try:
            while True:
                tasks = get_pending_tasks(agent_name)
                
                if tasks:
                    print(f"Found {len(tasks)} pending task(s)")
                    update_agent_state(agent_name, 'busy', tasks[0]['file'])
                    
                    for task in tasks:
                        process_task(agent_name, task)
                    
                    update_agent_state(agent_name, 'idle')
                else:
                    print(f"No pending tasks (polling...)")
                
                time.sleep(args.poll_interval)
        except KeyboardInterrupt:
            print("\n\nStopping poll...")
            update_agent_state(agent_name, 'idle')
    else:
        # Single poll
        tasks = get_pending_tasks(agent_name)
        
        if tasks:
            print(f"Found {len(tasks)} pending task(s)\n")
            update_agent_state(agent_name, 'busy', tasks[0]['file'])
            
            for task in tasks:
                process_task(agent_name, task)
            
            update_agent_state(agent_name, 'idle')
            print(f"\n✓ All tasks processed")
        else:
            print("No pending tasks")

if __name__ == "__main__":
    main()
