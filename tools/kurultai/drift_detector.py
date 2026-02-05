"""
Concept Drift Detector for Complexity Scoring System.

Detects distribution shifts in complexity score features using
Population Stability Index (PSI). When drift is detected, thresholds
may need recalibration.

Uses CypherInjectionPrevention.sanitize_property_key() (B5 fix)
to ensure safe Cypher queries when storing drift results in Neo4j.

Author: Claude (Anthropic)
Date: 2026-02-05
"""

import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from tools.security.injection_prevention import (
    CypherInjectionPrevention,
    CypherInjectionError,
)
from tools.kurultai.complexity_auth import ComplexityAuthenticator

logger = logging.getLogger(__name__)


class ConceptDriftDetector:
    """Detects concept drift in complexity scoring features via PSI.

    Population Stability Index (PSI) measures how much a distribution
    has shifted from a reference (training) distribution. Values:
        PSI < 0.1  -> No significant drift
        PSI 0.1-0.2 -> Moderate drift, monitor closely
        PSI > 0.2  -> Significant drift, recalibration needed

    All Neo4j property keys are sanitized through
    CypherInjectionPrevention.sanitize_property_key() and accessed
    via bracket notation c[safe_key] instead of dot notation.
    """

    # PSI interpretation thresholds
    PSI_NO_DRIFT = 0.1
    PSI_MODERATE = 0.2

    def __init__(
        self,
        neo4j_client: Optional[Any] = None,
        authenticator: Optional[ComplexityAuthenticator] = None,
    ):
        """Initialize drift detector.

        Args:
            neo4j_client: Neo4j driver/session for storing results.
                          If None, storage operations become no-ops.
            authenticator: Auth module for role-based access checks.
                           If None, a default instance is created.
        """
        self.neo4j_client = neo4j_client
        self.authenticator = authenticator or ComplexityAuthenticator()

    # ------------------------------------------------------------------
    # Core PSI calculation
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_psi(
        reference_distribution: List[float],
        current_distribution: List[float],
        bins: int = 10,
    ) -> float:
        """Calculate Population Stability Index between two distributions.

        PSI = SUM( (actual_% - expected_%) * ln(actual_% / expected_%) )

        Args:
            reference_distribution: Baseline (expected) data points.
            current_distribution: Current (actual) data points.
            bins: Number of histogram bins for discretisation.

        Returns:
            PSI value (float >= 0). Higher means more drift.

        Raises:
            ValueError: If either distribution is empty or bins < 2.
        """
        if not reference_distribution or not current_distribution:
            raise ValueError("Distributions must not be empty")
        if bins < 2:
            raise ValueError("bins must be >= 2")

        # Build histogram breakpoints from the reference distribution
        min_val = min(min(reference_distribution), min(current_distribution))
        max_val = max(max(reference_distribution), max(current_distribution))

        # Guard against constant distributions
        if max_val == min_val:
            return 0.0

        step = (max_val - min_val) / bins
        breakpoints = [min_val + i * step for i in range(bins + 1)]
        breakpoints[-1] = max_val + 1e-10  # ensure max value falls in last bin

        def _bin_counts(data: List[float]) -> List[int]:
            counts = [0] * bins
            for val in data:
                for i in range(bins):
                    if breakpoints[i] <= val < breakpoints[i + 1]:
                        counts[i] += 1
                        break
            return counts

        ref_counts = _bin_counts(reference_distribution)
        cur_counts = _bin_counts(current_distribution)

        ref_total = len(reference_distribution)
        cur_total = len(current_distribution)

        # Convert to proportions with epsilon to avoid division by zero / log(0)
        epsilon = 1e-6
        ref_pcts = [(c / ref_total) + epsilon for c in ref_counts]
        cur_pcts = [(c / cur_total) + epsilon for c in cur_counts]

        psi = 0.0
        for cur_p, ref_p in zip(cur_pcts, ref_pcts):
            psi += (cur_p - ref_p) * math.log(cur_p / ref_p)

        return psi

    # ------------------------------------------------------------------
    # High-level drift detection
    # ------------------------------------------------------------------

    def detect_drift(
        self,
        feature_name: str,
        reference_data: List[float],
        current_data: List[float],
        threshold: float = 0.2,
    ) -> Dict[str, Any]:
        """Detect concept drift for a named feature.

        Args:
            feature_name: Feature identifier (e.g. "domain_risk").
            reference_data: Baseline distribution.
            current_data: Current distribution.
            threshold: PSI value above which drift is declared.

        Returns:
            dict with keys: feature_name, psi, drifted (bool),
            severity ("none" | "moderate" | "significant"),
            timestamp.
        """
        # Sanitize feature name for safe downstream use in Cypher
        safe_name = CypherInjectionPrevention.sanitize_property_key(feature_name)

        psi = self.calculate_psi(reference_data, current_data)
        drifted = psi > threshold

        if psi < self.PSI_NO_DRIFT:
            severity = "none"
        elif psi < self.PSI_MODERATE:
            severity = "moderate"
        else:
            severity = "significant"

        return {
            "feature_name": safe_name,
            "psi": round(psi, 6),
            "drifted": drifted,
            "severity": severity,
            "threshold": threshold,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # Neo4j persistence
    # ------------------------------------------------------------------

    def store_drift_result(
        self,
        feature_name: str,
        psi_value: float,
        drifted: bool,
        agent_id: str,
    ) -> bool:
        """Store a drift detection result in Neo4j.

        Requires the agent to be authorised for the "drift_store"
        operation via ComplexityAuthenticator.

        Args:
            feature_name: Feature that was evaluated.
            psi_value: Computed PSI value.
            drifted: Whether drift was declared.
            agent_id: Agent requesting the store.

        Returns:
            True if stored successfully, False otherwise.

        Raises:
            PermissionError: If agent_id is not authorised.
            CypherInjectionError: If feature_name contains unsafe chars.
        """
        if not self.authenticator.authorize(agent_id, "ground_truth"):
            raise PermissionError(
                f"Agent '{agent_id}' is not authorised to store drift results"
            )

        # B5 fix: sanitize property key before using in Cypher
        safe_key = CypherInjectionPrevention.sanitize_property_key(feature_name)

        if self.neo4j_client is None:
            logger.warning("No Neo4j client configured; drift result not stored")
            return False

        query = (
            "CREATE (d:DriftResult {"
            "  feature_name: $feature_name,"
            "  psi_value: $psi_value,"
            "  drifted: $drifted,"
            "  agent_id: $agent_id,"
            "  created_at: datetime()"
            "})"
        )

        params = {
            "feature_name": safe_key,
            "psi_value": psi_value,
            "drifted": drifted,
            "agent_id": agent_id,
        }

        try:
            self.neo4j_client.run(query, params)
            logger.info(
                "Stored drift result for feature '%s' (PSI=%.4f, drifted=%s)",
                safe_key,
                psi_value,
                drifted,
            )
            return True
        except Exception:
            logger.exception("Failed to store drift result for '%s'", safe_key)
            return False
