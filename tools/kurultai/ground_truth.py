"""
Ground Truth Capture for Complexity Scoring System.

Allows authorised agents to record user-provided overrides of complexity
scores and team sizes. These overrides feed into model recalibration
and validation pipelines.

Author: Claude (Anthropic)
Date: 2026-02-05
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from tools.kurultai.complexity_auth import ComplexityAuthenticator

logger = logging.getLogger(__name__)


class GroundTruthCapture:
    """Captures human-verified complexity scores for model feedback.

    Only agents in GROUND_TRUTH_ROLES (kublai, analyst) may write
    ground truth records. All Neo4j queries use parameterised values.
    """

    def __init__(
        self,
        neo4j_client: Optional[Any] = None,
        authenticator: ComplexityAuthenticator = None,
    ):
        """Initialize ground truth capture.

        Args:
            neo4j_client: Neo4j driver/session. If None, storage is a no-op.
            authenticator: Required auth module for role checks.
                           If None, a default instance is created.
        """
        self.neo4j_client = neo4j_client
        self.authenticator = authenticator or ComplexityAuthenticator()

    # ------------------------------------------------------------------
    # Write path
    # ------------------------------------------------------------------

    def capture_user_override(
        self,
        task_id: str,
        actual_complexity: float,
        actual_team_size: int,
        agent_id: str,
    ) -> bool:
        """Record a human-verified complexity override.

        Args:
            task_id: Unique identifier for the task being overridden.
            actual_complexity: The human-assessed complexity score [0, 1].
            actual_team_size: The correct team size (number of agents).
            agent_id: Agent submitting the override.

        Returns:
            True if the override was stored successfully.

        Raises:
            PermissionError: If agent_id is not in GROUND_TRUTH_ROLES.
            ValueError: If actual_complexity is outside [0, 1].
        """
        if not self.authenticator.authorize(agent_id, "ground_truth"):
            raise PermissionError(
                f"Agent '{agent_id}' is not authorised for ground truth capture"
            )

        if not (0.0 <= actual_complexity <= 1.0):
            raise ValueError(
                f"actual_complexity must be in [0, 1], got {actual_complexity}"
            )

        if actual_team_size < 1:
            raise ValueError(
                f"actual_team_size must be >= 1, got {actual_team_size}"
            )

        if self.neo4j_client is None:
            logger.warning("No Neo4j client configured; override not stored")
            return False

        query = (
            "CREATE (gt:GroundTruth {"
            "  task_id: $task_id,"
            "  actual_complexity: $actual_complexity,"
            "  actual_team_size: $actual_team_size,"
            "  agent_id: $agent_id,"
            "  created_at: datetime()"
            "})"
        )

        params = {
            "task_id": task_id,
            "actual_complexity": actual_complexity,
            "actual_team_size": actual_team_size,
            "agent_id": agent_id,
        }

        try:
            self.neo4j_client.run(query, params)
            logger.info(
                "Captured ground truth for task '%s': "
                "complexity=%.2f, team_size=%d (by %s)",
                task_id,
                actual_complexity,
                actual_team_size,
                agent_id,
            )
            return True
        except Exception:
            logger.exception(
                "Failed to store ground truth for task '%s'", task_id
            )
            return False

    # ------------------------------------------------------------------
    # Read path
    # ------------------------------------------------------------------

    def get_overrides(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieve stored ground truth overrides.

        Args:
            limit: Maximum number of records to return.

        Returns:
            List of override dicts, newest first.
        """
        if self.neo4j_client is None:
            logger.warning("No Neo4j client configured; returning empty list")
            return []

        query = (
            "MATCH (gt:GroundTruth) "
            "RETURN gt "
            "ORDER BY gt.created_at DESC "
            "LIMIT $limit"
        )

        try:
            result = self.neo4j_client.run(query, {"limit": limit})
            records = []
            for record in result:
                node = record["gt"]
                records.append({
                    "task_id": node["task_id"],
                    "actual_complexity": node["actual_complexity"],
                    "actual_team_size": node["actual_team_size"],
                    "agent_id": node["agent_id"],
                    "created_at": str(node.get("created_at", "")),
                })
            return records
        except Exception:
            logger.exception("Failed to retrieve ground truth overrides")
            return []
