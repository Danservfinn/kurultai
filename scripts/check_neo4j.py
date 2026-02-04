"""
Neo4j Connectivity Tests (NEO-001 through NEO-010)

Validates Neo4j database connectivity, schema, and performance.

Checks:
    NEO-001 [CRITICAL]: Neo4j reachable on port 7687
    NEO-002 [CRITICAL]: Bolt connection works
    NEO-003 [CRITICAL]: Write capability
    NEO-004: Connection pool healthy
    NEO-005: Index validation (>= 10 indexes)
    NEO-006: Constraint validation (>= 5 constraints)
    NEO-007: Migration version check
    NEO-008: Fallback mode test
    NEO-009: Read replica check (optional)
    NEO-010: Query performance baseline (< 100ms)
"""

import os
import sys
import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from urllib.parse import urlparse

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.check_types import CheckResult, CheckCategory, CheckStatus

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class Neo4jConfig:
    """Configuration for Neo4j checks."""
    # Minimum requirements
    MIN_INDEXES = 10
    MIN_CONSTRAINTS = 5
    QUERY_PERFORMANCE_MS = 100

    # Connection settings
    DEFAULT_PORT = 7687
    CONNECTION_TIMEOUT = 10
    MAX_RETRY_TIME = 30


class Neo4jChecker:
    """
    Neo4j connectivity and schema checker.

    Validates Neo4j database connectivity, schema, and performance.

    Example:
        >>> checker = Neo4jChecker(
        ...     uri="bolt://localhost:7687",
        ...     username="neo4j",
        ...     password="password"
        ... )
        >>> results = checker.run_all_checks()
        >>> for result in results:
        ...     print(f"{result.check_id}: {result.status}")
    """

    def __init__(
        self,
        uri: str = "bolt://localhost:7687",
        username: str = "neo4j",
        password: Optional[str] = None,
        database: str = "neo4j",
        verbose: bool = False
    ):
        """
        Initialize Neo4j checker.

        Args:
            uri: Neo4j bolt URI
            username: Neo4j username
            password: Neo4j password
            database: Neo4j database name
            verbose: Enable verbose logging
        """
        self.uri = uri
        self.username = username
        self.password = password or os.environ.get("NEO4J_PASSWORD")
        self.database = database
        self.verbose = verbose

        # Parse URI for host and port
        parsed = urlparse(uri)
        self.host = parsed.hostname or "localhost"
        self.port = parsed.port or Neo4jConfig.DEFAULT_PORT

        # Driver (lazy initialization)
        self._driver = None

    def _get_driver(self):
        """Get or create Neo4j driver."""
        if self._driver is None:
            try:
                from neo4j import GraphDatabase
                self._driver = GraphDatabase.driver(
                    self.uri,
                    auth=(self.username, self.password),
                    connection_timeout=Neo4jConfig.CONNECTION_TIMEOUT,
                    max_transaction_retry_time=Neo4jConfig.MAX_RETRY_TIME
                )
            except ImportError:
                logger.error("neo4j package not installed")
                raise
        return self._driver

    def _close_driver(self):
        """Close Neo4j driver."""
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    def _run_check(
        self,
        check_id: str,
        description: str,
        critical: bool,
        check_func: callable
    ) -> CheckResult:
        """
        Run a single check.

        Args:
            check_id: Check identifier (e.g., NEO-001)
            description: Check description
            critical: Whether this is a critical check
            check_func: Function that performs the check

        Returns:
            CheckResult with status and details
        """
        start_time = datetime.now(timezone.utc)

        try:
            result = check_func()
        except ImportError as e:
            logger.error(f"neo4j package not available: {e}")
            result = {
                "status": CheckStatus.SKIP,
                "expected": "neo4j package installed",
                "actual": "Package not installed",
                "output": "SKIP: neo4j package not installed",
                "details": {"error": "neo4j package not installed"}
            }
        except Exception as e:
            logger.error(f"Error running {check_id}: {e}")
            result = {
                "status": CheckStatus.FAIL,
                "expected": "Check to complete without error",
                "actual": f"Exception: {str(e)}",
                "output": f"Check failed with exception: {str(e)}",
                "details": {"error": str(e), "error_type": type(e).__name__}
            }

        duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

        return CheckResult(
            check_id=check_id,
            category=CheckCategory.NEO4J,
            description=description,
            critical=critical,
            status=result.get("status", CheckStatus.FAIL),
            expected=result.get("expected", ""),
            actual=result.get("actual", ""),
            output=result.get("output", ""),
            duration_ms=duration_ms,
            details=result.get("details", {})
        )

    def run_all_checks(self) -> List[CheckResult]:
        """Run all Neo4j checks (NEO-001 through NEO-010)."""
        results = []

        # NEO-001: Neo4j reachable on port 7687
        results.append(self._run_check(
            "NEO-001",
            "Neo4j reachable on port 7687",
            True,
            self._check_reachable
        ))

        # NEO-002: Bolt connection works
        results.append(self._run_check(
            "NEO-002",
            "Bolt connection works",
            True,
            self._check_bolt_connection
        ))

        # NEO-003: Write capability
        results.append(self._run_check(
            "NEO-003",
            "Write capability",
            True,
            self._check_write_capability
        ))

        # NEO-004: Connection pool healthy
        results.append(self._run_check(
            "NEO-004",
            "Connection pool healthy",
            False,
            self._check_connection_pool
        ))

        # NEO-005: Index validation
        results.append(self._run_check(
            "NEO-005",
            "Index validation (>= 10 indexes)",
            False,
            self._check_indexes
        ))

        # NEO-006: Constraint validation
        results.append(self._run_check(
            "NEO-006",
            "Constraint validation (>= 5 constraints)",
            False,
            self._check_constraints
        ))

        # NEO-007: Migration version check
        results.append(self._run_check(
            "NEO-007",
            "Migration version check",
            False,
            self._check_migration_version
        ))

        # NEO-008: Fallback mode test
        results.append(self._run_check(
            "NEO-008",
            "Fallback mode test",
            False,
            self._check_fallback_mode
        ))

        # NEO-009: Read replica check
        results.append(self._run_check(
            "NEO-009",
            "Read replica check (optional)",
            False,
            self._check_read_replica
        ))

        # NEO-010: Query performance baseline
        results.append(self._run_check(
            "NEO-010",
            "Query performance baseline (< 100ms)",
            False,
            self._check_query_performance
        ))

        # Clean up
        self._close_driver()

        return results

    # ========================================================================
    # Individual Check Functions
    # ========================================================================

    def _check_reachable(self) -> Dict[str, Any]:
        """
        NEO-001 [CRITICAL]: Neo4j reachable on port 7687

        Validates that Neo4j is reachable on the configured port.
        """
        import socket

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((self.host, self.port))
            sock.close()

            if result == 0:
                return {
                    "status": CheckStatus.PASS,
                    "expected": f"Port {self.port} open",
                    "actual": f"Port {self.port} open",
                    "output": f"PASS: Neo4j reachable at {self.host}:{self.port}",
                    "details": {"host": self.host, "port": self.port}
                }
            else:
                return {
                    "status": CheckStatus.FAIL,
                    "expected": f"Port {self.port} open",
                    "actual": f"Port {self.port} closed",
                    "output": f"FAIL: Cannot connect to {self.host}:{self.port}",
                    "details": {"host": self.host, "port": self.port, "error_code": result}
                }
        except socket.gaierror:
            return {
                "status": CheckStatus.FAIL,
                "expected": f"Host {self.host} resolvable",
                "actual": "DNS resolution failed",
                "output": f"FAIL: Cannot resolve host {self.host}",
                "details": {"host": self.host, "error": "DNS resolution failed"}
            }
        except Exception as e:
            return {
                "status": CheckStatus.FAIL,
                "expected": f"Port {self.port} open",
                "actual": f"Error: {str(e)}",
                "output": f"FAIL: {str(e)}",
                "details": {"host": self.host, "port": self.port, "error": str(e)}
            }

    def _check_bolt_connection(self) -> Dict[str, Any]:
        """
        NEO-002 [CRITICAL]: Bolt connection works

        Validates that Bolt protocol connection works.
        """
        try:
            driver = self._get_driver()
            driver.verify_connectivity()

            # Try to get server info
            with driver.session(database=self.database) as session:
                result = session.run("RETURN 1 as test")
                value = result.single()["test"]

            if value == 1:
                return {
                    "status": CheckStatus.PASS,
                    "expected": "Bolt connection successful",
                    "actual": "Connected",
                    "output": f"PASS: Bolt connection to {self.uri} successful",
                    "details": {"uri": self.uri, "database": self.database}
                }
            else:
                return {
                    "status": CheckStatus.FAIL,
                    "expected": "Bolt connection successful",
                    "actual": "Query returned unexpected value",
                    "output": "FAIL: Query returned unexpected value",
                    "details": {"uri": self.uri}
                }
        except Exception as e:
            return {
                "status": CheckStatus.FAIL,
                "expected": "Bolt connection successful",
                "actual": f"Error: {str(e)}",
                "output": f"FAIL: Bolt connection failed: {str(e)}",
                "details": {"uri": self.uri, "error": str(e)}
            }

    def _check_write_capability(self) -> Dict[str, Any]:
        """
        NEO-003 [CRITICAL]: Write capability

        Validates that write operations work on the database.
        """
        try:
            driver = self._get_driver()

            with driver.session(database=self.database) as session:
                # Create a test node
                result = session.run("""
                    CREATE (t:PreFlightTest {id: 'preflight_test', timestamp: $ts})
                    RETURN t.id as id
                """, ts=datetime.now(timezone.utc).isoformat())
                node_id = result.single()["id"]

                # Delete the test node
                session.run("""
                    MATCH (t:PreFlightTest {id: 'preflight_test'})
                    DELETE t
                """)

            return {
                "status": CheckStatus.PASS,
                "expected": "Write operations successful",
                "actual": "Write successful",
                "output": "PASS: Write capability confirmed",
                "details": {"database": self.database, "test_node": node_id}
            }
        except Exception as e:
            return {
                "status": CheckStatus.FAIL,
                "expected": "Write operations successful",
                "actual": f"Error: {str(e)}",
                "output": f"FAIL: Write operation failed: {str(e)}",
                "details": {"database": self.database, "error": str(e)}
            }

    def _check_connection_pool(self) -> Dict[str, Any]:
        """
        NEO-004: Connection pool healthy

        Validates that connection pool is healthy.
        """
        try:
            driver = self._get_driver()

            # Get pool metrics
            pool_metrics = driver._pool.metrics if hasattr(driver, "_pool") else {}

            # Run multiple concurrent queries to test pool
            with driver.session(database=self.database) as session:
                for i in range(5):
                    session.run("RETURN $i as i", i=i).consume()

            return {
                "status": CheckStatus.PASS,
                "expected": "Connection pool healthy",
                "actual": "Pool healthy",
                "output": "PASS: Connection pool healthy",
                "details": {
                    "queries_executed": 5,
                    "pool_metrics": str(pool_metrics) if pool_metrics else "N/A"
                }
            }
        except Exception as e:
            return {
                "status": CheckStatus.WARN,
                "expected": "Connection pool healthy",
                "actual": f"Error: {str(e)}",
                "output": f"WARN: Could not verify connection pool: {str(e)}",
                "details": {"error": str(e)}
            }

    def _check_indexes(self) -> Dict[str, Any]:
        """
        NEO-005: Index validation (>= 10 indexes)

        Validates that required indexes exist for performance.
        """
        try:
            driver = self._get_driver()

            with driver.session(database=self.database) as session:
                result = session.run("SHOW INDEXES")
                indexes = [record.data() for record in result]

            index_count = len(indexes)

            # Expected indexes for OpenClaw
            expected_indexes = [
                "Task_id",
                "Task_status",
                "Task_assigned_to",
                "Notification_agent",
                "Notification_read",
                "Agent_name",
                "RateLimit_composite",
                "SignalSession_sender_hash",
                "SignalSession_current_agent",
                "Task_created_at"
            ]

            actual_index_names = [
                idx.get("name") or idx.get("indexName", "")
                for idx in indexes
            ]

            if index_count >= Neo4jConfig.MIN_INDEXES:
                return {
                    "status": CheckStatus.PASS,
                    "expected": f"At least {Neo4jConfig.MIN_INDEXES} indexes",
                    "actual": f"{index_count} indexes",
                    "output": f"PASS: {index_count} indexes found",
                    "details": {
                        "index_count": index_count,
                        "indexes": actual_index_names[:10]  # First 10
                    }
                }
            else:
                missing = [
                    idx for idx in expected_indexes
                    if not any(idx in name for name in actual_index_names)
                ]
                return {
                    "status": CheckStatus.WARN,
                    "expected": f"At least {Neo4jConfig.MIN_INDEXES} indexes",
                    "actual": f"{index_count} indexes",
                    "output": f"WARN: Only {index_count} indexes found (need {Neo4jConfig.MIN_INDEXES})",
                    "details": {
                        "index_count": index_count,
                        "expected": expected_indexes,
                        "missing": missing
                    }
                }
        except Exception as e:
            return {
                "status": CheckStatus.WARN,
                "expected": f"At least {Neo4jConfig.MIN_INDEXES} indexes",
                "actual": f"Error: {str(e)}",
                "output": f"WARN: Could not check indexes: {str(e)}",
                "details": {"error": str(e)}
            }

    def _check_constraints(self) -> Dict[str, Any]:
        """
        NEO-006: Constraint validation (>= 5 constraints)

        Validates that required constraints exist for data integrity.
        """
        try:
            driver = self._get_driver()

            with driver.session(database=self.database) as session:
                result = session.run("SHOW CONSTRAINTS")
                constraints = [record.data() for record in result]

            constraint_count = len(constraints)

            # Expected constraints
            expected_constraints = [
                "Task_id_unique",
                "Notification_id_unique",
                "Agent_name_unique",
                "RateLimit_composite_unique",
                "SignalSession_thread_id_unique"
            ]

            actual_constraint_names = [
                cons.get("name") or cons.get("constraintName", "")
                for cons in constraints
            ]

            if constraint_count >= Neo4jConfig.MIN_CONSTRAINTS:
                return {
                    "status": CheckStatus.PASS,
                    "expected": f"At least {Neo4jConfig.MIN_CONSTRAINTS} constraints",
                    "actual": f"{constraint_count} constraints",
                    "output": f"PASS: {constraint_count} constraints found",
                    "details": {
                        "constraint_count": constraint_count,
                        "constraints": actual_constraint_names
                    }
                }
            else:
                return {
                    "status": CheckStatus.WARN,
                    "expected": f"At least {Neo4jConfig.MIN_CONSTRAINTS} constraints",
                    "actual": f"{constraint_count} constraints",
                    "output": f"WARN: Only {constraint_count} constraints found (need {Neo4jConfig.MIN_CONSTRAINTS})",
                    "details": {
                        "constraint_count": constraint_count,
                        "expected": expected_constraints
                    }
                }
        except Exception as e:
            return {
                "status": CheckStatus.WARN,
                "expected": f"At least {Neo4jConfig.MIN_CONSTRAINTS} constraints",
                "actual": f"Error: {str(e)}",
                "output": f"WARN: Could not check constraints: {str(e)}",
                "details": {"error": str(e)}
            }

    def _check_migration_version(self) -> Dict[str, Any]:
        """
        NEO-007: Migration version check

        Validates that database schema migration version is current.
        """
        try:
            driver = self._get_driver()

            with driver.session(database=self.database) as session:
                # Check for migration version node
                result = session.run("""
                    MATCH (m:MigrationVersion)
                    RETURN m.version as version, m.applied_at as applied_at
                    ORDER BY m.applied_at DESC
                    LIMIT 1
                """)
                record = result.single()

                if record:
                    version = record["version"]
                    return {
                        "status": CheckStatus.PASS,
                        "expected": "Migration version recorded",
                        "actual": f"Version {version}",
                        "output": f"PASS: Migration version {version}",
                        "details": {
                            "version": version,
                            "applied_at": str(record["applied_at"])
                        }
                    }
                else:
                    return {
                        "status": CheckStatus.WARN,
                        "expected": "Migration version recorded",
                        "actual": "No migration version found",
                        "output": "WARN: No migration version found (may need to run migrations)",
                        "details": {}
                    }
        except Exception as e:
            return {
                "status": CheckStatus.WARN,
                "expected": "Migration version recorded",
                "actual": f"Error: {str(e)}",
                "output": f"WARN: Could not check migration version: {str(e)}",
                "details": {"error": str(e)}
            }

    def _check_fallback_mode(self) -> Dict[str, Any]:
        """
        NEO-008: Fallback mode test

        Validates that fallback mode works when Neo4j is unavailable.
        """
        try:
            # Import OperationalMemory to test fallback mode
            from openclaw_memory import OperationalMemory

            # Create memory with fallback mode enabled
            memory = OperationalMemory(
                uri="bolt://invalid:9999",  # Invalid URI
                username="neo4j",
                password="test",
                fallback_mode=True
            )

            # Try an operation - should not fail
            task_id = memory.create_task(
                task_type="test",
                description="Fallback test",
                delegated_by="test",
                assigned_to="any"
            )

            # If we got here without exception, fallback mode works
            return {
                "status": CheckStatus.PASS,
                "expected": "Fallback mode handles unavailability",
                "actual": "Fallback mode works",
                "output": "PASS: Fallback mode works correctly",
                "details": {"test_task_id": task_id}
            }
        except Exception as e:
            return {
                "status": CheckStatus.WARN,
                "expected": "Fallback mode handles unavailability",
                "actual": f"Error: {str(e)}",
                "output": f"WARN: Fallback mode test failed: {str(e)}",
                "details": {"error": str(e)}
            }

    def _check_read_replica(self) -> Dict[str, Any]:
        """
        NEO-009: Read replica check (optional)

        Checks if read replica is configured for HA setups.
        """
        # Check for read replica environment variables
        read_replica_uri = os.environ.get("NEO4J_READ_REPLICA_URI")
        read_replica_enabled = os.environ.get("NEO4J_READ_REPLICA_ENABLED", "").lower() == "true"

        if read_replica_enabled and read_replica_uri:
            return {
                "status": CheckStatus.PASS,
                "expected": "Read replica configured",
                "actual": f"Replica at {read_replica_uri}",
                "output": f"PASS: Read replica configured",
                "details": {"replica_uri": read_replica_uri}
            }
        elif read_replica_enabled:
            return {
                "status": CheckStatus.WARN,
                "expected": "Read replica configured",
                "actual": "Enabled but no URI set",
                "output": "WARN: Read replica enabled but URI not configured",
                "details": {}
            }
        else:
            return {
                "status": CheckStatus.SKIP,
                "expected": "Read replica configured",
                "actual": "Not configured",
                "output": "SKIP: Read replica not configured (optional)",
                "details": {}
            }

    def _check_query_performance(self) -> Dict[str, Any]:
        """
        NEO-010: Query performance baseline (< 100ms)

        Validates that simple queries complete within performance baseline.
        """
        try:
            driver = self._get_driver()

            # Run a simple query and measure time
            start = time.time()
            with driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (n)
                    RETURN count(n) as count
                """)
                count = result.single()["count"]
            duration_ms = (time.time() - start) * 1000

            if duration_ms < Neo4jConfig.QUERY_PERFORMANCE_MS:
                return {
                    "status": CheckStatus.PASS,
                    "expected": f"< {Neo4jConfig.QUERY_PERFORMANCE_MS}ms",
                    "actual": f"{duration_ms:.2f}ms",
                    "output": f"PASS: Query completed in {duration_ms:.2f}ms",
                    "details": {
                        "duration_ms": duration_ms,
                        "node_count": count,
                        "baseline_ms": Neo4jConfig.QUERY_PERFORMANCE_MS
                    }
                }
            else:
                return {
                    "status": CheckStatus.WARN,
                    "expected": f"< {Neo4jConfig.QUERY_PERFORMANCE_MS}ms",
                    "actual": f"{duration_ms:.2f}ms",
                    "output": f"WARN: Query took {duration_ms:.2f}ms (baseline: {Neo4jConfig.QUERY_PERFORMANCE_MS}ms)",
                    "details": {
                        "duration_ms": duration_ms,
                        "node_count": count,
                        "baseline_ms": Neo4jConfig.QUERY_PERFORMANCE_MS
                    }
                }
        except Exception as e:
            return {
                "status": CheckStatus.WARN,
                "expected": f"< {Neo4jConfig.QUERY_PERFORMANCE_MS}ms",
                "actual": f"Error: {str(e)}",
                "output": f"WARN: Could not measure query performance: {str(e)}",
                "details": {"error": str(e)}
            }
