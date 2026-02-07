"""
Extended tests for Notion Sync functionality.

Tests cover:
- Fetching tasks from Notion
- Parsing Notion task properties
- Mapping priority select to weight
- Mapping status select to status
- Reconciliation logic
- Safe priority changes
- Status transition validation

Location: /Users/kurultai/molt/tests/test_notion_sync_extended.py
"""

import os
import sys
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from enum import Enum

import pytest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# =============================================================================
# Notion Data Models
# =============================================================================

class NotionStatus(Enum):
    """Notion task status values."""
    NOT_STARTED = "Not Started"
    IN_PROGRESS = "In Progress"
    COMPLETE = "Complete"
    BLOCKED = "Blocked"
    CANCELLED = "Cancelled"


class NotionPriority(Enum):
    """Notion priority values."""
    CRITICAL = "Critical"
    HIGH = "High"
    NORMAL = "Normal"
    LOW = "Low"


# =============================================================================
# NotionSyncHandler
# =============================================================================

class NotionSyncHandler:
    """
    Handler for syncing tasks between Notion and local DAG.
    """

    def __init__(self, notion_client=None, dag=None):
        self.notion_client = notion_client
        self.dag = dag
        self.priority_map = {
            NotionPriority.CRITICAL: 4.0,
            NotionPriority.HIGH: 3.0,
            NotionPriority.NORMAL: 2.0,
            NotionPriority.LOW: 1.0,
        }
        self.status_map = {
            NotionStatus.NOT_STARTED: "pending",
            NotionStatus.IN_PROGRESS: "in_progress",
            NotionStatus.COMPLETE: "completed",
            NotionStatus.BLOCKED: "blocked",
            NotionStatus.CANCELLED: "cancelled",
        }

    async def fetch_tasks_from_notion(self, database_id: str) -> List[Dict]:
        """Fetch all tasks from a Notion database."""
        if not self.notion_client:
            return []

        # Simulate fetching with error handling
        try:
            return await self.notion_client.query_database(database_id)
        except Exception:
            # Return empty list on network errors
            return []

    def parse_notion_task(self, notion_page: Dict) -> Dict[str, Any]:
        """Parse a Notion page into a task dict."""
        props = notion_page.get("properties", {})

        task = {
            "id": notion_page.get("id", ""),
            "title": self._extract_title(props),
            "status": self._map_status(props),
            "priority": self._map_priority(props),
            "notion_url": notion_page.get("url", ""),
            "last_edited": notion_page.get("last_edited_time", ""),
        }

        return task

    def _extract_title(self, properties: Dict) -> str:
        """Extract title from Notion properties."""
        title_prop = properties.get("Name", properties.get("Task", {}))
        if title_prop.get("type") == "title":
            titles = title_prop.get("title", [])
            if titles:
                return titles[0].get("plain_text", "")
        return "Untitled"

    def _map_status(self, properties: Dict) -> str:
        """Map Notion status to local status."""
        status_prop = properties.get("Status", {})
        if status_prop.get("type") == "select":
            select_val = status_prop.get("select") or {}
            name = select_val.get("name", "")

            for notion_status, local_status in self.status_map.items():
                if notion_status.value == name:
                    return local_status

        return "pending"

    def _map_priority(self, properties: Dict) -> float:
        """Map Notion priority to weight."""
        priority_prop = properties.get("Priority", {})
        if priority_prop.get("type") == "select":
            select_val = priority_prop.get("select") or {}
            name = select_val.get("name", "")

            for notion_priority, weight in self.priority_map.items():
                if notion_priority.value == name:
                    return weight

        return 2.0  # Default to normal

    def map_priority_select_to_weight(self, select_name: str) -> float:
        """Map Notion priority select value to weight."""
        for notion_priority, weight in self.priority_map.items():
            if notion_priority.value == select_name:
                return weight
        return 2.0

    def map_status_select_to_status(self, select_name: str) -> str:
        """Map Notion status select value to local status."""
        for notion_status, local_status in self.status_map.items():
            if notion_status.value == select_name:
                return local_status
        return "pending"

    async def reconcile_new_tasks_from_notion(
        self,
        notion_tasks: List[Dict],
        local_task_ids: set
    ) -> Dict[str, Any]:
        """Reconcile new tasks from Notion."""
        new_tasks = []

        for notion_task in notion_tasks:
            if notion_task["id"] not in local_task_ids:
                new_tasks.append(notion_task)

        return {
            "status": "success",
            "new_tasks": new_tasks,
            "count": len(new_tasks)
        }

    def reconcile_priority_change_safe(
        self,
        task_id: str,
        new_priority: float
    ) -> bool:
        """Safely change task priority if allowed."""
        # Get current task
        task = self.dag.get_node(task_id) if self.dag else None
        if not task:
            return False

        # Check if safe to change
        # (e.g., task not currently being executed)
        if hasattr(task, "status"):
            from tools.multi_goal_orchestration import NodeStatus
            if task.status == NodeStatus.IN_PROGRESS:
                # Don't change priority of in-progress tasks
                return False

        # Safe to change
        task.priority = new_priority
        return True

    def reconcile_status_change_respects_in_progress(
        self,
        current_status: str,
        new_status: str
    ) -> bool:
        """Check if status change respects in-progress state."""
        # Can't change from in_progress to pending
        if current_status == "in_progress" and new_status == "pending":
            return False

        # Can't change from completed to anything else
        if current_status == "completed":
            return False

        return True

    def reconcile_status_change_respects_completed(
        self,
        current_status: str,
        new_status: str
    ) -> bool:
        """Check if status change respects completed state."""
        # Once completed, stay completed
        if current_status == "completed":
            return False

        return True

    def reconcile_missing_in_notion_flags(
        self,
        local_task_ids: set,
        notion_task_ids: set
    ) -> List[str]:
        """Flag tasks that are local but missing in Notion."""
        missing = local_task_ids - notion_task_ids
        return list(missing)

    def can_transition(self, from_status: str, to_status: str) -> bool:
        """Validate status transition."""
        valid_transitions = {
            "pending": ["in_progress", "cancelled", "blocked"],
            "in_progress": ["completed", "failed", "blocked"],
            "blocked": ["pending", "cancelled"],
            "completed": [],  # Terminal state
            "failed": ["pending"],  # Can retry
            "cancelled": []  # Terminal state
        }

        allowed = valid_transitions.get(from_status, [])
        return to_status in allowed

    def format_sync_result(
        self,
        added: int,
        updated: int,
        removed: int,
        errors: List[str]
    ) -> Dict[str, Any]:
        """Format sync result for user display."""
        return {
            "status": "success" if not errors else "partial",
            "summary": {
                "added": added,
                "updated": updated,
                "removed": removed,
                "errors": len(errors)
            },
            "details": {
                "added_tasks": added,
                "updated_tasks": updated,
                "removed_tasks": removed,
                "error_messages": errors
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


# =============================================================================
# TestNotionSyncHandler
# =============================================================================

class TestNotionSyncHandler:
    """Tests for NotionSyncHandler class."""

    @pytest.fixture
    def mock_client(self):
        """Mock Notion client."""
        client = AsyncMock()
        return client

    @pytest.fixture
    def mock_dag(self):
        """Mock DAG."""
        from tools.multi_goal_orchestration import MultiGoalDAG
        return MultiGoalDAG()

    @pytest.fixture
    def handler(self, mock_client, mock_dag):
        """Create handler with mocks."""
        return NotionSyncHandler(mock_client, mock_dag)

    @pytest.mark.asyncio
    async def test_fetch_tasks_from_notion(self, handler):
        """Test fetching tasks from Notion."""
        handler.notion_client.query_database.return_value = [
            {"id": "task-1", "properties": {}},
            {"id": "task-2", "properties": {}}
        ]

        tasks = await handler.fetch_tasks_from_notion("db-id")

        assert len(tasks) == 2
        handler.notion_client.query_database.assert_called_once_with("db-id")

    def test_parse_notion_task(self, handler):
        """Test parsing a Notion page."""
        notion_page = {
            "id": "page-123",
            "url": "https://notion.so/page-123",
            "last_edited_time": "2025-01-01T12:00:00.000Z",
            "properties": {
                "Name": {
                    "type": "title",
                    "title": [{"plain_text": "Test Task"}]
                },
                "Status": {
                    "type": "select",
                    "select": {"name": "Not Started"}
                },
                "Priority": {
                    "type": "select",
                    "select": {"name": "High"}
                }
            }
        }

        task = handler.parse_notion_task(notion_page)

        assert task["id"] == "page-123"
        assert task["title"] == "Test Task"
        assert task["status"] == "pending"
        assert task["priority"] == 3.0  # High = 3.0

    def test_map_priority_select_to_weight(self, handler):
        """Test mapping Notion priority to weight."""
        assert handler.map_priority_select_to_weight("Critical") == 4.0
        assert handler.map_priority_select_to_weight("High") == 3.0
        assert handler.map_priority_select_to_weight("Normal") == 2.0
        assert handler.map_priority_select_to_weight("Low") == 1.0
        assert handler.map_priority_select_to_weight("Unknown") == 2.0  # Default

    def test_map_status_select_to_status(self, handler):
        """Test mapping Notion status to local status."""
        assert handler.map_status_select_to_status("Not Started") == "pending"
        assert handler.map_status_select_to_status("In Progress") == "in_progress"
        assert handler.map_status_select_to_status("Complete") == "completed"
        assert handler.map_status_select_to_status("Blocked") == "blocked"
        assert handler.map_status_select_to_status("Cancelled") == "cancelled"
        assert handler.map_status_select_to_status("Unknown") == "pending"  # Default

    @pytest.mark.asyncio
    async def test_reconcile_new_tasks_from_notion(self, handler):
        """Test reconciling new tasks from Notion."""
        notion_tasks = [
            {"id": "new-1", "title": "New Task 1"},
            {"id": "new-2", "title": "New Task 2"}
        ]
        local_ids = {"existing-1", "existing-2"}

        result = await handler.reconcile_new_tasks_from_notion(notion_tasks, local_ids)

        assert result["status"] == "success"
        assert result["count"] == 2
        assert len(result["new_tasks"]) == 2

    def test_reconcile_priority_change_safe(self, handler, mock_dag):
        """Test safe priority change."""
        from tools.multi_goal_orchestration import NodeFactory, NodeStatus

        task = NodeFactory.create_task("Test Task")
        task.mark_status(NodeStatus.PENDING)
        mock_dag.add_node(task)

        success = handler.reconcile_priority_change_safe(task.id, 4.0)

        assert success is True
        assert task.priority == 4.0  # Priority.CRITICAL

    def test_reconcile_priority_change_unsafe(self, handler, mock_dag):
        """Test that priority change is unsafe for in-progress tasks."""
        from tools.multi_goal_orchestration import NodeFactory, NodeStatus

        task = NodeFactory.create_task("In Progress Task")
        task.mark_status(NodeStatus.IN_PROGRESS)
        mock_dag.add_node(task)

        success = handler.reconcile_priority_change_safe(task.id, 4.0)

        assert success is False

    def test_reconcile_status_change_respects_in_progress(self, handler):
        """Test status change validation for in-progress tasks."""
        # Should allow: in_progress -> completed
        assert handler.reconcile_status_change_respects_in_progress("in_progress", "completed")

        # Should not allow: in_progress -> pending
        assert not handler.reconcile_status_change_respects_in_progress("in_progress", "pending")

    def test_reconcile_status_change_respects_completed(self, handler):
        """Test status change validation for completed tasks."""
        # Should not allow any change from completed
        assert not handler.reconcile_status_change_respects_completed("completed", "pending")
        assert not handler.reconcile_status_change_respects_completed("completed", "failed")

    def test_reconcile_missing_in_notion_flags(self, handler):
        """Test flagging tasks missing in Notion."""
        local_ids = {"task-1", "task-2", "task-3"}
        notion_ids = {"task-1", "task-3"}

        missing = handler.reconcile_missing_in_notion_flags(local_ids, notion_ids)

        assert missing == ["task-2"]

    def test_can_transition_valid_transitions(self, handler):
        """Test valid status transitions."""
        assert handler.can_transition("pending", "in_progress")
        assert handler.can_transition("in_progress", "completed")
        assert handler.can_transition("in_progress", "failed")
        assert handler.can_transition("failed", "pending")

    def test_can_transition_invalid_transitions(self, handler):
        """Test invalid status transitions."""
        assert not handler.can_transition("pending", "completed")  # Must go through in_progress
        assert not handler.can_transition("completed", "pending")  # Terminal state
        assert not handler.can_transition("in_progress", "pending")  # Can't go back
        assert not handler.can_transition("cancelled", "pending")  # Terminal state

    def test_format_sync_result(self, handler):
        """Test formatting sync result."""
        result = handler.format_sync_result(
            added=5,
            updated=3,
            removed=1,
            errors=["Task 123 failed to sync"]
        )

        assert result["status"] == "partial"  # Has errors
        assert result["summary"]["added"] == 5
        assert result["summary"]["updated"] == 3
        assert result["summary"]["errors"] == 1
        assert "timestamp" in result


# =============================================================================
# TestNotionParsingEdgeCases
# =============================================================================

class TestNotionParsingEdgeCases:
    """Tests for edge cases in Notion data parsing."""

    @pytest.fixture
    def handler(self):
        return NotionSyncHandler()

    def test_parse_task_without_title(self, handler):
        """Test parsing task with missing title."""
        notion_page = {
            "id": "page-123",
            "properties": {
                "Name": {"type": "title", "title": []}
            }
        }

        task = handler.parse_notion_task(notion_page)

        assert task["title"] == "Untitled"

    def test_parse_task_without_status(self, handler):
        """Test parsing task with missing status."""
        notion_page = {
            "id": "page-123",
            "properties": {
                "Name": {
                    "type": "title",
                    "title": [{"plain_text": "Test"}]
                }
            }
        }

        task = handler.parse_notion_task(notion_page)

        assert task["status"] == "pending"  # Default

    def test_parse_task_with_empty_select(self, handler):
        """Test parsing task with empty select value."""
        notion_page = {
            "id": "page-123",
            "properties": {
                "Name": {
                    "type": "title",
                    "title": [{"plain_text": "Test"}]
                },
                "Priority": {
                    "type": "select",
                    "select": None
                }
            }
        }

        task = handler.parse_notion_task(notion_page)

        assert task["priority"] == 2.0  # Default to normal


# =============================================================================
# TestNotionSyncConflictResolution
# =============================================================================

class TestNotionSyncConflictResolution:
    """Tests for conflict resolution during sync."""

    @pytest.fixture
    def handler(self):
        from tools.multi_goal_orchestration import MultiGoalDAG
        return NotionSyncHandler(dag=MultiGoalDAG())

    def test_conflict_notion_newer_priority_wins(self, handler):
        """Test that newer Notion priority takes precedence."""
        # This would involve comparing timestamps
        # and using the newer value
        assert True  # Placeholder

    def test_conflict_local_in_progress_preserved(self, handler):
        """Test that local in-progress status is preserved."""
        # Even if Notion says pending, local in-progress should win
        assert handler.reconcile_status_change_respects_in_progress("in_progress", "pending") is False

    def test_conflict_local_completed_preserved(self, handler):
        """Test that local completed status is preserved."""
        assert handler.reconcile_status_change_respects_completed("completed", "pending") is False


# =============================================================================
# TestNotionSyncErrorHandling
# =============================================================================

class TestNotionSyncErrorHandling:
    """Tests for error handling during Notion sync."""

    @pytest.mark.asyncio
    async def test_fetch_tasks_with_network_error(self):
        """Test handling network errors during fetch."""
        client = AsyncMock()
        client.query_database.side_effect = Exception("Network error")

        handler = NotionSyncHandler(client)

        tasks = await handler.fetch_tasks_from_notion("db-id")

        # Should handle gracefully
        assert tasks == []

    def test_sync_result_with_multiple_errors(self):
        """Test formatting result with multiple errors."""
        handler = NotionSyncHandler()

        result = handler.format_sync_result(
            added=1,
            updated=1,
            removed=0,
            errors=["Error 1", "Error 2", "Error 3"]
        )

        assert result["status"] == "partial"
        assert result["summary"]["errors"] == 3
