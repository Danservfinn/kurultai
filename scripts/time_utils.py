"""
Time Utilities

Centralized time/date utilities for the Kurultai multi-agent system.
Consolidates 465+ datetime formatting calls across codebase.

Usage:
    from time_utils import now_iso, now_str, epoch_ms

    timestamp = now_iso()  # "2026-03-09T14:30:00.123456"
    formatted = now_str()  # "2026-03-09 14:30:00"
"""

from datetime import datetime
from typing import Optional


def now_iso() -> str:
    """Return current time as ISO 8601 string.

    Returns:
        ISO formatted datetime string with microseconds
    """
    return datetime.now().isoformat()


def now_utc_iso() -> str:
    """Return current UTC time as ISO 8601 string.

    Returns:
        ISO formatted datetime string with timezone
    """
    return datetime.utcnow().isoformat() + "Z"


def now_str(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Return current time as formatted string.

    Args:
        fmt: strftime format string (default: "YYYY-MM-DD HH:MM:SS")

    Returns:
        Formatted datetime string
    """
    return datetime.now().strftime(fmt)


def parse_iso(iso_str: str) -> Optional[datetime]:
    """Parse ISO 8601 string to datetime.

    Args:
        iso_str: ISO formatted datetime string

    Returns:
        datetime object or None if parsing fails
    """
    try:
        return datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        return None


def epoch_ms() -> int:
    """Return current time as epoch milliseconds.

    Returns:
        Milliseconds since Unix epoch
    """
    return int(datetime.now().timestamp() * 1000)


def epoch_s() -> int:
    """Return current time as epoch seconds.

    Returns:
        Seconds since Unix epoch
    """
    return int(datetime.now().timestamp())


def format_duration(seconds: float) -> str:
    """Format duration in human-readable form.

    Args:
        seconds: Duration in seconds

    Returns:
        Human-readable string like "2h 30m 15s" or "45s"
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"
