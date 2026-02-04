"""
Kublai Failover Protocol (Phase 6.5)

Emergency router implementation that activates when Kublai is unavailable.
Ögedei assumes the routing role to maintain system operation during outages.
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum

# Configure logging
logger = logging.getLogger(__name__)


class FailoverStatus(Enum):
    """Failover event status."""
    ACTIVE = "active"
    RECOVERING = "recovering"
    RESOLVED = "resolved"


class KublaiStatus(Enum):
    """Kublai health status."""
    ACTIVE = "active"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class FailoverProtocol:
    """
    Ögedei emergency router - activates when Kublai is unavailable.

    Monitors Kublai's health via heartbeats and automatically assumes
    routing responsibilities when Kublai becomes unavailable.
    """

    # Configuration constants
    HEARTBEAT_INTERVAL_SECONDS = 30  # Expected heartbeat interval
    MAX_MISSED_HEARTBEATS = 3  # Failover after 3 missed heartbeats (90s)
    RECOVERY_HEARTBEATS_REQUIRED = 3  # Consecutive heartbeats for recovery
    FAILOVER_TIMEOUT_SECONDS = 90  # 3 missed heartbeats

    # Simplified routing map for failover mode
    ROUTING_MAP = {
        "research": "möngke",
        "researcher": "möngke",
        "write": "chagatai",
        "writer": "chagatai",
        "writing": "chagatai",
        "code": "temüjin",
        "developer": "temüjin",
        "develop": "temüjin",
        "coding": "temüjin",
        "analyze": "jochi",
        "analysis": "jochi",
        "analyst": "jochi",
        "review": "jochi",
        "ops": "ögedei",
        "operations": "ögedei",
        "operational": "ögedei",
        "system": "ögedei",
        "monitor": "ögedei",
        "health": "ögedei",
        "file": "ögedei",
        "security": "ögedei",
        "audit": "ögedei",
        "main": "kublai",
        "orchestrate": "kublai",
        "route": "kublai",
        "delegate": "kublai",
    }

    def __init__(self, memory: Any, ogedei_agent_id: str = "ops"):
        """
        Initialize with operational memory.

        Args:
            memory: OperationalMemory instance for Neo4j operations
            ogedei_agent_id: Agent ID for Ögedei (default: "ops")
        """
        self.memory = memory
        self.ogedei_agent_id = ogedei_agent_id
        self._kublai_agent_id = "main"  # Kublai's agent ID
        self._consecutive_heartbeats = 0
        self._missed_heartbeats = 0
        self._last_kublai_heartbeat: Optional[datetime] = None
        self._failover_active = False
        self._current_failover_event_id: Optional[str] = None
        self._messages_routed_during_failover = 0

        logger.info(f"FailoverProtocol initialized for {ogedei_agent_id}")

    def _generate_id(self) -> str:
        """Generate a unique ID."""
        return str(uuid.uuid4())

    def _now(self) -> datetime:
        """Get current UTC datetime."""
        return datetime.now(timezone.utc)

    def check_kublai_health(self) -> Dict[str, Any]:
        """
        Check Kublai's health status.

        Returns:
            Dict with health information:
                - healthy: bool - Whether Kublai is healthy
                - last_heartbeat: datetime - Last known heartbeat
                - missed_beats: int - Number of missed heartbeats
                - status: str - "active" | "degraded" | "unavailable"
        """
        try:
            # Query Neo4j for Kublai's agent status
            cypher = """
                MATCH (a:Agent {name: $agent_name})
                RETURN a.last_heartbeat as last_heartbeat,
                       a.status as status,
                       a.current_task as current_task
            """

            with self.memory._session() as session:
                if session is None:
                    # Neo4j unavailable - assume degraded
                    return {
                        "healthy": False,
                        "last_heartbeat": self._last_kublai_heartbeat,
                        "missed_beats": self._missed_heartbeats,
                        "status": KublaiStatus.UNAVAILABLE.value
                    }

                result = session.run(cypher, agent_name=self._kublai_agent_id)
                record = result.single()

                if record is None:
                    # Agent not found in database
                    self._missed_heartbeats += 1
                    return {
                        "healthy": False,
                        "last_heartbeat": None,
                        "missed_beats": self._missed_heartbeats,
                        "status": KublaiStatus.UNAVAILABLE.value
                    }

                last_heartbeat = record.get("last_heartbeat")
                status = record.get("status", "unknown")

                if last_heartbeat:
                    # Handle Neo4j datetime format
                    if hasattr(last_heartbeat, 'to_native'):
                        last_heartbeat = last_heartbeat.to_native()
                    self._last_kublai_heartbeat = last_heartbeat

                    # Calculate missed heartbeats
                    time_since = self._now() - last_heartbeat
                    missed_beats = int(time_since.total_seconds() / self.HEARTBEAT_INTERVAL_SECONDS)
                    self._missed_heartbeats = max(0, missed_beats)

                    # Determine status
                    if self._missed_heartbeats >= self.MAX_MISSED_HEARTBEATS:
                        kublai_status = KublaiStatus.UNAVAILABLE
                    elif self._missed_heartbeats >= 1:
                        kublai_status = KublaiStatus.DEGRADED
                    else:
                        kublai_status = KublaiStatus.ACTIVE

                    return {
                        "healthy": kublai_status == KublaiStatus.ACTIVE,
                        "last_heartbeat": last_heartbeat,
                        "missed_beats": self._missed_heartbeats,
                        "status": kublai_status.value
                    }
                else:
                    # No heartbeat recorded
                    self._missed_heartbeats = self.MAX_MISSED_HEARTBEATS
                    return {
                        "healthy": False,
                        "last_heartbeat": None,
                        "missed_beats": self._missed_heartbeats,
                        "status": KublaiStatus.UNAVAILABLE.value
                    }

        except Exception as e:
            logger.error(f"Error checking Kublai health: {e}")
            return {
                "healthy": False,
                "last_heartbeat": self._last_kublai_heartbeat,
                "missed_beats": self._missed_heartbeats,
                "status": KublaiStatus.UNAVAILABLE.value,
                "error": str(e)
            }

    def should_activate_failover(self) -> bool:
        """
        Determine if failover should activate.

        Activates when:
        - Kublai missed 3+ heartbeats (90 seconds)
        - Kublai status is "unavailable"
        - Manual failover triggered

        Returns:
            True if failover should be activated
        """
        health = self.check_kublai_health()

        # Already in failover - don't re-trigger
        if self._failover_active:
            return False

        # Check activation conditions
        if health["missed_beats"] >= self.MAX_MISSED_HEARTBEATS:
            logger.warning(
                f"Failover condition met: {health['missed_beats']} missed heartbeats"
            )
            return True

        if health["status"] == KublaiStatus.UNAVAILABLE.value:
            logger.warning("Failover condition met: Kublai status is unavailable")
            return True

        return False

    def activate_failover(self, reason: str, triggered_by: str = "auto") -> bool:
        """
        Activate Ögedei as emergency router.

        Steps:
        1. Create FailoverEvent node in Neo4j
        2. Update routing configuration
        3. Notify all agents of failover
        4. Start monitoring Kublai for recovery

        Args:
            reason: Reason for failover activation
            triggered_by: "auto" or "manual"

        Returns:
            True if failover was successfully activated
        """
        if self._failover_active:
            logger.info("Failover already active")
            return True

        try:
            # Get current Kublai status
            health = self.check_kublai_health()

            # Create FailoverEvent node
            event_id = self._generate_id()
            cypher = """
                CREATE (fe:FailoverEvent {
                    id: $event_id,
                    triggered_by: $triggered_by,
                    reason: $reason,
                    activated_at: datetime(),
                    deactivated_at: null,
                    status: 'active',
                    kublai_status_at_trigger: $kublai_status,
                    resolved_by: null,
                    messages_routed: 0,
                    ogedei_agent_id: $ogedei_id
                })
                RETURN fe.id as event_id
            """

            with self.memory._session() as session:
                if session is not None:
                    result = session.run(
                        cypher,
                        event_id=event_id,
                        triggered_by=triggered_by,
                        reason=reason,
                        kublai_status=health["status"],
                        ogedei_id=self.ogedei_agent_id
                    )
                    record = result.single()
                    if record:
                        self._current_failover_event_id = record.get("event_id")

            # Update Kublai's status to reflect failover
            self._update_kublai_status("failover")

            # Set failover state
            self._failover_active = True
            self._messages_routed_during_failover = 0

            # Create notification for all agents
            self._notify_agents_of_failover("activated", reason)

            logger.info(
                f"Failover activated (event_id: {self._current_failover_event_id}, "
                f"reason: {reason})"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to activate failover: {e}")
            return False

    def deactivate_failover(self) -> bool:
        """
        Deactivate failover when Kublai recovers.

        Steps:
        1. Verify Kublai is healthy (3 consecutive heartbeats)
        2. Update FailoverEvent as resolved
        3. Resume normal routing
        4. Notify all agents

        Returns:
            True if failover was successfully deactivated
        """
        if not self._failover_active:
            logger.info("Failover not active, nothing to deactivate")
            return True

        try:
            # Verify Kublai is healthy
            health = self.check_kublai_health()
            if not health["healthy"]:
                logger.warning(
                    "Cannot deactivate failover: Kublai is not healthy yet"
                )
                return False

            # Update FailoverEvent as resolved
            if self._current_failover_event_id:
                cypher = """
                    MATCH (fe:FailoverEvent {id: $event_id})
                    SET fe.status = 'resolved',
                        fe.deactivated_at = datetime(),
                        fe.resolved_by = $resolved_by,
                        fe.messages_routed = $messages_routed,
                        fe.duration_seconds = duration.inSeconds(
                            fe.activated_at, datetime()
                        ).seconds
                """

                with self.memory._session() as session:
                    if session is not None:
                        session.run(
                            cypher,
                            event_id=self._current_failover_event_id,
                            resolved_by=self.ogedei_agent_id,
                            messages_routed=self._messages_routed_during_failover
                        )

            # Update Kublai's status back to active
            self._update_kublai_status("active")

            # Reset failover state
            self._failover_active = False
            self._consecutive_heartbeats = 0

            # Notify all agents
            self._notify_agents_of_failover(
                "ended",
                f"Kublai recovered, {self._messages_routed_during_failover} messages routed during failover"
            )

            logger.info(
                f"Failover deactivated. Routed {self._messages_routed_during_failover} "
                "messages during failover period."
            )

            # Reset message counter
            self._messages_routed_during_failover = 0
            self._current_failover_event_id = None

            return True

        except Exception as e:
            logger.error(f"Failed to deactivate failover: {e}")
            return False

    def route_during_failover(self, sender: str, message: str) -> str:
        """
        Route message during failover (Ögedei acting as router).

        Simplified routing - direct to appropriate agent based on keywords:
        - research questions -> researcher (möngke)
        - code issues -> developer (temüjin)
        - writing tasks -> writer (chagatai)
        - analysis -> analyst (jochi)
        - operations -> ops (ögedei)

        Args:
            sender: Original sender of the message
            message: Message content to route

        Returns:
            Agent ID to route to
        """
        if not self._failover_active:
            logger.warning("route_during_failover called but failover not active")
            return self._kublai_agent_id

        message_lower = message.lower()

        # Score each agent based on keyword matches
        agent_scores: Dict[str, int] = {}

        for keyword, agent in self.ROUTING_MAP.items():
            if keyword in message_lower:
                agent_scores[agent] = agent_scores.get(agent, 0) + 1

        # Select agent with highest score
        if agent_scores:
            target_agent = max(agent_scores, key=agent_scores.get)
        else:
            # Default to researcher if no keywords match
            target_agent = "möngke"

        # Don't route back to Kublai during failover
        if target_agent == self._kublai_agent_id:
            target_agent = "möngke"

        # Increment message counter
        self._messages_routed_during_failover += 1

        # Update message count in Neo4j
        self._increment_messages_routed()

        logger.info(
            f"Failover routing: message from {sender} -> {target_agent} "
            f"(keywords: {agent_scores})"
        )

        return target_agent

    def get_failover_status(self) -> Dict[str, Any]:
        """
        Get current failover status.

        Returns:
            Dict with failover status information
        """
        health = self.check_kublai_health()

        status = {
            "failover_active": self._failover_active,
            "kublai_health": health,
            "current_event_id": self._current_failover_event_id,
            "messages_routed": self._messages_routed_during_failover,
            "ogedei_agent_id": self.ogedei_agent_id,
            "should_activate": self.should_activate_failover(),
            "consecutive_heartbeats": self._consecutive_heartbeats,
        }

        # Add event details if active
        if self._failover_active and self._current_failover_event_id:
            try:
                cypher = """
                    MATCH (fe:FailoverEvent {id: $event_id})
                    RETURN fe.activated_at as activated_at,
                           fe.reason as reason,
                           fe.triggered_by as triggered_by
                """

                with self.memory._session() as session:
                    if session is not None:
                        result = session.run(
                            cypher,
                            event_id=self._current_failover_event_id
                        )
                        record = result.single()
                        if record:
                            status["event_details"] = {
                                "activated_at": record.get("activated_at"),
                                "reason": record.get("reason"),
                                "triggered_by": record.get("triggered_by")
                            }
            except Exception as e:
                logger.error(f"Error fetching event details: {e}")

        return status

    def monitor_and_recover(self) -> bool:
        """
        Background task: monitor Kublai and auto-recover.

        This method should be called periodically (e.g., every 30 seconds)
        to monitor Kublai's health and handle automatic failover/recovery.

        Returns:
            True if state changed (failover activated or deactivated)
        """
        health = self.check_kublai_health()

        # Handle recovery detection
        if health["healthy"]:
            self._consecutive_heartbeats += 1
            self._missed_heartbeats = 0

            if self._failover_active:
                # Check if we have enough consecutive heartbeats to recover
                if self._consecutive_heartbeats >= self.RECOVERY_HEARTBEATS_REQUIRED:
                    logger.info(
                        f"Kublai recovery detected ({self._consecutive_heartbeats} "
                        "consecutive heartbeats)"
                    )
                    return self.deactivate_failover()
                else:
                    logger.debug(
                        f"Kublai heartbeat received, need "
                        f"{self.RECOVERY_HEARTBEATS_REQUIRED - self._consecutive_heartbeats} "
                        "more for recovery"
                    )
        else:
            self._consecutive_heartbeats = 0

            # Check if we should activate failover
            if not self._failover_active and self.should_activate_failover():
                reason = f"Kublai {health['status']}: {health['missed_beats']} missed heartbeats"
                return self.activate_failover(reason, triggered_by="auto")

        return False

    def record_kublai_heartbeat(self, status: str = "active") -> bool:
        """
        Record a heartbeat from Kublai.

        This should be called when Kublai sends a heartbeat message.

        Args:
            status: Kublai's current status

        Returns:
            True if heartbeat was recorded successfully
        """
        try:
            self._last_kublai_heartbeat = self._now()

            # Update in Neo4j
            cypher = """
                MERGE (a:Agent {name: $agent_name})
                SET a.last_heartbeat = datetime(),
                    a.status = $status,
                    a.updated_at = datetime()
            """

            with self.memory._session() as session:
                if session is not None:
                    session.run(
                        cypher,
                        agent_name=self._kublai_agent_id,
                        status=status
                    )

            logger.debug(f"Recorded Kublai heartbeat (status: {status})")
            return True

        except Exception as e:
            logger.error(f"Error recording Kublai heartbeat: {e}")
            return False

    def manual_trigger_failover(self, reason: str) -> bool:
        """
        Manually trigger failover.

        Args:
            reason: Reason for manual failover

        Returns:
            True if failover was triggered successfully
        """
        logger.warning(f"Manual failover triggered: {reason}")
        return self.activate_failover(reason, triggered_by="manual")

    def _update_kublai_status(self, status: str) -> bool:
        """
        Update Kublai's status in Neo4j.

        Args:
            status: New status for Kublai

        Returns:
            True if update was successful
        """
        try:
            cypher = """
                MATCH (a:Agent {name: $agent_name})
                SET a.status = $status,
                    a.updated_at = datetime()
            """

            with self.memory._session() as session:
                if session is not None:
                    session.run(
                        cypher,
                        agent_name=self._kublai_agent_id,
                        status=status
                    )

            return True

        except Exception as e:
            logger.error(f"Error updating Kublai status: {e}")
            return False

    def _notify_agents_of_failover(self, notification_type: str, message: str) -> bool:
        """
        Notify all agents of failover status change.

        Args:
            notification_type: "activated" or "ended"
            message: Notification message

        Returns:
            True if notification was created successfully
        """
        try:
            # Create notifications for all agents
            notification_type_str = f"failover_{notification_type}"

            # Get all active agents
            agents = self.memory.list_active_agents()

            for agent in agents:
                agent_name = agent.get("name", "")
                if agent_name and agent_name != self.ogedei_agent_id:
                    self.memory.create_notification(
                        agent=agent_name,
                        type=notification_type_str,
                        summary=message,
                        task_id=self._current_failover_event_id
                    )

            logger.info(f"Sent failover {notification_type} notification to agents")
            return True

        except Exception as e:
            logger.error(f"Error notifying agents: {e}")
            return False

    def _increment_messages_routed(self) -> bool:
        """
        Increment the messages routed counter in Neo4j.

        Returns:
            True if update was successful
        """
        if not self._current_failover_event_id:
            return False

        try:
            cypher = """
                MATCH (fe:FailoverEvent {id: $event_id})
                SET fe.messages_routed = coalesce(fe.messages_routed, 0) + 1
            """

            with self.memory._session() as session:
                if session is not None:
                    session.run(
                        cypher,
                        event_id=self._current_failover_event_id
                    )

            return True

        except Exception as e:
            logger.error(f"Error incrementing messages routed: {e}")
            return False

    def get_failover_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get history of failover events.

        Args:
            limit: Maximum number of events to return

        Returns:
            List of failover event records
        """
        try:
            cypher = """
                MATCH (fe:FailoverEvent)
                RETURN fe.id as id,
                       fe.triggered_by as triggered_by,
                       fe.reason as reason,
                       fe.activated_at as activated_at,
                       fe.deactivated_at as deactivated_at,
                       fe.status as status,
                       fe.messages_routed as messages_routed,
                       fe.kublai_status_at_trigger as kublai_status
                ORDER BY fe.activated_at DESC
                LIMIT $limit
            """

            with self.memory._session() as session:
                if session is None:
                    return []

                result = session.run(cypher, limit=limit)
                records = []

                for record in result:
                    records.append({
                        "id": record.get("id"),
                        "triggered_by": record.get("triggered_by"),
                        "reason": record.get("reason"),
                        "activated_at": record.get("activated_at"),
                        "deactivated_at": record.get("deactivated_at"),
                        "status": record.get("status"),
                        "messages_routed": record.get("messages_routed"),
                        "kublai_status_at_trigger": record.get("kublai_status")
                    })

                return records

        except Exception as e:
            logger.error(f"Error fetching failover history: {e}")
            return []
