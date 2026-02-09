// Phase 7: Optimization Schema Extensions
// OptimizationResult node for tracking continuous improvements

// Create index on OptimizationResult
CREATE INDEX optimization_result_task_name IF NOT EXISTS
FOR (o:OptimizationResult) ON (o.task_name);

CREATE INDEX optimization_result_agent IF NOT EXISTS
FOR (o:OptimizationResult) ON (o.agent);

CREATE INDEX optimization_result_status IF NOT EXISTS
FOR (o:OptimizationResult) ON (o.status);

CREATE INDEX optimization_result_created IF NOT EXISTS
FOR (o:OptimizationResult) ON (o.created_at);
