#!/usr/bin/env python3
"""
Kurultai Notion Sync Module

Provides command-based sync between Notion task databases and Kurultai's
Neo4j Task Dependency Engine. Users can reprioritize tasks in Notion and
sync changes on-demand without breaking ongoing work.

Usage:
    user_message = "Sync from Notion"
    handler = NotionSyncHandler(neo4j_client, notion_client)
    response = await handler.handle(user_message, sender_hash)
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
import httpx
from neo4j import AsyncGraphDatabase


# ============================================================================
# Data Models
# ============================================================================

class TaskStatus(Enum):
    """Task status values matching TaskNode schema."""
    PENDING = "pending"
    BLOCKED = "blocked"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABORTED = "aborted"


class PriorityLevel(Enum):
    """Priority levels with numeric weights."""
    CRITICAL = 1.0
    HIGH = 0.8
    MEDIUM = 0.5
    LOW = 0.3
    BACKLOG = 0.1


class ChangeType(Enum):
    """Types of changes during reconciliation."""
    CREATE = "create"
    PRIORITY = "priority"
    STATUS = "status"
    MISSING_IN_NOTION = "missing_in_notion"
    BLOCKED = "blocked"


@dataclass
class NotionTask:
    """Task representation from Notion database."""
    id: str
    description: str
    status: TaskStatus
    priority_weight: float
    required_agents: List[str]
    notion_url: str
    notion_page_id: str
    last_edited_time: datetime           # For change detection
    deliverable_type: str = "analysis"
    estimated_duration: int = 15
    sender_hash: str = ""


@dataclass
class TaskNode:
    """Task representation from Neo4j."""
    id: str
    description: str
    status: TaskStatus
    priority_weight: float
    required_agents: List[str]
    deliverable_type: str
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    notion_synced_at: Optional[datetime] = None
    notion_url: Optional[str] = None


@dataclass
class Change:
    """A detected change during reconciliation."""
    type: ChangeType
    task_id: str
    safe: bool = True
    old_value: Any = None
    new_value: Any = None
    notion: Optional[NotionTask] = None
    message: str = ""


@dataclass
class SyncResult:
    """Result of a sync operation."""
    success: bool
    created: List[Change] = field(default_factory=list)
    updated: List[Change] = field(default_factory=list)
    skipped: List[Change] = field(default_factory=list)
    failed: List[Change] = field(default_factory=list)
    duration_seconds: float = 0.0

    def total_changes(self) -> int:
        return len(self.created) + len(self.updated)


# ============================================================================
# Notion API Client
# ============================================================================

class NotionClient:
    """
    Client for interacting with Notion API.

    Requires NOTION_API_KEY and NOTION_DATABASE_ID environment variables.
    """

    BASE_URL = "https://api.notion.com/v1"
    VERSION = "2022-06-28"

    # Status mappings
    STATUS_MAP: Dict[str, TaskStatus] = {
        "Not Started": TaskStatus.PENDING,
        "Blocked": TaskStatus.BLOCKED,
        "Ready": TaskStatus.READY,
        "In Progress": TaskStatus.IN_PROGRESS,
        "Completed": TaskStatus.COMPLETED,
        "Cancelled": TaskStatus.ABORTED,
    }

    # Priority mappings
    PRIORITY_MAP: Dict[str, float] = {
        "Critical": PriorityLevel.CRITICAL.value,
        "High": PriorityLevel.HIGH.value,
        "Medium": PriorityLevel.MEDIUM.value,
        "Low": PriorityLevel.LOW.value,
        "Backlog": PriorityLevel.BACKLOG.value,
    }

    # Agent mappings
    AGENT_MAP: Dict[str, List[str]] = {
        "Research": ["researcher"],
        "Analysis": ["analyst"],
        "Development": ["developer"],
        "Writing": ["writer"],
        "Operations": ["ops"],
        "Strategy": ["analyst"],
    }

    def __init__(
        self,
        api_key: Optional[str] = None,
        database_id: Optional[str] = None
    ):
        self.api_key = api_key or os.getenv("NOTION_API_KEY")
        self.database_id = database_id or os.getenv("NOTION_DATABASE_ID")

        if not self.api_key:
            raise ValueError("NOTION_API_KEY environment variable required")
        if not self.database_id:
            raise ValueError("NOTION_DATABASE_ID environment variable required")

        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Notion-Version": self.VERSION,
                "Content-Type": "application/json",
            },
            timeout=30.0
        )
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    async def fetch_tasks(self, sender_hash: str) -> List[NotionTask]:
        """
        Fetch all tasks for a user from Notion database.

        Args:
            sender_hash: HMAC-SHA256 of user's phone number

        Returns:
            List of NotionTask objects
        """
        if not self._client:
            raise RuntimeError("Client not initialized. Use async context manager.")

        tasks = []
        has_more = True
        next_cursor = None

        while has_more:
            body = {
                "filter": {
                    "property": "SenderHash",
                    "rich_text": {"equals": sender_hash}
                }
            }
            if next_cursor:
                body["start_cursor"] = next_cursor

            response = await self._client.post(
                f"/databases/{self.database_id}/query",
                json=body
            )
            response.raise_for_status()
            data = response.json()

            for row in data.get("results", []):
                try:
                    task = self._parse_task(row, sender_hash)
                    tasks.append(task)
                except (KeyError, ValueError) as e:
                    # Log but continue parsing other tasks
                    print(f"Warning: Failed to parse task: {e}")

            has_more = data.get("has_more", False)
            next_cursor = data.get("next_cursor")

        return tasks

    def _parse_task(self, row: dict, sender_hash: str) -> NotionTask:
        """Parse Notion page into NotionTask object."""
        props = row.get("properties", {})

        # Extract ID (required)
        id_prop = props.get("ID", props.get("id", {}))
        if "title" in id_prop:
            task_id = id_prop["title"][0]["plain_text"]
        elif "rich_text" in id_prop:
            task_id = id_prop["rich_text"]["plain_text"]
        else:
            raise ValueError("Task missing ID property")

        # Extract description (title property)
        title_prop = props.get("Name", props.get("description", {}))
        description = title_prop.get("title", [{}])[0].get("plain_text", task_id)

        # Extract status
        status_prop = props.get("Status", {})
        status_name = status_prop.get("select", {}).get("name", "Not Started")
        status = self.STATUS_MAP.get(status_name, TaskStatus.PENDING)

        # Extract priority
        priority_prop = props.get("Priority", {})
        priority_name = priority_prop.get("select", {}).get("name", "Medium")
        priority_weight = self.PRIORITY_MAP.get(priority_name, PriorityLevel.MEDIUM.value)

        # Extract agents
        agents_prop = props.get("Agent", props.get("Agents", {}))
        agent_selects = agents_prop.get("multi_select", [])
        required_agents = []
        for select in agent_selects:
            agent_list = self.AGENT_MAP.get(select["name"])
            if agent_list:
                required_agents.extend(agent_list)

        # Deliverable type (optional property)
        deliverable_prop = props.get("Type", props.get("DeliverableType", {}))
        deliverable_type = deliverable_prop.get("select", {}).get("name", "analysis")

        # Estimated duration (optional property)
        duration_prop = props.get("Duration", props.get("EstimatedDuration", {}))
        estimated_duration = duration_prop.get("number", 15)

        # Extract last_edited_time (for change detection)
        last_edited_str = row.get("last_edited_time", "")
        if last_edited_str:
            # Notion returns ISO 8601 format
            last_edited_time = datetime.fromisoformat(last_edited_str.replace("Z", "+00:00"))
        else:
            last_edited_time = datetime.now(timezone.utc)

        return NotionTask(
            id=task_id,
            description=description,
            status=status,
            priority_weight=priority_weight,
            required_agents=required_agents or ["analyst"],
            notion_url=row.get("url", ""),
            notion_page_id=row.get("id", ""),
            last_edited_time=last_edited_time,
            deliverable_type=deliverable_type,
            estimated_duration=estimated_duration,
            sender_hash=sender_hash
        )


# ============================================================================
# Reconciliation Engine
# ============================================================================

class ReconciliationEngine:
    """
    Intelligently merges Notion changes with Neo4j state.

    Safety rules:
    1. Never interrupt in-progress tasks
    2. Never revert completed tasks
    3. Respect DAG dependencies (can't enable blocked tasks)
    4. Priority changes are always safe
    """

    # Safe status transitions
    SAFE_TRANSITIONS: Dict[TaskStatus, Set[TaskStatus]] = {
        TaskStatus.PENDING: {TaskStatus.BLOCKED, TaskStatus.READY, TaskStatus.ABORTED},
        TaskStatus.BLOCKED: {TaskStatus.PENDING, TaskStatus.ABORTED},
        TaskStatus.READY: {TaskStatus.IN_PROGRESS, TaskStatus.ABORTED},
        TaskStatus.ABORTED: {TaskStatus.PENDING},  # Allow retry
    }

    def __init__(self, neo4j_client):
        self.neo4j = neo4j_client

    async def reconcile(
        self,
        notion_tasks: List[NotionTask],
        neo4j_tasks: List[TaskNode]
    ) -> List[Change]:
        """
        Compute safe changes to apply.

        Args:
            notion_tasks: Tasks from Notion
            neo4j_tasks: Current tasks from Neo4j

        Returns:
            List of Change objects
        """
        changes = []

        # Index by ID
        notion_by_id = {t.id: t for t in notion_tasks}
        neo4j_by_id = {t.id: t for t in neo4j_tasks}

        # 1. Tasks in Notion but not Neo4j → CREATE
        for notion_task in notion_tasks:
            if notion_task.id not in neo4j_by_id:
                changes.append(Change(
                    type=ChangeType.CREATE,
                    task_id=notion_task.id,
                    notion=notion_task,
                    safe=True
                ))

        # 2. Tasks in both → COMPARE
        for task_id in set(notion_by_id) & set(neo4j_by_id):
            notion = notion_by_id[task_id]
            neo4j = neo4j_by_id[task_id]

            # Rule 1: Never touch in-progress tasks
            if neo4j.status == TaskStatus.IN_PROGRESS:
                continue

            # Rule 2: Never revert completed tasks
            if neo4j.status == TaskStatus.COMPLETED:
                continue

            # Priority change (always safe)
            if abs(notion.priority_weight - neo4j.priority_weight) > 0.01:
                changes.append(Change(
                    type=ChangeType.PRIORITY,
                    task_id=task_id,
                    old_value=neo4j.priority_weight,
                    new_value=notion.priority_weight,
                    safe=True
                ))

            # Status change (conditional safety)
            if notion.status != neo4j.status:
                if self._can_transition(neo4j.status, notion.status):
                    # Additional check: verify dependencies for READY status
                    if notion.status == TaskStatus.READY:
                        dependencies_clear = await self._check_dependencies_clear(task_id)
                        if not dependencies_clear:
                            changes.append(Change(
                                type=ChangeType.BLOCKED,
                                task_id=task_id,
                                safe=False,
                                message=f"Cannot set to READY: dependencies not met"
                            ))
                            continue

                    changes.append(Change(
                        type=ChangeType.STATUS,
                        task_id=task_id,
                        old_value=neo4j.status.value,
                        new_value=notion.status.value,
                        safe=True
                    ))

        # 3. Tasks in Neo4j but not Notion → FLAG
        for neo4j_task in neo4j_tasks:
            if neo4j_task.id not in notion_by_id:
                changes.append(Change(
                    type=ChangeType.MISSING_IN_NOTION,
                    task_id=neo4j_task.id,
                    safe=False,
                    message=f"Task '{neo4j_task.description[:50]}' exists in Kurultai "
                           f"but not in Notion. Please add to Notion or cancel here."
                ))

        return changes

    def _can_transition(self, from_status: TaskStatus, to_status: TaskStatus) -> bool:
        """Check if status transition is safe."""
        allowed = self.SAFE_TRANSITIONS.get(from_status, set())
        return to_status in allowed

    async def _check_dependencies_clear(self, task_id: str) -> bool:
        """Check if all BLOCKS dependencies for this task are completed."""
        query = """
        MATCH (t:Task {id: $task_id})<-[:DEPENDS_ON {type: "blocks"}]-(blocker:Task)
        WHERE blocker.status <> "completed"
        RETURN count(blocker) as blocked_count
        """
        async with self.neo4j.session() as session:
            result = await session.run(query, {"task_id": task_id})
            record = await result.single()
            blocked_count = record["blocked_count"] if record else 0
            return blocked_count == 0


# ============================================================================
# Sync Handler
# ============================================================================

class NotionSyncHandler:
    """
    Main handler for Notion sync commands.

    Detects sync commands, fetches data, reconciles changes, and applies updates.
    """

    SYNC_PATTERNS = [
        r"sync\s+(from\s+)?notion",
        r"notion\s+sync",
        r"pull\s+from\s+notion",
        r"update\s+from\s+notion",
    ]

    def __init__(self, neo4j_uri: str, neo4j_user: str, neo4j_password: str):
        self.driver = AsyncGraphDatabase.driver(
            neo4j_uri,
            auth=(neo4j_user, neo4j_password)
        )
        self.reconciler = ReconciliationEngine(self.driver)

    async def close(self):
        """Close Neo4j driver."""
        await self.driver.close()

    async def handle(self, message: str, sender_hash: str) -> Optional[str]:
        """
        Detect and handle Notion sync commands.

        Args:
            message: User message text
            sender_hash: HMAC-SHA256 of sender's phone

        Returns:
            Response message if sync triggered, None otherwise
        """
        for pattern in self.SYNC_PATTERNS:
            if re.search(pattern, message, re.I):
                return await self.sync_from_notion(sender_hash)

        return None

    async def sync_from_notion(self, sender_hash: str) -> str:
        """
        Execute full sync from Notion.

        Args:
            sender_hash: User's sender hash

        Returns:
            Formatted sync result message
        """
        start_time = datetime.now(timezone.utc)

        try:
            # 1. Fetch from Notion
            async with NotionClient() as notion:
                notion_tasks = await notion.fetch_tasks(sender_hash)
        except Exception as e:
            return f"❌ **Failed to connect to Notion:** {str(e)}\n\n" \
                   f"Please check your NOTION_API_KEY and NOTION_DATABASE_ID."

        # 2. Fetch from Neo4j
        neo4j_tasks = await self._fetch_neo4j_tasks(sender_hash)

        # 3. Reconcile
        changes = await self.reconciler.reconcile(notion_tasks, neo4j_tasks)

        # 4. Apply safe changes
        result = await self._apply_changes(changes, sender_hash)

        # 5. Log sync event
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        await self._log_sync_event(sender_hash, result, duration)

        # 6. Format response
        return self._format_result(result)

    async def _fetch_neo4j_tasks(self, sender_hash: str) -> List[TaskNode]:
        """Fetch all tasks for user from Neo4j."""
        query = """
        MATCH (t:Task {sender_hash: $sender_hash})
        RETURN t
        ORDER BY t.created_at DESC
        """
        tasks = []

        async with self.driver.session() as session:
            result = await session.run(query, {"sender_hash": sender_hash})
            async for record in result:
                node = record["t"]
                tasks.append(TaskNode(
                    id=node["id"],
                    description=node["description"],
                    status=TaskStatus(node["status"]),
                    priority_weight=node["priority_weight"],
                    required_agents=node.get("required_agents", []),
                    deliverable_type=node.get("deliverable_type", "analysis"),
                    created_at=datetime.fromisoformat(node["created_at"]),
                    started_at=datetime.fromisoformat(node["started_at"]) if node.get("started_at") else None,
                    completed_at=datetime.fromisoformat(node["completed_at"]) if node.get("completed_at") else None,
                    notion_synced_at=datetime.fromisoformat(node["notion_synced_at"]) if node.get("notion_synced_at") else None,
                    notion_url=node.get("notion_url")
                ))

        return tasks

    async def _apply_changes(self, changes: List[Change], sender_hash: str) -> SyncResult:
        """Apply safe changes to Neo4j."""
        result = SyncResult(success=True)
        now = datetime.now(timezone.utc).isoformat()

        async with self.driver.session() as session:
            for change in changes:
                try:
                    if change.type == ChangeType.CREATE and change.safe and change.notion:
                        await self._create_task(session, change.notion, sender_hash, now)
                        result.created.append(change)

                    elif change.type == ChangeType.PRIORITY and change.safe:
                        await self._update_priority(session, change.task_id, change.new_value, now)
                        result.updated.append(change)

                    elif change.type == ChangeType.STATUS and change.safe:
                        await self._update_status(session, change.task_id, change.new_value, now)
                        result.updated.append(change)

                    elif not change.safe:
                        result.skipped.append(change)

                except Exception as e:
                    change.message = f"Error: {str(e)}"
                    result.failed.append(change)

        result.success = len(result.failed) == 0
        return result

    async def _create_task(
        self,
        session,
        task: NotionTask,
        sender_hash: str,
        timestamp: str
    ):
        """Create a new task in Neo4j from Notion data."""
        query = """
        MERGE (t:Task {id: $id})
        SET t.description = $description,
            t.sender_hash = $sender_hash,
            t.status = $status,
            t.priority_weight = $priority_weight,
            t.required_agents = $required_agents,
            t.deliverable_type = $deliverable_type,
            t.estimated_duration = $estimated_duration,
            t.created_at = $created_at,
            t.notion_synced_at = $synced_at,
            t.notion_url = $notion_url,
            t.notion_page_id = $notion_page_id,
            t.external_priority_source = "notion"
        """
        await session.run(query, {
            "id": task.id,
            "description": task.description,
            "sender_hash": sender_hash,
            "status": task.status.value,
            "priority_weight": task.priority_weight,
            "required_agents": task.required_agents,
            "deliverable_type": task.deliverable_type,
            "estimated_duration": task.estimated_duration,
            "created_at": timestamp,
            "synced_at": timestamp,
            "notion_url": task.notion_url,
            "notion_page_id": task.notion_page_id
        })

    async def _update_priority(self, session, task_id: str, priority: float, timestamp: str):
        """Update task priority weight."""
        query = """
        MATCH (t:Task {id: $task_id})
        SET t.priority_weight = $priority,
            t.external_priority_source = "notion",
            t.notion_synced_at = $synced_at
        """
        await session.run(query, {
            "task_id": task_id,
            "priority": priority,
            "synced_at": timestamp
        })

    async def _update_status(self, session, task_id: str, status: str, timestamp: str):
        """Update task status."""
        query = """
        MATCH (t:Task {id: $task_id})
        SET t.status = $status,
            t.notion_synced_at = $synced_at
        """
        await session.run(query, {
            "task_id": task_id,
            "status": status,
            "synced_at": timestamp
        })

    async def _log_sync_event(self, sender_hash: str, result: SyncResult, duration: float):
        """Log sync event to Neo4j for audit trail."""
        query = """
        CREATE (e:SyncEvent {
            id: randomUUID(),
            sender_hash: $sender_hash,
            sync_type: "notion",
            triggered_at: datetime(),
            completed_at: datetime(),
            changes_applied: $applied,
            changes_skipped: $skipped,
            changes_failed: $failed,
            duration_seconds: $duration,
            status: $status
        })
        """
        await self.driver.run(query, {
            "sender_hash": sender_hash,
            "applied": result.total_changes(),
            "skipped": len(result.skipped),
            "failed": len(result.failed),
            "duration": duration,
            "status": "success" if result.success else "partial" if result.total_changes() > 0 else "failed"
        })

    def _format_result(self, result: SyncResult) -> str:
        """Format sync result for user message."""
        lines = ["**Sync from Notion complete**\n"]

        if result.created:
            lines.append(f"✅ **{len(result.created)} new task(s) created:**")
            for change in result.created[:5]:  # Limit output
                lines.append(f"  • {change.notion.description[:50]}")
            if len(result.created) > 5:
                lines.append(f"  • ... and {len(result.created) - 5} more")

        if result.updated:
            lines.append(f"\n✅ **{len(result.updated)} task(s) updated:**")
            for change in result.updated[:5]:
                if change.type == ChangeType.PRIORITY:
                    lines.append(
                        f"  • Priority: {change.old_value} → {change.new_value} "
                        f"({change.task_id[:8]}...)"
                    )
                else:
                    lines.append(
                        f"  • Status: {change.old_value} → {change.new_value}"
                    )
            if len(result.updated) > 5:
                lines.append(f"  • ... and {len(result.updated) - 5} more")

        if result.skipped:
            lines.append(f"\n⚠️ **{len(result.skipped)} change(s) skipped** (safety rules):")
            for change in result.skipped[:3]:
                lines.append(f"  • {change.message}")
            if len(result.skipped) > 3:
                lines.append(f"  • ... and {len(result.skipped) - 3} more")

        if result.failed:
            lines.append(f"\n❌ **{len(result.failed)} change(s) failed:**")
            for change in result.failed[:3]:
                lines.append(f"  • {change.message}")
            if len(result.failed) > 3:
                lines.append(f"  • ... and {len(result.failed) - 3} more")

        if not result.total_changes() and not result.skipped:
            lines.append("✅ Everything up to date. No changes needed.")

        return "\n".join(lines)


# ============================================================================
# Continuous Polling Engine (Ögedei's Background Service)
# ============================================================================

class NotionChangeType(Enum):
    """Types of changes detected in Notion."""
    NEW_TASK = "new_task"
    PRIORITY = "priority"
    STATUS = "status"
    AGENT = "agent"
    DESCRIPTION = "description"
    DELETED = "deleted"
    PROPERTIES = "properties"


@dataclass
class NotionChange:
    """A detected change from Notion."""
    type: NotionChangeType
    task_id: str
    priority: str  # critical|high|medium|low
    message: str = ""

    # Change data
    old_value: Any = None
    new_value: Any = None
    notion_task: Optional[NotionTask] = None
    neo4j_task: Optional[TaskNode] = None

    # Processing metadata
    skip_reason: str = ""
    error: str = ""


class NotionPollingEngine:
    """
    Ögedei's continuous polling engine for Notion changes.

    Runs every N seconds (configurable, default: 60s).
    Detects ALL changes using Notion's last_edited_time.
    Applies changes safely using ReconciliationEngine.

    Usage:
        engine = NotionPollingEngine(neo4j_driver, poll_interval=60)
        engine.start()
        # ... runs in background ...
        engine.stop()
    """

    def __init__(
        self,
        neo4j_uri: str,
        neo4j_user: str,
        neo4j_password: str,
        poll_interval_seconds: int = None
    ):
        self.driver = AsyncGraphDatabase.driver(
            neo4j_uri,
            auth=(neo4j_user, neo4j_password)
        )
        self.poll_interval = poll_interval_seconds or int(
            os.getenv("NOTION_POLL_INTERVAL", "60")
        )
        self.reconciler = ReconciliationEngine(self.driver)

        # Track last sync time per user
        self.last_sync: Dict[str, datetime] = {}

        # Track seen task IDs (for deletion detection)
        self.seen_task_ids: Dict[str, Set[str]] = {}

        self._running = False
        self._scheduler: Optional[Any] = None

    async def close(self):
        """Close Neo4j driver and stop polling."""
        await self.driver.close()
        if self._running:
            self.stop()

    def start(self):
        """Start background polling."""
        if self._running:
            print("[Poll] Already running")
            return

        try:
            from apscheduler.schedulers.background import BackgroundScheduler

            self._scheduler = BackgroundScheduler()
            self._scheduler.add_job(
                self._poll_loop,
                'interval',
                seconds=self.poll_interval,
                id='notion_poll',
                max_instances=1
            )
            self._scheduler.start()
            self._running = True
            print(f"[Ögedei] Notion polling started (interval: {self.poll_interval}s)")
        except ImportError:
            print("[WARN] APScheduler not available. Polling disabled.")
            print("[INFO] Install: pip install APScheduler")
        except Exception as e:
            print(f"[ERROR] Failed to start polling: {e}")

    def stop(self):
        """Stop background polling."""
        if self._scheduler:
            self._scheduler.shutdown()
            self._running = False
            print("[Ögedei] Notion polling stopped")

    async def _poll_loop(self):
        """Poll loop called by scheduler."""
        try:
            # Get all users with Notion integration enabled
            users = await self._get_active_users()

            for user_hash in users:
                try:
                    await self._poll_user(user_hash)
                except Exception as e:
                    print(f"[ERROR] Poll failed for {user_hash[:8]}...: {e}")
                    await self._log_sync_event(
                        sender_hash=user_hash,
                        status="failed",
                        error=str(e)
                    )
        except Exception as e:
            print(f"[ERROR] Poll loop error: {e}")

    async def _get_active_users(self) -> List[str]:
        """Get all users with Notion integration enabled."""
        query = """
        MATCH (u:UserConfig {notion_integration_enabled: true})
        RETURN u.sender_hash as sender_hash
        """
        async with self.driver.session() as session:
            result = await session.run(query)
            return [record["sender_hash"] async for record in result]

    async def _poll_user(self, sender_hash: str):
        """
        Poll Notion for a single user, detect all changes.
        """
        last_sync = self.last_sync.get(sender_hash, datetime.min)

        # Fetch all tasks from Notion
        async with NotionClient() as notion:
            notion_tasks = await notion.fetch_tasks(sender_hash)

        # Detect changes by last_edited_time
        changed_tasks = [
            t for t in notion_tasks
            if t.last_edited_time > last_sync
        ]

        # Detect new tasks
        neo4j_task_ids = await self._get_task_ids(sender_hash)
        current_ids = {t.id for t in notion_tasks}
        new_tasks = [t for t in notion_tasks if t.id not in neo4j_task_ids]

        # Detect deletions
        previously_seen = self.seen_task_ids.get(sender_hash, set())
        deleted_ids = previously_seen - current_ids

        # Reconcile and apply
        changes = await self._detect_all_changes(
            notion_tasks,
            changed_tasks,
            new_tasks,
            deleted_ids,
            sender_hash
        )

        if changes:
            result = await self._apply_changes(changes, sender_hash)
            await self._log_sync_result(sender_hash, result)

        # Update tracking
        self.last_sync[sender_hash] = datetime.now(timezone.utc)
        self.seen_task_ids[sender_hash] = current_ids

    async def _get_task_ids(self, sender_hash: str) -> Set[str]:
        """Get all task IDs for user from Neo4j."""
        query = """
        MATCH (t:Task {sender_hash: $sender_hash})
        RETURN t.id as id
        """
        async with self.driver.session() as session:
            result = await session.run(query, {"sender_hash": sender_hash})
            return {record["id"] async for record in result}

    async def _detect_all_changes(
        self,
        notion_tasks: List[NotionTask],
        changed_tasks: List[NotionTask],
        new_tasks: List[NotionTask],
        deleted_ids: Set[str],
        sender_hash: str
    ) -> List[NotionChange]:
        """Detect ALL types of changes."""
        changes = []

        # Get Neo4j state
        neo4j_tasks = await self._fetch_neo4j_tasks(sender_hash)
        neo4j_by_id = {t.id: t for t in neo4j_tasks}

        # CRITICAL: New tasks
        for task in new_tasks:
            changes.append(NotionChange(
                type=NotionChangeType.NEW_TASK,
                task_id=task.id,
                notion_task=task,
                priority="critical",
                message=f"New task: '{task.description[:50]}...'"
            ))

        # HIGH: Deleted tasks
        for task_id in deleted_ids:
            if task_id in neo4j_by_id:
                changes.append(NotionChange(
                    type=NotionChangeType.DELETED,
                    task_id=task_id,
                    neo4j_task=neo4j_by_id[task_id],
                    priority="high",
                    message=f"Deleted from Notion"
                ))

        # HIGH: Status changes
        for task in changed_tasks:
            if task.id in neo4j_by_id:
                neo4j = neo4j_by_id[task.id]
                if task.status != neo4j.status:
                    changes.append(NotionChange(
                        type=NotionChangeType.STATUS,
                        task_id=task.id,
                        old_value=neo4j.status.value,
                        new_value=task.status.value,
                        notion_task=task,
                        neo4j_task=neo4j,
                        priority="high"
                    ))

        # MEDIUM: Priority changes
        for task in changed_tasks:
            if task.id in neo4j_by_id:
                neo4j = neo4j_by_id[task.id]
                if abs(task.priority_weight - neo4j.priority_weight) > 0.01:
                    changes.append(NotionChange(
                        type=NotionChangeType.PRIORITY,
                        task_id=task.id,
                        old_value=neo4j.priority_weight,
                        new_value=task.priority_weight,
                        priority="medium"
                    ))

        # LOW: Agent changes
        for task in changed_tasks:
            if task.id in neo4j_by_id:
                neo4j = neo4j_by_id[task.id]
                if set(task.required_agents) != set(neo4j.required_agents):
                    changes.append(NotionChange(
                        type=NotionChangeType.AGENT,
                        task_id=task.id,
                        old_value=neo4j.required_agents,
                        new_value=task.required_agents,
                        priority="low"
                    ))

        # LOW: Description changes
        for task in changed_tasks:
            if task.id in neo4j_by_id:
                neo4j = neo4j_by_id[task.id]
                if task.description != neo4j.description:
                    changes.append(NotionChange(
                        type=NotionChangeType.DESCRIPTION,
                        task_id=task.id,
                        old_value=neo4j.description[:50],
                        new_value=task.description[:50],
                        priority="low"
                    ))

        # Sort by priority
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        changes.sort(key=lambda c: priority_order.get(c.priority, 99))

        return changes

    async def _fetch_neo4j_tasks(self, sender_hash: str) -> List[TaskNode]:
        """Fetch all tasks for user from Neo4j."""
        query = """
        MATCH (t:Task {sender_hash: $sender_hash})
        RETURN t
        """
        tasks = []
        async with self.driver.session() as session:
            result = await session.run(query, {"sender_hash": sender_hash})
            async for record in result:
                node = record["t"]
                tasks.append(TaskNode(
                    id=node["id"],
                    description=node["description"],
                    status=TaskStatus(node["status"]),
                    priority_weight=node["priority_weight"],
                    required_agents=node.get("required_agents", []),
                    deliverable_type=node.get("deliverable_type", "analysis"),
                    created_at=datetime.fromisoformat(node["created_at"]),
                    notion_synced_at=datetime.fromisoformat(node["notion_synced_at"]) if node.get("notion_synced_at") else None,
                    notion_url=node.get("notion_url")
                ))
        return tasks

    async def _apply_changes(
        self,
        changes: List[NotionChange],
        sender_hash: str
    ) -> SyncResult:
        """Apply detected changes using safety rules."""
        result = SyncResult(success=True)
        now = datetime.now(timezone.utc).isoformat()

        async with self.driver.session() as session:
            for change in changes:
                try:
                    if change.type == NotionChangeType.NEW_TASK:
                        # Create with status "pending_review" for Kublai
                        await self._create_task(session, change.notion_task, sender_hash, now)
                        result.created.append(change)

                    elif change.type == NotionChangeType.PRIORITY:
                        await self._update_priority(session, change.task_id, change.new_value, now)
                        result.updated.append(change)

                    elif change.type == NotionChangeType.STATUS:
                        # Check safety
                        safe = await self._check_status_safe(change)
                        if safe:
                            await self._update_status(session, change.task_id, change.new_value, now)
                            result.updated.append(change)
                        else:
                            change.skip_reason = "Safety rule blocked"
                            result.skipped.append(change)

                    elif change.type == NotionChangeType.DESCRIPTION:
                        await self._update_description(session, change.task_id, change.new_value, now)
                        result.updated.append(change)

                    elif change.type == NotionChangeType.DELETED:
                        # Archive, don't delete
                        await self._archive_task(session, change.task_id, now)
                        result.updated.append(change)

                except Exception as e:
                    change.error = str(e)
                    result.failed.append(change)

        result.success = len(result.failed) == 0
        return result

    async def _check_status_safe(self, change: NotionChange) -> bool:
        """Check if status change is safe."""
        current = change.neo4j_task.status
        new = TaskStatus(change.new_value)

        # Never interrupt in_progress
        if current == TaskStatus.IN_PROGRESS:
            return False

        # Never revert completed
        if current == TaskStatus.COMPLETED:
            return False

        # Check dependencies for READY
        if new == TaskStatus.READY:
            return await self.reconciler._check_dependencies_clear(change.task_id)

        return True

    async def _create_task(self, session, task: NotionTask, sender_hash: str, timestamp: str):
        """Create task with pending_review status."""
        query = """
        MERGE (t:Task {id: $id})
        SET t.description = $description,
            t.sender_hash = $sender_hash,
            t.status = "pending_review",
            t.priority_weight = $priority_weight,
            t.required_agents = $required_agents,
            t.deliverable_type = $deliverable_type,
            t.estimated_duration = $estimated_duration,
            t.created_at = $created_at,
            t.notion_synced_at = $synced_at,
            t.notion_url = $notion_url,
            t.notion_page_id = $notion_page_id,
            t.external_priority_source = "notion"
        """
        await session.run(query, {
            "id": task.id,
            "description": task.description,
            "sender_hash": sender_hash,
            "priority_weight": task.priority_weight,
            "required_agents": task.required_agents,
            "deliverable_type": task.deliverable_type,
            "estimated_duration": task.estimated_duration,
            "created_at": timestamp,
            "synced_at": timestamp,
            "notion_url": task.notion_url,
            "notion_page_id": task.notion_page_id
        })

    async def _update_priority(self, session, task_id: str, priority: float, timestamp: str):
        """Update task priority."""
        query = """
        MATCH (t:Task {id: $task_id})
        SET t.priority_weight = $priority,
            t.notion_synced_at = $synced_at
        """
        await session.run(query, {"task_id": task_id, "priority": priority, "synced_at": timestamp})

    async def _update_status(self, session, task_id: str, status: str, timestamp: str):
        """Update task status."""
        query = """
        MATCH (t:Task {id: $task_id})
        SET t.status = $status,
            t.notion_synced_at = $synced_at
        """
        await session.run(query, {"task_id": task_id, "status": status, "synced_at": timestamp})

    async def _update_description(self, session, task_id: str, description: str, timestamp: str):
        """Update task description."""
        query = """
        MATCH (t:Task {id: $task_id})
        SET t.description = $description,
            t.notion_synced_at = $synced_at
        """
        await session.run(query, {"task_id": task_id, "description": description, "synced_at": timestamp})

    async def _archive_task(self, session, task_id: str, timestamp: str):
        """Archive task (soft delete)."""
        query = """
        MATCH (t:Task {id: $task_id})
        SET t.status = "archived",
            t.notion_synced_at = $synced_at,
            t.archived_at = $synced_at
        """
        await session.run(query, {"task_id": task_id, "synced_at": timestamp})

    async def _log_sync_result(self, sender_hash: str, result: SyncResult):
        """Log sync result to Neo4j."""
        await self._log_sync_event(
            sender_hash=sender_hash,
            status="success" if result.success else "partial",
            created=result.total_changes(),
            skipped=len(result.skipped),
            failed=len(result.failed)
        )

    async def _log_sync_event(
        self,
        sender_hash: str,
        status: str,
        error: str = "",
        created: int = 0,
        skipped: int = 0,
        failed: int = 0
    ):
        """Log sync event."""
        query = """
        CREATE (e:SyncEvent {
            id: randomUUID(),
            sender_hash: $sender_hash,
            sync_type: "notion_poll",
            triggered_at: datetime(),
            completed_at: datetime(),
            changes_applied: $applied,
            changes_skipped: $skipped,
            changes_failed: $failed,
            status: $status,
            error: $error
        })
        """
        await self.driver.run(query, {
            "sender_hash": sender_hash,
            "applied": created,
            "skipped": skipped,
            "failed": failed,
            "status": status,
            "error": error
        })


# ============================================================================
# Standalone Usage
# ============================================================================

async def main():
    """Example usage for testing."""
    import asyncio

    # Configuration
    NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

    # Test sender hash (use real hash in production)
    test_sender = "test_sender_hash"

    handler = NotionSyncHandler(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)

    try:
        # Test sync
        result = await handler.sync_from_notion(test_sender)
        print(result)
    finally:
        await handler.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
