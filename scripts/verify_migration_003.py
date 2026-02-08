#!/usr/bin/env python3
"""
Neo4j Migration 003 (v4_proposals) Verification Script

This script verifies that the proposal system schema migration has been applied
to the production Neo4j database.

Usage:
    export NEO4J_URI="bolt://neo4j.railway.internal:7687"
    export NEO4J_USER="neo4j"
    export NEO4J_PASSWORD="<password>"
    python3 scripts/verify_migration_003.py
"""

import os
import sys
from neo4j import GraphDatabase

# Expected constraints from migration 003 (v4_proposals)
EXPECTED_CONSTRAINTS = [
    "proposal_id_unique",      # ArchitectureProposal.id IS UNIQUE
    "opportunity_id_unique",   # ImprovementOpportunity.id IS UNIQUE
    "vetting_id_unique",       # Vetting.id IS UNIQUE
    "implementation_id_unique", # Implementation.id IS UNIQUE
    "validation_id_unique",    # Validation.id IS UNIQUE
]

# Expected indexes from migration 003
EXPECTED_INDEXES = [
    # ArchitectureProposal indexes
    "proposal_status",
    "proposal_priority",
    "proposal_created_at",
    "proposal_implementation_status",
    # ImprovementOpportunity indexes
    "opportunity_status",
    "opportunity_priority",
    "opportunity_type",
    "opportunity_proposed_by",
    # Vetting indexes
    "vetting_proposal",
    "vetting_vetted_by",
    "vetting_created_at",
    # Implementation indexes
    "implementation_proposal",
    "implementation_status",
    "implementation_started_at",
    # Validation indexes
    "validation_implementation",
    "validation_passed",
    "validation_validated_at",
    # Relationship indexes
    "evolves_into",
    "updates_section",
    "synced_to",
    "has_vetting",
    "implemented_by",
    "validated_by",
]

# Node types that should exist after migration
EXPECTED_NODE_TYPES = [
    "ArchitectureProposal",
    "ImprovementOpportunity",
    "Vetting",
    "Implementation",
    "Validation",
]


def get_constraints(driver):
    """Get all constraints from Neo4j."""
    with driver.session() as session:
        result = session.run("SHOW CONSTRAINTS YIELD name, type")
        return {record["name"]: record["type"] for record in result}


def get_indexes(driver):
    """Get all indexes from Neo4j."""
    with driver.session() as session:
        result = session.run("SHOW INDEXES YIELD name, type")
        return {record["name"]: record["type"] for record in result}


def get_migration_version(driver):
    """Get current migration version from Neo4j."""
    with driver.session() as session:
        result = session.run("""
            MATCH (m:Migration)
            RETURN m.version as version, m.name as name, m.applied_at as applied_at
            ORDER BY m.version DESC
            LIMIT 1
        """)
        record = result.single()
        if record:
            return {
                "version": record["version"],
                "name": record["name"],
                "applied_at": record["applied_at"]
            }
        return None


def get_all_migrations(driver):
    """Get all migration records from Neo4j."""
    with driver.session() as session:
        result = session.run("""
            MATCH (m:Migration)
            RETURN m.version as version, m.name as name, m.applied_at as applied_at
            ORDER BY m.version ASC
        """)
        return [
            {
                "version": record["version"],
                "name": record["name"],
                "applied_at": record["applied_at"]
            }
            for record in result
        ]


def check_node_types(driver):
    """Check if expected node types have been used in the database."""
    node_counts = {}
    with driver.session() as session:
        for node_type in EXPECTED_NODE_TYPES:
            result = session.run(f"""
                MATCH (n:{node_type})
                RETURN count(n) as count
            """)
            record = result.single()
            node_counts[node_type] = record["count"] if record else 0
    return node_counts


def verify_migration():
    """Main verification function."""
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD")

    if not password:
        print("Error: NEO4J_PASSWORD environment variable required")
        sys.exit(1)

    print(f"Connecting to Neo4j at {uri}...")

    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        driver.verify_connectivity()
        print("Connected successfully!\n")
    except Exception as e:
        print(f"Connection failed: {e}")
        sys.exit(1)

    try:
        # Get current state
        constraints = get_constraints(driver)
        indexes = get_indexes(driver)
        current_migration = get_migration_version(driver)
        all_migrations = get_all_migrations(driver)
        node_counts = check_node_types(driver)

        # Print report header
        print("=" * 70)
        print("NEO4J MIGRATION 003 (v4_proposals) VERIFICATION REPORT")
        print("=" * 70)
        print()

        # Migration version status
        print("-" * 70)
        print("MIGRATION VERSION STATUS")
        print("-" * 70)
        if current_migration:
            print(f"Current version: {current_migration['version']}")
            print(f"Migration name: {current_migration['name']}")
            print(f"Applied at: {current_migration['applied_at']}")
        else:
            print("No migration records found!")
        print()

        # All migrations
        print("-" * 70)
        print("MIGRATION HISTORY")
        print("-" * 70)
        if all_migrations:
            for m in all_migrations:
                print(f"  v{m['version']}: {m['name']} (applied: {m['applied_at']})")
        else:
            print("  No migrations found")
        print()

        # Constraints check
        print("-" * 70)
        print("CONSTRAINTS VERIFICATION")
        print("-" * 70)
        constraints_ok = True
        for constraint in EXPECTED_CONSTRAINTS:
            if constraint in constraints:
                print(f"  [OK] {constraint}: {constraints[constraint]}")
            else:
                print(f"  [MISSING] {constraint}")
                constraints_ok = False

        if constraints_ok:
            print(f"\n  All {len(EXPECTED_CONSTRAINTS)} constraints present!")
        else:
            print(f"\n  WARNING: Some constraints are missing!")
        print()

        # Indexes check
        print("-" * 70)
        print("INDEXES VERIFICATION")
        print("-" * 70)
        indexes_ok = True
        for index in EXPECTED_INDEXES:
            if index in indexes:
                print(f"  [OK] {index}: {indexes[index]}")
            else:
                print(f"  [MISSING] {index}")
                indexes_ok = False

        if indexes_ok:
            print(f"\n  All {len(EXPECTED_INDEXES)} indexes present!")
        else:
            print(f"\n  WARNING: Some indexes are missing!")
        print()

        # Node types check
        print("-" * 70)
        print("NODE TYPES STATUS")
        print("-" * 70)
        for node_type, count in node_counts.items():
            status = "[USED]" if count > 0 else "[DEFINED]"
            print(f"  {status} {node_type}: {count} nodes")
        print()

        # Summary
        print("=" * 70)
        print("SUMMARY")
        print("=" * 70)

        migration_applied = current_migration and current_migration['version'] >= 4

        if migration_applied and constraints_ok and indexes_ok:
            print("STATUS: MIGRATION 003 (v4_proposals) IS DEPLOYED AND APPLIED")
            print()
            print("The proposal system schema is fully configured:")
            print(f"  - All {len(EXPECTED_CONSTRAINTS)} constraints created")
            print(f"  - All {len(EXPECTED_INDEXES)} indexes created")
            print(f"  - Migration version: {current_migration['version']}")
            return 0
        elif constraints_ok and indexes_ok:
            print("STATUS: SCHEMA PRESENT BUT MIGRATION RECORD MISSING")
            print()
            print("The constraints and indexes exist but the Migration node")
            print("may not have been created. This could indicate:")
            print("  - Manual schema creation")
            print("  - Migration record was not committed")
            return 1
        else:
            print("STATUS: MIGRATION NOT FULLY APPLIED")
            print()
            print("Missing components detected:")
            if not constraints_ok:
                missing = [c for c in EXPECTED_CONSTRAINTS if c not in constraints]
                print(f"  - Missing constraints: {', '.join(missing)}")
            if not indexes_ok:
                missing = [i for i in EXPECTED_INDEXES if i not in indexes]
                print(f"  - Missing indexes: {', '.join(missing)}")
            print()
            print("To apply the migration, run:")
            print("  python /app/scripts/run_migrations.py --target-version 4")
            return 1

    finally:
        driver.close()


if __name__ == "__main__":
    sys.exit(verify_migration())
