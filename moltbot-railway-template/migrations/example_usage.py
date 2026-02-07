"""
Example Usage of MigrationManager

This script demonstrates how to use the MigrationManager for Neo4j schema migrations.
"""

import os
import logging
from migrations import MigrationManager, V1InitialSchema

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def example_basic_migration():
    """Example: Basic migration workflow."""

    # Get connection details from environment
    neo4j_uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
    neo4j_password = os.environ.get("NEO4J_PASSWORD", "password")

    # Method 1: Using context manager (recommended)
    with MigrationManager(neo4j_uri, neo4j_user, neo4j_password) as manager:
        # Register the initial schema migration
        V1InitialSchema.register(manager)

        # Check current status
        status = manager.status()
        logger.info(f"Current version: {status['current_version']}")
        logger.info(f"Pending migrations: {status['pending_count']}")

        # Run migrations to latest
        success = manager.migrate()
        if success:
            logger.info("Migration successful!")

        # Check new status
        new_status = manager.status()
        logger.info(f"New version: {new_status['current_version']}")


def example_rollback():
    """Example: Rolling back migrations."""

    neo4j_uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
    neo4j_password = os.environ.get("NEO4J_PASSWORD", "password")

    with MigrationManager(neo4j_uri, neo4j_user, neo4j_password) as manager:
        V1InitialSchema.register(manager)

        # Rollback 1 step
        logger.info("Rolling back 1 migration...")
        success = manager.rollback(steps=1)
        if success:
            logger.info("Rollback successful!")


def example_custom_migration():
    """Example: Registering a custom migration."""

    neo4j_uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
    neo4j_password = os.environ.get("NEO4J_PASSWORD", "password")

    with MigrationManager(neo4j_uri, neo4j_user, neo4j_password) as manager:
        # First register v1
        V1InitialSchema.register(manager)

        # Register a custom v2 migration
        manager.register_migration(
            version=2,
            name="add_task_priority",
            up_cypher="""
                CREATE INDEX task_priority_index IF NOT EXISTS
                FOR (t:Task) ON (t.priority);

                MATCH (m:MigrationControl)
                SET m.version = 2, m.last_updated = datetime();
            """,
            down_cypher="""
                DROP INDEX task_priority_index IF EXISTS;

                MATCH (m:MigrationControl)
                SET m.version = 1, m.last_updated = datetime();
            """,
            description="Add priority field to Task nodes"
        )

        # Migrate to v2
        manager.migrate(target_version=2)


def example_status_check():
    """Example: Checking migration status."""

    neo4j_uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
    neo4j_password = os.environ.get("NEO4J_PASSWORD", "password")

    with MigrationManager(neo4j_uri, neo4j_user, neo4j_password) as manager:
        V1InitialSchema.register(manager)

        status = manager.status()
        print("\n=== Migration Status ===")
        print(f"Current Version: {status['current_version']}")
        print(f"Latest Registered: {status['latest_registered']}")
        print(f"Pending Count: {status['pending_count']}")
        print(f"Pending Versions: {status['pending_versions']}")
        print(f"Registered Count: {status['registered_count']}")

        if status['validation_errors']:
            print(f"\nValidation Errors: {status['validation_errors']}")

        if status['recent_history']:
            print("\nRecent History:")
            for h in status['recent_history']:
                print(f"  v{h['version']} {h['name']} - {'✓' if h['success'] else '✗'}")


def example_convenience_function():
    """Example: Using the convenience function."""

    from migrations.v1_initial_schema import run_initial_schema_migration

    neo4j_uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
    neo4j_password = os.environ.get("NEO4J_PASSWORD", "password")

    # One-line migration
    success = run_initial_schema_migration(neo4j_uri, neo4j_user, neo4j_password)
    if success:
        logger.info("Initial schema migration completed!")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python example_usage.py [basic|rollback|custom|status|convenience]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "basic":
        example_basic_migration()
    elif command == "rollback":
        example_rollback()
    elif command == "custom":
        example_custom_migration()
    elif command == "status":
        example_status_check()
    elif command == "convenience":
        example_convenience_function()
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
