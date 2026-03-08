// Neo4j Schema Migration - Enhanced Task Metrics
// Run this to add new properties and indexes for comprehensive task reporting
//
// Usage:
//   cypher-shell -u neo4j -p <password> < neo4j-task-metrics-schema.cypher
//
// Or via Python:
//   python3 -c "from neo4j_task_tracker import get_driver; d=get_driver(); d.execute_query(open('neo4j-task-metrics-schema.cypher').read())"

// ============================================================
// Task Property Indexes (for new metrics)
// ============================================================

// Token usage indexes
CREATE INDEX task_input_tokens_idx IF NOT EXISTS FOR (t:Task) ON (t.input_tokens);
CREATE INDEX task_output_tokens_idx IF NOT EXISTS FOR (t:Task) ON (t.output_tokens);
CREATE INDEX task_total_tokens_idx IF NOT EXISTS FOR (t:Task) ON (t.total_tokens);

// Model and temperature
CREATE INDEX task_model_idx IF NOT EXISTS FOR (t:Task) ON (t.model);
CREATE INDEX task_temperature_idx IF NOT EXISTS FOR (t:Task) ON (t.temperature);

// Context window
CREATE INDEX task_context_window_idx IF NOT EXISTS FOR (t:Task) ON (t.context_window_percent);

// Duration and efficiency
CREATE INDEX task_duration_seconds_idx IF NOT EXISTS FOR (t:Task) ON (t.duration_seconds);
CREATE INDEX task_duration_minutes_idx IF NOT EXISTS FOR (t:Task) ON (t.duration_minutes);

// Agent state
CREATE INDEX task_queue_depth_idx IF NOT EXISTS FOR (t:Task) ON (t.queue_depth);
CREATE INDEX task_memory_mb_idx IF NOT EXISTS FOR (t:Task) ON (t.memory_mb);

// Error analysis
CREATE INDEX task_error_category_idx IF NOT EXISTS FOR (t:Task) ON (t.error_category);
CREATE INDEX task_error_hash_idx IF NOT EXISTS FOR (t:Task) ON (t.error_hash);
CREATE INDEX task_is_retryable_idx IF NOT EXISTS FOR (t:Task) ON (t.is_retryable);

// Code metrics
CREATE INDEX task_files_created_idx IF NOT EXISTS FOR (t:Task) ON (t.files_created);
CREATE INDEX task_lines_added_idx IF NOT EXISTS FOR (t:Task) ON (t.lines_added);
CREATE INDEX task_functions_count_idx IF NOT EXISTS FOR (t:Task) ON (t.functions_count);
CREATE INDEX task_classes_count_idx IF NOT EXISTS FOR (t:Task) ON (t.classes_count);
CREATE INDEX task_tests_count_idx IF NOT EXISTS FOR (t:Task) ON (t.tests_count);

// Quality and resources
CREATE INDEX task_quality_score_idx IF NOT EXISTS FOR (t:Task) ON (t.data_quality_score);
CREATE INDEX task_cpu_time_idx IF NOT EXISTS FOR (t:Task) ON (t.cpu_time_seconds);

// Context chain
CREATE INDEX task_parent_id_idx IF NOT EXISTS FOR (t:Task) ON (t.parent_id);

// ============================================================
// Composite Indexes (for common query patterns)
// ============================================================

// Agent + status + created (for hourly reflections)
CREATE INDEX task_agent_status_created_idx IF NOT EXISTS FOR (t:Task) ON (t.agent, t.status, t.created);

// Agent + date (for daily aggregations)
CREATE INDEX task_agent_date_idx IF NOT EXISTS FOR (t:Task) ON (t.agent, date(t.created));

// Error category + status (for failure analysis)
CREATE INDEX task_error_status_idx IF NOT EXISTS FOR (t:Task) ON (t.error_category, t.status);

// Skill hint + created (for skill usage analysis)
CREATE INDEX task_skill_created_idx IF NOT EXISTS FOR (t:Task) ON (t.skill_hint, t.created);

// ============================================================
// Fulltext Indexes (for search)
// ============================================================

// Error message search
CREATE FULLTEXT INDEX task_error_search IF NOT EXISTS FOR (t:Task) ON EACH [t.error_category, t.error_hash];

// Task deliverables search
CREATE FULLTEXT INDEX task_deliverables_search IF NOT EXISTS FOR (t:Task) ON EACH [t.title, t.body];

// ============================================================
// Aggregation Views (as virtual nodes for performance)
// ============================================================

// Note: Neo4j doesn't support materialized views in Community Edition.
// For production, consider creating summary nodes updated by triggers.

// Example: Daily agent summary node pattern
// Match this pattern in aggregation queries:
// MATCH (t:Task)
// WHERE t.created > datetime() - duration({days: 7})
// WITH date(t.created) AS day, t.agent AS agent, t.status AS status
// WITH day, agent, status, count(*) AS count
// RETURN day, agent, status, count
// ORDER BY day DESC

// ============================================================
// Constraint Additions (if not already present)
// ============================================================

// Ensure task_id uniqueness
CREATE CONSTRAINT task_id_unique IF NOT EXISTS FOR (t:Task) REQUIRE t.task_id IS UNIQUE;

// ============================================================
// Sample Queries for Validation
// ============================================================

// After running this migration, validate with:

// 1. Check token usage distribution
// MATCH (t:Task)
// WHERE t.total_tokens IS NOT NULL
// RETURN
//     avg(t.total_tokens) AS avg_tokens,
//     min(t.total_tokens) AS min_tokens,
//     max(t.total_tokens) AS max_tokens
// LIMIT 1;

// 2. Check error category distribution
// MATCH (t:Task)
// WHERE t.error_category IS NOT NULL
// RETURN t.error_category AS category, count(*) AS count
// ORDER BY count DESC;

// 3. Check agent performance with new metrics
// MATCH (t:Task)
// WHERE t.created > datetime() - duration({hours: 24})
// RETURN
//     t.agent AS agent,
//     count(*) AS tasks,
//     avg(t.duration_seconds) AS avg_duration,
//     sum(t.total_tokens) AS total_tokens,
//     sum(CASE WHEN t.status = 'completed' THEN 1 ELSE 0 END) AS completed
// ORDER BY tasks DESC;
