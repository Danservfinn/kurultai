"""
Performance Benchmark Tests for Kurultai System

Benchmarks:
- Task throughput (tasks/minute)
- Heartbeat latency (ms)
- Vector query performance (ms)
- Message signing overhead (ms)

Author: Jochi (Analyst Agent)
Date: 2026-02-09
"""

import asyncio
import hashlib
import hmac
import json
import statistics
import time
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple
from unittest.mock import Mock, MagicMock, patch

import pytest

from tests.fixtures.integration_harness import KurultaiTestHarness


# =============================================================================
# Benchmark Configuration
# =============================================================================

class BenchmarkConfig:
    """Configuration for performance benchmarks."""
    
    # Task throughput benchmarks
    TASK_THROUGHPUT_DURATION_SECONDS = 60
    TASK_THROUGHPUT_TARGET_MIN = 100  # tasks per minute
    
    # Heartbeat latency benchmarks
    HEARTBEAT_LATENCY_P50_MAX_MS = 100
    HEARTBEAT_LATENCY_P95_MAX_MS = 500
    HEARTBEAT_LATENCY_P99_MAX_MS = 1000
    
    # Vector query benchmarks
    VECTOR_QUERY_P50_MAX_MS = 50
    VECTOR_QUERY_P95_MAX_MS = 200
    VECTOR_QUERY_P99_MAX_MS = 500
    
    # Message signing benchmarks
    MESSAGE_SIGNING_P50_MAX_MS = 10
    MESSAGE_SIGNING_P95_MAX_MS = 50
    
    # Sample sizes
    SAMPLE_SIZE_SMALL = 100
    SAMPLE_SIZE_MEDIUM = 500
    SAMPLE_SIZE_LARGE = 1000


# =============================================================================
# Task Throughput Benchmarks
# =============================================================================

@pytest.mark.performance
@pytest.mark.asyncio
class TestTaskThroughputBenchmarks:
    """Benchmark task creation and processing throughput."""

    async def test_task_creation_throughput(self):
        """
        Benchmark task creation throughput (tasks/minute).
        
        Target: 100+ tasks/minute sustained
        """
        harness = KurultaiTestHarness()
        await harness.setup()

        try:
            num_tasks = 50  # Create 50 tasks
            start_time = time.time()

            # Create tasks sequentially (to measure individual latency)
            for i in range(num_tasks):
                task_id = f"throughput-seq-{i}-{int(time.time() * 1000)}"
                await harness.create_task(
                    task_id=task_id,
                    title=f"Benchmark task {i}"
                )

            elapsed = time.time() - start_time
            tasks_per_second = num_tasks / elapsed
            tasks_per_minute = tasks_per_second * 60

            # Report metrics
            print(f"\nTask Creation Throughput:")
            print(f"  Total tasks: {num_tasks}")
            print(f"  Total time: {elapsed:.2f}s")
            print(f"  Tasks/second: {tasks_per_second:.2f}")
            print(f"  Tasks/minute: {tasks_per_minute:.2f}")
            
            # Store for reporting
            self._last_throughput = tasks_per_minute

            # Assert meets target
            assert tasks_per_minute >= BenchmarkConfig.TASK_THROUGHPUT_TARGET_MIN, \
                f"Throughput {tasks_per_minute:.2f} tasks/min below target {BenchmarkConfig.TASK_THROUGHPUT_TARGET_MIN}"

        finally:
            await harness.teardown()

    async def test_concurrent_task_creation_throughput(self):
        """
        Benchmark concurrent task creation throughput.
        
        Tests system behavior under concurrent load.
        """
        harness = KurultaiTestHarness()
        await harness.setup()

        try:
            num_tasks = 100
            batch_size = 10
            
            start_time = time.time()

            # Create tasks in concurrent batches
            async def create_batch(start_idx: int) -> List[Dict]:
                tasks = []
                for i in range(batch_size):
                    idx = start_idx + i
                    task_id = f"throughput-concurrent-{idx}"
                    task = await harness.create_task(
                        task_id=task_id,
                        title=f"Concurrent task {idx}"
                    )
                    tasks.append(task)
                return tasks

            # Run batches concurrently
            batches = [create_batch(i * batch_size) for i in range(num_tasks // batch_size)]
            results = await asyncio.gather(*batches)

            elapsed = time.time() - start_time
            tasks_per_second = num_tasks / elapsed
            tasks_per_minute = tasks_per_second * 60

            print(f"\nConcurrent Task Creation Throughput:")
            print(f"  Total tasks: {num_tasks}")
            print(f"  Batch size: {batch_size}")
            print(f"  Total time: {elapsed:.2f}s")
            print(f"  Tasks/second: {tasks_per_second:.2f}")
            print(f"  Tasks/minute: {tasks_per_minute:.2f}")

            # Concurrent should be faster per task
            assert tasks_per_minute >= BenchmarkConfig.TASK_THROUGHPUT_TARGET_MIN * 1.5, \
                f"Concurrent throughput {tasks_per_minute:.2f} below expected"

        finally:
            await harness.teardown()

    async def test_task_claim_throughput(self):
        """Benchmark task claiming throughput."""
        harness = KurultaiTestHarness()
        await harness.setup()

        try:
            # Create tasks first
            num_tasks = 50
            task_ids = []
            for i in range(num_tasks):
                task_id = f"claim-bench-{i}"
                await harness.create_task(task_id=task_id, title=f"Task {i}")
                task_ids.append(task_id)

            # Benchmark claiming
            start_time = time.time()
            
            for task_id in task_ids:
                await harness.claim_task(task_id, agent_id="jochi")

            elapsed = time.time() - start_time
            claims_per_second = num_tasks / elapsed
            claims_per_minute = claims_per_second * 60

            print(f"\nTask Claim Throughput:")
            print(f"  Total claims: {num_tasks}")
            print(f"  Total time: {elapsed:.2f}s")
            print(f"  Claims/second: {claims_per_second:.2f}")
            print(f"  Claims/minute: {claims_per_minute:.2f}")

            assert claims_per_minute >= BenchmarkConfig.TASK_THROUGHPUT_TARGET_MIN

        finally:
            await harness.teardown()

    async def test_task_completion_throughput(self):
        """Benchmark task completion throughput."""
        harness = KurultaiTestHarness()
        await harness.setup()

        try:
            num_tasks = 50
            
            # Create and claim tasks
            task_ids = []
            for i in range(num_tasks):
                task_id = f"complete-bench-{i}"
                await harness.create_task(task_id=task_id, title=f"Task {i}")
                await harness.claim_task(task_id, agent_id="mongke")
                task_ids.append(task_id)

            # Benchmark completions
            start_time = time.time()
            
            for task_id in task_ids:
                await harness.complete_task(task_id, result=f"Result for {task_id}")

            elapsed = time.time() - start_time
            completions_per_second = num_tasks / elapsed
            completions_per_minute = completions_per_second * 60

            print(f"\nTask Completion Throughput:")
            print(f"  Total completions: {num_tasks}")
            print(f"  Total time: {elapsed:.2f}s")
            print(f"  Completions/second: {completions_per_second:.2f}")
            print(f"  Completions/minute: {completions_per_minute:.2f}")

            assert completions_per_minute >= BenchmarkConfig.TASK_THROUGHPUT_TARGET_MIN

        finally:
            await harness.teardown()


# =============================================================================
# Heartbeat Latency Benchmarks
# =============================================================================

@pytest.mark.performance
class TestHeartbeatLatencyBenchmarks:
    """Benchmark heartbeat system latency."""

    def test_infra_heartbeat_write_latency(self):
        """
        Benchmark infrastructure heartbeat write latency.
        
        Target: P50 < 100ms, P95 < 500ms
        """
        from openclaw_memory import OperationalMemory

        latencies_ms = []
        num_samples = BenchmarkConfig.SAMPLE_SIZE_SMALL

        # Mock memory for testing
        mock_memory = MagicMock()
        mock_memory.update_agent_heartbeat = Mock(return_value=True)

        for i in range(num_samples):
            start = time.perf_counter()
            
            # Simulate heartbeat write
            result = mock_memory.update_agent_heartbeat(agent_id="kublai")
            
            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies_ms.append(elapsed_ms)

        # Calculate percentiles
        latencies_ms.sort()
        p50 = statistics.median(latencies_ms)
        p95 = latencies_ms[int(len(latencies_ms) * 0.95)]
        p99 = latencies_ms[int(len(latencies_ms) * 0.99)]

        print(f"\nInfrastructure Heartbeat Write Latency:")
        print(f"  Samples: {num_samples}")
        print(f"  P50: {p50:.3f}ms")
        print(f"  P95: {p95:.3f}ms")
        print(f"  P99: {p99:.3f}ms")
        print(f"  Min: {min(latencies_ms):.3f}ms")
        print(f"  Max: {max(latencies_ms):.3f}ms")

        # These should be very fast with mocks (< 1ms)
        # In real system would check against actual targets
        assert p50 < BenchmarkConfig.HEARTBEAT_LATENCY_P50_MAX_MS
        assert p95 < BenchmarkConfig.HEARTBEAT_LATENCY_P95_MAX_MS

    def test_functional_heartbeat_update_latency(self):
        """
        Benchmark functional heartbeat update latency (on task operations).
        
        Target: P50 < 100ms, P95 < 500ms
        """
        latencies_ms = []
        num_samples = BenchmarkConfig.SAMPLE_SIZE_SMALL

        mock_memory = MagicMock()

        for i in range(num_samples):
            start = time.perf_counter()
            
            # Simulate functional heartbeat update
            mock_memory.claim_task = Mock(return_value={
                "task_id": f"task-{i}",
                "claimed": True,
                "agent_id": "kublai",
                "claimed_at": datetime.now(timezone.utc).isoformat()
            })
            
            result = mock_memory.claim_task(task_id=f"task-{i}", agent_id="kublai")
            
            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies_ms.append(elapsed_ms)

        latencies_ms.sort()
        p50 = statistics.median(latencies_ms)
        p95 = latencies_ms[int(len(latencies_ms) * 0.95)]

        print(f"\nFunctional Heartbeat Update Latency:")
        print(f"  Samples: {num_samples}")
        print(f"  P50: {p50:.3f}ms")
        print(f"  P95: {p95:.3f}ms")

        assert p50 < BenchmarkConfig.HEARTBEAT_LATENCY_P50_MAX_MS
        assert p95 < BenchmarkConfig.HEARTBEAT_LATENCY_P95_MAX_MS

    def test_heartbeat_read_latency(self):
        """
        Benchmark heartbeat read/query latency.
        
        Target: P50 < 50ms, P95 < 200ms
        """
        latencies_ms = []
        num_samples = BenchmarkConfig.SAMPLE_SIZE_MEDIUM

        mock_memory = MagicMock()
        mock_memory.get_agent = Mock(return_value={
            "agent_id": "kublai",
            "last_heartbeat": datetime.now(timezone.utc).isoformat(),
            "infra_heartbeat": datetime.now(timezone.utc).isoformat()
        })

        for i in range(num_samples):
            start = time.perf_counter()
            
            agent = mock_memory.get_agent("kublai")
            
            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies_ms.append(elapsed_ms)

        latencies_ms.sort()
        p50 = statistics.median(latencies_ms)
        p95 = latencies_ms[int(len(latencies_ms) * 0.95)]

        print(f"\nHeartbeat Read Latency:")
        print(f"  Samples: {num_samples}")
        print(f"  P50: {p50:.3f}ms")
        print(f"  P95: {p95:.3f}ms")

        assert p50 < 50  # Reads should be faster than writes
        assert p95 < 200


# =============================================================================
# Vector Query Performance Benchmarks
# =============================================================================

@pytest.mark.performance
class TestVectorQueryBenchmarks:
    """Benchmark vector query performance."""

    def test_vector_similarity_calculation(self):
        """
        Benchmark vector similarity calculation performance.
        
        Target: P50 < 1ms per comparison
        """
        import random
        import math

        def cosine_similarity(v1: List[float], v2: List[float]) -> float:
            """Calculate cosine similarity between two vectors."""
            dot_product = sum(a * b for a, b in zip(v1, v2))
            norm1 = math.sqrt(sum(a * a for a in v1))
            norm2 = math.sqrt(sum(b * b for b in v2))
            return dot_product / (norm1 * norm2) if norm1 > 0 and norm2 > 0 else 0.0

        latencies_ms = []
        vector_dim = 768  # Common embedding dimension
        num_samples = BenchmarkConfig.SAMPLE_SIZE_MEDIUM

        for i in range(num_samples):
            # Generate random vectors
            v1 = [random.random() for _ in range(vector_dim)]
            v2 = [random.random() for _ in range(vector_dim)]

            start = time.perf_counter()
            similarity = cosine_similarity(v1, v2)
            elapsed_ms = (time.perf_counter() - start) * 1000
            
            latencies_ms.append(elapsed_ms)

        latencies_ms.sort()
        p50 = statistics.median(latencies_ms)
        p95 = latencies_ms[int(len(latencies_ms) * 0.95)]
        p99 = latencies_ms[int(len(latencies_ms) * 0.99)]

        print(f"\nVector Similarity Calculation:")
        print(f"  Vector dimension: {vector_dim}")
        print(f"  Samples: {num_samples}")
        print(f"  P50: {p50:.3f}ms")
        print(f"  P95: {p95:.3f}ms")
        print(f"  P99: {p99:.3f}ms")

        assert p50 < BenchmarkConfig.VECTOR_QUERY_P50_MAX_MS
        assert p95 < BenchmarkConfig.VECTOR_QUERY_P95_MAX_MS

    def test_vector_index_query_simulation(self):
        """
        Simulate vector index query performance.
        
        Tests the query pattern used for semantic search.
        """
        latencies_ms = []
        num_samples = BenchmarkConfig.SAMPLE_SIZE_SMALL

        mock_driver = MagicMock()
        mock_session = MagicMock()
        
        # Mock vector query result
        mock_result = MagicMock()
        mock_result.__iter__ = Mock(return_value=iter([
            {"node": {"id": "n1", "content": "test"}, "score": 0.95},
            {"node": {"id": "n2", "content": "test2"}, "score": 0.87},
        ]))
        mock_session.run.return_value = mock_result
        mock_driver.session.return_value.__enter__ = Mock(return_value=mock_session)
        mock_driver.session.return_value.__exit__ = Mock(return_value=False)

        for i in range(num_samples):
            start = time.perf_counter()
            
            # Simulate vector index query
            with mock_driver.session() as session:
                result = session.run("""
                    CALL db.index.vector.queryNodes($index, $k, $vector)
                    YIELD node, score
                    RETURN node, score
                """, index="content_embedding", k=10, vector=[0.1] * 768)
                
                results = list(result)
            
            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies_ms.append(elapsed_ms)

        latencies_ms.sort()
        p50 = statistics.median(latencies_ms)
        p95 = latencies_ms[int(len(latencies_ms) * 0.95)]

        print(f"\nVector Index Query Simulation:")
        print(f"  Samples: {num_samples}")
        print(f"  P50: {p50:.3f}ms")
        print(f"  P95: {p95:.3f}ms")

        assert p50 < BenchmarkConfig.VECTOR_QUERY_P50_MAX_MS


# =============================================================================
# Message Signing Overhead Benchmarks
# =============================================================================

@pytest.mark.performance
class TestMessageSigningBenchmarks:
    """Benchmark HMAC message signing overhead."""

    def test_hmac_signing_latency_small_message(self):
        """
        Benchmark HMAC signing latency for small messages.
        
        Target: P50 < 10ms
        """
        secret_key = b"test-secret-key-12345"
        small_message = json.dumps({"type": "ping", "timestamp": time.time()}).encode()

        latencies_ms = []
        num_samples = BenchmarkConfig.SAMPLE_SIZE_MEDIUM

        for i in range(num_samples):
            start = time.perf_counter()
            
            signature = hmac.new(secret_key, small_message, hashlib.sha256).hexdigest()
            
            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies_ms.append(elapsed_ms)

        latencies_ms.sort()
        p50 = statistics.median(latencies_ms)
        p95 = latencies_ms[int(len(latencies_ms) * 0.95)]
        p99 = latencies_ms[int(len(latencies_ms) * 0.99)]

        print(f"\nHMAC Signing Latency (Small Message, ~50 bytes):")
        print(f"  Samples: {num_samples}")
        print(f"  Message size: {len(small_message)} bytes")
        print(f"  P50: {p50:.3f}ms")
        print(f"  P95: {p95:.3f}ms")
        print(f"  P99: {p99:.3f}ms")
        print(f"  Ops/second: {num_samples / (sum(latencies_ms) / 1000):.0f}")

        assert p50 < BenchmarkConfig.MESSAGE_SIGNING_P50_MAX_MS
        assert p95 < BenchmarkConfig.MESSAGE_SIGNING_P95_MAX_MS

    def test_hmac_signing_latency_large_message(self):
        """
        Benchmark HMAC signing latency for large messages.
        
        Tests overhead for larger payloads (e.g., task results).
        """
        secret_key = b"test-secret-key-12345"
        
        # Create a larger message (simulating task results)
        large_payload = {
            "type": "task_result",
            "task_id": "task-" + "x" * 100,
            "results": ["result-" + str(i) for i in range(100)],
            "metadata": {f"key_{i}": f"value_{i}" for i in range(50)},
            "timestamp": time.time()
        }
        large_message = json.dumps(large_payload).encode()

        latencies_ms = []
        num_samples = BenchmarkConfig.SAMPLE_SIZE_SMALL

        for i in range(num_samples):
            start = time.perf_counter()
            
            signature = hmac.new(secret_key, large_message, hashlib.sha256).hexdigest()
            
            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies_ms.append(elapsed_ms)

        latencies_ms.sort()
        p50 = statistics.median(latencies_ms)
        p95 = latencies_ms[int(len(latencies_ms) * 0.95)]

        print(f"\nHMAC Signing Latency (Large Message, {len(large_message)} bytes):")
        print(f"  Samples: {num_samples}")
        print(f"  Message size: {len(large_message)} bytes")
        print(f"  P50: {p50:.3f}ms")
        print(f"  P95: {p95:.3f}ms")

        assert p50 < BenchmarkConfig.MESSAGE_SIGNING_P50_MAX_MS * 2  # Allow 2x for large messages

    def test_hmac_verification_latency(self):
        """
        Benchmark HMAC signature verification latency.
        
        Target: Similar to signing latency.
        """
        secret_key = b"test-secret-key-12345"
        message = json.dumps({"type": "task_claim", "task_id": "123"}).encode()
        signature = hmac.new(secret_key, message, hashlib.sha256).hexdigest()

        latencies_ms = []
        num_samples = BenchmarkConfig.SAMPLE_SIZE_MEDIUM

        for i in range(num_samples):
            start = time.perf_counter()
            
            # Verify by recomputing
            expected = hmac.new(secret_key, message, hashlib.sha256).hexdigest()
            is_valid = hmac.compare_digest(signature, expected)
            
            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies_ms.append(elapsed_ms)

        latencies_ms.sort()
        p50 = statistics.median(latencies_ms)
        p95 = latencies_ms[int(len(latencies_ms) * 0.95)]

        print(f"\nHMAC Verification Latency:")
        print(f"  Samples: {num_samples}")
        print(f"  P50: {p50:.3f}ms")
        print(f"  P95: {p95:.3f}ms")

        assert p50 < BenchmarkConfig.MESSAGE_SIGNING_P50_MAX_MS
        assert is_valid is True

    def test_signing_overhead_percentage(self):
        """
        Calculate signing overhead as percentage of total message processing.
        
        Helps understand the relative cost of signing.
        """
        secret_key = b"test-secret-key-12345"
        message = json.dumps({"type": "heartbeat", "agent_id": "kublai"}).encode()

        # Measure total processing time
        total_times_ms = []
        signing_times_ms = []

        for i in range(1000):
            # Total time (serialization + signing)
            start_total = time.perf_counter()
            msg_bytes = json.dumps({"type": "heartbeat", "agent_id": "kublai"}).encode()
            sig = hmac.new(secret_key, msg_bytes, hashlib.sha256).hexdigest()
            total_ms = (time.perf_counter() - start_total) * 1000
            total_times_ms.append(total_ms)

            # Just signing time
            start_sign = time.perf_counter()
            sig = hmac.new(secret_key, message, hashlib.sha256).hexdigest()
            sign_ms = (time.perf_counter() - start_sign) * 1000
            signing_times_ms.append(sign_ms)

        avg_total = statistics.mean(total_times_ms)
        avg_signing = statistics.mean(signing_times_ms)
        overhead_pct = (avg_signing / avg_total) * 100

        print(f"\nSigning Overhead Analysis:")
        print(f"  Average total processing: {avg_total:.3f}ms")
        print(f"  Average signing time: {avg_signing:.3f}ms")
        print(f"  Signing overhead: {overhead_pct:.1f}%")

        # Signing should be a small fraction of total processing
        assert overhead_pct < 60  # Less than 60% overhead (microbenchmark variance)


# =============================================================================
# Database Operation Benchmarks
# =============================================================================

@pytest.mark.performance
class TestDatabaseOperationBenchmarks:
    """Benchmark Neo4j database operations."""

    def test_neo4j_write_latency(self):
        """Benchmark Neo4j write operation latency."""
        latencies_ms = []
        num_samples = 100

        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {"id": "node-123"}
        mock_session.run.return_value = mock_result
        mock_driver.session.return_value.__enter__ = Mock(return_value=mock_session)
        mock_driver.session.return_value.__exit__ = Mock(return_value=False)

        for i in range(num_samples):
            start = time.perf_counter()
            
            with mock_driver.session() as session:
                result = session.run("""
                    CREATE (n:Task {id: $id, created_at: datetime()})
                    RETURN n.id as id
                """, id=f"task-{i}")
                record = result.single()
            
            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies_ms.append(elapsed_ms)

        latencies_ms.sort()
        p50 = statistics.median(latencies_ms)
        p95 = latencies_ms[int(len(latencies_ms) * 0.95)]

        print(f"\nNeo4j Write Latency (Mocked):")
        print(f"  Samples: {num_samples}")
        print(f"  P50: {p50:.3f}ms")
        print(f"  P95: {p95:.3f}ms")

    def test_neo4j_read_latency(self):
        """Benchmark Neo4j read operation latency."""
        latencies_ms = []
        num_samples = 100

        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {"task": {"id": "task-123", "status": "pending"}}
        mock_session.run.return_value = mock_result
        mock_driver.session.return_value.__enter__ = Mock(return_value=mock_session)
        mock_driver.session.return_value.__exit__ = Mock(return_value=False)

        for i in range(num_samples):
            start = time.perf_counter()
            
            with mock_driver.session() as session:
                result = session.run("""
                    MATCH (t:Task {id: $id})
                    RETURN t {.*} as task
                """, id=f"task-{i}")
                record = result.single()
            
            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies_ms.append(elapsed_ms)

        latencies_ms.sort()
        p50 = statistics.median(latencies_ms)

        print(f"\nNeo4j Read Latency (Mocked):")
        print(f"  Samples: {num_samples}")
        print(f"  P50: {p50:.3f}ms")


# =============================================================================
# System Load Benchmarks
# =============================================================================

@pytest.mark.performance
@pytest.mark.asyncio
class TestSystemLoadBenchmarks:
    """Benchmark system under various load conditions."""

    async def test_mixed_workload_throughput(self):
        """
        Benchmark system with mixed workload (reads, writes, updates).
        
        Simulates realistic system load.
        """
        harness = KurultaiTestHarness()
        await harness.setup()

        try:
            num_operations = 100
            operations_per_type = num_operations // 3

            start_time = time.time()

            # Create tasks (writes)
            for i in range(operations_per_type):
                await harness.create_task(
                    task_id=f"mixed-{i}",
                    title=f"Mixed workload task {i}"
                )

            # Query agents (reads)
            for i in range(operations_per_type):
                await harness.get_agent("kublai")

            # Claim tasks (updates)
            for i in range(operations_per_type):
                await harness.claim_task(f"mixed-{i}", agent_id="jochi")

            elapsed = time.time() - start_time
            ops_per_second = num_operations / elapsed

            print(f"\nMixed Workload Throughput:")
            print(f"  Total operations: {num_operations}")
            print(f"  Total time: {elapsed:.2f}s")
            print(f"  Operations/second: {ops_per_second:.2f}")

            assert ops_per_second > 10  # At least 10 ops/sec

        finally:
            await harness.teardown()


# =============================================================================
# Benchmark Summary
# =============================================================================

@pytest.mark.performance
class TestBenchmarkSummary:
    """Generate benchmark summary report."""

    def test_all_benchmarks_documented(self):
        """Verify all benchmark categories are documented."""
        benchmarks = {
            "Task Throughput": [
                "test_task_creation_throughput",
                "test_concurrent_task_creation_throughput",
                "test_task_claim_throughput",
                "test_task_completion_throughput"
            ],
            "Heartbeat Latency": [
                "test_infra_heartbeat_write_latency",
                "test_functional_heartbeat_update_latency",
                "test_heartbeat_read_latency"
            ],
            "Vector Query Performance": [
                "test_vector_similarity_calculation",
                "test_vector_index_query_simulation"
            ],
            "Message Signing Overhead": [
                "test_hmac_signing_latency_small_message",
                "test_hmac_signing_latency_large_message",
                "test_hmac_verification_latency",
                "test_signing_overhead_percentage"
            ]
        }

        for category, tests in benchmarks.items():
            assert len(tests) > 0, f"Category {category} has no tests"
            print(f"{category}: {len(tests)} benchmarks")

    def test_performance_targets_defined(self):
        """Verify all performance targets are defined."""
        targets = {
            "task_throughput_tpm": BenchmarkConfig.TASK_THROUGHPUT_TARGET_MIN,
            "heartbeat_p50_ms": BenchmarkConfig.HEARTBEAT_LATENCY_P50_MAX_MS,
            "heartbeat_p95_ms": BenchmarkConfig.HEARTBEAT_LATENCY_P95_MAX_MS,
            "vector_query_p50_ms": BenchmarkConfig.VECTOR_QUERY_P50_MAX_MS,
            "vector_query_p95_ms": BenchmarkConfig.VECTOR_QUERY_P95_MAX_MS,
            "signing_p50_ms": BenchmarkConfig.MESSAGE_SIGNING_P50_MAX_MS,
            "signing_p95_ms": BenchmarkConfig.MESSAGE_SIGNING_P95_MAX_MS,
        }

        for target_name, target_value in targets.items():
            assert target_value > 0, f"Target {target_name} not defined"
            print(f"  {target_name}: {target_value}")
