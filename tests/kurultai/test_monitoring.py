"""
Test Suite for Phase 4: Production Monitoring Modules.

Tests drift detection, ground truth capture, and threshold adjustment engine.

Run with: pytest tests/kurultai/test_monitoring.py -v
"""

import pytest
from unittest.mock import Mock, MagicMock, call

from tools.security.injection_prevention import CypherInjectionError
from tools.kurultai.complexity_auth import (
    ComplexityAuthenticator,
    THRESHOLD_ADJUST_ROLES,
    GROUND_TRUTH_ROLES,
)
from tools.kurultai.drift_detector import ConceptDriftDetector
from tools.kurultai.ground_truth import GroundTruthCapture
from tools.kurultai.threshold_engine import ThresholdAdjustmentEngine


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def authenticator():
    """Real authenticator for role-based tests."""
    return ComplexityAuthenticator()


@pytest.fixture
def mock_neo4j():
    """Mock Neo4j client with a run() method."""
    client = Mock()
    client.run = Mock(return_value=[])
    return client


@pytest.fixture
def drift_detector(mock_neo4j, authenticator):
    """Drift detector with mocked Neo4j and real auth."""
    return ConceptDriftDetector(
        neo4j_client=mock_neo4j,
        authenticator=authenticator,
    )


@pytest.fixture
def ground_truth(mock_neo4j, authenticator):
    """Ground truth capture with mocked Neo4j and real auth."""
    return GroundTruthCapture(
        neo4j_client=mock_neo4j,
        authenticator=authenticator,
    )


@pytest.fixture
def threshold_engine(mock_neo4j, authenticator):
    """Threshold engine with mocked Neo4j and real auth."""
    return ThresholdAdjustmentEngine(
        neo4j_client=mock_neo4j,
        authenticator=authenticator,
    )


# =============================================================================
# DRIFT DETECTOR TESTS
# =============================================================================

class TestDriftDetector:
    """Tests for ConceptDriftDetector."""

    def test_psi_calculation_no_drift(self):
        """Identical distributions should produce PSI near zero."""
        data = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        psi = ConceptDriftDetector.calculate_psi(data, data, bins=5)
        # Identical distributions -> PSI should be very close to 0
        assert psi < 0.05, f"Expected PSI near 0 for identical distributions, got {psi}"

    def test_psi_calculation_with_drift(self):
        """Clearly different distributions should produce PSI > 0.2."""
        reference = [0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55]
        # Current distribution is shifted high -- significant drift
        current = [0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.92, 0.95, 0.99]
        psi = ConceptDriftDetector.calculate_psi(reference, current, bins=5)
        assert psi > 0.2, f"Expected PSI > 0.2 for drifted distributions, got {psi}"

    def test_psi_empty_distributions_raises(self):
        """Empty distributions should raise ValueError."""
        with pytest.raises(ValueError, match="must not be empty"):
            ConceptDriftDetector.calculate_psi([], [1.0, 2.0])

        with pytest.raises(ValueError, match="must not be empty"):
            ConceptDriftDetector.calculate_psi([1.0, 2.0], [])

    def test_psi_constant_distribution_returns_zero(self):
        """Constant distributions (no variance) should return 0."""
        data = [0.5, 0.5, 0.5, 0.5, 0.5]
        psi = ConceptDriftDetector.calculate_psi(data, data, bins=5)
        assert psi == 0.0

    def test_feature_name_sanitized(self, drift_detector):
        """Feature names with special characters should raise CypherInjectionError."""
        reference = [0.1, 0.2, 0.3, 0.4, 0.5]
        current = [0.1, 0.2, 0.3, 0.4, 0.5]

        with pytest.raises(CypherInjectionError, match="Invalid property key"):
            drift_detector.detect_drift(
                "feature; DROP DATABASE",
                reference,
                current,
            )

    def test_feature_name_with_spaces_raises(self, drift_detector):
        """Feature names with spaces should be rejected."""
        with pytest.raises(CypherInjectionError, match="Invalid property key"):
            drift_detector.detect_drift(
                "bad feature name",
                [0.1, 0.2],
                [0.1, 0.2],
            )

    def test_detect_drift_returns_correct_structure(self, drift_detector):
        """detect_drift returns dict with expected keys."""
        result = drift_detector.detect_drift(
            "domain_risk",
            [0.1, 0.2, 0.3, 0.4, 0.5],
            [0.1, 0.2, 0.3, 0.4, 0.5],
        )
        assert "feature_name" in result
        assert "psi" in result
        assert "drifted" in result
        assert "severity" in result
        assert "threshold" in result
        assert "timestamp" in result
        assert result["feature_name"] == "domain_risk"
        assert result["drifted"] is False

    def test_auth_required_for_store(self, drift_detector):
        """Unauthorized agent cannot store drift results."""
        with pytest.raises(PermissionError, match="not authorised"):
            drift_detector.store_drift_result(
                feature_name="domain_risk",
                psi_value=0.15,
                drifted=False,
                agent_id="unknown_agent",
            )

    def test_authorized_store_succeeds(self, drift_detector, mock_neo4j):
        """Authorized agent (kublai) can store drift results."""
        result = drift_detector.store_drift_result(
            feature_name="domain_risk",
            psi_value=0.15,
            drifted=False,
            agent_id="kublai",
        )
        assert result is True
        mock_neo4j.run.assert_called_once()
        # Verify parameterized query
        args = mock_neo4j.run.call_args
        params = args[0][1]
        assert params["feature_name"] == "domain_risk"
        assert params["psi_value"] == 0.15
        assert params["drifted"] is False
        assert params["agent_id"] == "kublai"

    def test_store_without_neo4j_returns_false(self, authenticator):
        """Store returns False when no Neo4j client is configured."""
        detector = ConceptDriftDetector(
            neo4j_client=None,
            authenticator=authenticator,
        )
        result = detector.store_drift_result(
            feature_name="domain_risk",
            psi_value=0.1,
            drifted=False,
            agent_id="kublai",
        )
        assert result is False

    def test_store_sanitizes_feature_name(self, drift_detector):
        """Feature name with injection attempt is rejected during store."""
        with pytest.raises(CypherInjectionError):
            drift_detector.store_drift_result(
                feature_name="name} RETURN *; //",
                psi_value=0.1,
                drifted=False,
                agent_id="kublai",
            )


# =============================================================================
# GROUND TRUTH CAPTURE TESTS
# =============================================================================

class TestGroundTruthCapture:
    """Tests for GroundTruthCapture."""

    def test_authorized_capture_works(self, ground_truth, mock_neo4j):
        """kublai can capture ground truth overrides."""
        result = ground_truth.capture_user_override(
            task_id="task_001",
            actual_complexity=0.75,
            actual_team_size=3,
            agent_id="kublai",
        )
        assert result is True
        mock_neo4j.run.assert_called_once()
        # Verify parameterized query
        args = mock_neo4j.run.call_args
        params = args[0][1]
        assert params["task_id"] == "task_001"
        assert params["actual_complexity"] == 0.75
        assert params["actual_team_size"] == 3
        assert params["agent_id"] == "kublai"

    def test_unauthorized_capture_rejected(self, ground_truth):
        """Random/unknown agent raises PermissionError."""
        with pytest.raises(PermissionError, match="not authorised"):
            ground_truth.capture_user_override(
                task_id="task_002",
                actual_complexity=0.5,
                actual_team_size=1,
                agent_id="random_agent",
            )

    def test_analyst_can_capture(self, ground_truth, mock_neo4j):
        """analyst is in GROUND_TRUTH_ROLES and can capture."""
        assert "analyst" in GROUND_TRUTH_ROLES
        result = ground_truth.capture_user_override(
            task_id="task_003",
            actual_complexity=0.4,
            actual_team_size=1,
            agent_id="analyst",
        )
        assert result is True
        mock_neo4j.run.assert_called_once()

    def test_developer_cannot_capture(self, ground_truth):
        """developer is a known agent but not in GROUND_TRUTH_ROLES."""
        assert "developer" not in GROUND_TRUTH_ROLES
        with pytest.raises(PermissionError, match="not authorised"):
            ground_truth.capture_user_override(
                task_id="task_004",
                actual_complexity=0.6,
                actual_team_size=2,
                agent_id="developer",
            )

    def test_invalid_complexity_raises(self, ground_truth):
        """Complexity score outside [0, 1] raises ValueError."""
        with pytest.raises(ValueError, match="must be in"):
            ground_truth.capture_user_override(
                task_id="task_005",
                actual_complexity=1.5,
                actual_team_size=1,
                agent_id="kublai",
            )

        with pytest.raises(ValueError, match="must be in"):
            ground_truth.capture_user_override(
                task_id="task_006",
                actual_complexity=-0.1,
                actual_team_size=1,
                agent_id="kublai",
            )

    def test_invalid_team_size_raises(self, ground_truth):
        """Team size < 1 raises ValueError."""
        with pytest.raises(ValueError, match="must be >= 1"):
            ground_truth.capture_user_override(
                task_id="task_007",
                actual_complexity=0.5,
                actual_team_size=0,
                agent_id="kublai",
            )

    def test_get_overrides_empty_without_neo4j(self, authenticator):
        """get_overrides returns empty list when no Neo4j client."""
        gt = GroundTruthCapture(neo4j_client=None, authenticator=authenticator)
        result = gt.get_overrides()
        assert result == []

    def test_get_overrides_returns_records(self, ground_truth, mock_neo4j):
        """get_overrides returns records from Neo4j."""
        mock_record = Mock()
        mock_record.__getitem__ = Mock(return_value={
            "task_id": "task_001",
            "actual_complexity": 0.75,
            "actual_team_size": 3,
            "agent_id": "kublai",
            "created_at": "2026-02-05T12:00:00Z",
        })
        mock_neo4j.run.return_value = [mock_record]

        records = ground_truth.get_overrides(limit=10)
        assert len(records) == 1
        assert records[0]["task_id"] == "task_001"
        assert records[0]["actual_complexity"] == 0.75


# =============================================================================
# THRESHOLD ADJUSTMENT ENGINE TESTS
# =============================================================================

class TestThresholdAdjustmentEngine:
    """Tests for ThresholdAdjustmentEngine."""

    def test_authorized_adjustment_works(self, threshold_engine, mock_neo4j):
        """kublai can adjust thresholds."""
        result = threshold_engine.apply_threshold_adjustment(
            lower=0.55,
            upper=0.85,
            approved_by="kublai",
            reason="Recalibration after drift detection",
        )
        assert result is True
        mock_neo4j.run.assert_called_once()

    def test_unauthorized_adjustment_rejected(self, threshold_engine):
        """developer raises PermissionError for threshold adjustment."""
        with pytest.raises(PermissionError):
            threshold_engine.apply_threshold_adjustment(
                lower=0.55,
                upper=0.85,
                approved_by="developer",
                reason="Unauthorized attempt",
            )

    def test_unknown_agent_rejected(self, threshold_engine):
        """Unknown agent (not in KNOWN_AGENTS) is rejected."""
        with pytest.raises(PermissionError, match="not authorised"):
            threshold_engine.apply_threshold_adjustment(
                lower=0.55,
                upper=0.85,
                approved_by="hacker",
                reason="Malicious attempt",
            )

    def test_system_can_adjust(self, threshold_engine, mock_neo4j):
        """system is in THRESHOLD_ADJUST_ROLES and can adjust."""
        assert "system" in THRESHOLD_ADJUST_ROLES
        result = threshold_engine.apply_threshold_adjustment(
            lower=0.5,
            upper=0.8,
            approved_by="system",
            reason="Automated recalibration",
        )
        assert result is True
        mock_neo4j.run.assert_called_once()

    def test_audit_trail_stored(self, threshold_engine, mock_neo4j):
        """Verify Neo4j query parameters form a complete audit trail."""
        threshold_engine.apply_threshold_adjustment(
            lower=0.55,
            upper=0.85,
            approved_by="kublai",
            reason="PSI > 0.2 detected on domain_risk",
        )

        mock_neo4j.run.assert_called_once()
        args = mock_neo4j.run.call_args
        query = args[0][0]
        params = args[0][1]

        # Verify all audit fields are present in params
        assert params["lower"] == 0.55
        assert params["upper"] == 0.85
        assert params["approved_by"] == "kublai"
        assert params["reason"] == "PSI > 0.2 detected on domain_risk"

        # Verify query creates a ThresholdAdjustment node
        assert "ThresholdAdjustment" in query
        assert "$lower" in query
        assert "$upper" in query
        assert "$approved_by" in query
        assert "$reason" in query

    def test_invalid_thresholds_rejected(self, threshold_engine):
        """Invalid threshold values are rejected."""
        # lower >= upper
        with pytest.raises(ValueError, match="0 < lower < upper < 1"):
            threshold_engine.apply_threshold_adjustment(
                lower=0.85,
                upper=0.55,
                approved_by="kublai",
                reason="Bad thresholds",
            )

        # lower == upper
        with pytest.raises(ValueError, match="0 < lower < upper < 1"):
            threshold_engine.apply_threshold_adjustment(
                lower=0.6,
                upper=0.6,
                approved_by="kublai",
                reason="Equal thresholds",
            )

        # lower <= 0
        with pytest.raises(ValueError, match="0 < lower < upper < 1"):
            threshold_engine.apply_threshold_adjustment(
                lower=0.0,
                upper=0.8,
                approved_by="kublai",
                reason="Zero lower",
            )

        # upper >= 1
        with pytest.raises(ValueError, match="0 < lower < upper < 1"):
            threshold_engine.apply_threshold_adjustment(
                lower=0.5,
                upper=1.0,
                approved_by="kublai",
                reason="Upper at boundary",
            )

    def test_empty_reason_rejected(self, threshold_engine):
        """Empty or whitespace-only reason is rejected."""
        with pytest.raises(ValueError, match="non-empty reason"):
            threshold_engine.apply_threshold_adjustment(
                lower=0.5,
                upper=0.8,
                approved_by="kublai",
                reason="",
            )

        with pytest.raises(ValueError, match="non-empty reason"):
            threshold_engine.apply_threshold_adjustment(
                lower=0.5,
                upper=0.8,
                approved_by="kublai",
                reason="   ",
            )

    def test_get_history_empty_without_neo4j(self, authenticator):
        """get_adjustment_history returns empty list when no Neo4j client."""
        engine = ThresholdAdjustmentEngine(
            neo4j_client=None,
            authenticator=authenticator,
        )
        result = engine.get_adjustment_history()
        assert result == []

    def test_get_history_returns_records(self, threshold_engine, mock_neo4j):
        """get_adjustment_history returns records from Neo4j."""
        mock_record = Mock()
        mock_record.__getitem__ = Mock(return_value={
            "lower_threshold": 0.55,
            "upper_threshold": 0.85,
            "approved_by": "kublai",
            "reason": "Drift detected",
            "created_at": "2026-02-05T12:00:00Z",
        })
        mock_neo4j.run.return_value = [mock_record]

        records = threshold_engine.get_adjustment_history(limit=5)
        assert len(records) == 1
        assert records[0]["approved_by"] == "kublai"
        assert records[0]["lower_threshold"] == 0.55
