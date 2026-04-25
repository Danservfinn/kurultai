#!/usr/bin/env python3
"""
GDS Projection Manager — Creates and caches per-human named graph projections.

Manages the lifecycle of GDS graph projections used by all algorithm runners.
Each human gets their own projection scoped to their topic/message subgraph.

Usage:
    from gds_projection_manager import GDSProjectionManager
    mgr = GDSProjectionManager()
    mgr.ensure_projection(human_id)
    mgr.refresh_projection(human_id)
    mgr.drop_projection(human_id)
"""
from __future__ import annotations

import logging
from typing import Optional, Dict, Any, List

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import get_driver, close_driver

logger = logging.getLogger(__name__)


def _gds_available(driver) -> bool:
    """Check if GDS plugin is installed."""
    try:
        with driver.session() as session:
            result = session.run("RETURN gds.version() AS v")
            record = result.single()
            return record is not None
    except Exception:
        return False


class GDSProjectionManager:
    """Manages per-human GDS graph projections."""

    def __init__(self):
        self.driver = get_driver()
        self._gds_ok = _gds_available(self.driver)
        if not self._gds_ok:
            logger.warning("GDS plugin not available — algorithm features disabled")

    @property
    def gds_available(self) -> bool:
        return self._gds_ok

    def close(self):
        if self.driver:
            close_driver()
            self.driver = None

    def _projection_name(self, human_id: str, graph_type: str = "topic") -> str:
        """Generate a deterministic projection name."""
        short_id = human_id[:8]
        return f"conv_mem_{graph_type}_{short_id}"

    def projection_exists(self, human_id: str, graph_type: str = "topic") -> bool:
        """Check if a projection already exists."""
        if not self._gds_ok:
            return False

        name = self._projection_name(human_id, graph_type)
        try:
            with self.driver.session() as session:
                result = session.run(
                    "CALL gds.graph.exists($name) YIELD exists RETURN exists",
                    name=name,
                )
                record = result.single()
                return record["exists"] if record else False
        except Exception:
            return False

    def ensure_projection(self, human_id: str, graph_type: str = "topic") -> bool:
        """Create projection if it doesn't exist. Returns True if projection is ready."""
        if not self._gds_ok:
            return False

        if self.projection_exists(human_id, graph_type):
            return True

        return self.create_projection(human_id, graph_type)

    def create_projection(self, human_id: str, graph_type: str = "topic") -> bool:
        """Create a new named graph projection for a human.

        Uses Cypher projection (GDS 2.x compatible).
        Topic graph: Topic nodes discussed by this human + CO_OCCURRED/LED_TO edges.
        """
        if not self._gds_ok:
            return False

        name = self._projection_name(human_id, graph_type)

        # Drop existing if any
        self.drop_projection(human_id, graph_type)

        try:
            with self.driver.session() as session:
                if graph_type == "topic":
                    # Use MATCH-based Cypher projection (GDS 2.x)
                    session.run(
                        """
                        MATCH (h:Human {id: $human_id})-[:DISCUSSED]->(t:Topic)
                        WITH collect(t) AS topics
                        WITH topics, [t IN topics | id(t)] AS nodeIds
                        UNWIND topics AS t1
                        UNWIND topics AS t2
                        WITH t1, t2, nodeIds
                        WHERE id(t1) < id(t2)
                        OPTIONAL MATCH (t1)-[co:CO_OCCURRED]-(t2)
                        OPTIONAL MATCH (t1)-[lt:LED_TO]->(t2)
                        WITH t1, t2, nodeIds,
                             coalesce(co.count, 0) + coalesce(lt.count, 0) AS weight
                        WHERE weight > 0
                        WITH collect({source: id(t1), target: id(t2), weight: weight}) AS rels, nodeIds
                        CALL gds.graph.project.cypher(
                            $name,
                            'MATCH (t:Topic) WHERE id(t) IN $nodeIds RETURN id(t) AS id',
                            'UNWIND $rels AS r RETURN r.source AS source, r.target AS target, r.weight AS weight',
                            {parameters: {nodeIds: nodeIds, rels: rels}}
                        )
                        YIELD graphName
                        RETURN graphName
                        """,
                        name=name,
                        human_id=human_id,
                    )
                elif graph_type == "social":
                    session.run(
                        """
                        CALL gds.graph.project(
                            $name,
                            'Human',
                            {
                                KNOWN_THROUGH: {orientation: 'UNDIRECTED'},
                                RELATED_TO: {orientation: 'UNDIRECTED'}
                            }
                        )
                        """,
                        name=name,
                    )

                logger.info(f"Created GDS projection: {name}")
                return True

        except Exception as e:
            logger.error(f"Failed to create projection {name}: {e}")
            return False

    def refresh_projection(self, human_id: str, graph_type: str = "topic") -> bool:
        """Drop and recreate a projection."""
        self.drop_projection(human_id, graph_type)
        return self.create_projection(human_id, graph_type)

    def drop_projection(self, human_id: str, graph_type: str = "topic") -> bool:
        """Drop a projection if it exists."""
        if not self._gds_ok:
            return False

        name = self._projection_name(human_id, graph_type)
        try:
            with self.driver.session() as session:
                result = session.run(
                    "CALL gds.graph.exists($name) YIELD exists RETURN exists",
                    name=name,
                )
                record = result.single()
                if record and record["exists"]:
                    session.run("CALL gds.graph.drop($name)", name=name)
                    logger.info(f"Dropped projection: {name}")
            return True
        except Exception as e:
            logger.debug(f"Drop projection {name}: {e}")
            return False

    def list_projections(self) -> List[Dict[str, Any]]:
        """List all conversation memory projections."""
        if not self._gds_ok:
            return []

        try:
            with self.driver.session() as session:
                result = session.run(
                    """
                    CALL gds.graph.list()
                    YIELD graphName, nodeCount, relationshipCount, creationTime
                    WHERE graphName STARTS WITH 'conv_mem_'
                    RETURN graphName, nodeCount, relationshipCount, toString(creationTime) AS createdAt
                    """
                )
                return [dict(r) for r in result]
        except Exception:
            return []


if __name__ == "__main__":
    mgr = GDSProjectionManager()
    print(f"GDS available: {mgr.gds_available}")
    if mgr.gds_available:
        projections = mgr.list_projections()
        print(f"Existing projections: {len(projections)}")
        for p in projections:
            print(f"  {p['graphName']}: {p['nodeCount']} nodes, {p['relationshipCount']} rels")
    mgr.close()
