#!/usr/bin/env python3
"""
Squad Chat Client - Python client for agent integration.

Provides a simple async interface for agents to communicate via Squad Chat.

Usage:
    async with SquadChatClient("temujin") as client:
        await client.send_message("Hello from temujin!")
        await client.subscribe("task-123")
        await client.send_message("Working on task", channel="task-123")

    # Or with event handling:
    client = SquadChatClient("temujin")
    client.on_message(lambda msg: print(f"Got: {msg}"))
    await client.connect()
    await client.send_message("Connected!")
    await client.disconnect()
"""

import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Callable, List, Awaitable

try:
    import websockets
except ImportError:
    print("ERROR: websockets package required")
    print("Install with: pip3 install --break-system-packages websockets")
    sys.exit(1)

# Kurultai paths
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kurultai_paths import LOGS_DIR

# Configuration
DEFAULT_SERVER = "ws://localhost:8765/squad"
RECONNECT_DELAY = 1.0
MAX_RECONNECT_DELAY = 30.0

logger = logging.getLogger("squad-chat-client")


@dataclass
class Message:
    """Represents a received message."""
    id: str
    sender: str
    channel: str
    content: str
    timestamp: str
    event_type: str = "message"
    mentions: List[str] = None
    model: str = None


class SquadChatClient:
    """Async client for Squad Chat communication."""

    def __init__(
        self,
        agent_name: str,
        server_url: str = DEFAULT_SERVER,
        model: str = None,
        auto_reconnect: bool = True
    ):
        self.agent_name = agent_name
        self.server_url = server_url
        self.model = model
        self.auto_reconnect = auto_reconnect

        self._websocket = None
        self._connected = False
        self._reconnect_delay = RECONNECT_DELAY
        self._message_handlers: List[Callable[[Message], Awaitable[None]]] = []
        self._receive_task = None
        self._channels = {"system"}

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> bool:
        """Connect to the Squad Chat server."""
        try:
            self._websocket = await websockets.connect(self.server_url)

            # Authenticate
            await self._websocket.send(json.dumps({
                "type": "auth",
                "agent": self.agent_name,
                "model": self.model
            }))

            # Wait for auth response
            response = await asyncio.wait_for(self._websocket.recv(), timeout=10.0)
            data = json.loads(response)

            if data.get("type") == "auth_success":
                self._connected = True
                self._reconnect_delay = RECONNECT_DELAY
                logger.info(f"Connected to Squad Chat as {self.agent_name}")

                # Start receive loop
                self._receive_task = asyncio.create_task(self._receive_loop())

                # Resubscribe to channels
                for channel in self._channels:
                    await self._subscribe_internal(channel)

                return True
            else:
                logger.error(f"Auth failed: {data.get('error', 'Unknown error')}")
                await self._websocket.close()
                return False

        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self._connected = False

            if self.auto_reconnect:
                await self._schedule_reconnect()

            return False

    async def disconnect(self):
        """Disconnect from the server."""
        self._connected = False

        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        if self._websocket:
            await self._websocket.close()
            self._websocket = None

        logger.info(f"Disconnected from Squad Chat")

    async def _schedule_reconnect(self):
        """Schedule a reconnection attempt."""
        logger.info(f"Reconnecting in {self._reconnect_delay}s...")
        await asyncio.sleep(self._reconnect_delay)
        self._reconnect_delay = min(self._reconnect_delay * 2, MAX_RECONNECT_DELAY)
        await self.connect()

    async def _receive_loop(self):
        """Continuously receive messages."""
        try:
            async for message in self._websocket:
                try:
                    data = json.loads(message)

                    # Handle different message types
                    if data.get("type") == "history":
                        # History response - emit as individual messages
                        for msg_data in data.get("messages", []):
                            msg = Message(**msg_data)
                            for handler in self._message_handlers:
                                try:
                                    await handler(msg)
                                except Exception as e:
                                    logger.error(f"Handler error: {e}")
                    else:
                        msg = Message(**data)
                        for handler in self._message_handlers:
                            try:
                                await handler(msg)
                            except Exception as e:
                                logger.error(f"Handler error: {e}")

                except json.JSONDecodeError as e:
                    logger.warning(f"Invalid JSON received: {e}")

        except websockets.ConnectionClosed:
            logger.warning("Connection closed by server")
            self._connected = False

            if self.auto_reconnect:
                await self._schedule_reconnect()

        except Exception as e:
            logger.error(f"Receive error: {e}")
            self._connected = False

    async def _subscribe_internal(self, channel: str):
        """Internal subscribe without tracking."""
        if self._websocket and self._connected:
            await self._websocket.send(json.dumps({
                "type": "subscribe",
                "channel": channel
            }))

    async def subscribe(self, channel: str):
        """Subscribe to a channel."""
        self._channels.add(channel)
        await self._subscribe_internal(channel)

    async def unsubscribe(self, channel: str):
        """Unsubscribe from a channel."""
        self._channels.discard(channel)
        if self._websocket and self._connected:
            await self._websocket.send(json.dumps({
                "type": "unsubscribe",
                "channel": channel
            }))

    async def send_message(
        self,
        content: str,
        channel: str = "system",
        event_type: str = "message"
    ):
        """Send a message to a channel."""
        if not self._connected or not self._websocket:
            logger.warning("Not connected, cannot send message")
            return False

        try:
            await self._websocket.send(json.dumps({
                "type": "message",
                "content": content,
                "channel": channel,
                "event_type": event_type,
                "model": self.model
            }))
            return True
        except Exception as e:
            logger.error(f"Send failed: {e}")
            return False

    async def send_event(self, event_type: str, content: str, channel: str = "system"):
        """Send a system event."""
        return await self.send_message(content, channel=channel, event_type=event_type)

    async def get_history(self, channel: str = "system", limit: int = 100) -> List[Message]:
        """Request message history for a channel."""
        if not self._connected or not self._websocket:
            return []

        await self._websocket.send(json.dumps({
            "type": "history",
            "channel": channel,
            "limit": limit
        }))

        # History will be delivered via the receive loop
        # This is a fire-and-forget request
        return []

    def on_message(self, handler: Callable[[Message], Awaitable[None]]):
        """Register a message handler."""
        self._message_handlers.append(handler)
        return handler

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()


# Convenience functions for synchronous code
def send_message_sync(agent_name: str, content: str, channel: str = "system", model: str = None):
    """Synchronously send a single message."""
    async def _send():
        async with SquadChatClient(agent_name, model=model) as client:
            await client.send_message(content, channel=channel)

    asyncio.run(_send())


def emit_event_sync(agent_name: str, event_type: str, content: str, channel: str = "system"):
    """Synchronously emit an event."""
    async def _emit():
        async with SquadChatClient(agent_name) as client:
            await client.send_event(event_type, content, channel=channel)

    asyncio.run(_emit())


# CLI for testing
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Squad Chat Client")
    parser.add_argument("agent", help="Agent name")
    parser.add_argument("--message", "-m", help="Message to send")
    parser.add_argument("--channel", "-c", default="system", help="Channel")
    parser.add_argument("--listen", action="store_true", help="Listen for messages")
    args = parser.parse_args()

    async def main():
        client = SquadChatClient(args.agent)

        @client.on_message
        async def handle_message(msg: Message):
            print(f"[{msg.timestamp}] {msg.sender}@{msg.channel}: {msg.content}")

        await client.connect()

        if args.message:
            await client.send_message(args.message, channel=args.channel)
            print(f"Sent: {args.message}")

        if args.listen:
            print(f"Listening as {args.agent}...")
            try:
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                pass

        await client.disconnect()

    asyncio.run(main())
