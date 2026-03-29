#!/usr/bin/env python3
"""
asmr_deep_extractor.py — ASMR Deep Extraction Orchestrator.

Creates tasks for Jochi (Data Analyst) to extract heavyweight vectors
using claude-agent. Does NOT call LLM APIs directly.

Flow:
    1. Read asmr_config.json (enabled, frequency, cost cap)
    2. Find humans with new messages since last run
    3. For each human: create task via task_intake.py --agent jochi
    4. Store extraction results when tasks complete
    5. Update last_run_timestamp

Runs as a cron system-event every 4 hours.

Vectors extracted:
    V11: Implicit Beliefs (pattern inference)
    V13: Decision Patterns (meta-reasoning)
    V14: Emotional Triggers (pattern aggregation)
    V15: Knowledge Map (vocabulary analysis)
    V16: Unresolved Threads (cross-thread resolution)
    V17: Trust Map (delegation inference)

Usage:
    python3 asmr_deep_extractor.py
    python3 asmr_deep_extractor.py --limit 5
    python3 asmr_deep_extractor.py --dry-run
"""

import os
import sys
import json
import logging
import argparse
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import get_driver, close_driver
from asmr_schema_validator import validate_deep_extraction

logger = logging.getLogger(__name__)

CONFIG_PATH = Path.home() / ".openclaw" / "asmr_config.json"
TASK_INTAKE = Path(__file__).parent / "task_intake.py"
SCRIPTS_DIR = Path(__file__).parent

# ---------------------------------------------------------------------------
# Deep extraction prompt template
# ---------------------------------------------------------------------------

DEEP_EXTRACTION_PROMPT = """You are analyzing {human_name}'s communication patterns across {msg_count} messages from the last {hours} hours.

You have access to Neo4j. Query the messages for human {human_id} using:

```cypher
MATCH (m:Message {{humanId: '{human_id}', direction: 'inbound'}})
WHERE m.timestamp >= datetime('{since_ts}')
RETURN m.contentScrubbed AS text, toString(m.timestamp) AS ts, m.scope AS scope
ORDER BY m.timestamp ASC
```

After reading the messages, extract the following structured insights as a JSON object.
Only extract patterns supported by multiple messages or strong single signals.

{{
  "implicit_beliefs": [
    {{"belief": "...", "evidence_count": 1, "confidence": 0.0, "domain": "<technology|management|work-culture|personal|business>"}}
  ],
  "decision_patterns": [
    {{"pattern": "...", "domain": "<technology|management|work-culture|personal|business>", "evidence": "...", "confidence": 0.0}}
  ],
  "emotional_patterns": [
    {{"trigger": "...", "reaction": "<energized|frustrated|uncomfortable|boundary>", "context": "...", "evidence_count": 1}}
  ],
  "knowledge_levels": [
    {{"domain": "...", "level": "<expert|proficient|learning|aware|unknown>", "evidence": "...", "last_assessed": ""}}
  ],
  "unresolved_threads": [
    {{"topic": "...", "first_mentioned": "...", "status": "<dormant|active>", "related_goal": ""}}
  ],
  "trust_map": [
    {{"target": "...", "domain": "...", "trust_level": "<high|medium|low|none>", "evidence": "..."}}
  ]
}}

Return ONLY valid JSON. No markdown fences. No explanation."""


# ---------------------------------------------------------------------------
# Config management
# ---------------------------------------------------------------------------

def load_config() -> dict:
    """Load ASMR config, creating default if missing."""
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except Exception as e:
            logger.error(f"Config read error: {e}")

    default = {
        "qwen_tier": {
            "enabled": True,
            "frequency_minutes": 15,
            "model": "qwen3.5:9b",
            "vectors": [1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 14, 16],
        },
        "claude_tier": {
            "enabled": True,
            "frequency_minutes": 240,
            "agent": "jochi",
            "vectors": [11, 13, 14, 15, 16, 17],
            "delta_only": True,
            "cost_cap_daily_usd": 10.0,
            "cost_today_usd": 0.0,
            "last_run_timestamp": None,
        },
        "context_profile_v2": True,
    }
    save_config(default)
    return default


def save_config(config: dict) -> None:
    """Write config to disk."""
    try:
        CONFIG_PATH.write_text(json.dumps(config, indent=2))
    except Exception as e:
        logger.error(f"Config write error: {e}")


def should_run(config: dict) -> tuple[bool, str]:
    """Check if deep extraction should run now."""
    tier = config.get("claude_tier", {})

    if not tier.get("enabled", False):
        return False, "claude_tier disabled"

    # Check cost cap
    cost_today = tier.get("cost_today_usd", 0.0)
    cap = tier.get("cost_cap_daily_usd", 10.0)
    if cost_today >= cap:
        return False, f"cost cap reached ({cost_today:.2f} >= {cap:.2f})"

    # Check frequency
    last_run = tier.get("last_run_timestamp")
    if last_run:
        try:
            last_dt = datetime.fromisoformat(last_run)
            freq_min = tier.get("frequency_minutes", 240)
            elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds() / 60
            if elapsed < freq_min:
                return False, f"too soon ({elapsed:.0f}m < {freq_min}m)"
        except Exception:
            pass  # Invalid timestamp, allow run

    return True, "ok"


# ---------------------------------------------------------------------------
# Neo4j queries
# ---------------------------------------------------------------------------

def get_humans_with_new_messages(driver, since_ts: Optional[str]) -> List[Dict[str, Any]]:
    """Find humans with inbound messages since last run."""
    if since_ts:
        query = """
            MATCH (m:Message {direction: 'inbound'})
            WHERE m.timestamp >= datetime($since)
            WITH DISTINCT m.humanId AS hid, count(m) AS msg_count
            WHERE hid IS NOT NULL
            MATCH (h:Human {id: hid})
            RETURN h.id AS human_id,
                   coalesce(h.displayName, h.name, 'Unknown') AS name,
                   msg_count
            ORDER BY msg_count DESC
        """
        params = {"since": since_ts}
    else:
        # First run — process last 24 hours
        query = """
            MATCH (m:Message {direction: 'inbound'})
            WHERE m.timestamp >= datetime() - duration('P1D')
            WITH DISTINCT m.humanId AS hid, count(m) AS msg_count
            WHERE hid IS NOT NULL
            MATCH (h:Human {id: hid})
            RETURN h.id AS human_id,
                   coalesce(h.displayName, h.name, 'Unknown') AS name,
                   msg_count
            ORDER BY msg_count DESC
        """
        params = {}

    with driver.session() as s:
        result = s.run(query, **params)
        return [dict(r) for r in result]


def check_pending_deep_tasks(driver) -> List[str]:
    """Check for already-pending deep extraction tasks to avoid duplicates."""
    with driver.session() as s:
        result = s.run("""
            MATCH (t:Task)
            WHERE t.source = 'asmr-deep-cron'
              AND t.status IN ['PENDING', 'WORKING']
            RETURN t.task_id AS tid
        """)
        return [r['tid'] for r in result]


# ---------------------------------------------------------------------------
# Task creation
# ---------------------------------------------------------------------------

def create_deep_task(human_id: str, human_name: str, msg_count: int,
                     since_ts: str, agent: str = "jochi") -> Optional[str]:
    """Create a deep extraction task for one human via task_intake.py."""
    hours = 4  # default window
    if since_ts:
        try:
            since_dt = datetime.fromisoformat(since_ts)
            hours = max(1, int((datetime.now(timezone.utc) - since_dt).total_seconds() / 3600))
        except Exception:
            pass

    prompt = DEEP_EXTRACTION_PROMPT.format(
        human_name=human_name,
        human_id=human_id,
        msg_count=msg_count,
        hours=hours,
        since_ts=since_ts or datetime.now(timezone.utc).isoformat(),
    )

    title = f"ASMR Deep Extraction: {human_name} ({msg_count} msgs)"

    try:
        cmd = [
            sys.executable, str(TASK_INTAKE),
            "--title", title,
            "--body", prompt,
            "--agent", agent,
            "--priority", "normal",
            "--source", "asmr-deep-cron",
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
            cwd=str(SCRIPTS_DIR),
        )
        if result.returncode == 0:
            # Try to extract task_id from output
            output = result.stdout.strip()
            logger.info(f"Deep task created for {human_name}: {output[:100]}")
            return output
        else:
            logger.error(f"task_intake failed: {result.stderr[:200]}")
            return None
    except Exception as e:
        logger.error(f"Failed to create task for {human_name}: {e}")
        return None


# ---------------------------------------------------------------------------
# Result storage (called on subsequent runs when tasks complete)
# ---------------------------------------------------------------------------

def process_completed_tasks(driver) -> int:
    """Find completed deep extraction tasks and store their results."""
    with driver.session() as s:
        result = s.run("""
            MATCH (t:Task)
            WHERE t.source = 'asmr-deep-cron'
              AND t.status = 'COMPLETED'
              AND NOT coalesce(t.asmr_processed, false)
            OPTIONAL MATCH (t)-[:HAS_OUTPUT]->(o:TaskOutput)
            RETURN t.task_id AS tid, t.title AS title,
                   coalesce(o.text, o.content, '') AS output
            LIMIT 10
        """)
        tasks = [dict(r) for r in result]

    stored = 0
    for task in tasks:
        try:
            output_text = task.get('output', '')
            if not output_text:
                logger.warning(f"Deep task {task['tid']}: no output, skipping")
                _mark_processed(driver, task['tid'])
                continue

            # Parse JSON from output
            parsed = _parse_deep_output(output_text)
            if not parsed:
                logger.warning(f"Deep task {task['tid']}: couldn't parse output")
                _mark_processed(driver, task['tid'])
                continue

            # Extract human_id from task title
            # Title format: "ASMR Deep Extraction: Name (N msgs)"
            # We need to find the human from the task context
            human_id = _extract_human_id_from_task(driver, task['tid'])
            if not human_id:
                logger.warning(f"Deep task {task['tid']}: couldn't determine human_id")
                _mark_processed(driver, task['tid'])
                continue

            # Validate and store
            cleaned, warnings = validate_deep_extraction(parsed)
            for w in warnings:
                logger.info(f"Deep validation [{task['tid'][:12]}]: {w}")

            _store_deep_vectors(driver, human_id, cleaned)
            _mark_processed(driver, task['tid'])
            stored += 1
            logger.info(f"Deep extraction stored for task {task['tid'][:12]}")

        except Exception as e:
            logger.error(f"Deep task processing failed for {task.get('tid')}: {e}")
            _mark_processed(driver, task.get('tid', ''))

    return stored


def _parse_deep_output(text: str) -> Optional[dict]:
    """Extract JSON from claude-agent output text."""
    import re

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON block in output
    json_match = re.search(r'\{[\s\S]*"implicit_beliefs"[\s\S]*\}', text)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    # Try markdown fence
    fence_match = re.search(r'```(?:json)?\s*\n([\s\S]*?)```', text)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            pass

    return None


def _extract_human_id_from_task(driver, task_id: str) -> Optional[str]:
    """Try to extract human_id from the task body."""
    with driver.session() as s:
        result = s.run("""
            MATCH (t:Task {task_id: $tid})
            RETURN t.body AS body
        """, tid=task_id).single()

    if not result or not result['body']:
        return None

    import re
    # Look for humanId pattern in the prompt
    match = re.search(r"humanId:\s*'([^']+)'", result['body'])
    if match:
        return match.group(1)

    match = re.search(r"human\s+([a-f0-9-]{36})", result['body'])
    if match:
        return match.group(1)

    return None


def _mark_processed(driver, task_id: str) -> None:
    """Mark a deep extraction task as processed."""
    try:
        with driver.session() as s:
            s.run(
                "MATCH (t:Task {task_id: $tid}) SET t.asmr_processed = true",
                tid=task_id,
            )
    except Exception as e:
        logger.warning(f"Failed to mark task {task_id} as processed: {e}")


def _store_deep_vectors(driver, human_id: str, cleaned: dict) -> None:
    """Store all deep vectors as multi-label Inference nodes."""
    with driver.session() as s:
        # V11: Implicit Beliefs
        for item in cleaned.get('implicit_beliefs', []):
            try:
                s.run("""
                    MERGE (b:Inference:ImplicitBelief {humanId: $hid, belief: $belief})
                    ON CREATE SET
                        b.id = randomUUID(), b.evidenceCount = $ecount,
                        b.confidence = $conf, b.domain = $domain,
                        b.scope = 'deep', b.field = 'belief',
                        b.value = $belief, b.superseded = false,
                        b.createdAt = datetime(), b.timestamp = datetime()
                    ON MATCH SET
                        b.evidenceCount = $ecount, b.confidence = $conf,
                        b.domain = $domain, b.updatedAt = datetime()
                """, hid=human_id, belief=item['belief'],
                     ecount=item.get('evidence_count', 1),
                     conf=item.get('confidence', 0.5),
                     domain=item.get('domain', 'business'))
            except Exception as e:
                logger.warning(f"Store belief failed: {e}")

        # V13: Decision Patterns
        for item in cleaned.get('decision_patterns', []):
            try:
                s.run("""
                    MERGE (d:Inference:DecisionPattern {humanId: $hid, pattern: $pattern})
                    ON CREATE SET
                        d.id = randomUUID(), d.domain = $domain,
                        d.evidence = $evidence, d.confidence = $conf,
                        d.scope = 'deep', d.field = 'decision_pattern',
                        d.value = $pattern, d.superseded = false,
                        d.createdAt = datetime(), d.timestamp = datetime()
                    ON MATCH SET
                        d.evidence = $evidence, d.confidence = $conf,
                        d.domain = $domain, d.updatedAt = datetime()
                """, hid=human_id, pattern=item['pattern'],
                     domain=item.get('domain', 'business'),
                     evidence=item.get('evidence', ''),
                     conf=item.get('confidence', 0.5))
            except Exception as e:
                logger.warning(f"Store decision pattern failed: {e}")

        # V14: Emotional Triggers
        for item in cleaned.get('emotional_patterns', []):
            try:
                s.run("""
                    MERGE (et:Inference:EmotionalTrigger {humanId: $hid, trigger: $trigger})
                    ON CREATE SET
                        et.id = randomUUID(), et.reaction = $reaction,
                        et.context = $context, et.evidenceCount = $ecount,
                        et.scope = 'deep', et.field = 'emotional_trigger',
                        et.value = $trigger, et.superseded = false,
                        et.createdAt = datetime(), et.timestamp = datetime()
                    ON MATCH SET
                        et.reaction = $reaction, et.context = $context,
                        et.evidenceCount = $ecount, et.updatedAt = datetime()
                """, hid=human_id, trigger=item['trigger'],
                     reaction=item.get('reaction', 'neutral'),
                     context=item.get('context', ''),
                     ecount=item.get('evidence_count', 1))
            except Exception as e:
                logger.warning(f"Store emotional trigger failed: {e}")

        # V15: Knowledge Levels
        for item in cleaned.get('knowledge_levels', []):
            try:
                s.run("""
                    MERGE (k:Inference:KnowledgeLevel {humanId: $hid, domain: $domain})
                    ON CREATE SET
                        k.id = randomUUID(), k.level = $level,
                        k.evidence = $evidence, k.lastAssessed = $assessed,
                        k.scope = 'deep', k.field = 'knowledge_level',
                        k.value = $domain + ':' + $level,
                        k.superseded = false,
                        k.createdAt = datetime(), k.timestamp = datetime()
                    ON MATCH SET
                        k.level = $level, k.evidence = $evidence,
                        k.lastAssessed = $assessed, k.updatedAt = datetime()
                """, hid=human_id, domain=item['domain'],
                     level=item.get('level', 'unknown'),
                     evidence=item.get('evidence', ''),
                     assessed=item.get('last_assessed', ''))
            except Exception as e:
                logger.warning(f"Store knowledge level failed: {e}")

        # V16: Unresolved Threads
        for item in cleaned.get('unresolved_threads', []):
            try:
                s.run("""
                    MERGE (u:Inference:UnresolvedThread {humanId: $hid, topic: $topic})
                    ON CREATE SET
                        u.id = randomUUID(), u.firstMentioned = $first,
                        u.status = $status, u.relatedGoal = $goal,
                        u.scope = 'deep', u.field = 'unresolved_thread',
                        u.value = $topic, u.superseded = false,
                        u.createdAt = datetime(), u.timestamp = datetime()
                    ON MATCH SET
                        u.status = $status, u.relatedGoal = $goal,
                        u.updatedAt = datetime()
                """, hid=human_id, topic=item['topic'],
                     first=item.get('first_mentioned', ''),
                     status=item.get('status', 'active'),
                     goal=item.get('related_goal', ''))
            except Exception as e:
                logger.warning(f"Store unresolved thread failed: {e}")

        # V17: Trust Map
        for item in cleaned.get('trust_map', []):
            try:
                s.run("""
                    MERGE (tm:Inference:TrustMap {humanId: $hid, target: $target, domain: $domain})
                    ON CREATE SET
                        tm.id = randomUUID(), tm.trustLevel = $level,
                        tm.evidence = $evidence,
                        tm.scope = 'deep', tm.field = 'trust',
                        tm.value = $target + ':' + $domain + ':' + $level,
                        tm.superseded = false,
                        tm.createdAt = datetime(), tm.timestamp = datetime()
                    ON MATCH SET
                        tm.trustLevel = $level, tm.evidence = $evidence,
                        tm.updatedAt = datetime()
                """, hid=human_id, target=item['target'],
                     domain=item.get('domain', 'general'),
                     level=item.get('trust_level', 'medium'),
                     evidence=item.get('evidence', ''))
            except Exception as e:
                logger.warning(f"Store trust map failed: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="ASMR Deep Extraction Orchestrator")
    parser.add_argument("--limit", type=int, default=10, help="Max humans to process")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    args = parser.parse_args()

    config = load_config()

    # Check if we should run
    ok, reason = should_run(config)
    if not ok:
        logger.info(f"Deep extraction skipped: {reason}")
        return

    driver = get_driver()
    try:
        # First: process any completed deep tasks from prior runs
        stored = process_completed_tasks(driver)
        if stored:
            logger.info(f"Stored results from {stored} completed deep task(s)")

        # Check for already-pending tasks
        pending = check_pending_deep_tasks(driver)
        if pending:
            logger.info(f"Skipping: {len(pending)} deep task(s) still pending/working")
            return

        # Find humans with new messages
        since_ts = config.get("claude_tier", {}).get("last_run_timestamp")
        humans = get_humans_with_new_messages(driver, since_ts)

        if not humans:
            logger.info("No humans with new messages since last run")
            config["claude_tier"]["last_run_timestamp"] = datetime.now(timezone.utc).isoformat()
            save_config(config)
            return

        logger.info(f"Found {len(humans)} human(s) with new messages")

        agent = config.get("claude_tier", {}).get("agent", "jochi")
        created = 0

        for human in humans[:args.limit]:
            if args.dry_run:
                logger.info(f"[DRY RUN] Would create task for {human['name']} ({human['msg_count']} msgs)")
                continue

            task_output = create_deep_task(
                human_id=human['human_id'],
                human_name=human['name'],
                msg_count=human['msg_count'],
                since_ts=since_ts or "",
                agent=agent,
            )
            if task_output:
                created += 1

        if not args.dry_run:
            config["claude_tier"]["last_run_timestamp"] = datetime.now(timezone.utc).isoformat()
            save_config(config)

        logger.info(f"Deep extraction: created {created} task(s) for {agent}")

    finally:
        close_driver()


if __name__ == "__main__":
    main()
