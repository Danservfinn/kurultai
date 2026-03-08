#!/usr/bin/env python3
"""
Canary Deployment Manager for Kurultai Experiments

Provides canary deployment with health monitoring, automatic rollback
on error rate spike, and gradual traffic scaling.

Usage:
    from canary_deploy import CanaryDeployer

    deployer = CanaryDeployer()
    deployer.start_canary("exp-20260308-001")
    # ... wait 10 minutes ...
    status = deployer.check_canary_health("exp-20260308-001")
    if status.healthy:
        deployer.promote_to_full("exp-20260308-001")
    else:
        deployer.rollback_canary("exp-20260308-001", "error_rate_spike")
"""

import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional

# Paths
CANARY_STATE_PATH = Path(__file__).parent.parent.parent / "config" / "canary_state.json"
EXPERIMENTS_PATH = Path(__file__).parent.parent.parent / "experiments"


class CanaryStatus(Enum):
    """Status of a canary deployment."""
    NONE = "none"  # No canary running
    STARTING = "starting"  # Canary starting up
    RUNNING = "running"  # Canary at partial traffic
    HEALTHY = "healthy"  # Canary healthy, ready for promotion
    UNHEALTHY = "unhealthy"  # Canary unhealthy, needs rollback
    PROMOTED = "promoted"  # Canary promoted to full traffic
    ROLLED_BACK = "rolled_back"  # Canary rolled back


@dataclass
class CanaryMetrics:
    """Metrics collected during canary deployment."""
    error_rate: float = 0.0
    latency_p50_ms: float = 0.0
    latency_p99_ms: float = 0.0
    success_count: int = 0
    error_count: int = 0
    total_requests: int = 0
    collected_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class CanaryState:
    """State of a canary deployment."""
    experiment_id: str
    status: CanaryStatus = CanaryStatus.NONE
    traffic_pct: int = 0  # 0-100
    started_at: Optional[str] = None
    baseline_metrics: Optional[CanaryMetrics] = None
    current_metrics: Optional[CanaryMetrics] = None
    rollback_on_error_rate: float = 2.0
    rollback_reason: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "experiment_id": self.experiment_id,
            "status": self.status.value,
            "traffic_pct": self.traffic_pct,
            "started_at": self.started_at,
            "baseline_metrics": self.baseline_metrics.__dict__ if self.baseline_metrics else None,
            "current_metrics": self.current_metrics.__dict__ if self.current_metrics else None,
            "rollback_on_error_rate": self.rollback_on_error_rate,
            "rollback_reason": self.rollback_reason,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CanaryState":
        state = cls(
            experiment_id=data["experiment_id"],
            status=CanaryStatus(data.get("status", "none")),
            traffic_pct=data.get("traffic_pct", 0),
            started_at=data.get("started_at"),
            rollback_on_error_rate=data.get("rollback_on_error_rate", 2.0),
            rollback_reason=data.get("rollback_reason"),
        )
        if data.get("baseline_metrics"):
            state.baseline_metrics = CanaryMetrics(**data["baseline_metrics"])
        if data.get("current_metrics"):
            state.current_metrics = CanaryMetrics(**data["current_metrics"])
        return state


class CanaryDeployer:
    """
    Manages canary deployments for experiments.

    Canary deployment flow:
    1. start_canary() - Deploy to 5% traffic
    2. check_canary_health() - Check metrics after observation period
    3. promote_to_full() or rollback_canary() - Based on health check
    """

    CANARY_INITIAL_PCT = 5  # Start at 5% traffic
    CANARY_OBSERVATION_MINUTES = 10  # Observe for 10 minutes
    HEALTH_CHECK_INTERVAL_SECONDS = 60  # Check health every minute

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or CANARY_STATE_PATH
        self._states: dict[str, CanaryState] = {}
        self._load_states()

    def _load_states(self) -> None:
        """Load canary states from disk."""
        if self.config_path.exists():
            try:
                with open(self.config_path) as f:
                    data = json.load(f)
                self._states = {
                    exp_id: CanaryState.from_dict(state_data)
                    for exp_id, state_data in data.items()
                }
            except (json.JSONDecodeError, KeyError):
                self._states = {}

    def _save_states(self) -> None:
        """Persist canary states to disk."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        data = {exp_id: state.to_dict() for exp_id, state in self._states.items()}
        with open(self.config_path, "w") as f:
            json.dump(data, f, indent=2)

    def _collect_metrics(self) -> CanaryMetrics:
        """
        Collect current system metrics.

        In production, this would query:
        - Task error rates from Neo4j/ledger
        - Latency from logs
        - Success/failure counts

        Returns simulated metrics for now.
        """
        # TODO: Integrate with actual metrics sources
        # For now, return baseline metrics
        return CanaryMetrics(
            error_rate=0.05,  # 5% baseline error rate
            latency_p50_ms=150.0,
            latency_p99_ms=500.0,
            success_count=95,
            error_count=5,
            total_requests=100,
        )

    def _get_baseline_metrics(self) -> CanaryMetrics:
        """Get baseline metrics before canary deployment."""
        return self._collect_metrics()

    def start_canary(self, experiment_id: str) -> bool:
        """
        Start a canary deployment at 5% traffic.

        Args:
            experiment_id: Unique identifier for the experiment

        Returns:
            True if canary started successfully
        """
        # Check if canary already running for this experiment
        if experiment_id in self._states:
            existing = self._states[experiment_id]
            if existing.status in (CanaryStatus.RUNNING, CanaryStatus.STARTING):
                return False  # Already running

        # Collect baseline metrics before deployment
        baseline = self._get_baseline_metrics()

        # Create new canary state
        state = CanaryState(
            experiment_id=experiment_id,
            status=CanaryStatus.STARTING,
            traffic_pct=self.CANARY_INITIAL_PCT,
            started_at=datetime.utcnow().isoformat(),
            baseline_metrics=baseline,
            rollback_on_error_rate=2.0,
        )

        self._states[experiment_id] = state
        self._save_states()

        # Log canary start
        self._log_canary_event(experiment_id, "canary_started", {
            "initial_traffic_pct": self.CANARY_INITIAL_PCT,
            "baseline_error_rate": baseline.error_rate,
        })

        # Transition to running after a brief period
        state.status = CanaryStatus.RUNNING
        self._save_states()

        return True

    def check_canary_health(self, experiment_id: str) -> CanaryState:
        """
        Check health of canary deployment.

        Compares current metrics against baseline:
        - Error rate must be < rollback_on_error_rate * baseline
        - Latency must not spike > 50% above baseline

        Args:
            experiment_id: The experiment to check

        Returns:
            CanaryState with updated status and metrics
        """
        if experiment_id not in self._states:
            return CanaryState(experiment_id=experiment_id, status=CanaryStatus.NONE)

        state = self._states[experiment_id]

        if state.status not in (CanaryStatus.RUNNING, CanaryStatus.STARTING):
            return state

        # Collect current metrics
        current = self._collect_metrics()
        state.current_metrics = current

        # Check if observation period elapsed
        if state.started_at:
            started = datetime.fromisoformat(state.started_at)
            elapsed = datetime.utcnow() - started
            if elapsed < timedelta(minutes=self.CANARY_OBSERVATION_MINUTES):
                # Still in observation period
                self._save_states()
                return state

        # Health checks
        baseline = state.baseline_metrics
        if baseline is None:
            # No baseline, assume healthy
            state.status = CanaryStatus.HEALTHY
            self._save_states()
            return state

        # Error rate check
        error_rate_threshold = baseline.error_rate * state.rollback_on_error_rate
        if current.error_rate > error_rate_threshold:
            state.status = CanaryStatus.UNHEALTHY
            state.rollback_reason = f"error_rate_{current.error_rate:.2f}_threshold_{error_rate_threshold:.2f}"
            self._save_states()
            self._log_canary_event(experiment_id, "canary_unhealthy", {
                "reason": state.rollback_reason,
                "current_error_rate": current.error_rate,
                "threshold": error_rate_threshold,
            })
            return state

        # Latency check (P99)
        latency_threshold = baseline.latency_p99_ms * 1.5
        if current.latency_p99_ms > latency_threshold:
            state.status = CanaryStatus.UNHEALTHY
            state.rollback_reason = f"latency_spike_{current.latency_p99_ms:.0f}ms"
            self._save_states()
            self._log_canary_event(experiment_id, "canary_unhealthy", {
                "reason": state.rollback_reason,
                "current_latency_p99": current.latency_p99_ms,
                "threshold": latency_threshold,
            })
            return state

        # All checks passed
        state.status = CanaryStatus.HEALTHY
        self._save_states()
        self._log_canary_event(experiment_id, "canary_healthy", {
            "current_error_rate": current.error_rate,
            "current_latency_p99": current.latency_p99_ms,
        })

        return state

    def promote_to_full(self, experiment_id: str) -> bool:
        """
        Promote canary to 100% traffic.

        Args:
            experiment_id: The experiment to promote

        Returns:
            True if promotion succeeded
        """
        if experiment_id not in self._states:
            return False

        state = self._states[experiment_id]

        if state.status not in (CanaryStatus.RUNNING, CanaryStatus.HEALTHY):
            return False

        # Scale to 100%
        state.traffic_pct = 100
        state.status = CanaryStatus.PROMOTED
        self._save_states()

        self._log_canary_event(experiment_id, "canary_promoted", {
            "final_traffic_pct": 100,
        })

        return True

    def rollback_canary(self, experiment_id: str, reason: str) -> bool:
        """
        Instantly rollback a canary deployment.

        Args:
            experiment_id: The experiment to rollback
            reason: Human-readable reason for rollback

        Returns:
            True if rollback succeeded
        """
        if experiment_id not in self._states:
            return False

        state = self._states[experiment_id]

        # Set traffic to 0
        state.traffic_pct = 0
        state.status = CanaryStatus.ROLLED_BACK
        state.rollback_reason = reason
        self._save_states()

        # Trigger feature flag rollback
        try:
            from feature_flags import rollback_rollout
            rollback_rollout(f"experiment-{experiment_id}")
        except ImportError:
            pass  # Feature flags not available

        # Alert humans
        self._send_rollback_alert(experiment_id, reason)

        self._log_canary_event(experiment_id, "canary_rolled_back", {
            "reason": reason,
        })

        return True

    def get_canary_status(self, experiment_id: str) -> Optional[CanaryState]:
        """Get current canary status for an experiment."""
        return self._states.get(experiment_id)

    def list_active_canaries(self) -> list[CanaryState]:
        """List all active canary deployments."""
        return [
            state for state in self._states.values()
            if state.status in (CanaryStatus.RUNNING, CanaryStatus.STARTING)
        ]

    def _log_canary_event(self, experiment_id: str, event: str, data: dict) -> None:
        """Log canary event to experiment ledger."""
        EXPERIMENTS_PATH.mkdir(parents=True, exist_ok=True)
        ledger_path = EXPERIMENTS_PATH / "canary_events.jsonl"

        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "experiment_id": experiment_id,
            "event": event,
            **data,
        }

        with open(ledger_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def _send_rollback_alert(self, experiment_id: str, reason: str) -> None:
        """Send rollback alert via Signal."""
        try:
            # Try to use Signal notification if available
            from signal_notifier import send_signal_message
            send_signal_message(
                f"CANARY ROLLBACK: {experiment_id}\nReason: {reason}\nAction required: Check experiment logs."
            )
        except ImportError:
            # Fallback to logging
            print(f"[ALERT] Canary rollback: {experiment_id} - {reason}")


def run_canary_monitor_loop(interval_seconds: int = 60) -> None:
    """
    Run continuous canary health monitoring loop.

    Checks all active canaries and rolls back unhealthy ones.
    """
    deployer = CanaryDeployer()

    print(f"Starting canary monitor loop (interval: {interval_seconds}s)")

    while True:
        active_canaries = deployer.list_active_canaries()

        for state in active_canaries:
            print(f"Checking canary: {state.experiment_id}")

            result = deployer.check_canary_health(state.experiment_id)

            if result.status == CanaryStatus.UNHEALTHY:
                print(f"  UNHEALTHY - Rolling back: {result.rollback_reason}")
                deployer.rollback_canary(state.experiment_id, result.rollback_reason or "health_check_failed")
            elif result.status == CanaryStatus.HEALTHY:
                print(f"  HEALTHY - Ready for promotion")
            else:
                print(f"  {result.status.value}")

        time.sleep(interval_seconds)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "monitor":
        # Run monitoring loop
        run_canary_monitor_loop()
    else:
        # Demo
        print("Canary Deployer Demo")
        print("=" * 50)

        deployer = CanaryDeployer()

        # Start a canary
        exp_id = "exp-demo-001"
        print(f"\nStarting canary for {exp_id}...")
        deployer.start_canary(exp_id)

        # Check status
        status = deployer.get_canary_status(exp_id)
        if status:
            print(f"Status: {status.status.value}")
            print(f"Traffic: {status.traffic_pct}%")
            print(f"Started: {status.started_at}")

        # Check health (simulated)
        print("\nChecking canary health...")
        result = deployer.check_canary_health(exp_id)
        print(f"Health check result: {result.status.value}")

        # Promote
        print("\nPromoting to full traffic...")
        deployer.promote_to_full(exp_id)
        status = deployer.get_canary_status(exp_id)
        if status:
            print(f"Final status: {status.status.value}")
            print(f"Final traffic: {status.traffic_pct}%")