"""
Mock Agent Factory - Creates consistent mock agents for testing.

This module provides factory methods for creating mock agents that:
- Have correct role and capabilities
- Return structured responses
- Support async operations
- Can be configured for specific test scenarios

Usage:
    from tests.fixtures.mock_agents import MockAgentFactory

    # Create a specific agent
    kublai = MockAgentFactory.create_kublai()

    # Create with custom response
    mongke = MockAgentFactory.create_researcher(
        response_data={"findings": "Test research results"}
    )
"""

from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, Mock

import pytest


class MockAgent:
    """Base mock agent with common functionality."""

    def __init__(
        self,
        agent_id: str,
        role: str,
        capabilities: List[str],
        status: str = "active",
    ):
        self.agent_id = agent_id
        self.role = role
        self.capabilities = capabilities
        self.status = status
        self.messages_received: List[Dict] = []
        self.last_heartbeat: Optional[str] = None

        # Create async mock for process_message
        self.process_message = AsyncMock(
            return_value={
                "type": "response",
                "agent_id": agent_id,
                "content": f"Response from {agent_id}",
                "success": True,
            }
        )

    def set_response(self, response: Dict[str, Any]):
        """Set a custom response for process_message."""
        self.process_message = AsyncMock(return_value=response)

    def add_to_response_sequence(self, responses: List[Dict[str, Any]]):
        """Set up a sequence of responses."""
        self.process_message = AsyncMock(side_effect=responses)

    def reset(self):
        """Reset message history and mocks."""
        self.messages_received.clear()
        self.process_message.reset_mock()

    def assert_called_with_message(self, message_type: str, **kwargs):
        """Assert that process_message was called with specific criteria."""
        assert self.process_message.called, "Agent was not called"
        call_args = self.process_message.call_args
        if call_args:
            msg = call_args[0][0] if call_args[0] else {}
            assert msg.get("type") == message_type or any(
                msg.get(k) == v for k, v in kwargs.items()
            )


class MockAgentFactory:
    """Factory for creating consistent mock agents."""

    # Agent capability definitions
    AGENT_CAPABILITIES = {
        "kublai": ["delegation", "coordination", "synthesis", "monitoring", "routing"],
        "mongke": ["search", "summarize", "extract", "research", "analysis"],
        "chagatai": ["write", "edit", "format", "document", "content"],
        "temujin": ["code", "debug", "refactor", "implement", "testing"],
        "jochi": ["analyze", "review", "audit", "metrics", "performance"],
        "ogedei": ["ops", "deploy", "monitor", "failover", "emergency"],
    }

    # Agent role definitions
    AGENT_ROLES = {
        "kublai": "orchestrator",
        "mongke": "researcher",
        "chagatai": "writer",
        "temujin": "developer",
        "jochi": "analyst",
        "ogedei": "operations",
    }

    @classmethod
    def create_agent(
        cls,
        agent_id: str,
        status: str = "active",
        custom_response: Optional[Dict[str, Any]] = None,
    ) -> MockAgent:
        """Create a mock agent by ID with default configuration."""
        if agent_id not in cls.AGENT_CAPABILITIES:
            raise ValueError(f"Unknown agent ID: {agent_id}")

        agent = MockAgent(
            agent_id=agent_id,
            role=cls.AGENT_ROLES[agent_id],
            capabilities=cls.AGENT_CAPABILITIES[agent_id],
            status=status,
        )

        if custom_response:
            agent.set_response(custom_response)

        return agent

    @classmethod
    def create_kublai(
        cls, custom_response: Optional[Dict[str, Any]] = None
    ) -> MockAgent:
        """Create Kublai with delegation protocol mocked."""
        response = custom_response or {
            "type": "delegation_result",
            "agent_id": "kublai",
            "delegated_to": "mongke",
            "task_id": "test-task-123",
            "success": True,
        }
        return cls.create_agent("kublai", custom_response=response)

    @classmethod
    def create_mongke(
        cls, findings: str = "Research findings summary", **kwargs
    ) -> MockAgent:
        """Create Mongke with research capabilities."""
        response = kwargs.get(
            "custom_response",
            {
                "type": "research_result",
                "agent_id": "mongke",
                "content": findings,
                "sources": ["source1", "source2"],
                "success": True,
            },
        )
        return cls.create_agent("mongke", custom_response=response)

    @classmethod
    def create_chagatai(
        cls, content: str = "Written content", **kwargs
    ) -> MockAgent:
        """Create Chagatai with writing capabilities."""
        response = kwargs.get(
            "custom_response",
            {
                "type": "writing_result",
                "agent_id": "chagatai",
                "content": content,
                "word_count": 100,
                "success": True,
            },
        )
        return cls.create_agent("chagatai", custom_response=response)

    @classmethod
    def create_temujin(
        cls, code: str = "def example():\n    pass", **kwargs
    ) -> MockAgent:
        """Create Temüjin with development capabilities."""
        response = kwargs.get(
            "custom_response",
            {
                "type": "code_result",
                "agent_id": "temujin",
                "content": code,
                "language": "python",
                "success": True,
            },
        )
        return cls.create_agent("temujin", custom_response=response)

    @classmethod
    def create_jochi(
        cls, analysis: str = "Analysis complete", **kwargs
    ) -> MockAgent:
        """Create Jochi with analysis capabilities."""
        response = kwargs.get(
            "custom_response",
            {
                "type": "analysis_result",
                "agent_id": "jochi",
                "content": analysis,
                "metrics": {"complexity": 0.7, "confidence": 0.9},
                "success": True,
            },
        )
        return cls.create_agent("jochi", custom_response=response)

    @classmethod
    def create_ogedei(
        cls, operation: str = "Operation complete", **kwargs
    ) -> MockAgent:
        """Create Ögedei with operations capabilities."""
        response = kwargs.get(
            "custom_response",
            {
                "type": "ops_result",
                "agent_id": "ogedei",
                "content": operation,
                "success": True,
            },
        )
        return cls.create_agent("ogedei", custom_response=response)

    @classmethod
    def create_all_agents(cls, status: str = "active") -> Dict[str, MockAgent]:
        """Create all 6 agents with default configuration."""
        return {
            "kublai": cls.create_kublai(),
            "mongke": cls.create_mongke(),
            "chagatai": cls.create_chagatai(),
            "temujin": cls.create_temujin(),
            "jochi": cls.create_jochi(),
            "ogedei": cls.create_ogedei(),
        }

    @classmethod
    def create_unavailable_agent(cls, agent_id: str) -> MockAgent:
        """Create an agent that simulates being unavailable."""
        agent = cls.create_agent(agent_id, status="unavailable")

        async def unavailable_response(message):
            raise Exception(f"Agent {agent_id} is unavailable")

        agent.process_message = AsyncMock(side_effect=unavailable_response)
        return agent

    @classmethod
    def create_slow_agent(cls, agent_id: str, delay_seconds: float = 2.0) -> MockAgent:
        """Create an agent with artificial delay."""
        import asyncio

        async def slow_response(message):
            await asyncio.sleep(delay_seconds)
            return {
                "type": "response",
                "agent_id": agent_id,
                "content": f"Slow response after {delay_seconds}s",
                "success": True,
            }

        agent = cls.create_agent(agent_id)
        agent.process_message = AsyncMock(side_effect=slow_response)
        return agent


# Pytest fixtures (only available if pytest is installed)
try:
    import pytest

    @pytest.fixture
    def mock_kublai():
        """Pytest fixture for Kublai mock agent."""
        return MockAgentFactory.create_kublai()

    @pytest.fixture
    def mock_mongke():
        """Pytest fixture for Mongke mock agent."""
        return MockAgentFactory.create_mongke()

    @pytest.fixture
    def mock_chagatai():
        """Pytest fixture for Chagatai mock agent."""
        return MockAgentFactory.create_chagatai()

    @pytest.fixture
    def mock_temujin():
        """Pytest fixture for Temüjin mock agent."""
        return MockAgentFactory.create_temujin()

    @pytest.fixture
    def mock_jochi():
        """Pytest fixture for Jochi mock agent."""
        return MockAgentFactory.create_jochi()

    @pytest.fixture
    def mock_ogedei():
        """Pytest fixture for Ögedei mock agent."""
        return MockAgentFactory.create_ogedei()

    @pytest.fixture
    def all_mock_agents():
        """Pytest fixture for all 6 mock agents."""
        return MockAgentFactory.create_all_agents()

    # Fixtures available
    _pytest_fixtures = [
        "mock_kublai",
        "mock_mongke",
        "mock_chagatai",
        "mock_temujin",
        "mock_jochi",
        "mock_ogedei",
        "all_mock_agents",
    ]

except ImportError:
    _pytest_fixtures = []


__all__ = [
    "MockAgent",
    "MockAgentFactory",
    "mock_kublai",
    "mock_mongke",
    "mock_chagatai",
    "mock_temujin",
    "mock_jochi",
    "mock_ogedei",
    "all_mock_agents",
]
