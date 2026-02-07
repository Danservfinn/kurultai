#!/usr/bin/env python3
"""Neo4j migration runner for Kurultai v0.2.

Registers all migrations (v1, v2, v3, v4) and runs to the specified target version.
Supports dry-run mode for validation before applying changes.

Usage:
    python3 scripts/run_migrations.py --target-version 4
    python3 scripts/run_migrations.py --target-version 4 --dry-run
    python3 scripts/run_migrations.py --status
"""

import argparse
import os
import sys
from pathlib import Path

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from migrations.migration_manager import MigrationManager
from migrations.v1_initial_schema import V1InitialSchema
from migrations.v2_kurultai_dependencies import V2KurultaiDependencies
from migrations.v3_capability_acquisition import V3CapabilityAcquisition
from migrations.v4_proposals import V4Proposals
from migrations.v5_chat_summaries import V5ChatSummaries


def main():
    parser = argparse.ArgumentParser(description="Kurultai Neo4j Migration Runner")
    parser.add_argument("--target-version", type=int, default=None,
                        help="Target schema version (default: latest)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate migrations without applying")
    parser.add_argument("--status", action="store_true",
                        help="Show current migration status")
    parser.add_argument("--rollback", type=int, default=None,
                        help="Rollback N steps")
    args = parser.parse_args()

    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD")

    if not password:
        print("Error: NEO4J_PASSWORD environment variable required")
        sys.exit(1)

    print(f"Connecting to Neo4j at {uri}...")

    try:
        manager = MigrationManager(uri, user, password)
    except Exception as e:
        print(f"Connection failed: {e}")
        sys.exit(1)

    try:
        # Register all migrations
        V1InitialSchema.register(manager)
        V2KurultaiDependencies.register(manager)
        V3CapabilityAcquisition.register(manager)
        V4Proposals.register(manager)
        V5ChatSummaries.register(manager)
        print("Registered migrations: v1, v2, v3, v4, v5")

        current = manager.get_current_version()
        print(f"Current schema version: {current}")

        if args.status:
            history = manager.get_migration_history()
            if history:
                print("\nMigration history:")
                for h in history:
                    status = "OK" if h.success else "FAILED"
                    print(f"  v{h.version} ({h.name}): {status} at {h.applied_at}")
            else:
                print("No migration history found.")
            return

        if args.rollback is not None:
            print(f"Rolling back {args.rollback} step(s)...")
            success = manager.rollback(steps=args.rollback)
            if success:
                print(f"Rollback complete. Now at version: {manager.get_current_version()}")
            else:
                print("Rollback failed!")
                sys.exit(1)
            return

        target = args.target_version
        if target is None:
            target = 5  # Latest

        if args.dry_run:
            print(f"\n[DRY RUN] Would migrate from v{current} to v{target}")
            for v in range(current + 1, target + 1):
                print(f"  Would apply: v{v}")
            print("[DRY RUN] No changes applied.")
            return

        if current >= target:
            print(f"Already at version {current} (target: {target}). Nothing to do.")
            return

        print(f"\nMigrating from v{current} to v{target}...")
        success = manager.migrate(target_version=target)

        if success:
            new_version = manager.get_current_version()
            print(f"Migration complete! Now at version: {new_version}")
        else:
            print("Migration failed!")
            sys.exit(1)

    finally:
        manager.close()


if __name__ == "__main__":
    main()
