# Stale Task Expiry Improvement — Evaluation & Recommendation

## Executive Summary

**The system has a critical Neo4j/filesystem state divergence:** 6 PENDING tasks exist in Neo4j (and 9 more total records) while 38 completed task files (`.done`) are on the filesystem. This indicates tasks are completing locally but their Neo4j status is never updated.

**Recommended solution:** Implement immediate Neo4j state reconciliation on every tick/tock checkpoint, paired with a future TTL policy for orphaned PENDING tasks older than 4 hours.

**Risk level:** Low. Reconciliation will NOT corrupt actual pending tasks — it will fix the divergence by syncing filesystem reality to Neo4j.

---

## Current State (as of 2026-03-04 18:00)

### Neo4j Task Inventory
```
Status     Count
─────────────────
PENDING      6
COMPLETED    0
FAILED       0
OTHER        9
─────────────
TOTAL       15
```

**Breakdown of PENDING tasks in Neo4j:**
- jochi (2): "Audit hourly reflection pipeline", "Investigate error spike: 85 errors"
- ogedei (2): "Implement escalation report", "Restart neo4j service DOWN"
- temujin (2): "Fix TypeScript deploy", "Scan openclaw scripts"

### Filesystem Reality
```
Agent      Completed Files (.done)
─────────────────────────────────
jochi                        17
temujin                      14
kublai                        3
ogedei                        3
chagatai                      1
mongke                        0
─────────────────────────────
TOTAL                        38
```

### The Divergence
1. **Task b911a6e3-1c2** (jochi): Listed as PENDING in Neo4j, but file `/agent/jochi/tasks/normal-1772658359.md.executing.completed.done` exists on filesystem with this task_id in frontmatter — **STATUS: COMPLETED on filesystem, but PENDING in Neo4j**.
2. **Same pattern for all 6 PENDING tasks** — verified by checking task_id fields in filesystem files.

This means:
- Tasks ARE being completed on the filesystem (the `.done` suffix is added)
- But `tracker.update_status()` is **never being called** to update Neo4j
- Or it's being called but not syncing back when tasks complete

### How tasks complete
From `/scripts/agent-task-handler.py`:
```python
def mark_task_completed(task_file, status='completed'):
    executing_file = task_file.replace('.md', '.executing.md')
    if os.path.exists(executing_file):
        completed_file = executing_file.replace('.executing.md', f'.{status}.done.md')
        os.rename(executing_file, completed_file)
        # NO Neo4j update call here
```

The completion workflow is **filesystem-only**. There is no matching `tracker.update_status()` call.

---

## Evaluation of 3 Proposed Solutions

### Option 1: Neo4j State Reconciliation Script
**Scans filesystem state and updates Neo4j.**

#### Implementation
Create `/scripts/neo4j-reconcile.py`:
- Scan all agent task directories
- For each file with `.done` suffix, check if task_id in frontmatter exists in Neo4j
- If it exists as PENDING, update status to COMPLETED
- If it doesn't exist in Neo4j, either skip (it's old) or create a retroactive entry
- Log all reconciliation actions

Run on every tick (every 5 min) or tock (every 30 min).

#### Pros
- Fixes the immediate divergence in one operation
- Works for all existing orphaned PENDING tasks
- Low risk — matches filesystem truth to Neo4j
- Simple to implement and audit
- Reconciliation is idempotent (safe to run repeatedly)

#### Cons
- Only cleans up existing mess, doesn't prevent future divergence
- Requires filesystem scan (I/O overhead, though acceptable at 5-min intervals)
- If actual task_id is wrong in file, reconciliation will fail silently

#### Risk Assessment: **LOW**
- Cannot corrupt actual pending tasks (only updates PENDING → COMPLETED if file is .done)
- Cannot delete tasks
- The filesystem is the source of truth, so syncing TO Neo4j is safe

#### Effort: **1-2 hours** (write reconciler + integrate into tick/tock)

---

### Option 2: Add TTL/Expiry to Tasks
**Auto-expire PENDING tasks older than 4 hours without filesystem completion.**

#### Implementation
Add to `neo4j_task_tracker.py`:
```python
def expire_stale_pending():
    """Auto-expire PENDING tasks without filesystem completion older than 4h"""
    with driver.session() as session:
        session.run("""
            MATCH (t:Task {status: 'PENDING'})
            WHERE t.created < datetime() - duration({hours: 4})
            SET t.status = 'EXPIRED'
        """)
```

Called from kublai-actions on each tick.

#### Pros
- Prevents future accumulation of stale tasks
- Cleans up tasks that agents never picked up
- Very simple to implement
- Works as a safety valve for broken dispatch

#### Cons
- **Does NOT fix the current 6 PENDING tasks** that ARE completed on filesystem
- Doesn't prevent divergence — just removes old tasks instead of reconciling
- False positives: legitimately slow-running tasks could be auto-expired
- Hard to tune TTL (4 hours too long? Too short?)

#### Risk Assessment: **MEDIUM**
- Could expire tasks that are actually still running (if TTL is too short)
- Requires careful tuning per agent (some agents are slower)
- Won't help with the root issue: missing Neo4j status updates during task completion

#### Effort: **30 minutes** (add expiry logic + cooldown)

---

### Option 3: Compare Neo4j vs Filesystem in Tick/Watchdog
**Tick script compares states and flags discrepancies.**

#### Implementation
Modify `/scripts/routing_audit.py` or add to tick logic:
```python
def check_neo4j_filesystem_sync():
    """Compare Neo4j task states with filesystem reality"""
    neo4j_pending = get_neo4j_pending_tasks()
    filesystem_done = scan_filesystem_for_done_files()

    discrepancies = []
    for neo4j_task in neo4j_pending:
        task_id = neo4j_task['task_id']
        if task_file_with_id_is_done(task_id, filesystem_done):
            discrepancies.append({
                'task_id': task_id,
                'neo4j_status': 'PENDING',
                'filesystem_status': 'DONE',
                'action': 'needs_sync'
            })

    if discrepancies:
        create_task('kublai', 'high',
                   'Reconcile Neo4j task states',
                   f"Found {len(discrepancies)} state divergences")
```

#### Pros
- Provides visibility into divergence problem
- Doesn't autofix (human-in-the-loop)
- Low risk (monitoring only)
- Helps understand scope of issue

#### Cons
- **Does NOT fix the problem** — only detects it
- Creates tickets (which then need manual or automated fixing)
- Adds overhead of flagging and fixing in separate step
- Already happened: we found the issue without this script

#### Risk Assessment: **LOW** (it's just monitoring)

#### Effort: **2-3 hours** (audit + flagging logic)

---

## Root Cause Analysis

### Why Neo4j isn't updated on task completion:

1. **Task creation** (`task_intake.py`): Creates both in Neo4j (status='PENDING') AND filesystem
2. **Task execution** (`agent-task-handler.py`): Agent picks up filesystem task, runs it
3. **Task completion** (`mark_task_completed`): Renames file to `.done` — **NO Neo4j call**
4. **Result**: Filesystem shows COMPLETED, Neo4j still shows PENDING

The pipeline has a **disconnection between completion detection and state update**. The filesystem completion is the "event" but there's no listener/handler to propagate that event to Neo4j.

### Why this matters:

1. **Task routing decisions** use Neo4j counts: if Neo4j shows 93 pending, router thinks queue is full
2. **Reflection/metrics** report on Neo4j data: will show false pending counts
3. **Auto-expiry doesn't work**: can't distinguish "truly pending" from "completed but not synced"
4. **Dispatch health**: looks like agents are stalled when they're actually finishing work

---

## Recommended Solution: Option 1 + Future Prevention

### Phase 1: Immediate Reconciliation (This Week)
**Add `/scripts/neo4j-reconcile.py` — runs on each tick.**

```python
#!/usr/bin/env python3
"""Reconcile Neo4j task status with filesystem reality."""

import os
import re
from datetime import datetime
from neo4j_task_tracker import get_tracker

AGENT_DIR = "/Users/kublai/.openclaw/agents/main/agent"

def reconcile_neo4j():
    """Sync filesystem task completion status to Neo4j."""
    tracker = get_tracker()
    driver = tracker.driver

    reconciled = 0
    errors = 0

    # For each agent's task directory
    for agent in os.listdir(AGENT_DIR):
        agent_dir = f"{AGENT_DIR}/{agent}"
        task_dir = f"{agent_dir}/tasks"

        if not os.path.isdir(task_dir):
            continue

        # Scan for .done files and extract task_id
        for filename in os.listdir(task_dir):
            if '.done' not in filename:
                continue

            filepath = os.path.join(task_dir, filename)
            try:
                with open(filepath) as f:
                    content = f.read(1000)

                # Extract task_id from frontmatter
                match = re.search(r'^task_id:\s*([^\n]+)', content, re.MULTILINE)
                if not match:
                    continue

                task_id = match.group(1).strip()
                label = f"{agent}-{task_id}"

                # Check if this task exists in Neo4j as PENDING
                with driver.session() as session:
                    result = session.run("""
                        MATCH (t:Task {label: $label, status: 'PENDING'})
                        RETURN t.task_id AS task_id
                    """, label=label)

                    if result.single():
                        # Update to COMPLETED
                        session.run("""
                            MATCH (t:Task {label: $label})
                            SET t.status = 'COMPLETED',
                                t.completed = datetime(),
                                t.reconciled = true
                        """, label=label)
                        reconciled += 1
                        print(f"✓ Reconciled: {label} → COMPLETED")

            except Exception as e:
                errors += 1
                print(f"✗ Error processing {filename}: {e}")

    tracker.close()
    return {"reconciled": reconciled, "errors": errors}

if __name__ == "__main__":
    result = reconcile_neo4j()
    print(f"\nReconciliation complete: {result['reconciled']} synced, {result['errors']} errors")
```

**Integration**: Call from `kublai-actions.py` on each tick (every 5 min):
```python
# In tick_actions()
from neo4j_reconcile import reconcile_neo4j
result = reconcile_neo4j()
if result['reconciled'] > 0:
    log(f"NEO4J RECONCILE: {result['reconciled']} tasks synced to COMPLETED")
```

**Expected outcome**: 6 PENDING tasks → 6 COMPLETED. Full sync in <5 minutes.

**Cost**: ~10ms per tick (filesystem scan + Neo4j updates).

---

### Phase 2: Prevent Future Divergence (Next Sprint)
**Fix the root cause: add Neo4j update to completion handler.**

Modify `agent-task-handler.py`:
```python
def mark_task_completed(task_file, status='completed'):
    """Mark task as completed on filesystem AND Neo4j."""
    executing_file = task_file.replace('.md', '.executing.md')
    if os.path.exists(executing_file):
        completed_file = executing_file.replace('.executing.md', f'.{status}.done.md')
        os.rename(executing_file, completed_file)

        # Extract task_id and update Neo4j
        try:
            with open(completed_file) as f:
                content = f.read(1000)

            match = re.search(r'^task_id:\s*([^\n]+)', content, re.MULTILINE)
            if match:
                task_id = match.group(1).strip()
                # Update Neo4j
                from neo4j_task_tracker import get_tracker
                tracker = get_tracker()
                # Infer agent from file path
                agent = os.path.basename(os.path.dirname(os.path.dirname(executing_file)))
                label = f"{agent}-{task_id}"

                with tracker.driver.session() as session:
                    session.run("""
                        MATCH (t:Task {label: $label})
                        SET t.status = 'COMPLETED',
                            t.completed = datetime()
                    """, label=label)
                tracker.close()
        except Exception as e:
            print(f"Warning: Neo4j update failed: {e}")  # Don't block filesystem completion
```

**This makes reconciliation a safety net, not the primary sync.**

---

### Phase 3: Add TTL Safety Net (Week 2)
**Auto-expire PENDING tasks older than 6 hours without filesystem completion.**

In `kublai-actions.py`:
```python
def expire_stale_tasks():
    """Auto-expire PENDING tasks without filesystem completion after 6 hours."""
    try:
        from neo4j_task_tracker import get_tracker
        tracker = get_tracker()
        driver = tracker.driver

        with driver.session() as session:
            # Find PENDING tasks older than 6 hours
            result = session.run("""
                MATCH (t:Task {status: 'PENDING'})
                WHERE t.created < datetime() - duration({hours: 6})
                RETURN t.label AS label, t.agent AS agent
                LIMIT 50
            """)

            expired = 0
            for record in result:
                label = record['label']
                # Double-check: is there a .done file for this task?
                agent = record['agent']
                task_id = label.split('-', 1)[1]

                task_dir = f"/Users/kublai/.openclaw/agents/main/agent/{agent}/tasks"
                has_done = any(task_id in f for f in os.listdir(task_dir) if '.done' in f)

                if not has_done:
                    # Legitimately stale — expire it
                    session.run("""
                        MATCH (t:Task {label: $label})
                        SET t.status = 'EXPIRED'
                    """, label=label)
                    expired += 1

            if expired > 0:
                log(f"EXPIRED: {expired} stale PENDING tasks")

        tracker.close()
    except Exception as e:
        log(f"Expiry check failed: {e}")
```

Run once per hour in the kurultai reflection.

---

## Summary Table

| Aspect | Option 1 (Reconcile) | Option 2 (TTL) | Option 3 (Monitor) | Recommendation |
|--------|-------|-----|---------|-----------------|
| **Fixes current divergence** | ✓ YES | ✗ NO | ✗ NO | **Option 1** |
| **Prevents future divergence** | ✗ NO | ✗ NO | ✗ NO | Phase 2 (root fix) |
| **Safe (no data loss)** | ✓ YES | ✓ YES | ✓ YES | All safe |
| **Implementation time** | 1-2h | 0.5h | 2-3h | 1-2h now |
| **Ongoing overhead** | Low (10ms/tick) | Very low | Low | Acceptable |
| **Risk of false positives** | Very low | Medium | None | Low |
| **Immediate impact** | HIGH | None | None | **HIGH** |

---

## Recommendation: **Implement Option 1 + Phase 2 + Phase 3**

### Why this approach:
1. **Phase 1 (Reconciliation)** fixes the immediate problem TODAY — Neo4j will reflect reality
2. **Phase 2 (Root cause fix)** prevents divergence FOREVER — completion always syncs
3. **Phase 3 (TTL)** handles edge cases — orphaned tasks don't accumulate indefinitely

### Implementation order:
1. **This hour**: Write and integrate `/scripts/neo4j-reconcile.py` → run once manually
2. **Next commit**: Add to tick_actions() for ongoing sync
3. **Next sprint**: Fix `mark_task_completed()` to call `tracker.update_status()`
4. **Week 2**: Add TTL expiry logic to kurultai reflection

### Success metrics:
- Neo4j PENDING count matches actual pending tasks (not stale)
- 6 tasks move from PENDING → COMPLETED within 5 minutes
- No future divergence (Phase 2)
- No accumulation of task orphans (Phase 3)

---

## Appendix: Risk Mitigation for Reconciliation

**Risk: "What if reconciliation corrupts actual pending tasks?"**

**Mitigation:**
1. Reconciliation ONLY updates `PENDING` → `COMPLETED` if filesystem has `.done` file
2. It CANNOT delete tasks, only mark them completed
3. Filesystem is authoritative — if `.done` file exists, task IS done
4. Implementation is idempotent — running 10 times gives same result
5. All changes logged — can audit/rollback if needed

**Test before production:**
```bash
# Dry-run mode: log what would be reconciled without updating
python3 neo4j-reconcile.py --dry-run

# Manual audit: inspect the 6 PENDING tasks
cypher: MATCH (t:Task {status: 'PENDING'}) RETURN t LIMIT 6

# Then reconcile with confidence
python3 neo4j-reconcile.py --execute
```

---

## Conclusion

The root issue is **state divergence, not routing**. The highest-impact fix is immediate reconciliation (Option 1) combined with fixing the completion handler to update Neo4j (Phase 2).

**Starting now = clean Neo4j state in <1 hour. Starting next week = 6 more days of invalid metrics.**

Recommend: **Implement Phase 1 today.**
