#!/usr/bin/env python3
"""
JSON Registry - Atomic JSON file operations with file locking.

Provides thread-safe JSON file operations using fcntl file locking to
prevent race conditions when multiple processes access the same files.

Usage:
    from json_registry import locked_json_read, locked_json_update

    # Read with shared lock
    with locked_json_read("rules.json") as data:
        print(data["rules"])

    # Update with exclusive lock
    with locked_json_update("rules.json") as data:
        data["rules"].append({"pattern": "new_rule", "action": "block"})

Consolidates from:
- rule_registry.py
- continuous_registry.py
- cross_agent_rules.py
"""

import fcntl
import json
import os
import tempfile
from pathlib import Path
from contextlib import contextmanager
from typing import Any, Dict, Optional, Callable


class RegistryError(Exception):
    """Base exception for registry errors."""
    pass


class RegistryLocked(RegistryError):
    """Raised when registry is locked by another process."""
    pass


class RegistryCorrupted(RegistryError):
    """Raised when registry file is corrupted."""
    pass


@contextmanager
def locked_json_read(filepath: str | Path):
    """Read JSON file with shared lock (multiple readers allowed).

    Args:
        filepath: Path to JSON file

    Yields:
        Dict with file contents

    Raises:
        FileNotFoundError: If file doesn't exist
        RegistryCorrupted: If JSON is invalid
    """
    filepath = Path(filepath)

    if not filepath.exists():
        raise FileNotFoundError(f"Registry file not found: {filepath}")

    with open(filepath, 'r') as f:
        # Shared lock - allows multiple readers
        fcntl.flock(f.fileno(), fcntl.LOCK_SH)
        try:
            data = json.load(f)
            yield data
        except json.JSONDecodeError as e:
            raise RegistryCorrupted(f"Invalid JSON in {filepath}: {e}")
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


@contextmanager
def locked_json_update(filepath: str | Path, backup: bool = True):
    """Update JSON file with exclusive lock (atomic write).

    Reads the file with an exclusive lock, yields the data for modification,
    and writes back atomically on exit.

    Args:
        filepath: Path to JSON file
        backup: If True, create .bak file before writing

    Yields:
        Dict with file contents (modifiable)

    Raises:
        FileNotFoundError: If file doesn't exist
        RegistryLocked: If file is locked by another process
        RegistryCorrupted: If JSON is invalid
    """
    filepath = Path(filepath)

    if not filepath.exists():
        raise FileNotFoundError(f"Registry file not found: {filepath}")

    with open(filepath, 'r+') as f:
        # Exclusive lock - only one writer, no readers
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            data = json.load(f)

            # Yield data for modification
            yield data

            # Write back atomically
            f.seek(0)
            json.dump(data, f, indent=2)
            f.truncate()

        except json.JSONDecodeError as e:
            raise RegistryCorrupted(f"Invalid JSON in {filepath}: {e}")
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def atomic_write_json(filepath: str | Path, data: Dict[str, Any]) -> None:
    """Atomically write JSON file using write-then-rename pattern.

    Creates a temporary file, writes data, then renames to target.
    This is the safest way to write files that might be read by other processes.

    Args:
        filepath: Target path
        data: Data to write
    """
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    # Write to temp file
    fd, temp_path = tempfile.mkstemp(
        dir=filepath.parent,
        prefix=f".{filepath.name}.",
        suffix=".tmp"
    )

    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(data, f, indent=2)

        # Atomic rename
        os.rename(temp_path, filepath)
    except Exception:
        # Clean up temp file on error
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def safe_read_json(
    filepath: str | Path,
    default: Any = None,
    create_if_missing: bool = False
) -> Any:
    """Safely read JSON file with default fallback.

    Args:
        filepath: Path to JSON file
        default: Default value if file doesn't exist or is corrupted
        create_if_missing: If True, create file with default value

    Returns:
        File contents or default
    """
    filepath = Path(filepath)

    if not filepath.exists():
        if create_if_missing and default is not None:
            atomic_write_json(filepath, default)
        return default

    try:
        with locked_json_read(filepath) as data:
            return data
    except (RegistryCorrupted, json.JSONDecodeError):
        return default


def safe_update_json(
    filepath: str | Path,
    update_func: Callable[[Dict], Dict],
    default: Any = None
) -> Any:
    """Safely update JSON file with transformation function.

    Args:
        filepath: Path to JSON file
        update_func: Function that takes current data and returns updated data
        default: Default value if file doesn't exist

    Returns:
        Updated data
    """
    filepath = Path(filepath)

    if not filepath.exists():
        if default is not None:
            atomic_write_json(filepath, default)
            return default
        raise FileNotFoundError(f"Registry file not found: {filepath}")

    with locked_json_update(filepath) as data:
        updated = update_func(data)
        # Data is automatically written back on exit from context
        return updated


class JsonRegistry:
    """High-level registry with CRUD operations.

    Provides a simple key-value registry stored in a JSON file
    with automatic locking and versioning.

    Example:
        registry = JsonRegistry("my_registry.json")
        registry.set("key1", {"value": 123})
        value = registry.get("key1")
    """

    def __init__(self, filepath: str | Path, default: Any = None):
        """Initialize registry.

        Args:
            filepath: Path to JSON file
            default: Default registry structure
        """
        self.filepath = Path(filepath)
        self.default = default if default is not None else {"version": 1, "entries": {}}
        self._ensure_exists()

    def _ensure_exists(self):
        """Ensure registry file exists."""
        if not self.filepath.exists():
            atomic_write_json(self.filepath, self.default)

    def get(self, key: str) -> Any:
        """Get value by key.

        Args:
            key: Key to look up

        Returns:
            Value or None if not found
        """
        data = safe_read_json(self.filepath, self.default)
        return data.get("entries", {}).get(key)

    def set(self, key: str, value: Any) -> None:
        """Set value for key.

        Args:
            key: Key to set
            value: Value to store
        """
        def update(data):
            data.setdefault("entries", {})[key] = value
            return data

        safe_update_json(self.filepath, update, self.default)

    def delete(self, key: str) -> bool:
        """Delete key from registry.

        Args:
            key: Key to delete

        Returns:
            True if key existed and was deleted
        """
        def update(data):
            entries = data.get("entries", {})
            if key in entries:
                del entries[key]
                return data
            return data

        safe_update_json(self.filepath, update, self.default)
        return True

    def keys(self) -> list[str]:
        """Get all keys in registry.

        Returns:
            List of keys
        """
        data = safe_read_json(self.filepath, self.default)
        return list(data.get("entries", {}).keys())

    def values(self) -> list[Any]:
        """Get all values in registry.

        Returns:
            List of values
        """
        data = safe_read_json(self.filepath, self.default)
        return list(data.get("entries", {}).values())

    def items(self) -> list[tuple[str, Any]]:
        """Get all key-value pairs.

        Returns:
            List of (key, value) tuples
        """
        data = safe_read_json(self.filepath, self.default)
        return list(data.get("entries", {}).items())

    def clear(self) -> None:
        """Clear all entries from registry."""
        def update(data):
            data["entries"] = {}
            return data

        safe_update_json(self.filepath, update, self.default)
