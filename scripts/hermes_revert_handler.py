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


def _find_task_action_record(task_id: str) -> Optional[dict]:
    """Scan hermes-actions.jsonl for the most recent task_action record
    matching this task_id. Returns the record dict or None."""
    import json as _json
    from pathlib import Path as _Path
    log_path = _Path.home() / ".openclaw" / "agents" / "main" / "logs" / "hermes-actions.jsonl"
    if not log_path.exists():
        return None
    match = None
    try:
        with log_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = _json.loads(line)
                except _json.JSONDecodeError:
                    continue
                if rec.get("action_type") != "task_action":
                    continue
                ev = rec.get("evidence") or {}
                if ev.get("task_id") == task_id:
                    match = rec  # keep overwriting so last match wins
    except OSError:
        return None
    return match


def handle_revert_task_action(task_id: str) -> dict:
    """Revert a Hermes task-pipeline mutation (custodian sweep action).

    Reads the most recent task_action record for this task_id from
    hermes-actions.jsonl, uses evidence.previous_state to restore the
    field the mutation changed. Soft-reverts — no git commits involved.
    """
    rec = _find_task_action_record(task_id)
    if rec is None:
        return {"outcome": "NOT_FOUND", "task_id": task_id,
                "hint": "no task_action record for this task_id"}

    ev = rec.get("evidence") or {}
    kind = ev.get("action_kind")
    prev = ev.get("previous_state") or {}

    try:
        from neo4j_v2_core import TaskStore
    except ImportError as e:
        return {"outcome": "NO_NEO4J", "reason": str(e)}

    store = TaskStore()
    try:
        if kind == "delete":
            # previous_state.status is the pre-obsolete status
            prev_status = prev.get("status")
            if not prev_status:
                return {"outcome": "NO_PREVIOUS_STATE", "task_id": task_id}
            with store.driver.session() as session:
                session.run("""
                    MATCH (t:Task {task_id: $id, status: 'OBSOLETE'})
                    SET t.status = $prev,
                        t.obsolete_reverted_at = datetime(),
                        t.updated_at = datetime()
                """, id=task_id, prev=prev_status)
            return {"outcome": "reverted", "action_kind": kind,
                    "task_id": task_id, "restored_status": prev_status}
        if kind == "rewrite_prompt":
            prev_prompt = prev.get("prompt")
            if prev_prompt is None:
                return {"outcome": "NO_PREVIOUS_STATE", "task_id": task_id}
            with store.driver.session() as session:
                session.run("""
                    MATCH (t:Task {task_id: $id})
                    SET t.prompt = $prompt,
                        t.rewrite_reverted_at = datetime(),
                        t.updated_at = datetime()
                """, id=task_id, prompt=prev_prompt)
            return {"outcome": "reverted", "action_kind": kind,
                    "task_id": task_id}
        if kind == "reassign":
            prev_agent = prev.get("assigned_to") or prev.get("agent")
            if not prev_agent:
                return {"outcome": "NO_PREVIOUS_STATE", "task_id": task_id}
            with store.driver.session() as session:
                session.run("""
                    MATCH (t:Task {task_id: $id})
                    SET t.assigned_to = $prev,
                        t.agent = $prev,
                        t.claim_epoch = coalesce(t.claim_epoch, 0) + 1,
                        t.reassign_reverted_at = datetime(),
                        t.updated_at = datetime()
                """, id=task_id, prev=prev_agent)
            return {"outcome": "reverted", "action_kind": kind,
                    "task_id": task_id, "restored_agent": prev_agent}
        if kind == "retry":
            # Retries already ran — can't un-retry. Return a clear no-op.
            return {"outcome": "noop_retry_not_revertable",
                    "action_kind": kind, "task_id": task_id}
        return {"outcome": "UNKNOWN_ACTION_KIND", "action_kind": kind,
                "task_id": task_id}
    finally:
        try:
            store.close()
        except Exception:
            pass


def handle_revert_auto(id_hint: str) -> dict:
    """Auto-detect whether id_hint is a task_id (task_action in
    hermes-actions.jsonl) or a git SHA (HermesCommit). Task IDs take
    priority because they're the operator's semantic reference."""
    # Task IDs are slugs; SHAs are hex strings (7+ chars, base16 only).
    # If it looks like a SHA and we find a matching HermesCommit, use
    # git revert. Otherwise try the task-action path first.
    if _find_task_action_record(id_hint):
        return handle_revert_task_action(id_hint)
    return handle_revert(id_hint)


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
    sub_ta = sub.add_parser(
        "task-action",
        help="Revert a Hermes task-pipeline mutation by task_id",
    )
    sub_ta.add_argument("task_id", help="Task ID the custodian mutated")
    sub_auto = sub.add_parser(
        "auto",
        help="Auto-detect task_id vs SHA; used by the Signal handler",
    )
    sub_auto.add_argument("id_hint", help="task_id or SHA hint")
    args = parser.parse_args()

    if args.cmd == "sha":
        result = handle_revert(args.sha)
    elif args.cmd == "last":
        result = handle_revert(None)
    elif args.cmd == "all-today":
        result = handle_revert_all_today()
    elif args.cmd == "task-action":
        result = handle_revert_task_action(args.task_id)
    elif args.cmd == "auto":
        result = handle_revert_auto(args.id_hint)
    else:
        parser.print_help()
        return 1

    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("outcome") in (
        "reverted", "ok", "empty", "noop_retry_not_revertable",
    ) else 2


if __name__ == "__main__":
    sys.exit(main())
