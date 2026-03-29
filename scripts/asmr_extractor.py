#!/usr/bin/env python3
"""
asmr_extractor.py — 10-Vector Structured Knowledge Extraction for OpenClaw Kurultai.

ASMR = Adaptive Structured Memory Representation.

Processes messages at extractionStatus='EXTRACTED' and extracts ten knowledge
vectors, validates them with asmr_schema_validator, then MERGEs them into
Neo4j as multi-label Inference nodes with full supersede tracking.

10 Vectors:
    1. personal_info       — key/value facts about the human
    2. preferences         — domain-scoped like/dislike statements
    3. events              — calendar events and deadlines
    4. temporal_data       — facts that change over time (job, city, etc.)
    5. updates             — explicit corrections to prior facts
    6. assistant_instructions — how the AI should behave with this human
    7. goals               — projects and objectives the human is pursuing
    10. relationships      — relationship context between people
    14p. emotional_cue     — per-message emotional tone (V14p)
    16p. questions         — questions the speaker is asking (V16p)

MERGE keys:
    PersonalFact       MERGE on (humanId, key)
    Preference         MERGE on (humanId, domain, canonical_key)
    CalendarEvent      MERGE on (humanId, title, startTime)
    TemporalSeq        CREATE new + [:SUPERSEDES] chain
    Correction         CREATE new + process_supersedes()
    PersonalFact (ASSISTANT_PREF)  MERGE on (humanId, key)

Usage:
    python3 asmr_extractor.py --limit 20
    python3 asmr_extractor.py --limit 5   # smoke-test on small batch
"""

import os
import sys
import json
import re
import time
import logging
import argparse
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import get_driver, close_driver
from asmr_schema_validator import validate_extraction
from supersede_detector import process_supersedes

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Extraction prompt — closed enums, temperature=0 (set in API call params)
# ---------------------------------------------------------------------------

# NOTE: temperature=0 is enforced in the LLM API call parameters, not here.
# This prompt uses closed enums to constrain hallucination surface.

ASMR_EXTRACTION_PROMPT = """You are a structured knowledge extraction engine operating at temperature=0.
Extract ONLY information that is EXPLICITLY stated in the message. Do not infer or guess.

Speaker: {display_name}
Date: {date}
Scope: {scope}

Message:
---
{content}
---

Thread context (last 2 messages):
---
{context}
---

Return a JSON object with exactly these 6 keys. Use empty arrays [] when nothing applies.

{{
  "personal_info": [
    {{
      "key": "<one of: name|email|phone|role|company|location|relationship|age|birthday|timezone|language|other>",
      "value": "<exact stated value>",
      "confidence": <0.0-1.0>
    }}
  ],
  "preferences": [
    {{
      "domain": "<one of: communication|schedule|format|content|tool|social>",
      "canonical_key": "<short snake_case identifier, e.g. 'prefers_short_replies'>",
      "statement": "<verbatim or near-verbatim preference statement>",
      "valence": "<one of: LIKE|DISLIKE|NEUTRAL>",
      "strength": <0.0-1.0>
    }}
  ],
  "events": [
    {{
      "title": "<event name>",
      "event_type": "<one of: MEETING|APPOINTMENT|DEADLINE|REMINDER|ANNIVERSARY>",
      "start_time": "<ISO 8601 or natural date string, empty string if unknown>",
      "participants": ["<name1>", "<name2>"]
    }}
  ],
  "temporal_data": [
    {{
      "subject": "<snake_case field name, e.g. 'city' or 'job_title'>",
      "old_value": "<prior value if stated, else empty string>",
      "new_value": "<current value>",
      "valid_from": "<date this became true, empty if unknown>"
    }}
  ],
  "updates": [
    {{
      "corrects_field": "<field being corrected, e.g. 'email' or 'company'>",
      "old_value": "<what was wrong>",
      "new_value": "<what is correct>",
      "verbatim": "<the exact phrase that signals the correction>"
    }}
  ],
  "assistant_instructions": [
    {{
      "key": "<one of: response_length|response_style|formality|emoji_use|format|persona|proactivity|other>",
      "instruction": "<what the human wants the AI to do>",
      "confidence": <0.0-1.0>
    }}
  ],
  "goals": [
    {{
      "title": "<what they are working toward>",
      "status": "<active|completed|abandoned>",
      "domain": "<product|engineering|hiring|business|personal>",
      "priority": "<high|medium|low>",
      "deadline": "<date or timeframe if mentioned, else empty>",
      "blockers": ["<obstacles mentioned>"]
    }}
  ],
  "relationships": [
    {{
      "person": "<name of the person>",
      "nature": "<reports-to|mentoring|collaborating|conflict|manages|advises>",
      "context": "<brief context about the relationship>",
      "active": true
    }}
  ],
  "emotional_cue": "<one of: frustrated|excited|anxious|grateful|neutral — overall emotional tone of this message>",
  "questions": [
    {{
      "question": "<a question the speaker is asking>",
      "expecting_answer": true
    }}
  ]
}}

RULES:
- Only extract EXPLICITLY stated information. Never infer or assume.
- personal_info.key MUST be from the closed enum above.
- preferences.domain MUST be from the closed enum above.
- events.event_type MUST be from the closed enum above.
- assistant_instructions.key MUST be from the closed enum above.
- valence MUST be LIKE, DISLIKE, or NEUTRAL (uppercase).
- confidence and strength are floats between 0.0 and 1.0.
- Return ONLY valid JSON. No markdown fences. No explanation. No preamble."""


# ---------------------------------------------------------------------------
# AsmrExtractor
# ---------------------------------------------------------------------------

class AsmrExtractor:
    """6-vector knowledge extraction worker.

    Reads messages at extractionStatus='EXTRACTED', calls the LLM, validates
    output, then MERGEs into Neo4j. Advances status to 'ASMR_EXTRACTED' on
    success or 'ASMR_FAILED' on error.

    Lifecycle:
        extractor = AsmrExtractor()
        result = extractor.process_pending(limit=20)
        extractor.close()

    Or use as a context manager::

        with AsmrExtractor() as e:
            result = e.process_pending()
    """

    #: Ollama local model — Qwen 3.5 9B for structured extraction at temp=0
    OLLAMA_MODEL = "qwen3.5:9b"

    def __init__(self) -> None:
        self.driver = get_driver()

    def __enter__(self) -> "AsmrExtractor":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def close(self) -> None:
        """Release Neo4j driver connection."""
        if self.driver:
            close_driver()
            self.driver = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_pending(self, limit: int = 20) -> Dict[str, Any]:
        """Process messages at extractionStatus='EXTRACTED' -> 'ASMR_EXTRACTED'.

        Args:
            limit: Maximum number of messages to process in this batch.

        Returns:
            Dict with keys: processed, errors, skipped, ms
        """
        # Check ASMR config — skip if disabled or too soon
        try:
            config_path = Path.home() / '.openclaw' / 'asmr_config.json'
            if config_path.exists():
                config = json.loads(config_path.read_text())
                qwen = config.get('qwen_tier', {})
                if not qwen.get('enabled', True):
                    logger.info("ASMR: Qwen tier disabled via config, skipping")
                    return {'processed': 0, 'errors': 0, 'skipped': 0, 'ms': 0}
        except Exception as e:
            logger.debug(f"ASMR: config check failed (proceeding anyway): {e}")

        t0 = time.monotonic()
        messages = self._fetch_pending(limit)

        if not messages:
            logger.info("ASMR: no pending messages found")
            return {'processed': 0, 'errors': 0, 'skipped': 0, 'ms': 0}

        logger.info(f"ASMR: processing {len(messages)} message(s)")
        processed = errors = skipped = 0

        for msg in messages:
            msg_id = msg['id']
            try:
                context = self._get_thread_context(msg_id, msg.get('threadId'))
                scope = msg.get('scope') or 'dm'
                display_name = msg.get('displayName') or 'Unknown'
                date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')

                raw_result = self._extract(
                    content=msg['contentScrubbed'],
                    context=context,
                    display_name=display_name,
                    date_str=date_str,
                    scope=scope,
                )

                if raw_result is None:
                    logger.warning(f"ASMR: LLM returned no result for {msg_id[:8]}")
                    self._mark_status(msg_id, 'ASMR_FAILED')
                    errors += 1
                    continue

                # Validate before any MERGE (review fix #7)
                cleaned, warnings = validate_extraction(raw_result)
                for w in warnings:
                    logger.info(f"ASMR validation [{msg_id[:8]}]: {w}")

                self._store_vectors(msg_id, msg['humanId'], cleaned, scope)
                self._mark_status(msg_id, 'ASMR_EXTRACTED')
                processed += 1
                logger.info(
                    f"ASMR: processed {msg_id[:8]} "
                    f"(pi={len(cleaned['personal_info'])}, "
                    f"pref={len(cleaned['preferences'])}, "
                    f"ev={len(cleaned['events'])}, "
                    f"td={len(cleaned['temporal_data'])}, "
                    f"upd={len(cleaned['updates'])}, "
                    f"ai={len(cleaned['assistant_instructions'])}, "
                    f"cue={cleaned.get('emotional_cue', 'neutral')}, "
                    f"qs={len(cleaned.get('questions', []))})"
                )

            except Exception as e:
                logger.error(
                    f"ASMR: extraction error on {msg_id[:8]}: {e}", exc_info=True
                )
                self._mark_status(msg_id, 'ASMR_FAILED')
                errors += 1

        # V12: Communication Fingerprint (pure Python stats, no LLM)
        try:
            from asmr_stats_extractor import compute_all_fingerprints
            fp_count = compute_all_fingerprints(self.driver)
            logger.info(f"ASMR: V12 fingerprints updated for {fp_count} human(s)")
        except Exception as e:
            logger.warning(f"ASMR: V12 fingerprint computation failed: {e}")

        ms = round((time.monotonic() - t0) * 1000)
        summary = {'processed': processed, 'errors': errors, 'skipped': skipped, 'ms': ms}
        logger.info(f"ASMR batch complete: {summary}")
        return summary

    # ------------------------------------------------------------------
    # Neo4j fetch helpers
    # ------------------------------------------------------------------

    def _fetch_pending(self, limit: int) -> List[Dict[str, Any]]:
        """Fetch messages at extractionStatus='EXTRACTED' with thread and human info."""
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (m:Message {extractionStatus: 'EXTRACTED'})
                OPTIONAL MATCH (m)-[:IN_THREAD]->(t:Thread)
                OPTIONAL MATCH (m)-[:SENT_BY]->(h:Human)
                RETURN
                    m.id          AS id,
                    m.humanId     AS humanId,
                    m.contentScrubbed AS contentScrubbed,
                    m.scope       AS scope,
                    coalesce(h.displayName, h.name, 'Unknown') AS displayName,
                    t.id          AS threadId
                ORDER BY m.timestamp ASC
                LIMIT $limit
                """,
                limit=limit,
            )
            return [dict(r) for r in result]

    def _get_thread_context(
        self, message_id: str, thread_id: Optional[str]
    ) -> str:
        """Return last 2 messages in the thread as a formatted string."""
        if not thread_id:
            return "(no thread context)"

        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (m:Message)-[:IN_THREAD]->(t:Thread {id: $thread_id})
                WHERE m.id <> $msg_id
                RETURN m.contentScrubbed AS text,
                       m.direction       AS dir,
                       toString(m.timestamp) AS ts
                ORDER BY m.timestamp DESC
                LIMIT 2
                """,
                thread_id=thread_id,
                msg_id=message_id,
            )
            msgs = [dict(r) for r in result]

        if not msgs:
            return "(first message in thread)"

        lines = []
        for m in reversed(msgs):
            arrow = "→" if m.get("dir") == "outbound" else "←"
            lines.append(f"{arrow} {m.get('text', '')}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # LLM extraction
    # ------------------------------------------------------------------

    def _extract(
        self,
        content: str,
        context: str,
        display_name: str,
        date_str: str,
        scope: str,
    ) -> Optional[Dict[str, Any]]:
        """Build prompt and call local Ollama LLM (qwen3.5:9b)."""
        if not content or not content.strip():
            logger.debug("ASMR: skipping empty content")
            return None

        prompt = ASMR_EXTRACTION_PROMPT.format(
            display_name=display_name,
            date=date_str,
            scope=scope,
            content=content,
            context=context,
        )

        return self._try_ollama(prompt)

    def _try_ollama(self, prompt: str) -> Optional[Dict[str, Any]]:
        """Call local Ollama qwen3.5:9b at temperature=0 via chat API.

        Uses the chat endpoint for proper system/user message separation.
        Thinking mode is disabled to avoid wasted tokens and latency.

        Returns parsed dict on success, None on failure.
        """
        try:
            import requests
            resp = requests.post(
                "http://localhost:11434/api/chat",
                json={
                    "model": self.OLLAMA_MODEL,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a precise structured knowledge extraction engine. "
                                "Return only valid JSON with no markdown, no explanations."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "options": {
                        "temperature": 0,
                        "num_predict": 1500,
                    },
                    "think": False,
                },
                timeout=120,
            )

            if resp.status_code != 200:
                logger.error(f"ASMR: Ollama HTTP {resp.status_code}")
                return None

            data = resp.json()
            raw = data.get("message", {}).get("content", "")
            return self._parse_response(raw)

        except Exception as e:
            logger.error(f"ASMR: Ollama call failed: {e}")
            return None

    def _parse_response(self, text: str) -> Optional[Dict[str, Any]]:
        """Strip <think> blocks and markdown fences, then parse JSON.

        Handles:
        - <think>...</think> wrapper (Qwen reasoning models)
        - ```json ... ``` markdown fences
        - Leading/trailing whitespace
        """
        if not text:
            return None

        text = text.strip()

        # Strip <think>...</think> blocks (Qwen 2.5 sometimes emits these)
        think_match = re.search(r'<think>.*?</think>', text, re.DOTALL | re.IGNORECASE)
        if think_match:
            text = text[think_match.end():].strip()

        # Strip markdown fences (```json ... ``` or ``` ... ```)
        fence_match = re.match(r'^```(?:json)?\s*\n?(.*?)```\s*$', text, re.DOTALL)
        if fence_match:
            text = fence_match.group(1).strip()

        if not text:
            return None

        try:
            result = json.loads(text)
            if not isinstance(result, dict):
                logger.warning("ASMR: parsed response is not a dict")
                return None
            return result
        except json.JSONDecodeError as e:
            logger.error(f"ASMR: JSON parse error: {e}")
            logger.debug(f"ASMR: raw text snippet: {text[:300]}")
            return None

    # ------------------------------------------------------------------
    # Vector storage — dispatches to per-vector methods
    # ------------------------------------------------------------------

    def _store_vectors(
        self,
        msg_id: str,
        human_id: str,
        cleaned: Dict[str, Any],
        scope: str,
    ) -> None:
        """Dispatch all 8 vectors to their respective store methods."""
        self._store_personal_info(msg_id, human_id, cleaned.get('personal_info', []), scope)
        self._store_preferences(msg_id, human_id, cleaned.get('preferences', []), scope)
        self._store_events(msg_id, human_id, cleaned.get('events', []), scope)
        self._store_temporal(msg_id, human_id, cleaned.get('temporal_data', []), scope)
        self._store_updates(msg_id, human_id, cleaned.get('updates', []), scope)
        self._store_assistant_instructions(
            msg_id, human_id, cleaned.get('assistant_instructions', []), scope
        )
        self._store_goals(msg_id, human_id, cleaned.get('goals', []), scope)
        self._store_relationships(msg_id, human_id, cleaned.get('relationships', []), scope)
        self._store_emotional_cue(msg_id, human_id, cleaned.get('emotional_cue', 'neutral'), scope)
        self._store_questions(msg_id, human_id, cleaned.get('questions', []), scope)

    # ------------------------------------------------------------------
    # Vector 1: PersonalFact — MERGE on (humanId, key) [review fix #1]
    # ------------------------------------------------------------------

    def _store_personal_info(
        self, msg_id: str, human_id: str, items: list, scope: str
    ) -> None:
        """MERGE PersonalFact on (humanId, key). Sets value ON MATCH.

        MERGE key is (humanId, key) — NOT (humanId, key, value).
        This means a second extraction with a new value for the same key
        overwrites in place, then process_supersedes() creates the audit trail.
        """
        with self.driver.session() as session:
            for item in items:
                try:
                    result = session.run(
                        """
                        MERGE (pf:Inference:PersonalFact {humanId: $hid, key: $key})
                        ON CREATE SET
                            pf.id          = randomUUID(),
                            pf.value       = $value,
                            pf.active      = true,
                            pf.scope       = $scope,
                            pf.field       = $key,
                            pf.confidence  = $conf,
                            pf.sourceMsg   = $msg_id,
                            pf.superseded  = false,
                            pf.claim       = $hid + ' ' + $key + ': ' + $value,
                            pf.createdAt   = datetime(),
                            pf.timestamp   = datetime()
                        ON MATCH SET
                            pf.value       = $value,
                            pf.confidence  = $conf,
                            pf.sourceMsg   = $msg_id,
                            pf.updatedAt   = datetime()
                        WITH pf
                        MATCH (m:Message {id: $msg_id})
                        MERGE (m)-[:EXTRACTED]->(pf)
                        RETURN pf.id AS pf_id
                        """,
                        hid=human_id,
                        key=item['key'],
                        value=item['value'],
                        scope=scope,
                        conf=item['confidence'],
                        msg_id=msg_id,
                    )
                    record = result.single()
                    if record and record['pf_id']:
                        process_supersedes(
                            session,
                            human_id,
                            record['pf_id'],
                            item['key'],
                            item['value'],
                            '',  # no verbatim signal text for implicit updates
                        )
                except Exception as e:
                    logger.warning(
                        f"ASMR: _store_personal_info failed for key={item.get('key')}: {e}"
                    )

    # ------------------------------------------------------------------
    # Vector 2: Preference — MERGE on (humanId, domain, canonical_key) [review fix #2]
    # ------------------------------------------------------------------

    def _store_preferences(
        self, msg_id: str, human_id: str, items: list, scope: str
    ) -> None:
        """MERGE Preference on (humanId, domain, canonical_key). Updates free-text ON MATCH.

        canonical_key provides stable identity for dedup across sessions.
        Free-text statement can evolve without creating duplicate nodes.
        """
        with self.driver.session() as session:
            for item in items:
                try:
                    session.run(
                        """
                        MERGE (p:Inference:Preference {
                            humanId:       $hid,
                            domain:        $domain,
                            canonical_key: $ckey
                        })
                        ON CREATE SET
                            p.id         = randomUUID(),
                            p.preference = $stmt,
                            p.valence    = $valence,
                            p.strength   = $strength,
                            p.active     = true,
                            p.scope      = $scope,
                            p.field      = 'preference:' + $domain,
                            p.value      = $stmt,
                            p.superseded = false,
                            p.sourceMsg  = $msg_id,
                            p.createdAt  = datetime(),
                            p.timestamp  = datetime()
                        ON MATCH SET
                            p.preference = $stmt,
                            p.strength   = $strength,
                            p.valence    = $valence,
                            p.sourceMsg  = $msg_id,
                            p.updatedAt  = datetime()
                        WITH p
                        MATCH (m:Message {id: $msg_id})
                        MERGE (m)-[:EXTRACTED]->(p)
                        """,
                        hid=human_id,
                        domain=item['domain'],
                        ckey=item['canonical_key'],
                        stmt=item['statement'],
                        valence=item['valence'],
                        strength=item['strength'],
                        scope=scope,
                        msg_id=msg_id,
                    )
                except Exception as e:
                    logger.warning(
                        f"ASMR: _store_preferences failed for ckey={item.get('canonical_key')}: {e}"
                    )

    # ------------------------------------------------------------------
    # Vector 3: CalendarEvent — MERGE on (humanId, title, startTime) [review fix #8]
    # ------------------------------------------------------------------

    def _store_events(
        self, msg_id: str, human_id: str, items: list, scope: str
    ) -> None:
        """MERGE CalendarEvent on (humanId, title, startTime).

        Idempotent: re-mentioning the same event in the same thread will
        MATCH rather than CREATE, avoiding duplicate calendar nodes.
        """
        with self.driver.session() as session:
            for item in items:
                if not item.get('title'):
                    continue
                try:
                    session.run(
                        """
                        MERGE (ce:Inference:CalendarEvent {
                            humanId:   $hid,
                            title:     $title,
                            startTime: $start
                        })
                        ON CREATE SET
                            ce.id          = randomUUID(),
                            ce.eventType   = $etype,
                            ce.participants = $parts,
                            ce.status      = 'PENDING',
                            ce.scope       = $scope,
                            ce.field       = 'event:' + $title,
                            ce.value       = $title,
                            ce.superseded  = false,
                            ce.sourceMsg   = $msg_id,
                            ce.createdAt   = datetime(),
                            ce.timestamp   = datetime()
                        ON MATCH SET
                            ce.eventType    = $etype,
                            ce.participants = $parts,
                            ce.sourceMsg    = $msg_id,
                            ce.updatedAt    = datetime()
                        WITH ce
                        MATCH (m:Message {id: $msg_id})
                        MERGE (m)-[:EXTRACTED]->(ce)
                        """,
                        hid=human_id,
                        title=item['title'],
                        start=item['start_time'],
                        etype=item['event_type'],
                        parts=item['participants'],
                        scope=scope,
                        msg_id=msg_id,
                    )
                except Exception as e:
                    logger.warning(
                        f"ASMR: _store_events failed for title={item.get('title')}: {e}"
                    )

    # ------------------------------------------------------------------
    # Vector 4: TemporalSeq — CREATE + [:SUPERSEDES] chain
    # ------------------------------------------------------------------

    def _store_temporal(
        self, msg_id: str, human_id: str, items: list, scope: str
    ) -> None:
        """CREATE new TemporalSeq nodes and link via [:SUPERSEDES] to prior current.

        Each change to a temporal fact (e.g. city moves, job changes) creates a
        new node. The prior isCurrent=true node is set to isCurrent=false before
        the new one is created, preserving full change history.
        """
        with self.driver.session() as session:
            for item in items:
                if not item.get('subject') or not item.get('new_value'):
                    continue
                try:
                    # Step 1: retire any currently-active node for this subject
                    session.run(
                        """
                        MATCH (ts:Inference:TemporalSeq {
                            humanId:   $hid,
                            subject:   $subj,
                            isCurrent: true
                        })
                        SET ts.isCurrent    = false,
                            ts.superseded   = true,
                            ts.supersededAt = datetime()
                        """,
                        hid=human_id,
                        subj=item['subject'],
                    )

                    # Step 2: create new current node and link to prior
                    session.run(
                        """
                        CREATE (ts:Inference:TemporalSeq {
                            id:        randomUUID(),
                            humanId:   $hid,
                            subject:   $subj,
                            value:     $new_val,
                            validFrom: $vfrom,
                            isCurrent: true,
                            scope:     $scope,
                            field:     $subj,
                            sourceMsg: $msg_id,
                            superseded: false,
                            createdAt: datetime(),
                            timestamp: datetime()
                        })
                        WITH ts
                        OPTIONAL MATCH (prior:Inference:TemporalSeq {
                            humanId: $hid,
                            subject: $subj,
                            value:   $old_val
                        })
                        WHERE prior <> ts
                        FOREACH (_ IN CASE WHEN prior IS NOT NULL THEN [1] ELSE [] END |
                            MERGE (ts)-[:SUPERSEDES]->(prior)
                        )
                        WITH ts
                        MATCH (m:Message {id: $msg_id})
                        MERGE (m)-[:EXTRACTED]->(ts)
                        """,
                        hid=human_id,
                        subj=item['subject'],
                        new_val=item['new_value'],
                        old_val=item['old_value'],
                        vfrom=item['valid_from'],
                        scope=scope,
                        msg_id=msg_id,
                    )
                except Exception as e:
                    logger.warning(
                        f"ASMR: _store_temporal failed for subject={item.get('subject')}: {e}"
                    )

    # ------------------------------------------------------------------
    # Vector 5: Updates (corrections) — process_supersedes() audit trail
    # ------------------------------------------------------------------

    def _store_updates(
        self, msg_id: str, human_id: str, items: list, scope: str
    ) -> None:
        """Process explicit corrections using the SUPERSEDES system.

        Creates a new Inference node for the corrected value, then calls
        process_supersedes() to find and retire conflicting prior facts
        and create the [:SUPERSEDES] audit edge with verbatim signal text.
        """
        with self.driver.session() as session:
            for item in items:
                if not item.get('corrects_field') or not item.get('new_value'):
                    continue
                try:
                    result = session.run(
                        """
                        CREATE (i:Inference {
                            id:         randomUUID(),
                            humanId:    $hid,
                            field:      $field,
                            value:      $new_val,
                            claim:      $hid + ' ' + $field + ': ' + $new_val,
                            confidence: 0.95,
                            superseded: false,
                            scope:      $scope,
                            sourceMsg:  $msg_id,
                            createdAt:  datetime(),
                            timestamp:  datetime()
                        })
                        WITH i
                        MATCH (m:Message {id: $msg_id})
                        MERGE (m)-[:EXTRACTED]->(i)
                        RETURN i.id AS id
                        """,
                        hid=human_id,
                        field=item['corrects_field'],
                        new_val=item['new_value'],
                        scope=scope,
                        msg_id=msg_id,
                    )
                    record = result.single()
                    if record and record['id']:
                        process_supersedes(
                            session,
                            human_id,
                            record['id'],
                            item['corrects_field'],
                            item['new_value'],
                            item.get('verbatim', ''),
                        )
                except Exception as e:
                    logger.warning(
                        f"ASMR: _store_updates failed for field={item.get('corrects_field')}: {e}"
                    )

    # ------------------------------------------------------------------
    # Vector 6: AssistantInstructions — MERGE as PersonalFact category=ASSISTANT_PREF
    # ------------------------------------------------------------------

    def _store_assistant_instructions(
        self, msg_id: str, human_id: str, items: list, scope: str
    ) -> None:
        """MERGE assistant instructions as PersonalFact with category='ASSISTANT_PREF'.

        Reuses the PersonalFact MERGE key (humanId, key) so a new instruction
        for the same preference key overwrites the old one in place.
        """
        with self.driver.session() as session:
            for item in items:
                try:
                    session.run(
                        """
                        MERGE (pf:Inference:PersonalFact {humanId: $hid, key: $key})
                        ON CREATE SET
                            pf.id         = randomUUID(),
                            pf.value      = $instruction,
                            pf.category   = 'ASSISTANT_PREF',
                            pf.active     = true,
                            pf.scope      = $scope,
                            pf.field      = $key,
                            pf.confidence = $conf,
                            pf.superseded = false,
                            pf.sourceMsg  = $msg_id,
                            pf.createdAt  = datetime(),
                            pf.timestamp  = datetime()
                        ON MATCH SET
                            pf.value      = $instruction,
                            pf.confidence = $conf,
                            pf.category   = 'ASSISTANT_PREF',
                            pf.sourceMsg  = $msg_id,
                            pf.updatedAt  = datetime()
                        WITH pf
                        MATCH (m:Message {id: $msg_id})
                        MERGE (m)-[:EXTRACTED]->(pf)
                        """,
                        hid=human_id,
                        key=item['key'],
                        instruction=item['instruction'],
                        scope=scope,
                        conf=item['confidence'],
                        msg_id=msg_id,
                    )
                except Exception as e:
                    logger.warning(
                        f"ASMR: _store_assistant_instructions failed for key={item.get('key')}: {e}"
                    )

    # ------------------------------------------------------------------
    # Status management
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Vector 7: Goals — MERGE on (humanId, title)
    # ------------------------------------------------------------------

    def _store_goals(
        self, msg_id: str, human_id: str, items: list, scope: str
    ) -> None:
        if not items:
            return
        with self.driver.session() as session:
            for item in items:
                title = item.get('title', '').strip()
                if not title:
                    continue
                try:
                    session.run("""
                        MERGE (g:Inference:Goal {humanId: $hid, title: $title})
                        ON CREATE SET
                            g.id = randomUUID(), g.status = $status,
                            g.domain = $domain, g.priority = $priority,
                            g.deadline = $deadline, g.blockers = $blockers,
                            g.scope = $scope, g.field = 'goal:' + $title,
                            g.value = $title, g.superseded = false,
                            g.active = true, g.sourceMsg = $msg_id,
                            g.createdAt = datetime(), g.timestamp = datetime()
                        ON MATCH SET
                            g.status = $status, g.priority = $priority,
                            g.deadline = $deadline, g.blockers = $blockers,
                            g.updatedAt = datetime()
                    """, hid=human_id, title=title, status=item.get('status', 'active'),
                         domain=item.get('domain', 'business'),
                         priority=item.get('priority', 'medium'),
                         deadline=item.get('deadline', ''),
                         blockers=item.get('blockers', []),
                         scope=scope, msg_id=msg_id)
                except Exception as e:
                    logger.warning(f"ASMR: _store_goals failed: {e}")

    # ------------------------------------------------------------------
    # Vector 10: RelationshipContext — MERGE on (humanId, person, nature)
    # ------------------------------------------------------------------

    def _store_relationships(
        self, msg_id: str, human_id: str, items: list, scope: str
    ) -> None:
        if not items:
            return
        with self.driver.session() as session:
            for item in items:
                person = item.get('person', '').strip()
                nature = item.get('nature', '').strip()
                if not person or not nature:
                    continue
                try:
                    session.run("""
                        MERGE (rc:Inference:RelationshipContext {
                            humanId: $hid, person: $person, nature: $nature
                        })
                        ON CREATE SET
                            rc.id = randomUUID(), rc.context = $context,
                            rc.active = $active, rc.scope = $scope,
                            rc.field = 'relationship:' + $person,
                            rc.value = $nature + ':' + $person,
                            rc.superseded = false, rc.sourceMsg = $msg_id,
                            rc.createdAt = datetime(), rc.timestamp = datetime()
                        ON MATCH SET
                            rc.context = $context, rc.active = $active,
                            rc.updatedAt = datetime()
                    """, hid=human_id, person=person, nature=nature,
                         context=item.get('context', ''),
                         active=item.get('active', True),
                         scope=scope, msg_id=msg_id)
                except Exception as e:
                    logger.warning(f"ASMR: _store_relationships failed: {e}")

    # ------------------------------------------------------------------
    # V14p: EmotionalCue — MERGE on (humanId, sourceMsg)
    # ------------------------------------------------------------------

    def _store_emotional_cue(
        self, msg_id: str, human_id: str, cue: str, scope: str
    ) -> None:
        """Store per-message emotional cue as :Inference:EmotionalCue."""
        if cue == 'neutral':
            return  # Don't store neutral — it's the default, saves space
        try:
            with self.driver.session() as session:
                session.run("""
                    MERGE (ec:Inference:EmotionalCue {humanId: $hid, sourceMsg: $msg_id})
                    ON CREATE SET
                        ec.id = randomUUID(), ec.cue = $cue,
                        ec.scope = $scope, ec.field = 'emotional_cue',
                        ec.value = $cue, ec.superseded = false,
                        ec.createdAt = datetime(), ec.timestamp = datetime()
                    ON MATCH SET
                        ec.cue = $cue, ec.updatedAt = datetime()
                """, hid=human_id, msg_id=msg_id, cue=cue, scope=scope)
        except Exception as e:
            logger.warning(f"ASMR: _store_emotional_cue failed: {e}")

    # ------------------------------------------------------------------
    # V16p: QuestionTag — CREATE per question
    # ------------------------------------------------------------------

    def _store_questions(
        self, msg_id: str, human_id: str, items: list, scope: str
    ) -> None:
        """Create QuestionTag nodes for each outbound question."""
        if not items:
            return
        with self.driver.session() as session:
            for item in items:
                q = item.get('question', '').strip()
                if not q:
                    continue
                try:
                    session.run("""
                        CREATE (qt:Inference:QuestionTag {
                            id: randomUUID(),
                            humanId: $hid,
                            question: $question,
                            expectingAnswer: $expecting,
                            status: 'open',
                            scope: $scope,
                            field: 'question',
                            value: $question,
                            superseded: false,
                            sourceMsg: $msg_id,
                            createdAt: datetime(),
                            timestamp: datetime()
                        })
                        WITH qt
                        MATCH (m:Message {id: $msg_id})
                        MERGE (m)-[:EXTRACTED]->(qt)
                    """, hid=human_id, question=q,
                         expecting=item.get('expecting_answer', True),
                         scope=scope, msg_id=msg_id)
                except Exception as e:
                    logger.warning(f"ASMR: _store_questions failed: {e}")

    def _mark_status(self, msg_id: str, status: str) -> None:
        """Advance Message.extractionStatus to the given value."""
        try:
            with self.driver.session() as session:
                session.run(
                    "MATCH (m:Message {id: $id}) SET m.extractionStatus = $status",
                    id=msg_id,
                    status=status,
                )
        except Exception as e:
            logger.error(f"ASMR: _mark_status failed for {msg_id[:8]} -> {status}: {e}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    )

    parser = argparse.ArgumentParser(
        description='ASMR 6-Vector Knowledge Extraction Worker',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=20,
        help='Maximum number of messages to process per run',
    )
    args = parser.parse_args()

    extractor = AsmrExtractor()
    try:
        result = extractor.process_pending(limit=args.limit)
        print(json.dumps(result))
        sys.exit(0 if result['errors'] == 0 else 1)
    finally:
        extractor.close()
