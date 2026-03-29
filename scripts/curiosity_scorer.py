#!/usr/bin/env python3
"""
Curiosity Scorer — Score and rank candidate questions using a composite formula.

Composite scoring considers:
- Base priority hint (1-10)
- Recency boost for contextual questions (up to 3.0, decays over 24h)
- Novelty boost (penalize recently-asked categories, up to 2.0)
- Relationship depth for human questions (up to 2.0)
- Self-urgency if task failure rate > 20% (2.0 for self category)
- Cost penalty: web_search -1.0, agent_delegation -1.5

Usage:
    from curiosity_scorer import score_question, rank_and_filter
"""

import sys
import os
import json
import logging
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from curiosity_dedup import is_duplicate_question, get_canonical_hash
from curiosity_budget import load_config

logger = logging.getLogger(__name__)


def _getfield(obj, name, default=None):
    """Get a field from a dataclass or dict, with default."""
    try:
        val = getattr(obj, name, None)
        if val is not None:
            return val
    except Exception:
        pass
    try:
        val = obj[name]
        if val is not None:
            return val
    except (TypeError, KeyError, IndexError):
        pass
    return default


# ---------------------------------------------------------------------------
# CuriosityContext import with graceful fallback
# ---------------------------------------------------------------------------

try:
    from curiosity_context import CuriosityContext
except ImportError:
    # CuriosityContext not yet available -- define a minimal stub so the module
    # can still be imported and tested with mock objects.
    CuriosityContext = None


# ---------------------------------------------------------------------------
# Cost penalties by research_method
# ---------------------------------------------------------------------------

COST_PENALTIES = {
    "web_search": -1.0,
    "agent_delegation": -1.5,
    "neo4j_lookup": 0.0,
    "memory_scan": 0.0,
    "llm_reasoning": -0.5,
}


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _recency_boost(q, context) -> float:
    """Contextual questions get up to 3.0 boost, decaying over 24h.

    Uses q.created_at (epoch seconds) or q.get("created_at").
    """
    category = _getfield(q, "category", "")
    if category != "contextual":
        return 0.0

    created_at = _getfield(q, "created_at")
    if created_at is None:
        return 1.5  # unknown age -- give half boost

    now = time.time()
    if isinstance(created_at, (int, float)):
        age_seconds = now - created_at
    elif isinstance(created_at, datetime):
        age_seconds = now - created_at.timestamp()
    else:
        return 1.5

    hours_old = age_seconds / 3600.0
    if hours_old >= 24:
        return 0.0
    # Linear decay: 3.0 at age 0 -> 0.0 at age 24h
    return max(0.0, 3.0 * (1.0 - hours_old / 24.0))


def _novelty_boost(q, context) -> float:
    """Penalize recently-asked categories. Up to 2.0 boost for novel categories.

    Uses context.recent_category_counts -- a dict {category: int} of how many
    questions in that category were asked today.
    """
    category = _getfield(q, "category", "")
    recent_counts = {}
    if context is not None:
        recent_counts = getattr(context, "recent_category_counts", None) or {}
        if callable(getattr(context, "get", None)):
            recent_counts = context.get("recent_category_counts", recent_counts)

    asked_today = recent_counts.get(category, 0)
    if asked_today == 0:
        return 2.0
    elif asked_today == 1:
        return 1.0
    elif asked_today == 2:
        return 0.5
    return 0.0


def _relationship_depth_boost(q, context) -> float:
    """Human-category questions get up to 2.0 boost based on message count.

    Uses context.relationship_depths -- a dict {target: int} of message counts.
    """
    category = _getfield(q, "category", "")
    if category != "human":
        return 0.0

    target = _getfield(q, "target", "")
    if not target:
        return 0.0

    depths = {}
    if context is not None:
        depths = getattr(context, "relationship_depths", None) or {}
        if callable(getattr(context, "get", None)):
            depths = context.get("relationship_depths", depths)

    msg_count = depths.get(target, 0)
    # Scale: 0 messages = 0.0, 10+ messages = 2.0
    return min(2.0, msg_count / 5.0)


def _self_urgency_boost(q, context) -> float:
    """Self-category questions get 2.0 boost if task failure rate > 20%.

    Uses context.task_failure_rate -- a float 0.0-1.0.
    """
    category = _getfield(q, "category", "")
    if category != "self":
        return 0.0

    failure_rate = 0.0
    if context is not None:
        failure_rate = getattr(context, "task_failure_rate", 0.0)
        if callable(getattr(context, "get", None)):
            failure_rate = context.get("task_failure_rate", failure_rate)

    if failure_rate > 0.20:
        return 2.0
    return 0.0


def _cost_penalty(q) -> float:
    """Penalize expensive research methods."""
    method = _getfield(q, "research_method", "")
    return COST_PENALTIES.get(method, 0.0)


def score_question(q, context) -> float:
    """Composite scoring formula.

    base = q.priority_hint (1-10)
    + recency boost for contextual (up to 3.0, decays over 24h)
    + novelty boost (penalize recently-asked categories, up to 2.0)
    + relationship depth for human questions (more messages = higher, up to 2.0)
    + self-urgency if task failure rate > 20% (2.0 for self category)
    - cost penalty: web_search -1.0, agent_delegation -1.5
    """
    base = float(_getfield(q, "priority_hint", 5.0))

    recency = _recency_boost(q, context)
    novelty = _novelty_boost(q, context)
    relationship = _relationship_depth_boost(q, context)
    urgency = _self_urgency_boost(q, context)
    cost = _cost_penalty(q)

    total = base + recency + novelty + relationship + urgency + cost

    logger.debug(
        "score_question: base=%.1f recency=%.1f novelty=%.1f "
        "relationship=%.1f urgency=%.1f cost=%.1f => total=%.1f",
        base, recency, novelty, relationship, urgency, cost, total,
    )

    return round(total, 2)


# ---------------------------------------------------------------------------
# Rank & Filter
# ---------------------------------------------------------------------------

def rank_and_filter(candidates: list, context, config: dict = None) -> list:
    """Score, dedup, apply category quotas, return sorted list.

    Steps:
    1. Compute score for each candidate
    2. Filter out duplicates (via is_duplicate_question)
    3. Apply category quotas (from context.category_quotas)
    4. Sort by score descending
    5. Limit to config.limits.maxQuestionsPerSweep (default 5)

    Returns list of (candidate, score) tuples.
    """
    if config is None:
        try:
            config = load_config()
        except Exception:
            config = {"limits": {"maxQuestionsPerSweep": 5}}

    max_per_sweep = config.get("limits", {}).get("maxQuestionsPerSweep", 5)

    # Step 1: Score all candidates
    scored = []
    for q in candidates:
        s = score_question(q, context)
        scored.append((q, s))

    # Step 2: Filter duplicates
    deduped = []
    for q, s in scored:
        question_text = _getfield(q, "question_text", "") or _getfield(q, "text", "")
        target = _getfield(q, "target", "")
        try:
            if is_duplicate_question(question_text, target):
                logger.info("Filtered duplicate: %s", question_text[:60])
                continue
        except Exception:
            # Neo4j unavailable -- skip dedup check, keep the question
            pass
        deduped.append((q, s))

    # Step 3: Apply category quotas
    category_quotas = {}
    if context is not None:
        category_quotas = getattr(context, "category_quotas", None) or {}
        if callable(getattr(context, "get", None)):
            category_quotas = context.get("category_quotas", category_quotas)

    category_counts = {}
    quota_filtered = []
    for q, s in deduped:
        category = getattr(q, "category", None) or q.get("category", "world")
        quota = category_quotas.get(category)
        if quota is not None and quota <= 0:
            logger.info("Category quota exhausted for %s, skipping", category)
            continue
        count = category_counts.get(category, 0)
        if quota is not None and count >= quota:
            logger.info("Category quota reached for %s (%d/%d)", category, count, quota)
            continue
        category_counts[category] = count + 1
        quota_filtered.append((q, s))

    # Step 4: Sort by score descending
    quota_filtered.sort(key=lambda x: x[1], reverse=True)

    # Step 5: Limit to maxQuestionsPerSweep
    return quota_filtered[:max_per_sweep]


# ---------------------------------------------------------------------------
# Main: demo with mock candidates
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(message)s")

    # Mock context (dict-based, since CuriosityContext may not exist yet)
    mock_context = {
        "recent_category_counts": {"human": 2, "world": 0, "self": 1, "contextual": 0},
        "relationship_depths": {"danny": 15, "alex": 3, "unknown": 0},
        "task_failure_rate": 0.35,  # > 20% => self-urgency kicks in
        "category_quotas": {"human": 3, "self": 2, "world": 2, "contextual": 3},
    }

    # Mock candidate questions (dict-based)
    now_epoch = time.time()
    candidates = [
        {
            "question_text": "What timezone is Danny in?",
            "category": "human",
            "target": "danny",
            "research_method": "neo4j_lookup",
            "priority_hint": 7,
            "created_at": now_epoch - 3600,  # 1 hour ago
        },
        {
            "question_text": "What are the latest developments in the AI agent space?",
            "category": "world",
            "target": "world",
            "research_method": "web_search",
            "priority_hint": 5,
            "created_at": now_epoch - 7200,  # 2 hours ago
        },
        {
            "question_text": "Why did 3 tasks fail in the last hour?",
            "category": "self",
            "target": "self",
            "research_method": "memory_scan",
            "priority_hint": 8,
            "created_at": now_epoch - 600,  # 10 minutes ago
        },
        {
            "question_text": "Danny just mentioned a conference -- which one?",
            "category": "contextual",
            "target": "danny",
            "research_method": "neo4j_lookup",
            "priority_hint": 6,
            "created_at": now_epoch - 300,  # 5 minutes ago (very fresh)
        },
        {
            "question_text": "What is Alex working on this week?",
            "category": "human",
            "target": "alex",
            "research_method": "agent_delegation",
            "priority_hint": 4,
            "created_at": now_epoch - 86400,  # 24 hours ago
        },
        {
            "question_text": "What is the current weather forecast for NYC?",
            "category": "world",
            "target": "world",
            "research_method": "web_search",
            "priority_hint": 3,
            "created_at": now_epoch - 43200,  # 12 hours ago
        },
    ]

    print("=" * 70)
    print("Curiosity Scorer — Mock Candidate Scoring Demo")
    print("=" * 70)

    print("\n--- Individual Scores ---\n")
    for q in candidates:
        s = score_question(q, mock_context)
        print(f"  [{s:6.2f}]  ({q['category']:10s})  {q['question_text'][:55]}")

    print("\n--- Ranked & Filtered ---\n")
    # Use a config that skips Neo4j dedup (tests would fail without it)
    mock_config = {"limits": {"maxQuestionsPerSweep": 5}}

    # Temporarily patch is_duplicate_question to avoid Neo4j dependency
    import curiosity_dedup
    _orig_is_dup = curiosity_dedup.is_duplicate_question
    curiosity_dedup.is_duplicate_question = lambda *a, **kw: False

    try:
        ranked = rank_and_filter(candidates, mock_context, config=mock_config)
        for i, (q, s) in enumerate(ranked, 1):
            print(f"  #{i}  [{s:6.2f}]  ({q['category']:10s})  {q['question_text'][:55]}")
    finally:
        curiosity_dedup.is_duplicate_question = _orig_is_dup

    print(f"\n  Total candidates: {len(candidates)}")
    print(f"  After rank & filter: {len(ranked)}")
    print("\n  Score differentiation shows contextual recency boost,")
    print("  self-urgency boost (failure rate 35%), novelty for world,")
    print("  and cost penalties for web_search / agent_delegation.")
    print()
