#!/usr/bin/env python3
"""
task_snapshot.py — Lightweight pre-task snapshots for rollback capability.

Usage (CLI):
    python3 task_snapshot.py create <agent> <task_id> <task_file>
    python3 task_snapshot.py restore <task_id>
    python3 task_snapshot.py list [--agent AGENT] [--limit N]
    python3 task_snapshot.py cleanup [--max-age-days N] [--max-count N]
    python3 task_snapshot.py get <task_id>
"""

import argparse
import hashlib
import json
import logging
import os
import subprocess
import tarfile
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

HOME = Path(os.environ["HOME"])
BACKUPS_DIR = HOME / ".openclaw" / "backups" / "tasks"
AGENTS_DIR = HOME / ".openclaw" / "agents"

EXCLUDE_DIRS = {".git", "node_modules", "__pycache__"}
EXCLUDE_SUFFIXES = {".log"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _build_manifest(workspace: Path) -> dict:
    manifest: dict = {}
    if not workspace.exists():
        return manifest
    for file in workspace.rglob("*"):
        if not file.is_file():
            continue
        # Skip excluded dirs anywhere in the path
        if any(part in EXCLUDE_DIRS for part in file.parts):
            continue
        if file.suffix in EXCLUDE_SUFFIXES:
            continue
        try:
            stat = file.stat()
            rel = str(file.relative_to(workspace))
            manifest[rel] = {
                "sha256": _sha256(file),
                "size": stat.st_size,
                "mtime": stat.st_mtime,
            }
        except OSError as exc:
            log.warning("Skipping %s: %s", file, exc)
    return manifest


def _git_info(directory: Path) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Return (commit_hash, branch, diff_stat) or (None, None, None)."""
    def run(args: list[str]) -> Optional[str]:
        try:
            result = subprocess.run(
                args,
                cwd=str(directory),
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None

    commit = run(["git", "rev-parse", "HEAD"])
    if commit is None:
        return None, None, None
    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    diff_stat = run(["git", "diff", "--stat", "HEAD"])
    # Collapse multi-line diff stat to single summary line (last line)
    if diff_stat:
        lines = [l for l in diff_stat.splitlines() if l.strip()]
        diff_stat = lines[-1] if lines else None
    return commit, branch, diff_stat


def _create_archive(workspace: Path, archive_path: Path) -> None:
    with tarfile.open(archive_path, "w:gz") as tar:
        for item in workspace.rglob("*"):
            if not item.is_file():
                continue
            if any(part in EXCLUDE_DIRS for part in item.parts):
                continue
            if item.suffix in EXCLUDE_SUFFIXES:
                continue
            try:
                tar.add(item, arcname=str(item.relative_to(workspace.parent)))
            except OSError as exc:
                log.warning("Skipping archive entry %s: %s", item, exc)


def _snapshot_dir(task_id: str) -> Path:
    return BACKUPS_DIR / task_id


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_snapshot(agent_name: str, task_id: str, task_file: str) -> dict:
    """Create a snapshot of the agent workspace before task execution.

    Returns the metadata dict written to snapshot.json.
    """
    workspace = AGENTS_DIR / agent_name
    snap_dir = _snapshot_dir(task_id)
    snap_dir.mkdir(parents=True, exist_ok=True)

    archive_path = snap_dir / "workspace.tar.gz"
    meta_path = snap_dir / "snapshot.json"

    log.info("Building file manifest for %s …", workspace)
    manifest = _build_manifest(workspace)

    log.info("Creating archive at %s …", archive_path)
    _create_archive(workspace, archive_path)
    archive_size = archive_path.stat().st_size if archive_path.exists() else 0

    commit, branch, diff_stat = _git_info(workspace)

    metadata = {
        "task_id": task_id,
        "agent": agent_name,
        "task_file": task_file,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_commit": commit,
        "git_branch": branch,
        "git_diff_stat": diff_stat,
        "workspace_dir": str(workspace),
        "file_count": len(manifest),
        "archive_size_bytes": archive_size,
        "archive_path": str(archive_path),
        "file_manifest": manifest,
    }

    meta_path.write_text(json.dumps(metadata, indent=2))
    log.info(
        "Snapshot created: %d files, %.1f KB",
        len(manifest),
        archive_size / 1024,
    )
    return metadata


def restore_snapshot(task_id: str) -> list[str]:
    """Restore workspace from a snapshot. Returns list of restored file paths."""
    snap_dir = _snapshot_dir(task_id)
    meta_path = snap_dir / "snapshot.json"

    if not meta_path.exists():
        raise FileNotFoundError(f"Snapshot not found for task_id={task_id!r}")

    metadata = json.loads(meta_path.read_text())
    archive_path = Path(metadata["archive_path"])

    if not archive_path.exists():
        raise FileNotFoundError(f"Archive missing: {archive_path}")

    workspace = Path(metadata["workspace_dir"])
    extract_root = workspace.parent  # archive stores paths relative to parent

    log.info("Restoring snapshot for task %s to %s …", task_id, extract_root)
    restored: list[str] = []

    with tarfile.open(archive_path, "r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            tar.extract(member, path=extract_root, filter="data")
            restored.append(str(extract_root / member.name))

    log.info("Restored %d files.", len(restored))
    return restored


def get_snapshot(task_id: str) -> Optional[dict]:
    """Return snapshot metadata or None if not found."""
    meta_path = _snapshot_dir(task_id) / "snapshot.json"
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Could not read snapshot %s: %s", task_id, exc)
        return None


def list_snapshots(agent: Optional[str] = None, limit: int = 50) -> list[dict]:
    """List snapshots, newest first. Optionally filter by agent name."""
    if not BACKUPS_DIR.exists():
        return []

    results: list[dict] = []
    for meta_path in BACKUPS_DIR.glob("*/snapshot.json"):
        try:
            data = json.loads(meta_path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if agent and data.get("agent") != agent:
            continue
        results.append(data)

    results.sort(key=lambda d: d.get("created_at", ""), reverse=True)
    return results[:limit]


def cleanup_old_snapshots(max_age_days: int = 30, max_count: int = 100) -> int:
    """Remove old snapshots. Returns number of snapshots deleted."""
    snapshots = list_snapshots(limit=10_000)
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    deleted = 0

    for i, snap in enumerate(snapshots):
        snap_dir = _snapshot_dir(snap["task_id"])
        should_delete = False

        # Too old
        try:
            created = datetime.strptime(snap["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            )
            if created < cutoff:
                should_delete = True
        except (ValueError, KeyError):
            pass

        # Beyond count limit (list is newest-first, so index >= max_count means old)
        if i >= max_count:
            should_delete = True

        if should_delete:
            try:
                for f in snap_dir.iterdir():
                    f.unlink()
                snap_dir.rmdir()
                deleted += 1
                log.info("Deleted snapshot %s", snap["task_id"])
            except OSError as exc:
                log.warning("Failed to delete snapshot %s: %s", snap["task_id"], exc)

    log.info("Cleanup complete: %d snapshot(s) removed.", deleted)
    return deleted


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli() -> None:
    parser = argparse.ArgumentParser(
        description="Manage pre-task snapshots for agent workspaces."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create", help="Create a snapshot")
    p_create.add_argument("agent", help="Agent name (e.g. temujin)")
    p_create.add_argument("task_id", help="Task ID")
    p_create.add_argument("task_file", help="Task filename")

    p_restore = sub.add_parser("restore", help="Restore from a snapshot")
    p_restore.add_argument("task_id", help="Task ID to restore")

    p_list = sub.add_parser("list", help="List snapshots")
    p_list.add_argument("--agent", default=None, help="Filter by agent name")
    p_list.add_argument("--limit", type=int, default=50, help="Max results")

    p_get = sub.add_parser("get", help="Print snapshot metadata")
    p_get.add_argument("task_id", help="Task ID")

    p_cleanup = sub.add_parser("cleanup", help="Remove old snapshots")
    p_cleanup.add_argument("--max-age-days", type=int, default=30)
    p_cleanup.add_argument("--max-count", type=int, default=100)

    args = parser.parse_args()

    if args.command == "create":
        meta = create_snapshot(args.agent, args.task_id, args.task_file)
        print(json.dumps(meta, indent=2))

    elif args.command == "restore":
        restored = restore_snapshot(args.task_id)
        print(f"Restored {len(restored)} file(s).")
        for f in restored:
            print(f"  {f}")

    elif args.command == "list":
        snaps = list_snapshots(agent=args.agent, limit=args.limit)
        if not snaps:
            print("No snapshots found.")
            return
        print(f"{'TASK_ID':<36}  {'AGENT':<12}  {'CREATED_AT':<22}  {'FILES':>6}  {'SIZE_KB':>8}")
        print("-" * 90)
        for s in snaps:
            size_kb = s.get("archive_size_bytes", 0) / 1024
            print(
                f"{s['task_id']:<36}  {s.get('agent','?'):<12}  "
                f"{s.get('created_at','?'):<22}  {s.get('file_count',0):>6}  {size_kb:>8.1f}"
            )

    elif args.command == "get":
        snap = get_snapshot(args.task_id)
        if snap is None:
            print(f"Snapshot not found: {args.task_id}")
            raise SystemExit(1)
        print(json.dumps(snap, indent=2))

    elif args.command == "cleanup":
        count = cleanup_old_snapshots(
            max_age_days=args.max_age_days,
            max_count=args.max_count,
        )
        print(f"Deleted {count} snapshot(s).")


if __name__ == "__main__":
    _cli()
