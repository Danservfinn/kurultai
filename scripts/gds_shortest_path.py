#!/usr/bin/env python3
"""
GDS Shortest Path — Traces interest evolution via LED_TO edges.

Uses Dijkstra to find how topics connect through temporal flow,
revealing the narrative path between two topics in a human's history.
"""

import logging
from typing import List, Dict, Any, Optional

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import neo4j_session

logger = logging.getLogger(__name__)


def find_topic_path(
    human_id: str, topic_from: str, topic_to: str
) -> Optional[Dict[str, Any]]:
    """Find the shortest narrative path between two topics via LED_TO edges.

    Args:
        human_id: Human UUID (for scoping)
        topic_from: Starting topic label
        topic_to: Ending topic label

    Returns:
        Dict with path (topic labels) and total weight, or None
    """
    with neo4j_session() as session:
        result = session.run(
            """
            MATCH (h:Human {id: $human_id})-[:DISCUSSED]->(t1:Topic {label: $from})
            MATCH (h)-[:DISCUSSED]->(t2:Topic {label: $to})
            CALL {
                WITH t1, t2
                MATCH path = shortestPath((t1)-[:LED_TO*1..10]->(t2))
                RETURN path, reduce(w = 0, r IN relationships(path) | w + coalesce(r.count, 1)) AS weight
            }
            RETURN [n IN nodes(path) | n.label] AS topicPath, weight
            ORDER BY weight DESC
            LIMIT 1
            """,
            human_id=human_id,
            **{"from": topic_from, "to": topic_to},
        )
        record = result.single()
        if not record:
            return None
        return {
            "path": record["topicPath"],
            "weight": record["weight"],
            "from": topic_from,
            "to": topic_to,
        }


def find_interest_evolution(human_id: str, topic_label: str, depth: int = 5) -> List[Dict[str, Any]]:
    """Find what topics evolved from a given topic via LED_TO.

    Returns the downstream topic chain.
    """
    with neo4j_session() as session:
        result = session.run(
            """
            MATCH (h:Human {id: $human_id})-[:DISCUSSED]->(start:Topic {label: $label})
            MATCH path = (start)-[:LED_TO*1..{depth}]->(downstream:Topic)
            WHERE (h)-[:DISCUSSED]->(downstream)
            RETURN downstream.label AS topic,
                   length(path) AS distance,
                   [r IN relationships(path) | coalesce(r.count, 1)] AS weights
            ORDER BY distance
            """.replace("{depth}", str(depth)),
            human_id=human_id,
            label=topic_label,
        )
        return [dict(r) for r in result]
