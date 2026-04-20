#!/usr/bin/env python3
"""Hermes scheduled improvement sweeps.

Each sweep is a plugin exposing two functions:
  - audit() -> list[{'target': path, 'reason': str, 'autonomy_level': 'content'|'code'}]
  - (optional) describe() -> str   # human-readable sweep description

The runner:
  1. Checks per-capability flags (sweep-disabled, plus the per-sweep
     'hermes-sweep-{name}-disabled.flag' and the per-sweep mode flag
     'hermes-sweep-{name}-mode.flag' — contents 'autonomous' | 'notify-only').
  2. Calls the plugin's audit().
  3. Caps at max_proposals (default 3).
  4. For each candidate:
       - notify-only mode: enqueue a DM describing what WOULD happen
       - autonomous mode: invoke hermes-fix-content.py or hermes-fix-code.py

Registered sweeps:
  knowledge_stale → content
  dedup_gap       → code (dogfood — review finding #1)
  bare_except     → code

Usage:
    python3 hermes_sweep_runner.py --sweep knowledge_stale
    python3 hermes_sweep_runner.py --sweep dedup_gap --max 2 --dry-run

All sweeps default to notify-only mode until their mode flag is explicitly
flipped to 'autonomous' (Phase 9.4 activation).
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

FLAGS_DIR = Path.home() / ".openclaw" / "flags"
SWEEP_DISABLED_FLAG = FLAGS_DIR / "hermes-autonomous-sweep-disabled.flag"
DEFAULT_MAX_PROPOSALS = 3

# Streaming mode emits JSON-line progress events to stdout during a run
# instead of printing the final JSON at the end. The dashboard tails
# these via SSE so the operator can see live progress during long
# horde-review sessions. Activated by --stream CLI flag.
_STREAM_MODE = False


def _emit(event_type: str, **kwargs) -> None:
    """Emit a JSON-line progress event to stdout, flushed immediately."""
    if not _STREAM_MODE:
        return
    payload = {"type": event_type}
    payload.update(kwargs)
    try:
        import time
        payload.setdefault("ts", time.time())
        print(json.dumps(payload), flush=True)
    except (OSError, BrokenPipeError):
        pass

REVIEW_CYCLES_LOG = Path.home() / ".openclaw" / "logs" / "hermes-review-cycles.jsonl"

# Shared action ledger — the same file hermes_auto_fix.py has always
# written to, which the Daily Summary + improvement-scan tools read.
# Sweep runs append a summary row here so the dashboard's summary card
# sees cron/ad-hoc sweep activity (not just legacy auto-fix entries).
HERMES_ACTIONS_LOG = Path.home() / ".openclaw" / "agents" / "main" / "logs" / "hermes-actions.jsonl"


def _log_sweep_action(result: dict) -> None:
    """Append a summary row for a completed sweep run to hermes-actions.jsonl.

    One row per run, not per candidate — the Daily Summary aggregator
    digests these to produce the plain-English narrative. Per-candidate
    detail is still available via the evidence.actions array.

    Non-fatal on IO error (logging must never break the sweep itself).
    """
    from datetime import datetime, timezone
    try:
        HERMES_ACTIONS_LOG.parent.mkdir(parents=True, exist_ok=True)
        actions = result.get("actions", []) or []
        applied = [a for a in actions if a.get("action") == "apply"]
        notified = [a for a in actions if a.get("action") == "notify-only"]
        applied_ok = [
            a for a in applied
            if isinstance(a.get("outcome"), dict)
            and a["outcome"].get("outcome") == "applied"
        ]
        commit_shas = [
            (a.get("outcome") or {}).get("commit_sha") or
            ((a.get("outcome") or {}).get("evidence") or {}).get("commit_sha")
            for a in applied_ok
            if isinstance(a.get("outcome"), dict)
        ]
        sweep = result.get("sweep") or "?"
        mode = result.get("mode") or "?"
        outcome = result.get("outcome") or "?"
        # Map sweep outcome → action_type + top-line outcome the summary
        # aggregator will render. Keep the action_type prefixed so the
        # old auto-fix rows stay distinguishable.
        if outcome in ("dry_run",):
            top_outcome = "dry_run"
        elif outcome == "ok":
            if applied_ok:
                top_outcome = "applied"
            elif notified:
                top_outcome = "notified"
            else:
                top_outcome = "no_candidates"
        else:
            top_outcome = outcome
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action_type": f"sweep_{sweep}",
            "target": result.get("scope") or f"sweep:{sweep}",
            "tier": "T1",
            "dry_run": outcome == "dry_run",
            "outcome": top_outcome,
            "evidence": {
                "sweep": sweep,
                "mode": mode,
                "scope": result.get("scope"),
                "candidates_found": result.get("candidates_found", 0),
                "applied_count": len(applied_ok),
                "notified_count": len(notified),
                "commit_shas": [s for s in commit_shas if s],
            },
        }
        with HERMES_ACTIONS_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except OSError as e:
        print(f"[sweep_runner] hermes-actions log write failed: {e}", file=sys.stderr)


def _log_review_cycle(result: dict) -> None:
    """Append a review-cycle record to the cycles JSONL for operator
    browsing + per-cycle revert. Non-fatal on IO error.

    The record includes the timestamp, scope, mode, outcome, and for
    every applied fix, the resulting commit SHA (extracted from the
    per-candidate outcome dict). That lets the dashboard render a
    cycle-log table with a Revert button that iterates over the
    stored commit SHAs.
    """
    import uuid
    from datetime import datetime, timezone
    try:
        REVIEW_CYCLES_LOG.parent.mkdir(parents=True, exist_ok=True)
        applied = []
        notified = []
        for a in result.get("actions", []) or []:
            if a.get("action") == "apply":
                outcome = a.get("outcome") or {}
                applied.append({
                    "target": a.get("target"),
                    "autonomy_level": a.get("autonomy_level"),
                    "outcome": outcome.get("outcome") if isinstance(outcome, dict) else str(outcome),
                    "commit_sha": (
                        outcome.get("commit_sha") or
                        (outcome.get("evidence") or {}).get("commit_sha")
                    ) if isinstance(outcome, dict) else None,
                })
            elif a.get("action") == "notify-only":
                notified.append({
                    "target": a.get("target"),
                    "autonomy_level": a.get("autonomy_level"),
                })
        record = {
            "cycle_id": "cycle-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6],
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "sweep": result.get("sweep"),
            "scope": result.get("scope"),
            "mode": result.get("mode"),
            "outcome": result.get("outcome"),
            "candidates_found": result.get("candidates_found", 0),
            "applied": applied,
            "notified": notified,
        }
        with REVIEW_CYCLES_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except OSError as e:
        print(f"[sweep_runner] review-cycle log write failed: {e}", file=sys.stderr)

REGISTERED_SWEEPS: dict[str, dict] = {
    "knowledge_stale": {
        "autonomy_level": "content",
        "module": "hermes_sweep_knowledge",
    },
    "dedup_gap": {
        "autonomy_level": "code",
        "module": "hermes_sweep_dedup",
    },
    "bare_except": {
        "autonomy_level": "code",
        "module": "hermes_sweep_bare_except",
    },
    "horde_review": {
        # Plugin sets autonomy_level per-candidate (code vs content);
        # this registry default is used as a fallback only.
        "autonomy_level": "content",
        "module": "hermes_sweep_horde_review",
        "requires_scope": True,
    },
}


def _sweep_disabled_flag(sweep_name: str) -> Path:
    return FLAGS_DIR / f"hermes-sweep-{sweep_name}-disabled.flag"


def _sweep_mode_flag(sweep_name: str) -> Path:
    return FLAGS_DIR / f"hermes-sweep-{sweep_name}-mode.flag"


def _sweep_mode(sweep_name: str) -> str:
    """Read the per-sweep mode. Defaults to notify-only."""
    flag = _sweep_mode_flag(sweep_name)
    if not flag.exists():
        return "notify-only"
    try:
        content = flag.read_text(encoding="utf-8").strip()
        if content == "autonomous":
            return "autonomous"
    except OSError:
        pass
    return "notify-only"


def _notify_sweep_candidate(sweep: str, target: str, reason: str,
                             autonomy_level: str) -> None:
    """Queue a DM describing what a fix WOULD do (notify-only mode)."""
    try:
        from hermes_notify import _enqueue, _operator_phone
        msg = (
            f"Hermes sweep '{sweep}' (notify-only) found a candidate:\n\n"
            f"Target: {target}\n"
            f"Reason: {reason}\n"
            f"Autonomy level: {autonomy_level}\n\n"
            f"No change was made. Flip the mode flag to 'autonomous' to enable."
        )
        _enqueue(f"sweep-{sweep}-{uuid.uuid4().hex[:8]}", msg)
    except Exception as e:
        print(f"notify-only enqueue failed: {e}", file=sys.stderr)


def _apply_candidate(sweep: str, target: str, reason: str,
                     autonomy_level: str) -> dict:
    """Invoke the appropriate authoring script for a candidate."""
    script_name = f"hermes-fix-{autonomy_level}.py"
    script_path = Path(__file__).resolve().parent / script_name
    if not script_path.exists():
        return {"outcome": "SCRIPT_MISSING", "target": target}
    try:
        result = subprocess.run(
            ["python3", str(script_path),
             "--target", target, "--reason", reason],
            capture_output=True, text=True, timeout=600,
        )
    except subprocess.TimeoutExpired:
        return {"outcome": "AUTHOR_TIMEOUT", "target": target}
    try:
        return json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        return {
            "outcome": f"AUTHOR_RC_{result.returncode}",
            "target": target,
            "stdout": result.stdout[:400],
            "stderr": result.stderr[:400],
        }


def _load_plugin(module_name: str):
    """Import a sweep plugin module. Returns the imported module or raises."""
    try:
        return importlib.import_module(module_name)
    except ImportError as e:
        raise RuntimeError(f"sweep plugin '{module_name}' not importable: {e}") from e


def run_sweep(sweep_name: str, max_proposals: int = DEFAULT_MAX_PROPOSALS,
              dry_run: bool = False, mode_override: str | None = None,
              scope: str | None = None) -> dict:
    """Run one sweep end-to-end.

    dry_run: return candidates WITHOUT enqueueing or applying anything.
    mode_override: force 'autonomous' | 'notify-only' instead of reading
                   the mode flag. Use from cron when the operator has
                   graduated a sweep.
    scope: directory path passed to the plugin via HERMES_SWEEP_SCOPE
           env var. Required when reg["requires_scope"] is True
           (currently only horde_review).
    """
    if sweep_name not in REGISTERED_SWEEPS:
        return {"outcome": "UNKNOWN_SWEEP", "sweep": sweep_name}

    # Master sweep flag
    if SWEEP_DISABLED_FLAG.exists():
        return {"outcome": "DISABLED_BY_MASTER_FLAG"}

    # Per-sweep disabled
    if _sweep_disabled_flag(sweep_name).exists():
        return {"outcome": f"DISABLED_BY_SWEEP_FLAG", "sweep": sweep_name}

    reg = REGISTERED_SWEEPS[sweep_name]
    autonomy_level = reg["autonomy_level"]
    mode = mode_override or _sweep_mode(sweep_name)

    # Scope requirement check
    if reg.get("requires_scope") and not scope:
        return {
            "outcome": "SCOPE_REQUIRED",
            "sweep": sweep_name,
            "reason": f"{sweep_name} requires --scope argument",
        }

    # Thread scope through env var (plugin reads it). Scoped so we
    # don't pollute the parent process's env on subsequent calls.
    prev_scope = os.environ.get("HERMES_SWEEP_SCOPE")
    if scope:
        os.environ["HERMES_SWEEP_SCOPE"] = scope

    _emit("sweep_start", sweep=sweep_name, scope=scope, mode=mode, dry_run=dry_run)

    try:
        # Load plugin
        try:
            plugin = _load_plugin(reg["module"])
        except RuntimeError as e:
            _emit("sweep_error", stage="plugin_load", reason=str(e))
            err_result = {
                "sweep": sweep_name, "scope": scope, "mode": mode,
                "outcome": "PLUGIN_LOAD_FAILED", "reason": str(e), "actions": [],
            }
            _log_sweep_action(err_result)
            return err_result

        # Audit
        _emit("audit_start", sweep=sweep_name, scope=scope)
        try:
            candidates = plugin.audit()
        except Exception as e:
            _emit("sweep_error", stage="audit", reason=str(e)[:400])
            err_result = {
                "sweep": sweep_name, "scope": scope, "mode": mode,
                "outcome": "AUDIT_FAILED", "reason": str(e)[:400], "actions": [],
            }
            _log_sweep_action(err_result)
            return err_result

        candidates = candidates[:max_proposals]
        _emit("audit_done", candidates_found=len(candidates),
              candidates=[{"target": c.get("target"), "reason": c.get("reason", "")[:200],
                           "autonomy_level": c.get("autonomy_level", autonomy_level)}
                          for c in candidates])
        result: dict = {
            "sweep": sweep_name,
            "mode": mode,
            "autonomy_level": autonomy_level,
            "scope": scope,
            "candidates_found": len(candidates),
            "actions": [],
        }

        if dry_run:
            result["outcome"] = "dry_run"
            result["candidates"] = candidates
            _log_sweep_action(result)
            _emit("final", result=result)
            return result

        for i, cand in enumerate(candidates):
            target = cand["target"]
            reason = cand["reason"]
            # Allow per-candidate autonomy_level override (used by
            # horde_review which mixes code + content findings).
            cand_level = cand.get("autonomy_level", autonomy_level)
            if mode == "notify-only":
                _emit("candidate_notify", idx=i, target=target,
                      autonomy_level=cand_level)
                _notify_sweep_candidate(sweep_name, target, reason, cand_level)
                result["actions"].append({
                    "target": target, "action": "notify-only",
                    "autonomy_level": cand_level,
                })
            else:
                _emit("apply_start", idx=i, target=target,
                      autonomy_level=cand_level, reason=reason[:200])
                outcome = _apply_candidate(sweep_name, target, reason, cand_level)
                _emit("apply_done", idx=i, target=target,
                      outcome=outcome.get("outcome") if isinstance(outcome, dict) else str(outcome),
                      commit_sha=(outcome.get("commit_sha") or
                                  (outcome.get("evidence") or {}).get("commit_sha"))
                                 if isinstance(outcome, dict) else None)
                result["actions"].append({
                    "target": target, "action": "apply",
                    "autonomy_level": cand_level, "outcome": outcome,
                })

        result["outcome"] = "ok"
        # Log review cycles (horde_review only — other sweeps have no
        # cycle concept; they're single-target).
        if sweep_name == "horde_review":
            _log_review_cycle(result)
        # Every sweep run appends one summary row to hermes-actions.jsonl
        # so the Daily Summary card picks it up.
        _log_sweep_action(result)
        _emit("final", result=result)
        return result
    finally:
        # Restore env var so concurrent/subsequent sweep runs don't
        # inherit this scope.
        if scope:
            if prev_scope is None:
                os.environ.pop("HERMES_SWEEP_SCOPE", None)
            else:
                os.environ["HERMES_SWEEP_SCOPE"] = prev_scope


def main() -> int:
    parser = argparse.ArgumentParser(description="Hermes sweep runner")
    parser.add_argument("--sweep", required=True,
                        choices=list(REGISTERED_SWEEPS.keys()))
    parser.add_argument("--max", type=int, default=DEFAULT_MAX_PROPOSALS)
    parser.add_argument("--dry-run", action="store_true",
                        help="Return audit candidates without acting on them")
    parser.add_argument("--mode", choices=["autonomous", "notify-only"],
                        help="Override the sweep's mode flag for this run")
    parser.add_argument("--scope",
                        help="Absolute directory path (required for "
                             "sweeps with requires_scope=True, e.g. horde_review)")
    parser.add_argument("--stream", action="store_true",
                        help="Emit JSON-line progress events to stdout instead "
                             "of a single JSON blob at the end. Used by the "
                             "dashboard SSE endpoint for live progress.")
    args = parser.parse_args()

    global _STREAM_MODE
    if args.stream:
        _STREAM_MODE = True

    result = run_sweep(args.sweep, max_proposals=args.max,
                       dry_run=args.dry_run, mode_override=args.mode,
                       scope=args.scope)
    # Non-streaming mode prints the final JSON; streaming mode has
    # already emitted the `final` event and should not duplicate.
    if not _STREAM_MODE:
        print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("outcome") in ("ok", "dry_run") else 1


if __name__ == "__main__":
    sys.exit(main())
