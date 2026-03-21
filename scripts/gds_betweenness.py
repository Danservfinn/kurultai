#!/usr/bin/env python3
"""
GDS Betweenness Centrality — Finds bridge topics between communities.

Bridge topics are key topics that connect different interest clusters,
indicating where conversations tend to pivot between subjects.
"""

import logging
from typing import List, Dict, Any

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import neo4j_session
from gds_projection_manager import GDSProjectionManager

logger = logging.getLogger(__name__)


def run_betweenness(human_id: str) -> List[Dict[str, Any]]:
    """Run betweenness centrality on a human's topic graph."""
    mgr = GDSProjectionManager()
    if not mgr.gds_available:
        return []

    try:
        if not mgr.ensure_projection(human_id):
            return []

        projection_name = mgr._projection_name(human_id)

        with neo4j_session() as session:
            result = session.run(
                """
                CALL gds.betweenness.stream($projection)
                YIELD nodeId, score
                WITH gds.util.asNode(nodeId) AS topic, score
                WHERE score > 0
                RETURN topic.label AS topicLabel, topic.id AS topicId, score
                ORDER BY score DESC
                """,
                projection=projection_name,
            )
            scores = [dict(r) for r in result]

            # Write scores back
            for item in scores:
                session.run(
                    """
                    MATCH (t:Topic {id: $topic_id})
                    SET t.betweenness_score = $score
                    """,
                    topic_id=item["topicId"],
                    score=item["score"],
                )

            logger.info(f"Betweenness: {len(scores)} bridge topics for {human_id[:8]}")
            return scores

    except Exception as e:
        logger.error(f"Betweenness failed for {human_id[:8]}: {e}")
        return []
    finally:
        mgr.close()


def get_bridge_topics(human_id: str, top_n: int = 5) -> List[Dict[str, Any]]:
    """Get the top bridge topics between communities."""
    with neo4j_session() as session:
        result = session.run(
            """
            MATCH (h:Human {id: $human_id})-[:DISCUSSED]->(t:Topic)
            WHERE t.betweenness_score IS NOT NULL AND t.betweenness_score > 0
            RETURN t.label AS topicLabel, t.betweenness_score AS score
            ORDER BY t.betweenness_score DESC
            LIMIT $n
            """,
            human_id=human_id,
            n=top_n,
        )
        return [dict(r) for r in result]
