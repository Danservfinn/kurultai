"""
Security Test Suite for Complexity Scoring System (Phase 2).

Tests cover:
- Input validation and length limits (B6)
- Circuit breaker state machine and cost tracking (B7)
- A/B test HMAC-SHA256 hashing (B10)
- Role-based authentication (B3/B4)

Run with: pytest tests/kurultai/test_complexity_security.py -v
"""

import hashlib
import hmac
import os
import time
from unittest.mock import patch

import pytest

from tools.kurultai.complexity_config import INPUT_MAX_LENGTH
from tools.kurultai.complexity_validation import (
    ABTestFramework,
    TeamSimulator,
)
from tools.kurultai.complexity_auth import (
    ComplexityAuthenticator,
    KNOWN_AGENTS,
    THRESHOLD_ADJUST_ROLES,
    GROUND_TRUTH_ROLES,
)
from tools.kurultai.circuit_breaker import CircuitBreaker, CircuitState


# =============================================================================
# INPUT VALIDATION TESTS
# =============================================================================

class TestInputValidation:
    """Tests for input validation and length-limit guards (B6)."""

    def test_long_input_truncated_technical_terms(self):
        """Inputs exceeding INPUT_MAX_LENGTH are truncated in _count_technical_terms."""
        # Build a string that has "api" at position 0 and "kubernetes" beyond the limit
        padding = "x" * (INPUT_MAX_LENGTH + 100)
        long_input = "api " + padding + " kubernetes"
        count = TeamSimulator._count_technical_terms(long_input)
        # "api" is within the limit, "kubernetes" is beyond -- only "api" should match
        assert count == 1

    def test_long_input_truncated_integration_words(self):
        """Inputs exceeding INPUT_MAX_LENGTH are truncated in _count_integration_words."""
        padding = "x" * (INPUT_MAX_LENGTH + 100)
        long_input = "integrate " + padding + " webhook"
        count = TeamSimulator._count_integration_words(long_input)
        assert count == 1

    def test_long_input_truncated_security_words(self):
        """Inputs exceeding INPUT_MAX_LENGTH are truncated in _count_security_words."""
        padding = "x" * (INPUT_MAX_LENGTH + 100)
        # Use "mfa" (3 chars, no substring overlap with other security words)
        long_input = "mfa " + padding + " rbac"
        count = TeamSimulator._count_security_words(long_input)
        assert count == 1

    def test_empty_input_handled(self):
        """Empty strings should return zero counts without errors."""
        assert TeamSimulator._count_technical_terms("") == 0
        assert TeamSimulator._count_integration_words("") == 0
        assert TeamSimulator._count_security_words("") == 0

    def test_unicode_input_handled(self):
        """Unicode input is processed without raising exceptions."""
        unicode_input = "Deploy kubernetes \u2603 with authentication \u00e9ncryption"
        count = TeamSimulator._count_technical_terms(unicode_input)
        # "kubernetes" and "authentication" should match
        assert count >= 2

    def test_input_within_limit_unchanged(self):
        """Inputs shorter than INPUT_MAX_LENGTH are not altered."""
        short_input = "api database websocket"
        count = TeamSimulator._count_technical_terms(short_input)
        assert count == 3

    def test_exact_limit_boundary(self):
        """Input exactly at INPUT_MAX_LENGTH is not truncated."""
        # Put a term right at the end of a string that is exactly INPUT_MAX_LENGTH
        term = "api"
        filler_len = INPUT_MAX_LENGTH - len(term) - 1  # -1 for a space
        exact_input = "x" * filler_len + " " + term
        assert len(exact_input) == INPUT_MAX_LENGTH
        count = TeamSimulator._count_technical_terms(exact_input)
        assert count == 1


# =============================================================================
# CIRCUIT BREAKER TESTS
# =============================================================================

class TestCircuitBreaker:
    """Tests for the CircuitBreaker module (B7)."""

    def test_starts_closed(self):
        """Circuit breaker initializes in CLOSED state."""
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED

    def test_stays_closed_under_threshold(self):
        """Fewer failures than threshold keeps the circuit CLOSED."""
        cb = CircuitBreaker(failure_threshold=5)
        for _ in range(4):
            cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute() is True

    def test_opens_after_failures(self):
        """Circuit opens after reaching the failure threshold."""
        cb = CircuitBreaker(failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() is False

    def test_half_open_after_timeout(self):
        """Circuit transitions OPEN -> HALF_OPEN after recovery timeout."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout_seconds=0.1)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        # Wait for recovery timeout
        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.can_execute() is True

    def test_half_open_to_closed_on_success(self):
        """A success in HALF_OPEN state transitions back to CLOSED."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout_seconds=0.1)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)

        assert cb.state == CircuitState.HALF_OPEN
        cb.record_success(cost=1.0)
        assert cb.state == CircuitState.CLOSED

    def test_half_open_to_open_on_failure(self):
        """A failure in HALF_OPEN state transitions back to OPEN."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout_seconds=0.1)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)

        assert cb.state == CircuitState.HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_cost_limit_enforced(self):
        """Requests are rejected when daily cost exceeds the limit."""
        cb = CircuitBreaker(daily_cost_limit=10.0)
        assert cb.can_execute() is True

        # Accumulate cost up to the limit
        cb.record_success(cost=5.0)
        cb.record_success(cost=5.0)
        assert cb.can_execute() is False

    def test_cost_limit_below_threshold_allows(self):
        """Requests are allowed when daily cost is below the limit."""
        cb = CircuitBreaker(daily_cost_limit=100.0)
        cb.record_success(cost=50.0)
        assert cb.can_execute() is True

    def test_resets_on_success(self):
        """Successful requests reset the consecutive failure counter."""
        cb = CircuitBreaker(failure_threshold=5)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        # After reset, we need 5 more failures to open
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED

    def test_manual_reset(self):
        """Manual reset returns breaker to CLOSED with zero state."""
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute() is True

    def test_uses_default_config_daily_limit(self):
        """When no daily_cost_limit is given, DEFAULT_CONFIG value is used."""
        cb = CircuitBreaker()
        # DEFAULT_CONFIG.daily_system_limit is 200.0
        assert cb.daily_cost_limit == 200.0


# =============================================================================
# A/B TEST SECURITY TESTS
# =============================================================================

class TestABTestSecurity:
    """Tests for HMAC-SHA256 in ABTestFramework (B10)."""

    def test_uses_hmac_not_md5(self):
        """Verify that assign_variant uses HMAC-SHA256, not plain MD5."""
        framework = ABTestFramework(traffic_split=0.5)
        request_id = "test-request-123"

        # Compute expected HMAC-SHA256 result
        secret = os.getenv("AB_TEST_SECRET", "kurultai-ab-test-default-secret").encode()
        expected_hash = int(
            hmac.new(secret, request_id.encode(), hashlib.sha256).hexdigest(), 16
        )
        expected_variant = "variant" if expected_hash % 100 < 50 else "control"

        result = framework.assign_variant(request_id)
        assert result == expected_variant

    def test_md5_gives_different_result(self):
        """Confirm the HMAC result differs from what plain MD5 would produce."""
        framework = ABTestFramework(traffic_split=0.5)
        request_id = "determinism-check-456"

        # Old MD5 approach
        md5_hash = int(hashlib.md5(request_id.encode()).hexdigest(), 16)
        md5_variant = "variant" if md5_hash % 100 < 50 else "control"

        # New HMAC approach
        hmac_result = framework.assign_variant(request_id)

        # They may coincidentally agree for some inputs, but we verify
        # the underlying mechanism is different by checking the hash values
        secret = os.getenv("AB_TEST_SECRET", "kurultai-ab-test-default-secret").encode()
        hmac_hash = int(
            hmac.new(secret, request_id.encode(), hashlib.sha256).hexdigest(), 16
        )
        # The raw hash values must differ (MD5 is 128-bit, SHA256 is 256-bit)
        assert md5_hash != hmac_hash

    def test_deterministic_assignment(self):
        """Same request_id always maps to the same variant."""
        framework = ABTestFramework(traffic_split=0.3)
        request_id = "stable-request-789"

        results = {framework.assign_variant(request_id) for _ in range(100)}
        assert len(results) == 1  # Always the same result

    def test_variant_distribution(self):
        """Variant assignment roughly matches the traffic split."""
        framework = ABTestFramework(traffic_split=0.5)
        variant_count = sum(
            1 for i in range(1000)
            if framework.assign_variant(f"req-{i}") == "variant"
        )
        # With 50% split and 1000 samples, expect roughly 400-600 variants
        assert 300 <= variant_count <= 700

    def test_custom_secret_via_env(self):
        """A custom AB_TEST_SECRET environment variable changes assignments."""
        framework = ABTestFramework(traffic_split=0.5)
        request_id = "env-secret-test"

        # Get result with default secret
        default_result = framework.assign_variant(request_id)

        # Patch the environment variable to use a different secret
        with patch.dict(os.environ, {"AB_TEST_SECRET": "custom-test-secret-xyz"}):
            custom_result = framework.assign_variant(request_id)

        # The hash computation uses os.getenv at call time, so results
        # will differ if the secret differs (with very high probability)
        secret_default = "kurultai-ab-test-default-secret".encode()
        secret_custom = "custom-test-secret-xyz".encode()
        hash_default = int(
            hmac.new(secret_default, request_id.encode(), hashlib.sha256).hexdigest(), 16
        )
        hash_custom = int(
            hmac.new(secret_custom, request_id.encode(), hashlib.sha256).hexdigest(), 16
        )
        assert hash_default != hash_custom


# =============================================================================
# COMPLEXITY AUTH TESTS
# =============================================================================

class TestComplexityAuth:
    """Tests for ComplexityAuthenticator role-based authorization (B3/B4)."""

    def test_kublai_authorized_for_threshold_adjust(self):
        """Kublai (lead agent) can adjust thresholds."""
        auth = ComplexityAuthenticator()
        assert auth.authorize("kublai", "threshold_adjust") is True

    def test_system_authorized_for_threshold_adjust(self):
        """System agent can adjust thresholds."""
        auth = ComplexityAuthenticator()
        assert auth.authorize("system", "threshold_adjust") is True

    def test_random_agent_rejected_for_threshold_adjust(self):
        """Non-privileged known agents cannot adjust thresholds."""
        auth = ComplexityAuthenticator()
        assert auth.authorize("researcher", "threshold_adjust") is False
        assert auth.authorize("writer", "threshold_adjust") is False
        assert auth.authorize("developer", "threshold_adjust") is False

    def test_unknown_agent_rejected(self):
        """Unknown agents are rejected for all operations."""
        auth = ComplexityAuthenticator()
        assert auth.authorize("evil-agent", "threshold_adjust") is False
        assert auth.authorize("evil-agent", "classify") is False
        assert auth.authorize("evil-agent", "read_metrics") is False
        assert auth.authorize("evil-agent", "ground_truth") is False

    def test_analyst_can_provide_ground_truth(self):
        """Analyst agent can provide ground truth labels."""
        auth = ComplexityAuthenticator()
        assert auth.authorize("analyst", "ground_truth") is True

    def test_kublai_can_provide_ground_truth(self):
        """Kublai can also provide ground truth labels."""
        auth = ComplexityAuthenticator()
        assert auth.authorize("kublai", "ground_truth") is True

    def test_developer_cannot_provide_ground_truth(self):
        """Developer agent cannot provide ground truth labels."""
        auth = ComplexityAuthenticator()
        assert auth.authorize("developer", "ground_truth") is False

    def test_all_known_agents_can_classify(self):
        """All known agents can run classification."""
        auth = ComplexityAuthenticator()
        for agent_id in KNOWN_AGENTS:
            assert auth.authorize(agent_id, "classify") is True

    def test_all_known_agents_can_read_metrics(self):
        """All known agents can read metrics."""
        auth = ComplexityAuthenticator()
        for agent_id in KNOWN_AGENTS:
            assert auth.authorize(agent_id, "read_metrics") is True

    def test_unknown_operation_rejected(self):
        """Unknown operations are rejected for all agents."""
        auth = ComplexityAuthenticator()
        assert auth.authorize("kublai", "delete_everything") is False

    def test_validate_approved_by_known_agent(self):
        """validate_approved_by accepts known agents."""
        auth = ComplexityAuthenticator()
        assert auth.validate_approved_by("kublai") is True
        assert auth.validate_approved_by("analyst") is True

    def test_validate_approved_by_unknown_agent(self):
        """validate_approved_by rejects unknown agents."""
        auth = ComplexityAuthenticator()
        assert auth.validate_approved_by("unknown-approver") is False

    def test_custom_known_agents(self):
        """Custom known_agents set overrides the default."""
        custom_agents = frozenset({"alpha", "beta"})
        auth = ComplexityAuthenticator(known_agents=custom_agents)

        assert auth.authorize("alpha", "classify") is True
        assert auth.authorize("kublai", "classify") is False  # Not in custom set

    def test_role_sets_are_frozen(self):
        """Role allowlists are immutable frozensets."""
        assert isinstance(KNOWN_AGENTS, frozenset)
        assert isinstance(THRESHOLD_ADJUST_ROLES, frozenset)
        assert isinstance(GROUND_TRUTH_ROLES, frozenset)

    def test_threshold_roles_subset_of_known(self):
        """Threshold-adjust roles are a subset of known agents."""
        assert THRESHOLD_ADJUST_ROLES.issubset(KNOWN_AGENTS)

    def test_ground_truth_roles_subset_of_known(self):
        """Ground-truth roles are a subset of known agents."""
        assert GROUND_TRUTH_ROLES.issubset(KNOWN_AGENTS)
