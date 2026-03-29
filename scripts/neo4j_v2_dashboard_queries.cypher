// ============================================================
// Unified Task Executor — Dashboard & Anomaly Detection Queries
// Created: 2026-03-22
// ============================================================

// ----- DASHBOARD QUERIES -----

// Q1: Success rate by agent (24h)
MATCH (e:Event)
WHERE e.event_type IN ['TASK_COMPLETED', 'TASK_FAILED_PERMANENT']
  AND e.ts >= datetime() - duration({hours: 24})
RETURN e.agent,
  count(CASE WHEN e.event_type = 'TASK_COMPLETED' THEN 1 END) AS completed,
  count(CASE WHEN e.event_type = 'TASK_FAILED_PERMANENT' THEN 1 END) AS failed,
  toFloat(count(CASE WHEN e.event_type = 'TASK_COMPLETED' THEN 1 END)) /
    CASE WHEN count(e) > 0 THEN count(e) ELSE 1 END AS success_rate
ORDER BY success_rate DESC;

// Q2: Average duration by skill type (24h)
MATCH (e:Event {event_type: 'TASK_COMPLETED'})
WHERE e.ts >= datetime() - duration({hours: 24})
  AND e.duration_s IS NOT NULL
MATCH (t:Task {task_id: e.task_id})
WHERE t.skill_hint IS NOT NULL AND t.skill_hint <> ''
RETURN t.skill_hint AS skill,
  avg(e.duration_s) AS avg_duration_s,
  count(e) AS task_count
ORDER BY avg_duration_s DESC;

// Q3: Current queue depth per agent
MATCH (t:Task)
WHERE t.status IN ['PENDING', 'WORKING', 'BLOCKED']
RETURN t.assigned_to AS agent,
  count(CASE WHEN t.status = 'PENDING' THEN 1 END) AS pending,
  count(CASE WHEN t.status = 'WORKING' THEN 1 END) AS active,
  count(CASE WHEN t.status = 'BLOCKED' THEN 1 END) AS blocked
ORDER BY pending DESC;

// Q4: Session reset correlation with failures (24h)
MATCH (reset:Event {event_type: 'SESSION_RESET'})
WHERE reset.ts >= datetime() - duration({hours: 24})
OPTIONAL MATCH (fail:Event)
WHERE fail.event_type IN ['TASK_FAILED', 'TASK_FAILED_PERMANENT']
  AND fail.agent = reset.agent
  AND fail.ts >= reset.ts
  AND fail.ts <= reset.ts + duration({minutes: 5})
RETURN reset.agent,
  count(DISTINCT reset) AS resets,
  count(DISTINCT fail) AS failures_after_reset;

// Q5: Task throughput (hourly buckets, last 24h)
MATCH (e:Event)
WHERE e.event_type IN ['TASK_COMPLETED', 'TASK_FAILED_PERMANENT']
  AND e.ts >= datetime() - duration({hours: 24})
WITH e, datetime.truncate('hour', e.ts) AS hour
RETURN hour,
  count(CASE WHEN e.event_type = 'TASK_COMPLETED' THEN 1 END) AS completed,
  count(CASE WHEN e.event_type = 'TASK_FAILED_PERMANENT' THEN 1 END) AS failed
ORDER BY hour;

// Q6: AgentMetrics snapshot
MATCH (m:AgentMetrics)
RETURN m.agent, m.tasks_completed_24h, m.tasks_failed_24h,
  m.success_rate_24h, m.avg_duration_s_24h, m.session_resets_24h,
  m.last_updated
ORDER BY m.agent;

// Q7: Model fallback frequency (24h)
MATCH (e:Event)
WHERE e.event_type IN ['MODEL_FALLBACK', 'MODEL_FALLBACK_SUCCESS', 'MODEL_FALLBACK_FAILED']
  AND e.ts >= datetime() - duration({hours: 24})
RETURN e.event_type, count(e) AS count
ORDER BY e.event_type;

// ----- ANOMALY DETECTION (zero rows = healthy) -----

// A1: False completions — COMPLETED without TaskOutput
MATCH (t:Task {status: 'COMPLETED'})
WHERE NOT (t)-[:HAS_OUTPUT]->()
  AND t.completed_at >= datetime() - duration({hours: 24})
RETURN t.task_id, t.assigned_to, t.completed_at;

// A2: Agent success rate dropping below 50%
MATCH (m:AgentMetrics)
WHERE m.success_rate_24h < 0.5
  AND m.tasks_completed_24h + m.tasks_failed_24h >= 3
RETURN m.agent, m.success_rate_24h, m.tasks_failed_24h;

// A3: Queue growing faster than throughput (30min window)
WITH datetime() - duration({minutes: 30}) AS window
MATCH (created:Event {event_type: 'TASK_CLAIMED'})
WHERE created.ts >= window
WITH count(created) AS incoming, window
MATCH (completed:Event)
WHERE completed.event_type IN ['TASK_COMPLETED', 'TASK_FAILED_PERMANENT']
  AND completed.ts >= window
WITH incoming, count(completed) AS outgoing
WHERE incoming > outgoing * 2
RETURN incoming, outgoing, incoming - outgoing AS backlog_growth;

// A4: Stale WORKING tasks (lease expired)
MATCH (t:Task)
WHERE t.status = 'WORKING'
  AND t.lease_expires_at < datetime()
RETURN t.task_id, t.assigned_to, t.lease_expires_at;
