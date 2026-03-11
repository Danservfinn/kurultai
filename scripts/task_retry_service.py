#!/usr/bin/env python3
"""
task_retry_service.py — Task retry service for Kurultai multi-agent system.

Provides core logic for retrying failed tasks, including file operations,
state management, and retry history tracking.

Usage:
    from task_retry_service import TaskRetryService

    service = TaskRetryService()
    result = service.retry_task("temujin", "high-1773165922.failed.done.md")
"""

import json
import logging
import os
import re
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Literal

from kurultai_paths import (
    AGENTS_DIR,
    VALID_AGENTS,
    agent_tasks_dir,
    WATCHER_STATE,
    LOGS_DIR
)

# Set up logging
RETRY_LOG_DIR = LOGS_DIR / "task-retry"
RETRY_LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(RETRY_LOG_DIR / "retry.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("task-retry")


@dataclass
class TaskInfo:
    """Information about a failed task."""
    agent: str
    task_id: str
    filename: str
    title: str
    priority: str
    failed_at: Optional[str] = None
    error: Optional[str] = None
    retry_count: int = 0

    def to_dict(self):
        return asdict(self)


@dataclass
class RetryResult:
    """Result of a retry operation."""
    success: bool
    agent: str
    old_file: str
    new_file: Optional[str] = None
    retry_count: int = 0
    retry_at: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self):
        return asdict(self)


class TaskRetryService:
    """Service for retrying failed tasks in the Kurultai system."""

    # Valid task priorities
    VALID_PRIORITIES = {"high", "normal", "low", "critical"}

    # Failed task file patterns
    FAILED_PATTERN = re.compile(r'^(critical|high|normal|low)-(\d+)(-[a-f0-9-]+)?\.failed\.done\.md$')

    def __init__(self):
        """Initialize the retry service."""
        self._state_cache = None
        self._ensure_dirs()

    def _ensure_dirs(self):
        """Ensure required directories exist."""
        RETRY_LOG_DIR.mkdir(parents=True, exist_ok=True)

    def _load_watcher_state(self) -> Dict:
        """Load task-watcher state from disk."""
        if self._state_cache is not None:
            return self._state_cache

        try:
            if WATCHER_STATE.exists():
                with open(WATCHER_STATE, 'r') as f:
                    self._state_cache = json.load(f)
            else:
                self._state_cache = {}
        except Exception as e:
            logger.warning(f"Failed to load watcher state: {e}")
            self._state_cache = {}

        return self._state_cache

    def _save_watcher_state(self, state: Dict):
        """Save task-watcher state to disk."""
        try:
            WATCHER_STATE.parent.mkdir(parents=True, exist_ok=True)
            with open(WATCHER_STATE, 'w') as f:
                json.dump(state, f, indent=2)
            self._state_cache = state
            logger.debug(f"Saved watcher state with {len(state)} entries")
        except Exception as e:
            logger.error(f"Failed to save watcher state: {e}")

    def _invalidate_state_cache(self):
        """Invalidate state cache after external modifications."""
        self._state_cache = None

    def validate_agent(self, agent: str) -> bool:
        """Validate agent name."""
        return agent in VALID_AGENTS

    def get_task_path(self, agent: str, filename: str) -> Path:
        """Get the full path to a task file."""
        if not self.validate_agent(agent):
            raise ValueError(f"Invalid agent: {agent}")

        tasks_dir = agent_tasks_dir(agent)
        return tasks_dir / filename

    def extract_task_id(self, filename: str) -> Optional[str]:
        """Extract task ID from filename."""
        # Remove .failed.done.md suffix
        base = filename.replace('.failed.done.md', '').replace('.done.md', '').replace('.executing.md', '').replace('.md', '')
        return base

    def parse_task_frontmatter(self, filepath: Path) -> Dict:
        """Parse YAML frontmatter from task file."""
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read(2000)

            if not content.startswith('---'):
                return {}

            parts = content.split('---', 2)
            if len(parts) < 3:
                return {}

            frontmatter = {}
            for line in parts[1].strip().splitlines():
                if ':' in line:
                    key, _, value = line.partition(':')
                    frontmatter[key.strip()] = value.strip().strip('"\'')
            return frontmatter
        except Exception as e:
            logger.warning(f"Failed to parse frontmatter from {filepath}: {e}")
            return {}

    def extract_task_title(self, filepath: Path) -> str:
        """Extract task title from # Task: heading."""
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read(5000)

            match = re.search(r'^#\s*Task:\s*(.+)', content, re.MULTILINE)
            return match.group(1).strip() if match else Path(filepath).stem[:60]
        except Exception:
            return Path(filepath).stem[:60]

    def extract_error_excerpt(self, filepath: Path) -> Optional[str]:
        """Extract error message from task file."""
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()

            # Look for error sections
            error_patterns = [
                r'## Error\s*\n\s*(.+?)(?:\n##|\n\n|$)',
                r'## Issues\s*\n\s*(.+?)(?:\n##|\n\n|$)',
                r'ERROR:\s*(.+?)(?:\n\n|$)',
            ]

            for pattern in error_patterns:
                match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
                if match:
                    error = match.group(1).strip()
                    # Return first 200 chars
                    return error[:200] + ("..." if len(error) > 200 else "")

            return None
        except Exception:
            return None

    def extract_retry_count(self, frontmatter: Dict) -> int:
        """Extract retry count from frontmatter retry history."""
        history = frontmatter.get('retry_history')
        if isinstance(history, list):
            return len(history)
        return 0

    def is_failed_task(self, filename: str) -> bool:
        """Check if filename indicates a failed task."""
        return '.failed.done.md' in filename.lower()

    def get_pending_filename(self, failed_filename: str) -> str:
        """Convert failed filename to pending filename."""
        # Remove .failed.done suffix
        return failed_filename.replace('.failed.done.md', '.md')

    def list_failed_tasks(self, agent: Optional[str] = None) -> List[TaskInfo]:
        """List all failed tasks, optionally filtered by agent."""
        failed_tasks = []

        agents_to_check = [agent] if agent else list(VALID_AGENTS)

        for agent_name in agents_to_check:
            if not self.validate_agent(agent_name):
                continue

            tasks_dir = agent_tasks_dir(agent_name)
            if not tasks_dir.exists():
                continue

            for task_file in tasks_dir.glob("*.failed.done.md"):
                try:
                    frontmatter = self.parse_task_frontmatter(task_file)
                    task_id = self.extract_task_id(task_file.name)

                    # Get file modification time as failed_at
                    failed_at = datetime.fromtimestamp(task_file.stat().st_mtime).isoformat()

                    failed_tasks.append(TaskInfo(
                        agent=agent_name,
                        task_id=task_id,
                        filename=task_file.name,
                        title=self.extract_task_title(task_file),
                        priority=frontmatter.get('priority', 'normal'),
                        failed_at=failed_at,
                        error=self.extract_error_excerpt(task_file),
                        retry_count=self.extract_retry_count(frontmatter)
                    ))
                except Exception as e:
                    logger.warning(f"Failed to parse task {task_file}: {e}")

        return failed_tasks

    def add_retry_history(self, filepath: Path, reason: str = "manual_retry") -> bool:
        """Add retry entry to task frontmatter."""
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()

            if not content.startswith('---'):
                return False

            parts = content.split('---', 2)
            if len(parts) < 3:
                return False

            frontmatter_text = parts[1]
            body = parts[2]

            # Parse existing frontmatter
            frontmatter = self.parse_task_frontmatter(filepath)

            # Get retry history or create new
            history = frontmatter.get('retry_history', [])
            if not isinstance(history, list):
                history = []

            # Add new retry entry
            history.append({
                'timestamp': datetime.now().isoformat(),
                'reason': reason,
                'attempt': len(history) + 1
            })

            # Rebuild frontmatter with retry history
            new_frontmatter_lines = []
            for line in frontmatter_text.strip().splitlines():
                if not line.lower().startswith('retry_history:'):
                    new_frontmatter_lines.append(line)

            new_frontmatter_lines.append(f"retry_history:")
            for entry in history:
                new_frontmatter_lines.append(f"  - timestamp: \"{entry['timestamp']}\"")
                new_frontmatter_lines.append(f"    reason: {entry['reason']}")
                new_frontmatter_lines.append(f"    attempt: {entry['attempt']}")

            # Reconstruct file content
            new_content = f"---\n{chr(10).join(new_frontmatter_lines)}\n---\n{body}"

            # Write back
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)

            return True

        except Exception as e:
            logger.error(f"Failed to add retry history to {filepath}: {e}")
            return False

    def clear_error_markers(self, filepath: Path) -> bool:
        """Remove error section from task file for clean retry."""
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()

            # Remove common error sections
            error_section_patterns = [
                r'\n## Error\b.*?(?=\n##|\Z)',
                r'\n## Issues\b.*?(?=\n##|\Z)',
                r'\n## Failure\b.*?(?=\n##|\Z)',
            ]

            for pattern in error_section_patterns:
                content = re.sub(pattern, '', content, flags=re.MULTILINE | re.DOTALL)

            # Write back
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)

            return True

        except Exception as e:
            logger.error(f"Failed to clear errors from {filepath}: {e}")
            return False

    def retry_task(
        self,
        agent: str,
        task_file: str,
        clear_errors: bool = False,
        reason: str = "manual_retry"
    ) -> RetryResult:
        """Retry a single failed task.

        Args:
            agent: Agent name (e.g., "temujin")
            task_file: Task filename (e.g., "high-1773165922.failed.done.md")
            clear_errors: Whether to remove error sections from task file
            reason: Reason for retry (logged in history)

        Returns:
            RetryResult with operation outcome
        """
        # Validate agent
        if not self.validate_agent(agent):
            return RetryResult(
                success=False,
                agent=agent,
                old_file=task_file,
                error=f"Invalid agent: {agent}"
            )

        # Get file paths
        old_path = self.get_task_path(agent, task_file)
        new_filename = self.get_pending_filename(task_file)
        new_path = self.get_task_path(agent, new_filename)

        # Validate source file exists and is actually failed
        if not old_path.exists():
            return RetryResult(
                success=False,
                agent=agent,
                old_file=task_file,
                error="Task file not found"
            )

        if not self.is_failed_task(task_file):
            return RetryResult(
                success=False,
                agent=agent,
                old_file=task_file,
                error="Task is not in failed state"
            )

        # Get current retry count
        frontmatter = self.parse_task_frontmatter(old_path)
        retry_count = self.extract_retry_count(frontmatter)

        try:
            # Add retry history before moving
            if not self.add_retry_history(old_path, reason):
                logger.warning(f"Failed to add retry history for {task_file}")

            # Optionally clear error markers
            if clear_errors:
                self.clear_error_markers(old_path)

            # Perform atomic rename
            old_path.rename(new_path)

            # Update task-watcher state to clear any stale tracking
            state = self._load_watcher_state()
            state_key = f"{agent}/{task_file}"
            if state_key in state:
                del state[state_key]
                logger.debug(f"Cleared watcher state for {state_key}")
            self._save_watcher_state(state)

            # Log retry operation
            self._log_retry_operation(agent, task_file, new_filename, retry_count + 1, reason)

            logger.info(f"Retried task: {agent}/{task_file} → {new_filename}")

            return RetryResult(
                success=True,
                agent=agent,
                old_file=task_file,
                new_file=new_filename,
                retry_count=retry_count + 1,
                retry_at=datetime.now().isoformat()
            )

        except Exception as e:
            logger.error(f"Failed to retry task {agent}/{task_file}: {e}")
            return RetryResult(
                success=False,
                agent=agent,
                old_file=task_file,
                error=str(e)
            )

    def retry_agent_tasks(
        self,
        agent: str,
        clear_errors: bool = False,
        reason: str = "bulk_agent_retry"
    ) -> Dict:
        """Retry all failed tasks for a specific agent.

        Returns dict with:
            - success: bool
            - agent: str
            - queued: int
            - tasks: list of RetryResult
        """
        if not self.validate_agent(agent):
            return {
                "success": False,
                "error": f"Invalid agent: {agent}"
            }

        failed_tasks = self.list_failed_tasks(agent)
        results = []
        queued = 0

        for task in failed_tasks:
            result = self.retry_task(agent, task.filename, clear_errors, reason)
            results.append(result)
            if result.success:
                queued += 1

        return {
            "success": True,
            "agent": agent,
            "queued": queued,
            "total": len(failed_tasks),
            "tasks": [r.to_dict() for r in results]
        }

    def retry_all_tasks(
        self,
        clear_errors: bool = False,
        reason: str = "bulk_all_retry"
    ) -> Dict:
        """Retry all failed tasks across all agents.

        Returns dict with:
            - success: bool
            - queued: int
            - by_agent: dict of counts per agent
        """
        all_failed = self.list_failed_tasks()
        by_agent = {agent: 0 for agent in VALID_AGENTS}
        total_queued = 0

        for task in all_failed:
            result = self.retry_task(task.agent, task.filename, clear_errors, reason)
            if result.success:
                by_agent[task.agent] += 1
                total_queued += 1

        return {
            "success": True,
            "queued": total_queued,
            "by_agent": by_agent
        }

    def _log_retry_operation(
        self,
        agent: str,
        old_file: str,
        new_file: str,
        retry_count: int,
        reason: str
    ):
        """Log retry operation to dedicated ledger."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "agent": agent,
            "old_file": old_file,
            "new_file": new_file,
            "retry_count": retry_count,
            "reason": reason
        }

        try:
            ledger_file = RETRY_LOG_DIR / "retry-ledger.jsonl"
            with open(ledger_file, 'a') as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception as e:
            logger.error(f"Failed to write to retry ledger: {e}")


# CLI interface for direct execution
def main():
    """CLI interface for task retry operations."""
    import argparse

    parser = argparse.ArgumentParser(description="Task Retry Service")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # List command
    list_parser = subparsers.add_parser("list", help="List failed tasks")
    list_parser.add_argument("--agent", help="Filter by agent")

    # Retry command
    retry_parser = subparsers.add_parser("retry", help="Retry a task")
    retry_parser.add_argument("agent", help="Agent name")
    retry_parser.add_argument("task_file", help="Task filename")
    retry_parser.add_argument("--clear-errors", action="store_true", help="Clear error sections")

    # Retry-agent command
    retry_agent_parser = subparsers.add_parser("retry-agent", help="Retry all failed tasks for an agent")
    retry_agent_parser.add_argument("agent", help="Agent name")

    # Retry-all command
    subparsers.add_parser("retry-all", help="Retry all failed tasks")

    args = parser.parse_args()

    service = TaskRetryService()

    if args.command == "list":
        tasks = service.list_failed_tasks(args.agent)
        print(f"\nFound {len(tasks)} failed tasks:\n")
        for task in tasks:
            print(f"  [{task.agent}] {task.filename}")
            print(f"    Title: {task.title}")
            print(f"    Retries: {task.retry_count}")
            if task.error:
                print(f"    Error: {task.error[:100]}...")
            print()

    elif args.command == "retry":
        result = service.retry_task(args.agent, args.task_file, args.clear_errors)
        if result.success:
            print(f"✓ Retried: {result.old_file} → {result.new_file}")
            print(f"  Retry #{result.retry_count} at {result.retry_at}")
        else:
            print(f"✗ Failed: {result.error}")

    elif args.command == "retry-agent":
        result = service.retry_agent_tasks(args.agent)
        if result["success"]:
            print(f"✓ Queued {result['queued']}/{result['total']} tasks for {args.agent}")
        else:
            print(f"✗ {result['error']}")

    elif args.command == "retry-all":
        result = service.retry_all_tasks()
        print(f"✓ Queued {result['queued']} failed tasks across all agents")
        for agent, count in result["by_agent"].items():
            if count > 0:
                print(f"  {agent}: {count}")


if __name__ == "__main__":
    main()
