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
| `status` | String | One of: `PENDING`, `WORKING`, `COMPLETED`, `FAILED`, `ORPHANED`, `OBSOLETE`. `OBSOLETE` is a soft-delete written by Hermes's `task_custodian` sweep (duplicates, harmful prompts); the pre-obsolete status is preserved in `previous_status` so Signal `revert <task_id>` can restore it. |
| `previous_status` / `previous_prompt` / `previous_agent` | String | Pre-mutation values captured by `task_custodian` mutations for revert. |
| `obsolete_reason` / `obsolete_by` / `obsolete_at` | String / String / DateTime | Set by `mark_obsolete()`. |
| `rewrite_reason` / `rewrite_by` / `rewritten_at` / `original_prompt` | String / String / DateTime / String | Set by `rewrite_prompt()`. `original_prompt` only captures the FIRST pre-rewrite prompt, so subsequent rewrites never lose the true operator intent. |
| `reassign_reason` / `reassigned_by` / `reassigned_from` / `reassigned_at` | String / String / String / DateTime | Set by `reassign()`. |
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

### CalendarEvent (label: `:CalendarEvent`)

Calendar events, used by `/api/calendar/events`. Split from `:Event` label on 2026-03-23.

| Property | Type | Description |
|----------|------|-------------|
| `event_id` | String | Unique event identifier (`evt-<ts>-<rand>`) |
| `name` | String | Event name/title |
| `description` | String | Event description |
| `start_datetime` | DateTime | Event start time (required) |
| `end_datetime` | DateTime | Event end time |
| `status` | String | `active` / `cancelled` |
| `category` | String | `personal`, `social`, `work`, `agent`, `health`, `deadline`, `travel`, `finance` |
| `tags` | List\<String\> | Freeform labels, e.g. `["outdoor","camping"]` |
| `priority` | String | `critical` / `normal` / `low` |
| `source` | String | `manual`, `signal_parse`, `agent_auto` |
| `source_agent` | String | Agent name if agent-created, else null |
| `url` | String | Ticket link, venue page, etc. |
| `notes` | String | Prep notes, parking info |
| `outdoor` | Boolean | Weather-sensitive flag |
| `suggested_by` | String | Who proposed the idea |
| `visibility` | String | Event visibility |
| `all_day` | Boolean | Whether event spans full day |
| `created_at` | DateTime | When the event was created |
| `updated_at` | DateTime | Last modification timestamp |

**Relationships:** `(:CalendarEvent)-[:AT_LOCATION]->(:Location)`, `(:Person)-[:ATTENDING]->(:CalendarEvent)`, `(:CalendarEvent)-[:CREATED_BY]->(:Person)`, `(:CalendarEvent)-[:HAS_REMINDER]->(:Reminder)`

### Reminder (label: `:Reminder`)

Linked to CalendarEvent via `(:CalendarEvent)-[:HAS_REMINDER]->(:Reminder)`. Added 2026-03-23.

| Property | Type | Description |
|----------|------|-------------|
| `reminder_id` | String | Unique ID (`rem-<ts>-<rand>`) |
| `event_id` | String | Parent event ID (denormalized) |
| `offset_minutes` | Integer | Minutes before event start to fire |
| `fire_at` | DateTime | Precomputed absolute fire time |
| `channel` | String | `signal_dm`, `dashboard`, `both` |
| `status` | String | `pending`, `sent`, `acknowledged`, `snoozed` |
| `sent_at` | DateTime | When delivered |
| `snooze_until` | DateTime | If snoozed, new fire time |
| `attempt_count` | Integer | Delivery attempts |
| `last_error` | String | Last failure reason |
| `created_at` | DateTime | Creation timestamp |

**Indexes:** `(status, fire_at)` composite, `(event_id)`, unique constraint on `reminder_id`.

### LifecycleEvent (label: `:LifecycleEvent`, also `:Event`)

Append-only lifecycle event nodes emitted by `neo4j_v2_events.py` for task execution observability. Split from shared `:Event` label on 2026-03-23 — these nodes have NO `start_datetime`.

**Properties:**

| Property | Type | Description |
|----------|------|-------------|
| `event_id` | String | UUID, unique per event |
| `event_type` | String | One of the `EVENT_TYPES` set (see below) |
| `task_id` | String | Associated task (empty for system events like `EXECUTOR_STARTED`) |
| `agent` | String | Agent name |
| `executor_id` | String | Executor instance ID (format: `exec-<hex8>`) |
| `ts` | DateTime | Event timestamp (UTC) |
| `duration_s` | Float | Task execution duration (on completion/failure events) |
| `error_category` | String | Failure classification (on failure events) |
| `error_msg` | String | Short error description (on failure events) |
| `model` | String | Model used for execution |
| `fallback_model` | String | Model used after primary fallback |
| `session_action` | String | Session cleanup description (on `SESSION_RESET` events) |
| `reason` | String | Human-readable reason (on `FALSE_COMPLETION_BLOCKED`, etc.) |

**Event Types** (`neo4j_v2_events.EVENT_TYPES`):

| Event Type | Description |
|------------|-------------|
| `TASK_CLAIMED` | Task claimed by executor for execution |
| `TASK_EXECUTING` | Subprocess started for task |
| `TASK_COMPLETED` | Task passed `verify_result()` and persisted as COMPLETED |
| `TASK_FAILED` | Transient failure (will retry) |
| `TASK_FAILED_PERMANENT` | Permanent failure (max retries exhausted) |
| `SESSION_RESET` | Session cleanup triggered (bloat or model drift) |
| `MODEL_FALLBACK` | Primary model failed, attempting fallback |
| `MODEL_FALLBACK_SUCCESS` | Fallback model succeeded |
| `MODEL_FALLBACK_FAILED` | Fallback model also failed |
| `STALL_DETECTED` | Stdout silence + lsof confirmed stall |
| `LEASE_RENEWED` | WORKING task lease extended |
| `ORPHAN_RECOVERED` | Orphaned WORKING task reset to PENDING |
| `FALSE_COMPLETION_BLOCKED` | Exit code 0 but error patterns detected in output |
| `EXECUTOR_STARTED` | Executor process started |
| `EXECUTOR_STOPPED` | Executor process stopped |

**Relationships:**
- `(Event)-[:ABOUT]->(Task)` -- links event to the task it describes (created when `task_id` is non-empty)

### AgentMetrics

Incrementally updated per-agent performance counters, maintained by `neo4j_v2_events.py`. One node per agent, updated on every `TASK_COMPLETED` or `TASK_FAILED_PERMANENT` event.

**Properties:**

| Property | Type | Description |
|----------|------|-------------|
| `agent` | String | Agent name (MERGE key) |
| `tasks_completed_24h` | Integer | Completed task count |
| `tasks_failed_24h` | Integer | Failed task count |
| `success_rate_24h` | Float | `completed / (completed + failed)` |
| `avg_duration_s_24h` | Float | Running average of completion duration |
| `session_resets_24h` | Integer | Session reset count |
| `last_updated` | DateTime | Last counter update |

**Note:** Counter names include `_24h` but are not automatically windowed -- they accumulate until externally reset.

### Inference (Multi-Label)

Knowledge graph nodes created by the ASMR extraction pipeline (`asmr_extractor.py`). All inference nodes carry the base `:Inference` label plus one or more type-specific labels.

**Multi-label combinations:**

| Labels | MERGE Key | Description |
|--------|-----------|-------------|
| `:Inference:PersonalFact` | `(humanId, key)` | Key/value facts (name, email, role, etc.) |
| `:Inference:Preference` | `(humanId, domain, canonical_key)` | Domain-scoped preferences with valence |
| `:Inference:CalendarEvent` | `(humanId, title, startTime)` | Calendar events extracted from messages |
| `:Inference:TemporalSeq` | CREATE (chain) | Facts that change over time, linked via `[:SUPERSEDES]` |

**Common Properties (all Inference nodes):**

| Property | Type | Description |
|----------|------|-------------|
| `id` | String | UUID |
| `humanId` | String | Associated human |
| `value` | String | The fact value |
| `confidence` | Float | Extraction confidence (0.0--1.0) |
| `active` | Boolean | Whether this fact is current |
| `superseded` | Boolean | Whether a newer fact has replaced this one |
| `supersededAt` | DateTime | When this fact was superseded |
| `scope` | String | `dm` or channel identifier |
| `field` | String | Structured field name (for conflict detection) |
| `timestamp` | DateTime | When extracted |
| `category` | String | `ASSISTANT_PREF` for behavioral instructions |

**PersonalFact-specific:** `key` (closed enum: name, email, phone, role, company, location, relationship, age, birthday, timezone, language, other)

**Preference-specific:** `domain` (closed enum: communication, schedule, format, content, tool, social), `canonical_key`, `valence` (LIKE, DISLIKE, NEUTRAL), `strength` (0.0--1.0)

**CalendarEvent-specific:** `title`, `startTime`, `eventType` (MEETING, APPOINTMENT, DEADLINE, REMINDER, ANNIVERSARY), `status`

**TemporalSeq-specific:** `subject`, `isCurrent` (Boolean), `validFrom` (DateTime)

**Relationships:**
- `(Inference)-[:SUPERSEDES]->(Inference)` -- audit chain for fact corrections (see below)

---

## Relationships

### [:SUPERSEDES] (Inference Audit Chain)

Created by `supersede_detector.py` when a new fact replaces an old one. Maintains a full audit trail.

**Properties:**

| Property | Type | Description |
|----------|------|-------------|
| `detected_at` | DateTime | When the supersede was detected |
| `reason` | String | Why the old fact was replaced (e.g., `explicit_correction`, `field_conflict`) |
| `confidence` | Float | Detection confidence |
| `signal_text` | String | Verbatim text that triggered detection (e.g., "actually", "changed to") |
| `old_value` | String | Previous value (captured from the old Inference node) |
| `new_value` | String | Current value (captured from the new Inference node) |

**Detection triggers** (`supersede_detector.EXPLICIT_SIGNALS`):
- "actually", "changed to", "no longer", "correction:", "update:"
- "my X is now", "I moved to", "I switched to"
- "new email/number/phone/address", "FYI ... changed/updated/new"
- "I don't X anymore", "not X anymore"

**Key functions:**
- `detect_explicit_signal(text)` -- check for correction signals
- `find_conflicting_inferences(session, human_id, field, new_value, ts)` -- find active contradictions
- `mark_superseded(session, new_id, old_id, reason, confidence, signal_text)` -- atomically mark old + create relationship
- `find_active_contradictions(session, human_id)` -- find unresolved same-field conflicts
- `process_supersedes(session, human_id, field, new_value, new_id, signal_text)` -- end-to-end pipeline

### Other Relationships

| Relationship | From | To | Description |
|-------------|------|-----|-------------|
| `[:ABOUT]` | Event | Task | Links lifecycle event to its task |
| `[:PROPOSED]` | Agent | Proposal | Who proposed it |
| `[:IMPLEMENTED_BY]` | Proposal | Task | Implementation tasks |
| `[:VOTED_ON]` | Agent | Vote | Who voted |
| `[:FOR_PROPOSAL]` | Vote | Proposal | What they voted on |
| `[:HAS_OUTPUT]` | Task | TaskOutput | Task completion output |

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

### Proposal

Represents a proposed change from the reflection cycle. Created by `proposal_manager.py` or `reflection_proposal_extractor.py`.

**Properties:**

| Property | Type | Description |
|----------|------|-------------|
| `proposal_id` | String | Unique identifier (UUID[:12] or `{agent}-{timestamp}-{slug}`) |
| `title` | String | Proposal title |
| `description` | String | Full proposal body/rationale |
| `proposing_agent` | String | Agent who proposed this |
| `created_at` | DateTime | When proposed |
| `expires_at` | DateTime | Tier-specific TTL (T2: 5h, T3: 14h, legacy: 24h) |
| `status` | String | `pending`, `approved`, `rejected`, `expired`, `implementing`, `implemented` |
| `priority` | String | `normal`, `high`, `critical` |
| `category` | String | `feature`, `self-rule`, `routing`, `reliability`, `monitoring`, etc. |
| `tier` | String | Approval tier: `T0` (bypass), `T1` (auto-approve), `T2` (4/6 majority), `T3` (5/6 supermajority) |
| `implementation_tasks` | List[String] | Task IDs created from this proposal |
| `reflection_cycle` | String | Reflection cycle ID that generated this proposal |
| `vote_yes_count` | Integer | Cached YES vote count |
| `vote_no_count` | Integer | Cached NO vote count |
| `vote_abstain_count` | Integer | Cached ABSTAIN count |
| `vote_total` | Integer | Cached total votes |
| `vote_unanimous` | Boolean | Cached: `total = 6 AND no = 0` (legacy compat) |
| `vote_threshold_met` | Boolean | Cached: tier-aware threshold check |

**Relationships:**
- `(Agent)-[:PROPOSED]->(Proposal)` — who proposed it
- `(Proposal)-[:IMPLEMENTED_BY]->(Task)` — implementation tasks

### Vote

Individual agent vote on a Proposal.

**Properties:**

| Property | Type | Description |
|----------|------|-------------|
| `vote_id` | String | Unique identifier |
| `proposal_id` | String | Associated proposal |
| `agent` | String | Voting agent |
| `decision` | String | `yes`, `no`, `abstain` |
| `reasoning` | String | Vote rationale |
| `voted_at` | DateTime | When vote was cast |
| `updated_at` | DateTime | Last vote change |
| `reflection_cycle` | String | Reflection cycle context |

**Relationships:**
- `(Agent)-[:VOTED_ON]->(Vote)` — who voted
- `(Vote)-[:FOR_PROPOSAL]->(Proposal)` — what they voted on

---

## Proposal Approval Pipeline

### Tiered Approval (added 2026-03-23)

| Tier | Threshold | TTL | Auto-Cast Proposer Vote | Use Case |
|------|-----------|-----|------------------------|----------|
| T0 | Bypass (0 votes) | 1h | Yes | CRITICAL infra actions (restart, fix) |
| T1 | Auto-approve (0 votes) | 1h | Yes | Self-scoped rules (agent modifying own behavior) |
| T2 | 4/6 majority | 5h (4h + 1h buffer) | No (proposer excluded) | Cross-agent rules, new skills |
| T3 | 5/6 supermajority | 14h (12h + 2h buffer) | No (proposer excluded) | System-wide changes |

**Kublai veto**: A `kublai` NO vote on any T2/T3 proposal immediately excludes it from `check_threshold_met()` results.

**Key scripts:**
- `proposal_manager.py` — CRUD, `create_proposal(tier=)`, `check_threshold_met()`, `check_unanimous_approval()` (legacy)
- `proposal_approval_handler.py` — `--process` converts approved proposals to tasks via `task_intake.py`
- `voting_manager.py` — File-based voting with tier-aware windows and consensus
- `reflection_proposal_extractor.py` — Extracts proposals from reflection markdown, classifies tiers, routes T0→tasks, T1→auto-approve, T2+→voting
- `proposal_ingest.py` — Bridges filesystem `.md` proposals to Neo4j nodes
- `proposal_expiration.py` — Expires proposals past `expires_at`

### Common Proposal Queries

```cypher
-- Find proposals meeting their tier's threshold
MATCH (p:Proposal {status: 'pending'})
OPTIONAL MATCH (p)<-[:FOR_PROPOSAL]-(v:Vote)
WITH p,
    count(v) AS total_votes,
    sum(CASE WHEN v.decision = 'yes' THEN 1 ELSE 0 END) AS yes_count,
    coalesce(p.tier, 'T2') AS tier
RETURN p.proposal_id, p.title, yes_count, tier

-- Proposal tier distribution
MATCH (p:Proposal) WHERE p.tier IS NOT NULL
RETURN p.tier, p.status, count(p)

-- Check kublai veto
MATCH (p:Proposal {status: 'pending'})<-[:FOR_PROPOSAL]-(v:Vote {agent: 'kublai', decision: 'no'})
RETURN p.proposal_id, p.title
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

## Indexes and Constraints

### Uniqueness Constraints

| Constraint | Property | Added |
|------------|----------|-------|
| `task_id_unique` | `Task.task_id` | Legacy |
| `event_id_unique` | `Event.event_id` | 2026-03-22 |
| `agent_metrics_unique` | `AgentMetrics.agent` | 2026-03-22 |

### Composite Indexes

Composite indexes improve performance for common multi-property queries:

- `(Task.status, Task.assigned_to)` -- kanban board queries, agent workload counts
- `(Task.status, Task.updated_at)` -- archival queries, stale task detection

### Event Indexes (added 2026-03-22)

| Index Name | Properties | Purpose |
|------------|-----------|---------|
| `v2_event_type_ts` | `(Event.event_type, Event.ts)` | Filter events by type within time range |
| `v2_event_task_id` | `(Event.task_id)` | Look up all events for a specific task |
| `v2_event_agent_ts` | `(Event.agent, Event.ts)` | Per-agent event timeline |

### Inference Indexes (added 2026-03-22)

| Index Name | Properties | Purpose |
|------------|-----------|---------|
| `inference_superseded` | `(Inference.superseded)` | Filter active vs superseded inferences |
| `inference_human_field` | `(Inference.humanId, Inference.field)` | Conflict detection queries |
| `inference_scope` | `(Inference.scope)` | Scope-filtered queries (dm vs channel) |
| `pf_human_key` | `(PersonalFact.humanId, PersonalFact.key)` | MERGE on personal facts |
| `pref_human_domain` | `(Preference.humanId, Preference.domain)` | MERGE on preferences |
| `cal_human_status` | `(CalendarEvent.humanId, CalendarEvent.status)` | Calendar event lookup |
| `ts_human_current` | `(TemporalSeq.humanId, TemporalSeq.isCurrent)` | Current temporal fact lookup |

**Note:** Legacy single-property indexes (`task_agent_index`, `task_status_index`, `task_created_idx`) were dropped on 2026-03-19 as they are subsumed by the composite indexes above.

**Note:** Skill and Domain nodes were removed in the v2 schema overhaul (consistent with architecture.md v1.8). All skill/domain data is stored as string properties on Task nodes. There are no separate Skill or Domain constraints.

---

## Task Executor Observability

The unified task executor (`task_executor.py`, see [task-executor.md](task-executor.md)) provides two complementary observability layers:

### File-Based (legacy compatibility)

- **Heartbeat file**: `~/.openclaw/agents/main/logs/task-executor-heartbeat.json` -- updated every 30s with `timestamp`, `pid`, `executor_id`, `poll_count`, `active_tasks`, `status` (idle/active)
- **Ledger emission**: Writes TASK_COMPLETED/TASK_FAILED events to `~/.openclaw/tasks/task-ledger.jsonl` with `executor: "claude-code"` field
- **PID lock**: `~/.openclaw/agents/main/logs/task-executor.pid` -- single-instance enforcement

### Graph-Based (Event nodes via `neo4j_v2_events.py`)

- **Event nodes**: Append-only Event nodes for every lifecycle transition (see Event node type above)
- **AgentMetrics nodes**: Incrementally updated per-agent counters (see AgentMetrics node type above)
- **WAL buffering**: When Neo4j is unavailable, operations are buffered to `~/.openclaw/neo4j-wal.db` (SQLite) and replayed on reconnect (`neo4j_v2_wal.py`)

---

## Archival Strategy

Completed and failed tasks are archived to JSONL cold storage after a configurable retention period (default: 30 days).

- **Script**: `neo4j_archive_tasks.py`
- **Archive location**: `~/.openclaw/archives/tasks/<date>.jsonl`
- **Batch size**: 100 tasks per transaction
- **Includes**: Task properties, associated TaskOutput, and FailureReport nodes
- **Orphan cleanup**: FailureReport nodes without parent Tasks are also cleaned up
- **Usage**: `python3 neo4j_archive_tasks.py --dry-run` to preview, `--execute` to run
