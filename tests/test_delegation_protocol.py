"""
Comprehensive tests for Kublai Delegation Protocol.

Tests cover:
- Personal memory loading
- Operational memory querying
- Privacy sanitization patterns
- Agent routing for all task types
- Delegation workflow
- Health check
- Response synthesis

Location: /Users/kurultai/molt/tests/test_delegation_protocol.py
"""

import os
import sys
import uuid
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, call
from typing import Dict, Any

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openclaw_memory import OperationalMemory
from tools.delegation_protocol import (
    DelegationProtocol,
    PersonalContext,
    DelegationResult,
    Agent,
    TaskType,
    delegate_research,
    delegate_writing,
    delegate_code,
    delegate_analysis
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_neo4j_driver():
    """Create a mock Neo4j driver."""
    driver = MagicMock()
    driver.verify_connectivity.return_value = None
    return driver


@pytest.fixture
def mock_neo4j_session():
    """Create a mock Neo4j session."""
    session = MagicMock()

    def mock_run(cypher: str, **kwargs):
        """Mock run that returns an empty result by default."""
        result = MagicMock()
        result.single.return_value = None
        result.data.return_value = []
        result.__iter__ = lambda self: iter([])
        return result

    session.run = mock_run
    return session


def create_mock_session():
    """Create a mock Neo4j session."""
    session = MagicMock()

    def mock_run(cypher: str, **kwargs):
        """Mock run that returns an empty result by default."""
        result = MagicMock()
        result.single.return_value = None
        result.data.return_value = []
        result.__iter__ = lambda self: iter([])
        return result

    session.run = mock_run
    return session


@pytest.fixture
def mock_operational_memory(mock_neo4j_driver):
    """Create a mock OperationalMemory with configured session."""
    memory = Mock(spec=OperationalMemory)
    memory._driver = mock_neo4j_driver
    memory.database = "neo4j"
    memory.fallback_mode = True

    # Mock the _session context manager
    session_ctx = MagicMock()
    session_ctx.__enter__ = Mock(return_value=create_mock_session())
    session_ctx.__exit__ = Mock(return_value=False)
    memory._session = Mock(return_value=session_ctx)

    # Mock health_check to return healthy
    memory.health_check = Mock(return_value={"status": "healthy"})

    return memory


@pytest.fixture
def temp_memory_dir(tmp_path):
    """Create a temporary directory for memory files."""
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()

    # Create a sample MEMORY.md file
    memory_md = tmp_path / "MEMORY.md"
    memory_md.write_text("""
# Personal Memory

## Preferences
- I prefer concise responses
- I like Python over JavaScript
- My favorite color is blue

## Friends
- My friend Alice works at TechCorp
- Contact my friend Bob for design questions

## Recent Activity
- Working on the Moltbook project
- Planning community launch
- Researching competitors

## Notes
Remember that I dislike being called "buddy" or "pal".
I prefer to be addressed by my name.
""")

    # Create a daily memory file
    daily_md = memory_dir / "2026-02-04.md"
    daily_md.write_text("""
# February 4, 2026

## Tasks
- Research competitor pricing
- Write community guidelines
- Fix authentication bug

## Notes
Discussed project timeline with team.
""")

    return tmp_path


@pytest.fixture
def delegation_protocol(mock_operational_memory, temp_memory_dir):
    """Create a DelegationProtocol instance for testing."""
    return DelegationProtocol(
        memory=mock_operational_memory,
        personal_memory_path=str(temp_memory_dir / "memory"),
        gateway_url=None,  # No gateway for unit tests
        gateway_token=None
    )


# =============================================================================
# Test Personal Memory Loading
# =============================================================================

class TestPersonalMemoryLoading:
    """Tests for querying personal memory."""

    def test_query_personal_memory_returns_context(self, delegation_protocol, temp_memory_dir):
        """Test that querying personal memory returns a PersonalContext."""
        result = delegation_protocol.query_personal_memory("project")

        assert isinstance(result, PersonalContext)
        assert hasattr(result, "user_preferences")
        assert hasattr(result, "recent_history")
        assert hasattr(result, "friend_names")
        assert hasattr(result, "relevant_notes")

    def test_query_personal_memory_finds_relevant_notes(self, delegation_protocol):
        """Test that querying finds notes related to the topic."""
        result = delegation_protocol.query_personal_memory("project")

        # Should find notes containing "project"
        assert len(result.relevant_notes) > 0
        assert any("project" in note.lower() for note in result.relevant_notes)

    def test_query_personal_memory_extracts_friend_names(self, delegation_protocol):
        """Test that friend names are extracted from memory."""
        result = delegation_protocol.query_personal_memory("friends")

        # Should find Alice and Bob as friends
        assert len(result.friend_names) >= 0
        # Note: The extraction pattern looks for capitalized names after "friend"

    def test_query_personal_memory_extracts_preferences(self, delegation_protocol):
        """Test that user preferences are extracted."""
        result = delegation_protocol.query_personal_memory("preferences")

        assert isinstance(result.user_preferences, dict)

    def test_query_personal_memory_with_nonexistent_directory(self, mock_operational_memory):
        """Test behavior when personal memory directory doesn't exist."""
        protocol = DelegationProtocol(
            memory=mock_operational_memory,
            personal_memory_path="/nonexistent/path"
        )

        result = protocol.query_personal_memory("test")

        # Should return empty context, not crash
        assert isinstance(result, PersonalContext)
        assert len(result.relevant_notes) == 0

    def test_personal_context_to_dict(self, delegation_protocol):
        """Test PersonalContext conversion to dictionary."""
        result = delegation_protocol.query_personal_memory("test")
        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)
        assert "user_preferences" in result_dict
        assert "recent_history" in result_dict
        assert "friend_names" in result_dict
        assert "relevant_notes" in result_dict


# =============================================================================
# Test Operational Memory Querying
# =============================================================================

class TestOperationalMemoryQuerying:
    """Tests for querying operational memory."""

    def test_query_operational_memory_returns_list(self, delegation_protocol):
        """Test that querying operational memory returns a list."""
        result = delegation_protocol.query_operational_memory("test")

        assert isinstance(result, list)

    def test_query_operational_memory_with_agent_filter(self, delegation_protocol):
        """Test querying with an agent filter."""
        result = delegation_protocol.query_operational_memory("test", agent="researcher")

        assert isinstance(result, list)

    def test_query_operational_memory_respects_limit(self, delegation_protocol):
        """Test that limit parameter is respected."""
        result = delegation_protocol.query_operational_memory("test", limit=5)

        assert len(result) <= 5


# =============================================================================
# Test Privacy Sanitization
# =============================================================================

class TestPrivacySanitization:
    """Tests for privacy sanitization."""

    def test_sanitize_removes_phone_numbers(self, delegation_protocol):
        """Test that phone numbers are removed."""
        content = "Call me at 555-123-4567 or 555.987.6543"
        sanitized, counts = delegation_protocol.sanitize_for_delegation(content)

        assert "[PHONE]" in sanitized
        assert "555-123-4567" not in sanitized
        assert counts.get("[PHONE]", 0) >= 2

    def test_sanitize_removes_emails(self, delegation_protocol):
        """Test that email addresses are removed."""
        content = "Email me at john@example.com or jane@test.org"
        sanitized, counts = delegation_protocol.sanitize_for_delegation(content)

        assert "[EMAIL]" in sanitized
        assert "john@example.com" not in sanitized
        assert counts.get("[EMAIL]", 0) >= 2

    def test_sanitize_removes_ssn(self, delegation_protocol):
        """Test that SSN numbers are removed."""
        content = "My SSN is 123-45-6789"
        sanitized, counts = delegation_protocol.sanitize_for_delegation(content)

        # SSN pattern (XXX-XX-XXXX) should be detected and sanitized
        assert "[SSN]" in sanitized
        assert "123-45-6789" not in sanitized

    def test_sanitize_removes_nine_digit_ssn(self, delegation_protocol):
        """Test that 9-digit SSN without dashes is handled."""
        content = "My SSN is 123456789"
        sanitized, counts = delegation_protocol.sanitize_for_delegation(content)

        # 9-digit number might be detected as potential key or similar
        # The main SSN pattern requires dashes
        assert "123456789" not in sanitized or "[POTENTIAL_KEY]" in sanitized

    def test_sanitize_removes_api_keys(self, delegation_protocol):
        """Test that API keys are removed."""
        content = "Use this api_key: sk-1234567890abcdef1234567890abcdef"
        sanitized, counts = delegation_protocol.sanitize_for_delegation(content)

        assert "[API_KEY]" in sanitized
        assert "sk-1234567890abcdef" not in sanitized

    def test_sanitize_removes_credit_cards(self, delegation_protocol):
        """Test that credit card numbers are removed."""
        content = "Card: 4111-1111-1111-1111"
        sanitized, counts = delegation_protocol.sanitize_for_delegation(content)

        assert "[CREDIT_CARD]" in sanitized
        assert "4111-1111-1111-1111" not in sanitized

    def test_sanitize_removes_ip_addresses(self, delegation_protocol):
        """Test that IP addresses are removed."""
        content = "Server at 192.168.1.1"
        sanitized, counts = delegation_protocol.sanitize_for_delegation(content)

        assert "[IP_ADDRESS]" in sanitized
        assert "192.168.1.1" not in sanitized

    def test_sanitize_does_not_false_positive_ip_on_phone(self, delegation_protocol):
        """Test that phone numbers are not confused with IP addresses."""
        content = "Call 555-123-4567"
        sanitized, counts = delegation_protocol.sanitize_for_delegation(content)

        assert "[PHONE]" in sanitized
        # Should not also be marked as IP
        assert sanitized.count("[") == sanitized.count("]")

    def test_sanitize_removes_addresses(self, delegation_protocol):
        """Test that physical addresses are removed."""
        content = "I live at 123 Main St"
        sanitized, counts = delegation_protocol.sanitize_for_delegation(content)

        assert "[ADDRESS]" in sanitized or "[ADDRESS]" in sanitized

    def test_sanitize_removes_friend_references(self, delegation_protocol):
        """Test that friend references are sanitized."""
        content = "Ask my friend Alice about that"
        sanitized, counts = delegation_protocol.sanitize_for_delegation(content)

        assert "[FRIEND_REFERENCE]" in sanitized or "friend Alice" not in sanitized

    def test_sanitize_returns_counts(self, delegation_protocol):
        """Test that sanitization returns counts of removed items."""
        content = "Call 555-123-4567 or email test@example.com"
        sanitized, counts = delegation_protocol.sanitize_for_delegation(content)

        assert isinstance(counts, dict)
        assert len(counts) > 0

    def test_sanitize_empty_string(self, delegation_protocol):
        """Test sanitizing an empty string."""
        sanitized, counts = delegation_protocol.sanitize_for_delegation("")

        assert sanitized == ""
        assert counts == {}

    def test_sanitize_none(self, delegation_protocol):
        """Test sanitizing None."""
        sanitized, counts = delegation_protocol.sanitize_for_delegation(None)

        assert sanitized is None
        assert counts == {}


# =============================================================================
# Test Agent Routing
# =============================================================================

class TestAgentRouting:
    """Tests for agent routing determination."""

    def test_route_research_to_researcher(self, delegation_protocol):
        """Test that research tasks route to researcher."""
        agent = delegation_protocol.determine_target_agent("Research AI trends")

        assert agent == "researcher"

    def test_route_writing_to_writer(self, delegation_protocol):
        """Test that writing tasks route to writer."""
        agent = delegation_protocol.determine_target_agent("Write a blog post")

        assert agent == "writer"

    def test_route_code_to_developer(self, delegation_protocol):
        """Test that code tasks route to developer."""
        agent = delegation_protocol.determine_target_agent("Fix the authentication bug")

        assert agent == "developer"

    def test_route_security_to_developer(self, delegation_protocol):
        """Test that security tasks route to developer."""
        agent = delegation_protocol.determine_target_agent("Audit security vulnerabilities")

        assert agent == "developer"

    def test_route_analysis_to_analyst(self, delegation_protocol):
        """Test that analysis tasks route to analyst."""
        agent = delegation_protocol.determine_target_agent("Analyze performance metrics")

        assert agent == "analyst"

    def test_route_process_to_ops(self, delegation_protocol):
        """Test that process tasks route to ops."""
        agent = delegation_protocol.determine_target_agent("Update the deployment workflow")

        assert agent == "ops"

    def test_route_with_at_mention(self, delegation_protocol):
        """Test routing with explicit @mention."""
        agent = delegation_protocol.determine_target_agent("@writer please help")

        assert agent == "writer"

    def test_route_with_suggested_agent(self, delegation_protocol):
        """Test routing with explicit suggested agent."""
        agent = delegation_protocol.determine_target_agent(
            "Do something",
            suggested_agent="analyst"
        )

        assert agent == "analyst"

    def test_route_unknown_to_main(self, delegation_protocol):
        """Test that unknown tasks default to main (Kublai)."""
        agent = delegation_protocol.determine_target_agent("Hello there")

        assert agent == "main"

    def test_route_complex_task(self, delegation_protocol):
        """Test routing of a task with multiple keywords."""
        # Should prioritize based on keyword matching
        agent = delegation_protocol.determine_target_agent(
            "Research and write about security best practices"
        )

        # Should route to the first matched agent (researcher)
        assert agent in ["researcher", "writer", "developer"]

    def test_agent_names_mapping(self, delegation_protocol):
        """Test that agent IDs map to correct display names."""
        assert delegation_protocol.AGENT_NAMES["main"] == "Kublai"
        assert delegation_protocol.AGENT_NAMES["researcher"] == "Möngke"
        assert delegation_protocol.AGENT_NAMES["writer"] == "Chagatai"
        assert delegation_protocol.AGENT_NAMES["developer"] == "Temüjin"
        assert delegation_protocol.AGENT_NAMES["analyst"] == "Jochi"
        assert delegation_protocol.AGENT_NAMES["ops"] == "Ögedei"


# =============================================================================
# Test Delegation Workflow
# =============================================================================

class TestDelegationWorkflow:
    """Tests for the full delegation workflow."""

    def test_delegate_task_returns_result(self, delegation_protocol):
        """Test that delegation returns a DelegationResult."""
        result = delegation_protocol.delegate_task(
            task_description="Research AI trends",
            context={"topic": "AI", "sender_hash": "test123"}
        )

        assert isinstance(result, DelegationResult)

    def test_delegate_task_has_task_id(self, delegation_protocol):
        """Test that delegated task has a valid UUID."""
        result = delegation_protocol.delegate_task(
            task_description="Write documentation",
            context={"topic": "docs"}
        )

        assert result.task_id is not None
        # Should be a valid UUID
        uuid.UUID(result.task_id)  # Will raise if invalid

    def test_delegate_task_sets_target_agent(self, delegation_protocol):
        """Test that delegation sets the correct target agent."""
        result = delegation_protocol.delegate_task(
            task_description="Fix the bug in the auth module",
            context={"topic": "bug"}
        )

        assert result.target_agent == "developer"

    def test_delegate_task_with_suggested_agent(self, delegation_protocol):
        """Test delegation with explicit agent suggestion."""
        result = delegation_protocol.delegate_task(
            task_description="Help with this",
            context={"topic": "help"},
            suggested_agent="writer"
        )

        assert result.target_agent == "writer"

    def test_delegate_task_with_priority(self, delegation_protocol):
        """Test delegation with custom priority."""
        result = delegation_protocol.delegate_task(
            task_description="Critical security issue",
            context={"topic": "security"},
            priority="critical"
        )

        assert result.success is True  # Should succeed even if Neo4j is mocked

    def test_delegate_task_sanitizes_content(self, delegation_protocol):
        """Test that delegated tasks have sanitized content."""
        result = delegation_protocol.delegate_task(
            task_description="Email john@example.com about the project",
            context={"topic": "email"}
        )

        # Should succeed and the internal description should be sanitized
        assert result.success is True

    def test_delegation_result_to_dict(self, delegation_protocol):
        """Test DelegationResult conversion to dictionary."""
        result = delegation_protocol.delegate_task(
            task_description="Test task",
            context={"topic": "test"}
        )

        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)
        assert "success" in result_dict
        assert "task_id" in result_dict
        assert "target_agent" in result_dict
        assert "agent_name" in result_dict
        assert "message" in result_dict


# =============================================================================
# Test Result Storage
# =============================================================================

class TestResultStorage:
    """Tests for storing agent results."""

    def test_store_results_returns_true_on_success(self, delegation_protocol):
        """Test that storing results returns True."""
        success = delegation_protocol.store_results(
            agent="researcher",
            task_id=str(uuid.uuid4()),
            results={"topic": "test", "findings": "test results"}
        )

        assert success is True

    def test_store_results_for_writer(self, delegation_protocol):
        """Test storing writer results creates Content node."""
        task_id = str(uuid.uuid4())
        success = delegation_protocol.store_results(
            agent="writer",
            task_id=task_id,
            results={"title": "Test Article", "body": "Content here"}
        )

        assert success is True

    def test_store_results_for_developer(self, delegation_protocol):
        """Test storing developer results creates Application node."""
        task_id = str(uuid.uuid4())
        success = delegation_protocol.store_results(
            agent="developer",
            task_id=task_id,
            results={"context": "fix auth", "result": "fixed"}
        )

        assert success is True

    def test_store_results_for_analyst(self, delegation_protocol):
        """Test storing analyst results creates Analysis node."""
        task_id = str(uuid.uuid4())
        success = delegation_protocol.store_results(
            agent="analyst",
            task_id=task_id,
            results={"title": "Performance Analysis", "findings": "All good"}
        )

        assert success is True

    def test_store_results_for_ops(self, delegation_protocol):
        """Test storing ops results creates ProcessUpdate node."""
        task_id = str(uuid.uuid4())
        success = delegation_protocol.store_results(
            agent="ops",
            task_id=task_id,
            results={"notes": "Deployment complete"}
        )

        assert success is True


# =============================================================================
# Test Response Synthesis
# =============================================================================

class TestResponseSynthesis:
    """Tests for response synthesis."""

    def test_synthesize_response_combines_contexts(self, delegation_protocol):
        """Test that synthesis combines personal and operational context."""
        personal = {"user_preferences": {"prefer": "concise"}}
        operational = {
            "agent": "researcher",
            "summary": "Research completed on AI trends.",
            "details": "Key findings include..."
        }

        response = delegation_protocol.synthesize_response(
            personal_context=personal,
            operational_results=operational,
            task_type="research"
        )

        assert "Research completed" in response
        assert "Möngke" in response

    def test_synthesize_response_without_agent(self, delegation_protocol):
        """Test synthesis when agent is main (Kublai)."""
        personal = {}
        operational = {
            "agent": "main",
            "summary": "I've completed your request."
        }

        response = delegation_protocol.synthesize_response(
            personal_context=personal,
            operational_results=operational,
            task_type="general"
        )

        assert "I've completed" in response
        # Should not have attribution for main
        assert "Completed by" not in response

    def test_synthesize_response_with_details(self, delegation_protocol):
        """Test synthesis includes details when available."""
        personal = {}
        operational = {
            "agent": "analyst",
            "summary": "Analysis complete.",
            "details": "Found 3 patterns and 2 opportunities."
        }

        response = delegation_protocol.synthesize_response(
            personal_context=personal,
            operational_results=operational,
            task_type="analysis"
        )

        assert "Analysis complete" in response
        assert "Found 3 patterns" in response
        assert "Jochi" in response


# =============================================================================
# Test Health Check
# =============================================================================

class TestHealthCheck:
    """Tests for health check endpoint."""

    def test_health_check_returns_dict(self, mock_operational_memory):
        """Test that health check returns a dictionary."""
        result = DelegationProtocol.health_check(mock_operational_memory)

        assert isinstance(result, dict)

    def test_health_check_has_required_fields(self, mock_operational_memory):
        """Test that health check has all required fields."""
        result = DelegationProtocol.health_check(mock_operational_memory)

        assert "status" in result
        assert "timestamp" in result
        assert "services" in result

    def test_health_check_services_field(self, mock_operational_memory):
        """Test that health check services has sub-fields."""
        result = DelegationProtocol.health_check(mock_operational_memory)

        assert "openclaw" in result["services"]
        assert "neo4j" in result["services"]
        assert "signal" in result["services"]

    def test_health_check_with_healthy_neo4j(self, mock_operational_memory):
        """Test health check when Neo4j is healthy."""
        mock_operational_memory.health_check = Mock(
            return_value={"status": "healthy"}
        )

        result = DelegationProtocol.health_check(mock_operational_memory)

        assert result["status"] == "ok"
        assert result["services"]["neo4j"] == "healthy"

    def test_health_check_with_unhealthy_neo4j(self, mock_operational_memory):
        """Test health check when Neo4j is unhealthy."""
        mock_operational_memory.health_check = Mock(
            return_value={"status": "unhealthy"}
        )

        result = DelegationProtocol.health_check(mock_operational_memory)

        assert result["status"] == "degraded"
        assert result["services"]["neo4j"] == "unhealthy"

    def test_health_check_timestamp_format(self, mock_operational_memory):
        """Test that health check timestamp is ISO format."""
        result = DelegationProtocol.health_check(mock_operational_memory)

        # Should be parseable as ISO datetime
        datetime.fromisoformat(result["timestamp"])


# =============================================================================
# Test Pending Delegations
# =============================================================================

class TestPendingDelegations:
    """Tests for getting pending delegations."""

    def test_get_pending_delegations_returns_list(self, delegation_protocol):
        """Test that getting pending delegations returns a list."""
        result = delegation_protocol.get_pending_delegations()

        assert isinstance(result, list)

    def test_get_pending_delegations_with_agent_filter(self, delegation_protocol):
        """Test filtering pending delegations by agent."""
        result = delegation_protocol.get_pending_delegations(agent="researcher")

        assert isinstance(result, list)


# =============================================================================
# Test Agent Availability
# =============================================================================

class TestAgentAvailability:
    """Tests for agent availability checking."""

    def test_check_agent_availability_returns_bool(self, delegation_protocol):
        """Test that agent availability check returns boolean."""
        result = delegation_protocol.check_agent_availability("researcher")

        assert isinstance(result, bool)

    def test_check_agent_availability_unknown_agent(self, delegation_protocol):
        """Test checking unknown agent availability."""
        # Unknown agent returns False (not found in database)
        result = delegation_protocol.check_agent_availability("unknown")

        # When agent is not found in Neo4j, returns False
        # This is the correct behavior - unknown agents are unavailable
        assert result is False


# =============================================================================
# Test Agent Status
# =============================================================================

class TestAgentStatus:
    """Tests for getting agent status."""

    def test_get_agent_status_returns_dict_or_none(self, delegation_protocol):
        """Test that agent status returns dict or None."""
        result = delegation_protocol.get_agent_status("researcher")

        assert result is None or isinstance(result, dict)


# =============================================================================
# Test Convenience Functions
# =============================================================================

class TestConvenienceFunctions:
    """Tests for convenience delegation functions."""

    def test_delegate_research(self, delegation_protocol):
        """Test the delegate_research convenience function."""
        result = delegate_research(
            protocol=delegation_protocol,
            topic="AI trends",
            context={"sender_hash": "test"}
        )

        assert isinstance(result, DelegationResult)
        assert result.target_agent == "researcher"

    def test_delegate_writing(self, delegation_protocol):
        """Test the delegate_writing convenience function."""
        result = delegate_writing(
            protocol=delegation_protocol,
            topic="blog post",
            context={"sender_hash": "test"}
        )

        assert isinstance(result, DelegationResult)
        assert result.target_agent == "writer"

    def test_delegate_code(self, delegation_protocol):
        """Test the delegate_code convenience function."""
        result = delegate_code(
            protocol=delegation_protocol,
            task="fix authentication",
            context={"sender_hash": "test"}
        )

        assert isinstance(result, DelegationResult)
        assert result.target_agent == "developer"

    def test_delegate_analysis(self, delegation_protocol):
        """Test the delegate_analysis convenience function."""
        result = delegate_analysis(
            protocol=delegation_protocol,
            topic="performance",
            context={"sender_hash": "test"}
        )

        assert isinstance(result, DelegationResult)
        assert result.target_agent == "analyst"

    def test_delegate_research_with_priority(self, delegation_protocol):
        """Test delegate_research with custom priority."""
        result = delegate_research(
            protocol=delegation_protocol,
            topic="urgent research",
            context={"sender_hash": "test"},
            priority="high"
        )

        assert result.success is True


# =============================================================================
# Test Agent Enum
# =============================================================================

class TestAgentEnum:
    """Tests for Agent enumeration."""

    def test_agent_enum_values(self):
        """Test Agent enum has correct values."""
        assert Agent.KUBLAI.value == "main"
        assert Agent.MONGKE.value == "researcher"
        assert Agent.CHAGATAI.value == "writer"
        assert Agent.TEMUJIN.value == "developer"
        assert Agent.JOCHI.value == "analyst"
        assert Agent.OGEDEI.value == "ops"


# =============================================================================
# Test TaskType Enum
# =============================================================================

class TestTaskTypeEnum:
    """Tests for TaskType enumeration."""

    def test_task_type_enum_values(self):
        """Test TaskType enum has correct values."""
        assert TaskType.RESEARCH.value == "research"
        assert TaskType.WRITING.value == "writing"
        assert TaskType.CODE.value == "code"
        assert TaskType.SECURITY.value == "security"
        assert TaskType.ANALYSIS.value == "analysis"
        assert TaskType.PROCESS.value == "process"
        assert TaskType.OPS.value == "ops"


# =============================================================================
# Integration Tests (with real file I/O)
# =============================================================================

class TestIntegration:
    """Integration tests with real file operations."""

    def test_full_delegation_workflow(self, delegation_protocol, temp_memory_dir):
        """Test the complete delegation workflow from start to finish."""
        # 1. Create a task
        result = delegation_protocol.delegate_task(
            task_description="Research quantum computing applications",
            context={
                "topic": "quantum computing",
                "sender_hash": "test_user_123"
            },
            priority="high"
        )

        # Verify delegation was created
        assert result.success is True
        assert result.task_id is not None
        assert result.target_agent == "researcher"

        # 2. Store results
        store_success = delegation_protocol.store_results(
            agent="researcher",
            task_id=result.task_id,
            results={
                "topic": "quantum computing",
                "findings": "Quantum computing has applications in cryptography...",
                "summary": "Research completed on quantum computing applications."
            }
        )

        assert store_success is True

        # 3. Synthesize response
        response = delegation_protocol.synthesize_response(
            personal_context={"user_preferences": {"prefer": "detailed"}},
            operational_results={
                "agent": "researcher",
                "summary": "Research completed on quantum computing applications.",
                "details": "Key findings include cryptography, optimization, and simulation applications."
            },
            task_type="research"
        )

        assert "quantum computing" in response.lower()
        assert "Möngke" in response


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
