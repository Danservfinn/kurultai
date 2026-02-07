#!/usr/bin/env python3
"""
Infrastructure heartbeat sidecar for Kurultai multi-agent system.

Writes Agent.infra_heartbeat every 30 seconds for all 6 agents,
proving the gateway process is alive. Read by Ogedei's failover
detection (infra_heartbeat stale >120s = gateway dead).

Uses a single batched UNWIND query per cycle. Includes circuit
breaker: 3 consecutive failures -> 60s cooldown.
"""

import os
import signal
import sys
import time
import logging
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [heartbeat-sidecar] %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# All 6 Kurultai agents
AGENT_NAMES = ["main", "researcher", "writer", "developer", "analyst", "ops"]

HEARTBEAT_INTERVAL = 30  # seconds
CIRCUIT_BREAKER_THRESHOLD = 3  # consecutive failures before cooldown
CIRCUIT_BREAKER_COOLDOWN = 60  # seconds

_shutdown = False


def _handle_signal(signum, frame):
    global _shutdown
    logger.info(f"Received signal {signum}, shutting down...")
    _shutdown = True


def write_heartbeats(driver):
    """Write infra_heartbeat for all agents in a single transaction."""
    cypher = """
    UNWIND $agents AS agent_name
    MERGE (a:Agent {name: agent_name})
    SET a.infra_heartbeat = datetime($now)
    RETURN count(a) AS updated
    """
    now = datetime.now(timezone.utc).isoformat()

    with driver.session() as session:
        result = session.run(cypher, agents=AGENT_NAMES, now=now)
        record = result.single()
        return record["updated"] if record else 0


def main():
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD")

    if not password:
        logger.error("NEO4J_PASSWORD not set, exiting")
        sys.exit(1)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(uri, auth=(user, password))

    logger.info(f"Starting infra heartbeat sidecar (interval={HEARTBEAT_INTERVAL}s, agents={len(AGENT_NAMES)})")

    consecutive_failures = 0

    try:
        while not _shutdown:
            try:
                count = write_heartbeats(driver)
                logger.info(f"Heartbeat written for {count} agents")
                consecutive_failures = 0
            except Exception as e:
                consecutive_failures += 1
                logger.error(f"Heartbeat write failed ({consecutive_failures}/{CIRCUIT_BREAKER_THRESHOLD}): {e}")

                if consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
                    logger.warning(f"Circuit breaker open, cooling down {CIRCUIT_BREAKER_COOLDOWN}s")
                    for _ in range(CIRCUIT_BREAKER_COOLDOWN):
                        if _shutdown:
                            break
                        time.sleep(1)
                    consecutive_failures = 0
                    continue

            for _ in range(HEARTBEAT_INTERVAL):
                if _shutdown:
                    break
                time.sleep(1)
    finally:
        driver.close()
        logger.info("Heartbeat sidecar stopped")


if __name__ == "__main__":
    main()
