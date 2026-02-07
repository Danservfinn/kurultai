"""
Security Tests for Neo4j Privacy Module.

Tests for anonymization, encryption, access control, and injection prevention.
"""

import pytest
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.security import (
    AnonymizationEngine,
    FieldEncryption,
    CypherInjectionPrevention,
    SecureQueryBuilder,
    PrivacyBlockedError,
    DataClassification,
    StorageLocation,
    PRIVACY_BOUNDARIES,
)


# =============================================================================
# Anonymization Tests
# =============================================================================

class TestAnonymizationEngine:
    """Tests for PII detection and anonymization."""

    def test_detect_email(self):
        engine = AnonymizationEngine(salt="test-salt")
        text = "Contact me at john@example.com"
        entities = engine.detect_pii(text)

        assert len(entities) == 1
        assert entities[0].entity_type == "email"
        assert entities[0].value == "john@example.com"

    def test_detect_phone(self):
        engine = AnonymizationEngine(salt="test-salt")
        text = "Call me at 555-123-4567"
        entities = engine.detect_pii(text)

        assert len(entities) == 1
        assert entities[0].entity_type == "phone_us"

    def test_detect_ssn(self):
        engine = AnonymizationEngine(salt="test-salt")
        text = "My SSN is 123-45-6789"
        entities = engine.detect_pii(text)

        ssn_entities = [e for e in entities if e.entity_type == "ssn"]
        assert len(ssn_entities) == 1

    def test_anonymize_reversible(self):
        engine = AnonymizationEngine(salt="test-salt")
        text = "Email john@example.com or call 555-123-4567"

        anonymized, token_map = engine.anonymize(text, reversible=True)

        # Should contain tokens
        assert "TOKEN:" in anonymized
        assert len(token_map) > 0

        # Should be able to restore
        restored = engine.deanonymize(anonymized, token_map)
        assert restored == text

    def test_anonymize_irreversible(self):
        engine = AnonymizationEngine(salt="test-salt")
        text = "Email john@example.com"

        anonymized, token_map = engine.anonymize(text, reversible=False)

        # Should contain replacement markers
        assert "[EMAIL_" in anonymized
        # Token map should be empty for irreversible
        assert len(token_map) == 0

    def test_consistent_replacement(self):
        """Same value should get same replacement with same salt."""
        engine = AnonymizationEngine(salt="test-salt")
        text = "Contact john@example.com or john@example.com"

        entities = engine.detect_pii(text)

        # Should detect both emails
        emails = [e for e in entities if e.entity_type == "email"]
        assert len(emails) == 2

        # Same value should have same replacement
        assert emails[0].replacement == emails[1].replacement

    def test_get_statistics(self):
        engine = AnonymizationEngine(salt="test-salt")
        text = "SSN: 123-45-6789, Email: test@example.com"

        stats = engine.get_statistics(text)

        assert stats["total_entities"] == 2
        assert stats["has_critical"] == True
        assert stats["risk_level"] == "critical"


# =============================================================================
# Encryption Tests
# =============================================================================

class TestFieldEncryption:
    """Tests for field-level encryption."""

    def test_encrypt_decrypt_randomized(self):
        key = "test-key-for-encryption-12345678"
        encryption = FieldEncryption(master_key=key)

        plaintext = "sensitive data"
        encrypted = encryption.encrypt(plaintext, deterministic=False)

        # Should have randomized prefix
        assert encrypted.startswith("ENC:R:")

        # Should decrypt correctly
        decrypted = encryption.decrypt(encrypted)
        assert decrypted == plaintext

    def test_encrypt_decrypt_deterministic(self):
        key = "test-key-for-encryption-12345678"
        encryption = FieldEncryption(master_key=key)

        plaintext = "sensitive data"
        encrypted = encryption.encrypt(plaintext, deterministic=True)

        # Should have deterministic prefix
        assert encrypted.startswith("ENC:D:")

        # Same input should produce same output
        encrypted2 = encryption.encrypt(plaintext, deterministic=True)
        assert encrypted == encrypted2

    def test_different_inputs_different_outputs(self):
        key = "test-key-for-encryption-12345678"
        encryption = FieldEncryption(master_key=key)

        encrypted1 = encryption.encrypt("data1", deterministic=False)
        encrypted2 = encryption.encrypt("data2", deterministic=False)

        assert encrypted1 != encrypted2

    def test_is_encrypted(self):
        key = "test-key-for-encryption-12345678"
        encryption = FieldEncryption(master_key=key)

        assert encryption.is_encrypted("ENC:R:abc123") == True
        assert encryption.is_encrypted("ENC:D:abc123") == True
        assert encryption.is_encrypted("plain text") == False
        assert encryption.is_encrypted("") == False

    def test_invalid_key(self):
        with pytest.raises(ValueError):
            FieldEncryption(master_key=None)


# =============================================================================
# Injection Prevention Tests
# =============================================================================

class TestCypherInjectionPrevention:
    """Tests for Cypher injection prevention."""

    def test_validate_safe_query(self):
        query = "MATCH (t:Task {id: $task_id}) RETURN t"
        result = CypherInjectionPrevention.validate_query(query)

        assert result.is_valid == True
        assert len(result.errors) == 0

    def test_detect_string_interpolation(self):
        query = 'MATCH (t:Task) WHERE t.id = "${user_id}" RETURN t'
        result = CypherInjectionPrevention.validate_query(query)

        assert result.is_valid == False
        assert any("interpolation" in e.lower() for e in result.errors)

    def test_detect_comment_injection(self):
        query = "MATCH (t:Task) RETURN t // DELETE ALL"
        result = CypherInjectionPrevention.validate_query(query)

        assert result.is_valid == False

    def test_sanitize_parameter_string(self):
        value = "test' OR '1'='1"
        sanitized = CypherInjectionPrevention.sanitize_parameter(
            "test_param", value
        )

        # Should be sanitized
        assert "'" not in sanitized or sanitized != value

    def test_sanitize_parameter_type_check(self):
        with pytest.raises(Exception):  # CypherInjectionError
            CypherInjectionPrevention.sanitize_parameter(
                "test_param", {"dict": "value"}
            )

    def test_sanitize_label_valid(self):
        label = CypherInjectionPrevention.sanitize_label("Task")
        assert label == "Task"

    def test_sanitize_label_invalid(self):
        with pytest.raises(Exception):  # CypherInjectionError
            CypherInjectionPrevention.sanitize_label("Task`DELETE")

    def test_sanitize_label_reserved_keyword(self):
        with pytest.raises(Exception):  # CypherInjectionError
            CypherInjectionPrevention.sanitize_label("DELETE")


class TestSecureQueryBuilder:
    """Tests for secure query builder."""

    def test_build_simple_query(self):
        builder = SecureQueryBuilder()
        query, params = (builder
            .match("(t:Task)")
            .where("t.id = $task_id", task_id="123")
            .return_("t")
            .build()
        )

        assert "MATCH (t:Task)" in query
        assert "WHERE" in query
        assert "RETURN" in query
        assert "task_id_" in str(params)

    def test_build_complex_query(self):
        builder = SecureQueryBuilder()
        query, params = (builder
            .match("(t:Task)")
            .where("t.status = $status", status="pending")
            .and_where("t.priority = $priority", priority="high")
            .return_("t.id, t.description")
            .limit(10)
            .build()
        )

        assert "MATCH" in query
        assert "WHERE" in query
        assert "AND" in query
        assert "RETURN" in query
        assert "LIMIT" in query
        assert len(params) == 2

    def test_parameter_sanitization(self):
        builder = SecureQueryBuilder()

        # This should work with valid string
        query, params = (builder
            .match("(t:Task)")
            .where("t.name = $name", name="valid name")
            .build()
        )

        assert "valid name" in str(params.values())

    def test_prevents_injection_in_build(self):
        builder = SecureQueryBuilder()

        # Attempt injection through parameter
        with pytest.raises(Exception):
            (builder
                .match("(t:Task)")
                .where("t.name = $name", name="test' OR '1'='1")
                .build()
            )


# =============================================================================
# Privacy Boundary Tests
# =============================================================================

class TestPrivacyBoundaries:
    """Tests for privacy boundary definitions."""

    def test_task_metadata_boundary(self):
        boundary = PRIVACY_BOUNDARIES["task_metadata"]

        assert boundary.classification == DataClassification.OPERATIONAL
        assert boundary.storage == StorageLocation.NEO4J_SHARED
        assert boundary.anonymization_required == True
        assert boundary.encryption_required == False

    def test_personal_relationships_blocked(self):
        boundary = PRIVACY_BOUNDARIES["personal_relationships"]

        assert boundary.classification == DataClassification.PRIVATE
        assert boundary.storage == StorageLocation.FILE_KUBLAI

    def test_business_ideas_sensitive(self):
        boundary = PRIVACY_BOUNDARIES["business_ideas"]

        assert boundary.classification == DataClassification.SENSITIVE
        assert boundary.encryption_required == True
        assert boundary.anonymization_required == True

    def test_code_patterns_public(self):
        boundary = PRIVACY_BOUNDARIES["code_patterns"]

        assert boundary.classification == DataClassification.PUBLIC
        assert boundary.anonymization_required == False
        assert boundary.encryption_required == False


# =============================================================================
# Integration Tests
# =============================================================================

class TestPrivacyPipeline:
    """Integration tests for the complete privacy pipeline."""

    def test_full_anonymization_pipeline(self):
        """Test complete flow from detection to anonymization."""
        engine = AnonymizationEngine(salt="test-salt")

        # Input with multiple PII types
        text = (
            "Contact Sarah at sarah@example.com or 555-123-4567. "
            "Her SSN is 123-45-6789."
        )

        # Detect
        entities = engine.detect_pii(text)
        assert len(entities) >= 3  # email, phone, SSN

        # Anonymize
        anonymized, _ = engine.anonymize(text, reversible=False)

        # Should not contain original PII
        assert "sarah@example.com" not in anonymized
        assert "555-123-4567" not in anonymized
        assert "123-45-6789" not in anonymized

        # Should contain replacement markers
        assert "[EMAIL_" in anonymized or "[PHONE_" in anonymized

    def test_encryption_pipeline(self):
        """Test encryption and decryption pipeline."""
        key = "test-key-for-encryption-12345678"
        encryption = FieldEncryption(master_key=key)

        # Test data
        sensitive_data = "confidential business strategy"

        # Encrypt
        encrypted = encryption.encrypt(sensitive_data, deterministic=False)

        # Verify encrypted
        assert encrypted != sensitive_data
        assert encryption.is_encrypted(encrypted)

        # Decrypt
        decrypted = encryption.decrypt(encrypted)
        assert decrypted == sensitive_data


# =============================================================================
# Security Checklist Tests
# =============================================================================

def test_neo4j_security_checklist():
    """Verify security checklist items are documented."""
    from tools.security.privacy_boundary import PRE_NEO4J_CHECKLIST

    checklist_items = [
        "raw phone numbers",
        "email addresses",
        "personal names",
        "API keys",
        "credit card",
        "SSN",
        "sender_hash",
    ]

    checklist_lower = PRE_NEO4J_CHECKLIST.lower()

    for item in checklist_items:
        assert item.lower() in checklist_lower, f"Missing checklist item: {item}"


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
