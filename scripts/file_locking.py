"""
File Locking Utilities

Centralized file locking utilities for the Kurultai multi-agent system.
Consolidates patterns from json_state.py, agent-task-handler.py, auto_dispatch.py.

Usage:
    from file_locking import exclusive_lock, shared_lock

    with open('file.json', 'r') as f:
        with exclusive_lock(f):
            data = json.load(f)
"""

import fcntl
from contextlib import contextmanager
from typing import Generator, IO


class LockAcquisitionError(Exception):
    """Raised when a non-blocking lock cannot be acquired."""
    pass


@contextmanager
def exclusive_lock(file_obj: IO) -> Generator:
    """Acquire exclusive lock (LOCK_EX).

    Blocks until the lock is available.

    Args:
        file_obj: File object to lock

    Yields:
        None
    """
    try:
        fcntl.flock(file_obj.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(file_obj.fileno(), fcntl.LOCK_UN)


@contextmanager
def shared_lock(file_obj: IO) -> Generator:
    """Acquire shared lock (LOCK_SH).

    Blocks until the lock is available.
    Multiple readers can hold shared locks simultaneously.

    Args:
        file_obj: File object to lock

    Yields:
        None
    """
    try:
        fcntl.flock(file_obj.fileno(), fcntl.LOCK_SH)
        yield
    finally:
        fcntl.flock(file_obj.fileno(), fcntl.LOCK_UN)


@contextmanager
def non_blocking_exclusive_lock(file_obj: IO) -> Generator:
    """Acquire exclusive lock without blocking (LOCK_EX | LOCK_NB).

    Raises LockAcquisitionError if lock cannot be acquired immediately.

    Args:
        file_obj: File object to lock

    Yields:
        None

    Raises:
        LockAcquisitionError: If lock cannot be acquired
    """
    try:
        fcntl.flock(file_obj.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    except BlockingIOError:
        raise LockAcquisitionError("Could not acquire lock - resource busy")
    finally:
        fcntl.flock(file_obj.fileno(), fcntl.LOCK_UN)


@contextmanager
def non_blocking_shared_lock(file_obj: IO) -> Generator:
    """Acquire shared lock without blocking (LOCK_SH | LOCK_NB).

    Raises LockAcquisitionError if lock cannot be acquired immediately.

    Args:
        file_obj: File object to lock

    Yields:
        None

    Raises:
        LockAcquisitionError: If lock cannot be acquired
    """
    try:
        fcntl.flock(file_obj.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
        yield
    except BlockingIOError:
        raise LockAcquisitionError("Could not acquire lock - resource busy")
    finally:
        fcntl.flock(file_obj.fileno(), fcntl.LOCK_UN)
