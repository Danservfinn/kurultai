#!/usr/bin/env python3
"""
Agent Rules Evaluator — Evaluates and executes agent-specific behavioral rules.

This script loads rules.json from an agent directory and evaluates enabled rules.
When rule conditions are met, it executes the THEN clause.

Primary implementation: C002 "Documentation Self-Tasking" for chagatai

Usage:
    python3 evaluate_agent_rules.py              # dry-run (print what would happen)
    python3 evaluate_agent_rules.py --exec      # actually execute rules
    python3 evaluate_agent_rules.py --agent chagatai  # specific agent
    python3 evaluate_agent_rules.py --rule C002  # specific rule only

Architecture:
    - Loads {agent}/rules.json
    - Evaluates enabled rules in priority order
    - Executes THEN actions when WHEN conditions are true
    - Cooldown mechanism prevents over-generation
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add scripts directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kurultai_paths import AGENTS_DIR

# Default configuration
DEFAULT_AGENT = "chagatai"
IDLE_THRESHOLD_HOURS = 2  # C002: idle for >2 hours
STALE_DOCS_DAYS = 7  # C002: docs not modified in >7 days
COOLDOWN_MINUTES = 60  # Don't re-evaluate rules more than once per hour

# Cooldown file to prevent over-evaluation
_COOLDOWN_FILE = Path(__file__).parent.parent / "logs" / "rules-evaluator-cooldown.json"


def load_rules(agent: str) -> dict:
    """Load rules.json from agent directory.

    Returns:
        dict with 'rules' list and metadata, or empty dict if file doesn't exist
    """
    rules_path = AGENTS_DIR / agent / "rules.json"
    if not rules_path.exists():
        return {"rules": [], "metadata": {"total_rules": 0, "active_rules": 0}}

    try:
        with open(rules_path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Warning: Failed to load rules from {rules_path}: {e}")
        return {"rules": [], "metadata": {"total_rules": 0, "active_rules": 0}}


def get_agent_idle_time(agent: str) -> tuple[float, datetime]:
    """Calculate agent idle time based on last task completion.

    Returns:
        (idle_hours, last_completion_time)
    """
    tasks_dir = AGENTS_DIR / agent / "tasks"
    if not tasks_dir.exists():
        return float('inf'), None

    last_completion = None

    # Find most recently completed task
    for task_file in tasks_dir.iterdir():
        if not task_file.suffix == ".md":
            continue

        # Check for completion markers in filename
        if any(marker in task_file.name for marker in [".done", ".completed", ".verified"]):
            mtime = datetime.fromtimestamp(task_file.stat().st_mtime)
            if last_completion is None or mtime > last_completion:
                last_completion = mtime

    if last_completion is None:
        # No completed tasks found - check creation time of oldest task
        oldest = None
        for task_file in tasks_dir.iterdir():
            if task_file.suffix == ".md":
                mtime = datetime.fromtimestamp(task_file.stat().st_mtime)
                if oldest is None or mtime < oldest:
                    oldest = mtime
        if oldest:
            last_completion = oldest
        else:
            # No tasks at all - consider very idle
            return float('inf'), None

    idle_hours = (datetime.now() - last_completion).total_seconds() / 3600
    return idle_hours, last_completion


def get_pending_tasks_count(agent: str) -> int:
    """Count pending (non-completed) tasks for an agent."""
    tasks_dir = AGENTS_DIR / agent / "tasks"
    if not tasks_dir.exists():
        return 0

    pending_count = 0
    for task_file in tasks_dir.iterdir():
        if not task_file.suffix == ".md":
            continue

        # Check for completion markers
        if any(marker in task_file.name for marker in [
            ".done", ".completed", ".failed", ".verified", ".stale", ".obsolete", ".resolved"
        ]):
            continue

        pending_count += 1

    return pending_count


def find_stale_documentation(agent: str, days_threshold: int = STALE_DOCS_DAYS) -> list[dict]:
    """Find stale documentation files in agent's docs/ directory.

    Returns:
        List of dicts with 'path', 'name', 'age_days', 'last_modified'
    """
    docs_dir = AGENTS_DIR / agent / "docs"
    stale_files = []

    if not docs_dir.exists():
        return stale_files

    cutoff = datetime.now() - timedelta(days=days_threshold)

    for doc_file in docs_dir.rglob("*.md"):
        mtime = datetime.fromtimestamp(doc_file.stat().st_mtime)

        if mtime < cutoff:
            age_days = (datetime.now() - mtime).days

            # Extract title from file
            title_hint = doc_file.stem.replace("-", " ").replace("_", " ").title()
            try:
                with open(doc_file, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("#"):
                            title_hint = line.lstrip("# ").strip()[:80]
                            break
            except Exception:
                pass

            stale_files.append({
                "path": str(doc_file.relative_to(docs_dir.parent)),
                "name": title_hint,
                "age_days": age_days,
                "last_modified": mtime.isoformat(),
            })

    # Sort by age (oldest first)
    stale_files.sort(key=lambda x: x["age_days"], reverse=True)
    return stale_files


def evaluate_c002(agent: str, dry_run: bool = True) -> list[dict]:
    """Evaluate C002: Documentation Self-Tasking.

    WHEN conditions:
        - Agent idle for >2 hours
        - No pending tasks exist
        - Documentation gaps exist (stale files in docs/)

    THEN action:
        - Identify stale documentation
        - Create content task for highest-priority gap
        - Mark task as self-generated

    Returns:
        List of task dicts that would be/were created
    """
    results = []

    # Check condition 1: Idle time
    idle_hours, last_completion = get_agent_idle_time(agent)
    if idle_hours <= IDLE_THRESHOLD_HOURS:
        print(f"  [C002] Skip: Agent not idle enough ({idle_hours:.1f}h < {IDLE_THRESHOLD_HOURS}h)")
        return results

    # Check condition 2: No pending tasks
    pending_count = get_pending_tasks_count(agent)
    if pending_count > 0:
        print(f"  [C002] Skip: {pending_count} pending task(s) exist")
        return results

    # Check condition 3: Documentation gaps exist
    stale_docs = find_stale_documentation(agent)
    if not stale_docs:
        print(f"  [C002] Skip: No stale documentation (threshold: {STALE_DOCS_DAYS} days)")
        return results

    # All conditions met - create task for highest-priority (oldest) gap
    highest_priority_doc = stale_docs[0]

    task_title = f"Update stale documentation: '{highest_priority_doc['name']}' ({highest_priority_doc['age_days']} days old)"
    task_body = f"""# Task: Update Stale Documentation

**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')} (C002 behavioral rule execution)
**Agent:** {agent}
**Type:** Documentation
**Priority:** normal

## Assignment

The documentation file `{highest_priority_doc['path']}` has not been updated in {highest_priority_doc['age_days']} days.

## What To Do

1. **Review the current content** - Read the file and assess accuracy
2. **Check for outdated information** - Look for:
   - Deprecated procedures or configurations
   - Outdated system references
   - Missing recent changes or features
3. **Update as needed** - Refresh content with current information
4. **Add new insights** - Document any new findings or patterns since last update

## File Location

`{highest_priority_doc['path']}`

**Last modified:** {highest_priority_doc['last_modified']}

## Self-Generated

This task was self-generated by C002 behavioral rule: "WHEN idle for >2 hours AND no pending tasks exist AND documentation gaps exist, THEN identify stale documentation and create content task."
"""

    results.append({
        "rule_id": "C002",
        "title": task_title,
        "body": task_body,
        "priority": "normal",
        "type": "documentation",
        "doc_file": highest_priority_doc['path'],
        "age_days": highest_priority_doc['age_days'],
    })

    return results


def evaluate_rule(rule: dict, agent: str, dry_run: bool = True) -> list[dict]:
    """Dispatch to specific evaluator based on rule ID.

    Args:
        rule: Rule dict from rules.json
        agent: Agent name
        dry_run: If True, don't actually create tasks

    Returns:
        List of task dicts that would be/were created
    """
    rule_id = rule.get("id", "")
    enabled = rule.get("enabled", False)

    if not enabled:
        return []

    if rule_id == "C002":
        return evaluate_c002(agent, dry_run)

    # Add other rule evaluators here as they are implemented
    # C003, C004, C005 are quality/routing rules - handled elsewhere

    print(f"  [{rule_id}] No evaluator implemented yet")
    return []


def check_cooldown(agent: str) -> bool:
    """Check if evaluation cooldown has expired.

    Returns:
        True if cooldown has expired (ok to evaluate), False otherwise
    """
    if not _COOLDOWN_FILE.exists():
        return True

    try:
        with open(_COOLDOWN_FILE) as f:
            data = json.load(f)

        agent_key = f"last_run_{agent}"
        if agent_key not in data:
            return True

        last_run = datetime.fromisoformat(data[agent_key])
        elapsed = datetime.now() - last_run

        return elapsed.total_seconds() > (COOLDOWN_MINUTES * 60)
    except (json.JSONDecodeError, ValueError, KeyError):
        return True


def update_cooldown(agent: str):
    """Record that we just evaluated rules for this agent."""
    _COOLDOWN_FILE.parent.mkdir(parents=True, exist_ok=True)

    data = {}
    if _COOLDOWN_FILE.exists():
        try:
            with open(_COOLDOWN_FILE) as f:
                data = json.load(f)
        except json.JSONDecodeError:
            pass

    data[f"last_run_{agent}"] = datetime.now().isoformat()

    with open(_COOLDOWN_FILE, "w") as f:
        json.dump(data, f, indent=2)


def create_task_from_rule(task_dict: dict, agent: str) -> str | None:
    """Create a task from rule evaluation results.

    Args:
        task_dict: Task dict from evaluate_rule
        agent: Target agent name

    Returns:
        task_id if created, None if rejected
    """
    # Import here to avoid circular imports in dry-run mode
    from task_intake import create_task

    return create_task(
        title=task_dict["title"],
        body=task_dict["body"],
        priority=task_dict.get("priority", "normal"),
        source=f"{agent}-rules-evaluator",
        agent=agent,
        skill_hint=None,  # Let routing decide
        depth=0,
        skip_duplicate_check=False,
    )


def evaluate_agent_rules(agent: str, dry_run: bool = True, specific_rule: str | None = None) -> dict:
    """Evaluate all enabled rules for an agent.

    Args:
        agent: Agent name (e.g., "chagatai")
        dry_run: If True, print what would happen without executing
        specific_rule: Only evaluate this rule ID (e.g., "C002")

    Returns:
        Summary dict with evaluation results
    """
    print(f"\n{'='*60}")
    print(f"Agent Rules Evaluator: {agent}")
    print(f"{'='*60}")
    print(f"Mode: {'DRY RUN' if dry_run else 'EXECUTE'}")

    # Load rules
    rules_data = load_rules(agent)
    rules = rules_data.get("rules", [])

    if not rules:
        print(f"No rules found for {agent}")
        return {"agent": agent, "rules_evaluated": 0, "tasks_created": 0}

    # Filter by enabled and specific_rule if provided
    rules_to_check = [
        r for r in rules
        if r.get("enabled", False) and (specific_rule is None or r.get("id") == specific_rule)
    ]

    print(f"\nFound {len(rules_to_check)} enabled rule(s) to evaluate")

    # Check cooldown
    if not dry_run and not check_cooldown(agent):
        print(f"\nCooldown active (last run < {COOLDOWN_MINUTES}m ago) - skipping")
        return {"agent": agent, "rules_evaluated": 0, "tasks_created": 0, "status": "cooldown"}

    all_tasks = []
    results_by_rule = {}

    # Evaluate each rule
    for rule in rules_to_check:
        rule_id = rule.get("id", "unknown")
        rule_name = rule.get("name", "")

        print(f"\nEvaluating {rule_id}: {rule_name}")

        tasks = evaluate_rule(rule, agent, dry_run)

        if tasks:
            print(f"  [{rule_id}] Would create {len(tasks)} task(s)")
            results_by_rule[rule_id] = {"would_create": len(tasks)}
        else:
            print(f"  [{rule_id}] No action needed")
            results_by_rule[rule_id] = {"would_create": 0}

        all_tasks.extend(tasks)

    # Summary
    print(f"\n{'='*60}")
    print(f"Summary: {len(all_tasks)} task(s) would be created")

    if dry_run and all_tasks:
        print("\nTasks to be created:")
        for i, task in enumerate(all_tasks, 1):
            print(f"  {i}. [{task.get('rule_id')}] {task['title'][:70]}")

    # Execute if not dry run
    if not dry_run and all_tasks:
        from task_intake import create_task

        created_count = 0
        for task in all_tasks:
            task_id = create_task(
                title=task["title"],
                body=task["body"],
                priority=task.get("priority", "normal"),
                source=f"{agent}-rules-evaluator",
                agent=agent,
                depth=0,
            )
            if task_id:
                print(f"  Created: {task_id} - {task['title'][:60]}")
                created_count += 1
            else:
                print(f"  Rejected: {task['title'][:60]}")

        if created_count > 0:
            update_cooldown(agent)
            print(f"\nCooldown updated for {agent}")

        return {
            "agent": agent,
            "rules_evaluated": len(rules_to_check),
            "tasks_created": created_count,
            "results_by_rule": results_by_rule,
        }

    return {
        "agent": agent,
        "rules_evaluated": len(rules_to_check),
        "tasks_created": 0,
        "results_by_rule": results_by_rule,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate and execute agent-specific behavioral rules",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python evaluate_agent_rules.py                 # Dry-run for chagatai
  python evaluate_agent_rules.py --exec          # Actually execute rules
  python evaluate_agent_rules.py --agent mongke  # Different agent
  python evaluate_agent_rules.py --rule C002     # Specific rule only
        """
    )
    parser.add_argument(
        "--agent", "-a",
        default=DEFAULT_AGENT,
        help=f"Agent to evaluate rules for (default: {DEFAULT_AGENT})"
    )
    parser.add_argument(
        "--exec", "-e",
        action="store_true",
        help="Execute rules (default: dry-run)"
    )
    parser.add_argument(
        "--rule", "-r",
        help="Only evaluate specific rule ID (e.g., C002)"
    )

    args = parser.parse_args()

    result = evaluate_agent_rules(
        agent=args.agent,
        dry_run=not args.exec,
        specific_rule=args.rule
    )

    # Exit code based on whether tasks would be created
    if result.get("tasks_created", 0) > 0:
        return 0
    elif result.get("results_by_rule", {}) and any(v.get("would_create", 0) > 0 for v in result["results_by_rule"].values()):
        return 0  # Dry run showed potential tasks
    return 0


if __name__ == "__main__":
    sys.exit(main())
