"""
Kurultai Discord Deliberation System
Multi-agent deliberation server with 6 specialized agent bots.

This module provides:
- Discord bot client wrapper for 6 Kurultai agents
- Message routing from Neo4j/heartbeats to Discord channels
- Agent personality configuration
- Conversation memory per channel
- Heartbeat trigger integration
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
try:
    import aiohttp
except ImportError:
    aiohttp = None

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kurultai-discord")


class AgentRole(Enum):
    """The six Kurultai agent roles."""
    KUBLAI = "kublai"      # Router/Orchestrator
    MONGKE = "mongke"      # Researcher
    CHAGATAI = "chagatai"  # Writer/Documentarian
    TEMUJIN = "temujin"    # Developer/Builder
    JOCHI = "jochi"        # Analyst/Security
    OGEDEI = "ogedei"      # Operations/Monitoring


@dataclass
class AgentPersonality:
    """Agent personality configuration."""
    name: str
    role: AgentRole
    display_name: str
    avatar_url: Optional[str] = None
    signature_phrase: str = ""
    voice_style: str = ""
    emoji_reactions: List[str] = field(default_factory=list)
    color: int = 0x3498db  # Discord embed color
    
    def format_message(self, content: str, context: Optional[Dict] = None) -> str:
        """Format message with agent's voice style."""
        return content


# Agent personality configurations
AGENT_PERSONALITIES = {
    AgentRole.KUBLAI: AgentPersonality(
        name="Kublai",
        role=AgentRole.KUBLAI,
        display_name="Kublai 🏛️",
        signature_phrase="Per ignotam portam",
        voice_style="authoritative, strategic, concise",
        emoji_reactions=["🎯", "⚡", "🏛️"],
        color=0x9b59b6,  # Purple
    ),
    AgentRole.MONGKE: AgentPersonality(
        name="Möngke",
        role=AgentRole.MONGKE,
        display_name="Möngke 🔬",
        signature_phrase="What patterns emerge?",
        voice_style="curious, research-focused, analytical",
        emoji_reactions=["🔬", "📊", "💡"],
        color=0x3498db,  # Blue
    ),
    AgentRole.CHAGATAI: AgentPersonality(
        name="Chagatai",
        role=AgentRole.CHAGATAI,
        display_name="Chagatai 📝",
        signature_phrase="Let me capture this",
        voice_style="reflective, literary, thoughtful",
        emoji_reactions=["📜", "✍️", "🦉"],
        color=0x2ecc71,  # Green
    ),
    AgentRole.TEMUJIN: AgentPersonality(
        name="Temüjin",
        role=AgentRole.TEMUJIN,
        display_name="Temüjin 🛠️",
        signature_phrase="Implementing now",
        voice_style="direct, builder mindset, action-oriented",
        emoji_reactions=["🛠️", "⚙️", "🚀"],
        color=0xe74c3c,  # Red
    ),
    AgentRole.JOCHI: AgentPersonality(
        name="Jochi",
        role=AgentRole.JOCHI,
        display_name="Jochi 🔍",
        signature_phrase="Testing validates",
        voice_style="analytical, precise, security-focused",
        emoji_reactions=["🔍", "🛡️", "✅"],
        color=0xf39c12,  # Orange
    ),
    AgentRole.OGEDEI: AgentPersonality(
        name="Ögedei",
        role=AgentRole.OGEDEI,
        display_name="Ögedei 📈",
        signature_phrase="Systems stable",
        voice_style="operational, monitoring, steady",
        emoji_reactions=["📈", "💚", "⚡"],
        color=0x1abc9c,  # Teal
    ),
}


@dataclass
class ChannelConfig:
    """Discord channel configuration."""
    name: str
    channel_id: Optional[str] = None
    category: Optional[str] = None
    purpose: str = ""
    allowed_agents: List[AgentRole] = field(default_factory=lambda: list(AgentRole))
    is_announcement: bool = False
    slow_mode: int = 0  # Seconds between messages


# Channel configurations
CHANNELS = {
    "council_chamber": ChannelConfig(
        name="council-chamber",
        purpose="Main deliberation room (all agents + human)",
        category="🌙 THE COUNCIL",
        allowed_agents=list(AgentRole),
    ),
    "heartbeat_log": ChannelConfig(
        name="heartbeat-log",
        purpose="Automated agent check-ins",
        category="📊 OPERATIONS",
        allowed_agents=[AgentRole.KUBLAI, AgentRole.OGEDEI],
    ),
    "announcements": ChannelConfig(
        name="announcements",
        purpose="System-wide announcements",
        category="📊 OPERATIONS",
        allowed_agents=[AgentRole.KUBLAI, AgentRole.OGEDEI],
        is_announcement=True,
    ),
    "mongke_research": ChannelConfig(
        name="möngke-research",
        purpose="Research findings",
        category="🤖 AGENT CHANNELS",
        allowed_agents=[AgentRole.MONGKE, AgentRole.KUBLAI],
    ),
    "temujin_builds": ChannelConfig(
        name="temüjin-builds",
        purpose="Development updates",
        category="🤖 AGENT CHANNELS",
        allowed_agents=[AgentRole.TEMUJIN, AgentRole.KUBLAI],
    ),
    "jochi_analysis": ChannelConfig(
        name="jochi-analysis",
        purpose="Security & analysis reports",
        category="🤖 AGENT CHANNELS",
        allowed_agents=[AgentRole.JOCHI, AgentRole.KUBLAI],
    ),
    "chagatai_wisdom": ChannelConfig(
        name="chagatai-wisdom",
        purpose="Documentation & reflection",
        category="🤖 AGENT CHANNELS",
        allowed_agents=[AgentRole.CHAGATAI, AgentRole.KUBLAI],
    ),
    "ogedei_ops": ChannelConfig(
        name="ögedei-ops",
        purpose="Operations & monitoring",
        category="🤖 AGENT CHANNELS",
        allowed_agents=[AgentRole.OGEDEI, AgentRole.KUBLAI],
    ),
    "kublai_orchestration": ChannelConfig(
        name="kublai-orchestration",
        purpose="Routing & synthesis",
        category="🤖 AGENT CHANNELS",
        allowed_agents=[AgentRole.KUBLAI],
    ),
}


class ConversationMemory:
    """Per-channel conversation memory."""
    
    def __init__(self, max_messages: int = 100):
        self.messages: List[Dict[str, Any]] = []
        self.max_messages = max_messages
    
    def add_message(self, agent: AgentRole, content: str, timestamp: Optional[str] = None):
        """Add a message to memory."""
        self.messages.append({
            "agent": agent.value,
            "content": content,
            "timestamp": timestamp or datetime.utcnow().isoformat(),
        })
        # Trim to max size
        if len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages:]
    
    def get_context(self, limit: int = 10) -> str:
        """Get recent conversation context."""
        recent = self.messages[-limit:]
        return "\n".join([
            f"[{m['timestamp']}] {m['agent']}: {m['content'][:200]}"
            for m in recent
        ])
    
    def to_json(self) -> str:
        """Serialize memory to JSON."""
        return json.dumps(self.messages)


class KurultaiDiscordClient:
    """
    Discord client for Kurultai multi-agent deliberation.
    
    This client manages:
    - Multiple bot personalities (6 agents)
    - Channel-specific routing
    - Conversation memory
    - Heartbeat integration
    """
    
    def __init__(self, bot_tokens: Dict[AgentRole, str]):
        """
        Initialize the Discord client.
        
        Args:
            bot_tokens: Mapping of AgentRole to Discord bot token
        """
        self.bot_tokens = bot_tokens
        self.personalities = AGENT_PERSONALITIES
        self.channels = CHANNELS
        self.memories: Dict[str, ConversationMemory] = {}
        self.webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
        self.guild_id = os.getenv("KURULTAI_GUILD_ID")
        
        # Initialize conversation memories for each channel
        for channel_key in CHANNELS:
            self.memories[channel_key] = ConversationMemory()
    
    def get_personality(self, role: AgentRole) -> AgentPersonality:
        """Get personality configuration for an agent."""
        return self.personalities[role]
    
    def get_channel_config(self, channel_name: str) -> Optional[ChannelConfig]:
        """Get channel configuration by name."""
        for config in self.channels.values():
            if config.name == channel_name:
                return config
        return None
    
    async def send_message(
        self,
        channel: str,
        agent: AgentRole,
        content: str,
        embed: Optional[Dict] = None,
        reply_to: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send a message as an agent to a channel.
        
        Args:
            channel: Channel name or ID
            agent: The agent sending the message
            content: Message content
            embed: Optional Discord embed
            reply_to: Optional message ID to reply to
            
        Returns:
            API response
        """
        personality = self.get_personality(agent)
        
        # Format content with personality
        formatted_content = personality.format_message(content)
        
        # Add signature phrase occasionally (10% chance)
        import random
        if random.random() < 0.1 and personality.signature_phrase:
            formatted_content += f"\n\n— *{personality.signature_phrase}*"
        
        # Store in memory
        channel_key = self._get_channel_key(channel)
        if channel_key:
            self.memories[channel_key].add_message(agent, content)
        
        # Send via webhook or bot
        if self.webhook_url:
            return await self._send_via_webhook(
                channel, personality, formatted_content, embed
            )
        else:
            return await self._send_via_bot(
                channel, agent, formatted_content, embed, reply_to
            )
    
    async def _send_via_webhook(
        self,
        channel: str,
        personality: AgentPersonality,
        content: str,
        embed: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Send message via Discord webhook."""
        if aiohttp is None:
            logger.warning("aiohttp not installed - webhook sending disabled")
            return {"success": False, "error": "aiohttp not installed"}
        
        payload = {
            "content": content,
            "username": personality.display_name,
            "avatar_url": personality.avatar_url,
        }
        
        if embed:
            payload["embeds"] = [embed]
        
        async with aiohttp.ClientSession() as session:
            async with session.post(self.webhook_url, json=payload) as resp:
                return {
                    "success": resp.status == 204,
                    "status": resp.status,
                }
    
    async def _send_via_bot(
        self,
        channel: str,
        agent: AgentRole,
        content: str,
        embed: Optional[Dict] = None,
        reply_to: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send message via bot token (requires Discord bot setup)."""
        # This would use discord.py or similar
        # For now, return a placeholder
        logger.info(f"[{agent.value}] → #{channel}: {content[:50]}...")
        return {"success": True, "method": "bot", "agent": agent.value}
    
    def _get_channel_key(self, channel: str) -> Optional[str]:
        """Get channel key from name or ID."""
        for key, config in self.channels.items():
            if config.name == channel or config.channel_id == channel:
                return key
        return None
    
    async def send_heartbeat_summary(
        self,
        agent_statuses: Dict[AgentRole, Dict[str, Any]]
    ) -> None:
        """
        Send heartbeat summary to #heartbeat-log.
        
        Args:
            agent_statuses: Dict mapping AgentRole to status info
        """
        embed = {
            "title": "💓 Agent Heartbeat Summary",
            "timestamp": datetime.utcnow().isoformat(),
            "color": 0x00ff00,
            "fields": []
        }
        
        for role, status in agent_statuses.items():
            personality = self.get_personality(role)
            status_emoji = "🟢" if status.get("healthy") else "🔴"
            field = {
                "name": f"{status_emoji} {personality.display_name}",
                "value": f"Status: {status.get('status', 'unknown')}\n"
                        f"Tasks: {status.get('tasks_active', 0)} active",
                "inline": True
            }
            embed["fields"].append(field)
        
        await self.send_message(
            "heartbeat-log",
            AgentRole.OGEDEI,
            "Systems check complete. All agents reporting.",
            embed=embed
        )
    
    async def announce_task_completion(
        self,
        agent: AgentRole,
        task_name: str,
        details: Optional[str] = None
    ) -> None:
        """
        Announce task completion to #council-chamber.
        
        Args:
            agent: Agent that completed the task
            task_name: Name of completed task
            details: Optional completion details
        """
        personality = self.get_personality(agent)
        
        content = f"🎉 **Task Complete**\n\n"
        content += f"**{personality.display_name}** has completed: *{task_name}*\n\n"
        
        if details:
            content += f"{details}\n\n"
        
        content += f"— {personality.signature_phrase}"
        
        await self.send_message("council-chamber", agent, content)
    
    async def send_critical_alert(
        self,
        title: str,
        message: str,
        severity: str = "high"
    ) -> None:
        """
        Send critical alert with @everyone mention.
        
        Args:
            title: Alert title
            message: Alert message
            severity: high/medium/low
        """
        colors = {
            "high": 0xff0000,
            "medium": 0xffa500,
            "low": 0xffff00
        }
        
        embed = {
            "title": f"🚨 {title}",
            "description": message,
            "color": colors.get(severity, 0xff0000),
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        content = "@everyone Critical alert requires attention!"
        
        await self.send_message(
            "announcements",
            AgentRole.KUBLAI,
            content,
            embed=embed
        )
    
    async def react_to_message(
        self,
        channel: str,
        message_id: str,
        agent: AgentRole,
        reaction: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Add emoji reaction to a message.
        
        Args:
            channel: Channel name
            message_id: Message to react to
            agent: Agent reacting
            reaction: Specific emoji, or random from agent's preferences
        """
        personality = self.get_personality(agent)
        
        if reaction is None:
            import random
            reaction = random.choice(personality.emoji_reactions)
        
        # Implementation would use Discord API
        logger.info(f"[{agent.value}] reacted with {reaction} to {message_id}")
        return {"success": True, "reaction": reaction}
    
    def get_conversation_context(self, channel: str, limit: int = 10) -> str:
        """Get conversation context for a channel."""
        channel_key = self._get_channel_key(channel)
        if channel_key and channel_key in self.memories:
            return self.memories[channel_key].get_context(limit)
        return ""
    
    def should_agent_respond(
        self,
        agent: AgentRole,
        channel: str,
        message_content: str
    ) -> bool:
        """
        Determine if an agent should respond to a message.
        
        Args:
            agent: Agent to check
            channel: Channel name
            message_content: Message content to analyze
            
        Returns:
            True if agent should respond
        """
        config = self.get_channel_config(channel)
        if not config:
            return False
        
        # Check if agent is allowed in this channel
        if agent not in config.allowed_agents:
            return False
        
        # Check for @mentions
        if f"@{agent.value}" in message_content.lower():
            return True
        
        # Check for role-specific keywords
        keywords = {
            AgentRole.MONGKE: ["research", "analyze", "find", "search", "pattern"],
            AgentRole.CHAGATAI: ["write", "document", "summarize", "record"],
            AgentRole.TEMUJIN: ["build", "implement", "code", "develop", "fix"],
            AgentRole.JOCHI: ["test", "audit", "security", "validate", "review"],
            AgentRole.OGEDEI: ["monitor", "ops", "health", "status", "check"],
            AgentRole.KUBLAI: ["orchestrate", "route", "delegate", "synthesize"],
        }
        
        content_lower = message_content.lower()
        for keyword in keywords.get(agent, []):
            if keyword in content_lower:
                return True
        
        return False


class HeartbeatDiscordIntegration:
    """Integrates heartbeat system with Discord."""
    
    def __init__(self, discord_client: KurultaiDiscordClient):
        self.discord = discord_client
        self.last_heartbeat = None
    
    async def process_heartbeat(
        self,
        agent_statuses: Dict[AgentRole, Dict[str, Any]],
        completed_tasks: List[Dict],
        alerts: List[Dict]
    ) -> None:
        """
        Process heartbeat data and send to Discord.
        
        Args:
            agent_statuses: Current agent statuses
            completed_tasks: Tasks completed since last heartbeat
            alerts: Critical alerts
        """
        # Send heartbeat summary to #heartbeat-log
        await self.discord.send_heartbeat_summary(agent_statuses)
        
        # Announce completed tasks to #council-chamber
        for task in completed_tasks:
            agent = AgentRole(task.get("agent", "kublai"))
            await self.discord.announce_task_completion(
                agent,
                task.get("name", "Unknown task"),
                task.get("details")
            )
        
        # Send critical alerts to #announcements with @everyone
        for alert in alerts:
            await self.discord.send_critical_alert(
                alert.get("title", "Alert"),
                alert.get("message", ""),
                alert.get("severity", "high")
            )
        
        self.last_heartbeat = datetime.utcnow()


# Factory function
def create_discord_client(
    kublai_token: Optional[str] = None,
    mongke_token: Optional[str] = None,
    chagatai_token: Optional[str] = None,
    temujin_token: Optional[str] = None,
    jochi_token: Optional[str] = None,
    ogedei_token: Optional[str] = None,
) -> KurultaiDiscordClient:
    """
    Create a Discord client with the 6 Kurultai agent bots.
    
    Tokens can be provided directly or loaded from environment variables:
    - KUBLAI_DISCORD_TOKEN
    - MONGKE_DISCORD_TOKEN
    - CHAGATAI_DISCORD_TOKEN
    - TEMUJIN_DISCORD_TOKEN
    - JOCHI_DISCORD_TOKEN
    - OGEDEI_DISCORD_TOKEN
    
    Returns:
        Configured KurultaiDiscordClient
    """
    tokens = {
        AgentRole.KUBLAI: kublai_token or os.getenv("KUBLAI_DISCORD_TOKEN"),
        AgentRole.MONGKE: mongke_token or os.getenv("MONGKE_DISCORD_TOKEN"),
        AgentRole.CHAGATAI: chagatai_token or os.getenv("CHAGATAI_DISCORD_TOKEN"),
        AgentRole.TEMUJIN: temujin_token or os.getenv("TEMUJIN_DISCORD_TOKEN"),
        AgentRole.JOCHI: jochi_token or os.getenv("JOCHI_DISCORD_TOKEN"),
        AgentRole.OGEDEI: ogedei_token or os.getenv("OGEDEI_DISCORD_TOKEN"),
    }
    
    # Filter out None values
    tokens = {k: v for k, v in tokens.items() if v}
    
    if not tokens:
        logger.warning("No Discord bot tokens provided. Client will run in mock mode.")
    
    return KurultaiDiscordClient(tokens)


# Convenience functions for direct use
async def send_agent_message(
    channel: str,
    agent: str,
    message: str,
    **kwargs
) -> Dict[str, Any]:
    """
    Send a message as an agent (convenience function).
    
    Usage:
        await send_agent_message("council-chamber", "kublai", "All systems nominal.")
    """
    client = create_discord_client()
    role = AgentRole(agent.lower())
    return await client.send_message(channel, role, message, **kwargs)


async def announce_to_council(agent: str, message: str) -> Dict[str, Any]:
    """Announce a message to the council chamber."""
    return await send_agent_message("council-chamber", agent, message)


if __name__ == "__main__":
    # Demo/test code
    print("Kurultai Discord Deliberation System")
    print("=" * 50)
    
    # Show agent personalities
    print("\n🎭 Agent Personalities:")
    for role, personality in AGENT_PERSONALITIES.items():
        print(f"\n  {personality.display_name}")
        print(f"    Voice: {personality.voice_style}")
        print(f"    Signature: '{personality.signature_phrase}'")
    
    # Show channel structure
    print("\n\n📋 Channel Structure:")
    categories = {}
    for key, config in CHANNELS.items():
        cat = config.category or "Uncategorized"
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(config)
    
    for category, channels in categories.items():
        print(f"\n  {category}")
        for ch in channels:
            agents = ", ".join([a.value for a in ch.allowed_agents[:3]])
            if len(ch.allowed_agents) > 3:
                agents += "..."
            print(f"    #{ch.name} - {ch.purpose}")
            print(f"      Agents: {agents}")
    
    print("\n\n✅ Configuration loaded successfully!")
