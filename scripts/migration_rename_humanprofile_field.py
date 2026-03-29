#!/usr/bin/env python3
"""
Migration: Rename HumanProfile.human_id → phone_e164

This migration resolves naming confusion where:
- HumanStoreV2.human_id = UUID (internal identifier)
- HumanProfileStore.human_id = E.164 phone number (links to Person.phone_number)

After migration, HumanProfile will use phone_e164 for clarity.

Usage:
    python3 migration_rename_humanprofile_field.py [--dry-run] [--verify]

Options:
    --dry-run    Show what would be changed without executing
    --verify     Verify migration completed successfully

Steps:
    1. Drop old index on human_id
    2. Add new phone_e164 field (backfilled from human_id)
    3. Create new index on phone_e164
    4. Remove old human_id field
"""

import sys
import os
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import get_driver, close_driver


def print_step(step_num: int, total: int, message: str):
    """Print migration step with progress indicator."""
    print(f"[{step_num}/{total}] {message}")


def migrate(dry_run: bool = False) -> bool:
    """Execute the migration."""
    driver = get_driver()
    total_steps = 5

    try:
        with driver.session() as session:
            # Step 1: Drop old index
            print_step(1, total_steps, "Dropping old index human_profile_human_id_idx...")
            if not dry_run:
                result = session.run("DROP INDEX human_profile_human_id_idx IF EXISTS")
                print(f"   ✓ Dropped (or didn't exist)")
            else:
                print("   [DRY RUN] Would drop index human_profile_human_id_idx")

            # Step 2: Add new field (backfill from old)
            print_step(2, total_steps, "Adding phone_e164 field (backfilling from human_id)...")
            if not dry_run:
                result = session.run("""
                    MATCH (hp:HumanProfile)
                    WHERE hp.human_id IS NOT NULL
                    SET hp.phone_e164 = hp.human_id
                    RETURN count(hp) AS updated
                """)
                record = result.single()
                print(f"   ✓ Backfilled {record['updated']} profiles")
            else:
                # Count what would be updated
                result = session.run("""
                    MATCH (hp:HumanProfile)
                    WHERE hp.human_id IS NOT NULL
                    RETURN count(hp) AS would_update
                """)
                record = result.single()
                print(f"   [DRY RUN] Would backfill {record['would_update']} profiles")

            # Step 3: Create new index
            print_step(3, total_steps, "Creating new index human_profile_phone_e164_idx...")
            if not dry_run:
                session.run("""
                    CREATE INDEX human_profile_phone_e164_idx IF NOT EXISTS
                    FOR (h:HumanProfile) ON (h.phone_e164)
                """)
                print("   ✓ Index created")
            else:
                print("   [DRY RUN] Would create index human_profile_phone_e164_idx")

            # Step 4: Remove old field
            print_step(4, total_steps, "Removing old human_id field...")
            if not dry_run:
                result = session.run("""
                    MATCH (hp:HumanProfile)
                    WHERE hp.phone_e164 IS NOT NULL
                    REMOVE hp.human_id
                    RETURN count(hp) AS cleaned
                """)
                record = result.single()
                print(f"   ✓ Removed human_id from {record['cleaned']} profiles")
            else:
                print("   [DRY RUN] Would remove human_id field from all profiles")

            # Step 5: Verify migration
            print_step(5, total_steps, "Verifying migration...")
            result = session.run("""
                MATCH (hp:HumanProfile)
                RETURN count(hp) AS total,
                       count(hp.phone_e164) AS with_phone,
                       count(hp.human_id) AS with_old_field
            """)
            record = result.single()

            print(f"\n   Migration Summary:")
            print(f"   • Total profiles: {record['total']}")
            print(f"   • With phone_e164: {record['with_phone']}")
            print(f"   • Still with human_id: {record['with_old_field']}")

            if record['with_old_field'] > 0:
                print("\n   ⚠ WARNING: Some profiles still have human_id field")
                return False

            if record['with_phone'] < record['total']:
                print("\n   ⚠ WARNING: Not all profiles have phone_e164")
                return False

            print("\n   ✓ Migration verified successfully")
            return True

    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        return False
    finally:
        close_driver()


def verify() -> bool:
    """Verify migration completed successfully."""
    driver = get_driver()

    try:
        with driver.session() as session:
            print("Verifying migration...")

            # Check for any remaining human_id references
            result = session.run("""
                MATCH (hp:HumanProfile)
                WHERE hp.human_id IS NOT NULL
                RETURN count(hp) AS with_old_field
            """)
            record = result.single()

            if record['with_old_field'] > 0:
                print(f"✗ Found {record['with_old_field']} profiles still using human_id")
                return False

            # Check all profiles have phone_e164
            result = session.run("""
                MATCH (hp:HumanProfile)
                RETURN count(hp) AS total,
                       count(hp.phone_e164) AS with_phone
            """)
            record = result.single()

            print(f"✓ All {record['total']} profiles using phone_e164")
            print(f"✓ No human_id references remain")
            return True

    except Exception as e:
        print(f"✗ Verification failed: {e}")
        return False
    finally:
        close_driver()


def main():
    parser = argparse.ArgumentParser(
        description="Migration: Rename HumanProfile.human_id → phone_e164"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without executing"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify migration completed successfully"
    )

    args = parser.parse_args()

    print("=" * 70)
    print("HumanProfile Field Rename Migration")
    print("human_id → phone_e164")
    print("=" * 70)
    print()

    if args.verify:
        success = verify()
        sys.exit(0 if success else 1)

    if args.dry_run:
        print("DRY RUN MODE - No changes will be made\n")

    success = migrate(dry_run=args.dry_run)

    print()
    print("=" * 70)

    if success:
        if args.dry_run:
            print("Dry run complete. Run without --dry-run to execute migration.")
            print("Then update neo4j_human_profile.py and run tests.")
        else:
            print("Migration complete!")
            print("Next steps:")
            print("  1. Update neo4j_human_profile.py (all hp.human_id → hp.phone_e164)")
            print("  2. Run tests to verify functionality")
            print("  3. Run: python3 migration_rename_humanprofile_field.py --verify")
    else:
        print("Migration failed. Check errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
