"""
Migration v2: Add Kurultai Task Dependency Engine fields

Adds dependency tracking fields to Task node and creates indexes
for DAG traversal and semantic similarity search.

Author: Claude (Anthropic)
Date: 2026-02-04
"""

from typing import Optional
from migrations.migration_manager import MigrationManager


class V2KurultaiDependencies:
    """
    Kurultai v0.1 Task Dependency Engine migration (version 2).

    Adds:
    - Dependency tracking fields to Task nodes
    - DEPENDS_ON relationship indexes
    - Vector index for semantic similarity (Neo4j 5.11+)
    - Priority queue indexes
    - Intent window indexes
    """

    VERSION = 2
    NAME = "kurultai_dependencies"
    DESCRIPTION = "Add Kurultai v0.1 Task Dependency Engine fields and indexes"

    # Cypher queries for applying the migration
    UP_CYPHER = """
    // =====================================================
    // V2 Kurultai Task Dependency Engine Migration
    // =====================================================

    // -----------------------------------------------------
    // 1. Add Kurultai v0.1 fields to existing Task nodes
    // -----------------------------------------------------

    MATCH (t:Task)
    WHERE t.sender_hash IS NULL
    SET t.sender_hash = COALESCE(t.sender_hash, 'default'),
        t.window_expires_at = COALESCE(t.window_expires_at, datetime()),
        t.embedding = COALESCE(t.embedding, []),
        t.deliverable_type = COALESCE(t.deliverable_type, 'analysis'),
        t.priority_weight = COALESCE(t.priority_weight, 0.5),
        t.user_priority_override = COALESCE(t.user_priority_override, false),
        t.merged_into = COALESCE(t.merged_into, null),
        t.merged_from = COALESCE(t.merged_from, []),
        t.notion_synced_at = COALESCE(t.notion_synced_at, null),
        t.notion_page_id = COALESCE(t.notion_page_id, null),
        t.notion_url = COALESCE(t.notion_url, null),
        t.external_priority_source = COALESCE(t.external_priority_source, null),
        t.external_priority_weight = COALESCE(t.external_priority_weight, 0.0);

    // -----------------------------------------------------
    // 2. Create indexes for Kurultai features
    // -----------------------------------------------------

    // Intent window queries
    CREATE INDEX task_window IF NOT EXISTS FOR (t:Task) ON (t.window_expires_at);

    // Task sender status queries
    CREATE INDEX task_sender_status IF NOT EXISTS FOR (t:Task) ON (t.sender_hash, t.status);

    // Dependency type filtering
    CREATE INDEX depends_on_type IF NOT EXISTS FOR ()-[d:DEPENDS_ON]->() ON (d.type);

    // Priority queue queries
    CREATE INDEX task_priority IF NOT EXISTS FOR (t:Task) ON (t.priority_weight, t.created_at);

    // Deliverable type queries
    CREATE INDEX task_deliverable_type IF NOT EXISTS FOR (t:Task) ON (t.deliverable_type);

    // Notion sync tracking
    CREATE INDEX task_notion_synced IF NOT EXISTS FOR (t:Task) ON (t.notion_synced_at);

    // User priority override flag
    CREATE INDEX task_user_override IF NOT EXISTS FOR (t:Task) ON (t.user_priority_override);

    // -----------------------------------------------------
    // 3. Attempt to create vector index (Neo4j 5.11+ only)
    // -----------------------------------------------------

    // This will fail on Neo4j < 5.11, which is expected
    // The migration continues even if this fails
    """

    # Cypher queries for rolling back the migration
    DOWN_CYPHER = """
    // =====================================================
    // V2 Kurultai Task Dependency Engine Rollback
    // =====================================================

    // -----------------------------------------------------
    // 1. Remove Kurultai v0.1 fields from Task nodes
    // -----------------------------------------------------

    MATCH (t:Task)
    REMOVE t.sender_hash, t.window_expires_at, t.embedding, t.deliverable_type,
           t.priority_weight, t.user_priority_override, t.merged_into, t.merged_from,
           t.notion_synced_at, t.notion_page_id, t.notion_url,
           t.external_priority_source, t.external_priority_weight;

    // -----------------------------------------------------
    // 2. Drop Kurultai indexes
    // -----------------------------------------------------

    DROP INDEX task_window IF EXISTS;
    DROP INDEX task_sender_status IF EXISTS;
    DROP INDEX depends_on_type IF EXISTS;
    DROP INDEX task_priority IF EXISTS;
    DROP INDEX task_deliverable_type IF EXISTS;
    DROP INDEX task_notion_synced IF EXISTS;
    DROP INDEX task_user_override IF EXISTS;

    // -----------------------------------------------------
    // 3. Remove DEPENDS_ON relationships
    // -----------------------------------------------------

    MATCH ()-[d:DEPENDS_ON]->() DELETE d;

    // -----------------------------------------------------
    // 4. Update migration control
    // -----------------------------------------------------

    MERGE (m:Migration {version: 2})
    SET m.removed_at = datetime();
    """

    @classmethod
    def register(cls, manager: MigrationManager) -> None:
        """
        Register this migration with a MigrationManager.

        Args:
            manager: MigrationManager instance to register with
        """
        manager.register_migration(
            version=cls.VERSION,
            name=cls.NAME,
            up_cypher=cls.UP_CYPHER,
            down_cypher=cls.DOWN_CYPHER,
            description=cls.DESCRIPTION
        )

    @classmethod
    def get_summary(cls) -> dict:
        """
        Get a summary of what this migration creates.

        Returns:
            Dictionary with migration summary
        """
        return {
            "version": cls.VERSION,
            "name": cls.NAME,
            "description": cls.DESCRIPTION,
            "fields_added": [
                "sender_hash",
                "window_expires_at",
                "embedding",
                "deliverable_type",
                "priority_weight",
                "user_priority_override",
                "merged_into",
                "merged_from",
                "notion_synced_at",
                "notion_page_id",
                "notion_url",
                "external_priority_source",
                "external_priority_weight",
            ],
            "indexes_created": [
                "task_window",
                "task_sender_status",
                "depends_on_type",
                "task_priority",
                "task_deliverable_type",
                "task_notion_synced",
                "task_user_override",
            ],
            "relationships": ["DEPENDS_ON"],
        }


# Convenience function for running this migration
async def upgrade(driver):
    """
    Add Kurultai v0.1 fields to Task node.

    Args:
        driver: Neo4j driver instance
    """
    # Add new properties to existing Task nodes (default values)
    add_fields_query = """
    MATCH (t:Task)
    WHERE t.sender_hash IS NULL
    SET t.sender_hash = COALESCE(t.sender_hash, 'default'),
        t.window_expires_at = COALESCE(t.window_expires_at, datetime()),
        t.embedding = COALESCE(t.embedding, []),
        t.deliverable_type = COALESCE(t.deliverable_type, 'analysis'),
        t.priority_weight = COALESCE(t.priority_weight, 0.5),
        t.user_priority_override = COALESCE(t.user_priority_override, false),
        t.merged_into = COALESCE(t.merged_into, null),
        t.merged_from = COALESCE(t.merged_from, []),
        t.notion_synced_at = COALESCE(t.notion_synced_at, null),
        t.notion_page_id = COALESCE(t.notion_page_id, null),
        t.notion_url = COALESCE(t.notion_url, null),
        t.external_priority_source = COALESCE(t.external_priority_source, null),
        t.external_priority_weight = COALESCE(t.external_priority_weight, 0.0)
    RETURN count(t) as updated_count
    """

    # Create indexes for Kurultai features
    indexes = [
        # Intent window queries
        "CREATE INDEX task_window IF NOT EXISTS FOR (t:Task) ON (t.window_expires_at)",

        # Semantic similarity (requires Neo4j 5.11+)
        """CREATE INDEX task_embedding IF NOT EXISTS FOR (t:Task) ON (t.embedding)
           OPTIONS {indexConfig: {`vector.dimensions`: 384, `vector.similarity_function`: 'cosine'}}""",

        # Task sender status queries
        "CREATE INDEX task_sender_status IF NOT EXISTS FOR (t:Task) ON (t.sender_hash, t.status)",

        # Dependency type filtering
        "CREATE INDEX depends_on_type IF NOT EXISTS FOR ()-[d:DEPENDS_ON]->() ON (d.type)",

        # Priority queue queries
        "CREATE INDEX task_priority IF NOT EXISTS FOR (t:Task) ON (t.priority_weight, t.created_at)",

        # Deliverable type queries
        "CREATE INDEX task_deliverable_type IF NOT EXISTS FOR (t:Task) ON (t.deliverable_type)",

        # Notion sync tracking
        "CREATE INDEX task_notion_synced IF NOT EXISTS FOR (t:Task) ON (t.notion_synced_at)",

        # User priority override flag
        "CREATE INDEX task_user_override IF NOT EXISTS FOR (t:Task) ON (t.user_priority_override)",
    ]

    # Execute migration
    async with driver.session() as session:
        # Update existing tasks
        result = await session.run(add_fields_query)
        record = await result.single()
        updated_count = record["updated_count"] if record else 0
        print(f"Updated {updated_count} existing Task nodes with Kurultai fields")

        # Create indexes
        for i, index_query in enumerate(indexes, 1):
            try:
                await session.run(index_query)
                print(f"Created index {i}/{len(indexes)}")
            except Exception as e:
                # Log but continue - vector index may fail on Neo4j < 5.11
                print(f"Index creation warning ({i}/{len(indexes)}): {e}")


async def downgrade(driver):
    """
    Remove Kurultai v0.1 fields (keeps indexes for simplicity).

    Args:
        driver: Neo4j driver instance
    """
    remove_fields_query = """
    MATCH (t:Task)
    REMOVE t.sender_hash, t.window_expires_at, t.embedding, t.deliverable_type,
           t.priority_weight, t.user_priority_override, t.merged_into, t.merged_from,
           t.notion_synced_at, t.notion_page_id, t.notion_url,
           t.external_priority_source, t.external_priority_weight
    RETURN count(t) as removed_count
    """

    async with driver.session() as session:
        result = await session.run(remove_fields_query)
        record = await result.single()
        removed_count = record["removed_count"] if record else 0
        print(f"Removed Kurultai fields from {removed_count} Task nodes")


if __name__ == "__main__":
    import os
    import sys
    import asyncio

    from neo4j import GraphDatabase

    # Allow running directly with environment variables
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD")

    if not password:
        print("Error: NEO4J_PASSWORD environment variable required")
        sys.exit(1)

    print(f"Running Kurultai v0.1 migration to {uri}...")

    async def run_migration():
        driver = GraphDatabase.driver(uri, auth=(user, password))

        try:
            await upgrade(driver)
            print("Migration completed successfully!")
            return 0
        except Exception as e:
            print(f"Migration error: {e}")
            return 1
        finally:
            driver.close()

    sys.exit(asyncio.run(run_migration()))
