#!/usr/bin/env python3
"""
Emergency wrapper to process approved proposals into Neo4j Task nodes.

This script calls phase4_create_tasks_for_approved() which is missing
from the kurultai_voting.py CLI but exists in the code.

Usage:
    python3 process_approved_to_tasks.py
"""

import sys
from pathlib import Path

# Ensure we're in the scripts directory
SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPTS_DIR))

# Import the voting module
from kurultai_voting import phase4_create_tasks_for_approved, log_phase

def main():
    print("=" * 60)
    print("PROCESSING APPROVED PROPOSALS → NEO4J TASKS")
    print("=" * 60)
    print()

    try:
        tasks_created = phase4_create_tasks_for_approved()

        print()
        print("=" * 60)
        print(f"COMPLETE: {len(tasks_created)} tasks created")
        print("=" * 60)
        print()
        print("Task IDs:")
        for task_id in tasks_created:
            print(f"  - {task_id}")

        return 0

    except Exception as e:
        print()
        print("=" * 60)
        print(f"ERROR: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
