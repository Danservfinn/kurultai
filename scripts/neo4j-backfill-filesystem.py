#!/usr/bin/env python3
"""
neo4j-backfill-filesystem.py — Rebuild filesystem task files from Neo4j.

Neo4j is now the single source of truth for task state. This script rebuilds
the filesystem materialized view (task .md files) from Neo4j data.

Use cases:
- Recover from filesystem corruption
- Sync after Neo4j migration
- Rebuild after accidental deletion

Usage:
    python3 neo4j-backfill-filesystem.py --agent temujin  # Rebuild one agent
    python3 neo4j-backfill-filesystem.py --all              # Rebuild all agents
    python3 neo4j-backfill-filesystem.py --status PENDING   # Only PENDING tasks
    python3 neo4j-backfill-filesystem.py --dry-run           # Preview without writing
"""

import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from neo4j_task_tracker import get_driver
from kurultai_paths import AGENTS_DIR, VALID_AGENTS


def get_tasks_from_neo4j(agent=None, status=None):
    """Query Neo4j for tasks to backfill."""
    driver = get_driver()
    tasks = []

    with driver.session() as session:
        if agent:
            query = """
                MATCH (t:Task {agent: $agent})
                WHERE $status IS NULL OR t.status = $status
                RETURN t.task_id as task_id, t.agent as agent, t.title as title,
                       t.body as body, t.priority as priority, t.status as status,
                       t.skill_hint as skill_hint, t.created as created,
                       t.source as source, t.bucket as bucket
                ORDER BY t.created DESC
            """
            result = session.run(query, agent=agent, status=status)
        else:
            query = """
                MATCH (t:Task)
                WHERE $status IS NULL OR t.status = $status
                RETURN t.task_id as task_id, t.agent as agent, t.title as title,
                       t.body as body, t.priority as priority, t.status as status,
                       t.skill_hint as skill_hint, t.created as created,
                       t.source as source, t.bucket as bucket
                ORDER BY t.agent, t.created DESC
            """
            result = session.run(query, status=status)

        for record in result:
            tasks.append(dict(record))

    return tasks


def generate_task_filename(task):
    """Generate task filename from task data."""
    priority = task.get("priority") or "normal"
    created = task.get("created")
    if created:
        try:
            ts = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
            epoch = int(ts.timestamp())
        except Exception:
            epoch = int(datetime.now().timestamp())
    else:
        epoch = int(datetime.now().timestamp())

    status_suffix = ""
    status = task.get("status")
    if status == "EXECUTING":
        status_suffix = ".executing"
    elif status in ("COMPLETED", "COMPLETED_VERIFIED"):
        status_suffix = ".completed.done"
    elif status == "FAILED":
        status_suffix = ".failed.done"

    return f"{priority}-{epoch}{status_suffix}.md"


def generate_task_frontmatter(task):
    """Generate YAML frontmatter from task data."""
    lines = ["---"]
    lines.append(f"task_id: {task.get('task_id', 'unknown')}")
    lines.append(f"title: {task.get('title', 'Untitled')}")
    lines.append(f"priority: {task.get('priority', 'normal')}")
    lines.append(f"agent: {task.get('agent', 'unknown')}")

    if task.get("skill_hint"):
        lines.append(f"skill_hint: {task['skill_hint']}")
    if task.get("bucket"):
        lines.append(f"bucket: {task['bucket']}")
    if task.get("source"):
        lines.append(f"source: {task['source']}")
    if task.get("created"):
        lines.append(f"created: {task['created']}")

    lines.append(f"status: {task.get('status', 'PENDING')}")
    lines.append("---")
    lines.append("")

    return "\n".join(lines)


def backfill_task(task, dry_run=False):
    """Create filesystem task file from Neo4j data."""
    agent = task.get("agent")
    if not agent or agent not in VALID_AGENTS:
        print(f"[SKIP] Invalid agent: {agent}")
        return False

    agent_dir = AGENTS_DIR / agent / "tasks"
    agent_dir.mkdir(parents=True, exist_ok=True)

    filename = generate_task_filename(task)
    filepath = agent_dir / filename

    # Check if file already exists
    if filepath.exists():
        print(f"[EXISTS] {filepath}")
        return False

    # Generate content
    frontmatter = generate_task_frontmatter(task)
    body = task.get("body") or task.get("title") or "No description"
    content = f"{frontmatter}\n# Task: {task.get('title', 'Untitled')}\n\n{body}\n"

    if dry_run:
        print(f"[DRY-RUN] Would create: {filepath}")
        print(f"           task_id={task.get('task_id')}, status={task.get('status')}")
        return True

    # Write file
    filepath.write_text(content, encoding="utf-8")
    print(f"[CREATED] {filepath}")
    return True


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Backfill filesystem from Neo4j")
    parser.add_argument("--agent", choices=VALID_AGENTS, help="Rebuild specific agent")
    parser.add_argument("--all", action="store_true", help="Rebuild all agents")
    parser.add_argument("--status", help="Filter by status (PENDING, EXECUTING, COMPLETED, FAILED)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    if not args.agent and not args.all:
        parser.error("Specify --agent <name> or --all")

    agent = args.agent if not args.all else None

    print(f"=== Neo4j Filesystem Backfill ===")
    print(f"Agent: {agent or 'all'}")
    print(f"Status filter: {args.status or 'none'}")
    print(f"Dry run: {args.dry_run}")
    print()

    tasks = get_tasks_from_neo4j(agent=agent, status=args.status)
    print(f"Found {len(tasks)} tasks in Neo4j")
    print()

    created = 0
    skipped = 0
    for task in tasks:
        if backfill_task(task, dry_run=args.dry_run):
            created += 1
        else:
            skipped += 1

    print()
    print(f"[SUMMARY] Created: {created}, Skipped: {skipped}")


if __name__ == "__main__":
    main()
