#!/usr/bin/env python3
"""
Queue Audit — Detect and re-queue fake task completions.

Scans agent task directories for tasks marked "done" that were never
actually executed by Claude Code. Re-queues valid ones automatically.

Called by tock-gather.sh every 30 minutes, or run standalone.

Usage:
    python3 queue-audit.py [--dry-run] [--json]
"""

import glob
import json
import os
import re
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from json_state import locked_json_update

AGENTS_DIR = "/Users/kublai/.openclaw/agents"
WATCHER_STATE = os.path.join(AGENTS_DIR, "main/logs/task-watcher-state.json")
AGENTS = ["kublai", "mongke", "chagatai", "temujin", "jochi", "ogedei"]
MAX_AGE_DAYS = 7

# Known test/trivial patterns to skip
SKIP_PATTERNS = [
    re.compile(r"(?i)^#\s*task:\s*test\b", re.MULTILINE),
    re.compile(r"(?i)hello\s*world"),
    re.compile(r"(?i)fibonacci"),
    re.compile(r"(?i)^#\s*task:\s*build a login feature$", re.MULTILINE),
    re.compile(r"(?i)^#\s*task:\s*test direct execution", re.MULTILINE),
    re.compile(r"(?i)^#\s*task:\s*verify claude code execution", re.MULTILINE),
    re.compile(r"(?i)^#\s*task:\s*write a short python script", re.MULTILINE),
    re.compile(r"(?i)^#\s*task:\s*generate a python script", re.MULTILINE),
]


def is_test_task(content):
    for pat in SKIP_PATTERNS:
        if pat.search(content):
            return True
    # Very short content is likely a test
    text = re.sub(r"---.*?---", "", content, flags=re.DOTALL).strip()
    if len(text) < 80:
        return True
    return False


def find_result_file(agent, task_mtime):
    """Find workspace result file created near the task completion time."""
    workspace = os.path.join(AGENTS_DIR, agent, "workspace")
    if not os.path.isdir(workspace):
        return None
    best = None
    best_delta = 1800  # 30 min window
    for f in glob.glob(os.path.join(workspace, "task-*.md")):
        try:
            delta = abs(os.path.getmtime(f) - task_mtime)
            if delta < best_delta:
                best_delta = delta
                best = f
        except OSError:
            continue
    return best


def is_fake(result_path, done_path=None):
    """Return True if the result file shows no real Claude Code execution."""
    # Check if the done file itself contains a resolution or is intentionally closed
    if done_path:
        try:
            done_content = open(done_path).read()
            basename = os.path.basename(done_path)
            # Agent-written closures with resolution content
            if "## Resolution" in done_content or "**Status:** RESOLVED" in done_content:
                return False
            # Intentionally marked obsolete (superseded by newer tasks)
            if ".obsolete.done" in basename:
                return False
        except OSError:
            pass
    if result_path is None:
        return True
    try:
        content = open(result_path).read()
    except OSError:
        return True
    if "**Model:** claude-code" in content:
        return False
    if "delegated to" in content.lower() and "spawn queue" in content.lower():
        return True
    if "**Model:** qwen3.5-plus" in content:
        return True
    if "**Model:** fallback" in content:
        return True
    if "**Latency:** 0ms" in content and "**Model:**" in content:
        return True
    return False


def original_name(done_filename):
    """Strip .done suffixes to get original pending filename."""
    name = done_filename
    # Standard suffixes from agent-task-handler
    for suf in [".completed.done.md", ".in_progress.done.md", ".failed.done.md"]:
        if name.endswith(suf):
            return name[:-len(suf)] + ".md"
    # Non-standard suffixes created by LLM agents during cleanup/reflection
    m = re.match(r'^(.+)\.(stale-cleared|orphan-failed|stale)\.done\.md$', name)
    if m:
        return m.group(1) + ".md"
    # .obsolete.done and .resolved.done are intentional closures — not re-queueable
    return None


def requeue(agent, done_path, dry_run=False):
    """Rename done file back to pending and clear watcher state."""
    orig = original_name(os.path.basename(done_path))
    if not orig:
        return False
    dest = os.path.join(os.path.dirname(done_path), orig)
    if os.path.exists(dest):
        return False  # already a pending copy
    if dry_run:
        return True
    try:
        os.rename(done_path, dest)
        # Touch file so mtime > state execution time (watcher detects re-queue)
        os.utime(dest, None)
    except OSError:
        return False
    # Clear from watcher state
    key = f"{agent}/{orig}"
    try:
        with locked_json_update(WATCHER_STATE) as state:
            state.pop(key, None)
    except Exception:
        pass
    return True


def audit():
    now = time.time()
    totals = {"audited": 0, "fake_found": 0, "requeued": 0, "skipped": 0}
    details = []
    dry_run = "--dry-run" in sys.argv

    for agent in AGENTS:
        tasks_dir = os.path.join(AGENTS_DIR, agent, "tasks")
        if not os.path.isdir(tasks_dir):
            continue
        for fname in os.listdir(tasks_dir):
            path = os.path.join(tasks_dir, fname)
            if not os.path.isfile(path) or ".done.md" not in fname:
                continue
            # Skip stale
            try:
                age = (now - os.path.getmtime(path)) / 86400
                if age > MAX_AGE_DAYS:
                    totals["skipped"] += 1
                    continue
            except OSError:
                continue

            totals["audited"] += 1
            try:
                content = open(path).read()
            except OSError:
                continue
            if is_test_task(content):
                totals["skipped"] += 1
                continue

            result = find_result_file(agent, os.path.getmtime(path))
            if not is_fake(result, done_path=path):
                continue

            totals["fake_found"] += 1
            # Extract title
            title = fname[:60]
            for line in content.split("\n"):
                if line.startswith("# Task:") or line.startswith("# TASK:"):
                    title = line.split(":", 1)[1].strip()[:80]
                    break

            if requeue(agent, path, dry_run=dry_run):
                totals["requeued"] += 1
                details.append({"agent": agent, "title": title, "action": "requeued"})
            else:
                details.append({"agent": agent, "title": title, "action": "skipped"})

    return totals, details


def main():
    totals, details = audit()
    if "--json" in sys.argv:
        print(json.dumps(totals))
    else:
        mode = "(DRY RUN)" if "--dry-run" in sys.argv else ""
        print(f"[{datetime.now().isoformat()}] Queue Audit {mode}")
        print(f"  Audited: {totals['audited']}")
        print(f"  Fake: {totals['fake_found']}")
        print(f"  Re-queued: {totals['requeued']}")
        print(f"  Skipped: {totals['skipped']}")
        for d in details:
            tag = "REQUEUED" if d["action"] == "requeued" else "SKIPPED"
            print(f"  [{d['agent']}] {tag}: {d['title']}")


if __name__ == "__main__":
    main()
