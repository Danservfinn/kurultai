"""Tests for unified heartbeat system."""

import pytest
import asyncio
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import sys
import os

# Add tools/kurultai to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'tools', 'kurultai'))

from heartbeat_master import HeartbeatTask, UnifiedHeartbeat, CycleResult


class TestHeartbeatTask:
    """Test the HeartbeatTask dataclass and its methods."""

    def test_should_run_every_5_min(self):
        """Tasks with 5 min frequency should run every cycle."""
        task = HeartbeatTask(
            name="test",
            agent="agent",
            frequency_minutes=5,
            max_tokens=100,
            handler=AsyncMock(),
            description="Test task"
        )
        assert task.should_run(1) is True
        assert task.should_run(2) is True
        assert task.should_run(100) is True

    def test_should_run_every_15_min(self):
        """Tasks with 15 min frequency should run every 3 cycles."""
        task = HeartbeatTask(
            name="test",
            agent="agent",
            frequency_minutes=15,
            max_tokens=100,
            handler=AsyncMock(),
            description="Test task"
        )
        assert task.should_run(1) is False   # 5 min
        assert task.should_run(2) is False   # 10 min
        assert task.should_run(3) is True    # 15 min
        assert task.should_run(6) is True    # 30 min
        assert task.should_run(9) is True    # 45 min

    def test_should_run_every_60_min(self):
        """Tasks with 60 min frequency should run every 12 cycles."""
        task = HeartbeatTask(
            name="test",
            agent="agent",
            frequency_minutes=60,
            max_tokens=100,
            handler=AsyncMock(),
            description="Test task"
        )
        assert task.should_run(1) is False   # 5 min
        assert task.should_run(11) is False  # 55 min
        assert task.should_run(12) is True   # 60 min
        assert task.should_run(24) is True   # 120 min

    def test_should_run_daily(self):
        """Tasks with daily frequency should run every 288 cycles (24h / 5min)."""
        task = HeartbeatTask(
            name="test",
            agent="agent",
            frequency_minutes=1440,  # 24 hours
            max_tokens=100,
            handler=AsyncMock(),
            description="Test task"
        )
        assert task.should_run(1) is False
        assert task.should_run(287) is False
        assert task.should_run(288) is True
        assert task.should_run(576) is True

    def test_disabled_task_never_runs(self):
        """Disabled tasks should never run."""
        task = HeartbeatTask(
            name="test",
            agent="agent",
            frequency_minutes=5,
            max_tokens=100,
            handler=AsyncMock(),
            description="Test task",
            enabled=False
        )
        assert task.should_run(1) is False
        assert task.should_run(100) is False


class TestUnifiedHeartbeat:
    """Test the UnifiedHeartbeat orchestrator."""

    @pytest.fixture
    def mock_driver(self):
        """Create a mock Neo4j driver."""
        return Mock()

    @pytest.fixture
    def heartbeat(self, mock_driver):
        """Create a UnifiedHeartbeat instance with mock driver."""
        return UnifiedHeartbeat(mock_driver)

    def test_register_task(self, heartbeat):
        """Test that tasks can be registered."""
        task = HeartbeatTask(
            name="test_task",
            agent="test_agent",
            frequency_minutes=5,
            max_tokens=100,
            handler=AsyncMock(),
            description="Test description"
        )
        heartbeat.register(task)

        assert len(heartbeat.tasks) == 1
        assert heartbeat.tasks[0].name == "test_task"
        assert heartbeat.tasks[0].agent == "test_agent"

    def test_register_multiple_tasks(self, heartbeat):
        """Test that multiple tasks can be registered."""
        for i in range(3):
            task = HeartbeatTask(
                name=f"task_{i}",
                agent="agent",
                frequency_minutes=5,
                max_tokens=100,
                handler=AsyncMock(),
                description=f"Task {i}"
            )
            heartbeat.register(task)

        assert len(heartbeat.tasks) == 3

    def test_get_tasks_for_agent(self, heartbeat):
        """Test filtering tasks by agent."""
        heartbeat.register(HeartbeatTask(
            name="task1", agent="ogedei", frequency_minutes=5,
            max_tokens=100, handler=AsyncMock(), description=""
        ))
        heartbeat.register(HeartbeatTask(
            name="task2", agent="jochi", frequency_minutes=5,
            max_tokens=100, handler=AsyncMock(), description=""
        ))
        heartbeat.register(HeartbeatTask(
            name="task3", agent="ogedei", frequency_minutes=15,
            max_tokens=100, handler=AsyncMock(), description=""
        ))

        ogedei_tasks = heartbeat.get_tasks_for_agent("ogedei")
        assert len(ogedei_tasks) == 2
        assert all(t.agent == "ogedei" for t in ogedei_tasks)

    def test_enable_disable_task(self, heartbeat):
        """Test enabling and disabling tasks."""
        task = HeartbeatTask(
            name="test_task",
            agent="test_agent",
            frequency_minutes=5,
            max_tokens=100,
            handler=AsyncMock(),
            description="Test"
        )
        heartbeat.register(task)

        # Disable
        assert heartbeat.disable_task("test_agent", "test_task") is True
        assert task.enabled is False
        assert task.should_run(1) is False

        # Enable
        assert heartbeat.enable_task("test_agent", "test_task") is True
        assert task.enabled is True
        assert task.should_run(1) is True

    @pytest.mark.asyncio
    async def test_run_cycle_executes_eligible_tasks(self, heartbeat):
        """Test that run_cycle executes tasks that should run."""
        mock_handler_5min = AsyncMock(return_value={"summary": "OK"})
        mock_handler_15min = AsyncMock(return_value={"summary": "OK"})

        heartbeat.register(HeartbeatTask(
            name="rapid_task",
            agent="agent",
            frequency_minutes=5,
            max_tokens=100,
            handler=mock_handler_5min,
            description="Runs every cycle"
        ))

        heartbeat.register(HeartbeatTask(
            name="slow_task",
            agent="agent",
            frequency_minutes=15,
            max_tokens=100,
            handler=mock_handler_15min,
            description="Runs every 3 cycles"
        ))

        result = await heartbeat.run_cycle()

        # First cycle: only 5min task should run
        assert isinstance(result, CycleResult)
        assert result.tasks_run == 1
        assert result.tasks_succeeded == 1
        mock_handler_5min.assert_called_once()
        mock_handler_15min.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_cycle_increments_cycle_count(self, heartbeat):
        """Test that cycle_count increments after each run."""
        assert heartbeat.cycle_count == 0

        mock_handler = AsyncMock(return_value={"summary": "OK"})
        heartbeat.register(HeartbeatTask(
            name="task",
            agent="agent",
            frequency_minutes=5,
            max_tokens=100,
            handler=mock_handler,
            description="Test"
        ))

        await heartbeat.run_cycle()
        assert heartbeat.cycle_count == 1

        await heartbeat.run_cycle()
        assert heartbeat.cycle_count == 2

    @pytest.mark.asyncio
    async def test_run_cycle_handles_errors(self, heartbeat):
        """Test that run_cycle handles task errors gracefully."""
        mock_handler_success = AsyncMock(return_value={"summary": "OK"})
        mock_handler_error = AsyncMock(side_effect=Exception("Task failed"))

        heartbeat.register(HeartbeatTask(
            name="success_task",
            agent="agent",
            frequency_minutes=5,
            max_tokens=100,
            handler=mock_handler_success,
            description="Success"
        ))

        heartbeat.register(HeartbeatTask(
            name="error_task",
            agent="agent",
            frequency_minutes=5,
            max_tokens=100,
            handler=mock_handler_error,
            description="Error"
        ))

        result = await heartbeat.run_cycle()

        assert result.tasks_run == 2
        assert result.tasks_succeeded == 1
        assert result.tasks_failed == 1

        # Check error is recorded in results
        error_result = [r for r in result.results if r["status"] == "error"]
        assert len(error_result) == 1
        assert "Task failed" in error_result[0]["error"]

    @pytest.mark.asyncio
    async def test_run_cycle_respects_timeout(self, heartbeat):
        """Test that tasks are subject to timeout based on max_tokens."""
        async def slow_handler(driver):
            await asyncio.sleep(35)  # Will exceed 30s minimum timeout
            return {"summary": "OK"}

        heartbeat.register(HeartbeatTask(
            name="slow_task",
            agent="agent",
            frequency_minutes=5,
            max_tokens=50,  # 30s minimum timeout (max(30, 50/100))
            handler=slow_handler,
            description="Slow task"
        ))

        result = await heartbeat.run_cycle()

        assert result.tasks_run == 1
        assert result.tasks_failed == 1

        timeout_result = [r for r in result.results if r["status"] == "timeout"]
        assert len(timeout_result) == 1


class TestCycleResult:
    """Test the CycleResult dataclass."""

    def test_cycle_result_creation(self):
        """Test that CycleResult can be created with required fields."""
        result = CycleResult(
            cycle_number=1,
            started_at=datetime(2026, 2, 8, 10, 0, 0, tzinfo=timezone.utc),
            completed_at=datetime(2026, 2, 8, 10, 0, 30, tzinfo=timezone.utc),
            tasks_run=3,
            tasks_succeeded=2,
            tasks_failed=1,
            results=[{"task": "test", "status": "success"}],
            total_tokens=1000
        )

        assert result.cycle_number == 1
        assert result.tasks_run == 3
        assert result.tasks_succeeded == 2
        assert result.tasks_failed == 1
        assert len(result.results) == 1
        assert result.total_tokens == 1000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
