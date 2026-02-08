"""Rate limiter for Kurultai v0.2 task operations.

Enforces per-agent request limits to prevent abuse and ensure fair resource allocation.
"""

import time
from collections import defaultdict
from typing import Optional


class RateLimiter:
    """Token-bucket rate limiter for task operations.

    Args:
        max_per_hour: Maximum requests per hour per agent.
        max_per_batch: Maximum requests per batch operation.
    """

    def __init__(self, max_per_hour: int = 1000, max_per_batch: int = 100):
        self.max_per_hour = max_per_hour
        self.max_per_batch = max_per_batch
        self._requests: dict = defaultdict(list)

    def _cleanup(self, agent_id: str) -> None:
        """Remove requests older than 1 hour."""
        cutoff = time.time() - 3600
        self._requests[agent_id] = [
            ts for ts in self._requests[agent_id] if ts > cutoff
        ]

    def check(self, agent_id: str) -> bool:
        """Check if agent is within rate limit.

        Args:
            agent_id: The agent requesting access.

        Returns:
            True if request is allowed, False if rate limited.
        """
        self._cleanup(agent_id)
        return len(self._requests[agent_id]) < self.max_per_hour

    def record(self, agent_id: str) -> bool:
        """Record a request and check if allowed.

        Args:
            agent_id: The agent making the request.

        Returns:
            True if allowed, False if rate limited.

        Raises:
            RuntimeError: If rate limit exceeded.
        """
        if not self.check(agent_id):
            raise RuntimeError(
                f"Rate limit exceeded for agent {agent_id}: "
                f"{len(self._requests[agent_id])}/{self.max_per_hour} per hour"
            )
        self._requests[agent_id].append(time.time())
        return True

    def check_batch(self, batch_size: int) -> bool:
        """Check if batch size is within limits.

        Args:
            batch_size: Number of items in the batch.

        Returns:
            True if batch is allowed.

        Raises:
            ValueError: If batch exceeds max_per_batch.
        """
        if batch_size > self.max_per_batch:
            raise ValueError(
                f"Batch size {batch_size} exceeds max {self.max_per_batch}"
            )
        return True

    def get_remaining(self, agent_id: str) -> int:
        """Get remaining requests for agent in current window."""
        self._cleanup(agent_id)
        return max(0, self.max_per_hour - len(self._requests[agent_id]))
