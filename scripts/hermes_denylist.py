#!/usr/bin/env python3
"""Hermes denylist: paths Hermes may NEVER modify autonomously.

Enforced at two layers:
  1. Authoring (refuses to submit a patch targeting denylisted paths)
  2. Apply (refuses to apply a patch targeting denylisted paths — even if
     authoring was somehow bypassed)

Both layers canonicalize the path with os.path.realpath() before matching,
so symlinks cannot smuggle denylisted targets in under an innocuous name.

An override flag exists for the one-shot Phase 5.3 dedup-gap bootstrap against
hermes-watchdog.py. Without the flag, even hermes-watchdog.py is denied.
"""

import os
import tempfile
from pathlib import Path

HOME = Path.home()


def _fs_is_case_insensitive() -> bool:
    """Detect whether the filesystem is case-insensitive (macOS APFS default).

    Creates a tempfile and checks whether its upper/lower-cased path refers
    to the same file. Fail-open to False (case-sensitive comparison) on any
    error — that's the stricter behavior, which is safer.
    """
    try:
        with tempfile.NamedTemporaryFile(
            prefix="hermes_case_test_",
            suffix=".tmp",
            delete=True,
        ) as f:
            lower = f.name.lower()
            upper = f.name.upper()
            if lower == upper:
                return False  # nothing to compare
            try:
                return os.path.samefile(lower, upper)
            except OSError:
                return False
    except OSError:
        return False


_CASE_INSENSITIVE_FS = _fs_is_case_insensitive()


def _norm(path_str: str) -> str:
    """Normalize a path for denylist comparison.

    On case-insensitive filesystems (APFS default, HFS+), all comparisons
    are done in lowercase to prevent bypass via case variation.
    """
    return path_str.lower() if _CASE_INSENSITIVE_FS else path_str

# Absolute canonical path prefixes — any descendant is denied.
# The resolved target path must either equal one of these prefixes exactly,
# or start with prefix + "/". This catches symlinks because realpath()
# canonicalizes before the match.
DENIED_PREFIXES = tuple(str(HOME / suffix) for suffix in [
    # Hermes's own scripts (hard self-modification prevention).
    # Each script that is part of the Hermes subsystem is listed individually
    # so that adjacent non-Hermes files in the same dir remain writable.
    ".openclaw/agents/main/scripts/hermes-watchdog.py",
    ".openclaw/agents/main/scripts/hermes_auto_fix.py",
    ".openclaw/agents/main/scripts/hermes-proposal-submit.py",
    ".openclaw/agents/main/scripts/hermes-reflection.py",
    ".openclaw/agents/main/scripts/hermes-improvement-scan.py",
    ".openclaw/agents/main/scripts/hermes_fix_engine.py",
    ".openclaw/agents/main/scripts/hermes-fix-runner.py",
    ".openclaw/agents/main/scripts/hermes-fix-content.py",
    ".openclaw/agents/main/scripts/hermes-fix-code.py",
    ".openclaw/agents/main/scripts/hermes_denylist.py",
    ".openclaw/agents/main/scripts/hermes_sanitize.py",
    ".openclaw/agents/main/scripts/hermes_commit.py",
    ".openclaw/agents/main/scripts/hermes_precommit_validator.py",
    ".openclaw/agents/main/scripts/hermes_notify.py",
    ".openclaw/agents/main/scripts/hermes_rate_limit.py",
    ".openclaw/agents/main/scripts/hermes_circuit_breaker.py",
    ".openclaw/agents/main/scripts/hermes_sweep_runner.py",
    ".openclaw/agents/main/scripts/hermes_revert_handler.py",
    ".openclaw/agents/main/scripts/hermes_sweep_knowledge.py",
    ".openclaw/agents/main/scripts/hermes_sweep_dedup.py",
    ".openclaw/agents/main/scripts/hermes_sweep_bare_except.py",
    ".openclaw/agents/main/scripts/hermes-fix-log.py",
    ".openclaw/agents/main/scripts/hermes_metrics.py",
    ".openclaw/agents/main/scripts/hermes-panic-stop.sh",
    ".openclaw/agents/main/scripts/hermes-resume.sh",
    # Integrity manifest & Hermes workspace
    ".openclaw/agents/hermes/import-manifest.json",
    ".openclaw/agents/hermes",  # whole agent dir — no writes to Hermes's own workspace
    # Kill-switch flags (whole dir — any flag file)
    ".openclaw/flags",
    # Credentials
    ".openclaw/credentials",
    ".claude/credentials.json",
    # Single-writer boundaries
    ".openclaw/agents/main/scripts/task-reaper.py",
    # Kurultai voting pipeline (separate system; Hermes stays out)
    ".openclaw/agents/main/scripts/kurultai_voting.py",
    ".openclaw/agents/main/scripts/proposal_generator.py",
    ".openclaw/agents/main/scripts/proposal_approval_handler.py",
    ".openclaw/agents/main/scripts/cast_structured_vote.py",
    ".openclaw/agents/main/scripts/cast_structured_vote_parallel.py",
    ".openclaw/agents/main/scripts/process_approved_to_tasks.py",
    ".openclaw/agents/main/proposals",
    # Signal/notification critical path (Hermes depends on these; don't let
    # a Hermes fix accidentally disable its own notification channel)
    ".openclaw/agents/main/scripts/signal_send.py",
    ".openclaw/agents/main/scripts/signal_jsonrpc_server.py",
    ".openclaw/agents/main/scripts/signal_message_handler.py",
    ".openclaw/agents/main/scripts/notification_queue.py",
])

# Override flag — when present, a specific one-shot sweep may target
# hermes-watchdog.py for dedup-gap fixes. Used during bootstrap only and
# is expected to be removed immediately after.
SELF_MODIFICATION_OVERRIDE_FLAG = HOME / ".openclaw" / "flags" / "hermes-self-modification-override.flag"

_HERMES_WATCHDOG_PATH = str(HOME / ".openclaw" / "agents" / "main" / "scripts" / "hermes-watchdog.py")


def _override_active() -> bool:
    """Return True if the self-modification override flag is present.

    Fail-closed on OSError (override treated as inactive — the safer default).
    """
    try:
        return SELF_MODIFICATION_OVERRIDE_FLAG.exists()
    except OSError:
        return False


def is_denied(target_path: str) -> tuple[bool, str]:
    """Return (is_denied, reason) for a candidate patch target path.

    Canonicalizes via realpath() to defeat symlinks and relative paths.
    On case-insensitive filesystems (macOS APFS/HFS+), comparisons are
    case-folded to prevent bypass via case variation.

    Also matches variant-filename attempts: a path that equals a denylist
    entry with additional suffix (e.g., 'hermes-watchdog.py.new') is
    treated as a denylist match.

    Unresolvable paths are denied (fail-closed).
    """
    try:
        resolved = os.path.realpath(str(Path(target_path).expanduser()))
    except (OSError, ValueError) as e:
        return True, f"unresolvable: {e}"

    resolved_norm = _norm(resolved)

    # Special case: hermes-watchdog.py may be touched ONLY when the override
    # flag is set (Phase 5.3 dedup-gap bootstrap).
    if resolved_norm == _norm(_HERMES_WATCHDOG_PATH):
        if _override_active():
            return False, "self-mod override active — one-shot permitted"
        return True, "hermes-watchdog.py is self-denylisted"
    # Also deny sibling variants like hermes-watchdog.py.new (M2)
    if resolved_norm.startswith(_norm(_HERMES_WATCHDOG_PATH) + "."):
        return True, "hermes-watchdog.py variant is self-denylisted"

    for prefix in DENIED_PREFIXES:
        prefix_norm = _norm(prefix)
        if resolved_norm == prefix_norm or resolved_norm.startswith(prefix_norm + "/"):
            return True, f"denylist prefix: {prefix}"
        # M2: deny variant filenames. If the prefix is a file path (has a
        # recognizable extension), also deny {prefix}.* (e.g., .py.new, .py.bak).
        # Only applies to exact-file entries, not directory prefixes.
        if "." in os.path.basename(prefix):
            if resolved_norm.startswith(prefix_norm + "."):
                return True, f"denylist variant of: {prefix}"
    return False, ""


if __name__ == "__main__":
    # Quick self-test when run directly
    import sys
    test_cases = [
        ("~/.openclaw/agents/main/scripts/hermes-watchdog.py", True),
        # C1 regression: case variation must still match
        ("~/.openclaw/agents/main/scripts/HERMES-WATCHDOG.py", True),
        ("~/.openclaw/agents/main/scripts/Hermes-Watchdog.PY", True),
        # M2 regression: variant filenames must match
        ("~/.openclaw/agents/main/scripts/hermes-watchdog.py.new", True),
        ("~/.openclaw/agents/main/scripts/hermes_auto_fix.py.bak", True),
        ("~/.openclaw/agents/main/knowledge/agent-roster.md", False),
        ("~/.openclaw/flags/any-file.flag", True),
        ("~/.claude/credentials.json", True),
        ("/tmp/ok-to-edit.md", False),
    ]
    print(f"  fs_case_insensitive = {_CASE_INSENSITIVE_FS}")
    failed = 0
    for path, expected in test_cases:
        denied, reason = is_denied(path)
        ok = "✓" if denied == expected else "✗"
        if denied != expected:
            failed += 1
        print(f"  {ok} is_denied({path!r}) = ({denied}, {reason!r})")
    sys.exit(0 if failed == 0 else 1)
