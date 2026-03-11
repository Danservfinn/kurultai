#!/usr/bin/env python3
"""
Autoresearch Approval Flow — Human-in-the-loop approval for autonomous agent operations.

This module implements the approval workflow for autoresearch tasks:
1. Propose: Agent creates task with autoresearch type
2. Kublai Review: Human reviews and approves/rejects
3. Quarantine Execute: Agent works in isolated branch
4. Submit for Review: PR created for human review
5. Merge: Human merges after review

Security Model:
- No autonomous merges to main/master without explicit Kublai approval
- All autoresearch work happens in quarantine branches
- Signal notifications for all key events
- Completion gate blocks unauthorized autonomous commits

Usage:
    from autoresearch_approval import AutoresearchApproval

    approval = AutoresearchApproval()

    # Start approval flow
    request_id = approval.propose(
        task_id="task-123",
        agent="mongke",
        title="Research competitors",
        files=["research/output.md"]
    )

    # Check approval status
    status = approval.check_status(request_id)

    # Approve/reject
    approval.approve(request_id, approver="kublai")
    approval.reject(request_id, approver="kublai", reason="Needs more detail")
"""

import json
import os
import subprocess
import sys
import time
import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any

# Add scripts directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import from approval_workflow for shared patterns
try:
    from approval_workflow import ApprovalStatus
except ImportError:
    class ApprovalStatus(Enum):
        PENDING = "pending"
        APPROVED = "approved"
        REJECTED = "rejected"
        BYPASSED = "bypassed"
        EXPIRED = "expired"
        CANCELLED = "cancelled"

# Policy config path
POLICY_PATH = Path(__file__).parent.parent.parent / "config" / "autoresearch-policy.json"
APPROVAL_STATE_PATH = Path(__file__).parent.parent.parent / "config" / "approval_requests.json"

# Signal notification script
SEND_SIGNAL_SCRIPT = Path.home() / ".claude" / "skills" / "agent-collaboration" / "scripts" / "send_signal.sh"


class ApprovalEventType(Enum):
    """Types of autoresearch approval events."""
    TASK_PROPOSED = "task_proposed"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_DENIED = "approval_denied"
    QUARANTINE_STARTED = "quarantine_started"
    PR_CREATED = "pr_created"
    PR_MERGED = "pr_merged"
    QUARANTINE_VIOLATION = "quarantine_violation"
    AUTONOMOUS_COMMIT = "autonomous_commit"
    ESCALATION_TRIGGERED = "escalation_triggered"


@dataclass
class AutoresearchRequest:
    """An autoresearch approval request."""
    request_id: str
    task_id: str
    agent: str
    title: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    expires_at: Optional[str] = None
    approver: Optional[str] = None
    rejection_reason: Optional[str] = None
    branch: Optional[str] = None
    target_branch: str = "main"
    files_affected: List[str] = field(default_factory=list)
    commit_hashes: List[str] = field(default_factory=list)
    pr_url: Optional[str] = None
    pr_merged_at: Optional[str] = None
    notification_sent: bool = False
    escalation_sent: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d['status'] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AutoresearchRequest":
        data = data.copy()
        if 'status' in data and isinstance(data['status'], str):
            data['status'] = ApprovalStatus(data['status'])
        return cls(**data)


class AutoresearchApproval:
    """
    Manages autoresearch approval workflow.

    Workflow:
    1. propose() — Create approval request, notify Kublai
    2. check_status() — Check if approval granted
    3. approve() — Grant approval (Kublai only)
    4. reject() — Deny approval (Kublai only)
    5. start_quarantine() — Create quarantine branch for work
    6. create_pr() — Create PR after work complete
    7. notify() — Send Signal notifications
    """

    DEFAULT_TIMEOUT_MINUTES = 60
    ESCALATION_TIMEOUT_MINUTES = 120

    def __init__(self, policy_path: Optional[Path] = None):
        self.policy_path = policy_path or POLICY_PATH
        self.state_path = APPROVAL_STATE_PATH
        self._requests: Dict[str, AutoresearchRequest] = {}
        self._policy: Dict = {}
        self._load_policy()
        self._load_state()

    def _load_policy(self) -> None:
        """Load autoresearch policy configuration."""
        if self.policy_path.exists():
            with open(self.policy_path) as f:
                self._policy = json.load(f)
        else:
            self._policy = {
                "enabled_agents": ["mongke", "jochi", "chagatai"],
                "require_human_approval_for": ["main", "master"],
                "auto_approve_safe_paths": ["workspace/**", "memory/*.md"],
                "max_parallel_autonomous_tasks": 3,
            }

    def _load_state(self) -> None:
        """Load existing approval requests."""
        if self.state_path.exists():
            try:
                with open(self.state_path) as f:
                    data = json.load(f)
                self._requests = {
                    req_id: AutoresearchRequest.from_dict(req_data)
                    for req_id, req_data in data.get("autoresearch_requests", {}).items()
                }
            except (json.JSONDecodeError, KeyError):
                self._requests = {}

    def _save_state(self) -> None:
        """Persist approval requests to disk."""
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"autoresearch_requests": {}}
        for req_id, req in self._requests.items():
            data["autoresearch_requests"][req_id] = req.to_dict()

        # Preserve other data in the file
        if self.state_path.exists():
            try:
                with open(self.state_path) as f:
                    existing = json.load(f)
                existing.update(data)
                data = existing
            except:
                pass

        with open(self.state_path, "w") as f:
            json.dump(data, f, indent=2)

    def _generate_request_id(self, task_id: str, agent: str) -> str:
        """Generate unique request ID."""
        timestamp = int(time.time() * 1000)
        hash_input = f"{task_id}:{agent}:{timestamp}"
        hash_suffix = hashlib.md5(hash_input.encode()).hexdigest()[:8]
        return f"ar-{task_id}-{hash_suffix}"

    def _is_agent_enabled(self, agent: str) -> bool:
        """Check if agent is enabled for autoresearch."""
        return agent in self._policy.get("enabled_agents", [])

    def _is_path_auto_approved(self, path: str) -> bool:
        """Check if path is in auto-approve safe paths."""
        import fnmatch
        safe_paths = self._policy.get("auto_approve_safe_paths", [])
        for pattern in safe_paths:
            if fnmatch.fnmatch(path, pattern):
                return True
        return False

    def _requires_human_approval(self, target_branch: str, files: List[str]) -> bool:
        """Check if changes require human approval."""
        import fnmatch
        protected = self._policy.get("require_human_approval_for", [])

        # Check branch
        for pattern in protected:
            if fnmatch.fnmatch(target_branch, pattern):
                return True

        # Check files
        for file_path in files:
            for pattern in protected:
                if fnmatch.fnmatch(file_path, pattern):
                    return True

        return False

    def _send_signal_notification(self, event: ApprovalEventType, request: AutoresearchRequest, extra_message: str = "") -> bool:
        """Send Signal notification for autoresearch events."""
        if not self._policy.get("signal_notifications", {}).get("enabled", True):
            return False

        recipients = self._policy.get("signal_notifications", {}).get("recipients", {})
        primary = recipients.get("primary", "+15165643945")

        # Build notification message
        event_emoji = {
            ApprovalEventType.TASK_PROPOSED: "📋",
            ApprovalEventType.APPROVAL_REQUESTED: "⏳",
            ApprovalEventType.APPROVAL_GRANTED: "✅",
            ApprovalEventType.APPROVAL_DENIED: "❌",
            ApprovalEventType.QUARANTINE_STARTED: "🔒",
            ApprovalEventType.PR_CREATED: "🔗",
            ApprovalEventType.PR_MERGED: "🎉",
            ApprovalEventType.QUARANTINE_VIOLATION: "⚠️",
            ApprovalEventType.AUTONOMOUS_COMMIT: "📝",
            ApprovalEventType.ESCALATION_TRIGGERED: "🚨",
        }

        emoji = event_emoji.get(event, "📢")
        message = f"{emoji} *Autoresearch Alert*\n\n"
        message += f"*Event:* {event.value.replace('_', ' ').title()}\n"
        message += f"*Task:* {request.task_id}\n"
        message += f"*Agent:* {request.agent}\n"
        message += f"*Title:* {request.title}\n"
        message += f"*Status:* {request.status.value}\n"

        if request.branch:
            message += f"*Branch:* {request.branch}\n"
        if request.pr_url:
            message += f"*PR:* {request.pr_url}\n"

        if extra_message:
            message += f"\n{extra_message}"

        if request.status == ApprovalStatus.PENDING:
            expires = request.expires_at or "N/A"
            message += f"\n⏰ Expires: {expires}"

        # Send via signal-cli
        try:
            if SEND_SIGNAL_SCRIPT.exists():
                cmd = ["bash", str(SEND_SIGNAL_SCRIPT), primary, message]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                return result.returncode == 0
            else:
                # Fallback: direct signal-cli call
                cmd = [
                    "signal-cli",
                    "-a", os.getenv("SIGNAL_ACCOUNT", "+15165643945"),
                    "send",
                    "-m", message,
                    primary
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                return result.returncode == 0
        except Exception as e:
            print(f"[AUTORESEARCH] Signal notification failed: {e}", file=sys.stderr)
            return False

    def propose(
        self,
        task_id: str,
        agent: str,
        title: str,
        files: Optional[List[str]] = None,
        target_branch: str = "main",
        details: Optional[Dict] = None
    ) -> Optional[str]:
        """
        Propose an autoresearch task for approval.

        Args:
            task_id: The task ID
            agent: Agent requesting autoresearch
            title: Task title
            files: Files that will be affected
            target_branch: Target branch for merge
            details: Additional details

        Returns:
            request_id if successful, None if rejected by policy
        """
        # Check if agent is enabled
        if not self._is_agent_enabled(agent):
            print(f"[AUTORESEARCH] Agent {agent} not enabled for autoresearch")
            return None

        # Check max parallel tasks
        max_parallel = self._policy.get("max_parallel_autonomous_tasks", 3)
        active_count = sum(
            1 for req in self._requests.values()
            if req.agent == agent and req.status in [ApprovalStatus.PENDING, ApprovalStatus.APPROVED]
        )
        if active_count >= max_parallel:
            print(f"[AUTORESEARCH] Agent {agent} has {active_count} active tasks (max: {max_parallel})")
            return None

        # Generate request ID
        request_id = self._generate_request_id(task_id, agent)

        # Check if human approval required
        requires_approval = self._requires_human_approval(target_branch, files or [])

        # Set expiration
        timeout = self._policy.get("approval_timeout_minutes", self.DEFAULT_TIMEOUT_MINUTES)
        expires_at = (datetime.utcnow() + timedelta(minutes=timeout)).isoformat()

        # Create request
        request = AutoresearchRequest(
            request_id=request_id,
            task_id=task_id,
            agent=agent,
            title=title,
            status=ApprovalStatus.PENDING if requires_approval else ApprovalStatus.APPROVED,
            expires_at=expires_at,
            branch=f"autoresearch/{task_id}",
            target_branch=target_branch,
            files_affected=files or [],
            approver="auto-approved" if not requires_approval else None,
        )

        self._requests[request_id] = request
        self._save_state()

        # Send notifications
        event = ApprovalEventType.TASK_PROPOSED
        self._send_signal_notification(event, request)

        if requires_approval:
            event = ApprovalEventType.APPROVAL_REQUESTED
            extra = f"\n\n*Action Required:* Please review and approve/reject this autoresearch task."
            self._send_signal_notification(event, request, extra)

        print(f"[AUTORESEARCH] Proposed task {task_id} -> request {request_id}")
        return request_id

    def check_status(self, request_id: str) -> Optional[AutoresearchRequest]:
        """Check approval status for a request."""
        request = self._requests.get(request_id)
        if not request:
            return None

        # Check expiration
        if request.status == ApprovalStatus.PENDING and request.expires_at:
            try:
                expires = datetime.fromisoformat(request.expires_at)
                if datetime.utcnow() > expires:
                    request.status = ApprovalStatus.EXPIRED
                    request.updated_at = datetime.utcnow().isoformat()
                    self._save_state()
            except:
                pass

        return request

    def approve(self, request_id: str, approver: str = "kublai") -> bool:
        """
        Approve an autoresearch request.

        Args:
            request_id: The request to approve
            approver: Who is approving (should be kublai)

        Returns:
            True if approved successfully
        """
        request = self._requests.get(request_id)
        if not request:
            print(f"[AUTORESEARCH] Request {request_id} not found")
            return False

        if request.status != ApprovalStatus.PENDING:
            print(f"[AUTORESEARCH] Request {request_id} not pending (status: {request.status.value})")
            return False

        request.status = ApprovalStatus.APPROVED
        request.approver = approver
        request.updated_at = datetime.utcnow().isoformat()
        self._save_state()

        # Send notification
        event = ApprovalEventType.APPROVAL_GRANTED
        extra = f"\n\n*Approved by:* {approver}"
        self._send_signal_notification(event, request, extra)

        print(f"[AUTORESEARCH] Request {request_id} approved by {approver}")
        return True

    def reject(self, request_id: str, approver: str = "kublai", reason: str = "") -> bool:
        """
        Reject an autoresearch request.

        Args:
            request_id: The request to reject
            approver: Who is rejecting
            reason: Rejection reason

        Returns:
            True if rejected successfully
        """
        request = self._requests.get(request_id)
        if not request:
            print(f"[AUTORESEARCH] Request {request_id} not found")
            return False

        if request.status != ApprovalStatus.PENDING:
            print(f"[AUTORESEARCH] Request {request_id} not pending")
            return False

        request.status = ApprovalStatus.REJECTED
        request.approver = approver
        request.rejection_reason = reason
        request.updated_at = datetime.utcnow().isoformat()
        self._save_state()

        # Send notification
        event = ApprovalEventType.APPROVAL_DENIED
        extra = f"\n\n*Rejected by:* {approver}\n*Reason:* {reason}"
        self._send_signal_notification(event, request, extra)

        print(f"[AUTORESEARCH] Request {request_id} rejected by {approver}: {reason}")
        return True

    def start_quarantine(self, request_id: str, working_dir: Optional[str] = None) -> bool:
        """
        Start quarantine branch for approved autoresearch work.

        Args:
            request_id: The approved request
            working_dir: Working directory for git operations

        Returns:
            True if quarantine started successfully
        """
        request = self.check_status(request_id)
        if not request:
            return False

        if request.status != ApprovalStatus.APPROVED:
            print(f"[AUTORESEARCH] Request {request_id} not approved")
            return False

        # Create quarantine branch
        branch_name = request.branch or f"autoresearch/{request.task_id}"

        try:
            cwd = working_dir or os.getcwd()

            # Checkout and create branch
            subprocess.run(["git", "checkout", "-b", branch_name], cwd=cwd, check=True, capture_output=True)

            request.updated_at = datetime.utcnow().isoformat()
            self._save_state()

            # Send notification
            event = ApprovalEventType.QUARANTINE_STARTED
            extra = f"\n\n*Quarantine Branch:* {branch_name}"
            self._send_signal_notification(event, request, extra)

            print(f"[AUTORESEARCH] Quarantine started: {branch_name}")
            return True

        except subprocess.CalledProcessError as e:
            print(f"[AUTORESEARCH] Failed to create quarantine branch: {e}")
            return False

    def create_pr(
        self,
        request_id: str,
        pr_title: Optional[str] = None,
        pr_body: Optional[str] = None,
        working_dir: Optional[str] = None
    ) -> Optional[str]:
        """
        Create pull request for completed autoresearch work.

        Args:
            request_id: The request
            pr_title: PR title (defaults to task title)
            pr_body: PR body/description
            working_dir: Working directory for git operations

        Returns:
            PR URL if successful
        """
        request = self.check_status(request_id)
        if not request:
            return None

        branch_name = request.branch

        try:
            cwd = working_dir or os.getcwd()

            # Use gh CLI to create PR
            title = pr_title or f"[Autoresearch] {request.title}"
            body = pr_body or f"Autoresearch task completed by {request.agent}.\n\nTask ID: {request.task_id}"

            cmd = [
                "gh", "pr", "create",
                "--base", request.target_branch,
                "--head", branch_name,
                "--title", title,
                "--body", body,
                "--label", "autoresearch",
                "--label", "requires-review"
            ]

            result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=True)

            # Extract PR URL from output
            pr_url = result.stdout.strip()
            request.pr_url = pr_url
            request.updated_at = datetime.utcnow().isoformat()
            self._save_state()

            # Send notification
            event = ApprovalEventType.PR_CREATED
            extra = f"\n\n*PR URL:* {pr_url}"
            self._send_signal_notification(event, request, extra)

            print(f"[AUTORESEARCH] PR created: {pr_url}")
            return pr_url

        except subprocess.CalledProcessError as e:
            print(f"[AUTORESEARCH] Failed to create PR: {e.stderr}")
            return None

    def check_autonomous_commit_allowed(self, branch: str, files: List[str]) -> tuple[bool, str]:
        """
        Check if autonomous commit is allowed for given branch and files.

        Args:
            branch: Target branch
            files: Files to commit

        Returns:
            Tuple of (allowed: bool, reason: str)
        """
        # Check if branch is protected
        protected_branches = self._policy.get("completion_gate", {}).get("block_branches", ["main", "master"])
        if branch in protected_branches:
            return False, f"Autonomous commits to {branch} are blocked by completion gate"

        # Check if any files require approval
        for file_path in files:
            if not self._is_path_auto_approved(file_path):
                return False, f"File {file_path} requires human approval"

        return True, "Autonomous commit allowed"

    def escalate(self, request_id: str) -> bool:
        """
        Escalate pending request to Kublai after timeout.

        Args:
            request_id: The request to escalate

        Returns:
            True if escalated successfully
        """
        request = self._requests.get(request_id)
        if not request:
            return False

        if request.status != ApprovalStatus.PENDING:
            return False

        # Check if escalation already sent
        if request.escalation_sent:
            return False

        request.escalation_sent = True
        self._save_state()

        # Send escalation notification
        event = ApprovalEventType.ESCALATION_TRIGGERED
        extra = "\n\n🚨 *ESCALATION:* This request has been pending for over 2 hours."
        self._send_signal_notification(event, request, extra)

        # Create escalation task for Kublai
        try:
            from task_intake import create_task
            create_task(
                title=f"Review pending autoresearch request {request_id}",
                body=f"Autoresearch request {request_id} from {request.agent} has been pending for over 2 hours.\n\nTask: {request.task_id}\nTitle: {request.title}",
                priority="high",
                source="autoresearch-escalation",
                agent="kublai",
            )
        except ImportError:
            pass

        return True


def main():
    """CLI interface for autoresearch approval."""
    import argparse

    parser = argparse.ArgumentParser(description="Autoresearch Approval Flow")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Propose command
    propose_parser = subparsers.add_parser("propose", help="Propose autoresearch task")
    propose_parser.add_argument("--task-id", required=True, help="Task ID")
    propose_parser.add_argument("--agent", required=True, help="Agent name")
    propose_parser.add_argument("--title", required=True, help="Task title")
    propose_parser.add_argument("--files", nargs="*", default=[], help="Files affected")
    propose_parser.add_argument("--target-branch", default="main", help="Target branch")

    # Approve command
    approve_parser = subparsers.add_parser("approve", help="Approve request")
    approve_parser.add_argument("--request-id", required=True, help="Request ID")
    approve_parser.add_argument("--approver", default="kublai", help="Approver name")

    # Reject command
    reject_parser = subparsers.add_parser("reject", help="Reject request")
    reject_parser.add_argument("--request-id", required=True, help="Request ID")
    reject_parser.add_argument("--approver", default="kublai", help="Approver name")
    reject_parser.add_argument("--reason", default="", help="Rejection reason")

    # Status command
    status_parser = subparsers.add_parser("status", help="Check request status")
    status_parser.add_argument("--request-id", required=True, help="Request ID")

    args = parser.parse_args()

    approval = AutoresearchApproval()

    if args.command == "propose":
        request_id = approval.propose(
            task_id=args.task_id,
            agent=args.agent,
            title=args.title,
            files=args.files,
            target_branch=args.target_branch
        )
        if request_id:
            print(f"Request created: {request_id}")
        else:
            print("Failed to create request")
            sys.exit(1)

    elif args.command == "approve":
        if approval.approve(args.request_id, args.approver):
            print(f"Request {args.request_id} approved")
        else:
            print("Failed to approve request")
            sys.exit(1)

    elif args.command == "reject":
        if approval.reject(args.request_id, args.approver, args.reason):
            print(f"Request {args.request_id} rejected")
        else:
            print("Failed to reject request")
            sys.exit(1)

    elif args.command == "status":
        request = approval.check_status(args.request_id)
        if request:
            print(json.dumps(request.to_dict(), indent=2))
        else:
            print("Request not found")
            sys.exit(1)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
