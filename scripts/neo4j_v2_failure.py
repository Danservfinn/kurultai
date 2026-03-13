#!/usr/bin/env python3
"""
neo4j_v2_failure.py — Failure classification: transient vs permanent.

Transient failures are auto-retried (WORKING -> PENDING).
Permanent failures stay FAILED and alert humans.

Usage:
    from neo4j_v2_failure import classify_failure
    error_class, is_transient = classify_failure(return_code, stderr, stdout)
"""

import re
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Error patterns
# ---------------------------------------------------------------------------

# Transient: auto-retry makes sense
_TRANSIENT_PATTERNS = [
    # Network / service issues
    (r"(?i)connection\s*(refused|reset|timed?\s*out)", "NETWORK_ERROR"),
    (r"(?i)service\s*unavailable", "SERVICE_UNAVAILABLE"),
    (r"(?i)502|503|504", "HTTP_ERROR"),
    (r"(?i)ECONNREFUSED|ECONNRESET|ETIMEDOUT", "NETWORK_ERROR"),
    # Rate limiting
    (r"(?i)rate\s*limit|429|too\s*many\s*requests", "RATE_LIMITED"),
    (r"(?i)overloaded|capacity", "OVERLOADED"),
    # Stall / timeout (process hung but may succeed on retry)
    (r"(?i)stall\s*detect|no\s*output", "STALL"),
    (r"(?i)timed?\s*out|timeout", "TIMEOUT"),
    # Temporary resource issues
    (r"(?i)out\s*of\s*memory|oom|cannot\s*allocate", "OOM"),
    (r"(?i)disk\s*full|no\s*space", "DISK_FULL"),
    # Neo4j transient
    (r"(?i)deadlock|TransientError", "DB_TRANSIENT"),
]

# Permanent: don't waste retries
_PERMANENT_PATTERNS = [
    # Authentication / authorization
    (r"(?i)401|403|unauthorized|forbidden|auth.*fail|invalid.*key|invalid.*token", "AUTH_FAILURE"),
    # Bad request / validation
    (r"(?i)400|bad\s*request|invalid.*param|validation.*error", "INVALID_REQUEST"),
    # Model/API issues that won't self-resolve
    (r"(?i)model.*not\s*found|unsupported.*model", "MODEL_NOT_FOUND"),
    (r"(?i)content.*policy|safety.*filter|blocked.*content", "CONTENT_POLICY"),
    # Empty / hollow output (the glm-5 problem)
    (r"(?i)empty.*output|hollow.*completion|no.*substantive", "EMPTY_OUTPUT"),
    # Permission / filesystem
    (r"(?i)permission\s*denied|EACCES", "PERMISSION_DENIED"),
    (r"(?i)file\s*not\s*found|ENOENT|no\s*such\s*file", "FILE_NOT_FOUND"),
    # Script errors
    (r"(?i)SyntaxError|ImportError|ModuleNotFoundError", "CODE_ERROR"),
]


def classify_failure(return_code: int, stderr: str = "",
                     stdout: str = "") -> tuple[str, bool]:
    """Classify a task failure as transient or permanent.

    Args:
        return_code: Process exit code (0 = success, non-zero = failure)
        stderr: Standard error output
        stdout: Standard output (checked for error patterns too)

    Returns:
        (error_class, is_transient) tuple.
        error_class: Short classification string (e.g., "TIMEOUT", "AUTH_FAILURE")
        is_transient: True if auto-retry is worthwhile
    """
    combined = f"{stderr}\n{stdout}"

    # Special case: signal kills (SIGTERM=143, SIGKILL=137)
    if return_code in (137, 143):
        return "KILLED", True  # Process was killed, likely stall detection

    if return_code == 0 and not stderr:
        return "SUCCESS", False  # Not actually a failure

    # Check permanent patterns first (more specific)
    for pattern, error_class in _PERMANENT_PATTERNS:
        if re.search(pattern, combined):
            logger.info(f"Permanent failure: {error_class}")
            return error_class, False

    # Check transient patterns
    for pattern, error_class in _TRANSIENT_PATTERNS:
        if re.search(pattern, combined):
            logger.info(f"Transient failure: {error_class}")
            return error_class, True

    # Fallback classification by return code
    if return_code == 1:
        return "GENERAL_ERROR", True  # Generic error, worth retrying once
    if return_code == 2:
        return "USAGE_ERROR", False  # Bad arguments, permanent
    if return_code >= 128:
        return "SIGNAL", True  # Killed by signal, transient

    return "UNKNOWN", True  # Default to transient (safe: will exhaust retries naturally)


def classify_validation_failure(reason: str) -> tuple[str, bool]:
    """Classify a completion validation failure.

    Validation failures are generally transient — the task can be retried
    with the failure context informing the next attempt.
    """
    if "empty" in reason.lower() or "missing" in reason.lower():
        return "EMPTY_OUTPUT", True
    if "problem" in reason.lower() or "solution" in reason.lower():
        return "INCOMPLETE_REPORT", True
    return "VALIDATION_FAILED", True
