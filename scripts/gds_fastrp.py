#!/usr/bin/env python3
"""
GDS FastRP — Generates structural graph embeddings (128d) for topic nodes.

FastRP captures the structural position of topics in the co-occurrence graph,
complementing semantic (nomic-embed-text) embeddings with structural signal.
"""

import logging
from typing import List, Dict, Any

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import neo4j_session
from gds_projection_manager import GDSProjectionManager

logger = logging.getLogger(__name__)

FASTRP_DIM = 128


def run_fastrp(human_id: str) -> List[Dict[str, Any]]:
    """Run FastRP on a human's topic graph and store embeddings."""
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
                CALL gds.fastRP.stream($projection, {
                    embeddingDimension: $dim,
                    relationshipWeightProperty: 'weight',
                    iterationWeights: [0.0, 1.0, 1.0, 0.8]
                })
                YIELD nodeId, embedding
                WITH gds.util.asNode(nodeId) AS topic, embedding
                SET topic.structuralEmbedding = embedding
                RETURN topic.label AS topicLabel, topic.id AS topicId
                """,
                projection=projection_name,
                dim=FASTRP_DIM,
            )
            topics = [dict(r) for r in result]
            logger.info(f"FastRP: {len(topics)} topic embeddings for {human_id[:8]}")
            return topics

    except Exception as e:
        logger.error(f"FastRP failed for {human_id[:8]}: {e}")
        return []
    finally:
        mgr.close()
