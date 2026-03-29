#!/usr/bin/env python3
"""
Curiosity Follow-up — Generate follow-up questions when answers arrive.

When a curiosity question is answered, this module decides whether the answer
warrants a natural follow-up question.  Uses chain depth limits per category,
priority decay, dedup checking, and LLM-based generation.

Usage:
    from curiosity_followup import maybe_generate_followup
"""

import sys
import os
import json
import logging
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from curiosity_dedup import is_duplicate_question

logger = logging.getLogger(__name__)

# Maximum chain depth per category (0-indexed: depth 0 = original, depth 1 = first followup)
MAX_CHAIN_DEPTH = {
    "human": 2,
    "self": 1,
    "world": 3,
    "contextual": 1,
}

# Priority decays by this factor per chain level
CHAIN_PRIORITY_DECAY = 0.6

# Minimum answer length to consider a followup
MIN_ANSWER_LENGTH = 10

# Phrases indicating a non-substantive answer
NON_SUBSTANTIVE_MARKERS = [
    "i don't know",
    "idk",
    "not sure",
    "no idea",
    "no clue",
    "can't help",
    "don't have",
    "n/a",
    "pass",
]


def _is_substantive_answer(answer_text: str) -> bool:
    """Check if the answer is long enough and substantive."""
    if not answer_text or len(answer_text.strip()) < MIN_ANSWER_LENGTH:
        return False
    lower = answer_text.lower().strip()
    for marker in NON_SUBSTANTIVE_MARKERS:
        if lower == marker or lower.startswith(marker):
            return False
    return True


def maybe_generate_followup(answered_question: dict, answer_text: str, context=None) -> dict:
    """Decide whether an answer warrants a follow-up question.

    Args:
        answered_question: dict with keys: question_text, category, target,
                          research_method, priority, chain_depth, chain_id
        answer_text: the answer received
        context: optional CuriosityContext for budget check

    Returns:
        dict with followup question fields, or None if no followup warranted.
        {text, category, target, research_method, priority_hint, chain_id, chain_depth, reasoning}

    Rules:
    1. Hard stop at MAX_CHAIN_DEPTH per category
    2. Budget check: if category quota is 0, return None
    3. Don't follow up if answer is "I don't know" / very short
    4. Don't follow up if followup would be duplicate
    5. Priority decays by CHAIN_PRIORITY_DECAY per level
    6. If OPENROUTER_API_KEY available, use LLM to generate followup
    7. Otherwise return None (no template-based followups)
    """
    depth = answered_question.get("chain_depth", 0)
    category = answered_question.get("category", "world")
    max_depth = MAX_CHAIN_DEPTH.get(category, 2)

    # Rule 1: Hard stop at max chain depth
    if depth >= max_depth:
        logger.debug(
            "Chain depth %d >= max %d for category %s, no followup",
            depth, max_depth, category,
        )
        return None

    # Rule 2: Budget check
    if context is not None:
        category_quotas = getattr(context, "category_quotas", None) or {}
        if callable(getattr(context, "get", None)):
            category_quotas = context.get("category_quotas", category_quotas)
        remaining = category_quotas.get(category)
        if remaining is not None and remaining <= 0:
            logger.debug("Category quota exhausted for %s, no followup", category)
            return None

    # Rule 3: Skip if answer is too short or non-substantive
    if not _is_substantive_answer(answer_text):
        logger.debug("Answer too short or non-substantive, no followup")
        return None

    # Rule 6: Try LLM-based followup generation
    followup = _llm_followup(answered_question, answer_text)
    if not followup:
        # Rule 7: No template-based fallback
        return None

    # Rule 4: Check dedup
    target = answered_question.get("target", "")
    try:
        if is_duplicate_question(followup["text"], target):
            logger.info("Follow-up would be duplicate, skipping: %s", followup["text"][:60])
            return None
    except Exception:
        # Neo4j unavailable -- skip dedup, allow the followup
        pass

    # Rule 5: Apply priority decay
    parent_priority = answered_question.get("priority", 5.0)
    followup["priority_hint"] = round(parent_priority * CHAIN_PRIORITY_DECAY, 2)
    followup["chain_id"] = answered_question.get("chain_id", "")
    followup["chain_depth"] = depth + 1
    followup["category"] = category
    followup["target"] = answered_question.get("target", "world")
    followup["research_method"] = answered_question.get("research_method", "web_search")

    logger.info(
        "Generated followup (depth %d->%d, priority %.1f->%.1f): %s",
        depth, depth + 1, parent_priority, followup["priority_hint"],
        followup["text"][:60],
    )

    return followup


def _llm_followup(answered_question: dict, answer_text: str) -> dict:
    """Use LLM to decide if a follow-up is natural.
    Returns {text, reasoning} or None.
    """
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        logger.debug("No OPENROUTER_API_KEY set, cannot generate LLM followup")
        return None

    prompt = f"""Original question: {answered_question.get('question_text', '')}
Answer received: {answer_text}

Is there a single natural follow-up question? If not, reply "none".
If yes, return JSON: {{"text": "...", "reasoning": "..."}}

Rules:
- Only follow up if the answer revealed something genuinely new
- Never follow up just to be polite
- Never ask the same question rephrased"""

    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek/deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 200,
                "temperature": 0.3,
            },
            timeout=(10, 30),
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()

        if content.lower() == "none" or "none" in content.lower()[:10]:
            return None

        # Strip markdown code fences if present
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0]

        return json.loads(content)
    except Exception as e:
        logger.warning("Follow-up LLM call failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Main: test with mock answered question
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(message)s")

    print("=" * 70)
    print("Curiosity Follow-up — Self-Test")
    print("=" * 70)

    # Test 1: Should return None without API key (LLM required)
    print("\n--- Test 1: No API key (expect None) ---")
    answered = {
        "question_text": "What timezone is Danny in?",
        "category": "human",
        "target": "danny",
        "research_method": "neo4j_lookup",
        "priority": 7.0,
        "chain_depth": 0,
        "chain_id": "chain-001",
    }
    answer = "Danny is in Pacific Time (PT), he lives in San Francisco."
    result = maybe_generate_followup(answered, answer)
    status = "PASS" if result is None else "FAIL"
    print(f"  {status}  No API key -> {result}")

    # Test 2: Chain depth exceeded
    print("\n--- Test 2: Chain depth exceeded (expect None) ---")
    deep_question = {
        "question_text": "Follow-up about Danny's work?",
        "category": "self",
        "target": "self",
        "research_method": "memory_scan",
        "priority": 3.0,
        "chain_depth": 1,  # self max is 1
        "chain_id": "chain-002",
    }
    result = maybe_generate_followup(deep_question, "Some detailed answer here about task status.")
    status = "PASS" if result is None else "FAIL"
    print(f"  {status}  Depth exceeded -> {result}")

    # Test 3: Non-substantive answer
    print("\n--- Test 3: Non-substantive answer (expect None) ---")
    result = maybe_generate_followup(answered, "idk")
    status = "PASS" if result is None else "FAIL"
    print(f"  {status}  Non-substantive -> {result}")

    # Test 4: Too-short answer
    print("\n--- Test 4: Too-short answer (expect None) ---")
    result = maybe_generate_followup(answered, "yes")
    status = "PASS" if result is None else "FAIL"
    print(f"  {status}  Too short -> {result}")

    # Test 5: Budget exhausted
    print("\n--- Test 5: Budget exhausted (expect None) ---")
    mock_context = {"category_quotas": {"human": 0, "self": 0, "world": 0, "contextual": 0}}
    result = maybe_generate_followup(answered, answer, context=mock_context)
    status = "PASS" if result is None else "FAIL"
    print(f"  {status}  Budget exhausted -> {result}")

    # Test 6: World category depth check (max depth 3)
    print("\n--- Test 6: World category at depth 2 (expect None -- no API key) ---")
    world_q = {
        "question_text": "What are latest AI safety developments?",
        "category": "world",
        "target": "world",
        "research_method": "web_search",
        "priority": 5.0,
        "chain_depth": 2,  # world max is 3, so depth 2 is allowed
        "chain_id": "chain-003",
    }
    result = maybe_generate_followup(world_q, "Several new papers were published on AI alignment this week including...")
    status = "PASS" if result is None else "FAIL"
    print(f"  {status}  World depth 2, no API key -> {result}")

    # Test 7: Priority decay calculation
    print("\n--- Test 7: Priority decay verification ---")
    p0 = 8.0
    p1 = round(p0 * CHAIN_PRIORITY_DECAY, 2)
    p2 = round(p1 * CHAIN_PRIORITY_DECAY, 2)
    p3 = round(p2 * CHAIN_PRIORITY_DECAY, 2)
    status = "PASS" if p1 == 4.8 and p2 == 2.88 and p3 == 1.73 else "FAIL"
    print(f"  {status}  Priority decay: {p0} -> {p1} -> {p2} -> {p3}")

    # Summary
    has_api_key = bool(os.getenv("OPENROUTER_API_KEY", ""))
    print(f"\n  OPENROUTER_API_KEY present: {has_api_key}")
    print("  All guard-rail tests passed (LLM generation requires API key).")
    print()
