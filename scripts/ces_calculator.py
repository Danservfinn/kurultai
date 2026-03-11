#!/usr/bin/env python3
"""
CES (Composite Effectiveness Score) Calculator for Kurultai Autonomous Experimentation

Composite Effectiveness Score combines multiple task outcome metrics into a single
normalized score (0.0 to 1.0) to evaluate task effectiveness.

Formula:
    CES = w_sr * Success_Rate + w_qs * Quality + w_ef * Efficiency + w_im * Impact

Default weights: SR=0.35, QS=0.30, EF=0.20, IM=0.15

Integration with action_scorer.py:
    - Reads artifact_quality_score, tool_efficiency_score, rule_adherence_score
    - Uses these as proxy metrics when human review is unavailable

Usage:
    # Single task CES
    python3 ces_calculator.py --task-id <id>

    # Batch CES for period
    python3 ces_calculator.py --period 7d --dry-run

    # CES distribution stats
    python3 ces_calculator.py --stats --agent temujin
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean, median, stdev
from typing import Any, Dict, List, Optional, Tuple

# Add scripts directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from kurultai_ledger import read_ledger
except ImportError:
    read_ledger = None

# =============================================================================
# Agent-Specific Weights
# Each agent has different priorities based on role
# =============================================================================
AGENT_WEIGHTS: Dict[str, Dict[str, float]] = {
    "temujin": {  # Implementation agent
        "success_rate": 0.40,
        "quality": 0.25,
        "efficiency": 0.20,
        "impact": 0.15,
    },
    "mongke": {  # Research agent
        "success_rate": 0.30,
        "quality": 0.35,
        "efficiency": 0.15,
        "impact": 0.20,
    },
    "chagatai": {  # Documentation/writing agent
        "success_rate": 0.30,
        "quality": 0.40,
        "efficiency": 0.15,
        "impact": 0.15,
    },
    "jochi": {  # Analysis agent
        "success_rate": 0.35,
        "quality": 0.30,
        "efficiency": 0.15,
        "impact": 0.20,
    },
    "ogedei": {  # Ops agent
        "success_rate": 0.45,
        "quality": 0.20,
        "efficiency": 0.25,
        "impact": 0.10,
    },
    "kublai": {  # Coordination agent
        "success_rate": 0.35,
        "quality": 0.25,
        "efficiency": 0.15,
        "impact": 0.25,
    },
}

# Default weights (fallback when agent not specified)
DEFAULT_WEIGHTS = {
    "success_rate": 0.35,
    "quality": 0.30,
    "efficiency": 0.20,
    "impact": 0.15,
}

# Priority weights for impact calculation
PRIORITY_WEIGHTS = {
    "critical": 1.0,
    "high": 0.75,
    "normal": 0.5,
    "low": 0.25,
}

# Default baseline duration fallback (seconds)
DEFAULT_BASELINE_DURATION = 600.0  # 10 minutes

# Efficiency cap (diminishing returns beyond this)
EFFICIENCY_CAP = 1.5


@dataclass
class CESResult:
    """Container for CES calculation result."""
    ces: float  # 0.0 to 1.0
    components: Dict[str, float]
    calculation_source: str  # "full", "proxy", "partial"
    agent: Optional[str] = None
    task_id: Optional[str] = None
    weights_used: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ces": round(self.ces, 4),
            "components": {k: round(v, 4) for k, v in self.components.items()},
            "calculation_source": self.calculation_source,
            "agent": self.agent,
            "task_id": self.task_id,
            "weights_used": {k: round(v, 2) for k, v in self.weights_used.items()},
        }


def calculate_success_rate(
    task: Dict[str, Any],
    priority: str = "normal"
) -> float:
    """
    Calculate Success Rate component.

    Args:
        task: Task dictionary with status and metadata
        priority: Task priority for penalty calculation

    Returns:
        Success rate score (0.0 to 1.0)

    Rules:
        - Base: 1.0 for completed, 0.0 for failed
        - Rework required: 0.5
        - Critical task failure: -0.15 penalty
        - High task failure: -0.08 penalty
        - Floor at 0.0
    """
    status = task.get("status", "").upper()
    rework_required = task.get("rework_required", False)

    # Base score
    if status == "COMPLETED" or status == "DONE":
        base = 1.0
    elif status == "FAILED" or status == "ERROR":
        base = 0.0
    elif status == "PENDING" or status == "IN_PROGRESS":
        return 0.0  # Incomplete tasks get 0
    else:
        base = 0.5  # Unknown status

    # Apply rework penalty
    if rework_required:
        base = 0.5

    # Apply priority-based failure penalty
    if status == "FAILED":
        if priority == "critical":
            base = max(0.0, base - 0.15)
        elif priority == "high":
            base = max(0.0, base - 0.08)

    return max(0.0, min(1.0, base))


def calculate_quality_score(
    task: Dict[str, Any],
    human_review: Optional[Dict[str, Any]] = None
) -> Tuple[float, str]:
    """
    Calculate Quality Score component.

    Args:
        task: Task dictionary with action_scorer metrics
        human_review: Optional human review dict with 'score' key (0-10 scale)

    Returns:
        Tuple of (quality_score, source)
        - quality_score: 0.0 to 1.0
        - source: "human_review" or "proxy"
    """
    # If human review exists, use it directly
    if human_review and "score" in human_review:
        score = human_review["score"]
        # Normalize from 0-10 scale to 0-1
        normalized = score / 10.0
        return max(0.0, min(1.0, normalized)), "human_review"

    # Otherwise, use proxy metrics from action_scorer
    # Proxy: 0.4 * artifact_quality + 0.3 * tool_efficiency + 0.3 * rule_adherence
    # All proxy scores are on 0-3 scale, normalized to 0-1

    artifact_quality = task.get("artifact_quality_score", 1.5)  # 0-3 scale
    tool_efficiency = task.get("tool_efficiency_score", 1.5)
    rule_adherence = task.get("rule_adherence_score", 1.5)

    # Normalize from 0-3 to 0-1
    aq_norm = artifact_quality / 3.0
    te_norm = tool_efficiency / 3.0
    ra_norm = rule_adherence / 3.0

    proxy_score = 0.4 * aq_norm + 0.3 * te_norm + 0.3 * ra_norm

    return max(0.0, min(1.0, proxy_score)), "proxy"


def calculate_efficiency(
    task: Dict[str, Any],
    baseline_duration: Optional[float] = None
) -> float:
    """
    Calculate Efficiency component.

    Args:
        task: Task dictionary with duration_seconds
        baseline_duration: Expected duration in seconds (fallback: 7-day median or 0.7)

    Returns:
        Efficiency score (0.0 to 1.5, capped)

    Formula:
        efficiency = min(1.5, baseline_duration / actual_duration)
    """
    actual_duration = task.get("duration_seconds", 0)

    if actual_duration <= 0:
        return 0.7  # Default fallback for tasks without duration

    # Use provided baseline or default
    if baseline_duration is None:
        baseline_duration = task.get("baseline_duration", DEFAULT_BASELINE_DURATION)

    if baseline_duration <= 0:
        return 0.7  # Fallback

    # Calculate efficiency ratio
    efficiency = baseline_duration / actual_duration

    # Cap at 1.5 (diminishing returns)
    return min(EFFICIENCY_CAP, max(0.0, efficiency))


def calculate_impact(
    task: Dict[str, Any]
) -> float:
    """
    Calculate Impact component.

    Args:
        task: Task dictionary with priority, downstream_enables, skill_match

    Returns:
        Impact score (0.0 to 1.0)

    Formula:
        impact = 0.5 * priority_weight + 0.3 * downstream_enables + 0.2 * skill_match
    """
    priority = task.get("priority", "normal").lower()
    priority_weight = PRIORITY_WEIGHTS.get(priority, 0.5)

    # Downstream enables: count of tasks this enables (normalized 0-1)
    downstream_enables = task.get("downstream_enables", 0)
    downstream_norm = min(1.0, downstream_enables / 5.0) if downstream_enables else 0.3

    # Skill match: how well task aligns with agent's skills (0-1)
    skill_match = task.get("skill_match", 0.5)

    impact = 0.5 * priority_weight + 0.3 * downstream_norm + 0.2 * skill_match

    return max(0.0, min(1.0, impact))


def calculate_ces(
    task: Dict[str, Any],
    human_review: Optional[Dict[str, Any]] = None,
    baseline_duration: Optional[float] = None,
    agent_weights: Optional[Dict[str, float]] = None
) -> Dict[str, Any]:
    """
    Calculate Composite Effectiveness Score for a task.

    Args:
        task: Task dictionary containing:
            - status: "COMPLETED", "FAILED", etc.
            - priority: "critical", "high", "normal", "low"
            - duration_seconds: Actual task duration
            - artifact_quality_score: From action_scorer (0-3 scale)
            - tool_efficiency_score: From action_scorer (0-3 scale)
            - rule_adherence_score: From action_scorer (0-3 scale)
            - downstream_enables: Count of downstream tasks enabled
            - skill_match: How well task matches agent skills (0-1)
            - agent: Agent name for weight lookup

        human_review: Optional dict with:
            - score: Human review score (0-10 scale)

        baseline_duration: Expected duration in seconds

        agent_weights: Custom weights dict with keys:
            - success_rate, quality, efficiency, impact

    Returns:
        {
            "ces": float,  # 0.0 to 1.0
            "components": {
                "success_rate": float,
                "quality_score": float,
                "efficiency": float,
                "impact": float
            },
            "calculation_source": str,  # "full", "proxy", "partial"
            "weights_used": dict,
            "task_id": str,
            "agent": str
        }
    """
    # Determine weights to use
    agent = task.get("agent", "default")

    if agent_weights:
        weights = agent_weights
    elif agent in AGENT_WEIGHTS:
        weights = AGENT_WEIGHTS[agent]
    else:
        weights = DEFAULT_WEIGHTS

    # Calculate each component
    priority = task.get("priority", "normal")
    success_rate = calculate_success_rate(task, priority)
    quality_score, quality_source = calculate_quality_score(task, human_review)
    efficiency = calculate_efficiency(task, baseline_duration)
    impact = calculate_impact(task)

    # Determine calculation source
    if human_review and baseline_duration:
        calc_source = "full"
    elif quality_source == "proxy" and baseline_duration:
        calc_source = "proxy"
    else:
        calc_source = "partial"

    # Calculate weighted CES
    ces = (
        weights["success_rate"] * success_rate +
        weights["quality"] * quality_score +
        weights["efficiency"] * efficiency +
        weights["impact"] * impact
    )

    # Normalize to 0-1 range (since efficiency can go up to 1.5)
    # Cap at 1.0
    ces = min(1.0, ces)

    return {
        "ces": round(ces, 4),
        "components": {
            "success_rate": round(success_rate, 4),
            "quality_score": round(quality_score, 4),
            "efficiency": round(efficiency, 4),
            "impact": round(impact, 4),
        },
        "calculation_source": calc_source,
        "weights_used": weights,
        "task_id": task.get("task_id", task.get("id")),
        "agent": agent,
    }


def calculate_ces_batch(
    tasks: List[Dict[str, Any]],
    human_reviews: Optional[Dict[str, Dict[str, Any]]] = None,
    baseline_durations: Optional[Dict[str, float]] = None
) -> List[Dict[str, Any]]:
    """
    Calculate CES for multiple tasks, returning enriched task dicts.

    Args:
        tasks: List of task dictionaries
        human_reviews: Optional dict mapping task_id to human review
        baseline_durations: Optional dict mapping task_id to baseline duration

    Returns:
        List of task dicts with added 'ces_result' key containing CES calculation
    """
    results = []

    for task in tasks:
        task_id = task.get("task_id", task.get("id"))
        human_review = human_reviews.get(task_id) if human_reviews else None
        baseline = baseline_durations.get(task_id) if baseline_durations else None

        ces_result = calculate_ces(
            task,
            human_review=human_review,
            baseline_duration=baseline
        )

        # Add CES result to task
        enriched_task = dict(task)
        enriched_task["ces_result"] = ces_result
        results.append(enriched_task)

    return results


def get_ces_stats(ces_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculate statistics from a list of CES results.

    Args:
        ces_results: List of CES result dicts

    Returns:
        Statistics dict with mean, median, std_dev, distribution
    """
    if not ces_results:
        return {
            "count": 0,
            "mean": None,
            "median": None,
            "std_dev": None,
            "min": None,
            "max": None,
            "distribution": {},
        }

    ces_values = [r.get("ces", 0) for r in ces_results]

    stats = {
        "count": len(ces_values),
        "mean": round(mean(ces_values), 4) if ces_values else None,
        "median": round(median(ces_values), 4) if ces_values else None,
        "min": round(min(ces_values), 4) if ces_values else None,
        "max": round(max(ces_values), 4) if ces_values else None,
    }

    if len(ces_values) >= 2:
        stats["std_dev"] = round(stdev(ces_values), 4)
    else:
        stats["std_dev"] = None

    # Distribution by range
    distribution = {
        "excellent_90+": len([v for v in ces_values if v >= 0.9]),
        "good_70_89": len([v for v in ces_values if 0.7 <= v < 0.9]),
        "acceptable_50_69": len([v for v in ces_values if 0.5 <= v < 0.7]),
        "poor_below_50": len([v for v in ces_values if v < 0.5]),
    }
    stats["distribution"] = distribution

    return stats


# =============================================================================
# CLI Interface
# =============================================================================

def parse_period(period_str: str) -> datetime:
    """Parse period string like '7d', '24h', '30d' to datetime."""
    if not period_str:
        return datetime.now() - timedelta(days=7)

    period_str = period_str.lower()
    if period_str.endswith("d"):
        days = int(period_str[:-1])
        return datetime.now() - timedelta(days=days)
    elif period_str.endswith("h"):
        hours = int(period_str[:-1])
        return datetime.now() - timedelta(hours=hours)
    else:
        # Assume days
        return datetime.now() - timedelta(days=int(period_str))


def load_tasks_from_ledger(
    period: Optional[str] = None,
    agent: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Load tasks from ledger within period."""
    if read_ledger is None:
        print("Warning: kurultai_ledger not available, using empty task list")
        return []

    hours = 168  # Default 7 days
    if period:
        if period.endswith("d"):
            hours = int(period[:-1]) * 24
        elif period.endswith("h"):
            hours = int(period[:-1])

    events = read_ledger(hours=hours)

    # Filter by agent if specified
    if agent:
        events = [e for e in events if e.get("agent") == agent]

    # Group by task_id and aggregate into task dicts
    tasks_by_id: Dict[str, Dict[str, Any]] = {}

    for event in events:
        task_id = event.get("task_id")
        if not task_id:
            continue

        if task_id not in tasks_by_id:
            tasks_by_id[task_id] = {
                "task_id": task_id,
                "agent": event.get("agent"),
                "status": "pending",
            }

        task = tasks_by_id[task_id]

        # Update status from terminal events
        if event.get("event") == "COMPLETED":
            task["status"] = "COMPLETED"
        elif event.get("event") == "FAILED":
            task["status"] = "FAILED"

        # Extract action scores
        if event.get("event") == "ACTION_SCORED":
            task["artifact_quality_score"] = event.get("output_score", 1.5)
            task["tool_efficiency_score"] = event.get("tool_score", 1.5)
            task["rule_adherence_score"] = 1.5  # Default if not in event

        # Extract duration
        if "duration_seconds" in event:
            task["duration_seconds"] = event["duration_seconds"]

        # Extract priority
        if "priority" in event:
            task["priority"] = event["priority"]

    return list(tasks_by_id.values())


def main():
    parser = argparse.ArgumentParser(
        description="CES Calculator - Composite Effectiveness Score for Kurultai Tasks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Calculate CES for single task
    python3 ces_calculator.py --task-id task-123

    # Calculate CES for all tasks in period
    python3 ces_calculator.py --period 7d --dry-run

    # Show CES distribution for agent
    python3 ces_calculator.py --stats --agent temujin

    # Use custom weights
    python3 ces_calculator.py --task-id task-123 --weights '{"success_rate": 0.5, "quality": 0.3, "efficiency": 0.1, "impact": 0.1}'
        """
    )

    parser.add_argument("--task-id", type=str, help="Calculate CES for specific task ID")
    parser.add_argument("--period", type=str, default="7d",
                        help="Period to analyze (e.g., 7d, 24h)")
    parser.add_argument("--agent", type=str,
                        choices=["temujin", "mongke", "chagatai", "jochi", "ogedei", "kublai"],
                        help="Filter by agent")
    parser.add_argument("--stats", action="store_true",
                        help="Show CES distribution statistics")
    parser.add_argument("--dry-run", action="store_true",
                        help="Calculate without writing results")
    parser.add_argument("--weights", type=str,
                        help="Custom weights as JSON string")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Verbose output")

    args = parser.parse_args()

    # Parse custom weights if provided
    custom_weights = None
    if args.weights:
        try:
            custom_weights = json.loads(args.weights)
        except json.JSONDecodeError:
            print(f"Error: Invalid JSON in weights: {args.weights}")
            sys.exit(1)

    # Load tasks
    tasks = load_tasks_from_ledger(period=args.period, agent=args.agent)

    if args.task_id:
        # Single task mode
        task = next((t for t in tasks if t.get("task_id") == args.task_id), None)
        if not task:
            # Create minimal task from ID
            task = {"task_id": args.task_id, "status": "unknown"}

        result = calculate_ces(task, agent_weights=custom_weights)
        print(json.dumps(result, indent=2))

    elif args.stats:
        # Stats mode
        ces_results = [calculate_ces(t, agent_weights=custom_weights) for t in tasks]
        stats = get_ces_stats(ces_results)
        stats["period"] = args.period
        stats["agent_filter"] = args.agent
        print(json.dumps(stats, indent=2))

    else:
        # Batch mode
        if not tasks:
            print("No tasks found in the specified period")
            return

        ces_results = calculate_ces_batch(tasks)

        if args.verbose:
            for task in ces_results:
                cr = task["ces_result"]
                print(f"{cr['task_id']}: CES={cr['ces']:.3f} "
                      f"(SR={cr['components']['success_rate']:.2f} "
                      f"QS={cr['components']['quality_score']:.2f} "
                      f"EF={cr['components']['efficiency']:.2f} "
                      f"IM={cr['components']['impact']:.2f})")

        stats = get_ces_stats([t["ces_result"] for t in ces_results])
        print(f"\nCES Statistics ({len(ces_results)} tasks):")
        print(f"  Mean: {stats['mean']:.4f}")
        print(f"  Median: {stats['median']:.4f}")
        print(f"  Std Dev: {stats['std_dev']:.4f}" if stats['std_dev'] else "  Std Dev: N/A")
        print(f"  Range: [{stats['min']:.4f}, {stats['max']:.4f}]")
        print(f"\nDistribution:")
        print(f"  Excellent (0.9+): {stats['distribution']['excellent_90+']}")
        print(f"  Good (0.7-0.9): {stats['distribution']['good_70_89']}")
        print(f"  Acceptable (0.5-0.7): {stats['distribution']['acceptable_50_69']}")
        print(f"  Poor (<0.5): {stats['distribution']['poor_below_50']}")

        if args.dry_run:
            print("\n(Dry run - results not persisted)")


if __name__ == "__main__":
    main()
