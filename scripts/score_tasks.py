#!/usr/bin/env python3
"""
Task Quality Scorecard

Reads task-ledger.jsonl and computes quality scores for each completed task.
Scores are appended back to the ledger as SCORED events.

Scoring dimensions (0-10 total):
  - delegation_score (0-2): Was the task delegated or self-routed?
  - domain_match_score (0-3): Did the destination agent match the task domain?
  - substantive_score (0-3): Did execution produce real output?
  - pending_time_score (0-2): How fast did the task move from QUEUED to EXECUTING?

Usage:
    python3 score_tasks.py                    # Score all unscored tasks
    python3 score_tasks.py --hours 1          # Score tasks from last N hours
    python3 score_tasks.py --summary          # Print scorecard summary
"""

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kurultai_ledger import append_ledger as _kp_append_ledger, read_ledger

# Domain keywords for domain_match validation
# Single source of truth: task_intake.py:AGENT_KEYWORDS
# Previously maintained a separate copy that drifted (missing keywords caused
# correctly-routed tasks to score as "weak domain match" 1/3 instead of 2-3/3).
from task_intake import AGENT_KEYWORDS
AGENT_DOMAINS = AGENT_KEYWORDS


def normalize_score(scored_event):
    """Normalize a SCORED event to the /10 scale.

    score_version 2 (current): 0-10, already correct.
    score_version missing or 1: 0-8 (no pending_time), scale to /10.
    """
    version = scored_event.get("score_version")
    total = scored_event.get("total_score", 0)
    if version and version >= 2:
        return total
    return round(total * 10 / 8, 1)



def group_by_task_id(events):
    """Group events by task_id, building a lifecycle view."""
    tasks = defaultdict(list)
    for e in events:
        tid = e.get("task_id")
        if tid:
            tasks[tid].append(e)
    return tasks


def score_delegation(task_events):
    """Score 0-2: Was the task properly delegated?

    2 = Routed to a specialist agent (not kublai, not subagent)
    1 = Routed to subagent (acceptable but not ideal)
    0 = Self-routed to kublai (routing failure)
    """
    queued = [e for e in task_events if e.get("event") == "QUEUED"]
    if not queued:
        return 1  # No routing data available, neutral score

    agent = queued[0].get("agent", "")
    if agent == "kublai":
        return 0
    if agent == "subagent":
        return 1
    return 2


def score_domain_match(task_events):
    """Score 0-3: Does the agent match the task domain?

    3 = Strong domain keyword match (3+ keywords)
    2 = Moderate match (1-2 keywords)
    1 = Weak match (0 keywords but agent exists)
    0 = No agent or clear mismatch
    """
    queued = [e for e in task_events if e.get("event") == "QUEUED"]
    if not queued:
        return 1

    agent = queued[0].get("agent", "")
    task_summary = queued[0].get("task_summary", "").lower()

    if agent not in AGENT_DOMAINS:
        return 0

    domain_keywords = AGENT_DOMAINS[agent]
    matches = sum(1 for kw in domain_keywords if kw in task_summary)

    if matches >= 3:
        return 3
    if matches >= 1:
        return 2
    return 1


def score_substantive(task_events):
    """Score 0-3: Did execution produce real output?

    3 = Success with substantial output (10+ lines)
    2 = Success with some output
    1 = Failed but attempted (has execution detail)
    0 = No execution data or empty output
    """
    details = [e for e in task_events if e.get("event") == "EXECUTION_DETAIL"]
    completed = [e for e in task_events if e.get("event") in ("COMPLETED", "FAILED")]

    if not details and not completed:
        return 0

    # Check execution detail
    if details:
        detail = details[-1]
        if detail.get("success"):
            output_lines = detail.get("output_lines", 0)
            if output_lines >= 10:
                return 3
            return 2
        return 1

    # Fallback to COMPLETED/FAILED events
    if any(e.get("event") == "COMPLETED" for e in completed):
        return 2
    return 1


def score_pending_time(task_events):
    """Score 0-2: How fast did the task move from QUEUED to EXECUTING?

    2 = QUEUED→EXECUTING < 60s
    1 = 60-300s
    0 = >300s or unmeasurable
    """
    queued = [e for e in task_events if e.get("event") == "QUEUED"]
    executing = [e for e in task_events if e.get("event") == "EXECUTING"]

    if not queued or not executing:
        return 0  # unmeasurable

    try:
        queued_ts = datetime.fromisoformat(queued[0]["ts"])
        executing_ts = datetime.fromisoformat(executing[0]["ts"])
        delta_s = (executing_ts - queued_ts).total_seconds()
    except (KeyError, ValueError, TypeError):
        return 0

    if delta_s < 0:
        return 0  # clock skew or data issue
    if delta_s < 60:
        return 2
    if delta_s < 300:
        return 1
    return 0


def detect_self_route_flag(task_events):
    """Detect if kublai routed a design/implementation task to itself."""
    queued = [e for e in task_events if e.get("event") == "QUEUED"]
    if not queued:
        return False

    agent = queued[0].get("agent", "")
    task_summary = queued[0].get("task_summary", "").lower()

    if agent != "kublai":
        return False

    # Check if task contains specialist-domain keywords
    specialist_keywords = ["design", "build", "implement", "research", "write",
                          "test", "audit", "monitor", "fix", "create", "plan",
                          "brainstorm", "payment", "protocol"]
    return any(kw in task_summary for kw in specialist_keywords)


def score_all_tasks(hours=None):
    """Score all unscored tasks and append SCORED events."""
    events = read_ledger(hours)
    tasks = group_by_task_id(events)

    # Find already-scored task_ids
    scored_ids = {e["task_id"] for e in events if e.get("event") == "SCORED"}

    results = []
    new_scores = 0

    for task_id, task_events in tasks.items():
        if task_id in scored_ids:
            continue

        # Only score tasks that have reached COMPLETED or FAILED
        terminal = [e for e in task_events if e.get("event") in ("COMPLETED", "FAILED")]
        if not terminal:
            continue

        delegation = score_delegation(task_events)
        domain_match = score_domain_match(task_events)
        substantive = score_substantive(task_events)
        pending_time = score_pending_time(task_events)
        self_route = detect_self_route_flag(task_events)
        total = delegation + domain_match + substantive + pending_time

        score_entry = {
            "task_id": task_id,
            "event": "SCORED",
            "ts": datetime.now().isoformat(),
            "delegation_score": delegation,
            "domain_match_score": domain_match,
            "substantive_score": substantive,
            "pending_time_score": pending_time,
            "total_score": total,
            "self_route_flag": self_route,
            "agent": task_events[0].get("agent", "unknown"),
            "score_version": 2,
        }

        # Append to ledger
        _kp_append_ledger(score_entry)
        new_scores += 1

        results.append(score_entry)

    return results, new_scores


def generate_summary(hours=None):
    """Generate a scorecard summary for reflection consumption."""
    events = read_ledger(hours)
    scored = [e for e in events if e.get("event") == "SCORED"]

    if not scored:
        return "No scored tasks found."

    total_tasks = len(scored)
    avg_total = sum(normalize_score(s) for s in scored) / total_tasks
    avg_delegation = sum(s["delegation_score"] for s in scored) / total_tasks
    avg_domain = sum(s["domain_match_score"] for s in scored) / total_tasks
    avg_substance = sum(s["substantive_score"] for s in scored) / total_tasks
    avg_pending = sum(s.get("pending_time_score", 0) for s in scored) / total_tasks
    self_routes = sum(1 for s in scored if s.get("self_route_flag"))

    # Per-agent breakdown
    agent_scores = defaultdict(list)
    for s in scored:
        agent_scores[s.get("agent", "unknown")].append(normalize_score(s))

    lines = [
        f"## Task Quality Scorecard ({total_tasks} tasks)",
        f"- Average score: {avg_total:.1f}/10",
        f"- Delegation: {avg_delegation:.1f}/2 | Domain match: {avg_domain:.1f}/3 | Substance: {avg_substance:.1f}/3 | Pending time: {avg_pending:.1f}/2",
        f"- Self-route violations: {self_routes}",
        "",
        "### Per-Agent Scores",
    ]
    for agent, scores_list in sorted(agent_scores.items()):
        avg = sum(scores_list) / len(scores_list)
        lines.append(f"- {agent}: {avg:.1f}/10 ({len(scores_list)} tasks)")

    # Flag low-scoring tasks
    low_scores = [s for s in scored if normalize_score(s) <= 4]
    if low_scores:
        lines.append("")
        lines.append("### Low-Score Tasks (<=4/10)")
        for s in low_scores[:5]:
            lines.append(f"- task_id={s['task_id'][:8]}... agent={s['agent']} score={normalize_score(s)}")

    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Task quality scorer')
    parser.add_argument('--hours', type=int, help='Score tasks from last N hours')
    parser.add_argument('--summary', action='store_true', help='Print scorecard summary')
    args = parser.parse_args()

    if args.summary:
        print(generate_summary(args.hours))
        return

    results, new_scores = score_all_tasks(args.hours)
    print(f"Scored {new_scores} new task(s)")
    for r in results:
        flag = " [SELF-ROUTE]" if r["self_route_flag"] else ""
        print(f"  {r['task_id'][:8]}... {r['agent']}: {r['total_score']}/10{flag}")


if __name__ == "__main__":
    main()
