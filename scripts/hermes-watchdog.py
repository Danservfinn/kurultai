#!/usr/bin/env python3
"""
hermes-watchdog.py -- Hermes System Caretaker Watchdog.

Persistent daemon (60s poll cycle) that monitors internal Kurultai health.
Deterministic rules engine -- no LLM calls in the daemon layer.

When a check fires:
  - T0 auto-fixes are applied immediately (if not --dry-run)
  - Non-deterministic problems get a task file written to
    ~/.openclaw/agents/hermes/tasks/ for LLM investigation

Usage:
    python3 hermes-watchdog.py --once          # single cycle
    python3 hermes-watchdog.py --once --dry-run # detect but don't fix
    python3 hermes-watchdog.py --daemon         # persistent (60s interval)
    python3 hermes-watchdog.py --daemon --dry-run # observe only

Kill switch: ~/.openclaw/flags/hermes-disabled.flag
"""

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event

sys.path.insert(0, str(Path(__file__).parent))
from kurultai_paths import AGENTS_DIR, LOGS_DIR
from kurultai_logging import get_logger, write_heartbeat, check_heartbeat
from json_state import locked_json_read, locked_json_update
from cascade_writer import append_entry as cascade_append
from alert_deduplication import should_suppress_alert, record_alert_created

logger = get_logger('hermes-watchdog', agent='hermes')

# ---------------------------------------------------------------------------
# Import integrity verification
# ---------------------------------------------------------------------------

IMPORT_MANIFEST = Path.home() / ".openclaw" / "agents" / "hermes" / "import-manifest.json"
SCRIPTS_DIR = Path(__file__).parent


def verify_import_integrity() -> bool:
    """Verify SHA256 of critical helpers against pinned manifest. Self-kill-switch on mismatch."""
    if not IMPORT_MANIFEST.exists():
        logger.critical("import-manifest.json not found — integrity check FAIL-CLOSED")
        return False
    try:
        manifest = json.loads(IMPORT_MANIFEST.read_text())
    except Exception as e:
        logger.error(f"import-manifest.json corrupt: {e}")
        return False
    ok = True
    for filename, expected in manifest.items():
        # H3: support absolute paths (starting with ~ or /) for files outside
        # SCRIPTS_DIR such as git pre-commit hooks. Bare filenames are
        # SCRIPTS_DIR-relative as before.
        if filename.startswith("~"):
            filepath = Path(filename).expanduser()
        elif filename.startswith("/"):
            filepath = Path(filename)
        else:
            filepath = SCRIPTS_DIR / filename
        if not filepath.exists():
            logger.error(f"IMPORT_INTEGRITY: {filename} missing")
            ok = False
            continue
        actual = hashlib.sha256(filepath.read_bytes()).hexdigest()
        if f"sha256:{actual}" != expected:
            logger.error(f"IMPORT_INTEGRITY_VIOLATION: {filename} expected={expected} actual=sha256:{actual}")
            ok = False
    if not ok:
        try:
            DISABLED_FLAG.touch()
            logger.critical("Self-kill-switch activated due to import integrity violations")
        except OSError as exc:
            logger.critical(f"Cannot activate self-kill-switch: {exc} — integrity compromised, refusing to proceed")
            return False
    return ok


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
STATE_FILE = LOGS_DIR / "hermes-watchdog-state.json"
DRY_RUN_MODE = False
POLL_INTERVAL = 60          # seconds between cycles
STALE_EXECUTING_SECS = 900  # 15 minutes
FLAG_WARN_SECS = 300        # 5 minutes: flag candidate
FLAG_TERMINATE_SECS = 900   # 15 minutes: terminate / requeue
QUALITY_LOOKBACK_SECS = 1800  # 30 minutes for .done.md scan
QUEUE_IMBALANCE_FACTOR = 3  # agent has >3x average = imbalanced
CASCADE_LOOKBACK_SECS = 600  # 10 minutes
CASCADE_THRESHOLD = 3       # 3+ same pattern in window
HEARTBEAT_STALE_SECS = 300  # 5 minutes
REFLECTION_MAX_AGE_SECS = 172800  # 48 hours
PROPOSAL_MAX_AGE_DAYS = 7
KNOWLEDGE_STALE_DAYS = 30
FAILURE_RATE_WINDOW_H = 1
FAILURE_RATE_THRESHOLD = 0.5
FAILURE_RATE_MIN_TASKS = 3

# Directories
HERMES_TASKS_DIR = AGENTS_DIR / "hermes" / "tasks"
HEARTBEATS_DIR = LOGS_DIR / "heartbeats"
KNOWLEDGE_DIRS = [
    AGENTS_DIR / "main" / "knowledge",
    AGENTS_DIR / "chagatai" / "knowledge",
    AGENTS_DIR / "mongke" / "knowledge",
]
CASCADE_LOG = LOGS_DIR / "cascade-detections.jsonl"
AGENT_HEALTH_FLAGS = LOGS_DIR / "agent-health-flags.json"
REFLECTION_STATUS_FILE = LOGS_DIR / "reflection-status.json"
DISABLED_FLAG = Path.home() / ".openclaw" / "flags" / "hermes-disabled.flag"

AGENTS = ["kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei", "tolui"]
DISPATCH_AGENTS = ["kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei"]

# Launchd one-shot daemons that should be excluded from heartbeat checks
LAUNCHD_ONESHOTS = frozenset({
    "calendar-reminders",
    "hourly-reflection",
    "brainstorm",
})

stop_event = Event()

# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------

def load_state() -> dict:
    """Load persistent watchdog state from JSON file."""
    return locked_json_read(str(STATE_FILE), default={
        "cycle_count": 0,
        "last_cycle": None,
        "last_check": {},
        "counters": {},
        "model_drift_ts": None,
        "model_drift_drifted": [],
    })


def save_state(state: dict) -> None:
    """Persist watchdog state to JSON file."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with locked_json_update(str(STATE_FILE)) as data:
        data.clear()
        data.update(state)


# ---------------------------------------------------------------------------
# Task writer helper -- writes a .md task for Hermes LLM investigation
# ---------------------------------------------------------------------------

def write_hermes_task(title: str, body: str, priority: str = "normal",
                      source: str = "hermes-watchdog") -> str | None:
    """Write a task file to hermes/tasks/ for LLM investigation.

    Returns the task filename on success, None on failure.
    """
    try:
        HERMES_TASKS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe_title = re.sub(r'[^a-zA-Z0-9_-]', '-', title)[:60]
        filename = f"{priority}-{ts}-{safe_title}.md"
        content = (
            f"---\n"
            f"agent: hermes\n"
            f"priority: {priority}\n"
            f"created: {datetime.now().isoformat()}\n"
            f"task_type: watchdog_escalation\n"
            f"source: {source}\n"
            f"---\n\n"
            f"# {title}\n\n{body}\n"
        )
        path = HERMES_TASKS_DIR / filename
        path.write_text(content)
        logger.info(f"Escalation task written: {filename}")
        return filename
    except Exception as e:
        logger.error(f"Failed to write hermes task: {e}")
        return None


# ---------------------------------------------------------------------------
# hermes_auto_fix integration (lazy import)
# ---------------------------------------------------------------------------

def _auto_fix():
    """Lazy-import hermes_auto_fix from scripts directory."""
    try:
        scripts_dir = str(Path(__file__).parent)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import hermes_auto_fix
        return hermes_auto_fix
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Check 1: Task executor alive
# ---------------------------------------------------------------------------

def check_task_executor_alive(state: dict) -> tuple[bool, dict]:
    """Check task_executor heartbeat and process liveness.

    T0 fix: restart via launchctl if heartbeat is stale and process is gone.
    Escalate if restart fails.
    """
    evidence = {}
    fired = False

    # Check heartbeat freshness (5-minute tolerance)
    hb_ok = check_heartbeat("task-executor", max_age_seconds=300)
    evidence["heartbeat_ok"] = hb_ok

    # Check process via pgrep
    try:
        result = subprocess.run(
            ["pgrep", "-f", "task_executor"],
            capture_output=True, text=True, timeout=5,
        )
        process_alive = result.returncode == 0
    except Exception:
        process_alive = False
    evidence["process_alive"] = process_alive

    if hb_ok and process_alive:
        return False, evidence

    fired = True
    evidence["issue"] = "task_executor_down"

    if process_alive and not hb_ok:
        evidence["detail"] = "Process alive but heartbeat stale"
        logger.warning("task_executor process alive but heartbeat stale")
        return fired, evidence

    # Process is down -- attempt T0 restart
    logger.warning("TASK EXECUTOR DOWN -- attempting T0 restart via launchctl")

    if DRY_RUN_MODE:
        evidence["restart_attempted"] = True
        evidence["restart_blocked_by_dry_run"] = True
        logger.info("T0 restart blocked by dry_run/kill-switch mode")
        return fired, evidence
    evidence["restart_attempted"] = True

    # O3: Log T0 auto-fix restart attempt to cascade-detections
    cascade_append(
        pattern_type="executor_restart",
        agent="hermes",
        detail=f"task_executor heartbeat stale, process down — T0 launchctl restart",
        risk_level="high",
        affected_agents=DISPATCH_AGENTS,
    )

    try:
        result = subprocess.run(
            ["launchctl", "kickstart", "-k",
             f"gui/{os.getuid()}/com.kurultai.task-executor"],
            capture_output=True, text=True, timeout=15,
        )
        restart_ok = result.returncode == 0
        evidence["restart_success"] = restart_ok

        if restart_ok:
            # Verify restart via lsof
            time.sleep(2)
            verify = subprocess.run(
                ["lsof", "-c", "task_executor"],
                capture_output=True, text=True, timeout=5,
            )
            evidence["restart_confirmed"] = verify.returncode == 0
            logger.info("task_executor restart issued and confirmed")
            cascade_append(
                pattern_type="executor_restart_confirmed",
                agent="hermes",
                detail=f"task_executor restart confirmed via lsof (rc={verify.returncode})",
                risk_level="low",
                affected_agents=DISPATCH_AGENTS,
            )
        else:
            logger.error(f"task_executor restart failed: {result.stderr}")
            # O4: Dedup repeated critical escalation tasks
            _title = "Task Executor Restart Failed"
            if not should_suppress_alert("hermes", _title, "hermes-watchdog"):
                write_hermes_task(
                    _title,
                    f"launchctl kickstart returned rc={result.returncode}\n"
                    f"stderr: {result.stderr[:500]}",
                    priority="critical",
                )
                record_alert_created("hermes", _title, "hermes-watchdog")
            cascade_append(
                pattern_type="executor_restart_failed",
                agent="hermes",
                detail=f"launchctl restart failed: rc={result.returncode}",
                risk_level="high",
                affected_agents=DISPATCH_AGENTS,
            )
    except Exception as e:
        evidence["restart_error"] = str(e)
        logger.error(f"task_executor restart exception: {e}")
        _title = "Task Executor Restart Exception"
        if not should_suppress_alert("hermes", _title, "hermes-watchdog"):
            write_hermes_task(
                _title,
                str(e),
                priority="critical",
            )
            record_alert_created("hermes", _title, "hermes-watchdog")
        cascade_append(
            pattern_type="executor_restart_exception",
            agent="hermes",
            detail=f"restart exception: {e}",
            risk_level="high",
            affected_agents=DISPATCH_AGENTS,
        )

    state["counters"]["executor_restarts"] = (
        state["counters"].get("executor_restarts", 0) + 1
    )
    return fired, evidence


# ---------------------------------------------------------------------------
# Check 2: Stalled tasks
# ---------------------------------------------------------------------------

def check_stalled_tasks(state: dict) -> tuple[bool, dict]:
    """Scan agent dirs for .executing.md files with dead PIDs.

    Candidates are flagged at 5min, terminated at 15min.
    T0 fix: emit HERMES_REQUEST_REAP event via hermes_auto_fix for task-reaper to consume.
    """
    evidence = {"candidates": [], "requeued": [], "reap_requested": []}
    fired = False
    now = time.time()

    for agent in AGENTS:
        tasks_dir = AGENTS_DIR / agent / "tasks"
        if not tasks_dir.exists():
            continue
        for f in tasks_dir.iterdir():
            if not f.name.endswith(".executing.md"):
                continue
            if not f.is_file():
                continue
            # Skip tasks with terminal state patterns already in filename
            if any(p in f.name for p in [
                ".done.md", ".failed.md", ".resolved.",
                ".gate-passed.", ".cancelled", ".false-positive",
            ]):
                continue

            try:
                age = now - f.stat().st_mtime
            except OSError:
                continue

            if age < FLAG_WARN_SECS:
                continue

            # Check PID liveness
            pid_file = f.with_suffix(".pid")
            pid_dead = True
            pid_value = None
            if pid_file.exists():
                try:
                    pid_value = int(pid_file.read_text().strip())
                    os.kill(pid_value, 0)
                    pid_dead = False
                except (ValueError, OSError):
                    pid_dead = True

            candidate = {
                "path": str(f),
                "agent": agent,
                "age_s": round(age),
                "pid_dead": pid_dead,
                "pid": pid_value,
            }
            evidence["candidates"].append(candidate)
            fired = True

            # T0 fix: emit HERMES_REQUEST_REAP event for task-reaper to consume
            if pid_dead and age >= FLAG_TERMINATE_SECS and not DRY_RUN_MODE:
                if autofix and hasattr(autofix, "requeue_stuck_task"):
                    try:
                        autofix.requeue_stuck_task(str(f))
                        evidence["reap_requested"].append(f.name)
                        logger.info(f"Requested reap for stuck task: {agent}/{f.name}")
                    except Exception as e:
                        logger.error(f"Auto-fix reap request failed for {f.name}: {e}")
                        write_hermes_task(
                            f"Stuck Task Reap Request Failed: {agent}/{f.name}",
                            f"Age: {age:.0f}s, PID dead. Error: {e}",
                            priority="high",
                        )
                else:
                    # No auto-fix module -- write task for LLM
                    write_hermes_task(
                        f"Stuck Task: {agent}/{f.name}",
                        f"Task has been executing for {age:.0f}s with a dead PID.\n"
                        f"PID file: {pid_file}\n"
                        f"Action: Clear lock and requeue.",
                        priority="high",
                    )

    state["counters"]["stalled_candidates"] = len(evidence["candidates"])
    state["counters"]["stalled_requeued"] = (
        state["counters"].get("stalled_requeued", 0) + len(evidence["requeued"])
    )
    return fired, evidence


# ---------------------------------------------------------------------------
# Check 3: Quality gate drift
# ---------------------------------------------------------------------------

def check_quality_gate_drift(state: dict) -> tuple[bool, dict]:
    """Find recent .done.md files missing the '## Resolution' section.

    Logs detection and writes a task for follow-up investigation.
    """
    evidence = {"missing_resolution": []}
    fired = False
    now = time.time()
    cutoff = now - QUALITY_LOOKBACK_SECS

    for agent in AGENTS:
        tasks_dir = AGENTS_DIR / agent / "tasks"
        if not tasks_dir.exists():
            continue
        for f in tasks_dir.iterdir():
            if ".done.md" not in f.name or not f.is_file():
                continue
            # Skip already-verified or terminal states
            if any(p in f.name for p in [
                ".verified.done.", ".failed.done.", ".no_output.done.",
                ".resolved.", ".gate-passed.", ".false-positive",
            ]):
                continue
            try:
                mtime = f.stat().st_mtime
                if mtime < cutoff:
                    continue
            except OSError:
                continue

            try:
                content = f.read_text()
            except OSError:
                continue

            if "## Resolution" not in content:
                evidence["missing_resolution"].append({
                    "agent": agent,
                    "file": f.name,
                })
                fired = True
                logger.warning(
                    f"Quality gate drift: {agent}/{f.name} missing ## Resolution"
                )

    if evidence["missing_resolution"]:
        names = [f"{e['agent']}/{e['file']}" for e in evidence["missing_resolution"]]
        _title = f"Quality Gate Drift: {len(names)} tasks missing Resolution"
        _key = "quality_gate_drift"
        if not should_suppress_alert("hermes", _title, "hermes-watchdog", dedup_key=_key)[0]:
            write_hermes_task(
                _title,
                "The following .done.md files lack a ## Resolution section:\n\n"
                + "\n".join(f"- {n}" for n in names[:10])
                + ("\n... and more" if len(names) > 10 else ""),
                priority="normal",
            )
            record_alert_created("hermes", _title, "hermes-watchdog", dedup_key=_key)
        state["counters"]["quality_drift"] = len(evidence["missing_resolution"])

    return fired, evidence


# ---------------------------------------------------------------------------
# Check 4: Model drift
# ---------------------------------------------------------------------------

def check_model_drift(state: dict) -> tuple[bool, dict]:
    """Read agent sessions for model mismatches vs kurultai.json config.

    T0 fix: attempt auto-correction via hermes_auto_fix if safe.
    """
    evidence = {"drifted": [], "checked": 0}
    fired = False

    # Read tock snapshot for model data
    tock_file = LOGS_DIR / "tock" / "latest.json"
    if not tock_file.exists():
        evidence["reason"] = "no_tock_snapshot"
        return False, evidence

    try:
        with open(str(tock_file)) as f:
            tock = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        evidence["reason"] = f"tock_read_error: {e}"
        return False, evidence

    tock_age = time.time() - tock_file.stat().st_mtime
    if tock_age > 3600:
        evidence["reason"] = f"tock_stale: {tock_age:.0f}s"
        return False, evidence

    agents_data = tock.get("agents", {})

    for agent, data in agents_data.items():
        session = data.get("session", {})
        config_model = data.get("config_model", {})
        session_model = session.get("model", "none")
        resolved_model = config_model.get("resolved", "unknown")
        session_match = config_model.get("session_match", True)

        if session_model == "none":
            continue

        evidence["checked"] += 1

        if not session_match:
            evidence["drifted"].append({
                "agent": agent,
                "session_model": session_model,
                "config_model": resolved_model,
            })
            fired = True
            logger.warning(
                f"Model drift: {agent} running {session_model!r} "
                f"(configured: {resolved_model!r})"
            )

            # T0 fix: attempt auto-correction if hermes_auto_fix available
            autofix = _auto_fix()
            if autofix and hasattr(autofix, "correct_model_drift") and not DRY_RUN_MODE:
                try:
                    autofix.correct_model_drift(agent, session_model, resolved_model)
                    evidence["drifted"][-1]["auto_fixed"] = True
                except Exception as e:
                    logger.error(f"Model drift auto-fix failed for {agent}: {e}")

    if evidence["drifted"]:
        state["model_drift_ts"] = datetime.now().isoformat()
        state["model_drift_drifted"] = evidence["drifted"]

    return fired, evidence


# ---------------------------------------------------------------------------
# Check 5: Queue balance
# ---------------------------------------------------------------------------

def check_queue_balance(state: dict) -> tuple[bool, dict]:
    """Count pending tasks per agent and flag imbalances.

    If any agent has >3x the average, write a redistribution task.
    """
    evidence = {"depths": {}, "average": 0, "imbalanced": []}
    fired = False

    depths = {}
    for agent in DISPATCH_AGENTS:
        tasks_dir = AGENTS_DIR / agent / "tasks"
        if not tasks_dir.exists():
            depths[agent] = 0
            continue
        pending = 0
        for f in tasks_dir.iterdir():
            if not f.name.endswith(".md"):
                continue
            if any(tag in f.name for tag in [
                ".executing.", ".done.md", ".failed.md",
                ".cancelled", ".archived", ".verified.",
            ]):
                continue
            pending += 1
        depths[agent] = pending

    evidence["depths"] = depths
    total = sum(depths.values())
    count = len(depths)
    average = total / count if count else 0
    evidence["average"] = round(average, 1)

    for agent, depth in depths.items():
        if average > 0 and depth > QUEUE_IMBALANCE_FACTOR * average:
            evidence["imbalanced"].append({
                "agent": agent,
                "depth": depth,
                "average": round(average, 1),
            })
            fired = True

    if evidence["imbalanced"]:
        imbalance_lines = [
            f"- {e['agent']}: {e['depth']} tasks (avg: {e['average']})"
            for e in evidence["imbalanced"]
        ]
        _title = f"Queue Imbalance: {len(evidence['imbalanced'])} agent(s) overloaded"
        if not should_suppress_alert("hermes", _title, "hermes-watchdog"):
            write_hermes_task(
                _title,
                "Queue depths:\n\n"
                + "\n".join(f"- {a}: {d}" for a, d in depths.items())
                + "\n\nOverloaded:\n\n"
                + "\n".join(imbalance_lines)
                + "\n\nAction: Redistribute tasks from overloaded to underloaded agents.",
                priority="normal",
            )
            record_alert_created("hermes", _title, "hermes-watchdog")
        state["counters"]["queue_imbalance"] = len(evidence["imbalanced"])

    return fired, evidence


# ---------------------------------------------------------------------------
# Check 6: Agent failure rates
# ---------------------------------------------------------------------------

def check_agent_failure_rates(state: dict) -> tuple[bool, dict]:
    """Check agent health flags for high 1h failure rates.

    Reads agent-health-flags.json written by ogedei-watchdog.
    Writes health flags to state for dashboard consumption.
    """
    evidence = {"flagged": []}
    fired = False

    if not AGENT_HEALTH_FLAGS.exists():
        return False, evidence

    try:
        with open(str(AGENT_HEALTH_FLAGS)) as f:
            health = json.load(f)
    except (json.JSONDecodeError, IOError):
        return False, evidence

    agents_health = health.get("agents", {})
    for agent, flag in agents_health.items():
        if not flag.get("flagged", False):
            continue
        fail_rate = flag.get("fail_rate_1h", 0)
        total = flag.get("total_1h", 0)
        if total < FAILURE_RATE_MIN_TASKS:
            continue

        evidence["flagged"].append({
            "agent": agent,
            "fail_rate": round(fail_rate, 3),
            "total": total,
            "failed": flag.get("failed_1h", 0),
        })
        fired = True
        logger.warning(
            f"High failure rate: {agent} {fail_rate:.0%} "
            f"({flag.get('failed_1h', 0)}/{total} in 1h)"
        )

    if evidence["flagged"]:
        state["counters"]["high_failure_agents"] = len(evidence["flagged"])

    return fired, evidence


# ---------------------------------------------------------------------------
# Check 7: Cascade patterns
# ---------------------------------------------------------------------------

def check_cascade_patterns(state: dict) -> tuple[bool, dict]:
    """Read cascade-detections.jsonl for recurring patterns in last 10min.

    If 3+ entries of the same pattern_type appear within 10 minutes,
    escalate to hermes task.
    """
    evidence = {"patterns": {}, "escalated": []}
    fired = False

    if not CASCADE_LOG.exists():
        return False, evidence

    now = time.time()
    cutoff = now - CASCADE_LOOKBACK_SECS

    # Read recent entries
    recent = []
    try:
        with open(str(CASCADE_LOG)) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts_str = entry.get("timestamp", "")
                try:
                    ts = datetime.fromisoformat(ts_str).timestamp()
                except (ValueError, TypeError):
                    continue
                if ts >= cutoff:
                    recent.append(entry)
    except IOError:
        return False, evidence

    # Count by pattern type
    pattern_counts: dict[str, int] = {}
    for entry in recent:
        ptype = entry.get("type", "UNKNOWN")
        pattern_counts[ptype] = pattern_counts.get(ptype, 0) + 1

    evidence["patterns"] = pattern_counts

    for ptype, count in pattern_counts.items():
        if count >= CASCADE_THRESHOLD:
            evidence["escalated"].append({"type": ptype, "count": count})
            fired = True
            logger.warning(
                f"Cascade pattern escalation: {ptype} seen {count}x in "
                f"{CASCADE_LOOKBACK_SECS // 60}min"
            )
            _title = f"Cascade Pattern: {ptype} ({count}x in 10min)"
            if not should_suppress_alert("hermes", _title, "hermes-watchdog"):
                write_hermes_task(
                    _title,
                    f"Pattern type '{ptype}' has been detected {count} times in "
                    f"the last {CASCADE_LOOKBACK_SECS // 60} minutes.\n\n"
                    f"Recent entries:\n"
                    + "\n".join(
                        f"- {e.get('timestamp', '?')}: {e.get('detection', '?')[:100]}"
                        for e in recent if e.get("type") == ptype
                    )[:1000],
                    priority="high",
                )
                record_alert_created("hermes", _title, "hermes-watchdog")

    return fired, evidence


# ---------------------------------------------------------------------------
# Check 8: Heartbeat freshness
# ---------------------------------------------------------------------------

def check_heartbeat_freshness(state: dict) -> tuple[bool, dict]:
    """Check all heartbeat files for staleness (>5min).

    Excludes launchd one-shot daemons from freshness checks.
    """
    evidence = {"stale": [], "checked": 0}
    fired = False

    if not HEARTBEATS_DIR.exists():
        return False, evidence

    now = time.time()
    for hb_file in HEARTBEATS_DIR.iterdir():
        if not hb_file.name.endswith(".json"):
            continue
        daemon_name = hb_file.stem

        # Skip launchd one-shots (they run intermittently)
        if daemon_name in LAUNCHD_ONESHOTS:
            continue

        try:
            data = json.loads(hb_file.read_text())
            ts_str = data.get("timestamp", "")
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - ts).total_seconds()
        except Exception:
            age = float("inf")

        evidence["checked"] += 1

        if age > HEARTBEAT_STALE_SECS:
            evidence["stale"].append({
                "daemon": daemon_name,
                "age_s": round(age),
            })
            fired = True
            logger.warning(
                f"Heartbeat stale: {daemon_name} ({age:.0f}s > {HEARTBEAT_STALE_SECS}s)"
            )

    return fired, evidence


# ---------------------------------------------------------------------------
# Check 9: Reflection pipeline
# ---------------------------------------------------------------------------

def check_reflection_pipeline(state: dict) -> tuple[bool, dict]:
    """Check reflection-status.json age. If >48h, force refresh."""
    evidence = {}
    fired = False

    if not REFLECTION_STATUS_FILE.exists():
        evidence["status"] = "missing"
        fired = True
        logger.warning("reflection-status.json missing -- pipeline may have never run")
        write_hermes_task(
            "Reflection Pipeline: status file missing",
            "reflection-status.json does not exist. The hourly reflection pipeline "
            "may have never run or the file was deleted.\n\n"
            "Action: Check cron schedule and run reflection manually if needed.",
            priority="high",
        )
        return fired, evidence

    try:
        age = time.time() - REFLECTION_STATUS_FILE.stat().st_mtime
    except OSError:
        return False, evidence

    evidence["age_s"] = round(age)
    evidence["age_h"] = round(age / 3600, 1)

    if age > REFLECTION_MAX_AGE_SECS:
        fired = True
        evidence["status"] = "stale"
        logger.warning(
            f"Reflection pipeline stale: {evidence['age_h']}h "
            f"(threshold: {REFLECTION_MAX_AGE_SECS // 3600}h)"
        )
        write_hermes_task(
            f"Reflection Pipeline Stale: {evidence['age_h']}h since last run",
            f"reflection-status.json is {evidence['age_h']}h old.\n\n"
            f"Threshold: {REFLECTION_MAX_AGE_SECS // 3600}h\n\n"
            f"Action: Check cron schedule for hourly_reflection.sh, "
            f"inspect logs for errors, run manually if needed.",
            priority="high",
        )
    else:
        evidence["status"] = "healthy"

    return fired, evidence


# ---------------------------------------------------------------------------
# Check 10: Proposal pipeline
# ---------------------------------------------------------------------------

def check_proposal_pipeline(state: dict) -> tuple[bool, dict]:
    """Query Neo4j for open proposals >7d old. Write task to prompt voting."""
    evidence = {"stale_proposals": []}
    fired = False

    try:
        from neo4j_v2_core import TaskStore
        store = TaskStore()
        with store.driver.session() as sess:
            result = sess.run(
                "MATCH (p:Proposal) "
                "WHERE p.status = 'OPEN' "
                "AND p.created_at < datetime() - duration({days: $max_days}) "
                "RETURN p.proposal_id AS id, p.title AS title, "
                "p.created_at AS created_at "
                "LIMIT 20",
                max_days=PROPOSAL_MAX_AGE_DAYS,
            )
            for record in result:
                evidence["stale_proposals"].append({
                    "id": record["id"],
                    "title": record["title"],
                    "created_at": str(record["created_at"]),
                })
        store.close()
    except Exception as e:
        evidence["neo4j_error"] = str(e)
        logger.error(f"Proposal pipeline check Neo4j error: {e}")
        return False, evidence

    if evidence["stale_proposals"]:
        fired = True
        proposal_lines = [
            f"- {p['id']}: {p['title']} (created {p['created_at']})"
            for p in evidence["stale_proposals"]
        ]
        write_hermes_task(
            f"Stale Proposals: {len(evidence['stale_proposals'])} need votes",
            "The following open proposals are older than "
            f"{PROPOSAL_MAX_AGE_DAYS} days and need voting:\n\n"
            + "\n".join(proposal_lines)
            + "\n\nAction: Prompt voting or close stale proposals.",
            priority="normal",
        )

    return fired, evidence


# ---------------------------------------------------------------------------
# Check 11: Knowledge stale
# ---------------------------------------------------------------------------

def check_knowledge_stale(state: dict) -> tuple[bool, dict]:
    """Scan knowledge/*.md for validated_at frontmatter older than 30d.

    Flags if source file mtime is newer than validated_at (knowledge is
    outdated relative to its source).
    """
    evidence = {"stale": []}
    fired = False
    now = time.time()

    for knowledge_dir in KNOWLEDGE_DIRS:
        if not knowledge_dir.exists():
            continue
        for md_file in knowledge_dir.glob("*.md"):
            try:
                content = md_file.read_text()
            except OSError:
                continue

            # Parse frontmatter for validated_at
            parts = content.split("---", 2)
            if len(parts) < 3:
                continue
            frontmatter = parts[1]

            validated_match = re.search(
                r'^validated_at:\s*(.+)$', frontmatter, re.MULTILINE
            )
            if not validated_match:
                continue

            try:
                validated_str = validated_match.group(1).strip().strip('"\'')
                validated_ts = datetime.fromisoformat(validated_str).timestamp()
            except (ValueError, TypeError):
                continue

            age_days = (now - validated_ts) / 86400
            if age_days < KNOWLEDGE_STALE_DAYS:
                continue

            # Check if source file was modified after validation
            source_mtime = md_file.stat().st_mtime
            if source_mtime <= validated_ts:
                continue  # Source hasn't changed since validation

            evidence["stale"].append({
                "file": str(md_file),
                "validated_days_ago": round(age_days, 1),
                "source_newer_by_days": round(
                    (source_mtime - validated_ts) / 86400, 1
                ),
            })
            fired = True

    if evidence["stale"]:
        stale_lines = [
            f"- {e['file']}: validated {e['validated_days_ago']}d ago, "
            f"source updated {e['source_newer_by_days']}d after validation"
            for e in evidence["stale"]
        ]
        write_hermes_task(
            f"Knowledge Stale: {len(evidence['stale'])} file(s) need re-validation",
            "The following knowledge files have been modified since their "
            f"last validation (> {KNOWLEDGE_STALE_DAYS}d ago):\n\n"
            + "\n".join(stale_lines)
            + "\n\nAction: Re-validate knowledge content against current system state.",
            priority="low",
        )
        state["counters"]["knowledge_stale"] = len(evidence["stale"])

    return fired, evidence


# ---------------------------------------------------------------------------
# Main cycle
# ---------------------------------------------------------------------------

def run_cycle(state: dict, dry_run: bool = False) -> dict:
    """Run all checks once. Returns dict of check_name -> result."""
    checks = [
        check_task_executor_alive,
        check_stalled_tasks,
        check_quality_gate_drift,
        check_model_drift,
        check_queue_balance,
        check_agent_failure_rates,
        check_cascade_patterns,
        check_heartbeat_freshness,
        check_reflection_pipeline,
        check_proposal_pipeline,
        check_knowledge_stale,
    ]

    results = {}
    # Set module-level dry_run flag so individual checks can gate T0 fixes
    global DRY_RUN_MODE
    DRY_RUN_MODE = dry_run
    for check_fn in checks:
        try:
            fired, evidence = check_fn(state)
            if dry_run:
                evidence["dry_run"] = True
            results[check_fn.__name__] = {"fired": fired, "evidence": evidence}
        except Exception as e:
            logger.error(f"Check {check_fn.__name__} failed: {e}")
            results[check_fn.__name__] = {"fired": False, "error": str(e)}

    # Emit heartbeat
    write_heartbeat("hermes-watchdog")

    # Save state
    state["last_cycle"] = datetime.now().isoformat()
    state["cycle_count"] = state.get("cycle_count", 0) + 1
    save_state(state)

    # Log summary
    fired_count = sum(1 for r in results.values() if r.get("fired"))
    if fired_count > 0:
        logger.info(
            f"Cycle #{state['cycle_count']}: {fired_count}/{len(checks)} checks fired"
        )
    else:
        logger.info(f"Cycle #{state['cycle_count']}: all clear")

    return results


# ---------------------------------------------------------------------------
# Daemon loop
# ---------------------------------------------------------------------------

def daemon_loop(dry_run: bool = False) -> None:
    """Main daemon loop -- runs cycle every POLL_INTERVAL seconds.

    Self-reload: if this script file is modified, the daemon automatically
    restarts to pick up changes.
    """
    script_path = Path(__file__).resolve()
    last_mtime = script_path.stat().st_mtime
    logger.info(
        f"Hermes Watchdog starting (interval: {POLL_INTERVAL}s, "
        f"dry_run: {dry_run})"
    )
    logger.info(f"State: {STATE_FILE}")
    logger.info(f"Script: {script_path} (mtime: {last_mtime})")

    while not stop_event.is_set():
        # Kill switch: run detection cycle in dry_run mode, skip T0 actions
        cycle_dry_run = dry_run or DISABLED_FLAG.exists()

        try:
            state = load_state()
            run_cycle(state, dry_run=cycle_dry_run)
            write_heartbeat("hermes-watchdog", status="observing" if cycle_dry_run else "running")
        except Exception as e:
            logger.error(f"Error in watchdog cycle: {e}")

        for _ in range(POLL_INTERVAL):
            if stop_event.is_set():
                break
            time.sleep(1)

        # Self-reload check
        try:
            current_mtime = script_path.stat().st_mtime
            if current_mtime > last_mtime:
                logger.info(f"Script modified: {script_path} -- restarting")
                os.execv(
                    sys.executable,
                    [sys.executable, str(script_path)]
                    + (["--daemon", "--dry-run"] if dry_run else ["--daemon"]),
                )
        except Exception as e:
            logger.error(f"Self-reload check failed: {e}")

    logger.info("Hermes Watchdog stopped")


def signal_handler(sig, frame):
    """Handle SIGTERM/SIGINT gracefully."""
    logger.info(f"Received signal {sig}, shutting down...")
    stop_event.set()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Hermes Watchdog -- system caretaker daemon"
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Run single cycle and exit",
    )
    parser.add_argument(
        "--daemon", action="store_true",
        help="Run as persistent daemon (60s interval)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Detect issues but do not apply T0 fixes",
    )
    parser.add_argument(
        "--status", action="store_true",
        help="Print current state and exit",
    )
    args = parser.parse_args()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    kill_switch_active = DISABLED_FLAG.exists()
    if kill_switch_active:
        print(f"Kill switch active: {DISABLED_FLAG} — detection only, T0 actions disabled")

    if not verify_import_integrity():
        print("IMPORT INTEGRITY CHECK FAILED — self-kill-switch activated. Refusing to proceed.")
        return 1

    if args.status:
        state = load_state()
        print(json.dumps(state, indent=2))
        return 0

    if args.once:
        state = load_state()
        results = run_cycle(state, dry_run=args.dry_run or kill_switch_active)
        fired = [k for k, v in results.items() if v.get("fired")]
        if fired:
            print(f"Checks fired: {len(fired)}/{len(results)}")
            for name in fired:
                ev = results[name].get("evidence", {})
                print(f"  - {name}: {json.dumps(ev, default=str)[:200]}")
        else:
            print("All checks passed -- no issues detected")
        return 0

    # Default: daemon mode
    daemon_loop(dry_run=args.dry_run or kill_switch_active)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
