#!/usr/bin/env python3
"""
Experiment Health Monitor — Autoresearch monitoring for the Kurultai

Checks:
1. Stale experiments (running > 2 hours)
2. Crash sequences (3+ consecutive crashes)
3. Merge rate (alert if < 10%)
4. Cost per hour (alert if > $5)
5. Active experiment count (alert if > 5)

Usage:
    python3 experiment_health_monitor.py [--json] [--quiet]
    --json: Output JSON format for logging
    --quiet: Suppress normal output, only show warnings
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any

# Add script directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configuration
OPENCLAW_DIR = Path.home() / ".openclaw"
EXPERIMENTS_DIR = OPENCLAW_DIR / "experiments"
LEDGER_FILE = EXPERIMENTS_DIR / "experiment-ledger.tsv"
LOG_DIR = OPENCLAW_DIR / "agents" / "main" / "logs"
HEALTH_LOG = LOG_DIR / "experiment-health.log"

# Alert thresholds
STALE_THRESHOLD_HOURS = 2
CRASH_SEQUENCE_COUNT = 3
MERGE_RATE_THRESHOLD_PCT = 10.0
COST_PER_HOUR_LIMIT = 5.0
ACTIVE_EXPERIMENT_LIMIT = 5

# Neo4j connection
NEO4J_AVAILABLE = False
NEO4J_DRIVER = None

try:
    from neo4j_task_tracker import get_driver
    NEO4J_AVAILABLE = True
except ImportError:
    pass


@dataclass
class Experiment:
    """Represents an experiment for health monitoring."""
    experiment_id: str
    agent: str
    status: str
    created: Optional[datetime] = None
    started: Optional[datetime] = None
    completed: Optional[datetime] = None
    decision: Optional[str] = None
    cost_usd: Optional[float] = None
    duration_seconds: Optional[int] = None
    hypothesis: Optional[str] = None

    @property
    def runtime(self) -> Optional[timedelta]:
        """Calculate how long experiment has been running."""
        if self.started:
            end = self.completed or datetime.now(timezone.utc)
            return end - self.started
        return None

    def is_stale(self, threshold_hours: int = STALE_THRESHOLD_HOURS) -> bool:
        """Check if experiment is stale (running too long)."""
        if self.status != "running" and self.status != "pending":
            return False
        if not self.started:
            # Pending experiments started are considered from created time
            start = self.created
        else:
            start = self.started

        if not start:
            return False

        threshold = timedelta(hours=threshold_hours)
        age = datetime.now(timezone.utc) - start
        return age > threshold


@dataclass
class HealthReport:
    """Health check report."""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    active_experiments: int = 0
    merge_rate_24h: float = 0.0
    consecutive_crashes: int = 0
    cost_per_hour: float = 0.0
    stale_experiments: List[Experiment] = field(default_factory=list)
    crash_sequence_detected: bool = False
    merge_rate_healthy: bool = True
    cost_within_budget: bool = True
    active_count_healthy: bool = True
    alerts: List[str] = field(default_factory=list)
    active_experiment_details: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "active_experiments": self.active_experiments,
            "merge_rate_24h": round(self.merge_rate_24h, 1),
            "consecutive_crashes": self.consecutive_crashes,
            "cost_per_hour": round(self.cost_per_hour, 2),
            "stale_count": len(self.stale_experiments),
            "crash_sequence_detected": self.crash_sequence_detected,
            "merge_rate_healthy": self.merge_rate_healthy,
            "cost_within_budget": self.cost_within_budget,
            "active_count_healthy": self.active_count_healthy,
            "alerts": self.alerts,
            "active_experiment_details": self.active_experiment_details,
        }

    def to_text(self) -> str:
        """Generate human-readable report."""
        lines = [
            f"EXPERIMENT HEALTH CHECK - {self.timestamp.strftime('%Y-%m-%d %H:%M')}",
            "",
            "SUMMARY",
            "-------",
            f"Active experiments:   {self.active_experiments}",
            f"Merge rate (24h):     {self.merge_rate_24h:.1f}%",
            f"Consecutive crashes:  {self.consecutive_crashes}",
            f"Cost per hour:        ${self.cost_per_hour:.2f}",
            "",
            "STATUS",
            "------",
        ]

        # Status indicators
        lines.append(f"{'✓' if not self.stale_experiments else '✗'} No stale experiments" if not self.stale_experiments else f"✗ {len(self.stale_experiments)} stale experiment(s)")
        lines.append(f"{'✓' if self.merge_rate_healthy else '✗'} Merge rate {'healthy' if self.merge_rate_healthy else f'LOW ({self.merge_rate_24h:.1f}%)'}")
        lines.append(f"{'✓' if not self.crash_sequence_detected else '✗'} {'No crash sequences' if not self.crash_sequence_detected else f'Crash sequence detected ({self.consecutive_crashes} consecutive)'}")
        lines.append(f"{'✓' if self.cost_within_budget else '✗'} Cost {'within budget' if self.cost_within_budget else f'exceeds budget (${self.cost_per_hour:.2f}/hr)'}")

        if self.active_experiment_details:
            lines.append("")
            lines.append("ACTIVE EXPERIMENTS")
            lines.append("------------------")
            for exp in self.active_experiment_details:
                runtime_str = exp.get("runtime", "N/A")
                lines.append(f"{exp['id']:20} {exp['agent']:8} {exp['status']:8} {runtime_str:12} {exp.get('hypothesis', 'N/A')[:40]}")

        if self.alerts:
            lines.append("")
            lines.append("ALERTS")
            lines.append("------")
            for alert in self.alerts:
                lines.append(f"⚠ {alert}")

        return "\n".join(lines)


class ExperimentHealthMonitor:
    """Monitor experiment health for autoresearch system."""

    def __init__(self):
        self.driver = get_driver() if NEO4J_AVAILABLE else None
        self.experiments: List[Experiment] = []
        LOG_DIR.mkdir(parents=True, exist_ok=True)

    def _log(self, message: str, level: str = "INFO"):
        """Log message to file."""
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        log_line = f"[{timestamp}] [{level}] {message}"
        with open(HEALTH_LOG, "a") as f:
            f.write(log_line + "\n")

    def _parse_ledger(self) -> List[Experiment]:
        """Parse experiment ledger TSV file."""
        experiments = []

        if not LEDGER_FILE.exists():
            self._log("Ledger file not found", "WARNING")
            return experiments

        try:
            with open(LEDGER_FILE, "r") as f:
                lines = f.readlines()

            if len(lines) < 2:
                return experiments

            # Parse header
            header = lines[0].strip().split("\t")

            for line in lines[1:]:
                if not line.strip():
                    continue

                parts = line.strip().split("\t")
                if len(parts) < 8:
                    continue

                exp = Experiment(
                    experiment_id=parts[0],
                    agent=parts[1],
                    status=parts[6] if len(parts) > 6 else "unknown",
                )

                # Parse timestamps
                if len(parts) > 7:
                    try:
                        exp.completed = datetime.fromisoformat(parts[7].replace("Z", "+00:00"))
                    except (ValueError, IndexError):
                        pass

                # Parse cost if available
                if len(parts) > 4:
                    try:
                        exp.cost_usd = float(parts[4])
                    except (ValueError, IndexError):
                        pass

                # Parse hypothesis from last column
                if len(parts) > 7:
                    exp.hypothesis = parts[7][:100]  # Truncate long hypotheses

                experiments.append(exp)

        except Exception as e:
            self._log(f"Error parsing ledger: {e}", "ERROR")

        return experiments

    def _fetch_neo4j_experiments(self) -> List[Experiment]:
        """Fetch experiments from Neo4j."""
        if not self.driver:
            return []

        experiments = []
        try:
            with self.driver.session() as session:
                result = session.run("""
                    MATCH (e:Experiment)
                    RETURN e
                    ORDER BY e.created DESC
                    LIMIT 100
                """)

                for record in result:
                    data = record["e"]
                    exp = Experiment(
                        experiment_id=data.get("experiment_id", "unknown"),
                        agent=data.get("agent", "unknown"),
                        status=data.get("status", "unknown"),
                        cost_usd=data.get("cost_usd"),
                        duration_seconds=data.get("duration_seconds"),
                        hypothesis=data.get("hypothesis"),
                    )

                    # Parse datetime fields
                    for key in ["created", "started", "completed"]:
                        if key in data and data[key]:
                            try:
                                value = data[key]
                                if isinstance(value, str):
                                    setattr(exp, key, datetime.fromisoformat(value.replace("Z", "+00:00")))
                                elif hasattr(value, "to_native"):
                                    # Neo4j DateTime object
                                    setattr(exp, key, value.to_native())
                                else:
                                    setattr(exp, key, value)
                            except (ValueError, AttributeError):
                                pass

                    experiments.append(exp)

        except Exception as e:
            self._log(f"Error fetching Neo4j experiments: {e}", "ERROR")

        return experiments

    def get_all_experiments(self) -> List[Experiment]:
        """Get all experiments from both sources."""
        ledger_exps = self._parse_ledger()
        neo4j_exps = self._fetch_neo4j_experiments()

        # Deduplicate by experiment_id, preferring Neo4j data
        seen = set()
        all_experiments = []

        for exp in neo4j_exps + ledger_exps:
            if exp.experiment_id not in seen:
                seen.add(exp.experiment_id)
                all_experiments.append(exp)

        self.experiments = all_experiments
        return all_experiments

    def check_stale_experiments(self, threshold_hours: int = STALE_THRESHOLD_HOURS) -> List[Experiment]:
        """Find experiments running > threshold hours."""
        stale = []
        for exp in self.experiments:
            if exp.is_stale(threshold_hours):
                stale.append(exp)
        return stale

    def check_crash_sequence(self, threshold: int = CRASH_SEQUENCE_COUNT) -> bool:
        """Detect threshold+ consecutive crashes."""
        # Sort experiments by completion time (most recent last)
        completed = [e for e in self.experiments if e.status == "crashed" and e.completed]
        completed.sort(key=lambda x: x.completed or datetime.min)

        if len(completed) < threshold:
            self.consecutive_crash_count = 0
            return False

        # Count consecutive crashes from the end
        consecutive = 0
        for exp in reversed(completed):
            # Check if crashes are close in time (within 1 hour of each other)
            if consecutive == 0:
                consecutive += 1
            else:
                # Compare with previous crash
                prev_crash = completed[-(consecutive + 1)]
                time_diff = (exp.completed or datetime.min) - (prev_crash.completed or datetime.min)
                if time_diff <= timedelta(hours=1):
                    consecutive += 1
                else:
                    break

            if consecutive >= threshold:
                self.consecutive_crash_count = consecutive
                return True

        self.consecutive_crash_count = consecutive
        return False

    def calculate_merge_rate(self, hours: int = 24) -> float:
        """Calculate merged / total experiments in last N hours."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        recent = [e for e in self.experiments if e.completed and e.completed >= cutoff]

        if not recent:
            return 0.0

        merged = sum(1 for e in recent if e.status == "merged" or e.decision == "merge")
        total = len(recent)

        return (merged / total * 100) if total > 0 else 0.0

    def check_cost_budget(self, hourly_limit: float = COST_PER_HOUR_LIMIT) -> bool:
        """Alert if cost exceeds budget."""
        # Calculate total cost in last 24 hours
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        recent = [e for e in self.experiments if e.completed and e.completed >= cutoff]

        total_cost = sum(e.cost_usd or 0 for e in recent)
        self.current_cost_per_hour = total_cost / 24  # Spread over 24 hours

        return self.current_cost_per_hour <= hourly_limit

    def get_active_experiments(self) -> List[Experiment]:
        """Get all active (pending/running) experiments."""
        return [e for e in self.experiments if e.status in ["pending", "running"]]

    def generate_report(self) -> HealthReport:
        """Generate comprehensive health report."""
        self.get_all_experiments()

        report = HealthReport()

        # Active experiments
        active = self.get_active_experiments()
        report.active_experiments = len(active)
        report.active_count_healthy = len(active) <= ACTIVE_EXPERIMENT_LIMIT

        # Format active experiment details
        for exp in active:
            runtime = "N/A"
            if exp.started:
                end = exp.completed or datetime.now(timezone.utc)
                delta = end - exp.started
                hours, remainder = divmod(int(delta.total_seconds()), 3600)
                minutes, _ = divmod(remainder, 60)
                runtime = f"{hours}h {minutes}m"

            report.active_experiment_details.append({
                "id": exp.experiment_id,
                "agent": exp.agent,
                "status": exp.status,
                "runtime": runtime,
                "hypothesis": exp.hypothesis or "N/A",
            })

        # Stale experiments
        report.stale_experiments = self.check_stale_experiments()

        # Crash sequence
        report.crash_sequence_detected = self.check_crash_sequence()
        report.consecutive_crashes = self.consecutive_crash_count

        # Merge rate
        report.merge_rate_24h = self.calculate_merge_rate()
        report.merge_rate_healthy = report.merge_rate_24h >= MERGE_RATE_THRESHOLD_PCT

        # Cost budget
        report.cost_within_budget = self.check_cost_budget()
        report.cost_per_hour = self.current_cost_per_hour

        # Generate alerts
        if report.stale_experiments:
            for exp in report.stale_experiments:
                report.alerts.append(f"Stale experiment: {exp.experiment_id} ({exp.agent}) running > {STALE_THRESHOLD_HOURS}h")

        if report.crash_sequence_detected:
            report.alerts.append(f"Crash sequence: {report.consecutive_crashes} consecutive crashes detected")

        if not report.merge_rate_healthy:
            report.alerts.append(f"Low merge rate: {report.merge_rate_24h:.1f}% (threshold: {MERGE_RATE_THRESHOLD_PCT}%)")

        if not report.cost_within_budget:
            report.alerts.append(f"Cost exceeds budget: ${report.cost_per_hour:.2f}/hr (limit: ${COST_PER_HOUR_LIMIT}/hr)")

        if not report.active_count_healthy:
            report.alerts.append(f"High active count: {report.active_experiments} experiments (limit: {ACTIVE_EXPERIMENT_LIMIT})")

        return report

    def close(self):
        """Close Neo4j connection."""
        if self.driver:
            self.driver.close()


def main():
    """CLI interface."""
    parser = argparse.ArgumentParser(description="Experiment Health Monitor")
    parser.add_argument("--json", action="store_true", help="Output JSON format")
    parser.add_argument("--quiet", action="store_true", help="Suppress normal output, only show warnings")

    args = parser.parse_args()

    monitor = ExperimentHealthMonitor()
    try:
        report = monitor.generate_report()

        if args.json:
            print(json.dumps(report.to_dict(), indent=2))
        else:
            output = report.to_text()
            print(output)

            # Log to file
            monitor._log(f"Health check: {report.active_experiments} active, "
                        f"{report.merge_rate_24h:.1f}% merge rate, "
                        f"{len(report.alerts)} alerts")

            # Exit with error code if alerts present
            if report.alerts:
                sys.exit(1)

    finally:
        monitor.close()


if __name__ == "__main__":
    main()
