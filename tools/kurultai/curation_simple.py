#!/usr/bin/env python3
"""
Simplified Memory Curation - Four essential operations.

Replaces the complex 15-query curation system with 4 simple, maintainable operations:
1. curation_rapid() - Every 5 minutes
2. curation_standard() - Every 15 minutes
3. curation_hourly() - Every hour
4. curation_deep() - Every 6 hours

Safety rules:
- NEVER delete Agent nodes
- NEVER delete active tasks (in_progress, pending)
- NEVER delete high-confidence beliefs (>= 0.9)
- NEVER delete entries < 24 hours old
- NEVER delete SystemConfig, AgentKey, Migration nodes
"""

from typing import Dict, List, Optional
from datetime import datetime, timezone


class SimpleCuration:
    """Simplified curation with clear, maintainable queries."""

    # Token budgets per tier
    HOT_TOKENS = 1600
    WARM_TOKENS = 400
    COLD_TOKENS = 200

    # Safety thresholds
    MIN_AGE_HOURS = 24
    HIGH_CONFIDENCE = 0.9

    def __init__(self, driver):
        self.driver = driver

    def curation_rapid(self) -> Dict:
        """
        Every 5 minutes:
        1. Enforce token budgets (demote LRU if over)
        2. Delete read notifications > 7 days
        3. Delete inactive sessions > 24 hours
        """
        with self.driver.session() as session:
            # Enforce HOT budget - demote oldest accessed to WARM
            hot_count_result = session.run("""
                MATCH (m:MemoryEntry {tier: 'HOT'})
                RETURN count(m) AS c
            """).single()
            hot_count = hot_count_result["c"] if hot_count_result else 0

            demoted = 0
            if hot_count > self.HOT_TOKENS:
                # Demote oldest accessed HOT entries to WARM
                demote_result = session.run("""
                    MATCH (m:MemoryEntry {tier: 'HOT'})
                    WHERE m.last_accessed < datetime() - duration('PT1H')
                      OR m.last_accessed IS NULL
                    WITH m ORDER BY m.last_accessed ASC
                    LIMIT $excess
                    SET m.tier = 'WARM',
                        m.curation_action = 'demoted_budget',
                        m.curation_at = datetime()
                    RETURN count(m) AS demoted
                """, excess=hot_count - self.HOT_TOKENS).single()
                demoted = demote_result["demoted"] if demote_result else 0

            # Clean old read notifications
            notifications_result = session.run("""
                MATCH (n:Notification)
                WHERE n.read = true
                  AND n.created_at < datetime() - duration('P7D')
                WITH n LIMIT 1000
                DELETE n
                RETURN count(n) AS deleted
            """).single()
            notifications_deleted = notifications_result["deleted"] if notifications_result else 0

            # Clean inactive sessions
            sessions_result = session.run("""
                MATCH (s:SessionContext)
                WHERE s.active = false
                  AND s.last_active_at < datetime() - duration('P1D')
                WITH s LIMIT 1000
                DELETE s
                RETURN count(s) AS deleted
            """).single()
            sessions_deleted = sessions_result["deleted"] if sessions_result else 0

            return {
                "hot_demoted": demoted,
                "hot_total": hot_count,
                "notifications_deleted": notifications_deleted,
                "sessions_deleted": sessions_deleted
            }

    def curation_standard(self) -> Dict:
        """
        Every 15 minutes:
        1. Archive completed tasks > 14 days
        2. Demote stale HOT entries (> 12h unused)
        """
        with self.driver.session() as session:
            # Archive old completed tasks
            # Safety: Only archive if > 14 days old and no learned_from relationships
            archived_result = session.run("""
                MATCH (t:Task {status: 'completed'})
                WHERE t.completed_at < datetime() - duration('P14D')
                  AND t.completed_at < datetime() - duration('PT24H')
                  AND NOT (t)-[:LEARNED_FROM]->()
                  AND NOT (t)<-[:LEARNED_FROM]-()
                WITH t LIMIT 500
                SET t.tier = 'ARCHIVE',
                    t.archived_at = datetime()
                RETURN count(t) AS archived
            """).single()
            archived = archived_result["archived"] if archived_result else 0

            # Demote stale HOT entries (> 12h unused)
            demoted_result = session.run("""
                MATCH (m:MemoryEntry {tier: 'HOT'})
                WHERE m.last_accessed < datetime() - duration('PT12H')
                  AND (m.created_at < datetime() - duration('PT24H') OR m.created_at IS NULL)
                WITH m ORDER BY m.last_accessed ASC
                LIMIT 100
                SET m.tier = 'WARM',
                    m.curation_action = 'demoted_stale',
                    m.curation_at = datetime()
                RETURN count(m) AS demoted
            """).single()
            demoted = demoted_result["demoted"] if demoted_result else 0

            return {
                "archived": archived,
                "demoted": demoted
            }

    def curation_hourly(self) -> Dict:
        """
        Hourly:
        1. Promote frequently accessed COLD entries
        2. Decay belief confidence
        3. Enforce WARM/COLD budgets
        """
        with self.driver.session() as session:
            # Promote frequently accessed COLD entries
            promoted_result = session.run("""
                MATCH (m:MemoryEntry {tier: 'COLD'})
                WHERE m.access_count_7d >= 3
                  AND (m.created_at < datetime() - duration('PT24H') OR m.created_at IS NULL)
                WITH m ORDER BY m.access_count_7d DESC
                LIMIT 50
                SET m.tier = 'WARM',
                    m.curation_action = 'promoted_access',
                    m.curation_at = datetime()
                RETURN count(m) AS promoted
            """).single()
            promoted = promoted_result["promoted"] if promoted_result else 0

            # Decay belief confidence for old beliefs
            decayed_result = session.run("""
                MATCH (b:Belief)
                WHERE b.last_accessed < datetime() - duration('P7D')
                  AND b.confidence > 0.3
                  AND b.confidence < $high_confidence
                  AND (b.created_at < datetime() - duration('PT24H') OR b.created_at IS NULL)
                WITH b LIMIT 100
                SET b.confidence = b.confidence - 0.01,
                    b.curation_at = datetime()
                RETURN count(b) AS decayed
            """, high_confidence=self.HIGH_CONFIDENCE).single()
            decayed = decayed_result["decayed"] if decayed_result else 0

            # Enforce WARM budget - demote to COLD
            warm_count_result = session.run("""
                MATCH (m:MemoryEntry {tier: 'WARM'})
                RETURN count(m) AS c
            """).single()
            warm_count = warm_count_result["c"] if warm_count_result else 0

            warm_demoted = 0
            if warm_count > self.WARM_TOKENS:
                warm_demote_result = session.run("""
                    MATCH (m:MemoryEntry {tier: 'WARM'})
                    WHERE m.last_accessed < datetime() - duration('P1D')
                      OR m.last_accessed IS NULL
                    WITH m ORDER BY m.last_accessed ASC
                    LIMIT $excess
                    SET m.tier = 'COLD',
                        m.curation_action = 'demoted_warm_budget',
                        m.curation_at = datetime()
                    RETURN count(m) AS demoted
                """, excess=warm_count - self.WARM_TOKENS).single()
                warm_demoted = warm_demote_result["demoted"] if warm_demote_result else 0

            return {
                "promoted": promoted,
                "confidence_decayed": decayed,
                "warm_demoted": warm_demoted,
                "warm_total": warm_count
            }

    def curation_deep(self) -> Dict:
        """
        Every 6 hours:
        1. Delete orphaned nodes (no relationships, old)
        2. Hard delete tombstoned entries > 30 days
        3. Enforce COLD budget
        """
        with self.driver.session() as session:
            # Delete orphaned nodes
            # Safety: Exclude protected labels, require > 7 days old
            orphans_result = session.run("""
                MATCH (n)
                WHERE NOT n:Agent
                  AND NOT n:AgentKey
                  AND NOT n:SystemConfig
                  AND NOT n:Migration
                  AND NOT n:Task
                  AND NOT n:Belief
                  AND NOT (n)--()
                  AND n.created_at < datetime() - duration('P7D')
                WITH n LIMIT 500
                DELETE n
                RETURN count(n) AS deleted
            """).single()
            orphans_deleted = orphans_result["deleted"] if orphans_result else 0

            # Hard delete tombstoned entries > 30 days
            tombstones_result = session.run("""
                MATCH (m)
                WHERE m.tombstone = true
                  AND m.deleted_at < datetime() - duration('P30D')
                WITH m LIMIT 500
                DELETE m
                RETURN count(m) AS deleted
            """).single()
            tombstones_purged = tombstones_result["deleted"] if tombstones_result else 0

            # Enforce COLD budget - move to ARCHIVE
            cold_count_result = session.run("""
                MATCH (m:MemoryEntry {tier: 'COLD'})
                RETURN count(m) AS c
            """).single()
            cold_count = cold_count_result["c"] if cold_count_result else 0

            cold_archived = 0
            if cold_count > self.COLD_TOKENS:
                cold_archive_result = session.run("""
                    MATCH (m:MemoryEntry {tier: 'COLD'})
                    WHERE m.last_accessed < datetime() - duration('P7D')
                      OR m.last_accessed IS NULL
                    WITH m ORDER BY m.last_accessed ASC
                    LIMIT $excess
                    SET m.tier = 'ARCHIVE',
                        m.curation_action = 'archived_cold_budget',
                        m.curation_at = datetime()
                    RETURN count(m) AS archived
                """, excess=cold_count - self.COLD_TOKENS).single()
                cold_archived = cold_archive_result["archived"] if cold_archive_result else 0

            return {
                "orphans_deleted": orphans_deleted,
                "tombstones_purged": tombstones_purged,
                "cold_archived": cold_archived,
                "cold_total": cold_count
            }

    def get_curation_stats(self) -> Dict:
        """Get current curation statistics."""
        with self.driver.session() as session:
            # Count by tier
            tier_result = session.run("""
                MATCH (m:MemoryEntry)
                RETURN m.tier AS tier, count(m) AS count
            """).data()

            tiers = {r["tier"]: r["count"] for r in tier_result}

            # Count protected nodes
            protected_result = session.run("""
                MATCH (n)
                WHERE n:Agent OR n:AgentKey OR n:SystemConfig OR n:Migration
                RETURN labels(n)[0] AS label, count(n) AS count
            """).data()

            protected = {r["label"]: r["count"] for r in protected_result}

            # Recent curation activity
            activity_result = session.run("""
                MATCH (m)
                WHERE m.curation_at > datetime() - duration('P1D')
                RETURN m.curation_action AS action, count(m) AS count
            """).data()

            activity = {r["action"]: r["count"] for r in activity_result}

            return {
                "tiers": tiers,
                "protected_nodes": protected,
                "recent_activity": activity,
                "budgets": {
                    "hot": self.HOT_TOKENS,
                    "warm": self.WARM_TOKENS,
                    "cold": self.COLD_TOKENS
                }
            }


# ============================================================================
# CLI for testing
# ============================================================================

def main():
    """CLI for testing curation operations."""
    import argparse
    import os
    from neo4j import GraphDatabase

    parser = argparse.ArgumentParser(description="Test curation operations")
    parser.add_argument("operation", choices=["rapid", "standard", "hourly", "deep", "stats"])
    parser.add_argument("--neo4j-uri", default=os.getenv("NEO4J_URI", "bolt://localhost:7687"))
    parser.add_argument("--neo4j-user", default=os.getenv("NEO4J_USER", "neo4j"))
    parser.add_argument("--neo4j-password", default=os.getenv("NEO4J_PASSWORD"))

    args = parser.parse_args()

    if not args.neo4j_password:
        print("NEO4J_PASSWORD not set")
        return

    driver = GraphDatabase.driver(
        args.neo4j_uri,
        auth=(args.neo4j_user, args.neo4j_password)
    )

    curation = SimpleCuration(driver)

    if args.operation == "rapid":
        result = curation.curation_rapid()
        print(f"Rapid curation:")
        print(f"  HOT demoted: {result['hot_demoted']} (total: {result['hot_total']})")
        print(f"  Notifications deleted: {result['notifications_deleted']}")
        print(f"  Sessions deleted: {result['sessions_deleted']}")

    elif args.operation == "standard":
        result = curation.curation_standard()
        print(f"Standard curation:")
        print(f"  Tasks archived: {result['archived']}")
        print(f"  HOT demoted: {result['demoted']}")

    elif args.operation == "hourly":
        result = curation.curation_hourly()
        print(f"Hourly curation:")
        print(f"  COLD promoted: {result['promoted']}")
        print(f"  Confidence decayed: {result['confidence_decayed']}")
        print(f"  WARM demoted: {result['warm_demoted']} (total: {result['warm_total']})")

    elif args.operation == "deep":
        result = curation.curation_deep()
        print(f"Deep curation:")
        print(f"  Orphans deleted: {result['orphans_deleted']}")
        print(f"  Tombstones purged: {result['tombstones_purged']}")
        print(f"  COLD archived: {result['cold_archived']} (total: {result['cold_total']})")

    elif args.operation == "stats":
        stats = curation.get_curation_stats()
        print(f"Curation stats:")
        print(f"  Tiers: {stats['tiers']}")
        print(f"  Protected: {stats['protected_nodes']}")
        print(f"  Recent activity: {stats['recent_activity']}")
        print(f"  Budgets: {stats['budgets']}")

    driver.close()


if __name__ == "__main__":
    main()
