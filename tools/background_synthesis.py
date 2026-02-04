"""
Chagatai Background Synthesis - Background task management for the OpenClaw system.

This module provides the BackgroundTaskManager class for running background tasks
when agents are idle, including reflection consolidation and knowledge synthesis.

Named after Chagatai, the writer/synthesis agent who performs background synthesis
tasks in the 6-agent OpenClaw system.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any

from neo4j.exceptions import Neo4jError

# Configure logging
logger = logging.getLogger(__name__)


class BackgroundTaskError(Exception):
    """Raised when a background task operation fails."""
    pass


class TaskNotFoundError(Exception):
    """Raised when a background task ID is not found."""
    pass


class BackgroundTaskManager:
    """
    Background task management and synthesis for the OpenClaw system.

    Manages background tasks that run when agents are idle, including:
    - Reflection consolidation (triggered when 5+ reflections exist)
    - Knowledge synthesis from multiple sources
    - Knowledge graph maintenance (cleaning orphaned nodes)

    Attributes:
        memory: OperationalMemory instance for persistence
        reflection_threshold: Number of unconsolidated reflections to trigger consolidation
        idle_threshold_seconds: Default idle time threshold for agents
    """

    # Valid task types
    VALID_TASK_TYPES = [
        "reflection_consolidation",
        "knowledge_synthesis",
        "graph_maintenance",
        "other"
    ]

    # Valid priorities
    VALID_PRIORITIES = ["low", "normal", "high"]

    # Valid statuses
    VALID_STATUSES = ["pending", "running", "completed", "failed"]

    def __init__(
        self,
        memory: Any,  # OperationalMemory
        reflection_threshold: int = 5,
        idle_threshold_seconds: int = 300
    ):
        """
        Initialize the BackgroundTaskManager.

        Args:
            memory: OperationalMemory instance for Neo4j persistence
            reflection_threshold: Number of unconsolidated reflections to trigger consolidation
            idle_threshold_seconds: Default idle time threshold for agents (default 5 minutes)
        """
        self.memory = memory
        self.reflection_threshold = reflection_threshold
        self.idle_threshold_seconds = idle_threshold_seconds

        logger.info(
            f"BackgroundTaskManager initialized with reflection_threshold={reflection_threshold}, "
            f"idle_threshold_seconds={idle_threshold_seconds}"
        )

    def _generate_id(self) -> str:
        """Generate a unique ID using the memory's method or fallback to uuid."""
        if hasattr(self.memory, '_generate_id'):
            return self.memory._generate_id()
        import uuid
        return str(uuid.uuid4())

    def _now(self) -> datetime:
        """Get current UTC datetime using the memory's method or fallback."""
        if hasattr(self.memory, '_now'):
            return self.memory._now()
        return datetime.now(timezone.utc)

    def _session(self):
        """Get Neo4j session context manager from memory."""
        if hasattr(self.memory, '_session'):
            return self.memory._session()
        # Fallback - return a no-op context manager
        from contextlib import nullcontext
        return nullcontext(None)

    def is_agent_idle(self, agent: str, idle_threshold_seconds: Optional[int] = None) -> bool:
        """
        Check if an agent is idle.

        An agent is considered idle if:
        - No task claimed in last idle_threshold_seconds
        - No active session (check agent heartbeat/status)
        - Not marked as busy

        Args:
            agent: Agent name to check
            idle_threshold_seconds: Override default idle threshold

        Returns:
            True if agent is idle, False otherwise
        """
        threshold = idle_threshold_seconds or self.idle_threshold_seconds

        # Get agent status from memory
        if hasattr(self.memory, 'get_agent_status'):
            agent_status = self.memory.get_agent_status(agent)
        else:
            agent_status = None

        if agent_status is None:
            # No status found, assume idle
            logger.debug(f"Agent {agent}: no status found, assuming idle")
            return True

        # Check if agent is marked as busy
        status = agent_status.get('status', 'unknown')
        if status == 'busy':
            logger.debug(f"Agent {agent}: marked as busy")
            return False

        # Check last heartbeat
        last_heartbeat = agent_status.get('last_heartbeat')
        if last_heartbeat:
            if isinstance(last_heartbeat, str):
                # Parse ISO format string
                try:
                    last_heartbeat = datetime.fromisoformat(last_heartbeat.replace('Z', '+00:00'))
                except ValueError:
                    last_heartbeat = None

            if last_heartbeat:
                now = self._now()
                # Ensure both are timezone-aware
                if last_heartbeat.tzinfo is None:
                    last_heartbeat = last_heartbeat.replace(tzinfo=timezone.utc)
                elapsed = (now - last_heartbeat).total_seconds()
                if elapsed < threshold:
                    logger.debug(f"Agent {agent}: active heartbeat {elapsed:.0f}s ago")
                    return False

        # Check if agent has in-progress tasks
        if hasattr(self.memory, 'list_tasks_by_status'):
            in_progress = self.memory.list_tasks_by_status('in_progress', agent=agent)
            if in_progress:
                logger.debug(f"Agent {agent}: has {len(in_progress)} in-progress tasks")
                return False

        logger.debug(f"Agent {agent}: is idle")
        return True

    def queue_task(
        self,
        task_type: str,
        priority: str = "normal",
        data: Optional[Dict] = None
    ) -> str:
        """
        Queue a background task.

        Args:
            task_type: Type of task ('reflection_consolidation', 'knowledge_synthesis',
                      'graph_maintenance', 'other')
            priority: Task priority ('low', 'normal', 'high')
            data: Optional task data dictionary

        Returns:
            Task ID string

        Raises:
            ValueError: If task_type or priority is invalid
        """
        if task_type not in self.VALID_TASK_TYPES:
            raise ValueError(
                f"Invalid task_type '{task_type}'. Must be one of: {self.VALID_TASK_TYPES}"
            )

        if priority not in self.VALID_PRIORITIES:
            raise ValueError(
                f"Invalid priority '{priority}'. Must be one of: {self.VALID_PRIORITIES}"
            )

        task_id = self._generate_id()
        created_at = self._now()

        # Convert data to string for Neo4j storage
        data_str = str(data) if data else None

        cypher = """
        CREATE (t:BackgroundTask {
            id: $task_id,
            task_type: $task_type,
            priority: $priority,
            status: 'pending',
            data: $data,
            created_at: $created_at,
            started_at: null,
            completed_at: null,
            result: null,
            error_message: null
        })
        RETURN t.id as task_id
        """

        with self._session() as session:
            if session is None:
                logger.warning(f"Fallback mode: Background task creation simulated for {task_type}")
                return task_id

            try:
                result = session.run(
                    cypher,
                    task_id=task_id,
                    task_type=task_type,
                    priority=priority,
                    data=data_str,
                    created_at=created_at
                )
                record = result.single()
                if record:
                    logger.info(f"Background task queued: {task_id} (type: {task_type}, priority: {priority})")
                    return record["task_id"]
                else:
                    raise RuntimeError("Background task creation failed: no record returned")
            except Neo4jError as e:
                logger.error(f"Failed to queue background task: {e}")
                raise

    def get_next_task(self) -> Optional[Dict]:
        """
        Get the next pending background task (priority-ordered).

        Returns:
            Task dict if found, None otherwise
        """
        cypher = """
        MATCH (t:BackgroundTask {status: 'pending'})
        RETURN t
        ORDER BY
            CASE t.priority
                WHEN 'high' THEN 3
                WHEN 'normal' THEN 2
                WHEN 'low' THEN 1
                ELSE 0
            END DESC,
            t.created_at ASC
        LIMIT 1
        """

        with self._session() as session:
            if session is None:
                return None

            try:
                result = session.run(cypher)
                record = result.single()
                if record:
                    task_dict = dict(record["t"])
                    # Parse data back from string if possible
                    if task_dict.get("data"):
                        try:
                            import ast
                            task_dict["data"] = ast.literal_eval(task_dict["data"])
                        except (ValueError, SyntaxError):
                            pass  # Keep as string if parsing fails
                    return task_dict
                return None
            except Neo4jError as e:
                logger.error(f"Failed to get next background task: {e}")
                raise

    def start_task(self, task_id: str) -> bool:
        """
        Mark a background task as running.

        Args:
            task_id: Task ID to start

        Returns:
            True if successful, False if task not found

        Raises:
            TaskNotFoundError: If task ID not found
        """
        started_at = self._now()

        cypher = """
        MATCH (t:BackgroundTask {id: $task_id})
        WHERE t.status = 'pending'
        SET t.status = 'running',
            t.started_at = $started_at
        RETURN t.id as task_id
        """

        with self._session() as session:
            if session is None:
                logger.warning(f"Fallback mode: Background task start simulated for {task_id}")
                return True

            try:
                result = session.run(
                    cypher,
                    task_id=task_id,
                    started_at=started_at
                )
                record = result.single()

                if record is None:
                    raise TaskNotFoundError(f"Task not found or not pending: {task_id}")

                logger.info(f"Background task started: {task_id}")
                return True

            except Neo4jError as e:
                logger.error(f"Failed to start background task: {e}")
                raise

    def complete_task(self, task_id: str, result: Dict) -> bool:
        """
        Mark a background task as completed.

        Args:
            task_id: Task ID to complete
            result: Task result dictionary

        Returns:
            True if successful, False if task not found

        Raises:
            TaskNotFoundError: If task ID not found
        """
        completed_at = self._now()
        result_str = str(result) if result else None

        cypher = """
        MATCH (t:BackgroundTask {id: $task_id})
        WHERE t.status = 'running'
        SET t.status = 'completed',
            t.completed_at = $completed_at,
            t.result = $result
        RETURN t.id as task_id
        """

        with self._session() as session:
            if session is None:
                logger.warning(f"Fallback mode: Background task completion simulated for {task_id}")
                return True

            try:
                result_run = session.run(
                    cypher,
                    task_id=task_id,
                    completed_at=completed_at,
                    result=result_str
                )
                record = result_run.single()

                if record is None:
                    raise TaskNotFoundError(f"Task not found or not running: {task_id}")

                logger.info(f"Background task completed: {task_id}")
                return True

            except Neo4jError as e:
                logger.error(f"Failed to complete background task: {e}")
                raise

    def fail_task(self, task_id: str, error_message: str) -> bool:
        """
        Mark a background task as failed.

        Args:
            task_id: Task ID to fail
            error_message: Error message describing the failure

        Returns:
            True if successful, False if task not found

        Raises:
            TaskNotFoundError: If task ID not found
        """
        completed_at = self._now()

        cypher = """
        MATCH (t:BackgroundTask {id: $task_id})
        WHERE t.status = 'running'
        SET t.status = 'failed',
            t.completed_at = $completed_at,
            t.error_message = $error_message
        RETURN t.id as task_id
        """

        with self._session() as session:
            if session is None:
                logger.warning(f"Fallback mode: Background task failure simulated for {task_id}")
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
                    raise TaskNotFoundError(f"Task not found or not running: {task_id}")

                logger.warning(f"Background task failed: {task_id} - {error_message[:100]}")
                return True

            except Neo4jError as e:
                logger.error(f"Failed to mark background task as failed: {e}")
                raise

    def get_task(self, task_id: str) -> Optional[Dict]:
        """
        Get a background task by ID.

        Args:
            task_id: Task ID to retrieve

        Returns:
            Task dict if found, None otherwise
        """
        cypher = """
        MATCH (t:BackgroundTask {id: $task_id})
        RETURN t
        """

        with self._session() as session:
            if session is None:
                return None

            try:
                result = session.run(cypher, task_id=task_id)
                record = result.single()
                if record:
                    task_dict = dict(record["t"])
                    # Parse data and result back from strings if possible
                    for key in ["data", "result"]:
                        if task_dict.get(key):
                            try:
                                import ast
                                task_dict[key] = ast.literal_eval(task_dict[key])
                            except (ValueError, SyntaxError):
                                pass
                    return task_dict
                return None
            except Neo4jError as e:
                logger.error(f"Failed to get background task: {e}")
                raise

    def list_tasks(
        self,
        status: Optional[str] = None,
        task_type: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        List background tasks with optional filters.

        Args:
            status: Filter by status ('pending', 'running', 'completed', 'failed')
            task_type: Filter by task type
            limit: Maximum number of tasks to return

        Returns:
            List of task dicts
        """
        conditions = []
        params = {"limit": limit}

        if status is not None:
            conditions.append("t.status = $status")
            params["status"] = status

        if task_type is not None:
            conditions.append("t.task_type = $task_type")
            params["task_type"] = task_type

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        cypher = f"""
        MATCH (t:BackgroundTask)
        {where_clause}
        RETURN t
        ORDER BY t.created_at DESC
        LIMIT $limit
        """

        with self._session() as session:
            if session is None:
                return []

            try:
                result = session.run(cypher, **params)
                tasks = []
                for record in result:
                    task_dict = dict(record["t"])
                    # Parse data and result back from strings if possible
                    for key in ["data", "result"]:
                        if task_dict.get(key):
                            try:
                                import ast
                                task_dict[key] = ast.literal_eval(task_dict[key])
                            except (ValueError, SyntaxError):
                                pass
                    tasks.append(task_dict)
                return tasks
            except Neo4jError as e:
                logger.error(f"Failed to list background tasks: {e}")
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
            except Neo4jError as e:
                logger.error(f"Failed to count unconsolidated reflections: {e}")
                return 0

    def get_unconsolidated_reflections(self, limit: int = 100) -> List[Dict]:
        """
        Get unconsolidated reflections.

        Args:
            limit: Maximum number of reflections to return

        Returns:
            List of reflection dicts
        """
        cypher = """
        MATCH (r:Reflection {consolidated: false})
        RETURN r
        ORDER BY r.created_at ASC
        LIMIT $limit
        """

        with self._session() as session:
            if session is None:
                return []

            try:
                result = session.run(cypher, limit=limit)
                return [dict(record["r"]) for record in result]
            except Neo4jError as e:
                logger.error(f"Failed to get unconsolidated reflections: {e}")
                return []

    def consolidate_reflections(self) -> Dict:
        """
        Consolidate unconsolidated reflections into learnings.

        Triggered when 5+ unconsolidated reflections exist. Groups reflections
        by agent and topic, extracts common patterns, and creates consolidated
        learning nodes.

        Returns:
            Summary dict with consolidation results
        """
        # Check if threshold is met
        count = self.count_unconsolidated_reflections()
        if count < self.reflection_threshold:
            return {
                "consolidated": False,
                "reason": f"Threshold not met ({count}/{self.reflection_threshold})",
                "learnings_created": 0,
                "reflections_processed": 0
            }

        # Get unconsolidated reflections
        reflections = self.get_unconsolidated_reflections(limit=100)

        if not reflections:
            return {
                "consolidated": False,
                "reason": "No unconsolidated reflections found",
                "learnings_created": 0,
                "reflections_processed": 0
            }

        # Group reflections by agent and topic
        grouped: Dict[str, Dict[str, List[Dict]]] = {}
        for reflection in reflections:
            agent = reflection.get("agent", "unknown")
            topic = reflection.get("topic", "general")

            if agent not in grouped:
                grouped[agent] = {}
            if topic not in grouped[agent]:
                grouped[agent][topic] = []

            grouped[agent][topic].append(reflection)

        # Create consolidated learnings
        learnings_created = 0
        consolidated_reflection_ids = []

        created_at = self._now()

        with self._session() as session:
            if session is None:
                logger.warning("Fallback mode: Reflection consolidation simulated")
                return {
                    "consolidated": True,
                    "reason": "Fallback mode - simulation",
                    "learnings_created": len(reflections) // 3,
                    "reflections_processed": len(reflections)
                }

            try:
                for agent, topics in grouped.items():
                    for topic, topic_reflections in topics.items():
                        if len(topic_reflections) < 2:
                            # Skip single reflections
                            continue

                        # Extract common patterns/themes
                        themes = self._extract_themes(topic_reflections)

                        # Create learning node
                        learning_id = self._generate_id()
                        content_summary = f"Consolidated {len(topic_reflections)} reflections on {topic}"

                        cypher = """
                        CREATE (l:Learning {
                            id: $learning_id,
                            agent: $agent,
                            topic: $topic,
                            content: $content,
                            themes: $themes,
                            reflection_count: $reflection_count,
                            created_at: $created_at,
                            source_reflections: $reflection_ids
                        })
                        RETURN l.id as learning_id
                        """

                        result = session.run(
                            cypher,
                            learning_id=learning_id,
                            agent=agent,
                            topic=topic,
                            content=content_summary,
                            themes=str(themes),
                            reflection_count=len(topic_reflections),
                            created_at=created_at,
                            reflection_ids=str([r["id"] for r in topic_reflections])
                        )

                        record = result.single()
                        if record:
                            learnings_created += 1
                            consolidated_reflection_ids.extend([r["id"] for r in topic_reflections])

                # Mark reflections as consolidated
                if consolidated_reflection_ids:
                    self._mark_reflections_consolidated(consolidated_reflection_ids)

                logger.info(
                    f"Reflection consolidation complete: {learnings_created} learnings created "
                    f"from {len(consolidated_reflection_ids)} reflections"
                )

                return {
                    "consolidated": True,
                    "learnings_created": learnings_created,
                    "reflections_processed": len(consolidated_reflection_ids),
                    "agents": list(grouped.keys()),
                    "topics": list({t for topics in grouped.values() for t in topics.keys()})
                }

            except Neo4jError as e:
                logger.error(f"Failed to consolidate reflections: {e}")
                raise

    def _extract_themes(self, reflections: List[Dict]) -> List[str]:
        """
        Extract common themes from a list of reflections.

        Args:
            reflections: List of reflection dicts

        Returns:
            List of theme strings
        """
        # Simple theme extraction based on content analysis
        themes = set()

        for reflection in reflections:
            content = reflection.get("content", "")
            # Extract keywords (simple approach - words longer than 5 chars)
            words = content.lower().split()
            for word in words:
                clean_word = ''.join(c for c in word if c.isalnum())
                if len(clean_word) > 5:
                    themes.add(clean_word)

        # Return top themes (limit to 10)
        return list(themes)[:10]

    def _mark_reflections_consolidated(self, reflection_ids: List[str]) -> None:
        """
        Mark reflections as consolidated.

        Args:
            reflection_ids: List of reflection IDs to mark
        """
        cypher = """
        MATCH (r:Reflection)
        WHERE r.id IN $reflection_ids
        SET r.consolidated = true,
            r.consolidated_at = $consolidated_at
        """

        with self._session() as session:
            if session is None:
                return

            try:
                session.run(
                    cypher,
                    reflection_ids=reflection_ids,
                    consolidated_at=self._now()
                )
            except Neo4jError as e:
                logger.error(f"Failed to mark reflections as consolidated: {e}")

    def clean_orphaned_nodes(self) -> Dict:
        """
        Clean orphaned nodes from the knowledge graph.

        Identifies and removes nodes that are no longer connected to
        any active agents or tasks.

        Returns:
            Summary dict with cleanup results
        """
        results = {
            "orphaned_tasks": 0,
            "orphaned_notifications": 0,
            "orphaned_reflections": 0,
            "orphaned_learnings": 0,
            "total_cleaned": 0
        }

        with self._session() as session:
            if session is None:
                logger.warning("Fallback mode: Orphaned node cleanup simulated")
                return results

            try:
                # Find orphaned tasks (old pending tasks with no agent)
                cutoff_date = self._now() - timedelta(days=7)

                cypher_tasks = """
                MATCH (t:Task {status: 'pending'})
                WHERE t.created_at < $cutoff_date
                AND t.assigned_to IS NULL
                WITH t LIMIT 100
                DELETE t
                RETURN count(t) as deleted
                """

                result = session.run(cypher_tasks, cutoff_date=cutoff_date)
                record = result.single()
                if record:
                    results["orphaned_tasks"] = record["deleted"]

                # Find orphaned notifications (old read notifications)
                cypher_notifications = """
                MATCH (n:Notification {read: true})
                WHERE n.created_at < $cutoff_date
                WITH n LIMIT 100
                DELETE n
                RETURN count(n) as deleted
                """

                result = session.run(cypher_notifications, cutoff_date=cutoff_date)
                record = result.single()
                if record:
                    results["orphaned_notifications"] = record["deleted"]

                # Find orphaned reflections (consolidated and old)
                cypher_reflections = """
                MATCH (r:Reflection {consolidated: true})
                WHERE r.consolidated_at < $cutoff_date
                WITH r LIMIT 100
                DELETE r
                RETURN count(r) as deleted
                """

                result = session.run(cypher_reflections, cutoff_date=cutoff_date)
                record = result.single()
                if record:
                    results["orphaned_reflections"] = record["deleted"]

                # Find orphaned learnings (not connected to any agent)
                cypher_learnings = """
                MATCH (l:Learning)
                WHERE l.created_at < $cutoff_date
                AND NOT EXISTS {
                    MATCH (a:Agent)-[:HAS_LEARNING]->(l)
                }
                WITH l LIMIT 100
                DELETE l
                RETURN count(l) as deleted
                """

                result = session.run(cypher_learnings, cutoff_date=cutoff_date)
                record = result.single()
                if record:
                    results["orphaned_learnings"] = record["deleted"]

                results["total_cleaned"] = (
                    results["orphaned_tasks"] +
                    results["orphaned_notifications"] +
                    results["orphaned_reflections"] +
                    results["orphaned_learnings"]
                )

                logger.info(
                    f"Orphaned node cleanup complete: {results['total_cleaned']} nodes removed"
                )

                return results

            except Neo4jError as e:
                logger.error(f"Failed to clean orphaned nodes: {e}")
                raise

    def run_synthesis_cycle(self) -> List[Dict]:
        """
        Run one cycle of background tasks.

        Processes pending background tasks that can be executed.

        Returns:
            List of task results
        """
        results = []

        # Get next pending task
        task = self.get_next_task()

        if not task:
            logger.debug("No pending background tasks")
            return results

        task_id = task["id"]
        task_type = task["task_type"]

        try:
            # Mark task as running
            self.start_task(task_id)

            # Execute task based on type
            if task_type == "reflection_consolidation":
                result = self.consolidate_reflections()
            elif task_type == "graph_maintenance":
                result = self.clean_orphaned_nodes()
            elif task_type == "knowledge_synthesis":
                # Knowledge synthesis would be implemented here
                result = {"synthesized": True, "note": "Knowledge synthesis placeholder"}
            else:
                result = {"executed": True, "note": f"Task type {task_type} executed"}

            # Mark task as completed
            self.complete_task(task_id, result)

            results.append({
                "task_id": task_id,
                "task_type": task_type,
                "status": "completed",
                "result": result
            })

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Background task failed: {task_id} - {error_msg}")
            self.fail_task(task_id, error_msg)

            results.append({
                "task_id": task_id,
                "task_type": task_type,
                "status": "failed",
                "error": error_msg
            })

        return results

    def check_and_queue_consolidation(self) -> Optional[str]:
        """
        Check if reflection consolidation should be triggered and queue if needed.

        Returns:
            Task ID if queued, None otherwise
        """
        count = self.count_unconsolidated_reflections()

        if count >= self.reflection_threshold:
            # Check if there's already a pending consolidation task
            pending = self.list_tasks(status="pending", task_type="reflection_consolidation")

            if not pending:
                # Queue consolidation task
                task_id = self.queue_task(
                    task_type="reflection_consolidation",
                    priority="normal",
                    data={"reflection_count": count, "threshold": self.reflection_threshold}
                )
                logger.info(f"Queued reflection consolidation task: {task_id} ({count} reflections)")
                return task_id

        return None

    def create_indexes(self) -> List[str]:
        """
        Create recommended indexes for background task tracking.

        Returns:
            List of created index names
        """
        indexes = [
            ("CREATE INDEX backgroundtask_id_idx IF NOT EXISTS FOR (t:BackgroundTask) ON (t.id)", "backgroundtask_id_idx"),
            ("CREATE INDEX backgroundtask_status_idx IF NOT EXISTS FOR (t:BackgroundTask) ON (t.status)", "backgroundtask_status_idx"),
            ("CREATE INDEX backgroundtask_type_idx IF NOT EXISTS FOR (t:BackgroundTask) ON (t.task_type)", "backgroundtask_type_idx"),
            ("CREATE INDEX backgroundtask_priority_idx IF NOT EXISTS FOR (t:BackgroundTask) ON (t.priority)", "backgroundtask_priority_idx"),
            ("CREATE INDEX backgroundtask_created_idx IF NOT EXISTS FOR (t:BackgroundTask) ON (t.created_at)", "backgroundtask_created_idx"),
            ("CREATE INDEX reflection_consolidated_idx IF NOT EXISTS FOR (r:Reflection) ON (r.consolidated)", "reflection_consolidated_idx"),
            ("CREATE INDEX learning_agent_idx IF NOT EXISTS FOR (l:Learning) ON (l.agent)", "learning_agent_idx"),
            ("CREATE INDEX learning_topic_idx IF NOT EXISTS FOR (l:Learning) ON (l.topic)", "learning_topic_idx"),
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


# =============================================================================
# Convenience Functions
# =============================================================================

def create_background_task_manager(
    memory: Any,
    reflection_threshold: int = 5,
    idle_threshold_seconds: int = 300
) -> BackgroundTaskManager:
    """
    Create a BackgroundTaskManager instance.

    Args:
        memory: OperationalMemory instance
        reflection_threshold: Number of reflections to trigger consolidation
        idle_threshold_seconds: Default idle threshold

    Returns:
        BackgroundTaskManager instance
    """
    return BackgroundTaskManager(
        memory=memory,
        reflection_threshold=reflection_threshold,
        idle_threshold_seconds=idle_threshold_seconds
    )


def run_background_synthesis(
    manager: BackgroundTaskManager,
    agent: Optional[str] = None
) -> List[Dict]:
    """
    Run background synthesis cycle.

    Args:
        manager: BackgroundTaskManager instance
        agent: Optional agent to check for idle status

    Returns:
        List of task results
    """
    # Check if agent is idle (if specified)
    if agent and not manager.is_agent_idle(agent):
        logger.debug(f"Agent {agent} is not idle, skipping background synthesis")
        return []

    # Check and queue consolidation if needed
    manager.check_and_queue_consolidation()

    # Run synthesis cycle
    return manager.run_synthesis_cycle()


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    # Configure logging for example
    logging.basicConfig(level=logging.INFO)

    # Example usage (requires OperationalMemory)
    print("BackgroundTaskManager - Example Usage")
    print("=" * 50)

    print("""
    from openclaw_memory import OperationalMemory
    from tools.background_synthesis import BackgroundTaskManager

    # Initialize
    with OperationalMemory(
        uri="bolt://localhost:7687",
        username="neo4j",
        password="password"
    ) as memory:

        # Create manager
        manager = BackgroundTaskManager(
            memory=memory,
            reflection_threshold=5,
            idle_threshold_seconds=300
        )

        # Create indexes
        manager.create_indexes()

        # Check if agent is idle
        is_idle = manager.is_agent_idle("writer")
        print(f"Agent idle: {is_idle}")

        # Queue a background task
        task_id = manager.queue_task(
            task_type="graph_maintenance",
            priority="low"
        )

        # Check and queue consolidation if threshold met
        consolidation_task_id = manager.check_and_queue_consolidation()

        # Run synthesis cycle
        results = manager.run_synthesis_cycle()

        # Consolidate reflections manually
        summary = manager.consolidate_reflections()

        # Clean orphaned nodes
        cleanup_summary = manager.clean_orphaned_nodes()
    """)
