#!/usr/bin/env python3
"""
Migration: Rename SENT → SENT_BY relationship.

Root cause: (Message)-[:SENT]->(Human) is semantically inverted.
Fix: Rename to SENT_BY to indicate Message was sent BY Human.

Usage:
    python3 migration_rename_sent_rel.py

Verification:
    MATCH ()-[:SENT]->() RETURN count(*)  # Should return 0
    MATCH ()-[:SENT_BY]->() RETURN count(*)  # Should return total messages
"""

import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from neo4j_task_tracker import get_driver, close_driver, is_neo4j_available

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def migrate():
    """Migrate all SENT relationships to SENT_BY."""

    if not is_neo4j_available():
        logger.error("Neo4j is not available. Aborting migration.")
        return False

    driver = get_driver()

    try:
        with driver.session() as session:
            # Step 1: Count existing SENT relationships
            logger.info("Step 1: Counting existing SENT relationships...")
            result = session.run("MATCH ()-[r:SENT]->() RETURN count(r) AS count")
            count = result.single()["count"]
            logger.info(f"  Found {count} SENT relationships to migrate")

            if count == 0:
                logger.info("  No SENT relationships found. Migration complete.")
                return True

            # Step 2: Create SENT_BY relationships
            logger.info("Step 2: Creating SENT_BY relationships...")
            result = session.run(
                """
                MATCH (m:Message)-[r:SENT]->(h:Human)
                CREATE (m)-[:SENT_BY]->(h)
                RETURN count(*) AS created
                """
            )
            created = result.single()["created"]
            logger.info(f"  Created {created} SENT_BY relationships")

            # Step 3: Delete old SENT relationships
            logger.info("Step 3: Deleting old SENT relationships...")
            result = session.run(
                """
                MATCH (m:Message)-[r:SENT]->(h:Human)
                DELETE r
                RETURN count(*) AS deleted
                """
            )
            deleted = result.single()["deleted"]
            logger.info(f"  Deleted {deleted} SENT relationships")

            # Step 4: Verification - ensure no SENT relationships remain
            logger.info("Step 4: Verification...")
            result = session.run("MATCH ()-[r:SENT]->() RETURN count(r) AS count")
            remaining = result.single()["count"]

            if remaining > 0:
                logger.error(f"  FAILED: {remaining} SENT relationships still exist!")
                return False

            # Step 5: Verify SENT_BY count matches expected
            result = session.run("MATCH ()-[r:SENT_BY]->() RETURN count(r) AS count")
            sent_by_count = result.single()["count"]
            logger.info(f"  VERIFIED: {sent_by_count} SENT_BY relationships exist")
            logger.info("  Migration successful!")

            return True

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False


def verify():
    """Verify migration completed successfully."""

    if not is_neo4j_available():
        logger.error("Neo4j is not available.")
        return False

    driver = get_driver()

    try:
        with driver.session() as session:
            # Check SENT relationships
            result = session.run("MATCH ()-[r:SENT]->() RETURN count(r) AS count")
            sent_count = result.single()["count"]

            # Check SENT_BY relationships
            result = session.run("MATCH ()-[r:SENT_BY]->() RETURN count(r) AS count")
            sent_by_count = result.single()["count"]

            logger.info(f"SENT relationships: {sent_count} (should be 0)")
            logger.info(f"SENT_BY relationships: {sent_by_count}")

            return sent_count == 0

    except Exception as e:
        logger.error(f"Verification failed: {e}")
        return False


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Migrate SENT → SENT_BY relationships")
    parser.add_argument("--verify", action="store_true", help="Only verify, don't migrate")
    args = parser.parse_args()

    if args.verify:
        success = verify()
        sys.exit(0 if success else 1)
    else:
        success = migrate()
        sys.exit(0 if success else 1)
