#!/usr/bin/env python3
"""
Completion Audit — Continuous verification of recently completed tasks.

Integrates into watchdog-gather.sh heartbeat cycle (runs every 5 minutes).
Verifies tasks that completed since the last audit by checking:
  1. Workspace result file exists with substantive content
  2. No fake completion markers (delegated without execution, wrong model)
  3. Cross-references watcher state for execution records

Unlike queue-audit.py (30-min full audit), this is a lightweight,
continuous check that catches fake completions within minutes.

Usage:
    python3 completion-audit.py [--json]

Output:
    - completion-audit.jsonl (append, machine-readable history)
    - stdout (summary for watchdog integration)
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from json_state import locked_json_read, locked_json_update
from kurultai_paths import AGENTS_DIR, LOGS_DIR

STATE_FILE = LOGS_DIR / "completion-audit-state.json"
AUDIT_LOG = LOGS_DIR / "completion-audit.jsonl"
WATCHER_STATE = LOGS_DIR / "watcher-state.json"

AGENTS = ["kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei"]

# Known test/trivial patterns to skip
SKIP_PATTERNS = [
    "test", "hello world", "fibonacci",
    "build a login", "verify claude code", "write a short"
]


def load_state():
    """Load last audit timestamp."""
    return locked_json_read(str(STATE_FILE), default={"last_audit": 0, "audits_run": 0})


def save_state(state):
    """Persist audit state."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with locked_json_update(str(STATE_FILE)) as data:
        data.clear()
        data.update(state)


def is_test_task(content):
    """Check if task is a test or trivial task."""
    content_lower = content.lower()
    for pattern in SKIP_PATTERNS:
        if pattern in content_lower:
            return True
    # Very short content is likely a test
    text = content.split("---", 3)[-1].strip() if "---" in content else content
    if len(text) < 80:
        return True
    return False


def find_result_file(agent, task_mtime):
    """Find workspace result file created near task completion time."""
    workspace = AGENTS_DIR / agent / "workspace"
    if not workspace.exists():
        return None

    best = None
    best_delta = 1800  # 30 min window
    for f in workspace.glob("task-*.md"):
        try:
            delta = abs(f.stat().st_mtime - task_mtime)
            if delta < best_delta:
                best_delta = delta
                best = str(f)
        except OSError:
            continue
    return best


def check_execution_in_watcher_state(agent, task_name):
    """Check if task has execution record in watcher state."""
    if not WATCHER_STATE.exists():
        return False
    try:
        state = json.loads(WATCHER_STATE.read_text())
        key = f"{agent}/{task_name}"
        return key in state
    except (OSError, json.JSONDecodeError):
        return False


def is_fake_completion(result_path, done_content, agent, task_name):
    """Determine if a task completion is fake (no real execution)."""
    # Check for agent-written closures with real content
    if "## Resolution" in done_content or "**Status:** RESOLVED" in done_content:
        return False

    # Intentionally marked obsolete
    if ".obsolete.done" in task_name:
        return False

    # Failed tasks are legitimate (agent ran but failed)
    if ".failed.done" in task_name or ".orphan-failed.done" in task_name:
        return False

    # Verified/unverified passed through task-verifier.py
    if ".verified.done" in task_name or ".unverified.done" in task_name:
        return False

    # No result file — check watcher state
    if result_path is None:
        # Strip suffixes to get original name
        orig_name = task_name.replace(".completed.done.md", ".md")
        orig_name = orig_name.replace(".done.md", ".md")
        if check_execution_in_watcher_state(agent, orig_name):
            return False
        return True

    # Check result file content
    try:
        result_content = Path(result_path).read_text()
    except OSError:
        return True

    # Real Claude Code execution markers
    if "**Model:** claude-code" in result_content:
        return False

    # Fake completion markers
    if "delegated to" in result_content.lower() and "spawn queue" in result_content.lower():
        return True

    # Legacy fake markers (from old model routing)
    if "**Model:** qwen3.5-plus" in result_content:
        return True

    if "**Latency:** 0ms" in result_content and "**Model:**" in result_content:
        return True

    return False


def audit():
    """Run completion audit. Returns (totals, details)."""
    state = load_state()
    last_audit = state.get("last_audit", 0)
    now = time.time()

    totals = {
        "audited": 0,
        "fake_found": 0,
        "requeued": 0,
        "skipped": 0,
        "verified": 0,
    }
    details = []

    for agent in AGENTS:
        tasks_dir = AGENTS_DIR / agent / "tasks"
        if not tasks_dir.exists():
            continue

        for f in tasks_dir.glob("*.done.md"):
            # Skip files audited in previous cycle
            try:
                mtime = f.stat().st_mtime
                if mtime <= last_audit:
                    continue
            except OSError:
                continue

            # Skip old tasks (only check recent completions)
            age_hours = (now - mtime) / 3600
            if age_hours > 2:
                continue

            task_name = f.name
            content = f.read_text(encoding="utf-8", errors="replace")

            # Skip test tasks
            if is_test_task(content):
                totals["skipped"] += 1
                continue

            totals["audited"] += 1

            # Find result file
            result_path = find_result_file(agent, mtime)

            # Check if fake
            if is_fake_completion(result_path, content, agent, task_name):
                totals["fake_found"] += 1

                # Re-queue by renaming back to pending
                orig_name = task_name.replace(".completed.done.md", ".md")
                orig_name = orig_name.replace(".done.md", ".md")

                # Handle various suffix patterns
                for suffix in [".verified.done.md", ".unverified.done.md",
                               ".failed.done.md", ".stale.done.md"]:
                    if task_name.endswith(suffix):
                        orig_name = task_name[:-len(suffix)] + ".md"
                        break

                dest = tasks_dir / orig_name
                if not dest.exists():
                    try:
                        f.rename(dest)
                        # Touch to update mtime
                        dest.touch()
                        totals["requeued"] += 1

                        # Clear from watcher state
                        try:
                            ws = json.loads(WATCHER_STATE.read_text())
                            key = f"{agent}/{orig_name}"
                            if key in ws:
                                del ws[key]
                                WATCHER_STATE.write_text(json.dumps(ws, indent=2))
                        except (OSError, json.JSONDecodeError):
                            pass

                        details.append({
                            "agent": agent,
                            "task": task_name,
                            "action": "requeued",
                            "reason": "fake_completion"
                        })
                    except OSError:
                        details.append({
                            "agent": agent,
                            "task": task_name,
                            "action": "requeue_failed"
                        })
                else:
                    details.append({
                        "agent": agent,
                        "task": task_name,
                        "action": "skipped",
                        "reason": "original_exists"
                    })
            else:
                totals["verified"] += 1
                details.append({
                    "agent": agent,
                    "task": task_name,
                    "action": "verified",
                    "has_result": result_path is not None
                })

    # Update state
    state["last_audit"] = now
    state["audits_run"] = state.get("audits_run", 0) + 1
    state["last_totals"] = totals
    state["last_ts"] = datetime.now().isoformat()
    save_state(state)

    # Append to audit log
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(AUDIT_LOG, "a") as logf:
        logf.write(json.dumps({
            "ts": datetime.now().isoformat(),
            "totals": totals,
            "details": details[:10]  # Limit details in log
        }) + "\n")

    return totals, details


def main():
    totals, details = audit()

    if "--json" in sys.argv:
        print(json.dumps(totals))
    else:
        ts = datetime.now().isoformat(timespec="seconds")
        print(f"[{ts}] Completion Audit")
        print(f"  Audited: {totals['audited']}")
        print(f"  Verified: {totals['verified']}")
        print(f"  Fake: {totals['fake_found']}")
        print(f"  Re-queued: {totals['requeued']}")
        print(f"  Skipped: {totals['skipped']}")

        for d in details:
            if d["action"] == "requeued":
                print(f"  [REQUEUED] {d['agent']}/{d['task']} ({d['reason']})")
            elif d["action"] == "verified":
                icon = "+" if d.get("has_result") else "?"
                print(f"  [{icon}] {d['agent']}/{d['task']}")


if __name__ == "__main__":
    main()
