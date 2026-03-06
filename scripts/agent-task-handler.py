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
import subprocess
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from json_state import locked_json_update

AGENTS_DIR = "/Users/kublai/.openclaw/agents"
SPAWN_QUEUE = "/Users/kublai/.openclaw/agents/main/logs/spawn-pending.json"
TASK_LEDGER = "/Users/kublai/.openclaw/tasks/task-ledger.jsonl"
CLAUDE_AGENT = "/Users/kublai/.local/bin/claude-agent"
CLAUDE_TIMEOUT = 600  # 10 minutes for Claude Code execution
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
    """Mark task as completed.

    Handles both cases: task_file is the original .md or already .executing.md.
    Avoids double-suffix bug (.executing.executing.md → .executing.completed.done.md).
    """
    if task_file.endswith('.executing.md'):
        executing_file = task_file
    else:
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


def _extract_task_id(content):
    """Extract task_id from task frontmatter."""
    import re
    match = re.search(r'^task_id:\s*(\S+)', content, re.MULTILINE)
    return match.group(1) if match else None


def _extract_skill_hint(content):
    """Extract skill_hint from task frontmatter."""
    import re
    match = re.search(r'^skill_hint:\s*(\S+)', content, re.MULTILINE)
    return match.group(1) if match else None


def _append_ledger(entry):
    """Append an event to the unified task-ledger.jsonl."""
    try:
        os.makedirs(os.path.dirname(TASK_LEDGER), exist_ok=True)
        with open(TASK_LEDGER, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


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

def _load_agent_memory(agent_name):
    """Load recent memory context for the agent."""
    memory_dir = f"{AGENTS_DIR}/{agent_name}/memory"
    context = ""

    # Load context.md if it exists
    context_file = f"{memory_dir}/context.md"
    if os.path.exists(context_file):
        try:
            with open(context_file, 'r') as f:
                context += f.read()[:2000] + "\n\n"
        except Exception:
            pass

    # Load today's memory file
    today = datetime.now().strftime("%Y-%m-%d")
    today_file = f"{memory_dir}/{today}.md"
    if os.path.exists(today_file):
        try:
            with open(today_file, 'r') as f:
                lines = f.readlines()
                context += "".join(lines[-50:])  # Last 50 lines
        except Exception:
            pass

    return context.strip()


def execute_task_with_llm(agent_name, task_text, config, skill_hint=None):
    """Execute task via Claude Code using the claude-agent wrapper.

    Each agent runs as a sovereign Claude Code session with its own
    CLAUDE.md (auto-discovered from workdir), identity, and tools.
    """
    # Use agent ROOT directory as workdir so CLAUDE.md is auto-discovered
    agent_root = f"{AGENTS_DIR}/{agent_name}"

    # Build prompt with agent context
    memory = _load_agent_memory(agent_name)
    memory_section = f"\n\n## Recent Context\n{memory}" if memory else ""
    skill_section = f"\n\nIMPORTANT: Start this task by invoking {skill_hint} — it is the correct skill for this work." if skill_hint else ""

    prompt = (
        f"{task_text}"
        f"{memory_section}"
        f"{skill_section}\n\n"
        "Execute this task completely using your tools. "
        "Read files, write code, run commands, verify your work. "
        "For simple questions, a direct answer is fine."
    )

    env = os.environ.copy()
    env.pop('CLAUDECODE', None)  # Allow nested Claude Code sessions
    env['PATH'] = (
        "/Users/kublai/.local/bin:/opt/homebrew/bin:"
        "/usr/local/bin:/usr/bin:/bin:" + env.get('PATH', '')
    )

    try:
        result = subprocess.run(
            [CLAUDE_AGENT, "--workdir", agent_root, "--", prompt],
            capture_output=True,
            text=True,
            timeout=CLAUDE_TIMEOUT,
            env=env,
        )

        output = result.stdout or ""
        error = result.stderr[-2000:] if result.stderr else ""

        success = result.returncode == 0
        if success and not output.strip():
            success = False
            error = "Claude Code returned success but produced no output"

        return {
            "success": success,
            "content": output,
            "error": error if not success else None,
            "model": "claude-code",
            "latency_ms": 0
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": f"Claude Code timed out after {CLAUDE_TIMEOUT}s",
            "model": "claude-code",
            "latency_ms": 0
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "model": "claude-code",
            "latency_ms": 0
        }

def process_task(agent_name, task):
    """Process a single task via Claude Code.

    All tasks (simple and complex) go through Claude Code, which handles
    complexity internally via its own subagent system and skills.
    """
    # Use full task content for Claude Code, not just the summary line
    task_content = task.get('full_content', task['task'])
    task_id = task.get('task_id')
    print(f"\n📋 Processing: {task['task'][:80]}...")

    # Mark as executing
    executing_file = mark_task_executing(task['file'])
    print(f"  Status: executing")

    # Load agent config
    config = load_agent_config(agent_name)

    # Execute via Claude Code
    skill_hint = task.get('skill_hint')
    print(f"  🤖 Executing via Claude Code...{f' (skill: {skill_hint})' if skill_hint else ''}")
    start_time = time.time()
    result = execute_task_with_llm(agent_name, task_content, config, skill_hint=skill_hint)
    elapsed_s = round(time.time() - start_time, 1)

    if result.get('success'):
        # Save result to workspace
        workspace_path = config.get('workspace_path', f"{AGENTS_DIR}/{agent_name}/workspace")
        result_file = f"{workspace_path}/task-{int(datetime.now().timestamp())}.md"

        os.makedirs(workspace_path, exist_ok=True)
        with open(result_file, 'w') as f:
            f.write(f"# Task Result\n\n")
            f.write(f"**Task:** {task['task']}\n\n")
            f.write(f"**Model:** claude-code\n\n")
            f.write(f"---\n\n")
            f.write(f"{result.get('content', 'No content')}\n")

        print(f"  ✓ Result saved: {result_file}")
        mark_task_completed(task['file'], 'completed')
        print(f"  ✓ Task completed via Claude Code ({elapsed_s}s)")

        # Emit execution metadata to ledger
        if task_id:
            output_content = result.get('content', '')
            _append_ledger({
                "task_id": task_id,
                "event": "EXECUTION_DETAIL",
                "ts": datetime.now().isoformat(),
                "agent": agent_name,
                "execution_time_s": elapsed_s,
                "output_lines": len(output_content.splitlines()),
                "result_file": result_file,
                "success": True,
            })

        # Update Neo4j
        update_agent_state(agent_name, 'idle', None, increment_completed=True)

        return True
    else:
        error_msg = result.get('error', 'Unknown error')
        print(f"  ✗ Claude Code failed: {error_msg[:200]}")
        mark_task_completed(task['file'], 'failed')

        if task_id:
            _append_ledger({
                "task_id": task_id,
                "event": "EXECUTION_DETAIL",
                "ts": datetime.now().isoformat(),
                "agent": agent_name,
                "execution_time_s": elapsed_s,
                "error": error_msg[:500],
                "success": False,
            })

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
    """Execute a single task file via Claude Code."""
    with open(task_file, 'r') as f:
        content = f.read()

    # Extract short description for logging
    task_desc = content
    for line in content.split('\n'):
        if line.startswith('# Task:'):
            task_desc = line.replace('# Task:', '').strip()
            break

    depth = _extract_depth(content)
    task_id = _extract_task_id(content)
    skill_hint = _extract_skill_hint(content)

    task = {
        'file': task_file,
        'task': task_desc,
        'task_id': task_id,
        'skill_hint': skill_hint,
        'full_content': content,  # Pass full content to Claude Code
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
