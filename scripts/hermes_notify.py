#!/usr/bin/env python3
"""Hermes-specific Signal notification helpers.

Thin wrapper around notification_queue.NotificationQueue. Every Hermes
autonomous action (fix applied, fix rolled back, circuit breaker tripped,
revert confirmed, panic-stop engaged, too-big-to-fix skipped) enqueues a
message here. The underlying queue handles delivery, retries, and backoff.

Operator-phone resolution order:
  1. ~/.openclaw/config/operator_phone (one line, phone number)
  2. HERMES_OPERATOR_PHONE env var
  3. Fallback: "+19193375833" (historical default)

Usage:
    from hermes_notify import notify_fix_success
    notify_fix_success(fix_id, subject, commit_sha, repo, diff_head, level)

CLI entry point (for shell-script callers such as hermes-panic-stop.sh):
    python3 hermes_notify.py --panic-stop-engaged
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

_OPERATOR_PHONE_FILE = Path.home() / ".openclaw" / "config" / "operator_phone"
_DEFAULT_PHONE = "+19193375833"


def _operator_phone() -> str:
    """Resolve the operator's Signal phone number."""
    try:
        if _OPERATOR_PHONE_FILE.exists():
            phone = _OPERATOR_PHONE_FILE.read_text(encoding="utf-8").strip()
            if phone:
                return phone
    except OSError:
        pass
    return os.getenv("HERMES_OPERATOR_PHONE", _DEFAULT_PHONE)


def _enqueue(task_id: str, message: str) -> Optional[int]:
    """Enqueue a message. Returns queue entry ID or None on failure."""
    try:
        from notification_queue import NotificationQueue  # type: ignore
    except ImportError:
        print("hermes_notify: notification_queue unavailable — skipping DM",
              file=sys.stderr)
        return None
    try:
        q = NotificationQueue()
        return q.enqueue(
            task_id=task_id,
            agent="hermes",
            notify_target=_operator_phone(),
            message=message,
        )
    except Exception as e:
        print(f"hermes_notify: enqueue failed: {e}", file=sys.stderr)
        return None


def notify_fix_success(
    fix_id: str,
    subject: str,
    commit_sha: str,
    repo: str,
    diff_head: str,
    autonomy_level: str,
) -> Optional[int]:
    """Queue a 'fix applied' DM."""
    short_sha = commit_sha[:10]
    diff_block = (
        diff_head if len(diff_head) < 1500
        else diff_head[:1500] + "\n...(truncated)..."
    )
    msg = (
        "Hermes auto-fix applied\n\n"
        f"{subject}\n\n"
        f"Repo: {repo}\n"
        f"Commit: {short_sha}\n"
        f"Autonomy: {autonomy_level}\n\n"
        f"--- Diff (first 1500 bytes) ---\n{diff_block}\n\n"
        f"Reply 'revert' to undo this commit, or 'revert {short_sha}' from anywhere."
    )
    return _enqueue(fix_id, msg)


def notify_fix_rolled_back(
    fix_id: str,
    subject: str,
    reason: str,
    repo: str,
) -> Optional[int]:
    """Queue a 'post-apply tests failed, auto-rolled-back' DM."""
    msg = (
        "Hermes auto-fix rolled back\n\n"
        f"{subject}\n\n"
        f"Repo: {repo}\n"
        f"Reason: {reason}\n\n"
        "File was restored to pre-fix state. No further action required."
    )
    return _enqueue(fix_id, msg)


def notify_circuit_breaker_tripped(detail: str) -> Optional[int]:
    """Queue a 'circuit breaker tripped' DM."""
    msg = (
        "Hermes circuit breaker TRIPPED\n\n"
        f"{detail}\n\n"
        "Autonomous mode disabled. Remove flag to re-enable:\n"
        "  rm ~/.openclaw/flags/hermes-autonomous-disabled.flag"
    )
    return _enqueue("circuit-breaker", msg)


def notify_revert_confirmed(
    revert_sha: str,
    original_sha: str,
    subject: str,
) -> Optional[int]:
    """Queue a 'revert applied' DM."""
    msg = (
        "Revert applied\n\n"
        f"Original: {original_sha[:10]} - {subject}\n"
        f"Revert commit: {revert_sha[:10]}\n\n"
        "File restored to pre-Hermes-commit state."
    )
    return _enqueue(f"revert-{original_sha[:10]}", msg)


def notify_panic_stop_engaged() -> Optional[int]:
    """Queue a 'panic stop' DM."""
    import datetime
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    msg = (
        "Hermes PANIC STOP engaged\n\n"
        f"Timestamp: {ts}\n"
        "All autonomous flags set. No further autonomous actions will occur.\n\n"
        "To resume: run hermes-resume.sh (staged tier-by-tier)."
    )
    return _enqueue("panic-stop", msg)


def notify_fix_skipped_too_big(
    fix_id: str,
    target: str,
    reason: str,
    diff_lines: int,
    diff_path: str,
    max_lines: int,
) -> Optional[int]:
    """Queue a 'diff too big to auto-apply' DM."""
    msg = (
        "Hermes proposed a fix too large to auto-apply\n\n"
        f"Target: {target}\n"
        f"Reason: {reason}\n"
        f"Diff size: {diff_lines} lines (cap: {max_lines})\n\n"
        f"Full diff saved to: {diff_path}\n\n"
        "Review manually and apply if desired."
    )
    return _enqueue(fix_id, msg)


def main() -> int:
    parser = argparse.ArgumentParser(description="Hermes notify CLI")
    parser.add_argument("--panic-stop-engaged", action="store_true",
                        help="Send a panic-stop notification.")
    parser.add_argument("--test", action="store_true",
                        help="Send a test DM to the resolved operator.")
    args = parser.parse_args()

    if args.panic_stop_engaged:
        qid = notify_panic_stop_engaged()
        print(f"queued: {qid}")
        return 0 if qid is not None else 1

    if args.test:
        qid = _enqueue(
            "test", "Hermes notify test — if you see this, the pipeline works.")
        print(f"queued: {qid}")
        return 0 if qid is not None else 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
