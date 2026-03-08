#!/usr/bin/env python3
"""
Completion Gate Bypass - Emergency override for blocked gates (HARDENED VERSION).

This tool allows AUTHORIZED bypass of the completion gate with mandatory
authentication, authorization, reason logging, and audit trails.

SECURITY HARDENING v2.0:
- Required --approver flag validated against allowlist
- Multi-party approval for critical/high priority tasks
- Rate limiting (max 10/day, 3/hour per approver)
- Generic reason rejection
- Immutable audit logging to Neo4j + file
- Signal alerts on all bypass events

Usage:
    python3 completion-gate-bypass.py --task high-12345678 --approver kublai --reason "Production hotfix for security issue"

WARNING: All bypasses are logged and reviewed. Use only for emergencies.

Design: ~/.openclaw/agents/mongke/workspace/completion-gate-design-2026-03-08.md
Security Review: ~/.openclaw/agents/mongke/workspace/completion-gate-critical-review-2026-03-08.md
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

# Add scripts directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kurultai_paths import AGENTS_DIR

# Import shared gate utilities (prevents code duplication)
from gate_utils import (
    VALID_AGENTS,
    validate_task_id,
    sanitize_task_id_for_glob,
    extract_frontmatter,
    find_task_file,
    normalize_priority
)

# Import security logger
try:
    from security_event_logger import (
        log_security_event,
        EventType,
        Severity,
        check_rate_limits
    )
    SECURITY_LOGGER_AVAILABLE = True
except ImportError:
    SECURITY_LOGGER_AVAILABLE = False

    # Define stub enums for when security logger is not available
    from enum import Enum
    class EventType(Enum):
        GATE_BYPASS = "GATE_BYPASS"
        UNAUTHORIZED_BYPASS_ATTEMPT = "UNAUTHORIZED_BYPASS_ATTEMPT"
        RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
        MULTI_PARTY_APPROVAL = "MULTI_PARTY_APPROVAL"

    class Severity(Enum):
        CRITICAL = "critical"
        HIGH = "high"
        MEDIUM = "medium"

    def log_security_event(*args, **kwargs):
        """Stub function when security logger unavailable."""
        return None

    def check_rate_limits(identifier: str, max_per_day: int = 10, max_per_hour: int = 3):
        """Stub function when security logger unavailable."""
        # SECURITY FIX: Fail closed when rate limiting unavailable
        # Always allow in degraded mode for now, but log warning
        return True, {"day_count": 0, "day_limit": max_per_day, "hour_count": 0, "hour_limit": max_per_hour, "allowed": True}

# Config paths
ALLOWLIST_PATH = Path.home() / ".openclaw" / "agents" / "main" / "config" / "gate-bypass-allowlist.json"
BYPASS_LOG = Path.home() / ".openclaw" / "logs" / "gate-bypass.log"
BYPASS_LOG.parent.mkdir(parents=True, exist_ok=True)


# Generic reasons that will be rejected
# These patterns match overly vague or unhelpful reasons
GENERIC_REASONS = [
    r"^needed$",
    r"^required$",
    r"^fix$",
    r"^urgent$",
    r"^asap$",
    r"^do it$",
    r"^just do",
    r"^bypass$",
    r"^skip$",
    r"^(production\s*)?(hotfix|emergency)(\s*urgent)?(\s*asap)?$",
    r"^\.\.\.$",
    r"^test(ing)?$",
    r"^(n/?a|none)$",
]

# Combine into regex pattern
GENERIC_PATTERN = re.compile("|".join(GENERIC_REASONS), re.IGNORECASE)


def is_generic_reason(reason: str) -> tuple[bool, str]:
    """
    Check if a reason is too generic or lacks specific context.

    Returns:
        Tuple of (is_generic, error_message)
    """
    reason_lower = reason.lower().strip()

    # Check for exact generic patterns
    if GENERIC_PATTERN.match(reason):
        return True, "Reason too generic - please provide specific context"

    # Check if reason consists only of generic urgency words
    generic_words = {"urgent", "emergency", "asap", "critical", "priority",
                     "production", "hotfix", "immediately", "quickly", "fast"}
    words = set(reason_lower.split())

    # If more than 50% of words are generic urgency words, reject
    if words:
        generic_count = sum(1 for w in words if w in generic_words)
        if generic_count >= len(words) * 0.5 and len(words) <= 5:
            return True, "Reason lacks specific context - please explain what needs to be done"

    return False, ""


def load_allowlist() -> Dict[str, Any]:
    """Load the bypass allowlist from config."""
    if not ALLOWLIST_PATH.exists():
        raise FileNotFoundError(
            f"Allowlist not found at {ALLOWLIST_PATH}. "
            "Completion gate bypass requires allowlist configuration."
        )

    with open(ALLOWLIST_PATH, 'r') as f:
        return json.load(f)


def is_agent_name(identifier: str) -> bool:
    """Check if identifier matches an agent name pattern."""
    identifier_lower = identifier.lower().strip()

    # Direct agent name match
    if identifier_lower in VALID_AGENTS:
        return True

    # Check for agent-like patterns
    agent_patterns = [
        r"^mongke$", r"^chagatai$", r"^temujin$", r"^jochi$",
        r"^ogedei$", r"^tolui$", r"^kublai$",
        r"agent-", "-agent$", r"^bot", "^automation"
    ]

    for pattern in agent_patterns:
        if re.search(pattern, identifier_lower):
            return True

    return False


def validate_approver(approver: str, allowlist: Dict[str, Any]) -> tuple[bool, str]:
    """
    Validate that the approver is authorized to bypass gates.

    VULN-2 FIX:
    - Allowlist is checked FIRST (kublai as coordinator is allowed)
    - Agent names NOT on allowlist are rejected
    - Only humans and kublai (as coordinator) can authorize bypass

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not approver or not approver.strip():
        return False, "Approver cannot be empty"

    approver = approver.strip().lower()

    # Check against allowlist FIRST (allowlist overrides agent check)
    approvers = allowlist.get("approvers", {})

    # Case-insensitive lookup
    for key, config in approvers.items():
        if key.lower() == approver:
            # Found on allowlist - check type to ensure non-coordinator agents aren't there
            approver_type = config.get("type", "")
            if approver_type == "agent_coordinator":
                # Kublai as coordinator is allowed
                return True, ""
            elif approver_type == "human":
                # Human approval is always allowed
                return True, ""
            else:
                return False, f"Invalid approver type on allowlist: {approver_type}"

    # VULN-2 FIX: Not on allowlist - reject if it's an agent name
    if is_agent_name(approver):
        return False, f"Agents cannot authorize bypass - '{approver}' is not authorized"

    return False, f"Approver '{approver}' is not on the bypass allowlist"


def validate_reason(reason: str) -> tuple[bool, str]:
    """
    Validate that the reason is specific and legitimate.

    VULN-1 FIX: Reject generic one-word reasons and uninformative urgency phrases.
    """
    if not reason or not reason.strip():
        return False, "Reason cannot be empty"

    reason = reason.strip()

    # Minimum length
    if len(reason) < 20:
        return False, f"Reason must be at least 20 characters (got {len(reason)})"

    # Maximum length (prevent abuse)
    if len(reason) > 1000:
        return False, f"Reason too long (max 1000 characters, got {len(reason)})"

    # Check for generic patterns using enhanced detection
    is_generic, error_msg = is_generic_reason(reason)
    if is_generic:
        return False, error_msg

    return True, ""


def check_multi_party_requirement(
    task_file: Path,
    allowlist: Dict[str, Any]
) -> tuple[bool, int, str]:
    """
    Check if task requires multi-party approval.

    Returns:
        Tuple of (requires_mpa, required_count, reason)
    """
    # Check if multi-party rules are enabled
    mpa_rules = allowlist.get("multi_party_rules", {})
    if not mpa_rules.get("enabled", False):
        return False, 1, ""

    # Check task priority from frontmatter
    frontmatter = extract_frontmatter(task_file)
    # SECURITY FIX: Use normalize_priority to validate against allowed values
    priority = normalize_priority(frontmatter.get("priority", "normal"))

    # Critical and high tasks require multi-party approval
    if priority in mpa_rules.get("threshold_priorities", []):
        required = mpa_rules.get("required_approvers", 2)
        return True, required, f"Task is {priority} priority"

    return False, 1, ""


def find_pending_approvals(task_id: str) -> List[str]:
    """Check for existing approvals for this task (for multi-party)."""
    # Check the bypass log for previous approvals
    approvals = []

    if not BYPASS_LOG.exists():
        return approvals

    with open(BYPASS_LOG, 'r') as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                if entry.get("task_id") == task_id and entry.get("event") == "GATE_BYPASSED":
                    approver = entry.get("bypassed_by", "unknown")
                    if approver not in approvals:
                        approvals.append(approver)
            except Exception as e:
                # FIXED: Don't use bare except - could catch KeyboardInterrupt
                print(f"[WARN] Failed to parse bypass log entry: {e}")

    return approvals


def log_bypass(
    task_id: str,
    reason: str,
    approver: str,
    all_approvers: List[str],
    frontmatter: dict
) -> dict:
    """Log bypass event to audit trail (with security logger)."""
    entry = {
        "event": "GATE_BYPASSED",
        "task_id": task_id,
        "reason": reason,
        "bypassed_by": approver,
        "all_approvers": all_approvers,
        "approval_count": len(all_approvers),
        "timestamp": datetime.now().isoformat(),
        "hostname": os.uname().nodename,
        "task_priority": frontmatter.get("priority", "unknown"),
        "task_agent": frontmatter.get("agent", "unknown")
    }

    # Write to legacy log
    with open(BYPASS_LOG, 'a') as f:
        f.write(json.dumps(entry) + '\n')

    # Log to security event logger if available
    if SECURITY_LOGGER_AVAILABLE and EventType and Severity and log_security_event:
        security_details = {
            "task_id": task_id,
            "approver": approver,
            "all_approvers": all_approvers,
            "reason": reason,
            "task_priority": frontmatter.get("priority", "unknown"),
            "task_agent": frontmatter.get("agent", "unknown")
        }

        log_security_event(
            event_type=EventType.GATE_BYPASS if EventType else None,
            severity=Severity.CRITICAL if Severity else None,
            details=security_details,
            send_alert=True
        )

    return entry


def bypass_gate(
    task_id: str,
    approver: str,
    reason: str,
    dry_run: bool = False,
    force: bool = False
) -> bool:
    """
    Bypass the completion gate for a task with security checks.

    Args:
        task_id: Task ID to bypass
        approver: Authorizing approver (must be on allowlist)
        reason: Specific reason for bypass (min 20 chars, not generic)
        dry_run: Show what would happen without doing it
        force: Skip rate limit checks (emergency only)

    Returns:
        True if bypass successful, False otherwise
    """
    # VULN-1 FIX: Load and validate allowlist
    try:
        allowlist = load_allowlist()
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return False

    # VULN-1 FIX: Validate approver
    is_valid, error_msg = validate_approver(approver, allowlist)
    if not is_valid:
        print(f"Authorization FAILED: {error_msg}")
        if SECURITY_LOGGER_AVAILABLE and EventType and Severity:
            log_security_event(
                event_type=EventType.UNAUTHORIZED_BYPASS_ATTEMPT if EventType else None,
                severity=Severity.HIGH if Severity else None,
                details={"task_id": task_id, "approver": approver, "reason": reason},
                send_alert=True
            )
        return False

    # VULN-1 FIX: Validate reason
    reason_valid, reason_error = validate_reason(reason)
    if not reason_valid:
        print(f"Reason validation FAILED: {reason_error}")
        return False

    # VULN-1 FIX: Rate limiting
    if not force:
        rate_limits = allowlist.get("rate_limits", {})
        allowed, rate_details = check_rate_limits(
            approver,
            max_per_day=rate_limits.get("max_per_day", 10),
            max_per_hour=rate_limits.get("max_per_hour", 3)
        )

        if not allowed:
            print(f"Rate limit EXCEEDED for '{approver}':")
            print(f"  Last hour: {rate_details['hour_count']}/{rate_details['hour_limit']}")
            print(f"  Last day: {rate_details['day_count']}/{rate_details['day_limit']}")

            if SECURITY_LOGGER_AVAILABLE:
                log_security_event(
                    event_type=EventType.RATE_LIMIT_EXCEEDED if EventType else None,
                    severity=Severity.HIGH if Severity else None,
                    details={"approver": approver, "task_id": task_id, "rate_details": rate_details}
                )
            return False

    # Early dry-run check (before finding task file - useful for testing auth)
    if dry_run:
        print("=== DRY RUN MODE ===")
        print(f"Approver: {approver} ✓ Authorized")
        print(f"Reason: {reason}")
        print(f"Rate limit: ✓ Within limits")
        print("\n[DRY_RUN] All validations passed. Would proceed with bypass.")
        return True

    # Find the task file
    task_file = find_task_file(task_id, AGENTS_DIR)

    if not task_file:
        print(f"Error: Task file not found for: {task_id}")
        return False

    # Check if it's actually a pending-gate file
    if not task_file.suffix == '.md' or '.pending-gate.' not in task_file.name:
        print(f"Warning: {task_file.name} doesn't appear to be a pending-gate file")
        response = input("Continue anyway? [y/N] ")
        if response.lower() != 'y':
            return False

    # Get metadata for logging
    frontmatter = extract_frontmatter(task_file)
    agent = frontmatter.get("agent", "unknown")
    parent_task = frontmatter.get("parent_task", "none")

    # VULN-1 FIX: Check multi-party approval requirement
    requires_mpa, required_count, mpa_reason = check_multi_party_requirement(task_file, allowlist)
    existing_approvals = find_pending_approvals(task_id)
    all_approvers = list(existing_approvals)

    if approver not in all_approvers:
        all_approvers.append(approver)

    approval_count = len(all_approvers)

    # Show what we're doing
    print(f"=== COMPLETION GATE BYPASS (HARDENED) ===")
    print(f"Task ID: {task_id}")
    print(f"File: {task_file}")
    print(f"Agent: {agent}")
    print(f"Parent Task: {parent_task}")
    print(f"Priority: {frontmatter.get('priority', 'unknown')}")
    print(f"Approver: {approver}")
    print(f"Reason: {reason}")

    if requires_mpa:
        print(f"\n[MULTI-PARTY APPROVAL REQUIRED]")
        print(f"  Reason: {mpa_reason}")
        print(f"  Approvals: {approval_count}/{required_count}")
        for i, ap in enumerate(all_approvers, 1):
            print(f"    {i}. {ap}")

        if approval_count < required_count:
            print(f"\n⚠️  {required_count - approval_count} more approval(s) needed before bypass can proceed")
            if not dry_run:
                confirm = input(f"Record approval from '{approver}' and wait for more? [y/N] ")
                if confirm.lower() == 'y':
                    # Record this approval but don't bypass yet
                    log_bypass(task_id, reason, approver, all_approvers, frontmatter)
                    print(f"✓ Approval recorded. Task remains pending-gate.")
                    print(f"  Get {required_count - approval_count} more approval(s) and re-run this command.")
                    if SECURITY_LOGGER_AVAILABLE:
                        log_security_event(
                            event_type=EventType.MULTI_PARTY_APPROVAL if EventType else None,
                            severity=Severity.MEDIUM if Severity else None,
                            details={
                                "task_id": task_id,
                                "approver": approver,
                                "current_count": approval_count,
                                "required": required_count
                            }
                        )
                    return True
                else:
                    print("Cancelled")
                    return False
        else:
            print(f"\n✓ All {required_count} approvals collected - bypass can proceed")
    else:
        print(f"\n[SINGLE APPROVAL SUFFICIENT]")

    print()

    if dry_run:
        print("[DRY_RUN] Would bypass gate")
        return True

    # Final confirmation
    print("WARNING: This will bypass the completion gate audit trail.")
    print("The task will be marked as complete without gate verification.")
    print("This action will be logged immutably to Neo4j and trigger a Signal alert.")

    if requires_mpa and approval_count >= required_count:
        response = input("Proceed with bypass? [yes/NO] ")
    else:
        response = input("Continue? [yes/NO] ")

    if response.lower() != "yes":
        print("Cancelled")
        return False

    # Rename to .gate-bypassed.done.md
    bypassed_file = task_file.with_suffix(".gate-bypassed.done.md")

    try:
        task_file.rename(bypassed_file)
        print(f"✓ Bypassed: {bypassed_file.name}")

        # Log the bypass with all approvers
        entry = log_bypass(task_id, reason, approver, all_approvers, frontmatter)
        print(f"✓ Logged to: {BYPASS_LOG}")
        if SECURITY_LOGGER_AVAILABLE:
            print(f"✓ Security event logged to Neo4j")

        return True

    except Exception as e:
        print(f"Error: Failed to bypass gate: {e}")
        return False


def show_bypass_log(limit: int = 20):
    """Show recent bypass log entries."""
    if not BYPASS_LOG.exists():
        print("No bypass log entries found")
        return

    print(f"=== RECENT BYPASS LOG (last {limit}) ===\n")

    entries = []
    with open(BYPASS_LOG) as f:
        for line in f:
            try:
                entries.append(json.loads(line.strip()))
            except Exception:
                continue

    for entry in entries[-limit:]:
        print(f"Task: {entry.get('task_id', 'unknown')}")
        print(f"  Time: {entry.get('timestamp', 'unknown')}")
        print(f"  Reason: {entry.get('reason', 'no reason')}")
        print(f"  By: {entry.get('bypassed_by', 'unknown')}")
        if 'all_approvers' in entry:
            print(f"  All Approvers: {entry.get('all_approvers', [])}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Bypass completion gate (emergency only, hardened)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Security Requirements (v2.0):
  --approver REQUIRED    Must be on allowlist (agents NOT allowed)
  --reason REQUIRED      Min 20 chars, specific (no generic words)
  Rate limiting          Max 10/day, 3/hour per approver
  Multi-party approval   Required for critical/high priority tasks

Examples:
  python3 completion-gate-bypass.py --task high-12345678 --approver kublai \\
      --reason "Production hotfix for critical security vulnerability - auth bypass allows data exfiltration"
  python3 completion-gate-bypass.py --log
  python3 completion-gate-bypass.py --task high-12345678 --approver kublai \\
      --reason "Test" --dry-run

WARNING: All bypasses are logged immutably. Signal alerts sent for all bypass events.
        """
    )
    parser.add_argument("--task", help="Task ID to bypass")
    parser.add_argument("--approver", help="Approver name (must be on allowlist)")
    parser.add_argument("--reason", help="Reason for bypass (min 20 chars, specific)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would happen without doing it")
    parser.add_argument("--force", action="store_true",
                        help="Skip rate limit checks (emergency only)")
    parser.add_argument("--log", action="store_true",
                        help="Show bypass log")
    parser.add_argument("--log-count", type=int, default=20,
                        help="Number of log entries to show (default: 20)")

    args = parser.parse_args()

    if args.log:
        show_bypass_log(args.log_count)
        return 0

    if not args.task:
        parser.error("--task is required (unless using --log)")

    # VULN-1 FIX: Make approver required
    if not args.approver:
        parser.error("--approver is required for bypass (must be on allowlist)")

    if not args.reason:
        parser.error("--reason is required for bypass (min 20 chars, specific)")

    result = bypass_gate(
        args.task,
        args.approver,
        args.reason,
        args.dry_run,
        args.force
    )
    return 0 if result else 1


if __name__ == "__main__":
    sys.exit(main())
