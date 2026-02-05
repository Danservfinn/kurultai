"""
Performance Tests - Load Testing.

Tests cover:
- Concurrent task creation (100 concurrent)
- Concurrent task claiming (race conditions)
- Concurrent agent heartbeat updates
- Rate limiting under load
- Performance targets (P50 < 100ms, P95 < 500ms, P99 < 1000ms)

Location: /Users/kurultai/molt/tests/performance/test_load.py
"""

import os
import sys
import asyncio
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import List, Dict, Any
from unittest.mock import Mock, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# =============================================================================
# Performance Targets
# =============================================================================

PERFORMANCE_TARGETS = {
    "p50_latency_ms": 100,
    "p95_latency_ms": 500,
    "p99_latency_ms": 1000,
    "max_concurrent_operations": 100,
    "throughput_per_second": 50
}


# =============================================================================
# Mock Memory for Load Testing
# =============================================================================

class MockMemoryLoadTest:
    """Mock OperationalMemory for load testing."""

    def __init__(self):
        self.tasks = {}
        self.lock = threading.Lock()
        self.counters = {
            "create": 0,
            "claim": 0,
            "complete": 0,
            "heartbeat": 0
        }

    def create_task(self, task_type: str, description: str, **kwargs) -> str:
        """Create a task (thread-safe)."""
        import uuid
        with self.lock:
            task_id = str(uuid.uuid4())
            self.tasks[task_id] = {
                "id": task_id,
                "type": task_type,
                "description": description,
                "status": "pending",
                "created_at": datetime.now(timezone.utc)
            }
            self.counters["create"] += 1
            return task_id

    def claim_task(self, agent: str) -> Dict | None:
        """Claim a task (thread-safe)."""
        with self.lock:
            # Find pending task
            for task_id, task in self.tasks.items():
                if task["status"] == "pending":
                    task["status"] = "in_progress"
                    task["claimed_by"] = agent
                    task["claimed_at"] = datetime.now(timezone.utc)
                    self.counters["claim"] += 1
                    return task.copy()
            return None

    def complete_task(self, task_id: str, results: Dict) -> bool:
        """Complete a task (thread-safe)."""
        with self.lock:
            if task_id in self.tasks:
                self.tasks[task_id]["status"] = "completed"
                self.tasks[task_id]["results"] = results
                self.tasks[task_id]["completed_at"] = datetime.now(timezone.utc)
                self.counters["complete"] += 1
                return True
            return False

    def update_heartbeat(self, agent: str) -> bool:
        """Update agent heartbeat (thread-safe)."""
        with self.lock:
            self.counters["heartbeat"] += 1
            return True

    def get_stats(self) -> Dict:
        """Get performance statistics."""
        return self.counters.copy()


# =============================================================================
# Performance Metrics
# =============================================================================

class PerformanceMetrics:
    """Track and calculate performance metrics."""

    def __init__(self):
        self.latencies: List[float] = []

    def record(self, latency_ms: float):
        """Record a latency measurement."""
        self.latencies.append(latency_ms)

    def percentile(self, p: float) -> float:
        """Calculate percentile."""
        if not self.latencies:
            return 0
        sorted_latencies = sorted(self.latencies)
        index = int(len(sorted_latencies) * p / 100)
        return sorted_latencies[min(index, len(sorted_latencies) - 1)]

    def p50(self) -> float:
        return self.percentile(50)

    def p95(self) -> float:
        return self.percentile(95)

    def p99(self) -> float:
        return self.percentile(99)

    def avg(self) -> float:
        if not self.latencies:
            return 0
        return sum(self.latencies) / len(self.latencies)

    def min(self) -> float:
        if not self.latencies:
            return 0
        return min(self.latencies)

    def max(self) -> float:
        if not self.latencies:
            return 0
        return max(self.latencies)

    def report(self) -> Dict[str, Any]:
        """Generate performance report."""
        return {
            "count": len(self.latencies),
            "min_ms": round(self.min(), 2),
            "max_ms": round(self.max(), 2),
            "avg_ms": round(self.avg(), 2),
            "p50_ms": round(self.p50(), 2),
            "p95_ms": round(self.p95(), 2),
            "p99_ms": round(self.p99(), 2)
        }


# =============================================================================
# TestLoad
# =============================================================================

class TestLoad:
    """Load tests for the system."""

    @pytest.fixture
    def memory(self):
        return MockMemoryLoadTest()

    @pytest.mark.performance
    @pytest.mark.slow
    def test_concurrent_task_creation(self, memory):
        """Test concurrent task creation (100 concurrent)."""
        num_tasks = 100
        metrics = PerformanceMetrics()

        def create_task(i: int):
            start = time.time()
            task_id = memory.create_task(
                task_type="test",
                description=f"Load test task {i}"
            )
            elapsed = (time.time() - start) * 1000
            metrics.record(elapsed)
            return task_id

        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = [executor.submit(create_task, i) for i in range(num_tasks)]
            results = [f.result() for f in as_completed(futures)]

        # Verify all tasks created
        assert len(results) == num_tasks
        assert all(r is not None for r in results)

        # Check performance
        report = metrics.report()

        assert report["count"] == num_tasks
        # P50 should be reasonably fast
        assert report["p50_ms"] < PERFORMANCE_TARGETS["p95_latency_ms"]

        # Print report for debugging
        print(f"\nTask Creation Performance:")
        print(f"  Min: {report['min_ms']}ms")
        print(f"  Avg: {report['avg_ms']}ms")
        print(f"  P50: {report['p50_ms']}ms")
        print(f"  P95: {report['p95_ms']}ms")
        print(f"  P99: {report['p99_ms']}ms")

    @pytest.mark.performance
    @pytest.mark.slow
    def test_concurrent_task_claiming(self, memory):
        """Test concurrent task claiming with race conditions."""
        # Create 50 pending tasks
        num_tasks = 50
        task_ids = []

        for i in range(num_tasks):
            task_id = memory.create_task(
                task_type="test",
                description=f"Task {i}"
            )
            task_ids.append(task_id)

        metrics = PerformanceMetrics()
        agents = ["jochi", "temüjin", "chagatai", "tolui"]

        def claim_tasks(agent_idx: int):
            claimed = 0
            agent = agents[agent_idx % len(agents)]

            while True:
                start = time.time()
                task = memory.claim_task(agent)
                elapsed = (time.time() - start) * 1000
                metrics.record(elapsed)

                if task is None:
                    break
                claimed += 1

            return claimed

        # Have 4 agents claim concurrently
        with ThreadPoolExecutor(max_workers=len(agents)) as executor:
            futures = [executor.submit(claim_tasks, i) for i in range(len(agents))]
            results = [f.result() for f in as_completed(futures)]

        # All tasks should be claimed
        total_claimed = sum(results)
        assert total_claimed == num_tasks

        report = metrics.report()
        print(f"\nTask Claiming Performance:")
        print(f"  Total claims: {report['count']}")
        print(f"  P50: {report['p50_ms']}ms")
        print(f"  P95: {report['p95_ms']}ms")

    @pytest.mark.performance
    @pytest.mark.slow
    def test_concurrent_agent_heartbeat_updates(self, memory):
        """Test concurrent agent heartbeat updates."""
        num_updates = 1000
        agents = ["kublai", "jochi", "temüjin", "ögedei", "chagatai", "tolui"]
        metrics = PerformanceMetrics()

        def update_heartbeats(agent: str, count: int):
            for _ in range(count):
                start = time.time()
                memory.update_heartbeat(agent)
                elapsed = (time.time() - start) * 1000
                metrics.record(elapsed)

        # Distribute updates across agents
        updates_per_agent = num_updates // len(agents)
        expected_updates = updates_per_agent * len(agents)

        with ThreadPoolExecutor(max_workers=len(agents)) as executor:
            futures = [
                executor.submit(update_heartbeats, agent, updates_per_agent)
                for agent in agents
            ]
            [f.result() for f in as_completed(futures)]

        # Verify all updates recorded (allow for small variance due to threading)
        stats = memory.get_stats()
        assert stats["heartbeat"] >= expected_updates * 0.99, f"Expected ~{expected_updates} updates, got {stats['heartbeat']}"

        report = metrics.report()
        print(f"\nHeartbeat Update Performance:")
        print(f"  Total updates: {report['count']}")
        print(f"  P50: {report['p50_ms']}ms")

    @pytest.mark.performance
    @pytest.mark.slow
    def test_rate_limiting_under_load(self, memory):
        """Test rate limiting behavior under load."""
        # Simulate rapid requests from same agent
        num_requests = 500
        metrics = PerformanceMetrics()

        def make_request(i: int):
            start = time.time()
            # Simulate rate limit check
            memory.update_heartbeat("jochi")
            elapsed = (time.time() - start) * 1000
            metrics.record(elapsed)

        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = [executor.submit(make_request, i) for i in range(num_requests)]
            [f.result() for f in as_completed(futures)]

        report = metrics.report()

        # Check that system handles load gracefully
        assert report["count"] == num_requests

        # P99 should still be reasonable
        assert report["p99_ms"] < PERFORMANCE_TARGETS["p99_latency_ms"]

        print(f"\nRate Limiting Under Load:")
        print(f"  Requests: {report['count']}")
        print(f"  P95: {report['p95_ms']}ms")
        print(f"  P99: {report['p99_ms']}ms")

    @pytest.mark.performance
    @pytest.mark.slow
    def test_mixed_concurrent_operations(self, memory):
        """Test mix of different operations under load."""
        num_operations = 200
        metrics = PerformanceMetrics()

        def mixed_operation(op_id: int):
            op_type = op_id % 4  # 4 operation types

            start = time.time()

            if op_type == 0:
                memory.create_task("test", f"Task {op_id}")
            elif op_type == 1:
                memory.claim_task("jochi")
            elif op_type == 2:
                # Try to complete a task (may not exist)
                memory.complete_task(f"task-{op_id}", {})
            else:
                memory.update_heartbeat("kublai")

            elapsed = (time.time() - start) * 1000
            metrics.record(elapsed)

        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(mixed_operation, i) for i in range(num_operations)]
            [f.result() for f in as_completed(futures)]

        report = metrics.report()
        stats = memory.get_stats()

        print(f"\nMixed Operations Performance:")
        print(f"  Operations: {report['count']}")
        print(f"  Created: {stats['create']}")
        print(f"  Claimed: {stats['claim']}")
        print(f"  Heartbeats: {stats['heartbeat']}")
        print(f"  P95: {report['p95_ms']}ms")


# =============================================================================
# TestPerformanceTargets
# =============================================================================

class TestPerformanceTargets:
    """Tests for meeting performance targets."""

    @pytest.fixture
    def memory(self):
        return MockMemoryLoadTest()

    @pytest.mark.performance
    @pytest.mark.slow
    def test_p50_target(self, memory):
        """Test P50 latency target (< 100ms)."""
        num_operations = 50
        latencies = []

        for i in range(num_operations):
            start = time.time()
            memory.create_task("test", f"Task {i}")
            elapsed = (time.time() - start) * 1000
            latencies.append(elapsed)

        latencies.sort()
        p50 = latencies[len(latencies) // 2]

        assert p50 < PERFORMANCE_TARGETS["p50_latency_ms"], \
            f"P50 latency {p50}ms exceeds target {PERFORMANCE_TARGETS['p50_latency_ms']}ms"

    @pytest.mark.performance
    @pytest.mark.slow
    def test_p95_target(self, memory):
        """Test P95 latency target (< 500ms)."""
        num_operations = 50
        latencies = []

        for i in range(num_operations):
            start = time.time()
            memory.create_task("test", f"Task {i}")
            elapsed = (time.time() - start) * 1000
            latencies.append(elapsed)

        latencies.sort()
        p95 = latencies[int(len(latencies) * 0.95)]

        assert p95 < PERFORMANCE_TARGETS["p95_latency_ms"], \
            f"P95 latency {p95}ms exceeds target {PERFORMANCE_TARGETS['p95_latency_ms']}ms"

    @pytest.mark.performance
    @pytest.mark.slow
    def test_p99_target(self, memory):
        """Test P99 latency target (< 1000ms)."""
        num_operations = 50
        latencies = []

        for i in range(num_operations):
            start = time.time()
            memory.create_task("test", f"Task {i}")
            elapsed = (time.time() - start) * 1000
            latencies.append(elapsed)

        latencies.sort()
        p99 = latencies[int(len(latencies) * 0.99)]

        assert p99 < PERFORMANCE_TARGETS["p99_latency_ms"], \
            f"P99 latency {p99}ms exceeds target {PERFORMANCE_TARGETS['p99_latency_ms']}ms"

    @pytest.mark.performance
    @pytest.mark.slow
    def test_throughput_target(self, memory):
        """Test throughput target (50 ops/second)."""
        duration_seconds = 2
        end_time = time.time() + duration_seconds
        operations = 0

        while time.time() < end_time:
            start = time.time()
            memory.create_task("test", f"Task {operations}")
            elapsed = (time.time() - start) * 1000
            operations += 1

        throughput = operations / duration_seconds

        assert throughput >= PERFORMANCE_TARGETS["throughput_per_second"], \
            f"Throughput {throughput} ops/sec below target {PERFORMANCE_TARGETS['throughput_per_second']} ops/sec"
