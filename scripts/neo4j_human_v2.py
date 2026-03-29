#!/usr/bin/env python3
"""
Neo4j Human V2 — Channel-decoupled Human + Identifier CRUD operations.

Schema:
- (:Human {id, displayName, confidence, firstKnown, source, lastContact, status})
- (:Identifier {type, value, verified, addedAt, source})

Relationships:
- (Human)-[:IDENTIFIED_BY]->(Identifier)
- (Human)-[:KNOWN_THROUGH {context, since}]->(Human)
- (Human)-[:RELATED_TO {relationship}]->(Human)

Usage:
    from neo4j_human_v2 import HumanStoreV2
    store = HumanStoreV2()
    human = store.create_human("Danny", source="signal")
    store.add_identifier(human["id"], "SIGNAL_PHONE", "+19194133445")
"""

import os
import sys
import uuid
import logging
import hashlib
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import get_driver

logger = logging.getLogger(__name__)

# Identifier types
IDENTIFIER_TYPES = {
    "SIGNAL_PHONE",
    "EMAIL",
    "GITHUB",
    "TELEGRAM",
    "DISPLAY_NAME",
    "NAME_VARIANT",
}


# Allowed fields for update_human (prevents Cypher injection via kwargs)
ALLOWED_HUMAN_FIELDS = {
    "displayName", "confidence", "status", "source", "timezone",
    "lastContact", "proactiveSkipCount", "lastProactiveAt",
}

# Phone hashing configuration for PII protection
_PHONE_HASH_SALT = os.environ.get('PHONE_HASH_SALT', '')
if not _PHONE_HASH_SALT:
    raise ValueError(
        "PHONE_HASH_SALT environment variable must be set for PII protection. "
        "Generate with: python3 -c 'import secrets; print(secrets.token_hex(32))'"
    )


def hash_phone(phone: str) -> str:
    """
    Hash a phone number using HMAC-SHA256 with salt.

    This provides one-way encryption for PII while maintaining lookup ability.
    Same phone number will always produce the same hash (deterministic).

    Args:
        phone: Phone number in E.164 format (e.g., +1234567890)

    Returns:
        64-character hexadecimal string (SHA256 hash)

    Raises:
        ValueError: If phone is empty
    """
    if not phone:
        raise ValueError("Phone number cannot be empty")

    # Normalize to E.164 format if not already
    normalized = phone.strip()
    if not normalized.startswith('+'):
        # Assume US number if no country code
        normalized = '+1' + normalized

    # HMAC-SHA256 hash with salt
    import hmac
    h = hmac.new(_PHONE_HASH_SALT.encode('utf-8'), normalized.encode('utf-8'), hashlib.sha256)
    return h.hexdigest()


def redact_phone(phone: str) -> str:
    """
    Redact phone number for API responses: +1***7890 format.

    Args:
        phone: Phone number in E.164 format (e.g., +1234567890)

    Returns:
        Redacted phone number showing only country code and last 4 digits
    """
    if not phone or len(phone) < 4:
        return '***'
    return f"{phone[:2]}***{phone[-4:]}"

class HumanStoreV2:
    """CRUD operations for Human + Identifier nodes in Neo4j."""

    def __init__(self):
        self.driver = get_driver()

    def close(self):
        # Don't call close_driver() — let the atexit handler manage lifecycle
        self.driver = None

    @staticmethod
    def _is_valid_uuid(id_string: str) -> bool:
        """Check if a string is a valid UUID format.

        Args:
            id_string: String to validate

        Returns:
            True if valid UUID format, False otherwise
        """
        try:
            uuid.UUID(id_string)
            return True
        except (ValueError, AttributeError):
            return False

    # =========================================================================
    # Human CRUD
    # =========================================================================

    def create_human(
        self,
        display_name: str,
        source: str = "signal",
        confidence: float = 1.0,
        human_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new Human node with a UUID.

        Args:
            display_name: Display name for the human
            source: Source system (default: "signal")
            confidence: Confidence score (default: 1.0)
            human_id: Optional UUID string. If provided, must be a valid UUID format.
                      Use find_or_create_by_phone() for phone-based human creation.

        Returns:
            Dict with created human data

        Raises:
            ValueError: If human_id is provided but not a valid UUID format
        """
        # Validate human_id if provided (defensive measure to prevent slug-based IDs)
        if human_id is not None:
            if not self._is_valid_uuid(human_id):
                raise ValueError(
                    f"Human ID must be UUID format, got '{human_id}'. "
                    "Use find_or_create_by_phone() to create Human nodes from phone numbers."
                )
            # Use the provided valid UUID
            final_human_id = human_id
        else:
            # Generate new UUID (default behavior)
            final_human_id = str(uuid.uuid4())

        with self.driver.session() as session:
            result = session.run(
                """
                CREATE (h:Human {
                    id: $id,
                    displayName: $displayName,
                    confidence: $confidence,
                    firstKnown: datetime(),
                    source: $source,
                    lastContact: datetime(),
                    status: 'active',
                    createdAt: datetime(),
                    updatedAt: datetime()
                })
                RETURN h.id AS id, h.displayName AS displayName,
                       h.source AS source, h.status AS status
                """,
                id=final_human_id,
                displayName=display_name,
                confidence=confidence,
                source=source,
            )
            record = result.single()
            human_data = dict(record) if record else {}

            # Auto-grant all consent categories (opt-out model — humans consent by default)
            if human_data.get("id"):
                self._grant_default_consent(human_data["id"])

            return human_data

    @staticmethod
    def _grant_default_consent(human_id: str) -> None:
        """Grant all consent categories to a new human (opt-out model)."""
        try:
            from consent_decorator import grant_consent, ALL_CATEGORIES
            for category in ALL_CATEGORIES:
                grant_consent(human_id, category, source="auto_default")
        except Exception:
            pass  # Best-effort — don't block human creation

    def get_human(self, human_id: str) -> Optional[Dict[str, Any]]:
        """Get a Human by UUID with all identifiers."""
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (h:Human {id: $human_id})
                OPTIONAL MATCH (h)-[:IDENTIFIED_BY]->(i:Identifier)
                WITH h, collect({
                    type: i.type, value: i.value,
                    verified: i.verified, addedAt: toString(i.addedAt)
                }) AS identifiers
                RETURN h.id AS id, h.displayName AS displayName,
                       h.confidence AS confidence,
                       toString(h.firstKnown) AS firstKnown,
                       h.source AS source,
                       toString(h.lastContact) AS lastContact,
                       h.status AS status,
                       identifiers
                """,
                human_id=human_id,
            )
            record = result.single()
            if not record:
                return None
            data = dict(record)
            # Filter out null identifiers (from OPTIONAL MATCH with no results)
            data["identifiers"] = [
                i for i in data.get("identifiers", []) if i.get("type")
            ]
            return data

    def find_human_by_identifier(
        self, id_type: str, id_value: str
    ) -> Optional[Dict[str, Any]]:
        """Find a Human by any of their identifiers."""
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (h:Human)-[:IDENTIFIED_BY]->(i:Identifier {type: $type, value: $value})
                OPTIONAL MATCH (h)-[:IDENTIFIED_BY]->(allIds:Identifier)
                WITH h, collect({
                    type: allIds.type, value: allIds.value,
                    verified: allIds.verified
                }) AS identifiers
                RETURN h.id AS id, h.displayName AS displayName,
                       h.confidence AS confidence,
                       toString(h.firstKnown) AS firstKnown,
                       h.source AS source,
                       toString(h.lastContact) AS lastContact,
                       h.status AS status,
                       identifiers
                """,
                type=id_type,
                value=id_value,
            )
            record = result.single()
            if not record:
                return None
            data = dict(record)
            data["identifiers"] = [
                i for i in data.get("identifiers", []) if i.get("type")
            ]
            return data

    def find_or_create_by_phone(
        self, phone: str, display_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Find existing Human by phone or create new one. Atomic via MERGE.

        Phone numbers are stored as HMAC-SHA256 hashes for PII protection.
        The same phone number will always produce the same hash (deterministic).
        """
        # Hash phone before storage/lookup (PII protection)
        phone_hash = hash_phone(phone)

        # Store format hint for redaction (e.g., "+1" for US numbers)
        phone_format = phone[:2] if phone.startswith('+') else '+1'

        name = display_name or phone
        new_id = str(uuid.uuid4())

        with self.driver.session() as session:
            result = session.run(
                """
                MERGE (i:Identifier {type: 'SIGNAL_PHONE', value: $phone_hash})
                ON CREATE SET i.verified = true, i.addedAt = datetime(), i.source = 'signal',
                              i.formatHint = $phone_format
                WITH i
                OPTIONAL MATCH (existing:Human)-[:IDENTIFIED_BY]->(i)
                WITH i, existing
                // If no existing human, create one
                FOREACH (_ IN CASE WHEN existing IS NULL THEN [1] ELSE [] END |
                    CREATE (h:Human {
                        id: $new_id,
                        displayName: $name,
                        confidence: 1.0,
                        firstKnown: datetime(),
                        source: 'signal',
                        lastContact: datetime(),
                        status: 'active',
                        createdAt: datetime(),
                        updatedAt: datetime()
                    })
                    CREATE (h)-[:IDENTIFIED_BY]->(i)
                )
                // Re-match to get the human (existing or newly created)
                WITH i
                MATCH (h:Human)-[:IDENTIFIED_BY]->(i)
                SET h.lastContact = datetime(), h.updatedAt = datetime()
                WITH h
                OPTIONAL MATCH (h)-[:IDENTIFIED_BY]->(allIds:Identifier)
                WITH h, collect({
                    type: allIds.type, value: allIds.value,
                    verified: allIds.verified, formatHint: allIds.formatHint
                }) AS identifiers
                RETURN h.id AS id, h.displayName AS displayName,
                       h.confidence AS confidence,
                       toString(h.firstKnown) AS firstKnown,
                       h.source AS source,
                       toString(h.lastContact) AS lastContact,
                       h.status AS status,
                       identifiers
                """,
                phone_hash=phone_hash,
                phone_format=phone_format,
                new_id=new_id,
                name=name,
            )
            record = result.single()
            if not record:
                return {}
            data = dict(record)
            data["identifiers"] = [
                i for i in data.get("identifiers", []) if i.get("type")
            ]

            # Auto-grant consent for newly created humans
            if data.get("id") == new_id:
                self._grant_default_consent(new_id)

            return data

    def update_human(self, human_id: str, **fields) -> bool:
        """Update fields on a Human node."""
        if not fields:
            return False

        # Whitelist validation to prevent Cypher injection
        invalid = set(fields.keys()) - ALLOWED_HUMAN_FIELDS
        if invalid:
            logger.warning(f"update_human rejected invalid fields: {invalid}")
            fields = {k: v for k, v in fields.items() if k in ALLOWED_HUMAN_FIELDS}
            if not fields:
                return False

        set_parts = []
        params = {"human_id": human_id}
        for key, value in fields.items():
            safe_key = key.replace(" ", "_")
            set_parts.append(f"h.{safe_key} = ${safe_key}")
            params[safe_key] = value
        set_parts.append("h.updatedAt = datetime()")

        cypher = f"""
            MATCH (h:Human {{id: $human_id}})
            SET {', '.join(set_parts)}
            RETURN h.id AS id
        """
        with self.driver.session() as session:
            result = session.run(cypher, **params)
            return result.single() is not None

    def touch_contact(self, human_id: str) -> bool:
        """Update lastContact timestamp."""
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (h:Human {id: $human_id})
                SET h.lastContact = datetime(), h.updatedAt = datetime()
                RETURN h.id AS id
                """,
                human_id=human_id,
            )
            return result.single() is not None

    def list_humans(
        self,
        status: str = "active",
        source: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List humans with optional filters."""
        where_parts = ["h.status = $status"]
        params: Dict[str, Any] = {"status": status, "limit": limit, "skip": offset}
        if source:
            where_parts.append("h.source = $source")
            params["source"] = source

        cypher = f"""
            MATCH (h:Human)
            WHERE {' AND '.join(where_parts)}
            OPTIONAL MATCH (h)-[:IDENTIFIED_BY]->(i:Identifier)
            WITH h, collect({{type: i.type, value: i.value}}) AS identifiers
            RETURN h.id AS id, h.displayName AS displayName,
                   h.source AS source, h.confidence AS confidence,
                   toString(h.lastContact) AS lastContact,
                   identifiers
            ORDER BY h.lastContact DESC
            SKIP $skip LIMIT $limit
        """
        with self.driver.session() as session:
            result = session.run(cypher, **params)
            humans = []
            for record in result:
                data = dict(record)
                data["identifiers"] = [
                    i for i in data.get("identifiers", []) if i.get("type")
                ]
                humans.append(data)
            return humans

    # =========================================================================
    # Identifier CRUD
    # =========================================================================

    def add_identifier(
        self,
        human_id: str,
        id_type: str,
        id_value: str,
        verified: bool = False,
        source: str = "manual",
    ) -> bool:
        """Add an identifier to a Human."""
        if id_type not in IDENTIFIER_TYPES:
            raise ValueError(f"Invalid identifier type: {id_type}. Must be one of {IDENTIFIER_TYPES}")
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (h:Human {id: $human_id})
                MERGE (i:Identifier {type: $type, value: $value})
                ON CREATE SET i.verified = $verified,
                              i.addedAt = datetime(),
                              i.source = $source
                MERGE (h)-[:IDENTIFIED_BY]->(i)
                RETURN h.id AS id
                """,
                human_id=human_id,
                type=id_type,
                value=id_value,
                verified=verified,
                source=source,
            )
            return result.single() is not None

    def remove_identifier(self, human_id: str, id_type: str, id_value: str) -> bool:
        """Remove an identifier from a Human."""
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (h:Human {id: $human_id})-[r:IDENTIFIED_BY]->(i:Identifier {type: $type, value: $value})
                DELETE r
                WITH i
                WHERE NOT exists((i)<-[:IDENTIFIED_BY]-())
                DELETE i
                RETURN count(*) AS removed
                """,
                human_id=human_id,
                type=id_type,
                value=id_value,
            )
            return True

    def verify_identifier(self, human_id: str, id_type: str, id_value: str) -> bool:
        """Mark an identifier as verified."""
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (h:Human {id: $human_id})-[:IDENTIFIED_BY]->(i:Identifier {type: $type, value: $value})
                SET i.verified = true, i.verifiedAt = datetime()
                RETURN i.value AS value
                """,
                human_id=human_id,
                type=id_type,
                value=id_value,
            )
            return result.single() is not None

    # =========================================================================
    # Relationships
    # =========================================================================

    def add_known_through(
        self, human_id_a: str, human_id_b: str, context: str = "conversation"
    ) -> bool:
        """Create a KNOWN_THROUGH relationship between two Humans."""
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (a:Human {id: $id_a})
                MATCH (b:Human {id: $id_b})
                WHERE a <> b
                MERGE (a)-[r:KNOWN_THROUGH]->(b)
                ON CREATE SET r.context = $context, r.since = datetime()
                RETURN a.id AS id
                """,
                id_a=human_id_a,
                id_b=human_id_b,
                context=context,
            )
            return result.single() is not None

    def add_relationship(
        self, human_id_a: str, human_id_b: str, relationship: str
    ) -> bool:
        """Create a RELATED_TO relationship between two Humans."""
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (a:Human {id: $id_a})
                MATCH (b:Human {id: $id_b})
                WHERE a <> b
                MERGE (a)-[r:RELATED_TO]->(b)
                ON CREATE SET r.relationship = $relationship, r.since = datetime()
                ON MATCH SET r.relationship = $relationship
                RETURN a.id AS id
                """,
                id_a=human_id_a,
                id_b=human_id_b,
                relationship=relationship,
            )
            return result.single() is not None

    def get_social_graph(self, human_id: str, depth: int = 2) -> Dict[str, Any]:
        """Get the social network around a Human."""
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (h:Human {id: $human_id})
                CALL {
                    WITH h
                    MATCH path = (h)-[:KNOWN_THROUGH|RELATED_TO*1..""" + str(depth) + """]->(other:Human)
                    RETURN other, relationships(path) AS rels, length(path) AS dist
                }
                WITH other, rels, dist
                ORDER BY dist
                RETURN other.id AS id, other.displayName AS displayName,
                       other.source AS source, dist AS distance,
                       [r IN rels | type(r) + ': ' + coalesce(r.context, r.relationship, '')] AS connections
                """,
                human_id=human_id,
            )
            return {
                "human_id": human_id,
                "connections": [dict(r) for r in result],
            }

    # =========================================================================
    # Mapping from legacy phone-based IDs
    # =========================================================================

    def get_human_id_for_phone(self, phone: str) -> Optional[str]:
        """Get the Human UUID for a phone number. Returns None if not found."""
        human = self.find_human_by_identifier("SIGNAL_PHONE", phone)
        return human["id"] if human else None

    def delete_human(self, human_id: str) -> bool:
        """Delete a Human and all their relationships and orphaned identifiers."""
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (h:Human {id: $human_id})
                OPTIONAL MATCH (h)-[:IDENTIFIED_BY]->(i:Identifier)
                DETACH DELETE h
                WITH i
                WHERE i IS NOT NULL AND NOT exists((i)<-[:IDENTIFIED_BY]-())
                DELETE i
                RETURN count(*) AS deleted
                """,
                human_id=human_id,
            )
            return True


def get_store() -> HumanStoreV2:
    """Factory function."""
    return HumanStoreV2()


if __name__ == "__main__":
    store = HumanStoreV2()
    try:
        # Create test
        h = store.create_human("Test User V2", source="test")
        print(f"Created: {h}")

        # Add identifier
        store.add_identifier(h["id"], "SIGNAL_PHONE", "+19999999999", verified=True)

        # Find by phone
        found = store.find_human_by_identifier("SIGNAL_PHONE", "+19999999999")
        print(f"Found by phone: {found['displayName'] if found else 'Not found'}")

        # Cleanup
        store.delete_human(h["id"])
        print("Cleaned up test Human")
    finally:
        store.close()
