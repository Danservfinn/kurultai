"""
Intent Window Buffer

Collects user messages within a configurable time window (default 45 seconds)
before releasing them as a batch for DAG building.

Author: Claude (Anthropic)
Date: 2026-02-04
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from .kurultai_types import Message, DEFAULT_WINDOW_SECONDS, DEFAULT_MAX_MESSAGES


class IntentWindowBuffer:
    """
    Collects messages within time window before DAG building.

    Async-safe: uses asyncio.Lock instead of threading.Lock.
    Enforces MAX_MESSAGES limit to prevent unbounded memory growth.

    Args:
        window_seconds: Time window in seconds (default: 45)
        max_messages: Maximum messages to buffer (default: 100)

    Example:
        >>> buffer = IntentWindowBuffer(window_seconds=45)
        >>> batch = await buffer.add(Message("Hello", "user123", datetime.now()))
        >>> if batch:
        ...     # Process batch of messages
    """

    MAX_MESSAGES = 100  # Hard limit to prevent unbounded memory growth

    def __init__(self, window_seconds: int = None, max_messages: int = None):
        self.window = window_seconds or DEFAULT_WINDOW_SECONDS
        self.max_messages = max_messages or self.MAX_MESSAGES
        self.pending: List[Message] = []
        self._lock = asyncio.Lock()

    async def add(self, message: Message) -> Optional[List[Message]]:
        """
        Add message to buffer. Returns full batch if window expired.

        Args:
            message: Message to add to buffer

        Returns:
            List of messages if window expired, None if still collecting
        """
        async with self._lock:
            self.pending.append(message)

            # Enforce max_messages limit - drop oldest if exceeded
            if len(self.pending) > self.max_messages:
                self.pending = self.pending[-self.max_messages:]

            if not self.pending:
                return None

            oldest = min(m.timestamp for m in self.pending)
            now = datetime.now(timezone.utc)

            if (now - oldest).total_seconds() >= self.window:
                batch = self.pending.copy()
                self.pending.clear()
                return batch

            return None  # Still collecting

    async def flush(self) -> List[Message]:
        """
        Force flush all pending messages.

        Returns:
            All currently buffered messages
        """
        async with self._lock:
            batch = self.pending.copy()
            self.pending.clear()
            return batch

    async def pending_count(self) -> int:
        """Get current count of pending messages."""
        async with self._lock:
            return len(self.pending)

    def is_empty(self) -> bool:
        """Check if buffer is empty (non-blocking check)."""
        return len(self.pending) == 0

    async def peek(self) -> List[Message]:
        """
        Get a copy of pending messages without clearing the buffer.

        Returns:
            Copy of current pending messages
        """
        async with self._lock:
            return self.pending.copy()

    async def time_until_expiry(self) -> Optional[float]:
        """
        Get time until window expires.

        Returns:
            Seconds until expiry, or None if buffer is empty
        """
        async with self._lock:
            if not self.pending:
                return None

            oldest = min(m.timestamp for m in self.pending)
            now = datetime.now(timezone.utc)
            elapsed = (now - oldest).total_seconds()
            remaining = self.window - elapsed
            return max(0.0, remaining)

    async def add_text(
        self,
        content: str,
        sender_hash: str,
        metadata: Optional[dict] = None
    ) -> Optional[List[Message]]:
        """
        Convenience method to add text message.

        Args:
            content: Message content
            sender_hash: Sender identifier
            metadata: Optional metadata

        Returns:
            List of messages if window expired, None otherwise
        """
        message = Message(
            content=content,
            sender_hash=sender_hash,
            timestamp=datetime.now(timezone.utc),
            metadata=metadata
        )
        return await self.add(message)

    async def wait_for_expiry(self, check_interval: float = 0.5) -> List[Message]:
        """
        Wait for the current window to expire and return the batch.

        Args:
            check_interval: How often to check for expiry (seconds)

        Returns:
            Batch of messages when window expires
        """
        while True:
            time_left = await self.time_until_expiry()
            if time_left is None:
                # Buffer is empty, wait for a message
                await asyncio.sleep(check_interval)
                continue

            if time_left <= 0:
                # Window expired
                return await self.flush()

            # Wait until expiry (or check interval)
            wait_time = min(time_left, check_interval)
            await asyncio.sleep(wait_time)

    def clear(self) -> None:
        """
        Clear the buffer synchronously (use with caution).

        This is a non-blocking clear that should only be used
        when no concurrent access is possible.
        """
        self.pending.clear()

    async def clear_async(self) -> int:
        """
        Clear the buffer asynchronously and return count cleared.

        Returns:
            Number of messages cleared
        """
        async with self._lock:
            count = len(self.pending)
            self.pending.clear()
            return count

    async def get_metadata_summary(self) -> dict:
        """
        Get summary of buffered messages including metadata.

        Returns:
            Dictionary with buffer statistics
        """
        async with self._lock:
            if not self.pending:
                return {
                    "count": 0,
                    "senders": {},
                    "oldest": None,
                    "newest": None,
                }

            senders = {}
            for msg in self.pending:
                senders[msg.sender_hash] = senders.get(msg.sender_hash, 0) + 1

            timestamps = [m.timestamp for m in self.pending]
            oldest = min(timestamps)
            newest = max(timestamps)

            return {
                "count": len(self.pending),
                "senders": senders,
                "oldest": oldest.isoformat(),
                "newest": newest.isoformat(),
                "time_span_seconds": (newest - oldest).total_seconds(),
            }

    def __len__(self) -> int:
        """Get buffer size (non-blocking)."""
        return len(self.pending)

    def __bool__(self) -> bool:
        """Check if buffer has messages (non-blocking)."""
        return len(self.pending) > 0

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"IntentWindowBuffer(window={self.window}s, "
            f"max_messages={self.max_messages}, pending={len(self.pending)})"
        )
