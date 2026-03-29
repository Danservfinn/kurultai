#!/usr/bin/env python3
"""
launch_daily_reflection_pipeline.py — Create reflection pipeline as a task dependency graph.

Replaces the bash orchestration in hourly_reflection.sh with Neo4j tasks
that have DEPENDS_ON relationships. Executors claim tasks as they become PENDING.

Runs once daily. Pipeline ID uses date only (e.g., reflection-2026-03-20).

Migration path:
    1. Run with --shadow alongside hourly_reflection.sh to validate task graph
    2. Wire one phase to real executors (Phase C, follow-up plan)
    3. Retire hourly_reflection.sh (Phase D, follow-up plan)

Cron entry (disabled by default):
    # python3 /Users/kublai/.openclaw/agents/main/scripts/launch_daily_reflection_pipeline.py

Usage:
    python3 launch_daily_reflection_pipeline.py                   # Create pipeline tasks
    python3 launch_daily_reflection_pipeline.py --dry-run         # Print task graph without creating
    python3 launch_daily_reflection_pipeline.py --status <pid>    # Check pipeline status
    python3 launch_daily_reflection_pipeline.py --cleanup <pid>   # Remove all tasks for a pipeline
    python3 launch_daily_reflection_pipeline.py --shadow          # Shadow mode (non-claimable tasks)
    python3 launch_daily_reflection_pipeline.py --force           # Override dedup guard
    python3 launch_daily_reflection_pipeline.py --launch          # Manual launch from UI (alias for --force)
"""

import os
import sys
import argparse
import logging
from datetime import datetime, timezone
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_v2_core import TaskStore
from agents_config import AGENTS

logger = logging.getLogger(__name__)


def _check_existing_pipeline(store: TaskStore, date_prefix: str) -> Optional[str]:
    """Return pipeline_id if a pipeline already exists for this date."""
    with store.driver.session() as s:
        result = s.run("""
            MATCH (t:Task)
            WHERE t.pipeline_id STARTS WITH $prefix
            RETURN t.pipeline_id AS pid
            LIMIT 1
        """, prefix=f"reflection-{date_prefix}")
        rec = result.single()
        return rec["pid"] if rec else None


def launch_pipeline(store: TaskStore, dry_run: bool = False,
                    shadow: bool = False, force: bool = False) -> dict:
    """Create all pipeline tasks with dependency edges.

    Returns dict mapping phase names to lists of task_ids.
    """
    now = datetime.now(timezone.utc)
    pid = f"reflection-{now.strftime('%Y-%m-%d')}"

    # Dedup guard
    if not force and not dry_run:
        existing = _check_existing_pipeline(store, now.strftime('%Y-%m-%d'))
        if existing:
            print(f"Pipeline already exists for today: {existing}")
            print("Use --force to override.")
            return {"pipeline_id": existing, "skipped": True}

    source = "pipeline-shadow" if shadow else "pipeline"

    def agent_name(agent):
        return f"shadow-{agent}" if shadow else agent

    task_ids = {"pipeline_id": pid}

    # Phase 1: Reflections — 6 tasks, no dependencies (PENDING immediately)
    reflect_ids = []
    for agent in AGENTS:
        tid = f"{pid}-reflect-{agent}"
        if not dry_run:
            store.create_task(
                task_id=tid,
                title=f"Protocol reflection: {agent}",
                prompt=f"python3 meta_reflection.py --protocol --agent {agent}",
                assigned_to=agent_name(agent),
                priority="high",
                domain="reflection",
                source=source,
                pipeline_id=pid,
                phase=1,
                timeout_s=240,  # Increased from 120s to 240s - ogedei reflection tasks take 121-205s (avg 153s)
                max_retries=1,
            )
        reflect_ids.append(tid)
    task_ids["reflect"] = reflect_ids

    # Phase 2: Reviews — 6 tasks, each BLOCKED on ALL 6 reflections
    review_ids = []
    for agent in AGENTS:
        tid = f"{pid}-review-{agent}"
        if not dry_run:
            store.create_task(
                task_id=tid,
                title=f"Self-review: {agent}",
                prompt=f"python3 review-with-fallback.py --agent {agent} --timeout 300",
                assigned_to=agent_name(agent),
                priority="high",
                domain="review",
                source=source,
                depends_on=reflect_ids,
                pipeline_id=pid,
                phase=2,
                timeout_s=600,
                max_retries=1,
            )
        review_ids.append(tid)
    task_ids["review"] = review_ids

    # Phase 3: Proposals — 6 tasks, BLOCKED on all reviews
    propose_ids = []
    for agent in AGENTS:
        tid = f"{pid}-propose-{agent}"
        if not dry_run:
            store.create_task(
                task_id=tid,
                title=f"Write proposal: {agent}",
                prompt=f"python3 proposal_generator.py --agent {agent} --pipeline {pid}",
                assigned_to=agent_name(agent),
                priority="high",
                domain="proposal",
                source=source,
                depends_on=review_ids,
                pipeline_id=pid,
                phase=3,
                timeout_s=300,
                max_retries=1,
            )
        propose_ids.append(tid)
    task_ids["propose"] = propose_ids

    # Phase 3.5: Voting launcher sentinel — runs AFTER all proposals complete
    # Deferred: creates voting tasks only after proposals are verified (quality-gated)
    sentinel_tid = f"{pid}-launch-voting"
    if not dry_run:
        store.create_task(
            task_id=sentinel_tid,
            title="Launch voting phase (deferred)",
            prompt=f"python3 launch_voting_phase.py --pipeline {pid}",
            assigned_to=agent_name("ogedei"),
            priority="high",
            domain="pipeline-control",
            source=source,
            depends_on=propose_ids,   # BLOCKED until all 6 proposals complete
            pipeline_id=pid,
            phase=3.5,
            timeout_s=120,
            max_retries=1,
        )
    task_ids["voting_launcher"] = [sentinel_tid]

    return task_ids


def get_pipeline_status(store: TaskStore, pipeline_id: str) -> dict:
    """Query status of all tasks in a pipeline run."""
    with store.driver.session() as s:
        result = s.run("""
            MATCH (t:Task {pipeline_id: $pid})
            RETURN t.task_id AS id, t.title AS title, t.status AS status,
                   t.phase AS phase, t.assigned_to AS agent
            ORDER BY t.phase, t.created_at
        """, pid=pipeline_id)
        tasks = [dict(r) for r in result]

    summary = {}
    for t in tasks:
        status = t["status"]
        summary[status] = summary.get(status, 0) + 1

    return {"pipeline_id": pipeline_id, "tasks": tasks, "summary": summary}


def cleanup_pipeline(store: TaskStore, pipeline_id: str) -> int:
    """Delete all tasks in a pipeline run. Returns count deleted."""
    with store.driver.session() as s:
        result = s.run("""
            MATCH (t:Task {pipeline_id: $pid})
            WITH t
            OPTIONAL MATCH (t)-[r1:HAS_OUTPUT]->(o:TaskOutput)
            OPTIONAL MATCH (t)-[r2:HAS_FAILURE]->(f:FailureReport)
            DETACH DELETE t, o, f
            RETURN count(t) AS deleted
        """, pid=pipeline_id)
        rec = result.single()
        return rec["deleted"] if rec else 0


def main():
    parser = argparse.ArgumentParser(description="Launch reflection pipeline as task graph")
    parser.add_argument("--dry-run", action="store_true", help="Print task graph without creating")
    parser.add_argument("--status", metavar="PIPELINE_ID", help="Check pipeline status")
    parser.add_argument("--cleanup", metavar="PIPELINE_ID", help="Remove all tasks for a pipeline run")
    parser.add_argument("--shadow", action="store_true",
                        help="Shadow mode: create non-claimable pipeline tasks alongside bash orchestrator")
    parser.add_argument("--force", action="store_true", help="Override dedup guard")
    parser.add_argument("--launch", action="store_true",
                        help="Manual launch from UI (alias for --force with clearer intent)")
    args = parser.parse_args()

    store = TaskStore()
    try:
        if args.status:
            status = get_pipeline_status(store, args.status)
            print(f"Pipeline: {status['pipeline_id']}")
            print(f"Summary: {status['summary']}")
            for t in status['tasks']:
                print(f"  [{t['status']:9s}] Phase {t['phase']}: {t['title']} ({t['agent']})")
            if not status['tasks']:
                print("  (no tasks found)")

        elif args.cleanup:
            deleted = cleanup_pipeline(store, args.cleanup)
            print(f"Cleaned up pipeline {args.cleanup}: {deleted} tasks deleted")

        else:
            # Treat --launch the same as --force (override dedup guard)
            force = args.force or args.launch
            result = launch_pipeline(store, dry_run=args.dry_run,
                                     shadow=args.shadow, force=force)
            if result.get("skipped"):
                return

            pid = result["pipeline_id"]
            total = sum(len(v) for k, v in result.items() if k != "pipeline_id")
            mode = "DRY RUN" if args.dry_run else ("SHADOW" if args.shadow else "CREATED")
            print(f"[{mode}] Pipeline {pid}: {total} tasks")
            for phase_name, ids in result.items():
                if phase_name == "pipeline_id":
                    continue
                print(f"  {phase_name}: {len(ids)} tasks")
                for tid in ids:
                    print(f"    {tid}")
    finally:
        store.close()


if __name__ == "__main__":
    main()
