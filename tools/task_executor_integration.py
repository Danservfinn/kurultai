"""
Task Execution Integration

This module provides the integration layer between NotionIntegration and TaskExecutor.
It handles the wiring of callbacks and provides a unified interface for task management.

Usage:
    # Simple setup - auto-executes Notion tasks
    from tools.notion_integration import NotionIntegration
    from tools.task_executor_integration import TaskExecutionPipeline
    
    memory = OperationalMemory(...)
    pipeline = TaskExecutionPipeline(memory)
    pipeline.start()  # Tasks from Notion now auto-execute

    # Advanced setup with custom configuration
    pipeline = TaskExecutionPipeline(
        memory=memory,
        agent_mapping={
            'security_audit': 'jochi',
            'performance_opt': 'jochi',
            'refactor': 'temujin',
        },
        max_retries=5,
        auto_approve_high_priority=True
    )
"""

import logging
from typing import Any, Callable, Dict, List, Optional

from tools.notion_integration import NotionIntegration, NotionTask
from tools.task_executor import (
    TaskExecutor,
    TaskExecutorConfig,
    integrate_with_notion,
)

logger = logging.getLogger(__name__)


class TaskExecutionPipeline:
    """
    Unified pipeline integrating Notion task polling with agent execution.

    This class provides a high-level interface that:
    1. Polls Notion for new tasks
    2. Creates Neo4j tasks
    3. Maps tasks to appropriate agents
    4. Spawns agent sessions
    5. Tracks execution status
    6. Syncs completion back to Notion

    Example:
        >>> memory = OperationalMemory(...)
        >>> pipeline = TaskExecutionPipeline(memory)
        >>> pipeline.start()
        >>> # Tasks from Notion are now automatically executed
    """

    def __init__(
        self,
        memory,
        notion_api_key: Optional[str] = None,
        notion_database_id: Optional[str] = None,
        agent_mapping: Optional[Dict[str, str]] = None,
        max_retries: int = 3,
        poll_interval: int = 60,
        auto_approve_high_priority: bool = True,
        on_task_complete: Optional[Callable[[str, str], None]] = None,
        on_task_fail: Optional[Callable[[str, str, str], None]] = None,
    ):
        """
        Initialize the task execution pipeline.

        Args:
            memory: OperationalMemory instance
            notion_api_key: Notion API key (or use env NOTION_TOKEN)
            notion_database_id: Notion database ID (or use env NOTION_TASK_DATABASE_ID)
            agent_mapping: Custom task type -> agent mapping
            max_retries: Maximum retry attempts for failed tasks
            poll_interval: Seconds between polling cycles
            auto_approve_high_priority: Auto-execute high priority tasks
            on_task_complete: Callback(task_id, summary) on completion
            on_task_fail: Callback(task_id, error_type, message) on failure
        """
        self.memory = memory
        self.auto_approve_high_priority = auto_approve_high_priority

        # Create NotionIntegration
        self.notion = NotionIntegration(
            memory=memory,
            api_key=notion_api_key,
            database_id=notion_database_id,
            poll_interval_seconds=poll_interval
        )

        # Create config with optional custom mapping
        config = TaskExecutorConfig(
            max_retries=max_retries,
            poll_interval_seconds=poll_interval
        )
        if agent_mapping:
            config.agent_mapping.update(agent_mapping)

        # Create TaskExecutor
        self.executor = TaskExecutor(
            memory=memory,
            notion_integration=self.notion,
            config=config
        )

        # Set callbacks
        if on_task_complete or on_task_fail:
            self.executor.set_callbacks(on_task_complete, on_task_fail)

        self._running = False
        logger.info("TaskExecutionPipeline initialized")

    def start(self) -> None:
        """Start the pipeline - begins polling and execution."""
        if self._running:
            logger.warning("Pipeline already running")
            return

        # Start the executor (which also starts Notion polling via callback)
        self.executor.start()

        self._running = True
        logger.info("TaskExecutionPipeline started - tasks will auto-execute")

    def stop(self) -> None:
        """Stop the pipeline."""
        if not self._running:
            return

        self.executor.stop()
        self._running = False
        logger.info("TaskExecutionPipeline stopped")

    def is_running(self) -> bool:
        """Check if pipeline is running."""
        return self._running

    def get_status(self) -> Dict[str, Any]:
        """Get current pipeline status."""
        return {
            'running': self._running,
            'notion_polling': self.notion.is_polling(),
            'executor_stats': self.executor.get_stats(),
            'active_executions': self.executor.get_active_executions(),
        }

    def manually_execute_task(self, task_id: str, agent: Optional[str] = None) -> Optional[str]:
        """
        Manually trigger execution of a task.

        Args:
            task_id: Neo4j task ID
            agent: Optional agent override

        Returns:
            Execution attempt ID if started
        """
        return self.executor.execute_task(task_id, agent)

    def cancel_task(self, attempt_id: str) -> bool:
        """Cancel an active task execution."""
        return self.executor.cancel_execution(attempt_id)

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()
        return False


class TaskRouter:
    """
    Advanced task routing with approval workflows and escalation.

    Extends basic TaskExecutor with approval gates for sensitive operations.
    """

    SENSITIVE_PATTERNS = [
        'delete', 'remove', 'drop', 'purge', 'clean',
        'deploy', 'production', 'prod',
        'password', 'secret', 'key', 'credential',
        'payment', 'billing', 'transaction',
    ]

    def __init__(
        self,
        executor: TaskExecutor,
        require_approval_for: Optional[List[str]] = None,
        approval_timeout_minutes: int = 60,
    ):
        """
        Initialize task router.

        Args:
            executor: TaskExecutor instance
            require_approval_for: List of task patterns requiring approval
            approval_timeout_minutes: How long to wait for approval
        """
        self.executor = executor
        self.approval_patterns = require_approval_for or self.SENSITIVE_PATTERNS
        self.approval_timeout = approval_timeout_minutes
        self._pending_approvals: Dict[str, Dict[str, Any]] = {}

    def route_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Route a task with approval check.

        Args:
            task: Task dictionary

        Returns:
            Routing result with action taken
        """
        task_id = task.get('id')
        description = task.get('description', '').lower()
        task_type = task.get('type', '').lower()
        priority = task.get('priority', 'normal')

        # Check if approval is needed
        needs_approval = any(
            pattern in description or pattern in task_type
            for pattern in self.approval_patterns
        )

        if needs_approval:
            # Queue for approval
            self._pending_approvals[task_id] = {
                'task': task,
                'requested_at': __import__('datetime').datetime.now(),
                'auto_approve_by': __import__('datetime').datetime.now() + 
                    __import__('datetime').timedelta(minutes=self.approval_timeout)
            }

            return {
                'action': 'pending_approval',
                'task_id': task_id,
                'reason': 'Sensitive operation detected',
                'auto_approve_at': self._pending_approvals[task_id]['auto_approve_by'].isoformat()
            }

        # Auto-route to executor
        attempt_id = self.executor.execute_task(task_id)

        return {
            'action': 'executed',
            'task_id': task_id,
            'attempt_id': attempt_id,
        }

    def approve_task(self, task_id: str) -> Optional[str]:
        """
        Approve a pending task.

        Args:
            task_id: Task ID to approve

        Returns:
            Execution attempt ID if started
        """
        if task_id not in self._pending_approvals:
            return None

        del self._pending_approvals[task_id]
        return self.executor.execute_task(task_id)

    def get_pending_approvals(self) -> List[Dict[str, Any]]:
        """Get list of tasks pending approval."""
        now = __import__('datetime').datetime.now()
        return [
            {
                'task_id': task_id,
                'description': info['task'].get('description', 'No description'),
                'requested_at': info['requested_at'].isoformat(),
                'auto_approve_at': info['auto_approve_by'].isoformat(),
                'expires_in_minutes': max(0, int((info['auto_approve_by'] - now).total_seconds() / 60))
            }
            for task_id, info in self._pending_approvals.items()
        ]


# =============================================================================
# Quick Start Functions
# =============================================================================

def start_auto_execution(
    memory,
    notion_api_key: Optional[str] = None,
    notion_database_id: Optional[str] = None,
) -> TaskExecutionPipeline:
    """
    Quick start function to begin auto-executing Notion tasks.

    Args:
        memory: OperationalMemory instance
        notion_api_key: Notion API key
        notion_database_id: Notion database ID

    Returns:
        Started TaskExecutionPipeline

    Example:
        >>> from openclaw_memory import OperationalMemory
        >>> memory = OperationalMemory(...)
        >>> pipeline = start_auto_execution(memory)
        >>> # Leave running - tasks will auto-execute
    """
    pipeline = TaskExecutionPipeline(
        memory=memory,
        notion_api_key=notion_api_key,
        notion_database_id=notion_database_id
    )
    pipeline.start()
    return pipeline


def create_execution_context(
    task_id: str,
    agent: str,
    task_type: str,
    description: str,
    priority: str = 'normal',
    notion_url: Optional[str] = None,
    additional_context: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Create a standardized execution context for agent sessions.

    Args:
        task_id: Task ID
        agent: Agent identifier
        task_type: Type of task
        description: Task description
        priority: Task priority
        notion_url: Optional Notion URL
        additional_context: Additional context dict

    Returns:
        Execution context dictionary
    """
    return {
        'task_id': task_id,
        'agent': agent,
        'task_type': task_type,
        'description': description,
        'priority': priority,
        'notion_url': notion_url,
        'context': additional_context or {},
        'created_at': __import__('datetime').datetime.now().isoformat(),
    }
