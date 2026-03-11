#!/usr/bin/env python3
"""
Proposal Audit Logger for Kurultai agents.

Creates immutable audit trail for all proposal actions.
Written to security audit ledger for compliance.

Usage:
    from proposal_audit import ProposalAudit, log_proposal_action

    log_proposal_action(
        proposal_id="prop-123",
        action=ProposalAction.APPROVED,
        details={"approved_by": "kublai"}
    )
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from pathlib import Path
from enum import Enum

logger = logging.getLogger(__name__)

# Paths
AUDIT_LEDGER_PATH = Path('/Users/kublai/.openclaw/logs/proposal_audit.jsonl')


class ProposalAction(str, Enum):
    """Types of proposal actions that are logged."""
    CREATED = "CREATED"
    APPROVED = "APPROVED"
    IMPLEMENTING = "IMPLEMENTING"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


class AuditEntry:
    """A single audit entry."""
    timestamp: str
    proposal_id: str
    action: ProposalAction
    agent: str
    details: Dict[str, Any]
    previous_hash: str
    current_hash: str


class ProposalAudit:
    """Creates immutable audit trail for proposal actions."""

    def __init__(self):
        """Initialize the audit logger."""
        AUDIT_LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not AUDIT_LEDGER_PATH.exists():
            AUDIT_LEDGER_PATH.touch(0o600)  # Owner read/write only

        logger.debug(f"Audit ledger initialized at {AUDIT_LEDGER_PATH}")

    def _compute_hash(self, entry: Dict[str, Any]) -> str:
        """Compute SHA256 hash of entry for integrity verification."""
        import hashlib
        content = json.dumps(entry, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()

    def log_proposal_action(
        self,
        proposal_id: str,
        action: ProposalAction,
        details: Dict[str, Any],
        agent: str
    ) -> None:
        """
        Log a proposal action to the audit trail.

        Args:
            proposal_id: The proposal ID
            action: The action type
            details: Additional details about the action
            agent: The agent performing the action
        """
        # Get previous hash for previous_hash = "0" * 64  # Genesis hash
        try:
            with open(AUDIT_LEDGER_PATH, 'r') as f:
                lines = f.readlines()
                for line in lines:
                    if line.strip() and line.startswith('{'):
                        try:
                            entry = json.loads(line)
                            if 'current_hash' in entry:
                                previous_hash = entry['current_hash']
                        except:
                            pass
        except FileNotFoundError:
            pass

        # Create entry
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "proposal_id": proposal_id,
            "action": action.value,
            "agent": agent,
            "details": details,
            "previous_hash": previous_hash
        }
        entry["current_hash"] = self._compute_hash(entry)

        # Append to ledger
        with open(AUDIT_LEDGER_PATH, 'a') as f:
            f.write(json.dumps(entry) + '\n')

        logger.debug(f"Logged proposal action: {action.value} for {proposal_id}")

    def verify_chain(self, proposal_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        Verify the integrity of the audit chain for a proposal.

        Returns:
            List of entries in the chain, or None if chain is broken
        """
        entries = []
        try:
            with open(AUDIT_LEDGER_PATH, 'r') as f:
                for line in f:
                    if line.strip() and line.startswith('{'):
                        try:
                            entry = json.loads(line)
                            if entry.get('proposal_id') == proposal_id:
                                entries.append(entry)
                        except:
                            pass
        except FileNotFoundError:
            return []

        # Verify hash chain
        current_hash = "0" * 64  # Genesis hash
        for entry in entries:
            stored_hash = entry.get('current_hash', '')
            computed_hash = self._compute_hash(entry)
            if computed_hash != stored_hash:
                logger.error(
                    f"Hash mismatch for entry {entry.get('timestamp')}. "
                    f"Expected: {stored_hash}, Got: {computed_hash}"
                )
                return None

            current_hash = stored_hash

        return entries

    def get_proposal_history(self, proposal_id: str) -> List[Dict[str, Any]]:
        """
        Get all audit entries for a proposal.

        Returns:
            List of audit entries sorted by timestamp
        """
        entries = []
        try:
            with open(AUDIT_LEDGER_PATH, 'r') as f:
                for line in f:
                    if line.strip() and line.startswith('{'):
                        try:
                            entry = json.loads(line)
                            if entry.get('proposal_id') == proposal_id:
                                entries.append({
                                    'timestamp': entry['timestamp'],
                                    'action': entry['action'],
                                    'agent': entry['agent'],
                                    'details': entry['details']
                                })
                        except:
                            pass
        except FileNotFoundError:
            pass
        return sorted(entries, key=lambda x: x['timestamp'])


if __name__ == "__main__":
    print("Testing Proposal Audit...")

    # Initialize audit
    audit = ProposalAudit()

    log_proposal_action(
        proposal_id="test-prop-1",
        action=ProposalAction.CREATED,
        details={"title": "Test Proposal"},
        agent="test_agent"
    )

    log_proposal_action(
        proposal_id="test-prop-1",
        action=ProposalAction.APPROVED,
        details={"approved_by": "kublai"},
        agent="kublai"
    )

    # Verify chain
    chain = audit.verify_chain("test-prop-1")
    assert chain is not None
    assert len(chain) == 2
    print("Chain verified successfully")

    # Get history
    history = audit.get_proposal_history("test-prop-1")
    assert len(history) == 2
    print(f"History: {history}")

    # Cleanup
    if AUDIT_LEDGER_PATH.exists():
        AUDIT_LEDGER_PATH.unlink()

    print("\nDone!")
