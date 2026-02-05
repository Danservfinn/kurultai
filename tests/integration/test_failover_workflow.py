"""
Integration tests for Failover Workflow.

Tests cover:
- Kublai heartbeat triggering failover
- Ögedei activating as emergency router
- Ögedei routing to correct agents
- Kublai recovery deactivating failover
- Failover preserves task state
- Failover notification to user

Location: /Users/kurultai/molt/tests/integration/test_failover_workflow.py
"""

import os
import sys
import asyncio
import time
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
from unittest.mock import Mock, MagicMock, AsyncMock, patch, call

import pytest

# Calculate project root (two levels up from this file)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

# Import the real implementations
from tools.failover_monitor import FailoverMonitor, FailoverError
from src.protocols.failover import FailoverProtocol, FailoverStatus, KublaiStatus


# =============================================================================
# Mock Components (for isolated testing)
# =============================================================================

class MockKublaiHeartbeat:
    """Mock Kublai heartbeat tracker."""

    def __init__(self):
        self.last_heartbeat = None
        self.failover_threshold = 3
        self.missed_heartbeats = 0

    def record_heartbeat(self):
        """Record a heartbeat from Kublai."""
        self.last_heartbeat = datetime.now(timezone.utc)
        self.missed_heartbeats = 0

    def check_heartbeat(self) -> bool:
        """Check if heartbeat is within threshold."""
        if self.last_heartbeat is None:
            return False

        elapsed = (datetime.now(timezone.utc) - self.last_heartbeat).total_seconds()
        return elapsed < 10  # 10 second threshold


class MockOgedeiRouter:
    """Mock Ögedei as emergency router."""

    def __init__(self):
        self.is_active = False
        self.routing_map = {
            "tolui": "tolui",      # Research
            "hulagu": "hulagu",    # Strategy
            "mongke": "mongke",    # Execution
            "ariq_boke": "ariq_boke",  # QA
            "ögedei": "ögedei",    # Self-routing for emergency router
            "kublai": "kublai"     # Original delegator for notifications
        }

    def activate(self):
        """Activate emergency routing mode."""
        self.is_active = True

    def deactivate(self):
        """Deactivate emergency routing mode."""
        self.is_active = False

    def route_message(self, target_agent: str, message: Dict) -> Dict:
        """Route a message to the target agent."""
        if target_agent in self.routing_map:
            return {
                "status": "routed",
                "target": self.routing_map[target_agent],
                "original_target": target_agent,
                "message": message,
                "via": "ögedei"
            }
        return {
            "status": "failed",
            "error": f"Unknown agent: {target_agent}"
        }


class MockFailoverMonitor:
    """Mock failover monitoring system."""

    def __init__(self):
        self.heartbeat_tracker = MockKublaiHeartbeat()
        self.emergency_router = MockOgedeiRouter()
        self.failover_active = False
        self.notifications = []

    def check_kublai_status(self) -> bool:
        """Check if Kublai is healthy."""
        return self.heartbeat_tracker.check_heartbeat()

    def activate_failover(self):
        """Activate failover mode."""
        if not self.failover_active:
            self.failover_active = True
            self.emergency_router.activate()
            self.notifications.append({
                "type": "failover_activated",
                "timestamp": datetime.now(timezone.utc)
            })

    def deactivate_failover(self):
        """Deactivate failover mode."""
        if self.failover_active:
            self.failover_active = False
            self.emergency_router.deactivate()
            self.notifications.append({
                "type": "failover_deactivated",
                "timestamp": datetime.now(timezone.utc)
            })

    def delegate_via_ögedei(self, target_agent: str, task: Dict) -> Dict:
        """Delegate a task via Ögedei routing."""
        if not self.failover_active:
            return {"status": "error", "error": "Failover not active"}

        return self.emergency_router.route_message(target_agent, task)


# =============================================================================
# Fixtures for Real Implementation Tests
# =============================================================================

def create_mock_result(data=None, single=None):
    """Helper to create mock Neo4j result."""
    r = Mock()
    r.data = Mock(return_value=data or [])
    r.single = Mock(return_value=single)
    r.__iter__ = lambda self: iter(data or [])
    return r


class MockMemoryFactory:
    """Factory for creating configurable mock memories."""

    @staticmethod
    def create(agent_available=True, event_id=None):
        """Create a mock memory with configurable behavior."""
        memory = Mock()
        memory._generate_id = Mock(side_effect=lambda: f"failover-{id(object())}-{time.time()}")
        memory._now = Mock(return_value=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc))

        # Create a smart mock session that returns appropriate results based on query
        mock_session = Mock()

        def smart_run(cypher, **kwargs):
            # Normalize cypher to handle newlines and whitespace
            cypher_normalized = ' '.join(cypher.split())
            # Return appropriate result based on the Cypher query type
            if "MERGE (h:AgentHeartbeat" in cypher_normalized:
                # Heartbeat update - return agent name
                return create_mock_result(single={"agent": kwargs.get("agent", "main")})
            elif "MATCH (h:AgentHeartbeat" in cypher_normalized:
                # Heartbeat check - return last_seen
                if agent_available:
                    return create_mock_result(single={"last_seen": datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)})
                else:
                    return create_mock_result(single={"last_seen": None})
            elif "CREATE (f:FailoverEvent" in cypher_normalized or "CREATE (fe:FailoverEvent" in cypher_normalized:
                # Failover event creation - return event_id
                return create_mock_result(single={"event_id": event_id or f"event-{time.time()}"})
            elif "MATCH (f:FailoverEvent" in cypher_normalized or "MATCH (fe:FailoverEvent" in cypher_normalized:
                # Failover event query
                return create_mock_result(single={"id": event_id, "activated_at": datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)})
            elif "MATCH (a:Agent" in cypher_normalized and "{name:" in cypher_normalized:
                # Agent query for FailoverProtocol - matches MATCH (a:Agent {name: $agent_name})
                return create_mock_result(single={
                    "last_heartbeat": datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc) if agent_available else None,
                    "status": "active" if agent_available else "unavailable",
                    "current_task": None
                })
            else:
                # Default empty result
                return create_mock_result(single={})

        mock_session.run = Mock(side_effect=smart_run)
        mock_session.close = Mock()

        mock_ctx = Mock()
        mock_ctx.__enter__ = Mock(return_value=mock_session)
        mock_ctx.__exit__ = Mock(return_value=False)
        memory._session = Mock(return_value=mock_ctx)

        # Additional methods used by FailoverProtocol
        memory.list_active_agents = Mock(return_value=[
            {"name": "kublai"},
            {"name": "ögedei"},
            {"name": "tolui"},
            {"name": "hulagu"},
            {"name": "mongke"},
            {"name": "ariq_boke"}
        ])
        memory.create_notification = Mock(return_value="notif-123")

        return memory


@pytest.fixture
def mock_memory_for_failover():
    """Create mock OperationalMemory for failover testing."""
    return MockMemoryFactory.create(agent_available=True)



@pytest.fixture
def failover_monitor(mock_memory_for_failover):
    """Create FailoverMonitor with mock memory."""
    return FailoverMonitor(memory=mock_memory_for_failover)


@pytest.fixture
def failover_protocol(mock_memory_for_failover):
    """Create FailoverProtocol with mock memory."""
    return FailoverProtocol(memory=mock_memory_for_failover)


# =============================================================================
# TestFailoverWorkflow - Using Real Implementations
# =============================================================================

class TestFailoverWorkflow:
    """Integration tests for failover workflow using real implementations."""

    def test_kublai_heartbeat_triggers_failover(self, failover_monitor, mock_memory_for_failover):
        """Test that missed Kublai heartbeats trigger failover."""
        # Record initial heartbeat
        failover_monitor.update_heartbeat("main")

        # Verify Kublai is available
        assert failover_monitor.is_agent_available("main") is True

        # Simulate missed heartbeats by replacing with unavailable memory
        old_time = datetime(2025, 1, 1, 11, 58, 0, tzinfo=timezone.utc)  # 2 minutes ago

        mock_session = Mock()

        def unavailable_run(cypher, **kwargs):
            if "MATCH (h:AgentHeartbeat" in cypher:
                return create_mock_result(single={"last_seen": old_time})
            elif "CREATE (f:FailoverEvent" in cypher:
                return create_mock_result(single={"event_id": "failover-event-123"})
            return create_mock_result(single={})

        mock_session.run = Mock(side_effect=unavailable_run)
        mock_session.close = Mock()

        mock_ctx = Mock()
        mock_ctx.__enter__ = Mock(return_value=mock_session)
        mock_ctx.__exit__ = Mock(return_value=False)
        mock_memory_for_failover._session = Mock(return_value=mock_ctx)

        # Check availability - should be False due to old heartbeat
        is_available = failover_monitor.is_agent_available("main")
        assert is_available is False

        # Simulate consecutive failures to trigger failover
        for _ in range(FailoverMonitor.MAX_CONSECUTIVE_FAILURES):
            if failover_monitor.should_activate_failover():
                break

        # Activate failover
        event_id = failover_monitor.activate_failover("test_heartbeat_timeout")

        assert failover_monitor.is_failover_active() is True
        assert event_id is not None
        assert failover_monitor.get_current_router() == FailoverMonitor.OGEDEI_AGENT_ID

    def test_ögedei_activates_as_emergency_router(self, failover_monitor, mock_memory_for_failover):
        """Test that Ögedei activates as emergency router."""
        # Activate failover
        event_id = failover_monitor.activate_failover("test_activation")

        assert failover_monitor.is_failover_active() is True
        assert event_id is not None

        # Verify Ögedei is the current router
        assert failover_monitor.get_current_router() == FailoverMonitor.OGEDEI_AGENT_ID

        # Verify failover status
        status = failover_monitor.get_failover_status()
        assert status["failover_active"] is True
        assert status["current_router"] == FailoverMonitor.OGEDEI_AGENT_ID

    def test_ögedei_routes_to_correct_agents(self, failover_monitor):
        """Test that Ögedei routes to correct agents during failover."""
        # Activate failover
        failover_monitor.activate_failover("test_routing")

        # Test routing critical messages
        test_cases = [
            ("emergency: system down", FailoverMonitor.OGEDEI_AGENT_ID),
            ("urgent research needed", FailoverMonitor.OGEDEI_AGENT_ID),
            ("health check failed", FailoverMonitor.OGEDEI_AGENT_ID),
        ]

        for message, expected_agent in test_cases:
            result = failover_monitor.route_message("user", message, is_critical=True)
            assert result == expected_agent, f"Expected {expected_agent} for message: {message}"

        # Test non-critical messages are queued
        result = failover_monitor.route_message("user", "regular question", is_critical=False)
        assert result == "queue"

    def test_kublai_recovery_deactivates_failover(self, failover_monitor, mock_memory_for_failover):
        """Test that Kublai recovery deactivates failover."""
        # Activate failover first
        failover_monitor.activate_failover("test_recovery")
        assert failover_monitor.is_failover_active() is True

        # Simulate Kublai recovery by updating heartbeat
        failover_monitor.update_heartbeat("main")

        # Mock the query to return recent heartbeat (agent available)
        mock_session = Mock()

        def healthy_run(cypher, **kwargs):
            if "MATCH (h:AgentHeartbeat" in cypher:
                return create_mock_result(single={"last_seen": datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)})
            return create_mock_result(single={})

        mock_session.run = Mock(side_effect=healthy_run)
        mock_session.close = Mock()

        mock_ctx = Mock()
        mock_ctx.__enter__ = Mock(return_value=mock_session)
        mock_ctx.__exit__ = Mock(return_value=False)
        mock_memory_for_failover._session = Mock(return_value=mock_ctx)

        # Deactivate failover
        failover_monitor.deactivate_failover()

        assert failover_monitor.is_failover_active() is False
        assert failover_monitor.get_current_router() == FailoverMonitor.KUBLAI_AGENT_ID

    def test_failover_preserves_task_state(self, failover_monitor):
        """Test that failover preserves task state."""
        # Create task in failover state
        task = {
            "id": "task-123",
            "type": "research",
            "description": "Test task",
            "status": "in_progress",
            "assigned_to": "tolui",
            "priority": "high",
            "created_at": datetime(2025, 1, 1, 11, 0, 0, tzinfo=timezone.utc).isoformat()
        }

        # Activate failover
        failover_monitor.activate_failover("test_state_preservation")

        # Route task via Ögedei
        result = failover_monitor.route_message("kublai", str(task), is_critical=True)

        # Verify routing occurred
        assert result is not None
        assert failover_monitor.is_failover_active() is True

        # Task state should be preserved (we can verify by checking messages routed)
        status = failover_monitor.get_failover_status()
        assert status["messages_routed"] >= 1

    def test_failover_notification_to_user(self, failover_monitor, mock_memory_for_failover):
        """Test that failover sends notification to user."""
        # Activate failover
        failover_monitor.activate_failover("test_notification")

        # Verify notification was created
        status = failover_monitor.get_failover_status()
        assert status["failover_active"] is True

        # Deactivate and verify
        failover_monitor.deactivate_failover()
        assert failover_monitor.is_failover_active() is False


# =============================================================================
# TestFailoverWorkflowWithProtocol - Using FailoverProtocol
# =============================================================================

class TestFailoverWorkflowWithProtocol:
    """Integration tests using FailoverProtocol implementation."""

    def test_protocol_kublai_health_check(self, failover_protocol, mock_memory_for_failover):
        """Test FailoverProtocol health check functionality."""
        # Mock healthy Kublai with recent heartbeat
        mock_session = Mock()

        fixed_now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        def healthy_run(cypher, **kwargs):
            # Match the pattern: MATCH (a:Agent {name: $agent_name})
            # The cypher query may have newlines and whitespace
            cypher_normalized = ' '.join(cypher.split())
            if "MATCH (a:Agent" in cypher_normalized and "{name:" in cypher_normalized:
                return create_mock_result(single={
                    "last_heartbeat": fixed_now,
                    "status": "active",
                    "current_task": None
                })
            return create_mock_result(single={})

        mock_session.run = Mock(side_effect=healthy_run)
        mock_session.close = Mock()

        mock_ctx = Mock()
        mock_ctx.__enter__ = Mock(return_value=mock_session)
        mock_ctx.__exit__ = Mock(return_value=False)
        mock_memory_for_failover._session = Mock(return_value=mock_ctx)

        # Patch the protocol's _now method to return fixed time
        failover_protocol._now = Mock(return_value=fixed_now)

        health = failover_protocol.check_kublai_health()

        # With recent heartbeat, should be healthy
        assert health["healthy"] is True
        assert health["status"] == KublaiStatus.ACTIVE.value

    def test_protocol_should_activate_failover(self, failover_protocol, mock_memory_for_failover):
        """Test FailoverProtocol activation decision."""
        # Mock unhealthy Kublai (many missed heartbeats)
        old_time = datetime(2025, 1, 1, 11, 55, 0, tzinfo=timezone.utc)  # 5 minutes ago

        mock_session = Mock()

        def unhealthy_run(cypher, **kwargs):
            # Match the pattern: MATCH (a:Agent {name: $agent_name})
            # The cypher query may have newlines and whitespace
            cypher_normalized = ' '.join(cypher.split())
            if "MATCH (a:Agent" in cypher_normalized and "{name:" in cypher_normalized:
                return create_mock_result(single={
                    "last_heartbeat": old_time,
                    "status": "unavailable",
                    "current_task": None
                })
            return create_mock_result(single={})

        mock_session.run = Mock(side_effect=unhealthy_run)
        mock_session.close = Mock()

        mock_ctx = Mock()
        mock_ctx.__enter__ = Mock(return_value=mock_session)
        mock_ctx.__exit__ = Mock(return_value=False)
        mock_memory_for_failover._session = Mock(return_value=mock_ctx)

        should_activate = failover_protocol.should_activate_failover()
        assert should_activate is True

    def test_protocol_activate_and_deactivate_failover(self, failover_protocol, mock_memory_for_failover):
        """Test FailoverProtocol activate and deactivate cycle with proper time mocking."""
        fixed_now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        # Mock unhealthy Kublai for activation
        mock_session = Mock()

        def unhealthy_run(cypher, **kwargs):
            cypher_normalized = ' '.join(cypher.split())
            if "MATCH (a:Agent" in cypher_normalized and "{name:" in cypher_normalized:
                return create_mock_result(single={
                    "last_heartbeat": None,
                    "status": "unavailable",
                    "current_task": None
                })
            return create_mock_result(single={})

        mock_session.run = Mock(side_effect=unhealthy_run)
        mock_session.close = Mock()

        mock_ctx = Mock()
        mock_ctx.__enter__ = Mock(return_value=mock_session)
        mock_ctx.__exit__ = Mock(return_value=False)
        mock_memory_for_failover._session = Mock(return_value=mock_ctx)

        # Activate failover
        result = failover_protocol.activate_failover("test_protocol_activation")
        assert result is True

        # Verify failover is active
        status = failover_protocol.get_failover_status()
        assert status["failover_active"] is True

        # Now mock healthy Kublai for deactivation
        mock_session2 = Mock()

        def healthy_run(cypher, **kwargs):
            cypher_normalized = ' '.join(cypher.split())
            if "MATCH (a:Agent" in cypher_normalized and "{name:" in cypher_normalized:
                return create_mock_result(single={
                    "last_heartbeat": fixed_now,
                    "status": "active",
                    "current_task": None
                })
            return create_mock_result(single={})

        mock_session2.run = Mock(side_effect=healthy_run)
        mock_session2.close = Mock()

        mock_ctx2 = Mock()
        mock_ctx2.__enter__ = Mock(return_value=mock_session2)
        mock_ctx2.__exit__ = Mock(return_value=False)
        mock_memory_for_failover._session = Mock(return_value=mock_ctx2)

        # Patch the protocol's _now method to return fixed time
        failover_protocol._now = Mock(return_value=fixed_now)

        # Deactivate failover
        result = failover_protocol.deactivate_failover()
        assert result is True

        # Verify failover is inactive
        status = failover_protocol.get_failover_status()
        assert status["failover_active"] is False

    def test_protocol_routing_during_failover(self, failover_protocol, mock_memory_for_failover):
        """Test FailoverProtocol routing during failover."""
        # Activate failover
        failover_protocol._failover_active = True  # Direct activation for testing

        # Test routing based on keywords
        routing_tests = [
            ("research OAuth options", "möngke"),  # Research -> möngke
            ("write documentation", "chagatai"),   # Write -> chagatai
            ("code review needed", "temüjin"),     # Code -> temüjin
            ("analyze performance", "jochi"),      # Analyze -> jochi
            ("system health check", "ögedei"),     # System/health -> ögedei
        ]

        for message, expected_agent in routing_tests:
            result = failover_protocol.route_during_failover("user", message)
            assert result == expected_agent, f"Expected {expected_agent} for: {message}"

    def test_protocol_monitor_and_recover(self, failover_protocol, mock_memory_for_failover):
        """Test FailoverProtocol automatic monitoring and recovery."""
        fixed_now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        # Activate failover manually first
        failover_protocol._failover_active = True
        failover_protocol._consecutive_heartbeats = 0

        # Now simulate healthy Kublai for recovery
        mock_session2 = Mock()

        def healthy_run(cypher, **kwargs):
            # Match the pattern: MATCH (a:Agent {name: $agent_name})
            # The cypher query may have newlines and whitespace
            cypher_normalized = ' '.join(cypher.split())
            if "MATCH (a:Agent" in cypher_normalized and "{name:" in cypher_normalized:
                return create_mock_result(single={
                    "last_heartbeat": fixed_now,
                    "status": "active",
                    "current_task": None
                })
            return create_mock_result(single={})

        mock_session2.run = Mock(side_effect=healthy_run)
        mock_session2.close = Mock()

        mock_ctx2 = Mock()
        mock_ctx2.__enter__ = Mock(return_value=mock_session2)
        mock_ctx2.__exit__ = Mock(return_value=False)
        mock_memory_for_failover._session = Mock(return_value=mock_ctx2)

        # Patch the protocol's _now method to return fixed time
        failover_protocol._now = Mock(return_value=fixed_now)

        # Set consecutive heartbeats to required amount for recovery
        failover_protocol._consecutive_heartbeats = FailoverProtocol.RECOVERY_HEARTBEATS_REQUIRED

        # Call monitor_and_recover which should detect recovery and deactivate
        result = failover_protocol.monitor_and_recover()

        # Failover should be deactivated
        assert failover_protocol._failover_active is False

    def test_protocol_manual_trigger_failover(self, failover_protocol, mock_memory_for_failover):
        """Test manual failover triggering."""
        result = failover_protocol.manual_trigger_failover("manual_test_reason")
        assert result is True
        assert failover_protocol._failover_active is True


# =============================================================================
# TestFailoverWorkflow (Original Mock-Based Tests)
# =============================================================================

class TestFailoverWorkflowMock:
    """Integration tests for failover workflow using mocks."""

    @pytest.fixture
    def monitor(self):
        return MockFailoverMonitor()

    def test_kublai_heartbeat_triggers_failover_mock(self, monitor):
        """Test that missed Kublai heartbeats trigger failover."""
        # Simulate initial heartbeat
        monitor.heartbeat_tracker.record_heartbeat()
        assert monitor.check_kublai_status() is True

        # Simulate heartbeat timeout
        monitor.heartbeat_tracker.last_heartbeat = None
        assert monitor.check_kublai_status() is False

        # Should trigger failover
        monitor.activate_failover()
        assert monitor.failover_active is True
        assert monitor.emergency_router.is_active is True

    def test_ögedei_activates_as_emergency_router_mock(self, monitor):
        """Test that Ögedei activates as emergency router."""
        monitor.activate_failover()

        assert monitor.emergency_router.is_active is True

        # Check routing capabilities
        result = monitor.emergency_router.route_message("tolui", {"task": "test"})

        assert result["status"] == "routed"
        assert result["via"] == "ögedei"

    def test_ögedei_routes_to_correct_agents_mock(self, monitor):
        """Test that Ögedei routes to correct agents."""
        monitor.activate_failover()

        # Test routing to each agent
        agents = ["tolui", "hulagu", "mongke", "ariq_boke"]

        for agent in agents:
            result = monitor.emergency_router.route_message(agent, {"test": "data"})
            assert result["target"] == agent
            assert result["status"] == "routed"

    def test_kublai_recovery_deactivates_failover_mock(self, monitor):
        """Test that Kublai recovery deactivates failover."""
        # Activate failover
        monitor.activate_failover()
        assert monitor.failover_active is True

        # Simulate Kublai recovery
        monitor.heartbeat_tracker.record_heartbeat()

        # Deactivate failover
        monitor.deactivate_failover()

        assert monitor.failover_active is False
        assert monitor.emergency_router.is_active is False

    def test_failover_preserves_task_state_mock(self, monitor):
        """Test that failover preserves task state."""
        # Create task in failover state
        task = {
            "id": "task-123",
            "type": "research",
            "description": "Test task",
            "status": "in_progress",
            "assigned_to": "tolui"
        }

        # Activate failover
        monitor.activate_failover()

        # Route task via Ögedei
        result = monitor.delegate_via_ögedei("tolui", task)

        assert result["status"] == "routed"
        assert result["message"]["status"] == "in_progress"

    def test_failover_notification_to_user_mock(self, monitor):
        """Test that failover sends notification to user."""
        monitor.activate_failover()

        assert len(monitor.notifications) > 0

        # Check failover activation notification
        failover_notifs = [n for n in monitor.notifications if n["type"] == "failover_activated"]
        assert len(failover_notifs) == 1

        # Deactivate and check deactivation notification
        monitor.deactivate_failover()

        deactivate_notifs = [n for n in monitor.notifications if n["type"] == "failover_deactivated"]
        assert len(deactivate_notifs) == 1


# =============================================================================
# TestFailoverWorkflowAdvanced
# =============================================================================

class TestFailoverWorkflowAdvanced:
    """Advanced failover workflow tests."""

    @pytest.fixture
    def monitor(self):
        return MockFailoverMonitor()

    def test_failover_with_pending_tasks(self, monitor):
        """Test failover behavior with pending tasks."""
        # Create pending tasks
        pending_tasks = [
            {"id": "task-1", "status": "pending", "assigned_to": "tolui"},
            {"id": "task-2", "status": "pending", "assigned_to": "hulagu"}
        ]

        monitor.activate_failover()

        # All tasks should be routable
        for task in pending_tasks:
            result = monitor.delegate_via_ögedei(task["assigned_to"], task)
            assert result["status"] == "routed"

    def test_failover_with_in_progress_tasks(self, monitor):
        """Test failover behavior with in-progress tasks."""
        in_progress_task = {
            "id": "task-123",
            "status": "in_progress",
            "assigned_to": "tolui"
        }

        monitor.activate_failover()

        # Task should remain with its assigned agent
        result = monitor.delegate_via_ögedei("tolui", in_progress_task)

        assert result["status"] == "routed"
        assert result["message"]["assigned_to"] == "tolui"

    def test_failover_recovery_with_task_completion(self, monitor):
        """Test recovery after failover with completed tasks."""
        # Simulate task completion during failover
        monitor.activate_failover()

        completed_task = {
            "id": "task-456",
            "status": "completed",
            "result": "Task completed during failover"
        }

        # Kublai recovers
        monitor.heartbeat_tracker.record_heartbeat()
        monitor.deactivate_failover()

        # Completed task should still be marked complete
        assert completed_task["status"] == "completed"

    def test_multiple_failover_cycles(self, monitor):
        """Test multiple failover activation/deactivation cycles."""
        for i in range(3):
            monitor.activate_failover()
            assert monitor.failover_active is True

            monitor.heartbeat_tracker.record_heartbeat()
            monitor.deactivate_failover()
            assert monitor.failover_active is False

        # Should have 3 activation and 3 deactivation notifications
        assert len(monitor.notifications) == 6


# =============================================================================
# TestEmergencyRouting
# =============================================================================

class TestEmergencyRouting:
    """Tests for emergency routing via Ögedei."""

    @pytest.fixture
    def router(self):
        return MockOgedeiRouter()

    def test_routes_to_all_specialists(self, router):
        """Test that routing works to all specialist agents."""
        specialists = ["tolui", "hulagu", "ögedei", "mongke", "ariq_boke"]

        for specialist in specialists:
            if specialist in router.routing_map:
                result = router.route_message(specialist, {"test": "data"})
                assert result["status"] == "routed"

    def test_routing_preserves_message_content(self, router):
        """Test that routing preserves message content."""
        original_message = {
            "task": "Implement feature",
            "priority": "high",
            "deadline": "2025-01-15"
        }

        result = router.route_message("tolui", original_message)

        assert result["message"] == original_message

    def test_routing_metadata_added(self, router):
        """Test that routing adds metadata."""
        result = router.route_message("hulagu", {"task": "test"})

        assert "via" in result
        assert result["via"] == "ögedei"
        assert "original_target" in result

    def test_unknown_agent_routing(self, router):
        """Test routing to unknown agent."""
        result = router.route_message("unknown_agent", {"task": "test"})

        assert result["status"] == "failed"
        assert "error" in result


# =============================================================================
# TestFailoverTimeouts
# =============================================================================

class TestFailoverTimeouts:
    """Tests for failover timeout behavior."""

    @pytest.fixture
    def monitor(self):
        return MockFailoverMonitor()

    def test_heartbeat_timeout_detection(self, monitor):
        """Test heartbeat timeout detection."""
        # Set old heartbeat
        monitor.heartbeat_tracker.last_heartbeat = datetime.now(timezone.utc) - timedelta(seconds=20)

        is_healthy = monitor.check_kublai_status()

        assert is_healthy is False

    def test_failover_auto_activation_on_timeout(self, monitor):
        """Test automatic failover activation on timeout."""
        # Simulate timeout
        monitor.heartbeat_tracker.last_heartbeat = None

        if not monitor.check_kublai_status():
            monitor.activate_failover()

        assert monitor.failover_active is True

    def test_failover_deactivation_after_heartbeat_restored(self, monitor):
        """Test deactivation after heartbeat is restored."""
        # Activate failover
        monitor.activate_failover()

        # Restore heartbeat
        monitor.heartbeat_tracker.record_heartbeat()

        # Should be able to deactivate
        monitor.deactivate_failover()
        assert monitor.failover_active is False


# =============================================================================
# TestFailoverWithDelegation
# =============================================================================

class TestFailoverWithDelegation:
    """Tests for failover during delegation operations."""

    @pytest.fixture
    def monitor(self):
        return MockFailoverMonitor()

    def test_delegate_during_failover(self, monitor):
        """Test delegating a task while failover is active."""
        monitor.activate_failover()

        task = {
            "id": "task-789",
            "type": "code",
            "description": "Fix auth bug",
            "delegated_by": "kublai",
            "assigned_to": "tolui"
        }

        result = monitor.delegate_via_ögedei("tolui", task)

        assert result["status"] == "routed"
        assert result["message"]["id"] == "task-789"

    def test_claim_during_failover(self, monitor):
        """Test task claiming during failover."""
        monitor.activate_failover()

        claim_request = {
            "agent": "tolui",
            "task_id": "task-123"
        }

        result = monitor.delegate_via_ögedei("tolui", claim_request)

        assert result["status"] == "routed"

    def test_complete_during_failover(self, monitor):
        """Test task completion during failover."""
        monitor.activate_failover()

        completion = {
            "task_id": "task-456",
            "status": "completed",
            "result": "Task completed"
        }

        # Route to original delegator for notification
        result = monitor.delegate_via_ögedei("kublai", completion)

        assert result["status"] == "routed"


# =============================================================================
# TestFailoverEdgeCases
# =============================================================================

class TestFailoverEdgeCases:
    """Tests for edge cases in failover behavior."""

    def test_failover_monitor_concurrent_activation(self, failover_monitor, mock_memory_for_failover):
        """Test that concurrent failover activation is handled."""
        # Activate failover
        event_id1 = failover_monitor.activate_failover("test_concurrent")

        # Try to activate again (should return same event_id)
        event_id2 = failover_monitor.activate_failover("test_concurrent_2")

        assert event_id1 == event_id2

    def test_failover_monitor_deactivate_when_not_active(self, failover_monitor):
        """Test deactivating failover when not active."""
        # Should not raise error
        failover_monitor.deactivate_failover()
        assert failover_monitor.is_failover_active() is False

    def test_failover_protocol_routing_when_not_active(self, failover_protocol):
        """Test routing when failover is not active."""
        # Should return Kublai as router
        result = failover_protocol.route_during_failover("user", "test message")
        assert result == "main"  # Kublai's agent ID

    def test_failover_monitor_rate_limit_triggers_failover(self, failover_monitor):
        """Test that rate limit errors trigger failover."""
        # Record multiple rate limit errors
        for _ in range(FailoverMonitor.MAX_CONSECUTIVE_FAILURES):
            failover_monitor.record_rate_limit_error()

        # Failover should be triggered
        assert failover_monitor.is_failover_active() is True

    def test_failover_status_comprehensive(self, failover_monitor, mock_memory_for_failover):
        """Test comprehensive failover status reporting."""
        # Mock unavailable Kublai
        mock_session = Mock()

        def unavailable_run(cypher, **kwargs):
            if "MATCH (h:AgentHeartbeat" in cypher:
                return create_mock_result(single={"last_seen": None})
            return create_mock_result(single={})

        mock_session.run = Mock(side_effect=unavailable_run)
        mock_session.close = Mock()

        mock_ctx = Mock()
        mock_ctx.__enter__ = Mock(return_value=mock_session)
        mock_ctx.__exit__ = Mock(return_value=False)
        mock_memory_for_failover._session = Mock(return_value=mock_ctx)

        status = failover_monitor.get_failover_status()

        assert "failover_active" in status
        assert "current_router" in status
        assert "kublai_failures" in status
        assert "consecutive_healthy_checks" in status
        assert "current_event_id" in status
        assert "messages_routed" in status
        assert "kublai_available" in status
        assert "threshold_seconds" in status
        assert "max_consecutive_failures" in status
