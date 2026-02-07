/**
 * Proposal System Migration
 *
 * Creates node types and constraints for the improvement proposal workflow.
 * This enables Kublai to propose, track, and validate architectural improvements.
 *
 * Workflow: Opportunity → Proposal → Ögedei Vetting → Approval → Temüjin Implementation → Validation → Sync
 */

// ArchitectureProposal - Proposals that may become ARCHITECTURE.md sections
CREATE CONSTRAINT proposal_id IF NOT EXISTS FOR (p:ArchitectureProposal) REQUIRE p.id IS UNIQUE;

// ImprovementOpportunity - Opportunities identified by Kublai
CREATE CONSTRAINT opportunity_id IF NOT EXISTS FOR (o:ImprovementOpportunity) REQUIRE o.id IS UNIQUE;

// Vetting - Ögedei's operational assessment of proposals
CREATE CONSTRAINT vetting_id IF NOT EXISTS FOR (v:Vetting) REQUIRE v.id IS UNIQUE;

// Implementation - Temüjin's implementation record
CREATE CONSTRAINT implementation_id IF NOT EXISTS FOR (i:Implementation) REQUIRE i.id IS UNIQUE;

// Validation - Validation checks for implementations
CREATE CONSTRAINT validation_id IF NOT EXISTS FOR (v:Validation) REQUIRE v.id IS UNIQUE;

// Relationship patterns (documented for reference):
// (:ImprovementOpportunity)-[:EVOLVES_INTO]->(:ArchitectureProposal)
// (:ArchitectureProposal)-[:UPDATES_SECTION]->(:ArchitectureSection)
// (:ArchitectureProposal)-[:HAS_VETTING]->(:Vetting)
// (:Vetting)-[:ASSESSS]->(:ArchitectureProposal)
// (:ArchitectureProposal)-[:IMPLEMENTED_BY]->(:Implementation)
// (:Implementation)-[:VALIDATED_BY]->(:Validation)
// (:ArchitectureProposal)-[:SYNCED_TO]->(:ArchitectureSection)

// Index for querying proposals by status
CREATE INDEX proposal_status IF NOT EXISTS FOR (p:ArchitectureProposal) ON (p.status);

// Index for querying opportunities by status
CREATE INDEX opportunity_status IF NOT EXISTS FOR (o:ImprovementOpportunity) ON (o.status);

// Index for querying proposals by priority
CREATE INDEX proposal_priority IF NOT EXISTS FOR (p:ArchitectureProposal) ON (p.priority);
