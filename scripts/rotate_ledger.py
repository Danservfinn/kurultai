#!/usr/bin/env python3
"""Daily ledger rotation: archive events older than 14 days."""
from __future__ import annotations
import fcntl
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from kurultai_paths import TASK_LEDGER

ARCHIVE_DIR = TASK_LEDGER.parent
RETENTION_DAYS = 14


def rotate() -> None:
    if not TASK_LEDGER.exists():
        print("Ledger not found — nothing to rotate")
        return

    cutoff = (datetime.now() - timedelta(days=RETENTION_DAYS)).isoformat()
    keep: list[str] = []
    archive_buckets: dict[str, list[str]] = {}  # YYYY-MM -> lines

    with open(TASK_LEDGER, "r+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    ev = json.loads(stripped)
                    ts = ev.get("ts", "")
                    if ts and ts < cutoff:
                        bucket = ts[:7]  # YYYY-MM
                        archive_buckets.setdefault(bucket, []).append(stripped)
                    else:
                        keep.append(stripped)
                except json.JSONDecodeError:
                    keep.append(stripped)
            f.seek(0)
            f.truncate()
            for line in keep:
                f.write(line + "\n")
            f.flush()
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)

    archived_count = sum(len(v) for v in archive_buckets.values())
    print(f"Kept {len(keep)} events, archiving {archived_count} events")

    for bucket, lines in archive_buckets.items():
        archive_path = ARCHIVE_DIR / f"task-ledger-archive-{bucket}.jsonl"
        tmp_path = archive_path.with_suffix(".tmp")
        existing: list[str] = []
        if archive_path.exists():
            with open(archive_path, "r") as af:
                fcntl.flock(af, fcntl.LOCK_SH)
                try:
                    existing = [ln.strip() for ln in af if ln.strip()]
                finally:
                    fcntl.flock(af, fcntl.LOCK_UN)
        with open(tmp_path, "w") as tf:
            fcntl.flock(tf, fcntl.LOCK_EX)
            try:
                for ln in existing + lines:
                    tf.write(ln + "\n")
                tf.flush()
            finally:
                fcntl.flock(tf, fcntl.LOCK_UN)
        os.replace(tmp_path, archive_path)
        print(f"  Archived {len(lines)} events to {archive_path.name}")


if __name__ == "__main__":
    rotate()
