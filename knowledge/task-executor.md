# Unified Task Executor

**Script**: `agents/main/scripts/task_executor.py`
**Launchd**: `com.kurultai.task-executor`
**PID lock**: `~/.openclaw/agents/main/logs/task-executor.pid`
**Last Updated**: 2026-03-23 (added post-completion hook)

---

## Overview

The unified task executor replaces two previous scripts:

| Replaced Script | Lines | Responsibilities Absorbed |
|----------------|-------|--------------------------|
| `task-watcher.py` | 3,724 | Session bloat detection, stall detection, poll/claim/run loop, ledger writes |
| `agent-task-handler.py` | 4,349 | Model drift detection, `verify_result` gate, `build_agent_env`, completion/failure persistence |

Both original scripts are archived in `agents/main/scripts/_archived/`.

---

## Architecture (6 Components)

### 1. Data Types

Frozen dataclasses used throughout the executor:

- **`RunResult`** -- immutable record of a single agent subprocess execution: `success`, `content`, `return_code`, `duration_s`, `model`, `stall_detected`
- **`SessionState`** -- immutable record of pre-execution session cleanup: `clean`, `bloat_reset`, `drift_archived`, `reason`

### 2. SessionManager

Unified pre-execution session hygiene. Replaces both `_check_and_reset_bloated_session()` and `_validate_session_model()` with a single atomic pass.

**`prepare(agent) -> SessionState`**:
1. Checks `sessions.json` for size bloat (threshold: 100 KB). If bloated, backs up and resets to `{}`.
2. Checks the latest `.jsonl` file for model drift (known drift providers: glm-5, kimi, qwen, bailian, dashscope, minimax, zai-coding). If drifted, renames with `.drift-<timestamp>` suffix.
3. Returns a `SessionState` describing what was found and cleaned.

### 3. TaskRunner

asyncio subprocess runner with PID-scoped stall detection.

**`run(agent, prompt, env, timeout, model) -> RunResult`**:
- Executes `claude-agent --workdir <dir> [--model <model>] -- <prompt>`
- Streams stdout line-by-line
- Stall detection: after `STALL_MIN_ELAPSED` (900s), if `STALL_SILENCE` (900s) of stdout silence, confirms via `lsof` that the PID has no recently-modified `.jsonl` files before terminating
- Hard timeout: kills process after `timeout` seconds
- Child processes run in a new session group (`start_new_session=True`) for signal isolation

### 4. verify_result() -- The Completion Gate

The sole path to COMPLETED status. Checks in order:

1. Process exit code must be 0
2. Output must be non-empty
3. No stall flag from TaskRunner
4. For short output (<500 chars): absence of error patterns masquerading as success (auth_failure, rate_limited, network_error, killed)

Returns `(passed, reason)` where reason is `"verified"` on success or a short category string on failure.

### 5. build_agent_env()

Builds a clean subprocess environment:

1. Copy `os.environ`
2. Remove `CLAUDECODE` (allows nested Claude Code sessions)
3. Prepend known tool paths to `PATH`
4. Strip ALL `ANTHROPIC_*` vars (prevents key inheritance from parent)
5. Load vault credentials from `~/.openclaw/credentials/provider.env`
6. Load agent-specific env overrides from `.claude/settings.json`

### 6. Executor (Main Loop)

asyncio event loop: `poll -> claim -> run -> verify -> persist`.

**Startup sequence:**
1. Recover orphaned tasks from previous crashes (immediate, not lease-based)
2. Replay buffered WAL entries from `neo4j-wal.db`
3. Emit `EXECUTOR_STARTED` event
4. Start background lease renewal task

**Poll cycle (every 30s):**
1. Process spawn queue (`~/.openclaw/spawn-queue/`)
2. For each agent in `DISPATCH_AGENTS`:
   - Check circuit breaker status
   - Respect concurrency semaphore (cap: 6)
   - Attempt to claim a PENDING task
   - If claimed, dispatch `_execute_inner()` as an asyncio task

**Execution pipeline (`_execute_inner`) — Two-Phase:**
1. Session cleanup via `SessionManager.prepare()`
2. Sanitize task body via `PromptSanitizer`
3. **Phase 1 — Prompt optimization** (new): If task complexity >= 15 and priority != critical:
   - Select relevant KB docs via `kb_selector.select_kb_docs()`
   - Build a meta-prompt instructing Claude Code to invoke `/horde-prompt`
   - Spawn a short claude-agent session (haiku, 90s timeout)
   - Extract optimized prompt from `<<<OPTIMIZED_PROMPT>>>` delimiters
   - Fallback: if Phase 1 fails, use simple `_build_prompt()` concatenation
   - Events: `PROMPT_OPTIMIZED` on success, `PROMPT_FALLBACK` on failure
4. Build execution environment via `build_agent_env()`
5. **Phase 2 — Task execution**: Run subprocess via `TaskRunner.run()` with the optimized prompt
6. Verify result via `verify_result()` -- **THE GATE**
6. On rate-limit/auth failure: model fallback to `claude-sonnet-4-6` (except tolui)
7. Persist terminal state to Neo4j (COMPLETED or FAILED)
8. On Neo4j failure: buffer to WAL for later replay

---

## Module Constants

| Constant | Value | Description |
|----------|-------|-------------|
| `STALL_SILENCE` | 900s | Seconds of stdout silence before stall check |
| `STALL_MIN_ELAPSED` | 900s | Minimum elapsed time before stall checks begin |
| `POLL_INTERVAL` | 30s | Seconds between poll cycles |
| `CONCURRENCY` | 1 | Maximum concurrent tasks (reduced from 3 for OOM prevention on 16GB) |

---

## Dependencies

| Module | Purpose |
|--------|---------|
| `kurultai_paths` | Path constants (`AGENTS_DIR`, `DISPATCH_AGENTS`, `CLAUDE_AGENT`, etc.) |
| `neo4j_v2_core` | `TaskStore` -- claim, complete, fail, recover operations |
| `neo4j_v2_wal` | `WAL` -- SQLite write-ahead log for Neo4j outages |
| `neo4j_v2_failure` | `classify_failure()` -- error classification (transient vs permanent) |
| `neo4j_v2_events` | `emit_event()`, `emit_session_reset()` -- Event node creation |
| `circuit_breaker` | `AgentCircuitBreaker` -- per-agent availability gate |
| `prompt_sanitizer` | `PromptSanitizer` -- threat detection in task prompts |

---

## Observability

### File-Based

- **Heartbeat**: `~/.openclaw/agents/main/logs/task-executor-heartbeat.json` (updated every poll cycle)
  ```json
  {"timestamp":"...","pid":12345,"executor_id":"exec-a1b2c3d4","poll_count":42,"active_tasks":1,"status":"active"}
  ```
- **Ledger**: `~/.openclaw/tasks/task-ledger.jsonl` (TASK_COMPLETED / TASK_FAILED events)
- **PID file**: `~/.openclaw/agents/main/logs/task-executor.pid` (single-instance lock)

### Graph-Based (Neo4j)

- **Event nodes**: Append-only lifecycle events (see [neo4j-schema.md](neo4j-schema.md#event-task-lifecycle))
- **AgentMetrics nodes**: Incrementally updated per-agent performance counters
- **WAL**: `~/.openclaw/neo4j-wal.db` (SQLite buffer for Neo4j outages, replayed on reconnect)

---

## Key Design Decisions

1. **Concurrency = 1**: Reduced from 3 to prevent OOM kills on the 16GB host machine. The semaphore cap is a module constant, easily adjustable.

2. **PID-scoped stall detection**: Instead of relying solely on stdout silence, the executor uses `lsof` to check if the child PID has any recently-modified `.jsonl` files. This eliminates false-positive stall kills when Claude Code is working but producing output to files rather than stdout.

3. **WAL for Neo4j outages**: When Neo4j is unavailable (e.g., during restarts), completed/failed task state changes are buffered to a local SQLite database and replayed when the connection is restored. This prevents task state loss during database maintenance.

4. **Single `verify_result()` gate**: All completion decisions flow through one function. This eliminates the class of bugs where different code paths had inconsistent completion logic.

5. **Event-sourced observability**: Every lifecycle transition emits an Event node to Neo4j, providing a complete audit trail. AgentMetrics nodes are updated incrementally for dashboard queries without expensive aggregation.

6. **Fire-and-forget post-completion hook**: After `store.complete()` succeeds, a background asyncio task is spawned (non-blocking) to detect and queue follow-up tasks declared in the agent's output.

---

## Notification on Completion (2026-03-29 rebuild)

**Module**: `signal_send.py` (direct call, no subprocess)

When a task completes, both dispatchers send Signal notifications directly:

### task_executor.py path (`_send_notification`)
1. Guard: skip if `origin_type` is not `human` (safe fallback: warn + send if None)
2. Guard: skip if `notify_target` doesn't start with `+`
3. Build message: `[DONE] agent: title\n\nresult_preview\n\nportal_link`
4. Call `signal_send.send()` via `run_in_executor` (non-blocking)
5. Pass `quote_timestamp` + `quote_author` from task dict for Signal reply threading
6. On failure: enqueue to `NotificationQueue` as fallback

### ogedei_dispatch.py path (`_queue_notification` → `_send_notification_sync`)
1. Same origin_type + phone guards
2. Enqueue to SQLite NotificationQueue (WAL mode, persistent)
3. Notification loop peeks every 15s, respects exponential backoff
4. `_send_notification_sync`: queries Neo4j for `origin_message_id`, calls `signal_send.send()` with threading params
5. On max attempts (5): dead-letter alert to operator

### Failed task notifications
`_handle_failure` also calls `_queue_notification` with `status="failed"` to notify humans when their tasks fail.

### Key change from previous architecture
The old `/task-complete` skill subprocess (breadcrumb → claude-agent → signal_send) had 3 fatal bugs and has been completely removed. All notification is now direct `signal_send.send()` calls.

---

## Post-Completion Hook

**Module**: `agents/main/scripts/post_completion_hook.py`
**Entry point**: `run_post_completion_hook(task_id, task_title, result_content)`

When a task completes successfully, the executor fires `run_post_completion_hook()` as a fire-and-forget `asyncio.create_task()`. The hook:

1. Scans `result_content` for fenced ` ```yaml ` blocks containing a `follow_ups:` key
2. Validates each follow-up declaration (required: `title`, `agent`; optional: `priority`, `skill_hint`, `context`)
3. For each valid declaration, spawns `claude-agent --print --no-session-persistence` to invoke `/horde-prompt` and generate a full task body (120s timeout; falls back to minimal body on failure)
4. Creates the new task in Neo4j via `task_intake.create_task()` with `source="post-completion-hook"` and `parent_id` pointing to the originating task

### Follow-up Declaration Format (agent-facing)

Agents add a `follow_ups:` YAML block anywhere in their task output:

```yaml
follow_ups:
  - title: "One-line imperative title"   # required
    agent: temujin                        # required; temujin|mongke|chagatai|jochi|ogedei
    priority: normal                      # optional; critical|high|normal|low (default: normal)
    skill_hint: /horde-implement          # optional
    context: |                            # optional; 1-3 sentences explaining WHY
      Context for the target agent.
```

**Constraints**: max 5 follow-ups per task; invalid agent names or missing title cause that item to be skipped (never fails the parent task). Full format documented in `agents/_shared/FOLLOWUP_FORMAT.md`.

### Error Handling

- The hook **never raises** — all errors are logged and silently dropped
- `_POST_HOOK_AVAILABLE` flag: if the module fails to import at executor startup, the flag is `False` and the hook call is skipped entirely
- `task_intake.create_task` import is lazy (inside a sync executor closure) to avoid circular imports and Neo4j connectivity requirements at module load time
