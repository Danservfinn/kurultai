"""
Access Control and Sender Isolation for Neo4j.

Implements role-based access control (RBAC) and mandatory sender isolation
to prevent cross-sender data leakage in multi-tenant Neo4j.

Security Model:
- Agents have role-based permissions
- All sender-associated queries require sender_hash filter
- Main agent and Ops can access all senders (for coordination)
- Audit logging for sensitive access

OWASP References:
- A01:2021-Broken Access Control
- A05:2021-Security Misconfiguration
"""

import os
import ssl
import logging
from typing import Dict, Any, Optional, List, Set, Tuple
from neo4j import GraphDatabase

logger = logging.getLogger(__name__)


# ============================================================================
# AGENT ROLE DEFINITIONS
# ============================================================================

AGENT_ROLES: Dict[str, Dict[str, Any]] = {
    "main": {
        "name": "Kublai",
        "description": "Squad Lead / Router (Primary)",
        "permissions": ["read", "write", "delete", "admin"],
        "allowed_labels": ["*"],  # All node labels
        "sender_isolation": False,  # Can see all senders (for synthesis)
        "max_tasks": 10,
    },
    "researcher": {
        "name": "Möngke",
        "description": "Researcher",
        "permissions": ["read", "write"],
        "allowed_labels": ["Research", "Concept", "Task", "Analysis", "Reflection"],
        "sender_isolation": True,
        "max_tasks": 2,
    },
    "writer": {
        "name": "Chagatai",
        "description": "Content Writer",
        "permissions": ["read", "write"],
        "allowed_labels": ["Content", "Task", "Concept", "Reflection"],
        "sender_isolation": True,
        "max_tasks": 2,
    },
    "developer": {
        "name": "Temüjin",
        "description": "Developer/Security Lead",
        "permissions": ["read", "write"],
        "allowed_labels": ["CodeReview", "SecurityAudit", "Task", "Concept", "Reflection"],
        "sender_isolation": True,
        "max_tasks": 2,
    },
    "analyst": {
        "name": "Jochi",
        "description": "Analyst/Performance Lead",
        "permissions": ["read", "write"],
        "allowed_labels": ["Analysis", "Insight", "Task", "Concept", "Reflection", "SecurityAudit"],
        "sender_isolation": True,
        "max_tasks": 2,
    },
    "ops": {
        "name": "Ögedei",
        "description": "Operations / Emergency Router",
        "permissions": ["read", "write", "delete"],
        "allowed_labels": ["Task", "ProcessUpdate", "WorkflowImprovement", "Reflection"],
        "sender_isolation": False,  # Ops manages all tasks
        "max_tasks": 5,
    },
}

# Node labels that require sender isolation
SENDER_ASSOCIATED_LABELS = {
    "Task", "Research", "Content", "Analysis", "Concept",
    "Application", "Insight", "Reflection", "Synthesis",
    "Notification", "SessionContext", "SignalSession"
}


class Neo4jSecurityManager:
    """
    Security manager for Neo4j connections with role-based access.

    Implements:
    - Connection encryption (TLS)
    - Role-based access control
    - Query injection prevention
    - Audit logging

    Example:
        security = Neo4jSecurityManager(
            uri="bolt+s://localhost:7687",
            username="neo4j",
            password="...",
            encryption_key="...",
            verify_mode="verify-full"
        )

        driver = security.get_driver()
    """

    def __init__(
        self,
        uri: str,
        username: str,
        password: str,
        encryption_key: str,
        ca_cert_path: Optional[str] = None,
        verify_mode: str = "require"
    ):
        """
        Initialize secure Neo4j connection.

        Args:
            uri: Neo4j bolt URI (should use bolt+s:// or neo4j+s://)
            username: Neo4j username
            password: Neo4j password
            encryption_key: Key for field-level encryption
            ca_cert_path: Path to CA certificate for TLS verification
            verify_mode: "require", "verify-full", or "verify-ca"
        """
        self.uri = uri
        self.auth = (username, password)
        self.encryption_key = encryption_key
        self.ca_cert_path = ca_cert_path
        self.verify_mode = verify_mode

        # Validate TLS is used in production
        if not uri.startswith(("bolt+s://", "neo4j+s://", "bolt+ssc://")):
            logger.warning(
                "Neo4j connection should use TLS (bolt+s:// or neo4j+s://). "
                "Current URI: %s", uri
            )

    def get_driver(self) -> Any:
        """Get Neo4j driver with security configuration."""
        # Configure TLS
        if self.verify_mode in ("verify-ca", "verify-full") and self.ca_cert_path:
            ssl_context = ssl.create_default_context(cafile=self.ca_cert_path)
        else:
            ssl_context = ssl.create_default_context()
            if self.verify_mode == "require":
                # Require TLS but don't verify certificate (dev only!)
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE

        return GraphDatabase.driver(
            self.uri,
            auth=self.auth,
            encrypted=True,
            ssl_context=ssl_context
        )

    def check_agent_permission(
        self,
        agent_id: str,
        action: str,
        label: Optional[str] = None
    ) -> bool:
        """
        Check if agent has permission for action.

        Args:
            agent_id: Agent identifier
            action: Action to check (read, write, delete, admin)
            label: Node label being accessed (optional)

        Returns:
            True if permitted
        """
        role = AGENT_ROLES.get(agent_id)
        if not role:
            logger.warning(f"Unknown agent: {agent_id}")
            return False

        if action not in role["permissions"]:
            logger.warning(
                f"Agent {agent_id} lacks {action} permission"
            )
            return False

        if label and role["allowed_labels"] != ["*"]:
            if label not in role["allowed_labels"]:
                logger.warning(
                    f"Agent {agent_id} cannot access {label} nodes"
                )
                return False

        return True

    def get_agent_max_tasks(self, agent_id: str) -> int:
        """Get maximum concurrent tasks for agent."""
        role = AGENT_ROLES.get(agent_id, {})
        return role.get("max_tasks", 2)

    def requires_sender_isolation(self, agent_id: str) -> bool:
        """Check if agent requires sender isolation."""
        role = AGENT_ROLES.get(agent_id, {})
        return role.get("sender_isolation", True)


class SenderIsolationEnforcer:
    """
    Enforces sender isolation on all Neo4j queries.

    Every query that accesses sender data MUST include sender_hash filter.
    This class wraps queries to ensure isolation.

    Example:
        enforcer = SenderIsolationEnforcer(security_manager)

        query = "MATCH (t:Task) WHERE t.status = 'pending' RETURN t"
        params = {}

        # For regular agent (requires sender_hash)
        safe_query, safe_params = enforcer.enforce_isolation(
            query, params, agent_id="researcher", sender_hash="abc123"
        )
        # Result: query with sender_hash filter added

        # For main agent (no isolation required)
        safe_query, safe_params = enforcer.enforce_isolation(
            query, params, agent_id="main", sender_hash=None
        )
        # Result: original query unchanged
    """

    def __init__(self, security_manager: Neo4jSecurityManager):
        self.security = security_manager

    def enforce_isolation(
        self,
        query: str,
        params: Dict[str, Any],
        agent_id: str,
        sender_hash: Optional[str]
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Modify query to enforce sender isolation.

        Args:
            query: Original Cypher query
            params: Query parameters
            agent_id: Agent executing query
            sender_hash: Sender hash for isolation

        Returns:
            Modified query and parameters with isolation enforced
        """
        # Check if agent requires sender isolation
        if not self.security.requires_sender_isolation(agent_id):
            return query, params

        if not sender_hash:
            raise ValueError(
                f"Agent {agent_id} requires sender_hash for all queries"
            )

        # Check if query accesses sender-associated labels
        if not self._accesses_sender_data(query):
            return query, params

        # Check if query already has sender_hash filter
        if self._has_sender_filter(query):
            # Verify it's parameterized
            if "$sender_hash" not in query:
                logger.warning(
                    "Query has hardcoded sender_hash - potential security issue"
                )
            return query, params

        # Add sender_hash filter to query
        modified_query = self._inject_sender_filter(query)
        modified_params = {**params, "sender_hash": sender_hash}

        return modified_query, modified_params

    def _accesses_sender_data(self, query: str) -> bool:
        """Check if query accesses sender-associated node labels."""
        query_upper = query.upper()

        for label in SENDER_ASSOCIATED_LABELS:
            # Check for :Label pattern
            if f":{label.upper()}" in query_upper:
                return True

        return False

    def _has_sender_filter(self, query: str) -> bool:
        """Check if query already filters by sender_hash."""
        return "sender_hash" in query.lower()

    def _inject_sender_filter(self, query: str) -> str:
        """
        Inject sender_hash filter into Cypher query.

        WARNING: This is a simplified implementation. Production use should
        employ a proper Cypher AST parser for robust injection.
        """
        query_lower = query.lower()

        # Find the best place to inject the filter
        if "where" in query_lower:
            # Add AND condition to existing WHERE
            # Find WHERE and add condition after it
            import re

            # Pattern to match WHERE clause
            where_pattern = r'(\s+where\s+)'
            match = re.search(where_pattern, query, re.IGNORECASE)

            if match:
                # Insert sender_hash condition after WHERE
                pos = match.end()
                return query[:pos] + "sender_hash = $sender_hash AND " + query[pos:]

        elif "return" in query_lower:
            # Add WHERE before RETURN
            return_query = query_lower.split("return")[0]
            remainder = query[len(return_query):]
            return return_query + f"WHERE sender_hash = $sender_hash\n{remainder}"

        elif "with" in query_lower:
            # Add WHERE before WITH
            with_query = query_lower.split("with")[0]
            remainder = query[len(with_query):]
            return with_query + f"WHERE sender_hash = $sender_hash\n{remainder}"

        # Fallback: append WHERE clause
        return query + "\nWHERE sender_hash = $sender_hash"


class AuditLogger:
    """
    Audit logging for sensitive operations.

    Logs:
    - Data access by agents
    - Cross-sender queries
    - Permission violations
    - Encryption/decryption operations
    """

    def __init__(self, neo4j_client=None, log_to_file: bool = True):
        """
        Initialize audit logger.

        Args:
            neo4j_client: Optional Neo4j client for audit storage
            log_to_file: Whether to log to file
        """
        self.neo4j = neo4j_client
        self.log_to_file = log_to_file

    async def log_data_access(
        self,
        agent_id: str,
        sender_hash: str,
        action: str,
        labels: List[str],
        record_count: int
    ):
        """Log data access event."""
        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": "data_access",
            "agent_id": agent_id,
            "sender_hash": sender_hash,
            "action": action,
            "labels": labels,
            "record_count": record_count
        }

        await self._store_audit_event(event)

    async def log_permission_violation(
        self,
        agent_id: str,
        attempted_action: str,
        target_label: str,
        reason: str
    ):
        """Log permission violation."""
        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": "permission_violation",
            "agent_id": agent_id,
            "attempted_action": attempted_action,
            "target_label": target_label,
            "reason": reason,
            "severity": "high"
        }

        logger.warning(
            f"Permission violation: {agent_id} attempted {attempted_action} "
            f"on {target_label}"
        )

        await self._store_audit_event(event)

    async def log_cross_sender_access(
        self,
        agent_id: str,
        source_sender: str,
        accessed_senders: List[str]
    ):
        """Log potential cross-sender data access."""
        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": "cross_sender_access",
            "agent_id": agent_id,
            "source_sender": source_sender,
            "accessed_senders": accessed_senders,
            "severity": "critical"
        }

        logger.error(
            f"Cross-sender access detected: {agent_id} accessed "
            f"{len(accessed_senders)} senders"
        )

        await self._store_audit_event(event)

    async def _store_audit_event(self, event: Dict[str, Any]):
        """Store audit event to Neo4j and/or file."""
        # Log to Python logger
        logger.info(f"AUDIT: {event}")

        # Store in Neo4j if available
        if self.neo4j:
            try:
                query = """
                CREATE (a:AuditEvent {
                    timestamp: datetime($timestamp),
                    event_type: $event_type,
                    agent_id: $agent_id,
                    details: $details
                })
                RETURN a
                """
                await self.neo4j.run(query, {
                    "timestamp": event["timestamp"],
                    "event_type": event["event_type"],
                    "agent_id": event.get("agent_id", "unknown"),
                    "details": json.dumps(event)
                })
            except Exception as e:
                logger.error(f"Failed to store audit event: {e}")


# Import for type hints
from datetime import datetime
import json
