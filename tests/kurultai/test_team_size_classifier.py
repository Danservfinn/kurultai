"""
Tests for the TeamSizeClassifier.

Validates the deterministic keyword-based classifier that maps capability
request text to complexity scores and team size labels.

Run with: pytest tests/kurultai/test_team_size_classifier.py -v
"""

import pytest

from tools.kurultai.team_size_classifier import TeamSizeClassifier
from tools.kurultai.complexity_config import INPUT_MAX_LENGTH


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def classifier():
    """Fresh classifier instance for each test."""
    return TeamSizeClassifier()


# =============================================================================
# CORE CLASSIFICATION TESTS
# =============================================================================

class TestTeamSizeClassifier:
    """Tests for the TeamSizeClassifier core classify method."""

    def test_simple_request_returns_individual(self, classifier):
        """Simple requests like 'Send a Slack message' should return low complexity."""
        result = classifier.classify("Send a Slack message")
        assert result["complexity"] < 0.6, (
            f"Expected complexity < 0.6 for simple request, got {result['complexity']}"
        )
        assert result["team_size"] == "individual"

    def test_complex_request_returns_full_team(self, classifier):
        """Highly complex requests should return high complexity and full_team."""
        request = (
            "Distributed database with sharding and replication "
            "across multiple regions with encryption and authentication"
        )
        result = classifier.classify(request)
        assert result["complexity"] > 0.8, (
            f"Expected complexity > 0.8 for complex request, got {result['complexity']}"
        )
        assert result["team_size"] == "full_team"

    def test_moderate_request_returns_small_team(self, classifier):
        """Moderate requests should return small_team."""
        request = "Build a webhook handler with retry logic and event routing"
        result = classifier.classify(request)
        assert result["team_size"] == "small_team", (
            f"Expected small_team, got {result['team_size']} (complexity={result['complexity']})"
        )

    def test_input_length_limit(self, classifier):
        """Very long inputs (100KB) should be truncated without OOM."""
        long_input = "distributed database api " * 5000  # ~125KB
        assert len(long_input) > INPUT_MAX_LENGTH

        result = classifier.classify(long_input)

        # Should still return valid result
        assert 0.0 <= result["complexity"] <= 1.0
        assert result["team_size"] in ("individual", "small_team", "full_team")
        assert result["confidence"] > 0.0
        # Confidence should be penalized for truncation
        assert result["confidence"] < 0.95

    def test_deterministic_results(self, classifier):
        """Same input must always produce the exact same output."""
        request = "Build a microservice with Kubernetes deployment and monitoring"
        result1 = classifier.classify(request)
        result2 = classifier.classify(request)

        assert result1["complexity"] == result2["complexity"]
        assert result1["team_size"] == result2["team_size"]
        assert result1["confidence"] == result2["confidence"]
        assert result1["factors"] == result2["factors"]

    def test_empty_input(self, classifier):
        """Empty string should return low complexity."""
        result = classifier.classify("")
        assert result["complexity"] < 0.2, (
            f"Expected very low complexity for empty input, got {result['complexity']}"
        )
        assert result["team_size"] == "individual"

    def test_classify_returns_expected_keys(self, classifier):
        """Verify the result dict has all required keys."""
        result = classifier.classify("Any capability request")
        assert "complexity" in result
        assert "team_size" in result
        assert "confidence" in result
        assert "factors" in result
        assert isinstance(result["complexity"], float)
        assert isinstance(result["team_size"], str)
        assert isinstance(result["confidence"], float)
        assert isinstance(result["factors"], dict)


# =============================================================================
# FACTOR EXTRACTION TESTS
# =============================================================================

class TestFactorExtraction:
    """Tests for individual factor extraction."""

    def test_technical_terms_increase_complexity(self, classifier):
        """Requests with many technical keywords should score higher."""
        simple = classifier.classify("Read a file")
        technical = classifier.classify(
            "Deploy Kubernetes microservice with Redis cache and Kafka queue"
        )
        assert technical["complexity"] > simple["complexity"]
        assert technical["factors"]["technical_terms_factor"] > simple["factors"]["technical_terms_factor"]

    def test_security_keywords_increase_complexity(self, classifier):
        """Security-related keywords should boost complexity."""
        simple = classifier.classify("Read data from file")
        secure = classifier.classify(
            "Implement OAuth SSO with MFA, RBAC permission and JWT token management"
        )
        assert secure["factors"]["security_factor"] > simple["factors"]["security_factor"]

    def test_integration_keywords_increase_complexity(self, classifier):
        """Integration keywords should boost the integration factor."""
        simple = classifier.classify("Print a message")
        integrated = classifier.classify(
            "Integrate webhook with event stream and connect adapter middleware"
        )
        assert integrated["factors"]["integration_factor"] > simple["factors"]["integration_factor"]

    def test_concurrency_keywords_increase_complexity(self, classifier):
        """Concurrency keywords should boost the concurrency factor."""
        simple = classifier.classify("Write to log file")
        concurrent = classifier.classify(
            "Build concurrent distributed multi-region real-time streaming cluster"
        )
        assert concurrent["factors"]["concurrency_factor"] > simple["factors"]["concurrency_factor"]

    def test_data_scale_keywords_increase_complexity(self, classifier):
        """Data scale keywords should boost the data scale factor."""
        simple = classifier.classify("Parse a JSON file")
        large_scale = classifier.classify(
            "Process petabyte data lake with high-throughput batch ingestion"
        )
        assert large_scale["factors"]["data_scale_factor"] > simple["factors"]["data_scale_factor"]

    def test_length_factor_increases_with_longer_input(self, classifier):
        """Longer inputs should have higher length factor."""
        short = classifier.classify("Hello")
        long_text = classifier.classify(
            "Build a comprehensive end-to-end system that handles multiple "
            "components including data processing, API gateway configuration, "
            "authentication flows, monitoring setup, and deployment automation "
            "with rollback capabilities and comprehensive logging throughout"
        )
        assert long_text["factors"]["length_factor"] > short["factors"]["length_factor"]


# =============================================================================
# CONFIDENCE TESTS
# =============================================================================

class TestConfidence:
    """Tests for confidence scoring."""

    def test_very_short_input_low_confidence(self, classifier):
        """Very short inputs (< 3 tokens) should have lower confidence."""
        result = classifier.classify("hello")
        assert result["confidence"] < 0.75

    def test_rich_input_high_confidence(self, classifier):
        """Rich inputs with multiple factors should have high confidence."""
        result = classifier.classify(
            "Build distributed microservice with Kubernetes orchestration, "
            "Redis cache, Kafka queue, OAuth authentication, and real-time "
            "streaming data pipeline"
        )
        assert result["confidence"] >= 0.85

    def test_truncated_input_penalized_confidence(self, classifier):
        """Truncated inputs should have reduced confidence."""
        within_limit = classifier.classify("Build API with authentication")
        over_limit = classifier.classify("a " * (INPUT_MAX_LENGTH + 1000))
        assert over_limit["confidence"] < within_limit["confidence"]


# =============================================================================
# EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Edge case tests for robustness."""

    def test_none_input(self, classifier):
        """None input should be handled gracefully."""
        result = classifier.classify(None)
        assert result["complexity"] < 0.2
        assert result["team_size"] == "individual"

    def test_numeric_input(self, classifier):
        """Numeric input should be converted to string."""
        result = classifier.classify(12345)
        assert 0.0 <= result["complexity"] <= 1.0

    def test_unicode_input(self, classifier):
        """Unicode input should not crash the classifier."""
        result = classifier.classify("Build API with authentication for users")
        assert 0.0 <= result["complexity"] <= 1.0

    def test_all_caps_input(self, classifier):
        """All-caps input should be case-insensitive."""
        lower = classifier.classify("build kubernetes microservice with cache")
        upper = classifier.classify("BUILD KUBERNETES MICROSERVICE WITH CACHE")
        assert lower["complexity"] == upper["complexity"]

    def test_custom_weights(self):
        """Classifier should accept custom weights."""
        weights = {
            "length_factor": 0.0,
            "technical_terms_factor": 1.0,
            "integration_factor": 0.0,
            "security_factor": 0.0,
            "domain_complexity_factor": 0.0,
            "concurrency_factor": 0.0,
            "data_scale_factor": 0.0,
        }
        classifier = TeamSizeClassifier(weights=weights)
        result = classifier.classify("Deploy Kubernetes microservice")
        # Only technical terms should matter
        assert result["factors"]["technical_terms_factor"] > 0

    def test_complexity_bounds(self, classifier):
        """Complexity should always be between 0 and 1."""
        test_inputs = [
            "",
            "a",
            "simple task",
            "Build the most complex distributed multi-region Kubernetes "
            "federation with sharding replication encryption authentication "
            "authorization RBAC SSO MFA streaming real-time concurrent "
            "parallel high-volume petabyte large-scale data-lake warehouse",
        ]
        for text in test_inputs:
            result = classifier.classify(text)
            assert 0.0 <= result["complexity"] <= 1.0, (
                f"Complexity {result['complexity']} out of bounds for input: {text[:50]}"
            )
