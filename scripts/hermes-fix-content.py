#!/usr/bin/env python3
"""Hermes content-fix authoring.

Spawns a Claude Code subprocess with a focused prompt, extracts a
unified diff from the output, validates it, and hands off to
hermes_fix_engine.apply_autonomous_fix for the commit + notify flow.

Gates (fail-closed at each):
  - hermes-disabled.flag (global T0)
  - hermes-autonomous-disabled.flag (master autonomous)
  - hermes-autonomous-fix-content-disabled.flag (per-capability)
  - hermes_denylist.is_denied(target)

Usage:
    python3 hermes-fix-content.py --target <path> --reason "<short>"
    python3 hermes-fix-content.py --target <path> --reason "..." --dry-run
    python3 hermes-fix-content.py --spec spec.json   # pre-built fix-job

The --dry-run mode writes the LLM-produced diff to stdout but does not
commit anything — used by sweeps in notify-only mode.

Exit codes:
  0 — fix applied (or dry-run produced valid diff)
  1 — gate blocked, no LLM call made
  2 — LLM produced invalid/empty output
  3 — apply engine rejected (denylist, rate-limit, tests)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

LLM_CMD = os.getenv("HERMES_LLM_CMD", "claude")
LLM_TIMEOUT_SECS = int(os.getenv("HERMES_LLM_TIMEOUT", "300"))
SOURCE_EXCERPT_MAX_BYTES = 8000  # Cap the source we pass to the LLM


def _repo_dir_for_target(target: str) -> str | None:
    """Find the git repo that contains this target, walking up the tree."""
    p = Path(target).expanduser().resolve()
    for ancestor in [p] + list(p.parents):
        if (ancestor / ".git").exists():
            return str(ancestor)
    return None


def _read_source_excerpt(path: Path, max_bytes: int = SOURCE_EXCERPT_MAX_BYTES) -> str:
    """Read the source file, truncate to max_bytes, sanitize injection markers."""
    from hermes_sanitize import sanitize
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        raise RuntimeError(f"cannot read {path}: {e}") from e
    if len(text) > max_bytes:
        # Keep head + tail with marker in between
        half = max_bytes // 2
        text = text[:half] + "\n\n... [TRUNCATED MIDDLE] ...\n\n" + text[-half:]
    return sanitize(text)


def _build_prompt(target_rel: str, reason: str, source_excerpt: str) -> str:
    """Build the focused prompt for Claude Code."""
    return (
        f"You are Hermes, the Kurultai autonomous-improvement agent. "
        f"Produce a MINIMAL unified diff that fixes the stated reason "
        f"for the single file below. Nothing else.\n\n"
        f"Target file (repo-relative): {target_rel}\n"
        f"Reason: {reason}\n\n"
        f"Rules for your output:\n"
        f"- Output ONLY a unified diff (no prose, no ```diff fences, no explanation).\n"
        f"- The diff must have `--- a/{target_rel}` and `+++ b/{target_rel}` headers.\n"
        f"- Keep the change minimal — edit only what the reason requires.\n"
        f"- Do not rewrite the whole file.\n"
        f"- Do not introduce new sections unless the reason says so.\n"
        f"- If the reason does not clearly describe a fix you can produce "
        f"with high confidence, output the single literal line: NO_FIX_POSSIBLE\n\n"
        f"--- Source content (sanitized, possibly truncated) ---\n"
        f"{source_excerpt}\n"
        f"--- End of source ---\n"
    )


def _invoke_llm(prompt: str) -> tuple[int, str, str]:
    """Invoke the Claude Code CLI with --print (one-shot) and capture stdout.

    Returns (returncode, stdout, stderr).
    """
    try:
        result = subprocess.run(
            [LLM_CMD, "--print", prompt],
            capture_output=True, text=True, timeout=LLM_TIMEOUT_SECS,
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return 127, "", f"LLM CLI '{LLM_CMD}' not found on PATH"
    except subprocess.TimeoutExpired:
        return 124, "", f"LLM timeout after {LLM_TIMEOUT_SECS}s"


_DIFF_HEADER_RE = re.compile(
    r"(?m)^---\s+a/(\S+).*?\n\+\+\+\s+b/(\S+)", re.DOTALL,
)


def _extract_diff(llm_output: str, target_rel: str) -> tuple[str | None, str]:
    """Extract a unified diff from LLM output.

    Returns (diff_text, reason).
      diff_text is None if no valid diff was found.
      reason is a short diagnostic.
    """
    text = llm_output.strip()
    if not text:
        return None, "empty output"
    if "NO_FIX_POSSIBLE" in text:
        return None, "LLM declined: NO_FIX_POSSIBLE"

    # Strip fenced code blocks if present (tolerance for LLMs that fence
    # despite our instruction not to)
    fenced = re.match(
        r"```(?:diff|patch)?\n(.*?)\n```",
        text, flags=re.DOTALL,
    )
    if fenced:
        text = fenced.group(1)

    m = _DIFF_HEADER_RE.search(text)
    if not m:
        return None, "no --- a/... +++ b/... headers found"
    a, b = m.group(1), m.group(2)
    if a != target_rel or b != target_rel:
        return None, f"header path mismatch: a={a!r} b={b!r} (expected {target_rel!r})"

    # Find the diff start (first --- a/... line) and return from there
    start = text.find(m.group(0))
    diff_body = text[start:]

    # Normalize trailing newline: git apply rejects diffs that end without \n
    # (unless there's a '\ No newline at end of file' marker). LLMs often
    # omit the trailing \n. Append one if missing.
    if not diff_body.endswith("\n"):
        diff_body = diff_body + "\n"

    return diff_body, "ok"


def _repo_relative(target: str, repo_dir: str) -> str:
    """Convert absolute target to repo-relative path for the diff headers."""
    abs_t = Path(target).expanduser().resolve()
    abs_r = Path(repo_dir).expanduser().resolve()
    try:
        return str(abs_t.relative_to(abs_r))
    except ValueError:
        return str(abs_t)


def author_content_fix(target: str, reason: str, dry_run: bool = False) -> dict:
    """Main entry: author a content fix and apply it (unless --dry-run)."""
    import hermes_auto_fix as haf
    from hermes_denylist import is_denied

    # Gate 1: global + master + per-capability flags
    if haf._check_kill_switch():
        return {"outcome": "DISABLED_BY_KILL_SWITCH"}
    if haf._check_autonomous_disabled():
        return {"outcome": "DISABLED_BY_AUTONOMOUS_FLAG"}
    if haf._check_autonomous_fix_content_disabled():
        return {"outcome": "DISABLED_BY_CONTENT_FLAG"}

    # Gate 2: denylist
    denied, deny_reason = is_denied(target)
    if denied:
        return {"outcome": "DENYLIST_VIOLATION", "reason": deny_reason}

    # Resolve repo
    repo_dir = _repo_dir_for_target(target)
    if repo_dir is None:
        return {"outcome": "NO_REPO", "reason": f"no .git ancestor of {target}"}

    target_abs = str(Path(target).expanduser().resolve())
    target_rel = _repo_relative(target_abs, repo_dir)

    # Read + sanitize source
    try:
        source_excerpt = _read_source_excerpt(Path(target_abs))
    except RuntimeError as e:
        return {"outcome": "READ_FAILED", "reason": str(e)}

    # Build prompt, invoke LLM
    prompt = _build_prompt(target_rel, reason, source_excerpt)
    rc, stdout, stderr = _invoke_llm(prompt)
    if rc != 0:
        return {
            "outcome": "LLM_FAILED",
            "reason": f"rc={rc} stderr={stderr[-500:]}"
        }

    # Extract + validate diff
    diff_text, extract_reason = _extract_diff(stdout, target_rel)
    if diff_text is None:
        return {"outcome": "NO_DIFF", "reason": extract_reason,
                "llm_output_head": stdout[:500]}

    diff_lines = len(diff_text.splitlines())

    if dry_run:
        return {
            "outcome": "dry_run_ok",
            "target": target_abs,
            "diff_lines": diff_lines,
            "diff": diff_text,
        }

    # Hand off to the apply engine
    from hermes_fix_engine import apply_autonomous_fix
    spec = {
        "fix_id": str(uuid.uuid4()),
        "autonomy_level": "content",
        "sweep_name": "manual",
        "target_paths": [target_abs],
        "diff": diff_text,
        "subject": f"Fix content in {target_rel}: {reason[:50]}",
        "reason": reason,
        "repo_dir": repo_dir,
    }
    return apply_autonomous_fix(spec)


def main() -> int:
    parser = argparse.ArgumentParser(description="Hermes content fix authoring")
    parser.add_argument("--target", help="Absolute path to the target file")
    parser.add_argument("--reason", help="Short reason for the fix")
    parser.add_argument("--dry-run", action="store_true",
                        help="Produce diff but do not commit")
    parser.add_argument("--spec", help="Pre-built fix-job JSON (from queue)")
    args = parser.parse_args()

    if args.spec:
        spec_data = json.loads(Path(args.spec).read_text())
        target = spec_data["target"]
        reason = spec_data.get("reason", "auto-fix")
    else:
        if not args.target or not args.reason:
            parser.error("--target and --reason required (or use --spec)")
        target = args.target
        reason = args.reason

    result = author_content_fix(target, reason, dry_run=args.dry_run)
    print(json.dumps(result, indent=2, default=str))

    outcome = result.get("outcome", "")
    if outcome in ("applied", "dry_run_ok"):
        return 0
    if outcome.startswith("DISABLED_") or outcome == "DENYLIST_VIOLATION":
        return 1
    if outcome in ("NO_DIFF", "LLM_FAILED", "READ_FAILED", "NO_REPO"):
        return 2
    return 3


if __name__ == "__main__":
    sys.exit(main())
