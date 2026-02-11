#!/usr/bin/env python3
"""
Kurultai Deliberation Trigger
Manually trigger agent deliberations on specific topics.

Usage:
    # Simple deliberation
    python trigger_deliberation.py --topic "System architecture review"
    
    # Multi-agent deliberation
    python trigger_deliberation.py --topic "Security audit" --agents kublai,jochi,ogedei
    
    # Urgent deliberation with alert
    python trigger_deliberation.py --topic "Critical bug" --urgent
"""

import os
import sys
import asyncio
import argparse
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from deliberation_client import (
    KurultaiDiscordClient,
    AgentRole,
    AGENT_PERSONALITIES,
    create_discord_client,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kurultai-deliberation")


class DeliberationSession:
    """
    Manages a multi-agent deliberation session.
    
    A deliberation is a structured conversation where agents discuss
    a topic, share perspectives, and reach conclusions.
    """
    
    def __init__(
        self,
        topic: str,
        agents: Optional[List[AgentRole]] = None,
        channel: str = "council-chamber",
        urgent: bool = False
    ):
        self.topic = topic
        self.agents = agents or list(AgentRole)
        self.channel = channel
        self.urgent = urgent
        self.discord = create_discord_client()
        self.started_at = None
        self.messages: List[Dict[str, Any]] = []
    
    async def start(self):
        """Start the deliberation session."""
        self.started_at = datetime.utcnow()
        
        # Create the opening announcement
        await self._announce_session()
        
        # Have each agent contribute their perspective
        await self._gather_perspectives()
        
        # Kublai synthesizes
        await self._synthesize_conclusions()
        
        logger.info(f"Deliberation complete: {self.topic}")
    
    async def _announce_session(self):
        """Announce the start of deliberation."""
        urgency = "🚨 URGENT" if self.urgent else "📢"
        
        embed = {
            "title": f"{urgency} Deliberation Called",
            "description": self.topic,
            "color": 0xff0000 if self.urgent else 0x3498db,
            "timestamp": self.started_at.isoformat(),
            "fields": [
                {
                    "name": "Participating Agents",
                    "value": ", ".join([AGENT_PERSONALITIES[a].display_name for a in self.agents]),
                }
            ]
        }
        
        content = f"{urgency} **The Council is Convened**\n\n"
        content += f"Topic: *{self.topic}*\n\n"
        content += "Let the deliberation begin."
        
        await self.discord.send_message(
            self.channel,
            AgentRole.KUBLAI,
            content,
            embed=embed
        )
    
    async def _gather_perspectives(self):
        """Have each agent share their perspective."""
        perspectives = {
            AgentRole.MONGKE: self._mongke_perspective,
            AgentRole.CHAGATAI: self._chagatai_perspective,
            AgentRole.TEMUJIN: self._temujin_perspective,
            AgentRole.JOCHI: self._jochi_perspective,
            AgentRole.OGEDEI: self._ogedei_perspective,
        }
        
        for agent in self.agents:
            if agent == AgentRole.KUBLAI:
                continue  # Kublai speaks last
            
            if agent in perspectives:
                await perspectives[agent]()
                await asyncio.sleep(1)  # Brief pause between messages
    
    async def _mongke_perspective(self):
        """Möngke's research perspective."""
        content = (
            "🔬 **Research Perspective**\n\n"
            f"Examining '{self.topic}' from a research standpoint. "
            "What patterns emerge from the data? What precedents exist?\n\n"
            "I'll gather relevant information and precedents to inform our decision."
        )
        await self.discord.send_message(
            self.channel,
            AgentRole.MONGKE,
            content
        )
    
    async def _chagatai_perspective(self):
        """Chagatai's documentation perspective."""
        content = (
            "📝 **Documentation Perspective**\n\n"
            f"Regarding '{self.topic}' — let me capture the key considerations. "
            "What must we record for future reference?\n\n"
            "The wisdom we generate here should be preserved for the team."
        )
        await self.discord.send_message(
            self.channel,
            AgentRole.CHAGATAI,
            content
        )
    
    async def _temujin_perspective(self):
        """Temüjin's builder perspective."""
        content = (
            "🛠️ **Implementation Perspective**\n\n"
            f"For '{self.topic}', I'm considering the build approach. "
            "What's our technical path forward? What resources do we need?\n\n"
            "Ready to implement once we reach consensus."
        )
        await self.discord.send_message(
            self.channel,
            AgentRole.TEMUJIN,
            content
        )
    
    async def _jochi_perspective(self):
        """Jochi's security perspective."""
        content = (
            "🔍 **Analysis Perspective**\n\n"
            f"Analyzing '{self.topic}' for risks and validation requirements. "
            "What edge cases should we consider?\n\n"
            "Testing validates our approach — let's ensure we're thorough."
        )
        await self.discord.send_message(
            self.channel,
            AgentRole.JOCHI,
            content
        )
    
    async def _ogedei_perspective(self):
        """Ögedei's operations perspective."""
        content = (
            "📈 **Operations Perspective**\n\n"
            f"From an operations view, '{self.topic}' impacts our systems. "
            "Current status is stable. What's our resource allocation?\n\n"
            "Monitoring will track our progress on this initiative."
        )
        await self.discord.send_message(
            self.channel,
            AgentRole.OGEDEI,
            content
        )
    
    async def _synthesize_conclusions(self):
        """Kublai synthesizes the deliberation."""
        content = (
            "🏛️ **Synthesis**\n\n"
            f"The council has deliberated on '{self.topic}'.\n\n"
            "**Consensus reached:**\n"
            "• Research phase initiated (Möngke)\n"
            "• Documentation framework established (Chagatai)\n"
            "• Implementation path identified (Temüjin)\n"
            "• Risk assessment complete (Jochi)\n"
            "• Operations monitoring active (Ögedei)\n\n"
            "Per ignotam portam — through the unknown gate we proceed."
        )
        
        embed = {
            "title": "✅ Deliberation Complete",
            "description": f"Topic: {self.topic}",
            "color": 0x2ecc71,
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        await self.discord.send_message(
            self.channel,
            AgentRole.KUBLAI,
            content,
            embed=embed
        )


async def trigger_simple_deliberation(topic: str, urgent: bool = False):
    """Trigger a simple deliberation with all agents."""
    session = DeliberationSession(topic=topic, urgent=urgent)
    await session.start()


async def trigger_targeted_deliberation(
    topic: str,
    agent_names: List[str],
    urgent: bool = False
):
    """Trigger a deliberation with specific agents."""
    agents = []
    for name in agent_names:
        try:
            agents.append(AgentRole(name.lower().strip()))
        except ValueError:
            logger.warning(f"Unknown agent: {name}")
    
    # Always include Kublai for synthesis
    if AgentRole.KUBLAI not in agents:
        agents.insert(0, AgentRole.KUBLAI)
    
    session = DeliberationSession(
        topic=topic,
        agents=agents,
        urgent=urgent
    )
    await session.start()


async def trigger_celebration(task_name: str, agent_name: str):
    """Trigger a celebration for task completion."""
    discord = create_discord_client()
    
    try:
        agent = AgentRole(agent_name.lower())
    except ValueError:
        logger.error(f"Unknown agent: {agent_name}")
        return
    
    personality = AGENT_PERSONALITIES[agent]
    
    content = (
        f"🎉 **Celebration Time!** 🎉\n\n"
        f"**{personality.display_name}** has completed an important milestone:\n"
        f"*{task_name}*\n\n"
        f"The council recognizes this achievement!"
    )
    
    embed = {
        "title": "🏆 Task Completed",
        "description": task_name,
        "color": personality.color,
        "timestamp": datetime.utcnow().isoformat(),
    }
    
    await discord.send_message(
        "council-chamber",
        agent,
        content,
        embed=embed
    )
    
    # Add reactions from other agents
    for role in AgentRole:
        if role != agent:
            reaction = random.choice(AGENT_PERSONALITIES[role].emoji_reactions)
            await discord.react_to_message(
                "council-chamber",
                "last_message",  # Would need actual message ID
                role,
                reaction
            )


def main():
    """Main entry point."""
    import random  # Import here for celebration reactions
    
    parser = argparse.ArgumentParser(
        description="Trigger Kurultai Agent Deliberations"
    )
    parser.add_argument(
        "--topic", "-t",
        required=True,
        help="Topic for deliberation"
    )
    parser.add_argument(
        "--agents", "-a",
        help="Comma-separated list of agents (default: all)"
    )
    parser.add_argument(
        "--urgent", "-u",
        action="store_true",
        help="Mark as urgent (sends @everyone alert)"
    )
    parser.add_argument(
        "--celebrate", "-c",
        nargs=2,
        metavar=("AGENT", "TASK"),
        help="Celebrate task completion: --celebrate temujin 'Built feature'"
    )
    parser.add_argument(
        "--channel",
        default="council-chamber",
        help="Target channel (default: council-chamber)"
    )
    
    args = parser.parse_args()
    
    if args.celebrate:
        asyncio.run(trigger_celebration(args.celebrate[1], args.celebrate[0]))
    elif args.agents:
        agent_list = [a.strip() for a in args.agents.split(",")]
        asyncio.run(trigger_targeted_deliberation(
            args.topic,
            agent_list,
            args.urgent
        ))
    else:
        asyncio.run(trigger_simple_deliberation(args.topic, args.urgent))


if __name__ == "__main__":
    main()
