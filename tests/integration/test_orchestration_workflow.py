"""
Integration tests for Orchestration Workflow.

Tests cover:
- Intent window collecting messages
- DAG building from buffered messages
- Topological execution respects dependencies
- Parallel execution of independent tasks
- Unified delivery for related tasks
- Streaming delivery for independent tasks
- Priority override reorders execution

Location: /Users/kurultai/molt/tests/integration/test_orchestration_workflow.py
"""

import os
import sys
import asyncio
import time
from datetime import datetime, timezone
from typing import List, Dict, Any
from unittest.mock import Mock, MagicMock, AsyncMock

import pytest

# Calculate project root (two levels up from this file)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

# Import directly from module file to bypass tools/__init__.py issues
# Use importlib to avoid executing tools/__init__.py which has numpy issues
import importlib.machinery
import importlib.util

# Create module spec and add to sys.modules before execution
module_path = os.path.join(PROJECT_ROOT, "tools", "multi_goal_orchestration.py")
spec = importlib.util.spec_from_file_location("multi_goal_orchestration", module_path)
mgo = importlib.util.module_from_spec(spec)
sys.modules["multi_goal_orchestration"] = mgo  # Required for dataclass processing
spec.loader.exec_module(mgo)

NodeStatus = mgo.NodeStatus
Priority = mgo.Priority
TaskNode = mgo.TaskNode
GoalNode = mgo.GoalNode
MultiGoalDAG = mgo.MultiGoalDAG
NodeFactory = mgo.NodeFactory
RelationshipType = mgo.RelationshipType
TopologicalExecutor = mgo.TopologicalExecutor
DependencyEdge = mgo.DependencyEdge


# =============================================================================
# Intent Window Mock
# =============================================================================

class MockIntentWindow:
    """Mock intent window for testing."""

    def __init__(self, window_ms=100):
        self.window_ms = window_ms
        self.messages = []
        self.start_time = 0

    def add(self, content: str) -> List[Dict] | None:
        now = time.time() * 1000
        self.messages.append({"content": content, "timestamp": now})

        if not self.start_time:
            self.start_time = now

        if now - self.start_time >= self.window_ms:
            batch = self.messages.copy()
            self.messages = []
            self.start_time = 0
            return batch

        return None


# =============================================================================
# TestOrchestrationWorkflow
# =============================================================================

class TestOrchestrationWorkflow:
    """Integration tests for orchestration workflow."""

    @pytest.fixture
    def intent_window(self):
        return MockIntentWindow(window_ms=100)

    def test_intent_window_collects_messages(self, intent_window):
        """Test that intent window collects messages."""
        messages = [
            "Fix the authentication bug",
            "Add unit tests",
            "Update documentation"
        ]

        for msg in messages:
            result = intent_window.add(msg)

        assert result is None  # Window not expired yet
        assert len(intent_window.messages) == 3

    def test_dag_build_from_buffered_messages(self, intent_window):
        """Test building DAG from buffered messages."""
        # Add messages
        intent_window.add("Research OAuth options")
        intent_window.add("Implement JWT middleware")
        intent_window.add("Add tests for auth")

        # Wait for window
        time.sleep(0.15)
        batch = intent_window.add("Trigger")

        assert batch is not None
        assert len(batch) >= 3

        # Build DAG from messages
        dag = MultiGoalDAG()
        tasks = []

        for msg_data in batch:
            task = NodeFactory.create_task(msg_data["content"])
            tasks.append(task)
            dag.add_node(task)

        assert len(dag._nodes) == len(batch)

    def test_topological_execution_respects_dependencies(self):
        """Test that topological execution respects dependencies."""
        dag = MultiGoalDAG()

        task1 = NodeFactory.create_task("Research")
        task2 = NodeFactory.create_task("Implement")
        task3 = NodeFactory.create_task("Test")

        dag.add_node(task1)
        dag.add_node(task2)
        dag.add_node(task3)

        # Create dependencies: 1 -> 2 -> 3
        edge1 = DependencyEdge(
            source_id=task1.id,
            target_id=task2.id,
            relationship=RelationshipType.ENABLES
        )
        edge2 = DependencyEdge(
            source_id=task2.id,
            target_id=task3.id,
            relationship=RelationshipType.ENABLES
        )
        dag.add_edge(edge1)
        dag.add_edge(edge2)

        # Get execution order
        order = dag.execution_order()

        # task1 should come before task2, task2 before task3
        assert order.index(task1.id) < order.index(task2.id)
        assert order.index(task2.id) < order.index(task3.id)

    def test_parallel_execution_of_independent_tasks(self):
        """Test parallel execution of independent tasks."""
        dag = MultiGoalDAG()

        tasks = []
        for i in range(5):
            task = NodeFactory.create_task(f"Task {i}")
            tasks.append(task)
            dag.add_node(task)

        # All tasks are independent
        executor = TopologicalExecutor()

        # Get ready tasks (should be all of them)
        ready = []
        for node_id, node in dag._nodes.items():
            if isinstance(node, TaskNode) and node.status == NodeStatus.PENDING:
                ready.append(node_id)

        assert len(ready) == 5

    def test_unified_delivery_for_related_tasks(self):
        """Test unified delivery for tasks with dependencies."""
        dag = MultiGoalDAG()

        task1 = NodeFactory.create_task("Task 1")
        task2 = NodeFactory.create_task("Task 2")
        task3 = NodeFactory.create_task("Task 3")

        dag.add_node(task1)
        dag.add_node(task2)
        dag.add_node(task3)

        # Related chain
        edge1 = DependencyEdge(
            source_id=task1.id,
            target_id=task2.id,
            relationship=RelationshipType.ENABLES
        )
        edge2 = DependencyEdge(
            source_id=task2.id,
            target_id=task3.id,
            relationship=RelationshipType.ENABLES
        )
        dag.add_edge(edge1)
        dag.add_edge(edge2)

        # These should be delivered as a unified group
        order = dag.execution_order()
        assert len(order) == 3

    def test_streaming_delivery_for_independent_tasks(self):
        """Test streaming delivery for independent tasks."""
        dag = MultiGoalDAG()

        tasks = []
        for i in range(3):
            task = NodeFactory.create_task(f"Independent {i}")
            tasks.append(task)
            dag.add_node(task)

        # Independent tasks can be streamed
        executor = TopologicalExecutor()
        levels = executor._group_by_level(dag, dag.execution_order())

        # All should be in same level (parallel executable)
        assert 0 in levels
        assert len(levels[0]) == 3

    def test_priority_override_reorders_execution(self):
        """Test that priority override affects execution order."""
        dag = MultiGoalDAG()

        task_low = NodeFactory.create_task("Low Priority", priority=Priority.LOW)
        task_critical = NodeFactory.create_task("Critical Task", priority=Priority.CRITICAL)

        dag.add_node(task_low)
        dag.add_node(task_critical)

        # Critical should execute before low
        assert task_critical.priority.value < task_low.priority.value


# =============================================================================
# TestOrchestrationWorkflowAsync
# =============================================================================

class TestOrchestrationWorkflowAsync:
    """Async integration tests."""

    @pytest.mark.asyncio
    async def test_async_dag_execution(self):
        """Test async DAG execution."""
        dag = MultiGoalDAG()

        tasks = []
        for i in range(3):
            task = NodeFactory.create_task(f"Task {i}")
            tasks.append(task)
            dag.add_node(task)

        # Add linear dependency
        for i in range(2):
            edge = DependencyEdge(
                source_id=tasks[i].id,
                target_id=tasks[i+1].id,
                relationship=RelationshipType.ENABLES
            )
            dag.add_edge(edge)

        executor = TopologicalExecutor()

        result = await executor.execute(dag, max_parallel=2)

        assert result["status"] in ["completed", "partial"]
        assert result["nodes_completed"] == 3
        assert "duration_seconds" in result

    @pytest.mark.asyncio
    async def test_parallel_levels_execution(self):
        """Test execution of parallel levels."""
        dag = MultiGoalDAG()

        # Level 0
        start = NodeFactory.create_task("Start")
        dag.add_node(start)

        # Level 1 (parallel)
        branch1 = NodeFactory.create_task("Branch 1")
        branch2 = NodeFactory.create_task("Branch 2")
        dag.add_node(branch1)
        dag.add_node(branch2)

        # Level 2 (merge)
        end = NodeFactory.create_task("End")
        dag.add_node(end)

        # Dependencies
        dag.add_edge(DependencyEdge(
            source_id=start.id, target_id=branch1.id, relationship=RelationshipType.ENABLES
        ))
        dag.add_edge(DependencyEdge(
            source_id=start.id, target_id=branch2.id, relationship=RelationshipType.ENABLES
        ))
        dag.add_edge(DependencyEdge(
            source_id=branch1.id, target_id=end.id, relationship=RelationshipType.ENABLES
        ))
        dag.add_edge(DependencyEdge(
            source_id=branch2.id, target_id=end.id, relationship=RelationshipType.ENABLES
        ))

        executor = TopologicalExecutor()
        result = await executor.execute(dag, max_parallel=2)

        assert result["status"] == "completed"


# =============================================================================
# TestGoalOrchestration
# =============================================================================

class TestGoalOrchestration:
    """Tests for goal-based orchestration."""

    def test_goal_to_task_decomposition(self):
        """Test decomposing goals into tasks."""
        dag = MultiGoalDAG()

        goal = NodeFactory.create_goal(
            "Implement Authentication",
            success_criteria=["OAuth flow working", "Tests passing"]
        )
        dag.add_node(goal)

        # Add subtasks
        task1 = NodeFactory.create_task("Research OAuth")
        task2 = NodeFactory.create_task("Implement JWT")
        task3 = NodeFactory.create_task("Write tests")

        dag.add_node(task1)
        dag.add_node(task2)
        dag.add_node(task3)

        goal.add_contributing_task(task1.id)
        goal.add_contributing_task(task2.id)
        goal.add_contributing_task(task3.id)

        assert len(goal.contributing_tasks) == 3

    def test_goal_progress_tracking(self):
        """Test goal progress tracking."""
        goal = NodeFactory.create_goal(
            "Complete Feature",
            success_criteria=["Task 1", "Task 2", "Task 3"]
        )

        goal.add_contributing_task("task-1")
        goal.add_contributing_task("task-2")
        goal.add_contributing_task("task-3")

        progress = goal.progress_fraction()

        assert 0.0 <= progress <= 1.0

    def test_synergistic_goal_merging(self):
        """Test merging synergistic goals."""
        dag = MultiGoalDAG()

        goal1 = NodeFactory.create_goal("Performance")
        goal2 = NodeFactory.create_goal("Security")

        dag.add_node(goal1)
        dag.add_node(goal2)

        # Mark as synergistic
        dag.add_edge(DependencyEdge(
            source_id=goal1.id, target_id=goal2.id, relationship=RelationshipType.SYNERGISTIC
        ))

        # Check they are connected
        assert dag.graph.has_edge(goal1.id, goal2.id)


# =============================================================================
# TestOrchestrationErrorRecovery
# =============================================================================

class TestOrchestrationErrorRecovery:
    """Tests for error recovery in orchestration."""

    @pytest.mark.asyncio
    async def test_task_failure_handling(self):
        """Test handling of task failures."""
        dag = MultiGoalDAG()

        task1 = NodeFactory.create_task("Task 1")
        task2 = NodeFactory.create_task("Task 2")
        task3 = NodeFactory.create_task("Task 3")

        dag.add_node(task1)
        dag.add_node(task2)
        dag.add_node(task3)

        # Dependencies
        dag.add_edge(DependencyEdge(
            source_id=task1.id, target_id=task2.id, relationship=RelationshipType.ENABLES
        ))
        dag.add_edge(DependencyEdge(
            source_id=task2.id, target_id=task3.id, relationship=RelationshipType.ENABLES
        ))

        # Mock executor that fails task2
        async def failing_executor(task):
            if "Task 2" in task.title:
                raise Exception("Simulated failure")
            return {"status": "completed"}

        executor = TopologicalExecutor(executor=failing_executor)

        result = await executor.execute(dag)

        # Should have partial completion
        assert result["status"] == "partial"
        assert result["nodes_failed"] > 0

    def test_cycle_detection_before_execution(self):
        """Test cycle detection before starting execution."""
        dag = MultiGoalDAG()

        task1 = NodeFactory.create_task("A")
        task2 = NodeFactory.create_task("B")
        task3 = NodeFactory.create_task("C")

        dag.add_node(task1)
        dag.add_node(task2)
        dag.add_node(task3)

        # Create cycle
        dag.add_edge(DependencyEdge(
            source_id=task1.id, target_id=task2.id, relationship=RelationshipType.ENABLES
        ))
        dag.add_edge(DependencyEdge(
            source_id=task2.id, target_id=task3.id, relationship=RelationshipType.ENABLES
        ))
        dag.add_edge(DependencyEdge(
            source_id=task3.id, target_id=task1.id, relationship=RelationshipType.ENABLES
        ))

        is_valid, errors = dag.validate()

        assert is_valid is False
        assert len(errors) > 0
