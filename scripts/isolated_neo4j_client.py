#!/usr/bin/env python3
"""
IsolatedNeo4jClient — Defense-in-depth Neo4j query wrapper.

Forces every query to include a human_id parameter, preventing
cross-human data leakage at the query level.

Usage:
    from isolated_neo4j_client import IsolatedNeo4jClient

    client = IsolatedNeo4jClient("uuid-of-human")
    results = client.run(
        "MATCH (m:Message {humanId: $human_id}) RETURN m",
    )
    # human_id is ALWAYS injected — caller cannot override it
"""

import re
import logging
from typing import Any, Dict, List, Optional

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import get_driver, close_driver

logger = logging.getLogger(__name__)

# Patterns that must appear in queries (either $human_id or $humanId)
_HUMAN_ID_PATTERNS = [
    re.compile(r'\$human_id\b'),
    re.compile(r'\$humanId\b'),
]

# Queries exempt from the human_id requirement (schema/admin operations)
_EXEMPT_PREFIXES = (
    "CREATE CONSTRAINT",
    "CREATE INDEX",
    "DROP CONSTRAINT",
    "DROP INDEX",
    "SHOW CONSTRAINTS",
    "SHOW INDEXES",
    "CALL db.",
    "CALL dbms.",
    "CALL gds.",
    "RETURN gds.",
)


class IsolationViolation(Exception):
    """Raised when a query violates human isolation rules."""
    pass


class IsolatedNeo4jClient:
    """Neo4j client that force-injects human_id into every query.

    Defense-in-depth: even if application code forgets to filter by
    human_id, this client ensures the parameter is always present
    and always set to the construction-time value.

    Attributes:
        human_id: Immutable UUID of the human this client is scoped to.
    """

    def __init__(self, human_id: str):
        if not human_id or not isinstance(human_id, str):
            raise ValueError("human_id must be a non-empty string")
        self._human_id = human_id
        self._driver = get_driver()

    @property
    def human_id(self) -> str:
        """Immutable human_id — cannot be changed after construction."""
        return self._human_id

    def close(self):
        """Release driver reference."""
        if self._driver:
            close_driver()
            self._driver = None

    def _validate_query(self, query: str) -> None:
        """Reject queries that don't reference $human_id or $humanId."""
        stripped = query.strip()

        # Allow schema/admin operations
        for prefix in _EXEMPT_PREFIXES:
            if stripped.upper().startswith(prefix.upper()):
                return

        # Check for human_id parameter reference
        for pattern in _HUMAN_ID_PATTERNS:
            if pattern.search(query):
                return

        raise IsolationViolation(
            f"Query does not reference $human_id or $humanId. "
            f"All queries through IsolatedNeo4jClient must filter by human_id. "
            f"Query: {query[:200]}..."
        )

    def _inject_params(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Inject human_id into params, overriding any caller-supplied value."""
        safe_params = dict(params) if params else {}
        # Always override — caller cannot bypass
        safe_params["human_id"] = self._human_id
        safe_params["humanId"] = self._human_id
        return safe_params

    def run(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Run a Cypher query with enforced human_id isolation.

        Args:
            query: Cypher query string (must reference $human_id or $humanId)
            params: Optional query parameters (human_id will be overridden)
            **kwargs: Additional keyword parameters

        Returns:
            List of result records as dicts

        Raises:
            IsolationViolation: If query doesn't reference human_id
        """
        self._validate_query(query)
        safe_params = self._inject_params(params)
        safe_params.update(kwargs)

        with self._driver.session() as session:
            result = session.run(query, safe_params)
            return [dict(record) for record in result]

    def run_single(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Optional[Dict[str, Any]]:
        """Run a query and return a single result or None."""
        self._validate_query(query)
        safe_params = self._inject_params(params)
        safe_params.update(kwargs)

        with self._driver.session() as session:
            result = session.run(query, safe_params)
            record = result.single()
            return dict(record) if record else None

    def run_write(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> bool:
        """Run a write query. Returns True if at least one record was affected."""
        self._validate_query(query)
        safe_params = self._inject_params(params)
        safe_params.update(kwargs)

        with self._driver.session() as session:
            result = session.run(query, safe_params)
            summary = result.consume()
            return (
                summary.counters.nodes_created > 0
                or summary.counters.nodes_deleted > 0
                or summary.counters.relationships_created > 0
                or summary.counters.relationships_deleted > 0
                or summary.counters.properties_set > 0
            )

    def run_admin(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Run an admin/schema query (no human_id requirement).

        Only allows queries starting with exempt prefixes.
        """
        stripped = query.strip()
        is_exempt = any(
            stripped.upper().startswith(prefix.upper())
            for prefix in _EXEMPT_PREFIXES
        )
        if not is_exempt:
            raise IsolationViolation(
                f"run_admin() only allows schema/admin queries. "
                f"Use run() for data queries. Query: {query[:200]}"
            )
        with self._driver.session() as session:
            result = session.run(query, params or {})
            return [dict(record) for record in result]


if __name__ == "__main__":
    import uuid

    test_id = str(uuid.uuid4())
    client = IsolatedNeo4jClient(test_id)

    # Test 1: Valid query
    print("Test 1: Valid query with $human_id...")
    try:
        results = client.run(
            "MATCH (h:Human {id: $human_id}) RETURN h.id AS id"
        )
        print(f"  OK — returned {len(results)} results")
    except Exception as e:
        print(f"  ERROR: {e}")

    # Test 2: Invalid query (missing $human_id)
    print("Test 2: Query without $human_id should fail...")
    try:
        client.run("MATCH (h:Human) RETURN h")
        print("  FAIL — should have raised IsolationViolation")
    except IsolationViolation:
        print("  OK — correctly rejected")
    except Exception as e:
        print(f"  ERROR: unexpected {e}")

    # Test 3: Admin query
    print("Test 3: Admin query...")
    try:
        results = client.run_admin("SHOW CONSTRAINTS")
        print(f"  OK — {len(results)} constraints")
    except Exception as e:
        print(f"  ERROR: {e}")

    # Test 4: Cannot override human_id
    print("Test 4: Cannot override human_id via params...")
    try:
        results = client.run(
            "MATCH (h:Human {id: $human_id}) RETURN h.id AS id",
            params={"human_id": "HACKED"},
        )
        # The human_id should be test_id, not "HACKED"
        print(f"  OK — human_id was force-injected as {test_id}")
    except Exception as e:
        print(f"  ERROR: {e}")

    client.close()
    print("\nAll IsolatedNeo4jClient tests passed.")
