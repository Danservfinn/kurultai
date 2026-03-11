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

# Valid event types (as of 2026-03-10)
# Core lifecycle events
VALID_EVENTS = {
    "QUEUED", "EXECUTING", "COMPLETED", "FAILED",
    # Execution detail events
    "EXECUTION_DETAIL", "EXECUTION_TRACE",
    # Scoring and routing events
    "SCORED", "ACTION_SCORED", "QUEUED_REDISTRIBUTED",
    # Verification events
    "VERIFIED", "VERIFICATION_FAILED",
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
    "MODEL_FALLBACK_SUCCESS", "MODEL_DRIFT_REJECTED",
    # Task state events
    "TASK_REPORT_GENERATED", "FAKE_COMPLETION_BLOCKED", "COMPLETED_MD_SUFFIX_BUG",
    "STALL_DETECTED", "GATE_PASSED", "RESOLVED", "RECOVERED",
    "GATE_FOLLOWUPS_CREATED", "ESCALATION_RESOLVED", "ESCALATION_CHAIN_RESOLVED",
    "REQUEUED", "ORPHAN_RESOLVED", "CANCELLED",
    "CIRCUIT_BREAKER_HALF_OPEN",
    # Rule enforcement events
    "R008_VIOLATION",
    # Test events (should not appear in production)
    "PERF_TEST", "CONCURRENT_TEST", "TEST_EVENT",
}

# System-level events that don't require task_id (session, system, operational events)
SYSTEM_EVENTS = {
    "SESSION_AUTO_CLEANUP", "SESSION_RESET", "ARCH_UPDATE_CHECK",
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
    """Append an event to the task ledger with exclusive file locking.

    Args:
        entry: Event dictionary to append
        validate: If True, validate event before appending (default True)

    Returns:
        True on success, False on failure
    """
    try:
        # Validate event type first
        event_type = entry.get("event")
        if event_type and event_type not in VALID_EVENTS:
            print(f"[LEDGER ERROR] Invalid event type: {event_type}", file=sys.stderr)
            # Still write for audit trail, but mark as invalid
            if "_validation_errors" not in entry:
                entry["_validation_errors"] = []
            entry["_validation_errors"].append(f"invalid event type: {event_type}")

        # Validate task_id - add correlation_id if missing/unknown
        # Exception: System-level events (SESSION_AUTO_CLEANUP, etc.) don't require task_id
        task_id = entry.get("task_id")
        event_type = entry.get("event")
        is_system_event = event_type in SYSTEM_EVENTS
        if not task_id or task_id == "unknown":
            if not is_system_event:
                # Log warning for task events without task_id
                print(f"[LEDGER WARNING] Event without valid task_id: {event_type}", file=sys.stderr)
            # Generate correlation ID for tracing (system events included)
            if "_correlation_id" not in entry:
                entry["_correlation_id"] = generate_correlation_id()
        elif not validate_task_id(task_id):
            # Non-canonical task_id format - warn but accept for audit trail
            print(f"[LEDGER WARNING] Non-canonical task_id format: {task_id}", file=sys.stderr)
            # Add to validation errors list if it exists, or create it
            validation_errors = entry.get("_validation_errors", [])
            validation_errors.append(f"non-canonical task_id format: {task_id}")
            entry["_validation_errors"] = validation_errors

        # Schema validation (optional, can be disabled for emergency writes)
        if validate:
            is_valid, errors = validate_event(entry)
            if not is_valid:
                print(f"[LEDGER ERROR] Invalid event: {'; '.join(errors)}", file=sys.stderr)
                # Still write for audit trail, but mark as invalid
                if "_validation_errors" not in entry:
                    entry["_validation_errors"] = errors
                else:
                    # Merge errors, avoiding duplicates
                    existing = set(entry["_validation_errors"])
                    for e in errors:
                        if e not in existing:
                            entry["_validation_errors"].append(e)

        # Ensure timestamp exists
        if "ts" not in entry:
            entry["ts"] = datetime.now().isoformat()

        TASK_LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with open(TASK_LEDGER, "a", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.write(json.dumps(entry) + "\n")
                f.flush()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        return True
    except Exception as e:
        print(f"[ledger] append failed: {e}", file=sys.stderr)
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
    """Read events from the task ledger with shared locking.

    Args:
        hours: Optionally filter to events within the last N hours
        valid_only: If True, only return events that pass validation

    Returns:
        List of events
    """
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
                                    pass  # Keep events with unparseable timestamps
                        # Filter invalid events if requested
                        if valid_only and not is_valid_event(ev):
                            continue
                        events.append(ev)
                    except json.JSONDecodeError:
                        continue
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except Exception as e:
        print(f"[ledger] read failed: {e}", file=sys.stderr)
    return events
