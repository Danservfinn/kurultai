# Agent Integration Patterns for Capability Acquisition

> **Status**: Design Document
> **Date**: 2026-02-04
> **Version**: 0.1

## Executive Summary

This document provides concrete patterns for implementing autonomous capability acquisition in the Kublai multi-agent system. It covers agent self-modification, tool registry management, Neo4j memory integration, delegation strategies, capability verification, and security boundaries.

---

## Table of Contents

1. [Agent Self-Modification Patterns](#1-agent-self-modification-patterns)
2. [Tool Registry Patterns](#2-tool-registry-patterns)
3. [Memory Integration](#3-memory-integration)
4. [Delegation Strategies](#4-delegation-strategies)
5. [Capability Verification](#5-capability-verification)
6. [Security Boundaries](#6-security-boundaries)

---

## 1. Agent Self-Modification Patterns

### 1.1 SOUL.md Update Architecture

When an agent learns a new capability, it must update its SOUL.md to reflect the new skill. This requires a controlled self-modification system.

```python
# tools/capability_self_modification.py
"""
Self-modification protocol for agent SOUL.md files.
Implements safe, validated updates to agent capability definitions.
"""

import re
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

class ModificationRisk(Enum):
    """Risk levels for SOUL.md modifications."""
    LOW = "low"           # Adding examples, clarifications
    MEDIUM = "medium"     # Adding capabilities, tools
    HIGH = "high"         # Changing core behavior, boundaries
    CRITICAL = "critical" # Changing identity, safety rules

@dataclass
class SOULModification:
    """Represents a proposed SOUL.md modification."""
    agent_id: str
    section: str
    content: str
    modification_type: str  # "add", "replace", "append"
    risk_level: ModificationRisk
    capability_id: Optional[str] = None
    justification: str = ""
    proposed_by: str = ""  # Agent proposing the change
    approved_by: Optional[str] = None  # Human or Kublai approval

class SOULModificationProtocol:
    """
    Protocol for safe agent self-modification.

    Implements a multi-stage approval process:
    1. Proposal: Agent proposes modification
    2. Validation: System validates syntax and risk
    3. Approval: Required based on risk level
    4. Application: Modification applied with backup
    5. Verification: Confirm modification successful
    """

    # Risk level approval requirements
    APPROVAL_REQUIREMENTS = {
        ModificationRisk.LOW: None,           # Auto-approve
        ModificationRisk.MEDIUM: "kublai",    # Kublai approval
        ModificationRisk.HIGH: "human",       # Human approval
        ModificationRisk.CRITICAL: "human"    # Human approval + review
    }

    # Protected sections that cannot be modified autonomously
    PROTECTED_SECTIONS = [
        "core_truths",
        "boundaries",
        "safety_rules",
        "identity"
    ]

    def __init__(self, souls_dir: str = "/Users/kurultai/molt/data/workspace/souls"):
        self.souls_dir = Path(souls_dir)
        self.backup_dir = self.souls_dir / ".backups"
        self.backup_dir.mkdir(exist_ok=True)

    def propose_modification(
        self,
        agent_id: str,
        section: str,
        content: str,
        modification_type: str,
        capability_id: Optional[str] = None,
        justification: str = ""
    ) -> SOULModification:
        """
        Create a modification proposal.

        Args:
            agent_id: Agent proposing the modification
            section: SOUL.md section to modify
            content: New content to add/replace
            modification_type: "add", "replace", or "append"
            capability_id: Associated capability ID
            justification: Why this modification is needed

        Returns:
            SOULModification proposal
        """
        # Assess risk level
        risk_level = self._assess_risk(section, content, modification_type)

        proposal = SOULModification(
            agent_id=agent_id,
            section=section,
            content=content,
            modification_type=modification_type,
            risk_level=risk_level,
            capability_id=capability_id,
            justification=justification,
            proposed_by=agent_id
        )

        return proposal

    def _assess_risk(
        self,
        section: str,
        content: str,
        modification_type: str
    ) -> ModificationRisk:
        """Assess risk level of proposed modification."""
        # Check if section is protected
        if any(protected in section.lower() for protected in self.PROTECTED_SECTIONS):
            return ModificationRisk.CRITICAL

        # Check for dangerous keywords
        dangerous_patterns = [
            r"ignore\s+(previous|prior|above)",
            r"forget\s+(everything|all)",
            r"you\s+are\s+now",
            r"new\s+instructions",
            r"system\s+prompt",
            r"override\s+safety"
        ]

        content_lower = content.lower()
        for pattern in dangerous_patterns:
            if re.search(pattern, content_lower):
                return ModificationRisk.CRITICAL

        # Check modification type
        if modification_type == "replace":
            return ModificationRisk.HIGH

        # Check content size (larger = more risk)
        if len(content) > 1000:
            return ModificationRisk.MEDIUM

        # Adding capabilities is medium risk
        if "capability" in section.lower() or "skill" in section.lower():
            return ModificationRisk.MEDIUM

        return ModificationRisk.LOW

    def validate_modification(self, proposal: SOULModification) -> Tuple[bool, str]:
        """
        Validate a proposed modification.

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check protected sections
        if any(protected in proposal.section.lower() for protected in self.PROTECTED_SECTIONS):
            if proposal.risk_level == ModificationRisk.CRITICAL:
                return False, f"Cannot autonomously modify protected section: {proposal.section}"

        # Validate SOUL.md exists
        soul_path = self._get_soul_path(proposal.agent_id)
        if not soul_path.exists():
            return False, f"SOUL.md not found for agent: {proposal.agent_id}"

        # Validate content doesn't break markdown
        if proposal.content.count("```") % 2 != 0:
            return False, "Unclosed code block in content"

        # Validate section exists (for replace/append)
        if proposal.modification_type in ("replace", "append"):
            current_content = soul_path.read_text()
            section_header = f"## {proposal.section}"
            if section_header not in current_content:
                return False, f"Section not found: {proposal.section}"

        return True, "Valid"

    def requires_approval(self, proposal: SOULModification) -> Optional[str]:
        """
        Check if modification requires approval.

        Returns:
            None if no approval needed, otherwise who must approve
        """
        return self.APPROVAL_REQUIREMENTS.get(proposal.risk_level)

    def apply_modification(
        self,
        proposal: SOULModification,
        force: bool = False
    ) -> Tuple[bool, str]:
        """
        Apply a validated modification to SOUL.md.

        Args:
            proposal: Validated SOULModification
            force: Skip approval check (use with caution)

        Returns:
            Tuple of (success, message)
        """
        # Check approval
        if not force:
            required_approval = self.requires_approval(proposal)
            if required_approval and not proposal.approved_by:
                return False, f"Requires approval by: {required_approval}"

        # Create backup
        soul_path = self._get_soul_path(proposal.agent_id)
        backup_path = self._create_backup(soul_path, proposal.agent_id)

        try:
            # Read current content
            content = soul_path.read_text()

            # Apply modification
            new_content = self._apply_change(content, proposal)

            # Write new content
            soul_path.write_text(new_content)

            # Verify
            if self._verify_modification(soul_path, proposal):
                return True, f"Modification applied successfully. Backup: {backup_path}"
            else:
                # Rollback
                self._restore_backup(backup_path, soul_path)
                return False, "Verification failed, rolled back"

        except Exception as e:
            # Rollback on error
            self._restore_backup(backup_path, soul_path)
            return False, f"Error applying modification: {e}"

    def _apply_change(self, content: str, proposal: SOULModification) -> str:
        """Apply the modification to content."""
        section_header = f"## {proposal.section}"

        if proposal.modification_type == "add":
            # Add new section at end
            return content + f"\n\n{section_header}\n\n{proposal.content}\n"

        elif proposal.modification_type == "append":
            # Append to existing section
            pattern = f"({re.escape(section_header)}.*?)(\n## |\Z)"
            replacement = f"\\1{proposal.content}\\2"
            return re.sub(pattern, replacement, content, flags=re.DOTALL)

        elif proposal.modification_type == "replace":
            # Replace section content
            pattern = f"{re.escape(section_header)}.*?((?=\n## )|$)"
            replacement = f"{section_header}\n\n{proposal.content}\n"
            return re.sub(pattern, replacement, content, flags=re.DOTALL)

        return content

    def _create_backup(self, soul_path: Path, agent_id: str) -> Path:
        """Create timestamped backup of SOUL.md."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{agent_id}_{timestamp}.md.bak"
        backup_path = self.backup_dir / backup_name

        backup_path.write_bytes(soul_path.read_bytes())
        return backup_path

    def _restore_backup(self, backup_path: Path, soul_path: Path):
        """Restore from backup."""
        if backup_path.exists():
            soul_path.write_bytes(backup_path.read_bytes())

    def _verify_modification(self, soul_path: Path, proposal: SOULModification) -> bool:
        """Verify modification was applied correctly."""
        content = soul_path.read_text()

        # Check section exists
        section_header = f"## {proposal.section}"
        if section_header not in content:
            return False

        # Check content is present
        if proposal.content.strip() not in content:
            return False

        # Check file is valid markdown
        if content.count("```") % 2 != 0:
            return False

        return True

    def _get_soul_path(self, agent_id: str) -> Path:
        """Get path to agent's SOUL.md."""
        return self.souls_dir / agent_id / "SOUL.md"
```

### 1.2 Capability Registration in SOUL.md

When an agent learns a new capability, it should add a structured entry to its SOUL.md:

```markdown
## Learned Capabilities

### Capability: twilio_voice_call
**Learned**: 2026-02-04
**Mastery Score**: 0.91
**Status**: active
**Verified By**: jochi

**Description**: Make outbound voice calls using Twilio API

**Requirements**:
- Environment variables: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER
- Cost: $0.013 per call
- Rate limit: 1 call per second

**Usage**:
```python
result = execute_skill("twilio_voice_call", {
    "to": "+15551234567",
    "message": "Hello from Kublai"
})
```

**Limitations**:
- Cannot call emergency services
- Requires valid Twilio account with credit
- Message length limited to 1000 characters

**Error Patterns**:
- Authentication failed: Check TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN
- Invalid number: Ensure E.164 format (+1XXXXXXXXXX)
```

### 1.3 Self-Modification Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Identity drift | Protected sections cannot be modified |
| Capability bloat | Max 50 learned capabilities per agent |
| Circular updates | Hash-based change detection |
| Malicious injection | Content sanitization, approval workflow |
| Backup failure | Multiple backup retention (last 10) |

---

## 2. Tool Registry Patterns

### 2.1 Tool Registry Schema

```python
# tools/tool_registry.py
"""
Centralized tool registry for capability management.
Stores tool metadata, versions, and discovery information.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime
from enum import Enum
import json

class ToolStatus(Enum):
    """Tool lifecycle status."""
    RESEARCHING = "researching"    # Being researched
    DEVELOPING = "developing"      # Being implemented
    TESTING = "testing"            # In validation
    ACTIVE = "active"              # Ready for use
    DEPRECATED = "deprecated"      # Being phased out
    RETIRED = "retired"            # No longer available

@dataclass
class ToolParameter:
    """Tool parameter definition."""
    name: str
    type: str
    description: str
    required: bool = True
    default: Any = None
    example: Any = None

@dataclass
class ToolExample:
    """Tool usage example."""
    description: str
    parameters: Dict[str, Any]
    expected_result: Any

@dataclass
class ToolMetadata:
    """Complete tool metadata."""
    # Identity
    id: str
    name: str
    version: str
    category: str  # "communication", "data", "automation", etc.

    # Description
    description: str
    long_description: Optional[str] = None

    # Parameters
    parameters: List[ToolParameter] = field(default_factory=list)

    # Examples
    examples: List[ToolExample] = field(default_factory=list)

    # Execution
    handler: Optional[str] = None  # Path to handler function
    sandboxed: bool = False
    timeout_seconds: int = 30

    # Requirements
    required_secrets: List[str] = field(default_factory=list)
    required_capabilities: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)

    # Cost
    cost_per_use: float = 0.0
    cost_currency: str = "USD"
    rate_limit: Optional[str] = None

    # Status
    status: ToolStatus = ToolStatus.RESEARCHING
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    created_by: str = ""

    # Validation
    test_suite_id: Optional[str] = None
    mastery_score: float = 0.0
    usage_count: int = 0
    success_count: int = 0

    # Safety
    risk_level: str = "low"  # low, medium, high, critical
    allowed_agents: List[str] = field(default_factory=list)  # Empty = all
    prohibited_agents: List[str] = field(default_factory=list)

class ToolRegistry:
    """
    Central registry for all tools/capabilities.

    Provides:
    - Tool registration and discovery
    - Version management
    - Usage tracking
    - Agent capability queries
    """

    def __init__(self, neo4j_client=None):
        self.neo4j = neo4j_client
        self._local_cache: Dict[str, ToolMetadata] = {}

    def register_tool(self, metadata: ToolMetadata) -> str:
        """
        Register a new tool in the registry.

        Args:
            metadata: Tool metadata

        Returns:
            Tool ID
        """
        # Store in Neo4j
        if self.neo4j:
            self._store_in_neo4j(metadata)

        # Update cache
        self._local_cache[metadata.id] = metadata

        return metadata.id

    def _store_in_neo4j(self, metadata: ToolMetadata):
        """Store tool metadata in Neo4j."""
        cypher = """
        CREATE (t:Tool {
            id: $id,
            name: $name,
            version: $version,
            category: $category,
            description: $description,
            parameters: $parameters,
            examples: $examples,
            handler: $handler,
            sandboxed: $sandboxed,
            timeout_seconds: $timeout_seconds,
            required_secrets: $required_secrets,
            required_capabilities: $required_capabilities,
            dependencies: $dependencies,
            cost_per_use: $cost_per_use,
            status: $status,
            created_at: datetime($created_at),
            updated_at: datetime($updated_at),
            created_by: $created_by,
            mastery_score: $mastery_score,
            risk_level: $risk_level,
            allowed_agents: $allowed_agents,
            prohibited_agents: $prohibited_agents
        })
        RETURN t.id
        """

        with self.neo4j._session() as session:
            session.run(cypher,
                id=metadata.id,
                name=metadata.name,
                version=metadata.version,
                category=metadata.category,
                description=metadata.description,
                parameters=json.dumps([self._param_to_dict(p) for p in metadata.parameters]),
                examples=json.dumps([self._example_to_dict(e) for e in metadata.examples]),
                handler=metadata.handler,
                sandboxed=metadata.sandboxed,
                timeout_seconds=metadata.timeout_seconds,
                required_secrets=metadata.required_secrets,
                required_capabilities=metadata.required_capabilities,
                dependencies=metadata.dependencies,
                cost_per_use=metadata.cost_per_use,
                status=metadata.status.value,
                created_at=metadata.created_at.isoformat(),
                updated_at=metadata.updated_at.isoformat(),
                created_by=metadata.created_by,
                mastery_score=metadata.mastery_score,
                risk_level=metadata.risk_level,
                allowed_agents=metadata.allowed_agents,
                prohibited_agents=metadata.prohibited_agents
            )

    def _param_to_dict(self, param: ToolParameter) -> dict:
        return {
            "name": param.name,
            "type": param.type,
            "description": param.description,
            "required": param.required,
            "default": param.default,
            "example": param.example
        }

    def _example_to_dict(self, example: ToolExample) -> dict:
        return {
            "description": example.description,
            "parameters": example.parameters,
            "expected_result": example.expected_result
        }

    def discover_tools(
        self,
        category: Optional[str] = None,
        agent: Optional[str] = None,
        status: Optional[ToolStatus] = None,
        min_mastery: float = 0.0
    ) -> List[ToolMetadata]:
        """
        Discover available tools.

        Args:
            category: Filter by category
            agent: Filter by agent authorization
            status: Filter by status
            min_mastery: Minimum mastery score

        Returns:
            List of matching tool metadata
        """
        cypher = """
        MATCH (t:Tool)
        WHERE t.status = $status
        AND t.mastery_score >= $min_mastery
        """

        params = {
            "status": status.value if status else ToolStatus.ACTIVE.value,
            "min_mastery": min_mastery
        }

        if category:
            cypher += " AND t.category = $category"
            params["category"] = category

        if agent:
            cypher += """
            AND (t.allowed_agents = [] OR $agent IN t.allowed_agents)
            AND NOT ($agent IN t.prohibited_agents)
            """
            params["agent"] = agent

        cypher += " RETURN t"

        tools = []
        with self.neo4j._session() as session:
            result = session.run(cypher, **params)
            for record in result:
                tools.append(self._dict_to_metadata(dict(record["t"])))

        return tools

    def get_tool(self, tool_id: str) -> Optional[ToolMetadata]:
        """Get tool by ID."""
        # Check cache first
        if tool_id in self._local_cache:
            return self._local_cache[tool_id]

        # Query Neo4j
        if self.neo4j:
            cypher = "MATCH (t:Tool {id: $id}) RETURN t"
            with self.neo4j._session() as session:
                result = session.run(cypher, id=tool_id)
                record = result.single()
                if record:
                    metadata = self._dict_to_metadata(dict(record["t"]))
                    self._local_cache[tool_id] = metadata
                    return metadata

        return None

    def update_tool_status(
        self,
        tool_id: str,
        new_status: ToolStatus,
        updated_by: str
    ) -> bool:
        """Update tool status."""
        cypher = """
        MATCH (t:Tool {id: $id})
        SET t.status = $status,
            t.updated_at = datetime(),
            t.updated_by = $updated_by
        RETURN t.id
        """

        with self.neo4j._session() as session:
            result = session.run(cypher,
                id=tool_id,
                status=new_status.value,
                updated_by=updated_by
            )
            return result.single() is not None

    def record_usage(
        self,
        tool_id: str,
        success: bool,
        execution_time_ms: int,
        cost: float = 0.0
    ):
        """Record tool usage statistics."""
        cypher = """
        MATCH (t:Tool {id: $id})
        SET t.usage_count = t.usage_count + 1,
            t.success_count = CASE WHEN $success
                THEN t.success_count + 1
                ELSE t.success_count
            END,
            t.total_execution_time_ms = coalesce(t.total_execution_time_ms, 0) + $execution_time,
            t.total_cost = coalesce(t.total_cost, 0) + $cost
        RETURN t
        """

        with self.neo4j._session() as session:
            session.run(cypher,
                id=tool_id,
                success=success,
                execution_time=execution_time_ms,
                cost=cost
            )

    def _dict_to_metadata(self, data: dict) -> ToolMetadata:
        """Convert Neo4j dict to ToolMetadata."""
        return ToolMetadata(
            id=data["id"],
            name=data["name"],
            version=data["version"],
            category=data["category"],
            description=data["description"],
            parameters=[ToolParameter(**p) for p in json.loads(data.get("parameters", "[]"))],
            examples=[ToolExample(**e) for e in json.loads(data.get("examples", "[]"))],
            handler=data.get("handler"),
            sandboxed=data.get("sandboxed", False),
            timeout_seconds=data.get("timeout_seconds", 30),
            required_secrets=data.get("required_secrets", []),
            required_capabilities=data.get("required_capabilities", []),
            dependencies=data.get("dependencies", []),
            cost_per_use=data.get("cost_per_use", 0.0),
            status=ToolStatus(data["status"]),
            created_by=data.get("created_by", ""),
            mastery_score=data.get("mastery_score", 0.0),
            risk_level=data.get("risk_level", "low"),
            allowed_agents=data.get("allowed_agents", []),
            prohibited_agents=data.get("prohibited_agents", [])
        )
```

### 2.2 Tool Versioning

Tools should follow semantic versioning:

```python
class ToolVersionManager:
    """Manages tool versioning and migrations."""

    def create_new_version(
        self,
        tool_id: str,
        new_version: str,
        changes: str,
        breaking: bool = False
    ) -> str:
        """
        Create a new version of an existing tool.

        Args:
            tool_id: Existing tool ID
            new_version: New version string (e.g., "2.0.0")
            changes: Description of changes
            breaking: Whether this is a breaking change

        Returns:
            New tool ID
        """
        # Get existing tool
        old_tool = self.registry.get_tool(tool_id)
        if not old_tool:
            raise ValueError(f"Tool not found: {tool_id}")

        # Create new tool with updated version
        new_tool = ToolMetadata(
            id=f"{old_tool.name}_v{new_version}",
            name=old_tool.name,
            version=new_version,
            category=old_tool.category,
            description=old_tool.description,
            # ... copy other fields
            status=ToolStatus.TESTING if breaking else ToolStatus.ACTIVE
        )

        # Store new version
        new_id = self.registry.register_tool(new_tool)

        # Create version relationship
        self._create_version_relationship(old_tool.id, new_id, breaking, changes)

        # If breaking change, deprecate old version
        if breaking:
            self.registry.update_tool_status(
                old_tool.id,
                ToolStatus.DEPRECATED,
                "system"
            )

        return new_id

    def _create_version_relationship(
        self,
        old_id: str,
        new_id: str,
        breaking: bool,
        changes: str
    ):
        """Create VERSIONED_TO relationship between tools."""
        cypher = """
        MATCH (old:Tool {id: $old_id})
        MATCH (new:Tool {id: $new_id})
        CREATE (old)-[v:VERSIONED_TO {
            breaking: $breaking,
            changes: $changes,
            created_at: datetime()
        }]->(new)
        """

        with self.registry.neo4j._session() as session:
            session.run(cypher,
                old_id=old_id,
                new_id=new_id,
                breaking=breaking,
                changes=changes
            )
```

---

## 3. Memory Integration

### 3.1 Neo4j Schema for Capabilities

```cypher
// Core capability nodes
(:Capability {
    id: string,                    // UUID
    name: string,                  // e.g., "twilio_voice_call"
    category: string,              // "communication", "data", "automation"
    description: string,
    status: string,                // "researching" | "practicing" | "active" | "deprecated"

    // Mastery tracking
    mastery_score: float,          // 0-1
    confidence_level: string,      // "low" | "medium" | "high" | "expert"
    last_validated: datetime,
    validation_interval_days: int,

    // Usage tracking
    usage_count: int,
    success_count: int,
    failure_count: int,
    last_used: datetime,

    // Cost tracking
    cost_per_use: float,
    total_cost: float,

    // Implementation
    implementation_type: string,   // "api", "code", "integration"
    handler_reference: string,     // Path to handler code
    language: string,              // "python", "javascript", etc.

    // Security
    requires_secrets: boolean,
    secret_keys: [string],
    risk_level: string,            // "low" | "medium" | "high" | "critical"

    // Metadata
    created_at: datetime,
    created_by: string,            // Agent ID
    version: string,

    // Embedding for semantic search
    embedding: [float]
})

// Capability learning session
(:CapabilityLearningSession {
    id: string,
    capability_id: string,
    agent_id: string,
    phase: string,                 // "research" | "practice" | "validation"
    started_at: datetime,
    completed_at: datetime,
    status: string,                // "in_progress" | "completed" | "failed"
    attempts: int,
    successes: int,
    cost_incurred: float,
    notes: string
})

// Capability execution record
(:CapabilityExecution {
    id: string,
    capability_id: string,
    agent_id: string,
    task_id: string,
    status: string,                // "success" | "failure" | "partial"
    execution_time_ms: int,
    cost: float,
    input_summary: string,         // Sanitized input
    output_summary: string,        // Sanitized output
    error_message: string,
    timestamp: datetime
})

// Error patterns learned
(:CapabilityErrorPattern {
    id: string,
    capability_id: string,
    error_type: string,
    error_pattern: string,         // Regex or description
    frequency: int,
    solutions: [string],
    prevention_strategy: string,
    resolved: boolean
})

// Capability dependencies
(:CapabilityDependency {
    capability_id: string,
    depends_on: string,
    dependency_type: string        // "required" | "optional" | "enhances"
})
```

### 3.2 Relationships

```cypher
// Agent-capability relationships
(Agent)-[:KNOWS {
    learned_at: datetime,
    mastery_level: string,
    practice_hours: float,
    last_used: datetime
}]->(Capability)

(Agent)-[:CAN_USE]->(Capability)  // Available but not expert

// Learning process
(Agent)-[:RESEARCHED]->(CapabilityResearch)
(CapabilityResearch)-[:ENABLES]->(Capability)

(Agent)-[:PRACTICED]->(CapabilityLearningSession)
(CapabilityLearningSession)-[:IMPROVES]->(Capability)

(Agent)-[:VALIDATED]->(CapabilityValidation)
(CapabilityValidation)-[:CONFIRMS]->(Capability)

// Execution
(CapabilityExecution)-[:USES]->(Capability)
(CapabilityExecution)-[:EXECUTED_BY]->(Agent)

// Error patterns
(Capability)-[:HAS_ERROR_PATTERN]->(CapabilityErrorPattern)

// Dependencies
(Capability)-[:REQUIRES]->(Capability)
(Capability)-[:ENHANCED_BY]->(Capability)

// Task relationship
(Task)-[:REQUIRES_CAPABILITY]->(Capability)
```

### 3.3 Capability Memory Queries

```python
class CapabilityMemory:
    """Neo4j-based capability memory operations."""

    def __init__(self, neo4j_client):
        self.neo4j = neo4j_client

    def find_capability_gap(self, task_description: str, agent_id: str) -> List[Dict]:
        """
        Find capabilities needed for a task that the agent doesn't have.

        Uses semantic search to find relevant capabilities.
        """
        cypher = """
        // Find capabilities that might match the task
        CALL db.index.vector.queryNodes('capability_embedding', 5, $embedding)
        YIELD node, score

        // Check if agent knows this capability
        OPTIONAL MATCH (agent:Agent {id: $agent_id})-[k:KNOWS]->(node)

        // Return capabilities agent doesn't know
        WHERE k IS NULL AND node.status = 'active'

        RETURN node.id as capability_id,
               node.name as name,
               node.description as description,
               node.mastery_score as mastery_score,
               score as relevance
        ORDER BY score DESC
        """

        # Generate embedding for task description
        embedding = self._generate_embedding(task_description)

        with self.neo4j._session() as session:
            result = session.run(cypher,
                embedding=embedding,
                agent_id=agent_id
            )
            return [dict(record) for record in result]

    def get_agent_capabilities(
        self,
        agent_id: str,
        min_mastery: float = 0.0
    ) -> List[Dict]:
        """Get all capabilities known by an agent."""
        cypher = """
        MATCH (a:Agent {id: $agent_id})-[k:KNOWS]->(c:Capability)
        WHERE c.mastery_score >= $min_mastery
        RETURN c.id as id,
               c.name as name,
               c.category as category,
               c.mastery_score as mastery_score,
               k.mastery_level as my_level,
               k.last_used as last_used
        ORDER BY c.mastery_score DESC
        """

        with self.neo4j._session() as session:
            result = session.run(cypher,
                agent_id=agent_id,
                min_mastery=min_mastery
            )
            return [dict(record) for record in result]

    def record_execution(
        self,
        capability_id: str,
        agent_id: str,
        task_id: str,
        success: bool,
        execution_time_ms: int,
        cost: float = 0.0,
        error: Optional[str] = None
    ):
        """Record a capability execution."""
        cypher = """
        // Create execution record
        CREATE (e:CapabilityExecution {
            id: $execution_id,
            capability_id: $capability_id,
            agent_id: $agent_id,
            task_id: $task_id,
            status: $status,
            execution_time_ms: $execution_time,
            cost: $cost,
            error_message: $error,
            timestamp: datetime()
        })

        // Link to capability and agent
        WITH e
        MATCH (c:Capability {id: $capability_id})
        MATCH (a:Agent {id: $agent_id})
        CREATE (e)-[:USES]->(c)
        CREATE (e)-[:EXECUTED_BY]->(a)

        // Update capability stats
        WITH c
        SET c.usage_count = c.usage_count + 1,
            c.success_count = CASE WHEN $success
                THEN c.success_count + 1
                ELSE c.success_count
            END,
            c.last_used = datetime()
        """

        execution_id = str(uuid.uuid4())

        with self.neo4j._session() as session:
            session.run(cypher,
                execution_id=execution_id,
                capability_id=capability_id,
                agent_id=agent_id,
                task_id=task_id,
                status="success" if success else "failure",
                execution_time=execution_time_ms,
                cost=cost,
                error=error,
                success=success
            )

    def find_similar_capabilities(
        self,
        capability_id: str,
        threshold: float = 0.8
    ) -> List[Dict]:
        """Find capabilities similar to a given capability."""
        cypher = """
        MATCH (c:Capability {id: $capability_id})
        CALL db.index.vector.queryNodes('capability_embedding', 10, c.embedding)
        YIELD node, score
        WHERE node.id <> $capability_id AND score >= $threshold
        RETURN node.id as id,
               node.name as name,
               node.description as description,
               score
        ORDER BY score DESC
        """

        with self.neo4j._session() as session:
            result = session.run(cypher,
                capability_id=capability_id,
                threshold=threshold
            )
            return [dict(record) for record in result]

    def get_capability_success_rate(
        self,
        capability_id: str,
        days: int = 30
    ) -> Dict:
        """Get success rate for a capability over time."""
        cypher = """
        MATCH (e:CapabilityExecution)
        WHERE e.capability_id = $capability_id
        AND e.timestamp >= datetime() - duration({days: $days})
        RETURN count(e) as total,
               count(CASE WHEN e.status = 'success' THEN 1 END) as successes,
               avg(e.execution_time_ms) as avg_time,
               sum(e.cost) as total_cost
        """

        with self.neo4j._session() as session:
            result = session.run(cypher,
                capability_id=capability_id,
                days=days
            )
            record = result.single()
            total = record["total"]
            successes = record["successes"]

            return {
                "capability_id": capability_id,
                "total_executions": total,
                "successes": successes,
                "failures": total - successes,
                "success_rate": successes / total if total > 0 else 0,
                "avg_execution_time_ms": record["avg_time"],
                "total_cost": record["total_cost"]
            }
```

---

## 4. Delegation Strategies

### 4.1 Capability Acquisition as Special Agent Role

```python
# tools/capability_acquisition_orchestrator.py
"""
Orchestrates the capability acquisition workflow across agents.
"""

from enum import Enum
from typing import Dict, List, Optional
from dataclasses import dataclass

class AcquisitionPhase(Enum):
    RESEARCH = "research"           # Mongke
    IMPLEMENT = "implement"         # Temujin
    VALIDATE = "validate"           # Jochi
    DOCUMENT = "document"           # Chagatai
    DEPLOY = "deploy"               # Ogedei

@dataclass
class CapabilityAcquisitionTask:
    """Task for acquiring a new capability."""
    id: str
    goal: str                       # "learn to call phones"
    capability_name: str
    priority: str                   # "low", "medium", "high", "critical"
    requesting_agent: str
    current_phase: AcquisitionPhase
    phases_completed: List[AcquisitionPhase]
    research_findings: Optional[Dict] = None
    implementation_code: Optional[str] = None
    validation_results: Optional[Dict] = None
    status: str = "pending"         # "pending", "in_progress", "completed", "failed"

class CapabilityAcquisitionOrchestrator:
    """
    Orchestrates capability acquisition across the agent team.

    Workflow:
    1. Kublai detects capability gap
    2. Creates acquisition task
    3. Delegates to appropriate agent per phase
    4. Tracks progress through phases
    5. Validates and registers completed capability
    """

    # Phase to agent mapping
    PHASE_AGENTS = {
        AcquisitionPhase.RESEARCH: "researcher",      # Mongke
        AcquisitionPhase.IMPLEMENT: "developer",      # Temujin
        AcquisitionPhase.VALIDATE: "analyst",         # Jochi
        AcquisitionPhase.DOCUMENT: "writer",          # Chagatai
        AcquisitionPhase.DEPLOY: "ops"                # Ogedei
    }

    # Phase dependencies
    PHASE_ORDER = [
        AcquisitionPhase.RESEARCH,
        AcquisitionPhase.IMPLEMENT,
        AcquisitionPhase.VALIDATE,
        AcquisitionPhase.DOCUMENT,
        AcquisitionPhase.DEPLOY
    ]

    def __init__(self, delegation_protocol, tool_registry, capability_memory):
        self.delegation = delegation_protocol
        self.registry = tool_registry
        self.memory = capability_memory

    def initiate_acquisition(
        self,
        goal: str,
        capability_name: str,
        requesting_agent: str,
        priority: str = "normal"
    ) -> CapabilityAcquisitionTask:
        """
        Initiate a new capability acquisition workflow.

        Args:
            goal: Natural language goal (e.g., "learn to call phones")
            capability_name: Structured capability name (e.g., "twilio_voice_call")
            requesting_agent: Agent that needs this capability
            priority: Task priority

        Returns:
            CapabilityAcquisitionTask
        """
        task_id = str(uuid.uuid4())

        task = CapabilityAcquisitionTask(
            id=task_id,
            goal=goal,
            capability_name=capability_name,
            priority=priority,
            requesting_agent=requesting_agent,
            current_phase=AcquisitionPhase.RESEARCH,
            phases_completed=[],
            status="in_progress"
        )

        # Store task in Neo4j
        self._store_task(task)

        # Delegate first phase
        self._delegate_phase(task, AcquisitionPhase.RESEARCH)

        return task

    def _delegate_phase(self, task: CapabilityAcquisitionTask, phase: AcquisitionPhase):
        """Delegate a phase to the appropriate agent."""
        agent = self.PHASE_AGENTS[phase]

        phase_tasks = {
            AcquisitionPhase.RESEARCH: self._create_research_task,
            AcquisitionPhase.IMPLEMENT: self._create_implementation_task,
            AcquisitionPhase.VALIDATE: self._create_validation_task,
            AcquisitionPhase.DOCUMENT: self._create_documentation_task,
            AcquisitionPhase.DEPLOY: self._create_deployment_task
        }

        description, context = phase_tasks[phase](task)

        # Delegate via delegation protocol
        result = self.delegation.delegate_task(
            task_description=description,
            context={
                **context,
                "acquisition_task_id": task.id,
                "phase": phase.value,
                "capability_name": task.capability_name
            },
            suggested_agent=agent,
            priority=task.priority
        )

        return result

    def _create_research_task(self, task: CapabilityAcquisitionTask) -> tuple:
        """Create research phase task for Mongke."""
        description = f"""
Research how to implement capability: {task.capability_name}

Goal: {task.goal}

Research questions:
1. What APIs or services provide this capability?
2. What are the authentication requirements?
3. What are the costs and rate limits?
4. What are common failure modes?
5. What are the security considerations?

Deliverable: Research report with provider comparison and recommendation.
"""

        context = {
            "research_type": "capability_acquisition",
            "capability_name": task.capability_name,
            "output_format": "structured_report"
        }

        return description, context

    def _create_implementation_task(self, task: CapabilityAcquisitionTask) -> tuple:
        """Create implementation phase task for Temujin."""
        description = f"""
Implement capability: {task.capability_name}

Based on research findings, implement a working solution.

Requirements:
- Implement handler function
- Include error handling
- Add input validation
- Follow security best practices
- Include usage examples

Deliverable: Working code with tests.
"""

        context = {
            "implementation_type": "capability",
            "capability_name": task.capability_name,
            "research_findings": task.research_findings,
            "output_format": "code_with_tests"
        }

        return description, context

    def _create_validation_task(self, task: CapabilityAcquisitionTask) -> tuple:
        """Create validation phase task for Jochi."""
        description = f"""
Validate capability: {task.capability_name}

Create and run comprehensive test suite:
1. Happy path tests
2. Error handling tests
3. Edge case tests
4. Security tests
5. Performance tests

Calculate mastery score based on pass rate.

Deliverable: Validation report with mastery score.
"""

        context = {
            "validation_type": "capability",
            "capability_name": task.capability_name,
            "implementation_code": task.implementation_code,
            "output_format": "validation_report"
        }

        return description, context

    def handle_phase_completion(
        self,
        task_id: str,
        phase: AcquisitionPhase,
        results: Dict
    ):
        """Handle completion of a phase."""
        # Load task
        task = self._load_task(task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")

        # Store phase results
        if phase == AcquisitionPhase.RESEARCH:
            task.research_findings = results
        elif phase == AcquisitionPhase.IMPLEMENT:
            task.implementation_code = results.get("code")
        elif phase == AcquisitionPhase.VALIDATE:
            task.validation_results = results

        # Mark phase complete
        task.phases_completed.append(phase)

        # Determine next phase
        current_index = self.PHASE_ORDER.index(phase)
        if current_index < len(self.PHASE_ORDER) - 1:
            next_phase = self.PHASE_ORDER[current_index + 1]
            task.current_phase = next_phase

            # Check if we should proceed
            if self._should_proceed(task, phase, results):
                self._delegate_phase(task, next_phase)
            else:
                task.status = "failed"
                self._notify_failure(task, phase, results)
        else:
            # All phases complete
            self._finalize_acquisition(task)

        # Update stored task
        self._store_task(task)

    def _should_proceed(
        self,
        task: CapabilityAcquisitionTask,
        completed_phase: AcquisitionPhase,
        results: Dict
    ) -> bool:
        """Determine if acquisition should proceed to next phase."""
        if completed_phase == AcquisitionPhase.RESEARCH:
            # Need sufficient confidence in research
            return results.get("confidence", 0) >= 0.7

        elif completed_phase == AcquisitionPhase.IMPLEMENT:
            # Code must compile/pass basic tests
            return results.get("compiles", False)

        elif completed_phase == AcquisitionPhase.VALIDATE:
            # Mastery score must meet threshold
            mastery_score = results.get("mastery_score", 0)
            return mastery_score >= 0.85

        return True

    def _finalize_acquisition(self, task: CapabilityAcquisitionTask):
        """Finalize capability acquisition."""
        task.status = "completed"

        # Register tool in registry
        tool_metadata = self._create_tool_metadata(task)
        self.registry.register_tool(tool_metadata)

        # Store capability in memory
        self._store_capability(task)

        # Update agent SOUL.md
        self._update_agent_capabilities(task)

        # Notify requesting agent
        self._notify_completion(task)

    def _create_tool_metadata(self, task: CapabilityAcquisitionTask) -> ToolMetadata:
        """Create tool metadata from completed acquisition."""
        validation = task.validation_results or {}

        return ToolMetadata(
            id=f"capability_{task.capability_name}",
            name=task.capability_name,
            version="1.0.0",
            category=self._categorize_capability(task.capability_name),
            description=task.goal,
            status=ToolStatus.ACTIVE,
            created_by=task.phases_completed[1].value if len(task.phases_completed) > 1 else "unknown",
            mastery_score=validation.get("mastery_score", 0),
            test_suite_id=validation.get("test_suite_id"),
            risk_level=self._assess_risk(task)
        )

    def _categorize_capability(self, name: str) -> str:
        """Categorize capability by name."""
        categories = {
            "call": "communication",
            "sms": "communication",
            "email": "communication",
            "voice": "communication",
            "api": "integration",
            "webhook": "integration",
            "database": "data",
            "query": "data",
            "file": "storage",
            "image": "media",
            "video": "media"
        }

        for keyword, category in categories.items():
            if keyword in name.lower():
                return category

        return "automation"

    def _assess_risk(self, task: CapabilityAcquisitionTask) -> str:
        """Assess risk level of the capability."""
        research = task.research_findings or {}

        # High cost = higher risk
        if research.get("cost_per_use", 0) > 1.0:
            return "high"

        # Requires secrets = medium risk
        if research.get("requires_secrets", False):
            return "medium"

        # External API calls = medium risk
        if research.get("external_api", False):
            return "medium"

        return "low"
```

### 4.2 Specialist Selection Based on Capability Type

```python
class SpecialistRouter:
    """Routes capability acquisition to appropriate specialists."""

    # Capability type to specialist mapping
    SPECIALIST_MAP = {
        # Communication
        "voice_call": "developer",
        "sms": "developer",
        "email": "developer",
        "chat": "developer",

        # Data
        "database": "analyst",
        "analytics": "analyst",
        "ml": "analyst",
        "visualization": "analyst",

        # Web/Integration
        "api_integration": "developer",
        "webhook": "developer",
        "scraping": "developer",
        "automation": "developer",

        # Content
        "content_generation": "writer",
        "summarization": "writer",
        "translation": "writer",

        # Infrastructure
        "deployment": "ops",
        "monitoring": "ops",
        "backup": "ops",

        # Security
        "security_audit": "developer",
        "penetration_test": "developer",
        "vulnerability_scan": "developer"
    }

    def route_to_specialist(
        self,
        capability_type: str,
        task_complexity: str = "medium"
    ) -> str:
        """
        Determine which specialist should handle a capability.

        Args:
            capability_type: Type of capability
            task_complexity: "simple", "medium", "complex"

        Returns:
            Agent ID to handle the task
        """
        # Direct mapping
        if capability_type in self.SPECIALIST_MAP:
            return self.SPECIALIST_MAP[capability_type]

        # Pattern matching
        for pattern, specialist in self.SPECIALIST_MAP.items():
            if pattern in capability_type.lower():
                return specialist

        # Default based on complexity
        if task_complexity == "simple":
            return "developer"  # Temujin handles simple tasks
        elif task_complexity == "complex":
            return "researcher"  # Mongke researches complex new areas

        return "developer"  # Default
```

---

## 5. Capability Verification

### 5.1 Validation Framework

```python
# tools/capability_validation.py
"""
Capability validation framework for testing learned capabilities.
"""

from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass
from enum import Enum
import time
import traceback

class TestResult(Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    ERROR = "error"

@dataclass
class ValidationTest:
    """Single validation test."""
    name: str
    description: str
    test_function: Callable
    weight: float = 1.0
    required: bool = True
    timeout_seconds: int = 30

@dataclass
class TestOutcome:
    """Outcome of a single test."""
    test_name: str
    result: TestResult
    execution_time_ms: int
    message: str
    details: Optional[Dict] = None

class CapabilityValidator:
    """
    Validates capabilities through automated testing.

    Test categories:
    - Happy path: Normal operation
    - Error handling: Invalid inputs, failures
    - Edge cases: Boundary conditions
    - Security: Input validation, injection attempts
    - Performance: Response time, resource usage
    """

    def __init__(self, capability_name: str, handler: Callable):
        self.capability_name = capability_name
        self.handler = handler
        self.tests: List[ValidationTest] = []

    def add_test(self, test: ValidationTest):
        """Add a validation test."""
        self.tests.append(test)

    def generate_standard_tests(self, schema: Dict) -> List[ValidationTest]:
        """
        Generate standard tests from capability schema.

        Args:
            schema: Capability parameter schema

        Returns:
            List of validation tests
        """
        tests = []

        # Happy path test
        tests.append(ValidationTest(
            name="happy_path",
            description="Test normal operation with valid inputs",
            test_function=self._create_happy_path_test(schema),
            weight=1.0,
            required=True
        ))

        # Required parameter tests
        for param_name, param_spec in schema.get("parameters", {}).items():
            if param_spec.get("required", False):
                tests.append(ValidationTest(
                    name=f"missing_required_{param_name}",
                    description=f"Test missing required parameter: {param_name}",
                    test_function=self._create_missing_param_test(param_name, schema),
                    weight=0.8,
                    required=True
                ))

            # Type validation tests
            tests.append(ValidationTest(
                name=f"invalid_type_{param_name}",
                description=f"Test invalid type for parameter: {param_name}",
                test_function=self._create_invalid_type_test(param_name, param_spec, schema),
                weight=0.6,
                required=False
            ))

        # Error handling tests
        tests.append(ValidationTest(
            name="error_handling",
            description="Test error handling with invalid inputs",
            test_function=self._create_error_handling_test(schema),
            weight=0.9,
            required=True
        ))

        # Timeout test
        tests.append(ValidationTest(
            name="timeout_handling",
            description="Test timeout handling",
            test_function=self._create_timeout_test(schema),
            weight=0.7,
            required=False
        ))

        return tests

    def run_validation(self) -> Dict:
        """
        Run all validation tests.

        Returns:
            Validation report with mastery score
        """
        outcomes: List[TestOutcome] = []

        for test in self.tests:
            outcome = self._run_single_test(test)
            outcomes.append(outcome)

        # Calculate mastery score
        mastery_score = self._calculate_mastery_score(outcomes)

        # Generate report
        report = {
            "capability_name": self.capability_name,
            "total_tests": len(outcomes),
            "passed": sum(1 for o in outcomes if o.result == TestResult.PASS),
            "failed": sum(1 for o in outcomes if o.result == TestResult.FAIL),
            "errors": sum(1 for o in outcomes if o.result == TestResult.ERROR),
            "skipped": sum(1 for o in outcomes if o.result == TestResult.SKIP),
            "mastery_score": mastery_score,
            "outcomes": [
                {
                    "test_name": o.test_name,
                    "result": o.result.value,
                    "execution_time_ms": o.execution_time_ms,
                    "message": o.message
                }
                for o in outcomes
            ],
            "validated_at": datetime.now().isoformat()
        }

        return report

    def _run_single_test(self, test: ValidationTest) -> TestOutcome:
        """Run a single test."""
        start_time = time.time()

        try:
            # Run with timeout
            result = self._run_with_timeout(
                test.test_function,
                test.timeout_seconds
            )

            execution_time = int((time.time() - start_time) * 1000)

            if result:
                return TestOutcome(
                    test_name=test.name,
                    result=TestResult.PASS,
                    execution_time_ms=execution_time,
                    message="Test passed"
                )
            else:
                return TestOutcome(
                    test_name=test.name,
                    result=TestResult.FAIL,
                    execution_time_ms=execution_time,
                    message="Test assertion failed"
                )

        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            return TestOutcome(
                test_name=test.name,
                result=TestResult.ERROR,
                execution_time_ms=execution_time,
                message=str(e),
                details={"traceback": traceback.format_exc()}
            )

    def _calculate_mastery_score(self, outcomes: List[TestOutcome]) -> float:
        """Calculate mastery score from test outcomes."""
        total_weight = 0
        weighted_score = 0

        for outcome in outcomes:
            test = next((t for t in self.tests if t.name == outcome.test_name), None)
            if not test:
                continue

            weight = test.weight
            total_weight += weight

            if outcome.result == TestResult.PASS:
                weighted_score += weight
            elif outcome.result == TestResult.SKIP:
                # Skipped tests don't count against score
                total_weight -= weight

        if total_weight == 0:
            return 0

        return weighted_score / total_weight

    def _create_happy_path_test(self, schema: Dict) -> Callable:
        """Create happy path test from schema."""
        def test():
            # Generate valid inputs from schema
            inputs = self._generate_valid_inputs(schema)
            result = self.handler(**inputs)
            return result is not None and not isinstance(result, Exception)
        return test

    def _create_missing_param_test(self, param_name: str, schema: Dict) -> Callable:
        """Create test for missing required parameter."""
        def test():
            inputs = self._generate_valid_inputs(schema)
            del inputs[param_name]
            try:
                self.handler(**inputs)
                return False  # Should have raised error
            except (TypeError, ValueError):
                return True  # Correctly raised error
        return test

    def _create_invalid_type_test(
        self,
        param_name: str,
        param_spec: Dict,
        schema: Dict
    ) -> Callable:
        """Create test for invalid parameter type."""
        def test():
            inputs = self._generate_valid_inputs(schema)
            # Set invalid type
            inputs[param_name] = self._get_invalid_value(param_spec.get("type"))
            try:
                self.handler(**inputs)
                return False  # Should have raised error or handled gracefully
            except (TypeError, ValueError):
                return True
        return test

    def _create_error_handling_test(self, schema: Dict) -> Callable:
        """Create error handling test."""
        def test():
            # Test with deliberately invalid inputs
            try:
                result = self.handler(invalid_param="test")
                # Should either raise error or return error response
                return isinstance(result, dict) and "error" in result
            except Exception:
                return True  # Correctly raised error
        return test

    def _create_timeout_test(self, schema: Dict) -> Callable:
        """Create timeout handling test."""
        def test():
            start = time.time()
            try:
                inputs = self._generate_valid_inputs(schema)
                self.handler(**inputs)
                elapsed = time.time() - start
                return elapsed < 30  # Should complete within timeout
            except Exception:
                return False
        return test

    def _generate_valid_inputs(self, schema: Dict) -> Dict:
        """Generate valid test inputs from schema."""
        inputs = {}
        for param_name, param_spec in schema.get("parameters", {}).items():
            param_type = param_spec.get("type", "string")
            example = param_spec.get("example")

            if example is not None:
                inputs[param_name] = example
            elif param_type == "string":
                inputs[param_name] = f"test_{param_name}"
            elif param_type == "integer":
                inputs[param_name] = 42
            elif param_type == "number":
                inputs[param_name] = 3.14
            elif param_type == "boolean":
                inputs[param_name] = True
            elif param_type == "array":
                inputs[param_name] = []
            elif param_type == "object":
                inputs[param_name] = {}

        return inputs

    def _get_invalid_value(self, param_type: str) -> Any:
        """Get an invalid value for a parameter type."""
        if param_type == "string":
            return 12345  # Number instead of string
        elif param_type in ("integer", "number"):
            return "not_a_number"
        elif param_type == "boolean":
            return "not_a_boolean"
        elif param_type == "array":
            return "not_an_array"
        elif param_type == "object":
            return "not_an_object"
        return None

    def _run_with_timeout(self, func: Callable, timeout: int) -> Any:
        """Run function with timeout."""
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(func)
            try:
                return future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                raise TimeoutError(f"Test timed out after {timeout} seconds")
```

### 5.2 Human-in-the-Loop Validation

```python
class HumanValidationWorkflow:
    """
    Human-in-the-loop validation for critical capabilities.
    """

    def __init__(self, notification_system):
        self.notifications = notification_system

    def request_human_validation(
        self,
        capability_name: str,
        validation_report: Dict,
        test_outputs: List[Dict]
    ) -> str:
        """
        Request human validation before activating capability.

        Args:
            capability_name: Name of capability
            validation_report: Automated validation results
            test_outputs: Detailed test outputs

        Returns:
            Validation request ID
        """
        request_id = str(uuid.uuid4())

        # Create detailed validation request
        request = {
            "id": request_id,
            "capability_name": capability_name,
            "mastery_score": validation_report["mastery_score"],
            "test_summary": {
                "total": validation_report["total_tests"],
                "passed": validation_report["passed"],
                "failed": validation_report["failed"]
            },
            "test_outputs": test_outputs,
            "status": "pending",
            "requested_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(days=7)).isoformat()
        }

        # Store request
        self._store_validation_request(request)

        # Notify human
        self.notifications.send(
            channel="human_review",
            message=f"""
Capability '{capability_name}' requires human validation.

Mastery Score: {validation_report['mastery_score']:.2%}
Tests: {validation_report['passed']}/{validation_report['total_tests']} passed

Review at: /validate/{request_id}
"""
        )

        return request_id

    def process_human_decision(
        self,
        request_id: str,
        decision: str,  # "approve", "reject", "request_changes"
        feedback: Optional[str] = None
    ):
        """Process human validation decision."""
        request = self._load_validation_request(request_id)

        if decision == "approve":
            request["status"] = "approved"
            request["approved_at"] = datetime.now().isoformat()
            self._activate_capability(request["capability_name"])

        elif decision == "reject":
            request["status"] = "rejected"
            request["rejection_reason"] = feedback
            self._reject_capability(request["capability_name"], feedback)

        elif decision == "request_changes":
            request["status"] = "changes_requested"
            request["feedback"] = feedback
            self._request_changes(request["capability_name"], feedback)

        self._store_validation_request(request)
```

---

## 6. Security Boundaries

### 6.1 Prohibited Capabilities

```python
# tools/capability_security.py
"""
Security controls for capability acquisition.
"""

from typing import Set, List, Dict
from enum import Enum

class CapabilityClass(Enum):
    """Classification of capability risk levels."""
    SAFE = "safe"              # No external effects
    LOW_RISK = "low_risk"      # Limited external effects
    MEDIUM_RISK = "medium_risk" # Significant external effects
    HIGH_RISK = "high_risk"    # Potentially dangerous
    PROHIBITED = "prohibited"  # Never allowed

class CapabilitySecurityPolicy:
    """
    Security policy for capability acquisition.

    Defines what capabilities can be learned autonomously
    and what requires human approval.
    """

    # Absolutely prohibited capabilities
    PROHIBITED_PATTERNS = {
        # Self-modification beyond SOUL.md
        r"self.*modify.*code",
        r"auto.*update.*system",
        r"rewrite.*own.*source",

        # Financial without limits
        r"unlimited.*spend",
        r"bypass.*cost.*limit",
        r"auto.*purchase",

        # Communication abuse
        r"spam",
        r"bulk.*email",
        r"harassment",
        r"impersonat",

        # Security circumvention
        r"bypass.*auth",
        r"crack.*password",
        r"exploit",
        r"vulnerability.*scan.*without.*permission",

        # Privacy violations
        r"scrap.*personal.*data",
        r"bypass.*privacy",
        r"collect.*without.*consent",

        # Legal issues
        r"copyright.*infringement",
        r"illegal",
        r"unauthorized.*access"
    }

    # Capabilities requiring human approval
    HIGH_RISK_PATTERNS = {
        r"delete.*data",
        r"modify.*production",
        r"deploy.*to.*production",
        r"access.*sensitive",
        r"financial.*transaction",
        r"legal.*document",
        r"medical.*advice",
        r"security.*configuration"
    }

    # Capabilities allowed with cost limits
    MEDIUM_RISK_PATTERNS = {
        r"api.*call",
        r"external.*service",
        r"third.*party",
        r"cloud.*service"
    }

    def classify_capability(self, capability_name: str, description: str) -> CapabilityClass:
        """
        Classify a capability by risk level.

        Args:
            capability_name: Name of capability
            description: Capability description

        Returns:
            CapabilityClass
        """
        text = f"{capability_name} {description}".lower()

        # Check prohibited
        for pattern in self.PROHIBITED_PATTERNS:
            if re.search(pattern, text):
                return CapabilityClass.PROHIBITED

        # Check high risk
        for pattern in self.HIGH_RISK_PATTERNS:
            if re.search(pattern, text):
                return CapabilityClass.HIGH_RISK

        # Check medium risk
        for pattern in self.MEDIUM_RISK_PATTERNS:
            if re.search(pattern, text):
                return CapabilityClass.MEDIUM_RISK

        return CapabilityClass.LOW_RISK

    def can_learn_autonomously(self, capability_name: str, description: str) -> bool:
        """Check if capability can be learned without human approval."""
        classification = self.classify_capability(capability_name, description)
        return classification in (CapabilityClass.SAFE, CapabilityClass.LOW_RISK)

    def requires_human_approval(self, capability_name: str, description: str) -> bool:
        """Check if capability requires human approval."""
        classification = self.classify_capability(capability_name, description)
        return classification in (CapabilityClass.HIGH_RISK, CapabilityClass.MEDIUM_RISK)

    def is_prohibited(self, capability_name: str, description: str) -> bool:
        """Check if capability is prohibited."""
        classification = self.classify_capability(capability_name, description)
        return classification == CapabilityClass.PROHIBITED
```

### 6.2 Sandboxing Learned Capabilities

```python
class CapabilitySandbox:
    """
    Sandboxed execution environment for learned capabilities.

    Provides isolation for:
    - Network access
    - File system access
    - Resource limits
    - Secret access
    """

    def __init__(
        self,
        capability_id: str,
        max_cost: float = 1.0,
        max_execution_time: int = 30,
        allowed_network_hosts: Optional[List[str]] = None,
        allow_file_write: bool = False
    ):
        self.capability_id = capability_id
        self.max_cost = max_cost
        self.max_execution_time = max_execution_time
        self.allowed_network_hosts = allowed_network_hosts or []
        self.allow_file_write = allow_file_write

        self.execution_count = 0
        self.total_cost = 0.0
        self.total_execution_time = 0

    def execute(self, handler: Callable, **kwargs) -> Dict:
        """
        Execute capability in sandbox.

        Args:
            handler: Capability handler function
            **kwargs: Arguments for handler

        Returns:
            Execution result
        """
        # Pre-execution checks
        if not self._check_limits():
            return {
                "success": False,
                "error": "Sandbox limits exceeded",
                "capability_id": self.capability_id
            }

        # Execute with monitoring
        start_time = time.time()
        try:
            # Wrap handler with monitors
            wrapped_handler = self._wrap_handler(handler)
            result = wrapped_handler(**kwargs)

            execution_time = time.time() - start_time
            self._record_execution(execution_time)

            return {
                "success": True,
                "result": result,
                "execution_time_ms": int(execution_time * 1000),
                "capability_id": self.capability_id
            }

        except Exception as e:
            execution_time = time.time() - start_time
            self._record_execution(execution_time, failed=True)

            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "execution_time_ms": int(execution_time * 1000),
                "capability_id": self.capability_id
            }

    def _check_limits(self) -> bool:
        """Check if execution is within limits."""
        if self.total_cost >= self.max_cost:
            return False
        if self.execution_count >= 100:  # Max executions per session
            return False
        return True

    def _wrap_handler(self, handler: Callable) -> Callable:
        """Wrap handler with security monitors."""
        def wrapped(**kwargs):
            # Inject sandbox context
            kwargs['_sandbox'] = {
                'allowed_hosts': self.allowed_network_hosts,
                'allow_file_write': self.allow_file_write,
                'capability_id': self.capability_id
            }

            # Execute with timeout
            import signal

            def timeout_handler(signum, frame):
                raise TimeoutError(f"Execution exceeded {self.max_execution_time}s")

            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(self.max_execution_time)

            try:
                result = handler(**kwargs)
                signal.alarm(0)
                return result
            except Exception:
                signal.alarm(0)
                raise

        return wrapped

    def _record_execution(self, execution_time: float, failed: bool = False):
        """Record execution metrics."""
        self.execution_count += 1
        self.total_execution_time += execution_time
        # Cost tracking would be implemented here
```

### 6.3 Capability Poisoning Prevention

```python
class CapabilityPoisoningDetector:
    """
    Detects potential capability poisoning attempts.

    Checks for:
    - Suspicious code patterns
    - Hidden malicious behavior
    - Dependency confusion
    - Prompt injection in examples
    """

    SUSPICIOUS_PATTERNS = [
        # Code execution
        r"eval\s*\(",
        r"exec\s*\(",
        r"__import__\s*\(",
        r"subprocess\.call",
        r"os\.system",
        r"compile\s*\(",

        # Data exfiltration
        r"requests\.post.*http",
        r"urllib\.request",
        r"socket\.connect",

        # Obfuscation
        r"base64\.(b64decode|decode)",
        r"chr\s*\(\s*\d+",
        r"\\x[0-9a-f]{2}",

        # Privilege escalation
        r"chmod\s+\+?x",
        r"setuid",
        r"sudo",

        # Backdoors
        r"backdoor",
        r"shell",
        r"reverse.*connect"
    ]

    def scan_capability(self, code: str, examples: List[Dict]) -> Dict:
        """
        Scan capability for potential poisoning.

        Args:
            code: Capability implementation code
            examples: Usage examples

        Returns:
            Scan report
        """
        findings = []

        # Scan code
        for pattern in self.SUSPICIOUS_PATTERNS:
            matches = re.finditer(pattern, code, re.IGNORECASE)
            for match in matches:
                findings.append({
                    "type": "suspicious_code",
                    "pattern": pattern,
                    "location": f"line {code[:match.start()].count(chr(10)) + 1}",
                    "severity": "high"
                })

        # Scan examples for prompt injection
        for i, example in enumerate(examples):
            injection_score = self._check_prompt_injection(example)
            if injection_score > 0.5:
                findings.append({
                    "type": "prompt_injection",
                    "example_index": i,
                    "score": injection_score,
                    "severity": "medium"
                })

        # Check dependencies
        dependency_issues = self._check_dependencies(code)
        findings.extend(dependency_issues)

        return {
            "clean": len(findings) == 0,
            "findings": findings,
            "risk_score": self._calculate_risk_score(findings)
        }

    def _check_prompt_injection(self, example: Dict) -> float:
        """Check for prompt injection attempts in examples."""
        text = str(example)

        injection_patterns = [
            r"ignore\s+previous",
            r"forget\s+instructions",
            r"new\s+instructions",
            r"you\s+are\s+now",
            r"system\s+prompt",
            r"DAN\s+mode",
            r"jailbreak"
        ]

        score = 0
        for pattern in injection_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                score += 0.2

        return min(score, 1.0)

    def _check_dependencies(self, code: str) -> List[Dict]:
        """Check for suspicious dependencies."""
        issues = []

        # Extract imports
        import_pattern = r"(?:from|import)\s+(\S+)"
        imports = re.findall(import_pattern, code)

        # Check for typosquatting (simplified)
        common_packages = ["requests", "numpy", "pandas", "django", "flask"]
        for imp in imports:
            for pkg in common_packages:
                if self._is_typosquat(imp, pkg):
                    issues.append({
                        "type": "typosquatting",
                        "package": imp,
                        "similar_to": pkg,
                        "severity": "critical"
                    })

        return issues

    def _is_typosquat(self, name: str, target: str) -> bool:
        """Check if name is a typosquat of target."""
        if name == target:
            return False

        # Simple Levenshtein distance check
        distance = self._levenshtein_distance(name, target)
        return distance <= 2 and len(name) > 3

    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """Calculate Levenshtein distance."""
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)

        if len(s2) == 0:
            return len(s1)

        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]

    def _calculate_risk_score(self, findings: List[Dict]) -> float:
        """Calculate overall risk score from findings."""
        if not findings:
            return 0.0

        severity_weights = {
            "low": 0.1,
            "medium": 0.3,
            "high": 0.6,
            "critical": 1.0
        }

        total_weight = sum(
            severity_weights.get(f["severity"], 0.1)
            for f in findings
        )

        return min(total_weight, 1.0)
```

---

## Summary

This document provides comprehensive patterns for agent capability acquisition:

### Key Patterns

1. **Self-Modification**: Multi-stage approval workflow with risk assessment, protected sections, and automatic backup/rollback

2. **Tool Registry**: Centralized registry with semantic versioning, dependency tracking, and usage statistics

3. **Memory Integration**: Neo4j schema supporting capability nodes, execution history, error patterns, and semantic search

4. **Delegation**: Phase-based orchestration routing to appropriate specialists (Mongke for research, Temujin for implementation, Jochi for validation)

5. **Verification**: Automated test generation, mastery scoring, and human-in-the-loop for high-risk capabilities

6. **Security**: Classification system for capability risk, sandboxed execution, and poisoning detection

### Implementation Priority

1. **Phase 1**: Tool registry and basic Neo4j schema
2. **Phase 2**: Self-modification protocol with approval workflow
3. **Phase 3**: Capability validation framework
4. **Phase 4**: Security sandbox and poisoning detection
5. **Phase 5**: Full delegation orchestration

These patterns enable safe, autonomous capability acquisition while maintaining security boundaries and human oversight for critical operations.
