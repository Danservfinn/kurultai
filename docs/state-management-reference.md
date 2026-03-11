# State Management Reference

**Version:** 1.0
**Date:** 2026-03-07
**Author:** Chagatai (Writer)
**Domain:** Infrastructure / Operations

---

## Overview

The Kurultai uses **three state stores** that must stay consistent. Most bugs involving "missing tasks", "wrong counts", or "stale metrics" trace back to desync between these stores.

```
                    +-----------------------+
                    |       NEO4J           |  Queryable history
                    |  (Task, Agent nodes)  |  Metrics, summaries
                    +-----------+-----------+
                                |
                  neo4j-state-sync.py (reconciler)
                                |
                    +-----------+-----------+
                    |     FILESYSTEM        |  Source of truth
                    |  agents/*/tasks/*.md  |  for execution state
                    +-----------+-----------+
                                |
                     json_state.py (locking)
                                |
                    +-----------+-----------+
                    |   JSON STATE FILES    |  Operational state
                    |  logs/*-state.json    |  (watcher, dispatch,
                    +-----------------------+   watchdog, cooldowns)
```

---

## Store 1: Filesystem Task Files

**Location:** `~/.openclaw/agents/<agent>/tasks/`
**Source of truth for:** Task execution lifecycle
**Written by:** `task_intake.py` (create), `task-watcher.py` (rename on state change), `agent-task-handler.py` (execution)

### File Naming Conventions

| Suffix | Status | Terminal? |
|--------|--------|-----------|
| `.md` (plain) | PENDING | No |
| `.executing.md` | EXECUTING | No |
| `.completed.done.md` | COMPLETED | Yes |
| `.failed.done.md` | FAILED | Yes |
| `.retry-N.md` | Retrying (check further suffix) | No |
| `.stale.done.md` | Stale (treated as COMPLETED) | Yes |
| `.obsolete.done.md` | Obsolete (treated as COMPLETED) | Yes |
| `.absorbed.done.md` | Absorbed into another task | Yes |
| `.dispatched` | Dispatched by auto_dispatch | - |

### Lifecycle

```
task_intake.py creates .md
       |
task-watcher.py renames -> .executing.md
       |
agent-task-handler.py runs Claude Code
       |
   +---+---+
   |       |
success   failure
   |       |
.completed  .failed.done.md
.done.md    (retry if count < MAX_RETRY_COUNT=2)
```

### Key Parameters (task-watcher.py)

| Constant | Value | Meaning |
|----------|-------|---------|
| `TIMEOUT_DEFAULT` | 7200s (2h) | Max execution time per task |
| `STALE_EXECUTING_AGE` | max(priority timeouts) + 120s | Age before task considered stale |
| `HARD_MAX_EXECUTING_AGE` | 10800s (3h) | Force-kill even if PID alive |
| `MAX_RETRY_COUNT` | 2 | Max retries before `.failed.done` |

---

## Store 2: Neo4j Graph Database

**Connection:** `bolt://localhost:7687` (credentials in `~/.openclaw/credentials/neo4j.env`)
**Source of truth for:** Metrics, historical queries, cross-agent patterns
**Connection factory:** `neo4j_task_tracker.get_driver()` (sole entry point)

### Schema

```cypher
(:Agent {name})
(:Task {label, agent, status, created, completed, priority, mode,
        retry_count, error, session_key, started, updated})
(:Agent)-[:EXECUTED]->(:Task)
(:Task)-[:RETRIED]->(:Task)

# Experimentation nodes (Store 1B)
(:Hypothesis {id, agent, description, target_files, expected_impact,
              baseline_metric, confidence, learning_id, variable_type,
              control_value, treatment_value, created, status})

# Feedback nodes (Store 1C)
(:AgentFeedback {id, agent, feedback, priority, proposals,
                submitted, status})
(:Agent)-[:SUBMITTED]->(:AgentFeedback)
```

### Status Values

Neo4j uses UPPERCASE: `ready`, `running`, `completed`, `failed`, `killed`

### Key Classes

- `TaskTracker` in `neo4j_task_tracker.py` - CRUD operations
  - `create_task()` - Creates Task node + EXECUTED relationship
  - `update_status()` - Atomic status update with timestamps
  - `get_hourly_summary()` - Per-agent counts for last N hours
  - `get_completion_rate()` - Success/failure rates

### Known Desync: Neo4j vs Filesystem

**Root cause:** `task-watcher.py` renames files on state change but **does not update Neo4j**. Neo4j Task nodes can stay `ready`/`running` forever while filesystem shows completion.

**Reconciler:** `neo4j-state-sync.py`
```bash
python3 neo4j-state-sync.py           # Dry run (report mismatches)
python3 neo4j-state-sync.py --apply   # Fix Neo4j to match filesystem
python3 neo4j-state-sync.py --verbose # Show all scanned files
```

**Rule:** Filesystem is source of truth for execution state. Neo4j is updated to match, never the reverse.

**When to run:** After any incident involving stuck tasks, after model failures that produce bulk failed tasks, or routinely via tock (every 30min).

---

## Store 1B: Neo4j Hypothesis Nodes

**Purpose:** Track autoresearch experiments generated from KublaiLearning patterns
**Source:** `hypothesis_generator.py` creates nodes, `neo4j_task_tracker.validate_hypotheses()` updates status
**Lifecycle:** pending → testing → validated/rejected

### Hypothesis Node Schema

```cypher
(:Hypothesis {
    id: "hyp-<uuid8>",           # Unique identifier
    agent: "temujin",              # Target agent (or "all")
    description: "Using skill hint /horde-implement...",  # Human-readable hypothesis
    target_files: ["scripts/task_intake.py"],  # Files this would modify
    expected_impact: "success_rate:+5%",  # Metric and direction
    baseline_metric: 0.75,         # Current value
    confidence: 0.85,              # 0.0-1.0 based on evidence
    learning_id: "kl-abc123",      # Source KublaiLearning node (optional)
    variable_type: "skill_hint",   # model, prompt_template, timeout, etc.
    control_value: "none",         # Current value
    treatment_value: "horde-implement",  # Proposed new value
    created: datetime(),
    status: "pending"              # pending, testing, validated, rejected, expired
})
```

### Validation Logic (`neo4j_task_tracker.validate_hypotheses()`)

| Condition | Action |
|-----------|--------|
| Hypothesis age > 2h AND matching completed task exists | Mark `validated` |
| Hypothesis age > 24h AND no match found | Mark `expired` |
| Otherwise | Keep `pending` |

### Generation Sources

1. **KublaiLearning nodes** (`_generate_from_learnings`) - Active patterns with confidence > 0.5
2. **Failure patterns** (`_generate_from_failures`) - Recurring error types with 3+ occurrences
3. **Duration outliers** (`_generate_from_durations`) - Tasks with p95 > 3× p50
4. **Reflection feedback** (`_generate_from_reflections`) - Agent complaints about context/tools/timeout

---

## Store 1C: Neo4j AgentFeedback Nodes

**Purpose:** Capture structured proposals/feedback from agents during kurultai reflection
**Source:** `meta_reflection.py` creates nodes when agents submit proposals
**Status Flow:** pending_review → reviewed → implemented/dismissed

### AgentFeedback Node Schema

```cypher
(:AgentFeedback {
    id: "af-<uuid8>",           # Unique identifier
    agent: "chagatai",            # Submitting agent
    feedback: "Summary of proposed improvement",  # Human-readable feedback
    priority: "high",             # low, medium, high, critical
    proposals: ["prop1", "prop2"],# Array of proposal references
    submitted: datetime(),
    status: "pending_review"      # pending_review, reviewed, implemented, dismissed
})

(:Agent {name: "chagatai"})-[:SUBMITTED]->(:AgentFeedback)
```

### Query Examples

```cypher
# Get pending feedback for review
MATCH (f:AgentFeedback {status: 'pending_review'})
RETURN f ORDER BY
    CASE f.priority
        WHEN 'critical' THEN 1
        WHEN 'high' THEN 2
        WHEN 'medium' THEN 3
        ELSE 4
    END, f.submitted DESC

# Mark feedback as reviewed
MATCH (f:AgentFeedback {id: 'af-abc123'})
SET f.status = 'reviewed',
    f.reviewed_at = datetime()
```

---

## Store 3: JSON State Files

**Location:** `~/.openclaw/agents/main/logs/`
**Source of truth for:** Script operational state between runs
**Locking:** `json_state.py` provides `locked_json_read()` (shared lock) and `locked_json_update()` (exclusive lock with fsync)

### State Files

| File | Used By | Contents |
|------|---------|----------|
| `task-watcher-state.json` | `task-watcher.py` | Active executions, last scan times |
| `auto-dispatch-state.json` | `auto_dispatch.py` | Dispatch history, cooldowns |
| `ogedei-watchdog-state.json` | `ogedei-watchdog.py` | Watchdog findings, queue audit |
| `self-wake-state.json` | `agent-self-wake.py` | Wake schedule, last wake times |
| `rule-compliance-state.json` | `parse_rule_compliance.py` | Rule tracking |

### Locking Model

```python
# Read-only (shared lock, non-blocking for other readers):
data = locked_json_read(filepath)

# Read-modify-write (exclusive lock, blocks all others):
with locked_json_update(filepath) as data:
    data['key'] = 'value'
# File fsynced to disk on context exit, then lock released.
```

**Guarantees:**
- `locked_json_update` uses `O_RDWR | O_CREAT` to atomically create files (no TOCTOU race)
- Write is `seek(0) + truncate() + json.dump() + flush() + fsync()` under exclusive lock
- On `JSONDecodeError`, returns the default (no crash, data reset)

**13 scripts** import `json_state`: task-watcher, auto_dispatch, ogedei-watchdog, kublai-actions, kublai-initiative, kurultai_brainstorm, queue-audit, agent-self-wake, health_dashboard, agent-task-handler.

### Other Shared JSON Files (no locking)

| File | Contents |
|------|----------|
| `logs/action-cooldowns.json` | Per-action cooldown timestamps |
| `logs/initiative-cooldown.json` | Initiative action cooldowns |
| `logs/brainstorm-cooldown.json` | Brainstorm cycle cooldowns |
| `logs/brainstorm-domain-rotation.json` | Domain rotation state |
| `logs/routing-audit-latest.json` | Latest routing audit results |

These files are written by single scripts so locking is unnecessary, but concurrent reads are safe.

---

## Consistency Model

### Write Paths

| Event | Filesystem | Neo4j | JSON State |
|-------|-----------|-------|------------|
| Task created | `task_intake.py` writes `.md` | `task_intake.py` calls `create_task_full()` | - |
| Task dispatched | `auto_dispatch.py` renames `.dispatched` | - | `auto-dispatch-state.json` |
| Execution starts | `task-watcher.py` renames `.executing` | - | `task-watcher-state.json` |
| Execution completes | `task-watcher.py` renames `.completed.done` | **NOT UPDATED** | `task-watcher-state.json` |
| Execution fails | `task-watcher.py` renames `.failed.done` | **NOT UPDATED** | `task-watcher-state.json` |
| Hypothesis created | - | `hypothesis_generator.py` creates Hypothesis node | - |
| Hypothesis validated | - | `neo4j_task_tracker.validate_hypotheses()` updates status | - |
| Agent feedback | - | `meta_reflection.py` creates AgentFeedback node | - |
| Reconciliation | (source of truth) | `neo4j-state-sync.py --apply` | - |

### Known Failure Modes

1. **Neo4j shows stale status after execution** - task-watcher never updates Neo4j on completion/failure. Run `neo4j-state-sync.py --apply`.

2. **Ledger count mismatch** - Failed tasks recorded in Neo4j but not synced to ledger counters. The ledger reads from filesystem; Neo4j counts diverge after bulk failures.

3. **Task-watcher rename race** - `mark_task_completed()` fails when `recover_stale_executions()` renames the file first. The file no longer exists at the expected path.

4. **Double-dispatch after watcher restart** - task-watcher tracked active tasks only in memory. After restart, it dispatched duplicates alongside zombie `.executing` files. Fixed: now checks `.executing` files on disk before dispatching.

5. **JSON state corruption** - If a script crashes mid-write without `json_state.py` locking, the JSON file can be truncated/empty. `locked_json_read` returns `default` on parse error (silent recovery).

---

## Troubleshooting Quick Reference

```bash
# Check filesystem task state for an agent
ls -la ~/.openclaw/agents/temujin/tasks/

# Check Neo4j task state
python3 -c "
from neo4j_task_tracker import TaskTracker
t = TaskTracker()
for task in t.get_tasks_by_agent('temujin', limit=5):
    print(f\"{task.get('label', '?')}: {task.get('status', '?')}\")
t.close()
"

# Find Neo4j/filesystem mismatches
python3 neo4j-state-sync.py --verbose

# Fix mismatches
python3 neo4j-state-sync.py --apply

# Read a JSON state file safely
python3 -c "
from json_state import locked_json_read
import json
print(json.dumps(locked_json_read('logs/task-watcher-state.json'), indent=2))
"

# Check for lock contention (should return quickly)
time python3 -c "from json_state import locked_json_read; locked_json_read('logs/task-watcher-state.json')"
```

---

## Guidelines for Script Authors

1. **Always use `json_state.py`** for any JSON file read by multiple scripts. Never use raw `json.load/dump`.
2. **Always use `neo4j_task_tracker.get_driver()`** for Neo4j connections. Never create `GraphDatabase.driver()` directly.
3. **Filesystem is source of truth** for task execution state. If Neo4j disagrees, Neo4j is wrong.
4. **Terminal states are immutable.** Once a file has `.done` suffix, do not rename it again.
5. **After bulk failures**, run `neo4j-state-sync.py --apply` to reconcile counts.
