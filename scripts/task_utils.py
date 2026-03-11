#!/usr/bin/env python3
"""
task_utils.py — Shared utilities for task handling.

This module consolidates duplicate functions that were previously defined
in multiple files (agent-task-handler.py, task-watcher.py, etc.).

Usage:
    from task_utils import extract_task_id, verify_task_completion, derive_status_from_filename
"""

import os
import re
from pathlib import Path
from typing import Optional

# Import paths from centralized module
from kurultai_paths import AGENTS_DIR


def extract_task_id(filepath: str) -> Optional[str]:
    """Extract task_id from file path or frontmatter.

    Checks:
    1. task_id in YAML frontmatter
    2. UUID pattern in filename

    Returns task_id or None if not found.
    """
    filepath = Path(filepath)

    # First check frontmatter
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read(2000)

        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 2:
                for line in parts[1].strip().splitlines():
                    if line.lower().startswith('task_id:'):
                        _, _, value = line.partition(':')
                        tid = value.strip().strip('"\'')
                        if tid:
                            return tid
    except Exception:
        pass

    # Check filename for UUID pattern
    filename = filepath.name
    uuid_match = re.search(r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})', filename, re.I)
    if uuid_match:
        return uuid_match.group(1).lower()

    return None


def verify_task_completion(filepath: str) -> dict:
    """Verify task completion by checking file content for completion markers.

    Returns dict with:
    - completed: bool
    - has_completion_section: bool
    - has_summary: bool
    - issues: list of str
    """
    result = {
        'completed': False,
        'has_completion_section': False,
        'has_summary': False,
        'issues': []
    }

    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except Exception as e:
        result['issues'].append(f"Cannot read file: {e}")
        return result

    # Check for completion section markers
    completion_markers = [
        '## Summary',
        '## Completion',
        '## Result',
        '## Changes Made',
        '## Implementation Complete',
        '# Summary',
        '# Completion',
    ]

    for marker in completion_markers:
        if marker in content:
            result['has_completion_section'] = True
            break

    # Check for summary content
    if '## Summary' in content or '# Summary' in content:
        summary_section = content.split('## Summary')[-1] if '## Summary' in content else content.split('# Summary')[-1]
        summary_lines = [l for l in summary_section.split('\n') if l.strip() and not l.startswith('#')]
        if len(summary_lines) >= 2:
            result['has_summary'] = True

    # Determine overall completion
    if result['has_completion_section'] or result['has_summary']:
        result['completed'] = True
    elif len(content) > 500:
        # Heuristic: if file has substantial content, consider it potentially complete
        result['completed'] = True
        result['issues'].append("No explicit completion section found")

    return result


def derive_status_from_filename(filename: str) -> str:
    """Derive task status from filesystem filename conventions.

    Conventions used by task-watcher.py and agent-task-handler.py:
    - .completed.done.md / .md.completed.done -> COMPLETED
    - .failed.done.md / .failed.done -> FAILED
    - .executing.md -> EXECUTING
    - .stale.done.md / .obsolete.done.md / .resolved.done.md -> COMPLETED (terminal)
    - .retry-N.* -> check further suffix
    - plain .md (no special suffix) -> PENDING
    """
    name = filename.lower()
    if '.completed.done' in name:
        return 'COMPLETED'
    if '.failed.done' in name:
        return 'FAILED'
    if '.stale' in name and '.done' in name:
        return 'COMPLETED'
    if '.obsolete' in name and '.done' in name:
        return 'COMPLETED'
    if '.resolved' in name and '.done' in name:
        return 'COMPLETED'
    if '.executing' in name:
        return 'EXECUTING'
    if name.endswith('.done'):
        return 'COMPLETED'
    return 'PENDING'


def extract_title(filepath: str) -> str:
    """Extract title from # Task: heading or filename."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read(2000)
        match = re.search(r'^#\s*Task:\s*(.+)', content, re.MULTILINE)
        return match.group(1).strip() if match else Path(filepath).stem[:60]
    except Exception:
        return Path(filepath).stem[:60]


def extract_frontmatter(filepath: str) -> dict:
    """Extract frontmatter fields from a task file."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read(1000)
    except Exception:
        return {}

    if not content.startswith('---'):
        return {}

    parts = content.split('---', 2)
    if len(parts) < 3:
        return {}

    fm = {}
    for line in parts[1].strip().splitlines():
        if ':' in line:
            key, _, value = line.partition(':')
            fm[key.strip()] = value.strip()
    return fm


# Valid task statuses (canonical source)
VALID_STATUSES = frozenset({'PENDING', 'EXECUTING', 'COMPLETED', 'FAILED'})

# Status normalization map
STATUS_NORMALIZE = {
    'verified': 'COMPLETED',
    'done': 'COMPLETED',
    'no_output': 'COMPLETED',
    'pending': 'PENDING',
    'ready': 'PENDING',
    'executing': 'EXECUTING',
    'running': 'EXECUTING',
    'failed': 'FAILED',
    'paused': 'PENDING',
}


def normalize_status(status: str) -> str:
    """Normalize status to canonical form."""
    if not status:
        return 'PENDING'
    status_lower = status.lower().strip()
    return STATUS_NORMALIZE.get(status_lower, status.upper())
