"""Lightweight trace helpers for Kublai production-agent flows."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


def utc_ms() -> int:
    """Return the current Unix time in milliseconds (UTC)."""
    return int(time.time() * 1000)


def new_trace_id() -> str:
    """Create a sortable-enough opaque trace id."""
    return f"trace-{uuid.uuid4().hex}"


def new_span_id() -> str:
    return f"span-{uuid.uuid4().hex}"


@dataclass(frozen=True)
class TraceContext:
    """Minimal trace context shared across telemetry, audit, and task rows."""

    actor: str
    operation: str
    resource: str | None = None
    trace_id: str = field(default_factory=new_trace_id)
    parent_span_id: str | None = None
    started_at: int = field(default_factory=utc_ms)
    metadata: dict[str, Any] = field(default_factory=dict)


def trace_event(event_type: str, *, span_id: str | None = None, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a JSON-serializable trace event payload."""
    return {
        "event_type": event_type,
        "span_id": span_id or new_span_id(),
        "payload": payload or {},
        "created_at": utc_ms(),
    }
