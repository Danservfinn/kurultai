#!/usr/bin/env python3
"""
Neo4j Utilities - Shared helper functions for Neo4j operations.

This module provides common utilities used across Neo4j store classes:
- JSON field parsing with safe fallbacks
- Connection management helpers

Usage:
    from neo4j_utils import parse_json_field, parse_json_fields

    # Parse a single field
    data = parse_json_field(record.get("metadata"), default={})

    # Parse multiple fields in a dict
    record = parse_json_fields(record, ["communication_style", "preferences"])
"""

import json
from typing import Any, Dict, List, Optional, Union


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
