"""
Tests for TopologicalExecutor

Tests cover:
- Getting ready tasks from dependency graph
- Executing ready sets with agent limits
- Agent selection based on deliverable type
- Current load tracking
- Execution cycle summary

Author: Claude (Anthropic)
Date: 2026-02-04
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from tools.kurultai.topological_executor import TopologicalExecutor
from tools.kurultai.types import Task, DeliverableType


@pytest.fixture
def mock_neo4j():
    """Create a mock Neo4j client."""
    mock = AsyncMock()
    mock._session = MagicMock()
    mock._session.__enter__ = MagicMock(return_value=None)
    neo4j._session.__exit__ = MagicMock(return_value=None)
    return mock


@pytest.mark.asyncio
async def test_get_ready_tasks():
    """Test retrieval of tasks with no unmet dependencies."""
    neo4j_mock = AsyncMock()
    neo4j_mock.get_ready_tasks = AsyncMock(return_value=[
        Task(
            id="1", type="", description="Task 1", status="pending",
            assigned_to=None, claimed_by=None, delegated_by=None,
            priority="normal", deliverable_type="research",
            sender_hash="user1", created_at=datetime.now(timezone.utc),
            updated_at=None, priority_weight=0.8, embedding=None,
            window_expires_at=None, user_priority_override=False,
            claimed_at=None, completed_at=None, results=None, error_message=None,
        )
    ])

    executor = TopologicalExecutor(neo4j_mock)
    ready = await executor.get_ready_tasks("user1")

    assert len(ready) == 1
    assert ready[0]["id"] == "1"


@pytest.mark.asyncio
async def test_select_best_agent():
    """Test agent selection based on deliverable type."""
    neo4j_mock = AsyncMock()
    executor = TopologicalExecutor(neo4j_mock)

    research_task = Task(
        id="1", type="", description="", status="pending",
        assigned_to=None, claimed_by=None, delegated_by=None,
        priority="normal", deliverable_type="research",
        sender_hash="", created_at=datetime.now(timezone.utc),
        updated_at=None, priority_weight=0.5, embedding=None,
        window_expires_at=None, user_priority_override=False,
        claimed_at=None, completed_at=None, results=None, error_message=None,
    )

    agent = executor._select_best_agent(research_task)
    assert agent == "researcher"


def test_get_agent_name():
    """Test getting human-readable agent name."""
    neo4j_mock = AsyncMock()
    executor = TopologicalExecutor(neo4j_mock)

    research_task = Task(
        id="1", type="", description="", status="pending",
        assigned_to=None, claimed_by=None, delegated_by=None,
        priority="normal", deliverable_type="research",
        sender_hash="", created_at=datetime.now(timezone.utc),
        updated_at=None, priority_weight=0.5, embedding=None,
        window_expires_at=None, user_priority_override=False,
        claimed_at=None, completed_at=None, results=None, error_message=None,
    )

    agent_name = executor.get_agent_name(research_task)
    assert agent_name == "Möngke"


@pytest.mark.asyncio
async def test_select_agent_for_all_deliverable_types():
    """Test agent routing for all deliverable types."""
    executor = TopologicalExecutor()

    routing_expectations = {
        "research": "researcher",
        "analysis": "analyst",
        "code": "developer",
        "content": "writer",
        "strategy": "analyst",
        "ops": "ops",
        "testing": "developer",
        "docs": "writer",
    }

    for dtype, expected_agent in routing_expectations.items():
        task = Task(
            id="1", type="", description="", status="pending",
            assigned_to=None, claimed_by=None, delegated_by=None,
            priority="normal", deliverable_type=dtype,
            sender_hash="", created_at=datetime.now(timezone.utc),
            updated_at=None, priority_weight=0.5, embedding=None,
            window_expires_at=None, user_priority_override=False,
            claimed_at=None, completed_at=None, results=None, error_message=None,
        )

        agent = executor._select_best_agent(task)
        assert agent == expected_agent, f"Expected {expected_agent} for {dtype}, got {agent}"


def test_max_tasks_per_agent():
    """Test agent task limit is correctly set."""
    assert TopologicalExecutor.MAX_TASKS_PER_AGENT == 2


@pytest.mark.asyncio
async def test_execute_ready_set():
    """Test executing ready set of tasks."""
    neo4j_mock = AsyncMock()
    neo4j_mock.get_ready_tasks = AsyncMock(return_value=[
        Task(
            id="1", type="", description="Task 1", status="pending",
            assigned_to=None, claimed_by=None, delegated_by=None,
            priority="normal", deliverable_type="research",
            sender_hash="user1", created_at=datetime.now(timezone.utc),
            updated_at=None, priority_weight=0.5, embedding=None,
            window_expires_at=None, user_priority_override=False,
            claimed_at=None, completed_at=None, results=None, error_message=None,
        )
    ])

    async def mock_get_current_load(agent_id):
        return 0  # No current load

    neo4j_mock._session = MagicMock()
    neo4j_mock._session.return_value.__aenter__ = AsyncMock(return_value=None)
    neo4j_mock._session.return_value.__aexit__ = AsyncMock(return_value=None)

    executor = TopologicalExecutor(neo4j_mock)
    executor._get_current_load = mock_get_current_load
    executor._dispatch_to_agent = AsyncMock(return_value=True)

    summary = await executor.execute_ready_set("user1")

    assert summary.executed_count == 1
    assert summary.error_count == 0
    assert "1" in summary.executed


@pytest.mark.asyncio
async def test_get_execution_summary():
    """Test getting execution status summary."""
    # Create a mock neo4j client that properly implements the session interface
    class MockAsyncResult:
        """Mock async result that can be iterated."""
        def __init__(self, records):
            self.records = records
            self.idx = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self.idx >= len(self.records):
                raise StopAsyncIteration
            record = self.records[self.idx]
            self.idx += 1
            return record

    class MockSession:
        """Mock session with synchronous context manager support."""
        def __init__(self, records):
            self.records = records

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def run(self, query, **kwargs):
            """Return an async result that yields records."""
            return MockAsyncResult(self.records)

    class MockNeo4j:
        """Mock Neo4j client with session that returns context manager."""
        def __init__(self, records):
            self.records = records

        def _session(self):
            return MockSession(self.records)

    records = [
        {"status": "pending", "count": 5},
        {"status": "completed", "count": 10},
        {"status": "in_progress", "count": 2},
    ]

    executor = TopologicalExecutor(MockNeo4j(records))
    summary = await executor.get_execution_summary("user1")

    assert summary["total"] == 17
    assert summary["pending"] == 5
    assert summary["completed"] == 10
    assert summary["in_progress"] == 2


def test_get_routing_info():
    """Test getting routing information."""
    executor = TopologicalExecutor()

    agent_id, agent_name = executor.get_routing_info("research")
    assert agent_id == "researcher"
    assert agent_name == "Möngke"

    agent_id, agent_name = executor.get_routing_info("unknown_type")
    # Should default to analyst for unknown types
    assert agent_id == "analyst"
    assert agent_name == "Jochi"


@pytest.mark.asyncio
async def test_run_execution_cycle():
    """Test running full execution cycle."""
    from tools.kurultai.types import ExecutionSummary

    call_count = [0]

    async def mock_execute(sender_hash, max_execution_limit=None):
        """Mock execute_ready_set with correct signature."""
        call_count[0] += 1
        if call_count[0] == 1:
            # First call has tasks
            return ExecutionSummary(
                executed_count=3,
                error_count=0,
                executed=["1", "2", "3"],
                errors=[]
            )
        else:
            # Subsequent calls have no tasks
            return ExecutionSummary(
                executed_count=0,
                error_count=0,
                executed=[],
                errors=[]
            )

    neo4j_mock = AsyncMock()
    executor = TopologicalExecutor(neo4j_mock)
    executor.execute_ready_set = mock_execute

    result = await executor.run_execution_cycle("user1", max_iterations=10)

    assert result["total_executed"] == 3
    assert result["total_errors"] == 0
    assert result["iterations"] == 2  # First call + empty check


@pytest.mark.asyncio
async def test_dispatch_to_agent():
    """Test dispatching task to agent."""
    neo4j_mock = AsyncMock()

    # Mock successful dispatch
    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_result = AsyncMock()
    mock_result.single = AsyncMock(return_value={"dispatch_id": "123"})
    mock_session.run = MagicMock(return_value=mock_result)
    neo4j_mock._session = MagicMock(return_value=mock_session)

    executor = TopologicalExecutor(neo4j_mock)

    task = Task(
        id="task-1", type="", description="Test task", status="pending",
        assigned_to=None, claimed_by=None, delegated_by=None,
        priority="normal", deliverable_type="research",
        sender_hash="", created_at=datetime.now(timezone.utc),
        updated_at=None, priority_weight=0.5, embedding=None,
        window_expires_at=None, user_priority_override=False,
        claimed_at=None, completed_at=None, results=None, error_message=None,
    )

    result = await executor._dispatch_to_agent(task, "researcher")

    assert result is True


@pytest.mark.asyncio
async def test_get_current_load():
    """Test getting current agent load."""
    # Create mock neo4j client that returns proper async result
    class MockResult:
        """Mock result with single() async method."""
        async def single(self):
            return {"load": 1}

    class MockSession:
        """Mock session with synchronous context manager support."""
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def run(self, query, **kwargs):
            return MockResult()

    class MockNeo4j:
        """Mock Neo4j client with session that returns context manager."""
        def _session(self):
            return MockSession()

    executor = TopologicalExecutor(MockNeo4j())

    load = await executor._get_current_load("researcher")

    assert load == 1
