"""
PII sanitizer for chat summary persistence.

Defense-in-depth layer: strips phone numbers, emails, SSNs, IPs,
credit cards, and street addresses from text before Neo4j write.

Also detects sensitive keywords (passwords, tokens, etc.) that should
block storage entirely — better to lose a summary than leak secrets.
"""

import re

PII_PATTERNS = {
    'phone': r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
    'email': r'\b[\w.+-]+@[\w-]+\.[\w.-]+\b',
    'ssn': r'\b\d{3}-\d{2}-\d{4}\b',
    'ip': r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b',
    'credit_card': r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b',
    'address': r'\b\d+\s+[\w\s]+(?:St|Ave|Blvd|Dr|Rd|Ln|Ct|Way|Circle|Place)\b',
}

SENSITIVE_KEYWORDS = [
    'password', 'secret', 'token', 'api_key', 'private_key',
    'credential', 'ssn', 'social security',
]


def sanitize(text: str) -> str:
    """Strip PII patterns from text. Returns sanitized text."""
    for name, pattern in PII_PATTERNS.items():
        text = re.sub(pattern, f'[{name.upper()}_REDACTED]', text, flags=re.IGNORECASE)
    return text


def contains_sensitive_content(text: str) -> bool:
    """Check if text contains sensitive keywords that should block storage entirely."""
    lower = text.lower()
    return any(kw in lower for kw in SENSITIVE_KEYWORDS)
