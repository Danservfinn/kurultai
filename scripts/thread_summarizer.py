#!/usr/bin/env python3
"""
Thread Summarizer — Generate summaries for DORMANT/ARCHIVED threads.

Finds threads with null summary, concatenates their messages, and uses
a local LLM (Ollama qwen3.5:9b) or Z.AI to produce 1-2 sentence summaries.

Usage:
    python3 thread_summarizer.py --limit 5
"""

import os
import sys
import json
import logging
import argparse
from typing import Optional, List, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from neo4j_task_tracker import get_driver, close_driver
from embedding_generator import generate_embedding
from consent_decorator import check_consent

logger = logging.getLogger(__name__)


def get_unsummarized_threads(limit: int = 5) -> List[Dict[str, Any]]:
    """Find DORMANT/ARCHIVED threads with null summary."""
    driver = get_driver()
    try:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (t:Thread)
                WHERE t.status IN ['DORMANT', 'ARCHIVED']
                  AND t.summary IS NULL
                  AND t.messageCount > 0
                RETURN t.id AS threadId, t.humanId AS humanId,
                       t.status AS status, t.messageCount AS messageCount,
                       toString(t.startedAt) AS startedAt
                ORDER BY t.startedAt DESC
                LIMIT $limit
                """,
                limit=limit,
            )
            return [dict(r) for r in result]
    finally:
        pass  # Don't close shared driver


def get_thread_messages(thread_id: str) -> List[str]:
    """Get scrubbed message content for a thread."""
    driver = get_driver()
    with driver.session() as session:
        result = session.run(
            """
            MATCH (m:Message)-[:IN_THREAD]->(t:Thread {id: $tid})
            WHERE m.contentScrubbed IS NOT NULL
            RETURN m.contentScrubbed AS text, m.direction AS direction
            ORDER BY m.timestamp ASC
            LIMIT 50
            """,
            tid=thread_id,
        )
        messages = []
        for r in result:
            prefix = "Human" if r["direction"] == "inbound" else "Kublai"
            messages.append(f"{prefix}: {r['text']}")
        return messages


def summarize_with_ollama(messages: List[str]) -> Optional[str]:
    """Generate a 1-2 sentence summary using Ollama."""
    try:
        import requests
        conversation = "\n".join(messages[:30])  # Cap at 30 messages
        prompt = (
            "Summarize this conversation in 1-2 sentences. "
            "Focus on the main topic and outcome.\n\n"
            f"{conversation}\n\nSummary:"
        )

        resp = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": "qwen3.5:9b",
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 100},
            },
            timeout=30,
        )
        if resp.status_code == 200:
            text = resp.json().get("message", {}).get("content", "").strip()
            # Strip thinking tags
            if "<think>" in text:
                think_end = text.rfind("</think>")
                if think_end >= 0:
                    text = text[think_end + 8:].strip()
            return text if text else None
    except Exception as e:
        logger.warning(f"Ollama summarization failed: {e}")
    return None


def summarize_with_zai(messages: List[str]) -> Optional[str]:
    """Generate a summary using Z.AI as fallback."""
    vault_file = os.path.expanduser("~/.openclaw/credentials/provider.env")
    token = None
    base_url = None
    try:
        with open(vault_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith("ZAI_AUTH_TOKEN="):
                    token = line.split("=", 1)[1].strip()
                elif line.startswith("ZAI_BASE_URL="):
                    base_url = line.split("=", 1)[1].strip()
    except FileNotFoundError:
        return None

    if not token or not base_url:
        return None

    try:
        import requests
        conversation = "\n".join(messages[:30])
        resp = requests.post(
            f"{base_url}/v1/messages",
            headers={
                "x-api-key": token,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 100,
                "messages": [{
                    "role": "user",
                    "content": (
                        "Summarize this conversation in 1-2 sentences. "
                        f"Focus on the main topic and outcome.\n\n{conversation}"
                    ),
                }],
            },
            timeout=30,
        )
        if resp.status_code == 200:
            content = resp.json().get("content", [])
            for block in content:
                if block.get("type") == "text":
                    return block.get("text", "").strip() or None
    except Exception as e:
        logger.warning(f"Z.AI summarization failed: {e}")
    return None


def store_summary(thread_id: str, summary: str, embedding: Optional[List[float]] = None):
    """Write summary + embedding to Thread node."""
    driver = get_driver()
    with driver.session() as session:
        session.run(
            """
            MATCH (t:Thread {id: $tid})
            SET t.summary = $summary,
                t.summaryEmbedding = $embedding,
                t.summarizedAt = datetime()
            """,
            tid=thread_id,
            summary=summary,
            embedding=embedding,
        )


def process_threads(limit: int = 5):
    """Main pipeline: find unsummarized threads, generate summaries."""
    threads = get_unsummarized_threads(limit)
    logger.info(f"Found {len(threads)} unsummarized threads")

    summarized = 0
    for thread in threads:
        tid = thread["threadId"]
        messages = get_thread_messages(tid)
        if not messages:
            logger.debug(f"Thread {tid[:8]} has no messages, skipping")
            continue

        # Try Ollama first (local, no consent needed)
        summary = summarize_with_ollama(messages)

        # Only try Z.AI if Ollama fails AND human has external_llm_processing consent
        if not summary:
            human_id = thread["humanId"]
            if check_consent(human_id, "external_llm_processing"):
                summary = summarize_with_zai(messages)
            else:
                logger.info(f"Skipping Z.AI for thread {tid[:8]} — no external_llm_processing consent")

        if summary:
            # Generate embedding of summary
            embedding = generate_embedding(summary)
            store_summary(tid, summary, embedding)
            summarized += 1
            logger.info(f"Summarized thread {tid[:8]}: {summary[:60]}...")
        else:
            logger.warning(f"Failed to summarize thread {tid[:8]}")

    logger.info(f"Summarized {summarized}/{len(threads)} threads")
    return summarized


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Thread Summarizer")
    parser.add_argument("--limit", type=int, default=5, help="Max threads to process")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    count = process_threads(args.limit)
    print(f"Summarized {count} threads")
