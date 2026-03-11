#!/usr/bin/env python3
"""
test_task_retry.py — Integration tests for task retry functionality.

Tests the core retry service without requiring HTTP server.

Usage:
    python3 test_task_retry.py
    python3 test_task_retry.py --verbose
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from task_retry_service import TaskRetryService, RetryResult, TaskInfo


class TestTaskRetryService(unittest.TestCase):
    """Test suite for TaskRetryService."""

    def setUp(self):
        """Set up test fixtures."""
        # Create a temporary directory structure
        self.test_dir = tempfile.mkdtemp()
        self.agents_dir = Path(self.test_dir) / "agents"
        self.agents_dir.mkdir()

        # Create test agent directories
        for agent in ["temujin", "mongke", "chagatai"]:
            (self.agents_dir / agent / "tasks").mkdir(parents=True)

        # Create a test state directory
        self.state_dir = Path(self.test_dir) / "logs"
        self.state_dir.mkdir()

        # Create a failed task file
        self.failed_task_content = """---
agent: temujin
priority: high
created: 2026-03-10T19:31:00
timeout: 7200
---

# Task: Test task for retry functionality

This task failed and should be retryable.

## Error

Rate limit exceeded. Please try again later.
"""
        self.failed_task_path = (
            self.agents_dir / "temujin" / "tasks" / "high-1773185511.failed.done.md"
        )
        self.failed_task_path.write_text(self.failed_task_content)

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.test_dir)

    def test_extract_task_id(self):
        """Test task ID extraction from filename."""
        service = TaskRetryService()

        test_cases = [
            ("high-1773185511.failed.done.md", "high-1773185511"),
            ("normal-1234567890.failed.done.md", "normal-1234567890"),
            ("low-abc123-def.failed.done.md", "low-abc123-def"),
        ]

        for filename, expected_id in test_cases:
            with self.subTest(filename=filename):
                result = service.extract_task_id(filename)
                self.assertEqual(result, expected_id)

    def test_get_pending_filename(self):
        """Test conversion of failed filename to pending."""
        service = TaskRetryService()

        test_cases = [
            ("high-1773185511.failed.done.md", "high-1773185511.md"),
            ("normal-1234567890.failed.done.md", "normal-1234567890.md"),
        ]

        for failed_name, expected_pending in test_cases:
            with self.subTest(failed=failed_name):
                result = service.get_pending_filename(failed_name)
                self.assertEqual(result, expected_pending)

    def test_is_failed_task(self):
        """Test detection of failed task filenames."""
        service = TaskRetryService()

        failed_files = [
            "high-1773185511.failed.done.md",
            "normal-1234567890.failed.done.md",
            "LOW-ABC.failed.done.md",  # case insensitive
        ]

        not_failed_files = [
            "high-1773185511.md",
            "normal-1234567890.executing.md",
            "low-123.completed.done.md",
        ]

        for filename in failed_files:
            with self.subTest(filename=filename):
                self.assertTrue(service.is_failed_task(filename))

        for filename in not_failed_files:
            with self.subTest(filename=filename):
                self.assertFalse(service.is_failed_task(filename))

    def test_validate_agent(self):
        """Test agent validation."""
        service = TaskRetryService()

        valid_agents = ["kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei", "tolui"]
        invalid_agents = ["invalid", "GPT4", "claude", ""]

        for agent in valid_agents:
            with self.subTest(agent=agent):
                self.assertTrue(service.validate_agent(agent))

        for agent in invalid_agents:
            with self.subTest(agent=agent):
                self.assertFalse(service.validate_agent(agent))

    def test_parse_task_frontmatter(self):
        """Test YAML frontmatter parsing."""
        service = TaskRetryService()

        frontmatter = service.parse_task_frontmatter(self.failed_task_path)

        self.assertEqual(frontmatter.get("agent"), "temujin")
        self.assertEqual(frontmatter.get("priority"), "high")
        self.assertEqual(frontmatter.get("timeout"), "7200")

    def test_extract_task_title(self):
        """Test task title extraction."""
        service = TaskRetryService()

        title = service.extract_task_title(self.failed_task_path)

        self.assertEqual(title, "Test task for retry functionality")

    def test_extract_error_excerpt(self):
        """Test error excerpt extraction."""
        service = TaskRetryService()

        error = service.extract_error_excerpt(self.failed_task_path)

        self.assertIsNotNone(error)
        self.assertIn("Rate limit exceeded", error)

    def test_retry_count_initial(self):
        """Test retry count for task without history."""
        service = TaskRetryService()

        frontmatter = service.parse_task_frontmatter(self.failed_task_path)
        count = service.extract_retry_count(frontmatter)

        self.assertEqual(count, 0)


def run_integration_test():
    """Run a simple integration test with real files."""
    print("\n=== Integration Test ===\n")

    from kurultai_paths import agent_tasks_dir, VALID_AGENTS

    service = TaskRetryService()

    # List all failed tasks
    print("1. Listing failed tasks...")
    failed_tasks = service.list_failed_tasks()

    if failed_tasks:
        print(f"   Found {len(failed_tasks)} failed tasks:")
        for task in failed_tasks[:5]:  # Show first 5
            print(f"   - [{task.agent}] {task.filename}")
            print(f"     Title: {task.title}")
            print(f"     Retries: {task.retry_count}")
    else:
        print("   No failed tasks found in system")

    # Show statistics
    print("\n2. Task statistics:")
    by_agent = {}
    for task in failed_tasks:
        by_agent[task.agent] = by_agent.get(task.agent, 0) + 1

    for agent in sorted(by_agent):
        print(f"   {agent}: {by_agent[agent]} failed")

    print(f"\n   Total: {len(failed_tasks)} failed tasks")

    # Test validation
    print("\n3. Testing validation...")
    test_cases = [
        ("temujin", "high-1773185511.failed.done.md", True),
        ("invalid_agent", "some-file.failed.done.md", False),
        ("temujin", "not-a-failed-file.md", False),
    ]

    for agent, filename, should_pass in test_cases:
        valid_agent = service.validate_agent(agent)
        is_failed = service.is_failed_task(filename)
        result = valid_agent and is_failed

        status = "✓" if result == should_pass else "✗"
        print(f"   {status} {agent}/{filename}: valid={valid_agent}, failed={is_failed}")

    print("\n=== Integration Test Complete ===\n")


def main():
    """Run tests."""
    import argparse

    parser = argparse.ArgumentParser(description="Test task retry functionality")
    parser.add_argument("--unit", action="store_true", help="Run unit tests")
    parser.add_argument("--integration", action="store_true", help="Run integration tests")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    if not args.unit and not args.integration:
        # Run both by default
        args.unit = True
        args.integration = True

    if args.unit:
        print("Running unit tests...\n")
        verbosity = 2 if args.verbose else 1
        unittest.main(argv=[""], exit=False, verbosity=verbosity)

    if args.integration:
        try:
            run_integration_test()
        except Exception as e:
            print(f"Integration test failed: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
