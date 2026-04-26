#!/usr/bin/env python3
"""
action-resolution-tracker.py — Tracks whether TICK actions actually resolve issues

Run periodically (via cron or on-demand) to analyze watchdog.log and measure:
- Which actions were taken
- Whether the triggering condition was resolved
- Time-to-resolution for each action type

Output: logs/action-resolution.jsonl (append-only, one entry per action event)
"""
from __future__ import annotations

import json
import re
import os
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

LOGDIR = Path("/Users/kublai/.openclaw/agents/main/logs")
WATCHDOG_LOG = LOGDIR / "watchdog.log"
OUTPUT_LOG = LOGDIR / "action-resolution.jsonl"
STATE_FILE = LOGDIR / "action-resolution-state.json"

# Pattern to extract action events from watchdog.log
ACTION_PATTERNS = {
    "AUTO_REDISTRIBUTE": r"AUTO_REDISTRIBUTE \| (.+)",
    "THROUGHPUT_ESCALATION": r"THROUGHPUT_ESCALATION \| (.+)",
    "TICK_LLM_dispatch": r"TICK_LLM \| dispatching main immediately",
    "escalation_task": r"action=escalate",
}

# Pattern for TICK summary (to check if condition resolved)
TICK_PATTERN = r"\[([\d\-:\s]+)\] TICK \| (.+)"


def parse_tick_summary(line):
    """Extract key metrics from a TICK log line."""
    match = re.search(TICK_PATTERN, line)
    if not match:
        return None

    ts_str, data = match.groups()
    try:
        ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None

    # Parse key-value pairs from the tick data
    metrics = {"ts": ts, "raw": line.strip()}
    for item in data.split(" | "):
        if "=" in item:
            k, v = item.split("=", 1)
            metrics[k] = v

    return metrics


def parse_action(line):
    """Extract action type and details from a log line."""
    ts_match = re.match(r"\[([\d\-:\s]+)\]", line)
    if not ts_match:
        return None
    try:
        ts = datetime.strptime(ts_match.group(1), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None

    for action_type, pattern in ACTION_PATTERNS.items():
        match = re.search(pattern, line)
        if match:
            return {
                "ts": ts,
                "action_type": action_type,
                "details": match.group(1) if match.groups() else "",
                "raw": line.strip()
            }
    return None


def load_state():
    """Load pending actions that need resolution tracking."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, IOError):
            pass
    return {"pending_actions": [], "resolved_actions": []}


def save_state(state):
    """Persist state to disk."""
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str))


def is_queue_imbalance_resolved(tick_metrics):
    """Check if QUEUE_IMBALANCE condition is resolved."""
    # Condition is resolved if:
    # - No longer in action=escalate
    # - No longer has QUEUE_IMBALANCE in reason
    # - Or pending tasks < threshold (e.g., 5)
    action = tick_metrics.get("action", "")
    reason = tick_metrics.get("reason", "")
    pending = int(tick_metrics.get("tasks_pending", 999))

    if "QUEUE_IMBALANCE" not in reason and "escalate" not in action:
        return True
    if pending < 5:  # Threshold for "healthy"
        return True
    return False


def is_high_error_resolved(tick_metrics):
    """Check if high error condition is resolved."""
    errors = int(tick_metrics.get("errors", 999))
    # Resolved if errors < 10 per tick
    return errors < 10


def track_resolution():
    """Main analysis: match actions with resolutions."""
    state = load_state()
    pending = state.get("pending_actions", [])
    resolved = state.get("resolved_actions", [])

    # Read recent watchdog.log entries
    if not WATCHDOG_LOG.exists():
        print(f"ERROR: {WATCHDOG_LOG} not found")
        return

    # Get last 1000 lines (efficient tail read)
    lines = []
    with open(WATCHDOG_LOG, "r") as f:
        for line in f:
            lines.append(line)
        if len(lines) > 2000:
            lines = lines[-2000:]

    # Find new actions and check for resolutions
    new_actions = []
    still_pending = []

    for line in lines:
        # Check for new actions
        action = parse_action(line)
        if action:
            # Check if this action is already tracked
            action_sig = f"{action['ts'].isoformat()}:{action['action_type']}"
            if not any(a.get("signature") == action_sig for a in pending + resolved + new_actions):
                new_actions.append({
                    "signature": action_sig,
                    "triggered_at": action["ts"].isoformat(),
                    "action_type": action["action_type"],
                    "details": action["details"],
                    "raw_trigger": action["raw"],
                    "status": "pending",
                    "resolution_checks": 0
                })

        # Check if pending actions are resolved
        tick = parse_tick_summary(line)
        if tick:
            ts = tick["ts"]
            for pending_action in pending + new_actions:
                if pending_action["status"] != "pending":
                    continue

                # Check if action is too old (>30 min) - mark as stale
                action_time = datetime.fromisoformat(pending_action["triggered_at"])
                if (ts - action_time) > timedelta(minutes=30):
                    pending_action["status"] = "stale"
                    pending_action["resolved_at"] = ts.isoformat()
                    pending_action["resolution_reason"] = "timed_out"
                    resolved.append(pending_action)
                    continue

                pending_action["resolution_checks"] += 1

                # Check resolution based on action type
                action_type = pending_action["action_type"]
                is_resolved = False

                if action_type == "AUTO_REDISTRIBUTE" and "QUEUE_IMBALANCE" in pending_action.get("details", ""):
                    is_resolved = is_queue_imbalance_resolved(tick)
                elif "errors" in tick:
                    is_resolved = is_high_error_resolved(tick)

                if is_resolved:
                    pending_action["status"] = "resolved"
                    pending_action["resolved_at"] = ts.isoformat()
                    pending_action["resolution_ticks"] = pending_action["resolution_checks"]
                    pending_action["resolution_seconds"] = int((ts - action_time).total_seconds())
                    pending_action["final_tick"] = tick
                    resolved.append(pending_action)

    # Update pending list (remove resolved/stale, add new)
    still_pending = [a for a in pending + new_actions if a["status"] == "pending"]
    state["pending_actions"] = still_pending
    state["resolved_actions"] = resolved[-100:]  # Keep last 100
    save_state(state)

    # Append new resolution events to jsonl log
    with open(OUTPUT_LOG, "a") as f:
        for action in state["resolved_actions"]:
            if "logged" not in action:
                entry = {
                    "triggered_at": action["triggered_at"],
                    "action_type": action["action_type"],
                    "status": action["status"],
                    "resolution_seconds": action.get("resolution_seconds"),
                    "resolution_ticks": action.get("resolution_ticks"),
                    "details": action.get("details", ""),
                }
                f.write(json.dumps(entry) + "\n")
                action["logged"] = True

    # Print summary
    print(f"Action Resolution Tracker:")
    print(f"  Pending: {len(still_pending)}")
    print(f"  Resolved/Stale (last 100): {len(resolved)}")

    if still_pending:
        print(f"\nPending actions:")
        for a in still_pending[:5]:
            print(f"  - {a['action_type']}: {a.get('details', '')[:60]}")

    if resolved:
        # Calculate effectiveness stats
        resolved_list = [r for r in resolved if r["status"] == "resolved"]
        if resolved_list:
            avg_time = sum(r.get("resolution_seconds", 0) for r in resolved_list) / len(resolved_list)
            print(f"\nResolution stats:")
            print(f"  Avg time: {avg_time:.0f}s")
            print(f"  Success rate: {len(resolved_list)}/{len(resolved)}")


if __name__ == "__main__":
    track_resolution()
