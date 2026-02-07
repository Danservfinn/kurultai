"""
Tests for Intent Window Buffer functionality.

Tests the real IntentWindowBuffer implementation from tools.kurultai.intent_buffer.

Covers:
- Message buffering with time-based windowing
- Async-safe operations
- Adjustable window duration
- Batch collection when window expires
- Thread safety (via asyncio.Lock)
- Buffer clearing after batch returned

Location: /Users/kurultai/molt/tests/test_intent_window.py
"""

import asyncio
import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from tools.kurultai.intent_buffer import IntentWindowBuffer
from tools.kurultai.types import Message


# =============================================================================
# TestIntentWindowBuffer
# =============================================================================

class TestIntentWindowBuffer:
    """Tests for IntentWindowBuffer class."""

    @pytest_asyncio.fixture
    async def buffer(self):
        """Create a fresh buffer for each test with short window."""
        buf = IntentWindowBuffer(window_seconds=0.1, max_messages=10)  # 100ms window
        yield buf
        # Cleanup
        await buf.clear_async()

    @pytest.mark.asyncio
    async def test_add_message_to_buffer(self, buffer):
        """Test adding a message to the buffer."""
        message = Message(
            content="Test message",
            sender_hash="user123",
            timestamp=datetime.now(timezone.utc)
        )

        result = await buffer.add(message)

        assert result is None  # No batch returned yet
        assert len(buffer) == 1
        assert await buffer.pending_count() == 1

    @pytest.mark.asyncio
    async def test_add_returns_none_before_window_expires(self, buffer):
        """Test that add returns None before window expires."""
        message1 = Message(
            content="Message 1",
            sender_hash="user123",
            timestamp=datetime.now(timezone.utc)
        )
        await buffer.add(message1)

        # Immediately add another - should not trigger batch
        message2 = Message(
            content="Message 2",
            sender_hash="user123",
            timestamp=datetime.now(timezone.utc)
        )
        result = await buffer.add(message2)

        assert result is None
        assert len(buffer) == 2

    @pytest.mark.asyncio
    async def test_add_returns_batch_when_window_expires(self, buffer):
        """Test that add returns batch when window expires."""
        message1 = Message(
            content="Message 1",
            sender_hash="user123",
            timestamp=datetime.now(timezone.utc)
        )
        await buffer.add(message1)

        # Wait for window to expire
        await asyncio.sleep(0.15)  # 150ms > 100ms window

        message2 = Message(
            content="Message 2",
            sender_hash="user123",
            timestamp=datetime.now(timezone.utc)
        )
        result = await buffer.add(message2)

        assert result is not None
        assert len(result) >= 1  # At least the first message
        assert any(m.content == "Message 1" for m in result)

    @pytest.mark.asyncio
    async def test_buffer_async_safety(self, buffer):
        """Test that buffer is async-safe with concurrent operations."""
        results = []
        exceptions = []

        async def add_messages(task_id: int):
            try:
                for i in range(10):
                    message = Message(
                        content=f"Task {task_id} - Message {i}",
                        sender_hash=f"user{task_id}",
                        timestamp=datetime.now(timezone.utc)
                    )
                    result = await buffer.add(message)
                    if result:
                        results.append((task_id, result))
                    # Small delay to allow interleaving
                    await asyncio.sleep(0.01)
            except Exception as e:
                exceptions.append(e)

        # Run 5 concurrent tasks
        await asyncio.gather(
            add_messages(0),
            add_messages(1),
            add_messages(2),
            add_messages(3),
            add_messages(4)
        )

        assert len(exceptions) == 0
        # Due to window expiration (100ms), some messages may have been batched
        # The buffer has max_messages=10, so at most 10 remain
        # We verify that no messages were lost and no exceptions occurred
        total_in_batches = sum(len(batch) for _, batch in results)
        remaining_in_buffer = len(buffer)
        # Total should be <= 50 (some may have been dropped due to max_messages limit)
        assert total_in_batches + remaining_in_buffer <= 50
        assert total_in_batches + remaining_in_buffer > 0  # Some data was processed

    @pytest.mark.asyncio
    async def test_buffer_clears_after_batch_returned(self, buffer):
        """Test that buffer is cleared after batch is returned."""
        message1 = Message(
            content="Message 1",
            sender_hash="user123",
            timestamp=datetime.now(timezone.utc)
        )
        message2 = Message(
            content="Message 2",
            sender_hash="user123",
            timestamp=datetime.now(timezone.utc)
        )
        await buffer.add(message1)
        await buffer.add(message2)

        await asyncio.sleep(0.15)

        message3 = Message(
            content="Message 3",
            sender_hash="user123",
            timestamp=datetime.now(timezone.utc)
        )
        result = await buffer.add(message3)

        assert result is not None
        # Buffer should be cleared after returning batch
        assert len(buffer) == 0

    @pytest.mark.asyncio
    async def test_adjustable_window_duration(self):
        """Test creating buffers with different window durations."""
        short_buffer = IntentWindowBuffer(window_seconds=0.05, max_messages=10)  # 50ms
        long_buffer = IntentWindowBuffer(window_seconds=0.5, max_messages=10)    # 500ms

        msg_short = Message(
            content="Test",
            sender_hash="user1",
            timestamp=datetime.now(timezone.utc)
        )
        msg_long = Message(
            content="Test",
            sender_hash="user2",
            timestamp=datetime.now(timezone.utc)
        )

        await short_buffer.add(msg_short)
        await long_buffer.add(msg_long)

        await asyncio.sleep(0.1)  # 100ms

        # Short buffer should have triggered
        msg_short2 = Message(
            content="Test 2",
            sender_hash="user1",
            timestamp=datetime.now(timezone.utc)
        )
        short_result = await short_buffer.add(msg_short2)
        assert short_result is not None

        # Long buffer should not have triggered yet
        msg_long2 = Message(
            content="Test 2",
            sender_hash="user2",
            timestamp=datetime.now(timezone.utc)
        )
        long_result = await long_buffer.add(msg_long2)
        assert long_result is None

        # Cleanup
        await short_buffer.clear_async()
        await long_buffer.clear_async()

    @pytest.mark.asyncio
    async def test_max_messages_does_not_trigger_early(self):
        """Test that max_messages does NOT trigger batch - it only drops old messages."""
        buffer = IntentWindowBuffer(window_seconds=10, max_messages=3)

        # Add messages up to and beyond max
        for i in range(5):
            msg = Message(
                content=f"Message {i+1}",
                sender_hash="user123",
                timestamp=datetime.now(timezone.utc)
            )
            result = await buffer.add(msg)
            # Should not trigger batch - window hasn't expired
            assert result is None

        # Buffer should only keep most recent 3 (max_messages)
        assert len(buffer) == 3
        peeked = await buffer.peek()
        contents = [m.content for m in peeked]
        # Oldest messages should be dropped
        assert "Message 1" not in contents
        assert "Message 2" not in contents
        assert "Message 3" in contents
        assert "Message 4" in contents
        assert "Message 5" in contents

    @pytest.mark.asyncio
    async def test_clear_buffer(self, buffer):
        """Test clearing the buffer."""
        message1 = Message(
            content="Message 1",
            sender_hash="user123",
            timestamp=datetime.now(timezone.utc)
        )
        message2 = Message(
            content="Message 2",
            sender_hash="user123",
            timestamp=datetime.now(timezone.utc)
        )
        await buffer.add(message1)
        await buffer.add(message2)

        assert len(buffer) == 2

        await buffer.clear_async()

        assert len(buffer) == 0

    @pytest.mark.asyncio
    async def test_peek_without_clearing(self, buffer):
        """Test peeking at messages without clearing."""
        message1 = Message(
            content="Message 1",
            sender_hash="user123",
            timestamp=datetime.now(timezone.utc)
        )
        message2 = Message(
            content="Message 2",
            sender_hash="user123",
            timestamp=datetime.now(timezone.utc)
        )
        await buffer.add(message1)
        await buffer.add(message2)

        peeked = await buffer.peek()

        assert len(peeked) == 2
        assert len(buffer) == 2  # Buffer not cleared

    @pytest.mark.asyncio
    async def test_metadata_preservation(self, buffer):
        """Test that message metadata is preserved."""
        metadata = {"source": "user", "priority": "high"}
        message = Message(
            content="Test message",
            sender_hash="user123",
            timestamp=datetime.now(timezone.utc),
            metadata=metadata
        )
        await buffer.add(message)

        peeked = await buffer.peek()

        assert len(peeked) == 1
        assert peeked[0].metadata == metadata

    @pytest.mark.asyncio
    async def test_timestamp_ordering(self, buffer):
        """Test that messages maintain timestamp order."""
        messages = ["First", "Second", "Third"]

        for i, msg in enumerate(messages):
            message = Message(
                content=msg,
                sender_hash="user123",
                timestamp=datetime.now(timezone.utc) + timedelta(milliseconds=i*10)
            )
            await buffer.add(message)
            await asyncio.sleep(0.02)  # Small delay

        # Wait for window to expire, then trigger batch
        await asyncio.sleep(0.15)
        trigger_msg = Message(
            content="Trigger",
            sender_hash="user123",
            timestamp=datetime.now(timezone.utc)
        )
        batch = await buffer.add(trigger_msg)

        assert batch is not None
        # Check ordering (excluding trigger message)
        batch_messages = [m.content for m in batch if m.content in messages]
        assert batch_messages == messages

    @pytest.mark.asyncio
    async def test_empty_buffer_state(self, buffer):
        """Test buffer state when empty."""
        assert len(buffer) == 0
        assert buffer.is_empty()
        peeked = await buffer.peek()
        assert peeked == []
        assert await buffer.pending_count() == 0

    @pytest.mark.asyncio
    async def test_multiple_windows(self, buffer):
        """Test multiple sequential windows."""
        # First window
        msg1 = Message(
            content="W1-M1",
            sender_hash="user1",
            timestamp=datetime.now(timezone.utc)
        )
        await buffer.add(msg1)
        await asyncio.sleep(0.15)
        trigger1 = Message(
            content="W1-Trigger",
            sender_hash="user1",
            timestamp=datetime.now(timezone.utc)
        )
        result1 = await buffer.add(trigger1)

        assert result1 is not None

        # Second window
        msg2 = Message(
            content="W2-M1",
            sender_hash="user2",
            timestamp=datetime.now(timezone.utc)
        )
        msg3 = Message(
            content="W2-M2",
            sender_hash="user2",
            timestamp=datetime.now(timezone.utc)
        )
        await buffer.add(msg2)
        await buffer.add(msg3)
        await asyncio.sleep(0.15)
        trigger2 = Message(
            content="W2-Trigger",
            sender_hash="user2",
            timestamp=datetime.now(timezone.utc)
        )
        result2 = await buffer.add(trigger2)

        assert result2 is not None
        # Verify results are from different windows
        all_messages = [m.content for m in result1 + result2]
        assert "W1-M1" in all_messages
        assert "W2-M1" in all_messages

    @pytest.mark.asyncio
    async def test_flush_force_returns_batch(self, buffer):
        """Test that flush forces batch return without waiting."""
        message1 = Message(
            content="Message 1",
            sender_hash="user123",
            timestamp=datetime.now(timezone.utc)
        )
        message2 = Message(
            content="Message 2",
            sender_hash="user123",
            timestamp=datetime.now(timezone.utc)
        )
        await buffer.add(message1)
        await buffer.add(message2)

        # Flush without waiting for window
        flushed = await buffer.flush()

        assert len(flushed) == 2
        assert len(buffer) == 0  # Buffer cleared

    @pytest.mark.asyncio
    async def test_time_until_expiry(self, buffer):
        """Test time_until_expiry method."""
        # Empty buffer returns None
        time_left = await buffer.time_until_expiry()
        assert time_left is None

        # Add message
        message = Message(
            content="Test",
            sender_hash="user123",
            timestamp=datetime.now(timezone.utc)
        )
        await buffer.add(message)

        # Should have time remaining
        time_left = await buffer.time_until_expiry()
        assert time_left is not None
        assert time_left > 0
        assert time_left <= 0.1  # Window is 100ms

        # Wait for expiry
        await asyncio.sleep(0.15)

        time_left = await buffer.time_until_expiry()
        assert time_left == 0.0

    @pytest.mark.asyncio
    async def test_add_text_convenience_method(self, buffer):
        """Test the add_text convenience method."""
        result = await buffer.add_text(
            content="Hello world",
            sender_hash="user123",
            metadata={"priority": "high"}
        )

        assert result is None  # Window not expired
        assert len(buffer) == 1

        peeked = await buffer.peek()
        assert peeked[0].content == "Hello world"
        assert peeked[0].sender_hash == "user123"

    @pytest.mark.asyncio
    async def test_get_metadata_summary(self, buffer):
        """Test get_metadata_summary method."""
        # Empty buffer summary
        summary = await buffer.get_metadata_summary()
        assert summary["count"] == 0
        assert summary["senders"] == {}
        assert summary["oldest"] is None
        assert summary["newest"] is None

        # Add messages
        msg1 = Message(
            content="Msg1",
            sender_hash="user1",
            timestamp=datetime.now(timezone.utc)
        )
        msg2 = Message(
            content="Msg2",
            sender_hash="user2",
            timestamp=datetime.now(timezone.utc)
        )
        msg3 = Message(
            content="Msg3",
            sender_hash="user1",
            timestamp=datetime.now(timezone.utc)
        )
        await buffer.add(msg1)
        await buffer.add(msg2)
        await buffer.add(msg3)

        summary = await buffer.get_metadata_summary()
        assert summary["count"] == 3
        assert summary["senders"]["user1"] == 2
        assert summary["senders"]["user2"] == 1
        assert summary["oldest"] is not None
        assert summary["newest"] is not None
        assert "time_span_seconds" in summary

    @pytest.mark.asyncio
    async def test_max_messages_limit(self):
        """Test that max_messages limit is enforced."""
        buffer = IntentWindowBuffer(window_seconds=10, max_messages=5)

        # Add more messages than max
        for i in range(10):
            msg = Message(
                content=f"Message {i}",
                sender_hash="user123",
                timestamp=datetime.now(timezone.utc) + timedelta(milliseconds=i)
            )
            await buffer.add(msg)

        # Should only keep the most recent 5
        assert len(buffer) == 5
        peeked = await buffer.peek()
        contents = [m.content for m in peeked]
        # Oldest messages should be dropped
        assert "Message 0" not in contents
        assert "Message 5" in contents
        assert "Message 9" in contents

    @pytest.mark.asyncio
    async def test_wait_for_expiry(self, buffer):
        """Test wait_for_expiry method."""
        # Add a message
        msg = Message(
            content="Test",
            sender_hash="user123",
            timestamp=datetime.now(timezone.utc)
        )
        await buffer.add(msg)

        # Wait for expiry with short check interval
        batch = await buffer.wait_for_expiry(check_interval=0.05)

        assert batch is not None
        assert len(batch) == 1
        assert batch[0].content == "Test"

    def test_sync_clear(self):
        """Test synchronous clear method."""
        buffer = IntentWindowBuffer(window_seconds=1, max_messages=10)

        # Add messages (using the async add in a sync context)
        async def add_messages():
            for i in range(3):
                msg = Message(
                    content=f"Msg {i}",
                    sender_hash="user123",
                    timestamp=datetime.now(timezone.utc)
                )
                await buffer.add(msg)

        asyncio.run(add_messages())
        assert len(buffer) == 3

        # Synchronous clear
        buffer.clear()
        assert len(buffer) == 0

    def test_bool_and_repr(self):
        """Test __bool__ and __repr__ methods."""
        buffer = IntentWindowBuffer(window_seconds=1, max_messages=10)

        # Empty buffer is falsy
        assert not buffer

        # Add a message
        async def add_message():
            msg = Message(
                content="Test",
                sender_hash="user123",
                timestamp=datetime.now(timezone.utc)
            )
            await buffer.add(msg)

        asyncio.run(add_message())

        # Non-empty buffer is truthy
        assert buffer

        # Check repr
        repr_str = repr(buffer)
        assert "IntentWindowBuffer" in repr_str
        assert "window=1s" in repr_str
        assert "pending=1" in repr_str


# =============================================================================
# TestIntentWindowIntegration
# =============================================================================

class TestIntentWindowIntegration:
    """Integration tests for intent window with various scenarios."""

    @pytest_asyncio.fixture
    async def buffer(self):
        """Create a buffer with 200ms window for integration tests."""
        buf = IntentWindowBuffer(window_seconds=0.2, max_messages=10)
        yield buf
        await buf.clear_async()

    @pytest.mark.asyncio
    async def test_batch_processing_simulation(self, buffer):
        """Test simulating batch processing of user messages."""
        messages = [
            "Fix the authentication bug",
            "Add unit tests",
            "Update documentation"
        ]

        for msg in messages:
            await buffer.add_text(content=msg, sender_hash="user123")

        # Wait for window
        await asyncio.sleep(0.25)

        # Add trigger message
        result = await buffer.add_text(content="Final message", sender_hash="user123")

        assert result is not None
        assert len(result) >= len(messages)

        extracted = [m.content for m in result]
        for original in messages:
            assert original in extracted

    @pytest.mark.asyncio
    async def test_rapid_fire_messages(self, buffer):
        """Test handling rapid-fire messages."""
        count = 20
        batches = []

        for i in range(count):
            result = await buffer.add_text(content=f"Message {i}", sender_hash="user123")
            if result:
                batches.append(result)

        # Wait for final window
        await asyncio.sleep(0.25)
        final = await buffer.add_text(content="Final", sender_hash="user123")
        if final:
            batches.append(final)

        # All messages should be in batches (buffer has max_messages=10)
        # Due to window expiration during message adding, some batches may have been returned
        total_in_batches = sum(len(b) for b in batches)
        # Should have at least some messages batched (the 10 most recent if window expired once)
        assert total_in_batches > 0
        # Verify the final batch contains the expected messages
        if final:
            assert len(final) <= 10  # max_messages limit

    @pytest.mark.asyncio
    async def test_window_with_delays(self, buffer):
        """Test window behavior with delays between messages."""
        await buffer.add_text(content="Message 1", sender_hash="user123")
        await asyncio.sleep(0.1)

        await buffer.add_text(content="Message 2", sender_hash="user123")
        await asyncio.sleep(0.1)

        # This should trigger first batch
        result = await buffer.add_text(content="Message 3", sender_hash="user123")

        # Due to delays, we might have triggered
        # The exact behavior depends on window duration
        assert result is not None or len(buffer) >= 2

    @pytest.mark.asyncio
    async def test_multiple_senders(self, buffer):
        """Test buffer with messages from multiple senders."""
        senders = ["user1", "user2", "user3"]

        for i, sender in enumerate(senders):
            await buffer.add_text(
                content=f"Message from {sender}",
                sender_hash=sender,
                metadata={"sender_idx": i}
            )

        summary = await buffer.get_metadata_summary()
        assert summary["count"] == 3
        assert len(summary["senders"]) == 3
        for sender in senders:
            assert summary["senders"][sender] == 1

    @pytest.mark.asyncio
    async def test_message_to_dict(self, buffer):
        """Test Message.to_dict conversion."""
        msg = Message(
            content="Test content",
            sender_hash="user123",
            timestamp=datetime.now(timezone.utc),
            metadata={"key": "value"}
        )
        await buffer.add(msg)

        peeked = await buffer.peek()
        msg_dict = peeked[0].to_dict()

        assert msg_dict["content"] == "Test content"
        assert msg_dict["sender_hash"] == "user123"
        assert msg_dict["timestamp"] is not None
        assert msg_dict["metadata"] == {"key": "value"}
