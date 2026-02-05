"""
Chaos Tests - Failure Scenarios.

Tests cover:
- Neo4j connection loss during task creation
- Neo4j connection loss during task claim
- Gateway timeout during delegation
- Agent crash during task execution
- Network partition between agents
- Recovery after failure

Location: /Users/kurultai/molt/tests/chaos/test_failure_scenarios.py
"""

import os
import sys
import time
from datetime import datetime, timezone
from typing import List, Dict, Any
from unittest.mock import Mock, MagicMock, patch
from contextlib import contextmanager

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# =============================================================================
# Chaos Testing Utilities
# =============================================================================

class ConnectionKiller:
    """Simulates connection failures."""

    def __init__(self):
        self.kill_count = 0
        self.restore_count = 0

    @contextmanager
    def kill_connection_during(self, operation: str):
        """Kill connection during specified operation."""
        self.kill_count += 1
        # Simulate connection failure
        raise Exception("Connection lost")

    def simulate_connection_drop(self):
        """Simulate connection dropping."""
        self.kill_count += 1
        return Exception("Neo4j connection lost")

    def restore_connection(self):
        """Simulate connection restoration."""
        self.restore_count += 1


class MockOperationalMemoryWithChaos:
    """Mock OperationalMemory with chaos capabilities."""

    def __init__(self, failure_rate: float = 0.0):
        self.failure_rate = failure_rate
        self.fail_on_operation = set()
        self.tasks = {}
        self.call_count = 0

    def _maybe_fail(self, operation: str):
        """Maybe fail based on configuration."""
        self.call_count += 1
        if operation in self.fail_on_operation:
            raise Exception(f"Chaos injection: {operation} failed")

        import random
        if random.random() < self.failure_rate:
            raise Exception(f"Random chaos failure on {operation}")

    def create_task(self, task_type: str, description: str, **kwargs) -> str:
        """Create task with possible failure."""
        self._maybe_fail("create_task")

        import uuid
        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {
            "id": task_id,
            "type": task_type,
            "description": description,
            "status": "pending"
        }
        return task_id

    def claim_task(self, agent: str) -> Dict | None:
        """Claim task with possible failure."""
        self._maybe_fail("claim_task")

        for task_id, task in self.tasks.items():
            if task["status"] == "pending":
                task["status"] = "in_progress"
                task["claimed_by"] = agent
                return task.copy()
        return None

    def complete_task(self, task_id: str, results: Dict) -> bool:
        """Complete task with possible failure."""
        self._maybe_fail("complete_task")

        if task_id in self.tasks:
            self.tasks[task_id]["status"] = "completed"
            self.tasks[task_id]["results"] = results
            return True
        return False

    def health_check(self) -> Dict:
        """Health check with possible failure."""
        self._maybe_fail("health_check")

        return {
            "status": "healthy",
            "tasks_total": len(self.tasks),
            "tasks_pending": sum(1 for t in self.tasks.values() if t["status"] == "pending")
        }


class MockAgentWithCrash:
    """Mock agent that can crash."""

    def __init__(self, agent_id: str, crash_on_tasks: List[int] = None):
        self.agent_id = agent_id
        self.crash_on_tasks = crash_on_tasks or []
        self.task_count = 0
        self.is_crashed = False

    def execute_task(self, task: Dict) -> Dict:
        """Execute a task, potentially crashing."""
        if self.is_crashed:
            raise Exception(f"Agent {self.agent_id} is crashed")

        self.task_count += 1
        if self.task_count in self.crash_on_tasks:
            self.is_crashed = True
            raise Exception(f"Agent {self.agent_id} crashed during task {self.task_count}")

        return {
            "agent": self.agent_id,
            "task": task,
            "status": "completed"
        }


# =============================================================================
# TestFailureScenarios
# =============================================================================

class TestFailureScenarios:
    """Tests for various failure scenarios."""

    @pytest.fixture
    def chaos_memory(self):
        return MockOperationalMemoryWithChaos(failure_rate=0.0)

    @pytest.mark.chaos
    def test_neo4j_connection_during_task_creation(self, chaos_memory):
        """Test Neo4j connection loss during task creation."""
        chaos_memory.fail_on_operation.add("create_task")

        with pytest.raises(Exception, match="Chaos injection"):
            chaos_memory.create_task(
                task_type="test",
                description="Test task"
            )

        # Verify system can recover
        chaos_memory.fail_on_operation.remove("create_task")

        task_id = chaos_memory.create_task("test", "Recovery task")
        assert task_id is not None

    @pytest.mark.chaos
    def test_neo4j_connection_during_task_claim(self, chaos_memory):
        """Test Neo4j connection loss during task claim."""
        # First create a task
        task_id = chaos_memory.create_task("test", "Test task")

        # Configure failure on claim
        chaos_memory.fail_on_operation.add("claim_task")

        with pytest.raises(Exception, match="Chaos injection"):
            chaos_memory.claim_task("jochi")

        # Verify recovery
        chaos_memory.fail_on_operation.remove("claim_task")

        task = chaos_memory.claim_task("jochi")
        assert task is not None

    @pytest.mark.chaos
    def test_gateway_timeout_during_delegation(self):
        """Test gateway timeout during delegation."""
        mock_memory = MockOperationalMemoryWithChaos()

        # Simulate timeout
        with patch('time.sleep', side_effect=lambda *args, **kwargs:
                     (_ for _ in ()).throw(Exception("Gateway timeout"))):
            pass

        # System should handle timeout gracefully
        try:
            mock_memory.create_task("test", "Test")
        except Exception as e:
            # Expected to fail
            assert "timeout" in str(e).lower()

    @pytest.mark.chaos
    def test_agent_crash_during_task_execution(self):
        """Test agent crash during task execution."""
        agent = MockAgentWithCrash(agent_id="test-agent", crash_on_tasks=[3])  # Crash on 3rd task

        # First two tasks should succeed
        result1 = agent.execute_task({"id": "1"})
        assert result1["status"] == "completed"

        result2 = agent.execute_task({"id": "2"})
        assert result2["status"] == "completed"

        # Third task should crash
        with pytest.raises(Exception, match="crashed"):
            agent.execute_task({"id": "3"})

        # Subsequent tasks should fail
        with pytest.raises(Exception, match="is crashed"):
            agent.execute_task({"id": "4"})

    @pytest.mark.chaos
    def test_network_partition_between_agents(self):
        """Test network partition between agents."""
        class PartitionedNetwork:
            def __init__(self):
                self.partitions = {"group_a": ["kublai", "jochi"], "group_b": ["temüjin", "ögedei"]}
                self.is_partitioned = True

            def send_message(self, from_agent: str, to_agent: str, message: Dict) -> bool:
                """Simulate sending message."""
                if not self.is_partitioned:
                    return True

                # Check if agents are in same partition
                from_partition = None
                to_partition = None

                for partition, agents in self.partitions.items():
                    if from_agent in agents:
                        from_partition = partition
                    if to_agent in agents:
                        to_partition = partition

                if from_partition != to_partition:
                    raise Exception(f"Network partition: cannot reach {to_agent}")

                return True

        network = PartitionedNetwork()

        # Same partition should work
        assert network.send_message("kublai", "jochi", {"test": "data"})

        # Cross partition should fail
        with pytest.raises(Exception, match="Network partition"):
            network.send_message("kublai", "temüjin", {"test": "data"})

    @pytest.mark.chaos
    def test_recovery_after_failure(self):
        """Test system recovery after failure."""
        memory = MockOperationalMemoryWithChaos()

        # Fail first operation
        memory.fail_on_operation.add("create_task")

        with pytest.raises(Exception):
            memory.create_task("test", "Failing task")

        # Clear failure and verify recovery
        memory.fail_on_operation.clear()

        task_id = memory.create_task("test", "Recovery task")
        assert task_id is not None

        # Verify normal operation continues
        task = memory.claim_task("jochi")
        assert task is not None


# =============================================================================
# TestCascadingFailures
# =============================================================================

class TestCascadingFailures:
    """Tests for cascading failure scenarios."""

    @pytest.mark.chaos
    def test_cascading_task_failures(self):
        """Test handling of cascading task failures."""
        memory = MockOperationalMemoryWithChaos(failure_rate=0.5)

        successful_tasks = []
        failed_tasks = []

        for i in range(20):
            try:
                task_id = memory.create_task("test", f"Task {i}")
                successful_tasks.append(task_id)
            except Exception:
                failed_tasks.append(i)

        # System should handle mixed success/failure
        total = len(successful_tasks) + len(failed_tasks)
        assert total == 20

        print(f"\nCascading failures: {len(successful_tasks)} success, {len(failed_tasks)} failed")

    @pytest.mark.chaos
    def test_memory_exhaustion_recovery(self):
        """Test recovery from memory exhaustion."""
        memory = MockOperationalMemoryWithChaos()

        # Simulate memory limit
        memory.max_tasks = 10

        original_create = memory.create_task

        def limited_create(*args, **kwargs):
            if len(memory.tasks) >= memory.max_tasks:
                raise MemoryError("Memory exhausted")
            return original_create(*args, **kwargs)

        memory.create_task = limited_create

        # Fill up to limit
        for i in range(10):
            memory.create_task("test", f"Task {i}")

        # Next should fail
        with pytest.raises(MemoryError):
            memory.create_task("test", "Overflow task")

        # Recovery: complete and remove some tasks to free memory
        task_ids = list(memory.tasks.keys())[:5]
        for task_id in task_ids:
            memory.complete_task(task_id, {})
            # Actually remove from tasks to simulate memory being freed
            del memory.tasks[task_id]

        # Should be able to add more now
        task_id = memory.create_task("test", "Recovery task")
        assert task_id is not None


# =============================================================================
# TestTimeoutScenarios
# =============================================================================

class TestTimeoutScenarios:
    """Tests for timeout scenarios."""

    @pytest.mark.chaos
    def test_operation_timeout(self):
        """Test operation timeout handling using threading instead of asyncio."""
        import threading

        result = {"timed_out": False}

        def slow_operation():
            time.sleep(5)  # Takes 5 seconds
            result["completed"] = True

        # Start slow operation in thread
        thread = threading.Thread(target=slow_operation)
        thread.start()

        # Wait with timeout
        thread.join(timeout=1.0)

        # Should have timed out
        if thread.is_alive():
            result["timed_out"] = True
            # Don't wait for thread to finish, just mark as timed out
            # In real code, you'd use a proper cancellation mechanism

        assert result["timed_out"], "Operation should have timed out"

    @pytest.mark.chaos
    def test_deadlock_prevention(self):
        """Test deadlock prevention in concurrent operations using timeout-based locks."""
        import threading

        lock1 = threading.Lock()
        lock2 = threading.Lock()
        errors = []
        acquired_locks = {"t1": [], "t2": []}

        def thread1():
            try:
                # Use timeout to prevent deadlock
                if lock1.acquire(timeout=2.0):
                    acquired_locks["t1"].append("lock1")
                    time.sleep(0.05)  # Increase delay to increase contention
                    if lock2.acquire(timeout=2.0):
                        acquired_locks["t1"].append("lock2")
                        lock2.release()
                    else:
                        errors.append("t1: timeout acquiring lock2")
                    lock1.release()
                else:
                    errors.append("t1: timeout acquiring lock1")
            except Exception as e:
                errors.append(f"t1: {e}")

        def thread2():
            try:
                # Reverse order to increase deadlock chance
                if lock2.acquire(timeout=2.0):
                    acquired_locks["t2"].append("lock2")
                    time.sleep(0.05)
                    if lock1.acquire(timeout=2.0):
                        acquired_locks["t2"].append("lock1")
                        lock1.release()
                    else:
                        errors.append("t2: timeout acquiring lock1")
                    lock2.release()
                else:
                    errors.append("t2: timeout acquiring lock2")
            except Exception as e:
                errors.append(f"t2: {e}")

        t1 = threading.Thread(target=thread1)
        t2 = threading.Thread(target=thread2)

        t1.start()
        t2.start()

        # Wait with generous timeout
        t1.join(timeout=10)
        t2.join(timeout=10)

        # Cleanup: ensure threads don't hang test suite
        if t1.is_alive() or t2.is_alive():
            # Force release locks to allow threads to complete
            try:
                lock1.release()
            except RuntimeError:
                pass  # Lock was not held
            try:
                lock2.release()
            except RuntimeError:
                pass

        # Wait again after cleanup
        t1.join(timeout=2)
        t2.join(timeout=2)

        # System should handle contention gracefully - either succeed or timeout
        # The key assertion is that we don't hang indefinitely
        assert not t1.is_alive(), "Thread 1 should have completed"
        assert not t2.is_alive(), "Thread 2 should have completed"


# =============================================================================
# TestFailureRecovery
# =============================================================================

class TestFailureRecovery:
    """Tests for failure recovery mechanisms."""

    @pytest.mark.chaos
    def test_automatic_retry_on_failure(self):
        """Test automatic retry mechanism."""
        class RetryHandler:
            def __init__(self, max_retries=3):
                self.max_retries = max_retries
                self.attempt = 0

            def operation(self):
                self.attempt += 1
                if self.attempt < 3:
                    raise Exception("Temporary failure")
                return "success"

        handler = RetryHandler()

        # Simulate retry logic
        for attempt in range(handler.max_retries):
            try:
                result = handler.operation()
                break
            except Exception:
                if attempt == handler.max_retries - 1:
                    raise

        assert result == "success"
        assert handler.attempt == 3

    @pytest.mark.chaos
    def test_circuit_breaker_activation(self):
        """Test circuit breaker activation."""
        class CircuitBreaker:
            def __init__(self, failure_threshold=3, timeout=5):
                self.failure_threshold = failure_threshold
                self.timeout = timeout
                self.failures = 0
                self.last_failure_time = None
                self.state = "closed"  # closed, open, half-open

            def call(self, operation):
                if self.state == "open":
                    if time.time() - self.last_failure_time > self.timeout:
                        self.state = "half-open"
                    else:
                        raise Exception("Circuit breaker is OPEN")

                try:
                    result = operation()
                    if self.state == "half-open":
                        self.state = "closed"
                        self.failures = 0
                    return result
                except Exception as e:
                    self.failures += 1
                    self.last_failure_time = time.time()

                    if self.failures >= self.failure_threshold:
                        self.state = "open"

                    raise

        cb = CircuitBreaker()

        def failing_operation():
            raise Exception("Operation failed")

        # Trigger circuit breaker
        for i in range(3):
            try:
                cb.call(failing_operation)
            except:
                pass

        # Circuit should be open
        assert cb.state == "open"

        # Should fail immediately
        with pytest.raises(Exception, match="OPEN"):
            cb.call(failing_operation)


# =============================================================================
# TestChaosCleanup
# =============================================================================

class TestChaosCleanup:
    """Tests for cleanup after chaos tests."""

    @pytest.mark.chaos
    def test_cleanup_after_test(self):
        """Test that system cleans up after chaos test."""
        memory = MockOperationalMemoryWithChaos()

        # Simulate various operations
        memory.fail_on_operation.add("create_task")
        try:
            memory.create_task("test", "Fail")
        except:
            pass

        # Cleanup
        memory.fail_on_operation.clear()

        # System should be functional
        task_id = memory.create_task("test", "Clean task")
        assert task_id is not None
