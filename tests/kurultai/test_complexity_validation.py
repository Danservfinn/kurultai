"""
Test Suite for Complexity Validation Framework

Tests the validation framework components including:
- Test case library
- Metrics calculation
- Threshold calibration
- Production monitoring

Run with: pytest tests/kurultai/test_complexity_validation.py -v
"""

import pytest
import numpy as np
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, AsyncMock

from tools.kurultai.complexity_validation_framework import (
    # Enums
    CapabilityDomain,
    TeamSize,
    TestCaseCategory as CaseCategory,
    ValidationStatus,

    # Data classes — aliased to avoid pytest collection (classes named Test*)
    ComplexityFactors,
    TestCase as VTestCase,
    TestResult as VTestResult,
    ValidationMetrics,
    ThresholdCalibration,
    ProductionMetrics,

    # Classes
    TestCaseLibrary as CaseLibrary,
    ComplexityValidationFramework,
    ThresholdCalibrator,
    ProductionMonitor,
    StagingValidationPipeline,

    # Functions
    create_validation_suite,
    run_quick_validation,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def sample_complexity_factors():
    """Sample complexity factors for testing."""
    return ComplexityFactors(
        domain_risk=0.5,
        api_count=3,
        integration_points=2,
        security_sensitivity=0.4,
        data_volume_gb=50,
        concurrency_requirements=100
    )


@pytest.fixture
def sample_test_case(sample_complexity_factors):
    """Sample test case for testing."""
    return VTestCase(
        id="test_001",
        name="Sample Test Case",
        capability_request="Build a REST API with authentication",
        expected_complexity=0.65,
        expected_team_size=TeamSize.SMALL_TEAM,
        domain=CapabilityDomain.INFRASTRUCTURE,
        category=CaseCategory.DOMAIN_SPECIFIC,
        factors=sample_complexity_factors,
        description="Test case for validation framework",
        tags=["api", "auth"]
    )


@pytest.fixture
def mock_classifier():
    """Mock classifier for testing."""
    classifier = Mock()
    classifier.classify = Mock(return_value={
        "complexity": 0.65,
        "token_usage": 500,
        "metadata": {"confidence": 0.85}
    })
    return classifier


@pytest.fixture
def sample_test_results():
    """Generate sample test results for metrics testing."""
    results = []

    # Create results with known patterns
    test_cases = [
        # Individual cases (correctly classified)
        ("ind_1", 0.3, TeamSize.INDIVIDUAL, 0.32, TeamSize.INDIVIDUAL),
        ("ind_2", 0.4, TeamSize.INDIVIDUAL, 0.38, TeamSize.INDIVIDUAL),
        ("ind_3", 0.5, TeamSize.INDIVIDUAL, 0.52, TeamSize.INDIVIDUAL),

        # Small team cases (correctly classified)
        ("small_1", 0.65, TeamSize.SMALL_TEAM, 0.67, TeamSize.SMALL_TEAM),
        ("small_2", 0.7, TeamSize.SMALL_TEAM, 0.68, TeamSize.SMALL_TEAM),
        ("small_3", 0.75, TeamSize.SMALL_TEAM, 0.73, TeamSize.SMALL_TEAM),

        # Full team cases (correctly classified)
        ("full_1", 0.85, TeamSize.FULL_TEAM, 0.87, TeamSize.FULL_TEAM),
        ("full_2", 0.9, TeamSize.FULL_TEAM, 0.88, TeamSize.FULL_TEAM),
        ("full_3", 0.95, TeamSize.FULL_TEAM, 0.92, TeamSize.FULL_TEAM),

        # Misclassified cases
        ("mis_1", 0.55, TeamSize.INDIVIDUAL, 0.62, TeamSize.SMALL_TEAM),  # FP
        ("mis_2", 0.82, TeamSize.FULL_TEAM, 0.77, TeamSize.SMALL_TEAM),   # FN
    ]

    for test_id, expected_complexity, expected_team, predicted_complexity, predicted_team in test_cases:
        case = VTestCase(
            id=test_id,
            name=f"Test {test_id}",
            capability_request=f"Capability {test_id}",
            expected_complexity=expected_complexity,
            expected_team_size=expected_team,
            domain=CapabilityDomain.DATA,
            category=CaseCategory.KNOWN_SIMPLE if expected_team == TeamSize.INDIVIDUAL else CaseCategory.KNOWN_COMPLEX,
            factors=ComplexityFactors()
        )

        result = VTestResult(
            test_case=case,
            predicted_complexity=predicted_complexity,
            predicted_team_size=predicted_team,
            status=ValidationStatus.PASS if expected_team == predicted_team else ValidationStatus.FAIL,
            error_margin=abs(predicted_complexity - expected_complexity),
            classification_correct=expected_team == predicted_team,
            execution_time_ms=100.0,
            token_usage=500
        )
        results.append(result)

    return results


# =============================================================================
# TEST CASE LIBRARY TESTS
# =============================================================================

class TestCaseLibrary:
    """Tests for the CaseLibrary class."""

    def test_get_all_test_cases_count(self):
        """Test that library returns 100+ test cases after expansion."""
        cases = CaseLibrary.get_all_test_cases()
        assert len(cases) >= 100, f"Expected at least 100 test cases, got {len(cases)}"

    def test_edge_cases_include_threshold_boundaries(self):
        """Test that edge cases include cases near 0.6 and 0.8 thresholds."""
        edge_cases = CaseLibrary._get_edge_cases()

        complexities = [c.expected_complexity for c in edge_cases]

        # Check for cases near 0.6
        near_06 = any(0.55 <= c <= 0.65 for c in complexities)
        assert near_06, "No edge cases near 0.6 threshold"

        # Check for cases near 0.8
        near_08 = any(0.75 <= c <= 0.85 for c in complexities)
        assert near_08, "No edge cases near 0.8 threshold"

    def test_known_simple_cases_below_threshold(self):
        """Test that known simple cases are below 0.6 complexity."""
        simple_cases = CaseLibrary._get_known_simple_cases()

        for case in simple_cases:
            assert case.expected_complexity < 0.6, \
                f"Simple case {case.id} has complexity {case.expected_complexity} >= 0.6"
            assert case.expected_team_size == TeamSize.INDIVIDUAL, \
                f"Simple case {case.id} expected team size is not INDIVIDUAL"

    def test_known_complex_cases_above_threshold(self):
        """Test that known complex cases are above 0.8 complexity."""
        complex_cases = CaseLibrary._get_known_complex_cases()

        for case in complex_cases:
            assert case.expected_complexity > 0.8, \
                f"Complex case {case.id} has complexity {case.expected_complexity} <= 0.8"
            assert case.expected_team_size == TeamSize.FULL_TEAM, \
                f"Complex case {case.id} expected team size is not FULL_TEAM"

    def test_domain_coverage(self):
        """Test that all domains are covered."""
        cases = CaseLibrary.get_all_test_cases()
        domains = set(c.domain for c in cases)

        expected_domains = set(CapabilityDomain)
        assert domains == expected_domains, f"Missing domains: {expected_domains - domains}"

    def test_synthetic_cases_generation(self):
        """Test synthetic case generation."""
        synthetic = CaseLibrary.get_synthetic_cases(10)

        assert len(synthetic) == 10

        # Check that complexities are distributed
        complexities = [c.expected_complexity for c in synthetic]
        assert min(complexities) >= 0.0
        assert max(complexities) <= 1.0

    def test_test_case_validation(self):
        """Test that invalid test cases raise errors."""
        with pytest.raises(ValueError, match="Expected complexity must be 0-1"):
            VTestCase(
                id="invalid",
                name="Invalid",
                capability_request="Test",
                expected_complexity=1.5,  # Invalid
                expected_team_size=TeamSize.INDIVIDUAL,
                domain=CapabilityDomain.DATA,
                category=CaseCategory.KNOWN_SIMPLE,
                factors=ComplexityFactors()
            )


# =============================================================================
# COMPLEXITY FACTORS TESTS
# =============================================================================

class TestComplexityFactors:
    """Tests for ComplexityFactors dataclass."""

    def test_to_vector_normalization(self):
        """Test that factor vector is properly normalized."""
        factors = ComplexityFactors(
            domain_risk=0.5,
            api_count=20,  # Should be capped at 1.0
            integration_points=10,  # Should be capped at 1.0
            security_sensitivity=0.7,
            data_volume_gb=200,  # Should be capped
            concurrency_requirements=5000  # Should be capped
        )

        vector = factors.to_vector()

        assert len(vector) == 6
        assert 0 <= vector[0] <= 1  # domain_risk
        assert 0 <= vector[1] <= 1  # api_count (normalized)
        assert 0 <= vector[2] <= 1  # integration_points (normalized)
        assert 0 <= vector[3] <= 1  # security_sensitivity
        assert 0 <= vector[4] <= 1  # data_volume (normalized)
        assert 0 <= vector[5] <= 1  # concurrency (normalized)

        # Check capping
        assert vector[1] == 1.0  # 20/10 capped at 1.0
        assert vector[2] == 1.0  # 10/5 capped at 1.0


# =============================================================================
# VALIDATION FRAMEWORK TESTS
# =============================================================================

class TestComplexityValidationFramework:
    """Tests for ComplexityValidationFramework."""

    @pytest.mark.asyncio
    async def test_run_validation_suite(self, mock_classifier):
        """Test running validation suite."""
        framework = ComplexityValidationFramework(mock_classifier)
        results = await framework.run_validation_suite()

        assert len(results) > 0
        assert all(isinstance(r, VTestResult) for r in results)

    @pytest.mark.asyncio
    async def test_classification_correctness(self, mock_classifier):
        """Test that classification correctness is determined properly."""
        framework = ComplexityValidationFramework(mock_classifier)

        # Create a test case with known expected value
        case = VTestCase(
            id="test_correct",
            name="Test Correct",
            capability_request="Test",
            expected_complexity=0.65,
            expected_team_size=TeamSize.SMALL_TEAM,
            domain=CapabilityDomain.DATA,
            category=CaseCategory.KNOWN_SIMPLE,
            factors=ComplexityFactors()
        )

        result = await framework._run_single_test(case)

        assert isinstance(result, VTestResult)
        assert result.test_case == case
        assert 0 <= result.predicted_complexity <= 1

    def test_complexity_to_team_size(self):
        """Test complexity to team size conversion."""
        framework = ComplexityValidationFramework(Mock())

        # Test calibrated thresholds (0.21, 0.64)
        assert framework._complexity_to_team_size(0.10) == TeamSize.INDIVIDUAL
        assert framework._complexity_to_team_size(0.20) == TeamSize.INDIVIDUAL
        assert framework._complexity_to_team_size(0.21) == TeamSize.SMALL_TEAM
        assert framework._complexity_to_team_size(0.50) == TeamSize.SMALL_TEAM
        assert framework._complexity_to_team_size(0.64) == TeamSize.FULL_TEAM
        assert framework._complexity_to_team_size(0.90) == TeamSize.FULL_TEAM

    def test_calculate_metrics(self, sample_test_results):
        """Test metrics calculation."""
        framework = ComplexityValidationFramework(Mock())
        framework.results = sample_test_results

        metrics = framework.calculate_metrics()

        assert isinstance(metrics, ValidationMetrics)
        assert metrics.total_cases == len(sample_test_results)
        assert 0 <= metrics.accuracy <= 1
        assert 0 <= metrics.precision <= 1
        assert 0 <= metrics.recall <= 1

    def test_accuracy_calculation(self, sample_test_results):
        """Test that accuracy is calculated correctly."""
        framework = ComplexityValidationFramework(Mock())
        framework.results = sample_test_results

        metrics = framework.calculate_metrics()

        # 9 correct out of 11 (3 individual + 3 small + 3 full correct, 2 misclassified)
        expected_accuracy = 9 / 11
        assert metrics.accuracy == pytest.approx(expected_accuracy, 0.01)

    def test_precision_calculation(self, sample_test_results):
        """Test precision calculation for team spawning."""
        framework = ComplexityValidationFramework(Mock())
        framework.results = sample_test_results

        metrics = framework.calculate_metrics()

        # Precision = TP / (TP + FP)
        # TP: correctly predicted small or full team
        # FP: predicted team but should be individual
        assert 0 <= metrics.precision <= 1

    def test_recall_calculation(self, sample_test_results):
        """Test recall calculation for complex tasks."""
        framework = ComplexityValidationFramework(Mock())
        framework.results = sample_test_results

        metrics = framework.calculate_metrics()

        # Recall = TP / (TP + FN)
        assert 0 <= metrics.recall <= 1

    def test_error_metrics(self, sample_test_results):
        """Test error metric calculations."""
        framework = ComplexityValidationFramework(Mock())
        framework.results = sample_test_results

        metrics = framework.calculate_metrics()

        assert metrics.mean_absolute_error >= 0
        assert metrics.root_mean_squared_error >= 0
        assert metrics.max_error >= 0
        assert metrics.root_mean_squared_error >= metrics.mean_absolute_error

    def test_generate_report(self, sample_test_results):
        """Test report generation."""
        framework = ComplexityValidationFramework(Mock())
        framework.results = sample_test_results

        metrics = framework.calculate_metrics()
        report = framework.generate_report(metrics)

        assert isinstance(report, str)
        assert "COMPLEXITY SCORING VALIDATION REPORT" in report
        assert "SUMMARY" in report
        assert "PER-TEAM-SIZE PERFORMANCE" in report
        assert "RECOMMENDATIONS" in report

    def test_report_recommendations_low_accuracy(self):
        """Test that report includes warnings for low accuracy."""
        framework = ComplexityValidationFramework(Mock())

        # Create metrics with low accuracy
        metrics = ValidationMetrics(
            accuracy=0.70,  # Below 85%
            precision=0.85,
            recall=0.90
        )

        recommendations = framework._generate_recommendations(metrics)

        assert any("accuracy" in r.lower() for r in recommendations)

    def test_report_recommendations_low_precision(self):
        """Test that report includes warnings for low precision."""
        framework = ComplexityValidationFramework(Mock())

        metrics = ValidationMetrics(
            accuracy=0.90,
            precision=0.85,  # Below 90%
            recall=0.95
        )

        recommendations = framework._generate_recommendations(metrics)

        assert any("precision" in r.lower() for r in recommendations)


# =============================================================================
# THRESHOLD CALIBRATOR TESTS
# =============================================================================

class TestThresholdCalibrator:
    """Tests for ThresholdCalibrator."""

    def test_calibrate_thresholds(self, sample_test_results):
        """Test threshold calibration."""
        framework = ComplexityValidationFramework(Mock())
        framework.results = sample_test_results

        calibrator = ThresholdCalibrator(framework)
        calibration = calibrator.calibrate_thresholds(sample_test_results)

        assert isinstance(calibration, ThresholdCalibration)
        assert 0.4 <= calibration.lower_threshold < calibration.upper_threshold <= 0.95
        assert 0 <= calibration.confidence <= 1

    def test_calibration_respects_constraints(self, sample_test_results):
        """Test that calibration respects min precision/recall constraints."""
        framework = ComplexityValidationFramework(Mock())
        framework.results = sample_test_results

        # Set high constraints that may not be achievable
        calibrator = ThresholdCalibrator(framework, min_precision=0.99, min_recall=0.99)
        calibration = calibrator.calibrate_thresholds(sample_test_results)

        # Should still return a result but with warning
        assert isinstance(calibration, ThresholdCalibration)

    def test_suggest_ab_test(self, sample_test_results):
        """Test A/B test suggestion generation."""
        framework = ComplexityValidationFramework(Mock())
        framework.results = sample_test_results

        calibrator = ThresholdCalibrator(framework)

        current = ThresholdCalibration(lower_threshold=0.6, upper_threshold=0.8)
        new = ThresholdCalibration(lower_threshold=0.65, upper_threshold=0.85)

        ab_test = calibrator.suggest_ab_test(current, new)

        assert "test_name" in ab_test
        assert "control" in ab_test
        assert "treatment" in ab_test
        assert "success_criteria" in ab_test
        assert ab_test["control"]["traffic_percentage"] == 50
        assert ab_test["treatment"]["traffic_percentage"] == 50


# =============================================================================
# PRODUCTION MONITOR TESTS
# =============================================================================

class TestProductionMonitor:
    """Tests for ProductionMonitor."""

    def test_record_classification(self):
        """Test recording classifications."""
        monitor = ProductionMonitor()

        monitor.record_classification(
            capability_request="Test API",
            complexity=0.7,
            team_size=TeamSize.SMALL_TEAM,
            execution_time_ms=150.0,
            token_usage=500
        )

        assert len(monitor.classifications) == 1

    def test_get_current_metrics(self):
        """Test current metrics calculation."""
        monitor = ProductionMonitor()

        # Add some classifications
        for i in range(10):
            monitor.record_classification(
                capability_request=f"Test {i}",
                complexity=0.5 + (i * 0.05),
                team_size=TeamSize.INDIVIDUAL if i < 5 else TeamSize.SMALL_TEAM,
                execution_time_ms=100.0 + i * 10,
                token_usage=400 + i * 50
            )

        metrics = monitor.get_current_metrics()

        assert isinstance(metrics, ProductionMetrics)
        assert metrics.individual_count == 5
        assert metrics.small_team_count == 5
        assert metrics.tokens_24h > 0

    def test_drift_detection(self):
        """Test complexity drift detection."""
        monitor = ProductionMonitor(
            alert_thresholds={
                "max_avg_complexity_change": 0.1,
                "max_classification_time_ms": 5000,
            },
            drift_window_hours=168,  # 7 days so old data is kept
        )

        # Add old classifications (low complexity) — within 7d but outside 24h
        old_time = datetime.now(timezone.utc) - timedelta(days=3)
        for i in range(5):
            monitor.classifications.append({
                "timestamp": old_time,
                "capability_request": f"Old {i}",
                "complexity": 0.3,
                "team_size": "individual",
                "execution_time_ms": 100.0,
                "token_usage": 400
            })

        # Add recent classifications (high complexity - drift)
        for i in range(5):
            monitor.record_classification(
                capability_request=f"New {i}",
                complexity=0.8,  # Much higher
                team_size=TeamSize.FULL_TEAM,
                execution_time_ms=200.0,
                token_usage=800
            )

        metrics = monitor.get_current_metrics()

        assert metrics.complexity_drift_detected

    def test_check_alerts_drift(self):
        """Test drift alert generation."""
        monitor = ProductionMonitor(
            alert_thresholds={
                "max_avg_complexity_change": 0.05,
                "max_classification_time_ms": 5000,
            },
            drift_window_hours=168,  # 7 days so old data is kept
        )

        # Create drift scenario — old data within 7d but outside 24h
        old_time = datetime.now(timezone.utc) - timedelta(days=3)
        for i in range(10):
            monitor.classifications.append({
                "timestamp": old_time,
                "capability_request": f"Old {i}",
                "complexity": 0.3,
                "team_size": "individual",
                "execution_time_ms": 100.0,
                "token_usage": 400
            })

        for i in range(10):
            monitor.record_classification(
                capability_request=f"New {i}",
                complexity=0.8,
                team_size=TeamSize.FULL_TEAM,
                execution_time_ms=200.0,
                token_usage=800
            )

        alerts = monitor.check_alerts()

        drift_alerts = [a for a in alerts if a["type"] == "complexity_drift"]
        assert len(drift_alerts) > 0

    def test_check_alerts_performance(self):
        """Test performance alert generation."""
        monitor = ProductionMonitor(
            alert_thresholds={
                "max_classification_time_ms": 50,
                "max_avg_complexity_change": 0.15,
            }
        )

        # Add slow classifications
        for i in range(5):
            monitor.record_classification(
                capability_request=f"Slow {i}",
                complexity=0.7,
                team_size=TeamSize.SMALL_TEAM,
                execution_time_ms=1000.0,  # Very slow
                token_usage=500
            )

        alerts = monitor.check_alerts()

        perf_alerts = [a for a in alerts if a["type"] == "performance_degradation"]
        assert len(perf_alerts) > 0

    def test_feedback_summary(self):
        """Test feedback summary generation."""
        monitor = ProductionMonitor()

        # Add feedback
        for i in range(10):
            monitor.record_classification(
                capability_request=f"Test {i}",
                complexity=0.7,
                team_size=TeamSize.SMALL_TEAM,
                execution_time_ms=100.0,
                token_usage=500,
                feedback="correct" if i < 7 else "overclassified"
            )

        summary = monitor.get_feedback_summary()

        assert summary["total_feedback"] == 10
        assert summary["correct_ratio"] == 0.7
        assert summary["overclassified_ratio"] == 0.3

    def test_feedback_summary_recommendations(self):
        """Test that feedback summary generates recommendations."""
        monitor = ProductionMonitor()

        # Add mostly overclassified feedback
        for i in range(10):
            monitor.record_classification(
                capability_request=f"Test {i}",
                complexity=0.7,
                team_size=TeamSize.SMALL_TEAM,
                execution_time_ms=100.0,
                token_usage=500,
                feedback="overclassified"
            )

        summary = monitor.get_feedback_summary()

        assert len(summary["recommendations"]) > 0
        assert any("overclassification" in r.lower() for r in summary["recommendations"])

    def test_prune_old_data(self):
        """Test that old data is pruned."""
        monitor = ProductionMonitor(drift_window_hours=1)

        # Add old data
        old_time = datetime.now(timezone.utc) - timedelta(hours=3)
        monitor.classifications.append({
            "timestamp": old_time,
            "capability_request": "Old",
            "complexity": 0.5,
            "team_size": "individual",
            "execution_time_ms": 100.0,
            "token_usage": 400
        })

        # Add new data
        monitor.record_classification(
            capability_request="New",
            complexity=0.7,
            team_size=TeamSize.SMALL_TEAM,
            execution_time_ms=100.0,
            token_usage=500
        )

        # Prune should remove old data
        monitor._prune_old_data()

        assert len(monitor.classifications) == 1


# =============================================================================
# STAGING PIPELINE TESTS
# =============================================================================

class TestStagingValidationPipeline:
    """Tests for StagingValidationPipeline."""

    @pytest.mark.asyncio
    async def test_run_full_validation(self, mock_classifier):
        """Test full validation pipeline."""
        pipeline = StagingValidationPipeline(mock_classifier)

        result = await pipeline.run_full_validation()

        assert "timestamp" in result
        assert "metrics" in result
        assert "calibration" in result
        assert "report" in result
        assert "recommendation" in result
        assert "test_results" in result

    def test_go_decision(self):
        """Test GO decision for good metrics."""
        pipeline = StagingValidationPipeline(Mock())

        metrics = ValidationMetrics(
            accuracy=0.90,
            individual_precision=0.95,
            full_team_recall=0.94,
            edge_case_accuracy=0.80,
            mean_absolute_error=0.08
        )
        calibration = ThresholdCalibration(confidence=0.85)

        decision = pipeline._make_go_no_go_decision(metrics, calibration)

        assert decision["decision"] == "GO"
        assert decision["confidence"] == "high"
        assert len(decision["issues"]) == 0

    def test_no_go_decision_low_accuracy(self):
        """Test NO_GO decision for low accuracy."""
        pipeline = StagingValidationPipeline(Mock())

        metrics = ValidationMetrics(
            accuracy=0.75,  # Too low
            precision=0.85,
            recall=0.90
        )
        calibration = ThresholdCalibration()

        decision = pipeline._make_go_no_go_decision(metrics, calibration)

        assert decision["decision"] == "NO_GO"
        assert "accuracy" in str(decision["issues"]).lower()

    def test_no_go_decision_low_individual_precision(self):
        """Test NO_GO decision for low individual precision."""
        pipeline = StagingValidationPipeline(Mock())

        metrics = ValidationMetrics(
            accuracy=0.88,
            individual_precision=0.85,  # Below 90% threshold
            full_team_recall=0.95,
            edge_case_accuracy=0.80,
            mean_absolute_error=0.10,
        )
        calibration = ThresholdCalibration()

        decision = pipeline._make_go_no_go_decision(metrics, calibration)

        assert decision["decision"] == "NO_GO"
        assert "individual precision" in str(decision["issues"]).lower()

    def test_no_go_decision_low_full_team_recall(self):
        """Test NO_GO decision for low full team recall."""
        pipeline = StagingValidationPipeline(Mock())

        metrics = ValidationMetrics(
            accuracy=0.88,
            individual_precision=0.95,
            full_team_recall=0.85,  # Below 90% threshold
            edge_case_accuracy=0.80,
            mean_absolute_error=0.10,
        )
        calibration = ThresholdCalibration()

        decision = pipeline._make_go_no_go_decision(metrics, calibration)

        assert decision["decision"] == "NO_GO"
        assert "full team recall" in str(decision["issues"]).lower()


# =============================================================================
# UTILITY FUNCTION TESTS
# =============================================================================

class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_create_validation_suite(self, mock_classifier):
        """Test validation suite creation."""
        suite = create_validation_suite(mock_classifier, include_synthetic=True)

        assert isinstance(suite, ComplexityValidationFramework)
        assert len(suite.test_cases) >= 100  # Base + synthetic

    def test_create_validation_suite_without_synthetic(self, mock_classifier):
        """Test validation suite creation without synthetic cases."""
        suite = create_validation_suite(mock_classifier, include_synthetic=False)

        assert isinstance(suite, ComplexityValidationFramework)
        assert len(suite.test_cases) >= 100  # Expanded base cases (no synthetic)

    @pytest.mark.asyncio
    async def test_run_quick_validation(self, mock_classifier):
        """Test quick validation function."""
        metrics = await run_quick_validation(mock_classifier)

        assert isinstance(metrics, ValidationMetrics)


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestIntegration:
    """Integration tests for the complete validation flow."""

    @pytest.mark.asyncio
    async def test_end_to_end_validation(self, mock_classifier):
        """Test complete validation flow."""
        # Create framework
        framework = ComplexityValidationFramework(mock_classifier)

        # Run validation
        results = await framework.run_validation_suite()

        # Calculate metrics
        metrics = framework.calculate_metrics(results)

        # Generate report
        report = framework.generate_report(metrics)

        # Verify results
        assert len(results) > 0
        assert metrics.total_cases == len(results)
        assert isinstance(report, str)

    @pytest.mark.asyncio
    async def test_calibration_flow(self, mock_classifier):
        """Test calibration workflow."""
        # Setup
        framework = ComplexityValidationFramework(mock_classifier)
        await framework.run_validation_suite()

        # Calibrate
        calibrator = ThresholdCalibrator(framework)
        calibration = calibrator.calibrate_thresholds()

        # Suggest A/B test
        current = ThresholdCalibration(lower_threshold=0.6, upper_threshold=0.8)
        ab_test = calibrator.suggest_ab_test(current, calibration)

        # Verify
        assert calibration.lower_threshold != 0 or calibration.upper_threshold != 0
        assert "control" in ab_test
        assert "treatment" in ab_test

    def test_metrics_serialization(self):
        """Test that metrics can be serialized to JSON."""
        metrics = ValidationMetrics(
            accuracy=0.90,
            precision=0.92,
            recall=0.95,
            domain_accuracy={
                "COMMUNICATION": 0.88,
                "DATA": 0.92
            }
        )

        json_str = metrics.to_json()

        assert isinstance(json_str, str)
        assert "accuracy" in json_str
        assert "0.9" in json_str


# =============================================================================
# PHASE 0 TESTS - Complexity Config & Enum Unification
# =============================================================================

class TestPhase0Config:
    """Phase 0 tests: verify complexity_config and enum unification."""

    def test_teamsize_enums_are_identical(self):
        """Both modules share the same TeamSize class (not just same values)."""
        from tools.kurultai.complexity_validation_framework import TeamSize as FrameworkTeamSize
        from tools.kurultai.complexity_validation_framework import TeamSize

        # They must be the exact same class object
        assert FrameworkTeamSize is TeamSize

    def test_complexity_config_thresholds(self):
        """Verify default thresholds match calibrated values."""
        from tools.kurultai.complexity_config import DEFAULT_CONFIG

        assert DEFAULT_CONFIG.individual_threshold == 0.21
        assert DEFAULT_CONFIG.small_team_threshold == 0.64

    def test_complexity_to_team_size_boundaries(self):
        """Test boundary values at calibrated thresholds (0.21/0.64)."""
        from tools.kurultai.complexity_config import complexity_to_team_size

        assert complexity_to_team_size(0.20) == "individual"
        assert complexity_to_team_size(0.21) == "small_team"
        assert complexity_to_team_size(0.63) == "small_team"
        assert complexity_to_team_size(0.64) == "full_team"

    def test_reg_002_consistency(self):
        """Verify expected_complexity >= individual_threshold for SMALL_TEAM regression cases."""
        from tools.kurultai.complexity_config import DEFAULT_CONFIG
        regression_cases = CaseLibrary._get_regression_cases()

        for case in regression_cases:
            if case.expected_team_size == TeamSize.SMALL_TEAM:
                assert case.expected_complexity >= DEFAULT_CONFIG.individual_threshold, (
                    f"Regression case {case.id} has expected_complexity "
                    f"{case.expected_complexity} < {DEFAULT_CONFIG.individual_threshold} but is SMALL_TEAM"
                )
