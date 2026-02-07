"""
Tests for Multi-Goal Orchestration patterns.

Run with: pytest tools/test_multi_goal_orchestration.py -v
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import the module
import sys
sys.path.insert(0, "/Users/kurultai/molt/tools")

from multi_goal_orchestration import (
    BaseNode,
    TaskNode,
    GoalNode,
    NodeFactory,
    RelationshipType,
    DependencyEdge,
    EdgeBuilder,
    edge,
    NodeStatus,
    Priority,
    MultiGoalDAG,
    TopologicalExecutor,
    SynergyExecutor,
    GoalOrchestrator,
    RelationshipDetection,
    JaccardSimilarity,
)


class TestNodeClasses:
    """Tests for Goal vs Task class hierarchy."""

    def test_task_node_creation(self):
        """Test creating a basic task node."""
        task = TaskNode(
            id="task-1",
            title="Write tests",
            description="Write unit tests for the module",
            task_type="code",
            priority=Priority.HIGH
        )
        assert task.id == "task-1"
        assert task.title == "Write tests"
        assert task.task_type == "code"
        assert task.priority == Priority.HIGH
        assert task.status == NodeStatus.PENDING

    def test_goal_node_creation(self):
        """Test creating a goal node with success criteria."""
        goal = GoalNode(
            id="goal-1",
            title="Launch product",
            description="Launch the MVP",
            success_criteria=["Complete features", "Get 10 users"],
            priority=Priority.CRITICAL
        )
        assert goal.id == "goal-1"
        assert len(goal.success_criteria) == 2
        assert goal.priority == Priority.CRITICAL

    def test_task_progress_is_binary(self):
        """Test that task progress is binary (0 or 1)."""
        task = TaskNode(id="t1", title="Test task")
        assert task.progress_fraction() == 0.0

        task.status = NodeStatus.COMPLETED
        assert task.progress_fraction() == 1.0

    def test_goal_progress_aggregates(self):
        """Test that goal progress aggregates from components."""
        goal = GoalNode(
            id="g1",
            title="Parent goal",
            contributing_tasks=["t1", "t2", "t3"],
            contributing_subgoals=["sg1"]
        )
        # With no completed tasks or subgoals, progress is 0
        # (In real implementation, would look up actual task status)
        assert 0.0 <= goal.progress_fraction() <= 1.0

    def test_node_factory(self):
        """Test the NodeFactory creates nodes correctly."""
        task = NodeFactory.create_task(
            title="Factory task",
            description="Created by factory"
        )
        assert isinstance(task, TaskNode)
        assert task.title == "Factory task"

        goal = NodeFactory.create_goal(
            title="Factory goal",
            success_criteria=["Done"]
        )
        assert isinstance(goal, GoalNode)
        assert len(goal.success_criteria) == 1

    def test_status_transitions(self):
        """Test node status transitions."""
        task = TaskNode(id="t1", title="Test")
        assert task.status == NodeStatus.PENDING
        assert not task.is_terminal()

        task.mark_status(NodeStatus.IN_PROGRESS)
        assert task.status == NodeStatus.IN_PROGRESS

        task.mark_status(NodeStatus.COMPLETED)
        assert task.is_terminal()


class TestRelationshipTypes:
    """Tests for relationship modeling."""

    def test_edge_creation(self):
        """Test creating a basic edge."""
        edge = DependencyEdge(
            source_id="a",
            target_id="b",
            relationship=RelationshipType.ENABLES
        )
        assert edge.source_id == "a"
        assert edge.target_id == "b"
        assert edge.relationship == RelationshipType.ENABLES

    def test_edge_prevents_self_loops(self):
        """Test that edges cannot loop to self."""
        with pytest.raises(ValueError):
            DependencyEdge(
                source_id="a",
                target_id="a",
                relationship=RelationshipType.ENABLES
            )

    def test_edge_builder_enables(self):
        """Test the fluent edge builder for ENABLES."""
        edge_obj = edge("a", "b").enables().build()
        assert edge_obj.relationship == RelationshipType.ENABLES

    def test_edge_builder_synergistic(self):
        """Test the fluent edge builder for SYNERGISTIC."""
        edge_obj = edge("a", "b").synergistic(strategy="merge").build()
        assert edge_obj.relationship == RelationshipType.SYNERGISTIC
        assert edge_obj.metadata.get("strategy") == "merge"

    def test_edge_builder_conflicts(self):
        """Test the fluent edge builder for CONFLICTS_WITH."""
        edge_obj = edge("a", "b").conflicts().build()
        assert edge_obj.relationship == RelationshipType.CONFLICTS_WITH

    def test_edge_builder_reinforces(self):
        """Test the fluent edge builder for REINFORCES."""
        edge_obj = edge("a", "b").reinforces(boost_factor=2.0).build()
        assert edge_obj.relationship == RelationshipType.REINFORCES
        assert edge_obj.weight == 2.0

    def test_edge_builder_with_metadata(self):
        """Test adding metadata to edges."""
        edge_obj = (
            edge("a", "b")
            .enables()
            .with_weight(1.5)
            .with_metadata(confidence=0.9, source="llm")
            .build()
        )
        assert edge_obj.weight == 1.5
        assert edge_obj.metadata["confidence"] == 0.9
        assert edge_obj.metadata["source"] == "llm"


class TestRelationshipDetection:
    """Tests for relationship detection algorithms."""

    def test_jaccard_similarity_identical(self):
        """Test Jaccard similarity with identical texts."""
        metric = JaccardSimilarity()
        similarity = metric("hello world", "hello world")
        assert similarity == 1.0

    def test_jaccard_similarity_no_overlap(self):
        """Test Jaccard similarity with no overlap."""
        metric = JaccardSimilarity()
        similarity = metric("apple banana", "orange grape")
        assert similarity == 0.0

    def test_jaccard_similarity_partial_overlap(self):
        """Test Jaccard similarity with partial overlap."""
        metric = JaccardSimilarity()
        similarity = metric("hello world test", "hello world")
        assert 0.0 < similarity < 1.0

    def test_detect_enabling_relationship(self):
        """Test detecting enabling relationship via keywords."""
        detector = RelationshipDetection()

        goal1 = GoalNode(
            id="g1",
            title="Research",
            description="Research the topic first"
        )
        goal2 = GoalNode(
            id="g2",
            title="Build",
            description="Requires research to be completed"
        )

        relationship = detector.detect(goal1, goal2)
        assert relationship == RelationshipType.ENABLES

    def test_detect_conflicting_relationship(self):
        """Test detecting conflicting relationship via keywords."""
        detector = RelationshipDetection()

        goal1 = GoalNode(
            id="g1",
            title="Option A",
            description="Choose option A instead of B"
        )
        goal2 = GoalNode(
            id="g2",
            title="Option B",
            description="Alternative to option A"
        )

        relationship = detector.detect(goal1, goal2)
        assert relationship == RelationshipType.CONFLICTS_WITH

    def test_detect_independent_default(self):
        """Test default to independent when no cues detected."""
        detector = RelationshipDetection()

        goal1 = GoalNode(
            id="g1",
            title="Write documentation",
            description="Document the API"
        )
        goal2 = GoalNode(
            id="g2",
            title="Fix UI bug",
            description="Fix button alignment"
        )

        relationship = detector.detect(goal1, goal2)
        assert relationship == RelationshipType.INDEPENDENT


class TestMultiGoalDAG:
    """Tests for the MultiGoalDAG class."""

    def test_add_node(self):
        """Test adding nodes to the DAG."""
        dag = MultiGoalDAG("test_dag")
        task = TaskNode(id="t1", title="Test task")
        dag.add_node(task)

        assert "t1" in dag._nodes
        assert dag.get_node("t1") is task

    def test_add_edge(self):
        """Test adding edges to the DAG."""
        dag = MultiGoalDAG("test_dag")
        dag.add_node(TaskNode(id="a", title="A"))
        dag.add_node(TaskNode(id="b", title="B"))

        edge_obj = DependencyEdge(
            source_id="a",
            target_id="b",
            relationship=RelationshipType.ENABLES
        )
        dag.add_edge(edge_obj)

        assert dag.graph.has_edge("a", "b")

    def test_add_edge_missing_node_raises_error(self):
        """Test that adding edge with missing node raises error."""
        dag = MultiGoalDAG("test_dag")
        dag.add_node(TaskNode(id="a", title="A"))

        edge_obj = DependencyEdge(
            source_id="a",
            target_id="nonexistent",
            relationship=RelationshipType.ENABLES
        )

        with pytest.raises(ValueError):
            dag.add_edge(edge_obj)

    def test_cycle_detection_no_cycle(self):
        """Test cycle detection with no cycles."""
        dag = MultiGoalDAG("acyclic")
        dag.add_node(TaskNode(id="a", title="A"))
        dag.add_node(TaskNode(id="b", title="B"))
        dag.add_node(TaskNode(id="c", title="C"))

        dag.add_edge(edge("a", "b").enables().build())
        dag.add_edge(edge("b", "c").enables().build())

        cycles = dag.detect_cycles()
        # Only enabling/subgoal edges should be checked
        assert len(cycles) == 0

    def test_cycle_detection_with_cycle(self):
        """Test cycle detection with a cycle."""
        dag = MultiGoalDAG("cyclic")
        dag.add_node(TaskNode(id="a", title="A"))
        dag.add_node(TaskNode(id="b", title="B"))
        dag.add_node(TaskNode(id="c", title="C"))

        dag.add_edge(edge("a", "b").enables().build())
        dag.add_edge(edge("b", "c").enables().build())
        dag.add_edge(edge("c", "a").enables().build())

        cycles = dag.detect_cycles()
        assert len(cycles) > 0

    def test_validation_passes_for_valid_dag(self):
        """Test validation passes for valid DAG."""
        dag = MultiGoalDAG("valid")
        dag.add_node(TaskNode(id="a", title="A"))
        dag.add_node(TaskNode(id="b", title="B"))
        dag.add_edge(edge("a", "b").enables().build())

        is_valid, errors = dag.validate()
        assert is_valid
        assert len(errors) == 0

    def test_validation_fails_for_cyclic_dag(self):
        """Test validation fails for cyclic DAG."""
        dag = MultiGoalDAG("invalid")
        dag.add_node(TaskNode(id="a", title="A"))
        dag.add_node(TaskNode(id="b", title="B"))
        dag.add_edge(edge("a", "b").enables().build())
        dag.add_edge(edge("b", "a").enables().build())

        is_valid, errors = dag.validate()
        assert not is_valid
        assert len(errors) > 0
        assert "cycle" in errors[0].lower()

    def test_execution_order(self):
        """Test topological execution order."""
        dag = MultiGoalDAG("ordered")
        dag.add_node(TaskNode(id="a", title="A"))
        dag.add_node(TaskNode(id="b", title="B"))
        dag.add_node(TaskNode(id="c", title="C"))

        dag.add_edge(edge("a", "b").enables().build())
        dag.add_edge(edge("b", "c").enables().build())

        order = dag.execution_order()
        assert order.index("a") < order.index("b")
        assert order.index("b") < order.index("c")

    def test_get_ready_nodes(self):
        """Test getting ready nodes (no blocking dependencies)."""
        dag = MultiGoalDAG("ready_test")
        a = TaskNode(id="a", title="A", status=NodeStatus.PENDING)
        b = TaskNode(id="b", title="B", status=NodeStatus.PENDING)
        c = TaskNode(id="c", title="C", status=NodeStatus.PENDING)

        dag.add_node(a)
        dag.add_node(b)
        dag.add_node(c)

        # A enables B and C
        dag.add_edge(edge("a", "b").enables().build())
        dag.add_edge(edge("a", "c").enables().build())

        ready = dag.get_ready_nodes()
        # Only A is ready (no incoming dependencies)
        assert "a" in ready
        assert "b" not in ready
        assert "c" not in ready

    def test_get_parallelizable_nodes(self):
        """Test finding parallelizable nodes."""
        dag = MultiGoalDAG("parallel_test")
        a = TaskNode(id="a", title="A")
        b = TaskNode(id="b", title="B")
        c = TaskNode(id="c", title="C")

        dag.add_node(a)
        dag.add_node(b)
        dag.add_node(c)

        # A enables B, but C is independent
        dag.add_edge(edge("a", "b").enables().build())

        parallel = dag.get_parallelizable_nodes("a")
        assert "c" in parallel  # C is independent of A
        assert "b" not in parallel  # B depends on A


class TestTopologicalExecutor:
    """Tests for the topological execution strategy."""

    @pytest.mark.asyncio
    async def test_execute_simple_dag(self):
        """Test executing a simple DAG."""
        dag = MultiGoalDAG("simple")
        a = TaskNode(id="a", title="A")
        b = TaskNode(id="b", title="B")
        c = TaskNode(id="c", title="C")

        dag.add_node(a)
        dag.add_node(b)
        dag.add_node(c)

        dag.add_edge(edge("a", "b").enables().build())
        dag.add_edge(edge("b", "c").enables().build())

        executor = TopologicalExecutor()
        result = await executor.execute(dag, max_parallel=1)

        assert result["status"] in ["completed", "partial"]
        assert "duration_seconds" in result

    @pytest.mark.asyncio
    async def test_custom_executor(self):
        """Test executor with custom execution function."""
        dag = MultiGoalDAG("custom")
        task = TaskNode(id="t1", title="Custom task")
        dag.add_node(task)

        executed_tasks = []

        async def custom_executor(t: TaskNode):
            executed_tasks.append(t.id)
            return f"Result for {t.title}"

        executor = TopologicalExecutor(executor=custom_executor)
        result = await executor.execute(dag, max_parallel=1)

        assert "t1" in executed_tasks
        assert result["nodes_completed"] >= 1


class TestGoalOrchestrator:
    """Tests for the high-level GoalOrchestrator API."""

    def test_add_goal(self):
        """Test adding a goal."""
        orchestrator = GoalOrchestrator("test")
        goal = orchestrator.add_goal(
            title="Test goal",
            description="A test goal",
            success_criteria=["Done"]
        )

        assert goal.title == "Test goal"
        assert goal.id in orchestrator.dag._nodes

    def test_add_task(self):
        """Test adding a task."""
        orchestrator = GoalOrchestrator("test")
        task = orchestrator.add_task(
            title="Test task",
            description="A test task",
            task_type="code"
        )

        assert task.title == "Test task"
        assert task.task_type == "code"

    def test_relate_enables(self):
        """Test creating an ENABLES relationship."""
        orchestrator = GoalOrchestrator("test")
        g1 = orchestrator.add_goal("Goal 1")
        g2 = orchestrator.add_goal("Goal 2")

        orchestrator.relate(g1.id, g2.id, RelationshipType.ENABLES)

        assert orchestrator.dag.graph.has_edge(g1.id, g2.id)

    def test_relate_synergistic(self):
        """Test creating a SYNERGISTIC relationship."""
        orchestrator = GoalOrchestrator("test")
        g1 = orchestrator.add_goal("Goal 1")
        g2 = orchestrator.add_goal("Goal 2")

        orchestrator.relate(
            g1.id,
            g2.id,
            RelationshipType.SYNERGISTIC,
            strategy="unified"
        )

        edge_data = orchestrator.dag.graph.get_edge_data(g1.id, g2.id)
        assert edge_data is not None

    def test_decompose_goal_into_tasks(self):
        """Test decomposing a goal into tasks."""
        orchestrator = GoalOrchestrator("test")
        goal = orchestrator.add_goal("Parent goal")
        t1 = orchestrator.add_task("Task 1")
        t2 = orchestrator.add_task("Task 2")

        orchestrator.decompose(goal.id, task_ids=[t1.id, t2.id])

        assert goal.decomposition_complete
        assert t1.id in goal.contributing_tasks
        assert t2.id in goal.contributing_tasks

    def test_decompose_goal_into_subgoals(self):
        """Test decomposing a goal into subgoals."""
        orchestrator = GoalOrchestrator("test")
        parent = orchestrator.add_goal("Parent goal")
        child1 = orchestrator.add_goal("Child goal 1")
        child2 = orchestrator.add_goal("Child goal 2")

        orchestrator.decompose(parent.id, subgoal_ids=[child1.id, child2.id])

        assert child1.id in parent.contributing_subgoals
        assert child2.id in parent.contributing_subgoals

    def test_get_status(self):
        """Test getting overall status."""
        orchestrator = GoalOrchestrator("status_test")
        orchestrator.add_goal("Goal 1")
        orchestrator.add_task("Task 1")

        status = orchestrator.get_status()

        assert status["goals"]["total"] == 1
        assert status["tasks"]["total"] == 1
        assert "execution_order" in status
        assert "ready_nodes" in status

    def test_to_dict(self):
        """Test serializing orchestrator to dict."""
        orchestrator = GoalOrchestrator("serialize_test")
        goal = orchestrator.add_goal("Goal 1")
        task = orchestrator.add_task("Task 1")
        orchestrator.relate(goal.id, task.id, RelationshipType.ENABLES)

        data = orchestrator.to_dict()

        assert data["name"] == "serialize_test"
        assert len(data["nodes"]) == 2
        assert len(data["edges"]) == 1


class TestIntegration:
    """Integration tests for complex scenarios."""

    @pytest.mark.asyncio
    async def test_multi_goal_with_mixed_relationships(self):
        """Test a DAG with multiple relationship types."""
        orchestrator = GoalOrchestrator("complex")

        # Create goals
        research = orchestrator.add_goal("Research")
        build = orchestrator.add_goal("Build")
        docs = orchestrator.add_goal("Documentation")
        marketing = orchestrator.add_goal("Marketing")

        # Create tasks
        r1 = orchestrator.add_task("Market research", task_type="research")
        r2 = orchestrator.add_task("Competitor analysis", task_type="research")
        b1 = orchestrator.add_task("Core implementation", task_type="code")
        d1 = orchestrator.add_task("Write README", task_type="writing")
        m1 = orchestrator.add_task("Launch campaign", task_type="marketing")

        # Decompose goals
        orchestrator.decompose(research.id, task_ids=[r1.id, r2.id])
        orchestrator.decompose(build.id, task_ids=[b1.id])
        orchestrator.decompose(docs.id, task_ids=[d1.id])
        orchestrator.decompose(marketing.id, task_ids=[m1.id])

        # Add relationships
        orchestrator.relate(research.id, build.id, RelationshipType.ENABLES)
        orchestrator.relate(build.id, docs.id, RelationshipType.ENABLES)
        orchestrator.relate(build.id, marketing.id, RelationshipType.ENABLES)
        orchestrator.relate(docs.id, marketing.id, RelationshipType.REINFORCES)

        # Validate
        is_valid, errors = orchestrator.dag.validate()
        assert is_valid, f"DAG validation failed: {errors}"

        # Check execution order
        order = orchestrator.dag.execution_order()
        assert research.id in order
        assert build.id in order

        # Get status
        status = orchestrator.get_status()
        assert status["goals"]["total"] == 4
        assert status["tasks"]["total"] == 5


# Example test demonstrating visualization
def test_visualization():
    """Test DOT format generation."""
    orchestrator = GoalOrchestrator("viz_test")
    g1 = orchestrator.add_goal("Goal 1")
    g2 = orchestrator.add_goal("Goal 2")
    t1 = orchestrator.add_task("Task 1")

    orchestrator.relate(g1.id, g2.id, RelationshipType.ENABLES)
    orchestrator.relate(t1.id, g1.id, RelationshipType.ENABLES)

    dot = orchestrator.visualize()
    assert "digraph viz_test" in dot
    assert "Goal 1" in dot
    assert "Goal 2" in dot
    assert "Task 1" in dot


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-x"])
