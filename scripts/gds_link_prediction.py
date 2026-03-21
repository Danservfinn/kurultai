#!/usr/bin/env python3
"""
GDS Link Prediction — Predicts next topic connections using Adamic-Adar.

Identifies topics likely to be discussed together in the future,
enabling proactive context preparation.
"""

import logging
from typing import List, Dict, Any

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import neo4j_session
from gds_projection_manager import GDSProjectionManager

logger = logging.getLogger(__name__)


def run_link_prediction(human_id: str, top_n: int = 10) -> List[Dict[str, Any]]:
    """Predict future topic co-occurrences using Adamic-Adar index."""
    mgr = GDSProjectionManager()
    if not mgr.gds_available:
        return []

    try:
        if not mgr.ensure_projection(human_id):
            return []

        # Use Cypher-based Adamic-Adar (works without named projection)
        with neo4j_session() as session:
            result = session.run(
                """
                MATCH (h:Human {id: $human_id})-[:DISCUSSED]->(t1:Topic)
                MATCH (h)-[:DISCUSSED]->(t2:Topic)
                WHERE t1 <> t2 AND NOT exists((t1)-[:CO_OCCURRED]-(t2))
                WITH t1, t2
                OPTIONAL MATCH (t1)-[:CO_OCCURRED]-(shared:Topic)-[:CO_OCCURRED]-(t2)
                WITH t1, t2, collect(shared) AS sharedTopics
                WHERE size(sharedTopics) > 0
                WITH t1, t2, reduce(score = 0.0, s IN sharedTopics |
                    score + 1.0 / log(2.0 + size((s)-[:CO_OCCURRED]-()))
                ) AS adamicAdar
                WHERE adamicAdar > 0
                RETURN t1.label AS topic1, t2.label AS topic2, adamicAdar AS score
                ORDER BY adamicAdar DESC
                LIMIT $n
                """,
                human_id=human_id,
                n=top_n,
            )
            predictions = [dict(r) for r in result]
            logger.info(f"Link prediction: {len(predictions)} pairs for {human_id[:8]}")
            return predictions

    except Exception as e:
        logger.error(f"Link prediction failed for {human_id[:8]}: {e}")
        return []
    finally:
        mgr.close()
