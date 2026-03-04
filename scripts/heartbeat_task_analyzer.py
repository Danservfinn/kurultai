#!/usr/bin/env python3
"""
Heartbeat Task Analyzer - Reads tick (5m) and tock (30m) data,
aggregates trends, detects anomalies, and generates a compact
markdown summary for injection into agent reflection prompts.

Usage:
    from heartbeat_task_analyzer import generate_review
    review = generate_review("temujin", hours=1)
"""

import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path.home() / ".openclaw/agents/main"
TICKS_FILE = BASE / "logs/ticks.jsonl"
TOCK_LATEST = BASE / "logs/tock/latest.json"
WATCHDOG_LOG = BASE / "logs/watchdog.log"


def parse_tick_data(hours=1):
    """Read tick data from ticks.jsonl (preferred) or watchdog.log (fallback)."""
    ticks = []
    entries_needed = hours * 12  # 12 ticks per hour (every 5m)

    # Primary: structured JSONL
    if TICKS_FILE.exists() and TICKS_FILE.stat().st_size > 0:
        try:
            with open(TICKS_FILE) as f:
                lines = f.readlines()
            for line in lines[-entries_needed:]:
                line = line.strip()
                if line:
                    try:
                        ticks.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
            if ticks:
                return ticks
        except Exception:
            pass

    # Fallback: parse watchdog.log structured lines
    if WATCHDOG_LOG.exists():
        try:
            with open(WATCHDOG_LOG) as f:
                lines = f.readlines()
            cutoff = datetime.now() - timedelta(hours=hours)
            for line in lines[-entries_needed * 2:]:  # read extra for safety
                line = line.strip()
                if "TICK |" not in line and "WATCHDOG |" not in line:
                    continue
                # Parse: [2026-03-04 01:05:00] TICK | status=X | pid=Y | ...
                ts_match = re.match(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]', line)
                if not ts_match:
                    continue
                try:
                    ts = datetime.strptime(ts_match.group(1), "%Y-%m-%d %H:%M:%S")
                    if ts < cutoff:
                        continue
                except ValueError:
                    continue

                # Extract key=value pairs
                fields = {}
                for kv in re.findall(r'(\w+)=([^\s|]+)', line):
                    fields[kv[0]] = kv[1]

                ticks.append({
                    "ts": ts.isoformat(),
                    "gateway": {
                        "http": int(fields.get("http", 0) or 0),
                        "latency_ms": int(fields.get("latency", "0").replace("ms", "") or 0),
                    },
                    "process": {
                        "cpu_pct": float(fields.get("cpu", "0").replace("%", "") or 0),
                        "mem_pct": float(fields.get("mem", "0").replace("%", "") or 0),
                        "rss_kb": int(fields.get("rss", "0").replace("MB", "").replace("KB", "") or 0),
                    },
                    "errors": {
                        "last_5m": int(fields.get("errors", 0) or fields.get("errors_5m", 0) or 0),
                    },
                    "services": {
                        "neo4j": fields.get("neo4j", "unknown"),
                        "redis": fields.get("redis", "unknown"),
                    },
                    "tasks": {
                        "pending": int(fields.get("tasks_pending", 0) or 0),
                        "dispatched": int(fields.get("tasks_dispatched", 0) or 0),
                    },
                    "decision": fields.get("status", "unknown"),
                    "action": fields.get("action", "none"),
                })
        except Exception:
            pass

    return ticks


def parse_tock_data():
    """Read latest tock snapshot."""
    if not TOCK_LATEST.exists():
        return None
    try:
        # Resolve symlink
        target = TOCK_LATEST.resolve() if TOCK_LATEST.is_symlink() else TOCK_LATEST
        if not target.exists():
            return None
        with open(target) as f:
            return json.load(f)
    except Exception:
        return None


def compute_trend(values, label=""):
    """Compute trend direction from a time series."""
    if len(values) < 3:
        return "insufficient data"

    n = len(values)
    x_mean = (n - 1) / 2
    y_mean = sum(values) / n

    numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    denominator = sum((i - x_mean) ** 2 for i in range(n))

    if denominator == 0:
        return "stable"

    slope = numerator / denominator
    relative_slope = slope / max(y_mean, 0.01)

    if abs(relative_slope) < 0.05:
        return "stable"
    elif relative_slope > 0.2:
        return "rising sharply"
    elif relative_slope > 0.05:
        return "rising"
    elif relative_slope < -0.2:
        return "falling sharply"
    else:
        return "falling"


def aggregate_trends(ticks):
    """Compute infrastructure trends from tick data."""
    if not ticks:
        return {}

    n = len(ticks)
    cpu_vals = [t.get("process", {}).get("cpu_pct", 0) for t in ticks]
    mem_vals = [t.get("process", {}).get("mem_pct", 0) for t in ticks]
    lat_vals = [t.get("gateway", {}).get("latency_ms", 0) for t in ticks]
    err_vals = [t.get("errors", {}).get("last_5m", 0) for t in ticks]
    http_vals = [t.get("gateway", {}).get("http", 0) for t in ticks]

    healthy_count = sum(1 for t in ticks if t.get("decision") == "healthy")
    restart_count = sum(1 for t in ticks if "restart" in str(t.get("action", "")))
    tasks_dispatched = sum(t.get("tasks", {}).get("dispatched", 0) for t in ticks)

    return {
        "tick_count": n,
        "expected_ticks": 12,  # per hour
        "missing_ticks": max(0, 12 - n),
        "uptime_pct": round(100.0 * healthy_count / n, 1) if n > 0 else 0,
        "avg_cpu": round(sum(cpu_vals) / n, 1) if n else 0,
        "max_cpu": round(max(cpu_vals), 1) if cpu_vals else 0,
        "cpu_trend": compute_trend(cpu_vals),
        "avg_mem": round(sum(mem_vals) / n, 1) if n else 0,
        "mem_trend": compute_trend(mem_vals),
        "avg_latency_ms": round(sum(lat_vals) / n) if n else 0,
        "max_latency_ms": max(lat_vals) if lat_vals else 0,
        "total_errors": sum(err_vals),
        "error_trend": compute_trend(err_vals),
        "endpoint_failures": sum(1 for h in http_vals if h != 200),
        "restart_count": restart_count,
        "tasks_dispatched": tasks_dispatched,
        # Service availability
        "neo4j_down": sum(1 for t in ticks if t.get("services", {}).get("neo4j") == "down"),
        "redis_down": sum(1 for t in ticks if t.get("services", {}).get("redis") == "down"),
    }


def detect_anomalies(trends, tock_data=None, agent=None):
    """Detect anomalies using threshold rules."""
    anomalies = []

    if not trends:
        return anomalies

    # Infrastructure anomalies
    if trends.get("restart_count", 0) >= 2:
        anomalies.append(("HIGH", f"Gateway restarted {trends['restart_count']} times"))

    if trends.get("max_cpu", 0) > 80:
        anomalies.append(("WARNING", f"CPU peaked at {trends['max_cpu']}%"))

    if trends.get("cpu_trend") in ("rising sharply",):
        anomalies.append(("WARNING", f"CPU trending up ({trends['avg_cpu']}% avg, {trends['cpu_trend']})"))

    if trends.get("avg_mem", 0) > 85:
        anomalies.append(("WARNING", f"Memory at {trends['avg_mem']}% ({trends['mem_trend']})"))

    if trends.get("endpoint_failures", 0) >= 2:
        anomalies.append(("HIGH", f"Gateway endpoint failed {trends['endpoint_failures']} times"))

    if trends.get("total_errors", 0) > 10:
        anomalies.append(("WARNING", f"{trends['total_errors']} errors in last hour"))

    if trends.get("missing_ticks", 0) > 3:
        anomalies.append(("WARNING", f"{trends['missing_ticks']} missing ticks (expected 12)"))

    if trends.get("neo4j_down", 0) > 0:
        anomalies.append(("WARNING", f"Neo4j was down for {trends['neo4j_down']} ticks"))

    if trends.get("redis_down", 0) > 0:
        anomalies.append(("WARNING", f"Redis was down for {trends['redis_down']} ticks"))

    # Agent-specific anomalies from tock data
    if tock_data and agent:
        agent_data = tock_data.get("agents", {}).get(agent, {})
        tasks = agent_data.get("tasks", {})
        queue_depth = tasks.get("queue_depth", 0)
        completed = tasks.get("completed", 0)

        if queue_depth > 0 and completed == 0:
            anomalies.append(("WARNING", f"Agent {agent} stalled: {queue_depth} queued, 0 completed"))

        if tasks.get("failed", 0) > 2:
            anomalies.append(("HIGH", f"Agent {agent} has {tasks['failed']} failed tasks"))

    # Cron anomalies from tock
    if tock_data:
        cron = tock_data.get("cron", {})
        if cron.get("erroring", 0) > 0:
            erroring_jobs = [j["name"] for j in cron.get("jobs", []) if j.get("consecutive_errors", 0) > 0]
            anomalies.append(("WARNING", f"Cron jobs erroring: {', '.join(erroring_jobs)}"))

    return anomalies


def format_agent_section(tock_data, agent):
    """Format per-agent metrics from tock data."""
    if not tock_data:
        return ""

    agent_data = tock_data.get("agents", {}).get(agent)
    if not agent_data:
        return f"*No tock data for agent {agent}*\n"

    t = agent_data.get("tasks", {})
    s = agent_data.get("session", {})
    sr = agent_data.get("success_rate")
    sr_str = f"{sr}%" if sr is not None else "N/A"

    return f"""- Tasks: {t.get('completed',0)} done, {t.get('failed',0)} failed, {t.get('pending',0)} pending, {t.get('queue_depth',0)} queued
- Success rate: {sr_str} | Retries: {agent_data.get('retries',0)}
- Session: {s.get('count',0)} sessions, {s.get('pct_used',0)}% ctx used, model={s.get('model','?')}
"""


def generate_review(agent, hours=1):
    """Generate compact infrastructure pulse for reflection prompt.

    This is the main entry point called by meta_reflection.py.
    Returns a markdown string (target: <600 tokens).
    """
    ticks = parse_tick_data(hours)
    tock_data = parse_tock_data()
    trends = aggregate_trends(ticks)
    anomalies = detect_anomalies(trends, tock_data, agent)

    # Build compact summary
    lines = []
    lines.append(f"## Infrastructure Pulse (Last {hours}h)\n")

    if not ticks and not tock_data:
        lines.append("*No heartbeat data available. Tick/tock collection may not be running.*\n")
        return "\n".join(lines)

    # Gateway status line
    if trends:
        uptime = trends.get("uptime_pct", "N/A")
        cpu = trends.get("avg_cpu", "N/A")
        cpu_t = trends.get("cpu_trend", "?")
        mem = trends.get("avg_mem", "N/A")
        lat = trends.get("avg_latency_ms", "N/A")
        lines.append(f"**Gateway:** {uptime}% uptime | CPU: {cpu}% ({cpu_t}) | Mem: {mem}% | Latency: {lat}ms")
        lines.append(f"**Restarts:** {trends.get('restart_count',0)} | Errors: {trends.get('total_errors',0)} | Endpoint failures: {trends.get('endpoint_failures',0)}")
        lines.append(f"**Tasks dispatched:** {trends.get('tasks_dispatched',0)} | Ticks: {trends.get('tick_count',0)}/{trends.get('expected_ticks',12)}")
        lines.append("")

    # Agent-specific section
    if tock_data:
        lines.append(f"### Your Agent: {agent}")
        lines.append(format_agent_section(tock_data, agent))

        # LLM assessment from tock
        assessment = tock_data.get("llm_assessment", {})
        if assessment.get("workload_balance"):
            lines.append("### System Assessment (from Tock)")
            lines.append(f"- **Workload:** {assessment.get('workload_balance','N/A')}")
            lines.append(f"- **Bottleneck:** {assessment.get('bottleneck','N/A')}")
            lines.append(f"- **Coordination:** {assessment.get('coordination_gap','N/A')}")
            lines.append(f"- **Severity:** {assessment.get('severity','N/A')}")
            lines.append("")

    # Anomalies
    lines.append("### Anomalies")
    if anomalies:
        for severity, msg in anomalies:
            lines.append(f"- **{severity}:** {msg}")
    else:
        lines.append("(none detected)")
    lines.append("")

    return "\n".join(lines)


def main():
    """CLI interface for testing."""
    import argparse

    parser = argparse.ArgumentParser(description="Heartbeat Task Analyzer")
    parser.add_argument("--agent", default="kublai", help="Agent name")
    parser.add_argument("--hours", type=int, default=1, help="Hours to look back")
    args = parser.parse_args()

    review = generate_review(args.agent, args.hours)
    print(review)


if __name__ == "__main__":
    main()
