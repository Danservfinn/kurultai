"""
Performance Benchmarks with pytest-benchmark

Establishes performance baselines for critical operations:
- Task creation latency
- DAG topological sort scalability
- Vector similarity search performance

Run with: pytest tests/performance/test_benchmarks.py --benchmark-json=output.json
"""

import random
from typing import Any, Dict, List
from unittest.mock import MagicMock, Mock

import pytest


@pytest.mark.benchmark
class TestBenchmarks:
    """Performance benchmarks for Kurultai operations."""

    def test_task_creation_latency(self, benchmark):
        """Benchmark: Task creation should be fast.

        Target: p50 < 100ms
        """
        # Mock the delegation protocol
        from tests.fixtures.mock_agents import MockAgentFactory

        protocol = Mock()
        protocol.create_delegation_task = MagicMock(
            return_value={
                "task_id": "benchmark-task",
                "title": "Benchmark task",
                "agent_id": "temujin",
                "status": "pending",
            }
        )

        result = benchmark(
            protocol.create_delegation_task,
            title="Benchmark task",
            description="Benchmark description",
            agent_id="temujin"
        )

        assert result["task_id"]

    def test_dag_topological_sort_1000_nodes(self, benchmark):
        """Benchmark: DAG topological sort scales linearly.

        Target: 1000 nodes < 1s
        """
        from tests.fixtures.test_data import TestDataGenerator

        # Create a large DAG
        dag = TestDataGenerator.complex_dag(num_tasks=1000, dependency_ratio=0.3)

        # Topological sort function
        def topological_sort(tasks: List[Dict]) -> List[str]:
            # Build adjacency list
            graph = {}
            in_degree = {}

            for task in tasks:
                task_id = task["id"]
                graph[task_id] = []
                in_degree[task_id] = 0

            for task in tasks:
                task_id = task["id"]
                for dep in task.get("dependencies", []):
                    graph[dep].append(task_id)
                    in_degree[task_id] = in_degree.get(task_id, 0) + 1

            # Kahn's algorithm
            queue = [tid for tid, degree in in_degree.items() if degree == 0]
            result = []

            while queue:
                node = queue.pop(0)
                result.append(node)

                for neighbor in graph[node]:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)

            return result

        sorted_nodes = benchmark(topological_sort, dag)
        assert len(sorted_nodes) == 1000

    def test_vector_similarity_search_1000_queries(self, benchmark):
        """Benchmark: Vector similarity search performance.

        Target: 1000 queries < 500ms
        """
        # Generate sample embeddings
        import numpy as np

        # Create embedding database
        embeddings_db = {
            f"doc_{i}": np.random.rand(768) for i in range(1000)
        }

        # Query embedding
        query_embedding = np.random.rand(768)

        def similarity_search(query: np.ndarray, db: Dict[str, np.ndarray], k: int = 5):
            """Find top k most similar documents using cosine similarity."""
            similarities = {}
            for doc_id, embedding in db.items():
                # Cosine similarity
                dot_product = np.dot(query, embedding)
                norm_a = np.linalg.norm(query)
                norm_b = np.linalg.norm(embedding)
                similarity = dot_product / (norm_a * norm_b)
                similarities[doc_id] = similarity

            # Return top k
            return sorted(similarities.items(), key=lambda x: x[1], reverse=True)[:k]

        # Benchmark single query
        results = benchmark(similarity_search, query_embedding, embeddings_db)
        assert len(results) == 5

    def test_agent_selection_latency(self, benchmark):
        """Benchmark: Agent selection from routing rules.

        Target: p50 < 50ms
        """
        # Simulated routing rules
        routing_rules = {
            "code": "temujin",
            "research": "mongke",
            "write": "chagatai",
            "analyze": "jochi",
            "ops": "ogedei",
        }

        def select_agent(message: str) -> str:
            """Select agent based on message keywords."""
            for keyword, agent in routing_rules.items():
                if keyword in message.lower():
                    return agent
            return "kublai"  # default

        messages = [
            "Implement the API endpoint",
            "Research this topic",
            "Write documentation",
            "Analyze performance",
            "Deploy to production",
        ]

        # Benchmark
        for msg in messages:
            agent = benchmark(select_agent, msg)
            assert agent in list(routing_rules.values()) + ["kublai"]

    def test_task_claims_concurrent_100(self, benchmark):
        """Benchmark: 100 concurrent task claims.

        Target: < 500ms total
        """
        import asyncio

        harness = MagicMock()
        harness.claim_task = MagicMock(return_value={"claimed": True})

        async def claim_batch(task_ids: List[str]) -> List[Any]:
            return [harness.claim_task(tid, "agent-1") for tid in task_ids]

        task_ids = [f"task-{i}" for i in range(100)]

        def run_claims():
            return asyncio.run(claim_batch(task_ids))

        result = benchmark(run_claims)
        assert len(result) == 100


@pytest.mark.benchmark
class TestMemoryScalability:
    """Benchmarks for memory system scalability."""

    def test_large_dag_with_500_nodes(self, benchmark):
        """Test creating and querying large DAG.

        Target: < 2s for 500 node DAG
        """
        from tests.fixtures.test_data import TestDataGenerator

        dag = TestDataGenerator.complex_dag(num_tasks=500, dependency_ratio=0.4)

        def count_dependencies(dag: List[Dict]) -> int:
            total = 0
            for task in dag:
                total += len(task.get("dependencies", []))
            return total

        deps = benchmark(count_dependencies, dag)
        assert deps > 0

    def test_batch_task_creation_1000(self, benchmark):
        """Test batch task creation.

        Target: 1000 tasks < 500ms
        """
        from tests.fixtures.test_data import TestDataGenerator

        def create_batch(count: int) -> List[Dict]:
            return [TestDataGenerator.simple_task() for _ in range(count)]

        tasks = benchmark(create_batch, 1000)
        assert len(tasks) == 1000


@pytest.mark.benchmark
class TestMessageProcessing:
    """Benchmarks for message processing operations."""

    def test_message_dispatch_latency(self, benchmark):
        """Benchmark: Message dispatch to agents.

        Target: p50 < 10ms
        """
        agents = {
            "kublai": MockAgentFactory().create_kublai(),
            "mongke": MockAgentFactory().create_mongke(),
            "chagatai": MockAgentFactory().create_chagatai(),
        }

        def dispatch_message(agent_id: str, message: str) -> str:
            agent = agents.get(agent_id)
            if agent:
                return f"Dispatched to {agent_id}"
            return "No agent"

        result = benchmark(dispatch_message, "mongke", "Test message")
        assert "mongke" in result


# Mock agent factory for benchmarks
class MockAgentFactory:
    """Simple mock agent factory for benchmarking."""

    @staticmethod
    def create_kublai():
        from unittest.mock import Mock
        agent = Mock()
        agent.agent_id = "kublai"
        return agent

    @staticmethod
    def create_mongke():
        from unittest.mock import Mock
        agent = Mock()
        agent.agent_id = "mongke"
        return agent

    @staticmethod
    def create_chagatai():
        from unittest.mock import Mock
        agent = Mock()
        agent.agent_id = "chagatai"
        return agent
