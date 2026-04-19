#!/usr/bin/env python3
"""Hermes revert handler.

Core revert logic: resolve a target commit (by SHA, by "last", or by
"all today"), verify it's a Hermes-authored commit, run `git revert
--no-edit`, push, mark reverted in Neo4j, and notify confirmation.

The signal_message_handler.py intent registration (Task 7.1) calls
handle_revert() / handle_revert_all_today() from the inbound-message
chain when the operator replies 'revert' / 'revert <sha>' / 'revert
all today'.

Safety gates:
  - Only commits authored by 'hermes-autonomous@kurultai.local' can be
    reverted through this path (git log --format=%ae match).
  - The SHA must be in the HermesCommit Neo4j index (belt AND suspenders).
  - Sender phone must match the operator phone (only the operator can
    trigger reverts — prevents arbitrary-phone abuse). Enforced in the
    signal_message_handler intent wrapper, not here.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))


HERMES_EMAIL = "hermes-autonomous@kurultai.local"


def _git_show_author_email(repo_dir: str, sha: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", repo_dir, "log", "-1", "--format=%ae", sha],
            text=True, timeout=10, stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return ""


def _repo_dir_for_commit(commit_record: dict) -> Optional[str]:
    """Map the HermesCommit's 'repo' field to an absolute path."""
    repo_name = commit_record.get("repo", "")
    if repo_name == "openclaw-scripts":
        return str(Path.home() / ".openclaw" / "agents" / "main" / "scripts")
    if repo_name == "brain":
        return str(Path.home() / "brain")
    # Fallback: if target_paths exist, walk up to find .git
    targets = commit_record.get("target_paths", [])
    if targets:
        p = Path(targets[0]).expanduser()
        for ancestor in [p] + list(p.parents):
            if (ancestor / ".git").exists():
                return str(ancestor)
    return None


def _git_revert(repo_dir: str, sha: str) -> tuple[bool, str, str]:
    """Run git revert --no-edit <sha>. Returns (ok, revert_sha, detail)."""
    try:
        result = subprocess.run(
            ["git", "-C", repo_dir, "revert", "--no-edit", sha],
            capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        return False, "", "revert timeout"
    if result.returncode != 0:
        # Attempt to clean up partial revert state
        subprocess.run(
            ["git", "-C", repo_dir, "revert", "--abort"],
            capture_output=True, text=True, timeout=10,
        )
        return False, "", f"revert conflict/failed: {result.stderr[:400]}"

    try:
        revert_sha = subprocess.check_output(
            ["git", "-C", repo_dir, "rev-parse", "HEAD"],
            text=True, timeout=5,
        ).strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        revert_sha = ""
    return True, revert_sha, "ok"


def _git_push(repo_dir: str) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["git", "-C", repo_dir, "push", "origin", "main"],
            capture_output=True, text=True, timeout=60,
        )
    except subprocess.TimeoutExpired:
        return False, "push timeout"
    return result.returncode == 0, (result.stderr or result.stdout).strip()


def handle_revert(sha_hint: Optional[str]) -> dict:
    """Revert a single HermesCommit.

    sha_hint: full SHA, short SHA, or None. If None, picks the most
    recent un-reverted HermesCommit via hermes_commit.recent_commits(1).
    """
    from hermes_commit import find_commit, recent_commits, mark_reverted
    from hermes_notify import notify_revert_confirmed

    # 1. Resolve target commit record
    if sha_hint is None:
        recents = recent_commits(1)
        if not recents:
            return {"outcome": "NO_RECENT_HERMES_COMMIT"}
        commit = recents[0]
    else:
        commit = find_commit(sha_hint)
        if commit is None:
            return {"outcome": "NOT_FOUND", "sha_hint": sha_hint}

    sha = commit.get("sha", "")
    subject = commit.get("subject", "(no subject)")
    repo_dir = _repo_dir_for_commit(commit)
    if repo_dir is None:
        return {"outcome": "NO_REPO_DIR", "sha": sha}

    # 2. Verify the commit is authored by Hermes (defense in depth beyond
    #    the Neo4j HermesCommit index match)
    author = _git_show_author_email(repo_dir, sha)
    if author != HERMES_EMAIL:
        return {
            "outcome": "NOT_HERMES_COMMIT",
            "sha": sha,
            "actual_author": author,
        }

    # 3. Revert
    ok, revert_sha, detail = _git_revert(repo_dir, sha)
    if not ok:
        return {"outcome": "REVERT_FAILED", "sha": sha, "reason": detail}

    # 4. Push (best-effort; local revert commit stays either way)
    push_ok, push_detail = _git_push(repo_dir)

    # 5. Mark reverted in Neo4j
    mark_reverted(sha, revert_sha)

    # 6. Notify confirmation
    notify_revert_confirmed(revert_sha, sha, subject)

    return {
        "outcome": "reverted",
        "sha": sha,
        "revert_sha": revert_sha,
        "push_ok": push_ok,
        "push_detail": push_detail[:200],
        "subject": subject,
    }


def handle_revert_all_today() -> dict:
    """Revert every un-reverted HermesCommit in the last 24 hours, in
    reverse chronological order. Stops on first conflict."""
    from hermes_commit import commits_in_last_hours

    commits = commits_in_last_hours(24)
    summary: dict = {
        "found": len(commits),
        "reverted": [],
        "skipped": [],
        "conflict": None,
    }
    if not commits:
        summary["outcome"] = "empty"
        return summary

    for commit in commits:
        sha = commit.get("sha", "")
        result = handle_revert(sha)
        if result.get("outcome") == "reverted":
            summary["reverted"].append({
                "sha": sha,
                "revert_sha": result.get("revert_sha"),
            })
        elif result.get("outcome") in ("REVERT_FAILED",):
            summary["conflict"] = {"sha": sha, "detail": result.get("reason")}
            break
        else:
            summary["skipped"].append({
                "sha": sha,
                "outcome": result.get("outcome"),
            })

    if summary["conflict"] is not None:
        summary["outcome"] = "partial_conflict"
    else:
        summary["outcome"] = "ok"

    # Send a summary DM via hermes_notify (reusing existing infra)
    try:
        from hermes_notify import _enqueue
        msg_lines = [
            "Revert-all-today result",
            f"Reverted: {len(summary['reverted'])}",
        ]
        for r in summary["reverted"][:10]:
            msg_lines.append(f"  - {r['sha'][:10]}")
        if summary["conflict"]:
            msg_lines.append(
                f"Stopped at conflict on {summary['conflict']['sha'][:10]}"
            )
        _enqueue("revert-all-today", "\n".join(msg_lines))
    except Exception:
        pass

    return summary


def main() -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Hermes revert handler")
    sub = parser.add_subparsers(dest="cmd")
    sub_sha = sub.add_parser("sha", help="Revert a specific SHA")
    sub_sha.add_argument("sha", help="Full or short SHA")
    sub.add_parser("last", help="Revert the most recent HermesCommit")
    sub.add_parser("all-today", help="Revert all HermesCommits in last 24h")
    args = parser.parse_args()

    if args.cmd == "sha":
        result = handle_revert(args.sha)
    elif args.cmd == "last":
        result = handle_revert(None)
    elif args.cmd == "all-today":
        result = handle_revert_all_today()
    else:
        parser.print_help()
        return 1

    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("outcome") in ("reverted", "ok", "empty") else 2


if __name__ == "__main__":
    sys.exit(main())
