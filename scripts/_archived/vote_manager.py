#!/usr/bin/env python3
"""
vote_manager.py - Vote casting and aggregation for Kurultai proposals.

Usage:
    python vote_manager.py cast --proposal-id <uuid> --agent "temujin" --vote yes --reason "..."
    python vote_manager.py sync --agent "temujin"  # Sync votes from agent's votes/ directory
    python vote_manager.py summary --proposal-id <uuid>
"""

import os
import sys
import uuid
import re
import json
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import get_driver
from kurultai_paths import AGENTS_DIR, LOGS_DIR

KURULTAI_AGENTS = ["kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei"]
VOTING_LOG = LOGS_DIR / "voting.jsonl"


def _log_voting_event(event_type: str, data: dict):
    """Log voting events to voting.jsonl."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now().isoformat(),
        "event_type": event_type,
        **data
    }
    with open(VOTING_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


class VoteManager:
    def __init__(self):
        self.driver = get_driver()

    def close(self):
        self.driver.close()

    def cast_vote(self, proposal_id: str, agent: str, decision: str,
                  reasoning: str = "", reflection_cycle: str = None) -> str:
        """Cast a vote on a proposal (upserts existing vote)."""
        if reflection_cycle is None:
            reflection_cycle = datetime.now().strftime("%Y-%m-%d-%H%M")

        if decision not in ("yes", "no", "abstain"):
            raise ValueError(f"Invalid decision: {decision}")

        vote_id = str(uuid.uuid4())[:12]

        with self.driver.session() as session:
            # Delete existing vote from this agent for this proposal
            session.run("""
                MATCH (v:Vote {proposal_id: $proposal_id, agent: $agent})
                DETACH DELETE v
            """, proposal_id=proposal_id, agent=agent)

            # Create new vote
            session.run("""
                MATCH (p:Proposal {proposal_id: $proposal_id})
                MATCH (a:Agent {name: $agent})
                CREATE (a)-[:VOTED_ON {at: datetime()}]->(v:Vote {
                    vote_id: $vote_id,
                    proposal_id: $proposal_id,
                    agent: $agent,
                    decision: $decision,
                    reasoning: $reasoning,
                    voted_at: datetime(),
                    updated_at: datetime(),
                    reflection_cycle: $reflection_cycle
                })
                CREATE (v)-[:FOR_PROPOSAL]->(p)
            """, vote_id=vote_id, proposal_id=proposal_id, agent=agent,
                decision=decision, reasoning=reasoning, reflection_cycle=reflection_cycle)

            # Update vote summary cache
            self._update_vote_summary(proposal_id, session)

        # Create vote file in agent's votes/ directory
        self._create_vote_file(proposal_id, agent, decision, reasoning)

        # Log the vote event
        _log_voting_event("vote_cast", {
            "proposal_id": proposal_id,
            "agent": agent,
            "decision": decision,
            "vote_id": vote_id
        })

        return vote_id

    def _update_vote_summary(self, proposal_id: str, session):
        """Update cached vote summary on proposal (as separate properties)."""
        session.run("""
            MATCH (p:Proposal {proposal_id: $proposal_id})
            OPTIONAL MATCH (p)<-[:FOR_PROPOSAL]-(v:Vote)
            WITH p,
                count(v) AS total,
                sum(CASE WHEN v.decision = 'yes' THEN 1 ELSE 0 END) AS yes,
                sum(CASE WHEN v.decision = 'no' THEN 1 ELSE 0 END) AS no,
                sum(CASE WHEN v.decision = 'abstain' THEN 1 ELSE 0 END) AS abstain
            SET p.vote_yes_count = coalesce(yes, 0),
                p.vote_no_count = coalesce(no, 0),
                p.vote_abstain_count = coalesce(abstain, 0),
                p.vote_total = total,
                p.vote_unanimous = (total = 6 AND coalesce(no, 0) = 0)
        """, proposal_id=proposal_id)

    def _create_vote_file(self, proposal_id: str, agent: str, decision: str, reasoning: str):
        """Create vote file in agent's votes/ directory."""
        votes_dir = AGENTS_DIR / agent / "votes"
        votes_dir.mkdir(parents=True, exist_ok=True)

        filepath = votes_dir / f"{proposal_id}.md"
        now = datetime.now().isoformat()

        content = f"""---
proposal_id: {proposal_id}
agent: {agent}
decision: {decision}
voted_at: {now}
---

# Vote on {proposal_id}

**Decision:** {decision.upper()}

**Reasoning:** {reasoning or "No reasoning provided"}
"""
        filepath.write_text(content)

    def sync_votes_from_files(self, agent: str) -> dict:
        """Sync vote files from agent's votes/ directory to Neo4j."""
        votes_dir = AGENTS_DIR / agent / "votes"
        if not votes_dir.exists():
            return {"synced": 0, "errors": 0}

        synced = 0
        errors = 0

        for filepath in votes_dir.glob("*.md"):
            try:
                # Parse frontmatter
                content = filepath.read_text()
                match = re.search(r'^proposal_id:\s*(\S+)', content, re.MULTILINE)
                if not match:
                    errors += 1
                    continue

                proposal_id = match.group(1)

                # Extract decision
                decision_match = re.search(r'^decision:\s*(yes|no|abstain)', content, re.MULTILINE)
                decision = decision_match.group(1) if decision_match else "abstain"

                # Extract reasoning
                reasoning_match = re.search(r'\*\*Reasoning:\*\*\s*(.+)', content)
                reasoning = reasoning_match.group(1).strip() if reasoning_match else ""

                # Cast vote
                self.cast_vote(proposal_id, agent, decision, reasoning)
                synced += 1

            except Exception as e:
                errors += 1
                print(f"Error syncing {filepath}: {e}")

        return {"synced": synced, "errors": errors}

    def get_vote_summary(self, proposal_id: str) -> dict:
        """Get vote summary for a proposal."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (p:Proposal {proposal_id: $proposal_id})
                RETURN p.vote_yes_count AS yes_count,
                       p.vote_no_count AS no_count,
                       p.vote_abstain_count AS abstain_count,
                       p.vote_total AS total_votes,
                       p.vote_unanimous AS unanimous
            """, proposal_id=proposal_id)
            record = result.single()
            if record:
                return {
                    "yes_count": record["yes_count"],
                    "no_count": record["no_count"],
                    "abstain_count": record["abstain_count"],
                    "total_votes": record["total_votes"],
                    "unanimous": record["unanimous"]
                }
            return {}

    def get_agent_votes(self, agent: str, limit: int = 50):
        """Get all votes cast by an agent."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (a:Agent {name: $agent})-[:VOTED_ON]->(v:Vote)
                RETURN v ORDER BY v.voted_at DESC LIMIT $limit
            """, agent=agent, limit=limit)
            return [dict(r["v"]) for r in result]


def main():
    import argparse
    vm = VoteManager()
    parser = argparse.ArgumentParser(description="Manage proposal votes")
    subparsers = parser.add_subparsers(dest="command", help="Command")

    # Cast
    cast_sp = subparsers.add_parser("cast", help="Cast a vote")
    cast_sp.add_argument("--proposal-id", required=True, help="Proposal ID")
    cast_sp.add_argument("--agent", required=True, help="Voting agent")
    cast_sp.add_argument("--vote", required=True, choices=["yes", "no", "abstain"], help="Vote decision")
    cast_sp.add_argument("--reason", default="", help="Vote reasoning")

    # Sync
    sync_sp = subparsers.add_parser("sync", help="Sync votes from files")
    sync_sp.add_argument("--agent", required=True, help="Agent to sync")

    # Summary
    summary_sp = subparsers.add_parser("summary", help="Get vote summary")
    summary_sp.add_argument("--proposal-id", required=True, help="Proposal ID")

    args = parser.parse_args()

    if args.command == "cast":
        vid = vm.cast_vote(args.proposal_id, args.agent, args.vote, args.reason)
        print(f"Cast vote {vid}")
    elif args.command == "sync":
        result = vm.sync_votes_from_files(args.agent)
        print(f"Synced {result['synced']} votes, {result['errors']} errors")
    elif args.command == "summary":
        summary = vm.get_vote_summary(args.proposal_id)
        print(summary)

    vm.close()


if __name__ == "__main__":
    main()
