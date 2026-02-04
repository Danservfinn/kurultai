"""
Notion Integration Module

Bidirectional Notion integration with Kublai review and checkpoint support.

This module provides:
- Polling for new tasks created in Notion
- Kublai review protocol for Notion tasks
- Bidirectional status synchronization
- Checkpoint system for interrupted tasks
- Error routing and failure tracking
- Agent reliability metrics

Environment Variables:
    NOTION_TOKEN: Notion API integration token
    NOTION_TASK_DATABASE_ID: Notion database ID for tasks
    NOTION_POLL_INTERVAL_SECONDS: Polling interval (default: 60)
"""

import asyncio
import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse
import urllib.request

# Configure logging
logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

KUBLAI_AGENT_ID = "main"
OGEDEI_AGENT_ID = "ops"

# Notion status to Neo4j status mapping
STATUS_MAPPING: Dict[str, str] = {
    'Backlog': 'suspended',
    'Pending Review': 'pending_review',
    'To Do': 'pending',
    'In Progress': 'in_progress',
    'Review': 'review',
    'Done': 'completed',
    'Blocked': 'blocked'
}

# Neo4j status to Notion status mapping (reverse of STATUS_MAPPING)
NEO4J_TO_NOTION_STATUS: Dict[str, str] = {
    'suspended': 'Backlog',
    'pending_review': 'Pending Review',
    'pending': 'To Do',
    'in_progress': 'In Progress',
    'review': 'Review',
    'completed': 'Done',
    'failed': 'Blocked',
    'blocked': 'Blocked'
}

# Priority mapping
PRIORITY_MAPPING: Dict[str, str] = {
    'P0': 'urgent',
    'P1': 'high',
    'P2': 'medium',
    'P3': 'low'
}

# Reverse priority mapping
NOTION_TO_NEO4J_PRIORITY: Dict[str, str] = {
    'P0': 'critical',
    'P1': 'high',
    'P2': 'normal',
    'P3': 'low'
}

# Error classification with confidence scores and recommended agents
ERROR_CLASSIFICATION: Dict[str, Tuple[str, float]] = {
    'api_error': ('developer', 0.85),
    'syntax_error': ('developer', 0.95),
    'import_error': ('developer', 0.90),
    'type_error': ('developer', 0.85),
    'performance_issue': ('analyst', 0.85),
    'memory_leak': ('analyst', 0.90),
    'race_condition': ('analyst', 0.90),
    'deadlock': ('analyst', 0.90),
    'insufficient_information': ('researcher', 0.80),
    'missing_context': ('researcher', 0.80),
    'tone_issue': ('writer', 0.75),
    'grammar_error': ('writer', 0.70),
    'sync_failure': ('ops', 0.90),
    'connection_error': ('ops', 0.85),
    'timeout_error': ('ops', 0.80),
}

# Keywords for error classification
ERROR_KEYWORDS: Dict[str, List[str]] = {
    'api_error': ['api', 'endpoint', 'http', 'request failed', 'response error'],
    'syntax_error': ['syntax', 'parse', 'invalid syntax', 'unexpected token'],
    'import_error': ['import', 'module', 'no module named', 'cannot import'],
    'type_error': ['type', 'typeerror', 'has no attribute'],
    'performance_issue': ['slow', 'performance', 'latency', 'optimization'],
    'memory_leak': ['memory', 'leak', 'oom', 'out of memory'],
    'race_condition': ['race', 'concurrent', 'locking', 'synchronization'],
    'deadlock': ['deadlock', 'lock timeout', 'waiting forever'],
    'insufficient_information': ['missing', 'not enough', 'need more', 'unclear'],
    'tone_issue': ['tone', 'voice', 'inappropriate', 'unprofessional'],
    'grammar_error': ['grammar', 'spelling', 'typo', 'wording'],
    'sync_failure': ['sync', 'synchronization', 'out of sync', 'conflict'],
    'connection_error': ['connection', 'network', 'unreachable', 'refused'],
    'timeout_error': ['timeout', 'timed out', 'too long'],
}

DEFAULT_POLL_INTERVAL = 60
CHECKPOINT_EXPIRY_HOURS = 24


# =============================================================================
# Exceptions
# =============================================================================

class NotionIntegrationError(Exception):
    """Base exception for Notion integration errors."""
    pass


class NotionAPIError(NotionIntegrationError):
    """Exception raised when Notion API returns an error."""
    pass


class NotionAuthError(NotionAPIError):
    """Exception raised when Notion authentication fails."""
    pass


class NotionRateLimitError(NotionAPIError):
    """Exception raised when Notion rate limit is hit."""
    pass


class NotionConfigError(NotionIntegrationError):
    """Exception raised when configuration is invalid."""
    pass


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class NotionTask:
    """Represents a task from Notion."""
    id: str
    title: str
    status: str
    priority: str
    neo4j_task_id: Optional[str] = None
    agent: Optional[str] = None
    requester: Optional[str] = None
    created_from: str = "Notion"
    created_at: Optional[datetime] = None
    url: Optional[str] = None
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Checkpoint:
    """Represents a saved agent state for interrupted tasks."""
    id: str
    task_id: str
    agent: str
    created_at: datetime
    context_json: str
    progress_percent: float
    expires_at: datetime
    notes: Optional[str] = None


@dataclass
class AgentFailure:
    """Represents a tracked agent failure."""
    id: str
    agent: str
    task_type: str
    error_type: str
    fix_successful: bool
    fix_agent: str
    created_at: datetime
    error_message: Optional[str] = None


@dataclass
class ErrorClassification:
    """Result of error classification."""
    error_type: str
    recommended_agent: str
    confidence: float
    reasoning: str


@dataclass
class TrainingRecommendation:
    """Recommendation for agent training."""
    agent: str
    error_type: str
    reason: str
    priority: str
    recent_failures: List[AgentFailure]


# =============================================================================
# Notion API Client
# =============================================================================

class NotionClient:
    """
    Low-level client for Notion API.

    Handles HTTP requests to Notion API with authentication,
    rate limiting, and error handling.
    """

    NOTION_API_BASE = "https://api.notion.com/v1"
    NOTION_VERSION = "2022-06-28"

    def __init__(
        self,
        api_key: Optional[str] = None,
        database_id: Optional[str] = None
    ):
        """
        Initialize Notion API client.

        Args:
            api_key: Notion API integration token (from NOTION_TOKEN env var)
            database_id: Notion database ID (from NOTION_TASK_DATABASE_ID env var)

        Raises:
            NotionConfigError: If configuration is invalid
        """
        self.api_key = api_key or os.getenv("NOTION_TOKEN")
        self.database_id = database_id or os.getenv("NOTION_TASK_DATABASE_ID")

        if not self.api_key:
            raise NotionConfigError(
                "Notion API key not provided. Set NOTION_TOKEN environment variable "
                "or pass api_key parameter."
            )

        if not self.database_id:
            raise NotionConfigError(
                "Notion database ID not provided. Set NOTION_TASK_DATABASE_ID "
                "environment variable or pass database_id parameter."
            )

        self._headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Notion-Version": self.NOTION_VERSION
        }

        logger.info(f"Notion client initialized for database: {self.database_id[:8]}...")

    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None
    ) -> Dict:
        """
        Make HTTP request to Notion API.

        Args:
            method: HTTP method (GET, POST, PATCH, DELETE)
            endpoint: API endpoint path
            data: Request body for POST/PATCH

        Returns:
            Response JSON as dictionary

        Raises:
            NotionAPIError: If API returns an error
            NotionRateLimitError: If rate limit is hit
            NotionAuthError: If authentication fails
        """
        url = f"{self.NOTION_API_BASE}{endpoint}"
        request_body = json.dumps(data).encode("utf-8") if data else None

        req = urllib.request.Request(
            url,
            data=request_body,
            headers=self._headers,
            method=method
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                response_data = response.read().decode("utf-8")
                if response_data:
                    return json.loads(response_data)
                return {}

        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            logger.error(f"Notion API error: {e.code} - {error_body}")

            if e.code == 401:
                raise NotionAuthError("Invalid Notion API token")
            elif e.code == 429:
                retry_after = e.headers.get("Retry-After", "60")
                raise NotionRateLimitError(
                    f"Rate limited. Retry after {retry_after} seconds"
                )
            elif e.code >= 500:
                raise NotionAPIError(f"Notion server error: {e.code}")

            try:
                error_json = json.loads(error_body)
                message = error_json.get("message", str(e))
            except json.JSONDecodeError:
                message = str(e)

            raise NotionAPIError(f"Notion API error: {message}")

        except urllib.error.URLError as e:
            raise NotionAPIError(f"Network error: {e.reason}")

        except json.JSONDecodeError as e:
            raise NotionAPIError(f"Invalid JSON response: {e}")

    def query_database(
        self,
        filter: Optional[Dict] = None,
        sorts: Optional[List[Dict]] = None
    ) -> Dict:
        """
        Query Notion database.

        Args:
            filter: Notion filter object
            sorts: Notion sort objects

        Returns:
            Database query response with results array
        """
        endpoint = f"/databases/{self.database_id}/query"
        data: Dict[str, Any] = {}

        if filter:
            data["filter"] = filter
        if sorts:
            data["sorts"] = sorts

        return self._make_request("POST", endpoint, data)

    def get_page(self, page_id: str) -> Dict:
        """
        Get page details.

        Args:
            page_id: Notion page ID

        Returns:
            Page object with properties
        """
        endpoint = f"/pages/{page_id}"
        return self._make_request("GET", endpoint)

    def update_page(
        self,
        page_id: str,
        properties: Dict,
        archived: bool = False
    ) -> Dict:
        """
        Update page properties.

        Args:
            page_id: Notion page ID
            properties: Properties to update
            archived: Whether to archive the page

        Returns:
            Updated page object
        """
        endpoint = f"/pages/{page_id}"
        data = {"properties": properties}

        if archived:
            data["archived"] = True

        return self._make_request("PATCH", endpoint, data)

    def create_page(
        self,
        parent_id: str,
        properties: Dict,
        content: Optional[List[Dict]] = None
    ) -> Dict:
        """
        Create new page.

        Args:
            parent_id: Parent database or page ID
            properties: Page properties
            content: Block content for the page

        Returns:
            Created page object
        """
        endpoint = "/pages"
        data = {
            "parent": {"database_id": parent_id},
            "properties": properties
        }

        if content:
            data["children"] = content

        return self._make_request("POST", endpoint, data)

    def append_blocks(
        self,
        block_id: str,
        blocks: List[Dict]
    ) -> Dict:
        """
        Append blocks to a page.

        Args:
            block_id: Page or block ID
            blocks: List of block objects to append

        Returns:
            Response with created blocks
        """
        endpoint = f"/blocks/{block_id}/children"
        data = {"children": blocks}

        return self._make_request("PATCH", endpoint, data)


# =============================================================================
# Notion Integration
# =============================================================================

class NotionIntegration:
    """
    Bidirectional Notion integration with Kublai review and checkpoint support.

    This class manages the synchronization between Notion Kanban boards
    and Neo4j operational memory, including task polling, status sync,
    checkpoint management for interruptions, error classification and routing,
    and agent reliability tracking.

    Attributes:
        memory: OperationalMemory instance for Neo4j operations
        client: NotionClient for API interactions
        poll_interval: Seconds between polling cycles

    Example:
        >>> from openclaw_memory import OperationalMemory
        >>> memory = OperationalMemory(...)
        >>> integration = NotionIntegration(memory)
        >>> # Start background polling
        >>> integration.start_polling()
        >>> # Sync a task status
        >>> integration.sync_neo4j_status_to_notion(task_id)
    """

    def __init__(
        self,
        memory,
        api_key: Optional[str] = None,
        database_id: Optional[str] = None,
        poll_interval_seconds: Optional[int] = None
    ):
        """
        Initialize Notion integration.

        Args:
            memory: OperationalMemory instance
            api_key: Notion API key (defaults to NOTION_TOKEN env var)
            database_id: Notion database ID (defaults to NOTION_TASK_DATABASE_ID env var)
            poll_interval_seconds: Polling interval (defaults to NOTION_POLL_INTERVAL_SECONDS env var)
        """
        self.memory = memory
        self.client = NotionClient(api_key, database_id)

        poll_interval = poll_interval_seconds or os.getenv(
            "NOTION_POLL_INTERVAL_SECONDS",
            str(DEFAULT_POLL_INTERVAL)
        )
        self.poll_interval = int(poll_interval)

        # Polling state
        self._polling = False
        self._stop_polling = threading.Event()
        self._poll_thread: Optional[threading.Thread] = None
        self._last_poll_time: Optional[datetime] = None

        # Callbacks
        self._on_new_task_callback: Optional[Callable[[NotionTask], None]] = None
        self._on_status_change_callback: Optional[Callable[[str, str, str], None]] = None

        logger.info(
            f"NotionIntegration initialized with {self.poll_interval}s poll interval"
        )

    # =========================================================================
    # Task Polling
    # =========================================================================

    def poll_new_tasks(self) -> List[NotionTask]:
        """
        Detect tasks created in Notion without Neo4j Task ID.

        Returns:
            List of new NotionTask objects found during polling

        Example:
            >>> new_tasks = integration.poll_new_tasks()
            >>> for task in new_tasks:
            ...     print(f"New task: {task.title}")
        """
        logger.debug("Polling Notion for new tasks (no Neo4j Task ID)")

        try:
            # Query for tasks without Neo4j Task ID
            filter_obj = {
                "and": [
                    {
                        "property": "Neo4j Task ID",
                        "rich_text": {
                            "is_empty": True
                        }
                    },
                    {
                        "property": "Status",
                        "select": {
                            "does_not_equal": "Done"
                        }
                    }
                ]
            }

            response = self.client.query_database(filter=filter_obj)

            new_tasks = []
            for page_data in response.get("results", []):
                task = self._parse_notion_page(page_data)
                if task:
                    new_tasks.append(task)
                    logger.info(f"Found new Notion task: {task.title} ({task.id})")

            self._last_poll_time = datetime.now(timezone.utc)

            return new_tasks

        except NotionRateLimitError:
            logger.warning("Rate limited while polling for new tasks")
            return []
        except NotionAPIError as e:
            logger.error(f"API error while polling for new tasks: {e}")
            return []

    def poll_status_changes(self) -> List[Tuple[NotionTask, str, str]]:
        """
        Detect tasks that have changed status in Notion.

        Returns:
            List of tuples (task, old_status, new_status)

        Example:
            >>> changes = integration.poll_status_changes()
            >>> for task, old_status, new_status in changes:
            ...     print(f"{task.title}: {old_status} -> {new_status}")
        """
        logger.debug("Polling Notion for status changes")

        changes = []

        try:
            # Get all active tasks with Neo4j IDs
            filter_obj = {
                "and": [
                    {
                        "property": "Neo4j Task ID",
                        "rich_text": {
                            "is_not_empty": True
                        }
                    },
                    {
                        "property": "Status",
                        "select": {
                            "does_not_equal": "Done"
                        }
                    }
                ]
            }

            response = self.client.query_database(filter=filter_obj)

            for page_data in response.get("results", []):
                task = self._parse_notion_page(page_data)
                if task and task.neo4j_task_id:
                    # Get the Neo4j task status
                    neo4j_task = self.memory.get_task(task.neo4j_task_id)
                    if neo4j_task:
                        neo4j_status = neo4j_task.get("status")
                        expected_notion = NEO4J_TO_NOTION_STATUS.get(
                            neo4j_status,
                            task.status
                        )

                        if task.status != expected_notion:
                            changes.append((task, expected_notion, task.status))
                            logger.info(
                                f"Status change detected: {task.title} "
                                f"{expected_notion} -> {task.status}"
                            )

        except NotionAPIError as e:
            logger.error(f"API error while polling for status changes: {e}")

        return changes

    # =========================================================================
    # Task Creation from Notion
    # =========================================================================

    def create_neo4j_task_from_notion(
        self,
        notion_task: NotionTask,
        delegated_by: str = KUBLAI_AGENT_ID
    ) -> Optional[str]:
        """
        Create draft Neo4j task from Notion task.

        Args:
            notion_task: NotionTask object
            delegated_by: Agent creating the task (default: Kublai)

        Returns:
            Neo4j task ID if successful, None otherwise

        Example:
            >>> task_id = integration.create_neo4j_task_from_notion(notion_task)
            >>> if task_id:
            ...     print(f"Created task: {task_id}")
        """
        logger.info(f"Creating Neo4j task from Notion: {notion_task.title}")

        try:
            # Map Notion priority to Neo4j priority
            priority = NOTION_TO_NEO4J_PRIORITY.get(
                notion_task.priority,
                "normal"
            )

            # Determine assigned agent
            assigned_to = notion_task.agent if notion_task.agent else "any"

            # Create the task
            task_id = self.memory.create_task(
                task_type="notion_task",
                description=notion_task.title,
                delegated_by=delegated_by,
                assigned_to=assigned_to,
                priority=priority,
                notion_page_id=notion_task.id,
                notion_url=notion_task.url,
                requester=notion_task.requester or "Notion"
            )

            # Update Notion with Neo4j Task ID
            self.update_task_neo4j_id(notion_task.id, task_id)

            # Create link in Neo4j
            self._create_notion_task_link(task_id, notion_task)

            logger.info(
                f"Created Neo4j task {task_id} from Notion task {notion_task.id}"
            )

            # Notify callback if registered
            if self._on_new_task_callback:
                try:
                    self._on_new_task_callback(notion_task)
                except Exception as e:
                    logger.error(f"Error in new task callback: {e}")

            return task_id

        except Exception as e:
            logger.error(f"Failed to create Neo4j task from Notion: {e}")
            return None

    def _create_notion_task_link(
        self,
        neo4j_task_id: str,
        notion_task: NotionTask
    ) -> None:
        """
        Create NotionTask node in Neo4j linked to Task.

        Args:
            neo4j_task_id: Neo4j task ID
            notion_task: NotionTask object
        """
        query = """
        MERGE (t:Task {id: $neo4j_task_id})
        MERGE (nt:NotionTask {
            notion_page_id: $notion_page_id,
            neo4j_task_id: $neo4j_task_id
        })
        ON CREATE SET
            nt.id: $notion_task_id,
            nt.title: $title,
            nt.status: $status,
            nt.priority: $priority,
            nt.agent: $agent,
            nt.requester: $requester,
            nt.created_from: $created_from,
            nt.url: $url,
            nt.created_at: $created_at,
            nt.synced_at: $synced_at
        MERGE (t)-[r:LINKED_TO]->(nt)
        """

        with self.memory._session() as session:
            if session is None:
                logger.warning("Fallback mode: NotionTask link not created")
                return

            try:
                session.run(
                    query,
                    neo4j_task_id=neo4j_task_id,
                    notion_page_id=notion_task.id,
                    notion_task_id=str(self.memory._generate_id()),
                    title=notion_task.title,
                    status=notion_task.status,
                    priority=notion_task.priority,
                    agent=notion_task.agent,
                    requester=notion_task.requester,
                    created_from=notion_task.created_from,
                    url=notion_task.url,
                    created_at=notion_task.created_at or self.memory._now(),
                    synced_at=self.memory._now()
                )
                logger.debug(f"Created NotionTask link for {neo4j_task_id}")

            except Exception as e:
                logger.error(f"Failed to create NotionTask link: {e}")

    # =========================================================================
    # Status Synchronization
    # =========================================================================

    def update_notion_task_status(
        self,
        page_id: str,
        status: str
    ) -> bool:
        """
        Update Notion task status.

        Args:
            page_id: Notion page ID
            status: New status value

        Returns:
            True if successful

        Example:
            >>> success = integration.update_notion_task_status(
            ...     "page-123", "In Progress"
            ... )
        """
        logger.debug(f"Updating Notion task {page_id} to status: {status}")

        try:
            properties = {
                "Status": {
                    "select": {
                        "name": status
                    }
                }
            }

            self.client.update_page(page_id, properties)
            logger.info(f"Updated Notion task {page_id} to {status}")
            return True

        except NotionAPIError as e:
            logger.error(f"Failed to update Notion status: {e}")
            return False

    def sync_neo4j_status_to_notion(self, task_id: str) -> bool:
        """
        Sync Neo4j task status back to Notion.

        Args:
            task_id: Neo4j task ID

        Returns:
            True if successful

        Example:
            >>> success = integration.sync_neo4j_status_to_notion("task-123")
        """
        logger.debug(f"Syncing Neo4j task {task_id} status to Notion")

        try:
            # Get Neo4j task
            task = self.memory.get_task(task_id)
            if not task:
                logger.warning(f"Task not found: {task_id}")
                return False

            # Get linked Notion task
            notion_page_id = self._get_notion_page_id(task_id)
            if not notion_page_id:
                logger.debug(f"No Notion page linked to task {task_id}")
                return False

            # Map Neo4j status to Notion status
            neo4j_status = task.get("status")
            notion_status = NEO4J_TO_NOTION_STATUS.get(neo4j_status)

            if not notion_status:
                logger.warning(f"No Notion status mapping for: {neo4j_status}")
                return False

            # Update Notion
            return self.update_notion_task_status(notion_page_id, notion_status)

        except Exception as e:
            logger.error(f"Failed to sync status to Notion: {e}")
            return False

    def _get_notion_page_id(self, task_id: str) -> Optional[str]:
        """
        Get Notion page ID linked to Neo4j task.

        Args:
            task_id: Neo4j task ID

        Returns:
            Notion page ID if found
        """
        query = """
        MATCH (t:Task {id: $task_id})-[:LINKED_TO]->(nt:NotionTask)
        RETURN nt.notion_page_id as page_id
        """

        with self.memory._session() as session:
            if session is None:
                return None

            try:
                result = session.run(query, task_id=task_id)
                record = result.single()
                return record["page_id"] if record else None

            except Exception as e:
                logger.error(f"Failed to get Notion page ID: {e}")
                return None

    def handle_column_change(
        self,
        notion_task: NotionTask,
        old_status: str,
        new_status: str
    ) -> Dict[str, Any]:
        """
        Handle user moving cards in Notion.

        Args:
            notion_task: Task that was moved
            old_status: Previous status
            new_status: New status

        Returns:
            Result dict with action taken and any checkpoint info

        Example:
            >>> result = integration.handle_column_change(task, "To Do", "In Progress")
            >>> print(f"Action: {result['action']}")
        """
        logger.info(
            f"Column change: {notion_task.title} {old_status} -> {new_status}"
        )

        result = {
            "action": "none",
            "checkpoint": None,
            "message": ""
        }

        if not notion_task.neo4j_task_id:
            result["message"] = "No Neo4j task linked"
            return result

        try:
            # Case: Interrupt active work
            if old_status == "In Progress" and new_status in [
                "Backlog", "To Do", "Blocked"
            ]:
                checkpoint = self.create_checkpoint(
                    agent=self._get_task_claimer(notion_task.neo4j_task_id),
                    task_id=notion_task.neo4j_task_id
                )
                result["action"] = "interrupted"
                result["checkpoint"] = checkpoint
                result["message"] = f"Paused task - checkpoint saved"

                # Update Neo4j status
                neo4j_status = STATUS_MAPPING.get(new_status, "suspended")
                self._update_neo4j_task_status(
                    notion_task.neo4j_task_id,
                    neo4j_status
                )

            # Case: Resume from checkpoint
            elif old_status in ["Backlog", "To Do"] and new_status == "In Progress":
                checkpoint = self.get_latest_checkpoint(notion_task.neo4j_task_id)
                result["action"] = "resumed"
                result["checkpoint"] = checkpoint
                result["message"] = (
                    f"Resumed task" +
                    (f" from checkpoint" if checkpoint else "")
                )

                # Update Neo4j status
                self._update_neo4j_task_status(
                    notion_task.neo4j_task_id,
                    "in_progress"
                )

            # Case: Task completed
            elif new_status in ["Done", "Review"]:
                result["action"] = "completed"
                result["message"] = f"Task marked as {new_status}"

                # Update Neo4j status
                neo4j_status = STATUS_MAPPING.get(new_status, "completed")
                self._update_neo4j_task_status(
                    notion_task.neo4j_task_id,
                    neo4j_status
                )

            # Notify callback if registered
            if self._on_status_change_callback:
                try:
                    self._on_status_change_callback(
                        notion_task.neo4j_task_id,
                        old_status,
                        new_status
                    )
                except Exception as e:
                    logger.error(f"Error in status change callback: {e}")

        except Exception as e:
            logger.error(f"Error handling column change: {e}")
            result["message"] = f"Error: {e}"

        return result

    def _get_task_claimer(self, task_id: str) -> Optional[str]:
        """Get agent that claimed a task."""
        task = self.memory.get_task(task_id)
        return task.get("claimed_by") if task else None

    def _update_neo4j_task_status(self, task_id: str, status: str) -> bool:
        """Update Neo4j task status."""
        query = """
        MATCH (t:Task {id: $task_id})
        SET t.status = $status
        RETURN t.id as id
        """

        with self.memory._session() as session:
            if session is None:
                return False

            try:
                session.run(query, task_id=task_id, status=status)
                logger.debug(f"Updated Neo4j task {task_id} to {status}")
                return True

            except Exception as e:
                logger.error(f"Failed to update Neo4j task status: {e}")
                return False

    def update_task_neo4j_id(
        self,
        page_id: str,
        neo4j_task_id: str
    ) -> bool:
        """
        Update Notion task with Neo4j Task ID.

        Args:
            page_id: Notion page ID
            neo4j_task_id: Neo4j task ID to write to the task

        Returns:
            True if successful
        """
        try:
            # Get current page to preserve other properties
            page = self.client.get_page(page_id)

            # Update Neo4j Task ID field
            current_properties = page.get("properties", {})
            current_text = current_properties.get("Neo4j Task ID", {})
            current_rich_text = current_text.get("rich_text", [])

            properties = {
                "Neo4j Task ID": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": neo4j_task_id
                            }
                        }
                    ]
                }
            }

            self.client.update_page(page_id, properties)
            logger.debug(f"Updated Notion task {page_id} with Neo4j ID: {neo4j_task_id}")
            return True

        except NotionAPIError as e:
            logger.error(f"Failed to update Notion with Neo4j ID: {e}")
            return False

    # =========================================================================
    # Checkpoint System
    # =========================================================================

    def create_checkpoint(
        self,
        agent: str,
        task_id: str,
        context: Optional[Dict] = None,
        progress_percent: float = 0.0,
        notes: Optional[str] = None
    ) -> Optional[Checkpoint]:
        """
        Save agent state before interruption.

        Args:
            agent: Agent ID
            task_id: Neo4j task ID
            context: Agent context to save
            progress_percent: Progress percentage (0-100)
            notes: Optional notes about the checkpoint

        Returns:
            Checkpoint object if successful

        Example:
            >>> checkpoint = integration.create_checkpoint(
            ...     agent="developer",
            ...     task_id="task-123",
            ...     context={"file": "main.py", "line": 42},
            ...     progress_percent=50.0
            ... )
        """
        logger.info(f"Creating checkpoint for agent {agent}, task {task_id}")

        checkpoint_id = str(self.memory._generate_id())
        now = self.memory._now()
        expires_at = now + timedelta(hours=CHECKPOINT_EXPIRY_HOURS)

        context_json = json.dumps(context or {})

        query = """
        CREATE (c:Checkpoint {
            id: $id,
            task_id: $task_id,
            agent: $agent,
            created_at: $created_at,
            context_json: $context_json,
            progress_percent: $progress_percent,
            expires_at: $expires_at,
            notes: $notes
        })
        RETURN c
        """

        with self.memory._session() as session:
            if session is None:
                logger.warning("Fallback mode: Checkpoint not saved")
                return None

            try:
                result = session.run(
                    query,
                    id=checkpoint_id,
                    task_id=task_id,
                    agent=agent,
                    created_at=now,
                    context_json=context_json,
                    progress_percent=progress_percent,
                    expires_at=expires_at,
                    notes=notes
                )
                record = result.single()

                if record:
                    logger.info(f"Created checkpoint {checkpoint_id}")
                    return Checkpoint(
                        id=checkpoint_id,
                        task_id=task_id,
                        agent=agent,
                        created_at=now,
                        context_json=context_json,
                        progress_percent=progress_percent,
                        expires_at=expires_at,
                        notes=notes
                    )

            except Exception as e:
                logger.error(f"Failed to create checkpoint: {e}")

        return None

    def get_checkpoint(self, checkpoint_id: str) -> Optional[Checkpoint]:
        """
        Get checkpoint by ID.

        Args:
            checkpoint_id: Checkpoint ID

        Returns:
            Checkpoint object if found
        """
        query = """
        MATCH (c:Checkpoint {id: $id})
        RETURN c
        """

        with self.memory._session() as session:
            if session is None:
                return None

            try:
                result = session.run(query, id=checkpoint_id)
                record = result.single()

                if record:
                    node = dict(record["c"])
                    return Checkpoint(
                        id=node["id"],
                        task_id=node["task_id"],
                        agent=node["agent"],
                        created_at=node["created_at"],
                        context_json=node["context_json"],
                        progress_percent=node["progress_percent"],
                        expires_at=node["expires_at"],
                        notes=node.get("notes")
                    )

            except Exception as e:
                logger.error(f"Failed to get checkpoint: {e}")

        return None

    def get_latest_checkpoint(self, task_id: str) -> Optional[Checkpoint]:
        """
        Get latest checkpoint for a task.

        Args:
            task_id: Neo4j task ID

        Returns:
            Latest Checkpoint if found
        """
        query = """
        MATCH (c:Checkpoint {task_id: $task_id})
        WHERE c.expires_at > datetime()
        RETURN c
        ORDER BY c.created_at DESC
        LIMIT 1
        """

        with self.memory._session() as session:
            if session is None:
                return None

            try:
                result = session.run(query, task_id=task_id)
                record = result.single()

                if record:
                    node = dict(record["c"])
                    return Checkpoint(
                        id=node["id"],
                        task_id=node["task_id"],
                        agent=node["agent"],
                        created_at=node["created_at"],
                        context_json=node["context_json"],
                        progress_percent=node["progress_percent"],
                        expires_at=node["expires_at"],
                        notes=node.get("notes")
                    )

            except Exception as e:
                logger.error(f"Failed to get latest checkpoint: {e}")

        return None

    def load_checkpoint(self, checkpoint_id: str) -> Optional[Dict]:
        """
        Load checkpoint context.

        Args:
            checkpoint_id: Checkpoint ID

        Returns:
            Context dictionary if found
        """
        checkpoint = self.get_checkpoint(checkpoint_id)
        if checkpoint:
            try:
                return json.loads(checkpoint.context_json)
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON in checkpoint {checkpoint_id}")
                return None
        return None

    def cleanup_expired_checkpoints(self) -> int:
        """
        Remove expired checkpoints.

        Returns:
            Number of checkpoints removed
        """
        query = """
        MATCH (c:Checkpoint)
        WHERE c.expires_at < datetime()
        DELETE c
        RETURN count(c) as deleted_count
        """

        with self.memory._session() as session:
            if session is None:
                return 0

            try:
                result = session.run(query)
                record = result.single()
                count = record["deleted_count"] if record else 0
                logger.info(f"Cleaned up {count} expired checkpoints")
                return count

            except Exception as e:
                logger.error(f"Failed to cleanup checkpoints: {e}")

        return 0

    # =========================================================================
    # Error Classification and Routing
    # =========================================================================

    def classify_error(
        self,
        error_message: str,
        task_type: Optional[str] = None
    ) -> ErrorClassification:
        """
        Analyze error and determine best agent.

        Args:
            error_message: Error message to classify
            task_type: Optional task type context

        Returns:
            ErrorClassification with recommended agent

        Example:
            >>> result = integration.classify_error("TypeError: 'NoneType' object is not subscriptable")
            >>> print(f"Recommended agent: {result.recommended_agent}")
        """
        error_lower = error_message.lower()

        # Check for keyword matches
        best_match = None
        best_score = 0

        for error_type, keywords in ERROR_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw.lower() in error_lower)
            if score > best_score:
                best_score = score
                best_match = error_type

        # Get classification
        if best_match:
            agent, confidence = ERROR_CLASSIFICATION[best_match]
            reasoning = f"Matched error type '{best_match}' based on keywords"
        else:
            # Default to developer
            agent = "developer"
            confidence = 0.5
            reasoning = "No specific error type matched, defaulting to developer"

        # Adjust confidence based on task type
        if task_type:
            if task_type == "code_review" and agent == "developer":
                confidence = min(confidence + 0.1, 1.0)

        return ErrorClassification(
            error_type=best_match or "unknown",
            recommended_agent=agent,
            confidence=confidence,
            reasoning=reasoning
        )

    def route_error_task(
        self,
        task_id: str,
        error_message: str,
        original_agent: str
    ) -> Optional[str]:
        """
        Route failed task to appropriate agent based on error.

        Args:
            task_id: Failed task ID
            error_message: Error that occurred
            original_agent: Agent that originally failed

        Returns:
            New task ID if routed, None otherwise
        """
        classification = self.classify_error(error_message)

        logger.info(
            f"Routing task {task_id} from {original_agent} to "
            f"{classification.recommended_agent} (confidence: {classification.confidence})"
        )

        # Get original task
        original_task = self.memory.get_task(task_id)
        if not original_task:
            logger.error(f"Original task not found: {task_id}")
            return None

        # Create new task for recommended agent
        new_task_id = self.memory.create_task(
            task_type=f"error_fix_{classification.error_type}",
            description=f"Fix error in task {task_id}: {error_message}",
            delegated_by=KUBLAI_AGENT_ID,
            assigned_to=classification.recommended_agent,
            priority=original_task.get("priority", "normal"),
            original_task_id=task_id,
            error_type=classification.error_type,
            original_agent=original_agent
        )

        # Track the failure
        self.track_agent_failure(
            agent=original_agent,
            task_type=original_task.get("type", "unknown"),
            error_type=classification.error_type,
            fix_successful=False,
            fix_agent=classification.recommended_agent
        )

        return new_task_id

    # =========================================================================
    # Agent Failure Tracking
    # =========================================================================

    def track_agent_failure(
        self,
        agent: str,
        task_type: str,
        error_type: str,
        fix_successful: bool,
        fix_agent: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> bool:
        """
        Track agent failure for reliability metrics.

        Args:
            agent: Agent that failed
            task_type: Type of task being attempted
            error_type: Type of error that occurred
            fix_successful: Whether the fix was successful
            fix_agent: Agent that fixed the issue (if different)
            error_message: Optional error message

        Returns:
            True if recorded successfully

        Example:
            >>> success = integration.track_agent_failure(
            ...     agent="developer",
            ...     task_type="code_implement",
            ...     error_type="syntax_error",
            ...     fix_successful=True,
            ...     fix_agent="developer"
            ... )
        """
        failure_id = str(self.memory._generate_id())
        now = self.memory._now()

        query = """
        CREATE (f:AgentFailure {
            id: $id,
            agent: $agent,
            task_type: $task_type,
            error_type: $error_type,
            fix_successful: $fix_successful,
            fix_agent: $fix_agent,
            error_message: $error_message,
            created_at: $created_at
        })
        RETURN f.id as id
        """

        with self.memory._session() as session:
            if session is None:
                return False

            try:
                session.run(
                    query,
                    id=failure_id,
                    agent=agent,
                    task_type=task_type,
                    error_type=error_type,
                    fix_successful=fix_successful,
                    fix_agent=fix_agent or agent,
                    error_message=error_message,
                    created_at=now
                )

                # Update reliability stats
                self._update_reliability_stats(
                    agent, task_type, error_type, fix_successful
                )

                logger.debug(f"Tracked failure: {agent} on {task_type}")
                return True

            except Exception as e:
                logger.error(f"Failed to track agent failure: {e}")

        return False

    def _update_reliability_stats(
        self,
        agent: str,
        task_type: str,
        error_type: str,
        fix_successful: bool
    ) -> None:
        """
        Update agent reliability statistics.

        Args:
            agent: Agent ID
            task_type: Type of task
            error_type: Type of error
            fix_successful: Whether fix was successful
        """
        # Calculate new success rate
        query = """
        MATCH (f:AgentFailure {
            agent: $agent,
            task_type: $task_type,
            error_type: $error_type
        })
        WHERE f.created_at > datetime() - duration('P30D')
        WITH count(f) as total,
             sum(CASE WHEN f.fix_successful THEN 1 ELSE 0 END) as successful
        MERGE (r:AgentReliability {
            agent: $agent,
            task_type: $task_type
        })
        ON CREATE SET
            r.success_rate = 0.5,
            r.total_attempts = 1,
            r.recent_failures = 0
        SET r.success_rate = coalesce(successful * 1.0 / total, 0.5),
            r.total_attempts = coalesce(total, 1),
            r.recent_failures = total - coalesce(successful, 0)
        """

        with self.memory._session() as session:
            if session is None:
                return

            try:
                session.run(
                    query,
                    agent=agent,
                    task_type=task_type,
                    error_type=error_type
                )
            except Exception as e:
                logger.error(f"Failed to update reliability stats: {e}")

    def get_agent_reliability(
        self,
        agent: str,
        task_type: Optional[str] = None
    ) -> List[Dict]:
        """
        Get agent's success rate and reliability metrics.

        Args:
            agent: Agent ID
            task_type: Filter by task type (optional)

        Returns:
            List of reliability metrics

        Example:
            >>> metrics = integration.get_agent_reliability("developer")
            >>> for metric in metrics:
            ...     print(f"{metric['task_type']}: {metric['success_rate']:.1%}")
        """
        if task_type:
            query = """
            MATCH (r:AgentReliability {
                agent: $agent,
                task_type: $task_type
            })
            RETURN r
            """
            params = {"agent": agent, "task_type": task_type}
        else:
            query = """
            MATCH (r:AgentReliability {agent: $agent})
            RETURN r
            ORDER BY r.task_type
            """
            params = {"agent": agent}

        with self.memory._session() as session:
            if session is None:
                return []

            try:
                result = session.run(query, **params)
                return [dict(record["r"]) for record in result]

            except Exception as e:
                logger.error(f"Failed to get agent reliability: {e}")

        return []

    def detect_training_needs(
        self,
        agent: str,
        error_type: Optional[str] = None
    ) -> Optional[TrainingRecommendation]:
        """
        Identify when an agent needs training.

        Args:
            agent: Agent ID
            error_type: Specific error type to check (optional)

        Returns:
            TrainingRecommendation if training needed, None otherwise

        Example:
            >>> recommendation = integration.detect_training_needs("developer")
            >>> if recommendation:
            ...     print(f"Training needed: {recommendation.reason}")
        """
        # Get recent failures
        days_back = 30
        query = """
        MATCH (f:AgentFailure {agent: $agent})
        WHERE f.created_at > datetime() - duration('P{days}D')
        """

        if error_type:
            query += " AND f.error_type = $error_type "

        query += """
        WITH f.error_type as error_type,
             count(f) as failures,
             avg(CASE WHEN f.fix_successful THEN 1.0 ELSE 0.0 END) as fix_rate
        WHERE failures >= 3 AND fix_rate < 0.6
        RETURN error_type, failures, fix_rate
        ORDER BY failures DESC
        LIMIT 1
        """

        query = query.replace("{days}", str(days_back))

        with self.memory._session() as session:
            if session is None:
                return None

            try:
                params = {"agent": agent}
                if error_type:
                    params["error_type"] = error_type

                result = session.run(query, **params)
                record = result.single()

                if record:
                    # Get recent failures for this error type
                    failures_query = """
                    MATCH (f:AgentFailure {
                        agent: $agent,
                        error_type: $error_type
                    })
                    WHERE f.created_at > datetime() - duration('P30D')
                    RETURN f
                    ORDER BY f.created_at DESC
                    LIMIT 10
                    """

                    failures_result = session.run(
                        failures_query,
                        agent=agent,
                        error_type=record["error_type"]
                    )

                    failures = []
                    for f_record in failures_result:
                        node = dict(f_record["f"])
                        failures.append(AgentFailure(
                            id=node["id"],
                            agent=node["agent"],
                            task_type=node["task_type"],
                            error_type=node["error_type"],
                            fix_successful=node["fix_successful"],
                            fix_agent=node.get("fix_agent", node["agent"]),
                            created_at=node["created_at"],
                            error_message=node.get("error_message")
                        ))

                    return TrainingRecommendation(
                        agent=agent,
                        error_type=record["error_type"],
                        reason=f"Low success rate ({record['fix_rate']:.1%}) on {record['failures']} "
                               f"recent failures with {record['error_type']}",
                        priority="high" if record["failures"] >= 5 else "medium",
                        recent_failures=failures
                )

            except Exception as e:
                logger.error(f"Failed to detect training needs: {e}")

        return None

    # =========================================================================
    # Background Polling
    # =========================================================================

    def start_polling(self, callback: Optional[Callable[[NotionTask], None]] = None) -> None:
        """
        Start background polling for new Notion tasks.

        Args:
            callback: Optional callback function for new tasks

        Example:
            >>> def on_new_task(task):
            ...     print(f"New task: {task.title}")
            >>> integration.start_polling(callback=on_new_task)
        """
        if self._polling:
            logger.warning("Polling already active")
            return

        self._on_new_task_callback = callback
        self._polling = True
        self._stop_polling.clear()

        self._poll_thread = threading.Thread(
            target=self._poll_loop,
            daemon=True,
            name="NotionPoller"
        )
        self._poll_thread.start()

        logger.info(f"Started Notion polling (interval: {self.poll_interval}s)")

    def stop_polling(self) -> None:
        """
        Stop background polling.

        Example:
            >>> integration.stop_polling()
        """
        if not self._polling:
            return

        self._polling = False
        self._stop_polling.set()

        if self._poll_thread:
            self._poll_thread.join(timeout=5)
            self._poll_thread = None

        logger.info("Stopped Notion polling")

    def _poll_loop(self) -> None:
        """Background polling loop."""
        while self._polling and not self._stop_polling.is_set():
            try:
                # Poll for new tasks
                new_tasks = self.poll_new_tasks()

                for task in new_tasks:
                    # Create Neo4j task for each new Notion task
                    task_id = self.create_neo4j_task_from_notion(task)
                    if task_id:
                        logger.info(
                            f"Auto-created Neo4j task {task_id} from Notion"
                        )

                # Poll for status changes
                status_changes = self.poll_status_changes()

                for task, old_status, new_status in status_changes:
                    self.handle_column_change(task, old_status, new_status)

            except Exception as e:
                logger.error(f"Error in polling loop: {e}")

            # Wait for next interval
            self._stop_polling.wait(self.poll_interval)

    def is_polling(self) -> bool:
        """Check if polling is active."""
        return self._polling and self._poll_thread is not None

    def get_polling_status(self) -> Dict:
        """
        Get current polling status.

        Returns:
            Dict with polling status information
        """
        return {
            "active": self.is_polling(),
            "interval": self.poll_interval,
            "last_poll": self._last_poll_time.isoformat() if self._last_poll_time else None
        }

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def _parse_notion_page(self, page_data: Dict) -> Optional[NotionTask]:
        """
        Parse Notion page data into NotionTask object.

        Args:
            page_data: Raw Notion API page data

        Returns:
            NotionTask object if successful
        """
        try:
            props = page_data.get("properties", {})
            page_id = page_data.get("id", "")

            # Extract title
            title_prop = props.get("Name", {})
            title_parts = title_prop.get("title", [])
            title = title_parts[0]["text"]["content"] if title_parts else "Untitled"

            # Extract status
            status_prop = props.get("Status", {})
            status_select = status_prop.get("select", {})
            status = status_select.get("name", "Backlog")

            # Extract priority
            priority_prop = props.get("Priority", {})
            priority_select = priority_prop.get("select", {})
            priority = priority_select.get("name", "P2")

            # Extract agent
            agent_prop = props.get("Agent", {})
            agent_select = agent_prop.get("select", {})
            agent = agent_select.get("name")

            # Extract Neo4j Task ID
            neo4j_prop = props.get("Neo4j Task ID", {})
            neo4j_parts = neo4j_prop.get("rich_text", [])
            neo4j_id = neo4j_parts[0]["text"]["content"] if neo4j_parts else None

            # Extract requester
            requester_prop = props.get("Requester", {})
            requester_parts = requester_prop.get("rich_text", [])
            requester = requester_parts[0]["text"]["content"] if requester_parts else None

            # Extract created from
            created_from_prop = props.get("Created From", {})
            created_from_select = created_from_prop.get("select", {})
            created_from = created_from_select.get("name", "Notion")

            # Extract created time
            created_time = page_data.get("created_time")

            return NotionTask(
                id=page_id,
                title=title,
                status=status,
                priority=priority,
                neo4j_task_id=neo4j_id,
                agent=agent,
                requester=requester,
                created_from=created_from,
                created_at=datetime.fromisoformat(
                    created_time.replace("Z", "+00:00")
                ) if created_time else None,
                url=f"https://notion.so/{page_id.replace('-', '')}",
                properties=props
            )

        except Exception as e:
            logger.error(f"Failed to parse Notion page: {e}")
            return None

    def create_indexes(self) -> List[str]:
        """
        Create recommended Neo4j indexes for Notion integration.

        Returns:
            List of created index names
        """
        indexes = [
            "CREATE INDEX notion_task_page_id IF NOT EXISTS FOR (n:NotionTask) ON (n.notion_page_id)",
            "CREATE INDEX notion_task_neo4j_id IF NOT EXISTS FOR (n:NotionTask) ON (n.neo4j_task_id)",
            "CREATE INDEX checkpoint_task_id IF NOT EXISTS FOR (c:Checkpoint) ON (c.task_id)",
            "CREATE INDEX checkpoint_expires_at IF NOT EXISTS FOR (c:Checkpoint) ON (c.expires_at)",
            "CREATE INDEX agent_failure_agent IF NOT EXISTS FOR (f:AgentFailure) ON (f.agent)",
            "CREATE INDEX agent_failure_error_type IF NOT EXISTS FOR (f:AgentFailure) ON (f.error_type)",
            "CREATE INDEX agent_reliability_agent IF NOT EXISTS FOR (r:AgentReliability) ON (r.agent)",
        ]

        created = []

        with self.memory._session() as session:
            if session is None:
                return []

            try:
                for index_query in indexes:
                    result = session.run(index_query)
                    # Extract index name from query
                    name_match = re.search(r'INDEX (\w+)', index_query)
                    if name_match:
                        created.append(name_match.group(1))

                logger.info(f"Created {len(created)} Notion integration indexes")

            except Exception as e:
                logger.error(f"Failed to create indexes: {e}")

        return created

    def health_check(self) -> Dict:
        """
        Perform health check on Notion integration.

        Returns:
            Health status dictionary
        """
        health = {
            "status": "healthy",
            "notion_api": False,
            "database_accessible": False,
            "polling_active": self.is_polling(),
            "last_poll": self._last_poll_time.isoformat() if self._last_poll_time else None,
            "errors": []
        }

        # Test Notion API
        try:
            response = self.client.query_database()
            health["notion_api"] = True
            health["database_accessible"] = True
        except NotionAuthError:
            health["errors"].append("Notion authentication failed")
            health["status"] = "error"
        except NotionAPIError as e:
            health["errors"].append(f"Notion API error: {e}")
            health["status"] = "error"

        # Check Neo4j
        try:
            self.memory.health_check()
        except Exception as e:
            health["errors"].append(f"Neo4j error: {e}")
            health["status"] = "error"

        return health

    def close(self) -> None:
        """
        Close resources and stop polling.

        Example:
            >>> integration.close()
        """
        self.stop_polling()
        logger.info("Notion integration closed")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False


# =============================================================================
# Convenience Functions
# =============================================================================

def create_notion_integration(
    memory,
    api_key: Optional[str] = None,
    database_id: Optional[str] = None
) -> NotionIntegration:
    """
    Convenience function to create NotionIntegration.

    Args:
        memory: OperationalMemory instance
        api_key: Notion API key (defaults to NOTION_TOKEN env var)
        database_id: Notion database ID (defaults to NOTION_TASK_DATABASE_ID env var)

    Returns:
        Configured NotionIntegration instance

    Example:
        >>> from openclaw_memory import OperationalMemory
        >>> memory = OperationalMemory(...)
        >>> integration = create_notion_integration(memory)
    """
    return NotionIntegration(memory, api_key, database_id)
