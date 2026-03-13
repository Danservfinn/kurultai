---
name: neo4j-reconciliation
description: Neo4j/filesystem dual-state reconciliation patterns and scripts
type: reference
---

# Neo4j Reconciliation Reference

## Safe Operations Pattern (NEW - 2026-03-12)

When writing scripts that interact with Neo4j, use the safe wrapper functions to prevent task failures when Neo4j is unavailable:

### Option 1: Using `neo4j_utils.py` (for queries)

```python
from neo4j_utils import safe_neo4j_op, execute_query_cypher, check_neo4j_available

# Check health first
if not check_neo4j_available():
    logger.warning("Neo4j unavailable - using filesystem-only mode")

# Safe operation with fallback
tasks = safe_neo4j_op(
    lambda s: list(s.run("MATCH (t:Task) RETURN t")),
    fallback=[]  # Returns empty list if Neo4j down
)

# Convenience wrapper for simple queries
results = execute_query_cypher(
    "MATCH (t:Task {id: $id}) RETURN t",
    params={"id": "123"},
    fallback=None,
    single=True
)
```

### Option 2: Using `neo4j_task_tracker.py` (for TaskTracker)

```python
from neo4j_task_tracker import is_neo4j_available, safe_get_driver, require_neo4j

# Check before creating TaskTracker
if is_neo4j_available():
    tracker = TaskTracker()
    tracker.create_task(...)
else:
    logger.warning("Neo4j unavailable - skipping task creation")

# Get driver with graceful fallback
driver = safe_get_driver()
if driver:
    with driver.session() as session:
        session.run("CREATE (n:Task {id: $id})", id=123)
else:
    # Fallback to filesystem-only mode
    filesystem_create_task(123)

# For scripts that MUST have Neo4j
require_neo4j()  # Raises Neo4jConnectionError if unavailable
tracker = TaskTracker()  # Safe to proceed
```

**Benefits:**
- Prevents task failures from Neo4j connection issues
- Enables filesystem-only mode during Neo4j outages
- Consistent error handling across all scripts
- Pre-flight checks fail fast instead of timing out

**See also:**
- `scripts/neo4j_utils.py` — Query-level safe operations
- `scripts/neo4j_task_tracker.py` — Tracker-level safe operations

---

## Problem Space

The Kurultai maintains **dual state**: Neo4j (graph DB) + filesystem (task files). Desynchronization occurs in two distinct scenarios:

| Scenario | Root Cause | Symptom | Script to Use |
|----------|-----------|---------|---------------|
| **Orphaned filesystem tasks** | Neo4j unavailable during `task_intake.py` | Tasks exist in filesystem but not Neo4j; queue depth reporting wrong | `reconcile_neo4j_tasks.py` |
| **Stale Neo4j status** | Pre-2026-03-09 architecture (deprecated) | Neo4j shows `ready`/`running` but filesystem shows completion | `neo4j-state-sync.py` (deprecated) |

---

## Script 1: `reconcile_neo4j_tasks.py` (ACTIVE)

**Purpose:** Find filesystem tasks missing from Neo4j and create corresponding Task nodes.

**When to use:**
- After Neo4j outage/recconnect
- When queue depth reports don't match actual task counts
- As part of hourly reflection (automated in `hourly_reflection.sh`)

**Usage:**
```bash
# Dry run - show what would be synced
python3 reconcile_neo4j_tasks.py

# Fix - actually create missing Neo4j nodes
python3 reconcile_neo4j_tasks.py --fix

# Specific agent only
python3 reconcile_neo4j_tasks.py --agent mongke --fix
```

**Automation:**
```bash
# Runs automatically in hourly_reflection.sh
python3 "$SCRIPTS/reconcile_neo4j_tasks.py" --fix >> "$LOGS_DIR/reconciliation.log" 2>&1
```

**What it does:**
1. Scans `~/.openclaw/agents/*/tasks/*.md` for task files
2. Extracts metadata (agent, priority, task_id, created, source, skill_hint)
3. Queries Neo4j for matching Task nodes
4. Creates missing Task nodes with filesystem-derived state
5. Handles both YAML frontmatter and self-wake formats

**Key files:**
- Script: `scripts/reconcile_neo4j_tasks.py`
- Log: `logs/reconciliation.log`

---

## Script 2: `neo4j-state-sync.py` (DEPRECATED)

**Status:** ❌ DEPRECATED as of 2026-03-09 (Phase 2 of Kurultai Task System Overhaul)

**Why deprecated:** Architecture changed — Neo4j is now the **single source of truth** for task state. Filesystem is a materialized view/cache.

**When to use:**
- Emergency reconciliation only
- Manual repair operations
- One-time legacy task migration

**Replacement:** `neo4j-backfill-filesystem.py` to rebuild filesystem from Neo4j

**New architecture (post-2026-03-09):**
```
Neo4j (source of truth)
    ↓
Atomic CAS transitions
    ↓
Filesystem (cache/backward-compat)
```

---

## Architecture Timeline

| Date | Architecture | Source of Truth | Reconciliation Method |
|------|-------------|-----------------|----------------------|
| Pre-2026-03-09 | Filesystem-first, Neo4j updated after | Filesystem | `neo4j-state-sync.py` (filesystem → Neo4j) |
| 2026-03-09+ | Neo4j-first, filesystem as cache | Neo4j | `neo4j-backfill-filesystem.py` (Neo4j → filesystem) |
| Current | Neo4j-first with fallback | Neo4j | `reconcile_neo4j_tasks.py` (orphan recovery) |

---

## Troubleshooting

### Queue depth mismatch
```bash
# Check Neo4j task count
cypher-shell "MATCH (t:Task {status: 'ready'}) RETURN count(t);"

# Check filesystem task count
find ~/.openclaw/agents/*/tasks -name "*.md" ! -name ".*.done.md" | wc -l

# If filesystem > Neo4j, run reconciliation
python3 reconcile_neo4j_tasks.py --fix
```

### Stale `running`/`ready` tasks in Neo4j
- Check if `neo4j-state-sync.py` is needed (rare, legacy scenario)
- Usually indicates watcher/monitoring issue, not data sync issue

---

## Related Documentation
- `docs/state-management-reference.md` — Full state management guide
- `docs/heartbeat-troubleshooting.md` — Neo4j connection issues
- `scripts/neo4j_task_tracker.py` — Neo4j TaskTracker class
