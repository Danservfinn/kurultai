#!/usr/bin/env python3
"""
task-consistency-reconciler.py — Detect and fix Neo4j / disk / ledger inconsistencies.

Three checks:
  1. Neo4j WORKING but disk has .done.md → update Neo4j status
  2. EXECUTING ledger event with no terminal event → cross-reference Neo4j
  3. Stale .executing.md with no WORKING Neo4j task → rename to .orphaned.md

Dry-run by default. Pass --fix to apply corrections.
Run every 30 min from watchdog-gather.sh or standalone.
"""

import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from neo4j_v2_core import TaskStore
from kurultai_paths import AGENTS_DIR, DISPATCH_AGENTS, TASK_LEDGER

logger = logging.getLogger("reconciler")

LOOKBACK_HOURS = 6
TERMINAL_EVENTS = {"COMPLETED", "FAILED", "EXECUTOR_CRASH", "LEASE_CANCEL", "CANCELLED"}


# ---------------------------------------------------------------------------
# Check 1: Neo4j WORKING but disk COMPLETED
# ---------------------------------------------------------------------------

def check_working_but_done(store: TaskStore, fix: bool) -> list[dict]:
    """Find tasks that are WORKING in Neo4j but have .done.md on disk."""
    issues = []

    # Get all WORKING tasks from Neo4j
    working_tasks = {}
    for agent in DISPATCH_AGENTS:
        for task in store.get_agent_tasks(agent, status="WORKING", limit=100):
            working_tasks[task["task_id"]] = task

    if not working_tasks:
        return issues

    # Scan disk for .done.md files matching WORKING task_ids
    for agent in DISPATCH_AGENTS:
        tasks_dir = AGENTS_DIR / agent / "tasks"
        if not tasks_dir.exists():
            continue
        for f in tasks_dir.iterdir():
            if not f.name.endswith(".done.md") and not f.name.endswith(".verified.done.md"):
                continue
            # Extract task_id from filename (e.g., "high-123-abc.done.md")
            task_id = f.name.split(".")[0]
            if task_id in working_tasks:
                issue = {
                    "check": "working_but_done",
                    "task_id": task_id,
                    "agent": agent,
                    "file": str(f),
                    "neo4j_status": "WORKING",
                    "disk_status": "done",
                }
                issues.append(issue)

                if fix:
                    try:
                        task = working_tasks[task_id]
                        epoch = task.get("claim_epoch", 0)
                        # Read result from disk
                        content = f.read_text()[:5000]
                        ok, reason = store.complete_task(
                            task_id, epoch,
                            text=content,
                            problem="Reconciled from disk",
                            solution="Task completed on disk but Neo4j was not updated",
                            rationale="Consistency reconciler fix",
                            output_lines=content.count("\n"),
                        )
                        issue["fixed"] = ok
                        issue["fix_reason"] = reason
                        if ok:
                            logger.info(f"Fixed: {task_id} → COMPLETED (from disk)")
                        else:
                            logger.warning(f"Fix failed for {task_id}: {reason}")
                    except Exception as e:
                        issue["fixed"] = False
                        issue["fix_error"] = str(e)
                        logger.error(f"Fix error for {task_id}: {e}")

    return issues


# ---------------------------------------------------------------------------
# Check 2: EXECUTING with no terminal event
# ---------------------------------------------------------------------------

def check_orphaned_executing(store: TaskStore) -> list[dict]:
    """Find EXECUTING ledger events from last 6 hours with no terminal event."""
    issues = []

    if not TASK_LEDGER.exists():
        return issues

    cutoff = datetime.now() - timedelta(hours=LOOKBACK_HOURS)
    executing = {}  # task_id -> event
    terminal = set()  # task_ids with terminal events

    try:
        with open(TASK_LEDGER, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue

                ts_str = ev.get("timestamp", ev.get("ts", ""))
                if not ts_str:
                    continue
                try:
                    ev_time = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    if hasattr(ev_time, 'tzinfo') and ev_time.tzinfo:
                        ev_time = ev_time.replace(tzinfo=None)
                    if ev_time < cutoff:
                        continue
                except (ValueError, TypeError):
                    continue

                event_type = ev.get("event", "")
                task_id = ev.get("task_id", "")

                if event_type == "EXECUTING" and task_id:
                    executing[task_id] = ev
                elif event_type in TERMINAL_EVENTS and task_id:
                    terminal.add(task_id)
    except Exception as e:
        logger.error(f"Ledger read error: {e}")
        return issues

    # Find EXECUTING without terminal
    for task_id, ev in executing.items():
        if task_id in terminal:
            continue

        # Cross-reference Neo4j
        try:
            task = store.get_task(task_id)
            neo4j_status = task.get("status", "UNKNOWN") if task else "NOT_FOUND"
        except Exception:
            neo4j_status = "QUERY_ERROR"

        issues.append({
            "check": "orphaned_executing",
            "task_id": task_id,
            "agent": ev.get("agent", "unknown"),
            "executing_since": ev.get("timestamp", ev.get("ts", "")),
            "neo4j_status": neo4j_status,
        })

    return issues


# ---------------------------------------------------------------------------
# Check 3: Stale .executing.md with no WORKING task
# ---------------------------------------------------------------------------

def check_stale_executing_files(store: TaskStore, fix: bool) -> list[dict]:
    """Find .executing.md files with no corresponding WORKING task in Neo4j."""
    issues = []

    # Collect all WORKING task_ids
    working_ids = set()
    for agent in DISPATCH_AGENTS:
        for task in store.get_agent_tasks(agent, status="WORKING", limit=100):
            working_ids.add(task["task_id"])

    # Scan for .executing.md files
    for agent in DISPATCH_AGENTS:
        tasks_dir = AGENTS_DIR / agent / "tasks"
        if not tasks_dir.exists():
            continue
        for f in tasks_dir.iterdir():
            if not f.name.endswith(".executing.md"):
                continue
            task_id = f.name.replace(".executing.md", "")
            if task_id not in working_ids:
                issue = {
                    "check": "stale_executing_file",
                    "task_id": task_id,
                    "agent": agent,
                    "file": str(f),
                }
                issues.append(issue)

                if fix:
                    try:
                        orphaned_name = f.name.replace(".executing.md", ".orphaned.md")
                        f.rename(f.parent / orphaned_name)
                        issue["fixed"] = True
                        logger.info(f"Renamed: {f.name} → {orphaned_name}")
                    except Exception as e:
                        issue["fixed"] = False
                        issue["fix_error"] = str(e)

    return issues


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Task consistency reconciler")
    parser.add_argument("--fix", action="store_true",
                        help="Apply fixes (default: dry-run)")
    parser.add_argument("--json", action="store_true",
                        help="Output JSON report")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    store = TaskStore()
    start = time.time()

    try:
        report = {
            "timestamp": datetime.now().isoformat(),
            "mode": "fix" if args.fix else "dry-run",
            "issues": [],
        }

        # Check 1
        issues1 = check_working_but_done(store, fix=args.fix)
        report["issues"].extend(issues1)

        # Check 2
        issues2 = check_orphaned_executing(store)
        report["issues"].extend(issues2)

        # Check 3
        issues3 = check_stale_executing_files(store, fix=args.fix)
        report["issues"].extend(issues3)

        elapsed = time.time() - start
        report["elapsed_s"] = round(elapsed, 2)
        report["total_issues"] = len(report["issues"])

        if args.json:
            print(json.dumps(report, indent=2))
        else:
            mode = "FIX" if args.fix else "DRY-RUN"
            print(f"[{mode}] Reconciler found {len(report['issues'])} issues in {elapsed:.1f}s")
            for issue in report["issues"]:
                check = issue["check"]
                tid = issue.get("task_id", "?")
                agent = issue.get("agent", "?")
                fixed = issue.get("fixed", "n/a")
                print(f"  [{check}] {tid} (agent={agent}) fixed={fixed}")

    finally:
        store.close()


if __name__ == "__main__":
    main()
