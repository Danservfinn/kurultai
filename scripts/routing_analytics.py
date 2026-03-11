#!/usr/bin/env python3
"""
Routing Analytics - Shared routing analysis utilities.

Consolidates routing analysis functions from:
- routing_audit.py
- routing_outcomes.py
- routing_accuracy_tracker.py

Usage:
    from routing_analytics import read_routing_decisions, compute_routing_metrics

    decisions = read_routing_decisions(hours_back=24)
    metrics = compute_routing_metrics(decisions)

    # Detect retry storms (tasks repeatedly failing on same agent)
    storms = detect_retry_storms(hours_back=2)
"""

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import defaultdict
from dataclasses import dataclass, field


# Default paths — must match task_intake.py's ROUTING_LOG
ROUTING_DECISIONS_PATH = Path.home() / ".openclaw" / "agents" / "main" / "logs" / "routing-decisions.jsonl"


@dataclass
class RoutingDecision:
    """Represents a single routing decision."""
    timestamp: datetime
    task_id: str
    task_text: str
    routed_agent: str
    optimal_agent: Optional[str] = None
    confidence: float = 0.0
    source: str = "keyword"  # keyword, llm, explicit, skill_reroute
    skill_hint: Optional[str] = None
    success: Optional[bool] = None
    latency_ms: int = 0
    idle_agents: Optional[List[str]] = None
    would_overflow: bool = False
    domain: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict) -> 'RoutingDecision':
        """Create from dictionary.

        Handles both legacy format (timestamp/task_id/routed_agent) and
        current format (ts/task/dest/method) from task_intake.py.
        """
        # Handle current JSONL format: ts, task, dest, method
        ts_raw = data.get('ts') or data.get('timestamp', datetime.now().isoformat())
        task_text = data.get('task') or data.get('task_text', '')
        routed_agent = data.get('dest') or data.get('routed_agent', '')
        method = data.get('method') or data.get('source', 'keyword')

        return cls(
            timestamp=datetime.fromisoformat(ts_raw),
            task_id=data.get('task_id', ''),
            task_text=task_text,
            routed_agent=routed_agent,
            optimal_agent=data.get('optimal_agent'),
            confidence=data.get('confidence', 0.0),
            source=method,
            skill_hint=data.get('skill_hint'),
            success=data.get('success'),
            latency_ms=data.get('latency_ms', 0),
            idle_agents=data.get('idle_agents'),
            would_overflow=data.get('would_overflow', False),
            domain=data.get('domain'),
        )


def read_routing_decisions(
    hours_back: float = 24,
    path: Optional[Path] = None
) -> List[RoutingDecision]:
    """Read routing decisions from JSONL file.

    Args:
        hours_back: How many hours of history to read
        path: Optional custom path to decisions file

    Returns:
        List of RoutingDecision objects
    """
    path = path or ROUTING_DECISIONS_PATH

    if not path.exists():
        return []

    cutoff = datetime.now() - timedelta(hours=hours_back)
    decisions = []

    try:
        with open(path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                    decision = RoutingDecision.from_dict(data)

                    if decision.timestamp >= cutoff:
                        decisions.append(decision)
                except (json.JSONDecodeError, ValueError):
                    continue
    except Exception as e:
        print(f"Error reading routing decisions: {e}")

    return decisions


def compute_routing_metrics(
    decisions: List[RoutingDecision]
) -> Dict[str, Any]:
    """Compute aggregate routing metrics from decisions.

    Args:
        decisions: List of RoutingDecision objects

    Returns:
        Dict with metrics including:
        - total_decisions: Total count
        - by_agent: Counts per agent
        - by_source: Counts by source type
        - accuracy: Overall routing accuracy (if ground truth available)
        - avg_confidence: Average confidence score
    """
    if not decisions:
        return {
            "total_decisions": 0,
            "by_agent": {},
            "by_source": {},
            "accuracy": None,
            "avg_confidence": 0.0
        }

    by_agent = defaultdict(int)
    by_source = defaultdict(int)
    confidence_sum = 0.0
    accuracy_matches = 0
    accuracy_total = 0

    for d in decisions:
        by_agent[d.routed_agent] += 1
        by_source[d.source] += 1
        confidence_sum += d.confidence

        if d.optimal_agent is not None:
            accuracy_total += 1
            if d.routed_agent == d.optimal_agent:
                accuracy_matches += 1

    metrics = {
        "total_decisions": len(decisions),
        "by_agent": dict(by_agent),
        "by_source": dict(by_source),
        "avg_confidence": confidence_sum / len(decisions),
        "accuracy": accuracy_matches / accuracy_total if accuracy_total > 0 else None
    }

    return metrics


def compute_missed_opportunities(
    decisions: List[RoutingDecision]
) -> List[Dict[str, Any]]:
    """Identify routing decisions where a better agent was available.

    Args:
        decisions: List of RoutingDecision objects

    Returns:
        List of missed opportunity dicts with:
        - task_id: Task ID
        - routed_agent: Agent that was chosen
        - optimal_agent: Agent that should have been chosen
        - confidence: Confidence score
    """
    missed = []

    for d in decisions:
        if d.optimal_agent is not None and d.routed_agent != d.optimal_agent:
            missed.append({
                "task_id": d.task_id,
                "task_text": d.task_text[:100],
                "routed_agent": d.routed_agent,
                "optimal_agent": d.optimal_agent,
                "confidence": d.confidence
            })

    return missed


def compute_agent_workload(
    decisions: List[RoutingDecision]
) -> Dict[str, Dict[str, int]]:
    """Compute workload distribution by agent.

    Args:
        decisions: List of RoutingDecision objects

    Returns:
        Dict mapping agent to workload stats:
        - total: Total tasks routed to agent
        - by_source: Breakdown by source type
    """
    workload = defaultdict(lambda: {"total": 0, "by_source": defaultdict(int)})

    for d in decisions:
        workload[d.routed_agent]["total"] += 1
        workload[d.routed_agent]["by_source"][d.source] += 1

    # Convert defaultdicts to regular dicts
    return {
        agent: {
            "total": data["total"],
            "by_source": dict(data["by_source"])
        }
        for agent, data in workload.items()
    }


def get_routing_trends(
    decisions: List[RoutingDecision],
    bucket_hours: int = 6
) -> List[Dict[str, Any]]:
    """Get routing trends over time.

    Args:
        decisions: List of RoutingDecision objects
        bucket_hours: Hours per time bucket

    Returns:
        List of time bucket dicts with counts by agent
    """
    if not decisions:
        return []

    # Sort by timestamp
    sorted_decisions = sorted(decisions, key=lambda d: d.timestamp)

    # Determine bucket boundaries
    start_time = sorted_decisions[0].timestamp
    end_time = sorted_decisions[-1].timestamp

    buckets = []
    current_bucket_start = start_time

    while current_bucket_start <= end_time:
        bucket_end = current_bucket_start + timedelta(hours=bucket_hours)

        bucket_decisions = [
            d for d in sorted_decisions
            if current_bucket_start <= d.timestamp < bucket_end
        ]

        if bucket_decisions:
            by_agent = defaultdict(int)
            for d in bucket_decisions:
                by_agent[d.routed_agent] += 1

            buckets.append({
                "start": current_bucket_start.isoformat(),
                "end": bucket_end.isoformat(),
                "count": len(bucket_decisions),
                "by_agent": dict(by_agent)
            })

        current_bucket_start = bucket_end

    return buckets


def compute_skill_effectiveness(
    decisions: List[RoutingDecision]
) -> Dict[str, Dict[str, Any]]:
    """Compute routing effectiveness by skill hint.

    Args:
        decisions: List of RoutingDecision objects

    Returns:
        Dict mapping skill to effectiveness metrics
    """
    skill_stats = defaultdict(lambda: {"count": 0, "agents": defaultdict(int), "confidence_sum": 0.0})

    for d in decisions:
        if d.skill_hint:
            skill_stats[d.skill_hint]["count"] += 1
            skill_stats[d.skill_hint]["agents"][d.routed_agent] += 1
            skill_stats[d.skill_hint]["confidence_sum"] += d.confidence

    return {
        skill: {
            "count": data["count"],
            "agents": dict(data["agents"]),
            "avg_confidence": data["confidence_sum"] / data["count"] if data["count"] > 0 else 0
        }
        for skill, data in skill_stats.items()
    }


# =============================================================================
# Retry Storm Detection
# =============================================================================

_RETRY_PREFIX_RE = re.compile(r'^RETRY:\s*')


def _normalize_task_name(task_text: str) -> str:
    """Strip RETRY: prefix and status suffixes to get base task identity."""
    name = _RETRY_PREFIX_RE.sub('', task_text).strip()
    # Strip common suffixes like .executing, .failed, .done
    for suffix in ('.executing', '.failed', '.done', '.md'):
        if name.endswith(suffix):
            name = name[:-len(suffix)]
    return name


def detect_retry_storms(
    hours_back: float = 2,
    min_retries: int = 3,
    path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Detect tasks repeatedly routed to the same (likely failing) agent.

    A retry storm is when the same base task appears 3+ times routed to the
    same agent via explicit routing within the time window. This indicates
    the task keeps failing and being re-created without redistribution.

    Args:
        hours_back: Hours of history to analyze
        min_retries: Minimum repeat count to flag as storm
        path: Optional custom path to routing decisions JSONL

    Returns:
        List of storm dicts:
        - base_task: Normalized task name
        - agent: Agent receiving repeated retries
        - count: Number of times routed
        - idle_alternatives: Agents that were idle during routing
        - first_seen / last_seen: Timestamps
        - recommendation: Suggested action
    """
    path = path or ROUTING_DECISIONS_PATH
    if not path.exists():
        return []

    cutoff = datetime.now() - timedelta(hours=hours_back)

    # Group by (normalized_task, agent)
    storm_map: Dict[tuple, Dict] = defaultdict(lambda: {
        "count": 0,
        "idle_alternatives": set(),
        "first_seen": None,
        "last_seen": None,
        "would_overflow_count": 0,
    })

    try:
        with open(path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                ts_raw = data.get('ts', '')
                try:
                    ts = datetime.fromisoformat(ts_raw)
                except (ValueError, TypeError):
                    continue

                if ts < cutoff:
                    continue

                task_text = data.get('task', '')
                dest = data.get('dest', '')
                method = data.get('method', '')
                idle = data.get('idle_agents', [])
                would_overflow = data.get('would_overflow', False)

                # Only track explicit routing (retries come in as explicit)
                if method != 'explicit':
                    continue

                base = _normalize_task_name(task_text)
                key = (base, dest)
                entry = storm_map[key]
                entry["count"] += 1
                if idle:
                    entry["idle_alternatives"].update(a for a in idle if a != dest)
                if would_overflow:
                    entry["would_overflow_count"] += 1
                if entry["first_seen"] is None or ts < entry["first_seen"]:
                    entry["first_seen"] = ts
                if entry["last_seen"] is None or ts > entry["last_seen"]:
                    entry["last_seen"] = ts
    except Exception:
        return []

    # Filter to storms (>= min_retries)
    storms = []
    for (base_task, agent), info in storm_map.items():
        if info["count"] >= min_retries:
            idle_alts = sorted(info["idle_alternatives"])
            storms.append({
                "base_task": base_task,
                "agent": agent,
                "count": info["count"],
                "idle_alternatives": idle_alts,
                "first_seen": info["first_seen"].isoformat() if info["first_seen"] else None,
                "last_seen": info["last_seen"].isoformat() if info["last_seen"] else None,
                "would_overflow_count": info["would_overflow_count"],
                "recommendation": (
                    f"Redistribute to {idle_alts[0] if idle_alts else 'any idle agent'} — "
                    f"{agent} has failed this task {info['count']}x"
                ),
            })

    # Sort by count descending (worst storms first)
    storms.sort(key=lambda s: s["count"], reverse=True)
    return storms


def compute_explicit_routing_ratio(
    hours_back: float = 1,
    path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Compute the ratio of explicit vs keyword-routed tasks.

    High explicit routing (>80%) suggests the keyword table is being bypassed,
    meaning auto-routing improvements won't have impact until callers stop
    hardcoding agent assignments.

    Returns:
        Dict with total, explicit_count, keyword_count, explicit_pct
    """
    path = path or ROUTING_DECISIONS_PATH
    if not path.exists():
        return {"total": 0, "explicit_count": 0, "keyword_count": 0, "explicit_pct": 0.0}

    cutoff = datetime.now() - timedelta(hours=hours_back)
    total = 0
    explicit = 0
    keyword = 0
    by_method = defaultdict(int)

    try:
        with open(path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts_raw = data.get('ts', '')
                try:
                    ts = datetime.fromisoformat(ts_raw)
                except (ValueError, TypeError):
                    continue
                if ts < cutoff:
                    continue

                total += 1
                method = data.get('method', 'unknown')
                by_method[method] += 1
                if method == 'explicit':
                    explicit += 1
                elif method in ('keyword', 'keyword_fallback', 'llm'):
                    keyword += 1
    except Exception:
        pass

    return {
        "total": total,
        "explicit_count": explicit,
        "keyword_count": keyword,
        "explicit_pct": (explicit / total * 100) if total > 0 else 0.0,
        "by_method": dict(by_method),
    }


if __name__ == "__main__":
    import sys

    print("=== Routing Analytics Report ===\n")

    # Retry storm detection
    storms = detect_retry_storms(hours_back=2)
    if storms:
        print(f"RETRY STORMS DETECTED ({len(storms)}):")
        for s in storms[:5]:
            print(f"  {s['base_task'][:60]} -> {s['agent']} x{s['count']}")
            print(f"    Idle alternatives: {', '.join(s['idle_alternatives']) or 'none'}")
            print(f"    Recommendation: {s['recommendation']}")
        print()
    else:
        print("No retry storms detected (last 2h)\n")

    # Explicit routing ratio
    ratio = compute_explicit_routing_ratio(hours_back=1)
    print(f"EXPLICIT ROUTING RATIO (1h):")
    print(f"  Total: {ratio['total']}, Explicit: {ratio['explicit_count']} ({ratio['explicit_pct']:.0f}%)")
    print(f"  By method: {ratio['by_method']}")
    print()

    # Basic metrics
    decisions = read_routing_decisions(hours_back=6)
    if decisions:
        metrics = compute_routing_metrics(decisions)
        print(f"ROUTING METRICS (6h):")
        print(f"  Total decisions: {metrics['total_decisions']}")
        print(f"  By agent: {metrics['by_agent']}")
        print(f"  By source: {metrics['by_source']}")
    else:
        print("No routing decisions found (last 6h)")
