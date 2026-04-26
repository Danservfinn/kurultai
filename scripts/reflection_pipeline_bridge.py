#!/usr/bin/env python3
"""
reflection_pipeline_bridge.py — Bridge between Neo4j pipeline and proposal extractor.

The old hourly_reflection.sh wrote reflection-status.json and collected reflection
markdown files into agents/main/reflections/. When it was deprecated, the new Neo4j
pipeline task system never gained this capability, leaving the proposal extractor in
a permanent skip loop.

This script bridges the gap:
  1. Queries Neo4j for pipeline days where all reflect/propose tasks are COMPLETED
  2. Copies propose result files from agent workspace dirs → agents/main/reflections/
  3. Updates reflection-status.json with content_complete status

Run as a cron job before the extractor:
  50 */4 * * * python3 reflection_pipeline_bridge.py >> ~/.openclaw/logs/reflection-bridge.log 2>&1
  0  */4 * * * python3 reflection_proposal_extractor.py --extract >> ...

Usage:
    python3 reflection_pipeline_bridge.py              # Normal run
    python3 reflection_pipeline_bridge.py --dry-run    # Preview without writing
    python3 reflection_pipeline_bridge.py --force      # Force update even if already bridged
    python3 reflection_pipeline_bridge.py --days 7     # Look back N days (default 7)
"""

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


def get_driver():
    """Get Neo4j driver connection."""
    from neo4j import GraphDatabase
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD")
    return GraphDatabase.driver(uri, auth=(user, password))


def get_completed_pipeline_days(driver, lookback_days=7):
    """
    Query Neo4j for pipeline days where all reflect/propose tasks are COMPLETED.

    Returns list of (pipeline_date, agent_name, propose_task_id) tuples.
    """
    query = """
    MATCH (p:PipelineDay)-[:HAS_TASK]->(t:Task)
    WHERE t.type IN ['daily_reflection', 'performance_review', 'write_proposal', 'vote_on_proposal']
      AND t.status = 'COMPLETED'
      AND p.date >= date() - duration('P{days}D')
    WITH p, t.agent as agent_name
    MATCH (p)-[:HAS_TASK]->(propose:Task)
    WHERE propose.type = 'write_proposal'
      AND propose.status = 'COMPLETED'
      AND propose.agent = agent_name
    RETURN DISTINCT p.date as pipeline_date, agent_name, propose.id as propose_task_id
    ORDER BY p.date DESC, agent_name
    """.format(days=lookback_days)

    with driver.session() as session:
        result = session.run(query)
        return [(record["pipeline_date"], record["agent_name"], record["propose_task_id"])
                for record in result]


def find_propose_result_file(agent_name, propose_task_id):
    """
    Find the propose result file in agent workspace.

    Looks for: ~/.openclaw/agents/{agent}/tasks/{task_id}*.md
    """
    agent_dir = Path(f"~/.openclaw/agents/{agent_name}").expanduser()
    tasks_dir = agent_dir / "tasks"

    if not tasks_dir.exists():
        return None

    # Look for task files matching the task_id
    for task_file in tasks_dir.glob(f"*{propose_task_id}*.md"):
        # Check if it's a completed task with results
        content = task_file.read_text()
        if "**Outcome:**" in content or "## Proposal" in content:
            return task_file

    return None


def copy_to_reflections(agent_name, pipeline_date, task_file, reflections_dir, dry_run=False):
    """Copy propose result file to reflections directory."""
    reflections_dir.mkdir(parents=True, exist_ok=True)

    # Target filename: {agent}_{pipeline_date}.md
    target_filename = f"{agent_name}_{pipeline_date}.md"
    target_path = reflections_dir / target_filename

    if target_path.exists():
        return False  # Already copied

    if not dry_run:
        shutil.copy2(task_file, target_path)
    return True


def update_reflection_status(pipeline_date, reflections_dir, dry_run=False):
    """Update reflection-status.json with content_complete status."""
    status_file = reflections_dir / "reflection-status.json"

    if status_file.exists():
        with open(status_file) as f:
            status = json.load(f)
    else:
        status = {}

    date_key = str(pipeline_date)

    if date_key not in status:
        status[date_key] = {}

    status[date_key]["content_complete"] = True
    status[date_key]["bridged_at"] = datetime.now(timezone.utc).isoformat()

    if not dry_run:
        with open(status_file, "w") as f:
            json.dump(status, f, indent=2)

    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--force", action="store_true", help="Force update even if already bridged")
    parser.add_argument("--days", type=int, default=7, help="Look back N days (default 7)")
    args = parser.parse_args()

    reflections_dir = Path("agents/main/reflections").expanduser()
    reflections_dir.mkdir(parents=True, exist_ok=True)

    driver = get_driver()

    try:
        completed_days = get_completed_pipeline_days(driver, args.days)

        if not completed_days:
            print(f"[{datetime.now().isoformat()}] No completed pipeline days found in lookback period.")
            return 0

        copied_count = 0
        for pipeline_date, agent_name, propose_task_id in completed_days:
            print(f"[{datetime.now().isoformat()}] Processing {agent_name} for {pipeline_date} (task: {propose_task_id})")

            # Find propose result file
            task_file = find_propose_result_file(agent_name, propose_task_id)
            if not task_file:
                print(f"[{datetime.now().isoformat()}]  ⚠ No propose result file found for {agent_name}/{propose_task_id}")
                continue

            # Copy to reflections
            if copy_to_reflections(agent_name, pipeline_date, task_file, reflections_dir, args.dry_run):
                print(f"[{datetime.now().isoformat()}]  ✓ Copied {task_file.name} → {agent_name}_{pipeline_date}.md")
                copied_count += 1
            else:
                print(f"[{datetime.now().isoformat()}]  - Already exists: {agent_name}_{pipeline_date}.md")

        # Update reflection-status.json
        if copied_count > 0:
            update_reflection_status(pipeline_date, reflections_dir, args.dry_run)
            print(f"[{datetime.now().isoformat()}] Updated reflection-status.json for {pipeline_date}")

        print(f"[{datetime.now().isoformat()}] Bridge complete: {copied_count} files copied")

    finally:
        driver.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
