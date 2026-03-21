#!/usr/bin/env python3
"""
Security Event Logger - Immutable audit trail for security-critical events.

Logs security events to multiple destinations for tamper-proof audit trails:
- JSON log file (append-only)
- Neo4j (immutable nodes with timestamps)
- Optional Signal alerts for critical events

Usage:
    from security_event_logger import log_security_event

    log_security_event(
        event_type="GATE_BYPASS",
        severity="critical",
        details={"task_id": "abc123", "approver": "kublai", "reason": "..."}
    )

Events are immutable - once logged, they cannot be modified.
"""

import json
import os
import sys
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any, List
import hashlib

# Add scripts directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kurultai_paths import AGENTS_DIR

try:
    from neo4j import GraphDatabase
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False

# Security log directory
SECURITY_LOG_DIR = Path.home() / ".openclaw" / "logs" / "security"
SECURITY_LOG_DIR.mkdir(parents=True, exist_ok=True)

# Main security log (append-only)
SECURITY_LOG = SECURITY_LOG_DIR / "security-events.log"

# Critical events log (separate for alerting)
CRITICAL_LOG = SECURITY_LOG_DIR / "critical-events.log"


class Severity(Enum):
    """Security event severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class EventType(Enum):
    """Security event types."""
    GATE_BYPASS = "GATE_BYPASS"
    UNAUTHORIZED_BYPASS_ATTEMPT = "UNAUTHORIZED_BYPASS_ATTEMPT"
    PROMPT_INJECTION_DETECTED = "PROMPT_INJECTION_DETECTED"
    OPT_OUT_DENIED = "OPT_OUT_DENIED"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    AUDIT_TAMPER_ATTEMPT = "AUDIT_TAMPER_ATTEMPT"
    AUTH_FAILURE = "AUTH_FAILURE"
    MULTI_PARTY_APPROVAL = "MULTI_PARTY_APPROVAL"
    FORCE_BYPASS_USED = "FORCE_BYPASS_USED"


def _generate_event_hash(event_data: Dict[str, Any]) -> str:
    """Generate SHA-256 hash of event data for integrity verification."""
    # Sort keys for consistent hashing
    normalized = json.dumps(event_data, sort_keys=True)
    return hashlib.sha256(normalized.encode()).hexdigest()


def _write_to_log(event: Dict[str, Any], log_path: Path) -> None:
    """Write event to log file (append-only)."""
    with open(log_path, 'a') as f:
        f.write(json.dumps(event) + '\n')
    # Set permissions to read-write only by owner
    os.chmod(log_path, 0o600)


def _log_to_neo4j(event: Dict[str, Any]) -> bool:
    """Create immutable SecurityEvent node in Neo4j."""
    if not NEO4J_AVAILABLE:
        return False

    try:
        # Neo4j connection - use centralized driver with connection pooling
        try:
            from neo4j_task_tracker import neo4j_session
        except ImportError:
            print("[WARN] neo4j_task_tracker not available - skipping Neo4j security logging")
            return False

        with neo4j_session() as session:
            # Create immutable SecurityEvent node
            # Using CREATE ensures new node each time (no updates possible)
            query = """
            CREATE (e:SecurityEvent {
                event_id: $event_id,
                event_type: $event_type,
                severity: $severity,
                event_hash: $event_hash,
                details: $details,
                timestamp: $timestamp,
                hostname: $hostname,
                immutable: true,
                logged_at: datetime()
            })
            RETURN e.event_id as id
            """

            session.run(
                query,
                event_id=event["event_id"],
                event_type=event["event_type"],
                severity=event["severity"],
                event_hash=event["event_hash"],
                details=json.dumps(event.get("details", {})),
                timestamp=event["timestamp"],
                hostname=event.get("hostname", "unknown")
            )

        return True

    except Exception as e:
        # Log Neo4j failure to local log
        error_event = {
            "event": "NEO4J_LOG_FAILED",
            "original_event_id": event.get("event_id"),
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }
        _write_to_log(error_event, SECURITY_LOG_DIR / "neo4j-errors.log")
        return False


def _send_signal_alert(event: Dict[str, Any]) -> bool:
    """Send Signal alert for critical security events."""
    if event.get("severity") != Severity.CRITICAL.value:
        return True  # Not critical, no alert needed

    try:
        # Check for Signal bot configuration
        signal_script = Path.home() / ".openclaw" / "agents" / "main" / "scripts" / "signal-alert.sh"

        if not signal_script.exists():
            return False

        # Format alert message
        event_type = event.get("event_type", "UNKNOWN")
        details = event.get("details", {})
        approver = details.get("approver", "unknown")
        task_id = details.get("task_id", "unknown")

        message = f"""
🚨 SECURITY ALERT 🚨

Event: {event_type}
Severity: CRITICAL
Time: {event.get('timestamp')}
Approver: {approver}
Task: {task_id}

Details: {json.dumps(details, indent=2)}

Hash: {event.get('event_hash')}
""".strip()

        # Call Signal alert script
        import subprocess
        result = subprocess.run(
            [str(signal_script), message],
            capture_output=True,
            text=True,
            timeout=30
        )

        return result.returncode == 0

    except Exception as e:
        # Log Signal failure but don't fail the security event
        error_event = {
            "event": "SIGNAL_ALERT_FAILED",
            "original_event_id": event.get("event_id"),
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }
        _write_to_log(error_event, SECURITY_LOG_DIR / "signal-errors.log")
        return False


def log_security_event(
    event_type: EventType,
    severity: Severity,
    details: Dict[str, Any],
    send_alert: bool = True
) -> Dict[str, Any]:
    """
    Log a security event to all configured destinations.

    Args:
        event_type: Type of security event
        severity: Event severity level
        details: Event-specific details (will be logged and hashed)
        send_alert: Whether to send Signal alert for critical events

    Returns:
        The complete event dictionary that was logged
    """
    # Generate event ID
    event_id = f"sec-{datetime.now().strftime('%Y%m%d')}-{hashlib.sha256(os.urandom(16)).hexdigest()[:16]}"

    # Build event structure
    event = {
        "event_id": event_id,
        "event_type": event_type.value,
        "severity": severity.value,
        "timestamp": datetime.now().isoformat(),
        "hostname": os.uname().nodename,
        "details": details
    }

    # Generate integrity hash
    event["event_hash"] = _generate_event_hash(event)

    # Write to main log (always succeeds or raises)
    _write_to_log(event, SECURITY_LOG)

    # Write to critical log if critical severity
    if severity == Severity.CRITICAL:
        _write_to_log(event, CRITICAL_LOG)

    # Log to Neo4j (best effort)
    neo4j_success = _log_to_neo4j(event)
    event["neo4j_logged"] = neo4j_success

    # Send Signal alert for critical events (best effort)
    if send_alert and severity == Severity.CRITICAL:
        signal_success = _send_signal_alert(event)
        event["signal_sent"] = signal_success
    else:
        event["signal_sent"] = False

    return event


def check_rate_limits(
    identifier: str,
    max_per_day: int = 10,
    max_per_hour: int = 3
) -> tuple[bool, Dict[str, Any]]:
    """
    Check if an identifier has exceeded rate limits for bypass operations.

    Args:
        identifier: Unique identifier (e.g., approver name)
        max_per_day: Maximum operations allowed per day
        max_per_hour: Maximum operations allowed per hour

    Returns:
        Tuple of (allowed, details_dict)
        - allowed: True if within limits, False if exceeded
        - details: Counts and limits
    """
    rate_log = SECURITY_LOG_DIR / "rate-limits.jsonl"

    # Read existing rate log
    events = []
    if rate_log.exists():
        with open(rate_log, 'r') as f:
            for line in f:
                try:
                    events.append(json.loads(line.strip()))
                except (json.JSONDecodeError, ValueError):
                    pass  # Skip malformed lines

    # Filter events for this identifier
    now = datetime.now()
    day_ago = now.timestamp() - 86400
    hour_ago = now.timestamp() - 3600

    identifier_events = [
        e for e in events
        if e.get("identifier") == identifier
    ]

    # Count recent events
    last_day = [e for e in identifier_events if e.get("timestamp", 0) > day_ago]
    last_hour = [e for e in identifier_events if e.get("timestamp", 0) > hour_ago]

    day_count = len(last_day)
    hour_count = len(last_hour)

    # Check limits
    allowed = day_count < max_per_day and hour_count < max_per_hour

    # Log this check
    check_record = {
        "identifier": identifier,
        "timestamp": now.timestamp(),
        "day_count": day_count,
        "hour_count": hour_count,
        "allowed": allowed
    }
    with open(rate_log, 'a') as f:
        f.write(json.dumps(check_record) + '\n')

    return allowed, {
        "day_count": day_count,
        "day_limit": max_per_day,
        "hour_count": hour_count,
        "hour_limit": max_per_hour,
        "allowed": allowed
    }


def get_recent_bypasses(hours: int = 24) -> List[Dict[str, Any]]:
    """
    Retrieve recent bypass events for review.

    Args:
        hours: Number of hours to look back

    Returns:
        List of bypass event dictionaries
    """
    bypasses = []

    if not SECURITY_LOG.exists():
        return bypasses

    cutoff = datetime.now().timestamp() - (hours * 3600)

    with open(SECURITY_LOG, 'r') as f:
        for line in f:
            try:
                event = json.loads(line.strip())
                if event.get("event_type") == EventType.GATE_BYPASS.value:
                    # Parse ISO timestamp to compare
                    try:
                        event_time = datetime.fromisoformat(event.get("timestamp", ""))
                        if event_time.timestamp() > cutoff:
                            bypasses.append(event)
                    except (ValueError, TypeError):
                        # If timestamp parse fails, include anyway
                        bypasses.append(event)
            except (json.JSONDecodeError, ValueError):
                pass

    return bypasses


def main():
    """CLI for security event logger."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Security event logger for audit trails"
    )
    parser.add_argument("--test", action="store_true", help="Log a test event")
    parser.add_argument("--recent", type=int, default=24, help="Show recent events (hours)")
    parser.add_argument("--check-rate", help="Check rate limits for identifier")
    parser.add_argument("--type", choices=[e.value for e in EventType], help="Event type")
    parser.add_argument("--severity", choices=[s.value for s in Severity], default="info", help="Event severity")
    parser.add_argument("--details", help="JSON string of event details")

    args = parser.parse_args()

    if args.test:
        event = log_security_event(
            event_type=EventType.GATE_BYPASS,
            severity=Severity.INFO,
            details={"test": True, "description": "Test security event"}
        )
        print(f"✓ Test event logged: {event['event_id']}")
        print(f"  Hash: {event['event_hash']}")
        return 0

    if args.check_rate:
        allowed, details = check_rate_limits(args.check_rate)
        print(f"Rate limit check for '{args.check_rate}':")
        print(f"  Last hour: {details['hour_count']}/{details['hour_limit']}")
        print(f"  Last day: {details['day_count']}/{details['day_limit']}")
        print(f"  Allowed: {details['allowed']}")
        return 0 if allowed else 1

    if args.recent:
        events = get_recent_bypasses(args.recent)
        print(f"Recent bypasses (last {args.recent}h): {len(events)}")
        for event in events:
            print(f"  {event.get('timestamp')} - {event.get('details', {}).get('approver', 'unknown')} - {event.get('details', {}).get('task_id', 'unknown')}")
        return 0

    if args.type and args.details:
        try:
            details = json.loads(args.details)
        except json.JSONDecodeError:
            print("Error: --details must be valid JSON")
            return 1

        event = log_security_event(
            event_type=EventType(args.type),
            severity=Severity(args.severity),
            details=details
        )
        print(f"✓ Event logged: {event['event_id']}")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
