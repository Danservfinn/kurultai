#!/usr/bin/env python3
"""
Voting Manager for Kurultai Consensus Voting System

Manages the voting process for proposals:
- Moves proposals to voting stage
- Collects votes from all 6 Khans
- Enforces 60-minute voting window
- Records vote metadata

Historical Context:
In the authentic Mongolian Kurultai, all Khans had equal voting rights.
Each Khan could APPROVE, REJECT (veto), or ABSTAIN from any proposal.
Unanimous consent (6/6 APPROVE) was required for implementation.

Usage:
    python3 voting_manager.py --action start-voting --proposal <proposal_id>
    python3 voting_manager.py --action cast-vote --proposal <proposal_id> --agent <agent> --vote <APPROVE|REJECT|ABSTAIN>
    python3 voting_manager.py --action check-status --proposal <proposal_id>
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

# Kurultai paths
KURULTAI_ROOT = Path("/Users/kublai/.openclaw/agents/main")
PROPOSALS_DIR = KURULTAI_ROOT / "proposals"
PENDING_DIR = PROPOSALS_DIR / "pending"
VOTING_DIR = PROPOSALS_DIR / "voting"
APPROVED_DIR = PROPOSALS_DIR / "approved"
REJECTED_DIR = PROPOSALS_DIR / "rejected"
ARCHIVED_DIR = PROPOSALS_DIR / "archived"
LOGS_DIR = KURULTAI_ROOT / "logs"

# All Khans who participate in voting
ALL_KHANS = ["kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei"]

# Voting window in minutes
VOTING_WINDOW_MINUTES = 60


class Vote(Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    ABSTAIN = "ABSTAIN"


@dataclass
class VoteRecord:
    agent: str
    vote: str
    timestamp: str
    reason: Optional[str] = None


@dataclass
class ProposalStatus:
    proposal_id: str
    status: str  # pending, voting, approved, rejected
    votes: Dict[str, VoteRecord]
    created: str
    voting_started: Optional[str] = None
    voting_deadline: Optional[str] = None
    result: Optional[str] = None  # PASSED, FAILED, PENDING


def ensure_directories():
    """Ensure all proposal directories exist."""
    for d in [PENDING_DIR, VOTING_DIR, APPROVED_DIR, REJECTED_DIR, ARCHIVED_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def parse_proposal_file(proposal_path: Path) -> dict:
    """Parse a proposal file and extract frontmatter and content."""
    content = proposal_path.read_text()

    # Extract frontmatter
    frontmatter = {}
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            fm_text = parts[1].strip()
            for line in fm_text.split("\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    frontmatter[key.strip()] = value.strip()

    return {
        "frontmatter": frontmatter,
        "content": content,
        "path": proposal_path
    }


def get_proposal_status(proposal_id: str) -> Optional[ProposalStatus]:
    """Get the current status of a proposal."""
    ensure_directories()

    # Check all directories for the proposal
    for status_dir, status in [
        (PENDING_DIR, "pending"),
        (VOTING_DIR, "voting"),
        (APPROVED_DIR, "approved"),
        (REJECTED_DIR, "rejected")
    ]:
        for f in status_dir.glob(f"{proposal_id}*.md"):
            proposal = parse_proposal_file(f)
            fm = proposal["frontmatter"]

            # Load votes if voting file exists
            votes_file = VOTING_DIR / f"{proposal_id}-votes.json"
            votes = {}
            if votes_file.exists():
                try:
                    with open(votes_file, 'r') as vf:
                        votes_data = json.load(vf)
                        for agent, v in votes_data.items():
                            votes[agent] = VoteRecord(**v)
                except Exception:
                    pass

            return ProposalStatus(
                proposal_id=proposal_id,
                status=status,
                votes=votes,
                created=fm.get("created", ""),
                voting_started=fm.get("voting_started"),
                voting_deadline=fm.get("voting_deadline"),
                result=fm.get("result")
            )

    return None


def start_voting(proposal_id: str) -> Tuple[bool, str]:
    """Move a proposal from pending to voting stage."""
    ensure_directories()

    # Find the proposal in pending
    proposal_files = list(PENDING_DIR.glob(f"{proposal_id}*.md"))
    if not proposal_files:
        # Check if already in voting
        if list(VOTING_DIR.glob(f"{proposal_id}*.md")):
            return True, f"Proposal {proposal_id} already in voting"
        return False, f"Proposal {proposal_id} not found in pending"

    proposal_file = proposal_files[0]
    proposal = parse_proposal_file(proposal_file)

    # Update frontmatter
    content = proposal["content"]
    now = datetime.now()
    deadline = now + timedelta(minutes=VOTING_WINDOW_MINUTES)

    # Add voting timestamps to frontmatter
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            fm_text = parts[1]
            # Add voting started and deadline
            fm_text += f"\nvoting_started: {now.isoformat()}"
            fm_text += f"\nvoting_deadline: {deadline.isoformat()}"
            fm_text += f"\nstatus: voting"
            content = f"---{fm_text}\n---{parts[2]}"

    # Move to voting directory
    new_path = VOTING_DIR / proposal_file.name
    new_path.write_text(content)
    proposal_file.unlink()

    # Initialize votes file
    votes_file = VOTING_DIR / f"{proposal_id}-votes.json"
    with open(votes_file, 'w') as f:
        json.dump({}, f)

    return True, f"Voting started for {proposal_id}. Deadline: {deadline.isoformat()}"


def cast_vote(
    proposal_id: str,
    agent: str,
    vote: Vote,
    reason: Optional[str] = None
) -> Tuple[bool, str]:
    """Cast a vote for a proposal."""
    ensure_directories()

    if agent not in ALL_KHANS:
        return False, f"Invalid agent: {agent}. Must be one of {ALL_KHANS}"

    status = get_proposal_status(proposal_id)
    if not status:
        return False, f"Proposal {proposal_id} not found"

    if status.status != "voting":
        return False, f"Proposal {proposal_id} is not in voting stage (status: {status.status})"

    # Check if voting deadline has passed
    if status.voting_deadline:
        deadline = datetime.fromisoformat(status.voting_deadline)
        if datetime.now() > deadline:
            return False, f"Voting deadline has passed for {proposal_id}"

    # Record the vote
    votes_file = VOTING_DIR / f"{proposal_id}-votes.json"
    votes = {}
    if votes_file.exists():
        with open(votes_file, 'r') as f:
            votes = json.load(f)

    votes[agent] = VoteRecord(
        agent=agent,
        vote=vote.value,
        timestamp=datetime.now().isoformat(),
        reason=reason
    )
    votes[agent] = asdict(votes[agent])

    with open(votes_file, 'w') as f:
        json.dump(votes, f, indent=2)

    return True, f"Vote recorded: {agent} -> {vote.value} for {proposal_id}"


def get_vote_tally(proposal_id: str) -> Dict[str, int]:
    """Get the current vote tally for a proposal."""
    votes_file = VOTING_DIR / f"{proposal_id}-votes.json"

    tally = {
        "APPROVE": 0,
        "REJECT": 0,
        "ABSTAIN": 0,
        "NOT_VOTED": len(ALL_KHANS)
    }

    if votes_file.exists():
        with open(votes_file, 'r') as f:
            votes = json.load(f)

        for agent in ALL_KHANS:
            if agent in votes:
                vote = votes[agent]["vote"]
                tally[vote] += 1
                tally["NOT_VOTED"] -= 1

    return tally


def check_voting_complete(proposal_id: str) -> Tuple[bool, str]:
    """Check if voting is complete and determine result."""
    status = get_proposal_status(proposal_id)
    if not status:
        return False, f"Proposal {proposal_id} not found"

    if status.status != "voting":
        return True, f"Proposal {proposal_id} is not in voting stage"

    tally = get_vote_tally(proposal_id)

    # Check for any REJECT votes (veto)
    if tally["REJECT"] > 0:
        return finalize_proposal(proposal_id, "rejected", f"Vetoed with {tally['REJECT']} REJECT vote(s)")

    # Check for unanimous approval
    if tally["APPROVE"] == len(ALL_KHANS):
        return finalize_proposal(proposal_id, "approved", "Unanimous consent (6/6 APPROVE)")

    # Check if voting window has closed
    if status.voting_deadline:
        deadline = datetime.fromisoformat(status.voting_deadline)
        if datetime.now() > deadline:
            if tally["NOT_VOTED"] > 0:
                # Incomplete voting - extend or fail
                return False, f"Voting incomplete: {tally['NOT_VOTED']} agents haven't voted"
            elif tally["APPROVE"] < len(ALL_KHANS):
                # Not unanimous - fail
                return finalize_proposal(proposal_id, "rejected",
                    f"Failed to achieve unanimous consent: {tally['APPROVE']}/6 APPROVE, {tally['ABSTAIN']} ABSTAIN")

    # Voting still in progress
    votes_remaining = tally["NOT_VOTED"]
    return False, f"Voting in progress: {tally['APPROVE']}/6 APPROVE, {votes_remaining} votes remaining"


def finalize_proposal(proposal_id: str, result: str, reason: str) -> Tuple[bool, str]:
    """Move proposal to final directory and record result."""
    ensure_directories()

    # Find the proposal in voting
    proposal_files = list(VOTING_DIR.glob(f"{proposal_id}*.md"))
    if not proposal_files:
        return False, f"Proposal {proposal_id} not found in voting"

    proposal_file = proposal_files[0]
    proposal = parse_proposal_file(proposal_file)

    # Update frontmatter with result
    content = proposal["content"]
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            fm_text = parts[1]
            fm_text += f"\nstatus: {result}"
            fm_text += f"\nresult: {reason}"
            fm_text += f"\nfinalized: {datetime.now().isoformat()}"
            content = f"---{fm_text}\n---{parts[2]}"

    # Move to appropriate directory
    if result == "approved":
        dest_dir = APPROVED_DIR
    else:
        dest_dir = REJECTED_DIR

    new_path = dest_dir / proposal_file.name
    new_path.write_text(content)

    # Archive votes file
    votes_file = VOTING_DIR / f"{proposal_id}-votes.json"
    if votes_file.exists():
        archive_votes = dest_dir / f"{proposal_id}-votes.json"
        archive_votes.write_text(votes_file.read_text())
        votes_file.unlink()

    proposal_file.unlink()

    # Log the result
    log_result(proposal_id, result, reason)

    return True, f"Proposal {proposal_id} {result}: {reason}"


def log_result(proposal_id: str, result: str, reason: str):
    """Log proposal result for audit trail."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOGS_DIR / "proposal-results.jsonl"

    entry = {
        "proposal_id": proposal_id,
        "result": result,
        "reason": reason,
        "timestamp": datetime.now().isoformat()
    }

    with open(log_file, 'a') as f:
        f.write(json.dumps(entry) + "\n")


def list_active_voting() -> List[ProposalStatus]:
    """List all proposals currently in voting."""
    ensure_directories()

    proposals = []
    for f in VOTING_DIR.glob("*.md"):
        if "-votes.json" in f.name:
            continue

        proposal_id = f.stem
        status = get_proposal_status(proposal_id)
        if status:
            proposals.append(status)

    return proposals


def print_voting_status(proposal_id: str):
    """Print detailed voting status for a proposal."""
    status = get_proposal_status(proposal_id)
    if not status:
        print(f"Proposal {proposal_id} not found")
        return

    print(f"\n{'='*60}")
    print(f"PROPOSAL: {proposal_id}")
    print(f"STATUS: {status.status.upper()}")
    print(f"{'='*60}")

    if status.voting_started:
        print(f"Voting Started: {status.voting_started}")
    if status.voting_deadline:
        print(f"Voting Deadline: {status.voting_deadline}")

    tally = get_vote_tally(proposal_id)
    print(f"\nVOTE TALLY:")
    print(f"  APPROVE:  {tally['APPROVE']}/6")
    print(f"  REJECT:   {tally['REJECT']}/6")
    print(f"  ABSTAIN:  {tally['ABSTAIN']}/6")
    print(f"  NOT VOTED: {tally['NOT_VOTED']}/6")

    votes_file = VOTING_DIR / f"{proposal_id}-votes.json"
    if votes_file.exists():
        print(f"\nVOTES:")
        with open(votes_file, 'r') as f:
            votes = json.load(f)
        for agent in ALL_KHANS:
            if agent in votes:
                v = votes[agent]
                reason = f" ({v.get('reason')})" if v.get('reason') else ""
                print(f"  {agent}: {v['vote']}{reason}")
            else:
                print(f"  {agent}: NOT VOTED")

    if status.result:
        print(f"\nRESULT: {status.result}")

    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Manage voting for Kurultai proposals"
    )
    parser.add_argument(
        "--action",
        required=True,
        choices=[
            "start-voting",
            "cast-vote",
            "check-status",
            "tally",
            "list-voting",
            "finalize"
        ],
        help="Action to perform"
    )
    parser.add_argument("--proposal", help="Proposal ID")
    parser.add_argument("--agent", help="Agent casting vote")
    parser.add_argument(
        "--vote",
        choices=["APPROVE", "REJECT", "ABSTAIN"],
        help="Vote value"
    )
    parser.add_argument("--reason", help="Reason for vote (optional)")

    args = parser.parse_args()

    if args.action == "start-voting":
        if not args.proposal:
            print("Error: --proposal required for start-voting")
            sys.exit(1)
        success, message = start_voting(args.proposal)
        print(message)
        sys.exit(0 if success else 1)

    elif args.action == "cast-vote":
        if not args.proposal or not args.agent or not args.vote:
            print("Error: --proposal, --agent, and --vote required for cast-vote")
            sys.exit(1)
        vote = Vote(args.vote)
        success, message = cast_vote(args.proposal, args.agent, vote, args.reason)
        print(message)
        sys.exit(0 if success else 1)

    elif args.action == "check-status":
        if not args.proposal:
            print("Error: --proposal required for check-status")
            sys.exit(1)
        print_voting_status(args.proposal)

    elif args.action == "tally":
        if not args.proposal:
            print("Error: --proposal required for tally")
            sys.exit(1)
        tally = get_vote_tally(args.proposal)
        print(json.dumps(tally, indent=2))

    elif args.action == "list-voting":
        proposals = list_active_voting()
        for p in proposals:
            tally = get_vote_tally(p.proposal_id)
            print(f"{p.proposal_id}: {p.status} ({tally['APPROVE']}/6 APPROVE, {tally['NOT_VOTED']} remaining)")

    elif args.action == "finalize":
        if not args.proposal:
            print("Error: --proposal required for finalize")
            sys.exit(1)
        complete, message = check_voting_complete(args.proposal)
        print(message)


if __name__ == "__main__":
    main()