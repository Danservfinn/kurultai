"""
Authentication and authorization for complexity scoring operations.

Provides role-based access control (RBAC) for the Kurultai complexity
scoring system. Operations are gated by agent identity and role allowlists.

Usage:
    from tools.kurultai.complexity_auth import ComplexityAuthenticator

    auth = ComplexityAuthenticator()
    if auth.authorize("kublai", "threshold_adjust"):
        # proceed with threshold adjustment
        ...
"""

import logging
from typing import FrozenSet

logger = logging.getLogger(__name__)

# Known agent IDs in the Kurultai system
KNOWN_AGENTS: FrozenSet[str] = frozenset({
    "kublai", "researcher", "writer", "developer", "analyst", "ops", "system"
})

# Role-based allowlists
THRESHOLD_ADJUST_ROLES: FrozenSet[str] = frozenset({"kublai", "system"})
GROUND_TRUTH_ROLES: FrozenSet[str] = frozenset({"kublai", "analyst"})


class ComplexityAuthenticator:
    """Role-based authorization for complexity scoring operations.

    Supports four operation categories:
      - threshold_adjust: modify classification thresholds (kublai, system only)
      - ground_truth: provide ground-truth labels (kublai, analyst only)
      - classify: run complexity classification (all known agents)
      - read_metrics: read validation metrics (all known agents)

    Unknown agents or unknown operations are rejected and logged.
    """

    def __init__(self, known_agents: FrozenSet[str] | None = None):
        self.known_agents = known_agents or KNOWN_AGENTS

    def authorize(self, agent_id: str, operation: str) -> bool:
        """Check if agent is authorized for the given operation.

        Args:
            agent_id: Identifier of the requesting agent.
            operation: One of "threshold_adjust", "ground_truth",
                       "classify", or "read_metrics".

        Returns:
            True if the agent is permitted to perform the operation.
        """
        if agent_id not in self.known_agents:
            logger.warning(f"Unknown agent '{agent_id}' attempted operation '{operation}'")
            return False

        if operation == "threshold_adjust":
            return agent_id in THRESHOLD_ADJUST_ROLES
        elif operation == "ground_truth":
            return agent_id in GROUND_TRUTH_ROLES
        elif operation == "classify":
            return True  # All known agents can classify
        elif operation == "read_metrics":
            return True  # All known agents can read
        else:
            logger.warning(f"Unknown operation: {operation}")
            return False

    def validate_approved_by(self, approved_by: str) -> bool:
        """Validate that the approver is a known agent.

        Args:
            approved_by: Agent ID claiming to have approved an action.

        Returns:
            True if the approver is in the known agents set.
        """
        return approved_by in self.known_agents
