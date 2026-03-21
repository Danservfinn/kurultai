#!/usr/bin/env python3
"""
Neo4j Utilities - Shared helper functions for Neo4j operations.

This module provides common utilities used across Neo4j store classes:
- JSON field parsing with safe fallbacks
- Connection management helpers
- Safe Neo4j operations with graceful degradation

Usage:
    from neo4j_utils import parse_json_field, parse_json_fields, safe_neo4j_op

    # Parse a single field
    data = parse_json_field(record.get("metadata"), default={})

    # Parse multiple fields in a dict
    record = parse_json_fields(record, ["communication_style", "preferences"])

    # Safe Neo4j operation with fallback
    result = safe_neo4j_op(lambda session: session.run("MATCH (n) RETURN n"))
"""

import json
import os
import time
import logging
from typing import Any, Callable, Dict, List, Optional, Union, TypeVar

logger = logging.getLogger(__name__)

# Type variable for return values
T = TypeVar('T')


def parse_json_field(
    value: Any,
    default: Any = None
) -> Any:
    """Parse a JSON string field, returning default if invalid.

    Neo4j sometimes stores complex data as JSON strings. This helper
    safely parses them with appropriate fallback handling.

    Args:
        value: The value to parse (may be string, dict, list, or None)
        default: Default value to return if parsing fails (default: None)

    Returns:
        Parsed JSON value, or default if:
        - value is None or empty
        - value is already a dict/list (pass through)
        - JSON parsing fails

    Examples:
        >>> parse_json_field('{"key": "value"}')
        {'key': 'value'}
        >>> parse_json_field(None, default={})
        {}
        >>> parse_json_field({"already": "parsed"})
        {"already": "parsed"}
        >>> parse_json_field("invalid json", default=[])
        []
    """
    if not value:
        return default

    # Already parsed (dict or list)
    if isinstance(value, (dict, list)):
        return value

    # Try to parse string
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return default

    return default


def parse_json_fields(
    record: Dict[str, Any],
    fields: List[str],
    defaults: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Parse multiple JSON string fields in a record.

    Modifies the record in-place, converting specified string fields
    to their parsed JSON equivalents.

    Args:
        record: Dictionary containing fields to parse
        fields: List of field names to parse
        defaults: Optional dict mapping field names to default values
                  (default: None for all fields)

    Returns:
        The modified record (same object, modified in-place)

    Examples:
        >>> record = {"data": '{"key": "value"}', "other": "text"}
        >>> parse_json_fields(record, ["data"])
        {"data": {"key": "value"}, "other": "text"}
    """
    defaults = defaults or {}

    for field in fields:
        if field in record and record[field] is not None:
            default = defaults.get(field)
            record[field] = parse_json_field(record[field], default=default)

    return record


def safe_int(value: Any, default: int = 0) -> int:
    """Safely convert a value to int with fallback.

    Args:
        value: Value to convert
        default: Default if conversion fails

    Returns:
        Integer value or default
    """
    try:
        return int(value) if value is not None else default
    except (ValueError, TypeError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert a value to float with fallback.

    Args:
        value: Value to convert
        default: Default if conversion fails

    Returns:
        Float value or default
    """
    try:
        return float(value) if value is not None else default
    except (ValueError, TypeError):
        return default


class Neo4jUnavailableError(Exception):
    """Raised when Neo4j is unavailable and fallback mode is active."""
    pass


_health_cache = {"result": None, "expires": 0.0}


def check_neo4j_available() -> bool:
    """Check if Neo4j is available without raising exceptions.

    Results are cached for 10 seconds to avoid creating ephemeral
    drivers on every call.

    Returns:
        True if Neo4j is reachable, False otherwise
    """
    if time.monotonic() < _health_cache["expires"]:
        return _health_cache["result"]

    try:
        from neo4j import GraphDatabase

        uri = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
        user = os.environ.get('NEO4J_USER', 'neo4j')

        # Handle both NEO4J_PASSWORD and NEO4J_AUTH formats
        password = os.environ.get('NEO4J_PASSWORD')
        if not password and 'NEO4J_AUTH' in os.environ:
            auth_val = os.environ.get('NEO4J_AUTH', '')
            parts = auth_val.split('/', 1)
            password = parts[1] if len(parts) > 1 else auth_val

        if not password:
            logger.debug("Neo4j health check: no password configured")
            _health_cache["result"] = False
            _health_cache["expires"] = time.monotonic() + 10
            return False

        # Quick connectivity check with short timeout
        driver = GraphDatabase.driver(
            uri,
            auth=(user, password),
            connection_timeout=3,  # Short timeout for health check
            max_connection_lifetime=1
        )
        with driver.session() as session:
            session.run("RETURN 1 as test").consume()
        driver.close()
        result = True
    except Exception as e:
        logger.debug(f"Neo4j health check failed: {e}")
        result = False

    _health_cache["result"] = result
    _health_cache["expires"] = time.monotonic() + 10
    return result


def safe_neo4j_op(
    operation: Callable,
    fallback: T = None,
    silent: bool = False,
    log_error: bool = True
) -> Union[T, Any]:
    """Execute a Neo4j operation with graceful degradation.

    When Neo4j is unavailable, returns the fallback value instead of
    raising an exception. This enables filesystem-only mode for research
    and analysis tasks.

    Args:
        operation: Callable that takes a Neo4j session and returns a value
                   Signature: operation(session) -> result
        fallback: Value to return when Neo4j is unavailable (default: None)
        silent: If True, suppress warning messages (default: False)
        log_error: If True, log errors (default: True)

    Returns:
        Result of operation if Neo4j available, otherwise fallback value

    Examples:
        >>> # Simple query with list fallback
        >>> results = safe_neo4j_op(
        ...     lambda s: list(s.run("MATCH (t:Task) RETURN t")),
        ...     fallback=[]
        ... )

        >>> # Single record with dict fallback
        >>> task = safe_neo4j_op(
        ...     lambda s: s.run("MATCH (t:Task {id: $id}) RETURN t", id=123).single(),
        ...     fallback=None
        ... )

        >>> # Write operation (returns success status)
        >>> success = safe_neo4j_op(
        ...     lambda s: s.run("CREATE (n:Task {id: $id})", id=123),
        ...     fallback=False
        ... ) is not False
    """
    try:
        from neo4j import GraphDatabase

        uri = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
        user = os.environ.get('NEO4J_USER', 'neo4j')

        # Handle both NEO4J_PASSWORD and NEO4J_AUTH formats
        password = os.environ.get('NEO4J_PASSWORD')
        if not password and 'NEO4J_AUTH' in os.environ:
            auth_val = os.environ.get('NEO4J_AUTH', '')
            parts = auth_val.split('/', 1)
            password = parts[1] if len(parts) > 1 else auth_val

        if not password:
            raise Exception("No Neo4j password configured")

        driver = GraphDatabase.driver(
            uri,
            auth=(user, password),
            connection_timeout=5,
            max_connection_lifetime=60
        )

        try:
            with driver.session() as session:
                return operation(session)
        finally:
            driver.close()

    except Exception as e:
        if log_error:
            logger.warning(f"Neo4j unavailable, using fallback: {e}")
        if not silent:
            import warnings
            warnings.warn(
                f"Neo4j unavailable - running in filesystem-only mode. Error: {e}",
                UserWarning,
                stacklevel=2
            )
        return fallback


def execute_query_cypher(
    query: str,
    params: Optional[Dict[str, Any]] = None,
    fallback: T = None,
    single: bool = False
) -> Union[T, Any]:
    """Execute a Cypher query with safe fallback.

    Convenience wrapper around safe_neo4j_op for simple query execution.

    Args:
        query: Cypher query string
        params: Query parameters (default: None)
        fallback: Value to return when Neo4j unavailable (default: None)
        single: If True, return single() result; otherwise return list of records

    Returns:
        Query result or fallback value

    Examples:
        >>> # Get all tasks
        >>> tasks = execute_query_cypher(
        ...     "MATCH (t:Task) RETURN t",
        ...     fallback=[]
        ... )

        >>> # Get single task
        >>> task = execute_query_cypher(
        ...     "MATCH (t:Task {id: $id}) RETURN t",
        ...     params={"id": "123"},
        ...     fallback=None,
        ...     single=True
        ... )
    """
    def op(session):
        result = session.run(query, params or {})
        if single:
            return result.single()
        return list(result)

    return safe_neo4j_op(op, fallback=fallback)
