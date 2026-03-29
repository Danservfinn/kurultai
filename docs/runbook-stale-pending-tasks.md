# Runbook: PENDING_NO_DISPATCH Anomaly

**Symptom:** Tick shows "pending=XX" but 0 executing, 0 active processes. Task-executor heartbeat shows "idle" with poll_count increasing but no active tasks.

**Diagnosis Steps:**

1. **Check if Redis queues or Neo4j?**
   ```bash
   redis-cli KEYS "queue:*"                    # If empty → using Neo4j
   redis-cli LLEN "queue:temujin"              # Should return 0 if Neo4j-based
   ```

2. **Check Neo4j task counts (case-sensitive!)**
   ```bash
   # Check uppercase PENDING
   echo 'MATCH (t:Task) WHERE t.status = "PENDING" RETURN count(t)' | cypher-shell ...

   # Check lowercase pending (stale tasks)
   echo 'MATCH (t:Task) WHERE t.status = "pending" RETURN count(t)' | cypher-shell ...

   # Check all status distribution
   echo 'MATCH (t:Task) RETURN t.status, count(t) ORDER BY count DESC' | cypher-shell ...
   ```

3. **Manual claim test**
   ```bash
   cd /Users/kublai/.openclaw/agents/main/scripts
   python3 -c "
   from neo4j_v2_core import TaskStore
   store = TaskStore()
   result = store.claim_task('temujin')
   print(f'Claimed: {result.get(\"task_id\") if result else \"None\"}')"
   ```

**Root Causes:**

### Cause 1: Stale lowercase "pending" tasks
Old proposal tasks from March 10-12 with status `"pending"` (lowercase) and `assigned_to = NULL` accumulate in Neo4j. The executor queries for uppercase `"PENDING"`, so these tasks are invisible to the executor but counted by the tick script.

**Fix:**
```bash
# Delete stale lowercase pending tasks
echo 'MATCH (t:Task) WHERE t.status = "pending" AND t.assigned_to IS NULL DETACH DELETE t RETURN count(t)' | cypher-shell -u neo4j -p "$(cat ~/.openclaw/agents/main/.neo4j_password)" --format plain
```

### Cause 2: Executor in bad state
The task-executor process may become stuck or unresponsive despite being alive.

**Fix:**
```bash
# Find executor PID
cat logs/task-executor.pid
# OR
ps aux | grep task_executor | grep -v grep

# Graceful termination
kill -TERM <pid>

# Force if needed
kill -9 <pid>

# Start new executor
cd /Users/kublai/.openclaw/agents/main
nohup python3 scripts/task_executor.py > logs/executor.out 2>&1 &

# Verify
sleep 5 && cat logs/task-executor-heartbeat.json
```

**Prevention:**

1. **Fix case-sensitivity at source** — Ensure all task creation uses uppercase status values
2. **Proposal task cleanup** — Add periodic cleanup of stale proposal tasks (>7 days old, lowercase status)
3. **Executor health check** — Add watchdog to restart executor if poll_count increases but active_tasks stays 0

**Related Files:**
- `scripts/task_executor.py` — Main executor loop
- `scripts/neo4j_v2_core.py` — claim_task method (line 65)
- `logs/task-executor-heartbeat.json` — Executor heartbeat
- `logs/ticks.jsonl` — System tick summaries

**Incident History:**
- 2026-03-23 16:18 — PENDING_NO_DISPATCH x6 ticks (CRITICAL)
- Root cause: 81 stale lowercase "pending" tasks + stuck executor
- Resolution: Deleted stale tasks + restarted executor
- MTTR: ~10 minutes
