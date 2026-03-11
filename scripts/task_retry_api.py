#!/usr/bin/env python3
"""
task_retry_api.py — HTTP API endpoints for task retry functionality.

Integrates with squad_chat_server.py or runs standalone.
Provides REST endpoints for retrying failed tasks.

Usage:
    # Standalone (development)
    python3 task_retry_api.py --port 8767

    # Integrated with squad_chat_server
    from task_retry_api import setup_routes
    app = web.Application()
    setup_routes(app)
"""

import argparse
import asyncio
import logging
from aiohttp import web
from typing import Optional

from task_retry_service import TaskRetryService, logger

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
api_logger = logging.getLogger("task-retry-api")

# Initialize service
retry_service = TaskRetryService()


def json_response(data: dict, status: int = 200):
    """Create JSON response."""
    return web.json_response(data, status=status)


def json_error(message: str, status: int = 400) -> web.Response:
    """Create error response."""
    return web.json_response({"success": False, "error": message}, status=status)


async def handle_list_failed(request: web.Request) -> web.Response:
    """GET /api/tasks/failed - List all failed tasks."""
    agent_filter = request.query.get("agent")

    try:
        tasks = retry_service.list_failed_tasks(agent_filter)
        return json_response({
            "tasks": [t.to_dict() for t in tasks],
            "total": len(tasks)
        })
    except Exception as e:
        api_logger.error(f"Error listing failed tasks: {e}")
        return json_error(f"Internal error: {e}", 500)


async def handle_retry_single(request: web.Request) -> web.Response:
    """POST /api/tasks/retry - Retry a single failed task."""
    try:
        data = await request.json()

        agent = data.get("agent")
        task_file = data.get("task_file")
        clear_errors = data.get("clear_errors", False)
        reason = data.get("reason", "manual_retry")

        # Validate required fields
        if not agent or not task_file:
            return json_error("Missing required fields: agent, task_file", 400)

        # Validate agent
        if not retry_service.validate_agent(agent):
            return json_error(f"Invalid agent: {agent}", 400)

        # Check if task is actually failed
        if not retry_service.is_failed_task(task_file):
            return json_error("Task is not in failed state (must end with .failed.done.md)", 400)

        # Perform retry
        result = retry_service.retry_task(agent, task_file, clear_errors, reason)

        if result.success:
            return json_response({
                "success": True,
                "task": result.to_dict(),
                "message": "Task queued for retry"
            })
        else:
            return json_error(result.error or "Retry failed", 500)

    except Exception as e:
        api_logger.error(f"Error in retry_single: {e}")
        return json_error(f"Internal error: {e}", 500)


async def handle_retry_bulk(request: web.Request) -> web.Response:
    """POST /api/tasks/retry/bulk - Retry multiple tasks."""
    try:
        data = await request.json()

        tasks = data.get("tasks", [])
        clear_errors = data.get("clear_errors", False)
        reason = data.get("reason", "bulk_manual_retry")

        if not tasks:
            return json_error("No tasks provided", 400)

        results = []
        queued = 0
        failed_count = 0

        for task_spec in tasks:
            agent = task_spec.get("agent")
            task_file = task_spec.get("task_file")

            if not agent or not task_file:
                results.append({
                    "success": False,
                    "error": "Missing agent or task_file"
                })
                failed_count += 1
                continue

            result = retry_service.retry_task(agent, task_file, clear_errors, reason)
            results.append({
                "task_file": task_file,
                "success": result.success,
                "error": result.error
            })

            if result.success:
                queued += 1
            else:
                failed_count += 1

        return json_response({
            "success": True,
            "results": results,
            "queued": queued,
            "failed": failed_count
        })

    except Exception as e:
        api_logger.error(f"Error in retry_bulk: {e}")
        return json_error(f"Internal error: {e}", 500)


async def handle_retry_agent(request: web.Request) -> web.Response:
    """POST /api/tasks/retry/agent/:agent - Retry all failed tasks for an agent."""
    agent = request.match_info.get("agent")
    clear_errors = bool(request.query.get("clear_errors", "false").lower() == "true")

    if not agent:
        return json_error("Agent not specified", 400)

    if not retry_service.validate_agent(agent):
        return json_error(f"Invalid agent: {agent}", 400)

    try:
        result = retry_service.retry_agent_tasks(agent, clear_errors, "bulk_agent_retry")
        return json_response(result)
    except Exception as e:
        api_logger.error(f"Error in retry_agent: {e}")
        return json_error(f"Internal error: {e}", 500)


async def handle_retry_all(request: web.Request) -> web.Response:
    """POST /api/tasks/retry/all - Retry all failed tasks across all agents."""
    clear_errors = bool(request.query.get("clear_errors", "false").lower() == "true")

    try:
        result = retry_service.retry_all_tasks(clear_errors, "bulk_all_retry")
        return json_response(result)
    except Exception as e:
        api_logger.error(f"Error in retry_all: {e}")
        return json_error(f"Internal error: {e}", 500)


async def handle_status(request: web.Request) -> web.Response:
    """GET /api/tasks/retry/status - Health check for retry service."""
    return json_response({
        "status": "healthy",
        "service": "task-retry",
        "valid_agents": list(retry_service.VALID_AGENTS)
    })


async def handle_stats(request: web.Request) -> web.Response:
    """GET /api/tasks/stats - Get task statistics by status."""
    try:
        failed_tasks = retry_service.list_failed_tasks()

        # Count by agent
        by_agent = {}
        by_priority = {"critical": 0, "high": 0, "normal": 0, "low": 0}

        for task in failed_tasks:
            by_agent[task.agent] = by_agent.get(task.agent, 0) + 1
            if task.priority in by_priority:
                by_priority[task.priority] += 1

        return json_response({
            "failed_total": len(failed_tasks),
            "by_agent": by_agent,
            "by_priority": by_priority
        })
    except Exception as e:
        api_logger.error(f"Error in stats: {e}")
        return json_error(f"Internal error: {e}", 500)


def setup_routes(app: web.Application, prefix: str = "/api/tasks"):
    """Setup retry API routes on an existing aiohttp Application.

    Args:
        app: The aiohttp Application instance
        prefix: URL prefix for all routes (default: /api/tasks)

    Usage:
        from aiohttp import web
        from task_retry_api import setup_routes

        app = web.Application()
        setup_routes(app)
    """
    routes = [
        # Failed task listing
        web.get(f"{prefix}/failed", handle_list_failed),

        # Single task retry
        web.post(f"{prefix}/retry", handle_retry_single),

        # Bulk operations
        web.post(f"{prefix}/retry/bulk", handle_retry_bulk),
        web.post(f"{prefix}/retry/agent/{{agent}}", handle_retry_agent),
        web.post(f"{prefix}/retry/all", handle_retry_all),

        # Status and stats
        web.get(f"{prefix}/retry/status", handle_status),
        web.get(f"{prefix}/stats", handle_stats),
    ]

    app.router.add_routes(routes)
    api_logger.info(f"Registered {len(routes)} task retry routes at prefix: {prefix}")


def create_app() -> web.Application:
    """Create a standalone aiohttp Application for the retry API."""
    app = web.Application()
    setup_routes(app)
    return app


async def run_server(port: int = 8767, host: str = "localhost"):
    """Run the retry API server."""
    app = create_app()

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()

    api_logger.info(f"Task Retry API listening on http://{host}:{port}")
    api_logger.info("Available endpoints:")
    api_logger.info(f"  GET    http://{host}:{port}/api/tasks/failed")
    api_logger.info(f"  POST   http://{host}:{port}/api/tasks/retry")
    api_logger.info(f"  POST   http://{host}:{port}/api/tasks/retry/bulk")
    api_logger.info(f"  POST   http://{host}:{port}/api/tasks/retry/agent/{{agent}}")
    api_logger.info(f"  POST   http://{host}:{port}/api/tasks/retry/all")
    api_logger.info(f"  GET    http://{host}:{port}/api/tasks/stats")
    api_logger.info(f"  GET    http://{host}:{port}/api/tasks/retry/status")

    return runner


def main():
    """Run the retry API server standalone."""
    parser = argparse.ArgumentParser(description="Task Retry API Server")
    parser.add_argument("--port", type=int, default=8767, help="HTTP port")
    parser.add_argument("--host", default="localhost", help="Host to bind to")
    parser.add_argument("--daemon", action="store_true", help="Run as daemon")
    args = parser.parse_args()

    async def run():
        runner = await run_server(args.port, args.host)
        try:
            # Keep running
            while True:
                await asyncio.sleep(3600)
        finally:
            await runner.cleanup()

    if args.daemon:
        import daemon
        with daemon.DaemonContext():
            asyncio.run(run())
    else:
        asyncio.run(run())


if __name__ == "__main__":
    main()
