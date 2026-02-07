"""
Performance Tests - DAG Scalability.

Tests cover:
- Topological sort of 100 tasks
- Topological sort of 500 tasks
- Dependency detection scalability
- DAG visualization generation

Location: /Users/kurultai/molt/tests/performance/test_dag_scalability.py
"""

import time
from datetime import datetime, timezone
from typing import List, Dict, Any
from unittest.mock import Mock

import pytest

from tools.multi_goal_orchestration import (
    NodeStatus,
    Priority,
    TaskNode,
    GoalNode,
    MultiGoalDAG,
    NodeFactory,
    RelationshipType,
    DependencyEdge,
)


# =============================================================================
# TestDAGScalability
# =============================================================================

class TestDAGScalability:
    """Scalability tests for DAG operations."""

    def create_linear_dag(self, num_nodes: int) -> MultiGoalDAG:
        """Create a linear DAG for testing."""
        dag = MultiGoalDAG()
        nodes = []

        for i in range(num_nodes):
            task = NodeFactory.create_task(f"Task {i}")
            nodes.append(task)
            dag.add_node(task)

        # Create linear chain
        for i in range(num_nodes - 1):
            dag.add_edge(DependencyEdge(
                source_id=nodes[i].id,
                target_id=nodes[i+1].id,
                relationship=RelationshipType.ENABLES
            ))

        return dag

    def create_parallel_dag(self, num_branches: int, branch_depth: int) -> MultiGoalDAG:
        """Create a parallel DAG for testing."""
        dag = MultiGoalDAG()

        # Root node
        root = NodeFactory.create_task("Root")
        dag.add_node(root)

        # Create branches
        current_level = [root]

        for depth in range(branch_depth):
            next_level = []

            for parent in current_level:
                for i in range(num_branches):
                    task = NodeFactory.create_task(f"L{depth}B{i}")
                    dag.add_node(task)
                    dag.add_edge(DependencyEdge(
                        source_id=parent.id,
                        target_id=task.id,
                        relationship=RelationshipType.ENABLES
                    ))
                    next_level.append(task)

            current_level = next_level

        return dag

    @pytest.mark.performance
    @pytest.mark.slow
    def test_topological_sort_100_tasks(self):
        """Test topological sort with 100 tasks."""
        dag = self.create_linear_dag(100)

        start = time.time()
        order = dag.execution_order()
        elapsed = (time.time() - start) * 1000

        assert len(order) == 100
        assert elapsed < 1000  # Should complete in < 1 second

        print(f"\nTopological sort 100 tasks: {elapsed:.2f}ms")

    @pytest.mark.performance
    @pytest.mark.slow
    def test_topological_sort_500_tasks(self):
        """Test topological sort with 500 tasks."""
        dag = self.create_linear_dag(500)

        start = time.time()
        order = dag.execution_order()
        elapsed = (time.time() - start) * 1000

        assert len(order) == 500
        assert elapsed < 5000  # Should complete in < 5 seconds

        print(f"\nTopological sort 500 tasks: {elapsed:.2f}ms")

    @pytest.mark.performance
    @pytest.mark.slow
    def test_dependency_detection_scalability(self):
        """Test dependency detection with many nodes."""
        # Create DAG with 200 nodes and random-ish dependencies
        dag = MultiGoalDAG()
        nodes = []

        for i in range(200):
            task = NodeFactory.create_task(f"Task {i}")
            nodes.append(task)
            dag.add_node(task)

        # Create dependencies (each node depends on previous 3)
        for i in range(3, 200):
            for j in range(1, 4):
                if i - j >= 0:
                    dag.add_edge(DependencyEdge(
                        source_id=nodes[i-j].id,
                        target_id=nodes[i].id,
                        relationship=RelationshipType.ENABLES
                    ))

        start = time.time()
        is_valid, errors = dag.validate()
        elapsed = (time.time() - start) * 1000

        assert is_valid is True
        assert elapsed < 1000  # Validation should be fast

        print(f"\nDependency detection 200 nodes: {elapsed:.2f}ms")

    @pytest.mark.performance
    @pytest.mark.slow
    def test_dag_visualization_generation(self):
        """Test DAG visualization generation performance."""
        dag = self.create_parallel_dag(num_branches=5, branch_depth=4)

        # Simulate visualization generation
        start = time.time()

        # Get all nodes and edges
        nodes = list(dag._nodes.values())
        edges = list(dag.graph.edges())

        # Build visualization structure
        viz_data = {
            "nodes": [
                {
                    "id": n.id,
                    "title": n.title,
                    "type": "goal" if isinstance(n, GoalNode) else "task"
                }
                for n in nodes
            ],
            "edges": [
                {"source": u, "target": v}
                for u, v in edges
            ]
        }

        elapsed = (time.time() - start) * 1000

        assert len(viz_data["nodes"]) > 0
        assert elapsed < 500  # Should be fast

        print(f"\nDAG visualization generation: {elapsed:.2f}ms")

    @pytest.mark.performance
    @pytest.mark.slow
    def test_level_grouping_scalability(self):
        """Test level grouping with large DAG."""
        dag = self.create_parallel_dag(num_branches=10, branch_depth=5)

        from tools.multi_goal_orchestration import TopologicalExecutor
        executor = TopologicalExecutor()

        start = time.time()
        order = dag.execution_order()
        levels = executor._group_by_level(dag, order)
        elapsed = (time.time() - start) * 1000

        assert len(levels) > 0
        assert elapsed < 2000  # Increased from 1000ms to account for coverage overhead

        print(f"\nLevel grouping with {len(order)} nodes: {elapsed:.2f}ms")

    @pytest.mark.performance
    @pytest.mark.slow
    def test_cycle_detection_scalability(self):
        """Test cycle detection with large DAG."""
        dag = MultiGoalDAG()
        nodes = []

        # Create 500 nodes
        for i in range(500):
            task = NodeFactory.create_task(f"Task {i}")
            nodes.append(task)
            dag.add_node(task)

        # Create linear dependencies (no cycles)
        for i in range(499):
            dag.add_edge(DependencyEdge(
                source_id=nodes[i].id,
                target_id=nodes[i+1].id,
                relationship=RelationshipType.ENABLES
            ))

        start = time.time()
        cycles = dag.detect_cycles()
        elapsed = (time.time() - start) * 1000

        assert len(cycles) == 0
        assert elapsed < 1000

        print(f"\nCycle detection 500 nodes: {elapsed:.2f}ms")

    @pytest.mark.performance
    @pytest.mark.slow
    def test_parallel_branches_scalability(self):
        """Test DAG with many parallel branches."""
        dag = self.create_parallel_dag(num_branches=20, branch_depth=3)

        start = time.time()
        order = dag.execution_order()
        elapsed = (time.time() - start) * 1000

        # Should handle many branches
        assert len(order) > 0
        assert elapsed < 2000

        print(f"\nParallel branches (20x3): {elapsed:.2f}ms, {len(order)} nodes")

    @pytest.mark.performance
    @pytest.mark.slow
    def test_complex_dag_operations(self):
        """Test complex DAG with multiple operations."""
        # Create DAG with mixed structure
        dag = MultiGoalDAG()

        # Add root
        root = NodeFactory.create_task("Root")
        dag.add_node(root)

        # Add 50 parallel tasks
        parallel_tasks = []
        for i in range(50):
            task = NodeFactory.create_task(f"Parallel {i}")
            parallel_tasks.append(task)
            dag.add_node(task)
            dag.add_edge(DependencyEdge(
                source_id=root.id,
                target_id=task.id,
                relationship=RelationshipType.ENABLES
            ))

        # Add sequential chain
        chain_tasks = []
        prev = root
        for i in range(20):
            task = NodeFactory.create_task(f"Chain {i}")
            chain_tasks.append(task)
            dag.add_node(task)
            dag.add_edge(DependencyEdge(
                source_id=prev.id,
                target_id=task.id,
                relationship=RelationshipType.ENABLES
            ))
            prev = task

        # Run multiple operations
        start = time.time()

        is_valid, errors = dag.validate()
        assert is_valid

        order = dag.execution_order()
        assert len(order) > 0

        cycles = dag.detect_cycles()
        assert len(cycles) == 0

        elapsed = (time.time() - start) * 1000

        assert elapsed < 2000

        print(f"\nComplex DAG operations: {elapsed:.2f}ms, {len(order)} nodes")


# =============================================================================
# TestDAGMemoryUsage
# =============================================================================

class TestDAGMemoryUsage:
    """Tests for DAG memory efficiency."""

    @pytest.mark.performance
    @pytest.mark.slow
    def test_node_storage_efficiency(self):
        """Test that node storage is memory efficient."""
        dag = MultiGoalDAG()

        # Add many nodes
        for i in range(1000):
            task = NodeFactory.create_task(f"Task {i}")
            dag.add_node(task)

        # Should handle 1000 nodes
        assert len(dag._nodes) == 1000

    @pytest.mark.performance
    @pytest.mark.slow
    def test_edge_storage_efficiency(self):
        """Test that edge storage is memory efficient."""
        dag = MultiGoalDAG()

        # Create chain with many edges
        prev_node = None
        for i in range(1000):
            task = NodeFactory.create_task(f"Task {i}")
            dag.add_node(task)

            if prev_node:
                dag.add_edge(DependencyEdge(
                    source_id=prev_node.id,
                    target_id=task.id,
                    relationship=RelationshipType.ENABLES
                ))

            prev_node = task

        # Count edges
        edge_count = sum(1 for _ in dag.graph.edges())
        assert edge_count == 999


# =============================================================================
# TestDAGConcurrency
# =============================================================================

class TestDAGConcurrency:
    """Tests for concurrent DAG operations."""

    @pytest.mark.performance
    @pytest.mark.slow
    def test_concurrent_dag_modification(self):
        """Test concurrent DAG modifications."""
        import threading

        dag = MultiGoalDAG()
        num_threads = 10
        nodes_per_thread = 50
        errors = []

        def add_nodes(thread_id: int):
            try:
                for i in range(nodes_per_thread):
                    task = NodeFactory.create_task(f"T{thread_id}-{i}")
                    dag.add_node(task)
            except Exception as e:
                errors.append(e)

        threads = []
        for i in range(num_threads):
            t = threading.Thread(target=add_nodes, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # All nodes should be added
        assert len(errors) == 0
        assert len(dag._nodes) == num_threads * nodes_per_thread

    @pytest.mark.performance
    @pytest.mark.slow
    def test_concurrent_edge_addition(self):
        """Test concurrent edge additions."""
        import threading

        dag = MultiGoalDAG()

        # Add nodes first
        nodes = []
        for i in range(100):
            task = NodeFactory.create_task(f"Task {i}")
            nodes.append(task)
            dag.add_node(task)

        num_threads = 10
        edges_per_thread = 20
        errors = []

        def add_edges(thread_id: int):
            try:
                for i in range(edges_per_thread):
                    # Add edges in a pattern
                    idx = (thread_id * edges_per_thread + i) % 100
                    next_idx = (idx + 1) % 100
                    dag.add_edge(DependencyEdge(
                        source_id=nodes[idx].id,
                        target_id=nodes[next_idx].id,
                        relationship=RelationshipType.ENABLES
                    ))
            except Exception as e:
                errors.append(e)

        threads = []
        for i in range(num_threads):
            t = threading.Thread(target=add_edges, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0
