#!/usr/bin/env python3
"""
Response Guard — Post-generation filter for group chat responses.

Blocks PII patterns (phone numbers, file paths, UUIDs, credentials) from
group responses and enforces length caps. DM responses pass through unfiltered.

Usage:
    from response_guard import guard_response
    safe = guard_response(response, is_group=True)
"""

import json
import re
import logging
import unicodedata
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

GUARD_LOG = Path("/Users/kublai/.openclaw/logs/response-guard-activations.jsonl")


def _log_activation(redaction_count: int, is_fallback: bool, patterns_hit: list):
    """Log ResponseGuard activations. Atomic single-write for concurrent safety."""
    try:
        GUARD_LOG.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now().isoformat(),
            "redaction_count": redaction_count,
            "is_fallback": is_fallback,
            "patterns_hit": patterns_hit[:5],
        }
        with open(GUARD_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")
            f.flush()
    except Exception:
        pass  # Never fail message handling due to logging


def _normalize_text(text: str) -> str:
    """Normalize Unicode to prevent regex bypass via homoglyphs/zero-width chars."""
    # NFKC normalizes full-width chars to ASCII equivalents
    text = unicodedata.normalize('NFKC', text)
    # Strip all Unicode format characters (Cf category): zero-width joiners,
    # word joiners, directional marks, variation selectors, and more
    text = ''.join(c for c in text if unicodedata.category(c) != 'Cf')
    return text

# Max character length for group responses
GROUP_MAX_CHARS = 500

# Patterns to redact from group responses (order matters — more specific first)
REDACT_PATTERNS = [
    # UUIDs (before phone numbers — UUIDs contain digit sequences that phone regex can match)
    (re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', re.I), "[id]"),
    # API keys / tokens (common patterns — underscores allowed in token body)
    (re.compile(r'(?:sk|pk|api|key|token|secret|bearer)[_\-][a-zA-Z0-9_\-]{12,}', re.I), "[credential]"),
    # Phone numbers (US format: +1XXXXXXXXXX, (XXX) XXX-XXXX, XXX-XXX-XXXX)
    (re.compile(r'\+?\d[\d\s\-()]{8,14}\d'), "[phone]"),
    # File paths (Unix-style)
    (re.compile(r'/(?:Users|home|var|tmp|opt|etc)/[\w./\-]+'), "[path]"),
    # Email addresses
    (re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+'), "[email]"),
    # IP addresses
    (re.compile(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b'), "[ip]"),
]

# Private topic keywords that shouldn't appear in group responses
PRIVATE_TOPIC_PATTERNS = [
    re.compile(r'\b(?:your|their)\s+(?:doctor|therapist|medication|diagnosis|prescription|surgery)\b', re.I),
    re.compile(r'\b(?:your|their)\s+(?:salary|debt|loan|mortgage|bank\s*account)\b', re.I),
    re.compile(r'\b(?:your|their)\s+(?:divorce|custody|lawyer)\b', re.I),
    re.compile(r'\b(?:you\s+mentioned\s+in\s+(?:our|a)\s+(?:DM|private|direct))\b', re.I),
    re.compile(r'\b(?:in\s+our\s+(?:private|direct)\s+(?:conversation|chat|message))\b', re.I),
]

# Fallback response when too many redactions occur
FALLBACK_RESPONSE = "Let's discuss that in a DM."
MAX_REDACTIONS = 3


def guard_response(response: str, is_group: bool = False) -> str:
    """Filter a response for group safety. DM responses pass through unmodified.

    Args:
        response: The generated response text
        is_group: True if this response will be sent to a group chat

    Returns:
        Filtered response (or original if DM)
    """
    if not is_group:
        return response

    if not response:
        return response

    redaction_count = 0
    patterns_hit = []

    # Normalize Unicode to catch homoglyph/zero-width bypasses
    filtered = _normalize_text(response)
    for pattern, replacement in REDACT_PATTERNS:
        matches = pattern.findall(filtered)
        if matches:
            redaction_count += len(matches)
            patterns_hit.append(replacement)
            filtered = pattern.sub(replacement, filtered)

    # Check for private topic references
    for pattern in PRIVATE_TOPIC_PATTERNS:
        if pattern.search(filtered):
            redaction_count += 1
            patterns_hit.append("[private topic]")
            filtered = pattern.sub("[private topic]", filtered)

    # If too many redactions, the response is probably leaking private context
    if redaction_count > MAX_REDACTIONS:
        logger.warning(f"ResponseGuard: {redaction_count} redactions — falling back to safe response")
        _log_activation(redaction_count, True, patterns_hit)
        return FALLBACK_RESPONSE

    # Log non-fallback activations
    if redaction_count > 0:
        _log_activation(redaction_count, False, patterns_hit)

    # Enforce length cap
    if len(filtered) > GROUP_MAX_CHARS:
        # Try to break at a sentence boundary
        limit = GROUP_MAX_CHARS - 3  # Leave room for "..."
        truncated = filtered[:limit]
        last_period = truncated.rfind(".")
        last_question = truncated.rfind("?")
        last_exclaim = truncated.rfind("!")
        best_break = max(last_period, last_question, last_exclaim)
        if best_break > limit * 0.5:
            filtered = truncated[:best_break + 1]
        else:
            filtered = truncated.rstrip() + "..."

    # Ensure no partial redaction tokens after truncation
    if '[' in filtered and filtered.count('[') != filtered.count(']'):
        # Find last complete token
        last_open = filtered.rfind('[')
        if last_open > len(filtered) * 0.5:
            filtered = filtered[:last_open].rstrip()

    return filtered


if __name__ == "__main__":
    # Self-test
    print("ResponseGuard self-test:")

    tests = [
        ("Call +19194133445 for info", True, "+1919", False),
        ("Check /Users/kublai/file.txt", True, "/Users/", False),
        ("The UUID is 550e8400-e29b-41d4-a716-446655440000", True, "550e8400", False),
        ("Use sk_live_abc123def456ghi789", True, "sk_live", False),
        ("Call +19194133445 for info", False, "+19194133445", True),  # DM: unchanged
        ("x" * 600, True, None, None),  # Length check
    ]

    for text, is_group, should_not_contain, should_contain in tests:
        result = guard_response(text, is_group=is_group)
        ok = True
        if should_not_contain and should_not_contain in result:
            ok = False
        if should_contain and should_contain not in result:
            ok = False
        if is_group and len(result) > GROUP_MAX_CHARS:
            ok = False
        status = "OK" if ok else "FAIL"
        print(f"  [{status}] is_group={is_group}: '{text[:40]}...' → '{result[:60]}...'")
