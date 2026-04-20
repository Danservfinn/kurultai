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


def _emit_progress(event_type: str, **kwargs) -> None:
    """Forward a progress event through the sweep_runner's _emit if
    streaming is active. Imported lazily to avoid a circular import
    at module load (sweep_runner imports this module dynamically)."""
    try:
        import hermes_sweep_runner
        hermes_sweep_runner._emit(event_type, **kwargs)
    except Exception:
        pass


def _run_review(scope: str) -> list[dict]:
    """Spawn claude with horde-review + read-only tools on scope.

    Returns findings (possibly empty list). Never raises; on failure
    returns [] and lets the audit function surface an empty result.

    When sweep_runner is in --stream mode, intermediate events from
    claude's stream-json output are forwarded as `reviewer_*` progress
    events so the dashboard can render a live log panel.
    """
    import time
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

    _emit_progress("reviewer_spawn", cmd=LLM_CMD, scope=scope)

    try:
        proc = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # line-buffered
        )
    except FileNotFoundError as e:
        _emit_progress("reviewer_error", reason=str(e))
        print(f"[horde_review] LLM invocation failed: {e}", file=sys.stderr)
        return []

    try:
        proc.stdin.write(prompt)
        proc.stdin.close()
    except (OSError, BrokenPipeError):
        pass

    final_text = ""
    deadline = time.time() + REVIEW_TIMEOUT_SECS
    current_tool = None
    stderr_tail: list[str] = []

    # Drain stdout line-by-line as the subprocess runs. Each line is
    # a stream-json event. We route a small summary of each into
    # progress events for the dashboard.
    try:
        while True:
            if time.time() > deadline:
                _emit_progress("reviewer_error", reason="timeout")
                proc.kill()
                break
            line = proc.stdout.readline()
            if not line:
                if proc.poll() is not None:
                    break
                continue
            line = line.strip()
            if not line:
                continue
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                continue

            etype = evt.get("type")

            if etype == "system" and evt.get("subtype") == "init":
                _emit_progress(
                    "reviewer_init",
                    model=evt.get("model"),
                    session_id=evt.get("session_id"),
                )
            elif etype == "stream_event":
                inner = evt.get("event", {}) or {}
                delta = inner.get("delta", {}) or {}
                if delta.get("type") == "text_delta":
                    txt = delta.get("text", "")
                    if txt:
                        _emit_progress("reviewer_delta", text=txt)
                elif delta.get("type") == "input_json_delta":
                    _emit_progress("reviewer_tool_input", partial=delta.get("partial_json", "")[:200])
            elif etype == "assistant":
                msg = evt.get("message", {}) or {}
                for block in msg.get("content", []):
                    btype = block.get("type")
                    if btype == "text":
                        txt = block.get("text", "")
                        if txt:
                            final_text += txt
                            _emit_progress("reviewer_text", text=txt[:500])
                    elif btype == "tool_use":
                        current_tool = block.get("name", "?")
                        _emit_progress(
                            "reviewer_tool_call",
                            tool=current_tool,
                            input_preview=json.dumps(block.get("input", {}), default=str)[:200],
                        )
            elif etype == "user":
                # tool_result messages come back as user-role; summarize
                msg = evt.get("message", {}) or {}
                for block in msg.get("content", []):
                    if block.get("type") == "tool_result":
                        content = block.get("content")
                        preview = ""
                        if isinstance(content, str):
                            preview = content[:200]
                        elif isinstance(content, list) and content:
                            first = content[0]
                            if isinstance(first, dict):
                                preview = str(first.get("text", ""))[:200]
                        _emit_progress(
                            "reviewer_tool_result",
                            tool=current_tool,
                            preview=preview,
                        )
            elif etype == "result":
                result_text = evt.get("result", "") or ""
                if result_text:
                    final_text = result_text
                _emit_progress(
                    "reviewer_result",
                    duration_ms=evt.get("duration_ms"),
                    total_cost_usd=evt.get("total_cost_usd"),
                    num_turns=evt.get("num_turns"),
                )
    except Exception as e:
        _emit_progress("reviewer_error", reason=f"stream_parse: {e!r}"[:400])
    finally:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        if proc.stderr:
            try:
                tail = proc.stderr.read() or ""
                stderr_tail = tail.splitlines()[-6:]
            except Exception:
                pass

    if proc.returncode not in (0, None):
        _emit_progress(
            "reviewer_error",
            reason=f"rc={proc.returncode}",
            stderr_tail="\n".join(stderr_tail)[-400:],
        )
        print(
            f"[horde_review] claude returned rc={proc.returncode}; "
            f"stderr tail: {' | '.join(stderr_tail)}",
            file=sys.stderr,
        )
        return []

    findings = _extract_findings(final_text)
    _emit_progress("reviewer_done", findings_count=len(findings))
    return findings


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
