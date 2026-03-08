#!/usr/bin/env python3
"""
Skill Exploration - Epsilon-greedy exploration for skill selection.

Tests alternative skills to learn their effectiveness. When a task completes,
records the outcome for counterfactual analysis.

Usage:
    from skill_exploration import should_explore, explore_skill, record_outcome

    if should_explore(task_summary, suggested_skill):
        actual_skill = explore_skill(suggested_skill)
        # ... execute task ...
        record_outcome(task_id, suggested_skill, actual_skill, success)
"""
import json
import random
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

# Exploration rate
EXPLORATION_EPSILON = 0.05  # 5% of tasks use exploration

# Skill similarity groups (alternatives for exploration)
SKILL_GROUPS = {
    "debugging": ["/horde-debug", "/systematic-debugging"],
    "implementation": ["/horde-implement", "/senior-fullstack", "/dev-deploy"],
    "brainstorming": ["/horde-brainstorming", "/horde-plan"],
    "review": ["/horde-review", "/code-reviewer", "/horde-gate-testing"],
    "research": ["/horde-learn", "/scrapling-research"],
}

EXPLORATION_LOG = Path.home() / ".openclaw/tasks/skill-exploration.jsonl"


def get_skill_group(skill):
    """Get the similarity group for a skill."""
    for group, skills in SKILL_GROUPS.items():
        if skill in skills:
            return skills
    return [skill]


def should_explore(task_summary, suggested_skill, epsilon=None):
    """Determine if we should explore an alternative skill.

    Args:
        task_summary: The task text
        suggested_skill: The skill that was suggested
        epsilon: Exploration rate (default: EXPLORATION_EPSILON)

    Returns:
        bool: True if we should explore
    """
    # Don't explore for critical tasks (high priority)
    critical_keywords = ["urgent", "critical", "production", "outage", "security"]
    if any(kw in task_summary.lower() for kw in critical_keywords):
        return False

    # Don't explore if no alternatives
    alternatives = get_skill_group(suggested_skill)
    if len(alternatives) <= 1:
        return False

    # Epsilon-greedy: random chance
    if random.random() < (epsilon or EXPLORATION_EPSILON):
        return True

    return False


def explore_skill(suggested_skill):
    """Select an alternative skill for exploration.

    Args:
        suggested_skill: The skill that was suggested

    Returns:
        str: The alternative skill to use
    """
    alternatives = get_skill_group(suggested_skill)
    alternatives = [s for s in alternatives if s != suggested_skill]

    if not alternatives:
        return suggested_skill

    return random.choice(alternatives)


def record_exploration(task_id, suggested_skill, actual_skill, agent, reason="random"):
    """Record an exploration decision.

    Args:
        task_id: The task ID
        suggested_skill: The skill that was suggested
        actual_skill: The skill actually used
        agent: The agent executing
        reason: Why we explored (default: "random")
    """
    event = {
        "event": "SKILL_EXPLORATION",
        "ts": datetime.now().isoformat(),
        "task_id": task_id,
        "suggested_skill": suggested_skill,
        "actual_skill": actual_skill,
        "agent": agent,
        "exploration_strategy": "epsilon_greedy",
        "exploration_epsilon": EXPLORATION_EPSILON,
        "reason": reason,
    }

    EXPLORATION_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(EXPLORATION_LOG, "a") as f:
        f.write(json.dumps(event) + "\n")

    return event


def record_outcome(task_id, suggested_skill, actual_skill, success, execution_time_s=None):
    """Record the outcome of an exploration.

    Called when task completes. Joins with SKILL_EXPLORATION event.

    Args:
        task_id: The task ID
        suggested_skill: The skill that was suggested
        actual_skill: The skill actually used
        success: Whether the task succeeded
        execution_time_s: Execution time in seconds (optional)
    """
    # Read existing exploration log
    explorations = []
    if EXPLORATION_LOG.exists():
        with open(EXPLORATION_LOG, "r") as f:
            for line in f:
                try:
                    explorations.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    # Find matching exploration
    for exp in explorations:
        if exp.get("task_id") == task_id and exp.get("outcome_recorded") is not True:
            # Update with outcome
            exp["outcome_recorded"] = True
            exp["outcome_ts"] = datetime.now().isoformat()
            exp["outcome_success"] = success
            if execution_time_s:
                exp["outcome_execution_time_s"] = execution_time_s

            # Write back
            with open(EXPLORATION_LOG, "w") as f:
                for e in explorations:
                    f.write(json.dumps(e) + "\n")

            return exp

    return None


def analyze_exploration(hours=168):
    """Analyze exploration outcomes.

    Returns summary statistics about exploration performance.
    """
    if not EXPLORATION_LOG.exists():
        return {"error": "No exploration data"}

    cutoff = datetime.now() - timedelta(hours=hours)
    explorations = []

    with open(EXPLORATION_LOG, "r") as f:
        for line in f:
            try:
                exp = json.loads(line)
                ts = datetime.fromisoformat(exp.get("ts", ""))
                if ts >= cutoff:
                    explorations.append(exp)
            except (json.JSONDecodeError, ValueError):
                continue

    if not explorations:
        return {"error": f"No explorations in last {hours}h"}

    # Analyze
    total = len(explorations)
    with_outcome = [e for e in explorations if e.get("outcome_recorded")]
    successful = [e for e in with_outcome if e.get("outcome_success")]

    # Compare suggested vs actual
    by_pair = defaultdict(lambda: {"suggested": 0, "actual": 0, "success": 0})
    for e in with_outcome:
        pair = (e.get("suggested_skill"), e.get("actual_skill"))
        by_pair[pair]["suggested"] += 1
        by_pair[pair]["actual"] += 1
        if e.get("outcome_success"):
            by_pair[pair]["success"] += 1

    return {
        "window_hours": hours,
        "total_explorations": total,
        "explorations_with_outcome": len(with_outcome),
        "success_rate": len(successful) / len(with_outcome) if with_outcome else 0,
        "by_skill_pair": [
            {
                "suggested": suggested,
                "actual": actual,
                "count": stats["actual"],
                "success_rate": stats["success"] / stats["actual"] if stats["actual"] > 0 else 0,
            }
            for (suggested, actual), stats in sorted(by_pair.items(), key=lambda x: x[1]["actual"], reverse=True)
        ],
    }


def print_analysis(hours=168):
    """Print exploration analysis to stdout."""
    analysis = analyze_exploration(hours)

    if "error" in analysis:
        print(f"Exploration Analysis: {analysis['error']}")
        return

    print(f"\n=== Skill Exploration Analysis (last {hours}h) ===")
    print(f"Total explorations: {analysis['total_explorations']}")
    print(f"With outcome: {analysis['explorations_with_outcome']}")
    print(f"Success rate: {analysis['success_rate']:.1%}")

    if analysis.get("by_skill_pair"):
        print("\nBy skill pair:")
        for pair in analysis["by_skill_pair"][:10]:  # Top 10
            print(f"  {pair['suggested']} → {pair['actual']}: "
                  f"{pair['count']}x, {pair['success_rate']:.1%} success")


def main():
    import argparse
    import sys

    sys.path.insert(0, Path(__file__).parent)
    from kurultai_ledger import append_ledger

    parser = argparse.ArgumentParser(description="Skill exploration analysis")
    parser.add_argument("--hours", type=int, default=168, help="Analysis window (default: 168h)")
    parser.add_argument("--analyze", action="store_true", help="Analyze explorations")
    parser.add_argument("--test", nargs=2, metavar=("SUMMARY", "SKILL"), help="Test exploration decision")
    args = parser.parse_args()

    if args.test:
        summary, skill = args.test
        should = should_explore(summary, skill)
        print(f"Should explore '{summary}' with skill {skill}: {should}")
        if should:
            actual = explore_skill(skill)
            print(f"  → Would use: {actual}")

    elif args.analyze:
        print_analysis(args.hours)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
