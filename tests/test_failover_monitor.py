"""
Tests for FailoverMonitor class.

This module contains comprehensive tests for the failover monitoring system
including heartbeat tracking, failover activation/deactivation, and routing.
"""

import pytest
import threading
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, MagicMock, patch, call

# Import the module under test
import sys
sys.path.insert(0, '/Users/kurultai/molt')

from tools.failover_monitor import (
    FailoverMonitor,
    FailoverError,
    create_failover_monitor,
)


class TestFailoverMonitor:
    """Test cases for FailoverMonitor class."""

    @pytest.fixture
    def mock_memory(self):
        """Create a mock OperationalMemory."""
        memory = Mock()
        memory._generate_id.return_value = "test-failover-id"
        memory._now.return_value = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        # Mock session context manager
        mock_session = Mock()
        mock_context = MagicMock()
        mock_context.__enter__ = Mock(return_value=mock_session)
        mock_context.__exit__ = Mock(return_value=False)
        memory._session.return_value = mock_context

        return memory, mock_session

    @pytest.fixture
    def failover_monitor(self, mock_memory):
        """Create a FailoverMonitor instance with mocked dependencies."""
        memory, _ = mock_memory
        return FailoverMonitor(memory, check_interval_seconds=1)

    def test_initialization(self, mock_memory):
        """Test that FailoverMonitor initializes correctly."""
        memory, _ = mock_memory
        fm = FailoverMonitor(memory, check_interval_seconds=45)

        assert fm.memory == memory
        assert fm.check_interval == 45
        assert fm._kublai_failures == 0
        assert fm._failover_active is False
        assert fm._current_failover_event_id is None

    def test_generate_id(self, failover_monitor):
        """Test ID generation using memory's method."""
        assert failover_monitor._generate_id() == "test-failover-id"

    def test_generate_id_fallback(self):
        """Test ID generation fallback when memory lacks _generate_id."""
        memory = Mock(spec=[])  # No _generate_id method
        fm = FailoverMonitor(memory)

        generated_id = fm._generate_id()
        assert generated_id is not None
        assert isinstance(generated_id, str)
        assert len(generated_id) > 0

    def test_now(self, failover_monitor):
        """Test datetime generation using memory's method."""
        now = failover_monitor._now()
        assert now == datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    def test_update_heartbeat_success(self, mock_memory):
        """Test successful heartbeat update."""
        memory, mock_session = mock_memory

        # Mock the session run result
        mock_result = Mock()
        mock_result.single.return_value = {"agent": "main"}
        mock_session.run.return_value = mock_result

        fm = FailoverMonitor(memory)
        fm.update_heartbeat("main")

        mock_session.run.assert_called_once()

        # Verify the cypher query was called with correct parameters
        call_args = mock_session.run.call_args
        assert call_args[1]["agent"] == "main"

    def test_update_heartbeat_fallback_mode(self, mock_memory):
        """Test heartbeat update in fallback mode."""
        memory, mock_session = mock_memory

        # Set session to None for fallback mode
        mock_context = MagicMock()
        mock_context.__enter__ = Mock(return_value=None)
        mock_context.__exit__ = Mock(return_value=False)
        memory._session.return_value = mock_context

        fm = FailoverMonitor(memory)
        # Should not raise exception
        fm.update_heartbeat("main")

    def test_is_agent_available_true(self, mock_memory):
        """Test agent availability check returns True when heartbeat is recent."""
        memory, mock_session = mock_memory

        recent_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_result = Mock()
        mock_result.single.return_value = {"last_seen": recent_time}
        mock_session.run.return_value = mock_result

        fm = FailoverMonitor(memory)
        available = fm.is_agent_available("main")

        assert available is True

    def test_is_agent_available_false_stale(self, mock_memory):
        """Test agent availability check returns False when heartbeat is stale."""
        memory, mock_session = mock_memory

        # Heartbeat from 2 minutes ago (beyond 60 second threshold)
        stale_time = datetime(2025, 1, 1, 11, 58, 0, tzinfo=timezone.utc)
        mock_result = Mock()
        mock_result.single.return_value = {"last_seen": stale_time}
        mock_session.run.return_value = mock_result

        fm = FailoverMonitor(memory)
        available = fm.is_agent_available("main")

        assert available is False

    def test_is_agent_available_no_heartbeat(self, mock_memory):
        """Test agent availability check returns False when no heartbeat exists."""
        memory, mock_session = mock_memory

        mock_result = Mock()
        mock_result.single.return_value = None
        mock_session.run.return_value = mock_result

        fm = FailoverMonitor(memory)
        available = fm.is_agent_available("main")

        assert available is False

    def test_is_agent_available_fallback_mode(self, mock_memory):
        """Test agent availability check in fallback mode."""
        memory, mock_session = mock_memory

        mock_context = MagicMock()
        mock_context.__enter__ = Mock(return_value=None)
        mock_context.__exit__ = Mock(return_value=False)
        memory._session.return_value = mock_context

        fm = FailoverMonitor(memory)
        available = fm.is_agent_available("main")

        # In fallback mode, assume agent is available
        assert available is True

    def test_should_activate_failover_false(self, mock_memory):
        """Test should_activate_failover returns False when Kublai is healthy."""
        memory, mock_session = mock_memory

        recent_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_result = Mock()
        mock_result.single.return_value = {"last_seen": recent_time}
        mock_session.run.return_value = mock_result

        fm = FailoverMonitor(memory)
        should_failover = fm.should_activate_failover()

        assert should_failover is False

    def test_should_activate_failover_true(self, mock_memory):
        """Test should_activate_failover returns True after threshold failures."""
        memory, mock_session = mock_memory

        stale_time = datetime(2025, 1, 1, 11, 58, 0, tzinfo=timezone.utc)
        mock_result = Mock()
        mock_result.single.return_value = {"last_seen": stale_time}
        mock_session.run.return_value = mock_result

        fm = FailoverMonitor(memory)

        # First check - increments failures to 1
        fm.should_activate_failover()
        assert fm._kublai_failures == 1

        # Second check - increments failures to 2
        fm.should_activate_failover()
        assert fm._kublai_failures == 2

        # Third check - increments failures to 3, should activate
        should_failover = fm.should_activate_failover()
        assert fm._kublai_failures == 3
        assert should_failover is True

    def test_should_activate_failover_already_active(self, mock_memory):
        """Test should_activate_failover returns False when already active."""
        memory, mock_session = mock_memory

        stale_time = datetime(2025, 1, 1, 11, 58, 0, tzinfo=timezone.utc)
        mock_result = Mock()
        mock_result.single.return_value = {"last_seen": stale_time}
        mock_session.run.return_value = mock_result

        fm = FailoverMonitor(memory)

        # Activate failover
        with fm._state_lock:
            fm._failover_active = True

        # Should not reactivate
        should_failover = fm.should_activate_failover()
        assert should_failover is False

    def test_activate_failover_success(self, mock_memory):
        """Test successful failover activation."""
        memory, mock_session = mock_memory

        # Mock create event result
        mock_results = [
            Mock(single=Mock(return_value={"event_id": "test-event-id"})),
            Mock(),  # For _update_ogedei_role
            Mock(),  # For _create_failover_notification
        ]
        mock_session.run.side_effect = mock_results

        fm = FailoverMonitor(memory)
        event_id = fm.activate_failover("test_reason")

        assert event_id == "test-event-id"
        assert fm._failover_active is True
        assert fm._current_failover_event_id == "test-event-id"

    def test_activate_failover_already_active(self, mock_memory):
        """Test activate_failover when already active."""
        memory, mock_session = mock_memory

        # Set failover as already active
        memory._generate_id.return_value = "existing-event-id"

        fm = FailoverMonitor(memory)
        with fm._state_lock:
            fm._failover_active = True
            fm._current_failover_event_id = "existing-event-id"

        event_id = fm.activate_failover("test_reason")

        # Should return existing event ID
        assert event_id == "existing-event-id"
        assert fm._failover_active is True

    def test_activate_failover_fallback_mode(self, mock_memory):
        """Test failover activation in fallback mode."""
        memory, mock_session = mock_memory

        mock_context = MagicMock()
        mock_context.__enter__ = Mock(return_value=None)
        mock_context.__exit__ = Mock(return_value=False)
        memory._session.return_value = mock_context

        fm = FailoverMonitor(memory)
        event_id = fm.activate_failover("test_reason")

        assert event_id == "test-failover-id"
        assert fm._failover_active is True

    def test_deactivate_failover_success(self, mock_memory):
        """Test successful failover deactivation."""
        memory, mock_session = mock_memory

        # Setup: activate failover first
        memory._generate_id.return_value = "test-event-id"
        mock_session.run.return_value = Mock(single=Mock(return_value={"event_id": "test-event-id"}))

        fm = FailoverMonitor(memory)
        fm.activate_failover("test_reason")
        fm._messages_routed_during_failover = 42

        # Now deactivate
        mock_session.run.reset_mock()
        mock_session.run.return_value = Mock(single=Mock(return_value={"event_id": "test-event-id"}))

        fm.deactivate_failover()

        assert fm._failover_active is False
        assert fm._current_failover_event_id is None
        assert fm._messages_routed_during_failover == 0

    def test_deactivate_failover_not_active(self, mock_memory):
        """Test deactivate_failover when not active."""
        memory, _ = mock_memory

        fm = FailoverMonitor(memory)
        # Should not raise exception
        fm.deactivate_failover()

        assert fm._failover_active is False

    def test_is_failover_active(self, mock_memory):
        """Test is_failover_active method."""
        memory, _ = mock_memory

        fm = FailoverMonitor(memory)

        assert fm.is_failover_active() is False

        with fm._state_lock:
            fm._failover_active = True

        assert fm.is_failover_active() is True

    def test_get_current_router_kublai(self, mock_memory):
        """Test get_current_router returns Kublai when failover inactive."""
        memory, _ = mock_memory

        fm = FailoverMonitor(memory)
        router = fm.get_current_router()

        assert router == "main"  # KUBLAI_AGENT_ID

    def test_get_current_router_ogedei(self, mock_memory):
        """Test get_current_router returns Ögedei when failover active."""
        memory, _ = mock_memory

        fm = FailoverMonitor(memory)

        with fm._state_lock:
            fm._failover_active = True

        router = fm.get_current_router()

        assert router == "ops"  # OGEDEI_AGENT_ID

    def test_get_failover_status(self, mock_memory):
        """Test get_failover_status returns comprehensive status."""
        memory, mock_session = mock_memory

        recent_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_result = Mock()
        mock_result.single.return_value = {"last_seen": recent_time}
        mock_session.run.return_value = mock_result

        fm = FailoverMonitor(memory)

        with fm._state_lock:
            fm._kublai_failures = 2
            fm._consecutive_healthy_checks = 1
            fm._messages_routed_during_failover = 5

        status = fm.get_failover_status()

        assert status["failover_active"] is False
        assert status["current_router"] == "main"
        assert status["kublai_failures"] == 2
        assert status["consecutive_healthy_checks"] == 1
        assert status["messages_routed"] == 5
        assert status["kublai_available"] is True
        assert status["threshold_seconds"] == 60
        assert status["max_consecutive_failures"] == 3

    def test_record_rate_limit_error(self, mock_memory):
        """Test recording rate limit error."""
        memory, _ = mock_memory

        fm = FailoverMonitor(memory)
        fm.record_rate_limit_error()

        assert fm._kublai_failures == 1

    def test_record_rate_limit_error_triggers_failover(self, mock_memory):
        """Test rate limit error triggers failover after threshold."""
        memory, mock_session = mock_memory

        # Mock failover activation
        mock_session.run.return_value = Mock(single=Mock(return_value={"event_id": "test-event"}))

        fm = FailoverMonitor(memory)

        # Record 2 rate limit errors
        fm.record_rate_limit_error()
        fm.record_rate_limit_error()

        assert fm._kublai_failures == 2
        assert fm._failover_active is False

        # Third error should trigger failover
        fm.record_rate_limit_error()

        assert fm._kublai_failures == 3
        assert fm._failover_active is True

    def test_route_message_normal_mode(self, mock_memory):
        """Test route_message returns Kublai when failover inactive."""
        memory, _ = mock_memory

        fm = FailoverMonitor(memory)
        target = fm.route_message("user", "test message", is_critical=True)

        assert target == "main"

    def test_route_message_failover_critical(self, mock_memory):
        """Test route_message routes critical messages during failover."""
        memory, _ = mock_memory

        fm = FailoverMonitor(memory)

        with fm._state_lock:
            fm._failover_active = True

        target = fm.route_message("user", "emergency help needed", is_critical=True)

        # Should route to Ögedei for emergency
        assert target == "ops"
        assert fm._messages_routed_during_failover == 1

    def test_route_message_failover_non_critical(self, mock_memory):
        """Test route_message queues non-critical messages during failover."""
        memory, _ = mock_memory

        fm = FailoverMonitor(memory)

        with fm._state_lock:
            fm._failover_active = True

        target = fm.route_message("user", "can you help with this", is_critical=False)

        assert target == "queue"
        assert fm._messages_routed_during_failover == 1

    def test_route_message_with_keyword(self, mock_memory):
        """Test route_message routes based on keywords."""
        memory, _ = mock_memory

        fm = FailoverMonitor(memory)

        with fm._state_lock:
            fm._failover_active = True

        # Test "health" keyword
        target = fm.route_message("user", "system health check", is_critical=True)
        assert target == "ops"

        # Test "urgent" keyword
        target = fm.route_message("user", "urgent issue", is_critical=True)
        assert target == "ops"

    def test_start_monitoring(self, mock_memory):
        """Test starting background monitoring."""
        memory, _ = mock_memory

        fm = FailoverMonitor(memory)
        fm.start_monitoring()

        assert fm._monitor_thread is not None
        assert fm._monitor_thread.is_alive()

        # Stop monitoring to clean up
        fm.stop_monitoring()

    def test_start_monitoring_already_running(self, mock_memory):
        """Test start_monitoring when already running."""
        memory, _ = mock_memory

        fm = FailoverMonitor(memory)
        fm.start_monitoring()

        first_thread = fm._monitor_thread

        # Should not create new thread
        fm.start_monitoring()

        assert fm._monitor_thread == first_thread

        fm.stop_monitoring()

    def test_stop_monitoring(self, mock_memory):
        """Test stopping background monitoring."""
        memory, _ = mock_memory

        fm = FailoverMonitor(memory)
        fm.start_monitoring()

        assert fm._monitor_thread is not None

        fm.stop_monitoring()

        assert fm._stop_monitoring.is_set()

    def test_check_kublai_health_healthy(self, mock_memory):
        """Test _check_kublai_health when Kublai is healthy."""
        memory, mock_session = mock_memory

        recent_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_result = Mock()
        mock_result.single.return_value = {"last_seen": recent_time}
        mock_session.run.return_value = mock_result

        fm = FailoverMonitor(memory)
        fm._check_kublai_health()

        assert fm._consecutive_healthy_checks == 1
        assert fm._kublai_failures == 0

    def test_check_kublai_health_unavailable(self, mock_memory):
        """Test _check_kublai_health when Kublai is unavailable."""
        memory, mock_session = mock_memory

        stale_time = datetime(2025, 1, 1, 11, 58, 0, tzinfo=timezone.utc)
        mock_result = Mock()
        mock_result.single.return_value = {"last_seen": stale_time}
        mock_session.run.return_value = mock_result

        fm = FailoverMonitor(memory)

        # Mock failover activation
        mock_session.run.return_value = Mock(single=Mock(return_value={"event_id": "test-event"}))

        fm._check_kublai_health()

        assert fm._kublai_failures == 1

    def test_failback_after_recovery(self, mock_memory):
        """Test failback after Kublai recovers."""
        memory, mock_session = mock_memory

        # Activate failover first
        mock_session.run.return_value = Mock(single=Mock(return_value={"event_id": "test-event"}))
        memory._generate_id.return_value = "test-event-id"

        fm = FailoverMonitor(memory)
        fm.activate_failover("test_reason")

        # Reset mock for health check
        recent_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_result = Mock()
        mock_result.single.return_value = {"last_seen": recent_time}
        mock_session.run.return_value = mock_result

        # Simulate multiple healthy checks to trigger failback
        for _ in range(fm.RECOVERY_HEARTBEATS_REQUIRED):
            fm._check_kublai_health()

        assert fm._failover_active is False

    def test_update_ogedei_role_emergency(self, mock_memory):
        """Test _update_ogedei_role sets emergency mode."""
        memory, mock_session = mock_memory

        fm = FailoverMonitor(memory)
        fm._update_ogedei_role(emergency_mode=True)

        mock_session.run.assert_called_once()

        call_args = mock_session.run.call_args
        assert "Emergency Router" in call_args[0][0]
        assert call_args[1]["agent_id"] == "ops"

    def test_update_ogedei_role_normal(self, mock_memory):
        """Test _update_ogedei_role restores normal role."""
        memory, mock_session = mock_memory

        fm = FailoverMonitor(memory)
        fm._update_ogedei_role(emergency_mode=False)

        mock_session.run.assert_called_once()

        call_args = mock_session.run.call_args
        assert "REMOVE" in call_args[0][0]
        assert call_args[1]["agent_id"] == "ops"

    def test_create_failover_notification(self, mock_memory):
        """Test _create_failover_notification creates notification."""
        memory, mock_session = mock_memory

        fm = FailoverMonitor(memory)
        fm._create_failover_notification("activated", "test reason")

        mock_session.run.assert_called_once()

        call_args = mock_session.run.call_args
        assert call_args[1]["type"] == "failover_activated"
        assert call_args[1]["summary"] == "test reason"

    def test_get_failover_history(self, mock_memory):
        """Test get_failover_history returns events."""
        memory, mock_session = mock_memory

        mock_result = Mock()
        mock_result.__iter__ = Mock(return_value=iter([
            {
                "id": "event-1",
                "activated_at": datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                "deactivated_at": None,
                "reason": "test",
                "duration_seconds": None,
                "messages_queued": 0,
                "is_active": True,
                "triggered_by": "auto",
            }
        ]))
        mock_session.run.return_value = mock_result

        fm = FailoverMonitor(memory)
        history = fm.get_failover_history(limit=10)

        assert len(history) == 1
        assert history[0]["id"] == "event-1"
        assert history[0]["is_active"] is True

    def test_get_failover_history_fallback_mode(self, mock_memory):
        """Test get_failover_history in fallback mode."""
        memory, mock_session = mock_memory

        mock_context = MagicMock()
        mock_context.__enter__ = Mock(return_value=None)
        mock_context.__exit__ = Mock(return_value=False)
        memory._session.return_value = mock_context

        fm = FailoverMonitor(memory)
        history = fm.get_failover_history()

        assert history == []

    def test_create_indexes(self, mock_memory):
        """Test creating indexes."""
        memory, mock_session = mock_memory

        fm = FailoverMonitor(memory)
        indexes = fm.create_indexes()

        assert len(indexes) == 4
        assert "agentheartbeat_agent_idx" in indexes
        assert "agentheartbeat_last_seen_idx" in indexes
        assert "failoverevent_is_active_idx" in indexes
        assert "failoverevent_activated_at_idx" in indexes

    def test_create_indexes_fallback_mode(self, mock_memory):
        """Test creating indexes in fallback mode."""
        memory, mock_session = mock_memory

        mock_context = MagicMock()
        mock_context.__enter__ = Mock(return_value=None)
        mock_context.__exit__ = Mock(return_value=False)
        memory._session.return_value = mock_context

        fm = FailoverMonitor(memory)
        indexes = fm.create_indexes()

        assert indexes == []

    def test_thread_safety_concurrent_heartbeat_updates(self, mock_memory):
        """Test concurrent heartbeat updates are thread-safe."""
        memory, mock_session = mock_memory

        mock_result = Mock()
        mock_result.single.return_value = {"agent": "main"}
        mock_session.run.return_value = mock_result

        fm = FailoverMonitor(memory)

        def update_heartbeat():
            for _ in range(10):
                fm.update_heartbeat("main")

        threads = [threading.Thread(target=update_heartbeat) for _ in range(5)]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # Should complete without errors
        assert True

    def test_thread_safety_concurrent_failover_checks(self, mock_memory):
        """Test concurrent failover checks are thread-safe."""
        memory, mock_session = mock_memory

        recent_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_result = Mock()
        mock_result.single.return_value = {"last_seen": recent_time}
        mock_session.run.return_value = mock_result

        fm = FailoverMonitor(memory)

        def check_failover():
            for _ in range(10):
                fm.should_activate_failover()

        threads = [threading.Thread(target=check_failover) for _ in range(5)]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # Should complete without errors and failover should not be active
        assert fm._failover_active is False


class TestConvenienceFunctions:
    """Test convenience functions."""

    @pytest.fixture
    def mock_memory(self):
        """Create a mock OperationalMemory."""
        memory = Mock()
        return memory

    def test_create_failover_monitor(self, mock_memory):
        """Test create_failover_monitor convenience function."""
        fm = create_failover_monitor(mock_memory, check_interval_seconds=60)

        assert isinstance(fm, FailoverMonitor)
        assert fm.check_interval == 60


class TestConstants:
    """Test class constants."""

    def test_constants_values(self):
        """Test that constants have expected values."""
        assert FailoverMonitor.FAILOVER_THRESHOLD_SECONDS == 60
        assert FailoverMonitor.MAX_CONSECUTIVE_FAILURES == 3
        assert FailoverMonitor.CHECK_INTERVAL_SECONDS == 30
        assert FailoverMonitor.RECOVERY_HEARTBEATS_REQUIRED == 3
        assert FailoverMonitor.KUBLAI_AGENT_ID == "main"
        assert FailoverMonitor.OGEDEI_AGENT_ID == "ops"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
