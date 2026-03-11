#!/usr/bin/env python3
"""
Test suite for evaluation_engine.py

Tests the following scenarios:
1. MERGE: Success rate improvement > 5%
2. MERGE: Duration P95 reduction > 10%
3. DISCARD: Regression > 5%
4. DISCARD: Error rate > 2x baseline
5. CRASH: Experiment failed to complete
6. EDGE: No tasks in experiment window
7. EDGE: Neutral result (no significant change)
"""

import os
import sys
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch, PropertyMock

# Add script directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from evaluation_engine import (
    EvaluationEngine,
    Experiment,
    Decision,
    MetricSnapshot,
    MERGE_THRESHOLD_IMPROVEMENT,
    MERGE_THRESHOLD_DURATION_REDUCTION,
    DISCARD_THRESHOLD_REGRESSION,
    DISCARD_THRESHOLD_ERROR_MULTIPLIER
)


class MockRecord:
    """Mock Neo4j record that supports item access."""
    def __init__(self, **kwargs):
        self._data = kwargs

    def __getitem__(self, key):
        return self._data.get(key)

    def get(self, key, default=None):
        return self._data.get(key, default)


class MockResult:
    """Mock Neo4j result object."""
    def __init__(self, record=None):
        self._record = record

    def single(self):
        return self._record


def create_mock_driver_with_result(record_value):
    """Create a mock Neo4j driver that returns a specific record."""
    mock_driver = Mock()
    mock_session = Mock()
    mock_result = MockResult(record_value)
    mock_session.run.return_value = mock_result
    mock_driver.session.return_value.__enter__ = Mock(return_value=mock_session)
    mock_driver.session.return_value.__exit__ = Mock(return_value=False)
    return mock_driver, mock_session


def test_merge_improvement():
    """Test MERGE decision when success rate improves by > 5%."""
    print("TEST 1: MERGE - Success rate improvement > 5%")

    # Baseline: 80% success rate
    baseline_record = MockRecord(success_rate=0.80)
    mock_driver, mock_session = create_mock_driver_with_result(baseline_record)

    experiment = Experiment(
        id="exp-001",
        agent="temujin",
        hypothesis="Router tuning improves success rate",
        start_time=datetime.now() - timedelta(hours=4),
        end_time=datetime.now()
    )

    with patch('evaluation_engine.get_driver', return_value=mock_driver):
        engine = EvaluationEngine(mock_driver)

        # Mock experiment metrics to return 88% success rate (10% improvement)
        experiment_snapshot = MetricSnapshot(
            timestamp=datetime.now(),
            agent="temujin",
            success_rate=0.88,  # 10% improvement
            total_tasks=50,
            completed_tasks=44,
            failed_tasks=6,
            error_rate=0.12
        )

        with patch.object(engine, 'get_experiment_metric', return_value=experiment_snapshot):
            decision = engine.evaluate(experiment)

    assert decision.status == "merged", f"Expected 'merged', got '{decision.status}'"
    assert decision.improvement_pct > 5.0, f"Expected improvement > 5%, got {decision.improvement_pct}%"
    assert decision.confidence > 0.5, f"Expected confidence > 0.5, got {decision.confidence}"

    print(f"  ✓ Status: {decision.status}")
    print(f"  ✓ Improvement: {decision.improvement_pct:.1f}%")
    print(f"  ✓ Reasoning: {decision.reasoning}")
    print()


def test_merge_duration_reduction():
    """Test MERGE decision when duration P95 reduces by > 10%."""
    print("TEST 2: MERGE - Duration P95 reduction > 10%")

    # Create multiple mock records for different queries
    mock_records = [
        MockRecord(success_rate=0.80),    # get_baseline_metric
        MockRecord(error_rate=0.15),      # get_baseline_error_rate
        MockRecord(p95_duration=500.0)    # get_baseline_duration_p95
    ]
    record_iter = iter(mock_records)

    mock_driver = Mock()
    mock_session = Mock()

    def create_mock_result(*args, **kwargs):
        try:
            return MockResult(next(record_iter))
        except StopIteration:
            return MockResult(success_rate=0.80)

    mock_session.run.side_effect = create_mock_result
    mock_driver.session.return_value.__enter__ = Mock(return_value=mock_session)
    mock_driver.session.return_value.__exit__ = Mock(return_value=False)

    experiment = Experiment(
        id="exp-002",
        agent="mongke",
        hypothesis="Optimization reduces task duration",
        start_time=datetime.now() - timedelta(hours=4),
        end_time=datetime.now()
    )

    with patch('evaluation_engine.get_driver', return_value=mock_driver):
        engine = EvaluationEngine(mock_driver)

        # Mock experiment metrics: duration reduced from 500s to 400s (20% reduction)
        experiment_snapshot = MetricSnapshot(
            timestamp=datetime.now(),
            agent="mongke",
            success_rate=0.82,  # Slight improvement, not enough on its own
            total_tasks=50,
            completed_tasks=41,
            failed_tasks=9,
            error_rate=0.18,
            duration_p95=400.0  # 20% reduction
        )

        with patch.object(engine, 'get_experiment_metric', return_value=experiment_snapshot):
            decision = engine.evaluate(experiment)

    assert decision.status == "merged", f"Expected 'merged', got '{decision.status}'"
    assert "duration" in decision.reasoning.lower(), f"Expected duration in reasoning, got: {decision.reasoning}"

    print(f"  ✓ Status: {decision.status}")
    print(f"  ✓ Reasoning: {decision.reasoning}")
    print()


def test_discard_regression():
    """Test DISCARD decision when success rate regresses by > 5%."""
    print("TEST 3: DISCARD - Regression > 5%")

    baseline_record = MockRecord(success_rate=0.80)
    mock_driver, mock_session = create_mock_driver_with_result(baseline_record)

    experiment = Experiment(
        id="exp-003",
        agent="jochi",
        hypothesis="New security layer",
        start_time=datetime.now() - timedelta(hours=4),
        end_time=datetime.now()
    )

    with patch('evaluation_engine.get_driver', return_value=mock_driver):
        engine = EvaluationEngine(mock_driver)

        # Mock experiment metrics: 72% success rate (10% regression)
        experiment_snapshot = MetricSnapshot(
            timestamp=datetime.now(),
            agent="jochi",
            success_rate=0.72,  # 10% regression
            total_tasks=50,
            completed_tasks=36,
            failed_tasks=14,
            error_rate=0.28
        )

        with patch.object(engine, 'get_experiment_metric', return_value=experiment_snapshot):
            decision = engine.evaluate(experiment)

    assert decision.status == "discarded", f"Expected 'discarded', got '{decision.status}'"
    assert decision.improvement_pct < 0, f"Expected negative improvement, got {decision.improvement_pct}%"
    assert "regressed" in decision.reasoning.lower(), f"Expected 'regressed' in reasoning"

    print(f"  ✓ Status: {decision.status}")
    print(f"  ✓ Improvement: {decision.improvement_pct:.1f}%")
    print(f"  ✓ Reasoning: {decision.reasoning}")
    print()


def test_discard_error_spike():
    """Test DISCARD decision when error rate > 2x baseline."""
    print("TEST 4: DISCARD - Error rate > 2x baseline")

    # Baseline: 10% error rate
    mock_records = [
        MockRecord(success_rate=0.80),    # get_baseline_metric
        MockRecord(error_rate=0.10),      # get_baseline_error_rate
        MockRecord(p95_duration=300.0)    # get_baseline_duration_p95 (also queried)
    ]
    record_iter = iter(mock_records)

    mock_driver = Mock()
    mock_session = Mock()

    def create_mock_result(*args, **kwargs):
        try:
            return MockResult(next(record_iter))
        except StopIteration:
            return MockRecord(success_rate=0.80)

    mock_session.run.side_effect = create_mock_result
    mock_driver.session.return_value.__enter__ = Mock(return_value=mock_session)
    mock_driver.session.return_value.__exit__ = Mock(return_value=False)

    experiment = Experiment(
        id="exp-004",
        agent="chagatai",
        hypothesis="Experimental code path",
        start_time=datetime.now() - timedelta(hours=4),
        end_time=datetime.now()
    )

    with patch('evaluation_engine.get_driver', return_value=mock_driver):
        engine = EvaluationEngine(mock_driver)

        # Mock experiment metrics: 82% success (neutral), but 25% error rate (2.5x baseline)
        experiment_snapshot = MetricSnapshot(
            timestamp=datetime.now(),
            agent="chagatai",
            success_rate=0.82,  # Slight improvement
            total_tasks=50,
            completed_tasks=41,
            failed_tasks=9,
            error_rate=0.25  # 2.5x baseline
        )

        with patch.object(engine, 'get_experiment_metric', return_value=experiment_snapshot):
            decision = engine.evaluate(experiment)

    assert decision.status == "discarded", f"Expected 'discarded', got '{decision.status}'"
    assert "error rate" in decision.reasoning.lower(), f"Expected 'error rate' in reasoning"

    print(f"  ✓ Status: {decision.status}")
    print(f"  ✓ Reasoning: {decision.reasoning}")
    print()


def test_crash_incomplete():
    """Test CRASH decision when experiment fails to complete."""
    print("TEST 5: CRASH - Experiment failed to complete")

    baseline_record = MockRecord(success_rate=0.80)
    mock_driver, mock_session = create_mock_driver_with_result(baseline_record)

    # Experiment with crashed status
    experiment = Experiment(
        id="exp-005",
        agent="ogedei",
        hypothesis="Infrastructure change",
        start_time=datetime.now() - timedelta(hours=4),
        end_time=None,  # Never completed
        status="crashed"
    )

    with patch('evaluation_engine.get_driver', return_value=mock_driver):
        engine = EvaluationEngine(mock_driver)
        decision = engine.evaluate(experiment)

    assert decision.status == "crashed", f"Expected 'crashed', got '{decision.status}'"
    assert decision.confidence == 1.0, f"Expected confidence 1.0 for crash, got {decision.confidence}"

    print(f"  ✓ Status: {decision.status}")
    print(f"  ✓ Reasoning: {decision.reasoning}")
    print()


def test_edge_no_tasks():
    """Test DISCARD decision when no tasks in experiment window."""
    print("TEST 6: EDGE - No tasks in experiment window")

    baseline_record = MockRecord(success_rate=0.80)
    mock_driver, mock_session = create_mock_driver_with_result(baseline_record)

    experiment = Experiment(
        id="exp-006",
        agent="tolui",
        hypothesis="Quiet period test",
        start_time=datetime.now() - timedelta(hours=4),
        end_time=datetime.now()
    )

    with patch('evaluation_engine.get_driver', return_value=mock_driver):
        engine = EvaluationEngine(mock_driver)

        # Mock experiment metrics: zero tasks
        experiment_snapshot = MetricSnapshot(
            timestamp=datetime.now(),
            agent="tolui",
            success_rate=0.0,
            total_tasks=0,
            completed_tasks=0,
            failed_tasks=0,
            error_rate=0.0
        )

        with patch.object(engine, 'get_experiment_metric', return_value=experiment_snapshot):
            decision = engine.evaluate(experiment)

    assert decision.status == "discarded", f"Expected 'discarded', got '{decision.status}'"
    assert "no tasks" in decision.reasoning.lower(), f"Expected 'no tasks' in reasoning"

    print(f"  ✓ Status: {decision.status}")
    print(f"  ✓ Reasoning: {decision.reasoning}")
    print()


def test_edge_neutral():
    """Test DISCARD decision for neutral result (no significant change)."""
    print("TEST 7: EDGE - Neutral result (no significant change)")

    baseline_record = MockRecord(success_rate=0.80)
    mock_driver, mock_session = create_mock_driver_with_result(baseline_record)

    experiment = Experiment(
        id="exp-007",
        agent="kublai",
        hypothesis="Minimal change",
        start_time=datetime.now() - timedelta(hours=4),
        end_time=datetime.now()
    )

    with patch('evaluation_engine.get_driver', return_value=mock_driver):
        engine = EvaluationEngine(mock_driver)

        # Mock experiment metrics: 81% success rate (1.25% improvement - below threshold)
        experiment_snapshot = MetricSnapshot(
            timestamp=datetime.now(),
            agent="kublai",
            success_rate=0.81,  # 1.25% improvement
            total_tasks=50,
            completed_tasks=40,
            failed_tasks=10,
            error_rate=0.20
        )

        with patch.object(engine, 'get_experiment_metric', return_value=experiment_snapshot):
            decision = engine.evaluate(experiment)

    assert decision.status == "discarded", f"Expected 'discarded', got '{decision.status}'"
    assert ("no significant change" in decision.reasoning.lower() or
            "below merge threshold" in decision.reasoning.lower()), \
        f"Expected neutral reasoning, got: {decision.reasoning}"

    print(f"  ✓ Status: {decision.status}")
    print(f"  ✓ Improvement: {decision.improvement_pct:.1f}%")
    print(f"  ✓ Reasoning: {decision.reasoning}")
    print()


def test_decision_to_dict():
    """Test Decision serialization."""
    print("TEST 8: Decision serialization")

    decision = Decision(
        status="merged",
        improvement_pct=8.3,
        baseline_metric=0.80,
        result_metric=0.8664,
        reasoning="Improved by 8.3% via router tuning",
        confidence=0.75
    )

    decision_dict = decision.to_dict()

    assert decision_dict["status"] == "merged"
    assert decision_dict["improvement_pct"] == 8.3
    assert "evaluated_at" in decision_dict

    print(f"  ✓ Decision serializes correctly")
    print(f"  ✓ Dict keys: {list(decision_dict.keys())}")
    print()


def test_experiment_serialization():
    """Test Experiment to_dict/from_dict roundtrip."""
    print("TEST 9: Experiment serialization")

    experiment = Experiment(
        id="exp-008",
        agent="temujin",
        hypothesis="Test hypothesis",
        start_time=datetime(2026, 3, 8, 10, 0),
        end_time=datetime(2026, 3, 8, 14, 0),
        branch="experiment/temujin/exp-008/test",
        status="completed",
        commit_hash="abc123"
    )

    experiment_dict = experiment.to_dict()
    restored = Experiment.from_dict(experiment_dict)

    assert restored.id == experiment.id
    assert restored.agent == experiment.agent
    assert restored.status == experiment.status

    print(f"  ✓ Experiment serializes and deserializes correctly")
    print()


def run_all_tests():
    """Run all test cases."""
    print("=" * 60)
    print("EVALUATION ENGINE TEST SUITE")
    print("=" * 60)
    print()

    tests = [
        test_merge_improvement,
        test_merge_duration_reduction,
        test_discard_regression,
        test_discard_error_spike,
        test_crash_incomplete,
        test_edge_no_tasks,
        test_edge_neutral,
        test_decision_to_dict,
        test_experiment_serialization
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"  ✗ FAILED: {e}")
            print()
            failed += 1
        except Exception as e:
            print(f"  ✗ ERROR: {e}")
            import traceback
            traceback.print_exc()
            print()
            failed += 1

    print("=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
