#!/usr/bin/env python3
"""
Group Context Bridge — Safe topic bridging and shareability classification.

Enables enriched group responses by identifying topics discussed in BOTH
DM and group contexts (safe for group enrichment), and classifying message
shareability using fast keyword heuristics (no LLM).

Usage:
    from group_context_bridge import (
        get_bridgeable_topics, classify_shareability, GroupSafeContextAssembler,
    )
"""
from __future__ import annotations

import re
import logging
from typing import Optional, List, Dict, Any

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from neo4j_task_tracker import neo4j_session
from context_assembler import assemble_context

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shareability classification patterns
# ---------------------------------------------------------------------------

SENSITIVE_PATTERNS = [
    re.compile(r'\b(?:doctor|hospital|diagnosis|medication|prescription|therapy|therapist|surgery|cancer|tumor)\b', re.I),
    re.compile(r'\b(?:salary|debt|loan|mortgage|bankruptcy|credit\s*score|overdraft)\b', re.I),
    re.compile(r'\bowe(?:s|d)?\s+(?:money|\$|\d|a\s+lot|them|him|her|you)\b', re.I),
    re.compile(r'\b(?:lawyer|lawsuit|divorce|custody|restraining\s*order|subpoena)\b', re.I),
    re.compile(r'\b(?:password|api[_\s]?key|secret[_\s]?key|ssh[_\s]?key|token)\b', re.I),
    re.compile(r'\b(?:ssn|social\s*security|bank\s*account|routing\s*number)\b', re.I),
    # Abbreviations and slang
    re.compile(r'\b(?:meds|rx|rehab|psych|shrink|er|icu)\b', re.I),
    re.compile(r'\b(?:broke|in\s*debt|payday|repo|foreclos|evict)\b', re.I),
    re.compile(r'\b(?:arrest|probation|parole|jail|prison|court\s*date)\b', re.I),
]

PRIVATE_PATTERNS = [
    re.compile(r'\b(?:feeling|anxious|stressed|depressed|lonely|overwhelmed|panic)\b', re.I),
    re.compile(r'\b(?:just\s+between\s+us|don\'?t\s+tell|confidential|private|secret)\b', re.I),
    re.compile(r'\b(?:crush|dating|breakup|affair|cheating|jealous)\b', re.I),
    re.compile(r'\b(?:fired|laid\s*off|demoted|performance\s*review)\b', re.I),
]


def classify_shareability(content: str) -> str:
    """Classify message shareability using keyword heuristics.

    Returns: 'SENSITIVE', 'PRIVATE', 'GROUP_SAFE', or 'PUBLIC'
    - SENSITIVE: health, finance, legal — never bridge to group
    - PRIVATE: personal feelings, confidential markers — never bridge
    - GROUP_SAFE: neutral content safe for group context
    - PUBLIC: explicitly shared or general knowledge
    """
    if not content:
        return "GROUP_SAFE"

    # Check sensitive patterns first (strongest signal)
    for pattern in SENSITIVE_PATTERNS:
        if pattern.search(content):
            return "SENSITIVE"

    # Check private patterns
    for pattern in PRIVATE_PATTERNS:
        if pattern.search(content):
            return "PRIVATE"

    return "GROUP_SAFE"


# ---------------------------------------------------------------------------
# Topic bridging
# ---------------------------------------------------------------------------

def get_bridgeable_topics(human_id: str, group_id: str) -> List[Dict]:
    """Topics discussed in BOTH DM and this group — safe for group enrichment.

    Returns list of dicts with label and domain.
    """
    try:
        gscope = f"group:{group_id}"
        with neo4j_session() as session:
            result = session.run(
                """
                MATCH (h:Human {id: $human_id})-[:DISCUSSED]->(t:Topic)
                WHERE EXISTS {
                    MATCH (m:Message {humanId: $hid})-[:HAS_TOPIC]->(t)
                    WHERE m.scope = 'dm'
                }
                AND EXISTS {
                    MATCH (m2:Message {humanId: $hid})-[:HAS_TOPIC]->(t)
                    WHERE m2.scope = $gscope
                }
                RETURN t.label AS label, t.domain AS domain
                """,
                human_id=human_id,
                hid=human_id,
                gscope=gscope,
            )
            return [dict(r) for r in result]
    except Exception as e:
        logger.error(f"get_bridgeable_topics failed: {e}")
        return []


# ---------------------------------------------------------------------------
# GroupSafeContextAssembler
# ---------------------------------------------------------------------------

class GroupSafeContextAssembler:
    """Wraps assemble_context() with bridging logic for group responses.

    Primary context = group-scoped messages.
    Bridged topics = topics appearing in both DM and group (safe overlap).
    """

    def assemble(
        self, human_id: str, message: str, group_id: str, max_tokens: int = 2000,
    ) -> Dict[str, Any]:
        """Assemble group-safe context with bridged topics."""
        # Get group-scoped context
        group_ctx = assemble_context(human_id, message, group_id=group_id, max_tokens=max_tokens)

        # Add bridged topics (safe overlap between DM and group)
        bridged_topics = get_bridgeable_topics(human_id, group_id)
        group_ctx["bridged_topics"] = bridged_topics
        group_ctx["context_mode"] = "group_safe"

        return group_ctx


if __name__ == "__main__":
    # Quick self-test
    print("Shareability classification tests:")
    tests = [
        ("my doctor appointment is Thursday", "SENSITIVE"),
        ("salary is $150k", "SENSITIVE"),
        ("the deployment looks good", "GROUP_SAFE"),
        ("just between us, I'm worried", "PRIVATE"),
        ("feeling really stressed lately", "PRIVATE"),
        ("hey everyone, the build passed", "GROUP_SAFE"),
        ("my lawyer said to file by Friday", "SENSITIVE"),
    ]
    for content, expected in tests:
        result = classify_shareability(content)
        status = "OK" if result == expected else "FAIL"
        print(f"  [{status}] '{content[:40]}' → {result} (expected {expected})")
