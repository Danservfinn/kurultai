"""
Migration v5: Chat Summaries for Neo4j

Adds ChatSummary nodes for storing sanitized agent conversation summaries.
These are periodic snapshots of agent activity captured by the heartbeat
sidecar's WebSocket listener, with PII stripped before storage.

ChatSummary properties:
- id (UUID)
- agent_id (main, researcher, etc.)
- session_key (OpenClaw session identifier)
- turn_count (agent responses in this window)
- topics (extracted topic tags)
- summary (sanitized summary text)
- tools_used (tools/capabilities exercised)
- delegations (agent-to-agent delegations)
- created_at, window_start, window_end (datetimes)
- pii_stripped (boolean, always true)

Relationship: (Agent)-[:HAS_SUMMARY]->(ChatSummary)

Author: Claude (Anthropic)
Date: 2026-02-07
"""

from migrations.migration_manager import MigrationManager


class V5ChatSummaries:
    """
    Kurultai v0.2 Chat Summaries migration (version 5).

    Adds:
    - ChatSummary uniqueness constraint on id
    - Composite index on (agent_id, created_at) for time-range queries
    - Index on session_key for session-scoped lookups
    """

    VERSION = 5
    NAME = "chat_summaries"
    DESCRIPTION = "Add ChatSummary nodes for sanitized agent conversation persistence"

    UP_CYPHER = """
    // =====================================================
    // V5 Chat Summaries Migration
    // Kurultai v0.2
    // =====================================================

    // -----------------------------------------------------
    // 1. Constraints — ChatSummary
    // -----------------------------------------------------

    CREATE CONSTRAINT chat_summary_id_unique IF NOT EXISTS
    FOR (cs:ChatSummary) REQUIRE cs.id IS UNIQUE;

    // -----------------------------------------------------
    // 2. Indexes — ChatSummary
    // -----------------------------------------------------

    CREATE INDEX chat_summary_agent_time IF NOT EXISTS
    FOR (cs:ChatSummary) ON (cs.agent_id, cs.created_at);

    CREATE INDEX chat_summary_session IF NOT EXISTS
    FOR (cs:ChatSummary) ON (cs.session_key);
    """

    DOWN_CYPHER = """
    // =====================================================
    // V5 Chat Summaries Rollback
    // =====================================================

    // 1. Drop indexes
    DROP INDEX chat_summary_session IF EXISTS;
    DROP INDEX chat_summary_agent_time IF EXISTS;

    // 2. Drop constraint
    DROP CONSTRAINT chat_summary_id_unique IF EXISTS;

    // 3. Remove nodes
    MATCH (cs:ChatSummary) DETACH DELETE cs;

    // 4. Update migration control
    MERGE (m:Migration {version: 5})
    SET m.removed_at = datetime();
    """

    @classmethod
    def register(cls, manager: MigrationManager) -> None:
        """Register this migration with a MigrationManager."""
        manager.register_migration(
            version=cls.VERSION,
            name=cls.NAME,
            up_cypher=cls.UP_CYPHER,
            down_cypher=cls.DOWN_CYPHER,
            description=cls.DESCRIPTION
        )

    @classmethod
    def get_summary(cls) -> dict:
        """Get a summary of what this migration creates."""
        return {
            "version": cls.VERSION,
            "name": cls.NAME,
            "description": cls.DESCRIPTION,
            "constraints_created": [
                "chat_summary_id_unique",
            ],
            "indexes_created": [
                "chat_summary_agent_time",
                "chat_summary_session",
            ],
            "node_types": [
                "ChatSummary",
            ],
            "relationship_types": [
                "HAS_SUMMARY",
            ],
        }
