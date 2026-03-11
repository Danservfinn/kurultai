#!/usr/bin/env python3
"""
Evaluation Engine for Kurultai Autonomous Experiments

Evaluates experiment results against baseline metrics to decide:
- MERGE: Improvement meets thresholds
- DISCARD: Regression or no significant change
- CRASH: Experiment failed to complete

Usage:
    from evaluation_engine import EvaluationEngine, Experiment, Decision

    engine = EvaluationEngine()
    experiment = Experiment(
        id="exp-20260308-001",
        agent="temujin",
        hypothesis="Router scorer LR tuning improves success rate",
        start_time=datetime(2026, 3, 8, 10, 0),
        end_time=datetime(2026, 3, 8, 14, 0),
        branch="experiment/temujin/exp-20260308-001/router-lr-tuning"
    )
    decision = engine.evaluate(experiment)
    print(decision.status)  # "merged", "discarded", or "crashed"
"""

import os
import sys
import csv
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any, Literal
from pathlib import Path
import logging

# Add script directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kurultai_paths import AGENTS_DIR, OPENCLAW_DIR

# Try to import Neo4j dependency
try:
    from neo4j_task_tracker import get_driver
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False
    logging.warning("neo4j_task_tracker not available - using mock data")

# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class Experiment:
    """Experiment metadata and state."""
    id: str
    agent: str
    hypothesis: str
    start_time: datetime
    end_time: Optional[datetime] = None
    branch: str = ""
    status: Literal["pending", "running", "completed", "merged", "discarded", "crashed"] = "running"
    commit_hash: str = ""
    baseline_metric: float = 0.0  # Pre-computed baseline
    result_metric: Optional[float] = None  # Will be computed

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "agent": self.agent,
            "hypothesis": self.hypothesis,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "branch": self.branch,
            "status": self.status,
            "commit_hash": self.commit_hash,
            "baseline_metric": self.baseline_metric,
            "result_metric": self.result_metric
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Experiment":
        return cls(
            id=data["id"],
            agent=data["agent"],
            hypothesis=data["hypothesis"],
            start_time=datetime.fromisoformat(data["start_time"]) if isinstance(data["start_time"], str) else data["start_time"],
            end_time=datetime.fromisoformat(data["end_time"]) if data.get("end_time") else None,
            branch=data.get("branch", ""),
            status=data.get("status", "running"),
            commit_hash=data.get("commit_hash", ""),
            baseline_metric=data.get("baseline_metric", 0.0),
            result_metric=data.get("result_metric")
        )


@dataclass
class MetricSnapshot:
    """Snapshot of metrics at a point in time."""
    timestamp: datetime
    agent: str
    success_rate: float
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    error_rate: float
    duration_p95: Optional[float] = None  # 95th percentile task duration in seconds
    quality_score_avg: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Decision:
    """Evaluation decision with full reasoning."""
    status: Literal["merged", "discarded", "crashed"]
    improvement_pct: float
    baseline_metric: float
    result_metric: float
    reasoning: str
    confidence: float  # 0.0 - 1.0
    metrics_compared: Dict[str, Any] = field(default_factory=dict)
    evaluated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "improvement_pct": round(self.improvement_pct, 2),
            "baseline_metric": round(self.baseline_metric, 4),
            "result_metric": round(self.result_metric, 4),
            "reasoning": self.reasoning,
            "confidence": round(self.confidence, 3),
            "metrics_compared": self.metrics_compared,
            "evaluated_at": self.evaluated_at.isoformat()
        }

    def __str__(self) -> str:
        return (
            f"Decision: {self.status.upper()}\n"
            f"  Improvement: {self.improvement_pct:+.1f}%\n"
            f"  Baseline: {self.baseline_metric:.2%} → Result: {self.result_metric:.2%}\n"
            f"  Confidence: {self.confidence:.1%}\n"
            f"  Reasoning: {self.reasoning}"
        )


# =============================================================================
# CONFIGURATION
# =============================================================================

# Decision thresholds (configurable)
MERGE_THRESHOLD_IMPROVEMENT = 0.05  # 5% improvement
MERGE_THRESHOLD_DURATION_REDUCTION = 0.10  # 10% duration reduction
DISCARD_THRESHOLD_REGRESSION = -0.05  # 5% regression
DISCARD_THRESHOLD_ERROR_MULTIPLIER = 2.0  # 2x error rate

# Ledger path for experiment evaluations
EXPERIMENT_LEDGER = OPENCLAW_DIR / "experiments" / "experiment-ledger.tsv"


# =============================================================================
# EVALUATION ENGINE
# =============================================================================

class EvaluationEngine:
    """
    Evaluates experiments against baseline metrics.

    Uses Neo4j TaskTracker data to calculate:
    - Success rate during experiment window
    - Comparison against 7-day rolling average
    - Error rate changes
    - Duration P95 changes
    """

    def __init__(self, driver=None):
        """
        Initialize the evaluation engine.

        Args:
            driver: Neo4j driver (optional, will use get_driver() if not provided)
        """
        self.driver = driver or (get_driver() if NEO4J_AVAILABLE else None)
        self._ledger_path = EXPERIMENT_LEDGER
        self._ensure_ledger_exists()

    def close(self):
        """Close Neo4j driver if we created it."""
        if self.driver and NEO4J_AVAILABLE:
            self.driver.close()

    def _ensure_ledger_exists(self):
        """Create the ledger directory and file if they don't exist."""
        self._ledger_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._ledger_path.exists():
            with open(self._ledger_path, 'w') as f:
                writer = csv.writer(f, delimiter='\t')
                writer.writerow([
                    'experiment_id', 'agent', 'status', 'improvement_pct',
                    'baseline_metric', 'result_metric', 'reasoning', 'confidence',
                    'evaluated_at', 'branch', 'commit_hash'
                ])

    def _log_to_ledger(self, experiment: Experiment, decision: Decision):
        """Log evaluation decision to the experiment ledger."""
        try:
            with open(self._ledger_path, 'a') as f:
                writer = csv.writer(f, delimiter='\t')
                writer.writerow([
                    experiment.id,
                    experiment.agent,
                    decision.status,
                    f"{decision.improvement_pct:.2f}",
                    f"{decision.baseline_metric:.4f}",
                    f"{decision.result_metric:.4f}",
                    decision.reasoning,
                    f"{decision.confidence:.3f}",
                    decision.evaluated_at.isoformat(),
                    experiment.branch,
                    experiment.commit_hash
                ])
        except Exception as e:
            logging.warning(f"Failed to log to ledger: {e}")

    def get_baseline_metric(self, agent: str, days: int = 7) -> float:
        """
        Get rolling average success rate for an agent.

        Args:
            agent: Agent name (e.g., "temujin", "mongke")
            days: Number of days to look back (default: 7)

        Returns:
            Success rate as float (0.0 - 1.0)
        """
        if not self.driver:
            # Fallback: return 0.8 if Neo4j unavailable
            logging.warning(f"Neo4j unavailable - returning default baseline 0.8 for {agent}")
            return 0.8

        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task {agent: $agent})
                WHERE t.created > datetime() - duration({days: $days})
                  AND toUpper(t.status) IN ['COMPLETED', 'FAILED']
                WITH
                    count(t) AS total,
                    sum(CASE WHEN toUpper(t.status) = 'COMPLETED' THEN 1 ELSE 0 END) AS success
                RETURN
                    CASE
                        WHEN total > 0 THEN 1.0 * success / total
                        ELSE 0.0
                    END AS success_rate
            """, agent=agent, days=days)

            record = result.single()
            return float(record["success_rate"]) if record and record["success_rate"] is not None else 0.0

    def get_experiment_metric(
        self,
        agent: str,
        start: datetime,
        end: Optional[datetime] = None
    ) -> MetricSnapshot:
        """
        Get metrics during the experiment window.

        Args:
            agent: Agent name
            start: Experiment start time
            end: Experiment end time (defaults to now)

        Returns:
            MetricSnapshot with success rate, error rate, duration P95, etc.
        """
        if end is None:
            end = datetime.utcnow()

        if not self.driver:
            # Fallback: return default snapshot
            logging.warning(f"Neo4j unavailable - returning default metrics for {agent}")
            return MetricSnapshot(
                timestamp=end,
                agent=agent,
                success_rate=0.82,
                total_tasks=50,
                completed_tasks=41,
                failed_tasks=9,
                error_rate=0.18,
                duration_p95=300.0,
                quality_score_avg=0.75
            )

        with self.driver.session() as session:
            # Convert datetime to ISO format for Cypher
            start_iso = start.isoformat()
            end_iso = end.isoformat()

            # Primary metrics query
            result = session.run("""
                MATCH (t:Task {agent: $agent})
                WHERE t.created >= datetime($start)
                  AND t.created <= datetime($end)
                  AND toUpper(t.status) IN ['COMPLETED', 'FAILED']
                WITH
                    count(t) AS total,
                    sum(CASE WHEN toUpper(t.status) = 'COMPLETED' THEN 1 ELSE 0 END) AS completed,
                    sum(CASE WHEN toUpper(t.status) = 'FAILED' THEN 1 ELSE 0 END) AS failed
                WITH total, completed, failed,
                    CASE
                        WHEN total > 0 THEN 1.0 * completed / total
                        ELSE 0.0
                    END AS success_rate,
                    CASE
                        WHEN total > 0 THEN 1.0 * failed / total
                        ELSE 0.0
                    END AS error_rate
                RETURN success_rate, total AS total_tasks,
                       completed AS completed_tasks, failed AS failed_tasks, error_rate
            """, agent=agent, start=start_iso, end=end_iso)

            record = result.single()

            if not record or record["total_tasks"] == 0:
                # No tasks in window - return empty snapshot
                return MetricSnapshot(
                    timestamp=end,
                    agent=agent,
                    success_rate=0.0,
                    total_tasks=0,
                    completed_tasks=0,
                    failed_tasks=0,
                    error_rate=0.0
                )

            # Duration P95 query (tasks with completion time)
            duration_result = session.run("""
                MATCH (t:Task {agent: $agent})
                WHERE t.created >= datetime($start)
                  AND t.created <= datetime($end)
                  AND t.started IS NOT NULL
                  AND t.completed IS NOT NULL
                WITH duration.between(t.started, t.completed).seconds AS duration_seconds
                RETURN collect(duration_seconds) AS durations
            """, agent=agent, start=start_iso, end=end_iso)

            duration_p95 = None
            dur_record = duration_result.single()
            if dur_record and dur_record["durations"]:
                durations = sorted([d for d in dur_record["durations"] if d is not None])
                if durations:
                    idx = int(len(durations) * 0.95)
                    duration_p95 = durations[min(idx, len(durations) - 1)]

            return MetricSnapshot(
                timestamp=end,
                agent=agent,
                success_rate=float(record["success_rate"]),
                total_tasks=int(record["total_tasks"]),
                completed_tasks=int(record["completed_tasks"]),
                failed_tasks=int(record["failed_tasks"]),
                error_rate=float(record["error_rate"]),
                duration_p95=duration_p95
            )

    def get_baseline_duration_p95(self, agent: str, days: int = 7) -> Optional[float]:
        """Get baseline 95th percentile task duration."""
        if not self.driver:
            return 300.0  # Default fallback

        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task {agent: $agent})
                WHERE t.created > datetime() - duration({days: $days})
                  AND t.started IS NOT NULL
                  AND t.completed IS NOT NULL
                WITH duration.between(t.started, t.completed).seconds AS duration_seconds
                WITH collect(duration_seconds) AS durations
                WITH [d IN durations WHERE d IS NOT NULL | d] AS valid_durations
                WITH valid_durations, size(valid_durations) AS n
                RETURN CASE
                    WHEN n > 0 THEN valid_durations[toInteger(n * 0.95)]
                    ELSE NULL
                END AS p95_duration
            """, agent=agent, days=days)

            record = result.single()
            return float(record["p95_duration"]) if record and record["p95_duration"] else None

    def get_baseline_error_rate(self, agent: str, days: int = 7) -> float:
        """Get baseline error rate (failed / total)."""
        if not self.driver:
            return 0.15  # Default fallback

        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task {agent: $agent})
                WHERE t.created > datetime() - duration({days: $days})
                  AND toUpper(t.status) IN ['COMPLETED', 'FAILED']
                WITH count(t) AS total,
                     sum(CASE WHEN toUpper(t.status) = 'FAILED' THEN 1 ELSE 0 END) AS failed
                RETURN CASE
                    WHEN total > 0 THEN 1.0 * failed / total
                    ELSE 0.0
                END AS error_rate
            """, agent=agent, days=days)

            record = result.single()
            return float(record["error_rate"]) if record and record["error_rate"] else 0.0

    def evaluate(self, experiment: Experiment) -> Decision:
        """
        Evaluate experiment against baseline metrics.

        Args:
            experiment: Experiment to evaluate

        Returns:
            Decision with status, improvement, reasoning, and confidence
        """
        # Get baseline metrics (7-day rolling average)
        baseline_success_rate = self.get_baseline_metric(experiment.agent, days=7)
        baseline_error_rate = self.get_baseline_error_rate(experiment.agent, days=7)
        baseline_duration_p95 = self.get_baseline_duration_p95(experiment.agent, days=7)

        # Edge case: Experiment crashed (check BEFORE querying experiment metrics)
        if experiment.status == "crashed" or (
            experiment.end_time is None and
            (datetime.utcnow() - experiment.start_time) > timedelta(hours=24)
        ):
            metrics_compared = {
                "baseline": {
                    "success_rate": baseline_success_rate,
                    "error_rate": baseline_error_rate,
                    "duration_p95": baseline_duration_p95
                },
                "experiment": None
            }
            decision = Decision(
                status="crashed",
                improvement_pct=0.0,
                baseline_metric=baseline_success_rate,
                result_metric=baseline_success_rate,  # No result, use baseline
                reasoning="Experiment failed to complete or crashed during execution",
                confidence=1.0,
                metrics_compared=metrics_compared
            )
            self._log_to_ledger(experiment, decision)
            return decision

        # Get experiment metrics (only if not crashed)
        end_time = experiment.end_time or datetime.utcnow()
        experiment_metrics = self.get_experiment_metric(
            experiment.agent,
            experiment.start_time,
            end_time
        )

        # Calculate improvement percentage
        if baseline_success_rate > 0:
            improvement_pct = ((experiment_metrics.success_rate - baseline_success_rate)
                              / baseline_success_rate) * 100
        else:
            improvement_pct = 0.0

        # Build metrics comparison dict
        metrics_compared = {
            "baseline": {
                "success_rate": baseline_success_rate,
                "error_rate": baseline_error_rate,
                "duration_p95": baseline_duration_p95
            },
            "experiment": {
                "success_rate": experiment_metrics.success_rate,
                "error_rate": experiment_metrics.error_rate,
                "duration_p95": experiment_metrics.duration_p95,
                "total_tasks": experiment_metrics.total_tasks
            }
        }

        # Edge case: No tasks in experiment window
        if experiment_metrics.total_tasks == 0:
            decision = Decision(
                status="discarded",
                improvement_pct=0.0,
                baseline_metric=baseline_success_rate,
                result_metric=0.0,
                reasoning="No tasks completed during experiment window - inconclusive",
                confidence=0.0,
                metrics_compared=metrics_compared
            )
            self._log_to_ledger(experiment, decision)
            return decision

        # MERGE condition 1: Success rate improvement > 5%
        if improvement_pct >= MERGE_THRESHOLD_IMPROVEMENT * 100:
            confidence = min(0.9, 0.5 + (improvement_pct / 20))  # Scale confidence with improvement
            decision = Decision(
                status="merged",
                improvement_pct=improvement_pct,
                baseline_metric=baseline_success_rate,
                result_metric=experiment_metrics.success_rate,
                reasoning=f"Improved by {improvement_pct:.1f}% - exceeds {MERGE_THRESHOLD_IMPROVEMENT*100:.0f}% threshold",
                confidence=confidence,
                metrics_compared=metrics_compared
            )
            self._log_to_ledger(experiment, decision)
            return decision

        # MERGE condition 2: Duration P95 reduced by > 10% (if duration data available)
        if (baseline_duration_p95 and experiment_metrics.duration_p95 and
            baseline_duration_p95 > 0):
            duration_reduction = ((baseline_duration_p95 - experiment_metrics.duration_p95)
                                 / baseline_duration_p95)
            if duration_reduction >= MERGE_THRESHOLD_DURATION_REDUCTION:
                decision = Decision(
                    status="merged",
                    improvement_pct=improvement_pct,  # Report actual success rate change too
                    baseline_metric=baseline_success_rate,
                    result_metric=experiment_metrics.success_rate,
                    reasoning=(f"Duration P95 reduced by {duration_reduction*100:.1f}% "
                             f"({baseline_duration_p95:.0f}s → {experiment_metrics.duration_p95:.0f}s)"),
                    confidence=0.75,
                    metrics_compared=metrics_compared
                )
                self._log_to_ledger(experiment, decision)
                return decision

        # DISCARD condition 1: Regression > 5%
        if improvement_pct <= DISCARD_THRESHOLD_REGRESSION * 100:
            decision = Decision(
                status="discarded",
                improvement_pct=improvement_pct,
                baseline_metric=baseline_success_rate,
                result_metric=experiment_metrics.success_rate,
                reasoning=f"Regressed by {abs(improvement_pct):.1f}% - exceeds {abs(DISCARD_THRESHOLD_REGRESSION)*100:.0f}% threshold",
                confidence=0.9,
                metrics_compared=metrics_compared
            )
            self._log_to_ledger(experiment, decision)
            return decision

        # DISCARD condition 2: Error rate > 2x baseline
        if baseline_error_rate > 0:
            error_multiplier = experiment_metrics.error_rate / baseline_error_rate
            if error_multiplier > DISCARD_THRESHOLD_ERROR_MULTIPLIER:
                decision = Decision(
                    status="discarded",
                    improvement_pct=improvement_pct,
                    baseline_metric=baseline_success_rate,
                    result_metric=experiment_metrics.success_rate,
                    reasoning=(f"Error rate {error_multiplier:.1f}x baseline "
                             f"({experiment_metrics.error_rate:.1%} vs {baseline_error_rate:.1%})"),
                    confidence=0.85,
                    metrics_compared=metrics_compared
                )
                self._log_to_ledger(experiment, decision)
                return decision

        # DEFAULT: No significant change - discard
        # (We require positive action to merge; neutral results are discarded to avoid regression risk)
        decision = Decision(
            status="discarded",
            improvement_pct=improvement_pct,
            baseline_metric=baseline_success_rate,
            result_metric=experiment_metrics.success_rate,
            reasoning=f"No significant change ({improvement_pct:+.1f}%) - below merge threshold",
            confidence=0.6,
            metrics_compared=metrics_compared
        )
        self._log_to_ledger(experiment, decision)
        return decision


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def evaluate_experiment_from_dict(experiment_dict: Dict[str, Any]) -> Decision:
    """
    Evaluate an experiment from a dictionary representation.

    Args:
        experiment_dict: Dictionary with experiment data

    Returns:
        Decision object
    """
    experiment = Experiment.from_dict(experiment_dict)
    engine = EvaluationEngine()
    try:
        return engine.evaluate(experiment)
    finally:
        engine.close()


def create_experiment(
    experiment_id: str,
    agent: str,
    hypothesis: str,
    start_time: datetime,
    branch: str = ""
) -> Experiment:
    """
    Create an Experiment object with default values.

    Args:
        experiment_id: Unique experiment identifier
        agent: Agent name
        hypothesis: Description of hypothesis
        start_time: When experiment started
        branch: Git branch name (optional)

    Returns:
        Experiment object
    """
    return Experiment(
        id=experiment_id,
        agent=agent,
        hypothesis=hypothesis,
        start_time=start_time,
        end_time=None,
        branch=branch,
        status="running"
    )


# =============================================================================
# CLI INTERFACE
# =============================================================================

def main():
    """CLI interface for evaluating experiments."""
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="Evaluate Kurultai autonomous experiments"
    )
    parser.add_argument(
        "experiment_id",
        help="Experiment ID (e.g., exp-20260308-001)"
    )
    parser.add_argument(
        "--agent",
        required=True,
        help="Agent name (e.g., temujin, mongke)"
    )
    parser.add_argument(
        "--hypothesis",
        required=True,
        help="Experiment hypothesis description"
    )
    parser.add_argument(
        "--start",
        required=True,
        help="Start time (ISO format: 2026-03-08T10:00:00)"
    )
    parser.add_argument(
        "--end",
        help="End time (ISO format, defaults to now)"
    )
    parser.add_argument(
        "--branch",
        default="",
        help="Git branch name"
    )
    parser.add_argument(
        "--baseline",
        type=float,
        default=0.0,
        help="Pre-computed baseline success rate (0-1)"
    )
    parser.add_argument(
        "--output",
        choices=["text", "json"],
        default="text",
        help="Output format"
    )

    args = parser.parse_args()

    # Parse datetime
    start_time = datetime.fromisoformat(args.start)
    end_time = datetime.fromisoformat(args.end) if args.end else None

    # Create experiment
    experiment = Experiment(
        id=args.experiment_id,
        agent=args.agent,
        hypothesis=args.hypothesis,
        start_time=start_time,
        end_time=end_time,
        branch=args.branch,
        baseline_metric=args.baseline
    )

    # Evaluate
    engine = EvaluationEngine()
    try:
        decision = engine.evaluate(experiment)

        if args.output == "json":
            print(json.dumps({
                "experiment": experiment.to_dict(),
                "decision": decision.to_dict()
            }, indent=2))
        else:
            print("=" * 60)
            print(f"EXPERIMENT EVALUATION: {experiment.id}")
            print("=" * 60)
            print(f"Agent: {experiment.agent}")
            print(f"Hypothesis: {experiment.hypothesis}")
            print(f"Window: {start_time.isoformat()} → {end_time.isoformat() if end_time else 'now'}")
            print()
            print(str(decision))
            print("=" * 60)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
