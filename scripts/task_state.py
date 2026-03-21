#!/usr/bin/env python3
"""
task_state.py — CLI for agents to transition dispatch_phase via Bash.

Does NOT modify Neo4j `status` (that's Ogedei's job via TaskStore).
Only transitions the `dispatch_phase` sub-status property on WORKING tasks.

Uses CAS on claim_epoch to prevent race conditions.
Uses dual-write ordering: ledger FIRST, then Neo4j.

Exit codes:
    0 = success
    1 = CAS failed (another process modified the task)
    2 = invalid transition
    3 = Neo4j error
    4 = path validation error

Usage:
    python3 task_state.py phase --task-id <id> --phase planning --claim-epoch <N>
    python3 task_state.py phase --task-id <id> --phase executing --claim-epoch <N>
    python3 task_state.py phase --task-id <id> --phase pending_verification --claim-epoch <N> --result-file <path>
    python3 task_state.py heartbeat --task-id <id>
    python3 task_state.py fail --task-id <id> --error "msg" [--transient]
"""

import argparse
import json
import os
import sys
import logging
from datetime import datetime, timezone
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kurultai_paths import AGENTS_DIR, VALID_AGENTS
from kurultai_ledger import append_ledger

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Valid dispatch_phase transitions (AD1)
# ---------------------------------------------------------------------------

VALID_PHASES = {None, 'dispatched', 'planning', 'executing', 'pending_verification'}

VALID_PHASE_TRANSITIONS = {
    None:                      ['dispatched'],
    'dispatched':              ['planning', None],
    'planning':                ['executing', None],
    'executing':               ['pending_verification', None],
    'pending_verification':    [None],
}

# Reverse lookup: for each target phase, what are the valid source phases?
VALID_PHASE_SOURCES = {}
for src, targets in VALID_PHASE_TRANSITIONS.items():
    for tgt in targets:
        VALID_PHASE_SOURCES.setdefault(tgt, []).append(src)


# ---------------------------------------------------------------------------
# Security: path validation (C5, C7)
# ---------------------------------------------------------------------------

def validate_result_path(agent_name: str, result_file: str) -> str:
    """Reject path traversal. Returns canonical path or raises ValueError.

    result_file must resolve to a path under the agent's workspace/ directory.
    """
    if not agent_name or agent_name not in VALID_AGENTS:
        raise ValueError(f"Invalid agent name: {agent_name}")

    allowed_prefix = os.path.realpath(str(AGENTS_DIR / agent_name / "workspace"))
    canonical = os.path.realpath(result_file)

    if not canonical.startswith(allowed_prefix + os.sep) and canonical != allowed_prefix:
        raise ValueError(
            f"result_file must be under {allowed_prefix}/, got {canonical}"
        )

    return canonical


# ---------------------------------------------------------------------------
# Neo4j operations
# ---------------------------------------------------------------------------

def _get_store():
    """Lazy import to avoid import-time Neo4j connection."""
    from neo4j_v2_core import TaskStore
    return TaskStore()


def _emit_ledger(event: str, task_id: str, agent: str = "",
                 extra: Optional[dict] = None):
    """Write ledger event FIRST (dual-write: ledger before Neo4j)."""
    entry = {
        "event": event,
        "task_id": task_id,
        "agent": agent,
        "ts": datetime.now(timezone.utc).isoformat(),
        "executor": "agent-self",
    }
    if extra:
        entry.update(extra)
    append_ledger(entry)


def transition_phase(task_id: str, expected_epoch: int, new_phase: str,
                     result_file: Optional[str] = None,
                     agent: str = "") -> int:
    """Transition dispatch_phase with CAS on claim_epoch.

    Returns exit code: 0=success, 1=CAS_failed, 2=invalid_transition, 3=neo4j_error.
    """
    if new_phase not in VALID_PHASES and new_phase is not None:
        print(f"ERROR: Invalid phase '{new_phase}'", file=sys.stderr)
        return 2

    # Compute valid source phases for this transition
    allowed_from = VALID_PHASE_SOURCES.get(new_phase, [])
    # Convert None to string for Cypher comparison
    allowed_from_cypher = [p for p in allowed_from if p is not None]
    allow_null = None in allowed_from

    # Validate result_file path if provided
    validated_path = None
    if result_file:
        if not agent:
            print("ERROR: --agent required when using --result-file", file=sys.stderr)
            return 4
        try:
            validated_path = validate_result_path(agent, result_file)
        except ValueError as e:
            print(f"ERROR: Path validation failed: {e}", file=sys.stderr)
            return 4

    # Dual-write: ledger FIRST
    event_name = f"PHASE_{new_phase.upper()}" if new_phase else "PHASE_RESET"
    _emit_ledger(event_name, task_id, agent=agent, extra={
        "claim_epoch": expected_epoch,
        "new_phase": new_phase,
    })

    # Then Neo4j
    try:
        store = _get_store()
        try:
            with store.driver.session() as session:
                # Build WHERE clause for CAS + phase validation
                where_parts = [
                    "t.task_id = $task_id",
                    "t.status = 'WORKING'",
                    "t.claim_epoch = $expected_epoch",
                ]

                if allow_null and allowed_from_cypher:
                    where_parts.append(
                        "(t.dispatch_phase IS NULL OR t.dispatch_phase IN $allowed_from)"
                    )
                elif allow_null:
                    where_parts.append("t.dispatch_phase IS NULL")
                elif allowed_from_cypher:
                    where_parts.append("t.dispatch_phase IN $allowed_from")

                set_parts = [
                    "t.dispatch_phase = $new_phase",
                    "t.phase_updated_at = datetime()",
                ]

                params = {
                    "task_id": task_id,
                    "expected_epoch": expected_epoch,
                    "new_phase": new_phase,
                    "allowed_from": allowed_from_cypher,
                }

                if validated_path:
                    set_parts.append("t.result_file = $result_file")
                    params["result_file"] = validated_path

                query = (
                    f"MATCH (t:Task) WHERE {' AND '.join(where_parts)} "
                    f"SET {', '.join(set_parts)} "
                    "RETURN t.task_id AS tid"
                )

                result = session.run(query, **params)
                record = result.single()

                if record:
                    print(f"OK: {task_id} -> dispatch_phase={new_phase}")
                    return 0
                else:
                    # Diagnose why CAS failed
                    diag = session.run(
                        "MATCH (t:Task {task_id: $id}) "
                        "RETURN t.status AS status, t.claim_epoch AS epoch, "
                        "t.dispatch_phase AS phase",
                        id=task_id,
                    ).single()

                    if diag is None:
                        print(f"CAS FAILED: task {task_id} not found", file=sys.stderr)
                    elif diag["status"] != "WORKING":
                        print(f"CAS FAILED: status is {diag['status']}, not WORKING",
                              file=sys.stderr)
                    elif diag["epoch"] != expected_epoch:
                        print(f"CAS FAILED: epoch is {diag['epoch']}, expected {expected_epoch}",
                              file=sys.stderr)
                    else:
                        current = diag["phase"]
                        print(f"CAS FAILED: current phase '{current}' cannot transition "
                              f"to '{new_phase}'", file=sys.stderr)
                        return 2
                    return 1
        finally:
            store.close()
    except Exception as e:
        print(f"NEO4J ERROR: {e}", file=sys.stderr)
        return 3


def update_heartbeat(task_id: str) -> int:
    """Update last_heartbeat on a task. Returns 0 on success, 3 on error."""
    try:
        store = _get_store()
        try:
            with store.driver.session() as session:
                result = session.run(
                    "MATCH (t:Task {task_id: $id, status: 'WORKING'}) "
                    "SET t.last_heartbeat = datetime() "
                    "RETURN t.task_id AS tid",
                    id=task_id,
                )
                if result.single():
                    return 0
                print(f"HEARTBEAT FAILED: task {task_id} not WORKING", file=sys.stderr)
                return 1
        finally:
            store.close()
    except Exception as e:
        print(f"NEO4J ERROR: {e}", file=sys.stderr)
        return 3


def fail_task(task_id: str, error_msg: str, is_transient: bool = False) -> int:
    """Mark task as failed via TaskStore.fail_task(). Returns exit code."""
    # Ledger first
    _emit_ledger("FAILED", task_id, extra={
        "error_msg": error_msg[:500],
        "is_transient": is_transient,
        "source": "agent-self-report",
    })

    try:
        store = _get_store()
        try:
            # Get current claim_epoch
            task = store.get_task(task_id)
            if not task:
                print(f"ERROR: task {task_id} not found", file=sys.stderr)
                return 1
            if task.get("status") != "WORKING":
                print(f"ERROR: task {task_id} status is {task.get('status')}, not WORKING",
                      file=sys.stderr)
                return 1

            epoch = task.get("claim_epoch", 0)
            from neo4j_v2_failure import classify_failure
            error_class = "AGENT_REPORTED"
            if "auth" in error_msg.lower() or "401" in error_msg:
                error_class = "AUTH_FAILURE"
            elif "timeout" in error_msg.lower():
                error_class = "TIMEOUT"

            ok, new_status = store.fail_task(
                task_id, epoch, error_class, error_msg, is_transient
            )
            if ok:
                print(f"OK: {task_id} -> {new_status}")
                return 0
            print(f"FAIL CAS FAILED: {new_status}", file=sys.stderr)
            return 1
        finally:
            store.close()
    except Exception as e:
        print(f"NEO4J ERROR: {e}", file=sys.stderr)
        return 3


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Agent CLI for dispatch_phase transitions"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # phase command
    p_phase = sub.add_parser("phase", help="Transition dispatch_phase")
    p_phase.add_argument("--task-id", required=True, help="Task ID")
    p_phase.add_argument("--phase", required=True,
                         choices=["dispatched", "planning", "executing",
                                  "pending_verification"],
                         help="Target dispatch_phase")
    p_phase.add_argument("--claim-epoch", required=True, type=int,
                         help="Expected claim_epoch for CAS")
    p_phase.add_argument("--result-file", default=None,
                         help="Path to result file (for pending_verification)")
    p_phase.add_argument("--agent", default="",
                         help="Agent name (required with --result-file)")

    # heartbeat command
    p_hb = sub.add_parser("heartbeat", help="Update task heartbeat")
    p_hb.add_argument("--task-id", required=True, help="Task ID")

    # fail command
    p_fail = sub.add_parser("fail", help="Report task failure")
    p_fail.add_argument("--task-id", required=True, help="Task ID")
    p_fail.add_argument("--error", required=True, help="Error description")
    p_fail.add_argument("--transient", action="store_true",
                        help="Mark as transient (eligible for retry)")

    args = parser.parse_args()

    if args.command == "phase":
        code = transition_phase(
            args.task_id, args.claim_epoch, args.phase,
            result_file=args.result_file, agent=args.agent,
        )
        sys.exit(code)
    elif args.command == "heartbeat":
        code = update_heartbeat(args.task_id)
        sys.exit(code)
    elif args.command == "fail":
        code = fail_task(args.task_id, args.error, args.transient)
        sys.exit(code)


if __name__ == "__main__":
    main()
