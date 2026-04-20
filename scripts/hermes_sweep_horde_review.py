#!/usr/bin/env python3
"""horde-review sweep plugin.

Invokes `claude --print` with Skill(horde-review) enabled on a scoped
directory, parses findings into sweep candidates. Each finding with
severity >= Medium becomes a {target, reason, autonomy_level} candidate
routed through the normal fix engine (same as the other sweeps).

Scope is passed via the HERMES_SWEEP_SCOPE env var. run_sweep sets
this from its --scope CLI flag.

The plugin contract matches the other sweeps in this directory:
    audit() -> list[dict]       # sweep_runner calls this
    describe() -> str           # human-readable summary
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

MAX_CANDIDATES = 5
REVIEW_TIMEOUT_SECS = int(os.getenv("HERMES_HORDE_REVIEW_TIMEOUT", "900"))  # 15 min
LLM_CMD = os.getenv("HERMES_LLM_CMD", "claude")

_FINDINGS_PREFIX = "HERMES_FINDINGS="
_SEVERITY_ACCEPT = {"medium", "high", "critical"}


def _build_prompt(scope: str) -> str:
    """System prompt for the review invocation."""
    return (
        f"You are running a codebase review on the directory:\n\n"
        f"    {scope}\n\n"
        f"Invoke the horde-review skill to dispatch multi-agent analysis. "
        f"Focus on: security vulnerabilities, correctness bugs, and "
        f"simplification opportunities. Skip purely stylistic nits.\n\n"
        f"Do NOT propose changes to any file under:\n"
        f"  - ~/.openclaw/agents/main/scripts/hermes*.py\n"
        f"  - ~/.openclaw/agents/hermes/\n"
        f"These are denylisted; any proposal targeting them will be "
        f"rejected, so don't waste tokens on them.\n\n"
        f"When you finish the review, output your findings as a single "
        f"line starting with '{_FINDINGS_PREFIX}' followed by a JSON "
        f"array. Each item must have this exact shape:\n"
        f"  {{\n"
        f'    "severity": "critical" | "high" | "medium" | "low",\n'
        f'    "title": "<short summary, <= 80 chars>",\n'
        f'    "target": "<absolute path to the file to fix>",\n'
        f'    "autonomy_level": "code" | "content",\n'
        f'    "fix_description": "<1-2 sentences describing the fix>"\n'
        f"  }}\n\n"
        f"Cap the array at the {MAX_CANDIDATES} most important findings "
        f"(severity >= medium). If you find fewer, that's fine. If you "
        f"find zero real issues, output {_FINDINGS_PREFIX}[]\n"
    )


def _extract_findings(llm_output: str) -> list[dict]:
    """Scan stdout for the HERMES_FINDINGS= line + parse JSON."""
    # Search each line; pick the last one that starts with the prefix
    # (in case the agent emitted multiple trial lines)
    last_match = None
    for line in llm_output.splitlines():
        line = line.strip()
        if line.startswith(_FINDINGS_PREFIX):
            last_match = line[len(_FINDINGS_PREFIX):].strip()
    if not last_match:
        return []
    try:
        parsed = json.loads(last_match)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [f for f in parsed if isinstance(f, dict)]


def _run_review(scope: str) -> list[dict]:
    """Spawn claude with horde-review + read-only tools on scope.

    Returns findings (possibly empty list). Never raises; on failure
    returns [] and lets the audit function surface an empty result.
    """
    prompt = _build_prompt(scope)
    args = [
        LLM_CMD,
        "--print",
        "--verbose",
        "--output-format", "stream-json",
        "--include-partial-messages",
        "--allowedTools", "Skill", "Read", "Grep", "Glob", "Task",
        "--disallowedTools", "Bash", "Edit", "Write", "NotebookEdit",
        "--add-dir", scope,
    ]
    try:
        result = subprocess.run(
            args,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=REVIEW_TIMEOUT_SECS,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f"[horde_review] LLM invocation failed: {e}", file=sys.stderr)
        return []

    if result.returncode != 0:
        print(
            f"[horde_review] claude returned rc={result.returncode}; "
            f"stderr tail: {result.stderr[-400:]}",
            file=sys.stderr,
        )
        return []

    # stream-json output: the final "result" event has .result = full text
    final_text = ""
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        if evt.get("type") == "result":
            final_text = evt.get("result", "") or final_text
        # Also capture from assistant message content blocks as a fallback
        if evt.get("type") == "assistant":
            for block in evt.get("message", {}).get("content", []):
                if block.get("type") == "text":
                    final_text += block.get("text", "")

    return _extract_findings(final_text)


def audit() -> list[dict]:
    """Return sweep candidates. Called by hermes_sweep_runner."""
    from hermes_denylist import is_denied

    scope = os.environ.get("HERMES_SWEEP_SCOPE")
    if not scope:
        raise RuntimeError(
            "horde_review requires HERMES_SWEEP_SCOPE env var "
            "(set by --scope flag on hermes_sweep_runner)"
        )

    findings = _run_review(scope)
    candidates: list[dict] = []

    # Over-fetch then filter down to MAX_CANDIDATES so we don't run
    # out if the first few are denylisted.
    for f in findings[: MAX_CANDIDATES * 3]:
        if len(candidates) >= MAX_CANDIDATES:
            break
        sev = str(f.get("severity", "low")).lower()
        if sev not in _SEVERITY_ACCEPT:
            continue
        target = f.get("target", "")
        if not isinstance(target, str) or not target.startswith("/"):
            continue
        try:
            denied, _reason = is_denied(target)
        except Exception:
            # Fail closed — if denylist check errors, skip the candidate
            continue
        if denied:
            continue
        autonomy = f.get("autonomy_level", "content")
        if autonomy not in ("code", "content"):
            autonomy = "content"
        title = str(f.get("title", "no title"))[:80]
        fix_desc = str(f.get("fix_description", ""))[:400]
        reason = f"[{sev}] {title}: {fix_desc}".strip()[:500]
        candidates.append({
            "target": target,
            "reason": reason,
            "autonomy_level": autonomy,
        })

    return candidates


def describe() -> str:
    return (
        "Multi-agent codebase review via the horde-review skill. "
        "Scope required. Findings at severity >= Medium become fix "
        "candidates (capped at 5 per run)."
    )


if __name__ == "__main__":
    # Manual-run mode for testing — caller must set HERMES_SWEEP_SCOPE
    import argparse
    p = argparse.ArgumentParser(description="horde_review sweep plugin")
    p.add_argument("--scope", required=True, help="Absolute directory to review")
    p.add_argument("--dump-prompt", action="store_true",
                    help="Print the prompt and exit (no LLM call)")
    args = p.parse_args()

    if args.dump_prompt:
        print(_build_prompt(args.scope))
        sys.exit(0)

    os.environ["HERMES_SWEEP_SCOPE"] = args.scope
    try:
        cands = audit()
        print(json.dumps(cands, indent=2))
    finally:
        os.environ.pop("HERMES_SWEEP_SCOPE", None)
