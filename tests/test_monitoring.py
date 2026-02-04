"""
Tests for Monitoring Module - Prometheus metrics and alerting.

This module contains comprehensive tests for the monitoring system including:
- PrometheusMetrics class
- AlertManager class
- Metrics and alerts functionality
- Thread safety and concurrent access
"""

import json
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from unittest.mock import Mock, MagicMock, patch, call, AsyncMock

import pytest

# Import the module under test
import sys
sys.path.insert(0, '/Users/kurultai/molt')

from tools.monitoring import (
    # Metric types
    Metric,
    Counter,
    Gauge,
    Histogram,
    MetricValue,
    MetricsRegistry,
    get_registry,

    # Main classes
    PrometheusMetrics,
    AlertManager,
    Alert,

    # Constants
    AGENT_ERROR_RATE_THRESHOLD,
    TASK_FAILURE_RATE_THRESHOLD,
    NEO4J_QUERY_DURATION_THRESHOLD,
    FAILOVER_THRESHOLD,
    QUEUE_DEPTH_THRESHOLD,

    # Convenience functions
    create_monitoring,
    start_monitoring,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def reset_registry():
    """Reset the global registry before each test."""
    registry = get_registry()
    registry.clear()
    yield registry
    registry.clear()


@pytest.fixture
def fresh_registry(reset_registry):
    """Create a fresh registry for isolated tests."""
    return MetricsRegistry()


@pytest.fixture
def prometheus_metrics(reset_registry):
    """Create a PrometheusMetrics instance for testing."""
    # Create a fresh registry for this test to avoid interference
    fresh_registry = MetricsRegistry()
    return PrometheusMetrics(port=0, host="localhost", registry=fresh_registry)


@pytest.fixture
def alert_manager():
    """Create an AlertManager instance for testing."""
    return AlertManager(webhook_url=None)


@pytest.fixture
def sample_metrics(prometheus_metrics):
    """Create a PrometheusMetrics instance with sample data."""
    # Set some baseline metrics
    prometheus_metrics.set_neo4j_status(1)
    prometheus_metrics.set_signal_status(1)
    prometheus_metrics.set_gateway_status("main", 1)

    # Add agent heartbeats
    prometheus_metrics.set_agent_heartbeat("main")
    prometheus_metrics.set_agent_heartbeat("research")
    prometheus_metrics.set_agent_heartbeat("write")
    prometheus_metrics.set_agent_heartbeat("dev")
    prometheus_metrics.set_agent_heartbeat("analyze")
    prometheus_metrics.set_agent_heartbeat("ops")

    # Add some tasks
    prometheus_metrics.inc_task_created("main", "research")
    prometheus_metrics.inc_task_completed("research", "research", 45.2)
    prometheus_metrics.set_agent_success_rate("research", 0.95)
    prometheus_metrics.set_agent_error_rate("research", 0.05)
    prometheus_metrics.set_queue_depth("research", 10)

    # Add memory stats
    prometheus_metrics.set_node_count("Task", 150)
    prometheus_metrics.set_relationship_count("HAS_TASK", 150)

    return prometheus_metrics


# =============================================================================
# Metric Tests
# =============================================================================

class TestMetric:
    """Test cases for the base Metric class."""

    def test_gauge_initialization(self, fresh_registry):
        """Test Gauge metric initialization."""
        gauge = Gauge("test_gauge", "A test gauge", registry=fresh_registry)
        assert gauge.name == "openclaw_test_gauge"
        assert gauge.help_text == "A test gauge"
        assert gauge.metric_type == "gauge"
        assert gauge.label_names == []

    def test_gauge_set(self, fresh_registry):
        """Test setting gauge values."""
        gauge = Gauge("test_gauge", registry=fresh_registry)
        gauge.set(42.0)
        assert gauge.get_value() == 42.0

    def test_gauge_set_with_labels(self, fresh_registry):
        """Test setting labeled gauge values."""
        gauge = Gauge("test_gauge", label_names=["agent", "status"], registry=fresh_registry)
        gauge.set(1.0, agent="main", status="healthy")
        assert gauge.get_value(agent="main", status="healthy") == 1.0

    def test_gauge_inc(self, fresh_registry):
        """Test incrementing gauge values."""
        gauge = Gauge("test_gauge", registry=fresh_registry)
        gauge.set(5.0)
        gauge.inc()
        assert gauge.get_value() == 6.0

    def test_gauge_inc_amount(self, fresh_registry):
        """Test incrementing gauge by specific amount."""
        gauge = Gauge("test_gauge", registry=fresh_registry)
        gauge.set(5.0)
        gauge.inc(3.5)
        assert gauge.get_value() == 8.5

    def test_gauge_dec(self, fresh_registry):
        """Test decrementing gauge values."""
        gauge = Gauge("test_gauge", registry=fresh_registry)
        gauge.set(10.0)
        gauge.dec()
        assert gauge.get_value() == 9.0

    def test_gauge_dec_amount(self, fresh_registry):
        """Test decrementing gauge by specific amount."""
        gauge = Gauge("test_gauge", registry=fresh_registry)
        gauge.set(10.0)
        gauge.dec(3.5)
        assert gauge.get_value() == 6.5

    def test_counter_initialization(self, fresh_registry):
        """Test Counter metric initialization."""
        counter = Counter("test_counter", "A test counter", registry=fresh_registry)
        assert counter.metric_type == "counter"

    def test_counter_inc(self, fresh_registry):
        """Test incrementing counter."""
        counter = Counter("test_counter", registry=fresh_registry)
        counter.inc()
        assert counter.get_value() == 1.0

    def test_counter_inc_multiple(self, fresh_registry):
        """Test incrementing counter multiple times."""
        counter = Counter("test_counter", registry=fresh_registry)
        counter.inc()
        counter.inc()
        counter.inc()
        assert counter.get_value() == 3.0

    def test_counter_inc_amount(self, fresh_registry):
        """Test incrementing counter by specific amount."""
        counter = Counter("test_counter", registry=fresh_registry)
        counter.inc(5)
        assert counter.get_value() == 5.0

    def test_counter_cannot_decrement(self, fresh_registry):
        """Test that counter cannot be decremented."""
        counter = Counter("test_counter", registry=fresh_registry)
        with pytest.raises(ValueError):
            counter.inc(-1)

    def test_histogram_initialization(self, fresh_registry):
        """Test Histogram metric initialization."""
        histogram = Histogram("test_histogram", "A test histogram", registry=fresh_registry)
        assert histogram.metric_type == "histogram"
        assert histogram.buckets == Histogram.DEFAULT_BUCKETS

    def test_histogram_observe(self, fresh_registry):
        """Test observing values in histogram."""
        histogram = Histogram("test_histogram", registry=fresh_registry)
        histogram.observe(0.5)
        histogram.observe(1.5)
        histogram.observe(0.25)

        # Verify observations were recorded
        all_values = histogram.get_all_values()
        assert len(all_values) == 1
        assert all_values[0].value == 0.25  # Last observed value

    def test_histogram_custom_buckets(self, fresh_registry):
        """Test histogram with custom buckets."""
        custom_buckets = [0.1, 0.5, 1.0, 5.0]
        histogram = Histogram(
            "test_histogram",
            buckets=custom_buckets,
            registry=fresh_registry
        )
        assert histogram.buckets == custom_buckets

    def test_metric_export_prometheus(self, fresh_registry):
        """Test Prometheus format export."""
        gauge = Gauge("test_gauge", "Help text", registry=fresh_registry)
        gauge.set(42.0)

        exported = gauge.export_prometheus()
        assert "# HELP openclaw_test_gauge Help text" in exported
        assert "# TYPE openclaw_test_gauge gauge" in exported
        assert "openclaw_test_gauge 42" in exported

    def test_metric_export_with_labels(self, fresh_registry):
        """Test Prometheus format export with labels."""
        gauge = Gauge("test_gauge", label_names=["agent"], registry=fresh_registry)
        gauge.set(1.0, agent="main")
        gauge.set(0.0, agent="ops")

        exported = gauge.export_prometheus()
        assert 'openclaw_test_gauge{agent="main"} 1' in exported
        assert 'openclaw_test_gauge{agent="ops"} 0' in exported

    def test_histogram_export_prometheus(self, fresh_registry):
        """Test histogram Prometheus format export."""
        histogram = Histogram("test_histogram", "Test histogram", registry=fresh_registry)
        histogram.observe(0.5)
        histogram.observe(1.5)

        exported = histogram.export_prometheus()
        assert "# HELP openclaw_test_histogram Test histogram" in exported
        assert "# TYPE openclaw_test_histogram histogram" in exported
        assert "openclaw_test_histogram_count" in exported
        assert "openclaw_test_histogram_sum" in exported
        assert "openclaw_test_histogram_bucket" in exported


# =============================================================================
# MetricsRegistry Tests
# =============================================================================

class TestMetricsRegistry:
    """Test cases for the MetricsRegistry class."""

    def test_register_metric(self):
        """Test registering a metric."""
        registry = MetricsRegistry()
        gauge = Gauge("test_gauge", "Help text")

        registered = registry.register(gauge)
        assert registered is gauge

    def test_register_idempotent(self):
        """Test that registering the same metric twice returns the existing one."""
        registry = MetricsRegistry()
        gauge1 = Gauge("test_gauge", "Help text")
        gauge2 = Gauge("test_gauge", "Different help")

        registry.register(gauge1)
        registered = registry.register(gauge2)

        assert registered is gauge1

    def test_get_metric(self):
        """Test retrieving a metric by name."""
        registry = MetricsRegistry()
        gauge = Gauge("test_gauge", "Help text")
        registry.register(gauge)

        retrieved = registry.get_metric("openclaw_test_gauge")
        assert retrieved is gauge

    def test_get_metric_not_found(self):
        """Test retrieving a non-existent metric returns None."""
        registry = MetricsRegistry()
        retrieved = registry.get_metric("nonexistent")
        assert retrieved is None

    def test_get_all_metrics(self):
        """Test getting all registered metrics."""
        registry = MetricsRegistry()
        gauge1 = Gauge("test_gauge1")
        gauge2 = Gauge("test_gauge2")
        counter1 = Counter("test_counter1")

        registry.register(gauge1)
        registry.register(gauge2)
        registry.register(counter1)

        all_metrics = registry.get_all_metrics()
        assert len(all_metrics) == 3

    def test_unregister_metric(self):
        """Test unregistering a metric."""
        registry = MetricsRegistry()
        gauge = Gauge("test_gauge")
        registry.register(gauge)

        registry.unregister(gauge)
        assert registry.get_metric("openclaw_test_gauge") is None

    def test_export_metrics(self):
        """Test exporting all metrics."""
        registry = MetricsRegistry()
        gauge = Gauge("test_gauge", "Help text")
        gauge.set(42.0)
        registry.register(gauge)

        exported = registry.export()
        assert "# HELP openclaw_test_gauge Help text" in exported
        assert "openclaw_test_gauge 42" in exported

    def test_clear_metrics(self):
        """Test clearing all metrics."""
        registry = MetricsRegistry()
        gauge = Gauge("test_gauge")
        registry.register(gauge)

        registry.clear()
        assert len(registry.get_all_metrics()) == 0


# =============================================================================
# PrometheusMetrics Tests
# =============================================================================

class TestPrometheusMetrics:
    """Test cases for the PrometheusMetrics class."""

    def test_initialization(self):
        """Test PrometheusMetrics initialization."""
        metrics = PrometheusMetrics(port=9090, host="localhost")
        assert metrics.port == 9090
        assert metrics.host == "localhost"
        assert metrics.registry is not None

    def test_set_neo4j_status_connected(self, prometheus_metrics):
        """Test setting Neo4j status to connected."""
        prometheus_metrics.set_neo4j_status("connected")
        assert prometheus_metrics.neo4j_status.get_value() == 1

    def test_set_neo4j_status_disconnected(self, prometheus_metrics):
        """Test setting Neo4j status to disconnected."""
        prometheus_metrics.set_neo4j_status("disconnected")
        assert prometheus_metrics.neo4j_status.get_value() == 0

    def test_set_neo4j_status_boolean(self, prometheus_metrics):
        """Test setting Neo4j status with boolean."""
        prometheus_metrics.set_neo4j_status(True)
        assert prometheus_metrics.neo4j_status.get_value() == 1

        prometheus_metrics.set_neo4j_status(False)
        assert prometheus_metrics.neo4j_status.get_value() == 0

    def test_set_neo4j_status_int(self, prometheus_metrics):
        """Test setting Neo4j status with integer."""
        prometheus_metrics.set_neo4j_status(1)
        assert prometheus_metrics.neo4j_status.get_value() == 1

        prometheus_metrics.set_neo4j_status(0)
        assert prometheus_metrics.neo4j_status.get_value() == 0

    def test_set_gateway_status(self, prometheus_metrics):
        """Test setting gateway status."""
        prometheus_metrics.set_gateway_status("main", "available")
        assert prometheus_metrics.gateway_status.get_value(gateway_id="main") == 1

        prometheus_metrics.set_gateway_status("main", "unavailable")
        assert prometheus_metrics.gateway_status.get_value(gateway_id="main") == 0

    def test_set_signal_status(self, prometheus_metrics):
        """Test setting Signal status."""
        prometheus_metrics.set_signal_status("connected")
        assert prometheus_metrics.signal_status.get_value() == 1

        prometheus_metrics.set_signal_status("disconnected")
        assert prometheus_metrics.signal_status.get_value() == 0

    def test_inc_task_created(self, prometheus_metrics):
        """Test incrementing task creation counter."""
        prometheus_metrics.inc_task_created("main", "research")
        value = prometheus_metrics.task_created_total.get_value(agent="main", task_type="research")
        assert value == 1.0

    def test_inc_task_created_multiple(self, prometheus_metrics):
        """Test incrementing task creation counter multiple times."""
        prometheus_metrics.inc_task_created("main", "research")
        prometheus_metrics.inc_task_created("main", "research")
        prometheus_metrics.inc_task_created("main", "write")

        assert prometheus_metrics.task_created_total.get_value(agent="main", task_type="research") == 2.0
        assert prometheus_metrics.task_created_total.get_value(agent="main", task_type="write") == 1.0

    def test_inc_task_completed(self, prometheus_metrics):
        """Test incrementing task completion counter."""
        prometheus_metrics.inc_task_completed("research", "research", 45.2)
        value = prometheus_metrics.task_completed_total.get_value(agent="research", task_type="research")
        assert value == 1.0

    def test_inc_task_failed(self, prometheus_metrics):
        """Test incrementing task failure counter."""
        prometheus_metrics.inc_task_failed("research", "research", "timeout")
        value = prometheus_metrics.task_failed_total.get_value(
            agent="research",
            task_type="research",
            error_type="timeout"
        )
        assert value == 1.0

    def test_set_queue_depth(self, prometheus_metrics):
        """Test setting queue depth."""
        prometheus_metrics.set_queue_depth("research", 25)
        assert prometheus_metrics.queue_depth.get_value(agent="research") == 25.0

    def test_set_agent_heartbeat(self, prometheus_metrics):
        """Test setting agent heartbeat."""
        now = time.time()
        prometheus_metrics.set_agent_heartbeat("main", now)
        assert prometheus_metrics.agent_heartbeat_timestamp.get_value(agent="main") == now

    def test_set_agent_heartbeat_default_time(self, prometheus_metrics):
        """Test setting agent heartbeat with default time."""
        before = time.time()
        prometheus_metrics.set_agent_heartbeat("main")
        after = time.time()

        heartbeat = prometheus_metrics.agent_heartbeat_timestamp.get_value(agent="main")
        assert before <= heartbeat <= after

    def test_set_agent_success_rate(self, prometheus_metrics):
        """Test setting agent success rate."""
        prometheus_metrics.set_agent_success_rate("research", 0.95)
        assert prometheus_metrics.agent_success_rate.get_value(agent="research") == 0.95

    def test_set_agent_success_rate_clamped(self, prometheus_metrics):
        """Test that success rate is clamped between 0 and 1."""
        prometheus_metrics.set_agent_success_rate("research", 1.5)
        assert prometheus_metrics.agent_success_rate.get_value(agent="research") == 1.0

        prometheus_metrics.set_agent_success_rate("research", -0.5)
        assert prometheus_metrics.agent_success_rate.get_value(agent="research") == 0.0

    def test_set_agent_error_rate(self, prometheus_metrics):
        """Test setting agent error rate."""
        prometheus_metrics.set_agent_error_rate("research", 0.05)
        assert prometheus_metrics.agent_error_rate.get_value(agent="research") == 0.05

    def test_observe_agent_response_time(self, prometheus_metrics):
        """Test observing agent response time."""
        prometheus_metrics.observe_agent_response_time("research", 3.5)
        # Response time is a histogram, we just verify it doesn't error
        assert True

    def test_set_node_count(self, prometheus_metrics):
        """Test setting node count."""
        prometheus_metrics.set_node_count("Task", 150)
        assert prometheus_metrics.memory_nodes_total.get_value(node_type="Task") == 150.0

    def test_set_relationship_count(self, prometheus_metrics):
        """Test setting relationship count."""
        prometheus_metrics.set_relationship_count("HAS_TASK", 150)
        assert prometheus_metrics.memory_relationships_total.get_value(relationship_type="HAS_TASK") == 150.0

    def test_set_index_usage(self, prometheus_metrics):
        """Test setting index usage."""
        prometheus_metrics.set_index_usage("task_agent_idx", "hits", 1000)
        assert prometheus_metrics.memory_index_usage.get_value(
            index_name="task_agent_idx",
            stat_type="hits"
        ) == 1000.0

    def test_observe_query_duration(self, prometheus_metrics):
        """Test observing query duration."""
        prometheus_metrics.observe_query_duration("create_task", 0.015)
        # Query duration is a histogram, we just verify it doesn't error
        assert True

    def test_inc_failover_activated(self, prometheus_metrics):
        """Test incrementing failover activation counter."""
        prometheus_metrics.inc_failover_activated("kublai_unresponsive")
        value = prometheus_metrics.failover_activated_total.get_value(reason="kublai_unresponsive")
        assert value == 1.0

    def test_set_failover_active(self, prometheus_metrics):
        """Test setting failover active status."""
        prometheus_metrics.set_failover_active(True)
        assert prometheus_metrics.failover_active.get_value() == 1

        prometheus_metrics.set_failover_active(False)
        assert prometheus_metrics.failover_active.get_value() == 0

    def test_set_failover_duration(self, prometheus_metrics):
        """Test setting failover duration."""
        prometheus_metrics.set_failover_duration(120.5)
        assert prometheus_metrics.failover_duration_seconds.get_value() == 120.5

    def test_export_metrics(self, prometheus_metrics):
        """Test exporting all metrics."""
        prometheus_metrics.set_neo4j_status(1)
        prometheus_metrics.inc_task_created("main", "research")

        exported = prometheus_metrics.export_metrics()
        assert "openclaw_neo4j_status 1" in exported
        assert "openclaw_task_created_total" in exported

    def test_is_agent_healthy_true(self, prometheus_metrics):
        """Test agent health check returns True for recent heartbeat."""
        prometheus_metrics.set_agent_heartbeat("main")
        assert prometheus_metrics.is_agent_healthy("main") is True

    def test_is_agent_healthy_false(self, prometheus_metrics):
        """Test agent health check returns False for stale heartbeat."""
        # Set heartbeat to 10 minutes ago
        old_time = time.time() - 600
        prometheus_metrics.set_agent_heartbeat("main", old_time)
        assert prometheus_metrics.is_agent_healthy("main") is False

    def test_is_agent_healthy_no_heartbeat(self, prometheus_metrics):
        """Test agent health check returns False when no heartbeat recorded."""
        assert prometheus_metrics.is_agent_healthy("nonexistent") is False

    def test_get_unhealthy_agents(self, prometheus_metrics):
        """Test getting list of unhealthy agents."""
        # Recent heartbeat
        prometheus_metrics.set_agent_heartbeat("main")

        # Stale heartbeat
        old_time = time.time() - 400
        prometheus_metrics.set_agent_heartbeat("ops", old_time)

        unhealthy = prometheus_metrics.get_unhealthy_agents()
        assert "ops" in unhealthy
        assert "main" not in unhealthy

    def test_get_task_failure_rate(self, prometheus_metrics):
        """Test calculating task failure rate."""
        # Record some completed and failed tasks
        prometheus_metrics.inc_task_completed("research", "research", 10.0)
        prometheus_metrics.inc_task_completed("research", "research", 15.0)
        prometheus_metrics.inc_task_failed("research", "research", "error")
        prometheus_metrics.inc_task_failed("research", "research", "timeout")

        rate = prometheus_metrics.get_task_failure_rate("research", "research")
        # 2 failures out of 4 total = 0.5
        assert rate == 0.5

    def test_get_task_failure_rate_no_data(self, prometheus_metrics):
        """Test failure rate returns 0 when no data."""
        rate = prometheus_metrics.get_task_failure_rate("nonexistent")
        assert rate == 0.0


# =============================================================================
# AlertManager Tests
# =============================================================================

class TestAlert:
    """Test cases for the Alert class."""

    def test_alert_creation(self):
        """Test creating an alert."""
        alert = Alert(
            alert_name="TestAlert",
            severity="warning",
            summary="Test summary",
            description="Test description",
        )
        assert alert.alert_name == "TestAlert"
        assert alert.severity == "warning"
        assert alert.summary == "Test summary"
        assert alert.description == "Test description"

    def test_alert_with_labels(self):
        """Test creating an alert with labels."""
        alert = Alert(
            alert_name="TestAlert",
            severity="critical",
            summary="Test",
            labels={"agent": "main", "reason": "timeout"},
        )
        assert alert.labels["agent"] == "main"
        assert alert.labels["reason"] == "timeout"

    def test_alert_to_dict(self):
        """Test converting alert to dictionary."""
        alert = Alert(
            alert_name="TestAlert",
            severity="warning",
            summary="Test summary",
            description="Test description",
        )
        alert_dict = alert.to_dict()

        assert alert_dict["alert_name"] == "TestAlert"
        assert alert_dict["severity"] == "warning"
        assert alert_dict["summary"] == "Test summary"
        assert "timestamp" in alert_dict
        assert "datetime" in alert_dict


class TestAlertManager:
    """Test cases for the AlertManager class."""

    def test_initialization(self):
        """Test AlertManager initialization."""
        manager = AlertManager(webhook_url=None)
        assert manager.webhook_url is None
        assert manager._alert_cooldown == 300

    def test_initialization_with_webhook(self):
        """Test AlertManager initialization with webhook URL."""
        manager = AlertManager(webhook_url="https://example.com/webhook")
        assert manager.webhook_url == "https://example.com/webhook"

    def test_initialization_with_thresholds(self):
        """Test AlertManager initialization with custom thresholds."""
        manager = AlertManager(thresholds={"agent_error_rate": 0.2})
        assert manager.AGENT_ERROR_RATE_THRESHOLD == 0.2

    def test_create_alert(self, alert_manager):
        """Test creating an alert."""
        alert = alert_manager._create_alert(
            alert_name="TestAlert",
            severity="warning",
            summary="Test summary",
            description="Test description",
        )
        assert alert.alert_name == "TestAlert"
        assert alert.severity == "warning"

    def test_check_agent_health_no_issues(self, alert_manager, sample_metrics):
        """Test agent health check with no issues."""
        alerts = alert_manager.check_agent_health(sample_metrics)
        assert len(alerts) == 0

    def test_check_agent_health_unhealthy_agent(self, alert_manager, prometheus_metrics):
        """Test agent health check detects unhealthy agent."""
        # Set stale heartbeat
        old_time = time.time() - 400
        prometheus_metrics.set_agent_heartbeat("main", old_time)

        alerts = alert_manager.check_agent_health(prometheus_metrics)
        assert len(alerts) > 0
        assert any("main" in alert.labels.get("agent", "") for alert in alerts)

    def test_check_agent_health_high_error_rate(self, alert_manager, prometheus_metrics):
        """Test agent health check detects high error rate."""
        prometheus_metrics.set_agent_heartbeat("main")
        prometheus_metrics.set_agent_error_rate("main", 0.15)  # Above 10% threshold

        alerts = alert_manager.check_agent_health(prometheus_metrics)
        assert len(alerts) > 0
        assert any("HighErrorRate" in alert.alert_name for alert in alerts)

    def test_check_task_performance_no_issues(self, alert_manager, sample_metrics):
        """Test task performance check with no issues."""
        alerts = alert_manager.check_task_performance(sample_metrics)
        assert len(alerts) == 0

    def test_check_task_performance_queue_backlog(self, alert_manager, prometheus_metrics):
        """Test task performance check detects queue backlog."""
        prometheus_metrics.set_queue_depth("research", 75)  # Above 50 threshold

        alerts = alert_manager.check_task_performance(prometheus_metrics)
        assert len(alerts) > 0
        assert any("QueueBacklog" in alert.alert_name for alert in alerts)

    def test_check_neo4j_health_down(self, alert_manager, prometheus_metrics):
        """Test Neo4j health check detects disconnection."""
        prometheus_metrics.set_neo4j_status(0)

        alerts = alert_manager.check_neo4j_health(prometheus_metrics)
        assert len(alerts) > 0
        assert any(alert.alert_name == "Neo4jDown" for alert in alerts)

    def test_check_neo4j_health_healthy(self, alert_manager, sample_metrics):
        """Test Neo4j health check with healthy connection."""
        alerts = alert_manager.check_neo4j_health(sample_metrics)
        assert len(alerts) == 0

    def test_check_failover_status_active(self, alert_manager, prometheus_metrics):
        """Test failover status check detects active failover."""
        prometheus_metrics.set_failover_active(True)

        alerts = alert_manager.check_failover_status(prometheus_metrics)
        assert len(alerts) > 0
        assert any("Failover" in alert.alert_name for alert in alerts)

    def test_check_failover_status_extended(self, alert_manager, prometheus_metrics):
        """Test failover status check detects extended failover."""
        prometheus_metrics.set_failover_active(True)
        prometheus_metrics.set_failover_duration(4000)  # Over 1 hour

        alerts = alert_manager.check_failover_status(prometheus_metrics)
        assert len(alerts) > 0
        assert any("Extended" in alert.alert_name for alert in alerts)

    def test_check_all(self, alert_manager, prometheus_metrics):
        """Test running all health checks."""
        # Set up conditions that trigger alerts
        prometheus_metrics.set_neo4j_status(0)
        old_time = time.time() - 400
        prometheus_metrics.set_agent_heartbeat("main", old_time)

        alerts = alert_manager.check_all(prometheus_metrics)
        assert len(alerts) >= 2  # At least Neo4jDown and AgentDown

    def test_alert_cooldown(self, alert_manager, prometheus_metrics):
        """Test that alerts respect cooldown period."""
        # Set up condition that triggers alert
        prometheus_metrics.set_neo4j_status(0)

        # First check should generate alert
        alerts1 = alert_manager.check_neo4j_health(prometheus_metrics)
        assert len(alerts1) > 0

        # Immediate second check should not generate alert due to cooldown
        alerts2 = alert_manager.check_neo4j_health(prometheus_metrics)
        assert len(alerts2) == 0

    def test_send_alert_no_webhook(self, alert_manager):
        """Test sending alert with no webhook configured."""
        alert = Alert(
            alert_name="TestAlert",
            severity="info",
            summary="Test",
        )
        result = alert_manager.send_alert(alert)
        assert result is False  # No webhook configured

    def test_send_alert_with_mock_webhook(self, alert_manager):
        """Test sending alert with mocked webhook."""
        alert_manager.webhook_url = "https://example.com/webhook"

        alert = Alert(
            alert_name="TestAlert",
            severity="info",
            summary="Test",
        )

        # Mock urlopen to avoid actual HTTP request
        with patch("tools.monitoring.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.__enter__ = Mock(return_value=mock_response)
            mock_response.__exit__ = Mock(return_value=False)
            mock_urlopen.return_value = mock_response

            result = alert_manager.send_alert(alert)
            assert result is True

    def test_send_alerts(self, alert_manager):
        """Test sending multiple alerts."""
        alert_manager.webhook_url = "https://example.com/webhook"

        alerts = [
            Alert("Alert1", "warning", "Summary1"),
            Alert("Alert2", "critical", "Summary2"),
        ]

        # Mock urlopen
        with patch("tools.monitoring.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.__enter__ = Mock(return_value=mock_response)
            mock_response.__exit__ = Mock(return_value=False)
            mock_urlopen.return_value = mock_response

            success_count = alert_manager.send_alerts(alerts)
            assert success_count == 2


# =============================================================================
# Convenience Functions Tests
# =============================================================================

class TestConvenienceFunctions:
    """Test cases for convenience functions."""

    def test_create_monitoring(self):
        """Test create_monitoring function."""
        metrics, alert_manager = create_monitoring(
            port=9090,
            host="localhost",
            webhook_url="https://example.com/webhook",
        )
        assert isinstance(metrics, PrometheusMetrics)
        assert isinstance(alert_manager, AlertManager)
        assert metrics.port == 9090
        assert alert_manager.webhook_url == "https://example.com/webhook"

    def test_create_monitoring_defaults(self):
        """Test create_monitoring with default values."""
        metrics, alert_manager = create_monitoring()
        assert isinstance(metrics, PrometheusMetrics)
        assert isinstance(alert_manager, AlertManager)

    def test_get_registry(self):
        """Test get_registry returns singleton."""
        registry1 = get_registry()
        registry2 = get_registry()
        assert registry1 is registry2


# =============================================================================
# Thread Safety Tests
# =============================================================================

class TestThreadSafety:
    """Test cases for thread safety of metrics and alerts."""

    def test_concurrent_metric_updates(self, fresh_registry):
        """Test concurrent metric updates are thread-safe."""
        import threading

        gauge = Gauge("test_gauge", registry=fresh_registry)

        def increment_gauge():
            for _ in range(100):
                gauge.inc()

        threads = [threading.Thread(target=increment_gauge) for _ in range(10)]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # All 1000 increments should be recorded
        assert gauge.get_value() == 1000

    def test_concurrent_labeled_metric_updates(self, fresh_registry):
        """Test concurrent labeled metric updates are thread-safe."""
        import threading

        counter = Counter("test_counter", label_names=["agent"], registry=fresh_registry)

        def increment_agent(agent_id):
            for _ in range(50):
                counter.inc(amount=1, agent=agent_id)

        agents = ["main", "research", "write", "dev", "analyze"]
        threads = [threading.Thread(target=increment_agent, args=(agent,)) for agent in agents]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # Each agent should have 50 increments
        for agent in agents:
            assert counter.get_value(agent=agent) == 50

    def test_concurrent_alert_checks(self, prometheus_metrics, alert_manager):
        """Test concurrent alert checks are thread-safe."""
        import threading

        # Set up alert condition
        prometheus_metrics.set_neo4j_status(0)

        alert_counts = [0]
        lock = threading.Lock()

        def check_alerts():
            alerts = alert_manager.check_neo4j_health(prometheus_metrics)
            with lock:
                alert_counts[0] += len(alerts)

        threads = [threading.Thread(target=check_alerts) for _ in range(5)]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # Only first check should generate alert due to cooldown
        assert alert_counts[0] == 1


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for the monitoring system."""

    def test_full_monitoring_workflow(self):
        """Test complete monitoring workflow from metrics to alerts."""
        # Create monitoring setup
        metrics, alert_manager = create_monitoring(port=0)

        # Simulate system operation
        metrics.set_neo4j_status(1)
        metrics.set_agent_heartbeat("main")
        metrics.inc_task_created("main", "research")
        metrics.inc_task_completed("main", "research", 30.0)
        metrics.set_queue_depth("main", 5)

        # Check for alerts - should be none
        alerts = alert_manager.check_all(metrics)
        assert len(alerts) == 0

        # Simulate degradation
        metrics.set_agent_error_rate("main", 0.15)  # Above threshold
        metrics.set_queue_depth("main", 75)  # Above threshold

        # Check for alerts
        alerts = alert_manager.check_all(metrics)
        assert len(alerts) > 0

        # Verify alert types
        alert_types = [alert.alert_name for alert in alerts]
        assert "AgentHighErrorRate_main" in alert_types or "AgentQueueBacklog_main" in alert_types

    def test_metrics_export_format(self, prometheus_metrics):
        """Test that metrics export is valid Prometheus format."""
        # Set various metrics
        prometheus_metrics.set_neo4j_status(1)
        prometheus_metrics.inc_task_created("main", "research")
        prometheus_metrics.set_agent_heartbeat("main")

        exported = prometheus_metrics.export_metrics()

        # Verify required elements
        assert "# HELP" in exported
        assert "# TYPE" in exported
        assert "openclaw_" in exported
        assert "neo4j_status" in exported

    def test_multiple_agents_monitoring(self):
        """Test monitoring multiple agents simultaneously."""
        metrics, alert_manager = create_monitoring(port=0)

        agents = ["main", "research", "write", "dev", "analyze", "ops"]

        # Set up all agents
        for agent in agents:
            metrics.set_agent_heartbeat(agent)
            metrics.set_agent_success_rate(agent, 0.95)
            metrics.set_agent_error_rate(agent, 0.05)
            metrics.set_queue_depth(agent, 10)

        # All should be healthy
        alerts = alert_manager.check_all(metrics)
        assert len(alerts) == 0

        # Make one agent unhealthy
        old_time = time.time() - 400
        metrics.set_agent_heartbeat("ops", old_time)

        alerts = alert_manager.check_all(metrics)
        assert len(alerts) > 0
        assert "ops" in str(alerts)

    def test_failover_scenario(self):
        """Test monitoring during failover scenario."""
        metrics, alert_manager = create_monitoring(port=0)

        # Normal operation
        metrics.set_neo4j_status(1)
        metrics.set_agent_heartbeat("main")

        alerts = alert_manager.check_all(metrics)
        assert len(alerts) == 0

        # Failover activation
        metrics.inc_failover_activated("kublai_unresponsive")
        metrics.set_failover_active(True)

        alerts = alert_manager.check_all(metrics)
        assert any("Failover" in alert.alert_name for alert in alerts)

        # Extended failover
        metrics.set_failover_duration(4000)

        alerts = alert_manager.check_all(metrics)
        assert any("Extended" in alert.alert_name for alert in alerts)


# =============================================================================
# Constants Tests
# =============================================================================

class TestConstants:
    """Test cases for monitoring constants."""

    def test_threshold_constants(self):
        """Test that threshold constants have expected values."""
        assert AGENT_ERROR_RATE_THRESHOLD == 0.10
        assert TASK_FAILURE_RATE_THRESHOLD == 0.15
        assert NEO4J_QUERY_DURATION_THRESHOLD == 1.0
        assert FAILOVER_THRESHOLD == 3
        assert QUEUE_DEPTH_THRESHOLD == 50


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
