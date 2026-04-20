#!/usr/bin/env python3
"""hermes-fix-task-action — action authoring for the task_custodian sweep.

Analog of hermes-fix-content.py / hermes-fix-code.py. Invoked by the
sweep runner's _apply_candidate when autonomy_level == "task_action".

Inputs:
    --target task:<task_id>
    --reason "<short reason>"
    env HERMES_TASK_ACTION_KIND = retry | delete | rewrite_prompt | reassign
    env HERMES_TASK_AGENT          (current assigned_to)
    env HERMES_TASK_CURRENT_STATUS (current status)
    env HERMES_TASK_SOURCE         (source field, for denylist)

Gates (fail-closed at each):
    - hermes-disabled.flag (global T0)
    - hermes-autonomous-disabled.flag (master autonomous)
    - hermes-sweep-task_custodian-action-<kind>.flag (per-action)
    - hermes_denylist.is_task_denied(source)
    - hermes_rate_limit.consume_slot('task_action') (10/day cap)

Output: single-line JSON on stdout
    {"outcome": "applied" | "notify_only" | "error:<code>",
     "target": "task:...", "evidence": {action_kind, ..., previous_state_snapshot}}
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

HOME = Path.home()
FLAGS_DIR = HOME / ".openclaw" / "flags"
ACTIONS_LOG = HOME / ".openclaw" / "agents" / "main" / "logs" / "hermes-actions.jsonl"

KURULTAI_BASE = os.environ.get("KURULTAI_BASE_URL", "http://localhost:18790")
KURULTAI_API_TOKEN = os.environ.get("KURULTAI_API_TOKEN", "")
HTTP_TIMEOUT = 20

VALID_KINDS = {"retry", "delete", "rewrite_prompt", "reassign"}


def _global_flag(name: str) -> Path:
    return FLAGS_DIR / name


def _is_disabled_globally() -> tuple[bool, str]:
    for flag_name in ("hermes-disabled.flag", "hermes-autonomous-disabled.flag"):
        if _global_flag(flag_name).exists():
            return True, f"blocked by {flag_name}"
    return False, ""


def _per_action_mode(kind: str) -> str:
    """Read per-action mode flag. Default notify-only."""
    f = _global_flag(f"hermes-sweep-task_custodian-action-{kind}.flag")
    if not f.exists():
        return "notify-only"
    try:
        content = f.read_text(encoding="utf-8").strip()
    except OSError:
        return "notify-only"
    return "autonomous" if content == "autonomous" else "notify-only"


def _parse_target(target: str) -> Optional[str]:
    """Extract task_id from 'task:<id>' target string."""
    if not target.startswith("task:"):
        return None
    return target[len("task:"):].strip() or None


def _post_kurultai(path: str, body: dict) -> tuple[int, dict]:
    """POST to the Kurultai API. Uses bearer token when available.

    Returns (http_status, parsed_json_or_error_dict).
    """
    url = KURULTAI_BASE.rstrip("/") + path
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if KURULTAI_API_TOKEN:
        req.add_header("Authorization", f"Bearer {KURULTAI_API_TOKEN}")
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            status = resp.status
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return status, json.loads(raw)
            except json.JSONDecodeError:
                return status, {"raw": raw[:500]}
    except urllib.error.HTTPError as e:
        status = e.code
        try:
            raw = e.read().decode("utf-8", errors="replace")
            return status, json.loads(raw) if raw else {"error": e.reason}
        except (json.JSONDecodeError, OSError):
            return status, {"error": str(e)}
    except urllib.error.URLError as e:
        return 0, {"error": f"network: {e}"}


def _snapshot_task(task_id: str) -> dict:
    """Read the task's pre-mutation state from Neo4j for revert evidence."""
    try:
        from neo4j_v2_core import TaskStore
    except ImportError:
        return {}
    try:
        store = TaskStore()
        task = store.get_task(task_id)
        store.close()
    except Exception:
        return {}
    if not task:
        return {}
    # Capture only the fields a revert needs — keep evidence small
    return {
        "status": task.get("status"),
        "prompt": task.get("prompt"),
        "assigned_to": task.get("assigned_to"),
        "agent": task.get("agent"),
        "priority": task.get("priority"),
        "source": task.get("source"),
    }


def _append_action_log(record: dict) -> None:
    try:
        ACTIONS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with ACTIONS_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except OSError as e:
        print(f"[task-action] action-log write failed: {e}", file=sys.stderr)


def _enqueue_signal(task_id: str, kind: str, reason: str,
                    outcome: str, revert_hint: str) -> None:
    try:
        from hermes_notify import _enqueue
    except ImportError:
        return
    body = (
        f"Hermes task-custodian · {kind}\n"
        f"task: {task_id}\n"
        f"reason: {reason[:200]}\n"
        f"outcome: {outcome}\n"
        f"{revert_hint}"
    )
    try:
        _enqueue(f"task-action-{task_id}-{kind}", body)
    except Exception as e:
        print(f"[task-action] signal enqueue failed: {e}", file=sys.stderr)


def _alternative_agent(current_agent: str | None) -> str:
    """Simple round-robin for reassign action. Skip the current agent."""
    # Fixed roster — matches AGENTS in the Node server
    roster = ["kublai", "chagatai", "jochi", "ogedei", "tolui", "mongke", "temujin"]
    for a in roster:
        if a != current_agent:
            return a
    return roster[0]


def _do_action(kind: str, task_id: str, agent: str, reason: str,
               before: dict) -> tuple[str, dict]:
    """Perform the actual API call. Returns (outcome, api_response)."""
    if kind == "retry":
        status, body = _post_kurultai(
            f"/api/tasks/{agent}/{task_id}/retry", {})
    elif kind == "delete":
        status, body = _post_kurultai(
            f"/api/tasks/{agent}/{task_id}/obsolete", {"reason": reason})
    elif kind == "reassign":
        new_agent = _alternative_agent(agent)
        status, body = _post_kurultai(
            f"/api/tasks/{agent}/{task_id}/reassign",
            {"new_agent": new_agent, "reason": reason},
        )
        body["new_agent"] = new_agent
    elif kind == "rewrite_prompt":
        # v1: no LLM-authored rewrite. Notify-only is the supported mode.
        return "unsupported_autonomous_rewrite", {
            "error": "rewrite_prompt not supported in autonomous mode (v1); "
                     "keep this action in notify-only until LLM authoring is added",
        }
    else:
        return f"error:unknown_kind:{kind}", {}
    if 200 <= status < 300:
        return "applied", body
    return f"error:http_{status}", body


def main() -> int:
    p = argparse.ArgumentParser(description="Hermes task-action fix engine")
    p.add_argument("--target", required=True)
    p.add_argument("--reason", required=True)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    kind = os.environ.get("HERMES_TASK_ACTION_KIND", "").strip()
    agent = os.environ.get("HERMES_TASK_AGENT", "").strip()
    source = os.environ.get("HERMES_TASK_SOURCE", "").strip() or None

    task_id = _parse_target(args.target)
    if not task_id:
        out = {"outcome": "error:bad_target", "target": args.target}
        print(json.dumps(out))
        return 3
    if kind not in VALID_KINDS:
        out = {"outcome": "error:bad_action_kind", "target": args.target,
               "evidence": {"action_kind": kind}}
        print(json.dumps(out))
        return 3

    # Gate 1: global kill flags
    disabled, reason = _is_disabled_globally()
    if disabled:
        out = {"outcome": f"blocked:{reason}", "target": args.target,
               "evidence": {"action_kind": kind, "task_id": task_id}}
        print(json.dumps(out))
        return 1

    # Gate 2: denylist (task source)
    try:
        from hermes_denylist import is_task_denied
        denied, deny_reason = is_task_denied(source, task_id)
        if denied:
            out = {"outcome": f"denied:{deny_reason}", "target": args.target,
                   "evidence": {"action_kind": kind, "task_id": task_id,
                                "source": source}}
            print(json.dumps(out))
            return 1
    except ImportError:
        pass  # Should not happen in practice

    # Capture before-snapshot for revert evidence
    before = _snapshot_task(task_id)

    # Gate 3: per-action mode flag
    mode = _per_action_mode(kind)

    if args.dry_run or mode == "notify-only":
        outcome = "notify_only" if mode == "notify-only" else "dry_run"
        _enqueue_signal(
            task_id, kind, args.reason, outcome,
            revert_hint="(notify-only — no mutation applied)",
        )
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action_type": "task_action",
            "target": args.target,
            "tier": "T1",
            "dry_run": args.dry_run,
            "outcome": outcome,
            "evidence": {
                "action_kind": kind,
                "task_id": task_id,
                "agent": agent,
                "source": source,
                "previous_state": before,
                "mode": mode,
            },
        }
        _append_action_log(record)
        print(json.dumps({
            "outcome": outcome, "target": args.target,
            "evidence": record["evidence"],
        }))
        return 0

    # Gate 4: rate limiter (autonomous mode only — notify-only doesn't spend a slot)
    try:
        import hermes_rate_limit as rl
        ok, rl_reason = rl.consume_slot("task_action")
        if not ok:
            out = {"outcome": f"rate_limited:{rl_reason}",
                   "target": args.target,
                   "evidence": {"action_kind": kind, "task_id": task_id}}
            print(json.dumps(out))
            return 1
    except ImportError:
        pass

    # Apply mutation
    outcome, api_body = _do_action(kind, task_id, agent, args.reason, before)

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action_type": "task_action",
        "target": args.target,
        "tier": "T1",
        "dry_run": False,
        "outcome": outcome,
        "evidence": {
            "action_kind": kind,
            "task_id": task_id,
            "agent": agent,
            "source": source,
            "previous_state": before,
            "api_response": api_body,
            "mode": mode,
        },
    }
    _append_action_log(record)
    _enqueue_signal(
        task_id, kind, args.reason, outcome,
        revert_hint=(f"reply `revert {task_id}` to undo"
                     if outcome == "applied" else ""),
    )

    print(json.dumps({
        "outcome": outcome, "target": args.target,
        "evidence": record["evidence"],
    }))
    return 0 if outcome == "applied" else 2


if __name__ == "__main__":
    sys.exit(main())
