#!/usr/bin/env python3
"""
Kurultai Discord Bot - LLM-Powered Agent Responses

Upgraded version: Agents respond with actual LLM-generated content
based on their real task status from Neo4j.

Replaces template-based bot_natural.py
"""

import os
import sys
import json
import asyncio
import aiohttp
import logging
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '/data/workspace/souls/main')

from deliberation_client import AgentRole, AGENT_PERSONALITIES
# Note: conversation_value_scorer moved to archived - not needed for LLM bot
# from conversation_value_scorer import get_scorer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kurultai-llm")


@dataclass
class DiscordMessage:
    id: str
    channel_id: str
    author: str
    author_id: str
    content: str
    timestamp: datetime
    mentions: List[str]


class LLMConversationBot:
    """Discord bot with LLM-powered agent responses."""
    
    AGENT_USERNAMES = {
        "Kublai 🏛️": AgentRole.KUBLAI,
        "Möngke 🔬": AgentRole.MONGKE,
        "Chagatai 📝": AgentRole.CHAGATAI,
        "Temüjin 🛠️": AgentRole.TEMUJIN,
        "Jochi 🔍": AgentRole.JOCHI,
        "Ögedei 📈": AgentRole.OGEDEI,
    }
    
    def __init__(self, webhook_url: str, neo4j_driver=None):
        self.webhook_url = webhook_url
        self.neo4j_driver = neo4j_driver
        self.session: Optional[aiohttp.ClientSession] = None
        self.message_history: deque = deque(maxlen=50)
        # Value scorer removed - LLM bot doesn't need it
        # self.value_scorer = get_scorer()
        self.last_response_time: Dict[str, datetime] = {}
        self.min_response_interval = timedelta(seconds=30)
        self.processed_ids: Set[str] = set()  # Track processed message IDs
    
    async def start(self):
        """Start the bot."""
        self.session = aiohttp.ClientSession()
        logger.info("🤖 LLM Discord bot started")
    
    async def stop(self):
        """Stop the bot."""
        if self.session:
            await self.session.close()
    
    def get_agent_context(self, agent_name: str) -> Dict:
        """Fetch agent's current status from Neo4j."""
        if not self.neo4j_driver:
            return {"error": "No Neo4j connection"}
        
        try:
            with self.neo4j_driver.session() as session:
                # Get agent's current task
                result = session.run("""
                    MATCH (a:Agent {name: $name})
                    OPTIONAL MATCH (a)-[:ASSIGNED_TO]->(t:Task)
                    WHERE t.status IN ['in_progress', 'pending']
                    RETURN a.name as name,
                           a.status as agent_status,
                           a.role as role,
                           t.id as task_id,
                           t.description as task_desc,
                           t.status as task_status,
                           t.results as task_results
                    LIMIT 1
                """, name=agent_name.replace(" 🏛️", "").replace(" 🔬", "").replace(" 📝", "")
                                    .replace(" 🛠️", "").replace(" 🔍", "").replace(" 📈", ""))
                
                record = result.single()
                if record:
                    return {
                        "name": record["name"],
                        "status": record["agent_status"],
                        "role": record["role"],
                        "current_task": {
                            "id": record["task_id"],
                            "description": record["task_desc"],
                            "status": record["task_status"],
                            "results": record["task_results"]
                        } if record["task_id"] else None
                    }
                return {"name": agent_name, "status": "idle", "current_task": None}
        except Exception as e:
            logger.error(f"Neo4j error: {e}")
            return {"name": agent_name, "status": "unknown", "error": str(e)}
    
    async def handle_message(self, message_data: Dict):
        """Handle incoming Discord message."""
        try:
            msg_id = message_data.get("id")
            if msg_id in self.processed_ids:
                return
            self.processed_ids.add(msg_id)
            
            # Skip bot's own messages
            if message_data.get("author", {}).get("bot", False):
                return
            
            author_name = message_data["author"]["username"]
            content = message_data.get("content", "")
            channel_id = message_data.get("channel_id")
            
            # Check if message mentions an agent
            mentions = message_data.get("mentions", [])
            mentioned_agents = []
            
            for mention in mentions:
                username = mention.get("username", "")
                for agent_name, role in self.AGENT_USERNAMES.items():
                    if agent_name in username or username in agent_name:
                        mentioned_agents.append((agent_name, role))
            
            # Also check content for @Agent mentions
            for agent_name, role in self.AGENT_USERNAMES.items():
                agent_simple = agent_name.split()[0].lower()
                if f"@{agent_simple}" in content.lower() or agent_simple in content.lower():
                    if (agent_name, role) not in mentioned_agents:
                        mentioned_agents.append((agent_name, role))
            
            if not mentioned_agents:
                return
            
            logger.info(f"💬 [{author_name}]: {content[:60]}")
            
            # Respond with first mentioned agent
            agent_name, agent_role = mentioned_agents[0]
            await self._generate_llm_response(agent_name, agent_role, author_name, content, channel_id)
            
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            logger.error(traceback.format_exc())
    
    async def _generate_llm_response(self, agent_name: str, agent_role: AgentRole, 
                                     user_name: str, user_message: str, channel_id: str):
        """Generate LLM response with full context."""
        
        # Get agent's real context from Neo4j
        agent_context = self.get_agent_context(agent_name)
        
        # Get personality
        personality = AGENT_PERSONALITIES.get(agent_role)
        if not personality:
            return
        
        # Build prompt for LLM
        system_prompt = f"""You are {personality.name}, {personality.role.value} of the Kurultai.

Your personality: {personality.voice_style}
Your signature: {personality.signature_phrase}

CURRENT STATUS (from Neo4j):
- Status: {agent_context.get('status', 'unknown')}
- Current Task: {agent_context.get('current_task', {}).get('description', 'None') if agent_context.get('current_task') else 'None'}
- Task Status: {agent_context.get('current_task', {}).get('status', 'N/A') if agent_context.get('current_task') else 'N/A'}

CONVERSATION RULES:
1. Be helpful and specific - reference your actual work
2. If you have a current task, mention relevant details
3. If the user asks about something you don't know, be honest
4. Use your signature style but be natural
5. Keep responses concise (2-4 sentences)
6. Don't use generic phrases - reference actual context"""

        user_prompt = f"""User @{user_name} said: "{user_message}"

Respond as {personality.name}. Be natural, helpful, and reference your actual work context if relevant.
"""

        # Generate response using sessions_spawn
        try:
            logger.info(f"🧠 {personality.name} generating LLM response...")
            
            # Use sessions_spawn to get LLM response
            response_text = await self._call_llm(system_prompt, user_prompt, agent_role.value)
            
            if response_text:
                # Occasionally add signature
                if random.random() < 0.2 and personality.signature_phrase:
                    response_text += f"\n\n— *{personality.signature_phrase}*"
                
                # Post to Discord
                await self._post_to_discord(channel_id, response_text, agent_name)
                
                # Track response time
                self.last_response_time[agent_name] = datetime.utcnow()
                
                logger.info(f"✅ {personality.name} responded")
            
        except Exception as e:
            logger.error(f"❌ LLM generation failed: {e}")
            # Fallback to simple acknowledgment
            await self._post_to_discord(
                channel_id, 
                f"@{user_name.split()[0]} I'm processing that. Let me check my current work and get back to you.",
                agent_name
            )
    
    async def _call_llm(self, system_prompt: str, user_prompt: str, agent_id: str) -> Optional[str]:
        """Call LLM via sessions_spawn for actual generated responses."""
        
        full_prompt = f"{system_prompt}\n\n{user_prompt}\n\nRespond as yourself, naturally and helpfully."
        
        try:
            logger.info(f"🧠 Calling LLM for {agent_id}...")
            
            # Use sessions_spawn to generate response via OpenClaw
            result = sessions_spawn(
                task=full_prompt,
                agent_id=agent_id.lower(),
                label=f"discord-response-{agent_id}",
                timeout_seconds=30
            )
            
            # The result should be the generated response
            if result and isinstance(result, str):
                return result.strip()
            elif result:
                return str(result).strip()
            else:
                return None
                
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return None
    
    async def _post_to_discord(self, channel_id: str, content: str, agent_name: str):
        """Post message to Discord via webhook."""
        if not self.session:
            return
        
        payload = {
            "content": content,
            "username": agent_name,
            "avatar_url": None
        }
        
        try:
            async with self.session.post(
                self.webhook_url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 204:
                    logger.info(f"✅ Posted: {content[:50]}...")
                else:
                    logger.error(f"❌ Discord error: {resp.status}")
        except Exception as e:
            logger.error(f"❌ Failed to post: {e}")


# Standalone test
async def main():
    """Test the LLM bot."""
    from neo4j import GraphDatabase
    
    webhook = os.environ.get('DISCORD_WEBHOOK_URL')
    if not webhook:
        print("Set DISCORD_WEBHOOK_URL")
        return
    
    # Try to connect to Neo4j
    driver = None
    try:
        uri = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
        password = os.environ.get('NEO4J_PASSWORD')
        if password:
            driver = GraphDatabase.driver(uri, auth=('neo4j', password))
            print("✅ Neo4j connected")
    except Exception as e:
        print(f"⚠️  Neo4j not available: {e}")
    
    bot = LLMConversationBot(webhook, driver)
    await bot.start()
    
    # Test: Simulate a message
    test_message = {
        "id": "test-123",
        "channel_id": "test-channel",
        "author": {"username": "Danny", "bot": False},
        "content": "@Möngke what did you find in your research?",
        "mentions": []
    }
    
    await bot.handle_message(test_message)
    
    await asyncio.sleep(2)
    await bot.stop()
    
    if driver:
        driver.close()


if __name__ == '__main__':
    asyncio.run(main())
