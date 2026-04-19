#!/usr/bin/env python3
"""Hermes pre-commit validator.

Invoked by the git pre-commit hook ONLY when the commit author is
'hermes-autonomous@kurultai.local' (see hook wrapper). Human commits
bypass this check entirely.

Responsibilities:
  1. If the pending commit message matches "This reverts commit <sha>" AND
     the reverted SHA is a known HermesCommit, allow the commit even if it
     stages denylisted paths. (This is the only way to undo a one-shot
     self-modification-override commit.)
  2. Otherwise, refuse the commit if ANY staged file matches the denylist.

Exit codes:
  0 — allow commit
  1 — deny commit (reason printed to stderr)
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


def _pending_commit_message() -> str:
    """Read the pending commit message from .git/COMMIT_EDITMSG."""
    try:
        path_str = subprocess.check_output(
            ["git", "rev-parse", "--git-path", "COMMIT_EDITMSG"],
            text=True, stderr=subprocess.DEVNULL, timeout=5,
        ).strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return ""
    msg_file = Path(path_str)
    if not msg_file.exists():
        return ""
    try:
        return msg_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _staged_paths() -> list[str]:
    """Return repo-relative paths of files staged for the pending commit."""
    try:
        out = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only"],
            text=True, stderr=subprocess.DEVNULL, timeout=10,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def _repo_root() -> Path:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            text=True, stderr=subprocess.DEVNULL, timeout=5,
        ).strip()
        return Path(out)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return Path.cwd()


def _files_changed_by_commit(sha: str) -> set[str] | None:
    """Return the set of file paths changed by the given commit, or None
    on lookup failure.

    Used by the revert-bypass path to verify that the revert commit only
    touches files that were actually changed by the original commit.
    This prevents smuggling NEW denylisted files under a 'This reverts
    commit <sha>' marker.
    """
    try:
        out = subprocess.check_output(
            ["git", "show", "--name-only", "--pretty=format:", sha],
            text=True, stderr=subprocess.DEVNULL, timeout=10,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    return {line.strip() for line in out.splitlines() if line.strip()}


def main() -> int:
    msg_text = _pending_commit_message()

    # Step 1: Detect revert-of-Hermes-commit and bypass denylist.
    #
    # For the bypass to fire, ALL of the following must hold:
    #   a) Commit message matches 'This reverts commit <sha>' (git's default
    #      revert-message format)
    #   b) The referenced <sha> is a known HermesCommit (Neo4j index lookup)
    #   c) Every staged file is also a file that was changed by the reverted
    #      commit (prevents smuggling NEW denylisted files under a forged
    #      revert message — H1 from review)
    #
    # If ANY of the above fails, the bypass does not fire and denylist
    # enforcement (step 2) applies normally.
    m = re.search(r"^This reverts commit ([0-9a-f]{7,40})", msg_text, re.MULTILINE)
    if m:
        reverted_sha = m.group(1)
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from hermes_commit import find_commit  # type: ignore
            if find_commit(reverted_sha) is not None:
                # Known Hermes commit. Now verify the staged files are a
                # SUBSET of the original commit's file list.
                original_files = _files_changed_by_commit(reverted_sha)
                staged = set(_staged_paths())
                if original_files is None:
                    print(
                        "hermes_precommit_validator: revert referenced "
                        f"{reverted_sha} but git show failed — denying bypass",
                        file=sys.stderr,
                    )
                    # Fall through to denylist enforcement
                elif not staged:
                    print(
                        "hermes_precommit_validator: revert commit has no "
                        "staged files — unusual, denying bypass",
                        file=sys.stderr,
                    )
                elif staged.issubset(original_files):
                    # All staged files were in the reverted commit. Allow.
                    return 0
                else:
                    extras = staged - original_files
                    print(
                        "hermes_precommit_validator: revert bypass rejected "
                        f"— staged files not in reverted commit: {sorted(extras)}",
                        file=sys.stderr,
                    )
                    # Fall through to denylist enforcement (which will
                    # reject if any of those extras is denylisted)
        except Exception as e:
            print(
                f"hermes_precommit_validator: revert bypass check errored: {e} "
                "— falling through to denylist",
                file=sys.stderr,
            )

    # Step 2: Enforce denylist on staged paths.
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from hermes_denylist import is_denied  # type: ignore
    except ImportError as e:
        print(f"hermes_precommit_validator: cannot import hermes_denylist: {e}",
              file=sys.stderr)
        return 1  # fail-closed if validator can't load denylist

    repo_root = _repo_root()
    violations: list[tuple[str, str]] = []
    for rel in _staged_paths():
        abs_path = str(repo_root / rel)
        denied, reason = is_denied(abs_path)
        if denied:
            violations.append((rel, reason))

    if violations:
        print("hermes_precommit_validator: commit rejected — denylist violation:",
              file=sys.stderr)
        for path, reason in violations:
            print(f"  {path}: {reason}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
