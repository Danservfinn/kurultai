#!/usr/bin/env python3
"""
Gate Timeout Watchdog - Check and escalate stuck completion gates.

Integrates with the watchdog-gather.sh system to periodically check for
gates stuck in pending-gate state beyond the timeout threshold.

This script is called by the watchdog system to ensure no gates remain
stuck indefinitely.

Usage (via cron/launchd):
    python3 gate-timeout-watchdog.py [--escalate] [--dry-run]

Design: ~/.openclaw/agents/mongke/workspace/completion-gate-design-2026-03-08.md
Task: gate-timeout-008
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add scripts directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from gate_timeouts import (
        GATE_PENDING_TIMEOUT,
        GATE_PENDING_TIMEOUT_HOURS,
        check_pending_gate_timeouts,
        escalate_stuck_gates,
        log_timeout_event,
        TIMEOUT_LOG_DIR
    )
    GATE_TIMEOUTS_AVAILABLE = True
except ImportError:
    GATE_TIMEOUTS_AVAILABLE = False
    print("[ERROR] gate_timeouts module not available")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Watchdog for stuck completion gates"
    )
    parser.add_argument("--escalate", action="store_true",
                        help="Escalate stuck gates to kublai")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would happen without taking action")
    parser.add_argument("--json", action="store_true",
                        help="Output results in JSON format")

    args = parser.parse_args()

    # Check for stuck gates
    stuck_gates = check_pending_gate_timeouts()

    # Prepare results
    results = {
        "timestamp": datetime.now().isoformat(),
        "timeout_hours": GATE_PENDING_TIMEOUT_HOURS,
        "stuck_count": len(stuck_gates),
        "stuck_gates": [
            {
                "task_id": g.get("task_id"),
                "age_hours": round(g.get("age_hours", 0), 1),
                "agent": g.get("agent"),
                "has_blocked": g.get("has_blocked", False),
                "followups_complete": g.get("followups_complete", False)
            }
            for g in stuck_gates
        ],
        "escalated": False,
        "escalated_count": 0
    }

    # Escalate if requested and there are stuck gates
    if args.escalate and stuck_gates:
        count, task_path = escalate_stuck_gates(stuck_gates, dry_run=args.dry_run)

        results["escalated"] = True
        results["escalated_count"] = count

        if task_path:
            results["escalation_task"] = str(task_path)

    # Log the watchdog check
    log_timeout_event("watchdog_check", {
        "stuck_count": len(stuck_gates),
        "escalated": results["escalated"],
        "escalated_count": results["escalated_count"],
        "dry_run": args.dry_run
    })

    # Output
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        if args.dry_run:
            print("[DRY RUN] Gate Timeout Watchdog")
        else:
            print("=== GATE TIMEOUT WATCHDOG ===")

        print(f"Timeout: {GATE_PENDING_TIMEOUT_HOURS}h")
        print(f"Stuck Gates: {len(stuck_gates)}")

        if stuck_gates:
            print()
            for gate in stuck_gates:
                status_symbol = "⚠"
                if gate.get("followups_complete"):
                    status_symbol = "✓"
                elif gate.get("has_blocked"):
                    status_symbol = "⛔"

                print(f"  {status_symbol} {gate.get('task_id', 'unknown')}")
                print(f"     Age: {gate.get('age_hours', 0):.1f}h | Agent: {gate.get('agent', 'unknown')}")

        if args.escalate:
            if args.dry_run:
                print()
                print(f"[DRY RUN] Would escalate {results['escalated_count']} gates to kublai")
            elif results["escalated_count"] > 0:
                print()
                print(f"✓ Escalated {results['escalated_count']} gates to kublai")
                if results.get("escalation_task"):
                    print(f"  Task: {results['escalation_task']}")

        # Exit code based on whether stuck gates were found
        # This allows the watchdog to detect problems
        if stuck_gates and not args.escalate:
            return 1  # Warning: stuck gates found but not escalated
        return 0  # OK: no stuck gates or successfully escalated


if __name__ == "__main__":
    sys.exit(main())
