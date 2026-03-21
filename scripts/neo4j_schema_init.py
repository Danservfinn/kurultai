#!/usr/bin/env python3
"""
neo4j_schema_init.py — Initialize Neo4j constraints and indexes for Kurultai Task System.

This script creates the required schema for the Neo4j-first architecture:
- Unique constraints on task_id and label
- Indexes for common query patterns
- Event correlation indexes

Run once after Neo4j installation or migration.
Idempotent - safe to run multiple times.

Usage:
    python3 scripts/neo4j_schema_init.py [--verify]
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from neo4j_task_tracker import neo4j_session


# Schema definitions
CONSTRAINTS = [
    # Unique constraint on task_id - prevents duplicate task_id entries
    {
        "name": "task_id_unique",
        "cypher": "CREATE CONSTRAINT task_id_unique IF NOT EXISTS FOR (t:Task) REQUIRE t.task_id IS UNIQUE",
        "description": "Ensures task_id is unique across all Task nodes"
    },
    # Unique constraint on label - prevents duplicate agent-taskid labels
    {
        "name": "task_label_unique",
        "cypher": "CREATE CONSTRAINT task_label_unique IF NOT EXISTS FOR (t:Task) REQUIRE t.label IS UNIQUE",
        "description": "Ensures label (agent-taskid) is unique"
    },
]

INDEXES = [
    # Status index for task discovery queries
    {
        "name": "task_status_idx",
        "cypher": "CREATE INDEX task_status_idx IF NOT EXISTS FOR (t:Task) ON (t.status)",
        "description": "Speeds up task status queries"
    },
    # Composite index for agent + status queries (most common pattern)
    {
        "name": "task_agent_status_idx",
        "cypher": "CREATE INDEX task_agent_status_idx IF NOT EXISTS FOR (t:Task) ON (t.agent, t.status)",
        "description": "Speeds up pending task discovery by agent"
    },
    # Created timestamp index for time-based queries
    {
        "name": "task_created_idx",
        "cypher": "CREATE INDEX task_created_idx IF NOT EXISTS FOR (t:Task) ON (t.created)",
        "description": "Speeds up time-based task queries"
    },
    # Priority index for queue prioritization
    {
        "name": "task_priority_idx",
        "cypher": "CREATE INDEX task_priority_idx IF NOT EXISTS FOR (t:Task) ON (t.priority)",
        "description": "Speeds up priority-based queries"
    },
    # Event correlation indexes
    {
        "name": "event_task_idx",
        "cypher": "CREATE INDEX event_task_idx IF NOT EXISTS FOR (e:Event) ON (e.task_id)",
        "description": "Speeds up event correlation queries by task_id"
    },
    {
        "name": "event_ts_idx",
        "cypher": "CREATE INDEX event_ts_idx IF NOT EXISTS FOR (e:Event) ON (e.ts)",
        "description": "Speeds up time-based event queries"
    },
    # Session key index for atomic claim verification
    {
        "name": "task_session_key_idx",
        "cypher": "CREATE INDEX task_session_key_idx IF NOT EXISTS FOR (t:Task) ON (t.session_key)",
        "description": "Speeds up session-based claim verification"
    },
]


def init_schema(verify_only=False, verbose=True):
    """Initialize Neo4j schema with constraints and indexes.

    Args:
        verify_only: If True, only verify schema exists without creating
        verbose: If True, print progress messages

    Returns:
        dict with 'constraints' and 'indexes' lists of created/verified items
    """
    results = {"constraints": [], "indexes": [], "errors": []}

    try:
        with neo4j_session() as session:
            # Get existing constraints
            existing_constraints = set()
            try:
                result = session.run("SHOW CONSTRAINTS")
                for record in result:
                    name = record.get("name") or record.get("constraintName")
                    if name:
                        existing_constraints.add(name)
            except Exception as e:
                if verbose:
                    print(f"[WARN] Could not list existing constraints: {e}")

            # Get existing indexes
            existing_indexes = set()
            try:
                result = session.run("SHOW INDEXES")
                for record in result:
                    name = record.get("name") or record.get("indexName")
                    if name:
                        existing_indexes.add(name)
            except Exception as e:
                if verbose:
                    print(f"[WARN] Could not list existing indexes: {e}")

            if verify_only:
                # Just verify
                for constraint in CONSTRAINTS:
                    if constraint["name"] in existing_constraints:
                        results["constraints"].append(constraint["name"])
                        if verbose:
                            print(f"[OK] Constraint exists: {constraint['name']}")
                    else:
                        results["errors"].append(f"Missing constraint: {constraint['name']}")
                        if verbose:
                            print(f"[MISSING] Constraint: {constraint['name']}")

                for index in INDEXES:
                    if index["name"] in existing_indexes:
                        results["indexes"].append(index["name"])
                        if verbose:
                            print(f"[OK] Index exists: {index['name']}")
                    else:
                        results["errors"].append(f"Missing index: {index['name']}")
                        if verbose:
                            print(f"[MISSING] Index: {index['name']}")
            else:
                # Create constraints
                for constraint in CONSTRAINTS:
                    try:
                        if constraint["name"] not in existing_constraints:
                            session.run(constraint["cypher"])
                            if verbose:
                                print(f"[CREATED] Constraint: {constraint['name']} - {constraint['description']}")
                        else:
                            if verbose:
                                print(f"[EXISTS] Constraint: {constraint['name']}")
                        results["constraints"].append(constraint["name"])
                    except Exception as e:
                        # Check if it's a "already exists" error
                        if "already exists" in str(e).lower():
                            if verbose:
                                print(f"[EXISTS] Constraint: {constraint['name']}")
                            results["constraints"].append(constraint["name"])
                        else:
                            results["errors"].append(f"Failed to create constraint {constraint['name']}: {e}")
                            if verbose:
                                print(f"[ERROR] Constraint {constraint['name']}: {e}")

                # Create indexes
                for index in INDEXES:
                    try:
                        if index["name"] not in existing_indexes:
                            session.run(index["cypher"])
                            if verbose:
                                print(f"[CREATED] Index: {index['name']} - {index['description']}")
                        else:
                            if verbose:
                                print(f"[EXISTS] Index: {index['name']}")
                        results["indexes"].append(index["name"])
                    except Exception as e:
                        # Check if it's an "already exists" error
                        if "already exists" in str(e).lower() or "equivalent" in str(e).lower():
                            if verbose:
                                print(f"[EXISTS] Index: {index['name']}")
                            results["indexes"].append(index["name"])
                        else:
                            results["errors"].append(f"Failed to create index {index['name']}: {e}")
                            if verbose:
                                print(f"[ERROR] Index {index['name']}: {e}")

        if verbose:
            print(f"\n[SUMMARY] Created/verified {len(results['constraints'])} constraints, {len(results['indexes'])} indexes")
            if results["errors"]:
                print(f"[ERRORS] {len(results['errors'])} errors occurred")

    finally:
        pass

    return results


def verify_schema():
    """Verify that all required schema elements exist.

    Returns True if all constraints and indexes exist, False otherwise.
    """
    results = init_schema(verify_only=True, verbose=False)
    return len(results["errors"]) == 0


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Initialize Neo4j schema for Kurultai Task System")
    parser.add_argument("--verify", action="store_true", help="Only verify schema, don't create")
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress output")
    args = parser.parse_args()

    verbose = not args.quiet

    if verbose:
        print("=== Neo4j Schema Initialization ===\n")

    results = init_schema(verify_only=args.verify, verbose=verbose)

    # Exit with error code if verification failed
    if args.verify and results["errors"]:
        sys.exit(1)

    # Exit with error code if creation failed
    if not args.verify and results["errors"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
