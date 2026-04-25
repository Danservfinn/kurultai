#!/usr/bin/env python3
"""
proposal_manager.py - CRUD operations for Kurultai proposals.

Usage:
    python proposal_manager.py create --agent "ogedei" --title "Add X" --desc "..."
    python proposal_manager.py list --status pending
    python proposal_manager.py approve --proposal-id <uuid>
    python proposal_manager.py expire --proposal-id <uuid>
"""
from __future__ import annotations

import uuid
import sys
import os
import json
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import get_driver, close_driver
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


class ProposalManager:
    def __init__(self):
        self.driver = get_driver()

    def close(self):
        if self.driver:
            close_driver()
            self.driver = None

    # Tier-specific TTLs (hours). T2/T3 include 1h buffer beyond voting window.
    TIER_TTL_HOURS = {"T0": 1, "T1": 1, "T2": 5, "T3": 14}

    # Tier-specific approval thresholds
    TIER_THRESHOLDS = {
        "T0": {"min_yes": 0, "quorum": 0},      # bypass — auto-approved
        "T1": {"min_yes": 0, "quorum": 0},      # auto-approved (self-scoped)
        "T2": {"min_yes": 4, "quorum": 4},      # 4/6 majority, proposer excluded
        "T3": {"min_yes": 5, "quorum": 5},      # 5/6 supermajority
    }

    def create_proposal(self, title: str, description: str, proposing_agent: str,
                       priority: str = "normal", category: str = "feature",
                       reflection_cycle: str = None, tier: str = "T2") -> str:
        """Create a new proposal and auto-cast YES vote from proposer (T0/T1 only)."""
        proposal_id = str(uuid.uuid4())[:12]
        now = datetime.now()
        ttl_hours = self.TIER_TTL_HOURS.get(tier, 24)
        expires_at = now + timedelta(hours=ttl_hours)

        if reflection_cycle is None:
            reflection_cycle = now.strftime("%Y-%m-%d-%H%M")

        with self.driver.session() as session:
            # Create proposal (vote summary as separate properties - Neo4j doesn't support nested maps)
            session.run("""
                MERGE (a:Agent {name: $proposing_agent})
                CREATE (p:Proposal {
                    proposal_id: $proposal_id,
                    title: $title,
                    description: $description,
                    proposing_agent: $proposing_agent,
                    created_at: datetime(),
                    expires_at: datetime($expires_at),
                    status: 'pending',
                    priority: $priority,
                    category: $category,
                    implementation_tasks: [],
                    vote_yes_count: 0,
                    vote_no_count: 0,
                    vote_abstain_count: 0,
                    vote_total: 0,
                    vote_unanimous: false,
                    vote_threshold_met: false,
                    tier: $tier,
                    reflection_cycle: $reflection_cycle
                })
                CREATE (a)-[:PROPOSED {at: datetime()}]->(p)
                RETURN p.proposal_id AS id
            """, proposal_id=proposal_id, title=title, description=description,
                proposing_agent=proposing_agent, expires_at=expires_at.isoformat(),
                priority=priority, category=category, reflection_cycle=reflection_cycle,
                tier=tier)

            # Auto-cast YES vote from proposer (T0/T1 only).
            # T2/T3 proposers are excluded from voting on their own proposals.
            if tier in ("T0", "T1"):
                self._cast_vote(proposal_id, proposing_agent, "yes",
                               "Proposed by me", reflection_cycle, session)

        # Create file in proposals/pending/
        self._create_proposal_file(proposal_id, title, description, proposing_agent, priority, category)

        # Log the proposal creation
        _log_voting_event("proposal_created", {
            "proposal_id": proposal_id,
            "title": title,
            "proposing_agent": proposing_agent,
            "priority": priority,
            "category": category
        })

        return proposal_id

    def _cast_vote(self, proposal_id: str, agent: str, decision: str,
                   reasoning: str, reflection_cycle: str, session) -> str:
        """Cast or update a vote (internal method)."""
        vote_id = str(uuid.uuid4())[:12]

        # Upsert: delete existing vote from this agent for this proposal
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
                p.vote_unanimous = (total = 6 AND coalesce(no, 0) = 0),
                p.vote_threshold_met = CASE coalesce(p.tier, 'T2')
                    WHEN 'T0' THEN true
                    WHEN 'T1' THEN true
                    WHEN 'T2' THEN (coalesce(yes, 0) >= 4)
                    WHEN 'T3' THEN (coalesce(yes, 0) >= 5)
                    ELSE (total = 6 AND coalesce(no, 0) = 0)
                END
        """, proposal_id=proposal_id)

    def _create_proposal_file(self, proposal_id: str, title: str,
                             description: str, proposing_agent: str,
                             priority: str = "normal", category: str = "feature"):
        """Create markdown file in proposals/pending/."""
        proposals_dir = AGENTS_DIR / "main" / "proposals" / "pending"
        proposals_dir.mkdir(parents=True, exist_ok=True)

        filepath = proposals_dir / f"{proposal_id}.md"
        now = datetime.now().isoformat()

        content = f"""---
proposal_id: {proposal_id}
title: "{title}"
proposing_agent: {proposing_agent}
created_at: {now}
expires_at: {(datetime.now() + timedelta(hours=24)).isoformat()}
status: pending
priority: {priority}
category: {category}
---

## Proposal

{description}

## Current Votes

| Agent | Vote | Reasoning |
|-------|------|-----------|
| {proposing_agent} | YES | Proposed by me |

## Implementation Plan

*To be filled by Kublai upon approval.*
"""
        filepath.write_text(content)

    def get_proposal(self, proposal_id: str):
        """Get proposal details with votes."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (p:Proposal {proposal_id: $proposal_id})
                OPTIONAL MATCH (p)<-[:FOR_PROPOSAL]-(v:Vote)
                RETURN p, collect({{agent: v.agent, decision: v.decision, reasoning: v.reasoning, voted_at: v.voted_at}}) AS votes
            """, proposal_id=proposal_id)
            record = result.single()
            if record:
                return {
                    "proposal": dict(record["p"]),
                    "votes": record["votes"]
                }
            return None

    def list_proposals(self, status: str = None, limit: int = 50):
        """List proposals, optionally filtered by status."""
        with self.driver.session() as session:
            if status:
                result = session.run("""
                    MATCH (p:Proposal {status: $status})
                    RETURN p ORDER BY p.created_at DESC LIMIT $limit
                """, status=status, limit=limit)
            else:
                result = session.run("""
                    MATCH (p:Proposal)
                    RETURN p ORDER BY p.created_at DESC LIMIT $limit
                """, limit=limit)
            return [dict(r["p"]) for r in result]

    def update_status(self, proposal_id: str, new_status: str, actor: str = "system"):
        """Update proposal status."""
        with self.driver.session() as session:
            session.run("""
                MATCH (p:Proposal {proposal_id: $proposal_id})
                SET p.status = $new_status,
                    p.updated_at = datetime()
            """, proposal_id=proposal_id, new_status=new_status)

            # Log the status change
            _log_voting_event("proposal_status_changed", {
                "proposal_id": proposal_id,
                "new_status": new_status,
                "actor": actor
            })

            # If approved, move file
            if new_status == "approved":
                self._move_proposal_file(proposal_id, "pending", "approved")
            elif new_status in ("expired", "rejected", "archived"):
                self._move_proposal_file(proposal_id, "pending", "archived")

    def _move_proposal_file(self, proposal_id: str, from_dir: str, to_dir: str, status: str = None):
        """Move proposal file between directories and update Resolution section."""
        import re
        from datetime import datetime

        base = AGENTS_DIR / "main" / "proposals"
        src = base / from_dir / f"{proposal_id}.md"
        dst = base / to_dir
        dst.mkdir(parents=True, exist_ok=True)

        if src.exists():
            # Read proposal content
            with open(src, 'r') as f:
                content = f.read()

            # Update Resolution section based on final status
            resolution_text = {
                "approved": f"APPROVED by Kurultai vote on {datetime.now().strftime('%Y-%m-%d')}. Implementation tasks created.",
                "rejected": f"REJECTED by Kurultai vote on {datetime.now().strftime('%Y-%m-%d')}. Approval threshold not met.",
                "expired": f"EXPIRED on {datetime.now().strftime('%Y-%m-%d')}. Voting deadline passed without sufficient approval.",
                "archived": f"ARCHIVED on {datetime.now().strftime('%Y-%m-%d')}. Proposal closed."
            }

            new_status = status or to_dir.capitalize()
            resolution_update = resolution_text.get(to_dir, f"This proposal is {new_status}.")

            # Replace or add Resolution section
            resolution_pattern = r'(## Resolution\s*\n).*?(?=\n---|\n##[A-Z]|\Z)'
            replacement = rf'\1{resolution_update}'

            if re.search(r'## Resolution', content, re.MULTILINE):
                content = re.sub(resolution_pattern, replacement, content, flags=re.DOTALL)
            else:
                # Add Resolution section before the footer
                content = re.sub(
                    r'(\n---\n\*Generated)',
                    rf'\n\n## Resolution\n{resolution_update}\n\1',
                    content
                )

            # Write updated content to destination
            with open(dst / f"{proposal_id}.md", 'w') as f:
                f.write(content)

            # Remove source file
            src.unlink()

    def link_implementation_tasks(self, proposal_id: str, task_ids: list):
        """Link implementation tasks to approved proposal."""
        with self.driver.session() as session:
            session.run("""
                MATCH (p:Proposal {proposal_id: $proposal_id})
                SET p.implementation_tasks = $task_ids,
                    p.status = 'implementing'
            """, proposal_id=proposal_id, task_ids=task_ids)

            # Create relationships to tasks
            for task_id in task_ids:
                session.run("""
                    MATCH (p:Proposal {proposal_id: $proposal_id})
                    MATCH (t:Task {task_id: $task_id})
                    CREATE (p)-[:IMPLEMENTED_BY]->(t)
                """, proposal_id=proposal_id, task_id=task_id)

    def check_unanimous_approval(self) -> list:
        """Return list of proposal_ids that have 6/6 YES votes."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (p:Proposal {status: 'pending'})
                OPTIONAL MATCH (p)<-[:FOR_PROPOSAL]-(v:Vote)
                WITH p,
                    count(v) AS total_votes,
                    sum(CASE WHEN v.decision = 'yes' THEN 1 ELSE 0 END) AS yes_count,
                    sum(CASE WHEN v.decision = 'no' THEN 1 ELSE 0 END) AS no_count
                WHERE total_votes = 6 AND no_count = 0
                RETURN p.proposal_id AS proposal_id, p.title AS title, yes_count
            """)
            return [{"proposal_id": r["proposal_id"], "title": r["title"],
                    "yes_count": r["yes_count"]} for r in result]

    def check_threshold_met(self) -> list:
        """Return proposals that meet their tier's approval threshold.

        Implements tiered approval:
        - T0/T1: auto-approved (threshold 0)
        - T2: 4/6 majority (proposer excluded)
        - T3: 5/6 supermajority
        Kublai NO vote on T2/T3 acts as veto (proposal excluded from results).
        Legacy proposals (no tier) default to T2 behavior.
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (p:Proposal {status: 'pending'})
                OPTIONAL MATCH (p)<-[:FOR_PROPOSAL]-(v:Vote)
                WITH p,
                    count(v) AS total_votes,
                    sum(CASE WHEN v.decision = 'yes' THEN 1 ELSE 0 END) AS yes_count,
                    sum(CASE WHEN v.decision = 'no' THEN 1 ELSE 0 END) AS no_count,
                    coalesce(p.tier, 'T2') AS tier
                OPTIONAL MATCH (p)<-[:FOR_PROPOSAL]-(kv:Vote {agent: 'kublai', decision: 'no'})
                WITH p, total_votes, yes_count, no_count, tier, kv
                WHERE NOT (tier IN ['T2', 'T3'] AND kv IS NOT NULL)
                RETURN p.proposal_id AS proposal_id, p.title AS title,
                       yes_count, no_count, total_votes, tier
            """)
            approved = []
            for r in result:
                t = r["tier"]
                threshold = self.TIER_THRESHOLDS.get(t, {"min_yes": 6, "quorum": 6})
                if (r["yes_count"] >= threshold["min_yes"] and
                    r["total_votes"] >= threshold["quorum"]):
                    approved.append({
                        "proposal_id": r["proposal_id"],
                        "title": r["title"],
                        "yes_count": r["yes_count"],
                        "no_count": r["no_count"],
                        "total_votes": r["total_votes"],
                        "tier": t
                    })
            return approved

    def get_expired_proposals(self) -> list:
        """Return list of pending proposals past their expiration."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (p:Proposal {status: 'pending'})
                WHERE p.expires_at < datetime()
                RETURN p.proposal_id AS proposal_id, p.title AS title, p.expires_at AS expires_at
            """)
            return [dict(r) for r in result]


def main():
    import argparse
    pm = ProposalManager()
    parser = argparse.ArgumentParser(description="Manage Kurultai proposals")
    subparsers = parser.add_subparsers(dest="command", help="Command")

    # Create
    create_sp = subparsers.add_parser("create", help="Create a proposal")
    create_sp.add_argument("--agent", required=True, help="Proposing agent")
    create_sp.add_argument("--title", required=True, help="Proposal title")
    create_sp.add_argument("--desc", required=True, help="Proposal description")
    create_sp.add_argument("--priority", default="normal", choices=["low", "normal", "high", "critical"])
    create_sp.add_argument("--category", default="feature", choices=["routing", "performance", "reliability", "feature", "refactoring", "monitoring"])

    # List
    list_sp = subparsers.add_parser("list", help="List proposals")
    list_sp.add_argument("--status", help="Filter by status")

    # Approve
    approve_sp = subparsers.add_parser("approve", help="Mark proposal as approved")
    approve_sp.add_argument("--proposal-id", required=True, help="Proposal ID")

    # Expire
    expire_sp = subparsers.add_parser("expire", help="Mark proposal as expired")
    expire_sp.add_argument("--proposal-id", required=True, help="Proposal ID")

    args = parser.parse_args()

    if args.command == "create":
        pid = pm.create_proposal(args.title, args.desc, args.agent, args.priority, args.category)
        print(f"Created proposal {pid}")
    elif args.command == "list":
        proposals = pm.list_proposals(args.status)
        for p in proposals:
            print(f"{p['proposal_id']}: {p['title']} [{p['status']}]")
    elif args.command == "approve":
        pm.update_status(args.proposal_id, "approved")
        print(f"Approved {args.proposal_id}")
    elif args.command == "expire":
        pm.update_status(args.proposal_id, "expired")
        print(f"Expired {args.proposal_id}")

    pm.close()


if __name__ == "__main__":
    main()
