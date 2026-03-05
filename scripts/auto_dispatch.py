#!/usr/bin/env python3
"""
auto_dispatch.py — Periodic task dispatcher for Kurultai agents.

Runs every 5 minutes via cron. For each agent:
1. Clean up stale .executing tasks (>15 min old → revert to pending)
2. Skip agents with active .executing tasks (max 1 concurrent per agent)
3. Find highest-priority pending task
4. Dispatch via `openclaw agent --agent X --message <task content>`
5. Log dispatch decisions to JSONL

This is the MISSING piece: tasks were being created in agent queues by
kublai-actions.py, kublai-initiative.py, and task_router.py, but nothing
was reliably picking them up and dispatching them to agents.

Usage:
    python3 auto_dispatch.py              # dispatch all agents
    python3 auto_dispatch.py --agent temujin  # dispatch single agent
    python3 auto_dispatch.py --dry-run    # show what would be dispatched
    python3 auto_dispatch.py --cleanup    # only clean stale tasks, no dispatch
"""

import argparse
import fcntl
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

# ============================================================
# Configuration
# ============================================================
AGENTS_BASE = Path("/Users/kublai/.openclaw/agents")
DISPATCH_AGENTS = ["temujin", "mongke", "chagatai", "jochi", "ogedei"]
DISPATCH_LOG = AGENTS_BASE / "main/logs/auto-dispatch.jsonl"
DISPATCH_STATE = AGENTS_BASE / "main/logs/auto-dispatch-state.json"
LOCK_FILE = AGENTS_BASE / "main/logs/auto-dispatch.lock"

# Stale task threshold: tasks stuck in .executing for >15 min get reverted
STALE_EXECUTING_SECS = 900  # 15 minutes

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
        if ".executing" in f.name and f.is_file():
            executing.append(f)
    return executing


def cleanup_stale_executing(agent):
    """Revert .executing tasks that have been stuck for too long."""
    executing = list_executing_tasks(agent)
    reverted = 0

    for task_file in executing:
        age_secs = time.time() - task_file.stat().st_mtime
        if age_secs > STALE_EXECUTING_SECS:
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
    """Run one dispatch cycle.

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
    dispatched_count = 0

    for agent in agents:
        agent_dir = AGENTS_BASE / agent
        if not agent_dir.exists():
            continue

        # Step 1: Clean up stale executing tasks
        reverted = cleanup_stale_executing(agent)
        stats["reverted"] += reverted

        if cleanup_only:
            continue

        # Step 2: Check if agent is currently busy
        executing = list_executing_tasks(agent)
        if executing:
            log(f"SKIP {agent}: busy with {len(executing)} executing task(s)")
            stats["skipped_busy"] += 1
            continue

        # Step 3: Check for pending tasks
        pending = list_pending_tasks(agent)
        if not pending:
            stats["skipped_empty"] += 1
            continue

        # Step 4: Dispatch the highest-priority task
        if dispatched_count >= MAX_DISPATCHES_PER_CYCLE:
            log(f"SKIP {agent}: hit max dispatches per cycle ({MAX_DISPATCHES_PER_CYCLE})")
            break

        task_file = pending[0]
        success, msg = dispatch_task(agent, task_file, dry_run=dry_run)

        if success:
            stats["dispatched"] += 1
            dispatched_count += 1
        else:
            log(f"FAILED dispatch to {agent}: {msg}", "ERROR")
            stats["errors"] += 1
            log_dispatch({
                "ts": datetime.now().isoformat(),
                "action": "dispatch_failed",
                "agent": agent,
                "task": task_file.name,
                "error": msg,
            })

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
