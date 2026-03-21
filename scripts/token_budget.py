#!/usr/bin/env python3
"""
Token Budget Manager — Elastic token allocation across context sections.

Implements the 7-slot budget from the design doc:
- Identity preamble: 400 tokens (fixed)
- Social context: 200 tokens (fixed)
- Topic map: 300 tokens (fixed)
- Narrative thread: 300 tokens (fixed)
- Active items: 200 tokens (fixed)
- Current thread: 1200 tokens (elastic, min 800)
- Semantic matches: 1400 tokens (elastic, fills remainder)

Usage:
    from token_budget import TokenBudget
    budget = TokenBudget(4000)
    budget.allocate("identity", text, max_tokens=400)
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Approximate: 1 token ≈ 4 characters
CHARS_PER_TOKEN = 4

# Budget slots with fixed/elastic allocation
BUDGET_SLOTS = {
    "identity_preamble": {"fixed": 400, "elastic": False, "min": 400},
    "social_context": {"fixed": 200, "elastic": False, "min": 200},
    "topic_map": {"fixed": 300, "elastic": False, "min": 300},
    "narrative": {"fixed": 300, "elastic": False, "min": 300},
    "active_items": {"fixed": 200, "elastic": False, "min": 200},
    "current_thread": {"fixed": 1200, "elastic": True, "min": 800},
    "semantic_matches": {"fixed": 1400, "elastic": True, "min": 0},
}


class TokenBudget:
    """Manages token allocation across context sections."""

    def __init__(self, total_tokens: int = 4000):
        self.total = total_tokens
        self.allocated: Dict[str, int] = {}
        self.content: Dict[str, str] = {}

    @property
    def remaining(self) -> int:
        return self.total - sum(self.allocated.values())

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count from text."""
        return max(1, len(text) // CHARS_PER_TOKEN)

    def truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        """Truncate text to fit within token budget."""
        max_chars = max_tokens * CHARS_PER_TOKEN
        if len(text) <= max_chars:
            return text
        # Truncate at word boundary
        truncated = text[:max_chars]
        last_space = truncated.rfind(" ")
        if last_space > max_chars * 0.8:
            truncated = truncated[:last_space]
        return truncated + "..."

    def allocate(self, slot: str, text: str, max_tokens: Optional[int] = None) -> str:
        """Allocate tokens for a context section.

        Args:
            slot: Budget slot name
            text: Content to allocate
            max_tokens: Override max tokens for this slot

        Returns:
            Potentially truncated text that fits within budget
        """
        if max_tokens is None:
            slot_config = BUDGET_SLOTS.get(slot, {"fixed": 200})
            max_tokens = slot_config.get("fixed", 200)

        # Don't exceed remaining budget
        available = min(max_tokens, self.remaining)
        if available <= 0:
            return ""

        truncated = self.truncate_to_tokens(text, available)
        actual_tokens = self.estimate_tokens(truncated)
        self.allocated[slot] = actual_tokens
        self.content[slot] = truncated
        return truncated

    def allocate_elastic(self, slot: str, text: str) -> str:
        """Allocate elastic tokens (fills remaining budget)."""
        available = self.remaining
        slot_config = BUDGET_SLOTS.get(slot, {"min": 0})
        min_tokens = slot_config.get("min", 0)

        if available < min_tokens:
            return ""

        return self.allocate(slot, text, max_tokens=available)

    def get_report(self) -> Dict[str, Any]:
        """Get allocation report."""
        return {
            "total": self.total,
            "allocated": sum(self.allocated.values()),
            "remaining": self.remaining,
            "slots": {
                slot: {"tokens": tokens, "chars": len(self.content.get(slot, ""))}
                for slot, tokens in self.allocated.items()
            },
        }
