#!/usr/bin/env python3
"""
Unified Heartbeat Master - Single entry point for all agent background tasks.

Runs every 5 minutes via Railway cron or systemd timer.
Each agent registers tasks with frequency predicates.

Usage:
    python heartbeat_master.py --setup       # Register all tasks
    python heartbeat_master.py --cycle       # Run one heartbeat cycle
    python heartbeat_master.py --daemon      # Run continuous daemon mode
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("kurultai.heartbeat")


@dataclass
class HeartbeatTask:
    """A task that runs on heartbeat."""
    name: str
    agent: str  # 'ogedei', 'jochi', 'chagatai', etc.
    frequency_minutes: int  # 5, 15, 60, 360, 1440, 10080, etc.
    max_tokens: int  # Token budget for this task
    handler: Callable[[Any], Awaitable[Dict]]  # async function(driver) -> result
    description: str = ""  # Human-readable description
    enabled: bool = True  # Can be disabled per task

    def should_run(self, cycle_count: int) -> bool:
        """Determine if task should run this cycle."""
        if not self.enabled:
            return False
        # Every 5 min cycle - check if this task's interval aligns
        return cycle_count % (self.frequency_minutes // 5) == 0


@dataclass
class CycleResult:
    """Result of a single heartbeat cycle."""
    cycle_number: int
    started_at: datetime
    completed_at: datetime
    tasks_run: int
    tasks_succeeded: int
    tasks_failed: int
    results: List[Dict[str, Any]] = field(default_factory=list)
    total_tokens: int = 0


class UnifiedHeartbeat:
    """Single heartbeat drives all background tasks."""

    CYCLE_MINUTES = 5
    DEFAULT_TIMEOUT_SECONDS = 60  # Default timeout for task execution

    def __init__(self, neo4j_driver, project_root: Optional[str] = None):
        self.driver = neo4j_driver
        self.project_root = project_root or os.getcwd()
        self.tasks: List[HeartbeatTask] = []
        self.cycle_count = 0
        self._running = False

    def register(self, task: HeartbeatTask) -> 'UnifiedHeartbeat':
        """Register a heartbeat task. Returns self for chaining."""
        self.tasks.append(task)
        logger.info(f"Registered {task.agent}/{task.name} (every {task.frequency_minutes}min, {task.max_tokens} tokens)")
        return self

    def unregister(self, agent: str, task_name: str) -> bool:
        """Unregister a specific task. Returns True if found and removed."""
        for i, task in enumerate(self.tasks):
            if task.agent == agent and task.name == task_name:
                self.tasks.pop(i)
                logger.info(f"Unregistered {agent}/{task_name}")
                return True
        return False

    def get_tasks_for_agent(self, agent: str) -> List[HeartbeatTask]:
        """Get all tasks registered for a specific agent."""
        return [t for t in self.tasks if t.agent == agent]

    def enable_task(self, agent: str, task_name: str) -> bool:
        """Enable a specific task."""
        for task in self.tasks:
            if task.agent == agent and task.name == task_name:
                task.enabled = True
                return True
        return False

    def disable_task(self, agent: str, task_name: str) -> bool:
        """Disable a specific task."""
        for task in self.tasks:
            if task.agent == agent and task.name == task_name:
                task.enabled = False
                return True
        return False

    async def run_cycle(self) -> CycleResult:
        """Execute one heartbeat cycle."""
        self.cycle_count += 1
        cycle_start = datetime.now(timezone.utc)
        started_at = cycle_start

        logger.info(f"=" * 60)
        logger.info(f"Heartbeat cycle #{self.cycle_count} starting")
        logger.info(f"=" * 60)

        results = []
        tasks_run = 0
        tasks_succeeded = 0
        tasks_failed = 0
        total_tokens = 0

        # Sort tasks by agent for consistent ordering
        sorted_tasks = sorted(self.tasks, key=lambda t: (t.agent, t.name))

        for task in sorted_tasks:
            if not task.should_run(self.cycle_count):
                continue

            tasks_run += 1
            task_start = datetime.now(timezone.utc)

            # Calculate timeout based on token budget (~100 tokens/sec)
            timeout = max(30, task.max_tokens / 100)

            try:
                logger.info(f"Running {task.agent}/{task.name} (budget: {task.max_tokens} tokens, timeout: {timeout:.0f}s)")

                result = await asyncio.wait_for(
                    task.handler(self.driver),
                    timeout=timeout
                )

                tasks_succeeded += 1
                total_tokens += result.get("tokens_used", 0)

                results.append({
                    "agent": task.agent,
                    "task": task.name,
                    "status": "success",
                    "started_at": task_start.isoformat(),
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "result": result
                })

                logger.info(f"✓ {task.agent}/{task.name} completed: {result.get('summary', 'OK')}")

            except asyncio.TimeoutError:
                tasks_failed += 1
                logger.error(f"✗ {task.agent}/{task.name} timed out after {timeout:.0f}s")
                results.append({
                    "agent": task.agent,
                    "task": task.name,
                    "status": "timeout",
                    "started_at": task_start.isoformat(),
                    "error": f"Timeout after {timeout:.0f}s"
                })

            except Exception as e:
                tasks_failed += 1
                logger.exception(f"✗ {task.agent}/{task.name} failed: {e}")
                results.append({
                    "agent": task.agent,
                    "task": task.name,
                    "status": "error",
                    "started_at": task_start.isoformat(),
                    "error": str(e)
                })

        cycle_end = datetime.now(timezone.utc)

        cycle_result = CycleResult(
            cycle_number=self.cycle_count,
            started_at=started_at,
            completed_at=cycle_end,
            tasks_run=tasks_run,
            tasks_succeeded=tasks_succeeded,
            tasks_failed=tasks_failed,
            results=results,
            total_tokens=total_tokens
        )

        # Log cycle summary to Neo4j
        await self._log_cycle(cycle_result)

        duration = (cycle_end - started_at).total_seconds()
        logger.info(f"=" * 60)
        logger.info(f"Cycle #{self.cycle_count} complete in {duration:.1f}s")
        logger.info(f"Tasks: {tasks_run} run, {tasks_succeeded} succeeded, {tasks_failed} failed")
        logger.info(f"Total tokens: {total_tokens}")
        logger.info(f"=" * 60)

        return cycle_result

    async def _log_cycle(self, result: CycleResult):
        """Log heartbeat cycle results to Neo4j."""
        try:
            cypher = """
            CREATE (hc:HeartbeatCycle {
                id: $id,
                cycle_number: $cycle_number,
                started_at: datetime($started_at),
                completed_at: datetime($completed_at),
                tasks_run: $tasks_run,
                tasks_succeeded: $tasks_succeeded,
                tasks_failed: $tasks_failed,
                total_tokens: $total_tokens,
                duration_seconds: $duration_seconds
            })
            WITH hc
            UNWIND $results AS result
            CREATE (tr:TaskResult {
                agent: result.agent,
                task_name: result.task,
                status: result.status,
                started_at: datetime(result.started_at),
                summary: COALESCE(result.result.summary, result.error, 'Unknown')
            })
            CREATE (hc)-[:HAS_RESULT]->(tr)
            RETURN hc.id AS cycle_id
            """

            duration = (result.completed_at - result.started_at).total_seconds()

            with self.driver.session() as session:
                session.run(cypher,
                    id=f"cycle-{result.cycle_number}-{int(result.started_at.timestamp())}",
                    cycle_number=result.cycle_number,
                    started_at=result.started_at.isoformat(),
                    completed_at=result.completed_at.isoformat(),
                    tasks_run=result.tasks_run,
                    tasks_succeeded=result.tasks_succeeded,
                    tasks_failed=result.tasks_failed,
                    total_tokens=result.total_tokens,
                    duration_seconds=duration,
                    results=result.results
                )

        except Exception as e:
            logger.error(f"Failed to log cycle to Neo4j: {e}")
            # Don't let logging failure break the cycle

    async def run_daemon(self, shutdown_event: Optional[asyncio.Event] = None):
        """Run continuous daemon mode."""
        self._running = True
        logger.info("Starting unified heartbeat daemon")

        event = shutdown_event or asyncio.Event()

        while self._running and not event.is_set():
            try:
                await self.run_cycle()
            except Exception as e:
                logger.exception(f"Cycle failed: {e}")

            # Wait for next cycle (5 minutes)
            try:
                await asyncio.wait_for(event.wait(), timeout=self.CYCLE_MINUTES * 60)
            except asyncio.TimeoutError:
                continue  # Normal cycle interval

        logger.info("Heartbeat daemon stopped")

    def stop(self):
        """Stop the daemon."""
        self._running = False


# Global instance for singleton pattern
_heartbeat: Optional[UnifiedHeartbeat] = None


def get_heartbeat(neo4j_driver=None, project_root: Optional[str] = None) -> UnifiedHeartbeat:
    """Get or create global heartbeat instance."""
    global _heartbeat
    if _heartbeat is None:
        if neo4j_driver is None:
            raise ValueError("Neo4j driver required for initial heartbeat creation")
        _heartbeat = UnifiedHeartbeat(neo4j_driver, project_root)
    return _heartbeat


def reset_heartbeat():
    """Reset global heartbeat instance (for testing)."""
    global _heartbeat
    _heartbeat = None


# ============================================================================
# CLI Entry Point
# ============================================================================

def main():
    """CLI entry point for unified heartbeat."""
    parser = argparse.ArgumentParser(
        description="Unified Heartbeat Master for Kurultai",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Register all tasks (run once at startup)
  python heartbeat_master.py --setup

  # Run one cycle (for cron/systemd)
  python heartbeat_master.py --cycle

  # Run continuous daemon
  python heartbeat_master.py --daemon

  # List all registered tasks
  python heartbeat_master.py --list-tasks

  # Run tasks for specific agent only
  python heartbeat_master.py --cycle --agent jochi
        """
    )

    parser.add_argument(
        "--setup",
        action="store_true",
        help="Register all agent tasks (run once at startup)"
    )

    parser.add_argument(
        "--cycle",
        action="store_true",
        help="Run one heartbeat cycle"
    )

    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run continuous daemon mode"
    )

    parser.add_argument(
        "--list-tasks",
        action="store_true",
        help="List all registered tasks"
    )

    parser.add_argument(
        "--agent",
        type=str,
        help="Filter to specific agent (e.g., jochi, ogedei)"
    )

    parser.add_argument(
        "--project-root",
        type=str,
        default=os.getcwd(),
        help="Project root directory (default: CWD)"
    )

    parser.add_argument(
        "--neo4j-uri",
        type=str,
        default=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        help="Neo4j URI"
    )

    parser.add_argument(
        "--neo4j-user",
        type=str,
        default=os.getenv("NEO4J_USER", "neo4j"),
        help="Neo4j username"
    )

    parser.add_argument(
        "--neo4j-password",
        type=str,
        default=os.getenv("NEO4J_PASSWORD"),
        help="Neo4j password"
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )

    args = parser.parse_args()

    # Validate Neo4j password
    if not args.neo4j_password:
        logger.error("NEO4J_PASSWORD not set. Use --neo4j-password or set env var.")
        sys.exit(1)

    # Connect to Neo4j
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(
            args.neo4j_uri,
            auth=(args.neo4j_user, args.neo4j_password)
        )
        # Test connection
        with driver.session() as session:
            session.run("RETURN 1")
        logger.info(f"Connected to Neo4j at {args.neo4j_uri}")
    except Exception as e:
        logger.error(f"Failed to connect to Neo4j: {e}")
        sys.exit(1)

    try:
        if args.setup:
            # Import and register all tasks
            from .agent_tasks import register_all_tasks
            hb = get_heartbeat(driver, args.project_root)
            asyncio.run(register_all_tasks(hb))

            if args.json:
                print(json.dumps({
                    "status": "success",
                    "tasks_registered": len(hb.tasks),
                    "tasks": [{"agent": t.agent, "name": t.name, "frequency": t.frequency_minutes} for t in hb.tasks]
                }, indent=2))
            else:
                print(f"✓ Registered {len(hb.tasks)} tasks")
                for task in hb.tasks:
                    print(f"  - {task.agent}/{task.name}: every {task.frequency_minutes}min ({task.max_tokens} tokens)")

        elif args.list_tasks:
            hb = get_heartbeat(driver, args.project_root)

            # Import to ensure tasks are registered
            try:
                from .agent_tasks import register_all_tasks
                asyncio.run(register_all_tasks(hb))
            except Exception:
                pass  # May fail if not set up yet

            tasks = hb.tasks
            if args.agent:
                tasks = [t for t in tasks if t.agent == args.agent]

            if args.json:
                print(json.dumps({
                    "tasks": [{"agent": t.agent, "name": t.name, "frequency": t.frequency_minutes,
                              "tokens": t.max_tokens, "enabled": t.enabled, "description": t.description} for t in tasks]
                }, indent=2))
            else:
                print(f"Registered Tasks ({len(tasks)}):")
                print("-" * 80)
                for task in sorted(tasks, key=lambda t: (t.agent, t.name)):
                    status = "✓" if task.enabled else "✗"
                    print(f"{status} {task.agent:12} | {task.name:30} | {task.frequency_minutes:5}min | {task.max_tokens:4} tokens")
                    if task.description:
                        print(f"  {task.description}")

        elif args.cycle:
            hb = get_heartbeat(driver, args.project_root)

            # Import and register tasks if not already done
            from .agent_tasks import register_all_tasks
            if len(hb.tasks) == 0:
                asyncio.run(register_all_tasks(hb))

            # Filter to specific agent if requested
            if args.agent:
                original_tasks = hb.tasks
                hb.tasks = [t for t in hb.tasks if t.agent == args.agent]
                logger.info(f"Filtered to {len(hb.tasks)} tasks for agent '{args.agent}'")

            result = asyncio.run(hb.run_cycle())

            if args.json:
                print(json.dumps({
                    "cycle_number": result.cycle_number,
                    "started_at": result.started_at.isoformat(),
                    "completed_at": result.completed_at.isoformat(),
                    "duration_seconds": (result.completed_at - result.started_at).total_seconds(),
                    "tasks_run": result.tasks_run,
                    "tasks_succeeded": result.tasks_succeeded,
                    "tasks_failed": result.tasks_failed,
                    "total_tokens": result.total_tokens,
                    "results": result.results
                }, indent=2, default=str))
            else:
                duration = (result.completed_at - result.started_at).total_seconds()
                print(f"\nCycle #{result.cycle_number} complete in {duration:.1f}s")
                print(f"Tasks: {result.tasks_run} run, {result.tasks_succeeded} succeeded, {result.tasks_failed} failed")

                if result.tasks_failed > 0:
                    sys.exit(1)

        elif args.daemon:
            hb = get_heartbeat(driver, args.project_root)

            # Import and register tasks
            from .agent_tasks import register_all_tasks
            if len(hb.tasks) == 0:
                asyncio.run(register_all_tasks(hb))

            # Filter to specific agent if requested
            if args.agent:
                hb.tasks = [t for t in hb.tasks if t.agent == args.agent]
                logger.info(f"Filtered to {len(hb.tasks)} tasks for agent '{args.agent}'")

            # Setup signal handlers
            import signal

            shutdown_event = asyncio.Event()

            def handle_signal(signum, frame):
                logger.info(f"Received signal {signum}, shutting down...")
                shutdown_event.set()

            signal.signal(signal.SIGTERM, handle_signal)
            signal.signal(signal.SIGINT, handle_signal)

            # Run daemon
            asyncio.run(hb.run_daemon(shutdown_event))

        else:
            parser.print_help()

    finally:
        driver.close()


if __name__ == "__main__":
    main()
