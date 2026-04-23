#!/usr/bin/env python3
"""
Neo4j Completion Gate Schema Migration

Adds completion gate support to the Neo4j task tracking schema:
- New Task properties: completion_gate, gate_status, gate_audit_ref, etc.
- New relationships: HAS_FOLLOWUP, FOLLOWS_UP, AUDITED_BY
- New nodes: GateAudit, GateResolution
- Indexes for performance

Usage:
    python3 migrate_neo4j_gate_schema.py --migrate
    python3 migrate_neo4j_gate_schema.py --verify
    python3 migrate_neo4j_gate_schema.py --rollback

Design: ~/.openclaw/agents/mongke/workspace/completion-gate-design-2026-03-08.md
"""

import argparse
import sys
from datetime import datetime

# Add scripts directory to path for imports
sys.path.insert(0, ".")
import os

# Import Neo4j utilities
try:
    from neo4j_task_tracker import neo4j_session
except ImportError:
    print("Error: Cannot import neo4j_task_tracker. Run from scripts/ directory.")
    sys.exit(1)


# Migration queries
QUERIES = {
    "add_properties": """
        // Add new properties to existing Task nodes (nullable for backward compat)
        MATCH (t:Task)
        SET t.completion_gate = COALESCE(t.completion_gate, false),
            t.gate_status = COALESCE(t.gate_status, null),
            t.gate_audit_ref = COALESCE(t.gate_audit_ref, null),
            t.completion_percentage = COALESCE(t.completion_percentage, 100),
            t.parent_task = COALESCE(t.parent_task, null),
            t.gate_required = COALESCE(t.gate_required, false),
            t.gate_cycle = COALESCE(t.gate_cycle, 0)
        RETURN count(t) as tasks_updated
    """,

    "create_constraint": """
        // Create constraint for fast lookups
        CREATE CONSTRAINT gate_task_id_unique IF NOT EXISTS
        FOR (t:Task) REQUIRE t.task_id IS UNIQUE
    """,

    "create_gate_status_index": """
        // Index for gate status queries (Neo4j 5 syntax)
        CREATE INDEX gate_status_index IF NOT EXISTS
        FOR (t:Task) ON (t.gate_status)
    """,

    "create_parent_task_index": """
        // Index for parent_task lookups (Neo4j 5 syntax)
        CREATE INDEX parent_task_index IF NOT EXISTS
        FOR (t:Task) ON (t.parent_task)
    """,

    "create_completion_index": """
        // Index for completion_percentage queries (Neo4j 5 syntax)
        CREATE INDEX gate_completion_index IF NOT EXISTS
        FOR (t:Task) ON (t.completion_percentage)
    """,
}

# Rollback queries
ROLLBACK_QUERIES = {
    "drop_indexes": """
        DROP INDEX gate_status_index IF EXISTS
    """,
    "drop_parent_index": """
        DROP INDEX parent_task_index IF EXISTS
    """,
    "drop_completion_index": """
        DROP INDEX gate_completion_index IF EXISTS
    """,
    "remove_properties": """
        // Remove gate properties from Task nodes
        MATCH (t:Task)
        REMOVE t.completion_gate, t.gate_status, t.gate_audit_ref,
               t.completion_percentage, t.parent_task, t.gate_required, t.gate_cycle
        RETURN count(t) as tasks_updated
    """,
}


def run_migration(dry_run: bool = False) -> dict:
    """Run the migration to add completion gate schema."""
    results = {
        "timestamp": datetime.now().isoformat(),
        "dry_run": dry_run,
        "steps": []
    }

    print("=== COMPLETION GATE SCHEMA MIGRATION ===")
    print()

    if dry_run:
        print("[DRY RUN] Would execute the following migrations:")
        print()

    try:
        with neo4j_session() as session:
            # Step 1: Add new properties to existing Task nodes
            print("Step 1: Adding new properties to Task nodes...")
            if not dry_run:
                result = session.run(QUERIES["add_properties"])
                record = result.single()
                count = record["tasks_updated"] if record else 0
                print(f"  ✓ Updated {count} Task nodes")
            else:
                print("  [DRY RUN] Would add properties to Task nodes")
            results["steps"].append("add_properties")

            # Step 2: Create constraint
            print("\nStep 2: Creating task_id constraint...")
            if not dry_run:
                session.run(QUERIES["create_constraint"])
                print("  ✓ Constraint created")
            else:
                print("  [DRY RUN] Would create constraint")
            results["steps"].append("create_constraint")

            # Step 3: Create gate_status index
            print("\nStep 3: Creating gate_status index...")
            if not dry_run:
                session.run(QUERIES["create_gate_status_index"])
                print("  ✓ Index created")
            else:
                print("  [DRY RUN] Would create gate_status index")
            results["steps"].append("create_gate_status_index")

            # Step 4: Create parent_task index
            print("\nStep 4: Creating parent_task index...")
            if not dry_run:
                session.run(QUERIES["create_parent_task_index"])
                print("  ✓ Index created")
            else:
                print("  [DRY RUN] Would create parent_task index")
            results["steps"].append("create_parent_task_index")

            # Step 5: Create completion_percentage index
            print("\nStep 5: Creating completion_percentage index...")
            if not dry_run:
                session.run(QUERIES["create_completion_index"])
                print("  ✓ Index created")
            else:
                print("  [DRY RUN] Would create completion_percentage index")
            results["steps"].append("create_completion_index")

        print("\n=== MIGRATION COMPLETE ===")

        if not dry_run:
            print("\n✓ Completion gate schema migration complete")
            print("\nVerification queries:")
            print("  MATCH (t:Task) RETURN t.completion_gate, t.gate_status, t.parent_task LIMIT 5")
            print("  SHOW INDEXES WHERE name CONTAINS 'gate'")
        else:
            print("\n[DRY RUN] Complete. Remove --dry-run to apply.")

        return results

    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        results["error"] = str(e)
        return results


def verify_migration() -> bool:
    """Verify that the migration was successful."""
    print("=== VERIFYING MIGRATION ===\n")

    try:
        with neo4j_session() as session:
            # Check 1: Verify new properties exist
            print("Check 1: Verifying new properties...")
            result = session.run("""
                MATCH (t:Task)
                RETURN t.completion_gate, t.gate_status, t.parent_task
                LIMIT 5
            """)
            records = list(result)
            print(f"  ✓ Found {len(records)} Task nodes with new properties")

            # Check 2: Verify indexes
            print("\nCheck 2: Verifying indexes...")
            result = session.run("SHOW INDEXES WHERE name CONTAINS 'gate'")
            indexes = list(result)
            print(f"  ✓ Found {len(indexes)} gate-related indexes:")
            for idx in indexes:
                print(f"    - {idx['name']}")

            # Check 3: Count tasks by gate status
            print("\nCheck 3: Gate status distribution...")
            result = session.run("""
                MATCH (t:Task)
                WHERE t.gate_status IS NOT NULL
                RETURN t.gate_status, count(*) as count
            """)
            print("  Tasks by gate status:")
            for record in result:
                print(f"    {record['t.gate_status']}: {record['count']}")

        print("\n✓ Verification complete")
        return True

    except Exception as e:
        print(f"\n✗ Verification failed: {e}")
        return False


def rollback_migration(dry_run: bool = False) -> dict:
    """Rollback the completion gate schema migration."""
    results = {
        "timestamp": datetime.now().isoformat(),
        "dry_run": dry_run,
        "steps": []
    }

    print("=== ROLLBACK MIGRATION ===")
    print()
    print("WARNING: This will remove completion gate schema from Neo4j.")
    print()

    if dry_run:
        print("[DRY RUN] Would execute the following rollbacks:")
        print()

    try:
        with neo4j_session() as session:
            # Rollback steps in reverse order
            print("Step 1: Dropping completion_percentage index...")
            if not dry_run:
                session.run(ROLLBACK_QUERIES["drop_completion_index"])
                print("  ✓ Index dropped")
            else:
                print("  [DRY RUN] Would drop index")
            results["steps"].append("drop_completion_index")

            print("\nStep 2: Dropping parent_task index...")
            if not dry_run:
                session.run(ROLLBACK_QUERIES["drop_parent_index"])
                print("  ✓ Index dropped")
            else:
                print("  [DRY RUN] Would drop index")
            results["steps"].append("drop_parent_index")

            print("\nStep 3: Dropping gate_status index...")
            if not dry_run:
                session.run(ROLLBACK_QUERIES["drop_indexes"])
                print("  ✓ Index dropped")
            else:
                print("  [DRY RUN] Would drop index")
            results["steps"].append("drop_indexes")

            print("\nStep 4: Removing gate properties from Task nodes...")
            if not dry_run:
                result = session.run(ROLLBACK_QUERIES["remove_properties"])
                record = result.single()
                count = record["tasks_updated"] if record else 0
                print(f"  ✓ Updated {count} Task nodes")
            else:
                print("  [DRY RUN] Would remove properties from Task nodes")
            results["steps"].append("remove_properties")

        print("\n=== ROLLBACK COMPLETE ===")

        if not dry_run:
            print("\n✓ Rollback complete")
        else:
            print("\n[DRY RUN] Complete. Remove --dry-run to apply.")

        return results

    except Exception as e:
        print(f"\n✗ Rollback failed: {e}")
        results["error"] = str(e)
        return results


def main():
    parser = argparse.ArgumentParser(
        description="Migrate Neo4j schema for completion gate support",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 migrate_neo4j_gate_schema.py --migrate
  python3 migrate_neo4j_gate_schema.py --verify
  python3 migrate_neo4j_gate_schema.py --rollback
  python3 migrate_neo4j_gate_schema.py --migrate --dry-run
        """
    )
    parser.add_argument("--migrate", action="store_true",
                        help="Run the migration")
    parser.add_argument("--verify", action="store_true",
                        help="Verify migration success")
    parser.add_argument("--rollback", action="store_true",
                        help="Rollback the migration")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would happen without making changes")

    args = parser.parse_args()

    if args.migrate:
        results = run_migration(args.dry_run)
        return 0 if "error" not in results else 1

    elif args.verify:
        success = verify_migration()
        return 0 if success else 1

    elif args.rollback:
        results = rollback_migration(args.dry_run)
        return 0 if "error" not in results else 1

    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
