#!/usr/bin/env python3
"""
routing_outcomes.py — Join routing decisions with task ledger to compute outcomes.

Analyzes the relationship between routing decisions and actual task execution:
- time_to_start_sec: time from routing to execution
- time_to_complete_sec: time from routing to completion
- reassignment_count: how many times task was reassigned
- final_destination: where task actually completed

Usage:
    python3 routing_outcomes.py              # Human-readable report (24h)
    python3 routing_outcomes.py --hours 48   # Look back 48 hours
    python3 routing_outcomes.py --json       # JSON output
    python3 routing_outcomes.py --missed     # Show missed opportunities
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kurultai_paths import LOGS_DIR, TASK_LEDGER
from agents_config import AGENTS

ROUTING_LOG = str(LOGS_DIR / "routing-decisions.jsonl")


def read_routing_decisions(hours=24):
    """Read routing decisions from the last N hours."""
    if not os.path.exists(ROUTING_LOG):
        return []

    cutoff = datetime.now() - timedelta(hours=hours)
    decisions = []

    with open(ROUTING_LOG) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                ts = datetime.fromisoformat(entry["ts"])
                if ts >= cutoff:
                    entry["_ts"] = ts
                    decisions.append(entry)
            except (json.JSONDecodeError, KeyError, ValueError):
                continue

    return decisions


def read_task_events(hours=24):
    """Read task events from ledger within the time window."""
    if not os.path.exists(TASK_LEDGER):
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


def build_task_timeline(events):
    """Build a timeline of events per task_id.

    Returns dict of {task_id: {"events": [...], "agent": str, "title": str}}
    """
    tasks = defaultdict(lambda: {"events": [], "agent": None, "title": None})

    for ev in events:
        task_id = ev.get("task_id")
        if not task_id:
            continue

        tasks[task_id]["events"].append(ev)

        # Track agent assignments
        if ev.get("event") == "QUEUED":
            tasks[task_id]["agent"] = ev.get("agent")
            tasks[task_id]["title"] = ev.get("task_summary", "")[:100]

        # Track reassignments
        if ev.get("event") == "REASSIGNED":
            tasks[task_id]["agent"] = ev.get("new_agent")

    return dict(tasks)


def compute_outcomes(decisions, task_timeline):
    """Compute routing outcomes by matching decisions to task events.

    Returns list of outcome dicts with timing and reassignment info.
    """
    outcomes = []

    for decision in decisions:
        task_text = decision.get("task", "")
        dest_agent = decision.get("dest", "")
        decision_ts = decision.get("_ts")

        # Find matching task in timeline (by title prefix match and agent)
        matched_task = None
        for task_id, task_info in task_timeline.items():
            task_title = task_info.get("title", "")
            task_agent = task_info.get("agent", "")

            # Match by agent and title prefix
            if task_agent == dest_agent and task_title and task_text:
                if task_title[:50].lower() in task_text.lower() or task_text[:50].lower() in task_title.lower():
                    matched_task = task_info
                    matched_task["task_id"] = task_id
                    break

        if not matched_task:
            # No matching task found
            outcomes.append({
                "decision_ts": decision_ts.isoformat() if decision_ts else None,
                "task": task_text,
                "dest": dest_agent,
                "method": decision.get("method"),
                "matched": False,
                "time_to_start_sec": None,
                "time_to_complete_sec": None,
                "reassignment_count": 0,
                "final_destination": None,
            })
            continue

        # Compute timing from events
        events = matched_task.get("events", [])
        queued_ev = next((e for e in events if e.get("event") == "QUEUED"), None)
        started_ev = next((e for e in events if e.get("event") == "STARTED"), None)
        completed_ev = next((e for e in events if e.get("event") in ("COMPLETED", "FAILED")), None)

        time_to_start = None
        time_to_complete = None

        if queued_ev and started_ev:
            delta = started_ev["_ts"] - queued_ev["_ts"]
            time_to_start = delta.total_seconds()

        if queued_ev and completed_ev:
            delta = completed_ev["_ts"] - queued_ev["_ts"]
            time_to_complete = delta.total_seconds()

        # Count reassignments
        reassignments = sum(1 for e in events if e.get("event") == "REASSIGNED")

        # Find final destination
        final_dest = matched_task.get("agent")
        if completed_ev:
            final_dest = completed_ev.get("agent", final_dest)

        outcomes.append({
            "decision_ts": decision_ts.isoformat() if decision_ts else None,
            "task": task_text,
            "dest": dest_agent,
            "method": decision.get("method"),
            "matched": True,
            "task_id": matched_task.get("task_id"),
            "time_to_start_sec": time_to_start,
            "time_to_complete_sec": time_to_complete,
            "reassignment_count": reassignments,
            "final_destination": final_dest,
            "success": completed_ev.get("event") == "COMPLETED" if completed_ev else None,
            "alt_scores": decision.get("alt_scores", {}),
            "idle_agents": decision.get("idle_agents", []),
            "would_overflow": decision.get("would_overflow", False),
        })

    return outcomes


def analyze_missed_opportunities(decisions, outcomes):
    """Identify tasks routed to busy agents when idle alternatives existed."""
    missed = []

    for decision in decisions:
        dest = decision.get("dest")
        queue_info = decision.get("queue", {})
        idle_agents = decision.get("idle_agents", [])
        alt_scores = decision.get("alt_scores", {})

        if not queue_info or not idle_agents:
            continue

        dest_queue = queue_info.get(dest, 0)

        # Check if we routed to a busy agent when idle alternatives existed
        if dest_queue > 0 and idle_agents:
            # Find if any idle agent had a decent score
            idle_with_score = [(a, alt_scores.get(a, 0)) for a in idle_agents]
            idle_with_score.sort(key=lambda x: -x[1])

            if idle_with_score and idle_with_score[0][1] > 0:
                missed.append({
                    "task": decision.get("task", "")[:80],
                    "routed_to": dest,
                    "dest_queue": dest_queue,
                    "idle_alternatives": idle_with_score,
                    "method": decision.get("method"),
                    "ts": decision.get("ts"),
                })

    return missed


def generate_report(hours=24, show_missed=False):
    """Generate the full outcomes report."""
    decisions = read_routing_decisions(hours)
    events = read_task_events(hours)
    timeline = build_task_timeline(events)
    outcomes = compute_outcomes(decisions, timeline)

    report = {
        "period_hours": hours,
        "generated_at": datetime.now().isoformat(),
        "total_decisions": len(decisions),
        "matched_tasks": sum(1 for o in outcomes if o.get("matched")),
        "outcomes": outcomes,
    }

    # Aggregate stats
    started = [o for o in outcomes if o.get("time_to_start_sec") is not None]
    completed = [o for o in outcomes if o.get("time_to_complete_sec") is not None]

    if started:
        report["avg_time_to_start_sec"] = sum(o["time_to_start_sec"] for o in started) / len(started)
    if completed:
        report["avg_time_to_complete_sec"] = sum(o["time_to_complete_sec"] for o in completed) / len(completed)

    report["reassignment_count"] = sum(o.get("reassignment_count", 0) for o in outcomes)
    report["success_rate"] = (
        sum(1 for o in outcomes if o.get("success") is True) /
        max(1, sum(1 for o in outcomes if o.get("success") is not None))
    )

    # Missed opportunities
    if show_missed:
        report["missed_opportunities"] = analyze_missed_opportunities(decisions, outcomes)

    return report


def format_report(report):
    """Format report as human-readable text."""
    lines = []
    lines.append(f"=== Routing Outcomes ({report['period_hours']}h) ===")
    lines.append(f"Generated: {report['generated_at']}")
    lines.append(f"Total decisions: {report['total_decisions']}")
    lines.append(f"Matched tasks: {report['matched_tasks']}/{report['total_decisions']}")
    lines.append("")

    if "avg_time_to_start_sec" in report:
        lines.append(f"Avg time to start: {report['avg_time_to_start_sec']:.1f}s")
    if "avg_time_to_complete_sec" in report:
        lines.append(f"Avg time to complete: {report['avg_time_to_complete_sec']:.1f}s")

    lines.append(f"Total reassignments: {report['reassignment_count']}")
    lines.append(f"Success rate: {report['success_rate']:.1%}")
    lines.append("")

    # Missed opportunities
    missed = report.get("missed_opportunities", [])
    if missed:
        lines.append(f"=== Missed Opportunities ({len(missed)}) ===")
        for m in missed[:10]:
            lines.append(f"  Task: {m['task']}")
            lines.append(f"    Routed to: {m['routed_to']} (queue={m['dest_queue']})")
            lines.append(f"    Idle alternatives: {m['idle_alternatives']}")
            lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Routing Outcomes — analyze routing decisions vs actual outcomes")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--hours", type=int, default=24, help="Hours to look back (default: 24)")
    parser.add_argument("--missed", action="store_true", help="Include missed opportunities analysis")
    args = parser.parse_args()

    report = generate_report(hours=args.hours, show_missed=args.missed)

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(format_report(report))


if __name__ == "__main__":
    main()
