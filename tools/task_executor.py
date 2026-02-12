"""
Task Executor Module

Bridges the gap between Notion task creation and actual agent execution.
Maps task types to specific agents, spawns OpenClaw sessions, and tracks execution.

This module provides:
- Task-to-agent mapping based on task type and content
- OpenClaw session spawning for task execution
- Status tracking and synchronization
- Error handling with retries and escalation
- Integration with NotionIntegration callbacks

Environment Variables:
    TASK_EXECUTOR_MAX_RETRIES: Maximum retry attempts (default: 3)
    TASK_EXECUTOR_RETRY_DELAY_SECONDS: Initial retry delay (default: 30)
    OPENCLAW_SESSIONS_SPAWN_CMD: Command to spawn sessions (default: openclaw sessions_spawn)
"""

import asyncio
import json
import logging
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from uuid import uuid4

# =============================================================================
# Custom JSON Encoder for Neo4j Types
# =============================================================================

class Neo4jJSONEncoder(json.JSONEncoder):
    """
    Custom JSON encoder that handles Neo4j data types.
    
    Neo4j returns DateTime objects that are not JSON serializable by default.
    This encoder converts them to ISO format strings.
    """
    def default(self, obj):
        # Handle Neo4j DateTime objects
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        # Handle Neo4j Date objects
        if hasattr(obj, 'toordinal'):
            return obj.isoformat()
        # Handle datetime objects (fallback)
        if isinstance(obj, datetime):
            return obj.isoformat()
        # Handle timedelta
        if isinstance(obj, timedelta):
            return str(obj)
        # Let the base class handle the rest or raise TypeError
        return super().default(obj)


# Configure logging
logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY_SECONDS = 30
DEFAULT_TASK_POLL_INTERVAL = 30

# Agent mapping configuration
AGENT_MAPPING = {
    # Task type patterns -> agent
    'research': 'mongke',
    'investigate': 'mongke',
    'analyze': 'jochi',
    'audit': 'jochi',
    'write': 'chagatai',
    'document': 'chagatai',
    'compose': 'chagatai',
    'build': 'temujin',
    'develop': 'temujin',
    'code': 'temujin',
    'implement': 'temujin',
    'refactor': 'temujin',
    'fix': 'temujin',
    'ops': 'ogedei',
    'deploy': 'ogedei',
    'monitor': 'ogedei',
    'maintain': 'ogedei',
    'orchestrate': 'kublai',
    'coordinate': 'kublai',
    'review': 'kublai',
    'default': 'main',
}

# Error types that warrant immediate retry vs escalation
RETRYABLE_ERRORS = [
    'timeout_error',
    'connection_error',
    'api_error',
    'rate_limit',
]

NON_RETRYABLE_ERRORS = [
    'syntax_error',
    'type_error',
    'import_error',
    'permission_error',
]


class TaskStatus(Enum):
    """Task execution status."""
    PENDING = "pending"
    ASSIGNED = "assigned"
    CLAIMED = "claimed"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class TaskAssignment:
    """Represents a task assignment to an agent."""
    task_id: str
    agent: str
    assigned_at: datetime
    expires_at: Optional[datetime] = None
    claimed_by: Optional[str] = None
    claimed_at: Optional[datetime] = None


@dataclass
class ExecutionAttempt:
    """Represents a single execution attempt."""
    id: str
    task_id: str
    agent: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: TaskStatus = TaskStatus.PENDING
    error_message: Optional[str] = None
    error_type: Optional[str] = None
    session_id: Optional[str] = None
    output_summary: Optional[str] = None


@dataclass
class TaskExecutorConfig:
    """Configuration for TaskExecutor."""
    max_retries: int = DEFAULT_MAX_RETRIES
    retry_delay_seconds: int = DEFAULT_RETRY_DELAY_SECONDS
    poll_interval_seconds: int = DEFAULT_TASK_POLL_INTERVAL
    agent_mapping: Dict[str, str] = field(default_factory=lambda: AGENT_MAPPING.copy())
    spawn_timeout_seconds: int = 300
    claim_timeout_minutes: int = 10
    auto_assign: bool = True
    track_execution: bool = True


# =============================================================================
# Exceptions
# =============================================================================

class TaskExecutorError(Exception):
    """Base exception for task executor errors."""
    pass


class AgentSpawnError(TaskExecutorError):
    """Exception raised when agent session spawning fails."""
    pass


class TaskAssignmentError(TaskExecutorError):
    """Exception raised when task assignment fails."""
    pass


class TaskNotFoundError(TaskExecutorError):
    """Exception raised when a task is not found."""
    pass


# =============================================================================
# Task Executor
# =============================================================================

class TaskExecutor:
    """
    Executes tasks by spawning agent sessions and tracking their progress.

    The TaskExecutor bridges Notion task creation with actual agent execution:
    1. Listens for new tasks via callback or polling
    2. Maps task types to appropriate agents
    3. Spawns OpenClaw sessions for task execution
    4. Tracks execution status and updates Neo4j/Notion
    5. Handles retries and error escalation

    Attributes:
        memory: OperationalMemory instance for Neo4j operations
        notion_integration: Optional NotionIntegration for bidirectional sync
        config: TaskExecutorConfig with execution parameters
        active_executions: Dict of currently executing tasks

    Example:
        >>> from openclaw_memory import OperationalMemory
        >>> from notion_integration import NotionIntegration
        >>> memory = OperationalMemory(...)
        >>> notion = NotionIntegration(memory)
        >>> executor = TaskExecutor(memory, notion)
        >>> executor.start()
        >>> # Tasks will now be auto-executed when created
    """

    def __init__(
        self,
        memory,
        notion_integration=None,
        config: Optional[TaskExecutorConfig] = None
    ):
        """
        Initialize TaskExecutor.

        Args:
            memory: OperationalMemory instance
            notion_integration: Optional NotionIntegration for status sync
            config: Optional TaskExecutorConfig (uses defaults if not provided)
        """
        self.memory = memory
        self.notion_integration = notion_integration
        self.config = config or TaskExecutorConfig()

        # Execution tracking
        self._active_executions: Dict[str, ExecutionAttempt] = {}
        self._execution_lock = threading.RLock()

        # Background processing
        self._running = False
        self._stop_event = threading.Event()
        self._executor_thread: Optional[threading.Thread] = None
        self._session_polling_thread: Optional[threading.Thread] = None

        # Callbacks
        self._on_task_completed: Optional[Callable[[str, str], None]] = None
        self._on_task_failed: Optional[Callable[[str, str, str], None]] = None

        # Session tracking for spawned agents
        self._spawned_sessions: Dict[str, Dict[str, Any]] = {}

        logger.info("TaskExecutor initialized")

    # =========================================================================
    # Lifecycle
    # =========================================================================

    def start(self) -> None:
        """
        Start the task executor background processing.

        This begins polling for pending tasks and monitoring active executions.
        """
        if self._running:
            logger.warning("TaskExecutor already running")
            return

        self._running = True
        self._stop_event.clear()

        # Start task polling thread
        self._executor_thread = threading.Thread(
            target=self._task_polling_loop,
            daemon=True,
            name="TaskExecutor-Poller"
        )
        self._executor_thread.start()

        # Start session monitoring thread
        self._session_polling_thread = threading.Thread(
            target=self._session_monitoring_loop,
            daemon=True,
            name="TaskExecutor-SessionMonitor"
        )
        self._session_polling_thread.start()

        # Register callback with NotionIntegration if available
        if self.notion_integration:
            self.notion_integration._on_new_task_callback = self._handle_new_notion_task
            self.notion_integration._on_status_change_callback = self._handle_status_change
            if not self.notion_integration.is_polling():
                self.notion_integration.start_polling()

        logger.info("TaskExecutor started")

    def stop(self) -> None:
        """Stop the task executor."""
        if not self._running:
            return

        self._running = False
        self._stop_event.set()

        if self._executor_thread:
            self._executor_thread.join(timeout=5)
            self._executor_thread = None

        if self._session_polling_thread:
            self._session_polling_thread.join(timeout=5)
            self._session_polling_thread = None

        logger.info("TaskExecutor stopped")

    def is_running(self) -> bool:
        """Check if executor is running."""
        return self._running

    # =========================================================================
    # Task-to-Agent Mapping
    # =========================================================================

    def map_task_to_agent(self, task: Dict[str, Any]) -> str:
        """
        Determine the best agent for a task based on its type and content.

        Args:
            task: Task dictionary with type, description, etc.

        Returns:
            Agent identifier string

        Example:
            >>> agent = executor.map_task_to_agent({
            ...     'type': 'research_task',
            ...     'description': 'Research Python async patterns'
            ... })
            >>> print(agent)  # 'mongke'
        """
        task_type = task.get('type', '').lower()
        description = task.get('description', '').lower()
        title = task.get('title', task.get('description', '')).lower()

        # Check explicit agent assignment first
        assigned_to = task.get('assigned_to') or task.get('agent')
        if assigned_to and assigned_to != 'any':
            logger.debug(f"Task {task.get('id')} has explicit assignment: {assigned_to}")
            return assigned_to

        # Check for explicit agent in required_agents list
        required_agents = task.get('required_agents', [])
        if required_agents and required_agents[0] != 'main':
            return required_agents[0]

        # Map based on task type keywords
        combined_text = f"{task_type} {description} {title}"

        for keyword, agent in self.config.agent_mapping.items():
            if keyword in combined_text:
                logger.debug(f"Task {task.get('id')} mapped to {agent} via keyword: {keyword}")
                return agent

        # Check for code-related patterns
        code_patterns = [
            r'\.(py|js|ts|go|rs|java|cpp|c|h)$',  # File extensions
            r'(function|class|def|import|from)\s+\w+',  # Code keywords
            r'(refactor|implement|bug|fix|error|exception)',  # Dev keywords
        ]
        for pattern in code_patterns:
            if re.search(pattern, combined_text):
                logger.debug(f"Task {task.get('id')} mapped to temujin (code pattern)")
                return 'temujin'

        # Check for research patterns
        research_patterns = [
            r'(research|investigate|explore|study|analyze)\s+\w+',
            r'(what|how|why|when|where)\s+(is|are|does|do)',
            r'(compare|contrast|evaluate|assess)',
        ]
        for pattern in research_patterns:
            if re.search(pattern, combined_text):
                logger.debug(f"Task {task.get('id')} mapped to mongke (research pattern)")
                return 'mongke'

        # Check for writing patterns
        writing_patterns = [
            r'(write|compose|draft|document|summarize)',
            r'(blog|post|article|doc|readme|guide)',
        ]
        for pattern in writing_patterns:
            if re.search(pattern, combined_text):
                logger.debug(f"Task {task.get('id')} mapped to chagatai (writing pattern)")
                return 'chagatai'

        # Default to main agent
        logger.debug(f"Task {task.get('id')} mapped to default agent: main")
        return self.config.agent_mapping.get('default', 'main')

    def get_agent_for_error_type(self, error_type: str, original_agent: str) -> str:
        """
        Get the appropriate agent to handle a specific error type.

        Args:
            error_type: Type of error that occurred
            original_agent: Agent that originally failed

        Returns:
            Agent identifier for error handling
        """
        error_agent_map = {
            'syntax_error': 'temujin',
            'type_error': 'temujin',
            'import_error': 'temujin',
            'api_error': 'ogedei',
            'connection_error': 'ogedei',
            'timeout_error': 'ogedei',
            'performance_issue': 'jochi',
            'memory_leak': 'jochi',
            'insufficient_information': 'mongke',
            'missing_context': 'mongke',
            'tone_issue': 'chagatai',
            'grammar_error': 'chagatai',
        }

        return error_agent_map.get(error_type, original_agent)

    # =========================================================================
    # Task Execution
    # =========================================================================

    def execute_task(self, task_id: str, agent: Optional[str] = None) -> Optional[str]:
        """
        Execute a task by spawning an agent session.

        Args:
            task_id: Neo4j task ID
            agent: Optional agent override (auto-detected if not provided)

        Returns:
            Execution attempt ID if started, None otherwise

        Example:
            >>> attempt_id = executor.execute_task("task-123")
            >>> if attempt_id:
            ...     print(f"Execution started: {attempt_id}")
        """
        # Get task details
        task = self.memory.get_task(task_id)
        if not task:
            logger.error(f"Task not found: {task_id}")
            return None

        # Check if already executing
        with self._execution_lock:
            for attempt in self._active_executions.values():
                if attempt.task_id == task_id and attempt.status == TaskStatus.IN_PROGRESS:
                    logger.warning(f"Task {task_id} already executing")
                    return None

        # Determine agent
        if not agent:
            agent = self.map_task_to_agent(task)

        # Create execution attempt
        attempt_id = str(uuid4())
        attempt = ExecutionAttempt(
            id=attempt_id,
            task_id=task_id,
            agent=agent,
            started_at=datetime.now(timezone.utc),
            status=TaskStatus.ASSIGNED
        )

        with self._execution_lock:
            self._active_executions[attempt_id] = attempt

        # Update task status in Neo4j
        self._update_task_status(task_id, TaskStatus.ASSIGNED.value, agent=agent)

        # Spawn agent session
        try:
            session_id = self._spawn_agent_session(task, agent, attempt_id)
            if session_id:
                attempt.session_id = session_id
                attempt.status = TaskStatus.IN_PROGRESS
                self._update_task_status(task_id, TaskStatus.IN_PROGRESS.value)
                logger.info(f"Task {task_id} executing via agent {agent} (attempt: {attempt_id})")
                return attempt_id
            else:
                attempt.status = TaskStatus.FAILED
                attempt.error_message = "Failed to spawn agent session"
                self._handle_execution_failure(attempt_id, "spawn_error", "Session spawn returned None")
                return None
        except Exception as e:
            attempt.status = TaskStatus.FAILED
            attempt.error_message = str(e)
            self._handle_execution_failure(attempt_id, "spawn_error", str(e))
            logger.error(f"Failed to spawn session for task {task_id}: {e}")
            return None

    def _spawn_agent_session(
        self,
        task: Dict[str, Any],
        agent: str,
        attempt_id: str
    ) -> Optional[str]:
        """
        Spawn an OpenClaw session for task execution.
        
        NOTE: This method is designed to be called from within an OpenClaw tool
        context where the sessions_spawn tool is available. When called from
        outside this context, it will fail.
        
        For external execution, use execute_pending_tasks() in agent_tasks.py
        which handles session spawning separately.
        
        Args:
            task: Task dictionary
            agent: Agent to spawn
            attempt_id: Execution attempt ID

        Returns:
            Session ID if successful, None otherwise
        """
        task_id = task.get('id')
        description = task.get('description', 'No description')
        task_type = task.get('type', 'task')

        # Build the task prompt for the agent
        task_prompt = self._build_task_prompt(task, attempt_id)

        try:
            # Use sessions_spawn tool directly
            # This only works when called from within OpenClaw tool context
            logger.info(f"Spawning session for task {task_id} with agent {agent}")
            
            # Call sessions_spawn via the tool interface
            spawn_result = sessions_spawn(
                task=task_prompt,
                agent_id=agent.lower(),
                label=f"task-{task_id[:8]}",
                timeout_seconds=300
            )
            
            # Generate a session ID from the result
            if spawn_result:
                # Create a deterministic session ID based on task and attempt
                session_id = f"{task_id[:8]}-{attempt_id[:8]}"
                
                # Track the spawned session
                self._spawned_sessions[session_id] = {
                    'attempt_id': attempt_id,
                    'task_id': task_id,
                    'agent': agent,
                    'spawned_at': datetime.now(timezone.utc),
                    'status': 'active',
                    'session_key': str(spawn_result) if spawn_result else None
                }

                # Store session reference in Neo4j
                self._store_session_reference(task_id, session_id, attempt_id)

                logger.info(f"Spawned session {session_id} for task {task_id}")
                return session_id
            else:
                raise AgentSpawnError("sessions_spawn returned None")

        except NameError:
            # sessions_spawn not available (not in OpenClaw tool context)
            logger.error("sessions_spawn tool not available - must be called from OpenClaw tool context")
            raise AgentSpawnError("sessions_spawn tool not available - use execute_pending_tasks() instead")
        except Exception as e:
            raise AgentSpawnError(f"Failed to spawn session: {e}")

    def _build_task_prompt(self, task: Dict[str, Any], attempt_id: str) -> str:
        """
        Build the task prompt for the agent.

        Args:
            task: Task dictionary
            attempt_id: Execution attempt ID

        Returns:
            Formatted prompt string
        """
        task_id = task.get('id')
        description = task.get('description', 'No description')
        task_type = task.get('type', 'task')
        priority = task.get('priority', 'normal')
        notion_url = task.get('notion_url')

        prompt = f"""You have been assigned a task.

TASK ID: {task_id}
ATTEMPT ID: {attempt_id}
TYPE: {task_type}
PRIORITY: {priority}

DESCRIPTION:
{description}

INSTRUCTIONS:
1. Read the task description carefully
2. Execute the task to completion
3. Report your results using the appropriate format
4. Update task status when complete

"""

        if notion_url:
            prompt += f"\nNOTION REFERENCE: {notion_url}\n"

        # Add any additional context from the task
        context = task.get('context') or task.get('additional_context')
        if context:
            prompt += f"\nADDITIONAL CONTEXT:\n{json.dumps(context, indent=2, cls=Neo4jJSONEncoder)}\n"

        # Add checkpoint info if resuming
        checkpoint = task.get('checkpoint_context')
        if checkpoint:
            prompt += f"\nCHECKPOINT (resuming from previous attempt):\n{json.dumps(checkpoint, indent=2, cls=Neo4jJSONEncoder)}\n"

        prompt += """
When you complete the task, report status with:
- TASK_COMPLETE: <summary of what was accomplished>
- Or if failed: TASK_FAILED: <reason>

Begin execution now.
"""

        return prompt

    def _parse_session_id(self, output: str) -> Optional[str]:
        """Parse session ID from spawn command output."""
        # Try to extract UUID pattern
        uuid_pattern = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
        match = re.search(uuid_pattern, output, re.IGNORECASE)
        if match:
            return match.group(0)

        # Try "Session: <id>" pattern
        session_pattern = r'[Ss]ession(?:\s+created)?[:\s]+(\S+)'
        match = re.search(session_pattern, output)
        if match:
            return match.group(1)

        # If output is just a single word/ID, use that
        if output and ' ' not in output:
            return output

        return None

    # =========================================================================
    # Status Updates
    # =========================================================================

    def _update_task_status(
        self,
        task_id: str,
        status: str,
        agent: Optional[str] = None,
        error_message: Optional[str] = None,
        output_summary: Optional[str] = None
    ) -> bool:
        """
        Update task status in Neo4j and sync to Notion.

        Args:
            task_id: Task ID
            status: New status
            agent: Optional agent identifier
            error_message: Optional error message
            output_summary: Optional completion summary

        Returns:
            True if successful
        """
        try:
            # Build update query
            set_clauses = ["t.status = $status", "t.updated_at = datetime()"]
            params = {'task_id': task_id, 'status': status}

            if agent:
                set_clauses.append("t.claimed_by = $agent")
                params['agent'] = agent

            if error_message:
                set_clauses.append("t.error_message = $error")
                params['error'] = error_message

            if output_summary:
                set_clauses.append("t.output_summary = $summary")
                params['summary'] = output_summary

            if status == TaskStatus.COMPLETED.value:
                set_clauses.append("t.completed_at = datetime()")
            elif status == TaskStatus.IN_PROGRESS.value:
                set_clauses.append("t.started_at = datetime()")

            query = f"""
            MATCH (t:Task {{id: $task_id}})
            SET {', '.join(set_clauses)}
            RETURN t.id as id
            """

            with self.memory._session() as session:
                if session:
                    session.run(query, **params)

            # Sync to Notion if available
            if self.notion_integration:
                self.notion_integration.sync_neo4j_status_to_notion(task_id)

            logger.debug(f"Updated task {task_id} status to {status}")
            return True

        except Exception as e:
            logger.error(f"Failed to update task status: {e}")
            return False

    def _store_session_reference(
        self,
        task_id: str,
        session_id: str,
        attempt_id: str
    ) -> None:
        """Store session reference in Neo4j."""
        query = """
        MATCH (t:Task {id: $task_id})
        CREATE (s:SessionExecution {
            id: $attempt_id,
            session_id: $session_id,
            task_id: $task_id,
            created_at: datetime(),
            status: 'active'
        })
        CREATE (t)-[:HAS_EXECUTION]->(s)
        """

        with self.memory._session() as session:
            if session:
                try:
                    session.run(query, task_id=task_id, session_id=session_id, attempt_id=attempt_id)
                except Exception as e:
                    logger.error(f"Failed to store session reference: {e}")

    # =========================================================================
    # Completion and Failure Handling
    # =========================================================================

    def mark_task_complete(
        self,
        attempt_id: str,
        output_summary: str,
        artifacts: Optional[List[Dict]] = None
    ) -> bool:
        """
        Mark a task execution as complete.

        Args:
            attempt_id: Execution attempt ID
            output_summary: Summary of what was accomplished
            artifacts: Optional list of generated artifacts

        Returns:
            True if successful
        """
        with self._execution_lock:
            attempt = self._active_executions.get(attempt_id)
            if not attempt:
                logger.error(f"Attempt not found: {attempt_id}")
                return False

            attempt.status = TaskStatus.COMPLETED
            attempt.completed_at = datetime.now(timezone.utc)
            attempt.output_summary = output_summary

        # Update task status
        self._update_task_status(
            attempt.task_id,
            TaskStatus.COMPLETED.value,
            output_summary=output_summary
        )

        # Store artifacts if provided
        if artifacts:
            self._store_artifacts(attempt.task_id, artifacts)

        # Cleanup
        self._cleanup_execution(attempt_id)

        # Notify callback
        if self._on_task_completed:
            try:
                self._on_task_completed(attempt.task_id, output_summary)
            except Exception as e:
                logger.error(f"Error in completion callback: {e}")

        logger.info(f"Task {attempt.task_id} completed: {output_summary[:100]}...")
        return True

    def mark_task_failed(
        self,
        attempt_id: str,
        error_type: str,
        error_message: str
    ) -> bool:
        """
        Mark a task execution as failed.

        Args:
            attempt_id: Execution attempt ID
            error_type: Type of error
            error_message: Error details

        Returns:
            True if handled (may trigger retry)
        """
        with self._execution_lock:
            attempt = self._active_executions.get(attempt_id)
            if not attempt:
                logger.error(f"Attempt not found: {attempt_id}")
                return False

            attempt.status = TaskStatus.FAILED
            attempt.completed_at = datetime.now(timezone.utc)
            attempt.error_type = error_type
            attempt.error_message = error_message

        return self._handle_execution_failure(attempt_id, error_type, error_message)

    def _handle_execution_failure(
        self,
        attempt_id: str,
        error_type: str,
        error_message: str
    ) -> bool:
        """
        Handle task execution failure with retry logic.

        Args:
            attempt_id: Execution attempt ID
            error_type: Type of error
            error_message: Error details

        Returns:
            True if retry scheduled, False otherwise
        """
        with self._execution_lock:
            attempt = self._active_executions.get(attempt_id)
            if not attempt:
                return False

            task_id = attempt.task_id
            agent = attempt.agent

        # Get retry count
        retry_count = self._get_retry_count(task_id)

        # Check if error is retryable
        is_retryable = error_type in RETRYABLE_ERRORS

        if is_retryable and retry_count < self.config.max_retries:
            # Schedule retry
            retry_delay = self.config.retry_delay_seconds * (2 ** retry_count)  # Exponential backoff
            logger.info(
                f"Scheduling retry {retry_count + 1}/{self.config.max_retries} "
                f"for task {task_id} in {retry_delay}s"
            )

            self._update_task_status(
                task_id,
                TaskStatus.RETRYING.value,
                error_message=f"Retry {retry_count + 1}/{self.config.max_retries}: {error_message}"
            )

            # Schedule retry in background
            threading.Timer(
                retry_delay,
                self._retry_task,
                args=[task_id, agent, retry_count + 1]
            ).start()

            return True
        else:
            # Max retries exceeded or non-retryable error
            self._update_task_status(
                task_id,
                TaskStatus.FAILED.value,
                error_message=error_message
            )

            # Route error to appropriate agent if using NotionIntegration
            if self.notion_integration:
                try:
                    self.notion_integration.route_error_task(
                        task_id=task_id,
                        error_message=error_message,
                        original_agent=agent
                    )
                except Exception as e:
                    logger.error(f"Error routing failed task: {e}")

            # Notify callback
            if self._on_task_failed:
                try:
                    self._on_task_failed(task_id, error_type, error_message)
                except Exception as e:
                    logger.error(f"Error in failure callback: {e}")

            # Cleanup
            self._cleanup_execution(attempt_id)

            logger.error(f"Task {task_id} failed after {retry_count} retries: {error_message}")
            return False

    def _retry_task(self, task_id: str, agent: str, retry_count: int) -> None:
        """Retry a failed task."""
        logger.info(f"Retrying task {task_id} (attempt {retry_count})")

        # Record retry in Neo4j
        try:
            query = """
            MATCH (t:Task {id: $task_id})
            SET t.retry_count = $retry_count,
                t.last_retry_at = datetime()
            """
            with self.memory._session() as session:
                if session:
                    session.run(query, task_id=task_id, retry_count=retry_count)
        except Exception as e:
            logger.error(f"Failed to record retry: {e}")

        # Re-execute
        self.execute_task(task_id, agent)

    def _get_retry_count(self, task_id: str) -> int:
        """Get current retry count for a task."""
        try:
            query = "MATCH (t:Task {id: $task_id}) RETURN t.retry_count as count"
            with self.memory._session() as session:
                if session:
                    result = session.run(query, task_id=task_id)
                    record = result.single()
                    return record["count"] if record and record["count"] else 0
        except Exception:
            pass
        return 0

    def _cleanup_execution(self, attempt_id: str) -> None:
        """Clean up execution tracking."""
        with self._execution_lock:
            if attempt_id in self._active_executions:
                attempt = self._active_executions[attempt_id]
                # Keep session reference but mark as inactive
                if attempt.session_id:
                    if attempt.session_id in self._spawned_sessions:
                        self._spawned_sessions[attempt.session_id]['status'] = 'completed'
                # Remove from active
                del self._active_executions[attempt_id]

    def _store_artifacts(self, task_id: str, artifacts: List[Dict]) -> None:
        """Store task artifacts in Neo4j."""
        query = """
        MATCH (t:Task {id: $task_id})
        WITH t
        UNWIND $artifacts as artifact
        CREATE (a:Artifact {
            id: artifact.id,
            type: artifact.type,
            path: artifact.path,
            description: artifact.description,
            created_at: datetime()
        })
        CREATE (t)-[:PRODUCED]->(a)
        """

        with self.memory._session() as session:
            if session:
                try:
                    session.run(query, task_id=task_id, artifacts=artifacts)
                except Exception as e:
                    logger.error(f"Failed to store artifacts: {e}")

    # =========================================================================
    # Background Polling Loops
    # =========================================================================

    def _task_polling_loop(self) -> None:
        """Background loop to poll for and execute pending tasks."""
        logger.info("Task polling loop started")

        while self._running and not self._stop_event.is_set():
            try:
                self._process_pending_tasks()
            except Exception as e:
                logger.error(f"Error in task polling loop: {e}")

            # Wait for next poll
            self._stop_event.wait(self.config.poll_interval_seconds)

    def _process_pending_tasks(self) -> None:
        """Process pending tasks from Neo4j."""
        try:
            query = """
            MATCH (t:Task)
            WHERE t.status IN ['pending', 'retrying']
              AND (t.assigned_to IS NULL OR t.assigned_to = 'any')
              AND (t.next_attempt_at IS NULL OR t.next_attempt_at <= datetime())
            RETURN t.id as id, t
            ORDER BY t.priority_weight DESC, t.created_at ASC
            LIMIT 10
            """

            with self.memory._session() as session:
                if not session:
                    return

                result = session.run(query)
                tasks = [(record["id"], dict(record["t"])) for record in result]

            for task_id, task_data in tasks:
                # Check if already being executed
                with self._execution_lock:
                    already_executing = any(
                        a.task_id == task_id and a.status == TaskStatus.IN_PROGRESS
                        for a in self._active_executions.values()
                    )
                    if already_executing:
                        continue

                # Execute the task
                logger.info(f"Auto-executing pending task: {task_id}")
                self.execute_task(task_id)

        except Exception as e:
            logger.error(f"Error processing pending tasks: {e}")

    def _session_monitoring_loop(self) -> None:
        """Background loop to monitor spawned sessions."""
        logger.info("Session monitoring loop started")

        while self._running and not self._stop_event.is_set():
            try:
                self._monitor_sessions()
            except Exception as e:
                logger.error(f"Error in session monitoring loop: {e}")

            # Check every 10 seconds
            self._stop_event.wait(10)

    def _monitor_sessions(self) -> None:
        """Monitor active sessions for completion/failure."""
        sessions_to_check = []

        with self._execution_lock:
            for session_id, info in list(self._spawned_sessions.items()):
                if info['status'] == 'active':
                    sessions_to_check.append((session_id, info))

        for session_id, info in sessions_to_check:
            try:
                status = self._check_session_status(session_id)

                if status == 'completed':
                    self._handle_session_complete(session_id, info)
                elif status == 'failed':
                    self._handle_session_failure(session_id, info)
                elif status == 'timeout':
                    self._handle_session_timeout(session_id, info)

            except Exception as e:
                logger.error(f"Error checking session {session_id}: {e}")

    def _check_session_status(self, session_id: str) -> str:
        """
        Check the status of a spawned session.

        Args:
            session_id: Session ID to check

        Returns:
            Status string: 'active', 'completed', 'failed', 'timeout', or 'unknown'
        """
        try:
            # Use openclaw sessions_list or similar to check status
            cmd = ['openclaw', 'sessions_list', '--format', 'json']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

            if result.returncode != 0:
                return 'unknown'

            sessions = json.loads(result.stdout)
            for session in sessions:
                if session.get('id') == session_id:
                    return session.get('status', 'unknown')

            # Session not found - assume completed
            return 'completed'

        except Exception as e:
            logger.debug(f"Could not check session status: {e}")
            return 'unknown'

    def _handle_session_complete(self, session_id: str, info: Dict) -> None:
        """Handle session completion."""
        attempt_id = info['attempt_id']

        # Try to get output from session
        output = self._get_session_output(session_id)

        # Mark as complete
        self.mark_task_complete(
            attempt_id=attempt_id,
            output_summary=output or "Task completed (no output captured)"
        )

        # Update session tracking
        self._spawned_sessions[session_id]['status'] = 'completed'

    def _handle_session_failure(self, session_id: str, info: Dict) -> None:
        """Handle session failure."""
        attempt_id = info['attempt_id']

        # Get error details
        error = self._get_session_error(session_id)

        self.mark_task_failed(
            attempt_id=attempt_id,
            error_type=error.get('type', 'unknown'),
            error_message=error.get('message', 'Session failed')
        )

        self._spawned_sessions[session_id]['status'] = 'failed'

    def _handle_session_timeout(self, session_id: str, info: Dict) -> None:
        """Handle session timeout."""
        attempt_id = info['attempt_id']

        self.mark_task_failed(
            attempt_id=attempt_id,
            error_type='timeout_error',
            error_message=f"Session {session_id} timed out"
        )

        self._spawned_sessions[session_id]['status'] = 'timeout'

    def _get_session_output(self, session_id: str) -> Optional[str]:
        """Get output from a completed session."""
        try:
            # Try to fetch session output
            cmd = ['openclaw', 'sessions_logs', session_id, '--tail', '100']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

            if result.returncode == 0:
                # Look for TASK_COMPLETE marker
                output = result.stdout
                match = re.search(r'TASK_COMPLETE[:\s]+(.+?)(?:\n|$)', output, re.IGNORECASE)
                if match:
                    return match.group(1).strip()
                return output[:1000]  # Return first 1000 chars

        except Exception as e:
            logger.debug(f"Could not get session output: {e}")

        return None

    def _get_session_error(self, session_id: str) -> Dict[str, str]:
        """Get error details from a failed session."""
        try:
            cmd = ['openclaw', 'sessions_logs', session_id, '--tail', '50']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

            if result.returncode == 0:
                output = result.stdout

                # Look for TASK_FAILED marker
                match = re.search(r'TASK_FAILED[:\s]+(.+?)(?:\n|$)', output, re.IGNORECASE)
                if match:
                    return {'type': 'execution_error', 'message': match.group(1).strip()}

                # Look for common error patterns
                if 'syntax error' in output.lower():
                    return {'type': 'syntax_error', 'message': 'Syntax error detected'}
                if 'timeout' in output.lower():
                    return {'type': 'timeout_error', 'message': 'Execution timeout'}

                return {'type': 'unknown', 'message': output[:500]}

        except Exception as e:
            logger.debug(f"Could not get session error: {e}")

        return {'type': 'unknown', 'message': 'Session failed - details unavailable'}

    # =========================================================================
    # NotionIntegration Callbacks
    # =========================================================================

    def _handle_new_notion_task(self, notion_task) -> None:
        """
        Callback for new Notion tasks.

        Args:
            notion_task: NotionTask object
        """
        logger.info(f"New Notion task received: {notion_task.title}")

        # The task should already be created in Neo4j by NotionIntegration
        # Find and execute it
        if notion_task.neo4j_task_id:
            self.execute_task(notion_task.neo4j_task_id)
        else:
            logger.warning(f"Notion task {notion_task.id} has no Neo4j task ID yet")

    def _handle_status_change(self, task_id: str, old_status: str, new_status: str) -> None:
        """
        Callback for Notion status changes.

        Args:
            task_id: Neo4j task ID
            old_status: Previous status
            new_status: New status
        """
        logger.info(f"Status change for {task_id}: {old_status} -> {new_status}")

        # Handle user moving task to In Progress
        if new_status == 'In Progress' and old_status in ['To Do', 'Backlog']:
            # Check if already executing
            with self._execution_lock:
                already_executing = any(
                    a.task_id == task_id and a.status == TaskStatus.IN_PROGRESS
                    for a in self._active_executions.values()
                )

            if not already_executing:
                logger.info(f"User moved task {task_id} to In Progress - auto-executing")
                self.execute_task(task_id)

        # Handle user blocking/cancelling task
        if new_status in ['Blocked', 'Backlog']:
            # Cancel any active execution
            with self._execution_lock:
                for attempt_id, attempt in list(self._active_executions.items()):
                    if attempt.task_id == task_id:
                        logger.info(f"Cancelling execution for blocked task {task_id}")
                        attempt.status = TaskStatus.CANCELLED
                        self._cleanup_execution(attempt_id)

    # =========================================================================
    # Public API
    # =========================================================================

    def get_active_executions(self) -> List[Dict[str, Any]]:
        """
        Get list of currently active executions.

        Returns:
            List of execution dictionaries
        """
        with self._execution_lock:
            return [
                {
                    'attempt_id': a.id,
                    'task_id': a.task_id,
                    'agent': a.agent,
                    'status': a.status.value,
                    'started_at': a.started_at.isoformat() if a.started_at else None,
                    'session_id': a.session_id,
                }
                for a in self._active_executions.values()
            ]

    def get_execution_status(self, attempt_id: str) -> Optional[Dict[str, Any]]:
        """
        Get status of a specific execution attempt.

        Args:
            attempt_id: Execution attempt ID

        Returns:
            Status dictionary or None
        """
        with self._execution_lock:
            attempt = self._active_executions.get(attempt_id)
            if attempt:
                return {
                    'attempt_id': attempt.id,
                    'task_id': attempt.task_id,
                    'agent': attempt.agent,
                    'status': attempt.status.value,
                    'started_at': attempt.started_at.isoformat() if attempt.started_at else None,
                    'completed_at': attempt.completed_at.isoformat() if attempt.completed_at else None,
                    'error_message': attempt.error_message,
                    'session_id': attempt.session_id,
                }
        return None

    def cancel_execution(self, attempt_id: str) -> bool:
        """
        Cancel an active execution.

        Args:
            attempt_id: Execution attempt ID

        Returns:
            True if cancelled
        """
        with self._execution_lock:
            attempt = self._active_executions.get(attempt_id)
            if not attempt:
                return False

            attempt.status = TaskStatus.CANCELLED

            # Try to kill the session
            if attempt.session_id:
                try:
                    cmd = ['openclaw', 'sessions_kill', attempt.session_id]
                    subprocess.run(cmd, capture_output=True, timeout=10)
                except Exception as e:
                    logger.warning(f"Could not kill session {attempt.session_id}: {e}")

            self._cleanup_execution(attempt_id)

        # Update task status
        self._update_task_status(attempt.task_id, TaskStatus.CANCELLED.value)

        logger.info(f"Cancelled execution {attempt_id}")
        return True

    def set_callbacks(
        self,
        on_complete: Optional[Callable[[str, str], None]] = None,
        on_fail: Optional[Callable[[str, str, str], None]] = None
    ) -> None:
        """
        Set callback functions for task completion/failure.

        Args:
            on_complete: Callback(task_id, output_summary)
            on_fail: Callback(task_id, error_type, error_message)
        """
        self._on_task_completed = on_complete
        self._on_task_failed = on_fail

    def get_stats(self) -> Dict[str, Any]:
        """
        Get executor statistics.

        Returns:
            Statistics dictionary
        """
        with self._execution_lock:
            active_count = len(self._active_executions)
            status_counts = {}
            for a in self._active_executions.values():
                status = a.status.value
                status_counts[status] = status_counts.get(status, 0) + 1

        return {
            'running': self._running,
            'active_executions': active_count,
            'status_breakdown': status_counts,
            'spawned_sessions': len(self._spawned_sessions),
            'config': {
                'max_retries': self.config.max_retries,
                'poll_interval': self.config.poll_interval_seconds,
            }
        }

    def close(self) -> None:
        """Close the executor and cleanup resources."""
        self.stop()

        # Cancel any remaining executions
        with self._execution_lock:
            for attempt_id in list(self._active_executions.keys()):
                self.cancel_execution(attempt_id)

        logger.info("TaskExecutor closed")

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False


# =============================================================================
# Convenience Functions
# =============================================================================

def create_task_executor(
    memory,
    notion_integration=None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    poll_interval: int = DEFAULT_TASK_POLL_INTERVAL
) -> TaskExecutor:
    """
    Convenience function to create a TaskExecutor.

    Args:
        memory: OperationalMemory instance
        notion_integration: Optional NotionIntegration
        max_retries: Maximum retry attempts
        poll_interval: Polling interval in seconds

    Returns:
        Configured TaskExecutor instance

    Example:
        >>> from openclaw_memory import OperationalMemory
        >>> memory = OperationalMemory(...)
        >>> executor = create_task_executor(memory)
        >>> with executor:
        ...     # Tasks will be auto-executed
        ...     time.sleep(60)
    """
    config = TaskExecutorConfig(
        max_retries=max_retries,
        poll_interval_seconds=poll_interval
    )
    return TaskExecutor(memory, notion_integration, config)


# =============================================================================
# Integration with NotionIntegration
# =============================================================================

def integrate_with_notion(notion_integration, memory) -> TaskExecutor:
    """
    Create and start a TaskExecutor integrated with NotionIntegration.

    Args:
        notion_integration: NotionIntegration instance
        memory: OperationalMemory instance

    Returns:
        Started TaskExecutor instance

    Example:
        >>> from notion_integration import NotionIntegration
        >>> from openclaw_memory import OperationalMemory
        >>> memory = OperationalMemory(...)
        >>> notion = NotionIntegration(memory)
        >>> executor = integrate_with_notion(notion, memory)
        >>> # Notion tasks will now be auto-executed
    """
    executor = TaskExecutor(memory, notion_integration)

    # The TaskExecutor will register itself with NotionIntegration's callbacks
    # and start polling when start() is called
    executor.start()

    return executor
