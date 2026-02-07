"""
Migration v4: Kublai Self-Awareness Proposal System

Adds proposal workflow nodes for Kublai's proactive architecture improvement system:
- ArchitectureProposal - Proposals for ARCHITECTURE.md changes
- ImprovementOpportunity - Gaps identified by Kublai's reflection
- Vetting - Ögedei's operational impact assessment
- Implementation - Temüjin's implementation tracking
- Validation - Validation checks before allowing sync

GUARDRAIL (CRITICAL):
Only validated+implemented proposals can sync to ARCHITECTURE.md.

Since Neo4j does not support conditional relationship constraints, this guardrail
MUST be enforced at the application layer. See: src/workflow/guardrail-enforcer.js

The schema provides the structure (indexes, relationships) but application code
must verify BOTH conditions before creating SYNCED_TO relationships:
  1. proposal.status = 'validated'
  2. proposal.implementation_status = 'completed'
  3. A Validation node exists with passed = true

See docs/operations/guardrail-enforcement.md for implementation details.

Author: Claude (Anthropic)
Date: 2026-02-07
"""

from typing import Optional
from migrations.migration_manager import MigrationManager


class V4Proposals:
    """
    Kurultai v0.2 Kublai Self-Awareness Proposal System migration (version 4).

    Adds:
    - ArchitectureProposal uniqueness constraint
    - ImprovementOpportunity uniqueness constraint
    - Vetting uniqueness constraint
    - Implementation uniqueness constraint
    - Validation uniqueness constraint
    - Status and priority indexes
    """

    VERSION = 4
    NAME = "kublai_proposal_system"
    DESCRIPTION = "Add Kublai Self-Awareness Proposal Workflow with guardrails"

    UP_CYPHER = """
    // =====================================================
    // V4 Kublai Self-Awareness Proposal System Migration
    // Kurultai v0.2
    // =====================================================

    // -----------------------------------------------------
    // 1. Constraints — ArchitectureProposal
    // -----------------------------------------------------

    CREATE CONSTRAINT proposal_id_unique IF NOT EXISTS
    FOR (p:ArchitectureProposal) REQUIRE p.id IS UNIQUE;

    // -----------------------------------------------------
    // 2. Constraints — ImprovementOpportunity
    // -----------------------------------------------------

    CREATE CONSTRAINT opportunity_id_unique IF NOT EXISTS
    FOR (o:ImprovementOpportunity) REQUIRE o.id IS UNIQUE;

    // -----------------------------------------------------
    // 3. Constraints — Vetting
    // -----------------------------------------------------

    CREATE CONSTRAINT vetting_id_unique IF NOT EXISTS
    FOR (v:Vetting) REQUIRE v.id IS UNIQUE;

    // -----------------------------------------------------
    // 4. Constraints — Implementation
    // -----------------------------------------------------

    CREATE CONSTRAINT implementation_id_unique IF NOT EXISTS
    FOR (i:Implementation) REQUIRE i.id IS UNIQUE;

    // -----------------------------------------------------
    // 5. Constraints — Validation
    // -----------------------------------------------------

    CREATE CONSTRAINT validation_id_unique IF NOT EXISTS
    FOR (v:Validation) REQUIRE v.id IS UNIQUE;

    // -----------------------------------------------------
    // 6. Indexes — ArchitectureProposal
    // -----------------------------------------------------

    CREATE INDEX proposal_status IF NOT EXISTS
    FOR (p:ArchitectureProposal) ON (p.status);

    CREATE INDEX proposal_priority IF NOT EXISTS
    FOR (p:ArchitectureProposal) ON (p.priority);

    CREATE INDEX proposal_created_at IF NOT EXISTS
    FOR (p:ArchitectureProposal) ON (p.created_at);

    CREATE INDEX proposal_implementation_status IF NOT EXISTS
    FOR (p:ArchitectureProposal) ON (p.implementation_status);

    // -----------------------------------------------------
    // 7. Indexes — ImprovementOpportunity
    // -----------------------------------------------------

    CREATE INDEX opportunity_status IF NOT EXISTS
    FOR (o:ImprovementOpportunity) ON (o.status);

    CREATE INDEX opportunity_priority IF NOT EXISTS
    FOR (o:ImprovementOpportunity) ON (o.priority);

    CREATE INDEX opportunity_type IF NOT EXISTS
    FOR (o:ImprovementOpportunity) ON (o.type);

    CREATE INDEX opportunity_proposed_by IF NOT EXISTS
    FOR (o:ImprovementOpportunity) ON (o.proposed_by);

    // -----------------------------------------------------
    // 8. Indexes — Vetting
    // -----------------------------------------------------

    CREATE INDEX vetting_proposal IF NOT EXISTS
    FOR (v:Vetting) ON (v.proposal_id);

    CREATE INDEX vetting_vetted_by IF NOT EXISTS
    FOR (v:Vetting) ON (v.vetted_by);

    CREATE INDEX vetting_created_at IF NOT EXISTS
    FOR (v:Vetting) ON (v.created_at);

    // -----------------------------------------------------
    // 9. Indexes — Implementation
    // -----------------------------------------------------

    CREATE INDEX implementation_proposal IF NOT EXISTS
    FOR (i:Implementation) ON (i.proposal_id);

    CREATE INDEX implementation_status IF NOT EXISTS
    FOR (i:Implementation) ON (i.status);

    CREATE INDEX implementation_started_at IF NOT EXISTS
    FOR (i:Implementation) ON (i.started_at);

    // -----------------------------------------------------
    // 10. Indexes — Validation
    // -----------------------------------------------------

    CREATE INDEX validation_implementation IF NOT EXISTS
    FOR (v:Validation) ON (v.implementation_id);

    CREATE INDEX validation_passed IF NOT EXISTS
    FOR (v:Validation) ON (v.passed);

    CREATE INDEX validation_validated_at IF NOT EXISTS
    FOR (v:Validation) ON (v.validated_at);

    // -----------------------------------------------------
    // 11. Relationship indexes
    // -----------------------------------------------------

    CREATE INDEX evolves_into IF NOT EXISTS
    FOR ()-[r:EVOLVES_INTO]->() ON (r.created_at);

    CREATE INDEX updates_section IF NOT EXISTS
    FOR ()-[r:UPDATES_SECTION]->() ON (r.target_section);

    CREATE INDEX synced_to IF NOT EXISTS
    FOR ()-[r:SYNCED_TO]->() ON (r.synced_at);

    CREATE INDEX has_vetting IF NOT EXISTS
    FOR ()-[r:HAS_VETTING]->() ON (r.created_at);

    CREATE INDEX implemented_by IF NOT EXISTS
    FOR ()-[r:IMPLEMENTED_BY]->() ON (r.started_at);

    CREATE INDEX validated_by IF NOT EXISTS
    FOR ()-[r:VALIDATED_BY]->() ON (r.validated_at);
    """

    DOWN_CYPHER = """
    // =====================================================
    // V4 Proposal System Rollback
    // =====================================================
    //
    // SECURITY NOTE: Dropping constraints and nodes will permanently
    // remove all proposal workflow data. Ensure application layer
    // guardrails are also removed when downgrading.
    //
    // Order of operations:
    // 1. Drop relationship indexes (6)
    // 2. Drop Validation indexes (3)
    // 3. Drop Implementation indexes (3)
    // 4. Drop Vetting indexes (3)
    // 5. Drop ImprovementOpportunity indexes (4)
    // 6. Drop ArchitectureProposal indexes (4)
    // 7. Drop all 5 uniqueness constraints
    // 8. Delete all 5 node types with DETACH
    // 9. Mark migration as removed
    //
    // Total: 5 constraints, 21 indexes, 5 node types

    // -----------------------------------------------------
    // 1. Drop relationship indexes
    // -----------------------------------------------------

    DROP INDEX evolves_into IF EXISTS;
    DROP INDEX updates_section IF EXISTS;
    DROP INDEX synced_to IF EXISTS;
    DROP INDEX has_vetting IF EXISTS;
    DROP INDEX implemented_by IF EXISTS;
    DROP INDEX validated_by IF EXISTS;

    // -----------------------------------------------------
    // 2. Drop Validation indexes
    // -----------------------------------------------------

    DROP INDEX validation_implementation IF EXISTS;
    DROP INDEX validation_passed IF EXISTS;
    DROP INDEX validation_validated_at IF EXISTS;

    // -----------------------------------------------------
    // 3. Drop Implementation indexes
    // -----------------------------------------------------

    DROP INDEX implementation_proposal IF EXISTS;
    DROP INDEX implementation_status IF EXISTS;
    DROP INDEX implementation_started_at IF EXISTS;

    // -----------------------------------------------------
    // 4. Drop Vetting indexes
    // -----------------------------------------------------

    DROP INDEX vetting_proposal IF EXISTS;
    DROP INDEX vetting_vetted_by IF EXISTS;
    DROP INDEX vetting_created_at IF EXISTS;

    // -----------------------------------------------------
    // 5. Drop ImprovementOpportunity indexes
    // -----------------------------------------------------

    DROP INDEX opportunity_status IF EXISTS;
    DROP INDEX opportunity_priority IF EXISTS;
    DROP INDEX opportunity_type IF EXISTS;
    DROP INDEX opportunity_proposed_by IF EXISTS;

    // -----------------------------------------------------
    // 6. Drop ArchitectureProposal indexes
    // -----------------------------------------------------

    DROP INDEX proposal_status IF EXISTS;
    DROP INDEX proposal_priority IF EXISTS;
    DROP INDEX proposal_created_at IF EXISTS;
    DROP INDEX proposal_implementation_status IF EXISTS;

    // -----------------------------------------------------
    // 7. Drop constraints
    // -----------------------------------------------------

    DROP CONSTRAINT proposal_id_unique IF EXISTS;
    DROP CONSTRAINT opportunity_id_unique IF EXISTS;
    DROP CONSTRAINT vetting_id_unique IF EXISTS;
    DROP CONSTRAINT implementation_id_unique IF EXISTS;
    DROP CONSTRAINT validation_id_unique IF EXISTS;

    // -----------------------------------------------------
    // 8. Remove nodes
    // -----------------------------------------------------

    MATCH (ap:ArchitectureProposal) DETACH DELETE ap;
    MATCH (io:ImprovementOpportunity) DETACH DELETE io;
    MATCH (v:Vetting) DETACH DELETE v;
    MATCH (i:Implementation) DETACH DELETE i;
    MATCH (v:Validation) DETACH DELETE v;

    // -----------------------------------------------------
    // 9. Update migration control
    // -----------------------------------------------------

    MERGE (m:Migration {version: 4})
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
                "proposal_id_unique",
                "opportunity_id_unique",
                "vetting_id_unique",
                "implementation_id_unique",
                "validation_id_unique",
            ],
            "indexes_created": [
                "proposal_status",
                "proposal_priority",
                "proposal_created_at",
                "proposal_implementation_status",
                "opportunity_status",
                "opportunity_priority",
                "opportunity_type",
                "opportunity_proposed_by",
                "vetting_proposal",
                "vetting_vetted_by",
                "vetting_created_at",
                "implementation_proposal",
                "implementation_status",
                "implementation_started_at",
                "validation_implementation",
                "validation_passed",
                "validation_validated_at",
                "evolves_into",
                "updates_section",
                "synced_to",
                "has_vetting",
                "implemented_by",
                "validated_by",
            ],
            "node_types": [
                "ArchitectureProposal",
                "ImprovementOpportunity",
                "Vetting",
                "Implementation",
                "Validation",
            ],
            "relationship_types": [
                "EVOLVES_INTO",
                "UPDATES_SECTION",
                "HAS_VETTING",
                "IMPLEMENTED_BY",
                "VALIDATED_BY",
                "SYNCED_TO",
            ],
        }
