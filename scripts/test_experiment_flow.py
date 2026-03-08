#!/usr/bin/env python3
"""
End-to-End Integration Tests for Kurultai Autonomous Experiment System

Tests the full lifecycle of experiments: create -> run -> merge/discard -> cleanup

Run with: pytest test_experiment_flow.py -v
"""

import os
import sys
import time
import json
import tempfile
import subprocess
import unittest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

# Add scripts directory to path
SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPTS_DIR))


class MockExperimentManager:
    """Mock experiment manager for testing without full infrastructure."""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.experiments_dir = base_dir / "experiments"
        self.experiments_dir.mkdir(parents=True, exist_ok=True)
        self.active_experiments = {}
        self.ledger_path = self.experiments_dir / "ledger.tsv"
        self._init_ledger()

    def _init_ledger(self):
        """Initialize the experiment ledger."""
        if not self.ledger_path.exists():
            with open(self.ledger_path, "w") as f:
                f.write("experiment_id\tagent\tcommit\tval_quality\tduration_s\tcost_usd\tstatus\tdescription\n")

    def create_experiment(self, agent: str, hypothesis: str, target_files: list, timeout: int) -> dict:
        """Create a new experiment."""
        exp_id = f"exp-{datetime.now().strftime('%Y%m%d')}-{len(self.active_experiments) + 1:03d}"
        slug = hypothesis.lower().replace(" ", "-")[:30]

        experiment = {
            "experiment_id": exp_id,
            "agent": agent,
            "hypothesis": hypothesis,
            "branch": f"experiment/{agent}/{exp_id}/{slug}",
            "target_files": target_files,
            "timeout": timeout,
            "status": "pending",
            "created": datetime.now().isoformat(),
            "base_commit": "a1b2c3d7",
            "metrics": {
                "quality_score_baseline": 0.72,
                "quality_score_result": None,
                "error_rate_baseline": 0.05,
                "error_rate_result": None,
            }
        }

        self.active_experiments[exp_id] = experiment
        return experiment

    def start_experiment(self, exp_id: str) -> bool:
        """Start running an experiment."""
        if exp_id not in self.active_experiments:
            return False

        self.active_experiments[exp_id]["status"] = "running"
        self.active_experiments[exp_id]["started"] = datetime.now().isoformat()
        return True

    def complete_experiment(self, exp_id: str, metrics: dict, decision: str) -> bool:
        """Complete an experiment with metrics and decision."""
        if exp_id not in self.active_experiments:
            return False

        exp = self.active_experiments[exp_id]
        exp["status"] = decision  # merged, discarded, crashed
        exp["completed"] = datetime.now().isoformat()
        exp["metrics"].update(metrics)
        exp["decision"] = decision

        # Write to ledger
        with open(self.ledger_path, "a") as f:
            quality = metrics.get("quality_score_result", 0)
            duration = (datetime.now() - datetime.fromisoformat(exp["started"])).total_seconds() if "started" in exp else 0
            f.write(f"{exp_id}\t{exp['agent']}\t{exp['base_commit']}\t{quality:.4f}\t{int(duration)}\t0.47\t{decision}\t{exp['hypothesis'][:50]}\n")

        return True

    def cleanup_experiment(self, exp_id: str) -> bool:
        """Clean up experiment resources."""
        if exp_id in self.active_experiments:
            del self.active_experiments[exp_id]
        return True


class MockRollbackManager:
    """Mock rollback manager for testing."""

    def __init__(self):
        self.rollback_history = []
        self.baseline_metrics = {
            "quality": 0.72,
            "error_rate": 0.05,
            "duration": 300
        }

    def check_rollback_needed(self, current_metrics: dict) -> tuple:
        """Check if metrics regressed beyond threshold."""
        # Quality regression > 5%
        if current_metrics.get("quality", 1.0) < self.baseline_metrics["quality"] * 0.95:
            return True, "quality_regression_5pct"

        # Error rate spike > 2x
        if current_metrics.get("error_rate", 0) > self.baseline_metrics["error_rate"] * 2.0:
            return True, "error_rate_2x"

        # Duration spike > 50%
        if current_metrics.get("duration", 0) > self.baseline_metrics["duration"] * 1.5:
            return True, "duration_spike_50pct"

        return False, ""

    def execute_rollback(self, commit_hash: str, reason: str) -> dict:
        """Execute instant rollback."""
        result = {
            "success": True,
            "commit_hash": commit_hash,
            "reason": reason,
            "timestamp": datetime.now().isoformat(),
            "duration_ms": 0
        }
        self.rollback_history.append(result)
        return result


class MockExperimentLock:
    """Mock experiment lock for concurrent testing."""

    locks = {}  # Class-level lock registry

    def __init__(self, agent: str, target_paths: list):
        self.agent = agent
        self.target_paths = target_paths
        self.lock_file = f"/tmp/kurultai-exp-{agent}.lock"

    def acquire(self) -> bool:
        """Acquire lock on target paths."""
        for path in self.target_paths:
            if path in MockExperimentLock.locks:
                return False
        for path in self.target_paths:
            MockExperimentLock.locks[path] = self.agent
        return True

    def release(self):
        """Release all locks held by this agent."""
        keys_to_remove = [k for k, v in MockExperimentLock.locks.items() if v == self.agent]
        for key in keys_to_remove:
            del MockExperimentLock.locks[key]

    @classmethod
    def reset(cls):
        """Reset all locks."""
        cls.locks.clear()


class TestFullExperimentLifecycle(unittest.TestCase):
    """Test: create -> run -> merge -> cleanup"""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.manager = MockExperimentManager(self.temp_dir)

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_experiment(self):
        """Test experiment creation."""
        exp = self.manager.create_experiment(
            agent="temujin",
            hypothesis="Increase router scorer learning rate",
            target_files=["scripts/router_scorer.py"],
            timeout=600
        )

        self.assertEqual(exp["agent"], "temujin")
        self.assertEqual(exp["status"], "pending")
        self.assertIn("experiment/temujin/", exp["branch"])
        self.assertTrue(exp["experiment_id"].startswith("exp-"))

    def test_start_experiment(self):
        """Test experiment start."""
        exp = self.manager.create_experiment(
            agent="temujin",
            hypothesis="Test hypothesis",
            target_files=["test.py"],
            timeout=300
        )

        result = self.manager.start_experiment(exp["experiment_id"])
        self.assertTrue(result)

        updated = self.manager.active_experiments[exp["experiment_id"]]
        self.assertEqual(updated["status"], "running")
        self.assertIn("started", updated)

    def test_complete_with_merge(self):
        """Test successful experiment completion with merge."""
        exp = self.manager.create_experiment(
            agent="temujin",
            hypothesis="Quality improvement test",
            target_files=["test.py"],
            timeout=300
        )
        self.manager.start_experiment(exp["experiment_id"])

        metrics = {
            "quality_score_result": 0.78,  # +8.3% improvement
            "error_rate_result": 0.04
        }

        result = self.manager.complete_experiment(
            exp["experiment_id"],
            metrics,
            decision="merged"
        )

        self.assertTrue(result)

        # Verify ledger entry
        ledger_path = self.manager.ledger_path
        self.assertTrue(ledger_path.exists())

        with open(ledger_path) as f:
            content = f.read()
            self.assertIn(exp["experiment_id"], content)
            self.assertIn("merged", content)

    def test_full_lifecycle_happy_path(self):
        """Test complete happy path: create -> start -> merge -> cleanup."""
        # 1. Create
        exp = self.manager.create_experiment(
            agent="temujin",
            hypothesis="Full lifecycle test",
            target_files=["test.py"],
            timeout=300
        )
        self.assertEqual(exp["status"], "pending")

        # 2. Start
        self.manager.start_experiment(exp["experiment_id"])
        self.assertEqual(
            self.manager.active_experiments[exp["experiment_id"]]["status"],
            "running"
        )

        # 3. Complete with merge
        metrics = {
            "quality_score_result": 0.80,
            "error_rate_result": 0.03
        }
        self.manager.complete_experiment(exp["experiment_id"], metrics, "merged")

        # 4. Cleanup
        self.manager.cleanup_experiment(exp["experiment_id"])
        self.assertNotIn(exp["experiment_id"], self.manager.active_experiments)

        # 5. Verify ledger
        with open(self.manager.ledger_path) as f:
            lines = f.readlines()
            self.assertEqual(len(lines), 2)  # Header + 1 entry


class TestExperimentWithRegression(unittest.TestCase):
    """Test: create -> run -> discard -> cleanup"""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.manager = MockExperimentManager(self.temp_dir)
        self.rollback = MockRollbackManager()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_discard_on_quality_regression(self):
        """Test experiment discarded when quality regresses."""
        exp = self.manager.create_experiment(
            agent="temujin",
            hypothesis="Bad change test",
            target_files=["test.py"],
            timeout=300
        )
        self.manager.start_experiment(exp["experiment_id"])

        # Simulate regression
        metrics = {
            "quality_score_result": 0.65,  # -10% regression
            "error_rate_result": 0.08
        }

        # Check if rollback needed
        needs_rollback, reason = self.rollback.check_rollback_needed({
            "quality": metrics["quality_score_result"],
            "error_rate": metrics["error_rate_result"]
        })

        self.assertTrue(needs_rollback)
        self.assertEqual(reason, "quality_regression_5pct")

        # Discard experiment
        self.manager.complete_experiment(exp["experiment_id"], metrics, "discarded")

        updated = self.manager.active_experiments[exp["experiment_id"]]
        self.assertEqual(updated["status"], "discarded")

    def test_discard_on_error_spike(self):
        """Test experiment discarded when error rate spikes."""
        metrics = {
            "quality": 0.72,  # Same as baseline
            "error_rate": 0.15  # 3x baseline
        }

        needs_rollback, reason = self.rollback.check_rollback_needed(metrics)

        self.assertTrue(needs_rollback)
        self.assertEqual(reason, "error_rate_2x")


class TestConcurrentExperiments(unittest.TestCase):
    """Test: two experiments on different files run concurrently"""

    def setUp(self):
        MockExperimentLock.reset()
        self.temp_dir = Path(tempfile.mkdtemp())
        self.manager = MockExperimentManager(self.temp_dir)

    def tearDown(self):
        MockExperimentLock.reset()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_parallel_experiments_different_files(self):
        """Two agents experiment on different files - both succeed."""
        # Agent 1 locks file A
        lock1 = MockExperimentLock("temujin", ["scripts/file_a.py"])
        self.assertTrue(lock1.acquire())

        # Agent 2 locks file B (different file)
        lock2 = MockExperimentLock("ogedei", ["scripts/file_b.py"])
        self.assertTrue(lock2.acquire())

        # Both should be able to proceed
        exp1 = self.manager.create_experiment(
            "temujin", "Test A", ["scripts/file_a.py"], 300
        )
        exp2 = self.manager.create_experiment(
            "ogedei", "Test B", ["scripts/file_b.py"], 300
        )

        self.manager.start_experiment(exp1["experiment_id"])
        self.manager.start_experiment(exp2["experiment_id"])

        # Both running
        self.assertEqual(
            self.manager.active_experiments[exp1["experiment_id"]]["status"],
            "running"
        )
        self.assertEqual(
            self.manager.active_experiments[exp2["experiment_id"]]["status"],
            "running"
        )

        # Cleanup
        lock1.release()
        lock2.release()

    def test_same_file_blocked(self):
        """Second experiment on same file is blocked."""
        # Agent 1 locks file
        lock1 = MockExperimentLock("temujin", ["scripts/shared.py"])
        self.assertTrue(lock1.acquire())

        # Agent 2 tries to lock same file
        lock2 = MockExperimentLock("ogedei", ["scripts/shared.py"])
        self.assertFalse(lock2.acquire())  # Should fail

        lock1.release()


class TestConflictDetection(unittest.TestCase):
    """Test: second experiment on same file is blocked"""

    def setUp(self):
        MockExperimentLock.reset()

    def tearDown(self):
        MockExperimentLock.reset()

    def test_conflict_detection(self):
        """Verify conflict detection prevents overlapping experiments."""
        # First agent acquires lock
        lock1 = MockExperimentLock("temujin", ["scripts/router.py"])
        acquired1 = lock1.acquire()
        self.assertTrue(acquired1)

        # Second agent attempts same file
        lock2 = MockExperimentLock("kublai", ["scripts/router.py"])
        acquired2 = lock2.acquire()
        self.assertFalse(acquired2)

        # Verify lock state
        self.assertIn("scripts/router.py", MockExperimentLock.locks)
        self.assertEqual(
            MockExperimentLock.locks["scripts/router.py"],
            "temujin"
        )

    def test_lock_release_allows_next(self):
        """Verify releasing lock allows next experiment."""
        lock1 = MockExperimentLock("temujin", ["scripts/test.py"])
        lock1.acquire()

        lock1.release()

        lock2 = MockExperimentLock("ogedei", ["scripts/test.py"])
        acquired = lock2.acquire()
        self.assertTrue(acquired)


class TestRollbackAfterMerge(unittest.TestCase):
    """Test: merge -> detect regression -> rollback"""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.manager = MockExperimentManager(self.temp_dir)
        self.rollback = MockRollbackManager()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_rollback_after_merge(self):
        """Test rollback after detecting post-merge regression."""
        # 1. Create and complete experiment with good metrics
        exp = self.manager.create_experiment(
            "temujin", "Good experiment", ["test.py"], 300
        )
        self.manager.start_experiment(exp["experiment_id"])

        good_metrics = {
            "quality_score_result": 0.78,
            "error_rate_result": 0.04
        }
        self.manager.complete_experiment(exp["experiment_id"], good_metrics, "merged")

        # 2. Simulate post-merge regression detected
        post_merge_metrics = {
            "quality": 0.65,  # Regression detected
            "error_rate": 0.12
        }

        needs_rollback, reason = self.rollback.check_rollback_needed(post_merge_metrics)
        self.assertTrue(needs_rollback)

        # 3. Execute rollback
        result = self.rollback.execute_rollback(
            commit_hash=exp["base_commit"],
            reason=reason
        )

        self.assertTrue(result["success"])
        self.assertEqual(len(self.rollback.rollback_history), 1)

    def test_rollback_logging(self):
        """Verify rollback creates proper audit trail."""
        self.rollback.execute_rollback("abc123", "quality_regression_5pct")

        self.assertEqual(len(self.rollback.rollback_history), 1)

        entry = self.rollback.rollback_history[0]
        self.assertEqual(entry["commit_hash"], "abc123")
        self.assertEqual(entry["reason"], "quality_regression_5pct")
        self.assertIn("timestamp", entry)


class TestExperimentMetrics(unittest.TestCase):
    """Test metric collection and comparison."""

    def test_improvement_threshold_calculation(self):
        """Verify improvement threshold calculations."""
        baseline = 0.72
        result = 0.78
        improvement = (result - baseline) / baseline * 100

        self.assertGreater(improvement, 5.0)  # Exceeds +5% threshold

    def test_regression_threshold_calculation(self):
        """Verify regression threshold calculations."""
        baseline = 0.72
        result = 0.65
        regression = (baseline - result) / baseline * 100

        self.assertGreater(regression, 5.0)  # Exceeds -5% threshold


class TestExperimentLedger(unittest.TestCase):
    """Test experiment ledger functionality."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.manager = MockExperimentManager(self.temp_dir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_ledger_format(self):
        """Verify ledger TSV format is correct."""
        exp = self.manager.create_experiment(
            "temujin", "Ledger test", ["test.py"], 300
        )
        self.manager.start_experiment(exp["experiment_id"])
        self.manager.complete_experiment(
            exp["experiment_id"],
            {"quality_score_result": 0.80, "error_rate_result": 0.03},
            "merged"
        )

        with open(self.manager.ledger_path) as f:
            lines = f.readlines()

        # Header should be first line
        self.assertIn("experiment_id", lines[0])
        self.assertIn("agent", lines[0])
        self.assertIn("status", lines[0])

        # Data should be second line
        parts = lines[1].strip().split("\t")
        self.assertEqual(parts[0], exp["experiment_id"])
        self.assertEqual(parts[1], "temujin")
        self.assertEqual(parts[6], "merged")


def run_tests():
    """Run all tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestFullExperimentLifecycle))
    suite.addTests(loader.loadTestsFromTestCase(TestExperimentWithRegression))
    suite.addTests(loader.loadTestsFromTestCase(TestConcurrentExperiments))
    suite.addTests(loader.loadTestsFromTestCase(TestConflictDetection))
    suite.addTests(loader.loadTestsFromTestCase(TestRollbackAfterMerge))
    suite.addTests(loader.loadTestsFromTestCase(TestExperimentMetrics))
    suite.addTests(loader.loadTestsFromTestCase(TestExperimentLedger))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
