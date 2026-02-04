"""
OpenClaw Operational Memory - Neo4j-backed operational memory for the 6-agent system.

This module provides the OperationalMemory class for managing tasks, notifications,
rate limiting, and agent state in a Neo4j graph database.
"""

import logging
import uuid
import time
import functools
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any, Callable
from contextlib import contextmanager

from neo4j import GraphDatabase, Driver, Session
from neo4j.exceptions import ServiceUnavailable, Neo4jError, TransientError

# Configure logging
logger = logging.getLogger(__name__)


class RaceConditionError(Exception):
    """Raised when another agent claims a task simultaneously."""
    pass


class NoPendingTaskError(Exception):
    """Raised when no pending tasks are available."""
    pass


class Neo4jUnavailableError(Exception):
    """Raised when Neo4j is unavailable and fallback mode is disabled."""
    pass


def retry_on_race_condition(max_retries: int = 3, base_delay: float = 0.1):
    """
    Decorator for automatic retry on race conditions.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Base delay between retries (uses exponential backoff)
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except RaceConditionError as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(
                            f"Race condition in {func.__name__}, "
                            f"retrying in {delay}s (attempt {attempt + 1}/{max_retries})"
                        )
                        time.sleep(delay)
                    else:
                        logger.error(
                            f"Race condition in {func.__name__} persisted after "
                            f"{max_retries} attempts"
                        )
            raise last_exception
        return wrapper
    return decorator


class OperationalMemory:
    """
    Core operational memory component backed by Neo4j.

    Manages:
    - Task lifecycle (create, claim, complete)
    - Notifications between agents
    - Rate limiting
    - Agent heartbeat tracking
    - Health monitoring
    """

    def __init__(
        self,
        uri: str = "bolt://localhost:7687",
        username: str = "neo4j",
        password: str | None = None,
        database: str = "neo4j",
        fallback_mode: bool = True,
        max_connection_pool_size: int = 50,
        connection_timeout: int = 30,
        max_retry_time: int = 30
    ):
        """
        Initialize OperationalMemory with Neo4j connection.

        Args:
            uri: Neo4j bolt URI
            username: Neo4j username
            password: Neo4j password (required, must be provided explicitly)
            database: Neo4j database name
            fallback_mode: If True, return empty results when Neo4j unavailable
            max_connection_pool_size: Maximum connections in pool
            connection_timeout: Connection timeout in seconds
            max_retry_time: Maximum retry time for transient errors

        Raises:
            ValueError: If password is not provided
        """
        if password is None:
            raise ValueError("Neo4j password is required. Provide it explicitly or via NEO4J_PASSWORD environment variable.")

        self.uri = uri
        self.username = username
        self.password = password
        self.database = database
        self.fallback_mode = fallback_mode
        self._driver: Optional[Driver] = None
        self._pool_config = {
            "max_connection_pool_size": max_connection_pool_size,
            "connection_timeout": connection_timeout,
            "max_transaction_retry_time": max_retry_time
        }
        self._initialize_driver()

    def _initialize_driver(self) -> None:
        """Initialize Neo4j driver with connection pooling."""
        try:
            self._driver = GraphDatabase.driver(
                self.uri,
                auth=(self.username, self.password),
                **self._pool_config
            )
            # Verify connectivity
            self._driver.verify_connectivity()
            logger.info(f"Neo4j driver initialized: {self.uri}")
        except ServiceUnavailable as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            self._driver = None
            if not self.fallback_mode:
                raise Neo4jUnavailableError(f"Neo4j unavailable: {e}")

    def _ensure_driver(self) -> bool:
        """Ensure driver is available, attempt reconnection if needed."""
        if self._driver is None:
            self._initialize_driver()
        return self._driver is not None

    @contextmanager
    def _session(self):
        """Context manager for Neo4j sessions."""
        if not self._ensure_driver():
            if self.fallback_mode:
                logger.warning("Neo4j unavailable, operating in fallback mode")
                yield None
                return
            else:
                raise Neo4jUnavailableError("Neo4j is not available")

        session = None
        try:
            session = self._driver.session(database=self.database)
            yield session
        except ServiceUnavailable as e:
            logger.error(f"Neo4j service unavailable: {e}")
            self._driver = None
            if self.fallback_mode:
                yield None
            else:
                raise Neo4jUnavailableError(f"Neo4j service unavailable: {e}")
        finally:
            if session:
                session.close()

    def _generate_id(self) -> str:
        """Generate a unique ID."""
        return str(uuid.uuid4())

    def _now(self) -> datetime:
        """Get current UTC datetime."""
        return datetime.now(timezone.utc)

    # =======================================================================
    # Task Lifecycle
    # =======================================================================

    def create_task(
        self,
        task_type: str,
        description: str,
        delegated_by: str,
        assigned_to: str,
        priority: str = "normal",
        **kwargs
    ) -> str:
        """
        Create a new task node, return task ID.

        Args:
            task_type: Type of task (e.g., 'code_review', 'deploy')
            description: Task description
            delegated_by: Agent that delegated the task
            assigned_to: Agent assigned to the task (or 'any' for unassigned)
            priority: Task priority ('low', 'normal', 'high', 'critical')
            **kwargs: Additional task properties

        Returns:
            Task ID string
        """
        task_id = self._generate_id()
        created_at = self._now()

        # Normalize assigned_to - None or 'any' means unassigned
        if assigned_to == 'any':
            assigned_to_value = None
        else:
            assigned_to_value = assigned_to

        cypher = """
        CREATE (t:Task {
            id: $task_id,
            type: $task_type,
            description: $description,
            status: 'pending',
            delegated_by: $delegated_by,
            assigned_to: $assigned_to,
            priority: $priority,
            created_at: $created_at,
            claimed_at: null,
            completed_at: null,
            claimed_by: null,
            results: null,
            error_message: null
        })
        RETURN t.id as task_id
        """

        with self._session() as session:
            if session is None:
                logger.warning(f"Fallback mode: Task creation simulated for {task_type}")
                return task_id

            try:
                result = session.run(
                    cypher,
                    task_id=task_id,
                    task_type=task_type,
                    description=description,
                    delegated_by=delegated_by,
                    assigned_to=assigned_to_value,
                    priority=priority,
                    created_at=created_at
                )
                record = result.single()
                if record:
                    logger.info(f"Task created: {task_id} (type: {task_type}, assigned_to: {assigned_to})")
                    return record["task_id"]
                else:
                    raise RuntimeError("Task creation failed: no record returned")
            except Neo4jError as e:
                logger.error(f"Failed to create task: {e}")
                raise

    @retry_on_race_condition(max_retries=3, base_delay=0.1)
    def claim_task(self, agent: str) -> Optional[Dict]:
        """
        Atomically claim a pending task.

        Args:
            agent: Agent claiming the task

        Returns:
            Task dict if successful, None if no tasks available

        Raises:
            RaceConditionError: If another agent claimed the task simultaneously
            NoPendingTaskError: If no pending tasks are available
        """
        claimed_at = self._now()

        # Use explicit locking pattern for atomic claim
        cypher = """
        MATCH (t:Task {status: 'pending'})
        WHERE t.assigned_to = $agent OR t.assigned_to IS NULL
        WITH t ORDER BY
            CASE t.priority
                WHEN 'critical' THEN 4
                WHEN 'high' THEN 3
                WHEN 'normal' THEN 2
                WHEN 'low' THEN 1
                ELSE 0
            END DESC,
            t.created_at ASC
        LIMIT 1
        SET t.status = 'in_progress',
            t.claimed_by = $agent,
            t.claimed_at = $claimed_at
        RETURN t
        """

        with self._session() as session:
            if session is None:
                logger.warning(f"Fallback mode: Task claim simulated for {agent}")
                return None

            try:
                result = session.run(
                    cypher,
                    agent=agent,
                    claimed_at=claimed_at
                )
                record = result.single()

                if record is None:
                    raise NoPendingTaskError(f"No pending tasks available for {agent}")

                task_node = record["t"]
                task_dict = dict(task_node)
                logger.info(f"Task claimed: {task_dict['id']} by {agent}")
                return task_dict

            except (RaceConditionError, NoPendingTaskError):
                raise
            except Neo4jError as e:
                logger.error(f"Failed to claim task: {e}")
                raise

    def complete_task(
        self,
        task_id: str,
        results: Dict,
        notify_delegator: bool = True
    ) -> bool:
        """
        Mark task as complete with results.

        Args:
            task_id: Task ID to complete
            results: Task results dictionary
            notify_delegator: Whether to create notification for delegator

        Returns:
            True if successful
        """
        completed_at = self._now()

        cypher = """
        MATCH (t:Task {id: $task_id})
        WHERE t.status = 'in_progress'
        SET t.status = 'completed',
            t.completed_at = $completed_at,
            t.results = $results
        RETURN t.delegated_by as delegated_by, t.claimed_by as claimed_by
        """

        with self._session() as session:
            if session is None:
                logger.warning(f"Fallback mode: Task completion simulated for {task_id}")
                return True

            try:
                result = session.run(
                    cypher,
                    task_id=task_id,
                    completed_at=completed_at,
                    results=str(results)  # Neo4j doesn't support nested dicts directly
                )
                record = result.single()

                if record is None:
                    logger.warning(f"Task not found or not in_progress: {task_id}")
                    return False

                # Create notification for delegator if requested
                if notify_delegator and record["delegated_by"]:
                    self.create_notification(
                        agent=record["delegated_by"],
                        type="task_completed",
                        summary=f"Task {task_id} completed by {record['claimed_by']}",
                        task_id=task_id
                    )

                logger.info(f"Task completed: {task_id}")
                return True

            except Neo4jError as e:
                logger.error(f"Failed to complete task: {e}")
                raise

    def fail_task(self, task_id: str, error_message: str) -> bool:
        """
        Mark task as failed with error message.

        Args:
            task_id: Task ID to fail
            error_message: Error message describing the failure

        Returns:
            True if successful
        """
        completed_at = self._now()

        cypher = """
        MATCH (t:Task {id: $task_id})
        WHERE t.status = 'in_progress'
        SET t.status = 'failed',
            t.completed_at = $completed_at,
            t.error_message = $error_message
        RETURN t.delegated_by as delegated_by, t.claimed_by as claimed_by
        """

        with self._session() as session:
            if session is None:
                logger.warning(f"Fallback mode: Task failure simulated for {task_id}")
                return True

            try:
                result = session.run(
                    cypher,
                    task_id=task_id,
                    completed_at=completed_at,
                    error_message=error_message
                )
                record = result.single()

                if record is None:
                    logger.warning(f"Task not found or not in_progress: {task_id}")
                    return False

                # Create notification for delegator
                if record["delegated_by"]:
                    self.create_notification(
                        agent=record["delegated_by"],
                        type="task_failed",
                        summary=f"Task {task_id} failed: {error_message[:100]}",
                        task_id=task_id
                    )

                logger.info(f"Task failed: {task_id} - {error_message[:100]}")
                return True

            except Neo4jError as e:
                logger.error(f"Failed to mark task as failed: {e}")
                raise

    def get_task(self, task_id: str) -> Optional[Dict]:
        """
        Get task by ID.

        Args:
            task_id: Task ID to retrieve

        Returns:
            Task dict if found, None otherwise
        """
        cypher = """
        MATCH (t:Task {id: $task_id})
        RETURN t
        """

        with self._session() as session:
            if session is None:
                return None

            try:
                result = session.run(cypher, task_id=task_id)
                record = result.single()
                return dict(record["t"]) if record else None
            except Neo4jError as e:
                logger.error(f"Failed to get task: {e}")
                raise

    def list_pending_tasks(self, agent: Optional[str] = None) -> List[Dict]:
        """
        List pending tasks, optionally filtered by assigned agent.

        Args:
            agent: Filter by assigned agent (None for all)

        Returns:
            List of task dicts
        """
        if agent:
            cypher = """
            MATCH (t:Task {status: 'pending'})
            WHERE t.assigned_to = $agent OR t.assigned_to IS NULL
            RETURN t
            ORDER BY
                CASE t.priority
                    WHEN 'critical' THEN 4
                    WHEN 'high' THEN 3
                    WHEN 'normal' THEN 2
                    WHEN 'low' THEN 1
                    ELSE 0
                END DESC,
                t.created_at ASC
            """
            params = {"agent": agent}
        else:
            cypher = """
            MATCH (t:Task {status: 'pending'})
            RETURN t
            ORDER BY
                CASE t.priority
                    WHEN 'critical' THEN 4
                    WHEN 'high' THEN 3
                    WHEN 'normal' THEN 2
                    WHEN 'low' THEN 1
                    ELSE 0
                END DESC,
                t.created_at ASC
            """
            params = {}

        with self._session() as session:
            if session is None:
                return []

            try:
                result = session.run(cypher, **params)
                return [dict(record["t"]) for record in result]
            except Neo4jError as e:
                logger.error(f"Failed to list pending tasks: {e}")
                raise

    def list_tasks_by_status(self, status: str, agent: Optional[str] = None) -> List[Dict]:
        """
        List tasks by status.

        Args:
            status: Task status ('pending', 'in_progress', 'completed', 'failed')
            agent: Filter by claimed_by agent (optional)

        Returns:
            List of task dicts
        """
        if agent:
            cypher = """
            MATCH (t:Task {status: $status, claimed_by: $agent})
            RETURN t
            ORDER BY t.created_at DESC
            """
            params = {"status": status, "agent": agent}
        else:
            cypher = """
            MATCH (t:Task {status: $status})
            RETURN t
            ORDER BY t.created_at DESC
            """
            params = {"status": status}

        with self._session() as session:
            if session is None:
                return []

            try:
                result = session.run(cypher, **params)
                return [dict(record["t"]) for record in result]
            except Neo4jError as e:
                logger.error(f"Failed to list tasks: {e}")
                raise

    # =======================================================================
    # Notification System
    # =======================================================================

    def create_notification(
        self,
        agent: str,
        type: str,
        summary: str,
        task_id: Optional[str] = None
    ) -> str:
        """
        Create notification for an agent.

        Args:
            agent: Agent to notify
            type: Notification type (e.g., 'task_completed', 'task_failed')
            summary: Notification summary
            task_id: Associated task ID (optional)

        Returns:
            Notification ID
        """
        notification_id = self._generate_id()
        created_at = self._now()

        cypher = """
        CREATE (n:Notification {
            id: $notification_id,
            agent: $agent,
            type: $type,
            summary: $summary,
            task_id: $task_id,
            read: false,
            created_at: $created_at
        })
        RETURN n.id as notification_id
        """

        with self._session() as session:
            if session is None:
                logger.warning(f"Fallback mode: Notification creation simulated for {agent}")
                return notification_id

            try:
                result = session.run(
                    cypher,
                    notification_id=notification_id,
                    agent=agent,
                    type=type,
                    summary=summary,
                    task_id=task_id,
                    created_at=created_at
                )
                record = result.single()
                if record:
                    logger.info(f"Notification created: {notification_id} for {agent}")
                    return record["notification_id"]
                else:
                    raise RuntimeError("Notification creation failed")
            except Neo4jError as e:
                logger.error(f"Failed to create notification: {e}")
                raise

    def get_notifications(
        self,
        agent: str,
        unread_only: bool = True
    ) -> List[Dict]:
        """
        Get notifications for an agent.

        Args:
            agent: Agent to get notifications for
            unread_only: If True, only return unread notifications

        Returns:
            List of notification dicts
        """
        if unread_only:
            cypher = """
            MATCH (n:Notification {agent: $agent, read: false})
            RETURN n
            ORDER BY n.created_at DESC
            """
        else:
            cypher = """
            MATCH (n:Notification {agent: $agent})
            RETURN n
            ORDER BY n.created_at DESC
            """

        with self._session() as session:
            if session is None:
                return []

            try:
                result = session.run(cypher, agent=agent)
                return [dict(record["n"]) for record in result]
            except Neo4jError as e:
                logger.error(f"Failed to get notifications: {e}")
                raise

    def mark_notification_read(self, notification_id: str) -> bool:
        """
        Mark notification as read.

        Args:
            notification_id: Notification ID to mark as read

        Returns:
            True if successful
        """
        cypher = """
        MATCH (n:Notification {id: $notification_id})
        SET n.read = true
        RETURN n.id as notification_id
        """

        with self._session() as session:
            if session is None:
                return True

            try:
                result = session.run(cypher, notification_id=notification_id)
                record = result.single()
                if record:
                    logger.debug(f"Notification marked read: {notification_id}")
                    return True
                return False
            except Neo4jError as e:
                logger.error(f"Failed to mark notification as read: {e}")
                raise

    def mark_all_notifications_read(self, agent: str) -> int:
        """
        Mark all notifications as read for an agent.

        Args:
            agent: Agent to mark notifications for

        Returns:
            Number of notifications marked as read
        """
        cypher = """
        MATCH (n:Notification {agent: $agent, read: false})
        SET n.read = true
        RETURN count(n) as count
        """

        with self._session() as session:
            if session is None:
                return 0

            try:
                result = session.run(cypher, agent=agent)
                record = result.single()
                count = record["count"] if record else 0
                logger.info(f"Marked {count} notifications as read for {agent}")
                return count
            except Neo4jError as e:
                logger.error(f"Failed to mark notifications as read: {e}")
                raise

    # =======================================================================
    # Rate Limiting
    # =======================================================================

    def check_rate_limit(
        self,
        agent: str,
        operation: str,
        max_requests: int = 1000
    ) -> Tuple[bool, int, int]:
        """
        Check if operation is within rate limit.

        Uses hourly buckets for rate limiting.

        Args:
            agent: Agent making the request
            operation: Operation type being rate limited
            max_requests: Maximum requests per hour

        Returns:
            Tuple of (allowed, current_count, reset_time)
            - allowed: True if within limit
            - current_count: Current request count
            - reset_time: Unix timestamp when bucket resets
        """
        now = self._now()
        current_date = now.date()
        current_hour = now.hour

        # Calculate reset time (start of next hour)
        from datetime import timedelta
        if current_hour == 23:
            reset_time = int((datetime.combine(current_date + timedelta(days=1), datetime.min.time().replace(hour=0)) - datetime(1970, 1, 1)).total_seconds())
        else:
            reset_time = int((datetime.combine(current_date, datetime.min.time().replace(hour=current_hour + 1)) - datetime(1970, 1, 1)).total_seconds())

        cypher = """
        MATCH (r:RateLimit {agent: $agent, operation: $operation, date: $date, hour: $hour})
        RETURN r.count as count
        """

        with self._session() as session:
            if session is None:
                # In fallback mode, always allow
                return (True, 0, reset_time)

            try:
                result = session.run(
                    cypher,
                    agent=agent,
                    operation=operation,
                    date=current_date,
                    hour=current_hour
                )
                record = result.single()

                if record is None:
                    # No rate limit record yet, create one
                    self._create_rate_limit_record(agent, operation, current_date, current_hour)
                    return (True, 0, reset_time)

                count = record["count"]
                allowed = count < max_requests

                return (allowed, count, reset_time)

            except Neo4jError as e:
                logger.error(f"Failed to check rate limit: {e}")
                # Fail open - allow the request
                return (True, 0, reset_time)

    def _create_rate_limit_record(
        self,
        agent: str,
        operation: str,
        date,
        hour: int
    ) -> None:
        """Create a new rate limit record."""
        cypher = """
        MERGE (r:RateLimit {agent: $agent, operation: $operation, date: $date, hour: $hour})
        ON CREATE SET r.count = 0, r.last_updated = $last_updated
        """

        with self._session() as session:
            if session is None:
                return

            try:
                session.run(
                    cypher,
                    agent=agent,
                    operation=operation,
                    date=date,
                    hour=hour,
                    last_updated=self._now()
                )
            except Neo4jError as e:
                logger.error(f"Failed to create rate limit record: {e}")

    def record_rate_limit_hit(self, agent: str, operation: str) -> bool:
        """
        Record a rate limit hit.

        Args:
            agent: Agent making the request
            operation: Operation type

        Returns:
            True if successful
        """
        now = self._now()
        current_date = now.date()
        current_hour = now.hour

        cypher = """
        MERGE (r:RateLimit {agent: $agent, operation: $operation, date: $date, hour: $hour})
        ON CREATE SET r.count = 1, r.last_updated = $last_updated
        ON MATCH SET r.count = r.count + 1, r.last_updated = $last_updated
        RETURN r.count as count
        """

        with self._session() as session:
            if session is None:
                return True

            try:
                result = session.run(
                    cypher,
                    agent=agent,
                    operation=operation,
                    date=current_date,
                    hour=current_hour,
                    last_updated=now
                )
                record = result.single()
                if record:
                    logger.debug(
                        f"Rate limit hit recorded: {agent}/{operation} = {record['count']}"
                    )
                    return True
                return False
            except Neo4jError as e:
                logger.error(f"Failed to record rate limit hit: {e}")
                return False

    # =======================================================================
    # Agent State Management
    # =======================================================================

    def update_agent_heartbeat(self, agent: str, status: str = "active") -> bool:
        """
        Update agent heartbeat timestamp.

        Args:
            agent: Agent name
            status: Agent status ('active', 'busy', 'idle', 'offline')

        Returns:
            True if successful
        """
        now = self._now()

        cypher = """
        MERGE (a:Agent {name: $agent})
        ON CREATE SET a.created_at = $now
        SET a.last_heartbeat = $now,
            a.status = $status
        RETURN a.name as name
        """

        with self._session() as session:
            if session is None:
                return True

            try:
                result = session.run(
                    cypher,
                    agent=agent,
                    status=status,
                    now=now
                )
                record = result.single()
                if record:
                    logger.debug(f"Agent heartbeat updated: {agent} ({status})")
                    return True
                return False
            except Neo4jError as e:
                logger.error(f"Failed to update agent heartbeat: {e}")
                raise

    def get_agent_status(self, agent: str) -> Optional[Dict]:
        """
        Get agent status including last heartbeat.

        Args:
            agent: Agent name

        Returns:
            Agent status dict if found, None otherwise
        """
        cypher = """
        MATCH (a:Agent {name: $agent})
        RETURN a
        """

        with self._session() as session:
            if session is None:
                return None

            try:
                result = session.run(cypher, agent=agent)
                record = result.single()
                return dict(record["a"]) if record else None
            except Neo4jError as e:
                logger.error(f"Failed to get agent status: {e}")
                raise

    def list_active_agents(self, inactive_threshold_seconds: int = 300) -> List[Dict]:
        """
        List all active agents.

        Args:
            inactive_threshold_seconds: Consider agent inactive after this many seconds

        Returns:
            List of agent dicts with activity status
        """
        now = self._now()

        cypher = """
        MATCH (a:Agent)
        RETURN a,
            CASE
                WHEN a.last_heartbeat >= datetime($threshold) THEN true
                ELSE false
            END as is_active
        ORDER BY a.last_heartbeat DESC
        """

        threshold = (now.timestamp() - inactive_threshold_seconds) * 1000  # milliseconds

        with self._session() as session:
            if session is None:
                return []

            try:
                result = session.run(cypher, threshold=threshold)
                agents = []
                for record in result:
                    agent_dict = dict(record["a"])
                    agent_dict["is_active"] = record["is_active"]
                    agents.append(agent_dict)
                return agents
            except Neo4jError as e:
                logger.error(f"Failed to list active agents: {e}")
                raise

    def set_agent_busy(self, agent: str, busy: bool = True) -> bool:
        """
        Set agent busy status.

        Args:
            agent: Agent name
            busy: True to mark as busy, False for available

        Returns:
            True if successful
        """
        status = "busy" if busy else "active"
        return self.update_agent_heartbeat(agent, status)

    # =======================================================================
    # Health Checks
    # =======================================================================

    def health_check(self) -> Dict:
        """
        Check Neo4j health including write capability and rate limit status.

        Returns:
            Health status dict
        """
        health = {
            "status": "unknown",
            "connected": False,
            "writable": False,
            "response_time_ms": None,
            "error": None,
            "timestamp": self._now().isoformat()
        }

        if not self._ensure_driver():
            health["status"] = "unavailable"
            health["error"] = "Neo4j driver not initialized"
            return health

        start_time = time.time()

        try:
            # Test read
            with self._session() as session:
                if session is None:
                    health["status"] = "fallback_mode"
                    health["error"] = "Operating in fallback mode"
                    return health

                result = session.run("RETURN 1 as test")
                record = result.single()
                if record is None or record["test"] != 1:
                    health["error"] = "Read test failed"
                    return health

            # Test write
            test_id = self._generate_id()
            with self._session() as session:
                session.run(
                    "CREATE (h:HealthCheck {id: $id, timestamp: $timestamp})",
                    id=test_id,
                    timestamp=self._now()
                )
                session.run(
                    "MATCH (h:HealthCheck {id: $id}) DELETE h",
                    id=test_id
                )

            health["writable"] = True
            health["connected"] = True
            health["status"] = "healthy"
            health["response_time_ms"] = round((time.time() - start_time) * 1000, 2)

        except ServiceUnavailable as e:
            health["status"] = "unavailable"
            health["error"] = str(e)
            self._driver = None
        except Neo4jError as e:
            health["status"] = "error"
            health["error"] = str(e)
        except Exception as e:
            health["status"] = "error"
            health["error"] = f"Unexpected error: {e}"

        return health

    def is_healthy(self) -> bool:
        """
        Quick health check.

        Returns:
            True if Neo4j is healthy
        """
        health = self.health_check()
        return health["status"] == "healthy"

    # =======================================================================
    # Analysis (Jochi Backend Issue Identification Protocol)
    # =======================================================================

    def create_analysis(
        self,
        agent: str,
        analysis_type: str,
        severity: str,
        description: str,
        target_agent: Optional[str] = None,
        findings: Optional[Dict] = None,
        recommendations: Optional[List[str]] = None,
        assigned_to: Optional[str] = None
    ) -> str:
        """
        Create a new Analysis node for backend issues.

        Args:
            agent: Agent who created the analysis (e.g., 'jochi')
            analysis_type: Type of analysis ('performance', 'resource', 'error', 'security', 'other')
            severity: Severity level ('low', 'medium', 'high', 'critical')
            description: Human-readable description of the issue
            target_agent: Agent the analysis is about (if applicable)
            findings: Detailed findings as a dictionary
            recommendations: List of suggested fixes
            assigned_to: Agent assigned to fix (e.g., 'temujin' for backend issues)

        Returns:
            Analysis ID string

        Raises:
            ValueError: If analysis_type or severity is invalid
        """
        # Validate analysis_type
        valid_types = ['performance', 'resource', 'error', 'security', 'other']
        if analysis_type not in valid_types:
            raise ValueError(f"Invalid analysis_type '{analysis_type}'. Must be one of: {valid_types}")

        # Validate severity
        valid_severities = ['low', 'medium', 'high', 'critical']
        if severity not in valid_severities:
            raise ValueError(f"Invalid severity '{severity}'. Must be one of: {valid_severities}")

        analysis_id = self._generate_id()
        created_at = self._now()

        # Convert findings and recommendations to strings for Neo4j storage
        findings_str = str(findings) if findings else None
        recommendations_str = str(recommendations) if recommendations else None

        cypher = """
        CREATE (a:Analysis {
            id: $analysis_id,
            agent: $agent,
            target_agent: $target_agent,
            analysis_type: $analysis_type,
            severity: $severity,
            description: $description,
            findings: $findings,
            recommendations: $recommendations,
            assigned_to: $assigned_to,
            status: 'open',
            created_at: $created_at,
            updated_at: $created_at,
            resolved_at: null
        })
        RETURN a.id as analysis_id
        """

        with self._session() as session:
            if session is None:
                logger.warning(f"Fallback mode: Analysis creation simulated for {agent}")
                return analysis_id

            try:
                result = session.run(
                    cypher,
                    analysis_id=analysis_id,
                    agent=agent,
                    target_agent=target_agent,
                    analysis_type=analysis_type,
                    severity=severity,
                    description=description,
                    findings=findings_str,
                    recommendations=recommendations_str,
                    assigned_to=assigned_to,
                    created_at=created_at
                )
                record = result.single()
                if record:
                    logger.info(f"Analysis created: {analysis_id} (type: {analysis_type}, severity: {severity})")
                    return record["analysis_id"]
                else:
                    raise RuntimeError("Analysis creation failed: no record returned")
            except Neo4jError as e:
                logger.error(f"Failed to create analysis: {e}")
                raise

    def list_analyses(
        self,
        agent: Optional[str] = None,
        analysis_type: Optional[str] = None,
        severity: Optional[str] = None,
        status: Optional[str] = None,
        assigned_to: Optional[str] = None
    ) -> List[Dict]:
        """
        Query analyses with optional filters.

        Args:
            agent: Filter by agent who created the analysis
            analysis_type: Filter by type ('performance', 'resource', 'error', 'security', 'other')
            severity: Filter by severity ('low', 'medium', 'high', 'critical')
            status: Filter by status ('open', 'in_progress', 'resolved', 'closed')
            assigned_to: Filter by assigned agent

        Returns:
            List of analysis dicts, sorted by severity (critical first) then created_at
        """
        # Build dynamic query based on filters
        conditions = []
        params = {}

        if agent is not None:
            conditions.append("a.agent = $agent")
            params["agent"] = agent

        if analysis_type is not None:
            conditions.append("a.analysis_type = $analysis_type")
            params["analysis_type"] = analysis_type

        if severity is not None:
            conditions.append("a.severity = $severity")
            params["severity"] = severity

        if status is not None:
            conditions.append("a.status = $status")
            params["status"] = status

        if assigned_to is not None:
            conditions.append("a.assigned_to = $assigned_to")
            params["assigned_to"] = assigned_to

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        cypher = f"""
        MATCH (a:Analysis)
        {where_clause}
        RETURN a
        ORDER BY
            CASE a.severity
                WHEN 'critical' THEN 4
                WHEN 'high' THEN 3
                WHEN 'medium' THEN 2
                WHEN 'low' THEN 1
                ELSE 0
            END DESC,
            a.created_at DESC
        """

        with self._session() as session:
            if session is None:
                return []

            try:
                result = session.run(cypher, **params)
                analyses = []
                for record in result:
                    analysis_dict = dict(record["a"])
                    # Parse findings and recommendations back from strings if possible
                    if analysis_dict.get("findings"):
                        try:
                            import ast
                            analysis_dict["findings"] = ast.literal_eval(analysis_dict["findings"])
                        except (ValueError, SyntaxError):
                            pass  # Keep as string if parsing fails
                    if analysis_dict.get("recommendations"):
                        try:
                            import ast
                            analysis_dict["recommendations"] = ast.literal_eval(analysis_dict["recommendations"])
                        except (ValueError, SyntaxError):
                            pass
                    analyses.append(analysis_dict)
                return analyses
            except Neo4jError as e:
                logger.error(f"Failed to list analyses: {e}")
                raise

    def update_analysis_status(self, analysis_id: str, status: str, updated_by: str) -> bool:
        """
        Update analysis status.

        Args:
            analysis_id: Analysis ID to update
            status: New status ('open', 'in_progress', 'resolved', 'closed')
            updated_by: Agent who is updating the status

        Returns:
            True if successful, False if analysis not found

        Raises:
            ValueError: If status is invalid
        """
        valid_statuses = ['open', 'in_progress', 'resolved', 'closed']
        if status not in valid_statuses:
            raise ValueError(f"Invalid status '{status}'. Must be one of: {valid_statuses}")

        updated_at = self._now()

        # Set resolved_at if status is resolved or closed
        if status in ('resolved', 'closed'):
            cypher = """
            MATCH (a:Analysis {id: $analysis_id})
            SET a.status = $status,
                a.updated_at = $updated_at,
                a.resolved_at = $updated_at
            RETURN a.id as analysis_id
            """
        else:
            cypher = """
            MATCH (a:Analysis {id: $analysis_id})
            SET a.status = $status,
                a.updated_at = $updated_at
            RETURN a.id as analysis_id
            """

        with self._session() as session:
            if session is None:
                logger.warning(f"Fallback mode: Analysis status update simulated for {analysis_id}")
                return True

            try:
                result = session.run(
                    cypher,
                    analysis_id=analysis_id,
                    status=status,
                    updated_at=updated_at
                )
                record = result.single()

                if record is None:
                    logger.warning(f"Analysis not found: {analysis_id}")
                    return False

                logger.info(f"Analysis {status}: {analysis_id} by {updated_by}")
                return True

            except Neo4jError as e:
                logger.error(f"Failed to update analysis status: {e}")
                raise

    def assign_analysis(self, analysis_id: str, assigned_to: str, assigned_by: str) -> bool:
        """
        Assign analysis to an agent.

        Args:
            analysis_id: Analysis ID to assign
            assigned_to: Agent to assign the analysis to (e.g., 'temujin')
            assigned_by: Agent who is making the assignment

        Returns:
            True if successful, False if analysis not found
        """
        updated_at = self._now()

        cypher = """
        MATCH (a:Analysis {id: $analysis_id})
        SET a.assigned_to = $assigned_to,
            a.updated_at = $updated_at
        RETURN a.id as analysis_id
        """

        with self._session() as session:
            if session is None:
                logger.warning(f"Fallback mode: Analysis assignment simulated for {analysis_id}")
                return True

            try:
                result = session.run(
                    cypher,
                    analysis_id=analysis_id,
                    assigned_to=assigned_to,
                    updated_at=updated_at
                )
                record = result.single()

                if record is None:
                    logger.warning(f"Analysis not found: {analysis_id}")
                    return False

                logger.info(f"Analysis assigned: {analysis_id} to {assigned_to} by {assigned_by}")
                return True

            except Neo4jError as e:
                logger.error(f"Failed to assign analysis: {e}")
                raise

    def get_analysis(self, analysis_id: str) -> Optional[Dict]:
        """
        Get a specific analysis by ID.

        Args:
            analysis_id: Analysis ID to retrieve

        Returns:
            Analysis dict if found, None otherwise
        """
        cypher = """
        MATCH (a:Analysis {id: $analysis_id})
        RETURN a
        """

        with self._session() as session:
            if session is None:
                return None

            try:
                result = session.run(cypher, analysis_id=analysis_id)
                record = result.single()
                if record:
                    analysis_dict = dict(record["a"])
                    # Parse findings and recommendations back from strings if possible
                    if analysis_dict.get("findings"):
                        try:
                            import ast
                            analysis_dict["findings"] = ast.literal_eval(analysis_dict["findings"])
                        except (ValueError, SyntaxError):
                            pass
                    if analysis_dict.get("recommendations"):
                        try:
                            import ast
                            analysis_dict["recommendations"] = ast.literal_eval(analysis_dict["recommendations"])
                        except (ValueError, SyntaxError):
                            pass
                    return analysis_dict
                return None
            except Neo4jError as e:
                logger.error(f"Failed to get analysis: {e}")
                raise

    def get_analysis_summary(self, target_agent: Optional[str] = None) -> Dict:
        """
        Get summary counts of analyses by severity and status.

        Args:
            target_agent: Optional agent to filter by (the agent the analysis is about)

        Returns:
            Dict with counts by severity, status, and type
        """
        # Base query for counts by severity
        if target_agent:
            severity_cypher = """
            MATCH (a:Analysis {target_agent: $target_agent})
            RETURN a.severity as severity, a.status as status, a.analysis_type as analysis_type, count(a) as count
            """
            params = {"target_agent": target_agent}
        else:
            severity_cypher = """
            MATCH (a:Analysis)
            RETURN a.severity as severity, a.status as status, a.analysis_type as analysis_type, count(a) as count
            """
            params = {}

        with self._session() as session:
            if session is None:
                return {
                    "total": 0,
                    "by_severity": {"critical": 0, "high": 0, "medium": 0, "low": 0},
                    "by_status": {"open": 0, "in_progress": 0, "resolved": 0, "closed": 0},
                    "by_type": {"performance": 0, "resource": 0, "error": 0, "security": 0, "other": 0},
                    "open_by_severity": {"critical": 0, "high": 0, "medium": 0, "low": 0}
                }

            try:
                result = session.run(severity_cypher, **params)

                # Initialize counters
                by_severity = {"critical": 0, "high": 0, "medium": 0, "low": 0}
                by_status = {"open": 0, "in_progress": 0, "resolved": 0, "closed": 0}
                by_type = {"performance": 0, "resource": 0, "error": 0, "security": 0, "other": 0}
                open_by_severity = {"critical": 0, "high": 0, "medium": 0, "low": 0}

                total = 0
                for record in result:
                    severity = record["severity"]
                    status = record["status"]
                    analysis_type = record["analysis_type"]
                    count = record["count"]

                    total += count
                    if severity in by_severity:
                        by_severity[severity] += count
                    if status in by_status:
                        by_status[status] += count
                    if analysis_type in by_type:
                        by_type[analysis_type] += count
                    if status == "open" and severity in open_by_severity:
                        open_by_severity[severity] += count

                return {
                    "total": total,
                    "by_severity": by_severity,
                    "by_status": by_status,
                    "by_type": by_type,
                    "open_by_severity": open_by_severity
                }

            except Neo4jError as e:
                logger.error(f"Failed to get analysis summary: {e}")
                raise

    def detect_performance_issues(self, metrics: Dict) -> List[Dict]:
        """
        Analyze metrics and return potential performance issues.

        This method analyzes various performance metrics and returns a list
        of detected issues with severity and recommendations.

        Args:
            metrics: Dictionary containing performance metrics such as:
                - connection_pool_usage: Percentage of connections in use (0-100)
                - query_time_ms: Average query execution time in milliseconds
                - error_rate: Error rate as percentage (0-100)
                - memory_usage_mb: Memory usage in MB
                - cpu_usage_percent: CPU usage percentage (0-100)
                - active_sessions: Number of active Neo4j sessions
                - retry_count: Number of retries in time window
                - circuit_breaker_trips: Number of circuit breaker trips

        Returns:
            List of detected issues, each containing:
                - issue_type: Type of issue detected
                - severity: 'low', 'medium', 'high', or 'critical'
                - description: Human-readable description
                - metric_value: The value that triggered the issue
                - threshold: The threshold that was exceeded
                - recommendations: List of suggested fixes
        """
        issues = []

        # Connection pool exhaustion check
        if "connection_pool_usage" in metrics:
            usage = metrics["connection_pool_usage"]
            if usage >= 95:
                issues.append({
                    "issue_type": "connection_pool_exhaustion",
                    "severity": "critical",
                    "description": f"Connection pool nearly exhausted ({usage:.1f}% used). System may become unresponsive.",
                    "metric_value": usage,
                    "threshold": 95,
                    "recommendations": [
                        "Increase max_connection_pool_size in OperationalMemory config",
                        "Check for connection leaks - ensure all sessions are properly closed",
                        "Implement connection timeout reduction",
                        "Review and optimize query patterns to reduce connection hold time"
                    ]
                })
            elif usage >= 80:
                issues.append({
                    "issue_type": "connection_pool_high_usage",
                    "severity": "high",
                    "description": f"Connection pool usage is high ({usage:.1f}% used).",
                    "metric_value": usage,
                    "threshold": 80,
                    "recommendations": [
                        "Monitor connection pool usage trends",
                        "Review connection pool configuration",
                        "Optimize queries to release connections faster"
                    ]
                })
            elif usage >= 60:
                issues.append({
                    "issue_type": "connection_pool_elevated_usage",
                    "severity": "medium",
                    "description": f"Connection pool usage is elevated ({usage:.1f}% used).",
                    "metric_value": usage,
                    "threshold": 60,
                    "recommendations": [
                        "Monitor connection pool usage",
                        "Review for potential connection leaks"
                    ]
                })

        # Slow query detection
        if "query_time_ms" in metrics:
            query_time = metrics["query_time_ms"]
            if query_time >= 5000:
                issues.append({
                    "issue_type": "slow_query_critical",
                    "severity": "critical",
                    "description": f"Critical: Average query time is {query_time:.0f}ms. Queries are severely impacting performance.",
                    "metric_value": query_time,
                    "threshold": 5000,
                    "recommendations": [
                        "Add missing indexes for frequently queried fields",
                        "Optimize Cypher queries - avoid Cartesian products",
                        "Consider query result pagination",
                        "Review and optimize data model",
                        "Enable query logging to identify slow queries"
                    ]
                })
            elif query_time >= 1000:
                issues.append({
                    "issue_type": "slow_query_warning",
                    "severity": "high",
                    "description": f"Warning: Average query time is {query_time:.0f}ms. Queries may be impacting performance.",
                    "metric_value": query_time,
                    "threshold": 1000,
                    "recommendations": [
                        "Review slow query log",
                        "Add indexes for frequently filtered properties",
                        "Optimize complex queries"
                    ]
                })
            elif query_time >= 500:
                issues.append({
                    "issue_type": "slow_query_notice",
                    "severity": "medium",
                    "description": f"Notice: Average query time is {query_time:.0f}ms.",
                    "metric_value": query_time,
                    "threshold": 500,
                    "recommendations": [
                        "Monitor query performance trends",
                        "Review query patterns for optimization opportunities"
                    ]
                })

        # Error rate detection
        if "error_rate" in metrics:
            error_rate = metrics["error_rate"]
            if error_rate >= 10:
                issues.append({
                    "issue_type": "high_error_rate",
                    "severity": "critical",
                    "description": f"Critical error rate detected: {error_rate:.1f}% of operations are failing.",
                    "metric_value": error_rate,
                    "threshold": 10,
                    "recommendations": [
                        "Immediately review error logs",
                        "Check Neo4j server health and connectivity",
                        "Verify authentication credentials",
                        "Check for network issues",
                        "Review recent code changes"
                    ]
                })
            elif error_rate >= 5:
                issues.append({
                    "issue_type": "elevated_error_rate",
                    "severity": "high",
                    "description": f"Elevated error rate detected: {error_rate:.1f}% of operations are failing.",
                    "metric_value": error_rate,
                    "threshold": 5,
                    "recommendations": [
                        "Review error logs for patterns",
                        "Check Neo4j server status",
                        "Monitor error rate trends"
                    ]
                })
            elif error_rate >= 1:
                issues.append({
                    "issue_type": "increased_error_rate",
                    "severity": "medium",
                    "description": f"Increased error rate detected: {error_rate:.1f}% of operations are failing.",
                    "metric_value": error_rate,
                    "threshold": 1,
                    "recommendations": [
                        "Monitor error logs",
                        "Review transient error handling"
                    ]
                })

        # Memory usage detection
        if "memory_usage_mb" in metrics:
            memory_mb = metrics["memory_usage_mb"]
            if memory_mb >= 2048:  # 2GB
                issues.append({
                    "issue_type": "high_memory_usage",
                    "severity": "high",
                    "description": f"High memory usage detected: {memory_mb:.0f}MB. Potential memory leak.",
                    "metric_value": memory_mb,
                    "threshold": 2048,
                    "recommendations": [
                        "Profile memory usage to identify leaks",
                        "Check for large result sets being held in memory",
                        "Review caching strategies",
                        "Consider implementing result streaming"
                    ]
                })
            elif memory_mb >= 1024:  # 1GB
                issues.append({
                    "issue_type": "elevated_memory_usage",
                    "severity": "medium",
                    "description": f"Elevated memory usage detected: {memory_mb:.0f}MB.",
                    "metric_value": memory_mb,
                    "threshold": 1024,
                    "recommendations": [
                        "Monitor memory usage trends",
                        "Review memory-intensive operations"
                    ]
                })

        # Circuit breaker detection
        if "circuit_breaker_trips" in metrics:
            trips = metrics["circuit_breaker_trips"]
            if trips >= 5:
                issues.append({
                    "issue_type": "circuit_breaker_frequent_trips",
                    "severity": "critical",
                    "description": f"Circuit breaker has tripped {trips} times. System is in degraded state.",
                    "metric_value": trips,
                    "threshold": 5,
                    "recommendations": [
                        "Investigate root cause of failures",
                        "Check Neo4j server availability",
                        "Review timeout configurations",
                        "Consider implementing fallback strategies"
                    ]
                })
            elif trips >= 2:
                issues.append({
                    "issue_type": "circuit_breaker_trips",
                    "severity": "high",
                    "description": f"Circuit breaker has tripped {trips} times.",
                    "metric_value": trips,
                    "threshold": 2,
                    "recommendations": [
                        "Monitor circuit breaker status",
                        "Review error patterns leading to trips"
                    ]
                })

        # Retry storm detection
        if "retry_count" in metrics:
            retries = metrics["retry_count"]
            if retries >= 50:
                issues.append({
                    "issue_type": "retry_storm",
                    "severity": "high",
                    "description": f"High retry count detected ({retries} retries). System may be unstable.",
                    "metric_value": retries,
                    "threshold": 50,
                    "recommendations": [
                        "Check Neo4j server stability",
                        "Review retry logic and backoff strategies",
                        "Investigate root cause of transient failures"
                    ]
                })

        return issues

    def create_analysis_from_issues(
        self,
        agent: str,
        issues: List[Dict],
        target_agent: Optional[str] = None,
        assigned_to: Optional[str] = None
    ) -> List[str]:
        """
        Create Analysis nodes from detected issues.

        Convenience method to create analyses for all detected issues.

        Args:
            agent: Agent creating the analyses (e.g., 'jochi')
            issues: List of issues from detect_performance_issues()
            target_agent: Agent the analysis is about (if applicable)
            assigned_to: Agent assigned to fix (default: 'temujin' for backend issues)

        Returns:
            List of created analysis IDs
        """
        if assigned_to is None:
            assigned_to = "temujin"  # Default assignee for backend issues

        analysis_ids = []
        for issue in issues:
            analysis_type = issue.get("issue_type", "other")
            # Map issue types to analysis types
            if "connection" in analysis_type or "pool" in analysis_type:
                analysis_type = "resource"
            elif "query" in analysis_type or "slow" in analysis_type:
                analysis_type = "performance"
            elif "error" in analysis_type:
                analysis_type = "error"
            elif "circuit" in analysis_type or "retry" in analysis_type:
                analysis_type = "resource"
            else:
                analysis_type = "performance"

            findings = {
                "metric_value": issue.get("metric_value"),
                "threshold": issue.get("threshold"),
                "issue_type": issue.get("issue_type")
            }

            try:
                analysis_id = self.create_analysis(
                    agent=agent,
                    analysis_type=analysis_type,
                    severity=issue.get("severity", "medium"),
                    description=issue.get("description", ""),
                    target_agent=target_agent,
                    findings=findings,
                    recommendations=issue.get("recommendations", []),
                    assigned_to=assigned_to
                )
                analysis_ids.append(analysis_id)
            except Exception as e:
                logger.error(f"Failed to create analysis for issue {issue.get('issue_type')}: {e}")

        return analysis_ids

    # =======================================================================
    # Security Audit (Temüjin Protocol)
    # =======================================================================

    def create_security_audit(
        self,
        agent: str,
        severity: str,
        category: str,
        description: str,
        resource: str
    ) -> str:
        """
        Create a new security audit entry.

        Args:
            agent: Agent being audited
            severity: Severity level ('low', 'medium', 'high', 'critical')
            category: Type of security issue ('auth', 'injection', 'secrets', 'config', 'crypto', 'other')
            description: Human-readable description of the issue
            resource: Affected resource (file path, endpoint, etc.)

        Returns:
            Audit ID string

        Raises:
            ValueError: If severity or category is invalid
        """
        # Validate severity
        valid_severities = ['low', 'medium', 'high', 'critical']
        if severity not in valid_severities:
            raise ValueError(f"Invalid severity '{severity}'. Must be one of: {valid_severities}")

        # Validate category
        valid_categories = ['auth', 'injection', 'secrets', 'config', 'crypto', 'other']
        if category not in valid_categories:
            raise ValueError(f"Invalid category '{category}'. Must be one of: {valid_categories}")

        audit_id = self._generate_id()
        created_at = self._now()

        cypher = """
        CREATE (s:SecurityAudit {
            id: $audit_id,
            agent: $agent,
            severity: $severity,
            category: $category,
            description: $description,
            resource: $resource,
            created_at: $created_at,
            status: 'open',
            resolved_by: null,
            resolved_at: null
        })
        RETURN s.id as audit_id
        """

        with self._session() as session:
            if session is None:
                logger.warning(f"Fallback mode: Security audit creation simulated for {agent}")
                return audit_id

            try:
                result = session.run(
                    cypher,
                    audit_id=audit_id,
                    agent=agent,
                    severity=severity,
                    category=category,
                    description=description,
                    resource=resource,
                    created_at=created_at
                )
                record = result.single()
                if record:
                    logger.info(f"Security audit created: {audit_id} (agent: {agent}, severity: {severity})")
                    return record["audit_id"]
                else:
                    raise RuntimeError("Security audit creation failed: no record returned")
            except Neo4jError as e:
                logger.error(f"Failed to create security audit: {e}")
                raise

    def list_security_audits(
        self,
        agent: Optional[str] = None,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        category: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None
    ) -> List[Dict]:
        """
        Query security audits with optional filters.

        Args:
            agent: Filter by agent being audited
            status: Filter by status ('open', 'resolved', 'ignored')
            severity: Filter by severity ('low', 'medium', 'high', 'critical')
            category: Filter by category ('auth', 'injection', 'secrets', 'config', 'crypto', 'other')
            date_from: Filter by created_at >= date_from
            date_to: Filter by created_at <= date_to

        Returns:
            List of security audit dicts, sorted by severity (critical first) then created_at
        """
        # Build dynamic query based on filters
        conditions = []
        params = {}

        if agent is not None:
            conditions.append("s.agent = $agent")
            params["agent"] = agent

        if status is not None:
            conditions.append("s.status = $status")
            params["status"] = status

        if severity is not None:
            conditions.append("s.severity = $severity")
            params["severity"] = severity

        if category is not None:
            conditions.append("s.category = $category")
            params["category"] = category

        if date_from is not None:
            conditions.append("s.created_at >= $date_from")
            params["date_from"] = date_from

        if date_to is not None:
            conditions.append("s.created_at <= $date_to")
            params["date_to"] = date_to

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        cypher = f"""
        MATCH (s:SecurityAudit)
        {where_clause}
        RETURN s
        ORDER BY
            CASE s.severity
                WHEN 'critical' THEN 4
                WHEN 'high' THEN 3
                WHEN 'medium' THEN 2
                WHEN 'low' THEN 1
                ELSE 0
            END DESC,
            s.created_at DESC
        """

        with self._session() as session:
            if session is None:
                return []

            try:
                result = session.run(cypher, **params)
                return [dict(record["s"]) for record in result]
            except Neo4jError as e:
                logger.error(f"Failed to list security audits: {e}")
                raise

    def resolve_security_audit(
        self,
        audit_id: str,
        resolved_by: str,
        status: str = "resolved"
    ) -> bool:
        """
        Mark a security audit as resolved or ignored.

        Args:
            audit_id: Audit ID to resolve
            resolved_by: Agent who is resolving the audit
            status: New status ('resolved' or 'ignored')

        Returns:
            True if successful, False if audit not found

        Raises:
            ValueError: If status is not 'resolved' or 'ignored'
        """
        if status not in ('resolved', 'ignored'):
            raise ValueError("Status must be 'resolved' or 'ignored'")

        resolved_at = self._now()

        cypher = """
        MATCH (s:SecurityAudit {id: $audit_id})
        WHERE s.status = 'open'
        SET s.status = $status,
            s.resolved_by = $resolved_by,
            s.resolved_at = $resolved_at
        RETURN s.id as audit_id
        """

        with self._session() as session:
            if session is None:
                logger.warning(f"Fallback mode: Security audit resolution simulated for {audit_id}")
                return True

            try:
                result = session.run(
                    cypher,
                    audit_id=audit_id,
                    status=status,
                    resolved_by=resolved_by,
                    resolved_at=resolved_at
                )
                record = result.single()

                if record is None:
                    logger.warning(f"Security audit not found or not open: {audit_id}")
                    return False

                logger.info(f"Security audit {status}: {audit_id} by {resolved_by}")
                return True

            except Neo4jError as e:
                logger.error(f"Failed to resolve security audit: {e}")
                raise

    def get_security_audit(self, audit_id: str) -> Optional[Dict]:
        """
        Get a security audit by ID.

        Args:
            audit_id: Audit ID to retrieve

        Returns:
            Security audit dict if found, None otherwise
        """
        cypher = """
        MATCH (s:SecurityAudit {id: $audit_id})
        RETURN s
        """

        with self._session() as session:
            if session is None:
                return None

            try:
                result = session.run(cypher, audit_id=audit_id)
                record = result.single()
                return dict(record["s"]) if record else None
            except Neo4jError as e:
                logger.error(f"Failed to get security audit: {e}")
                raise

    def get_security_summary(self, agent: Optional[str] = None) -> Dict:
        """
        Get summary counts of security audits by severity and status.

        Args:
            agent: Optional agent to filter by

        Returns:
            Dict with counts by severity and status
        """
        # Base query for counts by severity
        if agent:
            severity_cypher = """
            MATCH (s:SecurityAudit {agent: $agent})
            RETURN s.severity as severity, s.status as status, count(s) as count
            """
            params = {"agent": agent}
        else:
            severity_cypher = """
            MATCH (s:SecurityAudit)
            RETURN s.severity as severity, s.status as status, count(s) as count
            """
            params = {}

        with self._session() as session:
            if session is None:
                return {
                    "total": 0,
                    "by_severity": {"critical": 0, "high": 0, "medium": 0, "low": 0},
                    "by_status": {"open": 0, "resolved": 0, "ignored": 0},
                    "open_by_severity": {"critical": 0, "high": 0, "medium": 0, "low": 0}
                }

            try:
                result = session.run(severity_cypher, **params)

                # Initialize counters
                by_severity = {"critical": 0, "high": 0, "medium": 0, "low": 0}
                by_status = {"open": 0, "resolved": 0, "ignored": 0}
                open_by_severity = {"critical": 0, "high": 0, "medium": 0, "low": 0}

                total = 0
                for record in result:
                    severity = record["severity"]
                    status = record["status"]
                    count = record["count"]

                    total += count
                    if severity in by_severity:
                        by_severity[severity] += count
                    if status in by_status:
                        by_status[status] += count
                    if status == "open" and severity in open_by_severity:
                        open_by_severity[severity] += count

                return {
                    "total": total,
                    "by_severity": by_severity,
                    "by_status": by_status,
                    "open_by_severity": open_by_severity
                }

            except Neo4jError as e:
                logger.error(f"Failed to get security summary: {e}")
                raise

    def get_security_audit_trail(
        self,
        agent: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None
    ) -> List[Dict]:
        """
        Get audit trail of security-related actions.

        Returns both created and resolved audits within the date range.

        Args:
            agent: Filter by agent (optional)
            date_from: Start date for audit trail
            date_to: End date for audit trail

        Returns:
            List of audit trail entries with action type
        """
        # Build conditions
        conditions = []
        params = {}

        if agent is not None:
            conditions.append("s.agent = $agent")
            params["agent"] = agent

        if date_from is not None:
            conditions.append("(s.created_at >= $date_from OR s.resolved_at >= $date_from)")
            params["date_from"] = date_from

        if date_to is not None:
            conditions.append("(s.created_at <= $date_to OR s.resolved_at <= $date_to)")
            params["date_to"] = date_to

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        cypher = f"""
        MATCH (s:SecurityAudit)
        {where_clause}
        RETURN s,
            CASE
                WHEN s.resolved_at IS NOT NULL THEN s.resolved_at
                ELSE s.created_at
            END as action_time,
            CASE
                WHEN s.resolved_at IS NOT NULL THEN 'resolved'
                ELSE 'created'
            END as action_type
        ORDER BY action_time DESC
        """

        with self._session() as session:
            if session is None:
                return []

            try:
                result = session.run(cypher, **params)
                trail = []
                for record in result:
                    entry = dict(record["s"])
                    entry["action_time"] = record["action_time"]
                    entry["action_type"] = record["action_type"]
                    trail.append(entry)
                return trail
            except Neo4jError as e:
                logger.error(f"Failed to get security audit trail: {e}")
                raise

    # =======================================================================
    # Schema Management
    # =======================================================================

    def create_indexes(self) -> List[str]:
        """
        Create recommended indexes for performance.

        Returns:
            List of created index names
        """
        indexes = [
            # Task indexes
            ("CREATE INDEX task_id_idx IF NOT EXISTS FOR (t:Task) ON (t.id)", "task_id_idx"),
            ("CREATE INDEX task_status_idx IF NOT EXISTS FOR (t:Task) ON (t.status)", "task_status_idx"),
            ("CREATE INDEX task_assigned_to_idx IF NOT EXISTS FOR (t:Task) ON (t.assigned_to)", "task_assigned_to_idx"),
            ("CREATE INDEX task_claimed_by_idx IF NOT EXISTS FOR (t:Task) ON (t.claimed_by)", "task_claimed_by_idx"),
            ("CREATE INDEX task_status_priority_created_idx IF NOT EXISTS FOR (t:Task) ON (t.status, t.priority, t.created_at)", "task_status_priority_created_idx"),
            ("CREATE INDEX task_claim_idx IF NOT EXISTS FOR (t:Task) ON (t.status, t.assigned_to, t.priority, t.created_at)", "task_claim_idx"),

            # Notification indexes
            ("CREATE INDEX notification_id_idx IF NOT EXISTS FOR (n:Notification) ON (n.id)", "notification_id_idx"),
            ("CREATE INDEX notification_agent_read_idx IF NOT EXISTS FOR (n:Notification) ON (n.agent, n.read)", "notification_agent_read_idx"),

            # Rate limit indexes
            ("CREATE INDEX ratelimit_composite_idx IF NOT EXISTS FOR (r:RateLimit) ON (r.agent, r.operation, r.date, r.hour)", "ratelimit_composite_idx"),

            # Agent indexes
            ("CREATE INDEX agent_name_idx IF NOT EXISTS FOR (a:Agent) ON (a.name)", "agent_name_idx"),
            ("CREATE INDEX agent_heartbeat_idx IF NOT EXISTS FOR (a:Agent) ON (a.last_heartbeat)", "agent_heartbeat_idx"),

            # SecurityAudit indexes
            ("CREATE INDEX securityaudit_id_idx IF NOT EXISTS FOR (s:SecurityAudit) ON (s.id)", "securityaudit_id_idx"),
            ("CREATE INDEX securityaudit_agent_idx IF NOT EXISTS FOR (s:SecurityAudit) ON (s.agent)", "securityaudit_agent_idx"),
            ("CREATE INDEX securityaudit_status_idx IF NOT EXISTS FOR (s:SecurityAudit) ON (s.status)", "securityaudit_status_idx"),
            ("CREATE INDEX securityaudit_severity_idx IF NOT EXISTS FOR (s:SecurityAudit) ON (s.severity)", "securityaudit_severity_idx"),
            ("CREATE INDEX securityaudit_category_idx IF NOT EXISTS FOR (s:SecurityAudit) ON (s.category)", "securityaudit_category_idx"),
            ("CREATE INDEX securityaudit_created_at_idx IF NOT EXISTS FOR (s:SecurityAudit) ON (s.created_at)", "securityaudit_created_at_idx"),
            ("CREATE INDEX securityaudit_agent_status_idx IF NOT EXISTS FOR (s:SecurityAudit) ON (s.agent, s.status)", "securityaudit_agent_status_idx"),
            ("CREATE INDEX securityaudit_severity_status_idx IF NOT EXISTS FOR (s:SecurityAudit) ON (s.severity, s.status)", "securityaudit_severity_status_idx"),

            # Analysis indexes (Jochi Backend Issue Identification)
            ("CREATE INDEX analysis_id_idx IF NOT EXISTS FOR (a:Analysis) ON (a.id)", "analysis_id_idx"),
            ("CREATE INDEX analysis_agent_idx IF NOT EXISTS FOR (a:Analysis) ON (a.agent)", "analysis_agent_idx"),
            ("CREATE INDEX analysis_target_agent_idx IF NOT EXISTS FOR (a:Analysis) ON (a.target_agent)", "analysis_target_agent_idx"),
            ("CREATE INDEX analysis_type_idx IF NOT EXISTS FOR (a:Analysis) ON (a.analysis_type)", "analysis_type_idx"),
            ("CREATE INDEX analysis_severity_idx IF NOT EXISTS FOR (a:Analysis) ON (a.severity)", "analysis_severity_idx"),
            ("CREATE INDEX analysis_status_idx IF NOT EXISTS FOR (a:Analysis) ON (a.status)", "analysis_status_idx"),
            ("CREATE INDEX analysis_assigned_to_idx IF NOT EXISTS FOR (a:Analysis) ON (a.assigned_to)", "analysis_assigned_to_idx"),
            ("CREATE INDEX analysis_created_at_idx IF NOT EXISTS FOR (a:Analysis) ON (a.created_at)", "analysis_created_at_idx"),
            ("CREATE INDEX analysis_severity_status_idx IF NOT EXISTS FOR (a:Analysis) ON (a.severity, a.status)", "analysis_severity_status_idx"),
            ("CREATE INDEX analysis_type_status_idx IF NOT EXISTS FOR (a:Analysis) ON (a.analysis_type, a.status)", "analysis_type_status_idx"),
        ]

        created = []

        with self._session() as session:
            if session is None:
                logger.warning("Cannot create indexes: Neo4j unavailable")
                return created

            for cypher, name in indexes:
                try:
                    session.run(cypher)
                    created.append(name)
                    logger.info(f"Created index: {name}")
                except Neo4jError as e:
                    if "already exists" not in str(e).lower():
                        logger.error(f"Failed to create index {name}: {e}")

        return created

    def close(self) -> None:
        """Close the Neo4j driver and release resources."""
        if self._driver:
            self._driver.close()
            self._driver = None
            logger.info("Neo4j driver closed")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    # Configure logging for example
    logging.basicConfig(level=logging.INFO)

    # Example usage
    with OperationalMemory(
        uri="bolt://localhost:7687",
        username="neo4j",
        password="password",
        fallback_mode=True
    ) as mem:

        # Health check
        health = mem.health_check()
        print(f"Health: {health}")

        if health["status"] == "healthy":
            # Create indexes
            indexes = mem.create_indexes()
            print(f"Created indexes: {indexes}")

            # Create a task
            task_id = mem.create_task(
                task_type="code_review",
                description="Review the authentication module",
                delegated_by="architect",
                assigned_to="implementer",
                priority="high"
            )
            print(f"Created task: {task_id}")

            # List pending tasks
            pending = mem.list_pending_tasks(agent="implementer")
            print(f"Pending tasks: {len(pending)}")

            # Claim task
            try:
                task = mem.claim_task("implementer")
                print(f"Claimed task: {task['id'] if task else 'None'}")
            except NoPendingTaskError:
                print("No pending tasks")

            # Complete task
            if task:
                success = mem.complete_task(
                    task_id=task['id'],
                    results={"approved": True, "comments": "Looks good!"}
                )
                print(f"Task completed: {success}")

            # Create notification
            notif_id = mem.create_notification(
                agent="architect",
                type="task_completed",
                summary="Code review completed",
                task_id=task_id
            )
            print(f"Created notification: {notif_id}")

            # Get notifications
            notifications = mem.get_notifications("architect")
            print(f"Notifications: {len(notifications)}")

            # Update agent heartbeat
            mem.update_agent_heartbeat("implementer", "active")
            print("Agent heartbeat updated")

            # Check rate limit
            allowed, count, reset = mem.check_rate_limit("implementer", "api_call", max_requests=100)
            print(f"Rate limit: allowed={allowed}, count={count}, reset={reset}")

            # Record rate limit hit
            mem.record_rate_limit_hit("implementer", "api_call")
            print("Rate limit hit recorded")

        else:
            print("Neo4j not available, running in fallback mode")
