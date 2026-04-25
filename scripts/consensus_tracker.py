#!/usr/bin/env python3
"""
Consensus Tracker for Kurultai Voting System

Tracks and reports on the consensus status of all proposals.
Provides metrics on voting patterns and proposal outcomes.

Historical Context:
In the authentic Mongolian Kurultai, tracking consensus was essential.
Each Khan's vote was recorded, and proposals only advanced with unanimous consent.
This tracker provides visibility into the voting process and outcomes.

Usage:
    python3 consensus_tracker.py --report
    python3 consensus_tracker.py --proposal <proposal_id>
    python3 consensus_tracker.py --agent <agent_name>
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from collections import defaultdict

# Kurultai paths
KURULTAI_ROOT = Path("/Users/kublai/.openclaw/agents/main")
PROPOSALS_DIR = KURULTAI_ROOT / "proposals"
PENDING_DIR = PROPOSALS_DIR / "pending"
VOTING_DIR = PROPOSALS_DIR / "voting"
APPROVED_DIR = PROPOSALS_DIR / "approved"
REJECTED_DIR = PROPOSALS_DIR / "rejected"
ARCHIVED_DIR = PROPOSALS_DIR / "archived"
LOGS_DIR = KURULTAI_ROOT / "logs"

# All Khans
ALL_KHANS = ["kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei"]


def load_all_proposals() -> Dict[str, List[dict]]:
    """Load all proposals from all directories."""
    proposals = {
        "pending": [],
        "voting": [],
        "approved": [],
        "rejected": [],
        "archived": []
    }

    for status, directory in [
        ("pending", PENDING_DIR),
        ("voting", VOTING_DIR),
        ("approved", APPROVED_DIR),
        ("rejected", REJECTED_DIR),
        ("archived", ARCHIVED_DIR)
    ]:
        if not directory.exists():
            continue

        for f in directory.glob("*.md"):
            if "-votes.json" in f.name:
                continue

            try:
                content = f.read_text()
                frontmatter = {}

                if content.startswith("---"):
                    parts = content.split("---", 2)
                    if len(parts) >= 3:
                        fm_text = parts[1].strip()
                        for line in fm_text.split("\n"):
                            if ":" in line:
                                key, value = line.split(":", 1)
                                frontmatter[key.strip()] = value.strip()

                proposals[status].append({
                    "id": f.stem,
                    "path": str(f),
                    "frontmatter": frontmatter,
                    "status": status
                })
            except Exception as e:
                print(f"Warning: Could not load {f}: {e}", file=sys.stderr)

    return proposals


def load_votes_for_proposal(proposal_id: str) -> Dict[str, dict]:
    """Load votes for a specific proposal."""
    votes_file = VOTING_DIR / f"{proposal_id}-votes.json"

    # Check in voting directory first
    if votes_file.exists():
        with open(votes_file, 'r') as f:
            return json.load(f)

    # Check in approved/rejected directories
    for directory in [APPROVED_DIR, REJECTED_DIR]:
        archived_votes = directory / f"{proposal_id}-votes.json"
        if archived_votes.exists():
            with open(archived_votes, 'r') as f:
                return json.load(f)

    return {}


def calculate_consensus_metrics(proposals: Dict[str, List[dict]]) -> dict:
    """Calculate overall consensus metrics."""
    metrics = {
        "total_proposals": 0,
        "by_status": {},
        "approval_rate": 0.0,
        "average_approval_time": 0,
        "voting_patterns": {khan: {"APPROVE": 0, "REJECT": 0, "ABSTAIN": 0} for khan in ALL_KHANS},
        "recent_activity": []
    }

    total_proposals = 0
    approved_count = 0
    rejected_count = 0

    for status, proposal_list in proposals.items():
        metrics["by_status"][status] = len(proposal_list)
        total_proposals += len(proposal_list)

        if status == "approved":
            approved_count = len(proposal_list)
        elif status == "rejected":
            rejected_count = len(proposal_list)

    metrics["total_proposals"] = total_proposals

    # Calculate approval rate
    total_decided = approved_count + rejected_count
    if total_decided > 0:
        metrics["approval_rate"] = approved_count / total_decided

    # Calculate voting patterns
    for status, proposal_list in proposals.items():
        for proposal in proposal_list:
            votes = load_votes_for_proposal(proposal["id"])
            for agent, vote_data in votes.items():
                if agent in metrics["voting_patterns"]:
                    vote_value = vote_data.get("vote", "ABSTAIN")
                    metrics["voting_patterns"][agent][vote_value] += 1

    # Get recent activity (last 24 hours)
    now = datetime.now()
    one_day_ago = now - timedelta(days=1)

    for status, proposal_list in proposals.items():
        for proposal in proposal_list:
            created = proposal["frontmatter"].get("created", "")
            if created:
                try:
                    created_dt = datetime.fromisoformat(created)
                    if created_dt > one_day_ago:
                        metrics["recent_activity"].append({
                            "id": proposal["id"],
                            "status": status,
                            "created": created
                        })
                except Exception:
                    pass

    return metrics


def get_proposal_consensus_status(proposal_id: str) -> dict:
    """Get detailed consensus status for a specific proposal."""
    proposals = load_all_proposals()

    # Find the proposal
    proposal = None
    current_status = None

    for status, proposal_list in proposals.items():
        for p in proposal_list:
            if p["id"] == proposal_id:
                proposal = p
                current_status = status
                break
        if proposal:
            break

    if not proposal:
        return {"error": f"Proposal {proposal_id} not found"}

    votes = load_votes_for_proposal(proposal_id)

    # Calculate vote counts
    vote_counts = {"APPROVE": 0, "REJECT": 0, "ABSTAIN": 0, "NOT_VOTED": 0}
    vote_details = {}

    for khan in ALL_KHANS:
        if khan in votes:
            vote_value = votes[khan].get("vote", "ABSTAIN")
            vote_counts[vote_value] += 1
            vote_details[khan] = {
                "vote": vote_value,
                "timestamp": votes[khan].get("timestamp", ""),
                "reason": votes[khan].get("reason", "")
            }
        else:
            vote_counts["NOT_VOTED"] += 1
            vote_details[khan] = {"vote": "NOT_VOTED"}

    # Determine consensus status
    consensus_status = "PENDING"
    if vote_counts["REJECT"] > 0:
        consensus_status = "VETOED"
    elif vote_counts["APPROVE"] == len(ALL_KHANS):
        consensus_status = "UNANIMOUS"
    elif vote_counts["NOT_VOTED"] == 0:
        consensus_status = "NO_CONSENSUS"

    return {
        "proposal_id": proposal_id,
        "status": current_status,
        "consensus_status": consensus_status,
        "vote_counts": vote_counts,
        "vote_details": vote_details,
        "frontmatter": proposal["frontmatter"],
        "voting_deadline": proposal["frontmatter"].get("voting_deadline", "")
    }


def get_agent_voting_history(agent: str) -> dict:
    """Get voting history for a specific agent."""
    if agent not in ALL_KHANS:
        return {"error": f"Invalid agent: {agent}"}

    proposals = load_all_proposals()
    history = {
        "agent": agent,
        "total_votes": 0,
        "by_vote": {"APPROVE": 0, "REJECT": 0, "ABSTAIN": 0},
        "proposals_voted": [],
        "proposals_authored": []
    }

    # Find proposals authored by this agent
    for status, proposal_list in proposals.items():
        for proposal in proposal_list:
            fm = proposal["frontmatter"]
            if fm.get("agent") == agent:
                history["proposals_authored"].append({
                    "id": proposal["id"],
                    "status": status,
                    "title": fm.get("title", "")
                })

    # Find votes cast by this agent
    for status in ["approved", "rejected", "voting"]:
        directory = PROPOSALS_DIR / status
        if not directory.exists():
            continue

        for f in directory.glob("*-votes.json"):
            try:
                with open(f, 'r') as vf:
                    votes = json.load(vf)
                    if agent in votes:
                        vote_data = votes[agent]
                        vote_value = vote_data.get("vote", "ABSTAIN")
                        history["by_vote"][vote_value] += 1
                        history["total_votes"] += 1
                        history["proposals_voted"].append({
                            "proposal_id": f.stem.replace("-votes", ""),
                            "vote": vote_value,
                            "timestamp": vote_data.get("timestamp", ""),
                            "reason": vote_data.get("reason", "")
                        })
            except Exception:
                pass

    return history


def generate_consensus_report() -> str:
    """Generate a human-readable consensus report."""
    proposals = load_all_proposals()
    metrics = calculate_consensus_metrics(proposals)

    report = []
    report.append("# Kurultai Consensus Report")
    report.append(f"\n**Generated:** {datetime.now().isoformat()}")
    report.append(f"\n## Overview\n")
    report.append(f"- Total Proposals: {metrics['total_proposals']}")
    report.append(f"- Approval Rate: {metrics['approval_rate']:.1%}")
    report.append(f"\n## Status Breakdown\n")

    for status, count in metrics["by_status"].items():
        report.append(f"- {status.capitalize()}: {count}")

    report.append(f"\n## Voting Patterns by Khan\n")
    report.append("| Khan | APPROVE | REJECT | ABSTAIN |")
    report.append("|------|---------|--------|---------|")
    for khan in ALL_KHANS:
        pattern = metrics["voting_patterns"][khan]
        report.append(f"| {khan} | {pattern['APPROVE']} | {pattern['REJECT']} | {pattern['ABSTAIN']} |")

    # Active voting
    if proposals["voting"]:
        report.append(f"\n## Active Voting\n")
        for proposal in proposals["voting"]:
            votes = load_votes_for_proposal(proposal["id"])
            approve_count = sum(1 for v in votes.values() if v.get("vote") == "APPROVE")
            deadline = proposal["frontmatter"].get("voting_deadline", "No deadline")
            report.append(f"- **{proposal['id']}**: {approve_count}/6 APPROVE (Deadline: {deadline})")

    # Recent activity
    if metrics["recent_activity"]:
        report.append(f"\n## Recent Activity (24h)\n")
        for activity in metrics["recent_activity"]:
            report.append(f"- {activity['id']}: {activity['status']}")

    return "\n".join(report)


def print_json(data: dict):
    """Print data as formatted JSON."""
    print(json.dumps(data, indent=2))


def main():
    parser = argparse.ArgumentParser(
        description="Track consensus status for Kurultai proposals"
    )
    parser.add_argument("--report", action="store_true", help="Generate consensus report")
    parser.add_argument("--proposal", help="Get consensus status for specific proposal")
    parser.add_argument("--agent", help="Get voting history for specific agent")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if args.proposal:
        status = get_proposal_consensus_status(args.proposal)
        if args.json:
            print_json(status)
        else:
            print(f"\nProposal: {status.get('proposal_id', args.proposal)}")
            print(f"Status: {status.get('status', 'unknown')}")
            print(f"Consensus: {status.get('consensus_status', 'unknown')}")
            print(f"\nVotes:")
            for khan, details in status.get("vote_details", {}).items():
                print(f"  {khan}: {details.get('vote', 'NOT_VOTED')}")

    elif args.agent:
        history = get_agent_voting_history(args.agent)
        if args.json:
            print_json(history)
        else:
            print(f"\nAgent: {args.agent}")
            print(f"Total Votes: {history.get('total_votes', 0)}")
            print(f"Proposals Authored: {len(history.get('proposals_authored', []))}")
            print(f"\nVote Breakdown:")
            for vote, count in history.get("by_vote", {}).items():
                print(f"  {vote}: {count}")

    elif args.report:
        report = generate_consensus_report()
        print(report)

    else:
        # Default: show summary
        proposals = load_all_proposals()
        metrics = calculate_consensus_metrics(proposals)

        print(f"\nKurultai Consensus Summary")
        print(f"========================")
        print(f"Total Proposals: {metrics['total_proposals']}")
        print(f"Approval Rate: {metrics['approval_rate']:.1%}")
        print(f"\nBy Status:")
        for status, count in metrics["by_status"].items():
            print(f"  {status}: {count}")


if __name__ == "__main__":
    main()