#!/usr/bin/env python3
"""
reconcile_neo4j_tasks.py — Reconcile orphaned filesystem tasks with Neo4j

Problem: When Neo4j is unavailable, task_intake.py falls back to filesystem-only
mode, creating tasks that exist in filesystem but NOT in Neo4j. This breaks:
- Queue depth reporting (Neo4j shows 0, filesystem has N)
- Load balancing (decisions based on incorrect queue depths)
- Task tracking (no Task node in Neo4j)

Solution: Scan filesystem for tasks not in Neo4j and sync them.

Usage:
    python3 reconcile_neo4j_tasks.py [--agent AGENT] [--dry-run] [--fix]

Options:
    --agent AGENT  Only reconcile specific agent (default: all)
    --dry-run      Show what would be done without making changes
    --fix          Actually create missing Neo4j nodes (default: report only)
"""

import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kurultai_paths import AGENTS_DIR, VALID_AGENTS


def parse_task_file(filepath):
    """Extract task metadata from filesystem task file.

    Handles two formats:
    1. YAML frontmatter: ---\nagent: mongke\n...---\n# Task...
    2. Self-wake format: # Task...\ntask_id: ...\n---\n...
    """
    content = filepath.read_text()

    metadata = {
        "filepath": str(filepath),
        "filename": filepath.name,
        "status": "pending",  # Default
    }

    # Parse frontmatter (two formats supported)
    if content.startswith("---"):
        # Format 1: Standard YAML frontmatter at start
        parts = content.split("---", 3)
        if len(parts) >= 3:
            frontmatter = parts[1].strip()
            for line in frontmatter.split("\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    key = key.strip().lower()
                    value = value.strip()

                    if key == "agent":
                        metadata["agent"] = value
                    elif key == "priority":
                        metadata["priority"] = value
                    elif key == "task_id":
                        metadata["task_id"] = value
                    elif key == "created":
                        metadata["created"] = value
                    elif key == "source":
                        metadata["source"] = value
                    elif key == "skill_hint":
                        metadata["skill_hint"] = value
                    elif key == "timeout":
                        metadata["timeout"] = value
                    elif key == "depth":
                        metadata["depth"] = value
    else:
        # Format 2: Self-wake style - metadata after title, before ---
        # Extract section between title and first ---
        title_end = content.find("\n")
        if title_end > 0:
            # Find the --- separator
            sep_pos = content.find("---", title_end)
            if sep_pos > title_end:
                metadata_section = content[title_end + 1:sep_pos].strip()
                for line in metadata_section.split("\n"):
                    if ":" in line and not line.strip().startswith("#"):
                        key, value = line.split(":", 1)
                        key = key.strip().lower()
                        value = value.strip()

                        if key == "agent":
                            metadata["agent"] = value
                        elif key == "priority":
                            metadata["priority"] = value
                        elif key == "task_id":
                            metadata["task_id"] = value
                        elif key == "created":
                            metadata["created"] = value
                        elif key == "source":
                            metadata["source"] = value
                        elif key == "skill_hint":
                            metadata["skill_hint"] = value
                        elif key == "timeout":
                            metadata["timeout"] = value
                        elif key == "depth":
                            metadata["depth"] = value

    # Determine status from filename
    # .done.md = completed, .failed.done.md = failed, etc.
    if ".done.md" in metadata["filename"]:
        if ".failed." in metadata["filename"]:
            metadata["status"] = "failed"
        elif ".completed." in metadata["filename"]:
            metadata["status"] = "completed"
        else:
            metadata["status"] = "completed"
    elif ".executing" in metadata["filename"]:
        metadata["status"] = "executing"

    # Extract title from body (first # heading)
    body_start = content.find("#")
    if body_start > 0:
        title_end = content.find("\n", body_start)
        if title_end > body_start:
            title_line = content[body_start:title_end].strip()
            # Remove # and Task: prefix
            metadata["title"] = re.sub(r'^#\s*(Task:\s*)?', '', title_line)

    return metadata


def get_neo4j_task_ids():
    """Get set of all task IDs that exist in Neo4j."""
    try:
        from neo4j import GraphDatabase

        uri = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
        user = os.environ.get('NEO4J_USER', 'neo4j')

        # Handle both NEO4J_PASSWORD and NEO4J_AUTH formats
        if 'NEO4J_AUTH' in os.environ:
            password = os.environ.get('NEO4J_AUTH', '').split('://')[1].split('@')[0]
        else:
            password = os.environ.get('NEO4J_PASSWORD', 'password')

        driver = GraphDatabase.driver(uri, auth=(user, password))
        with driver.session() as session:
            result = session.run("""
                MATCH (t:Task)
                WHERE t.task_id IS NOT NULL
                RETURN t.task_id as task_id
            """)
            task_ids = {record["task_id"] for record in result}
        driver.close()
        return task_ids
    except Exception as e:
        print(f"Warning: Could not connect to Neo4j: {e}", file=sys.stderr)
        return set()


def find_orphaned_tasks(agent_filter=None):
    """Find tasks in filesystem that don't exist in Neo4j."""
    orphaned = []
    neo4j_task_ids = get_neo4j_task_ids()

    agents = [agent_filter] if agent_filter else VALID_AGENTS

    for agent in agents:
        tasks_dir = AGENTS_DIR / agent / "tasks"
        if not tasks_dir.exists():
            continue

        for task_file in tasks_dir.glob("*.md"):
            if task_file.name == ".gitkeep":
                continue

            metadata = parse_task_file(task_file)
            task_id = metadata.get("task_id", "")

            # Check if this task exists in Neo4j
            if task_id and task_id not in neo4j_task_ids:
                metadata["agent"] = agent  # Ensure agent is set
                orphaned.append(metadata)

    return orphaned


def create_neo4j_task(metadata, dry_run=False):
    """Create a Neo4j Task node for an orphaned filesystem task."""
    if dry_run:
        return {"dry_run": True}

    try:
        from neo4j import GraphDatabase

        uri = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
        user = os.environ.get('NEO4J_USER', 'neo4j')

        if 'NEO4J_AUTH' in os.environ:
            password = os.environ.get('NEO4J_AUTH', '').split('://')[1].split('@')[0]
        else:
            password = os.environ.get('NEO4J_PASSWORD', 'password')

        driver = GraphDatabase.driver(uri, auth=(user, password))
        with driver.session() as session:
            # Create Task node
            query = """
                MERGE (t:Task {task_id: $task_id})
                SET t.agent = $agent,
                    t.title = $title,
                    t.priority = $priority,
                    t.status = $status,
                    t.created = datetime($created),
                    t.source = $source,
                    t.skill_hint = $skill_hint
                RETURN t
            """
            session.run(query,
                task_id=metadata.get("task_id"),
                agent=metadata.get("agent"),
                title=metadata.get("title", "Unknown"),
                priority=metadata.get("priority", "normal"),
                status=metadata.get("status", "pending"),
                created=metadata.get("created", datetime.now().isoformat()),
                source=metadata.get("source", "reconciliation"),
                skill_hint=metadata.get("skill_hint", "")
            )
        driver.close()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_all_neo4j_tasks():
    """Get all tasks from Neo4j with their current status."""
    try:
        from neo4j import GraphDatabase

        uri = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
        user = os.environ.get('NEO4J_USER', 'neo4j')

        if 'NEO4J_AUTH' in os.environ:
            password = os.environ.get('NEO4J_AUTH', '').split('://')[1].split('@')[0]
        else:
            password = os.environ.get('NEO4J_PASSWORD', 'password')

        driver = GraphDatabase.driver(uri, auth=(user, password))
        with driver.session() as session:
            result = session.run("""
                MATCH (t:Task)
                WHERE t.task_id IS NOT NULL
                RETURN t.task_id as task_id, t.agent as agent, t.status as status
            """)
            tasks = {}
            for record in result:
                task_id = record["task_id"]
                tasks[task_id] = {
                    "agent": record["agent"],
                    "status": record["status"]
                }
        driver.close()
        return tasks
    except Exception as e:
        print(f"Warning: Could not connect to Neo4j: {e}", file=sys.stderr)
        return {}


def get_filesystem_task_status(task_file):
    """Determine the actual status of a task from its filename."""
    filename = task_file.name

    if ".done.md" in filename:
        if ".failed." in filename:
            return "failed"
        elif ".completed." in filename:
            return "completed"
        else:
            return "completed"
    elif ".executing" in filename:
        return "executing"
    elif ".pending.md" in filename:
        return "pending"
    elif ".dispatched" in filename:
        return "executing"
    else:
        return "pending"


def find_stale_neo4j_tasks(agent_filter=None):
    """Find Neo4j tasks whose status doesn't match filesystem reality."""
    stale = []
    neo4j_tasks = get_all_neo4j_tasks()

    if not neo4j_tasks:
        return stale

    agents = [agent_filter] if agent_filter else VALID_AGENTS

    # Build filesystem task map
    fs_tasks = {}
    for agent in agents:
        tasks_dir = AGENTS_DIR / agent / "tasks"
        if not tasks_dir.exists():
            continue

        for task_file in tasks_dir.glob("*.md"):
            if task_file.name == ".gitkeep":
                continue

            metadata = parse_task_file(task_file)
            task_id = metadata.get("task_id", "")
            if task_id:
                fs_tasks[task_id] = {
                    "filepath": str(task_file),
                    "filename": task_file.name,
                    "status": get_filesystem_task_status(task_file),
                    "agent": agent
                }

    # Check for status mismatches
    for task_id, neo4j_info in neo4j_tasks.items():
        if task_id in fs_tasks:
            fs_status = fs_tasks[task_id]["status"]
            neo4j_status = neo4j_info["status"]

            # Status mapping: Neo4j uses different values sometimes
            if fs_status == "completed" and neo4j_status not in ("completed", "done"):
                stale.append({
                    "task_id": task_id,
                    "agent": neo4j_info["agent"],
                    "neo4j_status": neo4j_status,
                    "fs_status": fs_status,
                    "fs_filename": fs_tasks[task_id]["filename"],
                    "fix": f"update to '{fs_status}'"
                })
            elif fs_status == "failed" and neo4j_status != "failed":
                stale.append({
                    "task_id": task_id,
                    "agent": neo4j_info["agent"],
                    "neo4j_status": neo4j_status,
                    "fs_status": fs_status,
                    "fs_filename": fs_tasks[task_id]["filename"],
                    "fix": f"update to '{fs_status}'"
                })
        elif neo4j_info["status"] in ("pending", "executing"):
            # Neo4j thinks it's active but no filesystem task exists
            stale.append({
                "task_id": task_id,
                "agent": neo4j_info["agent"],
                "neo4j_status": neo4j_info,
                "fs_status": "missing",
                "fs_filename": "NOT FOUND",
                "fix": "mark as failed (orphaned)"
            })

    return stale


def update_neo4j_task_status(task_id, new_status, dry_run=False):
    """Update a Neo4j task's status."""
    if dry_run:
        return {"dry_run": True}

    try:
        from neo4j import GraphDatabase

        uri = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
        user = os.environ.get('NEO4J_USER', 'neo4j')

        if 'NEO4J_AUTH' in os.environ:
            password = os.environ.get('NEO4J_AUTH', '').split('://')[1].split('@')[0]
        else:
            password = os.environ.get('NEO4J_PASSWORD', 'password')

        driver = GraphDatabase.driver(uri, auth=(user, password))
        with driver.session() as session:
            query = """
                MATCH (t:Task {task_id: $task_id})
                SET t.status = $status,
                    t.completed_at = datetime()
                RETURN t.task_id as id
            """
            session.run(query, task_id=task_id, status=new_status)
        driver.close()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Reconcile orphaned filesystem tasks with Neo4j")
    parser.add_argument("--agent", help="Only reconcile specific agent")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    parser.add_argument("--fix", action="store_true", help="Actually create missing Neo4j nodes")
    args = parser.parse_args()

    print("=" * 70)
    print("NEO4J TASK RECONCILIATION (Bidirectional)")
    print("=" * 70)
    print()

    # Direction 1: Filesystem -> Neo4j (missing nodes)
    print("Direction 1: Filesystem -> Neo4j (missing nodes)")
    print("-" * 70)
    orphaned = find_orphaned_tasks(args.agent)

    if orphaned:
        print(f"Found {len(orphaned)} filesystem task(s) missing from Neo4j:")
        by_agent = {}
        for task in orphaned:
            agent = task.get("agent", "unknown")
            if agent not in by_agent:
                by_agent[agent] = []
            by_agent[agent].append(task)

        for agent, tasks in sorted(by_agent.items()):
            print(f"  [{agent}] {len(tasks)} task(s)")
            for task in tasks:
                print(f"    - {task.get('title', task.get('filename', 'unknown'))[:60]}")
                print(f"      ID: {task.get('task_id', 'NO ID')}")
    else:
        print("✓ No filesystem tasks missing from Neo4j")
    print()

    # Direction 2: Neo4j -> Filesystem (stale status)
    print("Direction 2: Neo4j -> Filesystem (stale status)")
    print("-" * 70)
    stale = find_stale_neo4j_tasks(args.agent)

    if stale:
        print(f"Found {len(stale)} Neo4j task(s) with stale status:")
        by_agent = {}
        for task in stale:
            agent = task.get("agent", "unknown")
            if agent not in by_agent:
                by_agent[agent] = []
            by_agent[agent].append(task)

        for agent, tasks in sorted(by_agent.items()):
            print(f"  [{agent}] {len(tasks)} task(s)")
            for task in tasks:
                fs = task.get('fs_filename', 'unknown')[:40]
                print(f"    - {task.get('task_id', 'NO ID')}")
                print(f"      Neo4j: {task.get('neo4j_status')} -> Filesystem: {task.get('fs_status')} ({fs})")
                print(f"      Action: {task.get('fix')}")
    else:
        print("✓ No stale Neo4j task statuses")
    print()

    # Exit early if no issues found
    total_issues = len(orphaned) + len(stale)
    if total_issues == 0:
        print("=" * 70)
        print("✓ Neo4j and filesystem are fully in sync.")
        print("=" * 70)
        return 0

    # Dry run mode
    if args.dry_run:
        print("=" * 70)
        print(f"[DRY-RUN] Would fix {total_issues} issue(s)")
        print("=" * 70)
        return 0

    if not args.fix:
        print("=" * 70)
        print(f"Found {total_issues} issue(s). Use --fix to apply corrections.")
        print("=" * 70)
        return 1

    # Apply fixes
    print("=" * 70)
    print("APPLYING FIXES")
    print("=" * 70)
    print()

    results = {"fs_to_neo4j": {"created": 0, "failed": 0},
               "neo4j_status": {"updated": 0, "failed": 0}}

    # Fix Direction 1: Create missing Neo4j nodes
    if orphaned:
        print("Direction 1: Creating missing Neo4j nodes...")
        for task in orphaned:
            result = create_neo4j_task(task, dry_run=False)
            if result.get("success") or result.get("dry_run"):
                results["fs_to_neo4j"]["created"] += 1
                print(f"  ✓ Created: {task.get('task_id')}")
            else:
                results["fs_to_neo4j"]["failed"] += 1
                error = result.get('error', 'Unknown error')
                print(f"  ✗ Failed: {task.get('task_id')} - {error}")
        print()

    # Fix Direction 2: Update stale Neo4j statuses
    if stale:
        print("Direction 2: Updating stale Neo4j statuses...")
        for task in stale:
            task_id = task.get("task_id")
            if task.get("fs_status") == "missing":
                new_status = "failed"
            else:
                new_status = task.get("fs_status", "failed")

            result = update_neo4j_task_status(task_id, new_status, dry_run=False)
            if result.get("success") or result.get("dry_run"):
                results["neo4j_status"]["updated"] += 1
                print(f"  ✓ Updated: {task_id} -> {new_status}")
            else:
                results["neo4j_status"]["failed"] += 1
                error = result.get('error', 'Unknown error')
                print(f"  ✗ Failed: {task_id} - {error}")
        print()

    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Direction 1 (FS->Neo4j): {results['fs_to_neo4j']['created']} created, {results['fs_to_neo4j']['failed']} failed")
    print(f"Direction 2 (Neo4j status): {results['neo4j_status']['updated']} updated, {results['neo4j_status']['failed']} failed")
    print("=" * 70)

    return 0 if (results['fs_to_neo4j']['failed'] == 0 and results['neo4j_status']['failed'] == 0) else 1

    if args.dry_run:
        print("[DRY-RUN] Would create Neo4j nodes for the above tasks.")
        return 0

    if not args.fix:
        print("Use --fix to create missing Neo4j nodes.")
        return 1

    # Fix: Create missing Neo4j nodes
    print("Creating missing Neo4j nodes...")
    print("-" * 70)

    results = {"created": 0, "failed": 0}
    for task in orphaned:
        result = create_neo4j_task(task, dry_run=False)
        if result.get("success"):
            results["created"] += 1
            print(f"✓ Created: {task.get('task_id')} - {task.get('title', '?')[:50]}")
        else:
            results["failed"] += 1
            error = result.get('error', 'Unknown error')
            print(f"✗ Failed: {task.get('task_id')} - {error}")

    print()
    print("=" * 70)
    print(f"SUMMARY: {results['created']} created, {results['failed']} failed")
    print("=" * 70)

    return 0 if results['failed'] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
