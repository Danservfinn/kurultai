"""
Tests for IntentWindowBuffer

Tests cover:
- Message buffering within time window
- MAX_MESSAGES limit enforcement
- Thread safety with asyncio.Lock
- Manual flush functionality
- Batch release on window expiry

Author: Claude (Anthropic)
Date: 2026-02-04
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta

from tools.kurultai.intent_buffer import IntentWindowBuffer
from tools.kurultai.types import Message


@pytest.mark.asyncio
async def test_buffer_collects_within_window():
    """Test that messages are collected within the time window."""
    buffer = IntentWindowBuffer(window_seconds=1)

    msg1 = Message("Task 1", "user1", datetime.now(timezone.utc))
    result = await buffer.add(msg1)
    assert result is None  # Still collecting

    msg2 = Message("Task 2", "user1", datetime.now(timezone.utc))
    result = await buffer.add(msg2)
    assert result is None  # Still collecting


@pytest.mark.asyncio
async def test_buffer_releases_after_window():
    """Test that batch is released after window expires."""
    buffer = IntentWindowBuffer(window_seconds=0.1)

    msg1 = Message("Task 1", "user1", datetime.now(timezone.utc))
    await buffer.add(msg1)

    # Wait for window to expire
    await asyncio.sleep(0.15)

    msg2 = Message("Task 2", "user1", datetime.now(timezone.utc))
    result = await buffer.add(msg2)

    assert result is not None
    assert len(result) == 2


@pytest.mark.asyncio
async def test_max_messages_limit():
    """Test that buffer enforces MAX_MESSAGES limit."""
    buffer = IntentWindowBuffer(window_seconds=10, max_messages=3)

    for i in range(5):
        msg = Message(f"Task {i}", "user1", datetime.now(timezone.utc))
        await buffer.add(msg)

    # Should only have last 3 messages
    count = await buffer.pending_count()
    assert count == 3


@pytest.mark.asyncio
async def test_flush():
    """Test manual flush."""
    buffer = IntentWindowBuffer(window_seconds=10)

    await buffer.add(Message("Task 1", "user1", datetime.now(timezone.utc)))
    await buffer.add(Message("Task 2", "user1", datetime.now(timezone.utc)))

    batch = await buffer.flush()
    assert len(batch) == 2
    assert await buffer.pending_count() == 0


@pytest.mark.asyncio
async def test_concurrent_access():
    """Test that buffer is thread-safe for concurrent access."""
    buffer = IntentWindowBuffer(window_seconds=1)

    async def add_messages(n):
        for i in range(n):
            msg = Message(f"Task {i}", "user1", datetime.now(timezone.utc))
            await buffer.add(msg)

    # Run concurrent additions
    await asyncio.gather(
        add_messages(10),
        add_messages(10),
        add_messages(10)
    )

    count = await buffer.pending_count()
    assert count == 30


@pytest.mark.asyncio
async def test_add_text_convenience_method():
    """Test the add_text convenience method."""
    buffer = IntentWindowBuffer(window_seconds=10)

    result = await buffer.add_text("Hello world", "user123")

    assert result is None  # Window not expired
    assert await buffer.pending_count() == 1
    assert len(buffer) == 1


@pytest.mark.asyncio
async def test_is_empty():
    """Test is_empty check."""
    buffer = IntentWindowBuffer(window_seconds=10)

    assert buffer.is_empty() is True

    await buffer.add_text("Test", "user1")
    assert buffer.is_empty() is False

    await buffer.flush()
    assert buffer.is_empty() is True


@pytest.mark.asyncio
async def test_time_until_expiry():
    """Test time_until_expiry calculation."""
    buffer = IntentWindowBuffer(window_seconds=1)

    # Empty buffer
    assert await buffer.time_until_expiry() is None

    # Add message
    await buffer.add_text("Test", "user1")
    time_left = await buffer.time_until_expiry()

    assert time_left is not None
    assert 0 <= time_left <= 1


@pytest.mark.asyncio
async def test_wait_for_expiry():
    """Test waiting for window expiry."""
    buffer = IntentWindowBuffer(window_seconds=0.1)

    await buffer.add_text("Task 1", "user1")

    # Wait for expiry
    batch = await buffer.wait_for_expiry(check_interval=0.05)

    assert len(batch) == 1
    assert batch[0].content == "Task 1"


@pytest.mark.asyncio
async def test_clear_async():
    """Test async clear method."""
    buffer = IntentWindowBuffer(window_seconds=10)

    await buffer.add_text("Task 1", "user1")
    await buffer.add_text("Task 2", "user1")

    count = await buffer.clear_async()
    assert count == 2
    assert await buffer.pending_count() == 0


@pytest.mark.asyncio
async def test_get_metadata_summary():
    """Test metadata summary."""
    buffer = IntentWindowBuffer(window_seconds=10)

    await buffer.add_text("Task 1", "user1")
    await buffer.add_text("Task 2", "user1")
    await buffer.add_text("Task 3", "user2")

    summary = await buffer.get_metadata_summary()

    assert summary["count"] == 3
    assert summary["senders"]["user1"] == 2
    assert summary["senders"]["user2"] == 1
    assert "oldest" in summary
    assert "newest" in summary


@pytest.mark.asyncio
async def test_peek_doesnt_clear_buffer():
    """Test that peek doesn't clear the buffer."""
    buffer = IntentWindowBuffer(window_seconds=10)

    await buffer.add_text("Task 1", "user1")

    peeked = await buffer.peek()
    assert len(peeked) == 1

    # Buffer should still have the message
    assert await buffer.pending_count() == 1


@pytest.mark.asyncio
async def test_non_blocking_length_and_bool():
    """Test __len__ and __bool__ methods."""
    buffer = IntentWindowBuffer(window_seconds=10)

    assert len(buffer) == 0
    assert not buffer  # __bool__ should return False

    await buffer.add_text("Task 1", "user1")

    assert len(buffer) == 1
    assert buffer  # __bool__ should return True


@pytest.mark.asyncio
async def test_metadata_preserved():
    """Test that message metadata is preserved."""
    buffer = IntentWindowBuffer(window_seconds=0.1)

    metadata = {"priority": "high", "source": "api"}
    await buffer.add_text("Task 1", "user1", metadata=metadata)

    await asyncio.sleep(0.15)
    batch = await buffer.flush()

    assert batch is not None
    first_msg = next((m for m in batch if m.content == "Task 1"), None)
    assert first_msg is not None
    assert first_msg.metadata == metadata


@pytest.mark.asyncio
async def test_repr():
    """Test string representation."""
    buffer = IntentWindowBuffer(window_seconds=45, max_messages=100)

    repr_str = repr(buffer)
    assert "IntentWindowBuffer" in repr_str
    assert "window=45s" in repr_str
    assert "max_messages=100" in repr_str
    assert "pending=0" in repr_str


@pytest.mark.asyncio
async def test_multiple_sequential_windows():
    """Test multiple sequential windows."""
    buffer = IntentWindowBuffer(window_seconds=0.1)

    # First window
    await buffer.add_text("W1-M1", "user1")
    await asyncio.sleep(0.15)
    batch1 = await buffer.add_text("W1-Trigger", "user1")

    assert batch1 is not None

    # Second window
    await buffer.add_text("W2-M1", "user1")
    await buffer.add_text("W2-M2", "user1")
    await asyncio.sleep(0.15)
    batch2 = await buffer.add_text("W2-Trigger", "user1")

    assert batch2 is not None

    # Verify separation
    all_content = [m.content for m in batch1 + batch2]
    assert "W1-M1" in all_content
    assert "W2-M1" in all_content
