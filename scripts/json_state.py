#!/usr/bin/env python3
"""
json_state.py — Locked JSON file access for shared state files.

Prevents corruption from concurrent access by multiple scripts
(task-watcher, kublai-actions, spawn-consumer, etc.).

Usage:
    from json_state import locked_json_read, locked_json_update

    # Read-only (shared lock):
    data = locked_json_read(filepath)

    # Read-modify-write (exclusive lock, fsync on exit):
    with locked_json_update(filepath) as data:
        data['key'] = 'value'
    # File is written and fsynced when context exits.
"""

import fcntl
import json
import os
from contextlib import contextmanager


def locked_json_read(filepath, default=None):
    """Read a JSON file with a shared (read) lock."""
    if not os.path.exists(filepath):
        return default if default is not None else {}
    try:
        with open(filepath, 'r') as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            try:
                return json.load(f)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except (json.JSONDecodeError, Exception):
        return default if default is not None else {}


@contextmanager
def locked_json_update(filepath, default=None):
    """Context manager: read JSON, yield mutable data, write back with exclusive lock.

    The file is locked exclusively for the entire read-modify-write cycle.
    Data is fsynced to disk before the lock is released.
    """
    if default is None:
        default = {}

    os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)

    # Open in r+ mode if file exists, else create it first
    if not os.path.exists(filepath):
        with open(filepath, 'w') as f:
            json.dump(default, f)

    with open(filepath, 'r+') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.seek(0)
            content = f.read()
            if content.strip():
                try:
                    data = json.loads(content)
                except json.JSONDecodeError:
                    data = default.copy() if isinstance(default, dict) else default
            else:
                data = default.copy() if isinstance(default, dict) else default

            yield data

            # Write back
            f.seek(0)
            f.truncate()
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
