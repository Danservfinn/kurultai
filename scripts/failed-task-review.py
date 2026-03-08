#!/usr/bin/env python3
"""
failed-task-review.py — Hourly failed task scanner with failure analysis.

Scans all agents for .failed.done.md tasks, classifies failure reasons,
tracks failure patterns, and sends a summary to kublai via Signal.
Supports restarting tasks with refined instructions.

Usage:
    python3 failed-task-review.py                  # scan + report via Signal
    python3 failed-task-review.py --dry-run        # scan + print (no Signal)
    python3 failed-task-review.py --restart AGENT TASK_FILE [--refine "new instructions"]
    python3 failed-task-review.py --restart-all    # restart all recent failed tasks
    python3 failed-task-review.py --patterns       # show failure pattern stats
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kurultai_paths import AGENTS_DIR, DISPATCH_AGENTS, LOGS_DIR
from json_state import locked_json_update

# ============================================================
# Configuration
# ============================================================
FAILURE_PATTERNS_FILE = LOGS_DIR / "failure-patterns.jsonl"
REVIEW_STATE_FILE = LOGS_DIR / "failed-task-review-state.json"
SEND_SIGNAL_SCRIPT = Path.home() / ".claude" / "skills" / "agent-collaboration" / "scripts" / "send_signal.sh"
WATCHER_STATE = LOGS_DIR / "task-watcher-state.json"

# Only look at failures from the last 24 hours
MAX_AGE_HOURS = 24

# Failure categories with regex patterns matched against error text
FAILURE_CATEGORIES = {
    "auth_error": {
        "patterns": [
            r"BLOCKED non-Anthropic BASE_URL",
            r"authentication.*fail",
            r"invalid.*api.*key",
            r"unauthorized",
            r"403\s+forbidden",
        ],
        "label": "Auth/Credential Error",
        "suggestion": "Check agent settings.json for correct API credentials",
    },
    "rate_limit": {
        "patterns": [
            r"rate.?limit",
            r"429\s",
            r"too many requests",
            r"quota.*exceed",
        ],
        "label": "Rate Limit",
        "suggestion": "Wait and retry, or reduce concurrent tasks",
    },
    "model_error": {
        "patterns": [
            r"model.*not.*found",
            r"MODEL_MISMATCH",
            r"invalid.*model",
            r"model.*unavailable",
        ],
        "label": "Model Error",
        "suggestion": "Verify model ID in agent config",
    },
    "claude_code_crash": {
        "patterns": [
            r"claude-code failed",
            r"claude-agent.*failed",
        ],
        "label": "Claude Code Crash",
        "suggestion": "Check API availability; may be transient",
    },
    "timeout": {
        "patterns": [
            r"timed?\s*out(?!\s*:\s*\d)",
            r"execution.*exceed",
            r"killed.*signal.*9",
            r"exceeded.*timeout",
        ],
        "label": "Timeout",
        "suggestion": "Increase timeout or break task into smaller subtasks",
    },
    "dependency_missing": {
        "patterns": [
            r"module.*not found",
            r"import.*error",
            r"command not found",
            r"no such file",
        ],
        "label": "Missing Dependency",
        "suggestion": "Install missing dependency or fix path",
    },
    "context_overflow": {
        "patterns": [
            r"context.*length.*exceed",
            r"token.*limit",
            r"too.*long",
        ],
        "label": "Context Overflow",
        "suggestion": "Simplify task or reduce input size",
    },
}


# ============================================================
# Failure Analysis
# ============================================================
def classify_failure(error_text):
    """Classify a failure into a category based on error text patterns."""
    error_lower = error_text.lower()
    for category, info in FAILURE_CATEGORIES.items():
        for pattern in info["patterns"]:
            if re.search(pattern, error_lower):
                return category, info["label"], info["suggestion"]
    return "unknown", "Unknown Error", "Review task file manually for details"


def extract_failures_from_task(content):
    """Extract failure sections from a task markdown file.

    Returns list of dicts with time, duration, error text, category.
    """
    failures = []
    # Match failure sections: ## Failure N ...
    sections = re.split(r'## Failure \d+', content)
    for section in sections[1:]:  # skip pre-failure content
        failure = {}

        # Extract time
        m = re.search(r'\*\*Time:\*\*\s*(.+)', section)
        if m:
            failure["time"] = m.group(1).strip()

        # Extract duration
        m = re.search(r'\*\*Duration:\*\*\s*(.+)', section)
        if m:
            failure["duration"] = m.group(1).strip()

        # Extract error text (everything after **Error:**)
        m = re.search(r'\*\*Error:\*\*\s*(.*?)(?=\n## |\n- \*\*Retry|\Z)', section, re.DOTALL)
        if m:
            failure["error"] = m.group(1).strip()
        else:
            failure["error"] = section.strip()[:500]

        # Classify
        category, label, suggestion = classify_failure(failure.get("error", ""))
        failure["category"] = category
        failure["category_label"] = label
        failure["suggestion"] = suggestion

        failures.append(failure)

    return failures


def _safe_parse_int(value, default=0):
    """Safely parse an integer from potentially JSON-escaped strings.

    Handles corrupted metadata like '"\\"\\\\\\"0\\\\\\"\\""' by stripping
    excessive JSON escaping and falling back to default if parsing fails.
    """
    if isinstance(value, int):
        return value
    if not value:
        return default

    # Remove JSON string escaping layers
    cleaned = value.strip().strip('"')
    # Handle nested escaping: "\"0\"" -> "0" -> 0
    while cleaned.startswith('"') or cleaned.startswith('\\'):
        cleaned = cleaned.strip('"').strip('\\').strip('"')

    try:
        return int(cleaned)
    except (ValueError, TypeError):
        # Log warning for debugging but don't crash
        import warnings
        warnings.warn(f"Failed to parse int from: {value!r}, using default: {default}")
        return default


def extract_task_metadata(content):
    """Extract frontmatter metadata from task markdown."""
    meta = {}
    fm_match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
    if fm_match:
        for line in fm_match.group(1).split('\n'):
            if ':' in line:
                key, val = line.split(':', 1)
                meta[key.strip()] = val.strip()

    # Extract title
    title_match = re.search(r'^# Task:\s*(.+)$', content, re.MULTILINE)
    if title_match:
        meta['title'] = title_match.group(1).strip()
    else:
        title_match = re.search(r'^# (.+)$', content, re.MULTILINE)
        if title_match:
            meta['title'] = title_match.group(1).strip()

    # Extract original task body (between --- and first ## Failure)
    body_match = re.search(r'^---\n.*?\n---\n\n(.*?)(?=\n## Failure|\Z)', content, re.DOTALL)
    if body_match:
        meta['body'] = body_match.group(1).strip()

    return meta


# ============================================================
# Scanning
# ============================================================
def scan_failed_tasks(max_age_hours=MAX_AGE_HOURS):
    """Scan all agents for recently failed tasks.

    Returns list of dicts: {agent, path, filename, meta, failures, age_hours}.
    """
    cutoff = time.time() - (max_age_hours * 3600)
    results = []

    for agent in DISPATCH_AGENTS:
        tasks_dir = AGENTS_DIR / agent / "tasks"
        if not tasks_dir.exists():
            continue

        for f in tasks_dir.iterdir():
            if not f.name.endswith(".failed.done.md"):
                continue
            if not f.is_file():
                continue

            try:
                mtime = f.stat().st_mtime
            except OSError:
                continue

            if mtime < cutoff:
                continue

            try:
                content = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            meta = extract_task_metadata(content)
            failures = extract_failures_from_task(content)
            age_hours = (time.time() - mtime) / 3600

            results.append({
                "agent": agent,
                "path": str(f),
                "filename": f.name,
                "meta": meta,
                "failures": failures,
                "age_hours": age_hours,
                "retry_count": _safe_parse_int(meta.get("retry_count", 0)),
            })

    # Sort by most recent first
    results.sort(key=lambda x: x["age_hours"])
    return results


# ============================================================
# Pattern Tracking
# ============================================================
def record_failure_pattern(task_info):
    """Append failure pattern to JSONL for historical tracking."""
    os.makedirs(FAILURE_PATTERNS_FILE.parent, exist_ok=True)

    for failure in task_info["failures"]:
        record = {
            "ts": datetime.now().isoformat(),
            "agent": task_info["agent"],
            "task_id": task_info["meta"].get("task_id", "unknown"),
            "title": task_info["meta"].get("title", "")[:100],
            "category": failure.get("category", "unknown"),
            "category_label": failure.get("category_label", ""),
            "duration": failure.get("duration", ""),
            "retry_count": task_info["retry_count"],
            "source": task_info["meta"].get("source", ""),
        }
        try:
            with open(FAILURE_PATTERNS_FILE, "a") as f:
                f.write(json.dumps(record) + "\n")
        except OSError:
            pass


def get_failure_pattern_stats(hours=168):
    """Analyze failure patterns from the last N hours (default 7 days)."""
    cutoff = datetime.now().timestamp() - (hours * 3600)
    stats = {
        "by_category": Counter(),
        "by_agent": Counter(),
        "by_source": Counter(),
        "total": 0,
        "repeat_tasks": Counter(),  # tasks that failed multiple times
    }

    if not FAILURE_PATTERNS_FILE.exists():
        return stats

    try:
        with open(FAILURE_PATTERNS_FILE) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Filter by time
                try:
                    ts = datetime.fromisoformat(record["ts"]).timestamp()
                    if ts < cutoff:
                        continue
                except (KeyError, ValueError):
                    continue

                stats["total"] += 1
                stats["by_category"][record.get("category", "unknown")] += 1
                stats["by_agent"][record.get("agent", "unknown")] += 1
                stats["by_source"][record.get("source", "unknown")] += 1
                stats["repeat_tasks"][record.get("task_id", "")] += 1
    except OSError:
        pass

    return stats


# ============================================================
# Restart / Requeue
# ============================================================
def restart_task(agent, task_path, refined_instructions=None):
    """Restart a failed task, optionally with refined instructions.

    1. Read the original task content
    2. Strip failure sections
    3. Optionally prepend refined instructions
    4. Rename back to pending
    """
    task_path = Path(task_path)
    if not task_path.exists():
        return False, f"File not found: {task_path}"

    content = task_path.read_text(encoding="utf-8", errors="replace")
    meta = extract_task_metadata(content)

    # Strip failure sections and redistribution comments
    cleaned = re.sub(r'\n## Failure \d+.*', '', content, flags=re.DOTALL)
    cleaned = re.sub(r'\n<!-- Task redistributed.*?-->\n?', '', cleaned)
    cleaned = cleaned.rstrip() + "\n"

    # Add refined instructions if provided
    if refined_instructions:
        # Insert after the task body, before any other content
        cleaned = cleaned.rstrip() + f"\n\n## Refined Instructions (retry)\n\n{refined_instructions}\n"

    # Bump retry count in frontmatter
    old_retry = int(meta.get("retry_count", 0))
    if f"retry_count: {old_retry}" in cleaned:
        cleaned = cleaned.replace(
            f"retry_count: {old_retry}",
            f"retry_count: {old_retry + 2}"  # +2 because original already used 2 retries
        )

    # Determine the original filename (strip .failed.done suffix)
    original_name = task_path.name
    for suffix in [".failed.done.md", ".retry-1.retry-2.failed.done.md"]:
        if original_name.endswith(suffix):
            original_name = original_name[:-len(suffix)] + ".md"
            break
    # Handle other retry patterns
    original_name = re.sub(r'\.retry-\d+', '', original_name)
    if original_name.endswith(".failed.done.md"):
        original_name = original_name[:-len(".failed.done.md")] + ".md"

    dest = task_path.parent / original_name
    if dest.exists():
        return False, f"Pending task already exists: {dest.name}"

    # Write cleaned content and rename
    try:
        task_path.write_text(cleaned, encoding="utf-8")
        task_path.rename(dest)
        os.utime(str(dest), None)  # touch to trigger watcher
    except OSError as e:
        return False, f"Failed to requeue: {e}"

    # Clear from watcher state
    key = f"{agent}/{original_name}"
    try:
        with locked_json_update(str(WATCHER_STATE)) as state:
            state.pop(key, None)
    except Exception:
        pass

    return True, f"Requeued as {original_name}"


# ============================================================
# Report Generation
# ============================================================
def generate_report(failed_tasks, include_suggestions=True):
    """Generate a Signal-ready text report of failed tasks."""
    if not failed_tasks:
        return None  # No report needed

    lines = []
    lines.append(f"FAILED TASK REVIEW ({len(failed_tasks)} tasks, last {MAX_AGE_HOURS}h)")
    lines.append("")

    # Group by failure category
    by_category = defaultdict(list)
    for task in failed_tasks:
        categories = set()
        for f in task["failures"]:
            categories.add(f.get("category_label", "Unknown"))
        for cat in categories:
            by_category[cat].append(task)

    for category, tasks in sorted(by_category.items(), key=lambda x: -len(x[1])):
        # Find the suggestion for this specific category
        cat_suggestion = ""
        for cat_key, cat_info in FAILURE_CATEGORIES.items():
            if cat_info["label"] == category:
                cat_suggestion = cat_info["suggestion"]
                break

        lines.append(f"[{category}] ({len(tasks)} tasks)")
        if include_suggestions and cat_suggestion:
            lines.append(f"  Suggestion: {cat_suggestion}")
        for task in tasks[:5]:  # limit per category
            title = task["meta"].get("title", task["filename"])[:60]
            agent = task["agent"]
            age = task["age_hours"]
            retries = task["retry_count"]
            lines.append(f"  {agent}: {title}")
            lines.append(f"    Age: {age:.1f}h | Retries: {retries}")
        if len(tasks) > 5:
            lines.append(f"  ... and {len(tasks) - 5} more")
        lines.append("")

    # Summary stats
    agents_affected = set(t["agent"] for t in failed_tasks)
    lines.append(f"Agents: {', '.join(sorted(agents_affected))}")

    # Restart instructions
    lines.append("")
    lines.append("To restart: tell kublai 'restart failed task [agent] [filename]'")
    lines.append("Or: python3 failed-task-review.py --restart AGENT FILE [--refine 'new instructions']")

    return "\n".join(lines)


def send_signal_message(message):
    """Send report to kublai via Signal DM."""
    if not SEND_SIGNAL_SCRIPT.exists():
        print(f"Signal script not found: {SEND_SIGNAL_SCRIPT}")
        return False

    try:
        result = subprocess.run(
            [str(SEND_SIGNAL_SCRIPT), message],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            print(f"Signal: sent ({len(message)} chars)")
            return True
        else:
            print(f"Signal send failed: {result.stderr[:200]}")
            return False
    except Exception as e:
        print(f"Signal send error: {e}")
        return False


def update_review_state(failed_tasks):
    """Track which tasks we've already reported to avoid duplicate alerts."""
    try:
        with locked_json_update(str(REVIEW_STATE_FILE), default={}) as state:
            state["last_run"] = datetime.now().isoformat()
            state["last_count"] = len(failed_tasks)
            state["reported_tasks"] = [
                {"agent": t["agent"], "filename": t["filename"], "ts": datetime.now().isoformat()}
                for t in failed_tasks[:50]
            ]
    except Exception:
        pass


# ============================================================
# Main
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="Failed Task Review — scan, analyze, restart")
    parser.add_argument("--dry-run", action="store_true", help="Print report without sending Signal")
    parser.add_argument("--restart", nargs=2, metavar=("AGENT", "TASK_FILE"),
                        help="Restart a specific failed task")
    parser.add_argument("--refine", type=str, help="Refined instructions for restarted task")
    parser.add_argument("--restart-all", action="store_true",
                        help="Restart all recent failed tasks (no refinement)")
    parser.add_argument("--patterns", action="store_true", help="Show failure pattern stats")
    parser.add_argument("--max-age", type=int, default=MAX_AGE_HOURS,
                        help="Max age in hours to scan (default: 24)")
    args = parser.parse_args()

    # --patterns: show historical failure stats
    if args.patterns:
        stats = get_failure_pattern_stats()
        print(f"\nFailure Pattern Stats (last 7 days)")
        print(f"Total failures: {stats['total']}")
        print(f"\nBy Category:")
        for cat, count in stats["by_category"].most_common():
            label = FAILURE_CATEGORIES.get(cat, {}).get("label", cat)
            print(f"  {label}: {count}")
        print(f"\nBy Agent:")
        for agent, count in stats["by_agent"].most_common():
            print(f"  {agent}: {count}")
        print(f"\nRepeat offenders (task_id with >2 failures):")
        for task_id, count in stats["repeat_tasks"].most_common(10):
            if count > 2 and task_id:
                print(f"  {task_id}: {count} failures")
        return

    # --restart: restart a specific task
    if args.restart:
        agent, task_file = args.restart
        # Resolve path
        if not os.path.isabs(task_file):
            task_path = AGENTS_DIR / agent / "tasks" / task_file
        else:
            task_path = Path(task_file)

        ok, msg = restart_task(agent, task_path, refined_instructions=args.refine)
        if ok:
            print(f"OK: {msg}")
        else:
            print(f"FAIL: {msg}")
            sys.exit(1)
        return

    # Scan for failed tasks
    failed_tasks = scan_failed_tasks(max_age_hours=args.max_age)

    # Record patterns for all found failures
    for task in failed_tasks:
        record_failure_pattern(task)

    # --restart-all: restart everything
    if args.restart_all:
        restarted = 0
        for task in failed_tasks:
            ok, msg = restart_task(task["agent"], task["path"])
            status = "OK" if ok else "SKIP"
            print(f"  {status}: {task['agent']}/{task['filename'][:50]} — {msg}")
            if ok:
                restarted += 1
        print(f"\nRestarted: {restarted}/{len(failed_tasks)}")
        return

    # Generate and send report
    report = generate_report(failed_tasks)

    if not report:
        ts = datetime.now().strftime("%H:%M")
        print(f"[{ts}] No failed tasks in last {args.max_age}h")
        update_review_state([])
        return

    if args.dry_run:
        print(report)
    else:
        # Only send if there are new failures since last report
        send_signal_message(report)
        update_review_state(failed_tasks)

    # Print summary to stdout for cron logging
    categories = Counter()
    for task in failed_tasks:
        for f in task["failures"]:
            categories[f.get("category", "unknown")] += 1
    cat_summary = ", ".join(f"{k}={v}" for k, v in categories.most_common(5))
    print(f"FAILED_TASK_REVIEW: count={len(failed_tasks)} categories=[{cat_summary}]")


if __name__ == "__main__":
    main()
