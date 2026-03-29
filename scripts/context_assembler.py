#!/usr/bin/env python3
"""
Context Assembler — Graph-guided retrieval engine for LLM context.

Combines topology traversal + vector search in a single Neo4j transaction
to build rich conversational context for the LLM.

4-Phase retrieval:
1. Core identity topics (pre-computed PageRank, top 7)
2. Community expansion + bridge topics (Louvain + betweenness)
3. Narrative path (shortest path via LED_TO)
4. Graph-guided message retrieval (topic-scoped vector search)

Usage:
    from context_assembler import assemble_context
    context = assemble_context(human_id, current_message)
"""

import time
import logging
from typing import Optional, Dict, Any, List

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import get_driver
from embedding_generator import generate_embedding
from token_budget import TokenBudget

logger = logging.getLogger(__name__)


class ContextAssembler:
    """Assembles graph-derived context for LLM consumption."""

    def __init__(self):
        self.driver = get_driver()

    def close(self):
        # Don't call close_driver() — let the atexit handler manage lifecycle
        self.driver = None

    def assemble(
        self,
        human_id: str,
        current_message: str = "",
        current_embedding: Optional[List[float]] = None,
        max_tokens: int = 4000,
        group_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Assemble full context for a human + current message.

        Args:
            human_id: UUID of the Human
            current_message: Current incoming message text
            current_embedding: Pre-computed embedding (generated if None)
            max_tokens: Total token budget
            group_id: Group identifier for scoped context (None = DM)

        Returns:
            Dict with structured context sections
        """
        t0 = time.monotonic()

        if current_embedding is None and current_message:
            current_embedding = generate_embedding(current_message)

        budget = TokenBudget(max_tokens)
        scope = f"group:{group_id}" if group_id else "dm"

        with self.driver.session() as session:
            # Phase 1: Core identity topics (PageRank) — scoped by message scope
            core_topics = self._get_core_topics(session, human_id, scope)

            # Phase 2: Community + bridge topics — scoped
            communities = self._get_communities(session, human_id, scope)
            bridges = self._get_bridge_topics(session, human_id, scope)

            # Phase 3: Drift signals — DM-private (topic trends from DMs)
            if group_id:
                drift = []
                logger.debug(f"Group context {group_id[:12]}: excluded drift_signals (DM-private)")
            else:
                drift = self._get_drift_signals(session, human_id)

            # Phase 4: Active thread messages — scoped
            thread_messages = self._get_active_thread(session, human_id, scope)

            # Phase 4b: Group-wide recent messages (all senders, not just this human)
            # Provides shared conversational context so follow-ups work across speakers
            group_recent = []
            if group_id:
                group_recent = self._get_group_recent_messages(session, group_id, human_id)

            # Phase 5: Vector-similar messages — scoped
            similar_messages = []
            if current_embedding:
                similar_messages = self._vector_search(
                    session, human_id, current_embedding, scope=scope
                )

            # Phase 6: Inferences — exclude from group context
            if group_id:
                inferences = []  # Private inferences never shown in groups
                logger.debug(f"Group context {group_id[:12]}: excluded inferences (private)")
            else:
                inferences = self._get_inferences(session, human_id)

            # Phase 7: Social context
            social = self._get_social_context(session, human_id)
            if group_id and social:
                # Drop records with sensitive/private relationship context entirely
                # (keeping name+relType alone still leaks structural metadata)
                from group_context_bridge import classify_shareability
                social = [
                    s for s in social
                    if classify_shareability(s.get('context', '')) not in ('SENSITIVE', 'PRIVATE')
                ]

            # Phase 8: Action items — DM-only (unscoped query, not safe for groups)
            if group_id:
                action_items = []
                logger.debug(f"Group context {group_id[:12]}: excluded action_items (DM-only)")
            else:
                action_items = self._get_action_items(session, human_id)

            # Phase 9: Human profile (scope-filtered at Cypher level when group_id set)
            profile = self._get_human_profile(session, human_id, group_id=group_id)

        # Assemble into structured context
        context = {
            "human_id": human_id,
            "profile": profile,
            "core_topics": core_topics[:7],
            "communities": communities,
            "bridge_topics": bridges[:5],
            "drift_signals": drift,
            "thread_messages": thread_messages[:20],
            "group_recent_messages": group_recent[:15],
            "similar_messages": similar_messages[:10],
            "inferences": inferences[:10],
            "social_context": social,
            "action_items": action_items[:10],
            "scope": scope,
            "assembly_ms": round((time.monotonic() - t0) * 1000),
        }

        return context

    def _get_core_topics(self, session, human_id: str, scope: str = "dm") -> List[Dict[str, Any]]:
        """Get top PageRank-scored topics, scoped to message scope."""
        result = session.run(
            """
            MATCH (h:Human {id: $human_id})-[d:DISCUSSED]->(t:Topic)
            WHERE EXISTS {
                MATCH (m:Message {humanId: $human_id})-[:HAS_TOPIC]->(t)
                WHERE m.scope = $scope
            }
            RETURN t.label AS label, t.domain AS domain,
                   coalesce(d.pagerank_score, toFloat(d.count)/10.0) AS score,
                   d.count AS mentions
            ORDER BY score DESC
            LIMIT 10
            """,
            human_id=human_id,
            scope=scope,
        )
        return [dict(r) for r in result]

    def _get_communities(self, session, human_id: str, scope: str = "dm") -> List[Dict[str, Any]]:
        """Get topic communities (Louvain clusters), scoped."""
        result = session.run(
            """
            MATCH (h:Human {id: $human_id})-[d:DISCUSSED]->(t:Topic)
            WHERE d.communityId IS NOT NULL
              AND EXISTS {
                  MATCH (m:Message {humanId: $human_id})-[:HAS_TOPIC]->(t)
                  WHERE m.scope = $scope
              }
            WITH d.communityId AS cid, collect(t.label) AS topics, avg(coalesce(d.pagerank_score, 0)) AS avgScore
            RETURN cid AS communityId, topics, avgScore
            ORDER BY avgScore DESC
            LIMIT 5
            """,
            human_id=human_id,
            scope=scope,
        )
        return [dict(r) for r in result]

    def _get_bridge_topics(self, session, human_id: str, scope: str = "dm") -> List[Dict[str, Any]]:
        """Get bridge topics (betweenness centrality), scoped."""
        result = session.run(
            """
            MATCH (h:Human {id: $human_id})-[:DISCUSSED]->(t:Topic)
            WHERE t.betweenness_score IS NOT NULL AND t.betweenness_score > 0
              AND EXISTS {
                  MATCH (m:Message {humanId: $human_id})-[:HAS_TOPIC]->(t)
                  WHERE m.scope = $scope
              }
            RETURN t.label AS label, t.betweenness_score AS score
            ORDER BY t.betweenness_score DESC
            LIMIT 5
            """,
            human_id=human_id,
            scope=scope,
        )
        return [dict(r) for r in result]

    def _get_drift_signals(self, session, human_id: str) -> List[Dict[str, Any]]:
        """Get recent drift signals (rising/fading topics)."""
        result = session.run(
            """
            MATCH (tm:TemporalMarker {humanId: $human_id})
            WHERE tm.detectedAt > datetime() - duration('P7D')
            RETURN tm.signal AS signal, tm.topicLabel AS topic,
                   tm.recentCount AS recent, tm.longtermCount AS longterm
            ORDER BY tm.detectedAt DESC
            LIMIT 10
            """,
            human_id=human_id,
        )
        return [dict(r) for r in result]

    def _get_active_thread(self, session, human_id: str, scope: str = "dm") -> List[Dict[str, Any]]:
        """Get messages from the active thread, scoped."""
        result = session.run(
            """
            MATCH (t:Thread {humanId: $human_id, status: 'ACTIVE'})
            WHERE t.scope = $scope
            MATCH (m:Message)-[:IN_THREAD]->(t)
            RETURN m.contentScrubbed AS text, m.direction AS direction,
                   toString(m.timestamp) AS timestamp,
                   m.summary AS summary
            ORDER BY m.timestamp DESC
            LIMIT 20
            """,
            human_id=human_id,
            scope=scope,
        )
        return [dict(r) for r in result]

    def _get_group_recent_messages(
        self, session, group_id: str, exclude_human_id: str
    ) -> List[Dict[str, Any]]:
        """Get recent messages from ALL senders in a group (shared conversational context).

        This provides group-wide context so follow-up questions work across speakers.
        For example, if Kublai posts a calendar event and someone asks "who's going",
        the LLM sees the calendar message even though it was sent by a different human_id.

        Excludes the current human's messages (those are already in thread_messages).
        Only returns scrubbed content — no PII leakage.
        """
        scope = f"group:{group_id}"
        result = session.run(
            """
            MATCH (m:Message)
            WHERE m.scope = $scope
              AND m.humanId <> $exclude_human_id
              AND m.timestamp > datetime() - duration('PT4H')
            OPTIONAL MATCH (m)-[:SENT_BY]->(h:Human)
            RETURN m.contentScrubbed AS text, m.direction AS direction,
                   toString(m.timestamp) AS timestamp,
                   m.summary AS summary,
                   coalesce(h.displayName, 'Kublai') AS sender
            ORDER BY m.timestamp DESC
            LIMIT 15
            """,
            scope=scope,
            exclude_human_id=exclude_human_id,
        )
        return [dict(r) for r in result]

    def _vector_search(
        self, session, human_id: str, embedding: List[float], top_k: int = 10,
        scope: str = "dm",
    ) -> List[Dict[str, Any]]:
        """Find semantically similar messages via vector index, scoped.

        Uses internal_k (5x top_k) to over-fetch from the global vector index,
        then post-filters by scope to avoid cross-scope messages consuming the
        result budget.
        """
        try:
            internal_k = top_k * 5
            result = session.run(
                """
                CALL db.index.vector.queryNodes('message_embedding', $internal_k, $embedding)
                YIELD node AS m, score
                WHERE m.humanId = $human_id
                  AND m.scope = $scope
                RETURN m.contentScrubbed AS text, m.direction AS direction,
                       toString(m.timestamp) AS timestamp,
                       m.summary AS summary,
                       score
                ORDER BY score DESC
                LIMIT $k
                """,
                human_id=human_id,
                embedding=embedding,
                internal_k=internal_k,
                k=top_k,
                scope=scope,
            )
            return [dict(r) for r in result]
        except Exception as e:
            logger.debug(f"Vector search failed (index may not exist yet): {e}")
            return []

    def _get_inferences(self, session, human_id: str) -> List[Dict[str, Any]]:
        """Get high-confidence inferences about the human."""
        result = session.run(
            """
            MATCH (i:Inference {humanId: $human_id})
            WHERE i.confidence > 0.6
              AND NOT coalesce(i.superseded, false)
            RETURN i.type AS type, i.content AS content,
                   i.confidence AS confidence,
                   toString(i.createdAt) AS createdAt
            ORDER BY i.confidence DESC
            LIMIT 10
            """,
            human_id=human_id,
        )
        return [dict(r) for r in result]

    def _get_social_context(self, session, human_id: str) -> List[Dict[str, Any]]:
        """Get KNOWN_THROUGH connections."""
        result = session.run(
            """
            MATCH (h:Human {id: $human_id})-[r:KNOWN_THROUGH|RELATED_TO]->(other:Human)
            RETURN other.displayName AS name,
                   type(r) AS relType,
                   coalesce(r.relationship, r.context, '') AS context
            LIMIT 10
            """,
            human_id=human_id,
        )
        return [dict(r) for r in result]

    def _get_action_items(self, session, human_id: str) -> List[Dict[str, Any]]:
        """Get open action items."""
        result = session.run(
            """
            MATCH (ai:ActionItem {humanId: $human_id, status: 'OPEN'})
            RETURN ai.description AS description, ai.priority AS priority,
                   ai.assignee AS assignee, ai.deadline AS deadline
            ORDER BY CASE ai.priority
                WHEN 'high' THEN 0
                WHEN 'medium' THEN 1
                ELSE 2 END
            LIMIT 10
            """,
            human_id=human_id,
        )
        return [dict(r) for r in result]

    def _get_human_profile(
        self, session, human_id: str, group_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Get basic human profile. When group_id is set, only group-safe identifiers are returned."""
        if group_id:
            # Cypher-level filtering: only return group-safe identifier types
            result = session.run(
                """
                MATCH (h:Human {id: $human_id})
                OPTIONAL MATCH (h)-[:IDENTIFIED_BY]->(i:Identifier)
                    WHERE i.type IN ['DISPLAY_NAME', 'NAME_VARIANT']
                RETURN h.displayName AS displayName,
                       h.source AS source,
                       h.confidence AS confidence,
                       toString(h.firstKnown) AS firstKnown,
                       toString(h.lastContact) AS lastContact,
                       collect({type: i.type, value: i.value}) AS identifiers
                """,
                human_id=human_id,
            )
        else:
            result = session.run(
                """
                MATCH (h:Human {id: $human_id})
                OPTIONAL MATCH (h)-[:IDENTIFIED_BY]->(i:Identifier)
                RETURN h.displayName AS displayName,
                       h.source AS source,
                       h.confidence AS confidence,
                       toString(h.firstKnown) AS firstKnown,
                       toString(h.lastContact) AS lastContact,
                       collect({type: i.type, value: i.value}) AS identifiers
                """,
                human_id=human_id,
            )
        record = result.single()
        if not record:
            return None
        data = dict(record)
        data["identifiers"] = [i for i in data.get("identifiers", []) if i.get("type")]
        return data


def assemble_context(
    human_id: str, current_message: str = "", group_id: Optional[str] = None, **kwargs
) -> Dict[str, Any]:
    """Convenience function for context assembly."""
    assembler = ContextAssembler()
    try:
        return assembler.assemble(human_id, current_message, group_id=group_id, **kwargs)
    finally:
        assembler.close()


if __name__ == "__main__":
    import argparse
    import json
    parser = argparse.ArgumentParser()
    parser.add_argument("human_id")
    parser.add_argument("--message", default="Hello", help="Current message")
    args = parser.parse_args()

    context = assemble_context(args.human_id, args.message)
    print(json.dumps(context, indent=2, default=str))
