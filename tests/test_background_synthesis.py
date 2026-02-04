"""
Tests for Chagatai Background Synthesis system.

This module tests the BackgroundTaskManager class for running background tasks
when agents are idle, including reflection consolidation and knowledge synthesis.
"""

import pytest
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, MagicMock, patch

# Import the module under test
import sys
sys.path.insert(0, '/Users/kurultai/molt')

from tools.background_synthesis import (
    BackgroundTaskManager,
    BackgroundTaskError,
    TaskNotFoundError,
    create_background_task_manager,
    run_background_synthesis
)


class TestBackgroundTaskManager:
    """Test cases for BackgroundTaskManager."""

    @pytest.fixture
    def mock_memory(self):
        """Create a mock OperationalMemory."""
        memory = Mock()
        memory._generate_id.return_value = str(uuid.uuid4())
        memory._now.return_value = datetime.now(timezone.utc)

        # Mock session context manager
        mock_session = Mock()
        mock_context = MagicMock()
        mock_context.__enter__ = Mock(return_value=mock_session)
        mock_context.__exit__ = Mock(return_value=False)
        memory._session.return_value = mock_context

        return memory, mock_session

    @pytest.fixture
    def manager(self, mock_memory):
        """Create a BackgroundTaskManager with mock memory."""
        memory, _ = mock_memory
        return BackgroundTaskManager(
            memory=memory,
            reflection_threshold=5,
            idle_threshold_seconds=300
        )

    def test_init(self, mock_memory):
        """Test BackgroundTaskManager initialization."""
        memory, _ = mock_memory
        manager = BackgroundTaskManager(
            memory=memory,
            reflection_threshold=3,
            idle_threshold_seconds=60
        )

        assert manager.memory == memory
        assert manager.reflection_threshold == 3
        assert manager.idle_threshold_seconds == 60

    def test_is_agent_idle_no_status(self, manager, mock_memory):
        """Test idle detection when no agent status exists."""
        memory, _ = mock_memory
        memory.get_agent_status.return_value = None

        assert manager.is_agent_idle("test_agent") is True

    def test_is_agent_idle_busy_status(self, manager, mock_memory):
        """Test idle detection when agent is marked busy."""
        memory, _ = mock_memory
        memory.get_agent_status.return_value = {"status": "busy"}

        assert manager.is_agent_idle("test_agent") is False

    def test_is_agent_idle_recent_heartbeat(self, manager, mock_memory):
        """Test idle detection with recent heartbeat."""
        memory, _ = mock_memory
        now = datetime.now(timezone.utc)
        memory.get_agent_status.return_value = {
            "status": "active",
            "last_heartbeat": now.isoformat()
        }
        memory.list_tasks_by_status.return_value = []

        assert manager.is_agent_idle("test_agent") is False

    def test_is_agent_idle_old_heartbeat(self, manager, mock_memory):
        """Test idle detection with old heartbeat."""
        memory, _ = mock_memory
        old_time = datetime.now(timezone.utc) - timedelta(seconds=400)
        memory.get_agent_status.return_value = {
            "status": "active",
            "last_heartbeat": old_time.isoformat()
        }
        memory.list_tasks_by_status.return_value = []

        assert manager.is_agent_idle("test_agent") is True

    def test_is_agent_idle_with_in_progress_tasks(self, manager, mock_memory):
        """Test idle detection when agent has in-progress tasks."""
        memory, _ = mock_memory
        old_time = datetime.now(timezone.utc) - timedelta(seconds=400)
        memory.get_agent_status.return_value = {
            "status": "active",
            "last_heartbeat": old_time.isoformat()
        }
        memory.list_tasks_by_status.return_value = [{"id": "task1"}]

        assert manager.is_agent_idle("test_agent") is False

    def test_queue_task_invalid_type(self, manager):
        """Test queuing task with invalid type raises error."""
        with pytest.raises(ValueError, match="Invalid task_type"):
            manager.queue_task("invalid_type")

    def test_queue_task_invalid_priority(self, manager):
        """Test queuing task with invalid priority raises error."""
        with pytest.raises(ValueError, match="Invalid priority"):
            manager.queue_task("graph_maintenance", priority="urgent")

    def test_queue_task_success(self, manager, mock_memory):
        """Test successful task queuing."""
        memory, mock_session = mock_memory

        # Mock the session run result
        mock_record = Mock()
        mock_record.__getitem__ = Mock(return_value="task-123")
        mock_result = Mock()
        mock_result.single.return_value = mock_record
        mock_session.run.return_value = mock_result

        task_id = manager.queue_task("graph_maintenance", priority="high")

        assert task_id == "task-123"
        mock_session.run.assert_called_once()

    def test_queue_task_fallback_mode(self, manager, mock_memory):
        """Test task queuing in fallback mode."""
        memory, mock_session = mock_memory

        # Make session return None (fallback mode)
        mock_context = MagicMock()
        mock_context.__enter__ = Mock(return_value=None)
        mock_context.__exit__ = Mock(return_value=False)
        memory._session.return_value = mock_context

        task_id = manager.queue_task("graph_maintenance")

        # Should still return a task ID (generated locally)
        assert task_id is not None
        assert isinstance(task_id, str)

    def test_get_next_task(self, manager, mock_memory):
        """Test getting next pending task."""
        memory, mock_session = mock_memory

        # Mock the session run result - needs to be dict-convertible
        mock_node = {
            "id": "task-123",
            "task_type": "graph_maintenance",
            "priority": "high",
            "status": "pending",
            "data": None,
        }
        mock_record = {"t": mock_node}
        mock_result = Mock()
        mock_result.single.return_value = mock_record
        mock_session.run.return_value = mock_result

        task = manager.get_next_task()

        assert task is not None
        assert task["id"] == "task-123"

    def test_get_next_task_no_pending(self, manager, mock_memory):
        """Test getting next task when none pending."""
        memory, mock_session = mock_memory

        mock_result = Mock()
        mock_result.single.return_value = None
        mock_session.run.return_value = mock_result

        task = manager.get_next_task()

        assert task is None

    def test_start_task_success(self, manager, mock_memory):
        """Test starting a task."""
        memory, mock_session = mock_memory

        mock_result = Mock()
        mock_result.single.return_value = {"task_id": "task-123"}
        mock_session.run.return_value = mock_result

        result = manager.start_task("task-123")

        assert result is True

    def test_start_task_not_found(self, manager, mock_memory):
        """Test starting a non-existent task."""
        memory, mock_session = mock_memory

        mock_result = Mock()
        mock_result.single.return_value = None
        mock_session.run.return_value = mock_result

        with pytest.raises(TaskNotFoundError):
            manager.start_task("nonexistent")

    def test_complete_task_success(self, manager, mock_memory):
        """Test completing a task."""
        memory, mock_session = mock_memory

        mock_result = Mock()
        mock_result.single.return_value = {"task_id": "task-123"}
        mock_session.run.return_value = mock_result

        result = manager.complete_task("task-123", {"status": "done"})

        assert result is True

    def test_fail_task_success(self, manager, mock_memory):
        """Test failing a task."""
        memory, mock_session = mock_memory

        mock_result = Mock()
        mock_result.single.return_value = {"task_id": "task-123"}
        mock_session.run.return_value = mock_result

        result = manager.fail_task("task-123", "Something went wrong")

        assert result is True

    def test_list_tasks(self, manager, mock_memory):
        """Test listing tasks with filters."""
        memory, mock_session = mock_memory

        mock_node = {
            "id": "task-123",
            "task_type": "graph_maintenance",
            "status": "pending",
        }
        mock_record = {"t": mock_node}

        # Create a proper iterator mock - use a list which is iterable
        mock_result = [mock_record]
        mock_session.run.return_value = mock_result

        tasks = manager.list_tasks(status="pending")

        assert len(tasks) == 1
        assert tasks[0]["id"] == "task-123"

    def test_count_unconsolidated_reflections(self, manager, mock_memory):
        """Test counting unconsolidated reflections."""
        memory, mock_session = mock_memory

        mock_result = Mock()
        mock_result.single.return_value = {"count": 5}
        mock_session.run.return_value = mock_result

        count = manager.count_unconsolidated_reflections()

        assert count == 5

    def test_consolidate_reflections_threshold_not_met(self, manager, mock_memory):
        """Test consolidation when threshold not met."""
        memory, mock_session = mock_memory

        mock_result = Mock()
        mock_result.single.return_value = {"count": 3}  # Below threshold of 5
        mock_session.run.return_value = mock_result

        result = manager.consolidate_reflections()

        assert result["consolidated"] is False
        assert "threshold not met" in result["reason"].lower()

    def test_consolidate_reflections_success(self, manager, mock_memory):
        """Test successful reflection consolidation."""
        memory, mock_session = mock_memory

        # Mock count query
        count_result = Mock()
        count_result.single.return_value = {"count": 6}  # Above threshold

        # Mock reflections query - use dict instead of Mock
        reflection_node = {
            "id": "ref-1",
            "agent": "writer",
            "topic": "coding",
            "content": "Learned about Python patterns",
            "created_at": datetime.now(timezone.utc),
        }
        reflection_record = {"r": reflection_node}

        # Use list as iterable
        reflections_result = [reflection_record]

        # Mock learning creation
        learning_result = Mock()
        learning_result.single.return_value = {"learning_id": "learn-1"}

        # Mock the mark_reflections_consolidated (no return needed)
        mark_result = Mock()

        mock_session.run.side_effect = [
            count_result,
            reflections_result,
            learning_result,
            mark_result,
        ]

        result = manager.consolidate_reflections()

        assert result["consolidated"] is True

    def test_clean_orphaned_nodes(self, manager, mock_memory):
        """Test cleaning orphaned nodes."""
        memory, mock_session = mock_memory

        mock_result = Mock()
        mock_result.single.return_value = {"deleted": 3}
        mock_session.run.return_value = mock_result

        result = manager.clean_orphaned_nodes()

        assert "total_cleaned" in result
        assert result["orphaned_tasks"] == 3

    def test_run_synthesis_cycle(self, manager, mock_memory):
        """Test running a synthesis cycle."""
        memory, mock_session = mock_memory

        # Mock get_next_task to return a task - use dict instead of Mock
        mock_node = {
            "id": "task-123",
            "task_type": "graph_maintenance",
            "priority": "low",
            "status": "pending",
        }
        mock_record = {"t": mock_node}

        # Create mock results for each call
        get_task_result = Mock()
        get_task_result.single.return_value = mock_record

        start_task_result = Mock()
        start_task_result.single.return_value = {"task_id": "task-123"}

        clean_result = Mock()
        clean_result.single.side_effect = [
            {"deleted": 2},  # orphaned_tasks
            {"deleted": 1},  # orphaned_notifications
            {"deleted": 0},  # orphaned_reflections
            {"deleted": 0},  # orphaned_learnings
        ]

        complete_task_result = Mock()
        complete_task_result.single.return_value = {"task_id": "task-123"}

        mock_session.run.side_effect = [
            get_task_result,    # get_next_task
            start_task_result,  # start_task
            clean_result,       # clean_orphaned_nodes (4 queries)
            clean_result,
            clean_result,
            clean_result,
            complete_task_result,  # complete_task
        ]

        results = manager.run_synthesis_cycle()

        assert len(results) == 1
        assert results[0]["status"] == "completed"

    def test_check_and_queue_consolidation(self, manager, mock_memory):
        """Test checking and queuing consolidation."""
        memory, mock_session = mock_memory

        # Mock count query
        count_result = Mock()
        count_result.single.return_value = {"count": 6}  # Above threshold

        # Mock list_tasks (no pending consolidation)
        mock_result = Mock()
        mock_result.__iter__ = Mock(return_value=iter([]))

        # Mock queue task
        queue_result = Mock()
        queue_result.single.return_value = {"task_id": "consolidation-task"}

        mock_session.run.side_effect = [count_result, mock_result, queue_result]

        task_id = manager.check_and_queue_consolidation()

        assert task_id is not None

    def test_check_and_queue_consolidation_already_pending(self, manager, mock_memory):
        """Test consolidation not queued when already pending."""
        memory, mock_session = mock_memory

        # Mock count query
        count_result = Mock()
        count_result.single.return_value = {"count": 6}  # Above threshold

        # Mock list_tasks (has pending consolidation) - use dict
        mock_node = {
            "id": "pending-task",
            "task_type": "reflection_consolidation",
            "status": "pending",
        }
        mock_record = {"t": mock_node}

        # Use list as iterable
        mock_result = [mock_record]

        mock_session.run.side_effect = [count_result, mock_result]

        task_id = manager.check_and_queue_consolidation()

        assert task_id is None

    def test_create_indexes(self, manager, mock_memory):
        """Test creating indexes."""
        memory, mock_session = mock_memory

        mock_session.run.return_value = None

        created = manager.create_indexes()

        assert len(created) > 0
        assert "backgroundtask_id_idx" in created


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_create_background_task_manager(self):
        """Test factory function."""
        memory = Mock()
        manager = create_background_task_manager(
            memory=memory,
            reflection_threshold=3,
            idle_threshold_seconds=60
        )

        assert isinstance(manager, BackgroundTaskManager)
        assert manager.reflection_threshold == 3
        assert manager.idle_threshold_seconds == 60

    def test_run_background_synthesis_agent_busy(self):
        """Test run_background_synthesis when agent is not idle."""
        memory = Mock()
        manager = Mock()
        manager.is_agent_idle.return_value = False

        results = run_background_synthesis(manager, agent="test_agent")

        assert results == []
        manager.is_agent_idle.assert_called_once_with("test_agent")

    def test_run_background_synthesis_agent_idle(self):
        """Test run_background_synthesis when agent is idle."""
        memory = Mock()
        manager = Mock()
        manager.is_agent_idle.return_value = True
        manager.check_and_queue_consolidation.return_value = None
        manager.run_synthesis_cycle.return_value = [{"task_id": "task-1"}]

        results = run_background_synthesis(manager, agent="test_agent")

        assert len(results) == 1
        manager.check_and_queue_consolidation.assert_called_once()
        manager.run_synthesis_cycle.assert_called_once()


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_extract_themes(self):
        """Test theme extraction from reflections."""
        memory = Mock()
        manager = BackgroundTaskManager(memory)

        reflections = [
            {"content": "Learning about Python programming and async patterns"},
            {"content": "Understanding Neo4j graph databases and Cypher queries"},
        ]

        themes = manager._extract_themes(reflections)

        assert isinstance(themes, list)
        assert len(themes) <= 10  # Max 10 themes

    def test_extract_themes_empty_content(self):
        """Test theme extraction with empty content."""
        memory = Mock()
        manager = BackgroundTaskManager(memory)

        reflections = [
            {"content": ""},
            {"content": "a b c"},  # Words too short
        ]

        themes = manager._extract_themes(reflections)

        assert isinstance(themes, list)

    def test_mark_reflections_consolidated_fallback(self):
        """Test marking reflections consolidated in fallback mode."""
        memory = Mock()

        mock_context = MagicMock()
        mock_context.__enter__ = Mock(return_value=None)
        mock_context.__exit__ = Mock(return_value=False)
        memory._session.return_value = mock_context

        manager = BackgroundTaskManager(memory)

        # Should not raise in fallback mode
        manager._mark_reflections_consolidated(["ref-1", "ref-2"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
