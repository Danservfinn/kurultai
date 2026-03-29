#!/usr/bin/env python3
"""
KB Selector — Select relevant knowledge base docs for task execution prompts.

Keyword-matches task body against KB doc topic maps to select the 1-2 most
relevant docs. Used by task_executor.py to inject grounded knowledge into
the prompt generation pipeline.

Usage:
    from kb_selector import select_kb_docs
    kb_content = select_kb_docs("fix the neo4j schema migration")
    # Returns: "## Knowledge Base: neo4j-schema.md\n[content...]"
"""

import os
from pathlib import Path
from typing import Optional

KB_DIR = Path.home() / ".openclaw" / "agents" / "main" / "knowledge"

KB_TOPIC_MAP = {
    "agent-roster.md": [
        "agent", "routing", "domain", "skill", "role", "asmr", "memory",
        "extractor", "temujin", "mongke", "chagatai", "jochi", "ogedei",
        "tolui", "kublai", "kurultai",
    ],
    "neo4j-schema.md": [
        "neo4j", "graph", "schema", "task", "node", "cypher", "inference",
        "proposal", "supersede", "constraint", "index", "merge", "event",
        "actionitem", "personalfact", "preference", "calendarevent",
    ],
    "api-endpoints.md": [
        "api", "endpoint", "http", "server", "route", "webhook",
        "get", "post", "patch", "delete", "server.js",
    ],
    "provider-fallback.md": [
        "provider", "fallback", "model", "credential", "vault", "oauth",
        "z.ai", "alibaba", "anthropic", "claude-agent", "mode.json",
    ],
    "task-executor.md": [
        "executor", "execution", "session", "stall", "verify", "concurrency",
        "wal", "task_executor", "taskrunner", "sessionmanager",
    ],
    "dashboard-views.md": [
        "dashboard", "ui", "kanban", "calendar", "view", "tab", "dispatch",
        "reflection", "session", "wrapper",
    ],
}


def select_kb_docs(
    task_body: str,
    kb_hint: Optional[str] = None,
    max_docs: int = 2,
    max_bytes: int = 12000,
) -> str:
    """Select and return concatenated KB content for the most relevant docs.

    Args:
        task_body: The task description to match against.
        kb_hint: Optional explicit KB doc filename (guaranteed include).
        max_docs: Maximum number of docs to include.
        max_bytes: Maximum total bytes of KB content.

    Returns:
        Formatted string with doc headers, or empty string if no matches.

        Example output:
            ## Knowledge Base: neo4j-schema.md
            [content...]

            ## Knowledge Base: api-endpoints.md
            [content...]
    """
    if not KB_DIR.exists():
        return ""

    task_lower = task_body.lower()

    # Score each doc by keyword overlap
    scores = {}
    for doc_name, keywords in KB_TOPIC_MAP.items():
        doc_path = KB_DIR / doc_name
        if not doc_path.exists():
            continue
        score = sum(1 for kw in keywords if kw in task_lower)
        if score > 0:
            scores[doc_name] = score

    # If kb_hint specified, guarantee it's included
    if kb_hint and (KB_DIR / kb_hint).exists():
        scores[kb_hint] = scores.get(kb_hint, 0) + 100  # priority boost

    if not scores:
        return ""

    # Sort by score descending, take top max_docs
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:max_docs]

    # Load and concatenate docs within byte budget
    sections = []
    total_bytes = 0

    for doc_name, _score in ranked:
        doc_path = KB_DIR / doc_name
        try:
            content = doc_path.read_text()
        except OSError:
            continue

        # Truncate if adding this doc would exceed budget
        remaining = max_bytes - total_bytes
        if remaining <= 0:
            break
        if len(content) > remaining:
            content = content[:remaining].rsplit("\n", 1)[0] + "\n..."

        sections.append(f"## Knowledge Base: {doc_name}\n{content}")
        total_bytes += len(content)

    return "\n\n".join(sections)


if __name__ == "__main__":
    import sys
    task = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "fix the neo4j schema"
    result = select_kb_docs(task)
    if result:
        print(f"Selected KB docs ({len(result)} bytes):")
        # Print just the headers
        for line in result.split("\n"):
            if line.startswith("## Knowledge Base:"):
                print(f"  {line}")
    else:
        print("No relevant KB docs found")
