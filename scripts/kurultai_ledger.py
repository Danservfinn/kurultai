"""
kurultai_ledger.py — Centralized task ledger I/O with file locking.

All scripts that need to read/write the task-ledger.jsonl should import
from here instead of implementing their own I/O.

Features:
- File locking for concurrent access safety
- Schema validation for event integrity
- task_id validation with correlation_id fallback
"""
from __future__ import annotations

import fcntl
import json
import re
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from kurultai_paths import TASK_LEDGER


# =============================================================================
# Event Schema Definition
# =============================================================================

# Valid event types (as of 2026-03-11)
# Core lifecycle events
VALID_EVENTS = {
    "QUEUED", "EXECUTING", "COMPLETED", "FAILED",
    # Execution detail events
    "EXECUTION_DETAIL", "EXECUTION_TRACE",
    # Scoring and routing events
    "SCORED", "ACTION_SCORED", "QUEUED_REDISTRIBUTED",
    # Verification events
    "VERIFIED", "VERIFICATION_FAILED", "COMPLETION_GATE_BLOCKED", "PRE_SUBMIT_GATE_BLOCKED", "PRE_SUBMIT_GATE_BLOCKED_FALLBACK",
    # Skill events
    "SKILL_INVOCATION", "SKILL_OUTCOME", "SKILL_AGGREGATE",
    # Architecture and session events
    "ARCH_UPDATE_CHECK", "SESSION_AUTO_CLEANUP", "SESSION_RESET",
    # Reflection events
    "REFLECT_SUMMARY",
    # Credential and error events (informational, non-blocking)
    "CREDENTIAL_WARNING_FALLBACK", "CREDENTIAL_ERROR_SHORT_CIRCUIT",
    "COMPLETION_VERIFICATION_FAILED",
    # Model events
    "MODEL_USED", "MODEL_CONFIG_ERROR", "MODEL_FALLBACK", "MODEL_FALLBACK_FAILED",
    "MODEL_FALLBACK_SUCCESS", "MODEL_FALLBACK_BLOCKED", "MODEL_DRIFT_REJECTED",
    # Task state events
    "TASK_REPORT_GENERATED", "FAKE_COMPLETION_BLOCKED", "COMPLETED_MD_SUFFIX_BUG",
    "STALL_DETECTED", "GATE_PASSED", "RESOLVED", "RECOVERED",
    "SOURCE_VALIDATION_BLOCKED", "DOMAIN_COMPLIANCE_REJECT", "PROXY_HEALTH_CHECK",
    "O002_FAST_FAILURE_REQUIRES_INVESTIGATION",
    "GATE_FOLLOWUPS_CREATED", "ESCALATION_RESOLVED", "ESCALATION_CHAIN_RESOLVED",
    "REQUEUED", "ORPHAN_RESOLVED", "CANCELLED",
    "CIRCUIT_BREAKER_HALF_OPEN",
    # Rule enforcement events
    "R008_VIOLATION", "R008_VIOLATION_TRACKED", "R008_VIOLATION_TIMEOUT", "R008_PREFLIGHT_FAIL", "R008_PREFLIGHT_CHECK",
    "AUTH_PREFLIGHT_FAIL", "STALL_SIGTERM",
    "R008_AUTO_INVOKE_SUCCESS", "R008_AUTO_INVOKE_FAILED", "R008_SKILL_NOT_INVOKED", "R008_SKILL_AUTO_INVOKED",
    "R008_SKILL_NOT_FOUND",
    # Timeout events
    "TASK_TIMEOUT",
    # Test events (should not appear in production)
    "PERF_TEST", "CONCURRENT_TEST", "TEST_EVENT",
}

# System-level events that don't require task_id (session, system, operational events)
SYSTEM_EVENTS = {
    "SESSION_AUTO_CLEANUP", "SESSION_RESET", "ARCH_UPDATE_CHECK",
    "AUTH_PREFLIGHT_FAIL",
    "R008_VIOLATION_TIMEOUT",  # R008 enforcement events written from monitoring loop without task_id
}

# UUID pattern: 8-36 hex chars with optional dashes (legacy format)
UUID_PATTERN = re.compile(r"^[a-f0-9-]{8,36}$", re.IGNORECASE)

# Canonical task ID format: {priority}-{timestamp}-{uuid8}
# See /agents/main/specs/TASK_ID_FORMAT.md for specification
TASK_ID_PATTERN = re.compile(r'^(critical|high|normal|low)-\d{10}-[a-f0-9]{8}$')
VALID_PRIORITIES = ("critical", "high", "normal", "low")


def validate_event(entry: dict) -> tuple[bool, list[str]]:
    """Validate event against schema.

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []

    # Required fields
    if "event" not in entry:
        errors.append("missing required field: event")
    elif entry["event"] not in VALID_EVENTS:
        errors.append(f"invalid event type: {entry['event']} (valid: {', '.join(sorted(VALID_EVENTS)[:5])}...)")

    if "ts" not in entry:
        errors.append("missing required field: ts")
    else:
        # Validate timestamp format
        ts_str = entry.get("ts", "")
        try:
            datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except (ValueError, TypeError, AttributeError):
            errors.append(f"invalid timestamp format: {ts_str}")

    # task_id validation (optional but recommended)
    # Accepts: canonical format (priority-timestamp-uuid8), legacy UUID formats, or legacy short IDs
    task_id = entry.get("task_id")
    if task_id is not None and task_id != "unknown":
        task_str = str(task_id)
        # Check canonical format first
        if not TASK_ID_PATTERN.match(task_str):
            # Fall back to legacy UUID pattern
            if not UUID_PATTERN.match(task_str):
                # Allow short task IDs (first 8-12 chars of UUID) - legacy format
                if not re.match(r"^[a-f0-9]{8,12}$", task_str, re.IGNORECASE):
                    # Allow fs-* and task-* prefixed IDs (legacy)
                    if not re.match(r'^(fs|task)-\d+', task_str):
                        errors.append(f"invalid task_id format: {task_id}")

    return len(errors) == 0, errors


def generate_task_id(priority: str = "normal") -> str:
    """Generate a unique task ID in canonical format.

    Format: {priority}-{timestamp}-{uuid8}
    Example: high-1773121500-a1b2c3d4

    Args:
        priority: Task priority (critical, high, normal, low). Defaults to "normal".

    Returns:
        Task ID string in canonical format.
    """
    priority = priority.lower()
    if priority not in VALID_PRIORITIES:
        priority = "normal"
    timestamp = int(time.time())
    uuid_suffix = uuid.uuid4().hex[:8]
    return f"{priority}-{timestamp}-{uuid_suffix}"


def validate_task_id(task_id: str) -> bool:
    """Validate task_id matches canonical format.

    Canonical format: {priority}-{timestamp}-{uuid8}
    Examples: high-1773121500-a1b2c3d4, normal-1773121600-1a2b3c4d

    Args:
        task_id: The task ID string to validate.

    Returns:
        True if task_id matches canonical format, False otherwise.
    """
    if not task_id or not isinstance(task_id, str):
        return False
    return bool(TASK_ID_PATTERN.match(task_id))


def generate_correlation_id() -> str:
    """Generate a correlation ID for tracing events without valid task_id."""
    return str(uuid.uuid4())[:8]


# =============================================================================
# Ledger I/O Functions
# =============================================================================

def append_ledger(entry: dict, validate: bool = True) -> bool:
    """Write event to Neo4j as PipelineEvent (Phase 5 cutover 2026-03-12).

    Since JSONL is no longer the source of truth, this writes to Neo4j
    so events are visible via read_ledger(). Callers like kublai_task_report.py
    rely on this for TASK_REPORT_GENERATED, MODEL_USED, etc.

    Returns:
        True on success, False on failure.
    """
    try:
        from neo4j_task_tracker import TaskTracker
        tracker = TaskTracker()
        tracker.emit_pipeline_event(
            event_type=entry.get("event", "UNKNOWN"),
            payload=entry,
            agent=entry.get("agent", ""),
        )
        return True
    except Exception:
        return False


def is_valid_event(entry: dict) -> bool:
    """Check if an event is valid (no validation errors and valid event type).

    Args:
        entry: Event dictionary to validate

    Returns:
        True if event is valid, False otherwise
    """
    # Events with validation errors are not valid
    if entry.get("_validation_errors"):
        return False

    # Events without event type are not valid
    event_type = entry.get("event")
    if not event_type:
        return False

    # Events with unknown event type are not valid
    if event_type not in VALID_EVENTS:
        return False

    return True


def read_ledger(hours: float | None = None, valid_only: bool = False) -> list:
    """Read task events from Neo4j (Phase 5 cutover 2026-03-12).

    Delegates to neo4j_v2_ledger_compat which reads from Neo4j Task nodes
    and returns events in the same JSONL-compatible format.

    Args:
        hours: Optionally filter to events within the last N hours
        valid_only: If True, only return core lifecycle events

    Returns:
        List of events matching the JSONL ledger schema.
    """
    try:
        from neo4j_v2_ledger_compat import read_ledger as _v2_read
        return _v2_read(hours=int(hours) if hours else None, valid_only=valid_only)
    except Exception as e:
        print(f"[ledger] Neo4j read failed, falling back to JSONL: {e}", file=sys.stderr)
        # Fallback to archived JSONL if Neo4j is unavailable
        if not TASK_LEDGER.exists():
            return []
        cutoff = None
        if hours is not None:
            cutoff = datetime.now() - timedelta(hours=hours)
        events = []
        try:
            with open(TASK_LEDGER, "r", encoding="utf-8") as f:
                fcntl.flock(f, fcntl.LOCK_SH)
                try:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            ev = json.loads(line)
                            if cutoff is not None:
                                ts_str = ev.get("ts", "")
                                if ts_str:
                                    try:
                                        ev_time = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                                        if ev_time.tzinfo:
                                            if ev_time < cutoff:
                                                continue
                                        else:
                                            if ev_time < cutoff.replace(tzinfo=None):
                                                continue
                                    except (ValueError, TypeError):
                                        pass
                            if valid_only and not is_valid_event(ev):
                                continue
                            events.append(ev)
                        except json.JSONDecodeError:
                            continue
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)
        except Exception as e2:
            print(f"[ledger] JSONL fallback also failed: {e2}", file=sys.stderr)
        return events
