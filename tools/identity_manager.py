"""Identity Manager - Core identity tracking for Kurultai.

This module provides comprehensive identity management:
- Detect and track people from messages
- Extract and store facts with privacy levels
- Manage person profiles across channels
- Link conversations to identities
"""

import logging
import uuid
import hashlib
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from contextlib import contextmanager

# Configure logging
logger = logging.getLogger(__name__)


class PrivacyLevel(Enum):
    """Privacy levels for facts and preferences."""
    PUBLIC = "public"       # Can be shared freely
    PRIVATE = "private"     # Only for the person themselves
    SENSITIVE = "sensitive" # Requires explicit authorization


class FactType(Enum):
    """Types of facts that can be stored."""
    IDENTITY = "identity"       # Name, handle, contact info
    PREFERENCE = "preference"   # User preferences
    HABIT = "habit"            # Recurring behaviors
    RELATIONSHIP = "relationship"  # Relationships to others
    SKILL = "skill"            # Known skills/capabilities
    INTEREST = "interest"      # Topics of interest
    GOAL = "goal"              # Stated goals
    CONSTRAINT = "constraint"  # Limitations/requirements
    CONTEXT = "context"        # Situational context
    OTHER = "other"            # Uncategorized


@dataclass
class PersonIdentity:
    """Represents a person's identity across channels."""
    id: str                                    # Unique ID (channel:handle)
    name: Optional[str] = None                 # Display name
    handle: Optional[str] = None               # Channel handle/identifier
    channel: Optional[str] = None              # Channel type (signal, discord, etc.)
    email: Optional[str] = None                # Email if known
    phone: Optional[str] = None                # Phone if known
    first_seen: Optional[datetime] = None      # When first encountered
    last_seen: Optional[datetime] = None       # When last active
    total_conversations: int = 0               # Count of conversations
    is_active: bool = True                     # Whether identity is active
    sender_hash: Optional[str] = None          # For sender isolation
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Ensure datetime fields are timezone-aware."""
        if self.first_seen and self.first_seen.tzinfo is None:
            self.first_seen = self.first_seen.replace(tzinfo=timezone.utc)
        if self.last_seen and self.last_seen.tzinfo is None:
            self.last_seen = self.last_seen.replace(tzinfo=timezone.utc)


@dataclass
class Fact:
    """A fact about a person with privacy and confidence metadata."""
    id: str
    person_id: str
    fact_type: FactType
    fact_key: str
    fact_value: str
    privacy_level: PrivacyLevel
    confidence: float                        # 0.0 to 1.0
    source: str                             # Where fact came from
    created_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime] = None    # Optional expiration
    verification_count: int = 0              # Times confirmed
    contradicted_by: Optional[str] = None    # ID of contradicting fact


@dataclass
class PersonContext:
    """Context information for a person in a conversation."""
    person: PersonIdentity
    recent_facts: List[Fact] = field(default_factory=list)
    preferences: Dict[str, str] = field(default_factory=dict)
    current_topics: List[str] = field(default_factory=list)
    conversation_history: List[Dict] = field(default_factory=list)


class IdentityManager:
    """
    Manages person identities, facts, and privacy levels.
    
    Integrates with Neo4j for persistent storage and provides
    a clean API for identity tracking across all channels.
    """

    def __init__(
        self,
        neo4j_uri: str = "bolt://localhost:7687",
        neo4j_username: str = "neo4j",
        neo4j_password: Optional[str] = None,
        database: str = "neo4j",
        fallback_mode: bool = True
    ):
        self.neo4j_uri = neo4j_uri
        self.neo4j_username = neo4j_username
        self.neo4j_password = neo4j_password
        self.database = database
        self.fallback_mode = fallback_mode
        self._driver = None
        self._initialized = False

        # Lazy import Neo4j
        self._import_neo4j()

    def _import_neo4j(self):
        """Lazy import Neo4j to avoid import issues."""
        try:
            from neo4j import GraphDatabase
            from neo4j.exceptions import ServiceUnavailable, Neo4jError
            self._GraphDatabase = GraphDatabase
            self._ServiceUnavailable = ServiceUnavailable
            self._Neo4jError = Neo4jError
        except ImportError:
            logger.warning("Neo4j driver not available")
            self._GraphDatabase = None

    def initialize(self) -> bool:
        """Initialize Neo4j connection."""
        if self._GraphDatabase is None:
            logger.error("Neo4j driver not available")
            return False

        if self.neo4j_password is None:
            if not self.fallback_mode:
                raise ValueError("Neo4j password is required")
            logger.warning("No Neo4j password provided, operating in fallback mode")
            return False

        try:
            self._driver = self._GraphDatabase.driver(
                self.neo4j_uri,
                auth=(self.neo4j_username, self.neo4j_password)
            )
            self._driver.verify_connectivity()
            self._initialized = True
            logger.info("IdentityManager initialized successfully")
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
    # Person Identity Operations
    # ===================================================================

    def get_or_create_person(
        self,
        channel: str,
        handle: str,
        name: Optional[str] = None,
        sender_hash: Optional[str] = None,
        **metadata
    ) -> PersonIdentity:
        """
        Get existing person or create new identity.
        
        Args:
            channel: Channel type (signal, discord, slack, etc.)
            handle: Channel-specific identifier
            name: Display name if known
            sender_hash: For sender isolation
            **metadata: Additional metadata
            
        Returns:
            PersonIdentity object
        """
        person_id = f"{channel}:{handle}"
        now = datetime.now(timezone.utc)

        with self._session() as session:
            if session is None:
                # Fallback mode - return in-memory identity
                return PersonIdentity(
                    id=person_id,
                    name=name or handle,
                    handle=handle,
                    channel=channel,
                    first_seen=now,
                    last_seen=now,
                    sender_hash=sender_hash,
                    metadata=metadata
                )

            cypher = """
            MERGE (p:Person {id: $person_id})
            ON CREATE SET
                p.name = $name,
                p.handle = $handle,
                p.channel = $channel,
                p.first_seen = $now,
                p.last_seen = $now,
                p.total_conversations = 0,
                p.is_active = true,
                p.sender_hash = $sender_hash,
                p.created_at = $now,
                p.metadata = $metadata
            ON MATCH SET
                p.last_seen = $now,
                p.name = COALESCE($name, p.name),
                p.sender_hash = COALESCE($sender_hash, p.sender_hash),
                p.metadata = apoc.map.merge(p.metadata, $metadata)
            RETURN p
            """

            try:
                result = session.run(
                    cypher,
                    person_id=person_id,
                    name=name or handle,
                    handle=handle,
                    channel=channel,
                    now=now,
                    sender_hash=sender_hash,
                    metadata=str(metadata) if metadata else "{}"
                )
                record = result.single()
                if record:
                    return self._record_to_person(record["p"])
            except Exception as e:
                logger.error(f"Error getting/creating person: {e}")
                if not self.fallback_mode:
                    raise

        # Fallback
        return PersonIdentity(
            id=person_id,
            name=name or handle,
            handle=handle,
            channel=channel,
            first_seen=now,
            last_seen=now,
            sender_hash=sender_hash,
            metadata=metadata
        )

    def get_person(self, person_id: str) -> Optional[PersonIdentity]:
        """Get person by ID."""
        with self._session() as session:
            if session is None:
                return None

            cypher = "MATCH (p:Person {id: $person_id}) RETURN p"
            result = session.run(cypher, person_id=person_id)
            record = result.single()
            if record:
                return self._record_to_person(record["p"])
            return None

    def update_person(
        self,
        person_id: str,
        **updates
    ) -> Optional[PersonIdentity]:
        """Update person fields."""
        with self._session() as session:
            if session is None:
                return None

            # Build SET clause
            set_clauses = []
            params = {"person_id": person_id, "now": datetime.now(timezone.utc)}
            for key, value in updates.items():
                if key in ["name", "email", "phone", "is_active", "metadata"]:
                    set_clauses.append(f"p.{key} = ${key}")
                    params[key] = value

            if not set_clauses:
                return self.get_person(person_id)

            cypher = f"""
            MATCH (p:Person {{id: $person_id}})
            SET {', '.join(set_clauses)}, p.updated_at = $now
            RETURN p
            """

            result = session.run(cypher, **params)
            record = result.single()
            if record:
                return self._record_to_person(record["p"])
            return None

    def increment_conversation_count(self, person_id: str) -> int:
        """Increment total conversations for a person."""
        with self._session() as session:
            if session is None:
                return 0

            cypher = """
            MATCH (p:Person {id: $person_id})
            SET p.total_conversations = COALESCE(p.total_conversations, 0) + 1
            RETURN p.total_conversations as count
            """
            result = session.run(cypher, person_id=person_id)
            record = result.single()
            return record["count"] if record else 0

    def find_persons_by_name(self, name: str, limit: int = 10) -> List[PersonIdentity]:
        """Find persons by name (fuzzy match)."""
        with self._session() as session:
            if session is None:
                return []

            cypher = """
            MATCH (p:Person)
            WHERE p.name CONTAINS $name OR p.handle CONTAINS $name
            RETURN p
            LIMIT $limit
            """
            result = session.run(cypher, name=name, limit=limit)
            return [self._record_to_person(record["p"]) for record in result]

    # ===================================================================
    # Fact Operations
    # ===================================================================

    def add_fact(
        self,
        person_id: str,
        fact_type: FactType,
        key: str,
        value: str,
        privacy_level: PrivacyLevel = PrivacyLevel.PRIVATE,
        confidence: float = 0.8,
        source: str = "conversation",
        expires_days: Optional[int] = None
    ) -> Fact:
        """
        Add a fact about a person.
        
        Args:
            person_id: Person's unique ID
            fact_type: Type of fact
            key: Fact key/category
            value: Fact value
            privacy_level: Privacy classification
            confidence: Confidence level (0.0-1.0)
            source: Source of the fact
            expires_days: Optional expiration in days
            
        Returns:
            Created Fact object
        """
        fact_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        expires_at = None
        if expires_days:
            from datetime import timedelta
            expires_at = now + timedelta(days=expires_days)

        with self._session() as session:
            if session is None:
                return Fact(
                    id=fact_id,
                    person_id=person_id,
                    fact_type=fact_type,
                    fact_key=key,
                    fact_value=value,
                    privacy_level=privacy_level,
                    confidence=confidence,
                    source=source,
                    created_at=now,
                    updated_at=now,
                    expires_at=expires_at
                )

            cypher = """
            MATCH (p:Person {id: $person_id})
            CREATE (f:Fact {
                id: $fact_id,
                person_id: $person_id,
                fact_type: $fact_type,
                fact_key: $fact_key,
                fact_value: $fact_value,
                privacy_level: $privacy_level,
                confidence: $confidence,
                source: $source,
                created_at: $now,
                updated_at: $now,
                expires_at: $expires_at,
                verification_count: 0
            })
            CREATE (p)-[:HAS_FACT {created_at: $now}]->(f)
            RETURN f
            """

            result = session.run(
                cypher,
                person_id=person_id,
                fact_id=fact_id,
                fact_type=fact_type.value,
                fact_key=key,
                fact_value=value,
                privacy_level=privacy_level.value,
                confidence=confidence,
                source=source,
                now=now,
                expires_at=expires_at
            )
            record = result.single()
            if record:
                return self._record_to_fact(record["f"])

        # Fallback
        return Fact(
            id=fact_id,
            person_id=person_id,
            fact_type=fact_type,
            fact_key=key,
            fact_value=value,
            privacy_level=privacy_level,
            confidence=confidence,
            source=source,
            created_at=now,
            updated_at=now,
            expires_at=expires_at
        )

    def get_facts(
        self,
        person_id: str,
        fact_type: Optional[FactType] = None,
        privacy_levels: Optional[List[PrivacyLevel]] = None,
        min_confidence: float = 0.0,
        limit: int = 50
    ) -> List[Fact]:
        """
        Get facts about a person with optional filtering.
        
        Args:
            person_id: Person's unique ID
            fact_type: Optional type filter
            privacy_levels: List of allowed privacy levels
            min_confidence: Minimum confidence threshold
            limit: Maximum results
            
        Returns:
            List of Fact objects
        """
        with self._session() as session:
            if session is None:
                return []

            # Build filters
            filters = ["f.person_id = $person_id"]
            params = {
                "person_id": person_id,
                "min_confidence": min_confidence,
                "limit": limit
            }

            if fact_type:
                filters.append("f.fact_type = $fact_type")
                params["fact_type"] = fact_type.value

            if privacy_levels:
                filters.append("f.privacy_level IN $privacy_levels")
                params["privacy_levels"] = [p.value for p in privacy_levels]

            where_clause = " AND ".join(filters)

            cypher = f"""
            MATCH (f:Fact)
            WHERE {where_clause}
              AND f.confidence >= $min_confidence
              AND (f.expires_at IS NULL OR f.expires_at > datetime())
            RETURN f
            ORDER BY f.confidence DESC, f.created_at DESC
            LIMIT $limit
            """

            result = session.run(cypher, **params)
            return [self._record_to_fact(record["f"]) for record in result]

    def update_fact_confidence(self, fact_id: str, new_confidence: float) -> bool:
        """Update fact confidence."""
        with self._session() as session:
            if session is None:
                return False

            cypher = """
            MATCH (f:Fact {id: $fact_id})
            SET f.confidence = $new_confidence,
                f.verification_count = COALESCE(f.verification_count, 0) + 1,
                f.updated_at = datetime()
            RETURN f.id
            """
            result = session.run(cypher, fact_id=fact_id, new_confidence=new_confidence)
            return result.single() is not None

    def delete_fact(self, fact_id: str) -> bool:
        """Delete a fact."""
        with self._session() as session:
            if session is None:
                return False

            cypher = """
            MATCH (f:Fact {id: $fact_id})
            DETACH DELETE f
            RETURN count(f) as deleted
            """
            result = session.run(cypher, fact_id=fact_id)
            record = result.single()
            return record["deleted"] > 0 if record else False

    # ===================================================================
    # Context Building
    # ===================================================================

    def get_person_context(
        self,
        person_id: str,
        include_private: bool = False,
        include_sensitive: bool = False
    ) -> Optional[PersonContext]:
        """
        Build comprehensive context for a person.
        
        Args:
            person_id: Person's unique ID
            include_private: Whether to include private facts
            include_sensitive: Whether to include sensitive facts
            
        Returns:
            PersonContext with all relevant information
        """
        person = self.get_person(person_id)
        if not person:
            return None

        # Determine which privacy levels to include
        privacy_levels = [PrivacyLevel.PUBLIC]
        if include_private:
            privacy_levels.append(PrivacyLevel.PRIVATE)
        if include_sensitive:
            privacy_levels.append(PrivacyLevel.SENSITIVE)

        # Get facts
        facts = self.get_facts(
            person_id=person_id,
            privacy_levels=privacy_levels,
            min_confidence=0.5,
            limit=20
        )

        # Get preferences
        preferences = self._get_preferences_dict(person_id)

        return PersonContext(
            person=person,
            recent_facts=facts,
            preferences=preferences
        )

    def _get_preferences_dict(self, person_id: str) -> Dict[str, str]:
        """Get preferences as a simple dict."""
        with self._session() as session:
            if session is None:
                return {}

            cypher = """
            MATCH (p:Preference {person_id: $person_id})
            WHERE p.expires_at IS NULL OR p.expires_at > datetime()
            RETURN p.pref_key as key, p.pref_value as value
            ORDER BY p.updated_at DESC
            """
            result = session.run(cypher, person_id=person_id)
            return {record["key"]: record["value"] for record in result}

    # ===================================================================
    # Utility Methods
    # ===================================================================

    def _record_to_person(self, record: Any) -> PersonIdentity:
        """Convert Neo4j record to PersonIdentity."""
        return PersonIdentity(
            id=record.get("id", ""),
            name=record.get("name"),
            handle=record.get("handle"),
            channel=record.get("channel"),
            email=record.get("email"),
            phone=record.get("phone"),
            first_seen=record.get("first_seen"),
            last_seen=record.get("last_seen"),
            total_conversations=record.get("total_conversations", 0),
            is_active=record.get("is_active", True),
            sender_hash=record.get("sender_hash"),
            metadata=self._parse_metadata(record.get("metadata", "{}"))
        )

    def _record_to_fact(self, record: Any) -> Fact:
        """Convert Neo4j record to Fact."""
        return Fact(
            id=record.get("id", ""),
            person_id=record.get("person_id", ""),
            fact_type=FactType(record.get("fact_type", "other")),
            fact_key=record.get("fact_key", ""),
            fact_value=record.get("fact_value", ""),
            privacy_level=PrivacyLevel(record.get("privacy_level", "private")),
            confidence=record.get("confidence", 0.5),
            source=record.get("source", "unknown"),
            created_at=record.get("created_at"),
            updated_at=record.get("updated_at"),
            expires_at=record.get("expires_at"),
            verification_count=record.get("verification_count", 0),
            contradicted_by=record.get("contradicted_by")
        )

    def _parse_metadata(self, metadata_str: str) -> Dict[str, Any]:
        """Parse metadata string to dict."""
        import json
        try:
            if isinstance(metadata_str, dict):
                return metadata_str
            return json.loads(metadata_str.replace("'", '"'))
        except:
            return {}

    # ===================================================================
    # Relationship Methods (Integration with Relationship Tracking System)
    # ===================================================================

    def record_relationship_fact(
        self,
        person_id: str,
        related_person: str,
        relationship_type: str,
        strength: float = 0.5,
        context: str = "",
        confidence: float = 0.5
    ) -> Optional[Any]:
        """
        Record a relationship fact about a person.
        
        This integrates with the relationship tracking system by storing
        relationship information as a fact with RELATIONSHIP type.
        
        Args:
            person_id: Person's unique ID
            related_person: Name or ID of related person
            relationship_type: Type of relationship (friend, colleague, etc.)
            strength: Relationship strength 0.0-1.0
            context: Additional context
            confidence: Confidence in this fact
            
        Returns:
            Created Fact object or None
        """
        fact_value = f"{relationship_type}:{related_person}:{strength:.2f}"
        if context:
            fact_value += f":{context[:100]}"
            
        return self.add_fact(
            person_id=person_id,
            fact_type=FactType.RELATIONSHIP,
            key=f"knows_{related_person.lower().replace(' ', '_')}",
            value=fact_value,
            privacy_level=PrivacyLevel.PRIVATE,
            confidence=confidence
        )

    def get_relationship_facts(
        self,
        person_id: str,
        min_confidence: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        Get all relationship facts for a person.
        
        Args:
            person_id: Person's unique ID
            min_confidence: Minimum confidence threshold
            
        Returns:
            List of parsed relationship facts
        """
        facts = self.get_facts(
            person_id=person_id,
            fact_type=FactType.RELATIONSHIP,
            min_confidence=min_confidence,
            limit=50
        )
        
        relationships = []
        for fact in facts:
            # Parse fact value: "type:person:strength:context"
            parts = fact.fact_value.split(":")
            if len(parts) >= 3:
                relationships.append({
                    "related_person": parts[1],
                    "relationship_type": parts[0],
                    "strength": float(parts[2]),
                    "context": parts[3] if len(parts) > 3 else "",
                    "confidence": fact.confidence,
                    "discovered_at": fact.created_at
                })
        
        return relationships

    def get_primary_human_relationship(
        self,
        person_id: str,
        primary_human: str = "Danny"
    ) -> Optional[Dict[str, Any]]:
        """
        Get a person's relationship to the primary human.
        
        Args:
            person_id: Person's unique ID
            primary_human: Name of primary human (default: Danny)
            
        Returns:
            Relationship dict or None
        """
        relationships = self.get_relationship_facts(person_id)
        
        for rel in relationships:
            if rel["related_person"].lower() == primary_human.lower():
                return rel
        
        return None


# =============================================================================
# Convenience Functions
# =============================================================================

def create_identity_manager(
    neo4j_uri: str = "bolt://localhost:7687",
    neo4j_username: str = "neo4j",
    neo4j_password: Optional[str] = None
) -> IdentityManager:
    """Create and initialize an IdentityManager."""
    manager = IdentityManager(
        neo4j_uri=neo4j_uri,
        neo4j_username=neo4j_username,
        neo4j_password=neo4j_password
    )
    manager.initialize()
    return manager


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    import os

    # Example usage
    logging.basicConfig(level=logging.INFO)

    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    password = os.environ.get("NEO4J_PASSWORD")

    manager = IdentityManager(neo4j_uri=uri, neo4j_password=password)

    if manager.initialize():
        # Create or get person
        person = manager.get_or_create_person(
            channel="signal",
            handle="+1234567890",
            name="Alice"
        )
        print(f"Person: {person.name} ({person.id})")

        # Add some facts
        fact = manager.add_fact(
            person_id=person.id,
            fact_type=FactType.PREFERENCE,
            key="communication_style",
            value="direct",
            privacy_level=PrivacyLevel.PUBLIC,
            confidence=0.9
        )
        print(f"Added fact: {fact.fact_key} = {fact.fact_value}")

        # Get context
        context = manager.get_person_context(person.id, include_private=True)
        print(f"Context has {len(context.recent_facts)} facts")

    manager.close()
