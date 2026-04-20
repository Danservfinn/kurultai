#!/usr/bin/env python3
"""task_custodian sweep plugin.

Scans the Kurultai Neo4j task graph for problematic tasks and proposes
per-task remediations. Plugin contract matches the other sweeps:

    audit() -> list[candidate]
    describe() -> str

Each candidate carries:
    target: "task:<task_id>"
    reason: "[action_kind] <short explanation>"
    autonomy_level: "task_action"
    evidence: {action_kind, task_id, agent, current_status, source, ...}

Action kinds produced:
    retry           — transient failure, re-run through existing /retry
    delete          — soft-delete via status=OBSOLETE (duplicates, harmful)
    rewrite_prompt  — repeated identical failure → prompt needs rewrite
    reassign        — chronic orphan → try a different agent

All downstream enforcement (per-action mode flag, rate limiter, circuit
breaker, denylist) lives in hermes-fix-task-action.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

MAX_CANDIDATES = 5

# Failure-category hints for the retry-vs-rewrite classifier.
# If the category is one of these, treat as transient → propose retry.
_TRANSIENT_CATEGORIES = {
    "network", "timeout", "rate_limit", "transient",
    "provider_busy", "model_overloaded", "temporary",
    "executor_crash", "lease_expired",
}

# If the category matches one of these, the prompt itself likely needs
# rewriting (not a retry). Propose rewrite_prompt.
_PROMPT_ERROR_CATEGORIES = {
    "prompt_error", "bad_prompt", "tool_mismatch",
    "context_too_large", "no_suitable_tool",
}


def _classify_failure(failure_record: dict) -> str:
    """Map a repeat-failure row to an action_kind.

    transient category  → retry
    prompt-error category → rewrite_prompt
    unknown / other     → reassign (try a different agent) as a
                          middle-ground default; delete is reserved for
                          dedup + LLM-classified harmful prompts only.
    """
    cat = (failure_record.get("last_error_category") or "").lower()
    if cat in _TRANSIENT_CATEGORIES:
        return "retry"
    if cat in _PROMPT_ERROR_CATEGORIES:
        return "rewrite_prompt"
    # Repeated failure with unrecognized category → try another agent
    # first; operator can graduate delete later for cases the dashboard
    # reviews decide are hopeless.
    return "reassign"


def _mk_candidate(action_kind: str, task_rec: dict,
                  reason_prefix: str) -> dict:
    return {
        "target": f"task:{task_rec['task_id']}",
        "reason": f"[{action_kind}] {reason_prefix}"[:500],
        "autonomy_level": "task_action",
        "evidence": {
            "action_kind": action_kind,
            "task_id": task_rec["task_id"],
            "agent": task_rec.get("agent"),
            "current_status": task_rec.get("status"),
            "source": task_rec.get("source"),
        },
    }


def audit() -> list[dict]:
    """Return sweep candidates. Called by hermes_sweep_runner."""
    from neo4j_v2_core import TaskStore
    from hermes_denylist import is_task_denied
    from hermes_task_queries import (
        find_repeat_failures, find_duplicate_pending, find_chronic_orphans,
    )

    candidates: list[dict] = []
    store = TaskStore()
    try:
        with store.driver.session() as session:
            # 1. Repeat failures
            for f in find_repeat_failures(session, threshold=3, window_hours=24):
                if len(candidates) >= MAX_CANDIDATES:
                    break
                if is_task_denied(f.get("source"), f.get("task_id"),
                                   f.get("agent"))[0]:
                    continue
                action = _classify_failure(f)
                candidates.append(_mk_candidate(
                    action, f,
                    reason_prefix=f"failed {f.get('fail_count', 0)}x/24h: "
                                   f"{(f.get('last_error_msg') or '')[:120]}",
                ))

            # 2. Duplicate PENDING tasks — keep oldest, propose delete on rest
            for group in find_duplicate_pending(session):
                if len(candidates) >= MAX_CANDIDATES:
                    break
                if not group:
                    continue
                keeper = group[0]
                for dupe in group[1:]:
                    if len(candidates) >= MAX_CANDIDATES:
                        break
                    if is_task_denied(dupe.get("source"), dupe.get("task_id"),
                                       dupe.get("agent"))[0]:
                        continue
                    candidates.append(_mk_candidate(
                        "delete", dupe,
                        reason_prefix=f"duplicate of {keeper['task_id']} "
                                       f"(same agent + prompt prefix)",
                    ))

            # 3. Chronic orphans — propose reassign
            for o in find_chronic_orphans(session, min_bounces=2):
                if len(candidates) >= MAX_CANDIDATES:
                    break
                if is_task_denied(o.get("source"), o.get("task_id"),
                                   o.get("agent"))[0]:
                    continue
                candidates.append(_mk_candidate(
                    "reassign", o,
                    reason_prefix=f"orphaned {o.get('bounces', 0)}x "
                                   f"(agent={o.get('agent')})",
                ))
    finally:
        # Close driver only if we own it — TaskStore handles this.
        try:
            store.close()
        except Exception:
            pass

    return candidates


def describe() -> str:
    return (
        "Scans the Kurultai task graph for repeat failures, duplicates, "
        "and chronic orphans. Proposes retry / delete (soft, via OBSOLETE) / "
        "rewrite_prompt / reassign per finding. Capped at "
        f"{MAX_CANDIDATES} candidates per run."
    )


if __name__ == "__main__":
    # Manual-run mode for testing
    import argparse
    import json
    p = argparse.ArgumentParser(description="task_custodian sweep plugin")
    p.add_argument("--describe", action="store_true")
    args = p.parse_args()
    if args.describe:
        print(describe())
    else:
        print(json.dumps(audit(), indent=2, default=str))
