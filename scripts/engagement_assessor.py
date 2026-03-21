#!/usr/bin/env python3
"""
Engagement Assessor — LLM-based engagement decision with safety overrides.

Pipeline: Safety overrides → Context assembly → LLM assessment → Decision

Model router: DeepSeek Chat (primary) → Ollama qwen3.5:9b (fallback) → heuristic

Usage:
    from engagement_assessor import assess_engagement
    decision = assess_engagement(human_id, message_text)
"""

import os
import sys
import json
import time
import logging
from typing import Optional, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engagement_safety import check_safety_overrides
from context_assembler import assemble_context
from context_formatter import format_context
from consent_decorator import check_consent
from pii_scrubber import PIIScrubber

logger = logging.getLogger(__name__)

# Load OpenRouter key
_OPENROUTER_KEY = None

def _get_openrouter_key():
    global _OPENROUTER_KEY
    if _OPENROUTER_KEY:
        return _OPENROUTER_KEY
    env_file = os.path.expanduser("~/.openclaw/credentials/openrouter.env")
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith("OPENROUTER_API_KEY="):
                    _OPENROUTER_KEY = line.split("=", 1)[1].strip()
                    return _OPENROUTER_KEY
    _OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY")
    return _OPENROUTER_KEY


ASSESSMENT_PROMPT = """You are Kublai's engagement intelligence module. Given context about a human and their latest message, decide whether and how to respond.

## Human Profile & Context
{context}

## Current Message
Direction: {direction}
Content: "{message}"

## Decision Framework
Consider:
1. Is this message directed at Kublai or just ambient noise?
2. Does the human expect a response based on their communication style?
3. What's the appropriate depth and timing?
4. Would responding add value or be annoying?

## Calibration Examples
- "thanks!" after Kublai's response → silent (acknowledgment, no response needed)
- "k" from a known terse communicator → respond/normal/brief (they're confirming, might need follow-up)
- "Can you help me with X?" → respond/normal/full (direct request)
- "lol" → silent (no information content)
- "Hey what do you think about X?" → respond/normal/full (asking for opinion)
- "Just FYI, I updated the config" → respond/brief/acknowledgment (inform, acknowledge)
- "Good morning!" → respond/normal/standard (greeting, reciprocate)
- "..." → silent (thinking/waiting)

Return a JSON object:
{{
    "decision": "respond|silent|defer",
    "confidence": 0.0-1.0,
    "timing": "instant|normal|delayed|null",
    "depth": "full|standard|brief|acknowledgment|null",
    "reasoning": "brief explanation",
    "human_state": "engaged|distracted|frustrated|neutral|positive",
    "context_needed": ["list of context types that would improve response"]
}}

Return ONLY the JSON object."""


def assess_engagement(
    human_id: str,
    message_text: str,
    direction: str = "inbound",
    has_media: bool = False,
    message_count: int = -1,
    last_message_days: Optional[float] = None,
    is_group: bool = False,
) -> Dict[str, Any]:
    """Assess whether and how to engage with a message.

    Args:
        human_id: UUID of the Human
        message_text: Message content
        direction: inbound/outbound
        has_media: Whether message has an attachment
        message_count: Total messages from this human (-1 to auto-detect)
        last_message_days: Days since last message (None to auto-detect)
        is_group: Whether message is from a group chat

    Returns:
        Engagement decision dict
    """
    t0 = time.monotonic()

    # Group messages use fast heuristic — skip LLM assessment
    if is_group:
        decision = _heuristic_assess_group(message_text, direction)
        decision["source"] = "group_heuristic"
        decision["ms"] = round((time.monotonic() - t0) * 1000)
        return decision

    # Auto-detect stats if not provided
    if message_count < 0 or last_message_days is None:
        from conversation_ingester import ConversationIngester
        ingester = ConversationIngester()
        stats = ingester.get_human_message_stats(human_id)
        ingester.close()
        if message_count < 0:
            message_count = stats.get("message_count", 0)
        if last_message_days is None:
            last_message_days = stats.get("last_message_days")

    # Phase 1: Safety overrides (deterministic, <1ms)
    override = check_safety_overrides(
        message_text=message_text,
        human_id=human_id,
        last_message_days=last_message_days,
        message_count=message_count,
        has_media=has_media,
    )
    if override:
        override["source"] = "safety_override"
        override["ms"] = round((time.monotonic() - t0) * 1000)
        return override

    # Phase 2: Check consent for external LLM processing
    use_llm = check_consent(human_id, "external_llm_processing")

    # Phase 3: LLM assessment (if consent granted)
    if use_llm:
        # Assemble context
        context = assemble_context(human_id, message_text)
        formatted = format_context(context)

        # Build context string
        context_str = "\n\n".join(
            f"### {section}\n{text}"
            for section, text in formatted.items()
            if text and not section.startswith("_")
        )

        # Scrub PII before external LLM calls (message + context)
        _scrubber = PIIScrubber()
        context_str, _ = _scrubber.scrub(context_str)
        message_scrubbed, _ = _scrubber.scrub(message_text)

        # Try LLM assessment
        decision = _llm_assess(context_str, message_scrubbed, direction)
        if decision:
            decision["source"] = "llm"
            decision["ms"] = round((time.monotonic() - t0) * 1000)
            return decision

    # Phase 4: Heuristic fallback
    decision = _heuristic_assess(message_text, direction, message_count)
    decision["source"] = "heuristic"
    decision["ms"] = round((time.monotonic() - t0) * 1000)
    return decision


def _llm_assess(
    context: str, message: str, direction: str
) -> Optional[Dict[str, Any]]:
    """Call LLM for engagement assessment. Tries DeepSeek then Ollama."""
    # Try DeepSeek via OpenRouter
    result = _try_openrouter(context, message, direction)
    if result:
        return result

    # Fallback: Ollama qwen3.5:9b
    result = _try_ollama(context, message, direction)
    if result:
        return result

    return None


def _try_openrouter(context: str, message: str, direction: str) -> Optional[Dict[str, Any]]:
    """Try OpenRouter DeepSeek Chat."""
    api_key = _get_openrouter_key()
    if not api_key:
        return None

    prompt = ASSESSMENT_PROMPT.format(
        context=context, message=message, direction=direction
    )

    try:
        import requests
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek/deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 500,
            },
            timeout=15,
        )
        if resp.status_code == 200:
            text = resp.json()["choices"][0]["message"]["content"]
            text = text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            return json.loads(text.strip())
    except Exception as e:
        logger.warning(f"OpenRouter assessment failed: {e}")
    return None


def _try_ollama(context: str, message: str, direction: str) -> Optional[Dict[str, Any]]:
    """Try Ollama qwen3.5:9b as fallback."""
    prompt = ASSESSMENT_PROMPT.format(
        context=context, message=message, direction=direction
    )

    try:
        import requests
        resp = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": "qwen3.5:9b",
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": 0.1},
            },
            timeout=30,
        )
        if resp.status_code == 200:
            text = resp.json().get("message", {}).get("content", "")
            text = text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            return json.loads(text.strip())
    except Exception as e:
        logger.debug(f"Ollama assessment failed: {e}")
    return None


def _heuristic_assess_group(
    message: str, direction: str
) -> Dict[str, Any]:
    """Fast heuristic for group messages — default silent unless addressed."""
    text = message.strip().lower()

    # Skip outbound
    if direction == "outbound":
        return {"decision": "silent", "confidence": 0.9, "timing": None, "depth": None,
                "reasoning": "Outbound message — no self-response"}

    # Respond if Kublai is addressed by name
    if "kublai" in text:
        return {"decision": "respond", "confidence": 0.9, "timing": "normal", "depth": "standard",
                "reasoning": "Addressed by name in group"}

    # Respond to direct questions (with some length to filter noise)
    if "?" in message and len(text) > 10:
        return {"decision": "respond", "confidence": 0.7, "timing": "normal", "depth": "brief",
                "reasoning": "Question in group — brief response"}

    # Default: stay silent in groups
    return {"decision": "silent", "confidence": 0.8, "timing": None, "depth": None,
            "reasoning": "Group message — not addressed, staying silent"}


def _heuristic_assess(
    message: str, direction: str, message_count: int
) -> Dict[str, Any]:
    """Rule-based heuristic fallback when LLM is unavailable."""
    text = message.strip().lower()

    # Skip outbound messages
    if direction == "outbound":
        return {"decision": "silent", "confidence": 0.9, "timing": None, "depth": None,
                "reasoning": "Outbound message — no self-response"}

    # Very short messages (likely acknowledgments)
    if len(text) <= 3 and text in ("k", "ok", "ty", "thx", "lol", "...", "ya", "yep"):
        return {"decision": "silent", "confidence": 0.7, "timing": None, "depth": None,
                "reasoning": "Short acknowledgment — no response needed"}

    # Questions get full responses
    if "?" in message:
        return {"decision": "respond", "confidence": 0.85, "timing": "normal", "depth": "full",
                "reasoning": "Question detected — provide answer"}

    # Greetings
    greetings = {"hello", "hi", "hey", "good morning", "good afternoon", "good evening", "morning"}
    if any(text.startswith(g) for g in greetings):
        return {"decision": "respond", "confidence": 0.8, "timing": "normal", "depth": "standard",
                "reasoning": "Greeting — reciprocate"}

    # Thanks/acknowledgments after Kublai response
    thanks = {"thanks", "thank you", "thx", "ty", "cheers", "appreciated"}
    if any(t in text for t in thanks):
        return {"decision": "silent", "confidence": 0.7, "timing": None, "depth": None,
                "reasoning": "Thanks — no further response needed"}

    # Default: respond normally
    return {"decision": "respond", "confidence": 0.6, "timing": "normal", "depth": "standard",
            "reasoning": "Default — engage with message"}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("human_id")
    parser.add_argument("message")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    decision = assess_engagement(args.human_id, args.message)
    print(json.dumps(decision, indent=2))
