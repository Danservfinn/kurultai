#!/usr/bin/env python3
"""Remove legacy file extensions from task tracking.

Legacy extensions (DEPRECATED as of 2026-03-10):
- .done, .done.md
- .failed, .failed.md
- .retry.md
- .executing

State is now tracked in Neo4j, not via file extensions.
See /agents/main/specs/TASK_ID_FORMAT.md for specification.

Usage:
    # Dry run (default) - shows what would be changed
    python3 cleanup_task_extensions.py

    # Execute changes
    python3 cleanup_task_extensions.py --execute

    # Also remove files for tasks that are COMPLETED/FAILED in Neo4j
    python3 cleanup_task_extensions.py --execute --remove-completed
"""

import argparse
import re
import sys
from pathlib import Path

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from kurultai_paths import AGENTS_DIR

# Legacy extension patterns to clean up
LEGACY_PATTERNS = [
    "*.done",
    "*.done.md",
    "*.failed",
    "*.failed.md",
    "*.retry.md",
    "*.executing",
    "*.executing.md",
    "*.completed.done.md",
    "*.resolved.md",
]

# Canonical task ID pattern
TASK_ID_PATTERN = re.compile(r'^(critical|high|normal|low)-\d{10}-[a-f0-9]{8}$')


def get_neo4j_status(task_id: str) -> str | None:
    """Get task status from Neo4j.

    Returns status string or None if not found.
    """
    try:
        from neo4j_task_tracker import get_driver
        driver = get_driver()
        if not driver:
            return None

        with driver.session() as session:
            result = session.run("""
                MATCH (t:Task {task_id: $task_id})
                RETURN t.status as status
            """, task_id=task_id)
            record = result.single()
            return record["status"] if record else None
    except Exception as e:
        print(f"  [ERROR] Neo4j query failed for {task_id}: {e}")
        return None


def extract_task_id(filepath: Path) -> str | None:
    """Extract task_id from filename.

    Handles both canonical format and legacy formats.
    """
    name = filepath.name

    # Remove known suffixes
    for suffix in ['.done.md', '.failed.md', '.retry.md', '.executing.md',
                   '.completed.done.md', '.resolved.md',
                   '.done', '.failed', '.executing', '.md']:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
            break

    # Check if it's canonical format
    if TASK_ID_PATTERN.match(name):
        return name

    # Legacy formats: fs-TIMESTAMP, task-TIMESTAMP, UUID-prefix, priority-TIMESTAMP
    # Accept any reasonable task_id
    if re.match(r'^(fs|task)-\d+', name):
        return name
    if re.match(r'^(critical|high|normal|low)-\d+', name):
        return name
    if re.match(r'^[a-f0-9]{8,12}$', name, re.IGNORECASE):
        return name

    return None


def cleanup_extensions(execute: bool = False, remove_completed: bool = False) -> dict:
    """Find and optionally clean up legacy extension files.

    Args:
        execute: If True, actually perform the changes. If False, dry run.
        remove_completed: If True, remove files for COMPLETED/FAILED tasks.

    Returns:
        Dict with counts of files found/processed.
    """
    results = {
        "found": 0,
        "renamed": 0,
        "removed": 0,
        "skipped": 0,
        "errors": 0,
    }

    agents_dir = Path(AGENTS_DIR)

    for pattern in LEGACY_PATTERNS:
        for filepath in agents_dir.glob(f"*/tasks/{pattern}"):
            results["found"] += 1
            task_id = extract_task_id(filepath)

            if not task_id:
                print(f"[SKIP] Cannot extract task_id from: {filepath}")
                results["skipped"] += 1
                continue

            # Get Neo4j status
            status = get_neo4j_status(task_id)

            if remove_completed and status in ("COMPLETED", "FAILED", "CANCELLED"):
                # Remove files for completed/failed tasks
                print(f"[REMOVE] {filepath.name} (Neo4j status: {status})")
                if execute:
                    try:
                        filepath.unlink()
                        results["removed"] += 1
                    except Exception as e:
                        print(f"  [ERROR] Failed to remove: {e}")
                        results["errors"] += 1
                else:
                    results["removed"] += 1  # Would remove
                continue

            # Determine base filename (without legacy extension)
            base_name = f"{task_id}.md"
            base_path = filepath.parent / base_name

            if base_path.exists():
                # Base file exists, just remove the extension file
                print(f"[REMOVE] {filepath.name} (base file exists)")
                if execute:
                    try:
                        filepath.unlink()
                        results["removed"] += 1
                    except Exception as e:
                        print(f"  [ERROR] Failed to remove: {e}")
                        results["errors"] += 1
                else:
                    results["removed"] += 1
            else:
                # Base file doesn't exist, rename to base
                print(f"[RENAME] {filepath.name} -> {base_name}")
                if execute:
                    try:
                        filepath.rename(base_path)
                        results["renamed"] += 1
                    except Exception as e:
                        print(f"  [ERROR] Failed to rename: {e}")
                        results["errors"] += 1
                else:
                    results["renamed"] += 1

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Clean up legacy task file extensions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Dry run - see what would be changed
    python3 cleanup_task_extensions.py

    # Execute the cleanup
    python3 cleanup_task_extensions.py --execute

    # Also remove files for completed/failed tasks
    python3 cleanup_task_extensions.py --execute --remove-completed
"""
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually perform the changes (default: dry run)"
    )
    parser.add_argument(
        "--remove-completed",
        action="store_true",
        help="Remove files for tasks that are COMPLETED/FAILED in Neo4j"
    )
    args = parser.parse_args()

    if not args.execute:
        print("=" * 60)
        print("DRY RUN - No changes will be made")
        print("Use --execute to apply changes")
        print("=" * 60)
        print()

    results = cleanup_extensions(execute=args.execute, remove_completed=args.remove_completed)

    print()
    print("=" * 60)
    print("Summary:")
    print(f"  Files found with legacy extensions: {results['found']}")
    print(f"  Files to rename: {results['renamed']}")
    print(f"  Files to remove: {results['removed']}")
    print(f"  Files skipped: {results['skipped']}")
    print(f"  Errors: {results['errors']}")
    print("=" * 60)

    if not args.execute and results["found"] > 0:
        print("\nRun with --execute to apply these changes.")

    return 0 if results["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
