# Neo4j Schema Reference

**Driver**: `the-kurultai/neo4j.js`
**Credentials**: `~/.openclaw/credentials/neo4j.env`
**Connection**: `bolt://localhost:7687` (default)
- JS (neo4j.js): pool size 25, acquisition timeout 15s
- Python (neo4j_task_tracker.py): pool size 30, acquisition timeout 15s

## Connection Management

- Singleton driver via `getDriver()` -- lazy initialization
- Credentials loaded from `neo4j.env` file, falling back to environment variables
- `verifyConnection()` called on server startup
- `closeDriver()` called on graceful shutdown (SIGTERM/SIGINT)

---

## Node Types

### Task

The primary node type. Represents a unit of work assigned to an agent.

**Properties:**

| Property | Type | Description |
|----------|------|-------------|
| `task_id` | String | Unique identifier (format: `<priority>-<unix_timestamp>-<random>` or custom slug) |
| `title` | String | Human-readable task title |
| `prompt` | String | Full task prompt/description (also updated for edits) |
| `description` | String | Alternative to prompt (legacy) |
| `result` | String | Task result/output (legacy) |
| `status` | String | One of: `PENDING`, `WORKING`, `COMPLETED`, `FAILED`, `ORPHANED` |
| `assigned_to` | String | Agent name (e.g., `temujin`, `kublai`). Always set on creation alongside `agent`. |
| `agent` | String | Agent name (legacy field, kept for backward compat; `assigned_to` is canonical) |
| `priority` | String | One of: `critical`, `high`, `normal`, `low` |
| `domain` | String | Task domain (e.g., `ops`, `dev`, `research`) |
| `source` | String | Origin of the task (e.g., `kanban-ui`, `kanban-review`, `kublai_router`, `reflection-api-rollback`) |
| `skill_hint` | String | Suggested skill for execution (e.g., `/horde-review`) |
| `created_at` | DateTime | When the task was created |
| `started_at` | DateTime | When execution began |
| `completed_at` | DateTime | When execution finished |
| `updated_at` | DateTime | Last modification timestamp |
| `sort_order` | Integer | UI ordering within kanban columns (higher = first) |
| `retry_count` | Integer | Number of retries attempted |
| `max_retries` | Integer | Maximum retries allowed (default 3) |
| `claim_epoch` | Integer | Incremented on retry to prevent stale claims |
| `depth` | Integer | Task nesting depth (for subtasks) |
| `timeout_s` | Integer | Task timeout in seconds |
| `score` | Float | Quality score |
| `paused` | Boolean | Whether the task is paused |
| `paused_at` | DateTime | When the task was paused |
| `parent_task` | String | task_id of parent task (for review tasks) |
| `reassigned_from` | String | Previous agent (set during redistribution) |
| `reassigned_at` | DateTime | When redistribution occurred |
| `reflection_id` | String | Associated reflection ID (for rollback tasks) |
| `retry_after` | DateTime | Earliest time a retried task should be re-attempted |
| `orphaned_at` | DateTime | When the task was detected as orphaned (WORKING with no active executor) |

### Event

Calendar events from Signal integration, used by `/api/calendar/events`.

| Property | Type | Description |
|----------|------|-------------|
| `event_id` | String | Unique event identifier |
| `name` | String | Event name/title |
| `description` | String | Event description |
| `start_datetime` | DateTime | Event start time |
| `end_datetime` | DateTime | Event end time |
| `status` | String | Event status |
| `visibility` | String | Event visibility |
| `all_day` | Boolean | Whether event spans full day |
| `created_at` | DateTime | When the event was created |
| `updated_at` | DateTime | Last modification timestamp |

---

## Status Mapping

Neo4j statuses map to kanban board columns:

| Neo4j Status | Board Column | Description |
|-------------|-------------|-------------|
| `PENDING` | pending | Waiting for execution |
| `WORKING` | executing | Currently being processed |
| `COMPLETED` | done | Successfully finished |
| `FAILED` | failed | Execution failed |
| `ORPHANED` | failed | Was WORKING but executor disappeared; recovered by watchdog |

Defined in `neo4j.js` as `STATUS_MAP`.

---

## Common Query Patterns

### Load Kanban Board
```cypher
MATCH (t:Task)
WHERE t.status IN ['PENDING', 'WORKING', 'COMPLETED', 'FAILED', 'ORPHANED']
RETURN t {.*} AS task
ORDER BY coalesce(t.sort_order, 0) DESC,
  CASE t.priority
    WHEN 'critical' THEN 0 WHEN 'high' THEN 1
    WHEN 'normal' THEN 2 WHEN 'low' THEN 3 ELSE 4
  END, t.created_at DESC
LIMIT 500
```

### Agent Status (Counts)
```cypher
MATCH (t:Task)
WHERE t.status IN ['PENDING', 'WORKING'] AND t.assigned_to IS NOT NULL
RETURN t.assigned_to AS agent, t.status AS status, count(t) AS cnt
```

### Filtered Task Query (Paginated)
```cypher
MATCH (t:Task)
WHERE t.status = $filterStatus AND t.assigned_to = $filterAgent
RETURN t {.*} AS task
ORDER BY t.created_at DESC
SKIP $offset LIMIT $limit
```

### Create Wake Task
```cypher
CREATE (t:Task {
  task_id: $taskId, title: 'Self-wake: process pending tasks',
  prompt: 'Check and process any pending tasks in your queue.',
  status: 'PENDING', assigned_to: $agent, priority: 'normal',
  domain: 'ops', source: 'kanban-ui', created_at: datetime(),
  retry_count: 0, max_retries: 1, depth: 0, timeout_s: 1800
})
```

### Retry Failed Task
```cypher
MATCH (t:Task {task_id: $taskId, assigned_to: $agent, status: 'FAILED'})
SET t.status = 'PENDING', t.retry_count = 0,
    t.claim_epoch = coalesce(t.claim_epoch, 0) + 1,
    t.updated_at = datetime()
RETURN t.task_id AS id
```

### Pause Task
```cypher
MATCH (t:Task {task_id: $taskId, status: 'PENDING'})
SET t.paused = true, t.paused_at = datetime(), t.updated_at = datetime()
RETURN t.task_id AS id
```

### Resume Task
```cypher
MATCH (t:Task {task_id: $taskId, paused: true})
REMOVE t.paused, t.paused_at
SET t.updated_at = datetime()
RETURN t.task_id AS id
```

### Redistribute Tasks (Load Balancing)
```cypher
-- Step 1: Find overloaded agents
MATCH (t:Task {status: 'PENDING'})
WHERE t.assigned_to IN $agents AND NOT coalesce(t.paused, false)
RETURN t.assigned_to AS agent, count(t) AS pending

-- Step 2: Move excess tasks (keep 2 per overloaded agent)
MATCH (t:Task {assigned_to: $fromAgent, status: 'PENDING'})
WHERE NOT coalesce(t.paused, false)
WITH t ORDER BY
  CASE t.priority WHEN 'low' THEN 0 WHEN 'normal' THEN 1
    WHEN 'high' THEN 2 WHEN 'critical' THEN 3 ELSE 1 END ASC,
  t.created_at ASC
LIMIT $limit
SET t.reassigned_from = t.assigned_to,
    t.assigned_to = $toAgent,
    t.reassigned_at = datetime(), t.updated_at = datetime()
RETURN t.task_id AS id, t.reassigned_from AS from_agent, $toAgent AS to_agent
```

### Reorder Tasks
```cypher
MATCH (t:Task {task_id: $taskId})
SET t.sort_order = $order, t.updated_at = datetime()
```

### Move Task to Top
```cypher
-- Get max sort_order
MATCH (t:Task) RETURN max(coalesce(t.sort_order, 0)) AS m

-- Set new order = max + 1
MATCH (t:Task {task_id: $taskId})
SET t.sort_order = $order, t.updated_at = datetime()
```

### Find Working Tasks (Active Sessions)
```cypher
MATCH (t:Task {status: 'WORKING'})
RETURN t.assigned_to AS agent, t.task_id AS taskId, t.title AS title,
       t.priority AS priority, t.started_at AS startedAt
```

---

## Legacy Fallback

When Neo4j is unavailable, `loadTasksLegacy()` reads task files directly from the filesystem:
- Path: `~/.openclaw/agents/<agent>/tasks/<filename>`
- Status parsed from filename extensions (`.executing.md`, `.completed.done`, `.failed.done`, etc.)
- Priority parsed from filename prefix (`critical-`, `high-`, `normal-`, `low-`)
- Frontmatter parsed from YAML-like block between `---` delimiters

This fallback is triggered automatically when `loadTasks()` catches a Neo4j error.

---

## Indexes

### Composite Indexes

Composite indexes improve performance for common multi-property queries:

- `(Task.status, Task.assigned_to)` -- kanban board queries, agent workload counts
- `(Task.status, Task.updated_at)` -- archival queries, stale task detection

### Single-Property Indexes

- `Task.task_id` -- uniqueness constraint (implicit index)

**Note:** Legacy single-property indexes (`task_agent_index`, `task_status_index`, `task_created_idx`) were dropped on 2026-03-19 as they are subsumed by the composite indexes above.

**Note:** Skill and Domain nodes were removed in the v2 schema overhaul (consistent with architecture.md v1.8). All skill/domain data is stored as string properties on Task nodes. There are no separate Skill or Domain constraints.

---

## v2 Executor Observability

The v2 executor (`neo4j_v2_executor.py`) provides:

- **Heartbeat file**: `~/.openclaw/agents/main/logs/v2-executor-heartbeat.json` — updated every 30s with `timestamp`, `pid`, `poll_count`, `active_tasks`, `status` (idle/executing)
- **Ledger emission**: Writes EXECUTING/COMPLETED/FAILED events to `~/.openclaw/tasks/task-ledger.jsonl` with `executor: "claude-code"` field
- **Idle logging**: Logs "Poll cycle N: no PENDING tasks" every ~5 minutes when queues are empty
- **Orphan recovery**: Calls `promote_orphans()` and `recover_orphans()` every ~5 minutes

---

## Archival Strategy

Completed and failed tasks are archived to JSONL cold storage after a configurable retention period (default: 30 days).

- **Script**: `neo4j_archive_tasks.py`
- **Archive location**: `~/.openclaw/archives/tasks/<date>.jsonl`
- **Batch size**: 100 tasks per transaction
- **Includes**: Task properties, associated TaskOutput, and FailureReport nodes
- **Orphan cleanup**: FailureReport nodes without parent Tasks are also cleaned up
- **Usage**: `python3 neo4j_archive_tasks.py --dry-run` to preview, `--execute` to run
