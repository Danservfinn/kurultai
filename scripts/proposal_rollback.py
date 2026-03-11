#!/usr/bin/env python3
"""
Proposal Rollback Manager for Kurultai agents.

Implements automatic rollback capability for proposals that
encounter critical errors or Also provides manual rollback for debugging.

Usage:
    from proposal_rollback import ProposalRollback, RollbackResult

    rollback = ProposalRollback(neo4j_driver=driver)
    result = rollback.check_error_rate(proposal_id)
    if result and not result.success:
        print("Error rate OK")
    else:
        rollback.execute_rollback(proposal_id, "Critical errors detected")
"""

import os
import json
import logging
import subprocess
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from pathlib import Path
from dataclasses import dataclass

from neo4j import GraphDatabase

logger = logging.getLogger(__name__)

# Paths
SCRIPTS_DIR = Path('/Users/kublai/.openclaw/agents/main/scripts')
LEDGER_PATH = Path('/Users/kublai/.openclaw/tasks/task-ledger.jsonl')


@dataclass
class RollbackResult:
    """Result of a rollback operation."""
    success: bool
    proposal_id: str
    previous_state: Dict[str, Any]
    restored_files: List[str]
    errors: List[str]


class ProposalRollback:
    """
    Manages automatic rollback for proposals.

    Monitors error rates after implementation and triggers rollback
    if critical errors detected.
    """

    def __init__(
        self,
        neo4j_driver=None,
        error_threshold: int = 5,
        time_threshold_hours: int = 1,
        restore_timeout_seconds: int = 30
    ):
        self.neo4j_driver = neo4j_driver
        self.error_threshold = error_threshold
        self.time_threshold_hours = time_threshold_hours
        self.restore_timeout_seconds = restore_timeout_seconds
        self._check_interval: int = 300  # 5 minutes

        self._restore_state: Dict[str, Dict[str, Any]] = {}
        self._check_times: Dict[str, datetime] = {}

    def _load_state(self, proposal_id: str) -> Dict[str, Any]:
        """Load previous rollback state from file."""
        state_file = SCRIPTS_DIR / f'rollback_state_{proposal_id}.json'
        if state_file.exists():
            with open(state_file, 'r') as f:
                return json.load(f)
        return {}

    def _save_state(self, proposal_id: str, state: Dict[str, Any]) -> None:
        """Save current rollback state to file."""
        state_file = SCRIPTS_DIR / f'rollback_state_{proposal_id}.json'
        if state_file.exists():
            state_file.unlink()
        with open(state_file, 'w') as f:
            json.dump(state, f, indent=2)

    def check_error_rate(
        self,
        proposal_id: str,
        baseline_error_rate: Optional[float] = None
    ) -> Optional[RollbackResult]:
        """
        Check error rate after proposal implementation.

        Queries Neo4j for tasks completed after the proposal
        and calculates error rate baseline.

        Args:
            proposal_id: The proposal ID to check
            baseline_error_rate: Optional baseline rate (0.0-1.0). If not provided, uses stored threshold

        Returns:
            RollbackResult with success=True if under threshold
        """
        if self.neo4j_driver is None:
            return None

        try:
            with self.neo4j_driver.session() as session:
                # Get all completed tasks for this proposal
                result = session.run("""
                    MATCH (t:Task {status: 'COMPLETED'})
                    WHERE t.metadata.reflection_proposal_id = $proposal_id
                    RETURN t
                """)
                tasks = list(result)

                if not tasks:
                    return RollbackResult(
                        success=True,
                        proposal_id=proposal_id,
                        previous_state={},
                        restored_files=[],
                        errors=[]
                    )

                # Calculate error rate (only tasks with errors)
                errors = []
                for t in tasks:
                    metadata = t.get('metadata', {})
                    if metadata and metadata.get('error'):
                        errors.append(metadata['error'])

                total_errors = len(errors)

                # Calculate error rate
                baseline = baseline_error_rate or 0.0 if baseline_error_rate else 0
                current_rate = total_errors / len(tasks)

                if current_rate > self.error_threshold:
                    logger.warning(
                        f"Error rate {current_rate:.2%} exceeds threshold {self.error_threshold}"
                    )
                    return RollbackResult(
                        success=False,
                        proposal_id=proposal_id,
                        previous_state=self._load_state(proposal_id),
                        restored_files=[],
                        errors=errors
                    )

                return RollbackResult(
                    success=True,
                    proposal_id=proposal_id,
                    previous_state=self._load_state(proposal_id),
                    restored_files=[],
                    errors=[]
                )

        except Exception as e:
            logger.error(f"Error checking error rate: {e}")
            return None

    def execute_rollback(
        self,
        proposal_id: str,
        reason: str,
        commit_message: Optional[str] = None
    ) -> Optional[RollbackResult]:
        """
        Execute rollback for a proposal.

        1. Load previous state
        2. Update proposal status to ROLLED_BACK
        3. Restore affected files from git
        4. Log rollback event
        """
        # Load previous state
        previous_state = self._load_state(proposal_id)
        if not previous_state:
            previous_state = {"restored_files": [], "errors": []}

        restored_files = []
        errors = []

        # Get proposal details from Neo4j
        if self.neo4j_driver:
            try:
                with self.neo4j_driver.session() as session:
                    result = session.run("""
                        MATCH (p:ReflectionProposal {proposal_id: $proposal_id})
                        RETURN p
                    """)
                    record = result.single()

                    if record:
                        proposal = dict(record['p'])
                        commit_sha = proposal.get('commit_sha')

                        # Update status
                        session.run("""
                            MATCH (p:ReflectionProposal {proposal_id: $proposal_id})
                            SET p.status = 'ROLLED_BACK',
                                p.rolled_back_at = datetime(),
                                p.rollback_reason = $reason
                        """)
            except Exception as e:
                logger.error(f"Failed to update Neo4j: {e}")
                errors.append(str(e))

        # Restore affected files
        if commit_sha:
            try:
                # Git revert
                result = subprocess.run(
                    ['git', 'revert', '--no-commit', commit_sha],
                    cwd=SCRIPTS_DIR.parent.parent,
                    capture_output=True,
                    text=True,
                    timeout=self.restore_timeout_seconds
                )

                if result.returncode == 0:
                    restored_files = result.stdout.split('\n')
                else:
                    logger.warning(f"Git revert failed: {result.stderr}")
            except Exception as e:
                logger.error(f"Failed to restore files: {e}")
                errors.append(str(e))

        # Clean up state file
        state_file = SCRIPTS_DIR / f'rollback_state_{proposal_id}.json'
        if state_file.exists():
            state_file.unlink()

        # Log rollback event to ledger
        try:
            event = {
                "event": "proposal_rollback",
                "proposal_id": proposal_id,
                "reason": reason,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "restored_files": restored_files,
                "errors": [str(e) for e in errors]
            }
            with open(LEDGER_PATH, 'a') as f:
                f.write(json.dumps(event) + '\n')
        except Exception as e:
            logger.error(f"Failed to write rollback event to ledger: {e}")

        return RollbackResult(
            success=len(errors) == 0,
            proposal_id=proposal_id,
            previous_state=previous_state,
            restored_files=restored_files,
            errors=errors
        )

    def get_proposal(self, proposal_id: str) -> Optional[Dict[str, Any]]:
        """Get a proposal by ID from Neo4j."""
        if not self.neo4j_driver:
            return None

        try:
            with self.neo4j_driver.session() as session:
                result = session.run("""
                    MATCH (p:ReflectionProposal {proposal_id: $proposal_id})
                    RETURN p
                """)
                record = result.single()
                if record:
                    return dict(record['p'])
        except Exception as e:
            logger.error(f"Failed to get proposal: {e}")
            return None


if __name__ == "__main__":
    print("Testing Proposal Rollback...")

    # Note: This would normally use a real Neo4j connection
    print("Skipping Neo4j tests (no connection)")

    print("\nDone!")
