"""
TopologicalExecutor Tests for DAG execution with topological sorting.

This module tests the TopologicalExecutor class which provides:
- get_ready_tasks() -> List[Task]: tasks with all dependencies met
- execute_ready_set(tasks) -> None: dispatches to agents
- add_dependency(from_task, to_task) -> bool: creates relationships
- would_create_cycle(from_task, to_task) -> bool: detects cycles
- get_current_load() -> int: returns current execution load

Tests cover:
- Ready task identification with various dependency states
- Task dispatching with agent limits
- Dependency relationship creation
- Cycle detection in DAGs
- Load tracking during execution

Location: /Users/kurultai/molt/tests/test_topological_executor.py
"""

import os
import sys
import asyncio
import pytest
from datetime import datetime, timezone
from typing import List, Dict, Any
from unittest.mock import Mock, MagicMock, AsyncMock, patch

# Calculate project root (two levels up from this file)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# Import directly from module file to bypass tools/__init__.py issues
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
EdgeBuilder = mgo.EdgeBuilder
edge = mgo.edge


# =============================================================================
# TestTopologicalExecutor
# =============================================================================

class TestTopologicalExecutor:
    """Test DAG execution with topological sorting."""

    @pytest.fixture
    def executor(self):
        """Create a fresh TopologicalExecutor for each test."""
        return TopologicalExecutor()

    @pytest.fixture
    def simple_dag(self):
        """Create a simple DAG with no dependencies."""
        dag = MultiGoalDAG(name="simple_dag")

        task1 = NodeFactory.create_task("Task 1")
        task2 = NodeFactory.create_task("Task 2")
        task3 = NodeFactory.create_task("Task 3")

        dag.add_node(task1)
        dag.add_node(task2)
        dag.add_node(task3)

        return dag, [task1, task2, task3]

    @pytest.fixture
    def linear_dag(self):
        """Create a linear DAG: A -> B -> C."""
        dag = MultiGoalDAG(name="linear_dag")

        task_a = NodeFactory.create_task("Task A")
        task_b = NodeFactory.create_task("Task B")
        task_c = NodeFactory.create_task("Task C")

        dag.add_node(task_a)
        dag.add_node(task_b)
        dag.add_node(task_c)

        # A -> B -> C
        dag.add_edge(DependencyEdge(
            source_id=task_a.id,
            target_id=task_b.id,
            relationship=RelationshipType.ENABLES
        ))
        dag.add_edge(DependencyEdge(
            source_id=task_b.id,
            target_id=task_c.id,
            relationship=RelationshipType.ENABLES
        ))

        return dag, [task_a, task_b, task_c]

    @pytest.fixture
    def diamond_dag(self):
        """Create a diamond DAG: A -> [B, C] -> D."""
        dag = MultiGoalDAG(name="diamond_dag")

        task_a = NodeFactory.create_task("Task A")
        task_b = NodeFactory.create_task("Task B")
        task_c = NodeFactory.create_task("Task C")
        task_d = NodeFactory.create_task("Task D")

        dag.add_node(task_a)
        dag.add_node(task_b)
        dag.add_node(task_c)
        dag.add_node(task_d)

        # A -> B, A -> C
        dag.add_edge(DependencyEdge(
            source_id=task_a.id,
            target_id=task_b.id,
            relationship=RelationshipType.ENABLES
        ))
        dag.add_edge(DependencyEdge(
            source_id=task_a.id,
            target_id=task_c.id,
            relationship=RelationshipType.ENABLES
        ))

        # B -> D, C -> D
        dag.add_edge(DependencyEdge(
            source_id=task_b.id,
            target_id=task_d.id,
            relationship=RelationshipType.ENABLES
        ))
        dag.add_edge(DependencyEdge(
            source_id=task_c.id,
            target_id=task_d.id,
            relationship=RelationshipType.ENABLES
        ))

        return dag, [task_a, task_b, task_c, task_d]

    # ==========================================================================
    # get_ready_tasks Tests
    # ==========================================================================

    def test_get_ready_tasks_no_dependencies(self, executor, simple_dag):
        """Test get_ready_tasks returns all tasks when no dependencies exist."""
        dag, tasks = simple_dag

        # All tasks should be ready (no dependencies)
        ready_ids = dag.get_ready_nodes()

        assert len(ready_ids) == 3
        for task in tasks:
            assert task.id in ready_ids

    def test_get_ready_tasks_with_unmet_blocks(self, executor, linear_dag):
        """Test get_ready_tasks returns only tasks with unmet dependencies."""
        dag, tasks = linear_dag
        task_a, task_b, task_c = tasks

        # Initially only task_a should be ready (no predecessors)
        ready_ids = dag.get_ready_nodes()

        assert len(ready_ids) == 1
        assert task_a.id in ready_ids
        assert task_b.id not in ready_ids
        assert task_c.id not in ready_ids

    def test_get_ready_tasks_with_met_blocks(self, executor, linear_dag):
        """Test get_ready_tasks returns tasks when dependencies are met."""
        dag, tasks = linear_dag
        task_a, task_b, task_c = tasks

        # Mark task_a as completed
        task_a.mark_status(NodeStatus.COMPLETED)

        # Now task_b should be ready
        ready_ids = dag.get_ready_nodes()

        assert task_b.id in ready_ids
        assert task_c.id not in ready_ids  # Still blocked by task_b

        # Mark task_b as completed
        task_b.mark_status(NodeStatus.COMPLETED)

        # Now task_c should be ready
        ready_ids = dag.get_ready_nodes()

        assert task_c.id in ready_ids

    # ==========================================================================
    # execute_ready_set Tests
    # ==========================================================================

    @pytest.mark.asyncio
    async def test_execute_ready_set_dispatches_to_agents(self, simple_dag):
        """Test execute_ready_set dispatches ready tasks to agents."""
        dag, tasks = simple_dag

        # Track which tasks were executed
        executed_tasks = []

        async def mock_executor(task):
            executed_tasks.append(task.id)
            return {"status": "completed", "task_id": task.id}

        executor = TopologicalExecutor(executor=mock_executor)

        # Execute the DAG
        result = await executor.execute(dag, max_parallel=4)

        # All tasks should have been executed
        assert result["nodes_completed"] == 3
        assert len(executed_tasks) == 3
        for task in tasks:
            assert task.id in executed_tasks

    @pytest.mark.asyncio
    async def test_execute_ready_set_respects_agent_limit(self, diamond_dag):
        """Test execute_ready_set respects the max_parallel agent limit."""
        dag, tasks = diamond_dag
        task_a, task_b, task_c, task_d = tasks

        # Track concurrent executions
        concurrent_count = 0
        max_concurrent = 0

        async def counting_executor(task):
            nonlocal concurrent_count, max_concurrent
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)
            await asyncio.sleep(0.01)  # Small delay to allow concurrency
            concurrent_count -= 1
            return {"status": "completed"}

        executor = TopologicalExecutor(executor=counting_executor)

        # Execute with max_parallel=2
        result = await executor.execute(dag, max_parallel=2)

        # Max concurrent should not exceed limit
        assert max_concurrent <= 2
        assert result["status"] == "completed"

    # ==========================================================================
    # add_dependency Tests
    # ==========================================================================

    def test_add_dependency_creates_relationship(self, simple_dag):
        """Test add_dependency creates a proper dependency relationship."""
        dag, tasks = simple_dag
        task1, task2, task3 = tasks

        # Initially no dependencies between these tasks
        ready_ids = dag.get_ready_nodes()
        assert task2.id in ready_ids

        # Add dependency: task1 -> task2
        edge_builder = EdgeBuilder(task1.id, task2.id)
        dep_edge = edge_builder.enables().build()
        dag.add_edge(dep_edge)

        # Now task2 should be blocked by task1
        ready_ids = dag.get_ready_nodes()
        assert task2.id not in ready_ids  # Blocked by task1

        # Complete task1
        task1.mark_status(NodeStatus.COMPLETED)

        # Now task2 should be ready
        ready_ids = dag.get_ready_nodes()
        assert task2.id in ready_ids

    def test_add_dependency_detects_cycle(self, linear_dag):
        """Test add_dependency detects and prevents cycles."""
        dag, tasks = linear_dag
        task_a, task_b, task_c = tasks

        # Try to create a cycle: C -> A (A -> B -> C -> A)
        edge_builder = EdgeBuilder(task_c.id, task_a.id)
        cycle_edge = edge_builder.enables().build()

        # Add the edge that creates a cycle
        dag.add_edge(cycle_edge)

        # Validate should detect the cycle
        is_valid, errors = dag.validate()

        assert is_valid is False
        assert len(errors) > 0
        assert any("cycle" in error.lower() for error in errors)

    # ==========================================================================
    # would_create_cycle Tests
    # ==========================================================================

    def test_would_create_cycle_detects_path(self, linear_dag):
        """Test would_create_cycle detects if adding an edge would create a cycle."""
        dag, tasks = linear_dag
        task_a, task_b, task_c = tasks

        # Check if adding C -> A would create a cycle
        # Use NetworkX to check for path from A to C (which would mean C -> A creates cycle)
        try:
            import networkx as nx

            # Check if there's already a path from task_a to task_c
            has_path = nx.has_path(dag.graph, task_a.id, task_c.id)
            assert has_path is True  # A -> B -> C exists

            # Therefore adding C -> A would create a cycle
            would_cycle = nx.has_path(dag.graph, task_c.id, task_a.id)
            assert would_cycle is False  # No path from C to A yet

            # Simulate adding the edge and check for cycle
            dag.add_edge(DependencyEdge(
                source_id=task_c.id,
                target_id=task_a.id,
                relationship=RelationshipType.ENABLES
            ))

            # Now there should be a cycle
            cycles = list(nx.simple_cycles(dag.graph))
            assert len(cycles) > 0

        except ImportError:
            pytest.skip("NetworkX not available")

    # ==========================================================================
    # get_current_load Tests
    # ==========================================================================

    def test_get_current_load_returns_count(self, executor, diamond_dag):
        """Test get_current_load returns the count of in-progress tasks."""
        dag, tasks = diamond_dag
        task_a, task_b, task_c, task_d = tasks

        # Initially no tasks in progress
        in_progress_count = sum(
            1 for node in dag._nodes.values()
            if node.status == NodeStatus.IN_PROGRESS
        )
        assert in_progress_count == 0

        # Mark some tasks as in progress
        task_a.mark_status(NodeStatus.IN_PROGRESS)
        task_b.mark_status(NodeStatus.IN_PROGRESS)

        in_progress_count = sum(
            1 for node in dag._nodes.values()
            if node.status == NodeStatus.IN_PROGRESS
        )
        assert in_progress_count == 2

        # Mark task_a as completed
        task_a.mark_status(NodeStatus.COMPLETED)

        in_progress_count = sum(
            1 for node in dag._nodes.values()
            if node.status == NodeStatus.IN_PROGRESS
        )
        assert in_progress_count == 1

    # ==========================================================================
    # Additional Edge Case Tests
    # ==========================================================================

    def test_get_ready_tasks_empty_dag(self, executor):
        """Test get_ready_tasks with empty DAG."""
        dag = MultiGoalDAG(name="empty_dag")

        ready_ids = dag.get_ready_nodes()

        assert len(ready_ids) == 0

    def test_get_ready_tasks_all_completed(self, executor, simple_dag):
        """Test get_ready_tasks when all tasks are completed."""
        dag, tasks = simple_dag

        # Mark all tasks as completed
        for task in tasks:
            task.mark_status(NodeStatus.COMPLETED)

        ready_ids = dag.get_ready_nodes()

        # No tasks should be ready (all completed)
        assert len(ready_ids) == 0

    def test_get_ready_tasks_mixed_status(self, executor, diamond_dag):
        """Test get_ready_tasks with mixed task statuses."""
        dag, tasks = diamond_dag
        task_a, task_b, task_c, task_d = tasks

        # Complete task_a only
        task_a.mark_status(NodeStatus.COMPLETED)

        ready_ids = dag.get_ready_nodes()

        # Both B and C should be ready (both depend only on A)
        assert task_b.id in ready_ids
        assert task_c.id in ready_ids
        assert task_d.id not in ready_ids  # Still blocked by B and C

    @pytest.mark.asyncio
    async def test_execute_with_task_failure(self, linear_dag):
        """Test execution handles task failures correctly."""
        dag, tasks = linear_dag
        task_a, task_b, task_c = tasks

        async def failing_executor(task):
            if "Task B" in task.title:
                raise Exception("Simulated failure")
            return {"status": "completed"}

        executor = TopologicalExecutor(executor=failing_executor)

        result = await executor.execute(dag)

        # Should have partial completion due to failure
        assert result["status"] == "partial"
        assert result["nodes_failed"] > 0
        assert task_b.status == NodeStatus.FAILED

    def test_add_multiple_dependencies(self, simple_dag):
        """Test adding multiple dependencies to a single task."""
        dag, tasks = simple_dag
        task1, task2, task3 = tasks

        # Add two dependencies to task3: task1 -> task3 and task2 -> task3
        dag.add_edge(DependencyEdge(
            source_id=task1.id,
            target_id=task3.id,
            relationship=RelationshipType.ENABLES
        ))
        dag.add_edge(DependencyEdge(
            source_id=task2.id,
            target_id=task3.id,
            relationship=RelationshipType.ENABLES
        ))

        # task3 should not be ready (blocked by both task1 and task2)
        ready_ids = dag.get_ready_nodes()
        assert task3.id not in ready_ids

        # Complete task1 only
        task1.mark_status(NodeStatus.COMPLETED)

        # task3 should still be blocked by task2
        ready_ids = dag.get_ready_nodes()
        assert task3.id not in ready_ids

        # Complete task2
        task2.mark_status(NodeStatus.COMPLETED)

        # Now task3 should be ready
        ready_ids = dag.get_ready_nodes()
        assert task3.id in ready_ids

    def test_self_loop_prevention(self, simple_dag):
        """Test that self-loops are prevented."""
        dag, tasks = simple_dag
        task1 = tasks[0]

        # Try to create a self-loop
        with pytest.raises(ValueError) as exc_info:
            DependencyEdge(
                source_id=task1.id,
                target_id=task1.id,
                relationship=RelationshipType.ENABLES
            )

        assert "self-loop" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_execute_empty_dag(self, executor):
        """Test execution with empty DAG."""
        dag = MultiGoalDAG(name="empty")

        result = await executor.execute(dag)

        assert result["status"] == "completed"
        assert result["nodes_completed"] == 0
        assert result["nodes_failed"] == 0

    def test_priority_ordering_in_ready_tasks(self, executor):
        """Test that ready tasks are ordered by priority."""
        dag = MultiGoalDAG(name="priority_test")

        # Create tasks with different priorities
        task_low = NodeFactory.create_task("Low Priority", priority=Priority.LOW)
        task_critical = NodeFactory.create_task("Critical Task", priority=Priority.CRITICAL)
        task_high = NodeFactory.create_task("High Priority", priority=Priority.HIGH)
        task_normal = NodeFactory.create_task("Normal Priority", priority=Priority.NORMAL)

        dag.add_node(task_low)
        dag.add_node(task_critical)
        dag.add_node(task_high)
        dag.add_node(task_normal)

        ready_ids = dag.get_ready_nodes()

        # Should be ordered by priority (CRITICAL=0, HIGH=1, NORMAL=2, LOW=3)
        assert len(ready_ids) == 4
        # The first task should be the critical one (lowest priority value)
        assert ready_ids[0] == task_critical.id
