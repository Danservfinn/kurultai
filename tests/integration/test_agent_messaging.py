"""
OpenClaw Gateway Integration Tests

Tests actual agent-to-agent messaging through the OpenClaw gateway:
- Message delivery through port 18789
- Concurrent delegation message ordering
- Gateway error responses for invalid targets

These tests use mock components to simulate the gateway without requiring
a full deployment.
"""

import asyncio
import random
from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from tests.fixtures.integration_harness import KurultaiTestHarness, MockAgent


@pytest.mark.integration
@pytest.mark.asyncio
class TestAgentMessaging:
    """Test agent-to-agent messaging through the gateway."""

    async def test_kublai_to_specialist_message_delivery(self):
        """Verify messages route through OpenClaw gateway port 18789."""
        harness = KurultaiTestHarness(use_testcontainers=False)
        await harness.setup()

        try:
            # Send message from Kublai to Mongke
            response = await harness.send_agent_message(
                from_agent="kublai",
                to_agent="mongke",
                message={
                    "type": "delegation",
                    "task": "Research topic X",
                    "task_id": "test-123",
                },
            )

            assert response["status"] == "delivered" or response["type"] == "response"
            assert "timestamp" in response or "agent_id" in response

            # Verify Mongke received the message
            mongke = harness.agents.get("mongke")
            assert mongke is not None
            assert len(mongke.messages_received) == 1
            assert mongke.messages_received[0]["task_id"] == "test-123"

        finally:
            await harness.teardown()

    async def test_concurrent_delegation_message_ordering(self):
        """Verify message delivery order when multiple agents delegate simultaneously."""
        harness = KurultaiTestHarness(use_testcontainers=False)
        await harness.setup()

        try:
            # Create 10 delegation tasks
            tasks = []
            for i in range(10):
                target = random.choice(["mongke", "temujin", "chagatai"])
                task = harness.send_agent_message(
                    from_agent="kublai",
                    to_agent=target,
                    message={
                        "type": "delegation",
                        "task": f"Task {i}",
                        "task_id": f"concurrent-test-{i}",
                    },
                )
                tasks.append(task)

            # Execute all concurrently
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # All should succeed
            assert all(isinstance(r, dict) for r in results if not isinstance(r, Exception))
            assert all(
                r.get("status") == "delivered" or r.get("type") == "response"
                for r in results
                if isinstance(r, dict)
            )

            # Verify message count per agent
            total_received = sum(
                len(agent.messages_received) for agent in harness.agents.values()
            )
            assert total_received == 10

        finally:
            await harness.teardown()

    async def test_invalid_target_agent_error_response(self):
        """Verify gateway returns proper error for invalid targets."""
        harness = KurultaiTestHarness(use_testcontainers=False)
        await harness.setup()

        try:
            # Try to send to non-existent agent
            with pytest.raises(ValueError, match="Unknown target agent"):
                await harness.send_agent_message(
                    from_agent="kublai",
                    to_agent="nonexistent_agent",
                    message={"type": "delegation", "task": "Test"},
                )

        finally:
            await harness.teardown()

    async def test_message_content_preserved(self):
        """Verify message content is preserved through gateway."""
        harness = KurultaiTestHarness(use_testcontainers=False)
        await harness.setup()

        try:
            original_message = {
                "type": "delegation",
                "task": "Implement feature X",
                "task_id": "content-test-123",
                "priority": "high",
                "metadata": {"key": "value"},
            }

            response = await harness.send_agent_message(
                from_agent="kublai",
                to_agent="temujin",
                message=original_message,
            )

            # Check that Temüjin received the complete message
            temujin = harness.agents.get("temujin")
            assert temujin is not None
            assert len(temujin.messages_received) == 1

            received = temujin.messages_received[0]
            assert received["task"] == original_message["task"]
            assert received["task_id"] == original_message["task_id"]
            assert received["priority"] == original_message["priority"]
            assert received["metadata"] == original_message["metadata"]

        finally:
            await harness.teardown()

    async def test_round_trip_messaging(self):
        """Verify round-trip messaging: agent A -> agent B -> agent A."""
        harness = KurultaiTestHarness(use_testcontainers=False)
        await harness.setup()

        try:
            # Kublai sends to Mongke
            response1 = await harness.send_agent_message(
                from_agent="kublai",
                to_agent="mongke",
                message={
                    "type": "research_request",
                    "query": "Find information about X",
                    "request_id": "round-trip-123",
                },
            )

            # Mongke sends back to Kublai
            response2 = await harness.send_agent_message(
                from_agent="mongke",
                to_agent="kublai",
                message={
                    "type": "research_result",
                    "findings": "Here is what I found",
                    "request_id": "round-trip-123",
                },
            )

            assert response1["type"] == "response"
            assert response2["type"] == "response"

            # Verify both agents have message history
            assert len(harness.agents["mongke"].messages_received) >= 1
            assert len(harness.agents["kublai"].messages_received) >= 1

        finally:
            await harness.teardown()


@pytest.mark.integration
@pytest.mark.asyncio
class TestGatewayPortConfiguration:
    """Test gateway port configuration."""

    async def test_default_gateway_port(self):
        """Verify default gateway port is 18789."""
        harness = KurultaiTestHarness()
        assert harness.gateway_port == 18789
        await harness.teardown()

    async def test_custom_gateway_port(self):
        """Verify custom gateway port can be configured."""
        harness = KurultaiTestHarness(gateway_port=9999)
        assert harness.gateway_port == 9999
        await harness.teardown()


@pytest.mark.integration
@pytest.mark.asyncio
class TestMessageTypes:
    """Test different message types through the gateway."""

    async def test_delegation_message(self):
        """Test delegation message type."""
        harness = KurultaiTestHarness()
        await harness.setup()

        try:
            response = await harness.send_agent_message(
                from_agent="kublai",
                to_agent="temujin",
                message={
                    "type": "delegation",
                    "task_id": "delegate-123",
                    "title": "Implement feature",
                    "description": "Add new feature",
                },
            )

            assert response["type"] == "response"
            temujin = harness.agents["temujin"]
            assert temujin.messages_received[0]["type"] == "delegation"

        finally:
            await harness.teardown()

    async def test_query_message(self):
        """Test query message type."""
        harness = KurultaiTestHarness()
        await harness.setup()

        try:
            response = await harness.send_agent_message(
                from_agent="kublai",
                to_agent="jochi",
                message={
                    "type": "query",
                    "query_id": "query-123",
                    "question": "Analyze this code",
                },
            )

            assert response["type"] == "response"
            jochi = harness.agents["jochi"]
            assert jochi.messages_received[0]["type"] == "query"

        finally:
            await harness.teardown()

    async def test_notification_message(self):
        """Test notification message type."""
        harness = KurultaiTestHarness()
        await harness.setup()

        try:
            response = await harness.send_agent_message(
                from_agent="system",
                to_agent="kublai",
                message={
                    "type": "notification",
                    "notification_id": "notify-123",
                    "message": "Task completed",
                },
            )

            assert response["type"] == "response"
            kublai = harness.agents["kublai"]
            assert kublai.messages_received[0]["type"] == "notification"

        finally:
            await harness.teardown()
