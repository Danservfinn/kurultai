#!/usr/bin/env python3
"""
Eval: Context Relevance — Scores assembled context chunks for relevance.
"""

import sys
import os
import json
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from neo4j_task_tracker import get_driver
from context_assembler import assemble_context
from context_formatter import format_context

logger = logging.getLogger(__name__)


def eval_context_relevance(human_id: str, test_messages: list = None) -> dict:
    """Evaluate context relevance for a human.

    Uses simple heuristics (non-empty sections, token usage).
    For full LLM-judge evaluation, extend with model call.
    """
    if not test_messages:
        test_messages = ["Hello", "How's the project going?", "What did we discuss last week?"]

    results = {"queries": [], "avg_sections_filled": 0, "avg_token_usage": 0}

    for msg in test_messages:
        context = assemble_context(human_id, msg)
        formatted = format_context(context)

        sections_filled = sum(
            1 for k, v in formatted.items()
            if v and not k.startswith("_") and len(v) > 10
        )
        total_sections = sum(1 for k in formatted if not k.startswith("_"))

        results["queries"].append({
            "message": msg,
            "sections_filled": sections_filled,
            "total_sections": total_sections,
            "fill_ratio": round(sections_filled / max(total_sections, 1), 2),
            "assembly_ms": context.get("assembly_ms", 0),
            "core_topics": len(context.get("core_topics", [])),
            "thread_messages": len(context.get("thread_messages", [])),
            "similar_messages": len(context.get("similar_messages", [])),
        })

    if results["queries"]:
        results["avg_sections_filled"] = round(
            sum(q["sections_filled"] for q in results["queries"]) / len(results["queries"]), 1
        )

    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("human_id")
    args = parser.parse_args()

    results = eval_context_relevance(args.human_id)
    print(json.dumps(results, indent=2))
