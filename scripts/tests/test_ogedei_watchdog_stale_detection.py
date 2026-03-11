#!/usr/bin/env python3
"""
Tests for Ogedei Watchdog stale task detection.

Specifically tests the fix for false positive stale task detection
on completed tasks with patterns like:
- .verified.done.md
- .completed.done.md
- .no_output.done.md
- .failed.done.md
- Any pattern ending in .done.md

Run with: pytest test_ogedei_watchdog_stale_detection.py -v
"""

import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestStaleTaskDetection:
    """Tests for stale task detection false positive prevention."""

    def test_stale_task_detection_skips_verified_done(self, tmp_path):
        """Test that .verified.done.md files are not flagged as stale."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()

        agent = agents_dir / "testagent"
        agent.mkdir()
        tasks = agent / "tasks"
        tasks.mkdir()

        # Create completed task files that should NOT be flagged as stale
        (tasks / "task-001.verified.done.md").write_text("# Verified done")
        (tasks / "task-002.completed.done.md").write_text("# Completed done")
        (tasks / "task-003.no_output.done.md").write_text("# No output done")
        (tasks / "task-004.failed.done.md").write_text("# Failed done")
        (tasks / "task-005.done.md").write_text("# Done")
        (tasks / "task-006.failed.md").write_text("# Failed")
        (tasks / "task-007.completed.md").write_text("# Completed")

        # Create one legitimate stale executing file
        stale_exec = tasks / "task-008.executing.md"
        stale_exec.write_text("# Stale executing")
        # Set modification time to 2 hours ago
        old_time = time.time() - (2 * 3600)
        import os
        os.utime(stale_exec, (old_time, old_time))

        with patch('scripts.ogedei_watchdog.AGENTS_DIR', agents_dir):
            # Import after patching
            from scripts.ogedei_watchdog import check_stalled_tasks
            state = {}
            issues = check_stalled_tasks(state)

            # Should only find the one legitimate stale executing file
            assert len(issues) == 1
            assert "task-008.executing.md" in issues[0]

    def test_stale_task_detection_skips_completed_executing_patterns(self, tmp_path):
        """Test that .executing.md files with completion markers are not flagged."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()

        agent = agents_dir / "testagent"
        agent.mkdir()
        tasks = agent / "tasks"
        tasks.mkdir()

        # Create executing files with completion markers - should be skipped
        old_time = time.time() - (2 * 3600)
        import os

        completed_executing = tasks / "task-001.verified.done.md.executing.md"
        completed_executing.write_text("# Verified done executing (should be skipped)")
        os.utime(completed_executing, (old_time, old_time))

        with patch('scripts.ogedei_watchdog.AGENTS_DIR', agents_dir):
            from scripts.ogedei_watchdog import check_stalled_tasks
            state = {}
            issues = check_stalled_tasks(state)

            # Should NOT flag the completed executing file
            assert len(issues) == 0

    def test_stale_task_detection_catches_real_stale_file(self, tmp_path):
        """Test that legitimate stale .executing.md files are still detected."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()

        agent = agents_dir / "testagent"
        agent.mkdir()
        tasks = agent / "tasks"
        tasks.mkdir()

        # Create a legitimately stale executing file
        stale_exec = tasks / "task-stale.executing.md"
        stale_exec.write_text("# This is legitimately stale")

        # Set modification time to 2 hours ago (> 3600s threshold)
        old_time = time.time() - (2 * 3600)
        import os
        os.utime(stale_exec, (old_time, old_time))

        with patch('scripts.ogedei_watchdog.AGENTS_DIR', agents_dir):
            from scripts.ogedei_watchdog import check_stalled_tasks
            state = {}
            issues = check_stalled_tasks(state)

            # Should detect the stale file
            assert len(issues) == 1
            assert "task-stale.executing.md" in issues[0]

    def test_stale_task_detection_recent_executing_not_flagged(self, tmp_path):
        """Test that recent .executing.md files are not flagged."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()

        agent = agents_dir / "testagent"
        agent.mkdir()
        tasks = agent / "tasks"
        tasks.mkdir()

        # Create a recent executing file (10 minutes old, < 900s threshold)
        recent_exec = tasks / "task-recent.executing.md"
        recent_exec.write_text("# Recent executing")

        # Set modification time to 10 minutes ago
        recent_time = time.time() - (10 * 60)
        import os
        os.utime(recent_exec, (recent_time, recent_time))

        with patch('scripts.ogedei_watchdog.AGENTS_DIR', agents_dir):
            from scripts.ogedei_watchdog import check_stalled_tasks
            state = {}
            issues = check_stalled_tasks(state)

            # Should NOT flag recent executing file
            assert len(issues) == 0


class TestQueueCleanupCompletedDetection:
    """Tests for queue cleanup completed task detection."""

    def test_is_task_completed_verified_done(self, tmp_path):
        """Test is_task_completed recognizes .verified.done.md."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()

        agent = agents_dir / "testagent"
        agent.mkdir()
        tasks = agent / "tasks"
        tasks.mkdir()

        # Create completed task
        (tasks / "high-12345.verified.done.md").write_text("# Verified done")

        with patch('scripts.queue_cleanup.AGENTS_DIR', agents_dir):
            from scripts.queue_cleanup import is_task_completed
            result = is_task_completed("12345", agent)
            assert result is True

    def test_is_task_completed_no_output_done(self, tmp_path):
        """Test is_task_completed recognizes .no_output.done.md."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()

        agent = agents_dir / "testagent"
        agent.mkdir()
        tasks = agent / "tasks"
        tasks.mkdir()

        # Create completed task
        (tasks / "high-12345.no_output.done.md").write_text("# No output done")

        with patch('scripts.queue_cleanup.AGENTS_DIR', agents_dir):
            from scripts.queue_cleanup import is_task_completed
            result = is_task_completed("12345", agent)
            assert result is True

    def test_is_task_completed_not_found(self, tmp_path):
        """Test is_task_completed returns False for non-existent task."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()

        agent = agents_dir / "testagent"
        agent.mkdir()
        tasks = agent / "tasks"
        tasks.mkdir()

        # Create pending task (not completed)
        (tasks / "high-12345.md").write_text("# Pending")

        with patch('scripts.queue_cleanup.AGENTS_DIR', agents_dir):
            from scripts.queue_cleanup import is_task_completed
            result = is_task_completed("12345", agent)
            assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
