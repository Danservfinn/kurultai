#!/usr/bin/env python3
from __future__ import annotations
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
    # Process enforcement violations (FIX 2026-03-23: R008 was falling through to GENERAL_ERROR)
    # R008_VIOLATION = required skill not invoked within timeout. Permanent: retrying won't
    # fix a missing skill invocation; the task needs re-dispatch with correct instructions.
    # Error format: "R008_VIOLATION: Required skill '/<name>' was not invoked within Ns"
    (r"(?i)R008_VIOLATION|required\s+skill.*not\s+invoked", "R008_VIOLATION"),
]

# --- Retry Budget by Error Class ---
# Determines max retries for each error category.
# Transient errors get more retries; permanent errors get 0.
RETRY_BUDGET = {
    # Transient: worth retrying
    "NETWORK_ERROR": 3,
    "SERVICE_UNAVAILABLE": 3,
    "HTTP_ERROR": 2,
    "RATE_LIMITED": 2,
    "OVERLOADED": 2,
    "STALL": 1,
    "TIMEOUT": 2,
    "OOM": 1,
    "DISK_FULL": 1,
    "DB_TRANSIENT": 3,
    "KILLED": 2,
    "SIGNAL": 2,
    "GENERAL_ERROR": 1,
    "UNKNOWN": 1,
    # Validation (transient but limited)
    "EMPTY_OUTPUT": 1,
    "INCOMPLETE_REPORT": 1,
    "VALIDATION_FAILED": 1,
    # Permanent: don't waste retries
    "AUTH_FAILURE": 0,
    "INVALID_REQUEST": 0,
    "MODEL_NOT_FOUND": 0,
    "CONTENT_POLICY": 0,
    "PERMISSION_DENIED": 0,
    "FILE_NOT_FOUND": 0,
    "CODE_ERROR": 0,
    "R008_VIOLATION": 0,
    "USAGE_ERROR": 0,
    "SUCCESS": 0,
    "prompt_injection": 0,
}

DEFAULT_RETRY_BUDGET = 1  # Default for unclassified errors


def get_retry_budget(error_class: str) -> int:
    """Get max retry count for a given error class.

    Returns:
        Maximum number of retries allowed for this error type.
    """
    return RETRY_BUDGET.get(error_class, DEFAULT_RETRY_BUDGET)


# --- Error Category Taxonomy ---
# Groups error classes into higher-level categories for reporting.
ERROR_CATEGORIES = {
    "infrastructure": {"NETWORK_ERROR", "SERVICE_UNAVAILABLE", "HTTP_ERROR",
                       "OOM", "DISK_FULL", "DB_TRANSIENT", "KILLED", "SIGNAL"},
    "rate_limiting": {"RATE_LIMITED", "OVERLOADED"},
    "timeout": {"TIMEOUT", "STALL"},
    "auth": {"AUTH_FAILURE"},
    "code": {"CODE_ERROR", "USAGE_ERROR", "R008_VIOLATION", "FILE_NOT_FOUND"},
    "input": {"INVALID_REQUEST", "CONTENT_POLICY", "EMPTY_OUTPUT",
              "INCOMPLETE_REPORT", "VALIDATION_FAILED", "MODEL_NOT_FOUND"},
    "permission": {"PERMISSION_DENIED", "prompt_injection"},
}


def categorize_error(error_class: str) -> str:
    """Map an error class to its higher-level category.

    Returns:
        Category name (e.g., 'infrastructure', 'rate_limiting', 'timeout').
    """
    for category, classes in ERROR_CATEGORIES.items():
        if error_class in classes:
            return category
    return "unknown"


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
