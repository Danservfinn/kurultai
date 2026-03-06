#!/usr/bin/env python3
"""
agent-self-wake.py -- Rule T7: Wake idle agents to work on blocked items.

Detects agents that have been idle > IDLE_THRESHOLD_MIN with no active Claude
session and no pending tasks, then scans their memory for blocked items,
commitments, or rules. If found, creates a wake task in their queue so
task-watcher.py picks it up within seconds.

Called from watchdog-gather.sh on every 5-minute tick cycle.

Usage:
    python3 agent-self-wake.py             # check all agents, wake if needed
    python3 agent-self-wake.py --dry-run   # show what would happen
    python3 agent-self-wake.py --agent temujin  # check single agent
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from json_state import locked_json_read, locked_json_update

# Configuration
AGENTS_DIR = Path("/Users/kublai/.openclaw/agents")
SCRIPTS_DIR = Path(__file__).parent
WAKE_STATE_FILE = AGENTS_DIR / "main/logs/self-wake-state.json"
WAKE_LOG_FILE = AGENTS_DIR / "main/logs/self-wake.log"
WATCHER_STATE = AGENTS_DIR / "main/logs/task-watcher-state.json"
WATCHDOG_LOG = AGENTS_DIR / "main/logs/watchdog.log"

AGENTS = ["temujin", "mongke", "chagatai", "jochi", "ogedei"]
# Exclude kublai -- lead agent, woken separately by LLM triage
IDLE_THRESHOLD_MIN = 30
COOLDOWN_MIN = 60  # Don't re-wake an agent within this window
MAX_WAKES_PER_CYCLE = 2  # Limit concurrent wakes to avoid resource contention


def log(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] SELF-WAKE {level}: {msg}"
    print(line)
    try:
        WAKE_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(WAKE_LOG_FILE, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def load_wake_state():
    return locked_json_read(str(WAKE_STATE_FILE), default={
        "last_wakes": {},   # agent -> last wake ISO timestamp
        "total_wakes": 0,
        "wakes_today": 0,
        "today": "",
    })


def save_wake_state(state):
    with locked_json_update(str(WAKE_STATE_FILE), default={}) as data:
        data.clear()
        data.update(state)


def agent_has_active_session(agent):
    """Check if agent has a running Claude Code process."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", f"claude.*{agent}"],
            capture_output=True, text=True, timeout=5
        )
        return bool(result.stdout.strip())
    except Exception:
        return False


def agent_has_pending_tasks(agent):
    """Check if agent has pending (unexecuted) task files."""
    tasks_dir = AGENTS_DIR / agent / "tasks"
    if not tasks_dir.exists():
        return False
    for f in tasks_dir.glob("*.md"):
        if not any(x in f.name for x in [".executing", ".completed", ".done"]):
            return True
    return False


def get_last_activity_time(agent):
    """Get the last time this agent completed or started a task.

    Sources: task-watcher state (completion times) and task file mtimes.
    """
    latest = 0

    # Check task-watcher state for last execution
    watcher_state = locked_json_read(str(WATCHER_STATE), default={})
    for key, val in watcher_state.items():
        if key.startswith(f"{agent}/"):
            try:
                exec_time = datetime.fromisoformat(val["executed"]).timestamp()
                latest = max(latest, exec_time)
            except (KeyError, ValueError):
                pass

    # Check task files for recent activity
    tasks_dir = AGENTS_DIR / agent / "tasks"
    if tasks_dir.exists():
        for f in tasks_dir.iterdir():
            try:
                latest = max(latest, f.stat().st_mtime)
            except OSError:
                pass

    # Check workspace for recent outputs
    workspace = AGENTS_DIR / agent / "workspace"
    if workspace.exists():
        for f in workspace.iterdir():
            try:
                latest = max(latest, f.stat().st_mtime)
            except OSError:
                pass

    return latest


def extract_blocked_items(agent):
    """Scan agent memory files for blocked items, commitments, and rules.

    Returns a list of extracted items (strings), or empty list if none found.
    """
    items = []
    memory_dir = AGENTS_DIR / agent / "memory"
    if not memory_dir.exists():
        return items

    # Patterns that indicate actionable blocked work
    patterns = [
        r"(?:blocked|BLOCKED)\s+(?:item|task|work).*?[:]\s*(.+)",
        r"COMMITMENT\s*\n(.+)",
        r"NEW RULE.*?\nWHEN\s+(.+?)(?:\n|$)",
        r"(?:TODO|FIXME|INVESTIGATE)[:]\s*(.+)",
        r"remains?\s+(?:unresolved|blocked|broken|unfixed).*?[:.]?\s*(.+)?",
    ]

    # Read today's memory and context.md
    today = datetime.now().strftime("%Y-%m-%d")
    files_to_check = [
        memory_dir / "context.md",
        memory_dir / f"{today}.md",
    ]
    # Also check yesterday if early in the day
    yesterday = datetime.now().strftime("%Y-%m-%d")  # will be overridden
    if datetime.now().hour < 6:
        from datetime import timedelta
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        files_to_check.append(memory_dir / f"{yesterday}.md")

    for filepath in files_to_check:
        if not filepath.exists():
            continue
        try:
            content = filepath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        # Look for commitment sections (most actionable)
        commitment_match = re.search(
            r"### COMMITMENT\s*\n(.+?)(?:\n###|\n---|\Z)",
            content, re.DOTALL
        )
        if commitment_match:
            text = commitment_match.group(1).strip()
            if text and len(text) > 10:
                items.append(f"COMMITMENT: {text[:300]}")

        # Look for blocked items
        for match in re.finditer(
            r"blocked item[s]?\s*(?:#\d+)?\s*\(([^)]+)\)",
            content, re.IGNORECASE
        ):
            items.append(f"BLOCKED: {match.group(1).strip()}")

        # Look for rules that haven't been verified
        for match in re.finditer(
            r"NEW RULE\s*\((\w+)\)\s*\n(WHEN .+?)(?:\n\n|\n###|\Z)",
            content, re.DOTALL
        ):
            rule_id = match.group(1)
            rule_text = match.group(2).strip()
            items.append(f"RULE {rule_id}: {rule_text[:200]}")

        # Look for explicit commitments with "Fix" or "Investigate"
        for match in re.finditer(
            r"(?:Fix|Investigate|Implement|Build|Create|Debug)\s+.{10,100}",
            content
        ):
            text = match.group(0).strip()
            if text not in [i.split(": ", 1)[-1] for i in items]:
                items.append(f"ACTION: {text}")

    # Deduplicate — check for substring overlap between items
    unique = []
    for item in items:
        text = item.split(": ", 1)[-1].lower()[:80]
        # Skip if this item's content is already covered by an existing item
        is_dup = False
        for existing in unique:
            existing_text = existing.split(": ", 1)[-1].lower()[:80]
            if text in existing_text or existing_text in text:
                is_dup = True
                break
        if not is_dup:
            unique.append(item)

    return unique[:5]  # Cap at 5 items


def create_wake_task(agent, blocked_items):
    """Create a task file in the agent's queue to wake them up."""
    tasks_dir = AGENTS_DIR / agent / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)

    ts = int(time.time())
    filename = f"normal-selfwake-{ts}.md"
    task_path = tasks_dir / filename

    items_text = "\n".join(f"- {item}" for item in blocked_items)

    content = f"""# Task: Self-Wake -- Execute Blocked Items

task_id: selfwake-{agent}-{ts}
source: agent-self-wake (Rule T7)
priority: normal

---

You have been idle for over {IDLE_THRESHOLD_MIN} minutes with unresolved items in your memory.

## Blocked Items Found in Your Memory

{items_text}

## Instructions

1. Read your memory files (`memory/context.md` and today's memory file)
2. Pick the highest-priority blocked item from the list above
3. Execute it: read code, write fixes, run tests, verify results
4. Update your memory with the outcome
5. If you finish early, pick the next item

Do NOT just describe what should be done. Actually do it using your tools.
"""

    task_path.write_text(content)
    log(f"Created wake task: {agent}/{filename} ({len(blocked_items)} items)")
    return str(task_path)


def check_and_wake_agent(agent, wake_state, dry_run=False):
    """Check if an agent should be woken and create a wake task if so.

    Returns True if agent was woken, False otherwise.
    """
    # Check cooldown
    last_wake = wake_state.get("last_wakes", {}).get(agent)
    if last_wake:
        try:
            last_wake_time = datetime.fromisoformat(last_wake).timestamp()
            if time.time() - last_wake_time < COOLDOWN_MIN * 60:
                mins_left = int((COOLDOWN_MIN * 60 - (time.time() - last_wake_time)) / 60)
                log(f"{agent}: cooldown ({mins_left}m remaining)", "SKIP")
                return False
        except (ValueError, TypeError):
            pass

    # Check if agent has an active Claude session
    if agent_has_active_session(agent):
        log(f"{agent}: active session running", "SKIP")
        return False

    # Check if agent already has pending tasks
    if agent_has_pending_tasks(agent):
        log(f"{agent}: has pending tasks", "SKIP")
        return False

    # Check idle time
    last_activity = get_last_activity_time(agent)
    if last_activity > 0:
        idle_min = (time.time() - last_activity) / 60
        if idle_min < IDLE_THRESHOLD_MIN:
            log(f"{agent}: idle only {idle_min:.0f}m (threshold: {IDLE_THRESHOLD_MIN}m)", "SKIP")
            return False
    else:
        idle_min = float("inf")

    # Scan memory for blocked items
    blocked_items = extract_blocked_items(agent)
    if not blocked_items:
        log(f"{agent}: idle {idle_min:.0f}m but no blocked items found", "SKIP")
        return False

    # All conditions met -- wake this agent
    log(f"{agent}: IDLE {idle_min:.0f}m, {len(blocked_items)} blocked items", "WAKE")
    for item in blocked_items:
        log(f"  -> {item[:100]}", "WAKE")

    if dry_run:
        log(f"{agent}: DRY RUN -- would create wake task", "WAKE")
        return False

    create_wake_task(agent, blocked_items)

    # Update state
    wake_state.setdefault("last_wakes", {})[agent] = datetime.now().isoformat()
    wake_state["total_wakes"] = wake_state.get("total_wakes", 0) + 1
    today = datetime.now().strftime("%Y-%m-%d")
    if wake_state.get("today") != today:
        wake_state["today"] = today
        wake_state["wakes_today"] = 0
    wake_state["wakes_today"] = wake_state.get("wakes_today", 0) + 1

    # Log to watchdog.log for visibility
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(WATCHDOG_LOG, "a") as f:
            f.write(f"[{ts}] SELF-WAKE | agent={agent} | idle={idle_min:.0f}m | blocked_items={len(blocked_items)}\n")
    except OSError:
        pass

    return True


def main():
    parser = argparse.ArgumentParser(description="Wake idle agents to work on blocked items (Rule T7)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without creating tasks")
    parser.add_argument("--agent", help="Check single agent only")
    args = parser.parse_args()

    agents = [args.agent] if args.agent else AGENTS
    wake_state = load_wake_state()
    woken = 0

    for agent in agents:
        if agent not in AGENTS and agent != "kublai":
            log(f"Unknown agent: {agent}", "ERROR")
            continue

        if woken >= MAX_WAKES_PER_CYCLE:
            log(f"Max wakes per cycle reached ({MAX_WAKES_PER_CYCLE})", "LIMIT")
            break

        try:
            if check_and_wake_agent(agent, wake_state, dry_run=args.dry_run):
                woken += 1
        except Exception as e:
            log(f"{agent}: error: {e}", "ERROR")

    if not args.dry_run:
        save_wake_state(wake_state)

    if woken > 0:
        log(f"Woke {woken} agent(s) this cycle")
    else:
        log(f"No agents needed waking")

    # Output summary for watchdog-gather.sh
    print(f"SELF_WAKE: woken={woken} checked={len(agents)}")


if __name__ == "__main__":
    main()
