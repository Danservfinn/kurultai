#!/usr/bin/env python3
"""
Neo4j Human Profile - Graph CRUD operations for human profile storage system

Schema:
- (:HumanProfile {profile_id, human_id, display_name, timezone, ...})
- (:ConsentCategory {name, description})
- (:Tag {name, description})

Relationships:
- (HumanProfile)-[:LINKED_TO]->(Person)
- (HumanProfile)-[:HAS_CONSENT]->(ConsentCategory)
- (HumanProfile)-[:TAGGED_AS]->(Tag)
- (HumanProfile)-[:KNOWS]->(HumanProfile)

Usage:
    from neo4j_human_profile import HumanProfileStore
    store = HumanProfileStore()
    profile = store.get_profile("+19194133445")
    store.update_field("+19194133445", "timezone", "America/New_York")
"""

import os
import sys
import json
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import get_driver
from neo4j_utils import parse_json_fields


# Default communication style template
DEFAULT_COMMUNICATION_STYLE = {
    "preferred_channel": "signal",
    "preferred_time": "anytime",
    "response_style": "balanced",
    "emoji_friendly": True,
    "detail_level": "moderate",
    "formality": "casual",
    "messaging_frequency": "normal",
    "quiet_hours": None,
    "topics_of_interest": [],
    "topics_to_avoid": [],
}

# Default preferences template
DEFAULT_PREFERENCES = {
    "response_time": "normal",
    "detail_level": "moderate",
    "formatting": "markdown",
    "code_review_style": "summary",
    "meeting_style": "flexible",
    "file_organization": "by-date",
    "notifications": {
        "email": False,
        "signal": True,
        "push": False
    }
}

# Default personal context - broader facts to remember per person
DEFAULT_PERSONAL_CONTEXT = {
    "expertise": [],              # ["python", "devops", "design"]
    "role": None,                 # "CTO", "designer", "founder"
    "location": None,             # "Raleigh, NC"
    "relationships": {},          # {"Danny": "business partner", "Liz": "spouse"}
    "personal_facts": [],         # ["has a dog named Rex", "vegetarian"]
    "decision_style": None,       # "wants options" | "wants recommendations" | "decides fast"
    "last_sentiment": None,       # "positive" | "neutral" | "frustrated"
    "interaction_count": 0,       # total messages processed
    "first_interaction": None,    # ISO date string
    "last_interaction": None,     # ISO date string
}

# Default projects structure
DEFAULT_PROJECTS = {
    "active": [],
    "planned": [],
    "completed": []
}


class HumanProfileStore:
    """CRUD operations for HumanProfile nodes in Neo4j."""

    def __init__(self):
        self.driver = get_driver()

    def close(self):
        """Release driver reference. Does NOT close the singleton driver.

        The singleton driver is managed by get_driver()/close_driver() and
        should only be closed via close_driver() when the entire process
        is done with Neo4j.
        """
        self.driver = None  # Release reference only

    # ==========================================================================
    # Schema Initialization
    # ==========================================================================

    def init_schema(self) -> bool:
        """Create all constraints and indexes for the human profile schema."""
        constraints = [
            "CREATE CONSTRAINT human_profile_id_unique IF NOT EXISTS FOR (h:HumanProfile) REQUIRE h.profile_id IS UNIQUE",
            "CREATE CONSTRAINT consent_category_name_unique IF NOT EXISTS FOR (c:ConsentCategory) REQUIRE c.name IS UNIQUE",
            "CREATE CONSTRAINT tag_name_unique IF NOT EXISTS FOR (t:Tag) REQUIRE t.name IS UNIQUE",
        ]

        indexes = [
            "CREATE INDEX human_profile_human_id_idx IF NOT EXISTS FOR (h:HumanProfile) ON (h.human_id)",
            "CREATE INDEX human_profile_display_name_idx IF NOT EXISTS FOR (h:HumanProfile) ON (h.display_name)",
            "CREATE INDEX human_profile_privacy_idx IF NOT EXISTS FOR (h:HumanProfile) ON (h.privacy_level)",
            "CREATE INDEX human_profile_consent_idx IF NOT EXISTS FOR (h:HumanProfile) ON (h.consent_categories)",
        ]

        with self.driver.session() as session:
            for constraint in constraints:
                session.run(constraint)
            for index in indexes:
                session.run(index)

            # Fulltext index for search
            session.run("""
                CREATE FULLTEXT INDEX human_profile_search IF NOT EXISTS
                FOR (h:HumanProfile) ON EACH [h.display_name, h.what_to_call, h.notes]
            """)

        return True

    def seed_consent_categories(self) -> bool:
        """Seed the consent category nodes."""
        categories = [
            ("calendar", "Store event preferences and availability"),
            ("tasks", "Remember task assignments and progress"),
            ("research", "Store research preferences and topics of interest"),
            ("social", "Remember personal interests and social context"),
            ("marketing", "Product updates and marketing communications"),
        ]

        with self.driver.session() as session:
            for name, description in categories:
                session.run("""
                    MERGE (c:ConsentCategory {name: $name})
                    ON CREATE SET c.description = $description,
                                  c.created_at = datetime()
                """, name=name, description=description)

        return True

    def seed_tags(self) -> bool:
        """Seed common tags."""
        tags = [
            ("vip", "High priority human"),
            ("founder", "Company founder"),
            ("engineering", "Engineering/technical"),
            ("admin", "System administrator"),
        ]

        with self.driver.session() as session:
            for name, description in tags:
                session.run("""
                    MERGE (t:Tag {name: $name})
                    ON CREATE SET t.description = $description,
                                  t.created_at = datetime()
                """, name=name, description=description)

        return True

    # ==========================================================================
    # CRUD Operations
    # ==========================================================================

    def create_profile(self, human_id: str, display_name: str,
                       timezone: Optional[str] = None,
                       what_to_call: Optional[str] = None,
                       pronouns: Optional[str] = None,
                       privacy_level: str = "contacts",
                       source: str = "manual") -> Optional[Dict[str, Any]]:
        """
        Create a new HumanProfile linked to a Person.

        Args:
            human_id: Phone number (E.164 format), links to Person
            display_name: Preferred display name
            timezone: IANA timezone (e.g., "America/New_York")
            what_to_call: How they want to be addressed
            pronouns: Optional pronouns
            privacy_level: "public", "contacts", or "private"
            source: "signal", "manual", or "inferred"

        Returns:
            The created profile or None if Person doesn't exist
        """
        with self.driver.session() as session:
            result = session.run("""
                // Ensure Person exists
                MATCH (p:Person {phone_number: $human_id})

                // Create or merge HumanProfile
                MERGE (hp:HumanProfile {human_id: $human_id})
                ON CREATE SET
                    hp.profile_id = "hp-" + randomUUID(),
                    hp.display_name = $display_name,
                    hp.what_to_call = COALESCE($what_to_call, $display_name),
                    hp.pronouns = $pronouns,
                    hp.timezone = COALESCE($timezone, "America/New_York"),
                    hp.communication_style = $communication_style,
                    hp.preferences = $preferences,
                    hp.personal_context = $personal_context,
                    hp.projects = $projects,
                    hp.privacy_level = $privacy_level,
                    hp.consent_categories = [],
                    hp.source = $source,
                    hp.confidence = 1.0,
                    hp.last_verified = datetime(),
                    hp.notes = null,
                    hp.status = "active",
                    hp.created_at = datetime(),
                    hp.updated_at = datetime()
                ON MATCH SET
                    hp.display_name = $display_name,
                    hp.what_to_call = COALESCE($what_to_call, hp.what_to_call, $display_name),
                    hp.pronouns = COALESCE($pronouns, hp.pronouns),
                    hp.timezone = COALESCE($timezone, hp.timezone),
                    hp.updated_at = datetime()

                // Link to Person
                MERGE (hp)-[link:LINKED_TO]->(p)
                ON CREATE SET link.created_at = datetime()

                RETURN hp.profile_id AS profile_id,
                       hp.display_name AS display_name,
                       hp.human_id AS human_id,
                       hp.status AS status
            """,
            human_id=human_id,
            display_name=display_name,
            what_to_call=what_to_call,
            pronouns=pronouns,
            timezone=timezone,
            privacy_level=privacy_level,
            source=source,
            communication_style=json.dumps(DEFAULT_COMMUNICATION_STYLE),
            preferences=json.dumps(DEFAULT_PREFERENCES),
            personal_context=json.dumps(DEFAULT_PERSONAL_CONTEXT),
            projects=json.dumps(DEFAULT_PROJECTS)
            )

            record = result.single()
            return dict(record) if record else None

    def get_profile(self, search_query: str) -> Optional[Dict[str, Any]]:
        """
        Get a profile by phone number or display name.

        Args:
            search_query: Phone number (E.164) or display name

        Returns:
            Full profile with linked Person data
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (hp:HumanProfile)
                WHERE hp.human_id = $search_term
                   OR toLower(hp.display_name) = toLower($search_term)
                   OR toLower(hp.what_to_call) = toLower($search_term)
                WITH hp LIMIT 1

                MATCH (hp)-[:LINKED_TO]->(p:Person)

                OPTIONAL MATCH (hp)-[rel:HAS_CONSENT]->(c:ConsentCategory)
                WHERE rel.revoked_at IS NULL

                OPTIONAL MATCH (hp)-[:TAGGED_AS]->(t:Tag)

                RETURN hp.profile_id AS profile_id,
                       hp.human_id AS human_id,
                       hp.display_name AS display_name,
                       hp.what_to_call AS what_to_call,
                       hp.pronouns AS pronouns,
                       hp.timezone AS timezone,
                       hp.communication_style AS communication_style,
                       hp.preferences AS preferences,
                       hp.personal_context AS personal_context,
                       hp.projects AS projects,
                       hp.privacy_level AS privacy_level,
                       hp.consent_categories AS consent_categories,
                       hp.notes AS notes,
                       hp.confidence AS confidence,
                       hp.last_verified AS last_verified,
                       hp.source AS source,
                       hp.status AS status,
                       hp.created_at AS created_at,
                       hp.updated_at AS updated_at,
                       p.name AS person_name,
                       p.aliases AS person_aliases,
                       collect(DISTINCT c.name) AS active_consents,
                       collect(DISTINCT t.name) AS tags
            """, search_term=search_query)

            record = result.single()
            if not record:
                return None

            profile = dict(record)

            # Parse JSON fields
            parse_json_fields(profile, ["communication_style", "preferences", "personal_context", "projects"])

            return profile

    def get_profile_by_phone(self, phone: str) -> Optional[Dict[str, Any]]:
        """Get profile by exact phone number match."""
        return self.get_profile(phone)

    def update_field(self, human_id: str, field: str, value: Any,
                     updated_by: Optional[str] = None,
                     source: Optional[str] = None) -> bool:
        """
        Update a specific field on a profile with audit trail.

        Args:
            human_id: The phone number (human_id)
            field: Field name to update
            value: New value
            updated_by: Optional agent name for audit
            source: How the change was detected ("explicit", "inferred", "signal_command")

        Returns:
            True if updated, False if profile not found
        """
        # Serialize JSON fields
        serialized_value = value
        if field in ["communication_style", "preferences", "projects", "personal_context"]:
            if isinstance(value, dict):
                serialized_value = json.dumps(value)

        with self.driver.session() as session:
            result = session.run("""
                MATCH (hp:HumanProfile {human_id: $human_id})

                // Capture old value before update
                WITH hp, hp[$field] AS old_value
                SET hp[$field] = $value,
                    hp.updated_at = datetime()

                // Create audit trail with old/new values
                WITH hp, old_value
                FOREACH (_ IN CASE WHEN $updated_by IS NOT NULL THEN [1] ELSE [] END |
                    MERGE (a:Agent {name: $updated_by})
                    CREATE (hp)-[:PREFERENCE_CHANGED {
                        at: datetime(),
                        field: $field,
                        old_value: COALESCE(toString(old_value), 'null'),
                        new_value: COALESCE(toString($value), 'null'),
                        source: COALESCE($source, 'unknown'),
                        updated_by: $updated_by
                    }]->(a)
                )

                RETURN hp.profile_id AS profile_id
            """, human_id=human_id, field=field, value=serialized_value,
                updated_by=updated_by, source=source)

            return result.single() is not None

    def update_profile(self, human_id: str, updates: Dict[str, Any],
                       updated_by: Optional[str] = None) -> bool:
        """
        Update multiple fields at once.

        Args:
            human_id: The phone number
            updates: Dict of field names to values
            updated_by: Optional agent name for audit

        Returns:
            True if updated
        """
        # Serialize JSON fields
        for field in ["communication_style", "preferences", "projects"]:
            if field in updates and isinstance(updates[field], dict):
                updates[field] = json.dumps(updates[field])

        with self.driver.session() as session:
            # Build dynamic SET clause
            set_clauses = []
            for key in updates.keys():
                set_clauses.append(f"hp.{key} = ${key}")
            set_clauses.append("hp.updated_at = datetime()")

            cypher = f"""
                MATCH (hp:HumanProfile {{human_id: $human_id}})
                SET {', '.join(set_clauses)}

                WITH hp
                FOREACH (_ IN CASE WHEN $updated_by IS NOT NULL THEN [1] ELSE [] END |
                    MERGE (a:Agent {{name: $updated_by}})
                    CREATE (hp)-[:UPDATED_BY {{at: datetime(), field: 'multiple'}}]->(a)
                )

                RETURN hp.profile_id AS profile_id
            """

            params = {"human_id": human_id, "updated_by": updated_by, **updates}
            result = session.run(cypher, **params)
            return result.single() is not None

    def search_profiles(self, search_text: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Search profiles using fulltext index.

        Args:
            search_text: Natural language search text
            limit: Max results

        Returns:
            List of matching profiles
        """
        with self.driver.session() as session:
            result = session.run("""
                CALL db.index.fulltext.queryNodes("human_profile_search", $search_text)
                YIELD node AS hp, score
                WHERE hp.status = "active"
                RETURN hp.human_id AS human_id,
                       hp.display_name AS display_name,
                       hp.what_to_call AS what_to_call,
                       hp.notes AS notes,
                       score
                ORDER BY score DESC
                LIMIT $limit
            """, search_text=search_text, limit=limit)

            return [dict(record) for record in result]

    def list_profiles(self, privacy_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List all profiles with optional privacy filter.

        Args:
            privacy_filter: Filter by privacy level

        Returns:
            List of profiles
        """
        with self.driver.session() as session:
            if privacy_filter:
                result = session.run("""
                    MATCH (hp:HumanProfile)
                    WHERE hp.status = "active"
                      AND hp.privacy_level = $privacy_filter
                    RETURN hp.human_id AS human_id,
                           hp.display_name AS display_name,
                           hp.timezone AS timezone,
                           hp.privacy_level AS privacy_level
                    ORDER BY hp.display_name
                """, privacy_filter=privacy_filter)
            else:
                result = session.run("""
                    MATCH (hp:HumanProfile)
                    WHERE hp.status = "active"
                    RETURN hp.human_id AS human_id,
                           hp.display_name AS display_name,
                           hp.timezone AS timezone,
                           hp.privacy_level AS privacy_level
                    ORDER BY hp.display_name
                """)

            return [dict(record) for record in result]

    # ==========================================================================
    # Consent Management
    # ==========================================================================

    def add_consent(self, human_id: str, category: str) -> bool:
        """
        Add a consent category for a human.

        Args:
            human_id: Phone number
            category: Consent category name

        Returns:
            True if successful
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (hp:HumanProfile {human_id: $human_id})
                MATCH (c:ConsentCategory {name: $category})

                MERGE (hp)-[rel:HAS_CONSENT]->(c)
                ON CREATE SET
                    rel.granted_at = datetime(),
                    rel.source = "explicit",
                    rel.revoked_at = NULL

                SET hp.consent_categories =
                    CASE WHEN $category IN COALESCE(hp.consent_categories, [])
                    THEN hp.consent_categories
                    ELSE COALESCE(hp.consent_categories, []) + $category
                    END,
                    hp.updated_at = datetime()

                RETURN hp.display_name AS name
            """, human_id=human_id, category=category)

            return result.single() is not None

    def revoke_consent(self, human_id: str, category: str) -> bool:
        """
        Revoke a consent category.

        Args:
            human_id: Phone number
            category: Consent category name

        Returns:
            True if successful
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (hp:HumanProfile {human_id: $human_id})
                MATCH (hp)-[rel:HAS_CONSENT]->(c:ConsentCategory {name: $category})

                SET rel.revoked_at = datetime(),
                    hp.consent_categories =
                        [x IN COALESCE(hp.consent_categories, [])
                         WHERE x <> $category],
                    hp.updated_at = datetime()

                RETURN hp.display_name AS name
            """, human_id=human_id, category=category)

            return result.single() is not None

    def check_consent(self, human_id: str, category: str) -> bool:
        """
        Check if a human has consented to a category.

        Args:
            human_id: Phone number
            category: Consent category name

        Returns:
            True if consented
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (hp:HumanProfile {human_id: $human_id})
                MATCH (hp)-[rel:HAS_CONSENT]->(c:ConsentCategory {name: $category})
                WHERE rel.revoked_at IS NULL
                RETURN c.name AS consented
            """, human_id=human_id, category=category)

            return result.single() is not None

    def get_consent_categories(self) -> List[Dict[str, Any]]:
        """Get all available consent categories."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (c:ConsentCategory)
                RETURN c.name AS name, c.description AS description
                ORDER BY c.name
            """)
            return [dict(record) for record in result]

    # ==========================================================================
    # Privacy and Data Management
    # ==========================================================================

    def set_privacy_level(self, human_id: str, level: str) -> bool:
        """
        Set the privacy level for a profile.

        Args:
            human_id: Phone number
            level: "public", "contacts", or "private"

        Returns:
            True if successful
        """
        if level not in ["public", "contacts", "private"]:
            raise ValueError("Invalid privacy level")

        return self.update_field(human_id, "privacy_level", level)

    def anonymize_profile(self, human_id: str) -> bool:
        """
        Soft delete - anonymize all personal data.

        Args:
            human_id: Phone number

        Returns:
            True if successful
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (hp:HumanProfile {human_id: $human_id})
                SET hp.display_name = "Anonymous",
                    hp.what_to_call = "User",
                    hp.pronouns = null,
                    hp.communication_style = '{}',
                    hp.preferences = '{}',
                    hp.projects = '{}',
                    hp.notes = null,
                    hp.consent_categories = [],
                    hp.status = "anonymized",
                    hp.updated_at = datetime()
                RETURN hp.profile_id AS profile_id
            """, human_id=human_id)

            return result.single() is not None

    def delete_profile(self, human_id: str) -> bool:
        """
        Hard delete - remove profile and all relationships.

        Args:
            human_id: Phone number

        Returns:
            True if successful
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (hp:HumanProfile {human_id: $human_id})
                OPTIONAL MATCH (hp)-[r]-()
                DELETE r, hp
                RETURN count(hp) AS deleted
            """, human_id=human_id)

            record = result.single()
            return record is not None and record["deleted"] > 0

    # ==========================================================================
    # Context Enrichment
    # ==========================================================================

    def get_profiles_for_context(self, human_ids: List[str]) -> List[Dict[str, Any]]:
        """
        Get minimal profiles for context enrichment (fast query).

        Args:
            human_ids: List of phone numbers

        Returns:
            List of profile dicts with essential fields
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (hp:HumanProfile)
                WHERE hp.human_id IN $human_ids
                  AND hp.status = "active"
                RETURN hp.human_id AS human_id,
                       hp.display_name AS display_name,
                       hp.what_to_call AS what_to_call,
                       hp.timezone AS timezone,
                       hp.communication_style AS communication_style,
                       hp.preferences AS preferences,
                       hp.personal_context AS personal_context,
                       hp.projects AS projects
            """, human_ids=human_ids)

            profiles = []
            for record in result:
                profile = dict(record)
                # Parse JSON
                for json_field in ["communication_style", "preferences", "personal_context", "projects"]:
                    if profile.get(json_field):
                        try:
                            profile[json_field] = json.loads(profile[json_field])
                        except (json.JSONDecodeError, TypeError):
                            pass
                profiles.append(profile)

            return profiles

    def get_communication_preferences(self, human_id: str) -> Optional[Dict[str, Any]]:
        """
        Get just the communication preferences for a human.

        Args:
            human_id: Phone number

        Returns:
            Communication style and preferences or None
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (hp:HumanProfile {human_id: $human_id})
                RETURN hp.display_name AS display_name,
                       hp.communication_style AS communication_style,
                       hp.preferences AS preferences
            """, human_id=human_id)

            record = result.single()
            if not record:
                return None

            prefs = dict(record)
            for field in ["communication_style", "preferences"]:
                if prefs.get(field):
                    try:
                        prefs[field] = json.loads(prefs[field])
                    except (json.JSONDecodeError, TypeError):
                        pass
            return prefs

    def get_preference_history(self, human_id: str, field: Optional[str] = None,
                               limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get preference change history for a human.

        Args:
            human_id: Phone number
            field: Optional field name to filter by
            limit: Max results

        Returns:
            List of change records with at, field, old_value, new_value, source
        """
        with self.driver.session() as session:
            if field:
                result = session.run("""
                    MATCH (hp:HumanProfile {human_id: $human_id})-[r:PREFERENCE_CHANGED]->(a:Agent)
                    WHERE r.field = $field
                    RETURN r.at AS at, r.field AS field,
                           r.old_value AS old_value, r.new_value AS new_value,
                           r.source AS source, a.name AS changed_by
                    ORDER BY r.at DESC
                    LIMIT $limit
                """, human_id=human_id, field=field, limit=limit)
            else:
                result = session.run("""
                    MATCH (hp:HumanProfile {human_id: $human_id})-[r:PREFERENCE_CHANGED]->(a:Agent)
                    RETURN r.at AS at, r.field AS field,
                           r.old_value AS old_value, r.new_value AS new_value,
                           r.source AS source, a.name AS changed_by
                    ORDER BY r.at DESC
                    LIMIT $limit
                """, human_id=human_id, limit=limit)

            return [dict(record) for record in result]

    # ==========================================================================
    # Tagging
    # ==========================================================================

    def add_tag(self, human_id: str, tag_name: str, tagged_by: Optional[str] = None) -> bool:
        """
        Add a tag to a profile.

        Args:
            human_id: Phone number
            tag_name: Tag to add
            tagged_by: Who added the tag

        Returns:
            True if successful
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (hp:HumanProfile {human_id: $human_id})
                MERGE (t:Tag {name: toLower($tag_name)})
                MERGE (hp)-[rel:TAGGED_AS]->(t)
                ON CREATE SET
                    rel.tagged_at = datetime(),
                    rel.tagged_by = $tagged_by
                RETURN hp.display_name AS name
            """, human_id=human_id, tag_name=tag_name, tagged_by=tagged_by)

            return result.single() is not None

    def remove_tag(self, human_id: str, tag_name: str) -> bool:
        """
        Remove a tag from a profile.

        Args:
            human_id: Phone number
            tag_name: Tag to remove

        Returns:
            True if successful
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (hp:HumanProfile {human_id: $human_id})
                MATCH (hp)-[rel:TAGGED_AS]->(t:Tag {name: toLower($tag_name)})
                DELETE rel
                RETURN count(rel) AS removed
            """, human_id=human_id, tag_name=tag_name)

            record = result.single()
            return record is not None and record["removed"] > 0


# ==========================================================================
# Helper Functions
# ==========================================================================

def get_store() -> HumanProfileStore:
    """Factory function to get a store instance."""
    return HumanProfileStore()


def init_human_profile_system() -> bool:
    """Initialize the entire human profile system."""
    store = HumanProfileStore()
    try:
        store.init_schema()
        store.seed_consent_categories()
        store.seed_tags()
        return True
    finally:
        store.close()


if __name__ == "__main__":
    # Test the module
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "init":
        print("Initializing human profile system...")
        if init_human_profile_system():
            print("Schema initialized successfully")
        else:
            print("Failed to initialize schema")
        sys.exit(0)

    # Simple test
    store = HumanProfileStore()

    # Create test profile
    result = store.create_profile(
        human_id="+19999999999",
        display_name="Test User",
        timezone="America/New_York",
        source="test"
    )
    print(f"Created profile: {result}")

    # Get profile
    profile = store.get_profile("+19999999999")
    print(f"Retrieved profile: {profile['display_name'] if profile else 'Not found'}")

    # Clean up
    if profile:
        store.delete_profile("+19999999999")
        print("Test profile deleted")

    store.close()
