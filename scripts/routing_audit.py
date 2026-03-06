#!/usr/bin/env python3
"""
routing_audit.py — Analyze task routing decisions and execution outcomes.

Reads the last hour of routing decisions from routing-decisions.jsonl,
cross-references with task-watcher-state.json for execution outcomes,
and produces a structured audit report for kublai's reflection.

Usage:
    python3 routing_audit.py              # Human-readable report
    python3 routing_audit.py --json       # JSON output
    python3 routing_audit.py --hours 2    # Look back 2 hours
"""

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agents_config import AGENTS

ROUTING_LOG = "/Users/kublai/.openclaw/agents/main/logs/routing-decisions.jsonl"
WATCHER_STATE = "/Users/kublai/.openclaw/agents/main/logs/task-watcher-state.json"
AGENT_DIR = "/Users/kublai/.openclaw/agents"


def read_routing_decisions(hours=1):
    """Read routing decisions from the last N hours."""
    if not os.path.exists(ROUTING_LOG):
        return []

    cutoff = datetime.now() - timedelta(hours=hours)
    decisions = []

    with open(ROUTING_LOG) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                ts = datetime.fromisoformat(entry["ts"])
                if ts >= cutoff:
                    entry["_ts"] = ts
                    decisions.append(entry)
            except (json.JSONDecodeError, KeyError, ValueError):
                continue

    return decisions


def read_execution_outcomes():
    """Read task execution outcomes from task-watcher state."""
    if not os.path.exists(WATCHER_STATE):
        return {}

    try:
        with open(WATCHER_STATE) as f:
            return json.load(f)
    except Exception:
        return {}


def get_current_queue_state():
    """Get current pending/executing/done counts per agent."""
    state = {}
    for agent in AGENTS:
        task_dir = f"{AGENT_DIR}/{agent}/tasks"
        if not os.path.isdir(task_dir):
            state[agent] = {"pending": 0, "executing": 0, "done": 0}
            continue

        pending = executing = done = 0
        for fname in os.listdir(task_dir):
            if ".done" in fname:
                done += 1
            elif ".executing" in fname:
                executing += 1
            elif fname.endswith(".md"):
                pending += 1

        state[agent] = {"pending": pending, "executing": executing, "done": done}
    return state


def generate_audit(hours=1):
    """Generate the full routing audit report."""
    decisions = read_routing_decisions(hours)
    outcomes = read_execution_outcomes()
    queue_state = get_current_queue_state()

    report = {
        "period_hours": hours,
        "generated_at": datetime.now().isoformat(),
        "total_routed": len(decisions),
        "routing_methods": Counter(),
        "destinations": Counter(),
        "by_agent": defaultdict(lambda: {"routed": 0, "executed": 0, "succeeded": 0, "failed": 0}),
        "queue_state": queue_state,
        "issues": [],
        "suggestions": [],
    }

    if not decisions:
        report["issues"].append(f"No routing decisions logged in the last {hours}h")
        return report

    # Analyze routing decisions
    for d in decisions:
        dest = d.get("dest", "unknown")
        method = d.get("method", "unknown")
        report["routing_methods"][method] += 1
        report["destinations"][dest] += 1
        report["by_agent"][dest]["routed"] += 1

    # Cross-reference with execution outcomes
    for key, outcome in outcomes.items():
        # key format: "agent/filename.md"
        agent = key.split("/")[0] if "/" in key else "unknown"
        if agent in report["by_agent"]:
            executed_at = outcome.get("executed", "")
            try:
                exec_time = datetime.fromisoformat(executed_at)
                cutoff = datetime.now() - timedelta(hours=hours)
                if exec_time >= cutoff:
                    report["by_agent"][agent]["executed"] += 1
                    if outcome.get("success"):
                        report["by_agent"][agent]["succeeded"] += 1
                    else:
                        report["by_agent"][agent]["failed"] += 1
            except (ValueError, TypeError):
                continue

    # Convert defaultdict for serialization
    report["by_agent"] = dict(report["by_agent"])
    report["routing_methods"] = dict(report["routing_methods"])
    report["destinations"] = dict(report["destinations"])

    # --- Generate issues and suggestions ---

    # Issue: LLM fallback usage
    fallback_count = report["routing_methods"].get("keyword_fallback", 0)
    llm_count = report["routing_methods"].get("llm", 0)
    total = fallback_count + llm_count
    if total > 0 and fallback_count > 0:
        pct = fallback_count / total * 100
        if pct > 20:
            report["issues"].append(
                f"High keyword fallback rate: {fallback_count}/{total} ({pct:.0f}%) — ollama may be unstable"
            )
        elif pct > 0:
            report["issues"].append(
                f"Some keyword fallbacks: {fallback_count}/{total} ({pct:.0f}%)"
            )

    # Issue: Agent imbalance
    agent_loads = {a: d["routed"] for a, d in report["by_agent"].items() if d["routed"] > 0}
    if len(agent_loads) >= 2:
        max_agent = max(agent_loads, key=agent_loads.get)
        min_agent = min(agent_loads, key=agent_loads.get)
        if agent_loads[max_agent] > 3 * max(agent_loads[min_agent], 1):
            report["issues"].append(
                f"Workload imbalance: {max_agent} got {agent_loads[max_agent]} tasks vs {min_agent} got {agent_loads[min_agent]}"
            )

    # Issue: Execution failures
    for agent, stats in report["by_agent"].items():
        if stats["failed"] > 0:
            report["issues"].append(
                f"{agent}: {stats['failed']} task(s) failed out of {stats['executed']} executed"
            )

    # Issue: Queue buildup
    for agent, qs in queue_state.items():
        if qs["pending"] > 5:
            report["issues"].append(
                f"{agent}: {qs['pending']} tasks pending in queue (backlog)"
            )

    # Issue: Tasks routed but not executed
    for agent, stats in report["by_agent"].items():
        routed = stats["routed"]
        executed = stats["executed"]
        if routed > 0 and executed == 0:
            report["issues"].append(
                f"{agent}: {routed} task(s) routed but 0 executed — dispatch may be stalled"
            )

    # Suggestion: Subagent overuse
    subagent_count = report["destinations"].get("subagent", 0)
    if total > 0 and subagent_count / total > 0.4:
        report["suggestions"].append(
            "Over 40% of tasks going to subagent — LLM system prompt may need agent role clarification"
        )

    # Suggestion: Single-agent concentration
    for agent, count in report["destinations"].items():
        if agent != "subagent" and total > 3 and count / total > 0.6:
            report["suggestions"].append(
                f"{agent} received {count}/{total} ({count/total*100:.0f}%) of all tasks — "
                f"check if task descriptions are too narrow or if other agents need broader keywords"
            )

    # Suggestion: All LLM, no fallbacks — good
    if fallback_count == 0 and llm_count > 0:
        report["suggestions"].append(
            f"All {llm_count} routing decisions used LLM — ollama is stable"
        )

    return report


def format_report(report):
    """Format audit report as human-readable text."""
    lines = []
    lines.append(f"=== Routing Audit ({report['period_hours']}h) ===")
    lines.append(f"Generated: {report['generated_at']}")
    lines.append(f"Total routed: {report['total_routed']}")
    lines.append("")

    # Methods
    lines.append("Routing methods:")
    for method, count in report.get("routing_methods", {}).items():
        lines.append(f"  {method}: {count}")

    # Per-agent
    lines.append("\nPer-agent breakdown:")
    for agent in AGENTS:
        stats = report.get("by_agent", {}).get(agent)
        if not stats:
            continue
        qs = report.get("queue_state", {}).get(agent, {})
        lines.append(
            f"  {agent}: routed={stats['routed']} executed={stats['executed']} "
            f"ok={stats['succeeded']} fail={stats['failed']} "
            f"queue={qs.get('pending',0)}p/{qs.get('executing',0)}x/{qs.get('done',0)}d"
        )

    # Issues
    if report.get("issues"):
        lines.append("\nIssues:")
        for issue in report["issues"]:
            lines.append(f"  - {issue}")

    # Suggestions
    if report.get("suggestions"):
        lines.append("\nSuggestions:")
        for s in report["suggestions"]:
            lines.append(f"  - {s}")

    return "\n".join(lines)


def format_for_reflection(report):
    """Format audit as compact markdown for injection into kublai's reflection context."""
    lines = []
    lines.append(f"## Routing Audit ({report['period_hours']}h)")
    lines.append(f"Routed: {report['total_routed']} tasks | Methods: {dict(report.get('routing_methods', {}))}")
    lines.append("")

    # Compact per-agent table
    lines.append("| Agent | Routed | Executed | OK | Fail | Queue |")
    lines.append("|-------|--------|----------|-----|------|-------|")
    for agent in AGENTS:
        stats = report.get("by_agent", {}).get(agent, {"routed": 0, "executed": 0, "succeeded": 0, "failed": 0})
        qs = report.get("queue_state", {}).get(agent, {})
        lines.append(
            f"| {agent} | {stats['routed']} | {stats['executed']} | "
            f"{stats['succeeded']} | {stats['failed']} | {qs.get('pending',0)} |"
        )
    lines.append("")

    if report.get("issues"):
        lines.append("**Issues:**")
        for issue in report["issues"]:
            lines.append(f"- {issue}")
        lines.append("")

    if report.get("suggestions"):
        lines.append("**Observations:**")
        for s in report["suggestions"]:
            lines.append(f"- {s}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Routing Audit — analyze task routing and execution")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--reflection", action="store_true", help="Output compact markdown for reflection injection")
    parser.add_argument("--hours", type=int, default=1, help="Hours to look back (default: 1)")
    args = parser.parse_args()

    report = generate_audit(hours=args.hours)

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    elif args.reflection:
        print(format_for_reflection(report))
    else:
        print(format_report(report))


if __name__ == "__main__":
    main()
