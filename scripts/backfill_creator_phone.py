#!/usr/bin/env python3
"""Backfill creator_phone on Event nodes from CREATED_BY relationships.

One-time migration for events created before creator_phone was added to the
Event node schema. Safe to run multiple times (idempotent).

Usage:
    python3 backfill_creator_phone.py             # Run backfill
    python3 backfill_creator_phone.py --dry-run   # Preview only
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import neo4j_session


def backfill_creator_phone(dry_run: bool = False):
    """Set creator_phone on Events from their CREATED_BY relationship."""
    with neo4j_session() as session:
        # Find events missing creator_phone
        result = session.run("""
            MATCH (e:Event)-[:CREATED_BY]->(p:Person)
            WHERE e.creator_phone IS NULL AND p.phone_number IS NOT NULL
            RETURN e.event_id AS eid, e.name AS name, p.phone_number AS phone
        """)
        events = [(r["eid"], r["name"], r["phone"]) for r in result]

    print(f"Found {len(events)} events missing creator_phone")

    if dry_run:
        for eid, name, phone in events[:10]:
            print(f"  [DRY RUN] {name} -> {phone}")
        if len(events) > 10:
            print(f"  ... and {len(events) - 10} more")
        return

    updated = 0
    with neo4j_session() as session:
        for eid, name, phone in events:
            session.run(
                "MATCH (e:Event {event_id: $eid}) SET e.creator_phone = $phone",
                eid=eid, phone=phone,
            )
            updated += 1

    print(f"Updated {updated} events with creator_phone")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill Event.creator_phone")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    backfill_creator_phone(dry_run=args.dry_run)
