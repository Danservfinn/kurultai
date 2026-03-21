---
plan_manifest:
  version: "1.2"
  created_by: "horde-plan"
  plan_name: "Task Dependency Infrastructure for Daily Reflection Pipeline"
  total_phases: 6
  total_tasks: 18
  phases:
    - id: "1"
      name: "Schema & Indexes"
      task_count: 2
      parallelizable: false
      gate_depth: "STANDARD"
    - id: "2"
      name: "Core Dependency Primitives"
      task_count: 4
      parallelizable: false
      gate_depth: "DEEP"
    - id: "3"
      name: "Pipeline Launcher (Daily)"
      task_count: 3
      parallelizable: false
      gate_depth: "STANDARD"
    - id: "3.5"
      name: "Human Approval Gate in Voting"
      task_count: 3
      parallelizable: false
      gate_depth: "STANDARD"
    - id: "4"
      name: "Self-Test & Verification"
      task_count: 4
      parallelizable: true
      gate_depth: "STANDARD"
    - id: "5"
      name: "Shadow Mode Integration"
      task_count: 2
      parallelizable: false
      gate_depth: "LIGHT"
  task_transfer:
    mode: "transfer"
    task_ids: []
---

# Task Dependency Infrastructure for Daily Reflection Pipeline

> **Plan Status:** Draft v1.2
> **Created:** 2026-03-20
> **Estimated Tasks:** 18
> **Estimated Phases:** 6

## Overview

**Goal:** Add forward dependency resolution to the Kurultai task system so the reflection pipeline can be expressed as a task graph instead of bash orchestration. Additionally, shift reflections from hourly to **daily** and add a **human approval gate** to the voting system (6/6 agent consensus → Signal DM to owner for final sign-off).

**Architecture:** New `DEPENDS_ON` relationship + `BLOCKED` state in Neo4j. Modified `claim_task()` skips tasks with unresolved dependencies. `complete_task()` triggers `unblock_dependents()` to promote BLOCKED → PENDING. A new `launch_daily_reflection_pipeline.py` creates all pipeline tasks with dependency edges in one transaction. The voting system gains a `PENDING_HUMAN_APPROVAL` status and Signal notification to +19194133445.

**Scope:** This plan covers Phases A-B of the migration path (build infrastructure + pipeline launcher + human approval gate). Phase C (wiring one real pipeline phase) and Phase D (full migration, retiring `hourly_reflection.sh`) are deferred to a follow-up plan after shadow-mode validation.

## Key Design Changes from Current System

1. **Daily instead of hourly**: Pipeline runs once per day instead of every hour. `meta_reflection.py` queries last 24h instead of last 1h. `generate_hourly_report.py` becomes a daily report.
2. **Human approval gate**: After 6/6 agent consensus, proposals enter `PENDING_HUMAN_APPROVAL` state. A Signal DM is sent to +19194133445 with a summary. The owner replies "approve" or "reject" to finalize. Tasks are only created after human sign-off.

## Files Modified

| File | Change | Lines Added |
|------|--------|-------------|
| `neo4j_v2_core.py` | `BLOCKED` state, modified `claim_task`, `unblock_dependents`, `create_task` extension | ~80 |
| `neo4j_v2_core.py` (self-test) | Dependency + fan-in self-tests | ~80 |
| `neo4j_v2_schema.py` | 2 new indexes (pipeline_id, dependency status) | ~15 |
| `launch_daily_reflection_pipeline.py` | **New file** — creates daily reflection pipeline task graph | ~200 |
| `kurultai_voting.py` | `PENDING_HUMAN_APPROVAL` status, Signal DM notification | ~55 |
| `kurultai_voting_approval.py` | **New file** — human approve/reject handler | ~50 |
| `signal_message_handler.py` | Approval command routing for owner phone | ~15 |

**Total:** ~495 new lines across 5 files (2 new, 3 modified).

---

## Phase 1: Schema & Indexes
**Duration**: 15-20 minutes
**Dependencies**: None
**Parallelizable**: No

### Task 1.1: Add Pipeline and Dependency Indexes to Schema
**Dependencies**: None

**File:** `neo4j_v2_schema.py`
**Location:** Append to `V2_INDEXES` list (after the conversational health indexes at line 235)

```python
    # --- Task Dependencies (reflection pipeline) ---
    {
        "name": "v2_task_pipeline_id",
        "cypher": "CREATE INDEX v2_task_pipeline_id IF NOT EXISTS "
                  "FOR (t:Task) ON (t.pipeline_id)",
        "desc": "Pipeline run grouping for dependency-based orchestration",
    },
    {
        "name": "v2_task_status_pipeline",
        "cypher": "CREATE INDEX v2_task_status_pipeline IF NOT EXISTS "
                  "FOR (t:Task) ON (t.status, t.pipeline_id)",
        "desc": "Pipeline tasks by status for monitoring",
    },
```

Both use `IF NOT EXISTS` — idempotent.

```bash
python3 neo4j_v2_schema.py
python3 neo4j_v2_schema.py --verify
# Expected: 0 missing
```

**Files:**
- Modify: `neo4j_v2_schema.py` (~15 lines)

**Acceptance Criteria:**
- [ ] Both indexes created and verified
- [ ] `--verify` reports 0 missing
- [ ] Existing schema self-test still passes (`--test`)

### Task 1.2: Verify DEPENDS_ON Relationship Can Be Created
**Dependencies**: Task 1.1

Quick smoke test that Neo4j accepts DEPENDS_ON relationship creation (no schema needed for relationships in Neo4j, but confirm driver handles it):

```bash
python3 -c "
import sys; sys.path.insert(0, '.')
from neo4j_v2_core import TaskStore
store = TaskStore()
with store.driver.session() as s:
    # Create two test tasks
    s.run('''
        CREATE (a:Task {task_id: 'dep-test-parent', status: 'PENDING', title: 'test', assigned_to: 'test',
                        priority: 'low', domain: 'test', claim_epoch: 0, retry_count: 0,
                        max_retries: 1, depth: 0, timeout_s: 60, created_at: datetime(), updated_at: datetime()})
        CREATE (b:Task {task_id: 'dep-test-child', status: 'BLOCKED', title: 'test child', assigned_to: 'test',
                        priority: 'low', domain: 'test', claim_epoch: 0, retry_count: 0,
                        max_retries: 1, depth: 0, timeout_s: 60, created_at: datetime(), updated_at: datetime()})
        CREATE (b)-[:DEPENDS_ON]->(a)
    ''')
    # Verify
    r = s.run('''
        MATCH (child:Task {task_id: 'dep-test-child'})-[:DEPENDS_ON]->(parent:Task)
        RETURN parent.task_id AS pid, child.status AS cstatus
    ''').single()
    print(f'Parent: {r[\"pid\"]}, Child status: {r[\"cstatus\"]}')
    assert r['pid'] == 'dep-test-parent'
    assert r['cstatus'] == 'BLOCKED'
    print('[OK] DEPENDS_ON relationship works')
    # Cleanup
    s.run('MATCH (t:Task) WHERE t.task_id STARTS WITH \"dep-test-\" DETACH DELETE t')
    print('[OK] Cleaned up')
store.close()
"
```

**Acceptance Criteria:**
- [ ] DEPENDS_ON relationship created successfully
- [ ] BLOCKED status accepted by Neo4j
- [ ] Cleanup removes all test nodes

### Exit Criteria Phase 1
- [ ] Both indexes created, `--verify` passes
- [ ] DEPENDS_ON relationship and BLOCKED status work in Neo4j
- [ ] No regressions in existing schema

---

## Phase 2: Core Dependency Primitives
**Duration**: 1-2 hours
**Dependencies**: Phase 1
**Parallelizable**: No (sequential — each builds on the previous)

### Task 2.1: Extend `create_task()` with `depends_on` Parameter
**Dependencies**: Phase 1

**File:** `neo4j_v2_core.py`
**Location:** Modify `create_task()` method (line 392)

Changes:
1. Add `depends_on: Optional[list[str]] = None` parameter
2. Add `pipeline_id: str = ""` and `phase: float = 0` parameters
3. Set initial status to `'BLOCKED'` if `depends_on` is non-empty, `'PENDING'` otherwise
4. Include `pipeline_id` and `phase` in the CREATE Cypher
5. After creating the task node, create DEPENDS_ON edges for each dependency

```python
def create_task(self, task_id: str, title: str, prompt: str,
                assigned_to: str, priority: str = "normal",
                domain: str = "implementation", skill_hint: str = "",
                source: str = "system", depth: int = 0,
                parent_id: Optional[str] = None,
                depends_on: Optional[list[str]] = None,
                pipeline_id: str = "", phase: float = 0,
                max_retries: int = 3, timeout_s: int = 10800) -> dict:
```

The CREATE Cypher changes from `status: 'PENDING'` to:
```cypher
status: CASE WHEN size($depends_on) > 0 THEN 'BLOCKED' ELSE 'PENDING' END,
pipeline_id: $pipeline_id,
phase: $phase,
```

After creating the task, create DEPENDS_ON edges:
```python
if depends_on:
    for dep_id in depends_on:
        session.run("""
            MATCH (child:Task {task_id: $child_id})
            MATCH (dep:Task {task_id: $dep_id})
            CREATE (child)-[:DEPENDS_ON]->(dep)
        """, child_id=task_id, dep_id=dep_id)
```

**Critical:** Use `CREATE` not `MERGE` for DEPENDS_ON — each dependency is created exactly once during task creation. Duplicates indicate a bug.

**Files:**
- Modify: `neo4j_v2_core.py` (~25 lines changed in `create_task`)

**Acceptance Criteria:**
- [ ] `create_task(depends_on=["x"])` creates task with status BLOCKED
- [ ] `create_task(depends_on=None)` creates task with status PENDING (backward compatible)
- [ ] DEPENDS_ON edges exist in Neo4j
- [ ] `pipeline_id` and `phase` stored on task node

### Task 2.2: Modify `claim_task()` to Respect Dependencies
**Dependencies**: Task 2.1

**File:** `neo4j_v2_core.py`
**Location:** Inside `_claim()` transaction function (line 73)

Add a dependency check to the WHERE clause. The task must have NO unresolved DEPENDS_ON targets:

```cypher
MATCH (t:Task {assigned_to: $agent, status: 'PENDING'})
WHERE (t.retry_after IS NULL OR t.retry_after <= datetime())
  AND NOT EXISTS {
    MATCH (t)-[:DEPENDS_ON]->(dep:Task)
    WHERE dep.status <> 'COMPLETED'
  }
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
```

**Note:** This check only fires for PENDING tasks. BLOCKED tasks won't match `status: 'PENDING'` at all, so they're naturally excluded. The EXISTS subquery catches edge cases where a task was moved to PENDING but a dependency later failed and was retried (re-entering PENDING).

**Impact on existing tasks:** Zero. Existing tasks have no DEPENDS_ON edges, so the NOT EXISTS clause is vacuously true — they continue to be claimable as before.

**Files:**
- Modify: `neo4j_v2_core.py` (~5 lines changed in `_claim`)

**Acceptance Criteria:**
- [ ] Tasks with all dependencies COMPLETED are claimable
- [ ] Tasks with any non-COMPLETED dependency are NOT claimable
- [ ] Existing tasks (no dependencies) claim normally — zero regression

### Task 2.3: Add `unblock_dependents()` Method
**Dependencies**: Task 2.2

**File:** `neo4j_v2_core.py`
**Location:** New method after `complete_task()` (around line 170)

```python
def unblock_dependents(self, task_id: str) -> list[str]:
    """Promote BLOCKED tasks to PENDING when all their dependencies are COMPLETED.

    Called after complete_task(). Push-based: O(dependents of this task),
    not O(all blocked tasks).

    Returns list of task_ids that were unblocked.
    """
    with self.driver.session() as session:
        result = session.run("""
            MATCH (completed:Task {task_id: $id, status: 'COMPLETED'})
            MATCH (blocked:Task {status: 'BLOCKED'})-[:DEPENDS_ON]->(completed)
            WHERE NOT EXISTS {
                MATCH (blocked)-[:DEPENDS_ON]->(other:Task)
                WHERE other.task_id <> $id AND other.status <> 'COMPLETED'
            }
            SET blocked.status = 'PENDING',
                blocked.updated_at = datetime()
            RETURN blocked.task_id AS unblocked
        """, id=task_id)
        unblocked = [rec["unblocked"] for rec in result]
        if unblocked:
            logger.info(f"Task {task_id} completed → unblocked {len(unblocked)} dependents: {unblocked}")
        return unblocked
```

**Key:** The WHERE clause checks that ALL other dependencies (not just the one that just completed) are also COMPLETED. Only then does the blocked task transition to PENDING.

**Files:**
- Modify: `neo4j_v2_core.py` (~25 lines)

**Acceptance Criteria:**
- [ ] BLOCKED task with 2 dependencies stays BLOCKED when only 1 completes
- [ ] BLOCKED task with 2 dependencies becomes PENDING when both complete
- [ ] Returns correct list of unblocked task_ids
- [ ] Idempotent — calling twice after same completion has no effect

### Task 2.4: Wire `unblock_dependents()` into `complete_task()`
**Dependencies**: Task 2.3

**File:** `neo4j_v2_core.py`
**Location:** Inside `complete_task()`, after the successful completion check (line 162-164)

```python
record = result.single()
if record:
    logger.info(f"Task {task_id} completed")
    # Unblock any tasks that depend on this one
    self.unblock_dependents(task_id)
    return True, "completed"
```

This is 2 lines. The `unblock_dependents` call is fire-and-forget from the caller's perspective — if it fails, the completed task stays completed, and a periodic sweep can fix orphaned BLOCKED tasks later.

**Files:**
- Modify: `neo4j_v2_core.py` (~2 lines)

**Acceptance Criteria:**
- [ ] Completing a task automatically unblocks its dependents
- [ ] `complete_task()` return value unchanged (backward compatible)
- [ ] Unblocking failure does not prevent task completion

### Exit Criteria Phase 2
- [ ] `create_task(depends_on=[...])` creates BLOCKED tasks with DEPENDS_ON edges
- [ ] `claim_task()` skips tasks with unresolved dependencies
- [ ] `complete_task()` triggers `unblock_dependents()` automatically
- [ ] BLOCKED → PENDING transition works for multi-dependency fan-in
- [ ] All existing tests still pass (zero regression)

---

## Phase 3: Daily Pipeline Launcher
**Duration**: 1-2 hours
**Dependencies**: Phase 2
**Parallelizable**: No

### Task 3.1: Create `launch_daily_reflection_pipeline.py` — Core Structure
**Dependencies**: Phase 2

**File:** `launch_daily_reflection_pipeline.py` (NEW)
**Location:** `/Users/kublai/.openclaw/agents/main/scripts/launch_daily_reflection_pipeline.py`

Creates all reflection pipeline tasks as a dependency graph in one function call. The launcher creates tasks but does NOT execute them — existing executors (`agent-task-handler.py`) claim them as they become PENDING. **Runs once daily** instead of hourly — pipeline_id uses date only (e.g., `reflection-2026-03-20`).

```python
#!/usr/bin/env python3
"""
launch_daily_reflection_pipeline.py — Create reflection pipeline as a task dependency graph.

Replaces the bash orchestration in hourly_reflection.sh with Neo4j tasks
that have DEPENDS_ON relationships. Executors claim tasks as they become PENDING.

Usage:
    python3 launch_daily_reflection_pipeline.py                # Create pipeline tasks
    python3 launch_daily_reflection_pipeline.py --dry-run      # Print task graph without creating
    python3 launch_daily_reflection_pipeline.py --status <pid> # Check pipeline status
"""

import os, sys, argparse, logging
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_v2_core import TaskStore
from agents_config import AGENTS

logger = logging.getLogger(__name__)


def launch_pipeline(store: TaskStore, dry_run: bool = False) -> dict:
    """Create all pipeline tasks with dependency edges.

    Returns dict mapping phase names to lists of task_ids.
    """
    now = datetime.now(timezone.utc)
    pid = f"reflection-{now.strftime('%Y-%m-%d')}"

    task_ids = {"pipeline_id": pid}

    # Phase 1: Reflections — 6 tasks, no dependencies (PENDING immediately)
    reflect_ids = []
    for agent in AGENTS:
        tid = f"{pid}-reflect-{agent}"
        if not dry_run:
            store.create_task(
                task_id=tid,
                title=f"Protocol reflection: {agent}",
                prompt=f"python3 meta_reflection.py --protocol --agent {agent}",
                assigned_to=agent,
                priority="high",
                domain="reflection",
                source="pipeline",
                pipeline_id=pid,
                phase=1,
                timeout_s=120,
                max_retries=1,
            )
        reflect_ids.append(tid)
    task_ids["reflect"] = reflect_ids

    # Phase 2: Reviews — 6 tasks, each BLOCKED on ALL 6 reflections
    review_ids = []
    for agent in AGENTS:
        tid = f"{pid}-review-{agent}"
        if not dry_run:
            store.create_task(
                task_id=tid,
                title=f"Performance review: {agent}",
                prompt=f"python3 review-with-fallback.py --agent {agent} --timeout 300",
                assigned_to="kublai",  # Kublai reviews all agents
                priority="high",
                domain="review",
                source="pipeline",
                depends_on=reflect_ids,
                pipeline_id=pid,
                phase=2,
                timeout_s=600,
                max_retries=1,
            )
        review_ids.append(tid)
    task_ids["review"] = review_ids

    # Phase 2.5: Post-review — 2 tasks, BLOCKED on all 6 reviews
    post_review_ids = []
    for name, cmd, timeout in [
        ("anomaly-scan", "python3 reflection_anomaly_scanner.py", 60),
        ("rule-compliance", "python3 parse_rule_compliance.py", 30),
    ]:
        tid = f"{pid}-{name}"
        if not dry_run:
            store.create_task(
                task_id=tid,
                title=f"Post-review: {name}",
                prompt=cmd,
                assigned_to="kublai",
                priority="normal",
                domain="analysis",
                source="pipeline",
                depends_on=review_ids,
                pipeline_id=pid,
                phase=2.5,
                timeout_s=timeout,
                max_retries=1,
            )
        post_review_ids.append(tid)
    task_ids["post_review"] = post_review_ids

    # Phase 3 Tier 1: Downstream scoring — 6 parallel tasks, BLOCKED on post-review
    tier1_scripts = [
        ("memory-audit", "python3 memory_audit.py --fix", 30),
        ("cross-agent-rules", "python3 cross_agent_rules.py", 30),
        ("route-quality", "python3 route_quality_tracker.py", 30),
        ("routing-audit", "python3 routing_audit_action.py", 30),
        ("neo4j-scorer", "python3 neo4j_v2_scorer.py --update-all", 30),
        ("action-scorer", "python3 action_scorer.py", 30),
    ]
    tier1_ids = []
    for name, cmd, timeout in tier1_scripts:
        tid = f"{pid}-{name}"
        if not dry_run:
            store.create_task(
                task_id=tid,
                title=f"Downstream: {name}",
                prompt=cmd,
                assigned_to="kublai",
                priority="normal",
                domain="scoring",
                source="pipeline",
                depends_on=post_review_ids,
                pipeline_id=pid,
                phase=3,
                timeout_s=timeout,
                max_retries=1,
            )
        tier1_ids.append(tid)
    task_ids["tier1"] = tier1_ids

    # Phase 3 Tier 2: Skill stats — BLOCKED on all Tier 1
    tier2_tid = f"{pid}-skill-stats"
    if not dry_run:
        store.create_task(
            task_id=tier2_tid,
            title="Downstream: update-skill-stats",
            prompt="python3 update_skill_stats.py",
            assigned_to="kublai",
            priority="normal",
            domain="scoring",
            source="pipeline",
            depends_on=tier1_ids,
            pipeline_id=pid,
            phase=3.5,
            timeout_s=30,
            max_retries=1,
        )
    task_ids["tier2"] = [tier2_tid]

    # Phase 3 Tier 3: Final reports — BLOCKED on Tier 2
    tier3_scripts = [
        ("kublai-actions", "python3 kublai-actions.py --trigger kurultai", 60),
        ("hourly-report", "python3 generate_hourly_report.py", 60),
    ]
    tier3_ids = []
    for name, cmd, timeout in tier3_scripts:
        tid = f"{pid}-{name}"
        if not dry_run:
            store.create_task(
                task_id=tid,
                title=f"Final: {name}",
                prompt=cmd,
                assigned_to="kublai",
                priority="normal",
                domain="reporting",
                source="pipeline",
                depends_on=[tier2_tid],
                pipeline_id=pid,
                phase=4,
                timeout_s=timeout,
                max_retries=1,
            )
        tier3_ids.append(tid)
    task_ids["tier3"] = tier3_ids

    return task_ids


def get_pipeline_status(store: TaskStore, pipeline_id: str) -> dict:
    """Query status of all tasks in a pipeline run."""
    with store.driver.session() as s:
        result = s.run("""
            MATCH (t:Task {pipeline_id: $pid})
            RETURN t.task_id AS id, t.title AS title, t.status AS status,
                   t.phase AS phase, t.assigned_to AS agent
            ORDER BY t.phase, t.created_at
        """, pid=pipeline_id)
        tasks = [dict(r) for r in result]

    summary = {}
    for t in tasks:
        status = t["status"]
        summary[status] = summary.get(status, 0) + 1

    return {"pipeline_id": pipeline_id, "tasks": tasks, "summary": summary}


def main():
    parser = argparse.ArgumentParser(description="Launch reflection pipeline as task graph")
    parser.add_argument("--dry-run", action="store_true", help="Print task graph without creating")
    parser.add_argument("--status", metavar="PIPELINE_ID", help="Check pipeline status")
    args = parser.parse_args()

    store = TaskStore()
    try:
        if args.status:
            status = get_pipeline_status(store, args.status)
            print(f"Pipeline: {status['pipeline_id']}")
            print(f"Summary: {status['summary']}")
            for t in status['tasks']:
                print(f"  [{t['status']:9s}] Phase {t['phase']}: {t['title']} ({t['agent']})")
        else:
            result = launch_pipeline(store, dry_run=args.dry_run)
            pid = result["pipeline_id"]
            total = sum(len(v) for k, v in result.items() if k != "pipeline_id")
            mode = "DRY RUN" if args.dry_run else "CREATED"
            print(f"[{mode}] Pipeline {pid}: {total} tasks")
            for phase_name, ids in result.items():
                if phase_name == "pipeline_id":
                    continue
                print(f"  {phase_name}: {len(ids)} tasks")
                for tid in ids:
                    print(f"    {tid}")
    finally:
        store.close()


if __name__ == "__main__":
    main()
```

**Files:**
- Create: `launch_daily_reflection_pipeline.py` (~200 lines)

**Acceptance Criteria:**
- [ ] `--dry-run` prints all 23 task IDs with correct dependency structure
- [ ] Without `--dry-run`, creates all tasks in Neo4j with correct statuses
- [ ] Phase 1 tasks are PENDING, all other phases are BLOCKED
- [ ] `--status <pipeline_id>` shows all tasks and their statuses

### Task 3.2: Add Dedup Guard to Pipeline Launcher
**Dependencies**: Task 3.1

Prevent double-launch within the same hour. Check if a pipeline with the same hour prefix already exists:

```python
def _check_existing_pipeline(store: TaskStore, hour_prefix: str) -> Optional[str]:
    """Return pipeline_id if a pipeline already exists for this hour."""
    with store.driver.session() as s:
        result = s.run("""
            MATCH (t:Task)
            WHERE t.pipeline_id STARTS WITH $prefix
            RETURN t.pipeline_id AS pid
            LIMIT 1
        """, prefix=f"reflection-{hour_prefix}")
        rec = result.single()
        return rec["pid"] if rec else None
```

Call this at the top of `launch_pipeline()`. If a pipeline exists, log and return early.

**Files:**
- Modify: `launch_daily_reflection_pipeline.py` (~15 lines)

**Acceptance Criteria:**
- [ ] Second launch within same hour is rejected with message
- [ ] `--force` flag overrides the dedup check

### Task 3.3: Add Pipeline Cleanup Function
**Dependencies**: Task 3.1

Remove all tasks for a pipeline run (for cleanup after testing or stuck pipelines):

```python
def cleanup_pipeline(store: TaskStore, pipeline_id: str) -> int:
    """Delete all tasks in a pipeline run. Returns count deleted."""
    with store.driver.session() as s:
        result = s.run("""
            MATCH (t:Task {pipeline_id: $pid})
            OPTIONAL MATCH (t)-[r]-()
            DELETE r, t
            RETURN count(t) AS deleted
        """, pid=pipeline_id)  # Note: this counts all tasks, not distinct
        # More accurate:
        result = s.run("""
            MATCH (t:Task {pipeline_id: $pid})
            DETACH DELETE t
            RETURN count(t) AS deleted
        """, pid=pipeline_id)
        return result.single()["deleted"]
```

Wire into CLI: `--cleanup <pipeline_id>`

**Files:**
- Modify: `launch_daily_reflection_pipeline.py` (~20 lines)

**Acceptance Criteria:**
- [ ] `--cleanup <pipeline_id>` removes all tasks for that pipeline
- [ ] Returns count of deleted tasks
- [ ] Handles non-existent pipeline gracefully

### Exit Criteria Phase 3
- [ ] `python3 launch_daily_reflection_pipeline.py --dry-run` shows 23 tasks across 6 phases
- [ ] Full launch creates all tasks with correct BLOCKED/PENDING statuses
- [ ] `--status` shows correct pipeline state
- [ ] `--cleanup` removes all pipeline tasks
- [ ] Dedup prevents double-launch (daily granularity)

---

## Phase 3.5: Human Approval Gate in Voting
**Duration**: 45-60 minutes
**Dependencies**: Phase 1 (needs Neo4j schema)
**Parallelizable**: No

Currently, when all 6 agents vote APPROVE on a proposal, `phase4_check_consensus()` in `kurultai_voting.py` immediately creates implementation tasks. The owner never sees the proposal. This phase adds a human-in-the-loop: 6/6 consensus → Signal DM to owner → owner replies → task created.

### Task 3.5.1: Add `PENDING_HUMAN_APPROVAL` Status to Voting
**Dependencies**: Phase 1

**File:** `kurultai_voting.py`
**Location:** Modify `phase4_check_consensus()` (line 565)

Instead of immediately calling `_create_task_for_proposal(proposal_id)` when `consensus == True`, change the flow:

1. Move the proposal file to a new `awaiting_approval/` directory (not `approved/`)
2. Set a `human_approval_status: 'PENDING_HUMAN_APPROVAL'` field on the Neo4j `AgentFeedback` node
3. Call `_notify_owner_for_approval(proposal_id, tally)` to send Signal DM

```python
# In phase4_check_consensus(), replace the consensus=True branch:

if consensus:
    # Move to awaiting_approval (not approved yet)
    awaiting_dir = PROPOSALS_DIR / "awaiting_approval"
    awaiting_dir.mkdir(parents=True, exist_ok=True)
    dest = awaiting_dir / f.name
    f.rename(dest)

    # Update Neo4j status
    _set_proposal_status(proposal_id, "PENDING_HUMAN_APPROVAL")

    # Notify owner via Signal DM
    _notify_owner_for_approval(proposal_id, tally, dest)

    results[proposal_id]["finalized"] = "awaiting_human_approval"
    log_phase(4, f"  -> AWAITING HUMAN APPROVAL: {proposal_id}")
```

Do NOT create tasks yet — that happens after human sign-off.

**Files:**
- Modify: `kurultai_voting.py` (~20 lines in `phase4_check_consensus`)

**Acceptance Criteria:**
- [ ] 6/6 consensus moves proposal to `awaiting_approval/` (not `approved/`)
- [ ] Neo4j node updated with `PENDING_HUMAN_APPROVAL` status
- [ ] No tasks created until human approves

### Task 3.5.2: Add Signal DM Notification for Approval
**Dependencies**: Task 3.5.1

**File:** `kurultai_voting.py`
**Location:** New function after `phase4_check_consensus()`

```python
OWNER_PHONE = "+19194133445"
SEND_SIGNAL_SCRIPT = Path.home() / ".claude" / "skills" / "agent-collaboration" / "scripts" / "send_signal.sh"

def _notify_owner_for_approval(proposal_id: str, tally: dict, proposal_path: Path):
    """Send Signal DM to owner with proposal summary for sign-off.

    The owner replies 'approve <id>' or 'reject <id>' to finalize.
    """
    # Read proposal for summary
    try:
        text = proposal_path.read_text()[:500]
    except Exception:
        text = "(could not read proposal)"

    # Extract title
    import re
    title_match = re.search(r'^#\s*Proposal:\s*(.+)', text, re.MULTILINE)
    title = title_match.group(1).strip()[:80] if title_match else proposal_id

    message = (
        f"KURULTAI VOTE: 6/6 APPROVE\n"
        f"Proposal: {title}\n"
        f"ID: {proposal_id}\n\n"
        f"{text[:300]}\n\n"
        f"Reply:\n"
        f"  'approve {proposal_id}' to sign off\n"
        f"  'reject {proposal_id}' to veto"
    )

    try:
        import subprocess
        subprocess.run(
            ["bash", str(SEND_SIGNAL_SCRIPT), message, "--dm", OWNER_PHONE],
            capture_output=True, timeout=15, text=True,
        )
        log_phase(4, f"  Signal DM sent to owner for {proposal_id}")
    except Exception as e:
        log_phase(4, f"  Signal DM failed: {e}")
```

**Files:**
- Modify: `kurultai_voting.py` (~35 lines)

**Acceptance Criteria:**
- [ ] Signal DM sent to +19194133445 on 6/6 consensus
- [ ] Message includes proposal title, ID, summary, and reply instructions
- [ ] DM failure doesn't crash the voting pipeline

### Task 3.5.3: Add Human Response Handler
**Dependencies**: Task 3.5.2

**File:** `signal_message_handler.py`
**Location:** Add a new handler step between Step 2 (profile commands) and Step 2.1 (context isolation)

When the owner sends "approve <proposal_id>" or "reject <proposal_id>", handle it:

```python
# Step 1.5: Voting approval commands (owner only)
if sender_phone == "+19194133445":
    text_lower = message_text.strip().lower()
    if text_lower.startswith("approve ") or text_lower.startswith("reject "):
        try:
            parts = message_text.strip().split(None, 1)
            action = parts[0].lower()  # "approve" or "reject"
            proposal_id = parts[1].strip() if len(parts) > 1 else ""

            if proposal_id:
                from kurultai_voting_approval import handle_human_approval
                result = handle_human_approval(proposal_id, action)
                _send_and_log(result, sender_phone, group_id, raw_msg)
                return True
        except Exception as e:
            log_msg(f"Voting approval handler error: {e}", "ERROR")
```

New file `kurultai_voting_approval.py`:

```python
def handle_human_approval(proposal_id: str, action: str) -> str:
    """Process human approve/reject for a proposal.

    Moves proposal from awaiting_approval/ to approved/ or rejected/.
    If approved, creates the implementation task.
    """
    awaiting_dir = PROPOSALS_DIR / "awaiting_approval"
    proposal_files = list(awaiting_dir.glob(f"{proposal_id}*"))

    if not proposal_files:
        return f"No proposal found awaiting approval with ID: {proposal_id}"

    proposal_file = proposal_files[0]

    if action == "approve":
        dest = APPROVED_DIR / proposal_file.name
        proposal_file.rename(dest)
        _set_proposal_status(proposal_id, "approved")
        _create_task_for_proposal(proposal_id)
        return f"Approved: {proposal_id}\nTask created and queued for execution."

    elif action == "reject":
        dest = REJECTED_DIR / proposal_file.name
        proposal_file.rename(dest)
        _set_proposal_status(proposal_id, "rejected_by_human")
        return f"Rejected: {proposal_id}\nProposal archived."

    return f"Unknown action: {action}"
```

**Files:**
- Modify: `signal_message_handler.py` (~15 lines)
- Create: `kurultai_voting_approval.py` (~50 lines)

**Acceptance Criteria:**
- [ ] Owner sends "approve <id>" → proposal moves to approved/, task created
- [ ] Owner sends "reject <id>" → proposal moves to rejected/, no task created
- [ ] Non-owner messages starting with "approve"/"reject" are NOT intercepted
- [ ] Response DM confirms the action taken

### Exit Criteria Phase 3.5
- [ ] 6/6 agent consensus sends Signal DM to +19194133445
- [ ] Owner "approve <id>" creates implementation task
- [ ] Owner "reject <id>" archives proposal without task creation
- [ ] Proposals without human sign-off do NOT generate tasks
- [ ] Existing non-consensus proposals (rejected/vetoed) still work as before

---

## Phase 4: Self-Test & Verification
**Duration**: 45-60 minutes
**Dependencies**: Phase 2
**Parallelizable**: Yes (Tasks 4.1-4.4 independent)

### Task 4.1: Add Dependency Self-Test to `neo4j_v2_core.py`
**Dependencies**: Phase 2

**File:** `neo4j_v2_core.py`
**Location:** Extend `_run_test()` function (after line 578)

Add a new section to the existing self-test:

```python
# --- Dependency test ---
print("\n9. Testing task dependencies...")
dep_parent_id = f"dep-parent-{uuid.uuid4().hex[:8]}"
dep_child_id = f"dep-child-{uuid.uuid4().hex[:8]}"

# Create parent (PENDING)
store.create_task(
    task_id=dep_parent_id, title="Dep parent", prompt="test",
    assigned_to=test_agent, priority="normal", domain="test",
)

# Create child with dependency (should be BLOCKED)
store.create_task(
    task_id=dep_child_id, title="Dep child", prompt="test",
    assigned_to=test_agent, priority="normal", domain="test",
    depends_on=[dep_parent_id],
)

child = store.get_task(dep_child_id)
assert child["status"] == "BLOCKED", f"Expected BLOCKED, got {child['status']}"
print("   [OK] Child created as BLOCKED")

# Child should NOT be claimable
claimed = store.claim_task(test_agent)
assert claimed is None or claimed["task_id"] != dep_child_id, "Child was claimed despite BLOCKED status"
print("   [OK] BLOCKED child not claimable")

# Claim and complete parent
parent_claimed = store.claim_task(test_agent)
assert parent_claimed["task_id"] == dep_parent_id
ok, _ = store.complete_task(dep_parent_id, parent_claimed["claim_epoch"],
                            text="done", problem="none", solution="none", rationale="test")
assert ok, "Parent completion failed"
print("   [OK] Parent completed")

# Child should now be PENDING (unblocked)
child = store.get_task(dep_child_id)
assert child["status"] == "PENDING", f"Expected PENDING after parent completed, got {child['status']}"
print("   [OK] Child unblocked to PENDING")

# Cleanup
with driver.session() as session:
    session.run("MATCH (t:Task) WHERE t.task_id IN [$p, $c] DETACH DELETE t",
                p=dep_parent_id, c=dep_child_id)
print("   [OK] Dependency test nodes cleaned up")
```

**Files:**
- Modify: `neo4j_v2_core.py` (~40 lines added to `_run_test()`)

**Acceptance Criteria:**
- [ ] `python3 neo4j_v2_core.py --test` passes all existing + new dependency tests
- [ ] BLOCKED → PENDING transition verified
- [ ] Claim filtering verified
- [ ] Cleanup complete

### Task 4.2: Add Fan-In Dependency Test
**Dependencies**: Phase 2

Test that a task blocked on 2 dependencies only unblocks when BOTH complete:

```python
# Fan-in test: child depends on parent_a AND parent_b
# Complete parent_a → child stays BLOCKED
# Complete parent_b → child becomes PENDING
```

Add to the self-test in `neo4j_v2_core.py` after Task 4.1's test block.

**Files:**
- Modify: `neo4j_v2_core.py` (~35 lines)

**Acceptance Criteria:**
- [ ] Child stays BLOCKED when only 1 of 2 parents complete
- [ ] Child becomes PENDING when both parents complete
- [ ] All test nodes cleaned up

### Task 4.3: Verify Backward Compatibility
**Dependencies**: Phase 2

Run existing tests to confirm zero regression:

```bash
# Existing core self-test
python3 neo4j_v2_core.py --test

# Schema verify
python3 neo4j_v2_schema.py --verify

# Reflection self-test (conversational health)
python3 neo4j_v2_reflection.py --self-test

# Create a normal task (no depends_on) and claim it
python3 -c "
from neo4j_v2_core import TaskStore
store = TaskStore()
t = store.create_task(task_id='compat-test-001', title='Compat test', prompt='test',
                      assigned_to='kublai', priority='low', domain='test')
assert t['status'] == 'PENDING', f'Expected PENDING, got {t[\"status\"]}'
claimed = store.claim_task('kublai')
assert claimed is not None and claimed['task_id'] == 'compat-test-001'
print('[OK] Backward compatible — task without dependencies works normally')
# Cleanup
with store.driver.session() as s:
    s.run('MATCH (t:Task {task_id: \"compat-test-001\"}) DETACH DELETE t')
store.close()
"
# Expected: All pass
```

**Acceptance Criteria:**
- [ ] All 3 existing self-tests pass
- [ ] Task creation without `depends_on` defaults to PENDING (not BLOCKED)
- [ ] `claim_task()` for dependency-free tasks works exactly as before

### Task 4.4: Pipeline Launch + Status End-to-End Test
**Dependencies**: Phase 3

```bash
# Launch a test pipeline
python3 launch_daily_reflection_pipeline.py

# Check status
PIPELINE_ID=$(python3 -c "
from datetime import datetime, timezone
print(f'reflection-{datetime.now(timezone.utc).strftime(\"%Y-%m-%d-%H%M\")}')")
python3 launch_daily_reflection_pipeline.py --status "$PIPELINE_ID"

# Expected: 6 PENDING (reflections), 17 BLOCKED (everything else)

# Cleanup
python3 launch_daily_reflection_pipeline.py --cleanup "$PIPELINE_ID"
```

**Acceptance Criteria:**
- [ ] Pipeline creates 23 tasks
- [ ] 6 reflection tasks are PENDING
- [ ] 17 remaining tasks are BLOCKED
- [ ] Status command shows correct breakdown
- [ ] Cleanup removes all 23 tasks

### Exit Criteria Phase 4
- [ ] All self-tests pass (core, schema, reflection, dependency, fan-in)
- [ ] Backward compatibility confirmed
- [ ] Pipeline launch + status + cleanup work end-to-end
- [ ] Zero regression in existing functionality

---

## Phase 5: Shadow Mode Integration
**Duration**: 30-45 minutes
**Dependencies**: Phase 4
**Parallelizable**: No

### Task 5.1: Add `--shadow` Flag to Pipeline Launcher
**Dependencies**: Phase 4

Shadow mode creates the pipeline tasks and monitors them WITHOUT replacing the bash orchestrator. Both run in parallel — bash does the real work, pipeline tasks track what would happen.

Add to `launch_daily_reflection_pipeline.py`:
```python
parser.add_argument("--shadow", action="store_true",
                    help="Shadow mode: create pipeline tasks alongside bash orchestrator")
```

In shadow mode:
- Tasks are created with `source='pipeline-shadow'` instead of `source='pipeline'`
- Tasks are NOT assigned to real agents — use `assigned_to='shadow-{agent}'` so executors don't pick them up
- A monitoring function runs every 30s, checking bash pipeline progress and manually completing shadow tasks as the bash steps finish

This lets you validate the task graph mirrors the bash execution without risk.

**Files:**
- Modify: `launch_daily_reflection_pipeline.py` (~30 lines)

**Acceptance Criteria:**
- [ ] Shadow tasks created with `source='pipeline-shadow'`
- [ ] Shadow tasks NOT claimable by real agents
- [ ] `--status` works for shadow pipelines

### Task 5.2: Add Pipeline Launcher to Cron (Disabled by Default)
**Dependencies**: Task 5.1

Add a commented-out entry to the hourly cron system that would replace the bash orchestrator:

```bash
# In the launchd plist or cron config, add (commented):
# FUTURE: Replace hourly_reflection.sh with:
# python3 /Users/kublai/.openclaw/agents/main/scripts/launch_daily_reflection_pipeline.py --shadow
```

Document the migration steps in a README section at the top of `launch_daily_reflection_pipeline.py`.

**Files:**
- Modify: `launch_daily_reflection_pipeline.py` (docstring update, ~10 lines)

**Acceptance Criteria:**
- [ ] Migration steps documented in script docstring
- [ ] Shadow mode invocation documented
- [ ] Cron entry documented (commented)

### Exit Criteria Phase 5
- [ ] Shadow mode creates non-claimable pipeline tasks
- [ ] Migration path documented
- [ ] Ready for Phase C (single-phase live wiring) in follow-up plan

---

## Dependency Graph

```
Phase 1 (Schema & Indexes)
    ├── Phase 2 (Core Dependency Primitives) — gate: DEEP
    │   ├── Phase 3 (Daily Pipeline Launcher) — gate: STANDARD
    │   │   └── Phase 4.4 (E2E Pipeline Test)
    │   ├── Phase 4.1-4.3 (Self-Tests) — gate: STANDARD
    │   └── Phase 5 (Shadow Mode) — gate: LIGHT
    └── Phase 3.5 (Human Approval Gate) — gate: STANDARD
        └── Phase 4 (includes approval testing)
```

## Risk Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| `claim_task()` regression | High | EXISTS subquery is vacuously true for tasks without DEPENDS_ON edges — zero behavioral change for existing tasks |
| `unblock_dependents()` failure | Medium | Fire-and-forget call in `complete_task()` — completion still succeeds. Orphaned BLOCKED tasks can be swept by a periodic job |
| Pool exhaustion from nested sessions | Medium | `unblock_dependents()` opens its own session, called after the `complete_task()` session closes. No nesting. |
| Deadlocked dependency cycles | Low | Pipeline graph is a strict DAG (phases flow forward). No cycle possible by construction. |
| Shadow mode pollutes task queue | Low | Shadow tasks use `assigned_to='shadow-{agent}'` — real executors filter on real agent names |

## What This Does NOT Include (Deferred)

- **Phase C**: Wiring real executors to run pipeline tasks (requires executor changes)
- **Phase D**: Retiring `hourly_reflection.sh` (requires Phase C validation)
- **Periodic BLOCKED sweep**: Job to detect orphaned BLOCKED tasks (fast-follow)
- **Brainstorm pipeline**: Brainstorming as a separate task graph (follow-up)
- **Pipeline dashboard**: Web UI for pipeline monitoring (aspirational)
- **Approval timeout**: Auto-expire proposals that sit in `PENDING_HUMAN_APPROVAL` > 48h (fast-follow)
- **Approval reminders**: Re-send Signal DM if owner hasn't responded in 12h (fast-follow)
