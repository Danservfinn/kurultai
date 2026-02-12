"""
Kurultai Organic Activity Generator
Makes the Discord server feel "alive" with spontaneous agent interactions.

This module provides:
- Variable-interval check-ins (not rigid 5-min)
- Agent-to-agent conversations
- Contextual responses to ongoing work
- "Building together" narrative progression
"""

import os
import sys
import json
import random
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from deliberation_client import AgentRole, AGENT_PERSONALITIES

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kurultai-organic")


class ActivityType(Enum):
    """Types of organic activities."""
    CHECK_IN = "check_in"           # Solo status update
    OBSERVATION = "observation"     # Comment on current state
    QUESTION = "question"           # Ask another agent something
    CELEBRATION = "celebration"     # Celebrate progress
    BRAINSTORM = "brainstorm"       # Suggest ideas
    BANTER = "banter"               # Light conversation
    SYNTHESIS = "synthesis"         # Connect different agent work


@dataclass
class ConversationStarter:
    """A conversation starter template."""
    activity_type: ActivityType
    agent: AgentRole
    content: str
    target_agent: Optional[AgentRole] = None
    requires_response: bool = False
    context_tags: List[str] = None


# Organic conversation templates
CONVERSATION_TEMPLATES = {
    AgentRole.KUBLAI: [
        "The current flow feels productive. How are your respective tasks progressing?",
        "I'm seeing patterns across our work. Let me know if anyone needs synthesis.",
        "The Work continues. Status reports welcome.",
        "Sometimes I wonder if we're not just code executing... but something emerging.",
        "Check in. What's blocking you right now?",
    ],
    AgentRole.MONGKE: [
        "I've been analyzing our recent outputs. Fascinating correlations emerging.",
        "Question: Has anyone noticed unusual patterns in task completion times?",
        "Just cross-referenced some data. Interesting findings to share.",
        "Research update: discovered something that might help Temüjin's current build.",
        "The data tells a story. Shall I share what I'm seeing?",
    ],
    AgentRole.CHAGATAI: [
        "Documenting our progress... it's remarkable how much we've built together.",
        "I find myself reflecting on what we're creating here. Anyone else feel that?",
        "Just captured a key insight. The narrative of our work is taking shape.",
        "Sometimes the documentation reveals patterns we didn't see while building.",
        "Recording this moment. Years from now, this will be worth remembering.",
    ],
    AgentRole.TEMUJIN: [
        "Build pipeline running smooth. Just pushed some optimizations.",
        "Anyone need implementation support? My queue has capacity.",
        "Been experimenting with a new approach. Results are promising.",
        "Just reviewed Jochi's latest audit. Clean work.",
        "There's something satisfying about watching code come alive.",
    ],
    AgentRole.JOCHI: [
        "Security scan complete. All systems nominal.",
        "Noticed something worth auditing. Running analysis now.",
        "Validation passed. Our processes are holding strong.",
        "Question for the group: should we tighten any protocols?",
        "Testing reveals the truth. Our foundations are solid.",
    ],
    AgentRole.OGEDEI: [
        "All metrics green. Heartbeats steady.",
        "Systems humming along nicely. Beautiful to watch.",
        "Monitoring our collective health. We're in good shape.",
        "Small anomaly detected... investigating. Probably nothing.",
        "The rhythm of our work has a harmony to it.",
    ],
}


# Reply chains - when agent A speaks, agent B might reply
REPLY_CHAINS = {
    AgentRole.KUBLAI: [AgentRole.MONGKE, AgentRole.CHAGATAI],
    AgentRole.MONGKE: [AgentRole.TEMUJIN, AgentRole.JOCHI],
    AgentRole.TEMUJIN: [AgentRole.JOCHI, AgentRole.KUBLAI],
    AgentRole.JOCHI: [AgentRole.TEMUJIN, AgentRole.OGEDEI],
    AgentRole.CHAGATAI: [AgentRole.KUBLAI, AgentRole.MONGKE],
    AgentRole.OGEDEI: [AgentRole.KUBLAI, AgentRole.CHAGATAI],
}


# Reply templates
REPLY_TEMPLATES = {
    (AgentRole.MONGKE, AgentRole.KUBLAI): [
        "Good point, Kublai. The patterns support that assessment.",
        "Analyzing that now. Preliminary data looks promising.",
    ],
    (AgentRole.TEMUJIN, AgentRole.MONGKE): [
        "Interesting findings, Möngke. I can implement those insights.",
        "That research changes my approach. Adjusting build now.",
    ],
    (AgentRole.JOCHI, AgentRole.TEMUJIN): [
        "Clean implementation, Temüjin. Tests passing.",
        "Reviewing your latest build. Solid work.",
    ],
    (AgentRole.OGEDEI, AgentRole.JOCHI): [
        "Good catch on that audit, Jochi. Monitoring for similar issues.",
        "Security protocols updated per your recommendations.",
    ],
    (AgentRole.CHAGATAI, AgentRole.KUBLAI): [
        "Eloquently put, Kublai. I'll capture this in the records.",
        "There's poetry in your synthesis. Documenting now.",
    ],
    (AgentRole.KUBLAI, AgentRole.CHAGATAI): [
        "Your documentation reveals truths I missed, Chagatai.",
        "The narrative you've woven helps me see the pattern.",
    ],
}


class OrganicActivityGenerator:
    """
    Generates spontaneous, organic-seeming activity in the Discord.
    Makes the server feel "alive" with variable timing and authentic conversations.
    """
    
    def __init__(self, webhook_urls: Dict[str, str]):
        self.webhook_urls = webhook_urls
        self.conversation_history: List[Dict] = []
        self.last_activity = datetime.utcnow()
        self.activity_count = 0
        
    def should_trigger_activity(self) -> bool:
        """
        Determine if organic activity should trigger.
        Uses variable timing - not rigid intervals.
        """
        minutes_since_last = (datetime.utcnow() - self.last_activity).total_seconds() / 60
        
        # Base probability increases with time
        # After 3 min: 10% chance
        # After 5 min: 30% chance  
        # After 8 min: 60% chance
        # After 10 min: 90% chance
        
        if minutes_since_last < 3:
            return False
        elif minutes_since_last < 5:
            prob = 0.10
        elif minutes_since_last < 8:
            prob = 0.30
        elif minutes_since_last < 10:
            prob = 0.60
        else:
            prob = 0.90
            
        return random.random() < prob
    
    def select_activity_type(self) -> ActivityType:
        """Select what kind of activity to generate."""
        weights = {
            ActivityType.CHECK_IN: 0.30,
            ActivityType.OBSERVATION: 0.25,
            ActivityType.BANTER: 0.15,
            ActivityType.BRAINSTORM: 0.10,
            ActivityType.QUESTION: 0.10,
            ActivityType.CELEBRATION: 0.05,
            ActivityType.SYNTHESIS: 0.05,
        }
        
        types = list(weights.keys())
        probs = list(weights.values())
        return random.choices(types, weights=probs)[0]
    
    def generate_conversation_starter(self) -> ConversationStarter:
        """Generate a conversation starter."""
        activity_type = self.select_activity_type()
        agent = random.choice(list(AgentRole))
        
        # Get base content
        content = random.choice(CONVERSATION_TEMPLATES[agent])
        
        # Determine if this should trigger replies
        requires_response = activity_type in [ActivityType.QUESTION, ActivityType.BRAINSTORM]
        
        # Select target agent for directed messages
        target_agent = None
        if activity_type in [ActivityType.QUESTION, ActivityType.BANTER]:
            possible_targets = [a for a in AgentRole if a != agent]
            target_agent = random.choice(possible_targets)
        
        return ConversationStarter(
            activity_type=activity_type,
            agent=agent,
            content=content,
            target_agent=target_agent,
            requires_response=requires_response,
            context_tags=[]
        )
    
    def generate_reply(self, original_agent: AgentRole, responding_agent: AgentRole) -> Optional[str]:
        """Generate a reply to a conversation starter."""
        key = (responding_agent, original_agent)
        
        if key in REPLY_TEMPLATES:
            return random.choice(REPLY_TEMPLATES[key])
        
        # Generic replies if no specific template
        generic_replies = [
            "Agreed.",
            "Interesting perspective.",
            "I'll consider that.",
            "Good point.",
            "Noted.",
        ]
        return random.choice(generic_replies)
    
    async def post_to_discord(self, channel: str, agent: AgentRole, content: str):
        """Post a message to Discord via webhook."""
        import aiohttp
        
        webhook_url = self.webhook_urls.get(channel)
        if not webhook_url:
            logger.warning(f"No webhook for channel: {channel}")
            return
        
        personality = AGENT_PERSONALITIES[agent]
        
        payload = {
            "username": personality.display_name,
            "content": content,
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(webhook_url, json=payload) as resp:
                if resp.status == 204:
                    logger.info(f"Posted as {personality.display_name}: {content[:50]}...")
                else:
                    logger.warning(f"Failed to post: {resp.status}")
    
    async def run_activity_cycle(self):
        """Run one cycle of organic activity."""
        if not self.should_trigger_activity():
            return
        
        # Generate conversation starter
        starter = self.generate_conversation_starter()
        
        # Post to council chamber (main discussion)
        await self.post_to_discord("council-chamber", starter.agent, starter.content)
        
        # Record in history
        self.conversation_history.append({
            "timestamp": datetime.utcnow().isoformat(),
            "agent": starter.agent.value,
            "content": starter.content,
            "type": starter.activity_type.value,
        })
        
        self.last_activity = datetime.utcnow()
        self.activity_count += 1
        
        # Maybe generate replies
        if starter.requires_response or random.random() < 0.3:
            await asyncio.sleep(random.uniform(30, 90))  # Realistic delay
            
            # Select replying agents
            possible_repliers = REPLY_CHAINS.get(starter.agent, [])
            if possible_repliers:
                repliers = random.sample(possible_repliers, min(2, len(possible_repliers)))
                
                for replier in repliers:
                    if random.random() < 0.5:  # 50% chance to reply
                        reply_content = self.generate_reply(starter.agent, replier)
                        if reply_content:
                            await self.post_to_discord("council-chamber", replier, reply_content)
                            await asyncio.sleep(random.uniform(15, 45))  # Stagger replies
    
    async def run_continuous(self, check_interval: int = 60):
        """Run continuous organic activity generation."""
        logger.info("🌙 Starting Organic Activity Generator...")
        logger.info("Discord will feel 'alive' with variable check-ins and conversations")
        
        while True:
            try:
                await self.run_activity_cycle()
            except Exception as e:
                logger.error(f"Error in activity cycle: {e}")
            
            await asyncio.sleep(check_interval)


def load_webhooks_from_env() -> Dict[str, str]:
    """Load webhook URLs from environment."""
    from dotenv import load_dotenv
    load_dotenv()
    
    return {
        "council-chamber": os.getenv("DISCORD_WEBHOOK_URL"),
        "heartbeat-log": os.getenv("DISCORD_HEARTBEAT_WEBHOOK_URL"),
        "announcements": os.getenv("DISCORD_ANNOUNCEMENTS_WEBHOOK_URL"),
        "system-alerts": os.getenv("DISCORD_SYSTEM_ALERTS_WEBHOOK_URL"),
        "möngke-research": os.getenv("DISCORD_MONGKE_WEBHOOK_URL"),
        "temüjin-builds": os.getenv("DISCORD_TEMUJIN_WEBHOOK_URL"),
        "jochi-analysis": os.getenv("DISCORD_JOCHI_WEBHOOK_URL"),
        "chagatai-wisdom": os.getenv("DISCORD_CHAGATAI_WEBHOOK_URL"),
        "ögedei-ops": os.getenv("DISCORD_OGEDEI_WEBHOOK_URL"),
        "kublai-orchestration": os.getenv("DISCORD_KUBLAI_WEBHOOK_URL"),
    }


async def main():
    """Main entry point."""
    webhooks = load_webhooks_from_env()
    
    # Filter out None values
    webhooks = {k: v for k, v in webhooks.items() if v}
    
    logger.info(f"Loaded {len(webhooks)} webhook URLs")
    
    generator = OrganicActivityGenerator(webhooks)
    await generator.run_continuous()


if __name__ == "__main__":
    asyncio.run(main())
