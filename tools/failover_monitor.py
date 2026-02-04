"""
Kublai Failover Monitor - Failover monitoring system for the OpenClaw multi-agent system.

This module provides the FailoverMonitor class for monitoring Kublai's health and
activating failover to Ögedei when Kublai is unavailable.

Named after the failover monitoring capabilities that enable Ögedei to act as
emergency router when Kublai is unresponsive.
"""

import logging
import threading
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any

from neo4j.exceptions import Neo4jError

# Configure logging
logger = logging.getLogger(__name__)


class FailoverError(Exception):
    """Raised when a failover operation fails."""
    pass


class FailoverMonitor:
    """
    Monitors Kublai's health and activates failover to Ögedei.

    Failover Triggers:
    - Kublai model returns 429 (rate limit)
    - Kublai process crashes or hangs
    - Kublai health check fails 3 consecutive times

    Emergency Router Responsibilities (Ögedei):
    1. Detection - Monitor Kublai's health via heartbeat/last_active timestamp
    2. Activation - Assume router role when Kublai unresponsive (60s threshold)
    3. Limited Routing - Handle critical messages only, queue non-critical
    4. Notification - Alert admin when failover activated
    5. Recovery - Return control to Kublai when healthy

    Attributes:
        memory: OperationalMemory instance for persistence
        FAILOVER_THRESHOLD_SECONDS: Seconds of inactivity before failover (default: 60)
        MAX_CONSECUTIVE_FAILURES: Failover after N consecutive failures (default: 3)
    """

    # Configuration constants
    FAILOVER_THRESHOLD_SECONDS = 60
    MAX_CONSECUTIVE_FAILURES = 3
    CHECK_INTERVAL_SECONDS = 30
    RECOVERY_HEARTBEATS_REQUIRED = 3

    # Agent IDs
    KUBLAI_AGENT_ID = "main"
    OGEDEI_AGENT_ID = "ops"

    def __init__(self, memory: Any, check_interval_seconds: int = None):
        """
        Initialize the FailoverMonitor.

        Args:
            memory: OperationalMemory instance for Neo4j persistence
            check_interval_seconds: Health check interval in seconds
        """
        self.memory = memory
        self.check_interval = check_interval_seconds or self.CHECK_INTERVAL_SECONDS

        # Thread-safe state management
        self._state_lock = threading.RLock()
        self._kublai_failures = 0
        self._failover_active = False
        self._current_failover_event_id: Optional[str] = None
        self._consecutive_healthy_checks = 0
        self._messages_routed_during_failover = 0

        # Background monitoring
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_monitoring = threading.Event()
        self._last_check: Optional[datetime] = None

        logger.info(f"FailoverMonitor initialized (threshold: {self.FAILOVER_THRESHOLD_SECONDS}s)")

    def _generate_id(self) -> str:
        """Generate a unique ID using the memory's method or fallback to uuid."""
        if hasattr(self.memory, '_generate_id'):
            return self.memory._generate_id()
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

    def update_heartbeat(self, agent: str) -> None:
        """
        Update agent's heartbeat timestamp.

        Creates or updates an AgentHeartbeat node with the current timestamp.

        Args:
            agent: Agent name to update heartbeat for

        Raises:
            FailoverError: If heartbeat update fails
        """
        heartbeat_id = self._generate_id()
        now = self._now()

        cypher = """
        MERGE (h:AgentHeartbeat {agent: $agent})
        SET h.last_seen = $last_seen,
            h.created_at = coalesce(h.created_at, $last_seen),
            h.id = coalesce(h.id, $heartbeat_id)
        RETURN h.agent as agent
        """

        with self._session() as session:
            if session is None:
                logger.warning(f"Fallback mode: Heartbeat update simulated for {agent}")
                return

            try:
                result = session.run(
                    cypher,
                    agent=agent,
                    last_seen=now,
                    heartbeat_id=heartbeat_id
                )
                record = result.single()
                if record:
                    logger.debug(f"Heartbeat updated for agent: {agent}")
                else:
                    raise FailoverError(f"Heartbeat update failed for agent: {agent}")
            except Neo4jError as e:
                logger.error(f"Failed to update heartbeat for {agent}: {e}")
                raise FailoverError(f"Failed to update heartbeat: {e}")

    def is_agent_available(self, agent: str) -> bool:
        """
        Check if agent is available (responded within threshold).

        Args:
            agent: Agent name to check availability for

        Returns:
            True if agent has responded within FAILOVER_THRESHOLD_SECONDS
        """
        cypher = """
        MATCH (h:AgentHeartbeat {agent: $agent})
        RETURN h.last_seen as last_seen
        """

        with self._session() as session:
            if session is None:
                # In fallback mode, assume agent is available
                return True

            try:
                result = session.run(cypher, agent=agent)
                record = result.single()

                if record and record.get("last_seen"):
                    last_seen = record["last_seen"]
                    # Handle Neo4j datetime format
                    if hasattr(last_seen, 'to_native'):
                        last_seen = last_seen.to_native()

                    time_since = (self._now() - last_seen).total_seconds()
                    return time_since <= self.FAILOVER_THRESHOLD_SECONDS

                return False

            except Neo4jError as e:
                logger.error(f"Failed to check agent availability for {agent}: {e}")
                return False

    def should_activate_failover(self) -> bool:
        """
        Determine if failover should be activated.

        Checks:
        1. Kublai's heartbeat is stale (beyond FAILOVER_THRESHOLD_SECONDS)
        2. Consecutive failures have reached MAX_CONSECUTIVE_FAILURES
        3. Failover is not already active

        Returns:
            True if failover should be activated
        """
        # Don't activate if already in failover
        with self._state_lock:
            if self._failover_active:
                return False

        # Check Kublai availability
        kublai_available = self.is_agent_available(self.KUBLAI_AGENT_ID)

        if not kublai_available:
            with self._state_lock:
                self._kublai_failures += 1
                current_failures = self._kublai_failures
                should_failover = self._kublai_failures >= self.MAX_CONSECUTIVE_FAILURES

                logger.warning(
                    f"Kublai unavailable, failure count: {current_failures}/"
                    f"{self.MAX_CONSECUTIVE_FAILURES}"
                )

                return should_failover

        # Kublai is available, reset failure counter
        with self._state_lock:
            if self._kublai_failures > 0:
                logger.info("Kublai recovered, resetting failure counter")
                self._kublai_failures = 0

        return False

    def activate_failover(self, reason: str) -> str:
        """
        Activate failover mode and create FailoverEvent node.

        Steps:
        1. Create FailoverEvent node in Neo4j
        2. Set failover state to active
        3. Update Ögedei's role to emergency router
        4. Create notification for admin

        Args:
            reason: Reason for failover activation

        Returns:
            Failover event ID string

        Raises:
            FailoverError: If failover activation fails
        """
        with self._state_lock:
            if self._failover_active:
                logger.info("Failover already active")
                return self._current_failover_event_id or ""

        try:
            event_id = self._generate_id()
            now = self._now()

            # Create FailoverEvent node
            cypher = """
            CREATE (f:FailoverEvent {
                id: $id,
                activated_at: $activated_at,
                deactivated_at: null,
                reason: $reason,
                duration_seconds: 0,
                messages_queued: 0,
                is_active: true,
                triggered_by: 'auto',
                kublai_status_at_trigger: 'unavailable',
                ogedei_agent_id: $ogedei_agent_id,
                created_at: $created_at
            })
            RETURN f.id as event_id
            """

            with self._session() as session:
                if session is None:
                    logger.warning(f"Fallback mode: Failover activation simulated for reason: {reason}")
                    with self._state_lock:
                        self._failover_active = True
                        self._current_failover_event_id = event_id
                    return event_id

                result = session.run(
                    cypher,
                    id=event_id,
                    activated_at=now,
                    reason=reason,
                    ogedei_agent_id=self.OGEDEI_AGENT_ID,
                    created_at=now
                )
                record = result.single()
                if not record:
                    raise FailoverError("Failed to create FailoverEvent node")

                event_id = record["event_id"]

            # Update failover state
            with self._state_lock:
                self._failover_active = True
                self._current_failover_event_id = event_id
                self._messages_routed_during_failover = 0

            # Update Ögedei's role
            self._update_ogedei_role(emergency_mode=True)

            # Create notification for admin
            self._create_failover_notification("activated", reason)

            logger.warning(f"Failover activated (event_id: {event_id}, reason: {reason})")
            return event_id

        except Neo4jError as e:
            logger.error(f"Failed to activate failover: {e}")
            raise FailoverError(f"Failed to activate failover: {e}")

    def deactivate_failover(self) -> None:
        """
        Deactivate failover mode and return control to Kublai.

        Steps:
        1. Update FailoverEvent as resolved
        2. Set failover state to inactive
        3. Restore Ögedei's normal role
        4. Create notification for admin

        Raises:
            FailoverError: If deactivation fails
        """
        with self._state_lock:
            if not self._failover_active:
                logger.info("Failover not active, nothing to deactivate")
                return

        try:
            now = self._now()
            event_id = self._current_failover_event_id
            messages_routed = self._messages_routed_during_failover

            if event_id:
                # Update FailoverEvent node
                cypher = """
                MATCH (f:FailoverEvent {id: $event_id})
                SET f.deactivated_at = $deactivated_at,
                    f.is_active = false,
                    f.duration_seconds = duration.inSeconds(f.activated_at, $deactivated_at).seconds,
                    f.messages_queued = $messages_queued
                RETURN f.id as event_id
                """

                with self._session() as session:
                    if session is not None:
                        result = session.run(
                            cypher,
                            event_id=event_id,
                            deactivated_at=now,
                            messages_queued=messages_routed
                        )
                        record = result.single()
                        if record:
                            logger.debug(f"Updated FailoverEvent: {event_id}")

            # Update failover state
            with self._state_lock:
                self._failover_active = False
                self._consecutive_healthy_checks = 0

            # Restore Ögedei's role
            self._update_ogedei_role(emergency_mode=False)

            # Create notification for admin
            self._create_failover_notification(
                "deactivated",
                f"Kublai recovered, {messages_routed} messages routed during failover"
            )

            logger.info(
                f"Failover deactivated (event_id: {event_id}, "
                f"messages_routed: {messages_routed})"
            )

            # Clear event ID
            self._current_failover_event_id = None
            self._messages_routed_during_failover = 0

        except Neo4jError as e:
            logger.error(f"Failed to deactivate failover: {e}")
            raise FailoverError(f"Failed to deactivate failover: {e}")

    def is_failover_active(self) -> bool:
        """
        Check if failover mode is currently active.

        Returns:
            True if failover is active
        """
        with self._state_lock:
            return self._failover_active

    def get_current_router(self) -> str:
        """
        Get the current active router (Kublai or Ögedei).

        Returns:
            Agent ID of the current router
        """
        with self._state_lock:
            if self._failover_active:
                return self.OGEDEI_AGENT_ID
            return self.KUBLAI_AGENT_ID

    def get_failover_status(self) -> Dict[str, Any]:
        """
        Get comprehensive failover status information.

        Returns:
            Dict with failover status including:
                - failover_active: bool
                - current_router: str
                - kublai_failures: int
                - consecutive_healthy_checks: int
                - current_event_id: Optional[str]
                - messages_routed: int
                - kublai_available: bool
        """
        with self._state_lock:
            kublai_available = self.is_agent_available(self.KUBLAI_AGENT_ID)

            return {
                "failover_active": self._failover_active,
                "current_router": self.get_current_router(),
                "kublai_failures": self._kublai_failures,
                "consecutive_healthy_checks": self._consecutive_healthy_checks,
                "current_event_id": self._current_failover_event_id,
                "messages_routed": self._messages_routed_during_failover,
                "kublai_available": kublai_available,
                "threshold_seconds": self.FAILOVER_THRESHOLD_SECONDS,
                "max_consecutive_failures": self.MAX_CONSECUTIVE_FAILURES,
            }

    def record_rate_limit_error(self) -> None:
        """
        Record a rate limit error from Kublai (429 response).

        Rate limit errors are counted as failures and can trigger failover.
        """
        with self._state_lock:
            self._kublai_failures += 1
            current_failures = self._kublai_failures
            should_failover = (self._kublai_failures >= self.MAX_CONSECUTIVE_FAILURES
                               and not self._failover_active)

        logger.warning(f"Kublai rate limit error, failures: {current_failures}/{self.MAX_CONSECUTIVE_FAILURES}")

        if should_failover:
            self.activate_failover("kublai_rate_limit_429")

    def route_message(self, sender: str, message: str, is_critical: bool = False) -> str:
        """
        Route a message during failover (Ögedei acting as router).

        During failover:
        - Critical messages are routed immediately
        - Non-critical messages are queued (logged for later processing)

        Args:
            sender: Original sender of the message
            message: Message content to route
            is_critical: Whether this is a critical message

        Returns:
            Agent ID to route to (or "queue" if non-critical during failover)
        """
        with self._state_lock:
            if not self._failover_active:
                # Failover not active, return Kublai
                return self.KUBLAI_AGENT_ID

            self._messages_routed_during_failover += 1

        if not is_critical:
            # Queue non-critical messages
            logger.info(f"Message queued during failover from {sender}")
            return "queue"

        # Route critical messages based on keywords
        message_lower = message.lower()

        routing_map = {
            "research": self.OGEDEI_AGENT_ID,  # Default to Ögedei for critical
            "urgent": self.OGEDEI_AGENT_ID,
            "emergency": self.OGEDEI_AGENT_ID,
            "health": self.OGEDEI_AGENT_ID,
            "ops": self.OGEDEI_AGENT_ID,
        }

        for keyword, agent in routing_map.items():
            if keyword in message_lower:
                logger.info(f"Critical message routed to {agent}")
                return agent

        # Default critical messages to Ögedei
        logger.info("Critical message routed to Ögedei (emergency router)")
        return self.OGEDEI_AGENT_ID

    def start_monitoring(self) -> None:
        """Start background thread to monitor Kublai health."""
        with self._state_lock:
            if self._monitor_thread and self._monitor_thread.is_alive():
                logger.info("Monitoring already active")
                return

            self._stop_monitoring.clear()
            self._monitor_thread = threading.Thread(
                target=self._monitor_loop,
                daemon=True,
                name="FailoverMonitor"
            )
            self._monitor_thread.start()

        logger.info("Kublai health monitoring started")

    def stop_monitoring(self) -> None:
        """Stop the monitoring thread."""
        self._stop_monitoring.set()

        with self._state_lock:
            if self._monitor_thread:
                self._monitor_thread.join(timeout=5)
                self._monitor_thread = None

        logger.info("Kublai health monitoring stopped")

    def _monitor_loop(self) -> None:
        """Background loop checking Kublai health."""
        while not self._stop_monitoring.is_set():
            try:
                self._check_kublai_health()
                self._last_check = self._now()
            except Exception as e:
                logger.error(f"Health check error: {e}")

            self._stop_monitoring.wait(self.check_interval)

    def _check_kublai_health(self) -> None:
        """Check if Kublai is healthy and handle failover if needed."""
        kublai_available = self.is_agent_available(self.KUBLAI_AGENT_ID)

        with self._state_lock:
            if kublai_available:
                self._consecutive_healthy_checks += 1
                self._kublai_failures = 0

                # Check if we should failback
                if self._failover_active:
                    if self._consecutive_healthy_checks >= self.RECOVERY_HEARTBEATS_REQUIRED:
                        logger.info(
                            f"Kublai recovered ({self._consecutive_healthy_checks} "
                            "consecutive healthy checks)"
                        )
                        self.deactivate_failover()
                    else:
                        logger.debug(
                            f"Kublai healthy, need "
                            f"{self.RECOVERY_HEARTBEATS_REQUIRED - self._consecutive_healthy_checks} "
                            "more checks for failback"
                        )
            else:
                self._consecutive_healthy_checks = 0
                self._kublai_failures += 1
                current_failures = self._kublai_failures
                should_failover = (self._kublai_failures >= self.MAX_CONSECUTIVE_FAILURES
                                   and not self._failover_active)

                logger.warning(
                    f"Kublai unavailable, failures: {current_failures}/"
                    f"{self.MAX_CONSECUTIVE_FAILURES}"
                )

                if should_failover:
                    reason = f"kublai_unavailable_{current_failures}_consecutive_failures"
                    self.activate_failover(reason)

    def _update_ogedei_role(self, emergency_mode: bool) -> None:
        """
        Update Ögedei's role in Neo4j.

        Args:
            emergency_mode: True to set emergency router role, False for normal
        """
        if emergency_mode:
            cypher = """
            MERGE (a:Agent {id: $agent_id})
            SET a.role = 'Operations / Emergency Router (ACTIVE)',
                a.failover_activated_at = datetime(),
                a.failover_reason = 'kublai_unresponsive'
            """
        else:
            cypher = """
            MATCH (a:Agent {id: $agent_id})
            SET a.role = 'Operations',
                a.failover_deactivated_at = datetime()
            REMOVE a.failover_activated_at, a.failover_reason
            """

        with self._session() as session:
            if session is None:
                return

            try:
                session.run(cypher, agent_id=self.OGEDEI_AGENT_ID)
                logger.debug(f"Ögedei role updated (emergency_mode: {emergency_mode})")
            except Neo4jError as e:
                logger.error(f"Failed to update Ögedei role: {e}")

    def _create_failover_notification(self, notification_type: str, message: str) -> None:
        """
        Create a notification for admin about failover status.

        Args:
            notification_type: "activated" or "deactivated"
            message: Notification message
        """
        notification_id = self._generate_id()
        now = self._now()

        cypher = """
        MERGE (o:Agent {id: $agent_id})
        CREATE (n:Notification {
            id: $id,
            type: $type,
            summary: $summary,
            created_at: $created_at,
            read: false
        })
        CREATE (o)-[:HAS_NOTIFICATION]->(n)
        RETURN n.id as notification_id
        """

        with self._session() as session:
            if session is None:
                return

            try:
                session.run(
                    cypher,
                    agent_id=self.OGEDEI_AGENT_ID,
                    id=notification_id,
                    type=f"failover_{notification_type}",
                    summary=message,
                    created_at=now
                )
                logger.info(f"Failover notification created: {notification_type}")
            except Neo4jError as e:
                logger.error(f"Failed to create notification: {e}")

    def get_failover_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get history of failover events.

        Args:
            limit: Maximum number of events to return

        Returns:
            List of failover event dicts
        """
        cypher = """
        MATCH (f:FailoverEvent)
        RETURN f.id as id,
               f.activated_at as activated_at,
               f.deactivated_at as deactivated_at,
               f.reason as reason,
               f.duration_seconds as duration_seconds,
               f.messages_queued as messages_queued,
               f.is_active as is_active,
               f.triggered_by as triggered_by
        ORDER BY f.activated_at DESC
        LIMIT $limit
        """

        with self._session() as session:
            if session is None:
                return []

            try:
                result = session.run(cypher, limit=limit)
                events = []
                for record in result:
                    events.append({
                        "id": record.get("id"),
                        "activated_at": record.get("activated_at"),
                        "deactivated_at": record.get("deactivated_at"),
                        "reason": record.get("reason"),
                        "duration_seconds": record.get("duration_seconds"),
                        "messages_queued": record.get("messages_queued"),
                        "is_active": record.get("is_active"),
                        "triggered_by": record.get("triggered_by"),
                    })
                return events
            except Neo4jError as e:
                logger.error(f"Failed to fetch failover history: {e}")
                return []

    def create_indexes(self) -> List[str]:
        """
        Create recommended indexes for failover monitoring.

        Returns:
            List of created index names
        """
        indexes = [
            ("CREATE INDEX agentheartbeat_agent_idx IF NOT EXISTS FOR (h:AgentHeartbeat) ON (h.agent)", "agentheartbeat_agent_idx"),
            ("CREATE INDEX agentheartbeat_last_seen_idx IF NOT EXISTS FOR (h:AgentHeartbeat) ON (h.last_seen)", "agentheartbeat_last_seen_idx"),
            ("CREATE INDEX failoverevent_is_active_idx IF NOT EXISTS FOR (f:FailoverEvent) ON (f.is_active)", "failoverevent_is_active_idx"),
            ("CREATE INDEX failoverevent_activated_at_idx IF NOT EXISTS FOR (f:FailoverEvent) ON (f.activated_at)", "failoverevent_activated_at_idx"),
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

def create_failover_monitor(
    memory: Any,
    check_interval_seconds: int = None
) -> FailoverMonitor:
    """
    Create a FailoverMonitor instance.

    Args:
        memory: OperationalMemory instance
        check_interval_seconds: Health check interval in seconds

    Returns:
        FailoverMonitor instance
    """
    return FailoverMonitor(
        memory=memory,
        check_interval_seconds=check_interval_seconds
    )


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    # Configure logging for example
    logging.basicConfig(level=logging.INFO)

    # Example usage (requires OperationalMemory)
    print("FailoverMonitor - Example Usage")
    print("=" * 50)

    print("""
    from openclaw_memory import OperationalMemory
    from tools.failover_monitor import FailoverMonitor

    # Initialize
    with OperationalMemory(
        uri="bolt://localhost:7687",
        username="neo4j",
        password="password"
    ) as memory:

        # Create failover monitor
        monitor = FailoverMonitor(memory)

        # Create indexes
        monitor.create_indexes()

        # Update Kublai heartbeat
        monitor.update_heartbeat("main")

        # Check if Kublai is available
        available = monitor.is_agent_available("main")
        print(f"Kublai available: {available}")

        # Check if failover should activate
        should_failover = monitor.should_activate_failover()
        print(f"Should activate failover: {should_failover}")

        # Get current router
        router = monitor.get_current_router()
        print(f"Current router: {router}")

        # Get failover status
        status = monitor.get_failover_status()
        print(f"Failover status: {status}")

        # Start background monitoring
        monitor.start_monitoring()

        # Route a message during failover
        target = monitor.route_message("user", "emergency: system down", is_critical=True)
        print(f"Routed to: {target}")

        # Stop monitoring
        monitor.stop_monitoring()
    """)
