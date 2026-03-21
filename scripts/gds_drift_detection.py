#!/usr/bin/env python3
"""
GDS Drift Detection — Compare 30-day vs 180-day PageRank to find rising/fading topics.

Emits TemporalMarker nodes for significant interest shifts.
"""

import logging
import uuid
from typing import List, Dict, Any

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import neo4j_session

logger = logging.getLogger(__name__)

DRIFT_THRESHOLD = 0.3  # Minimum PageRank change to flag


def detect_drift(human_id: str) -> Dict[str, List[Dict[str, Any]]]:
    """Compare short-term vs long-term topic engagement.

    Returns:
        Dict with 'rising' and 'fading' topic lists
    """
    with neo4j_session() as session:
        # Short-term: messages in last 30 days
        result = session.run(
            """
            // 30-day topic frequency
            MATCH (h:Human {id: $human_id})-[:DISCUSSED]->(t:Topic)
            OPTIONAL MATCH (m:Message {humanId: $human_id})-[:HAS_TOPIC]->(t)
            WHERE m.timestamp > datetime() - duration('P30D')
            WITH t, count(m) AS recent

            // 180-day topic frequency
            OPTIONAL MATCH (m2:Message {humanId: $human_id})-[:HAS_TOPIC]->(t)
            WHERE m2.timestamp > datetime() - duration('P180D')
            WITH t, recent, count(m2) AS longterm

            WHERE longterm > 0
            WITH t, recent, longterm,
                 toFloat(recent) / toFloat(longterm) AS recentRatio,
                 toFloat(longterm - recent) / toFloat(longterm) AS fadeRatio
            RETURN t.label AS topic, t.id AS topicId,
                   recent, longterm, recentRatio, fadeRatio
            ORDER BY recentRatio DESC
            """,
            human_id=human_id,
        )

        rising = []
        fading = []

        for record in result:
            data = dict(record)
            recent = data["recent"]
            longterm = data["longterm"]

            if longterm <= 2:
                continue

            # Rising: high recent activity relative to long-term
            if data["recentRatio"] > 0.5 and recent >= 3:
                rising.append({
                    "topic": data["topic"],
                    "topicId": data["topicId"],
                    "recent": recent,
                    "longterm": longterm,
                    "signal": "rising",
                })

            # Fading: no recent activity despite long-term presence
            elif recent == 0 and longterm >= 3:
                fading.append({
                    "topic": data["topic"],
                    "topicId": data["topicId"],
                    "recent": recent,
                    "longterm": longterm,
                    "signal": "fading",
                })

        # Emit TemporalMarker nodes for significant shifts
        for item in rising + fading:
            session.run(
                """
                MATCH (t:Topic {id: $topic_id})
                CREATE (tm:TemporalMarker {
                    id: $marker_id,
                    humanId: $human_id,
                    signal: $signal,
                    topicLabel: $topic,
                    recentCount: $recent,
                    longtermCount: $longterm,
                    detectedAt: datetime()
                })
                CREATE (tm)-[:MARKS]->(t)
                """,
                marker_id=str(uuid.uuid4()),
                human_id=human_id,
                topic_id=item["topicId"],
                signal=item["signal"],
                topic=item["topic"],
                recent=item["recent"],
                longterm=item["longterm"],
            )

        logger.info(
            f"Drift detection for {human_id[:8]}: "
            f"{len(rising)} rising, {len(fading)} fading topics"
        )
        return {"rising": rising, "fading": fading}
