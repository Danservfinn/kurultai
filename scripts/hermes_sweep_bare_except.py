"""Bare-except sweep plugin.

Scans Python files under ~/.openclaw/agents/main/scripts/ (excluding
denylisted paths) for bare `except:` and `except Exception: pass`
patterns, which silently swallow errors and are a known problem class
(install plan Phase 1 fixed the top 5 offenders; this sweep finds the
rest over time).

Produces candidates asking the LLM to replace each pattern with typed
exceptions + logging.
"""

from __future__ import annotations

import re
from pathlib import Path

SCRIPTS_DIR = Path.home() / ".openclaw" / "agents" / "main" / "scripts"

# Patterns indicating silent-swallow
_BARE_EXCEPT_RE = re.compile(r"^\s*except\s*:\s*$", re.MULTILINE)
_EXCEPT_PASS_RE = re.compile(
    r"^\s*except\s+Exception\s*:\s*\n\s*pass\s*$",
    re.MULTILINE,
)

# Cap per run
MAX_CANDIDATES = 3


def _scan_file(path: Path) -> list[tuple[str, int]]:
    """Return list of (pattern_name, line_number) for bare-except matches."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    hits: list[tuple[str, int]] = []
    for m in _BARE_EXCEPT_RE.finditer(text):
        line = text.count("\n", 0, m.start()) + 1
        hits.append(("bare_except", line))
    for m in _EXCEPT_PASS_RE.finditer(text):
        line = text.count("\n", 0, m.start()) + 1
        hits.append(("except_pass", line))
    return hits


def audit() -> list[dict]:
    from hermes_denylist import is_denied
    candidates: list[dict] = []
    if not SCRIPTS_DIR.exists():
        return []
    for py_file in sorted(SCRIPTS_DIR.glob("*.py")):
        if len(candidates) >= MAX_CANDIDATES:
            break
        denied, _ = is_denied(str(py_file))
        if denied:
            continue
        hits = _scan_file(py_file)
        if not hits:
            continue
        sites_desc = ", ".join(
            f"line {ln} ({kind})" for kind, ln in hits[:5]
        )
        candidates.append({
            "target": str(py_file),
            "reason": (
                f"Found {len(hits)} bare-except / except-pass pattern(s): "
                f"{sites_desc}"
                f"{' (and more)' if len(hits) > 5 else ''}. "
                "Replace each with a typed-exception catch that logs "
                "the error via the module's existing logger. If no logger "
                "is available, use logging.getLogger(__name__). Preserve "
                "the intent of the original code. Pick narrow exception "
                "types based on the operation inside the try block."
            ),
            "autonomy_level": "code",
        })
    return candidates


def describe() -> str:
    return ("Scan scripts for bare 'except:' / 'except Exception: pass' "
            "and propose typed-exception replacements with logging.")
