// Neo4j Migration: Proposal System Schema
// Creates constraints and indexes for Kublai's improvement proposal workflow

// =============================================================================
// CONSTRAINTS
// =============================================================================

// ArchitectureProposal - Kublai's suggestions that may become ARCHITECTURE.md sections
CREATE CONSTRAINT proposal_id IF NOT EXISTS
  FOR (p:ArchitectureProposal) REQUIRE p.id IS UNIQUE;

// ImprovementOpportunity - Opportunities identified by Kublai's proactive reflection
CREATE CONSTRAINT opportunity_id IF NOT EXISTS
  FOR (o:ImprovementOpportunity) REQUIRE o.id IS UNIQUE;

// ImprovementProposal - Alternative label used in some implementations
CREATE CONSTRAINT improvement_proposal_id IF NOT EXISTS
  FOR (p:ImprovementProposal) REQUIRE p.id IS UNIQUE;

// =============================================================================
// INDEXES
// =============================================================================

// Query proposals by status
CREATE INDEX proposal_status IF NOT EXISTS
  FOR (p:ArchitectureProposal) ON (p.status);

// Query opportunities by status
CREATE INDEX opportunity_status IF NOT EXISTS
  FOR (o:ImprovementOpportunity) ON (o.status);

// Query by proposer
CREATE INDEX proposal_proposed_by IF NOT EXISTS
  FOR (p:ArchitectureProposal) ON (p.proposed_by);

// Query by implementation status
CREATE INDEX proposal_impl_status IF NOT EXISTS
  FOR (p:ArchitectureProposal) ON (p.implementation_status);

// =============================================================================
// FULLTEXT INDEX (if not exists)
// =============================================================================

// Full-text search across proposal titles and descriptions
CALL apoc.trigger.install('create-proposal-fulltext-if-missing', '
  CALL db.indexes() YIELD name
  WITH collect(name) AS indexes
  CALL apoc.do.when(
    NOT "proposalSearch" IN indexes,
    "CALL db.index.fulltext.createNodeIndex('proposalSearch', ['ArchitectureProposal', 'ImprovementOpportunity'], ['title', 'description'])",
    "RETURN 'Index already exists' AS result",
    {}
  ) YIELD value
  RETURN value
', {phase: 'before'});

// =============================================================================
// RELATIONSHIP PATTERNS (documented for reference)
// =============================================================================

// (:ImprovementOpportunity)-[:EVOLVES_INTO]->(:ArchitectureProposal)
// (:ArchitectureProposal)-[:UPDATES_SECTION]->(:ArchitectureSection)
// (:ArchitectureProposal)-[:VETTED_BY]->(:Vetting)
// (:ArchitectureProposal)-[:IMPLEMENTED_BY]->(:Implementation)
// (:Implementation)-[:VALIDATED_BY]->(:Validation)
// (:ArchitectureProposal)-[:SYNCED_TO]->(:ArchitectureSection)

// =============================================================================
// MIGRATION METADATA
// =============================================================================

MERGE (m:Migration {version: '003'})
SET m.name = 'Proposal System Schema',
    m.applied_at = datetime(),
    m.description = 'Creates constraints and indexes for Kublai proactive self-awareness proposal workflow';
