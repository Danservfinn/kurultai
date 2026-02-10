#!/usr/bin/env python3
"""
Predictive Health Monitoring - Kurultai v2.0

Advanced monitoring with predictive analytics for:
- Signal daemon failure prediction
- Resource exhaustion forecasting
- Pre-emptive restart scheduling

Extends cost monitoring with ML-based predictions.

Author: Kurultai v2.0
Date: 2026-02-10
"""

import os
import sys
import json
import math
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from collections import deque
from enum import Enum

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


class HealthMetric(Enum):
    """Types of health metrics tracked."""
    CPU_USAGE = "cpu_usage"
    MEMORY_USAGE = "memory_usage"
    DISK_USAGE = "disk_usage"
    LOAD_AVERAGE = "load_average"
    NEO4J_CONNECTIONS = "neo4j_connections"
    NEO4J_QUERY_TIME = "neo4j_query_time"
    SIGNAL_DAEMON_PING = "signal_daemon_ping"
    AGENT_HEARTBEAT_LATENCY = "agent_heartbeat_latency"
    TASK_QUEUE_DEPTH = "task_queue_depth"
    ERROR_RATE = "error_rate"


class PredictedEvent(Enum):
    """Types of events that can be predicted."""
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    DAEMON_FAILURE = "daemon_failure"
    DATABASE_DEGRADATION = "database_degradation"
    AGENT_STARVATION = "agent_starvation"
    ERROR_SPIKE = "error_spike"


class AlertSeverity(Enum):
    """Severity levels for predictions."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class MetricSnapshot:
    """A single metric measurement."""
    metric: HealthMetric
    value: float
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Prediction:
    """A predictive health alert."""
    event_type: PredictedEvent
    severity: AlertSeverity
    probability: float
    predicted_time: datetime
    affected_components: List[str]
    recommendation: str
    confidence_score: float
    based_on_metrics: List[HealthMetric]
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "severity": self.severity.value,
            "probability": round(self.probability, 3),
            "predicted_time": self.predicted_time.isoformat(),
            "affected_components": self.affected_components,
            "recommendation": self.recommendation,
            "confidence_score": round(self.confidence_score, 3),
            "based_on_metrics": [m.value for m in self.based_on_metrics],
            "created_at": self.created_at.isoformat()
        }


class PredictiveHealthMonitor:
    """
    Predictive health monitoring with trend analysis and forecasting.
    
    Features:
    - Historical metric tracking and trend analysis
    - Linear regression for resource exhaustion prediction
    - Pattern matching for daemon failure prediction
    - Pre-emptive action recommendations
    - Cost/resource tracking with predictive budgeting
    """
    
    def __init__(self, driver, history_window_hours: int = 24):
        self.driver = driver
        self.history_window = timedelta(hours=history_window_hours)
        self.metric_history: Dict[HealthMetric, deque] = {
            metric: deque(maxlen=1000) for metric in HealthMetric
        }
        self.predictions: List[Prediction] = []
        self.cost_history: deque = deque(maxlen=1000)
        
        # Configuration
        self.prediction_threshold = 0.7  # Probability threshold for alerts
        self.critical_threshold = 0.85  # Critical alert threshold
        self.min_data_points = 10  # Minimum data points for prediction
        
        # Resource thresholds for exhaustion prediction
        self.resource_thresholds = {
            HealthMetric.CPU_USAGE: 85.0,
            HealthMetric.MEMORY_USAGE: 90.0,
            HealthMetric.DISK_USAGE: 85.0,
            HealthMetric.LOAD_AVERAGE: 10.0,  # Per CPU
        }
    
    def record_metric(self, metric: HealthMetric, value: float, metadata: Optional[Dict] = None) -> None:
        """Record a metric measurement."""
        snapshot = MetricSnapshot(
            metric=metric,
            value=value,
            timestamp=datetime.now(),
            metadata=metadata or {}
        )
        self.metric_history[metric].append(snapshot)
        
        # Also persist to Neo4j for long-term storage
        self._persist_metric(snapshot)
    
    def _persist_metric(self, snapshot: MetricSnapshot) -> None:
        """Persist metric to Neo4j."""
        try:
            with self.driver.session() as session:
                session.run('''
                    CREATE (m:HealthMetric {
                        metric_type: $metric_type,
                        value: $value,
                        timestamp: datetime($timestamp),
                        metadata: $metadata
                    })
                ''',
                    metric_type=snapshot.metric.value,
                    value=snapshot.value,
                    timestamp=snapshot.timestamp.isoformat(),
                    metadata=json.dumps(snapshot.metadata)
                )
        except Exception:
            pass  # Don't let persistence failures break monitoring
    
    def record_cost(self, tokens: int, cost_usd: float, task_name: str) -> None:
        """Record cost metrics."""
        self.cost_history.append({
            "tokens": tokens,
            "cost_usd": cost_usd,
            "task_name": task_name,
            "timestamp": datetime.now()
        })
    
    def get_metric_trend(self, metric: HealthMetric, minutes: int = 60) -> Dict[str, Any]:
        """
        Calculate trend for a metric over time.
        
        Returns trend analysis including slope, direction, and volatility.
        """
        cutoff = datetime.now() - timedelta(minutes=minutes)
        values = [
            (s.timestamp, s.value) 
            for s in self.metric_history[metric] 
            if s.timestamp > cutoff
        ]
        
        if len(values) < self.min_data_points:
            return {"status": "insufficient_data", "points": len(values)}
        
        # Calculate linear regression
        n = len(values)
        timestamps = [(v[0] - values[0][0]).total_seconds() / 60 for v in values]  # minutes
        metric_values = [v[1] for v in values]
        
        sum_x = sum(timestamps)
        sum_y = sum(metric_values)
        sum_xy = sum(x * y for x, y in zip(timestamps, metric_values))
        sum_x2 = sum(x * x for x in timestamps)
        
        # Slope in units per minute
        if sum_x2 * n - sum_x * sum_x == 0:
            slope = 0
        else:
            slope = (sum_xy * n - sum_x * sum_y) / (sum_x2 * n - sum_x * sum_x)
        
        # Calculate volatility (standard deviation)
        mean = sum_y / n
        variance = sum((y - mean) ** 2 for y in metric_values) / n
        volatility = math.sqrt(variance)
        
        # Determine direction
        if abs(slope) < 0.01:
            direction = "stable"
        elif slope > 0:
            direction = "increasing"
        else:
            direction = "decreasing"
        
        # Current value
        current_value = metric_values[-1]
        
        return {
            "current_value": round(current_value, 2),
            "slope_per_minute": round(slope, 4),
            "direction": direction,
            "volatility": round(volatility, 2),
            "data_points": n,
            "time_window_minutes": minutes
        }
    
    def predict_resource_exhaustion(self, metric: HealthMetric) -> Optional[Prediction]:
        """
        Predict when a resource will be exhausted based on current trend.
        
        Uses linear extrapolation to estimate time until threshold breach.
        """
        trend = self.get_metric_trend(metric, minutes=30)
        
        if trend.get("status") == "insufficient_data":
            return None
        
        threshold = self.resource_thresholds.get(metric)
        if not threshold:
            return None
        
        current_value = trend["current_value"]
        slope = trend["slope_per_minute"]
        
        # If stable or decreasing, no prediction needed
        if trend["direction"] != "increasing":
            return None
        
        # Calculate time to threshold
        if slope <= 0:
            return None
        
        remaining = threshold - current_value
        minutes_until_exhaustion = remaining / slope
        
        # Only predict if within reasonable time window (5 min to 4 hours)
        if minutes_until_exhaustion < 5 or minutes_until_exhaustion > 240:
            return None
        
        # Calculate probability based on trend volatility
        # Higher volatility = lower confidence
        volatility_factor = 1.0 - min(trend["volatility"] / 50, 0.5)
        probability = 0.7 * volatility_factor
        
        predicted_time = datetime.now() + timedelta(minutes=minutes_until_exhaustion)
        
        return Prediction(
            event_type=PredictedEvent.RESOURCE_EXHAUSTION,
            severity=AlertSeverity.CRITICAL if minutes_until_exhaustion < 30 else AlertSeverity.WARNING,
            probability=probability,
            predicted_time=predicted_time,
            affected_components=[metric.value],
            recommendation=f"Pre-emptive action: Scale up {metric.value} or reduce load. Predicted exhaustion in {int(minutes_until_exhaustion)} minutes.",
            confidence_score=volatility_factor,
            based_on_metrics=[metric]
        )
    
    def predict_daemon_failure(self) -> Optional[Prediction]:
        """
        Predict Signal daemon failure based on heartbeat patterns.
        
        Looks for:
        - Increasing latency
        - Missed heartbeats
        - Error rate spikes
        """
        # Check signal daemon ping
        ping_trend = self.get_metric_trend(HealthMetric.SIGNAL_DAEMON_PING, minutes=15)
        latency_trend = self.get_metric_trend(HealthMetric.AGENT_HEARTBEAT_LATENCY, minutes=15)
        
        if ping_trend.get("status") == "insufficient_data":
            return None
        
        risk_factors = 0
        total_factors = 0
        
        # Factor 1: Increasing ping latency
        if ping_trend["direction"] == "increasing" and ping_trend["current_value"] > 100:
            risk_factors += 1
        total_factors += 1
        
        # Factor 2: High agent heartbeat latency
        if latency_trend.get("status") != "insufficient_data":
            if latency_trend["direction"] == "increasing" and latency_trend["current_value"] > 5:
                risk_factors += 1
            total_factors += 1
        
        # Factor 3: Recent error rate
        error_trend = self.get_metric_trend(HealthMetric.ERROR_RATE, minutes=10)
        if error_trend.get("status") != "insufficient_data":
            if error_trend["current_value"] > 0.1:  # > 10% error rate
                risk_factors += 1
            total_factors += 1
        
        if total_factors == 0:
            return None
        
        probability = risk_factors / total_factors
        
        if probability < self.prediction_threshold:
            return None
        
        # Estimate time to failure based on degradation rate
        if ping_trend["direction"] == "increasing":
            # If ping latency increasing, estimate failure when it exceeds 5s
            if ping_trend["slope_per_minute"] > 0:
                remaining = (5000 - ping_trend["current_value"]) / ping_trend["slope_per_minute"]
                minutes_until_failure = max(5, min(remaining, 60))
            else:
                minutes_until_failure = 30
        else:
            minutes_until_failure = 30
        
        predicted_time = datetime.now() + timedelta(minutes=minutes_until_failure)
        
        return Prediction(
            event_type=PredictedEvent.DAEMON_FAILURE,
            severity=AlertSeverity.CRITICAL if probability > self.critical_threshold else AlertSeverity.WARNING,
            probability=probability,
            predicted_time=predicted_time,
            affected_components=["signal_daemon", "agent_communication"],
            recommendation=f"Pre-emptive restart recommended: Signal daemon showing degradation. Schedule restart in {int(minutes_until_failure)} minutes or during next maintenance window.",
            confidence_score=probability * 0.9,
            based_on_metrics=[HealthMetric.SIGNAL_DAEMON_PING, HealthMetric.AGENT_HEARTBEAT_LATENCY]
        )
    
    def predict_database_degradation(self) -> Optional[Prediction]:
        """Predict Neo4j database degradation."""
        query_trend = self.get_metric_trend(HealthMetric.NEO4J_QUERY_TIME, minutes=30)
        connection_trend = self.get_metric_trend(HealthMetric.NEO4J_CONNECTIONS, minutes=30)
        
        if query_trend.get("status") == "insufficient_data":
            return None
        
        # Check for query time degradation
        if query_trend["direction"] == "increasing" and query_trend["current_value"] > 500:
            probability = 0.6 + (query_trend["current_value"] - 500) / 2000
            probability = min(0.95, probability)
            
            predicted_time = datetime.now() + timedelta(minutes=45)
            
            return Prediction(
                event_type=PredictedEvent.DATABASE_DEGRADATION,
                severity=AlertSeverity.WARNING,
                probability=probability,
                predicted_time=predicted_time,
                affected_components=["neo4j", "query_performance"],
                recommendation="Consider connection pool tuning or query optimization. Current query time trending upward.",
                confidence_score=0.75,
                based_on_metrics=[HealthMetric.NEO4J_QUERY_TIME]
            )
        
        return None
    
    def predict_error_spike(self) -> Optional[Prediction]:
        """Predict upcoming error spike based on current error rate trend."""
        error_trend = self.get_metric_trend(HealthMetric.ERROR_RATE, minutes=15)
        
        if error_trend.get("status") == "insufficient_data":
            return None
        
        current_rate = error_trend["current_value"]
        
        # If error rate is increasing and above 5%
        if error_trend["direction"] == "increasing" and current_rate > 0.05:
            probability = min(0.9, current_rate * 3)  # Scale probability with error rate
            
            predicted_time = datetime.now() + timedelta(minutes=20)
            
            return Prediction(
                event_type=PredictedEvent.ERROR_SPIKE,
                severity=AlertSeverity.WARNING if current_rate < 0.15 else AlertSeverity.CRITICAL,
                probability=probability,
                predicted_time=predicted_time,
                affected_components=["task_execution", "agent_performance"],
                recommendation=f"Error rate trending upward ({current_rate:.1%}). Investigate recent changes or restart affected agents.",
                confidence_score=0.8,
                based_on_metrics=[HealthMetric.ERROR_RATE]
            )
        
        return None
    
    def run_all_predictions(self) -> List[Prediction]:
        """Run all prediction models and return alerts."""
        predictions = []
        
        # Resource exhaustion predictions
        for metric in [HealthMetric.CPU_USAGE, HealthMetric.MEMORY_USAGE, HealthMetric.DISK_USAGE]:
            pred = self.predict_resource_exhaustion(metric)
            if pred:
                predictions.append(pred)
        
        # Daemon failure prediction
        pred = self.predict_daemon_failure()
        if pred:
            predictions.append(pred)
        
        # Database degradation
        pred = self.predict_database_degradation()
        if pred:
            predictions.append(pred)
        
        # Error spike prediction
        pred = self.predict_error_spike()
        if pred:
            predictions.append(pred)
        
        # Filter by threshold and sort by severity
        predictions = [
            p for p in predictions 
            if p.probability >= self.prediction_threshold
        ]
        
        severity_order = {AlertSeverity.CRITICAL: 0, AlertSeverity.WARNING: 1, AlertSeverity.INFO: 2}
        predictions.sort(key=lambda p: (severity_order[p.severity], -p.probability))
        
        # Store predictions
        self.predictions = predictions
        
        # Persist critical predictions
        for pred in predictions:
            if pred.severity == AlertSeverity.CRITICAL:
                self._persist_prediction(pred)
        
        return predictions
    
    def _persist_prediction(self, prediction: Prediction) -> None:
        """Persist prediction to Neo4j."""
        try:
            with self.driver.session() as session:
                session.run('''
                    CREATE (p:Prediction {
                        event_type: $event_type,
                        severity: $severity,
                        probability: $probability,
                        predicted_time: datetime($predicted_time),
                        recommendation: $recommendation,
                        confidence_score: $confidence,
                        created_at: datetime(),
                        status: 'active'
                    })
                ''',
                    event_type=prediction.event_type.value,
                    severity=prediction.severity.value,
                    probability=prediction.probability,
                    predicted_time=prediction.predicted_time.isoformat(),
                    recommendation=prediction.recommendation,
                    confidence=prediction.confidence_score
                )
        except Exception:
            pass
    
    def get_preemptive_recommendations(self) -> List[Dict[str, Any]]:
        """Get list of pre-emptive actions recommended based on predictions."""
        recommendations = []
        
        for pred in self.predictions:
            if pred.probability >= self.critical_threshold:
                recommendations.append({
                    "priority": "immediate",
                    "action": pred.recommendation,
                    "event_type": pred.event_type.value,
                    "predicted_in_minutes": int((pred.predicted_time - datetime.now()).total_seconds() / 60)
                })
            elif pred.probability >= self.prediction_threshold:
                recommendations.append({
                    "priority": "planned",
                    "action": pred.recommendation,
                    "event_type": pred.event_type.value,
                    "predicted_in_minutes": int((pred.predicted_time - datetime.now()).total_seconds() / 60)
                })
        
        return recommendations
    
    def get_cost_forecast(self, hours_ahead: int = 24) -> Dict[str, Any]:
        """Forecast costs for the next N hours based on recent history."""
        if len(self.cost_history) < 10:
            return {"status": "insufficient_data"}
        
        # Calculate hourly rate from recent history
        recent_costs = list(self.cost_history)[-100:]
        total_cost = sum(c["cost_usd"] for c in recent_costs)
        time_span = (recent_costs[-1]["timestamp"] - recent_costs[0]["timestamp"]).total_seconds() / 3600
        
        if time_span < 0.1:
            return {"status": "insufficient_time_span"}
        
        hourly_rate = total_cost / time_span
        projected_cost = hourly_rate * hours_ahead
        
        # Calculate trend
        if len(recent_costs) >= 20:
            first_half = sum(c["cost_usd"] for c in recent_costs[:len(recent_costs)//2])
            second_half = sum(c["cost_usd"] for c in recent_costs[len(recent_costs)//2:])
            
            if first_half > 0:
                trend = (second_half - first_half) / first_half
            else:
                trend = 0
        else:
            trend = 0
        
        return {
            "current_hourly_rate": round(hourly_rate, 4),
            "projected_cost_24h": round(projected_cost, 2),
            "trend": "increasing" if trend > 0.1 else "decreasing" if trend < -0.1 else "stable",
            "trend_factor": round(trend, 2),
            "confidence": "medium" if len(recent_costs) > 50 else "low"
        }
    
    def get_health_dashboard(self) -> Dict[str, Any]:
        """Get comprehensive health dashboard data."""
        dashboard = {
            "timestamp": datetime.now().isoformat(),
            "current_metrics": {},
            "trends": {},
            "predictions": [p.to_dict() for p in self.predictions],
            "recommendations": self.get_preemptive_recommendations(),
            "cost_forecast": self.get_cost_forecast()
        }
        
        # Current values
        for metric in HealthMetric:
            history = self.metric_history[metric]
            if history:
                dashboard["current_metrics"][metric.value] = {
                    "current": round(list(history)[-1].value, 2),
                    "unit": self._get_metric_unit(metric)
                }
        
        # Trends for key metrics
        for metric in [HealthMetric.CPU_USAGE, HealthMetric.MEMORY_USAGE, HealthMetric.ERROR_RATE]:
            dashboard["trends"][metric.value] = self.get_metric_trend(metric, minutes=30)
        
        return dashboard
    
    def _get_metric_unit(self, metric: HealthMetric) -> str:
        """Get unit for a metric."""
        units = {
            HealthMetric.CPU_USAGE: "%",
            HealthMetric.MEMORY_USAGE: "%",
            HealthMetric.DISK_USAGE: "%",
            HealthMetric.LOAD_AVERAGE: "",
            HealthMetric.NEO4J_QUERY_TIME: "ms",
            HealthMetric.SIGNAL_DAEMON_PING: "ms",
            HealthMetric.AGENT_HEARTBEAT_LATENCY: "s",
            HealthMetric.TASK_QUEUE_DEPTH: "tasks",
            HealthMetric.ERROR_RATE: "%",
        }
        return units.get(metric, "")
    
    def schedule_preemptive_restart(self, component: str, window_minutes: int = 30) -> Dict[str, Any]:
        """Schedule a pre-emptive restart for a component."""
        scheduled_time = datetime.now() + timedelta(minutes=window_minutes)
        
        # Persist to Neo4j
        with self.driver.session() as session:
            session.run('''
                CREATE (r:PreemptiveAction {
                    id: $id,
                    action_type: 'restart',
                    component: $component,
                    scheduled_at: datetime($scheduled_time),
                    reason: $reason,
                    status: 'scheduled',
                    created_at: datetime()
                })
            ''',
                id=f"restart_{component}_{int(datetime.now().timestamp())}",
                component=component,
                scheduled_time=scheduled_time.isoformat(),
                reason=f"Pre-emptive restart based on predictive health monitoring"
            )
        
        return {
            "component": component,
            "scheduled_at": scheduled_time.isoformat(),
            "window_minutes": window_minutes,
            "status": "scheduled"
        }


# Global instance
_monitor: Optional[PredictiveHealthMonitor] = None


def get_health_monitor(driver) -> PredictiveHealthMonitor:
    """Get or create global health monitor instance."""
    global _monitor
    if _monitor is None:
        _monitor = PredictiveHealthMonitor(driver)
    return _monitor


def reset_health_monitor():
    """Reset global instance (for testing)."""
    global _monitor
    _monitor = None


# Standalone execution
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Predictive Health Monitor")
    parser.add_argument("--predict", action="store_true", help="Run all predictions")
    parser.add_argument("--dashboard", action="store_true", help="Show health dashboard")
    
    args = parser.parse_args()
    
    from neo4j import GraphDatabase
    
    uri = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
    password = os.environ.get('NEO4J_PASSWORD')
    
    if not password:
        print("NEO4J_PASSWORD not set")
        sys.exit(1)
    
    driver = GraphDatabase.driver(uri, auth=('neo4j', password))
    monitor = get_health_monitor(driver)
    
    if args.predict:
        predictions = monitor.run_all_predictions()
        print(json.dumps([p.to_dict() for p in predictions], indent=2))
    elif args.dashboard:
        print(json.dumps(monitor.get_health_dashboard(), indent=2))
    else:
        parser.print_help()
    
    driver.close()
