#!/usr/bin/env python3
"""
hermes-proposal-submit.py - Create a proposal in Neo4j for Hermes.

Accepts a JSON spec (from stdin or --spec file) and creates a Proposal node
with PROPOSED_FOR relationships to affected agents.

Usage:
    echo '{"title":"...","description":"..."}' | python3 hermes-proposal-submit.py --tier T2
    python3 hermes-proposal-submit.py --spec proposal.json --tier T1 --title "My Proposal"
    python3 hermes-proposal-submit.py --spec proposal.json --agents kublai,temujin
"""

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from kurultai_logging import setup_logging, get_logger

KURULTAI_AGENTS = ["kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei"]

logger = get_logger("hermes-proposal-submit", agent="hermes")


def load_spec(args) -> dict:
    """Load the proposal spec from file or stdin."""
    if args.spec:
        spec = json.loads(Path(args.spec).read_text())
    else:
        if sys.stdin.isatty():
            print("Error: provide --spec file or pipe JSON to stdin", file=sys.stderr)
            sys.exit(1)
        spec = json.loads(sys.stdin.read())

    # CLI flags override spec fields
    if args.title:
        spec["title"] = args.title
    if args.tier:
        spec["tier"] = args.tier
    if args.agents:
        spec["affected_agents"] = [a.strip() for a in args.agents.split(",")]

    return spec


def validate_spec(spec: dict) -> list[str]:
    """Return list of validation errors (empty = valid)."""
    errors = []
    if not spec.get("title"):
        errors.append("Missing required field: title")
    if spec.get("tier") not in ("T1", "T2", "T3"):
        errors.append("tier must be T1, T2, or T3")
    for agent in spec.get("affected_agents", []):
        if agent not in KURULTAI_AGENTS:
            errors.append(f"Unknown agent: {agent}")
    return errors


def submit_proposal(spec: dict) -> str:
    """Create the proposal in Neo4j."""
    from neo4j_task_tracker import get_driver, close_driver

    proposal_id = f"hermes-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)
    affected = spec.get("affected_agents", KURULTAI_AGENTS)

    driver = get_driver()
    try:
        with driver.session() as session:
            # Create the Proposal node
            session.run("""
                CREATE (p:Proposal {
                    proposal_id: $proposal_id,
                    tier: $tier,
                    title: $title,
                    description: $description,
                    rationale: $rationale,
                    created_at: datetime(),
                    status: 'OPEN',
                    proposing_agent: 'hermes'
                })
                RETURN p.proposal_id AS id
            """,
                proposal_id=proposal_id,
                tier=spec.get("tier", "T2"),
                title=spec["title"],
                description=spec.get("description", ""),
                rationale=spec.get("rationale", ""),
            )

            # Link to affected agents via PROPOSED_FOR
            for agent_name in affected:
                session.run("""
                    MATCH (p:Proposal {proposal_id: $proposal_id})
                    MERGE (a:Agent {name: $agent_name})
                    MERGE (p)-[:PROPOSED_FOR {at: datetime()}]->(a)
                """, proposal_id=proposal_id, agent_name=agent_name)

            logger.info("Created proposal %s (tier=%s, agents=%s)",
                        proposal_id, spec.get("tier"), affected)
    finally:
        close_driver()

    return proposal_id


def main():
    parser = argparse.ArgumentParser(description="Submit a Hermes proposal to Neo4j")
    parser.add_argument("--spec", type=str, default=None,
                        help="Path to JSON spec file")
    parser.add_argument("--tier", type=str, choices=["T1", "T2", "T3"],
                        help="Proposal tier (T1/T2/T3)")
    parser.add_argument("--title", type=str, default=None,
                        help="Proposal title (overrides spec)")
    parser.add_argument("--agents", type=str, default=None,
                        help="Comma-separated affected agents (overrides spec)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate spec without submitting")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    setup_logging(level=args.log_level, agent_name="hermes-proposal-submit")

    spec = load_spec(args)

    errors = validate_spec(spec)
    if errors:
        print(json.dumps({"status": "validation_error", "errors": errors}), file=sys.stderr)
        return 1

    if args.dry_run:
        print(json.dumps({"status": "valid", "spec": spec}, indent=2))
        return 0

    proposal_id = submit_proposal(spec)
    result = {
        "status": "created",
        "proposal_id": proposal_id,
        "tier": spec.get("tier", "T2"),
        "title": spec["title"],
        "affected_agents": spec.get("affected_agents", KURULTAI_AGENTS),
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
