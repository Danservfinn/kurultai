"""
Retry Utilities

Centralized retry utilities for the Kurultai multi-agent system.
Provides decorators and helper functions for retry logic with exponential backoff.

Usage:
    from retry_utils import retry

    @retry(max_attempts=3, delay=1.0, backoff=2.0)
    def flaky_operation():
        # May fail occasionally
        pass
"""

# Enable PEP 604 union syntax (X | Y) for Python < 3.10 compatibility
from __future__ import annotations

import time
import functools
from typing import Callable, TypeVar, Any
from collections.abc import Sequence

T = TypeVar('T')


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Sequence[type[Exception]] = (Exception,)
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Retry decorator with exponential backoff.

    Args:
        max_attempts: Maximum number of attempts (default: 3)
        delay: Initial delay in seconds (default: 1.0)
        backoff: Multiplier for delay after each failure (default: 2.0)
        exceptions: Tuple of exception types to catch (default: all exceptions)

    Returns:
        Decorated function that retries on failure

    Example:
        @retry(max_attempts=3, delay=1.0, backoff=2.0)
        def fetch_data():
            return requests.get("https://api.example.com/data")
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            current_delay = delay
            last_exception = None

            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        time.sleep(current_delay)
                        current_delay *= backoff

            # All retries exhausted
            if last_exception:
                raise last_exception
            raise RuntimeError("Retry failed without exception")

        return wrapper
    return decorator


def retry_with_result(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    should_retry: Callable[[Any], bool] = lambda x: x is None
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Retry decorator based on result value.

    Args:
        max_attempts: Maximum number of attempts (default: 3)
        delay: Initial delay in seconds (default: 1.0)
        backoff: Multiplier for delay after each failure (default: 2.0)
        should_retry: Function that returns True if result should trigger retry

    Returns:
        Decorated function that retries based on result

    Example:
        @retry_with_result(should_retry=lambda x: x is None or x == "")
        def get_config():
            return os.environ.get("CONFIG_VALUE")
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            current_delay = delay

            for attempt in range(max_attempts):
                result = func(*args, **kwargs)
                if not should_retry(result):
                    return result
                if attempt < max_attempts - 1:
                    time.sleep(current_delay)
                    current_delay *= backoff

            return result  # Return last result even if should_retry is True

        return wrapper
    return decorator


class RetryExhausted(Exception):
    """Raised when all retry attempts have been exhausted."""
    def __init__(self, attempts: int, last_exception: Exception | None = None):
        self.attempts = attempts
        self.last_exception = last_exception
        message = f"Retry exhausted after {attempts} attempts"
        if last_exception:
            message += f": {last_exception}"
        super().__init__(message)
