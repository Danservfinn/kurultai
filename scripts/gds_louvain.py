#!/usr/bin/env python3
"""
GDS Louvain Community Detection — Finds topic interest communities per human.

Stores communityId on Topic nodes via DISCUSSED relationship properties.
"""

import logging
from typing import Optional, Dict, Any, List

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import neo4j_session
from gds_projection_manager import GDSProjectionManager

logger = logging.getLogger(__name__)


def run_louvain(human_id: str) -> List[Dict[str, Any]]:
    """Run Louvain community detection on a human's topic graph."""
    mgr = GDSProjectionManager()
    if not mgr.gds_available:
        return _fallback_communities(human_id)

    try:
        if not mgr.ensure_projection(human_id):
            return _fallback_communities(human_id)

        projection_name = mgr._projection_name(human_id)

        with neo4j_session() as session:
            result = session.run(
                """
                CALL gds.louvain.stream($projection, {relationshipWeightProperty: 'weight'})
                YIELD nodeId, communityId
                WITH gds.util.asNode(nodeId) AS topic, communityId
                RETURN topic.label AS topicLabel, topic.id AS topicId, communityId
                ORDER BY communityId, topicLabel
                """,
                projection=projection_name,
            )
            communities = [dict(r) for r in result]

            # Write community IDs back
            for item in communities:
                session.run(
                    """
                    MATCH (h:Human {id: $human_id})-[d:DISCUSSED]->(t:Topic {id: $topic_id})
                    SET d.communityId = $community_id
                    """,
                    human_id=human_id,
                    topic_id=item["topicId"],
                    community_id=item["communityId"],
                )

            logger.info(f"Louvain: {len(communities)} topics in communities for {human_id[:8]}")
            return communities

    except Exception as e:
        logger.error(f"Louvain failed for {human_id[:8]}: {e}")
        return _fallback_communities(human_id)
    finally:
        mgr.close()


def _fallback_communities(human_id: str) -> List[Dict[str, Any]]:
    """Domain-based fallback when GDS is unavailable."""
    with neo4j_session() as session:
        result = session.run(
            """
            MATCH (h:Human {id: $human_id})-[:DISCUSSED]->(t:Topic)
            RETURN t.label AS topicLabel, t.id AS topicId,
                   coalesce(t.domain, 'general') AS communityId
            ORDER BY t.domain, t.label
            """,
            human_id=human_id,
        )
        return [dict(r) for r in result]


def get_communities(human_id: str) -> Dict[str, List[str]]:
    """Get topic communities as a dict of communityId → [topicLabels]."""
    with neo4j_session() as session:
        result = session.run(
            """
            MATCH (h:Human {id: $human_id})-[d:DISCUSSED]->(t:Topic)
            WHERE d.communityId IS NOT NULL
            RETURN d.communityId AS communityId, collect(t.label) AS topics
            ORDER BY size(collect(t.label)) DESC
            """,
            human_id=human_id,
        )
        return {str(r["communityId"]): r["topics"] for r in result}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("human_id")
    args = parser.parse_args()
    result = run_louvain(args.human_id)
    print(f"Communities for {args.human_id[:8]}: {len(result)} topics")
    for r in result:
        print(f"  [{r['communityId']}] {r['topicLabel']}")
