"""
Threshold Adjustment Engine for Complexity Scoring System.

Provides audited, role-gated threshold adjustments with a full
audit trail stored in Neo4j. Only agents in THRESHOLD_ADJUST_ROLES
(kublai, system) may modify thresholds.

Author: Claude (Anthropic)
Date: 2026-02-05
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from tools.kurultai.complexity_auth import ComplexityAuthenticator

logger = logging.getLogger(__name__)


class ThresholdAdjustmentEngine:
    """Manages audited threshold adjustments for complexity scoring.

    Every adjustment is stored in Neo4j with the full context:
    who approved it, what the new bounds are, and why it was made.
    This provides a complete audit trail for compliance and debugging.
    """

    def __init__(
        self,
        neo4j_client: Optional[Any] = None,
        authenticator: ComplexityAuthenticator = None,
    ):
        """Initialize threshold adjustment engine.

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

    def apply_threshold_adjustment(
        self,
        lower: float,
        upper: float,
        approved_by: str,
        reason: str,
    ) -> bool:
        """Apply a threshold adjustment with audit trail.

        Args:
            lower: New lower threshold (individual_threshold).
            upper: New upper threshold (small_team_threshold).
            approved_by: Agent/role that approved the adjustment.
            reason: Human-readable justification.

        Returns:
            True if the adjustment was stored successfully.

        Raises:
            PermissionError: If approved_by is not authorised.
            ValueError: If thresholds are invalid.
        """
        # Validate the approver against known roles
        if not self.authenticator.validate_approved_by(approved_by):
            raise PermissionError(
                f"Agent '{approved_by}' is not authorised to adjust thresholds"
            )

        if not self.authenticator.authorize(approved_by, "threshold_adjust"):
            raise PermissionError(
                f"Agent '{approved_by}' lacks threshold_adjust permission"
            )

        # Validate threshold values
        if not (0.0 < lower < upper < 1.0):
            raise ValueError(
                f"Thresholds must satisfy 0 < lower < upper < 1, "
                f"got lower={lower}, upper={upper}"
            )

        if not reason or not reason.strip():
            raise ValueError("A non-empty reason is required for audit trail")

        if self.neo4j_client is None:
            logger.warning(
                "No Neo4j client configured; threshold adjustment not stored"
            )
            return False

        query = (
            "CREATE (ta:ThresholdAdjustment {"
            "  lower_threshold: $lower,"
            "  upper_threshold: $upper,"
            "  approved_by: $approved_by,"
            "  reason: $reason,"
            "  created_at: datetime()"
            "})"
        )

        params = {
            "lower": lower,
            "upper": upper,
            "approved_by": approved_by,
            "reason": reason,
        }

        try:
            self.neo4j_client.run(query, params)
            logger.info(
                "Threshold adjustment applied: lower=%.3f, upper=%.3f "
                "(approved by %s: %s)",
                lower,
                upper,
                approved_by,
                reason,
            )
            return True
        except Exception:
            logger.exception("Failed to store threshold adjustment")
            return False

    # ------------------------------------------------------------------
    # Read path
    # ------------------------------------------------------------------

    def get_adjustment_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Retrieve threshold adjustment audit trail.

        Args:
            limit: Maximum number of records to return.

        Returns:
            List of adjustment dicts, newest first.
        """
        if self.neo4j_client is None:
            logger.warning("No Neo4j client configured; returning empty list")
            return []

        query = (
            "MATCH (ta:ThresholdAdjustment) "
            "RETURN ta "
            "ORDER BY ta.created_at DESC "
            "LIMIT $limit"
        )

        try:
            result = self.neo4j_client.run(query, {"limit": limit})
            records = []
            for record in result:
                node = record["ta"]
                records.append({
                    "lower_threshold": node["lower_threshold"],
                    "upper_threshold": node["upper_threshold"],
                    "approved_by": node["approved_by"],
                    "reason": node["reason"],
                    "created_at": str(node.get("created_at", "")),
                })
            return records
        except Exception:
            logger.exception("Failed to retrieve adjustment history")
            return []
