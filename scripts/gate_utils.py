#!/usr/bin/env python3
"""
Shared utility functions for Completion Gate scripts.

This module extracts common functionality used across multiple gate scripts
to prevent code duplication and ensure consistent behavior.

Security: All functions validate inputs and handle errors safely.
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List

# Import from kurultai_paths for shared paths and constants
from kurultai_paths import AGENTS_DIR, MAIN_DIR, LOGS_DIR, VALID_AGENTS

# Regex pattern for validating task IDs (prevents path traversal)
TASK_ID_PATTERN = re.compile(r'^[a-z]+-[0-9a-f]{8,16}$')

# Maximum safe content read size
MAX_CONTENT_READ = 2000

# Constants for depth limit
MAX_FOLLOWUP_DEPTH = 3

# Common paths
GATE_AUDITS_DIR = LOGS_DIR / "gate-audits"
GATE_EVENTS_LOG = LOGS_DIR.parent / "logs" / "gate-events.log"
LOCK_DIR = MAIN_DIR / "locks"
GATE_LEDGER = Path.home() / ".openclaw" / "tasks" / "task-ledger.jsonl"

# Platform-specific O_EXCL constant
try:
    O_OEXCL = os.O_EXCL
except AttributeError:
    O_OEXCL = 0  # Fallback for platforms without O_EXCL


def validate_task_id(task_id: str) -> bool:
    """
    Validate task ID format to prevent path traversal attacks.

    Args:
        task_id: Task ID string to validate

    Returns:
        True if task_id matches expected format, False otherwise
    """
    if not task_id or not isinstance(task_id, str):
        return False
    return bool(TASK_ID_PATTERN.match(task_id.strip()))


def sanitize_task_id_for_glob(task_id: str) -> str:
    """
    Safely escape task ID for use in glob patterns.

    If task_id fails validation, returns empty string to prevent unsafe glob.

    Args:
        task_id: Task ID to sanitize

    Returns:
        Sanitized task ID safe for glob patterns, or empty string if invalid
    """
    if not validate_task_id(task_id):
        return ""
    # Additional sanitization: remove any glob special characters
    return task_id.replace("*", "").replace("?", "").replace("[", "").replace("]", "")


def extract_frontmatter(file_path: Path) -> Dict[str, Any]:
    """
    Extract YAML frontmatter from a markdown file.

    Security: Uses simple parsing with size limits to prevent DoS.
    For complex YAML, consider using yaml.safe_load() instead.

    Args:
        file_path: Path to markdown file

    Returns:
        Dictionary of frontmatter key-value pairs
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read(MAX_CONTENT_READ)

        # Find frontmatter boundaries
        if not content.startswith('---'):
            return {}

        end_idx = content.find('---', 3)
        if end_idx == -1:
            return {}

        frontmatter_text = content[3:end_idx].strip()

        # Parse simple YAML-like key-value pairs
        result = {}
        for line in frontmatter_text.split('\n'):
            if ':' in line and not line.strip().startswith('#'):
                key, value = line.split(':', 1)
                key = key.strip()
                value = value.strip()
                result[key] = value

        return result
    except Exception as e:
        # Log but don't raise - allow caller to handle missing frontmatter
        print(f"[WARN] Failed to parse frontmatter from {file_path}: {e}")
        return {}


def extract_task_id(file_path: Path) -> Optional[str]:
    """
    Extract task ID from a task file.

    Tries frontmatter first, then filename parsing.

    Args:
        file_path: Path to task file

    Returns:
        Task ID string or None if not found
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read(MAX_CONTENT_READ)

        # Extract from frontmatter
        match = re.search(r'task_id:\s*(\S+)', content)
        if match:
            return match.group(1)

        # Extract from filename as fallback
        # Format: priority-taskid.pending-gate.md
        stem = file_path.stem
        stem = stem.replace('.pending-gate', '')
        stem = stem.replace('.gate-passed', '')
        stem = stem.replace('.gate-blocked', '')
        stem = stem.replace('.gate-bypassed', '')
        stem = stem.replace('.executing', '')
        stem = stem.replace('.done', '')

        parts = stem.split('-', 1)
        if len(parts) > 1:
            return parts[1]

        return None
    except Exception as e:
        print(f"[WARN] Failed to extract task ID from {file_path}: {e}")
        return None


def find_task_file(task_id: str, agents_dir: Path) -> Optional[Path]:
    """
    Find a task file by task ID across all agent directories.

    Security: Validates task_id format before using in glob patterns.

    Args:
        task_id: Task ID to search for
        agents_dir: Path to agents directory

    Returns:
        Path to task file or None if not found
    """
    # Validate task_id to prevent path traversal
    if not validate_task_id(task_id):
        print(f"[WARN] Invalid task_id format: {task_id}")
        return None

    # Safe task_id for glob
    safe_id = sanitize_task_id_for_glob(task_id)
    if not safe_id:
        return None

    for agent_dir in agents_dir.iterdir():
        if not agent_dir.is_dir() or agent_dir.name.startswith('.'):
            continue

        if agent_dir.name not in VALID_AGENTS:
            continue

        tasks_dir = agent_dir / "tasks"
        if not tasks_dir.exists():
            continue

        # Use validated task_id in glob pattern
        for task_file in tasks_dir.glob(f"*{safe_id}*.md"):
            return task_file

    return None


def is_within_depth_limit(frontmatter: Dict[str, Any], max_depth: int = MAX_FOLLOWUP_DEPTH) -> bool:
    """
    Check if a task is within the allowed follow-up depth limit.

    This prevents infinite recursion of follow-up tasks creating more follow-ups.

    Args:
        frontmatter: Task frontmatter dictionary
        max_depth: Maximum allowed depth (default: MAX_FOLLOWUP_DEPTH)

    Returns:
        True if depth is within limit, False otherwise
    """
    try:
        current_depth = int(frontmatter.get("depth", 0))
        return current_depth < max_depth
    except (ValueError, TypeError):
        return True  # Allow if depth is invalid


def normalize_priority(priority: str) -> str:
    """
    Normalize priority string to lowercase and validate.

    Args:
        priority: Priority string from frontmatter

    Returns:
        Normalized priority or 'normal' if invalid
    """
    if not priority or not isinstance(priority, str):
        return "normal"

    normalized = priority.strip().lower()
    valid_priorities = {"critical", "high", "normal", "low"}

    if normalized not in valid_priorities:
        print(f"[WARN] Invalid priority '{priority}', defaulting to 'normal'")
        return "normal"

    return normalized


def is_valid_agent(agent_name: str) -> bool:
    """
    Check if agent name is in the valid agents list.

    Args:
        agent_name: Agent name to validate

    Returns:
        True if agent is valid, False otherwise
    """
    return agent_name in VALID_AGENTS


# =============================================================================
# File Content Utilities
# =============================================================================

def extract_body_after_frontmatter(file_path: Path) -> str:
    """
    Extract markdown body after frontmatter.

    Args:
        file_path: Path to markdown file

    Returns:
        Body content after frontmatter, or empty string on error
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        if not content.startswith('---'):
            return content

        end_idx = content.find('---', 3)
        if end_idx == -1:
            return content

        return content[end_idx + 3:].strip()
    except Exception as e:
        print(f"[WARN] Failed to extract body: {e}")
        return ""


# =============================================================================
# Atomic File Operations
# =============================================================================

def atomic_rename_with_lock(
    source_path: Path,
    target_path: Path,
    lock_dir: Optional[Path] = None
) -> Tuple[bool, str]:
    """
    Atomic rename with per-gate lock to prevent race conditions.

    Args:
        source_path: Source file path
        target_path: Target file path
        lock_dir: Lock directory (uses LOCK_DIR if None)

    Returns:
        Tuple of (success, message)
    """
    if lock_dir is None:
        lock_dir = LOCK_DIR

    if not source_path.exists():
        return False, "source_not_found"

    # Create per-gate lock
    stem = source_path.name.replace('.pending-gate.md', '').replace('.md', '')
    lock_path = lock_dir / f"{stem}.gate-lock"

    lock_fd = None
    try:
        lock_fd = os.open(str(lock_path), os.O_CREAT | O_OEXCL | os.O_WRONLY)
    except FileExistsError:
        return False, "concurrent_operation"
    except Exception as e:
        return False, f"lock_error: {e}"

    try:
        # Recheck source after lock
        if not source_path.exists():
            return False, "source_gone_after_lock"

        # Check target doesn't exist
        if target_path.exists():
            return False, "target_already_exists"

        # Atomic rename
        source_path.rename(target_path)
        return True, "ok"
    finally:
        if lock_fd is not None:
            try:
                os.close(lock_fd)
            except Exception:
                pass
        lock_path.unlink(missing_ok=True)


# =============================================================================
# File Locking (for process-level locks)
# =============================================================================

def acquire_process_lock(
    lock_file: Path,
    timeout_seconds: int = 300
) -> Tuple[bool, Optional[int], str]:
    """
    Acquire exclusive process lock to prevent concurrent runs.

    Args:
        lock_file: Path to lock file (will store PID)
        timeout_seconds: Maximum age of lock before considering stale

    Returns:
        Tuple of (success, lock_fd, message)
    """
    lock_file.parent.mkdir(parents=True, exist_ok=True)

    # Check for stale lock
    if lock_file.exists():
        try:
            lock_age = datetime.now().timestamp() - lock_file.stat().st_mtime
            pid_content = lock_file.read_text().strip()

            # Parse PID from lock file
            try:
                lock_pid = int(pid_content.split('\n')[0])
            except (ValueError, IndexError):
                lock_pid = None

            # Check if lock is stale (too old OR process dead)
            is_stale = lock_age > timeout_seconds
            is_dead = False

            if lock_pid:
                # Use kill(0) to check if process exists
                try:
                    os.kill(lock_pid, 0)  # Signal 0 = check if process exists
                except OSError:
                    is_dead = True  # PID doesn't exist
            else:
                is_dead = True

            if is_stale or is_dead:
                print(f"[LOCK] Cleaning up stale lock (age={lock_age:.0f}s, dead={is_dead})")
                lock_file.unlink(missing_ok=True)
            else:
                return False, None, f"Lock held by PID {lock_pid}"
        except Exception as e:
            print(f"[LOCK] Error checking lock: {e}, proceeding anyway")
            lock_file.unlink(missing_ok=True)

    # Try to create lock file atomically
    try:
        lock_fd = os.open(str(lock_file), os.O_CREAT | O_OEXCL | os.O_WRONLY)
        # Write our PID
        os.write(lock_fd, f"{os.getpid()}\n{datetime.now().isoformat()}\n".encode())
        return True, lock_fd, "Lock acquired"
    except FileExistsError:
        return False, None, "Lock acquired by another process (race)"
    except Exception as e:
        return False, None, f"Lock error: {e}"


def release_process_lock(lock_fd: Optional[int], lock_file: Path):
    """
    Release process lock.

    Args:
        lock_fd: File descriptor from acquire_process_lock
        lock_file: Path to lock file
    """
    if lock_fd is not None:
        try:
            os.close(lock_fd)
        except Exception:
            pass
    lock_file.unlink(missing_ok=True)


# =============================================================================
# Event Logging
# =============================================================================

def log_gate_event(event: Dict[str, Any], log_path: Optional[Path] = None):
    """
    Log gate event to ledger file.

    Args:
        event: Event dictionary to log
        log_path: Path to log file (uses GATE_EVENTS_LOG if None)
    """
    if log_path is None:
        log_path = GATE_EVENTS_LOG

    log_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(log_path, 'a') as f:
            f.write(json.dumps(event) + '\n')
    except Exception:
        pass  # Don't block on logging failure


def log_ledger_entry(entry: Dict[str, Any], ledger_path: Optional[Path] = None):
    """
    Log entry to task ledger.

    Args:
        entry: Entry dictionary to log
        ledger_path: Path to ledger file (uses GATE_LEDGER if None)
    """
    if ledger_path is None:
        ledger_path = GATE_LEDGER

    ledger_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(ledger_path, 'a') as f:
            f.write(json.dumps(entry) + '\n')
    except Exception:
        pass  # Don't block on logging failure


# =============================================================================
# Status Suffix Utilities
# =============================================================================

def get_status_from_filename(filename: str) -> List[str]:
    """
    Extract status chain from filename suffixes.

    Examples:
        "task-123.verified.done.md" -> ["verified", "done"]
        "task-123.pending-gate.md" -> ["pending", "gate"]
        "task-123.md" -> []

    Args:
        filename: Task filename

    Returns:
        List of status markers in order
    """
    stem = Path(filename).stem
    parts = stem.split(".")
    return [p for p in parts[1:] if p not in ("pending", "md", "executing")]


def is_task_file_complete(filename: str) -> bool:
    """
    Check if task filename indicates completion.

    Args:
        filename: Task filename

    Returns:
        True if filename indicates task is done
    """
    return '.done.' in filename or filename.endswith('.done.md')


def is_task_file_pending_gate(filename: str) -> bool:
    """
    Check if task filename indicates pending gate state.

    Args:
        filename: Task filename

    Returns:
        True if filename indicates pending gate
    """
    return '.pending-gate.' in filename or filename.endswith('.pending-gate.md')
