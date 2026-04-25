#!/usr/bin/env python3
"""
Build Outcomes Tracker — Measure build success rate, revision count, debug efficiency.

Analyzes temujin (developer) tasks to compute:
- First-attempt success rate: Did code work on first try?
- Revision count: Average number of revisions per task
- Debug efficiency: Time spent debugging vs. building

Usage:
    python3 build_outcomes_tracker.py           # Human-readable report (24h)
    python3 build_outcomes_tracker.py --days 7  # Look back 7 days
    python3 build_outcomes_tracker.py --json    # JSON output
    python3 build_outcomes_tracker.py --agent temujin  # Specific agent
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kurultai_paths import AGENTS_DIR, LOGS_DIR, TASK_LEDGER, agent_tasks_dir

# Gate audits directory
GATE_AUDITS_DIR = LOGS_DIR / "gate-audits"
COMPLETION_AUDIT = LOGS_DIR / "completion-audit.jsonl"


def extract_revision_count(filename: str) -> int:
    """Extract revision count from task filename.

    Examples:
        "task-name.md" -> 0 (no revision)
        "task-name.failed.revision-1.md" -> 1
        "task-name.failed.revision-2.md" -> 2
    """
    match = re.search(r'\.revision-(\d+)', filename)
    if match:
        return int(match.group(1))
    return 0


def read_task_ledger(hours=24):
    """Read task events from ledger within time window."""
    if not TASK_LEDGER.exists():
        return []

    cutoff = datetime.now() - timedelta(hours=hours)
    events = []

    with open(TASK_LEDGER) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                ts_str = entry.get("ts", "")
                if ts_str:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    if ts.tzinfo:
                        ts = ts.replace(tzinfo=None)
                    if ts >= cutoff:
                        entry["_ts"] = ts
                        events.append(entry)
            except (json.JSONDecodeError, KeyError, ValueError):
                continue

    return events


def build_task_timeline(events, agent="temujin"):
    """Build timeline of events per task_id for specific agent.

    Returns dict of {task_id: {"events": [...], "summary": str, "started": ts, "completed": ts}}
    """
    tasks = defaultdict(lambda: {"events": [], "summary": None, "started": None, "completed": None})

    for ev in events:
        if ev.get("agent") != agent:
            continue

        task_id = ev.get("task_id")
        if not task_id:
            continue

        tasks[task_id]["events"].append(ev)

        if ev.get("event") == "QUEUED":
            tasks[task_id]["summary"] = ev.get("task_summary", "")
        elif ev.get("event") == "STARTED":
            tasks[task_id]["started"] = ev.get("_ts")
        elif ev.get("event") in ("COMPLETED", "FAILED"):
            tasks[task_id]["completed"] = ev.get("_ts")

    return dict(tasks)


def scan_task_files_for_revisions(agent="temujin", hours=24):
    """Scan task files for revision patterns.

    Returns dict of {base_task_id: {"revisions": N, "final_status": str}}
    """
    agent_tasks_dir_path = agent_tasks_dir(agent)
    if not agent_tasks_dir_path.exists():
        return {}

    cutoff = datetime.now() - timedelta(hours=hours)
    results = {}

    # Scan for task files
    for task_file in agent_tasks_dir_path.glob("*.md"):
        # Skip archived and hidden files
        if task_file.name.startswith(".") or "archived" in str(task_file):
            continue

        # Check mtime
        try:
            mtime = datetime.fromtimestamp(task_file.stat().st_mtime)
            if mtime < cutoff:
                continue
        except Exception:
            continue

        filename = task_file.name

        # Extract base task ID (strip revision suffixes)
        base_name = re.sub(r'\.revision-\d+', '', filename)
        base_name = re.sub(r'\.(failed|done|executing|pending|verified|no_output)', '', base_name)

        # Count revisions
        revision_count = extract_revision_count(filename)

        # Determine status from filename
        if "failed" in filename.lower():
            status = "FAILED"
        elif "done" in filename.lower():
            status = "DONE"
        elif "executing" in filename.lower():
            status = "EXECUTING"
        elif "pending" in filename.lower():
            status = "PENDING"
        else:
            status = "UNKNOWN"

        if base_name not in results:
            results[base_name] = {"revisions": revision_count, "status": status, "files": []}
        else:
            # Track maximum revision count seen
            results[base_name]["revisions"] = max(results[base_name]["revisions"], revision_count)
            if status == "FAILED" or results[base_name]["status"] != "DONE":
                results[base_name]["status"] = status

        results[base_name]["files"].append(filename)

    return results


def compute_first_attempt_success(revision_data):
    """Compute first-attempt success rate.

    Returns: {
        "total_tasks": N,
        "first_attempt_success": M,
        "required_revisions": K,
        "first_attempt_rate": M/N
    }
    """
    total = len(revision_data)
    if total == 0:
        return {"total_tasks": 0, "first_attempt_success": 0, "required_revisions": 0, "first_attempt_rate": 0.0}

    first_attempt = sum(1 for t in revision_data.values() if t["revisions"] == 0 and t["status"] == "DONE")
    required_revisions = sum(1 for t in revision_data.values() if t["revisions"] > 0)

    return {
        "total_tasks": total,
        "first_attempt_success": first_attempt,
        "required_revisions": required_revisions,
        "first_attempt_rate": first_attempt / total if total > 0 else 0.0
    }


def compute_average_revisions(revision_data):
    """Compute average revision count for tasks that needed revisions.

    Only counts tasks that actually required revisions (revision_count > 0).
    """
    revised_tasks = [t["revisions"] for t in revision_data.values() if t["revisions"] > 0]

    if not revised_tasks:
        return {"count": 0, "avg_revisions": 0.0, "max_revisions": 0}

    return {
        "count": len(revised_tasks),
        "avg_revisions": sum(revised_tasks) / len(revised_tasks),
        "max_revisions": max(revised_tasks)
    }


def compute_task_duration(timeline):
    """Compute average task duration from queued to completed.

    Returns {"avg_seconds": N, "median_seconds": M, "count": K}
    """
    durations = []
    for task_id, data in timeline.items():
        if data.get("started") and data.get("completed"):
            duration = (data["completed"] - data["started"]).total_seconds()
            if 0 < duration < 7200:  # Filter out outliers (> 2 hours)
                durations.append(duration)

    if not durations:
        return {"avg_seconds": 0, "median_seconds": 0, "count": 0}

    durations.sort()
    median = durations[len(durations) // 2] if durations else 0

    return {
        "avg_seconds": sum(durations) / len(durations),
        "median_seconds": median,
        "count": len(durations)
    }


def generate_report(agent="temujin", hours=24):
    """Generate comprehensive build outcomes report."""
    events = read_task_ledger(hours)
    timeline = build_task_timeline(events, agent)
    revision_data = scan_task_files_for_revisions(agent, hours)

    first_attempt = compute_first_attempt_success(revision_data)
    revisions = compute_average_revisions(revision_data)
    durations = compute_task_duration(timeline)

    report = {
        "agent": agent,
        "period_hours": hours,
        "generated_at": datetime.now().isoformat(),
        "first_attempt_success": first_attempt,
        "revisions": revisions,
        "durations": durations,
    }

    return report


def format_report(report):
    """Format report as human-readable text."""
    lines = []
    lines.append(f"=== Build Outcomes Report: {report['agent']} ===")
    lines.append(f"Period: Last {report['period_hours']}h")
    lines.append(f"Generated: {report['generated_at']}")
    lines.append("")

    # First Attempt Success
    fa = report["first_attempt_success"]
    lines.append("## First Attempt Success Rate")
    lines.append(f"  Total tasks: {fa['total_tasks']}")
    lines.append(f"  First-attempt success: {fa['first_attempt_success']} ({fa['first_attempt_rate']:.1%})")
    lines.append(f"  Required revisions: {fa['required_revisions']}")
    lines.append("")

    # Revisions
    rev = report["revisions"]
    lines.append("## Revision Analysis")
    if rev["count"] > 0:
        lines.append(f"  Tasks needing revision: {rev['count']}")
        lines.append(f"  Avg revisions: {rev['avg_revisions']:.2f}")
        lines.append(f"  Max revisions: {rev['max_revisions']}")
    else:
        lines.append("  No revisions in this period")
    lines.append("")

    # Durations
    dur = report["durations"]
    lines.append("## Task Duration")
    if dur["count"] > 0:
        lines.append(f"  Completed tasks: {dur['count']}")
        lines.append(f"  Avg duration: {dur['avg_seconds'] / 60:.1f} minutes")
        lines.append(f"  Median duration: {dur['median_seconds'] / 60:.1f} minutes")
    else:
        lines.append("  No completed tasks in this period")
    lines.append("")

    # Quality Grade
    if fa["total_tasks"] > 0:
        grade = "A" if fa["first_attempt_rate"] >= 0.8 else "B" if fa["first_attempt_rate"] >= 0.6 else "C"
        lines.append(f"## Quality Grade: {grade}")
        if grade == "A":
            lines.append("  Excellent: >80% of tasks completed on first attempt")
        elif grade == "B":
            lines.append("  Good: 60-80% first-attempt success rate")
        else:
            lines.append("  Needs improvement: <60% first-attempt success rate")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Build Outcomes Tracker")
    parser.add_argument("--agent", default="temujin", help="Agent to analyze (default: temujin)")
    parser.add_argument("--days", type=int, help="Days to look back (overrides --hours)")
    parser.add_argument("--hours", type=int, default=24, help="Hours to look back (default: 24)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    # Convert days to hours if specified
    if args.days:
        hours = args.days * 24
    else:
        hours = args.hours

    report = generate_report(agent=args.agent, hours=hours)

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(format_report(report))


if __name__ == "__main__":
    main()
