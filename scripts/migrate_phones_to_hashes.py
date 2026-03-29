#!/usr/bin/env python3
"""
Migration script to convert existing plaintext phone numbers in Identifier nodes
to HMAC-SHA256 hashed values for PII protection.

Run this ONCE to migrate existing data. After migration, all new phone numbers
will be automatically hashed via neo4j_human_v2.py.

Prerequisites:
1. PHONE_HASH_SALT environment variable must be set
2. Neo4j must be running
3. Backup your database before running: neo4j-admin database dump

Usage:
    export PHONE_HASH_SALT="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
    python3 migrate_phones_to_hashes.py --dry-run  # Preview changes
    python3 migrate_phones_to_hashes.py            # Execute migration
"""

import os
import sys
import hmac
import hashlib
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import get_driver

# Configuration
PHONE_HASH_SALT = os.environ.get('PHONE_HASH_SALT')

if not PHONE_HASH_SALT:
    print("ERROR: PHONE_HASH_SALT environment variable must be set")
    print("Generate with: python3 -c 'import secrets; print(secrets.token_hex(32))'")
    sys.exit(1)


def hash_phone(phone: str) -> str:
    """Hash a phone number using HMAC-SHA256 with salt."""
    import hmac
    h = hmac.new(PHONE_HASH_SALT.encode('utf-8'), phone.encode('utf-8'), hashlib.sha256)
    return h.hexdigest()


def migrate_phones(dry_run: bool = True) -> dict:
    """Migrate plaintext phone numbers to hashed values.

    Args:
        dry_run: If True, preview changes without executing

    Returns:
        Dict with migration statistics
    """
    driver = get_driver()
    stats = {
        "total_identifiers": 0,
        "plaintext_phones": 0,
        "already_hashed": 0,
        "migrated": 0,
        "errors": 0,
        "timestamp": datetime.now().isoformat()
    }

    try:
        with driver.session() as session:
            # Find all SIGNAL_PHONE identifiers with plaintext values (not 64-char hex)
            result = session.run("""
                MATCH (i:Identifier {type: 'SIGNAL_PHONE'})
                RETURN i.id AS id, i.value AS value
            """)

            identifiers = list(result)
            stats["total_identifiers"] = len(identifiers)

            print(f"\nFound {len(identifiers)} SIGNAL_PHONE identifiers")

            for record in identifiers:
                identifier_id = record["id"]
                phone_value = record["value"]

                # Skip if already hashed (64-character hex string)
                if len(phone_value) == 64 and all(c in '0123456789abcdef' for c in phone_value.lower()):
                    stats["already_hashed"] += 1
                    print(f"  ✓ Already hashed: {phone_value[:16]}...")
                    continue

                # This is a plaintext phone number
                stats["plaintext_phones"] += 1
                print(f"\n  → Migrating: {phone_value}")

                # Generate hash
                phone_hash = hash_phone(phone_value)
                print(f"    Hash: {phone_hash[:16]}...")

                # Store format hint for redaction
                format_hint = phone_value[:2] if phone_value.startswith('+') else '+1'

                if dry_run:
                    print(f"    [DRY RUN] Would update Identifier {identifier_id}")
                else:
                    # Update the identifier with hashed value
                    session.run("""
                        MATCH (i:Identifier {id: $id})
                        SET i.value = $phone_hash,
                            i.formatHint = $format_hint,
                            i.migratedAt = datetime()
                        RETURN i.id AS id
                    """, id=identifier_id, phone_hash=phone_hash, format_hint=format_hint)

                    stats["migrated"] += 1
                    print(f"    ✓ Migrated Identifier {identifier_id}")

    except Exception as e:
        print(f"\nERROR: {e}")
        stats["errors"] += 1

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Migrate plaintext phone numbers to HMAC-SHA256 hashes"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without executing (default: True)"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute migration (default: dry-run mode)"
    )

    args = parser.parse_args()

    # Default to dry-run for safety
    dry_run = not args.execute

    if dry_run:
        print("=" * 70)
        print("DRY RUN MODE - No changes will be made")
        print("Use --execute flag to run the actual migration")
        print("=" * 70)

    print(f"\nMigration started at {datetime.now().isoformat()}")
    print(f"PHONE_HASH_SALT: {PHONE_HASH_SALT[:16]}...")

    stats = migrate_phones(dry_run=dry_run)

    print("\n" + "=" * 70)
    print("MIGRATION SUMMARY")
    print("=" * 70)
    print(f"Total identifiers scanned:  {stats['total_identifiers']}")
    print(f"Plaintext phones found:     {stats['plaintext_phones']}")
    print(f"Already hashed:             {stats['already_hashed']}")
    print(f"Migrated:                   {stats['migrated']}")
    print(f"Errors:                     {stats['errors']}")
    print("=" * 70)

    if stats['plaintext_phones'] > 0 and dry_run:
        print("\nTo execute migration, run:")
        print("  python3 migrate_phones_to_hashes.py --execute")

    return 0 if stats['errors'] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
