#!/usr/bin/env python3
"""
worktree_cleanup.py — Daily cleanup of merged/stale git worktrees.

Invoked by launchd at 3:00 AM. For each project in PROJECT_REGISTRY:
  1. List worktrees
  2. For worktrees older than 48h: check if their PR was merged/closed
  3. Remove merged/closed worktrees
  4. Run git worktree prune

Safe to run repeatedly — all operations are idempotent.
"""

import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from kurultai_paths import PROJECT_REGISTRY

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(
            Path.home() / ".openclaw" / "agents" / "main" / "logs" / "worktree-cleanup.log"
        ),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("worktree-cleanup")


def run(cmd: list[str], cwd: str | None = None, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=30, check=check)


def list_worktrees(project_root: str) -> list[dict]:
    """Return list of {path, branch, head, is_main} dicts."""
    result = run(["git", "worktree", "list", "--porcelain"], cwd=project_root)
    if result.returncode != 0:
        return []

    worktrees = []
    current: dict = {}
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            if current:
                worktrees.append(current)
            current = {"path": line.split(" ", 1)[1], "branch": None, "head": None}
        elif line.startswith("HEAD "):
            current["head"] = line.split(" ", 1)[1]
        elif line.startswith("branch "):
            current["branch"] = line.split(" ", 1)[1].replace("refs/heads/", "")
        elif line == "bare":
            current["is_bare"] = True
    if current:
        worktrees.append(current)

    return worktrees


def is_old_worktree(worktree_path: str, min_age_hours: int = 48) -> bool:
    """Return True if the worktree directory is older than min_age_hours."""
    try:
        stat = Path(worktree_path).stat()
        age_hours = (datetime.now(timezone.utc).timestamp() - stat.st_mtime) / 3600
        return age_hours > min_age_hours
    except Exception:
        return False


def pr_is_done(repo: str, branch: str) -> bool:
    """Return True if the PR for this branch is merged or closed."""
    result = run(
        ["gh", "pr", "view", branch, "--repo", repo, "--json", "state"],
    )
    if result.returncode != 0:
        # No PR found — branch may have been force-pushed or PR never created
        return False
    try:
        data = json.loads(result.stdout)
        return data.get("state") in ("MERGED", "CLOSED")
    except Exception:
        return False


def remove_worktree(project_root: str, worktree_path: str, branch: str | None) -> bool:
    """Force-remove a worktree and delete its branch."""
    result = run(["git", "worktree", "remove", "--force", worktree_path], cwd=project_root)
    if result.returncode != 0:
        logger.warning(f"Failed to remove worktree {worktree_path}: {result.stderr}")
        return False

    if branch:
        run(["git", "branch", "-D", branch], cwd=project_root)
        logger.info(f"Deleted branch {branch}")

    logger.info(f"Removed worktree {worktree_path}")
    return True


def cleanup_project(project_root: str, config: dict) -> dict:
    repo = config["repo"]
    stats = {"checked": 0, "removed": 0, "preserved": 0, "errors": 0}

    worktrees = list_worktrees(project_root)
    if not worktrees:
        logger.info(f"No worktrees found for {config['name']}")
        return stats

    for wt in worktrees:
        branch = wt.get("branch")
        path = wt.get("path", "")

        # Skip main worktree
        if path == project_root or not branch or branch in ("main", "master", "HEAD"):
            continue

        # Only clean up task-* branches created by the executor
        if not branch.startswith("task-"):
            continue

        stats["checked"] += 1

        if not is_old_worktree(path):
            logger.debug(f"Worktree {path} is fresh, skipping")
            stats["preserved"] += 1
            continue

        if not pr_is_done(repo, branch):
            logger.info(f"PR for {branch} still open, preserving worktree")
            stats["preserved"] += 1
            continue

        if remove_worktree(project_root, path, branch):
            stats["removed"] += 1
        else:
            stats["errors"] += 1

    # Always prune stale git worktree refs
    prune_result = run(["git", "worktree", "prune"], cwd=project_root)
    if prune_result.returncode != 0:
        logger.warning(f"git worktree prune failed for {config['name']}: {prune_result.stderr}")

    return stats


def main():
    logger.info("=== Worktree cleanup started ===")
    total = {"checked": 0, "removed": 0, "preserved": 0, "errors": 0}

    for project_root, config in PROJECT_REGISTRY.items():
        if not Path(project_root).exists():
            logger.warning(f"Project root not found: {project_root}")
            continue

        logger.info(f"Cleaning {config['name']} ({project_root})")
        try:
            stats = cleanup_project(project_root, config)
            for k in total:
                total[k] += stats[k]
            logger.info(f"  {config['name']}: {stats}")
        except Exception as e:
            logger.error(f"Error cleaning {config['name']}: {e}")
            total["errors"] += 1

    logger.info(f"=== Cleanup complete: {total} ===")
    return 0 if total["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
