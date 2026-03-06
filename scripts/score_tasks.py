#!/usr/bin/env python3
"""
Task Quality Scorecard

Reads task-ledger.jsonl and computes quality scores for each completed task.
Scores are appended back to the ledger as SCORED events.

Scoring dimensions (0-8 total):
  - delegation_score (0-2): Was the task delegated or self-routed?
  - domain_match_score (0-3): Did the destination agent match the task domain?
  - substantive_score (0-3): Did execution produce real output?

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

TASK_LEDGER = "/Users/kublai/.openclaw/tasks/task-ledger.jsonl"

# Domain keywords for domain_match validation
AGENT_DOMAINS = {
    "temujin": ["code", "build", "implement", "fix", "api", "feature", "deploy",
                "design", "architect", "plan", "brainstorm", "payment", "protocol",
                "sdk", "script", "database", "infrastructure"],
    "mongke": ["research", "investigate", "discover", "explore", "competitor",
               "market", "trend", "find", "study"],
    "chagatai": ["write", "document", "blog", "content", "article", "copy",
                 "marketing", "readme", "changelog"],
    "jochi": ["test", "verify", "audit", "security", "review", "analyze",
              "vulnerability", "scan", "pattern"],
    "ogedei": ["monitor", "health", "restart", "backup", "alert", "ops",
               "uptime", "incident"],
    "kublai": ["triage", "coordinate", "route", "assess", "status"],
}


def read_ledger(hours=None):
    """Read all events from task-ledger.jsonl, optionally filtered by time."""
    if not os.path.exists(TASK_LEDGER):
        return []

    cutoff = None
    if hours:
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()

    events = []
    with open(TASK_LEDGER, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if cutoff and entry.get("ts", "") < cutoff:
                    continue
                events.append(entry)
            except json.JSONDecodeError:
                continue
    return events


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
        self_route = detect_self_route_flag(task_events)
        total = delegation + domain_match + substantive

        score_entry = {
            "task_id": task_id,
            "event": "SCORED",
            "ts": datetime.now().isoformat(),
            "delegation_score": delegation,
            "domain_match_score": domain_match,
            "substantive_score": substantive,
            "total_score": total,
            "self_route_flag": self_route,
            "agent": task_events[0].get("agent", "unknown"),
        }

        # Append to ledger
        try:
            with open(TASK_LEDGER, "a") as f:
                f.write(json.dumps(score_entry) + "\n")
            new_scores += 1
        except Exception:
            pass

        results.append(score_entry)

    return results, new_scores


def generate_summary(hours=None):
    """Generate a scorecard summary for reflection consumption."""
    events = read_ledger(hours)
    scored = [e for e in events if e.get("event") == "SCORED"]

    if not scored:
        return "No scored tasks found."

    total_tasks = len(scored)
    avg_total = sum(s["total_score"] for s in scored) / total_tasks
    avg_delegation = sum(s["delegation_score"] for s in scored) / total_tasks
    avg_domain = sum(s["domain_match_score"] for s in scored) / total_tasks
    avg_substance = sum(s["substantive_score"] for s in scored) / total_tasks
    self_routes = sum(1 for s in scored if s.get("self_route_flag"))

    # Per-agent breakdown
    agent_scores = defaultdict(list)
    for s in scored:
        agent_scores[s.get("agent", "unknown")].append(s["total_score"])

    lines = [
        f"## Task Quality Scorecard ({total_tasks} tasks)",
        f"- Average score: {avg_total:.1f}/8",
        f"- Delegation: {avg_delegation:.1f}/2 | Domain match: {avg_domain:.1f}/3 | Substance: {avg_substance:.1f}/3",
        f"- Self-route violations: {self_routes}",
        "",
        "### Per-Agent Scores",
    ]
    for agent, scores in sorted(agent_scores.items()):
        avg = sum(scores) / len(scores)
        lines.append(f"- {agent}: {avg:.1f}/8 ({len(scores)} tasks)")

    # Flag low-scoring tasks
    low_scores = [s for s in scored if s["total_score"] <= 3]
    if low_scores:
        lines.append("")
        lines.append("### Low-Score Tasks (<=3/8)")
        for s in low_scores[:5]:
            lines.append(f"- task_id={s['task_id'][:8]}... agent={s['agent']} score={s['total_score']}")

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
        print(f"  {r['task_id'][:8]}... {r['agent']}: {r['total_score']}/8{flag}")


if __name__ == "__main__":
    main()
