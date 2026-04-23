#!/usr/bin/env python3
from __future__ import annotations
"""
Git Branch Manager — Safe git branch operations for Kurultai autoresearch.

Provides isolated branch creation, safe merging, and rollback capability for
autonomous experiments run by Kurultai agents.

Usage:
    from git_branch_manager import GitBranchManager

    manager = GitBranchManager(repo_path=Path.home() / ".openclaw")
    branch = manager.create_experiment_branch("exp-20260308-001", "temujin", "router-lr-tuning")
    result = manager.merge_to_main(branch, "exp-20260308-001")
    manager.discard_branch(branch)
    manager.rollback(commit_hash, "regression detected")
"""


import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

# Import from canonical source
import sys
sys.path.insert(0, str(Path(__file__).parent))
from kurultai_paths import VALID_AGENTS as _VALID_AGENTS

# Configure logging
logger = logging.getLogger(__name__)


class BranchStatus(Enum):
    """Status of a git branch."""
    CLEAN = "clean"
    CONFLICTS = "conflicts"
    NOT_FOUND = "not_found"
    PROTECTED = "protected"
    DIVERGED = "diverged"


class MergeResult(Enum):
    """Result of a merge operation."""
    SUCCESS = "success"
    CONFLICTS = "conflicts"
    PROTECTED_BRANCH = "protected_branch"
    VALIDATION_FAILED = "validation_failed"
    NOT_FOUND = "not_found"
    ERROR = "error"


@dataclass
class MergeInfo:
    """Detailed information about a merge result."""
    result: MergeResult
    commit_hash: str = ""
    message: str = ""
    conflicts: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# Protected branch patterns - never auto-merge to these
PROTECTED_PATTERNS = [
    r"^main$",
    r"^prod/",
    r"^release/",
    r"^master$",  # Some repos use master
]

# Agents that can create experiment branches (imported from kurultai_paths)
VALID_AGENTS = list(_VALID_AGENTS)


class GitBranchManager:
    """
    Manages git branches for autonomous experiments.

    Provides safe branch creation, merging, and rollback operations
    with conflict detection and protected branch enforcement.
    """

    def __init__(
        self,
        repo_path: Path | str = None,
        remote: str = "origin",
        dry_run: bool = False
    ):
        """
        Initialize the GitBranchManager.

        Args:
            repo_path: Path to git repository (defaults to ~/.openclaw)
            remote: Name of the remote (default: origin)
            dry_run: If True, print commands without executing
        """
        self.repo_path = Path(repo_path) if repo_path else Path.home() / ".openclaw"
        self.remote = remote
        self.dry_run = dry_run
        self._operations_log: list[dict] = []

        # Validate repo exists
        if not (self.repo_path / ".git").exists():
            raise ValueError(f"Not a git repository: {self.repo_path}")

    def _run_git(
        self,
        args: list[str],
        check: bool = True,
        capture: bool = True
    ) -> subprocess.CompletedProcess:
        """
        Run a git command in the repository.

        Args:
            args: Git arguments (without 'git' prefix)
            check: Raise exception on non-zero exit
            capture: Capture stdout/stderr

        Returns:
            CompletedProcess result
        """
        cmd = ["git"] + args
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "command": " ".join(cmd),
            "dry_run": self.dry_run
        }

        if self.dry_run:
            logger.info(f"[DRY RUN] Would run: {' '.join(cmd)}")
            log_entry["status"] = "dry_run"
            self._operations_log.append(log_entry)
            # Return strings like the real subprocess.run with text=True
            return subprocess.CompletedProcess(
                cmd, 0, "", ""
            )

        try:
            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=capture,
                text=capture,
                check=check
            )
            log_entry["status"] = "success" if result.returncode == 0 else "failed"
            log_entry["returncode"] = result.returncode
            self._operations_log.append(log_entry)
            return result
        except subprocess.CalledProcessError as e:
            log_entry["status"] = "error"
            log_entry["returncode"] = e.returncode
            log_entry["error"] = str(e)
            self._operations_log.append(log_entry)
            raise

    def _is_protected_branch(self, branch: str) -> bool:
        """Check if branch is protected (should never auto-merge)."""
        for pattern in PROTECTED_PATTERNS:
            if re.match(pattern, branch):
                return True
        return False

    def _slugify(self, text: str, max_length: int = 30) -> str:
        """Convert text to URL-safe slug."""
        # Remove non-alphanumeric chars, convert to lowercase, replace spaces with hyphens
        slug = re.sub(r'[^a-zA-Z0-9\s-]', '', text)
        slug = slug.strip().lower()
        slug = re.sub(r'[\s_]+', '-', slug)
        slug = slug.strip('-')
        return slug[:max_length]

    def _validate_agent(self, agent: str) -> bool:
        """Validate agent name."""
        if agent not in VALID_AGENTS:
            raise ValueError(f"Invalid agent: {agent}. Must be one of {VALID_AGENTS}")
        return True

    def _has_uncommitted_changes(self) -> bool:
        """Check if working directory has uncommitted changes."""
        result = self._run_git(["status", "--porcelain"], check=False)
        return bool(result.stdout.strip())

    def _get_current_branch(self) -> str:
        """Get current branch name."""
        result = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"])
        return result.stdout.strip()

    def _get_base_commit(self, branch: str | None = None) -> str:
        """Get the base commit (HEAD or branch tip)."""
        if branch:
            result = self._run_git(["rev-parse", branch])
        else:
            result = self._run_git(["rev-parse", "HEAD"])
        return result.stdout.strip()

    def _detect_conflicts(self, target_branch: str, source_branch: str) -> list[str]:
        """
        Detect potential merge conflicts without actually merging.

        Returns list of files that would conflict.
        """
        try:
            # Try a merge --no-commit --no-ff to detect conflicts
            current = self._get_current_branch()

            # Stash current changes if any
            self._run_git(["stash", "push", "-m", "git-branch-manager-temp"], check=False)

            # Checkout target
            self._run_git(["checkout", target_branch])

            # Try merge
            result = self._run_git(
                ["merge", "--no-commit", "--no-ff", source_branch],
                check=False
            )

            # Check for conflict markers
            conflicts = []
            if result.returncode != 0:
                # Git reported conflict - get the files
                conflict_result = self._run_git(["diff", "--name-only", "--diff-filter=U"], check=False)
                conflicts = conflict_result.stdout.strip().split("\n") if conflict_result.stdout.strip() else []

            # Abort the merge attempt
            self._run_git(["merge", "--abort"], check=False)

            # Return to original branch
            self._run_git(["checkout", current])
            self._run_git(["stash", "pop"], check=False)

            return [f for f in conflicts if f]

        except Exception as e:
            logger.error(f"Error detecting conflicts: {e}")
            # Try to recover
            try:
                self._run_git(["merge", "--abort"], check=False)
            except Exception:
                pass
            return []

    def create_experiment_branch(
        self,
        exp_id: str,
        agent: str,
        description: str,
        base_branch: str = "main"
    ) -> str:
        """
        Create a new experiment branch with proper naming convention.

        Args:
            exp_id: Experiment ID (e.g., "exp-20260308-001")
            agent: Agent name creating the experiment
            description: Human-readable description for the slug
            base_branch: Branch to base the experiment on (default: main)

        Returns:
            The created branch name

        Raises:
            ValueError: If agent is invalid or uncommitted changes exist
            RuntimeError: If branch creation fails
        """
        self._validate_agent(agent)

        # Check for uncommitted changes
        if self._has_uncommitted_changes():
            raise RuntimeError(
                "Cannot create branch: uncommitted changes exist. "
                "Commit or stash changes first."
            )

        # Check if base branch exists
        result = self._run_git(["rev-parse", "--verify", base_branch], check=False)
        if result.returncode != 0:
            raise ValueError(f"Base branch does not exist: {base_branch}")

        # Generate branch name
        slug = self._slugify(description)
        branch_name = f"experiment/{agent}/{exp_id}/{slug}"

        # Check if branch already exists
        existing = self._run_git(
            ["rev-parse", "--verify", branch_name],
            check=False
        )
        if existing.returncode == 0:
            logger.warning(f"Branch already exists: {branch_name}")
            return branch_name

        # Ensure we're on base branch
        current = self._get_current_branch()
        if current != base_branch:
            self._run_git(["checkout", base_branch])

        # Pull latest changes
        self._run_git(["pull", self.remote, base_branch], check=False)

        # Create and checkout the branch
        self._run_git(["checkout", "-b", branch_name])

        # Record base commit for potential rollback
        base_commit = self._get_base_commit()
        self._save_experiment_metadata(exp_id, {
            "branch": branch_name,
            "agent": agent,
            "description": description,
            "base_commit": base_commit,
            "created_at": datetime.now(timezone.utc).isoformat()
        })

        logger.info(f"Created experiment branch: {branch_name}")
        return branch_name

    def merge_to_main(
        self,
        branch: str,
        exp_id: str,
        target_branch: str = "main",
        validate: bool = True
    ) -> MergeInfo:
        """
        Merge an experiment branch to main with safety checks.

        Args:
            branch: The experiment branch to merge
            exp_id: Experiment ID for metadata tracking
            target_branch: Target branch (default: main)
            validate: Run validation before merge

        Returns:
            MergeInfo with result details
        """
        # Check if target is protected
        if self._is_protected_branch(target_branch):
            return MergeInfo(
                result=MergeResult.PROTECTED_BRANCH,
                message=f"Cannot auto-merge to protected branch: {target_branch}"
            )

        # Check if branch exists
        result = self._run_git(["rev-parse", "--verify", branch], check=False)
        if result.returncode != 0:
            return MergeInfo(
                result=MergeResult.NOT_FOUND,
                message=f"Branch not found: {branch}"
            )

        # Store current branch
        current_branch = self._get_current_branch()

        try:
            # Check for conflicts first
            if validate:
                conflicts = self._detect_conflicts(target_branch, branch)
                if conflicts:
                    return MergeInfo(
                        result=MergeResult.CONFLICTS,
                        message=f"Merge conflicts detected in {len(conflicts)} files",
                        conflicts=conflicts
                    )

            # Checkout target branch
            self._run_git(["checkout", target_branch])

            # Pull latest
            self._run_git(["pull", self.remote, target_branch], check=False)

            # Merge with --no-ff to preserve history
            result = self._run_git(
                ["merge", "--no-ff", "--no-edit", branch],
                check=False
            )

            if result.returncode != 0:
                # Merge failed - abort and report
                self._run_git(["merge", "--abort"], check=False)

                # Get conflict files
                conflict_result = self._run_git(
                    ["diff", "--name-only", "--diff-filter=U"],
                    check=False
                )
                conflicts = conflict_result.stdout.strip().split("\n")

                return MergeInfo(
                    result=MergeResult.CONFLICTS,
                    message="Merge failed due to conflicts",
                    conflicts=[f for f in conflicts if f]
                )

            # Get merge commit hash
            merge_commit = self._get_base_commit()

            # Update metadata
            self._save_experiment_metadata(exp_id, {
                "merged_at": datetime.now(timezone.utc).isoformat(),
                "merge_commit": merge_commit,
                "merge_target": target_branch,
                "status": "merged"
            })

            logger.info(f"Merged {branch} to {target_branch} at {merge_commit}")

            return MergeInfo(
                result=MergeResult.SUCCESS,
                commit_hash=merge_commit,
                message=f"Successfully merged {branch} to {target_branch}"
            )

        except Exception as e:
            # Try to recover
            try:
                self._run_git(["merge", "--abort"], check=False)
                self._run_git(["checkout", current_branch], check=False)
            except Exception:
                pass

            return MergeInfo(
                result=MergeResult.ERROR,
                message=f"Merge error: {str(e)}"
            )

    def discard_branch(self, branch: str, force: bool = False) -> bool:
        """
        Delete an experiment branch.

        Args:
            branch: Branch name to delete
            force: Force delete even if unmerged

        Returns:
            True if deleted, False otherwise
        """
        # Never delete protected branches
        if self._is_protected_branch(branch):
            logger.error(f"Refusing to delete protected branch: {branch}")
            return False

        # Check if currently on the branch
        current = self._get_current_branch()
        if current == branch:
            # Switch to main first
            self._run_git(["checkout", "main"], check=False)

        # Delete the branch
        args = ["branch", "-D" if force else "-d", branch]
        result = self._run_git(args, check=False)

        if result.returncode == 0:
            logger.info(f"Deleted branch: {branch}")
            return True
        else:
            logger.warning(f"Failed to delete branch {branch}: {result.stderr}")
            return False

    def rollback(self, commit_hash: str, reason: str, create_branch: bool = False) -> bool:
        """
        Revert to a previous commit.

        Creates a revert commit that undoes the specified commit.

        Args:
            commit_hash: Commit hash to revert
            reason: Reason for rollback
            create_branch: If True, create a rollback branch instead of reverting on main

        Returns:
            True if rollback succeeded, False otherwise
        """
        current = self._get_current_branch()

        # Refuse to rollback on protected branches without explicit branch creation
        if self._is_protected_branch(current) and not create_branch:
            logger.error(
                f"Refusing to rollback on protected branch: {current}. "
                "Set create_branch=True to create a rollback branch first."
            )
            return False

        try:
            if create_branch:
                # Create a rollback branch from the target commit
                branch_name = f"rollback/{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
                self._run_git(["checkout", "-b", branch_name, commit_hash])
                logger.info(f"Created rollback branch: {branch_name}")
                return True

            # Revert the commit
            result = self._run_git(
                ["revert", "--no-edit", commit_hash],
                check=False
            )

            if result.returncode != 0:
                # Revert had conflicts - abort
                self._run_git(["revert", "--abort"], check=False)
                logger.error(f"Revert failed due to conflicts: {commit_hash}")
                return False

            # Log the rollback
            self._save_rollback_record({
                "commit_reverted": commit_hash,
                "reason": reason,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "branch": current
            })

            logger.info(f"Reverted commit {commit_hash[:7]}: {reason}")
            return True

        except Exception as e:
            logger.error(f"Rollback error: {e}")
            return False

    def get_branch_status(self, branch: str) -> tuple[BranchStatus, dict]:
        """
        Check the status of a branch.

        Args:
            branch: Branch name to check

        Returns:
            Tuple of (BranchStatus, info_dict)
        """
        # Check if branch exists
        result = self._run_git(
            ["rev-parse", "--verify", branch],
            check=False
        )

        if result.returncode != 0:
            return (BranchStatus.NOT_FOUND, {"exists": False})

        # Check if protected
        if self._is_protected_branch(branch):
            return (BranchStatus.PROTECTED, {"exists": True, "protected": True})

        # Get ahead/behind info
        current = self._get_current_branch()

        # Check if diverged from main
        try:
            # Get merge base
            merge_base = self._run_git(
                ["merge-base", "main", branch],
                check=False
            ).stdout.strip()

            # Get main tip
            main_tip = self._run_git(
                ["rev-parse", "main"],
                check=False
            ).stdout.strip()

            # Get branch tip
            branch_tip = self._run_git(
                ["rev-parse", branch],
                check=False
            ).stdout.strip()

            # Check for potential conflicts
            conflicts = self._detect_conflicts("main", branch)

            info = {
                "exists": True,
                "protected": False,
                "branch_tip": branch_tip[:7],
                "merge_base": merge_base[:7] if merge_base else None,
                "potential_conflicts": len(conflicts),
                "conflict_files": conflicts
            }

            if merge_base == main_tip:
                status = BranchStatus.CLEAN
            elif conflicts:
                status = BranchStatus.CONFLICTS
            else:
                status = BranchStatus.DIVERGED

            return (status, info)

        except Exception as e:
            logger.error(f"Error getting branch status: {e}")
            return (BranchStatus.CLEAN, {"exists": True, "error": str(e)})

    def list_experiment_branches(self, agent: str | None = None) -> list[dict]:
        """
        List all experiment branches, optionally filtered by agent.

        Args:
            agent: Optional agent name to filter by

        Returns:
            List of branch info dicts
        """
        # Get all branches matching experiment/ prefix
        result = self._run_git(
            ["for-each-ref", "--format=%(refname:short)%00%(committerdate:iso8601)", "refs/heads/experiment/"],
            check=False
        )

        branches = []
        if not result.stdout or not result.stdout.strip():
            return branches

        # Ensure stdout is string
        output = result.stdout if isinstance(result.stdout, str) else result.stdout.decode('utf-8', errors='ignore')

        for line in output.strip().split("\n"):
            if not line:
                continue

            parts = line.split("\x00")
            if len(parts) < 2:
                continue

            branch_name = parts[0]
            date_str = parts[1]

            # Parse branch components
            match = re.match(r'^experiment/([^/]+)/([^/]+)/(.+)$', branch_name)
            if not match:
                continue

            branch_agent, exp_id, slug = match.groups()

            # Filter by agent if specified
            if agent and branch_agent != agent:
                continue

            # Get last commit
            commit_result = self._run_git(
                ["log", "-1", "--format=%h %s", branch_name],
                check=False
            )

            last_commit = ""
            if commit_result.returncode == 0:
                last_commit = commit_result.stdout.strip()

            branches.append({
                "name": branch_name,
                "agent": branch_agent,
                "exp_id": exp_id,
                "slug": slug,
                "created": date_str,
                "last_commit": last_commit
            })

        return sorted(branches, key=lambda x: x["created"], reverse=True)

    def _save_experiment_metadata(self, exp_id: str, metadata: dict) -> None:
        """Save experiment metadata to storage."""
        metadata_dir = self.repo_path / "data" / "experiments"
        metadata_dir.mkdir(parents=True, exist_ok=True)

        metadata_file = metadata_dir / f"{exp_id}.json"

        # Load existing or create new
        if metadata_file.exists():
            with open(metadata_file, "r") as f:
                existing = json.load(f)
            existing.update(metadata)
            metadata = existing

        with open(metadata_file, "w") as f:
            json.dump(metadata, f, indent=2)

    def _save_rollback_record(self, record: dict) -> None:
        """Save rollback record to ledger."""
        ledger_dir = self.repo_path / "data" / "rollbacks"
        ledger_dir.mkdir(parents=True, exist_ok=True)

        ledger_file = ledger_dir / "ledger.jsonl"

        with open(ledger_file, "a") as f:
            f.write(json.dumps(record) + "\n")

    def get_operations_log(self) -> list[dict]:
        """Return log of all git operations performed."""
        return self._operations_log.copy()


# CLI interface for testing
def main():
    """CLI interface for git branch manager operations."""
    import argparse

    parser = argparse.ArgumentParser(description="Git Branch Manager for Kurultai")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Create branch command
    create_parser = subparsers.add_parser("create", help="Create experiment branch")
    create_parser.add_argument("exp_id", help="Experiment ID")
    create_parser.add_argument("agent", help="Agent name")
    create_parser.add_argument("description", help="Branch description")
    create_parser.add_argument("--base", default="main", help="Base branch")

    # Merge command
    merge_parser = subparsers.add_parser("merge", help="Merge branch to main")
    merge_parser.add_argument("branch", help="Branch to merge")
    merge_parser.add_argument("exp_id", help="Experiment ID")
    merge_parser.add_argument("--target", default="main", help="Target branch")

    # Discard command
    discard_parser = subparsers.add_parser("discard", help="Delete experiment branch")
    discard_parser.add_argument("branch", help="Branch to delete")
    discard_parser.add_argument("--force", action="store_true", help="Force delete")

    # Rollback command
    rollback_parser = subparsers.add_parser("rollback", help="Revert a commit")
    rollback_parser.add_argument("commit", help="Commit hash to revert")
    rollback_parser.add_argument("reason", help="Rollback reason")
    rollback_parser.add_argument("--branch", action="store_true", help="Create rollback branch")

    # Status command
    status_parser = subparsers.add_parser("status", help="Check branch status")
    status_parser.add_argument("branch", help="Branch to check")

    # List command
    list_parser = subparsers.add_parser("list", help="List experiment branches")
    list_parser.add_argument("--agent", help="Filter by agent")

    # Dry run option
    parser.add_argument("--dry-run", action="store_true", help="Print commands without executing")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Initialize manager
    manager = GitBranchManager(dry_run=getattr(args, "dry_run", False))

    # Execute command
    if args.command == "create":
        branch = manager.create_experiment_branch(
            args.exp_id,
            args.agent,
            args.description,
            args.base
        )
        print(f"Created: {branch}")

    elif args.command == "merge":
        result = manager.merge_to_main(args.branch, args.exp_id, args.target)
        print(f"Result: {result.result.value}")
        if result.message:
            print(f"Message: {result.message}")
        if result.conflicts:
            print(f"Conflicts: {', '.join(result.conflicts)}")

    elif args.command == "discard":
        success = manager.discard_branch(args.branch, args.force)
        print(f"Deleted: {success}")

    elif args.command == "rollback":
        success = manager.rollback(args.commit, args.reason, args.branch)
        print(f"Rollback: {'success' if success else 'failed'}")

    elif args.command == "status":
        status, info = manager.get_branch_status(args.branch)
        print(f"Status: {status.value}")
        print(f"Info: {json.dumps(info, indent=2)}")

    elif args.command == "list":
        branches = manager.list_experiment_branches(args.agent)
        for b in branches:
            print(f"{b['name']} - {b['agent']} - {b['created']}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
