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
              dry_run: bool = False, mode_override: str | None = None) -> dict:
    """Run one sweep end-to-end.

    dry_run: return candidates WITHOUT enqueueing or applying anything.
    mode_override: force 'autonomous' | 'notify-only' instead of reading
                   the mode flag. Use from cron when the operator has
                   graduated a sweep.
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

    # Load plugin
    try:
        plugin = _load_plugin(reg["module"])
    except RuntimeError as e:
        return {"outcome": "PLUGIN_LOAD_FAILED", "reason": str(e)}

    # Audit
    try:
        candidates = plugin.audit()
    except Exception as e:
        return {"outcome": "AUDIT_FAILED", "reason": str(e)[:400]}

    candidates = candidates[:max_proposals]
    result: dict = {
        "sweep": sweep_name,
        "mode": mode,
        "autonomy_level": autonomy_level,
        "candidates_found": len(candidates),
        "actions": [],
    }

    if dry_run:
        result["outcome"] = "dry_run"
        result["candidates"] = candidates
        return result

    for cand in candidates:
        target = cand["target"]
        reason = cand["reason"]
        if mode == "notify-only":
            _notify_sweep_candidate(sweep_name, target, reason, autonomy_level)
            result["actions"].append({
                "target": target, "action": "notify-only",
            })
        else:
            outcome = _apply_candidate(sweep_name, target, reason, autonomy_level)
            result["actions"].append({
                "target": target, "action": "apply", "outcome": outcome,
            })

    result["outcome"] = "ok"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Hermes sweep runner")
    parser.add_argument("--sweep", required=True,
                        choices=list(REGISTERED_SWEEPS.keys()))
    parser.add_argument("--max", type=int, default=DEFAULT_MAX_PROPOSALS)
    parser.add_argument("--dry-run", action="store_true",
                        help="Return audit candidates without acting on them")
    parser.add_argument("--mode", choices=["autonomous", "notify-only"],
                        help="Override the sweep's mode flag for this run")
    args = parser.parse_args()

    result = run_sweep(args.sweep, max_proposals=args.max,
                       dry_run=args.dry_run, mode_override=args.mode)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("outcome") in ("ok", "dry_run") else 1


if __name__ == "__main__":
    sys.exit(main())
