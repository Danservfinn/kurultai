#!/usr/bin/env python3
"""
Reflection Proposal Tracker for Kurultai agents.

Implements state machine and lifecycle tracking for proposals
generated during agent reflection cycles.

Usage:
    from reflection_proposal_tracker import (
        ReflectionProposalTracker,
        ProposalStatus,
        ProposalLifecycle
    )
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Set
from enum import Enum
from dataclasses import dataclass, field
from pathlib import Path
import uuid

logger = logging.getLogger(__name__)

LEDGER_PATH = Path('/Users/kublai/.openclaw/tasks/task-ledger.jsonl')


class ProposalStatus(str, Enum):
    """Valid states for a reflection proposal."""
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    IMPLEMENTING = "IMPLEMENTING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


class ProposalLifecycle:
    """State machine for reflection proposals."""

    VALID_TRANSITIONS: Dict[ProposalStatus, Set[ProposalStatus]] = {
        ProposalStatus.PROPOSED: {ProposalStatus.APPROVED, ProposalStatus.REJECTED},
        ProposalStatus.APPROVED: {ProposalStatus.IMPLEMENTING},
        ProposalStatus.IMPLEMENTING: {ProposalStatus.VERIFIED, ProposalStatus.FAILED},
        ProposalStatus.FAILED: {ProposalStatus.ROLLED_BACK},
    }

    @classmethod
    def can_transition(cls, from_state: ProposalStatus, to_state: ProposalStatus) -> bool:
        """Check if transition is valid."""
        return to_state in cls.VALID_TRANSITIONS.get(from_state, set())


@dataclass
class ReflectionProposal:
    """Represents a reflection proposal in the system."""
    proposal_id: str
    title: str
    description: str
    source_agent: str
    created_at: datetime
    status: ProposalStatus = ProposalStatus.PROPOSED
    approved_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    implementation_task_id: Optional[str] = None
    commit_sha: Optional[str] = None
    implemented_at: Optional[datetime] = None
    verified_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    failure_reason: Optional[str] = None
    rolled_back_at: Optional[datetime] = None
    rollback_reason: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert proposal to dictionary."""
        return {
            'proposal_id': self.proposal_id,
            'title': self.title,
            'description': self.description,
            'source_agent': self.source_agent,
            'created_at': self.created_at.isoformat(),
            'status': self.status.value,
            'approved_at': self.approved_at.isoformat() if self.approved_at else None,
            'approved_by': self.approved_by,
            'implementation_task_id': self.implementation_task_id,
            'commit_sha': self.commit_sha,
            'implemented_at': self.implemented_at.isoformat() if self.implemented_at else None,
            'verified_at': self.verified_at.isoformat() if self.verified_at else None,
            'failed_at': self.failed_at.isoformat() if self.failed_at else None,
            'failure_reason': self.failure_reason,
            'rolled_back_at': self.rolled_back_at.isoformat() if self.rolled_back_at else None,
            'rollback_reason': self.rollback_reason,
            'metrics': self.metrics or {}
        }


class ReflectionProposalTracker:
    """Manages reflection proposals with lifecycle tracking."""

    def __init__(self, neo4j_driver=None):
        self.neo4j_driver = neo4j_driver
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Ensure Neo4j has required indexes and constraints."""
        if self.neo4j_driver is None:
            return

        try:
            indexes = [
                "CREATE INDEX proposal_status_idx IF NOT EXISTS FOR (p:Proposal) ON (p.status)",
                "CREATE INDEX proposal_created_idx IF NOT EXISTS FOR (p:Proposal) ON (p.created_at)",
                "CREATE INDEX proposal_agent_idx IF NOT EXISTS FOR (p:Proposal) ON (p.source_agent)",
            ]

            with self.neo4j_driver.session() as session:
                for idx in indexes:
                    try:
                        session.run(idx)
                    except Exception as e:
                        if "already exists" not in str(e).lower():
                            logger.warning(f"Index creation warning: {e}")
        except Exception as e:
            logger.error(f"Schema initialization failed: {e}")

    def create_proposal(
        self,
        title: str,
        description: str,
        source_agent: str
    ) -> Optional[ReflectionProposal]:
        """Create a new reflection proposal."""
        proposal = ReflectionProposal(
            proposal_id=self._generate_id(),
            title=title,
            description=description,
            source_agent=source_agent,
            created_at=datetime.now(timezone.utc),
            status=ProposalStatus.PROPOSED
        )

        # Persist to ledger
        self._write_to_ledger({
            'event': 'PROPOSAL_CREATED',
            'proposal_id': proposal.proposal_id,
            'title': title,
            'source_agent': source_agent,
            'timestamp': proposal.created_at.isoformat(),
        })

        # Persist to Neo4j
        if self.neo4j_driver:
            try:
                with self.neo4j_driver.session() as session:
                    session.run("""
                        CREATE (p:ReflectionProposal {
                            proposal_id: $proposal_id,
                            title: $title,
                            description: $description,
                            source_agent: $source_agent,
                            status: $status,
                            created_at: datetime($created_at)
                        })
                    """,
                    proposal_id=proposal.proposal_id,
                    title=title,
                    description=description,
                    source_agent=source_agent,
                    status=proposal.status.value,
                    created_at=proposal.created_at.isoformat()
                )
            except Exception as e:
                logger.error(f"Failed to create proposal in Neo4j: {e}")
                return None

        return proposal

    def approve_proposal(
        self,
        proposal_id: str,
        approved_by: str = "auto"
    ) -> bool:
        """Approve a proposal for implementation."""
        proposal = self._get_proposal(proposal_id)
        if proposal is None:
            logger.error(f"Proposal not found: {proposal_id}")
            return False

        if not ProposalLifecycle.can_transition(proposal.status, ProposalStatus.APPROVED):
            logger.warning(f"Invalid transition: {proposal.status} -> APPROVED")
            return False

        proposal.status = ProposalStatus.APPROVED
        proposal.approved_at = datetime.now(timezone.utc)
        proposal.approved_by = approved_by

        # Update in Neo4j
        if self.neo4j_driver:
            try:
                with self.neo4j_driver.session() as session:
                    session.run("""
                        MATCH (p:ReflectionProposal {proposal_id: $proposal_id})
                        SET p.status = $status,
                            p.approved_at = datetime($approved_at),
                            p.approved_by = $approved_by
                    """,
                    proposal_id=proposal_id,
                    status=proposal.status.value,
                    approved_at=proposal.approved_at.isoformat(),
                    approved_by=approved_by
                )
            except Exception as e:
                logger.error(f"Failed to update proposal in Neo4j: {e}")

        # Write to ledger
        self._write_to_ledger({
            'event': 'PROPOSAL_APPROVED',
            'proposal_id': proposal_id,
            'approved_by': approved_by,
            'timestamp': proposal.approved_at.isoformat(),
        })

        return True

    def start_implementation(
        self,
        proposal_id: str,
        task_id: str
    ) -> bool:
        """Mark proposal as implementing with linked task."""
        proposal = self._get_proposal(proposal_id)
        if proposal is None:
            logger.error(f"Proposal not found: {proposal_id}")
            return False

        if not ProposalLifecycle.can_transition(proposal.status, ProposalStatus.IMPLEMENTING):
            logger.warning(f"Invalid transition: {proposal.status} -> IMPLEMENTING")
            return False

        proposal.status = ProposalStatus.IMPLEMENTING
        proposal.implementation_task_id = task_id

        # Update in Neo4j
        if self.neo4j_driver:
            try:
                with self.neo4j_driver.session() as session:
                    session.run("""
                        MATCH (p:ReflectionProposal {proposal_id: $proposal_id})
                        SET p.status = $status,
                            p.implementation_task_id = $task_id
                    """,
                    proposal_id=proposal_id,
                    status=proposal.status.value,
                    task_id=task_id
                )
                    # Create IMPLEMENTED_BY relationship
                    session.run("""
                        MATCH (t:Task {task_id: $task_id})
                        MATCH (p:ReflectionProposal {proposal_id: $proposal_id})
                        MERGE (p)-[:IMPLEMENTED_BY]->(t)
                    """,
                    task_id=task_id,
                    proposal_id=proposal_id
                )
            except Exception as e:
                logger.error(f"Failed to update proposal in Neo4j: {e}")

        # Write to ledger
        self._write_to_ledger({
            'event': 'PROPOSAL_IMPLEMENTING',
            'proposal_id': proposal_id,
            'task_id': task_id,
            'timestamp': datetime.now(timezone.utc).isoformat(),
        })

        return True

    def complete_implementation(
        self,
        proposal_id: str,
        commit_sha: str
    ) -> bool:
        """Mark proposal as verified with commit reference."""
        proposal = self._get_proposal(proposal_id)
        if proposal is None:
            logger.error(f"Proposal not found: {proposal_id}")
            return False

        if not ProposalLifecycle.can_transition(proposal.status, ProposalStatus.VERIFIED):
            logger.warning(f"Invalid transition: {proposal.status} -> VERIFIED")
            return False

        proposal.status = ProposalStatus.VERIFIED
        proposal.verified_at = datetime.now(timezone.utc)
        proposal.commit_sha = commit_sha

        # Update in Neo4j
        if self.neo4j_driver:
            try:
                with self.neo4j_driver.session() as session:
                    session.run("""
                        MATCH (p:ReflectionProposal {proposal_id: $proposal_id})
                        SET p.status = $status,
                            p.verified_at = datetime($verified_at),
                            p.commit_sha = $commit_sha
                    """,
                    proposal_id=proposal_id,
                    status=proposal.status.value,
                    verified_at=proposal.verified_at.isoformat(),
                    commit_sha=commit_sha
                )
            except Exception as e:
                logger.error(f"Failed to update proposal in Neo4j: {e}")

        # Write to ledger
        self._write_to_ledger({
            'event': 'PROPOSAL_VERIFIED',
            'proposal_id': proposal_id,
            'commit_sha': commit_sha,
            'timestamp': proposal.verified_at.isoformat(),
        })

        return True

    def fail_implementation(
        self,
        proposal_id: str,
        reason: str
    ) -> bool:
        """Mark proposal as failed."""
        proposal = self._get_proposal(proposal_id)
        if proposal is None:
            logger.error(f"Proposal not found: {proposal_id}")
            return False

        if not ProposalLifecycle.can_transition(proposal.status, ProposalStatus.FAILED):
            logger.warning(f"Invalid transition: {proposal.status} -> FAILED")
            return False

        proposal.status = ProposalStatus.FAILED
        proposal.failed_at = datetime.now(timezone.utc)
        proposal.failure_reason = reason

        # Update in Neo4j
        if self.neo4j_driver:
            try:
                with self.neo4j_driver.session() as session:
                    session.run("""
                        MATCH (p:ReflectionProposal {proposal_id: $proposal_id})
                        SET p.status = $status,
                            p.failed_at = datetime($failed_at),
                            p.failure_reason = $reason
                    """,
                    proposal_id=proposal_id,
                    status=proposal.status.value,
                    failed_at=proposal.failed_at.isoformat(),
                    reason=reason
                )
            except Exception as e:
                logger.error(f"Failed to update proposal in Neo4j: {e}")

        # Write to ledger
        self._write_to_ledger({
            'event': 'PROPOSAL_FAILED',
            'proposal_id': proposal_id,
            'reason': reason,
            'timestamp': proposal.failed_at.isoformat(),
        })

        return True

    def rollback_proposal(
        self,
        proposal_id: str,
        reason: str
    ) -> bool:
        """Rollback a failed proposal."""
        proposal = self._get_proposal(proposal_id)
        if proposal is None:
            logger.error(f"Proposal not found: {proposal_id}")
            return False

        if not ProposalLifecycle.can_transition(proposal.status, ProposalStatus.ROLLED_BACK):
            logger.warning(f"Invalid transition: {proposal.status} -> ROLLED_BACK")
            return False

        proposal.status = ProposalStatus.ROLLED_BACK
        proposal.rolled_back_at = datetime.now(timezone.utc)
        proposal.rollback_reason = reason

        # Update in Neo4j
        if self.neo4j_driver:
            try:
                with self.neo4j_driver.session() as session:
                    session.run("""
                        MATCH (p:ReflectionProposal {proposal_id: $proposal_id})
                        SET p.status = $status,
                            p.rolled_back_at = datetime($rolled_back_at),
                            p.rollback_reason = $reason
                    """,
                    proposal_id=proposal_id,
                    status=proposal.status.value,
                    rolled_back_at=proposal.rolled_back_at.isoformat(),
                    reason=reason
                )
            except Exception as e:
                logger.error(f"Failed to update proposal in Neo4j: {e}")

        # Write to ledger
        self._write_to_ledger({
            'event': 'PROPOSAL_ROLLED_BACK',
            'proposal_id': proposal_id,
            'reason': reason,
            'timestamp': proposal.rolled_back_at.isoformat(),
        })

        return True

    def get_proposal(self, proposal_id: str) -> Optional[ReflectionProposal]:
        """Get a proposal by ID."""
        return self._get_proposal(proposal_id)

    def _get_proposal(self, proposal_id: str) -> Optional[ReflectionProposal]:
        """Internal method to get proposal from Neo4j."""
        if self.neo4j_driver is None:
            return None

        try:
            with self.neo4j_driver.session() as session:
                result = session.run("""
                    MATCH (p:ReflectionProposal {proposal_id: $proposal_id})
                    RETURN p
                """,
                proposal_id=proposal_id
            )
                record = result.single()
                if record:
                    data = dict(record['p'])
                    return ReflectionProposal(
                        proposal_id=data.get('proposal_id'),
                        title=data.get('title'),
                        description=data.get('description'),
                        source_agent=data.get('source_agent'),
                        status=ProposalStatus(data.get('status')),
                        created_at=datetime.fromisoformat(data.get('created_at')),
                        approved_at=datetime.fromisoformat(data['approved_at']) if data.get('approved_at') else None,
                        approved_by=data.get('approved_by'),
                        implementation_task_id=data.get('implementation_task_id'),
                        commit_sha=data.get('commit_sha'),
                        implemented_at=datetime.fromisoformat(data['implemented_at']) if data.get('implemented_at') else None,
                        verified_at=datetime.fromisoformat(data['verified_at']) if data.get('verified_at') else None,
                        failed_at=datetime.fromisoformat(data['failed_at']) if data.get('failed_at') else None,
                        failure_reason=data.get('failure_reason'),
                        rolled_back_at=datetime.fromisoformat(data['rolled_back_at']) if data.get('rolled_back_at') else None,
                        rollback_reason=data.get('rollback_reason'),
                        metrics=data.get('metrics')
                    )
        except Exception as e:
            logger.error(f"Failed to get proposal from Neo4j: {e}")

        return None

    def get_active_proposals(self) -> List[ReflectionProposal]:
        """Get all proposals that are not terminal."""
        proposals = []

        if self.neo4j_driver:
            try:
                with self.neo4j_driver.session() as session:
                    result = session.run("""
                        MATCH (p:ReflectionProposal)
                        WHERE p.status IN ['PROPOSED', 'APPROVED', 'IMPLEMENTING']
                        RETURN p
                        ORDER BY p.created_at DESC
                    """)

                    for record in result:
                        proposals.append(self._record_to_proposal(record))
            except Exception as e:
                logger.error(f"Failed to get active proposals: {e}")

        return proposals

    def get_proposals_by_status(self, status: ProposalStatus) -> List[ReflectionProposal]:
        """Get proposals by status."""
        proposals = []

        if self.neo4j_driver:
            try:
                with self.neo4j_driver.session() as session:
                    result = session.run("""
                        MATCH (p:ReflectionProposal {status: $status})
                        RETURN p
                        ORDER BY p.created_at DESC
                    """,
                    status=status.value
                )

                    for record in result:
                        proposals.append(self._record_to_proposal(record))
            except Exception as e:
                logger.error(f"Failed to get proposals by status: {e}")

        return proposals

    def get_success_metrics(self, days: int = 7) -> Dict[str, Any]:
        """Get proposal success metrics for last N days."""
        if not self.neo4j_driver:
            return {}

        metrics = {
            'total_proposals': 0,
            'approved': 0,
            'verified': 0,
            'failed': 0,
            'rolled_back': 0,
            'success_rate': 0.0,
            'avg_implementation_time_hours': 0.0,
        }

        try:
            with self.neo4j_driver.session() as session:
                result = session.run("""
                    MATCH (p:ReflectionProposal)
                    WHERE p.created_at >= datetime() - duration({days: $days})
                    RETURN p.status as status,
                           p.created_at as created,
                           p.approved_at as approved,
                           p.verified_at as verified,
                           p.implemented_at as implemented
                    ORDER BY p.created_at DESC
                """,
                days=days
            )

                total = 0
                verified_count = 0
                failed_count = 0
                rolled_back_count = 0
                implementation_times = []

                for record in result:
                    total += 1
                    status = record['status']

                    if status == 'VERIFIED':
                        verified_count += 1
                    elif status == 'FAILED':
                        failed_count += 1
                    elif status == 'ROLLED_BACK':
                        rolled_back_count += 1

                    # Calculate implementation time
                    if record.get('approved') and record.get('implemented'):
                        try:
                            approved_dt = datetime.fromisoformat(record['approved'])
                            implemented_dt = datetime.fromisoformat(record['implemented'])
                            impl_time = (implemented_dt - approved_dt).total_seconds() / 3600
                            implementation_times.append(impl_time)
                        except:
                            pass

                metrics['total_proposals'] = total
                metrics['verified'] = verified_count
                metrics['failed'] = failed_count
                metrics['rolled_back'] = rolled_back_count

                if verified_count > 0 and (verified_count + failed_count) > 0:
                    metrics['success_rate'] = (verified_count / (verified_count + failed_count)) * 100

                if implementation_times:
                    metrics['avg_implementation_time_hours'] = sum(implementation_times) / len(implementation_times)

        except Exception as e:
            logger.error(f"Failed to get metrics: {e}")

        return metrics

    def _generate_id(self) -> str:
        """Generate a unique proposal ID."""
        return f"rp_{uuid.uuid4().hex[:8]}"

    def _write_to_ledger(self, event: Dict[str, Any]) -> None:
        """Write event to ledger file."""
        try:
            with open(LEDGER_PATH, 'a') as f:
                f.write(json.dumps(event) + '\n')
        except Exception as e:
            logger.error(f"Failed to write to ledger: {e}")

    def _record_to_proposal(self, record: Dict[str, Any]) -> ReflectionProposal:
        """Convert Neo4j record to Proposal object."""
        data = dict(record.get('p', {}))
        return ReflectionProposal(
            proposal_id=data.get('proposal_id'),
            title=data.get('title'),
            description=data.get('description'),
            source_agent=data.get('source_agent'),
            status=ProposalStatus(data.get('status')),
            created_at=datetime.fromisoformat(data.get('created_at')),
            approved_at=datetime.fromisoformat(data['approved_at']) if data.get('approved_at') else None,
            approved_by=data.get('approved_by'),
            implementation_task_id=data.get('implementation_task_id'),
            commit_sha=data.get('commit_sha'),
            implemented_at=datetime.fromisoformat(data['implemented_at']) if data.get('implemented_at') else None,
            verified_at=datetime.fromisoformat(data['verified_at']) if data.get('verified_at') else None,
            failed_at=datetime.fromisoformat(data['failed_at']) if data.get('failed_at') else None,
            failure_reason=data.get('failure_reason'),
            rolled_back_at=datetime.fromisoformat(data['rolled_back_at']) if data.get('rolled_back_at') else None,
            rollback_reason=data.get('rollback_reason'),
        )


if __name__ == "__main__":
    print("Testing Reflection Proposal Tracker...")

    # Test lifecycle
    print("\nValid transitions:")
    for from_state, transitions in ProposalLifecycle.VALID_TRANSITIONS.items():
        for to_state in transitions:
            can = ProposalLifecycle.can_transition(from_state, to_state)
            print(f"  {from_state.value} -> {to_state.value}: {can}")

    print("\nDone!")
