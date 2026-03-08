#!/usr/bin/env python3
"""
Cascade Failure Detector — Early warning for correlated failures.

Detects patterns like:
- Multiple agents failing simultaneously
- Single agent timeout spike
- Failure rate increasing over time
- Gateway-wide failure patterns

Provides actionable recommendations for preventive action.
"""

import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from kurultai_paths import AGENTS_DIR, LOGS_DIR

# Configuration
DEFAULT_LOOKBACK_MINUTES = 30
SIMULTANEOUS_WINDOW_SECONDS = 60  # Consider failures simultaneous if within 60s
TIMEOUT_CLUSTER_MIN_COUNT = 5     # Flag timeout cluster if 5+ in window
ACCELERATION_WINDOWS = 3          # Compare 3 consecutive time windows
FAILURE_RATE_WARNING = 0.5        # 50% failure rate triggers warning
FAILURE_RATE_CRITICAL = 0.7       # 70% failure rate triggers critical

# Cascade detection log
CASCADE_LOG = LOGS_DIR / "cascade-detections.jsonl"

# Agents to monitor
AGENTS = ["kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei"]


class CascadePattern:
    """Represents a detected cascade pattern."""

    def __init__(
        self,
        pattern_type: str,
        severity: str,
        description: str,
        affected_agents: list,
        evidence: dict,
        recommendation: str = "",
    ):
        self.pattern_type = pattern_type
        self.severity = severity  # low, medium, high
        self.description = description
        self.affected_agents = affected_agents
        self.evidence = evidence
        self.recommendation = recommendation

    def to_dict(self) -> dict:
        return {
            "type": self.pattern_type,
            "severity": self.severity,
            "description": self.description,
            "affected_agents": self.affected_agents,
            "evidence": self.evidence,
            "recommendation": self.recommendation,
        }


class CascadeDetector:
    """Detect potential cascade failures."""

    def __init__(self, lookback_minutes: int = DEFAULT_LOOKBACK_MINUTES):
        self.lookback = timedelta(minutes=lookback_minutes)

    def detect_cascade_risk(self) -> dict:
        """Analyze recent failures for cascade patterns.

        Returns:
            {
                "risk_level": "low|medium|high",
                "patterns": list[CascadePattern],
                "recommendations": list[str],
                "metrics": dict
            }
        """
        # Read recent ledger events
        events = self._read_ledger_events()

        if not events:
            return {
                "risk_level": "low",
                "patterns": [],
                "recommendations": [],
                "metrics": {"events_analyzed": 0},
            }

        # Analyze for patterns
        patterns = []

        # Pattern 1: Simultaneous multi-agent failures
        patterns.extend(self.check_simultaneous_failures(events))

        # Pattern 2: Timeout clustering on single agent
        patterns.extend(self.check_timeout_clustering(events))

        # Pattern 3: Failure acceleration over time
        patterns.extend(self.check_failure_acceleration(events))

        # Pattern 4: Gateway-wide failure spike
        patterns.extend(self.check_gateway_failure_spike(events))

        # Determine overall risk level
        risk_level = self._calculate_risk_level(patterns)

        # Generate recommendations
        recommendations = self.generate_recommendations(risk_level, patterns)

        # Calculate metrics
        metrics = self._calculate_metrics(events, patterns)

        # Log detection if risk is elevated
        if risk_level in ["medium", "high"]:
            self._log_cascade_detection(risk_level, patterns, metrics)

        return {
            "risk_level": risk_level,
            "patterns": [p.to_dict() for p in patterns],
            "recommendations": recommendations,
            "metrics": metrics,
        }

    def _read_ledger_events(self) -> list:
        """Read recent FAILED events from the ledger."""
        try:
            from kurultai_ledger import read_ledger
        except ImportError:
            return []

        hours = self.lookback.total_seconds() / 3600
        all_events = read_ledger(hours=hours)

        # Filter to FAILED events with agent info
        failed_events = []
        for ev in all_events:
            if ev.get("event") == "FAILED":
                agent = ev.get("agent")
                if agent and agent in AGENTS:
                    failed_events.append(ev)

        return failed_events

    def check_simultaneous_failures(self, events: list) -> list:
        """Detect multiple agents failing within short time window.

        Returns list of CascadePattern.
        """
        patterns = []

        if not events:
            return patterns

        # Group failures by time window
        time_windows = defaultdict(lambda: defaultdict(int))

        for ev in events:
            ts_str = ev.get("ts", "")
            if not ts_str:
                continue

            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                # Round to nearest minute
                window = ts.replace(second=0, microsecond=0)
                agent = ev.get("agent", "unknown")
                time_windows[window][agent] += 1
            except (ValueError, TypeError):
                continue

        # Check for windows with multiple failing agents
        for window, agent_counts in sorted(time_windows.items()):
            failing_agents = list(agent_counts.keys())
            if len(failing_agents) >= 3:  # 3+ agents failing in same minute
                total_failures = sum(agent_counts.values())

                # Determine severity
                if len(failing_agents) >= 5:
                    severity = "high"
                    description = f"CRITICAL: {len(failing_agents)} agents failing simultaneously ({total_failures} failures in {window.strftime('%H:%M')})"
                    recommendation = "IMMEDIATE: Check gateway health, verify network connectivity, consider pausing new tasks"
                else:
                    severity = "medium"
                    description = f"WARNING: {len(failing_agents)} agents failing in same minute ({total_failures} failures in {window.strftime('%H:%M')})"
                    recommendation = "Check for shared dependency failure (gateway, network, API)"

                patterns.append(CascadePattern(
                    pattern_type="simultaneous_failures",
                    severity=severity,
                    description=description,
                    affected_agents=failing_agents,
                    evidence={
                        "window": window.isoformat(),
                        "agent_counts": dict(agent_counts),
                        "total_failures": total_failures,
                    },
                    recommendation=recommendation,
                ))

        return patterns

    def check_timeout_clustering(self, events: list) -> list:
        """Detect timeout clustering on single agent.

        Returns list of CascadePattern.
        """
        patterns = []

        # Group by agent
        agent_events = defaultdict(list)
        for ev in events:
            agent = ev.get("agent")
            if agent:
                agent_events[agent].append(ev)

        # Check each agent for timeout clusters
        for agent, agent_failures in agent_events.items():
            timeouts = [ev for ev in agent_failures if self._is_timeout(ev)]

            if len(timeouts) >= TIMEOUT_CLUSTER_MIN_COUNT:
                # Check if they're clustered in time
                timeouts.sort(key=lambda e: e.get("ts", ""))

                # Find clusters
                clusters = []
                current_cluster = [timeouts[0]] if timeouts else []

                for timeout in timeouts[1:]:
                    try:
                        prev_ts = datetime.fromisoformat(current_cluster[-1].get("ts", "").replace("Z", "+00:00"))
                        curr_ts = datetime.fromisoformat(timeout.get("ts", "").replace("Z", "+00:00"))
                        if (curr_ts - prev_ts).total_seconds() <= 300:  # 5 minutes
                            current_cluster.append(timeout)
                        else:
                            if len(current_cluster) >= TIMEOUT_CLUSTER_MIN_COUNT:
                                clusters.append(current_cluster)
                            current_cluster = [timeout]
                    except (ValueError, TypeError):
                        current_cluster = [timeout]

                if len(current_cluster) >= TIMEOUT_CLUSTER_MIN_COUNT:
                    clusters.append(current_cluster)

                for cluster in clusters:
                    severity = "high" if len(cluster) >= 10 else "medium"
                    patterns.append(CascadePattern(
                        pattern_type="timeout_cluster",
                        severity=severity,
                        description=f"{len(cluster)} timeout(s) for {agent} in short window",
                        affected_agents=[agent],
                        evidence={
                            "timeout_count": len(cluster),
                            "time_range": {
                                "start": cluster[0].get("ts"),
                                "end": cluster[-1].get("ts"),
                            },
                            "sample_errors": [e.get("error", "unknown")[:100] for e in cluster[:3]],
                        },
                        recommendation=f"Check {agent} for stuck tasks, verify model availability, consider circuit breaker",
                    ))

        return patterns

    def check_failure_acceleration(self, events: list) -> list:
        """Detect increasing failure rate over time.

        Returns list of CascadePattern.
        """
        patterns = []

        if not events:
            return patterns

        # Split lookback into windows
        window_size = self.lookback / ACCELERATION_WINDOWS

        # Count failures per window per agent
        window_counts = defaultdict(lambda: defaultdict(int))
        window_success = defaultdict(lambda: defaultdict(int))

        # Also read COMPLETED events for rate calculation
        try:
            from kurultai_ledger import read_ledger
            hours = self.lookback.total_seconds() / 3600
            all_events = read_ledger(hours=hours)

            for ev in all_events:
                ts_str = ev.get("ts", "")
                if not ts_str:
                    continue

                try:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    window_idx = int((datetime.now() - ts).total_seconds() / window_size.total_seconds())
                    window_idx = min(window_idx, ACCELERATION_WINDOWS - 1)

                    agent = ev.get("agent")
                    if not agent:
                        continue

                    event_type = ev.get("event", "")
                    if event_type == "FAILED":
                        window_counts[window_idx][agent] += 1
                    elif event_type == "COMPLETED":
                        window_success[window_idx][agent] += 1
                except (ValueError, TypeError):
                    continue
        except ImportError:
            pass

        # Check for acceleration (increasing failure rate)
        for agent in AGENTS:
            rates = []
            for i in range(ACCELERATION_WINDOWS):
                failed = window_counts[i].get(agent, 0)
                success = window_success[i].get(agent, 0)
                total = failed + success
                rate = failed / total if total > 0 else 0
                rates.append((i, rate, failed, success))

            # Check if rate is consistently increasing
            if len(rates) >= 2:
                increasing = all(rates[i][1] < rates[i+1][1] for i in range(len(rates) - 1))

                if increasing and rates[-1][1] >= FAILURE_RATE_WARNING:
                    # Calculate acceleration
                    accel = rates[-1][1] - rates[0][1]

                    severity = "high" if rates[-1][1] >= FAILURE_RATE_CRITICAL else "medium"

                    patterns.append(CascadePattern(
                        pattern_type="failure_acceleration",
                        severity=severity,
                        description=f"{agent} failure rate accelerating: {rates[0][1]:.0%} → {rates[-1][1]:.0%} (+{accel:.0%})",
                        affected_agents=[agent],
                        evidence={
                            "agent": agent,
                            "rates": [{"window": f"w{i}", "rate": f"{r:.1%}", "failed": f, "total": f+s} for i, r, f, s in rates],
                            "acceleration": accel,
                        },
                        recommendation=f"Escalate {agent} degradation, check for resource exhaustion, verify model health",
                    ))

        return patterns

    def check_gateway_failure_spike(self, events: list) -> list:
        """Detect gateway-wide failure patterns.

        Returns list of CascadePattern.
        """
        patterns = []

        # Count total failures vs lookback period
        total_failures = len(events)

        # Calculate expected baseline (rough estimate)
        hours = self.lookback.total_seconds() / 3600
        # Assume ~20 tasks/hour as baseline, 10% failure rate = 2 failures/hour
        expected_failures = int(hours * 2)

        if total_failures >= expected_failures * 5:  # 5x expected
            severity = "high" if total_failures >= expected_failures * 10 else "medium"

            # Check if all agents affected
            affected = set(ev.get("agent") for ev in events if ev.get("agent"))

            patterns.append(CascadePattern(
                pattern_type="gateway_spike",
                severity=severity,
                description=f"Gateway failure spike: {total_failures} failures in {hours:.1f}h (baseline: ~{expected_failures})",
                affected_agents=list(affected),
                evidence={
                    "total_failures": total_failures,
                    "expected_failures": expected_failures,
                    "multiplier": total_failures / expected_failures if expected_failures > 0 else 0,
                    "lookback_hours": hours,
                },
                recommendation="Check openclaw-gateway status, verify API credentials, inspect gateway.err.log",
            ))

        return patterns

    def _is_timeout(self, event: dict) -> bool:
        """Check if an event represents a timeout failure."""
        error = event.get("error", "").lower()
        return any(keyword in error for keyword in [
            "timeout",
            "timed out",
            "deadline exceeded",
            "context deadline",
        ])

    def _calculate_risk_level(self, patterns: list) -> str:
        """Calculate overall risk level from detected patterns."""
        if not patterns:
            return "low"

        # Count patterns by severity
        high_count = sum(1 for p in patterns if p.severity == "high")
        medium_count = sum(1 for p in patterns if p.severity == "medium")

        if high_count >= 2 or (high_count >= 1 and medium_count >= 2):
            return "high"
        elif high_count >= 1 or medium_count >= 2:
            return "medium"
        elif medium_count >= 1:
            return "medium"
        else:
            return "low"

    def generate_recommendations(self, risk_level: str, patterns: list) -> list:
        """Generate actionable recommendations."""
        recommendations = []

        # Add pattern-specific recommendations
        for pattern in patterns:
            if pattern.recommendation:
                recommendations.append({
                    "action": "investigate",
                    "priority": pattern.severity,
                    "description": pattern.recommendation,
                })

        # Add systemic recommendations based on risk level
        if risk_level == "high":
            recommendations.append({
                "action": "reduce_load",
                "priority": "high",
                "description": "Consider reducing overall task load until system stabilizes",
            })
            recommendations.append({
                "action": "pause_new_tasks",
                "priority": "high",
                "description": "Pause routing new tasks to affected agents",
            })

        elif risk_level == "medium":
            recommendations.append({
                "action": "monitor_closely",
                "priority": "medium",
                "description": "Increase monitoring frequency, prepare to escalate",
            })

        return recommendations

    def _calculate_metrics(self, events: list, patterns: list) -> dict:
        """Calculate summary metrics."""
        agent_failures = defaultdict(int)
        for ev in events:
            agent = ev.get("agent")
            if agent:
                agent_failures[agent] += 1

        return {
            "events_analyzed": len(events),
            "patterns_detected": len(patterns),
            "agents_failing": len(agent_failures),
            "failures_by_agent": dict(agent_failures),
            "lookback_minutes": int(self.lookback.total_seconds() / 60),
        }

    def _log_cascade_detection(self, risk_level: str, patterns: list, metrics: dict):
        """Log cascade detection for analytics."""
        event = {
            "ts": datetime.now().isoformat(),
            "risk_level": risk_level,
            "pattern_count": len(patterns),
            "patterns": [p.to_dict() for p in patterns],
            "metrics": metrics,
        }

        try:
            CASCADE_LOG.parent.mkdir(parents=True, exist_ok=True)
            with open(CASCADE_LOG, "a") as f:
                f.write(json.dumps(event) + "\n")
        except Exception:
            pass  # Non-critical


def check_cascade_risk(lookback_minutes: int = DEFAULT_LOOKBACK_MINUTES) -> dict:
    """Convenience function to check cascade risk.

    Returns:
        dict with keys: risk_level, patterns, recommendations, metrics
    """
    detector = CascadeDetector(lookback_minutes=lookback_minutes)
    return detector.detect_cascade_risk()


def main():
    """CLI for cascade detection."""
    import argparse

    parser = argparse.ArgumentParser(description="Detect cascade failure risks")
    parser.add_argument("--lookback", "-l", type=int, default=DEFAULT_LOOKBACK_MINUTES,
                        help="Lookback period in minutes")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    detector = CascadeDetector(lookback_minutes=args.lookback)
    result = detector.detect_cascade_risk()

    print(f"Cascade Risk Level: {result['risk_level'].upper()}")
    print(f"Lookback: {result['metrics']['lookback_minutes']} minutes")
    print(f"Events analyzed: {result['metrics']['events_analyzed']}")
    print(f"Patterns detected: {result['metrics']['patterns_detected']}")

    if result['patterns']:
        print("\nPatterns:")
        for p in result['patterns']:
            print(f"  [{p['severity'].upper()}] {p['description']}")
            if args.verbose:
                print(f"    Evidence: {p['evidence']}")

    if result['recommendations']:
        print("\nRecommendations:")
        for rec in result['recommendations']:
            print(f"  [{rec['priority'].upper()}] {rec['description']}")

    return 0 if result['risk_level'] == 'low' else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
