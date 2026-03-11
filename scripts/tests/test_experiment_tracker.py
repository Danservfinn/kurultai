#!/usr/bin/env python3
"""
Tests for Experiment Tracker Module

Run with: python3 test_experiment_tracker.py

Tests:
1. Test experiment lifecycle state transitions
2. Test statistical analysis with known data
3. Test guardrail violation detection
4. Test early stopping conditions
5. Test YAML load/save
6. Test Neo4j node creation (mock)
7. Test sample size validation
8. Test targeting filter application
"""

import os
import sys
import json
import tempfile
import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from pathlib import Path

# Add script directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from experiment_tracker import (
    ExperimentTracker,
    ExperimentConfig,
    ExperimentTargeting,
    SampleSizeConfig,
    DurationConfig,
    SuccessCriteria,
    GuardrailConfig,
    RolloutConfig,
    ExperimentResult,
    GuardrailViolation,
    ConclusionResult,
    evaluate_experiment,
    check_guardrails,
    should_stop_early,
    calculate_cohens_d,
    load_experiment_from_yaml,
    save_experiment_to_yaml,
    DEFAULT_GUARDRAILS
)
from ces_calculator import calculate_ces, TaskMetrics


class TestExperimentConfig(unittest.TestCase):
    """Test experiment configuration dataclasses."""

    def test_experiment_targeting_defaults(self):
        """Test default targeting excludes critical."""
        targeting = ExperimentTargeting()
        self.assertIsNone(targeting.agents)
        self.assertIsNone(targeting.task_types)
        self.assertEqual(targeting.priorities, ["normal", "low"])

    def test_experiment_targeting_from_dict(self):
        """Test targeting creation from dict."""
        data = {
            "agents": ["temujin", "jochi"],
            "task_types": ["review", "security"],
            "priorities": ["high", "normal", "low"]
        }
        targeting = ExperimentTargeting.from_dict(data)
        self.assertEqual(targeting.agents, ["temujin", "jochi"])
        self.assertEqual(targeting.task_types, ["review", "security"])

    def test_experiment_config_to_dict_and_back(self):
        """Test config serialization roundtrip."""
        config = ExperimentConfig(
            experiment_id="test-exp-001",
            hypothesis="Test hypothesis",
            variable_type="model",
            control_value="model-a",
            treatment_value="model-b",
            targeting=ExperimentTargeting(agents=["temujin"]),
            sample_size=SampleSizeConfig(min_per_group=50),
            duration=DurationConfig(min_days=5, max_days=10),
            success_criteria=SuccessCriteria(ces_lift_min=0.10),
            guardrails={"test_metric": GuardrailConfig(min=0.5, weight=1.0)},
            rollout=RolloutConfig(strategy="immediate")
        )

        data = config.to_dict()
        restored = ExperimentConfig.from_dict(data)

        self.assertEqual(restored.experiment_id, config.experiment_id)
        self.assertEqual(restored.hypothesis, config.hypothesis)
        self.assertEqual(restored.targeting.agents, ["temujin"])


class TestStatisticalAnalysis(unittest.TestCase):
    """Test statistical analysis functions."""

    def test_cohens_d_calculation(self):
        """Test Cohen's d effect size calculation."""
        # Identical groups → d = 0
        control = [0.5, 0.5, 0.5, 0.5]
        treatment = [0.5, 0.5, 0.5, 0.5]
        self.assertAlmostEqual(calculate_cohens_d(control, treatment), 0.0, places=3)

        # Clear difference with variance → large positive d
        control = [0.5, 0.55, 0.45, 0.52]
        treatment = [0.8, 0.85, 0.75, 0.82]
        d = calculate_cohens_d(control, treatment)
        self.assertGreater(d, 2.0)  # Very large effect

        # Clear negative difference → large negative d
        control = [0.8, 0.85, 0.75, 0.82]
        treatment = [0.5, 0.55, 0.45, 0.52]
        d = calculate_cohens_d(control, treatment)
        self.assertLess(d, -2.0)  # Very large negative effect

    def test_evaluate_experiment_significant_result(self):
        """Test experiment evaluation with significant result."""
        # Create clear difference
        import random
        random.seed(42)

        control = [0.70 + random.gauss(0, 0.05) for _ in range(100)]
        treatment = [0.80 + random.gauss(0, 0.05) for _ in range(100)]

        result = evaluate_experiment(control, treatment)

        self.assertGreater(result.mean_treatment, result.mean_control)
        self.assertGreater(result.absolute_lift, 0)
        self.assertTrue(result.sample_adequate)
        self.assertGreater(result.cohens_d, 0)

    def test_evaluate_experiment_no_difference(self):
        """Test experiment evaluation with no real difference."""
        import random
        random.seed(42)

        # Same distribution
        control = [0.75 + random.gauss(0, 0.05) for _ in range(100)]
        treatment = [0.75 + random.gauss(0, 0.05) for _ in range(100)]

        result = evaluate_experiment(control, treatment)

        self.assertAlmostEqual(result.mean_control, result.mean_treatment, delta=0.05)
        self.assertAlmostEqual(result.absolute_lift, 0, delta=0.05)

    def test_evaluate_experiment_small_sample(self):
        """Test experiment evaluation with insufficient sample."""
        control = [0.7, 0.75, 0.8]
        treatment = [0.8, 0.85, 0.9]

        result = evaluate_experiment(control, treatment)

        self.assertFalse(result.sample_adequate)


class TestGuardrailChecking(unittest.TestCase):
    """Test guardrail violation detection."""

    def test_no_violations(self):
        """Test when all metrics are within bounds."""
        baseline = {
            "success_rate_normal": 0.80,
            "quality_score_avg": 0.75,
            "rework_rate": 0.10
        }
        experiment = {
            "success_rate_normal": 0.80,  # Equal to min
            "quality_score_avg": 0.75,    # Equal to min
            "rework_rate": 0.15           # Below max
        }

        violations = check_guardrails(baseline, experiment)
        self.assertEqual(len(violations), 0)

    def test_min_threshold_violation(self):
        """Test detection of minimum threshold violation."""
        baseline = {"success_rate_normal": 0.80}
        experiment = {"success_rate_normal": 0.50}  # Below min of 0.75

        violations = check_guardrails(baseline, experiment)

        self.assertGreaterEqual(len(violations), 1)
        sr_violations = [v for v in violations if v.metric_name == "success_rate_normal"]
        self.assertEqual(len(sr_violations), 1)
        self.assertEqual(sr_violations[0].violation_type, "min")

    def test_max_threshold_violation(self):
        """Test detection of maximum threshold violation."""
        baseline = {"rework_rate": 0.10}
        experiment = {"rework_rate": 0.30}  # Above max of 0.20

        violations = check_guardrails(baseline, experiment)

        self.assertGreaterEqual(len(violations), 1)
        rework_violations = [v for v in violations if v.metric_name == "rework_rate"]
        self.assertEqual(len(rework_violations), 1)

    def test_max_increase_pct_violation(self):
        """Test detection of max increase percentage violation."""
        baseline = {"duration_p90": 100}
        experiment = {"duration_p90": 150}  # 50% increase > 30% threshold

        violations = check_guardrails(baseline, experiment)

        self.assertGreaterEqual(len(violations), 1)


class TestEarlyStopping(unittest.TestCase):
    """Test early stopping conditions."""

    def test_catastrophic_failure(self):
        """Test early stop on catastrophic failure."""
        result = ExperimentResult(
            mean_control=0.75,
            mean_treatment=0.70,
            absolute_lift=-0.05,
            relative_lift_pct=-6.67,
            t_statistic=-1.5,
            p_value=0.15,
            cohens_d=-0.3,
            ci_95=(-0.12, 0.02),
            significant=False,
            practical_significance=False,
            sample_adequate=True,
            n_control=100,
            n_treatment=100
        )

        metrics = {"success_rate_critical": 0.70}  # Below 80%

        should_stop, reason = should_stop_early(
            "test-exp", 5, 100, 100, result, metrics
        )

        self.assertTrue(should_stop)
        self.assertIn("Catastrophic", reason)

    def test_severe_regression(self):
        """Test early stop on severe regression."""
        result = ExperimentResult(
            mean_control=0.75,
            mean_treatment=0.60,
            absolute_lift=-0.15,
            relative_lift_pct=-20.0,
            t_statistic=-3.5,
            p_value=0.001,
            cohens_d=-1.0,
            ci_95=(-0.22, -0.08),
            significant=True,
            practical_significance=True,
            sample_adequate=True,
            n_control=100,
            n_treatment=100
        )

        should_stop, reason = should_stop_early(
            "test-exp", 5, 100, 100, result
        )

        self.assertTrue(should_stop)
        self.assertIn("regression", reason.lower())

    def test_clear_winner(self):
        """Test early stop on clear winner."""
        result = ExperimentResult(
            mean_control=0.70,
            mean_treatment=0.85,
            absolute_lift=0.15,
            relative_lift_pct=21.4,
            t_statistic=5.5,
            p_value=0.0001,  # p < 0.01
            cohens_d=0.8,    # d > 0.5
            ci_95=(0.10, 0.20),
            significant=True,
            practical_significance=True,
            sample_adequate=True,
            n_control=150,
            n_treatment=150
        )

        should_stop, reason = should_stop_early(
            "test-exp", 5, 150, 150, result
        )

        self.assertTrue(should_stop)
        self.assertIn("winner", reason.lower())

    def test_no_effect_after_max_duration(self):
        """Test early stop when no effect detected after max duration."""
        result = ExperimentResult(
            mean_control=0.75,
            mean_treatment=0.751,
            absolute_lift=0.001,
            relative_lift_pct=0.13,
            t_statistic=0.1,
            p_value=0.92,
            cohens_d=0.01,
            ci_95=(-0.02, 0.022),  # Includes 0, width < 0.05
            significant=False,
            practical_significance=False,
            sample_adequate=True,
            n_control=500,
            n_treatment=500
        )

        should_stop, reason = should_stop_early(
            "test-exp", 14, 500, 500, result  # 14 days running
        )

        self.assertTrue(should_stop)
        self.assertIn("No effect", reason)


class TestYAMLSupport(unittest.TestCase):
    """Test YAML load/save functionality."""

    def test_yaml_roundtrip(self):
        """Test saving and loading experiment config from YAML."""
        config = ExperimentConfig(
            experiment_id="exp-2026-03-08-test",
            hypothesis="Test YAML support",
            variable_type="model",
            control_value="model-a",
            treatment_value="model-b",
            targeting=ExperimentTargeting(agents=["temujin"]),
            sample_size=SampleSizeConfig(min_per_group=50),
            duration=DurationConfig(min_days=5),
            success_criteria=SuccessCriteria(ces_lift_min=0.08),
            guardrails={},
            rollout=RolloutConfig()
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            temp_path = f.name

        try:
            save_experiment_to_yaml(config, temp_path)
            loaded = load_experiment_from_yaml(temp_path)

            self.assertEqual(loaded.experiment_id, config.experiment_id)
            self.assertEqual(loaded.hypothesis, config.hypothesis)
            self.assertEqual(loaded.variable_type, config.variable_type)
            self.assertEqual(loaded.targeting.agents, ["temujin"])
            self.assertEqual(loaded.sample_size.min_per_group, 50)

        finally:
            os.unlink(temp_path)


class TestExperimentTrackerLifecycle(unittest.TestCase):
    """Test experiment lifecycle state transitions."""

    def setUp(self):
        """Set up mock tracker for each test."""
        self.mock_driver = MagicMock()
        self.mock_session = MagicMock()
        self.mock_driver.session.return_value.__enter__ = Mock(return_value=self.mock_session)
        self.mock_driver.session.return_value.__exit__ = Mock(return_value=False)
        self.tracker = ExperimentTracker(neo4j_driver=self.mock_driver)

    def test_propose_creates_config(self):
        """Test proposing a new experiment."""
        config = ExperimentConfig(
            experiment_id="test-propose-001",
            hypothesis="Test proposal",
            variable_type="model",
            control_value="a",
            treatment_value="b",
            targeting=ExperimentTargeting(),
            sample_size=SampleSizeConfig(),
            duration=DurationConfig(),
            success_criteria=SuccessCriteria(),
            guardrails={},
            rollout=RolloutConfig()
        )

        exp_id = self.tracker.propose(config)
        self.assertEqual(exp_id, "test-propose-001")

    def test_start_transitions_to_running(self):
        """Test starting an experiment."""
        # Mock Neo4j responses
        mock_result = Mock()
        mock_result.single.return_value = {"status": "PROPOSED"}
        self.mock_session.run.return_value = mock_result

        # Create config file
        config = ExperimentConfig(
            experiment_id="test-start-001",
            hypothesis="Test start",
            variable_type="model",
            control_value="a",
            treatment_value="b",
            targeting=ExperimentTargeting(),
            sample_size=SampleSizeConfig(),
            duration=DurationConfig(),
            success_criteria=SuccessCriteria(),
            guardrails={},
            rollout=RolloutConfig()
        )
        self.tracker.propose(config)

        result = self.tracker.start("test-start-001")
        self.assertTrue(result)


class TestCESCalculator(unittest.TestCase):
    """Test CES calculator integration."""

    def test_ces_calculation(self):
        """Test basic CES calculation."""
        metrics = TaskMetrics(
            success_rate=0.95,
            quality_score=0.85,
            efficiency_score=0.90,
            rework_rate=0.05
        )

        ces = calculate_ces(metrics)

        self.assertGreaterEqual(ces, 0.0)
        self.assertLessEqual(ces, 1.0)
        # High success and quality should give high CES
        self.assertGreater(ces, 0.80)

    def test_ces_with_priority_weights(self):
        """Test CES with different priority weights."""
        metrics = TaskMetrics(
            success_rate=0.80,
            quality_score=0.70,
            efficiency_score=1.0,  # Very fast
            rework_rate=0.10,
            priority="low"
        )

        ces_low = calculate_ces(metrics)

        metrics.priority = "critical"
        ces_critical = calculate_ces(metrics)

        # For same metrics, critical priority weights success more
        # With low SR=0.80, critical CES should be lower
        self.assertNotEqual(ces_low, ces_critical)

    def test_ces_with_escalation_penalty(self):
        """Test CES penalty for escalations."""
        metrics = TaskMetrics(
            success_rate=0.95,
            quality_score=0.85,
            efficiency_score=0.90,
            rework_rate=0.05,
            escalation_rate=0.0
        )

        ces_no_escalation = calculate_ces(metrics)

        metrics.escalation_rate = 0.5  # 50% escalation
        ces_with_escalation = calculate_ces(metrics, include_escalation_penalty=True)

        self.assertLess(ces_with_escalation, ces_no_escalation)


class TestTargetingFilter(unittest.TestCase):
    """Test targeting filter application."""

    def test_agent_targeting(self):
        """Test filtering by agent."""
        targeting = ExperimentTargeting(agents=["temujin", "jochi"])

        self.assertIn("temujin", targeting.agents)
        self.assertIn("jochi", targeting.agents)
        self.assertEqual(len(targeting.agents), 2)

    def test_priority_exclusion(self):
        """Test critical tasks excluded by default."""
        targeting = ExperimentTargeting()

        self.assertIn("normal", targeting.priorities)
        self.assertIn("low", targeting.priorities)
        self.assertNotIn("critical", targeting.priorities)

    def test_task_type_targeting(self):
        """Test filtering by task type."""
        targeting = ExperimentTargeting(task_types=["review", "security"])

        self.assertEqual(targeting.task_types, ["review", "security"])


class TestSampleSizeValidation(unittest.TestCase):
    """Test sample size validation."""

    def test_min_sample_size(self):
        """Test minimum sample size configuration."""
        config = SampleSizeConfig(min_per_group=100)

        self.assertEqual(config.min_per_group, 100)
        self.assertEqual(config.power, 0.8)
        self.assertEqual(config.alpha, 0.05)

    def test_sample_adequacy_check(self):
        """Test sample adequacy in experiment result."""
        # Adequate sample
        control = [0.7 + 0.05 * (i % 10) for i in range(50)]
        treatment = [0.75 + 0.05 * (i % 10) for i in range(50)]

        result = evaluate_experiment(control, treatment)
        self.assertTrue(result.sample_adequate)

        # Inadequate sample
        control_small = [0.7, 0.75, 0.8]
        treatment_small = [0.75, 0.8, 0.85]

        result_small = evaluate_experiment(control_small, treatment_small)
        self.assertFalse(result_small.sample_adequate)


def run_all_tests():
    """Run all tests and print summary."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestExperimentConfig))
    suite.addTests(loader.loadTestsFromTestCase(TestStatisticalAnalysis))
    suite.addTests(loader.loadTestsFromTestCase(TestGuardrailChecking))
    suite.addTests(loader.loadTestsFromTestCase(TestEarlyStopping))
    suite.addTests(loader.loadTestsFromTestCase(TestYAMLSupport))
    suite.addTests(loader.loadTestsFromTestCase(TestExperimentTrackerLifecycle))
    suite.addTests(loader.loadTestsFromTestCase(TestCESCalculator))
    suite.addTests(loader.loadTestsFromTestCase(TestTargetingFilter))
    suite.addTests(loader.loadTestsFromTestCase(TestSampleSizeValidation))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print(f"\n{'='*60}")
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Skipped: {len(result.skipped)}")
    print(f"{'='*60}")

    return len(result.failures) + len(result.errors) == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
