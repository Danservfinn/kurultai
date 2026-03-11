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
from kurultai_paths import AGENTS_DIR as _AGENTS_DIR, WATCHER_STATE as _WATCHER_STATE, LOGS_DIR

ROUTING_LOG = str(LOGS_DIR / "routing-decisions.jsonl")
WATCHER_STATE = str(_WATCHER_STATE)
AGENT_DIR = str(_AGENTS_DIR)


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
            if fname.endswith(".done.md"):
                done += 1
            elif fname.endswith(".executing.md"):
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

    # Analyze routing decisions (skip diagnostic entries to avoid double-counting)
    _DIAGNOSTIC_METHODS = {"explicit_misroute", "skill_reroute"}
    for d in decisions:
        dest = d.get("dest", "unknown")
        method = d.get("method", "unknown")
        if method in _DIAGNOSTIC_METHODS:
            continue  # These are warnings, not actual task routings
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

    # --- Keyword disagreement analysis ---
    # Detect when logged top_scores disagree with actual destination
    # (signals keyword table gaps that need disambiguation rules)
    try:
        from task_intake import route_by_text
        kw_disagreements = defaultdict(int)  # (kw_winner, actual_dest) -> count
        kw_disagree_examples = []
        for d in decisions:
            top = d.get("top_scores", {})
            if not top:
                continue
            kw_winner = max(top, key=lambda k: top[k])
            dest = d.get("dest", "unknown")
            if kw_winner != dest and top.get(kw_winner, 0) > top.get(dest, 0):
                kw_disagreements[(kw_winner, dest)] += 1
                if len(kw_disagree_examples) < 5:
                    kw_disagree_examples.append(d.get("task", "")[:80])

        # Also test current keyword router against logged tasks
        # Only compare keyword-routed tasks (explicit tasks bypass keyword routing by design)
        kw_misroutes = 0
        kw_misroute_examples = []
        for d in decisions:
            # Skip diagnostic entries (misroute warnings, skill reroutes)
            if d.get("method", "") in _DIAGNOSTIC_METHODS:
                continue
            # Skip explicitly-routed tasks — keyword comparison is irrelevant
            # for tasks that were intentionally sent to a specific agent
            if d.get("method") == "explicit":
                continue
            task_text = d.get("task", "")
            dest = d.get("dest", "unknown")
            if not task_text:
                continue
            kw_result = route_by_text(task_text)
            if kw_result != dest:
                kw_misroutes += 1
                if len(kw_misroute_examples) < 5:
                    kw_misroute_examples.append(
                        f"'{task_text[:60]}' -> kw={kw_result} actual={dest}"
                    )
        report["kw_disagreements"] = dict(
            {f"{k[0]}->{k[1]}": v for k, v in kw_disagreements.items()}
        )
        report["kw_misroute_count"] = kw_misroutes
        report["kw_misroute_rate"] = f"{kw_misroutes}/{len(decisions)}" if decisions else "0/0"
        if kw_misroute_examples:
            report["kw_misroute_examples"] = kw_misroute_examples[:5]
    except Exception:
        pass

    # --- Generate issues and suggestions ---
    total = report["total_routed"]

    # Track overflow and skill hint stats from decision entries
    overflow_count = sum(1 for d in decisions if d.get("overflow"))
    skill_hint_count = sum(1 for d in decisions if d.get("skill_hint"))
    report["overflow_count"] = overflow_count
    report["skill_hint_coverage"] = f"{skill_hint_count}/{total}" if total > 0 else "0/0"

    # Issue: High explicit routing ratio (bypasses keyword routing — may mask routing table gaps)
    # Enhanced (2026-03-10): Distinguish system-generated tasks (explicit is expected)
    # from human-originated tasks (explicit may indicate keyword gaps).
    # System sources: watchdog, tick, tock, reflection, routing_audit, kublai-actions, task-watcher
    _SYSTEM_SOURCES = {
        "kublai-actions", "ogedei-watchdog", "task-watcher", "routing_audit",
        "reflection", "tick", "tock", "hourly_reflection", "mongke_self_task",
        "cascade_detector", "throughput_anomaly", "stall_detector",
        "action_resolution", "signal_calendar", "redistribution",
        "system-health-check", "task_intake", "queue-audit",
    }
    # Task text patterns that indicate system-generated tasks (for entries missing source field)
    _SYSTEM_TASK_PATTERNS = (
        "RETRY:", "System Health Alert", "ESCALATE", "TEST TASK:",
        "Restart neo4j", "FIX:", "REQUEUE:", "BACKFILL:",
        "3-hour review", "test-3-hour-review",  # Test tasks for systematic-debugging
    )
    explicit_count = report["routing_methods"].get("explicit", 0)
    keyword_count = report["routing_methods"].get("keyword", 0)
    mention_count = report["routing_methods"].get("mention", 0)

    # Count explicit routing from non-system sources (human/manual tasks)
    # Fix (2026-03-10): Entries without a source field are likely system-generated.
    # Use task text pattern matching as fallback when source is missing.
    def _is_system_task(d):
        source = d.get("source", "")
        if source and source in _SYSTEM_SOURCES:
            return True
        # No source logged — check task text for system patterns
        task_text = d.get("task", "")
        if any(task_text.startswith(p) for p in _SYSTEM_TASK_PATTERNS):
            return True
        # No source and no pattern match — only flag as human if source is
        # explicitly set to a non-system value (not just missing)
        if source and source not in _SYSTEM_SOURCES:
            return False
        # Missing source entirely — treat as unknown, not human
        return True

    human_explicit = sum(
        1 for d in decisions
        if d.get("method") == "explicit"
        and not _is_system_task(d)
        and d.get("method") not in _DIAGNOSTIC_METHODS
    )
    system_explicit = explicit_count - human_explicit

    if total > 3 and explicit_count > 0:
        explicit_pct = explicit_count / total * 100
        if explicit_pct > 80:
            if human_explicit > 0:
                # Only flag as issue if human tasks are being explicitly routed
                report["issues"].append(
                    f"High explicit routing: {explicit_count}/{total} ({explicit_pct:.0f}%) — "
                    f"{human_explicit} from non-system sources, keyword table may be underused"
                )
            else:
                # All explicit routing is from system sources — expected behavior
                report["suggestions"].append(
                    f"Explicit routing: {explicit_count}/{total} ({explicit_pct:.0f}%) — "
                    f"all from system sources (expected)"
                )

    # Issue: Overflow routing frequency
    if total > 0 and overflow_count > 0:
        overflow_pct = overflow_count / total * 100
        if overflow_pct > 30:
            report["issues"].append(
                f"High overflow rate: {overflow_count}/{total} ({overflow_pct:.0f}%) — agents frequently busy"
            )
        else:
            report["suggestions"].append(
                f"Overflow routing: {overflow_count}/{total} ({overflow_pct:.0f}%) — load balancing active"
            )

    # Issue: Agent imbalance
    # Only flag when keyword-routed tasks are imbalanced (system tasks target specific agents by design)
    agent_loads = {a: d["routed"] for a, d in report["by_agent"].items() if d["routed"] > 0}
    if len(agent_loads) >= 2:
        max_agent = max(agent_loads, key=agent_loads.get)
        min_agent = min(agent_loads, key=agent_loads.get)
        if agent_loads[max_agent] > 3 * max(agent_loads[min_agent], 1):
            # Check if imbalance is from system sources (expected) or keyword routing (problem)
            keyword_by_agent = defaultdict(int)
            for d in decisions:
                if d.get("method") == "keyword":
                    keyword_by_agent[d.get("dest", "")] += 1
            kw_max = max(keyword_by_agent.values()) if keyword_by_agent else 0
            kw_min = min(keyword_by_agent.values()) if keyword_by_agent else 0

            if keyword_by_agent and kw_max > 3 * max(kw_min, 1):
                # Keyword-routed tasks are also imbalanced — real routing problem
                report["issues"].append(
                    f"Workload imbalance: {max_agent} got {agent_loads[max_agent]} tasks vs {min_agent} got {agent_loads[min_agent]}"
                )
            else:
                # Imbalance is from explicit/system routing — expected
                report["suggestions"].append(
                    f"Workload skew: {max_agent} got {agent_loads[max_agent]} tasks vs {min_agent} got {agent_loads[min_agent]} "
                    f"(system-generated, expected)"
                )

    # Execution failures — classified as downstream issues (not routing problems)
    # Only flag as routing issue if failure rate suggests misrouting (>80% failure + high volume)
    # Also feeds back into health flags so the router can divert away from failing agents
    high_failure_agents = {}
    for agent, stats in report["by_agent"].items():
        if stats["failed"] > 0:
            fail_rate = stats["failed"] / max(stats["executed"], 1)
            if fail_rate >= 0.8 and stats["executed"] >= 3:
                # High failure rate with volume — could indicate routing to broken agent
                report["issues"].append(
                    f"{agent}: {stats['failed']}/{stats['executed']} tasks failed ({fail_rate*100:.0f}%) — "
                    f"check if agent is healthy before routing more tasks"
                )
                high_failure_agents[agent] = {
                    "fail_rate": fail_rate,
                    "failed": stats["failed"],
                    "total": stats["executed"],
                }
            else:
                # Normal failure rate — downstream issue, not routing
                report["suggestions"].append(
                    f"{agent}: {stats['failed']} task(s) failed out of {stats['executed']} executed (downstream)"
                )

    # Feed high-failure agents into health flags so route_quality_tracker.should_divert() can act
    if high_failure_agents:
        _update_health_flags_from_audit(high_failure_agents)

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

    # Issue: High keyword misroute rate (keyword table drift)
    kw_misroute_count = report.get("kw_misroute_count", 0)
    if total > 3 and kw_misroute_count > 0:
        kw_pct = kw_misroute_count / total * 100
        if kw_pct > 30:
            report["issues"].append(
                f"Keyword table drift: {kw_misroute_count}/{total} ({kw_pct:.0f}%) tasks "
                f"would route differently via keywords vs actual destination"
            )
        elif kw_pct > 10:
            report["suggestions"].append(
                f"Keyword divergence: {kw_misroute_count}/{total} ({kw_pct:.0f}%) — "
                f"consider adding disambiguation rules"
            )

    # Suggestion: Single-agent concentration
    for agent, count in report["destinations"].items():
        if total > 3 and count / total > 0.6:
            report["suggestions"].append(
                f"{agent} received {count}/{total} ({count/total*100:.0f}%) of all tasks — "
                f"check if task descriptions are too narrow or if other agents need broader keywords"
            )

    # Suggestion: Low skill hint coverage
    if total > 3 and skill_hint_count / total < 0.5:
        report["suggestions"].append(
            f"Low skill hint coverage: {skill_hint_count}/{total} — "
            f"consider expanding SKILL_HINTS in task_intake.py"
        )

    # Suggestion: Routing method breakdown
    if total > 0:
        methods_str = ", ".join(f"{m}={c}" for m, c in sorted(report["routing_methods"].items(), key=lambda x: -x[1]))
        report["suggestions"].append(f"Routing methods: {methods_str}")

    # Include routing drift data from watchdog if available
    try:
        watchdog_state_path = LOGS_DIR / "ogedei-watchdog-state.json"
        if watchdog_state_path.exists():
            with open(watchdog_state_path) as f:
                wstate = json.load(f)
            drift = wstate.get("routing_drift", {})
            if drift:
                report["routing_drift"] = drift
                drift_pct = drift.get("drift_pct", 0)
                mismatches = drift.get("mismatches", 0)
                drift_total = drift.get("total", 0)
                if drift_pct > 30 and mismatches >= 2:
                    report["issues"].append(
                        f"Keyword routing drift: {mismatches}/{drift_total} ({drift_pct:.0f}%) "
                        f"disagree with actual routing"
                    )
                elif mismatches > 0:
                    report["suggestions"].append(
                        f"Keyword drift: {mismatches}/{drift_total} ({drift_pct:.0f}%) — within tolerance"
                    )
    except Exception:
        pass

    # --- Trend tracking: detect recurring issues across audit runs ---
    trend_data = _load_trend_state()
    current_issue_keys = _extract_issue_keys(report.get("issues", []))
    trend_data = _update_trend_state(trend_data, current_issue_keys, report.get("generated_at", ""))
    _save_trend_state(trend_data)

    # Flag recurring issues (3+ consecutive runs)
    recurring = {k: v for k, v in trend_data.get("issue_streaks", {}).items()
                 if v.get("consecutive", 0) >= 3}
    if recurring:
        report["recurring_issues"] = [
            {"issue_key": k, "consecutive": v["consecutive"], "first_seen": v.get("first_seen", "")}
            for k, v in recurring.items()
        ]
        report["issues"].append(
            f"RECURRING: {len(recurring)} issue(s) unresolved for 3+ consecutive audits — escalation recommended"
        )

    # --- Missed opportunity detection (2026-03-08) ---
    # Identify tasks routed to busy agents when idle alternatives with capability existed
    missed_opportunities = []
    missed_by_agent = defaultdict(list)

    for d in decisions:
        # Skip diagnostic entries
        if d.get("method", "") in _DIAGNOSTIC_METHODS:
            continue

        dest = d.get("dest", "")
        queue_info = d.get("queue", {})
        idle_agents = d.get("idle_agents", [])
        alt_scores = d.get("alt_scores", {})
        would_overflow = d.get("would_overflow", False)

        # Skip if no enhanced logging data available
        if not queue_info or not idle_agents:
            continue

        dest_queue = queue_info.get(dest, 0)

        # Check if routed to busy agent when idle alternatives existed
        if dest_queue > 0 and idle_agents:
            # Find idle agents with non-zero scores (capable of handling task)
            capable_idle = []
            for idle_agent in idle_agents:
                idle_score = alt_scores.get(idle_agent, 0)
                if idle_score > 0:
                    capable_idle.append((idle_agent, idle_score))

            if capable_idle:
                # Sort by score descending
                capable_idle.sort(key=lambda x: -x[1])
                missed = {
                    "task": d.get("task", "")[:80],
                    "routed_to": dest,
                    "dest_queue": dest_queue,
                    "idle_alternatives": capable_idle,
                    "method": d.get("method"),
                    "ts": d.get("ts"),
                }
                missed_opportunities.append(missed)
                missed_by_agent[dest].append(missed)

    # Add missed opportunity stats to report
    if missed_opportunities:
        report["missed_opportunities"] = {
            "count": len(missed_opportunities),
            "by_agent": {agent: len(missed) for agent, missed in missed_by_agent.items()},
            "examples": missed_opportunities[:5],
        }

        # Flag as issue if significant
        missed_pct = len(missed_opportunities) / max(total, 1) * 100
        if missed_pct > 15 and len(missed_opportunities) >= 3:
            report["issues"].append(
                f"Missed routing opportunities: {len(missed_opportunities)} tasks routed to busy agents "
                f"when idle alternatives existed ({missed_pct:.0f}% of routed tasks)"
            )
            # Add per-agent breakdown
            for agent, count in sorted(report["missed_opportunities"]["by_agent"].items(), key=lambda x: -x[1]):
                if count >= 2:
                    report["suggestions"].append(
                        f"  {agent}: {count} missed opportunities — consider adjusting load balancing thresholds"
                    )
        elif len(missed_opportunities) >= 1:
            report["suggestions"].append(
                f"Missed opportunities: {len(missed_opportunities)} task(s) could have been routed to idle agents"
            )


    return report


# --- Health flags feedback from audit ---
AGENT_HEALTH_FLAGS_FILE = str(LOGS_DIR / "agent-health-flags.json")


def _update_health_flags_from_audit(high_failure_agents):
    """Merge audit-detected high-failure agents into agent-health-flags.json.

    The watchdog writes health flags from task-ledger events, but may miss
    failures visible in the task-watcher execution outcomes. This function
    closes the gap: when the routing audit detects >=80% failure rate with
    3+ tasks, it flags the agent so route_quality_tracker.should_divert()
    can divert tasks away.
    """
    try:
        existing = {}
        if os.path.exists(AGENT_HEALTH_FLAGS_FILE):
            with open(AGENT_HEALTH_FLAGS_FILE) as f:
                existing = json.load(f)

        agents_data = existing.get("agents", {})

        for agent, info in high_failure_agents.items():
            entry = agents_data.get(agent, {})
            # Only upgrade flagged status — don't clear flags the watchdog set
            if not entry.get("flagged"):
                agents_data[agent] = {
                    "completed_1h": info["total"] - info["failed"],
                    "failed_1h": info["failed"],
                    "total_1h": info["total"],
                    "fail_rate_1h": info["fail_rate"],
                    "flagged": True,
                    "flagged_by": "routing_audit",
                }

        existing["agents"] = agents_data
        existing["ts"] = datetime.now().isoformat()
        existing["window_hours"] = existing.get("window_hours", 1)

        os.makedirs(os.path.dirname(AGENT_HEALTH_FLAGS_FILE), exist_ok=True)
        with open(AGENT_HEALTH_FLAGS_FILE, "w") as f:
            json.dump(existing, f, indent=2)
    except Exception:
        pass  # Best-effort — don't break the audit if flag write fails


# --- Trend state management ---
TREND_STATE_FILE = str(LOGS_DIR / "routing-audit-trend.json")
_TREND_MAX_KEYS = 50  # Cap tracked issue keys to prevent unbounded growth


def _extract_issue_keys(issues):
    """Normalize issues into stable keys for trend tracking.

    Strips numbers/timestamps so 'temujin: 1 task(s) failed out of 1 executed'
    and 'temujin: 3 task(s) failed out of 5 executed' map to the same key.
    """
    import re
    keys = set()
    for issue in issues:
        if "No routing decisions logged" in issue:
            continue
        # Replace numbers with '#' to create a stable signature
        key = re.sub(r'\d+', '#', issue).strip()
        # Collapse repeated '#' and whitespace
        key = re.sub(r'#+', '#', key)
        key = re.sub(r'\s+', ' ', key)
        keys.add(key)
    return keys


def _load_trend_state():
    """Load persisted trend state."""
    if not os.path.exists(TREND_STATE_FILE):
        return {"issue_streaks": {}, "last_run": ""}
    try:
        with open(TREND_STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {"issue_streaks": {}, "last_run": ""}


def _update_trend_state(trend_data, current_keys, generated_at):
    """Update streak counts: increment for recurring issues, reset for resolved ones."""
    streaks = trend_data.get("issue_streaks", {})

    # Increment streaks for issues that are still present
    for key in current_keys:
        if key in streaks:
            streaks[key]["consecutive"] = streaks[key].get("consecutive", 0) + 1
            streaks[key]["last_seen"] = generated_at
        else:
            streaks[key] = {
                "consecutive": 1,
                "first_seen": generated_at,
                "last_seen": generated_at,
            }

    # Reset streaks for issues that are no longer present
    for key in list(streaks.keys()):
        if key not in current_keys:
            del streaks[key]

    # Cap total tracked keys
    if len(streaks) > _TREND_MAX_KEYS:
        # Keep the ones with highest consecutive count
        sorted_keys = sorted(streaks.keys(), key=lambda k: streaks[k].get("consecutive", 0), reverse=True)
        for k in sorted_keys[_TREND_MAX_KEYS:]:
            del streaks[k]

    trend_data["issue_streaks"] = streaks
    trend_data["last_run"] = generated_at
    return trend_data


def _save_trend_state(trend_data):
    """Persist trend state to disk."""
    try:
        os.makedirs(os.path.dirname(TREND_STATE_FILE), exist_ok=True)
        with open(TREND_STATE_FILE, "w") as f:
            json.dump(trend_data, f, indent=2)
    except Exception:
        pass


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

    # Keyword misroute examples
    kw_examples = report.get("kw_misroute_examples", [])
    if kw_examples:
        lines.append(f"\nKeyword misroutes ({report.get('kw_misroute_count', 0)}):")
        for ex in kw_examples[:5]:
            lines.append(f"  - {ex}")

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
    overflow = report.get('overflow_count', 0)
    skill_cov = report.get('skill_hint_coverage', '0/0')
    lines.append(f"Routed: {report['total_routed']} tasks | Methods: {dict(report.get('routing_methods', {}))} | Overflow: {overflow} | Skills: {skill_cov}")
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

    # Keyword misroute examples (from re-routing current decisions through keyword table)
    kw_examples = report.get("kw_misroute_examples", [])
    if kw_examples:
        lines.append(f"**Keyword Misroutes ({report.get('kw_misroute_count', 0)}):**")
        for ex in kw_examples[:5]:
            lines.append(f"- `{ex}`")
        lines.append("")

    # Routing drift summary
    drift = report.get("routing_drift", {})
    if drift and drift.get("total", 0) > 0:
        lines.append("")
        lines.append(f"**Keyword Drift:** {drift.get('mismatches', 0)}/{drift.get('total', 0)} "
                      f"({drift.get('drift_pct', 0):.0f}%) keyword-vs-actual mismatches")
        for ex in drift.get("top_examples", [])[:3]:
            lines.append(f"- `{ex.get('task', '?')[:50]}` keyword→{ex.get('keyword_would', '?')} actual→{ex.get('actual', '?')}")

    # Recurring issues summary
    recurring = report.get("recurring_issues", [])
    if recurring:
        lines.append("")
        lines.append("**RECURRING (3+ consecutive audits):**")
        for r in recurring:
            lines.append(f"- [{r['consecutive']}x] {r['issue_key']} (since {r['first_seen'][:16]})")

    # Missed opportunities (tasks routed to busy agents when idle alternatives existed)
    missed = report.get("missed_opportunities", {})
    if missed and missed.get("count", 0) > 0:
        lines.append("")
        lines.append(f"**Missed Opportunities ({missed['count']}):**")
        for agent, count in sorted(missed.get("by_agent", {}).items(), key=lambda x: -x[1]):
            lines.append(f"- {agent}: {count} tasks could have gone to idle agents")
        for ex in missed.get("examples", [])[:3]:
            lines.append(f"  - `{ex['task']}` → {ex['routed_to']} (q={ex['dest_queue']}) idle: {ex['idle_alternatives']}")

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
