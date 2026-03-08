#!/usr/bin/env python3
"""
Completion Gate Resolver - Monitors and resolves pending gates

Checks pending gates and resolves them when follow-up tasks complete.
Runs via task-watcher on every cycle or can be called directly.

Usage:
    from completion_gate_resolver import GateResolver

    resolver = GateResolver(dry_run=False)
    resolved_count = resolver.resolve_pending_gates()
"""

import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional

# Add scripts dir to path for imports
sys_path_insert = os.path.dirname(os.path.abspath(__file__))
if sys_path_insert not in sys.path:
    sys.path.insert(0, sys_path_insert)

from kurultai_paths import AGENTS_DIR

# Try to import ledger function
try:
    from kurultai_ledger import append_ledger
except ImportError:
    def append_ledger(entry):
        pass

# Gate file suffixes
SUFFIX_PENDING_GATE = ".pending-gate.md"
SUFFIX_GATE_PASSED = ".gate-passed.done.md"
SUFFIX_GATE_BYPASSED = ".gate-bypassed.done.md"
SUFFIX_GATE_BLOCKED = ".gate-blocked.md"

# Valid agents for lookups
VALID_AGENTS = {'kublai', 'temujin', 'mongke', 'chagatai', 'jochi', 'ogedei', 'tolui'}


def extract_yaml_frontmatter(content: str) -> dict:
    """Extract YAML frontmatter from task content."""
    metadata = {}
    if not content.startswith('---'):
        return metadata

    lines = content.split('\n')
    in_frontmatter = False

    for i, line in enumerate(lines):
        if i == 0 and line.strip() == '---':
            in_frontmatter = True
            continue
        if in_frontmatter and line.strip() == '---':
            break
        if in_frontmatter and ':' in line:
            key, _, value = line.partition(':')
            metadata[key.strip()] = value.strip().strip('"\'').strip()

    return metadata


class GateResolver:
    """Monitors pending gates and resolves them when follow-ups complete."""

    def __init__(self, dry_run: bool = False):
        self.agents_dir = Path(AGENTS_DIR)
        self.dry_run = dry_run
        self.resolved_count = 0
        self.errors = []

    def find_pending_gates(self) -> List[Path]:
        """Find all tasks in pending-gate state across all agents."""
        pending_gates = []

        for agent_dir in self.agents_dir.iterdir():
            if not agent_dir.is_dir() or agent_dir.name not in VALID_AGENTS:
                continue

            tasks_dir = agent_dir / "tasks"
            if not tasks_dir.exists():
                continue

            for task_file in tasks_dir.glob(f"*{SUFFIX_PENDING_GATE}"):
                pending_gates.append(task_file)

        return pending_gates

    def get_followup_tasks(self, parent_task_id: str) -> List[Tuple[Path, str]]:
        """
        Find all follow-up tasks for a parent task.

        Returns list of (task_path, status) tuples.
        Status is: 'pending', 'executing', 'completed', 'failed'
        """
        followups = []

        for agent_dir in self.agents_dir.iterdir():
            if not agent_dir.is_dir() or agent_dir.name not in VALID_AGENTS:
                continue

            tasks_dir = agent_dir / "tasks"
            if not tasks_dir.exists():
                continue

            # Look for tasks with parent_task matching our target
            for task_file in tasks_dir.glob("*.md"):
                try:
                    with open(task_file, 'r') as f:
                        content = f.read(2000)

                    # Check for parent_task field
                    parent_match = re.search(r'^parent_task:\s*(\S+)', content, re.MULTILINE)
                    if not parent_match:
                        continue

                    if parent_match.group(1) != parent_task_id:
                        continue

                    # Determine status from filename
                    fname = task_file.name
                    if '.completed.done' in fname or '.gate-passed.done' in fname:
                        status = 'completed'
                    elif '.failed.done' in fname or '.no_output.done' in fname:
                        status = 'failed'
                    elif '.executing' in fname:
                        status = 'executing'
                    else:
                        status = 'pending'

                    followups.append((task_file, status))

                except Exception as e:
                    self.errors.append(f"Error reading {task_file}: {e}")

        return followups

    def all_followups_complete(self, followups: List[Tuple[Path, str]]) -> bool:
        """Check if all follow-up tasks are complete."""
        if not followups:
            return True  # No followups = can proceed

        for _, status in followups:
            if status != 'completed':
                return False

        return True

    def has_blocked_followups(self, followups: List[Tuple[Path, str]]) -> bool:
        """Check if any follow-up has repeated failures (blocked)."""
        for task_path, status in followups:
            if status == 'failed':
                # Check retry count in frontmatter
                try:
                    with open(task_path, 'r') as f:
                        content = f.read(2000)
                    retry_match = re.search(r'^retry_count:\s*(\d+)', content, re.MULTILINE)
                    if retry_match and int(retry_match.group(1)) >= 3:
                        return True
                except Exception:
                    pass
        return False

    def mark_gate_blocked(self, gate_task: Path, reason: str):
        """Mark a gate as blocked (external blocker required)."""
        if self.dry_run:
            print(f"[DRY RUN] Would mark blocked: {gate_task.name}")
            return

        try:
            blocked_file = gate_task.parent / gate_task.name.replace(
                SUFFIX_PENDING_GATE, SUFFIX_GATE_BLOCKED
            )
            gate_task.rename(blocked_file)

            # Update Neo4j if available
            try:
                from neo4j_task_tracker import get_tracker
                tracker = get_tracker()
                task_id = extract_yaml_frontmatter(blocked_file.read_text()).get('task_id', '')
                tracker.update_gate_status(task_id, "BLOCKED")
            except Exception:
                pass

            append_ledger({
                "event": "GATE_BLOCKED",
                "ts": datetime.now().isoformat(),
                "task_file": str(gate_task),
                "reason": reason
            })

            print(f"⚠ Gate blocked: {gate_task.name} - {reason}")

        except Exception as e:
            self.errors.append(f"Failed to block {gate_task}: {e}")

    def pass_gate(self, gate_task: Path):
        """Mark gate as passed and rename to .done.md."""
        if self.dry_run:
            print(f"[DRY RUN] Would pass gate: {gate_task.name}")
            return

        try:
            task_id = extract_yaml_frontmatter(gate_task.read_text()).get('task_id', '')

            # Rename to .gate-passed.done.md
            passed_file = gate_task.parent / gate_task.name.replace(
                SUFFIX_PENDING_GATE, SUFFIX_GATE_PASSED
            )
            gate_task.rename(passed_file)

            # Update Neo4j
            try:
                from neo4j_task_tracker import get_tracker
                tracker = get_tracker()
                tracker.update_gate_status(task_id, "PASSED")
                tracker.update_status(task_id, "COMPLETED")
            except Exception:
                pass

            # Log completion
            append_ledger({
                "event": "GATE_PASSED",
                "task_id": task_id,
                "ts": datetime.now().isoformat()
            })

            print(f"✓ Gate passed: {task_id} → {passed_file.name}")

        except Exception as e:
            self.errors.append(f"Failed to pass gate {gate_task}: {e}")

    def bypass_gate(self, task_id: str, reason: str = "Manual bypass") -> bool:
        """Emergency bypass - mark a gate as bypassed without completing follow-ups."""
        # Find the pending gate file
        for agent_dir in self.agents_dir.iterdir():
            if not agent_dir.is_dir() or agent_dir.name not in VALID_AGENTS:
                continue

            tasks_dir = agent_dir / "tasks"
            if not tasks_dir.exists():
                continue

            for gate_file in tasks_dir.glob(f"*{SUFFIX_PENDING_GATE}"):
                try:
                    metadata = extract_yaml_frontmatter(gate_file.read_text())
                    if metadata.get('task_id') == task_id or task_id in gate_file.name:
                        if self.dry_run:
                            print(f"[DRY RUN] Would bypass: {gate_file.name}")
                            return True

                        # Rename to bypassed
                        bypassed_file = gate_file.parent / gate_file.name.replace(
                            SUFFIX_PENDING_GATE, SUFFIX_GATE_BYPASSED
                        )
                        gate_file.rename(bypassed_file)

                        # Update Neo4j
                        try:
                            from neo4j_task_tracker import get_tracker
                            tracker = get_tracker()
                            tracker.update_gate_status(task_id, "BYPASSED")
                            tracker.update_status(task_id, "COMPLETED")
                        except Exception:
                            pass

                        # Log
                        append_ledger({
                            "event": "GATE_BYPASSED",
                            "task_id": task_id,
                            "ts": datetime.now().isoformat(),
                            "reason": reason
                        })

                        print(f"⚠ Gate bypassed: {task_id}")
                        return True

                except Exception as e:
                    self.errors.append(f"Error checking {gate_file}: {e}")

        print(f"✗ Gate not found: {task_id}")
        return False

    def resolve_pending_gates(self) -> int:
        """
        Find all .pending-gate.md tasks and check if their follow-ups are complete.

        Returns: Number of gates resolved.
        """
        pending_gates = self.find_pending_gates()
        resolved = 0

        for gate_task in pending_gates:
            try:
                # Extract task ID from frontmatter
                with open(gate_task, 'r') as f:
                    content = f.read(2000)

                metadata = extract_yaml_frontmatter(content)
                task_id = metadata.get('task_id', gate_task.stem)

                # Get follow-up tasks
                followups = self.get_followup_tasks(task_id)

                # Check if all follow-ups are complete
                if self.all_followups_complete(followups):
                    # All follow-ups done - can pass gate
                    self.pass_gate(gate_task)
                    resolved += 1

                elif self.has_blocked_followups(followups):
                    # Follow-ups stuck - mark blocked
                    self.mark_gate_blocked(gate_task, "Follow-up tasks have repeated failures")

            except Exception as e:
                self.errors.append(f"Failed to process {gate_task}: {e}")
                print(f"✗ Gate resolution error: {gate_task.name} - {e}")

        self.resolved_count = resolved
        return resolved


def resolve_pending_gates() -> int:
    """Convenience function to resolve pending gates."""
    resolver = GateResolver(dry_run=False)
    return resolver.resolve_pending_gates()


# CLI interface
if __name__ == "__main__":
    import argparse
    import json as json_module

    parser = argparse.ArgumentParser(description="Completion Gate Resolver")
    parser.add_argument("--bypass", metavar="TASK_ID", help="Bypass a specific gate")
    parser.add_argument("--bypass-reason", default="Manual bypass", help="Reason for bypass")
    parser.add_argument("--list", action="store_true", help="List pending gates")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode")

    args = parser.parse_args()

    resolver = GateResolver(dry_run=args.dry_run)

    if args.list:
        gates = resolver.find_pending_gates()
        if args.json:
            print(json_module.dumps([str(g) for g in gates], indent=2))
        else:
            print(f"Found {len(gates)} pending gates:")
            for g in gates:
                print(f"  {g.name}")
        exit(0)

    if args.bypass:
        success = resolver.bypass_gate(args.bypass, args.bypass_reason)
        exit(0 if success else 1)

    # Default: resolve pending gates
    print(f"[gate_resolver] Checking for pending gates...")
    resolved = resolver.resolve_pending_gates()
    print(f"[gate_resolver] Resolved {resolved} gates")

    if resolver.errors:
        print(f"[gate_resolver] Errors: {len(resolver.errors)}")
        for e in resolver.errors:
            print(f"  - {e}")

    exit(0)
