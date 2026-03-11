#!/usr/bin/env python3
"""
pipeline_health.py — Throughput metrics from task-ledger.jsonl.

Computes 5 metrics that expose pipeline bottlenecks, pending time, and
velocity trends. Intended for injection into reflections and brainstorm prompts.

Usage:
    from pipeline_health import format_pipeline_health
    print(format_pipeline_health("temujin", hours=1))
"""

import json
import os
import re
import sys
import time as _time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kurultai_paths import TASK_LEDGER, AGENTS_DIR, VALID_AGENTS
from kurultai_ledger import read_ledger as _ledger_read

# In-process ledger cache — avoids re-reading the full file within a single
# format_pipeline_health() call. Keyed by hours parameter, 10s TTL.
_ledger_cache = {}  # key: hours -> (timestamp, events_list)
_CACHE_TTL_S = 10


def _clear_ledger_cache():
    """Clear the in-process ledger cache."""
    _ledger_cache.clear()


def _read_ledger(hours=None):
    """Read task-ledger events optionally filtered by time window (cached)."""
    cache_key = hours
    now = _time.time()

    # Check cache
    if cache_key in _ledger_cache:
        cached_ts, cached_events = _ledger_cache[cache_key]
        if now - cached_ts < _CACHE_TTL_S:
            return cached_events

    events = _ledger_read(hours=hours)
    _ledger_cache[cache_key] = (now, events)
    return events


def _task_file_epoch(agent, task_id):
    """Extract creation epoch from task filename as fallback for missing QUEUED events."""
    task_dir = AGENTS_DIR / agent / "tasks"
    if not task_dir.exists():
        return None
    # task_id may be like "abc123" — search files with that prefix
    try:
        for fname in os.listdir(str(task_dir)):
            if task_id[:8] in fname:
                m = re.search(r"-(\d{10,})", fname)
                if m:
                    return int(m.group(1))
    except Exception:
        pass
    return None


def pending_duration(agent, hours=1):
    """Compute p50/p95 of QUEUED→EXECUTING delta for agent in last N hours.

    Returns dict with keys: p50_s, p95_s, sample_count, agent.
    """
    events = _read_ledger(hours=hours * 2)  # wider window to catch QUEUED before window start

    # Build queued_ts per task_id
    queued_ts = {}
    for e in events:
        if e.get("agent") == agent and e.get("event") == "QUEUED":
            try:
                queued_ts[e["task_id"]] = datetime.fromisoformat(e["ts"])
            except (KeyError, ValueError):
                pass

    cutoff = datetime.now() - timedelta(hours=hours)
    durations = []
    for e in events:
        if e.get("agent") == agent and e.get("event") == "EXECUTING":
            try:
                exec_ts = datetime.fromisoformat(e["ts"])
                if exec_ts < cutoff:
                    continue
                tid = e.get("task_id")
                if tid and tid in queued_ts:
                    delta = (exec_ts - queued_ts[tid]).total_seconds()
                    if 0 <= delta < 7200:  # sanity: ignore deltas > 2h
                        durations.append(delta)
            except (ValueError, TypeError):
                pass

    if not durations:
        return {"p50_s": None, "p95_s": None, "sample_count": 0, "agent": agent}

    durations.sort()
    n = len(durations)
    p50 = durations[int(n * 0.5)]
    p95 = durations[min(int(n * 0.95), n - 1)]
    return {"p50_s": round(p50, 1), "p95_s": round(p95, 1), "sample_count": n, "agent": agent}


def recovery_churn(agent, hours=1):
    """Count RECOVERED events, sum stale_age_s, compute churn ratio.

    Returns dict with keys: recoveries, completions, churn_ratio, total_stale_s.
    """
    all_churn = recovery_churn_all(hours=hours)
    return all_churn.get(agent, {
        "recoveries": 0, "completions": 0, "churn_ratio": 0,
        "total_stale_s": 0, "agent": agent,
    })


def recovery_churn_all(hours=1):
    """Compute churn metrics for ALL agents in a single pass.

    Returns dict mapping agent -> {recoveries, completions, churn_ratio, total_stale_s, agent}.
    """
    events = _read_ledger(hours=hours)
    rec_counts = defaultdict(int)
    comp_counts = defaultdict(int)
    stale_sums = defaultdict(float)

    for e in events:
        agent = e.get("agent")
        if not agent:
            continue
        ev = e.get("event")
        if ev == "RECOVERED":
            rec_counts[agent] += 1
            stale_sums[agent] += e.get("stale_age_s", 0)
        elif ev == "COMPLETED":
            comp_counts[agent] += 1

    result = {}
    for a in set(list(rec_counts) + list(comp_counts) + list(VALID_AGENTS)):
        n_rec = rec_counts.get(a, 0)
        n_comp = comp_counts.get(a, 0)
        result[a] = {
            "recoveries": n_rec,
            "completions": n_comp,
            "churn_ratio": round(n_rec / max(n_comp, 1), 2),
            "total_stale_s": stale_sums.get(a, 0),
            "agent": a,
        }
    return result


def throughput_velocity(agent, hours_current=1, hours_baseline=6):
    """Compare current completions/hour vs rolling baseline.

    Returns dict with keys: current_rate, baseline_rate, velocity_factor, trend.
    """
    # Current window
    events_current = _read_ledger(hours=hours_current)
    current_completions = sum(
        1 for e in events_current
        if e.get("agent") == agent and e.get("event") == "COMPLETED"
    )
    current_rate = current_completions / hours_current

    # Baseline window
    events_baseline = _read_ledger(hours=hours_baseline)
    baseline_completions = sum(
        1 for e in events_baseline
        if e.get("agent") == agent and e.get("event") == "COMPLETED"
    )
    baseline_rate = baseline_completions / hours_baseline

    if baseline_rate > 0:
        velocity_factor = round(current_rate / baseline_rate, 2)
    else:
        velocity_factor = 1.0 if current_rate == 0 else 2.0

    if velocity_factor >= 1.2:
        trend = "ACCELERATING"
    elif velocity_factor <= 0.8:
        trend = "DECELERATING"
    else:
        trend = "STEADY"

    return {
        "current_rate": round(current_rate, 2),
        "baseline_rate": round(baseline_rate, 2),
        "velocity_factor": velocity_factor,
        "trend": trend,
        "agent": agent,
    }


def bottleneck_index(hours=1):
    """Compute hours-to-clear for ALL agents.

    Returns dict mapping agent -> {pending, recovering, rate_per_hr, hours_to_clear}
    plus "bottleneck_agent" key.
    """
    events = _read_ledger(hours=hours)

    result = {}
    for a in VALID_AGENTS:
        completions = sum(1 for e in events if e.get("agent") == a and e.get("event") == "COMPLETED")
        rate = completions / max(hours, 1)

        # Count pending tasks from filesystem
        # Terminal state markers: .done, .failed, .resolved, .completed, .cancelled, .false-positive
        skip_patterns = ['.done', '.failed', '.resolved', '.completed', '.cancelled', '.false-positive']
        pending = 0
        executing = 0
        recovering = 0
        task_dir = AGENTS_DIR / a / "tasks"
        if task_dir.exists():
            try:
                for fname in os.listdir(str(task_dir)):
                    if not fname.endswith(".md"):
                        continue
                    # Skip terminal state files (including .done-{uuid}.md patterns)
                    if any(pattern in fname for pattern in skip_patterns):
                        continue
                    if ".recovering" in fname:
                        recovering += 1
                    elif fname.endswith(".executing.md"):
                        executing += 1
                    else:
                        pending += 1
            except Exception:
                pass

        # Backlog = waiting tasks only; executing tasks are already in-progress
        backlog = pending + recovering
        if rate > 0:
            hours_to_clear = round(backlog / rate, 1)
        else:
            hours_to_clear = float("inf") if backlog > 0 else 0.0

        result[a] = {
            "pending": pending,
            "executing": executing,
            "recovering": recovering,
            "rate_per_hr": round(rate, 2),
            "hours_to_clear": hours_to_clear,
        }

    # Find bottleneck (finite max, fallback to agent with most pending)
    finite_agents = {a: v for a, v in result.items() if v["hours_to_clear"] != float("inf")}
    if finite_agents:
        bottleneck = max(finite_agents, key=lambda a: finite_agents[a]["hours_to_clear"])
    else:
        bottleneck = max(result, key=lambda a: result[a]["pending"])
    result["bottleneck_agent"] = bottleneck

    # System-wide throughput
    all_completions = sum(1 for e in events if e.get("event") == "COMPLETED")
    result["system_throughput_per_hr"] = round(all_completions / max(hours, 1), 1)

    return result


def first_attempt_success(agent, hours=1):
    """Compute % of COMPLETED tasks with no prior RECOVERED event.

    Returns dict with keys: success_count, recovered_count, total, rate_pct.
    """
    events = _read_ledger(hours=hours)

    # Group events by task_id
    tasks = defaultdict(list)
    for e in events:
        if e.get("agent") == agent:
            tid = e.get("task_id")
            if tid:
                tasks[tid].append(e.get("event"))

    first_attempt = 0
    had_recovery = 0
    total_completed = 0
    for tid, task_events in tasks.items():
        if "COMPLETED" in task_events:
            total_completed += 1
            if "RECOVERED" in task_events:
                had_recovery += 1
            else:
                first_attempt += 1

    rate = round(first_attempt / max(total_completed, 1) * 100, 1)
    return {
        "success_count": first_attempt,
        "recovered_count": had_recovery,
        "total": total_completed,
        "rate_pct": rate,
        "agent": agent,
    }


def format_pipeline_health(agent, hours=1):
    """Return formatted markdown block (~150 tokens) for injection into reflections."""
    _clear_ledger_cache()  # Ensure fresh data for this invocation
    try:
        pending = pending_duration(agent, hours=hours)
        churn = recovery_churn(agent, hours=hours)
        velocity = throughput_velocity(agent, hours_current=hours, hours_baseline=6)
        bottleneck = bottleneck_index(hours=hours)
        first_ok = first_attempt_success(agent, hours=hours)
    except Exception as exc:
        return f"## Pipeline Health ({hours}h)\n(unavailable: {exc})\n"

    # Pending line
    if pending["p50_s"] is not None:
        p50_str = f"{pending['p50_s']/60:.1f}min"
        p95_str = f"{pending['p95_s']/60:.1f}min"
        pending_str = f"p50={p50_str} p95={p95_str}"
    else:
        pending_str = "no data"

    vel_factor = velocity["velocity_factor"]
    trend = velocity["trend"]
    churn_ratio = churn["churn_ratio"]
    first_rate = first_ok["rate_pct"]
    bottleneck_agent = bottleneck.get("bottleneck_agent", "?")
    bottleneck_htc = bottleneck.get(bottleneck_agent, {}).get("hours_to_clear", "?")
    system_tput = bottleneck.get("system_throughput_per_hr", "?")

    if isinstance(bottleneck_htc, float) and bottleneck_htc == float("inf"):
        bottleneck_htc_str = "∞"
    elif isinstance(bottleneck_htc, float):
        bottleneck_htc_str = f"{bottleneck_htc:.1f}h"
    else:
        bottleneck_htc_str = str(bottleneck_htc)

    # Pre-compute churn for all agents in one pass (avoids 6x event list scans)
    all_churn = recovery_churn_all(hours=hours)

    lines = [
        f"## Pipeline Health ({hours}h)",
        f"Pending: {pending_str} | Velocity: {vel_factor}x {trend}",
        f"Churn: {churn['recoveries']} recoveries (target: <0.5/completion) | 1st-attempt: {first_rate}%",
        f"Bottleneck: {bottleneck_agent} ({bottleneck_htc_str} to clear) | System throughput: {system_tput} tasks/hr",
        "",
        "| Agent    | Pending | Exec | Churn | Rate/hr | H-to-Clear |",
        "|----------|---------|------|-------|---------|------------|",
    ]
    for a in VALID_AGENTS:
        d = bottleneck.get(a, {})
        a_churn = all_churn.get(a, {"recoveries": 0})
        htc = d.get("hours_to_clear", 0)
        htc_str = "∞" if htc == float("inf") else f"{htc:.1f}h"
        lines.append(
            f"| {a:<8} | {d.get('pending', 0):<7} | {d.get('executing', 0):<4} | "
            f"{a_churn['recoveries']:<5} | {d.get('rate_per_hr', 0):<7} | {htc_str:<10} |"
        )

    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Pipeline health metrics")
    parser.add_argument("--agent", default="temujin", help="Agent name")
    parser.add_argument("--hours", type=int, default=1, help="Lookback hours")
    args = parser.parse_args()
    print(format_pipeline_health(args.agent, hours=args.hours))
