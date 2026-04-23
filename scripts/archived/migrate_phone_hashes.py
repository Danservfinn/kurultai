#!/usr/bin/env python3
"""
Migration script to convert plaintext phone numbers to HMAC-SHA256 hashes.

This script queries all Identifier nodes with type='SIGNAL_PHONE' and plaintext values
(those NOT matching the 64-character hex pattern), then migrates them to use hashes.

Usage:
    # Dry run (shows what would be changed)
    python3 migrate_phone_hashes.py --dry-run

    # Apply migration
    python3 migrate_phone_hashes.py --apply

    # Verify no plaintext remains
    python3 migrate_phone_hashes.py --verify
"""

import argparse
import os
import sys
from typing import Dict, List, Any
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_human_v2 import HumanStoreV2, hash_phone


def find_plaintext_phones(store: HumanStoreV2) -> List[Dict[str, Any]]:
    """Query Neo4j for plaintext phone identifiers."""
    query = """
    MATCH (i:Identifier {type: 'SIGNAL_PHONE'})
    WHERE NOT i.value =~ '^[a-f0-9]{64}$'
    RETURN i.value AS phone, i.formatHint AS format, id(i) AS node_id
    ORDER BY i.value
    """
    result = store.driver.execute_query(query)
    return [record.data() for record in result.records]


def migrate_phone_to_hash(store: HumanStoreV2, node_id: int, plaintext: str) -> Dict[str, Any]:
    """Migrate a single phone identifier from plaintext to hash."""
    phone_hash = hash_phone(plaintext)
    format_hint = plaintext[:2] if plaintext.startswith('+') else '+1'

    query = """
    MATCH (i:Identifier)
    WHERE id(i) = $node_id
    SET i.value = $hash,
        i.formatHint = $format_hint
    RETURN i.value AS new_value, i.formatHint AS new_format
    """

    result = store.driver.execute_query(
        query,
        node_id=node_id,
        hash=phone_hash,
        format_hint=format_hint
    )

    return {
        "node_id": node_id,
        "plaintext": plaintext,
        "hash": phone_hash,
        "format_hint": format_hint,
    }


def main():
    parser = argparse.ArgumentParser(description="Migrate plaintext phone numbers to HMAC-SHA256 hashes")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be changed without applying")
    parser.add_argument("--apply", action="store_true", help="Apply the migration")
    parser.add_argument("--verify", action="store_true", help="Verify no plaintext phones remain")

    args = parser.parse_args()

    # Load environment variables
    load_dotenv()

    if not os.getenv("PHONE_HASH_SALT"):
        print("ERROR: PHONE_HASH_SALT environment variable must be set", file=sys.stderr)
        sys.exit(1)

    # Connect to Neo4j
    store = HumanStoreV2()

    if args.verify:
        print("🔍 Verifying no plaintext phone identifiers remain...")
        plaintext_phones = find_plaintext_phones(store)

        if plaintext_phones:
            print(f"❌ Found {len(plaintext_phones)} plaintext phone identifiers:")
            for phone in plaintext_phones:
                print(f"  - {phone['phone']} (node_id: {phone['node_id']})")
            sys.exit(1)
        else:
            print("✅ No plaintext phone identifiers found. Migration successful!")
            sys.exit(0)

    # Find plaintext phones
    print("🔍 Searching for plaintext phone identifiers...")
    plaintext_phones = find_plaintext_phones(store)

    if not plaintext_phones:
        print("✅ No plaintext phone identifiers found. No migration needed.")
        return

    print(f"📊 Found {len(plaintext_phones)} plaintext phone identifiers:")
    for phone in plaintext_phones:
        print(f"  - {phone['phone']} (node_id: {phone['node_id']})")

    if args.dry_run:
        print("\n🔮 DRY RUN - Showing what would be changed:")
        for phone in plaintext_phones:
            phone_hash = hash_phone(phone['phone'])
            format_hint = phone['phone'][:2] if phone['phone'].startswith('+') else '+1'
            print(f"  Node {phone['node_id']}: {phone['phone']} → {phone_hash} (format: {format_hint})")
        print("\n⚠️  No changes applied. Use --apply to execute migration.")
        return

    if args.apply:
        print("\n🔄 Applying migration...")
        migrated = []

        for phone in plaintext_phones:
            result = migrate_phone_to_hash(
                store,
                phone['node_id'],
                phone['phone']
            )
            migrated.append(result)
            print(f"  ✓ Node {result['node_id']}: {result['plaintext']} → {result['hash'][:16]}... (format: {result['format_hint']})")

        print(f"\n✅ Migration complete! {len(migrated)} phone identifiers migrated to hashes.")
        print("\n🔍 Verifying no plaintext remains...")

        remaining = find_plaintext_phones(store)
        if remaining:
            print(f"⚠️  Warning: {len(remaining)} plaintext identifiers remain:")
            for phone in remaining:
                print(f"  - {phone['phone']} (node_id: {phone['node_id']})")
        else:
            print("✅ Verification successful! No plaintext phone identifiers remain.")

        store.close()
        return

    # No action specified
    print("\n⚠️  No action specified. Use --dry-run, --apply, or --verify")
    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()
