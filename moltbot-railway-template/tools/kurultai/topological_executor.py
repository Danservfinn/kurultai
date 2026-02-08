"""
Topological Executor

Executes tasks in dependency order, respecting priorities and agent limits.

Author: Claude (Anthropic)
Date: 2026-02-04
"""

import asyncio
import logging
from collections import defaultdict
from typing import Dict, List, Optional

from .complexity_config import ComplexityConfig, DEFAULT_CONFIG, complexity_to_team_size
from .types import Task, ExecutionSummary, MAX_TASKS_PER_AGENT, DeliverableType

logger = logging.getLogger(__name__)


class TopologicalExecutor:
    """
    Executes tasks in dependency order with parallel execution.

    Features:
    - Calculates ready set (tasks with no unmet BLOCKS dependencies)
    - Sorts by priority_weight (user override > similarity)
    - Dispatches to agents (respecting 2-task limit)
    - Monitors completion, updates DAG status
    - Repeats until all tasks completed
    """

    MAX_TASKS_PER_AGENT = MAX_TASKS_PER_AGENT  # From neo4j.md agent limits

    # Agent routing based on deliverable type
    ROUTING = {
        DeliverableType.RESEARCH: ("researcher", "Möngke"),
        DeliverableType.ANALYSIS: ("analyst", "Jochi"),
        DeliverableType.CODE: ("developer", "Temüjin"),
        DeliverableType.CONTENT: ("writer", "Chagatai"),
        DeliverableType.STRATEGY: ("analyst", "Jochi"),
        DeliverableType.OPS: ("ops", "Ögedei"),
        DeliverableType.TESTING: ("developer", "Temüjin"),
        DeliverableType.DOCS: ("writer", "Chagatai"),
    }

    def __init__(self, neo4j_client=None, classifier=None, config=None):
        self.neo4j = neo4j_client
        self.classifier = classifier
        self.config = config or DEFAULT_CONFIG

    async def get_ready_tasks(
        self,
        sender_hash: str,
        limit: int = 50
    ) -> List[Task]:
        """
        Find tasks with no unmet BLOCKS dependencies.

        Args:
            sender_hash: User identifier
            limit: Maximum tasks to return

        Returns:
            List of tasks ready for execution
        """
        if self.neo4j:
            return await self.neo4j.get_ready_tasks(sender_hash, limit)

        # Fallback: return empty list
        return []

    def _determine_team_configuration(self, task: Task) -> Dict:
        """Determine team configuration based on complexity classification.

        Args:
            task: Task to classify

        Returns:
            Dict with 'mode' and 'agents' keys
        """
        if self.classifier is None:
            return {"mode": "individual", "agents": self.config.individual_agents}

        try:
            result = self.classifier.classify(task.get("description", ""))
            score = result.get("complexity", 0.0) if isinstance(result, dict) else 0.0
            team_size = complexity_to_team_size(score, self.config)

            agent_counts = {
                "individual": self.config.individual_agents,
                "small_team": self.config.small_team_agents,
                "full_team": self.config.full_team_agents,
            }

            return {
                "mode": team_size,
                "agents": agent_counts.get(team_size, self.config.individual_agents),
            }
        except Exception as e:
            logger.warning(f"Classifier failed for task {task.get('id', '?')}: {e}")
            return {"mode": "individual", "agents": self.config.individual_agents}

    async def execute_ready_set(
        self,
        sender_hash: str,
        max_execution_limit: int = 50
    ) -> ExecutionSummary:
        """
        Dispatch all ready tasks to appropriate agents.

        Args:
            sender_hash: User identifier
            max_execution_limit: Maximum tasks to execute

        Returns:
            Execution summary with counts and errors
        """
        ready = await self.get_ready_tasks(sender_hash, limit=max_execution_limit)

        executed_ids = []
        errors = []

        # Group by required agent type
        by_agent = defaultdict(list)
        for task in ready[:max_execution_limit]:
            # Store team configuration in task metadata
            task["_team_config"] = self._determine_team_configuration(task)
            agent = self._select_best_agent(task)
            by_agent[agent].append(task)

        # Dispatch to agents (respecting 2-task limit)
        for agent_id, tasks in by_agent.items():
            available_slots = self.MAX_TASKS_PER_AGENT - await self._get_current_load(agent_id)

            for task in tasks[:available_slots]:
                try:
                    await self._dispatch_to_agent(task, agent_id)
                    executed_ids.append(task["id"])
                except Exception as e:
                    errors.append({
                        "task_id": task["id"],
                        "error": str(e)
                    })

        return ExecutionSummary(
            executed_count=len(executed_ids),
            error_count=len(errors),
            executed=executed_ids,
            errors=errors
        )

    async def _get_current_load(self, agent_id: str) -> int:
        """Get current task load for an agent."""
        if not self.neo4j:
            return 0

        query = """
        MATCH (t:Task {assigned_to: $agent_id, status: 'in_progress'})
        RETURN count(t) as load
        """

        try:
            # Use async context manager for Neo4j async driver
            async with self.neo4j.session() as session:
                result = await session.run(query, agent_id=agent_id)
                record = await result.single()
                return record["load"] if record else 0
        except Exception:
            return 0

    def _select_best_agent(self, task: Task) -> str:
        """
        Route task to appropriate specialist based on deliverable_type.

        Args:
            task: Task to route

        Returns:
            Agent ID for the task
        """
        deliverable_type_str = task.get("deliverable_type", "analysis")

        try:
            deliverable_type = DeliverableType(deliverable_type_str)
        except ValueError:
            deliverable_type = DeliverableType.ANALYSIS  # Default

        routing = self.ROUTING.get(deliverable_type, ("analyst", "Jochi"))
        return routing[0]  # Return agent ID

    def get_agent_name(self, task: Task) -> str:
        """Get human-readable agent name for a task."""
        deliverable_type_str = task.get("deliverable_type", "analysis")

        try:
            deliverable_type = DeliverableType(deliverable_type_str)
        except ValueError:
            deliverable_type = DeliverableType.ANALYSIS

        routing = self.ROUTING.get(deliverable_type, ("analyst", "Jochi"))
        return routing[1]  # Return agent name

    async def _dispatch_to_agent(
        self,
        task: Task,
        agent_id: str
    ) -> bool:
        """
        Dispatch a task to a specific agent.

        Creates a dispatch record and updates task status.

        Args:
            task: Task to dispatch
            agent_id: Target agent ID

        Returns:
            True if successful
        """
        if not self.neo4j:
            # Simulated dispatch in fallback mode
            return True

        dispatch_query = """
        MATCH (t:Task {id: $task_id})
        MATCH (a:Agent {id: $agent_id})

        // Update task status
        SET t.status = 'in_progress',
            t.assigned_to = $agent_id,
            t.claimed_by = $agent_id

        // Create dispatch record
        CREATE (d:TaskDispatch {
            id: randomUUID(),
            task_id: $task_id,
            agent_id: $agent_id,
            dispatched_at: datetime(),
            status: 'dispatched'
        })

        RETURN d.id as dispatch_id
        """

        try:
            # Use async context manager for Neo4j async driver
            async with self.neo4j.session() as session:
                result = await session.run(dispatch_query, {
                    "task_id": task["id"],
                    "agent_id": agent_id
                })
                record = await result.single()
                return record is not None
        except Exception:
            return False

    async def run_execution_cycle(
        self,
        sender_hash: str,
        max_iterations: int = 100
    ) -> Dict[str, int]:
        """
        Run complete execution cycle until all tasks complete.

        Args:
            sender_hash: User identifier
            max_iterations: Maximum iterations to prevent infinite loops

        Returns:
            Summary of execution
        """
        total_executed = 0
        total_errors = 0
        iteration = 0  # Initialize before loop to avoid UnboundLocalError

        for iteration in range(max_iterations):
            summary = await self.execute_ready_set(sender_hash)

            if summary.executed_count == 0:
                # No more tasks ready to execute
                break

            total_executed += summary.executed_count
            total_errors += summary.error_count

            # Wait a bit for tasks to complete
            await asyncio.sleep(0.5)

        return {
            "total_executed": total_executed,
            "total_errors": total_errors,
            "iterations": iteration + 1
        }

    async def get_execution_summary(
        self,
        sender_hash: str
    ) -> Dict[str, any]:
        """
        Get summary of task execution status.

        Args:
            sender_hash: User identifier

        Returns:
            Execution status summary
        """
        if not self.neo4j:
            return {
                "pending": 0,
                "in_progress": 0,
                "completed": 0,
                "blocked": 0,
                "total": 0
            }

        query = """
        MATCH (t:Task {sender_hash: $sender_hash})
        RETURN t.status as status, count(t) as count
        """

        try:
            # Use async context manager for Neo4j async driver
            async with self.neo4j.session() as session:
                result = await session.run(query, sender_hash=sender_hash)
                status_counts = {record["status"]: record["count"] async for record in result}

                total = sum(status_counts.values())

                return {
                    "pending": status_counts.get("pending", 0),
                    "in_progress": status_counts.get("in_progress", 0),
                    "completed": status_counts.get("completed", 0),
                    "blocked": status_counts.get("blocked", 0),
                    "ready": status_counts.get("ready", 0),
                    "total": total
                }
        except Exception:
            return {
                "pending": 0,
                "in_progress": 0,
                "completed": 0,
                "blocked": 0,
                "total": 0
            }

    def get_routing_info(self, deliverable_type: str) -> tuple:
        """
        Get routing information for a deliverable type.

        Args:
            deliverable_type: Deliverable type string

        Returns:
            Tuple of (agent_id, agent_name)
        """
        try:
            dtype = DeliverableType(deliverable_type)
        except ValueError:
            dtype = DeliverableType.ANALYSIS

        return self.ROUTING.get(dtype, ("analyst", "Jochi"))
