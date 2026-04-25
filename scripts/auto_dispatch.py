#!/usr/bin/env python3
"""
auto_dispatch.py — Periodic cleanup for Kurultai agent task queues.

Runs every 5 minutes via cron. For each agent:
1. Check if dispatched processes (PIDs) have finished and clear state
2. Clean up stale .executing tasks (>15 min old → revert to pending)

NOTE: Dispatch is now handled exclusively by task_executor.py → claude-agent.
This script no longer dispatches new tasks — it only does cleanup
to prevent stale .executing files from blocking the pipeline.

Usage:
    python3 auto_dispatch.py              # cleanup all agents
    python3 auto_dispatch.py --agent temujin  # cleanup single agent
    python3 auto_dispatch.py --dry-run    # show what would be cleaned
    python3 auto_dispatch.py --cleanup    # same as default (cleanup only)
"""
from __future__ import annotations

import argparse
import fcntl
import gc
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from json_state import locked_json_update
from kurultai_paths import (
    AGENTS_DIR as AGENTS_BASE, DISPATCH_AGENTS, DISPATCH_LOG, DISPATCH_STATE, LOGS_DIR,
)

# ============================================================
# Configuration
# ============================================================
LOCK_FILE = LOGS_DIR / "auto-dispatch.lock"

# Stale task threshold — imported from canonical source (kurultai_paths.py)
# STALE_REVERT_SECS (1200s/20min) > STALE_EXECUTING_SECS (900s/15min) to avoid
# reverting tasks that task-watcher is still monitoring.
from kurultai_paths import STALE_REVERT_SECS as STALE_EXECUTING_SECS

# Max tasks to dispatch per cycle (across all agents)
MAX_DISPATCHES_PER_CYCLE = 3

# Dispatch timeout: how long to wait for openclaw agent to start
DISPATCH_START_TIMEOUT = 30  # seconds

# OpenClaw binary
OPENCLAW_BIN = "/opt/homebrew/bin/openclaw"

# Environment for subprocess
DISPATCH_ENV = {
    "PATH": "/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
    "NODE_PATH": "/opt/homebrew/lib/node_modules",
    "OPENCLAW_STATE_DIR": "/Users/kublai/.openclaw",
    "HOME": str(Path.home()),
}


# ============================================================
# Logging
# ============================================================
def log(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {level}: {msg}"
    print(line)


def log_dispatch(entry):
    """Append a dispatch record to the JSONL log."""
    try:
        os.makedirs(DISPATCH_LOG.parent, exist_ok=True)
        with open(DISPATCH_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


# ============================================================
# Task scanning
# ============================================================
def list_pending_tasks(agent):
    """List pending tasks for an agent, sorted by priority."""
    tasks_dir = AGENTS_BASE / agent / "tasks"
    if not tasks_dir.exists():
        return []

    pending = []
    for f in tasks_dir.iterdir():
        if not f.name.endswith(".md"):
            continue
        # Skip completed/executing/done tasks
        if any(x in f.name for x in [".executing", ".completed", ".done"]):
            continue
        # Skip directories and non-files
        if not f.is_file():
            continue
        pending.append(f)

    # Sort by priority: high > normal > low, then by mtime (oldest first)
    def priority_key(path):
        name = path.name.lower()
        if name.startswith("high-"):
            return (0, path.stat().st_mtime)
        elif name.startswith("normal-"):
            return (1, path.stat().st_mtime)
        elif name.startswith("low-"):
            return (2, path.stat().st_mtime)
        # direct-* tasks and others: treat as normal priority
        return (1, path.stat().st_mtime)

    return sorted(pending, key=priority_key)


def list_executing_tasks(agent):
    """List currently executing tasks for an agent."""
    tasks_dir = AGENTS_BASE / agent / "tasks"
    if not tasks_dir.exists():
        return []

    executing = []
    for f in tasks_dir.iterdir():
        if f.name.endswith(".executing.md") and f.is_file():
            executing.append(f)
    return executing


def check_completed_dispatches(agent):
    """Check if dispatched processes have finished and mark tasks .done.

    Reads the dispatch state to find PIDs. If a PID is no longer running,
    the task is considered complete and renamed from .executing to .done.
    This prevents the stale-revert-redispatch loop.
    """
    completed = 0
    try:
        if not DISPATCH_STATE.exists():
            return 0
        with open(DISPATCH_STATE, "r") as f:
            state = json.load(f)
        dispatch_info = state.get("dispatches", {}).get(agent)
        if not dispatch_info:
            return 0

        pid = dispatch_info.get("pid")
        task_name = dispatch_info.get("task", "")
        if not pid:
            return 0

        # Check if PID is still running
        try:
            os.kill(pid, 0)  # signal 0 = existence check
            return 0  # still running
        except ProcessLookupError:
            pass  # process finished
        except PermissionError:
            return 0  # still running, different user

        # Process finished — find the .executing file and determine outcome
        tasks_dir = AGENTS_BASE / agent / "tasks"
        dispatch_log = AGENTS_BASE / "main/logs" / f"dispatch-{agent}.log"
        for f in tasks_dir.iterdir():
            if f.name.endswith(".executing.md") and f.is_file():
                base_name = f.name.replace(".executing.md", "")
                if base_name == task_name or task_name in f.name:
                    # Check dispatch log for completion evidence
                    has_output = False
                    if dispatch_log.exists():
                        try:
                            log_text = dispatch_log.read_text()[-5000:]
                            # Look for success markers after the dispatch entry
                            if "Task completed" in log_text or "✅" in log_text or "✓" in log_text:
                                has_output = True
                        except Exception:
                            pass

                    if has_output:
                        done_path = f.parent / (base_name + ".completed.done")
                        status = "completed"
                    else:
                        done_path = f.parent / (base_name + ".failed.done")
                        status = "failed"

                    try:
                        f.rename(done_path)
                        log(f"{status.upper()} dispatch for {agent}: {base_name} (PID {pid} exited)")
                        log_dispatch({
                            "ts": datetime.now().isoformat(),
                            "action": f"{status}_dispatch",
                            "agent": agent,
                            "task": base_name,
                            "pid": pid,
                        })
                        completed += 1
                    except Exception as e:
                        log(f"Failed to mark {status} {f.name}: {e}", "ERROR")

        # Clear the dispatch state for this agent — always clear when PID is dead,
        # even if no .executing file was found (task-watcher may have already handled it)
        try:
            with locked_json_update(str(DISPATCH_STATE), default={"dispatches": {}}) as data:
                if "dispatches" in data and agent in data["dispatches"]:
                    del data["dispatches"][agent]
        except Exception:
            pass

    except Exception as e:
        log(f"Error checking completed dispatches for {agent}: {e}", "ERROR")

    return completed


def cleanup_stale_executing(agent):
    """Revert .executing tasks that have been stuck for too long.

    First checks if the dispatch process has completed (PID exited) and
    marks those as .done. Only reverts tasks whose PIDs are unknown or
    where the process is truly gone and stuck beyond the threshold.
    """
    # First: check for completed dispatches (PID-based)
    check_completed_dispatches(agent)

    executing = list_executing_tasks(agent)
    reverted = 0

    for task_file in executing:
        try:
            age_secs = time.time() - task_file.stat().st_mtime
        except FileNotFoundError:
            # Race condition: file was renamed/moved by another process (task completed)
            log(f"SKIP revert for {agent}: {task_file.name} — file moved (likely completed)")
            continue
        if age_secs > STALE_EXECUTING_SECS:
            # Check .executing.pid file — if the handler process is still alive, skip
            pid_file = task_file.parent / task_file.name.replace(".executing.md", ".executing.pid")
            if pid_file.exists():
                try:
                    handler_pid = int(pid_file.read_text().strip())
                    os.kill(handler_pid, 0)  # signal 0 = existence check
                    log(f"SKIP revert for {agent}: {task_file.name} — handler PID {handler_pid} still alive")
                    continue
                except (ProcessLookupError, ValueError):
                    pass  # PID dead or invalid — safe to revert
                except PermissionError:
                    log(f"SKIP revert for {agent}: {task_file.name} — handler PID still running (permission)")
                    continue

            # Revert: remove .executing suffix
            original_name = task_file.name.replace(".executing", "")
            original_path = task_file.parent / original_name
            try:
                task_file.rename(original_path)
                log(f"REVERTED stale task for {agent}: {original_name} (stuck {age_secs:.0f}s)")
                log_dispatch({
                    "ts": datetime.now().isoformat(),
                    "action": "revert_stale",
                    "agent": agent,
                    "task": original_name,
                    "stuck_secs": int(age_secs),
                })
                reverted += 1
                # Clean up orphaned PID file if it exists
                if pid_file.exists():
                    try:
                        pid_file.unlink()
                    except OSError:
                        pass
            except Exception as e:
                log(f"Failed to revert {task_file.name}: {e}", "ERROR")

    return reverted


def read_task_content(task_file):
    """Read task file content, return (title, body)."""
    try:
        content = task_file.read_text(encoding="utf-8", errors="replace")
        # Extract title from markdown
        title = ""
        for line in content.split("\n"):
            if line.startswith("# Task:"):
                title = line[7:].strip()
                break
            elif line.startswith("# "):
                title = line[2:].strip()
                break
        if not title:
            title = task_file.stem
        return title, content
    except Exception as e:
        return task_file.stem, f"(Failed to read: {e})"


# ============================================================
# Dispatch
# ============================================================
def dispatch_task(agent, task_file, dry_run=False):
    """Dispatch a single task to an agent via openclaw agent.

    Returns (success, message).
    """
    title, content = read_task_content(task_file)

    # Sanitize content for shell safety
    safe_content = re.sub(r'[\x00-\x1f\x7f]', '', content[:2000])

    if dry_run:
        log(f"DRY RUN: would dispatch to {agent}: {title[:80]}")
        return True, "dry_run"

    # Mark as executing
    executing_path = task_file.parent / (task_file.name + ".executing")
    try:
        task_file.rename(executing_path)
    except Exception as e:
        return False, f"Failed to mark executing: {e}"

    # Build dispatch command
    message = f"Execute this task:\n\n{safe_content}"
    cmd = [
        OPENCLAW_BIN,
        "agent",
        "--agent", agent,
        "--message", message,
        "--thinking", "high",
    ]

    try:
        # Non-blocking dispatch — Popen so we don't wait for completion
        dispatch_log_file = AGENTS_BASE / "main/logs" / f"dispatch-{agent}.log"
        with open(dispatch_log_file, "a") as logf:
            logf.write(f"\n{'='*60}\n")
            logf.write(f"[{datetime.now().isoformat()}] Dispatching: {title[:80]}\n")
            logf.write(f"Task file: {task_file.name}\n")
            logf.write(f"{'='*60}\n")
            logf.flush()

            proc = subprocess.Popen(
                cmd,
                stdout=logf,
                stderr=subprocess.STDOUT,
                cwd=str(AGENTS_BASE / "main"),
                env=DISPATCH_ENV,
            )

        log(f"DISPATCHED to {agent} (PID {proc.pid}): {title[:80]}")

        # Record dispatch state for tock metrics
        update_dispatch_state(agent, task_file.name, proc.pid, title)

        log_dispatch({
            "ts": datetime.now().isoformat(),
            "action": "dispatch",
            "agent": agent,
            "task": task_file.name,
            "title": title[:80],
            "pid": proc.pid,
        })

        return True, f"PID {proc.pid}"

    except FileNotFoundError:
        # openclaw binary not found — revert
        try:
            executing_path.rename(task_file)
        except Exception:
            pass
        return False, f"openclaw binary not found at {OPENCLAW_BIN}"

    except Exception as e:
        # Revert on any error
        try:
            executing_path.rename(task_file)
        except Exception:
            pass
        return False, f"Dispatch error: {e}"


def update_dispatch_state(agent, task_name, pid, title):
    """Update the dispatch state file for tock consumption."""
    try:
        with locked_json_update(str(DISPATCH_STATE), default={"dispatches": {}}) as data:
            if "dispatches" not in data:
                data["dispatches"] = {}
            data["dispatches"][agent] = {
                "task": task_name,
                "title": title[:80],
                "pid": pid,
                "dispatched_at": datetime.now().isoformat(),
            }
            data["last_cycle"] = datetime.now().isoformat()
    except Exception:
        pass


# ============================================================
# Main cycle
# ============================================================
def run_cycle(target_agent=None, dry_run=False, cleanup_only=False):
    """Run one cleanup cycle.

    Dispatch is handled by task-watcher.py — this only does stale cleanup.
    Returns dict with cycle stats.
    """
    agents = [target_agent] if target_agent else DISPATCH_AGENTS
    stats = {
        "reverted": 0,
        "dispatched": 0,
        "skipped_busy": 0,
        "skipped_empty": 0,
        "errors": 0,
    }

    for agent in agents:
        agent_dir = AGENTS_BASE / agent
        if not agent_dir.exists():
            continue

        # Cleanup stale executing tasks and check completed dispatches
        reverted = cleanup_stale_executing(agent)
        stats["reverted"] += reverted

    gc.collect()  # Release memory after cycle
    return stats


def acquire_lock():
    """Acquire exclusive lock to prevent overlapping cycles."""
    os.makedirs(LOCK_FILE.parent, exist_ok=True)
    lock_fd = open(LOCK_FILE, "w")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_fd.write(f"{os.getpid()}\n{datetime.now().isoformat()}\n")
        lock_fd.flush()
        return lock_fd
    except BlockingIOError:
        lock_fd.close()
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Auto-Dispatch — periodic task dispatcher for Kurultai agents"
    )
    parser.add_argument("--agent", type=str, help="Dispatch for a specific agent only")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be dispatched")
    parser.add_argument("--cleanup", action="store_true", help="Only clean stale tasks")
    parser.add_argument("--no-lock", action="store_true", help="Skip lock acquisition")
    args = parser.parse_args()

    # Validate agent name
    if args.agent and args.agent not in DISPATCH_AGENTS:
        print(f"ERROR: Unknown agent '{args.agent}'. Valid: {DISPATCH_AGENTS}")
        sys.exit(1)

    # Acquire lock
    lock_fd = None
    if not args.no_lock and not args.dry_run:
        lock_fd = acquire_lock()
        if lock_fd is None:
            log("SKIP: Another auto-dispatch cycle is running", "WARN")
            sys.exit(0)

    try:
        cycle_start = time.time()

        if not args.dry_run:
            log("=== Auto-Dispatch Cycle ===")

        stats = run_cycle(
            target_agent=args.agent,
            dry_run=args.dry_run,
            cleanup_only=args.cleanup,
        )

        elapsed = time.time() - cycle_start

        # Summary
        if stats["dispatched"] > 0 or stats["reverted"] > 0 or stats["errors"] > 0:
            log(
                f"CYCLE COMPLETE: dispatched={stats['dispatched']} "
                f"reverted={stats['reverted']} busy={stats['skipped_busy']} "
                f"empty={stats['skipped_empty']} errors={stats['errors']} "
                f"({elapsed:.1f}s)"
            )
        elif not args.dry_run:
            log(f"CYCLE: no dispatches needed ({elapsed:.1f}s)")

        # Log cycle summary
        log_dispatch({
            "ts": datetime.now().isoformat(),
            "action": "cycle_complete",
            "stats": stats,
            "elapsed_secs": round(elapsed, 1),
        })

        # Print machine-readable output for cron capture
        print(f"AUTO_DISPATCH: dispatched={stats['dispatched']} reverted={stats['reverted']}")

    finally:
        if lock_fd:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()


if __name__ == "__main__":
    main()
