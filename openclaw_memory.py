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

# Configure logging
logger = logging.getLogger(__name__)

# Lazy imports for neo4j to avoid numpy recursion issues during test collection
# The neo4j driver imports numpy which can cause RecursionError when pytest's -W error is enabled
_neo4j_imported = False
_GraphDatabase = None
_Driver = None
_Session = None
_ServiceUnavailable = None
_Neo4jError = None
_TransientError = None


def _import_neo4j():
    """Lazy import neo4j modules to avoid numpy recursion issues."""
    global _neo4j_imported, _GraphDatabase, _Driver, _Session
    global _ServiceUnavailable, _Neo4jError, _TransientError
    if not _neo4j_imported:
        import warnings
        # Suppress numpy reload warning during neo4j import
        # This is a known issue when neo4j imports numpy in certain contexts
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*NumPy module was reloaded.*")
            from neo4j import GraphDatabase, Driver, Session
            from neo4j.exceptions import ServiceUnavailable, Neo4jError, TransientError
        _GraphDatabase = GraphDatabase
        _Driver = Driver
        _Session = Session
        _ServiceUnavailable = ServiceUnavailable
        _Neo4jError = Neo4jError
        _TransientError = TransientError
        _neo4j_imported = True


def _get_graph_database():
    """Get the GraphDatabase class, importing if necessary."""
    _import_neo4j()
    return _GraphDatabase


def _get_driver_class():
    """Get the Driver class, importing if necessary."""
    _import_neo4j()
    return _Driver


def _get_session_class():
    """Get the Session class, importing if necessary."""
    _import_neo4j()
    return _Session


def _get_service_unavailable():
    """Get the ServiceUnavailable exception, importing if necessary."""
    _import_neo4j()
    return _ServiceUnavailable


def _get_neo4j_error():
    """Get the Neo4jError exception, importing if necessary."""
    _import_neo4j()
    return _Neo4jError


def _get_transient_error():
    """Get the TransientError exception, importing if necessary."""
    _import_neo4j()
    return _TransientError


# Module-level lazy exports for backward compatibility with tests
# These allow tests to patch 'openclaw_memory.GraphDatabase' etc.
class _LazyGraphDatabase:
    """Lazy wrapper for GraphDatabase to support test patching."""
    _driver = None
    _patched = False

    @property
    def driver(self):
        if self._patched:
            return self._driver
        return _get_graph_database().driver

    @driver.setter
    def driver(self, value):
        self._driver = value
        self._patched = True

    @driver.deleter
    def driver(self):
        self._driver = None
        self._patched = False

    def __getattr__(self, name):
        return getattr(_get_graph_database(), name)


class _LazyExceptions:
    """Lazy wrapper for neo4j exceptions to support test patching."""
    _service_unavailable = None
    _neo4j_error = None
    _transient_error = None

    @property
    def ServiceUnavailable(self):
        if self._service_unavailable is not None:
            return self._service_unavailable
        return _get_service_unavailable()

    @ServiceUnavailable.setter
    def ServiceUnavailable(self, value):
        self._service_unavailable = value

    @property
    def Neo4jError(self):
        if self._neo4j_error is not None:
            return self._neo4j_error
        return _get_neo4j_error()

    @Neo4jError.setter
    def Neo4jError(self, value):
        self._neo4j_error = value

    @property
    def TransientError(self):
        if self._transient_error is not None:
            return self._transient_error
        return _get_transient_error()

    @TransientError.setter
    def TransientError(self, value):
        self._transient_error = value


# Create module-level exports for backward compatibility
GraphDatabase = _LazyGraphDatabase()
exceptions = _LazyExceptions()


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
        self._driver: Optional[Any] = None
        self._pool_config = {
            "max_connection_pool_size": max_connection_pool_size,
            "connection_timeout": connection_timeout,
            "max_transaction_retry_time": max_retry_time
        }
        self._initialize_driver()

    def _initialize_driver(self) -> None:
        """Initialize Neo4j driver with connection pooling."""
        try:
            self._driver = _get_graph_database().driver(
                self.uri,
                auth=(self.username, self.password),
                **self._pool_config
            )
            # Verify connectivity
            self._driver.verify_connectivity()
            logger.info(f"Neo4j driver initialized: {self.uri}")
        except _get_service_unavailable() as e:
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
        except _get_service_unavailable() as e:
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
            except _get_neo4j_error() as e:
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
            except _get_neo4j_error() as e:
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

            except _get_neo4j_error() as e:
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

            except _get_neo4j_error() as e:
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
            except _get_neo4j_error() as e:
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
            except _get_neo4j_error() as e:
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
            except _get_neo4j_error() as e:
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
            except _get_neo4j_error() as e:
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
            except _get_neo4j_error() as e:
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
            except _get_neo4j_error() as e:
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
            except _get_neo4j_error() as e:
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

            except _get_neo4j_error() as e:
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
            except _get_neo4j_error() as e:
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
            except _get_neo4j_error() as e:
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
            except _get_neo4j_error() as e:
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
            except _get_neo4j_error() as e:
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
            except _get_neo4j_error() as e:
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

        except _get_service_unavailable() as e:
            health["status"] = "unavailable"
            health["error"] = str(e)
            self._driver = None
        except _get_neo4j_error() as e:
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
            except _get_neo4j_error() as e:
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
            except _get_neo4j_error() as e:
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

            except _get_neo4j_error() as e:
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

            except _get_neo4j_error() as e:
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
            except _get_neo4j_error() as e:
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

            except _get_neo4j_error() as e:
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
            except _get_neo4j_error() as e:
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
            except _get_neo4j_error() as e:
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

            except _get_neo4j_error() as e:
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
            except _get_neo4j_error() as e:
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

            except _get_neo4j_error() as e:
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
            except _get_neo4j_error() as e:
                logger.error(f"Failed to get security audit trail: {e}")
                raise

    # =======================================================================
    # Proactive Improvement (Ögedei Protocol)
    # =======================================================================

    def create_improvement(
        self,
        submitted_by: str,
        title: str,
        description: str,
        category: str,
        expected_benefit: str,
        effort_hours: float,
        improvement_value: float
    ) -> str:
        """
        Create a new improvement proposal.

        Ögedei uses this to record workflow improvements that require
        Kublai approval before implementation.

        Args:
            submitted_by: Agent who submitted the improvement (usually 'ogedei')
            title: Short title of the improvement
            description: Detailed description of the improvement
            category: Category ('workflow', 'performance', 'security', 'documentation', 'other')
            expected_benefit: Description of expected benefit
            effort_hours: Estimated effort to implement
            improvement_value: Estimated value of the improvement

        Returns:
            Improvement ID string

        Raises:
            ValueError: If category is invalid or effort_hours is not positive
        """
        # Validate category
        valid_categories = ['workflow', 'performance', 'security', 'documentation', 'other']
        if category not in valid_categories:
            raise ValueError(f"Invalid category '{category}'. Must be one of: {valid_categories}")

        # Validate effort_hours
        if effort_hours <= 0:
            raise ValueError("effort_hours must be greater than 0")

        # Calculate value_score (ROI)
        value_score = improvement_value / effort_hours if effort_hours > 0 else 0

        improvement_id = self._generate_id()
        created_at = self._now()

        cypher = """
        CREATE (i:Improvement {
            id: $improvement_id,
            submitted_by: $submitted_by,
            title: $title,
            description: $description,
            category: $category,
            expected_benefit: $expected_benefit,
            effort_hours: $effort_hours,
            improvement_value: $improvement_value,
            value_score: $value_score,
            status: 'proposed',
            approved_by: null,
            approved_at: null,
            implemented_at: null,
            rejection_reason: null,
            created_at: $created_at
        })
        RETURN i.id as improvement_id
        """

        with self._session() as session:
            if session is None:
                logger.warning(f"Fallback mode: Improvement creation simulated for {submitted_by}")
                return improvement_id

            try:
                result = session.run(
                    cypher,
                    improvement_id=improvement_id,
                    submitted_by=submitted_by,
                    title=title,
                    description=description,
                    category=category,
                    expected_benefit=expected_benefit,
                    effort_hours=effort_hours,
                    improvement_value=improvement_value,
                    value_score=value_score,
                    created_at=created_at
                )
                record = result.single()
                if record:
                    logger.info(f"Improvement created: {improvement_id} (category: {category}, value_score: {value_score:.2f})")

                    # Notify Kublai of pending approval
                    self.create_notification(
                        agent="kublai",
                        type="improvement_pending_approval",
                        summary=f"Improvement '{title}' ({category}) pending approval - Value Score: {value_score:.2f}",
                        task_id=improvement_id
                    )

                    return record["improvement_id"]
                else:
                    raise RuntimeError("Improvement creation failed: no record returned")
            except _get_neo4j_error() as e:
                logger.error(f"Failed to create improvement: {e}")
                raise

    def list_improvements(
        self,
        status: Optional[str] = None,
        category: Optional[str] = None,
        submitted_by: Optional[str] = None
    ) -> List[Dict]:
        """
        Query improvements with optional filters.

        Args:
            status: Filter by status ('proposed', 'approved', 'rejected', 'implemented')
            category: Filter by category ('workflow', 'performance', 'security', 'documentation', 'other')
            submitted_by: Filter by submitting agent

        Returns:
            List of improvement dicts, sorted by value_score (highest first) then created_at
        """
        # Validate status if provided
        if status is not None:
            valid_statuses = ['proposed', 'approved', 'rejected', 'implemented']
            if status not in valid_statuses:
                raise ValueError(f"Invalid status '{status}'. Must be one of: {valid_statuses}")

        # Validate category if provided
        if category is not None:
            valid_categories = ['workflow', 'performance', 'security', 'documentation', 'other']
            if category not in valid_categories:
                raise ValueError(f"Invalid category '{category}'. Must be one of: {valid_categories}")

        # Build dynamic query based on filters
        conditions = []
        params = {}

        if status is not None:
            conditions.append("i.status = $status")
            params["status"] = status

        if category is not None:
            conditions.append("i.category = $category")
            params["category"] = category

        if submitted_by is not None:
            conditions.append("i.submitted_by = $submitted_by")
            params["submitted_by"] = submitted_by

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        cypher = f"""
        MATCH (i:Improvement)
        {where_clause}
        RETURN i
        ORDER BY i.value_score DESC, i.created_at DESC
        """

        with self._session() as session:
            if session is None:
                return []

            try:
                result = session.run(cypher, **params)
                return [dict(record["i"]) for record in result]
            except _get_neo4j_error() as e:
                logger.error(f"Failed to list improvements: {e}")
                raise

    def approve_improvement(self, improvement_id: str, approved_by: str) -> bool:
        """
        Approve an improvement (Kublai action).

        Args:
            improvement_id: Improvement ID to approve
            approved_by: Agent who is approving (usually 'kublai')

        Returns:
            True if successful, False if improvement not found or not in proposed status
        """
        approved_at = self._now()

        cypher = """
        MATCH (i:Improvement {id: $improvement_id})
        WHERE i.status = 'proposed'
        SET i.status = 'approved',
            i.approved_by = $approved_by,
            i.approved_at = $approved_at
        RETURN i.submitted_by as submitted_by, i.title as title
        """

        with self._session() as session:
            if session is None:
                logger.warning(f"Fallback mode: Improvement approval simulated for {improvement_id}")
                return True

            try:
                result = session.run(
                    cypher,
                    improvement_id=improvement_id,
                    approved_by=approved_by,
                    approved_at=approved_at
                )
                record = result.single()

                if record is None:
                    logger.warning(f"Improvement not found or not in proposed status: {improvement_id}")
                    return False

                # Notify submitter of approval
                self.create_notification(
                    agent=record["submitted_by"],
                    type="improvement_approved",
                    summary=f"Improvement '{record['title']}' approved by {approved_by}",
                    task_id=improvement_id
                )

                logger.info(f"Improvement approved: {improvement_id} by {approved_by}")
                return True

            except _get_neo4j_error() as e:
                logger.error(f"Failed to approve improvement: {e}")
                raise

    def reject_improvement(self, improvement_id: str, rejected_by: str, reason: str) -> bool:
        """
        Reject an improvement.

        Args:
            improvement_id: Improvement ID to reject
            rejected_by: Agent who is rejecting (usually 'kublai')
            reason: Reason for rejection

        Returns:
            True if successful, False if improvement not found or not in proposed status
        """
        rejected_at = self._now()

        cypher = """
        MATCH (i:Improvement {id: $improvement_id})
        WHERE i.status = 'proposed'
        SET i.status = 'rejected',
            i.approved_by = $rejected_by,
            i.approved_at = $rejected_at,
            i.rejection_reason = $reason
        RETURN i.submitted_by as submitted_by, i.title as title
        """

        with self._session() as session:
            if session is None:
                logger.warning(f"Fallback mode: Improvement rejection simulated for {improvement_id}")
                return True

            try:
                result = session.run(
                    cypher,
                    improvement_id=improvement_id,
                    rejected_by=rejected_by,
                    rejected_at=rejected_at,
                    reason=reason
                )
                record = result.single()

                if record is None:
                    logger.warning(f"Improvement not found or not in proposed status: {improvement_id}")
                    return False

                # Notify submitter of rejection
                self.create_notification(
                    agent=record["submitted_by"],
                    type="improvement_rejected",
                    summary=f"Improvement '{record['title']}' rejected by {rejected_by}: {reason[:100]}",
                    task_id=improvement_id
                )

                logger.info(f"Improvement rejected: {improvement_id} by {rejected_by}")
                return True

            except _get_neo4j_error() as e:
                logger.error(f"Failed to reject improvement: {e}")
                raise

    def implement_improvement(self, improvement_id: str, implemented_by: str) -> bool:
        """
        Mark an improvement as implemented.

        Args:
            improvement_id: Improvement ID to mark as implemented
            implemented_by: Agent who implemented the improvement

        Returns:
            True if successful, False if improvement not found or not in approved status
        """
        implemented_at = self._now()

        cypher = """
        MATCH (i:Improvement {id: $improvement_id})
        WHERE i.status = 'approved'
        SET i.status = 'implemented',
            i.implemented_at = $implemented_at
        RETURN i.submitted_by as submitted_by, i.title as title, i.approved_by as approved_by
        """

        with self._session() as session:
            if session is None:
                logger.warning(f"Fallback mode: Improvement implementation simulated for {improvement_id}")
                return True

            try:
                result = session.run(
                    cypher,
                    improvement_id=improvement_id,
                    implemented_at=implemented_at
                )
                record = result.single()

                if record is None:
                    logger.warning(f"Improvement not found or not in approved status: {improvement_id}")
                    return False

                # Notify submitter and approver of implementation
                self.create_notification(
                    agent=record["submitted_by"],
                    type="improvement_implemented",
                    summary=f"Improvement '{record['title']}' implemented by {implemented_by}",
                    task_id=improvement_id
                )

                if record["approved_by"] and record["approved_by"] != record["submitted_by"]:
                    self.create_notification(
                        agent=record["approved_by"],
                        type="improvement_implemented",
                        summary=f"Improvement '{record['title']}' implemented by {implemented_by}",
                        task_id=improvement_id
                    )

                logger.info(f"Improvement implemented: {improvement_id} by {implemented_by}")
                return True

            except _get_neo4j_error() as e:
                logger.error(f"Failed to implement improvement: {e}")
                raise

    def get_improvement(self, improvement_id: str) -> Optional[Dict]:
        """
        Get a specific improvement by ID.

        Args:
            improvement_id: Improvement ID to retrieve

        Returns:
            Improvement dict if found, None otherwise
        """
        cypher = """
        MATCH (i:Improvement {id: $improvement_id})
        RETURN i
        """

        with self._session() as session:
            if session is None:
                return None

            try:
                result = session.run(cypher, improvement_id=improvement_id)
                record = result.single()
                return dict(record["i"]) if record else None
            except _get_neo4j_error() as e:
                logger.error(f"Failed to get improvement: {e}")
                raise

    def get_improvement_summary(self) -> Dict:
        """
        Get summary counts of improvements by status and category.

        Returns:
            Dict with counts by status and category, plus high-value improvements
        """
        cypher = """
        MATCH (i:Improvement)
        RETURN i.status as status, i.category as category, count(i) as count
        """

        with self._session() as session:
            if session is None:
                return {
                    "total": 0,
                    "by_status": {"proposed": 0, "approved": 0, "rejected": 0, "implemented": 0},
                    "by_category": {"workflow": 0, "performance": 0, "security": 0, "documentation": 0, "other": 0},
                    "high_value_pending": [],
                    "avg_value_score": 0.0
                }

            try:
                result = session.run(cypher)

                # Initialize counters
                by_status = {"proposed": 0, "approved": 0, "rejected": 0, "implemented": 0}
                by_category = {"workflow": 0, "performance": 0, "security": 0, "documentation": 0, "other": 0}

                total = 0
                total_value_score = 0.0
                count_with_score = 0

                for record in result:
                    status = record["status"]
                    category = record["category"]
                    count = record["count"]

                    total += count
                    if status in by_status:
                        by_status[status] += count
                    if category in by_category:
                        by_category[category] += count

                # Get high-value pending improvements (top 5 proposed with value_score > 1.0)
                high_value_cypher = """
                MATCH (i:Improvement {status: 'proposed'})
                WHERE i.value_score > 1.0
                RETURN i.id as id, i.title as title, i.value_score as value_score, i.category as category
                ORDER BY i.value_score DESC
                LIMIT 5
                """

                high_value_result = session.run(high_value_cypher)
                high_value_pending = [
                    {
                        "id": record["id"],
                        "title": record["title"],
                        "value_score": record["value_score"],
                        "category": record["category"]
                    }
                    for record in high_value_result
                ]

                # Calculate average value score for implemented improvements
                avg_cypher = """
                MATCH (i:Improvement)
                WHERE i.value_score IS NOT NULL
                RETURN avg(i.value_score) as avg_value_score, count(i) as count
                """

                avg_result = session.run(avg_cypher).single()
                avg_value_score = avg_result["avg_value_score"] if avg_result and avg_result["avg_value_score"] else 0.0

                return {
                    "total": total,
                    "by_status": by_status,
                    "by_category": by_category,
                    "high_value_pending": high_value_pending,
                    "avg_value_score": round(avg_value_score, 2) if avg_value_score else 0.0
                }

            except _get_neo4j_error() as e:
                logger.error(f"Failed to get improvement summary: {e}")
                raise

    # =======================================================================
    # Background Synthesis (Chagatai Protocol)
    # =======================================================================

    def create_reflection(
        self,
        agent: str,
        content: str,
        topic: str = "general",
        task_id: Optional[str] = None
    ) -> str:
        """
        Create a new reflection node.

        Chagatai uses this to record agent reflections for later consolidation.

        Args:
            agent: Agent who created the reflection
            content: Reflection content
            topic: Topic/category of the reflection
            task_id: Associated task ID (optional)

        Returns:
            Reflection ID string
        """
        reflection_id = self._generate_id()
        created_at = self._now()

        cypher = """
        CREATE (r:Reflection {
            id: $reflection_id,
            agent: $agent,
            content: $content,
            topic: $topic,
            task_id: $task_id,
            consolidated: false,
            consolidated_at: null,
            created_at: $created_at
        })
        RETURN r.id as reflection_id
        """

        with self._session() as session:
            if session is None:
                logger.warning(f"Fallback mode: Reflection creation simulated for {agent}")
                return reflection_id

            try:
                result = session.run(
                    cypher,
                    reflection_id=reflection_id,
                    agent=agent,
                    content=content,
                    topic=topic,
                    task_id=task_id,
                    created_at=created_at
                )
                record = result.single()
                if record:
                    logger.info(f"Reflection created: {reflection_id} (agent: {agent}, topic: {topic})")
                    return record["reflection_id"]
                else:
                    raise RuntimeError("Reflection creation failed: no record returned")
            except _get_neo4j_error() as e:
                logger.error(f"Failed to create reflection: {e}")
                raise

    def get_reflection(self, reflection_id: str) -> Optional[Dict]:
        """
        Get a reflection by ID.

        Args:
            reflection_id: Reflection ID to retrieve

        Returns:
            Reflection dict if found, None otherwise
        """
        cypher = """
        MATCH (r:Reflection {id: $reflection_id})
        RETURN r
        """

        with self._session() as session:
            if session is None:
                return None

            try:
                result = session.run(cypher, reflection_id=reflection_id)
                record = result.single()
                return dict(record["r"]) if record else None
            except _get_neo4j_error() as e:
                logger.error(f"Failed to get reflection: {e}")
                raise

    def list_reflections(
        self,
        agent: Optional[str] = None,
        topic: Optional[str] = None,
        consolidated: Optional[bool] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Query reflections with optional filters.

        Args:
            agent: Filter by agent
            topic: Filter by topic
            consolidated: Filter by consolidation status
            limit: Maximum number of reflections to return

        Returns:
            List of reflection dicts
        """
        conditions = []
        params = {"limit": limit}

        if agent is not None:
            conditions.append("r.agent = $agent")
            params["agent"] = agent

        if topic is not None:
            conditions.append("r.topic = $topic")
            params["topic"] = topic

        if consolidated is not None:
            conditions.append("r.consolidated = $consolidated")
            params["consolidated"] = consolidated

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        cypher = f"""
        MATCH (r:Reflection)
        {where_clause}
        RETURN r
        ORDER BY r.created_at DESC
        LIMIT $limit
        """

        with self._session() as session:
            if session is None:
                return []

            try:
                result = session.run(cypher, **params)
                return [dict(record["r"]) for record in result]
            except _get_neo4j_error() as e:
                logger.error(f"Failed to list reflections: {e}")
                raise

    def count_unconsolidated_reflections(self) -> int:
        """
        Count unconsolidated reflections.

        Returns:
            Number of unconsolidated reflections
        """
        cypher = """
        MATCH (r:Reflection {consolidated: false})
        RETURN count(r) as count
        """

        with self._session() as session:
            if session is None:
                return 0

            try:
                result = session.run(cypher)
                record = result.single()
                return record["count"] if record else 0
            except _get_neo4j_error() as e:
                logger.error(f"Failed to count unconsolidated reflections: {e}")
                return 0

    def create_learning(
        self,
        agent: str,
        topic: str,
        content: str,
        themes: Optional[List[str]] = None,
        reflection_ids: Optional[List[str]] = None
    ) -> str:
        """
        Create a consolidated learning node.

        Args:
            agent: Agent the learning belongs to
            topic: Topic of the learning
            content: Learning content/summary
            themes: List of theme keywords
            reflection_ids: IDs of source reflections

        Returns:
            Learning ID string
        """
        learning_id = self._generate_id()
        created_at = self._now()

        cypher = """
        CREATE (l:Learning {
            id: $learning_id,
            agent: $agent,
            topic: $topic,
            content: $content,
            themes: $themes,
            reflection_count: $reflection_count,
            source_reflections: $reflection_ids,
            created_at: $created_at
        })
        RETURN l.id as learning_id
        """

        with self._session() as session:
            if session is None:
                logger.warning(f"Fallback mode: Learning creation simulated for {agent}")
                return learning_id

            try:
                result = session.run(
                    cypher,
                    learning_id=learning_id,
                    agent=agent,
                    topic=topic,
                    content=content,
                    themes=str(themes) if themes else None,
                    reflection_count=len(reflection_ids) if reflection_ids else 0,
                    reflection_ids=str(reflection_ids) if reflection_ids else None,
                    created_at=created_at
                )
                record = result.single()
                if record:
                    logger.info(f"Learning created: {learning_id} (agent: {agent}, topic: {topic})")
                    return record["learning_id"]
                else:
                    raise RuntimeError("Learning creation failed: no record returned")
            except _get_neo4j_error() as e:
                logger.error(f"Failed to create learning: {e}")
                raise

    def get_learning(self, learning_id: str) -> Optional[Dict]:
        """
        Get a learning by ID.

        Args:
            learning_id: Learning ID to retrieve

        Returns:
            Learning dict if found, None otherwise
        """
        cypher = """
        MATCH (l:Learning {id: $learning_id})
        RETURN l
        """

        with self._session() as session:
            if session is None:
                return None

            try:
                result = session.run(cypher, learning_id=learning_id)
                record = result.single()
                if record:
                    learning_dict = dict(record["l"])
                    # Parse themes and source_reflections back from strings if possible
                    for key in ["themes", "source_reflections"]:
                        if learning_dict.get(key):
                            try:
                                import ast
                                learning_dict[key] = ast.literal_eval(learning_dict[key])
                            except (ValueError, SyntaxError):
                                pass
                    return learning_dict
                return None
            except _get_neo4j_error() as e:
                logger.error(f"Failed to get learning: {e}")
                raise

    def list_learnings(
        self,
        agent: Optional[str] = None,
        topic: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Query learnings with optional filters.

        Args:
            agent: Filter by agent
            topic: Filter by topic
            limit: Maximum number of learnings to return

        Returns:
            List of learning dicts
        """
        conditions = []
        params = {"limit": limit}

        if agent is not None:
            conditions.append("l.agent = $agent")
            params["agent"] = agent

        if topic is not None:
            conditions.append("l.topic = $topic")
            params["topic"] = topic

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        cypher = f"""
        MATCH (l:Learning)
        {where_clause}
        RETURN l
        ORDER BY l.created_at DESC
        LIMIT $limit
        """

        with self._session() as session:
            if session is None:
                return []

            try:
                result = session.run(cypher, **params)
                learnings = []
                for record in result:
                    learning_dict = dict(record["l"])
                    # Parse themes and source_reflections back from strings if possible
                    for key in ["themes", "source_reflections"]:
                        if learning_dict.get(key):
                            try:
                                import ast
                                learning_dict[key] = ast.literal_eval(learning_dict[key])
                            except (ValueError, SyntaxError):
                                pass
                    learnings.append(learning_dict)
                return learnings
            except _get_neo4j_error() as e:
                logger.error(f"Failed to list learnings: {e}")
                raise

    # =======================================================================
    # MetaRule Management (Self-Improvement Skills Integration)
    # =======================================================================

    def create_metarule(
        self,
        rule_content: str,
        rule_type: str,
        source_reflections: List[str]
    ) -> str:
        """
        Create a new MetaRule node.

        MetaRules are generated from consolidated reflections and represent
        general principles that agents should follow.

        Args:
            rule_content: The rule text content
            rule_type: Type of rule ('absolute', 'guideline', 'conditional')
            source_reflections: List of reflection IDs that generated this rule

        Returns:
            MetaRule ID string

        Raises:
            ValueError: If rule_type is invalid
        """
        valid_types = ['absolute', 'guideline', 'conditional']
        if rule_type not in valid_types:
            raise ValueError(f"Invalid rule_type '{rule_type}'. Must be one of: {valid_types}")

        rule_id = self._generate_id()
        created_at = self._now()

        cypher = """
        CREATE (m:MetaRule {
            id: $rule_id,
            rule_content: $rule_content,
            rule_type: $rule_type,
            source_reflections: $source_reflections,
            success_count: 0,
            application_count: 0,
            effectiveness_score: 0.0,
            approved: false,
            approved_by: null,
            approved_at: null,
            version: 1,
            created_at: $created_at
        })
        RETURN m.id as rule_id
        """

        with self._session() as session:
            if session is None:
                logger.warning(f"Fallback mode: MetaRule creation simulated")
                return rule_id

            try:
                result = session.run(
                    cypher,
                    rule_id=rule_id,
                    rule_content=rule_content,
                    rule_type=rule_type,
                    source_reflections=source_reflections,
                    created_at=created_at
                )
                record = result.single()
                if record:
                    logger.info(f"MetaRule created: {rule_id} (type: {rule_type})")
                    return record["rule_id"]
                else:
                    raise RuntimeError("MetaRule creation failed: no record returned")
            except _get_neo4j_error() as e:
                logger.error(f"Failed to create MetaRule: {e}")
                raise

    def get_metarule(self, rule_id: str) -> Optional[Dict]:
        """
        Get a MetaRule by ID.

        Args:
            rule_id: MetaRule ID to retrieve

        Returns:
            MetaRule dict if found, None otherwise
        """
        cypher = """
        MATCH (m:MetaRule {id: $rule_id})
        RETURN m
        """

        with self._session() as session:
            if session is None:
                return None

            try:
                result = session.run(cypher, rule_id=rule_id)
                record = result.single()
                return dict(record["m"]) if record else None
            except _get_neo4j_error() as e:
                logger.error(f"Failed to get MetaRule: {e}")
                return None

    def list_metarules(
        self,
        approved: Optional[bool] = None,
        rule_type: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        List MetaRules with optional filters.

        Args:
            approved: Filter by approval status
            rule_type: Filter by rule type
            limit: Maximum number of rules to return

        Returns:
            List of MetaRule dicts
        """
        conditions = []
        params = {"limit": limit}

        if approved is not None:
            conditions.append("m.approved = $approved")
            params["approved"] = approved

        if rule_type is not None:
            conditions.append("m.rule_type = $rule_type")
            params["rule_type"] = rule_type

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        cypher = f"""
        MATCH (m:MetaRule)
        {where_clause}
        RETURN m
        ORDER BY m.effectiveness_score DESC, m.created_at DESC
        LIMIT $limit
        """

        with self._session() as session:
            if session is None:
                return []

            try:
                result = session.run(cypher, **params)
                return [dict(record["m"]) for record in result]
            except _get_neo4j_error() as e:
                logger.error(f"Failed to list MetaRules: {e}")
                return []

    def approve_metarule(self, rule_id: str, approved_by: str) -> bool:
        """
        Approve a MetaRule (Kublai action).

        Args:
            rule_id: ID of the rule to approve
            approved_by: Agent who approved the rule

        Returns:
            True if approval successful, False if rule not found
        """
        approved_at = self._now()

        cypher = """
        MATCH (m:MetaRule {id: $rule_id})
        SET m.approved = true,
            m.approved_by = $approved_by,
            m.approved_at = $approved_at
        RETURN m.id as rule_id
        """

        with self._session() as session:
            if session is None:
                logger.warning(f"Fallback mode: MetaRule approval simulated for {rule_id}")
                return True

            try:
                result = session.run(
                    cypher,
                    rule_id=rule_id,
                    approved_by=approved_by,
                    approved_at=approved_at
                )
                record = result.single()

                if record is None:
                    logger.warning(f"MetaRule not found: {rule_id}")
                    return False

                logger.info(f"MetaRule approved: {rule_id} by {approved_by}")
                return True

            except _get_neo4j_error() as e:
                logger.error(f"Failed to approve MetaRule: {e}")
                raise

    def apply_metarule(self, rule_id: str, outcome_success: bool) -> bool:
        """
        Record a MetaRule application outcome.

        Updates success_count and application_count, recalculates effectiveness_score.

        Args:
            rule_id: ID of the rule that was applied
            outcome_success: Whether the application was successful

        Returns:
            True if update successful, False if rule not found
        """
        cypher = """
        MATCH (m:MetaRule {id: $rule_id})
        SET m.application_count = m.application_count + 1,
            m.success_count = CASE WHEN $outcome_success
                THEN m.success_count + 1
                ELSE m.success_count
            END,
            m.effectiveness_score = CASE WHEN $outcome_success
                THEN (m.success_count + 1.0) / (m.application_count + 1.0)
                ELSE m.success_count / (m.application_count + 1.0)
            END
        RETURN m.id as rule_id
        """

        with self._session() as session:
            if session is None:
                logger.warning(f"Fallback mode: MetaRule application simulated for {rule_id}")
                return True

            try:
                result = session.run(
                    cypher,
                    rule_id=rule_id,
                    outcome_success=outcome_success
                )
                record = result.single()

                if record is None:
                    logger.warning(f"MetaRule not found: {rule_id}")
                    return False

                logger.debug(f"MetaRule application recorded: {rule_id}, success={outcome_success}")
                return True

            except _get_neo4j_error() as e:
                logger.error(f"Failed to record MetaRule application: {e}")
                raise

    def get_metarule_effectiveness(self, rule_id: str) -> Optional[Dict]:
        """
        Get effectiveness metrics for a MetaRule.

        Args:
            rule_id: ID of the rule

        Returns:
            Dict with effectiveness metrics, or None if rule not found
        """
        cypher = """
        MATCH (m:MetaRule {id: $rule_id})
        RETURN m.success_count as success_count,
               m.application_count as application_count,
               m.effectiveness_score as effectiveness_score
        """

        with self._session() as session:
            if session is None:
                return None

            try:
                result = session.run(cypher, rule_id=rule_id)
                record = result.single()

                if record is None:
                    return None

                return {
                    "rule_id": rule_id,
                    "success_count": record["success_count"],
                    "application_count": record["application_count"],
                    "effectiveness_score": record["effectiveness_score"]
                }

            except _get_neo4j_error() as e:
                logger.error(f"Failed to get MetaRule effectiveness: {e}")
                return None

    def version_metarule(
        self,
        old_rule_id: str,
        new_rule_content: str,
        reason: str
    ) -> Optional[str]:
        """
        Create a new version of a MetaRule.

        Creates a new rule node and adds REPLACED_BY relationship from old to new.

        Args:
            old_rule_id: ID of the rule being replaced
            new_rule_content: Content for the new rule version
            reason: Reason for the replacement

        Returns:
            New rule ID if successful, None if old rule not found
        """
        # Get old rule data
        old_rule = self.get_metarule(old_rule_id)
        if old_rule is None:
            return None

        # Create new rule with incremented version
        new_rule_id = self._generate_id()
        created_at = self._now()
        new_version = old_rule.get("version", 1) + 1

        cypher_create = """
        CREATE (m:MetaRule {
            id: $rule_id,
            rule_content: $rule_content,
            rule_type: $rule_type,
            source_reflections: $source_reflections,
            success_count: 0,
            application_count: 0,
            effectiveness_score: 0.0,
            approved: false,
            approved_by: null,
            approved_at: null,
            version: $version,
            created_at: $created_at,
            replaces_rule: $old_rule_id
        })
        RETURN m.id as rule_id
        """

        cypher_relate = """
        MATCH (old:MetaRule {id: $old_rule_id})
        MATCH (new:MetaRule {id: $new_rule_id})
        CREATE (old)-[r:REPLACED_BY {
            reason: $reason,
            replaced_at: $replaced_at
        }]->(new)
        RETURN r
        """

        with self._session() as session:
            if session is None:
                logger.warning(f"Fallback mode: MetaRule versioning simulated")
                return new_rule_id

            try:
                # Create new rule
                result = session.run(
                    cypher_create,
                    rule_id=new_rule_id,
                    rule_content=new_rule_content,
                    rule_type=old_rule.get("rule_type", "guideline"),
                    source_reflections=old_rule.get("source_reflections", []),
                    version=new_version,
                    created_at=created_at,
                    old_rule_id=old_rule_id
                )
                record = result.single()
                if not record:
                    raise RuntimeError("New MetaRule creation failed")

                # Create REPLACED_BY relationship
                session.run(
                    cypher_relate,
                    old_rule_id=old_rule_id,
                    new_rule_id=new_rule_id,
                    reason=reason,
                    replaced_at=created_at
                )

                logger.info(f"MetaRule versioned: {old_rule_id} -> {new_rule_id} (version {new_version})")
                return new_rule_id

            except _get_neo4j_error() as e:
                logger.error(f"Failed to version MetaRule: {e}")
                raise

    def get_metarule_history(self, rule_id: str) -> List[Dict]:
        """
        Get version history for a MetaRule.

        Follows REPLACED_BY relationships to build version chain.

        Args:
            rule_id: Current rule ID

        Returns:
            List of rule versions (oldest first)
        """
        # Check if this rule replaced another
        cypher = """
        MATCH (old:MetaRule)-[r:REPLACED_BY]->(new:MetaRule {id: $rule_id})
        RETURN old, r
        """

        history = []

        with self._session() as session:
            if session is None:
                return history

            try:
                # Walk backwards through the chain
                current_id = rule_id
                chain = []

                while True:
                    result = session.run(cypher, rule_id=current_id)
                    record = result.single()

                    if record is None:
                        break

                    old_rule = dict(record["old"])
                    relationship = dict(record["r"])
                    chain.append({
                        "rule": old_rule,
                        "replaced_by_reason": relationship.get("reason", ""),
                        "replaced_at": relationship.get("replaced_at")
                    })
                    current_id = old_rule["id"]

                # Reverse to get oldest first
                chain.reverse()

                # Add current rule
                current_rule = self.get_metarule(rule_id)
                if current_rule:
                    chain.append({"rule": current_rule})

                return chain

            except _get_neo4j_error() as e:
                logger.error(f"Failed to get MetaRule history: {e}")
                return []

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

            # Improvement indexes (Ogedei Proactive Improvement Protocol)
            ("CREATE INDEX improvement_id_idx IF NOT EXISTS FOR (i:Improvement) ON (i.id)", "improvement_id_idx"),
            ("CREATE INDEX improvement_submitted_by_idx IF NOT EXISTS FOR (i:Improvement) ON (i.submitted_by)", "improvement_submitted_by_idx"),
            ("CREATE INDEX improvement_status_idx IF NOT EXISTS FOR (i:Improvement) ON (i.status)", "improvement_status_idx"),
            ("CREATE INDEX improvement_category_idx IF NOT EXISTS FOR (i:Improvement) ON (i.category)", "improvement_category_idx"),
            ("CREATE INDEX improvement_value_score_idx IF NOT EXISTS FOR (i:Improvement) ON (i.value_score)", "improvement_value_score_idx"),
            ("CREATE INDEX improvement_created_at_idx IF NOT EXISTS FOR (i:Improvement) ON (i.created_at)", "improvement_created_at_idx"),
            ("CREATE INDEX improvement_status_category_idx IF NOT EXISTS FOR (i:Improvement) ON (i.status, i.category)", "improvement_status_category_idx"),
            ("CREATE INDEX improvement_status_value_score_idx IF NOT EXISTS FOR (i:Improvement) ON (i.status, i.value_score)", "improvement_status_value_score_idx"),

            # Reflection indexes (Chagatai Background Synthesis)
            ("CREATE INDEX reflection_id_idx IF NOT EXISTS FOR (r:Reflection) ON (r.id)", "reflection_id_idx"),
            ("CREATE INDEX reflection_agent_idx IF NOT EXISTS FOR (r:Reflection) ON (r.agent)", "reflection_agent_idx"),
            ("CREATE INDEX reflection_topic_idx IF NOT EXISTS FOR (r:Reflection) ON (r.topic)", "reflection_topic_idx"),
            ("CREATE INDEX reflection_consolidated_idx IF NOT EXISTS FOR (r:Reflection) ON (r.consolidated)", "reflection_consolidated_idx"),
            ("CREATE INDEX reflection_created_at_idx IF NOT EXISTS FOR (r:Reflection) ON (r.created_at)", "reflection_created_at_idx"),

            # Learning indexes (Chagatai Background Synthesis)
            ("CREATE INDEX learning_id_idx IF NOT EXISTS FOR (l:Learning) ON (l.id)", "learning_id_idx"),
            ("CREATE INDEX learning_agent_idx IF NOT EXISTS FOR (l:Learning) ON (l.agent)", "learning_agent_idx"),
            ("CREATE INDEX learning_topic_idx IF NOT EXISTS FOR (l:Learning) ON (l.topic)", "learning_topic_idx"),
            ("CREATE INDEX learning_created_at_idx IF NOT EXISTS FOR (l:Learning) ON (l.created_at)", "learning_created_at_idx"),

            # MetaRule indexes (Self-Improvement Skills Integration)
            ("CREATE INDEX metarule_id_idx IF NOT EXISTS FOR (m:MetaRule) ON (m.id)", "metarule_id_idx"),
            ("CREATE INDEX metarule_approved_idx IF NOT EXISTS FOR (m:MetaRule) ON (m.approved)", "metarule_approved_idx"),
            ("CREATE INDEX metarule_type_idx IF NOT EXISTS FOR (m:MetaRule) ON (m.rule_type)", "metarule_type_idx"),
            ("CREATE INDEX metarule_version_idx IF NOT EXISTS FOR (m:MetaRule) ON (m.version)", "metarule_version_idx"),
            ("CREATE INDEX metarule_created_at_idx IF NOT EXISTS FOR (m:MetaRule) ON (m.created_at)", "metarule_created_at_idx"),
            ("CREATE INDEX metarule_effectiveness_idx IF NOT EXISTS FOR (m:MetaRule) ON (m.effectiveness_score)", "metarule_effectiveness_idx"),
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
                except _get_neo4j_error() as e:
                    if "already exists" not in str(e).lower():
                        logger.error(f"Failed to create index {name}: {e}")

        return created

    # =======================================================================
    # Kurultai v0.1 Task Dependency Engine Methods
    # =======================================================================

    def create_task_with_embedding(
        self,
        task_type: str,
        description: str,
        delegated_by: str,
        assigned_to: Optional[str],
        priority: str,
        sender_hash: str,
        embedding: Optional[List[float]] = None,
        deliverable_type: str = "analysis",
        priority_weight: float = 0.5,
        window_expires_at: Optional[datetime] = None,
        **kwargs
    ) -> str:
        """
        Create a task with Kurultai dependency fields.

        Args:
            task_type: Type of task
            description: Task description
            delegated_by: Agent who delegated the task
            assigned_to: Agent assigned to the task
            priority: Task priority (0-1)
            sender_hash: HMAC-SHA256 of sender identifier
            embedding: 384-dim vector for similarity (optional)
            deliverable_type: Type of deliverable (research, code, etc.)
            priority_weight: Weight for topological sort (0-1)
            window_expires_at: When intent window expires

        Returns:
            Task ID
        """
        task_id = self._generate_id()
        now = self._now()

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
            error_message: null,
            // Kurultai v0.1 fields
            sender_hash: $sender_hash,
            embedding: COALESCE($embedding, []),
            deliverable_type: $deliverable_type,
            priority_weight: $priority_weight,
            user_priority_override: false,
            window_expires_at: COALESCE($window_expires_at, $created_at),
            merged_into: null,
            merged_from: [],
            notion_synced_at: null,
            notion_page_id: null,
            notion_url: null,
            external_priority_source: null,
            external_priority_weight: 0.0
        })
        RETURN t.id as id
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
                    created_at=now,
                    sender_hash=sender_hash,
                    embedding=embedding,
                    deliverable_type=deliverable_type,
                    priority_weight=priority_weight,
                    window_expires_at=window_expires_at,
                )
                record = result.single()
                if record:
                    logger.info(
                        f"Task created with embedding: {task_id} "
                        f"(type: {task_type}, deliverable: {deliverable_type})"
                    )
                    return record["id"]
                else:
                    raise RuntimeError("Task creation failed: no record returned")
            except _get_neo4j_error() as e:
                logger.error(f"Failed to create task with embedding: {e}")
                raise

    def add_dependency(
        self,
        task_id: str,
        depends_on_id: str,
        dep_type: str = "blocks"
    ) -> bool:
        """
        Add a DEPENDS_ON relationship with ATOMIC cycle detection.

        Args:
            task_id: The task that depends on another (dependent)
            depends_on_id: The task that must complete first (dependency)
            dep_type: Type of dependency ("blocks" | "feeds_into" | "parallel_ok")

        Returns:
            True if dependency created successfully

        Raises:
            ValueError: If adding would create a cycle
        """
        atomic_query = """
        // Verify both tasks exist
        MATCH (task:Task {id: $task_id})
        MATCH (dep:Task {id: $depends_on_id})

        // Check for cycles - if a path exists from dep back to task, adding this edge creates a cycle
        WHERE NOT EXISTS {
            MATCH path = (dep)-[:DEPENDS_ON*]->(task)
        }

        // Create dependency atomically
        CREATE (task)-[r:DEPENDS_ON {
            type: $dep_type,
            weight: 0.5,
            detected_by: 'explicit',
            confidence: 1.0,
            created_at: datetime()
        }]->(dep)

        RETURN r as relationship
        """

        with self._session() as session:
            if session is None:
                logger.warning("Fallback mode: Dependency creation simulated")
                return True

            try:
                result = session.run(
                    atomic_query,
                    task_id=task_id,
                    depends_on_id=depends_on_id,
                    dep_type=dep_type
                )
                record = result.single()
                if record:
                    logger.info(f"Dependency created: {task_id} depends on {depends_on_id} ({dep_type})")
                    return True
                else:
                    # Cycle detected or tasks don't exist
                    logger.warning(f"Could not create dependency (would create cycle or tasks not found)")
                    return False
            except _get_neo4j_error() as e:
                logger.error(f"Failed to add dependency: {e}")
                raise

    def get_task_dependencies(
        self,
        task_id: str
    ) -> List[Dict]:
        """
        Get all dependencies for a task.

        Args:
            task_id: Task ID

        Returns:
            List of dependency relationships
        """
        query = """
        MATCH (t:Task {id: $task_id})-[d:DEPENDS_ON]->(dep:Task)
        RETURN d.type as type, d.weight as weight, d.detected_by as detected_by,
               d.confidence as confidence, dep.id as depends_on_id,
               dep.description as depends_on_description
        """

        with self._session() as session:
            if session is None:
                logger.warning("Fallback mode: No dependencies returned")
                return []

            try:
                result = session.run(query, task_id=task_id)
                return [dict(record) for record in result]
            except _get_neo4j_error() as e:
                logger.error(f"Failed to get task dependencies: {e}")
                raise

    def get_ready_tasks(
        self,
        sender_hash: str,
        limit: int = 50
    ) -> List[Dict]:
        """
        Find tasks with no unmet BLOCKS dependencies.

        Args:
            sender_hash: User identifier
            limit: Maximum tasks to return

        Returns:
            List of tasks ready for execution
        """
        query = """
        MATCH (t:Task {sender_hash: $sender_hash, status: 'pending'})
        WHERE NOT EXISTS {
            // Check for uncompleted blocking dependencies
            MATCH (t)-[:DEPENDS_ON {type: 'blocks'}]->(blocker:Task)
            WHERE blocker.status != 'completed'
        }
        RETURN t
        ORDER BY t.priority_weight DESC, t.created_at ASC
        LIMIT $limit
        """

        with self._session() as session:
            if session is None:
                logger.warning("Fallback mode: No ready tasks returned")
                return []

            try:
                result = session.run(query, sender_hash=sender_hash, limit=limit)
                return [dict(record["t"]) for record in result]
            except _get_neo4j_error() as e:
                logger.error(f"Failed to get ready tasks: {e}")
                raise

    def complete_task_with_dependencies(
        self,
        task_id: str,
        results: Dict,
        notify_delegator: bool = True
    ) -> bool:
        """
        Mark task as complete and check if dependent tasks are now ready.

        Args:
            task_id: Task ID to complete
            results: Task results
            notify_delegator: Whether to create notification

        Returns:
            True if successful
        """
        now = self._now()

        complete_query = """
        MATCH (t:Task {id: $task_id})
        SET t.status = 'completed',
            t.completed_at = $completed_at,
            t.results = $results

        // Find tasks that were blocked by this task
        WITH t
        MATCH (blocked:Task)-[:DEPENDS_ON {type: 'blocks'}]->(t)
        WHERE blocked.status = 'pending'

        // Check if blocked tasks are now ready (no other incomplete blockers)
        WITH blocked
        WHERE NOT EXISTS {
            MATCH (blocked)-[:DEPENDS_ON {type: 'blocks'}]->(other:Task)
            WHERE other.status != 'completed'
        }

        // Update now-ready tasks
        SET blocked.status = 'ready',
            blocked.unblocked_at = $completed_at

        RETURN count(blocked) as newly_unblocked
        """

        with self._session() as session:
            if session is None:
                logger.warning(f"Fallback mode: Task completion simulated for {task_id}")
                return True

            try:
                result = session.run(
                    complete_query,
                    task_id=task_id,
                    completed_at=now,
                    results=str(results)
                )
                record = result.single()

                newly_unblocked = record["newly_unblocked"] if record else 0
                logger.info(
                    f"Task completed: {task_id} (newly unblocked: {newly_unblocked})"
                )
                return True

            except _get_neo4j_error() as e:
                logger.error(f"Failed to complete task with dependencies: {e}")
                raise

    def log_priority_change(
        self,
        sender_hash: str,
        task_id: str,
        old_priority: float,
        new_priority: float,
        reason: str
    ) -> None:
        """
        Log priority change for audit trail.

        Args:
            sender_hash: User who made the change
            task_id: Task whose priority changed
            old_priority: Previous priority value
            new_priority: New priority value
            reason: Reason for the change
        """
        query = """
        CREATE (a:PriorityAudit {
            timestamp: datetime(),
            sender_hash: $sender_hash,
            task_id: $task_id,
            old_priority: $old_priority,
            new_priority: $new_priority,
            reason: $reason
        })
        RETURN a
        """

        with self._session() as session:
            if session is None:
                logger.warning("Fallback mode: Priority audit not recorded")
                return

            try:
                session.run(query, {
                    "sender_hash": sender_hash,
                    "task_id": task_id,
                    "old_priority": old_priority,
                    "new_priority": new_priority,
                    "reason": reason
                })
                logger.info(f"Priority audit logged: {task_id} {old_priority} -> {new_priority}")
            except _get_neo4j_error() as e:
                logger.error(f"Failed to log priority change: {e}")

    def get_tasks_by_sender(
        self,
        sender_hash: str,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Get tasks for a specific sender.

        Args:
            sender_hash: User identifier
            status: Optional status filter
            limit: Maximum tasks to return

        Returns:
            List of tasks
        """
        if status:
            query = """
            MATCH (t:Task {sender_hash: $sender_hash, status: $status})
            RETURN t
            ORDER BY t.priority_weight DESC, t.created_at ASC
            LIMIT $limit
            """
            params = {"sender_hash": sender_hash, "status": status, "limit": limit}
        else:
            query = """
            MATCH (t:Task {sender_hash: $sender_hash})
            RETURN t
            ORDER BY t.priority_weight DESC, t.created_at ASC
            LIMIT $limit
            """
            params = {"sender_hash": sender_hash, "limit": limit}

        with self._session() as session:
            if session is None:
                logger.warning("Fallback mode: No tasks returned")
                return []

            try:
                result = session.run(query, **params)
                return [dict(record["t"]) for record in result]
            except _get_neo4j_error() as e:
                logger.error(f"Failed to get tasks by sender: {e}")
                raise

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
