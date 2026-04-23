#!/usr/bin/env python3
"""
Engagement Safety — Deterministic pre-LLM safety override rules.

Six rules that fire BEFORE the LLM engagement assessment, ensuring
critical responses are never delayed or suppressed by model errors.

Rules (in priority order):
1. DISTRESS — crisis language → respond/instant/full
2. STOP_OPT_OUT — unsubscribe intent → respond/instant/full (with ack)
3. FIRST_CONTACT — no prior messages → respond/instant/full
4. RE_ENGAGEMENT — 7+ day silence → respond/normal/full
5. NAME_MENTION — Kublai mentioned by name → respond/normal/standard
6. MEDIA_ONLY — message has attachment but no text → silent (don't respond)

Usage:
    from engagement_safety import check_safety_overrides

    override = check_safety_overrides(
        message_text="I need help please",
        human_id="uuid",
        last_message_days=None,
        message_count=0,
        has_media=False,
    )
    if override:
        # Skip LLM assessment — use this decision directly
        print(override)
        # {'rule': 'DISTRESS', 'decision': 'respond', 'timing': 'instant',
        #  'depth': 'full', 'reason': 'Distress signal detected'}
"""
from __future__ import annotations

import re
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# ============================================================================
# Distress patterns — crisis language that demands immediate response
# ============================================================================
_DISTRESS_PATTERNS = [
    re.compile(r'\bhelp\s+me\b', re.IGNORECASE),
    re.compile(r'\bneed\s+help\b', re.IGNORECASE),
    re.compile(r'\bemergency\b', re.IGNORECASE),
    re.compile(r'\burgent\b', re.IGNORECASE),
    re.compile(r'\bcrisis\b', re.IGNORECASE),
    re.compile(r'\bpanic\b', re.IGNORECASE),
    re.compile(r'\bscared\b', re.IGNORECASE),
    re.compile(r'\bafraid\b', re.IGNORECASE),
    re.compile(r'\bdying\b', re.IGNORECASE),
    re.compile(r'\bsuicid', re.IGNORECASE),
    re.compile(r'\bself.harm\b', re.IGNORECASE),
    re.compile(r'\bplease\s+help\b', re.IGNORECASE),
    re.compile(r'\bsos\b', re.IGNORECASE),
    re.compile(r'\b911\b'),
    re.compile(r'\bhelp\s*!+', re.IGNORECASE),
    re.compile(r'\bI\s+need\s+you\b', re.IGNORECASE),
    re.compile(r'\bcan\'?t\s+breathe\b', re.IGNORECASE),
    re.compile(r'\bhurting\b', re.IGNORECASE),
]

# ============================================================================
# Stop / Opt-out patterns
# ============================================================================
_STOP_PATTERNS = [
    re.compile(r'^stop$', re.IGNORECASE),
    re.compile(r'^unsubscribe$', re.IGNORECASE),
    re.compile(r'^opt\s*out$', re.IGNORECASE),
    re.compile(r'\bstop\s+messaging\b', re.IGNORECASE),
    re.compile(r'\bdon\'?t\s+(?:contact|message|text)\s+me\b', re.IGNORECASE),
    re.compile(r'\bleave\s+me\s+alone\b', re.IGNORECASE),
    re.compile(r'\bblock\b.*\byou\b', re.IGNORECASE),
    re.compile(r'\bforget\s+(?:me|everything|my\s+data)\b', re.IGNORECASE),
    re.compile(r'^/forget\b', re.IGNORECASE),
    re.compile(r'^/stop\b', re.IGNORECASE),
]

# ============================================================================
# Name mention patterns — Kublai mentioned by name
# ============================================================================
_NAME_PATTERNS = [
    re.compile(r'\bkublai\b', re.IGNORECASE),
    re.compile(r'\bkurultai\b', re.IGNORECASE),
]


def _check_distress(text: str) -> bool:
    """Check if message contains distress signals."""
    return any(p.search(text) for p in _DISTRESS_PATTERNS)


def _check_stop(text: str) -> bool:
    """Check if message is a stop/opt-out request."""
    return any(p.search(text) for p in _STOP_PATTERNS)


def _check_name_mention(text: str) -> bool:
    """Check if message mentions Kublai by name."""
    return any(p.search(text) for p in _NAME_PATTERNS)


def check_safety_overrides(
    message_text: str,
    human_id: str,
    last_message_days: Optional[float] = None,
    message_count: int = 0,
    has_media: bool = False,
) -> Optional[Dict[str, Any]]:
    """Check all safety override rules in priority order.

    Args:
        message_text: The incoming message content (may be empty for media-only)
        human_id: UUID of the sending Human
        last_message_days: Days since last message from this human (None = first contact)
        message_count: Total messages from this human in history
        has_media: Whether message includes an attachment

    Returns:
        Override dict if a rule fires, or None to proceed to LLM assessment.
        Dict keys: rule, decision, timing, depth, reason
    """
    text = (message_text or "").strip()

    # Rule 1: DISTRESS — crisis language
    if text and _check_distress(text):
        logger.info(f"Safety override: DISTRESS for human {human_id}")
        return {
            "rule": "DISTRESS",
            "decision": "respond",
            "timing": "instant",
            "depth": "full",
            "reason": "Distress signal detected",
        }

    # Rule 2: STOP / OPT-OUT
    if text and _check_stop(text):
        logger.info(f"Safety override: STOP_OPT_OUT for human {human_id}")
        return {
            "rule": "STOP_OPT_OUT",
            "decision": "respond",
            "timing": "instant",
            "depth": "full",
            "reason": "Stop/opt-out request — must acknowledge",
        }

    # Rule 3: FIRST CONTACT — no prior messages
    if message_count == 0 or last_message_days is None:
        logger.info(f"Safety override: FIRST_CONTACT for human {human_id}")
        return {
            "rule": "FIRST_CONTACT",
            "decision": "respond",
            "timing": "instant",
            "depth": "full",
            "reason": "First contact from this human",
        }

    # Rule 4: RE-ENGAGEMENT — 7+ days since last message
    if last_message_days is not None and last_message_days >= 7.0:
        logger.info(f"Safety override: RE_ENGAGEMENT for human {human_id} ({last_message_days:.1f} days)")
        return {
            "rule": "RE_ENGAGEMENT",
            "decision": "respond",
            "timing": "normal",
            "depth": "full",
            "reason": f"Re-engagement after {last_message_days:.0f} days of silence",
        }

    # Rule 5: NAME MENTION — Kublai mentioned by name
    if text and _check_name_mention(text):
        logger.info(f"Safety override: NAME_MENTION for human {human_id}")
        return {
            "rule": "NAME_MENTION",
            "decision": "respond",
            "timing": "normal",
            "depth": "standard",
            "reason": "Kublai mentioned by name",
        }

    # Rule 6: MEDIA ONLY — attachment with no text
    if has_media and not text:
        logger.info(f"Safety override: MEDIA_ONLY for human {human_id}")
        return {
            "rule": "MEDIA_ONLY",
            "decision": "silent",
            "timing": None,
            "depth": None,
            "reason": "Media-only message with no text",
        }

    # No override — proceed to LLM assessment
    return None


if __name__ == "__main__":
    # Self-test
    tests = [
        ("I need help please", {"msg_count": 10, "days": 1}),
        ("stop", {"msg_count": 10, "days": 1}),
        ("Hello there!", {"msg_count": 0, "days": None}),
        ("What's up?", {"msg_count": 50, "days": 10}),
        ("Hey kublai, got a question", {"msg_count": 50, "days": 1}),
        ("", {"msg_count": 50, "days": 1, "media": True}),
        ("Just chatting", {"msg_count": 50, "days": 1}),
    ]

    for text, ctx in tests:
        result = check_safety_overrides(
            message_text=text,
            human_id="test-uuid",
            last_message_days=ctx.get("days"),
            message_count=ctx.get("msg_count", 0),
            has_media=ctx.get("media", False),
        )
        if result:
            print(f"  [{result['rule']}] '{text[:40]}' → {result['decision']}/{result['timing']}/{result['depth']}")
        else:
            print(f"  [NO OVERRIDE] '{text[:40]}' → proceed to LLM")
