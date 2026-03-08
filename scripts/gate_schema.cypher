// =============================================================================
// Neo4j Schema: Completion Gate Status Index
// =============================================================================
//
// This schema adds support for the completion gate system's Neo4j-first
// pending gate discovery.
//
// The gate_status property on Task nodes tracks the state of completion
// gates: none, waiting_followups, passed, blocked, failed.
//
// Design: ~/.openclaw/agents/ogedei/workspace/gate-repository-design.md
//
// Usage:
//   cypher-shell -u neo4j -p password < gate_schema.cypher
//
// =============================================================================

// -----------------------------------------------------------------------------
// Primary Index: gate_status on Task nodes
// -----------------------------------------------------------------------------
// This index enables fast O(log n) lookups of pending gates.
// Used by: Neo4jGateRepository.find_pending()
//
// Query: MATCH (t:Task) WHERE t.gate_status = 'waiting_followups' RETURN t
// -----------------------------------------------------------------------------

CREATE INDEX gate_status_idx IF NOT EXISTS
FOR (t:Task)
ON (t.gate_status);

// Optional: Create a full-text index for task searches
CREATE FULLTEXT INDEX gate_task_fulltext IF NOT EXISTS
FOR (t:Task) ON EACH [t.task_id, t.title, t.agent]
OPTIONS {
  indexConfig: {
    `fulltext.analyzer`: "standard-folding"
  }
};

// =============================================================================
// Constraint: Unique task_id
// =============================================================================
// Ensures each task_id appears at most once in the database.
// This prevents duplicate Task nodes for the same task.

CREATE CONSTRAINT task_id_unique IF NOT EXISTS
FOR (t:Task) REQUIRE t.task_id IS UNIQUE;

// =============================================================================
// Sample Queries for Verification
// =============================================================================

// Count gates by status
// MATCH (t:Task)
// WHERE t.gate_status IS NOT NULL
// RETURN t.gate_status as status, count(t) as count
// ORDER BY count DESC;

// Find oldest pending gates (the resolver processes these first)
// MATCH (t:Task)
// WHERE t.gate_status = 'waiting_followups'
// RETURN t.task_id, t.agent, t.modified
// ORDER BY t.modified
// LIMIT 10;

// Show gate status for a specific task
// MATCH (t:Task {task_id: 'high-12345678'})
// RETURN t.gate_status, t.status, t.title;

// =============================================================================
// Manual Gate Status Updates (for debugging)
// =============================================================================

// Mark a task as waiting_followups (pending gate)
// MATCH (t:Task {task_id: 'high-12345678'})
// SET t.gate_status = 'waiting_followups',
//     t.gate_updated = datetime();

// Mark a task as passed (gate completed)
// MATCH (t:Task {task_id: 'high-12345678'})
// SET t.gate_status = 'passed',
//     t.gate_updated = datetime(),
//     t.completed = datetime();

// Mark a task as blocked
// MATCH (t:Task {task_id: 'high-12345678'})
// SET t.gate_status = 'blocked',
//     t.gate_updated = datetime();

// Clear gate status
// MATCH (t:Task {task_id: 'high-12345678'})
// REMOVE t.gate_status, t.gate_updated;
