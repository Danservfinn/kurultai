#!/usr/bin/env python3
"""
Skill Outcome Scorer — companion to score_tasks.py.
Reads SKILL_INVOCATION events, joins with EXECUTION_DETAIL + SCORED,
appends SKILL_OUTCOME events to task-ledger.jsonl.

Usage:
    python3 score_skills.py                    # Score all unscored skill invocations
    python3 score_skills.py --hours 2          # Score from last N hours
    python3 score_skills.py --summary          # Print per-agent skill summary
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kurultai_ledger import append_ledger as _kp_append_ledger, read_ledger

SKILL_DOMAIN_MAP = {
    "horde-brainstorming": ["design", "architecture", "brainstorm", "explore", "idea", "approach"],
    "horde-implement": ["implement", "code", "build", "create", "develop", "write code", "feature"],
    "horde-debug": ["debug", "fix", "error", "bug", "issue", "traceback", "failure"],
    "horde-review": ["review", "audit", "check", "analyze", "assess", "evaluate"],
    "horde-plan": ["plan", "structure", "organize", "strategy", "roadmap"],
    "horde-learn": ["learn", "extract", "understand", "knowledge", "read", "study"],
    "golden-horde": ["complex", "orchestrate", "multi-agent", "coordinate"],
    "scrapling-research": ["research", "scrape", "gather", "data", "investigate", "find"],
    "tock-gather": ["telemetry", "metrics", "health", "gather"],
    "heartbeat-watchdog": ["health", "watchdog", "heartbeat", "monitor"],
    "senior-backend": ["backend", "api", "server", "database", "endpoint"],
    "senior-frontend": ["frontend", "ui", "component", "react", "css"],
    "lead-research-assistant": ["research", "leads", "market", "investigate"],
    "systematic-debugging": ["debug", "systematic", "trace", "root cause"],
    "kurultai-reflect": ["reflect", "review", "behavior", "rules", "pattern"],
}

PROTOCOL_COMPLETION_THRESHOLDS = {
    "horde-brainstorming": 20,
    "horde-implement": 40,
    "horde-plan": 15,
    "horde-review": 20,
    "horde-debug": 15,
    "horde-learn": 10,
    "golden-horde": 50,
    "scrapling-research": 5,
    "tock-gather": 1,
    "heartbeat-watchdog": 1,
    "kurultai-reflect": 30,
}
DEFAULT_THRESHOLD = 10



def score_output_quality(execution_detail):
    """Score output quality 0-3 based on success + output_lines."""
    if not execution_detail:
        return 0
    success = execution_detail.get("success", False)
    output_lines = execution_detail.get("output_lines", 0)
    score = 0
    if success:
        score += 1
    if output_lines >= 20:
        score += 1
    if output_lines >= 50:
        score += 1
    return min(3, score)


def score_fit(skill_name, task_summary, agent):
    """Score 0-3: how well did the skill match the task?"""
    if not skill_name or not task_summary:
        return 1
    skill_key = skill_name.lstrip("/")
    skill_keywords = SKILL_DOMAIN_MAP.get(skill_key, [])
    if not skill_keywords:
        for k, kws in SKILL_DOMAIN_MAP.items():
            if k in skill_key or skill_key in k:
                skill_keywords = kws
                break
    if not skill_keywords:
        return 1
    task_lower = task_summary.lower()
    matched = sum(1 for kw in skill_keywords if kw in task_lower)
    if matched >= 2:
        return 3
    elif matched == 1:
        return 2
    return 0


def score_protocol_completion(skill_name, output_lines):
    """Return True if output_lines meets the protocol completion threshold."""
    skill_key = skill_name.lstrip("/")
    threshold = PROTOCOL_COMPLETION_THRESHOLDS.get(skill_key, DEFAULT_THRESHOLD)
    return output_lines >= threshold


def compute_skill_outcome(task_id, invocation_event, all_events_by_task):
    """Build SKILL_OUTCOME dict for a single skill invocation."""
    task_events = all_events_by_task.get(task_id, [])

    exec_detail = next((e for e in task_events if e.get("event") == "EXECUTION_DETAIL"), None)
    completed_event = next(
        (e for e in task_events if e.get("event") in ("COMPLETED", "FAILED")), None
    )

    if exec_detail:
        success = exec_detail.get("success", False)
    elif completed_event:
        success = completed_event.get("event") == "COMPLETED"
    else:
        success = False

    output_lines = exec_detail.get("output_lines", 0) if exec_detail else 0
    skill_name = invocation_event.get("skill", "")
    agent = invocation_event.get("agent", "")

    queued_event = next((e for e in task_events if e.get("event") == "QUEUED"), None)
    task_summary = queued_event.get("task_summary", "") if queued_event else ""

    oq = score_output_quality(exec_detail)
    fs = score_fit(skill_name, task_summary, agent)
    pc = score_protocol_completion(skill_name, output_lines)

    error_signal = None
    if completed_event and not success:
        error_signal = (completed_event.get("error") or "")[:200]

    return {
        "task_id": task_id,
        "event": "SKILL_OUTCOME",
        "ts": datetime.now().isoformat(),
        "agent": agent,
        "skill": skill_name,
        "completed_protocol": pc,
        "output_quality": oq,
        "fit_score": fs,
        "error_signal": error_signal,
        "output_lines": output_lines,
        "task_success": success,
        "executor": invocation_event.get("executor"),
        "skill_version": 1,
    }


def score_all_skills(hours=None):
    """Score all unscored skill invocations and append SKILL_OUTCOME events."""
    events = read_ledger(hours)

    all_events_by_task = defaultdict(list)
    for e in events:
        tid = e.get("task_id")
        if tid:
            all_events_by_task[tid].append(e)

    scored_keys = set()
    for e in events:
        if e.get("event") == "SKILL_OUTCOME":
            key = f"{e.get('task_id')}:{e.get('skill')}"
            scored_keys.add(key)

    invocations = [e for e in events if e.get("event") == "SKILL_INVOCATION"]

    new_outcomes = 0
    for inv in invocations:
        task_id = inv.get("task_id")
        skill = inv.get("skill", "")
        if not task_id:
            continue
        key = f"{task_id}:{skill}"
        if key in scored_keys:
            continue

        task_events = all_events_by_task.get(task_id, [])
        terminal = [e for e in task_events if e.get("event") in ("COMPLETED", "FAILED")]
        if not terminal:
            continue

        outcome = compute_skill_outcome(task_id, inv, all_events_by_task)
        _kp_append_ledger(outcome)
        new_outcomes += 1

    return new_outcomes


def generate_skill_summary(agent=None, hours=24):
    """Generate compact markdown summary of skill performance."""
    events = read_ledger(hours=hours)
    skill_outcomes = [
        e for e in events
        if e.get("event") == "SKILL_OUTCOME"
        and (agent is None or e.get("agent") == agent)
    ]
    if not skill_outcomes:
        return f"No skill outcomes for {agent or 'all agents'} in last {hours}h."

    by_skill = defaultdict(lambda: {"uses": 0, "success": 0, "oq_sum": 0, "fit_sum": 0, "pc_count": 0, "cc_count": 0})
    for so in skill_outcomes:
        skill = so.get("skill", "unknown")
        s = by_skill[skill]
        s["uses"] += 1
        if so.get("task_success"):
            s["success"] += 1
        s["oq_sum"] += so.get("output_quality", 0)
        s["fit_sum"] += so.get("fit_score", 0)
        if so.get("completed_protocol"):
            s["pc_count"] += 1
        if so.get("executor") == "claude-code":
            s["cc_count"] += 1

    agent_label = agent or "all agents"
    lines = [f"## Skill Summary ({agent_label}, {hours}h)"]
    for skill, stats in sorted(by_skill.items()):
        uses = stats["uses"]
        sr = stats["success"] / uses if uses > 0 else 0
        oq = stats["oq_sum"] / uses if uses > 0 else 0
        pc = stats["pc_count"] / uses if uses > 0 else 0
        cc_pct = stats["cc_count"] / uses if uses > 0 else 0
        lines.append(f"  {skill}: {uses}x, {sr:.0%} ok, quality={oq:.1f}/3, protocol={pc:.0%}, cc={cc_pct:.0%}")

    return "\n".join(lines)


def generate_skill_aggregates(hours=24):
    """Generate SKILL_AGGREGATE events (one per agent+skill pair per day)."""
    events = read_ledger(hours=hours)

    groups = defaultdict(list)
    for e in events:
        if e.get("event") == "SKILL_OUTCOME":
            key = (e.get("agent", ""), e.get("skill", ""))
            groups[key].append(e)

    # Prior window for trend
    prior_cutoff = (datetime.now() - timedelta(hours=hours * 2)).isoformat()
    now_cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    prior_outcomes = [
        e for e in read_ledger(hours=hours * 2)
        if e.get("event") == "SKILL_OUTCOME"
        and e.get("ts", "") >= prior_cutoff
        and e.get("ts", "") < now_cutoff
    ]
    prior_groups = defaultdict(list)
    for e in prior_outcomes:
        key = (e.get("agent", ""), e.get("skill", ""))
        prior_groups[key].append(e)

    # Dedup by agent+skill+day
    existing_agg_keys = set()
    for e in events:
        if e.get("event") == "SKILL_AGGREGATE" and e.get("window_hours") == hours:
            day = e.get("ts", "")[:10]
            existing_agg_keys.add(f"{e.get('agent')}:{e.get('skill')}:{day}")

    new_aggregates = 0
    today = datetime.now().strftime("%Y-%m-%d")

    for (agent, skill), outcomes in groups.items():
        agg_key = f"{agent}:{skill}:{today}"
        if agg_key in existing_agg_keys:
            continue

        n = len(outcomes)
        success_count = sum(1 for o in outcomes if o.get("task_success"))
        success_rate = success_count / n if n > 0 else 0
        avg_oq = sum(o.get("output_quality", 0) for o in outcomes) / n if n > 0 else 0
        avg_fit = sum(o.get("fit_score", 0) for o in outcomes) / n if n > 0 else 0
        pc_rate = sum(1 for o in outcomes if o.get("completed_protocol")) / n if n > 0 else 0
        error_count = sum(1 for o in outcomes if o.get("error_signal"))
        cc_rate = sum(1 for o in outcomes if o.get("executor") == "claude-code") / n if n > 0 else 0

        prior = prior_groups.get((agent, skill), [])
        trend = "stable"
        if prior:
            prior_n = len(prior)
            prior_sr = sum(1 for o in prior if o.get("task_success")) / prior_n
            delta = success_rate - prior_sr
            if delta > 0.1:
                trend = "improving"
            elif delta < -0.1:
                trend = "declining"

        action = "keep" if success_rate >= 0.7 else ("review" if success_rate >= 0.4 else "replace")

        aggregate = {
            "event": "SKILL_AGGREGATE",
            "ts": datetime.now().isoformat(),
            "agent": agent,
            "skill": skill,
            "window_hours": hours,
            "task_count": n,
            "success_count": success_count,
            "success_rate": round(success_rate, 3),
            "avg_output_quality": round(avg_oq, 2),
            "avg_fit_score": round(avg_fit, 2),
            "protocol_completion_rate": round(pc_rate, 3),
            "error_signal_count": error_count,
            "claude_code_rate": round(cc_rate, 3),
            "trend": trend,
            "recommended_action": action,
            "skill_version": 1,
        }

        _kp_append_ledger(aggregate)
        new_aggregates += 1

    return new_aggregates


def main():
    parser = argparse.ArgumentParser(description='Skill outcome scorer')
    parser.add_argument('--hours', type=int, default=24, help='Score skills from last N hours')
    parser.add_argument('--summary', action='store_true', help='Print skill summary')
    parser.add_argument('--agent', help='Filter by agent')
    args = parser.parse_args()

    if args.summary:
        print(generate_skill_summary(agent=args.agent, hours=args.hours))
        return

    new_outcomes = score_all_skills(args.hours)
    print(f"Scored {new_outcomes} new skill invocation(s)")

    new_aggregates = generate_skill_aggregates(args.hours)
    print(f"Generated {new_aggregates} new SKILL_AGGREGATE event(s)")


if __name__ == "__main__":
    main()
