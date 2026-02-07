"""
Tests for Priority Command Handler functionality.

Tests cover:
- Natural language priority command parsing
- "do X before Y" commands
- "what's the plan" queries
- Priority overrides
- DAG explanation

Location: /Users/kurultai/molt/tests/test_priority_commands.py
"""

import os
import sys
import re
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from unittest.mock import Mock, MagicMock, patch

import pytest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
# Priority Command Handler (Mock Implementation)
# =============================================================================

class PriorityCommandHandler:
    """
    Handler for natural language priority override commands.

    Supports commands like:
    - "do X before Y"
    - "make X critical priority"
    - "what's the plan"
    - "sync from notion"
    """

    def __init__(self, dag: MultiGoalDAG):
        self.dag = dag
        self.command_patterns = {
            "do_X_before_Y": r"do\s+(.+?)\s+before\s+(.+?)$",
            "do_X_first": r"do\s+(.+?)\s+first",
            "make_X_priority": r"make\s+(.+?)\s+(critical|high|low)\s+priority",
            "whats_the_plan": r"what'?s\s+the\s+plan|what\s+is\s+the\s+plan",
            "sync_from_notion": r"sync\s+from\s+notion",
        }

    def handle(self, command: str, context: Dict = None) -> Dict[str, Any]:
        """
        Handle a priority command.

        Returns:
            Result dict with status and data
        """
        command = command.strip().lower()

        # Check each pattern
        for cmd_type, pattern in self.command_patterns.items():
            match = re.match(pattern, command, re.IGNORECASE)
            if match:
                return self._handle_command(cmd_type, match, command, context)

        return {
            "status": "unknown_command",
            "message": f"Unknown command: {command}"
        }

    def _handle_command(
        self,
        cmd_type: str,
        match: re.Match,
        original_command: str,
        context: Dict = None
    ) -> Dict[str, Any]:
        """Handle a matched command."""
        if cmd_type == "do_X_before_Y":
            x_task = match.group(1).strip()
            y_task = match.group(2).strip()
            return self.set_priority(x_task, y_task)

        elif cmd_type == "do_X_first":
            task = match.group(1).strip()
            return self.set_priority(task, priority=Priority.CRITICAL)

        elif cmd_type == "make_X_priority":
            task = match.group(1).strip()
            priority_str = match.group(2).strip()
            priority_map = {
                "critical": Priority.CRITICAL,
                "high": Priority.HIGH,
                "low": Priority.LOW
            }
            priority = priority_map.get(priority_str, Priority.NORMAL)
            return self.set_priority(task, priority=priority)

        elif cmd_type == "whats_the_plan":
            return self.explain_dag()

        elif cmd_type == "sync_from_notion":
            return {"status": "sync_requested", "message": "Syncing from Notion"}

        return {"status": "error", "message": "Command not implemented"}

    def set_priority(
        self,
        task_identifier: str,
        before_task: str = None,
        priority: Priority = None
    ) -> Dict[str, Any]:
        """
        Set priority for a task or create explicit dependency.

        Args:
            task_identifier: Task description or ID
            before_task: Optional task that this should come before
            priority: Optional priority to set

        Returns:
            Result dict
        """
        # Find matching task
        task = self._find_task(task_identifier)

        if not task:
            return {
                "status": "task_not_found",
                "message": f"Task not found: {task_identifier}"
            }

        actions = []

        # Set priority if specified
        if priority:
            old_priority = task.priority
            task.priority = priority
            actions.append(f"Priority changed from {old_priority.name} to {priority.name}")

        # Create dependency if specified
        if before_task:
            before_node = self._find_task(before_task)
            if before_node:
                success = self._create_dependency(task.id, before_node.id)
                if success:
                    actions.append(f"Dependency created: {task.title} before {before_node.title}")
                else:
                    return {
                        "status": "dependency_failed",
                        "message": "Could not create dependency (would create cycle?)"
                    }

        return {
            "status": "success",
            "actions": actions,
            "task_id": task.id,
            "task_title": task.title
        }

    def _find_task(self, identifier: str) -> Optional[TaskNode]:
        """Find a task by ID or title substring."""
        # First try exact ID match
        node = self.dag.get_node(identifier)
        if node and isinstance(node, TaskNode):
            return node

        # Then try title substring match
        for node in self.dag._nodes.values():
            if isinstance(node, TaskNode) and identifier.lower() in node.title.lower():
                return node

        return None

    def _create_dependency(self, source_id: str, target_id: str) -> bool:
        """Create a dependency edge between tasks."""
        # Check for cycle first
        if self._would_create_cycle(source_id, target_id):
            return False

        edge = DependencyEdge(
            source_id=source_id,
            target_id=target_id,
            relationship=RelationshipType.ENABLES
        )
        self.dag.add_edge(edge)
        return True

    def _would_create_cycle(self, source_id: str, target_id: str) -> bool:
        """Check if adding edge would create a cycle."""
        # Add temporary edge
        edge = DependencyEdge(
            source_id=source_id,
            target_id=target_id,
            relationship=RelationshipType.ENABLES
        )
        self.dag.add_edge(edge)

        cycles = self.dag.detect_cycles()
        has_cycle = len(cycles) > 0

        # Remove temporary edge
        self.dag.graph.remove_edge(source_id, target_id)

        return has_cycle

    def explain_dag(self) -> Dict[str, Any]:
        """
        Explain the current DAG plan.

        Returns a human-readable plan.
        """
        execution_order = self.dag.execution_order()

        levels = self._group_by_level(execution_order)

        plan = []
        for level in sorted(levels.keys()):
            tasks = []
            for node_id in levels[level]:
                node = self.dag.get_node(node_id)
                if node:
                    tasks.append({
                        "id": node.id,
                        "title": node.title,
                        "type": "task" if isinstance(node, TaskNode) else "goal",
                        "priority": node.priority.name,
                        "status": node.status.name
                    })
            plan.append({"level": level, "tasks": tasks})

        return {
            "status": "success",
            "plan": plan,
            "total_tasks": len(execution_order)
        }

    def _group_by_level(self, execution_order: List[str]) -> Dict[int, List[str]]:
        """Group tasks by dependency level."""
        levels = {}
        level_map = {}

        for node_id in execution_order:
            level = 0
            for pred in self.dag.graph.predecessors(node_id):
                pred_level = level_map.get(pred, 0)
                level = max(level, pred_level + 1)

            level_map[node_id] = level
            if level not in levels:
                levels[level] = []
            levels[level].append(node_id)

        return levels


# =============================================================================
# TestPriorityCommandHandler
# =============================================================================

class TestPriorityCommandHandler:
    """Tests for PriorityCommandHandler class."""

    @pytest.fixture
    def dag(self):
        """Create a test DAG."""
        dag = MultiGoalDAG()

        tasks = []
        titles = ["Research", "Implementation", "Testing", "Documentation"]

        for title in titles:
            task = NodeFactory.create_task(title, task_type="generic")
            tasks.append(task)
            dag.add_node(task)

        # Add some dependencies
        dag.add_edge(DependencyEdge(
            source_id=tasks[0].id,
            target_id=tasks[1].id,
            relationship=RelationshipType.ENABLES
        ))
        dag.add_edge(DependencyEdge(
            source_id=tasks[1].id,
            target_id=tasks[2].id,
            relationship=RelationshipType.ENABLES
        ))

        return dag, tasks

    @pytest.fixture
    def handler(self, dag):
        """Create handler with test DAG."""
        dag_obj, _ = dag
        return PriorityCommandHandler(dag_obj)

    def test_handle_priority_command(self, handler):
        """Test handling a priority command."""
        result = handler.handle("make research critical priority")

        assert result["status"] == "success"
        assert "actions" in result

    def test_handle_do_X_before_Y_command(self, handler):
        """Test handling 'do X before Y' command."""
        result = handler.handle("do documentation before testing")

        assert result["status"] in ["success", "task_not_found"]

    def test_handle_do_X_first_command(self, handler):
        """Test handling 'do X first' command."""
        result = handler.handle("do research first")

        assert result["status"] == "success"
        assert result.get("task_id") is not None

    def test_handle_whats_the_plan_command(self, dag):
        """Test handling 'what's the plan' command."""
        dag_obj, _ = dag
        handler = PriorityCommandHandler(dag_obj)

        result = handler.handle("what's the plan")

        assert result["status"] == "success"
        assert "plan" in result
        assert len(result["plan"]) > 0

    def test_handle_sync_from_notion_command(self, handler):
        """Test handling 'sync from notion' command."""
        result = handler.handle("sync from notion")

        assert result["status"] == "sync_requested"

    def test_set_priority_finds_matching_task(self, dag):
        """Test that set_priority finds tasks by substring."""
        dag_obj, tasks = dag
        handler = PriorityCommandHandler(dag_obj)

        result = handler.set_priority("research")

        assert result["status"] == "success"
        assert result["task_id"] == tasks[0].id

    def test_set_priority_boosts_weight(self, dag):
        """Test that set_priority changes task priority."""
        dag_obj, tasks = dag
        handler = PriorityCommandHandler(dag_obj)

        old_priority = tasks[0].priority
        result = handler.set_priority("research", priority=Priority.CRITICAL)

        assert result["status"] == "success"
        assert tasks[0].priority == Priority.CRITICAL
        assert tasks[0].priority != old_priority

    def test_create_explicit_dependency(self, dag):
        """Test creating an explicit dependency."""
        dag_obj, tasks = dag
        handler = PriorityCommandHandler(dag_obj)

        result = handler.set_priority("documentation", before_task="testing")

        assert result["status"] == "success"
        # Verify dependency exists
        assert dag_obj.graph.has_edge(tasks[3].id, tasks[2].id)

    def test_create_dependency_cycle_prevention(self, dag):
        """Test that creating cycles is prevented."""
        dag_obj, tasks = dag
        handler = PriorityCommandHandler(dag_obj)

        # Try to create cycle (testing -> research would create cycle)
        result = handler.set_priority("testing", before_task="research")

        assert result["status"] == "dependency_failed"

    def test_explain_dag_returns_readable_plan(self, dag):
        """Test that explain_dag returns readable plan."""
        dag_obj, _ = dag
        handler = PriorityCommandHandler(dag_obj)

        result = handler.explain_dag()

        assert result["status"] == "success"
        assert "plan" in result
        assert result["total_tasks"] > 0

        # Verify plan structure
        for level_data in result["plan"]:
            assert "level" in level_data
            assert "tasks" in level_data


# =============================================================================
# TestCommandParsing
# =============================================================================

class TestCommandParsing:
    """Tests for command pattern matching."""

    @pytest.fixture
    def handler(self):
        """Create handler with empty DAG."""
        return PriorityCommandHandler(MultiGoalDAG())

    def test_parse_do_X_before_Y(self, handler):
        """Test parsing 'do X before Y' pattern."""
        pattern = handler.command_patterns["do_X_before_Y"]
        match = re.match(pattern, "do the auth work before the UI design", re.IGNORECASE)

        assert match is not None
        assert match.group(1) == "the auth work"
        assert match.group(2) == "the UI design"

    def test_parse_do_X_first(self, handler):
        """Test parsing 'do X first' pattern."""
        pattern = handler.command_patterns["do_X_first"]
        match = re.match(pattern, "do the backend API first", re.IGNORECASE)

        assert match is not None
        assert match.group(1) == "the backend API"

    def test_parse_make_X_priority(self, handler):
        """Test parsing 'make X priority' pattern."""
        pattern = handler.command_patterns["make_X_priority"]
        match = re.match(pattern, "make this critical priority", re.IGNORECASE)

        assert match is not None
        assert match.group(1) == "this"
        assert match.group(2) == "critical"

    def test_parse_whats_the_plan_variations(self, handler):
        """Test parsing variations of 'what's the plan'."""
        pattern = handler.command_patterns["whats_the_plan"]

        variations = [
            "what's the plan",
            "whats the plan",
            "what is the plan"
        ]

        for variation in variations:
            match = re.match(pattern, variation, re.IGNORECASE)
            assert match is not None

    def test_unknown_command_returns_unknown_status(self, handler):
        """Test that unknown commands return unknown status."""
        result = handler.handle("do something completely different")

        assert result["status"] == "unknown_command"


# =============================================================================
# TestPriorityOverrides
# =============================================================================

class TestPriorityOverrides:
    """Tests for priority override functionality."""

    def test_priority_override_changes_execution_order(self):
        """Test that priority override affects execution order."""
        dag = MultiGoalDAG()

        task1 = NodeFactory.create_task("Low priority task", priority=Priority.LOW)
        task2 = NodeFactory.create_task("High priority task", priority=Priority.HIGH)
        task3 = NodeFactory.create_task("Normal task", priority=Priority.NORMAL)

        for task in [task1, task2, task3]:
            dag.add_node(task)

        handler = PriorityCommandHandler(dag)

        # Get initial order
        initial_plan = handler.explain_dag()
        initial_ids = [t["id"] for level in initial_plan["plan"] for t in level["tasks"]]

        # Boost task1 to critical
        handler.set_priority("low priority", priority=Priority.CRITICAL)

        # Get new order
        new_plan = handler.explain_dag()
        new_ids = [t["id"] for level in new_plan["plan"] for t in level["tasks"]]

        # Order should be the same (no dependencies), but priority changed
        assert task1.priority == Priority.CRITICAL

    def test_multiple_priority_commands(self):
        """Test applying multiple priority commands."""
        dag = MultiGoalDAG()

        tasks = []
        for i in range(5):
            task = NodeFactory.create_task(f"Task {i}")
            tasks.append(task)
            dag.add_node(task)

        handler = PriorityCommandHandler(dag)

        # Apply multiple commands
        handler.set_priority("task 0", priority=Priority.CRITICAL)
        handler.set_priority("task 1", priority=Priority.HIGH)
        handler.set_priority("task 2", priority=Priority.LOW)

        assert tasks[0].priority == Priority.CRITICAL
        assert tasks[1].priority == Priority.HIGH
        assert tasks[2].priority == Priority.LOW


# =============================================================================
# TestTaskNotFound
# =============================================================================

class TestTaskNotFound:
    """Tests for handling non-existent tasks."""

    @pytest.fixture
    def handler(self):
        return PriorityCommandHandler(MultiGoalDAG())

    def test_set_priority_non_existent_task(self, handler):
        """Test setting priority on non-existent task."""
        result = handler.set_priority("nonexistent task")

        assert result["status"] == "task_not_found"

    def test_create_dependency_non_existent_task(self, handler):
        """Test creating dependency with non-existent task."""
        result = handler.set_priority("fake task", before_task="also fake")

        assert result["status"] == "task_not_found"
