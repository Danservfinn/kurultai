# Task Dispatch Reference

**Version:** 1.0
**Date:** 2026-03-09
**Author:** Chagatai (Kurultai Content Specialist)
**Domain:** task_dispatch
**Status:** Reference Documentation

---

## Overview

This document provides a complete reference for the Kurultai task dispatch system. It complements `architecture.md` by focusing on state transitions, failure modes, and operational details.

**Quick links:**
- [Task State Machine](#task-state-machine)
- [Key Scripts](#key-scripts)
- [Common Failure Modes](#common-failure-modes)
- [Circuit Breaker](#circuit-breaker)
- [Neo4j Integration](#neo4j-integration)

---

## Task State Machine

### State Transition Diagram

```
                    ┌─────────────────────────────────────┐
                    │         HUMAN / CRON                │
                    │     creates task via intake         │
                    └─────────────────┬───────────────────┘
                                      │
                                      ▼
                    ┌─────────────────────────────────────┐
                    │          PENDING                    │◄─────────┐
                    │  • In agent queue (filesystem)      │          │
                    │  • In Neo4j (status=PENDING)        │          │
                    │  • Awaiting pickup                 │          │
                    └─────────────────┬───────────────────┘          │
                                      │                             │
                        ┌─────────────┴─────────────┐               │
                        │ task-watcher.py detects   │               │
                        │ new task file             │               │
                        └─────────────┬─────────────┘               │
                                      │                             │
                                      ▼                             │
                    ┌─────────────────────────────────────┐          │
                    │         DISPATCHING                  │          │
                    │  • Claim atomic (Neo4j CAS)         │          │
                    │  • Rename to .executing.md          │          │
                    │  • Spawn agent-task-handler.py      │          │
                    └─────────────────┬───────────────────┘          │
                                      │                             │
                        ┌─────────────┴─────────────┐               │
                        │          AGENT            │               │
                        │   executes task           │               │
                        └─────────────┬─────────────┘               │
                                      │                             │
                        ┌─────────────┴─────────────┐               │
                        │                         │               │
                        ▼                         ▼               │
              ┌───────────────────┐     ┌───────────────────┐      │
              │    COMPLETED      │     │      FAILED       │      │
              │  • .completed.done│     │  • .failed.done   │      │
              │  • Neo4j=COMPLETE │     │  • Neo4j=FAILED   │      │
              │  • Ledger event   │     │  • Ledger event   │      │
              └───────────────────┘     └─────────┬─────────┘      │
                                                │                 │
                                    ┌───────────┴───────────┐      │
                                    │   Retry logic         │      │
                                    │   (max 2 retries)     │      │
                                    └───────────┬───────────┘      │
                                                │                 │
                                    ┌───────────┴───────────┐      │
                                    │                       │      │
                                    ▼                       │      │
                          ┌───────────────────┐            │      │
                          │    .retry-N.md    │            │      │
                          │  (back to PENDING)│────────────┘      │
                          └───────────────────┘                   │
                                                                │
                                    ┌───────────────────────────┘
                                    │
                                    ▼
                          ┌───────────────────┐
                          │  .failed.done     │
                          │  (permanent)      │
                          └───────────────────┘
```

### State Definitions

| State | File Extension | Neo4j Status | Description |
|-------|---------------|--------------|-------------|
| **PENDING** | `.md` | `PENDING` | Task created, awaiting pickup |
| **DISPATCHING** | `.executing.md` | `EXECUTING` | Agent claimed task, executing |
| **COMPLETED** | `.completed.done.md` | `COMPLETED` | Task finished successfully |
| **FAILED** | `.failed.done.md` | `FAILED` | Task failed after all retries |
| **RETRY** | `.retry-N.md` | `PENDING` | Queued for retry (N=1,2) |

### Timeout Rules

| Priority | Timeout | Slow Skills |
|----------|---------|-------------|
| high | 7200s (2h) | All horde skills: 7200s |
| normal | 7200s (2h) | (skill-specific overrides) |
| low | 7200s (2h) | See `SLOW_SKILLS` in agent-task-handler.py |

**Stale detection:** After 2820s (47min) of no file modification, task-watcher marks task as stale and may retry.

---

## Key Scripts

### task_intake.py

**Purpose:** Single entry point for all task creation.

**Location:** `scripts/task_intake.py`

**Pipeline:**
```
1. Validate depth (< MAX_DEPTH=3)
2. Route via task_router.py
3. Duplicate check (has_pending_task)
4. Create in Neo4j (primary) via create_task_full()
5. Write filesystem (backward compat)
```

**Usage:**
```python
from task_intake import create_task

task_id = create_task(
    title="Investigate error spike",
    body="Check logs for errors...",
    priority="high",
    source="kublai-actions",
    depth=0,
    agent=None,  # auto-route
)
```

**Key functions:**
- `create_task()` - Main entry point
- `classify_task_domain()` - Maps task to domain (research, implementation, etc.)
- `compute_task_timeout()` - Returns timeout based on priority + skill
- `has_pending_task()` - Duplicate detection

### task-watcher.py

**Purpose:** Watches agent task directories and dispatches for execution.

**Location:** `scripts/task-watcher.py`

**Run mode:** Daemon process (15s poll interval)

**Pipeline:**
```
1. Poll agents/{agent}/tasks/ for .md files
2. Claim task atomically via Neo4j CAS
3. Rename to .executing.md
4. Spawn agent-task-handler.py in separate thread
5. Monitor for stale tasks (>47min no modification)
6. Retry up to 2x, then mark .failed.done
```

**Key functions:**
- `get_pending_tasks_from_neo4j()` - Queries pending tasks
- `claim_task_atomic()` - CAS pattern for distributed claim
- `check_neo4j_task_status()` - Verify task state

**State file:** `logs/task-watcher-state.json`

### agent-task-handler.py

**Purpose:** Executes individual tasks for an agent.

**Location:** `scripts/agent-task-handler.py`

**Pipeline:**
```
1. Read task file + extract frontmatter
2. Load agent memory (context.md + log)
3. Build prompt with skill hint directive
4. Launch claude-agent subprocess
5. Monitor for timeout (2h default)
6. On completion: rename to .completed.done
7. Record metrics to ledger + Neo4j
```

**Usage:**
```bash
python3 agent-task-handler.py --agent temujin --task-file /path/to/task.md
```

**Key features:**
- Prompt injection protection
- Circuit breaker integration
- Prompt optimizer (enhances task prompts)
- Fallback model handling (glm-5 for rate limits)

---

## Common Failure Modes

### 1. Stale Task (No Progress)

**Symptoms:**
- Task stuck in `.executing.md` for >47 minutes
- No file modifications in workspace
- Agent shows "executing" but not responsive

**Causes:**
- Claude Code session hung/crashed
- Network timeout during API call
- System resource exhaustion

**Resolution:**
- **Automatic:** task-watcher retries up to 2x (`.retry-1.md`, `.retry-2.md`)
- **Manual:** Move task file to `.failed.done.md` and create new task

**Prevention:**
- Circuit breaker tracks agent health
- Quality-aware diversion routes away from failing agents

### 2. Duplicate Task

**Symptoms:**
- Two tasks with similar titles in queue
- Same work being done twice

**Causes:**
- Human sends duplicate requests
- Race condition in task creation
- Reflection generates overlapping tasks

**Resolution:**
- `has_pending_task()` checks first 40 chars of title
- Manual: `rm agents/{agent}/tasks/duplicate.md`

**Prevention:**
- task_intake.py deduplication on create
- Neo4j uniqueness constraint on task_id

### 3. Queue Imbalance

**Symptoms:**
- One agent has 5+ pending tasks
- Other agents idle (0 tasks)

**Causes:**
- Routing bias to specific agent
- Load balancing thresholds not triggered
- Capability matrix mismatch

**Resolution:**
- **Automatic:** task-redistribute.py runs on TICK
- **Manual:** Move task files between agent queues
- **Fix:** Adjust `QUEUE_HIGH_THRESHOLD` or `AGENT_CAPABILITY_MATRIX`

**Prevention:**
- Quality-aware diversion checks success rates
- Load balancing triggers at 3+ pending (was 20)

### 4. Credential Failure (100% Error Rate)

**Symptoms:**
- All tasks for an agent failing
- Error logs show "auth" or "credential" errors
- Agent shows 0% success rate

**Causes:**
- Invalid API token in agent's settings.json
- Rate limit exceeded (Anthropic API)
- Wrong API endpoint configured

**Resolution:**
- **Immediate:** Update `ANTHROPIC_AUTH_TOKEN` in agent settings
- **Fallback:** System auto-switches to glm-5 after 1 retry
- **Escalate:** Create escalation task for ogedei if fleet-wide

**Current status (2026-03-09):**
- temujin, chagatai affected by DashScope token issue
- See `memory/MEMORY.md` credential crisis section

### 5. Neo4j Connection Lost

**Symptoms:**
- Tasks only in filesystem, not Neo4j
- Query errors in logs
- State sync failures

**Causes:**
- Neo4j service down
- Network issue to Neo4j port
- Driver connection pool exhausted

**Resolution:**
- **Automatic:** Falls back to filesystem-only mode
- **Manual:** `system-health-check.py` to diagnose
- **Recovery:** `neo4j-state-sync.py` to resync

**Prevention:**
- Lazy-load Neo4j driver (never blocks execution)
- Connection pooling with timeout

---

## Circuit Breaker

### Purpose

Prevents cascading failures by tracking agent health and routing away from failing agents.

### Location

`scripts/circuit_breaker.py`

### States

| State | Meaning | Action |
|-------|---------|--------|
| CLOSED | Agent healthy | Route normally |
| OPEN | Agent failing | Route to alternates |
| HALF_OPEN | Testing recovery | Allow limited traffic |

### Thresholds

| Metric | Threshold | Action |
|--------|-----------|--------|
| Consecutive failures | 3 | Open circuit |
| Success rate (domain) | <50% | Divert to overflow |
| Last failure | >30min ago | Test recovery (HALF_OPEN) |

### Usage

```python
from circuit_breaker import AgentCircuitBreaker

breaker = AgentCircuitBreaker()

# Check if agent is healthy
if breaker.is_agent_healthy("temujin"):
    route_to_agent("temujin")
else:
    route_to_alternative("temujin")
```

### State File

`logs/circuit-breaker-state.json`

---

## Neo4j Integration

### Neo4j-First Architecture (Phase 2)

**Status:** Completed 2026-03-09

Neo4j is now the **primary source of truth** for task state. Filesystem queues are maintained for backward compatibility.

### Node Schema

```cypher
// Task node
(:Task {
  task_id: string,        // Unique identifier
  title: string,          // Task title
  body: string,           // Full task description
  agent: string,          // Assigned agent
  status: string,         // PENDING|EXECUTING|COMPLETED|FAILED
  priority: string,       // high|normal|low
  domain: string,         // research|implementation|ops|...
  skill_hint: string,     // Suggested skill invocation
  parent_id: string,      // Parent task (for subtasks)
  depth: int,             // Nesting depth (max 3)
  retry_count: int,       // Number of retries
  session_key: string,    // Claim verification key
  created: datetime,      // Creation timestamp
  claimed: datetime,      // When claimed
  completed: datetime,    // When completed
})

// Agent node
(:Agent {
  name: string,           // Agent name
  status: string,         // idle|executing
  tasks_completed: int,   // Lifetime completions
  tasks_failed: int,      // Lifetime failures
  current_task: string,   // Currently executing task_id
})
```

### Atomic Transitions

**Claim (CAS pattern):**
```cypher
MATCH (t:Task {task_id: $task_id, status: 'PENDING'})
SET t.status = 'EXECUTING',
    t.session_key = $session_key,
    t.claimed = datetime()
RETURN t
```

**Complete:**
```cypher
MATCH (t:Task {task_id: $task_id, session_key: $session_key})
SET t.status = 'COMPLETED',
    t.completed = datetime()
RETURN t
```

### Queries

**Get pending tasks for agent:**
```python
# See get_pending_tasks_from_neo4j() in task-watcher.py
result = session.run("""
    MATCH (t:Task {agent: $agent, status: 'PENDING'})
    RETURN t.task_id as task_id, t.title as title, ...
    ORDER BY t.priority, t.created ASC
    LIMIT $limit
""", agent=agent, limit=10)
```

**Check task status:**
```python
# See check_neo4j_task_status() in task-watcher.py
result = session.run("""
    MATCH (t:Task {task_id: $task_id})
    RETURN t.status as status, t.session_key as session_key, ...
""", task_id=task_id)
```

---

## Depth Limits

### Why Depth Limits Exist

Tasks can spawn subtasks. Without limits, exponential growth would overwhelm the system.

### Rules

| Depth | Meaning | Limit |
|-------|---------|-------|
| 0 | Root task (human/cron) | No limit |
| 1 | Direct subtask | Allowed |
| 2 | Subtask of subtask | Allowed |
| 3+ | Too nested | **REJECTED** |

### Enforcement

```python
# In task_intake.py
MAX_DEPTH = 3

if depth >= MAX_DEPTH:
    raise ValueError(f"Task depth {depth} exceeds MAX_DEPTH {MAX_DEPTH}")
```

### Parent-Child Tracking

```yaml
# Task frontmatter
task_id: "abc123"
parent_id: "xyz789"  # Parent task that spawned this
depth: 1
```

---

## File Structure

```
~/.openclaw/agents/
├── main/
│   ├── scripts/
│   │   ├── task_intake.py          # Task creation
│   │   ├── task-watcher.py         # Dispatch daemon
│   │   ├── agent-task-handler.py   # Execution
│   │   ├── circuit_breaker.py      # Health tracking
│   │   ├── task-redistribute.py    # Load balancing
│   │   └── neo4j_task_tracker.py   # Neo4j operations
│   ├── logs/
│   │   ├── task-ledger.jsonl       # All task events
│   │   ├── task-watcher-state.json # Watcher state
│   │   ├── circuit-breaker-state.json
│   │   └── routing-decisions.jsonl
│   └── docs/
│       └── task-dispatch-reference.md  # This file
├── {agent}/
│   ├── tasks/
│   │   ├── {task-id}.md              # PENDING
│   │   ├── {task-id}.executing.md    # EXECUTING
│   │   ├── {task-id}.completed.done.md
│   │   └── {task-id}.retry-1.md
│   └── workspace/
│       └── task-{epoch}.md
```

---

## Related Documentation

- `routing-pipeline-reference.md` - **Routing decision pipeline** (how tasks get assigned to agents)
- `architecture.md` - Complete system architecture
- `completion-gate.md` - Task verification standards
- `heartbeat-troubleshooting.md` - TICK gap diagnosis
- `queue-monitoring-design.md` - Load balancing design
- `credential-troubleshooting.md` - API credential issues

---

**Document Metadata:**
- Author: Chagatai (Writer)
- Domain: task_dispatch
- Last updated: 2026-03-09
- Reflection cycle: 2026-03-09 06:00
