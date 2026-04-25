#!/usr/bin/env python3
from __future__ import annotations
# DEPRECATED: This filesystem-based proposal tracker is superseded by proposal_manager.py (Neo4j-backed).
# Migration status: hourly_reflection.sh still imports from this file for --list and --stale queries.
# TODO: Migrate remaining callers to proposal_manager.py, then archive this file.
"""
Proposal Lifecycle Tracker

Tracks agent proposals from creation through implementation.
Reviews pending proposals, converts approved ones to tasks, tracks status.

Usage:
    python3 proposal_lifecycle.py --list          # List all proposals with status
    python3 proposal_lifecycle.py --review        # Interactive review of pending proposals
    python3 proposal_lifecycle.py --approve <id>  # Approve a proposal (creates task)
    python3 proposal_lifecycle.py --reject <id>   # Reject a proposal
    python3 proposal_lifecycle.py --stale         # Show proposals >24h old without action
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROPOSALS_DIR = Path(__file__).parent.parent / "proposals"
STATE_FILE = Path(__file__).parent.parent / "logs" / "proposal-state.json"


def parse_proposal_file(filepath):
    """Parse a proposal markdown file into structured data"""
    content = filepath.read_text()

    # Extract frontmatter-like sections
    proposal = {
        "file": filepath.name,
        "path": str(filepath),
        "mtime": datetime.fromtimestamp(filepath.stat().st_mtime),
    }

    # Extract title (first # heading)
    title_match = re.search(r'^# (.+)', content, re.MULTILINE)
    proposal["title"] = title_match.group(1) if title_match else "Untitled"

    # Extract metadata
    agent_match = re.search(r'\*\*Agent:\*\*\s*(.+)', content)
    proposal["agent"] = agent_match.group(1).strip() if agent_match else "unknown"

    timestamp_match = re.search(r'\*\*Timestamp:\*\*\s*(.+)', content)
    proposal["timestamp"] = timestamp_match.group(1).strip() if timestamp_match else ""

    domain_match = re.search(r'\*\*Domain:\*\*\s*(.+)', content)
    proposal["domain"] = domain_match.group(1).strip() if domain_match else "general"

    # Extract status section
    status_match = re.search(r'## Status\s*\n(.*?)(?=## |$)', content, re.DOTALL)
    if status_match:
        status_text = status_match.group(1)
        impl_match = re.search(r'\*\*Implemented:\*\*\s*(YES|NO|PARTIAL)', status_text)
        proposal["implemented"] = impl_match.group(1) if impl_match else "UNKNOWN"

        verified_match = re.search(r'\*\*Verified:\*\*\s*(YES|NO)', status_text)
        proposal["verified"] = verified_match.group(1) if verified_match else "UNKNOWN"

        category_match = re.search(r'\*\*Category:\*\*\s*(\w+)', status_text)
        proposal["category"] = category_match.group(1) if category_match else "unknown"
    else:
        proposal["implemented"] = "UNKNOWN"
        proposal["verified"] = "UNKNOWN"
        proposal["category"] = "unknown"

    return proposal


def load_proposal_state():
    """Load the proposal state tracking file"""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    # Initialize empty state file if missing
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps({"reviews": {}, "last_review": None}, indent=2))
    return {"reviews": {}, "last_review": None}


def save_proposal_state(state):
    """Save proposal state"""
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def get_all_proposals():
    """Get all proposals with their state"""
    proposals = []
    for filepath in PROPOSALS_DIR.glob("*.md"):
        if filepath.name.startswith("."):
            continue
        proposal = parse_proposal_file(filepath)
        proposals.append(proposal)

    # Load state and merge
    state = load_proposal_state()
    for p in proposals:
        file_id = p["file"]
        if file_id in state.get("reviews", {}):
            p["review_status"] = state["reviews"][file_id].get("status", "pending")
            p["reviewed_at"] = state["reviews"][file_id].get("reviewed_at")
            p["task_created"] = state["reviews"][file_id].get("task_created")
        else:
            # Check the proposal's own Status section if no formal review exists
            if p.get("implemented") == "YES":
                p["review_status"] = "implemented"
            else:
                p["review_status"] = "pending"
            p["reviewed_at"] = None
            p["task_created"] = None

    # Sort by mtime, newest first
    proposals.sort(key=lambda p: p["mtime"], reverse=True)
    return proposals


def list_proposals(show_all=False):
    """List proposals with status"""
    proposals = get_all_proposals()

    if not proposals:
        print("No proposals found.")
        return

    print(f"\n{'='*80}")
    print(f"PROPOSALS ({len(proposals)} total)")
    print(f"{'='*80}\n")

    # Filter to pending unless show_all
    to_show = proposals if show_all else [p for p in proposals if p["review_status"] == "pending"]

    for p in to_show:
        age = datetime.now() - p["mtime"]
        age_str = f"{age.seconds//3600}h ago" if age.days == 0 else f"{age.days}d ago"

        status_color = {
            "pending": "⏳",
            "approved": "✅",
            "rejected": "❌",
            "implemented": "✨",
        }.get(p["review_status"], "?")

        print(f"{status_color} {p['file']}")
        print(f"   Agent: {p['agent']} | Domain: {p['domain']} | Age: {age_str}")
        print(f"   Title: {p['title'][:70]}")

        if p["review_status"] != "pending":
            print(f"   Status: {p['review_status'].upper()}")
        if p.get("task_created"):
            print(f"   Task: {p['task_created']}")

        print()


def show_stale_proposals():
    """Show proposals >24h old without action"""
    proposals = get_all_proposals()
    stale = [p for p in proposals if p["review_status"] == "pending" and (datetime.now() - p["mtime"]) > timedelta(hours=24)]

    if not stale:
        print("\n✓ No stale proposals (>24h pending)")
        return

    print(f"\n⚠️  STALE PROPOSALS ({len(stale)} proposals >24h old)")
    print("="*60)

    for p in stale:
        age = datetime.now() - p["mtime"]
        print(f"\n{p['file']} — {age.days}d old")
        print(f"   {p['agent']}: {p['title'][:60]}")

    print(f"\nThese proposals need review. Run: python3 proposal_lifecycle.py --review")


def approve_proposal(proposal_id, target_agent=None):
    """Approve a proposal and create a task"""
    proposals = get_all_proposals()

    # Find proposal by file name or partial match
    proposal = None
    for p in proposals:
        if proposal_id in p["file"]:
            proposal = p
            break

    if not proposal:
        print(f"Proposal not found: {proposal_id}")
        return False

    # Read the full proposal for task creation
    content = Path(proposal["path"]).read_text()

    # Determine target agent for task
    # If not specified, use the proposal author or infer from domain
    task_agent = target_agent or proposal["agent"]

    # Extract problem and solution for task
    problem_match = re.search(r'## Problem\s*\n(.*?)(?=## |$)', content, re.DOTALL)
    solution_match = re.search(r'## Solution\s*\n(.*?)(?=## |$)', content, re.DOTALL)

    problem = problem_match.group(1).strip() if problem_match else "See proposal file"
    solution = solution_match.group(1).strip() if solution_match else "See proposal file"

    # Create task file
    task_dir = Path(__file__).parent.parent / task_agent / "tasks"
    task_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    task_file = task_dir / f"proposal-{proposal['file'].replace('.md', '')}-{timestamp}.md"

    task_content = f"""# Task: Implement Proposal — {proposal['title']}

**Source:** Proposal from {proposal['agent']} ({proposal['file']})
**Created:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Domain:** {proposal['domain']}
**Priority:** MEDIUM

## Problem

{problem[:500]}

## Proposed Solution

{solution[:1000]}

## Requirements

1. Read the full proposal at: `{proposal['path']}`
2. Implement the solution as described
3. Verify the implementation works
4. Update the proposal's Status section to mark Implemented/Verified

## Deliverables

- [ ] Implementation complete
- [ ] Verification testing done
- [ ] Proposal status updated
"""

    task_file.write_text(task_content)

    # Update state
    state = load_proposal_state()
    if "reviews" not in state:
        state["reviews"] = {}
    state["reviews"][proposal["file"]] = {
        "status": "approved",
        "reviewed_at": datetime.now().isoformat(),
        "task_created": str(task_file),
    }
    save_proposal_state(state)

    print(f"✅ Proposal approved: {proposal['file']}")
    print(f"   Task created: {task_file}")
    print(f"   Assigned to: {task_agent}")

    return True


def reject_proposal(proposal_id, reason=""):
    """Reject a proposal"""
    proposals = get_all_proposals()

    proposal = None
    for p in proposals:
        if proposal_id in p["file"]:
            proposal = p
            break

    if not proposal:
        print(f"Proposal not found: {proposal_id}")
        return False

    # Update state
    state = load_proposal_state()
    if "reviews" not in state:
        state["reviews"] = {}
    state["reviews"][proposal["file"]] = {
        "status": "rejected",
        "reviewed_at": datetime.now().isoformat(),
        "reason": reason,
    }
    save_proposal_state(state)

    print(f"❌ Proposal rejected: {proposal['file']}")
    if reason:
        print(f"   Reason: {reason}")

    return True


def main():
    parser = argparse.ArgumentParser(description='Proposal lifecycle tracker')
    parser.add_argument('--list', '-l', action='store_true', help='List all proposals')
    parser.add_argument('--all', '-a', action='store_true', help='Show all proposals (including reviewed)')
    parser.add_argument('--stale', action='store_true', help='Show proposals >24h old without action')
    parser.add_argument('--approve', metavar='ID', help='Approve a proposal (partial filename)')
    parser.add_argument('--reject', metavar='ID', help='Reject a proposal (partial filename)')
    parser.add_argument('--agent', help='Target agent for approved proposal task')
    parser.add_argument('--reason', help='Reason for rejection')

    args = parser.parse_args()

    if args.stale:
        show_stale_proposals()
    elif args.approve:
        approve_proposal(args.approve, args.agent)
    elif args.reject:
        reject_proposal(args.reject, args.reason or "")
    elif args.list or args.all:
        list_proposals(show_all=args.all)
    else:
        # Default: show pending proposals
        list_proposals(show_all=False)


if __name__ == "__main__":
    main()
