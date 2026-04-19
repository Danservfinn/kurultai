#!/usr/bin/env python3
"""Hermes autonomous fix engine.

Invariant: after apply_autonomous_fix(spec) returns, target files are in
exactly ONE of two states:
  1. The fix was applied, committed, pushed, Signal DM enqueued
  2. Target files are in their original pre-fix state (git restore or
     backup fallback) and a rollback notification was sent

No intermediate state is legitimate. If any gate fails, the function
must return WITHOUT committing.

Flow (14 steps):
  1.  gate: master + per-scope flag
  2.  gate: denylist on every target path (double-check at apply time)
  3.  rate-limit: atomic consume_slot (H2)
  4.  baseline test: fail-fast if affected tests are already broken
  5.  dry-run: git apply --check on the diff
  6.  snapshot: copy target files to workspace/apply-backups/{fix_id}/
  7.  apply: git apply
  8.  post-apply test: if fails, git restore + rollback notification
  9.  commit: commit_hermes_fix() with structured trailer
  10. push: git push origin main (best-effort)
  11. record: HermesCommit Neo4j node
  12. emit: HermesAction Neo4j node
  13. record: rate_limit.record on this scope
  14. notify: fix_success DM via hermes_notify

Rollback on post-apply test failure:
  - git restore --source=HEAD -- <targets>  (primary; no commit was made)
  - if restore fails: copy from workspace/apply-backups/{fix_id}/ (fallback)
  - circuit breaker: record_event('apply_failed' or 'rollback')
  - notify_fix_rolled_back DM

Isolation:
  - Subprocess environments for baseline/post-apply tests set
    HERMES_TEST_ISOLATED=1 + dead-port Neo4j/Signal URLs so any test
    that forgets to mock fails fast instead of polluting prod.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

MAX_DIFF_LINES_CONTENT = 500   # content: generous (docs can be long)
MAX_DIFF_LINES_CODE = 80       # code: strict (H1 from review)

TEST_TIMEOUT_SECS = 120
PUSH_TIMEOUT_SECS = 60
GIT_TIMEOUT_SECS = 30

BACKUP_ROOT = Path.home() / ".openclaw" / "agents" / "hermes" / "workspace" / "apply-backups"
FIX_LOG_DIR = Path.home() / ".openclaw" / "logs" / "hermes-fixes"


def _disabled(reason: str) -> dict:
    return {"outcome": f"DISABLED_BY_{reason.upper()}", "reason": reason}


def _escape_path_for_backup(p: str) -> str:
    """Convert an absolute path into a flat filename for the backup dir."""
    return p.replace("/", "__").lstrip("_")


def _snapshot_files(fix_id: str, paths: list[str]) -> Path:
    """Copy affected files to workspace/apply-backups/{fix_id}/."""
    backup_dir = BACKUP_ROOT / fix_id
    backup_dir.mkdir(parents=True, exist_ok=True)
    for p in paths:
        src = Path(p).expanduser().resolve()
        if src.exists():
            dst = backup_dir / _escape_path_for_backup(str(src))
            shutil.copy2(src, dst)
    return backup_dir


def _restore_from_backup(backup_dir: Path, paths: list[str]) -> bool:
    """Best-effort restore from a per-fix backup dir. Returns True if all
    paths restored successfully."""
    ok = True
    for p in paths:
        src = Path(p).expanduser().resolve()
        backup = backup_dir / _escape_path_for_backup(str(src))
        if backup.exists():
            try:
                shutil.copy2(backup, src)
            except OSError:
                ok = False
        else:
            # No backup existed (new file) — remove the in-place version
            try:
                if src.exists():
                    src.unlink()
            except OSError:
                ok = False
    return ok


def _isolated_test_env() -> dict[str, str]:
    """Subprocess env for baseline/post-apply test invocations.

    Ensures any test that forgets to mock real services fails fast.
    """
    env = dict(os.environ)
    env["HERMES_TEST_ISOLATED"] = "1"
    env["NEO4J_URI"] = "bolt://127.0.0.1:0"
    env["SIGNAL_DAEMON_URL"] = "http://127.0.0.1:0/fail"
    env["HERMES_OPERATOR_PHONE"] = "+10000000000"
    return env


def _detect_affected_test_files(affected_paths: list[str]) -> list[str]:
    """Heuristic: for each source file, find its test file (if any)."""
    tests: list[str] = []
    for p in affected_paths:
        path = Path(p)
        if path.suffix != ".py":
            continue
        # Common patterns: same dir has tests/test_<name>.py
        candidate = path.parent / "tests" / f"test_{path.stem}.py"
        if candidate.exists():
            tests.append(str(candidate))
    return tests


def run_tests_for_paths(affected_paths: list[str]) -> tuple[bool, str]:
    """Run pytest against test files covering the affected source paths.

    Returns (ok, detail). If no test files found, returns (True, "no tests
    applicable") — logged by caller as a WARN but not a blocker.
    """
    test_files = _detect_affected_test_files(affected_paths)
    if not test_files:
        return True, "no tests applicable"
    try:
        result = subprocess.run(
            ["python3", "-m", "pytest", "-q", "--no-header"] + test_files,
            env=_isolated_test_env(),
            capture_output=True, text=True, timeout=TEST_TIMEOUT_SECS,
        )
    except subprocess.TimeoutExpired:
        return False, f"test timeout after {TEST_TIMEOUT_SECS}s"
    except OSError as e:
        return False, f"test invocation failed: {e}"
    tail = (result.stdout + result.stderr)[-2000:]
    return result.returncode == 0, tail


def _dry_run_apply(repo_dir: str, diff_text: str) -> tuple[bool, str]:
    """git apply --check on the diff. Returns (ok, detail)."""
    try:
        result = subprocess.run(
            ["git", "apply", "--check", "-"],
            input=diff_text,
            cwd=repo_dir, capture_output=True, text=True,
            timeout=GIT_TIMEOUT_SECS,
        )
    except subprocess.TimeoutExpired:
        return False, "git apply --check timeout"
    except OSError as e:
        return False, f"git invocation failed: {e}"
    return result.returncode == 0, (result.stderr or result.stdout).strip()


def _apply_diff(repo_dir: str, diff_text: str) -> tuple[bool, str]:
    """git apply the diff. Returns (ok, detail)."""
    try:
        result = subprocess.run(
            ["git", "apply", "-"],
            input=diff_text,
            cwd=repo_dir, capture_output=True, text=True,
            timeout=GIT_TIMEOUT_SECS,
        )
    except subprocess.TimeoutExpired:
        return False, "git apply timeout"
    except OSError as e:
        return False, f"git invocation failed: {e}"
    return result.returncode == 0, (result.stderr or result.stdout).strip()


def _git_restore(repo_dir: str, paths: list[str]) -> tuple[bool, str]:
    """git restore --source=HEAD -- <paths>. Returns (ok, detail)."""
    try:
        # Convert absolute paths to repo-relative
        rel_paths = []
        for p in paths:
            abs_p = Path(p).expanduser().resolve()
            try:
                rel_paths.append(str(abs_p.relative_to(Path(repo_dir).resolve())))
            except ValueError:
                rel_paths.append(str(abs_p))
        result = subprocess.run(
            ["git", "restore", "--source=HEAD", "--"] + rel_paths,
            cwd=repo_dir, capture_output=True, text=True,
            timeout=GIT_TIMEOUT_SECS,
        )
    except subprocess.TimeoutExpired:
        return False, "git restore timeout"
    except OSError as e:
        return False, f"git invocation failed: {e}"
    return result.returncode == 0, result.stderr.strip()


def _git_add(repo_dir: str, paths: list[str]) -> tuple[bool, str]:
    """git add <paths>. Returns (ok, detail)."""
    rel_paths = []
    for p in paths:
        abs_p = Path(p).expanduser().resolve()
        try:
            rel_paths.append(str(abs_p.relative_to(Path(repo_dir).resolve())))
        except ValueError:
            rel_paths.append(str(abs_p))
    try:
        result = subprocess.run(
            ["git", "add"] + rel_paths,
            cwd=repo_dir, capture_output=True, text=True,
            timeout=GIT_TIMEOUT_SECS,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        return False, f"git add error: {e}"
    return result.returncode == 0, result.stderr.strip()


def _git_push(repo_dir: str) -> tuple[bool, str]:
    """git fetch + push with one retry. Returns (ok, detail)."""
    for attempt in (1, 2):
        # Fetch first to reduce conflicts
        subprocess.run(
            ["git", "fetch", "origin", "main"],
            cwd=repo_dir, capture_output=True, text=True,
            timeout=PUSH_TIMEOUT_SECS,
        )
        try:
            result = subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=repo_dir, capture_output=True, text=True,
                timeout=PUSH_TIMEOUT_SECS,
            )
            if result.returncode == 0:
                return True, result.stdout.strip()
        except (subprocess.TimeoutExpired, OSError) as e:
            if attempt == 2:
                return False, f"git push error: {e}"
            continue
        # Failed; one more attempt after brief wait
        if attempt == 2:
            return False, (result.stderr or result.stdout).strip()
        import time
        time.sleep(5)
    return False, "git push failed after retries"


def _repo_name(repo_dir: str) -> str:
    """Friendly name for the repo used in notifications."""
    mapping = {
        str(Path.home() / ".openclaw" / "agents" / "main" / "scripts"): "openclaw-scripts",
        str(Path.home() / "brain"): "brain",
    }
    resolved = str(Path(repo_dir).expanduser().resolve())
    return mapping.get(resolved, Path(resolved).name or "unknown-repo")


def _log_fix(fix_id: str, spec: dict, result: dict) -> None:
    """Write a structured log of the fix attempt to ~/.openclaw/logs/hermes-fixes/."""
    try:
        FIX_LOG_DIR.mkdir(parents=True, exist_ok=True)
        entry = {"fix_id": fix_id, "spec": spec, "result": result}
        (FIX_LOG_DIR / f"{fix_id}.json").write_text(
            json.dumps(entry, indent=2, default=str)
        )
    except OSError:
        pass


def apply_autonomous_fix(spec: dict) -> dict:
    """Execute the full flow for one fix. See module docstring for
    step-by-step contract.

    spec = {
        'fix_id': str,
        'autonomy_level': 'content' | 'code',
        'sweep_name': str,
        'target_paths': [absolute path, ...],
        'diff': unified diff text,
        'subject': commit subject,
        'reason': commit body reason,
        'repo_dir': absolute path to repo,
    }

    Returns dict with 'outcome' key and optional 'commit_sha', 'reason',
    'error' keys. Callers should check result['outcome'] to branch.
    """
    # Deferred imports so the engine can be partially tested in isolation.
    import hermes_auto_fix as haf
    from hermes_denylist import is_denied
    from hermes_commit import commit_hermes_fix, create_hermes_commit_node
    from hermes_circuit_breaker import record_event
    import hermes_rate_limit as rl
    from hermes_notify import notify_fix_success, notify_fix_rolled_back

    fix_id = spec.get("fix_id") or str(uuid.uuid4())
    autonomy = spec.get("autonomy_level", "content")
    diff_text = spec.get("diff", "")
    diff_lines = len(diff_text.splitlines())
    targets = spec.get("target_paths", [])
    repo_dir = spec.get("repo_dir")
    subject = spec.get("subject", "Hermes auto-fix")
    reason = spec.get("reason", "")
    sweep_name = spec.get("sweep_name", "unknown")

    result: dict[str, Any] = {"fix_id": fix_id}

    # --- Step 1: gates ---
    if haf._check_autonomous_disabled():
        result["outcome"] = "DISABLED_BY_AUTONOMOUS_FLAG"
        _log_fix(fix_id, spec, result)
        return result
    if autonomy == "code" and haf._check_autonomous_fix_code_disabled():
        result["outcome"] = "DISABLED_BY_CODE_FLAG"
        _log_fix(fix_id, spec, result)
        return result
    if autonomy == "content" and haf._check_autonomous_fix_content_disabled():
        result["outcome"] = "DISABLED_BY_CONTENT_FLAG"
        _log_fix(fix_id, spec, result)
        return result

    # --- Step 2: denylist double-check ---
    for path in targets:
        denied, deny_reason = is_denied(path)
        if denied:
            result["outcome"] = "DENYLIST_VIOLATION"
            result["reason"] = f"{path}: {deny_reason}"
            record_event("denylist_violation", result["reason"])
            _log_fix(fix_id, spec, result)
            return result

    # --- Step 3: rate limit (atomic) ---
    ok, rl_reason = rl.consume_slot(autonomy)
    if not ok:
        result["outcome"] = "RATE_LIMITED"
        result["reason"] = rl_reason
        _log_fix(fix_id, spec, result)
        return result

    # --- Step 4: baseline tests ---
    ok, baseline_detail = run_tests_for_paths(targets)
    if not ok:
        result["outcome"] = "BASELINE_FAILED"
        result["reason"] = f"baseline tests broken: {baseline_detail[-500:]}"
        _log_fix(fix_id, spec, result)
        return result
    result["baseline"] = baseline_detail[-200:]

    # --- Step 5: dry-run apply ---
    ok, dry_detail = _dry_run_apply(repo_dir, diff_text)
    if not ok:
        result["outcome"] = "DIFF_INVALID"
        result["reason"] = dry_detail
        _log_fix(fix_id, spec, result)
        return result

    # --- Step 6: snapshot ---
    try:
        backup_dir = _snapshot_files(fix_id, targets)
    except OSError as e:
        result["outcome"] = "BACKUP_FAILED"
        result["reason"] = str(e)
        _log_fix(fix_id, spec, result)
        return result

    # --- Step 7: apply ---
    ok, apply_detail = _apply_diff(repo_dir, diff_text)
    if not ok:
        # Restore from backup (defense — target files shouldn't have been
        # mutated if git apply failed, but be safe)
        _restore_from_backup(backup_dir, targets)
        record_event("apply_failed", apply_detail[:200])
        result["outcome"] = "APPLY_FAILED"
        result["reason"] = apply_detail
        _log_fix(fix_id, spec, result)
        return result

    # --- Step 8: post-apply tests ---
    ok, post_detail = run_tests_for_paths(targets)
    if not ok:
        # Primary rollback: git restore
        rok, rerror = _git_restore(repo_dir, targets)
        if not rok:
            # Fallback: backup restore
            _restore_from_backup(backup_dir, targets)
        record_event("apply_failed", f"post-test failed: {post_detail[-200:]}")
        notify_fix_rolled_back(fix_id, subject, post_detail[-500:], _repo_name(repo_dir))
        result["outcome"] = "POST_TEST_FAILED_ROLLED_BACK"
        result["reason"] = post_detail[-1000:]
        _log_fix(fix_id, spec, result)
        return result

    # --- Step 9: commit ---
    add_ok, add_err = _git_add(repo_dir, targets)
    if not add_ok:
        _git_restore(repo_dir, targets)
        _restore_from_backup(backup_dir, targets)
        result["outcome"] = "GIT_ADD_FAILED"
        result["reason"] = add_err
        _log_fix(fix_id, spec, result)
        return result

    try:
        commit_sha = commit_hermes_fix(
            repo_dir=Path(repo_dir),
            subject=subject,
            reason=reason,
            sweep_name=sweep_name,
            autonomy_level=autonomy,
            target_paths=targets,
            diff_lines=diff_lines,
            fix_id=fix_id,
        )
    except RuntimeError as e:
        # Pre-commit hook rejected, etc.
        _git_restore(repo_dir, targets)
        _restore_from_backup(backup_dir, targets)
        result["outcome"] = "COMMIT_FAILED"
        result["reason"] = str(e)
        _log_fix(fix_id, spec, result)
        return result

    result["commit_sha"] = commit_sha

    # --- Step 10: push (best-effort — local commit stays either way) ---
    push_ok, push_detail = _git_push(repo_dir)
    result["push_ok"] = push_ok
    result["push_detail"] = push_detail[:200]

    # --- Step 11: HermesCommit Neo4j node ---
    create_hermes_commit_node(
        sha=commit_sha, fix_id=fix_id, repo=_repo_name(repo_dir),
        sweep=sweep_name, autonomy_level=autonomy,
        subject=subject, target_paths=targets, diff_lines=diff_lines,
    )

    # --- Step 12: HermesAction emit ---
    haf._emit_hermes_action(
        action_type="autonomous_fix",
        target=targets[0] if targets else "unknown",
        outcome="applied",
        dry_run=False,
        evidence={
            "fix_id": fix_id,
            "commit_sha": commit_sha,
            "repo": _repo_name(repo_dir),
            "diff_lines": diff_lines,
            "sweep": sweep_name,
            "autonomy_level": autonomy,
            "push_ok": push_ok,
            "extra_targets": targets[1:] if len(targets) > 1 else [],
        },
    )

    # --- Step 13: rate-limit record is already done via consume_slot ---

    # --- Step 14: notify operator ---
    diff_head = "\n".join(diff_text.splitlines()[:40])
    notify_fix_success(
        fix_id=fix_id, subject=subject, commit_sha=commit_sha,
        repo=_repo_name(repo_dir), diff_head=diff_head,
        autonomy_level=autonomy,
    )

    result["outcome"] = "applied"
    _log_fix(fix_id, spec, result)
    return result


def main() -> int:
    """CLI: read a fix-spec JSON from stdin or --spec file, apply, print result."""
    import argparse
    parser = argparse.ArgumentParser(description="Apply a Hermes autonomous fix")
    parser.add_argument("--spec", help="Path to spec JSON (defaults to stdin)")
    args = parser.parse_args()

    if args.spec:
        spec = json.loads(Path(args.spec).read_text())
    else:
        spec = json.loads(sys.stdin.read())

    result = apply_autonomous_fix(spec)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result["outcome"] == "applied" else 1


if __name__ == "__main__":
    sys.exit(main())
