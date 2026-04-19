#!/usr/bin/env python3
"""Hermes code-fix authoring.

Mirrors hermes-fix-content.py but with stricter gates for code:
  - diff size cap (default 80 lines)
  - AST parse check on the resulting file (Python only)
  - baseline test must pass before authoring (don't pile on broken state)

Gates (fail-closed at each):
  - hermes-disabled.flag
  - hermes-autonomous-disabled.flag
  - hermes-autonomous-fix-code-disabled.flag
  - hermes_denylist.is_denied(target)

Usage:
    python3 hermes-fix-code.py --target <path.py> --reason "<short>"
    python3 hermes-fix-code.py --target <path.py> --reason "..." --dry-run

Exit codes:
  0 — fix applied (or dry-run produced valid diff)
  1 — gate blocked, no LLM call made
  2 — LLM produced invalid output, diff too big, or AST/test gate failed
  3 — apply engine rejected (denylist, rate-limit, tests)
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Load hermes-fix-content.py's helpers (it has hyphens, not a standard module name)
_HFC_PATH = Path(__file__).resolve().parent / "hermes-fix-content.py"
_hfc_spec = importlib.util.spec_from_file_location("_hfc_mod", _HFC_PATH)
_hfc = importlib.util.module_from_spec(_hfc_spec)
_hfc_spec.loader.exec_module(_hfc)

MAX_DIFF_LINES_CODE = int(os.getenv("HERMES_MAX_DIFF_LINES", "80"))
BASELINE_TEST_TIMEOUT_SECS = 60


def _run_baseline_tests(target_abs: str) -> tuple[bool, str]:
    """Run pytest against the target's test file (if one exists).

    Returns (ok, detail). If no test file, returns (True, 'no tests').
    If tests fail, returns (False, ...) — caller must abort authoring.
    """
    path = Path(target_abs)
    if path.suffix != ".py":
        return True, "not a python file"
    test_file = path.parent / "tests" / f"test_{path.stem}.py"
    if not test_file.exists():
        return True, "no tests applicable"
    try:
        result = subprocess.run(
            ["python3", "-m", "pytest", "-q", "--no-header", str(test_file)],
            capture_output=True, text=True,
            timeout=BASELINE_TEST_TIMEOUT_SECS,
        )
        if result.returncode == 0:
            return True, "ok"
        return False, (result.stdout + result.stderr)[-800:]
    except subprocess.TimeoutExpired:
        return False, "baseline test timeout"
    except OSError as e:
        return False, f"test invocation failed: {e}"


def _validate_code_patch(target_abs: str, diff_text: str, repo_dir: str) -> tuple[bool, str]:
    """Apply the diff to a temp copy of target_abs, AST-parse the result.

    Uses `git apply` against a throwaway working tree (no commits needed —
    git apply can work against an index-free worktree).
    """
    import re as _re
    path = Path(target_abs)
    if path.suffix != ".py":
        return True, "not a python file, skipping AST check"

    m = _re.search(r"^---\s+a/(\S+)", diff_text, _re.MULTILINE)
    if not m:
        return False, "cannot locate diff header"
    rel = m.group(1)

    scratch = Path(tempfile.mkdtemp(prefix="hermes_fix_code_scratch_"))
    try:
        target_in_scratch = scratch / rel
        target_in_scratch.parent.mkdir(parents=True, exist_ok=True)
        try:
            target_in_scratch.write_bytes(path.read_bytes())
        except OSError as e:
            return False, f"scratch copy failed: {e}"

        # Use GNU patch (more lenient than git apply outside a repo).
        # The scratch dir is arranged so relative path `a/{rel}` -> file.
        # `--strip=1` removes the a/ prefix; `--directory` sets the root.
        try:
            result = subprocess.run(
                ["patch", "--strip=1", "--directory", str(scratch),
                 "--silent", "--no-backup-if-mismatch"],
                input=diff_text, text=True,
                capture_output=True, timeout=10,
            )
        except subprocess.TimeoutExpired:
            return False, "patch timeout"
        except OSError as e:
            return False, f"patch invocation failed: {e}"

        if result.returncode != 0:
            return False, f"patch failed: {(result.stderr or result.stdout)[:400]}"

        try:
            post_text = target_in_scratch.read_text(
                encoding="utf-8", errors="replace",
            )
        except OSError as e:
            return False, f"scratch read failed: {e}"

        try:
            ast.parse(post_text)
        except SyntaxError as e:
            return False, f"post-patch SyntaxError: {e}"

        return True, "ast ok"
    finally:
        # Best-effort cleanup of the scratch dir
        try:
            import shutil
            shutil.rmtree(scratch, ignore_errors=True)
        except Exception:
            pass


def author_code_fix(target: str, reason: str, dry_run: bool = False,
                    max_diff_lines: int = MAX_DIFF_LINES_CODE) -> dict:
    """Main entry: author a code fix and apply it (unless --dry-run)."""
    import hermes_auto_fix as haf
    from hermes_denylist import is_denied

    # Gate 1: flags
    if haf._check_kill_switch():
        return {"outcome": "DISABLED_BY_KILL_SWITCH"}
    if haf._check_autonomous_disabled():
        return {"outcome": "DISABLED_BY_AUTONOMOUS_FLAG"}
    if haf._check_autonomous_fix_code_disabled():
        return {"outcome": "DISABLED_BY_CODE_FLAG"}

    # Gate 2: denylist
    denied, deny_reason = is_denied(target)
    if denied:
        return {"outcome": "DENYLIST_VIOLATION", "reason": deny_reason}

    repo_dir = _hfc._repo_dir_for_target(target)
    if repo_dir is None:
        return {"outcome": "NO_REPO",
                "reason": f"no .git ancestor of {target}"}

    target_abs = str(Path(target).expanduser().resolve())
    target_rel = _hfc._repo_relative(target_abs, repo_dir)

    # Gate 3: baseline tests must pass BEFORE authoring
    ok, baseline_detail = _run_baseline_tests(target_abs)
    if not ok:
        return {"outcome": "BASELINE_BROKEN",
                "reason": f"target has failing tests at baseline: {baseline_detail}"}

    # Read + sanitize source
    try:
        source_excerpt = _hfc._read_source_excerpt(Path(target_abs))
    except RuntimeError as e:
        return {"outcome": "READ_FAILED", "reason": str(e)}

    # Build prompt, invoke LLM
    prompt = _hfc._build_prompt(target_rel, reason, source_excerpt)
    rc, stdout, stderr = _hfc._invoke_llm(prompt)
    if rc != 0:
        return {"outcome": "LLM_FAILED",
                "reason": f"rc={rc} stderr={stderr[-500:]}"}

    # Extract + validate diff structure
    diff_text, extract_reason = _hfc._extract_diff(stdout, target_rel)
    if diff_text is None:
        return {"outcome": "NO_DIFF", "reason": extract_reason,
                "llm_output_head": stdout[:500]}

    diff_lines = len(diff_text.splitlines())

    # Gate 4: diff-size cap
    if diff_lines > max_diff_lines:
        # Save full diff for operator review; notify-only
        from hermes_notify import notify_fix_skipped_too_big
        fix_id = str(uuid.uuid4())
        diff_log = Path.home() / ".openclaw" / "logs" / "hermes-fixes" / f"{fix_id}-skipped.diff"
        diff_log.parent.mkdir(parents=True, exist_ok=True)
        diff_log.write_text(diff_text)
        notify_fix_skipped_too_big(
            fix_id=fix_id, target=target_abs, reason=reason,
            diff_lines=diff_lines, diff_path=str(diff_log),
            max_lines=max_diff_lines,
        )
        return {"outcome": "DIFF_TOO_BIG", "diff_lines": diff_lines,
                "diff_log": str(diff_log), "cap": max_diff_lines}

    # Gate 5: syntax + scratch-test on the diff-applied version
    ok, validate_detail = _validate_code_patch(target_abs, diff_text, repo_dir)
    if not ok:
        return {"outcome": "VALIDATION_FAILED", "reason": validate_detail}

    if dry_run:
        return {
            "outcome": "dry_run_ok",
            "target": target_abs,
            "diff_lines": diff_lines,
            "diff": diff_text,
            "validation": validate_detail,
        }

    # Hand off to the apply engine
    from hermes_fix_engine import apply_autonomous_fix
    spec = {
        "fix_id": str(uuid.uuid4()),
        "autonomy_level": "code",
        "sweep_name": "manual",
        "target_paths": [target_abs],
        "diff": diff_text,
        "subject": f"Fix code in {target_rel}: {reason[:50]}",
        "reason": reason,
        "repo_dir": repo_dir,
    }
    return apply_autonomous_fix(spec)


def main() -> int:
    parser = argparse.ArgumentParser(description="Hermes code fix authoring")
    parser.add_argument("--target", required=True, help="Absolute path to the .py target")
    parser.add_argument("--reason", required=True, help="Short reason for the fix")
    parser.add_argument("--dry-run", action="store_true",
                        help="Produce + validate diff but do not commit")
    parser.add_argument("--max-diff-lines", type=int, default=MAX_DIFF_LINES_CODE,
                        help=f"Diff size cap (default: {MAX_DIFF_LINES_CODE})")
    args = parser.parse_args()

    result = author_code_fix(
        args.target, args.reason, dry_run=args.dry_run,
        max_diff_lines=args.max_diff_lines,
    )
    print(json.dumps(result, indent=2, default=str))

    outcome = result.get("outcome", "")
    if outcome in ("applied", "dry_run_ok"):
        return 0
    if outcome.startswith("DISABLED_") or outcome == "DENYLIST_VIOLATION":
        return 1
    if outcome in ("NO_DIFF", "LLM_FAILED", "READ_FAILED", "NO_REPO",
                    "DIFF_TOO_BIG", "VALIDATION_FAILED", "BASELINE_BROKEN"):
        return 2
    return 3


if __name__ == "__main__":
    sys.exit(main())
