// Neo4j Schema Extension: Relationship Tracking System
// Adds relationship tracking to the identity system

// =============================================================================
// Constraints and Indexes for Relationships
// =============================================================================

// Unique constraint on Relationship nodes
CREATE CONSTRAINT relationship_id IF NOT EXISTS
FOR (r:Relationship) REQUIRE r.id IS UNIQUE;

// Indexes for relationship queries
CREATE INDEX relationship_type IF NOT EXISTS
FOR ()-[r:KNOWS]-() ON (r.type);

CREATE INDEX relationship_strength IF NOT EXISTS
FOR ()-[r:KNOWS]-() ON (r.strength);

CREATE INDEX relationship_last_updated IF NOT EXISTS
FOR ()-[r:KNOWS]-() ON (r.last_updated);

// Indexes for aggregated relationships
CREATE INDEX aggregated_relationship_type IF NOT EXISTS
FOR (r:AggregatedRelationship) ON (r.type);

CREATE INDEX aggregated_relationship_confidence IF NOT EXISTS
FOR (r:AggregatedRelationship) ON (r.confidence);

// Indexes for analysis tracking
CREATE INDEX relationship_analysis_id IF NOT EXISTS
FOR (a:RelationshipAnalysis) ON (a.id);

CREATE INDEX relationship_analysis_timestamp IF NOT EXISTS
FOR (a:RelationshipAnalysis) ON (a.timestamp);

// Indexes for privacy and discovery tracking
CREATE INDEX relationship_discovered_via IF NOT EXISTS
FOR ()-[r:KNOWS]-() ON (r.discovered_via);

CREATE INDEX relationship_is_explicit IF NOT EXISTS
FOR ()-[r:KNOWS]-() ON (r.is_explicit);

CREATE INDEX relationship_privacy_level IF NOT EXISTS
FOR ()-[r:KNOWS]-() ON (r.privacy_level);

// =============================================================================
// Person-to-Person Relationship (:KNOWS)
// =============================================================================
/*
The :KNOWS relationship connects two Person nodes with rich properties:

(:Person)-[:KNOWS {
    type: "COLLEAGUE",           // RelationshipType enum value
    strength: 0.8,               // 0.0 to 1.0
    context: "Work together...", // Description of relationship
    discovered_at: datetime(),   // When first detected
    last_updated: datetime(),    // When last confirmed/updated
    confidence: 0.85,            // Confidence in this relationship
    evidence_count: 5,           // Number of supporting evidence
    source: "conversation"       // Source of detection
}]->(:Person)
*/

// Create sample :KNOWS relationship with all properties
/*
MATCH (p1:Person {name: "Alice"}), (p2:Person {name: "Danny"})
CREATE (p1)-[:KNOWS {
    type: "COLLEAGUE",
    strength: 0.8,
    context: "Work on Kurultai project together",
    discovered_at: datetime(),
    last_updated: datetime(),
    confidence: 0.85,
    evidence_count: 5,
    source: "conversation_analysis",
    discovered_via: "conversation",              // How was this discovered
    discovered_in_conversation_with: "Danny",  // Who mentioned this
    is_explicit: true,                         // Explicitly stated or inferred
    privacy_level: "observed"                  // observed, inferred, sensitive
}]->(p2);
*/

// =============================================================================
// Complex Relationship Nodes
// =============================================================================
/*
For complex relationships that need their own properties and connections,
we create :Relationship nodes:

(:Person)-[:HAS_RELATIONSHIP]->(:Relationship)-[:WITH]->(:Person)

This allows:
- Multiple people in the same relationship (e.g., team members)
- Time-bounded relationships
- Relationships with their own metadata
*/

// Create constraint for Relationship nodes
CREATE CONSTRAINT complex_relationship_id IF NOT EXISTS
FOR (r:Relationship) REQUIRE r.id IS UNIQUE;

// Sample complex relationship structure
/*
// Create a business partnership relationship
CREATE (r:Relationship {
    id: "rel_001",
    type: "BUSINESS_PARTNERSHIP",
    name: "Kurultai Co-founders",
    start_date: date("2023-01-15"),
    status: "active",
    context: "Co-founded Kurultai AI system"
});

// Connect people to the relationship
MATCH (alice:Person {name: "Alice"}), (danny:Person {name: "Danny"}), (r:Relationship {id: "rel_001"})
CREATE (alice)-[:HAS_RELATIONSHIP {role: "co-founder", joined: date("2023-01-15")}]->(r)
CREATE (danny)-[:HAS_RELATIONSHIP {role: "co-founder", joined: date("2023-01-15")}]->(r);

// Or connect to another person through the relationship
MATCH (r:Relationship {id: "rel_001"}), (danny:Person {name: "Danny"})
CREATE (r)-[:WITH {relationship_type: "BUSINESS_PARTNER"}]->(danny);
*/

// =============================================================================
// Aggregated Relationship Tracking
// =============================================================================
/*
Store aggregated relationship data from multiple analyses:

(:AggregatedRelationship {
    type: "FRIEND",
    avg_strength: 0.75,
    max_strength: 0.9,
    min_strength: 0.6,
    confidence: 0.85,
    evidence_count: 12,
    discovered_at: datetime(),
    last_updated: datetime(),
    agent_votes: "{FRIEND: 5, COLLEAGUE: 2}"  // JSON string
})
*/

// =============================================================================
// Evidence and Context Tracking
// =============================================================================

// Evidence nodes for relationship verification
CREATE CONSTRAINT relationship_evidence_id IF NOT EXISTS
FOR (e:RelationshipEvidence) REQUIRE e.id IS UNIQUE;

// Sample evidence structure
/*
CREATE (e:RelationshipEvidence {
    id: "evidence_001",
    source_conversation: "conv_123",
    timestamp: datetime(),
    supporting_text: "Danny and I have been working together...",
    indicators: ["colleague", "work together", "project"],
    confidence: 0.8
});

// Connect evidence to relationship
MATCH (r:AggregatedRelationship), (e:RelationshipEvidence {id: "evidence_001"})
CREATE (r)-[:SUPPORTED_BY]->(e);
*/

// =============================================================================
// Analysis Job Tracking
// =============================================================================
/*
Track relationship analysis jobs:

(:RelationshipAnalysis {
    id: "horde_rel_20250210_120000",
    status: "completed",
    total_batches: 10,
    completed_batches: 10,
    failed_batches: 0,
    processing_time_seconds: 45.5,
    conflicts_resolved: 2,
    timestamp: datetime()
})
*/

// =============================================================================
// Primary Human Tracking
// =============================================================================
/*
Special tracking for the primary human (Danny):

// Mark the primary human
MATCH (p:Person {name: "Danny"})
SET p.is_primary_human = true,
    p.primary_human_since = datetime();

// Index for quick lookup
CREATE INDEX person_primary IF NOT EXISTS
FOR (p:Person) ON (p.is_primary_human);
*/

// =============================================================================
// Useful Queries
// =============================================================================

// Get all relationships for a person
/*
MATCH (p:Person {name: "Danny"})-[r:KNOWS]-(other:Person)
RETURN other.name, r.type, r.strength, r.context
ORDER BY r.strength DESC;
*/

// Get relationships by type
/*
MATCH (p:Person)-[r:KNOWS {type: "COLLEAGUE"}]-(other:Person)
RETURN p.name, other.name, r.strength, r.context;
*/

// Get strongest relationships
/*
MATCH (p:Person {name: "Danny"})-[r:KNOWS]-(other:Person)
WHERE r.strength > 0.7
RETURN other.name, r.type, r.strength, r.context
ORDER BY r.strength DESC;
*/

// Get relationships with low confidence (need more evidence)
/*
MATCH (p:Person)-[r:KNOWS]-(other:Person)
WHERE r.confidence < 0.5
RETURN p.name, other.name, r.type, r.confidence, r.evidence_count;
*/

// Update relationship strength (decay over time)
/*
MATCH (p1:Person)-[r:KNOWS]-(p2:Person)
WHERE r.last_updated < datetime() - duration('P90D')
SET r.strength = r.strength * 0.9,
    r.last_updated = datetime();
*/

// Aggregate relationship statistics
/*
MATCH (p:Person {name: "Danny"})-[r:KNOWS]-(other:Person)
RETURN r.type as relationship_type,
       count(*) as count,
       avg(r.strength) as avg_strength,
       max(r.strength) as max_strength
ORDER BY count DESC;
*/

// Find mutual relationships (people who know each other AND Danny)
/*
MATCH (danny:Person {name: "Danny"})-[:KNOWS]-(person:Person)-[:KNOWS]-(other:Person)
WHERE danny <> other
RETURN person.name, collect(DISTINCT other.name) as mutual_connections;
*/

// =============================================================================
// Maintenance Queries
// =============================================================================

// Clean up old relationship analyses
/*
MATCH (a:RelationshipAnalysis)
WHERE a.timestamp < datetime() - duration('P30D')
DETACH DELETE a;
*/

// Archive old evidence
/*
MATCH (e:RelationshipEvidence)
WHERE e.timestamp < datetime() - duration('P180D')
SET e.archived = true;
*/

// Update relationship confidence based on new evidence
/*
MATCH (p1:Person)-[r:KNOWS]-(p2:Person)
WHERE r.evidence_count > 10
SET r.confidence = CASE 
    WHEN r.confidence < 0.9 THEN r.confidence + 0.05
    ELSE 0.95
END;
*/
