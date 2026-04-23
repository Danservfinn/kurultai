#!/usr/bin/env python3
"""
neo4j_v2_delegate.py — Delegation: create child tasks, query status/output.

Backs the CLI wrappers:
  kurultai-delegate     — create child task with SPAWNED edge
  kurultai-task-status  — query task status
  kurultai-task-output  — read TaskOutput text

Usage (Python):
    from neo4j_v2_delegate import delegate_task, get_task_status, get_task_output
    child_id = delegate_task(parent_id="normal-123-abc", title="...", prompt="...", to="temujin")
"""
from __future__ import annotations

import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from neo4j_v2_core import TaskStore, MAX_DELEGATION_DEPTH
from kurultai_ledger import generate_task_id
from kurultai_paths import VALID_AGENTS, DISPATCH_AGENTS

logger = logging.getLogger(__name__)


def delegate_task(parent_id: str, title: str, prompt: str,
                  to: str = None, priority: str = "normal",
                  max_retries: int = 2, timeout_s: int = 10800,
                  store: TaskStore = None) -> str:
    """Create a child task delegated from a parent.

    Args:
        parent_id: Parent task ID
        title: Child task title
        prompt: Child task prompt/body
        to: Target agent name (if None, auto-route with anti-affinity)
        priority: Task priority
        max_retries: Max retry count for child
        timeout_s: Timeout in seconds

    Returns:
        Child task_id string

    Raises:
        ValueError: If validation fails (bad agent, depth exceeded, etc.)
    """
    _store = store or TaskStore()
    try:
        # Look up parent task
        parent = _store.get_task(parent_id)
        if parent is None:
            raise ValueError(f"Parent task not found: {parent_id}")

        # Depth check
        parent_depth = parent.get('depth', 0)
        child_depth = parent_depth + 1
        if child_depth > MAX_DELEGATION_DEPTH:
            raise ValueError(
                f"Max delegation depth exceeded: {child_depth} > {MAX_DELEGATION_DEPTH}"
            )

        # Agent validation
        if to:
            if to not in VALID_AGENTS:
                raise ValueError(f"Invalid agent: {to}. Valid: {', '.join(sorted(VALID_AGENTS))}")
        else:
            # Auto-route with anti-affinity (prefer different agent than parent)
            to = _route_with_anti_affinity(
                _store, parent.get('assigned_to', ''), priority
            )

        # Generate child task_id
        child_id = generate_task_id(priority)

        # Classify domain from prompt
        try:
            from task_intake import classify_task_domain
            domain = classify_task_domain(title + " " + prompt)
        except Exception:
            domain = "implementation"

        # Create child task with SPAWNED edge
        _store.create_task(
            task_id=child_id,
            title=title,
            prompt=prompt,
            assigned_to=to,
            priority=priority,
            domain=domain,
            source=f"delegation:{parent_id}",
            depth=child_depth,
            parent_id=parent_id,
            max_retries=max_retries,
            timeout_s=timeout_s,
        )

        logger.info(f"Delegated {child_id} to {to} (parent={parent_id}, depth={child_depth})")
        return child_id

    finally:
        if store is None:
            _store.close()


def _route_with_anti_affinity(store: TaskStore, parent_agent: str,
                               priority: str) -> str:
    """Route child task with anti-affinity: prefer agent different from parent.

    Uses load-based routing with parent agent penalty.
    """
    try:
        from neo4j_v2_router import route_task
        # route_task handles anti-affinity internally
        return route_task(store, "", priority, exclude_agent=parent_agent)
    except ImportError:
        pass

    # Fallback: pick least-loaded dispatch agent that isn't the parent
    best_agent = None
    best_load = float('inf')

    for agent in DISPATCH_AGENTS:
        if agent == parent_agent:
            continue
        depths = store.get_queue_depth(agent)
        load = depths['PENDING'] + depths['WORKING']
        if load < best_load:
            best_load = load
            best_agent = agent

    return best_agent or DISPATCH_AGENTS[0]


def get_task_status(task_id: str, store: TaskStore = None) -> str:
    """Query task status from Neo4j.

    Returns: PENDING | WORKING | COMPLETED | FAILED | NOT_FOUND
    """
    _store = store or TaskStore()
    try:
        with _store.driver.session() as session:
            result = session.run(
                "MATCH (t:Task {task_id: $id}) RETURN t.status AS status",
                id=task_id,
            )
            record = result.single()
            return record["status"] if record else "NOT_FOUND"
    finally:
        if store is None:
            _store.close()


def get_task_output(task_id: str, store: TaskStore = None) -> str:
    """Read TaskOutput text from Neo4j.

    Returns: Output text, or empty string if not found/not completed.
    """
    _store = store or TaskStore()
    try:
        with _store.driver.session() as session:
            result = session.run("""
                MATCH (t:Task {task_id: $id})-[:HAS_OUTPUT]->(o:TaskOutput)
                RETURN o.text AS text
            """, id=task_id)
            record = result.single()
            return record["text"] if record else ""
    finally:
        if store is None:
            _store.close()


# ---------------------------------------------------------------------------
# CLI (direct invocation for testing)
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Task delegation")
    sub = parser.add_subparsers(dest="cmd")

    # delegate
    p_del = sub.add_parser("delegate")
    p_del.add_argument("--parent-id", required=True)
    p_del.add_argument("--to", default=None)
    p_del.add_argument("--title", required=True)
    p_del.add_argument("--prompt", required=True)
    p_del.add_argument("--priority", default="normal")
    p_del.add_argument("--max-retries", type=int, default=2)

    # status
    p_st = sub.add_parser("status")
    p_st.add_argument("task_id")

    # output
    p_out = sub.add_parser("output")
    p_out.add_argument("task_id")

    args = parser.parse_args()

    if args.cmd == "delegate":
        child_id = delegate_task(
            parent_id=args.parent_id, title=args.title, prompt=args.prompt,
            to=args.to, priority=args.priority, max_retries=args.max_retries,
        )
        print(child_id)
    elif args.cmd == "status":
        print(get_task_status(args.task_id))
    elif args.cmd == "output":
        print(get_task_output(args.task_id))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
