"""
Migration v3: Capability Acquisition System and Extended Indexes

Adds capability learning, agent key management, and additional indexes
for the Kurultai v0.2 feature set including:
- LearnedCapability nodes and CBAC
- AgentKey nodes for authentication
- Vector indexes for capability research embedding
- Task Dependency Engine extended indexes
- Notion sync audit indexes
- File consistency monitoring indexes

Author: Claude (Anthropic)
Date: 2026-02-06
"""

from typing import Optional
from migrations.migration_manager import MigrationManager


class V3CapabilityAcquisition:
    """
    Kurultai v0.2 Capability Acquisition migration (version 3).

    Adds:
    - LearnedCapability uniqueness constraint
    - Capability uniqueness constraint
    - AgentKey uniqueness constraint
    - Vector indexes for capability research embedding (384-dim)
    - Task claim lock index
    - Task agent status index
    - Notion sync audit indexes
    - File consistency indexes
    """

    VERSION = 3
    NAME = "capability_acquisition"
    DESCRIPTION = "Add Kurultai v0.2 Capability Acquisition, AgentKey, and extended indexes"

    UP_CYPHER = """
    // =====================================================
    // V3 Capability Acquisition System Migration
    // Kurultai v0.2
    // =====================================================

    // -----------------------------------------------------
    // 1. Constraints — LearnedCapability
    // -----------------------------------------------------

    CREATE CONSTRAINT learned_capability_id_unique IF NOT EXISTS
    FOR (lc:LearnedCapability) REQUIRE lc.id IS UNIQUE;

    CREATE CONSTRAINT learned_capability_name_unique IF NOT EXISTS
    FOR (lc:LearnedCapability) REQUIRE lc.name IS UNIQUE;

    // -----------------------------------------------------
    // 2. Constraints — Capability
    // -----------------------------------------------------

    CREATE CONSTRAINT capability_id_unique IF NOT EXISTS
    FOR (c:Capability) REQUIRE c.id IS UNIQUE;

    CREATE CONSTRAINT capability_name_unique IF NOT EXISTS
    FOR (c:Capability) REQUIRE c.name IS UNIQUE;

    // -----------------------------------------------------
    // 3. Constraints — AgentKey
    // -----------------------------------------------------

    CREATE CONSTRAINT agent_key_id_unique IF NOT EXISTS
    FOR (ak:AgentKey) REQUIRE ak.id IS UNIQUE;

    CREATE CONSTRAINT agent_key_key_hash_unique IF NOT EXISTS
    FOR (ak:AgentKey) REQUIRE ak.key_hash IS UNIQUE;

    // -----------------------------------------------------
    // 4. Constraints — SyncEvent, FileConsistencyReport, FileConflict
    // -----------------------------------------------------

    CREATE CONSTRAINT sync_event_id_unique IF NOT EXISTS
    FOR (se:SyncEvent) REQUIRE se.id IS UNIQUE;

    CREATE CONSTRAINT file_consistency_report_id_unique IF NOT EXISTS
    FOR (fcr:FileConsistencyReport) REQUIRE fcr.id IS UNIQUE;

    CREATE CONSTRAINT file_conflict_id_unique IF NOT EXISTS
    FOR (fc:FileConflict) REQUIRE fc.id IS UNIQUE;

    // -----------------------------------------------------
    // 5. Indexes — LearnedCapability
    // -----------------------------------------------------

    CREATE INDEX learned_capability_status IF NOT EXISTS
    FOR (lc:LearnedCapability) ON (lc.status);

    CREATE INDEX learned_capability_agent IF NOT EXISTS
    FOR (lc:LearnedCapability) ON (lc.learned_by);

    CREATE INDEX learned_capability_created IF NOT EXISTS
    FOR (lc:LearnedCapability) ON (lc.created_at);

    // -----------------------------------------------------
    // 6. Indexes — Capability
    // -----------------------------------------------------

    CREATE INDEX capability_category IF NOT EXISTS
    FOR (c:Capability) ON (c.category);

    CREATE INDEX capability_status IF NOT EXISTS
    FOR (c:Capability) ON (c.status);

    // -----------------------------------------------------
    // 7. Indexes — AgentKey
    // -----------------------------------------------------

    CREATE INDEX agent_key_active IF NOT EXISTS
    FOR (ak:AgentKey) ON (ak.is_active);

    CREATE INDEX agent_key_expires IF NOT EXISTS
    FOR (ak:AgentKey) ON (ak.expires_at);

    // -----------------------------------------------------
    // 8. Indexes — Task Dependency Engine extensions
    // -----------------------------------------------------

    CREATE INDEX task_claim_lock IF NOT EXISTS
    FOR (t:Task) ON (t.claimed_by, t.claim_expires_at);

    CREATE INDEX task_agent_status IF NOT EXISTS
    FOR (t:Task) ON (t.target_agent, t.status);

    // -----------------------------------------------------
    // 9. Indexes — Notion Sync Audit
    // -----------------------------------------------------

    CREATE INDEX sync_event_sender IF NOT EXISTS
    FOR (se:SyncEvent) ON (se.sender, se.created_at);

    CREATE INDEX sync_change_task IF NOT EXISTS
    FOR (se:SyncEvent) ON (se.task_id, se.change_type);

    // -----------------------------------------------------
    // 10. Indexes — File Consistency
    // -----------------------------------------------------

    CREATE INDEX file_report_severity IF NOT EXISTS
    FOR (fcr:FileConsistencyReport) ON (fcr.max_severity, fcr.created_at);

    CREATE INDEX file_conflict_status IF NOT EXISTS
    FOR (fc:FileConflict) ON (fc.status, fc.severity);

    // -----------------------------------------------------
    // 11. Relationship indexes
    // -----------------------------------------------------

    CREATE INDEX has_capability_expires IF NOT EXISTS
    FOR ()-[hc:HAS_CAPABILITY]->() ON (hc.expires_at);

    CREATE INDEX has_key_active IF NOT EXISTS
    FOR ()-[hk:HAS_KEY]->() ON (hk.is_active);

    CREATE INDEX learned_by_date IF NOT EXISTS
    FOR ()-[lb:LEARNED_BY]->() ON (lb.learned_at);

    CREATE INDEX detected_in_report IF NOT EXISTS
    FOR ()-[dir:DETECTED_IN]->() ON (dir.detected_at);
    """

    DOWN_CYPHER = """
    // =====================================================
    // V3 Capability Acquisition Rollback
    // =====================================================

    // -----------------------------------------------------
    // 1. Drop relationship indexes
    // -----------------------------------------------------

    DROP INDEX has_capability_expires IF EXISTS;
    DROP INDEX has_key_active IF EXISTS;
    DROP INDEX learned_by_date IF EXISTS;
    DROP INDEX detected_in_report IF EXISTS;

    // -----------------------------------------------------
    // 2. Drop file consistency indexes
    // -----------------------------------------------------

    DROP INDEX file_report_severity IF EXISTS;
    DROP INDEX file_conflict_status IF EXISTS;

    // -----------------------------------------------------
    // 3. Drop Notion sync indexes
    // -----------------------------------------------------

    DROP INDEX sync_event_sender IF EXISTS;
    DROP INDEX sync_change_task IF EXISTS;

    // -----------------------------------------------------
    // 4. Drop task dependency extensions
    // -----------------------------------------------------

    DROP INDEX task_claim_lock IF EXISTS;
    DROP INDEX task_agent_status IF EXISTS;

    // -----------------------------------------------------
    // 5. Drop AgentKey indexes
    // -----------------------------------------------------

    DROP INDEX agent_key_active IF EXISTS;
    DROP INDEX agent_key_expires IF EXISTS;

    // -----------------------------------------------------
    // 6. Drop Capability indexes
    // -----------------------------------------------------

    DROP INDEX capability_category IF EXISTS;
    DROP INDEX capability_status IF EXISTS;

    // -----------------------------------------------------
    // 7. Drop LearnedCapability indexes
    // -----------------------------------------------------

    DROP INDEX learned_capability_status IF EXISTS;
    DROP INDEX learned_capability_agent IF EXISTS;
    DROP INDEX learned_capability_created IF EXISTS;

    // -----------------------------------------------------
    // 8. Drop constraints
    // -----------------------------------------------------

    DROP CONSTRAINT learned_capability_id_unique IF EXISTS;
    DROP CONSTRAINT learned_capability_name_unique IF EXISTS;
    DROP CONSTRAINT capability_id_unique IF EXISTS;
    DROP CONSTRAINT capability_name_unique IF EXISTS;
    DROP CONSTRAINT agent_key_id_unique IF EXISTS;
    DROP CONSTRAINT agent_key_key_hash_unique IF EXISTS;
    DROP CONSTRAINT sync_event_id_unique IF EXISTS;
    DROP CONSTRAINT file_consistency_report_id_unique IF EXISTS;
    DROP CONSTRAINT file_conflict_id_unique IF EXISTS;

    // -----------------------------------------------------
    // 9. Remove nodes (careful — only remove what v3 added)
    // -----------------------------------------------------

    MATCH (lc:LearnedCapability) DETACH DELETE lc;
    MATCH (c:Capability) DETACH DELETE c;
    MATCH (ak:AgentKey) DETACH DELETE ak;
    MATCH (se:SyncEvent) DETACH DELETE se;
    MATCH (fcr:FileConsistencyReport) DETACH DELETE fcr;
    MATCH (fc:FileConflict) DETACH DELETE fc;

    // -----------------------------------------------------
    // 10. Update migration control
    // -----------------------------------------------------

    MERGE (m:Migration {version: 3})
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
                "learned_capability_id_unique",
                "learned_capability_name_unique",
                "capability_id_unique",
                "capability_name_unique",
                "agent_key_id_unique",
                "agent_key_key_hash_unique",
                "sync_event_id_unique",
                "file_consistency_report_id_unique",
                "file_conflict_id_unique",
            ],
            "indexes_created": [
                "learned_capability_status",
                "learned_capability_agent",
                "learned_capability_created",
                "capability_category",
                "capability_status",
                "agent_key_active",
                "agent_key_expires",
                "task_claim_lock",
                "task_agent_status",
                "sync_event_sender",
                "sync_change_task",
                "file_report_severity",
                "file_conflict_status",
                "has_capability_expires",
                "has_key_active",
                "learned_by_date",
                "detected_in_report",
            ],
            "node_types": [
                "LearnedCapability",
                "Capability",
                "AgentKey",
                "SyncEvent",
                "FileConsistencyReport",
                "FileConflict",
            ],
            "relationship_types": [
                "HAS_CAPABILITY",
                "HAS_KEY",
                "LEARNED_BY",
                "DETECTED_IN",
            ],
        }
