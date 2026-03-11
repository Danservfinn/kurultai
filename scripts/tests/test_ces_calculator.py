#!/usr/bin/env python3
"""
Unit tests for CES Calculator Module

Tests cover:
1. CES calculation with full human review
2. CES calculation with proxy metrics only
3. CES calculation with partial data
4. Agent-specific weight application
5. Efficiency cap at 1.5x
6. Success rate penalties
7. Impact calculation
8. Batch calculation
"""

import unittest
import sys
import os

# Add scripts directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ces_calculator import (
    calculate_ces,
    calculate_ces_batch,
    calculate_success_rate,
    calculate_quality_score,
    calculate_efficiency,
    calculate_impact,
    get_ces_stats,
    AGENT_WEIGHTS,
    DEFAULT_WEIGHTS,
    EFFICIENCY_CAP,
    CESResult,
)


class TestSuccessRateCalculation(unittest.TestCase):
    """Tests for success rate component calculation."""

    def test_completed_task(self):
        """Completed tasks get 1.0."""
        task = {"status": "COMPLETED"}
        result = calculate_success_rate(task)
        self.assertEqual(result, 1.0)

    def test_done_task(self):
        """Done status is treated as completed."""
        task = {"status": "DONE"}
        result = calculate_success_rate(task)
        self.assertEqual(result, 1.0)

    def test_failed_task(self):
        """Failed tasks get 0.0."""
        task = {"status": "FAILED"}
        result = calculate_success_rate(task)
        self.assertEqual(result, 0.0)

    def test_rework_required(self):
        """Rework required reduces score to 0.5."""
        task = {"status": "COMPLETED", "rework_required": True}
        result = calculate_success_rate(task)
        self.assertEqual(result, 0.5)

    def test_critical_failure_penalty(self):
        """Critical task failure applies -0.15 penalty."""
        task = {"status": "FAILED", "priority": "critical"}
        result = calculate_success_rate(task, "critical")
        # 0.0 base - 0.15 penalty, floored at 0.0
        self.assertEqual(result, 0.0)

    def test_high_failure_penalty(self):
        """High priority task failure applies -0.08 penalty."""
        task = {"status": "FAILED", "priority": "high"}
        result = calculate_success_rate(task, "high")
        self.assertEqual(result, 0.0)

    def test_pending_task(self):
        """Pending tasks get 0.0."""
        task = {"status": "PENDING"}
        result = calculate_success_rate(task)
        self.assertEqual(result, 0.0)

    def test_floor_at_zero(self):
        """Success rate cannot go below 0.0."""
        task = {"status": "FAILED", "priority": "critical"}
        result = calculate_success_rate(task, "critical")
        self.assertGreaterEqual(result, 0.0)


class TestQualityScoreCalculation(unittest.TestCase):
    """Tests for quality score component calculation."""

    def test_human_review_perfect(self):
        """Human review score 10/10 gives 1.0."""
        task = {"status": "COMPLETED"}
        human_review = {"score": 10}
        result, source = calculate_quality_score(task, human_review)
        self.assertEqual(result, 1.0)
        self.assertEqual(source, "human_review")

    def test_human_review_zero(self):
        """Human review score 0/10 gives 0.0."""
        task = {"status": "COMPLETED"}
        human_review = {"score": 0}
        result, source = calculate_quality_score(task, human_review)
        self.assertEqual(result, 0.0)
        self.assertEqual(source, "human_review")

    def test_human_review_middle(self):
        """Human review score 5/10 gives 0.5."""
        task = {"status": "COMPLETED"}
        human_review = {"score": 5}
        result, source = calculate_quality_score(task, human_review)
        self.assertEqual(result, 0.5)
        self.assertEqual(source, "human_review")

    def test_proxy_metrics_default(self):
        """Proxy metrics use default values when not specified."""
        task = {"status": "COMPLETED"}
        result, source = calculate_quality_score(task)
        # Default values: artifact=1.5, tool=1.5, rule=1.5 (all on 0-3 scale)
        # (1.5/3 * 0.4) + (1.5/3 * 0.3) + (1.5/3 * 0.3) = 0.5
        self.assertEqual(result, 0.5)
        self.assertEqual(source, "proxy")

    def test_proxy_metrics_high(self):
        """High proxy metrics give high quality score."""
        task = {
            "artifact_quality_score": 3.0,
            "tool_efficiency_score": 3.0,
            "rule_adherence_score": 3.0,
        }
        result, source = calculate_quality_score(task)
        # (3/3 * 0.4) + (3/3 * 0.3) + (3/3 * 0.3) = 1.0
        self.assertEqual(result, 1.0)
        self.assertEqual(source, "proxy")

    def test_proxy_metrics_low(self):
        """Low proxy metrics give low quality score."""
        task = {
            "artifact_quality_score": 0.0,
            "tool_efficiency_score": 0.0,
            "rule_adherence_score": 0.0,
        }
        result, source = calculate_quality_score(task)
        self.assertEqual(result, 0.0)
        self.assertEqual(source, "proxy")


class TestEfficiencyCalculation(unittest.TestCase):
    """Tests for efficiency component calculation."""

    def test_exact_baseline(self):
        """Task at baseline duration gives efficiency 1.0."""
        task = {"duration_seconds": 600}
        result = calculate_efficiency(task, baseline_duration=600)
        self.assertEqual(result, 1.0)

    def test_faster_than_baseline(self):
        """Task faster than baseline gives efficiency > 1.0, capped at 1.5."""
        task = {"duration_seconds": 300}  # Half the time
        result = calculate_efficiency(task, baseline_duration=600)
        # 600/300 = 2.0, but capped at 1.5
        self.assertEqual(result, EFFICIENCY_CAP)

    def test_slower_than_baseline(self):
        """Task slower than baseline gives efficiency < 1.0."""
        task = {"duration_seconds": 1200}  # Double the time
        result = calculate_efficiency(task, baseline_duration=600)
        self.assertEqual(result, 0.5)  # 600/1200 = 0.5

    def test_efficiency_cap(self):
        """Efficiency is capped at 1.5 (diminishing returns)."""
        task = {"duration_seconds": 100}  # Very fast
        result = calculate_efficiency(task, baseline_duration=600)
        # 600/100 = 6.0, but capped at 1.5
        self.assertEqual(result, EFFICIENCY_CAP)

    def test_no_duration(self):
        """Tasks without duration get default 0.7."""
        task = {}
        result = calculate_efficiency(task)
        self.assertEqual(result, 0.7)

    def test_zero_duration(self):
        """Zero duration gets default 0.7."""
        task = {"duration_seconds": 0}
        result = calculate_efficiency(task)
        self.assertEqual(result, 0.7)

    def test_no_baseline(self):
        """Missing baseline uses default or task's baseline."""
        task = {"duration_seconds": 600, "baseline_duration": 500}
        result = calculate_efficiency(task)  # No explicit baseline
        # Uses task's baseline_duration
        self.assertAlmostEqual(result, 500/600, places=2)


class TestImpactCalculation(unittest.TestCase):
    """Tests for impact component calculation."""

    def test_critical_priority(self):
        """Critical priority gives 1.0 base weight."""
        task = {"priority": "critical"}
        result = calculate_impact(task)
        # 0.5 * 1.0 + 0.3 * 0.3 + 0.2 * 0.5 = 0.5 + 0.09 + 0.1 = 0.69
        self.assertGreater(result, 0.5)
        self.assertLessEqual(result, 1.0)

    def test_high_priority(self):
        """High priority gives 0.75 base weight."""
        task = {"priority": "high"}
        result = calculate_impact(task)
        # 0.5 * 0.75 + 0.3 * 0.3 + 0.2 * 0.5 = 0.375 + 0.09 + 0.1 = 0.565
        self.assertGreater(result, 0.4)

    def test_normal_priority(self):
        """Normal priority gives 0.5 base weight."""
        task = {"priority": "normal"}
        result = calculate_impact(task)
        # 0.5 * 0.5 + 0.3 * 0.3 + 0.2 * 0.5 = 0.25 + 0.09 + 0.1 = 0.44
        self.assertGreater(result, 0.3)

    def test_low_priority(self):
        """Low priority gives 0.25 base weight."""
        task = {"priority": "low"}
        result = calculate_impact(task)
        # 0.5 * 0.25 + 0.3 * 0.3 + 0.2 * 0.5 = 0.125 + 0.09 + 0.1 = 0.315
        self.assertGreater(result, 0.2)

    def test_downstream_enables(self):
        """Downstream enables increases impact."""
        task = {"priority": "normal", "downstream_enables": 5}
        result = calculate_impact(task)
        # downstream_norm = min(1.0, 5/5) = 1.0
        # 0.5 * 0.5 + 0.3 * 1.0 + 0.2 * 0.5 = 0.25 + 0.3 + 0.1 = 0.65
        self.assertGreater(result, 0.6)

    def test_skill_match(self):
        """Higher skill match increases impact."""
        task = {"priority": "normal", "skill_match": 1.0}
        result = calculate_impact(task)
        # 0.5 * 0.5 + 0.3 * 0.3 + 0.2 * 1.0 = 0.25 + 0.09 + 0.2 = 0.54
        self.assertGreater(result, 0.5)


class TestCESCalculation(unittest.TestCase):
    """Tests for full CES calculation."""

    def test_full_ces_with_human_review(self):
        """Test 1: CES calculation with full human review."""
        task = {
            "task_id": "test-001",
            "agent": "temujin",
            "status": "COMPLETED",
            "priority": "high",
            "duration_seconds": 500,
        }
        human_review = {"score": 8}  # 80%
        baseline = 600

        result = calculate_ces(task, human_review=human_review, baseline_duration=baseline)

        self.assertIn("ces", result)
        self.assertIn("components", result)
        self.assertEqual(result["calculation_source"], "full")
        self.assertEqual(result["components"]["success_rate"], 1.0)
        self.assertEqual(result["components"]["quality_score"], 0.8)
        self.assertGreater(result["ces"], 0.5)

    def test_ces_with_proxy_metrics(self):
        """Test 2: CES calculation with proxy metrics only."""
        task = {
            "task_id": "test-002",
            "agent": "mongke",
            "status": "COMPLETED",
            "priority": "normal",
            "duration_seconds": 600,
            "artifact_quality_score": 2.5,
            "tool_efficiency_score": 2.0,
            "rule_adherence_score": 2.5,
        }
        baseline = 600

        result = calculate_ces(task, baseline_duration=baseline)

        self.assertEqual(result["calculation_source"], "proxy")
        self.assertEqual(result["agent"], "mongke")
        self.assertEqual(result["components"]["success_rate"], 1.0)

    def test_ces_with_partial_data(self):
        """Test 3: CES calculation with partial data."""
        task = {
            "task_id": "test-003",
            "agent": "chagatai",
            "status": "COMPLETED",
            "priority": "normal",
            # No duration, no action scores
        }

        result = calculate_ces(task)

        self.assertEqual(result["calculation_source"], "partial")
        self.assertEqual(result["components"]["success_rate"], 1.0)
        # Should use defaults for missing values
        self.assertGreater(result["ces"], 0.0)

    def test_agent_specific_weights(self):
        """Test 4: Agent-specific weight application."""
        task_base = {
            "status": "COMPLETED",
            "priority": "normal",
            "duration_seconds": 600,
            "artifact_quality_score": 2.0,
            "tool_efficiency_score": 2.0,
            "rule_adherence_score": 2.0,
        }

        results = {}
        for agent in ["temujin", "mongke", "chagatai", "jochi", "ogedei", "kublai"]:
            task = dict(task_base)
            task["agent"] = agent
            result = calculate_ces(task, baseline_duration=600)
            results[agent] = result["ces"]
            # Verify weights used match agent weights
            self.assertEqual(result["weights_used"], AGENT_WEIGHTS[agent])

        # Different agents should produce different CES for same metrics
        # (due to different weights)
        unique_ces = len(set(results.values()))
        self.assertGreater(unique_ces, 1)

    def test_efficiency_cap(self):
        """Test 5: Efficiency cap at 1.5x."""
        # Very fast task
        task = {
            "task_id": "test-005",
            "agent": "temujin",
            "status": "COMPLETED",
            "duration_seconds": 100,  # Very fast
        }
        baseline = 1000  # Expected 16+ minutes

        result = calculate_ces(task, baseline_duration=baseline)

        # Efficiency should be capped at 1.5
        self.assertLessEqual(result["components"]["efficiency"], EFFICIENCY_CAP)

    def test_success_rate_penalties(self):
        """Test 6: Success rate penalties."""
        # Failed critical task
        task_critical = {
            "task_id": "test-006a",
            "agent": "temujin",
            "status": "FAILED",
            "priority": "critical",
        }
        result_critical = calculate_ces(task_critical)
        # Should have 0.0 success rate (or with penalty applied)
        self.assertEqual(result_critical["components"]["success_rate"], 0.0)

        # Failed high priority task
        task_high = {
            "task_id": "test-006b",
            "agent": "temujin",
            "status": "FAILED",
            "priority": "high",
        }
        result_high = calculate_ces(task_high)
        self.assertEqual(result_high["components"]["success_rate"], 0.0)

        # Rework required
        task_rework = {
            "task_id": "test-006c",
            "agent": "temujin",
            "status": "COMPLETED",
            "rework_required": True,
        }
        result_rework = calculate_ces(task_rework)
        self.assertEqual(result_rework["components"]["success_rate"], 0.5)

    def test_impact_calculation(self):
        """Test 7: Impact calculation."""
        # High impact task
        task_high_impact = {
            "task_id": "test-007",
            "agent": "temujin",
            "status": "COMPLETED",
            "priority": "critical",
            "downstream_enables": 5,
            "skill_match": 1.0,
        }
        result_high = calculate_ces(task_high_impact)

        # Low impact task
        task_low_impact = {
            "task_id": "test-007b",
            "agent": "temujin",
            "status": "COMPLETED",
            "priority": "low",
            "downstream_enables": 0,
            "skill_match": 0.2,
        }
        result_low = calculate_ces(task_low_impact)

        # High impact should have higher impact score
        self.assertGreater(
            result_high["components"]["impact"],
            result_low["components"]["impact"]
        )

    def test_batch_calculation(self):
        """Test 8: Batch calculation."""
        tasks = [
            {
                "task_id": "batch-001",
                "agent": "temujin",
                "status": "COMPLETED",
                "priority": "high",
                "duration_seconds": 500,
            },
            {
                "task_id": "batch-002",
                "agent": "mongke",
                "status": "COMPLETED",
                "priority": "normal",
                "duration_seconds": 600,
            },
            {
                "task_id": "batch-003",
                "agent": "chagatai",
                "status": "FAILED",
                "priority": "low",
            },
        ]

        baselines = {
            "batch-001": 600,
            "batch-002": 600,
        }

        results = calculate_ces_batch(tasks, baseline_durations=baselines)

        self.assertEqual(len(results), 3)

        for result in results:
            self.assertIn("ces_result", result)
            ces = result["ces_result"]
            self.assertIn("ces", ces)
            self.assertIn("components", ces)

        # Verify each task has CES result
        task_ids = [r["task_id"] for r in results]
        self.assertIn("batch-001", task_ids)
        self.assertIn("batch-002", task_ids)
        self.assertIn("batch-003", task_ids)


class TestCESStats(unittest.TestCase):
    """Tests for CES statistics calculation."""

    def test_empty_stats(self):
        """Empty list returns null stats."""
        stats = get_ces_stats([])
        self.assertEqual(stats["count"], 0)
        self.assertIsNone(stats["mean"])

    def test_single_value_stats(self):
        """Single value returns correct stats."""
        results = [{"ces": 0.75}]
        stats = get_ces_stats(results)
        self.assertEqual(stats["count"], 1)
        self.assertEqual(stats["mean"], 0.75)
        self.assertEqual(stats["median"], 0.75)
        self.assertIsNone(stats["std_dev"])  # Need 2+ for std_dev

    def test_multiple_value_stats(self):
        """Multiple values return correct stats."""
        results = [
            {"ces": 0.9},
            {"ces": 0.8},
            {"ces": 0.7},
            {"ces": 0.6},
        ]
        stats = get_ces_stats(results)

        self.assertEqual(stats["count"], 4)
        self.assertEqual(stats["mean"], 0.75)
        self.assertEqual(stats["median"], 0.75)
        self.assertIsNotNone(stats["std_dev"])

    def test_distribution(self):
        """Distribution categorization works correctly."""
        results = [
            {"ces": 0.95},  # excellent
            {"ces": 0.85},  # good
            {"ces": 0.75},  # good
            {"ces": 0.55},  # acceptable
            {"ces": 0.35},  # poor
        ]
        stats = get_ces_stats(results)

        self.assertEqual(stats["distribution"]["excellent_90+"], 1)
        self.assertEqual(stats["distribution"]["good_70_89"], 2)
        self.assertEqual(stats["distribution"]["acceptable_50_69"], 1)
        self.assertEqual(stats["distribution"]["poor_below_50"], 1)


class TestCustomWeights(unittest.TestCase):
    """Tests for custom weight application."""

    def test_custom_weights_override(self):
        """Custom weights override agent defaults."""
        task = {
            "task_id": "custom-001",
            "agent": "temujin",
            "status": "COMPLETED",
            "duration_seconds": 600,
        }

        custom = {
            "success_rate": 0.5,
            "quality": 0.3,
            "efficiency": 0.1,
            "impact": 0.1,
        }

        result = calculate_ces(task, agent_weights=custom)

        self.assertEqual(result["weights_used"], custom)

    def test_unknown_agent_uses_defaults(self):
        """Unknown agent uses default weights."""
        task = {
            "task_id": "unknown-001",
            "agent": "unknown_agent",
            "status": "COMPLETED",
        }

        result = calculate_ces(task)

        self.assertEqual(result["weights_used"], DEFAULT_WEIGHTS)


if __name__ == "__main__":
    # Run tests with verbose output
    unittest.main(verbosity=2)
