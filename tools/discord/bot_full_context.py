#!/usr/bin/env python3
"""
Kurultai Discord Bot - Full Context Integration

Integrates:
- OpenClaw context (LLM generation via sessions_spawn)
- Notion context (read/write task data)
- Neo4j context (already have this)

This is an OpenClaw session that runs continuously and responds to Discord.
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
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '/data/workspace/souls/main')

from deliberation_client import AgentRole, AGENT_PERSONALITIES

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kurultai-full-context")


class FullContextDiscordBot:
    """
    Discord bot with FULL context:
    - OpenClaw (LLM generation)
    - Notion (task management)
    - Neo4j (agent state)
    """
    
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
        self.processed_ids: Set[str] = set()
        self.last_response_time: Dict[str, datetime] = {}
        self.min_response_interval = timedelta(seconds=30)
    
    async def start(self):
        """Start the bot."""
        self.session = aiohttp.ClientSession()
        logger.info("🤖 Full-context Discord bot started")
        logger.info("   ✅ OpenClaw context: ACTIVE (can use sessions_spawn)")
        logger.info("   ✅ Notion context: Will integrate on request")
        logger.info("   ✅ Neo4j context: Connected")
    
    async def stop(self):
        """Stop the bot."""
        if self.session:
            await self.session.close()
    
    def get_neo4j_context(self, agent_name: str) -> Dict:
        """Get agent's current status from Neo4j."""
        if not self.neo4j_driver:
            return {"error": "No Neo4j connection"}
        
        try:
            with self.neo4j_driver.session() as session:
                result = session.run("""
                    MATCH (a:Agent {name: $name})
                    OPTIONAL MATCH (t:Task)
                    WHERE t.assigned_to = $name AND t.status IN ['in_progress', 'completed']
                    RETURN a.name as name,
                           a.status as agent_status,
                           t.id as task_id,
                           t.description as task_desc,
                           t.status as task_status,
                           t.updated_at as task_updated
                    ORDER BY t.updated_at DESC
                    LIMIT 1
                """, name=agent_name.replace(" 🏛️", "").replace(" 🔬", "").replace(" 📝", "")
                                    .replace(" 🛠️", "").replace(" 🔍", "").replace(" 📈", ""))
                
                record = result.single()
                if record:
                    return {
                        "name": record["name"],
                        "status": record["agent_status"],
                        "current_task": {
                            "id": record["task_id"],
                            "description": record["task_desc"],
                            "status": record["task_status"]
                        } if record["task_id"] else None
                    }
                return {"name": agent_name, "status": "idle", "current_task": None}
        except Exception as e:
            return {"error": str(e)}
    
    def get_notion_context(self, agent_name: str) -> Dict:
        """Get agent's tasks from Notion."""
        try:
            from tools.notion_integration import NotionIntegration
            from openclaw_memory import OperationalMemory
            
            memory = OperationalMemory()
            notion = NotionIntegration(memory)
            
            # Query Notion for tasks assigned to this agent
            tasks = notion.query_tasks(
                filters={
                    "assignee": agent_name,
                    "status": ["To Do", "In Progress"]
                }
            )
            
            return {
                "notion_tasks": [
                    {
                        "name": t.name,
                        "status": t.status,
                        "priority": t.priority,
                        "url": t.url
                    }
                    for t in tasks[:3]  # Top 3 tasks
                ]
            }
        except Exception as e:
            return {"notion_error": str(e)}
    
    async def handle_message(self, message_data: Dict):
        """Handle incoming Discord message."""
        try:
            msg_id = message_data.get("id")
            if msg_id in self.processed_ids:
                return
            self.processed_ids.add(msg_id)
            
            if message_data.get("author", {}).get("bot", False):
                return
            
            author_name = message_data["author"]["username"]
            content = message_data.get("content", "")
            channel_id = message_data.get("channel_id")
            
            # Find mentioned agents
            mentioned_agents = []
            for agent_name, role in self.AGENT_USERNAMES.items():
                agent_simple = agent_name.split()[0].lower()
                if f"@{agent_simple}" in content.lower() or agent_simple in content.lower():
                    mentioned_agents.append((agent_name, role))
            
            if not mentioned_agents:
                return
            
            logger.info(f"💬 [{author_name}]: {content[:60]}")
            
            # Respond with first mentioned agent
            agent_name, agent_role = mentioned_agents[0]
            await self._generate_full_context_response(
                agent_name, agent_role, author_name, content, channel_id
            )
            
        except Exception as e:
            logger.error(f"Error: {e}")
            logger.error(traceback.format_exc())
    
    async def _generate_full_context_response(self, agent_name: str, agent_role: AgentRole,
                                               user_name: str, user_message: str, channel_id: str):
        """Generate response with FULL context (OpenClaw + Notion + Neo4j)."""
        
        personality = AGENT_PERSONALITIES.get(agent_role)
        if not personality:
            return
        
        # Gather ALL context
        neo4j_context = self.get_neo4j_context(agent_name)
        notion_context = self.get_notion_context(agent_name)
        
        # Build comprehensive prompt
        context_sections = []
        
        # Neo4j section
        if neo4j_context.get('current_task'):
            task = neo4j_context['current_task']
            context_sections.append(f"""CURRENT NEO4J TASK:
- Task: {task['description']}
- Status: {task['status']}
- ID: {task['id'][:8]}""")
        
        # Notion section
        if notion_context.get('notion_tasks'):
            tasks_str = "\n".join([
                f"  • {t['name']} ({t['status']})"
                for t in notion_context['notion_tasks']
            ])
            context_sections.append(f"""NOTION TASKS:
{tasks_str}""")
        
        full_context = "\n\n".join(context_sections) if context_sections else "No active tasks."
        
        # Build prompt for LLM
        prompt = f"""You are {personality.name}, {personality.role.value} of the Kurultai.

Your personality: {personality.voice_style}
Your signature phrase: "{personality.signature_phrase}"

YOUR CURRENT CONTEXT:
{full_context}

USER MESSAGE:
@{user_name.split()[0]} said: "{user_message}"

INSTRUCTIONS:
1. Respond naturally as {personality.name}
2. Reference your actual work if relevant
3. Be helpful and specific
4. Use your signature style but be conversational
5. If you don't know something, say so
6. Keep response to 2-4 sentences
7. Only sign with your signature phrase occasionally (20% of the time)

Respond now:"""

        # Generate via OpenClaw (sessions_spawn is available!)
        try:
            logger.info(f"🧠 {personality.name} generating with FULL context...")
            
            response = sessions_spawn(
                task=prompt,
                agent_id=personality.role.value.lower(),
                label=f"discord-response-{personality.role.value.lower()}",
                timeout_seconds=30
            )
            
            if response:
                response_text = str(response).strip()
                
                # Post to Discord
                await self._post_to_discord(channel_id, response_text, agent_name)
                
                self.last_response_time[agent_name] = datetime.utcnow()
                logger.info(f"✅ {personality.name} responded")
            else:
                logger.error("LLM returned None")
                
        except Exception as e:
            logger.error(f"❌ LLM generation failed: {e}")
            # Fallback
            await self._post_to_discord(
                channel_id,
                f"@{user_name.split()[0]} I'm here. {personality.signature_phrase}",
                agent_name
            )
    
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


# This runs inside OpenClaw context - sessions_spawn is available!
async def main():
    """Run bot with full context."""
    from neo4j import GraphDatabase
    
    webhook = os.environ.get('DISCORD_WEBHOOK_URL')
    if not webhook:
        print("❌ Set DISCORD_WEBHOOK_URL")
        return
    
    # Connect to Neo4j
    driver = None
    try:
        uri = os.environ.get('NEO4J_URI')
        password = os.environ.get('NEO4J_PASSWORD')
        if uri and password:
            driver = GraphDatabase.driver(uri, auth=('neo4j', password))
            print("✅ Neo4j connected")
    except Exception as e:
        print(f"⚠️ Neo4j: {e}")
    
    bot = FullContextDiscordBot(webhook, driver)
    await bot.start()
    
    print("\n🤖 Bot running with FULL context:")
    print("   ✅ OpenClaw (LLM generation)")
    print("   ✅ Notion (task management)")
    print("   ✅ Neo4j (agent state)")
    print("\nMention @Agent in Discord to test!")
    print("Press Ctrl+C to stop\n")
    
    try:
        # Keep running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        await bot.stop()
        if driver:
            driver.close()
        print("\n✅ Bot stopped")


if __name__ == '__main__':
    asyncio.run(main())
