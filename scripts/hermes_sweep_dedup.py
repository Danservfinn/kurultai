"""Dedup-gap sweep plugin — the dogfood sweep.

Scans hermes-watchdog.py for write_hermes_task() callsites that are NOT
preceded by a should_suppress_alert() call within 10 lines (the dedup
pattern we already fixed at one site but deferred at 10+ other sites
during the install plan's review).

Candidates produce a reason that instructs the LLM to wrap each site
with a dedup_key=... parameter. Since hermes-watchdog.py is on the
self-modification denylist, the applier will reject unless
hermes-self-modification-override.flag is present (see docstring).

For the initial bootstrap:
  1. Operator touches ~/.openclaw/flags/hermes-self-modification-override.flag
  2. Operator sets this sweep's mode to 'autonomous'
  3. Run once (either via cron or manual), let the 10 sites get wrapped
  4. Operator removes the override flag immediately
  5. Subsequent runs find no candidates (or produce DIFF_TOO_BIG for
     any late-found callsites, since the override is gone)
"""

from __future__ import annotations

import re
from pathlib import Path

WATCHDOG_PATH = Path.home() / ".openclaw" / "agents" / "main" / "scripts" / "hermes-watchdog.py"


def _unwrapped_sites(source: str) -> list[int]:
    """Return 1-based line numbers where write_hermes_task(
    appears without should_suppress_alert within the prior 10 lines."""
    lines = source.splitlines()
    suppress_lines = {
        i + 1 for i, L in enumerate(lines)
        if "should_suppress_alert" in L
    }
    write_calls: list[int] = []
    for i, L in enumerate(lines):
        # Match the call site, not the def
        if "write_hermes_task(" in L and "def write_hermes_task" not in L:
            ln = i + 1
            # Check for a should_suppress_alert in the preceding 10 lines
            nearby = [s for s in suppress_lines if ln - 10 <= s <= ln]
            if not nearby:
                write_calls.append(ln)
    return write_calls


def audit() -> list[dict]:
    if not WATCHDOG_PATH.exists():
        return []
    try:
        source = WATCHDOG_PATH.read_text(encoding="utf-8")
    except OSError:
        return []
    sites = _unwrapped_sites(source)
    if not sites:
        return []
    return [{
        "target": str(WATCHDOG_PATH),
        "reason": (
            f"Found {len(sites)} unwrapped write_hermes_task() callsites "
            f"at lines: {', '.join(str(ln) for ln in sites[:10])}"
            f"{', and more' if len(sites) > 10 else ''}. "
            "Each needs wrapping with `should_suppress_alert(..., dedup_key=...)` "
            "gating the write_hermes_task() and `record_alert_created(..., dedup_key=...)` "
            "inside the body. Follow the existing pattern at check_quality_gate_drift "
            "(lines 474, 482) — define a stable _key per site, gate accordingly. "
            "Keep diffs minimal and preserve the existing logic exactly."
        ),
        "autonomy_level": "code",
    }]


def describe() -> str:
    return ("Find write_hermes_task() callsites in hermes-watchdog.py "
            "without a nearby should_suppress_alert, propose dedup_key wrapping.")
