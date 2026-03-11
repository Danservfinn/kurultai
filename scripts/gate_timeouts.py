#!/usr/bin/env python3
"""
Gate Timeout Configuration and Enforcement.

Implements timeout mechanisms for the completion gate system:
- Pending timeout: Tasks stuck in pending-gate > 24h auto-escalate
- Audit timeout: LLM calls wrap with 5-minute timeout
- Follow-up timeout: Track follow-ups > 7 days with auto-resolve option

Usage:
    from gate_timeouts import (
        GATE_PENDING_TIMEOUT,
        GATE_AUDIT_TIMEOUT,
        GATE_FOLLOWUP_TIMEOUT,
        check_pending_gate_timeouts,
        check_followup_timeouts,
        escalate_stuck_gate
    )

Design: ~/.openclaw/agents/mongke/workspace/completion-gate-design-2026-03-08.md
Task: gate-timeout-008
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

# Add scripts directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kurultai_paths import AGENTS_DIR

# Import shared gate utilities
from gate_utils import (
    VALID_AGENTS,
    extract_frontmatter,
    find_task_file,
    extract_task_id
)

# =============================================================================
# TIMEOUT CONFIGURATION
# =============================================================================

# Default timeout values (can be overridden via environment variables)
GATE_PENDING_TIMEOUT_HOURS = int(os.getenv("GATE_PENDING_TIMEOUT_HOURS", "24"))
GATE_AUDIT_TIMEOUT_SECONDS = int(os.getenv("GATE_AUDIT_TIMEOUT_SECONDS", "300"))  # 5 minutes
GATE_FOLLOWUP_TIMEOUT_DAYS = int(os.getenv("GATE_FOLLOWUP_TIMEOUT_DAYS", "7"))

# Convert to timedelta objects
GATE_PENDING_TIMEOUT = timedelta(hours=GATE_PENDING_TIMEOUT_HOURS)
GATE_AUDIT_TIMEOUT = timedelta(seconds=GATE_AUDIT_TIMEOUT_SECONDS)
GATE_FOLLOWUP_TIMEOUT = timedelta(days=GATE_FOLLOWUP_TIMEOUT_DAYS)

# Escalation paths
KUBLAI_TASKS_DIR = AGENTS_DIR / "kublai" / "tasks"
TIMEOUT_LOG_DIR = Path.home() / ".openclaw" / "agents" / "main" / "logs" / "gate-timeouts"
TIMEOUT_LOG_DIR.mkdir(parents=True, exist_ok=True)

# Watchdog state file for tracking consecutive timeout detections
TIMEOUT_STATE_FILE = TIMEOUT_LOG_DIR / "timeout_state.json"


# =============================================================================
# TIMEOUT DETECTION
# =============================================================================

def find_pending_gate_tasks() -> List[Path]:
    """Find all tasks in pending-gate state.

    Returns:
        List of Path objects to pending gate files
    """
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


def get_gate_age(gate_file: Path) -> timedelta:
    """Calculate the age of a gate task.

    Args:
        gate_file: Path to the pending-gate task file

    Returns:
        Timedelta representing the age of the gate
    """
    # Try to get created timestamp from frontmatter
    frontmatter = extract_frontmatter(gate_file)
    created_str = frontmatter.get("created")

    if created_str:
        try:
            # Parse ISO 8601 timestamp
            created_dt = datetime.fromisoformat(created_str.replace('Z', '+00:00'))
            # Make it timezone-aware if it isn't
            if created_dt.tzinfo is None:
                created_dt = created_dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
            return datetime.now().astimezone() - created_dt
        except (ValueError, TypeError):
            pass

    # Fallback to file mtime
    mtime = datetime.fromtimestamp(gate_file.stat().st_mtime)
    return datetime.now() - mtime


def find_followup_tasks(parent_task_id: str) -> List[Dict[str, Any]]:
    """Find all follow-up tasks for a parent task.

    Args:
        parent_task_id: Parent task ID to find follow-ups for

    Returns:
        List of dicts with task_id, file_path, agent, status, and age
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

                # Check for parent_task reference
                if f'parent_task: {parent_task_id}' in content:
                    # Extract task ID
                    import re
                    task_match = re.search(r'task_id:\s*(\S+)', content)
                    if task_match:
                        task_id = task_match.group(1)

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

                        # Get age
                        frontmatter = extract_frontmatter(task_file)
                        created_str = frontmatter.get("created")
                        age = None
                        if created_str:
                            try:
                                created_dt = datetime.fromisoformat(created_str.replace('Z', '+00:00'))
                                if created_dt.tzinfo is None:
                                    created_dt = created_dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
                                age = datetime.now().astimezone() - created_dt
                            except (ValueError, TypeError):
                                pass

                        if age is None:
                            # Fallback to file mtime
                            mtime = datetime.fromtimestamp(task_file.stat().st_mtime)
                            age = datetime.now() - mtime

                        followups.append({
                            "task_id": task_id,
                            "file_path": task_file,
                            "agent": agent_dir.name,
                            "status": status,
                            "age": age
                        })
            except Exception:
                continue

    return followups


# =============================================================================
# TIMEOUT CHECKING
# =============================================================================

def check_pending_gate_timeouts(
    timeout: Optional[timedelta] = None
) -> List[Dict[str, Any]]:
    """Check for gates stuck in pending state too long.

    Args:
        timeout: Custom timeout (uses GATE_PENDING_TIMEOUT if None)

    Returns:
        List of stuck gate info dicts with keys:
        - task_id: The task ID
        - file_path: Path to the gate file
        - age: Timedelta of how long it's been stuck
        - agent: Agent name
        - followups: List of follow-up task status
    """
    if timeout is None:
        timeout = GATE_PENDING_TIMEOUT

    stuck_gates = []

    for gate_file in find_pending_gate_tasks():
        age = get_gate_age(gate_file)

        if age > timeout:
            task_id = extract_task_id(gate_file)
            agent = gate_file.parent.parent.name

            # Get follow-up status
            parent_task_id = task_id or gate_file.stem.replace('.pending-gate', '')
            followups = find_followup_tasks(parent_task_id)

            stuck_gates.append({
                "task_id": task_id,
                "file_path": gate_file,
                "age": age,
                "age_hours": age.total_seconds() / 3600,
                "agent": agent,
                "followups": followups,
                "followup_count": len(followups),
                "followups_complete": all(f["status"] == "completed" for f in followups),
                "has_blocked": any(f["status"] == "blocked" for f in followups)
            })

    return stuck_gates


def check_followup_timeouts(
    timeout: Optional[timedelta] = None
) -> List[Dict[str, Any]]:
    """Check for follow-up tasks that are too old.

    Args:
        timeout: Custom timeout (uses GATE_FOLLOWUP_TIMEOUT if None)

    Returns:
        List of timed-out follow-up info dicts
    """
    if timeout is None:
        timeout = GATE_FOLLOWUP_TIMEOUT

    timed_out_followups = []

    # Find all tasks with parent_task
    for agent_dir in AGENTS_DIR.iterdir():
        if not agent_dir.is_dir() or agent_dir.name.startswith('.'):
            continue

        if agent_dir.name not in VALID_AGENTS:
            continue

        tasks_dir = agent_dir / "tasks"
        if not tasks_dir.exists():
            continue

        for task_file in tasks_dir.glob("*.md"):
            # Skip completed tasks
            if '.done.' in task_file.name:
                continue

            try:
                with open(task_file, 'r') as f:
                    content = f.read(2000)

                # Check if it has a parent_task
                import re
                parent_match = re.search(r'parent_task:\s*(\S+)', content)
                if not parent_match:
                    continue

                parent_task_id = parent_match.group(1)

                # Get task ID
                task_match = re.search(r'task_id:\s*(\S+)', content)
                if not task_match:
                    continue

                task_id = task_match.group(1)

                # Get age
                frontmatter = extract_frontmatter(task_file)
                created_str = frontmatter.get("created")
                age = None
                if created_str:
                    try:
                        created_dt = datetime.fromisoformat(created_str.replace('Z', '+00:00'))
                        if created_dt.tzinfo is None:
                            created_dt = created_dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
                        age = datetime.now().astimezone() - created_dt
                    except (ValueError, TypeError):
                        pass

                if age is None:
                    mtime = datetime.fromtimestamp(task_file.stat().st_mtime)
                    age = datetime.now() - mtime

                if age > timeout:
                    timed_out_followups.append({
                        "task_id": task_id,
                        "parent_task_id": parent_task_id,
                        "file_path": task_file,
                        "age": age,
                        "age_days": age.total_seconds() / 86400,
                        "agent": agent_dir.name,
                        "status": "pending"  # Since we skipped .done files
                    })
            except Exception:
                continue

    return timed_out_followups


# =============================================================================
# ESCALATION
# =============================================================================

def create_kublai_timeout_task(
    reason: str,
    stuck_gates: List[Dict[str, Any]],
    timeout_type: str
) -> Optional[Path]:
    """Create a kublai task for timeout escalation.

    Args:
        reason: Human-readable reason for escalation
        stuck_gates: List of stuck gate info
        timeout_type: Type of timeout (e.g., "pending_gate", "followup")

    Returns:
        Path to created task file, or None if failed
    """
    import uuid

    task_id = f"timeout-{timeout_type}-{uuid.uuid4().hex[:8]}"
    timestamp = datetime.now().isoformat()

    # Build task frontmatter
    frontmatter_lines = [
        "---",
        f"agent: kublai",
        f"priority: high",
        f"created: {timestamp}",
        f"source: gate-timeout-monitor",
        f"task_id: {task_id}",
        f"bucket: TODAY",
        f"domain: operations",
        f"skill_hint: null",
        "---"
    ]

    # Build task body
    body_lines = [
        f"# Gate Timeout Escalation: {timeout_type}",
        "",
        f"**Detected:** {timestamp}",
        f"**Reason:** {reason}",
        "",
        "## Stuck Gates",
        ""
    ]

    for gate in stuck_gates:
        body_lines.append(f"### `{gate.get('task_id', 'unknown')}`")
        body_lines.append(f"- **Agent:** {gate.get('agent', 'unknown')}")
        body_lines.append(f"- **Age:** {gate.get('age_hours', 0):.1f} hours")
        body_lines.append(f"- **File:** {gate.get('file_path', 'unknown')}")

        if timeout_type == "pending_gate":
            followups = gate.get('followups', [])
            body_lines.append(f"- **Follow-ups:** {len(followups)} total, {sum(1 for f in followups if f['status'] == 'completed')} complete")

            if gate.get('has_blocked'):
                body_lines.append(f"- **⚠️ BLOCKED:** Has blocked follow-ups")
            elif gate.get('followups_complete'):
                body_lines.append(f"- **✅ All follow-ups complete - gate should resolve**")

        body_lines.append("")

    body_lines.extend([
        "## Required Action",
        "",
        "1. Investigate why the gate is stuck",
        "2. Resolve or bypass as appropriate",
        "3. Consider updating follow-up tasks if needed",
        "",
        f"---\n_Generated by gate_timeouts.py at {timestamp}_"
    ])

    # Write task file
    task_filename = f"high-{task_id}.md"
    task_path = KUBLAI_TASKS_DIR / task_filename

    # Ensure directory exists
    KUBLAI_TASKS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        with open(task_path, 'w') as f:
            f.write('\n'.join(frontmatter_lines) + '\n')
            f.write('\n'.join(body_lines) + '\n')
        return task_path
    except Exception as e:
        print(f"[ERROR] Failed to create kublai task: {e}")
        return None


def escalate_stuck_gates(
    stuck_gates: List[Dict[str, Any]],
    dry_run: bool = False
) -> Tuple[int, Optional[Path]]:
    """Escalate stuck gates to kublai.

    Args:
        stuck_gates: List of stuck gate info from check_pending_gate_timeouts
        dry_run: If True, don't actually create tasks

    Returns:
        Tuple of (count of escalations, path to kublai task)
    """
    if not stuck_gates:
        return 0, None

    reason = f"{len(stuck_gates)} gate(s) stuck > {GATE_PENDING_TIMEOUT_HOURS}h"

    if dry_run:
        print(f"[DRY_RUN] Would create kublai task: {reason}")
        for gate in stuck_gates:
            print(f"  - {gate.get('task_id', 'unknown')}: {gate.get('age_hours', 0):.1f}h")
        return len(stuck_gates), None

    task_path = create_kublai_timeout_task(
        reason=reason,
        stuck_gates=stuck_gates,
        timeout_type="pending_gate"
    )

    if task_path:
        return len(stuck_gates), task_path
    return 0, None


def log_timeout_event(
    event_type: str,
    details: Dict[str, Any]
):
    """Log a timeout event to the timeout log.

    Args:
        event_type: Type of event (e.g., "pending_timeout", "followup_timeout")
        details: Event details
    """
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "event_type": event_type,
        "details": details
    }

    # Append to daily log file
    log_file = TIMEOUT_LOG_DIR / f"timeouts-{datetime.now().strftime('%Y-%m-%d')}.jsonl"

    try:
        with open(log_file, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
    except Exception as e:
        print(f"[ERROR] Failed to log timeout event: {e}")


# =============================================================================
# MAIN CLI
# =============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Check and enforce gate timeouts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 gate_timeouts.py --check-pending
  python3 gate_timeouts.py --check-followups
  python3 gate_timeouts.py --escalate --dry-run
  python3 gate_timeouts.py --summary
        """
    )

    parser.add_argument("--check-pending", action="store_true",
                        help="Check for pending gate timeouts")
    parser.add_argument("--check-followups", action="store_true",
                        help="Check for follow-up timeouts")
    parser.add_argument("--escalate", action="store_true",
                        help="Escalate stuck gates to kublai")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would happen without making changes")
    parser.add_argument("--summary", action="store_true",
                        help="Show timeout configuration summary")
    parser.add_argument("--pending-hours", type=int,
                        help=f"Override pending timeout (default: {GATE_PENDING_TIMEOUT_HOURS}h)")
    parser.add_argument("--followup-days", type=int,
                        help=f"Override followup timeout (default: {GATE_FOLLOWUP_TIMEOUT_DAYS}d)")

    args = parser.parse_args()

    if args.summary:
        print("=== GATE TIMEOUT CONFIGURATION ===")
        print()
        print(f"Pending Gate Timeout: {GATE_PENDING_TIMEOUT_HOURS} hours")
        print(f"Audit Timeout: {GATE_AUDIT_TIMEOUT_SECONDS} seconds")
        print(f"Follow-up Timeout: {GATE_FOLLOWUP_TIMEOUT_DAYS} days")
        print()
        print(f"Timeout Log Dir: {TIMEOUT_LOG_DIR}")
        print(f"Kublai Tasks Dir: {KUBLAI_TASKS_DIR}")
        print()
        print("Environment Variables:")
        print(f"  GATE_PENDING_TIMEOUT_HOURS={os.getenv('GATE_PENDING_TIMEOUT_HOURS', '24')}")
        print(f"  GATE_AUDIT_TIMEOUT_SECONDS={os.getenv('GATE_AUDIT_TIMEOUT_SECONDS', '300')}")
        print(f"  GATE_FOLLOWUP_TIMEOUT_DAYS={os.getenv('GATE_FOLLOWUP_TIMEOUT_DAYS', '7')}")
        return 0

    # Build custom timeouts if specified
    pending_timeout = None
    followup_timeout = None
    if args.pending_hours:
        pending_timeout = timedelta(hours=args.pending_hours)
    if args.followup_days:
        followup_timeout = timedelta(days=args.followup_days)

    if args.check_pending:
        stuck = check_pending_gate_timeouts(timeout=pending_timeout)

        if not stuck:
            print(f"✓ No pending gates stuck > {args.pending_hours or GATE_PENDING_TIMEOUT_HOURS}h")
            return 0

        print(f"⚠ Found {len(stuck)} stuck pending gates:")
        for gate in stuck:
            print(f"  - {gate['task_id']}: {gate['age_hours']:.1f}h ({gate['agent']})")
            print(f"    Follow-ups: {gate['followup_count']}, Complete: {gate['followups_complete']}, Blocked: {gate['has_blocked']}")

        # Log the event
        log_timeout_event("pending_timeout_check", {
            "count": len(stuck),
            "stuck_gates": [
                {"task_id": g["task_id"], "age_hours": g["age_hours"]}
                for g in stuck
            ]
        })

        return 1 if stuck else 0

    if args.check_followups:
        timed_out = check_followup_timeouts(timeout=followup_timeout)

        if not timed_out:
            print(f"✓ No follow-ups stuck > {args.followup_days or GATE_FOLLOWUP_TIMEOUT_DAYS}d")
            return 0

        print(f"⚠ Found {len(timed_out)} timed-out follow-ups:")
        for fu in timed_out:
            print(f"  - {fu['task_id']}: {fu['age_days']:.1f}d ({fu['agent']})")
            print(f"    Parent: {fu['parent_task_id']}")

        # Log the event
        log_timeout_event("followup_timeout_check", {
            "count": len(timed_out),
            "timed_out": [
                {"task_id": f["task_id"], "age_days": f["age_days"]}
                for f in timed_out
            ]
        })

        return 1 if timed_out else 0

    if args.escalate:
        stuck = check_pending_gate_timeouts(timeout=pending_timeout)

        if not stuck:
            print("✓ No stuck gates to escalate")
            return 0

        count, task_path = escalate_stuck_gates(stuck, dry_run=args.dry_run)

        if args.dry_run:
            print(f"[DRY_RUN] Would escalate {count} gates to kublai")
        elif task_path:
            print(f"✓ Escalated {count} gates to kublai: {task_path}")
            log_timeout_event("escalation", {
                "count": count,
                "task_path": str(task_path)
            })
        else:
            print(f"✗ Failed to escalate gates")
            return 1

        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
