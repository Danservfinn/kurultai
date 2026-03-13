#!/usr/bin/env python3
"""
Self-Healing Score — Track system resilience.

Calculates percentage of issues auto-resolved vs. escalated.
Tracks healing events and produces metrics on system self-healing effectiveness.
"""

# Enable PEP 604 union syntax (X | Y) for Python < 3.10 compatibility
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from kurultai_paths import LOGS_DIR

# Score tracking file
SCORE_FILE = LOGS_DIR / "self-healing-score.json"
HEALING_EVENTS_LOG = LOGS_DIR / "healing-events.jsonl"

# Scoring weights
WEIGHTS = {
    "auto_recovered": 1.0,
    "escalated": 0.0,
    "manual": 0.0,
    "partial": 0.5,
}

# Issue types tracked
ISSUE_TYPES = [
    "gateway_crash",
    "gateway_restart",
    "stale_task",
    "stale_task_recovered",
    "fake_completion",
    "memory_contamination",
    "memory_bloat",
    "agent_failure",
    "agent_circuit_open",
    "quality_failure",
    "quality_retry",
    "cascade_detected",
    "queue_imbalance",
    "queue_rebalanced",
]


class HealingEvent:
    """Represents a single healing action."""

    def __init__(
        self,
        issue_type: str,
        action: str,
        outcome: str,
        agent: str = "",
        details: dict | None = None,
        ts: str = "",
    ):
        self.issue_type = issue_type
        self.action = action  # auto_recovered, escalated, manual, partial
        self.outcome = outcome  # success, failed, partial
        self.agent = agent
        self.details = details or {}
        self.ts = ts or datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "ts": self.ts,
            "issue_type": self.issue_type,
            "action": self.action,
            "outcome": self.outcome,
            "agent": self.agent,
            "details": self.details,
        }


class SelfHealingScore:
    """Track self-healing effectiveness."""

    def __init__(self, score_file: str | Path = SCORE_FILE):
        self.score_file = Path(score_file)
        self.events_log = Path(HEALING_EVENTS_LOG)

    def record_issue(
        self,
        issue_type: str,
        action: str,
        outcome: str,
        agent: str = "",
        details: dict | None = None,
    ):
        """Record a healing action.

        Args:
            issue_type: Type of issue (e.g., "gateway_crash", "stale_task")
            action: Action taken ("auto_recovered", "escalated", "manual", "partial")
            outcome: Outcome ("success", "failed", "partial")
            agent: Agent affected (if applicable)
            details: Additional details about the event
        """
        event = HealingEvent(
            issue_type=issue_type,
            action=action,
            outcome=outcome,
            agent=agent,
            details=details,
        )

        # Append to events log
        try:
            self.events_log.parent.mkdir(parents=True, exist_ok=True)
            with open(self.events_log, "a") as f:
                f.write(json.dumps(event.to_dict()) + "\n")
        except Exception as e:
            print(f"[self-healing-score] Failed to log event: {e}", file=os.sys.stderr)

    def calculate_score(self, hours: int = 24) -> dict:
        """Calculate self-healing score for time window.

        Args:
            hours: Lookback period in hours

        Returns:
            {
                "score": 85.0,  # Percentage
                "auto_resolved": 17,
                "escalated": 3,
                "manual": 1,
                "by_type": {...},
                "trends": [...],
                "total_issues": 21
            }
        """
        events = self._read_events(hours=hours)

        if not events:
            return {
                "score": 100.0,
                "auto_resolved": 0,
                "escalated": 0,
                "manual": 0,
                "partial": 0,
                "total_issues": 0,
                "by_type": {},
                "trends": [],
            }

        # Categorize events
        auto_resolved = 0
        escalated = 0
        manual = 0
        partial = 0
        by_type = defaultdict(lambda: {"auto": 0, "escalated": 0, "manual": 0, "partial": 0})

        for ev in events:
            issue_type = ev.get("issue_type", "unknown")
            action = ev.get("action", "unknown")

            if action == "auto_recovered":
                auto_resolved += 1
                by_type[issue_type]["auto"] += 1
            elif action == "escalated":
                escalated += 1
                by_type[issue_type]["escalated"] += 1
            elif action == "manual":
                manual += 1
                by_type[issue_type]["manual"] += 1
            elif action == "partial":
                partial += 1
                by_type[issue_type]["partial"] += 1

        total = auto_resolved + escalated + manual + partial

        # Calculate weighted score
        weighted_sum = (
            auto_resolved * WEIGHTS["auto_recovered"]
            + escalated * WEIGHTS["escalated"]
            + manual * WEIGHTS["manual"]
            + partial * WEIGHTS["partial"]
        )

        score = (weighted_sum / total * 100) if total > 0 else 100.0

        # Calculate trends (compare to previous period)
        trends = self._calculate_trends(hours)

        return {
            "score": round(score, 1),
            "auto_resolved": auto_resolved,
            "escalated": escalated,
            "manual": manual,
            "partial": partial,
            "total_issues": total,
            "by_type": dict(by_type),
            "trends": trends,
        }

    def get_report(self, hours: int = 24) -> str:
        """Generate human-readable report."""
        score_data = self.calculate_score(hours=hours)

        lines = [
            "=" * 50,
            f"Self-Healing Score Report (Last {hours}h)",
            "=" * 50,
            "",
            f"OVERALL SCORE: {score_data['score']:.1f}%",
            f"Total Issues: {score_data['total_issues']}",
            "",
            "Breakdown:",
            f"  Auto-Resolved: {score_data['auto_resolved']} ({score_data['auto_resolved'] / max(score_data['total_issues'], 1) * 100:.1f}%)",
            f"  Escalated:      {score_data['escalated']} ({score_data['escalated'] / max(score_data['total_issues'], 1) * 100:.1f}%)",
            f"  Manual:         {score_data['manual']} ({score_data['manual'] / max(score_data['total_issues'], 1) * 100:.1f}%)",
            f"  Partial:        {score_data['partial']} ({score_data['partial'] / max(score_data['total_issues'], 1) * 100:.1f}%)",
            "",
        ]

        # Add by-type breakdown
        if score_data["by_type"]:
            lines.append("By Issue Type:")
            for issue_type, counts in sorted(score_data["by_type"].items()):
                total = sum(counts.values())
                if total > 0:
                    auto_pct = counts["auto"] / total * 100
                    lines.append(f"  {issue_type}: {counts['auto']}/{total} auto ({auto_pct:.0f}%)")
            lines.append("")

        # Add trends
        if score_data["trends"]:
            lines.append("Trends:")
            for trend in score_data["trends"]:
                direction = trend["direction"]
                symbol = "↑" if direction == "up" else "↓" if direction == "down" else "→"
                lines.append(f"  {symbol} {trend['description']}")
            lines.append("")

        lines.append("=" * 50)

        return "\n".join(lines)

    def _read_events(self, hours: int = 24) -> list:
        """Read healing events from log file."""
        if not self.events_log.exists():
            return []

        cutoff = datetime.now() - timedelta(hours=hours)
        events = []

        try:
            with open(self.events_log, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                        ts_str = ev.get("ts", "")
                        if ts_str:
                            try:
                                ev_time = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                                if ev_time >= cutoff:
                                    events.append(ev)
                            except (ValueError, TypeError):
                                events.append(ev)  # Keep events with unparseable timestamps
                        else:
                            events.append(ev)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            print(f"[self-healing-score] Failed to read events: {e}", file=os.sys.stderr)

        return events

    def _calculate_trends(self, hours: int) -> list:
        """Calculate trends comparing current to previous period."""
        # Read events directly to avoid infinite recursion
        current_events = self._read_events(hours=hours)
        previous_events = self._read_events(hours=hours * 2)

        # Calculate current period metrics
        current_auto = sum(1 for e in current_events if e.get("action") == "auto_recovered")
        current_escalated = sum(1 for e in current_events if e.get("action") == "escalated")
        current_manual = sum(1 for e in current_events if e.get("action") == "manual")
        current_partial = sum(1 for e in current_events if e.get("action") == "partial")
        current_total = current_auto + current_escalated + current_manual + current_partial

        # Calculate previous period metrics
        prev_auto = sum(1 for e in previous_events if e.get("action") == "auto_recovered")
        prev_escalated = sum(1 for e in previous_events if e.get("action") == "escalated")
        prev_manual = sum(1 for e in previous_events if e.get("action") == "manual")
        prev_partial = sum(1 for e in previous_events if e.get("action") == "partial")
        prev_total = prev_auto + prev_escalated + prev_manual + prev_partial

        # Calculate scores
        current_weighted = (
            current_auto * WEIGHTS["auto_recovered"]
            + current_escalated * WEIGHTS["escalated"]
            + current_manual * WEIGHTS["manual"]
            + current_partial * WEIGHTS["partial"]
        )
        current_score = (current_weighted / current_total * 100) if current_total > 0 else 100.0

        prev_weighted = (
            prev_auto * WEIGHTS["auto_recovered"]
            + prev_escalated * WEIGHTS["escalated"]
            + prev_manual * WEIGHTS["manual"]
            + prev_partial * WEIGHTS["partial"]
        )
        prev_score = (prev_weighted / prev_total * 100) if prev_total > 0 else 100.0

        trends = []

        # Score trend
        if current_total > 0:
            score_diff = current_score - prev_score
            if abs(score_diff) > 5:  # Only note significant changes
                direction = "up" if score_diff > 0 else "down"
                trends.append({
                    "direction": direction,
                    "description": f"Score {'improved' if direction == 'up' else 'declined'} by {abs(score_diff):.1f}%",
                })

        # Auto-resolution rate trend
        if current_total > 0 and prev_total > 0:
            curr_auto_rate = current_auto / current_total
            prev_auto_rate = prev_auto / prev_total
            rate_diff = curr_auto_rate - prev_auto_rate

            if abs(rate_diff) > 0.1:  # 10% threshold
                direction = "up" if rate_diff > 0 else "down"
                trends.append({
                    "direction": direction,
                    "description": f"Auto-resolution rate {'increased' if direction == 'up' else 'decreased'} by {abs(rate_diff)*100:.0f}%",
                })

        # Issue volume trend
        if prev_total > 0:
            volume_ratio = current_total / prev_total
            if volume_ratio > 1.5:
                trends.append({
                    "direction": "up",
                    "description": f"Issue volume increased by {(volume_ratio-1)*100:.0f}%",
                })
            elif volume_ratio < 0.67:
                trends.append({
                    "direction": "down",
                    "description": f"Issue volume decreased by {(1-volume_ratio)*100:.0f}%",
                })

        return trends

    def save_score_snapshot(self, hours: int = 24):
        """Save current score as a snapshot for historical tracking."""
        score_data = self.calculate_score(hours=hours)

        snapshot = {
            "ts": datetime.now().isoformat(),
            "window_hours": hours,
            "score": score_data,
        }

        try:
            self.score_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.score_file, "w") as f:
                json.dump(snapshot, f, indent=2)
        except Exception as e:
            print(f"[self-healing-score] Failed to save snapshot: {e}", file=os.sys.stderr)

    def get_last_snapshot(self) -> dict | None:
        """Read the last saved score snapshot."""
        if not self.score_file.exists():
            return None

        try:
            with open(self.score_file, "r") as f:
                return json.load(f)
        except Exception:
            return None


def record_healing(
    issue_type: str,
    action: str,
    outcome: str = "success",
    agent: str = "",
    details: dict | None = None,
):
    """Convenience function to record a healing event."""
    tracker = SelfHealingScore()
    tracker.record_issue(issue_type, action, outcome, agent, details)


def get_score(hours: int = 24) -> dict:
    """Convenience function to get current self-healing score."""
    tracker = SelfHealingScore()
    return tracker.calculate_score(hours=hours)


def main():
    """CLI for self-healing score."""
    import argparse

    parser = argparse.ArgumentParser(description="Track self-healing effectiveness")
    parser.add_argument("--hours", "-h", type=int, default=24, help="Lookback period in hours")
    parser.add_argument("--report", "-r", action="store_true", help="Generate human-readable report")
    parser.add_argument("--record", nargs=4, metavar=("TYPE", "ACTION", "OUTCOME", "AGENT"),
                        help="Record a healing event")
    args = parser.parse_args()

    tracker = SelfHealingScore()

    if args.record:
        # Record an event
        issue_type, action, outcome, agent = args.record
        details = {}
        tracker.record_issue(issue_type, action, outcome, agent, details)
        print(f"Recorded: {issue_type} - {action} - {outcome} ({agent})")

    elif args.report:
        # Generate report
        print(tracker.get_report(hours=args.hours))

    else:
        # Show score JSON
        score = tracker.calculate_score(hours=args.hours)
        print(json.dumps(score, indent=2))

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
