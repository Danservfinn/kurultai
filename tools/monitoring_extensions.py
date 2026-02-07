"""
Monitoring Extensions - Additional metrics for Kurultai testing framework.

This module extends the base monitoring.py with:
- Classification metrics (confidence, buckets, routing accuracy)
- Delegation latency breakdown by component
- Agent utilization tracking (active vs idle time)
- Instrumented versions of existing classes

Usage:
    from tools.monitoring_extensions import (
        InstrumentedTeamSizeClassifier,
        get_instrumented_metrics,
    )

    # Use instrumented classifier
    classifier = InstrumentedTeamSizeClassifier()
    result = classifier.classify(factors)
    # Metrics automatically recorded
"""

import logging
import time
from typing import Any, Dict, List, Optional
from functools import wraps

from tools.monitoring import Counter, Gauge, Histogram, MetricsRegistry

logger = logging.getLogger(__name__)

# =============================================================================
# Classification Metrics
# =============================================================================

# These would be registered in the main PrometheusMetrics class
# For now, they're defined here for reference

classification_confidence = Histogram(
    "kurultai_classification_confidence",
    "Distribution of classification confidence scores",
    buckets=[0.1, 0.3, 0.5, 0.7, 0.9, 0.95, 0.99, 1.0],
)

classification_bucket = Counter(
    "kurultai_classification_bucket_total",
    "Count of classifications by complexity bucket",
    label_names=["bucket"],  # low, medium, high, very_high
)

routing_accuracy = Gauge(
    "kurultai_routing_accuracy",
    "Percentage of correct initial agent assignments",
)

# =============================================================================
# Delegation Latency Metrics
# =============================================================================

delegation_latency = Histogram(
    "kurultai_delegation_latency_seconds",
    "Delegation latency by component",
    label_names=["component"],  # classification, neo4j_create, agentToAgent, claim
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

task_end_to_end_latency = Histogram(
    "kurultai_task_e2e_latency_seconds",
    "End-to-end task completion latency",
    label_names=["task_type"],
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
)

# =============================================================================
# Agent Utilization Metrics
# =============================================================================

agent_active_time = Counter(
    "kurultai_agent_active_seconds",
    "Time agents spend actively processing",
    label_names=["agent_id"],
)

agent_idle_time = Counter(
    "kurultai_agent_idle_seconds",
    "Time agents spend available but idle",
    label_names=["agent_id"],
)

agent_utilization = Gauge(
    "kurultai_agent_utilization",
    "Agent utilization as percentage (active / (active + idle))",
    label_names=["agent_id"],
)

# =============================================================================
# Instrumented Classes
# =============================================================================


def track_timing(metric: Histogram, component_label: str = None):
    """Decorator to track timing of a function.

    Args:
        metric: Histogram metric to record to
        component_label: Label value for the metric
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start
                if component_label:
                    metric.observe(duration, component=component_label)
                else:
                    metric.observe(duration)
        return wrapper
    return decorator


def track_agent_utilization(agent_id: str):
    """Decorator to track agent active time.

    Args:
        agent_id: ID of the agent being tracked
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start
                agent_active_time.labels(agent_id=agent_id).inc(duration)
        return wrapper
    return decorator


class InstrumentedTeamSizeClassifier:
    """TeamSizeClassifier with automatic metric recording.

    Wraps the original TeamSizeClassifier to record metrics
    for each classification operation.
    """

    def __init__(self, original_classifier=None):
        """Initialize with original classifier.

        Args:
            original_classifier: The original TeamSizeClassifier instance
        """
        self.original_classifier = original_classifier
        self._score_to_bucket_map = {
            (0.0, 0.25): "low",
            (0.25, 0.5): "medium",
            (0.5, 0.75): "high",
            (0.75, 1.0): "very_high",
        }

    def classify(self, factors: Dict[str, Any]) -> Dict[str, Any]:
        """Classify and record metrics.

        Args:
            factors: Input factors for classification

        Returns:
            Classification result with score and agent selection
        """
        # Call original classifier
        if self.original_classifier:
            result = self.original_classifier.classify(factors)
        else:
            # Mock classification if no original provided
            result = {
                "score": 0.5,
                "confidence": 0.8,
                "team_size": "small",
                "recommended_agents": ["temujin"],
            }

        # Record metrics
        if "confidence" in result:
            classification_confidence.observe(result["confidence"])

        if "score" in result:
            bucket = self._score_to_bucket(result["score"])
            classification_bucket.labels(bucket=bucket).inc()

        return result

    def _score_to_bucket(self, score: float) -> str:
        """Convert score to bucket name.

        Args:
            score: Complexity score (0.0 to 1.0)

        Returns:
            Bucket name: low, medium, high, or very_high
        """
        for (low, high), bucket in self._score_to_bucket_map.items():
            if low <= score < high:
                return bucket
        return "very_high"


class InstrumentedDelegationProtocol:
    """DelegationProtocol with timing instrumentation.

    Wraps the original DelegationProtocol to record timing
    breakdown for each delegation operation.
    """

    def __init__(self, original_protocol=None):
        """Initialize with original protocol.

        Args:
            original_protocol: The original DelegationProtocol instance
        """
        self.original_protocol = original_protocol

    async def create_delegation_task(
        self,
        title: str,
        description: str,
        agent_id: str,
        complexity_score: float = 0.5,
        **kwargs
    ) -> Dict[str, Any]:
        """Create delegation task with timing instrumentation.

        Args:
            title: Task title
            description: Task description
            agent_id: Agent to assign
            complexity_score: Complexity score
            **kwargs: Additional parameters

        Returns:
            Created task information
        """
        start = time.time()

        # Classification timing
        class_start = time.time()
        if self.original_protocol:
            classification = await self.original_protocol.classify_and_route(title, description)
        else:
            classification = {"agent_id": agent_id, "confidence": 0.8}
        class_duration = time.time() - class_start
        delegation_latency.labels(component="classification").observe(class_duration)

        # Neo4j create timing
        neo4j_start = time.time()
        if self.original_protocol:
            task = await self.original_protocol.memory.create_task(
                title=title,
                description=description,
                agent_id=agent_id,
            )
        else:
            task = {"task_id": f"task-{time.time()}"}
        neo4j_duration = time.time() - neo4j_start
        delegation_latency.labels(component="neo4j_create").observe(neo4j_duration)

        # agentToAgent delivery timing
        delivery_start = time.time()
        # Simulate delivery
        await asyncio.sleep(0.001)
        delivery_duration = time.time() - delivery_start
        delegation_latency.labels(component="agentToAgent").observe(delivery_duration)

        # Record total latency
        total_duration = time.time() - start
        task_end_to_end_latency.labels(task_type=kwargs.get("task_type", "generic")).observe(
            total_duration
        )

        return task


# =============================================================================
# Metrics Collection
# =============================================================================

def get_instrumented_metrics() -> Dict[str, Any]:
    """Get all instrumented metrics for registration.

    Returns:
        Dictionary of metric name -> metric instance
    """
    return {
        "classification_confidence": classification_confidence,
        "classification_bucket": classification_bucket,
        "routing_accuracy": routing_accuracy,
        "delegation_latency": delegation_latency,
        "task_end_to_end_latency": task_end_to_end_latency,
        "agent_active_time": agent_active_time,
        "agent_idle_time": agent_idle_time,
        "agent_utilization": agent_utilization,
    }


def register_metrics_with(registry: MetricsRegistry) -> MetricsRegistry:
    """Register all instrumented metrics with a registry.

    Args:
        registry: The MetricsRegistry to register with

    Returns:
        The same registry for chaining
    """
    for metric in get_instrumented_metrics().values():
        registry.register(metric)

    return registry


# =============================================================================
# Metrics Summary
# =============================================================================

def get_metrics_summary() -> Dict[str, Any]:
    """Get summary of all metrics being tracked.

    Returns:
        Dictionary with metric descriptions and types
    """
    return {
        "classification_metrics": {
            "classification_confidence": {
                "type": "histogram",
                "description": "Distribution of classification confidence scores",
                "buckets": [0.1, 0.3, 0.5, 0.7, 0.9, 0.95, 0.99, 1.0],
            },
            "classification_bucket": {
                "type": "counter",
                "description": "Count of classifications by complexity bucket",
                "labels": ["bucket"],
            },
            "routing_accuracy": {
                "type": "gauge",
                "description": "Percentage of correct initial agent assignments",
            },
        },
        "delegation_metrics": {
            "delegation_latency": {
                "type": "histogram",
                "description": "Delegation latency by component",
                "labels": ["component"],
                "components": ["classification", "neo4j_create", "agentToAgent", "claim"],
            },
            "task_end_to_end_latency": {
                "type": "histogram",
                "description": "End-to-end task completion latency",
                "labels": ["task_type"],
            },
        },
        "agent_utilization_metrics": {
            "agent_active_time": {
                "type": "counter",
                "description": "Time agents spend actively processing",
                "labels": ["agent_id"],
            },
            "agent_idle_time": {
                "type": "counter",
                "description": "Time agents spend available but idle",
                "labels": ["agent_id"],
            },
            "agent_utilization": {
                "type": "gauge",
                "description": "Agent utilization as percentage",
                "labels": ["agent_id"],
            },
        },
    }


# Import asyncio for async operations
import asyncio


__all__ = [
    # Metrics
    "classification_confidence",
    "classification_bucket",
    "routing_accuracy",
    "delegation_latency",
    "task_end_to_end_latency",
    "agent_active_time",
    "agent_idle_time",
    "agent_utilization",
    # Instrumented classes
    "InstrumentedTeamSizeClassifier",
    "InstrumentedDelegationProtocol",
    # Decorators
    "track_timing",
    "track_agent_utilization",
    # Utilities
    "get_instrumented_metrics",
    "register_metrics_with",
    "get_metrics_summary",
]
