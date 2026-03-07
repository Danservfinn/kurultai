#!/usr/bin/env python3
"""
Stall Detector — Time-to-First-Action metric for Kurultai tasks.

Scans all agent task queues for active tasks (pending/executing) and checks
whether the agent has produced any workspace artifact since the task was created.

If a task has been active for > STALL_THRESHOLD_MINS with no workspace activity,
it emits a STALL_WARNING line.

Called from watchdog-gather.sh on every tick (5 minutes).

Output format (stdout, one line per stall):
    STALL_WARNING: <agent> idle <minutes>m on "<task_title>" (file: <task_filename>)

Exit codes:
    0 = no stalls detected
    1 = one or more stalls detected
"""

import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from kurultai_paths import AGENTS_DIR
STALL_THRESHOLD_SECS = 3600  # 60 minutes
AGENTS = ["temujin", "mongke", "chagatai", "jochi", "ogedei", "kublai"]

# Directories/files in workspace to ignore (not real task output)
WORKSPACE_IGNORE = {"__pycache__", ".DS_Store", ".gitkeep"}


def get_active_tasks(agent):
    """Return list of (task_path, creation_epoch) for active tasks."""
    tasks_dir = AGENTS_DIR / agent / "tasks"
    if not tasks_dir.exists():
        return []

    active = []
    for f in tasks_dir.iterdir():
        name = f.name
        # Active = not done, not archived
        if ".done" in name or name.startswith("."):
            continue
        if not name.endswith(".md"):
            continue
        # Skip archived directories
        if f.is_dir():
            continue
        try:
            ctime = f.stat().st_birthtime  # macOS birth time
        except AttributeError:
            ctime = f.stat().st_mtime  # fallback for Linux
        active.append((f, ctime))

    return active


def extract_title(task_path):
    """Extract task title from frontmatter."""
    try:
        content = task_path.read_text(encoding="utf-8", errors="replace")[:500]
        match = re.search(r'^#\s+(?:Task:\s*)?(.+)', content, re.MULTILINE)
        if match:
            return match.group(1).strip()
    except Exception:
        pass
    return task_path.stem


def latest_workspace_mtime(agent, since_epoch):
    """Return the earliest workspace file mtime after since_epoch.

    Returns the mtime of the first artifact created after the task,
    or None if no workspace activity since then.
    """
    workspace = AGENTS_DIR / agent / "workspace"
    if not workspace.exists():
        return None

    first_action = None
    for f in workspace.iterdir():
        if f.name in WORKSPACE_IGNORE or f.name.startswith("."):
            continue
        try:
            mtime = f.stat().st_mtime
        except OSError:
            continue
        if mtime > since_epoch:
            if first_action is None or mtime < first_action:
                first_action = mtime

    return first_action


def detect_stalls():
    """Scan all agents for stalled tasks. Returns list of warning strings."""
    now = time.time()
    warnings = []

    for agent in AGENTS:
        active = get_active_tasks(agent)
        if not active:
            continue

        for task_path, task_created in active:
            age_secs = now - task_created
            if age_secs < STALL_THRESHOLD_SECS:
                continue  # Too young to be stalled

            # Check if agent has produced any workspace output since task creation
            first_action = latest_workspace_mtime(agent, task_created)

            if first_action is None:
                # No workspace activity at all since task was created
                age_mins = int(age_secs / 60)
                title = extract_title(task_path)
                warnings.append(
                    f"STALL_WARNING: {agent} idle {age_mins}m on "
                    f"\"{title}\" (file: {task_path.name})"
                )

    return warnings


def main():
    warnings = detect_stalls()
    for w in warnings:
        print(w)
    sys.exit(1 if warnings else 0)


if __name__ == "__main__":
    main()
