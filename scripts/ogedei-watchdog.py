#!/usr/bin/env python3
"""
Ogedei Watchdog — Persistent quality-assurance daemon for the Kurultai.

Runs every 30 seconds between tock cycles. Five checks per cycle:
  1. check_watcher_alive()     — pgrep task-watcher.py + log mtime
  2. check_stalled_tasks()     — .executing.md files > 15 min old
  3. verify_recent_completions() — new .done.md → check for real Claude Code execution
  4. periodic_queue_audit()    — full queue_audit.audit() every 30 min
  5. cleanup_malformed()       — remove .executing.completed.done artifacts > 24h

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

# Force unbuffered output for launchd
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# Configuration
AGENTS_DIR = Path("/Users/kublai/.openclaw/agents")
SCRIPTS_DIR = Path(__file__).parent
STATE_FILE = AGENTS_DIR / "main/logs/ogedei-watchdog-state.json"
LOG_FILE = AGENTS_DIR / "main/logs/ogedei-watchdog.log"
WATCHER_PLIST = "com.kurultai.task-watcher"
WATCHER_LOG = AGENTS_DIR / "main/logs/task-watcher.log"

POLL_INTERVAL = 30        # seconds
STALE_EXECUTING_SECS = 900  # 15 minutes
WATCHER_LOG_MAX_AGE = 300   # 5 minutes
MALFORMED_MAX_AGE = 86400   # 24 hours
QUEUE_AUDIT_INTERVAL = 1800 # 30 minutes

AGENTS = ["kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei"]

stop_event = Event()


def log(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {level}: {msg}"
    print(line)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


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
            if ".executing" in name and ".completed" not in name and ".done" not in name and ".failed" not in name and f.is_file():
                try:
                    age = now - f.stat().st_mtime
                except OSError:
                    continue
                if age > STALE_EXECUTING_SECS:
                    log(f"STALLED: {agent}/{f.name} — {age:.0f}s old", "WARN")
                    issues.append(f"{agent}/{f.name} stalled {age:.0f}s")
                    state["stalled_warnings"] = state.get("stalled_warnings", 0) + 1

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
            if qa.is_fake(result_path):
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
        # Also check the legacy path
        for check_dir in [tasks_dir, AGENTS_DIR / "main/agent" / agent / "tasks"]:
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
# Main cycle
# ============================================================
def run_cycle():
    """Run all five checks. Returns list of issues found."""
    state = load_state()
    all_issues = []

    all_issues.extend(check_watcher_alive(state))
    all_issues.extend(check_stalled_tasks(state))
    all_issues.extend(verify_recent_completions(state))
    all_issues.extend(periodic_queue_audit(state))
    all_issues.extend(cleanup_malformed(state))

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
