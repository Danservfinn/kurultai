#!/usr/bin/env python3
"""
Kurultai Proposal Utilities

Housekeeping for self-improvement proposals: listing, expiry, approval, rejection.
Kublai reviews proposals himself during agent sessions — this script provides
the CLI tools he uses to act on them.

Usage:
    python3 kurultai_review.py --list              # Show pending proposals
    python3 kurultai_review.py --expire            # Expire proposals older than 24h
    python3 kurultai_review.py --approve <id>      # Approve and create task
    python3 kurultai_review.py --reject <id> "reason"  # Reject with reason
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agents_config import AGENTS

BASE = Path.home() / ".openclaw/agents/main"
LOG_FILE = BASE / "logs/kurultai-review.log"

MAX_PENDING_PROPOSALS = 12
PROPOSAL_EXPIRY_HOURS = 24


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        os.makedirs(LOG_FILE.parent, exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def get_pending_proposals():
    """Fetch all pending brainstorm proposals from Neo4j."""
    try:
        from neo4j_task_tracker import get_driver

        driver = get_driver()
        with driver.session() as session:
            result = session.run("""
                MATCH (f:AgentFeedback)
                WHERE f.status = 'pending_review'
                  AND f.source = 'kurultai_brainstorm'
                RETURN f
                ORDER BY
                    CASE f.priority
                        WHEN 'CRITICAL' THEN 1
                        WHEN 'HIGH' THEN 2
                        WHEN 'MEDIUM' THEN 3
                        ELSE 4
                    END,
                    f.submitted DESC
            """)
            proposals = []
            for r in result:
                node = dict(r["f"])
                raw_proposals = node.get("proposals", "[]")
                if isinstance(raw_proposals, str):
                    try:
                        node["parsed_proposals"] = json.loads(raw_proposals)
                    except Exception:
                        node["parsed_proposals"] = []
                else:
                    node["parsed_proposals"] = raw_proposals if isinstance(raw_proposals, list) else []
                proposals.append(node)
        driver.close()
        return proposals
    except Exception as e:
        log(f"Failed to fetch proposals: {e}")
        return []


def expire_old_proposals():
    """Mark proposals older than 24h as expired."""
    try:
        from neo4j_task_tracker import get_driver

        driver = get_driver()
        with driver.session() as session:
            result = session.run("""
                MATCH (f:AgentFeedback)
                WHERE f.status = 'pending_review'
                  AND f.source = 'kurultai_brainstorm'
                  AND f.submitted < datetime() - duration({hours: $hours})
                SET f.status = 'expired',
                    f.reviewed_at = datetime(),
                    f.review_reason = 'Auto-expired after 24h'
                RETURN count(f) AS expired_count
            """, hours=PROPOSAL_EXPIRY_HOURS)
            count = result.single()["expired_count"]
            if count > 0:
                log(f"EXPIRED: {count} proposals older than {PROPOSAL_EXPIRY_HOURS}h")
        driver.close()
    except Exception as e:
        log(f"Failed to expire proposals: {e}")


def update_proposal_status(feedback_id, status, reason=""):
    """Update a proposal's status in Neo4j."""
    try:
        from neo4j_task_tracker import get_driver

        driver = get_driver()
        with driver.session() as session:
            session.run("""
                MATCH (f:AgentFeedback {id: $id})
                SET f.status = $status,
                    f.reviewed_at = datetime(),
                    f.review_reason = $reason
            """, id=feedback_id, status=status, reason=reason)
        driver.close()
        return True
    except Exception as e:
        log(f"Failed to update proposal {feedback_id}: {e}")
        return False


def create_task_for_proposal(agent, proposal):
    """Create a task via task_intake for an approved proposal."""
    try:
        from task_intake import create_task

        p = proposal.get("parsed_proposals", [{}])
        detail = p[0] if p else {}

        title = detail.get("proposal", proposal.get("feedback", "Self-improvement task"))[:80]
        body = f"""## Self-Improvement Proposal (Kurultai Brainstorm)

**Agent:** {agent}
**Category:** {detail.get('category', '?')}
**Effort:** {detail.get('effort', '?')}

**Problem:** {detail.get('problem', 'See proposal')}

**Solution:** {detail.get('solution', 'See proposal')}

**Expected Impact:** {detail.get('impact', 'Improved agent effectiveness')}

## Instructions
1. Implement the solution described above
2. Test the change
3. Report results
"""

        result = create_task(
            title=title,
            body=body,
            priority="normal",
            source="kurultai-proposal",
            agent=agent,
            depth=0,
        )

        if result:
            log(f"TASK CREATED: {agent} -> {title}")
            return True
        return False
    except Exception as e:
        log(f"Failed to create task for {agent}: {e}")
        return False


def approve_proposal(feedback_id):
    """Approve a proposal by ID: update status and create task."""
    proposals = get_pending_proposals()
    target = None
    for p in proposals:
        if p.get("id") == feedback_id:
            target = p
            break

    if not target:
        print(f"Proposal not found: {feedback_id}")
        return False

    agent = target.get("agent", "unknown")
    update_proposal_status(feedback_id, "approved", "Approved by Kublai")
    create_task_for_proposal(agent, target)
    return True


def reject_proposal(feedback_id, reason="Rejected by Kublai"):
    """Reject a proposal by ID."""
    update_proposal_status(feedback_id, "rejected", reason)
    log(f"REJECTED: {feedback_id} — {reason}")


def list_proposals():
    """List all pending proposals."""
    proposals = get_pending_proposals()
    if not proposals:
        print("No pending proposals.")
        return

    print(f"\nPending proposals: {len(proposals)}")
    print(f"{'='*70}")
    for p in proposals:
        agent = p.get("agent", "?")
        feedback = p.get("feedback", "?")[:60]
        priority = p.get("priority", "?")
        category = p.get("category", "?")
        effort = p.get("effort", "?")
        fid = p.get("id", "?")

        detail = (p.get("parsed_proposals") or [{}])[0] if p.get("parsed_proposals") else {}
        problem = detail.get("problem", "")[:80]
        solution = detail.get("solution", "")[:80]

        print(f"  [{priority}] {agent} — {feedback}")
        print(f"    Problem:  {problem}")
        print(f"    Solution: {solution}")
        print(f"    Category: {category} | Effort: {effort} | ID: {fid}")
        print()
    print(f"{'='*70}")


def main():
    parser = argparse.ArgumentParser(description="Kurultai Proposal Utilities")
    parser.add_argument("--list", action="store_true", help="List pending proposals")
    parser.add_argument("--expire", action="store_true", help="Expire proposals older than 24h")
    parser.add_argument("--approve", metavar="ID", help="Approve a proposal by ID")
    parser.add_argument("--reject", metavar="ID", help="Reject a proposal by ID")
    parser.add_argument("--reason", default="Rejected by Kublai", help="Rejection reason")
    args = parser.parse_args()

    if args.list:
        list_proposals()
    elif args.expire:
        expire_old_proposals()
    elif args.approve:
        approve_proposal(args.approve)
    elif args.reject:
        reject_proposal(args.reject, args.reason)
    else:
        # Default: just expire old proposals and list what's pending
        expire_old_proposals()
        list_proposals()


if __name__ == "__main__":
    main()
