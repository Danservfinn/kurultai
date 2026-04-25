#!/usr/bin/env python3
"""
Async LLM Extraction Pipeline — Background processor for message analysis.

Processes messages with extractionStatus='PENDING' through DeepSeek (via OpenRouter).
Extracts: structured topics, sentiment, intent, action items, mentioned humans.

Usage:
    from async_extractor import AsyncExtractor
    extractor = AsyncExtractor()
    extractor.process_pending(limit=10)

    # Or run as a standalone worker:
    python3 async_extractor.py --limit 50 --interval 30
"""
from __future__ import annotations

import os
import sys
import json
import time
import logging
import argparse
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from neo4j_task_tracker import get_driver, close_driver
from pii_scrubber import PIIScrubber
from consent_decorator import check_consent

logger = logging.getLogger(__name__)

# Load OpenRouter key
_OPENROUTER_KEY = None


def _get_openrouter_key() -> Optional[str]:
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


EXTRACTION_PROMPT = """Analyze this conversation message and extract structured information.

Message (PII has been redacted):
---
{content}
---

Previous context (last 3 messages in thread):
---
{context}
---

Return a JSON object with these fields:
{{
    "topics": [
        {{"label": "topic name", "type": "keyword|concept|entity", "domain": "technical|business|personal|social", "confidence": 0.0-1.0}}
    ],
    "sentiment": {{
        "valence": "positive|neutral|negative|mixed",
        "arousal": "calm|moderate|intense",
        "confidence": 0.0-1.0
    }},
    "intent": {{
        "primary": "question|request|inform|discuss|vent|greet|farewell|acknowledge|other",
        "confidence": 0.0-1.0
    }},
    "action_items": [
        {{"description": "what needs doing", "assignee": "person or null", "priority": "high|medium|low", "deadline": "date or null"}}
    ],
    "mentioned_humans": [
        {{"name": "person name", "context": "how they were mentioned"}}
    ],
    "summary": "One-sentence summary of the message"
}}

Return ONLY the JSON object, no markdown or explanations."""


class AsyncExtractor:
    """Background worker for LLM-based message extraction."""

    def __init__(self):
        self.driver = get_driver()
        self.model = "deepseek/deepseek-chat"

    def close(self):
        if self.driver:
            close_driver()
            self.driver = None

    def process_pending(self, limit: int = 10) -> Dict[str, Any]:
        """Process pending messages.

        Returns:
            Dict with processed count, errors, timing
        """
        t0 = time.monotonic()
        messages = self._fetch_pending(limit)

        if not messages:
            return {"processed": 0, "errors": 0, "ms": 0}

        processed = 0
        errors = 0

        for msg in messages:
            try:
                # Check consent
                if not check_consent(msg["humanId"], "message_analysis"):
                    self._mark_status(msg["id"], "SKIPPED_NO_CONSENT")
                    continue

                # Get thread context
                context = self._get_thread_context(msg["id"], msg.get("threadId"))

                # Call LLM
                extraction = self._extract(msg["contentScrubbed"], context)

                if extraction:
                    # Store results
                    self._store_extraction(msg["id"], msg["humanId"], extraction)
                    self._mark_status(msg["id"], "EXTRACTED")
                    processed += 1
                else:
                    self._mark_status(msg["id"], "EXTRACTION_FAILED")
                    errors += 1

            except Exception as e:
                logger.error(f"Extraction failed for {msg['id'][:8]}: {e}")
                self._mark_status(msg["id"], "EXTRACTION_FAILED")
                errors += 1

        total_ms = (time.monotonic() - t0) * 1000
        return {"processed": processed, "errors": errors, "ms": round(total_ms)}

    def _fetch_pending(self, limit: int) -> List[Dict[str, Any]]:
        """Fetch messages with PENDING extraction status."""
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (m:Message {extractionStatus: 'PENDING'})
                OPTIONAL MATCH (m)-[:IN_THREAD]->(t:Thread)
                RETURN m.id AS id, m.humanId AS humanId,
                       m.contentScrubbed AS contentScrubbed,
                       m.direction AS direction,
                       toString(m.timestamp) AS timestamp,
                       t.id AS threadId
                ORDER BY m.timestamp ASC
                LIMIT $limit
                """,
                limit=limit,
            )
            return [dict(r) for r in result]

    def _get_thread_context(self, message_id: str, thread_id: Optional[str]) -> str:
        """Get last 3 messages in the thread for context."""
        if not thread_id:
            return "(no thread context)"

        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (m:Message)-[:IN_THREAD]->(t:Thread {id: $thread_id})
                WHERE m.id <> $msg_id
                RETURN m.contentScrubbed AS text, m.direction AS dir,
                       toString(m.timestamp) AS ts
                ORDER BY m.timestamp DESC
                LIMIT 3
                """,
                thread_id=thread_id,
                msg_id=message_id,
            )
            messages = [dict(r) for r in result]

        if not messages:
            return "(first message in thread)"

        lines = []
        for msg in reversed(messages):
            prefix = "→" if msg["dir"] == "outbound" else "←"
            lines.append(f"{prefix} {msg['text']}")
        return "\n".join(lines)

    def _extract(self, content: str, context: str) -> Optional[Dict[str, Any]]:
        """Call LLM for extraction. Tries OpenRouter, falls back to local Ollama."""
        prompt = EXTRACTION_PROMPT.format(content=content, context=context)

        # Try OpenRouter first
        result = self._try_openrouter(prompt)
        if result:
            return result

        # Fallback: local Ollama (qwen3.5:9b)
        result = self._try_ollama(prompt)
        if result:
            return result

        return None

    def _try_openrouter(self, prompt: str) -> Optional[Dict[str, Any]]:
        """Try OpenRouter DeepSeek Chat."""
        api_key = _get_openrouter_key()
        if not api_key:
            return None

        try:
            import requests
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": "You are a precise data extraction assistant. Return only valid JSON."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 1000,
                },
                timeout=30,
            )

            if resp.status_code != 200:
                logger.warning(f"OpenRouter API error {resp.status_code}, falling back to Ollama")
                return None

            return self._parse_llm_response(resp.json()["choices"][0]["message"]["content"])

        except Exception as e:
            logger.warning(f"OpenRouter failed: {e}, falling back to Ollama")
            return None

    def _try_ollama(self, prompt: str) -> Optional[Dict[str, Any]]:
        """Try local Ollama qwen3.5:9b."""
        try:
            import requests
            resp = requests.post(
                "http://localhost:11434/api/chat",
                json={
                    "model": "qwen3.5:9b",
                    "messages": [
                        {"role": "system", "content": "You are a precise data extraction assistant. Return only valid JSON. No thinking tags, no explanations."},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "options": {"temperature": 0.1},
                },
                timeout=60,
            )

            if resp.status_code != 200:
                logger.error(f"Ollama API error: {resp.status_code}")
                return None

            text = resp.json().get("message", {}).get("content", "")
            return self._parse_llm_response(text)

        except Exception as e:
            logger.error(f"Ollama extraction failed: {e}")
            return None

    def _parse_llm_response(self, text: str) -> Optional[Dict[str, Any]]:
        """Parse LLM response text into extraction dict."""
        text = text.strip()
        # Strip thinking tags (qwen3.5 sometimes wraps in <think>...</think>)
        if "<think>" in text:
            think_end = text.rfind("</think>")
            if think_end >= 0:
                text = text[think_end + 8:].strip()
        # Strip markdown code fences
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error in extraction: {e}")
            logger.debug(f"Raw text: {text[:200]}")
            return None
            return None

    def _store_extraction(
        self, message_id: str, human_id: str, extraction: Dict[str, Any]
    ):
        """Store extraction results on the Message node and create related nodes."""
        with self.driver.session() as session:
            # Store summary and sentiment on Message
            session.run(
                """
                MATCH (m:Message {id: $msg_id})
                SET m.summary = $summary,
                    m.sentiment = $sentiment,
                    m.intent = $intent,
                    m.extractedAt = datetime()
                """,
                msg_id=message_id,
                summary=extraction.get("summary"),
                sentiment=json.dumps(extraction.get("sentiment", {})),
                intent=json.dumps(extraction.get("intent", {})),
            )

            # Create/link topics
            for topic_data in extraction.get("topics", []):
                label = topic_data.get("label", "").strip().lower()
                if not label or len(label) < 2:
                    continue
                session.run(
                    """
                    MATCH (m:Message {id: $msg_id})
                    MERGE (topic:Topic {label: $label})
                    ON CREATE SET topic.id = randomUUID(),
                                  topic.type = $type,
                                  topic.domain = $domain,
                                  topic.createdAt = datetime()
                    MERGE (m)-[r:HAS_TOPIC]->(topic)
                    ON CREATE SET r.confidence = $confidence,
                                  r.detectedAt = datetime()
                    WITH topic
                    MERGE (h:Human {id: $human_id})
                    MERGE (h)-[d:DISCUSSED]->(topic)
                    ON CREATE SET d.count = 1, d.firstAt = datetime(), d.lastAt = datetime()
                    ON MATCH SET d.count = d.count + 1, d.lastAt = datetime()
                    """,
                    msg_id=message_id,
                    human_id=human_id,
                    label=label,
                    type=topic_data.get("type", "keyword"),
                    domain=topic_data.get("domain", "general"),
                    confidence=topic_data.get("confidence", 0.5),
                )

            # Create action items
            for item in extraction.get("action_items", []):
                session.run(
                    """
                    MATCH (m:Message {id: $msg_id})
                    CREATE (ai:ActionItem {
                        id: randomUUID(),
                        humanId: $human_id,
                        description: $description,
                        assignee: $assignee,
                        priority: $priority,
                        deadline: $deadline,
                        status: 'OPEN',
                        createdAt: datetime(),
                        updatedAt: datetime()
                    })
                    CREATE (m)-[:HAS_ACTION_ITEM]->(ai)
                    """,
                    msg_id=message_id,
                    human_id=human_id,
                    description=item.get("description", ""),
                    assignee=item.get("assignee"),
                    priority=item.get("priority", "medium"),
                    deadline=item.get("deadline"),
                )

    def _mark_status(self, message_id: str, status: str):
        """Update extractionStatus on a Message node."""
        with self.driver.session() as session:
            session.run(
                "MATCH (m:Message {id: $id}) SET m.extractionStatus = $status",
                id=message_id,
                status=status,
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Async message extraction worker")
    parser.add_argument("--limit", type=int, default=10, help="Messages per batch")
    parser.add_argument("--interval", type=int, default=0, help="Seconds between batches (0=once)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    extractor = AsyncExtractor()

    if args.interval > 0:
        print(f"Running extraction worker: batch={args.limit}, interval={args.interval}s")
        while True:
            result = extractor.process_pending(args.limit)
            if result["processed"] > 0 or result["errors"] > 0:
                print(f"  Processed: {result['processed']}, Errors: {result['errors']}, Time: {result['ms']}ms")
            time.sleep(args.interval)
    else:
        result = extractor.process_pending(args.limit)
        print(f"Processed: {result['processed']}, Errors: {result['errors']}, Time: {result['ms']}ms")

    extractor.close()
