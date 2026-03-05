#!/usr/bin/env python3
"""
Tests for auto_dispatch.py — Periodic task dispatcher for Kurultai agents.

Run:
    python3 test_auto_dispatch.py
    python3 -m pytest test_auto_dispatch.py -v
"""

import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add scripts dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import auto_dispatch


class TestAutoDispatchBase(unittest.TestCase):
    """Base class with temp directory setup."""

    def setUp(self):
        """Create temp agent directory structure."""
        self.tmpdir = Path(tempfile.mkdtemp(prefix="autodispatch_test_"))
        self.agents_base = self.tmpdir / "agents"

        # Create agent directories with task subdirs
        for agent in ["temujin", "mongke", "chagatai", "jochi", "ogedei"]:
            (self.agents_base / agent / "tasks").mkdir(parents=True)

        # Create main/logs for dispatch log
        (self.agents_base / "main/logs").mkdir(parents=True)

        # Patch module constants
        self._patches = [
            patch.object(auto_dispatch, "AGENTS_BASE", self.agents_base),
            patch.object(auto_dispatch, "DISPATCH_LOG", self.agents_base / "main/logs/auto-dispatch.jsonl"),
            patch.object(auto_dispatch, "DISPATCH_STATE", self.agents_base / "main/logs/auto-dispatch-state.json"),
            patch.object(auto_dispatch, "LOCK_FILE", self.agents_base / "main/logs/auto-dispatch.lock"),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def create_task(self, agent, name, content="# Task: Test task\n\nDo something."):
        """Helper to create a task file."""
        task_path = self.agents_base / agent / "tasks" / name
        task_path.write_text(content)
        return task_path


class TestListPendingTasks(TestAutoDispatchBase):
    """Test pending task listing and priority ordering."""

    def test_empty_queue(self):
        result = auto_dispatch.list_pending_tasks("temujin")
        self.assertEqual(result, [])

    def test_single_pending_task(self):
        self.create_task("temujin", "normal-1234.md")
        result = auto_dispatch.list_pending_tasks("temujin")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "normal-1234.md")

    def test_skips_done_tasks(self):
        self.create_task("temujin", "normal-1234.completed.done.md")
        self.create_task("temujin", "normal-1235.done.md")
        self.create_task("temujin", "normal-1236.md")
        result = auto_dispatch.list_pending_tasks("temujin")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "normal-1236.md")

    def test_skips_executing_tasks(self):
        self.create_task("temujin", "normal-1234.md.executing")
        self.create_task("temujin", "normal-1235.md")
        result = auto_dispatch.list_pending_tasks("temujin")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "normal-1235.md")

    def test_priority_ordering(self):
        # Create in reverse priority order
        self.create_task("temujin", "low-1234.md")
        time.sleep(0.01)
        self.create_task("temujin", "normal-1234.md")
        time.sleep(0.01)
        self.create_task("temujin", "high-1234.md")

        result = auto_dispatch.list_pending_tasks("temujin")
        self.assertEqual(len(result), 3)
        self.assertTrue(result[0].name.startswith("high-"))
        self.assertTrue(result[1].name.startswith("normal-"))
        self.assertTrue(result[2].name.startswith("low-"))

    def test_fifo_within_priority(self):
        """Older tasks should come first within same priority."""
        self.create_task("temujin", "normal-1000.md")
        # Ensure different mtime
        time.sleep(0.05)
        self.create_task("temujin", "normal-2000.md")

        result = auto_dispatch.list_pending_tasks("temujin")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].name, "normal-1000.md")
        self.assertEqual(result[1].name, "normal-2000.md")

    def test_nonexistent_agent_dir(self):
        result = auto_dispatch.list_pending_tasks("nonexistent")
        self.assertEqual(result, [])

    def test_direct_tasks_treated_as_normal(self):
        self.create_task("temujin", "high-1234.md")
        time.sleep(0.01)
        self.create_task("temujin", "direct-1234.md")
        time.sleep(0.01)
        self.create_task("temujin", "low-1234.md")

        result = auto_dispatch.list_pending_tasks("temujin")
        self.assertEqual(len(result), 3)
        # high first, then direct (as normal), then low
        self.assertTrue(result[0].name.startswith("high-"))
        self.assertTrue(result[1].name.startswith("direct-"))
        self.assertTrue(result[2].name.startswith("low-"))


class TestListExecutingTasks(TestAutoDispatchBase):
    """Test executing task detection."""

    def test_no_executing(self):
        self.create_task("temujin", "normal-1234.md")
        result = auto_dispatch.list_executing_tasks("temujin")
        self.assertEqual(result, [])

    def test_finds_executing(self):
        self.create_task("temujin", "normal-1234.md.executing")
        result = auto_dispatch.list_executing_tasks("temujin")
        self.assertEqual(len(result), 1)

    def test_finds_executing_suffix(self):
        self.create_task("temujin", "high-1234.executing.md")
        result = auto_dispatch.list_executing_tasks("temujin")
        self.assertEqual(len(result), 1)


class TestCleanupStaleExecuting(TestAutoDispatchBase):
    """Test stale .executing task cleanup."""

    def test_reverts_stale_task(self):
        task = self.create_task("temujin", "normal-1234.md.executing")
        # Make the file appear old
        old_time = time.time() - 1200  # 20 minutes ago
        os.utime(task, (old_time, old_time))

        reverted = auto_dispatch.cleanup_stale_executing("temujin")
        self.assertEqual(reverted, 1)

        # Original file should exist now
        original = self.agents_base / "temujin/tasks/normal-1234.md"
        self.assertTrue(original.exists())
        self.assertFalse(task.exists())

    def test_keeps_fresh_executing(self):
        task = self.create_task("temujin", "normal-1234.md.executing")
        # File was just created, so it's fresh

        reverted = auto_dispatch.cleanup_stale_executing("temujin")
        self.assertEqual(reverted, 0)
        self.assertTrue(task.exists())  # Still executing

    def test_multiple_stale_tasks(self):
        for i in range(3):
            task = self.create_task("temujin", f"normal-{1000+i}.md.executing")
            old_time = time.time() - 1200
            os.utime(task, (old_time, old_time))

        reverted = auto_dispatch.cleanup_stale_executing("temujin")
        self.assertEqual(reverted, 3)


class TestReadTaskContent(TestAutoDispatchBase):
    """Test task content reading."""

    def test_reads_title(self):
        task = self.create_task("temujin", "high-1234.md",
            "---\nagent: temujin\n---\n\n# Task: Build the login feature\n\nDetails here.")
        title, content = auto_dispatch.read_task_content(task)
        self.assertEqual(title, "Build the login feature")

    def test_reads_generic_heading(self):
        task = self.create_task("temujin", "normal-1234.md",
            "# Fix the bug\n\nSome body text.")
        title, content = auto_dispatch.read_task_content(task)
        self.assertEqual(title, "Fix the bug")

    def test_fallback_to_filename(self):
        task = self.create_task("temujin", "normal-1234.md",
            "No heading here, just text.")
        title, content = auto_dispatch.read_task_content(task)
        self.assertEqual(title, "normal-1234")


class TestDispatchTask(TestAutoDispatchBase):
    """Test task dispatching."""

    def test_dry_run_does_not_modify(self):
        task = self.create_task("temujin", "normal-1234.md")
        success, msg = auto_dispatch.dispatch_task("temujin", task, dry_run=True)
        self.assertTrue(success)
        self.assertEqual(msg, "dry_run")
        self.assertTrue(task.exists())  # File not moved

    @patch("auto_dispatch.subprocess.Popen")
    def test_successful_dispatch(self, mock_popen):
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_popen.return_value = mock_proc

        task = self.create_task("temujin", "normal-1234.md",
            "# Task: Test task\n\nDo the thing.")

        success, msg = auto_dispatch.dispatch_task("temujin", task)
        self.assertTrue(success)
        self.assertIn("12345", msg)

        # File should be renamed to .executing
        self.assertFalse(task.exists())
        executing = self.agents_base / "temujin/tasks/normal-1234.md.executing"
        self.assertTrue(executing.exists())

        # Popen should have been called with correct args
        call_args = mock_popen.call_args
        cmd = call_args[0][0]
        self.assertIn("openclaw", cmd[0])
        self.assertIn("--agent", cmd)
        self.assertIn("temujin", cmd)

    @patch("auto_dispatch.OPENCLAW_BIN", "/nonexistent/openclaw")
    @patch("auto_dispatch.subprocess.Popen", side_effect=FileNotFoundError)
    def test_missing_openclaw_reverts(self, mock_popen):
        task = self.create_task("temujin", "normal-1234.md")
        success, msg = auto_dispatch.dispatch_task("temujin", task)
        self.assertFalse(success)
        self.assertIn("not found", msg)
        # File should be reverted
        self.assertTrue(task.exists())


class TestRunCycle(TestAutoDispatchBase):
    """Test full dispatch cycle."""

    @patch("auto_dispatch.dispatch_task")
    def test_dispatches_to_idle_agent(self, mock_dispatch):
        mock_dispatch.return_value = (True, "PID 123")
        self.create_task("temujin", "normal-1234.md")

        stats = auto_dispatch.run_cycle()
        self.assertEqual(stats["dispatched"], 1)
        self.assertEqual(stats["skipped_empty"], 4)  # other 4 agents empty
        mock_dispatch.assert_called_once()

    @patch("auto_dispatch.dispatch_task")
    def test_skips_busy_agent(self, mock_dispatch):
        self.create_task("temujin", "normal-1234.md.executing")
        self.create_task("temujin", "normal-1235.md")  # pending but agent busy

        stats = auto_dispatch.run_cycle(target_agent="temujin")
        self.assertEqual(stats["dispatched"], 0)
        self.assertEqual(stats["skipped_busy"], 1)
        mock_dispatch.assert_not_called()

    @patch("auto_dispatch.dispatch_task")
    def test_respects_max_dispatches(self, mock_dispatch):
        mock_dispatch.return_value = (True, "PID 123")

        # Create tasks for all 5 agents
        for agent in auto_dispatch.DISPATCH_AGENTS:
            self.create_task(agent, "high-1234.md")

        stats = auto_dispatch.run_cycle()
        # Should stop at MAX_DISPATCHES_PER_CYCLE (3)
        self.assertEqual(stats["dispatched"], auto_dispatch.MAX_DISPATCHES_PER_CYCLE)

    def test_cleanup_only_mode(self):
        task = self.create_task("temujin", "normal-1234.md.executing")
        old_time = time.time() - 1200
        os.utime(task, (old_time, old_time))

        # Also create a pending task — should NOT be dispatched in cleanup mode
        self.create_task("temujin", "normal-1235.md")

        stats = auto_dispatch.run_cycle(cleanup_only=True)
        self.assertEqual(stats["reverted"], 1)
        self.assertEqual(stats["dispatched"], 0)

    @patch("auto_dispatch.dispatch_task")
    def test_single_agent_mode(self, mock_dispatch):
        mock_dispatch.return_value = (True, "PID 123")
        self.create_task("temujin", "normal-1234.md")
        self.create_task("mongke", "normal-1234.md")

        stats = auto_dispatch.run_cycle(target_agent="temujin")
        self.assertEqual(stats["dispatched"], 1)
        # Should only have processed temujin
        self.assertEqual(stats["skipped_empty"], 0)
        self.assertEqual(stats["skipped_busy"], 0)

    def test_all_empty_queues(self):
        stats = auto_dispatch.run_cycle()
        self.assertEqual(stats["dispatched"], 0)
        self.assertEqual(stats["skipped_empty"], 5)

    @patch("auto_dispatch.dispatch_task")
    def test_cleans_stale_before_dispatch(self, mock_dispatch):
        """Stale .executing should be reverted, making the agent available."""
        mock_dispatch.return_value = (True, "PID 123")

        # Create a stale executing task
        stale = self.create_task("temujin", "normal-1234.md.executing")
        old_time = time.time() - 1200
        os.utime(stale, (old_time, old_time))

        # The reverted task becomes the new pending task
        stats = auto_dispatch.run_cycle(target_agent="temujin")
        self.assertEqual(stats["reverted"], 1)
        self.assertEqual(stats["dispatched"], 1)


class TestDispatchLog(TestAutoDispatchBase):
    """Test JSONL logging."""

    def test_log_dispatch_creates_file(self):
        auto_dispatch.log_dispatch({"action": "test", "ts": "2026-03-05T00:00:00"})
        log_path = self.agents_base / "main/logs/auto-dispatch.jsonl"
        self.assertTrue(log_path.exists())

        with open(log_path) as f:
            entry = json.loads(f.readline())
        self.assertEqual(entry["action"], "test")

    def test_log_dispatch_appends(self):
        auto_dispatch.log_dispatch({"action": "first"})
        auto_dispatch.log_dispatch({"action": "second"})

        log_path = self.agents_base / "main/logs/auto-dispatch.jsonl"
        with open(log_path) as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 2)


class TestAcquireLock(TestAutoDispatchBase):
    """Test lock file mechanism."""

    def test_acquire_and_release(self):
        lock_fd = auto_dispatch.acquire_lock()
        self.assertIsNotNone(lock_fd)

        # Second acquire should fail
        lock_fd2 = auto_dispatch.acquire_lock()
        self.assertIsNone(lock_fd2)

        # Release and re-acquire should work
        import fcntl
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()

        lock_fd3 = auto_dispatch.acquire_lock()
        self.assertIsNotNone(lock_fd3)
        fcntl.flock(lock_fd3, fcntl.LOCK_UN)
        lock_fd3.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
