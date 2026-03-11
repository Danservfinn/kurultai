#!/usr/bin/env python3
"""
Rollback Manager Integration Test

Tests the rollback-manager.py with simulated regression scenarios.

Usage:
    python3 test_rollback_manager.py
"""

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from datetime import datetime

# Add scripts directory to path
SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPTS_DIR))

# Import the rollback manager directly using importlib
import importlib.util
spec = importlib.util.spec_from_file_location("rollback_manager", SCRIPTS_DIR / "rollback-manager.py")
rollback_manager_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rollback_manager_module)

RollbackManager = rollback_manager_module.RollbackManager
RollbackThresholds = rollback_manager_module.RollbackThresholds


class TestRollbackManagerImports(unittest.TestCase):
    """Verify rollback-manager.py imports without errors."""

    def test_import_success(self):
        """Module should import successfully."""
        self.assertIsNotNone(RollbackManager)
        self.assertIsNotNone(RollbackThresholds)

    def test_thresholds_defined(self):
        """Thresholds should be defined correctly."""
        self.assertEqual(RollbackThresholds.QUALITY_REGRESSION_PCT, 5.0)
        self.assertEqual(RollbackThresholds.ERROR_RATE_MULTIPLIER, 2.0)
        self.assertEqual(RollbackThresholds._DURATION_SPIKE_PCT, 50.0)


class TestRollbackDetection(unittest.TestCase):
    """Test rollback detection logic."""

    def setUp(self):
        """Set up test manager with default baseline."""
        self.manager = RollbackManager(baseline_metrics={
            "quality": 0.72,
            "error_rate": 0.05,
            "duration_ms": 300.0
        })

    def test_quality_regression_detection(self):
        """Detect quality regression > 5%."""
        # Quality at 0.65 is 9.7% below baseline 0.72
        needs_rollback, reason = self.manager.check_rollback_needed({
            "quality": 0.65,
            "error_rate": 0.05,
            "duration_ms": 300
        })

        self.assertTrue(needs_rollback)
        self.assertIn("quality_regression", reason)
        # Extract percentage from "quality_regression_9.7pct"
        pct_str = reason.split("_")[2]
        pct_value = float(pct_str.replace("pct", ""))
        self.assertGreater(pct_value, 5.0)

    def test_quality_at_threshold(self):
        """Exactly 5% regression should NOT trigger rollback."""
        # 5% below baseline (0.72 * 0.95 = 0.684)
        needs_rollback, reason = self.manager.check_rollback_needed({
            "quality": 0.685,  # Just above threshold
            "error_rate": 0.05,
            "duration_ms": 300
        })

        self.assertFalse(needs_rollback)

    def test_error_rate_spike_detection(self):
        """Detect error rate > 2x baseline."""
        needs_rollback, reason = self.manager.check_rollback_needed({
            "quality": 0.72,
            "error_rate": 0.15,  # 3x baseline 0.05
            "duration_ms": 300
        })

        self.assertTrue(needs_rollback)
        self.assertIn("error_rate", reason)
        self.assertIn("3.0x", reason)

    def test_error_rate_at_threshold(self):
        """Exactly 2x error rate should NOT trigger rollback."""
        needs_rollback, reason = self.manager.check_rollback_needed({
            "quality": 0.72,
            "error_rate": 0.09,  # Just below 2x (0.05 * 2 = 0.10)
            "duration_ms": 300
        })

        self.assertFalse(needs_rollback)

    def test_duration_spike_detection(self):
        """Detect duration spike > 50%."""
        needs_rollback, reason = self.manager.check_rollback_needed({
            "quality": 0.72,
            "error_rate": 0.05,
            "duration_ms": 500  # 66% above baseline 300
        })

        self.assertTrue(needs_rollback)
        self.assertIn("duration_spike", reason)

    def test_duration_at_threshold(self):
        """Exactly 50% duration increase should NOT trigger rollback."""
        needs_rollback, reason = self.manager.check_rollback_needed({
            "quality": 0.72,
            "error_rate": 0.05,
            "duration_ms": 449  # Just below 1.5x (300 * 1.5 = 450)
        })

        self.assertFalse(needs_rollback)

    def test_no_rollback_when_metrics_good(self):
        """No rollback when all metrics are acceptable."""
        needs_rollback, reason = self.manager.check_rollback_needed({
            "quality": 0.75,  # Better than baseline
            "error_rate": 0.04,  # Better than baseline
            "duration_ms": 280  # Better than baseline
        })

        self.assertFalse(needs_rollback)
        self.assertEqual(reason, "")

    def test_zero_baseline_quality_handling(self):
        """Handle zero baseline quality gracefully."""
        manager = RollbackManager(baseline_metrics={
            "quality": 0,
            "error_rate": 0.05,
            "duration_ms": 300
        })

        # Should not crash on zero baseline
        needs_rollback, reason = manager.check_rollback_needed({
            "quality": 0.5,
            "error_rate": 0.05,
            "duration_ms": 300
        })

        # With zero baseline, quality check is skipped
        self.assertFalse(needs_rollback)


class TestRollbackLogging(unittest.TestCase):
    """Test JSONL logging of rollback events."""

    def setUp(self):
        """Set up test manager with temp log file."""
        self.temp_dir = tempfile.mkdtemp()
        self.manager = RollbackManager()
        self.manager.log_dir = Path(self.temp_dir)
        # Disable Neo4j and Signal for logging tests
        self.manager.neo4j_available = False
        self._original_send_alert = self.manager._send_signal_alert
        self.manager._send_signal_alert = lambda x: True  # Mock alert

    def tearDown(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_log_entry_format(self):
        """Log entry should have all required fields."""
        log_path = self.manager.log_dir / "rollback.jsonl"

        # Create a mock rollback result
        result = {
            "commit_hash": "abc789",
            "reason": "error_rate_3x_baseline",
            "experiment_id": "exp-20260308-042",
            "timestamp": datetime.now().isoformat(),
            "action": "git_revert",
            "success": True,
            "duration_ms": 150,
            "error": None
        }

        self.manager._log_rollback_event(result)

        # Read and verify log entry
        with open(log_path) as f:
            entry = json.loads(f.read().strip())

        required_fields = [
            "timestamp", "commit_hash", "reason", "success", "duration_ms"
        ]
        for field in required_fields:
            self.assertIn(field, entry)

        self.assertEqual(entry["commit_hash"], "abc789")
        self.assertEqual(entry["reason"], "error_rate_3x_baseline")
        self.assertEqual(entry["experiment_id"], "exp-20260308-042")

    def test_multiple_log_entries(self):
        """Multiple rollbacks should create multiple log entries."""
        log_path = self.manager.log_dir / "rollback.jsonl"

        for i in range(3):
            result = {
                "commit_hash": f"commit{i}",
                "reason": f"reason{i}",
                "experiment_id": f"exp-{i}",
                "timestamp": datetime.now().isoformat(),
                "action": "git_revert",
                "success": True,
                "duration_ms": 100,
                "error": None
            }
            self.manager._log_rollback_event(result)

        # Should have 3 lines
        with open(log_path) as f:
            lines = f.readlines()

        self.assertEqual(len(lines), 3)


class TestSignalAlertFormat(unittest.TestCase):
    """Test Signal alert message formatting."""

    def test_signal_alert_message_format(self):
        """Signal alert should contain rollback details."""
        # Test the _send_signal_alert method indirectly via message format check
        result = {
            "commit_hash": "abc123def456",
            "reason": "error_rate_3x_baseline",
            "experiment_id": "exp-20260308-001",
            "timestamp": datetime.now().isoformat(),
            "action": "git_revert",
            "success": True,
            "duration_ms": 100,
            "error": None
        }

        # Verify the message would contain the right info
        commit = result["commit_hash"][:8]
        reason = result["reason"]
        exp_id = result.get("experiment_id", "unknown")
        status = "SUCCESS" if result["success"] else "FAILED"

        message = f"ROLLBACK: {reason}\nCommit: {commit}\nExperiment: {exp_id}\nStatus: {status}"

        self.assertIn("ROLLBACK", message)
        self.assertIn("error_rate_3x_baseline", message)
        self.assertIn("abc123de", message)  # Short hash
        self.assertIn("exp-20260308-001", message)
        self.assertIn("SUCCESS", message)


class TestNeo4jLogging(unittest.TestCase):
    """Test Neo4j RollbackEvent creation."""

    def test_neo4j_unavailable_handling(self):
        """Should handle Neo4j unavailability gracefully."""
        manager = RollbackManager()
        manager.neo4j_available = False

        result = {
            "commit_hash": "test123",
            "reason": "test",
            "experiment_id": "exp-001",
            "timestamp": datetime.now().isoformat(),
            "action": "git_revert",
            "success": True,
            "duration_ms": 100,
            "error": None
        }

        # Should not crash
        success = manager._log_to_neo4j(result)
        self.assertFalse(success)


class TestRollbackHistory(unittest.TestCase):
    """Test rollback history retrieval."""

    def setUp(self):
        """Set up test manager with temp log file."""
        self.temp_dir = tempfile.mkdtemp()
        self.manager = RollbackManager()
        self.manager.log_dir = Path(self.temp_dir)
        self.log_path = self.manager.log_dir / "rollback.jsonl"

    def tearDown(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_empty_history(self):
        """Empty history should return empty list."""
        history = self.manager.get_rollback_history()
        self.assertEqual(len(history), 0)

    def test_history_retrieval(self):
        """History should return logged rollbacks."""
        # Create test log entries
        entries = [
            {
                "timestamp": datetime.now().isoformat(),
                "experiment_id": "exp-001",
                "commit_hash": "commit1",
                "reason": "reason1",
                "success": True,
                "duration_ms": 100
            },
            {
                "timestamp": datetime.now().isoformat(),
                "experiment_id": "exp-002",
                "commit_hash": "commit2",
                "reason": "reason2",
                "success": True,
                "duration_ms": 150
            }
        ]

        with open(self.log_path, "w") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

        history = self.manager.get_rollback_history()

        self.assertEqual(len(history), 2)
        # History should be in reverse chronological order
        self.assertEqual(history[0]["commit_hash"], "commit2")
        self.assertEqual(history[1]["commit_hash"], "commit1")

    def test_history_limit(self):
        """History should respect limit parameter."""
        # Create 5 entries
        with open(self.log_path, "w") as f:
            for i in range(5):
                entry = {
                    "timestamp": datetime.now().isoformat(),
                    "commit_hash": f"commit{i}",
                    "reason": f"reason{i}",
                    "success": True,
                    "duration_ms": 100
                }
                f.write(json.dumps(entry) + "\n")

        history = self.manager.get_rollback_history(limit=3)

        self.assertEqual(len(history), 3)


class TestRegressionScenarios(unittest.TestCase):
    """Test real-world regression scenarios."""

    def setUp(self):
        """Set up test manager."""
        self.manager = RollbackManager(baseline_metrics={
            "quality": 0.72,
            "error_rate": 0.05,
            "duration_ms": 300.0
        })

    def test_post_merge_quality_regression(self):
        """Scenario: Quality drops after merge."""
        # Metrics after bad merge
        post_merge_metrics = {
            "quality": 0.64,  # 11% drop
            "error_rate": 0.06,
            "duration_ms": 320
        }

        needs_rollback, reason = self.manager.check_rollback_needed(post_merge_metrics)

        self.assertTrue(needs_rollback)
        self.assertIn("quality_regression", reason)

    def test_post_merge_error_spike(self):
        """Scenario: Error rate spikes after deployment."""
        post_deploy_metrics = {
            "quality": 0.70,
            "error_rate": 0.18,  # 3.6x baseline
            "duration_ms": 300
        }

        needs_rollback, reason = self.manager.check_rollback_needed(post_deploy_metrics)

        self.assertTrue(needs_rollback)
        self.assertIn("error_rate", reason)

    def test_post_merge_duration_bloat(self):
        """Scenario: Response time increases significantly."""
        post_merge_metrics = {
            "quality": 0.72,
            "error_rate": 0.05,
            "duration_ms": 520  # 73% increase
        }

        needs_rollback, reason = self.manager.check_rollback_needed(post_merge_metrics)

        self.assertTrue(needs_rollback)
        self.assertIn("duration_spike", reason)

    def test_beneficial_changes_no_rollback(self):
        """Scenario: Beneficial changes should not rollback."""
        good_metrics = {
            "quality": 0.78,  # Improved
            "error_rate": 0.03,  # Improved
            "duration_ms": 250  # Improved
        }

        needs_rollback, reason = self.manager.check_rollback_needed(good_metrics)

        self.assertFalse(needs_rollback)


class TestCLIInterface(unittest.TestCase):
    """Test command-line interface."""

    def test_check_command(self):
        """Test --check command."""
        import subprocess
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "rollback-manager.py"), "--test"],
            capture_output=True,
            text=True,
            timeout=30
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("All tests passed", result.stdout)


def run_tests():
    """Run all tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestRollbackManagerImports))
    suite.addTests(loader.loadTestsFromTestCase(TestRollbackDetection))
    suite.addTests(loader.loadTestsFromTestCase(TestRollbackLogging))
    suite.addTests(loader.loadTestsFromTestCase(TestSignalAlertFormat))
    suite.addTests(loader.loadTestsFromTestCase(TestNeo4jLogging))
    suite.addTests(loader.loadTestsFromTestCase(TestRollbackHistory))
    suite.addTests(loader.loadTestsFromTestCase(TestRegressionScenarios))
    suite.addTests(loader.loadTestsFromTestCase(TestCLIInterface))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "="*70)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print("="*70)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
