#!/usr/bin/env python3
"""Daily cron wrapper for the horde_review sweep.

Rotates through the configured scope list (one per day), runs
horde_review on that scope via hermes_sweep_runner, posts a digest
Signal DM summarizing the outcome.

Config: ~/.openclaw/config/hermes_daily_review_scopes.json
State:  ~/.openclaw/state/hermes_daily_review_last.json

Idempotent per-day: if already ran today, skips with exit 0.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

CONFIG_PATH = Path.home() / ".openclaw" / "config" / "hermes_daily_review_scopes.json"
STATE_PATH = Path.home() / ".openclaw" / "state" / "hermes_daily_review_last.json"
SWEEP_RUNNER = Path(__file__).resolve().parent / "hermes_sweep_runner.py"
RUN_TIMEOUT_SECS = 1800  # 30 min max for a full review + apply loop


def _today() -> str:
    return datetime.now().astimezone().date().isoformat()


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise RuntimeError(f"config missing: {CONFIG_PATH}")
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"last_run_date": None, "last_scope_idx": -1}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def pick_next_scope(config: dict, state: dict) -> tuple[dict, int]:
    """Round-robin: advance the index. Returns (scope_dict, idx)."""
    scopes = config.get("scopes", [])
    if not scopes:
        raise RuntimeError("config has no scopes")
    last_idx = state.get("last_scope_idx")
    # Treat None / missing as -1 so first run picks 0. Don't use `or`
    # because 0 is falsy and would incorrectly wrap to 0 again.
    if last_idx is None:
        last_idx = -1
    next_idx = (last_idx + 1) % len(scopes)
    return scopes[next_idx], next_idx


def run_review(scope: dict) -> dict:
    """Invoke hermes_sweep_runner for the given scope; parse JSON output."""
    args = [
        "python3", str(SWEEP_RUNNER),
        "--sweep", "horde_review",
        "--scope", scope["path"],
    ]
    if scope.get("mode_override"):
        args += ["--mode", scope["mode_override"]]
    try:
        out = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=RUN_TIMEOUT_SECS,
        )
    except subprocess.TimeoutExpired:
        return {"outcome": "TIMEOUT", "scope": scope["path"]}
    try:
        return json.loads(out.stdout)
    except (json.JSONDecodeError, ValueError):
        return {
            "outcome": "RUNNER_ERROR",
            "scope": scope["path"],
            "stdout_tail": out.stdout[-500:],
            "stderr_tail": out.stderr[-500:],
        }


def post_digest(scope: dict, result: dict) -> None:
    """Queue a Signal DM summarizing the review. Non-fatal on error."""
    try:
        from hermes_notify import _enqueue
    except Exception as e:
        print(f"[daily_review] hermes_notify import failed: {e}", file=sys.stderr)
        return

    applied = [a for a in result.get("actions", []) if a.get("action") == "apply"]
    notified = [a for a in result.get("actions", []) if a.get("action") == "notify-only"]
    outcome = result.get("outcome", "?")

    body_lines = [
        f"Hermes daily review — {scope['name']}",
        f"Scope: {scope['path']}",
        f"Mode: {result.get('mode', '?')}",
        f"Outcome: {outcome}",
        f"Candidates found: {result.get('candidates_found', 0)}",
    ]
    if applied:
        body_lines.append(f"Applied: {len(applied)}")
    if notified:
        body_lines.append(f"Notified-only: {len(notified)}")
    if outcome in ("RUNNER_ERROR", "TIMEOUT"):
        body_lines.append("(see logs for diagnostic detail)")
    body_lines.append("")
    body_lines.append("Reply `revert all today` via Signal to undo any commits.")

    body = "\n".join(body_lines)
    try:
        _enqueue(f"daily-review-{_today()}", body)
    except Exception as e:
        print(f"[daily_review] digest enqueue failed: {e}", file=sys.stderr)


def main() -> int:
    # Idempotency: if already ran today, skip
    state = load_state()
    if state.get("last_run_date") == _today():
        print(json.dumps({
            "outcome": "skipped_already_ran_today",
            "last_run_date": state["last_run_date"],
            "last_scope_idx": state.get("last_scope_idx"),
        }, indent=2))
        return 0

    config = load_config()
    scope, idx = pick_next_scope(config, state)
    result = run_review(scope)
    post_digest(scope, result)

    # Persist state AFTER the review (so if the review crashes, we
    # won't skip it next invocation — operator can re-run manually)
    state.update({"last_run_date": _today(), "last_scope_idx": idx})
    save_state(state)

    print(json.dumps({
        "scope": scope,
        "scope_idx": idx,
        "result": result,
    }, indent=2, default=str))

    outcome = result.get("outcome")
    # Successful outcomes: "ok" (autonomous), "dry_run" (edge case)
    if outcome in ("ok", "dry_run"):
        return 0
    # Gate-stopped outcomes aren't errors — just report them
    if outcome and outcome.startswith("DISABLED_BY"):
        return 0
    # SCOPE_REQUIRED means the scope was missing — shouldn't happen here
    # but treat as a config error
    return 1


if __name__ == "__main__":
    sys.exit(main())
