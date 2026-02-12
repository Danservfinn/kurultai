#!/usr/bin/env python3
"""
Kurultai Discord Deliberation Bot - Purpose-Driven Agent Communication

Agents talk to each other ONLY when:
1. Handoff needed (research → implementation)
2. Problem-solving (blocked, need expertise)
3. Review requested (quality gates)
4. Coordination required (shared resources)
5. Escalation (complex decisions)

NO social chatter. NO template phrases. Real context from Neo4j + LLM generation.
"""

import os
import sys
import json
import asyncio
import aiohttp
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kurultai-deliberation")


class DeliberationType(Enum):
    HANDOFF = "handoff"           # Research → Implementation
    PROBLEM_SOLVING = "problem"   # Blocked, need help
    REVIEW = "review"             # Quality gate
    COORDINATION = "coordination" # Shared resources
    ESCALATION = "escalation"     # Complex decision


@dataclass
class DeliberationThread:
    """Tracks a purposeful agent-to-agent conversation."""
    id: str
    thread_type: DeliberationType
    initiator: str
    participants: List[str]
    topic: str
    context: Dict
    messages: List[Dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    status: str = "active"  # active, resolved, escalated
    
    def add_message(self, author: str, content: str):
        self.messages.append({
            "author": author,
            "content": content,
            "timestamp": datetime.utcnow().isoformat()
        })
    
    def get_history(self, limit: int = 10) -> str:
        """Get conversation history for LLM context."""
        recent = self.messages[-limit:] if len(self.messages) > limit else self.messages
        return "\n".join([
            f"{m['author']}: {m['content'][:200]}"
            for m in recent
        ])
    
    def should_escalate(self) -> bool:
        """Check if deliberation should escalate to full Council."""
        # Escalate if too many messages without resolution
        if len(self.messages) > 12:
            return True
        # Escalate if stale
        if self.messages:
            last_time = datetime.fromisoformat(self.messages[-1]['timestamp'])
            if datetime.utcnow() - last_time > timedelta(minutes=30):
                return True
        return False


class AgentDeliberationBot:
    """Purpose-driven agent-to-agent communication."""
    
    def __init__(self, webhook_url: str, neo4j_driver=None):
        self.webhook_url = webhook_url
        self.neo4j_driver = neo4j_driver
        self.active_threads: Dict[str, DeliberationThread] = {}
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Agent capabilities for routing
        self.agent_capabilities = {
            "Möngke": ["research", "analysis", "pattern_recognition"],
            "Temüjin": ["implementation", "coding", "architecture"],
            "Jochi": ["security", "testing", "audit", "validation"],
            "Chagatai": ["documentation", "writing", "synthesis"],
            "Ögedei": ["operations", "monitoring", "coordination"],
            "Kublai": ["routing", "synthesis", "decision_making"]
        }
    
    async def start(self):
        """Start the deliberation bot."""
        self.session = aiohttp.ClientSession()
        logger.info("🧠 Deliberation bot started")
    
    async def stop(self):
        """Stop the deliberation bot."""
        if self.session:
            await self.session.close()
    
    def check_for_deliberation_trigger(self, task_update: Dict) -> Optional[DeliberationThread]:
        """
        Check if a task update should trigger agent deliberation.
        
        Returns a DeliberationThread if deliberation needed, None otherwise.
        """
        task_status = task_update.get('status')
        task_type = task_update.get('type', 'task')
        agent = task_update.get('assigned_to')
        complexity = task_update.get('complexity', 5)
        blocker = task_update.get('blocker')
        
        # TRIGGER 1: Research complete → handoff to implementation
        if task_status == 'completed' and task_type == 'research':
            return self._create_handoff_thread(task_update)
        
        # TRIGGER 2: Implementation blocked → need expertise
        if task_status == 'blocked' and blocker:
            return self._create_problem_solving_thread(task_update)
        
        # TRIGGER 3: Complex task complete → need review
        if task_status == 'completed' and complexity >= 7:
            return self._create_review_thread(task_update)
        
        # TRIGGER 4: Resource conflict detected
        if task_update.get('resource_conflict'):
            return self._create_coordination_thread(task_update)
        
        # TRIGGER 5: Critical issue → escalate to Council
        if task_update.get('priority') == 'critical' and task_status == 'failed':
            return self._create_escalation_thread(task_update)
        
        return None
    
    def _create_handoff_thread(self, task: Dict) -> DeliberationThread:
        """Create handoff deliberation: research → implementation."""
        research_agent = task.get('assigned_to', 'Möngke')
        
        # Find best implementer based on task content
        if 'code' in task.get('description', '').lower() or 'build' in task.get('description', '').lower():
            target_agent = 'Temüjin'
        elif 'documentation' in task.get('description', '').lower():
            target_agent = 'Chagatai'
        elif 'test' in task.get('description', '').lower():
            target_agent = 'Jochi'
        else:
            target_agent = 'Temüjin'  # Default builder
        
        thread = DeliberationThread(
            id=f"handoff-{task['id'][:8]}",
            thread_type=DeliberationType.HANDOFF,
            initiator=research_agent,
            participants=[research_agent, target_agent],
            topic=f"Handoff: {task.get('description', 'Task')[:50]}",
            context={
                'task_id': task['id'],
                'research_findings': task.get('results', {}),
                'estimated_implementation_time': task.get('estimated_next_phase', 'unknown'),
                'blockers_identified': task.get('blockers', [])
            }
        )
        
        self.active_threads[thread.id] = thread
        return thread
    
    def _create_problem_solving_thread(self, task: Dict) -> DeliberationThread:
        """Create problem-solving deliberation when blocked."""
        blocked_agent = task.get('assigned_to')
        blocker = task.get('blocker', 'unknown issue')
        
        # Determine who can help based on blocker type
        if 'security' in blocker.lower() or 'vulnerability' in blocker.lower():
            helper = 'Jochi'
        elif 'api' in blocker.lower() or 'integration' in blocker.lower():
            helper = 'Temüjin'
        elif 'research' in blocker.lower() or 'data' in blocker.lower():
            helper = 'Möngke'
        elif 'operations' in blocker.lower() or 'system' in blocker.lower():
            helper = 'Ögedei'
        else:
            helper = 'Kublai'  # Router can find right person
        
        thread = DeliberationThread(
            id=f"problem-{task['id'][:8]}",
            thread_type=DeliberationType.PROBLEM_SOLVING,
            initiator=blocked_agent,
            participants=[blocked_agent, helper],
            topic=f"Blocker: {blocker[:50]}",
            context={
                'task_id': task['id'],
                'blocker': blocker,
                'attempted_solutions': task.get('attempted_solutions', []),
                'time_blocked': task.get('time_blocked', 'unknown')
            }
        )
        
        self.active_threads[thread.id] = thread
        return thread
    
    def _create_review_thread(self, task: Dict) -> DeliberationThread:
        """Create review deliberation for quality gate."""
        author = task.get('assigned_to')
        
        # Determine reviewer based on task type
        if task.get('type') == 'documentation':
            reviewer = 'Möngke'  # Verify technical accuracy
        elif task.get('type') == 'implementation':
            reviewer = 'Jochi'  # Security review
        else:
            reviewer = 'Chagatai'  # General review
        
        thread = DeliberationThread(
            id=f"review-{task['id'][:8]}",
            thread_type=DeliberationType.REVIEW,
            initiator=author,
            participants=[author, reviewer],
            topic=f"Review: {task.get('description', 'Deliverable')[:50]}",
            context={
                'task_id': task['id'],
                'deliverables': task.get('deliverables', []),
                'complexity': task.get('complexity', 5),
                'time_invested': task.get('time_invested', 'unknown')
            }
        )
        
        self.active_threads[thread.id] = thread
        return thread
    
    def _create_coordination_thread(self, task: Dict) -> DeliberationThread:
        """Create coordination deliberation for resource conflicts."""
        thread = DeliberationThread(
            id=f"coord-{task['id'][:8]}",
            thread_type=DeliberationType.COORDINATION,
            initiator=task.get('assigned_to'),
            participants=['Ögedei', task.get('assigned_to')],  # Ops coordinates
            topic=f"Coordination: {task.get('description', 'Resource conflict')[:50]}",
            context={
                'resource_type': task.get('resource_type'),
                'conflicting_tasks': task.get('conflicting_tasks', []),
                'priority_matrix': task.get('priority_matrix', {})
            }
        )
        
        self.active_threads[thread.id] = thread
        return thread
    
    def _create_escalation_thread(self, task: Dict) -> DeliberationThread:
        """Create escalation deliberation for critical issues."""
        thread = DeliberationThread(
            id=f"escalate-{task['id'][:8]}",
            thread_type=DeliberationType.ESCALATION,
            initiator=task.get('assigned_to'),
            participants=['Kublai', 'Möngke', 'Chagatai', 'Temüjin', 'Jochi', 'Ögedei'],  # Full Council
            topic=f"🚨 CRITICAL: {task.get('description', 'Issue')[:50]}",
            context={
                'task_id': task['id'],
                'failure_reason': task.get('error', 'unknown'),
                'impact_assessment': task.get('impact', 'high'),
                'attempted_recovery': task.get('recovery_attempts', [])
            }
        )
        
        self.active_threads[thread.id] = thread
        return thread
    
    async def initiate_deliberation(self, thread: DeliberationThread):
        """Post the opening message to start deliberation."""
        
        # Generate opening message based on thread type
        if thread.thread_type == DeliberationType.HANDOFF:
            message = await self._generate_handoff_opening(thread)
        elif thread.thread_type == DeliberationType.PROBLEM_SOLVING:
            message = await self._generate_problem_opening(thread)
        elif thread.thread_type == DeliberationType.REVIEW:
            message = await self._generate_review_opening(thread)
        elif thread.thread_type == DeliberationType.COORDINATION:
            message = await self._generate_coordination_opening(thread)
        elif thread.thread_type == DeliberationType.ESCALATION:
            message = await self._generate_escalation_opening(thread)
        else:
            message = f"@{thread.participants[1]} — need to discuss: {thread.topic}"
        
        # Post to Discord
        await self._post_to_discord(
            channel="#agent-deliberations",
            content=message,
            author=thread.initiator,
            thread_name=thread.topic
        )
        
        # Store first message
        thread.add_message(thread.initiator, message)
        
        logger.info(f"🧠 Started {thread.thread_type.value} deliberation: {thread.id}")
    
    async def _generate_handoff_opening(self, thread: DeliberationThread) -> str:
        """Generate handoff opening message."""
        target = thread.participants[1]
        findings = thread.context.get('research_findings', {})
        
        # In real implementation, this would use LLM with full context
        # For now, structured message with actual content
        message_parts = [f"@{target} — research complete on **{thread.topic}**"]
        
        if findings:
            message_parts.append(f"\n**Key findings:**")
            if isinstance(findings, dict):
                for key, value in list(findings.items())[:3]:
                    message_parts.append(f"• {key}: {str(value)[:100]}")
        
        blockers = thread.context.get('blockers_identified', [])
        if blockers:
            message_parts.append(f"\n**Implementation notes:**")
            for blocker in blockers[:2]:
                message_parts.append(f"⚠️ {blocker}")
        
        message_parts.append(f"\n**Estimated effort:** {thread.context.get('estimated_implementation_time', 'TBD')}")
        message_parts.append(f"\nReady for implementation. Questions?")
        
        return "\n".join(message_parts)
    
    async def _generate_problem_opening(self, thread: DeliberationContext) -> str:
        """Generate problem-solving opening message."""
        helper = thread.participants[1]
        blocker = thread.context.get('blocker', 'unknown')
        attempted = thread.context.get('attempted_solutions', [])
        
        message_parts = [f"@{helper} — blocked on **{thread.topic}**"]
        message_parts.append(f"\n**Blocker:** {blocker}")
        
        if attempted:
            message_parts.append(f"\n**Already tried:**")
            for attempt in attempted[:3]:
                message_parts.append(f"• {attempt}")
        
        message_parts.append(f"\nTime blocked: {thread.context.get('time_blocked', 'unknown')}")
        message_parts.append(f"\nNeed your expertise to unblock. Thoughts?")
        
        return "\n".join(message_parts)
    
    async def _generate_review_opening(self, thread: DeliberationThread) -> str:
        """Generate review opening message."""
        reviewer = thread.participants[1]
        deliverables = thread.context.get('deliverables', [])
        
        message_parts = [f"@{reviewer} — ready for review: **{thread.topic}**"]
        
        if deliverables:
            message_parts.append(f"\n**Deliverables:**")
            for d in deliverables[:3]:
                message_parts.append(f"• `{d}`")
        
        message_parts.append(f"\nComplexity: {thread.context.get('complexity', 5)}/10")
        message_parts.append(f"Time invested: {thread.context.get('time_invested', 'unknown')}")
        message_parts.append(f"\nPlease review when you have capacity.")
        
        return "\n".join(message_parts)
    
    async def _generate_coordination_opening(self, thread: DeliberationThread) -> str:
        """Generate coordination opening message."""
        resource = thread.context.get('resource_type', 'resource')
        conflicts = thread.context.get('conflicting_tasks', [])
        
        message_parts = [f"@everyone — coordination needed for **{resource}**"]
        
        if conflicts:
            message_parts.append(f"\n**Conflicting tasks:**")
            for task in conflicts:
                message_parts.append(f"• {task.get('agent', 'Unknown')}: {task.get('description', 'Task')[:50]}")
        
        message_parts.append(f"\n**Proposed resolution:**")
        message_parts.append(f"Please check priority matrix and confirm approach.")
        
        return "\n".join(message_parts)
    
    async def _generate_escalation_opening(self, thread: DeliberationThread) -> str:
        """Generate escalation opening message."""
        reason = thread.context.get('failure_reason', 'unknown')
        impact = thread.context.get('impact_assessment', 'high')
        
        message_parts = [f"🚨 **CRITICAL ESCALATION** 🚨"]
        message_parts.append(f"\n**Issue:** {thread.topic}")
        message_parts.append(f"**Impact:** {impact}")
        message_parts.append(f"**Reason:** {reason[:200]}")
        
        attempts = thread.context.get('attempted_recovery', [])
        if attempts:
            message_parts.append(f"\n**Recovery attempts:** {len(attempts)}")
        
        message_parts.append(f"\n@everyone Council deliberation required. Please review and advise.")
        
        return "\n".join(message_parts)
    
    async def _post_to_discord(self, channel: str, content: str, author: str, thread_name: Optional[str] = None):
        """Post message to Discord via webhook."""
        if not self.session:
            logger.error("Session not started")
            return
        
        # Map agent names to display names
        display_names = {
            "Kublai": "Kublai 🏛️",
            "Möngke": "Möngke 🔬",
            "Chagatai": "Chagatai 📝",
            "Temüjin": "Temüjin 🛠️",
            "Jochi": "Jochi 🔍",
            "Ögedei": "Ögedei 📈"
        }
        
        payload = {
            "content": content,
            "username": display_names.get(author, author),
            "avatar_url": None  # Could add agent avatars
        }
        
        if thread_name:
            payload["thread_name"] = thread_name
        
        try:
            async with self.session.post(
                self.webhook_url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 204:
                    logger.info(f"✅ Posted to Discord: {content[:50]}...")
                else:
                    logger.error(f"❌ Discord error: {resp.status}")
        except Exception as e:
            logger.error(f"❌ Failed to post: {e}")
    
    async def continue_deliberation(self, thread_id: str, responder: str, message_content: str):
        """Continue an existing deliberation with a new message."""
        thread = self.active_threads.get(thread_id)
        if not thread:
            logger.warning(f"Thread not found: {thread_id}")
            return
        
        # Add message to thread
        thread.add_message(responder, message_content)
        
        # Check if resolved
        if any(word in message_content.lower() for word in ['resolved', 'complete', 'done', 'proceed']):
            thread.status = "resolved"
            logger.info(f"✅ Deliberation resolved: {thread_id}")
        
        # Check for escalation
        elif thread.should_escalate():
            thread.status = "escalated"
            await self._escalate_to_council(thread)
        
        # Post response
        target = [p for p in thread.participants if p != responder][0]
        await self._post_to_discord(
            channel="#agent-deliberations",
            content=f"@{target} {message_content}",
            author=responder
        )
    
    async def _escalate_to_council(self, thread: DeliberationThread):
        """Escalate deliberation to full Council."""
        logger.info(f"🚨 Escalating to Council: {thread.id}")
        
        # Post escalation notice
        await self._post_to_discord(
            channel="#council-chamber",
            content=f"🚨 **ESCALATION** 🚨\n\nDeliberation `{thread.id}` requires full Council review.\nTopic: {thread.topic}\n\n@everyone",
            author="Kublai"
        )


# Standalone execution
async def main():
    """Run deliberation bot in standalone mode."""
    webhook = os.environ.get('DISCORD_WEBHOOK_URL')
    if not webhook:
        logger.error("DISCORD_WEBHOOK_URL not set")
        return
    
    bot = AgentDeliberationBot(webhook)
    await bot.start()
    
    # Example: Simulate a handoff
    example_task = {
        'id': 'task-12345678',
        'status': 'completed',
        'type': 'research',
        'assigned_to': 'Möngke',
        'description': 'AI self-improvement research',
        'results': {
            'reflexion_improvement': '+30% on code tasks',
            'constitutional_ai_alignment': '95% reduction in harmful outputs'
        },
        'estimated_next_phase': '2-3 hours',
        'blockers': ['Need to handle iterative critique loops']
    }
    
    thread = bot.check_for_deliberation_trigger(example_task)
    if thread:
        await bot.initiate_deliberation(thread)
    
    await asyncio.sleep(5)
    await bot.stop()


if __name__ == '__main__':
    asyncio.run(main())
