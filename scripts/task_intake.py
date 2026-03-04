#!/usr/bin/env python3
"""
task_intake.py — Single entry point for all task creation.

Pipeline:
    1. Validate depth (reject if >= MAX_DEPTH)
    2. Route via canonical router (task_router.py)
    3. Duplicate check (has_pending_task)
    4. Create in Neo4j (primary) via create_task_full()
    5. Write filesystem (backward compat, done by create_task_full)

Usage:
    from task_intake import create_task

    task_id = create_task(
        title="Investigate error spike",
        body="Check logs for errors...",
        priority="high",
        source="kublai-actions",
        depth=0,
        agent=None,  # auto-route from title
    )
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from task_router import classify_task, route_by_text

MAX_TASK_DEPTH = 3
AGENT_DIR = os.path.expanduser("~/.openclaw/agents/main/agent")


def has_pending_task(agent, title_prefix):
    """Check if an agent already has an uncompleted task with this title prefix."""
    task_dir = f"{AGENT_DIR}/{agent}/tasks"
    if not os.path.exists(task_dir):
        return False
    for fname in os.listdir(task_dir):
        if '.done' in fname:
            continue
        fpath = os.path.join(task_dir, fname)
        try:
            with open(fpath) as f:
                content = f.read(500)
            if f"# Task: {title_prefix}" in content:
                return True
        except Exception:
            continue
    return False


def create_task(title, body, priority="normal", source="task_intake",
                depth=0, agent=None, parent_id=None, skip_duplicate_check=False):
    """Create a task through the canonical pipeline.

    Args:
        title: Task title (used for routing if agent is None)
        body: Task body/description
        priority: "high", "normal", or "low"
        source: Origin of the task
        depth: Current task chain depth
        agent: Target agent (auto-routed from title if None)
        parent_id: Parent task ID for chain tracking
        skip_duplicate_check: Set True to skip the has_pending_task guard

    Returns:
        task_id string on success, None on rejection
    """
    # 1. Validate depth
    if depth >= MAX_TASK_DEPTH:
        print(f"REJECT: depth={depth} >= {MAX_TASK_DEPTH} for '{title[:60]}'")
        return None

    # 2. Route if no agent specified
    if agent is None:
        agent = route_by_text(title)
        if agent == "subagent":
            agent = "kublai"  # Default fallback

    # 3. Duplicate check
    if not skip_duplicate_check:
        # Use first 40 chars of title as prefix
        prefix = title[:40]
        if has_pending_task(agent, prefix):
            print(f"SKIP: duplicate task for {agent}: '{title[:60]}'")
            return None

    # 4-5. Create in Neo4j + filesystem
    try:
        from neo4j_task_tracker import get_tracker
        tracker = get_tracker()
        task_id = tracker.create_task_full(
            agent=agent,
            title=title,
            body=body,
            priority=priority,
            source=source,
            depth=depth,
            parent_id=parent_id,
        )
        print(f"CREATED: {priority} task {task_id} for {agent}: {title[:60]}")
        return task_id
    except Exception as e:
        print(f"ERROR: Neo4j unavailable, falling back to filesystem-only: {e}")
        # Filesystem-only fallback
        import time
        from datetime import datetime
        task_dir = f"{AGENT_DIR}/{agent}/tasks"
        os.makedirs(task_dir, exist_ok=True)
        epoch = int(time.time())
        filepath = f"{task_dir}/{priority}-{epoch}.md"
        content = f"""---
agent: {agent}
priority: {priority}
created: {datetime.now().isoformat()}
source: {source}
depth: {depth}
---

# Task: {title}

{body}
"""
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"CREATED (filesystem-only): {filepath}")
        return f"fs-{epoch}"


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Task Intake — single entry point for task creation")
    parser.add_argument("--title", required=True, help="Task title")
    parser.add_argument("--body", default="", help="Task body")
    parser.add_argument("--priority", default="normal", choices=["high", "normal", "low"])
    parser.add_argument("--agent", default=None, help="Target agent (auto-routed if omitted)")
    parser.add_argument("--source", default="cli", help="Task source")
    args = parser.parse_args()

    task_id = create_task(
        title=args.title,
        body=args.body or f"Task: {args.title}",
        priority=args.priority,
        source=args.source,
        agent=args.agent,
    )
    if task_id:
        print(f"Task ID: {task_id}")
    else:
        print("Task creation rejected")
        sys.exit(1)
