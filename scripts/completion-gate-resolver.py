#!/usr/bin/env python3
"""
Completion Gate Resolver - Monitor and resolve pending gates.

This script finds tasks in .pending-gate state and checks if their follow-up
tasks are complete. When all follow-ups are done, it re-audits and either
passes the gate or creates additional follow-ups.

Usage:
    python3 completion-gate-resolver.py --resolve-all
    python3 completion-gate-resolver.py --metrics
    python3 completion-gate-resolver.py --task high-12345678

Design: ~/.openclaw/agents/mongke/workspace/completion-gate-design-2026-03-08.md
"""

import argparse
import json
import os
import re
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

# Add scripts directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kurultai_paths import AGENTS_DIR

# Import shared gate utilities (prevents code duplication)
from gate_utils import (
    VALID_AGENTS,
    validate_task_id,
    sanitize_task_id_for_glob,
    extract_frontmatter,
    find_task_file,
    extract_task_id
)

# Import gate repository for Neo4j-first pending gate discovery
try:
    from gate_repository import (
        get_gate_repository,
        GateRepository,
        GateTask,
        GateState,
        find_pending_gates as repo_find_pending_gates
    )
    GATE_REPOSITORY_AVAILABLE = True
except ImportError:
    GATE_REPOSITORY_AVAILABLE = False
    print("[WARN] gate_repository.py not available, using legacy filesystem scan")

# Gate audit log directory
GATE_AUDITS_DIR = Path.home() / ".openclaw" / "agents" / "main" / "logs" / "gate-audits"


class GateResolver:
    """
    Monitors pending gates and resolves them when follow-ups complete.

    Runs via cron (every 5 minutes) or triggered by task-watcher.

    Uses Neo4j-first gate discovery with filesystem fallback:
    - Primary: Indexed Neo4j query for gate_status='waiting_followups'
    - Fallback: Filesystem glob scan for *.pending-gate.md files
    - Cache: 60-second in-memory cache for performance
    """

    def __init__(self, dry_run: bool = False, use_cache: bool = True):
        self.dry_run = dry_run
        self.use_cache = use_cache

        # Initialize gate repository if available
        if GATE_REPOSITORY_AVAILABLE:
            self._gate_repo: Optional[GateRepository] = get_gate_repository(
                use_cache=use_cache
            )
        else:
            self._gate_repo = None

    def resolve_pending_gates(self) -> int:
        """
        Find all .pending-gate.md tasks and check if their follow-ups are complete.

        Returns:
            Number of gates resolved
        """
        pending_gates = self.find_pending_gates()

        if not pending_gates:
            return 0

        print(f"[GATE_RESOLVER] Found {len(pending_gates)} pending gates")

        resolved_count = 0

        for gate_task in pending_gates:
            try:
                task_id = extract_task_id(gate_task)

                if not task_id:
                    print(f"[WARN] Could not extract task ID from {gate_task}")
                    continue

                print(f"[GATE_RESOLVER] Checking gate: {task_id}")

                # Get follow-up tasks
                followup_ids = self.get_followup_tasks(task_id)

                if not followup_ids:
                    print(f"[GATE_RESOLVER] No follow-ups found for {task_id}, passing gate")
                    self.pass_gate(gate_task)
                    resolved_count += 1
                    continue

                # Check if all follow-ups are done
                all_complete = self.all_followups_complete(followup_ids)

                if all_complete:
                    print(f"[GATE_RESOLVER] All {len(followup_ids)} follow-ups complete for {task_id}")

                    # Re-audit to confirm nothing new missing
                    re_audit_result = self.re_audit(gate_task, task_id)

                    if re_audit_result and re_audit_result.get("can_complete"):
                        # Mark gate as passed
                        self.pass_gate(gate_task)
                        resolved_count += 1
                    else:
                        # New follow-ups needed
                        print(f"[GATE_RESOLVER] Re-audit found new issues for {task_id}")
                        # In production, would create additional follow-ups here
                        # For now, log and continue
                else:
                    # Check for blocked follow-ups
                    if self.has_blocked_followups(followup_ids):
                        print(f"[GATE_RESOLVER] Follow-ups blocked for {task_id}")
                        self.mark_gate_blocked(gate_task, "Some follow-up tasks are blocked")
                    else:
                        print(f"[GATE_RESOLVER] Follow-ups still pending for {task_id}")

            except Exception as e:
                print(f"[ERROR] Failed to resolve gate {gate_task}: {e}")

        return resolved_count

    def find_pending_gates(self) -> List[Path]:
        """Find all tasks in pending-gate state.

        Uses Neo4j-first query if available, falls back to filesystem scan.

        Returns:
            List of Path objects to pending gate files
        """
        # Use gate repository if available
        if self._gate_repo is not None:
            try:
                gate_tasks: List[GateTask] = self._gate_repo.find_pending()
                # Convert GateTask objects to Paths (for backward compatibility)
                return [gate.file_path for gate in gate_tasks]
            except Exception as e:
                # Repository failed, fall back to filesystem scan
                print(f"[WARN] Gate repository failed: {e}, using filesystem fallback")

        # Fallback: Legacy filesystem scan
        return self._find_pending_gates_filesystem()

    def _find_pending_gates_filesystem(self) -> List[Path]:
        """Legacy filesystem scan for *.pending-gate.md files.

        This is the fallback method when Neo4j is unavailable.
        """
        pending_gates = []

        for agent_dir in AGENTS_DIR.iterdir():
            if not agent_dir.is_dir() or agent_dir.name.startswith('.'):
                continue

            # Skip if not a valid agent directory
            if agent_dir.name not in VALID_AGENTS:
                continue

            tasks_dir = agent_dir / "tasks"
            if not tasks_dir.exists():
                continue

            for task_file in tasks_dir.glob("*.pending-gate.md"):
                pending_gates.append(task_file)

        return pending_gates

    def get_followup_tasks(self, parent_task_id: str) -> List[str]:
        """
        Get all follow-up task IDs for a parent task.

        Searches task files for parent_task reference.
        """
        followup_ids = []

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

                    # Check for parent_task reference
                    match = re.search(rf'parent_task:\s*{re.escape(parent_task_id)}', content)
                    if match:
                        # Extract this task's ID
                        task_match = re.search(r'task_id:\s*(\S+)', content)
                        if task_match:
                            followup_ids.append(task_match.group(1))
                except Exception:
                    continue

        return followup_ids

    def all_followups_complete(self, followup_ids: List[str]) -> bool:
        """
        Check if all follow-up tasks are complete (.done.md).

        Uses filesystem check for speed. Neo4j check available but not required.
        """
        for task_id in followup_ids:
            task_file = find_task_file(task_id, AGENTS_DIR)

            if not task_file:
                # Task file not found - can't be complete
                return False

            # Check if it ends with .done.md
            if not task_file.suffix == '.md' or '.done.' not in task_file.name:
                return False

        return True

    def has_blocked_followups(self, followup_ids: List[str]) -> bool:
        """Check if any follow-ups are in a blocked state (.gate-blocked.md or .failed)."""
        for task_id in followup_ids:
            task_file = find_task_file(task_id, AGENTS_DIR)

            if not task_file:
                continue

            if 'blocked' in task_file.name.lower() or 'failed' in task_file.name.lower():
                return True

        return False

    def re_audit(self, gate_task: Path, task_id: str) -> Optional[dict]:
        """
        Re-run audit on a pending gate.

        Returns the merged audit result, or None if audit failed.
        """
        try:
            # Import the audit function
            from completion_gate_audit import completion_gate_audit

            # Extract agent from frontmatter (now from gate_utils)
            task_metadata = extract_frontmatter(gate_task)
            agent = task_metadata.get("agent", "temujin")

            # Run fresh audit
            fresh_audit = completion_gate_audit(gate_task, agent)

            return {
                "can_complete": fresh_audit.can_complete,
                "completion_percentage": fresh_audit.completion_percentage,
                "required_followups": fresh_audit.required_followups,
                "optional_improvements": fresh_audit.optional_improvements,
                "blockers": fresh_audit.blockers
            }
        except Exception as e:
            print(f"[ERROR] Re-audit failed for {task_id}: {e}")
            return None

    def pass_gate(self, gate_task: Path):
        """
        Mark gate as passed and rename to .done.md.

        This is the FINAL completion that was originally blocked.
        """
        task_id = extract_task_id(gate_task)

        # Rename to .gate-passed.done.md
        done_file = gate_task.with_suffix(".gate-passed.done.md")

        if self.dry_run:
            print(f"[DRY_RUN] Would rename {gate_task.name} -> {done_file.name}")
            return

        try:
            gate_task.rename(done_file)
            print(f"[GATE_RESOLVER] ✓ Gate passed: {task_id} -> {done_file.name}")

            # Update Neo4j gate status if repository available
            if self._gate_repo is not None:
                try:
                    self._gate_repo.set_gate_status(task_id, GateState.PASSED)
                    self._gate_repo.invalidate_cache()
                except Exception as e:
                    print(f"[WARN] Failed to update Neo4j gate status: {e}")

            # Log completion
            self._log_gate_event({
                "event": "GATE_PASSED",
                "task_id": task_id,
                "timestamp": datetime.now().isoformat(),
                "file": str(done_file)
            })

        except Exception as e:
            print(f"[ERROR] Failed to pass gate for {task_id}: {e}")

    def mark_gate_blocked(self, gate_task: Path, reason: str):
        """Mark gate as blocked (external blocker requires human action)."""
        task_id = extract_task_id(gate_task)

        blocked_file = gate_task.with_suffix(".gate-blocked.md")

        if self.dry_run:
            print(f"[DRY_RUN] Would mark {gate_task.name} as blocked")
            return

        try:
            gate_task.rename(blocked_file)
            print(f"[GATE_RESOLVER] ⚠ Gate blocked: {task_id} - {reason}")

            # Update Neo4j gate status if repository available
            if self._gate_repo is not None:
                try:
                    self._gate_repo.set_gate_status(task_id, GateState.BLOCKED)
                    self._gate_repo.invalidate_cache()
                except Exception as e:
                    print(f"[WARN] Failed to update Neo4j gate status: {e}")

            self._log_gate_event({
                "event": "GATE_BLOCKED",
                "task_id": task_id,
                "reason": reason,
                "timestamp": datetime.now().isoformat()
            })
        except Exception as e:
            print(f"[ERROR] Failed to block gate for {task_id}: {e}")

    def get_gate_metrics(self) -> dict:
        """Return aggregate gate metrics."""
        pending_gates = self.find_pending_gates()

        # Count various states
        total_pending = len(pending_gates)
        blocked_count = 0
        total_followups = 0

        for gate in pending_gates:
            task_id = extract_task_id(gate)
            if task_id:
                followups = self.get_followup_tasks(task_id)
                total_followups += len(followups)

            if 'blocked' in str(gate):
                blocked_count += 1

        # Count recent audit results
        recent_audits = 0
        passed_audits = 0
        total_audit_completion = 0

        if GATE_AUDITS_DIR.exists():
            cutoff = datetime.now() - timedelta(hours=24)
            for audit_file in GATE_AUDITS_DIR.glob("*.json"):
                try:
                    # Check file mtime
                    mtime = datetime.fromtimestamp(audit_file.stat().st_mtime)
                    if mtime > cutoff:
                        recent_audits += 1
                        with open(audit_file) as f:
                            data = json.load(f)
                            if data.get("can_complete"):
                                passed_audits += 1
                            total_audit_completion += data.get("completion_percentage", 0)
                except Exception:
                    continue

        avg_completion = total_audit_completion / recent_audits if recent_audits > 0 else 0
        pass_rate = (passed_audits / recent_audits * 100) if recent_audits > 0 else 0

        return {
            "pending_gates": total_pending,
            "blocked_gates": blocked_count,
            "total_followups": total_followups,
            "recent_audits_24h": recent_audits,
            "passed_audits_24h": passed_audits,
            "pass_rate_24h": round(pass_rate, 1),
            "avg_completion_24h": round(avg_completion, 1)
        }

    def _log_gate_event(self, event: dict):
        """Log gate event to ledger file."""
        ledger_path = Path.home() / ".openclaw" / "logs" / "gate-events.log"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(ledger_path, 'a') as f:
                f.write(json.dumps(event) + '\n')
        except Exception:
            pass  # Don't block on logging failure


def print_metrics(metrics: dict):
    """Print formatted gate metrics."""
    print()
    print("=== COMPLETION GATE METRICS ===")
    print()
    print(f"Pending Gates:       {metrics['pending_gates']}")
    print(f"Blocked Gates:       {metrics['blocked_gates']}")
    print(f"Total Follow-ups:    {metrics['total_followups']}")
    print()
    print(f"Recent Audits (24h): {metrics['recent_audits_24h']}")
    print(f"Passed Audits:       {metrics['passed_audits_24h']}")
    print(f"Pass Rate:           {metrics['pass_rate_24h']}%")
    print(f"Avg Completion:      {metrics['avg_completion_24h']}%")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Resolve completion gates",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 completion-gate-resolver.py --resolve-all
  python3 completion-gate-resolver.py --metrics
  python3 completion-gate-resolver.py --task high-12345678 --check-only
        """
    )
    parser.add_argument("--resolve-all", action="store_true",
                        help="Check and resolve all pending gates")
    parser.add_argument("--metrics", action="store_true",
                        help="Show gate metrics")
    parser.add_argument("--task", help="Check specific task")
    parser.add_argument("--check-only", action="store_true",
                        help="Only check, don't resolve")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would happen without making changes")

    args = parser.parse_args()

    resolver = GateResolver(dry_run=args.dry_run)

    if args.metrics:
        metrics = resolver.get_gate_metrics()
        print_metrics(metrics)
        return 0

    elif args.resolve_all:
        resolved = resolver.resolve_pending_gates()
        print(f"\n[GATE_RESOLVER] Resolved {resolved} gates")
        return 0

    elif args.task:
        # Check specific task
        task_id = args.task
        followup_ids = resolver.get_followup_tasks(task_id)

        print(f"=== GATE STATUS: {task_id} ===")
        print(f"Follow-up tasks: {len(followup_ids)}")

        for fid in followup_ids:
            task_file = find_task_file(fid, AGENTS_DIR)
            status = "unknown"
            if task_file:
                if '.done.' in task_file.name:
                    status = "completed"
                elif '.executing.' in task_file.name:
                    status = "executing"
                elif '.blocked' in task_file.name:
                    status = "blocked"
                else:
                    status = "pending"

            print(f"  {fid}: {status}")

        all_complete = resolver.all_followups_complete(followup_ids)
        print(f"\nAll follow-ups complete: {all_complete}")

        if all_complete and not args.check_only:
            # Find the gate file
            gate_file = None
            for agent_dir in AGENTS_DIR.iterdir():
                tasks_dir = agent_dir / "tasks"
                if tasks_dir.exists():
                    for f in tasks_dir.glob(f"*{task_id}*.pending-gate.md"):
                        gate_file = f
                        break
                if gate_file:
                    break

            if gate_file:
                confirm = input(f"\nPass gate for {task_id}? [y/N] ")
                if confirm.lower() == 'y':
                    resolver.pass_gate(gate_file)

        return 0

    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
