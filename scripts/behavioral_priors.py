#!/usr/bin/env python3
"""
Behavioral Priors — Per-human communication style computed from engagement history.

After 30+ interactions, computes a communication_style object from
engagement decision history. Injected into LLM assessment context.
"""

import json
import logging
from typing import Optional, Dict, Any

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import neo4j_session

logger = logging.getLogger(__name__)

MIN_INTERACTIONS = 30


def compute_behavioral_priors(human_id: str) -> Optional[Dict[str, Any]]:
    """Compute communication style from engagement history.

    Returns None if < 30 interactions.
    """
    with neo4j_session() as session:
        # Count interactions
        count_result = session.run(
            "MATCH (m:Message {humanId: $human_id, direction: 'inbound'}) RETURN count(m) AS cnt",
            human_id=human_id,
        ).single()

        total = count_result["cnt"] if count_result else 0
        if total < MIN_INTERACTIONS:
            return None

        # Average message length
        length_result = session.run(
            """
            MATCH (m:Message {humanId: $human_id, direction: 'inbound'})
            WHERE m.contentScrubbed IS NOT NULL
            RETURN avg(size(m.contentScrubbed)) AS avgLength,
                   percentileDisc(size(m.contentScrubbed), 0.5) AS medianLength
            """,
            human_id=human_id,
        ).single()

        avg_length = length_result["avgLength"] if length_result else 0
        median_length = length_result["medianLength"] if length_result else 0

        # Sentiment distribution
        sentiment_result = session.run(
            """
            MATCH (m:Message {humanId: $human_id, direction: 'inbound'})
            WHERE m.sentiment IS NOT NULL
            WITH m, m.sentiment AS raw
            WITH CASE
                WHEN raw CONTAINS '"positive"' THEN 'positive'
                WHEN raw CONTAINS '"negative"' THEN 'negative'
                ELSE 'neutral'
            END AS valence
            RETURN valence, count(*) AS cnt
            """,
            human_id=human_id,
        )
        sentiment_dist = {r["valence"]: r["cnt"] for r in sentiment_result}

        # Question frequency
        question_result = session.run(
            """
            MATCH (m:Message {humanId: $human_id, direction: 'inbound'})
            WHERE m.contentScrubbed CONTAINS '?'
            RETURN count(m) AS questions
            """,
            human_id=human_id,
        ).single()
        questions = question_result["questions"] if question_result else 0

        # Response time distribution (how fast they follow up)
        response_result = session.run(
            """
            MATCH (m1:Message {humanId: $human_id, direction: 'inbound'})
            MATCH (m2:Message {humanId: $human_id, direction: 'inbound'})
            WHERE m2.timestamp > m1.timestamp
              AND duration.between(m1.timestamp, m2.timestamp).minutes < 60
            WITH duration.between(m1.timestamp, m2.timestamp).minutes AS gap
            RETURN avg(gap) AS avgGap, percentileDisc(gap, 0.5) AS medianGap
            """,
            human_id=human_id,
        ).single()

        avg_gap = response_result["avgGap"] if response_result else None

        # Engagement decision accuracy
        accuracy_result = session.run(
            """
            MATCH (m:Message {humanId: $human_id})
            WHERE m.engagementOutcome IS NOT NULL
            RETURN m.engagementOutcome AS outcome, count(*) AS cnt
            """,
            human_id=human_id,
        )
        outcomes = {r["outcome"]: r["cnt"] for r in accuracy_result}

    # Determine communication style
    style = "terse" if median_length < 20 else "verbose" if median_length > 200 else "moderate"
    question_ratio = questions / total if total > 0 else 0
    dominant_sentiment = max(sentiment_dist, key=sentiment_dist.get) if sentiment_dist else "neutral"

    priors = {
        "total_interactions": total,
        "communication_style": style,
        "avg_message_length": round(avg_length or 0),
        "median_message_length": round(median_length or 0),
        "question_frequency": round(question_ratio, 2),
        "dominant_sentiment": dominant_sentiment,
        "sentiment_distribution": sentiment_dist,
        "avg_followup_gap_minutes": round(avg_gap or 0),
        "engagement_outcomes": outcomes,
    }

    # Store on Human node
    with neo4j_session() as session:
        session.run(
            """
            MATCH (h:Human {id: $human_id})
            SET h.communicationStyle = $style_json,
                h.priorsComputedAt = datetime()
            """,
            human_id=human_id,
            style_json=json.dumps(priors),
        )

    return priors
