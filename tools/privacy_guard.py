"""Privacy Guard - Privacy enforcement and audit for Kurultai Identity Management.

This module provides:
- Privacy level enforcement (PUBLIC / PRIVATE / SENSITIVE)
- Content filtering based on audience
- Audit trail for sensitive data access
- Data retention policy enforcement
- Privacy-aware context building
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Set, Callable
from dataclasses import dataclass, field
from enum import Enum
from contextlib import contextmanager

# Configure logging
logger = logging.getLogger(__name__)


class PrivacyLevel(Enum):
    """Privacy classification levels."""
    PUBLIC = "public"       # Can be shared with anyone
    PRIVATE = "private"     # Only for the person themselves
    SENSITIVE = "sensitive" # Requires explicit authorization


class AccessAction(Enum):
    """Types of access actions to audit."""
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    SHARE = "share"
    FILTER = "filter"
    EXPORT = "export"


@dataclass
class AuditEntry:
    """A single audit log entry."""
    id: str
    person_id: str
    fact_id: Optional[str]
    action: AccessAction
    accessed_by: str                    # Agent or system that accessed
    accessed_at: datetime
    privacy_level: PrivacyLevel
    context: str                        # Why it was accessed
    recipient: Optional[str] = None     # If shared, who received it
    was_filtered: bool = False          # Whether content was filtered
    retain_until: Optional[datetime] = None


@dataclass
class FilterResult:
    """Result of privacy filtering."""
    original_content: str
    filtered_content: str
    was_modified: bool
    filtered_items: List[str]           # What was removed/changed
    privacy_violations: List[str]       # What would have been violations


@dataclass
class PrivacyPolicy:
    """Privacy policy configuration."""
    default_fact_privacy: PrivacyLevel = PrivacyLevel.PRIVATE
    default_preference_privacy: PrivacyLevel = PrivacyLevel.PRIVATE
    retain_audit_logs_days: int = 90
    auto_archive_conversations_days: int = 30
    enable_audit_logging: bool = True
    enable_privacy_filtering: bool = True
    sensitive_keywords: List[str] = field(default_factory=list)
    redaction_placeholder: str = "[REDACTED]"


class PrivacyGuard:
    """
    Enforces privacy policies and maintains audit trails.
    
    Features:
    - Filter content based on privacy levels
    - Audit all sensitive data access
    - Enforce data retention policies
    - Privacy-aware context building
    """

    # Default sensitive keywords (can be customized)
    DEFAULT_SENSITIVE_KEYWORDS = [
        "password", "secret", "token", "key", "credential",
        "ssn", "social security", "credit card", "bank account",
        "address", "phone number", "email", "personal",
        "private", "confidential"
    ]

    def __init__(
        self,
        neo4j_uri: str = "bolt://localhost:7687",
        neo4j_username: str = "neo4j",
        neo4j_password: Optional[str] = None,
        database: str = "neo4j",
        fallback_mode: bool = True,
        policy: Optional[PrivacyPolicy] = None
    ):
        self.neo4j_uri = neo4j_uri
        self.neo4j_username = neo4j_username
        self.neo4j_password = neo4j_password
        self.database = database
        self.fallback_mode = fallback_mode
        self.policy = policy or PrivacyPolicy()
        self._driver = None
        self._initialized = False

        self._import_neo4j()

    def _import_neo4j(self):
        """Lazy import Neo4j."""
        try:
            from neo4j import GraphDatabase
            from neo4j.exceptions import ServiceUnavailable
            self._GraphDatabase = GraphDatabase
            self._ServiceUnavailable = ServiceUnavailable
        except ImportError:
            logger.warning("Neo4j driver not available")
            self._GraphDatabase = None

    def initialize(self) -> bool:
        """Initialize Neo4j connection."""
        if self._GraphDatabase is None:
            logger.error("Neo4j driver not available")
            return False

        if self.neo4j_password is None:
            raise ValueError("Neo4j password is required")

        try:
            self._driver = self._GraphDatabase.driver(
                self.neo4j_uri,
                auth=(self.neo4j_username, self.neo4j_password)
            )
            self._driver.verify_connectivity()
            self._initialized = True

            # Load or create policy
            self._load_or_create_policy()

            logger.info("PrivacyGuard initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Neo4j: {e}")
            if not self.fallback_mode:
                raise
            return False

    def close(self):
        """Close Neo4j connection."""
        if self._driver:
            self._driver.close()
            self._driver = None
            self._initialized = False

    @contextmanager
    def _session(self):
        """Context manager for Neo4j sessions."""
        if not self._driver:
            yield None
            return
        session = self._driver.session(database=self.database)
        try:
            yield session
        finally:
            session.close()

    # ===================================================================
    # Policy Management
    # ===================================================================

    def _load_or_create_policy(self):
        """Load existing policy or create default."""
        with self._session() as session:
            if session is None:
                return

            cypher = """
            MERGE (ipc:IdentityPrivacyConfig {id: 'default'})
            ON CREATE SET
                ipc.default_fact_privacy = $default_fact,
                ipc.default_preference_privacy = $default_pref,
                ipc.retain_audit_logs_days = $retain_days,
                ipc.auto_archive_conversations_days = $archive_days,
                ipc.enable_audit_logging = $enable_audit,
                ipc.enable_privacy_filtering = $enable_filter,
                ipc.created_at = datetime()
            RETURN ipc
            """

            result = session.run(
                cypher,
                default_fact=self.policy.default_fact_privacy.value,
                default_pref=self.policy.default_preference_privacy.value,
                retain_days=self.policy.retain_audit_logs_days,
                archive_days=self.policy.auto_archive_conversations_days,
                enable_audit=self.policy.enable_audit_logging,
                enable_filter=self.policy.enable_privacy_filtering
            )
            record = result.single()
            if record:
                config = record["ipc"]
                self.policy = PrivacyPolicy(
                    default_fact_privacy=PrivacyLevel(config.get("default_fact_privacy", "private")),
                    default_preference_privacy=PrivacyLevel(config.get("default_preference_privacy", "private")),
                    retain_audit_logs_days=config.get("retain_audit_logs_days", 90),
                    auto_archive_conversations_days=config.get("auto_archive_conversations_days", 30),
                    enable_audit_logging=config.get("enable_audit_logging", True),
                    enable_privacy_filtering=config.get("enable_privacy_filtering", True)
                )

    def update_policy(self, **updates) -> bool:
        """Update privacy policy settings."""
        with self._session() as session:
            if session is None:
                return False

            set_clauses = []
            params = {}

            for key, value in updates.items():
                if hasattr(self.policy, key):
                    if isinstance(value, PrivacyLevel):
                        value = value.value
                    set_clauses.append(f"ipc.{key} = ${key}")
                    params[key] = value

            if not set_clauses:
                return False

            cypher = f"""
            MATCH (ipc:IdentityPrivacyConfig {{id: 'default'}})
            SET {', '.join(set_clauses)}, ipc.updated_at = datetime()
            RETURN ipc
            """

            result = session.run(cypher, **params)
            return result.single() is not None

    # ===================================================================
    # Privacy Filtering
    # ===================================================================

    def filter_content_for_audience(
        self,
        content: str,
        owner_person_id: str,
        audience_person_id: Optional[str],
        accessed_by: str = "system",
        context: str = "response_generation"
    ) -> FilterResult:
        """
        Filter content based on privacy levels for the intended audience.
        
        Args:
            content: Content to filter
            owner_person_id: Person the content belongs to
            audience_person_id: Person who will see it (None = public)
            accessed_by: System/agent accessing
            context: Why it's being accessed
            
        Returns:
            FilterResult with filtered content
        """
        if not self.policy.enable_privacy_filtering:
            return FilterResult(
                original_content=content,
                filtered_content=content,
                was_modified=False,
                filtered_items=[],
                privacy_violations=[]
            )

        # Determine what privacy levels are allowed
        allowed_levels = self._get_allowed_privacy_levels(
            owner_person_id, audience_person_id
        )

        # Find private facts in content
        facts_to_filter = self._find_facts_in_content(
            content, owner_person_id, allowed_levels
        )

        # Apply filtering
        filtered_content = content
        filtered_items = []
        violations = []

        for fact in facts_to_filter:
            if fact["privacy"] not in [l.value for l in allowed_levels]:
                # Replace fact value with placeholder
                filtered_content = filtered_content.replace(
                    fact["value"],
                    self.policy.redaction_placeholder
                )
                filtered_items.append(f"{fact['key']}: {fact['value'][:20]}...")
                violations.append(f"Filtered {fact['privacy']} fact: {fact['key']}")

                # Audit the filtering
                self._audit_access(
                    person_id=owner_person_id,
                    fact_id=fact.get("id"),
                    action=AccessAction.FILTER,
                    accessed_by=accessed_by,
                    privacy_level=PrivacyLevel(fact["privacy"]),
                    context=f"Filtered from response to {audience_person_id or 'public'}",
                    recipient=audience_person_id,
                    was_filtered=True
                )

        return FilterResult(
            original_content=content,
            filtered_content=filtered_content,
            was_modified=len(filtered_items) > 0,
            filtered_items=filtered_items,
            privacy_violations=violations
        )

    def filter_facts_for_audience(
        self,
        facts: List[Dict[str, Any]],
        owner_person_id: str,
        audience_person_id: Optional[str]
    ) -> List[Dict[str, Any]]:
        """
        Filter a list of facts for an audience.
        
        Args:
            facts: List of fact dictionaries
            owner_person_id: Person the facts belong to
            audience_person_id: Person who will see them
            
        Returns:
            Filtered list of facts
        """
        allowed_levels = self._get_allowed_privacy_levels(
            owner_person_id, audience_person_id
        )
        allowed_values = [l.value for l in allowed_levels]

        return [
            f for f in facts
            if f.get("privacy_level", "private") in allowed_values
        ]

    def _get_allowed_privacy_levels(
        self,
        owner_person_id: str,
        audience_person_id: Optional[str]
    ) -> Set[PrivacyLevel]:
        """Determine which privacy levels are allowed for an audience."""
        # Owner can see everything
        if audience_person_id == owner_person_id:
            return {PrivacyLevel.PUBLIC, PrivacyLevel.PRIVATE, PrivacyLevel.SENSITIVE}

        # Public audience - only public
        if audience_person_id is None:
            return {PrivacyLevel.PUBLIC}

        # Different person - public only
        return {PrivacyLevel.PUBLIC}

    def _find_facts_in_content(
        self,
        content: str,
        person_id: str,
        allowed_levels: Set[PrivacyLevel]
    ) -> List[Dict[str, Any]]:
        """Find facts in content that need filtering."""
        with self._session() as session:
            if session is None:
                return []

            cypher = """
            MATCH (f:Fact {person_id: $person_id})
            WHERE f.fact_value IS NOT NULL
            RETURN f.id as id, f.fact_key as key, f.fact_value as value,
                   f.privacy_level as privacy
            """

            result = session.run(cypher, person_id=person_id)
            facts_in_content = []

            for record in result:
                value = record["value"]
                if value and value in content:
                    facts_in_content.append({
                        "id": record["id"],
                        "key": record["key"],
                        "value": value,
                        "privacy": record["privacy"]
                    })

            return facts_in_content

    def check_content_privacy(
        self,
        content: str,
        target_privacy: PrivacyLevel = PrivacyLevel.PUBLIC
    ) -> Dict[str, Any]:
        """
        Check if content contains potentially sensitive information.
        
        Args:
            content: Content to check
            target_privacy: Target privacy level for the content
            
        Returns:
            Analysis result with warnings
        """
        warnings = []
        detected_keywords = []

        # Check for sensitive keywords
        keywords = self.policy.sensitive_keywords or self.DEFAULT_SENSITIVE_KEYWORDS
        content_lower = content.lower()

        for keyword in keywords:
            if keyword.lower() in content_lower:
                detected_keywords.append(keyword)
                warnings.append(f"Detected sensitive keyword: '{keyword}'")

        # Check for patterns (email, phone, etc.)
        import re

        # Email pattern
        if re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', content):
            warnings.append("Detected email address")
            detected_keywords.append("email")

        # Phone pattern
        if re.search(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', content):
            warnings.append("Detected phone number")
            detected_keywords.append("phone")

        # SSN pattern
        if re.search(r'\b\d{3}-\d{2}-\d{4}\b', content):
            warnings.append("Detected potential SSN")
            detected_keywords.append("ssn")

        is_safe = len(warnings) == 0 or target_privacy != PrivacyLevel.PUBLIC

        return {
            "is_safe": is_safe,
            "warnings": warnings,
            "detected_keywords": detected_keywords,
            "target_privacy": target_privacy.value,
            "recommendation": "PRIVATE" if warnings and target_privacy == PrivacyLevel.PUBLIC else target_privacy.value
        }

    # ===================================================================
    # Audit Logging
    # ===================================================================

    def _audit_access(
        self,
        person_id: str,
        fact_id: Optional[str],
        action: AccessAction,
        accessed_by: str,
        privacy_level: PrivacyLevel,
        context: str,
        recipient: Optional[str] = None,
        was_filtered: bool = False
    ) -> Optional[AuditEntry]:
        """Record an audit entry for sensitive data access."""
        if not self.policy.enable_audit_logging:
            return None

        # Skip audit for PUBLIC data unless sharing
        if privacy_level == PrivacyLevel.PUBLIC and action != AccessAction.SHARE:
            return None

        audit_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        retain_until = now + timedelta(days=self.policy.retain_audit_logs_days)

        with self._session() as session:
            if session is None:
                return None

            cypher = """
            CREATE (a:AuditLog {
                id: $audit_id,
                person_id: $person_id,
                fact_id: $fact_id,
                action: $action,
                accessed_by: $accessed_by,
                accessed_at: $now,
                privacy_level: $privacy_level,
                context: $context,
                recipient: $recipient,
                was_filtered: $was_filtered,
                retain_until: $retain_until
            })
            WITH a
            MATCH (p:Person {id: $person_id})
            CREATE (p)-[:ACCESS_AUDIT {at: $now}]->(a)
            RETURN a
            """

            try:
                result = session.run(
                    cypher,
                    audit_id=audit_id,
                    person_id=person_id,
                    fact_id=fact_id,
                    action=action.value,
                    accessed_by=accessed_by,
                    now=now,
                    privacy_level=privacy_level.value,
                    context=context,
                    recipient=recipient,
                    was_filtered=was_filtered,
                    retain_until=retain_until
                )
                record = result.single()
                if record:
                    return self._record_to_audit_entry(record["a"])
            except Exception as e:
                logger.error(f"Failed to create audit entry: {e}")

        return None

    def log_access(
        self,
        person_id: str,
        action: AccessAction,
        accessed_by: str,
        context: str,
        fact_id: Optional[str] = None,
        privacy_level: PrivacyLevel = PrivacyLevel.PRIVATE
    ) -> Optional[AuditEntry]:
        """Public method to log data access."""
        return self._audit_access(
            person_id=person_id,
            fact_id=fact_id,
            action=action,
            accessed_by=accessed_by,
            privacy_level=privacy_level,
            context=context
        )

    def get_audit_log(
        self,
        person_id: Optional[str] = None,
        action: Optional[AccessAction] = None,
        accessed_by: Optional[str] = None,
        days: int = 30,
        limit: int = 100
    ) -> List[AuditEntry]:
        """
        Retrieve audit log entries.
        
        Args:
            person_id: Filter by person
            action: Filter by action type
            accessed_by: Filter by accessor
            days: Look back period
            limit: Maximum entries
        """
        with self._session() as session:
            if session is None:
                return []

            # Build filters
            conditions = ["a.accessed_at >= $since"]
            params = {
                "since": datetime.now(timezone.utc) - timedelta(days=days),
                "limit": limit
            }

            if person_id:
                conditions.append("a.person_id = $person_id")
                params["person_id"] = person_id

            if action:
                conditions.append("a.action = $action")
                params["action"] = action.value

            if accessed_by:
                conditions.append("a.accessed_by = $accessed_by")
                params["accessed_by"] = accessed_by

            where_clause = " AND ".join(conditions)

            cypher = f"""
            MATCH (a:AuditLog)
            WHERE {where_clause}
            RETURN a
            ORDER BY a.accessed_at DESC
            LIMIT $limit
            """

            result = session.run(cypher, **params)
            return [self._record_to_audit_entry(record["a"]) for record in result]

    def get_access_summary(
        self,
        person_id: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """Get summary of access to a person's data."""
        with self._session() as session:
            if session is None:
                return {}

            cypher = """
            MATCH (a:AuditLog {person_id: $person_id})
            WHERE a.accessed_at >= $since
            RETURN 
                count(a) as total_accesses,
                count(CASE WHEN a.privacy_level = 'sensitive' THEN 1 END) as sensitive_accesses,
                count(CASE WHEN a.was_filtered = true THEN 1 END) as filtered_count,
                count(DISTINCT a.accessed_by) as unique_accessors,
                collect(DISTINCT a.action) as actions
            """

            result = session.run(
                cypher,
                person_id=person_id,
                since=datetime.now(timezone.utc) - timedelta(days=days)
            )

            record = result.single()
            if record:
                return {
                    "person_id": person_id,
                    "period_days": days,
                    "total_accesses": record["total_accesses"],
                    "sensitive_accesses": record["sensitive_accesses"],
                    "filtered_count": record["filtered_count"],
                    "unique_accessors": record["unique_accessors"],
                    "actions": record["actions"]
                }
            return {}

    # ===================================================================
    # Data Retention
    # ===================================================================

    def purge_expired_audit_logs(self, batch_size: int = 1000) -> int:
        """Remove audit logs past retention period."""
        with self._session() as session:
            if session is None:
                return 0

            cypher = """
            MATCH (a:AuditLog)
            WHERE a.retain_until < datetime()
            WITH a LIMIT $batch_size
            DETACH DELETE a
            RETURN count(a) as deleted
            """

            result = session.run(cypher, batch_size=batch_size)
            record = result.single()
            deleted = record["deleted"] if record else 0

            if deleted > 0:
                logger.info(f"Purged {deleted} expired audit log entries")

            return deleted

    def archive_old_conversations(self, days: Optional[int] = None) -> int:
        """
        Archive conversations older than retention period.
        
        Returns:
            Number of conversations archived
        """
        days = days or self.policy.auto_archive_conversations_days

        with self._session() as session:
            if session is None:
                return 0

            cypher = """
            MATCH (c:Conversation)
            WHERE c.timestamp < datetime() - duration({days: $days})
              AND c.archived = true
            WITH c LIMIT $batch_size
            SET c.archived = true,
                c.archived_at = datetime(),
                c.content_snippet = left(c.content_snippet, 200) + "..."
            RETURN count(c) as archived
            """

            result = session.run(cypher, days=days, batch_size=1000)
            record = result.single()
            return record["archived"] if record else 0

    # ===================================================================
    # Utility Methods
    # ===================================================================

    def _record_to_audit_entry(self, record: Any) -> AuditEntry:
        """Convert Neo4j record to AuditEntry."""
        return AuditEntry(
            id=record.get("id", ""),
            person_id=record.get("person_id", ""),
            fact_id=record.get("fact_id"),
            action=AccessAction(record.get("action", "read")),
            accessed_by=record.get("accessed_by", ""),
            accessed_at=record.get("accessed_at"),
            privacy_level=PrivacyLevel(record.get("privacy_level", "private")),
            context=record.get("context", ""),
            recipient=record.get("recipient"),
            was_filtered=record.get("was_filtered", False),
            retain_until=record.get("retain_until")
        )


# =============================================================================
# Convenience Functions
# =============================================================================

def create_privacy_guard(
    neo4j_uri: str = "bolt://localhost:7687",
    neo4j_username: str = "neo4j",
    neo4j_password: Optional[str] = None,
    policy: Optional[PrivacyPolicy] = None
) -> PrivacyGuard:
    """Create and initialize PrivacyGuard."""
    guard = PrivacyGuard(
        neo4j_uri=neo4j_uri,
        neo4j_username=neo4j_username,
        neo4j_password=neo4j_password,
        policy=policy
    )
    guard.initialize()
    return guard


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    import os

    logging.basicConfig(level=logging.INFO)

    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    password = os.environ.get("NEO4J_PASSWORD")

    guard = PrivacyGuard(neo4j_uri=uri, neo4j_password=password)

    if guard.initialize():
        # Check content privacy
        result = guard.check_content_privacy(
            "My email is user@example.com and I live at 123 Main St",
            target_privacy=PrivacyLevel.PUBLIC
        )
        print(f"Privacy check: {result}")

        # Filter content
        filtered = guard.filter_content_for_audience(
            content="Alice's password is secret123 and she likes pizza",
            owner_person_id="signal:alice",
            audience_person_id="signal:bob",
            accessed_by="kurultai"
        )
        print(f"Filtered: {filtered.filtered_content}")
        print(f"Was modified: {filtered.was_modified}")

        # Get audit log
        audit = guard.get_audit_log(days=7)
        print(f"Audit entries: {len(audit)}")

    guard.close()
