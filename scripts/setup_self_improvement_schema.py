#!/usr/bin/env python3
"""
Setup Neo4j Schema for Self-Improvement System
Run this once to initialize the database
"""

import os
from neo4j import GraphDatabase

NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'myStrongPassword123')

SCHEMA_CYPHER = """
// ============================================
// INDEXES (Performance)
// ============================================

CREATE INDEX agent_reflection_agent_time_idx IF NOT EXISTS 
  FOR (r:AgentReflection) ON (r.agent, r.timestamp);

CREATE INDEX agent_reflection_reviewed_idx IF NOT EXISTS 
  FOR (r:AgentReflection) ON (r.reviewed);

CREATE INDEX review_decision_idx IF NOT EXISTS 
  FOR (rev:Review) ON (rev.decision);

CREATE INDEX baseline_change_idx IF NOT EXISTS 
  FOR (b:Baseline) ON (b.change_id, b.metric);

CREATE INDEX implementation_status_idx IF NOT EXISTS 
  FOR (imp:ImplementationQueue) ON (imp.status);

// ============================================
// CONSTRAINTS (Data Integrity)
// ============================================

CREATE CONSTRAINT agent_reflection_id IF NOT EXISTS 
  FOR (r:AgentReflection) REQUIRE r.id IS UNIQUE;

CREATE CONSTRAINT review_id IF NOT EXISTS 
  FOR (rev:Review) REQUIRE rev.id IS UNIQUE;

CREATE CONSTRAINT baseline_id IF NOT EXISTS 
  FOR (b:Baseline) REQUIRE b.id IS UNIQUE;

CREATE CONSTRAINT implementation_queue_id IF NOT EXISTS 
  FOR (imp:ImplementationQueue) REQUIRE imp.id IS UNIQUE;

CREATE CONSTRAINT human_notification_id IF NOT EXISTS 
  FOR (hn:HumanNotification) REQUIRE hn.id IS UNIQUE;

CREATE CONSTRAINT validation_id IF NOT EXISTS 
  FOR (v:Validation) REQUIRE v.id IS UNIQUE;

// ============================================
// INITIAL DATA (Optional - for testing)
// ============================================

// Create placeholder nodes to verify schema
MERGE (test:AgentReflection {
    id: "test-setup-node",
    agent: "system",
    timestamp: datetime(),
    raw_text: "Schema initialized",
    reviewed: true,
    priority: "low"
});

MERGE (test2:ImplementationQueue {
    id: "test-implementation",
    agent: "system",
    queued_at: datetime(),
    status: "test"
});
"""

def setup_schema():
    """Initialize Neo4j schema for self-improvement system."""
    print("🔧 Setting up Neo4j schema for self-improvement system...")
    
    driver = GraphDatabase.driver(
        NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
    )
    
    try:
        with driver.session() as session:
            # Execute schema statements one by one for better error handling
            statements = [s.strip() for s in SCHEMA_CYPHER.split(';') if s.strip()]
            
            for stmt in statements:
                if stmt.startswith('//') or stmt.startswith('/*'):
                    continue
                    
                try:
                    session.run(stmt)
                    print(f"  ✅ Executed: {stmt[:50]}...")
                except Exception as e:
                    if "already exists" in str(e).lower():
                        print(f"  ⚠️  Skipped (already exists): {stmt[:50]}...")
                    else:
                        print(f"  ❌ Error: {e}")
        
        print("\n✅ Schema setup complete!")
        
        # Verify
        with driver.session() as session:
            result = session.run("""
                CALL db.labels() YIELD label
                WHERE label IN ['AgentReflection', 'Review', 'Baseline', 'ImplementationQueue']
                RETURN count(*) as count
            """)
            count = result.single()['count']
            print(f"   Verified {count} self-improvement labels created")
            
    except Exception as e:
        print(f"\n❌ Schema setup failed: {e}")
        raise
    finally:
        driver.close()

if __name__ == "__main__":
    setup_schema()
