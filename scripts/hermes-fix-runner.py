#!/usr/bin/env python3
"""Hermes fix-job queue consumer.

Runs on a cron cadence (every 5 min). Claims up to N pending fix-job
files atomically, dispatches each to hermes-fix-content.py or
hermes-fix-code.py, and moves the job file to done/failed/rate-limited
based on the outcome.

Fix-job JSON schema (pending/*.json):
  {
    "fix_id": "<uuid>",
    "target": "/absolute/path.ext",
    "reason": "short human-readable reason",
    "autonomy_level": "content" | "code",
    "origin": "detection:check_quality_gate_drift" | "sweep:knowledge_stale" | ...,
    "enqueued_at": "<iso8601>"
  }

Claim protocol: atomic rename from pending/ to in-progress/ — at most
one runner can claim a given job.

Circuit-breaker integration:
  - Before claiming: check ~/.openclaw/flags/hermes-autonomous-disabled.flag
    → if present, skip this run entirely
  - After each job: check again; if breaker tripped mid-run, release
    remaining in-progress jobs back to pending/
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

QUEUE_ROOT = Path.home() / ".openclaw" / "queues" / "hermes-fix-jobs"
PENDING = QUEUE_ROOT / "pending"
IN_PROGRESS = QUEUE_ROOT / "in-progress"
DONE = QUEUE_ROOT / "done"
FAILED = QUEUE_ROOT / "failed"
RATE_LIMITED = QUEUE_ROOT / "rate-limited"

MAX_JOBS_PER_RUN = 3
FIX_TIMEOUT_SECS = 600
AUTONOMOUS_DISABLED_FLAG = Path.home() / ".openclaw" / "flags" / "hermes-autonomous-disabled.flag"

SCRIPTS_DIR = Path(__file__).resolve().parent


def _autonomous_disabled() -> bool:
    try:
        return AUTONOMOUS_DISABLED_FLAG.exists()
    except OSError:
        return True


def _list_pending() -> list[Path]:
    if not PENDING.exists():
        return []
    return sorted(PENDING.glob("*.json"))


def _claim(job_path: Path) -> Path | None:
    """Atomic move from pending/ to in-progress/. Returns new path or None."""
    IN_PROGRESS.mkdir(parents=True, exist_ok=True)
    dest = IN_PROGRESS / job_path.name
    try:
        # os.rename is atomic within the same filesystem
        os.rename(str(job_path), str(dest))
        return dest
    except OSError:
        return None


def _move(src: Path, target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / src.name
    try:
        os.rename(str(src), str(dest))
    except OSError:
        # Last-ditch: copy + unlink
        try:
            dest.write_bytes(src.read_bytes())
            src.unlink()
        except OSError:
            pass
    return dest


def _release(src: Path) -> Path:
    """Move back to pending/ (used when breaker trips mid-run)."""
    return _move(src, PENDING)


def _dispatch(job: dict) -> dict:
    """Invoke the appropriate authoring script. Returns the result dict."""
    target = job.get("target")
    reason = job.get("reason", "auto-fix")
    level = job.get("autonomy_level", "content")
    if level not in ("content", "code"):
        return {"outcome": "UNKNOWN_LEVEL", "level": level}
    script = SCRIPTS_DIR / f"hermes-fix-{level}.py"
    if not script.exists():
        return {"outcome": "SCRIPT_MISSING", "script": str(script)}
    try:
        result = subprocess.run(
            ["python3", str(script),
             "--target", target, "--reason", reason],
            capture_output=True, text=True, timeout=FIX_TIMEOUT_SECS,
        )
    except subprocess.TimeoutExpired:
        return {"outcome": "DISPATCH_TIMEOUT"}
    try:
        return json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        return {
            "outcome": f"RC_{result.returncode}",
            "stdout_tail": result.stdout[-400:],
            "stderr_tail": result.stderr[-400:],
        }


def _final_bucket(outcome: str) -> Path:
    """Map an outcome to the bucket where the job file belongs."""
    if outcome == "applied":
        return DONE
    if outcome == "RATE_LIMITED":
        return RATE_LIMITED
    return FAILED


def run(max_jobs: int = MAX_JOBS_PER_RUN) -> dict:
    """Main loop. Returns a summary dict."""
    if _autonomous_disabled():
        return {"outcome": "DISABLED", "reason": "autonomous flag engaged"}

    QUEUE_ROOT.mkdir(parents=True, exist_ok=True)
    for d in (PENDING, IN_PROGRESS, DONE, FAILED, RATE_LIMITED):
        d.mkdir(parents=True, exist_ok=True)

    pending_files = _list_pending()
    summary: dict = {"total_pending": len(pending_files), "processed": []}

    for job_path in pending_files[:max_jobs]:
        if _autonomous_disabled():
            # Breaker tripped mid-run — release any in-progress jobs
            summary["aborted"] = True
            break

        claimed = _claim(job_path)
        if claimed is None:
            # Another runner won the race
            continue

        try:
            job_data = json.loads(claimed.read_text())
        except (OSError, json.JSONDecodeError) as e:
            _move(claimed, FAILED)
            summary["processed"].append({
                "file": claimed.name,
                "outcome": "SCHEMA_ERROR",
                "error": str(e),
            })
            continue

        result = _dispatch(job_data)
        outcome = result.get("outcome", "UNKNOWN")
        bucket = _final_bucket(outcome)

        # Write the result next to the job file for audit
        result_path = claimed.with_suffix(".result.json")
        try:
            result_path.write_text(json.dumps(result, indent=2, default=str))
            _move(result_path, bucket)
        except OSError:
            pass

        final = _move(claimed, bucket)
        summary["processed"].append({
            "file": final.name,
            "outcome": outcome,
            "target": job_data.get("target"),
            "autonomy_level": job_data.get("autonomy_level"),
        })

    return summary


def enqueue_fix_job(
    target: str, reason: str, autonomy_level: str,
    origin: str = "manual",
) -> str:
    """Helper used by detection checks to enqueue a new fix-job.

    Returns the fix_id. Performs per-target-per-hour dedup: if a pending
    job for the same target already exists with age < 1 hour, no new
    enqueue happens.
    """
    import datetime
    PENDING.mkdir(parents=True, exist_ok=True)

    # Per-target-per-hour dedup: skip if a recent pending job exists for
    # the same target.
    now = time.time()
    for existing in PENDING.glob("*.json"):
        try:
            data = json.loads(existing.read_text())
            if data.get("target") == target and (now - existing.stat().st_mtime) < 3600:
                return data.get("fix_id", existing.stem)
        except (OSError, json.JSONDecodeError):
            continue

    fix_id = str(uuid.uuid4())
    job = {
        "fix_id": fix_id,
        "target": target,
        "reason": reason,
        "autonomy_level": autonomy_level,
        "origin": origin,
        "enqueued_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    path = PENDING / f"{fix_id}.json"
    path.write_text(json.dumps(job, indent=2))
    return fix_id


def main() -> int:
    parser = argparse.ArgumentParser(description="Hermes fix-job runner")
    parser.add_argument("--max", type=int, default=MAX_JOBS_PER_RUN)
    parser.add_argument("--enqueue", action="store_true",
                        help="Enqueue a job from stdin JSON instead of running")
    args = parser.parse_args()

    if args.enqueue:
        job = json.loads(sys.stdin.read())
        fix_id = enqueue_fix_job(
            target=job["target"],
            reason=job["reason"],
            autonomy_level=job["autonomy_level"],
            origin=job.get("origin", "stdin"),
        )
        print(json.dumps({"enqueued": fix_id}))
        return 0

    summary = run(max_jobs=args.max)
    print(json.dumps(summary, indent=2, default=str))
    return 0 if summary.get("outcome") != "ERROR" else 1


if __name__ == "__main__":
    sys.exit(main())
