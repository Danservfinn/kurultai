#!/usr/bin/env python3
"""
Task Gate Validator - Check and debug gate status.

This is a CLI tool for querying and debugging completion gate state.
Use it to inspect stuck gates, list pending gates, and view follow-up chains.

Usage:
    python3 task-gate-validator.py --list-pending
    python3 task-gate-validator.py --task high-12345678
    python3 task-gate-validator.py --list-followups high-12345678
    python3 task-gate-validator.py --audit-json high-12345678

Design: ~/.openclaw/agents/mongke/workspace/completion-gate-design-2026-03-08.md
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

# Add scripts directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kurultai_paths import AGENTS_DIR

# Import shared gate utilities (prevents code duplication)
from gate_utils import (
    VALID_AGENTS,
    extract_frontmatter,
    find_task_file,
    extract_task_id
)

# Gate audit log directory
GATE_AUDITS_DIR = Path.home() / ".openclaw" / "agents" / "main" / "logs" / "gate-audits"


def find_pending_gates() -> List[Path]:
    """Find all tasks in pending-gate state."""
    pending_gates = []

    for agent_dir in AGENTS_DIR.iterdir():
        if not agent_dir.is_dir() or agent_dir.name.startswith('.'):
            continue

        if agent_dir.name not in VALID_AGENTS:
            continue

        tasks_dir = agent_dir / "tasks"
        if not tasks_dir.exists():
            continue

        for task_file in tasks_dir.glob("*.pending-gate.md"):
            pending_gates.append(task_file)

    return pending_gates


def get_followup_tasks(parent_task_id: str) -> List[Dict[str, Any]]:
    """
    Get all follow-up tasks for a parent task.

    Returns list of dicts with task_id, file_path, and status.
    """
    followups = []

    for agent_dir in AGENTS_DIR.iterdir():
        if not agent_dir.is_dir() or agent_dir.name.startswith('.'):
            continue

        if agent_dir.name not in VALID_AGENTS:
            continue

        tasks_dir = agent_dir / "tasks"
        if not tasks_dir.exists():
            continue

        for task_file in tasks_dir.glob("*.md"):
            try:
                with open(task_file, 'r') as f:
                    content = f.read(2000)

                match = re.search(rf'parent_task:\s*{re.escape(parent_task_id)}', content)
                if match:
                    task_match = re.search(r'task_id:\s*(\S+)', content)
                    if task_match:
                        # Determine status
                        status = "pending"
                        if '.done.' in task_file.name:
                            status = "completed"
                        elif '.executing.' in task_file.name:
                            status = "executing"
                        elif '.blocked' in task_file.name:
                            status = "blocked"
                        elif '.pending-gate.' in task_file.name:
                            status = "pending_gate"

                        followups.append({
                            "task_id": task_match.group(1),
                            "file_path": task_file,
                            "agent": agent_dir.name,
                            "status": status
                        })
            except Exception:
                continue

    return followups


def get_audit_json(task_id: str) -> Optional[dict]:
    """Load audit JSON for a task."""
    audit_file = GATE_AUDITS_DIR / f"{task_id}.json"

    if not audit_file.exists():
        return None

    try:
        with open(audit_file) as f:
            return json.load(f)
    except Exception:
        return None


def show_gate_status(task_id: str):
    """Show detailed gate status for a task."""
    print(f"=== GATE STATUS: {task_id} ===\n")

    # Find the task file
    task_file = find_task_file(task_id, AGENTS_DIR)

    if not task_file:
        print(f"Task file not found for: {task_id}")
        return

    # Show file info
    print(f"File: {task_file}")
    print(f"Agent: {task_file.parent.parent.name}")

    # Extract frontmatter
    frontmatter = extract_frontmatter(task_file)

    print(f"Status: {task_file.suffix}")
    print(f"Parent: {frontmatter.get('parent_task', 'N/A')}")
    print(f"Gate Required: {frontmatter.get('gate_required', 'N/A')}")
    print(f"Created: {frontmatter.get('created', 'N/A')}")

    # Show audit info
    audit_ref = frontmatter.get('gate_audit_ref')
    if audit_ref:
        audit_path = Path(audit_ref).expanduser()
        if audit_path.exists():
            try:
                with open(audit_path) as f:
                    audit_data = json.load(f)

                print(f"\nAudit Result:")
                print(f"  Completion: {audit_data.get('completion_percentage', 'N/A')}%")
                print(f"  Can Complete: {audit_data.get('can_complete', 'N/A')}")
                print(f"  Required Follow-ups: {len(audit_data.get('required_followups', []))}")
                print(f"  Optional Improvements: {len(audit_data.get('optional_improvements', []))}")
                print(f"  Blockers: {len(audit_data.get('blockers', []))}")
            except Exception as e:
                print(f"\nAudit: (failed to load: {e})")
        else:
            print(f"\nAudit: (file not found: {audit_path})")

    # Show follow-ups
    followups = get_followup_tasks(task_id)

    if followups:
        print(f"\nFollow-up Tasks ({len(followups)}):")
        for fup in followups:
            status_symbol = {
                "completed": "✓",
                "executing": "→",
                "pending": "○",
                "blocked": "⚠",
                "pending_gate": "⏳"
            }.get(fup["status"], "?")

            print(f"  {status_symbol} {fup['task_id']}")
            print(f"     Agent: {fup['agent']}, Status: {fup['status']}")
    else:
        print(f"\nNo follow-up tasks found")

    # Check if all follow-ups are complete
    if followups:
        all_done = all(f["status"] == "completed" for f in followups)
        print(f"\nAll follow-ups complete: {all_done}")


def list_pending_gates():
    """List all pending gates."""
    pending = find_pending_gates()

    if not pending:
        print("No pending gates found")
        return

    print(f"=== PENDING GATES ({len(pending)}) ===\n")

    for gate_file in pending:
        task_id = extract_task_id(gate_file)
        agent = gate_file.parent.parent.name

        # Get follow-up count
        followup_count = 0
        completed_count = 0
        if task_id:
            followups = get_followup_tasks(task_id)
            followup_count = len(followups)
            completed_count = sum(1 for f in followups if f["status"] == "completed")

        # Check age
        mtime = datetime.fromtimestamp(gate_file.stat().st_mtime)
        age = (datetime.now() - mtime).total_seconds() / 3600  # hours

        age_str = f"{age:.1f}h"
        if age > 24:
            age_str = f"{age/24:.1f}d ⚠ STALE"

        print(f"{task_id or 'unknown'}")
        print(f"  File: {gate_file.name}")
        print(f"  Agent: {agent}")
        print(f"  Follow-ups: {completed_count}/{followup_count} complete")
        print(f"  Age: {age_str}")

        # Check for audit
        audit = get_audit_json(task_id) if task_id else None
        if audit:
            print(f"  Audit: {audit.get('completion_percentage', 'N/A')}% complete")

        print()


def list_followups(task_id: str):
    """List follow-ups for a task."""
    followups = get_followup_tasks(task_id)

    if not followups:
        print(f"No follow-ups found for: {task_id}")
        return

    print(f"=== FOLLOW-UPS FOR: {task_id} ({len(followups)}) ===\n")

    for fup in sorted(followups, key=lambda x: x["status"]):
        status_symbol = {
            "completed": "✓",
            "executing": "→",
            "pending": "○",
            "blocked": "⚠",
            "pending_gate": "⏳"
        }.get(fup["status"], "?")

        # Get more details from frontmatter
        frontmatter = extract_frontmatter(fup["file_path"])
        title = frontmatter.get("title", "No title")
        priority = frontmatter.get("priority", "normal")

        print(f"{status_symbol} {fup['task_id']}")
        print(f"   Title: {title}")
        print(f"   Agent: {fup['agent']}, Priority: {priority}")
        print(f"   Status: {fup['status']}")
        print(f"   File: {fup['file_path']}")
        print()


def show_audit_json(task_id: str):
    """Show the full audit JSON for a task."""
    audit = get_audit_json(task_id)

    if not audit:
        print(f"No audit found for: {task_id}")
        print(f"Expected: {GATE_AUDITS_DIR}/{task_id}.json")
        return

    print(f"=== AUDIT JSON: {task_id} ===\n")
    print(json.dumps(audit, indent=2))


def detect_gate_cycles(max_depth: int = 3) -> List[List[str]]:
    """
    Detect potential circular dependencies in follow-up chains.

    Returns list of cycles found.
    """
    cycles = []

    # Get all tasks with parent_task
    all_edges = {}  # child -> parent

    for agent_dir in AGENTS_DIR.iterdir():
        if not agent_dir.is_dir() or agent_dir.name.startswith('.'):
            continue

        if agent_dir.name not in VALID_AGENTS:
            continue

        tasks_dir = agent_dir / "tasks"
        if not tasks_dir.exists():
            continue

        for task_file in tasks_dir.glob("*.md"):
            try:
                with open(task_file, 'r') as f:
                    content = f.read(2000)

                # Check for parent_task
                match = re.search(r'parent_task:\s*(\S+)', content)
                if match:
                    child_match = re.search(r'task_id:\s*(\S+)', content)
                    if child_match:
                        all_edges[child_match.group(1)] = match.group(1)
            except Exception:
                continue

    # Detect cycles using DFS
    def dfs(node: str, path: List[str], visited: set) -> Optional[List[str]]:
        if node in path:
            # Found a cycle
            cycle_start = path.index(node)
            return path[cycle_start:] + [node]
        if len(path) > max_depth:
            return None
        if node in visited:
            return None

        visited.add(node)
        new_path = path + [node]

        # Find children of this node (tasks where this is parent)
        for child, parent in all_edges.items():
            if parent == node:
                result = dfs(child, new_path, visited.copy())
                if result:
                    return result

        return None

    # Check for cycles starting from each node
    for start_node in all_edges.keys():
        visited = set()
        cycle = dfs(start_node, [], visited)
        if cycle and cycle not in cycles:
            cycles.append(cycle)

    return cycles


def check_stale_gates(hours: int = 24) -> List[Dict[str, Any]]:
    """Check for gates stuck for too long."""
    stale = []

    for gate_file in find_pending_gates():
        task_id = extract_task_id(gate_file)
        mtime = datetime.fromtimestamp(gate_file.stat().st_mtime)
        age_hours = (datetime.now() - mtime).total_seconds() / 3600

        if age_hours > hours:
            stale.append({
                "task_id": task_id,
                "file": gate_file,
                "age_hours": age_hours,
                "agent": gate_file.parent.parent.name
            })

    return stale


def main():
    parser = argparse.ArgumentParser(
        description="Validate and debug completion gate status",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 task-gate-validator.py --list-pending
  python3 task-gate-validator.py --task high-12345678
  python3 task-gate-validator.py --list-followups high-12345678
  python3 task-gate-validator.py --audit-json high-12345678
  python3 task-gate-validator.py --check-cycles
  python3 task-gate-validator.py --check-stale
        """
    )

    parser.add_argument("--task", help="Show gate status for task ID")
    parser.add_argument("--list-pending", action="store_true",
                        help="List all pending gates")
    parser.add_argument("--list-followups", metavar="TASK_ID",
                        help="List follow-ups for a task")
    parser.add_argument("--audit-json", metavar="TASK_ID",
                        help="Show full audit JSON for a task")
    parser.add_argument("--check-cycles", action="store_true",
                        help="Check for circular dependencies")
    parser.add_argument("--check-stale", action="store_true",
                        help="Check for gates stuck > 24 hours")
    parser.add_argument("--stale-hours", type=int, default=24,
                        help="Hours threshold for stale check (default: 24)")

    args = parser.parse_args()

    if args.list_pending:
        list_pending_gates()
        return 0

    elif args.check_cycles:
        cycles = detect_gate_cycles()

        if not cycles:
            print("✓ No circular dependencies detected")
        else:
            print(f"⚠ Found {len(cycles)} potential cycles:")
            for cycle in cycles:
                print(f"  {' -> '.join(cycle)}")

        return 0

    elif args.check_stale:
        stale = check_stale_gates(args.stale_hours)

        if not stale:
            print(f"✓ No gates stuck > {args.stale_hours}h")
        else:
            print(f"⚠ Found {len(stale)} stale gates:")
            for item in stale:
                print(f"  {item['task_id']}: {item['age_hours']:.1f}h ({item['agent']})")

        return 0

    elif args.list_followups:
        list_followups(args.list_followups)
        return 0

    elif args.audit_json:
        show_audit_json(args.audit_json)
        return 0

    elif args.task:
        show_gate_status(args.task)
        return 0

    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
