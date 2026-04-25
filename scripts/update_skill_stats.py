#!/usr/bin/env python3
"""
Aggregates SKILL_OUTCOME events into skill-stats.json.
Run hourly in the reflection pipeline before prepare_reflection_context.py.

Output format:
{
  "generated": "ISO8601",
  "agents": {
    "temujin": {
      "/horde-brainstorming": {
        "uses_7d": 11, "success_rate": 0.91,
        "avg_output_quality": 2.7, "avg_fit_score": 2.4,
        "protocol_completion_rate": 0.82,
        "claude_code_rate": 1.0,
        "trend": "stable", "recommended_action": "keep"
      }
    }
  }
}
"""
from __future__ import annotations
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kurultai_ledger import read_ledger

SKILL_STATS = Path.home() / ".openclaw/agents/main/logs/skill-stats.json"



def compute_trend(now_rate, prev_rate):
    if prev_rate is None:
        return "stable"
    delta = now_rate - prev_rate
    if delta > 0.1:
        return "improving"
    elif delta < -0.1:
        return "declining"
    return "stable"


def recommended_action(success_rate):
    if success_rate >= 0.7:
        return "keep"
    elif success_rate >= 0.4:
        return "review"
    return "replace"


def update_stats():
    """Read SKILL_OUTCOME events and write skill-stats.json."""
    events_7d = read_ledger(hours=7 * 24)

    cutoff_24h = (datetime.now() - timedelta(hours=24)).isoformat()
    cutoff_48h = (datetime.now() - timedelta(hours=48)).isoformat()

    events_24h = [e for e in events_7d if e.get("ts", "") >= cutoff_24h]
    events_prior_24h = [
        e for e in events_7d
        if e.get("ts", "") >= cutoff_48h and e.get("ts", "") < cutoff_24h
    ]

    def group_outcomes(events):
        groups = defaultdict(lambda: defaultdict(list))
        for e in events:
            if e.get("event") == "SKILL_OUTCOME":
                groups[e.get("agent", "")][e.get("skill", "")].append(e)
        return groups

    groups_7d = group_outcomes(events_7d)
    groups_24h = group_outcomes(events_24h)
    groups_prior = group_outcomes(events_prior_24h)

    agents_data = {}
    all_agents = set(groups_7d.keys()) | set(groups_24h.keys())

    for agent in all_agents:
        if not agent:
            continue
        agent_skills = {}
        all_skills = set(groups_7d.get(agent, {}).keys()) | set(groups_24h.get(agent, {}).keys())

        for skill in all_skills:
            if not skill:
                continue
            outcomes_7d = groups_7d.get(agent, {}).get(skill, [])
            outcomes_24h = groups_24h.get(agent, {}).get(skill, [])
            outcomes_prior = groups_prior.get(agent, {}).get(skill, [])

            n_7d = len(outcomes_7d)
            n_24h = len(outcomes_24h)
            n_prior = len(outcomes_prior)

            if n_7d == 0:
                continue

            sr_24h = sum(1 for o in outcomes_24h if o.get("task_success")) / n_24h if n_24h > 0 else None
            sr_prior = sum(1 for o in outcomes_prior if o.get("task_success")) / n_prior if n_prior > 0 else None
            sr_7d = sum(1 for o in outcomes_7d if o.get("task_success")) / n_7d

            avg_oq = sum(o.get("output_quality", 0) for o in outcomes_7d) / n_7d
            avg_fit = sum(o.get("fit_score", 0) for o in outcomes_7d) / n_7d
            pc_rate = sum(1 for o in outcomes_7d if o.get("completed_protocol")) / n_7d
            cc_rate = sum(1 for o in outcomes_7d if o.get("executor") == "claude-code") / n_7d

            trend = compute_trend(sr_24h, sr_prior) if sr_24h is not None else "stable"
            action = recommended_action(sr_7d)

            agent_skills[skill] = {
                "uses_7d": n_7d,
                "success_rate": round(sr_7d, 3),
                "avg_output_quality": round(avg_oq, 2),
                "avg_fit_score": round(avg_fit, 2),
                "protocol_completion_rate": round(pc_rate, 3),
                "claude_code_rate": round(cc_rate, 3),
                "trend": trend,
                "recommended_action": action,
            }

        if agent_skills:
            agents_data[agent] = agent_skills

    output = {
        "generated": datetime.now().isoformat(),
        "agents": agents_data,
    }

    SKILL_STATS.parent.mkdir(parents=True, exist_ok=True)
    tmp = SKILL_STATS.with_suffix(".tmp")
    tmp.write_text(json.dumps(output, indent=2))
    os.replace(tmp, SKILL_STATS)
    return len(agents_data)


def main():
    n = update_stats()
    print(f"Updated skill-stats.json for {n} agent(s)")


if __name__ == "__main__":
    main()
