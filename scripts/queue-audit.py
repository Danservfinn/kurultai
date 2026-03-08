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
from kurultai_paths import AGENTS_DIR as _AGENTS_DIR, WATCHER_STATE as _WATCHER_STATE, LOGS_DIR

AGENTS_DIR = str(_AGENTS_DIR)
WATCHER_STATE = str(_WATCHER_STATE)
AUDIT_LOG = str(LOGS_DIR / "queue-audit.log")
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


DONE_SUFFIXES = [".completed.done.md", ".in_progress.done.md", ".failed.done.md",
                 ".stale-cleared.done.md", ".orphan-failed.done.md", ".stale.done.md",
                 ".obsolete.done.md", ".resolved.done.md"]


def has_double_suffix(fname):
    """Detect state corruption: files with multiple done-state suffixes."""
    # Check for literal .done.md appearing multiple times
    if fname.count(".done.md") >= 2:
        return True
    # Check for done-state suffixes applied multiple times
    # e.g. .failed.done.failed.done.md
    for suf in DONE_SUFFIXES:
        if fname.endswith(suf):
            base = fname[:-len(suf)]
            # If the base itself ends with a done suffix, it's corrupted
            for suf2 in DONE_SUFFIXES:
                if base.endswith(suf2) or base.endswith(suf2[:-3]):
                    # suf2[:-3] strips trailing .md — catches .failed.done.failed.done.md
                    return True
            break
    return False


def fix_double_suffix(path):
    """Fix a double-suffixed file by collapsing to a single .done.md suffix."""
    fname = os.path.basename(path)
    dirn = os.path.dirname(path)
    # Strip the outermost done suffix, then check what's left
    for suf in DONE_SUFFIXES:
        if fname.endswith(suf):
            base = fname[:-len(suf)]
            # Strip any remaining done-like suffixes from the base
            # e.g. "foo.failed.done" from "foo.failed.done.failed.done.md"
            changed = True
            while changed:
                changed = False
                for suf2 in DONE_SUFFIXES:
                    bare = suf2[:-3]  # ".failed.done" from ".failed.done.md"
                    if base.endswith(bare):
                        base = base[:-len(bare)]
                        changed = True
                        break
                    if base.endswith(suf2):
                        base = base[:-len(suf2)]
                        changed = True
                        break
            fixed = base + suf
            dest = os.path.join(dirn, fixed)
            if dest == path:
                return fixed, "already_correct"
            if os.path.exists(dest):
                os.remove(path)
                return fixed, "removed_duplicate"
            os.rename(path, dest)
            return fixed, "renamed"
    return fname, "no_fix"


def audit_log(agent, fname, action, reason=""):
    """Append to persistent audit log for debugging fake detection patterns."""
    try:
        with open(AUDIT_LOG, "a") as f:
            ts = datetime.now().isoformat(timespec="seconds")
            f.write(f"[{ts}] {agent}/{fname} {action}")
            if reason:
                f.write(f" ({reason})")
            f.write("\n")
    except OSError:
        pass


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
            # Failed tasks are legitimate execution outcomes, not fake completions.
            # The agent ran but failed (timeout, session lock, model error, etc).
            if ".failed.done" in basename or ".orphan-failed.done" in basename:
                return False
            # Verified/unverified tasks have passed through task-verifier.py - legitimate states
            if ".verified.done" in basename or ".unverified.done" in basename:
                return False
        except OSError:
            pass
    if result_path is None:
        # Cross-check watcher state: if the task has an execution record, it ran
        if done_path:
            basename = os.path.basename(done_path)
            orig = original_name(basename)
            if orig:
                agent = os.path.basename(os.path.dirname(os.path.dirname(done_path)))
                key = f"{agent}/{orig}"
                try:
                    with open(WATCHER_STATE) as f:
                        state = json.load(f)
                    if key in state:
                        return False  # Task was executed per watcher state
                except (OSError, json.JSONDecodeError):
                    pass
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
    for suf in [".completed.done.md", ".in_progress.done.md", ".failed.done.md",
                ".verified.done.md", ".unverified.done.md"]:
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
    totals = {"audited": 0, "fake_found": 0, "requeued": 0, "skipped": 0,
              "double_suffix_fixed": 0}
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

            # Fix double-suffix corruption before auditing
            if has_double_suffix(fname):
                if not dry_run:
                    fixed_name, action = fix_double_suffix(path)
                    audit_log(agent, fname, f"double_suffix_{action}",
                              f"fixed to {fixed_name}")
                totals["double_suffix_fixed"] += 1
                totals["skipped"] += 1
                details.append({"agent": agent, "title": fname[:60],
                                "action": "double_suffix_fixed"})
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

            audit_log(agent, fname, "fake_detected", f"result={result}")

            if requeue(agent, path, dry_run=dry_run):
                totals["requeued"] += 1
                audit_log(agent, fname, "requeued")
                details.append({"agent": agent, "title": title, "action": "requeued"})
            else:
                audit_log(agent, fname, "fake_not_requeued",
                          "original_name returned None or dest exists")
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
        if totals.get("double_suffix_fixed", 0) > 0:
            print(f"  Double-suffix fixed: {totals['double_suffix_fixed']}")
        for d in details:
            tag = "REQUEUED" if d["action"] == "requeued" else "SKIPPED"
            print(f"  [{d['agent']}] {tag}: {d['title']}")


if __name__ == "__main__":
    main()
