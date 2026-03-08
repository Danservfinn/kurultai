// Kurultai Experiment Schema
// Neo4j migration for autonomous experiment tracking
// Run with: cat experiment_schema.cypher | cypher-shell -u neo4j -p <password>

// ============================================================================
// CONSTRAINTS
// ============================================================================

// Unique experiment ID constraint
CREATE CONSTRAINT experiment_id_unique IF NOT EXISTS
FOR (e:Experiment) REQUIRE e.experiment_id IS UNIQUE;

// Unique agent name constraint (if not exists)
CREATE CONSTRAINT agent_name_unique IF NOT EXISTS
FOR (a:Agent) REQUIRE a.name IS UNIQUE;

// ============================================================================
// INDEXES
// ============================================================================

// Index for status queries
CREATE INDEX experiment_status_idx IF NOT EXISTS
FOR (e:Experiment) ON (e.status);

// Index for agent queries
CREATE INDEX experiment_agent_idx IF NOT EXISTS
FOR (e:Experiment) ON (e.agent);

// Index for created timestamp queries
CREATE INDEX experiment_created_idx IF NOT EXISTS
FOR (e:Experiment) ON (e.created);

// Index for decision queries
CREATE INDEX experiment_decision_idx IF NOT EXISTS
FOR (e:Experiment) ON (e.decision);

// ============================================================================
// EXPERIMENT NODE STRUCTURE
// ============================================================================

// Example Experiment node (for documentation)
// (:Experiment {
//     experiment_id: "exp-20260308-001",
//     agent: "temujin",
//     hypothesis: "Increase router scorer learning rate",
//     branch: "experiment/temujin/exp-20260308-001/router-lr-tuning",
//     base_commit: "a1b2c3d7",
//     status: "merged",  // pending, running, merged, discarded, crashed
//     created: datetime(),
//     started: datetime(),
//     completed: datetime(),
//     duration_seconds: 312,
//     timeout: 600,
//
//     // Baseline metrics
//     quality_score_baseline: 0.72,
//     error_rate_baseline: 0.05,
//
//     // Result metrics
//     quality_score_result: 0.78,
//     error_rate_result: 0.04,
//     cost_usd: 0.47,
//
//     // Improvement calculation
//     quality_improvement_pct: 8.3,
//
//     // Decision
//     decision: "merge",  // merge, discard, crash
//     decision_reason: "quality_improvement_8pct",
//     human_approval: false,
//     approver: null
// })

// ============================================================================
// RELATIONSHIPS
// ============================================================================

// Agent creates experiment
// (:Agent {name: "temujin"})-[:CREATED_EXPERIMENT]->(:Experiment)

// Experiment modifies files
// (:Experiment)-[:MODIFIED]->(:File {path: "scripts/router_scorer.py"})

// Experiment merged at specific commit
// (:Experiment)-[:MERGED_AT]->(:MergeEvent {commit: "b2c3d4e8", timestamp: datetime()})

// Experiment rolled back
// (:Experiment)-[:ROLLED_BACK]->(:RollbackEvent {reason: "error_spike", timestamp: datetime()})

// Experiment based on previous experiment
// (:Experiment)-[:BASED_ON]->(:Experiment {experiment_id: "exp-20260307-015"})

// ============================================================================
// MERGE EVENT NODE
// ============================================================================

// MergeEvent node structure
// (:MergeEvent {
//     commit: "b2c3d4e8",
//     timestamp: datetime(),
//     branch: "main",
//     experiment_id: "exp-20260308-001",
//     quality_improvement_pct: 8.3
// })

CREATE INDEX merge_event_timestamp_idx IF NOT EXISTS
FOR (m:MergeEvent) ON (m.timestamp);

// ============================================================================
// ROLLBACK EVENT NODE
// ============================================================================

// RollbackEvent node structure
// (:RollbackEvent {
//     commit: "b2c3d4e8",
//     original_commit: "a1b2c3d7",
//     timestamp: datetime(),
//     reason: "error_spike_2x",
//     experiment_id: "exp-20260308-003"
// })

CREATE INDEX rollback_event_timestamp_idx IF NOT EXISTS
FOR (r:RollbackEvent) ON (r.timestamp);

// ============================================================================
// FILE NODE
// ============================================================================

// File node for tracking modifications
// (:File {
//     path: "scripts/router_scorer.py",
//     last_modified: datetime(),
//     modification_count: 5
// })

CREATE CONSTRAINT file_path_unique IF NOT EXISTS
FOR (f:File) REQUIRE f.path IS UNIQUE;

// ============================================================================
// UTILITY QUERIES
// ============================================================================

// Get daily experiment stats
// MATCH (e:Experiment)
// WHERE date(e.created) = date()
// RETURN
//     count(e) AS total,
//     sum(CASE WHEN e.status = 'merged' THEN 1 ELSE 0 END) AS merged,
//     sum(CASE WHEN e.status = 'discarded' THEN 1 ELSE 0 END) AS discarded,
//     avg(e.quality_improvement_pct) AS avg_improvement

// Get stale experiments (running >2 hours)
// MATCH (e:Experiment {status: 'running'})
// WHERE e.started < datetime() - duration('PT2H')
// RETURN e

// Get recent merges for dashboard
// MATCH (e:Experiment {status: 'merged'})-[:MERGED_AT]->(m:MergeEvent)
// WHERE m.timestamp > datetime() - duration('P1D')
// RETURN e, m
// ORDER BY m.timestamp DESC
// LIMIT 10

// ============================================================================
// VERIFICATION QUERY
// ============================================================================

// Run this to verify schema is created
RETURN
    "Experiment schema verification" AS status,
    count{(e:Experiment)} AS experiment_count,
    count{(a:Agent)} AS agent_count,
    count{(f:File)} AS file_count
