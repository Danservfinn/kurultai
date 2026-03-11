#!/usr/bin/env python3
"""
Kurultai Voting Orchestration

Main orchestration script for the consensus-based Kurultai voting system.
Implements the 6-phase voting process:

PHASE 1: Individual Agent Proposals
PHASE 2: Presentation to Kurultai
PHASE 3: Voting (Consensus Required)
PHASE 4: Implementation (Only After Consensus)
PHASE 5: Tally Results
PHASE 6: Report Results

Historical Context:
In the authentic Mongolian Kurultai, the Great Khans could only make decisions
through consensus among all Khans. No single Khan could act unilaterally.
This system honors that tradition.

Usage:
    python3 kurultai_voting.py --phase <1-6>
    python3 kurultai_voting.py --full-cycle
    python3 kurultai_voting.py --status
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Kurultai paths
KURULTAI_ROOT = Path("/Users/kublai/.openclaw/agents/main")
SCRIPTS_DIR = KURULTAI_ROOT / "scripts"
PROPOSALS_DIR = KURULTAI_ROOT / "proposals"
PENDING_DIR = PROPOSALS_DIR / "pending"
VOTING_DIR = PROPOSALS_DIR / "voting"
APPROVED_DIR = PROPOSALS_DIR / "approved"
REJECTED_DIR = PROPOSALS_DIR / "rejected"
LOGS_DIR = KURULTAI_ROOT / "logs"
TASKS_DIR = KURULTAI_ROOT / "tasks"

# All Khans
ALL_KHANS = ["kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei"]

# Voting window in minutes
VOTING_WINDOW_MINUTES = 60


def ensure_directories():
    """Ensure all required directories exist."""
    for d in [PENDING_DIR, VOTING_DIR, APPROVED_DIR, REJECTED_DIR, LOGS_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def log_phase(phase: int, message: str, data: dict = None):
    """Log phase execution."""
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "phase": phase,
        "message": message,
        "data": data or {}
    }

    log_file = LOGS_DIR / "voting-cycle.jsonl"
    with open(log_file, 'a') as f:
        f.write(json.dumps(log_entry) + "\n")

    print(f"[Phase {phase}] {message}")


def run_script(script_name: str, args: List[str] = None) -> Tuple[int, str, str]:
    """Run a Python script and return exit code, stdout, stderr."""
    script_path = SCRIPTS_DIR / script_name
    cmd = ["python3", str(script_path)] + (args or [])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Timeout expired"
    except Exception as e:
        return -1, "", str(e)


# ============================================================================
# PHASE 1: Individual Agent Proposals
# ============================================================================

def phase1_generate_proposals() -> Dict[str, List[str]]:
    """
    Each Khan generates proposals based on their domain expertise.

    In the authentic Kurultai, each Khan brought forward proposals
    for improvements within their sphere of influence.
    """
    log_phase(1, "Starting proposal generation by all Khans")

    proposals_created = {}

    for agent in ALL_KHANS:
        # Check if agent has pending proposals already
        existing = list(PENDING_DIR.glob(f"{agent}-*.md"))
        if existing:
            log_phase(1, f"  {agent} has {len(existing)} pending proposals, skipping")
            proposals_created[agent] = [p.stem for p in existing]
            continue

        # CHANGE: Skip sample generation - only use real proposals from kurultai-reflect
        log_phase(1, f"  {agent}: No pending proposals (reflection may not have run)")
        proposals_created[agent] = []

    total = sum(len(p) for p in proposals_created.values())
    log_phase(1, f"Proposal generation complete: {total} total proposals")

    return proposals_created


# ============================================================================
# PHASE 2: Presentation to Kurultai
# ============================================================================

def phase2_present_proposals() -> List[dict]:
    """
    All proposals are shared with all Khans for review.

    In the authentic Kurultai, all proposals were publicly presented
    so every Khan could understand and evaluate them.
    """
    log_phase(2, "Presenting proposals to all Khans")

    proposals = []

    # Gather all pending proposals
    for f in PENDING_DIR.glob("*.md"):
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

            proposals.append({
                "id": f.stem,
                "agent": frontmatter.get("agent", "unknown"),
                "title": frontmatter.get("title", ""),
                "domain": frontmatter.get("domain", ""),
                "impact": frontmatter.get("impact", "medium")
            })
        except Exception as e:
            log_phase(2, f"Error reading {f}: {e}")

    log_phase(2, f"Presented {len(proposals)} proposals for review", {"proposals": [p["id"] for p in proposals]})

    return proposals


# ============================================================================
# PHASE 3: Voting (Consensus Required)
# ============================================================================

def phase3_start_voting() -> Dict[str, str]:
    """
    Start the voting process for all pending proposals.

    Each Khan votes on each proposal:
    - APPROVE = will implement
    - REJECT = blocks implementation (veto)
    - ABSTAIN = no opinion (does not block)

    UNANIMOUS CONSENT REQUIRED: All 6 Khans must APPROVE.
    """
    log_phase(3, "Starting voting for all pending proposals")

    voting_started = {}

    # Get all pending proposals
    pending = list(PENDING_DIR.glob("*.md"))

    for proposal_file in pending:
        proposal_id = proposal_file.stem

        # Start voting
        rc, stdout, stderr = run_script(
            "voting_manager.py",
            ["--action", "start-voting", "--proposal", proposal_id]
        )

        if rc == 0:
            voting_started[proposal_id] = "started"
            log_phase(3, f"  Voting started for {proposal_id}")
        else:
            voting_started[proposal_id] = f"failed: {stderr}"
            log_phase(3, f"  Failed to start voting for {proposal_id}: {stderr}")

    log_phase(3, f"Voting started for {len(voting_started)} proposals")

    return voting_started


def phase3_simulate_voting() -> Dict[str, dict]:
    """
    Simulate voting for testing purposes.

    In production, this would be replaced by actual agent voting.
    """
    log_phase(3, "Simulating votes for testing")

    votes_cast = {}

    # Get all proposals in voting
    for f in VOTING_DIR.glob("*.md"):
        if "-votes.json" in f.name:
            continue

        proposal_id = f.stem
        votes_cast[proposal_id] = {}

        # Each agent votes
        for agent in ALL_KHANS:
            # Simple simulation: approve with 80% probability
            import random
            vote = "APPROVE" if random.random() < 0.8 else "ABSTAIN"

            rc, stdout, stderr = run_script(
                "voting_manager.py",
                ["--action", "cast-vote", "--proposal", proposal_id, "--agent", agent, "--vote", vote]
            )

            if rc == 0:
                votes_cast[proposal_id][agent] = vote
            else:
                votes_cast[proposal_id][agent] = f"failed: {stderr}"

    return votes_cast


def diagnose_voting_issues() -> List[str]:
    """
    Diagnose why votes may not be cast.

    Returns a list of diagnostic messages explaining potential issues.
    """
    issues = []

    # Check if pending directory has proposals
    pending_proposals = list(PENDING_DIR.glob("*.md"))
    if not pending_proposals:
        issues.append("No proposals in pending directory - kurultai-reflect may not have run")

    # Check if voting directory has proposals
    voting_proposals = [f for f in VOTING_DIR.glob("*.md") if "-votes.json" not in f.name]
    if not voting_proposals:
        issues.append("No proposals in voting directory - phase3_start_voting may not have run")
    else:
        issues.append(f"Found {len(voting_proposals)} proposals in voting directory")

    # Check if votes files exist for voting proposals
    for p in voting_proposals:
        votes_file = VOTING_DIR / f"{p.stem}-votes.json"
        if not votes_file.exists():
            issues.append(f"No votes file for {p.stem} - simulate_voting may not have been called")
        else:
            try:
                with open(votes_file, 'r') as f:
                    votes_data = json.load(f)
                    vote_count = len(votes_data.get("votes", {}))
                    if vote_count == 0:
                        issues.append(f"Empty votes file for {p.stem}")
                    else:
                        issues.append(f"Votes file for {p.stem} has {vote_count} votes")
            except Exception as e:
                issues.append(f"Could not read votes file for {p.stem}: {e}")

    return issues


# ============================================================================
# PHASE 4: Implementation (Only After Consensus)
# ============================================================================

def phase4_check_consensus() -> Dict[str, dict]:
    """
    Check voting results and identify proposals with unanimous consent.

    Kublai creates tasks ONLY for proposals with 6/6 APPROVE votes.
    This is the authentic Mongolian Kurultai model - no unilateral action.
    """
    log_phase(4, "Checking consensus for all proposals in voting")

    results = {}

    # Get all proposals in voting
    for f in VOTING_DIR.glob("*.md"):
        if "-votes.json" in f.name:
            continue

        proposal_id = f.stem

        # Check if voting is complete
        rc, stdout, stderr = run_script(
            "voting_manager.py",
            ["--action", "check-status", "--proposal", proposal_id]
        )

        # Get vote tally
        rc2, stdout2, stderr2 = run_script(
            "voting_manager.py",
            ["--action", "tally", "--proposal", proposal_id]
        )

        try:
            tally = json.loads(stdout2) if rc2 == 0 else {}
        except json.JSONDecodeError:
            tally = {}

        results[proposal_id] = {
            "status": "checking",
            "tally": tally,
            "consensus": tally.get("APPROVE", 0) == 6,
            "vetoed": tally.get("REJECT", 0) > 0
        }

        log_phase(4, f"  {proposal_id}: APPROVE={tally.get('APPROVE', 0)}/6, REJECT={tally.get('REJECT', 0)}")

    # Identify approved proposals
    approved = [p for p, r in results.items() if r["consensus"]]
    vetoed = [p for p, r in results.items() if r["vetoed"]]

    log_phase(4, f"Consensus check complete: {len(approved)} approved, {len(vetoed)} vetoed")

    return results


def phase4_create_tasks_for_approved() -> List[str]:
    """
    Create implementation tasks for proposals with unanimous consent.

    Kublai ONLY creates tasks after 6/6 APPROVE votes.
    This enforces the consensus model.
    """
    log_phase(4, "Creating tasks for approved proposals")

    tasks_created = []

    # Get all approved proposals
    for f in APPROVED_DIR.glob("*.md"):
        proposal_id = f.stem

        # Read proposal to get details
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

            agent = frontmatter.get("agent", "temujin")
            domain = frontmatter.get("domain", "")

            # Create task file
            task_id = f"proposal-{proposal_id}"
            task_file = TASKS_DIR / f"normal-{int(datetime.now().timestamp())}-{task_id}.md"

            task_content = f"""---
task_id: {task_id}
agent: {agent}
priority: normal
created: {datetime.now().isoformat()}
source: kurultai_consensus
proposal_id: {proposal_id}
---

# Task: Implement Approved Proposal

This task was created after unanimous consent (6/6 APPROVE) from the Kurultai.

## Original Proposal
See: proposals/approved/{proposal_id}.md

## Agent
{agent}

## Domain
{domain}

## Instructions
Review the approved proposal and implement the solution described.
The proposal has passed consensus voting and is ready for implementation.
"""
            task_file.write_text(task_content)
            tasks_created.append(task_id)
            log_phase(4, f"  Created task {task_id} for proposal {proposal_id}")

        except Exception as e:
            log_phase(4, f"  Error creating task for {proposal_id}: {e}")

    log_phase(4, f"Task creation complete: {len(tasks_created)} tasks created")

    return tasks_created


# ============================================================================
# PHASE 5: Tally Results
# ============================================================================

def phase5_tally_results() -> dict:
    """
    Tally final results of all voting.
    """
    log_phase(5, "Tallying final results")

    results = {
        "approved": [],
        "rejected": [],
        "pending": [],
        "voting": []
    }

    # Check all directories
    for status, directory in [
        ("approved", APPROVED_DIR),
        ("rejected", REJECTED_DIR),
        ("pending", PENDING_DIR),
        ("voting", VOTING_DIR)
    ]:
        for f in directory.glob("*.md"):
            if "-votes.json" in f.name:
                continue

            results[status].append(f.stem)

    log_phase(5, f"Tally complete: {len(results['approved'])} approved, {len(results['rejected'])} rejected")

    return results


# ============================================================================
# PHASE 6: Report Results
# ============================================================================

def phase6_report() -> str:
    """
    Generate final report of the voting cycle.
    """
    log_phase(6, "Generating final report")

    # Run consensus tracker for report
    rc, stdout, stderr = run_script("consensus_tracker.py", ["--report"])

    if rc == 0:
        report = stdout
    else:
        report = f"Error generating report: {stderr}"

    # Write report to file
    report_file = LOGS_DIR / f"voting-report-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"
    report_file.write_text(report)

    log_phase(6, f"Report generated: {report_file}")

    return report


# ============================================================================
# Main Orchestration
# ============================================================================

def run_full_cycle(simulate: bool = False) -> dict:
    """Run the complete 6-phase voting cycle."""
    ensure_directories()

    cycle_start = datetime.now()
    results = {
        "start_time": cycle_start.isoformat(),
        "phases": {}
    }

    # Phase 1: Generate proposals
    results["phases"]["1"] = phase1_generate_proposals()

    # Phase 2: Present proposals
    results["phases"]["2"] = phase2_present_proposals()

    # Phase 3: Start voting
    results["phases"]["3_start"] = phase3_start_voting()

    if simulate:
        # Simulate voting for testing
        results["phases"]["3_votes"] = phase3_simulate_voting()

    # Phase 4: Check consensus
    results["phases"]["4"] = phase4_check_consensus()

    # Phase 5: Tally results
    results["phases"]["5"] = phase5_tally_results()

    # Phase 6: Report
    results["phases"]["6"] = phase6_report()

    cycle_end = datetime.now()
    results["end_time"] = cycle_end.isoformat()
    results["duration_seconds"] = (cycle_end - cycle_start).total_seconds()

    return results


def get_status() -> dict:
    """Get current status of the voting system."""
    ensure_directories()

    status = {
        "pending": len(list(PENDING_DIR.glob("*.md"))),
        "voting": len([f for f in VOTING_DIR.glob("*.md") if "-votes.json" not in f.name]),
        "approved": len(list(APPROVED_DIR.glob("*.md"))),
        "rejected": len(list(REJECTED_DIR.glob("*.md")))
    }

    return status


def run_diagnostics() -> None:
    """Run voting diagnostics and print results."""
    ensure_directories()
    print("\nKurultai Voting Diagnostics")
    print("=" * 40)

    issues = diagnose_voting_issues()
    for issue in issues:
        print(f"  - {issue}")

    status = get_status()
    print(f"\nCurrent Status:")
    print(f"  Pending:  {status['pending']}")
    print(f"  Voting:   {status['voting']}")
    print(f"  Approved: {status['approved']}")
    print(f"  Rejected: {status['rejected']}")


def main():
    parser = argparse.ArgumentParser(
        description="Kurultai consensus-based voting orchestration"
    )
    parser.add_argument("--phase", type=int, choices=[1, 2, 3, 4, 5, 6],
                       help="Run a specific phase")
    parser.add_argument("--full-cycle", action="store_true",
                       help="Run complete 6-phase cycle")
    parser.add_argument("--simulate", action="store_true",
                       help="Simulate voting for testing")
    parser.add_argument("--status", action="store_true",
                       help="Show current status")
    parser.add_argument("--diagnose", action="store_true",
                       help="Run voting diagnostics to understand why votes may be 0/6")

    args = parser.parse_args()

    ensure_directories()

    if args.diagnose:
        run_diagnostics()

    elif args.status:
        status = get_status()
        print(f"\nKurultai Voting Status")
        print(f"=====================")
        print(f"Pending:  {status['pending']}")
        print(f"Voting:   {status['voting']}")
        print(f"Approved: {status['approved']}")
        print(f"Rejected: {status['rejected']}")

    elif args.full_cycle:
        print("\n" + "="*60)
        print("KURULTAI CONSENSUS VOTING CYCLE")
        print("="*60 + "\n")

        results = run_full_cycle(simulate=args.simulate)

        print("\n" + "="*60)
        print("CYCLE COMPLETE")
        print(f"Duration: {results['duration_seconds']:.1f}s")
        print("="*60 + "\n")

    elif args.phase:
        if args.phase == 1:
            phase1_generate_proposals()
        elif args.phase == 2:
            phase2_present_proposals()
        elif args.phase == 3:
            phase3_start_voting()
        elif args.phase == 4:
            phase4_check_consensus()
        elif args.phase == 5:
            phase5_tally_results()
        elif args.phase == 6:
            phase6_report()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()