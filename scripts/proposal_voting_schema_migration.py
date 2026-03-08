#!/usr/bin/env python3
"""
proposal_voting_schema_migration.py - Neo4j schema setup for proposal voting system.

Run this once to set up the Proposal and Vote node schema with constraints and indexes.

Usage:
    python proposal_voting_schema_migration.py --dry-run    # Show what will be created
    python proposal_voting_schema_migration.py --apply      # Apply schema changes
"""

import sys
import os
from neo4j import GraphDatabase

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import get_driver


# Cypher statements for schema setup
SCHEMA_STATEMENTS = [
    # ============================================================
    # PROPOSAL NODE SETUP
    # ============================================================
    {
        "name": "proposal_id_unique",
        "statement": """
            CREATE CONSTRAINT proposal_id_unique IF NOT EXISTS
            FOR (p:Proposal) REQUIRE p.proposal_id IS UNIQUE
        """,
        "description": "Unique constraint on Proposal.proposal_id"
    },
    {
        "name": "proposal_status_idx",
        "statement": """
            CREATE INDEX proposal_status_idx IF NOT EXISTS
            FOR (p:Proposal) ON (p.status)
        """,
        "description": "Index on Proposal.status for filtering"
    },
    {
        "name": "proposal_expires_at_idx",
        "statement": """
            CREATE INDEX proposal_expires_at_idx IF NOT EXISTS
            FOR (p:Proposal) ON (p.expires_at)
        """,
        "description": "Index on Proposal.expires_at for expiration queries"
    },
    {
        "name": "proposal_category_idx",
        "statement": """
            CREATE INDEX proposal_category_idx IF NOT EXISTS
            FOR (p:Proposal) ON (p.category)
        """,
        "description": "Index on Proposal.category for filtering"
    },

    # ============================================================
    # VOTE NODE SETUP
    # ============================================================
    {
        "name": "vote_id_unique",
        "statement": """
            CREATE CONSTRAINT vote_id_unique IF NOT EXISTS
            FOR (v:Vote) REQUIRE v.vote_id IS UNIQUE
        """,
        "description": "Unique constraint on Vote.vote_id"
    },
    {
        "name": "vote_proposal_idx",
        "statement": """
            CREATE INDEX vote_proposal_idx IF NOT EXISTS
            FOR (v:Vote) ON (v.proposal_id)
        """,
        "description": "Index on Vote.proposal_id for vote aggregation"
    },
    {
        "name": "vote_agent_idx",
        "statement": """
            CREATE INDEX vote_agent_idx IF NOT EXISTS
            FOR (v:Vote) ON (v.agent)
        """,
        "description": "Index on Vote.agent for agent vote queries"
    },

    # ============================================================
    # ENSURE AGENT NODES EXIST FOR ALL KURULTAI AGENTS
    # ============================================================
    {
        "name": "ensure_kurultai_agents",
        "statement": """
            UNWIND ['kublai', 'temujin', 'mongke', 'chagatai', 'jochi', 'ogedei'] AS name
            MERGE (:Agent {name: name})
        """,
        "description": "Ensure all Kurultai agents exist as Agent nodes"
    },
]


def run_migration(apply: bool = False) -> dict:
    """Run schema migration."""
    driver = get_driver()
    results = {
        "applied": 0,
        "skipped": 0,
        "errors": 0,
        "details": []
    }

    with driver.session() as session:
        for schema_obj in SCHEMA_STATEMENTS:
            name = schema_obj["name"]
            statement = schema_obj["statement"].strip()
            description = schema_obj["description"]

            if apply:
                try:
                    session.run(statement)
                    results["applied"] += 1
                    results["details"].append({
                        "name": name,
                        "status": "applied",
                        "description": description
                    })
                    print(f"[APPLY] {name}: {description}")
                except Exception as e:
                    results["errors"] += 1
                    results["details"].append({
                        "name": name,
                        "status": "error",
                        "description": description,
                        "error": str(e)
                    })
                    print(f"[ERROR] {name}: {e}")
            else:
                results["skipped"] += 1
                results["details"].append({
                    "name": name,
                    "status": "pending",
                    "description": description
                })
                print(f"[DRY RUN] {name}: {description}")

    driver.close()
    return results


def verify_schema() -> dict:
    """Verify that schema is correctly installed."""
    driver = get_driver()
    verification = {
        "constraints": [],
        "indexes": [],
        "agents": []
    }

    with driver.session() as session:
        # Check constraints
        result = session.run("""
            SHOW CONSTRAINTS YIELD name, labelsOrTypes, properties
            WHERE any(label IN labelsOrTypes WHERE label IN ['Proposal', 'Vote'])
            RETURN name, labelsOrTypes, properties
        """)
        for r in result:
            verification["constraints"].append({
                "name": r["name"],
                "label": r["labelsOrTypes"][0] if r["labelsOrTypes"] else None,
                "properties": r["properties"]
            })

        # Check indexes
        result = session.run("""
            SHOW INDEXES YIELD name, labelsOrTypes, properties
            WHERE any(label IN labelsOrTypes WHERE label IN ['Proposal', 'Vote'])
            RETURN name, labelsOrTypes, properties
        """)
        for r in result:
            verification["indexes"].append({
                "name": r["name"],
                "label": r["labelsOrTypes"][0] if r["labelsOrTypes"] else None,
                "properties": r["properties"]
            })

        # Check agents
        result = session.run("""
            MATCH (a:Agent)
            WHERE a.name IN ['kublai', 'temujin', 'mongke', 'chagatai', 'jochi', 'ogedei']
            RETURN a.name AS name, a.status AS status
            ORDER BY a.name
        """)
        for r in result:
            verification["agents"].append({
                "name": r["name"],
                "status": r["status"]
            })

    driver.close()
    return verification


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Setup proposal voting schema")
    parser.add_argument("--dry-run", action="store_true", help="Show what will be created")
    parser.add_argument("--apply", action="store_true", help="Apply schema changes")
    parser.add_argument("--verify", action="store_true", help="Verify existing schema")
    args = parser.parse_args()

    if args.verify:
        print("=== VERIFICATION ===")
        verification = verify_schema()

        print("\nConstraints:")
        for c in verification["constraints"]:
            print(f"  {c['name']}: {c['label']}.{c['properties']}")

        print("\nIndexes:")
        for i in verification["indexes"]:
            print(f"  {i['name']}: {i['label']}.{i['properties']}")

        print("\nAgents:")
        for a in verification["agents"]:
            print(f"  {a['name']}: {a['status']}")

        return 0

    results = run_migration(apply=args.apply)

    print(f"\n{'='*60}")
    print(f"Migration Summary {'(APPLIED)' if args.apply else '(DRY RUN)'}")
    print(f"{'='*60}")
    print(f"  Applied:  {results['applied']}")
    print(f"  Skipped:  {results['skipped']}")
    print(f"  Errors:   {results['errors']}")

    if not args.apply and results["skipped"] > 0:
        print(f"\nRun with --apply to create {results['skipped']} schema elements")

    if args.apply:
        print("\nVerifying...")
        verification = verify_schema()
        expected_constraints = 2  # proposal_id_unique, vote_id_unique
        expected_indexes = 5  # status, expires_at, category, proposal_id, agent
        expected_agents = 6

        actual_constraints = len(verification["constraints"])
        actual_indexes = len(verification["indexes"])
        actual_agents = len(verification["agents"])

        if (actual_constraints >= expected_constraints and
            actual_indexes >= expected_indexes and
            actual_agents == expected_agents):
            print("✅ Schema verification PASSED")
            return 0
        else:
            print("⚠️  Schema verification incomplete")
            print(f"   Constraints: {actual_constraints}/{expected_constraints}")
            print(f"   Indexes: {actual_indexes}/{expected_indexes}")
            print(f"   Agents: {actual_agents}/{expected_agents}")
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
