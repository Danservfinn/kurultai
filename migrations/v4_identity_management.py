"""Identity Management System - Neo4j Schema Migration

Creates the foundational schema for tracking people, their contexts,
and privacy-sensitive information in the Kurultai system.

Schema includes:
- Person nodes for identity tracking
- Fact nodes with privacy levels
- Preference nodes for user preferences
- Conversation nodes for context
- AuditLog for privacy enforcement tracking
"""

from typing import Optional
from migrations.migration_manager import MigrationManager


class V4IdentityManagement:
    """
    Identity Management System migration (version 4).

    Creates schema for:
    - Person identity tracking
    - Privacy-aware fact storage
    - Context memory with conversations
    - Audit logging for sensitive data access
    """

    VERSION = 4
    NAME = "identity_management"
    DESCRIPTION = "Create Identity Management System schema for person tracking and privacy enforcement"

    UP_CYPHER = """
    // =====================================================
    // V4 Identity Management System Migration
    // Kurultai - Identity & Privacy Schema
    // =====================================================

    // -----------------------------------------------------
    // 1. Constraints - Data Integrity
    // -----------------------------------------------------

    // Person.id must be unique (format: "channel:identifier")
    CREATE CONSTRAINT person_id_unique IF NOT EXISTS
    FOR (p:Person) REQUIRE p.id IS UNIQUE;

    // Fact.id must be unique
    CREATE CONSTRAINT fact_id_unique IF NOT EXISTS
    FOR (f:Fact) REQUIRE f.id IS UNIQUE;

    // Preference.id must be unique
    CREATE CONSTRAINT preference_id_unique IF NOT EXISTS
    FOR (pref:Preference) REQUIRE pref.id IS UNIQUE;

    // Conversation.id must be unique
    CREATE CONSTRAINT conversation_id_unique IF NOT EXISTS
    FOR (c:Conversation) REQUIRE c.id IS UNIQUE;

    // AuditLog.id must be unique
    CREATE CONSTRAINT audit_log_id_unique IF NOT EXISTS
    FOR (a:AuditLog) REQUIRE a.id IS UNIQUE;

    // Topic.id must be unique
    CREATE CONSTRAINT topic_id_unique IF NOT EXISTS
    FOR (t:Topic) REQUIRE t.id IS UNIQUE;

    // -----------------------------------------------------
    // 2. Indexes - Person Lookup Performance
    // -----------------------------------------------------

    // Person lookups by channel and handle
    CREATE INDEX person_channel_lookup IF NOT EXISTS
    FOR (p:Person) ON (p.channel, p.handle);

    // Person lookups by name
    CREATE INDEX person_name_lookup IF NOT EXISTS
    FOR (p:Person) ON (p.name);

    // Active persons
    CREATE INDEX person_active_lookup IF NOT EXISTS
    FOR (p:Person) ON (p.is_active, p.last_seen);

    // Person sender hash for isolation
    CREATE INDEX person_sender_hash_lookup IF NOT EXISTS
    FOR (p:Person) ON (p.sender_hash);

    // -----------------------------------------------------
    // 3. Indexes - Fact Queries
    // -----------------------------------------------------

    // Fact lookups by person
    CREATE INDEX fact_person_lookup IF NOT EXISTS
    FOR (f:Fact) ON (f.person_id, f.created_at);

    // Fact lookups by type
    CREATE INDEX fact_type_lookup IF NOT EXISTS
    FOR (f:Fact) ON (f.fact_type, f.privacy_level);

    // Fact lookups by privacy level
    CREATE INDEX fact_privacy_lookup IF NOT EXISTS
    FOR (f:Fact) ON (f.privacy_level, f.person_id);

    // Fact confidence filtering
    CREATE INDEX fact_confidence_lookup IF NOT EXISTS
    FOR (f:Fact) ON (f.confidence);

    // Fact key lookups
    CREATE INDEX fact_key_lookup IF NOT EXISTS
    FOR (f:Fact) ON (f.fact_key, f.person_id);

    // -----------------------------------------------------
    // 4. Indexes - Preference Queries
    // -----------------------------------------------------

    // Preference lookups by person
    CREATE INDEX preference_person_lookup IF NOT EXISTS
    FOR (p:Preference) ON (p.person_id, p.category);

    // Preference by key
    CREATE INDEX preference_key_lookup IF NOT EXISTS
    FOR (p:Preference) ON (p.pref_key, p.person_id);

    // -----------------------------------------------------
    // 5. Indexes - Conversation Queries
    // -----------------------------------------------------

    // Conversation lookups by person
    CREATE INDEX conversation_person_lookup IF NOT EXISTS
    FOR (c:Conversation) ON (c.person_id, c.timestamp);

    // Conversation by time range
    CREATE INDEX conversation_time_lookup IF NOT EXISTS
    FOR (c:Conversation) ON (c.timestamp);

    // Conversation by channel
    CREATE INDEX conversation_channel_lookup IF NOT EXISTS
    FOR (c:Conversation) ON (c.channel, c.timestamp);

    // -----------------------------------------------------
    // 6. Indexes - Topic Tracking
    // -----------------------------------------------------

    // Topic lookups
    CREATE INDEX topic_name_lookup IF NOT EXISTS
    FOR (t:Topic) ON (t.name);

    // Topic frequency
    CREATE INDEX topic_frequency_lookup IF NOT EXISTS
    FOR (t:Topic) ON (t.frequency);

    // -----------------------------------------------------
    // 7. Indexes - Audit Log
    // -----------------------------------------------------

    // Audit log lookups
    CREATE INDEX audit_person_lookup IF NOT EXISTS
    FOR (a:AuditLog) ON (a.person_id, a.accessed_at);

    // Audit by action type
    CREATE INDEX audit_action_lookup IF NOT EXISTS
    FOR (a:AuditLog) ON (a.action_type, a.accessed_at);

    // Audit by accessor
    CREATE INDEX audit_accessor_lookup IF NOT EXISTS
    FOR (a:AuditLog) ON (a.accessed_by, a.accessed_at);

    // Audit retention
    CREATE INDEX audit_retention_lookup IF NOT EXISTS
    FOR (a:AuditLog) ON (a.retain_until)
    WHERE a.retain_until IS NOT NULL;

    // -----------------------------------------------------
    // 8. Vector Index - Conversation Embeddings
    // -----------------------------------------------------

    CREATE VECTOR INDEX conversation_embedding IF NOT EXISTS
    FOR (c:Conversation) ON (c.embedding)
    OPTIONS {indexConfig: {`vector.dimensions`: 384, `vector.similarity_function`: 'cosine'}};

    // -----------------------------------------------------
    // 9. Full-Text Index - Content Search
    // -----------------------------------------------------

    CREATE FULLTEXT INDEX fact_content_search IF NOT EXISTS
    FOR (f:Fact) ON EACH [f.fact_value];

    CREATE FULLTEXT INDEX conversation_content_search IF NOT EXISTS
    FOR (c:Conversation) ON EACH [c.summary, c.content_snippet];

    // -----------------------------------------------------
    // 10. Migration Control Node
    // -----------------------------------------------------

    MERGE (mc:MigrationControl {id: 'identity_management'})
    ON CREATE SET
        mc.version = 4,
        mc.last_updated = datetime(),
        mc.created_at = datetime()
    ON MATCH SET
        mc.version = 4,
        mc.last_updated = datetime();

    // -----------------------------------------------------
    // 11. System Configuration - Privacy Defaults
    // -----------------------------------------------------

    MERGE (ipc:IdentityPrivacyConfig {id: 'default'})
    ON CREATE SET
        ipc.default_fact_privacy = 'public',
        ipc.default_preference_privacy = 'private',
        ipc.retain_audit_logs_days = 90,
        ipc.auto_archive_conversations_days = 30,
        ipc.max_conversation_history = 100,
        ipc.enable_privacy_filtering = true,
        ipc.enable_audit_logging = true,
        ipc.created_at = datetime()
    ON MATCH SET
        ipc.last_updated = datetime();

    // -----------------------------------------------------
    // 12. Record Migration Success
    // -----------------------------------------------------

    MERGE (m:Migration {version: 4})
    ON CREATE SET
        m.name = 'identity_management',
        m.description = 'Create Identity Management System schema',
        m.applied_at = datetime(),
        m.success = true,
        m.execution_time_ms = 0
    ON MATCH SET
        m.applied_at = datetime(),
        m.success = true;
    """

    DOWN_CYPHER = """
    // =====================================================
    // V4 Identity Management Rollback
    // =====================================================

    // -----------------------------------------------------
    // 1. Drop Full-Text Indexes
    // -----------------------------------------------------
    DROP INDEX fact_content_search IF EXISTS;
    DROP INDEX conversation_content_search IF EXISTS;

    // -----------------------------------------------------
    // 2. Drop Vector Indexes
    // -----------------------------------------------------
    DROP INDEX conversation_embedding IF EXISTS;

    // -----------------------------------------------------
    // 3. Drop Audit Log Indexes
    // -----------------------------------------------------
    DROP INDEX audit_person_lookup IF EXISTS;
    DROP INDEX audit_action_lookup IF EXISTS;
    DROP INDEX audit_accessor_lookup IF EXISTS;
    DROP INDEX audit_retention_lookup IF EXISTS;

    // -----------------------------------------------------
    // 4. Drop Topic Indexes
    // -----------------------------------------------------
    DROP INDEX topic_name_lookup IF EXISTS;
    DROP INDEX topic_frequency_lookup IF EXISTS;

    // -----------------------------------------------------
    // 5. Drop Conversation Indexes
    // -----------------------------------------------------
    DROP INDEX conversation_person_lookup IF EXISTS;
    DROP INDEX conversation_time_lookup IF EXISTS;
    DROP INDEX conversation_channel_lookup IF EXISTS;

    // -----------------------------------------------------
    // 6. Drop Preference Indexes
    // -----------------------------------------------------
    DROP INDEX preference_person_lookup IF EXISTS;
    DROP INDEX preference_key_lookup IF EXISTS;

    // -----------------------------------------------------
    // 7. Drop Fact Indexes
    // -----------------------------------------------------
    DROP INDEX fact_person_lookup IF EXISTS;
    DROP INDEX fact_type_lookup IF EXISTS;
    DROP INDEX fact_privacy_lookup IF EXISTS;
    DROP INDEX fact_confidence_lookup IF EXISTS;
    DROP INDEX fact_key_lookup IF EXISTS;

    // -----------------------------------------------------
    // 8. Drop Person Indexes
    // -----------------------------------------------------
    DROP INDEX person_channel_lookup IF EXISTS;
    DROP INDEX person_name_lookup IF EXISTS;
    DROP INDEX person_active_lookup IF EXISTS;
    DROP INDEX person_sender_hash_lookup IF EXISTS;

    // -----------------------------------------------------
    // 9. Drop Constraints
    // -----------------------------------------------------
    DROP CONSTRAINT person_id_unique IF EXISTS;
    DROP CONSTRAINT fact_id_unique IF EXISTS;
    DROP CONSTRAINT preference_id_unique IF EXISTS;
    DROP CONSTRAINT conversation_id_unique IF EXISTS;
    DROP CONSTRAINT audit_log_id_unique IF EXISTS;
    DROP CONSTRAINT topic_id_unique IF EXISTS;

    // -----------------------------------------------------
    // 10. Remove Configuration Node
    // -----------------------------------------------------
    MATCH (ipc:IdentityPrivacyConfig) DELETE ipc;

    // -----------------------------------------------------
    // 11. Remove Migration Control Node
    // -----------------------------------------------------
    MATCH (mc:MigrationControl {id: 'identity_management'}) DELETE mc;

    // -----------------------------------------------------
    // 12. Remove Migration Record
    // -----------------------------------------------------
    MATCH (m:Migration {version: 4}) DELETE m;
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
            "constraints_created": 6,
            "indexes_created": 20,
            "vector_indexes": 1,
            "fulltext_indexes": 2,
            "node_types": [
                "Person",
                "Fact",
                "Preference",
                "Conversation",
                "Topic",
                "AuditLog",
                "IdentityPrivacyConfig"
            ],
            "relationship_types": [
                "HAS_FACT",
                "HAS_PREFERENCE",
                "PARTICIPATED_IN",
                "DISCUSSED_TOPIC",
                "RELATED_TO",
                "ACCESS_AUDIT"
            ]
        }


def run_identity_management_migration(
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str
) -> bool:
    """Convenience function to run the identity management migration."""
    with MigrationManager(neo4j_uri, neo4j_user, neo4j_password) as manager:
        V4IdentityManagement.register(manager)
        return manager.migrate(target_version=4)


if __name__ == "__main__":
    import os
    import sys

    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD")

    if not password:
        print("Error: NEO4J_PASSWORD environment variable required")
        sys.exit(1)

    print(f"Running identity management migration to {uri}...")

    try:
        success = run_identity_management_migration(uri, user, password)
        if success:
            print("Migration completed successfully!")
            sys.exit(0)
        else:
            print("Migration failed!")
            sys.exit(1)
    except Exception as e:
        print(f"Migration error: {e}")
        sys.exit(1)
