#!/usr/bin/env python3
"""
Squad Chat Server - Real-time agent communication via WebSocket.

Provides inter-agent messaging for the Kurultai multi-agent system.
Supports task-specific channels, @mention notifications, and message history.

Usage:
    python3 squad-chat-server.py --port 8765
    python3 squad-chat-server.py --daemon

Endpoints:
    ws://localhost:8765/squad - WebSocket endpoint for agents
    GET /history/{task_id} - REST endpoint for message history
    GET /status - Health check

LaunchDaemon:
    launchctl load ~/Library/LaunchAgents/com.kurultai.squad-chat.plist
"""

import argparse
import asyncio
import json
import logging
import os
import re
import signal
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Set, Dict, List, Callable
from collections import defaultdict

# WebSocket and HTTP support
try:
    import websockets
    from websockets.server import serve
    from aiohttp import web
except ImportError as e:
    print(f"ERROR: Missing dependency: {e}")
    print("Install with: pip3 install --break-system-packages websockets aiohttp")
    sys.exit(1)

# Kurultai paths
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kurultai_paths import LOGS_DIR, VALID_AGENTS

# Configuration
SQUAD_CHAT_DIR = LOGS_DIR / "squad-chat"
MESSAGE_LOG = SQUAD_CHAT_DIR / "messages.jsonl"
STATE_FILE = SQUAD_CHAT_DIR / "server-state.json"
DEFAULT_PORT = 8765
HTTP_PORT = 8766  # REST API port

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger("squad-chat")


@dataclass
class Message:
    """Represents a chat message."""
    id: str
    sender: str
    channel: str  # "system" or task_id
    content: str
    timestamp: str
    event_type: str = "message"  # message, agent.spawned, agent.completed, etc.
    mentions: List[str] = None
    model: str = None  # Model attribution

    def __post_init__(self):
        if self.mentions is None:
            self.mentions = []
        if self.id is None:
            self.id = f"msg-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"


@dataclass
class AgentConnection:
    """Tracks an agent's connection state."""
    agent_name: str
    websocket: any
    connected_at: str
    channels: Set[str]
    model: str = None

    def to_dict(self):
        return {
            "agent": self.agent_name,
            "connected_at": self.connected_at,
            "channels": list(self.channels),
            "model": self.model
        }


class SquadChatServer:
    """WebSocket server for real-time agent communication."""

    def __init__(self, port: int = DEFAULT_PORT):
        self.port = port
        self.connections: Dict[str, AgentConnection] = {}  # agent_name -> connection
        self.channel_subscribers: Dict[str, Set[str]] = defaultdict(set)  # channel -> agent_names
        self.message_handlers: List[Callable] = []
        self.running = False

        # Ensure directories exist
        SQUAD_CHAT_DIR.mkdir(parents=True, exist_ok=True)

    def _generate_message_id(self) -> str:
        return f"msg-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"

    def _extract_mentions(self, content: str) -> List[str]:
        """Extract @mentions from message content."""
        mentions = re.findall(r'@(\w+)', content)
        return [m for m in mentions if m in VALID_AGENTS]

    async def _broadcast_to_channel(self, channel: str, message: Message, exclude: str = None):
        """Broadcast message to all agents in a channel."""
        subscribers = self.channel_subscribers.get(channel, set())
        for agent_name in subscribers:
            if agent_name == exclude:
                continue
            conn = self.connections.get(agent_name)
            if conn and conn.websocket:
                try:
                    await conn.websocket.send(json.dumps(asdict(message)))
                except Exception as e:
                    logger.warning(f"Failed to send to {agent_name}: {e}")

    async def _save_message(self, message: Message):
        """Persist message to JSONL log."""
        try:
            with open(MESSAGE_LOG, "a") as f:
                f.write(json.dumps(asdict(message)) + "\n")
        except Exception as e:
            logger.error(f"Failed to save message: {e}")

    def _load_recent_history(self, channel: str, limit: int = 100) -> List[dict]:
        """Load recent messages for a channel."""
        messages = []
        try:
            if MESSAGE_LOG.exists():
                with open(MESSAGE_LOG, "r") as f:
                    for line in f:
                        try:
                            msg = json.loads(line.strip())
                            if msg.get("channel") == channel:
                                messages.append(msg)
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            logger.error(f"Failed to load history: {e}")
        return messages[-limit:]

    async def _handle_message(self, agent_name: str, data: dict):
        """Process incoming message from an agent."""
        msg_type = data.get("type", "message")

        if msg_type == "message":
            content = data.get("content", "")
            channel = data.get("channel", "system")
            event_type = data.get("event_type", "message")

            # Extract mentions
            mentions = self._extract_mentions(content)

            # Create message
            message = Message(
                id=self._generate_message_id(),
                sender=agent_name,
                channel=channel,
                content=content,
                timestamp=datetime.now().isoformat(),
                event_type=event_type,
                mentions=mentions,
                model=data.get("model") or self.connections[agent_name].model
            )

            # Save and broadcast
            await self._save_message(message)
            await self._broadcast_to_channel(channel, message, exclude=agent_name)

            # Send mention notifications
            for mentioned in mentions:
                if mentioned in self.connections:
                    notification = Message(
                        id=self._generate_message_id(),
                        sender="system",
                        channel=f"notify:{mentioned}",
                        content=f"You were mentioned by {agent_name} in #{channel}",
                        timestamp=datetime.now().isoformat(),
                        event_type="mention",
                        mentions=[mentioned]
                    )
                    conn = self.connections.get(mentioned)
                    if conn and conn.websocket:
                        await conn.websocket.send(json.dumps(asdict(notification)))

            # Call registered handlers
            for handler in self.message_handlers:
                try:
                    await handler(message)
                except Exception as e:
                    logger.error(f"Handler error: {e}")

        elif msg_type == "subscribe":
            channel = data.get("channel", "system")
            if agent_name in self.connections:
                self.connections[agent_name].channels.add(channel)
                self.channel_subscribers[channel].add(agent_name)
                logger.info(f"{agent_name} subscribed to #{channel}")

                # Send recent history
                history = self._load_recent_history(channel, limit=50)
                if history:
                    conn = self.connections[agent_name]
                    if conn.websocket:
                        await conn.websocket.send(json.dumps({
                            "type": "history",
                            "channel": channel,
                            "messages": history
                        }))

        elif msg_type == "unsubscribe":
            channel = data.get("channel", "system")
            if agent_name in self.connections:
                self.connections[agent_name].channels.discard(channel)
            self.channel_subscribers[channel].discard(agent_name)
            logger.info(f"{agent_name} unsubscribed from #{channel}")

        elif msg_type == "history":
            channel = data.get("channel", "system")
            limit = data.get("limit", 100)
            history = self._load_recent_history(channel, limit=limit)
            if agent_name in self.connections:
                conn = self.connections[agent_name]
                if conn.websocket:
                    await conn.websocket.send(json.dumps({
                        "type": "history",
                        "channel": channel,
                        "messages": history
                    }))

    async def _handle_connection(self, websocket, path: str = "/squad"):
        """Handle a new WebSocket connection."""
        agent_name = None
        try:
            # Wait for authentication
            auth_msg = await asyncio.wait_for(websocket.recv(), timeout=10.0)
            auth_data = json.loads(auth_msg)

            if auth_data.get("type") != "auth":
                await websocket.send(json.dumps({"error": "Authentication required"}))
                await websocket.close()
                return

            agent_name = auth_data.get("agent")
            model = auth_data.get("model")

            if agent_name not in VALID_AGENTS and not agent_name.startswith("subagent-"):
                await websocket.send(json.dumps({"error": f"Invalid agent: {agent_name}"}))
                await websocket.close()
                return

            # Register connection
            self.connections[agent_name] = AgentConnection(
                agent_name=agent_name,
                websocket=websocket,
                connected_at=datetime.now().isoformat(),
                channels={"system"},
                model=model
            )
            self.channel_subscribers["system"].add(agent_name)

            await websocket.send(json.dumps({
                "type": "auth_success",
                "agent": agent_name,
                "message": f"Connected to Squad Chat"
            }))

            logger.info(f"Agent connected: {agent_name}")

            # Broadcast join event
            join_msg = Message(
                id=self._generate_message_id(),
                sender="system",
                channel="system",
                content=f"{agent_name} joined the squad",
                timestamp=datetime.now().isoformat(),
                event_type="agent.joined"
            )
            await self._save_message(join_msg)
            await self._broadcast_to_channel("system", join_msg, exclude=agent_name)

            # Message loop
            async for message in websocket:
                try:
                    data = json.loads(message)
                    await self._handle_message(agent_name, data)
                except json.JSONDecodeError as e:
                    logger.warning(f"Invalid JSON from {agent_name}: {e}")
                except Exception as e:
                    logger.error(f"Error handling message from {agent_name}: {e}")

        except asyncio.TimeoutError:
            await websocket.send(json.dumps({"error": "Authentication timeout"}))
            await websocket.close()
        except Exception as e:
            logger.error(f"Connection error: {e}")
        finally:
            # Cleanup on disconnect
            if agent_name and agent_name in self.connections:
                del self.connections[agent_name]
                for channel_subs in self.channel_subscribers.values():
                    channel_subs.discard(agent_name)

                # Broadcast leave event
                leave_msg = Message(
                    id=self._generate_message_id(),
                    sender="system",
                    channel="system",
                    content=f"{agent_name} left the squad",
                    timestamp=datetime.now().isoformat(),
                    event_type="agent.left"
                )
                await self._save_message(leave_msg)
                await self._broadcast_to_channel("system", leave_msg)

                logger.info(f"Agent disconnected: {agent_name}")

    def on_message(self, handler: Callable):
        """Register a message handler."""
        self.message_handlers.append(handler)
        return handler

    async def start(self):
        """Start the WebSocket server."""
        self.running = True
        logger.info(f"Starting Squad Chat server on port {self.port}")

        async with serve(self._handle_connection, "localhost", self.port):
            logger.info(f"Squad Chat server listening on ws://localhost:{self.port}/squad")
            while self.running:
                await asyncio.sleep(1)

    def stop(self):
        """Stop the server."""
        self.running = False
        logger.info("Squad Chat server stopping")


# HTTP API for message history
async def handle_history(request):
    """REST endpoint for message history."""
    task_id = request.match_info.get('task_id', 'system')
    limit = int(request.query.get('limit', 100))

    messages = []
    try:
        if MESSAGE_LOG.exists():
            with open(MESSAGE_LOG, "r") as f:
                for line in f:
                    try:
                        msg = json.loads(line.strip())
                        if msg.get("channel") == task_id:
                            messages.append(msg)
                    except json.JSONDecodeError:
                        continue
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

    return web.json_response({
        "channel": task_id,
        "messages": messages[-limit:],
        "count": len(messages[-limit:])
    })


async def handle_status(request):
    """Health check endpoint."""
    return web.json_response({
        "status": "healthy",
        "server": "squad-chat",
        "timestamp": datetime.now().isoformat()
    })


async def handle_agents(request):
    """List connected agents."""
    # This would need to share state with the WebSocket server
    # For now, return a placeholder
    return web.json_response({
        "agents": [],
        "count": 0
    })


async def run_http_server():
    """Run the HTTP API server."""
    app = web.Application()
    app.router.add_get('/history/{task_id}', handle_history)
    app.router.add_get('/history', handle_history)  # system channel
    app.router.add_get('/status', handle_status)
    app.router.add_get('/agents', handle_agents)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, 'localhost', HTTP_PORT)
    await site.start()
    logger.info(f"HTTP API listening on http://localhost:{HTTP_PORT}")
    return runner


def main():
    parser = argparse.ArgumentParser(description="Squad Chat Server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="WebSocket port")
    parser.add_argument("--daemon", action="store_true", help="Run as daemon")
    args = parser.parse_args()

    server = SquadChatServer(port=args.port)

    # Signal handlers
    def shutdown(sig, frame):
        logger.info("Shutdown signal received")
        server.stop()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Run both WebSocket and HTTP servers
    async def run_all():
        http_runner = await run_http_server()
        try:
            await server.start()
        finally:
            await http_runner.cleanup()

    if args.daemon:
        # Daemon mode - detach from terminal
        import daemon
        with daemon.DaemonContext():
            asyncio.run(run_all())
    else:
        asyncio.run(run_all())


if __name__ == "__main__":
    main()
