#!/usr/bin/env python3
"""
hermes_auto_fix.py -- T0 Auto-Fix Library for Hermes.

Safe, deterministic remediations that don't require LLM reasoning.
Each function supports dry-run mode and checks the kill-switch flag.

Kill switch: ~/.openclaw/flags/hermes-disabled.flag

Usage:
    from hermes_auto_fix import requeue_stuck_task, rotate_failing_provider

    result = requeue_stuck_task(task_path, dry_run=True)
    # result = {"action": "requeue_stuck_task", "target": str(task_path),
    #           "dry_run": True, "outcome": "would_requeue", "evidence": {...}}
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# Path setup -- allow imports from the same scripts directory
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent))

from kurultai_paths import AGENTS_DIR, LOGS_DIR  # noqa: E402
from kurultai_logging import get_logger, write_heartbeat  # noqa: E402
from json_state import locked_json_read, locked_json_update  # noqa: E402

logger = get_logger("hermes-auto-fix", agent="hermes")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
KILL_SWITCH_PATH: Path = Path.home() / ".openclaw" / "flags" / "hermes-disabled.flag"
RISKY_KILL_SWITCH_PATH: Path = Path.home() / ".openclaw" / "flags" / "hermes-risky-disabled.flag"
AUTONOMOUS_DISABLED_PATH: Path = Path.home() / ".openclaw" / "flags" / "hermes-autonomous-disabled.flag"
AUTONOMOUS_FIX_CODE_DISABLED_PATH: Path = Path.home() / ".openclaw" / "flags" / "hermes-autonomous-fix-code-disabled.flag"
AUTONOMOUS_FIX_CONTENT_DISABLED_PATH: Path = Path.home() / ".openclaw" / "flags" / "hermes-autonomous-fix-content-disabled.flag"
AUTONOMOUS_SWEEP_DISABLED_PATH: Path = Path.home() / ".openclaw" / "flags" / "hermes-autonomous-sweep-disabled.flag"
HERMES_ACTIONS_LOG: Path = LOGS_DIR / "hermes-actions.jsonl"
SESSION_BLOAT_THRESHOLD: int = 100_000  # 100 KB

SCRIPTS_DIR = Path(__file__).resolve().parent


# ===================================================================
# 1. Kill switch
# ===================================================================

def _check_kill_switch() -> bool:
    """Return True if the kill-switch flag file exists.

    Fail-closed: any OSError treated as "flag present" to avoid firing T0s
    during transient FS errors.
    """
    try:
        return KILL_SWITCH_PATH.exists()
    except OSError:
        return True


def _check_risky_kill_switch() -> bool:
    """Return True if the risky-action-only flag file exists.

    Blocks credential-affecting T0s (rotate_failing_provider,
    force_refresh_reflection_bridge) while allowing safe T0s.
    Fail-closed on OSError.
    """
    try:
        return RISKY_KILL_SWITCH_PATH.exists()
    except OSError:
        return True


def _check_autonomous_disabled() -> bool:
    """Return True if the master autonomous-mode flag is engaged.

    Overrides all per-capability autonomous flags below. Fail-closed on OSError.
    """
    try:
        return AUTONOMOUS_DISABLED_PATH.exists()
    except OSError:
        return True


def _check_autonomous_fix_code_disabled() -> bool:
    """Return True if autonomous code-fix mode is disabled.

    Applies only to the hermes_fix_engine code-patch path (Phase 4+ of the
    autonomous-improvement plan). Fail-closed on OSError.
    """
    try:
        return AUTONOMOUS_FIX_CODE_DISABLED_PATH.exists()
    except OSError:
        return True


def _check_autonomous_fix_content_disabled() -> bool:
    """Return True if autonomous content-fix mode is disabled.

    Applies only to the hermes_fix_engine content-patch path (Phase 3+ of the
    autonomous-improvement plan). Fail-closed on OSError.
    """
    try:
        return AUTONOMOUS_FIX_CONTENT_DISABLED_PATH.exists()
    except OSError:
        return True


def _check_autonomous_sweep_disabled() -> bool:
    """Return True if scheduled autonomous sweeps are disabled.

    Applies to hermes_sweep_runner invocations (Phase 5+ of the
    autonomous-improvement plan). Fail-closed on OSError.
    """
    try:
        return AUTONOMOUS_SWEEP_DISABLED_PATH.exists()
    except OSError:
        return True


# ===================================================================
# 2. Hermes action emitter
# ===================================================================

def _emit_hermes_action(
    action_type: str,
    target: str,
    outcome: str,
    tier: str = "T0",
    dry_run: bool = False,
    evidence: Optional[Dict[str, Any]] = None,
) -> None:
    """Record a HermesAction to both the local JSONL log and Neo4j.

    Failures to write to either destination are logged but never raised
    so that the calling T0 function can still return its result dict.
    """
    now = datetime.now(timezone.utc)
    entry: Dict[str, Any] = {
        "timestamp": now.isoformat(),
        "action_type": action_type,
        "target": target,
        "tier": tier,
        "dry_run": dry_run,
        "outcome": outcome,
        "evidence": evidence or {},
    }

    # -- JSONL append --
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        with open(HERMES_ACTIONS_LOG, "a") as fh:
            fh.write(json.dumps(entry, default=str) + "\n")
    except Exception:
        logger.warning("Failed to append to hermes-actions.jsonl", exc_info=True)

    # -- Neo4j HermesAction node --
    try:
        from neo4j_v2_core import TaskStore  # deferred import

        store = TaskStore()
        try:
            driver = store.driver
            with driver.session() as session:
                session.run(
                    """
                    CREATE (n:HermesAction {
                        timestamp: datetime($ts),
                        action_type: $action_type,
                        target: $target,
                        tier: $tier,
                        dry_run: $dry_run,
                        outcome: $outcome,
                        evidence: $evidence
                    })
                    """,
                    ts=now.isoformat(),
                    action_type=action_type,
                    target=target,
                    tier=tier,
                    dry_run=dry_run,
                    outcome=outcome,
                    evidence=json.dumps(evidence or {}, default=str),
                )
        finally:
            store.close()
    except Exception:
        logger.warning("Failed to write HermesAction to Neo4j", exc_info=True)


# ===================================================================
# 3. requeue_stuck_task
# ===================================================================

def requeue_stuck_task(task_path: str, dry_run: bool = False) -> Dict[str, Any]:
    """Emit a HERMES_REQUEST_REAP event for a stuck task.

    Detection-only: verifies PID is dead, then emits a Neo4j Event for
    task-reaper to consume. Does NOT perform file moves or session_key clears
    (single-writer principle: task-reaper.py is the sole owner of reaping).
    """
    action = "request_task_reap"
    target = str(task_path)

    if _check_kill_switch():
        result = {"action": action, "target": target, "dry_run": dry_run,
                  "outcome": "DISABLED_BY_FLAG", "evidence": {}}
        _emit_hermes_action(action, target, "DISABLED_BY_FLAG", dry_run=dry_run)
        return result

    path = Path(task_path)

    # Validate extension
    if not path.name.endswith(".executing.md"):
        msg = f"Task file does not end in .executing.md: {path.name}"
        result = {"action": action, "target": target, "dry_run": dry_run,
                  "outcome": "skipped", "evidence": {"reason": msg}}
        _emit_hermes_action(action, target, "skipped", dry_run=dry_run,
                            evidence={"reason": msg})
        return result

    # Read frontmatter to extract PID and task_id
    pid: Optional[int] = None
    task_id: Optional[str] = None
    try:
        content = path.read_text(encoding="utf-8", errors="replace")[:4000]
        pid_match = re.search(r"pid:\s*(\d+)", content)
        if pid_match:
            pid = int(pid_match.group(1))
        tid_match = re.search(r"task_id:\s*(\S+)", content)
        if tid_match:
            task_id = tid_match.group(1)
    except FileNotFoundError:
        result = {"action": action, "target": target, "dry_run": dry_run,
                  "outcome": "error", "evidence": {"reason": "file not found"}}
        _emit_hermes_action(action, target, "error", dry_run=dry_run,
                            evidence={"reason": "file not found"})
        return result

    # Check if PID is alive via lsof
    pid_alive = False
    if pid is not None:
        try:
            proc = subprocess.run(
                ["lsof", "-p", str(pid)],
                capture_output=True, text=True, timeout=5,
            )
            pid_alive = bool(proc.stdout.strip())
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pid_alive = True
    else:
        pid_alive = False

    evidence: Dict[str, Any] = {
        "task_id": task_id,
        "pid": pid,
        "pid_alive": pid_alive,
    }

    if pid_alive:
        result = {"action": action, "target": target, "dry_run": dry_run,
                  "outcome": "skipped", "evidence": {**evidence,
                  "reason": "PID still alive"}}
        _emit_hermes_action(action, target, "skipped", dry_run=dry_run,
                            evidence=result["evidence"])
        return result

    if dry_run:
        result = {"action": action, "target": target, "dry_run": dry_run,
                  "outcome": "would_emit_reap", "evidence": evidence}
        _emit_hermes_action(action, target, "would_emit_reap", dry_run=dry_run,
                            evidence=evidence)
        return result

    # Emit HERMES_REQUEST_REAP event for task-reaper to consume
    try:
        from neo4j_v2_core import TaskStore
        store = TaskStore()
        try:
            driver = store.driver
            with driver.session() as session:
                session.run(
                    "CREATE (e:Event {type: 'HERMES_REQUEST_REAP', "
                    "task_path: $path, task_id: $tid, pid: $pid, "
                    "agent: 'hermes', consumed: false, "
                    "timestamp: timestamp(), created_at: datetime()})",
                    {"path": str(path), "tid": task_id or "", "pid": pid or 0},
                )
            evidence["event_emitted"] = True
            logger.info(f"Emitted HERMES_REQUEST_REAP for {path.name}")
        finally:
            store.close()
    except Exception as exc:
        logger.warning(f"Failed to emit HERMES_REQUEST_REAP: {exc}")
        evidence["event_emitted"] = False
        evidence["emit_error"] = str(exc)

    result = {"action": action, "target": target, "dry_run": dry_run,
              "outcome": "event_emitted", "evidence": evidence}
    _emit_hermes_action(action, target, "event_emitted", dry_run=dry_run, evidence=evidence)
    return result


# ===================================================================
# 4. rotate_failing_provider
# ===================================================================

def rotate_failing_provider(agent: str, dry_run: bool = False) -> Dict[str, Any]:
    """Mark the primary provider as failed and switch to the backup.

    Reads the agent's mode.json, flags the current provider, and activates
    the backup if one is available.
    """
    action = "rotate_failing_provider"
    target = agent

    if _check_kill_switch():
        result = {"action": action, "target": target, "dry_run": dry_run,
                  "outcome": "DISABLED_BY_FLAG", "evidence": {}}
        _emit_hermes_action(action, target, "DISABLED_BY_FLAG", dry_run=dry_run)
        return result

    if _check_risky_kill_switch():
        result = {"action": action, "target": target, "dry_run": dry_run,
                  "outcome": "DISABLED_BY_RISKY_FLAG", "evidence": {}}
        _emit_hermes_action(action, target, "DISABLED_BY_RISKY_FLAG", dry_run=dry_run)
        return result

    mode_path = AGENTS_DIR / agent / "mode.json"
    if not mode_path.exists():
        result = {"action": action, "target": target, "dry_run": dry_run,
                  "outcome": "error", "evidence": {"reason": "mode.json not found",
                  "path": str(mode_path)}}
        _emit_hermes_action(action, target, "error", dry_run=dry_run,
                            evidence=result["evidence"])
        return result

    data = locked_json_read(str(mode_path))
    if not data:
        result = {"action": action, "target": target, "dry_run": dry_run,
                  "outcome": "error", "evidence": {"reason": "mode.json empty or unreadable"}}
        _emit_hermes_action(action, target, "error", dry_run=dry_run,
                            evidence=result["evidence"])
        return result

    providers = data.get("providers", [])
    if not providers:
        result = {"action": action, "target": target, "dry_run": dry_run,
                  "outcome": "skipped", "evidence": {"reason": "no providers configured"}}
        _emit_hermes_action(action, target, "skipped", dry_run=dry_run,
                            evidence=result["evidence"])
        return result

    # Find primary (first non-failed) and backup
    primary = None
    backup = None
    for provider in providers:
        if not provider.get("failed", False):
            if primary is None:
                primary = provider
            elif backup is None:
                backup = provider

    evidence: Dict[str, Any] = {
        "primary": primary.get("name") if primary else None,
        "backup": backup.get("name") if backup else None,
    }

    if primary is None:
        result = {"action": action, "target": target, "dry_run": dry_run,
                  "outcome": "skipped", "evidence": {**evidence,
                  "reason": "all providers already marked failed"}}
        _emit_hermes_action(action, target, "skipped", dry_run=dry_run,
                            evidence=result["evidence"])
        return result

    if backup is None:
        result = {"action": action, "target": target, "dry_run": dry_run,
                  "outcome": "skipped", "evidence": {**evidence,
                  "reason": "no backup provider available"}}
        _emit_hermes_action(action, target, "skipped", dry_run=dry_run,
                            evidence=result["evidence"])
        return result

    if dry_run:
        result = {"action": action, "target": target, "dry_run": dry_run,
                  "outcome": "would_rotate", "evidence": {**evidence,
                  "new_primary": backup.get("name")}}
        _emit_hermes_action(action, target, "would_rotate", dry_run=dry_run,
                            evidence=result["evidence"])
        return result

    # -- Live operation --
    # Mark primary as failed, reorder so backup becomes first
    primary["failed"] = True
    primary["failed_at"] = datetime.now(timezone.utc).isoformat()

    providers.remove(backup)
    providers.remove(primary)
    providers.insert(0, backup)
    providers.append(primary)

    data["providers"] = providers

    try:
        with locked_json_update(str(mode_path)) as locked_data:
            locked_data.update(data)
    except Exception as exc:
        result = {"action": action, "target": target, "dry_run": dry_run,
                  "outcome": "error", "evidence": {**evidence,
                  "reason": f"failed to write mode.json: {exc}"}}
        _emit_hermes_action(action, target, "error", dry_run=dry_run,
                            evidence=result["evidence"])
        return result

    evidence["new_primary"] = backup.get("name")
    result = {"action": action, "target": target, "dry_run": dry_run,
              "outcome": "rotated", "evidence": evidence}
    _emit_hermes_action(action, target, "rotated", dry_run=dry_run, evidence=evidence)
    return result


# ===================================================================
# 5. clear_bloated_session
# ===================================================================

def clear_bloated_session(agent: str, dry_run: bool = False) -> Dict[str, Any]:
    """Archive an oversized sessions.json if the agent has no active tasks."""
    action = "clear_bloated_session"
    target = agent

    if _check_kill_switch():
        result = {"action": action, "target": target, "dry_run": dry_run,
                  "outcome": "DISABLED_BY_FLAG", "evidence": {}}
        _emit_hermes_action(action, target, "DISABLED_BY_FLAG", dry_run=dry_run)
        return result

    sessions_path = AGENTS_DIR / agent / "sessions" / "sessions.json"
    if not sessions_path.exists():
        result = {"action": action, "target": target, "dry_run": dry_run,
                  "outcome": "skipped", "evidence": {"reason": "sessions.json not found"}}
        _emit_hermes_action(action, target, "skipped", dry_run=dry_run,
                            evidence=result["evidence"])
        return result

    file_size = sessions_path.stat().st_size
    evidence: Dict[str, Any] = {"size_bytes": file_size, "threshold": SESSION_BLOAT_THRESHOLD}

    if file_size <= SESSION_BLOAT_THRESHOLD:
        result = {"action": action, "target": target, "dry_run": dry_run,
                  "outcome": "skipped", "evidence": {**evidence,
                  "reason": "below bloat threshold"}}
        _emit_hermes_action(action, target, "skipped", dry_run=dry_run,
                            evidence=result["evidence"])
        return result

    # Check for active .executing.md tasks
    tasks_dir = AGENTS_DIR / agent / "tasks"
    executing_files = list(tasks_dir.glob("*.executing.md")) if tasks_dir.is_dir() else []
    evidence["active_executing"] = len(executing_files)

    if executing_files:
        result = {"action": action, "target": target, "dry_run": dry_run,
                  "outcome": "skipped", "evidence": {**evidence,
                  "reason": "agent has active executing tasks",
                  "files": [f.name for f in executing_files[:5]]}}
        _emit_hermes_action(action, target, "skipped", dry_run=dry_run,
                            evidence=result["evidence"])
        return result

    # Prepare archive destination
    archive_dir = AGENTS_DIR / agent / "sessions" / ".archive-backup"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_name = f"sessions-{timestamp}.json"
    archive_path = archive_dir / archive_name
    evidence["archive_path"] = str(archive_path)

    if dry_run:
        result = {"action": action, "target": target, "dry_run": dry_run,
                  "outcome": "would_archive", "evidence": evidence}
        _emit_hermes_action(action, target, "would_archive", dry_run=dry_run,
                            evidence=evidence)
        return result

    # -- Live operation --
    try:
        archive_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(sessions_path), str(archive_path))
        # Create a fresh empty sessions file
        sessions_path.write_text("{}\n", encoding="utf-8")
    except OSError as exc:
        result = {"action": action, "target": target, "dry_run": dry_run,
                  "outcome": "error", "evidence": {**evidence,
                  "reason": f"archive failed: {exc}"}}
        _emit_hermes_action(action, target, "error", dry_run=dry_run,
                            evidence=result["evidence"])
        return result

    result = {"action": action, "target": target, "dry_run": dry_run,
              "outcome": "archived", "evidence": evidence}
    _emit_hermes_action(action, target, "archived", dry_run=dry_run, evidence=evidence)
    return result


# ===================================================================
# 6. force_refresh_reflection_bridge
# ===================================================================

def force_refresh_reflection_bridge(dry_run: bool = False) -> Dict[str, Any]:
    """Run reflection_pipeline_bridge.py --force as a subprocess."""
    action = "force_refresh_reflection_bridge"
    target = "reflection_pipeline"

    if _check_kill_switch():
        result = {"action": action, "target": target, "dry_run": dry_run,
                  "outcome": "DISABLED_BY_FLAG", "evidence": {}}
        _emit_hermes_action(action, target, "DISABLED_BY_FLAG", dry_run=dry_run)
        return result

    if _check_risky_kill_switch():
        result = {"action": action, "target": target, "dry_run": dry_run,
                  "outcome": "DISABLED_BY_RISKY_FLAG", "evidence": {}}
        _emit_hermes_action(action, target, "DISABLED_BY_RISKY_FLAG", dry_run=dry_run)
        return result

    bridge_script = SCRIPTS_DIR / "reflection_pipeline_bridge.py"
    if not bridge_script.exists():
        result = {"action": action, "target": target, "dry_run": dry_run,
                  "outcome": "error", "evidence": {"reason": "bridge script not found",
                  "path": str(bridge_script)}}
        _emit_hermes_action(action, target, "error", dry_run=dry_run,
                            evidence=result["evidence"])
        return result

    if dry_run:
        result = {"action": action, "target": target, "dry_run": dry_run,
                  "outcome": "would_run", "evidence": {"command": "python3 reflection_pipeline_bridge.py --force"}}
        _emit_hermes_action(action, target, "would_run", dry_run=dry_run,
                            evidence=result["evidence"])
        return result

    # -- Live operation --
    cmd = [sys.executable, str(bridge_script), "--force"]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
        )
        evidence: Dict[str, Any] = {
            "returncode": proc.returncode,
            "stdout_tail": (proc.stdout or "")[-500:],
            "stderr_tail": (proc.stderr or "")[-500:],
        }
        outcome = "success" if proc.returncode == 0 else "script_error"
    except subprocess.TimeoutExpired:
        evidence = {"reason": "script timed out after 120s"}
        outcome = "timeout"
    except Exception as exc:
        evidence = {"reason": str(exc)}
        outcome = "error"

    result = {"action": action, "target": target, "dry_run": dry_run,
              "outcome": outcome, "evidence": evidence}
    _emit_hermes_action(action, target, outcome, dry_run=dry_run, evidence=evidence)
    return result


# ===================================================================
# 7. reconcile_orphan_tasks
# ===================================================================

def reconcile_orphan_tasks(dry_run: bool = False) -> Dict[str, Any]:
    """Run task-consistency-reconciler.py to detect and fix inconsistencies."""
    action = "reconcile_orphan_tasks"
    target = "neo4j_disk_consistency"

    if _check_kill_switch():
        result = {"action": action, "target": target, "dry_run": dry_run,
                  "outcome": "DISABLED_BY_FLAG", "evidence": {}}
        _emit_hermes_action(action, target, "DISABLED_BY_FLAG", dry_run=dry_run)
        return result

    reconciler_script = SCRIPTS_DIR / "task-consistency-reconciler.py"
    if not reconciler_script.exists():
        result = {"action": action, "target": target, "dry_run": dry_run,
                  "outcome": "error", "evidence": {"reason": "reconciler script not found",
                  "path": str(reconciler_script)}}
        _emit_hermes_action(action, target, "error", dry_run=dry_run,
                            evidence=result["evidence"])
        return result

    # --dry-run maps to default behavior (dry-run by default); --fix applies changes
    cmd = [sys.executable, str(reconciler_script)]
    if not dry_run:
        cmd.append("--fix")

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
        )
        evidence: Dict[str, Any] = {
            "returncode": proc.returncode,
            "stdout_tail": (proc.stdout or "")[-1000:],
            "stderr_tail": (proc.stderr or "")[-500:],
            "mode": "dry_run" if dry_run else "fix",
        }
        outcome = "success" if proc.returncode == 0 else "script_error"
    except subprocess.TimeoutExpired:
        evidence = {"reason": "reconciler timed out after 120s",
                    "mode": "dry_run" if dry_run else "fix"}
        outcome = "timeout"
    except Exception as exc:
        evidence = {"reason": str(exc)}
        outcome = "error"

    result = {"action": action, "target": target, "dry_run": dry_run,
              "outcome": outcome, "evidence": evidence}
    _emit_hermes_action(action, target, outcome, dry_run=dry_run, evidence=evidence)
    return result


# ===================================================================
# 8. emit_hermes_heartbeat
# ===================================================================

def emit_hermes_heartbeat() -> None:
    """Write a heartbeat file for the hermes-watchdog daemon."""
    write_heartbeat(daemon_name="hermes-watchdog")


# ===================================================================
# CLI entry point
# ===================================================================

def _build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Hermes T0 Auto-Fix Library -- run individual remediations from the CLI.",
    )
    parser.add_argument(
        "--action",
        required=True,
        choices=[
            "requeue_stuck_task",
            "rotate_failing_provider",
            "clear_bloated_session",
            "force_refresh_reflection_bridge",
            "reconcile_orphan_tasks",
            "emit_heartbeat",
        ],
        help="The auto-fix action to perform.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Preview the action without applying changes.",
    )
    parser.add_argument(
        "--target",
        default=None,
        help="Target for the action: task file path (requeue_stuck_task) "
             "or agent name (rotate_failing_provider, clear_bloated_session).",
    )
    return parser


def main() -> None:
    parser = _build_cli_parser()
    args = parser.parse_args()

    dispatch = {
        "requeue_stuck_task": lambda: requeue_stuck_task(args.target or "", dry_run=args.dry_run),
        "rotate_failing_provider": lambda: rotate_failing_provider(args.target or "", dry_run=args.dry_run),
        "clear_bloated_session": lambda: clear_bloated_session(args.target or "", dry_run=args.dry_run),
        "force_refresh_reflection_bridge": lambda: force_refresh_reflection_bridge(dry_run=args.dry_run),
        "reconcile_orphan_tasks": lambda: reconcile_orphan_tasks(dry_run=args.dry_run),
        "emit_heartbeat": lambda: (emit_hermes_heartbeat(), {"action": "emit_heartbeat", "outcome": "written"}),
    }

    handler = dispatch.get(args.action)
    if handler is None:
        parser.error(f"Unknown action: {args.action}")

    result = handler()

    # emit_heartbeat returns a tuple; unwrap it
    if isinstance(result, tuple):
        result = result[1]

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
