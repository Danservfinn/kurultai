#!/usr/bin/env python3
"""
Gate Metrics Dashboard - Display completion gate metrics summary.

Usage:
    python3 gate-metrics.py
    python3 gate-metrics.py --json
    python3 gate-metrics.py --watch

Design: ~/.openclaw/agents/mongke/workspace/completion-gate-design-2026-03-08.md
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Add scripts directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kurultai_paths import AGENTS_DIR

# Gate audit log directory
GATE_AUDITS_DIR = Path.home() / ".openclaw" / "agents" / "main" / "logs" / "gate-audits"


def get_pending_gates():
    """Count pending gates by scanning filesystem."""
    pending = 0
    blocked = 0
    gates = []

    for agent_dir in AGENTS_DIR.iterdir():
        if not agent_dir.is_dir() or agent_dir.name.startswith('.'):
            continue
        tasks_dir = agent_dir / "tasks"
        if not tasks_dir.exists():
            continue

        for f in tasks_dir.glob("*.pending-gate.md"):
            pending += 1
            # Get age
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            age_hours = (datetime.now() - mtime).total_seconds() / 3600
            gates.append({
                "file": f.name,
                "agent": agent_dir.name,
                "age_hours": round(age_hours, 1)
            })

        for f in tasks_dir.glob("*.gate-blocked.md"):
            blocked += 1

    return pending, blocked, gates


def get_audit_metrics():
    """Calculate metrics from audit JSON files."""
    if not GATE_AUDITS_DIR.exists():
        return {
            "recent_audits": 0,
            "passed": 0,
            "total_completion": 0,
            "avg_completion": 0,
            "pass_rate": 0
        }

    import time
    cutoff = time.time() - (24 * 3600)  # 24 hours ago

    recent_audits = []
    total_completion = 0
    passed = 0

    for audit_file in GATE_AUDITS_DIR.glob("*.json"):
        try:
            mtime = audit_file.stat().st_mtime
            if mtime > cutoff:
                with open(audit_file) as f:
                    data = json.load(f)
                recent_audits.append(data)
                total_completion += data.get("completion_percentage", 100)
                if data.get("can_complete"):
                    passed += 1
        except Exception:
            continue

    if recent_audits:
        return {
            "recent_audits": len(recent_audits),
            "passed": passed,
            "total_completion": total_completion,
            "avg_completion": round(total_completion / len(recent_audits), 1),
            "pass_rate": round(100.0 * passed / len(recent_audits), 1)
        }

    return {
        "recent_audits": 0,
        "passed": 0,
        "total_completion": 0,
        "avg_completion": 0,
        "pass_rate": 0
    }


def get_followup_metrics():
    """Calculate follow-up task metrics."""
    followups = 0
    followups_completed = 0

    for agent_dir in AGENTS_DIR.iterdir():
        if not agent_dir.is_dir() or agent_dir.name.startswith('.'):
            continue
        tasks_dir = agent_dir / "tasks"
        if not tasks_dir.exists():
            continue

        for task_file in tasks_dir.glob("*.md"):
            try:
                with open(task_file) as f:
                    content = f.read(1000)
                if "parent_task:" in content:
                    followups += 1
                    if ".done." in task_file.name:
                        followups_completed += 1
            except Exception:
                continue

    return {
        "total_followups": followups,
        "completed_followups": followups_completed,
        "completion_rate": round(100.0 * followups_completed / max(followups, 1), 1)
    }


def get_all_metrics():
    """Get all gate metrics."""
    pending, blocked, pending_gates = get_pending_gates()
    audit_metrics = get_audit_metrics()
    followup_metrics = get_followup_metrics()

    return {
        "timestamp": datetime.now().isoformat(),
        "pending_gates": pending,
        "blocked_gates": blocked,
        "recent_audits_24h": audit_metrics["recent_audits"],
        "passed_audits_24h": audit_metrics["passed"],
        "pass_rate_24h": audit_metrics["pass_rate"],
        "avg_completion_24h": audit_metrics["avg_completion"],
        "total_followups": followup_metrics["total_followups"],
        "completed_followups": followup_metrics["completed_followups"],
        "followup_completion_rate": followup_metrics["completion_rate"],
        "pending_gates_detail": pending_gates[:10]  # First 10
    }


def print_dashboard(metrics: dict):
    """Print formatted metrics dashboard."""
    print()
    print("=" * 65)
    print("          COMPLETION GATE METRICS")
    print("=" * 65)
    print()

    # Status section
    print("GATE STATUS")
    print("-" * 40)
    print(f"  Pending Gates:       {metrics['pending_gates']}")
    print(f"  Blocked Gates:       {metrics['blocked_gates']}")
    print()

    # Audit metrics
    print("AUDIT METRICS (24h)")
    print("-" * 40)
    print(f"  Recent Audits:       {metrics['recent_audits_24h']}")
    print(f"  Passed Audits:       {metrics['passed_audits_24h']}")
    print(f"  Pass Rate:           {metrics['pass_rate_24h']}%")
    print(f"  Avg Completion:      {metrics['avg_completion_24h']}%")
    print()

    # Follow-up metrics
    print("FOLLOW-UP TASKS")
    print("-" * 40)
    print(f"  Total Follow-ups:    {metrics['total_followups']}")
    print(f"  Completed:           {metrics['completed_followups']}")
    print(f"  Completion Rate:     {metrics['followup_completion_rate']}%")
    print()

    # Pending gates detail
    if metrics['pending_gates_detail']:
        print("PENDING GATES (oldest first)")
        print("-" * 40)
        for gate in sorted(metrics['pending_gates_detail'], key=lambda x: x['age_hours'], reverse=True)[:5]:
            age_str = f"{gate['age_hours']:.1f}h"
            if gate['age_hours'] > 24:
                age_str = f"{gate['age_hours']/24:.1f}d ⚠ STALE"
            print(f"  {gate['file'][:40]:<40} {gate['agent']}/{age_str}")
        print()

    print("=" * 65)


def check_stale_gates(hours: int = 24) -> list:
    """Check for gates stuck for too long."""
    pending, blocked, pending_gates = get_pending_gates()
    stale = [g for g in pending_gates if g['age_hours'] > hours]
    return stale


def main():
    parser = argparse.ArgumentParser(
        description="Display completion gate metrics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 gate-metrics.py
  python3 gate-metrics.py --json
  python3 gate-metrics.py --watch
  python3 gate-metrics.py --check-stale
        """
    )
    parser.add_argument("--json", action="store_true",
                        help="Output metrics as JSON")
    parser.add_argument("--watch", action="store_true",
                        help="Continuously refresh metrics every 30s")
    parser.add_argument("--check-stale", action="store_true",
                        help="Check for gates stuck > 24 hours")
    parser.add_argument("--stale-hours", type=int, default=24,
                        help="Hours threshold for stale check (default: 24)")

    args = parser.parse_args()

    if args.check_stale:
        stale = check_stale_gates(args.stale_hours)
        if not stale:
            print(f"✓ No gates stuck > {args.stale_hours}h")
            return 0
        else:
            print(f"⚠ Found {len(stale)} stale gates:")
            for gate in sorted(stale, key=lambda x: x['age_hours'], reverse=True):
                print(f"  {gate['file']}: {gate['age_hours']:.1f}h ({gate['agent']})")
            return 1

    try:
        while True:
            metrics = get_all_metrics()

            if args.json:
                print(json.dumps(metrics, indent=2))
            else:
                # Clear screen for watch mode
                if args.watch:
                    os.system('clear' if os.name == 'posix' else 'cls')
                print_dashboard(metrics)

            if not args.watch:
                break

            time.sleep(30)

        return 0

    except KeyboardInterrupt:
        print("\nExiting...")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
