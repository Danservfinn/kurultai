#!/usr/bin/env python3
"""
routing_accuracy_tracker.py — Aggregate routing accuracy metrics.

Computes routing accuracy from ROUTING_PREDICTED + SCORED events, measuring
whether tasks are being routed to the optimal agent.

Metrics:
- optimal_rate: % of tasks routed to the best agent
- top2_rate: % of tasks routed to top-2 agents
- avg_score: Average routing accuracy score (0-3 scale)

Usage:
    python3 routing_accuracy_tracker.py           # Print current metrics
    python3 routing_accuracy_tracker.py --update  # Update capability-scores.json
    python3 routing_accuracy_tracker.py --details # Show per-agent breakdown
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from kurultai_paths import LOGS_DIR, TASK_LEDGER
    from kurultai_ledger import read_ledger as _read_ledger
    from kurultai_paths import TASK_LEDGER as _TASK_LEDGER
except ImportError:
    LOGS_DIR = Path("/Users/kublai/.openclaw/agents/main/logs")
    TASK_LEDGER = LOGS_DIR / "task-ledger.jsonl"

    def _read_ledger(hours=None):
        return []

CAPABILITY_SCORES_FILE = LOGS_DIR / "capability-scores.json"
ROUTING_ACCURACY_FILE = LOGS_DIR / "routing-accuracy.json"
ROLLING_DAYS = 7


def load_routing_predictions(events: list) -> dict:
    """Load ROUTING_PREDICTED events indexed by task_id."""
    predictions = {}
    for ev in events:
        if ev.get("event") == "ROUTING_PREDICTED":
            task_id = ev.get("task_id")
            if task_id:
                predictions[task_id] = ev
    return predictions


def compute_routing_accuracy_score(assigned_agent: str, prediction: dict) -> tuple:
    """Compute routing accuracy score from prediction.

    Returns:
        (score, was_optimal, rank)
        - score: 0-3 (3=optimal, 2=2nd, 1=3rd+, 0=unknown)
        - was_optimal: bool
        - rank: 1-based rank of assigned agent
    """
    rankings = prediction.get("agent_rankings", prediction.get("rankings", {}))
    if not rankings:
        return 0, False, None

    optimal_agent = prediction.get("optimal_agent")
    was_optimal = (assigned_agent == optimal_agent)

    # Sort agents by score descending
    sorted_agents = sorted(
        rankings.keys(),
        key=lambda a: rankings.get(a, 0),
        reverse=True
    )

    try:
        rank = sorted_agents.index(assigned_agent) + 1
    except ValueError:
        return 0, False, None

    # Score mapping
    if rank == 1:
        return 3, was_optimal, rank
    elif rank == 2:
        return 2, was_optimal, rank
    else:
        return 1, was_optimal, rank


def compute_routing_metrics(hours: int = None) -> dict:
    """Compute routing accuracy metrics from events.

    Returns:
        {
            "overall": {optimal_rate, top2_rate, avg_score, sample_count},
            "by_agent": {agent: {optimal_rate, top2_rate, avg_score, sample_count}},
            "by_category": {...},
            "trend": [{date, optimal_rate, sample_count}, ...],
        }
    """
    hours = hours or ROLLING_DAYS * 24
    events = _read_ledger(hours=hours)

    # Get predictions
    predictions = load_routing_predictions(events)

    # Get scored events
    scored_events = [e for e in events if e.get("event") == "SCORED"]

    # Build per-task accuracy data
    task_accuracy = []
    agent_accuracy = defaultdict(list)
    category_accuracy = defaultdict(list)

    for score_ev in scored_events:
        task_id = score_ev.get("task_id")
        assigned_agent = score_ev.get("agent", "unknown")

        prediction = predictions.get(task_id)
        if not prediction:
            continue

        score, was_optimal, rank = compute_routing_accuracy_score(
            assigned_agent, prediction
        )

        accuracy_data = {
            "task_id": task_id,
            "agent": assigned_agent,
            "score": score,
            "was_optimal": was_optimal,
            "rank": rank,
            "confidence": prediction.get("confidence", 0),
            "ts": score_ev.get("ts", ""),
        }

        task_accuracy.append(accuracy_data)
        agent_accuracy[assigned_agent].append(accuracy_data)

        # Category detection (simplified)
        category = detect_category_from_prediction(prediction, assigned_agent)
        if category:
            category_accuracy[category].append(accuracy_data)

    if not task_accuracy:
        return {
            "overall": {"sample_count": 0},
            "by_agent": {},
            "by_category": {},
            "trend": [],
        }

    # Compute overall metrics
    overall = compute_aggregate_metrics(task_accuracy)

    # Compute per-agent metrics
    by_agent = {}
    for agent, data_list in agent_accuracy.items():
        if len(data_list) >= 3:  # Min samples for reliable metrics
            by_agent[agent] = compute_aggregate_metrics(data_list)

    # Compute per-category metrics
    by_category = {}
    for category, data_list in category_accuracy.items():
        if len(data_list) >= 3:
            by_category[category] = compute_aggregate_metrics(data_list)

    # Compute daily trend
    trend = compute_trend(task_accuracy)

    return {
        "overall": overall,
        "by_agent": by_agent,
        "by_category": by_category,
        "trend": trend,
        "computed_at": datetime.now().isoformat(),
    }


def compute_aggregate_metrics(data_list: list) -> dict:
    """Compute aggregate metrics from list of accuracy data."""
    n = len(data_list)
    if n == 0:
        return {"sample_count": 0}

    optimal_count = sum(1 for d in data_list if d.get("was_optimal"))
    top2_count = sum(1 for d in data_list if d.get("score", 0) >= 2)
    total_score = sum(d.get("score", 0) for d in data_list)
    avg_rank = sum(d.get("rank", 0) for d in data_list if d.get("rank")) / max(
        sum(1 for d in data_list if d.get("rank")), 1
    )
    avg_confidence = sum(d.get("confidence", 0) for d in data_list) / n

    return {
        "optimal_rate": round(optimal_count / n, 3),
        "top2_rate": round(top2_count / n, 3),
        "avg_score": round(total_score / n, 2),
        "avg_rank": round(avg_rank, 1),
        "avg_confidence": round(avg_confidence, 3),
        "sample_count": n,
    }


def compute_trend(data_list: list) -> list:
    """Compute daily trend of routing accuracy."""
    by_date = defaultdict(list)
    for d in data_list:
        ts = d.get("ts", "")
        try:
            date = datetime.fromisoformat(ts).strftime("%Y-%m-%d")
            by_date[date].append(d)
        except (ValueError, TypeError):
            continue

    trend = []
    for date in sorted(by_date.keys())[-7:]:  # Last 7 days
        metrics = compute_aggregate_metrics(by_date[date])
        trend.append({
            "date": date,
            "optimal_rate": metrics["optimal_rate"],
            "top2_rate": metrics["top2_rate"],
            "avg_score": metrics["avg_score"],
            "sample_count": metrics["sample_count"],
        })

    return trend


def detect_category_from_prediction(prediction: dict, agent: str) -> str:
    """Detect task category from prediction rankings."""
    # Use the ranking scores to infer category
    rankings = prediction.get("agent_rankings", prediction.get("rankings", {}))

    # Map agents to their primary categories
    agent_categories = {
        "temujin": "code",
        "jochi": "security",
        "mongke": "research",
        "chagatai": "content",
        "ogedei": "ops",
        "kublai": "routing",
        "tolui": "verification",
    }

    # Return the category of the highest-ranked agent
    if rankings:
        top_agent = max(rankings.keys(), key=lambda a: rankings.get(a, 0))
        return agent_categories.get(top_agent)

    return agent_categories.get(agent)


def update_capability_scores(metrics: dict) -> None:
    """Update capability-scores.json with routing accuracy metrics."""
    if not CAPABILITY_SCORES_FILE.exists():
        print("capability-scores.json not found, skipping merge")
        return

    try:
        with open(CAPABILITY_SCORES_FILE) as f:
            scores = json.load(f)
    except Exception:
        return

    # Add routing accuracy to each agent
    for agent, agent_metrics in metrics.get("by_agent", {}).items():
        if agent in scores:
            scores[agent]["routing_accuracy"] = {
                "optimal_rate": agent_metrics.get("optimal_rate", 0),
                "top2_rate": agent_metrics.get("top2_rate", 0),
                "avg_score": agent_metrics.get("avg_score", 0),
                "sample_count": agent_metrics.get("sample_count", 0),
            }

    # Add overall routing accuracy
    overall = metrics.get("overall", {})
    if overall.get("sample_count", 0) > 0:
        scores["_routing_overall"] = {
            "optimal_rate": overall.get("optimal_rate", 0),
            "top2_rate": overall.get("top2_rate", 0),
            "avg_score": overall.get("avg_score", 0),
            "sample_count": overall.get("sample_count", 0),
        }

    with open(CAPABILITY_SCORES_FILE, "w") as f:
        json.dump(scores, f, indent=2)

    print(f"Updated {CAPABILITY_SCORES_FILE} with routing accuracy")


def save_metrics(metrics: dict) -> None:
    """Save metrics to routing-accuracy.json."""
    with open(ROUTING_ACCURACY_FILE, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"Saved metrics to {ROUTING_ACCURACY_FILE}")


def print_metrics(metrics: dict, details: bool = False) -> None:
    """Print metrics in human-readable format."""
    overall = metrics.get("overall", {})
    sample_count = overall.get("sample_count", 0)

    if sample_count == 0:
        print("No routing accuracy data available.")
        print("\nNote: Requires ROUTING_PREDICTED events from llm_routing_judge.py")
        return

    print("\n=== Routing Accuracy Metrics (7-day rolling) ===\n")

    print("Overall:")
    print(f"  Optimal Rate: {overall.get('optimal_rate', 0):.1%}")
    print(f"  Top-2 Rate:   {overall.get('top2_rate', 0):.1%}")
    print(f"  Avg Score:    {overall.get('avg_score', 0):.2f}/3")
    print(f"  Avg Rank:     {overall.get('avg_rank', 0):.1f}")
    print(f"  Confidence:   {overall.get('avg_confidence', 0):.0%}")
    print(f"  Sample Count: {sample_count}")

    if details:
        print("\nBy Agent:")
        for agent, agent_metrics in sorted(metrics.get("by_agent", {}).items()):
            n = agent_metrics.get("sample_count", 0)
            optimal = agent_metrics.get("optimal_rate", 0)
            top2 = agent_metrics.get("top2_rate", 0)
            avg = agent_metrics.get("avg_score", 0)
            print(f"  {agent}: optimal={optimal:.0%} top2={top2:.0%} avg={avg:.1f}/3 ({n} tasks)")

        print("\nBy Category:")
        for category, cat_metrics in sorted(metrics.get("by_category", {}).items()):
            n = cat_metrics.get("sample_count", 0)
            optimal = cat_metrics.get("optimal_rate", 0)
            print(f"  {category}: optimal={optimal:.0%} ({n} tasks)")

    trend = metrics.get("trend", [])
    if trend:
        print("\nTrend (7 days):")
        for day in trend[-7:]:
            date = day.get("date", "?")
            optimal = day.get("optimal_rate", 0)
            n = day.get("sample_count", 0)
            bar = "#" * int(optimal * 20)
            print(f"  {date}: {optimal:.0%} {bar} ({n})")


def main():
    parser = argparse.ArgumentParser(description="Routing accuracy metrics tracker")
    parser.add_argument("--update", action="store_true",
                        help="Update capability-scores.json with routing accuracy")
    parser.add_argument("--details", action="store_true",
                        help="Show per-agent and per-category breakdown")
    parser.add_argument("--hours", type=int, default=24 * 7,
                        help="Hours to look back (default: 168 = 7 days)")
    args = parser.parse_args()

    metrics = compute_routing_metrics(hours=args.hours)

    if args.update:
        save_metrics(metrics)
        update_capability_scores(metrics)
    else:
        print_metrics(metrics, details=args.details)

    return 0


if __name__ == "__main__":
    sys.exit(main())
