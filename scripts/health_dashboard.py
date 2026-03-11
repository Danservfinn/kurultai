#!/usr/bin/env python3
"""
health_dashboard.py — Consolidated system health monitoring.

Single function system_health() that queries Neo4j for:
- Task stats (total, completed, failed, pending by agent)
- Completion rate
- Bottlenecks
- Agent workload balance
- Pending hypotheses
- Queue depth (filesystem)
- Dispatch health (task-watcher status)

Replaces the need for separate agent-manager.py --status cron job.

Usage:
    python3 health_dashboard.py
    python3 health_dashboard.py --json
"""

import argparse
import glob
import json
import os
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agents_config import AGENTS
from kurultai_paths import AGENTS_DIR as _AGENTS_DIR, SPAWN_QUEUE as _SPAWN_QUEUE

AGENT_DIR = str(_AGENTS_DIR)
SPAWN_QUEUE = str(_SPAWN_QUEUE)


def get_queue_depths():
    """Get pending task counts from filesystem."""
    queues = {}
    for agent in AGENTS:
        task_dir = f"{AGENT_DIR}/{agent}/tasks"
        if not os.path.isdir(task_dir):
            queues[agent] = 0
            continue
        pending = 0
        for pattern in ["high-*.md", "normal-*.md", "low-*.md"]:
            for f in glob.glob(f"{task_dir}/{pattern}"):
                if not f.endswith(".executing.md") and not f.endswith(".done.md"):
                    pending += 1
        queues[agent] = pending
    return queues


def get_spawn_queue_depth():
    """Get number of ready items in spawn queue."""
    try:
        from json_state import locked_json_read
        data = locked_json_read(SPAWN_QUEUE, default={'spawns': []})
        return len([s for s in data.get('spawns', []) if s.get('status') == 'ready'])
    except Exception:
        return 0


def get_dispatch_health():
    """Check if task-watcher.py daemon is running."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "task-watcher.py"],
            capture_output=True, text=True, timeout=5
        )
        running = result.returncode == 0
        pids = result.stdout.strip().split('\n') if running else []
        return {"running": running, "pids": pids}
    except Exception:
        return {"running": False, "pids": []}


def system_health():
    """Generate complete system health report."""
    report = {
        "timestamp": datetime.now().isoformat(),
        "status": "healthy",
        "issues": [],
    }

    # Queue depths from filesystem
    queues = get_queue_depths()
    total_pending = sum(queues.values())
    report["queues"] = {
        "by_agent": queues,
        "total_pending": total_pending,
        "spawn_pending": get_spawn_queue_depth(),
    }

    # Dispatch health
    dispatch = get_dispatch_health()
    report["dispatch"] = dispatch
    if not dispatch["running"]:
        report["issues"].append("task-watcher.py daemon not running")
        report["status"] = "degraded"

    # Neo4j data
    try:
        from neo4j_task_tracker import get_tracker
        tracker = get_tracker()

        # Task summary (1h)
        report["tasks_1h"] = tracker.get_hourly_summary(hours=1)

        # Completion rate (24h)
        report["completion_rate_24h"] = tracker.get_completion_rate(hours=24)

        # Bottlenecks
        report["bottlenecks"] = tracker.get_bottlenecks(hours=24)

        # Agent workload (7d)
        report["workload_7d"] = tracker.get_agent_workload(days=7)

        # Hypotheses
        report["hypotheses"] = tracker.validate_hypotheses()

        # Rules
        rules = tracker.get_active_rules()
        report["active_rules"] = len(rules)

        report["neo4j"] = "connected"
    except Exception as e:
        report["neo4j"] = f"error: {e}"
        report["issues"].append(f"Neo4j unavailable: {e}")
        report["status"] = "degraded"

    # Overall status
    if total_pending > 20:
        report["issues"].append(f"High queue backlog: {total_pending} pending")
        report["status"] = "degraded"

    if len(report["issues"]) == 0:
        report["status"] = "healthy"

    return report


def main():
    parser = argparse.ArgumentParser(description="System Health Dashboard")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    health = system_health()

    if args.json:
        print(json.dumps(health, indent=2, default=str))
    else:
        print(f"=== System Health: {health['status'].upper()} ===")
        print(f"Timestamp: {health['timestamp']}")
        print()

        print(f"Queue: {health['queues']['total_pending']} pending, "
              f"{health['queues']['spawn_pending']} spawn")
        for agent, count in health['queues']['by_agent'].items():
            if count > 0:
                print(f"  {agent}: {count}")

        print(f"\nDispatch: {'running' if health['dispatch']['running'] else 'NOT RUNNING'}")
        print(f"Neo4j: {health.get('neo4j', 'unknown')}")

        if health.get('completion_rate_24h'):
            cr = health['completion_rate_24h']
            print(f"\nCompletion rate (24h): {cr.get('success_rate', 'N/A')}% "
                  f"({cr.get('success', 0)}/{cr.get('total', 0)})")

        if health.get('hypotheses'):
            h = health['hypotheses']
            print(f"\nHypotheses: {h.get('pending', 0)} pending, "
                  f"{h.get('validated', 0)} validated, "
                  f"{h.get('expired', 0)} expired")

        if health.get('bottlenecks'):
            print(f"\nBottlenecks:")
            for b in health['bottlenecks'][:5]:
                print(f"  {b.get('agent')}/{b.get('label')}: {b.get('retries')} retries")

        if health['issues']:
            print(f"\nIssues:")
            for issue in health['issues']:
                print(f"  - {issue}")


if __name__ == "__main__":
    main()
