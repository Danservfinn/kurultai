"""
Kurultai Test Harness - Integration test infrastructure.

Provides a reusable test harness for integration tests that spawn real services:
- Neo4j testcontainers
- Mock OpenClaw gateway
- Mock agent processes
- Cleanup and teardown

Usage:
    harness = KurultaiTestHarness()
    await harness.setup()
    try:
        # Run tests
        result = await harness.send_agent_message("kublai", "mongke", {...})
    finally:
        await harness.teardown()
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock

import httpx

logger = logging.getLogger(__name__)


class MockAgent:
    """Mock agent for testing agent communication."""

    def __init__(
        self,
        agent_id: str,
        role: str,
        capabilities: List[str],
        response_delay: float = 0.1,
    ):
        self.agent_id = agent_id
        self.role = role
        self.capabilities = capabilities
        self.response_delay = response_delay
        self.messages_received: List[Dict] = []
        self.responses: List[Dict] = []

    async def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Process a message and return a response."""
        self.messages_received.append(message)
        await asyncio.sleep(self.response_delay)

        return {
            "type": "response",
            "agent_id": self.agent_id,
            "content": f"Test response from {self.agent_id}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "original_message_id": message.get("id"),
        }

    def reset(self):
        """Reset message history."""
        self.messages_received.clear()
        self.responses.clear()


class KurultaiTestHarness:
    """Spawns and manages test environment with real services.

    This harness provides:
    - Neo4j test container (via testcontainers or mock)
    - Mock OpenClaw gateway
    - Mock agents for all 6 specialist types
    - Helper methods for common operations

    In production, this would use testcontainers to spin up real Neo4j.
    For faster tests, it can use in-memory mocks.
    """

    def __init__(
        self,
        use_testcontainers: bool = False,
        neo4j_version: str = "5.15.0",
        gateway_port: int = 18789,
    ):
        self.use_testcontainers = use_testcontainers
        self.neo4j_version = neo4j_version
        self.gateway_port = gateway_port

        # Service references
        self.neo4j_container = None
        self.gateway_process = None
        self.neo4j_driver = None

        # Mock agents
        self.agents: Dict[str, MockAgent] = {}

        # Test state
        self._setup_complete = False
        self.tasks_created: List[str] = []

        logger.info(
            f"TestHarness initialized (testcontainers={use_testcontainers}, "
            f"neo4j={neo4j_version}, gateway_port={gateway_port})"
        )

    async def setup(self):
        """Start Neo4j container, gateway, and mock agents."""
        if self._setup_complete:
            logger.warning("Setup already complete, skipping")
            return

        logger.info("Setting up test harness...")

        # Start Neo4j (mocked for now, can use testcontainers)
        if self.use_testcontainers:
            await self._start_neo4j_container()
        else:
            await self._setup_mock_neo4j()

        # Start mock gateway
        await self._start_mock_gateway()

        # Register mock agents
        self._register_mock_agents()

        self._setup_complete = True
        logger.info("Test harness setup complete")

    async def _start_neo4j_container(self):
        """Start Neo4j testcontainer."""
        try:
            from testcontainers.neo4j import Neo4jContainer

            logger.info(f"Starting Neo4j {self.neo4j_version} container...")
            self.neo4j_container = Neo4jContainer(
                f"neo4j:{self.neo4j_version}", password="test_password"
            )
            self.neo4j_container.start()

            # Import neo4j driver and connect
            from neo4j import GraphDatabase

            uri = self.neo4j_container.get_connection_url()
            self.neo4j_driver = GraphDatabase.authenticated(
                uri, "neo4j", "test_password"
            )
            logger.info(f"Neo4j container started at {uri}")
        except ImportError:
            logger.warning(
                "testcontainers not installed, falling back to mock Neo4j. "
                "Install with: pip install testcontainers"
            )
            await self._setup_mock_neo4j()

    async def _setup_mock_neo4j(self):
        """Setup mock Neo4j driver for testing."""
        logger.info("Using mock Neo4j driver")
        # Create mock driver that will be used by OperationalMemory
        self.neo4j_driver = MagicMock()
        self.neo4j_driver.verify_connectivity = Mock()

        # Setup mock session
        mock_session = MagicMock()

        def mock_run(cypher: str, **kwargs):
            result = MagicMock()
            result.single.return_value = None
            result.data.return_value = []
            result.__iter__ = lambda self: iter([])
            result.peek.return_value = []
            return result

        mock_session.run = mock_run
        mock_session.close = Mock()

        # Setup session context manager
        session_ctx = MagicMock()
        session_ctx.__enter__ = Mock(return_value=mock_session)
        session_ctx.__exit__ = Mock(return_value=False)

        self.neo4j_driver.session = Mock(return_value=session_ctx)
        logger.info("Mock Neo4j driver configured")

    async def _start_mock_gateway(self):
        """Start mock OpenClaw gateway."""
        logger.info("Mock gateway configured (not running real server)")
        # In production, this would start an actual gateway process
        # For testing, we mock the HTTP client
        self.mock_gateway = AsyncMock()
        self.mock_gateway.post = AsyncMock(
            return_value=httpx.Response(
                200, json={"status": "delivered", "timestamp": time.time()}
            )
        )
        logger.info("Mock gateway configured")

    def _register_mock_agents(self):
        """Register all 6 specialist agents."""
        agent_configs = {
            "kublai": {
                "role": "orchestrator",
                "capabilities": ["delegation", "coordination", "synthesis"],
            },
            "mongke": {
                "role": "researcher",
                "capabilities": ["search", "summarize", "extract"],
            },
            "chagatai": {
                "role": "writer",
                "capabilities": ["write", "edit", "format"],
            },
            "temujin": {
                "role": "developer",
                "capabilities": ["code", "debug", "refactor"],
            },
            "jochi": {
                "role": "analyst",
                "capabilities": ["analyze", "review", "audit"],
            },
            "ogedei": {
                "role": "operations",
                "capabilities": ["ops", "deploy", "monitor"],
            },
        }

        for agent_id, config in agent_configs.items():
            self.agents[agent_id] = MockAgent(
                agent_id=agent_id,
                role=config["role"],
                capabilities=config["capabilities"],
                response_delay=0.05,  # Fast response for tests
            )

        logger.info(f"Registered {len(self.agents)} mock agents")

    async def teardown(self):
        """Cleanup all spawned processes and containers."""
        logger.info("Tearing down test harness...")

        # Stop agents in reverse order
        for agent_id in reversed(list(self.agents.keys())):
            self.agents[agent_id].reset()
            del self.agents[agent_id]

        # Close Neo4j driver
        if self.neo4j_driver:
            try:
                if hasattr(self.neo4j_driver, "close"):
                    self.neo4j_driver.close()
            except Exception as e:
                logger.warning(f"Error closing Neo4j driver: {e}")
            self.neo4j_driver = None

        # Stop container
        if self.neo4j_container:
            try:
                self.neo4j_container.stop()
            except Exception as e:
                logger.warning(f"Error stopping Neo4j container: {e}")
            self.neo4j_container = None

        self._setup_complete = False
        self.tasks_created.clear()
        logger.info("Test harness teardown complete")

    async def send_agent_message(
        self, from_agent: str, to_agent: str, message: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Send a message from one agent to another."""
        if to_agent not in self.agents:
            raise ValueError(f"Unknown target agent: {to_agent}")

        logger.debug(f"{from_agent} -> {to_agent}: {message.get('type', 'unknown')}")
        response = await self.agents[to_agent].process_message(message)
        return response

    async def create_task(
        self,
        task_id: str,
        title: str,
        description: str = "",
        task_type: str = "generic",
        status: str = "pending",
    ) -> Dict[str, Any]:
        """Create a test task."""
        task = {
            "task_id": task_id,
            "title": title,
            "description": description,
            "task_type": task_type,
            "status": status,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.tasks_created.append(task_id)
        return task

    async def claim_task(self, task_id: str, agent_id: str) -> Dict[str, Any]:
        """Simulate task claiming."""
        return {
            "task_id": task_id,
            "claimed": True,
            "agent_id": agent_id,
            "claimed_at": datetime.now(timezone.utc).isoformat(),
        }

    async def complete_task(
        self, task_id: str, result: str = "Task completed"
    ) -> Dict[str, Any]:
        """Simulate task completion."""
        return {
            "task_id": task_id,
            "status": "completed",
            "result": result,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }

    async def get_agent(self, agent_id: str) -> Dict[str, Any]:
        """Get agent information."""
        if agent_id not in self.agents:
            raise ValueError(f"Unknown agent: {agent_id}")

        agent = self.agents[agent_id]
        return {
            "agent_id": agent.agent_id,
            "role": agent.role,
            "capabilities": agent.capabilities,
            "messages_received": len(agent.messages_received),
            "last_heartbeat": datetime.now(timezone.utc).isoformat(),
        }

    def get_tasks_created(self) -> List[str]:
        """Get list of task IDs created during test."""
        return self.tasks_created.copy()


class AsyncContextManager:
    """Helper for creating async context managers from non-async objects."""

    def __init__(self, obj):
        self.obj = obj

    async def __aenter__(self):
        return self.obj

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if hasattr(self.obj, "close"):
            self.obj.close()


# Pytest fixtures (only available if pytest is installed)
try:
    import pytest

    @pytest.fixture
    async def integration_harness():
        """Pytest fixture for integration test harness."""
        harness = KurultaiTestHarness(use_testcontainers=False)
        await harness.setup()
        try:
            yield harness
        finally:
            await harness.teardown()

    @pytest.fixture
    def mock_agents():
        """Pytest fixture for mock agents."""
        agents = {}
        agent_configs = {
            "kublai": {"role": "orchestrator", "capabilities": ["delegation"]},
            "mongke": {"role": "researcher", "capabilities": ["search", "summarize"]},
            "chagatai": {"role": "writer", "capabilities": ["write"]},
            "temujin": {"role": "developer", "capabilities": ["code"]},
            "jochi": {"role": "analyst", "capabilities": ["analyze"]},
            "ogedei": {"role": "operations", "capabilities": ["ops"]},
        }

        for agent_id, config in agent_configs.items():
            agents[agent_id] = MockAgent(
                agent_id=agent_id,
                role=config["role"],
                capabilities=config["capabilities"],
            )

        return agents

    # Export fixtures
    __all__ = [
        "KurultaiTestHarness",
        "MockAgent",
        "integration_harness",
        "mock_agents",
    ]

except ImportError:
    # pytest not available
    __all__ = ["KurultaiTestHarness", "MockAgent"]
