#!/usr/bin/env python3
"""
Shared utility functions for Completion Gate scripts.

This module extracts common functionality used across multiple gate scripts
to prevent code duplication and ensure consistent behavior.

Security: All functions validate inputs and handle errors safely.
"""

import re
from pathlib import Path
from typing import Optional, Dict, Any


# Valid agents - single source of truth
VALID_AGENTS = {"mongke", "chagatai", "temujin", "jochi", "ogedei", "kublai"}

# Regex pattern for validating task IDs (prevents path traversal)
TASK_ID_PATTERN = re.compile(r'^[a-z]+-[0-9a-f]{8,16}$')

# Maximum safe content read size
MAX_CONTENT_READ = 2000

# Constants for depth limit
MAX_FOLLOWUP_DEPTH = 3


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
