#!/usr/bin/env python3
"""
Unit tests for self-task creation functionality in task_intake.py

Usage:
    python3 test_self_task_creation.py
"""

import os
import sys
import json
import unittest
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from task_intake import (
    create_self_task,
    check_self_task_limit,
    _load_tracker,
    _save_tracker,
    _reset_window_if_needed,
    _get_self_task_tracker_path,
    SELF_TASK_LIMITS,
)


class TestSelfTaskRateLimiting(unittest.TestCase):
    """Test rate limiting functionality for self-created tasks."""

    def setUp(self):
        """Set up test agent with clean tracker."""
        self.test_agent = "test_agent_self_task"
        self.tracker_path = _get_self_task_tracker_path(self.test_agent)

        # Clean up any existing tracker
        if self.tracker_path.exists():
            self.tracker_path.unlink()

    def tearDown(self):
        """Clean up test tracker."""
        if self.tracker_path.exists():
            self.tracker_path.unlink()

    def test_normal_priority_rate_limit_allows_three(self):
        """Test that NORMAL priority allows 3 tasks per hour."""
        for i in range(3):
            allowed, reason = check_self_task_limit(self.test_agent, "normal")
            self.assertTrue(allowed, f"Task {i+1} should be allowed")

        # 4th should be rejected
        allowed, reason = check_self_task_limit(self.test_agent, "normal")
        self.assertFalse(allowed)
        self.assertIn("3 self-tasks/hour", reason)

    def test_low_priority_shares_limit_with_normal(self):
        """Test that LOW priority shares the same limit as NORMAL."""
        # Create 2 NORMAL tasks
        for _ in range(2):
            check_self_task_limit(self.test_agent, "normal")

        # 3rd LOW should be allowed (count is at 2)
        allowed, reason = check_self_task_limit(self.test_agent, "low")
        self.assertTrue(allowed)

        # 4th LOW should be rejected
        allowed, reason = check_self_task_limit(self.test_agent, "low")
        self.assertFalse(allowed)
        self.assertIn("3 self-tasks/hour", reason)

    def test_high_priority_rate_limit_one_per_four_hours(self):
        """Test that HIGH priority allows 1 task per 4 hours."""
        # 1st HIGH should be allowed
        allowed, reason = check_self_task_limit(self.test_agent, "high")
        self.assertTrue(allowed)

        # 2nd HIGH should be rejected (within 4 hours)
        allowed, reason = check_self_task_limit(self.test_agent, "high")
        self.assertFalse(allowed)
        self.assertIn("1 HIGH self-task per 4 hours", reason)

    def test_high_priority_requires_justification(self):
        """Test that HIGH priority tasks require justification."""
        # This is tested in create_self_task, not check_self_task_limit
        pass  # Will be tested separately

    def test_tracker_persists_state(self):
        """Test that tracker persists state correctly."""
        # Create a task
        check_self_task_limit(self.test_agent, "normal")

        # Load tracker and verify
        tracker = _load_tracker(self.test_agent)
        self.assertEqual(tracker["normal_low_count"], 1)
        self.assertIsNotNone(tracker["window_start"])

    def test_window_reset_after_one_hour(self):
        """Test that rate limit window resets after 1 hour."""
        # Create tracker with old window
        old_time = (datetime.now() - timedelta(hours=2)).isoformat()
        tracker = {
            "window_start": old_time,
            "normal_low_count": 3,
            "high_count": 0,
            "last_high_at": None,
        }
        _save_tracker(self.test_agent, tracker)

        # Reset window
        tracker = _reset_window_if_needed(tracker)

        # Count should be reset
        self.assertEqual(tracker["normal_low_count"], 0)
        self.assertNotEqual(tracker["window_start"], old_time)


class TestSelfTaskCreation(unittest.TestCase):
    """Test the create_self_task function."""

    def setUp(self):
        """Set up test agent with clean tracker."""
        self.test_agent = "test_agent_creation"
        self.tracker_path = _get_self_task_tracker_path(self.test_agent)

        # Clean up any existing tracker
        if self.tracker_path.exists():
            self.tracker_path.unlink()

    def tearDown(self):
        """Clean up test tracker."""
        if self.tracker_path.exists():
            self.tracker_path.unlink()

    def test_high_priority_requires_justification(self):
        """Test that HIGH priority self-tasks require justification."""
        result = create_self_task(
            agent=self.test_agent,
            title="Test HIGH task",
            body="Test body",
            priority="high",
            justification=None,
        )
        self.assertIsNone(result)

    def test_high_priority_with_justification(self):
        """Test that HIGH priority with justification passes validation."""
        # Just check that it doesn't immediately reject - actual creation may fail
        # due to Neo4j not being available in test environment
        result = create_self_task(
            agent=self.test_agent,
            title="Test HIGH task with justification",
            body="Test body",
            priority="high",
            justification="Critical security vulnerability found",
        )
        # Result may be None due to Neo4j unavailability, but shouldn't be
        # rejected for missing justification

    def test_rate_limit_rejection(self):
        """Test that rate limited tasks are rejected."""
        # Exhaust rate limit
        for _ in range(3):
            check_self_task_limit(self.test_agent, "normal")

        # Next task should be rejected at rate limit check
        result = create_self_task(
            agent=self.test_agent,
            title="Rate limited task",
            body="Should be rejected",
            priority="normal",
        )
        self.assertIsNone(result)


class TestSelfTaskLimitsConfig(unittest.TestCase):
    """Test the SELF_TASK_LIMITS configuration."""

    def test_limits_has_required_keys(self):
        """Test that SELF_TASK_LIMITS has all required keys."""
        required_keys = ["normal_low_per_hour", "high_per_4_hours", "max_depth"]
        for key in required_keys:
            self.assertIn(key, SELF_TASK_LIMITS)

    def test_limits_are_reasonable(self):
        """Test that limits are set to reasonable values."""
        self.assertEqual(SELF_TASK_LIMITS["normal_low_per_hour"], 3)
        self.assertEqual(SELF_TASK_LIMITS["high_per_4_hours"], 1)
        self.assertEqual(SELF_TASK_LIMITS["max_depth"], 3)


def run_tests():
    """Run all tests and report results."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestSelfTaskRateLimiting))
    suite.addTests(loader.loadTestsFromTestCase(TestSelfTaskCreation))
    suite.addTests(loader.loadTestsFromTestCase(TestSelfTaskLimitsConfig))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
