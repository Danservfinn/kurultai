#!/usr/bin/env python3
"""
Autoresearch Completion Gate - Block autonomous commits to protected branches.

This script integrates with the completion gate system to block autonomous
agent commits to main/master branches without explicit Kublai approval.

Integration Points:
1. Called by completion-gate-audit.py before marking task complete
2. Checks autoresearch approval status
3. Blocks commits to protected branches without approval
4. Sends Signal notifications for violations

Usage:
    from autoresearch_completion_gate import check_autoresearch_commit

    # Check if autonomous commit is allowed
    allowed, reason = check_autoresearch_commit(
        agent="mongke",
        branch="main",
        files=["research/output.md"],
        task_id="task-123"
    )

    if not allowed:
        print(f"BLOCKED: {reason}")
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Tuple

# Add scripts directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import autoresearch approval module
try:
    from autoresearch_approval import AutoresearchApproval, ApprovalStatus
    AUTORESEARCH_APPROVAL_AVAILABLE = True
except ImportError:
    AUTORESEARCH_APPROVAL_AVAILABLE = False
    print("[WARN] autoresearch_approval module not available, gate will allow all commits")

# Import approval workflow for shared patterns
try:
    from approval_workflow import ApprovalWorkflow
    APPROVAL_WORKFLOW_AVAILABLE = True
except ImportError:
    APPROVAL_WORKFLOW_AVAILABLE = False

# Policy config path
POLICY_PATH = Path(__file__).parent.parent.parent / "config" / "autoresearch-policy.json"

# Signal notification script
SEND_SIGNAL_SCRIPT = Path.home() / ".claude" / "skills" / "agent-collaboration" / "scripts" / "send_signal.sh"


def send_signal_alert(message: str) -> bool:
    """Send Signal notification for autoresearch events."""
    try:
        if SEND_SIGNAL_SCRIPT.exists():
            cmd = ["bash", str(SEND_SIGNAL_SCRIPT), "+15165643945", message]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            return result.returncode == 0
        else:
            # Fallback: direct signal-cli call
            cmd = [
                "signal-cli",
                "-a", os.getenv("SIGNAL_ACCOUNT", "+15165643945"),
                "send",
                "-m", message,
                "+15165643945"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            return result.returncode == 0
    except Exception as e:
        print(f"[AUTORESEARCH-GATE] Signal alert failed: {e}", file=sys.stderr)
        return False


def load_policy() -> dict:
    """Load autoresearch policy configuration."""
    if POLICY_PATH.exists():
        with open(POLICY_PATH) as f:
            return json.load(f)
    return {
        "enabled_agents": ["mongke", "jochi", "chagatai"],
        "require_human_approval_for": ["main", "master"],
        "auto_approve_safe_paths": ["workspace/**", "memory/*.md"],
        "max_parallel_autonomous_tasks": 3,
    }


def check_autoresearch_commit(
    agent: str,
    branch: str,
    files: List[str],
    task_id: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Check if autonomous commit is allowed.

    Args:
        agent: Agent attempting the commit
        branch: Target branch for commit
        files: Files to be committed
        task_id: Optional task ID for lookup

    Returns:
        Tuple of (allowed: bool, reason: str)
    """
    if not AUTORESEARCH_APPROVAL_AVAILABLE:
        return True, "Autoresearch approval module not available, allowing commit"

    policy = load_policy()
    approval = AutoresearchApproval()

    # Check if agent is enabled for autoresearch
    if agent not in policy.get("enabled_agents", []):
        return True, f"Agent {agent} not in enabled_agents list, standard commit rules apply"

    # Check if branch is protected
    protected_branches = policy.get("completion_gate", {}).get("block_branches", ["main", "master"])
    if branch in protected_branches:
        # Check for approval
        if task_id:
            # Look for approval request matching this task
            for req_id, req in approval._requests.items():
                if req.task_id == task_id and req.status == ApprovalStatus.APPROVED:
                    return True, f"Approved by {req.approver} on {req.updated_at}"

        # No approval found - block
        reason = f"Autonomous commits to '{branch}' are blocked by completion gate. Requires Kublai approval."

        # Send alert
        message = f"⚠️ *AUTORESEARCH BLOCKED*\n\n"
        message += f"*Agent:* {agent}\n"
        message += f"*Branch:* {branch}\n"
        message += f"*Task:* {task_id or 'Unknown'}\n"
        message += f"*Reason:* {reason}"

        send_signal_alert(message)

        return False, reason

    # Check if files require approval
    import fnmatch
    require_approval_patterns = policy.get("require_human_approval_for", [])

    for file_path in files:
        for pattern in require_approval_patterns:
            if fnmatch.fnmatch(file_path, pattern):
                # Check for approval
                if task_id:
                    for req_id, req in approval._requests.items():
                        if req.task_id == task_id and req.status == ApprovalStatus.APPROVED:
                            if file_path in req.files_affected or not req.files_affected:
                                return True, f"Approved by {req.approver}"

                # No approval found - block
                reason = f"File '{file_path}' matches protected pattern '{pattern}'. Requires human approval."

                message = f"⚠️ *AUTORESEARCH BLOCKED*\n\n"
                message += f"*Agent:* {agent}\n"
                message += f"*File:* {file_path}\n"
                message += f"*Pattern:* {pattern}\n"
                message += f"*Reason:* {reason}"

                send_signal_alert(message)

                return False, reason

    return True, "Autonomous commit allowed"


def check_autoresearch_task_completion(
    task_id: str,
    agent: str,
    execution_output: str
) -> Tuple[bool, str, Optional[str]]:
    """
    Check if autoresearch task can be marked complete.

    Args:
        task_id: The task ID
        agent: Agent that executed the task
        execution_output: Task execution output

    Returns:
        Tuple of (can_complete: bool, reason: str, approval_request_id: Optional[str])
    """
    if not AUTORESEARCH_APPROVAL_AVAILABLE:
        return True, "Autoresearch approval module not available", None

    policy = load_policy()

    # Check if this is an autoresearch task
    # (tasks with autoresearch domain or containing autoresearch keywords)
    is_autoresearch = False

    # Check execution output for autoresearch markers
    if "autoresearch" in execution_output.lower() or "autonomous research" in execution_output.lower():
        is_autoresearch = True

    # Check if agent is in enabled_agents
    if agent in policy.get("enabled_agents", []):
        # Look for approval request
        approval = AutoresearchApproval()
        for req_id, req in approval._requests.items():
            if req.task_id == task_id:
                if req.status == ApprovalStatus.APPROVED:
                    return True, f"Autoresearch approved by {req.approver}", req_id
                elif req.status == ApprovalStatus.PENDING:
                    return False, f"Awaiting Kublai approval (request: {req_id})", req_id
                elif req.status == ApprovalStatus.REJECTED:
                    return False, f"Rejected by {req.approver}: {req.rejection_reason}", req_id

    return True, "Standard task completion", None


def record_autonomous_commit(
    agent: str,
    branch: str,
    files: List[str],
    task_id: str,
    commit_hash: str,
    allowed: bool,
    reason: str
) -> None:
    """Record autonomous commit to audit log."""
    log_dir = Path.home() / ".openclaw" / "logs" / "autoresearch-gate"
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / f"{datetime.now().strftime('%Y-%m-%d')}.jsonl"

    entry = {
        "timestamp": datetime.now().isoformat(),
        "agent": agent,
        "branch": branch,
        "files": files,
        "task_id": task_id,
        "commit_hash": commit_hash,
        "allowed": allowed,
        "reason": reason,
    }

    with open(log_file, "a") as f:
        f.write(json.dumps(entry) + "\n")


def main():
    """CLI interface for autoresearch completion gate."""
    import argparse

    parser = argparse.ArgumentParser(description="Autoresearch Completion Gate")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Check command
    check_parser = subparsers.add_parser("check", help="Check if commit is allowed")
    check_parser.add_argument("--agent", required=True, help="Agent name")
    check_parser.add_argument("--branch", required=True, help="Target branch")
    check_parser.add_argument("--files", nargs="*", default=[], help="Files to commit")
    check_parser.add_argument("--task-id", help="Task ID")

    # Record command
    record_parser = subparsers.add_parser("record", help="Record commit")
    record_parser.add_argument("--agent", required=True, help="Agent name")
    record_parser.add_argument("--branch", required=True, help="Target branch")
    record_parser.add_argument("--files", nargs="*", default=[], help="Files committed")
    record_parser.add_argument("--task-id", required=True, help="Task ID")
    record_parser.add_argument("--commit-hash", required=True, help="Git commit hash")
    record_parser.add_argument("--allowed", action="store_true", help="Was commit allowed")
    record_parser.add_argument("--reason", required=True, help="Reason for decision")

    args = parser.parse_args()

    if args.command == "check":
        allowed, reason = check_autoresearch_commit(
            agent=args.agent,
            branch=args.branch,
            files=args.files,
            task_id=args.task_id
        )
        print(f"ALLOWED: {allowed}")
        print(f"REASON: {reason}")
        sys.exit(0 if allowed else 1)

    elif args.command == "record":
        record_autonomous_commit(
            agent=args.agent,
            branch=args.branch,
            files=args.files,
            task_id=args.task_id,
            commit_hash=args.commit_hash,
            allowed=args.allowed,
            reason=args.reason
        )
        print("Commit recorded to audit log")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
