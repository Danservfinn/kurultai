"""
Memory Tools Module

Tool functions that wrap OperationalMemory methods for use by agents.
All functions use environment variables for Neo4j configuration.

Environment Variables:
    NEO4J_URI: Neo4j bolt URI (default: bolt://localhost:7687)
    NEO4J_USER: Neo4j username (default: neo4j)
    NEO4J_PASSWORD: Neo4j password (default: password)
    NEO4J_DATABASE: Neo4j database name (default: neo4j)
"""

import os
import logging
from typing import Dict, List, Optional, Any
from functools import wraps

# Import OperationalMemory from the parent directory
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from openclaw_memory import OperationalMemory

# Configure logging
logger = logging.getLogger(__name__)

# =============================================================================
# Configuration
# =============================================================================

def _get_neo4j_config() -> Dict[str, Any]:
    """
    Get Neo4j configuration from environment variables.

    Returns:
        Dictionary with Neo4j connection settings

    Raises:
        ValueError: If NEO4J_PASSWORD environment variable is not set
    """
    password = os.getenv("NEO4J_PASSWORD")
    if password is None:
        raise ValueError(
            "NEO4J_PASSWORD environment variable is required. "
            "Please set it before initializing the memory tools."
        )

    return {
        "uri": os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        "username": os.getenv("NEO4J_USER", "neo4j"),
        "password": password,
        "database": os.getenv("NEO4J_DATABASE", "neo4j"),
        "fallback_mode": True,
    }

# Global memory instance (lazy initialization)
_memory_instance: Optional[OperationalMemory] = None

def _get_memory() -> OperationalMemory:
    """
    Get or create the OperationalMemory singleton instance.

    Returns:
        OperationalMemory instance
    """
    global _memory_instance
    if _memory_instance is None:
        config = _get_neo4j_config()
        _memory_instance = OperationalMemory(**config)
        logger.debug(f"OperationalMemory initialized: {config['uri']}")
    return _memory_instance

# =============================================================================
# Decorators
# =============================================================================

def _log_tool_usage(func):
    """Decorator to log tool usage."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            result = func(*args, **kwargs)
            logger.debug(f"Tool {func.__name__} executed successfully")
            return result
        except Exception as e:
            logger.error(f"Tool {func.__name__} failed: {e}")
            raise
    return wrapper

def _handle_errors(default_return=None):
    """Decorator to handle errors gracefully."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in {func.__name__}: {e}")
                return default_return
        return wrapper
    return decorator

# =============================================================================
# Task Management Tools
# =============================================================================

@_log_tool_usage
@_handle_errors(default_return=None)
def create_task(
    delegated_by: str,
    assigned_to: str,
    task_type: str,
    description: str,
    priority: str = "normal"
) -> Optional[str]:
    """
    Tool: Create a new task. Returns task ID.

    Args:
        delegated_by: Agent that delegated the task
        assigned_to: Agent assigned to the task (or 'any' for unassigned)
        task_type: Type of task (e.g., 'code_review', 'deploy')
        description: Task description
        priority: Task priority ('low', 'normal', 'high', 'critical')

    Returns:
        Task ID string if successful, None otherwise

    Example:
        >>> task_id = create_task(
        ...     delegated_by="main",
        ...     assigned_to="developer",
        ...     task_type="code_review",
        ...     description="Review authentication module",
        ...     priority="high"
        ... )
        >>> print(f"Created task: {task_id}")
    """
    memory = _get_memory()
    task_id = memory.create_task(
        task_type=task_type,
        description=description,
        delegated_by=delegated_by,
        assigned_to=assigned_to,
        priority=priority
    )
    logger.info(f"Task created: {task_id} (type: {task_type}, assigned_to: {assigned_to})")
    return task_id

@_log_tool_usage
@_handle_errors(default_return=None)
def claim_task(agent: str) -> Optional[Dict]:
    """
    Tool: Claim a pending task. Returns task or None.

    Args:
        agent: Agent claiming the task

    Returns:
        Task dict if successful, None if no tasks available

    Example:
        >>> task = claim_task("developer")
        >>> if task:
        ...     print(f"Claimed task: {task['id']}")
        ... else:
        ...     print("No pending tasks")
    """
    memory = _get_memory()
    try:
        task = memory.claim_task(agent)
        if task:
            logger.info(f"Task claimed: {task['id']} by {agent}")
        return task
    except Exception as e:
        if "No pending tasks" in str(e):
            logger.info(f"No pending tasks available for {agent}")
            return None
        raise

@_log_tool_usage
@_handle_errors(default_return=False)
def complete_task(task_id: str, results: Dict, notify_delegator: bool = True) -> bool:
    """
    Tool: Complete a task with results.

    Args:
        task_id: Task ID to complete
        results: Task results dictionary
        notify_delegator: Whether to create notification for delegator

    Returns:
        True if successful, False otherwise

    Example:
        >>> success = complete_task(
        ...     task_id="task-123",
        ...     results={"approved": True, "comments": "Looks good!"},
        ...     notify_delegator=True
        ... )
        >>> print(f"Task completed: {success}")
    """
    memory = _get_memory()
    success = memory.complete_task(
        task_id=task_id,
        results=results,
        notify_delegator=notify_delegator
    )
    if success:
        logger.info(f"Task completed: {task_id}")
    else:
        logger.warning(f"Failed to complete task: {task_id}")
    return success

@_log_tool_usage
@_handle_errors(default_return=None)
def get_task_status(task_id: str) -> Optional[Dict]:
    """
    Tool: Get current status of a task.

    Args:
        task_id: Task ID to retrieve

    Returns:
        Task dict if found, None otherwise

    Example:
        >>> status = get_task_status("task-123")
        >>> if status:
        ...     print(f"Task status: {status['status']}")
    """
    memory = _get_memory()
    return memory.get_task(task_id)

@_log_tool_usage
@_handle_errors(default_return=False)
def fail_task(task_id: str, error_message: str) -> bool:
    """
    Tool: Mark a task as failed with error message.

    Args:
        task_id: Task ID to fail
        error_message: Error message describing the failure

    Returns:
        True if successful, False otherwise

    Example:
        >>> success = fail_task(
        ...     task_id="task-123",
        ...     error_message="Build failed due to missing dependency"
        ... )
        >>> print(f"Task marked as failed: {success}")
    """
    memory = _get_memory()
    success = memory.fail_task(task_id, error_message)
    if success:
        logger.info(f"Task failed: {task_id}")
    else:
        logger.warning(f"Failed to mark task as failed: {task_id}")
    return success

@_log_tool_usage
@_handle_errors(default_return=[])
def list_pending_tasks(agent: Optional[str] = None) -> List[Dict]:
    """
    Tool: List pending tasks, optionally filtered by agent.

    Args:
        agent: Filter by assigned agent (None for all)

    Returns:
        List of task dicts

    Example:
        >>> tasks = list_pending_tasks(agent="developer")
        >>> print(f"Pending tasks: {len(tasks)}")
    """
    memory = _get_memory()
    return memory.list_pending_tasks(agent)

# =============================================================================
# Notification Tools
# =============================================================================

@_log_tool_usage
@_handle_errors(default_return=None)
def create_notification(
    agent: str,
    type: str,
    summary: str,
    task_id: Optional[str] = None
) -> Optional[str]:
    """
    Tool: Create a notification for an agent.

    Args:
        agent: Agent to notify
        type: Notification type (e.g., 'task_completed', 'task_failed')
        summary: Notification summary
        task_id: Associated task ID (optional)

    Returns:
        Notification ID if successful, None otherwise

    Example:
        >>> notif_id = create_notification(
        ...     agent="main",
        ...     type="task_completed",
        ...     summary="Code review completed successfully",
        ...     task_id="task-123"
        ... )
        >>> print(f"Created notification: {notif_id}")
    """
    memory = _get_memory()
    notification_id = memory.create_notification(
        agent=agent,
        type=type,
        summary=summary,
        task_id=task_id
    )
    logger.info(f"Notification created: {notification_id} for {agent}")
    return notification_id

@_log_tool_usage
@_handle_errors(default_return=[])
def get_my_notifications(agent: str, unread_only: bool = True) -> List[Dict]:
    """
    Tool: Get notifications for calling agent.

    Args:
        agent: Agent to get notifications for
        unread_only: If True, only return unread notifications

    Returns:
        List of notification dicts

    Example:
        >>> notifications = get_my_notifications("developer", unread_only=True)
        >>> print(f"Unread notifications: {len(notifications)}")
    """
    memory = _get_memory()
    return memory.get_notifications(agent, unread_only=unread_only)

@_log_tool_usage
@_handle_errors(default_return=False)
def mark_notification_read(notification_id: str) -> bool:
    """
    Tool: Mark a notification as read.

    Args:
        notification_id: Notification ID to mark as read

    Returns:
        True if successful, False otherwise

    Example:
        >>> success = mark_notification_read("notif-123")
        >>> print(f"Notification marked as read: {success}")
    """
    memory = _get_memory()
    success = memory.mark_notification_read(notification_id)
    if success:
        logger.debug(f"Notification marked read: {notification_id}")
    return success

@_log_tool_usage
@_handle_errors(default_return=0)
def mark_all_notifications_read(agent: str) -> int:
    """
    Tool: Mark all notifications as read for an agent.

    Args:
        agent: Agent to mark notifications for

    Returns:
        Number of notifications marked as read

    Example:
        >>> count = mark_all_notifications_read("developer")
        >>> print(f"Marked {count} notifications as read")
    """
    memory = _get_memory()
    count = memory.mark_all_notifications_read(agent)
    logger.info(f"Marked {count} notifications as read for {agent}")
    return count

# =============================================================================
# Rate Limit Tools
# =============================================================================

@_log_tool_usage
@_handle_errors(default_return={"allowed": True, "count": 0, "reset_time": 0})
def check_rate_limit(agent: str, operation: str, max_requests: int = 1000) -> Dict:
    """
    Tool: Check if operation is within rate limit.

    Args:
        agent: Agent making the request
        operation: Operation type being rate limited
        max_requests: Maximum requests per hour

    Returns:
        Dictionary with:
            - allowed: True if within limit
            - count: Current request count
            - reset_time: Unix timestamp when bucket resets

    Example:
        >>> result = check_rate_limit("developer", "api_call", max_requests=100)
        >>> print(f"Allowed: {result['allowed']}, Count: {result['count']}")
    """
    memory = _get_memory()
    allowed, count, reset_time = memory.check_rate_limit(agent, operation, max_requests)
    return {
        "allowed": allowed,
        "count": count,
        "reset_time": reset_time
    }

@_log_tool_usage
@_handle_errors(default_return=False)
def record_operation(agent: str, operation: str) -> bool:
    """
    Tool: Record an operation for rate limiting.

    Args:
        agent: Agent making the request
        operation: Operation type

    Returns:
        True if successful, False otherwise

    Example:
        >>> success = record_operation("developer", "api_call")
        >>> print(f"Operation recorded: {success}")
    """
    memory = _get_memory()
    success = memory.record_rate_limit_hit(agent, operation)
    if success:
        logger.debug(f"Rate limit hit recorded: {agent}/{operation}")
    return success

# =============================================================================
# Agent State Tools
# =============================================================================

@_log_tool_usage
@_handle_errors(default_return=False)
def update_heartbeat(agent: str, status: str = "active") -> bool:
    """
    Tool: Update agent heartbeat.

    Args:
        agent: Agent name
        status: Agent status ('active', 'busy', 'idle', 'offline')

    Returns:
        True if successful, False otherwise

    Example:
        >>> success = update_heartbeat("developer", status="busy")
        >>> print(f"Heartbeat updated: {success}")
    """
    memory = _get_memory()
    success = memory.update_agent_heartbeat(agent, status)
    if success:
        logger.debug(f"Agent heartbeat updated: {agent} ({status})")
    return success

@_log_tool_usage
@_handle_errors(default_return=None)
def get_agent_status(agent: str) -> Optional[Dict]:
    """
    Tool: Get status of any agent.

    Args:
        agent: Agent name

    Returns:
        Agent status dict if found, None otherwise

    Example:
        >>> status = get_agent_status("developer")
        >>> if status:
        ...     print(f"Last heartbeat: {status['last_heartbeat']}")
    """
    memory = _get_memory()
    return memory.get_agent_status(agent)

@_log_tool_usage
@_handle_errors(default_return=[])
def list_active_agents(inactive_threshold_seconds: int = 300) -> List[Dict]:
    """
    Tool: List all active agents.

    Args:
        inactive_threshold_seconds: Consider agent inactive after this many seconds

    Returns:
        List of agent dicts with activity status

    Example:
        >>> agents = list_active_agents()
        >>> print(f"Active agents: {len(agents)}")
    """
    memory = _get_memory()
    return memory.list_active_agents(inactive_threshold_seconds)

@_log_tool_usage
@_handle_errors(default_return=False)
def set_agent_busy(agent: str, busy: bool = True) -> bool:
    """
    Tool: Set agent busy status.

    Args:
        agent: Agent name
        busy: True to mark as busy, False for available

    Returns:
        True if successful, False otherwise

    Example:
        >>> success = set_agent_busy("developer", busy=True)
        >>> print(f"Agent marked as busy: {success}")
    """
    memory = _get_memory()
    success = memory.set_agent_busy(agent, busy)
    if success:
        logger.debug(f"Agent busy status set: {agent} (busy={busy})")
    return success

# =============================================================================
# Health Check Tools
# =============================================================================

@_log_tool_usage
@_handle_errors(default_return={
    "status": "error",
    "connected": False,
    "writable": False,
    "error": "Health check failed"
})
def check_memory_health() -> Dict:
    """
    Tool: Check Neo4j memory system health.

    Returns:
        Health status dict with:
            - status: 'healthy', 'unavailable', 'error', or 'fallback_mode'
            - connected: True if connected to Neo4j
            - writable: True if write operations work
            - response_time_ms: Response time in milliseconds
            - error: Error message if any
            - timestamp: ISO format timestamp

    Example:
        >>> health = check_memory_health()
        >>> print(f"Memory health: {health['status']}")
    """
    memory = _get_memory()
    return memory.health_check()

@_log_tool_usage
@_handle_errors(default_return=False)
def is_memory_healthy() -> bool:
    """
    Tool: Quick health check.

    Returns:
        True if Neo4j is healthy

    Example:
        >>> if is_memory_healthy():
        ...     print("Memory system is healthy")
        ... else:
        ...     print("Memory system is not available")
    """
    memory = _get_memory()
    return memory.is_healthy()

# =============================================================================
# Utility Tools
# =============================================================================

@_log_tool_usage
@_handle_errors(default_return=[])
def create_indexes() -> List[str]:
    """
    Tool: Create recommended indexes for performance.

    Returns:
        List of created index names

    Example:
        >>> indexes = create_indexes()
        >>> print(f"Created indexes: {indexes}")
    """
    memory = _get_memory()
    return memory.create_indexes()

@_log_tool_usage
def close_memory() -> None:
    """
    Tool: Close the memory connection and release resources.

    This should be called when the application shuts down.

    Example:
        >>> close_memory()
        >>> print("Memory connection closed")
    """
    global _memory_instance
    if _memory_instance:
        _memory_instance.close()
        _memory_instance = None
        logger.info("Memory connection closed")
