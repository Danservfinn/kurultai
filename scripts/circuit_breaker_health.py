#!/usr/bin/env python3
"""
Circuit Breaker Health Monitor — Proactive state transitions.

The circuit breaker has a deadlock: OPEN agents need check_agent() to be
called to transition to HALF_OPEN, but OPEN agents aren't routed to, so
check_agent() never gets called.

This script proactively checks all agents and triggers timed transitions,
preventing the deadlock.

Usage:
    python3 scripts/circuit_breaker_health.py

Run via cron every 5 minutes:
    */5 * * * * cd ~/.openclaw/agents/main && python3 scripts/circuit_breaker_health.py >> logs/circuit-breaker-health.log 2>&1
"""

# Enable PEP 604 union syntax (X | Y) for Python < 3.10 compatibility
from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

# Add scripts to path for imports
sys.path.insert(0, str(Path(__file__).parent))

try:
    from circuit_breaker import AgentCircuitBreaker
    from kurultai_paths import VALID_AGENTS, LOGS_DIR
    from kurultai_ledger import read_ledger
except ImportError as e:
    print(f"[ERROR] Import failed: {e}")
    sys.exit(1)

# Log file for health checks
HEALTH_LOG = LOGS_DIR / "circuit-breaker-health.log"

# Urgent recovery: use shorter timeout when fleet is degraded
URGENT_RECOVERY_TIMEOUT = 600  # 10 minutes instead of 30
FLEET_FAILURE_THRESHOLD = 0.8  # 80% fleet failure rate triggers urgent mode


def log(message: str, urgent: bool = False):
    """Write to health log with timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    prefix = "🚨 " if urgent else ""
    log_line = f"[{timestamp}] {prefix}{message}\n"
    print(log_line, end="")
    with open(HEALTH_LOG, "a") as f:
        f.write(log_line)


def get_fleet_failure_rate(hours: int = 2) -> float:
    """Calculate fleet-wide task failure rate.

    Returns:
        Float from 0.0 to 1.0 representing failure rate.
    """
    try:
        events = read_ledger(hours=hours)
        if not events:
            return 0.0

        # Count completed vs failed
        completed = sum(1 for e in events if e.get("event") == "COMPLETED")
        failed = sum(1 for e in events if e.get("event") == "FAILED")
        total = completed + failed

        if total == 0:
            return 0.0

        return failed / total
    except Exception as e:
        log(f"Error calculating fleet failure rate: {e}")
        return 0.0


def check_all_agents(breaker: AgentCircuitBreaker, urgent_mode: bool = False) -> dict:
    """Check all agents and trigger timed transitions.

    Args:
        breaker: CircuitBreaker instance
        urgent_mode: If True, use URGENT_RECOVERY_TIMEOUT (10min) instead of RECOVERY_TIMEOUT (30min)

    Returns:
        Dict with agent statuses and any transitions made.
    """
    results = {
        "timestamp": time.time(),
        "urgent_mode": urgent_mode,
        "agents": {},
        "transitions": []
    }

    # Use shorter timeout in urgent mode
    recovery_timeout = URGENT_RECOVERY_TIMEOUT if urgent_mode else breaker.RECOVERY_TIMEOUT

    for agent in VALID_AGENTS:
        if agent == "tolui":  # Skip inactive agent
            continue

        try:
            state = breaker.check_agent(agent)
            results["agents"][agent] = state

            # Log OPEN agents for visibility
            if state["state"] == "OPEN":
                # Check if we should force a transition (deadlock breaker)
                agent_state = breaker.state["agents"].get(agent, {})
                since = agent_state.get("since", 0)
                if since > 0:
                    time_open = time.time() - since
                    urgency_note = " [URGENT MODE]" if urgent_mode else ""
                    log(f"{agent} is OPEN for {int(time_open)}s{urgency_note} — state: {state['detail']}")

                    # Force HALF_OPEN transition if past recovery timeout
                    # In urgent mode (fleet degraded), use 10min instead of 30min
                    if time_open > recovery_timeout:
                        reason = "urgent_deadlock_breaker" if urgent_mode else "deadlock_breaker"
                        log(f"⚠️  {agent} stuck in OPEN — forcing HALF_OPEN transition ({reason})", urgent=urgent_mode)
                        agent_state["state"] = "HALF_OPEN"
                        agent_state["since"] = time.time()
                        agent_state["half_open_trials"] = 0
                        breaker.save_state()
                        results["transitions"].append({
                            "agent": agent,
                            "from": "OPEN",
                            "to": "HALF_OPEN",
                            "reason": reason
                        })

            # Log HALF_OPEN agents approaching graceful recovery
            elif state["state"] == "HALF_OPEN":
                agent_state = breaker.state["agents"].get(agent, {})
                since = agent_state.get("since", 0)
                if since > 0:
                    time_in_state = time.time() - since
                    if time_in_state > breaker.HALF_OPEN_RECOVERY_TIMEOUT * 0.75:
                        log(f"ℹ️  {agent} in HALF_OPEN for {int(time_in_state)}s — graceful recovery in {int(breaker.HALF_OPEN_RECOVERY_TIMEOUT - time_in_state)}s")

        except Exception as e:
            log(f"ERROR checking {agent}: {e}")
            results["agents"][agent] = {"error": str(e)}

    return results


def main():
    """Run circuit breaker health check."""
    log("=" * 60)
    log("Circuit Breaker Health Check")

    # Check fleet health to determine if urgent mode is needed
    fleet_failure_rate = get_fleet_failure_rate(hours=2)
    urgent_mode = fleet_failure_rate >= FLEET_FAILURE_THRESHOLD

    if urgent_mode:
        log(f"🚨 URGENT MODE: Fleet failure rate {fleet_failure_rate:.1%} >= {FLEET_FAILURE_THRESHOLD:.0%} — using 10min recovery timeout", urgent=True)
    else:
        log(f"Fleet failure rate: {fleet_failure_rate:.1%} — normal mode")

    breaker = AgentCircuitBreaker()
    results = check_all_agents(breaker, urgent_mode=urgent_mode)

    # Summary
    open_count = sum(1 for s in results["agents"].values() if isinstance(s, dict) and s.get("state") == "OPEN")
    half_open_count = sum(1 for s in results["agents"].values() if isinstance(s, dict) and s.get("state") == "HALF_OPEN")
    closed_count = sum(1 for s in results["agents"].values() if isinstance(s, dict) and s.get("state") == "CLOSED")

    status_msg = f"Status: {open_count} OPEN, {half_open_count} HALF_OPEN, {closed_count} CLOSED"
    if urgent_mode:
        status_msg += " [URGENT ACTIVE]"
    log(status_msg)

    if results["transitions"]:
        log(f"Forced {len(results['transitions'])} transition(s):")
        for t in results["transitions"]:
            log(f"  • {t['agent']}: {t['from']} → {t['to']} ({t['reason']})")
    else:
        log("No forced transitions needed")

    return 0


if __name__ == "__main__":
    sys.exit(main())
