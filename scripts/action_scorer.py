#!/usr/bin/env python3
"""
Action Scorer — scores discrete agent actions across 6 categories.
Runs hourly alongside score_tasks.py, appends ACTION_SCORED events to ledger.

Categories: MEMORY, REFLECTION, COORDINATION, OUTPUT, DECISION, TOOL_USAGE

Usage:
    python3 action_scorer.py --agent temujin --hours 2
    python3 action_scorer.py --all --hours 1
"""
import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kurultai_paths import AGENTS_DIR as _AGENTS_DIR, VALID_AGENTS
from kurultai_ledger import append_ledger as _kp_append_ledger, read_ledger

AGENTS_DIR = _AGENTS_DIR

TASK_TYPE_TO_SKILL = {
    "debug": ["/horde-debug", "/systematic-debugging"],
    "implement": ["/horde-implement", "/senior-backend", "/senior-frontend"],
    "research": ["/scrapling-research", "/mongke-research", "/lead-research-assistant"],
    "plan": ["/horde-plan", "/implement"],
    "review": ["/horde-review", "/code-reviewer"],
    "brainstorm": ["/horde-brainstorming"],
    "write": ["/content-research-writer", "/changelog-generator"],
    "ops": ["/heartbeat-watchdog", "/tock-gather"],
}



def _append_ledger(entry):
    _kp_append_ledger(entry)


def jaccard_similarity(text1, text2):
    words1 = set(re.findall(r'\w+', text1.lower()))
    words2 = set(re.findall(r'\w+', text2.lower()))
    if not words1 or not words2:
        return 0.0
    intersection = len(words1 & words2)
    union = len(words1 | words2)
    return intersection / union if union > 0 else 0.0


def score_memory_specificity(memory_delta_text):
    """Score memory specificity 0-3."""
    if not memory_delta_text:
        return 0
    words = memory_delta_text.split()
    score = 0
    if len(words) >= 15:
        score += 1
    if (re.search(r'[~/][^\s]*\.[a-z]{1,5}', memory_delta_text) or
            re.search(r'\b\d+\b', memory_delta_text) or
            re.search(r'\b\w+\(\)', memory_delta_text) or
            re.search(r'["`\'].*?["`\']', memory_delta_text)):
        score += 1
    generic = ["task completed", "good session", "all good", "no issues", "everything worked"]
    if not any(g in memory_delta_text.lower() for g in generic):
        score += 1
    return min(3, score)


def detect_stale_rule_repeat(agent, new_rule_text, days=14):
    """Detect if a rule is a stale repeat (Jaccard > 0.7)."""
    memory_dir = AGENTS_DIR / agent / "memory"
    if not memory_dir.exists():
        return False
    for mf in sorted(memory_dir.glob("*.md"), reverse=True)[:days]:
        try:
            content = mf.read_text(encoding="utf-8", errors="replace")
            for line in content.splitlines():
                if "WHEN" in line and "THEN" in line:
                    if jaccard_similarity(new_rule_text, line) > 0.7:
                        return True
        except Exception:
            continue
    return False


def score_rule_adherence(agent, active_rules, task_events):
    """Score rule adherence 0-3."""
    if not active_rules:
        return 1
    followed = 0
    for rule in active_rules[:3]:
        when_match = re.search(r'WHEN\s+(.+?)\s+THEN', rule, re.IGNORECASE)
        if not when_match:
            continue
        trigger = when_match.group(1).lower()
        trigger_words = set(re.findall(r'\w+', trigger))
        if not trigger_words:
            continue
        for event in task_events:
            event_text = json.dumps(event).lower()
            event_words = set(re.findall(r'\w+', event_text))
            overlap = len(trigger_words & event_words) / len(trigger_words)
            if overlap > 0.5:
                followed += 1
                break
    return min(3, followed)


def score_output_artifact(result_file, output_lines, task_success):
    """Score output artifact quality. Returns dict with score 0-3."""
    if not result_file or not os.path.exists(result_file):
        return {"score": 0, "truncation_detected": False, "meaningful_density": 0.0, "reflection_flag": True}
    try:
        content = open(result_file, encoding="utf-8", errors="replace").read()
    except Exception:
        return {"score": 0, "truncation_detected": False, "meaningful_density": 0.0, "reflection_flag": True}

    lines = content.splitlines()
    total = len(lines)
    if total == 0:
        return {"score": 0, "truncation_detected": False, "meaningful_density": 0.0, "reflection_flag": True}

    last_lines = [l.strip() for l in lines[-5:] if l.strip()]
    truncation = bool(
        last_lines and last_lines[-1] and
        last_lines[-1][-1] not in ".!?`\"')" and
        len(last_lines[-1].split()) > 3
    )

    blank = sum(1 for l in lines if not l.strip())
    header_only = sum(1 for l in lines if l.strip().startswith("#") and len(l.split()) <= 3)
    meaningful = max(0, total - blank - header_only)
    density = meaningful / total if total > 0 else 0.0

    score = 0
    if output_lines >= 10 and task_success and not truncation:
        score += 1
    if density >= 0.6:
        score += 1

    return {
        "score": min(3, score),
        "truncation_detected": truncation,
        "meaningful_density": round(density, 2),
        "reflection_flag": truncation or density < 0.4,
    }


def score_skill_selection(skill_invoked, task_summary, scored_total=None):
    """Score 0-3: was the skill appropriate for the task?"""
    if not skill_invoked or not task_summary:
        return 1
    task_lower = task_summary.lower()
    for task_type, skills in TASK_TYPE_TO_SKILL.items():
        if task_type in task_lower:
            if skill_invoked in skills:
                return 3
            return 1
    return 1


def score_tool_efficiency(trace_event):
    """Score tool usage efficiency 0-3."""
    cats = trace_event.get("tool_categories", {})
    total_calls = sum(cats.values())
    bash = cats.get("bash", 0)
    search = cats.get("search", 0)
    errors = trace_event.get("intermediate_errors", 0)

    flags = []
    score = 3

    if bash > 2 and search == 0:
        flags.append("bash_grep_misuse")
        score -= 1
    if total_calls > 60:
        flags.append("tool_thrashing")
        score -= 1
    if total_calls > 0 and errors / total_calls > 0.15:
        flags.append("high_error_rate")
        score -= 1

    score = max(0, score)
    return {"score": score, "flags": flags, "reflection_flag": score < 2}


def compute_memory_score(agent, task_events):
    """Compute memory category score 0-3 from output quality as proxy."""
    detail_events = [e for e in task_events if e.get("event") == "EXECUTION_DETAIL"]
    if not detail_events:
        return 1
    avg_lines = sum(e.get("output_lines", 0) for e in detail_events) / len(detail_events)
    if avg_lines >= 20:
        return 3
    elif avg_lines >= 10:
        return 2
    elif avg_lines > 0:
        return 1
    return 0


def compute_output_score(agent, task_events):
    """Compute output artifact category score 0-3."""
    detail_events = [e for e in task_events if e.get("event") == "EXECUTION_DETAIL"]
    if not detail_events:
        return 1
    scores = []
    for de in detail_events:
        result_file = de.get("result_file")
        output_lines = de.get("output_lines", 0)
        success = de.get("success", False)
        artifact = score_output_artifact(result_file, output_lines, success)
        scores.append(artifact["score"])
    return round(sum(scores) / len(scores)) if scores else 1


def compute_decision_score(agent, task_events):
    """Compute decision quality score 0-3."""
    skill_invocations = [e for e in task_events if e.get("event") == "SKILL_INVOCATION"]
    scored_events = [e for e in task_events if e.get("event") == "SCORED"]
    queued_events = [e for e in task_events if e.get("event") == "QUEUED"]

    if not skill_invocations:
        return 1

    queued_event = queued_events[0] if queued_events else None
    task_summary = queued_event.get("task_summary", "") if queued_event else ""

    scores = []
    for inv in skill_invocations:
        skill = inv.get("skill", "")
        fit = score_skill_selection(skill, task_summary)
        scores.append(fit)

    return round(sum(scores) / len(scores)) if scores else 1


def compute_tool_score(agent, task_events):
    """Compute tool usage score from EXECUTION_TRACE events."""
    trace_events = [e for e in task_events if e.get("event") == "EXECUTION_TRACE"]
    if not trace_events:
        return None
    scores = []
    for te in trace_events:
        result = score_tool_efficiency(te)
        scores.append(result["score"])
    return round(sum(scores) / len(scores)) if scores else None


def generate_action_scored(agent, hours=2):
    """Aggregate action scores into ACTION_SCORED event for the agent."""
    events = read_ledger(hours=hours * 4)

    # Dedup: skip if already scored this hour
    current_hour = datetime.now().strftime("%Y-%m-%dT%H")
    existing = [e for e in events
                if e.get("event") == "ACTION_SCORED"
                and e.get("agent") == agent
                and e.get("hour") == current_hour]
    if existing:
        return None

    agent_events = [e for e in events if e.get("agent") == agent]
    by_task = defaultdict(list)
    for e in agent_events:
        tid = e.get("task_id")
        if tid:
            by_task[tid].append(e)

    if not by_task:
        return None

    # Compute per-category scores across completed tasks
    memory_scores = []
    output_scores = []
    decision_scores = []
    tool_scores = []
    claude_code_tasks = 0
    total_tasks = 0

    for task_id, task_events in by_task.items():
        terminal = [e for e in task_events if e.get("event") in ("COMPLETED", "FAILED")]
        if not terminal:
            continue

        total_tasks += 1
        # Track Claude Code usage
        exec_details = [e for e in task_events if e.get("event") == "EXECUTION_DETAIL"]
        if exec_details and exec_details[-1].get("executor") == "claude-code":
            claude_code_tasks += 1

        memory_scores.append(compute_memory_score(agent, task_events))
        output_scores.append(compute_output_score(agent, task_events))
        decision_scores.append(compute_decision_score(agent, task_events))
        ts = compute_tool_score(agent, task_events)
        if ts is not None:
            tool_scores.append(ts)

    if not memory_scores:
        return None

    def avg(lst):
        return round(sum(lst) / len(lst), 1) if lst else None

    memory_score = avg(memory_scores)
    output_score = avg(output_scores)
    decision_score = avg(decision_scores)
    tool_score = avg(tool_scores) if tool_scores else None
    reflection_score = 1   # placeholder until reflection log parsing
    coordination_score = 1  # placeholder until cross-agent event analysis

    category_scores = {
        "memory": memory_score,
        "output": output_score,
        "decision": decision_score,
    }
    if tool_score is not None:
        category_scores["tool"] = tool_score

    valid_scores = {k: v for k, v in category_scores.items() if v is not None}
    worst_category = min(valid_scores, key=lambda k: valid_scores[k]) if valid_scores else None
    worst_flag = f"low_{worst_category}" if worst_category else None
    needs_reflection = any(v is not None and v < 2 for v in category_scores.values())

    cc_rate = claude_code_tasks / total_tasks if total_tasks > 0 else 0.0

    return {
        "event": "ACTION_SCORED",
        "agent": agent,
        "ts": datetime.now().isoformat(),
        "hour": current_hour,
        "window_hours": hours,
        "memory_score": memory_score,
        "reflection_score": reflection_score,
        "coordination_score": coordination_score,
        "output_score": output_score,
        "decision_score": decision_score,
        "tool_score": tool_score,
        "worst_category": worst_category,
        "worst_flag": worst_flag,
        "reflection_flag": needs_reflection,
        "claude_code_rate": round(cc_rate, 3),
        "tasks_scored": total_tasks,
    }


def main():
    parser = argparse.ArgumentParser(description='Action scorer')
    parser.add_argument('--agent', help='Score specific agent')
    parser.add_argument('--all', action='store_true', help='Score all agents')
    parser.add_argument('--hours', type=int, default=2, help='Hours to look back')
    args = parser.parse_args()

    agents_to_score = VALID_AGENTS if args.all else ([args.agent] if args.agent else [])

    if not agents_to_score:
        print("Specify --agent <name> or --all")
        return

    for agent in agents_to_score:
        scored = generate_action_scored(agent, hours=args.hours)
        if scored:
            _append_ledger(scored)
            print(f"Scored {agent}: worst={scored.get('worst_category')} cc_rate={scored.get('claude_code_rate'):.0%}")
        else:
            print(f"No scoring needed for {agent} (no tasks or already scored this hour)")


if __name__ == "__main__":
    main()
