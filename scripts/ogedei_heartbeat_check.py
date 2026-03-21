#!/usr/bin/env python3
"""
ogedei_heartbeat_check.py — Independent dead-man's switch for ogedei-dispatcher.

Runs 5 CRITICAL checks independently of the dispatcher:
1. Dispatcher heartbeat file age (restart if stale >120s)
2. Credential failures (AUTH/PROXY_AUTH from ledger)
3. Stalled tasks (WORKING with expired leases)
4. Agent failure rates (1h window)
5. Queue starvation (all agents idle but pending tasks exist)

Runs every 60s via launchd (ThrottleInterval=10).

Usage:
    python3 ogedei_heartbeat_check.py        # Run once
    python3 ogedei_heartbeat_check.py --loop # Run continuously (60s interval)
"""

import json
import os
import subprocess
import sys
import time
import logging
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kurultai_paths import LOGS_DIR, DISPATCH_AGENTS

logger = logging.getLogger(__name__)

DISPATCHER_HEARTBEAT = LOGS_DIR / "ogedei-dispatcher-heartbeat.json"
HEARTBEAT_STALE_THRESHOLD = 120  # seconds
FAILURE_RATE_THRESHOLD = 0.5  # 50% failure rate triggers alert
HEALTH_FLAGS_PATH = LOGS_DIR / "agent-health-flags.json"
CRED_ALERTS_PATH = LOGS_DIR / "credential-alerts.json"
DISPATCHER_PLIST = "com.kurultai.ogedei-dispatcher"


def log(msg: str, level: str = "INFO"):
    """Log with timestamp."""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{level}] {msg}")


def check_dispatcher_heartbeat() -> list[str]:
    """Check if dispatcher heartbeat file is fresh. Restart if stale."""
    issues = []

    if not DISPATCHER_HEARTBEAT.exists():
        issues.append("CRITICAL: Dispatcher heartbeat file missing")
        _restart_dispatcher()
        return issues

    try:
        data = json.loads(DISPATCHER_HEARTBEAT.read_text())
        heartbeat_ts = data.get("timestamp", 0)
        age = time.time() - heartbeat_ts

        if age > HEARTBEAT_STALE_THRESHOLD:
            issues.append(
                f"CRITICAL: Dispatcher heartbeat stale ({age:.0f}s > {HEARTBEAT_STALE_THRESHOLD}s)"
            )
            _restart_dispatcher()
        else:
            log(f"Dispatcher heartbeat OK ({age:.0f}s old)")
    except (json.JSONDecodeError, KeyError) as e:
        issues.append(f"CRITICAL: Dispatcher heartbeat file corrupt: {e}")
        _restart_dispatcher()

    return issues


def _restart_dispatcher():
    """Restart dispatcher via launchctl."""
    log("Restarting ogedei-dispatcher via launchctl kickstart", "WARN")
    try:
        subprocess.run(
            ["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{DISPATCHER_PLIST}"],
            capture_output=True, timeout=10,
        )
        # Emit ledger event
        try:
            from kurultai_ledger import append_ledger
            append_ledger({
                "event": "HEARTBEAT_STALE",
                "ts": datetime.now(timezone.utc).isoformat(),
                "agent": "ogedei",
                "action": "dispatcher_restarted",
            })
        except Exception:
            pass
    except Exception as e:
        log(f"Failed to restart dispatcher: {e}", "ERROR")


def check_credential_failures() -> list[str]:
    """Detect AUTH failures from ledger (last 30 min)."""
    issues = []
    try:
        from kurultai_ledger import read_ledger
        events = read_ledger(hours=0.5, valid_only=True)
        if not events:
            return issues

        cred_keywords = [
            "unauthorized", "authentication", "invalid token", "invalid api key",
            "credential", "401", "403", "auth failed",
        ]

        agent_cred_failures = {}
        for ev in events:
            agent = ev.get("agent")
            if not agent:
                continue
            error_type = ev.get("error_type", "")
            error_msg = (ev.get("error") or ev.get("error_msg") or "").lower()
            if error_type in ("AUTH", "PROXY_AUTH") or any(kw in error_msg for kw in cred_keywords):
                agent_cred_failures[agent] = agent_cred_failures.get(agent, 0) + 1

        for agent, count in agent_cred_failures.items():
            if count >= 2:
                issues.append(f"CRED: {agent} has {count} auth failures in 30min")

        # Write alerts file for dashboard
        if agent_cred_failures:
            CRED_ALERTS_PATH.write_text(json.dumps({
                "timestamp": time.time(),
                "alerts": agent_cred_failures,
            }))
    except Exception as e:
        log(f"Credential check error: {e}", "ERROR")

    return issues


def check_stalled_tasks() -> list[str]:
    """Check for WORKING tasks with expired leases via Neo4j."""
    issues = []
    try:
        from neo4j_v2_core import TaskStore
        store = TaskStore()
        try:
            with store.driver.session() as session:
                result = session.run("""
                    MATCH (t:Task {status: 'WORKING'})
                    WHERE t.lease_expires_at IS NOT NULL
                      AND t.lease_expires_at < datetime()
                    RETURN t.task_id AS tid, t.assigned_to AS agent,
                           t.lease_expires_at AS lease
                    LIMIT 10
                """)
                stalled = [dict(r) for r in result]
                if stalled:
                    for t in stalled:
                        issues.append(f"STALLED: {t['tid']} ({t['agent']}) lease expired")
        finally:
            store.close()
    except Exception as e:
        log(f"Stalled task check error: {e}", "ERROR")

    return issues


def check_agent_failure_rates() -> list[str]:
    """Compute 1-hour failure rates per agent."""
    issues = []
    try:
        from kurultai_ledger import read_ledger
        events = read_ledger(hours=1, valid_only=True)
        if not events:
            return issues

        agent_completed = {}
        agent_failed = {}
        for ev in events:
            agent = ev.get("agent")
            if not agent:
                continue
            event_type = ev.get("event", "")
            if event_type == "COMPLETED":
                agent_completed[agent] = agent_completed.get(agent, 0) + 1
            elif event_type == "FAILED":
                agent_failed[agent] = agent_failed.get(agent, 0) + 1

        flags = {}
        all_agents = set(list(agent_completed.keys()) + list(agent_failed.keys()))
        for agent in all_agents:
            completed = agent_completed.get(agent, 0)
            failed = agent_failed.get(agent, 0)
            total = completed + failed
            if total == 0:
                continue
            rate = failed / total
            flags[agent] = {
                "completed": completed, "failed": failed,
                "failure_rate": round(rate, 2),
                "healthy": rate < FAILURE_RATE_THRESHOLD,
            }
            if rate >= FAILURE_RATE_THRESHOLD:
                issues.append(
                    f"FAILURE_RATE: {agent} at {rate:.0%} ({failed}/{total})"
                )

        # Write health flags for dashboard
        if flags:
            HEALTH_FLAGS_PATH.write_text(json.dumps({
                "timestamp": time.time(),
                "agents": flags,
            }))
    except Exception as e:
        log(f"Failure rate check error: {e}", "ERROR")

    return issues


def check_queue_starvation() -> list[str]:
    """Detect case where pending tasks exist but no agent is working."""
    issues = []
    try:
        from neo4j_v2_core import TaskStore
        store = TaskStore()
        try:
            with store.driver.session() as session:
                result = session.run("""
                    MATCH (t:Task)
                    WHERE t.status IN ['PENDING', 'WORKING']
                    RETURN t.status AS status, count(t) AS cnt
                """)
                counts = {r["status"]: r["cnt"] for r in result}
                pending = counts.get("PENDING", 0)
                working = counts.get("WORKING", 0)
                if pending > 0 and working == 0:
                    issues.append(
                        f"STARVATION: {pending} pending tasks but 0 working"
                    )
        finally:
            store.close()
    except Exception as e:
        log(f"Queue starvation check error: {e}", "ERROR")

    return issues


def run_all_checks() -> list[str]:
    """Run all 5 checks and return combined issues."""
    all_issues = []
    all_issues.extend(check_dispatcher_heartbeat())
    all_issues.extend(check_credential_failures())
    all_issues.extend(check_stalled_tasks())
    all_issues.extend(check_agent_failure_rates())
    all_issues.extend(check_queue_starvation())

    if all_issues:
        log(f"{len(all_issues)} issues found:", "WARN")
        for issue in all_issues:
            log(f"  - {issue}", "WARN")
    else:
        log("All checks passed")

    return all_issues


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Ogedei dispatcher health checks")
    parser.add_argument("--loop", action="store_true", help="Run continuously (60s)")
    args = parser.parse_args()

    if args.loop:
        log("Starting continuous health check loop (60s interval)")
        while True:
            try:
                run_all_checks()
            except Exception as e:
                log(f"Health check cycle error: {e}", "ERROR")
            time.sleep(60)
    else:
        issues = run_all_checks()
        sys.exit(1 if issues else 0)


if __name__ == "__main__":
    main()
