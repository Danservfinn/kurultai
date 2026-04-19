#!/usr/bin/env python3
"""Hermes git commit wrapper: structured trailer, revert-ready, distinct author.

Every autonomous commit carries:
  - Author: 'Hermes Autonomous <hermes-autonomous@kurultai.local>'
  - Subject: 'hermes-auto-fix: {subject}'
  - Body: reason, target paths, diff size
  - Trailers:
      Co-Authored-By: hermes-autonomous-fix <noreply@kurultai.local>
      X-Hermes-Fix-Id: {uuid4}
      X-Hermes-Sweep: {sweep_name}
      X-Hermes-Autonomy-Level: {level}

Usage (from hermes_fix_engine):
    from hermes_commit import commit_hermes_fix, create_hermes_commit_node
    sha = commit_hermes_fix(
        repo_dir=Path('/path/to/repo'),
        subject='Fix quality-gate drift: add Resolution section',
        reason='check_quality_gate_drift fired 3x for this file',
        sweep_name='quality_gate_drift',
        autonomy_level='content',
        target_paths=['ogedei/normal-foo.done.md'],
        diff_lines=5,
    )

Phase 1 (Task 1.2/1.3) extends this module with Neo4j HermesCommit node
creation and revert-lookup helpers.
"""

from __future__ import annotations

import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Optional

# Single source of truth for the Hermes git identity
HERMES_AUTHOR_NAME = "Hermes Autonomous"
HERMES_AUTHOR_EMAIL = "hermes-autonomous@kurultai.local"


def commit_hermes_fix(
    repo_dir: Path,
    subject: str,
    reason: str,
    sweep_name: str,
    autonomy_level: str,  # 'content' | 'code' | 'sweep'
    target_paths: list[str],
    diff_lines: int,
    fix_id: Optional[str] = None,
) -> str:
    """Commit staged changes with structured Hermes trailer. Returns commit SHA.

    Caller is responsible for having staged the appropriate files before
    invoking this function (via `git add <paths>`).

    Raises RuntimeError on commit failure (e.g., pre-commit hook rejected).
    """
    if fix_id is None:
        fix_id = str(uuid.uuid4())

    message = "\n".join([
        f"hermes-auto-fix: {subject}",
        "",
        f"Reason: {reason}",
        f"Target: {', '.join(target_paths)}",
        f"Diff size: {diff_lines} lines",
        "",
        "Co-Authored-By: hermes-autonomous-fix <noreply@kurultai.local>",
        f"X-Hermes-Fix-Id: {fix_id}",
        f"X-Hermes-Sweep: {sweep_name}",
        f"X-Hermes-Autonomy-Level: {autonomy_level}",
    ])

    commit_result = subprocess.run(
        [
            "git",
            "-c", f"user.name={HERMES_AUTHOR_NAME}",
            "-c", f"user.email={HERMES_AUTHOR_EMAIL}",
            "commit",
            "-m", message,
        ],
        cwd=str(repo_dir),
        capture_output=True,
        text=True,
        timeout=30,
    )
    if commit_result.returncode != 0:
        raise RuntimeError(
            f"git commit failed (rc={commit_result.returncode}): "
            f"{commit_result.stderr.strip()}"
        )

    sha_result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(repo_dir),
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )
    return sha_result.stdout.strip()


def create_hermes_commit_node(
    sha: str,
    fix_id: str,
    repo: str,  # 'openclaw-scripts' | 'brain' | test repo name
    sweep: str,
    autonomy_level: str,
    subject: str,
    target_paths: list[str],
    diff_lines: int,
) -> bool:
    """Create a HermesCommit Neo4j node. Non-fatal on Neo4j errors (warns only).

    Returns True on success, False if Neo4j was unavailable or write failed.
    The calling fix engine should NOT abort a successful git commit just
    because Neo4j was unavailable — the git log is the source of truth.
    """
    try:
        from neo4j_v2_core import TaskStore  # deferred import
        store = TaskStore()
        try:
            with store.driver.session() as session:
                session.run(
                    """
                    MERGE (c:HermesCommit {sha: $sha})
                    SET
                        c.fix_id = $fix_id,
                        c.repo = $repo,
                        c.sweep = $sweep,
                        c.autonomy_level = $autonomy_level,
                        c.subject = $subject,
                        c.target_paths = $target_paths,
                        c.diff_lines = $diff_lines,
                        c.created_at = coalesce(c.created_at, datetime()),
                        c.reverted = coalesce(c.reverted, false)
                    """,
                    sha=sha, fix_id=fix_id, repo=repo, sweep=sweep,
                    autonomy_level=autonomy_level, subject=subject,
                    target_paths=target_paths, diff_lines=diff_lines,
                )
            return True
        finally:
            store.close()
    except Exception as e:
        print(
            f"warning: failed to create HermesCommit node for {sha}: {e}",
            file=sys.stderr,
        )
        return False


# ---------------------------------------------------------------------------
# Phase 1 Task 1.3: Revert-lookup helpers (stubs for now — the real
# implementation lands in Phase 1. These stubs return safe defaults so the
# pre-commit validator can call find_commit() in Phase 0 without crashing.)
# ---------------------------------------------------------------------------

def find_commit(short_or_full_sha: str) -> Optional[dict[str, Any]]:
    """Look up a HermesCommit by (short or full) SHA. Returns dict or None.

    Phase 1 Task 1.3: production query backed by `hermes_commit_sha_unique`
    constraint (from migration hermes_action_v2). Still tolerant of
    Neo4j unavailability — returns None if anything fails.
    """
    if not short_or_full_sha or len(short_or_full_sha) < 7:
        return None
    try:
        from neo4j_v2_core import TaskStore
        store = TaskStore()
        try:
            with store.driver.session() as session:
                result = session.run(
                    "MATCH (c:HermesCommit) "
                    "WHERE c.sha = $sha OR c.sha STARTS WITH $sha "
                    "RETURN c LIMIT 1",
                    sha=short_or_full_sha,
                )
                record = result.single()
                if record is None:
                    return None
                return dict(record["c"])
        finally:
            store.close()
    except Exception:
        return None


def recent_commits(n: int = 5) -> list[dict[str, Any]]:
    """Return the N most-recently-created HermesCommit records.

    Used by `revert` (no SHA arg) to find the last Hermes commit in the
    repo to be reverted by default.
    """
    if n <= 0:
        return []
    try:
        from neo4j_v2_core import TaskStore
        store = TaskStore()
        try:
            with store.driver.session() as session:
                result = session.run(
                    "MATCH (c:HermesCommit) "
                    "WHERE c.reverted = false "
                    "RETURN c "
                    "ORDER BY c.created_at DESC "
                    "LIMIT $n",
                    n=n,
                )
                return [dict(r["c"]) for r in result]
        finally:
            store.close()
    except Exception:
        return []


def commits_in_last_hours(hours: int) -> list[dict[str, Any]]:
    """Return all un-reverted HermesCommit records in the last N hours.

    Used by `revert all today`.
    """
    if hours <= 0:
        return []
    try:
        from neo4j_v2_core import TaskStore
        store = TaskStore()
        try:
            with store.driver.session() as session:
                result = session.run(
                    "MATCH (c:HermesCommit) "
                    "WHERE c.reverted = false "
                    "AND c.created_at > datetime() - duration({hours: $h}) "
                    "RETURN c "
                    "ORDER BY c.created_at DESC",
                    h=hours,
                )
                return [dict(r["c"]) for r in result]
        finally:
            store.close()
    except Exception:
        return []


def mark_reverted(sha: str, revert_sha: str) -> bool:
    """Mark a HermesCommit as reverted. Returns True on success.

    Idempotent — marking an already-reverted commit succeeds but
    preserves the original revert_sha.
    """
    if not sha or not revert_sha:
        return False
    try:
        from neo4j_v2_core import TaskStore
        store = TaskStore()
        try:
            with store.driver.session() as session:
                session.run(
                    "MATCH (c:HermesCommit {sha: $sha}) "
                    "SET c.reverted = true, "
                    "    c.revert_sha = coalesce(c.revert_sha, $revert_sha), "
                    "    c.reverted_at = coalesce(c.reverted_at, datetime())",
                    sha=sha, revert_sha=revert_sha,
                )
            return True
        finally:
            store.close()
    except Exception as e:
        print(f"warning: mark_reverted failed for {sha}: {e}", file=sys.stderr)
        return False
