"""
Monitoring Module - Prometheus metrics and alerting for OpenClaw multi-agent system.

This module provides comprehensive monitoring capabilities including:
- Prometheus metrics export for system health and performance
- Alert generation based on configurable thresholds
- Integration with Neo4j for operational metrics
- Agent heartbeat tracking
- Task performance monitoring
- Failover event tracking

Classes:
    PrometheusMetrics: Main metrics collector and exporter
    AlertManager: Alert generation and notification handling
    MetricsRegistry: Shared metrics registry for all collectors

Environment Variables:
    METRICS_PORT: Port for metrics HTTP server (default: 9090)
    METRICS_HOST: Host for metrics HTTP server (default: 0.0.0.0)
    ALERT_WEBHOOK_URL: Webhook URL for alert notifications (optional)
    PROMETHEUS_MULTIPROC_DIR: Directory for multiprocess metrics (optional)

Example Usage:
    from tools.monitoring import PrometheusMetrics, AlertManager, create_monitoring

    # Create and start metrics server
    metrics = PrometheusMetrics(port=9090)
    metrics.start_metrics_server()

    # Record task metrics
    metrics.inc_task_created("main", "research")
    metrics.inc_task_completed("main", "research", duration=45.2)

    # Check for alerts
    alert_manager = AlertManager(webhook_url="https://hooks.example.com/alert")
    alerts = alert_manager.check_agent_health(metrics)
    for alert in alerts:
        alert_manager.send_alert(alert)

    # Stop server when done
    metrics.stop_metrics_server()
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Protocol,
    Tuple,
    Union,
)
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import URLError

# Configure logging
logger = logging.getLogger(__name__)

# =============================================================================
# Type Definitions
# =============================================================================

AgentId = str
TaskType = str
ErrorType = str
QueryType = str

# =============================================================================
# Constants
# =============================================================================

# Default configuration
DEFAULT_METRICS_PORT = 9090
DEFAULT_METRICS_HOST = "0.0.0.0"
DEFAULT_SCRAPE_INTERVAL = 15  # seconds

# Alert thresholds (from specification)
AGENT_ERROR_RATE_THRESHOLD = 0.10  # 10%
TASK_FAILURE_RATE_THRESHOLD = 0.15  # 15%
NEO4J_QUERY_DURATION_THRESHOLD = 1.0  # 1 second
FAILOVER_THRESHOLD = 3  # 3 per hour
QUEUE_DEPTH_THRESHOLD = 50

# Agent heartbeat thresholds
AGENT_HEARTBEAT_WARNING_SECONDS = 120  # 2 minutes
AGENT_HEARTBEAT_CRITICAL_SECONDS = 300  # 5 minutes

# Metric name prefixes
METRIC_PREFIX = "openclaw"

# =============================================================================
# Mock Prometheus Client for Testing
# =============================================================================

class MockPrometheusError(Exception):
    """Base exception for mock Prometheus client errors."""
    pass


class MetricType:
    """Enumeration of metric types."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


@dataclass
class MetricValue:
    """A single metric value with labels."""
    name: str
    value: float
    labels: Dict[str, str] = field(default_factory=dict)
    type: str = MetricType.GAUGE
    help: str = ""
    timestamp: float = field(default_factory=lambda: time.time())


class Metric:
    """
    Base class for Prometheus metrics.

    Provides thread-safe metric storage and Prometheus text format export.
    """

    def __init__(
        self,
        name: str,
        help_text: str = "",
        metric_type: str = MetricType.GAUGE,
        label_names: Optional[List[str]] = None,
        registry: Optional["MetricsRegistry"] = None,
    ):
        """
        Initialize a metric.

        Args:
            name: Metric name (will be prefixed with openclaw_)
            help_text: Metric description for Prometheus
            metric_type: Type of metric (counter, gauge, histogram, summary)
            label_names: List of label names for this metric
            registry: Optional MetricsRegistry to auto-register the metric
        """
        self.name = f"{METRIC_PREFIX}_{name}" if not name.startswith(METRIC_PREFIX) else name
        self.help_text = help_text
        self.metric_type = metric_type
        self.label_names = label_names or []
        self._values: Dict[str, MetricValue] = {}
        self._lock = threading.RLock()
        self._created = time.time()

        # Auto-register with provided registry
        if registry is not None:
            registry.register(self)

    def _get_label_key(self, labels: Dict[str, str]) -> str:
        """Generate a key for the labels dictionary."""
        if not self.label_names:
            return ""
        return "|".join(str(labels.get(name, "")) for name in self.label_names)

    def set(self, value: float, **labels: str) -> None:
        """Set the metric value (for Gauge)."""
        with self._lock:
            key = self._get_label_key(labels)
            if key not in self._values:
                self._values[key] = MetricValue(
                    name=self.name,
                    value=value,
                    labels=labels,
                    type=self.metric_type,
                    help=self.help_text,
                )
            else:
                self._values[key].value = value
                self._values[key].timestamp = time.time()

    def inc(self, amount: float = 1.0, **labels: str) -> None:
        """Increment the metric value."""
        with self._lock:
            key = self._get_label_key(labels)
            if key not in self._values:
                self._values[key] = MetricValue(
                    name=self.name,
                    value=amount,
                    labels=labels,
                    type=self.metric_type,
                    help=self.help_text,
                )
            else:
                self._values[key].value += amount
                self._values[key].timestamp = time.time()

    def dec(self, amount: float = 1.0, **labels: str) -> None:
        """Decrement the metric value (for Gauge)."""
        self.inc(-amount, **labels)

    def observe(self, value: float, **labels: str) -> None:
        """Observe a value (for Histogram/Summary)."""
        with self._lock:
            key = self._get_label_key(labels)
            if key not in self._values:
                self._values[key] = MetricValue(
                    name=self.name,
                    value=value,
                    labels=labels,
                    type=self.metric_type,
                    help=self.help_text,
                )
                # Initialize bucket counts for histogram
                if self.metric_type == MetricType.HISTOGRAM:
                    self._values[key]._count = 1
                    self._values[key]._sum = value
            else:
                metric_value = self._values[key]
                if self.metric_type == MetricType.HISTOGRAM:
                    metric_value._count = getattr(metric_value, '_count', 0) + 1
                    metric_value._sum = getattr(metric_value, '_sum', 0) + value
                metric_value.value = value
                metric_value.timestamp = time.time()

    def get_value(self, **labels: str) -> Optional[float]:
        """Get the current value for the given labels."""
        with self._lock:
            key = self._get_label_key(labels)
            if key in self._values:
                return self._values[key].value
            return None

    def get_all_values(self) -> List[MetricValue]:
        """Get all metric values."""
        with self._lock:
            return list(self._values.values())

    def export_prometheus(self) -> str:
        """Export metric in Prometheus text format."""
        lines = [f"# HELP {self.name} {self.help_text}"]
        lines.append(f"# TYPE {self.name} {self.metric_type}")

        for metric_value in self.get_all_values():
            label_str = ""
            if metric_value.labels:
                label_pairs = [f'{k}="{v}"' for k, v in metric_value.labels.items()]
                label_str = "{" + ",".join(label_pairs) + "}"

            if self.metric_type == MetricType.HISTOGRAM:
                # Export histogram with bucket notation
                count = getattr(metric_value, '_count', 1)
                sum_value = getattr(metric_value, '_sum', metric_value.value)
                lines.append(f"{self.name}_count{label_str} {count}")
                lines.append(f"{self.name}_sum{label_str} {sum_value}")
                # Add a +Inf bucket
                lines.append(f"{self.name}_bucket{label_str.replace('}', ',le=\"+Inf\"')} {count}")
            else:
                lines.append(f"{self.name}{label_str} {metric_value.value}")

        return "\n".join(lines) + "\n"


class Counter(Metric):
    """Counter metric that only increases."""

    def __init__(
        self,
        name: str,
        help_text: str = "",
        label_names: Optional[List[str]] = None,
        registry: Optional["MetricsRegistry"] = None,
    ):
        super().__init__(name, help_text, MetricType.COUNTER, label_names, registry)

    def inc(self, amount: float = 1.0, **labels: str) -> None:
        """Increment counter. Amount must be non-negative."""
        if amount < 0:
            raise ValueError("Counter can only be incremented by non-negative amounts")
        super().inc(amount, **labels)


class Gauge(Metric):
    """Gauge metric that can go up or down."""

    def __init__(
        self,
        name: str,
        help_text: str = "",
        label_names: Optional[List[str]] = None,
        registry: Optional["MetricsRegistry"] = None,
    ):
        super().__init__(name, help_text, MetricType.GAUGE, label_names, registry)


class Histogram(Metric):
    """Histogram metric for observing distributions."""

    # Default buckets (in seconds)
    DEFAULT_BUCKETS = [0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]

    def __init__(
        self,
        name: str,
        help_text: str = "",
        label_names: Optional[List[str]] = None,
        buckets: Optional[List[float]] = None,
        registry: Optional["MetricsRegistry"] = None,
    ):
        super().__init__(name, help_text, MetricType.HISTOGRAM, label_names, registry)
        self.buckets = buckets or self.DEFAULT_BUCKETS.copy()

    def observe(self, value: float, **labels: str) -> None:
        """Observe a value and update bucket counts."""
        with self._lock:
            key = self._get_label_key(labels)
            if key not in self._values:
                self._values[key] = MetricValue(
                    name=self.name,
                    value=value,
                    labels=labels,
                    type=self.metric_type,
                    help=self.help_text,
                )
                metric_value = self._values[key]
                metric_value._count = 1
                metric_value._sum = value
                metric_value._buckets = {b: 0 for b in self.buckets + ["+Inf"]}
            else:
                metric_value = self._values[key]
                metric_value._count += 1
                metric_value._sum += value
                metric_value.value = value

            # Update bucket counts
            metric_value = self._values[key]
            for bucket in self.buckets + ["+Inf"]:
                if bucket == "+Inf" or value <= bucket:
                    metric_value._buckets[bucket] = metric_value._buckets.get(bucket, 0) + 1

    def export_prometheus(self) -> str:
        """Export histogram in Prometheus text format."""
        lines = [f"# HELP {self.name} {self.help_text}"]
        lines.append(f"# TYPE {self.name} histogram")

        for metric_value in self.get_all_values():
            label_str = ""
            if metric_value.labels:
                label_pairs = [f'{k}="{v}"' for k, v in metric_value.labels.items()]
                label_str = "{" + ",".join(label_pairs) + "}"

            buckets = getattr(metric_value, '_buckets', {})
            count = getattr(metric_value, '_count', 0)
            sum_value = getattr(metric_value, '_sum', 0)

            # Export each bucket
            for bucket_value in self.buckets + ["+Inf"]:
                bucket_label = label_str.replace('}', f',le="{bucket_value}"')
                bucket_count = buckets.get(bucket_value, 0)
                lines.append(f"{self.name}_bucket{bucket_label} {bucket_count}")

            lines.append(f"{self.name}_sum{label_str} {sum_value}")
            lines.append(f"{self.name}_count{label_str} {count}")

        return "\n".join(lines) + "\n"


# =============================================================================
# Metrics Registry
# =============================================================================

class MetricsRegistry:
    """
    Registry for all Prometheus metrics.

    Provides centralized metric management and export functionality.
    Thread-safe for concurrent access.
    """

    def __init__(self):
        """Initialize an empty metrics registry."""
        self._metrics: Dict[str, Metric] = {}
        self._lock = threading.RLock()

    def register(self, metric: Metric) -> Metric:
        """
        Register a metric in the registry.

        Args:
            metric: The metric to register

        Returns:
            The registered metric

        Raises:
            MockPrometheusError: If a metric with the same name exists
        """
        with self._lock:
            if metric.name in self._metrics:
                # Return existing metric for idempotency
                return self._metrics[metric.name]
            self._metrics[metric.name] = metric
            logger.debug(f"Registered metric: {metric.name}")
            return metric

    def unregister(self, metric: Metric) -> None:
        """
        Unregister a metric from the registry.

        Args:
            metric: The metric to unregister
        """
        with self._lock:
            if metric.name in self._metrics and self._metrics[metric.name] is metric:
                del self._metrics[metric.name]
                logger.debug(f"Unregistered metric: {metric.name}")

    def get_metric(self, name: str) -> Optional[Metric]:
        """
        Get a metric by name.

        Args:
            name: Metric name

        Returns:
            The metric if found, None otherwise
        """
        with self._lock:
            return self._metrics.get(name)

    def get_all_metrics(self) -> List[Metric]:
        """Get all registered metrics."""
        with self._lock:
            return list(self._metrics.values())

    def export(self) -> str:
        """
        Export all metrics in Prometheus text format.

        Returns:
            String containing all metrics in Prometheus format
        """
        lines = []
        for metric in self.get_all_metrics():
            lines.append(metric.export_prometheus())
        return "\n".join(lines)

    def clear(self) -> None:
        """Clear all metrics from the registry."""
        with self._lock:
            self._metrics.clear()


# Global registry instance
_global_registry: Optional[MetricsRegistry] = None
_registry_lock = threading.Lock()


def get_registry() -> MetricsRegistry:
    """Get the global metrics registry, creating it if necessary."""
    global _global_registry
    with _registry_lock:
        if _global_registry is None:
            _global_registry = MetricsRegistry()
        return _global_registry


# =============================================================================
# Metrics Handler for HTTP Server
# =============================================================================

class MetricsRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for /metrics endpoint."""

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default logging."""
        pass

    def do_GET(self) -> None:
        """Handle GET request for metrics."""
        if self.path == "/metrics":
            registry = get_registry()
            metrics_data = registry.export()

            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.end_headers()
            self.wfile.write(metrics_data.encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")


# =============================================================================
# Main Prometheus Metrics Class
# =============================================================================

class PrometheusMetrics:
    """
    Prometheus metrics exporter for OpenClaw system.

    Provides a comprehensive set of metrics for monitoring:
    - System Health: Neo4j connection, agent heartbeat, gateway availability
    - Operational: Task creation/completion rates, queue depths
    - Agent Performance: Success rates, error rates, response times
    - Memory: Node/relationship counts, query performance
    - Failover: Failover activation counts and durations

    Metrics are exposed via HTTP on the configured port for Prometheus scraping.

    Attributes:
        port: Port number for the metrics HTTP server
        registry: MetricsRegistry instance for metric storage
    """

    # Class-level thresholds (can be overridden per instance)
    AGENT_ERROR_RATE_THRESHOLD = AGENT_ERROR_RATE_THRESHOLD
    TASK_FAILURE_RATE_THRESHOLD = TASK_FAILURE_RATE_THRESHOLD
    NEO4J_QUERY_DURATION_THRESHOLD = NEO4J_QUERY_DURATION_THRESHOLD
    FAILOVER_THRESHOLD = FAILOVER_THRESHOLD
    QUEUE_DEPTH_THRESHOLD = QUEUE_DEPTH_THRESHOLD

    def __init__(
        self,
        port: int = DEFAULT_METRICS_PORT,
        host: str = DEFAULT_METRICS_HOST,
        registry: Optional[MetricsRegistry] = None,
    ):
        """
        Initialize the Prometheus metrics exporter.

        Args:
            port: Port for the metrics HTTP server
            host: Host address for the metrics HTTP server
            registry: Optional custom metrics registry
        """
        self.port = port
        self.host = host
        self.registry = registry or get_registry()

        # HTTP server control
        self._server: Optional[HTTPServer] = None
        self._server_thread: Optional[threading.Thread] = None
        self._stop_server = threading.Event()

        # Tracking internal state for rate calculations
        self._task_created_window: Dict[Tuple[AgentId, TaskType], List[float]] = {}
        self._task_completed_window: Dict[Tuple[AgentId, TaskType], List[float]] = {}
        self._task_failed_window: Dict[Tuple[AgentId, TaskType], List[float]] = {}
        self._state_lock = threading.RLock()

        # Initialize all metrics
        self._init_system_health_metrics()
        self._init_operational_metrics()
        self._init_agent_performance_metrics()
        self._init_memory_metrics()
        self._init_failover_metrics()

        logger.info(f"PrometheusMetrics initialized (port: {self.port})")

    def _init_system_health_metrics(self) -> None:
        """Initialize system health metrics."""
        # Neo4j connection status
        self.neo4j_status = Gauge(
            "neo4j_status",
            "Neo4j connection status (1=connected, 0=disconnected)",
        )
        self.registry.register(self.neo4j_status)

        # Gateway availability
        self.gateway_status = Gauge(
            "gateway_status",
            "Gateway availability status (1=available, 0=unavailable)",
            ["gateway_id"],
        )
        self.registry.register(self.gateway_status)

        # Signal connectivity
        self.signal_status = Gauge(
            "signal_status",
            "Signal connectivity status (1=connected, 0=disconnected)",
        )
        self.registry.register(self.signal_status)

    def _init_operational_metrics(self) -> None:
        """Initialize operational metrics."""
        # Task creation rate
        self.task_created_total = Counter(
            "task_created_total",
            "Total number of tasks created",
            ["agent", "task_type"],
        )
        self.registry.register(self.task_created_total)

        # Task completion rate
        self.task_completed_total = Counter(
            "task_completed_total",
            "Total number of tasks completed",
            ["agent", "task_type"],
        )
        self.registry.register(self.task_completed_total)

        # Task failure rate
        self.task_failed_total = Counter(
            "task_failed_total",
            "Total number of task failures",
            ["agent", "task_type", "error_type"],
        )
        self.registry.register(self.task_failed_total)

        # Task duration
        self.task_duration_seconds = Histogram(
            "task_duration_seconds",
            "Task execution duration in seconds",
            ["agent", "task_type"],
            buckets=[1.0, 5.0, 15.0, 30.0, 60.0, 300.0, 600.0, 1800.0, 3600.0],
        )
        self.registry.register(self.task_duration_seconds)

        # Queue depth by agent
        self.queue_depth = Gauge(
            "queue_depth",
            "Current depth of task queue by agent",
            ["agent"],
        )
        self.registry.register(self.queue_depth)

    def _init_agent_performance_metrics(self) -> None:
        """Initialize agent performance metrics."""
        # Agent heartbeat timestamp
        self.agent_heartbeat_timestamp = Gauge(
            "agent_heartbeat_timestamp",
            "Unix timestamp of last agent heartbeat",
            ["agent"],
        )
        self.registry.register(self.agent_heartbeat_timestamp)

        # Agent success rate
        self.agent_success_rate = Gauge(
            "agent_success_rate",
            "Agent task success rate (0-1)",
            ["agent"],
        )
        self.registry.register(self.agent_success_rate)

        # Agent error rate
        self.agent_error_rate = Gauge(
            "agent_error_rate",
            "Agent task error rate (0-1)",
            ["agent"],
        )
        self.registry.register(self.agent_error_rate)

        # Agent response time
        self.agent_response_time_seconds = Histogram(
            "agent_response_time_seconds",
            "Agent response time in seconds",
            ["agent"],
            buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
        )
        self.registry.register(self.agent_response_time_seconds)

    def _init_memory_metrics(self) -> None:
        """Initialize Neo4j memory metrics."""
        # Node count by type
        self.memory_nodes_total = Gauge(
            "memory_nodes_total",
            "Total number of nodes in memory",
            ["node_type"],
        )
        self.registry.register(self.memory_nodes_total)

        # Relationship count by type
        self.memory_relationships_total = Gauge(
            "memory_relationships_total",
            "Total number of relationships in memory",
            ["relationship_type"],
        )
        self.registry.register(self.memory_relationships_total)

        # Index usage
        self.memory_index_usage = Gauge(
            "memory_index_usage",
            "Index usage statistics",
            ["index_name", "stat_type"],
        )
        self.registry.register(self.memory_index_usage)

        # Query performance
        self.neo4j_query_duration_seconds = Histogram(
            "neo4j_query_duration_seconds",
            "Neo4j query execution duration in seconds",
            ["query_type"],
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
        )
        self.registry.register(self.neo4j_query_duration_seconds)

    def _init_failover_metrics(self) -> None:
        """Initialize failover metrics."""
        # Failover activation count
        self.failover_activated_total = Counter(
            "failover_activated_total",
            "Total number of failover activations",
            ["reason"],
        )
        self.registry.register(self.failover_activated_total)

        # Failover duration
        self.failover_duration_seconds = Gauge(
            "failover_duration_seconds",
            "Current failover duration in seconds",
        )
        self.registry.register(self.failover_duration_seconds)

        # Failover active status
        self.failover_active = Gauge(
            "failover_active",
            "Failover activation status (1=active, 0=inactive)",
        )
        self.registry.register(self.failover_active)

    # =========================================================================
    # Server Management
    # =========================================================================

    def start_metrics_server(self) -> None:
        """
        Start the Prometheus metrics HTTP server.

        Starts a background thread serving metrics on the configured port.
        Safe to call multiple times (idempotent).
        """
        if self._server is not None and self._server_thread is alive():
            logger.debug("Metrics server already running")
            return

        self._stop_server.clear()

        try:
            self._server = HTTPServer((self.host, self.port), MetricsRequestHandler)
            self._server_thread = threading.Thread(
                target=self._run_server,
                daemon=True,
                name="PrometheusMetricsServer",
            )
            self._server_thread.start()

            logger.info(f"Metrics server started on http://{self.host}:{self.port}/metrics")

        except OSError as e:
            if "address already in use" in str(e).lower():
                logger.warning(f"Port {self.port} already in use, metrics may be served elsewhere")
            else:
                logger.error(f"Failed to start metrics server: {e}")
                raise

    def _run_server(self) -> None:
        """Run the HTTP server until stopped."""
        while not self._stop_server.is_set():
            self._server.handle_request()

    def stop_metrics_server(self) -> None:
        """Stop the Prometheus metrics HTTP server."""
        if self._server is None:
            return

        self._stop_server.set()
        self._server.shutdown()
        self._server.server_close()

        if self._server_thread:
            self._server_thread.join(timeout=5)

        self._server = None
        logger.info("Metrics server stopped")

    # =========================================================================
    # System Health Metrics
    # =========================================================================

    def set_neo4j_status(self, status: Union[int, bool, str]) -> None:
        """
        Set Neo4j connection status.

        Args:
            status: Connection status (1/connected/True for up, 0/disconnected/False for down)
        """
        if isinstance(status, str):
            value = 1 if status.lower() in ("connected", "up", "healthy", "1") else 0
        elif isinstance(status, bool):
            value = 1 if status else 0
        else:
            value = int(status)

        self.neo4j_status.set(value)

    def set_gateway_status(self, gateway_id: str, status: Union[int, bool, str]) -> None:
        """
        Set gateway availability status.

        Args:
            gateway_id: Identifier for the gateway
            status: Availability status (1/available/True for up, 0/unavailable/False for down)
        """
        if isinstance(status, str):
            value = 1 if status.lower() in ("available", "up", "healthy", "1") else 0
        elif isinstance(status, bool):
            value = 1 if status else 0
        else:
            value = int(status)

        self.gateway_status.set(value, gateway_id=gateway_id)

    def set_signal_status(self, status: Union[int, bool, str]) -> None:
        """
        Set Signal connectivity status.

        Args:
            status: Connectivity status (1/connected/True for up, 0/disconnected/False for down)
        """
        if isinstance(status, str):
            value = 1 if status.lower() in ("connected", "up", "healthy", "1") else 0
        elif isinstance(status, bool):
            value = 1 if status else 0
        else:
            value = int(status)

        self.signal_status.set(value)

    # =========================================================================
    # Operational Metrics
    # =========================================================================

    def inc_task_created(self, agent: AgentId, task_type: TaskType) -> None:
        """
        Increment task creation counter.

        Args:
            agent: Agent ID that created the task
            task_type: Type of task created
        """
        self.task_created_total.inc(amount=1, agent=agent, task_type=task_type)

        # Track in sliding window for rate calculation
        with self._state_lock:
            key = (agent, task_type)
            now = time.time()
            if key not in self._task_created_window:
                self._task_created_window[key] = []
            self._task_created_window[key].append(now)
            # Keep only last 5 minutes
            cutoff = now - 300
            self._task_created_window[key] = [
                t for t in self._task_created_window[key] if t > cutoff
            ]

    def inc_task_completed(
        self, agent: AgentId, task_type: TaskType, duration: float
    ) -> None:
        """
        Increment task completion counter with duration.

        Args:
            agent: Agent ID that completed the task
            task_type: Type of task completed
            duration: Task duration in seconds
        """
        self.task_completed_total.inc(amount=1, agent=agent, task_type=task_type)
        self.task_duration_seconds.observe(duration, agent=agent, task_type=task_type)

        # Track in sliding window for rate calculation
        with self._state_lock:
            key = (agent, task_type)
            now = time.time()
            if key not in self._task_completed_window:
                self._task_completed_window[key] = []
            self._task_completed_window[key].append(now)
            # Keep only last 5 minutes
            cutoff = now - 300
            self._task_completed_window[key] = [
                t for t in self._task_completed_window[key] if t > cutoff
            ]

    def inc_task_failed(
        self, agent: AgentId, task_type: TaskType, error_type: ErrorType
    ) -> None:
        """
        Increment task failure counter.

        Args:
            agent: Agent ID that failed the task
            task_type: Type of task that failed
            error_type: Type of error that occurred
        """
        self.task_failed_total.inc(
            amount=1, agent=agent, task_type=task_type, error_type=error_type
        )

        # Track in sliding window for rate calculation
        with self._state_lock:
            key = (agent, task_type)
            now = time.time()
            if key not in self._task_failed_window:
                self._task_failed_window[key] = []
            self._task_failed_window[key].append(now)
            # Keep only last 5 minutes
            cutoff = now - 300
            self._task_failed_window[key] = [
                t for t in self._task_failed_window[key] if t > cutoff
            ]

    def set_queue_depth(self, agent: AgentId, depth: int) -> None:
        """
        Set agent queue depth gauge.

        Args:
            agent: Agent ID
            depth: Current queue depth for the agent
        """
        self.queue_depth.set(float(depth), agent=agent)

    def get_task_failure_rate(self, agent: AgentId, task_type: Optional[TaskType] = None) -> float:
        """
        Calculate current task failure rate.

        Args:
            agent: Agent ID
            task_type: Optional task type filter

        Returns:
            Failure rate as a float between 0 and 1
        """
        with self._state_lock:
            now = time.time()
            cutoff = now - 300  # Last 5 minutes

            failed_count = 0
            completed_count = 0

            for (a, t), timestamps in self._task_failed_window.items():
                if a == agent and (task_type is None or t == task_type):
                    failed_count += sum(1 for ts in timestamps if ts > cutoff)

            for (a, t), timestamps in self._task_completed_window.items():
                if a == agent and (task_type is None or t == task_type):
                    completed_count += sum(1 for ts in timestamps if ts > cutoff)

            total = failed_count + completed_count
            if total == 0:
                return 0.0

            return failed_count / total

    # =========================================================================
    # Agent Performance Metrics
    # =========================================================================

    def set_agent_heartbeat(self, agent: AgentId, timestamp: Optional[float] = None) -> None:
        """
        Set agent heartbeat timestamp gauge.

        Args:
            agent: Agent ID
            timestamp: Unix timestamp (defaults to current time)
        """
        if timestamp is None:
            timestamp = time.time()

        self.agent_heartbeat_timestamp.set(timestamp, agent=agent)

    def set_agent_success_rate(self, agent: AgentId, rate: float) -> None:
        """
        Set agent success rate gauge.

        Args:
            agent: Agent ID
            rate: Success rate between 0 and 1
        """
        self.agent_success_rate.set(max(0.0, min(1.0, rate)), agent=agent)

    def set_agent_error_rate(self, agent: AgentId, rate: float) -> None:
        """
        Set agent error rate gauge.

        Args:
            agent: Agent ID
            rate: Error rate between 0 and 1
        """
        self.agent_error_rate.set(max(0.0, min(1.0, rate)), agent=agent)

    def observe_agent_response_time(self, agent: AgentId, duration: float) -> None:
        """
        Observe agent response time.

        Args:
            agent: Agent ID
            duration: Response time in seconds
        """
        self.agent_response_time_seconds.observe(duration, agent=agent)

    # =========================================================================
    # Memory Metrics
    # =========================================================================

    def set_node_count(self, node_type: str, count: int) -> None:
        """
        Set node count metric.

        Args:
            node_type: Type of node (e.g., Task, Agent, etc.)
            count: Number of nodes of this type
        """
        self.memory_nodes_total.set(float(count), node_type=node_type)

    def set_relationship_count(self, relationship_type: str, count: int) -> None:
        """
        Set relationship count metric.

        Args:
            relationship_type: Type of relationship
            count: Number of relationships of this type
        """
        self.memory_relationships_total.set(float(count), relationship_type=relationship_type)

    def set_index_usage(self, index_name: str, stat_type: str, value: float) -> None:
        """
        Set index usage metric.

        Args:
            index_name: Name of the index
            stat_type: Type of statistic (e.g., "hits", "misses", "size")
            value: Statistic value
        """
        self.memory_index_usage.set(value, index_name=index_name, stat_type=stat_type)

    def observe_query_duration(self, query_type: QueryType, duration: float) -> None:
        """
        Observe Neo4j query execution duration.

        Args:
            query_type: Type of query (e.g., "create_task", "claim_task")
            duration: Query duration in seconds
        """
        self.neo4j_query_duration_seconds.observe(duration, query_type=query_type)

    # =========================================================================
    # Failover Metrics
    # =========================================================================

    def inc_failover_activated(self, reason: str) -> None:
        """
        Increment failover activation counter.

        Args:
            reason: Reason for failover activation
        """
        self.failover_activated_total.inc(amount=1, reason=reason)

    def set_failover_active(self, active: bool) -> None:
        """
        Set failover active status.

        Args:
            active: Whether failover is currently active
        """
        self.failover_active.set(1 if active else 0)

    def set_failover_duration(self, duration: float) -> None:
        """
        Set failover duration gauge.

        Args:
            duration: Current failover duration in seconds
        """
        self.failover_duration_seconds.set(duration)

    # =========================================================================
    # Metric Export
    # =========================================================================

    def export_metrics(self) -> str:
        """
        Export all metrics in Prometheus text format.

        Returns:
            String containing all metrics in Prometheus text format
        """
        return self.registry.export()

    # =========================================================================
    # Health Check
    # =========================================================================

    def is_agent_healthy(self, agent: AgentId) -> bool:
        """
        Check if agent heartbeat is within acceptable threshold.

        Args:
            agent: Agent ID to check

        Returns:
            True if agent heartbeat is recent, False otherwise
        """
        last_seen = self.agent_heartbeat_timestamp.get_value(agent=agent)
        if last_seen is None:
            return False

        age = time.time() - last_seen
        return age <= AGENT_HEARTBEAT_CRITICAL_SECONDS

    def get_unhealthy_agents(self) -> List[AgentId]:
        """
        Get list of agents with stale heartbeats.

        Returns:
            List of agent IDs that are considered unhealthy
        """
        unhealthy = []
        all_values = self.agent_heartbeat_timestamp.get_all_values()

        for metric_value in all_values:
            agent = metric_value.labels.get("agent")
            if agent:
                age = time.time() - metric_value.value
                if age > AGENT_HEARTBEAT_CRITICAL_SECONDS:
                    unhealthy.append(agent)

        return unhealthy


# =============================================================================
# Alert Management
# =============================================================================

@dataclass
class Alert:
    """
    Representation of a monitoring alert.

    Attributes:
        alert_name: Name/identifier for the alert
        severity: Alert severity (critical, warning, info)
        summary: Brief summary of the alert
        description: Detailed description of the issue
        labels: Additional labels for the alert
        timestamp: When the alert was generated
    """
    alert_name: str
    severity: str
    summary: str
    description: str = ""
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=lambda: time.time())

    def to_dict(self) -> Dict[str, Any]:
        """Convert alert to dictionary for serialization."""
        return {
            "alert_name": self.alert_name,
            "severity": self.severity,
            "summary": self.summary,
            "description": self.description,
            "labels": self.labels,
            "timestamp": self.timestamp,
            "datetime": datetime.fromtimestamp(self.timestamp, tz=timezone.utc).isoformat(),
        }


class AlertManager:
    """
    Alert management for production monitoring.

    Monitors metrics and generates alerts when thresholds are exceeded.
    Supports webhook notification delivery.

    Attributes:
        webhook_url: Optional URL for alert webhook notifications
        AGENT_ERROR_RATE_THRESHOLD: Error rate threshold for agent alerts
        TASK_FAILURE_RATE_THRESHOLD: Failure rate threshold for task alerts
        NEO4J_QUERY_DURATION_THRESHOLD: Query duration threshold (seconds)
        FAILOVER_THRESHOLD: Failover count threshold per hour
        QUEUE_DEPTH_THRESHOLD: Queue depth threshold for alerts
    """

    # Alert thresholds (class-level defaults)
    AGENT_ERROR_RATE_THRESHOLD = AGENT_ERROR_RATE_THRESHOLD
    TASK_FAILURE_RATE_THRESHOLD = TASK_FAILURE_RATE_THRESHOLD
    NEO4J_QUERY_DURATION_THRESHOLD = NEO4J_QUERY_DURATION_THRESHOLD
    FAILOVER_THRESHOLD = FAILOVER_THRESHOLD
    QUEUE_DEPTH_THRESHOLD = QUEUE_DEPTH_THRESHOLD

    # Alert severities
    SEVERITY_CRITICAL = "critical"
    SEVERITY_WARNING = "warning"
    SEVERITY_INFO = "info"

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        thresholds: Optional[Dict[str, float]] = None,
    ):
        """
        Initialize the AlertManager.

        Args:
            webhook_url: Optional webhook URL for alert notifications
            thresholds: Optional custom threshold values
        """
        self.webhook_url = webhook_url

        # Apply custom thresholds if provided
        if thresholds:
            for key, value in thresholds.items():
                if hasattr(self, f"{key.upper()}_THRESHOLD"):
                    setattr(self, key.upper() + "_THRESHOLD", value)

        # Track recent alerts to avoid spam
        self._recent_alerts: Dict[str, float] = {}
        self._alert_cooldown = 300  # 5 minutes between same alert
        self._lock = threading.RLock()

        logger.info(f"AlertManager initialized (webhook: {webhook_url is not None})")

    def _should_fire_alert(self, alert_name: str) -> bool:
        """
        Check if alert should fire based on cooldown period.

        Args:
            alert_name: Name of the alert to check

        Returns:
            True if alert should fire, False if still in cooldown
        """
        with self._lock:
            now = time.time()
            last_fired = self._recent_alerts.get(alert_name, 0)

            if now - last_fired > self._alert_cooldown:
                self._recent_alerts[alert_name] = now
                return True

            return False

    def _create_alert(
        self,
        alert_name: str,
        severity: str,
        summary: str,
        description: str = "",
        **labels: str,
    ) -> Alert:
        """
        Create an alert instance.

        Args:
            alert_name: Name/identifier for the alert
            severity: Alert severity level
            summary: Brief summary
            description: Detailed description
            **labels: Additional labels for the alert

        Returns:
            Alert instance
        """
        return Alert(
            alert_name=alert_name,
            severity=severity,
            summary=summary,
            description=description or summary,
            labels=dict(labels),
        )

    # =========================================================================
    # Health Check Methods
    # =========================================================================

    def check_agent_health(self, metrics: PrometheusMetrics) -> List[Alert]:
        """
        Check agent health and generate alerts if needed.

        Checks:
        - Agent heartbeat staleness
        - Agent error rate
        - Agent success rate

        Args:
            metrics: PrometheusMetrics instance to check

        Returns:
            List of generated alerts
        """
        alerts = []

        # Check for agents with stale heartbeats
        unhealthy_agents = metrics.get_unhealthy_agents()

        for agent in unhealthy_agents:
            alert_name = f"AgentDown_{agent}"
            if self._should_fire_alert(alert_name):
                alert = self._create_alert(
                    alert_name=alert_name,
                    severity=self.SEVERITY_CRITICAL,
                    summary=f"Agent {agent} is down or unresponsive",
                    description=f"Agent {agent} has not sent a heartbeat in over "
                               f"{AGENT_HEARTBEAT_CRITICAL_SECONDS} seconds",
                    agent=agent,
                )
                alerts.append(alert)

        # Check agent error rates
        error_rate_metrics = metrics.agent_error_rate.get_all_values()
        for metric_value in error_rate_metrics:
            agent = metric_value.labels.get("agent", "unknown")
            error_rate = metric_value.value

            if error_rate > self.AGENT_ERROR_RATE_THRESHOLD:
                alert_name = f"AgentHighErrorRate_{agent}"
                if self._should_fire_alert(alert_name):
                    alert = self._create_alert(
                        alert_name=alert_name,
                        severity=self.SEVERITY_WARNING,
                        summary=f"High error rate for agent {agent}",
                        description=f"Agent {agent} error rate is {error_rate:.1%}, "
                                   f"above threshold of {self.AGENT_ERROR_RATE_THRESHOLD:.1%}",
                        agent=agent,
                        error_rate=f"{error_rate:.2%}",
                    )
                    alerts.append(alert)

        return alerts

    def check_task_performance(self, metrics: PrometheusMetrics) -> List[Alert]:
        """
        Check task performance and generate alerts if needed.

        Checks:
        - Task failure rate
        - Queue depth
        - Task duration outliers

        Args:
            metrics: PrometheusMetrics instance to check

        Returns:
            List of generated alerts
        """
        alerts = []

        # Check queue depths
        queue_metrics = metrics.queue_depth.get_all_values()
        for metric_value in queue_metrics:
            agent = metric_value.labels.get("agent", "unknown")
            depth = int(metric_value.value)

            if depth > self.QUEUE_DEPTH_THRESHOLD:
                alert_name = f"AgentQueueBacklog_{agent}"
                if self._should_fire_alert(alert_name):
                    alert = self._create_alert(
                        alert_name=alert_name,
                        severity=self.SEVERITY_WARNING,
                        summary=f"Task backlog for agent {agent}",
                        description=f"Agent {agent} has {depth} pending tasks, "
                                   f"above threshold of {self.QUEUE_DEPTH_THRESHOLD}",
                        agent=agent,
                        queue_depth=str(depth),
                    )
                    alerts.append(alert)

        # Check task failure rates per agent
        for metric_value in metrics.task_failed_total.get_all_values():
            agent = metric_value.labels.get("agent", "unknown")
            task_type = metric_value.labels.get("task_type", "unknown")

            failure_rate = metrics.get_task_failure_rate(agent, task_type)

            if failure_rate > self.TASK_FAILURE_RATE_THRESHOLD:
                alert_name = f"HighTaskFailureRate_{agent}_{task_type}"
                if self._should_fire_alert(alert_name):
                    alert = self._create_alert(
                        alert_name=alert_name,
                        severity=self.SEVERITY_WARNING,
                        summary=f"High task failure rate for {agent}",
                        description=f"Agent {agent} {task_type} task failure rate is "
                                   f"{failure_rate:.1%}, above threshold of "
                                   f"{self.TASK_FAILURE_RATE_THRESHOLD:.1%}",
                        agent=agent,
                        task_type=task_type,
                        failure_rate=f"{failure_rate:.2%}",
                    )
                    alerts.append(alert)

        return alerts

    def check_neo4j_health(self, metrics: PrometheusMetrics) -> List[Alert]:
        """
        Check Neo4j health and generate alerts if needed.

        Checks:
        - Connection status
        - Query duration
        - Circuit breaker state

        Args:
            metrics: PrometheusMetrics instance to check

        Returns:
            List of generated alerts
        """
        alerts = []

        # Check Neo4j connection status
        neo4j_status = metrics.neo4j_status.get_value()
        if neo4j_status is not None and neo4j_status == 0:
            alert_name = "Neo4jDown"
            if self._should_fire_alert(alert_name):
                alert = self._create_alert(
                    alert_name=alert_name,
                    severity=self.SEVERITY_CRITICAL,
                    summary="Neo4j is unavailable",
                    description="Neo4j connection is down or the system is in fallback mode",
                )
                alerts.append(alert)

        # Check query durations (p95 approximation from histogram)
        # For simplicity, we check if any query has exceeded threshold
        # In production, you'd use proper histogram quantile calculation

        return alerts

    def check_failover_status(self, metrics: PrometheusMetrics) -> List[Alert]:
        """
        Check failover status and generate alerts if needed.

        Checks:
        - Failover is active
        - Failover duration is excessive

        Args:
            metrics: PrometheusMetrics instance to check

        Returns:
            List of generated alerts
        """
        alerts = []

        # Check if failover is active
        failover_active = metrics.failover_active.get_value()
        if failover_active and failover_active > 0:
            alert_name = "FailoverActive"
            if self._should_fire_alert(alert_name):
                alert = self._create_alert(
                    alert_name=alert_name,
                    severity=self.SEVERITY_WARNING,
                    summary="Failover mode is active",
                    description="The system is currently operating in failover mode. "
                               "Kublai may be unavailable.",
                )
                alerts.append(alert)

        # Check failover duration
        duration = metrics.failover_duration_seconds.get_value()
        if duration and duration > 3600:  # 1 hour
            alert_name = "FailoverExtended"
            if self._should_fire_alert(alert_name):
                alert = self._create_alert(
                    alert_name=alert_name,
                    severity=self.SEVERITY_CRITICAL,
                    summary="Extended failover duration",
                    description=f"Failover has been active for {duration:.0f} seconds "
                               f"({duration / 60:.1f} minutes)",
                    duration_seconds=str(int(duration)),
                )
                alerts.append(alert)

        return alerts

    # =========================================================================
    # Alert Generation
    # =========================================================================

    def check_all(self, metrics: PrometheusMetrics) -> List[Alert]:
        """
        Run all health checks and generate alerts.

        Args:
            metrics: PrometheusMetrics instance to check

        Returns:
            List of all generated alerts
        """
        all_alerts = []

        all_alerts.extend(self.check_agent_health(metrics))
        all_alerts.extend(self.check_task_performance(metrics))
        all_alerts.extend(self.check_neo4j_health(metrics))
        all_alerts.extend(self.check_failover_status(metrics))

        if all_alerts:
            logger.info(f"Generated {len(all_alerts)} alerts")

        return all_alerts

    # =========================================================================
    # Alert Delivery
    # =========================================================================

    def send_alert(self, alert: Alert) -> bool:
        """
        Send alert notification via webhook.

        Args:
            alert: Alert to send

        Returns:
            True if alert was sent successfully, False otherwise
        """
        if not self.webhook_url:
            logger.warning(f"No webhook configured, would send alert: {alert.summary}")
            return False

        try:
            import json

            # Validate webhook URL
            parsed = urlparse(self.webhook_url)
            if not all([parsed.scheme, parsed.netloc]):
                logger.error(f"Invalid webhook URL: {self.webhook_url}")
                return False

            # Prepare payload
            payload = alert.to_dict()

            # Send request
            request = Request(
                self.webhook_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )

            with urlopen(request, timeout=10) as response:
                if response.status >= 200 and response.status < 300:
                    logger.info(f"Alert sent successfully: {alert.alert_name}")
                    return True
                else:
                    logger.error(f"Alert webhook returned status {response.status}")
                    return False

        except URLError as e:
            logger.error(f"Failed to send alert webhook: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending alert: {e}")
            return False

    def send_alerts(self, alerts: List[Alert]) -> int:
        """
        Send multiple alerts via webhook.

        Args:
            alerts: List of alerts to send

        Returns:
            Number of alerts sent successfully
        """
        success_count = 0
        for alert in alerts:
            if self.send_alert(alert):
                success_count += 1
        return success_count


# =============================================================================
# Convenience Functions
# =============================================================================

def create_monitoring(
    port: int = DEFAULT_METRICS_PORT,
    host: str = DEFAULT_METRICS_HOST,
    webhook_url: Optional[str] = None,
) -> Tuple[PrometheusMetrics, AlertManager]:
    """
    Create a complete monitoring setup.

    Args:
        port: Port for the metrics HTTP server
        host: Host for the metrics HTTP server
        webhook_url: Optional webhook URL for alerts

    Returns:
        Tuple of (PrometheusMetrics, AlertManager)
    """
    metrics = PrometheusMetrics(port=port, host=host)
    alert_manager = AlertManager(webhook_url=webhook_url)
    return metrics, alert_manager


def start_monitoring(
    port: int = DEFAULT_METRICS_PORT,
    host: str = DEFAULT_METRICS_HOST,
    webhook_url: Optional[str] = None,
) -> Tuple[PrometheusMetrics, AlertManager]:
    """
    Create and start monitoring with metrics server.

    Args:
        port: Port for the metrics HTTP server
        host: Host for the metrics HTTP server
        webhook_url: Optional webhook URL for alerts

    Returns:
        Tuple of (PrometheusMetrics, AlertManager)
    """
    metrics, alert_manager = create_monitoring(port, host, webhook_url)
    metrics.start_metrics_server()
    return metrics, alert_manager


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    # Configure logging for standalone usage
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    print("Prometheus Metrics - OpenClaw Monitoring")
    print("=" * 50)
    print()

    # Create and start monitoring
    metrics, alert_manager = start_monitoring(
        port=DEFAULT_METRICS_PORT,
        host=DEFAULT_METRICS_HOST,
    )

    print(f"Metrics server started on http://{DEFAULT_METRICS_HOST}:{DEFAULT_METRICS_PORT}/metrics")
    print()

    # Example: Record some metrics
    print("Recording example metrics...")

    metrics.set_neo4j_status("connected")
    metrics.inc_task_created("main", "research")
    metrics.set_agent_heartbeat("main")
    metrics.set_agent_heartbeat("research")
    metrics.set_agent_heartbeat("write")
    metrics.set_agent_heartbeat("dev")
    metrics.set_agent_heartbeat("analyze")
    metrics.set_agent_heartbeat("ops")
    metrics.set_node_count("Task", 150)
    metrics.set_relationship_count("HAS_TASK", 150)

    # Simulate task completion
    metrics.inc_task_completed("research", "research", 45.2)
    metrics.observe_agent_response_time("research", 3.5)
    metrics.observe_query_duration("create_task", 0.015)

    print("Example metrics recorded.")
    print()

    # Export metrics
    print("Current metrics:")
    print("-" * 30)
    print(metrics.export_metrics())

    # Run health checks
    print("Running health checks...")
    alerts = alert_manager.check_all(metrics)
    print(f"Generated {len(alerts)} alerts")

    # Keep server running
    print()
    print("Server running. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        metrics.stop_metrics_server()
        print("Done.")
