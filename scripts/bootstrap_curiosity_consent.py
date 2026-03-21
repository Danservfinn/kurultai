#!/usr/bin/env python3
"""Bootstrap proactive_engagement consent for all active humans.

One-time script to grant proactive_engagement consent so the curiosity
engine can start asking questions.

Usage:
    python3 bootstrap_curiosity_consent.py             # Grant consent
    python3 bootstrap_curiosity_consent.py --dry-run   # Preview only
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import neo4j_session
from consent_decorator import grant_consent, seed_consent_categories


def bootstrap_consent(dry_run: bool = False):
    """Grant proactive_engagement consent to all active humans."""
    # Ensure ConsentCategory nodes exist
    seed_consent_categories()

    with neo4j_session() as session:
        result = session.run(
            "MATCH (h:Human {status: 'active'}) RETURN h.id AS id, h.displayName AS name"
        )
        humans = [(r["id"], r["name"]) for r in result]

    print(f"Found {len(humans)} active humans")

    granted = 0
    for hid, name in humans:
        label = name or hid[:8]
        if dry_run:
            print(f"  [DRY RUN] Would grant to: {label}")
            granted += 1
        else:
            success = grant_consent(hid, "proactive_engagement", source="bootstrap_auto_grant")
            status = "OK" if success else "FAIL"
            print(f"  [{status}] {label}")
            if success:
                granted += 1

    print(f"\n{'Would grant' if dry_run else 'Granted'} proactive_engagement to {granted}/{len(humans)} active humans.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bootstrap curiosity consent")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    args = parser.parse_args()
    bootstrap_consent(dry_run=args.dry_run)
