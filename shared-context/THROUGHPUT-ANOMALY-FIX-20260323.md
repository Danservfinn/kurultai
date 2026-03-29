# Throughput Anomaly Fix — 2026-03-23

## Issue
**False Positive:** Sustained throughput anomaly alerts (PENDING_NO_DISPATCH) triggered by stale task markdown files being counted as "pending" tasks.

## Root Cause
The `watchdog-gather.sh` script was counting `.md` task files from the legacy file-based task system, which was deprecated in favor of Neo4j database tracking with the unified task executor.

### Evidence
- **Neo4j (truth):** 0 PENDING tasks
- **Filesystem count:** 31 "pending" tasks (stale `.md` files)
- **task-executor:** Working correctly (idle, no tasks to dispatch)

### Legacy Files Found
```
temujin:   8 files
mongke:    2 files
chagatai:  2 files
jochi:     7 files
ogedei:   26 files
tolui:     0 files
kublai:   12 files
```

Many of these were already in `_archive/` or `.archived-*` directories but lacked the filename suffix patterns (`.done.md`, `.completed.md`, etc.) that the script filtered on.

## Fix Applied
**File:** `scripts/watchdog-gather.sh` (lines 617-640)

**Before:** Counted `.md` files in each agent's `tasks/` directory, excluding certain filename patterns.

**After:** Queries Neo4j directly for tasks with `status="PENDING"` grouped by `agent_id`.

### New Query Logic
```cypher
MATCH (t:Task {status: "PENDING"})
RETURN t.agent_id as agent, count(t) as count
ORDER BY count DESC
```

## Verification
After fix:
- ✅ Pending count = 0 (matches Neo4j)
- ✅ No false positive alerts
- ✅ task-executor idle status correctly reported

## Related Documentation
- Task executor migration: `docs/ogedei-dispatcher-design.md`
- Task state management: `docs/state-management-reference.md`
- Task schema: `knowledge/neo4j-schema.md`

## Cleanup Recommendation
Consider archiving or deleting the stale `.md` task files to prevent confusion, though they are no longer used for monitoring.

_files:_
`/Users/kublai/.openclaw/agents/{agent}/tasks/_archive/*.md`
`/Users/kublai/.openclaw/agents/{agent}/tasks/.archived-*/*.md`
