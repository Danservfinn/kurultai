# Ogedei Persistent Dispatcher — Design Document

> **NOTE (2026-03-23):** This design document is historical. The v2-executor referenced throughout was replaced by the unified `task_executor.py` daemon. See `architecture.md` for current state.

**Version:** 1.0
**Date:** 2026-03-20
**Author:** Kublai (system architect)
**Status:** Proposal

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Architecture Diagram](#architecture-diagram)
3. [Design Decision: Execution Model](#1-persistent-execution-model)
4. [Task Queue Monitoring](#2-task-queue-monitoring)
5. [Agent Availability Tracking](#3-agent-availability-tracking)
6. [Task Dispatch Mechanism](#4-task-dispatch-mechanism)
7. [Health Monitoring](#5-health-monitoring)
8. [Self-Health](#6-self-health)
9. [Graceful Degradation](#7-graceful-degradation)
10. [Implementation Plan](#implementation-plan)
11. [Configuration](#configuration)
12. [Migration Path](#migration-path)

---

## Executive Summary

This document proposes replacing the current two-process task execution pipeline (`task-watcher.py` polling filesystem + `agent-task-handler.py` spawning Claude Code) and the separate `ogedei-watchdog.py` quality daemon with a **unified persistent dispatcher** running as the Ogedei agent itself.

**Current state (three processes):**
- `neo4j_v2_executor.py` — asyncio poll loop, claims PENDING tasks from Neo4j, spawns `claude-agent` (replaced `task-watcher.py` as of Phase 4 cutover 2026-03-12)
- `ogedei-watchdog.py` — 30s daemon, 18 health checks per cycle
- `agent-task-handler.py` — called by v2-executor to build prompts and run claude-agent

**Proposed state (one process):**
- `ogedei-dispatcher.py` — single asyncio process that merges v2-executor's claim-and-dispatch loop, ogedei-watchdog's health checks, and agent-task-handler's prompt construction. Ogedei becomes the system's nervous system.

**Why this matters:**
- Eliminates coordination bugs between three separate processes
- Gives Ogedei agency-level awareness (it *is* the scheduler, not just a watchdog)
- Reduces PID count from 3 persistent + N transient to 1 persistent + N transient
- Enables Ogedei to make intelligent scheduling decisions (priority inversion detection, agent affinity, cost-aware dispatch)

---

## Architecture Diagram

### Current Architecture

```
                    ┌─────────────────────────────────────────────┐
                    │             macOS launchd                    │
                    └───┬─────────────┬──────────────┬────────────┘
                        │             │              │
                  ┌─────▼─────┐ ┌────▼────┐  ┌──────▼───────┐
                  │v2-executor│ │ ogedei  │  │  heartbeat   │
                  │ (poll 30s)│ │watchdog │  │  writer etc  │
                  │           │ │(poll 30s│  │              │
                  └─────┬─────┘ └────┬────┘  └──────────────┘
                        │            │
                   ┌────▼────┐  ┌────▼────────────────────┐
                   │ Neo4j   │  │ Filesystem              │
                   │TaskStore│  │ (tasks/, logs/, state)   │
                   └────┬────┘  └─────────────────────────┘
                        │
          ┌─────────────┼──────────────────────┐
          │             │                      │
    ┌─────▼───┐   ┌────▼────┐          ┌──────▼──────┐
    │claude   │   │claude   │   ...    │claude       │
    │-agent   │   │-agent   │          │-agent       │
    │temujin  │   │mongke   │          │ogedei       │
    └─────────┘   └─────────┘          └─────────────┘
```

### Proposed Architecture

```
                    ┌─────────────────────────────────────────────┐
                    │             macOS launchd                    │
                    └───┬─────────────────────────┬───────────────┘
                        │                         │
                  ┌─────▼───────────────────┐ ┌───▼──────────┐
                  │   OGEDEI DISPATCHER     │ │  heartbeat   │
                  │   (ogedei-dispatcher.py)│ │  writer etc  │
                  │                         │ └──────────────┘
                  │  ┌───────────────────┐  │
                  │  │ Scheduler Loop    │  │
                  │  │ (poll Neo4j 15s)  │  │
                  │  └────────┬──────────┘  │
                  │           │             │
                  │  ┌────────▼──────────┐  │
                  │  │ Health Monitor    │  │
                  │  │ (18 checks/cycle) │  │
                  │  └────────┬──────────┘  │
                  │           │             │
                  │  ┌────────▼──────────┐  │
                  │  │ Agent Tracker     │  │
                  │  │ (semaphore+Neo4j) │  │
                  │  └──────────────────┘  │
                  └───┬───────┬─────┬──────┘
                      │       │     │
                ┌─────▼─┐ ┌──▼──┐ ┌▼──────┐
                │claude │ │cla..│ │claude  │   Ogedei dispatches
                │-agent │ │-ag..│ │-agent  │   but does NOT dispatch
                │temujin│ │mon..│ │chagatai│   to itself (avoids
                └───────┘ └─────┘ └───────┘   recursive deadlock)
                                               Ogedei's own tasks
                                               execute inline.
```

### Key Architectural Change

Ogedei becomes the **control plane** rather than a **data plane worker**. It no longer receives tasks the same way other agents do. Instead:

1. **Other agents' tasks** are dispatched by Ogedei via `claude-agent` subprocess (same as today)
2. **Ogedei's own tasks** (ops, monitoring, incident response) are either:
   - Handled inline by the dispatcher's health checks (no subprocess needed)
   - Executed via a dedicated inline worker (for skill-requiring tasks)
3. **Kublai remains the router** — task classification and creation unchanged

---

## 1. Persistent Execution Model

### Options Evaluated

| Option | Mechanism | Latency | Complexity | Resilience |
|--------|-----------|---------|------------|------------|
| **(A) True persistent process** | Python asyncio daemon, launchd `KeepAlive` | ~15s (poll) | Low | High — launchd auto-restart |
| **(B) Cron-triggered every N seconds** | launchd `StartInterval` + single-shot script | N seconds + startup | Medium | Medium — cold start each time |
| **(C) Neo4j change stream** | APOC triggers or custom CDC | <1s | High | Low — Neo4j dependency |
| **(D) Hybrid: persistent + cron watchdog** | Option A + a 60s cron that checks if A is alive | ~15s (poll) | Low-Medium | Very High |

### Recommendation: Option D (Hybrid)

**Rationale:**
- The v2-executor already proves that a persistent asyncio daemon works well on this system
- A true persistent process gives the lowest latency and simplest state management
- The cron watchdog provides the critical self-healing guarantee (see Section 6)
- Neo4j change streams (Option C) would add a hard dependency on Neo4j APOC plugins and are overkill for a 7-agent system
- Pure cron (Option B) wastes resources on process startup/teardown every cycle and loses in-memory state (active task tracking, circuit breaker state, agent availability cache)

**Why not Option A alone:** A single process with no external watchdog is a single point of failure. If the dispatcher crashes and launchd's `KeepAlive` fails to restart it (which happens — launchd can throttle restarts), the entire task system halts silently.

---

## 2. Task Queue Monitoring

### How Ogedei Detects New Tasks

The dispatcher polls Neo4j on a fixed interval using the existing `TaskStore.claim_task()` CAS pattern from `neo4j_v2_core.py`. This is the same proven mechanism used by v2-executor today.

### Poll Query

```cypher
// Primary: claim highest-priority PENDING task for a specific agent
MATCH (t:Task {assigned_to: $agent, status: 'PENDING'})
WHERE (t.retry_after IS NULL OR t.retry_after <= datetime())
WITH t ORDER BY
    CASE t.priority
        WHEN 'critical' THEN 0
        WHEN 'high' THEN 1
        WHEN 'normal' THEN 2
        WHEN 'low' THEN 3
        ELSE 4
    END ASC,
    t.created_at ASC
LIMIT 1
SET t.status = 'WORKING',
    t.claim_epoch = coalesce(t.claim_epoch, 0) + 1,
    t.claimed_by = $agent,
    t.started_at = datetime(),
    t.updated_at = datetime(),
    t.lease_expires_at = datetime() + duration({minutes: $lease_min})
RETURN t {.*, failure_reports: [/* ... */]} AS task
```

### Poll Interval: 15 seconds (down from 30)

**Rationale:**
- Current v2-executor polls every 30s; ogedei-watchdog polls every 30s. Combined, the system touches Neo4j every ~15s on average already.
- Merging into one process with a 15s interval maintains the same Neo4j load while halving perceived latency for new tasks.
- Critical-priority tasks get checked separately on a 5s fast path (see below).

### Critical Task Fast Path

```python
async def fast_poll_critical(self):
    """Check for critical tasks every 5 seconds (separate from main poll)."""
    while not self.shutdown.is_set():
        try:
            for agent in self.agents:
                task = self.store.claim_critical(agent)  # New method
                if task:
                    await self.dispatch(task)
        except Exception as e:
            logger.warning(f"Critical fast-poll error: {e}")
        await asyncio.sleep(5)
```

Where `claim_critical` adds `AND t.priority = 'critical'` to the claim query.

### Polling vs. Change Streams

**Decision: Polling.**

| Factor | Polling (15s) | Change Streams |
|--------|--------------|----------------|
| Neo4j version req | Any | 5.x+ with APOC Extended |
| Failure mode | Graceful — falls back to filesystem | Hard — stream disconnect = missed events |
| Implementation | Existing code, proven | New CDC consumer, new failure modes |
| Latency | 15s worst case, 5s for critical | Sub-second |
| Debugging | Simple — log each poll | Complex — async event replay |

For a 7-agent system processing ~50-200 tasks/day, 15s polling is more than adequate. Change streams would be justified at 1000+ tasks/day with latency SLAs.

---

## 3. Agent Availability Tracking

### How Ogedei Knows Which Agents Are Free

The dispatcher maintains a combined view from three sources:

```python
class AgentTracker:
    """Track agent availability from multiple signals."""

    def __init__(self, store: TaskStore, circuit_breaker: AgentCircuitBreaker):
        self.store = store
        self.breaker = circuit_breaker
        # In-memory: maps agent -> set of active task_ids
        self._active: dict[str, set[str]] = {a: set() for a in DISPATCH_AGENTS}
        # Concurrency limit per agent (from kurultai.json)
        self._max_concurrent: dict[str, int] = {}

    def is_available(self, agent: str) -> tuple[bool, str]:
        """Check if agent can accept a new task.

        Returns (available, reason) tuple.
        Checks in order: circuit breaker > concurrency > credentials.
        """
        # 1. Circuit breaker state
        cb_state = self.breaker.check_agent(agent)
        if not cb_state["available"]:
            return False, f"circuit_breaker:{cb_state['state']}"

        # 2. Concurrency limit
        active_count = len(self._active[agent])
        max_concurrent = self._max_concurrent.get(agent, 1)
        if active_count >= max_concurrent:
            return False, f"busy:{active_count}/{max_concurrent}"

        # 3. Credential validity (cached, refreshed every 5 min)
        if not self._credentials_valid(agent):
            return False, "credentials_invalid"

        return True, "idle"

    def mark_busy(self, agent: str, task_id: str):
        self._active[agent].add(task_id)

    def mark_idle(self, agent: str, task_id: str):
        self._active[agent].discard(task_id)

    def get_status_all(self) -> dict:
        """Return status of all agents (for dashboard)."""
        return {
            agent: {
                "active_tasks": list(self._active[agent]),
                "active_count": len(self._active[agent]),
                "available": self.is_available(agent)[0],
                "reason": self.is_available(agent)[1],
                "circuit_breaker": self.breaker.check_agent(agent)["state"],
            }
            for agent in DISPATCH_AGENTS
        }
```

### Neo4j Agent State

Agent nodes already exist. The dispatcher updates them:

```cypher
// On task claim
MATCH (a:Agent {name: $agent})
SET a.status = 'busy',
    a.current_task = $task_id,
    a.last_claimed = datetime()

// On task completion/failure
MATCH (a:Agent {name: $agent})
SET a.status = 'idle',
    a.current_task = null,
    a.tasks_completed = coalesce(a.tasks_completed, 0) + 1,
    a.last_completed = datetime()
```

### What Happens When All Agents of a Specialty Are Busy

The dispatcher implements a three-tier overflow strategy (preserving the existing `task_intake.py` logic):

```python
OVERFLOW_MAP = {
    # (primary_agent, task_category) -> overflow_agent
    ("temujin", "deploy"):     "ogedei",
    ("temujin", "ops"):        "ogedei",
    ("mongke",  "research"):   "chagatai",
    ("chagatai", "docs"):      "mongke",
    ("jochi",   "security"):   "temujin",
    ("ogedei",  "ops"):        "temujin",
}

AGENT_CAPABILITY_MATRIX = {
    "temujin":  ["mongke", "ogedei"],   # Can overflow to
    "mongke":   ["chagatai", "jochi"],
    "chagatai": ["mongke"],
    "jochi":    ["temujin", "ogedei"],
    "ogedei":   ["temujin", "jochi"],
}
```

**Decision flow when agent is busy:**

```
1. Is primary agent available?
   YES → dispatch to primary
   NO  → continue

2. Is there a capability-matrix alternate that's idle AND
   whose keywords match the task domain?
   YES → dispatch to alternate
   NO  → continue

3. Is there an overflow-map entry for this (agent, category)?
   YES → dispatch to overflow agent (if available)
   NO  → continue

4. QUEUE the task: leave it in PENDING state.
   Log: "DISPATCH_DEFERRED: {task_id} waiting for {agent} (all alternates busy)"
   The next poll cycle will try again.
```

**Critical invariant:** Tasks are NEVER dropped. The worst case is increased latency, not data loss.

---

## 4. Task Dispatch Mechanism

### Options Evaluated

| Option | Mechanism | Agent Autonomy | Latency | Observability |
|--------|-----------|----------------|---------|---------------|
| **(A)** `claude-agent --workdir <agent_dir> -- <prompt>` | Direct subprocess | Full — agent has all tools, skills, delegation | Instant spawn | stdout capture, stall detection |
| **(B)** `sessions_spawn({ task, agentId, mode: "run" })` | OpenClaw session API | Full — but session management overhead | API call + session init | Session-level tracking |
| **(C)** Write to filesystem + signal | File + IPC | Limited — requires polling | File write + poll interval | Filesystem state |

### Recommendation: Option A (Direct subprocess via `claude-agent`)

**Rationale:**

This is the proven mechanism already in production. The `claude-agent` wrapper at `/Users/kublai/.local/bin/claude-agent`:
- Strips `CLAUDECODE` env var to prevent recursion
- Adds `--dangerously-skip-permissions` for autonomous execution
- Uses `--print` mode for stdout capture
- Supports `--workdir` for agent-specific CLAUDE.md injection
- Supports `--model` override for fallback

**Why not Option B (sessions_spawn):**
- `sessions_spawn` creates OpenClaw-managed sessions, which adds a layer of indirection
- The dispatcher already needs stdout monitoring for stall detection — subprocess gives this natively
- `sessions_spawn` would require polling the session API to detect completion, rather than just waiting on the subprocess

**Why not Option C (filesystem):**
- The v2-executor already proved that direct dispatch is more reliable than filesystem-based queuing
- The old task-watcher.plist is already disabled (Phase 4 cutover 2026-03-12)
- Filesystem signals add latency and race conditions

### Dispatch Implementation

```python
async def dispatch(self, task: dict):
    """Dispatch a task to the appropriate agent."""
    agent = task.get('assigned_to', task.get('agent'))
    task_id = task['task_id']

    # Track in agent tracker
    self.tracker.mark_busy(agent, task_id)

    # Update Neo4j agent state
    self._neo4j_mark_agent_busy(agent, task_id)

    # Emit ledger event
    self._emit_ledger("DISPATCHED", task_id, agent,
                      skill_hint=task.get('skill_hint', ''))

    # Build prompt (same as existing _build_prompt)
    prompt = self._build_prompt(task)

    # Build clean env (same as existing _build_env)
    env = self._build_env(agent)

    # Spawn claude-agent
    cmd = [
        str(CLAUDE_AGENT),
        "--workdir", str(AGENTS_DIR / agent),
        "--effort", task.get('effort', 'medium'),
        "--", prompt
    ]

    try:
        result = await self._run_with_monitoring(cmd, env, task)
        await self._handle_result(task, result)
    finally:
        self.tracker.mark_idle(agent, task_id)
        self._neo4j_mark_agent_idle(agent)
```

### Ogedei's Own Tasks

Ogedei cannot dispatch to itself via subprocess (this would create a second dispatcher or deadlock). Instead:

```python
async def dispatch(self, task: dict):
    agent = task.get('assigned_to')

    if agent == 'ogedei':
        # Execute inline — Ogedei handles its own ops tasks
        await self._execute_ogedei_task_inline(task)
    else:
        # Normal dispatch via claude-agent subprocess
        await self._dispatch_to_subprocess(task)

async def _execute_ogedei_task_inline(self, task: dict):
    """Execute an Ogedei task within the dispatcher process.

    For simple ops tasks (health checks, restarts, log analysis), the
    dispatcher can handle them directly using Bash/filesystem operations.

    For complex tasks requiring skills (e.g., /horde-implement for
    infrastructure builds), spawn a claude-agent in a SEPARATE workdir
    that does NOT load the dispatcher's CLAUDE.md — preventing recursion.
    """
    skill_hint = task.get('skill_hint', '')

    if skill_hint and skill_hint.startswith('/horde'):
        # Complex task: spawn claude-agent with ogedei's workspace
        # but NOT as a dispatcher — just as a worker
        await self._dispatch_to_subprocess(task)
    else:
        # Simple ops task: handle inline
        result = await self._inline_ops_handler(task)
        await self._handle_result(task, result)
```

**Correction on the "cannot dispatch to itself" constraint:** Actually, spawning `claude-agent --workdir agents/ogedei/` is safe because it creates an isolated Claude Code session that reads Ogedei's CLAUDE.md (which has ops instructions, not dispatcher instructions). The dispatcher and the spawned session are separate processes. The constraint is only that the dispatcher should not try to become a Claude Code agent itself — it should remain a Python process.

Therefore, the simpler design is: **Ogedei dispatches to all agents including itself, exactly like the current v2-executor does.** The `agent == 'ogedei'` special case is only needed if we want to optimize simple ops tasks by avoiding the Claude Code overhead.

---

## 5. Health Monitoring

### Merged Health Checks (from ogedei-watchdog.py)

The dispatcher runs health checks on a staggered schedule within the main event loop:

```python
class HealthMonitor:
    """Staggered health checks running inside the dispatcher event loop."""

    CHECKS = {
        # check_name: (function, interval_seconds, last_run)
        "watcher_alive":         (check_watcher_alive,         30,  0),
        "stalled_tasks":         (check_stalled_tasks,         30,  0),
        "recent_completions":    (verify_recent_completions,   30,  0),
        "queue_audit":           (periodic_queue_audit,        1800, 0),
        "cleanup_malformed":     (cleanup_malformed,           300, 0),
        "reflection_pipeline":   (check_reflection_pipeline,   300, 0),
        "memory_health":         (check_memory_health,         1800, 0),
        "routing_drift":         (check_routing_drift,         1800, 0),
        "agent_failure_rates":   (check_agent_failure_rates,   300, 0),
        "credential_failures":   (check_credential_failures,   300, 0),
        "queue_balance":         (check_queue_balance,         300, 0),
        "cascade_risk":          (check_cascade_risk,          600, 0),
        "quality_gate":          (check_quality_gate,          300, 0),
        "self_healing_score":    (update_self_healing_score,   3600, 0),
        "circuit_breaker":       (check_circuit_breaker_health, 300, 0),
        "git_operations":        (check_git_operations,        300, 0),
        "proactive_patrol":      (check_proactive_health_patrol, 300, 0),
        "model_drift":           (check_model_drift,           600, 0),
    }

    async def run_due_checks(self):
        """Run all checks that are due. Non-blocking."""
        now = time.time()
        for name, (func, interval, last_run) in self.CHECKS.items():
            if now - last_run >= interval:
                try:
                    await asyncio.get_event_loop().run_in_executor(
                        None, func
                    )
                    self.CHECKS[name] = (func, interval, now)
                except Exception as e:
                    logger.warning(f"Health check {name} failed: {e}")
```

### Stuck Agent Detection

| Signal | Threshold | Action |
|--------|-----------|--------|
| No stdout for N seconds | 900s (normal), 1200s (slow skill), 2400s (proxy) | SIGTERM -> wait 10s -> SIGKILL |
| Lease expired in Neo4j | `lease_expires_at < datetime()` | Recover orphan -> re-queue as PENDING |
| Process exited with signal | SIGSEGV, SIGBUS, SIGKILL | Classify as crash, fail task, log incident |
| Circuit breaker tripped | >=80% failure rate over 1h (min 3 tasks) | Quarantine agent 30min, overflow tasks |

### Agent Crash Recovery

```python
async def _handle_crash(self, task: dict, result: dict):
    """Handle agent process crash."""
    task_id = task['task_id']
    agent = task['assigned_to']
    claim_epoch = task['claim_epoch']

    error_class, transient = classify_failure(
        result.get('return_code', -1),
        result.get('error', ''),
        result.get('content', ''),
    )

    # Record failure (may retry if transient)
    ok, new_status = self.store.fail_task(
        task_id, claim_epoch, error_class,
        result.get('error', 'Agent crash'),
        transient,
        output_snippet=result.get('content', '')[:2000],
    )

    # Update circuit breaker
    self.tracker.breaker.record_failure(agent)

    # Log incident
    self._emit_ledger("AGENT_CRASH", task_id, agent,
                      error_class=error_class,
                      return_code=result.get('return_code'),
                      new_status=new_status)

    # Pre-dispatch cleanup for next task
    await self._cleanup_orphan_processes(agent)
```

### Metrics Tracked

The dispatcher writes a metrics file every 60 seconds for the dashboard:

```python
METRICS_FILE = LOGS_DIR / "ogedei-dispatcher-metrics.json"

metrics = {
    "timestamp": datetime.now().isoformat(),
    "pid": os.getpid(),
    "uptime_s": time.time() - self._start_time,
    "poll_count": self._poll_count,

    # Throughput
    "tasks_dispatched_1h": self._counter_1h("dispatched"),
    "tasks_completed_1h": self._counter_1h("completed"),
    "tasks_failed_1h": self._counter_1h("failed"),

    # Latency
    "avg_queue_wait_s": self._avg_queue_wait_1h(),
    "avg_execution_s": self._avg_execution_1h(),
    "p95_execution_s": self._p95_execution_1h(),

    # Agent status
    "agents": self.tracker.get_status_all(),

    # Queue depths
    "queue_depths": self._get_queue_depths(),

    # Health
    "health_checks_passed": self._health_pass_count,
    "health_checks_failed": self._health_fail_count,
    "circuit_breakers": {
        agent: self.tracker.breaker.check_agent(agent)
        for agent in DISPATCH_AGENTS
    },

    # Self-health
    "memory_mb": self._get_memory_usage(),
    "thread_count": threading.active_count(),
    "active_tasks": len(self._active_tasks),
}
```

---

## 6. Self-Health

### What If Ogedei Itself Crashes?

Three layers of protection:

### Layer 1: launchd `KeepAlive` (immediate restart)

```xml
<key>KeepAlive</key>
<true/>
```

launchd will restart the process immediately if it exits. This handles most crashes.

### Layer 2: Cron-based heartbeat watchdog (detect silent failures)

A minimal cron job runs every 60 seconds. It checks whether the dispatcher is alive and healthy. If not, it kills the stale process and launchd restarts it.

```python
#!/usr/bin/env python3
"""ogedei-heartbeat-check.py — Lightweight watchdog for the dispatcher.

Runs via launchd every 60s. Checks:
1. Is the dispatcher PID alive?
2. Is the heartbeat file fresh (< 120s old)?
3. Is the metrics file fresh (< 180s old)?

If any check fails, kill the dispatcher and let launchd restart it.
"""

import json, os, signal, sys, time
from pathlib import Path

HEARTBEAT = Path.home() / ".openclaw/agents/main/logs/ogedei-dispatcher-heartbeat.json"
PIDFILE   = Path.home() / ".openclaw/agents/main/logs/ogedei-dispatcher.pid"
MAX_HEARTBEAT_AGE = 120  # seconds

def main():
    # Check PID file
    if not PIDFILE.exists():
        print("WARN: No PID file — dispatcher may not be running")
        return 1

    pid = int(PIDFILE.read_text().strip())

    # Check if process is alive
    try:
        os.kill(pid, 0)  # Signal 0 = check existence
    except ProcessLookupError:
        print(f"DEAD: Dispatcher PID {pid} not found — removing stale PID file")
        PIDFILE.unlink(missing_ok=True)
        return 1
    except PermissionError:
        pass  # Process exists but we can't signal it (shouldn't happen for own user)

    # Check heartbeat freshness
    if not HEARTBEAT.exists():
        print("WARN: No heartbeat file yet")
        return 0  # Grace period on first startup

    age = time.time() - HEARTBEAT.stat().st_mtime
    if age > MAX_HEARTBEAT_AGE:
        print(f"STALE: Heartbeat is {age:.0f}s old (max {MAX_HEARTBEAT_AGE}s) — killing PID {pid}")
        try:
            os.kill(pid, signal.SIGTERM)
            time.sleep(5)
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        except ProcessLookupError:
            pass
        PIDFILE.unlink(missing_ok=True)
        return 1

    # Read heartbeat data
    try:
        hb = json.loads(HEARTBEAT.read_text())
        active = hb.get("active_tasks", 0)
        poll = hb.get("poll_count", 0)
        print(f"OK: PID={pid}, polls={poll}, active={active}, age={age:.0f}s")
    except Exception as e:
        print(f"WARN: Heartbeat parse error: {e}")

    return 0

if __name__ == "__main__":
    sys.exit(main())
```

### Layer 3: Startup orphan recovery (survive unclean shutdown)

On startup, the dispatcher:
1. Reads the PID file. If a previous instance is still running, kills it.
2. Queries Neo4j for WORKING tasks with expired leases.
3. Transitions them to ORPHANED -> PENDING for retry.
4. Replays the WAL (write-ahead log) for any buffered state transitions.

```python
async def startup(self):
    """Startup sequence with orphan recovery."""
    # Write PID file
    self._pidfile.write_text(str(os.getpid()))

    # Recover orphaned tasks
    logger.info("Running startup orphan recovery...")
    recovered = self.store.recover_orphans(grace_minutes=5)
    if recovered:
        logger.info(f"Recovered {len(recovered)} orphans")

    # Replay WAL
    pending = self.wal.pending_count()
    if pending:
        replayed = self.wal.replay(self.store.driver)
        logger.info(f"Replayed {replayed} WAL entries")

    # Reconstruct in-memory state from Neo4j
    self._rebuild_tracker_from_neo4j()
```

### Why NOT dual-Ogedei with leader election?

- Leader election requires a consensus mechanism (ZooKeeper, Redis lock, etc.)
- Adds significant complexity for marginal benefit
- The three-layer approach (launchd + cron watchdog + startup recovery) provides equivalent availability guarantees for a single-machine deployment
- If the Kurultai moves to multi-machine, leader election becomes necessary — but that's a different architecture

---

## 7. Graceful Degradation

### If Neo4j Is Down

The dispatcher maintains a **filesystem fallback** path that mirrors the original task-watcher.py behavior:

```python
class FilesystemFallback:
    """Fallback task detection when Neo4j is unavailable.

    Scans agent task directories for .md files (excluding .executing, .done, .failed).
    This is the same mechanism task-watcher.py used before the Neo4j migration.
    """

    def scan_pending_tasks(self) -> list[dict]:
        """Scan filesystem for pending task files."""
        tasks = []
        for agent in DISPATCH_AGENTS:
            tasks_dir = AGENTS_DIR / agent / "tasks"
            if not tasks_dir.exists():
                continue
            for f in sorted(tasks_dir.glob("*.md")):
                # Skip non-pending states
                if any(s in f.name for s in ['.executing', '.done', '.failed',
                                              '.retry', '.gate', '.resolved']):
                    continue
                task_id = self._extract_task_id(f)
                tasks.append({
                    'task_id': task_id or f.stem,
                    'assigned_to': agent,
                    'file_path': str(f),
                    'priority': self._extract_priority(f.name),
                    'source': 'filesystem_fallback',
                })
        return tasks

    def claim_via_rename(self, task: dict) -> bool:
        """Claim a task by renaming to .executing.md (atomic on POSIX)."""
        src = Path(task['file_path'])
        dst = src.with_suffix('.executing.md')
        try:
            src.rename(dst)
            task['file_path'] = str(dst)
            return True
        except FileExistsError:
            return False  # Another process claimed it
```

### Degradation Cascade

```
Neo4j healthy     → Normal operation (Neo4j claim + dispatch)
                     │
Neo4j unreachable → Filesystem fallback (scan .md + rename)
                     │
                     ├── WAL: buffer state transitions for replay
                     │         when Neo4j recovers
                     │
                     └── Periodic retry: attempt Neo4j reconnect every 60s
                     │
Neo4j recovered   → Replay WAL, sync filesystem state to Neo4j,
                     resume normal operation
```

### Dispatch Failure Retry Strategy

```python
RETRY_SCHEDULE = {
    # error_class: (max_retries, backoff_base_seconds)
    "STALL":           (2, 60),    # Retry twice, 60s then 120s backoff
    "TIMEOUT":         (1, 300),   # Retry once after 5 min
    "RATE_LIMIT":      (3, 120),   # Retry 3x with 2min backoff
    "AUTH_ERROR":      (1, 600),   # Retry once after 10 min (credential refresh)
    "CRASH":           (2, 60),    # Retry twice
    "VALIDATION":      (2, 30),    # Retry twice quickly
    "EXECUTOR_ERROR":  (1, 120),   # Retry once
    "PERMANENT":       (0, 0),     # No retry — mark FAILED immediately
}
```

When a dispatch fails:
1. Classify the failure (using existing `neo4j_v2_failure.classify_failure`)
2. Look up retry schedule
3. If retries remain: set `retry_after = now + backoff`, transition to PENDING
4. If exhausted: transition to FAILED, score the failure, notify

### If the Dispatch Mechanism Itself Fails

If `subprocess.Popen` fails (e.g., `claude-agent` binary missing, permissions error):

```python
try:
    proc = subprocess.Popen(cmd, ...)
except FileNotFoundError:
    # Claude agent binary missing — critical infrastructure failure
    self._emit_alert("CRITICAL", "claude-agent binary not found",
                     recovery="Check ~/.local/bin/claude-agent")
    # Fail the task as non-transient
    self.store.fail_task(task_id, epoch, "INFRA_MISSING",
                         "claude-agent not found", is_transient=False)
except PermissionError:
    # Permission issue
    self._emit_alert("CRITICAL", "claude-agent not executable")
    self.store.fail_task(task_id, epoch, "INFRA_PERMS",
                         "claude-agent not executable", is_transient=False)
except OSError as e:
    # General OS error (OOM, too many files, etc.)
    self.store.fail_task(task_id, epoch, "OS_ERROR",
                         str(e), is_transient=True)
```

---

## Implementation Plan

### Phase 1: Scaffold (1-2 hours)

1. Create `ogedei-dispatcher.py` with the asyncio skeleton:
   - Main event loop
   - Signal handlers (SIGTERM, SIGINT for graceful shutdown)
   - PID file management
   - Heartbeat file writer
   - Logging setup (to `logs/ogedei-dispatcher.log`)

2. Port the `Executor` class from `neo4j_v2_executor.py`:
   - `TaskStore` integration
   - `WAL` integration
   - `poll_cycle()` with 15s interval
   - `run_claude_agent()` with stall detection
   - Startup orphan recovery

### Phase 2: Agent Tracker (1 hour)

3. Implement `AgentTracker`:
   - In-memory active task tracking
   - Circuit breaker integration
   - Neo4j agent status updates
   - Credential validation cache

4. Implement overflow logic (port from `task_intake.py`):
   - `OVERFLOW_MAP`
   - `AGENT_CAPABILITY_MATRIX`
   - Domain keyword matching for alternate selection

### Phase 3: Health Monitor (2 hours)

5. Port all 18 health checks from `ogedei-watchdog.py`:
   - Convert synchronous functions to `run_in_executor` wrappers
   - Implement staggered scheduling
   - Add the critical-task fast-poll coroutine

### Phase 4: Self-Health (30 minutes)

6. Create `ogedei-heartbeat-check.py` (cron watchdog)
7. Create `com.kurultai.ogedei-dispatcher.plist`
8. Create `com.kurultai.ogedei-heartbeat.plist`

### Phase 5: Filesystem Fallback (1 hour)

9. Implement `FilesystemFallback` class
10. Integrate with main poll cycle (try Neo4j first, fallback to filesystem)
11. WAL buffer for offline state transitions

### Phase 6: Cutover (30 minutes)

12. Disable `com.kurultai.v2-executor.plist` (set `RunAtLoad` to false)
13. Disable `com.kurultai.ogedei-watchdog.plist` (set `RunAtLoad` to false)
14. Enable `com.kurultai.ogedei-dispatcher.plist`
15. Monitor logs for 1 hour
16. Verify task throughput matches pre-cutover baseline

### Phase 7: Cleanup (30 minutes)

17. Archive `neo4j_v2_executor.py` and `ogedei-watchdog.py` to `_archived/`
18. Update `architecture.md` (this document)
19. Update dashboard to read from `ogedei-dispatcher-metrics.json`

**Total estimated effort: 6-8 hours**

---

## Configuration

### `kurultai.json` Changes

```json
{
  "agents": {
    "ogedei": {
      "role": "dispatcher",
      "executor": "native",
      "effort": "high",
      "max_concurrent_subagents": 6,
      "dispatcher_config": {
        "poll_interval_s": 15,
        "critical_poll_interval_s": 5,
        "lease_minutes": 45,
        "lease_renew_interval_s": 600,
        "health_check_enabled": true,
        "filesystem_fallback_enabled": true,
        "metrics_interval_s": 60,
        "max_concurrent_dispatches": 6
      }
    }
  }
}
```

Note: Ogedei's executor changes from `"claude-code"` to `"native"` because it is no longer a Claude Code agent that receives tasks — it IS the task system. It can still spawn Claude Code sessions for its own complex ops tasks.

### launchd Plist: `com.kurultai.ogedei-dispatcher.plist`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.kurultai.ogedei-dispatcher</string>

    <key>ProgramArguments</key>
    <array>
        <string>/opt/homebrew/bin/python3</string>
        <string>/Users/kublai/.openclaw/agents/main/scripts/ogedei-dispatcher.py</string>
    </array>

    <key>WorkingDirectory</key>
    <string>/Users/kublai/.openclaw/agents/main</string>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>/Users/kublai/.openclaw/agents/main/logs/ogedei-dispatcher.log</string>

    <key>StandardErrorPath</key>
    <string>/Users/kublai/.openclaw/agents/main/logs/ogedei-dispatcher.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/Users/kublai/.local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/local/bin</string>
        <key>OPENCLAW_STATE_DIR</key>
        <string>/Users/kublai/.openclaw</string>
    </dict>

    <key>ProcessType</key>
    <string>Background</string>

    <key>LowPriorityIO</key>
    <true/>

    <key>ThrottleInterval</key>
    <integer>10</integer>
</dict>
</plist>
```

### launchd Plist: `com.kurultai.ogedei-heartbeat.plist`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.kurultai.ogedei-heartbeat</string>

    <key>ProgramArguments</key>
    <array>
        <string>/opt/homebrew/bin/python3</string>
        <string>/Users/kublai/.openclaw/agents/main/scripts/ogedei-heartbeat-check.py</string>
    </array>

    <key>WorkingDirectory</key>
    <string>/Users/kublai/.openclaw/agents/main</string>

    <key>StartInterval</key>
    <integer>60</integer>

    <key>RunAtLoad</key>
    <true/>

    <key>StandardOutPath</key>
    <string>/Users/kublai/.openclaw/agents/main/logs/ogedei-heartbeat.log</string>

    <key>StandardErrorPath</key>
    <string>/Users/kublai/.openclaw/agents/main/logs/ogedei-heartbeat.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
```

### Neo4j Queries Summary

```cypher
// === TASK LIFECYCLE ===

// 1. Claim task (existing — from neo4j_v2_core.py)
MATCH (t:Task {assigned_to: $agent, status: 'PENDING'})
WHERE (t.retry_after IS NULL OR t.retry_after <= datetime())
WITH t ORDER BY priority_rank ASC, t.created_at ASC
LIMIT 1
SET t.status = 'WORKING', t.claim_epoch = coalesce(t.claim_epoch, 0) + 1,
    t.claimed_by = $agent, t.started_at = datetime(),
    t.lease_expires_at = datetime() + duration({minutes: $lease_min})
RETURN t {.*} AS task

// 2. Critical-priority fast claim (NEW)
MATCH (t:Task {assigned_to: $agent, status: 'PENDING', priority: 'critical'})
WHERE (t.retry_after IS NULL OR t.retry_after <= datetime())
WITH t ORDER BY t.created_at ASC LIMIT 1
SET t.status = 'WORKING', t.claim_epoch = coalesce(t.claim_epoch, 0) + 1,
    t.claimed_by = $agent, t.started_at = datetime(),
    t.lease_expires_at = datetime() + duration({minutes: $lease_min})
RETURN t {.*} AS task

// 3. Complete task (existing — from neo4j_v2_core.py)
MATCH (t:Task {task_id: $task_id, claim_epoch: $epoch, status: 'WORKING'})
SET t.status = 'COMPLETED', t.completed_at = datetime(), ...
RETURN t.task_id AS task_id

// 4. Fail task (existing)
MATCH (t:Task {task_id: $task_id, claim_epoch: $epoch, status: 'WORKING'})
SET t.status = CASE WHEN $transient AND t.retry_count < t.max_retries
                    THEN 'PENDING' ELSE 'FAILED' END, ...

// 5. Orphan recovery (existing)
MATCH (t:Task {status: 'WORKING'})
WHERE t.lease_expires_at < datetime() - duration({minutes: $grace})
SET t.status = 'ORPHANED', t.updated_at = datetime()
RETURN t.task_id AS task_id, t.assigned_to AS agent

// 6. Promote orphans to PENDING (existing)
MATCH (t:Task {status: 'ORPHANED'})
WHERE t.updated_at < datetime() - duration({minutes: $hold})
SET t.status = 'PENDING', t.claim_epoch = coalesce(t.claim_epoch, 0) + 1,
    t.retry_count = coalesce(t.retry_count, 0) + 1
RETURN t.task_id AS task_id


// === AGENT STATE ===

// 7. Mark agent busy (NEW)
MERGE (a:Agent {name: $agent})
SET a.status = 'busy', a.current_task = $task_id, a.last_claimed = datetime()

// 8. Mark agent idle (NEW)
MERGE (a:Agent {name: $agent})
SET a.status = 'idle', a.current_task = null,
    a.tasks_completed = coalesce(a.tasks_completed, 0) + 1,
    a.last_completed = datetime()

// 9. Get all agent statuses (for dashboard/overflow decisions)
MATCH (a:Agent)
OPTIONAL MATCH (a)-[:EXECUTED]->(t:Task {status: 'WORKING'})
RETURN a.name AS agent, a.status AS status,
       collect(t.task_id) AS active_tasks, a.tasks_completed AS completed


// === QUEUE MONITORING ===

// 10. Queue depths per agent
MATCH (t:Task {status: 'PENDING'})
RETURN t.assigned_to AS agent, count(t) AS depth
ORDER BY depth DESC

// 11. Global queue summary
MATCH (t:Task)
WHERE t.status IN ['PENDING', 'WORKING', 'ORPHANED']
RETURN t.status AS status, t.assigned_to AS agent, count(t) AS count

// 12. Average queue wait time (last hour)
MATCH (t:Task)
WHERE t.started_at > datetime() - duration({hours: 1})
  AND t.created_at IS NOT NULL
RETURN avg(duration.between(t.created_at, t.started_at).seconds) AS avg_wait_s


// === OVERFLOW DETECTION ===

// 13. Find overloaded agents with idle alternates
MATCH (t:Task {status: 'PENDING'})
WITH t.assigned_to AS agent, count(t) AS depth
WHERE depth >= $threshold
WITH collect({agent: agent, depth: depth}) AS overloaded
MATCH (a:Agent)
WHERE a.status = 'idle' AND NOT a.name IN [x.agent IN overloaded]
RETURN overloaded, collect(a.name) AS idle_agents
```

### Cron Entries Summary

| Plist | Schedule | Script | Purpose |
|-------|----------|--------|---------|
| `com.kurultai.ogedei-dispatcher.plist` | KeepAlive (persistent) | `ogedei-dispatcher.py` | Main dispatcher |
| `com.kurultai.ogedei-heartbeat.plist` | Every 60s | `ogedei-heartbeat-check.py` | Watchdog for dispatcher |

**Retired (disabled after cutover):**

| Plist | New Status | Replaced By |
|-------|------------|-------------|
| `com.kurultai.v2-executor.plist` | `RunAtLoad: false` | ogedei-dispatcher |
| `com.kurultai.ogedei-watchdog.plist` | `RunAtLoad: false` | ogedei-dispatcher (health monitor) |

---

## Migration Path

### Rollback Plan

If the dispatcher causes issues:

```bash
# 1. Stop the dispatcher
launchctl unload ~/Library/LaunchAgents/com.kurultai.ogedei-dispatcher.plist

# 2. Re-enable v2-executor + watchdog
launchctl load ~/Library/LaunchAgents/com.kurultai.v2-executor.plist
launchctl load ~/Library/LaunchAgents/com.kurultai.ogedei-watchdog.plist

# 3. Verify
pgrep -f neo4j_v2_executor && echo "v2-executor running"
pgrep -f ogedei-watchdog && echo "watchdog running"
```

Total rollback time: under 30 seconds.

### Validation Criteria

Before declaring cutover complete:

- [ ] Dispatcher starts and writes heartbeat within 30s
- [ ] Heartbeat watchdog detects and reports OK
- [ ] Tasks are claimed and dispatched (check `ogedei-dispatcher.log`)
- [ ] At least 3 tasks complete successfully through the new pipeline
- [ ] Health checks run on schedule (check metrics file)
- [ ] Circuit breaker state is correct
- [ ] Queue depths match Neo4j state
- [ ] Filesystem fallback works (test: stop Neo4j, create a task file, verify dispatch)
- [ ] Graceful shutdown works (send SIGTERM, verify active tasks drain)
- [ ] Crash recovery works (kill -9 dispatcher, verify heartbeat watchdog restarts it)
- [ ] Dashboard metrics update correctly

---

## Open Questions

1. **Should Ogedei remain in the `DISPATCH_AGENTS` list?** If yes, it can receive tasks from Kublai and dispatch them to a subprocess of itself. If no, ops tasks need a different routing path. Recommendation: keep it in the list but add a self-dispatch optimization for simple ops tasks.

2. **Should the dispatcher expose an HTTP endpoint?** A simple `/status` endpoint would let the dashboard query dispatcher state directly instead of reading the metrics file. Low priority but nice to have.

3. **Should the critical fast-poll (5s) be configurable per-agent?** For example, Temujin tasks rarely need sub-15s latency, but a critical incident response task for Ogedei might.

4. **Memory budget:** The dispatcher will hold all health check state, circuit breaker state, and active task tracking in memory. Expected footprint: ~50-100MB. Is this acceptable for the host machine? (Current: v2-executor ~30MB + watchdog ~20MB + task-handler transient = ~50MB baseline.)
