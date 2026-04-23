#!/usr/bin/env python3
"""
PII Scrubber — Reversible tokenization for privacy-safe LLM processing.

Replaces PII patterns with tokens: phone→[PHONE_1], names→[PERSON_1].
Maintains a bidirectional map for de-tokenization (kept local, never sent to LLM).

Usage:
    from pii_scrubber import PIIScrubber

    scrubber = PIIScrubber()
    scrubbed, token_map = scrubber.scrub("Call Danny at +19194133445")
    # scrubbed = "Call [PERSON_1] at [PHONE_1]"
    # token_map = {"[PERSON_1]": "Danny", "[PHONE_1]": "+19194133445"}

    original = scrubber.unscrub(scrubbed, token_map)
    # original = "Call Danny at +19194133445"
"""
from __future__ import annotations

import re
import logging
from typing import Dict, List, Tuple, Optional, Set

logger = logging.getLogger(__name__)

# ============================================================================
# PII detection patterns
# ============================================================================

# Phone numbers (international and US formats)
_PHONE_PATTERNS = [
    re.compile(r'\+\d{10,15}'),                          # +19194133445
    re.compile(r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b'),   # 919-413-3445
    re.compile(r'\(\d{3}\)\s*\d{3}[-.\s]?\d{4}'),        # (919) 413-3445
]

# Email addresses
_EMAIL_PATTERN = re.compile(
    r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
)

# URLs (may contain identifying info)
_URL_PATTERN = re.compile(
    r'https?://[^\s<>"\']+|www\.[^\s<>"\']+',
    re.IGNORECASE,
)

# Social security numbers (US)
_SSN_PATTERN = re.compile(r'\b\d{3}-\d{2}-\d{4}\b')

# Credit card numbers (basic detection)
_CC_PATTERN = re.compile(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b')

# IP addresses
_IP_PATTERN = re.compile(
    r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
)

# Street addresses (basic - number + street name)
_ADDRESS_PATTERN = re.compile(
    r'\b\d+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:St|Ave|Blvd|Dr|Ln|Rd|Way|Ct|Pl|Cir)\b',
    re.IGNORECASE,
)


class PIIScrubber:
    """Reversible PII tokenization."""

    def __init__(self, known_names: Optional[Set[str]] = None):
        """Initialize scrubber.

        Args:
            known_names: Set of known person names to detect. If None,
                         only regex-based detection is used (no name scrubbing
                         without a known names list).
        """
        self._known_names = known_names or set()

    def scrub(
        self,
        text: str,
        extra_names: Optional[List[str]] = None,
    ) -> Tuple[str, Dict[str, str]]:
        """Scrub PII from text, returning scrubbed text and token map.

        Args:
            text: Input text to scrub
            extra_names: Additional names to detect (e.g., from contact list)

        Returns:
            Tuple of (scrubbed_text, token_map) where token_map maps
            tokens like [PHONE_1] back to original values.
        """
        token_map: Dict[str, str] = {}
        counters = {
            "PHONE": 0,
            "EMAIL": 0,
            "URL": 0,
            "SSN": 0,
            "CC": 0,
            "IP": 0,
            "ADDRESS": 0,
            "PERSON": 0,
        }

        result = text

        # Order matters: longer patterns first to avoid partial matches

        # SSN (before phone to avoid overlap)
        result = self._replace_pattern(
            result, _SSN_PATTERN, "SSN", counters, token_map
        )

        # Credit cards (before phone)
        result = self._replace_pattern(
            result, _CC_PATTERN, "CC", counters, token_map
        )

        # Phone numbers
        for pattern in _PHONE_PATTERNS:
            result = self._replace_pattern(
                result, pattern, "PHONE", counters, token_map
            )

        # Email
        result = self._replace_pattern(
            result, _EMAIL_PATTERN, "EMAIL", counters, token_map
        )

        # URLs
        result = self._replace_pattern(
            result, _URL_PATTERN, "URL", counters, token_map
        )

        # IP addresses
        result = self._replace_pattern(
            result, _IP_PATTERN, "IP", counters, token_map
        )

        # Street addresses
        result = self._replace_pattern(
            result, _ADDRESS_PATTERN, "ADDRESS", counters, token_map
        )

        # Known names
        all_names = self._known_names.copy()
        if extra_names:
            all_names.update(extra_names)

        if all_names:
            result = self._replace_names(result, all_names, counters, token_map)

        return result, token_map

    def unscrub(self, scrubbed_text: str, token_map: Dict[str, str]) -> str:
        """Restore PII from token map.

        Args:
            scrubbed_text: Text with [PHONE_1] style tokens
            token_map: Map from tokens to original values

        Returns:
            Original text with PII restored
        """
        result = scrubbed_text
        # Replace longest tokens first to avoid partial replacements
        for token in sorted(token_map.keys(), key=len, reverse=True):
            result = result.replace(token, token_map[token])
        return result

    def _replace_pattern(
        self,
        text: str,
        pattern: re.Pattern,
        pii_type: str,
        counters: Dict[str, int],
        token_map: Dict[str, str],
    ) -> str:
        """Replace regex matches with numbered tokens."""

        def replacer(match):
            value = match.group(0)
            # Check if already tokenized
            for token, orig in token_map.items():
                if orig == value:
                    return token
            counters[pii_type] += 1
            token = f"[{pii_type}_{counters[pii_type]}]"
            token_map[token] = value
            return token

        return pattern.sub(replacer, text)

    def _replace_names(
        self,
        text: str,
        names: Set[str],
        counters: Dict[str, int],
        token_map: Dict[str, str],
    ) -> str:
        """Replace known names with [PERSON_N] tokens."""
        result = text
        # Sort by length (longest first) to avoid partial replacements
        for name in sorted(names, key=len, reverse=True):
            if not name or len(name) < 2:
                continue
            # Case-insensitive word-boundary match
            pattern = re.compile(r'\b' + re.escape(name) + r'\b', re.IGNORECASE)
            matches = pattern.findall(result)
            if matches:
                # Check if already mapped
                existing_token = None
                for token, orig in token_map.items():
                    if orig.lower() == name.lower():
                        existing_token = token
                        break

                if not existing_token:
                    counters["PERSON"] += 1
                    existing_token = f"[PERSON_{counters['PERSON']}]"
                    token_map[existing_token] = name

                result = pattern.sub(existing_token, result)

        return result


if __name__ == "__main__":
    scrubber = PIIScrubber(known_names={"Danny", "Liz"})

    tests = [
        "Call Danny at +19194133445 about the deployment",
        "Email danny@example.com or reach Liz at (919) 555-1234",
        "SSN is 123-45-6789 and card is 4111-1111-1111-1111",
        "Visit https://secret.internal.corp/admin for config",
        "Server at 192.168.1.100 needs reboot",
    ]

    for text in tests:
        scrubbed, token_map = scrubber.scrub(text)
        restored = scrubber.unscrub(scrubbed, token_map)
        print(f"\n  Original:  {text}")
        print(f"  Scrubbed:  {scrubbed}")
        print(f"  Tokens:    {token_map}")
        assert restored == text, f"Round-trip failed: {restored}"
    print("\nAll round-trip tests passed.")
