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
