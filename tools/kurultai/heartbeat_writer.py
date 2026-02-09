#!/usr/bin/env python3
"""
Heartbeat Writer Sidecar for Kurultai Multi-Agent System

Writes infra_heartbeat timestamp every 30 seconds to Neo4j for all 6 Kurultai agents.
This sidecar runs as a background process alongside the main application.

Environment Variables:
    NEO4J_URI: Neo4j connection URI (default: bolt://localhost:7687)
    NEO4J_USER: Neo4j username (default: neo4j)
    NEO4J_PASSWORD: Neo4j password (required)
    HEARTBEAT_INTERVAL: Seconds between writes (default: 30)
    CIRCUIT_BREAKER_THRESHOLD: Failures before pause (default: 3)
    CIRCUIT_BREAKER_PAUSE: Seconds to pause after threshold (default: 60)
    LOG_LEVEL: Logging level (default: INFO)
"""

import os
import sys
import time
import signal
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

# Lazy import neo4j to handle import errors gracefully
try:
    from neo4j import GraphDatabase
    from neo4j.exceptions import ServiceUnavailable, Neo4jError, TransientError
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False
    GraphDatabase = None
    ServiceUnavailable = Exception
    Neo4jError = Exception
    TransientError = Exception

# Configure logging
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("kurultai.heartbeat_writer")

# Configuration constants
NEO4J_URI = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
NEO4J_USER = os.environ.get('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.environ.get('NEO4J_PASSWORD')
HEARTBEAT_INTERVAL = int(os.environ.get('HEARTBEAT_INTERVAL', '30'))
CIRCUIT_BREAKER_THRESHOLD = int(os.environ.get('CIRCUIT_BREAKER_THRESHOLD', '3'))
CIRCUIT_BREAKER_PAUSE = int(os.environ.get('CIRCUIT_BREAKER_PAUSE', '60'))

# All 6 Kurultai agents
KURULTAI_AGENTS = ['Kublai', 'Möngke', 'Chagatai', 'Temüjin', 'Jochi', 'Ögedei']


class CircuitBreakerOpen(Exception):
    """Raised when circuit breaker is open."""
    pass


class HeartbeatWriter:
    """
    Writes infra_heartbeat timestamps to all Kurultai agents in Neo4j.
    
    Features:
    - Writes heartbeat every 30 seconds (configurable)
    - Creates Agent nodes if they don't exist
    - Circuit breaker: pauses after 3 consecutive failures
    - Graceful shutdown on SIGTERM/SIGINT
    """
    
    def __init__(self):
        self.driver: Optional[Any] = None
        self.failure_count: int = 0
        self.circuit_open: bool = False
        self.circuit_reset_time: Optional[datetime] = None
        self._shutdown_requested: bool = False
        
        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)
        
        logger.info(f"HeartbeatWriter initialized (interval: {HEARTBEAT_INTERVAL}s)")
    
    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signals gracefully."""
        sig_name = 'SIGTERM' if signum == signal.SIGTERM else 'SIGINT'
        logger.info(f"Received {sig_name}, initiating graceful shutdown...")
        self._shutdown_requested = True
    
    def connect(self) -> bool:
        """
        Connect to Neo4j.
        
        Returns:
            True if connected successfully, False otherwise
        """
        if not NEO4J_AVAILABLE:
            logger.error("Neo4j driver not available - cannot connect")
            return False
            
        if not NEO4J_PASSWORD:
            logger.error("NEO4J_PASSWORD environment variable is required")
            return False
            
        try:
            self.driver = GraphDatabase.driver(
                NEO4J_URI,
                auth=(NEO4J_USER, NEO4J_PASSWORD)
            )
            self.driver.verify_connectivity()
            logger.info(f"Connected to Neo4j at {NEO4J_URI}")
            return True
        except ServiceUnavailable as e:
            logger.error(f"Neo4j service unavailable: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            return False
    
    def _check_circuit_breaker(self) -> bool:
        """
        Check if circuit breaker allows operation.
        
        Returns:
            True if operation allowed, False if circuit is open
        """
        if not self.circuit_open:
            return True
            
        # Check if circuit should reset
        if self.circuit_reset_time and datetime.now(timezone.utc) >= self.circuit_reset_time:
            logger.info("Circuit breaker reset, resuming heartbeats")
            self.circuit_open = False
            self.failure_count = 0
            self.circuit_reset_time = None
            return True
            
        logger.warning(f"Circuit breaker open, skipping heartbeat cycle (resets at {self.circuit_reset_time.isoformat()})")
        return False
    
    def _open_circuit(self):
        """Open the circuit breaker after threshold failures."""
        self.circuit_open = True
        self.circuit_reset_time = datetime.now(timezone.utc) + timedelta(seconds=CIRCUIT_BREAKER_PAUSE)
        logger.critical(
            f"Circuit breaker triggered - pausing heartbeats for {CIRCUIT_BREAKER_PAUSE}s "
            f"(will reset at {self.circuit_reset_time.isoformat()})"
        )
    
    def write_heartbeat(self, agent_name: str) -> bool:
        """
        Write infra_heartbeat for a single agent.
        
        Args:
            agent_name: Name of the agent to update
            
        Returns:
            True if successful, False otherwise
        """
        timestamp = datetime.now(timezone.utc)
        
        cypher = """
        MERGE (a:Agent {name: $agent_name})
        ON CREATE SET a.created_at = $timestamp
        SET a.infra_heartbeat = $timestamp
        RETURN a.name as agent
        """
        
        try:
            with self.driver.session() as session:
                result = session.run(cypher, agent_name=agent_name, timestamp=timestamp)
                record = result.single()
                if record:
                    logger.debug(f"infra_heartbeat written for {agent_name}: {timestamp.isoformat()}")
                    return True
                return False
        except (ServiceUnavailable, Neo4jError, TransientError) as e:
            logger.error(f"Failed to write heartbeat for {agent_name}: {e}")
            raise
    
    def write_all_heartbeats(self) -> bool:
        """
        Write heartbeats for all Kurultai agents.
        
        Returns:
            True if all heartbeats written successfully, False otherwise
        """
        if not self._check_circuit_breaker():
            return False
            
        if not self.driver:
            logger.error("Neo4j driver not initialized")
            self.failure_count += 1
            if self.failure_count >= CIRCUIT_BREAKER_THRESHOLD:
                self._open_circuit()
            return False
        
        try:
            success_count = 0
            for agent in KURULTAI_AGENTS:
                if self.write_heartbeat(agent):
                    success_count += 1
            
            # Reset failure count on success
            if success_count == len(KURULTAI_AGENTS):
                self.failure_count = 0
                logger.info(f"infra_heartbeat written for {success_count} agents")
                return True
            else:
                logger.warning(f"Partial success: {success_count}/{len(KURULTAI_AGENTS)} heartbeats written")
                self.failure_count += 1
                if self.failure_count >= CIRCUIT_BREAKER_THRESHOLD:
                    self._open_circuit()
                return False
                
        except (ServiceUnavailable, Neo4jError, TransientError) as e:
            self.failure_count += 1
            logger.error(f"Heartbeat write failed ({self.failure_count}/{CIRCUIT_BREAKER_THRESHOLD}): {e}")
            
            if self.failure_count >= CIRCUIT_BREAKER_THRESHOLD:
                self._open_circuit()
            return False
    
    def run(self):
        """Main loop - write heartbeats every interval until shutdown."""
        logger.info(f"Starting heartbeat writer main loop (interval: {HEARTBEAT_INTERVAL}s)")
        logger.info(f"Monitoring agents: {', '.join(KURULTAI_AGENTS)}")
        
        # Track consecutive successful cycles for health metrics
        consecutive_successes = 0
        
        while not self._shutdown_requested:
            cycle_start = time.time()
            
            try:
                if self.write_all_heartbeats():
                    consecutive_successes += 1
                else:
                    consecutive_successes = 0
            except Exception as e:
                logger.exception(f"Unexpected error in heartbeat cycle: {e}")
                consecutive_successes = 0
            
            # Calculate sleep time to maintain interval
            elapsed = time.time() - cycle_start
            sleep_time = max(0, HEARTBEAT_INTERVAL - elapsed)
            
            # Sleep in small increments to check for shutdown
            slept = 0
            while slept < sleep_time and not self._shutdown_requested:
                sleep_chunk = min(0.5, sleep_time - slept)
                time.sleep(sleep_chunk)
                slept += sleep_chunk
        
        logger.info(f"Heartbeat writer stopped after {consecutive_successes} consecutive successful cycles")
    
    def close(self):
        """Close Neo4j connection gracefully."""
        if self.driver:
            try:
                self.driver.close()
                logger.info("Neo4j connection closed")
            except Exception as e:
                logger.warning(f"Error closing Neo4j connection: {e}")


def main():
    """Main entry point."""
    logger.info("=" * 60)
    logger.info("Kurultai Heartbeat Writer Sidecar Starting")
    logger.info("=" * 60)
    logger.info(f"Configuration:")
    logger.info(f"  NEO4J_URI: {NEO4J_URI}")
    logger.info(f"  NEO4J_USER: {NEO4J_USER}")
    logger.info(f"  HEARTBEAT_INTERVAL: {HEARTBEAT_INTERVAL}s")
    logger.info(f"  CIRCUIT_BREAKER_THRESHOLD: {CIRCUIT_BREAKER_THRESHOLD}")
    logger.info(f"  CIRCUIT_BREAKER_PAUSE: {CIRCUIT_BREAKER_PAUSE}s")
    logger.info(f"  LOG_LEVEL: {LOG_LEVEL}")
    
    writer = HeartbeatWriter()
    
    # Connect to Neo4j
    if not writer.connect():
        logger.error("Failed to connect to Neo4j, exiting")
        sys.exit(1)
    
    try:
        writer.run()
    except Exception as e:
        logger.exception(f"Fatal error in heartbeat writer: {e}")
        sys.exit(1)
    finally:
        writer.close()
        logger.info("Heartbeat writer shutdown complete")


if __name__ == '__main__':
    main()
