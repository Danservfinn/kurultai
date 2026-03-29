#!/usr/bin/env python3
"""
pipeline_monitor.py — Consensus check and pipeline advancement for reflection pipelines.

This script has two modes:
1. --consensus {pid}: Run consensus check for a specific pipeline (called by sentinel task)
2. --check-stalled: Scan for stalled pipelines and advance them (cron every 15min)

Consensus logic:
- Queries all voting task outputs from Neo4j (phase=4)
- Tallies APPROVE/REJECT votes per proposal
- For 6/6 APPROVE proposals: creates approval task with dispatch_phase='awaiting_approval'
- Logs rejected proposals

Usage:
    python3 pipeline_monitor.py --consensus reflection-2026-03-23
    python3 pipeline_monitor.py --check-stalled
    python3 pipeline_monitor.py --status reflection-2026-03-23
"""

import os
import sys
import json
import argparse
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_v2_core import TaskStore
from agents_config import AGENTS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# Number of agents in the Kurultai
AGENT_COUNT = len(AGENTS)  # Should be 6

# Phase definitions
PHASE_VOTING = 4
PHASE_CONSENSUS = 5
PHASE_APPROVAL = 6

# Stalled threshold (minutes)
STALL_THRESHOLD_MIN = 30


def get_proposal_outputs(store: TaskStore, pipeline_id: str) -> dict:
    """Fetch all proposal task outputs from Neo4j.

    Returns dict mapping task_id -> proposal content.
    """
    with store.driver.session() as s:
        result = s.run("""
            MATCH (t:Task {pipeline_id: $pid, phase: 3, domain: 'proposal'})
            OPTIONAL MATCH (t)-[:HAS_OUTPUT]->(o:TaskOutput)
            RETURN t.task_id AS task_id,
                   t.title AS title,
                   t.assigned_to AS proposer,
                   o.text AS output_text,
                   o.solution AS solution,
                   o.rationale AS rationale
        """, pid=pipeline_id)

        proposals = {}
        for rec in result:
            tid = rec["task_id"]
            proposals[tid] = {
                "task_id": tid,
                "title": rec["title"],
                "proposer": rec["proposer"],
                "output_text": rec["output_text"] or "",
                "solution": rec["solution"] or "",
                "rationale": rec["rationale"] or ""
            }
        return proposals


def get_voting_outputs(store: TaskStore, pipeline_id: str) -> list[dict]:
    """Fetch all voting task outputs from Neo4j.

    Returns list of vote dicts with voter, votes mapping.
    """
    with store.driver.session() as s:
        result = s.run("""
            MATCH (t:Task {pipeline_id: $pid, phase: 4, domain: 'voting'})
            OPTIONAL MATCH (t)-[:HAS_OUTPUT]->(o:TaskOutput)
            RETURN t.task_id AS task_id,
                   t.assigned_to AS voter,
                   o.text AS output_text
        """, pid=pipeline_id)

        votes = []
        for rec in result:
            output_text = rec["output_text"] or "{}"
            try:
                vote_data = json.loads(output_text)
            except json.JSONDecodeError:
                # Try to extract JSON from text
                import re
                json_match = re.search(r'\{[\s\S]*\}', output_text)
                if json_match:
                    try:
                        vote_data = json.loads(json_match.group())
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse votes from {rec['task_id']}")
                        vote_data = {"votes": {}}
                else:
                    logger.warning(f"No JSON found in voting output {rec['task_id']}")
                    vote_data = {"votes": {}}

            votes.append({
                "task_id": rec["task_id"],
                "voter": rec["voter"],
                "vote_data": vote_data
            })
        return votes


def tally_votes(votes: list[dict], proposals: dict) -> dict:
    """Tally votes per proposal.

    Returns dict mapping proposal_task_id -> {
        'proposal': {...},
        'tally': {'APPROVE': N, 'REJECT': M},
        'voters': {'agent': 'APPROVE'|'REJECT', ...},
        'reasons': {'agent': 'reason', ...}
    }
    """
    tally = {}

    # Initialize tally for each proposal
    for prop_id, prop_data in proposals.items():
        tally[prop_id] = {
            "proposal": prop_data,
            "tally": {"APPROVE": 0, "REJECT": 0, "ABSTAIN": 0},
            "voters": {},
            "reasons": {}
        }

    # Count votes
    for vote_entry in votes:
        voter = vote_entry["voter"]
        vote_data = vote_entry["vote_data"]

        for prop_id, vote_info in vote_data.get("votes", {}).items():
            if prop_id not in tally:
                logger.warning(f"Vote for unknown proposal {prop_id}")
                continue

            vote = vote_info.get("vote", "ABSTAIN").upper()
            reason = vote_info.get("reason", "")

            if vote in ("APPROVE", "REJECT", "ABSTAIN"):
                tally[prop_id]["tally"][vote] += 1
                tally[prop_id]["voters"][voter] = vote
                tally[prop_id]["reasons"][voter] = reason

    return tally


def create_approval_task(store: TaskStore, pipeline_id: str, proposal_id: str,
                         proposal_data: dict, vote_summary: dict) -> dict:
    """Create an approval task for a unanimously approved proposal.

    Task will have dispatch_phase='awaiting_approval' and appear in
    the 'Awaiting Approval' column on the kanban.
    """
    task_id = f"{pipeline_id}-approve-{proposal_id.split('-')[-1]}"

    # Build the task prompt with full proposal content
    proposal_text = f"""
# Proposal: {proposal_data['title']}

**Proposer:** {proposal_data['proposer']}

## Proposal Content
{proposal_data['output_text']}

## Solution
{proposal_data['solution']}

## Rationale
{proposal_data['rationale']}

---
## Vote Tally
- **APPROVE:** {vote_summary['tally']['APPROVE']}/{AGENT_COUNT}
- **REJECT:** {vote_summary['tally']['REJECT']}/{AGENT_COUNT}

### Voter Reasons:
""".strip()

    for voter, reason in vote_summary['reasons'].items():
        vote = vote_summary['voters'].get(voter, '?')
        proposal_text += f"\n- **{voter}** ({vote}): {reason}"

    # Create the approval task
    task = store.create_task(
        task_id=task_id,
        title=f"APPROVAL: {proposal_data['title']}",
        prompt=proposal_text,
        assigned_to="ogedei",  # Ops agent handles approval routing
        priority="high",
        domain="approval",
        source="consensus",
        pipeline_id=pipeline_id,
        phase=PHASE_APPROVAL,
        max_retries=0,  # Human approval - no auto-retry
        timeout_s=86400,  # 24 hours for human review
    )

    # Set dispatch_phase to 'awaiting_approval' for kanban visibility
    with store.driver.session() as s:
        s.run("""
            MATCH (t:Task {task_id: $tid})
            SET t.dispatch_phase = 'awaiting_approval'
        """, tid=task_id)

    return task


def run_consensus_check(store: TaskStore, pipeline_id: str, dry_run: bool = False) -> dict:
    """Run the full consensus check for a pipeline.

    Returns summary dict with approved/rejected counts.
    """
    logger.info(f"Running consensus check for pipeline {pipeline_id}")

    # Fetch proposals and votes
    proposals = get_proposal_outputs(store, pipeline_id)
    if not proposals:
        logger.warning(f"No proposals found for pipeline {pipeline_id}")
        return {"approved": 0, "rejected": 0, "error": "no_proposals"}

    votes = get_voting_outputs(store, pipeline_id)
    if not votes:
        logger.warning(f"No votes found for pipeline {pipeline_id}")
        return {"approved": 0, "rejected": 0, "error": "no_votes"}

    logger.info(f"Found {len(proposals)} proposals and {len(votes)} votes")

    # Tally votes
    tally = tally_votes(votes, proposals)

    # Process each proposal
    approved_count = 0
    rejected_count = 0
    results = []

    for prop_id, tally_data in tally.items():
        approve_votes = tally_data["tally"]["APPROVE"]
        reject_votes = tally_data["tally"]["REJECT"]
        abstain_votes = tally_data["tally"].get("ABSTAIN", 0)
        total_votes = approve_votes + reject_votes + abstain_votes

        # Quorum check: need at least 4 actual votes per proposal
        quorum_met = total_votes >= 4
        tally_data["quorum_met"] = quorum_met
        if not quorum_met:
            logger.warning(f"Quorum not met for {prop_id}: {total_votes}/6 votes")

        logger.info(f"Proposal {prop_id}: {approve_votes}/{AGENT_COUNT} APPROVE, "
                    f"{reject_votes}/{AGENT_COUNT} REJECT, "
                    f"{abstain_votes}/{AGENT_COUNT} ABSTAIN")

        result = {
            "proposal_id": prop_id,
            "title": tally_data["proposal"]["title"],
            "proposer": tally_data["proposal"]["proposer"],
            "approve_votes": approve_votes,
            "reject_votes": reject_votes,
            "abstain_votes": abstain_votes,
            "quorum_met": quorum_met,
            "voters": tally_data["voters"],
            "status": "rejected"
        }

        # Unanimous approval = 6/6 APPROVE + 0 ABSTAIN + quorum met
        if (approve_votes == AGENT_COUNT
                and abstain_votes == 0
                and quorum_met):
            result["status"] = "unanimous_approval"
            approved_count += 1

            if not dry_run:
                # Create approval task
                approval_task = create_approval_task(
                    store, pipeline_id, prop_id,
                    tally_data["proposal"], tally_data
                )
                result["approval_task_id"] = approval_task["task_id"]
                logger.info(f"Created approval task {approval_task['task_id']} for {prop_id}")
        elif not quorum_met:
            result["status"] = "quorum_not_met"
            rejected_count += 1
            logger.info(f"Proposal {prop_id} inconclusive: quorum not met ({total_votes}/6 votes)")
        else:
            rejected_count += 1
            logger.info(f"Proposal {prop_id} rejected: {approve_votes}/{AGENT_COUNT} APPROVE (need {AGENT_COUNT}/{AGENT_COUNT})")

        results.append(result)

    return {
        "pipeline_id": pipeline_id,
        "approved": approved_count,
        "rejected": rejected_count,
        "total_proposals": len(proposals),
        "results": results,
        "dry_run": dry_run
    }


def complete_consensus_sentinel(store: TaskStore, pipeline_id: str, result: dict) -> bool:
    """Mark the consensus sentinel task as complete with summary output."""
    sentinel_task_id = f"{pipeline_id}-consensus"

    # First, get the sentinel task to claim it
    with store.driver.session() as s:
        rec = s.run("""
            MATCH (t:Task {task_id: $tid})
            RETURN t.task_id AS tid, t.claim_epoch AS epoch, t.status AS status
        """, tid=sentinel_task_id).single()

        if not rec:
            logger.warning(f"Sentinel task {sentinel_task_id} not found")
            return False

        status = rec["status"]
        epoch = rec["epoch"] or 0

        if status == "COMPLETED":
            logger.info(f"Sentinel task {sentinel_task_id} already completed")
            return True

        if status != "WORKING":
            # Claim it first
            s.run("""
                MATCH (t:Task {task_id: $tid})
                SET t.status = 'WORKING',
                    t.claim_epoch = coalesce(t.claim_epoch, 0) + 1,
                    t.claimed_by = 'pipeline_monitor',
                    t.started_at = datetime(),
                    t.updated_at = datetime()
            """, tid=sentinel_task_id)
            epoch = (epoch or 0) + 1

    # Build completion summary
    summary_lines = [
        f"Consensus check completed for pipeline {pipeline_id}",
        f"",
        f"## Summary",
        f"- **Approved (unanimous):** {result['approved']}",
        f"- **Rejected:** {result['rejected']}",
        f"- **Total proposals:** {result['total_proposals']}",
        f"",
        f"## Results",
    ]

    for r in result.get("results", []):
        status_icon = "✅" if r["status"] == "unanimous_approval" else "❌"
        summary_lines.append(
            f"- {status_icon} **{r['title']}** ({r['proposer']}): "
            f"{r['approve_votes']}/{AGENT_COUNT} APPROVE"
        )
        if r.get("approval_task_id"):
            summary_lines.append(f"  - Approval task: `{r['approval_task_id']}`")

    summary_text = "\n".join(summary_lines)

    # Complete the sentinel task
    ok, reason = store.complete_task(
        sentinel_task_id, epoch,
        text=summary_text,
        problem=f"Process {result['total_proposals']} proposals for consensus",
        solution=f"Created {result['approved']} approval tasks, rejected {result['rejected']} proposals",
        rationale="Unanimous (6/6) approval required for human sign-off"
    )

    if ok:
        logger.info(f"Completed sentinel task {sentinel_task_id}")
    else:
        logger.warning(f"Failed to complete sentinel task: {reason}")

    return ok


def check_stalled_pipelines(store: TaskStore) -> list[dict]:
    """Scan for stalled pipelines and advance them.

    A pipeline is stalled if:
    - All voting tasks (phase 4) are COMPLETED
    - But consensus task (phase 5) is not COMPLETED
    - And consensus task has been pending/working for > STALL_THRESHOLD_MIN

    Returns list of pipelines that were advanced.
    """
    logger.info("Checking for stalled pipelines...")
    advanced = []

    with store.driver.session() as s:
        # Find pipelines where voting is complete but consensus is stuck
        result = s.run("""
            // Find pipelines with completed voting phase
            MATCH (vote_task:Task)
            WHERE vote_task.phase = 4 AND vote_task.status = 'COMPLETED'
            WITH vote_task.pipeline_id AS pid, count(vote_task) AS vote_count
            WHERE vote_count >= $min_votes

            // Check if consensus task exists and is stalled
            MATCH (consensus:Task {pipeline_id: pid, phase: 5})
            WHERE consensus.status IN ['PENDING', 'WORKING', 'BLOCKED']
              AND (consensus.updated_at IS NULL
                   OR consensus.updated_at < datetime() - duration({minutes: $threshold}))

            RETURN pid, consensus.task_id AS consensus_id, consensus.status AS status,
                   consensus.updated_at AS updated_at
        """, min_votes=AGENT_COUNT, threshold=STALL_THRESHOLD_MIN)

        stalled = [dict(rec) for rec in result]

    if not stalled:
        logger.info("No stalled pipelines found")
        return []

    logger.info(f"Found {len(stalled)} stalled pipelines")

    for stall in stalled:
        pid = stall["pid"]
        logger.info(f"Advancing stalled pipeline {pid} (status={stall['status']})")

        try:
            # Run consensus check for this pipeline
            result = run_consensus_check(store, pid)

            # Complete the sentinel task
            complete_consensus_sentinel(store, pid, result)

            advanced.append({
                "pipeline_id": pid,
                "status": "advanced",
                "result": result
            })
        except Exception as e:
            logger.error(f"Failed to advance pipeline {pid}: {e}")
            advanced.append({
                "pipeline_id": pid,
                "status": "error",
                "error": str(e)
            })

    return advanced


def get_pipeline_status(store: TaskStore, pipeline_id: str) -> dict:
    """Get detailed status of a pipeline's voting and consensus state."""
    with store.driver.session() as s:
        # Get all tasks in the pipeline
        result = s.run("""
            MATCH (t:Task {pipeline_id: $pid})
            WHERE t.phase >= 3
            RETURN t.task_id AS id, t.title AS title, t.status AS status,
                   t.phase AS phase, t.domain AS domain, t.assigned_to AS agent
            ORDER BY t.phase, t.created_at
        """, pid=pipeline_id)
        tasks = [dict(rec) for rec in result]

        # Count by phase/status
        summary = {}
        for t in tasks:
            phase = t["phase"]
            status = t["status"]
            key = f"phase_{phase}_{status}"
            summary[key] = summary.get(key, 0) + 1

    return {
        "pipeline_id": pipeline_id,
        "tasks": tasks,
        "summary": summary
    }


def main():
    parser = argparse.ArgumentParser(
        description="Pipeline monitor for consensus checks and stalled pipeline recovery"
    )
    parser.add_argument(
        "--consensus", metavar="PIPELINE_ID",
        help="Run consensus check for a specific pipeline"
    )
    parser.add_argument(
        "--check-stalled", action="store_true",
        help="Scan for stalled pipelines and advance them (cron mode)"
    )
    parser.add_argument(
        "--status", metavar="PIPELINE_ID",
        help="Get status of a pipeline's voting/consensus state"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would happen without making changes"
    )
    parser.add_argument(
        "--complete-sentinel", action="store_true",
        help="Also complete the sentinel task after consensus check"
    )
    args = parser.parse_args()

    store = TaskStore()

    try:
        if args.consensus:
            result = run_consensus_check(store, args.consensus, dry_run=args.dry_run)

            print(f"\n{'='*60}")
            print(f"Consensus Check: {args.consensus}")
            print(f"{'='*60}")
            print(f"Approved (unanimous): {result['approved']}")
            print(f"Rejected: {result['rejected']}")
            print(f"Total proposals: {result['total_proposals']}")
            print()

            for r in result.get("results", []):
                status = "✅ APPROVED" if r["status"] == "unanimous_approval" else "❌ REJECTED"
                print(f"  {status}: {r['title']} ({r['proposer']})")
                print(f"           {r['approve_votes']}/{AGENT_COUNT} APPROVE, {r['reject_votes']}/{AGENT_COUNT} REJECT")
                if r.get("approval_task_id"):
                    print(f"           Approval task: {r['approval_task_id']}")

            if args.complete_sentinel and not args.dry_run:
                complete_consensus_sentinel(store, args.consensus, result)
                print(f"\nSentinel task completed.")

        elif args.check_stalled:
            advanced = check_stalled_pipelines(store)
            print(f"\nChecked for stalled pipelines:")
            print(f"  Advanced: {len([a for a in advanced if a['status'] == 'advanced'])}")
            print(f"  Errors: {len([a for a in advanced if a['status'] == 'error'])}")

            for a in advanced:
                print(f"  - {a['pipeline_id']}: {a['status']}")

        elif args.status:
            status = get_pipeline_status(store, args.status)
            print(f"\nPipeline: {args.status}")
            print(f"{'='*60}")

            phase_names = {
                3: "Proposals",
                4: "Voting",
                5: "Consensus",
                6: "Approval"
            }

            current_phase = None
            for t in status["tasks"]:
                phase = t["phase"]
                if phase != current_phase:
                    current_phase = phase
                    print(f"\n## Phase {phase}: {phase_names.get(phase, 'Unknown')}")

                print(f"  [{t['status']:9s}] {t['title']} ({t['agent']})")

        else:
            parser.print_help()
            print("\nExamples:")
            print("  # Run consensus check for today's pipeline")
            print("  python3 pipeline_monitor.py --consensus reflection-2026-03-23 --complete-sentinel")
            print()
            print("  # Check for stalled pipelines (cron every 15min)")
            print("  python3 pipeline_monitor.py --check-stalled")
            print()
            print("  # Get pipeline status")
            print("  python3 pipeline_monitor.py --status reflection-2026-03-23")

    finally:
        store.close()


if __name__ == "__main__":
    main()
