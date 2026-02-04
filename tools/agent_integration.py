"""
Agent Integration Module

Helper class for agents to integrate with the operational memory system.
Provides convenience methods for common operations.

Environment Variables:
    NEO4J_URI: Neo4j bolt URI (default: bolt://localhost:7687)
    NEO4J_USER: Neo4j username (default: neo4j)
    NEO4J_PASSWORD: Neo4j password (default: password)
    NEO4J_DATABASE: Neo4j database name (default: neo4j)
"""

import os
import logging
from typing import Dict, List, Optional, Any

# Import OperationalMemory from the parent directory
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from openclaw_memory import OperationalMemory

# Configure logging
logger = logging.getLogger(__name__)


class AgentMemoryIntegration:
    """
    Helper class for agents to integrate with operational memory.

    This class provides a convenient interface for agents to interact with
    the operational memory system, handling connection management and
    providing agent-specific convenience methods.

    Attributes:
        agent_id: The ID of the agent using this integration
        memory: The OperationalMemory instance

    Example:
        >>> memory = AgentMemoryIntegration("developer")
        >>> task = memory.claim_next_task()
        >>> if task:
        ...     # Do work...
        ...     memory.complete_and_notify(task['id'], {"approved": True})
    """

    def __init__(self, agent_id: str):
        """
        Initialize with agent ID.

        Args:
            agent_id: The unique identifier for this agent

        Example:
            >>> memory = AgentMemoryIntegration("developer")
            >>> print(f"Initialized for agent: {memory.agent_id}")
        """
        self.agent_id = agent_id
        self._memory = self._create_memory_instance()
        logger.debug(f"AgentMemoryIntegration initialized for agent: {agent_id}")

    def _create_memory_instance(self) -> OperationalMemory:
        """
        Create OperationalMemory instance from environment variables.

        Returns:
            Configured OperationalMemory instance
        """
        config = {
            "uri": os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            "username": os.getenv("NEO4J_USER", "neo4j"),
            "password": os.getenv("NEO4J_PASSWORD", "password"),
            "database": os.getenv("NEO4J_DATABASE", "neo4j"),
            "fallback_mode": True,
        }
        return OperationalMemory(**config)

    # ========================================================================
    # Task Management
    # ========================================================================

    def create_and_delegate(
        self,
        to_agent: str,
        task_type: str,
        description: str,
        priority: str = "normal",
        **kwargs
    ) -> Optional[str]:
        """
        Create task and return task ID for agent-to-agent delegation.

        Args:
            to_agent: Agent to assign the task to
            task_type: Type of task (e.g., 'code_review', 'deploy')
            description: Task description
            priority: Task priority ('low', 'normal', 'high', 'critical')
            **kwargs: Additional task properties

        Returns:
            Task ID if successful, None otherwise

        Example:
            >>> memory = AgentMemoryIntegration("main")
            >>> task_id = memory.create_and_delegate(
            ...     to_agent="developer",
            ...     task_type="implement_feature",
            ...     description="Implement user authentication",
            ...     priority="high"
            ... )
            >>> print(f"Delegated task: {task_id}")
        """
        try:
            task_id = self._memory.create_task(
                task_type=task_type,
                description=description,
                delegated_by=self.agent_id,
                assigned_to=to_agent,
                priority=priority,
                **kwargs
            )
            logger.info(
                f"Task delegated by {self.agent_id} to {to_agent}: "
                f"{task_id} (type: {task_type})"
            )
            return task_id
        except Exception as e:
            logger.error(f"Failed to delegate task: {e}")
            return None

    def claim_next_task(self) -> Optional[Dict]:
        """
        Claim next pending task for this agent.

        Returns:
            Task dict if successful, None if no tasks available

        Example:
            >>> memory = AgentMemoryIntegration("developer")
            >>> task = memory.claim_next_task()
            >>> if task:
            ...     print(f"Claimed: {task['description']}")
            ... else:
            ...     print("No tasks available")
        """
        try:
            task = self._memory.claim_task(self.agent_id)
            if task:
                logger.info(f"Agent {self.agent_id} claimed task: {task['id']}")
            else:
                logger.debug(f"No pending tasks for {self.agent_id}")
            return task
        except Exception as e:
            if "No pending tasks" in str(e):
                logger.debug(f"No pending tasks for {self.agent_id}")
                return None
            logger.error(f"Failed to claim task: {e}")
            return None

    def complete_and_notify(self, task_id: str, results: Dict) -> bool:
        """
        Complete task and notify delegator.

        Args:
            task_id: Task ID to complete
            results: Task results dictionary

        Returns:
            True if successful, False otherwise

        Example:
            >>> memory = AgentMemoryIntegration("developer")
            >>> success = memory.complete_and_notify(
            ...     task_id="task-123",
            ...     results={"approved": True, "comments": "LGTM"}
            ... )
            >>> print(f"Completed: {success}")
        """
        try:
            success = self._memory.complete_task(
                task_id=task_id,
                results=results,
                notify_delegator=True
            )
            if success:
                logger.info(f"Agent {self.agent_id} completed task: {task_id}")
            else:
                logger.warning(f"Failed to complete task: {task_id}")
            return success
        except Exception as e:
            logger.error(f"Failed to complete task: {e}")
            return False

    def fail_and_notify(self, task_id: str, error_message: str) -> bool:
        """
        Mark task as failed and notify delegator.

        Args:
            task_id: Task ID to fail
            error_message: Error message describing the failure

        Returns:
            True if successful, False otherwise

        Example:
            >>> memory = AgentMemoryIntegration("developer")
            >>> success = memory.fail_and_notify(
            ...     task_id="task-123",
            ...     error_message="Build failed due to syntax error"
            ... )
            >>> print(f"Marked as failed: {success}")
        """
        try:
            success = self._memory.fail_task(task_id, error_message)
            if success:
                logger.info(f"Agent {self.agent_id} marked task as failed: {task_id}")
            else:
                logger.warning(f"Failed to mark task as failed: {task_id}")
            return success
        except Exception as e:
            logger.error(f"Failed to mark task as failed: {e}")
            return False

    def get_task(self, task_id: str) -> Optional[Dict]:
        """
        Get task by ID.

        Args:
            task_id: Task ID to retrieve

        Returns:
            Task dict if found, None otherwise

        Example:
            >>> memory = AgentMemoryIntegration("developer")
            >>> task = memory.get_task("task-123")
            >>> if task:
            ...     print(f"Status: {task['status']}")
        """
        try:
            return self._memory.get_task(task_id)
        except Exception as e:
            logger.error(f"Failed to get task: {e}")
            return None

    def list_my_pending_tasks(self) -> List[Dict]:
        """
        List pending tasks assigned to this agent.

        Returns:
            List of task dicts

        Example:
            >>> memory = AgentMemoryIntegration("developer")
            >>> tasks = memory.list_my_pending_tasks()
            >>> print(f"Pending tasks: {len(tasks)}")
        """
        try:
            return self._memory.list_pending_tasks(agent=self.agent_id)
        except Exception as e:
            logger.error(f"Failed to list pending tasks: {e}")
            return []

    def list_my_in_progress_tasks(self) -> List[Dict]:
        """
        List in-progress tasks claimed by this agent.

        Returns:
            List of task dicts

        Example:
            >>> memory = AgentMemoryIntegration("developer")
            >>> tasks = memory.list_my_in_progress_tasks()
            >>> print(f"In-progress tasks: {len(tasks)}")
        """
        try:
            return self._memory.list_tasks_by_status(
                status="in_progress",
                agent=self.agent_id
            )
        except Exception as e:
            logger.error(f"Failed to list in-progress tasks: {e}")
            return []

    # ========================================================================
    # Notification Management
    # ========================================================================

    def get_my_notifications(self, unread_only: bool = True) -> List[Dict]:
        """
        Get notifications for this agent.

        Args:
            unread_only: If True, only return unread notifications

        Returns:
            List of notification dicts

        Example:
            >>> memory = AgentMemoryIntegration("developer")
            >>> notifications = memory.get_my_notifications(unread_only=True)
            >>> for n in notifications:
            ...     print(f"- {n['summary']}")
        """
        try:
            return self._memory.get_notifications(
                agent=self.agent_id,
                unread_only=unread_only
            )
        except Exception as e:
            logger.error(f"Failed to get notifications: {e}")
            return []

    def send_notification(self, to_agent: str, type: str, summary: str) -> Optional[str]:
        """
        Send notification to another agent.

        Args:
            to_agent: Agent to notify
            type: Notification type (e.g., 'info', 'warning', 'task_completed')
            summary: Notification summary

        Returns:
            Notification ID if successful, None otherwise

        Example:
            >>> memory = AgentMemoryIntegration("developer")
            >>> notif_id = memory.send_notification(
            ...     to_agent="reviewer",
            ...     type="info",
            ...     summary="Code is ready for review"
            ... )
            >>> print(f"Sent notification: {notif_id}")
        """
        try:
            notification_id = self._memory.create_notification(
                agent=to_agent,
                type=type,
                summary=f"[{self.agent_id}] {summary}"
            )
            logger.info(
                f"Notification sent by {self.agent_id} to {to_agent}: "
                f"{notification_id}"
            )
            return notification_id
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
            return None

    def mark_notification_read(self, notification_id: str) -> bool:
        """
        Mark a notification as read.

        Args:
            notification_id: Notification ID to mark as read

        Returns:
            True if successful, False otherwise

        Example:
            >>> memory = AgentMemoryIntegration("developer")
            >>> success = memory.mark_notification_read("notif-123")
            >>> print(f"Marked as read: {success}")
        """
        try:
            return self._memory.mark_notification_read(notification_id)
        except Exception as e:
            logger.error(f"Failed to mark notification as read: {e}")
            return False

    def mark_all_my_notifications_read(self) -> int:
        """
        Mark all notifications as read for this agent.

        Returns:
            Number of notifications marked as read

        Example:
            >>> memory = AgentMemoryIntegration("developer")
            >>> count = memory.mark_all_my_notifications_read()
            >>> print(f"Marked {count} notifications as read")
        """
        try:
            count = self._memory.mark_all_notifications_read(self.agent_id)
            logger.info(f"Agent {self.agent_id} marked {count} notifications as read")
            return count
        except Exception as e:
            logger.error(f"Failed to mark notifications as read: {e}")
            return 0

    # ========================================================================
    # Rate Limiting
    # ========================================================================

    def check_my_rate_limit(self, operation: str, max_requests: int = 1000) -> Dict:
        """
        Check rate limit for this agent.

        Args:
            operation: Operation type being rate limited
            max_requests: Maximum requests per hour

        Returns:
            Dictionary with:
                - allowed: True if within limit
                - count: Current request count
                - reset_time: Unix timestamp when bucket resets

        Example:
            >>> memory = AgentMemoryIntegration("developer")
            >>> result = memory.check_my_rate_limit("api_call", max_requests=100)
            >>> if not result['allowed']:
            ...     print(f"Rate limit exceeded: {result['count']}/{max_requests}")
        """
        try:
            allowed, count, reset_time = self._memory.check_rate_limit(
                agent=self.agent_id,
                operation=operation,
                max_requests=max_requests
            )
            return {
                "allowed": allowed,
                "count": count,
                "reset_time": reset_time
            }
        except Exception as e:
            logger.error(f"Failed to check rate limit: {e}")
            # Fail open - allow the request
            return {"allowed": True, "count": 0, "reset_time": 0}

    def record_my_operation(self, operation: str) -> bool:
        """
        Record an operation for rate limiting.

        Args:
            operation: Operation type

        Returns:
            True if successful, False otherwise

        Example:
            >>> memory = AgentMemoryIntegration("developer")
            >>> success = memory.record_my_operation("api_call")
            >>> print(f"Operation recorded: {success}")
        """
        try:
            return self._memory.record_rate_limit_hit(self.agent_id, operation)
        except Exception as e:
            logger.error(f"Failed to record operation: {e}")
            return False

    # ========================================================================
    # Agent State
    # ========================================================================

    def update_my_heartbeat(self, status: str = "active") -> bool:
        """
        Update this agent's heartbeat.

        Args:
            status: Agent status ('active', 'busy', 'idle', 'offline')

        Returns:
            True if successful, False otherwise

        Example:
            >>> memory = AgentMemoryIntegration("developer")
            >>> success = memory.update_my_heartbeat(status="busy")
            >>> print(f"Heartbeat updated: {success}")
        """
        try:
            success = self._memory.update_agent_heartbeat(self.agent_id, status)
            if success:
                logger.debug(f"Heartbeat updated for {self.agent_id}: {status}")
            return success
        except Exception as e:
            logger.error(f"Failed to update heartbeat: {e}")
            return False

    def set_my_status(self, status: str) -> bool:
        """
        Set this agent's status.

        Args:
            status: Agent status ('active', 'busy', 'idle', 'offline')

        Returns:
            True if successful, False otherwise

        Example:
            >>> memory = AgentMemoryIntegration("developer")
            >>> success = memory.set_my_status("busy")
            >>> print(f"Status set: {success}")
        """
        return self.update_my_heartbeat(status)

    def set_busy(self, busy: bool = True) -> bool:
        """
        Set this agent's busy status.

        Args:
            busy: True to mark as busy, False for available

        Returns:
            True if successful, False otherwise

        Example:
            >>> memory = AgentMemoryIntegration("developer")
            >>> success = memory.set_busy(True)
            >>> print(f"Marked as busy: {success}")
        """
        try:
            return self._memory.set_agent_busy(self.agent_id, busy)
        except Exception as e:
            logger.error(f"Failed to set busy status: {e}")
            return False

    def get_my_status(self) -> Optional[Dict]:
        """
        Get this agent's status.

        Returns:
            Agent status dict if found, None otherwise

        Example:
            >>> memory = AgentMemoryIntegration("developer")
            >>> status = memory.get_my_status()
            >>> if status:
            ...     print(f"Last heartbeat: {status['last_heartbeat']}")
        """
        try:
            return self._memory.get_agent_status(self.agent_id)
        except Exception as e:
            logger.error(f"Failed to get agent status: {e}")
            return None

    # ========================================================================
    # Health Checks
    # ========================================================================

    def check_health(self) -> Dict:
        """
        Check memory system health.

        Returns:
            Health status dict

        Example:
            >>> memory = AgentMemoryIntegration("developer")
            >>> health = memory.check_health()
            >>> print(f"Memory health: {health['status']}")
        """
        try:
            return self._memory.health_check()
        except Exception as e:
            logger.error(f"Failed to check health: {e}")
            return {
                "status": "error",
                "connected": False,
                "writable": False,
                "error": str(e)
            }

    def is_healthy(self) -> bool:
        """
        Quick health check.

        Returns:
            True if memory system is healthy

        Example:
            >>> memory = AgentMemoryIntegration("developer")
            >>> if memory.is_healthy():
            ...     print("Memory system is healthy")
            ... else:
            ...     print("Memory system is not available")
        """
        try:
            return self._memory.is_healthy()
        except Exception as e:
            logger.error(f"Failed to check health: {e}")
            return False

    # ========================================================================
    # Utility Methods
    # ========================================================================

    def create_indexes(self) -> List[str]:
        """
        Create recommended indexes for performance.

        Returns:
            List of created index names

        Example:
            >>> memory = AgentMemoryIntegration("developer")
            >>> indexes = memory.create_indexes()
            >>> print(f"Created indexes: {indexes}")
        """
        try:
            return self._memory.create_indexes()
        except Exception as e:
            logger.error(f"Failed to create indexes: {e}")
            return []

    def close(self) -> None:
        """
        Close the memory connection and release resources.

        This should be called when the agent shuts down.

        Example:
            >>> memory = AgentMemoryIntegration("developer")
            >>> # ... do work ...
            >>> memory.close()
            >>> print("Memory connection closed")
        """
        try:
            self._memory.close()
            logger.info(f"Memory connection closed for agent: {self.agent_id}")
        except Exception as e:
            logger.error(f"Failed to close memory connection: {e}")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False
