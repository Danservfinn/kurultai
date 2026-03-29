#!/usr/bin/env python3
"""
Neo4j Task Tracker - Persistent task history with queryable metrics

Schema:
- (:Task {label, agent, status, created, completed, ...})
- (:Agent {name})-[:EXECUTED]->(:Task)
- (:Task)-[:RETRIED]->(:Task)

Usage:
    from neo4j_task_tracker import TaskTracker
    tracker = TaskTracker()
    tracker.create_task("mongke-123", "mongke", "Research X")
    tracker.update_status("mongke-123", "completed")
"""

import os
import sys
import json
import uuid
import glob
import logging
import threading
from contextlib import contextmanager
from datetime import datetime
from neo4j import GraphDatabase
from neo4j.exceptions import (
    ServiceUnavailable,
    SessionExpired,
    TransientError,
    AuthError,
    ClientError
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kurultai_paths import AGENTS_DIR as _AGENTS_DIR, agent_tasks_dir
from kurultai_ledger import generate_task_id, validate_task_id

import warnings
_V1_DEPRECATED = os.environ.get('V1_DEPRECATED', 'true').lower() == 'true'

def _check_deprecated(method_name):
    if _V1_DEPRECATED:
        warnings.warn(
            f"TaskTracker.{method_name}() is deprecated. Use TaskStore from neo4j_v2_core instead.",
            DeprecationWarning, stacklevel=3
        )

# Import Neo4j health check for pre-flight validation
try:
    from neo4j_utils import check_neo4j_available
    _HAS_HEALTH_CHECK = True
except ImportError:
    _HAS_HEALTH_CHECK = False
    def check_neo4j_available():
        """Fallback: always return True if health check unavailable."""
        return True

# Set up logging
logger = logging.getLogger(__name__)

# Thread safety lock for singleton driver
_lock = threading.Lock()

# Custom exception for connection errors
class Neo4jConnectionError(Exception):
    """Raised when Neo4j connection fails."""
    pass

_AGENTS_BASE = str(_AGENTS_DIR)

# Credentials env file — single source of truth
_NEO4J_ENV_FILE = os.path.expanduser("~/.openclaw/credentials/neo4j.env")


def _load_neo4j_env():
    """Load Neo4j credentials from env file into os.environ if not already set."""
    if os.path.exists(_NEO4J_ENV_FILE):
        with open(_NEO4J_ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _, value = line.partition('=')
                    if key.strip() not in os.environ:
                        os.environ[key.strip()] = value.strip()


# Singleton driver with connection pooling
_cached_driver = None
_driver_refcount = 0


def is_neo4j_available() -> bool:
    """Check if Neo4j is available using pre-flight health check.

    Returns:
        True if Neo4j is reachable, False otherwise.
        Uses cached result from neo4j_utils.check_neo4j_available().

    This enables scripts to gracefully degrade to filesystem-only mode
    when Neo4j is unavailable, preventing cascade failures across
    the fleet.

    Example:
        if is_neo4j_available():
            tracker = TaskTracker()
            tracker.create_task(...)
        else:
            logger.warning("Neo4j unavailable, using filesystem-only mode")
    """
    if not _HAS_HEALTH_CHECK:
        # If health check module unavailable, assume available (legacy behavior)
        return True

    try:
        return check_neo4j_available()
    except Exception as e:
        logger.debug(f"Neo4j health check error, assuming unavailable: {e}")
        return False


def get_driver():
    """Get a Neo4j driver using centralized credentials.

    This is the SOLE connection factory. All scripts should use this
    instead of creating their own GraphDatabase.driver() calls.

    Returns a singleton driver with connection pooling enabled.
    Call close_driver() when done to properly release connections.

    Thread-safe: Uses lock to protect singleton initialization.

    Raises:
        Neo4jConnectionError: If Neo4j is unavailable or credentials are missing.
    """
    global _cached_driver, _driver_refcount

    _lock.acquire()
    try:
        if _cached_driver is not None:
            _driver_refcount += 1
            return _cached_driver

        # Load credentials FIRST so health check uses real password
        _load_neo4j_env()

        # Pre-flight health check: fail fast if Neo4j is unavailable
        # This prevents lengthy timeout delays when Neo4j is down
        if not is_neo4j_available():
            raise Neo4jConnectionError(
                "Neo4j is unavailable (pre-flight check failed). "
                "Use safe_get_driver() for graceful fallback to filesystem-only mode."
            )
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD")
        if not password:
            raise Neo4jConnectionError(
                "NEO4J_PASSWORD not set. Configure it in ~/.openclaw/credentials/neo4j.env"
            )

        logger.info(f"Creating Neo4j driver connection to {uri}")

        try:
            # Connection pooling configuration with differentiated timeouts
            _cached_driver = GraphDatabase.driver(
                uri,
                auth=(user, password),
                max_connection_pool_size=30,
                connection_timeout=10,           # Initial connection (reduced from 30)
                connection_acquisition_timeout=15,  # Wait for pool slot
                max_transaction_retry_time=30,
                max_connection_lifetime=3600     # 1 hour max connection age
            )
            _driver_refcount = 1
            logger.info("Neo4j driver created successfully")
        except AuthError as e:
            logger.error(f"Neo4j authentication failed: {e}")
            raise Neo4jConnectionError(f"Authentication failed: {e}")
        except ServiceUnavailable as e:
            logger.error(f"Neo4j service unavailable: {e}")
            raise Neo4jConnectionError(f"Neo4j service unavailable: {e}")
        except Exception as e:
            logger.error(f"Neo4j connection failed: {e}")
            raise Neo4jConnectionError(f"Failed to connect to Neo4j: {e}")

        # Register force-close on exit (bypasses refcount for clean shutdown)
        import atexit
        atexit.register(_force_close_driver)

        return _cached_driver
    finally:
        _lock.release()


def close_driver():
    """Decrement refcount and close driver only when it reaches zero.

    Call this when your script is done with Neo4j to properly
    release connection pool resources.

    Thread-safe: Uses lock to protect refcount operations.
    """
    global _cached_driver, _driver_refcount

    _lock.acquire()
    try:
        if _driver_refcount > 0:
            _driver_refcount -= 1
        else:
            logger.warning("close_driver() called with refcount already at 0 — possible double-close bug")

        if _driver_refcount == 0 and _cached_driver is not None:
            try:
                _cached_driver.close()
                logger.info("Neo4j driver closed (refcount reached 0)")
            except Exception as e:
                logger.warning(f"Error closing Neo4j driver: {e}")
            finally:
                _cached_driver = None
    finally:
        _lock.release()


def _force_close_driver():
    """Force-close driver at process exit regardless of refcount."""
    global _cached_driver, _driver_refcount
    with _lock:
        if _cached_driver is not None:
            try:
                _cached_driver.close()
            except Exception:
                pass
            _cached_driver = None
            _driver_refcount = 0


def get_pool_metrics() -> dict:
    """Return connection pool metrics for monitoring.

    Thread-safe: Uses lock to access global state.
    """
    global _cached_driver, _driver_refcount, _lock

    _lock.acquire()
    try:
        if _cached_driver is None:
            return {
                "status": "not_initialized",
                "refcount": _driver_refcount,
                "pool_size": 0
            }

        return {
            "status": "active",
            "refcount": _driver_refcount,
            "pool_size": 30,
            "connection_timeout": 10,
            "acquisition_timeout": 15,
            "max_lifetime": 3600
        }
    finally:
        _lock.release()


def safe_get_driver():
    """Get Neo4j driver with graceful fallback when unavailable.

    Unlike get_driver(), which raises Neo4jConnectionError when
    Neo4j is down, this function returns None, enabling scripts
    to implement filesystem-only fallback behavior.

    Returns:
        Neo4j driver if available, None otherwise.

    Example:
        driver = safe_get_driver()
        if driver:
            try:
                with driver.session() as session:
                    session.run("CREATE (n:Task {id: $id})", id=123)
            finally:
                close_driver()
        else:
            # Fallback to filesystem-only mode
            filesystem_create_task(123)

    Prefer neo4j_session() context manager which handles cleanup automatically.
    """
    if not is_neo4j_available():
        logger.warning("Neo4j unavailable - safe_get_driver() returning None")
        return None

    try:
        return get_driver()
    except Neo4jConnectionError as e:
        logger.warning(f"Neo4j connection failed: {e}")
        return None


def require_neo4j():
    """Raise exception if Neo4j is unavailable.

    Use this for scripts that MUST have Neo4j to function correctly.
    Provides a clear early error instead of cryptic connection failures.

    Raises:
        Neo4jConnectionError: If Neo4j is not available.

    Example:
        require_neo4j()  # Will raise if Neo4j is down
        tracker = TaskTracker()  # Safe to proceed
    """
    if not is_neo4j_available():
        raise Neo4jConnectionError(
            "Neo4j is required but not available. "
            "Start Neo4j service or use filesystem-only mode."
        )


@contextmanager
def neo4j_session():
    """Context manager for Neo4j sessions with automatic cleanup.

    Usage:
        with neo4j_session() as session:
            result = session.run("MATCH (n) RETURN n LIMIT 1")

    Note: If get_driver() raises, the try/finally block is never entered,
    so close_driver() is only called when get_driver() succeeded — no
    mismatched refcount decrement.
    """
    driver = get_driver()
    session = None
    try:
        session = driver.session()
        yield session
    finally:
        if session:
            session.close()
        close_driver()


def consume_result(result) -> list:
    """Fully consume a Neo4j result to release connection.

    Args:
        result: Neo4j Result object

    Returns:
        List of records as dictionaries
    """
    try:
        records = [dict(record) for record in result]
        return records
    finally:
        try:
            result.consume()
        except Exception:
            pass  # Consume even on error, ignore failures


class TaskTracker:
    def __init__(self):
        self.driver = get_driver()

    def close(self):
        """Release driver reference using centralized cleanup.

        Calls close_driver() to properly decrement refcount.
        """
        if self.driver is not None:
            close_driver()
            self.driver = None

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup resources."""
        self.close()
        return False  # Don't suppress exceptions
    
    def create_task(self, label, agent, task_desc, priority="normal",
                    mode="run", continuous=False, source="chat"):
        """Create a task node"""
        _check_deprecated('create_task')
        with self.driver.session() as session:
            session.run("""
                MERGE (a:Agent {name: $agent})
                CREATE (t:Task {
                    label: $label,
                    agent: $agent,
                    task: $task,
                    priority: $priority,
                    mode: $mode,
                    continuous: $continuous,
                    source: $source,
                    status: 'ready',
                    created: datetime(),
                    retry_count: 0,
                    max_retries: 3
                })
                CREATE (a)-[:EXECUTED]->(t)
            """,
            label=label, agent=agent, task=task_desc,
            priority=priority, mode=mode, continuous=continuous, source=source)
    
    def update_status(self, label, status, error=None, session_key=None):
        """Update task status in a single atomic query."""
        _check_deprecated('update_status')
        is_terminal = status in ['completed', 'failed', 'killed']
        is_running = status == 'running' and session_key is not None
        with self.driver.session() as session:
            session.run("""
                MATCH (t:Task {label: $label})
                SET t.status = $status,
                    t.updated = datetime(),
                    t.error = CASE WHEN $error IS NOT NULL THEN $error ELSE t.error END,
                    t.session_key = CASE WHEN $is_running THEN $session_key ELSE t.session_key END,
                    t.started = CASE WHEN $is_running THEN datetime() ELSE t.started END,
                    t.completed = CASE WHEN $is_terminal THEN datetime() ELSE t.completed END
                """,
                label=label, status=status, error=error,
                session_key=session_key or "",
                is_running=is_running, is_terminal=is_terminal)
    
    def increment_retry(self, label):
        """Increment retry count"""
        _check_deprecated('increment_retry')
        with self.driver.session() as session:
            session.run("""
                MATCH (t:Task {label: $label})
                SET t.retry_count = t.retry_count + 1,
                    t.last_retry = datetime()
            """, label=label)
    
    def get_tasks_by_agent(self, agent, limit=10):
        """Get recent tasks for an agent"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (a:Agent {name: $agent})-[:EXECUTED]->(t:Task)
                RETURN t ORDER BY t.created DESC LIMIT $limit
            """, agent=agent, limit=limit)
            return [dict(r['t']) for r in result]
    
    def get_tasks_by_status(self, status, limit=50):
        """Get tasks by status"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task {status: $status})
                RETURN t ORDER BY t.created DESC LIMIT $limit
            """, status=status, limit=limit)
            return [dict(r['t']) for r in result]
    
    def get_hourly_summary(self, hours=1):
        """Get task summary for last N hours"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task)
                WHERE t.created > datetime() - duration({hours: $hours})
                WITH 
                    t.agent AS agent,
                    t.status AS status,
                    t
                WITH
                    agent,
                    status,
                    count(t) AS count
                WITH
                    agent,
                    sum(CASE WHEN toUpper(status) = 'COMPLETED' THEN count ELSE 0 END) AS completed,
                    sum(CASE WHEN toUpper(status) = 'FAILED' THEN count ELSE 0 END) AS failed,
                    sum(CASE WHEN toUpper(status) IN ['RUNNING', 'EXECUTING'] THEN count ELSE 0 END) AS running,
                    sum(CASE WHEN toUpper(status) IN ['READY', 'PENDING'] THEN count ELSE 0 END) AS ready,
                    sum(count) AS total
                RETURN
                    agent,
                    total,
                    completed,
                    failed,
                    running,
                    ready
                ORDER BY total DESC
            """, hours=hours)
            return [dict(r) for r in result]
    
    def get_completion_rate(self, hours=24):
        """Get success/failure rates"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task)
                WHERE t.created > datetime() - duration({hours: $hours})
                  AND toUpper(t.status) IN ['COMPLETED', 'FAILED']
                WITH
                    count(t) AS total,
                    sum(CASE WHEN toUpper(t.status) = 'COMPLETED' THEN 1 ELSE 0 END) AS success
                RETURN
                    total,
                    success,
                    CASE WHEN total > 0 THEN round(100.0 * success / total, 1) ELSE 0.0 END AS success_rate
            """, hours=hours)
            record = result.single()
            return dict(record) if record else {}
    
    def get_continuous_tasks(self):
        """Get all running continuous tasks"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task {continuous: true, status: 'running'})
                RETURN t ORDER BY t.created DESC
            """)
            return [dict(r['t']) for r in result]
    
    def get_reflection_data(self, agent=None, hours=1):
        """Get data for hourly reflection"""
        with self.driver.session() as session:
            if agent:
                result = session.run("""
                    MATCH (t:Task {agent: $agent})
                    WHERE t.created > datetime() - duration({hours: $hours})
                    RETURN 
                        count(t) AS total_tasks,
                        sum(CASE WHEN t.status = 'completed' THEN 1 ELSE 0 END) AS completed,
                        sum(CASE WHEN t.status = 'failed' THEN 1 ELSE 0 END) AS failed,
                        coalesce(sum(t.retry_count), 0) AS total_retries
                    """, agent=agent, hours=hours)
            else:
                result = session.run("""
                    MATCH (t:Task)
                    WHERE t.created > datetime() - duration({hours: $hours})
                    RETURN 
                        count(t) AS total_tasks,
                        sum(CASE WHEN t.status = 'completed' THEN 1 ELSE 0 END) AS completed,
                        sum(CASE WHEN t.status = 'failed' THEN 1 ELSE 0 END) AS failed,
                        coalesce(sum(t.retry_count), 0) AS total_retries
                    """, hours=hours)
            
            record = result.single()
            return dict(record) if record else {}
    
    def get_historical_trends(self, days=7):
        """Get daily task trends for last N days"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task)
                WHERE t.created > datetime() - duration({days: $days})
                WITH 
                    date(t.created) AS day,
                    t.status AS status,
                    t
                WITH
                    day,
                    status,
                    count(t) AS count
                WITH
                    day,
                    sum(CASE WHEN toUpper(status) = 'COMPLETED' THEN count ELSE 0 END) AS completed,
                    sum(CASE WHEN toUpper(status) = 'FAILED' THEN count ELSE 0 END) AS failed,
                    sum(CASE WHEN toUpper(status) IN ['RUNNING', 'EXECUTING'] THEN count ELSE 0 END) AS running,
                    sum(count) AS total
                RETURN
                    day,
                    completed,
                    failed,
                    running,
                    total
                ORDER BY day DESC
                """, days=days)
            return [dict(r) for r in result]
    
    def get_agent_workload(self, days=7):
        """Get workload distribution by agent"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task)
                WHERE t.created > datetime() - duration({days: $days})
                WITH 
                    t.agent AS agent,
                    t.status AS status,
                    t
                WITH 
                    agent,
                    count(t) AS total_tasks,
                    sum(CASE WHEN toUpper(status) = 'COMPLETED' THEN 1 ELSE 0 END) AS completed
                RETURN
                    agent,
                    total_tasks,
                    completed,
                    CASE WHEN total_tasks > 0 THEN round(100.0 * completed / total_tasks, 1) ELSE 0.0 END AS success_rate
                ORDER BY total_tasks DESC
                """, days=days)
            return [dict(r) for r in result]
    
    def get_peak_hours(self, days=7):
        """Get busiest hours of day"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task)
                WHERE t.created > datetime() - duration({days: $days})
                WITH 
                    t.created.hour AS hour,
                    count(t) AS count
                RETURN 
                    hour,
                    count
                ORDER BY count DESC
                LIMIT 5
                """, days=days)
            return [dict(r) for r in result]
    
    def get_bottlenecks(self, hours=24):
        """Find tasks with most retries (potential bottlenecks)"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task)
                WHERE t.created > datetime() - duration({hours: $hours})
                  AND t.retry_count > 0
                RETURN 
                    t.agent AS agent,
                    t.label AS label,
                    t.retry_count AS retries,
                    t.status AS status
                ORDER BY retries DESC
                LIMIT 10
                """, hours=hours)
            return [dict(r) for r in result]


    # ==========================================================
    # Phase B: Neo4j as single source of truth
    # ==========================================================

    def create_task_full(self, agent, title, body, priority="normal",
                         source="system", depth=0, parent_id=None,
                         skill_hint=None, notify_on_complete=False,
                         notify_channel="signal", notify_target="+19194133445",
                         timeout=None, bucket=None, domain=None,
                         template_version=None, prompt_template=None,
                         use_optimization=True, origin_type=None, origin_initiator=None,
                         origin_source=None, origin_message_id=None):
        """Create task in Neo4j (primary) AND filesystem (backward compat).

        Args:
            domain: Task domain (research/implementation/ops/documentation/strategy/analysis).
                    Auto-classified from title+skill_hint if not provided.
            template_version: Version of prompt template used for this task.
            prompt_template: Name of prompt template used for this task.
            use_optimization: If True, apply learned prompt optimizations (default True).
                             Set OPTIMIZATION_ENABLED=false env var to disable globally.
            origin_type: Type of origin ("human" or "agent"). Auto-detected from source if not provided.
            origin_initiator: Who initiated the task (phone number for human, agent name for agent).
            origin_source: Source channel (signal, reflection, proposal, api, cron, etc.).

        Returns the task_id in canonical format: {priority}-{timestamp}-{uuid8}
        """
        # Generate task_id in canonical format
        task_id = generate_task_id(priority)

        # Validate before writing
        if not validate_task_id(task_id):
            logger.warning(f"Generated invalid task_id: {task_id}")

        label = f"{agent}-{task_id}"

        # Track optimization metadata
        prompt_optimization = {}

        # Auto-assign bucket based on priority if not provided (needed for optimizer context)
        if bucket is None:
            bucket_map = {
                'critical': 'CRITICAL',
                'high': 'TODAY',
                'normal': 'WEEK',
                'low': 'BACKLOG'
            }
            bucket = bucket_map.get(priority, 'BACKLOG')

        # Auto-classify domain if not provided (needed for optimizer task_type)
        if domain is None:
            try:
                from task_intake import classify_task_domain
                domain = classify_task_domain(title, skill_hint)
            except Exception:
                domain = "implementation"  # Safe default

        # Apply optimization if enabled (after domain is classified)
        if use_optimization:
            try:
                from kublai_task_optimizer import create_optimized_task
                # Build kwargs, excluding None values so optimizer can fill them
                opt_kwargs = {
                    "priority": priority,
                    "task_type": domain,  # Domain is properly classified now
                }
                # Only include these if they have values
                if skill_hint is not None:
                    opt_kwargs["skill_hint"] = skill_hint
                if timeout is not None:
                    opt_kwargs["timeout"] = timeout
                optimized = create_optimized_task(
                    agent=agent,
                    title=title,
                    body=body,
                    **opt_kwargs
                )
                # Apply optimized values (only if not explicitly provided)
                if skill_hint is None:
                    skill_hint = optimized.get("skill_hint")
                if timeout is None:
                    timeout = optimized.get("timeout")
                if template_version is None:
                    template_version = optimized.get("template_version")
                if prompt_template is None:
                    prompt_template = optimized.get("prompt_template")
                prompt_optimization = optimized.get("prompt_optimization", {})
            except ImportError:
                # Optimization module not available, continue with defaults
                pass
            except Exception as e:
                # Log but don't fail on optimization errors
                print(f"[task_tracker] Optimization failed: {e}")

        # Auto-detect origin if not provided
        if origin_type is None:
            # Detect from source or initiator
            if origin_initiator and origin_initiator.startswith("+"):
                origin_type = "human"
            elif source in ("signal", "api"):
                origin_type = "human"
            else:
                origin_type = "agent"

        # Default origin_source if not provided
        if origin_source is None:
            origin_source = source

        with self.driver.session() as session:
            session.run("""
                MERGE (a:Agent {name: $agent})
                CREATE (t:Task {
                    task_id: $task_id,
                    label: $label,
                    agent: $agent,
                    assigned_to: $agent,
                    title: $title,
                    body: $body,
                    priority: $priority,
                    source: $source,
                    depth: $depth,
                    parent_id: $parent_id,
                    skill_hint: $skill_hint,
                    bucket: $bucket,
                    domain: $domain,
                    template_version: $template_version,
                    prompt_template: $prompt_template,
                    prompt_construction: $prompt_construction,
                    task_params: $task_params,
                    origin_type: $origin_type,
                    origin_initiator: $origin_initiator,
                    origin_source: $origin_source,
                    origin_message_id: $origin_message_id,
                    notify_target: $notify_target,
                    origin_timestamp: datetime(),
                    status: 'PENDING',
                    created: datetime(),
                    retry_count: 0,
                    max_retries: 3
                })
                CREATE (a)-[:EXECUTED]->(t)
            """,
            task_id=task_id, label=label, agent=agent, title=title,
            body=body, priority=priority, source=source, depth=depth,
            parent_id=parent_id, skill_hint=skill_hint or "", bucket=bucket, domain=domain,
            template_version=template_version or "unknown", prompt_template=prompt_template or "standard",
            prompt_construction=json.dumps({
                "template_used": prompt_template or "standard",
                "template_version": template_version or "unknown",
                "optimization_source": prompt_optimization.get("source", "none"),
                "optimization_confidence": prompt_optimization.get("confidence"),
                "optimized_at": prompt_optimization.get("applied_at"),
            }),
            task_params=json.dumps({
                "priority": priority,
                "timeout_seconds": timeout,
                "skill_hint": skill_hint,
                "bucket": bucket,
            }),
            origin_type=origin_type or "unknown",
            origin_initiator=origin_initiator or "",
            origin_source=origin_source or "",
            origin_message_id=origin_message_id,
            notify_target=notify_target or "+19194133445")

        # Filesystem write for backward compatibility with agent-task-handler.py
        # agent-task-handler.py still reads task files from disk
        # Neo4j is the source of truth, filesystem is for compatibility
        task_file_written = False
        try:
            task_dir = agent_tasks_dir(agent)
            task_dir.mkdir(parents=True, exist_ok=True)
            task_file = task_dir / f"{task_id}.md"

            # Build task content in markdown format
            task_content = f"""# {title}

**Priority:** {priority}
**Agent:** {agent}
**Source:** {source}
**Skill Hint:** {skill_hint or 'auto-detected'}
**Domain:** {domain}
**Bucket:** {bucket}
notify_target: {notify_target}

## Description

{body}

---
*Created: {datetime.now().isoformat()}*
*Task ID: {task_id}*
"""

            task_file.write_text(task_content)
            task_file_written = True

            # Verify the file was actually written
            if not task_file.exists():
                raise IOError(f"File write reported success but file does not exist: {task_file}")

            # Verify the file has content
            if task_file.stat().st_size == 0:
                raise IOError(f"File exists but is empty: {task_file}")

            logger.debug(f"Wrote task file: {task_file} ({task_file.stat().st_size} bytes)")
        except Exception as e:
            logger.error(f"Failed to write task file for {task_id}: {e}")
            logger.error(f"Task dir: {task_dir}")
            logger.error(f"Agent: {agent}, Task ID: {task_id}")
            logger.error(f"File written flag: {task_file_written}")
            # Don't fail - Neo4j is the source of truth
            # But make the error visible for debugging
            print(f"WARNING: Task file write failed for {task_id}: {e}")
            print(f"  Expected location: {task_file}")
            print(f"  Agent: {agent}")

        return task_id

    def transition_task(self, task_id, new_status, actor="system"):
        """Transition task to new state with validation.

        Valid transitions:
            PENDING -> ASSIGNED, CANCELLED
            ASSIGNED -> EXECUTING, CANCELLED
            EXECUTING -> COMPLETED, FAILED, TIMEOUT, CANCELLED
            FAILED -> PENDING (retry)
            TIMEOUT -> PENDING (retry)
        """
        VALID_TRANSITIONS = {
            "PENDING": {"ASSIGNED", "CANCELLED"},
            "ASSIGNED": {"EXECUTING", "CANCELLED"},
            "EXECUTING": {"COMPLETED", "FAILED", "TIMEOUT", "CANCELLED"},
            "FAILED": {"PENDING"},
            "TIMEOUT": {"PENDING"},
        }

        with self.driver.session() as session:
            # Get current status
            result = session.run("""
                MATCH (t:Task {task_id: $task_id})
                RETURN t.status AS status
            """, task_id=task_id)
            record = result.single()

            if not record:
                return {"success": False, "error": f"Task {task_id} not found"}

            current = record["status"]
            allowed = VALID_TRANSITIONS.get(current, set())

            if new_status not in allowed:
                return {
                    "success": False,
                    "error": f"Invalid transition: {current} -> {new_status} (allowed: {allowed})"
                }

            # Apply transition and log it
            session.run("""
                MATCH (t:Task {task_id: $task_id})
                SET t.status = $new_status,
                    t.updated = datetime()
                CREATE (t)-[:TRANSITIONED {
                    from_status: $current,
                    to_status: $new_status,
                    action: $action,
                    timestamp: datetime(),
                    actor: $actor
                }]->(t)
            """, task_id=task_id, new_status=new_status, current=current,
                action=f"{current}->{new_status}", actor=actor)

            # Set completed timestamp for terminal states
            if new_status in ("COMPLETED", "FAILED", "TIMEOUT", "CANCELLED"):
                session.run("""
                    MATCH (t:Task {task_id: $task_id})
                    SET t.completed = datetime()
                """, task_id=task_id)

            return {"success": True, "from": current, "to": new_status}

    def sync_check(self):
        """Bidirectional sync: compare Neo4j task states with filesystem.

        Two query scopes:
        - Forward (filesystem → Neo4j): recent tasks (P1D) for status mismatch
        - Reverse (Neo4j → filesystem): ALL non-terminal tasks, any age, to catch
          orphans that outlived the 24h window

        Returns a dict of discrepancies.
        """
        base = _AGENTS_BASE
        agents = ["kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei", "tolui"]
        discrepancies = []

        # Get recent tasks from Neo4j (for forward pass)
        neo4j_tasks = {}
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task)
                WHERE t.created > datetime() - duration('P1D')
                RETURN t.task_id AS task_id, t.agent AS agent,
                       t.status AS status, t.label AS label
            """)
            for r in result:
                tid = r.get("task_id")
                if tid:
                    neo4j_tasks[tid] = {
                        "agent": r["agent"],
                        "status": r["status"],
                        "label": r["label"],
                    }

            # Separate query: ALL non-terminal tasks regardless of age (for reverse pass)
            non_terminal_tasks = {}
            result2 = session.run("""
                MATCH (t:Task)
                WHERE t.status IN ['PENDING', 'ASSIGNED', 'EXECUTING', 'running', 'ready']
                RETURN t.task_id AS task_id, t.agent AS agent,
                       t.status AS status, t.label AS label
            """)
            for r in result2:
                tid = r.get("task_id")
                if tid:
                    non_terminal_tasks[tid] = {
                        "agent": r["agent"],
                        "status": r["status"],
                        "label": r["label"],
                    }

        # Track which Neo4j task_ids we find on filesystem
        seen_task_ids = set()

        # Forward pass: Check filesystem for tasks with task_id in frontmatter
        for agent in agents:
            task_dir = f"{base}/{agent}/tasks"
            if not os.path.isdir(task_dir):
                continue
            for fpath in glob.glob(f"{task_dir}/*.md"):
                try:
                    with open(fpath) as f:
                        content = f.read(500)
                    import re
                    match = re.search(r'^task_id:\s*(\S+)', content, re.MULTILINE)
                    if not match:
                        continue
                    file_task_id = match.group(1)

                    fname = os.path.basename(fpath)
                    seen_task_ids.add(file_task_id)

                    if '.failed.done' in fname or '.orphan-failed.done' in fname:
                        file_status = "FAILED"
                    elif '.completed.done' in fname:
                        file_status = "COMPLETED"
                    elif '.done' in fname:
                        file_status = "COMPLETED"
                    elif '.executing' in fname:
                        file_status = "EXECUTING"
                    else:
                        file_status = "PENDING"

                    # Check against both recent and non-terminal sets
                    neo_entry = neo4j_tasks.get(file_task_id) or non_terminal_tasks.get(file_task_id)
                    if neo_entry and neo_entry["status"] != file_status:
                        discrepancies.append({
                            "task_id": file_task_id,
                            "agent": agent,
                            "file": fname,
                            "file_status": file_status,
                            "neo4j_status": neo_entry["status"],
                        })
                except Exception:
                    continue

        # Reverse pass: non-terminal Neo4j tasks with no filesystem file = orphan
        for tid, info in non_terminal_tasks.items():
            if tid in seen_task_ids:
                continue
            discrepancies.append({
                "task_id": tid,
                "agent": info["agent"],
                "file": None,
                "file_status": "COMPLETED",  # assume done if file is gone
                "neo4j_status": info["status"],
                "orphan": True,
            })

        return {
            "checked": datetime.now().isoformat(),
            "neo4j_count": len(neo4j_tasks),
            "non_terminal_count": len(non_terminal_tasks),
            "discrepancies": discrepancies,
        }

    def sync_reconcile(self, dry_run=False):
        """Detect AND fix Neo4j/filesystem state discrepancies.

        Filesystem is the source of truth. When Neo4j status disagrees with
        the filesystem file suffix (.executing, .done, plain .md), Neo4j is
        updated to match.

        Returns dict with counts of fixes applied (or would-be-applied if dry_run).
        """
        result = self.sync_check()
        discrepancies = result.get("discrepancies", [])
        fixed = 0
        skipped = 0

        if not discrepancies:
            return {
                "checked": result["checked"],
                "neo4j_count": result["neo4j_count"],
                "discrepancies": 0,
                "fixed": 0,
                "skipped": 0,
                "dry_run": dry_run,
            }

        with self.driver.session() as session:
            for d in discrepancies:
                task_id = d["task_id"]
                file_status = d["file_status"]
                neo4j_status = d["neo4j_status"]

                # Safe reconciliation directions (filesystem is source of truth):
                # - Neo4j PENDING/EXECUTING but file is COMPLETED/FAILED -> fix
                # - Neo4j EXECUTING but file is PENDING -> fix to PENDING
                # - Neo4j FAILED/TIMEOUT -> PENDING/EXECUTING: allowed (task retried)
                # - Do NOT downgrade COMPLETED in Neo4j (completed is final)
                # - Do NOT downgrade CANCELLED in Neo4j
                if neo4j_status in ("COMPLETED", "CANCELLED"):
                    skipped += 1
                    continue
                # FAILED/TIMEOUT -> only allow if file shows non-terminal (retry)
                if neo4j_status in ("FAILED", "TIMEOUT") and file_status not in ("PENDING", "EXECUTING"):
                    skipped += 1
                    continue

                if dry_run:
                    fixed += 1
                    continue

                is_terminal = file_status in ("COMPLETED", "FAILED")
                session.run("""
                    MATCH (t:Task {task_id: $task_id})
                    SET t.status = $file_status,
                        t.updated = datetime(),
                        t.reconciled = true,
                        t.reconciled_at = datetime(),
                        t.completed = CASE WHEN $is_terminal THEN datetime() ELSE t.completed END,
                        t.session_key = CASE WHEN $is_terminal THEN null ELSE t.session_key END
                """, task_id=task_id, file_status=file_status, is_terminal=is_terminal)
                fixed += 1

        return {
            "checked": result["checked"],
            "neo4j_count": result["neo4j_count"],
            "discrepancies": len(discrepancies),
            "fixed": fixed,
            "skipped": skipped,
            "dry_run": dry_run,
        }


    # ==========================================================
    # Phase B4: Hypothesis validation
    # ==========================================================

    def validate_hypotheses(self):
        """Check pending Hypothesis nodes and mark as validated or expired.

        - Hypotheses older than 2h with matching completed tasks -> validated
        - Hypotheses older than 24h with no match -> expired
        """
        results = {"validated": 0, "expired": 0, "pending": 0}

        with self.driver.session() as session:
            # Validate: pending hypotheses older than 2h with completed tasks
            r = session.run("""
                MATCH (h:Hypothesis {status: 'pending'})
                WHERE h.created < datetime() - duration('PT2H')
                OPTIONAL MATCH (t:Task)
                    WHERE t.status = 'completed'
                      AND t.created > h.created
                      AND (toLower(t.title) CONTAINS toLower(substring(h.action, 0, 30))
                           OR toLower(t.task) CONTAINS toLower(substring(h.action, 0, 30)))
                WITH h, count(t) AS matching_tasks
                WHERE matching_tasks > 0
                SET h.status = 'validated',
                    h.validated_at = datetime(),
                    h.validated = true
                RETURN count(h) AS cnt
            """)
            record = r.single()
            results["validated"] = record["cnt"] if record else 0

            # Expire: pending hypotheses older than 24h with no match
            r = session.run("""
                MATCH (h:Hypothesis {status: 'pending'})
                WHERE h.created < datetime() - duration('P1D')
                SET h.status = 'expired',
                    h.expired_at = datetime()
                RETURN count(h) AS cnt
            """)
            record = r.single()
            results["expired"] = record["cnt"] if record else 0

            # Count remaining pending
            r = session.run("""
                MATCH (h:Hypothesis {status: 'pending'})
                RETURN count(h) AS cnt
            """)
            record = r.single()
            results["pending"] = record["cnt"] if record else 0

        return results

    # ==========================================================
    # Phase B5: WHEN/THEN Rules as Neo4j entities
    # ==========================================================

    def create_rule(self, agent, condition, action, source="system"):
        """Create a (:Rule) node with 'proposed' status."""
        rule_id = str(uuid.uuid4())[:12]
        with self.driver.session() as session:
            session.run("""
                CREATE (r:Rule {
                    rule_id: $rule_id,
                    agent: $agent,
                    condition: $condition,
                    action: $action,
                    status: 'proposed',
                    source: $source,
                    created: datetime(),
                    last_invoked: null,
                    invocations: 0
                })
            """, rule_id=rule_id, agent=agent, condition=condition,
                action=action, source=source)
        return rule_id

    def invoke_rule(self, rule_id):
        """Mark a rule as invoked. Transitions proposed->active on first use."""
        with self.driver.session() as session:
            session.run("""
                MATCH (r:Rule {rule_id: $rule_id})
                SET r.invocations = r.invocations + 1,
                    r.last_invoked = datetime(),
                    r.status = CASE
                        WHEN r.status = 'proposed' THEN 'active'
                        ELSE r.status
                    END
            """, rule_id=rule_id)

    def prune_rules(self):
        """Lifecycle management for rules.

        - active rules with no invocation for 7 days -> deprecated
        - deprecated rules with no invocation for 30 days -> pruned (deleted)
        """
        results = {"deprecated": 0, "pruned": 0}
        with self.driver.session() as session:
            # Deprecate: active rules unused for 7 days
            r = session.run("""
                MATCH (r:Rule {status: 'active'})
                WHERE r.last_invoked < datetime() - duration('P7D')
                SET r.status = 'deprecated'
                RETURN count(r) AS cnt
            """)
            record = r.single()
            results["deprecated"] = record["cnt"] if record else 0

            # Prune: deprecated rules unused for 30 days
            r = session.run("""
                MATCH (r:Rule {status: 'deprecated'})
                WHERE r.last_invoked < datetime() - duration('P30D')
                   OR (r.last_invoked IS NULL AND r.created < datetime() - duration('P30D'))
                DELETE r
                RETURN count(r) AS cnt
            """)
            record = r.single()
            results["pruned"] = record["cnt"] if record else 0

        return results

    def get_active_rules(self, agent=None):
        """Get active rules, optionally filtered by agent."""
        with self.driver.session() as session:
            if agent:
                result = session.run("""
                    MATCH (r:Rule)
                    WHERE r.status IN ['proposed', 'active']
                      AND r.agent = $agent
                    RETURN r.rule_id AS rule_id, r.agent AS agent,
                           r.condition AS condition, r.action AS action,
                           r.status AS status, r.invocations AS invocations
                    ORDER BY r.invocations DESC
                """, agent=agent)
            else:
                result = session.run("""
                    MATCH (r:Rule)
                    WHERE r.status IN ['proposed', 'active']
                    RETURN r.rule_id AS rule_id, r.agent AS agent,
                           r.condition AS condition, r.action AS action,
                           r.status AS status, r.invocations AS invocations
                    ORDER BY r.invocations DESC
                """)
            return [dict(r) for r in result]

    # ==========================================================
    # Pipeline observability events
    # ==========================================================

    def emit_pipeline_event(self, event_type, payload=None, agent=None,
                            status="delivered", latency_ms=None, error=None):
        """Create a (:PipelineEvent) node for observability.

        Event types:
        - TASK_COMPLETE_REPORT: Sent after /task-complete haiku finishes
        - FAILURE_ALERT: Sent when a task fails
        - HOURLY_DIGEST: Hourly reflection context generated
        - QUEUED_EVENT: Task queued for execution
        - CAPABILITY_SCORE_UPDATE: Capability scores recomputed
        - RULE_PROPAGATION: Cross-agent rule proposed
        """
        event_id = str(uuid.uuid4())[:12]
        try:
            with self.driver.session() as session:
                session.run("""
                    CREATE (e:PipelineEvent {
                        event_id: $event_id,
                        event_type: $event_type,
                        agent: $agent,
                        status: $status,
                        latency_ms: $latency_ms,
                        error: $error,
                        payload: $payload,
                        created: datetime()
                    })
                """,
                event_id=event_id, event_type=event_type,
                agent=agent or "", status=status,
                latency_ms=latency_ms, error=error,
                payload=json.dumps(payload) if payload else None)
        except Exception as e:
            logger.debug(f"Failed to emit pipeline event {event_type}: {e}")
        return event_id

    def get_pipeline_events(self, event_type=None, hours=1, limit=50):
        """Query recent pipeline events."""
        with self.driver.session() as session:
            if event_type:
                result = session.run("""
                    MATCH (e:PipelineEvent)
                    WHERE e.event_type = $event_type
                      AND e.created > datetime() - duration({hours: $hours})
                    RETURN e ORDER BY e.created DESC LIMIT $limit
                """, event_type=event_type, hours=hours, limit=limit)
            else:
                result = session.run("""
                    MATCH (e:PipelineEvent)
                    WHERE e.created > datetime() - duration({hours: $hours})
                    RETURN e ORDER BY e.created DESC LIMIT $limit
                """, hours=hours, limit=limit)
            return [dict(r['e']) for r in result]

    def prune_pipeline_events(self, days=7):
        """Remove PipelineEvent nodes older than N days."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (e:PipelineEvent)
                WHERE e.created < datetime() - duration({days: $days})
                DELETE e
                RETURN count(e) AS pruned
            """, days=days)
            record = result.single()
            return record["pruned"] if record else 0


    # ==========================================================
    # Completion Gate Support
    # ==========================================================

    def create_gate_node(self, task_id: str, audit_data: dict):
        """Create GateAudit node for tracking.

        Args:
            task_id: The task being audited
            audit_data: Dictionary with completion_percentage, can_complete,
                       required_followups_count, optional_improvements_count
        """
        audit_id = f"audit-{task_id}-{datetime.now().strftime('%Y%m%d')}"
        with self.driver.session() as session:
            session.run("""
                CREATE (g:GateAudit {
                    audit_id: $audit_id,
                    task_id: $task_id,
                    timestamp: datetime(),
                    completion_percentage: $completion_pct,
                    can_complete: $can_complete,
                    required_followups_count: $required_count,
                    optional_improvements_count: $optional_count
                })
            """,
            audit_id=audit_id,
            task_id=task_id,
            completion_pct=audit_data.get("completion_percentage", 100),
            can_complete=audit_data.get("can_complete", True),
            required_count=len(audit_data.get("required_followups", [])),
            optional_count=len(audit_data.get("optional_improvements", []))
            )

        return audit_id

    def update_gate_status(self, task_id: str, status: str,
                          completion_percentage: int = None,
                          audit_ref: str = None):
        """Update gate_status property on Task.

        Args:
            task_id: Task to update
            status: Gate status (pending, auditing, waiting_followups, ready,
                   blocked, passed, bypassed)
            completion_percentage: Optional completion percentage
            audit_ref: Optional path to audit JSON file
        """
        with self.driver.session() as session:
            query = """
                MATCH (t:Task {task_id: $task_id})
                SET t.gate_status = $status,
                    t.gate_updated = datetime()
            """
            params = {"task_id": task_id, "status": status}

            if completion_percentage is not None:
                query += ", t.completion_percentage = $completion_pct"
                params["completion_pct"] = completion_percentage

            if audit_ref:
                query += ", t.gate_audit_ref = $audit_ref"
                params["audit_ref"] = audit_ref

            session.run(query, **params)

    def link_followup(self, parent_id: str, followup_id: str,
                     gate_required: bool = True):
        """Create HAS_FOLLOWUP relationship between parent and follow-up.

        Args:
            parent_id: Parent task ID
            followup_id: Follow-up task ID
            gate_required: Whether this followup must complete for parent gate
        """
        with self.driver.session() as session:
            session.run("""
                MATCH (parent:Task {task_id: $parent_id})
                MATCH (followup:Task {task_id: $followup_id})
                CREATE (parent)-[:HAS_FOLLOWUP {gate_required: $gate_required, created: datetime()}]->(followup)
                CREATE (followup)-[:FOLLOWS_UP {created: datetime()}]->(parent)
            """, parent_id=parent_id, followup_id=followup_id, gate_required=gate_required)

    def get_followup_tasks(self, task_id: str) -> list:
        """Query for all follow-ups of a task.

        Args:
            task_id: Parent task ID

        Returns:
            List of dicts with followup task info
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (parent:Task {task_id: $task_id})-[:HAS_FOLLOWUP]->(followup:Task)
                RETURN followup.task_id AS task_id,
                       followup.agent AS agent,
                       followup.status AS status,
                       followup.gate_required AS gate_required
                ORDER BY followup.created ASC
            """, task_id=task_id)
            return [dict(r) for r in result]

    def get_gate_metrics(self) -> dict:
        """Return aggregate gate metrics.

        Returns dict with:
        - pass_rate: Percentage of gates that passed
        - avg_completion: Average completion percentage
        - avg_followups: Average follow-ups per task
        - active_gates: Count of gates in non-terminal states
        - blocked_gates: Count of blocked gates
        """
        with self.driver.session() as session:
            # Get audit metrics (handle empty case to avoid division by zero)
            result = session.run("""
                MATCH (g:GateAudit)
                WHERE g.timestamp > datetime() - duration('PT24H')
                WITH
                    count(CASE WHEN g.can_complete THEN 1 END) as passed,
                    count(*) as total,
                    avg(g.completion_percentage) as avg_pct,
                    avg(g.required_followups_count) as avg_followups
                RETURN {
                    passed: passed,
                    total: total,
                    pass_rate: CASE WHEN total > 0 THEN round(100.0 * passed / total, 1) ELSE 0.0 END,
                    avg_completion: round(coalesce(avg_pct, 0), 1),
                    avg_followups: round(coalesce(avg_followups, 0), 1)
                } as audit_metrics
            """)
            record = result.single()
            audit_metrics = dict(record["audit_metrics"]) if record and record.get("audit_metrics") else {
                "passed": 0, "total": 0, "pass_rate": 0.0, "avg_completion": 0.0, "avg_followups": 0.0
            }

            # Get active gate counts
            result = session.run("""
                MATCH (t:Task)
                WHERE t.gate_status IS NOT NULL
                  AND t.gate_status IN ['pending', 'auditing', 'waiting_followups', 'blocked']
                WITH
                    count(CASE WHEN t.gate_status = 'blocked' THEN 1 END) as blocked,
                    count(*) as active
                RETURN {active: active, blocked: blocked} as gate_counts
            """)
            record = result.single()
            gate_counts = dict(record["gate_counts"]) if record and record.get("gate_counts") else {"active": 0, "blocked": 0}

            return {
                **audit_metrics,
                **gate_counts
            }

    def find_pending_gates(self, limit: int = 100) -> list:
        """Find tasks in pending gate states.

        Args:
            limit: Maximum number of gates to return

        Returns:
            List of dicts with task_id, gate_status, agent, etc.
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task)
                WHERE t.gate_status IN ['pending', 'waiting_followups', 'auditing']
                RETURN t.task_id AS task_id,
                       t.agent AS agent,
                       t.gate_status AS gate_status,
                       t.completion_percentage AS completion_percentage,
                       t.created AS created
                ORDER BY t.created ASC
                LIMIT $limit
            """, limit=limit)
            return [dict(r) for r in result]

    def check_gate_resolve_status(self, task_id: str) -> dict:
        """Check if a gate can be resolved (all follow-ups complete).

        Args:
            task_id: Parent task ID

        Returns:
            Dict with can_resolve (bool), total_followups, completed_followups
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (parent:Task {task_id: $task_id})-[:HAS_FOLLOWUP]->(followup:Task)
                WITH parent,
                     count(followup) as total,
                     sum(CASE WHEN followup.status = 'COMPLETED' THEN 1 ELSE 0 END) as completed
                RETURN total,
                       completed,
                       total = completed as can_resolve
            """, task_id=task_id)
            record = result.single()
            if record:
                return {
                    "total_followups": record["total"],
                    "completed_followups": record["completed"],
                    "can_resolve": record["can_resolve"]
                }
            return {"total_followups": 0, "completed_followups": 0, "can_resolve": True}

    def create_gate_resolution(self, task_id: str, status: str,
                             total_followups: int, resolution_cycles: int = 1):
        """Create GateResolution node when a gate is resolved.

        Args:
            task_id: Original task ID
            status: Resolution status (PASSED, BLOCKED, BYPASSED)
            total_followups: Number of follow-ups created
            resolution_cycles: How many audit/followup cycles
        """
        with self.driver.session() as session:
            session.run("""
                CREATE (gr:GateResolution {
                    gate_id: $gate_id,
                    original_task: $task_id,
                    status: $status,
                    created_at: datetime(),
                    resolved_at: datetime(),
                    total_followups: $total_followups,
                    resolution_cycles: $resolution_cycles
                })
            """,
            gate_id=f"gate-{task_id}",
            task_id=task_id,
            status=status,
            total_followups=total_followups,
            resolution_cycles=resolution_cycles
            )

    def detect_gate_cycles(self, max_depth: int = 3) -> list:
        """Detect circular dependencies in follow-up chains.

        Args:
            max_depth: Maximum depth to traverse (1-10, validated)

        Returns:
            List of cycles found (each cycle is a list of task_ids)
        """
        # Validate max_depth to prevent injection (must be integer 1-10)
        if not isinstance(max_depth, int) or max_depth < 1 or max_depth > 10:
            raise ValueError("max_depth must be an integer between 1 and 10")

        with self.driver.session() as session:
            # Neo4j 5 doesn't allow parameters in relationship pattern length
            # Build query with validated literal depth (safe after validation)
            result = session.run(f"""
                MATCH path = (start:Task)-[:HAS_FOLLOWUP*..{max_depth}]->(start)
                WITH [node in nodes(path) | node.task_id] as cycle
                RETURN DISTINCT cycle
                LIMIT 10
            """)
            return [record["cycle"] for record in result]

    def update_task_scores(self, task_id, delegation_score, domain_match_score,
                          substantive_score, pending_time_score, total_score,
                          self_route_flag, scored_agent):
        """Update task quality scores in Neo4j.

        Args:
            task_id: Task label/identifier
            delegation_score: 0-2 (routed to specialist vs self-routed)
            domain_match_score: 0-3 (keyword match quality)
            substantive_score: 0-3 (output substance)
            pending_time_score: 0-2 (pickup speed)
            total_score: 0-10 (sum of above)
            self_route_flag: True if kublai self-routed specialist work
            scored_agent: Agent that executed the task
        """
        with self.driver.session() as session:
            session.run("""
                MATCH (t:Task)
                WHERE t.task_id = $task_id OR t.label = $task_id OR t.label ENDS WITH $task_id
                SET t.scored = true,
                    t.delegation_score = $delegation_score,
                    t.domain_match_score = $domain_match_score,
                    t.substantive_score = $substantive_score,
                    t.pending_time_score = $pending_time_score,
                    t.total_score = $total_score,
                    t.self_route_flag = $self_route_flag,
                    t.scored_agent = $scored_agent,
                    t.scored_at = datetime()
            """,
            task_id=task_id,
            delegation_score=delegation_score,
            domain_match_score=domain_match_score,
            substantive_score=substantive_score,
            pending_time_score=pending_time_score,
            total_score=total_score,
            self_route_flag=self_route_flag,
            scored_agent=scored_agent)

    def get_low_quality_tasks(self, threshold=7, hours=24):
        """Find completed tasks with quality below threshold.

        Args:
            threshold: Maximum total_score to include (default 7)
            hours: Look back period in hours (default 24)

        Returns:
            List of dicts with task label, agent, and scores
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task)
                WHERE t.status = 'COMPLETED'
                  AND t.total_score < $threshold
                  AND t.completed > datetime() - duration({hours: $hours})
                RETURN t.label, t.agent, t.total_score, t.delegation_score, t.substantive_score
                ORDER BY t.total_score ASC
                LIMIT 50
            """, threshold=threshold, hours=hours)
            return [dict(r) for r in result]


# Singleton instance
_tracker = None

def get_tracker():
    """Get or create tracker instance"""
    global _tracker
    if _tracker is None:
        _tracker = TaskTracker()
        import atexit
        atexit.register(lambda: _tracker.close() if _tracker else None)
    return _tracker


if __name__ == "__main__":
    # Test
    tracker = get_tracker()
    print("Neo4j Task Tracker initialized")
    print("Hourly summary:", tracker.get_hourly_summary(1))
    tracker.close()
