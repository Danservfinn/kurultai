#!/usr/bin/env python3
"""
Ögedei Vetting Handler - Operations Agent

Reviews ArchitectureProposals against SHIELD policies.
Validates resource requirements, checks for compliance,
approves or rejects with detailed reasoning.

Usage:
    python -m tools.kurultai.vetting_handlers --review-proposal prop-xxx
    python -m tools.kurultai.vetting_handlers --list-pending
    python -m tools.kurultai.vetting_handlers --batch-review

Author: Ögedei (Ops Agent)
Date: 2026-02-09
"""

import argparse
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Any, Set

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("kurultai.vetting_handlers")


class ProposalStatus(Enum):
    """Status values for ArchitectureProposal nodes."""
    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    IMPLEMENTING = "implementing"
    COMPLETED = "completed"


class VettingDecision(Enum):
    """Possible vetting decisions."""
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_CHANGES = "request_changes"
    NEEDS_DISCUSSION = "needs_discussion"


@dataclass
class PolicyViolation:
    """Represents a policy violation found during vetting."""
    policy_id: str
    policy_name: str
    severity: str  # critical, high, medium, low
    description: str
    recommendation: str


@dataclass
class ResourceEstimate:
    """Estimated resource requirements for a proposal."""
    tokens: int = 0
    memory_mb: int = 0
    cpu_seconds: int = 0
    neo4j_nodes: int = 0
    neo4j_relationships: int = 0
    external_api_calls: int = 0
    storage_mb: int = 0


@dataclass
class VettingResult:
    """Result of vetting a proposal."""
    proposal_id: str
    decision: VettingDecision
    confidence: float  # 0.0 - 1.0
    reasoning: str
    violations: List[PolicyViolation] = field(default_factory=list)
    resource_estimate: Optional[ResourceEstimate] = None
    warnings: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    vetted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    vetted_by: str = "ogedei"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "proposal_id": self.proposal_id,
            "decision": self.decision.value,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "violations": [
                {
                    "policy_id": v.policy_id,
                    "policy_name": v.policy_name,
                    "severity": v.severity,
                    "description": v.description,
                    "recommendation": v.recommendation
                }
                for v in self.violations
            ],
            "resource_estimate": {
                "tokens": self.resource_estimate.tokens if self.resource_estimate else 0,
                "memory_mb": self.resource_estimate.memory_mb if self.resource_estimate else 0,
                "cpu_seconds": self.resource_estimate.cpu_seconds if self.resource_estimate else 0,
                "neo4j_nodes": self.resource_estimate.neo4j_nodes if self.resource_estimate else 0,
                "neo4j_relationships": self.resource_estimate.neo4j_relationships if self.resource_estimate else 0,
                "external_api_calls": self.resource_estimate.external_api_calls if self.resource_estimate else 0,
                "storage_mb": self.resource_estimate.storage_mb if self.resource_estimate else 0,
            } if self.resource_estimate else None,
            "warnings": self.warnings,
            "suggestions": self.suggestions,
            "vetted_at": self.vetted_at.isoformat(),
            "vetted_by": self.vetted_by
        }


class ShieldPolicies:
    """
    SHIELD policy definitions and validation logic.
    
    SHIELD = Security Health Integrity Efficiency Limits Definitions
    """
    
    # Security Policies (S1.x)
    SECURITY_NO_SECRETS = "S1.1"
    SECURITY_INPUT_VALIDATION = "S1.2"
    SECURITY_RATE_LIMITING = "S1.3"
    SECURITY_AUTHENTICATION = "S1.4"
    SECURITY_ENCRYPTION = "S1.5"
    
    # Health Policies (H2.x)
    HEALTH_HEARTBEATS = "H2.1"
    HEALTH_DB_CONNECTIVITY = "H2.2"
    HEALTH_DISK_SPACE = "H2.3"
    HEALTH_MEMORY = "H2.4"
    
    # Integrity Policies (I3.x)
    INTEGRITY_SCHEMA_VALIDATION = "I3.1"
    INTEGRITY_DATA_CONSISTENCY = "I3.2"
    INTEGRITY_TASK_STATE = "I3.3"
    INTEGRITY_FILE_CONSISTENCY = "I3.4"
    
    # Efficiency Policies (E4.x)
    EFFICIENCY_TOKEN_BUDGETS = "E4.1"
    EFFICIENCY_TASK_PRIORITY = "E4.2"
    EFFICIENCY_RESOURCE_LIMITS = "E4.3"
    EFFICIENCY_PARALLELIZATION = "E4.4"
    
    # Limits Policies (L5.x)
    LIMITS_TASKS = "L5.1"
    LIMITS_STORAGE = "L5.2"
    LIMITS_API_RATE = "L5.3"
    LIMITS_MESSAGE_SIZE = "L5.4"
    
    # Policy definitions
    POLICIES = {
        # Security
        SECURITY_NO_SECRETS: {
            "name": "No Secrets in Code",
            "description": "No API keys, passwords, tokens, or secrets may be hardcoded in source code",
            "severity": "critical"
        },
        SECURITY_INPUT_VALIDATION: {
            "name": "Input Validation",
            "description": "All user inputs must be validated and sanitized",
            "severity": "high"
        },
        SECURITY_RATE_LIMITING: {
            "name": "Rate Limiting",
            "description": "All external-facing endpoints must have rate limiting",
            "severity": "high"
        },
        SECURITY_AUTHENTICATION: {
            "name": "Authentication",
            "description": "All administrative actions require authentication",
            "severity": "critical"
        },
        SECURITY_ENCRYPTION: {
            "name": "Data Encryption",
            "description": "Sensitive data must be encrypted at rest and in transit",
            "severity": "critical"
        },
        # Health
        HEALTH_HEARTBEATS: {
            "name": "Agent Heartbeats",
            "description": "All agents must report heartbeat every 5 minutes",
            "severity": "medium"
        },
        HEALTH_DB_CONNECTIVITY: {
            "name": "Database Connectivity",
            "description": "System must maintain Neo4j connection with retry logic",
            "severity": "high"
        },
        HEALTH_DISK_SPACE: {
            "name": "Disk Space",
            "description": "Minimum 20% free disk space required",
            "severity": "medium"
        },
        HEALTH_MEMORY: {
            "name": "Memory Usage",
            "description": "Container memory usage should not exceed 80%",
            "severity": "medium"
        },
        # Integrity
        INTEGRITY_SCHEMA_VALIDATION: {
            "name": "Schema Validation",
            "description": "All Neo4j schema changes require migration files",
            "severity": "high"
        },
        INTEGRITY_DATA_CONSISTENCY: {
            "name": "Data Consistency",
            "description": "Orphaned nodes must not persist > 24 hours",
            "severity": "medium"
        },
        INTEGRITY_TASK_STATE: {
            "name": "Task State Management",
            "description": "Task status transitions must be valid",
            "severity": "high"
        },
        INTEGRITY_FILE_CONSISTENCY: {
            "name": "File Consistency",
            "description": "All agent SOUL.md files must exist and be valid",
            "severity": "medium"
        },
        # Efficiency
        EFFICIENCY_TOKEN_BUDGETS: {
            "name": "Token Budgets",
            "description": "All automated tasks have token budgets (5min: 500, 15min: 1000, etc.)",
            "severity": "low"
        },
        EFFICIENCY_TASK_PRIORITY: {
            "name": "Task Prioritization",
            "description": "High-priority tasks must be processed first",
            "severity": "low"
        },
        EFFICIENCY_RESOURCE_LIMITS: {
            "name": "Resource Limits",
            "description": "Tasks must complete within CPU/memory/file descriptor limits",
            "severity": "medium"
        },
        EFFICIENCY_PARALLELIZATION: {
            "name": "Parallelization",
            "description": "Independent tasks should run in parallel (max 10 per agent)",
            "severity": "low"
        },
        # Limits
        LIMITS_TASKS: {
            "name": "Task Limits",
            "description": "Max 100 pending per sender, 1000 total system tasks",
            "severity": "high"
        },
        LIMITS_STORAGE: {
            "name": "Storage Limits",
            "description": "Neo4j limits: 200k nodes, 440k relationships, 8GB storage",
            "severity": "critical"
        },
        LIMITS_API_RATE: {
            "name": "API Rate Limits",
            "description": "External API calls are rate-limited",
            "severity": "medium"
        },
        LIMITS_MESSAGE_SIZE: {
            "name": "Message Size",
            "description": "Signal: 4000 chars, Task desc: 10000 chars, Research: 100000 chars",
            "severity": "low"
        }
    }
    
    # Resource limits
    TOKEN_BUDGETS = {
        5: 500,      # 5-minute tasks
        15: 1000,    # 15-minute tasks
        60: 2000,    # Hourly tasks
        360: 3000,   # 6-hour tasks
        1440: 5000,  # Daily tasks
        10080: 10000 # Weekly tasks
    }
    
    MAX_PENDING_PER_SENDER = 100
    MAX_TOTAL_TASKS = 1000
    MAX_NEO4J_NODES = 200000
    MAX_NEO4J_RELATIONSHIPS = 440000


class OgedeiVettingHandler:
    """
    Ögedei's vetting handler for ArchitectureProposals.
    
    Reviews proposals against SHIELD policies, validates resources,
    and makes approval/rejection decisions.
    """
    
    def __init__(self, neo4j_driver=None):
        self.driver = neo4j_driver
        self.policies = ShieldPolicies()
        
    def _get_driver(self):
        """Get or create Neo4j driver."""
        if self.driver is None:
            try:
                from neo4j import GraphDatabase
                uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
                user = os.environ.get("NEO4J_USER", "neo4j")
                password = os.environ.get("NEO4J_PASSWORD")
                
                if not password:
                    raise ValueError("NEO4J_PASSWORD environment variable not set")
                
                self.driver = GraphDatabase.driver(uri, auth=(user, password))
                logger.info(f"Connected to Neo4j at {uri}")
            except ImportError:
                logger.error("neo4j package not installed")
                raise
            except Exception as e:
                logger.error(f"Failed to connect to Neo4j: {e}")
                raise
        return self.driver
    
    def get_proposal(self, proposal_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch a proposal from Neo4j.
        
        Args:
            proposal_id: The proposal ID
            
        Returns:
            Proposal dictionary or None if not found
        """
        driver = self._get_driver()
        
        try:
            with driver.session() as session:
                result = session.run("""
                    MATCH (p:ArchitectureProposal {id: $proposal_id})
                    RETURN p {
                        .*,
                        type: 'ArchitectureProposal'
                    } as proposal
                """, {"proposal_id": proposal_id})
                
                record = result.single()
                if record:
                    return record["proposal"]
                
                # Try matching by partial ID
                result = session.run("""
                    MATCH (p:ArchitectureProposal)
                    WHERE p.id STARTS WITH $proposal_id
                    RETURN p {
                        .*,
                        type: 'ArchitectureProposal'
                    } as proposal
                    LIMIT 1
                """, {"proposal_id": proposal_id})
                
                record = result.single()
                if record:
                    return record["proposal"]
                    
        except Exception as e:
            logger.error(f"Error fetching proposal {proposal_id}: {e}")
        
        return None
    
    def list_pending_proposals(self) -> List[Dict[str, Any]]:
        """
        List all proposals awaiting review.
        
        Returns:
            List of proposal dictionaries
        """
        driver = self._get_driver()
        proposals = []
        
        try:
            with driver.session() as session:
                result = session.run("""
                    MATCH (p:ArchitectureProposal)
                    WHERE p.status IN ['submitted', 'under_review']
                    RETURN p {
                        .*,
                        type: 'ArchitectureProposal'
                    } as proposal
                    ORDER BY p.priority DESC, p.created_at ASC
                """)
                
                for record in result:
                    proposals.append(record["proposal"])
                    
        except Exception as e:
            logger.error(f"Error listing pending proposals: {e}")
        
        return proposals
    
    def _estimate_resources(self, proposal: Dict[str, Any]) -> ResourceEstimate:
        """
        Estimate resource requirements from proposal content.
        
        Args:
            proposal: Proposal dictionary
            
        Returns:
            ResourceEstimate
        """
        estimate = ResourceEstimate()
        
        # Extract text content
        title = proposal.get("title", "")
        description = proposal.get("description", "")
        content = f"{title} {description}"
        
        # Estimate tokens based on content length
        # Rough estimate: 1 token ≈ 4 characters
        content_tokens = len(content) // 4
        
        # Check for explicit resource mentions
        token_match = re.search(r'(\d+)\s*tokens?', content, re.I)
        if token_match:
            estimate.tokens = int(token_match.group(1))
        else:
            # Default based on complexity indicators
            if "migration" in content.lower():
                estimate.tokens = 1500
            elif "schema" in content.lower():
                estimate.tokens = 1000
            elif "endpoint" in content.lower():
                estimate.tokens = 800
            elif "test" in content.lower():
                estimate.tokens = 600
            else:
                estimate.tokens = max(500, content_tokens)
        
        # Memory estimate
        if "large" in content.lower() or "heavy" in content.lower():
            estimate.memory_mb = 1024
        elif "medium" in content.lower():
            estimate.memory_mb = 512
        else:
            estimate.memory_mb = 256
        
        # CPU estimate
        cpu_match = re.search(r'(\d+)\s*(?:min|minute)', content, re.I)
        if cpu_match:
            estimate.cpu_seconds = int(cpu_match.group(1)) * 60
        else:
            estimate.cpu_seconds = 300  # Default 5 minutes
        
        # Neo4j estimates
        if "node" in content.lower():
            node_match = re.search(r'(\d+)\s*nodes?', content, re.I)
            if node_match:
                estimate.neo4j_nodes = int(node_match.group(1))
            else:
                estimate.neo4j_nodes = 100
        
        if "relationship" in content.lower():
            rel_match = re.search(r'(\d+)\s*relationships?', content, re.I)
            if rel_match:
                estimate.neo4j_relationships = int(rel_match.group(1))
            else:
                estimate.neo4j_relationships = 200
        
        # API calls
        if "api" in content.lower() or "integration" in content.lower():
            estimate.external_api_calls = 100
        
        # Storage
        storage_match = re.search(r'(\d+)\s*(MB|GB)', content, re.I)
        if storage_match:
            size = int(storage_match.group(1))
            unit = storage_match.group(2).upper()
            estimate.storage_mb = size if unit == "MB" else size * 1024
        
        return estimate
    
    def _check_security_policies(self, proposal: Dict[str, Any]) -> List[PolicyViolation]:
        """
        Check proposal against security policies.
        
        Args:
            proposal: Proposal dictionary
            
        Returns:
            List of policy violations
        """
        violations = []
        content = f"{proposal.get('title', '')} {proposal.get('description', '')}"
        content_lower = content.lower()
        
        # S1.1: No Secrets in Code
        secret_patterns = [
            r'password\s*=\s*["\'][^"\']+["\']',
            r'api[_-]?\s*key\s*=\s*["\'][^"\']+["\']',
            r'token\s*=\s*["\'][^"\']+["\']',
            r'secret\s*=\s*["\'][^"\']+["\']',
        ]
        for pattern in secret_patterns:
            if re.search(pattern, content_lower):
                violations.append(PolicyViolation(
                    policy_id=ShieldPolicies.SECURITY_NO_SECRETS,
                    policy_name=self.policies.POLICIES[ShieldPolicies.SECURITY_NO_SECRETS]["name"],
                    severity="critical",
                    description="Potential hardcoded secret found in proposal",
                    recommendation="Use environment variables or secret management"
                ))
                break
        
        # S1.2: Input Validation
        if "user input" in content_lower or "endpoint" in content_lower:
            if "validate" not in content_lower and "sanitize" not in content_lower:
                violations.append(PolicyViolation(
                    policy_id=ShieldPolicies.SECURITY_INPUT_VALIDATION,
                    policy_name=self.policies.POLICIES[ShieldPolicies.SECURITY_INPUT_VALIDATION]["name"],
                    severity="high",
                    description="User input handling without explicit validation",
                    recommendation="Add input validation and sanitization"
                ))
        
        # S1.3: Rate Limiting
        if "api" in content_lower or "endpoint" in content_lower:
            if "rate limit" not in content_lower:
                violations.append(PolicyViolation(
                    policy_id=ShieldPolicies.SECURITY_RATE_LIMITING,
                    policy_name=self.policies.POLICIES[ShieldPolicies.SECURITY_RATE_LIMITING]["name"],
                    severity="medium",
                    description="API endpoint without rate limiting mentioned",
                    recommendation="Add rate limiting configuration"
                ))
        
        # S1.4: Authentication
        if "admin" in content_lower or "delete" in content_lower or "modify" in content_lower:
            if "auth" not in content_lower:
                violations.append(PolicyViolation(
                    policy_id=ShieldPolicies.SECURITY_AUTHENTICATION,
                    policy_name=self.policies.POLICIES[ShieldPolicies.SECURITY_AUTHENTICATION]["name"],
                    severity="critical",
                    description="Administrative action without authentication requirement",
                    recommendation="Require authentication for administrative actions"
                ))
        
        return violations
    
    def _check_efficiency_policies(self, proposal: Dict[str, Any], 
                                   estimate: ResourceEstimate) -> List[PolicyViolation]:
        """
        Check proposal against efficiency policies.
        
        Args:
            proposal: Proposal dictionary
            estimate: Resource estimate
            
        Returns:
            List of policy violations
        """
        violations = []
        
        # E4.1: Token Budgets
        # Determine expected frequency from content
        content_lower = proposal.get("description", "").lower()
        frequency = 60  # Default hourly
        
        if "5 min" in content_lower or "five minute" in content_lower:
            frequency = 5
        elif "15 min" in content_lower:
            frequency = 15
        elif "hour" in content_lower:
            frequency = 60
        elif "day" in content_lower:
            frequency = 1440
        elif "week" in content_lower:
            frequency = 10080
        
        budget = self.policies.TOKEN_BUDGETS.get(frequency, 2000)
        
        if estimate.tokens > budget:
            violations.append(PolicyViolation(
                policy_id=ShieldPolicies.EFFICIENCY_TOKEN_BUDGETS,
                policy_name=self.policies.POLICIES[ShieldPolicies.EFFICIENCY_TOKEN_BUDGETS]["name"],
                severity="medium",
                description=f"Estimated {estimate.tokens} tokens exceeds {budget} budget for {frequency}min tasks",
                recommendation=f"Reduce scope or increase interval (current budget: {budget} tokens)"
            ))
        
        # E4.3: Resource Limits
        if estimate.memory_mb > 2048:
            violations.append(PolicyViolation(
                policy_id=ShieldPolicies.EFFICIENCY_RESOURCE_LIMITS,
                policy_name=self.policies.POLICIES[ShieldPolicies.EFFICIENCY_RESOURCE_LIMITS]["name"],
                severity="medium",
                description=f"Estimated {estimate.memory_mb}MB memory exceeds 2GB limit",
                recommendation="Optimize memory usage or split into smaller tasks"
            ))
        
        return violations
    
    def _check_limits_policies(self, proposal: Dict[str, Any],
                               estimate: ResourceEstimate) -> List[PolicyViolation]:
        """
        Check proposal against limits policies.
        
        Args:
            proposal: Proposal dictionary
            estimate: Resource estimate
            
        Returns:
            List of policy violations
        """
        violations = []
        
        # L5.2: Storage Limits
        driver = self._get_driver()
        
        try:
            with driver.session() as session:
                # Check current node count
                result = session.run("""
                    MATCH (n) 
                    RETURN count(n) as node_count
                """)
                current_nodes = result.single()["node_count"]
                
                projected_nodes = current_nodes + estimate.neo4j_nodes
                if projected_nodes > self.policies.MAX_NEO4J_NODES:
                    violations.append(PolicyViolation(
                        policy_id=ShieldPolicies.LIMITS_STORAGE,
                        policy_name=self.policies.POLICIES[ShieldPolicies.LIMITS_STORAGE]["name"],
                        severity="critical",
                        description=f"Projected {projected_nodes} nodes exceeds limit of {self.policies.MAX_NEO4J_NODES}",
                        recommendation="Archive old data or upgrade Neo4j tier"
                    ))
                
                # Check current relationship count
                result = session.run("""
                    MATCH ()-[r]->() 
                    RETURN count(r) as rel_count
                """)
                current_rels = result.single()["rel_count"]
                
                projected_rels = current_rels + estimate.neo4j_relationships
                if projected_rels > self.policies.MAX_NEO4J_RELATIONSHIPS:
                    violations.append(PolicyViolation(
                        policy_id=ShieldPolicies.LIMITS_STORAGE,
                        policy_name=self.policies.POLICIES[ShieldPolicies.LIMITS_STORAGE]["name"],
                        severity="critical",
                        description=f"Projected {projected_rels} relationships exceeds limit of {self.policies.MAX_NEO4J_RELATIONSHIPS}",
                        recommendation="Archive old data or upgrade Neo4j tier"
                    ))
                    
        except Exception as e:
            logger.warning(f"Could not check storage limits: {e}")
        
        return violations
    
    def _check_integrity_policies(self, proposal: Dict[str, Any]) -> List[PolicyViolation]:
        """
        Check proposal against integrity policies.
        
        Args:
            proposal: Proposal dictionary
            
        Returns:
            List of policy violations
        """
        violations = []
        content_lower = proposal.get("description", "").lower()
        
        # I3.1: Schema Validation
        if "schema" in content_lower or "migration" in content_lower:
            if "migration" not in content_lower and "rollback" not in content_lower:
                violations.append(PolicyViolation(
                    policy_id=ShieldPolicies.INTEGRITY_SCHEMA_VALIDATION,
                    policy_name=self.policies.POLICIES[ShieldPolicies.INTEGRITY_SCHEMA_VALIDATION]["name"],
                    severity="high",
                    description="Schema change without migration plan",
                    recommendation="Create migration file with up/down migrations"
                ))
        
        # I3.3: Task State Management
        if "task" in content_lower and "status" in content_lower:
            if "validation" not in content_lower:
                violations.append(PolicyViolation(
                    policy_id=ShieldPolicies.INTEGRITY_TASK_STATE,
                    policy_name=self.policies.POLICIES[ShieldPolicies.INTEGRITY_TASK_STATE]["name"],
                    severity="medium",
                    description="Task status changes without validation mentioned",
                    recommendation="Add state transition validation"
                ))
        
        return violations
    
    def review_proposal(self, proposal_id: str) -> VettingResult:
        """
        Review a proposal against SHIELD policies.
        
        This is the main entry point for proposal vetting.
        
        Args:
            proposal_id: The proposal ID to review
            
        Returns:
            VettingResult with decision and reasoning
        """
        logger.info(f"Reviewing proposal: {proposal_id}")
        
        # Fetch proposal
        proposal = self.get_proposal(proposal_id)
        if not proposal:
            return VettingResult(
                proposal_id=proposal_id,
                decision=VettingDecision.REJECT,
                confidence=1.0,
                reasoning=f"Proposal {proposal_id} not found in Neo4j"
            )
        
        logger.info(f"Found proposal: {proposal.get('title', 'Untitled')}")
        
        # Update status to under_review
        driver = self._get_driver()
        try:
            with driver.session() as session:
                session.run("""
                    MATCH (p:ArchitectureProposal {id: $proposal_id})
                    SET p.status = 'under_review',
                        p.review_started_at = datetime()
                """, {"proposal_id": proposal_id})
        except Exception as e:
            logger.warning(f"Could not update proposal status: {e}")
        
        # Estimate resources
        estimate = self._estimate_resources(proposal)
        logger.info(f"Estimated resources: {estimate.tokens} tokens, {estimate.memory_mb}MB memory")
        
        # Check all policy categories
        all_violations = []
        all_violations.extend(self._check_security_policies(proposal))
        all_violations.extend(self._check_efficiency_policies(proposal, estimate))
        all_violations.extend(self._check_limits_policies(proposal, estimate))
        all_violations.extend(self._check_integrity_policies(proposal))
        
        # Count critical and high severity violations
        critical_count = sum(1 for v in all_violations if v.severity == "critical")
        high_count = sum(1 for v in all_violations if v.severity == "high")
        medium_count = sum(1 for v in all_violations if v.severity == "medium")
        
        logger.info(f"Found {critical_count} critical, {high_count} high, {medium_count} medium violations")
        
        # Generate warnings and suggestions
        warnings = []
        suggestions = []
        
        # Check for missing rollback plan
        if "rollback" not in proposal.get("description", "").lower():
            if "migration" in proposal.get("description", "").lower():
                warnings.append("No rollback plan specified for migration")
                suggestions.append("Add rollback procedure to proposal")
        
        # Check for missing tests
        if "test" not in proposal.get("description", "").lower():
            warnings.append("No testing approach mentioned")
            suggestions.append("Add test plan to proposal")
        
        # Make decision
        if critical_count > 0:
            decision = VettingDecision.REJECT
            confidence = 0.9
            reasoning = f"Rejected due to {critical_count} critical policy violation(s). " \
                       f"Address security/limits issues before resubmission."
        elif high_count > 2:
            decision = VettingDecision.REJECT
            confidence = 0.8
            reasoning = f"Rejected due to {high_count} high-severity policy violations. " \
                       f"Revise to address integrity and security concerns."
        elif high_count > 0 or medium_count > 3:
            decision = VettingDecision.REQUEST_CHANGES
            confidence = 0.75
            reasoning = f"Changes requested: {high_count} high, {medium_count} medium violations. " \
                       f"Address policy compliance issues and resubmit."
        elif len(all_violations) > 0:
            decision = VettingDecision.APPROVE
            confidence = 0.85
            reasoning = f"Approved with warnings: {len(all_violations)} minor violations. " \
                       f"Consider addressing suggestions before implementation."
        else:
            decision = VettingDecision.APPROVE
            confidence = 0.95
            reasoning = "Approved: No policy violations detected. Ready for implementation."
        
        # Create result
        result = VettingResult(
            proposal_id=proposal_id,
            decision=decision,
            confidence=confidence,
            reasoning=reasoning,
            violations=all_violations,
            resource_estimate=estimate,
            warnings=warnings,
            suggestions=suggestions
        )
        
        # Update proposal with result
        self._update_proposal_status(result)
        
        # Create Vetting node
        self._create_vetting_node(result)
        
        logger.info(f"Vetting complete: {decision.value} (confidence: {confidence:.2f})")
        
        return result
    
    def _update_proposal_status(self, result: VettingResult):
        """Update proposal status based on vetting result."""
        driver = self._get_driver()
        
        status_map = {
            VettingDecision.APPROVE: "approved",
            VettingDecision.REJECT: "rejected",
            VettingDecision.REQUEST_CHANGES: "submitted",  # Back to submitted for changes
            VettingDecision.NEEDS_DISCUSSION: "under_review"
        }
        
        new_status = status_map.get(result.decision, "under_review")
        
        try:
            with driver.session() as session:
                session.run("""
                    MATCH (p:ArchitectureProposal {id: $proposal_id})
                    SET p.status = $status,
                        p.vetted_at = datetime(),
                        p.vetted_by = $vetted_by,
                        p.vetting_decision = $decision,
                        p.vetting_confidence = $confidence,
                        p.vetting_reasoning = $reasoning
                """, {
                    "proposal_id": result.proposal_id,
                    "status": new_status,
                    "vetted_by": result.vetted_by,
                    "decision": result.decision.value,
                    "confidence": result.confidence,
                    "reasoning": result.reasoning
                })
                
                logger.info(f"Updated proposal {result.proposal_id} status to {new_status}")
                
        except Exception as e:
            logger.error(f"Error updating proposal status: {e}")
    
    def _create_vetting_node(self, result: VettingResult):
        """Create a Vetting node in Neo4j."""
        driver = self._get_driver()
        
        try:
            with driver.session() as session:
                # Create Vetting node
                vetting_result = session.run("""
                    CREATE (v:Vetting {
                        id: 'vet-' + randomUUID(),
                        proposal_id: $proposal_id,
                        decision: $decision,
                        confidence: $confidence,
                        reasoning: $reasoning,
                        vetted_at: datetime(),
                        vetted_by: $vetted_by,
                        violation_count: $violation_count,
                        warning_count: $warning_count
                    })
                    RETURN v.id as vetting_id
                """, {
                    "proposal_id": result.proposal_id,
                    "decision": result.decision.value,
                    "confidence": result.confidence,
                    "reasoning": result.reasoning,
                    "vetted_by": result.vetted_by,
                    "violation_count": len(result.violations),
                    "warning_count": len(result.warnings)
                })
                
                vetting_id = vetting_result.single()["vetting_id"]
                
                # Link to proposal
                session.run("""
                    MATCH (p:ArchitectureProposal {id: $proposal_id})
                    MATCH (v:Vetting {id: $vetting_id})
                    CREATE (p)-[:HAS_VETTING]->(v)
                """, {
                    "proposal_id": result.proposal_id,
                    "vetting_id": vetting_id
                })
                
                # Create PolicyViolation nodes for each violation
                for violation in result.violations:
                    session.run("""
                        MATCH (v:Vetting {id: $vetting_id})
                        CREATE (pv:PolicyViolation {
                            id: 'pv-' + randomUUID(),
                            policy_id: $policy_id,
                            policy_name: $policy_name,
                            severity: $severity,
                            description: $description,
                            recommendation: $recommendation,
                            detected_at: datetime()
                        })
                        CREATE (v)-[:HAS_VIOLATION]->(pv)
                    """, {
                        "vetting_id": vetting_id,
                        "policy_id": violation.policy_id,
                        "policy_name": violation.policy_name,
                        "severity": violation.severity,
                        "description": violation.description,
                        "recommendation": violation.recommendation
                    })
                
                logger.info(f"Created Vetting node: {vetting_id}")
                
        except Exception as e:
            logger.error(f"Error creating vetting node: {e}")
    
    def batch_review(self, max_proposals: int = 10) -> List[VettingResult]:
        """
        Review all pending proposals in batch.
        
        Args:
            max_proposals: Maximum number of proposals to review
            
        Returns:
            List of VettingResults
        """
        logger.info(f"Starting batch review (max: {max_proposals})")
        
        proposals = self.list_pending_proposals()
        logger.info(f"Found {len(proposals)} pending proposals")
        
        results = []
        for proposal in proposals[:max_proposals]:
            proposal_id = proposal.get("id")
            if proposal_id:
                try:
                    result = self.review_proposal(proposal_id)
                    results.append(result)
                except Exception as e:
                    logger.error(f"Error reviewing {proposal_id}: {e}")
        
        logger.info(f"Batch review complete: {len(results)} proposals reviewed")
        return results


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Ögedei Vetting Handler - Architecture Proposal Review",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Review a specific proposal
  python -m tools.kurultai.vetting_handlers --review-proposal prop-xxx

  # List all pending proposals
  python -m tools.kurultai.vetting_handlers --list-pending

  # Batch review all pending proposals
  python -m tools.kurultai.vetting_handlers --batch-review

  # Show SHIELD policies
  python -m tools.kurultai.vetting_handlers --show-policies

  # Dry run (don't update Neo4j)
  python -m tools.kurultai.vetting_handlers --review-proposal prop-xxx --dry-run
        """
    )
    
    parser.add_argument(
        "--review-proposal",
        type=str,
        metavar="PROPOSAL_ID",
        help="Review a specific proposal by ID"
    )
    
    parser.add_argument(
        "--list-pending",
        action="store_true",
        help="List all pending proposals"
    )
    
    parser.add_argument(
        "--batch-review",
        action="store_true",
        help="Review all pending proposals"
    )
    
    parser.add_argument(
        "--show-policies",
        action="store_true",
        help="Display SHIELD policies"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't update Neo4j (dry run)"
    )
    
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )
    
    parser.add_argument(
        "--max-proposals",
        type=int,
        default=10,
        help="Maximum proposals to review in batch (default: 10)"
    )
    
    args = parser.parse_args()
    
    # Show policies
    if args.show_policies:
        policies = ShieldPolicies()
        print("\nSHIELD Policies:")
        print("=" * 60)
        for policy_id, policy in policies.POLICIES.items():
            print(f"\n{policy_id}: {policy['name']}")
            print(f"  Severity: {policy['severity']}")
            print(f"  Description: {policy['description']}")
        print()
        return
    
    # Initialize handler
    handler = OgedeiVettingHandler()
    
    # List pending
    if args.list_pending:
        proposals = handler.list_pending_proposals()
        
        if args.json:
            print(json.dumps(proposals, indent=2, default=str))
        else:
            print(f"\nPending Proposals ({len(proposals)}):")
            print("-" * 80)
            for p in proposals:
                status = p.get("status", "unknown")
                priority = p.get("priority", "medium")
                title = p.get("title", "Untitled")[:50]
                print(f"  {p['id'][:30]:32} | {status:15} | {priority:8} | {title}")
        return
    
    # Review specific proposal
    if args.review_proposal:
        result = handler.review_proposal(args.review_proposal)
        
        if args.json:
            print(json.dumps(result.to_dict(), indent=2, default=str))
        else:
            print("\n" + "=" * 60)
            print("VETTING RESULT")
            print("=" * 60)
            print(f"Proposal ID: {result.proposal_id}")
            print(f"Decision: {result.decision.value.upper()}")
            print(f"Confidence: {result.confidence:.0%}")
            print(f"Reasoning: {result.reasoning}")
            
            if result.violations:
                print(f"\nPolicy Violations ({len(result.violations)}):")
                for v in result.violations:
                    print(f"  [{v.severity.upper()}] {v.policy_id}: {v.policy_name}")
                    print(f"    Issue: {v.description}")
                    print(f"    Fix: {v.recommendation}")
            
            if result.warnings:
                print(f"\nWarnings ({len(result.warnings)}):")
                for w in result.warnings:
                    print(f"  - {w}")
            
            if result.suggestions:
                print(f"\nSuggestions ({len(result.suggestions)}):")
                for s in result.suggestions:
                    print(f"  - {s}")
            
            if result.resource_estimate:
                e = result.resource_estimate
                print(f"\nResource Estimate:")
                print(f"  Tokens: {e.tokens}")
                print(f"  Memory: {e.memory_mb}MB")
                print(f"  CPU: {e.cpu_seconds}s")
                print(f"  Neo4j Nodes: +{e.neo4j_nodes}")
                print(f"  Neo4j Relationships: +{e.neo4j_relationships}")
            
            print("=" * 60)
        
        # Exit with error if rejected
        if result.decision == VettingDecision.REJECT:
            sys.exit(1)
        return
    
    # Batch review
    if args.batch_review:
        results = handler.batch_review(max_proposals=args.max_proposals)
        
        if args.json:
            print(json.dumps([r.to_dict() for r in results], indent=2, default=str))
        else:
            print(f"\nBatch Review Results ({len(results)} proposals):")
            print("-" * 80)
            
            approved = sum(1 for r in results if r.decision == VettingDecision.APPROVE)
            rejected = sum(1 for r in results if r.decision == VettingDecision.REJECT)
            changes = sum(1 for r in results if r.decision == VettingDecision.REQUEST_CHANGES)
            
            for r in results:
                print(f"  {r.proposal_id[:30]:32} | {r.decision.value.upper():15} | {r.confidence:.0%}")
            
            print("-" * 80)
            print(f"Summary: {approved} approved, {rejected} rejected, {changes} need changes")
        
        # Exit with error if any rejected
        if any(r.decision == VettingDecision.REJECT for r in results):
            sys.exit(1)
        return
    
    # No action specified
    parser.print_help()


if __name__ == "__main__":
    main()
