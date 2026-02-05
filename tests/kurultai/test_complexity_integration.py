"""
Integration Tests for Phase 3: Complexity Scoring in Execution Pipeline

Tests complexity-based team spawning in TopologicalExecutor,
complexity scoring in DelegationProtocol, and Neo4j result storage
in StagingValidationPipeline.

Run with: pytest tests/kurultai/test_complexity_integration.py -v
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, MagicMock, patch, call

from tools.kurultai.topological_executor import TopologicalExecutor
from tools.kurultai.complexity_config import (
    ComplexityConfig,
    DEFAULT_CONFIG,
    complexity_to_team_size,
)
from tools.kurultai.complexity_validation_framework import StagingValidationPipeline
from src.protocols.delegation import DelegationProtocol, OperationalMemory


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_classifier_low():
    """Classifier that returns low complexity (< individual_threshold) -> individual."""
    classifier = Mock()
    classifier.classify.return_value = {
        "complexity": 0.10,
        "team_size": "individual",
    }
    return classifier


@pytest.fixture
def mock_classifier_medium():
    """Classifier that returns medium complexity (0.21-0.64) -> small_team."""
    classifier = Mock()
    classifier.classify.return_value = {
        "complexity": 0.45,
        "team_size": "small_team",
    }
    return classifier


@pytest.fixture
def mock_classifier_high():
    """Classifier that returns high complexity (>= 0.8) -> full_team."""
    classifier = Mock()
    classifier.classify.return_value = {
        "complexity": 0.9,
        "team_size": "full_team",
    }
    return classifier


@pytest.fixture
def sample_task():
    """Sample task dict matching Task TypedDict structure."""
    return {
        "id": "task-001",
        "type": "research",
        "description": "Analyze market trends for Q1",
        "status": "ready",
        "assigned_to": None,
        "claimed_by": None,
        "delegated_by": None,
        "priority": "normal",
        "deliverable_type": "analysis",
        "sender_hash": "user123",
        "created_at": "2026-02-05T00:00:00Z",
        "updated_at": None,
        "embedding": None,
        "window_expires_at": None,
        "user_priority_override": False,
        "priority_weight": 0.5,
        "claimed_at": None,
        "completed_at": None,
        "results": None,
        "error_message": None,
    }


@pytest.fixture
def complex_task():
    """A task description that should score highly complex."""
    return {
        "id": "task-002",
        "type": "code",
        "description": (
            "Build a distributed real-time data pipeline with Kafka, "
            "Flink, and Neo4j integration including GDPR compliance, "
            "multi-tenant isolation, and automated failover across "
            "3 availability zones with SOC2 audit logging"
        ),
        "status": "ready",
        "assigned_to": None,
        "claimed_by": None,
        "delegated_by": None,
        "priority": "high",
        "deliverable_type": "code",
        "sender_hash": "user456",
        "created_at": "2026-02-05T00:00:00Z",
        "updated_at": None,
        "embedding": None,
        "window_expires_at": None,
        "user_priority_override": False,
        "priority_weight": 0.8,
        "claimed_at": None,
        "completed_at": None,
        "results": None,
        "error_message": None,
    }


@pytest.fixture
def mock_memory():
    """Mock OperationalMemory for DelegationProtocol tests."""
    memory = Mock(spec=OperationalMemory)
    memory.execute_query.return_value = [{"task_id": "test-task-id"}]
    return memory


@pytest.fixture
def delegation_protocol(mock_memory):
    """DelegationProtocol without classifier."""
    return DelegationProtocol(
        memory=mock_memory,
        gateway_url="https://kublai.kurult.ai",
        gateway_token="test-token-xyz",
    )


@pytest.fixture
def delegation_protocol_with_classifier(mock_memory, mock_classifier_medium):
    """DelegationProtocol with classifier."""
    return DelegationProtocol(
        memory=mock_memory,
        gateway_url="https://kublai.kurult.ai",
        gateway_token="test-token-xyz",
        classifier=mock_classifier_medium,
    )


# =============================================================================
# TestTopologicalExecutorComplexity
# =============================================================================

class TestTopologicalExecutorComplexity:
    """Tests for complexity-based team configuration in TopologicalExecutor."""

    def test_simple_task_individual_dispatch(self, mock_classifier_low, sample_task):
        """Classifier returns score < 0.6 -> individual mode with 1 agent."""
        executor = TopologicalExecutor(
            neo4j_client=None,
            classifier=mock_classifier_low,
        )

        config = executor._determine_team_configuration(sample_task)

        assert config["mode"] == "individual"
        assert config["agents"] == 1
        mock_classifier_low.classify.assert_called_once_with(
            sample_task["description"]
        )

    def test_moderate_task_small_team(self, mock_classifier_medium, sample_task):
        """Classifier returns 0.6-0.8 -> small_team mode with 3 agents."""
        executor = TopologicalExecutor(
            neo4j_client=None,
            classifier=mock_classifier_medium,
        )

        config = executor._determine_team_configuration(sample_task)

        assert config["mode"] == "small_team"
        assert config["agents"] == 3
        mock_classifier_medium.classify.assert_called_once_with(
            sample_task["description"]
        )

    def test_complex_task_full_team(self, mock_classifier_high, complex_task):
        """Classifier returns > 0.8 -> full_team mode with 5 agents."""
        executor = TopologicalExecutor(
            neo4j_client=None,
            classifier=mock_classifier_high,
        )

        config = executor._determine_team_configuration(complex_task)

        assert config["mode"] == "full_team"
        assert config["agents"] == 5
        mock_classifier_high.classify.assert_called_once_with(
            complex_task["description"]
        )

    def test_fallback_without_classifier(self, sample_task):
        """No classifier configured -> individual mode (existing behavior)."""
        executor = TopologicalExecutor(neo4j_client=None)

        config = executor._determine_team_configuration(sample_task)

        assert config["mode"] == "individual"
        assert config["agents"] == 1

    def test_classifier_exception_falls_back_to_individual(self, sample_task):
        """Classifier raising an exception -> individual mode fallback."""
        bad_classifier = Mock()
        bad_classifier.classify.side_effect = RuntimeError("model unavailable")

        executor = TopologicalExecutor(
            neo4j_client=None,
            classifier=bad_classifier,
        )

        config = executor._determine_team_configuration(sample_task)

        assert config["mode"] == "individual"
        assert config["agents"] == 1

    def test_custom_config_agent_counts(self, mock_classifier_high, complex_task):
        """Custom ComplexityConfig overrides default agent counts."""
        custom_config = ComplexityConfig(
            individual_agents=2,
            small_team_agents=4,
            full_team_agents=7,
        )

        executor = TopologicalExecutor(
            neo4j_client=None,
            classifier=mock_classifier_high,
            config=custom_config,
        )

        config = executor._determine_team_configuration(complex_task)

        assert config["mode"] == "full_team"
        assert config["agents"] == 7

    @pytest.mark.asyncio
    async def test_execute_ready_set_stores_team_config(
        self, mock_classifier_medium, sample_task
    ):
        """execute_ready_set stores _team_config in task metadata."""
        executor = TopologicalExecutor(
            neo4j_client=None,
            classifier=mock_classifier_medium,
        )

        # Mock get_ready_tasks to return our sample task
        executor.get_ready_tasks = AsyncMock(return_value=[sample_task])

        summary = await executor.execute_ready_set("user123")

        # Task should now have _team_config metadata
        assert "_team_config" in sample_task
        assert sample_task["_team_config"]["mode"] == "small_team"
        assert sample_task["_team_config"]["agents"] == 3

    def test_boundary_score_at_individual_threshold(self, sample_task):
        """Score exactly at individual_threshold (0.21) -> small_team."""
        classifier = Mock()
        classifier.classify.return_value = {"complexity": DEFAULT_CONFIG.individual_threshold, "team_size": "small_team"}

        executor = TopologicalExecutor(
            neo4j_client=None,
            classifier=classifier,
        )

        config = executor._determine_team_configuration(sample_task)
        assert config["mode"] == "small_team"
        assert config["agents"] == 3

    def test_boundary_score_at_small_team_threshold(self, sample_task):
        """Score exactly at small_team_threshold (0.64) -> full_team."""
        classifier = Mock()
        classifier.classify.return_value = {"complexity": DEFAULT_CONFIG.small_team_threshold, "team_size": "full_team"}

        executor = TopologicalExecutor(
            neo4j_client=None,
            classifier=classifier,
        )

        config = executor._determine_team_configuration(sample_task)
        assert config["mode"] == "full_team"
        assert config["agents"] == 5


# =============================================================================
# TestDelegationProtocolComplexity
# =============================================================================

class TestDelegationProtocolComplexity:
    """Tests for complexity scoring integration in DelegationProtocol."""

    def test_complexity_stored_in_task(
        self, mock_memory, mock_classifier_medium
    ):
        """Verify complexity_score and team_size are passed in CREATE query params."""
        protocol = DelegationProtocol(
            memory=mock_memory,
            gateway_url="https://kublai.kurult.ai",
            gateway_token="test-token",
            classifier=mock_classifier_medium,
        )

        protocol.create_delegation_task(
            from_user="user123",
            description="Analyze performance metrics for dashboard",
            task_type="analysis",
            priority="normal",
        )

        # Verify execute_query was called
        assert mock_memory.execute_query.called

        # Get the parameters passed to execute_query
        call_args = mock_memory.execute_query.call_args
        query = call_args[0][0]
        parameters = call_args[0][1]

        # Verify complexity fields are in the query
        assert "complexity_score" in query
        assert "team_size" in query

        # Verify parameter values
        assert parameters["complexity_score"] == 0.45
        assert parameters["team_size"] == "small_team"

    def test_pii_sanitized_before_classification(
        self, mock_memory, mock_classifier_medium
    ):
        """Verify sanitize_for_privacy runs before classify_task_complexity."""
        protocol = DelegationProtocol(
            memory=mock_memory,
            gateway_url="https://kublai.kurult.ai",
            gateway_token="test-token",
            classifier=mock_classifier_medium,
        )

        # Use a description with PII
        description_with_pii = (
            "Contact john@example.com to analyze performance"
        )

        protocol.create_delegation_task(
            from_user="user123",
            description=description_with_pii,
        )

        # The classifier should have been called with sanitized text
        classify_call_args = mock_classifier_medium.classify.call_args[0][0]
        # The email should have been sanitized before reaching the classifier
        assert "john@example.com" not in classify_call_args
        assert "[EMAIL]" in classify_call_args

    def test_no_classifier_still_works(self, mock_memory):
        """Delegation works without classifier, complexity fields are null."""
        protocol = DelegationProtocol(
            memory=mock_memory,
            gateway_url="https://kublai.kurult.ai",
            gateway_token="test-token",
            # No classifier
        )

        task_id = protocol.create_delegation_task(
            from_user="user123",
            description="Write a blog post about Python",
        )

        # Should still create the task
        assert task_id is not None

        # Parameters should have null complexity fields
        call_args = mock_memory.execute_query.call_args
        parameters = call_args[0][1]

        assert parameters["complexity_score"] is None
        assert parameters["team_size"] is None

    def test_classify_task_complexity_returns_none_without_classifier(self):
        """classify_task_complexity returns None when no classifier."""
        memory = Mock(spec=OperationalMemory)
        protocol = DelegationProtocol(
            memory=memory,
            gateway_url="https://kublai.kurult.ai",
            gateway_token="test-token",
        )

        result = protocol.classify_task_complexity("some description")
        assert result is None

    def test_classify_task_complexity_with_classifier(
        self, mock_memory, mock_classifier_high
    ):
        """classify_task_complexity returns dict with score and team_size."""
        protocol = DelegationProtocol(
            memory=mock_memory,
            gateway_url="https://kublai.kurult.ai",
            gateway_token="test-token",
            classifier=mock_classifier_high,
        )

        result = protocol.classify_task_complexity("complex distributed system")

        assert result is not None
        assert result["complexity_score"] == 0.9
        assert result["team_size"] == "full_team"

    def test_classify_task_complexity_handles_exception(self, mock_memory):
        """classify_task_complexity returns None on classifier exception."""
        bad_classifier = Mock()
        bad_classifier.classify.side_effect = ValueError("bad input")

        protocol = DelegationProtocol(
            memory=mock_memory,
            gateway_url="https://kublai.kurult.ai",
            gateway_token="test-token",
            classifier=bad_classifier,
        )

        result = protocol.classify_task_complexity("some description")
        assert result is None


# =============================================================================
# TestStoreResults
# =============================================================================

class TestStoreResults:
    """Tests for _store_results in StagingValidationPipeline."""

    @pytest.fixture(autouse=True)
    def _patch_test_case_library(self):
        """Patch TestCaseLibrary.get_all_test_cases to avoid missing method errors.

        The framework references _get_medium_complexity_cases which may not
        yet be implemented by other agents. We bypass this by returning an
        empty test case list during StagingValidationPipeline init.
        """
        with patch(
            "tools.kurultai.complexity_validation_framework.TestCaseLibrary.get_all_test_cases",
            return_value=[],
        ):
            yield

    def _make_mock_neo4j_driver(self, mock_session=None):
        """Create a properly configured mock Neo4j async driver.

        The driver's session() method returns an async context manager
        that yields the mock_session.
        """
        if mock_session is None:
            mock_session = AsyncMock()

        # Create an async context manager that yields the session
        ctx_manager = AsyncMock()
        ctx_manager.__aenter__.return_value = mock_session
        ctx_manager.__aexit__.return_value = False

        # driver.session() must return the context manager (not a coroutine)
        mock_driver = Mock()
        mock_driver.session.return_value = ctx_manager

        return mock_driver, mock_session

    @pytest.mark.asyncio
    async def test_creates_validation_run_node(self):
        """Verify _store_results creates a ValidationRun node in Neo4j."""
        mock_driver, mock_session = self._make_mock_neo4j_driver()

        mock_classifier = Mock()
        pipeline = StagingValidationPipeline(
            classifier=mock_classifier,
            neo4j_client=mock_driver,
        )

        result = {
            "timestamp": "2026-02-05T12:00:00Z",
            "metrics": {
                "accuracy": 0.92,
                "precision": 0.95,
                "recall": 0.97,
                "f1_score": 0.96,
                "mean_absolute_error": 0.05,
                "total_cases": 100,
            },
            "recommendation": {
                "decision": "GO",
            },
            "calibration": {
                "lower_threshold": 0.58,
                "upper_threshold": 0.82,
            },
        }

        await pipeline._store_results(result)

        # Verify session.run was called with the correct query
        mock_session.run.assert_called_once()
        call_args = mock_session.run.call_args

        query = call_args[0][0]
        params = call_args[0][1]

        # Verify the query creates a ValidationRun node
        assert "CREATE (v:ValidationRun" in query
        assert "randomUUID()" in query

        # Verify parameters are correctly extracted
        assert params["timestamp"] == "2026-02-05T12:00:00Z"
        assert params["accuracy"] == 0.92
        assert params["precision"] == 0.95
        assert params["recall"] == 0.97
        assert params["f1"] == 0.96
        assert params["mae"] == 0.05
        assert params["total_cases"] == 100
        assert params["decision"] == "GO"
        assert params["lower_threshold"] == 0.58
        assert params["upper_threshold"] == 0.82

    @pytest.mark.asyncio
    async def test_graceful_without_neo4j(self):
        """No Neo4j client configured -> no error, just logs info."""
        mock_classifier = Mock()
        pipeline = StagingValidationPipeline(
            classifier=mock_classifier,
            neo4j_client=None,
        )

        result = {
            "timestamp": "2026-02-05T12:00:00Z",
            "metrics": {},
            "recommendation": {},
            "calibration": {},
        }

        # Should not raise
        await pipeline._store_results(result)

    @pytest.mark.asyncio
    async def test_handles_neo4j_exception(self):
        """Neo4j exception is caught and logged, not raised."""
        mock_session = AsyncMock()
        mock_session.run.side_effect = Exception("connection refused")
        mock_driver, _ = self._make_mock_neo4j_driver(mock_session)

        mock_classifier = Mock()
        pipeline = StagingValidationPipeline(
            classifier=mock_classifier,
            neo4j_client=mock_driver,
        )

        result = {
            "timestamp": "2026-02-05T12:00:00Z",
            "metrics": {"accuracy": 0.5},
            "recommendation": {"decision": "NO_GO"},
            "calibration": {},
        }

        # Should not raise despite Neo4j failure
        await pipeline._store_results(result)

    @pytest.mark.asyncio
    async def test_default_values_for_missing_keys(self):
        """Missing keys in result dict default to safe values."""
        mock_driver, mock_session = self._make_mock_neo4j_driver()

        mock_classifier = Mock()
        pipeline = StagingValidationPipeline(
            classifier=mock_classifier,
            neo4j_client=mock_driver,
        )

        # Minimal result with no nested data
        result = {}

        await pipeline._store_results(result)

        call_args = mock_session.run.call_args
        params = call_args[0][1]

        # Verify defaults are used
        assert params["timestamp"] == ""
        assert params["accuracy"] == 0.0
        assert params["precision"] == 0.0
        assert params["recall"] == 0.0
        assert params["f1"] == 0.0
        assert params["mae"] == 0.0
        assert params["total_cases"] == 0
        assert params["decision"] == "UNKNOWN"
        assert params["lower_threshold"] == DEFAULT_CONFIG.individual_threshold
        assert params["upper_threshold"] == DEFAULT_CONFIG.small_team_threshold
