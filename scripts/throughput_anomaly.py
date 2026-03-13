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

    Uses ps aux instead of pgrep for more reliable detection of bash wrapper processes.

    Returns: int - number of active claude-agent processes
    """
    count = 0
    try:
        result = subprocess.run(
            ["ps", "aux"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            # Count bash processes running claude-agent with --workdir
            for line in result.stdout.split('\n'):
                if 'bin/claude-agent' in line and '--workdir' in line:
                    count += 1
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return count


def is_task_watcher_running():
    """Check if task-watcher.py process is running.

    Uses ps aux to detect task-watcher.py process. This provides diagnostic
    information for PENDING_NO_DISPATCH anomalies to distinguish between:
    - task-watcher not running (needs restart)
    - task-watcher running but not dispatching (different issue)

    Returns: tuple (is_running: bool, pid: int or None, details: str)
    """
    try:
        result = subprocess.run(
            ["ps", "aux"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if 'task-watcher' in line and 'python' in line:
                    # Extract PID (second column in ps aux output)
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            pid = int(parts[1])
                            return True, pid, f"running (pid={pid})"
                        except ValueError:
                            pass
                    return True, None, "running (pid unknown)"
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return False, None, "NOT RUNNING"


def is_reflection_running():
    """Detect if Kurultai hourly reflection is currently running.

    During reflection, all 6 agents run meta_reflection.py which takes them
    away from normal task execution. This causes total_executing==0 temporarily,
    which would trigger PENDING_NO_DISPATCH false positives.

    Detection methods (in order of reliability):
    1. Check for running meta_reflection.py or prepare_reflection_context.py processes
    2. Check for recent *_reflection_context.md files in /tmp (< 10 min old)

    Returns: bool - True if reflection appears to be running
    """
    import glob

    # Method 1: Check for active reflection processes (most reliable)
    try:
        result = subprocess.run(
            ["ps", "aux"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                # Look for reflection-related processes
                if any(pattern in line for pattern in [
                    'meta_reflection.py',
                    'prepare_reflection_context.py',
                    'kurultai_reflect',
                    'hourly_reflection.sh'
                ]):
                    # Ignore grep processes
                    if 'grep' not in line and 'def is_reflection_running' not in line:
                        return True
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    # Method 2: Check for recent reflection context files in /tmp
    tmp_dir = Path("/tmp")
    now = time.time()
    reflection_window_s = 600  # 10 minutes

    try:
        # Look for agent reflection context files (created by prepare_reflection_context.py)
        pattern = "*_reflection_context.md"
        for f in tmp_dir.glob(pattern):
            try:
                mtime = f.stat().st_mtime
                age = now - mtime
                if age < reflection_window_s:
                    return True
            except (OSError, FileNotFoundError):
                continue
    except (OSError, FileNotFoundError):
        pass

    return False


def get_active_claude_processes_by_agent():
    """Get count of active claude-agent processes per agent.

    Uses process command line inspection to determine which agent
    each claude-agent process is working for.

    ACP sessions execute via: /bin/bash /path/to/claude-agent --workdir /path/to/agents/{agent}
    This function extracts the agent name from the --workdir argument.

    Returns: dict mapping agent_name -> process_count
    """
    agent_counts = {a: 0 for a in DISPATCH_AGENTS}
    import re

    try:
        # Use ps aux directly instead of pgrep for more reliable detection
        # pgrep doesn't handle bash wrapper processes with embedded newlines well
        result = subprocess.run(
            ["ps", "aux"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            return agent_counts

        # Find lines containing claude-agent wrapper with --workdir
        for line in result.stdout.split('\n'):
            # Look for bash processes running claude-agent with --workdir
            if 'bin/claude-agent' in line and '--workdir' in line:
                # Extract agent name from --workdir argument
                # Pattern: --workdir /path/to/agents/{agent}
                match = re.search(r'--workdir\s+\S+agents/(\w+)', line)
                if match:
                    agent = match.group(1)
                    if agent in DISPATCH_AGENTS:
                        agent_counts[agent] += 1

    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    return agent_counts


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
    """Count FAILED and COMPLETED events per agent in window. Returns (per_agent, fleet) dicts.

    Rework-aware: Excludes failed tasks that eventually complete (rework cycles).
    Quality gate failures that trigger revision but eventually complete are not
    counted as terminal failures. This prevents false-positive HIGH_FAILURE_RATE
    alerts when agents are productively working through revision cycles.

    ACP-aware: Also excludes failed tasks that are actively being retried via ACP sessions.
    """
    events = read_ledger(hours=hours)
    agent_failed = defaultdict(int)
    agent_completed = defaultdict(int)

    # Track task_ids per event type for rework-aware calculation
    failed_task_ids = defaultdict(set)  # agent -> set of failed task_ids
    completed_task_ids = defaultdict(set)  # agent -> set of completed task_ids

    for e in events:
        agent = e.get("agent")
        if not agent or agent not in DISPATCH_AGENTS:
            continue
        ev = e.get("event")
        if ev == "FAILED":
            task_id = e.get("task_id")
            if task_id:
                failed_task_ids[agent].add(task_id)
        elif ev == "COMPLETED":
            task_id = e.get("task_id")
            if task_id:
                completed_task_ids[agent].add(task_id)

    # Rework-aware calculation: Exclude failures for tasks that eventually completed
    # A task that fails 3 times then completes = 1 completion, 0 failures (rework cycle)
    # A task that fails and never completes = 1 failure (terminal failure)
    rework_adjusted_failed = defaultdict(int)
    for agent in DISPATCH_AGENTS:
        failed = failed_task_ids.get(agent, set())
        completed = completed_task_ids.get(agent, set())

        # Terminal failures = tasks that failed but NEVER completed
        terminal_failures = failed - completed
        rework_adjusted_failed[agent] = len(terminal_failures)

    # ACP-aware adjustment: Also exclude failed tasks actively being retried
    active_processes = get_active_claude_processes_by_agent()

    adjusted_failed = defaultdict(int)
    for agent in DISPATCH_AGENTS:
        terminal_count = rework_adjusted_failed.get(agent, 0)
        active_count = active_processes.get(agent, 0)

        # Subtract actively-retrying tasks from terminal failure count
        # Each active process = one failed task now being retried
        adjusted_failed[agent] = max(0, terminal_count - active_count)

    per_agent = {}
    for agent in set(list(failed_task_ids) + list(completed_task_ids)):
        failed = adjusted_failed.get(agent, 0)
        completed = len(completed_task_ids.get(agent, set()))
        total = failed + completed
        raw_failed = len(failed_task_ids.get(agent, set()))
        per_agent[agent] = {
            "failed": failed,
            "completed": completed,
            "total": total,
            "raw_failed": raw_failed,  # Include raw count for debugging
            "active_processes": active_processes.get(agent, 0),
            "rate": failed / total if total > 0 else 0,
        }

    fleet_failed = sum(adjusted_failed.values())
    fleet_completed = sum(len(ct) for ct in completed_task_ids.values())
    fleet_total = fleet_failed + fleet_completed
    fleet_raw_failed = sum(len(ft) for ft in failed_task_ids.values())
    fleet = {
        "failed": fleet_failed,
        "completed": fleet_completed,
        "total": fleet_total,
        "raw_failed": fleet_raw_failed,  # Include raw count for debugging
        "active_processes_total": sum(active_processes.values()),
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
    # REFLECTION-AWARE: Suppress false positives during hourly reflection cycle
    # (all agents run meta_reflection.py, causing temporary 0 executing state)
    # DIAGNOSTIC: Includes task-watcher process status for faster triage
    if total_pending >= 3 and total_executing == 0:
        # Check if reflection is running before flagging anomaly
        if not is_reflection_running():
            pend_list = ", ".join(f"{a}={n}" for a, n in sorted(pending.items()))
            # Diagnostic: Check task-watcher process status
            tw_running, tw_pid, tw_status = is_task_watcher_running()
            tw_info = f"task-watcher={tw_status}" if tw_status else "task-watcher status unknown"
            warnings.append(
                f"THROUGHPUT_ANOMALY: PENDING_NO_DISPATCH — "
                f"{total_pending} task(s) pending [{pend_list}] but "
                f"0 executing. {tw_info}. "
                f"Action: {'check dispatch logs' if tw_running else 'restart task-watcher via launchctl'}"
            )
        # else: Reflection running - agents are busy reflecting, not stalled

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
    # ACP-aware: Suppress alert if active claude processes detected (system is retrying)
    per_agent_rates, fleet_rates = get_failure_rates(FAILURE_RATE_WINDOW_H)

    # Get active processes for ACP-aware suppression
    active_processes = get_active_claude_processes_by_agent()
    total_active = sum(active_processes.values())

    # ACP-aware suppression: Don't flag HIGH_FAILURE_RATE if work is actively happening
    # Work is "actively happening" if:
    # 1. There are active claude-agent processes (ACP sessions executing tasks)
    # 2. OR there are pending tasks waiting to execute
    has_active_work = total_active > 0 or total_pending > 0

    # FIX 2026-03-12: Check for recent activity to prevent false positives from stale failure data
    # If there's no current work AND no recent events (in shorter window), the failure rate
    # is based on old data and shouldn't trigger alerts. Only alert when failures are current.
    recent_events = read_ledger(hours=0.5)  # Last 30 minutes
    has_recent_activity = len(recent_events) > 0

    if fleet_rates["total"] >= MIN_TASKS_FOR_FAILURE_RATE:
        if fleet_rates["rate"] >= FLEET_FAILURE_RATE_THRESHOLD:
            # Jochi fix: Require recent activity to confirm failures are current, not historical
            # This prevents HIGH_FAILURE_RATE false positives when system is idle with old failures
            if not has_active_work:
                # Additional check: only alert if there's recent activity
                # This prevents escalation based on stale 2-hour-old failure data
                if has_recent_activity:
                    warnings.append(
                        f"THROUGHPUT_ANOMALY: HIGH_FAILURE_RATE — "
                        f"Fleet-wide failure rate {fleet_rates['rate']:.0%} "
                        f"({fleet_rates['failed']}/{fleet_rates['total']} tasks) "
                        f"in last {FAILURE_RATE_WINDOW_H}h. "
                        f"Recent activity: {len(recent_events)} events in 30min. "
                        f"Possible model misconfiguration, API outage, or systemic error."
                    )
                # else: No recent activity - failures are historical, not a current anomaly
            # else: Work is actively happening via ACP sessions - suppress false positive

    # Per-agent failure rate (only if fleet-wide didn't fire, to avoid noise)
    # ACP-aware: Also suppress per-agent alerts if that agent has active processes
    if fleet_rates["rate"] < FLEET_FAILURE_RATE_THRESHOLD:
        failing_agents = []
        for agent, stats in per_agent_rates.items():
            # Skip if this agent has active processes (work in progress)
            if active_processes.get(agent, 0) > 0:
                continue
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

    # Recovery detection: For HIGH_FAILURE_RATE, check recent health (last 1 hour)
    # If recent rate is healthy, the system has recovered even with old failures in 2h window
    if prev_type == "HIGH_FAILURE_RATE" and primary == "HIGH_FAILURE_RATE":
        # Check recent window (1 hour)
        _, recent_fleet = get_failure_rates(hours=1.0)
        recent_rate = recent_fleet.get("rate", 1.0)  # Default to 100% if no data
        recent_total = recent_fleet.get("total", 0)

        # If we have meaningful recent data and rate is healthy (<50%), reset counter
        # This allows the alert to clear when the system recovers, even with old failures in window
        # FIX: Lowered threshold from >=2 to >=1 to handle low-activity recovery (e.g., only 1 task completed)
        # A 0% rate with any activity means recovery, regardless of task count
        if (recent_total >= 1 and recent_rate == 0.0) or (recent_total >= 2 and recent_rate < 0.50):
            # System recovered: reset consecutive counter
            consecutive = 1
        elif consecutive >= 5:
            # For persistent alerts, also check if 2h rate is improving
            _, fleet = get_failure_rates(FAILURE_RATE_WINDOW_H)
            current_rate = fleet.get("rate", 0)

            # If rate dropped significantly (below 80% of threshold), reduce counter
            if current_rate < FLEET_FAILURE_RATE_THRESHOLD * 0.8:
                consecutive = max(1, consecutive // 2)

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
