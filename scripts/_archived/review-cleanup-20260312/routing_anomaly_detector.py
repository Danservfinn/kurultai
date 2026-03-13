#!/usr/bin/env python3
"""
routing_anomaly_detector.py — Detect routing and execution anomalies.

Scans for patterns that indicate problems in the routing pipeline:
- Fake completions: tasks marked done with minimal/no output
- Stuck tasks: tasks in .executing state beyond timeout thresholds
- Rapid-fire completions: suspiciously fast execution times
- Task drift: tasks routed but never executed

Usage:
    python3 routing_anomaly_detector.py              # Human-readable report
    python3 routing_anomaly_detector.py --json       # JSON output
    python3 routing_anomaly_detector.py --hours 2    # Look back 2 hours
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kurultai_paths import AGENTS_DIR, LOGS_DIR, TASK_LEDGER
from agents_config import AGENTS

# Thresholds for anomaly detection
FAKE_COMPLETION_MIN_CHARS = 200  # Below this = suspicious (matched to 4-line minimum)
FAKE_COMPLETION_MIN_LINES = 4    # Below this = suspicious
RAPID_COMPLETION_SEC = 30        # Completing in < 30s = suspicious
STUCK_EXECUTING_HOURS = 1        # In .executing > 1h = stuck


def read_task_ledger(hours=24):
    """Read task events from ledger within time window."""
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


def scan_fake_completions(hours=24):
    """Scan for fake completions — tasks done with minimal output."""
    fake_completions = []
    total_completed = 0

    for agent in AGENTS:
        task_dir = f"{AGENTS_DIR}/{agent}/tasks"
        if not os.path.isdir(task_dir):
            continue

        cutoff = datetime.now() - timedelta(hours=hours)

        for fname in os.listdir(task_dir):
            if not fname.endswith(".done.md"):
                continue

            fpath = os.path.join(task_dir, fname)
            try:
                stat = os.stat(fpath)
                mtime = datetime.fromtimestamp(stat.st_mtime)

                if mtime < cutoff:
                    continue

                total_completed += 1

                with open(fpath) as f:
                    content = f.read()

                char_count = len(content.strip())
                line_count = len([l for l in content.splitlines() if l.strip()])

                # Check for fake completion patterns
                is_fake = False
                reasons = []

                # Primary checks: content size
                if char_count < FAKE_COMPLETION_MIN_CHARS:
                    is_fake = True
                    reasons.append(f"too_short:{char_count}chars")

                if line_count < FAKE_COMPLETION_MIN_LINES:
                    is_fake = True
                    reasons.append(f"too_few_lines:{line_count}")

                # Secondary check: no_output marker ONLY if content is also too small
                # (files named no_output but with valid content are NOT fake)
                if ("no_output" in fname or "no output" in content.lower()) and char_count < 200:
                    if not is_fake:  # Only add if not already flagged
                        is_fake = True
                        reasons.append("no_output_marker")

                # Check for empty completion patterns
                if "done." in content.lower() and len(content.strip()) < 100:
                    is_fake = True
                    reasons.append("empty_done_pattern")

                if is_fake:
                    task_title = fname.replace(".done.md", "").replace(".md", "")
                    fake_completions.append({
                        "agent": agent,
                        "task_file": fname,
                        "task_title": task_title[:80],
                        "char_count": char_count,
                        "line_count": line_count,
                        "reasons": reasons,
                        "mtime": mtime.isoformat(),
                    })

            except Exception:
                continue

    return fake_completions, total_completed


def scan_stuck_tasks():
    """Scan for tasks stuck in .executing state."""
    stuck_tasks = []
    now = datetime.now()

    for agent in AGENTS:
        task_dir = f"{AGENTS_DIR}/{agent}/tasks"
        if not os.path.isdir(task_dir):
            continue

        for fname in os.listdir(task_dir):
            if not fname.endswith(".executing"):
                continue

            fpath = os.path.join(task_dir, fname)
            try:
                stat = os.stat(fpath)
                mtime = datetime.fromtimestamp(stat.st_mtime)
                age_hours = (now - mtime).total_seconds() / 3600

                if age_hours > STUCK_EXECUTING_HOURS:
                    # Extract task ID from filename
                    task_id = fname.replace(".executing", "")
                    stuck_tasks.append({
                        "agent": agent,
                        "task_file": fname,
                        "task_id": task_id[:80],
                        "age_hours": round(age_hours, 1),
                        "mtime": mtime.isoformat(),
                    })
            except Exception:
                continue

    return stuck_tasks


def analyze_rapid_completions(events):
    """Analyze completion times for suspiciously fast executions."""
    rapid_completions = []

    # Build task timeline
    task_events = defaultdict(list)
    for ev in events:
        task_id = ev.get("task_id")
        if task_id:
            task_events[task_id].append(ev)

    for task_id, evs in task_events.items():
        started = next((e for e in evs if e.get("event") == "STARTED"), None)
        completed = next((e for e in evs if e.get("event") in ("COMPLETED", "FAILED")), None)

        if started and completed:
            start_ts = started.get("_ts")
            comp_ts = completed.get("_ts")
            if start_ts and comp_ts:
                duration_sec = (comp_ts - start_ts).total_seconds()
                if 0 < duration_sec < RAPID_COMPLETION_SEC:
                    rapid_completions.append({
                        "task_id": task_id[:50],
                        "agent": completed.get("agent", "unknown"),
                        "duration_sec": round(duration_sec, 1),
                        "event": completed.get("event"),
                    })

    return rapid_completions


def detect_task_drift(events):
    """Detect tasks that were routed but never executed."""
    # Track QUEUED tasks without corresponding STARTED
    queued_tasks = {}
    started_tasks = set()

    for ev in events:
        task_id = ev.get("task_id")
        if not task_id:
            continue

        if ev.get("event") == "QUEUED":
            agent = ev.get("agent", "")
            task_summary = ev.get("task_summary", "")[:80]
            queued_tasks[task_id] = {"agent": agent, "summary": task_summary, "ts": ev.get("_ts")}
        elif ev.get("event") == "STARTED":
            started_tasks.add(task_id)

    # Find queued but never started
    drifted = []
    for task_id, info in queued_tasks.items():
        if task_id not in started_tasks:
            # Check if it's been more than 10 minutes
            if info.get("ts"):
                age_min = (datetime.now() - info["ts"]).total_seconds() / 60
                if age_min > 10:
                    drifted.append({
                        "task_id": task_id[:50],
                        "agent": info["agent"],
                        "summary": info["summary"],
                        "age_min": round(age_min),
                    })

    return drifted


def generate_report(hours=24):
    """Generate full anomaly detection report."""
    events = read_task_ledger(hours)
    fake_completions, total_completed = scan_fake_completions(hours)
    stuck_tasks = scan_stuck_tasks()
    rapid_completions = analyze_rapid_completions(events)
    task_drift = detect_task_drift(events)

    report = {
        "period_hours": hours,
        "generated_at": datetime.now().isoformat(),
        "thresholds": {
            "fake_min_chars": FAKE_COMPLETION_MIN_CHARS,
            "fake_min_lines": FAKE_COMPLETION_MIN_LINES,
            "rapid_sec": RAPID_COMPLETION_SEC,
            "stuck_hours": STUCK_EXECUTING_HOURS,
        },
        "fake_completions": {
            "count": len(fake_completions),
            "total_completed": total_completed,
            "by_agent": _count_by_agent(fake_completions),
            "examples": fake_completions[:10],
        },
        "stuck_tasks": {
            "count": len(stuck_tasks),
            "by_agent": _count_by_agent(stuck_tasks),
            "examples": stuck_tasks[:10],
        },
        "rapid_completions": {
            "count": len(rapid_completions),
            "examples": rapid_completions[:10],
        },
        "task_drift": {
            "count": len(task_drift),
            "examples": task_drift[:10],
        },
    }

    # Generate alerts
    alerts = []

    # Fake completion alert
    fake_count = len(fake_completions)
    if total_completed > 0:
        fake_pct = fake_count / total_completed * 100
        if fake_pct > 20:
            alerts.append({
                "severity": "HIGH",
                "type": "FAKE_COMPLETIONS",
                "message": f"{fake_count}/{total_completed} ({fake_pct:.0f}%) completions are fake (too short/no output)"
            })
        elif fake_pct > 5:
            alerts.append({
                "severity": "MEDIUM",
                "type": "FAKE_COMPLETIONS",
                "message": f"{fake_count}/{total_completed} ({fake_pct:.0f}%) completions are fake"
            })

    # Stuck tasks alert
    if stuck_tasks:
        alerts.append({
            "severity": "HIGH",
            "type": "STUCK_TASKS",
            "message": f"{len(stuck_tasks)} task(s) stuck in .executing state > {STUCK_EXECUTING_HOURS}h"
        })

    # Rapid completions alert
    if len(rapid_completions) > 5:
        alerts.append({
            "severity": "MEDIUM",
            "type": "RAPID_COMPLETIONS",
            "message": f"{len(rapid_completions)} tasks completed in < {RAPID_COMPLETION_SEC}s (suspicious)"
        })

    # Task drift alert
    if task_drift:
        alerts.append({
            "severity": "MEDIUM",
            "type": "TASK_DRIFT",
            "message": f"{len(task_drift)} routed tasks never started (dispatch may be stalled)"
        })

    report["alerts"] = alerts

    return report


def _count_by_agent(items):
    """Count items by agent."""
    by_agent = defaultdict(int)
    for item in items:
        agent = item.get("agent", "unknown")
        by_agent[agent] += 1
    return dict(by_agent)


def format_report(report):
    """Format report as human-readable text."""
    lines = []
    lines.append(f"=== Routing Anomaly Detector ({report['period_hours']}h) ===")
    lines.append(f"Generated: {report['generated_at']}")
    lines.append("")

    # Alerts
    alerts = report.get("alerts", [])
    if alerts:
        lines.append("⚠️  ALERTS:")
        for alert in alerts:
            severity_icon = "🔴" if alert["severity"] == "HIGH" else "🟡"
            lines.append(f"  {severity_icon} [{alert['type']}] {alert['message']}")
        lines.append("")

    # Fake completions
    fake = report["fake_completions"]
    lines.append(f"Fake Completions: {fake['count']}/{fake['total_completed']}")
    if fake["by_agent"]:
        lines.append(f"  By agent: {fake['by_agent']}")
    if fake["examples"]:
        lines.append("  Examples:")
        for ex in fake["examples"][:5]:
            lines.append(f"    - {ex['agent']}: {ex['task_title']} ({', '.join(ex['reasons'])})")
    lines.append("")

    # Stuck tasks
    stuck = report["stuck_tasks"]
    lines.append(f"Stuck Tasks: {stuck['count']}")
    if stuck["by_agent"]:
        lines.append(f"  By agent: {stuck['by_agent']}")
    if stuck["examples"]:
        lines.append("  Examples:")
        for ex in stuck["examples"][:5]:
            lines.append(f"    - {ex['agent']}: {ex['task_id']} (age: {ex['age_hours']}h)")
    lines.append("")

    # Rapid completions
    rapid = report["rapid_completions"]
    if rapid["count"] > 0:
        lines.append(f"Rapid Completions: {rapid['count']} (< {report['thresholds']['rapid_sec']}s)")
        for ex in rapid["examples"][:5]:
            lines.append(f"  - {ex['task_id']} by {ex['agent']} in {ex['duration_sec']}s")
        lines.append("")

    # Task drift
    drift = report["task_drift"]
    if drift["count"] > 0:
        lines.append(f"Task Drift: {drift['count']} routed but never started")
        for ex in drift["examples"][:5]:
            lines.append(f"  - {ex['task_id']} to {ex['agent']} ({ex['age_min']}min ago)")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Routing Anomaly Detector")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--hours", type=int, default=24, help="Hours to look back (default: 24)")
    args = parser.parse_args()

    report = generate_report(hours=args.hours)

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(format_report(report))


if __name__ == "__main__":
    main()
