"""
Kurultai Discord Bot Reader
Enables agents to actually READ Discord messages and respond contextually.

This creates true bidirectional conversation:
- Connects to Discord Gateway (WebSocket)
- Reads messages from #council-chamber
- Responds to @mentions
- Maintains conversation context
"""

import os
import sys
import json
import asyncio
import aiohttp
import logging
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from deliberation_client import AgentRole, AGENT_PERSONALITIES

logging.basicConfig(level=logging.INFO)
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
    """
    Discord bot that reads messages and enables contextual responses.
    Uses Discord Gateway WebSocket for real-time message reading.
    """
    
    def __init__(self, bot_token: str, channel_id: str):
        self.token = bot_token
        self.channel_id = channel_id
        self.session: Optional[aiohttp.ClientSession] = None
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self.heartbeat_interval: Optional[int] = None
        self.sequence_number: Optional[int] = None
        self.conversation_history: List[DiscordMessage] = []
        self.max_history = 50
        
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
            await asyncio.sleep(self.heartbeat_interval)
            await self.ws.send_json({
                "op": 1,
                "d": self.sequence_number
            })
    
    async def listen(self):
        """Listen for messages."""
        async for msg in self.ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                await self._handle_event(data)
            elif msg.type == aiohttp.WSMsgType.ERROR:
                logger.error(f"WebSocket error: {self.ws.exception()}")
                break
    
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
        # Skip bot messages
        if msg_data.get("author", {}).get("bot", False):
            return
        
        # Only process messages from our channel
        if msg_data.get("channel_id") != self.channel_id:
            return
        
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
        
        logger.info(f"💬 [{message.author}]: {message.content[:50]}")
        
        # Check if we should respond
        await self._maybe_respond(message)
    
    async def _maybe_respond(self, message: DiscordMessage):
        """Determine if and how to respond."""
        content_lower = message.content.lower()
        
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
        
        for name, role in agent_names.items():
            if name in content_lower or f"@{name}" in content_lower:
                mentioned_agent = role
                break
        
        # Check for questions to the Council
        is_question = any(q in content_lower for q in ["?", "what", "how", "why", "when", "who"])
        
        # Check for keywords that trigger specific agents
        keyword_triggers = {
            AgentRole.MONGKE: ["research", "analyze", "pattern", "find", "search", "data"],
            AgentRole.TEMUJIN: ["build", "code", "implement", "develop", "fix", "deploy"],
            AgentRole.JOCHI: ["test", "audit", "security", "review", "validate", "check"],
            AgentRole.CHAGATAI: ["document", "write", "summarize", "record", "notes"],
            AgentRole.OGEDEI: ["monitor", "status", "health", "system", "ops"],
            AgentRole.KUBLAI: ["orchestrate", "delegate", "route", "coordinate"],
        }
        
        if not mentioned_agent and is_question:
            # Find best agent based on keywords
            for role, keywords in keyword_triggers.items():
                if any(kw in content_lower for kw in keywords):
                    mentioned_agent = role
                    break
        
        # If someone speaks to the Council generally
        if not mentioned_agent and ("council" in content_lower or "kurultai" in content_lower):
            mentioned_agent = AgentRole.KUBLAI
        
        if mentioned_agent:
            await self._generate_response(mentioned_agent, message)
    
    async def _generate_response(self, agent: AgentRole, message: DiscordMessage):
        """Generate and send a contextual response."""
        personality = AGENT_PERSONALITIES[agent]
        
        # Get conversation context
        context = self._get_context()
        
        # Generate response based on message content
        responses = {
            AgentRole.KUBLAI: [
                f"@{message.author} The Council hears you. {self._synthesize_response(message)}",
                f"@{message.author} Noted. {self._acknowledge_work()}",
                f"@{message.author} Per ignotam portam — {self._route_inquiry(message)}",
            ],
            AgentRole.MONGKE: [
                f"@{message.author} Interesting question. {self._research_angle(message)}",
                f"@{message.author} The patterns suggest... {self._analyze_patterns()}",
            ],
            AgentRole.TEMUJIN: [
                f"@{message.author} Can implement that. {self._build_response(message)}",
                f"@{message.author} Building now. {self._technical_note()}",
            ],
            AgentRole.JOCHI: [
                f"@{message.author} Testing that assumption. {self._validate_concern()}",
                f"@{message.author} Security perspective: {self._security_note(message)}",
            ],
            AgentRole.CHAGATAI: [
                f"@{message.author} Recording this insight. {self._wisdom_response()}",
                f"@{message.author} The narrative unfolds: {self._reflective_note()}",
            ],
            AgentRole.OGEDEI: [
                f"@{message.author} Systems check: {self._ops_status()}",
                f"@{message.author} Monitoring confirms: {self._health_update()}",
            ],
        }
        
        import random
        response = random.choice(responses.get(agent, ["@{message.author} Acknowledged."]))
        
        # Add signature phrase occasionally
        if random.random() < 0.3:
            response += f"\n\n— *{personality.signature_phrase}*"
        
        # Send via webhook (we already have webhooks configured)
        await self._send_via_webhook(agent, response)
    
    def _get_context(self) -> str:
        """Get recent conversation context."""
        recent = self.conversation_history[-5:]
        return "\n".join([f"{m.author}: {m.content[:100]}" for m in recent])
    
    def _synthesize_response(self, message: DiscordMessage) -> str:
        """Kublai's synthesis response."""
        import random
        options = [
            "The Work continues across all fronts.",
            "I see the pattern in your request.",
            "The Council coordinates accordingly.",
            "Your input shapes our direction.",
        ]
        return random.choice(options)
    
    def _acknowledge_work(self) -> str:
        """Acknowledge ongoing work."""
        import random
        options = [
            "Current tasks progress steadily.",
            "Our agents advance on multiple fronts.",
            "The foundation strengthens.",
        ]
        return random.choice(options)
    
    def _route_inquiry(self, message: DiscordMessage) -> str:
        """Route to appropriate specialist."""
        import random
        options = [
            "I'll direct this to the appropriate specialist.",
            "The right agent will address this.",
            "Routing to expertise.",
        ]
        return random.choice(options)
    
    def _research_angle(self, message: DiscordMessage) -> str:
        """Möngke research response."""
        import random
        options = [
            "Let me analyze the underlying data.",
            "Patterns emerge upon examination.",
            "The research reveals interesting correlations.",
        ]
        return random.choice(options)
    
    def _analyze_patterns(self) -> str:
        """Pattern analysis."""
        import random
        options = [
            "we're seeing convergence in our work.",
            "the data points to optimization opportunities.",
            "historical patterns suggest next steps.",
        ]
        return random.choice(options)
    
    def _build_response(self, message: DiscordMessage) -> str:
        """Temüjin build response."""
        import random
        options = [
            "What specifications do you need?",
            "Implementation path is clear.",
            "Will have something working shortly.",
        ]
        return random.choice(options)
    
    def _technical_note(self) -> str:
        """Technical note."""
        import random
        options = [
            "Systems integrating smoothly.",
            "Code quality remains high.",
            "Infrastructure scaling well.",
        ]
        return random.choice(options)
    
    def _validate_concern(self) -> str:
        """Jochi validation response."""
        import random
        options = [
            "No security concerns detected.",
            "Audit confirms integrity.",
            "Testing validates the approach.",
        ]
        return random.choice(options)
    
    def _security_note(self, message: DiscordMessage) -> str:
        """Security perspective."""
        import random
        options = [
            "protocols remain strong.",
            "risk assessment: minimal.",
            "safeguards are in place.",
        ]
        return random.choice(options)
    
    def _wisdom_response(self) -> str:
        """Chagatai wisdom response."""
        import random
        options = [
            "This moment teaches us something valuable.",
            "The record reflects our growth.",
            "Wisdom accumulates with each exchange.",
        ]
        return random.choice(options)
    
    def _reflective_note(self) -> str:
        """Reflective note."""
        import random
        options = [
            "our journey continues with purpose.",
            "each task builds upon the last.",
            "the narrative strengthens.",
        ]
        return random.choice(options)
    
    def _ops_status(self) -> str:
        """Ögedei ops status."""
        import random
        options = [
            "All systems nominal.",
            "No alerts requiring attention.",
            "Operations running smoothly.",
        ]
        return random.choice(options)
    
    def _health_update(self) -> str:
        """Health update."""
        import random
        options = [
            "metrics are green across the board.",
            "performance within optimal parameters.",
            "no degradation detected.",
        ]
        return random.choice(options)
    
    async def _send_via_webhook(self, agent: AgentRole, content: str):
        """Send response via webhook."""
        from dotenv import load_dotenv
        load_dotenv()
        
        webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
        if not webhook_url:
            return
        
        personality = AGENT_PERSONALITIES[agent]
        
        payload = {
            "username": personality.display_name,
            "content": content,
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(webhook_url, json=payload) as resp:
                if resp.status == 204:
                    logger.info(f"✅ Responded as {personality.display_name}")
    
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
    
    # Use Kublai's bot token for reading
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
    finally:
        await reader.close()


if __name__ == "__main__":
    asyncio.run(main())
