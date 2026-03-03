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

AGENTS_DIR = "/Users/kublai/.openclaw/agents"
SPAWN_QUEUE = "/Users/kublai/.openclaw/agents/main/logs/spawn-pending.json"

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

def spawn_subagent(agent_name, task, subagent_task):
    """Spawn a subagent for parallel work"""
    config = load_agent_config(agent_name)
    
    spawn_request = {
        "agent": agent_name,
        "model": config.get('model', 'qwen3.5-plus'),
        "task": subagent_task,
        "priority": "normal",
        "label": f"{agent_name}-sub-{int(time.time())}",
        "source": "agent_delegation",
        "parent_task": task
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
        json.dump({'spawns': existing, 'updated': time.time()}, f, indent=2)
    
    print(f"✓ Subagent spawned: {spawn_request['label']}")
    return spawn_request['label']

def execute_task_with_llm(agent_name, task_text, config):
    """Execute task using LLM (local or cloud)"""
    from local_llm_router import run_with_routing
    
    # Build prompt with agent context
    prompt = f"""You are {agent_name.capitalize()}, {config.get('agent_role', 'an AI agent')}.

**Capabilities:** {', '.join(config.get('capabilities', []))}

**Task:** {task_text}

Execute this task using your capabilities. Provide:
1. Analysis of what needs to be done
2. Step-by-step execution plan
3. Results or deliverables
4. Any follow-up actions needed

Be thorough and professional."""
    
    # Run with local LLM routing
    result = run_with_routing(
        agent=agent_name,
        task_name="task_execution",
        prompt=prompt,
        force_cloud=False
    )
    
    return result

def process_task(agent_name, task):
    """Process a single task with actual execution"""
    print(f"\n📋 Processing task: {task['task'][:60]}...")
    
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
            subagent_task=task['task']
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
        from neo4j import GraphDatabase
        
        uri = "bolt://localhost:7687"
        user = "neo4j"
        password = "myStrongPassword123"
        
        driver = GraphDatabase.driver(uri, auth=(user, password))
        
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

def main():
    parser = argparse.ArgumentParser(description='Agent task handler')
    parser.add_argument('--agent', required=True, help='Agent name')
    parser.add_argument('--poll', action='store_true', help='Continuously poll for tasks')
    parser.add_argument('--poll-interval', type=int, default=30, help='Poll interval in seconds')
    
    args = parser.parse_args()
    
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
