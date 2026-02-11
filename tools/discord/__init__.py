"""
Kurultai Discord Deliberation System

A multi-agent deliberation system for Discord with 6 specialized AI agents:
- Kublai: Router/Orchestrator
- Möngke: Researcher
- Chagatai: Writer/Documentarian
- Temüjin: Developer/Builder
- Jochi: Analyst/Security
- Ögedei: Operations/Monitoring

Quick Start:
    1. Run bot_setup.py to generate configuration
    2. Follow SETUP.md to create Discord bots
    3. Add tokens to .env file
    4. Run test_bots.py to verify
    5. Start heartbeat_bridge.py for continuous operation

Modules:
    deliberation_client: Core Discord client and agent personalities
    bot_setup: Configuration generator and setup instructions
    heartbeat_bridge: Neo4j heartbeat to Discord integration
    trigger_deliberation: Manual deliberation triggering
    test_bots: Testing and validation

Example:
    >>> from tools.discord import create_discord_client, AgentRole
    >>> client = create_discord_client()
    >>> await client.send_message("council-chamber", AgentRole.KUBLAI, "Hello Council!")
"""

from .deliberation_client import (
    AgentRole,
    AgentPersonality,
    AGENT_PERSONALITIES,
    ChannelConfig,
    CHANNELS,
    ConversationMemory,
    KurultaiDiscordClient,
    HeartbeatDiscordIntegration,
    create_discord_client,
    send_agent_message,
    announce_to_council,
)

__all__ = [
    "AgentRole",
    "AgentPersonality",
    "AGENT_PERSONALITIES",
    "ChannelConfig",
    "CHANNELS",
    "ConversationMemory",
    "KurultaiDiscordClient",
    "HeartbeatDiscordIntegration",
    "create_discord_client",
    "send_agent_message",
    "announce_to_council",
]

__version__ = "1.0.0"
__author__ = "Kurultai Council"
