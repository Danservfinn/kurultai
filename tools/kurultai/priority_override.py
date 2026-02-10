"""
Priority Override Handler

Handles natural language commands to adjust task priorities.

Author: Claude (Anthropic)
Date: 2026-02-04
"""

import re
from typing import Optional, List, Dict, Any

from .kurultai_types import Task


class PriorityCommandHandler:
    """
    Parses and executes natural language priority commands.

    Supported patterns:
    - "Priority: do X before Y"
    - "Priority: X first"
    - "Priority: competitors [research] first"
    - "Show me the DAG"
    - "Recalculate order"

    Uses regex patterns to extract task references and priority intent.
    """

    # Regex patterns for priority commands
    PATTERNS = {
        "before": re.compile(r"priority:\s*(.+?)\s+before\s+(.+?)(?:\s|$)", re.IGNORECASE),
        "first": re.compile(r"priority:\s*(.+?)\s+first(?:\s|$)", re.IGNORECASE),
        "show_dag": re.compile(r"show\s+(me\s+)?the\s+dag", re.IGNORECASE),
        "recalculate": re.compile(r"recalculate\s+order", re.IGNORECASE),
    }

    def __init__(self, neo4j_client=None, task_engine=None):
        self.neo4j = neo4j_client
        self.task_engine = task_engine

    async def handle_command(
        self,
        command: str,
        sender_hash: str
    ) -> str:
        """
        Parse and execute a priority command.

        Args:
            command: User's command text
            sender_hash: User identifier

        Returns:
            Response message
        """
        command = command.strip()

        # Check for "show DAG"
        if self.PATTERNS["show_dag"].search(command):
            return await self._handle_show_dag(sender_hash)

        # Check for "recalculate order"
        if self.PATTERNS["recalculate"].search(command):
            return await self._handle_recalculate(sender_hash)

        # Check for "X before Y"
        match = self.PATTERNS["before"].search(command)
        if match:
            first_task = match.group(1).strip()
            second_task = match.group(2).strip()
            return await self._handle_before(first_task, second_task, sender_hash)

        # Check for "X first"
        match = self.PATTERNS["first"].search(command)
        if match:
            task_desc = match.group(1).strip()
            return await self._handle_first(task_desc, sender_hash)

        return "Could not understand priority command. Try: 'Priority: do X before Y'"

    async def _handle_before(
        self,
        first_task: str,
        second_task: str,
        sender_hash: str
    ) -> str:
        """Create dependency: first_task before second_task."""
        # Find tasks by description
        task1_id = await self._find_task_by_description(first_task, sender_hash)
        task2_id = await self._find_task_by_description(second_task, sender_hash)

        if not task1_id or not task2_id:
            return f"Could not find tasks: '{first_task}' and '{second_task}'"

        # Create dependency using task engine or neo4j directly
        if self.task_engine:
            success = await self.task_engine.add_dependency(
                task_id=task2_id,
                depends_on_id=task1_id,
                dep_type="blocks"
            )
        elif self.neo4j:
            success = self.neo4j.add_dependency(
                task_id=task2_id,
                depends_on_id=task1_id,
                dep_type="blocks"
            )
        else:
            return "No task engine available to create dependency"

        if success:
            return f"✓ Created dependency: '{first_task}' must complete before '{second_task}'"
        else:
            return "Could not create dependency (possibly would create a cycle)"

    async def _handle_first(self, task_desc: str, sender_hash: str) -> str:
        """Increase priority weight for a task."""
        task_id = await self._find_task_by_description(task_desc, sender_hash)

        if not task_id:
            return f"Could not find task: '{task_desc}'"

        # Set high priority
        query = """
        MATCH (t:Task {id: $task_id, sender_hash: $sender_hash})
        SET t.priority_weight = 1.0,
            t.user_priority_override = true
        RETURN t.description as description
        """

        if self.neo4j:
            try:
                with self.neo4j._session() as session:
                    if session is None:
                        return f"Could not update task: '{task_desc}' (Neo4j unavailable)"

                    result = session.run(query, task_id=task_id, sender_hash=sender_hash)
                    record = await result.single()
                    if record:
                        return f"✓ Set '{task_desc}' as highest priority"
            except Exception as e:
                return f"Error updating task: {e}"
        else:
            return f"✓ Would set '{task_desc}' as highest priority (no Neo4j connection)"

        return f"Could not update task: '{task_desc}'"

    async def _handle_show_dag(self, sender_hash: str) -> str:
        """Generate explanation of current task DAG."""
        query = """
        MATCH (t:Task {sender_hash: $sender_hash})
        OPTIONAL MATCH (t)-[d:DEPENDS_ON]->(dep:Task)
        OPTIONAL MATCH (other)-[:DEPENDS_ON]->(t)
        RETURN t, collect(DISTINCT dep) as dependencies, collect(DISTINCT other) as dependents
        """

        if not self.neo4j:
            return "No Neo4j connection available to show DAG"

        try:
            with self.neo4j._session() as session:
                if session is None:
                    return "Could not retrieve DAG (Neo4j unavailable)"

                result = session.run(query, sender_hash=sender_hash)

                lines = ["## Current Task DAG\n"]
                async for record in result:
                    task = record["t"]
                    deps = record["dependencies"]
                    dependents = record["dependents"]

                    lines.append(f"**{task['description']}** [{task['status']}]")
                    if deps:
                        dep_descs = [d['description'] for d in deps if d]
                        if dep_descs:
                            lines.append(f"  - Depends on: {', '.join(dep_descs)}")
                    if dependents:
                        dep_descs = [d['description'] for d in dependents if d]
                        if dep_descs:
                            lines.append(f"  - Blocks: {', '.join(dep_descs)}")
                    lines.append("")

                return "\n".join(lines)
        except Exception as e:
            return f"Error retrieving DAG: {e}"

    async def _handle_recalculate(self, sender_hash: str) -> str:
        """Recalculate and show execution order."""
        query = """
        MATCH (t:Task {sender_hash: $sender_hash})
        WHERE t.status IN ['pending', 'ready']
        OPTIONAL MATCH (t)-[d:DEPENDS_ON]->()
        RETURN t, count(d) as dep_count
        ORDER BY dep_count ASC, t.priority_weight DESC, t.created_at ASC
        """

        if not self.neo4j:
            return "No Neo4j connection available to recalculate order"

        try:
            with self.neo4j._session() as session:
                if session is None:
                    return "Could not recalculate order (Neo4j unavailable)"

                result = session.run(query, sender_hash=sender_hash)

                lines = ["## Execution Order\n"]
                i = 1
                async for record in result:
                    task = record["t"]
                    dep_count = record["dep_count"]
                    lines.append(f"{i}. {task['description']} (priority: {task.get('priority_weight', 0)}, deps: {dep_count})")
                    i += 1

                return "\n".join(lines)
        except Exception as e:
            return f"Error recalculating order: {e}"

    async def _find_task_by_description(
        self,
        pattern: str,
        sender_hash: str
    ) -> Optional[str]:
        """Find task ID by description pattern matching."""
        if not self.neo4j:
            return None

        query = """
        MATCH (t:Task {sender_hash: $sender_hash})
        WHERE t.description CONTAINS $pattern
        RETURN t.id as id, t.description as description
        ORDER BY t.created_at DESC
        LIMIT 1
        """

        try:
            with self.neo4j._session() as session:
                if session is None:
                    return None

                result = session.run(query, pattern=pattern, sender_hash=sender_hash)
                record = await result.single()
                return record["id"] if record else None
        except Exception:
            return None

    async def get_task_by_id(self, task_id: str) -> Optional[Task]:
        """
        Get a task by its ID.

        Args:
            task_id: Task ID to retrieve

        Returns:
            Task dict or None
        """
        if not self.neo4j:
            return None

        query = """
        MATCH (t:Task {id: $task_id})
        RETURN t
        """

        try:
            with self.neo4j._session() as session:
                if session is None:
                    return None

                result = session.run(query, task_id=task_id)
                record = await result.single()
                return dict(record["t"]) if record else None
        except Exception:
            return None


class PriorityOverride:
    """
    Manages priority overrides and audit logging.

    Provides methods for changing task priorities with audit trails.
    """

    def __init__(self, neo4j_client=None):
        self.neo4j = neo4j_client

    async def set_task_priority(
        self,
        task_id: str,
        new_priority: float,
        sender_hash: str,
        reason: str = "user_override"
    ) -> bool:
        """
        Set task priority with audit logging.

        Args:
            task_id: Task ID
            new_priority: New priority value (0-1)
            sender_hash: User making the change
            reason: Reason for the change

        Returns:
            True if successful
        """
        if not self.neo4j:
            return False

        # First get current priority for audit
        get_query = """
        MATCH (t:Task {id: $task_id})
        RETURN t.priority_weight as current_priority
        """

        try:
            with self.neo4j._session() as session:
                if session is None:
                    return False

                result = session.run(get_query, task_id=task_id)
                record = await result.single()

                if record is None:
                    return False

                old_priority = record["current_priority"]

                # Update priority
                update_query = """
                MATCH (t:Task {id: $task_id})
                SET t.priority_weight = $new_priority,
                    t.user_priority_override = true
                RETURN t.id as id
                """

                session.run(update_query, task_id=task_id, new_priority=new_priority)

                # Log the change
                self.neo4j.log_priority_change(
                    sender_hash=sender_hash,
                    task_id=task_id,
                    old_priority=old_priority,
                    new_priority=new_priority,
                    reason=reason
                )

                return True

        except Exception as e:
            print(f"Error setting priority: {e}")
            return False

    async def boost_to_critical(
        self,
        task_description: str,
        sender_hash: str
    ) -> str:
        """
        Boost a task to critical priority.

        Args:
            task_description: Task description to match
            sender_hash: User identifier

        Returns:
            Result message
        """
        query = """
        MATCH (t:Task {sender_hash: $sender_hash})
        WHERE t.description CONTAINS $description
        RETURN t.id as id, t.priority_weight as old_priority
        """

        if not self.neo4j:
            return "No Neo4j connection available"

        try:
            with self.neo4j._session() as session:
                if session is None:
                    return "Could not boost task (Neo4j unavailable)"

                result = session.run(query, description=task_description, sender_hash=sender_hash)
                record = await result.single()

                if not record:
                    return f"Could not find task matching: '{task_description}'"

                task_id = record["id"]
                old_priority = record["old_priority"]

                update_query = """
                MATCH (t:Task {id: $task_id})
                SET t.priority_weight = 1.0,
                    t.user_priority_override = true
                RETURN t.description as description
                """

                session.run(update_query, task_id=task_id)

                self.neo4j.log_priority_change(
                    sender_hash=sender_hash,
                    task_id=task_id,
                    old_priority=old_priority,
                    new_priority=1.0,
                    reason="boosted_to_critical"
                )

                return f"✓ Boosted '{task_description}' to critical priority"

        except Exception as e:
            return f"Error boosting task: {e}"
