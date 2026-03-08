#!/usr/bin/env python3
"""
Unit Tests for Gate Repository

Tests the Neo4j-first gate discovery with caching and fallback:
- Neo4jGateRepository: Primary implementation
- CachedGateRepository: Caching decorator
- FilesystemGateRepository: Fallback implementation
- get_gate_repository: Factory function

Run:
    python3 test_gate_repository.py
    python3 test_gate_repository.py --verbose
    python3 test_gate_repository.py --test Neo4j  # Run specific test class
"""

import os
import sys
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import modules under test
from gate_repository import (
    FilesystemGateRepository,
    Neo4jGateRepository,
    CachedGateRepository,
    get_gate_repository,
    GateTask,
    GateState,
    Neo4jUnavailableError,
    task_id_from_file,
)


# =============================================================================
# Test Utilities
# =============================================================================

class MockNeo4jSession:
    """Mock Neo4j session for testing."""

    def __init__(self, data=None, error=None):
        self.data = data or []
        self.error = error
        self.queries_run = []

    def run(self, query, **kwargs):
        self.queries_run.append((query, kwargs))
        if self.error:
            raise self.error
        return self.data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class MockNeo4jDriver:
    """Mock Neo4j driver for testing."""

    def __init__(self, session_data=None, error=None):
        self.session_data = session_data
        self.error = error
        self.session_count = 0

    def session(self):
        self.session_count += 1
        return MockNeo4jSession(self.session_data, self.error)


# =============================================================================
# FilesystemGateRepository Tests
# =============================================================================

class TestFilesystemGateRepository(unittest.TestCase):
    """Test the filesystem-based gate repository (fallback)."""

    def setUp(self):
        """Create a temporary directory structure for testing."""
        self.test_dir = tempfile.mkdtemp()
        self.agents_dir = Path(self.test_dir) / "agents"
        self.agents_dir.mkdir()

        # Create agent directories
        for agent in ["mongke", "temujin", "ogedei"]:
            agent_dir = self.agents_dir / agent / "tasks"
            agent_dir.mkdir(parents=True)

        # Create sample pending gate files
        self._create_gate_file("mongke", "high-12345678", pending=True)
        self._create_gate_file("temujin", "high-87654321", pending=True)
        self._create_gate_file("ogedei", "normal-11111111", pending=False)  # Not pending

        # Patch AGENTS_DIR in the gate_repository module
        import gate_repository
        self.original_agents_dir = gate_repository.AGENTS_DIR
        gate_repository.AGENTS_DIR = self.agents_dir

        self.repo = FilesystemGateRepository()

    def tearDown(self):
        """Clean up test directory."""
        import gate_repository
        gate_repository.AGENTS_DIR = self.original_agents_dir
        import shutil
        shutil.rmtree(self.test_dir)

    def _create_gate_file(self, agent: str, task_id: str, pending: bool = True):
        """Create a test gate file."""
        tasks_dir = self.agents_dir / agent / "tasks"
        if pending:
            filename = f"high-{task_id}.pending-gate.md"
        else:
            filename = f"high-{task_id}.done.md"

        file_path = tasks_dir / filename
        content = f"""---
agent: {agent}
task_id: {task_id}
priority: high
---

# Task: Test Task for {task_id}

This is a test task.
"""
        file_path.write_text(content)

    def test_find_pending_returns_gates(self):
        """Test that find_pending returns pending gates."""
        gates = self.repo.find_pending()

        self.assertEqual(len(gates), 2)
        task_ids = {g.task_id for g in gates}
        self.assertIn("high-12345678", task_ids)
        self.assertIn("high-87654321", task_ids)
        self.assertNotIn("normal-11111111", task_ids)

    def test_find_pending_sorted_by_modified_time(self):
        """Test that gates are sorted by modification time."""
        # Create a newer gate
        time.sleep(0.1)
        self._create_gate_file("mongke", "high-99999999", pending=True)

        gates = self.repo.find_pending()
        # The newest should be last (oldest first)
        self.assertEqual(gates[-1].task_id, "high-99999999")

    def test_get_gate_status_pending(self):
        """Test get_gate_status for pending gate."""
        status = self.repo.get_gate_status("high-12345678")
        self.assertEqual(status, GateState.WAITING_FOLLOWUPS)

    def test_get_gate_status_none_for_nonexistent(self):
        """Test get_gate_status for nonexistent task."""
        status = self.repo.get_gate_status("nonexistent-task")
        self.assertEqual(status, GateState.NONE)

    def test_extract_task_id_from_frontmatter(self):
        """Test task ID extraction from frontmatter."""
        # Get the actual gate files found by find_pending
        gates = self.repo.find_pending()
        # Find the mongke gate
        mongke_gate = next((g for g in gates if g.task_id == "high-12345678"), None)
        self.assertIsNotNone(mongke_gate, "Should find mongke gate")

        # Extract task_id from the file path
        task_id = self.repo._extract_task_id(mongke_gate.file_path)
        self.assertEqual(task_id, "high-12345678")

    def test_extract_task_id_from_filename(self):
        """Test task ID extraction from filename when frontmatter missing."""
        # Create a file without frontmatter
        tasks_dir = self.agents_dir / "temujin" / "tasks"
        gate_file = tasks_dir / "high-from-filename.pending-gate.md"
        gate_file.write_text("# Task without frontmatter")

        task_id = self.repo._extract_task_id(gate_file)
        self.assertEqual(task_id, "from-filename")


# =============================================================================
# Neo4jGateRepository Tests
# =============================================================================

class TestNeo4jGateRepository(unittest.TestCase):
    """Test the Neo4j-based gate repository (primary)."""

    def setUp(self):
        """Set up mocks for Neo4j driver."""
        # Patch at the import location in neo4j_task_tracker
        self.patcher = patch('neo4j_task_tracker.get_driver')
        self.mock_get_driver = self.patcher.start()

    def tearDown(self):
        """Clean up mocks."""
        self.patcher.stop()

    def _create_mock_result(self, task_data):
        """Create a mock Neo4j result with task data."""
        mock_records = []
        for task in task_data:
            # Create a record that returns task data
            def make_record(t):
                return lambda key, t=t: t.get(key)
            mock_record = MagicMock()
            mock_record.__getitem__ = make_record(task)
            mock_record.get = lambda key, default=None, t=task: t.get(key, default)
            mock_records.append(mock_record)

        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter(mock_records)
        return mock_result

    def test_find_pending_queries_neo4j(self):
        """Test that find_pending queries Neo4j correctly."""
        # Create a simple dict-like record class
        class MockRecord:
            def __init__(self, **kwargs):
                self._data = kwargs
            def __getitem__(self, key):
                return self._data.get(key)
            def get(self, key, default=None):
                return self._data.get(key, default)

        # Set up mock data
        task_data = [
            MockRecord(task_id='high-12345678', agent='mongke',
                      title='Test Task 1', modified=datetime.now()),
            MockRecord(task_id='high-87654321', agent='temujin',
                      title='Test Task 2', modified=datetime.now())
        ]

        # Create mock session
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter(task_data)

        mock_session = Mock()
        mock_session.run.return_value = mock_result
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)

        mock_driver = Mock()
        mock_driver.session.return_value = mock_session

        self.mock_get_driver.return_value = mock_driver

        # Test the repository
        repo = Neo4jGateRepository()
        repo._driver = mock_driver  # Inject mock driver

        gates = repo.find_pending()

        # Verify query was run
        mock_session.run.assert_called_once()
        call_args = mock_session.run.call_args
        query = call_args[0][0]
        self.assertIn('gate_status', query)
        self.assertIn('waiting_followups', query)

        # Verify count
        self.assertEqual(len(gates), 2)

    def test_find_pending_raises_error_on_neo4j_failure(self):
        """Test that Neo4j errors are converted to Neo4jUnavailableError."""
        mock_driver = Mock()
        mock_session = Mock()
        mock_session.run.side_effect = Exception("Connection failed")
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_driver.session.return_value = mock_session

        self.mock_get_driver.return_value = mock_driver

        repo = Neo4jGateRepository()
        repo._driver = mock_driver

        with self.assertRaises(Neo4jUnavailableError):
            repo.find_pending()

    def test_get_gate_status_queries_neo4j(self):
        """Test that get_gate_status queries Neo4j correctly."""
        mock_record = MagicMock()
        mock_record.__getitem__ = lambda self, key: 'waiting_followups'

        mock_result = MagicMock()
        mock_result.single.return_value = mock_record

        mock_session = Mock()
        mock_session.run.return_value = mock_result
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)

        mock_driver = Mock()
        mock_driver.session.return_value = mock_session

        self.mock_get_driver.return_value = mock_driver

        repo = Neo4jGateRepository()
        repo._driver = mock_driver

        status = repo.get_gate_status('high-12345678')

        self.assertEqual(status, GateState.WAITING_FOLLOWUPS)
        mock_session.run.assert_called_once()
        call_args = mock_session.run.call_args
        self.assertEqual(call_args[1]['task_id'], 'high-12345678')

    def test_set_gate_status_updates_neo4j(self):
        """Test that set_gate_status updates Neo4j correctly."""
        mock_session = Mock()
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)

        mock_driver = Mock()
        mock_driver.session.return_value = mock_session

        self.mock_get_driver.return_value = mock_driver

        repo = Neo4jGateRepository()
        repo._driver = mock_driver

        repo.set_gate_status('high-12345678', GateState.PASSED)

        mock_session.run.assert_called_once()
        call_args = mock_session.run.call_args
        self.assertEqual(call_args[1]['task_id'], 'high-12345678')
        self.assertEqual(call_args[1]['status'], 'passed')


# =============================================================================
# CachedGateRepository Tests
# =============================================================================

class TestCachedGateRepository(unittest.TestCase):
    """Test the caching decorator for gate repositories."""

    def setUp(self):
        """Set up mock base repository."""
        self.base_repo = Mock()
        self.cached_repo = CachedGateRepository(self.base_repo, ttl_seconds=1)

    def test_find_pending_queries_base_on_first_call(self):
        """Test that first call queries base repository."""
        self.base_repo.find_pending.return_value = [
            GateTask(task_id="test-1", agent="mongke", file_path=Path("/test"))
        ]

        gates = self.cached_repo.find_pending()

        self.base_repo.find_pending.assert_called_once()
        self.assertEqual(len(gates), 1)

    def test_find_pending_uses_cache_within_ttl(self):
        """Test that subsequent calls within TTL use cache."""
        self.base_repo.find_pending.return_value = [
            GateTask(task_id="test-1", agent="mongke", file_path=Path("/test"))
        ]

        # First call
        gates1 = self.cached_repo.find_pending()
        # Second call immediately (within TTL)
        gates2 = self.cached_repo.find_pending()

        # Base repo should only be called once
        self.assertEqual(self.base_repo.find_pending.call_count, 1)
        self.assertEqual(gates1[0].task_id, gates2[0].task_id)

    def test_find_pending_misses_cache_after_ttl(self):
        """Test that cache expires after TTL."""
        self.base_repo.find_pending.return_value = [
            GateTask(task_id="test-1", agent="mongke", file_path=Path("/test"))
        ]

        # First call
        self.cached_repo.find_pending()

        # Wait for TTL to expire
        time.sleep(1.1)

        # Second call (should miss cache)
        self.cached_repo.find_pending()

        # Base repo should be called twice
        self.assertEqual(self.base_repo.find_pending.call_count, 2)

    def test_invalidate_cache_clears_cache(self):
        """Test that invalidate_cache clears the cache."""
        self.base_repo.find_pending.return_value = [
            GateTask(task_id="test-1", agent="mongke", file_path=Path("/test"))
        ]

        # First call
        self.cached_repo.find_pending()

        # Invalidate cache
        self.cached_repo.invalidate_cache()

        # Second call (should query base repo again)
        self.cached_repo.find_pending()

        self.assertEqual(self.base_repo.find_pending.call_count, 2)

    def test_set_gate_status_invalidates_cache(self):
        """Test that set_gate_status invalidates cache."""
        self.base_repo.find_pending.return_value = []
        self.base_repo.set_gate_status.return_value = None

        # Populate cache
        self.cached_repo.find_pending()

        # Set status (should invalidate cache)
        self.cached_repo.set_gate_status("test-1", GateState.PASSED)

        self.base_repo.set_gate_status.assert_called_once_with(
            "test-1", GateState.PASSED
        )

        # Next find_pending should query base repo again
        self.cached_repo.find_pending()
        self.assertEqual(self.base_repo.find_pending.call_count, 2)

    def test_fallback_to_filesystem_on_neo4j_error(self):
        """Test fallback to filesystem when Neo4j fails."""
        import time

        # Set up base repo to raise error
        base_repo = Mock()
        base_repo.find_pending.side_effect = Neo4jUnavailableError("Neo4j down")

        with patch('gate_repository.FilesystemGateRepository') as mock_fs_repo:
            mock_fs_instance = Mock()
            mock_fs_instance.find_pending.return_value = [
                GateTask(task_id="fs-1", agent="mongke", file_path=Path("/fs"))
            ]
            mock_fs_repo.return_value = mock_fs_instance

            cached_repo = CachedGateRepository(base_repo, ttl_seconds=60)
            gates = cached_repo.find_pending()

            # Should fall back to filesystem
            self.assertEqual(len(gates), 1)
            self.assertEqual(gates[0].task_id, "fs-1")


# =============================================================================
# Factory Function Tests
# =============================================================================

class TestGetGateRepository(unittest.TestCase):
    """Test the get_gate_repository factory function."""

    @patch('gate_repository.Neo4jGateRepository')
    @patch('neo4j_task_tracker.get_driver')
    def test_returns_neo4j_when_available(self, mock_get_driver, mock_neo4j_class):
        """Test that Neo4j repository is returned when Neo4j is available."""
        mock_driver = Mock()
        mock_session = Mock()
        mock_result = Mock()
        mock_result.single.return_value = Mock()
        mock_session.run.return_value = mock_result
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_driver.session.return_value = mock_session
        mock_get_driver.return_value = mock_driver

        repo = get_gate_repository(use_cache=False)

        # Should be Neo4j repo (not wrapped in cache)
        self.assertIsInstance(repo, Mock)  # Mock because of patch
        # But the underlying class should have been instantiated
        mock_neo4j_class.assert_called_once()

    def test_falls_back_to_filesystem_on_error(self):
        """Test that filesystem repository is returned when Neo4j fails."""
        # Make get_driver fail immediately (Neo4j not available)
        with patch('neo4j_task_tracker.get_driver') as mock_get_driver:
            mock_get_driver.side_effect = Exception("Neo4j not available")

            repo = get_gate_repository(use_cache=False)

            # Should be filesystem repo (not Neo4j, not wrapped in cache)
            self.assertIsInstance(repo, FilesystemGateRepository)

    @patch('gate_repository.Neo4jGateRepository')
    @patch('neo4j_task_tracker.get_driver')
    def test_wraps_in_cache_when_requested(self, mock_get_driver, mock_neo4j_class):
        """Test that repository is wrapped in cache when use_cache=True."""
        mock_driver = Mock()
        mock_session = Mock()
        mock_result = Mock()
        mock_result.single.return_value = Mock()
        mock_session.run.return_value = mock_result
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_driver.session.return_value = mock_session
        mock_get_driver.return_value = mock_driver

        repo = get_gate_repository(use_cache=True, ttl_seconds=30)

        # Should be cached repo
        self.assertIsInstance(repo, CachedGateRepository)


# =============================================================================
# Helper Function Tests
# =============================================================================

class TestHelperFunctions(unittest.TestCase):
    """Test helper functions in gate_repository."""

    def test_task_id_from_file(self):
        """Test task_id_from_file extraction."""
        test_file = Path("/some/path/high-12345678.pending-gate.md")
        task_id = task_id_from_file(test_file)
        self.assertEqual(task_id, "12345678")

    def test_task_id_from_file_single_part(self):
        """Test task_id_from_file with single-part filename."""
        test_file = Path("/some/path/justtaskid.pending-gate.md")
        task_id = task_id_from_file(test_file)
        self.assertEqual(task_id, "justtaskid")


# =============================================================================
# Test Runner
# =============================================================================

def run_tests():
    """Run all tests and return results."""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test classes
    test_classes = [
        TestFilesystemGateRepository,
        TestNeo4jGateRepository,
        TestCachedGateRepository,
        TestGetGateRepository,
        TestHelperFunctions,
    ]

    for test_class in test_classes:
        tests = loader.loadTestsFromTestCase(test_class)
        suite.addTests(tests)

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Return summary
    return {
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "success": result.wasSuccessful()
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run gate repository tests")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Verbose output")
    parser.add_argument("--test", "-t", help="Run specific test class")

    args = parser.parse_args()

    if args.test:
        # Run specific test class
        suite = unittest.TestLoader().loadTestsFromName(args.test)
        unittest.TextTestRunner(verbosity=2).run(suite)
    else:
        # Run all tests
        summary = run_tests()
        print(f"\n{'='*50}")
        print(f"Tests: {summary['tests_run']}")
        print(f"Failures: {summary['failures']}")
        print(f"Errors: {summary['errors']}")
        print(f"Status: {'PASS' if summary['success'] else 'FAIL'}")
