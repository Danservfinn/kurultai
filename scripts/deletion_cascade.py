#!/usr/bin/env python3
"""
Deletion Cascade Engine — GDPR-compliant data deletion for /forget command.

Cascade order:
1. Messages → HAS_TOPIC edges → IN_THREAD edges
2. Threads (belonging to human)
3. ActionItems (belonging to human)
4. DISCUSSED edges (between human and topics)
5. Inferences (belonging to human)
6. TemporalMarkers (belonging to human)
7. HAS_CONSENT edges
8. IDENTIFIED_BY edges + orphaned Identifiers
9. Anonymize Human node (preserve for graph integrity)

Topic nodes are PRESERVED (non-PII, shared resource).
"""

import logging
from typing import Dict, Any

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import neo4j_session

logger = logging.getLogger(__name__)


def execute_deletion_cascade(human_id: str, confirm: bool = False) -> Dict[str, Any]:
    """Execute full data deletion for a human.

    Args:
        human_id: UUID of the Human
        confirm: Must be True to actually delete

    Returns:
        Dict with counts of deleted items per type
    """
    if not confirm:
        return {
            "success": False,
            "error": "Must set confirm=True to delete data",
            "warning": f"This will permanently delete ALL data for human {human_id[:8]}",
        }

    counts = {}

    with neo4j_session() as session:
        # 1. Delete Messages and their edges
        result = session.run(
            """
            MATCH (m:Message {humanId: $human_id})
            OPTIONAL MATCH (m)-[r]-()
            WITH m, count(r) AS relCount
            DETACH DELETE m
            RETURN count(m) AS deleted
            """,
            human_id=human_id,
        ).single()
        counts["messages"] = result["deleted"] if result else 0

        # 2. Delete Threads
        result = session.run(
            """
            MATCH (t:Thread {humanId: $human_id})
            DETACH DELETE t
            RETURN count(t) AS deleted
            """,
            human_id=human_id,
        ).single()
        counts["threads"] = result["deleted"] if result else 0

        # 3. Delete ActionItems
        result = session.run(
            """
            MATCH (ai:ActionItem {humanId: $human_id})
            DETACH DELETE ai
            RETURN count(ai) AS deleted
            """,
            human_id=human_id,
        ).single()
        counts["action_items"] = result["deleted"] if result else 0

        # 4. Delete DISCUSSED edges (keep Topic nodes)
        result = session.run(
            """
            MATCH (h:Human {id: $human_id})-[d:DISCUSSED]->(:Topic)
            DELETE d
            RETURN count(d) AS deleted
            """,
            human_id=human_id,
        ).single()
        counts["discussed_edges"] = result["deleted"] if result else 0

        # 5. Delete Inferences
        result = session.run(
            """
            MATCH (i:Inference {humanId: $human_id})
            DETACH DELETE i
            RETURN count(i) AS deleted
            """,
            human_id=human_id,
        ).single()
        counts["inferences"] = result["deleted"] if result else 0

        # 6. Delete TemporalMarkers
        result = session.run(
            """
            MATCH (tm:TemporalMarker {humanId: $human_id})
            DETACH DELETE tm
            RETURN count(tm) AS deleted
            """,
            human_id=human_id,
        ).single()
        counts["temporal_markers"] = result["deleted"] if result else 0

        # 7. Delete consent edges
        result = session.run(
            """
            MATCH (h:Human {id: $human_id})-[r:HAS_CONSENT]->(:ConsentCategory)
            DELETE r
            RETURN count(r) AS deleted
            """,
            human_id=human_id,
        ).single()
        counts["consent_edges"] = result["deleted"] if result else 0

        # 8. Delete identifiers
        result = session.run(
            """
            MATCH (h:Human {id: $human_id})-[r:IDENTIFIED_BY]->(i:Identifier)
            DELETE r
            WITH i
            WHERE NOT exists((i)<-[:IDENTIFIED_BY]-())
            DELETE i
            RETURN count(i) AS deleted
            """,
            human_id=human_id,
        ).single()
        counts["identifiers"] = result["deleted"] if result else 0

        # 9. Delete KNOWN_THROUGH / RELATED_TO edges
        result = session.run(
            """
            MATCH (h:Human {id: $human_id})-[r:KNOWN_THROUGH|RELATED_TO]-()
            DELETE r
            RETURN count(r) AS deleted
            """,
            human_id=human_id,
        ).single()
        counts["relationship_edges"] = result["deleted"] if result else 0

        # 10. Anonymize Human node
        session.run(
            """
            MATCH (h:Human {id: $human_id})
            SET h.displayName = 'Deleted User',
                h.status = 'deleted',
                h.communicationStyle = null,
                h.priorsComputedAt = null,
                h.socialCluster = null,
                h.deletedAt = datetime()
            """,
            human_id=human_id,
        )
        counts["human_anonymized"] = True

    total = sum(v for v in counts.values() if isinstance(v, int))
    logger.info(f"Deletion cascade for {human_id[:8]}: {total} items deleted")

    return {
        "success": True,
        "human_id": human_id,
        "counts": counts,
        "total_deleted": total,
    }


def verify_deletion(human_id: str) -> Dict[str, Any]:
    """Verify that all data for a human has been deleted."""
    with neo4j_session() as session:
        checks = {}

        for label, field in [
            ("Message", "humanId"),
            ("Thread", "humanId"),
            ("ActionItem", "humanId"),
            ("Inference", "humanId"),
            ("TemporalMarker", "humanId"),
        ]:
            result = session.run(
                f"MATCH (n:{label} {{{field}: $human_id}}) RETURN count(n) AS cnt",
                human_id=human_id,
            ).single()
            checks[label] = result["cnt"] if result else -1

        # Check edges
        result = session.run(
            """
            MATCH (h:Human {id: $human_id})-[r]-()
            RETURN type(r) AS relType, count(r) AS cnt
            """,
            human_id=human_id,
        )
        edges = {r["relType"]: r["cnt"] for r in result}
        checks["remaining_edges"] = edges

        # Check human status
        result = session.run(
            "MATCH (h:Human {id: $human_id}) RETURN h.status AS status",
            human_id=human_id,
        ).single()
        checks["human_status"] = result["status"] if result else "not found"

    all_clean = all(
        v == 0 for k, v in checks.items()
        if isinstance(v, int) and k != "human_status"
    ) and not checks.get("remaining_edges")

    return {"clean": all_clean, "checks": checks}
