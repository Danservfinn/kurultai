#!/usr/bin/env python3
"""
Ogedei Watchdog — Persistent quality-assurance daemon for the Kurultai.

Runs every 30 seconds between tock cycles. Nine checks per cycle:
  1. check_watcher_alive()     — pgrep task-watcher.py + log mtime
  2. check_stalled_tasks()     — .executing.md files > 15 min old
  3. verify_recent_completions() — new .done.md → check for real Claude Code execution
  4. periodic_queue_audit()    — full queue_audit.audit() every 30 min
  5. cleanup_malformed()       — remove .executing.completed.done artifacts > 24h
  6. check_reflection_pipeline() — reflection-status.json age + step timing
  7. check_memory_health()     — memory_audit.py every 30 min (contamination, bloat, rules)
  8. check_routing_drift()     — keyword vs actual routing drift every 30 min
  9. check_agent_failure_rates() — 1h failure rate per agent, writes health flags every 5 min

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
from datetime import datetime
from pathlib import Path
from threading import Event

sys.path.insert(0, str(Path(__file__).parent))
from json_state import locked_json_read, locked_json_update
from kurultai_paths import AGENTS_DIR, LOGS_DIR

# Force unbuffered output for launchd
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
            subprocess.run(
                ["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{WATCHER_PLIST}"],
                capture_output=True, text=True, timeout=15
            )
            state["watcher_restarts"] = state.get("watcher_restarts", 0) + 1
            log("Restart issued via launchctl kickstart")
        except Exception as e:
            log(f"Failed to restart watcher: {e}", "ERROR")
        return issues

    # Check log freshness
    if WATCHER_LOG.exists():
        age = time.time() - WATCHER_LOG.stat().st_mtime
        if age > WATCHER_LOG_MAX_AGE:
            log(f"WATCHER LOG STALE — {age:.0f}s old (threshold: {WATCHER_LOG_MAX_AGE}s)", "WARN")
            issues.append(f"task-watcher log stale ({age:.0f}s)")

    return issues


# ============================================================
# Check 2: Stalled .executing tasks
# ============================================================
def check_stalled_tasks(state):
    """Find .executing.md files older than 15 minutes."""
    issues = []
    now = time.time()

    for agent in AGENTS:
        tasks_dir = AGENTS_DIR / agent / "tasks"
        if not tasks_dir.exists():
            continue
        for f in tasks_dir.iterdir():
            name = f.name
            # Only match .executing.md task files (not .pid or other artifacts)
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
            if age > STALE_EXECUTING_SECS:
                key = f"{agent}/{name}"
                last_warned = _stall_warned_at.get(key, 0)
                if (now - last_warned) >= STALL_WARN_COOLDOWN:
                    log(f"STALLED: {key} — {age:.0f}s old", "WARN")
                    _stall_warned_at[key] = now
                    state["stalled_warnings"] = state.get("stalled_warnings", 0) + 1
                issues.append(f"{key} stalled {age:.0f}s")

    # Prune cooldown entries for files that no longer exist
    for key in list(_stall_warned_at):
        agent, fname = key.split("/", 1)
        if not (AGENTS_DIR / agent / "tasks" / fname).exists():
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

        # Prune deprecated rules (safe at any severity level, runs on "info" results)
        pruneable = [r for r in results if r["type"] == "pruneable_deprecated"]
        if pruneable:
            fixed = ma.fix_pruneable_deprecated(pruneable)
            if fixed:
                log(f"AUTO-FIX: Pruned {fixed} deprecated rule(s) from rules.json")
                state["memory_fixes"] = state.get("memory_fixes", 0) + fixed

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
# Main cycle
# ============================================================
def run_cycle():
    """Run all eight checks. Returns list of issues found."""
    state = load_state()
    all_issues = []

    all_issues.extend(check_watcher_alive(state))
    all_issues.extend(check_stalled_tasks(state))
    all_issues.extend(verify_recent_completions(state))
    all_issues.extend(periodic_queue_audit(state))
    all_issues.extend(cleanup_malformed(state))
    all_issues.extend(check_reflection_pipeline(state))
    all_issues.extend(check_memory_health(state))
    all_issues.extend(check_routing_drift(state))
    all_issues.extend(check_agent_failure_rates(state))

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
