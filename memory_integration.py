"""
Memory Integration - Integration between MemoryManager and OperationalMemory.

This module provides seamless integration between the tiered MemoryManager
and the existing OperationalMemory class, enabling:
- Shared Neo4j connections
- Unified agent memory access
- Coordinated cache invalidation
- Cross-tier task and notification tracking
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field

from memory_manager import (
    MemoryManager,
    MemoryTier,
    MemoryEntry,
    MemoryStats,
    estimate_tokens,
    create_memory_manager
)
from openclaw_memory import OperationalMemory

logger = logging.getLogger(__name__)


@dataclass
class IntegratedMemoryContext:
    """
    Combined memory context from all tiers.

    Provides a unified view of an agent's memory across
    hot, warm, cold, and archive tiers.
    """
    agent_name: str
    hot_context: str = ""
    warm_context: str = ""
    cold_context: str = ""
    active_tasks: List[Dict] = field(default_factory=list)
    pending_notifications: List[Dict] = field(default_factory=list)
    recent_beliefs: List[Dict] = field(default_factory=list)
    total_tokens: int = 0
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_markdown(self, max_tokens: int = 2000) -> str:
        """
        Convert context to bounded Markdown format.

        Args:
            max_tokens: Maximum tokens for output

        Returns:
            Formatted Markdown string
        """
        sections = []
        current_tokens = 0

        # Always include hot context
        if self.hot_context:
            header = f"# {self.agent_name.upper()} Memory Context\n\n"
            sections.append(header)
            current_tokens += estimate_tokens(header)

            hot_section = f"## Current Focus\n{self.hot_context}\n\n"
            sections.append(hot_section)
            current_tokens += estimate_tokens(hot_section)

        # Include active tasks if space permits
        if self.active_tasks and current_tokens < max_tokens * 0.7:
            task_section = "## Active Tasks\n"
            for task in self.active_tasks[:5]:  # Top 5 tasks
                task_line = f"- [{task.get('status', 'unknown')}] {task.get('description', 'Unknown')}\n"
                task_tokens = estimate_tokens(task_line)
                if current_tokens + task_tokens > max_tokens * 0.8:
                    break
                task_section += task_line
                current_tokens += task_tokens
            task_section += "\n"
            sections.append(task_section)

        # Include warm context if space permits
        if self.warm_context and current_tokens < max_tokens * 0.8:
            warm_header = "## Recent Activity\n"
            warm_tokens = estimate_tokens(warm_header) + estimate_tokens(self.warm_context)
            if current_tokens + warm_tokens <= max_tokens:
                sections.append(warm_header + self.warm_context + "\n\n")
                current_tokens += warm_tokens

        # Include pending notifications if space permits
        if self.pending_notifications and current_tokens < max_tokens * 0.9:
            notif_section = "## Notifications\n"
            for notif in self.pending_notifications[:3]:
                notif_line = f"- {notif.get('summary', 'New notification')}\n"
                notif_tokens = estimate_tokens(notif_line)
                if current_tokens + notif_tokens > max_tokens:
                    break
                notif_section += notif_line
                current_tokens += notif_tokens
            notif_section += "\n"
            sections.append(notif_section)

        return "".join(sections)


class IntegratedMemoryManager:
    """
    Integrated memory manager combining MemoryManager and OperationalMemory.

    Provides a unified interface for agent memory operations with:
    - Tiered memory caching (hot/warm/cold/archive)
    - Task lifecycle management
    - Notification handling
    - Bounded memory output

    Attributes:
        agent_name: Name of the agent
        memory_manager: Tiered MemoryManager instance
        operational_memory: OperationalMemory instance
    """

    def __init__(
        self,
        agent_name: str,
        operational_memory: OperationalMemory,
        enable_warm_tier: bool = True,
        enable_cold_tier: bool = False
    ):
        """
        Initialize IntegratedMemoryManager.

        Args:
            agent_name: Name of the agent
            operational_memory: Existing OperationalMemory instance
            enable_warm_tier: Whether to enable warm tier loading
            enable_cold_tier: Whether to enable cold tier loading
        """
        self.agent_name = agent_name
        self.operational_memory = operational_memory
        self.enable_warm_tier = enable_warm_tier
        self.enable_cold_tier = enable_cold_tier

        # Initialize MemoryManager with shared operational memory
        self.memory_manager = MemoryManager(
            agent_name=agent_name,
            operational_memory=operational_memory,
            fallback_mode=True
        )

        # Cache locks
        self._context_lock = asyncio.Lock()
        self._last_context: Optional[IntegratedMemoryContext] = None
        self._last_context_time: Optional[datetime] = None

        logger.info(f"IntegratedMemoryManager initialized for {agent_name}")

    async def initialize(self) -> bool:
        """
        Initialize both memory systems.

        Returns:
            True if initialization successful
        """
        try:
            # Initialize MemoryManager (loads hot tier)
            await self.memory_manager.initialize()

            # Verify OperationalMemory connection
            health = self.operational_memory.health_check()
            if health["status"] not in ["healthy", "fallback_mode"]:
                logger.warning(f"OperationalMemory health check: {health['status']}")

            return True
        except Exception as e:
            logger.error(f"Failed to initialize IntegratedMemoryManager: {e}")
            return False

    async def get_memory_context(
        self,
        force_refresh: bool = False,
        max_tokens: int = 2000
    ) -> IntegratedMemoryContext:
        """
        Get comprehensive memory context for the agent.

        Args:
            force_refresh: Force refresh from Neo4j
            max_tokens: Maximum tokens for context

        Returns:
            IntegratedMemoryContext with all tiers
        """
        async with self._context_lock:
            # Check if we can use cached context
            if not force_refresh and self._last_context:
                cache_age = (datetime.now(timezone.utc) - self._last_context_time).total_seconds()
                if cache_age < 30:  # Cache for 30 seconds
                    return self._last_context

            # Build fresh context
            context = IntegratedMemoryContext(agent_name=self.agent_name)

            # Get hot tier context
            context.hot_context = await self.memory_manager.get_memory_context(
                include_warm=False,
                include_cold=False
            )

            # Get warm tier if enabled
            if self.enable_warm_tier:
                warm_entries = await self._get_warm_tier_entries()
                context.warm_context = self._format_entries(warm_entries)

            # Get active tasks from OperationalMemory
            context.active_tasks = self.operational_memory.list_pending_tasks(
                agent=self.agent_name
            )

            # Get pending notifications
            context.pending_notifications = self.operational_memory.get_notifications(
                agent=self.agent_name,
                unread_only=True
            )

            # Get recent beliefs
            context.recent_beliefs = await self._get_recent_beliefs()

            # Calculate total tokens
            context.total_tokens = (
                estimate_tokens(context.hot_context) +
                estimate_tokens(context.warm_context)
            )

            # Cache the context
            self._last_context = context
            self._last_context_time = datetime.now(timezone.utc)

            return context

    async def get_memory_markdown(
        self,
        force_refresh: bool = False,
        max_tokens: int = 2000
    ) -> str:
        """
        Get memory context as formatted Markdown.

        Args:
            force_refresh: Force refresh from Neo4j
            max_tokens: Maximum tokens for output

        Returns:
            Formatted Markdown string
        """
        context = await self.get_memory_context(force_refresh, max_tokens)
        return context.to_markdown(max_tokens)

    async def _get_warm_tier_entries(self) -> List[MemoryEntry]:
        """Get warm tier entries from MemoryManager."""
        # Trigger warm tier load if not loaded
        if not self.memory_manager._warm_loaded:
            await self.memory_manager._load_warm_tier()

        return list(self.memory_manager._warm_cache.values())

    async def _get_recent_beliefs(self) -> List[Dict]:
        """Get recent high-confidence beliefs."""
        # This would query Neo4j directly for beliefs
        # For now, return empty list
        return []

    def _format_entries(self, entries: List[MemoryEntry]) -> str:
        """Format memory entries as text."""
        if not entries:
            return ""

        lines = []
        for entry in sorted(entries, key=lambda e: e.created_at, reverse=True):
            timestamp = entry.created_at.strftime("%m/%d %H:%M") if entry.created_at else ""
            lines.append(f"- [{entry.entry_type}] {timestamp}: {entry.content[:100]}...")

        return "\n".join(lines)

    # ========================================================================
    # Task Integration
    # ========================================================================

    async def create_task(
        self,
        task_type: str,
        description: str,
        delegated_by: str,
        assigned_to: str,
        priority: str = "normal",
        **kwargs
    ) -> str:
        """
        Create a task and add to hot memory.

        Args:
            task_type: Type of task
            description: Task description
            delegated_by: Agent delegating the task
            assigned_to: Agent assigned to task
            priority: Task priority
            **kwargs: Additional task properties

        Returns:
            Task ID
        """
        # Create task in OperationalMemory
        task_id = self.operational_memory.create_task(
            task_type=task_type,
            description=description,
            delegated_by=delegated_by,
            assigned_to=assigned_to,
            priority=priority,
            **kwargs
        )

        # Add to hot memory
        await self.memory_manager.add_entry(
            content=f"Task created: {description} (Priority: {priority})",
            entry_type="task_created",
            tier=MemoryTier.HOT,
            metadata={
                "task_id": task_id,
                "task_type": task_type,
                "assigned_to": assigned_to,
                "priority": priority
            }
        )

        return task_id

    async def claim_task(self) -> Optional[Dict]:
        """
        Claim a pending task and add to hot memory.

        Returns:
            Task dict if successful, None otherwise
        """
        task = self.operational_memory.claim_task(self.agent_name)

        if task:
            # Add to hot memory
            await self.memory_manager.add_entry(
                content=f"Claimed task: {task.get('description', 'Unknown')}",
                entry_type="task_claimed",
                tier=MemoryTier.HOT,
                metadata={
                    "task_id": task.get('id'),
                    "task_type": task.get('type')
                }
            )

        return task

    async def complete_task(
        self,
        task_id: str,
        results: Dict,
        notify_delegator: bool = True
    ) -> bool:
        """
        Complete a task and move to warm memory.

        Args:
            task_id: Task ID to complete
            results: Task results
            notify_delegator: Whether to notify delegator

        Returns:
            True if successful
        """
        success = self.operational_memory.complete_task(
            task_id=task_id,
            results=results,
            notify_delegator=notify_delegator
        )

        if success:
            # Move to warm memory
            await self.memory_manager.add_entry(
                content=f"Completed task {task_id}: {str(results)[:200]}",
                entry_type="task_completed",
                tier=MemoryTier.WARM,
                metadata={"task_id": task_id, "results": results}
            )

        return success

    # ========================================================================
    # Notification Integration
    # ========================================================================

    async def create_notification(
        self,
        target_agent: str,
        notification_type: str,
        summary: str,
        task_id: Optional[str] = None
    ) -> str:
        """
        Create a notification for another agent.

        Args:
            target_agent: Agent to notify
            notification_type: Type of notification
            summary: Notification summary
            task_id: Associated task ID

        Returns:
            Notification ID
        """
        notification_id = self.operational_memory.create_notification(
            agent=target_agent,
            type=notification_type,
            summary=summary,
            task_id=task_id
        )

        return notification_id

    async def get_notifications(self, unread_only: bool = True) -> List[Dict]:
        """
        Get notifications for this agent.

        Args:
            unread_only: Only return unread notifications

        Returns:
            List of notification dicts
        """
        return self.operational_memory.get_notifications(
            agent=self.agent_name,
            unread_only=unread_only
        )

    async def mark_notification_read(self, notification_id: str) -> bool:
        """
        Mark a notification as read.

        Args:
            notification_id: Notification ID

        Returns:
            True if successful
        """
        return self.operational_memory.mark_notification_read(notification_id)

    # ========================================================================
    # Archive Queries
    # ========================================================================

    async def search_archive(
        self,
        query_text: Optional[str] = None,
        entry_type: Optional[str] = None,
        days: int = 30,
        limit: int = 10
    ) -> List[Dict]:
        """
        Search archive tier.

        Args:
            query_text: Text to search for
            entry_type: Entry type filter
            days: Days back to search
            limit: Maximum results

        Returns:
            List of matching entries
        """
        return await self.memory_manager.query_archive(
            query_text=query_text,
            entry_type=entry_type,
            days=days,
            limit=limit
        )

    async def get_related_knowledge(
        self,
        entry_id: str,
        max_depth: int = 2,
        limit: int = 10
    ) -> List[Dict]:
        """
        Get related knowledge through graph traversal.

        Args:
            entry_id: Starting entry ID
            max_depth: Maximum traversal depth
            limit: Maximum results

        Returns:
            List of related entries
        """
        # This would use Neo4j graph traversal
        # For now, return empty list
        return []

    # ========================================================================
    # Memory Management
    # ========================================================================

    async def add_memory(
        self,
        content: str,
        entry_type: str,
        tier: MemoryTier = MemoryTier.HOT,
        confidence: float = 1.0,
        metadata: Optional[Dict] = None
    ) -> str:
        """
        Add a memory entry.

        Args:
            content: Entry content
            entry_type: Type of entry
            tier: Target tier
            confidence: Confidence level
            metadata: Optional metadata

        Returns:
            Entry ID
        """
        return await self.memory_manager.add_entry(
            content=content,
            entry_type=entry_type,
            tier=tier,
            confidence=confidence,
            metadata=metadata
        )

    async def refresh(self) -> None:
        """Refresh all memory tiers."""
        await self.memory_manager.refresh()
        self._last_context = None
        self._last_context_time = None

    async def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics."""
        memory_stats = await self.memory_manager.get_stats()

        # Get OperationalMemory stats
        op_health = self.operational_memory.health_check()

        return {
            "agent": self.agent_name,
            "memory_manager": {
                "hot": {
                    "entries": memory_stats.hot.entry_count,
                    "tokens": memory_stats.hot.token_count,
                    "utilization": memory_stats.hot.utilization
                },
                "warm": {
                    "entries": memory_stats.warm.entry_count,
                    "tokens": memory_stats.warm.token_count,
                    "loaded": self.memory_manager._warm_loaded
                },
                "cold": {
                    "entries": memory_stats.cold.entry_count,
                    "tokens": memory_stats.cold.token_count,
                    "loaded": self.memory_manager._cold_loaded
                }
            },
            "operational_memory": op_health,
            "neo4j_available": memory_stats.neo4j_available
        }

    async def close(self) -> None:
        """Close all memory connections."""
        await self.memory_manager.close()


# ============================================================================
# Factory and Convenience Functions
# ============================================================================

class IntegratedMemoryFactory:
    """Factory for creating IntegratedMemoryManager instances."""

    _instances: Dict[str, IntegratedMemoryManager] = {}
    _lock = asyncio.Lock()

    @classmethod
    async def get_manager(
        cls,
        agent_name: str,
        operational_memory: OperationalMemory,
        **kwargs
    ) -> IntegratedMemoryManager:
        """
        Get or create an IntegratedMemoryManager.

        Args:
            agent_name: Name of the agent
            operational_memory: OperationalMemory instance
            **kwargs: Additional arguments

        Returns:
            IntegratedMemoryManager instance
        """
        async with cls._lock:
            if agent_name not in cls._instances:
                manager = IntegratedMemoryManager(
                    agent_name=agent_name,
                    operational_memory=operational_memory,
                    **kwargs
                )
                await manager.initialize()
                cls._instances[agent_name] = manager

            return cls._instances[agent_name]

    @classmethod
    async def close_all(cls) -> None:
        """Close all integrated memory managers."""
        async with cls._lock:
            for manager in cls._instances.values():
                await manager.close()
            cls._instances.clear()


async def create_integrated_memory(
    agent_name: str,
    neo4j_uri: str = "bolt://localhost:7687",
    neo4j_username: str = "neo4j",
    neo4j_password: Optional[str] = None,
    enable_warm_tier: bool = True,
    enable_cold_tier: bool = False
) -> IntegratedMemoryManager:
    """
    Create an IntegratedMemoryManager with new OperationalMemory.

    Args:
        agent_name: Name of the agent
        neo4j_uri: Neo4j URI
        neo4j_username: Neo4j username
        neo4j_password: Neo4j password
        enable_warm_tier: Enable warm tier
        enable_cold_tier: Enable cold tier

    Returns:
        Initialized IntegratedMemoryManager
    """
    # Create OperationalMemory
    op_memory = OperationalMemory(
        uri=neo4j_uri,
        username=neo4j_username,
        password=neo4j_password,
        fallback_mode=True
    )

    # Create integrated manager
    manager = IntegratedMemoryManager(
        agent_name=agent_name,
        operational_memory=op_memory,
        enable_warm_tier=enable_warm_tier,
        enable_cold_tier=enable_cold_tier
    )

    await manager.initialize()
    return manager


# ============================================================================
# Agent-Specific Configurations
# ============================================================================

AGENT_MEMORY_CONFIG = {
    "kublai": {
        "enable_warm_tier": True,
        "enable_cold_tier": True,
        "description": "Squad lead - needs full context for orchestration"
    },
    "mongke": {
        "enable_warm_tier": True,
        "enable_cold_tier": False,
        "description": "Researcher - needs recent context for deep research"
    },
    "chagatai": {
        "enable_warm_tier": True,
        "enable_cold_tier": False,
        "description": "Writer - needs recent context for content creation"
    },
    "temujin": {
        "enable_warm_tier": True,
        "enable_cold_tier": True,
        "description": "Developer - may need historical context for technical debt"
    },
    "jochi": {
        "enable_warm_tier": True,
        "enable_cold_tier": True,
        "description": "Analyst - needs historical data for pattern recognition"
    },
    "ogedei": {
        "enable_warm_tier": True,
        "enable_cold_tier": False,
        "description": "Operations - needs recent context for process management"
    }
}


async def get_agent_memory(
    agent_name: str,
    operational_memory: OperationalMemory
) -> IntegratedMemoryManager:
    """
    Get memory manager with agent-specific configuration.

    Args:
        agent_name: Name of the agent
        operational_memory: OperationalMemory instance

    Returns:
        Configured IntegratedMemoryManager
    """
    config = AGENT_MEMORY_CONFIG.get(agent_name, {
        "enable_warm_tier": True,
        "enable_cold_tier": False
    })

    return await IntegratedMemoryFactory.get_manager(
        agent_name=agent_name,
        operational_memory=operational_memory,
        **config
    )


# ============================================================================
# Example Usage
# ============================================================================

if __name__ == "__main__":
    import os

    async def example():
        """Example usage of IntegratedMemoryManager."""
        logging.basicConfig(level=logging.INFO)

        print("IntegratedMemoryManager Example")
        print("=" * 50)

        # Get credentials
        neo4j_uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        neo4j_password = os.environ.get("NEO4J_PASSWORD")

        # Create integrated memory for Kublai
        memory = await create_integrated_memory(
            agent_name="kublai",
            neo4j_uri=neo4j_uri,
            neo4j_password=neo4j_password,
            enable_warm_tier=True,
            enable_cold_tier=True
        )

        # Get memory context as Markdown
        context = await memory.get_memory_markdown(max_tokens=2000)
        print(f"\nMemory Context:\n{context}")

        # Create a task
        task_id = await memory.create_task(
            task_type="research",
            description="Research async patterns in Python",
            delegated_by="kublai",
            assigned_to="mongke",
            priority="high"
        )
        print(f"\nCreated task: {task_id}")

        # Get stats
        stats = await memory.get_stats()
        print(f"\nMemory Stats: {stats}")

        # Close
        await memory.close()

    asyncio.run(example())
