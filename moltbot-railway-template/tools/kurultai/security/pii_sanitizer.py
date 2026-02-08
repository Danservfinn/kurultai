"""PII Sanitizer for Kurultai v0.2.

Detects and redacts personally identifiable information from text
before it enters the agent pipeline or gets stored in Neo4j.

Usage:
    sanitizer = PIISanitizer()
    clean = sanitizer.sanitize("Call me at +15165643945")
    # Returns: "Call me at [REDACTED_PHONE]"
"""

import re
from typing import Dict, List, Optional, Tuple


class PIISanitizer:
    """Sanitizes text by detecting and redacting PII patterns.

    Supports phone numbers, email addresses, SSNs, credit card numbers,
    IP addresses, and API keys/tokens.
    """

    PATTERNS: Dict[str, str] = {
        "phone": r"\+\d{7,15}",
        "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
        "credit_card": r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
        "ipv4": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
        "api_key": r"\b(?:sk-|pk-|ak-|bearer\s+)[A-Za-z0-9\-_]{20,}\b",
    }

    def __init__(self, extra_patterns: Optional[Dict[str, str]] = None):
        """Initialize with optional extra patterns.

        Args:
            extra_patterns: Additional {name: regex} patterns to detect.
        """
        self._patterns = dict(self.PATTERNS)
        if extra_patterns:
            self._patterns.update(extra_patterns)
        self._compiled = {
            name: re.compile(pattern, re.IGNORECASE)
            for name, pattern in self._patterns.items()
        }

    def sanitize(self, text: str) -> str:
        """Remove all detected PII from text.

        Args:
            text: Input text potentially containing PII.

        Returns:
            Text with PII replaced by [REDACTED_TYPE] placeholders.
        """
        if not text:
            return text

        result = text
        for pii_type, compiled in self._compiled.items():
            result = compiled.sub(f"[REDACTED_{pii_type.upper()}]", result)
        return result

    def detect(self, text: str) -> List[Tuple[str, str, int, int]]:
        """Detect PII in text without modifying it.

        Args:
            text: Input text to scan.

        Returns:
            List of (pii_type, matched_text, start, end) tuples.
        """
        if not text:
            return []

        findings = []
        for pii_type, compiled in self._compiled.items():
            for match in compiled.finditer(text):
                findings.append((pii_type, match.group(), match.start(), match.end()))
        return sorted(findings, key=lambda x: x[2])

    def has_pii(self, text: str) -> bool:
        """Check if text contains any PII.

        Args:
            text: Input text to check.

        Returns:
            True if any PII pattern matches.
        """
        if not text:
            return False
        return any(compiled.search(text) for compiled in self._compiled.values())
