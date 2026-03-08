#!/usr/bin/env python3
"""
Approval Workflow for Kurultai Experiments

Provides human-in-the-loop approval for high-risk changes:
- Request approval with change details
- Check approval status
- Emergency bypass with rate limiting

Usage:
    from approval_workflow import ApprovalWorkflow

    workflow = ApprovalWorkflow()
    request = workflow.request_approval("exp-001", "api_change", details)
    if workflow.check_approval("exp-001").approved:
        # Proceed with merge
"""

import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional

import yaml

# Paths
APPROVAL_STATE_PATH = Path(__file__).parent.parent.parent / "config" / "approval_requests.json"
PROTECTED_BRANCHES_PATH = Path(__file__).parent.parent.parent / "config" / "protected_branches.yaml"


class ApprovalStatus(Enum):
    """Status of an approval request."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    BYPASSED = "bypassed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ChangeType(Enum):
    """Types of changes requiring approval."""
    CONFIG_TUNING = "config_tuning"
    UTILITY_CODE = "utility_code"
    API_CHANGE = "api_change"
    DATABASE_SCHEMA = "database_schema"
    SECURITY_SENSITIVE = "security_sensitive"
    AGENT_BEHAVIOR = "agent_behavior"
    CRON_JOBS = "cron_jobs"
    FEATURE_FLAGS = "feature_flags"
    UNKNOWN = "unknown"


@dataclass
class ApprovalRequest:
    """A request for human approval."""
    request_id: str
    experiment_id: str
    change_type: ChangeType
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    expires_at: Optional[str] = None
    approver: Optional[str] = None
    bypass_reason: Optional[str] = None
    details: dict = field(default_factory=dict)

    # Change details
    branch: Optional[str] = None
    target_branch: Optional[str] = None
    files_changed: list = field(default_factory=list)
    commit_message: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "experiment_id": self.experiment_id,
            "change_type": self.change_type.value,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "expires_at": self.expires_at,
            "approver": self.approver,
            "bypass_reason": self.bypass_reason,
            "details": self.details,
            "branch": self.branch,
            "target_branch": self.target_branch,
            "files_changed": self.files_changed,
            "commit_message": self.commit_message,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ApprovalRequest":
        return cls(
            request_id=data["request_id"],
            experiment_id=data["experiment_id"],
            change_type=ChangeType(data.get("change_type", "unknown")),
            status=ApprovalStatus(data.get("status", "pending")),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
            updated_at=data.get("updated_at", datetime.utcnow().isoformat()),
            expires_at=data.get("expires_at"),
            approver=data.get("approver"),
            bypass_reason=data.get("bypass_reason"),
            details=data.get("details", {}),
            branch=data.get("branch"),
            target_branch=data.get("target_branch"),
            files_changed=data.get("files_changed", []),
            commit_message=data.get("commit_message"),
        )


class ApprovalWorkflow:
    """
    Manages human approval workflow for experiments.

    Workflow:
    1. request_approval() - Create approval request, notify humans
    2. check_approval() - Check if approval granted
    3. bypass_approval() - Emergency bypass (rate limited)
    """

    DEFAULT_TIMEOUT_MINUTES = 60
    BYPASS_RATE_LIMIT_PER_DAY = 2

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or APPROVAL_STATE_PATH
        self._requests: dict[str, ApprovalRequest] = {}
        self._bypass_count_today: int = 0
        self._bypass_reset_date: str = ""
        self._approval_rules: dict = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load approval requests and protected branches config."""
        # Load existing requests
        if self.config_path.exists():
            try:
                with open(self.config_path) as f:
                    data = json.load(f)
                self._requests = {
                    req_id: ApprovalRequest.from_dict(req_data)
                    for req_id, req_data in data.get("requests", {}).items()
                }
                self._bypass_count_today = data.get("bypass_count_today", 0)
                self._bypass_reset_date = data.get("bypass_reset_date", "")
            except (json.JSONDecodeError, KeyError):
                self._requests = {}

        # Load approval rules from protected branches config
        if PROTECTED_BRANCHES_PATH.exists():
            try:
                with open(PROTECTED_BRANCHES_PATH) as f:
                    config = yaml.safe_load(f)
                self._approval_rules = config.get("approval_rules", {})
            except (yaml.YAMLError, KeyError):
                self._approval_rules = {}

        # Reset bypass count on new day
        today = datetime.utcnow().strftime("%Y-%m-%d")
        if self._bypass_reset_date != today:
            self._bypass_count_today = 0
            self._bypass_reset_date = today

    def _save_config(self) -> None:
        """Persist approval requests to disk."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "requests": {
                req_id: req.to_dict()
                for req_id, req in self._requests.items()
            },
            "bypass_count_today": self._bypass_count_today,
            "bypass_reset_date": self._bypass_reset_date,
        }
        with open(self.config_path, "w") as f:
            json.dump(data, f, indent=2)

    def _classify_change_type(self, files_changed: list[str]) -> ChangeType:
        """Classify change type based on file patterns."""
        for file_path in files_changed:
            file_lower = file_path.lower()

            # Security-sensitive patterns
            if any(p in file_lower for p in ["auth", "security", "secret", "credential"]):
                return ChangeType.SECURITY_SENSITIVE

            # Database schema
            if any(p in file_lower for p in ["migration", "schema", "models"]):
                return ChangeType.DATABASE_SCHEMA

            # API changes
            if any(p in file_lower for p in ["api", "routes", "endpoints"]):
                return ChangeType.API_CHANGE

            # Cron jobs
            if any(p in file_lower for p in ["cron", "jobs.json"]):
                return ChangeType.CRON_JOBS

            # Agent behavior
            if any(p in file_lower for p in ["claude.md", "prompts", "config.json"]):
                return ChangeType.AGENT_BEHAVIOR

            # Config
            if any(p in file_lower for p in ["config", "env"]):
                return ChangeType.CONFIG_TUNING

        return ChangeType.UNKNOWN

    def _get_approval_requirements(self, change_type: ChangeType) -> dict:
        """Get approval requirements for a change type."""
        rule = self._approval_rules.get(change_type.value, {})
        return {
            "auto_merge": rule.get("auto_merge", False),
            "approval": rule.get("approval", "optional"),
            "approvers": rule.get("approvers", 1),
        }

    def request_approval(
        self,
        experiment_id: str,
        change_type: str,
        details: dict,
        files_changed: Optional[list[str]] = None,
        branch: Optional[str] = None,
        target_branch: Optional[str] = "main",
    ) -> ApprovalRequest:
        """
        Create an approval request and notify humans.

        Args:
            experiment_id: The experiment requesting approval
            change_type: Type of change (api_change, database_schema, etc.)
            details: Additional details about the change
            files_changed: List of files that will be changed
            branch: Source branch
            target_branch: Target branch for merge

        Returns:
            ApprovalRequest with pending status
        """
        # Classify change type
        if files_changed and change_type == "unknown":
            ct = self._classify_change_type(files_changed)
        else:
            try:
                ct = ChangeType(change_type)
            except ValueError:
                ct = ChangeType.UNKNOWN

        # Generate request ID
        request_id = f"apr-{experiment_id}-{int(time.time())}"

        # Set expiration
        expires_at = (datetime.utcnow() + timedelta(minutes=self.DEFAULT_TIMEOUT_MINUTES)).isoformat()

        # Create request
        request = ApprovalRequest(
            request_id=request_id,
            experiment_id=experiment_id,
            change_type=ct,
            status=ApprovalStatus.PENDING,
            expires_at=expires_at,
            details=details,
            branch=branch,
            target_branch=target_branch,
            files_changed=files_changed or [],
        )

        self._requests[request_id] = request
        self._save_config()

        # Check if approval is even required
        requirements = self._get_approval_requirements(ct)
        if requirements["approval"] == "optional" and requirements["auto_merge"]:
            # Auto-approve for low-risk changes
            request.status = ApprovalStatus.APPROVED
            request.approver = "auto-approved"
            self._save_config()
            return request

        # Notify humans
        self._send_approval_notification(request, requirements)

        return request

    def check_approval(self, experiment_id: str) -> ApprovalRequest:
        """
        Check if approval has been granted for an experiment.

        Also checks for expiration.

        Args:
            experiment_id: The experiment to check

        Returns:
            ApprovalRequest with current status
        """
        # Find request for this experiment
        request = None
        for req in self._requests.values():
            if req.experiment_id == experiment_id and req.status == ApprovalStatus.PENDING:
                request = req
                break

        if request is None:
            # No pending request found
            return ApprovalRequest(
                request_id="not-found",
                experiment_id=experiment_id,
                change_type=ChangeType.UNKNOWN,
                status=ApprovalStatus.CANCELLED,
            )

        # Check expiration
        if request.expires_at:
            expires = datetime.fromisoformat(request.expires_at)
            if datetime.utcnow() > expires:
                request.status = ApprovalStatus.EXPIRED
                self._save_config()
                return request

        # Check for external approval (from Signal response, etc.)
        # In a real implementation, this would check Signal/Slack/etc.
        approval_response = self._check_external_approval(request.request_id)
        if approval_response:
            if approval_response.get("approved"):
                request.status = ApprovalStatus.APPROVED
                request.approver = approval_response.get("approver", "unknown")
            elif approval_response.get("rejected"):
                request.status = ApprovalStatus.REJECTED
                request.approver = approval_response.get("approver", "unknown")
            request.updated_at = datetime.utcnow().isoformat()
            self._save_config()

        return request

    def bypass_approval(self, experiment_id: str, reason: str) -> bool:
        """
        Emergency bypass of approval process.

        Rate limited to prevent abuse. All bypasses are logged.

        Args:
            experiment_id: The experiment to bypass
            reason: Human-readable reason for bypass

        Returns:
            True if bypass succeeded, False if rate limited
        """
        # Check rate limit
        if self._bypass_count_today >= self.BYPASS_RATE_LIMIT_PER_DAY:
            self._log_bypass_denied(experiment_id, reason)
            return False

        # Find pending request
        request = None
        for req in self._requests.values():
            if req.experiment_id == experiment_id and req.status == ApprovalStatus.PENDING:
                request = req
                break

        if request is None:
            return False

        # Apply bypass
        request.status = ApprovalStatus.BYPASSED
        request.bypass_reason = reason
        request.approver = "emergency-bypass"
        request.updated_at = datetime.utcnow().isoformat()

        self._bypass_count_today += 1
        self._save_config()

        # Log bypass
        self._log_bypass(request, reason)

        # Notify humans about bypass
        self._send_bypass_notification(request, reason)

        return True

    def approve_request(self, request_id: str, approver: str) -> bool:
        """
        Manually approve a request (called from external system).

        Args:
            request_id: The request to approve
            approver: Who approved it

        Returns:
            True if approval succeeded
        """
        if request_id not in self._requests:
            return False

        request = self._requests[request_id]
        if request.status != ApprovalStatus.PENDING:
            return False

        request.status = ApprovalStatus.APPROVED
        request.approver = approver
        request.updated_at = datetime.utcnow().isoformat()
        self._save_config()

        return True

    def reject_request(self, request_id: str, approver: str, reason: str) -> bool:
        """
        Reject an approval request.

        Args:
            request_id: The request to reject
            approver: Who rejected it
            reason: Why it was rejected

        Returns:
            True if rejection succeeded
        """
        if request_id not in self._requests:
            return False

        request = self._requests[request_id]
        if request.status != ApprovalStatus.PENDING:
            return False

        request.status = ApprovalStatus.REJECTED
        request.approver = approver
        request.details["rejection_reason"] = reason
        request.updated_at = datetime.utcnow().isoformat()
        self._save_config()

        return True

    def list_pending_approvals(self) -> list[ApprovalRequest]:
        """List all pending approval requests."""
        return [
            req for req in self._requests.values()
            if req.status == ApprovalStatus.PENDING
        ]

    def _send_approval_notification(self, request: ApprovalRequest, requirements: dict) -> None:
        """Send notification about approval request."""
        message = f"""APPROVAL REQUEST

Experiment: {request.experiment_id}
Change Type: {request.change_type.value}
Target Branch: {request.target_branch}

Files Changed:
{chr(10).join(f'  - {f}' for f in request.files_changed[:10])}
{f'  ... and {len(request.files_changed) - 10} more' if len(request.files_changed) > 10 else ''}

Details:
{request.details.get('description', 'No description provided')}

Required Approvers: {requirements.get('approvers', 1)}

Reply with:
  APPROVE {request.request_id}
  or
  REJECT {request.request_id} <reason>
"""

        self._send_signal_notification(message)

    def _send_bypass_notification(self, request: ApprovalRequest, reason: str) -> None:
        """Send notification about emergency bypass."""
        message = f"""EMERGENCY BYPASS USED

Experiment: {request.experiment_id}
Request ID: {request.request_id}
Reason: {reason}

Bypasses used today: {self._bypass_count_today}/{self.BYPASS_RATE_LIMIT_PER_DAY}

This bypass has been logged and will be reviewed.
"""
        self._send_signal_notification(message)

    def _send_signal_notification(self, message: str) -> None:
        """Send notification via Signal."""
        try:
            # Try Signal CLI if available
            result = subprocess.run(
                ["signal-cli", "-u", "+15165643945", "send", "-m", message, "+15165643945"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                print(f"[Signal] Notification failed: {result.stderr}")
        except FileNotFoundError:
            # Signal CLI not available, log instead
            print(f"[Approval Notification] {message[:200]}...")
        except subprocess.TimeoutExpired:
            print("[Signal] Notification timed out")

    def _check_external_approval(self, request_id: str) -> Optional[dict]:
        """
        Check for external approval response.

        In production, this would check Signal/Slack responses.
        Returns None if no response yet.
        """
        # TODO: Implement Signal response checking
        # For now, always return None (pending)
        return None

    def _log_bypass(self, request: ApprovalRequest, reason: str) -> None:
        """Log bypass to Neo4j and local file."""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "event": "approval_bypass",
            "request_id": request.request_id,
            "experiment_id": request.experiment_id,
            "reason": reason,
        }

        # Log to file
        log_path = Path(__file__).parent.parent.parent / "logs" / "approval_bypasses.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as f:
            f.write(json.dumps(log_entry) + "\n")

        # TODO: Log to Neo4j

    def _log_bypass_denied(self, experiment_id: str, reason: str) -> None:
        """Log denied bypass attempt."""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "event": "bypass_denied_rate_limit",
            "experiment_id": experiment_id,
            "reason": reason,
            "bypasses_today": self._bypass_count_today,
        }

        log_path = Path(__file__).parent.parent.parent / "logs" / "approval_bypasses.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as f:
            f.write(json.dumps(log_entry) + "\n")


if __name__ == "__main__":
    print("Approval Workflow Demo")
    print("=" * 50)

    workflow = ApprovalWorkflow()

    # Create an approval request
    print("\n1. Creating approval request...")
    request = workflow.request_approval(
        experiment_id="exp-demo-001",
        change_type="api_change",
        details={"description": "Test API change for demo"},
        files_changed=["api/routes/tasks.py", "api/endpoints/tasks.py"],
        branch="experiment/temujin/exp-demo-001/api-test",
        target_branch="main",
    )

    print(f"Request ID: {request.request_id}")
    print(f"Status: {request.status.value}")
    print(f"Change Type: {request.change_type.value}")

    # Check approval
    print("\n2. Checking approval status...")
    status = workflow.check_approval("exp-demo-001")
    print(f"Status: {status.status.value}")

    # List pending
    print("\n3. Listing pending approvals...")
    pending = workflow.list_pending_approvals()
    print(f"Pending requests: {len(pending)}")

    # Test bypass
    print("\n4. Testing emergency bypass...")
    bypassed = workflow.bypass_approval("exp-demo-001", "Emergency deployment needed")
    print(f"Bypass succeeded: {bypassed}")

    # Check final status
    status = workflow.check_approval("exp-demo-001")
    print(f"Final status: {status.status.value}")
    if status.bypass_reason:
        print(f"Bypass reason: {status.bypass_reason}")