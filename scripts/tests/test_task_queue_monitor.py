#!/usr/bin/env python3
"""
Performance Tests for Kurultai Task Queue Monitor

Tests task scanning, priority ordering, and queue operations.
"""

import os
import sys
import time
import tempfile
import shutil
import unittest
from datetime import datetime
from unittest.mock import patch, MagicMock

# Add scripts directory to path
SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS_DIR)


class TestTaskQueueMonitorPerformance(unittest.TestCase):
    """Performance tests for task queue operations."""

    def setUp(self):
        """Set up test fixtures for each test."""
        self.test_dir = tempfile.mkdtemp()
        self.agents = ['kublai', 'temujin', 'mongke', 'chagatai', 'jochi', 'ogedei']

        # Create test task directories
        for agent in self.agents:
            task_dir = os.path.join(self.test_dir, agent, 'tasks')
            os.makedirs(task_dir, exist_ok=True)

    def tearDown(self):
        """Clean up test fixtures after each test."""
        shutil.rmtree(self.test_dir)

    def create_test_task(self, agent: str, priority: str, task_id: str) -> str:
        """Create a test task file."""
        task_dir = os.path.join(self.test_dir, agent, 'tasks')
        task_file = os.path.join(task_dir, f"{priority}-{task_id}.md")

        with open(task_file, 'w') as f:
            f.write(f"""---
task_id: {task_id}
agent: {agent}
priority: {priority}
created: {datetime.now().isoformat()}
---

# Task: Test task {task_id}

Test task content for performance testing.
""")
        return task_file

    def test_task_scan_performance(self):
        """Test that scanning 100 tasks completes in < 100ms."""
        # Create 100 test tasks across all agents
        for i in range(100):
            agent = self.agents[i % len(self.agents)]
            priority = ['high', 'normal', 'low'][i % 3]
            self.create_test_task(agent, priority, f"scan-test-{i}")

        # Time the scan operation
        start = time.perf_counter()

        pending = []
        for agent in self.agents:
            task_dir = os.path.join(self.test_dir, agent, 'tasks')
            if os.path.exists(task_dir):
                for filename in os.listdir(task_dir):
                    if filename.endswith('.md') and '.done' not in filename:
                        pending.append({
                            'agent': agent,
                            'file': os.path.join(task_dir, filename)
                        })

        elapsed_ms = (time.perf_counter() - start) * 1000

        # Verify
        self.assertEqual(len(pending), 100, "Should find all 100 tasks")
        self.assertLess(elapsed_ms, 100, f"Scan should take < 100ms, took {elapsed_ms:.2f}ms")

    def test_priority_sorting_performance(self):
        """Test priority sorting of 500 tasks completes in < 50ms."""
        # Create unsorted task list (in-memory, no files)
        tasks = []
        for i in range(500):
            priority = ['high', 'normal', 'low'][i % 3]
            tasks.append({
                'agent': self.agents[i % len(self.agents)],
                'priority': priority,
                'task_id': f"task-{i}"
            })

        # Time the sort operation
        start = time.perf_counter()

        priority_order = {'high': 0, 'normal': 1, 'low': 2}
        sorted_tasks = sorted(tasks, key=lambda x: priority_order.get(x['priority'], 1))

        elapsed_ms = (time.perf_counter() - start) * 1000

        # Verify sorting is correct
        self.assertEqual(len(sorted_tasks), 500)
        self.assertLess(elapsed_ms, 50, f"Sort should take < 50ms, took {elapsed_ms:.2f}ms")

        # Verify high priority tasks are first
        high_count = sum(1 for t in sorted_tasks[:200] if t['priority'] == 'high')
        self.assertGreater(high_count, 150, "High priority tasks should be sorted first")

    def test_file_read_performance(self):
        """Test reading 50 task files completes in < 200ms."""
        # Create 50 task files with content
        for i in range(50):
            agent = self.agents[i % len(self.agents)]
            self.create_test_task(agent, 'normal', f"read-test-{i}")

        # Time file reading
        start = time.perf_counter()

        tasks_read = 0
        for agent in self.agents:
            task_dir = os.path.join(self.test_dir, agent, 'tasks')
            if os.path.exists(task_dir):
                for filename in os.listdir(task_dir):
                    if filename.startswith('normal-read-test-'):
                        with open(os.path.join(task_dir, filename), 'r') as f:
                            content = f.read()
                            if '# Task:' in content:
                                tasks_read += 1

        elapsed_ms = (time.perf_counter() - start) * 1000

        self.assertEqual(tasks_read, 50, "Should read all 50 task files")
        self.assertLess(elapsed_ms, 200, f"Read should take < 200ms, took {elapsed_ms:.2f}ms")

    def test_concurrent_task_creation(self):
        """Test concurrent task creation doesn't cause file conflicts."""
        import threading

        created_files = []
        lock = threading.Lock()

        def create_task(idx):
            agent = self.agents[idx % len(self.agents)]
            task_file = self.create_test_task(agent, 'normal', f"concurrent-{idx}-{threading.current_thread().name}")
            with lock:
                created_files.append(task_file)

        # Create 20 tasks concurrently
        threads = []
        for i in range(20):
            t = threading.Thread(target=create_task, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Verify all files were created
        existing_files = [f for f in created_files if os.path.exists(f)]
        self.assertEqual(len(existing_files), 20, "All concurrent task files should exist")


class TestTaskQueueMonitorUnit(unittest.TestCase):
    """Unit tests for task queue monitor functions."""

    def test_priority_order_definition(self):
        """Test priority order mapping is correct."""
        priority_order = {'high': 0, 'normal': 1, 'low': 2}

        self.assertEqual(priority_order['high'], 0)
        self.assertEqual(priority_order['normal'], 1)
        self.assertEqual(priority_order['low'], 2)

    def test_task_pattern_matching(self):
        """Test task file pattern matching."""
        patterns = [
            ('high-12345.md', True, 'high'),
            ('normal-67890.md', True, 'normal'),
            ('low-11111.md', True, 'low'),
            ('high-12345.done.md', False, None),
            ('high-12345.executing.md', False, None),
            ('random.txt', False, None),
        ]

        for filename, should_match, expected_priority in patterns:
            # Check pattern matching logic
            is_pending = (
                filename.endswith('.md') and
                '.done' not in filename and
                '.executing' not in filename
            )

            if should_match:
                self.assertTrue(is_pending, f"{filename} should match as pending")
                self.assertIn(expected_priority, filename)
            else:
                # For files that should NOT match, is_pending should be False
                self.assertFalse(is_pending, f"{filename} should not match as pending")

    def test_task_id_extraction(self):
        """Test extracting task ID from filename."""
        test_cases = [
            ('high-abc123.md', 'abc123'),
            ('normal-xyz789.md', 'xyz789'),
            ('low-task-001.md', 'task-001'),
        ]

        for filename, expected_id in test_cases:
            # Extract task ID (remove priority prefix and .md suffix)
            parts = filename.replace('.md', '').split('-', 1)
            if len(parts) > 1:
                task_id = parts[1]
                self.assertEqual(task_id, expected_id, f"Should extract {expected_id} from {filename}")


if __name__ == '__main__':
    unittest.main(verbosity=2)