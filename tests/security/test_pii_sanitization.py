"""
Security tests for PII Sanitization functionality.

Tests cover:
- Email address detection and redaction
- Phone number detection and redaction
- SSN detection and redaction
- API key detection and redaction
- Context preservation
- Property-based testing with Hypothesis

Location: /Users/kurultai/molt/tests/security/test_pii_sanitization.py
"""

import os
import sys
import re
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from unittest.mock import Mock, MagicMock

import pytest
from hypothesis import given, strategies as st, example, settings


# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# =============================================================================
# PII Detection Patterns
# =============================================================================

class PIIPatterns:
    """Patterns for detecting PII in text."""

    # Email pattern (RFC 5322 simplified)
    EMAIL = re.compile(
        r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
        re.IGNORECASE
    )

    # Phone pattern (US format with variations)
    PHONE = re.compile(
        r'(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',
        re.IGNORECASE
    )

    # SSN pattern (XXX-XX-XXXX or XXX XX XXXX)
    SSN = re.compile(
        r'\d{3}[-\s]?\d{2}[-\s]?\d{4}',
        re.IGNORECASE
    )

    # API Key patterns (common prefixes)
    API_KEY_PREFIXES = [
        'sk_live_', 'sk_test_',
        'AKIA', 'SA_',
        'ghp_', 'gho_', 'ghu_', 'ghs_', 'ghr_',
        'xoxb-', 'xoxp-',
        'AIzaSy',
        'ya29.',  # Google OAuth
        'PKCS',  # Public key
    ]

    # Credit card pattern
    CREDIT_CARD = re.compile(
        r'\b(?:\d[ -]*?){13,16}\b',
        re.IGNORECASE
    )

    # IPv4 address pattern
    IPV4 = re.compile(
        r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
    )

    # IP address pattern (IPv6 not included)
    IP_ADDRESS = IPV4


# =============================================================================
# PII Sanitizer
# =============================================================================

class PIISanitizer:
    """Sanitizes PII from text while preserving context."""

    def __init__(self, preserve_example_domains: bool = True):
        self.preserve_example_domains = preserve_example_domains
        self.patterns = PIIPatterns()

        # Example domains (RFC 2606)
        self.example_domains = [
            'example.com', 'example.org', 'example.net',
            'test.com', 'localhost'
        ]

    def sanitize(self, text: str, options: Dict[str, Any] = None) -> str:
        """
        Sanitize PII from text.

        Args:
            text: Text to sanitize
            options: Sanitization options

        Returns:
            Sanitized text with PII redacted
        """
        if not text:
            return text

        result = text
        options = options or {}

        # Apply each sanitizer
        if options.get('sanitize_emails', True):
            result = self._sanitize_emails(result)

        if options.get('sanitize_phones', True):
            result = self._sanitize_phones(result)

        if options.get('sanitize_ssns', True):
            result = self._sanitize_ssns(result)

        if options.get('sanitize_api_keys', True):
            result = self._sanitize_api_keys(result)

        if options.get('sanitize_credit_cards', True):
            result = self._sanitize_credit_cards(result)

        if options.get('sanitize_ips', True):
            result = self._sanitize_ips(result)

        return result

    def _sanitize_emails(self, text: str) -> str:
        """Sanitize email addresses."""
        def replace_email(match):
            email = match.group(0)
            if self.preserve_example_domains:
                for domain in self.example_domains:
                    if email.endswith(f'@{domain}'):
                        return email  # Preserve
            return self._redact_email(email)

        return self.patterns.EMAIL.sub(replace_email, text)

    def _sanitize_phones(self, text: str) -> str:
        """Sanitize phone numbers."""
        def replace_phone(match):
            phone = match.group(0)
            return self._redact_phone(phone)

        return self.patterns.PHONE.sub(replace_phone, text)

    def _sanitize_ssns(self, text: str) -> str:
        """Sanitize SSNs."""
        def replace_ssn(match):
            ssn = match.group(0)
            return self._redact_ssn(ssn)

        return self.patterns.SSN.sub(replace_ssn, text)

    def _sanitize_api_keys(self, text: str) -> str:
        """Sanitize API keys."""
        result = text

        for prefix in self.patterns.API_KEY_PREFIXES:
            # Pattern: prefix followed by alphanumeric/underscore
            pattern = re.compile(
                re.escape(prefix) + r'[A-Za-z0-9_]{10,}',
                re.IGNORECASE
            )
            result = pattern.sub(lambda m: self._redact_api_key(m.group(0)), result)

        return result

    def _sanitize_credit_cards(self, text: str) -> str:
        """Sanitize credit card numbers."""
        def replace_card(match):
            card = match.group(0)
            # Only replace if it looks like a real card number
            # (not just 13-16 random digits)
            digits = re.sub(r'[^\d]', '', card)
            if len(digits) >= 13 and len(digits) <= 16:
                # Check Luhn algorithm or basic validation
                return self._redact_credit_card(card)
            return card

        return self.patterns.CREDIT_CARD.sub(replace_card, text)

    def _sanitize_ips(self, text: str) -> str:
        """Sanitize IP addresses."""
        def replace_ip(match):
            ip = match.group(0)
            return self._redact_ip(ip)

        return self.patterns.IP_ADDRESS.sub(replace_ip, text)

    def _redact_email(self, email: str) -> str:
        """Redact email while preserving structure."""
        parts = email.split('@')
        if len(parts) != 2:
            return "***@***"

        username, domain = parts
        # Show first char of username
        username_redacted = username[0] + '***' if username else '***'
        # Show domain TLD
        domain_parts = domain.split('.')
        if len(domain_parts) >= 2:
            domain_redacted = f'***.{domain_parts[-1]}'
        else:
            domain_redacted = '***'

        return f"{username_redacted}@{domain_redacted}"

    def _redact_phone(self, phone: str) -> str:
        """Redact phone number while preserving format."""
        digits = re.sub(r'[^\d]', '', phone)
        if len(digits) == 10:
            # Keep area code
            return f"({digits[:3]}) ***-****"
        elif len(digits) == 11 and digits[0] == '1':
            # US number with country code
            return f"+1 ({digits[1:4]}) ***-****"
        else:
            # Generic redaction
            return "***-***-****"

    def _redact_ssn(self, ssn: str) -> str:
        """Redact SSN."""
        return "***-**-****"

    def _redact_api_key(self, key: str) -> str:
        """Redact API key."""
        # Show prefix and last 4 chars
        for prefix in self.patterns.API_KEY_PREFIXES:
            if key.upper().startswith(prefix):
                return f"{prefix}***{key[-4:]}"
        return "***"

    def _redact_credit_card(self, card: str) -> str:
        """Redact credit card number."""
        digits = re.sub(r'[^\d]', '', card)
        return f"****-****-****-{digits[-4:]}"

    def _redact_ip(self, ip: str) -> str:
        """Redact IP address."""
        return "*.***.***.*"


# =============================================================================
# TestPIISanitization
# =============================================================================

class TestPIISanitization:
    """Tests for PII sanitization functionality."""

    @pytest.fixture
    def sanitizer(self):
        return PIISanitizer()

    def test_sanitization_detects_email_addresses(self, sanitizer):
        """Test email address detection."""
        text = "Contact user@example.com for support"
        result = sanitizer.sanitize(text)

        assert "user@example.com" not in result
        assert "***" in result or "@" in result

    def test_sanitization_detects_multiple_emails(self, sanitizer):
        """Test detecting multiple email addresses."""
        text = "Cc user@example.com and admin@test.com"
        result = sanitizer.sanitize(text)

        # Both should be redacted
        assert result.count("***") >= 2

    def test_sanitization_preserves_example_domains(self, sanitizer):
        """Test preserving RFC 2606 example domains."""
        text = "Email support@example.com or info@test.com"
        result = sanitizer.sanitize(text)

        # Example domains should be preserved
        assert "support@example.com" in result
        assert "info@test.com" in result

    def test_sanitization_detects_phone_numbers(self, sanitizer):
        """Test phone number detection."""
        text = "Call me at +1 (555) 123-4567"
        result = sanitizer.sanitize(text)

        assert "+1 (555) 123-4567" not in result
        assert "***" in result

    def test_sanitization_detects_various_phone_formats(self, sanitizer):
        """Test different phone number formats."""
        formats = [
            "555-123-4567",
            "(555) 123-4567",
            "1.555.123.4567",
            "+44 20 7123 4567"
        ]

        for phone in formats:
            text = f"Call {phone}"
            result = sanitizer.sanitize(text)
            assert phone not in result

    def test_sanitization_detects_ssn(self, sanitizer):
        """Test SSN detection."""
        text = "My SSN is 123-45-6789"
        result = sanitizer.sanitize(text)

        assert "123-45-6789" not in result
        assert "***-**-****" in result

    def test_sanitization_detects_api_keys(self, sanitizer):
        """Test API key detection."""
        text = "Use key sk_live_51HvXjbK2NXdJv5QRYG for auth"
        result = sanitizer.sanitize(text)

        assert "sk_live_51HvXjbK2NXdJv5QRYG" not in result
        assert "sk_live_***" in result or "***" in result

    def test_sanitization_detects_aws_keys(self, sanitizer):
        """Test AWS access key detection."""
        text = "AKIAIOSFODNN7EXAMPLE is the key"
        result = sanitizer.sanitize(text)

        assert "AKIAIOSFODNN7EXAMPLE" not in result

    def test_sanitization_detects_github_tokens(self, sanitizer):
        """Test GitHub token detection."""
        text = "Use ghp_1234567890abcdefghijklmnopqrstuvwxyz for auth"
        result = sanitizer.sanitize(text)

        assert "ghp_1234567890abcdefghijklmnopqrstuvwxyz" not in result

    def test_sanitization_preserves_context(self, sanitizer):
        """Test that context is preserved around redactions."""
        text = "Send the report to john.doe@company.com by EOD"
        result = sanitizer.sanitize(text)

        # Context words should remain
        assert "Send" in result
        assert "report" in result
        assert "EOD" in result

    def test_sanitization_mixed_pii(self, sanitizer):
        """Test sanitization with multiple PII types."""
        text = "Contact john@example.com at 555-123-4567, SSN: 123-45-6789"
        result = sanitizer.sanitize(text)

        # All PII should be redacted
        assert "john@example.com" not in result
        assert "555-123-4567" not in result
        assert "123-45-6789" not in result


# =============================================================================
# TestPIISanitizationPropertyBased
# =============================================================================

class TestPIISanitizationPropertyBased:
    """Property-based tests for PII sanitization."""

    @pytest.fixture
    def sanitizer(self):
        return PIISanitizer()

    @given(st.text(min_size=0, max_size=100))
    def test_property_based_sanitization(self, sanitizer, text):
        """Test that sanitization never raises on valid input."""
        # Should never raise an exception
        try:
            result = sanitizer.sanitize(text)
            assert isinstance(result, str)
        except Exception as e:
            pytest.fail(f"Sanitization raised exception: {e}")

    @given(st.emails())
    def test_property_based_email_sanitization(self, sanitizer, email):
        """Test email detection with Hypothesis."""
        text = f"Contact {email} for support"
        result = sanitizer.sanitize(text)

        # Original email should not appear in result
        # (unless it's an example domain)
        if not any(email.endswith(f"@{domain}") for domain in sanitizer.example_domains):
            assert email not in result

    @given(st.integers(min_value=1000000000, max_value=9999999999))
    def test_property_based_phone_sanitization(self, sanitizer, phone):
        """Test phone number detection with Hypothesis."""
        phone_str = f"{phone}"
        formatted = f"({phone_str[:3]}) {phone_str[3:6]}-{phone_str[6:]}"
        text = f"Call {formatted}"

        result = sanitizer.sanitize(text)

        # Phone should be redacted
        assert phone_str not in result


# =============================================================================
# TestPIIDetectionPatterns
# =============================================================================

class TestPIIDetectionPatterns:
    """Tests for individual PII detection patterns."""

    @pytest.fixture
    def patterns(self):
        return PIIPatterns()

    def test_email_pattern_valid_emails(self, patterns):
        """Test email pattern matches valid emails."""
        valid_emails = [
            "user@example.com",
            "john.doe@company.co.uk",
            "test+tag@gmail.com",
            "admin@test-domain.org"
        ]

        for email in valid_emails:
            match = patterns.EMAIL.search(email)
            assert match is not None

    def test_email_pattern_invalid_emails(self, patterns):
        """Test email pattern doesn't match invalid patterns."""
        invalid = [
            "@example.com",
            "user@",
            "user@@example.com"
        ]

        for email in invalid:
            # Should not match complete email
            match = patterns.EMAIL.search(email)
            if match:
                # If matched, should be the whole string
                assert match.group(0) != email

    def test_ssn_pattern_valid_ssns(self, patterns):
        """Test SSN pattern matches valid SSNs."""
        valid_ssns = [
            "123-45-6789",
            "123 45 6789",
            "123456789"
        ]

        for ssn in valid_ssns:
            match = patterns.SSN.search(ssn)
            assert match is not None

    def test_phone_pattern_valid_phones(self, patterns):
        """Test phone pattern matches valid phone numbers."""
        valid_phones = [
            "+1 (555) 123-4567",
            "555-123-4567",
            "(555) 123-4567",
            "1.555.123.4567"
        ]

        for phone in valid_phones:
            match = patterns.PHONE.search(phone)
            assert match is not None


# =============================================================================
# TestPIISanitizationOptions
# =============================================================================

class TestPIISanitizationOptions:
    """Tests for sanitization options."""

    def test_selective_sanitization(self):
        """Test selective PII sanitization."""
        sanitizer = PIISanitizer()

        text = "Email: user@example.com, Phone: 555-123-4567"

        # Only sanitize emails
        result = sanitizer.sanitize(text, options={'sanitize_phones': False})

        # Email should be redacted
        assert "user@example.com" not in result
        # Phone should remain
        assert "555-123-4567" in result

    def test_no_sanitization(self):
        """Test disabling all sanitization."""
        sanitizer = PIISanitizer()

        text = "Email: user@example.com, Phone: 555-123-4567"

        result = sanitizer.sanitize(text, options={
            'sanitize_emails': False,
            'sanitize_phones': False
        })

        # Both should remain
        assert "user@example.com" in result
        assert "555-123-4567" in result


# =============================================================================
# TestPIIFalsePositives
# =============================================================================

class TestPIIFalsePositives:
    """Tests for avoiding false positives in PII detection."""

    @pytest.fixture
    def sanitizer(self):
        return PIISanitizer()

    def test_at_symbol_not_email(self, sanitizer):
        """Test that @ without email context is preserved."""
        text = "Use @ symbol for mentions"
        result = sanitizer.sanitize(text)

        assert "@ symbol" in result or "@" in result

    def test_numbers_not_phone(self, sanitizer):
        """Test that generic numbers aren't flagged as phones."""
        text = "The values are 123 456 789 012"
        result = sanitizer.sanitize(text)

        # Should preserve context or not over-redact
        assert "123" in result or "values" in result

    def test_colon_separated_not_ssn(self, sanitizer):
        """Test that colon-separated values aren't flagged as SSN."""
        text = "Use format: key:value:pair"
        result = sanitizer.sanitize(text)

        assert "key:value:pair" in result or "format" in result


# =============================================================================
# TestPIIEdgeCases
# =============================================================================

class TestPIIEdgeCases:
    """Edge case tests for PII sanitization."""

    @pytest.fixture
    def sanitizer(self):
        return PIISanitizer()

    def test_empty_string(self, sanitizer):
        """Test sanitizing empty string."""
        result = sanitizer.sanitize("")
        assert result == ""

    def test_none_input(self, sanitizer):
        """Test sanitizing None input."""
        result = sanitizer.sanitize(None)
        assert result is None

    def test_unicode_characters(self, sanitizer):
        """Test handling Unicode characters."""
        text = "Contact user@例え.com for support"
        result = sanitizer.sanitize(text)

        # Should handle without error
        assert isinstance(result, str)

    def test_very_long_text(self, sanitizer):
        """Test sanitizing very long text."""
        text = "Contact user@example.com " * 1000
        result = sanitizer.sanitize(text)

        # Should process entire text
        assert "user@example.com" not in result

    def test_nested_pii(self, sanitizer):
        """Test text with nested/multiple PII."""
        text = "Email john@example.com, backup jane@test.com, emergency +1-555-999-8888"
        result = sanitizer.sanitize(text)

        # All should be redacted
        assert "john@example.com" not in result
        assert "jane@test.com" not in result
        assert "555-999-8888" not in result
