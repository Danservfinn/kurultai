#!/usr/bin/env python3
"""
Deduplicate failure-patterns.jsonl

Keeps only the FIRST occurrence of each (task_id, agent, category) tuple.
Removes invalid task_ids like "unknown" and "$(uuidgen)".

Usage: python3 dedup_failure_patterns.py [--dry-run]
"""

import json
import hashlib
import sys
from datetime import datetime
from pathlib import Path

LOGS_DIR = Path("/Users/kublai/.openclaw/agents/main/logs")
FAILURE_PATTERNS = LOGS_DIR / "failure-patterns.jsonl"
INVALID_TASK_IDS = {"unknown", "$(uuidgen)", "", "null", "none"}

def is_valid_task_id(task_id: str) -> bool:
    """Valid task IDs should be non-empty and not obviously invalid."""
    if not task_id or task_id.lower() in INVALID_TASK_IDS:
        return False
    # Skip shell commands or placeholders
    if task_id.startswith("$") or task_id.startswith("<"):
        return False
    return True

def dedup_patterns(dry_run: bool = False) -> dict:
    """Deduplicate failure patterns, returning statistics."""

    seen = set()  # (task_id, agent, category) -> first line
    unique_lines = []
    duplicate_count = 0
    invalid_count = 0
    original_count = 0

    with open(FAILURE_PATTERNS, 'r') as f:
        for line in f:
            original_count += 1
            if not line.strip():
                continue

            try:
                data = json.loads(line)
                task_id = data.get('task_id', '')
                agent = data.get('agent', '')
                category = data.get('category', '')

                # Skip invalid task IDs
                if not is_valid_task_id(task_id):
                    invalid_count += 1
                    continue

                # Create signature for deduplication
                signature = (task_id, agent, category)

                if signature not in seen:
                    seen.add(signature)
                    unique_lines.append(line.strip())
                else:
                    duplicate_count += 1

            except json.JSONDecodeError:
                # Skip malformed lines
                invalid_count += 1
                continue

    # Create backup and write deduplicated file
    if not dry_run:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = LOGS_DIR / f"failure-patterns.jsonl.backup-{timestamp}"

        # Backup original
        with open(FAILURE_PATTERNS, 'r') as src:
            with open(backup_path, 'w') as dst:
                dst.write(src.read())
        print(f"Backed up to: {backup_path.name}")

        # Write deduplicated
        with open(FAILURE_PATTERNS, 'w') as f:
            for line in unique_lines:
                f.write(line + '\n')
        print(f"Wrote {len(unique_lines)} entries to {FAILURE_PATTERNS.name}")

    return {
        "original": original_count,
        "unique": len(unique_lines),
        "duplicates": duplicate_count,
        "invalid": invalid_count,
        "reduction_pct": (duplicate_count + invalid_count) / original_count * 100 if original_count > 0 else 0
    }

if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv

    print("=" * 50)
    print("Failure Pattern Deduplication")
    print("=" * 50)
    print(f"Mode: {'DRY RUN - no changes' if dry_run else 'LIVE - will modify file'}")
    print()

    stats = dedup_patterns(dry_run=dry_run)

    print()
    print("Results:")
    print(f"  Original entries:  {stats['original']}")
    print(f"  Unique entries:    {stats['unique']}")
    print(f"  Duplicates removed: {stats['duplicates']}")
    print(f"  Invalid removed:   {stats['invalid']}")
    print(f"  Total reduction:   {stats['reduction_pct']:.1f}%")
    print()

    if dry_run:
        print("Run without --dry-run to apply changes.")
