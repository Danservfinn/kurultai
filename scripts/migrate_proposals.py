#!/usr/bin/env python3
"""
Migrate proposals from root to pending directory.
Run once to fix existing proposals.

Usage:
    python3 migrate_proposals.py [--dry-run]
"""
import argparse
import shutil
from pathlib import Path

PROPOSALS_DIR = Path("/Users/kublai/.openclaw/agents/main/proposals")
PENDING_DIR = PROPOSALS_DIR / "pending"


def migrate_proposals(dry_run: bool = False) -> int:
    """Move root-level proposals to pending/. Returns count of migrated proposals."""
    PENDING_DIR.mkdir(parents=True, exist_ok=True)

    migrated = 0
    skipped = 0

    for f in PROPOSALS_DIR.glob("*.md"):
        # Skip if already in subdirectory
        if f.parent != PROPOSALS_DIR:
            continue
        # Move to pending
        dest = PENDING_DIR / f.name
        if dest.exists():
            print(f"Skipped (exists): {f.name}")
            skipped += 1
        else:
            if dry_run:
                print(f"Would migrate: {f.name} -> pending/")
            else:
                shutil.move(str(f), str(dest))
                print(f"Migrated: {f.name} -> pending/")
            migrated += 1

    print(f"\nSummary: {migrated} migrated, {skipped} skipped")
    return migrated


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate proposals to pending directory")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    args = parser.parse_args()

    migrate_proposals(dry_run=args.dry_run)
