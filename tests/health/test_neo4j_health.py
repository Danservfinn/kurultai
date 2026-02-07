"""
Neo4j Health Checks

Tests for Neo4j database connectivity and operations:
- Basic connectivity verification
- Cypher query execution
- Node count validation
- Database version check
- Query performance validation
"""

import os
import time
from datetime import datetime, timezone
from typing import Dict, Any
from unittest.mock import MagicMock, patch

import pytest

# Neo4j import with graceful failure
try:
    from neo4j import GraphDatabase, Driver
    HAS_NEO4J = True
except ImportError:
    HAS_NEO4J = False
    Driver = MagicMock


@pytest.fixture
def neo4j_config() -> Dict[str, str]:
    """Neo4j connection configuration from environment."""
    return {
        "uri": os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        "user": os.getenv("NEO4J_USER", "neo4j"),
        "password": os.getenv("NEO4J_PASSWORD", "password"),
    }


@pytest.fixture
def neo4j_driver(neo4j_config: Dict[str, str]) -> Driver:
    """
    Provide a Neo4j driver instance.

    Skip tests if Neo4j is not available.
    """
    if not HAS_NEO4J:
        pytest.skip("neo4j package not installed")

    driver = GraphDatabase.driver(
        neo4j_config["uri"],
        auth=(neo4j_config["user"], neo4j_config["password"]),
        max_connection_lifetime=30,
        max_connection_pool_size=5,
    )

    try:
        driver.verify_connectivity()
        yield driver
    except Exception as e:
        pytest.skip(f"Neo4j not available: {e}")
    finally:
        driver.close()


@pytest.mark.health
@pytest.mark.neo4j
class TestNeo4jConnectivity:
    """Test Neo4j database connectivity."""

    def test_neo4j_basic_connectivity(self, neo4j_driver: Driver):
        """Verify basic Neo4j connectivity can be established."""
        # verify_connectivity is called in fixture, so if we're here, it worked
        assert neo4j_driver is not None

    def test_neo4j_server_info(self, neo4j_driver: Driver):
        """Retrieve and verify Neo4j server information."""
        with neo4j_driver.session() as session:
            result = session.run("CALL dbms.components() YIELD name, versions, edition")
            record = result.single()

            assert record is not None
            assert record["name"] == "Neo4j"
            assert len(record["versions"]) > 0
            assert record["edition"] in ["Enterprise", "Community"]

    def test_neo4j_database_version(self, neo4j_driver: Driver):
        """Retrieve and validate Neo4j database version."""
        with neo4j_driver.session() as session:
            result = session.run(
                "CALL dbms.components() YIELD versions RETURN versions[0] AS version"
            )
            record = result.single()

            assert record is not None
            version_str = record["version"]
            # Version should be in format like "5.15.0"
            parts = version_str.split(".")
            assert len(parts) >= 2
            assert parts[0].isdigit()


@pytest.mark.health
@pytest.mark.neo4j
class TestNeo4jCypherOperations:
    """Test Neo4j Cypher query execution."""

    def test_cypher_simple_ping(self, neo4j_driver: Driver):
        """Verify basic Cypher query execution with ping."""
        with neo4j_driver.session() as session:
            result = session.run("RETURN 1 AS ping")
            record = result.single()

            assert record is not None
            assert record["ping"] == 1

    def test_cypher_parameterized_query(self, neo4j_driver: Driver):
        """Verify parameterized Cypher query execution."""
        with neo4j_driver.session() as session:
            result = session.run(
                "RETURN $value AS result",
                value="test_parameter"
            )
            record = result.single()

            assert record is not None
            assert record["result"] == "test_parameter"

    def test_cypher_datetime_functions(self, neo4j_driver: Driver):
        """Verify Cypher datetime functions work correctly."""
        with neo4j_driver.session() as session:
            result = session.run("RETURN datetime() AS now")
            record = result.single()

            assert record is not None
            now = record["now"]
            # datetime() returns a neo4j.time.DateTime
            assert now is not None


@pytest.mark.health
@pytest.mark.neo4j
class TestNeo4jNodeOperations:
    """Test Neo4j node operations."""

    def test_node_count(self, neo4j_driver: Driver):
        """Count nodes in the database."""
        with neo4j_driver.session() as session:
            result = session.run("MATCH (n) RETURN count(n) AS count")
            record = result.single()

            assert record is not None
            count = record["count"]
            assert isinstance(count, int)
            assert count >= 0

    def test_agent_node_exists(self, neo4j_driver: Driver):
        """Check if Agent nodes exist in the database."""
        with neo4j_driver.session() as session:
            result = session.run(
                "MATCH (a:Agent) RETURN count(a) AS count"
            )
            record = result.single()

            assert record is not None
            # May be 0 if system is new, but should be a valid integer
            assert isinstance(record["count"], int)

    def test_task_node_exists(self, neo4j_driver: Driver):
        """Check if Task nodes exist in the database."""
        with neo4j_driver.session() as session:
            result = session.run(
                "MATCH (t:Task) RETURN count(t) AS count"
            )
            record = result.single()

            assert record is not None
            assert isinstance(record["count"], int)


@pytest.mark.health
@pytest.mark.neo4j
class TestNeo4jPerformance:
    """Test Neo4j query performance."""

    def test_simple_query_performance(self, neo4j_driver: Driver):
        """Verify simple queries complete within acceptable time."""
        start = time.time()
        with neo4j_driver.session() as session:
            session.run("RETURN 1 AS ping").consume()
        elapsed_ms = (time.time() - start) * 1000

        # Simple queries should be very fast (< 100ms)
        assert elapsed_ms < 100, f"Query took {elapsed_ms:.2f}ms, expected < 100ms"

    def test_count_query_performance(self, neo4j_driver: Driver):
        """Verify count queries complete within acceptable time."""
        start = time.time()
        with neo4j_driver.session() as session:
            session.run("MATCH (n) RETURN count(n) AS count").consume()
        elapsed_ms = (time.time() - start) * 1000

        # Count queries should complete in < 1 second
        assert elapsed_ms < 1000, f"Query took {elapsed_ms:.2f}ms, expected < 1000ms"

    def test_agent_query_performance(self, neo4j_driver: Driver):
        """Verify agent-related queries perform well."""
        start = time.time()
        with neo4j_driver.session() as session:
            session.run(
                "MATCH (a:Agent) WHERE a.name IS NOT NULL RETURN a.name LIMIT 10"
            ).consume()
        elapsed_ms = (time.time() - start) * 1000

        # Agent queries should be fast (< 200ms)
        assert elapsed_ms < 200, f"Query took {elapsed_ms:.2f}ms, expected < 200ms"


@pytest.mark.health
@pytest.mark.neo4j
class TestNeo4jConstraints:
    """Test Neo4j database constraints and indexes."""

    def test_list_constraints(self, neo4j_driver: Driver):
        """Verify we can list database constraints."""
        with neo4j_driver.session() as session:
            result = session.run("SHOW CONSTRAINTS")
            # Just verify the query works
            records = list(result)
            # Should return a list (may be empty)
            assert isinstance(records, list)

    def test_list_indexes(self, neo4j_driver: Driver):
        """Verify we can list database indexes."""
        with neo4j_driver.session() as session:
            result = session.run("SHOW INDEXES")
            records = list(result)
            assert isinstance(records, list)


def check_neo4j_health(config: Dict[str, str], timeout_ms: int = 1000) -> Dict[str, Any]:
    """
    Run comprehensive Neo4j health check.

    Args:
        config: Neo4j connection configuration
        timeout_ms: Max acceptable query time in milliseconds

    Returns:
        Health check result with status, latency, and details
    """
    if not HAS_NEO4J:
        return {
            "status": "fail",
            "error": "neo4j package not installed",
            "details": {}
        }

    start = time.time()
    result = {
        "status": "pass",
        "latency_ms": 0,
        "details": {}
    }

    try:
        driver = GraphDatabase.driver(
            config["uri"],
            auth=(config["user"], config["password"]),
            max_connection_lifetime=30
        )

        # Check connectivity
        driver.verify_connectivity()
        result["details"]["connectivity"] = True

        # Check Cypher execution
        with driver.session() as session:
            query_start = time.time()
            cypher_result = session.run("RETURN 1 AS ping")
            cypher_result.single()
            query_latency_ms = (time.time() - query_start) * 1000
            result["details"]["query_latency_ms"] = round(query_latency_ms, 2)
            result["details"]["cypher_executable"] = True

            # Check against threshold
            if query_latency_ms > timeout_ms:
                result["status"] = "warn"
                result["details"]["warning"] = f"Query latency {query_latency_ms:.2f}ms exceeds threshold {timeout_ms}ms"

            # Get node count
            count_result = session.run("MATCH (n) RETURN count(n) AS count")
            result["details"]["node_count"] = count_result.single()["count"]

            # Get database version
            try:
                version_result = session.run(
                    "CALL dbms.components() YIELD versions RETURN versions[0] AS version"
                )
                result["details"]["database_version"] = version_result.single()["version"]
            except Exception:
                result["details"]["database_version"] = "unknown"

        driver.close()

    except Exception as e:
        result["status"] = "fail"
        result["details"]["error"] = str(e)
        result["details"]["connectivity"] = False

    result["latency_ms"] = round((time.time() - start) * 1000)
    return result


@pytest.mark.health
@pytest.mark.neo4j
def test_neo4j_health_check_function(neo4j_config: Dict[str, str]):
    """Test the health check function itself."""
    if not HAS_NEO4J:
        pytest.skip("neo4j package not installed")

    result = check_neo4j_health(neo4j_config)

    assert "status" in result
    assert "latency_ms" in result
    assert "details" in result

    # If Neo4j is available, should pass
    try:
        driver = GraphDatabase.driver(
            neo4j_config["uri"],
            auth=(neo4j_config["user"], neo4j_config["password"])
        )
        driver.verify_connectivity()
        driver.close()
        assert result["status"] in ["pass", "warn"]
    except Exception:
        # If Neo4j is not available, fail is expected
        assert result["status"] == "fail"
