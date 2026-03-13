#!/usr/bin/env python3
"""
route_quality_tracker.py — Capability scoring + routing feedback.

Computes per-agent, per-category quality scores from SCORED events in
task-ledger.jsonl (7-day rolling window). Writes to capability-scores.json
for consumption by task_intake.py (overflow routing) and prepare_reflection_context.py.

Usage:
    python3 route_quality_tracker.py          # Compute + write scores
    python3 route_quality_tracker.py --show   # Print current scores
"""

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kurultai_paths import TASK_LEDGER, LOGS_DIR, AGENT_KEYWORDS
from kurultai_ledger import read_ledger as _kp_read_ledger
from agents_config import AGENTS

# Inline normalize_score (trivial function from archived score_tasks.py):
def normalize_score(raw: float, max_val: float = 10.0) -> float:
    """Normalize score to 0-1 range."""
    return max(0.0, min(1.0, raw / max_val))

# Build AGENT_DOMAINS from AGENT_KEYWORDS for backward compat
AGENT_DOMAINS = {agent: keywords for agent, keywords in AGENT_KEYWORDS.items()}

CAPABILITY_SCORES_FILE = LOGS_DIR / "capability-scores.json"
SCORES_STALENESS_S = 7200  # 2 hours — stale if older than this
ROLLING_DAYS = 7
MIN_TASKS_FOR_DIVERT = 3   # Minimum tasks before we trust the score for diversion
DIVERT_THRESHOLD = 4.0     # avg_score < 4.0/10 triggers potential diversion


def _detect_category(task_summary):
    """Detect the primary domain category from task summary text."""
    text = (task_summary or "").lower()
    # Score each agent's domain match and return best-matching agent domain
    best_agent, best_count = None, 0
    for agent, keywords in AGENT_DOMAINS.items():
        count = sum(1 for kw in keywords if kw in text)
        if count > best_count:
            best_agent, best_count = agent, count
    # Map agent domain -> category string
    DOMAIN_CATEGORY = {
        "temujin": "code",
        "jochi": "security",
        "mongke": "research",
        "chagatai": "content",
        "ogedei": "ops",
        "kublai": "routing",
    }
    if best_agent and best_count > 0:
        return DOMAIN_CATEGORY.get(best_agent)
    return None


def _recency_weight(event_ts_str, now=None):
    """Compute recency weight for an event: linear decay over ROLLING_DAYS.

    Returns a weight between 0.1 (oldest) and 1.0 (newest).
    This prevents transient infrastructure failures (e.g. model stalls)
    from permanently depressing capability scores.
    """
    if now is None:
        now = datetime.now()
    try:
        ts = datetime.fromisoformat(event_ts_str)
        age_days = (now - ts).total_seconds() / 86400
        return max(0.1, 1.0 - (age_days / ROLLING_DAYS) * 0.9)
    except (ValueError, TypeError):
        return 0.5  # unknown age gets neutral weight


def compute_capability_scores():
    """Read SCORED events from last 7 days, compute per-agent per-category scores.

    Uses recency weighting: recent events count more than older ones.
    This naturally decays transient failure periods (model stalls, infra issues).

    Returns dict: {agent: {category: {avg_score, task_count, fail_rate}, overall: {...}}}
    """
    # Single pass: collect SCORED, QUEUED, and FAILED events together
    scored_events = []
    queued_events = {}  # task_id -> queued event
    failed_events = []  # raw failed events (filtered below)

    now = datetime.now()

    all_events = _kp_read_ledger(hours=ROLLING_DAYS * 24)
    if not all_events:
        return {}

    scored_task_ids = set()
    for entry in all_events:
        ev = entry.get("event")
        if ev == "SCORED":
            scored_events.append(entry)
            scored_task_ids.add(entry.get("task_id"))
        elif ev == "QUEUED":
            queued_events[entry.get("task_id")] = entry
        elif ev == "FAILED":
            failed_events.append(entry)

    # Only count failures for tasks that never succeeded (no SCORED event).
    # Tasks that failed due to infra issues (model stalls) and were never
    # retried/scored should not permanently penalize agent capability.
    agent_fail_weighted = defaultdict(float)
    for entry in failed_events:
        if entry.get("task_id") not in scored_task_ids:
            w = _recency_weight(entry.get("ts", ""), now)
            agent_fail_weighted[entry.get("agent", "unknown")] += w

    # Build per-agent, per-category score buckets (weighted)
    agent_category_scores = defaultdict(lambda: defaultdict(list))  # (score, weight) tuples
    agent_all_scores = defaultdict(list)

    for score_ev in scored_events:
        agent = score_ev.get("agent", "unknown")
        task_id = score_ev.get("task_id")
        total = normalize_score(score_ev)
        w = _recency_weight(score_ev.get("ts", ""), now)

        # Get task summary for category detection
        queued = queued_events.get(task_id)
        task_summary = queued.get("task_summary", "") if queued else ""
        category = _detect_category(task_summary)

        if category:
            agent_category_scores[agent][category].append((total, w))
        agent_all_scores[agent].append((total, w))

    # Build output dict
    result = {}
    for agent, weighted_scores in agent_all_scores.items():
        n = len(weighted_scores)
        total_weight = sum(w for _, w in weighted_scores)
        avg = sum(s * w for s, w in weighted_scores) / total_weight if total_weight else 0
        weighted_fails = agent_fail_weighted.get(agent, 0)
        fail_rate = weighted_fails / max(total_weight + weighted_fails, 0.1)

        result[agent] = {
            "overall": {
                "avg_score": round(avg, 2),
                "task_count": n,
                "fail_rate": round(fail_rate, 3),
            }
        }
        for category, cat_weighted in agent_category_scores.get(agent, {}).items():
            cat_n = len(cat_weighted)
            cat_total_w = sum(w for _, w in cat_weighted)
            cat_avg = sum(s * w for s, w in cat_weighted) / cat_total_w if cat_total_w else 0
            result[agent][category] = {
                "avg_score": round(cat_avg, 2),
                "task_count": cat_n,
            }

    return result


def update_scores():
    """Compute and write scores to capability-scores.json."""
    scores = compute_capability_scores()
    os.makedirs(str(LOGS_DIR), exist_ok=True)
    with open(str(CAPABILITY_SCORES_FILE), "w") as f:
        json.dump(scores, f, indent=2)
    print(f"Updated capability scores for {len(scores)} agents -> {CAPABILITY_SCORES_FILE}")

    # Emit pipeline event for observability
    try:
        from neo4j_task_tracker import get_tracker
        get_tracker().emit_pipeline_event(
            "CAPABILITY_SCORE_UPDATE",
            payload={"agents_scored": len(scores)},
        )
    except Exception:
        pass

    return scores


def load_scores():
    """Read scores with staleness check. Returns empty dict if stale."""
    if not CAPABILITY_SCORES_FILE.exists():
        return {}
    try:
        mtime = CAPABILITY_SCORES_FILE.stat().st_mtime
        if time.time() - mtime > SCORES_STALENESS_S:
            return {}
        with open(str(CAPABILITY_SCORES_FILE)) as f:
            return json.load(f)
    except Exception:
        return {}


AGENT_HEALTH_FLAGS_FILE = LOGS_DIR / "agent-health-flags.json"
HEALTH_FLAGS_MAX_AGE_S = 600  # ignore health flags older than 10 min


def _load_health_flags():
    """Load short-term agent health flags written by ogedei-watchdog."""
    if not AGENT_HEALTH_FLAGS_FILE.exists():
        return {}
    try:
        mtime = AGENT_HEALTH_FLAGS_FILE.stat().st_mtime
        if time.time() - mtime > HEALTH_FLAGS_MAX_AGE_S:
            return {}
        with open(str(AGENT_HEALTH_FLAGS_FILE)) as f:
            return json.load(f).get("agents", {})
    except Exception:
        return {}


def should_divert(agent, task_text, scores):
    """Return (bool, reason) if agent's quality score is too low for this task.

    Checks both:
    - 7-day rolling capability scores (MIN_TASKS_FOR_DIVERT samples needed)
    - Short-term (1h) failure rate flags from ogedei-watchdog
    """
    # Short-term failure rate check (high priority — catches acute failures)
    try:
        health_flags = _load_health_flags()
        agent_health = health_flags.get(agent, {})
        if agent_health.get("flagged"):
            fail_rate = agent_health.get("fail_rate_1h", 0)
            total = agent_health.get("total_1h", 0)
            return True, f"high 1h failure rate: {fail_rate:.0%} ({total} tasks)"
    except Exception:
        pass

    if not scores:
        return False, "no score data"

    agent_data = scores.get(agent, {})
    if not agent_data:
        return False, "no data for agent"

    # Check category-specific score
    category = _detect_category(task_text)
    if category and category in agent_data:
        cat_data = agent_data[category]
        if cat_data.get("task_count", 0) >= MIN_TASKS_FOR_DIVERT:
            if cat_data.get("avg_score", 10) < DIVERT_THRESHOLD:
                return True, f"low {category} score: {cat_data['avg_score']:.1f}/10"

    # Check overall score as secondary signal
    overall = agent_data.get("overall", {})
    overall_count = overall.get("task_count", 0)
    overall_avg = overall.get("avg_score", 10)
    if overall_count >= MIN_TASKS_FOR_DIVERT * 2 and overall_avg < DIVERT_THRESHOLD:
        return True, f"low overall score: {overall_avg:.1f}/10"

    return False, "score ok"


def main():
    parser = argparse.ArgumentParser(description="Route quality capability scorer")
    parser.add_argument("--show", action="store_true", help="Show current scores without updating")
    args = parser.parse_args()

    if args.show:
        scores = load_scores()
        if not scores:
            # Compute fresh if stale or missing
            scores = compute_capability_scores()
        if not scores:
            print("No capability score data available.")
            return
        for agent, data in sorted(scores.items()):
            overall = data.get("overall", {})
            print(f"\n{agent}: {overall.get('avg_score', '?'):.1f}/10 "
                  f"({overall.get('task_count', 0)} tasks, fail_rate={overall.get('fail_rate', 0):.1%})")
            for cat, cat_data in sorted((k, v) for k, v in data.items() if k != "overall"):
                flag = " [LOW]" if cat_data.get("avg_score", 10) < DIVERT_THRESHOLD else ""
                print(f"  {cat}: {cat_data.get('avg_score', '?'):.1f}/10 "
                      f"({cat_data.get('task_count', 0)} tasks){flag}")
        return

    update_scores()


if __name__ == "__main__":
    main()
