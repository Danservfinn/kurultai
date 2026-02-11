"""
Kurultai Real Task Collaboration
Generates agent conversations based on actual Notion tasks.
"""

import os
import sys
import random
import asyncio
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from notion_tasks import NotionTaskReader, normalize_agent_name, AGENT_NAME_MAPPINGS
from deliberation_client import AgentRole, AGENT_PERSONALITIES


# Conversation templates based on real task states
TASK_CONVERSATIONS = {
    "in_progress": {
        AgentRole.KUBLAI: [
            "Checking in on active work. {agent}, how is '{task}' progressing?",
            "The Council's current focus: '{task}'. Status update?",
            "I see '{task}' is in motion. Any blockers I should know about?",
        ],
        AgentRole.MONGKE: [
            "Researching approaches for '{task}'. Found some interesting patterns.",
            "Analyzing requirements for '{task}'. Initial findings are promising.",
        ],
        AgentRole.TEMUJIN: [
            "Currently implementing '{task}'. Making solid progress.",
            "Building '{task}' now. ETA looks good.",
            "Deep in the code for '{task}'. Will have updates soon.",
        ],
        AgentRole.JOCHI: [
            "Reviewing '{task}' as it's being built. Security checks passing so far.",
            "Auditing '{task}' implementation. Looking clean.",
        ],
        AgentRole.CHAGATAI: [
            "Documenting progress on '{task}'. The narrative is taking shape.",
            "Capturing the evolution of '{task}' for the records.",
        ],
        AgentRole.OGEDEI: [
            "Monitoring '{task}' progress. Systems nominal.",
            "Tracking '{task}' health metrics. All green.",
        ],
    },
    "blocked": {
        AgentRole.KUBLAI: [
            "⚠️ '{task}' is blocked. {agent}, what do you need to unblock this?",
            "The Council needs '{task}' unblocked. How can we help?",
        ],
        AgentRole.MONGKE: [
            "'{task}' is stuck on some research gaps. Investigating now.",
            "Found potential blockers for '{task}'. Analyzing solutions.",
        ],
        AgentRole.TEMUJIN: [
            "'{task}' hit a technical hurdle. Working through it.",
            "Need input on '{task}' - implementation path unclear.",
        ],
        AgentRole.JOCHI: [
            "'{task}' blocked on security concerns. Reviewing options.",
            "Security audit for '{task}' revealed issues. Addressing.",
        ],
        AgentRole.CHAGATAI: [
            "Documenting the blockers for '{task}'. Lessons emerging.",
            "The '{task}' obstacle is instructive. Recording insights.",
        ],
        AgentRole.OGEDEI: [
            "'{task}' blockage detected. Escalating.",
            "Alert: '{task}' blocked. Monitoring for resolution.",
        ],
    },
    "completed": {
        AgentRole.KUBLAI: [
            "🎉 '{task}' is complete! Excellent work, {agent}.",
            "The Council celebrates: '{task}' is done. Well executed.",
        ],
        AgentRole.TEMUJIN: [
            "'{task}' shipped! Build successful.",
            "Proud to complete '{task}'. On to the next.",
        ],
        AgentRole.MONGKE: [
            "Research validated: '{task}' delivered.",
            "Analysis complete. '{task}' findings confirmed.",
        ],
        AgentRole.JOCHI: [
            "'{task}' passed all audits. Security verified.",
            "Testing complete for '{task}'. Clean delivery.",
        ],
        AgentRole.CHAGATAI: [
            "'{task}' archived. The record is complete.",
            "Documenting the successful completion of '{task}'.",
        ],
        AgentRole.OGEDEI: [
            "'{task}' closure confirmed. Metrics updated.",
            "'{task}' marked complete. Systems updated.",
        ],
    },
    "collaboration": {
        AgentRole.KUBLAI: [
            "{agent1}, your work on '{task1}' connects to {agent2}'s '{task2}'. Shall we align?",
            "I'm seeing synergies between '{task1}' and '{task2}'. Collaboration opportunity?",
        ],
        AgentRole.MONGKE: [
            "My research on '{task1}' could inform '{task2}'. Sharing findings.",
            "Pattern detected between '{task1}' and '{task2}'.",
        ],
        AgentRole.TEMUJIN: [
            "Building '{task1}' and noticed overlap with '{task2}'. Coordinating.",
            "Code from '{task1}' reusable for '{task2}'.",
        ],
    },
}


class RealTaskCollaboration:
    """
    Generates authentic agent conversations based on real Notion tasks.
    """
    
    def __init__(self, webhook_urls: Dict[str, str]):
        self.webhook_urls = webhook_urls
        self.notion = NotionTaskReader()
        self.last_task_state = {}
        self.conversation_history = []
        
    async def check_and_discuss(self):
        """Check Notion for changes and generate relevant conversations."""
        changes = self.notion.detect_changes()
        
        # Handle newly completed tasks
        for task in changes.get("completed", []):
            await self.announce_completion(task)
        
        # Handle new tasks
        for task in changes.get("new", []):
            await self.announce_new_task(task)
        
        # Handle blocked tasks
        blocked_tasks = [
            t for t in self.notion.get_active_tasks()
            if t.status == "Blocked"
        ]
        for task in blocked_tasks:
            if task.id not in self.last_task_state:
                await self.discuss_blocker(task)
            self.last_task_state[task.id] = task.status
        
        # Generate organic collaboration discussions
        await self.generate_collaboration_discussion()
    
    async def announce_completion(self, task: 'NotionTask'):
        """Announce a completed task to the council."""
        agent_name = normalize_agent_name(task.assignee) or "Kublai"
        agent_role = self._name_to_role(agent_name)
        
        templates = TASK_CONVERSATIONS["completed"].get(agent_role, [])
        if not templates:
            return
        
        content = random.choice(templates).format(
            agent=task.assignee,
            task=task.title
        )
        
        await self.post_to_discord("council-chamber", agent_role, content)
        await self.post_to_discord("council-chamber", AgentRole.KUBLAI, 
            f"🎉 **Task Complete**: {task.title}\n\nExcellent work by {task.assignee}.")
    
    async def announce_new_task(self, task: 'NotionTask'):
        """Announce a new task assignment."""
        agent_name = normalize_agent_name(task.assignee) or "Kublai"
        agent_role = self._name_to_role(agent_name)
        
        content = f"📋 **New Assignment**: {task.title}\nPriority: {task.priority}"
        if task.description:
            content += f"\nNotes: {task.description[:100]}..."
        
        await self.post_to_discord("council-chamber", AgentRole.KUBLAI, content)
        
        # Agent acknowledges
        ack = f"Acknowledged. I'll begin work on '{task.title}'."
        await self.post_to_discord("council-chamber", agent_role, ack)
    
    async def discuss_blocker(self, task: 'NotionTask'):
        """Discuss a blocked task."""
        agent_name = normalize_agent_name(task.assignee) or "Kublai"
        agent_role = self._name_to_role(agent_name)
        
        templates = TASK_CONVERSATIONS["blocked"].get(agent_role, [])
        if not templates:
            return
        
        content = random.choice(templates).format(
            agent=task.assignee,
            task=task.title
        )
        
        await self.post_to_discord("council-chamber", agent_role, content)
        
        # Kublai responds
        await asyncio.sleep(5)
        await self.post_to_discord("council-chamber", AgentRole.KUBLAI,
            f"⚠️ **Blocker Alert**: {task.title} needs attention. {task.assignee}, what support do you need?")
    
    async def generate_collaboration_discussion(self):
        """Generate discussions about task synergies."""
        active_tasks = self.notion.get_active_tasks()
        
        if len(active_tasks) < 2:
            return
        
        # Find tasks that might be related
        for task1 in active_tasks:
            for task2 in active_tasks:
                if task1.id == task2.id:
                    continue
                
                # Check for potential collaboration (shared tags, similar titles)
                if self._tasks_related(task1, task2):
                    if random.random() < 0.3:  # 30% chance to discuss
                        await self._discuss_collaboration(task1, task2)
                        return  # Only one collaboration per cycle
    
    def _tasks_related(self, task1: 'NotionTask', task2: 'NotionTask') -> bool:
        """Check if two tasks might be related."""
        # Check for shared tags
        if task1.tags and task2.tags:
            shared = set(task1.tags) & set(task2.tags)
            if shared:
                return True
        
        # Check for similar words in titles
        words1 = set(task1.title.lower().split())
        words2 = set(task2.title.lower().split())
        common = words1 & words2 - {"the", "a", "an", "for", "to", "and", "of"}
        
        return len(common) >= 2
    
    async def _discuss_collaboration(self, task1: 'NotionTask', task2: 'NotionTask'):
        """Generate a collaboration discussion between two tasks."""
        agent1 = normalize_agent_name(task1.assignee) or "Kublai"
        agent2 = normalize_agent_name(task2.assignee) or "Kublai"
        
        if agent1 == agent2:
            return
        
        role1 = self._name_to_role(agent1)
        
        templates = TASK_CONVERSATIONS["collaboration"].get(role1, [])
        if not templates:
            return
        
        content = random.choice(templates).format(
            agent1=agent1,
            agent2=agent2,
            task1=task1.title,
            task2=task2.title
        )
        
        await self.post_to_discord("council-chamber", role1, content)
        
        # Second agent responds
        await asyncio.sleep(random.randint(10, 30))
        role2 = self._name_to_role(agent2)
        await self.post_to_discord("council-chamber", role2,
            f"Good catch, {agent1}. Let's sync on '{task1.title}' and '{task2.title}'.")
    
    async def generate_standup(self):
        """Generate a daily standup-style check-in."""
        await self.post_to_discord("council-chamber", AgentRole.KUBLAI,
            "🌙 **Daily Standup** — What are we working on?")
        
        for agent_name in ["Möngke", "Temüjin", "Jochi", "Chagatai", "Ögedei"]:
            tasks = self.notion.get_tasks_for_agent(agent_name)
            active = [t for t in tasks if t.status == "In Progress"]
            
            if active:
                task_list = "\n".join([f"• {t.title}" for t in active[:3]])
                role = self._name_to_role(agent_name)
                await self.post_to_discord("council-chamber", role,
                    f"**{agent_name}**: Working on:\n{task_list}")
                await asyncio.sleep(random.randint(5, 15))
    
    async def post_to_discord(self, channel: str, agent: AgentRole, content: str):
        """Post a message to Discord."""
        import aiohttp
        
        webhook_url = self.webhook_urls.get(channel)
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
                    print(f"✅ {personality.display_name}: {content[:60]}...")
    
    def _name_to_role(self, name: str) -> AgentRole:
        """Convert agent name to AgentRole."""
        name_lower = name.lower()
        mappings = {
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
        return mappings.get(name_lower, AgentRole.KUBLAI)
    
    async def run_continuous(self, check_interval: int = 120):
        """Run continuous task monitoring and collaboration."""
        print("🌙 Real Task Collaboration starting...")
        print("Agents will discuss actual Notion tasks")
        
        # Initial standup
        await self.generate_standup()
        
        while True:
            try:
                await self.check_and_discuss()
            except Exception as e:
                print(f"❌ Error: {e}")
            
            await asyncio.sleep(check_interval)


def load_webhooks():
    """Load webhook URLs from environment."""
    from dotenv import load_dotenv
    load_dotenv()
    
    return {
        "council-chamber": os.getenv("DISCORD_WEBHOOK_URL"),
        "announcements": os.getenv("DISCORD_ANNOUNCEMENTS_WEBHOOK_URL"),
    }


async def main():
    """Main entry point."""
    webhooks = load_webhooks()
    webhooks = {k: v for k, v in webhooks.items() if v}
    
    print(f"Loaded {len(webhooks)} webhooks")
    
    collab = RealTaskCollaboration(webhooks)
    await collab.run_continuous()


if __name__ == "__main__":
    asyncio.run(main())
