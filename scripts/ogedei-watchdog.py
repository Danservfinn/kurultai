#!/usr/bin/env python3
"""
Ogedei Watchdog — Persistent quality-assurance daemon for the Kurultai.

Runs every 30 seconds between tock cycles. Fourteen checks per cycle:
  1. check_watcher_alive()         — pgrep task-watcher.py + log mtime
  2. check_stalled_tasks()         — .executing.md files > 15 min old
  3. verify_recent_completions()   — new .done.md → check for real Claude Code execution + quality gate
  4. periodic_queue_audit()        — full queue_audit.audit() every 30 min
  5. cleanup_malformed()           — remove .executing.completed.done artifacts > 24h
  6. check_reflection_pipeline()   — reflection-status.json age + step timing
  7. check_memory_health()         — memory_audit.py every 30 min (contamination, bloat, rules)
  8. check_routing_drift()         — keyword vs actual routing drift every 30 min
  9. check_agent_failure_rates()   — 1h failure rate per agent, writes health flags every 5 min
 10. check_queue_balance()         — auto-redistribute tasks from overloaded to underloaded agents
 11. check_cascade_risk()          — detect cascade failure patterns every 10 min
 12. check_quality_gate()          — verify completion quality on recent .done.md files
 13. update_self_healing_score()   — track and report self-healing metrics every hour
 14. check_watchdog_health()       — internal watchdog health check

Usage:
    python3 ogedei-watchdog.py --once    # single cycle
    python3 ogedei-watchdog.py --daemon  # persistent mode (30s poll)
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from threading import Event

sys.path.insert(0, str(Path(__file__).parent))
from json_state import locked_json_read, locked_json_update
from kurultai_paths import AGENTS_DIR, LOGS_DIR

# Force unbuffered output for launchd
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# Configuration
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# Configuration
SCRIPTS_DIR = Path(__file__).parent
STATE_FILE = LOGS_DIR / "ogedei-watchdog-state.json"
LOG_FILE = LOGS_DIR / "ogedei-watchdog.log"
WATCHER_PLIST = "com.kurultai.task-watcher"
WATCHER_LOG = LOGS_DIR / "task-watcher.log"

POLL_INTERVAL = 30        # seconds
STALE_EXECUTING_SECS = 900  # 15 minutes
WATCHER_LOG_MAX_AGE = 300   # 5 minutes
MALFORMED_MAX_AGE = 86400   # 24 hours
QUEUE_AUDIT_INTERVAL = 1800 # 30 minutes
MEMORY_AUDIT_INTERVAL = 1800 # 30 minutes
STALL_WARN_COOLDOWN = 600   # 10 minutes between repeated warnings for same file
REFLECTION_MAX_AGE = 4500   # 75 minutes — cron runs at :02, allow buffer
REFLECTION_STATUS = LOGS_DIR / "reflection-status.json"
REFLECTION_STEP_TIMING = LOGS_DIR / "reflection-step-timing.json"

# ============================================================
# P0 Self-Healing: Tiered Stale Task Recovery
# ============================================================
# Tier 1 (900s):  Log warning, check process liveness
# Tier 2 (1800s): Verify PID dead → clear lock → requeue
# Tier 3 (3600s): Escalate to Kublai with diagnostic bundle
TIER_WARN_S = 900          # 15 minutes - warn only
TIER_RECOVER_S = 1800      # 30 minutes - auto-recover if PID dead
TIER_ESCALATE_S = 3600     # 60 minutes - escalate to Kublai

# Recovery tracking to prevent thrashing
_recovery_cooldowns: dict[str, float] = {}  # task_path -> last recovery time
REFLECTION_STATUS = LOGS_DIR / "reflection-status.json"
REFLECTION_STEP_TIMING = LOGS_DIR / "reflection-step-timing.json"

AGENTS = ["kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei"]

stop_event = Event()
# Track last warning time per stalled file to avoid spamming
_stall_warned_at: dict[str, float] = {}


def log(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {level}: {msg}"
    # stdout is captured by launchd → LOG_FILE already; no direct write needed
    print(line)


def load_state():
    return locked_json_read(str(STATE_FILE), default={
        "last_audit": 0,
        "cycles": 0,
        "last_cycle": None,
        "watcher_restarts": 0,
        "stalled_warnings": 0,
        "fakes_detected": 0,
        "malformed_cleaned": 0,
        "audit_result": {},
    })


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with locked_json_update(str(STATE_FILE)) as data:
        data.clear()
        data.update(state)


# ============================================================
# Circuit breaker for agent health (loaded after log is available)
# ============================================================
try:
    from circuit_breaker import AgentCircuitBreaker
    _circuit_breaker = AgentCircuitBreaker()
except Exception as e:
    log(f"Circuit breaker init failed (non-fatal): {e}", "WARN")
    _circuit_breaker = None


# ============================================================
# Check 1: Is task-watcher alive?
# ============================================================
def check_watcher_alive(state):
    """Verify task-watcher.py is running and its log is fresh."""
    issues = []

    # Check process
    try:
        result = subprocess.run(
            ["pgrep", "-f", "task-watcher.py"],
            capture_output=True, text=True, timeout=5
        )
        alive = result.returncode == 0
    except Exception:
        alive = False

    if not alive:
        log("WATCHER DOWN — attempting restart via launchctl", "WARN")
        issues.append("task-watcher not running")
        try:
            result = subprocess.run(
                ["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{WATCHER_PLIST}"],
                capture_output=True, text=True, timeout=15
            )
            success = result.returncode == 0
            state["watcher_restarts"] = state.get("watcher_restarts", 0) + 1
            log("Restart issued via launchctl kickstart")
            record_gateway_restart(success)
        except Exception as e:
            log(f"Failed to restart watcher: {e}", "ERROR")
            record_gateway_restart(False)
        return issues

    # Check log freshness
    if WATCHER_LOG.exists():
        age = time.time() - WATCHER_LOG.stat().st_mtime
        if age > WATCHER_LOG_MAX_AGE:
            log(f"WATCHER LOG STALE — {age:.0f}s old (threshold: {WATCHER_LOG_MAX_AGE}s)", "WARN")
            issues.append(f"task-watcher log stale ({age:.0f}s)")

    return issues


# ============================================================
# Check 2: Stalled .executing tasks with Tiered Recovery (P0 Self-Healing)
# ============================================================

def verify_process_dead(task_path: Path) -> bool:
    """Verify the PID is actually dead before clearing lock."""
    pid_file = task_path.with_suffix(".pid")
    if not pid_file.exists():
        return True
    try:
        pid_str = pid_file.read_text().strip()
        pid = int(pid_str)
    except (ValueError, OSError):
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            if "claude-agent" in result.stdout or "claude" in result.stdout.lower():
                return False
            log(f"Orphaned PID {pid} for {task_path.name}")
            return True
    except Exception:
        pass
    return False


def recover_task(task_path: Path, agent: str, age_s: int, state: dict) -> bool:
    """Clear locks and requeue the task."""
    try:
        task_name = task_path.name
        base_name = task_name.replace(".executing.md", ".md")
        task_path.rename(task_path.parent / base_name)
        pid_file = task_path.with_suffix(".pid")
        if pid_file.exists():
            pid_file.unlink()
        state["tasks_recovered"] = state.get("tasks_recovered", 0) + 1
        _recovery_cooldowns[str(task_path)] = time.time()
        log(f"RECOVERED: {agent}/{base_name} (was {age_s:.0f}s old)")
        return True
    except Exception as e:
        log(f"RECOVERY FAILED for {agent}/{task_path.name}: {e}", "ERROR")
        return False


def escalate_to_kublai(task_path: Path, agent: str, age_s: int) -> bool:
    """Create high-priority task for Kublai investigation."""
    try:
        workspace = Path("/Users/kublai/.openclaw/agents/kublai/tasks")
        workspace.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        task_name = task_path.name.replace(".executing.md", "")
        escalation_file = workspace / f"ESCALATE-stale-task-{agent}-{task_name}-{timestamp}.md"
        task_content = task_path.read_text()[:500] if task_path.exists() else "(file not found)"
        escalation_content = f"""---
agent: kublai
priority: critical
created: {datetime.now().isoformat()}
task_type: escalation
source: ogedei-watchdog
original_task: {agent}/{task_name}
stalled_age_seconds: {age_s}
---

# Escalation: Stale Task Recovery

**Original Task:** {agent}/{task_name}
**Stalled For:** {age_s:.0f}s ({age_s // 60} min)

Investigate why this task is stuck and re-queue or cancel as appropriate.
Threshold: {TIER_ESCALATE_S}s
"""
        escalation_file.write_text(escalation_content)
        log(f"ESCALATED to Kublai: {escalation_file.name}")
        return True
    except Exception as e:
        log(f"ESCALATION FAILED: {e}", "ERROR")
        return False



# ============================================================
# Original check_stalled_tasks below (updated with tiered recovery)
# ============================================================
def check_stalled_tasks(state):
    """Find and recover .executing.md files based on tiered policy.
    
    Tier 1 (900s):  Log warning with cooldown
    Tier 2 (1800s): Verify PID dead -> clear lock -> requeue
    Tier 3 (3600s): Escalate to Kublai with diagnostic bundle
    """
    issues = []
    now = time.time()

    for agent in AGENTS:
        tasks_dir = AGENTS_DIR / agent / "tasks"
        if not tasks_dir.exists():
            continue
        for f in tasks_dir.iterdir():
            name = f.name
            if not name.endswith(".executing.md"):
                continue
            if ".completed" in name or ".done" in name or ".failed" in name:
                continue
            if not f.is_file():
                continue
            try:
                age = now - f.stat().st_mtime
            except OSError:
                continue

            if age < TIER_WARN_S:
                continue

            key = f"{agent}/{name}"
            task_path = f

            # Tier 1 (900-1800s): Warning only
            if age < TIER_RECOVER_S:
                last_warned = _stall_warned_at.get(key, 0)
                if (now - last_warned) >= STALL_WARN_COOLDOWN:
                    log(f"STALLED: {key} - {age:.0f}s old (Tier 1)", "WARN")
                    _stall_warned_at[key] = now
                    state["stalled_warnings"] = state.get("stalled_warnings", 0) + 1
                issues.append(f"{key} stalled {age:.0f}s")

            # Tier 2 (1800-3600s): Attempt recovery if PID dead
            elif age < TIER_ESCALATE_S:
                last_recovery = _recovery_cooldowns.get(key, 0)
                if (now - last_recovery) < STALL_WARN_COOLDOWN:
                    issues.append(f"{key} stalled {age:.0f}s (cooldown)")
                    continue

                if verify_process_dead(task_path):
                    log(f"RECOVERING: {key} - {age:.0f}s old (Tier 2)", "WARN")
                    if recover_task(task_path, agent, age, state):
                        issues.append(f"{key} recovered after {age:.0f}s")
                        _stall_warned_at.pop(key, None)
                    else:
                        issues.append(f"{key} recovery failed")
                else:
                    log(f"STALLED: {key} - {age:.0f}s old (Tier 2: PID alive)", "WARN")
                    issues.append(f"{key} stalled {age:.0f}s (alive)")

            # Tier 3 (3600s+): Escalate to Kublai
            else:
                last_esc = _recovery_cooldowns.get(f"{key}_escalation", 0)
                if (now - last_esc) < 3600:
                    issues.append(f"{key} stalled {age:.0f}s (escalated)")
                    continue

                log(f"ESCALATING: {key} - {age:.0f}s old (Tier 3)", "ERROR")
                if escalate_to_kublai(task_path, agent, age):
                    _recovery_cooldowns[f"{key}_escalation"] = now
                    issues.append(f"{key} escalated")
                else:
                    issues.append(f"{key} escalation failed")

    # Prune cooldown entries
    for key in list(_stall_warned_at):
        parts = key.split("/", 1)
        if len(parts) == 2:
            agent_part, fname = parts
            if not (AGENTS_DIR / agent_part / "tasks" / fname).exists():
                del _stall_warned_at[key]

    return issues


# ============================================================
# Check 3: Verify recent completions are real
# ============================================================
def verify_recent_completions(state):
    """Check new .done.md files for real Claude Code execution markers."""
    issues = []
    now = time.time()
    last_cycle = state.get("last_cycle_epoch", 0)

    # Import queue_audit functions
    try:
        sys.path.insert(0, str(SCRIPTS_DIR))
        from importlib import import_module
        # queue-audit.py has a hyphen, need importlib
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "queue_audit", str(SCRIPTS_DIR / "queue-audit.py")
        )
        qa = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(qa)
    except Exception as e:
        log(f"Cannot import queue-audit: {e}", "ERROR")
        return issues

    for agent in AGENTS:
        tasks_dir = AGENTS_DIR / agent / "tasks"
        if not tasks_dir.exists():
            continue
        for f in tasks_dir.iterdir():
            if ".done.md" not in f.name or not f.is_file():
                continue
            try:
                mtime = f.stat().st_mtime
            except OSError:
                continue
            # Only check files completed since last cycle
            if mtime <= last_cycle:
                continue
            # Skip test tasks
            try:
                content = f.read_text()
            except OSError:
                continue
            if qa.is_test_task(content):
                continue
            # Check result file
            result_path = qa.find_result_file(agent, mtime)
            if qa.is_fake(result_path, done_path=str(f)):
                log(f"FAKE completion: {agent}/{f.name}", "WARN")
                issues.append(f"{agent}/{f.name} fake completion")
                state["fakes_detected"] = state.get("fakes_detected", 0) + 1
                # Re-queue
                if qa.requeue(agent, str(f)):
                    log(f"  Re-queued: {agent}/{f.name}")
                    record_fake_completion_requeued(agent, f.name)

    return issues


# ============================================================
# Check 4: Periodic full queue audit (every 30 min)
# ============================================================
def periodic_queue_audit(state):
    """Run full queue audit every QUEUE_AUDIT_INTERVAL seconds."""
    issues = []
    now = time.time()
    last_audit = state.get("last_audit", 0)

    if (now - last_audit) < QUEUE_AUDIT_INTERVAL:
        return issues

    log("Running periodic queue audit")

    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "queue_audit", str(SCRIPTS_DIR / "queue-audit.py")
        )
        qa = importlib.util.module_from_spec(spec)
        # Temporarily set sys.argv for audit() which checks --dry-run
        old_argv = sys.argv
        sys.argv = ["queue-audit.py"]
        spec.loader.exec_module(qa)
        totals, details = qa.audit()
        sys.argv = old_argv

        state["last_audit"] = now
        state["audit_result"] = totals

        if totals.get("fake_found", 0) > 0:
            log(f"AUDIT: {totals['fake_found']} fakes, {totals['requeued']} requeued")
            issues.append(f"audit found {totals['fake_found']} fakes")

    except Exception as e:
        log(f"Queue audit failed: {e}", "ERROR")
        issues.append(f"audit error: {e}")

    return issues


# ============================================================
# Check 5: Clean up malformed file artifacts
# ============================================================
def cleanup_malformed(state):
    """Remove .executing.completed.done and similar malformed artifacts older than 24h."""
    issues = []
    now = time.time()
    cleaned = 0

    for agent in AGENTS:
        tasks_dir = AGENTS_DIR / agent / "tasks"
        if not tasks_dir.exists():
            continue
        for check_dir in [tasks_dir]:
            if not check_dir.exists():
                continue
            for f in check_dir.iterdir():
                if not f.is_file():
                    continue
                name = f.name
                # Detect malformed patterns
                is_malformed = (
                    ".executing.completed.done" in name or
                    ".executing.failed.done" in name or
                    ".executing.executing" in name
                )
                if not is_malformed:
                    continue
                try:
                    age = now - f.stat().st_mtime
                except OSError:
                    continue
                if age > MALFORMED_MAX_AGE:
                    try:
                        f.unlink()
                        cleaned += 1
                    except OSError:
                        pass

    if cleaned > 0:
        log(f"Cleaned {cleaned} malformed artifact(s)")
        state["malformed_cleaned"] = state.get("malformed_cleaned", 0) + cleaned
        issues.append(f"cleaned {cleaned} malformed files")

    return issues


# ============================================================
# Check 6: Reflection pipeline freshness
# ============================================================
def check_reflection_pipeline(state):
    """Verify the hourly reflection pipeline is running on schedule.

    Checks reflection-status.json age (should be < 75 min if cron is healthy).
    Also reads step timing data if available to flag slow steps.
    """
    issues = []
    now = time.time()

    if not REFLECTION_STATUS.exists():
        log("REFLECTION STATUS MISSING — hourly_reflection.sh may never have run", "WARN")
        issues.append("reflection-status.json missing")
        return issues

    try:
        age = now - REFLECTION_STATUS.stat().st_mtime
    except OSError:
        return issues

    if age > REFLECTION_MAX_AGE:
        age_min = int(age / 60)
        consecutive = state.get("reflection_misses", 0) + 1
        state["reflection_misses"] = consecutive
        log(f"REFLECTION STALE — {age_min}m old (threshold: {REFLECTION_MAX_AGE // 60}m, "
            f"consecutive misses: {consecutive})", "WARN")
        issues.append(f"reflection stale {age_min}m (miss #{consecutive})")
    else:
        state["reflection_misses"] = 0

    # Check step timing for slow steps (written by hourly_reflection.sh)
    if REFLECTION_STEP_TIMING.exists():
        try:
            with open(REFLECTION_STEP_TIMING) as f:
                timing = json.load(f)
            for step in timing.get("steps", []):
                duration = step.get("duration_s", 0)
                name = step.get("name", "?")
                if duration > 60:
                    log(f"REFLECTION SLOW STEP: {name} took {duration:.0f}s", "WARN")
                    issues.append(f"slow reflection step: {name} ({duration:.0f}s)")
        except Exception:
            pass

    return issues


# ============================================================
# Check 7: Memory health audit (contamination, bloat, rules)
# ============================================================
def check_memory_health(state):
    """Run memory_audit.py periodically to detect contamination, bloat, and rule excess."""
    issues = []
    now = time.time()
    last_mem_audit = state.get("last_memory_audit", 0)

    if (now - last_mem_audit) < MEMORY_AUDIT_INTERVAL:
        return issues

    log("Running periodic memory health audit")

    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "memory_audit", str(SCRIPTS_DIR / "memory_audit.py")
        )
        ma = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ma)
        results = ma.run_audit()

        state["last_memory_audit"] = now

        criticals = [r for r in results if r["severity"] == "critical"]
        warnings = [r for r in results if r["severity"] == "warning"]

        state["memory_audit_result"] = {
            "total": len(results),
            "critical": len(criticals),
            "warning": len(warnings),
            "ts": datetime.now().isoformat(),
        }

        if criticals:
            for r in criticals:
                log(f"MEMORY CRITICAL: {r['message']}", "WARN")
                issues.append(f"memory: {r['message']}")
            # Auto-fix contamination (highest severity, most damaging)
            contamination = [r for r in criticals if r["type"] == "contamination"]
            if contamination:
                fixed = ma.fix_contamination(contamination)
                if fixed:
                    log(f"AUTO-FIX: Cleared {fixed} contaminated memory file(s)")
                    state["memory_fixes"] = state.get("memory_fixes", 0) + fixed
                    record_memory_fix("contamination", fixed)

        if warnings:
            for r in warnings:
                log(f"MEMORY WARNING: {r['message']}", "WARN")
                issues.append(f"memory: {r['message']}")

            # Auto-fix bloat issues (context_bloat, intraday_bloat, stale_entries)
            # These are safe, reversible fixes that reduce token waste in task execution
            total_bloat_fixed = 0
            context_bloat = [r for r in warnings if r["type"] == "context_bloat"]
            if context_bloat:
                fixed = ma.fix_context_bloat(context_bloat)
                total_bloat_fixed += fixed
            intraday_bloat = [r for r in warnings if r["type"] == "intraday_bloat"]
            if intraday_bloat:
                fixed = ma.fix_intraday_bloat(intraday_bloat)
                total_bloat_fixed += fixed
            stale = [r for r in results if r["type"] == "stale_entries"]
            if stale:
                fixed = ma.fix_stale_entries(stale)
                total_bloat_fixed += fixed
            # Auto-fix dead rules (active but never evaluated past threshold)
            dead_rules = [r for r in results if r["type"] == "dead_rule"]
            if dead_rules:
                fixed = ma.fix_dead_rules(dead_rules)
                total_bloat_fixed += fixed

            if total_bloat_fixed:
                log(f"AUTO-FIX: Resolved {total_bloat_fixed} memory bloat/rule issue(s)")
                state["memory_fixes"] = state.get("memory_fixes", 0) + total_bloat_fixed
                record_memory_fix("bloat", total_bloat_fixed)

        # Prune deprecated rules (safe at any severity level, runs on "info" results)
        pruneable = [r for r in results if r["type"] == "pruneable_deprecated"]
        if pruneable:
            fixed = ma.fix_pruneable_deprecated(pruneable)
            if fixed:
                log(f"AUTO-FIX: Pruned {fixed} deprecated rule(s) from rules.json")
                state["memory_fixes"] = state.get("memory_fixes", 0) + fixed
                record_memory_fix("deprecated_rules", fixed)

        if not results:
            log("Memory audit: ALL CLEAR")

    except Exception as e:
        log(f"Memory audit failed: {e}", "ERROR")
        issues.append(f"memory audit error: {e}")

    return issues


# ============================================================
# Check 8: Routing keyword drift detection
# ============================================================
ROUTING_DRIFT_INTERVAL = 1800  # 30 minutes
ROUTING_DRIFT_LOG = LOGS_DIR / "routing-decisions.jsonl"
ROUTING_DRIFT_WARN_PCT = 30    # warn if >30% keyword mismatches

# Check 9: Agent failure rate monitoring
FAILURE_RATE_INTERVAL = 300    # 5 minutes
FAILURE_RATE_LOOKBACK_H = 1    # 1-hour window for short-term failure rate
FAILURE_RATE_THRESHOLD = 0.5   # warn if >50% failure rate
FAILURE_RATE_MIN_TASKS = 3     # minimum tasks before flagging
AGENT_HEALTH_FLAGS_FILE = LOGS_DIR / "agent-health-flags.json"

# Check 13: Auto queue balancing
QUEUE_BALANCE_INTERVAL = 300   # 5 minutes between balance checks
QUEUE_MAX_DEPTH = 8            # Trigger if agent has >8 tasks
QUEUE_MIN_DEPTH = 2            # Don't redistribute to agents with <2 tasks
QUEUE_IMBALANCE_THRESHOLD = 5  # Trigger if max-min difference > 5
QUEUE_MAX_MOVE_PER_CYCLE = 10  # Limit tasks moved per cycle

# Check 11: Cascade failure detection
CASCADE_CHECK_INTERVAL = 600   # 10 minutes between cascade risk checks
CASCADE_LOOKBACK_MINUTES = 30  # Lookback period for cascade detection

# Check 12: Quality gate
QUALITY_GATE_INTERVAL = 180    # 3 minutes between quality gate checks
QUALITY_LOOKBACK_MINUTES = 15  # Check completions from last 15 minutes

# Check 13: Self-healing score
SELF_HEALING_SCORE_INTERVAL = 3600  # 1 hour between score updates
SELF_HEALING_SCORE_HOURS = 24       # Calculate score over 24h window


def check_routing_drift(state):
    """Detect keyword routing vs actual routing disagreement.

    Reads recent routing decisions, re-runs route_by_text() on each,
    compares with actual destination. High drift means the keyword table
    is out of sync with LLM routing and needs updating.
    """
    issues = []
    now = time.time()
    last_check = state.get("last_routing_drift_check", 0)

    if (now - last_check) < ROUTING_DRIFT_INTERVAL:
        return issues

    try:
        from task_intake import route_by_text
    except Exception as e:
        log(f"Cannot import route_by_text for drift check: {e}", "ERROR")
        state["last_routing_drift_check"] = now
        return issues

    if not ROUTING_DRIFT_LOG.exists():
        state["last_routing_drift_check"] = now
        return issues

    # Read last 2 hours of routing decisions
    from datetime import timedelta
    cutoff = datetime.now() - timedelta(hours=2)
    decisions = []
    try:
        with open(ROUTING_DRIFT_LOG) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    ts = datetime.fromisoformat(entry["ts"])
                    if ts >= cutoff:
                        decisions.append(entry)
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue
    except Exception:
        state["last_routing_drift_check"] = now
        return issues

    # Only compare actual routings (skip explicit, mention, and diagnostic entries)
    _SKIP_METHODS = {"explicit", "mention", "explicit_misroute", "skill_reroute"}
    comparable = [d for d in decisions if d.get("method") not in _SKIP_METHODS]
    if not comparable:
        state["last_routing_drift_check"] = now
        state["routing_drift"] = {"total": 0, "mismatches": 0, "drift_pct": 0.0,
                                  "ts": datetime.now().isoformat()}
        return issues

    mismatches = []
    for d in comparable:
        task = d.get("task", "")
        actual = d.get("dest", "")
        keyword_result = route_by_text(task)
        if keyword_result != actual:
            mismatches.append({
                "task": task[:80],
                "actual": actual,
                "keyword_would": keyword_result,
            })

    total = len(comparable)
    drift_pct = (len(mismatches) / total * 100) if total > 0 else 0.0

    state["routing_drift"] = {
        "total": total,
        "mismatches": len(mismatches),
        "drift_pct": round(drift_pct, 1),
        "top_examples": mismatches[:5],
        "ts": datetime.now().isoformat(),
    }
    state["last_routing_drift_check"] = now

    if drift_pct > ROUTING_DRIFT_WARN_PCT and len(mismatches) >= 2:
        log(f"ROUTING DRIFT: {len(mismatches)}/{total} ({drift_pct:.0f}%) keyword mismatches", "WARN")
        for m in mismatches[:3]:
            log(f"  DRIFT: '{m['task'][:60]}' keyword={m['keyword_would']} actual={m['actual']}", "WARN")
        issues.append(f"routing drift {drift_pct:.0f}% ({len(mismatches)}/{total} mismatches)")
    elif mismatches:
        log(f"Routing drift: {len(mismatches)}/{total} ({drift_pct:.0f}%) — within tolerance")

    return issues


# ============================================================
# Check 9: Short-term agent failure rate monitoring
# ============================================================
def check_agent_failure_rates(state):
    """Compute 1-hour failure rates per agent and write health flags.

    Reads COMPLETED and FAILED events from the task ledger for the last hour.
    Writes agent-health-flags.json with per-agent failure status so that
    route_quality_tracker.should_divert() can use real-time data instead of
    relying solely on 7-day rolling averages.
    """
    issues = []
    now = time.time()
    last_check = state.get("last_failure_rate_check", 0)

    if (now - last_check) < FAILURE_RATE_INTERVAL:
        return issues

    try:
        from kurultai_ledger import read_ledger
    except Exception as e:
        log(f"Cannot import kurultai_ledger for failure rate check: {e}", "ERROR")
        state["last_failure_rate_check"] = now
        return issues

    events = read_ledger(hours=FAILURE_RATE_LOOKBACK_H)
    if not events:
        state["last_failure_rate_check"] = now
        return issues

    # Count completed and failed per agent
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

    # Build health flags
    flags = {}
    all_agents_with_tasks = set(list(agent_completed.keys()) + list(agent_failed.keys()))

    for agent in all_agents_with_tasks:
        completed = agent_completed.get(agent, 0)
        failed = agent_failed.get(agent, 0)
        total = completed + failed
        if total == 0:
            continue
        fail_rate = failed / total

        flag = {
            "completed_1h": completed,
            "failed_1h": failed,
            "total_1h": total,
            "fail_rate_1h": round(fail_rate, 3),
            "flagged": fail_rate >= FAILURE_RATE_THRESHOLD and total >= FAILURE_RATE_MIN_TASKS,
        }
        flags[agent] = flag

        if flag["flagged"]:
            log(f"HIGH FAILURE RATE: {agent} — {failed}/{total} ({fail_rate:.0%}) "
                f"failed in last {FAILURE_RATE_LOOKBACK_H}h", "WARN")
            issues.append(f"{agent} failure rate {fail_rate:.0%} ({failed}/{total} in 1h)")

    # Write health flags file for consumption by routing
    health_data = {
        "ts": datetime.now().isoformat(),
        "window_hours": FAILURE_RATE_LOOKBACK_H,
        "agents": flags,
    }

    try:
        AGENT_HEALTH_FLAGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(str(AGENT_HEALTH_FLAGS_FILE), "w") as f:
            json.dump(health_data, f, indent=2)
    except Exception as e:
        log(f"Failed to write agent health flags: {e}", "ERROR")

    state["last_failure_rate_check"] = now
    state["agent_failure_flags"] = {
        a: f["fail_rate_1h"] for a, f in flags.items() if f["flagged"]
    }

    return issues


# ============================================================
# Check 13: Auto queue balancing
# ============================================================
def check_queue_balance(state):
    """Check queue depths and auto-balance if imbalance detected.

    Redistributes tasks from overloaded agents to underloaded agents when:
    - Max queue depth > QUEUE_MAX_DEPTH (8 tasks)
    - Max-min difference > QUEUE_IMBALANCE_THRESHOLD (5 tasks)
    - At least one agent is underloaded (< QUEUE_MIN_DEPTH tasks)
    """
    issues = []
    now = time.time()
    last_check = state.get("last_queue_balance_check", 0)

    # Rate limiting: only check every QUEUE_BALANCE_INTERVAL
    if (now - last_check) < QUEUE_BALANCE_INTERVAL:
        return issues

    log("Checking queue balance")

    # Get current queue depths per agent
    depths = {}
    for agent in AGENTS:
        tasks_dir = AGENTS_DIR / agent / "tasks"
        if not tasks_dir.exists():
            depths[agent] = 0
            continue

        pending = 0
        # Count pending tasks by pattern
        for pattern in ["high-*.md", "normal-*.md", "low-*.md"]:
            pending += len(list(tasks_dir.glob(pattern)))

        # Subtract executing and done tasks (they may match the patterns above)
        for f in tasks_dir.glob("*"):
            if ".executing" in f.name or ".done" in f.name or ".failed" in f.name:
                pending -= 1

        depths[agent] = max(0, pending)

    # Calculate imbalance metrics
    max_depth = max(depths.values()) if depths else 0
    min_depth = min(depths.values()) if depths else 0
    imbalance = max_depth - min_depth

    state["last_queue_balance_check"] = now
    state["queue_depths"] = depths

    # Check if action is needed
    if imbalance < QUEUE_IMBALANCE_THRESHOLD or max_depth < QUEUE_MAX_DEPTH:
        log(f"Queue balanced: max={max_depth}, min={min_depth}, imbalance={imbalance}")
        return issues

    # Identify overloaded and underloaded agents
    overloaded = [a for a, d in sorted(depths.items(), key=lambda x: -x[1]) if d > QUEUE_MAX_DEPTH]
    underloaded = [a for a, d in sorted(depths.items(), key=lambda x: x[1]) if d < QUEUE_MIN_DEPTH]

    if not overloaded:
        log(f"No overloaded agents (max={max_depth}, threshold={QUEUE_MAX_DEPTH})")
        return issues

    if not underloaded:
        log(f"No underloaded agents to receive tasks (min={min_depth}, threshold={QUEUE_MIN_DEPTH})")
        issues.append(f"queue_imbalance: {overloaded} overloaded but no underloaded agents")
        return issues

    log(f"QUEUE IMBALANCE: overloaded={[f'{a}={depths[a]}' for a in overloaded]}, "
        f"underloaded={[f'{a}={depths[a]}' for a in underloaded]}")

    # Redistribute tasks from overloaded to underloaded agents
    moved = 0
    import shutil

    for source in overloaded:
        if moved >= QUEUE_MAX_MOVE_PER_CYCLE:
            break

        tasks_dir = AGENTS_DIR / source / "tasks"
        source_tasks = []

        # Collect all pending task files
        for pattern in ["high-*.md", "normal-*.md", "low-*.md"]:
            source_tasks.extend(tasks_dir.glob(pattern))

        # Filter to actual pending tasks (exclude executing, done, failed)
        source_tasks = [
            t for t in source_tasks
            if ".executing" not in t.name and ".done" not in t.name and ".failed" not in t.name
        ]

        # Sort by modification time (oldest first for fairness)
        source_tasks.sort(key=lambda f: f.stat().st_mtime)

        for i, task_path in enumerate(source_tasks):
            if moved >= QUEUE_MAX_MOVE_PER_CYCLE:
                break
            if not underloaded:
                break

            # Round-robin to underloaded agents
            target = underloaded[moved % len(underloaded)]

            try:
                target_dir = AGENTS_DIR / target / "tasks"
                target_dir.mkdir(parents=True, exist_ok=True)
                target_path = target_dir / task_path.name

                # Avoid name collisions (unlikely but possible)
                if target_path.exists():
                    # Add a small suffix to make unique
                    base_name = task_path.stem
                    ext = task_path.suffix
                    target_path = target_dir / f"{base_name}-moved{ext}"

                shutil.move(str(task_path), str(target_path))
                # Touch to update mtime (helps with priority ordering)
                target_path.touch()
                moved += 1
                log(f"AUTO-BALANCE: {task_path.name} {source} -> {target}")
            except Exception as e:
                log(f"Failed to move {task_path.name}: {e}", "ERROR")

    if moved > 0:
        log(f"Auto-balanced {moved} task(s)")
        state["queue_balance_moves"] = state.get("queue_balance_moves", 0) + moved
        issues.append(f"auto_balanced: {moved} tasks moved")
        record_queue_rebalance(moved, overloaded, underloaded)
    else:
        issues.append(f"queue_imbalance: detected but no tasks moved (check task file states)")

    return issues


# ============================================================
# Check 11: Cascade failure detection
# ============================================================
def check_cascade_risk(state):
    """Detect potential cascade failures across multiple agents.

    Analyzes recent failures for patterns like:
    - Multiple agents failing simultaneously
    - Single agent timeout spike
    - Failure rate accelerating over time
    - Gateway-wide failure spike
    """
    issues = []
    now = time.time()
    last_check = state.get("last_cascade_check", 0)

    # Only check every CASCADE_CHECK_INTERVAL
    if (now - last_check) < CASCADE_CHECK_INTERVAL:
        return issues

    log("Checking cascade failure risk")

    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "cascade_detector", str(SCRIPTS_DIR / "cascade_detector.py")
        )
        cd = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cd)

        detector = cd.CascadeDetector(lookback_minutes=CASCADE_LOOKBACK_MINUTES)
        risk_report = detector.detect_cascade_risk()

        state["last_cascade_check"] = now
        state["cascade_risk"] = risk_report["risk_level"]
        state["cascade_metrics"] = risk_report["metrics"]

        if risk_report["risk_level"] in ["medium", "high"]:
            log(f"CASCADE RISK: {risk_report['risk_level'].upper()} — "
                f"{len(risk_report['patterns'])} pattern(s) detected", "WARN")
            issues.append(f"cascade_risk_{risk_report['risk_level']}")

            for pattern in risk_report["patterns"][:3]:
                log(f"  PATTERN: {pattern['description']}", "WARN")

            # Log recommendations
            for rec in risk_report["recommendations"][:2]:
                log(f"  RECOMMEND: {rec['description']}", "WARN")

            # Take preventive action for high risk
            if risk_report["risk_level"] == "high":
                for rec in risk_report["recommendations"]:
                    if rec.get("action") in ["reduce_load", "pause_new_tasks"]:
                        log(f"PREVENTIVE ACTION RECOMMENDED: {rec['description']}", "WARN")
                        # Would require additional infrastructure to actually pause tasks
                        # For now, just log the recommendation

        else:
            log(f"Cascade risk: {risk_report['risk_level']} ({risk_report['metrics']['events_analyzed']} events analyzed)")

    except Exception as e:
        log(f"Cascade check failed: {e}", "ERROR")
        issues.append(f"cascade_check_error: {e}")

    return issues


# ============================================================
# Check 12: Quality gate for recent completions
# ============================================================
def check_quality_gate(state):
    """Verify completion quality for recent .done.md files.

    Checks for:
    - Low content (< 500 chars)
    - Weak structure (< 3 headings)
    - Missing resolution section
    """
    issues = []
    now = time.time()
    last_check = state.get("last_quality_gate_check", 0)

    # Only check every QUALITY_GATE_INTERVAL
    if (now - last_check) < QUALITY_GATE_INTERVAL:
        return issues

    log("Running completion quality gate")

    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "quality_gate", str(SCRIPTS_DIR / "quality_gate.py")
        )
        qg = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(qg)

        gate = qg.CompletionQualityGate()
        checked_count = 0
        failed_count = 0
        retried_count = 0
        escalated_count = 0

        # Check recent .done.md files
        cutoff_time = now - (QUALITY_LOOKBACK_MINUTES * 60)

        for agent in AGENTS:
            tasks_dir = AGENTS_DIR / agent / "tasks"
            if not tasks_dir.exists():
                continue

            for f in tasks_dir.glob("*.done.md"):
                if not f.is_file():
                    continue

                try:
                    mtime = f.stat().st_mtime
                except OSError:
                    continue

                if mtime < cutoff_time:
                    continue

                # Skip test tasks
                try:
                    content = f.read_text()
                    if "test" in content.lower() and len(content) < 500:
                        continue
                except OSError:
                    continue

                checked_count += 1
                result = gate.verify_completion(f)

                if not result.passed:
                    failed_count += 1
                    log(f"QUALITY FAIL: {agent}/{f.name} — {result.issues}", "WARN")

                    if result.action == "retry":
                        retried_count += 1
                        issues.append(f"{agent}/{f.name} quality: retry")
                        record_quality_retry(agent, f.name)
                    elif result.action == "escalate":
                        escalated_count += 1
                        issues.append(f"{agent}/{f.name} quality: escalate")
                        record_quality_escalation(agent, f.name)
                        # Create escalation task
                        gate.escalate_to_kublai(f, result.issues)

        state["last_quality_gate_check"] = now
        state["quality_gate_checked"] = checked_count
        state["quality_gate_failed"] = failed_count
        state["quality_gate_retried"] = retried_count
        state["quality_gate_escalated"] = escalated_count

        if checked_count > 0:
            log(f"Quality gate: {checked_count} checked, {failed_count} failed, "
                f"{retried_count} retried, {escalated_count} escalated")

    except Exception as e:
        log(f"Quality gate check failed: {e}", "ERROR")
        issues.append(f"quality_gate_error: {e}")

    return issues


# ============================================================
# Check 13: Self-healing score tracking
# ============================================================
def update_self_healing_score(state):
    """Calculate and report self-healing effectiveness score.

    Tracks percentage of issues auto-resolved vs. escalated.
    Saves snapshot for historical tracking.
    """
    issues = []
    now = time.time()
    last_check = state.get("last_self_healing_score_check", 0)

    # Only update every SELF_HEALING_SCORE_INTERVAL
    if (now - last_check) < SELF_HEALING_SCORE_INTERVAL:
        return issues

    log("Updating self-healing score")

    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "self_healing_score", str(SCRIPTS_DIR / "self_healing_score.py")
        )
        shs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(shs)

        tracker = shs.SelfHealingScore()
        score_data = tracker.calculate_score(hours=SELF_HEALING_SCORE_HOURS)

        # Save snapshot
        tracker.save_score_snapshot(hours=SELF_HEALING_SCORE_HOURS)

        state["last_self_healing_score_check"] = now
        state["self_healing_score"] = score_data["score"]
        state["self_healing_metrics"] = {
            "auto_resolved": score_data["auto_resolved"],
            "escalated": score_data["escalated"],
            "manual": score_data["manual"],
            "total": score_data["total_issues"],
        }

        log(f"Self-healing score: {score_data['score']:.1f}% "
            f"({score_data['auto_resolved']}/{score_data['total_issues']} auto-resolved)")

        # Alert if score drops below threshold
        if score_data["score"] < 50 and score_data["total_issues"] > 5:
            log(f"LOW SELF-HEALING SCORE: {score_data['score']:.1f}% — system resilience degraded", "WARN")
            issues.append(f"low_self_healing_score: {score_data['score']:.1f}%")

    except Exception as e:
        log(f"Self-healing score update failed: {e}", "ERROR")
        issues.append(f"self_healing_score_error: {e}")

    return issues


# ============================================================
# Check 14: Circuit breaker health check
# ============================================================
def check_circuit_breaker_health(state):
    """Report circuit breaker state and validate recent data.

    Monitors:
    - OPEN circuits (quarantined agents)
    - HALF-OPEN circuits (agents on probation)
    - Recent redistributions
    - State file health
    """
    issues = []

    if _circuit_breaker is None:
        return issues

    try:
        report = _circuit_breaker.get_status_report()

        # Log any OPEN circuits
        for agent, status in report["agents"].items():
            if status["state"] == "OPEN":
                log(f"CIRCUIT OPEN: {agent} — {status['detail']}", "WARN")
                state["circuit_open_agents"] = state.get("circuit_open_agents", [])
                if agent not in state["circuit_open_agents"]:
                    state["circuit_open_agents"].append(agent)
                    issues.append(f"circuit_open: {agent}")

            elif status["state"] == "HALF_OPEN":
                log(f"CIRCUIT HALF-OPEN: {agent} — {status['detail']}", "INFO")
                state["circuit_half_open_agents"] = state.get("circuit_half_open_agents", [])
                if agent not in state["circuit_half_open_agents"]:
                    state["circuit_half_open_agents"].append(agent)

        # Store report in state
        state["circuit_report"] = report
        state["circuit_summary"] = report["summary"]

        # Check for excessive redistributions (potential thrashing)
        if "redistributions" in _circuit_breaker.state:
            recent_redistributions = [
                r for r in _circuit_breaker.state.get("redistributions", [])
                if datetime.fromisoformat(r["ts"]) > datetime.now() - timedelta(hours=1)
            ]
            state["recent_redistributions"] = len(recent_redistributions)

            if len(recent_redistributions) > 20:
                log(f"High redistribution count: {len(recent_redistributions)} in last hour (potential thrashing)", "WARN")
                issues.append(f"high_redistribution_count: {len(recent_redistributions)}/hour")

    except Exception as e:
        log(f"Circuit breaker check failed: {e}", "ERROR")
        issues.append(f"circuit_breaker_error: {e}")

    return issues


# ============================================================
# Check 15: Internal watchdog health check
# ============================================================
def check_watchdog_health(state):
    """Internal health check for the watchdog itself.

    Monitors:
    - Cycle execution time
    - Issue count trends
    - State file health
    """
    issues = []
    now = time.time()

    # Track cycle start time if not set
    if "cycle_start_time" not in state:
        state["cycle_start_time"] = now

    cycle_duration = now - state["cycle_start_time"]
    state["last_cycle_duration"] = cycle_duration

    # Warn if cycle is taking too long
    if cycle_duration > 30:  # 30 seconds
        log(f"Watchdog cycle slow: {cycle_duration:.1f}s", "WARN")
        state["slow_cycles"] = state.get("slow_cycles", 0) + 1

    # Check state file size
    try:
        state_size = STATE_FILE.stat().st_size if STATE_FILE.exists() else 0
        state["state_file_size"] = state_size

        if state_size > 100_000:  # 100KB
            log(f"State file large: {state_size / 1024:.1f}KB", "WARN")
    except Exception:
        pass

    return issues


# ============================================================
# Main cycle
# ============================================================
def run_cycle():
    """Run all checks. Returns list of issues found."""
    state = load_state()
    state["cycle_start_time"] = time.time()
    all_issues = []

    # Core health checks
    all_issues.extend(check_watcher_alive(state))
    all_issues.extend(check_stalled_tasks(state))
    all_issues.extend(verify_recent_completions(state))
    all_issues.extend(periodic_queue_audit(state))
    all_issues.extend(cleanup_malformed(state))
    all_issues.extend(check_reflection_pipeline(state))
    all_issues.extend(check_memory_health(state))
    all_issues.extend(check_routing_drift(state))
    all_issues.extend(check_agent_failure_rates(state))
    all_issues.extend(check_queue_balance(state))

    # P2 enhancement checks
    all_issues.extend(check_cascade_risk(state))
    all_issues.extend(check_quality_gate(state))
    all_issues.extend(update_self_healing_score(state))
    all_issues.extend(check_circuit_breaker_health(state))
    all_issues.extend(check_watchdog_health(state))

    state["cycles"] = state.get("cycles", 0) + 1
    state["last_cycle"] = datetime.now().isoformat()
    state["last_cycle_epoch"] = time.time()
    state["last_issues"] = all_issues

    save_state(state)

    if all_issues:
        log(f"Cycle #{state['cycles']}: {len(all_issues)} issue(s)")
    return all_issues


def daemon_loop():
    """Main daemon loop — runs cycle every POLL_INTERVAL seconds."""
    log(f"Ogedei Watchdog starting (poll interval: {POLL_INTERVAL}s)")
    log(f"State: {STATE_FILE}")
    log(f"Log: {LOG_FILE}")

    while not stop_event.is_set():
        try:
            run_cycle()
        except Exception as e:
            log(f"Error in watchdog cycle: {e}", "ERROR")

        for _ in range(POLL_INTERVAL):
            if stop_event.is_set():
                break
            time.sleep(1)

    log("Ogedei Watchdog stopped")


def signal_handler(sig, frame):
    log(f"Received signal {sig}, shutting down...")
    stop_event.set()


# ============================================================
# Healing event recording helpers
# ============================================================
def record_healing(
    issue_type: str,
    action: str,
    outcome: str = "success",
    agent: str = "",
    details: dict | None = None,
):
    """Record a healing event to the self-healing score tracker.

    Args:
        issue_type: Type of issue (e.g., "gateway_crash", "stale_task")
        action: Action taken ("auto_recovered", "escalated", "manual", "partial")
        outcome: Outcome ("success", "failed", "partial")
        agent: Agent affected (if applicable)
        details: Additional details about the event
    """
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "self_healing_score", str(SCRIPTS_DIR / "self_healing_score.py")
        )
        shs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(shs)

        tracker = shs.SelfHealingScore()
        tracker.record_issue(issue_type, action, outcome, agent, details)
    except Exception as e:
        log(f"Failed to record healing event: {e}", "ERROR")


def record_gateway_restart(success: bool, pid: int = 0):
    """Record a gateway restart event."""
    record_healing(
        issue_type="gateway_restart",
        action="auto_recovered" if success else "escalated",
        outcome="success" if success else "failed",
        details={"pid": pid} if pid else {},
    )


def record_fake_completion_requeued(agent: str, task_file: str):
    """Record a fake completion detection and requeue."""
    record_healing(
        issue_type="fake_completion",
        action="auto_recovered",
        outcome="success",
        agent=agent,
        details={"task_file": task_file},
    )


def record_stale_task_recovered(agent: str, task_file: str):
    """Record a stale task recovery."""
    record_healing(
        issue_type="stale_task_recovered",
        action="auto_recovered",
        outcome="success",
        agent=agent,
        details={"task_file": task_file},
    )


def record_memory_fix(fix_type: str, count: int):
    """Record a memory health fix."""
    record_healing(
        issue_type=f"memory_{fix_type}",
        action="auto_recovered",
        outcome="success",
        details={"fix_count": count},
    )


def record_queue_rebalance(moved_count: int, from_agents: list, to_agents: list):
    """Record a queue balancing action."""
    record_healing(
        issue_type="queue_rebalanced",
        action="auto_recovered",
        outcome="success",
        details={
            "moved_count": moved_count,
            "from_agents": from_agents,
            "to_agents": to_agents,
        },
    )


def record_quality_retry(agent: str, task_file: str):
    """Record a quality gate retry."""
    record_healing(
        issue_type="quality_retry",
        action="auto_recovered",
        outcome="success",
        agent=agent,
        details={"task_file": task_file},
    )


def record_quality_escalation(agent: str, task_file: str):
    """Record a quality gate escalation."""
    record_healing(
        issue_type="quality_failure",
        action="escalated",
        outcome="partial",
        agent=agent,
        details={"task_file": task_file},
    )


def main():
    parser = argparse.ArgumentParser(description="Ogedei Watchdog — quality assurance daemon")
    parser.add_argument("--once", action="store_true", help="Run single cycle and exit")
    parser.add_argument("--daemon", action="store_true", help="Run as persistent daemon")
    parser.add_argument("--status", action="store_true", help="Print current state and exit")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    if args.status:
        state = load_state()
        print(json.dumps(state, indent=2))
        return

    if args.once:
        issues = run_cycle()
        if issues:
            print(f"Issues found: {len(issues)}")
            for i in issues:
                print(f"  - {i}")
        else:
            print("No issues found")
        return

    daemon_loop()


if __name__ == "__main__":
    main()
