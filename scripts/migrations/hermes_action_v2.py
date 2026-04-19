#!/usr/bin/env python3
"""Migration: HermesAction v2 schema + HermesCommit node type.

Idempotent. Safe to re-run.

Adds to existing HermesAction nodes:
  - schema_version = 1 (marks as pre-migration baseline)

Creates indexes:
  - hermes_action_fix_id on HermesAction(fix_id)
  - hermes_action_commit_sha on HermesAction(commit_sha)
  - hermes_commit_sha on HermesCommit(sha)
  - hermes_commit_sweep on HermesCommit(sweep)

Usage:
    python3 migrations/hermes_action_v2.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def migrate() -> dict:
    """Run the migration. Returns a dict of outcomes."""
    from neo4j_v2_core import TaskStore  # type: ignore

    results: dict = {"steps": []}
    store = TaskStore()
    try:
        with store.driver.session() as session:
            # Step 1: mark existing HermesAction nodes with schema_version=1
            res = session.run("""
                MATCH (a:HermesAction)
                WHERE a.schema_version IS NULL
                SET a.schema_version = 1
                RETURN count(a) AS n
            """)
            migrated = next(iter(res), None)
            n = migrated["n"] if migrated else 0
            results["steps"].append(
                {"step": "mark_schema_v1", "updated": n}
            )

            # Step 2: constraints + indexes. The UNIQUE constraint on
            # HermesCommit(sha) creates its own backing index, so no
            # separate sha index is needed.
            session.run(
                "CREATE CONSTRAINT hermes_commit_sha_unique IF NOT EXISTS "
                "FOR (c:HermesCommit) REQUIRE c.sha IS UNIQUE"
            )
            results["steps"].append({"step": "hermes_commit_sha_unique"})

            # Supplementary indexes for HermesAction lookups and
            # HermesCommit filters. All IF NOT EXISTS for idempotence.
            for stmt in [
                "CREATE INDEX hermes_action_fix_id IF NOT EXISTS "
                "FOR (a:HermesAction) ON (a.fix_id)",
                "CREATE INDEX hermes_action_commit_sha IF NOT EXISTS "
                "FOR (a:HermesAction) ON (a.commit_sha)",
                "CREATE INDEX hermes_commit_sweep IF NOT EXISTS "
                "FOR (c:HermesCommit) ON (c.sweep)",
                "CREATE INDEX hermes_commit_reverted IF NOT EXISTS "
                "FOR (c:HermesCommit) ON (c.reverted)",
                "CREATE INDEX hermes_commit_created_at IF NOT EXISTS "
                "FOR (c:HermesCommit) ON (c.created_at)",
            ]:
                session.run(stmt)
                results["steps"].append({"step": "index", "stmt": stmt[:60]})

        return results
    finally:
        store.close()


def main() -> int:
    import json
    try:
        out = migrate()
        print(json.dumps(out, indent=2))
        return 0
    except Exception as e:
        print(f"migration failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
