#!/usr/bin/env python3
"""
throughput_anomaly.py — Fleet-wide throughput anomaly detection.

Detects systemic pipeline issues that per-task stall detection misses:
  1. EXECUTING_NO_OUTPUT: Agents have .executing tasks but 0 completions in window
  2. FLEET_IDLE: All agents idle (0 executing, 0 pending) for extended period
  3. LOW_YIELD: Many agents executing but very few completions
  4. PENDING_NO_DISPATCH: Tasks pending but nothing executing
  5. QUEUE_IMBALANCE: Some agents overloaded while others idle
  6. HIGH_FAILURE_RATE: Fleet-wide or per-agent failure rate exceeds threshold

Called from watchdog-gather.sh on every tick (5 minutes), alongside stall_detector.py.

Persistent state: Tracks consecutive anomaly occurrences across ticks in
  logs/throughput-anomaly-state.json. Escalates severity when same anomaly
  persists: 1-2 ticks=MEDIUM, 3-5 ticks=HIGH, 6+ ticks=CRITICAL.

Output format (stdout, one line per anomaly + optional severity line):
    THROUGHPUT_ANOMALY: <type> — <details>
    THROUGHPUT_SEVERITY: <MEDIUM|HIGH|CRITICAL> consecutive=<N> type=<type>

Exit codes:
    0 = no anomalies
    1 = one or more anomalies detected
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent))
from kurultai_paths import AGENTS_DIR, TASK_LEDGER, VALID_AGENTS, LOGS_DIR
from kurultai_ledger import read_ledger

# Thresholds
ZERO_COMPLETION_WINDOW_H = 2      # Flag if 0 completions in this many hours
FLEET_IDLE_WINDOW_H = 3           # Flag if all agents idle for this long
DISPATCH_AGENTS = ["temujin", "mongke", "chagatai", "jochi", "ogedei", "tolui"]

# Failure rate thresholds
FAILURE_RATE_WINDOW_H = 2         # Window for failure rate calculation
FLEET_FAILURE_RATE_THRESHOLD = 0.60   # 60% fleet-wide failure rate triggers alert
AGENT_FAILURE_RATE_THRESHOLD = 0.80   # 80% per-agent failure rate triggers alert
MIN_TASKS_FOR_FAILURE_RATE = 5    # Minimum terminal tasks before checking rate

# Consecutive anomaly escalation thresholds (each tick = 5 minutes)
# PRIORITY_FIX (2026-03-11): Reduced CRITICAL from 6->3 to catch ops debt earlier
ANOMALY_STATE_FILE = LOGS_DIR / "throughput-anomaly-state.json"
CONSECUTIVE_HIGH = 2       # 2 ticks (10 min) -> HIGH
CONSECUTIVE_CRITICAL = 3   # 3 ticks (15 min) -> CRITICAL (was 6/30min)
TICK_STALENESS_S = 600     # If last tick > 10 min ago, reset counter (missed ticks)


def count_active_claude_processes():
    """Count active claude-agent processes to detect ACP session activity.

    ACP sessions (the current architecture) don't create .executing.md files.
    This function checks for running claude processes as a proxy for active work.
    Returns: int - number of active claude-agent processes
    """
    try:
        result = subprocess.run(
            ["pgrep", "-f", "claude-agent"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            pids = result.stdout.strip().split('\n')
            return len([p for p in pids if p])
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return 0


def count_executing_tasks():
    """Count .executing tasks per agent from filesystem.

    NOTE: Current architecture uses ACP sessions which don't create .executing.md files.
    Use count_active_claude_processes() for accurate fleet activity detection.
    This function is kept for backward compatibility with legacy dispatch.
    """
    executing = {}
    for agent in DISPATCH_AGENTS:
        tasks_dir = AGENTS_DIR / agent / "tasks"
        if not tasks_dir.exists():
            continue
        count = 0
        try:
            for fname in os.listdir(str(tasks_dir)):
                if fname.endswith(".executing.md"):
                    count += 1
        except OSError:
            pass
        if count > 0:
            executing[agent] = count
    return executing


def get_executing_task_ages():
    """Get age of each executing task in seconds.
    
    Returns dict: {agent: [(task_file, age_seconds), ...]}
    """
    executing_ages = {}
    now = time.time()
    for agent in DISPATCH_AGENTS:
        tasks_dir = AGENTS_DIR / agent / "tasks"
        if not tasks_dir.exists():
            continue
        agent_tasks = []
        try:
            for fname in os.listdir(str(tasks_dir)):
                if fname.endswith(".executing.md"):
                    fpath = tasks_dir / fname
                    try:
                        mtime = fpath.stat().st_mtime
                        age = now - mtime
                        agent_tasks.append((fname, age))
                    except OSError:
                        pass
        except OSError:
            pass
        if agent_tasks:
            executing_ages[agent] = agent_tasks
    return executing_ages


def has_stale_executing_tasks(min_age_seconds=600):
    """Check if any executing tasks are older than min_age_seconds.
    
    Default threshold: 10 minutes (600 seconds)
    Tasks younger than this are considered "normal execution" not "stalled".
    """
    executing_ages = get_executing_task_ages()
    for agent, tasks in executing_ages.items():
        for fname, age in tasks:
            if age > min_age_seconds:
                return True, agent, fname, age
    return False, None, None, None


def count_pending_tasks():
    """Count pending (non-done, non-executing) tasks per agent."""
    pending = {}
    for agent in DISPATCH_AGENTS:
        tasks_dir = AGENTS_DIR / agent / "tasks"
        if not tasks_dir.exists():
            continue
        count = 0
        try:
            for fname in os.listdir(str(tasks_dir)):
                if not fname.endswith(".md"):
                    continue
                # Skip executing tasks
                if fname.endswith(".executing.md"):
                    continue
                # Skip terminal state files (done, completed, resolved, failed, etc.)
                # These can have various suffixes like .done.md, .done-HASH.md, .completed.done.md, etc.
                terminal_markers = ['.done', '.completed', '.resolved', '.failed', '.cancelled', '.stale', '.obsolete']
                if any(marker in fname for marker in terminal_markers):
                    continue
                count += 1
        except OSError:
            pass
        if count > 0:
            pending[agent] = count
    return pending


def count_movable_pending_tasks():
    """Count pending tasks that CAN be moved via load balancing.

    Excludes:
    - HIGH/critical priority tasks (require primary agent attention)
    - ops tasks on ogedei (primary agent for ops domain)
    - escalation tasks (critical coordination)

    This matches the exemption logic in task-redistribute.py:find_movable_tasks()
    to prevent false-positive QUEUE_IMBALANCE alerts.
    """
    import re

    movable_pending = {}
    for agent in DISPATCH_AGENTS:
        tasks_dir = AGENTS_DIR / agent / "tasks"
        if not tasks_dir.exists():
            continue

        movable_count = 0
        try:
            for fname in os.listdir(str(tasks_dir)):
                if not fname.endswith(".md"):
                    continue
                # Skip executing tasks
                if fname.endswith(".executing.md"):
                    continue
                # Skip terminal state files (done, completed, resolved, failed, etc.)
                # These can have various suffixes like .done.md, .done-HASH.md, .completed.done.md, etc.
                terminal_markers = ['.done', '.completed', '.resolved', '.failed', '.cancelled', '.stale', '.obsolete']
                if any(marker in fname for marker in terminal_markers):
                    continue
                if "archived" in fname or fname.startswith("."):
                    continue

                # Read frontmatter to check exemptions
                try:
                    fpath = tasks_dir / fname
                    content = fpath.read_text()

                    # EXEMPTION 1: HIGH/critical priority tasks
                    priority_match = re.search(r'^priority:\s*(\w+)$', content, re.MULTILINE)
                    task_priority = priority_match.group(1).lower() if priority_match else "normal"
                    if task_priority in ("high", "critical"):
                        continue

                    # EXEMPTION 2: Extract domain if present
                    domain_match = re.search(r'^domain:\s*(\w+)$', content, re.MULTILINE)
                    domain = domain_match.group(1).lower() if domain_match else None

                    # EXEMPTION 2: ops tasks stay with ogedei (primary agent)
                    if domain == "ops" and agent == "ogedei":
                        continue

                    # EXEMPTION 3: escalation tasks require assigned agent
                    if domain == "escalation":
                        continue

                    # Task is movable
                    movable_count += 1
                except (OSError, IOError):
                    # If we can't read the file, count it as movable (conservative)
                    movable_count += 1
        except OSError:
            pass

        if movable_count > 0:
            movable_pending[agent] = movable_count

    return movable_pending


def get_completions_in_window(hours):
    """Count COMPLETED events per agent in the last N hours."""
    events = read_ledger(hours=hours)
    counts = defaultdict(int)
    for e in events:
        if e.get("event") == "COMPLETED":
            agent = e.get("agent")
            if agent:
                counts[agent] += 1
    return dict(counts)


def get_last_completion_age_hours():
    """Return hours since the most recent COMPLETED event system-wide."""
    events = read_ledger(hours=24)
    latest_ts = None
    for e in events:
        if e.get("event") == "COMPLETED":
            ts_str = e.get("ts")
            if ts_str:
                try:
                    from datetime import datetime
                    ts = datetime.fromisoformat(ts_str)
                    if latest_ts is None or ts > latest_ts:
                        latest_ts = ts
                except (ValueError, TypeError):
                    pass

    if latest_ts is None:
        return None

    from datetime import datetime
    delta = datetime.now() - latest_ts
    return delta.total_seconds() / 3600


def get_failure_rates(hours):
    """Count FAILED and COMPLETED events per agent in window. Returns (per_agent, fleet) dicts."""
    events = read_ledger(hours=hours)
    agent_failed = defaultdict(int)
    agent_completed = defaultdict(int)
    for e in events:
        agent = e.get("agent")
        if not agent or agent not in DISPATCH_AGENTS:
            continue
        ev = e.get("event")
        if ev == "FAILED":
            agent_failed[agent] += 1
        elif ev == "COMPLETED":
            agent_completed[agent] += 1

    per_agent = {}
    for agent in set(list(agent_failed) + list(agent_completed)):
        failed = agent_failed.get(agent, 0)
        completed = agent_completed.get(agent, 0)
        total = failed + completed
        per_agent[agent] = {
            "failed": failed, "completed": completed, "total": total,
            "rate": failed / total if total > 0 else 0,
        }

    fleet_failed = sum(agent_failed.values())
    fleet_completed = sum(agent_completed.values())
    fleet_total = fleet_failed + fleet_completed
    fleet = {
        "failed": fleet_failed, "completed": fleet_completed, "total": fleet_total,
        "rate": fleet_failed / fleet_total if fleet_total > 0 else 0,
    }
    return per_agent, fleet


def detect_anomalies():
    """Detect fleet-wide throughput anomalies. Returns list of warning strings."""
    warnings = []

    executing = count_executing_tasks()
    pending = count_pending_tasks()
    completions = get_completions_in_window(ZERO_COMPLETION_WINDOW_H)

    total_executing = sum(executing.values())
    total_pending = sum(pending.values())
    total_completions = sum(completions.values())

    # Anomaly 1: Agents executing but zero completions in window
    # Only flag if executing tasks are stale (>10 min old) - avoids false positives
    # for recently-dispatched tasks that haven't had time to complete
    if total_executing > 0 and total_completions == 0:
        is_stale, stale_agent, stale_task, stale_age = has_stale_executing_tasks(min_age_seconds=600)
        if is_stale:
            exec_list = ", ".join(f"{a}={n}" for a, n in sorted(executing.items()))
            warnings.append(
                f"THROUGHPUT_ANOMALY: EXECUTING_NO_OUTPUT — "
                f"{total_executing} task(s) executing [{exec_list}] but "
                f"0 completions in last {ZERO_COMPLETION_WINDOW_H}h. "
                f"Stale task: {stale_agent}/{stale_task} (age={stale_age:.0f}s). "
                f"Possible dispatch deadlock or agent stall."
            )
        # else: Tasks are executing normally, just haven't completed yet - no anomaly

    # Anomaly 2: Fleet completely idle for extended period
    # FIXED: Check for active claude-agent processes (ACP sessions) not just .executing.md files
    active_processes = count_active_claude_processes()
    total_activity = total_executing + active_processes
    if total_activity == 0 and total_pending == 0:
        last_age = get_last_completion_age_hours()
        if last_age is not None and last_age > FLEET_IDLE_WINDOW_H:
            warnings.append(
                f"THROUGHPUT_ANOMALY: FLEET_IDLE — "
                f"All agents idle (0 executing, 0 active processes, 0 pending) with last completion "
                f"{last_age:.1f}h ago. Check task intake pipeline."
            )

    # Anomaly 3: High executing-to-completion ratio (agents spinning)
    # If many agents executing but very few completions relative to executing count
    if total_executing >= 3 and total_completions <= 1:
        exec_list = ", ".join(f"{a}={n}" for a, n in sorted(executing.items()))
        warnings.append(
            f"THROUGHPUT_ANOMALY: LOW_YIELD — "
            f"{total_executing} tasks executing [{exec_list}] but only "
            f"{total_completions} completion(s) in {ZERO_COMPLETION_WINDOW_H}h. "
            f"Investigate task complexity or timeout patterns."
        )

    # Anomaly 4: Tasks pending but nothing executing (dispatch starvation)
    # Catches the gap where tasks queue up but task-watcher isn't picking them up
    if total_pending >= 3 and total_executing == 0:
        pend_list = ", ".join(f"{a}={n}" for a, n in sorted(pending.items()))
        warnings.append(
            f"THROUGHPUT_ANOMALY: PENDING_NO_DISPATCH — "
            f"{total_pending} task(s) pending [{pend_list}] but "
            f"0 executing. Task-watcher may be stalled or not running. "
            f"Check: launchctl list | grep task-watcher"
        )

    # Anomaly 5: Queue imbalance — some agents overloaded while others idle
    # Detects routing failures where work piles up on 1-2 agents while others starve
    # Uses movable_pending (excludes HIGH/critical, ops-on-ogedei, escalation tasks)
    # to prevent false positives when imbalance is due to domain-specialized work
    movable_pending = count_movable_pending_tasks()
    total_movable = sum(movable_pending.values())

    if total_movable >= 4:
        overloaded = {a: n for a, n in movable_pending.items() if n >= 3}
        idle_agents = [a for a in DISPATCH_AGENTS
                       if a not in movable_pending and a not in executing]
        if overloaded and len(idle_agents) >= 2:
            over_list = ", ".join(f"{a}={n}" for a, n in sorted(overloaded.items()))
            idle_list = ", ".join(sorted(idle_agents))
            warnings.append(
                f"THROUGHPUT_ANOMALY: QUEUE_IMBALANCE — "
                f"Overloaded agents [{over_list}] while "
                f"{len(idle_agents)} agents idle [{idle_list}]. "
                f"Routing may be sticky or load-balancing thresholds ineffective."
            )

    # Anomaly 6: High failure rate — systemic failures (e.g. model misconfiguration)
    # Catches issues like wrong model assignment that cause mass task failures
    per_agent_rates, fleet_rates = get_failure_rates(FAILURE_RATE_WINDOW_H)

    if fleet_rates["total"] >= MIN_TASKS_FOR_FAILURE_RATE:
        if fleet_rates["rate"] >= FLEET_FAILURE_RATE_THRESHOLD:
            warnings.append(
                f"THROUGHPUT_ANOMALY: HIGH_FAILURE_RATE — "
                f"Fleet-wide failure rate {fleet_rates['rate']:.0%} "
                f"({fleet_rates['failed']}/{fleet_rates['total']} tasks) "
                f"in last {FAILURE_RATE_WINDOW_H}h. "
                f"Possible model misconfiguration, API outage, or systemic error."
            )

    # Per-agent failure rate (only if fleet-wide didn't fire, to avoid noise)
    if fleet_rates["rate"] < FLEET_FAILURE_RATE_THRESHOLD:
        failing_agents = []
        for agent, stats in per_agent_rates.items():
            if (stats["total"] >= 3 and
                    stats["rate"] >= AGENT_FAILURE_RATE_THRESHOLD):
                failing_agents.append(
                    f"{agent}={stats['rate']:.0%}({stats['failed']}/{stats['total']})")
        if failing_agents:
            warnings.append(
                f"THROUGHPUT_ANOMALY: HIGH_FAILURE_RATE — "
                f"Per-agent failure spike: [{', '.join(sorted(failing_agents))}] "
                f"in last {FAILURE_RATE_WINDOW_H}h. "
                f"Check agent config, model assignment, or task compatibility."
            )

    return warnings


def load_anomaly_state():
    """Load persistent anomaly tracking state."""
    try:
        if ANOMALY_STATE_FILE.exists():
            data = json.loads(ANOMALY_STATE_FILE.read_text())
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return {"consecutive": 0, "type": None, "first_seen": None, "last_tick": 0}


def save_anomaly_state(state):
    """Save anomaly tracking state atomically."""
    try:
        tmp = ANOMALY_STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2))
        tmp.rename(ANOMALY_STATE_FILE)
    except OSError:
        pass


def update_anomaly_persistence(anomaly_types):
    """Track consecutive anomaly occurrences across ticks.

    Returns (severity, consecutive_count, primary_type) or None if no escalation.
    Severity: MEDIUM (1-2 ticks), HIGH (3-5 ticks), CRITICAL (6+ ticks).
    """
    now = time.time()
    state = load_anomaly_state()

    if not anomaly_types:
        # No anomalies this tick — reset counter
        state = {"consecutive": 0, "type": None, "first_seen": None, "last_tick": now}
        save_anomaly_state(state)
        return None

    # Determine primary anomaly (most severe: HIGH_FAILURE_RATE > PENDING_NO_DISPATCH > others)
    priority = ["HIGH_FAILURE_RATE", "PENDING_NO_DISPATCH", "EXECUTING_NO_OUTPUT", "LOW_YIELD", "QUEUE_IMBALANCE", "FLEET_IDLE"]
    primary = None
    for p in priority:
        if p in anomaly_types:
            primary = p
            break
    if primary is None:
        primary = anomaly_types[0]

    # Check if this is a continuation of the same anomaly type
    last_tick = state.get("last_tick", 0)
    prev_type = state.get("type")
    consecutive = state.get("consecutive", 0)

    if now - last_tick > TICK_STALENESS_S:
        # Too long since last tick — reset (missed ticks or restart)
        consecutive = 1
    elif prev_type == primary:
        # Same anomaly type continuing
        consecutive += 1
    else:
        # Different anomaly type — reset
        consecutive = 1

    state = {
        "consecutive": consecutive,
        "type": primary,
        "first_seen": state.get("first_seen") if prev_type == primary and consecutive > 1 else now,
        "last_tick": now,
    }
    save_anomaly_state(state)

    # Determine severity based on consecutive count
    if consecutive >= CONSECUTIVE_CRITICAL:
        severity = "CRITICAL"
    elif consecutive >= CONSECUTIVE_HIGH:
        severity = "HIGH"
    else:
        severity = "MEDIUM"

    return severity, consecutive, primary


def main():
    warnings = detect_anomalies()

    # Extract anomaly types from warnings
    anomaly_types = []
    for w in warnings:
        for atype in ["HIGH_FAILURE_RATE", "PENDING_NO_DISPATCH", "EXECUTING_NO_OUTPUT", "LOW_YIELD", "QUEUE_IMBALANCE", "FLEET_IDLE"]:
            if atype in w:
                anomaly_types.append(atype)
                break

    # Print individual anomaly lines (existing format, consumed by watchdog-gather.sh)
    for w in warnings:
        print(w)

    # Print severity escalation line (new format for persistent tracking)
    result = update_anomaly_persistence(anomaly_types)
    if result:
        severity, consecutive, primary = result
        duration_min = consecutive * 5
        print(f"THROUGHPUT_SEVERITY: {severity} consecutive={consecutive} "
              f"type={primary} duration={duration_min}min")

    sys.exit(1 if warnings else 0)


if __name__ == "__main__":
    main()
