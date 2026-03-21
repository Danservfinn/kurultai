#!/usr/bin/env python3
"""
Group Schema Migration — Adds Group/GroupThread nodes and scope properties.

Idempotent — safe to run multiple times. Follows neo4j_v2_schema.py patterns.

Usage:
    python3 group_schema_migration.py           # Apply migration
    python3 group_schema_migration.py --verify  # Verify only
"""

import sys
import os
import argparse
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import get_driver, close_driver

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Group constraints
# ---------------------------------------------------------------------------
GROUP_CONSTRAINTS = [
    {
        "name": "group_id_unique",
        "cypher": "CREATE CONSTRAINT group_id_unique IF NOT EXISTS FOR (g:Group) REQUIRE g.groupId IS UNIQUE",
        "desc": "Unique Group identifier",
    },
    {
        "name": "group_thread_id_unique",
        "cypher": "CREATE CONSTRAINT group_thread_id_unique IF NOT EXISTS FOR (gt:GroupThread) REQUIRE gt.id IS UNIQUE",
        "desc": "Unique GroupThread UUID",
    },
]

# ---------------------------------------------------------------------------
# Group indexes
# ---------------------------------------------------------------------------
GROUP_INDEXES = [
    {
        "name": "v2_group_status",
        "cypher": "CREATE INDEX v2_group_status IF NOT EXISTS FOR (g:Group) ON (g.status)",
        "desc": "Group status filter",
    },
    {
        "name": "v2_group_thread_group_human",
        "cypher": "CREATE INDEX v2_group_thread_group_human IF NOT EXISTS FOR (gt:GroupThread) ON (gt.groupId, gt.humanId, gt.status)",
        "desc": "GroupThread lookup by group + human + status",
    },
    {
        "name": "v2_message_scope",
        "cypher": "CREATE INDEX v2_message_scope IF NOT EXISTS FOR (m:Message) ON (m.scope)",
        "desc": "Message scope filter — kept because Neo4j 5.x composite indexes may not serve prefix-only queries",
    },
    {
        "name": "v2_message_scope_human",
        "cypher": "CREATE INDEX v2_message_scope_human IF NOT EXISTS FOR (m:Message) ON (m.scope, m.humanId, m.timestamp)",
        "desc": "Scoped message retrieval by human + time",
    },
    {
        "name": "v2_thread_scope_human",
        "cypher": "CREATE INDEX v2_thread_scope_human IF NOT EXISTS FOR (t:Thread) ON (t.scope, t.humanId, t.status)",
        "desc": "Scoped thread lookup by human + status",
    },
]


def apply_group_schema(driver, verbose=True):
    """Apply group-related constraints and indexes. Idempotent."""
    results = {"constraints": [], "indexes": [], "errors": []}

    with driver.session() as session:
        for item in GROUP_CONSTRAINTS:
            try:
                session.run(item["cypher"])
                results["constraints"].append(item["name"])
                if verbose:
                    print(f"  [OK] constraint {item['name']}: {item['desc']}")
            except Exception as e:
                if "already exists" in str(e).lower() or "equivalent" in str(e).lower():
                    results["constraints"].append(item["name"])
                    if verbose:
                        print(f"  [EXISTS] constraint {item['name']}")
                else:
                    results["errors"].append(f"{item['name']}: {e}")
                    if verbose:
                        print(f"  [ERROR] constraint {item['name']}: {e}")

        for item in GROUP_INDEXES:
            try:
                session.run(item["cypher"])
                results["indexes"].append(item["name"])
                if verbose:
                    print(f"  [OK] index {item['name']}: {item['desc']}")
            except Exception as e:
                if "already exists" in str(e).lower() or "equivalent" in str(e).lower():
                    results["indexes"].append(item["name"])
                    if verbose:
                        print(f"  [EXISTS] index {item['name']}")
                else:
                    results["errors"].append(f"{item['name']}: {e}")
                    if verbose:
                        print(f"  [ERROR] index {item['name']}: {e}")

    return results


def migrate_existing_data(driver, verbose=True):
    """Tag all existing Messages and Threads with scope='dm' where scope is NULL.

    Idempotent — only touches nodes without a scope property.
    """
    with driver.session() as session:
        # Tag Messages
        result = session.run(
            "MATCH (m:Message) WHERE m.scope IS NULL SET m.scope = 'dm' RETURN count(m) AS tagged"
        )
        msg_count = result.single()["tagged"]
        if verbose:
            print(f"  [MIGRATE] Tagged {msg_count} Messages with scope='dm'")

        # Tag Threads
        result = session.run(
            "MATCH (t:Thread) WHERE t.scope IS NULL SET t.scope = 'dm' RETURN count(t) AS tagged"
        )
        thread_count = result.single()["tagged"]
        if verbose:
            print(f"  [MIGRATE] Tagged {thread_count} Threads with scope='dm'")

    return {"messages_tagged": msg_count, "threads_tagged": thread_count}


def verify_group_schema(driver, verbose=True):
    """Verify group schema elements exist and data is migrated."""
    missing = []

    with driver.session() as session:
        existing = set()
        for label in ("CONSTRAINTS", "INDEXES"):
            try:
                for rec in session.run(f"SHOW {label}"):
                    name = rec.get("name") or rec.get("constraintName") or rec.get("indexName")
                    if name:
                        existing.add(name)
            except Exception:
                pass

        for item in GROUP_CONSTRAINTS + GROUP_INDEXES:
            if item["name"] in existing:
                if verbose:
                    print(f"  [OK] {item['name']}")
            else:
                missing.append(item["name"])
                if verbose:
                    print(f"  [MISSING] {item['name']}")

        # Check migration completeness
        result = session.run(
            "MATCH (m:Message) WHERE m.scope IS NULL RETURN count(m) AS n"
        )
        untagged = result.single()["n"]
        if untagged > 0:
            missing.append(f"untagged_messages:{untagged}")
            if verbose:
                print(f"  [MIGRATE] {untagged} Messages still without scope")
        elif verbose:
            print(f"  [OK] All Messages have scope property")

        result = session.run(
            "MATCH (t:Thread) WHERE t.scope IS NULL RETURN count(t) AS n"
        )
        untagged_t = result.single()["n"]
        if untagged_t > 0:
            missing.append(f"untagged_threads:{untagged_t}")
            if verbose:
                print(f"  [MIGRATE] {untagged_t} Threads still without scope")
        elif verbose:
            print(f"  [OK] All Threads have scope property")

    return len(missing) == 0


def main():
    parser = argparse.ArgumentParser(description="Group chat schema migration")
    parser.add_argument("--verify", action="store_true", help="Verify only")
    parser.add_argument("-q", "--quiet", action="store_true")
    args = parser.parse_args()

    verbose = not args.quiet
    if verbose:
        print("=== Group Chat Schema Migration ===\n")

    driver = get_driver()
    try:
        if args.verify:
            ok = verify_group_schema(driver, verbose)
            sys.exit(0 if ok else 1)
        else:
            if verbose:
                print("--- Schema ---")
            results = apply_group_schema(driver, verbose)

            if verbose:
                print("\n--- Data Migration ---")
            migrate_existing_data(driver, verbose)

            if verbose:
                c = len(results["constraints"])
                i = len(results["indexes"])
                e = len(results["errors"])
                print(f"\n  {c} constraints, {i} indexes applied. {e} errors.")

            if results["errors"]:
                sys.exit(1)
    finally:
        close_driver()


if __name__ == "__main__":
    main()
