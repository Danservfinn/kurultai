#!/usr/bin/env python3
"""
kurultai_voting_approval.py — Handle human approve/reject for Kurultai proposals.

Called by signal_message_handler.py when owner sends "approve <id>" or "reject <id>".
Moves proposal from awaiting_approval/ to approved/ or rejected/, and creates
implementation tasks for approved proposals.
"""

import json
import logging
import re
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

KURULTAI_ROOT = Path("/Users/kublai/.openclaw/agents/main")
PROPOSALS_DIR = KURULTAI_ROOT / "proposals"
AWAITING_DIR = PROPOSALS_DIR / "awaiting_approval"
APPROVED_DIR = PROPOSALS_DIR / "approved"
REJECTED_DIR = PROPOSALS_DIR / "rejected"
LOGS_DIR = KURULTAI_ROOT / "logs"


def _log(message: str):
    """Log to voting cycle log."""
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "phase": "human_approval",
        "message": message,
    }
    log_file = LOGS_DIR / "voting-cycle.jsonl"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, 'a') as f:
        f.write(json.dumps(log_entry) + "\n")


def _set_proposal_status(proposal_id: str, status: str):
    """Update Neo4j AgentFeedback node status for the proposal."""
    try:
        import sys, os
        sys.path.insert(0, str(KURULTAI_ROOT / "scripts"))
        from neo4j_task_tracker import neo4j_session
        with neo4j_session() as session:
            session.run("""
                MATCH (af:AgentFeedback)
                WHERE af.proposal_id = $pid
                SET af.human_approval_status = $status,
                    af.human_approval_at = datetime()
            """, pid=proposal_id, status=status)
    except Exception as e:
        logger.warning(f"Failed to update Neo4j proposal status: {e}")


def _create_task_for_proposal(proposal_id: str):
    """Create an implementation task for an approved proposal.

    Delegates to kurultai_voting._create_task_for_proposal.
    """
    try:
        import sys, os
        sys.path.insert(0, str(KURULTAI_ROOT / "scripts"))
        from kurultai_voting import _create_task_for_proposal as _create
        _create(proposal_id)
    except Exception as e:
        logger.error(f"Failed to create task for {proposal_id}: {e}")
        _log(f"Task creation failed for {proposal_id}: {e}")


def handle_human_approval(proposal_id: str, action: str) -> str:
    """Process human approve/reject for a proposal.

    Moves proposal from awaiting_approval/ to approved/ or rejected/.
    If approved, creates the implementation task.

    Returns a response message string.
    """
    # Sanitize proposal_id — reject glob metacharacters
    if not re.match(r'^[a-zA-Z0-9_\-]+$', proposal_id):
        return f"Invalid proposal ID: {proposal_id}"

    AWAITING_DIR.mkdir(parents=True, exist_ok=True)
    APPROVED_DIR.mkdir(parents=True, exist_ok=True)
    REJECTED_DIR.mkdir(parents=True, exist_ok=True)

    # Verify Neo4j state before allowing approval
    try:
        import sys, os
        sys.path.insert(0, str(KURULTAI_ROOT / "scripts"))
        from neo4j_task_tracker import neo4j_session
        with neo4j_session() as session:
            result = session.run("""
                MATCH (af:AgentFeedback {proposal_id: $pid})
                RETURN af.human_approval_status AS status
            """, pid=proposal_id)
            rec = result.single()
            if rec and rec["status"] not in (None, "PENDING_HUMAN_APPROVAL"):
                return f"Proposal {proposal_id} not in valid approval state (status: {rec['status']})"
    except Exception:
        pass  # Fail open — filesystem is primary source of truth

    # Exact match instead of glob
    proposal_file = AWAITING_DIR / f"{proposal_id}.md"
    if not proposal_file.exists():
        return f"No proposal found awaiting approval with ID: {proposal_id}"

    if action == "approve":
        dest = APPROVED_DIR / proposal_file.name
        proposal_file.rename(dest)
        _set_proposal_status(proposal_id, "approved")
        _create_task_for_proposal(proposal_id)
        _log(f"Human APPROVED: {proposal_id}")
        return f"Approved: {proposal_id}\nTask created and queued for execution."

    elif action == "reject":
        dest = REJECTED_DIR / proposal_file.name
        proposal_file.rename(dest)
        _set_proposal_status(proposal_id, "rejected_by_human")
        _log(f"Human REJECTED: {proposal_id}")
        return f"Rejected: {proposal_id}\nProposal archived."

    return f"Unknown action: {action}. Use 'approve' or 'reject'."
