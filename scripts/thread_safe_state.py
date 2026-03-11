#!/usr/bin/env python3
"""
Thread-Safe State Manager for Kurultai agents.

Provides RLock-based state management for concurrent access.
Replaces threading.Lock with threading.RLock for reentrant safety.

Usage:
    from thread_safe_state import ThreadSafeState

    state = ThreadSafeState()
    with state.access() as data:
        data['counter'] = data.get('counter', 0) + 1
"""

import threading
from contextlib import contextmanager
from typing import Any, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class ThreadSafeState:
    """
    Thread-safe state container using RLock for reentrant locking.

    RLock allows the same thread to acquire the lock multiple times
    without deadlocking, which is important for nested function calls.
    """

    def __init__(self, initial_state: Optional[Dict[str, Any]] = None):
        self._lock = threading.RLock()
        self._state: Dict[str, Any] = initial_state or {}
        self._version = 0

    @contextmanager
    def access(self):
        """
        Context manager for thread-safe state access.

        Usage:
            with state.access() as data:
                data['key'] = value
        """
        with self._lock:
            self._version += 1
            yield self._state

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from state (thread-safe)."""
        with self._lock:
            return self._state.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a value in state (thread-safe)."""
        with self._lock:
            self._state[key] = value
            self._version += 1

    def update(self, updates: Dict[str, Any]) -> None:
        """Update multiple values at once (thread-safe)."""
        with self._lock:
            self._state.update(updates)
            self._version += 1

    def delete(self, key: str) -> bool:
        """Delete a key from state (thread-safe). Returns True if key existed."""
        with self._lock:
            if key in self._state:
                del self._state[key]
                self._version += 1
                return True
            return False

    def clear(self) -> None:
        """Clear all state (thread-safe)."""
        with self._lock:
            self._state.clear()
            self._version += 1

    def snapshot(self) -> Dict[str, Any]:
        """Get a copy of the current state."""
        with self._lock:
            return dict(self._state)

    @property
    def version(self) -> int:
        """Current version (incremented on each modification)."""
        return self._version

    def __len__(self) -> int:
        with self._lock:
            return len(self._state)

    def __contains__(self, key: str) -> bool:
        with self._lock:
            return key in self._state

    def __repr__(self) -> str:
        return f"ThreadSafeState(version={self._version}, keys={len(self)})"


class GlobalStateManager:
    """
    Singleton manager for global application state.

    Provides a single point of access for shared state across modules.
    """
    _instance: Optional['GlobalStateManager'] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._state = ThreadSafeState()
        return cls._instance

    @classmethod
    def get_instance(cls) -> 'GlobalStateManager':
        return cls()

    def get(self, key: str, default: Any = None) -> Any:
        return self._state.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._state.set(key, value)

    def update(self, updates: Dict[str, Any]) -> None:
        self._state.update(updates)

    @contextmanager
    def access(self):
        with self._state.access() as data:
            yield data

    def snapshot(self) -> Dict[str, Any]:
        return self._state.snapshot()


# Module-level convenience
_global_state: Optional[GlobalStateManager] = None


def get_global_state() -> GlobalStateManager:
    """Get the global state manager singleton."""
    global _global_state
    if _global_state is None:
        _global_state = GlobalStateManager()
    return _global_state


if __name__ == "__main__":
    # Test the thread-safe state
    import concurrent.futures

    state = ThreadSafeState()

    def increment_counter(n):
        for _ in range(1000):
            with state.access() as data:
                data['counter'] = data.get('counter', 0) + 1

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        executor.map(increment_counter, range(10))

    print(f"Final counter: {state.get('counter')}")
    print(f"Expected: 10000")
    print(f"Test passed: {state.get('counter') == 10000}")
