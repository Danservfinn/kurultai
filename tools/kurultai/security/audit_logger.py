"""Audit logger for Kurultai v0.2 security-relevant operations.

Logs priority changes, dependency modifications, and security events
using structured logging for easy parsing and alerting.
"""

import logging
import json
from datetime import datetime, timezone
from typing import Any, Optional


logger = logging.getLogger("kurultai.audit")


class AuditLogger:
    """Structured audit logger for security-relevant task operations.

    Records changes to priority, dependencies, task claims, and security events
    in a structured format suitable for log aggregation and alerting.
    """

    def __init__(self, agent_id: str = "system"):
        self.agent_id = agent_id

    def _emit(self, event_type: str, details: dict) -> dict:
        """Emit a structured audit log entry.

        Returns the log entry dict for testing.
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "agent_id": self.agent_id,
            **details,
        }
        logger.info(json.dumps(entry))
        return entry

    def log_priority_change(
        self, task_id: str, old_weight: float, new_weight: float,
        reason: str = "", override: bool = False
    ) -> dict:
        """Log a priority weight change."""
        return self._emit("priority_change", {
            "task_id": task_id,
            "old_weight": old_weight,
            "new_weight": new_weight,
            "reason": reason,
            "user_override": override,
        })

    def log_dependency_change(
        self, task_id: str, action: str, dependency_id: str,
        dependency_type: str = "hard"
    ) -> dict:
        """Log a dependency addition or removal."""
        return self._emit("dependency_change", {
            "task_id": task_id,
            "action": action,  # "add" or "remove"
            "dependency_id": dependency_id,
            "dependency_type": dependency_type,
        })

    def log_task_claim(self, task_id: str, claimed_by: str) -> dict:
        """Log a task claim event."""
        return self._emit("task_claim", {
            "task_id": task_id,
            "claimed_by": claimed_by,
        })

    def log_security_event(
        self, event: str, severity: str = "info",
        details: Optional[dict] = None
    ) -> dict:
        """Log a security-relevant event."""
        return self._emit("security_event", {
            "event": event,
            "severity": severity,
            "details": details or {},
        })
