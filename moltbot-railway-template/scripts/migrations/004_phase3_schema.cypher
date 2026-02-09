"""
Neo4j Schema Completion for Phase 3

Creates missing node types and indexes for full ARCHITECTURE.md compliance.
"""

from neo4j import GraphDatabase
import os

SCHEMA_CYPHER = """
// =====================================================
// PHASE 3: NEO4J SCHEMA COMPLETION
// =====================================================

// ---------------------------------------------
// 1. HeartbeatCycle Nodes
// ---------------------------------------------
CREATE CONSTRAINT heartbeat_cycle_id IF NOT EXISTS
FOR (hc:HeartbeatCycle) REQUIRE hc.id IS UNIQUE;

CREATE INDEX heartbeat_cycle_number_idx IF NOT EXISTS
FOR (hc:HeartbeatCycle) ON (hc.cycle_number);

CREATE INDEX heartbeat_cycle_timestamp_idx IF NOT EXISTS
FOR (hc:HeartbeatCycle) ON (hc.started_at);

// ---------------------------------------------
// 2. TaskResult Nodes
// ---------------------------------------------
CREATE CONSTRAINT taskresult_id IF NOT EXISTS
FOR (tr:TaskResult) REQUIRE tr.id IS UNIQUE;

CREATE INDEX taskresult_agent_idx IF NOT EXISTS
FOR (tr:TaskResult) ON (tr.agent);

CREATE INDEX taskresult_status_idx IF NOT EXISTS
FOR (tr:TaskResult) ON (tr.status);

CREATE INDEX taskresult_timestamp_idx IF NOT EXISTS
FOR (tr:TaskResult) ON (tr.started_at);

// ---------------------------------------------
// 3. Research Nodes
// ---------------------------------------------
CREATE CONSTRAINT research_id IF NOT EXISTS
FOR (r:Research) REQUIRE r.id IS UNIQUE;

CREATE INDEX research_type_idx IF NOT EXISTS
FOR (r:Research) ON (r.research_type);

CREATE INDEX research_agent_idx IF NOT EXISTS
FOR (r:Research) ON (r.agent);

CREATE INDEX research_reliability_idx IF NOT EXISTS
FOR (r:Research) ON (r.reliability_score);

// Vector index for similarity search (requires Neo4j 5.x GDS)
// CREATE VECTOR INDEX research_embedding_idx IF NOT EXISTS
// FOR (r:Research) ON (r.embedding)
// OPTIONS {indexConfig: {`vector.dimensions`: 384, `vector.similarity_function`: 'cosine'}};

// ---------------------------------------------
// 4. LearnedCapability Nodes
// ---------------------------------------------
CREATE CONSTRAINT learned_capability_id IF NOT EXISTS
FOR (lc:LearnedCapability) REQUIRE lc.id IS UNIQUE;

CREATE CONSTRAINT learned_capability_name IF NOT EXISTS
FOR (lc:LearnedCapability) REQUIRE lc.name IS UNIQUE;

CREATE INDEX learned_capability_agent_idx IF NOT EXISTS
FOR (lc:LearnedCapability) ON (lc.agent);

CREATE INDEX learned_capability_status_idx IF NOT EXISTS
FOR (lc:LearnedCapability) ON (lc.status);

CREATE INDEX learned_capability_mastery_idx IF NOT EXISTS
FOR (lc:LearnedCapability) ON (lc.mastery_score);

// ---------------------------------------------
// 5. Capability Nodes (CBAC)
// ---------------------------------------------
CREATE CONSTRAINT capability_id IF NOT EXISTS
FOR (c:Capability) REQUIRE c.id IS UNIQUE;

CREATE CONSTRAINT capability_name IF NOT EXISTS
FOR (c:Capability) REQUIRE c.name IS UNIQUE;

CREATE INDEX capability_risk_idx IF NOT EXISTS
FOR (c:Capability) ON (c.risk_level);

// ---------------------------------------------
// 6. Analysis Nodes
// ---------------------------------------------
CREATE CONSTRAINT analysis_id IF NOT EXISTS
FOR (a:Analysis) REQUIRE a.id IS UNIQUE;

CREATE INDEX analysis_agent_idx IF NOT EXISTS
FOR (a:Analysis) ON (a.agent);

CREATE INDEX analysis_target_idx IF NOT EXISTS
FOR (a:Analysis) ON (a.target_agent);

CREATE INDEX analysis_type_idx IF NOT EXISTS
FOR (a:Analysis) ON (a.analysis_type);

CREATE INDEX analysis_severity_idx IF NOT EXISTS
FOR (a:Analysis) ON (a.severity);

CREATE INDEX analysis_status_idx IF NOT EXISTS
FOR (a:Analysis) ON (a.status);

// ---------------------------------------------
// 7. ArchitectureSection Nodes
// ---------------------------------------------
CREATE CONSTRAINT arch_section_id IF NOT EXISTS
FOR (as:ArchitectureSection) REQUIRE as.id IS UNIQUE;

CREATE CONSTRAINT arch_section_title IF NOT EXISTS
FOR (as:ArchitectureSection) REQUIRE as.title IS UNIQUE;

CREATE INDEX arch_section_category_idx IF NOT EXISTS
FOR (as:ArchitectureSection) ON (as.category);

CREATE INDEX arch_section_updated_idx IF NOT EXISTS
FOR (as:ArchitectureSection) ON (as.last_updated);

// ---------------------------------------------
// 8. ImprovementOpportunity Nodes
// ---------------------------------------------
CREATE CONSTRAINT opportunity_id IF NOT EXISTS
FOR (io:ImprovementOpportunity) REQUIRE io.id IS UNIQUE;

CREATE INDEX opportunity_type_idx IF NOT EXISTS
FOR (io:ImprovementOpportunity) ON (io.type);

CREATE INDEX opportunity_status_idx IF NOT EXISTS
FOR (io:ImprovementOpportunity) ON (io.status);

CREATE INDEX opportunity_priority_idx IF NOT EXISTS
FOR (io:ImprovementOpportunity) ON (io.priority);

// ---------------------------------------------
// 9. ArchitectureProposal Nodes
// ---------------------------------------------
CREATE CONSTRAINT proposal_id IF NOT EXISTS
FOR (ap:ArchitectureProposal) REQUIRE ap.id IS UNIQUE;

CREATE INDEX proposal_status_idx IF NOT EXISTS
FOR (ap:ArchitectureProposal) ON (ap.status);

CREATE INDEX proposal_impl_status_idx IF NOT EXISTS
FOR (ap:ArchitectureProposal) ON (ap.implementation_status);

CREATE INDEX proposal_created_idx IF NOT EXISTS
FOR (ap:ArchitectureProposal) ON (ap.proposed_at);

// ---------------------------------------------
// 10. Vetting, Implementation, Validation Nodes
// ---------------------------------------------
CREATE CONSTRAINT vetting_id IF NOT EXISTS
FOR (v:Vetting) REQUIRE v.id IS UNIQUE;

CREATE CONSTRAINT implementation_id IF NOT EXISTS
FOR (i:Implementation) REQUIRE i.id IS UNIQUE;

CREATE CONSTRAINT validation_id IF NOT EXISTS
FOR (val:Validation) REQUIRE val.id IS UNIQUE;

// ---------------------------------------------
// 11. AgentSpawn Tracking Nodes
// ---------------------------------------------
CREATE CONSTRAINT agent_spawn_id IF NOT EXISTS
FOR (as:AgentSpawn) REQUIRE as.id IS UNIQUE;

CREATE INDEX agent_spawn_agent_idx IF NOT EXISTS
FOR (as:AgentSpawn) ON (as.agent);

CREATE INDEX agent_spawn_timestamp_idx IF NOT EXISTS
FOR (as:AgentSpawn) ON (as.triggered_at);

// ---------------------------------------------
// 12. Memory Node MVS Properties
// ---------------------------------------------
CREATE INDEX memory_mvs_score_idx IF NOT EXISTS
FOR (m:MemoryEntry) ON (m.mvs_score);

CREATE INDEX memory_curation_action_idx IF NOT EXISTS
FOR (m:MemoryEntry) ON (m.curation_action);

CREATE INDEX memory_tombstone_idx IF NOT EXISTS
FOR (m:MemoryEntry) ON (m.tombstone);

// ---------------------------------------------
// 13. HealthCheck Nodes
// ---------------------------------------------
CREATE CONSTRAINT healthcheck_id IF NOT EXISTS
FOR (hc:HealthCheck) REQUIRE hc.id IS UNIQUE;

CREATE INDEX healthcheck_timestamp_idx IF NOT EXISTS
FOR (hc:HealthCheck) ON (hc.timestamp);

CREATE INDEX healthcheck_status_idx IF NOT EXISTS
FOR (hc:HealthCheck) ON (hc.status);

// ---------------------------------------------
// 14. FileConsistencyReport Nodes
// ---------------------------------------------
CREATE CONSTRAINT file_report_id IF NOT EXISTS
FOR (fcr:FileConsistencyReport) REQUIRE fcr.id IS UNIQUE;

CREATE INDEX file_report_timestamp_idx IF NOT EXISTS
FOR (fcr:FileConsistencyReport) ON (fcr.timestamp);
"""

def apply_schema():
    """Apply the complete Phase 3 schema."""
    uri = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
    password = os.environ.get('NEO4J_PASSWORD')
    
    driver = GraphDatabase.driver(uri, auth=('neo4j', password))
    
    print("🗄️  Applying Phase 3 Neo4j Schema...")
    print("=" * 60)
    
    with driver.session() as session:
        # Split and execute each statement
        statements = [s.strip() for s in SCHEMA_CYPHER.split(';') if s.strip()]
        
        success_count = 0
        skip_count = 0
        error_count = 0
        
        for stmt in statements:
            if not stmt or stmt.startswith('//') or stmt.startswith('/*'):
                continue
            
            try:
                session.run(stmt)
                # Extract name for logging
                name = stmt.split()[2] if len(stmt.split()) > 2 else "unknown"
                print(f"  ✅ {name}")
                success_count += 1
            except Exception as e:
                if "already exists" in str(e).lower() or "equivalent" in str(e).lower():
                    print(f"  ⏭️  {name} (already exists)")
                    skip_count += 1
                else:
                    print(f"  ⚠️  {name}: {e}")
                    error_count += 1
    
    driver.close()
    
    print("=" * 60)
    print(f"Results: {success_count} created, {skip_count} skipped, {error_count} errors")
    return success_count, skip_count, error_count

if __name__ == '__main__':
    apply_schema()
