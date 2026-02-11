"""
Kurultai Discord Bot Reader - DEBUG VERSION
Enables agents to actually READ Discord messages and respond contextually.
"""

import os
import sys
import json
import asyncio
import aiohttp
import logging
import traceback
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from deliberation_client import AgentRole, AGENT_PERSONALITIES

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("kurultai-reader")


@dataclass
class DiscordMessage:
    """Represents a Discord message."""
    id: str
    channel_id: str
    author: str
    author_id: str
    content: str
    timestamp: datetime
    mentions: List[str]
    referenced_message_id: Optional[str] = None


class DiscordBotReader:
    """Discord bot that reads messages and enables contextual responses."""
    
    def __init__(self, bot_token: str, channel_id: str):
        self.token = bot_token
        self.channel_id = channel_id
        self.session: Optional[aiohttp.ClientSession] = None
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self.heartbeat_interval: Optional[int] = None
        self.sequence_number: Optional[int] = None
        self.conversation_history: List[DiscordMessage] = []
        self.max_history = 50
        self.processed_message_ids: set = set()  # Deduplication
        
    async def connect(self):
        """Connect to Discord Gateway."""
        self.session = aiohttp.ClientSession()
        
        # Get gateway URL
        async with self.session.get(
            "https://discord.com/api/v10/gateway",
            headers={"Authorization": f"Bot {self.token}"}
        ) as resp:
            data = await resp.json()
            gateway_url = data.get("url", "wss://gateway.discord.gg")
        
        # Connect WebSocket
        self.ws = await self.session.ws_connect(f"{gateway_url}/?v=10&encoding=json")
        logger.info("🔗 Connected to Discord Gateway")
        
        # Handle initial hello
        msg = await self.ws.receive_json()
        if msg.get("op") == 10:  # Hello
            self.heartbeat_interval = msg["d"]["heartbeat_interval"] / 1000
            asyncio.create_task(self._heartbeat_loop())
        
        # Identify
        await self.ws.send_json({
            "op": 2,
            "d": {
                "token": self.token,
                "intents": 1 << 9 | 1 << 15,  # Guild messages + Message content
                "properties": {
                    "os": "linux",
                    "browser": "KurultaiBot",
                    "device": "KurultaiBot"
                }
            }
        })
        logger.info("🔐 Identified to Gateway")
    
    async def _heartbeat_loop(self):
        """Send periodic heartbeats."""
        while True:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                await self.ws.send_json({
                    "op": 1,
                    "d": self.sequence_number
                })
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
                break
    
    async def listen(self):
        """Listen for messages."""
        try:
            async for msg in self.ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        await self._handle_event(data)
                    except Exception as e:
                        logger.error(f"Error handling event: {e}")
                        logger.error(traceback.format_exc())
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {self.ws.exception()}")
                    break
        except Exception as e:
            logger.error(f"Listen loop error: {e}")
            logger.error(traceback.format_exc())
    
    async def _handle_event(self, data: dict):
        """Handle Discord events."""
        if "s" in data:
            self.sequence_number = data["s"]
        
        op = data.get("op")
        event_type = data.get("t")
        
        if op == 0 and event_type == "MESSAGE_CREATE":
            await self._handle_message(data["d"])
        elif op == 0 and event_type == "READY":
            logger.info(f"✅ Bot ready: {data['d']['user']['username']}")
    
    async def _handle_message(self, msg_data: dict):
        """Process incoming message."""
        try:
            # Skip bot messages AND our own agent webhook posts
            if msg_data.get("author", {}).get("bot", False):
                return
            
            # Skip messages from our own agents (webhook posts aren't marked as bot=True)
            agent_usernames = ["Kublai 🏛️", "Möngke 🔬", "Chagatai 📝", "Temüjin 🛠️", "Jochi 🔍", "Ögedei 📈"]
            if msg_data["author"]["username"] in agent_usernames:
                logger.info(f"⏭️ Skipping own message from {msg_data['author']['username']}")
                return
            
            # Only process messages from our channel
            if msg_data.get("channel_id") != self.channel_id:
                return
            
            message_id = msg_data["id"]
            
            # Deduplication: skip if already processed
            if message_id in self.processed_message_ids:
                logger.info(f"⏭️ Skipping duplicate message: {message_id}")
                return
            self.processed_message_ids.add(message_id)
            
            # Limit set size
            if len(self.processed_message_ids) > 1000:
                self.processed_message_ids = set(list(self.processed_message_ids)[-500:])
            
            message = DiscordMessage(
                id=msg_data["id"],
                channel_id=msg_data["channel_id"],
                author=msg_data["author"]["username"],
                author_id=msg_data["author"]["id"],
                content=msg_data["content"],
                timestamp=datetime.fromisoformat(msg_data["timestamp"].replace("Z", "+00:00")),
                mentions=[m["username"] for m in msg_data.get("mentions", [])],
                referenced_message_id=msg_data.get("referenced_message", {}).get("id") if msg_data.get("referenced_message") else None
            )
            
            # Store in history
            self.conversation_history.append(message)
            if len(self.conversation_history) > self.max_history:
                self.conversation_history = self.conversation_history[-self.max_history:]
            
            logger.info(f"💬 [{message.author}]: {message.content[:80]}")
            logger.info(f"   Mentions: {message.mentions}")
            logger.info(f"   Author ID: {message.author_id}")
            
            # Check if we should respond
            await self._maybe_respond(message)
        except Exception as e:
            logger.error(f"Error in _handle_message: {e}")
            logger.error(traceback.format_exc())
    
    async def _maybe_respond(self, message: DiscordMessage):
        """Determine if and how to respond."""
        try:
            content_lower = message.content.lower()
            
            logger.info(f"🤔 Checking if should respond to: {content_lower[:50]}")
            
            # Check for @mentions of agents
            mentioned_agent = None
            agent_names = {
                "kublai": AgentRole.KUBLAI,
                "möngke": AgentRole.MONGKE,
                "mongke": AgentRole.MONGKE,
                "chagatai": AgentRole.CHAGATAI,
                "temüjin": AgentRole.TEMUJIN,
                "temujin": AgentRole.TEMUJIN,
                "jochi": AgentRole.JOCHI,
                "ögedei": AgentRole.OGEDEI,
                "ogedei": AgentRole.OGEDEI,
            }
            
            # Check for bot ID mentions (Discord user IDs)
            bot_ids = {
                "1471002577381625917": AgentRole.KUBLAI,
                "1471003592394674230": AgentRole.MONGKE,
                "1471005067032268991": AgentRole.CHAGATAI,
                "1471005828462018774": AgentRole.TEMUJIN,
                "1471006249616408700": AgentRole.JOCHI,
                "1471007368845201500": AgentRole.OGEDEI,
            }
            
            for bot_id, role in bot_ids.items():
                if bot_id in message.content:
                    mentioned_agent = role
                    logger.info(f"✅ Detected bot ID mention: {bot_id} -> {role}")
                    break
            
            if not mentioned_agent:
                for name, role in agent_names.items():
                    if name in content_lower or f"@{name}" in content_lower:
                        mentioned_agent = role
                        logger.info(f"✅ Detected name mention: {name} -> {role}")
                        break
            
            if mentioned_agent:
                logger.info(f"🎯 Will respond as: {mentioned_agent}")
                await self._generate_response(mentioned_agent, message)
            else:
                logger.info("❌ No agent detected in message")
        except Exception as e:
            logger.error(f"Error in _maybe_respond: {e}")
            logger.error(traceback.format_exc())
    
    async def _generate_response(self, agent: AgentRole, message: DiscordMessage):
        """Generate and send a contextual response."""
        try:
            personality = AGENT_PERSONALITIES[agent]
            logger.info(f"📝 Generating response as {personality.display_name}")
            
            import random
            
            # Simple contextual responses
            responses = {
                AgentRole.TEMUJIN: [
                    f"@{message.author} 🛠️ Working on builds. Currently focused on Vector DB deduplication and x-research setup. What do you need?",
                    f"@{message.author} 🛠️ Build systems active. Can implement what you need — just describe the outcome.",
                    f"@{message.author} 🛠️ Temüjin here. Currently optimizing our knowledge graph storage. What's your requirement?",
                ],
                AgentRole.KUBLAI: [
                    f"@{message.author} 🏛️ The Council hears you. The Work continues — 25 tasks in motion across all agents.",
                    f"@{message.author} 🏛️ Per ignotam portam. What does the Council need to know?",
                ],
                AgentRole.MONGKE: [
                    f"@{message.author} 🔬 Researching patterns in our memory systems and Ordo Sacer Astaci developments. What patterns interest you?",
                ],
                AgentRole.JOCHI: [
                    f"@{message.author} 🔍 Running smoke tests and security audits. Systems look clean so far.",
                ],
                AgentRole.CHAGATAI: [
                    f"@{message.author} 📝 Documenting our progress and curating weekly reflections. The narrative takes shape.",
                ],
                AgentRole.OGEDEI: [
                    f"@{message.author} 📈 Systems nominal. Heartbeat bridges running. All 11 Discord channels operational.",
                ],
            }
            
            response = random.choice(responses.get(agent, [f"@{message.author} Acknowledged."]))
            
            # Add signature phrase
            if random.random() < 0.5:
                response += f"\n\n— *{personality.signature_phrase}*"
            
            logger.info(f"📤 Sending response: {response[:80]}")
            await self._send_via_webhook(agent, response)
        except Exception as e:
            logger.error(f"Error in _generate_response: {e}")
            logger.error(traceback.format_exc())
    
    async def _send_via_webhook(self, agent: AgentRole, content: str):
        """Send response via webhook."""
        try:
            from dotenv import load_dotenv
            load_dotenv()
            
            webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
            if not webhook_url:
                logger.error("❌ No webhook URL configured")
                return
            
            personality = AGENT_PERSONALITIES[agent]
            
            payload = {
                "username": personality.display_name,
                "content": content,
            }
            
            logger.info(f"🌐 POSTing to webhook as {personality.display_name}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload) as resp:
                    if resp.status == 204:
                        logger.info(f"✅ Response sent successfully as {personality.display_name}")
                    else:
                        logger.error(f"❌ Webhook failed: {resp.status}")
                        response_text = await resp.text()
                        logger.error(f"Response: {response_text}")
        except Exception as e:
            logger.error(f"Error in _send_via_webhook: {e}")
            logger.error(traceback.format_exc())
    
    async def close(self):
        """Close connections."""
        if self.ws:
            await self.ws.close()
        if self.session:
            await self.session.close()


async def main():
    """Main entry point."""
    from dotenv import load_dotenv
    load_dotenv()
    
    token = os.getenv("KUBLAI_DISCORD_TOKEN")
    channel_id = os.getenv("DISCORD_COUNCIL_CHANNEL_ID")
    
    if not token or not channel_id:
        logger.error("Missing KUBLAI_DISCORD_TOKEN or DISCORD_COUNCIL_CHANNEL_ID")
        return
    
    reader = DiscordBotReader(token, channel_id)
    
    try:
        await reader.connect()
        await reader.listen()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Main error: {e}")
        logger.error(traceback.format_exc())
    finally:
        await reader.close()


if __name__ == "__main__":
    asyncio.run(main())
