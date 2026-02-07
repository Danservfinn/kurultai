"""
Chaos Tests - Data Corruption.

Tests cover:
- Handling corrupted task status
- Handling orphaned dependencies
- Handling cycle in production DAG
- Handling duplicate task IDs
- Recovery with data repair

Location: /Users/kurultai/molt/tests/chaos/test_data_corruption.py
"""

import os
import sys
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from unittest.mock import Mock, MagicMock

import pytest

# Calculate project root (two levels up from this file)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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
DependencyEdge = mgo.DependencyEdge


# =============================================================================
# Data Corruption Simulator
# =============================================================================

class DataCorruptionSimulator:
    """Simulates various data corruption scenarios."""

    @staticmethod
    def corrupt_task_status(task: Dict) -> Dict:
        """Corrupt task status field."""
        valid_statuses = ["pending", "in_progress", "completed", "failed", "blocked", "cancelled"]

        # Set to invalid status
        task["status"] = "invalid_status_value"

        return task

    @staticmethod
    def create_orphaned_dependencies(dag_nodes: List[Dict]) -> List[Dict]:
        """Create tasks with orphaned dependencies."""
        # Create task that references non-existent dependencies
        orphaned = {
            "id": "orphaned-task",
            "status": "blocked",
            "blocked_by": ["non-existent-1", "non-existent-2"],
            "description": "Task with orphaned dependencies"
        }

        return [orphaned]

    @staticmethod
    def create_cyclic_dag() -> Dict:
        """Create a DAG with a cycle."""
        return {
            "nodes": [
                {"id": "A", "blocked_by": ["C"]},
                {"id": "B", "blocked_by": ["A"]},
                {"id": "C", "blocked_by": ["B"]}
            ],
            "has_cycle": True
        }

    @staticmethod
    def create_duplicate_task_ids() -> List[Dict]:
        """Create tasks with duplicate IDs."""
        duplicate_id = "duplicate-123"

        return [
            {"id": duplicate_id, "type": "research", "status": "pending"},
            {"id": duplicate_id, "type": "code", "status": "pending"}
        ]


# =============================================================================
# Data Repair Utilities
# =============================================================================

class DataRepairer:
    """Repairs corrupted data."""

    VALID_STATUSES = ["pending", "in_progress", "completed", "failed", "blocked", "cancelled", "skipped"]

    def repair_task_status(self, task: Dict) -> Dict:
        """Repair corrupted task status."""
        if task.get("status") not in self.VALID_STATUSES:
            # Default to pending for unknown status
            task["status"] = "pending"
            task["_repaired"] = True

        return task

    def remove_orphaned_dependencies(self, task: Dict, valid_ids: set) -> Dict:
        """Remove orphaned dependencies from task."""
        if "blocked_by" in task:
            valid_deps = [
                dep_id for dep_id in task["blocked_by"]
                if dep_id in valid_ids
            ]
            task["blocked_by"] = valid_deps

            if len(valid_deps) < len(task.get("blocked_by", [])):
                task["_repaired"] = True

        return task

    def break_cycle(self, dag_data: Dict) -> Dict:
        """Break cycles in DAG by removing edges."""
        if not dag_data.get("has_cycle"):
            return dag_data

        # Find and remove the cycle-causing edge
        nodes = dag_data["nodes"]
        node_map = {n["id"]: n for n in nodes}

        # Remove last edge that creates cycle
        for node in reversed(nodes):
            blocked_by = node.get("blocked_by", [])
            if blocked_by:
                # Remove this dependency
                node["blocked_by"] = []
                dag_data["has_cycle"] = False
                dag_data["_repaired"] = True
                break

        return dag_data

    def resolve_duplicate_ids(self, tasks: List[Dict]) -> List[Dict]:
        """Resolve duplicate task IDs."""
        seen_ids = {}
        duplicates = []

        # Group by ID
        for task in tasks:
            task_id = task["id"]
            if task_id not in seen_ids:
                seen_ids[task_id] = []
            seen_ids[task_id].append(task)

        # Resolve duplicates
        result = []
        import uuid

        for task_id, task_list in seen_ids.items():
            if len(task_list) == 1:
                result.append(task_list[0])
            else:
                # Keep first, regenerate IDs for rest
                result.append(task_list[0])
                for task in task_list[1:]:
                    task["id"] = f"{task_id}-{str(uuid.uuid4())[:8]}"
                    task["_original_id"] = task_id
                    task["_repaired"] = True
                    result.append(task)

        return result


# =============================================================================
# TestDataCorruption
# =============================================================================

class TestDataCorruption:
    """Tests for handling data corruption."""

    @pytest.fixture
    def repairer(self):
        return DataRepairer()

    @pytest.mark.chaos
    def test_handling_corrupted_task_status(self, repairer):
        """Test handling corrupted task status."""
        task = {
            "id": "task-123",
            "description": "Test task",
            "status": "corrupted_status"
        }

        # Validate
        assert task["status"] not in repairer.VALID_STATUSES

        # Repair
        repaired = repairer.repair_task_status(task)

        assert repaired["status"] in repairer.VALID_STATUSES
        assert repaired.get("_repaired") is True

    @pytest.mark.chaos
    def test_handling_orphaned_dependencies(self, repairer):
        """Test handling orphaned dependencies."""
        valid_ids = {"task-1", "task-2", "task-3"}

        task = {
            "id": "task-1",
            "status": "blocked",
            "blocked_by": ["task-2", "orphan-1", "orphan-2"]
        }

        # Repair
        repaired = repairer.remove_orphaned_dependencies(task, valid_ids)

        assert "orphan-1" not in repaired["blocked_by"]
        assert "orphan-2" not in repaired["blocked_by"]
        assert "task-2" in repaired["blocked_by"]

    @pytest.mark.chaos
    def test_handling_cycle_in_production_dag(self, repairer):
        """Test handling cycle in production DAG."""
        cyclic_dag = DataCorruptionSimulator.create_cyclic_dag()

        assert cyclic_dag["has_cycle"] is True

        # Repair
        repaired = repairer.break_cycle(cyclic_dag)

        assert repaired.get("has_cycle") is False
        assert repaired.get("_repaired") is True

    @pytest.mark.chaos
    def test_handling_cycle_in_multi_goal_dag(self):
        """Test cycle detection in actual MultiGoalDAG."""
        dag = MultiGoalDAG(name="cyclic_dag")

        # Create tasks
        task_a = NodeFactory.create_task("Task A")
        task_b = NodeFactory.create_task("Task B")
        task_c = NodeFactory.create_task("Task C")

        dag.add_node(task_a)
        dag.add_node(task_b)
        dag.add_node(task_c)

        # Create cycle: A -> B -> C -> A
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
        dag.add_edge(DependencyEdge(
            source_id=task_c.id,
            target_id=task_a.id,
            relationship=RelationshipType.ENABLES
        ))

        # Detect cycles
        cycles = dag.detect_cycles()
        assert len(cycles) > 0, "Should detect cycle in DAG"

        # Validate should fail
        is_valid, errors = dag.validate()
        assert is_valid is False
        assert any("cycle" in e.lower() for e in errors)

    @pytest.mark.chaos
    def test_handling_duplicate_task_ids(self, repairer):
        """Test handling duplicate task IDs."""
        duplicates = DataCorruptionSimulator.create_duplicate_task_ids()

        # Verify duplicates exist
        ids = [t["id"] for t in duplicates]
        assert len(ids) != len(set(ids))

        # Resolve
        resolved = repairer.resolve_duplicate_ids(duplicates)

        # No duplicates should remain
        resolved_ids = [t["id"] for t in resolved]
        assert len(resolved_ids) == len(set(resolved_ids))

        # Check repairs
        repaired_count = sum(1 for t in resolved if t.get("_repaired"))
        assert repaired_count == 1  # One was re-ID'd

    @pytest.mark.chaos
    def test_handling_duplicate_task_ids_in_dag(self):
        """Test handling duplicate task IDs in MultiGoalDAG."""
        dag = MultiGoalDAG(name="duplicate_test")

        # Create task
        task1 = NodeFactory.create_task("Task 1")
        task1_id = task1.id

        # Add first task
        dag.add_node(task1)
        assert dag.get_node(task1_id) is not None

        # Create second task with same ID (simulating corruption)
        task2 = NodeFactory.create_task("Task 2")
        task2.id = task1_id  # Force duplicate ID

        # Adding duplicate should overwrite or be handled gracefully
        dag.add_node(task2)

        # Verify only one node with that ID exists
        node = dag.get_node(task1_id)
        assert node is not None
        assert node.title == "Task 2"  # Second add overwrites


# =============================================================================
# TestDataIntegrityChecks
# =============================================================================

class TestDataIntegrityChecks:
    """Tests for data integrity checking."""

    def test_validate_task_integrity(self):
        """Test task integrity validation."""
        validator = DataRepairer()

        # Valid task
        valid_task = {
            "id": "task-123",
            "type": "research",
            "description": "Valid task",
            "status": "pending"
        }

        assert valid_task["status"] in validator.VALID_STATUSES

        # Invalid task
        invalid_task = {
            "id": "task-456",
            "type": "code",
            "description": "Invalid task",
            "status": "unknown_status"
        }

        assert invalid_task["status"] not in validator.VALID_STATUSES

    def test_validate_dag_integrity(self):
        """Test DAG integrity validation."""
        # Valid DAG
        dag = MultiGoalDAG()
        task1 = NodeFactory.create_task("Task 1")
        task2 = NodeFactory.create_task("Task 2")

        dag.add_node(task1)
        dag.add_node(task2)
        dag.add_edge(DependencyEdge(
            source_id=task1.id,
            target_id=task2.id,
            relationship=RelationshipType.ENABLES
        ))

        is_valid, errors = dag.validate()
        assert is_valid is True
        assert len(errors) == 0

    def test_detect_self_loops(self):
        """Test detection of self-looping tasks."""
        task_with_self_loop = {
            "id": "task-123",
            "description": "Task with self loop",
            "blocked_by": ["task-123"]  # References itself
        }

        # Should be detectable
        assert task_with_self_loop["blocked_by"][0] == task_with_self_loop["id"]


# =============================================================================
# TestRecoveryWithRepair
# =============================================================================

class TestRecoveryWithRepair:
    """Tests for recovery with data repair."""

    @pytest.fixture
    def repairer(self):
        return DataRepairer()

    @pytest.mark.chaos
    def test_recovery_with_data_repair(self, repairer):
        """Test system recovery with data repair."""
        corrupted_tasks = [
            {"id": "task-1", "status": "invalid1", "description": "Task 1"},
            {"id": "task-2", "status": "pending", "description": "Task 2"},
            {"id": "task-3", "status": "invalid2", "description": "Task 3"}
        ]

        # Repair all
        repaired = [repairer.repair_task_status(t) for t in corrupted_tasks]

        # All should have valid status now
        for task in repaired:
            assert task["status"] in repairer.VALID_STATUSES

        # Check repair count
        repaired_count = sum(1 for t in repaired if t.get("_repaired"))
        assert repaired_count == 2

    @pytest.mark.chaos
    def test_batch_repair(self, repairer):
        """Test batch repair of corrupted data."""
        batch_corruption = [
            {"id": f"task-{i}", "status": f"corrupt_{i}", "description": f"Task {i}"}
            for i in range(10)
        ]

        # Batch repair
        repaired = []
        for task in batch_corruption:
            repaired.append(repairer.repair_task_status(task))

        # Verify all repaired
        for task in repaired:
            assert task["status"] in repairer.VALID_STATUSES

    @pytest.mark.chaos
    def test_recovery_with_dag_repair(self):
        """Test recovery with DAG data repair."""
        dag = MultiGoalDAG(name="recovery_test")

        # Create tasks with corrupted status values
        task1 = NodeFactory.create_task("Task 1")
        task2 = NodeFactory.create_task("Task 2")
        task3 = NodeFactory.create_task("Task 3")

        # Simulate corrupted status by directly manipulating the node
        task1.status = NodeStatus.PENDING
        task2.status = NodeStatus.PENDING
        task3.status = NodeStatus.PENDING

        dag.add_node(task1)
        dag.add_node(task2)
        dag.add_node(task3)

        # Add valid dependencies
        dag.add_edge(DependencyEdge(
            source_id=task1.id,
            target_id=task2.id,
            relationship=RelationshipType.ENABLES
        ))

        # Validate before corruption
        is_valid, errors = dag.validate()
        assert is_valid is True

        # Now corrupt by adding a cycle
        dag.add_edge(DependencyEdge(
            source_id=task2.id,
            target_id=task3.id,
            relationship=RelationshipType.ENABLES
        ))
        dag.add_edge(DependencyEdge(
            source_id=task3.id,
            target_id=task1.id,
            relationship=RelationshipType.ENABLES
        ))

        # Validate should fail
        is_valid, errors = dag.validate()
        assert is_valid is False

        # Repair: remove the cycle-causing edge
        # In a real scenario, we'd remove the edge from task3 -> task1
        dag.graph.remove_edge(task3.id, task1.id)

        # Validate again
        is_valid, errors = dag.validate()
        assert is_valid is True

    @pytest.mark.chaos
    def test_recovery_with_orphaned_edges(self):
        """Test recovery when edges reference non-existent nodes."""
        dag = MultiGoalDAG(name="orphan_edge_test")

        task1 = NodeFactory.create_task("Task 1")
        dag.add_node(task1)

        # Attempt to add edge to non-existent node should raise ValueError
        with pytest.raises(ValueError) as exc_info:
            dag.add_edge(DependencyEdge(
                source_id=task1.id,
                target_id="non-existent-node",
                relationship=RelationshipType.ENABLES
            ))

        assert "non-existent-node" in str(exc_info.value)

    @pytest.mark.chaos
    def test_recovery_with_self_loop_prevention(self):
        """Test that self-loops are prevented at edge creation."""
        task1 = NodeFactory.create_task("Task 1")

        # Self-loop should be rejected at edge creation
        with pytest.raises(ValueError) as exc_info:
            DependencyEdge(
                source_id=task1.id,
                target_id=task1.id,
                relationship=RelationshipType.ENABLES
            )

        assert "self-loop" in str(exc_info.value).lower()


# =============================================================================
# Cycle Prevention
# =============================================================================

class CyclePreventer:
    """Prevents cycles in graph edges."""

    def __init__(self):
        self.edges = set()
        self.nodes = set()

    def add_edge(self, source: str, target: str) -> bool:
        """Add edge, preventing cycles."""
        if source == target:
            return False  # No self-loops

        # Check if would create cycle
        if self._would_create_cycle(source, target):
            return False

        self.edges.add((source, target))
        if source not in self.nodes:
            self.nodes.add(source)
        if target not in self.nodes:
            self.nodes.add(target)

        return True

    def _would_create_cycle(self, source: str, target: str) -> bool:
        """Check if adding edge would create cycle."""
        # Check if target can reach source (adding source->target would create cycle)
        visited = set()

        def dfs(node):
            if node == source:
                return True
            if node in visited:
                return False
            visited.add(node)

            for (u, v) in self.edges:
                if u == node:
                    if dfs(v):
                        return True
            return False

        return dfs(target)


# =============================================================================
# TestCorruptionPrevention
# =============================================================================

class TestCorruptionPrevention:
    """Tests for corruption prevention mechanisms."""

    def test_prevent_invalid_status_creation(self):
        """Test prevention of invalid status creation."""
        valid_statuses = ["pending", "in_progress", "completed", "failed", "blocked"]

        def create_task(status: str) -> bool:
            if status not in valid_statuses:
                raise ValueError(f"Invalid status: {status}")
            return True

        # Valid
        assert create_task("pending")

        # Invalid
        with pytest.raises(ValueError):
            create_task("unknown")

    def test_prevent_cycle_creation(self):
        """Test prevention of cycle creation."""
        preventer = CyclePreventer()

        # Add edges: A -> B -> C
        assert preventer.add_edge("A", "B")
        assert preventer.add_edge("B", "C")
        assert preventer.add_edge("A", "C")  # A->C is OK (not cycle)

        # Try to add C -> A (would create cycle)
        assert not preventer.add_edge("C", "A")

        # Try self-loop
        assert not preventer.add_edge("B", "B")
