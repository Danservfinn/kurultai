#!/usr/bin/env python3
"""
task-reaper.py — Independent orphan recovery daemon.

Runs every 5 minutes via launchctl. Defense-in-depth against silent task deaths:
  Check A: Recover WORKING tasks with expired leases
  Check B: Detect dead executor and restart it
  Check C: Promote ORPHANED tasks back to PENDING

Sends Signal DM when orphans found or executor is down.
"""

import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from neo4j_v2_core import TaskStore
from kurultai_paths import TASK_LEDGER, LOGS_DIR

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ORPHAN_GRACE_MINUTES = 10      # Default: how long past lease expiry before recovery
# Priority-aware grace — critical tasks get recovered faster
GRACE_BY_PRIORITY = {
    "critical": 2, "high": 3, "normal": 10, "low": 10,
}
PROMOTE_HOLD_MINUTES = 5       # How long ORPHANED tasks wait before PENDING
HEARTBEAT_FILE = LOGS_DIR / "v2-executor-heartbeat.json"
HEARTBEAT_STALE_SECONDS = 600  # 10 min — executor heartbeat considered stale
STATE_FILE = LOGS_DIR / "task-reaper-state.json"
ALERT_COOLDOWN_SECONDS = 900   # 15 min between same-class alerts

SIGNAL_TARGET = "+19194133445"
SEND_SIGNAL_SCRIPT = Path.home() / ".claude" / "skills" / "agent-collaboration" / "scripts" / "send_signal.sh"

EXECUTOR_PLIST_LABEL = "com.kurultai.v2-executor"

logger = logging.getLogger("task-reaper")

# ---------------------------------------------------------------------------
# Ledger emission (direct JSONL write — works even when Neo4j is down)
# ---------------------------------------------------------------------------

def _emit_ledger(event, task_id, agent, **extra):
    entry = {
        "event": event, "task_id": task_id, "agent": agent,
        "timestamp": datetime.now().isoformat(), "executor": "task-reaper",
        **extra,
    }
    try:
        with open(TASK_LEDGER, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logger.warning(f"Ledger write failed: {e}")


# ---------------------------------------------------------------------------
# Alert state (cooldown tracking)
# ---------------------------------------------------------------------------

def _load_state() -> dict:
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text())
    except Exception:
        pass
    return {}


def _save_state(state: dict):
    try:
        STATE_FILE.write_text(json.dumps(state))
    except Exception as e:
        logger.warning(f"State save failed: {e}")


def _should_alert(state: dict, alert_class: str) -> bool:
    last = state.get(f"last_alert_{alert_class}", 0)
    return (time.time() - last) >= ALERT_COOLDOWN_SECONDS


def _record_alert(state: dict, alert_class: str):
    state[f"last_alert_{alert_class}"] = time.time()


# ---------------------------------------------------------------------------
# Signal notification
# ---------------------------------------------------------------------------

def _send_signal(message: str):
    if not SEND_SIGNAL_SCRIPT.exists():
        logger.warning(f"Signal script not found: {SEND_SIGNAL_SCRIPT}")
        return
    try:
        subprocess.run(
            ["bash", str(SEND_SIGNAL_SCRIPT), message, "--dm", SIGNAL_TARGET],
            capture_output=True, timeout=15, text=True,
        )
    except Exception as e:
        logger.warning(f"Signal send failed: {e}")


# ---------------------------------------------------------------------------
# Check A: Orphan recovery
# ---------------------------------------------------------------------------

def check_orphans(store: TaskStore, state: dict) -> int:
    """Recover WORKING tasks with expired leases. Returns count recovered."""
    try:
        recovered = store.recover_orphans(grace_minutes=ORPHAN_GRACE_MINUTES)
    except Exception as e:
        logger.error(f"Orphan recovery query failed: {e}")
        return 0

    if not recovered:
        return 0

    for task in recovered:
        tid = task.get("task_id", "unknown")
        agent = task.get("assigned_to", "unknown")
        logger.warning(f"Reaped orphan: {tid} (agent={agent})")
        _emit_ledger("ORPHAN_REAPED", tid, agent,
                     retry_count=task.get("retry_count", 0),
                     new_status=task.get("status", "ORPHANED"))

    if _should_alert(state, "orphan"):
        task_list = ", ".join(t.get("task_id", "?")[:20] for t in recovered[:5])
        _send_signal(
            f"[REAPER] Recovered {len(recovered)} orphaned task(s): {task_list}\n"
            f"Executor may have crashed. Tasks will be retried."
        )
        _record_alert(state, "orphan")

    return len(recovered)


# ---------------------------------------------------------------------------
# Check B: Executor heartbeat
# ---------------------------------------------------------------------------

def check_executor(state: dict) -> bool:
    """Check if executor is alive. Returns True if healthy."""
    # Read heartbeat file
    heartbeat_stale = True
    if HEARTBEAT_FILE.exists():
        try:
            hb = json.loads(HEARTBEAT_FILE.read_text())
            ts_str = hb.get("timestamp", "")
            if ts_str:
                hb_time = datetime.fromisoformat(ts_str)
                age = (datetime.now() - hb_time).total_seconds()
                heartbeat_stale = age > HEARTBEAT_STALE_SECONDS
        except Exception as e:
            logger.warning(f"Heartbeat read error: {e}")

    if not heartbeat_stale:
        return True

    # Heartbeat is stale — check if process is actually running
    try:
        result = subprocess.run(
            ["pgrep", "-f", "neo4j_v2_executor"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            # Process exists but heartbeat stale — might be hung but not dead
            logger.info("Executor process found but heartbeat stale — not restarting yet")
            return True
    except Exception:
        pass

    # Executor is dead — attempt restart
    logger.error("Executor is DOWN — no process found, heartbeat stale")
    _emit_ledger("EXECUTOR_DOWN", "system", "task-reaper",
                 heartbeat_age_s=HEARTBEAT_STALE_SECONDS)

    try:
        uid = os.getuid()
        subprocess.run(
            ["launchctl", "kickstart", "-k", f"gui/{uid}/{EXECUTOR_PLIST_LABEL}"],
            capture_output=True, text=True, timeout=10,
        )
        logger.info("Executor restart triggered via launchctl")
    except Exception as e:
        logger.error(f"Executor restart failed: {e}")

    if _should_alert(state, "executor_down"):
        _send_signal(
            f"[REAPER] v2-executor is DOWN. Heartbeat stale >{HEARTBEAT_STALE_SECONDS}s, "
            f"no process found. Attempted launchctl restart."
        )
        _record_alert(state, "executor_down")

    return False


# ---------------------------------------------------------------------------
# Check C: Promote orphans
# ---------------------------------------------------------------------------

def check_promote(store: TaskStore) -> int:
    """Promote ORPHANED tasks back to PENDING after hold period."""
    try:
        promoted = store.promote_orphans(hold_minutes=PROMOTE_HOLD_MINUTES)
    except Exception as e:
        logger.error(f"Orphan promotion failed: {e}")
        return 0

    if promoted:
        ids = [t.get("task_id", "?") for t in promoted]
        logger.info(f"Promoted {len(promoted)} orphans to PENDING: {ids}")

    return len(promoted)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    state = _load_state()
    store = TaskStore()

    try:
        # Check A
        orphans_recovered = check_orphans(store, state)

        # Check B
        executor_ok = check_executor(state)

        # Check C
        promoted = check_promote(store)

        # Summary
        if orphans_recovered or not executor_ok or promoted:
            logger.info(
                f"Reaper summary: orphans_recovered={orphans_recovered}, "
                f"executor_ok={executor_ok}, promoted={promoted}"
            )
    except Exception as e:
        logger.exception(f"Reaper fatal error: {e}")
    finally:
        store.close()
        _save_state(state)


if __name__ == "__main__":
    main()
