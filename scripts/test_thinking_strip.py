#!/usr/bin/env python3
"""
Test for _strip_internal_thinking function.

Run: python3 test_thinking_strip.py

This test ensures internal reasoning/thinking is not leaked in Signal responses.
"""
from __future__ import annotations

import re
import sys

def _strip_internal_thinking(text: str) -> str:
    """Strip internal thinking/reasoning from model responses."""
    if not text:
        return text

    # 1. Strip explicit thinking tags (various formats)
    thinking_patterns = [
        r"<think[^>]*>.*?</think\s*>",
        r"< Malay>.*?```",
        r"\[THINKING\].*?\[/THINKING\]",
        r"\{thinking\}.*?\{/thinking\}",
    ]
    for pattern in thinking_patterns:
        text = re.sub(pattern, "", text, flags=re.DOTALL | re.IGNORECASE)

    text = text.strip()

    # 2. Detect internal monologue transition patterns
    transition_patterns = [
        r"^.*?(?:Now I can respond|I will now respond|Let me respond|I should respond|Now responding|My response:|Final response:|Response:)[^.]*\.\s*",
        r"^.*?(?:This is an internal task|Internal reasoning|Internal note|Note to self:|Self:)[.,].*?\.\s*",
    ]

    for pattern in transition_patterns:
        match = re.match(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            remaining = text[match.end():].strip()
            if remaining and len(remaining) < len(text) * 0.7:
                text = remaining
                break

    text = text.strip()
    text = re.sub(r"^(?:Good|OK|Alright|Right|Sure),?\s+(?:the|this|I|so|now)\s+[^.]+\.\s*", "", text, flags=re.IGNORECASE)
    return text.strip()


def test_strip_internal_thinking():
    """Test all cases for internal thinking stripping."""
    tests = [
        # (input, expected_output, description)
        (
            "Good, the script executed successfully. This is an internal task, so I dont need to relay the results to Danny. Now I can respond to Dannys greeting.Hello. Good to hear from you.",
            "Hello. Good to hear from you.",
            "Original reported bug: glm-5 style internal reasoning"
        ),
        (
            "The user asked about the weather. Now I can respond.Sunny today!",
            "Sunny today!",
            "Simple transition phrase"
        ),
        (
            "This is an internal task, I should not share this. The actual response is here.",
            "The actual response is here.",
            "Internal task with comma (not period)"
        ),
        (
            "Hello! How can I help you today?",
            "Hello! How can I help you today?",
            "Normal response - should pass through unchanged"
        ),
        (
            "",
            "",
            "Empty string"
        ),
        (
            "Now I can respond without a period after transition",
            "Now I can respond without a period after transition",
            "No period after transition - should not match"
        ),
        (
            "[THINKING]Let me think about this...[/THINKING]Here is my answer.",
            "Here is my answer.",
            "Bracketed thinking tag"
        ),
    ]

    failed = 0
    for i, (input_text, expected, description) in enumerate(tests, 1):
        result = _strip_internal_thinking(input_text)
        if result == expected:
            print(f"PASS Test {i}: {description}")
        else:
            print(f"FAIL Test {i}: {description}")
            print(f"  Input: {input_text[:60]}...")
            print(f"  Expected: {expected}")
            print(f"  Got: {result}")
            failed += 1

    print(f"\n{'='*60}")
    if failed == 0:
        print("ALL TESTS PASSED")
        return 0
    else:
        print(f"FAILED: {failed}/{len(tests)} tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(test_strip_internal_thinking())
