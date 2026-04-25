#!/usr/bin/env python3
"""
Curiosity Generator — Builds the curiosity prompt for the Claude Code agent.

Since the curiosity sweep runs as an agentTurn (Claude Code IS the LLM),
this module assembles context and provides the prompt + JSON parser.
The agent generates questions natively — no external LLM API needed.

Usage:
    from curiosity_generator import build_curiosity_prompt, parse_questions, CandidateQuestion

    # In the agent session:
    prompt = build_curiosity_prompt(context)
    # Agent generates JSON response
    candidates = parse_questions(json_text)

    # CLI: prints the prompt for the agent to use
    python3 curiosity_generator.py
"""
from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass, asdict
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from curiosity_context import CuriosityContext, summarize_for_prompt

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class CandidateQuestion:
    text: str
    category: str        # human|self|world|contextual
    target: str          # human_id, "self", or "world"
    research_method: str  # ask_human|web_search|neo4j_query|agent_delegation
    priority_hint: float  # 1-10
    reasoning: str
    related_to: str = ""  # optional topic/entity name


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

CURIOSITY_GENERATION_PROMPT = """You are Kublai, squad lead of the Kurultai multi-agent system.
Generate curiosity questions -- things you genuinely want to know.

{context_summary}

Generate 3-5 questions. Return JSON:
{{
  "questions": [
    {{
      "text": "the natural-language question",
      "category": "human|self|world|contextual",
      "target": "human_id or 'self' or 'world'",
      "research_method": "ask_human|web_search|neo4j_query|agent_delegation",
      "priority_hint": 1-10,
      "reasoning": "why this question matters right now",
      "related_to": "optional: concept/entity name"
    }}
  ]
}}

Rules:
- Never ask something in "Recently Asked"
- At least 1 question must be self-reflective (category: self)
- Contextual questions must reference a specific recent conversation
- Human questions require a valid human ID from the Humans list
- Respect quotas: if a category has 0 remaining, skip it
- For ask_human: only ask things the human uniquely knows (preferences, opinions, personal info)
- For web_search: factual lookups, news, weather
- For neo4j_query: performance metrics, patterns, relationships
- For agent_delegation: deep research needing sustained analysis
- Return ONLY valid JSON, no markdown fencing"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_curiosity_prompt(context) -> str:
    """Build the full prompt for the agent to generate questions.

    Args:
        context: A CuriosityContext (from assemble_context())

    Returns:
        The formatted prompt string with context injected.
    """
    context_summary = summarize_for_prompt(context)
    return CURIOSITY_GENERATION_PROMPT.format(context_summary=context_summary)


def parse_questions(json_text: str) -> List[CandidateQuestion]:
    """Parse JSON output from the agent into CandidateQuestion objects.

    Handles markdown fencing (```json ... ```) if present.

    Args:
        json_text: Raw JSON string (or markdown-fenced JSON)

    Returns:
        List of CandidateQuestion objects (may be empty on parse failure)
    """
    text = json_text.strip()

    # Strip markdown fencing
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning("Failed to parse questions JSON: %s", e)
        return []

    questions = parsed.get("questions", [])

    return [
        CandidateQuestion(
            text=q["text"],
            category=q.get("category", "world"),
            target=q.get("target", "world"),
            research_method=q.get("research_method", "web_search"),
            priority_hint=float(q.get("priority_hint", 5)),
            reasoning=q.get("reasoning", ""),
            related_to=q.get("related_to", ""),
        )
        for q in questions
        if q.get("text")
    ]


def generate_questions(context, config: Optional[dict] = None) -> List[CandidateQuestion]:
    """Assemble context and print the prompt for the agent to act on.

    When running inside a Claude Code agentTurn, the agent reads this
    output and generates questions natively. The questions are then
    passed back via parse_questions().

    When running standalone (CLI), this just prints the prompt.

    Returns:
        Empty list — the agent generates questions asynchronously.
        Use parse_questions() to parse the agent's response.
    """
    prompt = build_curiosity_prompt(context)
    # Print the prompt so the agent can read and act on it
    print("\n--- CURIOSITY PROMPT FOR AGENT ---")
    print(prompt)
    print("--- END PROMPT ---\n")
    return []


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    print("=== Curiosity Generator ===\n")

    from curiosity_context import assemble_context
    ctx = assemble_context()

    prompt = build_curiosity_prompt(ctx)
    print("Prompt for the agent:\n")
    print(prompt)

    print("\n\nTo test parsing, pass JSON to parse_questions():")
    test_json = json.dumps({
        "questions": [
            {
                "text": "How are task completion rates trending this week?",
                "category": "self",
                "target": "self",
                "research_method": "neo4j_query",
                "priority_hint": 7,
                "reasoning": "Self-reflection on operational efficiency",
            }
        ]
    })
    parsed = parse_questions(test_json)
    for q in parsed:
        print(f"  [{q.category}] {q.text} (priority={q.priority_hint})")

    print("\n=== Done ===")
