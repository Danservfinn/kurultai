#!/usr/bin/env python3
"""
RQ Worker for Kurultai Async Task Execution.

Processes background tasks from Redis queue.
Run: python -m tools.kurultai.worker
"""

import os
import sys
import logging
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from redis import Redis
from rq import Worker, Queue, Connection

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("kurultai.worker")

# Redis connection
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_conn = Redis.from_url(redis_url)


def execute_task(task_name: str, agent: str, **kwargs) -> dict:
    """
    Execute a task by name.
    
    This function is called by RQ workers to process tasks asynchronously.
    """
    logger.info(f"Executing {agent}/{task_name}")
    
    # Import here to avoid circular imports
    from neo4j import GraphDatabase
    from tools.kurultai.agent_tasks import (
        ogedei_health_check,
        ogedei_file_consistency,
        jochi_memory_curation,
        jochi_smoke_tests,
        jochi_full_tests,
        jochi_curation_deep,
        kublai_status_synthesis,
        chagatai_consolidate,
        mongke_gap_analysis,
        mongke_ordo_research,
        mongke_ecosystem_intelligence,
        notion_sync
    )
    
    # Task registry
    task_registry = {
        'health_check': ogedei_health_check,
        'file_consistency': ogedei_file_consistency,
        'memory_curation': jochi_memory_curation,
        'smoke_tests': jochi_smoke_tests,
        'full_tests': jochi_full_tests,
        'deep_curation': jochi_curation_deep,
        'status_synthesis': kublai_status_synthesis,
        'reflection_consolidation': chagatai_consolidate,
        'knowledge_gap_analysis': mongke_gap_analysis,
        'ordo_sacer_research': mongke_ordo_research,
        'ecosystem_intelligence': mongke_ecosystem_intelligence,
        'notion_sync': notion_sync
    }
    
    handler = task_registry.get(task_name)
    if not handler:
        logger.error(f"Unknown task: {task_name}")
        return {"error": f"Unknown task: {task_name}"}
    
    # Connect to Neo4j
    try:
        driver = GraphDatabase.driver(
            os.getenv('NEO4J_URI', 'bolt://localhost:7687'),
            auth=(
                os.getenv('NEO4J_USER', 'neo4j'),
                os.getenv('NEO4J_PASSWORD', 'myStrongPassword123')
            )
        )
    except Exception as e:
        logger.error(f"Failed to connect to Neo4j: {e}")
        return {"error": str(e)}
    
    # Execute the task
    try:
        import asyncio
        result = asyncio.run(handler(driver))
        logger.info(f"✅ {agent}/{task_name} completed successfully")
        return result
    except Exception as e:
        logger.error(f"❌ {agent}/{task_name} failed: {e}")
        return {"error": str(e)}
    finally:
        driver.close()


if __name__ == '__main__':
    logger.info("🚀 Starting Kurultai RQ Worker")
    logger.info(f"Redis: {redis_url}")
    
    with Connection(redis_conn):
        worker = Worker(
            ['kurultai-tasks', 'default'],
            name='kurultai-worker',
            default_result_ttl=3600  # 1 hour
        )
        worker.work()
