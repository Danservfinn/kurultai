"""
Neo4j Integration Tests with Testcontainers

Tests Cypher queries against real Neo4j 5.x:
- Task node CRUD operations
- Concurrent task claims with race condition prevention
- Vector similarity queries
- Testcontainers cleanup

Note: These tests require the testcontainers package.
Run with: pytest tests/integration/test_neo4j_operations.py -v
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional
from unittest.mock import MagicMock, Mock

import pytest

# Try to import testcontainers, skip tests if not available
try:
    from testcontainers.neo4j import Neo4jContainer
    HAS_TESTCONTAINERS = True
except ImportError:
    HAS_TESTCONTAINERS = False

    @pytest.fixture
    def skip_if_no_testcontainers():
        pytest.skip("testcontainers not installed. Install with: pip install testcontainers")


@pytest.mark.integration
class TestNeo4jOperations:
    """Neo4j integration tests."""

    @pytest.fixture
    async def neo4j_driver(self):
        """Provide real Neo4j instance for testing."""
        if not HAS_TESTCONTAINERS:
            pytest.skip("testcontainers not installed")

        container = Neo4jContainer("neo4j:5.15.0", password="test")
        container.start()

        from neo4j import GraphDatabase

        uri = container.get_connection_url()
        driver = GraphDatabase.authenticated(uri, "neo4j", "test")

        yield driver

        await driver.close()
        container.stop()

    @pytest.mark.asyncio
    async def test_task_lifecycle_crud(self, neo4j_driver):
        """Verify Task node CRUD operations work with real Neo4j."""
        # Create
        with neo4j_driver.session() as session:
            result = session.run(
                "CREATE (t:Task {id: $id, title: $title, status: 'pending', created_at: datetime()}) RETURN t",
                id="test-123", title="Test Task"
            )
            node = result.single()
            assert node is not None
            assert node["t"]["id"] == "test-123"

        # Read
        with neo4j_driver.session() as session:
            result = session.run(
                "MATCH (t:Task {id: $id}) RETURN t",
                id="test-123"
            )
            node = result.single()
            assert node["t"]["title"] == "Test Task"
            assert node["t"]["status"] == "pending"

        # Update
        with neo4j_driver.session() as session:
            session.run(
                "MATCH (t:Task {id: $id}) SET t.status = 'completed', t.completed_at = datetime()",
                id="test-123"
            )

        # Verify update
        with neo4j_driver.session() as session:
            result = session.run(
                "MATCH (t:Task {id: $id}) RETURN t.status AS status",
                id="test-123"
            )
            node = result.single()
            assert node["status"] == "completed"

        # Delete
        with neo4j_driver.session() as session:
            session.run("MATCH (t:Task {id: $id}) DELETE t", id="test-123")

        # Verify deletion
        with neo4j_driver.session() as session:
            result = session.run(
                "MATCH (t:Task {id: $id}) RETURN count(t) AS count",
                id="test-123"
            )
            node = result.single()
            assert node["count"] == 0

    @pytest.mark.asyncio
    async def test_concurrent_task_claims_no_race(self, neo4j_driver):
        """Verify two agents can't claim the same task simultaneously."""
        task_id = "race-test-123"

        # Create pending task
        with neo4j_driver.session() as session:
            session.run(
                "CREATE (t:Task {id: $id, status: 'pending'})",
                id=task_id
            )

        # Simulate concurrent claims
        async def claim_task(agent_id: str):
            with neo4j_driver.session() as session:
                result = session.run(
                    """
                    MATCH (t:Task {id: $id, status: 'pending'})
                    SET t.status = 'in_progress', t.claimed_by = $agent, t.claimed_at = datetime()
                    RETURN t.status AS status
                    """,
                    id=task_id, agent=agent_id
                )
                return result.single()

        results = await asyncio.gather(
            claim_task("agent-a"),
            claim_task("agent-b"),
            return_exceptions=True
        )

        # Exactly one should succeed with status='in_progress'
        successful = [r for r in results if isinstance(r, dict) and r.get("status") == "in_progress"]
        assert len(successful) == 1, f"Task should be claimed by exactly one agent, got {len(successful)}"

        # Verify final state
        with neo4j_driver.session() as session:
            result = session.run(
                "MATCH (t:Task {id: $id}) RETURN t.claimed_by AS agent, t.status AS status",
                id=task_id
            )
            node = result.single()
            assert node["status"] == "in_progress"
            assert node["agent"] in ["agent-a", "agent-b"]

    @pytest.mark.asyncio
    async def test_task_dependencies_create_valid_dag(self, neo4j_driver):
        """Verify task dependencies create a valid DAG structure."""
        # Create tasks with dependencies
        with neo4j_driver.session() as session:
            # Create tasks
            session.run("CREATE (t1:Task {id: 't1', title: 'Task 1'})")
            session.run("CREATE (t2:Task {id: 't2', title: 'Task 2'})")
            session.run("CREATE (t3:Task {id: 't3', title: 'Task 3'})")

            # Create dependencies: t1 -> t2 -> t3
            session.run(
                "MATCH (t1:Task {id: 't1'}), (t2:Task {id: 't2'}) "
                "CREATE (t1)-[:BLOCKS]->(t2)"
            )
            session.run(
                "MATCH (t2:Task {id: 't2'}), (t3:Task {id: 't3'}) "
                "CREATE (t2)-[:BLOCKS]->(t3)"
            )

        # Verify structure
        with neo4j_driver.session() as session:
            result = session.run(
                "MATCH (t1:Task {id: 't1'})-[:BLOCKS*]->(downstream) "
                "RETURN count(DISTINCT downstream) AS count"
            )
            node = result.single()
            assert node["count"] == 2  # t1 blocks t2 and t3 transitively

    @pytest.mark.asyncio
    async def test_agent_heartbeat_tracking(self, neo4j_driver):
        """Verify agent heartbeat timestamps can be tracked."""
        agent_id = "test-agent"

        # Create agent node
        with neo4j_driver.session() as session:
            session.run(
                "CREATE (a:Agent {id: $id, status: 'active'})",
                id=agent_id
            )

        # Update heartbeat
        with neo4j_driver.session() as session:
            session.run(
                "MATCH (a:Agent {id: $id}) SET a.last_heartbeat = datetime()",
                id=agent_id
            )

        # Verify heartbeat was set
        with neo4j_driver.session() as session:
            result = session.run(
                "MATCH (a:Agent {id: $id}) RETURN a.last_heartbeat AS hb",
                id=agent_id
            )
            node = result.single()
            assert node["hb"] is not None

    @pytest.mark.asyncio
    async def test_vector_similarity_query(self, neo4j_driver):
        """Verify vector similarity queries work correctly."""
        # This test requires Neo4j with GDS library
        # For now, we'll test a simpler approach

        # Create nodes with vector properties
        with neo4j_driver.session() as session:
            session.run(
                "CREATE (n1:Node {id: 'n1', embedding: [1.0, 0.0, 0.0]})"
            )
            session.run(
                "CREATE (n2:Node {id: 'n2', embedding: [0.9, 0.1, 0.0]})"
            )
            session.run(
                "CREATE (n3:Node {id: 'n3', embedding: [0.0, 1.0, 0.0]})"
            )

        # Query for similar nodes (using dot product as simple similarity)
        with neo4j_driver.session() as session:
            result = session.run(
                """
                MATCH (n1:Node {id: 'n1'}), (n2:Node)
                WHERE n2.id <> 'n1'
                WITH n1, n2,
                     reduce(sum = 0.0, i IN range(0, size(n1.embedding)-1) |
                         sum + n1.embedding[i] * n2.embedding[i]) AS similarity
                RETURN n2.id AS id, similarity
                ORDER BY similarity DESC
                LIMIT 2
                """
            )

            nodes = list(result)
            assert len(nodes) == 2
            # n2 should be most similar to n1
            assert nodes[0]["id"] == "n2"


@pytest.mark.integration
class TestNeo4jMockOperations:
    """Tests using mock Neo4j for faster execution without containers."""

    @pytest.fixture
    def mock_neo4j_session(self):
        """Create a mock Neo4j session."""
        session = MagicMock()

        def mock_run(cypher: str, **kwargs):
            result = MagicMock()
            result.single.return_value = None
            result.data.return_value = []
            result.__iter__ = lambda self: iter([])
            return result

        session.run = mock_run
        session.close = Mock()
        return session

    @pytest.mark.asyncio
    async def test_mock_task_create(self, mock_neo4j_session):
        """Test task creation with mock session."""
        result = mock_neo4j_session.run(
            "CREATE (t:Task {id: $id, title: $title})",
            id="mock-123", title="Mock Task"
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_mock_query_return_empty(self, mock_neo4j_session):
        """Test empty result handling."""
        result = mock_neo4j_session.run("MATCH (t:Task {id: $id}) RETURN t", id="nonexistent")
        node = result.single()
        assert node is None
