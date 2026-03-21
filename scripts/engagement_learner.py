#!/usr/bin/env python3
"""
Engagement Learner — Stores engagement decisions and infers outcomes.

Implements behavioral proxy labeling: 10-15 minutes after a decision,
checks if the human responded (positive outcome) or went silent (negative).
"""

import logging
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import neo4j_session

logger = logging.getLogger(__name__)


def store_engagement_decision(
    message_id: str, human_id: str, decision: Dict[str, Any]
) -> bool:
    """Store an engagement decision on the Message node."""
    with neo4j_session() as session:
        result = session.run(
            """
            MATCH (m:Message {id: $msg_id})
            SET m.engagementDecision = $decision,
                m.engagementSource = $source,
                m.engagementDecidedAt = datetime()
            RETURN m.id AS id
            """,
            msg_id=message_id,
            decision=json.dumps(decision),
            source=decision.get("source", "unknown"),
        )
        return result.single() is not None


def infer_outcomes(human_id: str, window_minutes: int = 15) -> Dict[str, int]:
    """Infer engagement decision outcomes via behavioral proxy.

    For each message with an engagement decision from > window_minutes ago:
    - If human responded within window → outcome = "positive"
    - If human went silent → outcome = "negative" (for "respond" decisions)
    - If Kublai stayed silent and human continued → outcome = "positive" (for "silent")
    """
    results = {"positive": 0, "negative": 0, "neutral": 0}

    with neo4j_session() as session:
        # Find messages with decisions but no outcome yet
        pending = session.run(
            """
            MATCH (m:Message {humanId: $human_id})
            WHERE m.engagementDecision IS NOT NULL
              AND m.engagementOutcome IS NULL
              AND m.timestamp < datetime() - duration('PT' + $window + 'M')
            RETURN m.id AS id, m.engagementDecision AS decision,
                   m.direction AS direction, m.timestamp AS timestamp
            ORDER BY m.timestamp ASC
            LIMIT 50
            """,
            human_id=human_id,
            window=str(window_minutes),
        )

        for record in pending:
            msg_id = record["id"]
            decision = json.loads(record["decision"]) if isinstance(record["decision"], str) else record["decision"]
            msg_time = record["timestamp"]
            chose_respond = decision.get("decision") == "respond"

            # Check if human sent a follow-up within the window
            follow_up = session.run(
                """
                MATCH (m:Message {humanId: $human_id})
                WHERE m.direction = 'inbound'
                  AND m.timestamp > $after
                  AND m.timestamp < $after + duration('PT' + $window + 'M')
                  AND m.id <> $msg_id
                RETURN count(m) AS count
                """,
                human_id=human_id,
                after=msg_time,
                window=str(window_minutes),
                msg_id=msg_id,
            ).single()

            human_continued = (follow_up["count"] if follow_up else 0) > 0

            if chose_respond and human_continued:
                outcome = "positive"
            elif chose_respond and not human_continued:
                outcome = "neutral"  # Responded but human went quiet (expected?)
            elif not chose_respond and human_continued:
                outcome = "negative"  # Stayed silent but human wanted attention
            else:
                outcome = "positive"  # Silent decision, human also silent — correct

            # Store outcome
            session.run(
                """
                MATCH (m:Message {id: $msg_id})
                SET m.engagementOutcome = $outcome,
                    m.engagementOutcomeAt = datetime()
                """,
                msg_id=msg_id,
                outcome=outcome,
            )
            results[outcome] += 1

    logger.info(f"Inferred {sum(results.values())} outcomes for {human_id[:8]}: {results}")
    return results


def get_decision_accuracy(human_id: str, days: int = 30) -> Dict[str, Any]:
    """Compute engagement decision accuracy over a time window."""
    with neo4j_session() as session:
        result = session.run(
            """
            MATCH (m:Message {humanId: $human_id})
            WHERE m.engagementOutcome IS NOT NULL
              AND m.timestamp > datetime() - duration('P' + $days + 'D')
            WITH m.engagementOutcome AS outcome, count(*) AS cnt
            RETURN outcome, cnt
            """,
            human_id=human_id,
            days=str(days),
        )
        counts = {r["outcome"]: r["cnt"] for r in result}

    total = sum(counts.values())
    if total == 0:
        return {"total": 0, "accuracy": None}

    positive = counts.get("positive", 0)
    negative = counts.get("negative", 0)

    return {
        "total": total,
        "positive": positive,
        "negative": negative,
        "neutral": counts.get("neutral", 0),
        "accuracy": round(positive / total, 3) if total else None,
        "fn_rate": round(negative / total, 3) if total else None,
    }
