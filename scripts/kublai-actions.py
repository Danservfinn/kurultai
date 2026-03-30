#!/usr/bin/env python3
"""
Kublai Actions — Rule-based action engine for the 3 checkpoints.

Called after each checkpoint to translate observations into agent tasks.
Creates task files in agent task queues for the task-consumer to dispatch.

Usage:
    python3 kublai-actions.py --trigger tick
    python3 kublai-actions.py --trigger tock
    python3 kublai-actions.py --trigger kurultai
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from json_state import locked_json_read, locked_json_update
from kurultai_paths import AGENTS_DIR, MAIN_DIR, LOGS_DIR, VALID_AGENTS

# Model detection
def get_model():
    """Get the default model from main agent config."""
    try:
        settings_file = MAIN_DIR / ".claude" / "settings.json"
        if settings_file.exists():
            with open(settings_file) as f:
                config = json.load(f)
            return config.get("env", {}).get("ANTHROPIC_MODEL", "unknown")
    except Exception:
        pass
    return "unknown"

MODEL = get_model()

BASE = str(MAIN_DIR)
AGENT_DIR = str(AGENTS_DIR)
TICKS_FILE = str(LOGS_DIR / "ticks.jsonl")
TOCK_LATEST = str(LOGS_DIR / "tock/latest.json")
ACTIONS_LOG = str(LOGS_DIR / "kublai-actions.log")
COOLDOWN_FILE = str(LOGS_DIR / "action-cooldowns.json")

# Staleness thresholds — skip actions if data is too old
MAX_TICK_AGE_SECS = 600   # 10 minutes (2 missed ticks)
MAX_TOCK_AGE_SECS = 3600  # 60 minutes (2 missed tocks)

# Cooldown periods (seconds) to prevent duplicate task creation
COOLDOWNS = {
    "error_spike": 7200,       # 2 hours
    "service_down": 600,       # 10 min
    "high_cpu": 1800,          # 30 min
    "high_memory": 1800,       # 30 min
    "cron_fix": 3600,          # 1 hour
    "queue_backlog": 1800,     # 30 min
    "agent_stalled": 14400,    # 4 hours (was 1h — increased to prevent triage spiral)
    "task_stall": 3600,        # 1 hour (time-to-first-action)
    "feedback_review": 7200,   # 2 hours
    "queue_audit": 1800,       # 30 min
    "resolution_compliance": 3600,  # 1 hour (2026-03-11)
    "critical_fleet_anomaly": 1800,  # 30 min (2026-03-12) — CRITICAL fleet investigation
    "queue_overflow_acceptance": 900,  # 15 min (2026-03-12) — K004 queue overflow absorption
}

MAX_ACTIONS_PER_CYCLE = 3

# Minimal routing for programmatic actions -- source of truth is kurultai-router SKILL.md
CATEGORY_ROUTING = {
    "infrastructure": "ogedei",
    "code_fix": "temujin",
    "code": "temujin",
    "investigation": "jochi",
    "documentation": "chagatai",
    "research": "mongke",
    "coordination": "kublai",
    "monitoring": "ogedei",
    "security": "jochi",
    "writing": "chagatai",
    "ops": "ogedei",
}

def route_by_category(category):
    """Route by pre-classified category string. Returns agent name."""
    return CATEGORY_ROUTING.get(category.lower(), "kublai")

def route_by_text(text):
    """Lightweight keyword routing for programmatic task creation."""
    from task_intake import route_by_text as _route
    return _route(text)


def _attempt_dispatch_restart(log_fn):
    """Directly check and restart the task-executor service.

    Called when PENDING_NO_DISPATCH is CRITICAL and investigation tasks are
    also pending (circular stall — creating more tasks won't help when the
    dispatch mechanism itself is down).

    Returns: str — "restarted", "already_running", or "failed:<reason>"
    """
    service = "com.kurultai.task-executor"
    uid = os.getuid()

    try:
        # Check if service is loaded and running via tabular list format.
        # `launchctl list | grep <service>` outputs: <PID|->\t<exit_code>\t<label>
        # PID is a number when running, "-" when loaded-but-not-running.
        result = subprocess.run(
            ["launchctl", "list"],
            capture_output=True, text=True, timeout=10
        )

        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if service in line:
                    parts = line.split()
                    if parts and parts[0].isdigit():
                        log_fn(f"DISPATCH_RESTART: task-executor already running (PID={parts[0]}), "
                               f"dispatch stall is not a launchd issue — investigate task files")
                        return "already_running"
                    break  # Found the service entry but no PID — proceed to kickstart

        # Service not running — attempt kickstart
        log_fn("DISPATCH_RESTART: task-executor not responding, attempting kickstart...")
        kick = subprocess.run(
            ["launchctl", "kickstart", "-k", f"gui/{uid}/{service}"],
            capture_output=True, text=True, timeout=15
        )

        if kick.returncode == 0:
            log_fn("DISPATCH_RESTART: SUCCESS — task-executor restarted via launchctl kickstart")
            return "restarted"

        # Kickstart failed — try bootstrap from plist
        plist_path = os.path.expanduser(f"~/Library/LaunchAgents/{service}.plist")
        if os.path.exists(plist_path):
            boot = subprocess.run(
                ["launchctl", "bootstrap", f"gui/{uid}", plist_path],
                capture_output=True, text=True, timeout=15
            )
            if boot.returncode == 0:
                log_fn("DISPATCH_RESTART: SUCCESS — task-executor bootstrapped via launchctl bootstrap")
                return "restarted"
            log_fn(f"DISPATCH_RESTART: FAILED — kickstart={kick.returncode}, "
                   f"bootstrap={boot.returncode}: {kick.stderr.strip()}")
            return f"failed:kickstart={kick.returncode}"

        log_fn(f"DISPATCH_RESTART: FAILED — plist not found at {plist_path}")
        return "failed:no_plist"

    except subprocess.TimeoutExpired:
        log_fn("DISPATCH_RESTART: TIMEOUT — launchctl command timed out")
        return "failed:timeout"
    except Exception as e:
        log_fn(f"DISPATCH_RESTART: ERROR — {e}")
        return f"failed:{e}"


def has_pending_task(agent, title_prefix):
    """Check if an agent already has an uncompleted task with this title prefix."""
    task_dir = f"{AGENT_DIR}/{agent}/tasks"
    if not os.path.exists(task_dir):
        return False

    # Terminal task state patterns - tasks in these states are complete
    TERMINAL_PATTERNS = (
        ".done.md",           # All done states
        ".resolved.md",       # Resolved tasks
        ".cancelled.md",      # Cancelled tasks
        ".obsolete.md",       # Obsolete tasks
    )

    for fname in os.listdir(task_dir):
        # Skip terminal states
        if any(fname.endswith(pattern) for pattern in TERMINAL_PATTERNS):
            continue
        fpath = os.path.join(task_dir, fname)
        try:
            with open(fpath) as f:
                content = f.read(500)
            if f"# Task: {title_prefix}" in content:
                return True
        except Exception:
            continue
    return False


def _file_age_secs(path):
    """Return age of file in seconds, or infinity if missing."""
    try:
        return time.time() - os.path.getmtime(path)
    except OSError:
        return float('inf')


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        os.makedirs(os.path.dirname(ACTIONS_LOG), exist_ok=True)
        with open(ACTIONS_LOG, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass  # Disk full — stdout still works for cron capture


def load_cooldowns():
    return locked_json_read(COOLDOWN_FILE, default={})


def save_cooldowns(cooldowns):
    with locked_json_update(COOLDOWN_FILE) as data:
        data.clear()
        data.update(cooldowns)


def is_cooled_down(action_key):
    """Check if an action is still in cooldown period."""
    cooldowns = load_cooldowns()
    last_fired = cooldowns.get(action_key, 0)
    cooldown_secs = COOLDOWNS.get(action_key.split(":")[0], 1800)
    return (time.time() - last_fired) < cooldown_secs


def mark_fired(action_key):
    """Mark an action as fired, resetting its cooldown."""
    cooldowns = load_cooldowns()
    cooldowns[action_key] = time.time()
    save_cooldowns(cooldowns)


def create_task(agent, priority, title, body, source="kublai-actions", depth=0,
                skill_hint=None, force_claude_code=True):
    """Create a task via canonical task_intake pipeline.

    Delegates to task_intake.create_task() for Neo4j + filesystem creation,
    duplicate checking, and depth limiting.
    """
    from task_intake import create_task as _intake_create
    result = _intake_create(
        title=title,
        body=body,
        priority=priority,
        source=source,
        depth=depth,
        agent=agent,
        skip_duplicate_check=True,  # callers already check has_pending_task
        skill_hint=skill_hint,
        force_claude_code=force_claude_code,
    )
    if result:
        log(f"ACTION: Created {priority} task for {agent}: {title} (depth={depth})")
    return result


# ============================================================
# TICK ACTIONS (every 5 minutes)
# ============================================================
def tick_actions():
    """Rule-based actions from tick (infrastructure) data."""
    # Read latest tick
    if not os.path.exists(TICKS_FILE):
        log("TICK: No ticks.jsonl found, skipping")
        return 0

    with open(TICKS_FILE) as f:
        lines = f.readlines()

    if not lines:
        log("TICK: ticks.jsonl empty, skipping")
        return 0

    # Parse latest tick, with resilience to malformed JSON entries
    # (iterate backwards from most recent to handle corrupted ticks)
    tick = None
    for i in range(1, min(len(lines), 10) + 1):  # check last 10 lines, most recent first
        try:
            tick = json.loads(lines[-i].strip())
            break  # found valid JSON
        except json.JSONDecodeError:
            continue  # try next older line

    if tick is None:
        log("TICK: Failed to parse any of last 10 ticks (all malformed)")
        return 0

    # Staleness check — warn if tick data is too old
    tick_age = _file_age_secs(TICKS_FILE)
    if tick_age > MAX_TICK_AGE_SECS:
        log(f"TICK: WARNING — ticks.jsonl is {tick_age:.0f}s old (tick may be failing)")
    tick_epoch = tick.get("epoch", 0)
    if tick_epoch and (time.time() - tick_epoch) > MAX_TICK_AGE_SECS:
        log(f"TICK: WARNING — last tick record is {time.time()-tick_epoch:.0f}s old")

    actions_created = 0
    decision = tick.get("decision", "healthy")
    errors_5m = tick.get("errors", {}).get("last_5m", 0)
    errors_1h = tick.get("errors", {}).get("last_1h", 0)
    fatal_5m = tick.get("errors", {}).get("fatal_5m", 0)
    services = tick.get("services", {})
    process = tick.get("process", {})
    gateway = tick.get("gateway", {})
    tasks = tick.get("tasks", {})

    # Rule 1: Fatal errors — immediate high-priority investigation
    if fatal_5m > 0 and not is_cooled_down("error_spike:fatal") and not has_pending_task("jochi", "Investigate FATAL"):
        create_task(
            "jochi", "high",
            "Investigate FATAL/CRASH errors in gateway log",
            f"""## Context
The tick detected {fatal_5m} FATAL/CRASH errors in the last 5 minutes.
Total errors last 5m: {errors_5m}, last 1h: {errors_1h}.

## Action Required
1. Read the last 200 lines of `~/.openclaw/logs/openclaw.log`
2. Identify the FATAL/CRASH entries
3. Determine root cause
4. Propose fix or escalate to temujin for code changes
"""
        )
        mark_fired("error_spike:fatal")
        actions_created += 1

    # Rule 2: High error rate (non-fatal) — investigate
    elif errors_5m > 50 and not is_cooled_down("error_spike:high") and not has_pending_task("jochi", "Investigate error spike"):
        create_task(
            "jochi", "normal",
            f"Investigate error spike: {errors_5m} errors in 5m",
            f"""## Context
The tick detected {errors_5m} errors in the last 5 minutes (1h total: {errors_1h}).
No FATAL errors, but error rate is elevated.

## Action Required
1. Check `~/.openclaw/logs/openclaw.log` for error patterns
2. Determine if this is a transient spike or ongoing issue
3. Report findings and recommend action
"""
        )
        mark_fired("error_spike:high")
        actions_created += 1

    # Rule 3: Service down — create restart task
    for svc in ["neo4j", "redis"]:
        if services.get(svc) == "down" and not is_cooled_down(f"service_down:{svc}") and not has_pending_task("ogedei", f"Restart {svc}"):
            create_task(
                "ogedei", "high",
                f"Restart {svc} — service is DOWN",
                f"""## Context
The tick health check shows {svc} is DOWN.
Gateway status: {gateway.get('status', '?')}, HTTP: {gateway.get('http', '?')}

## Action Required
1. Check if {svc} process is running: `pgrep -f {svc}`
2. If not running, restart it:
   - Neo4j: `brew services restart neo4j` or `neo4j start`
   - Redis: `brew services restart redis` or `redis-server`
3. Verify it's back up
4. Check logs for why it went down
"""
            )
            mark_fired(f"service_down:{svc}")
            actions_created += 1

    # Rule 4: High CPU
    cpu = process.get("cpu_pct", 0)
    if cpu > 80 and not is_cooled_down("high_cpu") and not has_pending_task("ogedei", "Investigate high CPU"):
        create_task(
            "ogedei", "normal",
            f"Investigate high CPU usage: {cpu}%",
            f"""## Context
OpenClaw gateway CPU is at {cpu}%.
Memory: {process.get('mem_pct', 0)}%, RSS: {process.get('rss_kb', 0)}KB

## Action Required
1. Check what's consuming CPU: `top -l 1 -o cpu`
2. Check if there are runaway sessions or loops
3. Report findings
"""
        )
        mark_fired("high_cpu")
        actions_created += 1

    # Rule 5: High memory
    rss_mb = process.get("rss_kb", 0) / 1024
    if rss_mb > 900 and not is_cooled_down("high_memory") and not has_pending_task("ogedei", "Investigate high memory"):
        create_task(
            "ogedei", "normal",
            f"Investigate high memory usage: {rss_mb:.0f}MB RSS",
            f"""## Context
OpenClaw gateway RSS is {rss_mb:.0f}MB (threshold: 900MB).

## Action Required
1. Check session count and context usage
2. Run `openclaw doctor` for cleanup recommendations
3. Consider restarting gateway if memory is climbing
"""
        )
        mark_fired("high_memory")
        actions_created += 1

    # Rule 6: Time-to-first-action stall detection
    if actions_created < MAX_ACTIONS_PER_CYCLE:
        try:
            from neo4j_v2_core import TaskStore
            def detect_stalls_v2():
                store = TaskStore()
                try:
                    orphans = store.recover_orphans(grace_minutes=15)
                    return [{"task_id": t["task_id"], "agent": t.get("assigned_to", "unknown"),
                             "warning": f"Stalled task recovered: {t['task_id']}"} for t in orphans]
                finally:
                    store.close()
            stall_warnings = detect_stalls_v2()
            for stall in stall_warnings:
                stalled_agent = stall.get("agent", "unknown")
                task_id = stall.get("task_id", "unknown")
                warning_text = stall.get("warning", f"Stalled task: {task_id}")

                # Use task-specific cooldown key to prevent repeated escalations
                cooldown_key = f"task_stall:{stalled_agent}:{task_id}"

                # Route investigation away from the stalled agent
                # NOTE: kublai is NOT in DISPATCH_AGENTS, so never route tasks to kublai
                target = "ogedei" if stalled_agent == "jochi" else "jochi"

                # Check: not in cooldown, no existing investigation for THIS specific stalled task
                pending_title = f"Investigate stalled task: {stalled_agent}"

                if not is_cooled_down(cooldown_key) and not has_pending_task(target, pending_title) and actions_created < MAX_ACTIONS_PER_CYCLE:
                    create_task(
                        target, "normal",
                        f"Investigate stalled task: {stalled_agent} {task_id[:20]}",
                        f"""## Context
{warning_text}

An active task has been sitting for over 15 minutes with no progress.
This likely indicates a stuck execution, a task that was never picked up, or a silent failure.

## Action Required
1. Check {stalled_agent}'s task directory for the stalled task file
2. Check task-watcher logs for dispatch/execution errors: `~/.openclaw/agents/main/logs/task-watcher.log`
3. Check if the agent's Claude Code process is running: `pgrep -f "claude.*{stalled_agent}"`
4. Either re-queue the task, cancel it, or escalate
5. Report findings
""",
                        source="stall-detector",
                    )
                    mark_fired(cooldown_key)
                    actions_created += 1
        except Exception as e:
            stall_warnings = []
            log(f"TICK: stall detection error: {e}")

    # Rule 7: Low resolution compliance — trigger fix-missing-resolutions
    # FIX 2026-03-11: System detected 0% compliance but created no tasks
    resolution = tick.get("resolution", {})
    compliance_pct = resolution.get("compliance_pct", 100)
    without_count = resolution.get("without", 0)

    if (compliance_pct < 90 and without_count > 0
        and not is_cooled_down("resolution_compliance")
        and not has_pending_task("ogedei", "Fix missing resolution sections")):
        create_task(
            "ogedei", "normal",
            f"Fix missing resolution sections: {without_count} tasks at {compliance_pct}% compliance",
            f"""## Context
Resolution compliance is at {compliance_pct}% (threshold: 90%).
{without_count} task(s) are missing resolution sections.

## Action Required
Run: `python3 scripts/fix-missing-resolutions.py --all-agents --execute`

This will:
1. Scan all agent task directories for incomplete reports
2. Create follow-up tasks to add resolution sections
3. Improve task completion quality metrics
""",
            source="tick-resolution-gate",
        )
        mark_fired("resolution_compliance")
        actions_created += 1

    # Rule 8: CRITICAL fleet anomaly auto-investigation (R013/K009)
    # FIX 2026-03-12: Addresses "92% failure rate persisted 10+ ticks without investigation" incident
    # FIX 2026-03-12 12:35: Implements adaptive cooldown based on cumulative CRITICAL duration
    # Creates direct investigation task when CRITICAL severity detected, bypassing message dispatch
    CRITICAL_STATE_FILE = str(LOGS_DIR / "critical-anomaly-state.json")

    def get_critical_state():
        """Load or initialize CRITICAL anomaly tracking state."""
        try:
            with open(CRITICAL_STATE_FILE) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {
                "current_anomaly": None,
                "started_at": None,
                "total_duration_seconds": 0,
                "tasks_created": 0,
                "last_task_at": None
            }

    def save_critical_state(state):
        """Save CRITICAL anomaly tracking state."""
        try:
            os.makedirs(os.path.dirname(CRITICAL_STATE_FILE), exist_ok=True)
            with open(CRITICAL_STATE_FILE, "w") as f:
                json.dump(state, f, indent=2)
        except OSError:
            pass  # State persistence is optional

    def get_adaptive_cooldown(duration_minutes):
        """
        Return cooldown based on cumulative CRITICAL duration.
        - First 30 min: 5 min cooldown (rapid response)
        - 30-60 min: 10 min cooldown (continued vigilance)
        - 60+ min: 15 min cooldown (persistent issue)
        This ensures long-running CRITICAL states get more frequent investigation.
        """
        if duration_minutes < 30:
            return 300   # 5 minutes
        elif duration_minutes < 60:
            return 600   # 10 minutes
        else:
            return 900   # 15 minutes

    try:
        throughput = tick.get("throughput", {})
        anomaly_type = throughput.get("anomaly_type", "")
        severity = throughput.get("severity", "")
        consecutive = throughput.get("consecutive", 0)
        failure_rate = throughput.get("failure_rate", 0)

        # CRITICAL triggers: HIGH_FAILURE_RATE, AUTH_HEARTBEAT failure, or circuit-breaker stuck
        auth_heartbeat_failed = tick.get("auth_heartbeat", {}).get("failed_checks", 0)
        circuit_stuck = tick.get("circuit_breaker", {}).get("still_open", 0)

        # Expanded CRITICAL detection: check severity OR direct metrics
        # This catches cases where severity field is missing but metrics are critical
        is_critical = (
            severity == "CRITICAL" or
            (failure_rate >= 75 and consecutive >= 3) or  # 3+ ticks of 75%+ failure
            auth_heartbeat_failed >= 1 or
            circuit_stuck >= 1
        )

        # Initialize anomaly_desc BEFORE conditional to prevent UnboundLocalError
        # FIX 2026-03-12: Addresses "cannot access local variable 'anomaly_desc'" error in TICK logs
        anomaly_desc = "NONE"

        if is_critical:
            # Build anomaly description
            anomaly_desc = anomaly_type if anomaly_type else "UNKNOWN"
            if auth_heartbeat_failed >= 1:
                anomaly_desc += " + AUTH_HEARTBEAT_FAILURE"
            if circuit_stuck >= 1:
                anomaly_desc += " + CIRCUIT_BREAKER_STUCK"
            if failure_rate >= 75 and severity != "CRITICAL":
                anomaly_desc += f" (failure_rate={failure_rate}%, consecutive={consecutive})"

            # Load and update CRITICAL state tracking
            state = get_critical_state()
            now = time.time()

            # Check if this is the same anomaly or a new one
            if state["current_anomaly"] == anomaly_desc and state["started_at"]:
                # Same anomaly - update duration
                duration_so_far = (now - state["started_at"]) + state["total_duration_seconds"]
            else:
                # New anomaly - reset tracking
                state["current_anomaly"] = anomaly_desc
                state["started_at"] = now
                state["total_duration_seconds"] = 0
                state["tasks_created"] = 0
                state["last_task_at"] = None
                duration_so_far = 0

            # Calculate adaptive cooldown based on cumulative duration
            adaptive_cooldown = get_adaptive_cooldown(duration_so_far / 60)

            # Check if we should create a task
            should_create = False
            if state["last_task_at"] is None:
                # First task for this anomaly - create immediately
                should_create = True
            elif (now - state["last_task_at"]) >= adaptive_cooldown:
                # Cooldown expired - create another task
                should_create = True

            if should_create and actions_created < MAX_ACTIONS_PER_CYCLE:
                # Idempotency guard: skip if jochi already has a pending CRITICAL investigation.
                # Task titles include a timestamp suffix making them unique, so has_pending_task()
                # won't catch duplicates without this prefix-based check.
                # This prevents queue spam when the anomaly outlasts task processing time.
                # ROUTE TO JOCHI (not ogedei): When HIGH_FAILURE_RATE fires, ogedei is likely
                # the failing agent. Routing the investigation back to ogedei creates a circular
                # cascade. jochi (analyst) investigates fleet-wide issues instead.
                if has_pending_task("jochi", "CRITICAL ("):
                    log(f"TICK: CRITICAL ({anomaly_desc}) — jochi already has pending CRITICAL task, skipping (idempotency guard)")
                    # Recovery path: when PENDING_NO_DISPATCH is stuck AND the investigation task
                    # is also pending, creating more tasks won't help — directly restart the
                    # dispatch service. This breaks the circular stall without queue dependency.
                    if "PENDING_NO_DISPATCH" in anomaly_desc:
                        restart_result = _attempt_dispatch_restart(log)
                        log(f"TICK: PENDING_NO_DISPATCH direct recovery attempted: {restart_result}")
                else:
                    escalation_level = 1 + (state["tasks_created"] // 3)  # Escalate every 3 tasks
                    create_task(
                        "jochi", "high",
                        f"CRITICAL ({escalation_level}{'st' if escalation_level == 1 else 'nd' if escalation_level == 2 else 'rd' if escalation_level == 3 else 'th'}): Investigate fleet-wide {anomaly_desc} - {int(now)}",
                        f"""## Context
CRITICAL fleet anomaly detected — requires immediate investigation.

**Anomaly Type:** {anomaly_desc}
**Severity:** {severity if severity else 'CRITICAL (detected from metrics)'}
**Failure Rate:** {failure_rate}%
**Consecutive Ticks:** {consecutive}
**Auth Heartbeat Failures:** {auth_heartbeat_failed}
**Circuit Breaker Stuck:** {circuit_stuck}

**Anomaly Duration:** {duration_so_far / 60:.1f} minutes (cumulative)
**Tasks Created for This Anomaly:** {state['tasks_created'] + 1}
**Escalation Level:** {escalation_level}

## Action Required
1. **Check AUTH_HEARTBEAT:** Run `python3 scripts/credential-health-monitor.py`
   - Verify all agents have valid API credentials
   - Check for DashScope vs Anthropic token issues
2. **Check circuit-breaker state:** Read `logs/circuit-breaker-state.json`
   - If stuck_open >= 1, reset via `python3 scripts/reset-circuit-breaker.py`
3. **Review recent task failures:** Check `logs/failure-patterns.jsonl`
4. **Verify model configuration:** Check `~/.openclaw/agents/*/config.json`
5. **Report findings** and fix or escalate

This is an automated rule (K009/R013) with adaptive cooldown.
Next task will be created in {adaptive_cooldown / 60:.0f} minutes if CRITICAL persists.
""",
                        source="critical-fleet-rule",
                    )
                    state["tasks_created"] += 1
                    state["last_task_at"] = now
                    save_critical_state(state)
                    actions_created += 1
                    log(f"TICK: CRITICAL anomaly detected — created investigation task for {anomaly_desc} (duration: {duration_so_far / 60:.1f}m, tasks: {state['tasks_created']}, cooldown: {adaptive_cooldown / 60:.0f}m)")
            else:
                time_since_last = now - state["last_task_at"] if state["last_task_at"] else adaptive_cooldown
                log(f"TICK: CRITICAL anomaly ({anomaly_desc}) detected — next task in {max(0, adaptive_cooldown - time_since_last) / 60:.1f}m (duration: {duration_so_far / 60:.1f}m)")
        else:
            # Anomaly cleared - reset state
            state = get_critical_state()
            if state["current_anomaly"]:
                log(f"TICK: CRITICAL anomaly ({state['current_anomaly']}) cleared after {(time.time() - state['started_at']) / 60:.1f}m")
                state["current_anomaly"] = None
                state["started_at"] = None
                state["total_duration_seconds"] = 0
                state["tasks_created"] = 0
                state["last_task_at"] = None
                save_critical_state(state)

    except Exception as e:
        log(f"TICK: CRITICAL fleet anomaly rule ERROR: {e}")
        # Don't let this rule failure crash the entire tick_actions() function

    if actions_created >= MAX_ACTIONS_PER_CYCLE:
        log(f"TICK: hit MAX_ACTIONS_PER_CYCLE={MAX_ACTIONS_PER_CYCLE}, stopping early")

    if actions_created == 0:
        log(f"TICK: {decision} — no actions needed")
    else:
        log(f"TICK: {decision} — created {actions_created} action(s)")

    return actions_created


# ============================================================
# TOCK ACTIONS (every 30 minutes)
# ============================================================
def tock_actions():
    """Rule-based actions from tock (agent effectiveness) data."""
    if not os.path.exists(TOCK_LATEST):
        log("TOCK: No latest.json found, skipping")
        return 0

    try:
        with open(TOCK_LATEST) as f:
            tock = json.load(f)
    except Exception as e:
        log(f"TOCK: Failed to parse latest.json: {e}")
        return 0

    # Staleness check — skip entirely if tock data is too old
    tock_age = _file_age_secs(TOCK_LATEST)
    if tock_age > MAX_TOCK_AGE_SECS:
        log(f"TOCK: WARNING — latest.json is {tock_age:.0f}s old, skipping stale data")
        return 0

    actions_created = 0
    agents = tock.get("agents", {})
    cron = tock.get("cron", {})
    queues = tock.get("queues", {})
    assessment = tock.get("llm_assessment", {})

    # Log when running on heuristic fallback (LLM unavailable)
    if assessment.get("model") == "heuristic-fallback":
        log("TOCK: WARNING — LLM assessment unavailable, using heuristic fallback")

    # Rule 1: Cron jobs erroring repeatedly
    # Cron fix tasks route to ogedei via /kurultai-health skill hint (ops domain)
    # This prevents "fix" keyword from routing to temujin (implementation domain)
    for job in cron.get("jobs", []):
        consec = job.get("consecutive_errors", 0)
        name = job.get("name", "?")
        if consec >= 3 and not is_cooled_down(f"cron_fix:{name}"):
            # Check any agent for pending task (not just temujin)
            has_pending = any(has_pending_task(agent, f"Fix cron job: {name}") for agent in VALID_AGENTS)
            if not has_pending and actions_created < MAX_ACTIONS_PER_CYCLE:
                # Force ops domain via skill_hint (fixes "fix"→implementation routing)
                create_task(
                    None, "high",  # None = auto-route via task_intake
                f"Fix cron job: {name} ({consec} consecutive errors)",
                f"""## Context
Cron job "{name}" has failed {consec} consecutive times.
Last status: {job.get('status', '?')}
Last duration: {job.get('last_duration_ms', 0)}ms

## Action Required
1. Check the cron job configuration: `openclaw cron list`
2. Try running it manually: `openclaw cron run <job-id>`
3. Check logs for the error
4. Fix the underlying issue (timeout, script error, etc.)
""",
                    skill_hint="/kurultai-health",  # Force ops domain (cron=ogedei, not temujin)
                )
            mark_fired(f"cron_fix:{name}")
            actions_created += 1

    # Rule 2: Queue backlog — log only (creating tasks worsens backlog)
    total_pending = queues.get("total_pending", 0)
    if total_pending > 10 and not is_cooled_down("queue_backlog"):
        by_agent = queues.get("by_agent", {})
        backlog_detail = ", ".join(
            f"{a}={c}" for a, c in by_agent.items() if c > 0
        )
        log(f"TOCK: queue_backlog detected: {total_pending} pending ({backlog_detail}) — logging only, not creating task")
        mark_fired("queue_backlog")

    # Rule 2c (PRIORITY_FIX 2026-03-12): Queue Overflow Acceptance (K004)
    # When kublai is idle AND multiple agents are overloaded, kublai CLAIMS tasks
    # from overloaded agents instead of creating new triage tasks.
    # This implements /horde-review PRIORITY_FIX: "kublai acts as active coordinator,
    # not passive message-forwarder"
    kublai_queue = 0
    kublai_data = agents.get("kublai", {})
    kublai_tasks = kublai_data.get("tasks", {})
    kublai_queue = kublai_tasks.get("queue_depth", 0)

    # Find overloaded agents (queue >= 4)
    overloaded_agents = []
    for agent_name, agent_data in agents.items():
        if agent_name == "kublai":
            continue
        agent_queue = agent_data.get("tasks", {}).get("queue_depth", 0)
        if agent_queue >= 4:
            overloaded_agents.append((agent_name, agent_queue))

    # Trigger condition: kublai queue < 2 AND 2+ agents have queue >= 4
    if kublai_queue < 2 and len(overloaded_agents) >= 2 and not is_cooled_down("queue_overflow_acceptance"):
        # Import move_task from task-redistribute
        try:
            from task_redistribute import move_task, get_pending_tasks

            moved_count = 0
            max_to_claim = 3  # Don't take too many at once

            for overloaded_agent, agent_queue in overloaded_agents:
                if moved_count >= max_to_claim:
                    break

                # Get pending tasks from overloaded agent
                pending = get_pending_tasks(overloaded_agent)
                if not pending:
                    continue

                # Take the oldest task (first in queue)
                src_path, title, content, domain = pending[0]

                # Check if kublai can handle this task (coordination/routing domain)
                # kublai can handle: coordination, routing, queue analysis, triage
                kublai_domains = {"coordination", "routing", "queue", "monitor", "health", "ops"}
                can_handle = domain in kublai_domains or any(
                    kw in title.lower() for kw in ["triage", "queue", "status", "review", "investigate", "coordinate"]
                )

                if can_handle:
                    success, result = move_task(src_path, "kublai", dry_run=False)
                    if success:
                        log(f"QUEUE_OVERFLOW_ACCEPTANCE: Claimed task '{title[:50]}' from {overloaded_agent} (queue={agent_queue}) -> kublai (queue={kublai_queue})")
                        moved_count += 1
                    else:
                        log(f"QUEUE_OVERFLOW_ACCEPTANCE: Failed to move task from {overloaded_agent}: {result}")

            if moved_count > 0:
                mark_fired("queue_overflow_acceptance")
                log(f"QUEUE_OVERFLOW_ACCEPTANCE: kublai claimed {moved_count} task(s) from {len(overloaded_agents)} overloaded agent(s)")
            else:
                # No movable tasks found - log but don't create triage task
                log(f"QUEUE_OVERFLOW_ACCEPTANCE: Detected {len(overloaded_agents)} overloaded agents but no movable tasks found (kublai queue={kublai_queue})")

        except ImportError as e:
            log(f"QUEUE_OVERFLOW_ACCEPTANCE: Failed to import task_redistribute: {e}")
        except Exception as e:
            log(f"QUEUE_OVERFLOW_ACCEPTANCE: Error claiming tasks: {e}")

    # Rule 2b: Queue audit — fake completions detected
    queue_audit = tock.get("queue_audit", {})
    audit_requeued = queue_audit.get("requeued", 0)
    audit_fake = queue_audit.get("fake_found", 0)
    if audit_requeued > 0:
        log(f"TOCK: queue_audit auto-fixed {audit_requeued} fake completion(s)")
    if audit_fake > 3 and not is_cooled_down("queue_audit") and not has_pending_task("ogedei", "Investigate task queue") and actions_created < MAX_ACTIONS_PER_CYCLE:
        create_task(
            "ogedei", "high",
            f"Investigate task queue: {audit_fake} fake completions detected",
            f"""## Context
The queue audit detected {audit_fake} tasks marked as "done" that were never
actually executed by Claude Code. {audit_requeued} were automatically re-queued.

## Action Required
1. Check task-watcher logs for execution errors
2. Verify Claude Code (claude-agent) is functioning
3. Review workspace result files for agents with fake completions
4. Ensure the execution chain is working: task-watcher -> agent-task-handler -> claude-agent
5. Report findings to Kublai
"""
        )
        mark_fired("queue_audit")
        actions_created += 1

    # Rule 3: Agent stalled — route to jochi (analyst) for investigation
    # NEVER route to the stalled agent itself (causes deadlock — see circular triage bug 2026-03-05)
    # Cross-validate tock queue_depth against filesystem to avoid false alarms from stale Neo4j data
    for name, data in agents.items():
        t = data.get("tasks", {})
        queue_depth = t.get("queue_depth", 0)
        completed = t.get("completed", 0)
        running = t.get("running", 0)
        if queue_depth > 0 and completed == 0 and running == 0:
            # Filesystem cross-validation: tock queue_depth can be stale (from Neo4j).
            # Count actual pending .md files (not terminal states, not .executing) before alerting.
            fs_pending = 0
            fs_pending_files = []
            agent_task_dir = f"{AGENT_DIR}/{name}/tasks"
            if os.path.exists(agent_task_dir):
                for fname in os.listdir(agent_task_dir):
                    # Skip terminal states and executing files
                    if fname.startswith('.'):
                        continue
                    # Check for terminal state patterns
                    # FIX 2026-03-12: Use 'in' check for .done to catch .done-{uuid}.md variants
                    if ".done" in fname or any(fname.endswith(pattern) for pattern in (
                        ".resolved.md",       # Resolved tasks
                        ".cancelled.md",      # Cancelled tasks
                        ".obsolete.md",       # Obsolete tasks
                    )):
                        continue
                    if '.executing' in fname:
                        continue
                    if fname.endswith('.md'):
                        fs_pending += 1
                        fs_pending_files.append(fname)
            if fs_pending == 0:
                log(f"TICK: stall alert suppressed for {name} — tock reports queue_depth={queue_depth} but filesystem has 0 pending tasks (stale Neo4j data)")
                continue

            # FIX 2026-03-20: Staleness check — skip triage if all pending tasks are
            # less than 10 minutes old (agent hasn't had time to process yet)
            all_recent = True
            now = time.time()
            for fname in fs_pending_files:
                fpath = os.path.join(agent_task_dir, fname)
                try:
                    age_seconds = now - os.path.getmtime(fpath)
                    if age_seconds > 600:  # 10 minutes
                        all_recent = False
                        break
                except OSError:
                    pass
            # FIX 2026-03-23: Changed AND to OR. Previous AND condition failed for bursts
            # of 4+ tasks all <10 min old — fs_pending > 3 caused the condition to be false
            # even when all tasks were brand-new and the agent simply hadn't had time to
            # process them yet. OR correctly suppresses triage if EITHER all tasks are recent
            # OR the queue is small enough (<=3) that it's likely transient, not a real stall.
            if all_recent or fs_pending <= 3:
                log(f"TICK: stall alert suppressed for {name} — {fs_pending} pending tasks are all <10 min old (agent hasn't had time to process)")
                continue

            # Guard: if jochi is stalled, route to ogedei (ops agent) instead (prevent self-routing deadlock)
            # NOTE: kublai is NOT in DISPATCH_AGENTS, so never route tasks to kublai
            target = "ogedei" if name == "jochi" else "jochi"

            # FIX 2026-03-20: Dedup guard — also check if target already has ANY triage
            # task for this agent created in the last 30 minutes (prevents cascade)
            has_recent_triage = False
            target_task_dir = f"{AGENT_DIR}/{target}/tasks"
            if os.path.exists(target_task_dir):
                for fname in os.listdir(target_task_dir):
                    if f"triage" in fname.lower() or f"stall" in fname.lower():
                        fpath = os.path.join(target_task_dir, fname)
                        try:
                            age = now - os.path.getmtime(fpath)
                            if age < 1800:  # 30 minutes
                                has_recent_triage = True
                                break
                        except OSError:
                            pass
            if has_recent_triage:
                log(f"TICK: stall alert suppressed for {name} — {target} already has a recent triage task (dedup)")
                continue

            # FIX 2026-03-29: Circuit breaker — don't create triage tasks for overloaded targets.
            # When the target agent already has a large backlog, adding another triage task
            # makes the spiral worse (triage tasks crowd out real work).
            target_pending = 0
            target_task_dir_cb = f"{AGENT_DIR}/{target}/tasks"
            if os.path.exists(target_task_dir_cb):
                for fname_cb in os.listdir(target_task_dir_cb):
                    if fname_cb.startswith('.'):
                        continue
                    if ".done" in fname_cb or fname_cb.endswith((".resolved.md", ".cancelled.md", ".obsolete.md")):
                        continue
                    if '.executing' in fname_cb:
                        continue
                    if fname_cb.endswith('.md'):
                        target_pending += 1
            if target_pending > 10:
                log(f"TICK: stall alert suppressed for {name} — target {target} already has {target_pending} pending tasks (circuit breaker)")
                continue

            if not is_cooled_down(f"agent_stalled:{name}") and not has_pending_task(target, f"Triage stalled agent: {name}") and actions_created < MAX_ACTIONS_PER_CYCLE:
                # FIX 2026-03-20: Triage tasks are coordination work, not implementation.
                # Explicitly set skill_hint=None to prevent auto-detection from assigning
                # /horde-implement. Also set completion_gate_optout for triage tasks.
                create_task(
                    target, "normal",
                    f"Triage stalled agent: {name} has {queue_depth} queued tasks with 0 completions",
                    f"""---
completion_gate_optout: true
---

## Context
Agent {name} has {queue_depth} tasks in file queue but 0 completions
in the last 30 minutes and nothing currently running.

## Action Required
1. Review {name}'s pending tasks
2. Determine if tasks should be redistributed or if there's a blocker
3. Take corrective action (reassign, cancel stale tasks, or investigate)
4. Report findings to kublai for coordination
""",
                    skill_hint="none",  # Explicit: triage is coordination, not implementation
                )
                mark_fired(f"agent_stalled:{name}")
                actions_created += 1

    # Rule 4: LLM assessment says HIGH or CRITICAL
    # Route to jochi (analyst), NOT kublai — kublai is often idle when this fires,
    # creating a circular deadlock (see circular triage bug 2026-03-05)
    severity = assessment.get("severity", "LOW")
    if severity in ["HIGH", "CRITICAL"] and not is_cooled_down("tock_severity") and not has_pending_task("jochi", "Tock assessment:") and actions_created < MAX_ACTIONS_PER_CYCLE:
        action = assessment.get("recommended_action", "unknown")
        bottleneck = assessment.get("bottleneck", "unknown")
        create_task(
            "jochi", "high",
            f"Tock assessment: {severity} — {bottleneck}",
            f"""## Context
The 30-minute tock assessment flagged severity: {severity}
Bottleneck: {bottleneck}
Workload: {assessment.get('workload_balance', '?')}
Coordination: {assessment.get('coordination_gap', '?')}
Recommended action: {action}

## Action Required
Review the tock data at `~/.openclaw/agents/main/logs/tock/latest.json`
and take the recommended action or delegate to the appropriate agent.
"""
        )
        mark_fired("tock_severity")
        actions_created += 1

    if actions_created >= MAX_ACTIONS_PER_CYCLE:
        log(f"TOCK: hit MAX_ACTIONS_PER_CYCLE={MAX_ACTIONS_PER_CYCLE}, stopping early")

    if actions_created == 0:
        log(f"TOCK: severity={severity} — no actions needed")
    else:
        log(f"TOCK: created {actions_created} action(s)")

    return actions_created


# ============================================================
# KURULTAI ACTIONS (every hour)
# ============================================================
def kurultai_actions():
    """Process agent feedback from Neo4j and create implementation tasks."""
    actions_created = 0

    try:
        from neo4j_task_tracker import neo4j_session

        with neo4j_session() as session:
            # Get pending feedback sorted by priority
            result = session.run("""
                MATCH (f:AgentFeedback {status: 'pending_review'})
                RETURN f.id AS id, f.agent AS agent, f.feedback AS feedback,
                       f.priority AS priority, f.proposals AS proposals
                ORDER BY
                    CASE f.priority
                        WHEN 'CRITICAL' THEN 1
                        WHEN 'HIGH' THEN 2
                        WHEN 'MEDIUM' THEN 3
                        ELSE 4
                    END
                LIMIT 10
            """)
            feedbacks = [dict(r) for r in result]

            if not feedbacks:
                log("KURULTAI: No pending feedback to review")
                return 0

            log(f"KURULTAI: Found {len(feedbacks)} pending feedback items")

            for fb in feedbacks:
                fb_id = fb.get("id", "?")
                agent = fb.get("agent", "?")
                priority = fb.get("priority", "MEDIUM")
                feedback_text = fb.get("feedback", "")[:500]

                # Parse proposals if present
                proposals = []
                try:
                    proposals = json.loads(fb.get("proposals", "[]"))
                except Exception:
                    pass

                # Only auto-create tasks for HIGH and CRITICAL
                if priority in ["CRITICAL", "HIGH"] and actions_created < MAX_ACTIONS_PER_CYCLE:
                    # Determine target agent based on feedback content
                    target = _route_feedback(feedback_text)
                    task_priority = "high" if priority == "CRITICAL" else "normal"

                    if not is_cooled_down(f"feedback_review:{fb_id}") and not has_pending_task(target, "Implement feedback from"):
                        create_task(
                            target, task_priority,
                            f"Implement feedback from {agent}: {feedback_text[:60]}",
                            f"""## Agent Feedback (from {agent}, priority: {priority})

{feedback_text}

## Proposals
{json.dumps(proposals, indent=2) if proposals else "No specific proposals"}

## Action Required
1. Review the feedback above
2. Implement the proposed changes if feasible
3. Report results back
"""
                        )
                        mark_fired(f"feedback_review:{fb_id}")
                        actions_created += 1

                        # Mark feedback as actioned in Neo4j
                        session.run("""
                            MATCH (f:AgentFeedback {id: $id})
                            SET f.status = 'actioned',
                                f.actioned_at = datetime(),
                                f.actioned_by = 'kublai-actions'
                        """, id=fb_id)

                else:
                    # MEDIUM/LOW — just mark as reviewed, don't create tasks
                    session.run("""
                        MATCH (f:AgentFeedback {id: $id})
                        SET f.status = 'reviewed',
                            f.reviewed_at = datetime()
                    """, id=fb_id)

    except ImportError:
        log("KURULTAI: neo4j driver not available")
    except Exception as e:
        log(f"KURULTAI: Error processing feedback: {e}")

    if actions_created == 0:
        log("KURULTAI: no actionable feedback")
    else:
        log(f"KURULTAI: created {actions_created} action(s) from feedback")

    return actions_created


def _route_feedback(text):
    """Route feedback to the appropriate agent based on content.
    Delegates to canonical task_router.
    """
    agent = route_by_text(text)
    return agent if agent != "subagent" else "ogedei"


def main():
    parser = argparse.ArgumentParser(description="Kublai Actions — checkpoint action engine")
    parser.add_argument("--trigger", required=True, choices=["tick", "tock", "kurultai"],
                        help="Which checkpoint triggered this")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be done without creating tasks")
    args = parser.parse_args()

    try:
        if args.trigger == "tick":
            count = tick_actions()
        elif args.trigger == "tock":
            count = tock_actions()
        elif args.trigger == "kurultai":
            count = kurultai_actions()
        else:
            count = 0
    except Exception as e:
        log(f"FATAL: Unhandled exception in {args.trigger}_actions: {e}")
        count = 0

    print(f"ACTIONS: {count} task(s) created")
    return count


if __name__ == "__main__":
    main()
