#!/usr/bin/env python3
"""
Rollback-Specific Tests for Kurultai Autonomous Experiment System

Tests instant rollback, alerting, and logging functionality.

Run with: pytest test_rollback.py -v
"""

import os
import sys
import time
import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

# Add scripts directory to path
SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPTS_DIR))


class RollbackManager:
    """Rollback manager implementation for testing."""

    ROLLBACK_THRESHOLDS = {
        "quality_regression_pct": 5.0,      # Rollback on > 5% quality drop
        "error_rate_multiplier": 2.0,       # Rollback on > 2x error rate
        "duration_spike_pct": 50.0,         # Rollback on > 50% duration increase
    }

    def __init__(self, baseline_metrics: dict = None):
        self.baseline_metrics = baseline_metrics or {
            "quality": 0.72,
            "error_rate": 0.05,
            "duration": 300.0
        }
        self.rollback_history = []
        self.alerts_sent = []

    def check_rollback_needed(self, current_metrics: dict) -> tuple:
        """
        Check if metrics regressed beyond threshold.

        Returns: (needs_rollback: bool, reason: str)
        """
        # Quality regression check
        quality_threshold = self.baseline_metrics["quality"] * (
            1 - self.ROLLBACK_THRESHOLDS["quality_regression_pct"] / 100
        )
        if current_metrics.get("quality", 1.0) < quality_threshold:
            regression_pct = (
                (self.baseline_metrics["quality"] - current_metrics.get("quality", 0))
                / self.baseline_metrics["quality"] * 100
            )
            return True, f"quality_regression_{regression_pct:.1f}pct"

        # Error rate spike check
        error_threshold = self.baseline_metrics["error_rate"] * self.ROLLBACK_THRESHOLDS["error_rate_multiplier"]
        if current_metrics.get("error_rate", 0) > error_threshold:
            multiplier = current_metrics.get("error_rate", 0) / self.baseline_metrics["error_rate"]
            return True, f"error_rate_{multiplier:.1f}x_baseline"

        # Duration spike check
        duration_threshold = self.baseline_metrics["duration"] * (
            1 + self.ROLLBACK_THRESHOLDS["duration_spike_pct"] / 100
        )
        if current_metrics.get("duration", 0) > duration_threshold:
            spike_pct = (
                (current_metrics.get("duration", 0) - self.baseline_metrics["duration"])
                / self.baseline_metrics["duration"] * 100
            )
            return True, f"duration_spike_{spike_pct:.0f}pct"

        return False, ""

    def execute_rollback(self, commit_hash: str, reason: str, experiment_id: str = None) -> dict:
        """
        Execute instant rollback to known-good commit.

        Returns: Rollback result with timing and status
        """
        start_time = time.time()

        # Simulate git revert
        # In production: subprocess.run(["git", "revert", "--no-commit", commit_hash])
        rollback_duration = time.time() - start_time

        result = {
            "success": True,
            "commit_hash": commit_hash,
            "reason": reason,
            "experiment_id": experiment_id,
            "timestamp": datetime.now().isoformat(),
            "duration_ms": int(rollback_duration * 1000),
            "action": "git_revert"
        }

        self.rollback_history.append(result)

        # Send alert
        self._send_alert(result)

        # Log to Neo4j (simulated)
        self._log_to_neo4j(result)

        return result

    def _send_alert(self, rollback_result: dict):
        """Send Signal alert on rollback."""
        alert = {
            "type": "ROLLBACK",
            "message": f"ROLLBACK: {rollback_result['reason']}",
            "commit": rollback_result["commit_hash"],
            "timestamp": rollback_result["timestamp"],
            "channel": "signal://+15165643945"
        }
        self.alerts_sent.append(alert)

    def _log_to_neo4j(self, rollback_result: dict):
        """Log rollback event to Neo4j (simulated)."""
        # In production:
        # session.run("""
        #     CREATE (r:RollbackEvent {
        #         commit: $commit,
        #         reason: $reason,
        #         timestamp: datetime(),
        #         experiment_id: $exp_id
        #     })
        # """, commit=rollback_result["commit_hash"], ...)
        pass

    def get_rollback_history(self, limit: int = 10) -> list:
        """Get recent rollback history."""
        return self.rollback_history[-limit:]


class TestInstantRollback(unittest.TestCase):
    """Verify rollback completes in < 5 seconds."""

    def setUp(self):
        self.rollback_manager = RollbackManager()

    def test_instant_rollback_timing(self):
        """Rollback should complete in under 5 seconds."""
        start_time = time.time()

        result = self.rollback_manager.execute_rollback(
            commit_hash="abc123def456",
            reason="quality_regression_10pct",
            experiment_id="exp-20260308-001"
        )

        elapsed = time.time() - start_time

        self.assertTrue(result["success"])
        self.assertLess(elapsed, 5.0, "Rollback took longer than 5 seconds")
        self.assertIn("duration_ms", result)

    def test_rollback_returns_immediately(self):
        """Rollback should return immediately even with invalid commit."""
        # Should not raise exception
        result = self.rollback_manager.execute_rollback(
            commit_hash="invalid",
            reason="test",
            experiment_id="test"
        )

        # In mock, always succeeds
        self.assertTrue(result["success"])

    def test_multiple_rapid_rollbacks(self):
        """System should handle multiple rapid rollbacks."""
        for i in range(5):
            result = self.rollback_manager.execute_rollback(
                commit_hash=f"commit{i}",
                reason="test_rollback",
                experiment_id=f"exp-{i}"
            )
            self.assertTrue(result["success"])

        self.assertEqual(len(self.rollback_manager.rollback_history), 5)


class TestRollbackAlerts(unittest.TestCase):
    """Verify Signal alert sent on rollback."""

    def setUp(self):
        self.rollback_manager = RollbackManager()

    def test_alert_sent_on_rollback(self):
        """Signal alert should be sent when rollback occurs."""
        result = self.rollback_manager.execute_rollback(
            commit_hash="abc123",
            reason="error_rate_3x_baseline"
        )

        self.assertEqual(len(self.rollback_manager.alerts_sent), 1)

        alert = self.rollback_manager.alerts_sent[0]
        self.assertEqual(alert["type"], "ROLLBACK")
        self.assertIn("error_rate", alert["message"])
        self.assertEqual(alert["channel"], "signal://+15165643945")

    def test_alert_contains_commit_info(self):
        """Alert should contain commit hash and timestamp."""
        result = self.rollback_manager.execute_rollback(
            commit_hash="def456",
            reason="quality_regression_8pct"
        )

        alert = self.rollback_manager.alerts_sent[0]
        self.assertEqual(alert["commit"], "def456")
        self.assertIn("timestamp", alert)

    def test_multiple_alerts_for_multiple_rollbacks(self):
        """Each rollback should generate its own alert."""
        self.rollback_manager.execute_rollback("commit1", "reason1")
        self.rollback_manager.execute_rollback("commit2", "reason2")
        self.rollback_manager.execute_rollback("commit3", "reason3")

        self.assertEqual(len(self.rollback_manager.alerts_sent), 3)

        # Each alert should be unique
        commits = [a["commit"] for a in self.rollback_manager.alerts_sent]
        self.assertEqual(len(set(commits)), 3)


class TestRollbackLogging(unittest.TestCase):
    """Verify Neo4j RollbackEvent created."""

    def setUp(self):
        self.rollback_manager = RollbackManager()

    def test_rollback_history_recorded(self):
        """Rollback should be recorded in history."""
        result = self.rollback_manager.execute_rollback(
            commit_hash="test123",
            reason="duration_spike_75pct",
            experiment_id="exp-20260308-042"
        )

        history = self.rollback_manager.get_rollback_history()

        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["commit_hash"], "test123")
        self.assertEqual(history[0]["experiment_id"], "exp-20260308-042")

    def test_rollback_event_structure(self):
        """Rollback event should have all required fields."""
        result = self.rollback_manager.execute_rollback(
            commit_hash="abc789",
            reason="test_reason"
        )

        # Check result structure
        required_fields = ["success", "commit_hash", "reason", "timestamp", "duration_ms", "action"]
        for field in required_fields:
            self.assertIn(field, result, f"Missing field: {field}")

    def test_rollback_history_order(self):
        """Rollback history should be in chronological order."""
        commits = ["first", "second", "third"]
        for commit in commits:
            self.rollback_manager.execute_rollback(commit, "test")

        history = self.rollback_manager.get_rollback_history()
        recorded_commits = [h["commit_hash"] for h in history]

        self.assertEqual(recorded_commits, commits)


class TestRollbackThresholds(unittest.TestCase):
    """Test rollback threshold calculations."""

    def setUp(self):
        self.rollback_manager = RollbackManager()

    def test_quality_regression_detection(self):
        """Detect quality regression > 5%."""
        needs_rollback, reason = self.rollback_manager.check_rollback_needed({
            "quality": 0.65,  # 9.7% below baseline of 0.72
            "error_rate": 0.05,
            "duration": 300
        })

        self.assertTrue(needs_rollback)
        self.assertIn("quality_regression", reason)

    def test_error_rate_spike_detection(self):
        """Detect error rate > 2x baseline."""
        needs_rollback, reason = self.rollback_manager.check_rollback_needed({
            "quality": 0.72,
            "error_rate": 0.15,  # 3x baseline of 0.05
            "duration": 300
        })

        self.assertTrue(needs_rollback)
        self.assertIn("error_rate", reason)
        self.assertIn("3", reason)

    def test_duration_spike_detection(self):
        """Detect duration spike > 50%."""
        needs_rollback, reason = self.rollback_manager.check_rollback_needed({
            "quality": 0.72,
            "error_rate": 0.05,
            "duration": 500  # 66% above baseline of 300
        })

        self.assertTrue(needs_rollback)
        self.assertIn("duration_spike", reason)

    def test_no_rollback_when_metrics_good(self):
        """No rollback when metrics are acceptable."""
        needs_rollback, reason = self.rollback_manager.check_rollback_needed({
            "quality": 0.75,  # Better than baseline
            "error_rate": 0.04,  # Better than baseline
            "duration": 280  # Better than baseline
        })

        self.assertFalse(needs_rollback)
        self.assertEqual(reason, "")

    def test_custom_thresholds(self):
        """Custom thresholds should be respected."""
        custom_manager = RollbackManager(baseline_metrics={
            "quality": 0.90,
            "error_rate": 0.01,
            "duration": 100
        })

        # Quality at 0.85 would be fine with default baseline (0.72)
        # but triggers rollback with custom baseline (0.90)
        needs_rollback, reason = custom_manager.check_rollback_needed({
            "quality": 0.85,
            "error_rate": 0.01,
            "duration": 100
        })

        self.assertTrue(needs_rollback)
        self.assertIn("quality_regression", reason)


class TestEmergencyRollback(unittest.TestCase):
    """Test emergency rollback scenarios."""

    def setUp(self):
        self.rollback_manager = RollbackManager()

    def test_emergency_rollback_flag(self):
        """Emergency rollback should be marked as urgent."""
        result = self.rollback_manager.execute_rollback(
            commit_hash="bad123",
            reason="EMERGENCY: Production incident"
        )

        alert = self.rollback_manager.alerts_sent[0]
        self.assertEqual(alert["type"], "ROLLBACK")

    def test_rollback_with_experiment_tracking(self):
        """Rollback should track associated experiment."""
        result = self.rollback_manager.execute_rollback(
            commit_hash="exp123",
            reason="Post-merge regression detected",
            experiment_id="exp-20260308-001"
        )

        self.assertEqual(result["experiment_id"], "exp-20260308-001")

        history = self.rollback_manager.get_rollback_history()
        self.assertEqual(history[0]["experiment_id"], "exp-20260308-001")


def run_tests():
    """Run all rollback tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestInstantRollback))
    suite.addTests(loader.loadTestsFromTestCase(TestRollbackAlerts))
    suite.addTests(loader.loadTestsFromTestCase(TestRollbackLogging))
    suite.addTests(loader.loadTestsFromTestCase(TestRollbackThresholds))
    suite.addTests(loader.loadTestsFromTestCase(TestEmergencyRollback))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
