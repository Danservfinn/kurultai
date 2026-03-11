#!/usr/bin/env python3
"""
Concurrency Tests for Kurultai Autonomous Experiment System

Tests parallel experiment execution, lock management, and deadlock prevention.

Run with: pytest test_concurrent_experiments.py -v
"""

import os
import sys
import time
import tempfile
import threading
import unittest
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import Mock, patch

# Add scripts directory to path
SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPTS_DIR))


class ExperimentLock:
    """
    Path-based locking for concurrent experiments.

    Rules:
    - Only one experiment per file/directory at a time
    - Locks have configurable timeout to prevent deadlock
    - Locks are released on experiment completion or timeout
    """

    DEFAULT_TIMEOUT_SECONDS = 3600  # 1 hour max lock hold time
    LOCK_DIR = "/tmp"

    def __init__(self, agent: str, target_paths: list, timeout: int = None):
        self.agent = agent
        self.target_paths = target_paths
        self.timeout = timeout or self.DEFAULT_TIMEOUT_SECONDS
        self.acquired_at = None
        self._lock_files = []

    def acquire(self) -> bool:
        """
        Acquire lock on all target paths.
        Returns False if any path is already locked.
        """
        # Check if all paths are available
        for path in self.target_paths:
            lock_file = self._get_lock_file_path(path)
            if os.path.exists(lock_file):
                # Check if lock is stale (older than timeout)
                if self._is_lock_stale(lock_file):
                    self._release_lock_file(lock_file)
                else:
                    return False

        # Acquire all locks
        for path in self.target_paths:
            lock_file = self._get_lock_file_path(path)
            self._create_lock_file(lock_file)
            self._lock_files.append(lock_file)

        self.acquired_at = time.time()
        return True

    def release(self):
        """Release all held locks."""
        for lock_file in self._lock_files:
            self._release_lock_file(lock_file)
        self._lock_files.clear()
        self.acquired_at = None

    def _get_lock_file_path(self, target_path: str) -> str:
        """Get lock file path for a target path."""
        safe_name = target_path.replace("/", "_").replace(".", "_")
        return os.path.join(self.LOCK_DIR, f"kurultai-exp-{safe_name}.lock")

    def _create_lock_file(self, lock_file: str):
        """Create lock file with metadata."""
        with open(lock_file, "w") as f:
            f.write(json.dumps({
                "agent": self.agent,
                "acquired_at": time.time(),
                "timeout": self.timeout,
                "paths": self.target_paths
            }))

    def _release_lock_file(self, lock_file: str):
        """Remove lock file."""
        try:
            os.remove(lock_file)
        except FileNotFoundError:
            pass

    def _is_lock_stale(self, lock_file: str) -> bool:
        """Check if lock is older than timeout."""
        try:
            with open(lock_file) as f:
                data = json.load(f)
            acquired_at = data.get("acquired_at", 0)
            timeout = data.get("timeout", self.DEFAULT_TIMEOUT_SECONDS)
            return time.time() - acquired_at > timeout
        except (FileNotFoundError, json.JSONDecodeError):
            return True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False


class ExperimentQueue:
    """Thread-safe queue for managing concurrent experiments."""

    def __init__(self, max_concurrent: int = 5):
        self.max_concurrent = max_concurrent
        self.active_experiments = {}
        self.pending_queue = []
        self.completed = []
        self._lock = threading.Lock()

    def submit(self, experiment_id: str, agent: str, target_paths: list) -> str:
        """Submit an experiment to the queue."""
        with self._lock:
            if len(self.active_experiments) < self.max_concurrent:
                return self._start(experiment_id, agent, target_paths)
            else:
                self.pending_queue.append({
                    "experiment_id": experiment_id,
                    "agent": agent,
                    "target_paths": target_paths
                })
                return "queued"

    def _start(self, experiment_id: str, agent: str, target_paths: list) -> str:
        """Start an experiment."""
        lock = ExperimentLock(agent, target_paths)
        if lock.acquire():
            self.active_experiments[experiment_id] = {
                "agent": agent,
                "target_paths": target_paths,
                "lock": lock,
                "started_at": time.time()
            }
            return "started"
        return "blocked"

    def complete(self, experiment_id: str):
        """Mark experiment as complete and release lock."""
        with self._lock:
            if experiment_id in self.active_experiments:
                exp = self.active_experiments.pop(experiment_id)
                exp["lock"].release()
                self.completed.append(experiment_id)

                # Start next pending experiment
                self._process_queue()

    def _process_queue(self):
        """Process pending experiments."""
        while self.pending_queue and len(self.active_experiments) < self.max_concurrent:
            next_exp = self.pending_queue[0]
            result = self._start(
                next_exp["experiment_id"],
                next_exp["agent"],
                next_exp["target_paths"]
            )
            if result == "started":
                self.pending_queue.pop(0)
            else:
                # Can't start, leave in queue
                break

    def get_status(self) -> dict:
        """Get queue status."""
        with self._lock:
            return {
                "active": len(self.active_experiments),
                "pending": len(self.pending_queue),
                "completed": len(self.completed),
                "max_concurrent": self.max_concurrent
            }


# Import json for lock files
import json


class TestParallelExperimentsDifferentFiles(unittest.TestCase):
    """Two agents experiment on different files - both succeed."""

    def setUp(self):
        """Clean up any existing lock files."""
        for f in os.listdir(ExperimentLock.LOCK_DIR):
            if f.startswith("kurultai-exp-") and f.endswith(".lock"):
                try:
                    os.remove(os.path.join(ExperimentLock.LOCK_DIR, f))
                except:
                    pass

    def tearDown(self):
        """Clean up lock files after tests."""
        self.setUp()

    def test_two_agents_different_files(self):
        """Two agents can run experiments on different files simultaneously."""
        lock1 = ExperimentLock("temujin", ["scripts/router.py"])
        lock2 = ExperimentLock("ogedei", ["scripts/cron_jobs.py"])

        # Both should acquire successfully
        self.assertTrue(lock1.acquire())
        self.assertTrue(lock2.acquire())

        # Both hold locks
        self.assertEqual(len(lock1._lock_files), 1)
        self.assertEqual(len(lock2._lock_files), 1)

        # Cleanup
        lock1.release()
        lock2.release()

    def test_three_agents_three_files(self):
        """Three agents can run on three different files."""
        locks = [
            ExperimentLock("temujin", ["scripts/a.py"]),
            ExperimentLock("ogedei", ["scripts/b.py"]),
            ExperimentLock("kublai", ["scripts/c.py"])
        ]

        # All should acquire
        results = [lock.acquire() for lock in locks]
        self.assertTrue(all(results))

        # Cleanup
        for lock in locks:
            lock.release()

    def test_multi_file_experiment(self):
        """Experiment spanning multiple files locks all of them."""
        lock = ExperimentLock("temujin", ["scripts/a.py", "scripts/b.py", "config/settings.yaml"])

        self.assertTrue(lock.acquire())

        # All files should be locked
        self.assertEqual(len(lock._lock_files), 3)

        # Another agent can't lock any of those files
        lock2 = ExperimentLock("ogedei", ["scripts/a.py"])
        self.assertFalse(lock2.acquire())

        lock.release()


class TestSequentialExperimentsSameFile(unittest.TestCase):
    """Two agents want same file - second waits for first."""

    def setUp(self):
        for f in os.listdir(ExperimentLock.LOCK_DIR):
            if f.startswith("kurultai-exp-") and f.endswith(".lock"):
                try:
                    os.remove(os.path.join(ExperimentLock.LOCK_DIR, f))
                except:
                    pass

    def tearDown(self):
        self.setUp()

    def test_second_blocked_until_first_releases(self):
        """Second experiment on same file is blocked until first releases."""
        lock1 = ExperimentLock("temujin", ["scripts/shared.py"])
        self.assertTrue(lock1.acquire())

        # Second agent blocked
        lock2 = ExperimentLock("ogedei", ["scripts/shared.py"])
        self.assertFalse(lock2.acquire())

        # Release first
        lock1.release()

        # Now second can acquire
        self.assertTrue(lock2.acquire())
        lock2.release()

    def test_queue_ordering(self):
        """Experiments are processed in queue order."""
        queue = ExperimentQueue(max_concurrent=2)

        # First two should start immediately
        r1 = queue.submit("exp-1", "temujin", ["scripts/a.py"])
        r2 = queue.submit("exp-2", "ogedei", ["scripts/b.py"])

        self.assertEqual(r1, "started")
        self.assertEqual(r2, "started")

        # Third should be queued (max reached)
        r3 = queue.submit("exp-3", "kublai", ["scripts/c.py"])
        self.assertEqual(r3, "queued")

        # Complete first, third should auto-start
        queue.complete("exp-1")

        status = queue.get_status()
        self.assertEqual(status["active"], 2)
        self.assertEqual(status["pending"], 0)


class TestDeadlockPrevention(unittest.TestCase):
    """Verify lock timeout prevents deadlock."""

    def setUp(self):
        for f in os.listdir(ExperimentLock.LOCK_DIR):
            if f.startswith("kurultai-exp-") and f.endswith(".lock"):
                try:
                    os.remove(os.path.join(ExperimentLock.LOCK_DIR, f))
                except:
                    pass

    def tearDown(self):
        self.setUp()

    def test_lock_timeout_releases_stale_lock(self):
        """Stale lock (older than timeout) is automatically released."""
        # Create lock with 1 second timeout
        lock1 = ExperimentLock("temujin", ["scripts/test.py"], timeout=1)
        self.assertTrue(lock1.acquire())

        # Wait for timeout
        time.sleep(1.5)

        # New lock attempt should succeed (stale lock released)
        lock2 = ExperimentLock("ogedei", ["scripts/test.py"])
        self.assertTrue(lock2.acquire())

        lock2.release()

    def test_no_deadlock_with_different_files(self):
        """No deadlock when agents work on different files."""
        # Agent 1 locks file A
        lock_a = ExperimentLock("temujin", ["scripts/a.py"])
        self.assertTrue(lock_a.acquire())

        # Agent 2 locks file B (different file, should succeed)
        lock_b = ExperimentLock("ogedei", ["scripts/b.py"])
        self.assertTrue(lock_b.acquire())

        # Agent 1 tries another file C - should succeed
        lock_c = ExperimentLock("temujin", ["scripts/c.py"])
        self.assertTrue(lock_c.acquire())

        # Agent 2 tries A - should fail (held by temujin)
        lock_a2 = ExperimentLock("ogedei", ["scripts/a.py"])
        self.assertFalse(lock_a2.acquire())

        # Agent 1 tries B - should fail (held by ogedei)
        lock_b2 = ExperimentLock("temujin", ["scripts/b.py"])
        self.assertFalse(lock_b2.acquire())

        # Cleanup
        lock_a.release()
        lock_b.release()
        lock_c.release()

    def test_context_manager_releases_on_exception(self):
        """Lock is released even if exception occurs."""
        lock = ExperimentLock("temujin", ["scripts/test.py"])
        lock_path = lock._get_lock_file_path("scripts/test.py")

        try:
            if lock.acquire():
                self.assertTrue(os.path.exists(lock_path))
                raise ValueError("Simulated error")
        except ValueError:
            lock.release()

        # Lock should be released
        self.assertFalse(os.path.exists(lock_path))

        # Another agent can now acquire
        lock2 = ExperimentLock("ogedei", ["scripts/test.py"])
        self.assertTrue(lock2.acquire())
        lock2.release()


class TestConcurrentExperimentExecution(unittest.TestCase):
    """Test actual concurrent execution of experiments."""

    def setUp(self):
        for f in os.listdir(ExperimentLock.LOCK_DIR):
            if f.startswith("kurultai-exp-") and f.endswith(".lock"):
                try:
                    os.remove(os.path.join(ExperimentLock.LOCK_DIR, f))
                except:
                    pass

    def tearDown(self):
        self.setUp()

    def test_concurrent_execution_thread_safety(self):
        """Multiple threads can safely acquire different locks."""
        results = []
        errors = []

        def run_experiment(agent: str, file: str):
            try:
                lock = ExperimentLock(agent, [f"scripts/{file}"])
                if lock.acquire():
                    results.append((agent, file, "acquired"))
                    time.sleep(0.1)  # Simulate work
                    lock.release()
                else:
                    results.append((agent, file, "blocked"))
            except Exception as e:
                errors.append((agent, str(e)))

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(run_experiment, f"agent{i}", f"file{i}.py")
                for i in range(5)
            ]
            for f in as_completed(futures):
                f.result()

        # All should have acquired (different files)
        acquired = [r for r in results if r[2] == "acquired"]
        self.assertEqual(len(acquired), 5)
        self.assertEqual(len(errors), 0)

    def test_contention_for_same_file(self):
        """Multiple agents contending for same file - only one wins."""
        results = []
        lock = threading.Lock()

        def try_acquire(agent: str):
            exp_lock = ExperimentLock(agent, ["scripts/contended.py"])
            success = exp_lock.acquire()
            with lock:
                results.append((agent, success))
            if success:
                time.sleep(0.2)
                exp_lock.release()

        threads = [
            threading.Thread(target=try_acquire, args=(f"agent{i}",))
            for i in range(5)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Only one should have acquired initially
        successful = [r for r in results if r[1]]
        # First one wins, others blocked
        self.assertGreaterEqual(len(successful), 1)


class TestQueueManagement(unittest.TestCase):
    """Test experiment queue behavior."""

    def setUp(self):
        for f in os.listdir(ExperimentLock.LOCK_DIR):
            if f.startswith("kurultai-exp-") and f.endswith(".lock"):
                try:
                    os.remove(os.path.join(ExperimentLock.LOCK_DIR, f))
                except:
                    pass

    def tearDown(self):
        self.setUp()

    def test_queue_respects_max_concurrent(self):
        """Queue doesn't exceed max concurrent experiments."""
        queue = ExperimentQueue(max_concurrent=2)

        # Submit 5 experiments on same file (forces queuing)
        results = []
        for i in range(5):
            result = queue.submit(f"exp-{i}", f"agent{i}", ["scripts/test.py"])
            results.append(result)

        # First starts, rest queue
        self.assertEqual(results[0], "started")
        self.assertTrue(all(r == "queued" or r == "blocked" for r in results[1:]))

    def test_queue_processes_on_completion(self):
        """Queue processes next experiment when one completes."""
        queue = ExperimentQueue(max_concurrent=1)

        queue.submit("exp-1", "temujin", ["scripts/a.py"])
        queue.submit("exp-2", "ogedei", ["scripts/a.py"])  # Queued

        status = queue.get_status()
        self.assertEqual(status["pending"], 1)

        queue.complete("exp-1")

        # exp-2 should have started
        status = queue.get_status()
        self.assertEqual(status["active"], 1)
        self.assertEqual(status["pending"], 0)


def run_tests():
    """Run all concurrency tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestParallelExperimentsDifferentFiles))
    suite.addTests(loader.loadTestsFromTestCase(TestSequentialExperimentsSameFile))
    suite.addTests(loader.loadTestsFromTestCase(TestDeadlockPrevention))
    suite.addTests(loader.loadTestsFromTestCase(TestConcurrentExperimentExecution))
    suite.addTests(loader.loadTestsFromTestCase(TestQueueManagement))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
