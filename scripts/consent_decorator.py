#!/usr/bin/env python3
"""
Consent Decorator — @requires_consent for gating data-processing functions.

Nine consent categories with parent→child cascade:

    message_storage           (root)
    ├── message_analysis
    │   ├── conversation_memory
    │   │   └── relationship_tracking
    │   └── embedding_generation
    ├── external_llm_processing
    └── proactive_engagement
        ├── general_curiosity
        └── personal_curiosity

Revoking a parent revokes all children. Granting a child does NOT
auto-grant its parent (must be granted explicitly bottom-up).

Usage:
    from consent_decorator import requires_consent, check_consent

    @requires_consent('message_analysis')
    def analyze_message(human_id: str, message: str):
        ...

    # The decorator extracts human_id from the first positional arg
    # or from a 'human_id' keyword arg.
"""

import functools
import logging
from typing import Optional, List, Dict, Set, Callable, Any

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import neo4j_session

logger = logging.getLogger(__name__)

# ============================================================================
# Consent category hierarchy
# ============================================================================

# Parent → children mapping
CONSENT_HIERARCHY: Dict[str, List[str]] = {
    "message_storage": ["message_analysis", "external_llm_processing", "proactive_engagement"],
    "message_analysis": ["conversation_memory", "embedding_generation"],
    "conversation_memory": ["relationship_tracking"],
    "embedding_generation": [],
    "external_llm_processing": [],
    "proactive_engagement": ["general_curiosity", "personal_curiosity"],
    "general_curiosity": [],
    "personal_curiosity": [],
    "relationship_tracking": [],
}

# Descriptions for seeding
CONSENT_DESCRIPTIONS: Dict[str, str] = {
    "message_storage": "Store message content in the conversation graph",
    "message_analysis": "Analyze messages for topics, sentiment, and intent",
    "conversation_memory": "Build long-term conversation memory across threads",
    "relationship_tracking": "Track relationships between humans mentioned in conversations",
    "embedding_generation": "Generate vector embeddings of message content",
    "external_llm_processing": "Send PII-scrubbed content to external LLMs for analysis",
    "proactive_engagement": "Allow Kublai to initiate conversations proactively",
    "general_curiosity": "Allow Kublai to ask open-ended questions about your interests and activities",
    "personal_curiosity": "Allow Kublai to ask about your personal life (where you're from, hobbies, etc.)",
}

ALL_CATEGORIES = set(CONSENT_HIERARCHY.keys())


def get_descendants(category: str) -> Set[str]:
    """Get all descendant categories of a given category."""
    descendants = set()
    queue = list(CONSENT_HIERARCHY.get(category, []))
    while queue:
        child = queue.pop(0)
        if child not in descendants:
            descendants.add(child)
            queue.extend(CONSENT_HIERARCHY.get(child, []))
    return descendants


def get_ancestors(category: str) -> List[str]:
    """Get all ancestor categories (parents, grandparents, etc.)."""
    ancestors = []
    for parent, children in CONSENT_HIERARCHY.items():
        if category in children:
            ancestors.append(parent)
            ancestors.extend(get_ancestors(parent))
    return ancestors


def get_required_categories(category: str) -> List[str]:
    """Get the category + all ancestors needed for it to be valid."""
    return [category] + get_ancestors(category)


# ============================================================================
# Consent checking
# ============================================================================

class ConsentDenied(Exception):
    """Raised when a function requires consent that hasn't been granted."""
    def __init__(self, human_id: str, category: str, missing: List[str]):
        self.human_id = human_id
        self.category = category
        self.missing = missing
        super().__init__(
            f"Consent denied for human {human_id}: "
            f"requires '{category}', missing: {missing}"
        )


def check_consent(human_id: str, category: str) -> bool:
    """Check if a human has granted consent for a category.

    Checks that the category AND all its ancestors are granted.

    Args:
        human_id: UUID of the Human
        category: Consent category to check

    Returns:
        True if consent is granted for the category and all ancestors
    """
    if category not in ALL_CATEGORIES:
        logger.warning(f"Unknown consent category: {category}")
        return False

    required = get_required_categories(category)

    try:
        with neo4j_session() as session:
            result = session.run(
                """
                MATCH (h:Human {id: $human_id})-[r:HAS_CONSENT]->(c:ConsentCategory)
                WHERE c.name IN $required AND r.revokedAt IS NULL
                RETURN collect(c.name) AS granted
                """,
                human_id=human_id,
                required=required,
            )
            record = result.single()
            if not record:
                return False
            granted = set(record["granted"])
            return all(r in granted for r in required)
    except Exception as e:
        logger.error(f"Consent check failed for {human_id}/{category}: {e}")
        # Fail closed — deny if we can't check
        return False


def grant_consent(human_id: str, category: str, source: str = "explicit") -> bool:
    """Grant consent for a category.

    Args:
        human_id: UUID of the Human
        category: Category to grant
        source: How consent was obtained

    Returns:
        True if granted successfully
    """
    if category not in ALL_CATEGORIES:
        return False

    try:
        with neo4j_session() as session:
            session.run(
                """
                MATCH (h:Human {id: $human_id})
                MERGE (c:ConsentCategory {name: $category})
                ON CREATE SET c.description = $description
                MERGE (h)-[r:HAS_CONSENT]->(c)
                ON CREATE SET r.grantedAt = datetime(), r.source = $source
                SET r.revokedAt = NULL
                """,
                human_id=human_id,
                category=category,
                description=CONSENT_DESCRIPTIONS.get(category, ""),
                source=source,
            )
            return True
    except Exception as e:
        logger.error(f"Grant consent failed for {human_id}/{category}: {e}")
        return False


def revoke_consent(human_id: str, category: str) -> Dict[str, Any]:
    """Revoke consent for a category and all its descendants.

    Returns:
        Dict with 'revoked' list and 'cascade_warning' if children were affected
    """
    if category not in ALL_CATEGORIES:
        return {"revoked": [], "error": f"Unknown category: {category}"}

    descendants = get_descendants(category)
    to_revoke = [category] + list(descendants)

    try:
        with neo4j_session() as session:
            result = session.run(
                """
                MATCH (h:Human {id: $human_id})-[r:HAS_CONSENT]->(c:ConsentCategory)
                WHERE c.name IN $categories AND r.revokedAt IS NULL
                SET r.revokedAt = datetime()
                RETURN collect(c.name) AS revoked
                """,
                human_id=human_id,
                categories=to_revoke,
            )
            record = result.single()
            revoked = record["revoked"] if record else []
            return {
                "revoked": revoked,
                "cascade_warning": (
                    f"Also revoked: {list(descendants)}"
                    if descendants & set(revoked)
                    else None
                ),
            }
    except Exception as e:
        logger.error(f"Revoke consent failed for {human_id}/{category}: {e}")
        return {"revoked": [], "error": str(e)}


def get_consent_status(human_id: str) -> Dict[str, Any]:
    """Get full consent status for a human."""
    try:
        with neo4j_session() as session:
            result = session.run(
                """
                MATCH (c:ConsentCategory)
                OPTIONAL MATCH (h:Human {id: $human_id})-[r:HAS_CONSENT]->(c)
                RETURN c.name AS category,
                       c.description AS description,
                       r IS NOT NULL AND r.revokedAt IS NULL AS granted,
                       toString(r.grantedAt) AS grantedAt,
                       toString(r.revokedAt) AS revokedAt,
                       r.source AS source
                ORDER BY c.name
                """,
                human_id=human_id,
            )
            statuses = {}
            for record in result:
                statuses[record["category"]] = {
                    "granted": record["granted"],
                    "description": record["description"],
                    "grantedAt": record["grantedAt"],
                    "revokedAt": record["revokedAt"],
                    "source": record["source"],
                }
            return statuses
    except Exception as e:
        logger.error(f"Get consent status failed for {human_id}: {e}")
        return {}


# ============================================================================
# Decorator
# ============================================================================

def requires_consent(category: str, fail_silent: bool = False):
    """Decorator that gates a function on consent.

    The decorated function must receive human_id as its first
    positional argument or as a keyword argument.

    Args:
        category: Required consent category
        fail_silent: If True, return None instead of raising ConsentDenied

    Usage:
        @requires_consent('message_analysis')
        def analyze(human_id: str, text: str) -> dict:
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Extract human_id from args or kwargs
            human_id = kwargs.get("human_id")
            if human_id is None and args:
                human_id = args[0]

            if not human_id:
                if fail_silent:
                    return None
                raise ConsentDenied("unknown", category, [category])

            if not check_consent(human_id, category):
                required = get_required_categories(category)
                if fail_silent:
                    logger.info(
                        f"Consent not granted for {human_id}/{category}, "
                        f"skipping {func.__name__}"
                    )
                    return None
                raise ConsentDenied(human_id, category, required)

            return func(*args, **kwargs)
        return wrapper
    return decorator


def seed_consent_categories() -> bool:
    """Seed all consent category nodes in Neo4j."""
    try:
        with neo4j_session() as session:
            for name, description in CONSENT_DESCRIPTIONS.items():
                session.run(
                    """
                    MERGE (c:ConsentCategory {name: $name})
                    ON CREATE SET c.description = $description,
                                  c.createdAt = datetime()
                    ON MATCH SET c.description = $description
                    """,
                    name=name,
                    description=description,
                )
        return True
    except Exception as e:
        logger.error(f"Seeding consent categories failed: {e}")
        return False


def get_active_humans_with_consent(category: str) -> List[str]:
    """Return human IDs that have granted a specific consent category.

    Args:
        category: Consent category name (e.g. 'proactive_engagement')

    Returns:
        List of human ID strings
    """
    if category not in ALL_CATEGORIES:
        logger.warning(f"Unknown consent category: {category}")
        return []

    required = get_required_categories(category)

    try:
        with neo4j_session() as session:
            result = session.run(
                """
                MATCH (h:Human {status: 'active'})-[r:HAS_CONSENT]->(c:ConsentCategory)
                WHERE c.name IN $required AND r.revokedAt IS NULL
                WITH h, collect(c.name) AS granted
                WHERE size([r IN $required WHERE r IN granted]) = size($required)
                RETURN h.id AS id
                """,
                required=required,
            )
            return [r["id"] for r in result]
    except Exception as e:
        logger.error(f"get_active_humans_with_consent failed for {category}: {e}")
        return []


if __name__ == "__main__":
    # Test hierarchy
    print("Consent hierarchy:")
    for cat in sorted(ALL_CATEGORIES):
        ancestors = get_ancestors(cat)
        descendants = get_descendants(cat)
        print(f"  {cat}")
        if ancestors:
            print(f"    parents: {ancestors}")
        if descendants:
            print(f"    children: {descendants}")

    # Test required categories
    print("\nRequired for 'relationship_tracking':")
    print(f"  {get_required_categories('relationship_tracking')}")

    print("\nSeeding categories...")
    seed_consent_categories()
    print("Done.")
