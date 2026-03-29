#!/usr/bin/env python3
"""
fix_stale_pending_files.py — Rename task files for COMPLETED tasks

Problem: Tick telemetry shows 31 "pending" tasks, but Neo4j shows 0 PENDING.
Root cause: Task completion workflow doesn't rename .md files to terminal states.

This script:
1. Queries Neo4j for COMPLETED tasks
2. Checks if the original task file exists (unrenamed)
3. Renames to .done.md or .verified.done.md based on report file presence

Usage:
    python3 fix_stale_pending_files.py [--dry-run] [--agent AGENT]
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import neo4j
    from neo4j_v2_core import TaskStore
except ImportError as e:
    print(f"ERROR: Missing dependency: {e}")
    sys.exit(1)

AGENTS = ("kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei", "tolui")
AGENT_BASE = Path.home() / ".openclaw" / "agents"


def get_terminal_tasks(agent: str = None) -> list:
    """Get COMPLETED and FAILED tasks from Neo4j."""
    # Read Neo4j credentials
    creds_file = Path.home() / ".openclaw" / "credentials" / "neo4j.env"
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_pass = os.getenv("NEO4J_PASSWORD")

    if creds_file.exists():
        with open(creds_file) as f:
            for line in f:
                if line.startswith("NEO4J_URI="):
                    neo4j_uri = line.strip().split("=", 1)[1]
                elif line.startswith("NEO4J_USER="):
                    neo4j_user = line.strip().split("=", 1)[1]
                elif line.startswith("NEO4J_PASSWORD="):
                    neo4j_pass = line.strip().split("=", 1)[1]

    if not neo4j_pass:
        raise EnvironmentError("NEO4J_PASSWORD environment variable not set")

    driver = neo4j.GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_pass))

    try:
        with driver.session() as session:
            if agent:
                result = session.run("""
                    MATCH (t:Task)
                    WHERE t.agent = $agent AND t.status IN ["COMPLETED", "FAILED"]
                    RETURN t.task_id as task_id, t.agent as agent, t.verified as verified, t.status as status
                    ORDER BY t.updated DESC
                """, agent=agent)
            else:
                result = session.run("""
                    MATCH (t:Task)
                    WHERE t.status IN ["COMPLETED", "FAILED"]
                    RETURN t.task_id as task_id, t.agent as agent, t.verified as verified, t.status as status
                    ORDER BY t.updated DESC
                """)

            tasks = []
            for record in result:
                tasks.append({
                    "task_id": record["task_id"],
                    "agent": record["agent"],
                    "verified": record.get("verified", False),
                    "status": record["status"],
                })

            return tasks
    finally:
        driver.close()


def rename_task_file(task: dict, dry_run: bool = False) -> dict:
    """Rename a task file to its terminal state."""
    task_id = task["task_id"]
    agent = task.get("agent")
    verified = task.get("verified", False)
    status = task.get("status", "COMPLETED")

    if not agent:
        return {"task_id": task_id, "status": "skip", "reason": "no_agent"}

    # Search for task file in all agent directories (routing can move tasks)
    task_file = None
    task_file_location = None
    for test_agent in AGENTS:
        test_file = AGENT_BASE / test_agent / "tasks" / f"{task_id}.md"
        if test_file.exists():
            task_file = test_file
            task_file_location = test_agent
            break

    if not task_file:
        return {"task_id": task_id, "status": "skip", "reason": "file_not_found"}

    # Check for result file in executing agent's workspace (from Neo4j agent field)
    workspace_dir = AGENT_BASE / agent / "workspace"

    # FAILED tasks get .failed suffix
    if status == "FAILED":
        target_name = f"{task_id}.failed.md"
        target_file = task_file.parent / target_name
        if target_file.exists():
            return {"task_id": task_id, "status": "skip", "reason": "target_exists"}

        # Perform rename for FAILED tasks
        if dry_run:
            print(f"  Would rename: {task_file.name} -> {target_name}")
            return {"task_id": task_id, "status": "dry_run", "target": target_name}

        try:
            task_file.rename(target_file)
            print(f"  Renamed: {task_file.name} -> {target_name}")
            return {"task_id": task_id, "status": "renamed", "target": target_name}
        except Exception as e:
            print(f"  ERROR renaming {task_id}: {e}")
            return {"task_id": task_id, "status": "error", "error": str(e)}
    else:
        # COMPLETED tasks get .done suffix (with optional .verified)
        # Check for result file to determine terminal state
        result_file = workspace_dir / f"{task_id}.result.md"

        # Check for verification file (in the location where task file was found)
        verified_file = task_file.parent / f"{task_id}.verified.done.md"

        if verified_file.exists():
            return {"task_id": task_id, "status": "skip", "reason": "already_verified"}

        # Determine target filename
        if verified and result_file.exists():
            # Check if verification exists
            verification_file = workspace_dir / f"{task_id}.verification.md"
            if verification_file.exists():
                target_name = f"{task_id}.verified.done.md"
            else:
                target_name = f"{task_id}.done.md"
        elif result_file.exists():
            target_name = f"{task_id}.done.md"
        else:
            return {"task_id": task_id, "status": "skip", "reason": "no_result_file"}

        target_file = task_file.parent / target_name

        if target_file.exists():
            return {"task_id": task_id, "status": "skip", "reason": "target_exists"}

        # Perform rename for COMPLETED tasks
        if dry_run:
            print(f"  Would rename: {task_file.name} -> {target_name}")
            return {"task_id": task_id, "status": "dry_run", "target": target_name}

        try:
            task_file.rename(target_file)
            print(f"  Renamed: {task_file.name} -> {target_name}")
            return {"task_id": task_id, "status": "renamed", "target": target_name}
        except Exception as e:
            print(f"  ERROR renaming {task_id}: {e}")
            return {"task_id": task_id, "status": "error", "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Fix stale pending task files")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without executing")
    parser.add_argument("--agent", choices=AGENTS, help="Only process specific agent")
    args = parser.parse_args()

    print("Fetching terminal tasks from Neo4j (COMPLETED + FAILED)...")
    terminal_tasks = get_terminal_tasks(args.agent)
    print(f"Found {len(terminal_tasks)} terminal tasks")

    if args.agent:
        print(f"Filtering for agent: {args.agent}")

    print("\nProcessing task files...")
    results = {
        "renamed": 0,
        "skip": 0,
        "error": 0,
        "dry_run": 0,
    }

    for task in terminal_tasks:
        result = rename_task_file(task, dry_run=args.dry_run)
        results[result["status"]] = results.get(result["status"], 0) + 1

    print(f"\n=== Summary ===")
    print(f"Renamed: {results.get('renamed', 0)}")
    print(f"Skipped: {results.get('skip', 0)}")
    print(f"Errors: {results.get('error', 0)}")
    if args.dry_run:
        print(f"Dry run: {results.get('dry_run', 0)}")


if __name__ == "__main__":
    main()
