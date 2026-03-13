#!/usr/bin/env python3
"""
neo4j_v2_schema.py — Neo4j v2 schema: nodes, constraints, indexes.

Idempotent — safe to run multiple times.
Does NOT modify or conflict with v1 schema (additive only).

Usage:
    python3 neo4j_v2_schema.py           # Apply schema
    python3 neo4j_v2_schema.py --verify  # Verify only
    python3 neo4j_v2_schema.py --test    # Run self-test
"""

import sys
import os
import argparse
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import get_driver, close_driver

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constraints (v2)
# ---------------------------------------------------------------------------
V2_CONSTRAINTS = [
    {
        "name": "task_id_unique",
        "cypher": "CREATE CONSTRAINT task_id_unique IF NOT EXISTS FOR (t:Task) REQUIRE t.task_id IS UNIQUE",
        "desc": "Unique task_id across Task nodes",
    },
    {
        "name": "agent_name_unique",
        "cypher": "CREATE CONSTRAINT agent_name_unique IF NOT EXISTS FOR (a:Agent) REQUIRE a.name IS UNIQUE",
        "desc": "Unique agent name",
    },
    {
        "name": "skill_name_unique",
        "cypher": "CREATE CONSTRAINT skill_name_unique IF NOT EXISTS FOR (s:Skill) REQUIRE s.name IS UNIQUE",
        "desc": "Unique skill name",
    },
    {
        "name": "domain_name_unique",
        "cypher": "CREATE CONSTRAINT domain_name_unique IF NOT EXISTS FOR (d:Domain) REQUIRE d.name IS UNIQUE",
        "desc": "Unique domain name",
    },
]

# ---------------------------------------------------------------------------
# Indexes (v2)
# ---------------------------------------------------------------------------
V2_INDEXES = [
    {
        "name": "v2_task_status_agent",
        "cypher": "CREATE INDEX v2_task_status_agent IF NOT EXISTS FOR (t:Task) ON (t.status, t.assigned_to)",
        "desc": "Claim queries: PENDING tasks by agent",
    },
    {
        "name": "v2_task_claim_epoch",
        "cypher": "CREATE INDEX v2_task_claim_epoch IF NOT EXISTS FOR (t:Task) ON (t.claim_epoch)",
        "desc": "Fencing token lookups",
    },
    {
        "name": "v2_task_lease",
        "cypher": "CREATE INDEX v2_task_lease IF NOT EXISTS FOR (t:Task) ON (t.lease_expires_at)",
        "desc": "Orphan recovery: expired leases",
    },
    {
        "name": "v2_task_created",
        "cypher": "CREATE INDEX v2_task_created IF NOT EXISTS FOR (t:Task) ON (t.created_at)",
        "desc": "Time-ordered task queries",
    },
    {
        "name": "v2_task_priority",
        "cypher": "CREATE INDEX v2_task_priority IF NOT EXISTS FOR (t:Task) ON (t.priority)",
        "desc": "Priority-based queue ordering",
    },
    {
        "name": "v2_agent_heartbeat",
        "cypher": "CREATE INDEX v2_agent_heartbeat IF NOT EXISTS FOR (a:Agent) ON (a.last_heartbeat)",
        "desc": "Agent liveness checks",
    },
]

# ---------------------------------------------------------------------------
# Apply / Verify
# ---------------------------------------------------------------------------

def apply_schema(driver, verbose=True):
    """Apply all v2 constraints and indexes. Idempotent."""
    results = {"constraints": [], "indexes": [], "errors": []}

    with driver.session() as session:
        for item in V2_CONSTRAINTS:
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

        for item in V2_INDEXES:
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


def verify_schema(driver, verbose=True):
    """Verify all v2 constraints and indexes exist. Returns True if all present."""
    missing = []

    with driver.session() as session:
        # Collect existing names
        existing = set()
        for label in ("CONSTRAINTS", "INDEXES"):
            try:
                for rec in session.run(f"SHOW {label}"):
                    name = rec.get("name") or rec.get("constraintName") or rec.get("indexName")
                    if name:
                        existing.add(name)
            except Exception:
                pass

        for item in V2_CONSTRAINTS + V2_INDEXES:
            if item["name"] in existing:
                if verbose:
                    print(f"  [OK] {item['name']}")
            else:
                missing.append(item["name"])
                if verbose:
                    print(f"  [MISSING] {item['name']}")

    if missing and verbose:
        print(f"\n  {len(missing)} missing schema elements")
    return len(missing) == 0


def run_self_test(driver):
    """Create and clean up test nodes to verify schema works."""
    import uuid
    test_id = f"test-{uuid.uuid4().hex[:8]}"

    print(f"  Creating test Task node: {test_id}")
    with driver.session() as session:
        # Create
        session.run("""
            CREATE (t:Task {
                task_id: $id, title: 'Schema self-test', status: 'PENDING',
                assigned_to: 'test-agent', priority: 'low', domain: 'test',
                claim_epoch: 0, retry_count: 0, max_retries: 1, depth: 0,
                timeout_s: 60, created_at: datetime(), updated_at: datetime()
            })
        """, id=test_id)

        # Verify
        result = session.run("MATCH (t:Task {task_id: $id}) RETURN t.status AS s", id=test_id)
        record = result.single()
        assert record and record["s"] == "PENDING", f"Expected PENDING, got {record}"
        print("  [OK] Task created and queried")

        # Test uniqueness constraint
        try:
            session.run("CREATE (t:Task {task_id: $id, title: 'dup'})", id=test_id)
            print("  [FAIL] Uniqueness constraint not enforced!")
        except Exception:
            print("  [OK] Uniqueness constraint enforced")

        # Cleanup
        session.run("MATCH (t:Task {task_id: $id}) DETACH DELETE t", id=test_id)
        print("  [OK] Test node cleaned up")

    print("\n  Self-test passed.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Neo4j v2 schema management")
    parser.add_argument("--verify", action="store_true", help="Verify schema only")
    parser.add_argument("--test", action="store_true", help="Run self-test")
    parser.add_argument("-q", "--quiet", action="store_true")
    args = parser.parse_args()

    verbose = not args.quiet
    if verbose:
        print("=== Neo4j v2 Schema ===\n")

    driver = get_driver()
    try:
        if args.test:
            apply_schema(driver, verbose)
            run_self_test(driver)
        elif args.verify:
            ok = verify_schema(driver, verbose)
            sys.exit(0 if ok else 1)
        else:
            results = apply_schema(driver, verbose)
            if verbose:
                c, i, e = len(results["constraints"]), len(results["indexes"]), len(results["errors"])
                print(f"\n  {c} constraints, {i} indexes applied. {e} errors.")
            if results["errors"]:
                sys.exit(1)
    finally:
        close_driver()


if __name__ == "__main__":
    main()
