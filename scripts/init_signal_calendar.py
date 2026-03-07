#!/usr/bin/env python3
"""
Signal Calendar System - Phase 1 Initialization

Initialize Neo4j schema and seed data for the Signal Calendar System.
Run this once to set up the database.

Usage:
    python3 init_signal_calendar.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'calendar'))

from neo4j_calendar import get_calendar_db

# Seed data - group members
SEED_PERSONS = [
    {
        "phone": "+19194133445",
        "name": "Danny",
        "aliases": [],
        "role": "admin"
    },
    {
        "phone": "+16624580725",
        "name": "Liz",
        "aliases": [],
        "role": "member"
    },
]


def init_calendar():
    """Initialize the Signal Calendar System."""
    print("=" * 60)
    print("Signal Calendar System - Phase 1 Initialization")
    print("=" * 60)

    db = get_calendar_db()

    try:
        # Step 1: Initialize schema
        print("\n[1/3] Creating schema constraints and indexes...")
        db.init_schema()
        print("      ✓ Schema created successfully")

        # Step 2: Seed persons
        print("\n[2/3] Seeding group members...")
        db.seed_persons(SEED_PERSONS)
        for person in SEED_PERSONS:
            print(f"      ✓ {person['name']} ({person['phone']}) - {person['role']}")

        # Step 3: Verify
        print("\n[3/3] Verifying setup...")
        danny = db.get_person_by_phone("+19194133445")
        liz = db.get_person_by_phone("+16624580725")

        if danny and liz:
            print(f"      ✓ Danny found: {danny.name}")
            print(f"      ✓ Liz found: {liz.name}")
            print("\n" + "=" * 60)
            print("Initialization complete!")
            print("=" * 60)
            print("\nNext steps:")
            print("  1. Start the Signal listener:")
            print("     python3 signal_calendar_listener.py")
            print("  2. Or run a single poll:")
            print("     python3 signal_calendar_listener.py --once")
            print("\nTest commands:")
            print("  - 'add event Dinner at Marios Friday 7pm'")
            print('  - "list events this weekend"')
            print('  - "who is coming to dinner"')
            print("  - 'Im in for dinner'")
            return True
        else:
            print("      ✗ Verification failed - persons not found")
            return False

    except Exception as e:
        print(f"\n✗ Error during initialization: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        db.close()


if __name__ == "__main__":
    success = init_calendar()
    sys.exit(0 if success else 1)
