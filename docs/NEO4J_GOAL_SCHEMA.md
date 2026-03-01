# Neo4j Goal/Task Schema - Autonomous Kurultai

## Overview

This schema enables goal-driven autonomous operation. The Kurultai executes toward goals without human task initiation.

---

## Core Node Types

### 1. Goal Nodes

```cypher
CREATE (g:Goal {
  id: "parse-monetization",
  title: "Parse Monetization - $1500 MRR by Day 90",
  description: "Launch subscription revenue for parsethe.media to sustain Kurultai operations",
  priority: 1,  -- 1=critical, 2=high, 3=medium, 4=low, 5=backlog
  status: "active",  -- active, completed, paused, abandoned
  target_metric: "1500 MRR",
  deadline: "2026-05-30",
  owner: "kurultai",  -- kurultai (team), or agent id
  created_by: "kublai",
  created_at: datetime("2026-03-01"),
  updated_at: datetime("2026-03-01"),
  human_approved: true,
  auto_execute: true  -- if true, agents can pull tasks without approval
})
```

**Properties:**
| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | String | ✅ | Unique slug identifier |
| title | String | ✅ | Human-readable goal name |
| description | String | ✅ | Full context |
| priority | Integer | ✅ | 1-5 (1=critical) |
| status | String | ✅ | active/completed/paused/abandoned |
| target_metric | String | ✅ | Measurable success criteria |
| deadline | Date | ⏳ | Optional target date |
| owner | String | ✅ | kurultai or agent id |
| auto_execute | Boolean | ✅ | Can agents auto-pull tasks? |

---

### 2. Task Nodes

```cypher
CREATE (t:Task {
  id: "stripe-integration",
  goal_id: "parse-monetization",
  title: "Implement Stripe Payment Integration",
  description: "Full Stripe checkout, webhooks, subscription management",
  status: "completed",  -- pending, in_progress, blocked, completed, failed
  assigned_to: "temujin",  -- agent id or "unassigned"
  priority: 1,  -- inherits from goal, or override
  deadline: "2026-03-03",
  estimated_hours: 8,
  actual_hours: null,
  started_at: datetime("2026-03-01T01:52"),
  completed_at: datetime("2026-03-01T02:05"),
  auto_assigned: true,  -- can agents auto-claim?
  requires_approval: false,  -- does completion need human review?
  artifact_path: "/Users/kublai/projects/parsethe.media/STRIPE_SETUP_GUIDE.md",
  dependencies: [],  -- list of task IDs that must complete first
  triggers: ["launch-pricing-page"]  -- task IDs to auto-start when complete
})
```

**Properties:**
| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | String | ✅ | Unique slug |
| goal_id | String | ✅ | Parent goal |
| title | String | ✅ | Task name |
| description | String | ✅ | What + why |
| status | String | ✅ | pending/in_progress/blocked/completed/failed |
| assigned_to | String | ✅ | Agent id or "unassigned" |
| auto_assigned | Boolean | ✅ | Can agents auto-claim? |
| requires_approval | Boolean | ✅ | Human review before next task? |
| artifact_path | String | ⏳ | Output file location |
| dependencies | List | ⏳ | Must complete first |
| triggers | List | ⏳ | Auto-start when complete |

---

### 3. Agent State Nodes

```cypher
CREATE (a:AgentState {
  agent_id: "kublai",
  status: "coordinating",  -- idle, working, coordinating, blocked
  current_task: "parse-goal-decomposition",
  tasks_completed: 47,
  tasks_failed: 2,
  last_active: datetime(),
  capacity: 1.0,  -- 0.0-1.0 (available capacity)
  specialization: ["routing", "synthesis", "coordination"],
  auto_claim_enabled: true
})
```

**Track all 6 agents:**
- kublai, mongke, chagatai, temujin, jochi, ogedei

---

### 4. Progress Snapshot Nodes

```cypher
CREATE (p:ProgressSnapshot {
  goal_id: "parse-monetization",
  timestamp: datetime("2026-03-01T02:00"),
  tasks_total: 47,
  tasks_completed: 12,
  tasks_in_progress: 3,
  tasks_blocked: 2,
  tasks_pending: 30,
  percent_complete: 25.5,
  days_remaining: 89,
  on_track: true,
  blockers: ["waiting-for-stripe-products"],
  next_milestone: "first-paying-user",
  summary: "Stripe integration complete. Awaiting product setup."
})
```

**Auto-created daily by cron job.**

---

## Relationships

```cypher
// Goal → Tasks (1-to-many)
(g:Goal)-[:HAS_TASK]->(t:Task)

// Task → Task (dependencies)
(t1:Task)-[:DEPENDS_ON]->(t2:Task)

// Task → Task (triggers)
(t1:Task)-[:TRIGGERS]->(t2:Task)

// Agent → Task (assignment)
(a:Agent)-[:ASSIGNED_TO]->(t:Task)

// Agent → Goal (ownership)
(a:Agent)-[:OWNS]->(g:Goal)

// Goal → ProgressSnapshot (history)
(g:Goal)-[:HAS_SNAPSHOT]->(p:ProgressSnapshot)
```

---

## Core Queries

### Create Goal with Tasks

```cypher
// Create goal
CREATE (g:Goal {
  id: "parse-monetization",
  title: "Parse Monetization - $1500 MRR by Day 90",
  priority: 1,
  status: "active",
  target_metric: "1500 MRR",
  deadline: "2026-05-30",
  auto_execute: true
})

// Create tasks
UNWIND [
  {id: "stripe-integration", title: "Stripe Integration", assigned_to: "temujin"},
  {id: "pricing-copy", title: "Pricing Page Copy", assigned_to: "chagatai"},
  {id: "market-research", title: "Market Research", assigned_to: "mongke"}
] AS task_data
CREATE (t:Task {
  id: task_data.id,
  goal_id: "parse-monetization",
  title: task_data.title,
  assigned_to: task_data.assigned_to,
  status: "pending",
  auto_assigned: true
})
CREATE (g)-[:HAS_TASK]->(t)
```

### Get Available Tasks for Agent

```cypher
// Find unassigned tasks matching agent specialization
MATCH (t:Task)
WHERE t.status = "pending"
  AND (t.assigned_to = "unassigned" OR t.assigned_to = $agent_id)
  AND t.auto_assigned = true
  AND NOT EXISTS((t)-[:DEPENDS_ON]->(:Task {status: "in_progress"}))
RETURN t
ORDER BY t.priority ASC, t.deadline ASC
LIMIT 1
```

### Auto-Claim Task

```cypher
// Agent claims task
MATCH (t:Task {id: $task_id})
SET t.status = "in_progress",
    t.assigned_to = $agent_id,
    t.started_at = datetime()

// Update agent state
MATCH (a:AgentState {agent_id: $agent_id})
SET a.status = "working",
    a.current_task = $task_id,
    a.capacity = 0.5
```

### Complete Task + Trigger Next

```cypher
// Mark task complete
MATCH (t:Task {id: $task_id})
SET t.status = "completed",
    t.completed_at = datetime(),
    t.artifact_path = $artifact_path

// Free up agent
MATCH (a:AgentState {agent_id: $agent_id})
SET a.status = "idle",
    a.current_task = null,
    a.capacity = 1.0,
    a.tasks_completed = a.tasks_completed + 1

// Trigger next tasks
MATCH (t:Task {id: $task_id})-[:TRIGGERS]->(next:Task)
SET next.status = "pending",
    next.assigned_to = "unassigned"
```

### Daily Progress Snapshot

```cypher
MATCH (g:Goal {id: $goal_id})
OPTIONAL MATCH (g)-[:HAS_TASK]->(t:Task)
WITH g,
     count(t) as total,
     sum(CASE WHEN t.status = "completed" THEN 1 ELSE 0 END) as completed,
     sum(CASE WHEN t.status = "in_progress" THEN 1 ELSE 0 END) as in_progress,
     sum(CASE WHEN t.status = "blocked" THEN 1 ELSE 0 END) as blocked
CREATE (p:ProgressSnapshot {
  goal_id: $goal_id,
  timestamp: datetime(),
  tasks_total: total,
  tasks_completed: completed,
  tasks_in_progress: in_progress,
  tasks_blocked: blocked,
  tasks_pending: total - completed - in_progress - blocked,
  percent_complete: round(100.0 * completed / total, 1),
  on_track: true  // TODO: calculate based on deadline
})
CREATE (g)-[:HAS_SNAPSHOT]->(p)
```

### Get Goal Status Summary

```cypher
MATCH (g:Goal {id: $goal_id})
OPTIONAL MATCH (g)-[:HAS_TASK]->(t:Task)
OPTIONAL MATCH (g)-[:HAS_SNAPSHOT]->(p:ProgressSnapshot)
RETURN 
  g.title,
  g.status,
  g.target_metric,
  g.deadline,
  count(DISTINCT t) as total_tasks,
  sum(CASE WHEN t.status = "completed" THEN 1 ELSE 0 END) as completed,
  p.percent_complete,
  p.on_track,
  p.blockers
```

---

## Indexes (Performance)

```cypher
// Goal lookups
CREATE INDEX goal_id_idx FOR (g:Goal) ON (g.id)
CREATE INDEX goal_status_idx FOR (g:Goal) ON (g.status)
CREATE INDEX goal_priority_idx FOR (g:Goal) ON (g.priority)

// Task lookups
CREATE INDEX task_id_idx FOR (t:Task) ON (t.id)
CREATE INDEX task_goal_idx FOR (t:Task) ON (t.goal_id)
CREATE INDEX task_status_idx FOR (t:Task) ON (t.status)
CREATE INDEX task_assigned_idx FOR (t:Task) ON (t.assigned_to)

// Agent state
CREATE INDEX agent_state_idx FOR (a:AgentState) ON (a.agent_id)

// Progress snapshots
CREATE INDEX snapshot_goal_idx FOR (p:ProgressSnapshot) ON (p.goal_id)
CREATE INDEX snapshot_time_idx FOR (p:ProgressSnapshot) ON (p.timestamp)
```

---

## Maintenance

### Archive Completed Goals (Monthly)

```cypher
MATCH (g:Goal {status: "completed"})
WHERE g.updated_at < datetime() - duration('P30D')
SET g.archived = true
```

### Clean Old Snapshots (Keep 90 Days)

```cypher
MATCH (p:ProgressSnapshot)
WHERE p.timestamp < datetime() - duration('P90D')
DETACH DELETE p
```

---

*This schema enables full autonomous operation. Goals drive tasks, agents auto-claim work, completions trigger next actions.*
