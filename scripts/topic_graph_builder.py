#!/usr/bin/env python3
"""
Topic Graph Builder — Creates/updates Topic nodes and topic-relationship edges.

Builds the topic co-occurrence and temporal flow graph from extraction results:
- CO_OCCURRED: Topics that appear in the same message/thread
- LED_TO: Temporal topic flow (topic A discussed before topic B)
- ABSTRACTS_TO: Topic hierarchy (specific → general)

Usage:
    from topic_graph_builder import TopicGraphBuilder
    builder = TopicGraphBuilder()
    builder.build_co_occurrence(human_id)
    builder.build_temporal_flow(human_id)
"""

import logging
from typing import Optional, Dict, Any, List

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import get_driver, close_driver

logger = logging.getLogger(__name__)


class TopicGraphBuilder:
    """Builds topic co-occurrence and temporal flow edges."""

    def __init__(self):
        self.driver = get_driver()

    def close(self):
        if self.driver:
            close_driver()
            self.driver = None

    def build_co_occurrence(self, human_id: Optional[str] = None) -> int:
        """Create CO_OCCURRED edges between topics in the same message.

        Args:
            human_id: Optional human filter. If None, processes all.

        Returns:
            Number of edges created/updated
        """
        human_filter = "AND m.humanId = $human_id" if human_id else ""
        params = {"human_id": human_id} if human_id else {}

        with self.driver.session() as session:
            result = session.run(
                f"""
                MATCH (t1:Topic)<-[:HAS_TOPIC]-(m:Message)-[:HAS_TOPIC]->(t2:Topic)
                WHERE id(t1) < id(t2) {human_filter}
                WITH t1, t2, count(m) AS coCount
                WHERE coCount >= 1
                MERGE (t1)-[r:CO_OCCURRED]-(t2)
                ON CREATE SET r.count = coCount, r.createdAt = datetime()
                ON MATCH SET r.count = coCount, r.updatedAt = datetime()
                RETURN count(r) AS edges
                """,
                **params,
            )
            record = result.single()
            count = record["edges"] if record else 0
            logger.info(f"Built {count} CO_OCCURRED edges" + (f" for {human_id[:8]}" if human_id else ""))
            return count

    def build_temporal_flow(self, human_id: Optional[str] = None) -> int:
        """Create LED_TO edges showing topic flow over time.

        If topic A appears in message M1 and topic B in M2 (same thread, M2 after M1),
        create (A)-[:LED_TO]->(B).

        Args:
            human_id: Optional human filter.

        Returns:
            Number of edges created/updated
        """
        human_filter = "AND m1.humanId = $human_id" if human_id else ""
        params = {"human_id": human_id} if human_id else {}

        with self.driver.session() as session:
            result = session.run(
                f"""
                MATCH (t1:Topic)<-[:HAS_TOPIC]-(m1:Message)-[:IN_THREAD]->(thread:Thread)<-[:IN_THREAD]-(m2:Message)-[:HAS_TOPIC]->(t2:Topic)
                WHERE m1.timestamp < m2.timestamp
                  AND t1 <> t2
                  AND duration.between(m1.timestamp, m2.timestamp).hours < 24
                  {human_filter}
                WITH t1, t2, count(*) AS flowCount
                WHERE flowCount >= 1
                MERGE (t1)-[r:LED_TO]->(t2)
                ON CREATE SET r.count = flowCount, r.createdAt = datetime()
                ON MATCH SET r.count = flowCount, r.updatedAt = datetime()
                RETURN count(r) AS edges
                """,
                **params,
            )
            record = result.single()
            count = record["edges"] if record else 0
            logger.info(f"Built {count} LED_TO edges" + (f" for {human_id[:8]}" if human_id else ""))
            return count

    def build_abstractions(self) -> int:
        """Create ABSTRACTS_TO edges from specific topics to general ones.

        Uses topic domain grouping: specific technical topics abstract to their domain.
        """
        with self.driver.session() as session:
            # Group topics by domain and create domain-level topic nodes
            result = session.run(
                """
                MATCH (t:Topic)
                WHERE t.domain IS NOT NULL AND t.domain <> 'general'
                WITH t.domain AS domain, collect(t) AS topics
                WHERE size(topics) >= 3
                MERGE (dt:Topic {label: domain + '_domain'})
                ON CREATE SET dt.id = randomUUID(),
                              dt.type = 'domain',
                              dt.domain = domain,
                              dt.createdAt = datetime()
                WITH dt, topics
                UNWIND topics AS t
                MERGE (t)-[r:ABSTRACTS_TO]->(dt)
                ON CREATE SET r.createdAt = datetime()
                RETURN count(r) AS edges
                """
            )
            record = result.single()
            count = record["edges"] if record else 0
            logger.info(f"Built {count} ABSTRACTS_TO edges")
            return count

    def rebuild_for_human(self, human_id: str) -> Dict[str, int]:
        """Rebuild all topic graph edges for a specific human.

        Returns:
            Dict with edge counts per type
        """
        return {
            "co_occurred": self.build_co_occurrence(human_id),
            "led_to": self.build_temporal_flow(human_id),
            "abstracts_to": self.build_abstractions(),
        }

    def get_topic_stats(self, human_id: Optional[str] = None) -> Dict[str, Any]:
        """Get topic graph statistics."""
        human_filter = "WHERE d.humanId = $human_id" if human_id else ""
        params = {"human_id": human_id} if human_id else {}

        with self.driver.session() as session:
            if human_id:
                result = session.run(
                    """
                    MATCH (h:Human {id: $human_id})-[d:DISCUSSED]->(t:Topic)
                    WITH count(t) AS topicCount, sum(d.count) AS totalMentions
                    OPTIONAL MATCH (:Topic)-[co:CO_OCCURRED]-(:Topic)
                    WITH topicCount, totalMentions, count(co) AS coEdges
                    OPTIONAL MATCH (:Topic)-[lt:LED_TO]->(:Topic)
                    RETURN topicCount, totalMentions, coEdges, count(lt) AS ledToEdges
                    """,
                    human_id=human_id,
                )
            else:
                result = session.run(
                    """
                    MATCH (t:Topic)
                    WITH count(t) AS topicCount
                    OPTIONAL MATCH (:Topic)-[co:CO_OCCURRED]-(:Topic)
                    WITH topicCount, count(co) AS coEdges
                    OPTIONAL MATCH (:Topic)-[lt:LED_TO]->(:Topic)
                    RETURN topicCount, coEdges, count(lt) AS ledToEdges
                    """
                )

            record = result.single()
            return dict(record) if record else {}


if __name__ == "__main__":
    builder = TopicGraphBuilder()
    stats = builder.get_topic_stats()
    print(f"Topic graph stats: {stats}")
    builder.close()
