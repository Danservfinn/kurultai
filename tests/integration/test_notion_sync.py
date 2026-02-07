#!/usr/bin/env python3
"""
Integration tests for Notion sync module.
Tests bidirectional sync, conflict resolution, soft-delete, and polling.
"""

import asyncio
import os
import re
import pytest
import warnings
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from tools.notion_sync import (
    NotionClient,
    ReconciliationEngine,
    NotionSyncHandler,
    NotionPollingEngine,
    NotionTask,
    TaskNode,
    TaskStatus,
    PriorityLevel,
    ChangeType,
    Change,
    SyncResult,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_notion_task():
    return NotionTask(
        id="task-001",
        description="Implement API endpoint",
        status=TaskStatus.PENDING,
        priority_weight=0.8,
        required_agents=["developer/Temujin"],
        notion_url="https://notion.so/task-001",
        notion_page_id="page-abc123",
        last_edited_time=datetime.now(timezone.utc),
        deliverable_type="code",
        estimated_duration=30,
        sender_hash="user-hash-001",
    )


@pytest.fixture
def sample_neo4j_task():
    return TaskNode(
        id="task-001",
        description="Implement API endpoint",
        status=TaskStatus.PENDING,
        priority_weight=0.8,
        required_agents=["developer/Temujin"],
        deliverable_type="code",
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def mock_driver():
    """Mock Neo4j async driver that won't leak connections."""
    driver = AsyncMock()
    session = AsyncMock()
    driver.session.return_value.__aenter__ = AsyncMock(return_value=session)
    driver.session.return_value.__aexit__ = AsyncMock(return_value=False)
    return driver


# =============================================================================
# ReconciliationEngine Tests
# =============================================================================

class TestReconciliationEngine:
    """Test conflict resolution logic."""

    @pytest.mark.asyncio
    async def test_new_task_from_notion(self, mock_driver, sample_notion_task):
        """Tasks in Notion but not Neo4j should be created."""
        engine = ReconciliationEngine(mock_driver)
        changes = await engine.reconcile(
            notion_tasks=[sample_notion_task],
            neo4j_tasks=[],
        )
        assert len(changes) == 1
        assert changes[0].type == ChangeType.CREATE
        assert changes[0].task_id == "task-001"

    @pytest.mark.asyncio
    async def test_in_progress_task_not_modified(
        self, mock_driver, sample_notion_task, sample_neo4j_task
    ):
        """In-progress Neo4j tasks should never be modified by Notion."""
        sample_neo4j_task.status = TaskStatus.IN_PROGRESS
        sample_notion_task.status = TaskStatus.PENDING

        engine = ReconciliationEngine(mock_driver)
        changes = await engine.reconcile(
            notion_tasks=[sample_notion_task],
            neo4j_tasks=[sample_neo4j_task],
        )
        # No changes should be generated for in-progress tasks
        assert len(changes) == 0

    @pytest.mark.asyncio
    async def test_completed_task_not_reverted(
        self, mock_driver, sample_notion_task, sample_neo4j_task
    ):
        """Completed Neo4j tasks should never be reverted by Notion."""
        sample_neo4j_task.status = TaskStatus.COMPLETED
        sample_notion_task.status = TaskStatus.PENDING

        engine = ReconciliationEngine(mock_driver)
        changes = await engine.reconcile(
            notion_tasks=[sample_notion_task],
            neo4j_tasks=[sample_neo4j_task],
        )
        # Completed tasks should not generate any changes
        assert len(changes) == 0

    @pytest.mark.asyncio
    async def test_priority_change_always_applies(
        self, mock_driver, sample_notion_task, sample_neo4j_task
    ):
        """Priority changes from Notion should apply when task is not in-progress/completed."""
        sample_neo4j_task.status = TaskStatus.PENDING
        sample_notion_task.priority_weight = 1.0  # Changed from 0.8

        engine = ReconciliationEngine(mock_driver)
        changes = await engine.reconcile(
            notion_tasks=[sample_notion_task],
            neo4j_tasks=[sample_neo4j_task],
        )
        priority_changes = [c for c in changes if c.type == ChangeType.PRIORITY]
        assert len(priority_changes) == 1
        assert priority_changes[0].new_value == 1.0

    @pytest.mark.asyncio
    async def test_neo4j_source_of_truth_blocked(
        self, mock_driver, sample_notion_task, sample_neo4j_task
    ):
        """BLOCKED→READY is not a safe transition, so no status change generated."""
        sample_neo4j_task.status = TaskStatus.BLOCKED
        sample_notion_task.status = TaskStatus.READY

        engine = ReconciliationEngine(mock_driver)
        changes = await engine.reconcile(
            notion_tasks=[sample_notion_task],
            neo4j_tasks=[sample_neo4j_task],
        )
        # BLOCKED→READY is not in SAFE_TRANSITIONS, so no status change
        status_changes = [c for c in changes if c.type == ChangeType.STATUS]
        assert len(status_changes) == 0


# =============================================================================
# NotionPollingEngine Tests
# =============================================================================

class TestNotionPollingEngine:
    """Test polling engine lifecycle and configuration."""

    def test_poll_interval_from_env(self):
        """NOTION_POLL_INTERVAL env var should configure polling interval."""
        with patch.dict(os.environ, {"NOTION_POLL_INTERVAL": "120"}):
            with patch("tools.notion_sync.AsyncGraphDatabase") as mock_gdb:
                mock_gdb.driver.return_value = AsyncMock()
                engine = NotionPollingEngine(
                    neo4j_uri="bolt://localhost:7687",
                    neo4j_user="neo4j",
                    neo4j_password="test",
                )
                assert engine.poll_interval == 120

    def test_poll_interval_default(self):
        """Default poll interval should be 60 seconds."""
        env = {k: v for k, v in os.environ.items() if k != "NOTION_POLL_INTERVAL"}
        with patch.dict(os.environ, env, clear=True):
            with patch("tools.notion_sync.AsyncGraphDatabase") as mock_gdb:
                mock_gdb.driver.return_value = AsyncMock()
                engine = NotionPollingEngine(
                    neo4j_uri="bolt://localhost:7687",
                    neo4j_user="neo4j",
                    neo4j_password="test",
                )
                assert engine.poll_interval == 60

    def test_poll_interval_constructor_overrides_env(self):
        """Constructor parameter should override env var."""
        with patch.dict(os.environ, {"NOTION_POLL_INTERVAL": "120"}):
            with patch("tools.notion_sync.AsyncGraphDatabase") as mock_gdb:
                mock_gdb.driver.return_value = AsyncMock()
                engine = NotionPollingEngine(
                    neo4j_uri="bolt://localhost:7687",
                    neo4j_user="neo4j",
                    neo4j_password="test",
                    poll_interval_seconds=30,
                )
                assert engine.poll_interval == 30


# =============================================================================
# NotionSyncHandler Tests
# =============================================================================

class TestNotionSyncHandler:
    """Test command-based sync handling."""

    def test_detects_sync_commands(self):
        """Should detect various sync command patterns."""
        sync_patterns = [
            r"sync\s+(?:from\s+)?notion",
            r"notion\s+sync",
            r"pull\s+(?:from\s+)?notion",
            r"update\s+(?:from\s+)?notion",
            r"refresh\s+(?:from\s+)?notion",
        ]
        test_cases = [
            ("sync from notion", True),
            ("notion sync", True),
            ("pull from notion", True),
            ("hello world", False),
            ("update from notion", True),
            ("refresh notion", True),  # "from" is optional in pattern
            ("refresh from notion", True),
        ]
        for msg, expected in test_cases:
            matched = any(re.search(p, msg, re.IGNORECASE) for p in sync_patterns)
            assert matched == expected, f"Failed for message: {msg}"


# =============================================================================
# Soft-Delete Tests
# =============================================================================

class TestSoftDelete:
    """Test that Notion deletions result in soft-delete (archived) in Neo4j."""

    @pytest.mark.asyncio
    async def test_missing_notion_task_flagged(self, mock_driver, sample_neo4j_task):
        """Tasks in Neo4j but not Notion should be flagged as MISSING_IN_NOTION."""
        engine = ReconciliationEngine(mock_driver)
        changes = await engine.reconcile(
            notion_tasks=[],
            neo4j_tasks=[sample_neo4j_task],
        )
        missing_changes = [
            c for c in changes if c.type == ChangeType.MISSING_IN_NOTION
        ]
        assert len(missing_changes) == 1
        assert missing_changes[0].task_id == "task-001"
        assert missing_changes[0].safe is False


# =============================================================================
# Data Model Tests
# =============================================================================

class TestDataModels:
    """Test data model correctness."""

    def test_sync_result_total_changes(self):
        """SyncResult should correctly count total changes."""
        result = SyncResult(
            success=True,
            created=[Change(type=ChangeType.CREATE, task_id="t1")],
            updated=[
                Change(type=ChangeType.PRIORITY, task_id="t2"),
                Change(type=ChangeType.STATUS, task_id="t3"),
            ],
        )
        assert result.total_changes() == 3

    def test_priority_levels_ordered(self):
        """Priority levels should have correct numeric ordering."""
        assert PriorityLevel.CRITICAL.value > PriorityLevel.HIGH.value
        assert PriorityLevel.HIGH.value > PriorityLevel.MEDIUM.value
        assert PriorityLevel.MEDIUM.value > PriorityLevel.LOW.value
        assert PriorityLevel.LOW.value > PriorityLevel.BACKLOG.value


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
