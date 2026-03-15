#!/usr/bin/env python3
"""
neo4j_v2_core.py — Core task primitives with claim_epoch fencing.

All state transitions use compare-and-swap via claim_epoch to prevent:
  - Orphan recovery vs executor race
  - Double-claim
  - FAIL vs COMPLETE race

State machine:
    PENDING --(claim)--> WORKING
    WORKING --(complete)--> COMPLETED  (requires TaskOutput + no blocking children)
    WORKING --(fail transient, retries remain)--> PENDING  (carries FailureReport, retry_after backoff)
    WORKING --(fail permanent or exhausted)--> FAILED  (carries FailureReport)
    WORKING --(orphan recovery)--> ORPHANED  (hold period before retry)
    ORPHANED --(promote, after hold)--> PENDING

Usage:
    from neo4j_v2_core import TaskStore
    store = TaskStore()
    task = store.claim_task("temujin", lease_minutes=30)
    store.complete_task(task["task_id"], task["claim_epoch"], output={...})
"""

import os
import sys
import logging
from datetime import datetime, timezone
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import get_driver, close_driver

logger = logging.getLogger(__name__)

# Default lease duration in minutes
DEFAULT_LEASE_MINUTES = 30
# Max depth for delegation chains
MAX_DELEGATION_DEPTH = 2


class TaskStore:
    """Neo4j-first task store with fencing tokens."""

    def __init__(self, driver=None):
        self._driver = driver
        self._owns_driver = driver is None

    @property
    def driver(self):
        if self._driver is None:
            self._driver = get_driver()
        return self._driver

    def close(self):
        if self._owns_driver and self._driver is not None:
            close_driver()
            self._driver = None

    # ------------------------------------------------------------------
    # CLAIM: PENDING --> WORKING
    # ------------------------------------------------------------------

    def claim_task(self, agent: str, lease_minutes: int = DEFAULT_LEASE_MINUTES) -> Optional[dict]:
        """Atomically claim the highest-priority PENDING task for agent.

        Uses CAS on claim_epoch to prevent double-claim.
        Sets lease_expires_at for orphan recovery.

        Returns:
            Task dict with all properties + prior failure_reports, or None.
        """
        with self.driver.session() as session:
            result = session.run("""
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
                WITH t
                OPTIONAL MATCH (t)-[:HAS_FAILURE]->(f:FailureReport)
                WITH t, collect(f {.*}) AS failures
                RETURN t {.*, failure_reports: failures} AS task
            """, agent=agent, lease_min=lease_minutes)

            record = result.single()
            if record is None:
                return None

            task = dict(record["task"])
            # Neo4j datetime to ISO string for JSON compatibility
            for key in ("created_at", "started_at", "completed_at", "updated_at",
                        "lease_expires_at"):
                if key in task and task[key] is not None:
                    try:
                        task[key] = task[key].iso_format()
                    except (AttributeError, TypeError):
                        pass
            return task

    # ------------------------------------------------------------------
    # COMPLETE: WORKING --> COMPLETED
    # ------------------------------------------------------------------

    def complete_task(self, task_id: str, claim_epoch: int,
                      text: str, problem: str, solution: str,
                      rationale: str, output_lines: int = 0,
                      duration_s: float = 0.0) -> tuple[bool, str]:
        """Complete a task with structured output.

        Requires:
            - Task is WORKING with matching claim_epoch (CAS)
            - No PENDING/WORKING children (delegation gate)

        Creates:
            - (:TaskOutput) node linked via [:HAS_OUTPUT]
            - Sets COMPLETED status

        Returns:
            (success, reason) tuple.
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task {task_id: $id, status: 'WORKING', claim_epoch: $epoch})
                OPTIONAL MATCH (t)-[:SPAWNED*1..5]->(child:Task)
                    WHERE child.status IN ['PENDING', 'WORKING']
                WITH t, count(child) AS blocking
                WHERE blocking = 0
                SET t.status = 'COMPLETED',
                    t.completed_at = datetime(),
                    t.updated_at = datetime()
                CREATE (t)-[:HAS_OUTPUT]->(:TaskOutput {
                    text: $text,
                    problem: $problem,
                    solution: $solution,
                    rationale: $rationale,
                    output_lines: $output_lines,
                    duration_s: $duration_s,
                    created_at: datetime()
                })
                RETURN t.task_id AS tid
            """, id=task_id, epoch=claim_epoch, text=text,
                problem=problem, solution=solution, rationale=rationale,
                output_lines=output_lines, duration_s=duration_s)

            record = result.single()
            if record:
                logger.info(f"Task {task_id} completed")
                return True, "completed"

            # Diagnose why it failed
            ok, reason = self._diagnose_complete_failure(session, task_id, claim_epoch)
            if not ok:
                logger.warning(f"Rejected completion for {task_id}: {reason} (stale executor?)")
            return ok, reason

    def _diagnose_complete_failure(self, session, task_id: str, claim_epoch: int) -> tuple[bool, str]:
        """Figure out why complete_task CAS failed."""
        diag = session.run("""
            MATCH (t:Task {task_id: $id})
            OPTIONAL MATCH (t)-[:SPAWNED*1..5]->(child:Task)
                WHERE child.status IN ['PENDING', 'WORKING']
            RETURN t.status AS status, t.claim_epoch AS epoch,
                   count(child) AS blocking
        """, id=task_id, epoch=claim_epoch)
        rec = diag.single()
        if rec is None:
            return False, "not_found"
        if rec["status"] != "WORKING":
            return False, f"wrong_status:{rec['status']}"
        if rec["epoch"] != claim_epoch:
            return False, f"epoch_mismatch:{rec['epoch']}"
        if rec["blocking"] > 0:
            return False, f"blocking_children:{rec['blocking']}"
        return False, "unknown"

    # ------------------------------------------------------------------
    # FAIL: WORKING --> FAILED or PENDING (auto-retry)
    # ------------------------------------------------------------------

    def fail_task(self, task_id: str, claim_epoch: int,
                  error_class: str, error_msg: str,
                  is_transient: bool, output_snippet: str = "",
                  backoff_base_s: int = 30) -> tuple[bool, str]:
        """Fail a task, creating a FailureReport.

        If transient and retries remain: WORKING --> PENDING (auto-retry with backoff).
        Otherwise: WORKING --> FAILED.

        Args:
            backoff_base_s: Base seconds for exponential backoff (default 30).
                            Actual delay = min(base * 2^retry_count, 600).

        Returns:
            (success, new_status) tuple.
        """
        # Calculate exponential backoff with cap
        max_backoff_s = 600  # 10 minute cap

        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task {task_id: $id, status: 'WORKING', claim_epoch: $epoch})
                CREATE (t)-[:HAS_FAILURE]->(:FailureReport {
                    attempt: t.retry_count + 1,
                    error_class: $error_class,
                    error_msg: $error_msg,
                    is_transient: $transient,
                    output_snippet: $snippet,
                    created_at: datetime()
                })
                SET t.status = CASE
                        WHEN $transient AND t.retry_count < t.max_retries THEN 'PENDING'
                        ELSE 'FAILED'
                    END,
                    t.retry_count = t.retry_count + 1,
                    t.retry_after = CASE
                        WHEN $transient AND t.retry_count < t.max_retries
                        THEN datetime() + duration({seconds: CASE
                            WHEN $backoff_base * toInteger(2 ^ toFloat(t.retry_count)) > $max_backoff THEN $max_backoff
                            ELSE $backoff_base * toInteger(2 ^ toFloat(t.retry_count))
                        END})
                        ELSE null
                    END,
                    t.updated_at = datetime(),
                    t.lease_expires_at = null,
                    t.claimed_by = CASE
                        WHEN $transient AND t.retry_count < t.max_retries THEN null
                        ELSE t.claimed_by
                    END
                RETURN t.status AS new_status
            """, id=task_id, epoch=claim_epoch, error_class=error_class,
                error_msg=error_msg, transient=is_transient,
                snippet=output_snippet[:2000],
                backoff_base=backoff_base_s, max_backoff=max_backoff_s)

            record = result.single()
            if record:
                new_status = record["new_status"]
                logger.info(f"Task {task_id} -> {new_status} (class={error_class}, transient={is_transient})")
                return True, new_status
            return False, "cas_failed"

    # ------------------------------------------------------------------
    # LEASE MANAGEMENT
    # ------------------------------------------------------------------

    def renew_lease(self, task_id: str, claim_epoch: int,
                    lease_minutes: int = DEFAULT_LEASE_MINUTES) -> bool:
        """Extend lease on a WORKING task. CAS on claim_epoch."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task {task_id: $id, status: 'WORKING', claim_epoch: $epoch})
                SET t.lease_expires_at = datetime() + duration({minutes: $lease_min}),
                    t.updated_at = datetime()
                RETURN t.task_id AS tid
            """, id=task_id, epoch=claim_epoch, lease_min=lease_minutes)
            return result.single() is not None

    # ------------------------------------------------------------------
    # ORPHAN RECOVERY
    # ------------------------------------------------------------------

    def recover_orphans(self, grace_minutes: int = 5) -> list[dict]:
        """Recover WORKING tasks with expired leases.

        Moves to ORPHANED (hold period before retry) or FAILED (exhausted).
        Creates FailureReport for each recovery.

        Returns list of recovered task dicts.
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task {status: 'WORKING'})
                WHERE t.lease_expires_at IS NOT NULL
                  AND t.lease_expires_at < datetime() - duration({minutes: $grace})
                CREATE (t)-[:HAS_FAILURE]->(:FailureReport {
                    attempt: t.retry_count + 1,
                    error_class: 'ORPHAN_RECOVERY',
                    error_msg: 'Task lease expired, executor presumed dead',
                    is_transient: true,
                    output_snippet: '',
                    created_at: datetime()
                })
                SET t.status = CASE
                        WHEN t.retry_count < t.max_retries THEN 'ORPHANED'
                        ELSE 'FAILED'
                    END,
                    t.orphaned_at = CASE
                        WHEN t.retry_count < t.max_retries THEN datetime()
                        ELSE null
                    END,
                    t.updated_at = datetime()
                RETURN t {.task_id, .status, .assigned_to, .retry_count} AS task
            """, grace=grace_minutes)

            recovered = [dict(rec["task"]) for rec in result]
            if recovered:
                logger.warning(f"Recovered {len(recovered)} orphaned tasks: "
                               f"{[t['task_id'] for t in recovered]}")
            return recovered

    def promote_orphans(self, hold_minutes: int = 5) -> list[dict]:
        """Move ORPHANED tasks to PENDING after hold period.

        Tasks sit in ORPHANED state for hold_minutes before being
        promoted back to PENDING, giving slow executors time to finish.
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task {status: 'ORPHANED'})
                WHERE t.orphaned_at < datetime() - duration({minutes: $hold})
                SET t.status = 'PENDING',
                    t.retry_count = t.retry_count + 1,
                    t.lease_expires_at = null,
                    t.claimed_by = null,
                    t.orphaned_at = null,
                    t.updated_at = datetime()
                RETURN t {.task_id, .status, .assigned_to} AS task
            """, hold=hold_minutes)
            promoted = [dict(rec["task"]) for rec in result]
            if promoted:
                logger.info(f"Promoted {len(promoted)} orphaned tasks to PENDING: "
                            f"{[t['task_id'] for t in promoted]}")
            return promoted

    # ------------------------------------------------------------------
    # QUERY HELPERS
    # ------------------------------------------------------------------

    def get_task(self, task_id: str) -> Optional[dict]:
        """Fetch a single task with its output and failure reports."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task {task_id: $id})
                OPTIONAL MATCH (t)-[:HAS_OUTPUT]->(o:TaskOutput)
                OPTIONAL MATCH (t)-[:HAS_FAILURE]->(f:FailureReport)
                WITH t, o, collect(f {.*}) AS failures
                RETURN t {.*,
                    output: o {.*},
                    failure_reports: failures
                } AS task
            """, id=task_id)
            record = result.single()
            return dict(record["task"]) if record else None

    def get_queue_depth(self, agent: str) -> dict:
        """Live queue depth from graph — no counters to drift."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task {assigned_to: $agent})
                WHERE t.status IN ['PENDING', 'WORKING']
                RETURN t.status AS status, count(t) AS cnt
            """, agent=agent)
            depths = {"PENDING": 0, "WORKING": 0}
            for rec in result:
                depths[rec["status"]] = rec["cnt"]
            return depths

    def get_agent_tasks(self, agent: str, status: Optional[str] = None,
                        limit: int = 50) -> list[dict]:
        """Get tasks for an agent, optionally filtered by status."""
        query = "MATCH (t:Task {assigned_to: $agent})"
        params = {"agent": agent, "limit": limit}
        if status:
            query += " WHERE t.status = $status"
            params["status"] = status
        query += " RETURN t {.*} AS task ORDER BY t.created_at DESC LIMIT $limit"

        with self.driver.session() as session:
            result = session.run(query, **params)
            return [dict(rec["task"]) for rec in result]

    # ------------------------------------------------------------------
    # TASK CREATION (used by delegation and intake)
    # ------------------------------------------------------------------

    def create_task(self, task_id: str, title: str, prompt: str,
                    assigned_to: str, priority: str = "normal",
                    domain: str = "implementation", skill_hint: str = "",
                    source: str = "system", depth: int = 0,
                    parent_id: Optional[str] = None,
                    max_retries: int = 3, timeout_s: int = 10800) -> dict:
        """Create a new PENDING task in Neo4j.

        If parent_id is provided, creates a SPAWNED relationship.
        """
        with self.driver.session() as session:
            result = session.run("""
                MERGE (a:Agent {name: $agent})
                CREATE (t:Task {
                    task_id: $task_id,
                    title: $title,
                    prompt: $prompt,
                    status: 'PENDING',
                    assigned_to: $agent,
                    priority: $priority,
                    domain: $domain,
                    skill_hint: $skill_hint,
                    source: $source,
                    depth: $depth,
                    claim_epoch: 0,
                    claimed_by: null,
                    lease_expires_at: null,
                    retry_count: 0,
                    max_retries: $max_retries,
                    timeout_s: $timeout_s,
                    created_at: datetime(),
                    started_at: null,
                    completed_at: null,
                    updated_at: datetime()
                })
                MERGE (a)-[:ASSIGNED_TO]->(t)
                RETURN t {.*} AS task
            """, task_id=task_id, title=title, prompt=prompt,
                agent=assigned_to, priority=priority, domain=domain,
                skill_hint=skill_hint, source=source, depth=depth,
                max_retries=max_retries, timeout_s=timeout_s)

            record = result.single()
            task = dict(record["task"])

            # Create SPAWNED edge if this is a child task
            if parent_id:
                session.run("""
                    MATCH (parent:Task {task_id: $parent_id})
                    MATCH (child:Task {task_id: $child_id})
                    MERGE (parent)-[:SPAWNED]->(child)
                """, parent_id=parent_id, child_id=task_id)

            logger.info(f"Created task {task_id} assigned to {assigned_to}"
                        f"{f' (child of {parent_id})' if parent_id else ''}")
            return task

    # ------------------------------------------------------------------
    # EXECUTED relationship (on completion/failure)
    # ------------------------------------------------------------------

    def record_execution(self, task_id: str, agent: str,
                         outcome: str, duration_s: float) -> bool:
        """Create EXECUTED relationship for historical queries."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (a:Agent {name: $agent})
                MATCH (t:Task {task_id: $id})
                MERGE (a)-[r:EXECUTED]->(t)
                SET r.outcome = $outcome,
                    r.duration_s = $duration_s,
                    r.completed_at = datetime()
                RETURN type(r) AS rel
            """, agent=agent, id=task_id, outcome=outcome, duration_s=duration_s)
            return result.single() is not None


# ---------------------------------------------------------------------------
# CLI self-test
# ---------------------------------------------------------------------------

def _run_test():
    """End-to-end test of core primitives."""
    import uuid
    from neo4j_v2_schema import apply_schema

    store = TaskStore()
    driver = store.driver

    # Ensure schema
    print("Applying schema...")
    apply_schema(driver, verbose=False)

    test_agent = "test-agent"
    test_id = f"normal-0000000000-{uuid.uuid4().hex[:8]}"

    try:
        # 1. Create
        print(f"\n1. Creating task {test_id}...")
        task = store.create_task(
            task_id=test_id, title="Core self-test", prompt="Test prompt",
            assigned_to=test_agent, priority="normal", domain="test",
        )
        assert task["status"] == "PENDING", f"Expected PENDING, got {task['status']}"
        print("   [OK] Task created as PENDING")

        # 2. Claim
        print("2. Claiming task...")
        claimed = store.claim_task(test_agent)
        assert claimed is not None, "Claim returned None"
        assert claimed["task_id"] == test_id, f"Wrong task claimed: {claimed['task_id']}"
        assert claimed["status"] == "WORKING", f"Expected WORKING, got {claimed['status']}"
        epoch = claimed["claim_epoch"]
        print(f"   [OK] Claimed with epoch={epoch}")

        # 3. Renew lease
        print("3. Renewing lease...")
        ok = store.renew_lease(test_id, epoch)
        assert ok, "Lease renewal failed"
        print("   [OK] Lease renewed")

        # 4. Fail (transient, should retry -> PENDING)
        print("4. Failing with transient error...")
        ok, new_status = store.fail_task(test_id, epoch, "TIMEOUT", "Test timeout", is_transient=True)
        assert ok, "Fail CAS failed"
        assert new_status == "PENDING", f"Expected PENDING after transient fail, got {new_status}"
        print(f"   [OK] Transient fail -> {new_status}")

        # 5. Re-claim (clear retry_after since backoff would block immediate re-claim)
        print("5. Re-claiming after retry...")
        with driver.session() as session:
            session.run("""
                MATCH (t:Task {task_id: $id})
                SET t.retry_after = null
            """, id=test_id)
        claimed2 = store.claim_task(test_agent)
        assert claimed2 is not None, "Re-claim returned None"
        epoch2 = claimed2["claim_epoch"]
        assert epoch2 > epoch, f"Epoch should increment: {epoch2} vs {epoch}"
        assert len(claimed2.get("failure_reports", [])) > 0, "Should carry failure context"
        print(f"   [OK] Re-claimed with epoch={epoch2}, {len(claimed2['failure_reports'])} prior failures")

        # 6. Complete
        print("6. Completing task...")
        ok, reason = store.complete_task(
            test_id, epoch2,
            text="Test output", problem="Test problem",
            solution="Test solution", rationale="Test rationale",
            output_lines=10, duration_s=5.0,
        )
        assert ok, f"Complete failed: {reason}"
        print("   [OK] Task completed")

        # 7. Verify final state
        print("7. Verifying final state...")
        final = store.get_task(test_id)
        assert final["status"] == "COMPLETED"
        assert final["output"] is not None
        assert final["output"]["problem"] == "Test problem"
        assert len(final["failure_reports"]) == 1
        print("   [OK] COMPLETED with output and failure history")

        # 8. Queue depth
        print("8. Checking queue depth...")
        depth = store.get_queue_depth(test_agent)
        print(f"   [OK] Queue: {depth}")

        print("\n  All core tests passed.")

    finally:
        # Cleanup
        with driver.session() as session:
            session.run("""
                MATCH (t:Task {task_id: $id})
                OPTIONAL MATCH (t)-[r1:HAS_OUTPUT]->(o:TaskOutput)
                OPTIONAL MATCH (t)-[r2:HAS_FAILURE]->(f:FailureReport)
                OPTIONAL MATCH ()-[r3]->(t)
                DELETE r1, r2, r3, o, f, t
            """, id=test_id)
            # Clean up test agent if no other tasks
            session.run("""
                MATCH (a:Agent {name: $agent})
                WHERE NOT (a)--()
                DELETE a
            """, agent=test_agent)
        store.close()
        print("  Test nodes cleaned up.")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Neo4j v2 core primitives")
    parser.add_argument("--test", action="store_true", help="Run self-test")
    args = parser.parse_args()

    if args.test:
        _run_test()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
