#!/usr/bin/env python3
"""
GDS Social Network — Connected components on KNOWN_THROUGH/RELATED_TO graph.

Finds social clusters among humans to understand group dynamics.
"""
from __future__ import annotations

import logging
from typing import List, Dict, Any

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import neo4j_session
from gds_projection_manager import GDSProjectionManager

logger = logging.getLogger(__name__)


def run_connected_components() -> List[Dict[str, Any]]:
    """Find connected components in the human social graph."""
    mgr = GDSProjectionManager()

    if not mgr.gds_available:
        return _fallback_social_clusters()

    try:
        # Create social projection
        dummy_id = "global"
        mgr.create_projection(dummy_id, "social")
        projection_name = mgr._projection_name(dummy_id, "social")

        with neo4j_session() as session:
            result = session.run(
                """
                CALL gds.wcc.stream($projection)
                YIELD nodeId, componentId
                WITH gds.util.asNode(nodeId) AS human, componentId
                RETURN componentId,
                       collect(human.displayName) AS members,
                       count(*) AS size
                ORDER BY size DESC
                """,
                projection=projection_name,
            )
            components = [dict(r) for r in result]

            # Write componentId back to Human nodes
            for comp in components:
                for name in comp["members"]:
                    session.run(
                        """
                        MATCH (h:Human {displayName: $name})
                        SET h.socialCluster = $comp_id
                        """,
                        name=name,
                        comp_id=comp["componentId"],
                    )

            logger.info(f"Social network: {len(components)} clusters")
            return components

    except Exception as e:
        logger.error(f"Connected components failed: {e}")
        return _fallback_social_clusters()
    finally:
        mgr.drop_projection("global", "social")
        mgr.close()


def _fallback_social_clusters() -> List[Dict[str, Any]]:
    """Fallback: group by KNOWN_THROUGH traversal."""
    with neo4j_session() as session:
        result = session.run(
            """
            MATCH (h:Human {status: 'active'})
            OPTIONAL MATCH (h)-[:KNOWN_THROUGH|RELATED_TO]-(other:Human)
            WITH h, collect(DISTINCT other.displayName) AS connections
            RETURN h.displayName AS human,
                   connections,
                   size(connections) AS connectionCount
            ORDER BY connectionCount DESC
            """
        )
        return [dict(r) for r in result]
