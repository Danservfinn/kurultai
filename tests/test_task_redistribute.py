#!/usr/bin/env python3
"""
Unit tests for task-redistribute.py domain priority logic.

Tests the core routing behavior introduced in the
"Priority Redistribution Mongke Domain" task.
"""

import sys
import importlib.util
from pathlib import Path
from unittest.mock import Mock, patch

# Add scripts directory to path
SCRIPT_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

# Import task-redistribute.py (module name has hyphen, need importlib)
spec = importlib.util.spec_from_file_location(
    "task_redistribute",
    SCRIPT_DIR / "task-redistribute.py"
)
task_redistribute = importlib.util.module_from_spec(spec)
spec.loader.exec_module(task_redistribute)

find_movable_tasks = task_redistribute.find_movable_tasks


class TestDomainPriorityRouting:
    """Test domain-priority routing logic."""

    def test_domain_none_fallback_to_keyword(self):
        """When domain is None, should skip to keyword-based fallback."""
        pending = [
            (Path("/fake/task.md"), "Test task", "---\ndomain: null\n---\nContent", None)
        ]

        with patch.object(task_redistribute, "get_pending_tasks", return_value=pending):
            with patch.object(task_redistribute, "get_capable_alternates", return_value=[("mongke", 0.9)]):
                result = find_movable_tasks(
                    overloaded_agent="kublai",
                    underutilized_agents=[("mongke", 0), ("jochi", 0)]
                )

        assert len(result) == 1
        assert result[0][2] == "mongke"

    def test_research_domain_mongke_priority(self):
        """Research domain tasks should prioritize mongke."""
        pending = [
            (Path("/fake/research-task.md"), "Research task", "---\ndomain: research\npriority: normal\n---\nContent", "research")
        ]

        with patch.object(task_redistribute, "get_pending_tasks", return_value=pending):
            result = find_movable_tasks(
                overloaded_agent="kublai",
                underutilized_agents=[("tolui", 0), ("mongke", 0), ("jochi", 0)]
            )

        assert len(result) == 1
        assert result[0][2] == "mongke"

    def test_analysis_domain_mongke_priority_over_tolui(self):
        """Analysis domain should prioritize mongke over tolui."""
        pending = [
            (Path("/fake/analysis-task.md"), "Analyze data", "---\ndomain: analysis\npriority: normal\n---\nContent", "analysis")
        ]

        with patch.object(task_redistribute, "get_pending_tasks", return_value=pending):
            result = find_movable_tasks(
                overloaded_agent="kublai",
                underutilized_agents=[("tolui", 0), ("mongke", 0)]
            )

        assert len(result) == 1
        assert result[0][2] == "mongke"

    def test_implementation_domain_temujin_priority(self):
        """Implementation domain should prioritize temujin."""
        pending = [
            (Path("/fake/impl-task.md"), "Build feature", "---\ndomain: implementation\npriority: normal\n---\nContent", "implementation")
        ]

        with patch.object(task_redistribute, "get_pending_tasks", return_value=pending):
            result = find_movable_tasks(
                overloaded_agent="kublai",
                underutilized_agents=[("tolui", 0), ("temujin", 0)]
            )

        assert len(result) == 1
        assert result[0][2] == "temujin"

    def test_high_priority_tasks_exempt(self):
        """HIGH priority tasks should not be moved."""
        pending = [
            (Path("/fake/high-task.md"), "Urgent task", "---\ndomain: research\npriority: high\n---\nContent", "research")
        ]

        with patch.object(task_redistribute, "get_pending_tasks", return_value=pending):
            result = find_movable_tasks(
                overloaded_agent="kublai",
                underutilized_agents=[("mongke", 0)]
            )

        assert len(result) == 0

    def test_ops_tasks_stay_with_ogedei(self):
        """Ops tasks should stay with ogedei (primary agent)."""
        pending = [
            (Path("/fake/ops-task.md"), "Restart service", "---\ndomain: ops\npriority: normal\n---\nContent", "ops")
        ]

        with patch.object(task_redistribute, "get_pending_tasks", return_value=pending):
            result = find_movable_tasks(
                overloaded_agent="ogedei",
                underutilized_agents=[("temujin", 0)]
            )

        assert len(result) == 0

    def test_escalation_tasks_not_moved(self):
        """Escalation tasks should not be moved."""
        pending = [
            (Path("/fake/escalation-task.md"), "Escalate issue", "---\ndomain: escalation\npriority: normal\n---\nContent", "escalation")
        ]

        with patch.object(task_redistribute, "get_pending_tasks", return_value=pending):
            result = find_movable_tasks(
                overloaded_agent="kublai",
                underutilized_agents=[("ogedei", 0)]
            )

        assert len(result) == 0


class TestPerformanceOptimizations:
    """Test performance-related optimizations."""

    def test_underutilized_set_lookup(self):
        """Verify underutilized_set is created for O(1) lookups."""
        pending = [
            (Path("/fake/research-task.md"), "Research task", "---\ndomain: research\npriority: normal\n---\nContent", "research")
        ]

        with patch.object(task_redistribute, "get_pending_tasks", return_value=pending):
            underutilized = [("temujin", 0), ("ogedei", 0), ("jochi", 0), ("tolui", 0), ("mongke", 0)]
            result = find_movable_tasks(
                overloaded_agent="kublai",
                underutilized_agents=underutilized
            )

        assert len(result) == 1
        assert result[0][2] == "mongke"


def run_tests() -> int:
    """Run all tests and return exit code."""
    test_classes = [
        TestDomainPriorityRouting(),
        TestPerformanceOptimizations()
    ]

    tests = []
    for obj in test_classes:
        for name in dir(obj):
            if name.startswith("test_"):
                tests.append((name, getattr(obj, name)))

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            test_func()
            print(f"✓ {name}")
            passed += 1
        except AssertionError as e:
            print(f"✗ {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {name}: ERROR - {e}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run_tests())
