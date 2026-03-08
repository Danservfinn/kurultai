#!/usr/bin/env python3
"""
Skill Affinity Tracker — Agent-Skill Specialization Detection

Tracks per-agent, per-skill success rates using Bayesian inference.
Computes affinity scores to answer: "Which agent is best for /horde-implement?"

Usage:
    python3 skill_affinity.py --agent temujin --skill horde-implement
    python3 skill_affinity.py --summary
    python3 skill_affinity.py --matrix
    python3 skill_affinity.py --recommendations
"""
import argparse
import json
import sys
from datetime import datetime
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, Path(__file__).parent)
from kurultai_ledger import read_ledger

# Beta prior for Bayesian inference
# alpha=1, beta=1 is uniform prior (no assumptions)
PRIOR_ALPHA = 1
PRIOR_BETA = 1

# Minimum samples before reporting "significant"
MIN_SAMPLES_SIGNIFICANT = 10

# Confidence interval width threshold for "high confidence"
CI_WIDTH_THRESHOLD = 0.20  # 20% width = 95% CI roughly +/-10%


def wilson_score_interval(successes, n, alpha=0.05):
    """Compute Wilson score interval for binomial proportion.

    Returns (lower, upper, width) bounds."""
    if n == 0:
        return 0, 1, 1

    p = successes / n
    z = 1.96  # 95% CI

    denominator = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denominator
    margin = z * ((p * (1 - p) / n + z**2 / (4 * n**2)) ** 0.5) / denominator

    return max(0, center - margin), min(1, center + margin), 2 * margin


def compute_affinities(hours=168):
    """Compute affinities from ledger events.

    Returns dict: {(agent, skill): {'alpha': int, 'beta': int, 'mean': float, 'ci': tuple}}
    """
    events = read_ledger(hours=hours)

    # Collect outcomes
    outcomes = defaultdict(lambda: {'success': 0, 'failure': 0})
    for e in events:
        if e.get('event') != 'SKILL_OUTCOME':
            continue
        agent = e.get('agent', '')
        skill = e.get('skill', '')
        if not agent or not skill:
            continue
        key = (agent, skill)
        if e.get('task_success', False):
            outcomes[key]['success'] += 1
        else:
            outcomes[key]['failure'] += 1

    # Compute posterior distributions
    affinities = {}
    for (agent, skill), counts in outcomes.items():
        alpha = PRIOR_ALPHA + counts['success']
        beta = PRIOR_BETA + counts['failure']
        mean = alpha / (alpha + beta)
        n = counts['success'] + counts['failure']
        lower, upper, width = wilson_score_interval(counts['success'], n)

        affinities[(agent, skill)] = {
            'agent': agent,
            'skill': skill,
            'alpha': alpha,
            'beta': beta,
            'mean': mean,
            'sample_count': n,
            'success_count': counts['success'],
            'ci_lower': lower,
            'ci_upper': upper,
            'ci_width': width,
            'is_significant': n >= MIN_SAMPLES_SIGNIFICANT,
            'is_confident': width <= CI_WIDTH_THRESHOLD,
        }

    return affinities


def compute_specialization_score(affinity, all_affinities_for_skill):
    """Compute specialization score for an agent-skill pair.

    Combines:
    1. Individual success rate (mean)
    2. Relative advantage vs other agents
    3. Confidence (based on sample count)
    """
    if not affinity['is_significant']:
        return 0.0, "insufficient_data"

    # Relative advantage: how much better than average?
    skill_mean = sum(a['mean'] for a in all_affinities_for_skill) / len(all_affinities_for_skill)
    relative_advantage = affinity['mean'] / skill_mean if skill_mean > 0 else 1

    # Confidence: scale by sample count up to MIN_SAMPLES_SIGNIFICANT
    confidence = min(affinity['sample_count'] / MIN_SAMPLES_SIGNIFICANT, 1.0)

    # Specialization score
    score = affinity['mean'] * relative_advantage * confidence

    # Label
    if score >= 0.8:
        label = "strong_specialist"
    elif score >= 0.6:
        label = "specialist"
    elif score >= 0.4:
        label = "generalist"
    else:
        label = "avoid"

    return round(score, 3), label


def print_affinity(agent, skill, hours=168):
    """Print detailed affinity for a single agent-skill pair."""
    affinities = compute_affinities(hours)
    key = (agent, skill)
    if key not in affinities:
        print(f"No data for {agent} + {skill}")
        return

    a = affinities[key]
    print(f"\n=== Affinity: {agent} + {skill} ===")
    print(f"Success rate: {a['mean']:.1%}")
    print(f"Samples: {a['sample_count']} ({a['success_count']} success)")
    print(f"95% CI: [{a['ci_lower']:.1%}, {a['ci_upper']:.1%}] (width: {a['ci_width']:.1%})")
    print(f"Significant: {a['is_significant']} (min {MIN_SAMPLES_SIGNIFICANT})")
    print(f"Confident: {a['is_confident']} (CI width < {CI_WIDTH_THRESHOLD:.0%})")

    # Specialization score
    skill_affinities = [v for k, v in affinities.items() if k[1] == skill]
    score, label = compute_specialization_score(a, skill_affinities)
    print(f"Specialization: {score:.3f} ({label})")


def print_summary(hours=168):
    """Print summary of all agent-skill pairs."""
    affinities = compute_affinities(hours)

    print(f"\n=== Skill Affinity Summary (last {hours}h) ===\n")

    # Group by agent
    by_agent = defaultdict(list)
    for (agent, skill), a in affinities.items():
        by_agent[agent].append((skill, a))

    for agent in sorted(by_agent.keys()):
        print(f"\n{agent.upper()}:")
        for skill, a in sorted(by_agent[agent], key=lambda x: x[1]['mean'], reverse=True):
            sig = "✓" if a['is_significant'] else "."
            conf = "!" if a['is_confident'] else "."
            print(f"  {sig}{conf} {skill}: {a['mean']:.1%} ({a['sample_count']} samples)")


def print_matrix(hours=168):
    """Print agent-skill affinity matrix."""
    affinities = compute_affinities(hours)

    # Get unique agents and skills
    agents = sorted(set(k[0] for k in affinities.keys()))
    skills = sorted(set(k[1] for k in affinities.keys()))

    if not skills:
        print("No skill data available.")
        return

    # Build matrix
    print(f"\n=== Affinity Matrix (success rate, last {hours}h) ===\n")

    # Header
    print(f"{'agent':<12} " + " ".join(f"{s[:15]:>15}" for s in skills[:6]))  # Limit to 6 for readability
    print("-" * (12 + 16 * min(len(skills), 6)))

    for agent in agents:
        row = [f"{agent:<12}"]
        for skill in skills[:6]:
            key = (agent, skill)
            if key in affinities:
                a = affinities[key]
                display = f"{a['mean']:.2f}"
                if a['is_significant']:
                    display += "*"
                row.append(f"{display:>15}")
            else:
                row.append(f"{'-':>15}")
        print(" ".join(row))

    print("\n* = significant (n >= 10)")


def print_recommendations(hours=168):
    """Print routing recommendations based on affinity."""
    affinities = compute_affinities(hours)

    print(f"\n=== Skill Routing Recommendations (last {hours}h) ===\n")

    # Group by skill
    by_skill = defaultdict(list)
    for (agent, skill), a in affinities.items():
        if a['is_significant']:  # Only consider significant pairs
            by_skill[skill].append((agent, a))

    for skill in sorted(by_skill.keys()):
        pairs = sorted(by_skill[skill], key=lambda x: x[1]['mean'], reverse=True)
        best_agent, best_a = pairs[0]

        print(f"\n{skill}:")
        print(f"  Best: {best_agent} ({best_a['mean']:.1%})")

        # Check if significant gap
        if len(pairs) > 1:
            second_best, second_a = pairs[1]
            gap = best_a['mean'] - second_a['mean']
            if gap > 0.15:
                print(f"  Gap: +{gap:.1%} vs {second_agent}")
                print(f"  Recommendation: Route to {best_agent}")

        # Specialization
        score, label = compute_specialization_score(best_a, [a for _, a in pairs])
        print(f"  Specialization: {label}")


def save_affinity_snapshot(hours=168):
    """Save current affinities to JSON for historical tracking."""
    affinities = compute_affinities(hours)

    output = Path.home() / ".openclaw/data/skill-affinities.json"
    output.parent.mkdir(parents=True, exist_ok=True)

    # Convert tuples to strings for JSON
    serializable = {}
    for (agent, skill), a in affinities.items():
        key = f"{agent}:{skill}"
        serializable[key] = a

    snapshot = {
        "ts": datetime.now().isoformat(),
        "window_hours": hours,
        "affinities": serializable,
    }

    with open(output, "w") as f:
        json.dump(snapshot, f, indent=2)

    return output


def main():
    parser = argparse.ArgumentParser(description="Skill affinity tracker")
    parser.add_argument("--hours", type=int, default=168, help="Lookback window (default: 168h = 1 week)")
    parser.add_argument("--agent", help="Filter by agent")
    parser.add_argument("--skill", help="Filter by skill")
    parser.add_argument("--summary", action="store_true", help="Print summary")
    parser.add_argument("--matrix", action="store_true", help="Print affinity matrix")
    parser.add_argument("--recommendations", action="store_true", help="Print routing recommendations")
    parser.add_argument("--save", action="store_true", help="Save snapshot to disk")
    args = parser.parse_args()

    if args.agent and args.skill:
        print_affinity(args.agent, args.skill, args.hours)
    elif args.matrix:
        print_matrix(args.hours)
    elif args.recommendations:
        print_recommendations(args.hours)
    elif args.summary or not args.agent:
        print_summary(args.hours)

    if args.save:
        path = save_affinity_snapshot(args.hours)
        print(f"\nSnapshot saved to {path}")


if __name__ == "__main__":
    main()
