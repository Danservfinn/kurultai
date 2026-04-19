"""Knowledge-stale sweep plugin.

Audits ~/.openclaw/agents/main/knowledge/ for markdown docs whose mtime
is older than 90 days. For each, produces a sweep candidate requesting
an LLM-driven refresh.

Reuses the detection logic from hermes-watchdog.check_knowledge_stale
philosophically, but directly rather than by re-running that check.
"""

from __future__ import annotations

import time
from pathlib import Path

KNOWLEDGE_DIR = Path.home() / ".openclaw" / "agents" / "main" / "knowledge"
STALE_DAYS = 90


def audit() -> list[dict]:
    """Return a list of candidate {target, reason, autonomy_level} dicts."""
    if not KNOWLEDGE_DIR.exists():
        return []
    cutoff = time.time() - STALE_DAYS * 86400
    candidates: list[dict] = []
    for md in KNOWLEDGE_DIR.rglob("*.md"):
        try:
            mtime = md.stat().st_mtime
        except OSError:
            continue
        if mtime < cutoff:
            age_days = int((time.time() - mtime) / 86400)
            candidates.append({
                "target": str(md),
                "reason": (
                    f"Knowledge doc is {age_days}d old (threshold {STALE_DAYS}d). "
                    "Review for accuracy against current system behavior; "
                    "update sections that no longer match. Keep tone + structure."
                ),
                "autonomy_level": "content",
            })
    # Sort by staleness (oldest first)
    candidates.sort(key=lambda c: -int(c["reason"].split("d old")[0].split(" ")[-1]))
    return candidates


def describe() -> str:
    return f"Flag knowledge docs older than {STALE_DAYS} days for LLM refresh."
