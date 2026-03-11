#!/usr/bin/env python3
"""
Unit tests for hypothesis_generator.py

Tests:
- Hypothesis dataclass
- HypothesisGenerator core methods
- Integration with Neo4j
- Hypothesis prioritization
- Learning conversion
"""

import os
import sys
import unittest
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hypothesis_generator import (
    Hypothesis,
    HypothesisGenerator,
    FailurePattern,
    DurationOutlier
)


class TestHypothesis(unittest.TestCase):
    """Test the Hypothesis dataclass."""

    def test_hypothesis_creation(self):
        """Test creating a hypothesis with all fields."""
        h = Hypothesis(
            id="hyp-test123",
            agent="temujin",
            description="Test hypothesis",
            target_files=["test.py"],
            expected_impact="success_rate:+5%",
            baseline_metric=0.75,
            confidence=0.8,
            variable_type="skill_hint",
            control_value="none",
            treatment_value="/test"
        )

        self.assertEqual(h.id, "hyp-test123")
        self.assertEqual(h.agent, "temujin")
        self.assertEqual(h.status, "pending")
        self.assertEqual(h.variable_type, "skill_hint")

    def test_hypothesis_priority_score(self):
        """Test priority score calculation."""
        h1 = Hypothesis(
            id="hyp-1",
            agent="test",
            description="Test",
            target_files=[],
            expected_impact="success_rate:+10%",
            baseline_metric=0.7,
            confidence=0.8
        )

        # 0.8 * 10 = 8.0
        self.assertAlmostEqual(h1.priority_score, 8.0)

        h2 = Hypothesis(
            id="hyp-2",
            agent="test",
            description="Test",
            target_files=[],
            expected_impact="success_rate:+5%",
            baseline_metric=0.7,
            confidence=0.9
        )

        # 0.9 * 5 = 4.5
        self.assertAlmostEqual(h2.priority_score, 4.5)

    def test_hypothesis_to_dict(self):
        """Test serializing hypothesis to dictionary."""
        h = Hypothesis(
            id="hyp-test",
            agent="mongke",
            description="Test",
            target_files=["test.py"],
            expected_impact="quality:+10%",
            baseline_metric=0.7,
            confidence=0.75
        )

        d = h.to_dict()
        self.assertIsInstance(d, dict)
        self.assertEqual(d["id"], "hyp-test")
        self.assertEqual(d["agent"], "mongke")
        self.assertEqual(d["confidence"], 0.75)


class TestHypothesisGenerator(unittest.TestCase):
    """Test the HypothesisGenerator class."""

    def setUp(self):
        """Set up mock driver for testing."""
        self.mock_driver = Mock()
        self.mock_session = Mock()
        self.mock_driver.session.return_value.__enter__ = Mock(return_value=self.mock_session)
        self.mock_driver.session.return_value.__exit__ = Mock(return_value=False)

        self.generator = HypothesisGenerator(self.mock_driver)

    def test_initialization(self):
        """Test generator initialization."""
        self.assertIsNotNone(self.generator.driver)
        self.assertIsNotNone(self.generator.queries)
        self.assertIsInstance(self.generator.file_map, dict)

    def test_prioritize(self):
        """Test hypothesis prioritization."""
        hypotheses = [
            Hypothesis(
                id="hyp-1",
                agent="test",
                description="Low priority",
                target_files=[],
                expected_impact="success_rate:+2%",
                baseline_metric=0.7,
                confidence=0.5
            ),
            Hypothesis(
                id="hyp-2",
                agent="test",
                description="High priority",
                target_files=[],
                expected_impact="success_rate:+10%",
                baseline_metric=0.7,
                confidence=0.9
            ),
            Hypothesis(
                id="hyp-3",
                agent="test",
                description="Medium priority",
                target_files=[],
                expected_impact="success_rate:+5%",
                baseline_metric=0.7,
                confidence=0.7
            ),
        ]

        prioritized = self.generator.prioritize(hypotheses)

        # Should be sorted by priority_score (confidence * impact_magnitude)
        self.assertEqual(prioritized[0].id, "hyp-2")  # 0.9 * 10 = 9
        self.assertEqual(prioritized[1].id, "hyp-3")  # 0.7 * 5 = 3.5
        self.assertEqual(prioritized[2].id, "hyp-1")  # 0.5 * 2 = 1

    def test_generate_from_learning_skill_hint(self):
        """Test converting skill_hint learning to hypothesis."""
        learning = {
            "learning_id": "kl-skill123",
            "learning_type": "skill_hint",
            "agent_filter": "temujin",
            "pattern_key": "/horde-implement",
            "confidence": 0.85,
            "recommendation": '{"action": "use_skill_hint", "skill_hint": "/horde-implement", "expected_success_rate": "0.75"}',
            "evidence": '{"success_rate": "0.75", "avg_quality": "0.8"}'
        }

        hypothesis = self.generator._convert_learning_to_hypothesis(learning)

        self.assertIsNotNone(hypothesis)
        self.assertEqual(hypothesis.agent, "temujin")
        self.assertEqual(hypothesis.variable_type, "skill_hint")
        self.assertEqual(hypothesis.treatment_value, "/horde-implement")
        self.assertEqual(hypothesis.confidence, 0.85)
        self.assertIn("horde-implement", hypothesis.description)

    def test_generate_from_learning_timeout(self):
        """Test converting timeout learning to hypothesis."""
        learning = {
            "learning_id": "kl-timeout123",
            "learning_type": "timeout",
            "agent_filter": "mongke",
            "pattern_key": "mongke:long",
            "confidence": 0.75,
            "recommendation": '{"action": "set_timeout", "timeout_bucket": "long", "timeout_seconds": 7200}',
            "evidence": '{"avg_quality": "0.75", "success_rate": "0.85"}'
        }

        hypothesis = self.generator._convert_learning_to_hypothesis(learning)

        self.assertIsNotNone(hypothesis)
        self.assertEqual(hypothesis.agent, "mongke")
        self.assertEqual(hypothesis.variable_type, "timeout")
        self.assertEqual(hypothesis.treatment_value, "7200")
        self.assertIn("7200", hypothesis.description)

    def test_generate_from_learning_model(self):
        """Test converting model learning to hypothesis."""
        learning = {
            "learning_id": "kl-model123",
            "learning_type": "model",
            "agent_filter": "chagatai",
            "pattern_key": "anthropic:claude-opus-4-6",
            "confidence": 0.9,
            "recommendation": '{"action": "use_model", "model_provider": "anthropic", "model_id": "claude-opus-4-6", "expected_quality": "0.85"}',
            "evidence": '{"avg_quality": "0.85", "sample_size": 25}'
        }

        hypothesis = self.generator._convert_learning_to_hypothesis(learning)

        self.assertIsNotNone(hypothesis)
        self.assertEqual(hypothesis.agent, "chagatai")
        self.assertEqual(hypothesis.variable_type, "model")
        self.assertIn("claude-opus-4-6", hypothesis.treatment_value)

    def test_generate_from_learning_invalid_json(self):
        """Test handling of invalid JSON in learning data."""
        learning = {
            "learning_id": "kl-bad123",
            "learning_type": "skill_hint",
            "agent_filter": "test",
            "pattern_key": "/test",
            "confidence": 0.5,
            "recommendation": "invalid json {{{",
            "evidence": "{}"
        }

        hypothesis = self.generator._convert_learning_to_hypothesis(learning)

        # Should return None for invalid JSON
        self.assertIsNone(hypothesis)

    def test_estimate_improvement(self):
        """Test improvement percentage estimation."""
        # High quality -> lower improvement estimate
        high = self.generator._estimate_improvement("0.85")
        self.assertEqual(high, "5")

        # Medium quality -> medium improvement
        medium = self.generator._estimate_improvement("0.7")
        self.assertEqual(medium, "8")

        # Low quality -> higher improvement
        low = self.generator._estimate_improvement("0.5")
        self.assertEqual(low, "12")

        # Invalid input -> default
        invalid = self.generator._estimate_improvement("invalid")
        self.assertEqual(invalid, "5")


class TestIntegration(unittest.TestCase):
    """Integration tests with mocked Neo4j."""

    def setUp(self):
        """Set up mocked Neo4j driver."""
        self.mock_driver = Mock()
        self.mock_result = Mock()
        self.mock_session = Mock()

    def test_generate_for_agent_with_learnings(self):
        """Test generating hypotheses when KublaiLearning nodes exist."""
        # Mock learning query result
        learning_record = {
            "l": {
                "learning_id": "kl-test123",
                "learning_type": "skill_hint",
                "agent_filter": "temujin",
                "pattern_key": "/horde-implement",
                "confidence": 0.85,
                "recommendation": '{"action": "use_skill_hint", "skill_hint": "/horde-implement", "expected_success_rate": "0.75"}',
                "evidence": '{"success_rate": "0.75"}'
            }
        }

        self.mock_session.run.return_value = [learning_record]
        self.mock_driver.session.return_value.__enter__ = Mock(return_value=self.mock_session)
        self.mock_driver.session.return_value.__exit__ = Mock(return_value=False)

        generator = HypothesisGenerator(self.mock_driver)
        hypotheses = generator._generate_from_learnings("temujin")

        self.assertGreater(len(hypotheses), 0)
        self.assertEqual(hypotheses[0].agent, "temujin")
        self.assertEqual(hypotheses[0].variable_type, "skill_hint")

    def test_generate_from_failures(self):
        """Test generating hypotheses from failure patterns."""
        # Mock failure query result
        failure_records = [
            {"agent": "mongke", "error_type": "timeout", "failure_count": 5, "total_failures": 8},
            {"agent": "mongke", "error_type": "no_output", "failure_count": 4, "total_failures": 4},
        ]

        self.mock_session.run.return_value = failure_records
        self.mock_driver.session.return_value.__enter__ = Mock(return_value=self.mock_session)
        self.mock_driver.session.return_value.__exit__ = Mock(return_value=False)

        generator = HypothesisGenerator(self.mock_driver)
        hypotheses = generator._generate_from_failures("mongke")

        self.assertGreater(len(hypotheses), 0)
        # Should generate timeout hypothesis
        timeout_hyp = next((h for h in hypotheses if "timeout" in h.description.lower()), None)
        self.assertIsNotNone(timeout_hyp)


if __name__ == "__main__":
    unittest.main()
