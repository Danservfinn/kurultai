# Kublai Known Bugs History

## 2026-03-12: Infinite Task Bouncing via Circuit Breaker (FIXED)

**Problem**: Task `normal-1773279490-8d97ec8f` was redistributed 4 times across agents (chagatai → temujin → jochi → temujin → ogedei) despite MAX_REDISPATCH_COUNT=3 limit. The task accumulated redistribution comments but the limit was never enforced.

**Root Cause**: Three separate code paths handle task redistribution, but only `task-redistribute.py` tracks `redispatch_count`:

1. ✅ `task-redistribute.py` - tracks `redispatch_count`, enforces MAX_REDISPATCH_COUNT=3
2. ❌ `circuit_breaker.py` - did NOT track `redispatch_count`
3. ❌ `task_intake.py` - does NOT track `redispatch_count`

When circuit_breaker.py redistributed tasks due to agent failure quarantine, it didn't:
- Check the existing `redispatch_count`
- Increment or write the count to the task file

This created a loophole where tasks could bounce indefinitely via circuit breaker redistribution.

**Impact**:
- Tasks could be redistributed infinitely without hitting the MAX_REDISPATCH_COUNT limit
- Difficult/blocked tasks accumulated redistribution comments but never got manual review
- Queue imbalance persisted as "problem tasks" kept bouncing

**Fix**: Modified `circuit_breaker.py` to:
1. Add `MAX_REDISPATCH_COUNT = 3` constant (line 140)
2. Check `redispatch_count` before redistributing (skip if >= 3)
3. Increment and write `redispatch_count` when redistributing (same logic as task-redistribute.py)

```python
# Check redispatch_count to prevent infinite bouncing
redispatch_match = re.search(r'^redispatch_count:\s*(\d+)$', content, re.MULTILINE)
current_count = int(redispatch_match.group(1)) if redispatch_match else 0
if current_count >= self.MAX_REDISPATCH_COUNT:
    self.log(f"Skipping {task_path.name}: redispatch_count={current_count} >= {self.MAX_REDISPATCH_COUNT}", "WARN")
    continue
```

**Verification**:
```bash
# Syntax check
python3 -m py_compile scripts/circuit_breaker.py
# Result: ✓ Syntax OK

# Test redispatch_count regex logic
python3 -c "import re; ..."
# Result: All 4 test cases passed
```

**Remaining Work**: `task_intake.py` also needs redispatch_count tracking for complete coverage. That's a larger change since it would need to be integrated into the `route_by_text()` → load balancing flow.

**Files Modified**: `scripts/circuit_breaker.py` (added MAX_REDISPATCH_COUNT, check/increment logic)

---

## 2026-03-11: Tick JSON Corruption (FIXED)

**Problem**: `kublai-actions.py` reported "Failed to parse latest tick" repeatedly, preventing task auto-generation from system events.

**Root Cause**: In `watchdog-gather.sh`, the JSON format string for `ticks.jsonl` had a mismatch:
- Format string only had: `"services":{"neo4j":"%s","redis":"%s","recovery":{"neo4j":{"attempted":%s,"result":"%s"}}}`
- But printf was passing 4 additional variables: `$CLOUDFLARED_STATUS`, `${CLOUDFLARED_PID:-none}`, `${CLOUDFLARED_RECOVERY_ATTEMPTED:-0}`, `${CLOUDFLARED_RECOVERY_RESULT:-}`

This caused all subsequent JSON fields (credentials, tasks, subprocess, etc.) to receive wrong values, producing corrupted JSON like:
```json
{"ts":"0","epoch":degraded,"model":"escalate",...}
```

**Fix**: Updated format string to include cloudflared fields:
```bash
"services":{"neo4j":"%s","redis":"%s","cloudflared":"%s","cloudflared_pid":"%s","recovery":{"neo4j":{"attempted":%s,"result":"%s"},"cloudflared":{"attempted":%s,"result":"%s"}}}
```

**Impact**: 
- Restored tick → kublai-actions → task creation pipeline
- All 1804 tick entries now parse as valid JSON
- System can now auto-create tasks from infrastructure events

**Files Modified**: `scripts/watchdog-gather.sh` (line 803)

---

## 2026-03-11: Neo4j-Filesystem State Divergence (FIXED)

**Problem**: Queue depth reports showed 0 pending tasks in Neo4j, but filesystem had 2+ pending tasks. This broke load balancing decisions and caused incorrect routing.

**Root Cause**: In `task_intake.py` (line 3280-3289), when Neo4j throws an exception, the system silently falls back to "filesystem-only" mode:
```python
except Exception as e:
    print(f"ERROR: Neo4j unavailable, falling back to filesystem-only: {e}")
    # Filesystem-only fallback
    ...
```

This creates "orphaned" tasks that exist in the filesystem but NOT in Neo4j.

**Impact**:
- Queue depth reporting based on Neo4j showed 0 when filesystem had N tasks
- Load balancing made decisions on incorrect data
- 28 orphaned tasks found across all agents (mongke: 5, temujin: 6, ogedei: 11, jochi: 4, kublai: 3, chagatai: 1, tolui: 3)

**Fix**: Created `scripts/reconcile_neo4j_tasks.py` to sync orphaned tasks back to Neo4j:
```bash
# Dry-run to see what would be synced
python3 scripts/reconcile_neo4j_tasks.py --agent mongke --dry-run

# Actually sync the tasks
python3 scripts/reconcile_neo4j_tasks.py --fix
```

**Prevention Recommendations**:
1. Add reconciliation to hourly reflection cron
2. Consider hard-fail instead of silent fallback for task creation
3. Add health check flag for "filesystem-only mode" to trigger alerts

**Files Modified**: Created `scripts/reconcile_neo4j_tasks.py`, updated `memory/MEMORY.md`

---

## 2026-03-11: FAILED Task Stale Claims Blocking Dispatch (FIXED)

**Problem**: 15+ ticks with PENDING_NO_DISPATCH pattern. Tasks existed in queues but were never dispatched to handlers. temujin had 1 pending but 0 executing for extended periods.

**Root Cause**: `clear_stale_claims.py` only cleared session_keys from PENDING tasks, but FAILED tasks with stale session_keys also blocked new task dispatch. The script logic was:
```python
WHERE t.status = 'PENDING'  # Only looked at PENDING tasks
AND t.session_key IS NOT NULL
```

FAILED tasks retained session_keys forever, creating a claim lock that prevented task-watcher from dispatching new tasks.

**Impact**:
- 8 FAILED tasks with stale session_keys blocked dispatch
- temujin: 3 stale claims, ogedei: 3, mongke: 1, tolui: 1
- Zero completions despite queued tasks
- Pipeline throughput: 0.0 tasks/hr

**Fix**: Extended `clear_stale_claims.py` to also clear session_keys from FAILED tasks (regardless of age - they're done):
```python
# Added after PENDING task clearing
failed_stuck = session.run("""
    MATCH (t:Task)
    WHERE t.status = 'FAILED'
    AND t.session_key IS NOT NULL
    AND t.session_key <> ''
    RETURN t.task_id as task_id, t.agent as agent, t.session_key as session_key
""")
```

**Verification**:
```bash
# Before: 8 tasks with session_keys blocking dispatch
# After: 0 tasks blocking, 3 PENDING tasks ready for dispatch
```

**Files Modified**: `scripts/clear_stale_claims.py`

---

## 2026-03-11: Self-Wake Task PENDING_NO_DISPATCH Stall (FIXED)

**Problem**: agent-self-wake.py created self-wake tasks in filesystem only, but task-watcher's claim_task_atomic() queries Neo4j (the source of truth). Result: tasks sat in queues indefinitely with `SKIP: Task selfwake-XXX - not_found` in logs.

**Root Cause**: In `agent-self-wake.py`, the `create_wake_task()` function only wrote to filesystem:
```python
task_path.write_text(content)  # Line 261 - filesystem only
```

When task-watcher tried to claim via `claim_task_atomic()` -> `claim_task()` in neo4j_atomic_transitions.py, it queried Neo4j for the task, got "not_found", and skipped the task.

**Impact**:
- mongke, ogedei, temujin selfwake tasks never dispatched
- PENDING_NO_DISPATCH anomaly persisted across 24 ticks
- Agents stayed idle despite having pending self-wake tasks
- Throughput: 0.0 tasks/hr (tasks queued but not executing)

**Fix**: Modified `agent-self-wake.py` to create tasks in BOTH Neo4j and filesystem:
1. Added `_get_neo4j_driver()` function for lazy Neo4j driver loading
2. Added `create_neo4j_task()` function to create Neo4j Task node
3. Modified `create_wake_task()` to call `create_neo4j_task()` after filesystem write

```python
# After writing filesystem file, also create Neo4j node
task_id = f"selfwake-{agent}-{ts}"
if create_neo4j_task(task_id, agent, "Self-Wake -- Execute Blocked Items", content, "normal", "agent-self-wake"):
    log(f"Created wake task in Neo4j+filesystem: {agent}/{filename}")
else:
    log(f"Created wake task (filesystem-only): {agent}/{filename}", "WARN")
```

**Verification**:
```bash
# Test create_neo4j_task function
python3 -c "from scripts.agent_self_wake import create_neo4j_task; ..."
# Result: True, task created in Neo4j with PENDING status

# Check Neo4j for test task
echo 'MATCH (t:Task {task_id: "test-selfwake-123"}) RETURN t.status' | cypher-shell
# Result: PENDING
```

**Files Modified**: `scripts/agent-self-wake.py` (added 3 functions, modified create_wake_task)

**Related**: This is a specific case of the Neo4j-Filesystem State Divergence bug (see above). The generic reconciliation script handles existing orphans, but this fix prevents new selfwake tasks from becoming orphans.
python3 -c "from neo4j_task_tracker import get_driver; ..."
```

**Files Modified**: `scripts/clear_stale_claims.py` (added FAILED task clearing, new stat `failed_cleared`)
