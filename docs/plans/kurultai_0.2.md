# Kurultai v0.2: horde-learn Capability Acquisition System

> **Status**: Design Document - REVISED AFTER CRITICAL REVIEW
> **Date**: 2026-02-05
> **Author**: Kurultai System Architecture
> **Prerequisites**: [`neo4j.md`](./neo4j.md), [`kurultai_0.1.md`](./kurultai_0.1.md) - Must be implemented first

---

## Overview

**Goal:** Adapt the horde-learn skill for use in the Kurultai multi-agent system, enabling agents to learn new capabilities through natural language requests (e.g., "/learn how to call phones").

**Architecture:** Extend horde-learn from "insight extraction from text" to "capability acquisition pipeline" that integrates with Kurultai's delegation protocol, Neo4j memory, capability registry, and sandboxed code execution.

**Key Changes from Original Plan (Post-Review):**
1. **FIXED:** Delegation interface aligned with existing `DelegationProtocol` using `gateway_url` + `agentToAgent`
2. **FIXED:** Neo4j schema uses `:Research {research_type: "capability_learning"}` instead of `:CapabilityResearch`
3. **FIXED:** Sandboxed execution uses subprocess with resource limits (Railway-compatible)
4. **FIXED:** Added circular delegation protection (max depth 3)
5. **FIXED:** Added mandatory PII sanitization before any delegation
6. **REMOVED:** SOUL.md modification - violates agent boundaries
7. **ADDED:** Capability registry in Neo4j instead of SOUL.md updates
8. **ADDED:** Security controls (prompt injection filtering, static analysis, cost enforcement)
9. **ADDED:** CBAC (Capability-Based Access Control) for privilege escalation prevention
10. **ADDED:** Agent Authentication (HMAC-SHA256 message signing, replay protection)
11. **ADDED:** Neo4j Schema Migration strategy with backfill script and rollback plan

---

## Critical Review Fixes Applied

### Fix 1: Delegation Protocol Interface
**Issue:** Plan referenced `delegate_task()` method that doesn't exist in `DelegationProtocol`
**Resolution:** Use existing `gateway_url` + `agentToAgent` messaging pattern from `neo4j.md` Section 2.2

### Fix 2: Neo4j Schema Conflict
**Issue:** `:CapabilityResearch` would conflict with existing `:Research` node type
**Resolution:** Extend `:Research` with `research_type: "capability_learning"` property

### Fix 3: Infrastructure Feasibility
**Issue:** gVisor not available in Railway container environment
**Resolution:** Use Python subprocess with resource limits (RLIMIT_CPU, RLIMIT_AS, RLIMIT_NOFILE) which works without privileges

### Fix 4: Circular Delegation Risk
**Issue:** Research → Implementation → Validation could loop infinitely
**Resolution:** Add `max_delegation_depth: 3` and `delegation_chain` tracking in context

### Fix 5: Privacy Sanitization Gap
**Issue:** No PII filtering before capability research delegation
**Resolution:** Mandatory `_sanitize_for_sharing()` call before any agent delegation

### Fix 6: Privilege Escalation via Capability Registry
**Issue:** No access control for learned capabilities - any agent could use any learned tool
**Resolution:** Add CBAC with `required_capabilities`, runtime capability checks, and capability grant/revoke workflow

---

## Integration Points

| Component | File | Integration Method |
|-----------|------|-------------------|
| Delegation Protocol | `tools/delegation_protocol.py` | Uses `gateway_url` + `agentToAgent` messaging |
| Neo4j Memory | `openclaw_memory.py` | Extends `:Research` node, adds capability methods |
| Multi-Goal Orchestration | `tools/multi_goal_orchestration.py` | Uses metadata for goal categorization |
| Capability Registry | `tools/kurultai/capability_registry.py` | NEW - stores learned capabilities in Neo4j |
| Sandboxed Execution | `tools/kurultai/sandbox_executor.py` | NEW - subprocess-based code execution |
| Backend Analysis | `tools/backend_collaboration.py` | EXISTING - Jochi-Temüjin collaboration protocol |
| Analysis Protocol | `src/protocols/backend_analysis.py` | EXISTING - Backend issue identification (Phase 4.6) |

### Jochi Backend Monitoring Integration

Jochi's backend monitoring capability (Phase 4.6 from `neo4j.md`) is **already implemented** in the codebase:

| File | Lines | Purpose |
|------|-------|---------|
| `tools/backend_collaboration.py` | 1,084 | Jochi-Temüjin collaboration, Analysis node creation |
| `src/protocols/backend_analysis.py` | 929 | Backend issue identification across 5 categories |

**Integration Strategy:** Rather than building a new 5-phase tree-sitter system, leverage the existing implementation and add AST-based enhancements as Task 1.5. The existing regex-based detection in `BackendCodeReviewer` can be enhanced with tree-sitter AST parsing for improved accuracy.

**Trigger Integration:** Jochi analysis is triggered via the existing delegation protocol:
1. **Kublai Directive** - `agentToAgent` message to Jochi (`analyst`)
2. **Scheduled** - Every 4 hours via Ögedei's proactive monitoring
3. **Event-based** - Code changes detected by file watchers

**Neo4j Integration:** Jochi creates `Analysis` nodes (already defined in schema) which Kublai queries to delegate fixes to Temüjin. See Phase 4.6 in `neo4j.md` for full protocol.

---

## Phase 1: Foundation & Security Infrastructure

**Status:** Pending
**Tasks:** 4
**Parallelizable:** Partial

### Task 1.1: Create Security Infrastructure
**Description:** Implement security controls for prompt injection, input validation, and cost enforcement
**Files:**
- Create: `tools/kurultai/security/prompt_injection_filter.py` (~150 lines)
- Create: `tools/kurultai/security/cost_enforcer.py` (~200 lines)
- Create: `tools/kurultai/security/static_analysis.py` (~250 lines)
**Acceptance:**
- [ ] `PromptInjectionFilter` class with `sanitize()` method
- [ ] Detects and blocks common prompt injection patterns
- [ ] Multi-turn injection detection via conversation state tracking
- [ ] `CostEnforcer` class with `authorize_spending()` method
- [ ] Pre-authorization pattern (reserves budget before spending)
- [ ] Hard limit enforcement ($10/skill default)
- [ ] Atomic budget tracking using Neo4j `SET r.budget = r.budget - $cost`
- [ ] `StaticAnalysis` class integrating bandit and semgrep with caching
- [ ] Tiered checks: regex → AST → bandit/semgrep (only if needed)
- [ ] AST security pattern detection
**Dependencies:** None
**Domain:** Backend

### Task 1.2: Create Sandboxed Execution Environment (Subprocess-based)
**Description:** Implement subprocess-based sandbox for generated code execution (Railway-compatible, no privileged capabilities required)
**Files:**
- Create: `tools/kurultai/sandbox_executor.py` (~400 lines)
- Create: `tools/kurultai/sandbox/subprocess_executor.py` (~300 lines)
**Acceptance:**
- [ ] `SandboxExecutor` class with `execute()` method
- [ ] Python `subprocess` module with `preexec_fn` for resource limits
- [ ] RLIMIT_CPU (30s), RLIMIT_AS (512MB), RLIMIT_NOFILE (100)
- [ ] Timeout handling via `signal.SIGALRM` or `subprocess` timeout
- [ ] Network blocking via `socket` module restrictions
- [ ] Filesystem restrictions (read-only root, tmpfs for writes)
- [ ] Restricted Python execution (no `exec`, `eval`, `compile`)
- [ ] Sandbox pooling for same capability type (performance)
- [ ] **Railway Compatibility:** No nsjail, no seccomp-bpf, no CAP_SYS_ADMIN required
**Dependencies:** None
**Domain:** DevOps/Backend

**Note on Railway Compatibility:** The original plan used `nsjail` and `seccomp-bpf` which require `CAP_SYS_ADMIN` and privileged capabilities not available in Railway's container environment. This subprocess-based approach uses standard Python resource limits (`resource` module) which work in all container environments including Railway.

### Task 1.3: Create horde-learn Adapter Module
**Description:** Create the main adapter that bridges horde-learn with Kurultai architecture
**Files:**
- Create: `tools/kurultai/horde_learn_adapter.py` (~500 lines)
**Acceptance:**
- [ ] `HordeLearnKurultai` class with `learn()` method
- [ ] Integration with `CapabilityClassifier`
- [ ] Integration with `CostEnforcer` for budget control
- [ ] Integration with `SandboxExecutor` for safe execution
- [ ] Neo4j memory read/write for capability tracking
- [ ] Proper agent ID usage (researcher, developer, analyst - not display names)
- [ ] Delegation via `gateway_url` + `agentToAgent` (not `delegate_task()`)
- [ ] Mandatory `_sanitize_for_sharing()` before delegation
- [ ] Circular delegation protection (max depth 3)
**Dependencies:** Task 1.1, Task 1.2
**Domain:** Backend

### Task 1.4: Create Capability Taxonomy Data for Kurultai
**Description:** Pre-populate capability taxonomy with Kurultai-relevant capabilities
**Files:**
- Create: `tools/kurultai/capability_taxonomy_kurultai.py` (~300 lines)
**Acceptance:**
- [ ] 5 domains: COMMUNICATION, DATA, INFRASTRUCTURE, AUTOMATION, INTELLIGENCE
- [ ] 25+ capability patterns
- [ ] 100+ pre-defined capabilities
- [ ] Research source mappings for each capability
- [ ] Implementation pattern templates
- [ ] Security risk classification per capability (LOW/MEDIUM/HIGH/CRITICAL)
**Dependencies:** Task 1.3
**Domain:** Backend

### Task 1.5: Jochi Static Analysis Enhancement (AST-Based)
**Description:** Enhance existing Jochi backend monitoring with tree-sitter AST parsing for improved accuracy. Leverages existing `BackendCodeReviewer` in `tools/backend_collaboration.py`.
**Files:**
- Create: `tools/kurultai/static_analysis/__init__.py`
- Create: `tools/kurultai/static_analysis/ast_parser.py` (~300 lines)
- Create: `tools/kurultai/static_analysis/rule_engine.py` (~250 lines)
- Create: `tools/kurultai/static_analysis/rules/connection_management.yaml`
- Create: `tools/kurultai/static_analysis/rules/resilience.yaml`
- Create: `tools/kurultai/static_analysis/rules/data_integrity.yaml`
- Create: `tools/kurultai/static_analysis/rules/performance.yaml`
- Create: `tools/kurultai/static_analysis/rules/security.yaml`
**Acceptance:**
- [ ] `ASTParser` class with tree-sitter integration for Python, JavaScript, Go
- [ ] Resource limits: 10MB file size, 30s parse time, 1000 AST depth
- [ ] `RuleEngine` class with YAML rule loading using `yaml.safe_load()`
- [ ] YAML depth limiting (max 10 levels) and file size limits (1MB per rule file)
- [ ] 20+ detection rules across 5 categories (Connection, Resilience, Data Integrity, Performance, Security)
- [ ] Integration with existing `BackendCodeReviewer.create_backend_analysis()`
- [ ] Parser lazy loading (only load language parsers when needed)
- [ ] Safe regex validation (ReDoS prevention)
- [ ] **Security:** SandboxedEnvironment for any template processing
- [ ] **Security:** Input sanitization before AST parsing
- [ ] **Security:** Authorization check for Analysis node creation
**Dependencies:** Task 1.1 (security infrastructure), Task 1.3 (adapter)
**Domain:** Backend
**Note:** Existing implementation in `tools/backend_collaboration.py` provides regex-based detection. This task adds AST-based enhancement for higher accuracy.

---

## Phase 2: Classification & Research Integration

**Status:** Pending
**Tasks:** 3
**Parallelizable:** Yes

### Task 2.1: Implement Capability Classification Engine
**Description:** Hybrid classifier (rule-based + semantic + LLM fallback) with security filtering
**Files:**
- Create: `tools/kurultai/capability_classifier.py` (~600 lines)
**Acceptance:**
- [ ] `CapabilityClassifier` class with `classify()` method
- [ ] Rule-based classification (fast path, >0.85 confidence)
- [ ] Semantic similarity using Neo4j vector index
- [ ] LLM fallback for ambiguous cases
- [ ] Confidence scoring and ambiguity detection
- [ ] **Security:** Prompt injection filtering on all inputs
- [ ] **Security:** Block classification of CRITICAL-risk capabilities
**Dependencies:** Task 1.4
**Domain:** Backend

### Task 2.2: Integrate Research Delegation to Möngke
**Description:** Delegate research phase to Möngke (researcher agent) via agentToAgent
**Files:**
- Create: `tools/kurultai/research_delegation.py` (~250 lines)
**Acceptance:**
- [ ] `ResearchDelegation` class using `gateway_url` + `agentToAgent`
- [ ] Proper message format per `neo4j.md` Section 2.2
- [ ] Context includes: `task_id`, `delegated_by`, `delegation_depth`, `delegation_chain`
- [ ] API discovery via web search
- [ ] Documentation extraction and pattern analysis
- [ ] Research artifact storage in Neo4j (extends `:Research` node)
- [ ] Source ranking and reliability scoring
- [ ] **Security:** URL validation for research sources
- [ ] **Security:** `_sanitize_for_sharing()` on all research inputs
**Dependencies:** Task 1.3
**Domain:** Backend

### Task 2.3: Extend Neo4j Schema for Capability Research
**Description:** Extend existing `:Research` node for capability research findings
**Files:**
- Modify: `openclaw_memory.py` (add capability research methods after line 4125)
**Acceptance:**
- [ ] Extends `:Research` node (NOT new `:CapabilityResearch`)
- [ ] Uses `research_type: "capability_learning"` property
- [ ] Methods: `store_capability_research()`, `get_capability_research()`
- [ ] Vector index for research similarity search (384-dim, cosine)
- [ ] Follows existing patterns from `store_research()`
- [ ] Includes properties: `capability_name`, `findings`, `sources`, `reliability_score`
**Dependencies:** Task 2.2
**Domain:** Backend

---

## Phase 3: Implementation & Code Generation

**Status:** Pending
**Tasks:** 4
**Parallelizable:** Partial

### Task 3.1: Create Code Generation Templates
**Description:** Jinja2 templates for common capability patterns with security hardening
**Files:**
- Create: `templates/capabilities/api_client.py.j2`
- Create: `templates/capabilities/web_automation.py.j2`
- Create: `templates/capabilities/file_processor.py.j2`
- Create: `templates/capabilities/error_handling.py.j2`
- Create: `templates/capabilities/test_suite.py.j2`
**Acceptance:**
- [ ] 5 base templates for API integration
- [ ] 3 templates for web automation
- [ ] Error handling patterns (retry, backoff, circuit breaker)
- [ ] Auto-generated test templates
- [ ] **Security:** SandboxedEnvironment for Jinja2 (prevent SSTI)
- [ ] **Security:** No dynamic code execution in templates
- [ ] **Security:** Input escaping for all template variables
**Dependencies:** Task 2.1
**Domain:** Backend

### Task 3.2: Integrate Implementation Delegation to Temüjin
**Description:** Delegate code generation to Temüjin (developer agent) with security scanning
**Files:**
- Create: `tools/kurultai/implementation_delegation.py` (~300 lines)
**Acceptance:**
- [ ] `ImplementationDelegation` class
- [ ] Uses `gateway_url` + `agentToAgent` with delegation depth tracking
- [ ] Template-based code generation
- [ ] AST validation of generated code
- [ ] **Security:** Mandatory `StaticAnalysis.scan()` before storage
- [ ] **Security:** Block code with high-severity findings
- [ ] Tool file creation in `tools/kurultai/generated/` directory (isolated namespace)
- [ ] Auto-prefix learned tools with `learned_` to prevent shadowing
**Dependencies:** Task 3.1
**Domain:** Backend

### Task 3.3: Create Capability Registry
**Description:** Store learned capabilities in Neo4j instead of modifying SOUL.md files
**Files:**
- Create: `tools/kurultai/capability_registry.py` (~350 lines)
**Acceptance:**
- [ ] `CapabilityRegistry` class with `register()` method
- [ ] Stores capabilities as `:LearnedCapability` nodes in Neo4j
- [ ] Links to agent via `:HAS_LEARNED_CAPABILITY` relationship
- [ ] Tool metadata: name, version, parameters, examples, sandbox_config
- [ ] Semantic versioning support
- [ ] Dependency tracking between tools
- [ ] **Security:** Cryptographic signing of registered tools
- [ ] **Security:** Registry access control (only specific agents can register)
- [ ] Risk assessment stored per capability (LOW/MEDIUM/HIGH)
- [ ] **Atomic:** `claim_capability()` with race condition handling
- [ ] **Limits:** Max 50 capabilities per agent, max 5 new per day
- [ ] **CBAC:** `required_capabilities` field to define which capabilities are needed to use a learned tool
- [ ] **CBAC:** Runtime capability check before tool execution via `can_execute()`
- [ ] **CBAC:** `(Agent)-[:HAS_CAPABILITY]->(Capability)` relationship for capability grants
- [ ] **CBAC:** Capability grant/revoke workflow with expiration support
**Dependencies:** Task 2.3
**Domain:** Backend

#### CBAC Enforcement Pseudocode

```python
class CapabilityRegistry:
    def can_execute(self, agent_id: str, capability_id: str) -> bool:
        """Check if agent has required capabilities."""
        lc = self.get_learned_capability(capability_id)
        agent_caps = self.get_agent_capabilities(agent_id)

        # Check if agent has all required capabilities
        for req_cap in lc.required_capabilities:
            if req_cap not in agent_caps:
                return False

        # Check if capabilities haven't expired
        for cap in agent_caps:
            if cap.expires_at and cap.expires_at < datetime.now():
                return False

        return True

    def grant_capability(self, agent_id: str, capability_id: str,
                        granted_by: str, expires_at: Optional[datetime] = None):
        """Grant a capability to an agent."""
        query = """
        MATCH (a:Agent {id: $agent_id}), (c:Capability {id: $capability_id})
        CREATE (a)-[:HAS_CAPABILITY {
            granted_at: datetime(),
            expires_at: $expires_at,
            granted_by: $granted_by
        }]->(c)
        """
        self.neo4j.run(query, agent_id=agent_id, capability_id=capability_id,
                      granted_by=granted_by, expires_at=expires_at)

    def revoke_capability(self, agent_id: str, capability_id: str):
        """Revoke a capability from an agent."""
        query = """
        MATCH (a:Agent {id: $agent_id})-[r:HAS_CAPABILITY]->(c:Capability {id: $capability_id})
        DELETE r
        """
        self.neo4j.run(query, agent_id=agent_id, capability_id=capability_id)

    def get_agent_capabilities(self, agent_id: str) -> List[Capability]:
        """Get all active capabilities for an agent."""
        query = """
        MATCH (a:Agent {id: $agent_id})-[r:HAS_CAPABILITY]->(c:Capability)
        WHERE r.expires_at IS NULL OR r.expires_at > datetime()
        RETURN c, r
        """
        return self.neo4j.run(query, agent_id=agent_id)
```

### Task 3.4: Extend Tool Registry Integration
**Description:** Extend existing types.py patterns instead of creating separate registry
**Files:**
- Modify: `tools/kurultai/types.py` (add LearnedCapability dataclass)
**Acceptance:**
- [ ] `LearnedCapability` dataclass with all metadata fields
- [ ] Integration with existing `AgentRouting` patterns
- [ ] Type-safe capability metadata handling
**Dependencies:** Task 3.3
**Domain:** Backend

---

## Phase 4: Validation & Testing

**Status:** Pending
**Tasks:** 3
**Parallelizable:** Yes

### Task 4.1: Integrate Validation Delegation to Jochi
**Description:** Delegate testing and validation to Jochi (analyst agent) with cross-agent review. Jochi performs both capability validation AND backend code analysis.
**Files:**
- Create: `tools/kurultai/validation_delegation.py` (~300 lines)
- Modify: `tools/backend_collaboration.py` (add AST-based validation hook)
**Acceptance:**
- [ ] `ValidationDelegation` class
- [ ] Uses `gateway_url` + `agentToAgent` with depth tracking
- [ ] Automated test generation
- [ ] Test execution in sandbox environment
- [ ] Mastery score calculation (threshold: 0.85)
- [ ] **Security:** Independent validation (Jochi validates Temüjin's code, not self-validation)
- [ ] **Security:** Security test suite execution
- [ ] **Security:** Human approval gate for HIGH-risk capabilities
- [ ] **Integration:** Jochi re-runs AST analysis on Temüjin's fix to verify resolution
- [ ] **Integration:** Compare before/after AST for structural changes
- [ ] **Integration:** Validate that patterns triggering original finding no longer match
**Dependencies:** Task 3.2, Task 1.5 (Jochi AST enhancement)
**Domain:** Backend
**Note:** Jochi has dual validation responsibilities: (1) validate learned capabilities, (2) validate backend fixes. Uses existing `BackendCodeReviewer.validate_fix()` pattern.

### Task 4.2: Create Capability Testing Framework
**Description:** Test harness for generated capabilities with sandbox execution
**Files:**
- Create: `tools/kurultai/capability_tester.py` (~400 lines)
- Create: `tests/capabilities/conftest.py`
**Acceptance:**
- [ ] `CapabilityTester` class
- [ ] Mock external APIs for testing
- [ ] **Security:** Sandbox execution environment (uses SandboxExecutor)
- [ ] Performance benchmarking
- [ ] Error injection testing
- [ ] **Security:** Behavior anomaly detection
**Dependencies:** Task 4.1, Task 1.2
**Domain:** Backend

### Task 4.3: Implement Failure Recovery
**Description:** Automatic recovery from learning failures with checkpoint/rollback
**Files:**
- Modify: `tools/kurultai/horde_learn_adapter.py`
**Acceptance:**
- [ ] Checkpoint creation before each phase
- [ ] Rollback on failure (removes partial artifacts)
- [ ] `CapabilityRegistry.deregister()` for cleanup
- [ ] Retry with exponential backoff
- [ ] Fallback to alternative approaches
- [ ] Error pattern storage for future learning
- [ ] **Security:** Cleanup of sandbox containers on failure
**Dependencies:** Task 4.2
**Domain:** Backend

---

## Phase 5: Integration & Orchestration

**Status:** Pending
**Tasks:** 3
**Parallelizable:** No (sequential)

### Task 5.1: Create Master Orchestration Pipeline
**Description:** End-to-end pipeline connecting all phases with state tracking
**Files:**
- Modify: `tools/kurultai/horde_learn_adapter.py` (finalize)
**Acceptance:**
- [ ] `learn_capability()` method with full pipeline
- [ ] Phase transitions with state tracking
- [ ] Cost tracking across phases (uses CostEnforcer)
- [ ] Progress reporting
- [ ] Cancellation support
- [ ] **Security:** Pre-authorization before each phase
- [ ] **Security:** Hard cost limits with emergency shutdown
- [ ] **Security:** Circular delegation detection (max depth 3)
**Dependencies:** Tasks 2.2, 3.2, 4.1
**Domain:** Backend

### Task 5.2: Integrate with Multi-Goal Orchestration
**Description:** Connect to existing goal orchestration system using metadata
**Files:**
- Modify: `tools/multi_goal_orchestration.py` (add helper method)
**Acceptance:**
- [ ] `add_capability_goal()` helper method in GoalOrchestrator
- [ ] Uses `metadata` field for goal categorization (not new goal type)
- [ ] Sets `metadata["goal_category"] = "capability_acquisition"`
- [ ] Dependency tracking for capability learning via ENABLES relationships
- [ ] Priority handling for learning tasks (default: NORMAL, not CRITICAL)
- [ ] Resource allocation via metadata cost tracking
**Dependencies:** Task 5.1
**Domain:** Backend

### Task 5.3: Add Monitoring and Observability
**Description:** Track learning metrics and health with alerting
**Files:**
- Create: `tools/kurultai/learning_monitor.py` (~250 lines)
**Acceptance:**
- [ ] Learning success/failure metrics
- [ ] Cost per capability tracking
- [ ] Time-to-mastery statistics
- [ ] Alerting for failed learnings
- [ ] Dashboard queries for Neo4j
- [ ] **Security:** Audit logging for all learning attempts
- [ ] **Security:** Anomaly detection for unusual learning patterns
**Dependencies:** Task 5.1
**Domain:** Backend

---

## Phase 6: Documentation & Testing

**Status:** Pending
**Tasks:** 2
**Parallelizable:** Yes

### Task 6.1: Create Comprehensive Tests
**Description:** Unit and integration tests for horde-learn Kurultai
**Files:**
- Create: `tests/kurultai/test_horde_learn_adapter.py`
- Create: `tests/kurultai/test_capability_classifier.py`
- Create: `tests/kurultai/test_capability_registry.py`
- Create: `tests/kurultai/test_sandbox_executor.py`
- Create: `tests/kurultai/test_security_filters.py`
**Acceptance:**
- [ ] 80%+ test coverage
- [ ] Mock Neo4j for tests
- [ ] Mock agent delegation
- [ ] End-to-end learning scenario tests
- [ ] Failure mode tests
- [ ] **Security:** Prompt injection test cases
- [ ] **Security:** Sandbox escape attempt tests
- [ ] **Security:** Cost limit enforcement tests
- [ ] **Security:** Circular delegation detection tests
- [ ] **Security:** CBAC enforcement tests (capability grants, revocations, expiration)
**Dependencies:** Task 5.1
**Domain:** Backend

### Task 6.2: Create Documentation
**Description:** Usage guide and architecture documentation
**Files:**
- Create: `docs/horde-learn-kurultai.md`
- Create: `docs/capability-acquisition-guide.md`
- Create: `docs/security/sandbox-security.md`
**Acceptance:**
- [ ] Architecture overview
- [ ] Usage examples for each agent
- [ ] Troubleshooting guide
- [ ] Cost estimation guide
- [ ] **Security:** Security architecture documentation
- [ ] **Security:** Threat model and mitigations
- [ ] **Security:** CBAC documentation (capability grant workflows, trust levels)
- [ ] **CRITICAL:** Document all fixes applied from critical review
**Dependencies:** Task 6.1
**Domain:** Documentation

---

## Dependencies

```
Phase 1 (Foundation)
    ├── Task 1.1 (Security) ──┬── Task 1.3 (Adapter)
    │                         │
    ├── Task 1.2 (Sandbox) ───┤
    │                         │
    ├── Task 1.4 (Taxonomy) ──┤
    │                         │
    └── Task 1.5 (Jochi AST) ─┴── Task 2.1 (Classifier)

Phase 2 (Classification/Research)
    ├── Task 2.1 ──┬── Task 3.1 (Templates)
    │              │
    ├── Task 2.2 ──┼── Task 3.2 (Implementation)
    │              │
    └── Task 2.3 ──┴── Task 3.3 (Capability Registry)

Phase 3 (Implementation)
    ├── Task 3.1 ──┬── Task 4.1 (Validation)
    ├── Task 3.2 ──┤
    ├── Task 3.3 ──┤
    └── Task 3.4 ──┴── Task 5.1 (Orchestration)

Phase 4 (Validation)
    ├── Task 4.1 ──┬── Task 5.1
    ├── Task 4.2 ──┤
    └── Task 4.3 ──┴── Task 6.1 (Tests)

Phase 5 (Integration)
    ├── Task 5.1 ──┬── Task 6.1
    ├── Task 5.2 ──┤
    └── Task 5.3 ──┴── Task 6.2 (Docs)

Phase 6 (Docs/Tests)
    └── Tasks 6.1, 6.2 (parallel)
```

---

## Critical Files to Modify

| File | Purpose | Changes |
|------|---------|---------|
| `tools/delegation_protocol.py` | Agent routing | Add capability learning keywords to AGENT_ROUTING |
| `openclaw_memory.py` | Neo4j interface | Add `store_capability_research()`, `get_capability_research()` methods after line 4125 |
| `tools/multi_goal_orchestration.py` | Goal management | Add `add_capability_goal()` helper method |
| `tools/kurultai/types.py` | Type definitions | Add `LearnedCapability` dataclass |

---

## New Files to Create

| File | Lines | Purpose |
|------|-------|---------|
| `tools/kurultai/security/prompt_injection_filter.py` | ~150 | Input sanitization |
| `tools/kurultai/security/cost_enforcer.py` | ~200 | Budget enforcement |
| `tools/kurultai/security/static_analysis.py` | ~250 | Code security scanning |
| `tools/kurultai/sandbox_executor.py` | ~400 | Subprocess-based sandbox execution |
| `tools/kurultai/sandbox/subprocess_executor.py` | ~300 | Resource limit enforcement |
| `tools/kurultai/horde_learn_adapter.py` | ~500 | Main adapter class |
| `tools/kurultai/capability_classifier.py` | ~600 | Hybrid classification |
| `tools/kurultai/capability_taxonomy_kurultai.py` | ~300 | Taxonomy data |
| `tools/kurultai/research_delegation.py` | ~250 | Research phase |
| `tools/kurultai/implementation_delegation.py` | ~300 | Implementation phase |
| `tools/kurultai/validation_delegation.py` | ~300 | Validation phase |
| `tools/kurultai/capability_registry.py` | ~350 | Capability registry |
| `tools/kurultai/capability_tester.py` | ~400 | Testing framework |
| `tools/kurultai/learning_monitor.py` | ~250 | Monitoring |
| `templates/capabilities/*.j2` | ~100 each | Code templates |
| `tests/kurultai/test_*.py` | ~300 each | Test suites |
| `docs/horde-learn-kurultai.md` | ~400 | Documentation |
| `docs/security/sandbox-security.md` | ~300 | Security docs |
| **Jochi Static Analysis (Task 1.5)** |||
| `tools/kurultai/static_analysis/__init__.py` | ~50 | Module exports |
| `tools/kurultai/static_analysis/ast_parser.py` | ~300 | Tree-sitter wrapper |
| `tools/kurultai/static_analysis/rule_engine.py` | ~250 | YAML rule engine |
| `tools/kurultai/static_analysis/rules/*.yaml` | ~50 each | Detection rules (20+ files) |

---

## Agent Naming Reference

| Agent ID (for code) | Display Name | Role |
|---------------------|--------------|------|
| `main` | Kublai | Orchestrator |
| `researcher` | Möngke | Research |
| `developer` | Temüjin | Code generation |
| `analyst` | Jochi | Analysis/Validation |
| `writer` | Chagatai | Content creation |
| `ops` | Ögedei | Operations |

**Important:** Use Agent IDs (left column) for all routing, delegation, and Neo4j storage. Use Display Names only for user-facing output.

---

## Jochi-Temüjin Backend Analysis Workflow

### Overview
Jochi (analyst) performs backend code analysis and delegates fixes to Temüjin (developer). This workflow is **already implemented** in `tools/backend_collaboration.py` and integrated with the capability learning system.

### Trigger Conditions

| Trigger Type | Frequency | Scope | Implementation |
|--------------|-----------|-------|----------------|
| **Kublai Directive** | On-demand | Specified files | `agentToAgent` message to `analyst` |
| **Scheduled Scan** | Every 4 hours | Modified backend files | Ögedei's proactive monitoring |
| **Event-Based** | Real-time | Changed files | File watcher webhook |
| **Post-Implementation** | After code generation | Generated capability code | Task 3.2 integration hook |

### Workflow: Jochi Finds Issue → Kublai Routes → Temüjin Fixes

```python
# Step 1: Jochi analyzes code and creates Analysis node
from tools.backend_collaboration import BackendCodeReviewer

reviewer = BackendCodeReviewer(memory)
analysis_id = reviewer.create_backend_analysis(
    category="connection_pool",  # One of 5 categories
    findings="Missing connection pool configuration",
    location="src/database.py:42",
    severity="high",
    recommended_fix="Add psycopg2.pool.ThreadedConnectionPool",
    target="src/database.py"
)

# Step 2: Kublai queries and delegates to Temüjin
query = """
MATCH (a:Analysis)
WHERE a.agent = 'jochi'
  AND a.status = 'open'
  AND a.severity IN ['critical', 'high']
  AND a.assigned_to = 'temujin'
RETURN a.id as analysis_id, a.description as title, a.severity as severity
"""

# Step 3: Temüjin implements fix
# (Temüjin receives delegation via agentToAgent, implements fix)

# Step 4: Jochi validates the fix
validation = reviewer.validate_fix(
    analysis_id=analysis_id,
    fix_summary="Added ThreadedConnectionPool with max 20 connections",
    validation_results={"pool_configured": True, "max_connections": 20}
)

# Step 5: Analysis status updated
# - 'validated' if fix addresses issue
# - 'reopened' if validation fails
```

### Category Mapping

| Jochi Category | analysis_type | Assigned To | Priority |
|----------------|---------------|-------------|----------|
| connection | resource | temujin | high |
| resilience | resource | temujin | high |
| data_integrity | error | temujin | high |
| performance | performance | temujin | medium |
| security | security | temujin | critical |

### Integration with Capability Learning

When Temüjin generates a new capability (Phase 3.2), Jochi automatically reviews the generated code:

```python
# In ImplementationDelegation (Task 3.2)
from tools.kurultai.static_analysis.ast_parser import ASTParser

class ImplementationDelegation:
    def generate_and_review(self, capability_request):
        # Generate code (existing)
        generated_code = self.generate_code(capability_request)

        # NEW: Jochi AST-based review
        parser = ASTParser()
        issues = parser.analyze_code(generated_code)

        if any(i.severity == 'critical' for i in issues):
            # Block registration, create Analysis nodes
            for issue in issues:
                self.memory.create_analysis(
                    agent='jochi',
                    analysis_type=self._map_category(issue.category),
                    severity=issue.severity,
                    description=issue.title,
                    findings={'location': issue.location, 'category': issue.category},
                    recommendations=[issue.recommended_fix],
                    assigned_to='temujin'
                )
            return {'status': 'blocked', 'reason': 'critical_issues_found'}

        # Proceed with registration
        return self.register_capability(generated_code)
```

---

## Neo4j Schema Extensions

```cypher
// Extend :Research node (NOT new :CapabilityResearch)
(:Research {
    // ... existing fields from neo4j.md ...
    research_type: "capability_learning",  // NEW
    capability_name: string,
    findings: string,
    sources: [string],
    reliability_score: float,
    embedding: [float],         // 384-dim vector
    access_tier: string,        // 'PUBLIC', 'SENSITIVE', 'PRIVATE'
    created_at: datetime
})

// New node type for learned capabilities (REPLACES SOUL.md modification)
(:LearnedCapability {
    id: string,
    name: string,
    agent: string,              // Which agent can use this
    tool_path: string,          // Path to generated tool
    version: string,            // Semantic version
    learned_at: datetime,
    cost: float,                // Actual cost to learn
    mastery_score: float,       // From validation
    risk_level: string,         // LOW, MEDIUM, HIGH
    signature: string,          // Cryptographic signature
    claimed_by: string,         // For atomic registration
    claimed_at: datetime,       // For race condition handling
    required_capabilities: [string],  // CBAC: List of capability IDs needed to use this tool
    min_trust_level: string           // CBAC: Minimum agent trust level (LOW, MEDIUM, HIGH)
})

// Capability node type for CBAC (Capability-Based Access Control)
(:Capability {
    id: string,
    name: string,
    description: string,
    risk_level: string,  // LOW, MEDIUM, HIGH
    created_at: datetime
})

// AgentKey node type for Agent Authentication (HMAC-SHA256 key storage)
(:AgentKey {
    id: string,
    key_hash: string,      // SHA256 hash of the key (never store plaintext)
    created_at: datetime,
    expires_at: datetime,  // 90-day rotation
    is_active: boolean
})

// Analysis node for Jochi backend monitoring (from neo4j.md Phase 4.6)
(:Analysis {
    id: string,
    agent: string,              // 'jochi' (analyst)
    target_agent: string,       // Agent whose code is analyzed
    analysis_type: string,      // 'performance', 'resource', 'error', 'security', 'other'
    category: string,           // 'connection_pool', 'resilience', 'data_integrity', 'performance', 'security'
    severity: string,           // 'low', 'medium', 'high', 'critical'
    description: string,        // Issue title/summary
    findings: string,           // JSON-serialized dict (stored as string in Neo4j)
    recommendations: string,    // JSON-serialized list of fix suggestions
    assigned_to: string,        // 'temujin' for backend fixes
    status: string,             // 'open', 'in_progress', 'resolved', 'validated', 'closed'
    identified_by: string,      // 'jochi'
    requires_implementation_by: string,  // 'temujin'
    created_at: datetime,
    updated_at: datetime,
    resolved_at: datetime
})

// Relationships
(Agent)-[:CREATED {category: 'capability_learning', timestamp: datetime()}]->(Research)
(Agent)-[:HAS_LEARNED_CAPABILITY {learned_at: datetime()}]->(LearnedCapability)

// CBAC Relationships
(Agent)-[:HAS_CAPABILITY {
    granted_at: datetime,
    expires_at: datetime,  // Optional, for temporary grants
    granted_by: string     // Which agent/admin granted
}]->(Capability)

// Agent Authentication Relationships
(Agent)-[:HAS_KEY {
    granted_at: datetime
}]->(AgentKey)

// Jochi Backend Analysis Relationships (Phase 4.6 from neo4j.md)
(Agent {id: 'analyst'})-[:CREATED]->(Analysis)
(Analysis)-[:INFORMED_BY]->(Research)           // Analysis references research context
(Analysis)-[:SUGGESTS_CAPABILITY {confidence: float, extracted_pattern: string}]->(LearnedCapability)
(Application)-[:ADDRESSES]->(Analysis)          // Temüjin's fix addresses Jochi's finding
(LearnedCapability)-[:PREVENTS]->(Analysis)     // Learned capability prevents recurring issues

// Indexes
CREATE INDEX capability_research_lookup IF NOT EXISTS FOR (r:Research) ON (r.capability_name, r.agent) WHERE r.research_type = 'capability_learning';
CREATE VECTOR INDEX capability_research_embedding IF NOT EXISTS FOR (r:Research) ON r.embedding OPTIONS {indexConfig: {`vector.dimensions`: 384, `vector.similarity_function`: 'cosine'}};
CREATE INDEX learned_capability_agent IF NOT EXISTS FOR (lc:LearnedCapability) ON (lc.agent, lc.name);
CREATE INDEX analysis_agent_status IF NOT EXISTS FOR (a:Analysis) ON (a.agent, a.status, a.severity);
CREATE INDEX analysis_assigned_lookup IF NOT EXISTS FOR (a:Analysis) ON (a.assigned_to, a.status) WHERE a.status = 'open';

// CBAC Indexes
CREATE INDEX capability_name IF NOT EXISTS FOR (c:Capability) ON (c.name);
CREATE INDEX agent_capability_lookup IF NOT EXISTS FOR ()-[r:HAS_CAPABILITY]-() ON (r.expires_at);

// Agent Authentication Indexes
CREATE INDEX agent_key_lookup IF NOT EXISTS FOR (k:AgentKey) ON (k.is_active, k.expires_at);
```

---

## Neo4j Schema Migration

When extending the `:Research` node with new properties (`research_type`, `capability_name`, etc.), existing research data must be backfilled to ensure the system remains operational during schema evolution.

### Migration Script

Create `scripts/migrate_research_schema.py`:

```python
#!/usr/bin/env python3
"""Neo4j schema migration for Research node extension.

Backfills existing Research nodes with research_type='general'.
Run this BEFORE deploying code that depends on the new schema.
"""

import logging
from datetime import datetime
from neo4j import GraphDatabase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate_research_nodes(neo4j_uri: str, neo4j_user: str, neo4j_password: str):
    """Backfill all existing Research nodes with research_type='general'."""
    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))

    try:
        with driver.session() as session:
            # Step 1: Backfill existing Research nodes
            result = session.run("""
                MATCH (r:Research)
                WHERE r.research_type IS NULL
                SET r.research_type = 'general',
                    r.migrated_at = datetime()
                RETURN count(r) as migrated
            """)
            record = result.single()
            migrated = record["migrated"] if record else 0
            logger.info(f"Migrated {migrated} Research nodes to research_type='general'")

            # Step 2: Verify no nodes remain with null research_type
            result = session.run("""
                MATCH (r:Research)
                WHERE r.research_type IS NULL
                RETURN count(r) as remaining
            """)
            record = result.single()
            remaining = record["remaining"] if record else 0

            if remaining > 0:
                raise ValueError(f"Migration incomplete: {remaining} nodes still have null research_type")

            logger.info("Migration completed successfully")
            return migrated

    finally:
        driver.close()


def rollback_migration(neo4j_uri: str, neo4j_user: str, neo4j_password: str):
    """Rollback: Remove migrated properties from Research nodes."""
    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))

    try:
        with driver.session() as session:
            result = session.run("""
                MATCH (r:Research)
                WHERE r.migrated_at IS NOT NULL
                REMOVE r.research_type, r.migrated_at
                RETURN count(r) as rolled_back
            """)
            record = result.single()
            rolled_back = record["rolled_back"] if record else 0
            logger.info(f"Rolled back {rolled_back} Research nodes")
            return rolled_back

    finally:
        driver.close()


if __name__ == "__main__":
    import os
    import sys

    if len(sys.argv) < 2 or sys.argv[1] not in ["migrate", "rollback"]:
        print("Usage: python migrate_research_schema.py [migrate|rollback]")
        sys.exit(1)

    neo4j_uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
    neo4j_password = os.environ.get("NEO4J_PASSWORD", "password")

    if sys.argv[1] == "migrate":
        migrate_research_nodes(neo4j_uri, neo4j_user, neo4j_password)
    else:
        rollback_migration(neo4j_uri, neo4j_user, neo4j_password)
```

### Migration Checklist

**Before Deployment:**
- [ ] Test migration script in staging environment
- [ ] Create database backup: `neo4j-admin dump --to=/backup/neo4j-$(date +%Y%m%d).dump`
- [ ] Verify application code handles both old and new schema (backward compatible)
- [ ] Schedule migration during low-traffic period

**During Deployment:**
1. **Create indexes first** (non-blocking operation):
   ```cypher
   CREATE INDEX capability_research_lookup IF NOT EXISTS FOR (r:Research) ON (r.capability_name, r.agent) WHERE r.research_type = 'capability_learning';
   CREATE VECTOR INDEX capability_research_embedding IF NOT EXISTS FOR (r:Research) ON r.embedding OPTIONS {indexConfig: {`vector.dimensions`: 384, `vector.similarity_function`: 'cosine'}};
   ```

2. **Run migration script**:
   ```bash
   python scripts/migrate_research_schema.py migrate
   ```

3. **Verify migration**:
   ```cypher
   MATCH (r:Research) WHERE r.research_type IS NULL RETURN count(r);
   -- Should return 0
   ```

4. **Deploy application code** that depends on new schema

**After Deployment:**
- [ ] Monitor error logs for 24 hours
- [ ] Verify new capability research creates nodes with correct research_type
- [ ] Confirm query performance with new indexes (use `PROFILE`)

### Rollback Plan

If issues arise after migration:

1. **Immediate rollback** (data preserved):
   ```bash
   python scripts/migrate_research_schema.py rollback
   ```

2. **Database restore** (if migration corrupted data):
   ```bash
   neo4j-admin load --from=/backup/neo4j-$(date +%Y%m%d).dump --force
   ```

3. **Application code rollback** to previous version

**Backup Retention:**
- Keep pre-migration backup for 7 days minimum
- Document rollback decision point (if >50% of new data created, don't rollback)

### Index Creation Ordering

**Correct order to avoid blocking:**
1. Create new indexes (non-blocking)
2. Run migration script to backfill data
3. Verify indexes are being used: `PROFILE MATCH (r:Research {research_type: 'capability_learning'}) RETURN r`
4. Remove old indexes if superseded (after 7 days of stability)

---

## Delegation Protocol (agentToAgent)

Per `neo4j.md` Section 2.2, use this pattern for all delegations:

```python
import requests
from urllib.parse import urljoin

# Validate gateway_url
if not gateway_url.startswith(('http://', 'https://')):
    raise ValueError("gateway_url must start with http:// or https://")

url = urljoin(gateway_url, "/agent/{target_agent}/message")

response = requests.post(
    url,
    headers={"Authorization": f"Bearer {token}"},
    json={
        "message": f"@{target_agent} {task_description}",
        "context": {
            "task_id": str(task_id),
            "delegated_by": "main",  # or agent_id
            "delegation_depth": current_depth + 1,
            "delegation_chain": delegation_chain + [agent_id],
            "reply_to": "main"
        }
    }
)
```

**Circular Delegation Protection:**
```python
MAX_DELEGATION_DEPTH = 3

def can_delegate(context: dict) -> bool:
    depth = context.get('delegation_depth', 0)
    chain = context.get('delegation_chain', [])

    if depth >= MAX_DELEGATION_DEPTH:
        return False
    if len(set(chain)) != len(chain):
        return False  # Cycle detected
    return True
```

---

## Security Architecture

### Defense in Depth Layers

```
Layer 1: Input Validation
├── PromptInjectionFilter.sanitize()
├── Multi-turn injection detection
└── Block dangerous capability requests

Layer 2: Privacy Sanitization
├── _sanitize_for_sharing() before delegation
├── PII pattern matching
└── LLM-based sanitization fallback

Layer 3: Capability Classification Security
├── Rule-based classification before LLM
├── Block CRITICAL-risk capabilities
└── Confidence threshold enforcement

Layer 4: Sandboxed Code Generation
├── Jinja2 SandboxedEnvironment
├── No network access during generation
└── Template injection prevention

Layer 5: Static Analysis
├── bandit security scanner (cached)
├── semgrep rule enforcement
├── AST pattern detection
└── Secret detection

Layer 6: Sandboxed Execution
├── Subprocess with resource limits (Railway-compatible)
├── RLIMIT_CPU (30s), RLIMIT_AS (512MB), RLIMIT_NOFILE (100)
├── Timeout handling via signal.SIGALRM
├── Network blocking via socket restrictions
├── Filesystem restrictions (read-only root, tmpfs for writes)
└── Restricted Python execution (no exec/eval/compile)

Layer 7: Registry Validation
├── Cryptographic signing
├── Namespace isolation (tools/kurultai/generated/)
├── Dependency verification
├── Registry access control
└── CBAC (Capability-Based Access Control)
    ├── Required capability enforcement
    ├── Agent capability grants
    ├── Expiration checking
    └── Runtime permission validation

Layer 8: Runtime Monitoring
├── Cost tracking with HARD limits
├── Circular delegation detection
├── Behavior anomaly detection
├── Audit logging
└── Human approval gates

Layer 9: Agent Authentication
├── HMAC-SHA256 message signing
├── 5-minute timestamp validation window
├── Nonce-based replay prevention
└── 90-day key rotation policy
```

### Cost Enforcement

```python
# Pre-authorization pattern with atomic Neo4j updates
class CostEnforcer:
    def authorize_spending(self, skill_id: str, estimated_cost: float) -> bool:
        query = """
        MATCH (b:Budget {skill_id: $skill_id})
        WHERE b.remaining >= $estimated_cost
        SET b.remaining = b.remaining - $estimated_cost,
            b.reserved = b.reserved + $estimated_cost
        RETURN b.remaining as remaining
        """
        result = self.neo4j.run(query, skill_id=skill_id, estimated_cost=estimated_cost)
        return result.single() is not None
```

### Agent Authentication

All agent-to-agent messages must be cryptographically signed to prevent impersonation and ensure message integrity.

```python
import hmac
import hashlib
import secrets
import time
from datetime import datetime, timedelta
from typing import Optional

class AgentAuthenticator:
    """HMAC-SHA256 based agent authentication with replay protection."""

    def __init__(self, neo4j_client):
        self.neo4j = neo4j_client
        self.used_nonces = set()  # In production, use Redis with TTL
        self.timestamp_window = timedelta(minutes=5)

    def sign_message(self, agent_id: str, message: dict,
                     timestamp: str, nonce: str) -> str:
        """Create HMAC-SHA256 signature for a message."""
        key = self._get_agent_key(agent_id)

        # Canonical payload: agent_id:timestamp:nonce:json_message
        payload = f"{agent_id}:{timestamp}:{nonce}:{json.dumps(message, sort_keys=True)}"

        return hmac.new(
            key.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()

    def verify_message(self, agent_id: str, message: dict,
                       signature: str, timestamp: str, nonce: str) -> bool:
        """Verify message signature and prevent replay attacks."""
        # Check timestamp window (prevent old messages)
        msg_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        if datetime.now(timezone.utc) - msg_time > self.timestamp_window:
            return False  # Message too old

        # Check nonce (prevent replay)
        if nonce in self.used_nonces:
            return False  # Replay detected
        self.used_nonces.add(nonce)

        # Verify signature
        expected = self.sign_message(agent_id, message, timestamp, nonce)
        return hmac.compare_digest(signature, expected)

    def _get_agent_key(self, agent_id: str) -> str:
        """Retrieve agent's signing key from Neo4j."""
        query = """
        MATCH (a:Agent {id: $agent_id})-[:HAS_KEY]->(k:AgentKey)
        WHERE k.is_active = true
        AND (k.expires_at IS NULL OR k.expires_at > datetime())
        RETURN k.key_hash as key_hash
        ORDER BY k.created_at DESC
        LIMIT 1
        """
        result = self.neo4j.run(query, agent_id=agent_id)
        record = result.single()
        if not record:
            raise ValueError(f"No active key found for agent: {agent_id}")
        return record["key_hash"]

    def rotate_key(self, agent_id: str) -> str:
        """Generate new signing key for agent (90-day rotation)."""
        new_key = secrets.token_hex(32)

        # Deactivate old keys
        deactivate_query = """
        MATCH (a:Agent {id: $agent_id})-[r:HAS_KEY]->(k:AgentKey)
        SET k.is_active = false
        """
        self.neo4j.run(deactivate_query, agent_id=agent_id)

        # Create new key
        create_query = """
        MATCH (a:Agent {id: $agent_id})
        CREATE (k:AgentKey {
            id: $key_id,
            key_hash: $key_hash,
            created_at: datetime(),
            expires_at: datetime() + duration('P90D'),
            is_active: true
        })
        CREATE (a)-[:HAS_KEY {granted_at: datetime()}]->(k)
        RETURN k.id as key_id
        """
        result = self.neo4j.run(
            create_query,
            agent_id=agent_id,
            key_id=secrets.token_urlsafe(16),
            key_hash=hashlib.sha256(new_key.encode()).hexdigest()
        )
        return new_key
```

**Delegation Protocol with Authentication:**

```python
import requests
from urllib.parse import urljoin
import secrets
from datetime import datetime, timezone

# Generate auth parameters
timestamp = datetime.now(timezone.utc).isoformat()
nonce = secrets.token_urlsafe(16)

# Sign message
auth = AgentAuthenticator(neo4j_client)
signature = auth.sign_message(
    agent_id="jochi",
    message={"task": "analyze_code"},
    timestamp=timestamp,
    nonce=nonce
)

# Send authenticated request
response = requests.post(
    urljoin(gateway_url, "/agent/analyst/message"),
    headers={"Authorization": f"Bearer {token}"},
    json={
        "message": "@analyst analyze this code",
        "context": {"task_id": "123"},
        "auth": {
            "agent_id": "jochi",
            "timestamp": timestamp,
            "nonce": nonce,
            "signature": signature
        }
    }
)
```

**Security Properties:**
- **Authentication**: HMAC-SHA256 proves message originated from claimed agent
- **Integrity**: Any message modification invalidates the signature
- **Replay Protection**: 5-minute timestamp window + nonce tracking prevents old messages from being reused
- **Timing Attack Resistance**: `hmac.compare_digest()` uses constant-time comparison
- **Key Rotation**: 90-day expiration with automatic key rotation workflow

---

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Arbitrary code execution | CRITICAL | Subprocess sandbox, RLIMIT enforcement, network filtering |
| SOUL.md tampering | CRITICAL | **REMOVED** - replaced with Neo4j registry |
| Circular delegation | CRITICAL | Max depth 3, delegation chain tracking |
| Prompt injection | HIGH | Input sanitization, output filtering, multi-turn detection |
| Cost overruns | HIGH | Pre-authorization, hard limits, kill switch |
| Tool registry pollution | CRITICAL | Namespace isolation, signing, access control, limits |
| Sandbox escape | CRITICAL | Subprocess resource limits, minimal attack surface, no root |
| Generated code backdoors | HIGH | Static analysis, independent validation |
| Secret exposure | HIGH | Secret scanning, vault integration |
| Validation bypass | MEDIUM | Cross-agent review, human gates |
| Neo4j schema conflicts | LOW | Extends `:Research` instead of new node type |
| **Privilege escalation via capability registry** | **CRITICAL** | **CBAC with required_capabilities, runtime checks, capability grants** |
| **Agent impersonation / message tampering** | **CRITICAL** | **HMAC-SHA256 message signing, 5-minute timestamp window, nonce-based replay protection** |
| **Data loss during schema migration** | **HIGH** | **Migration script with verification, rollback plan, 7-day backup retention** |

---

## Critical Review Summary

This plan was critically reviewed against:
- `neo4j.md` - Neo4j implementation plan
- `kurultai_0.1.md` - Task Dependency Engine
- `tools/delegation_protocol.py` - Existing delegation interface
- `openclaw_memory.py` - Neo4j operational memory
- Official OpenClaw documentation

### Fixes Applied

| Issue | Severity | Fix |
|-------|----------|-----|
| Delegation interface mismatch | Critical | Use `gateway_url` + `agentToAgent` |
| Neo4j schema conflict | Critical | Extend `:Research` node |
| gVisor unavailable | Critical | Use `nsjail` instead |
| Circular delegation risk | Critical | Add max depth 3 |
| Missing PII sanitization | High | Mandatory `_sanitize_for_sharing()` |
| Static analysis latency | High | Implement caching + tiered checks |
| Cost enforcer race condition | Medium | Atomic Neo4j updates |
| **Privilege escalation via capability registry** | **Critical** | **Add CBAC with required_capabilities, runtime checks, capability grants** |
| **Agent impersonation / message tampering** | **Critical** | **Add HMAC-SHA256 message signing with replay protection (Layer 9)** |
| **Neo4j schema lacks migration strategy** | **Critical** | **Add migration script, backfill procedure, rollback plan, deployment checklist** |

### Jochi Integration Review (2026-02-05)

A multi-agent swarm review assessed integrating Jochi's backend monitoring plan into kurultai_0.2.md:

| Finding | Assessment | Resolution |
|---------|------------|------------|
| **Existing Implementation** | `tools/backend_collaboration.py` (1,084 lines) already implements Jochi-Temüjin collaboration | Leverage existing, add AST enhancement as Task 1.5 |
| **Scope Creep Risk** | Full 5-phase tree-sitter system would duplicate existing capability | Integrate as single enhancement task, not new phase |
| **Tree-sitter vs nsjail** | Native dependency complexity conflicts with Railway-compatible sandbox | Add safeguards (file size, parse time, AST depth limits) |
| **Neo4j Schema** | Analysis nodes already defined in `openclaw_memory.py` | Document relationships to Research/LearnedCapability |
| **Agent Role Clarity** | Jochi has dual role: capability validation + backend analysis | Document prioritization rules |

**Resolution:** Added Task 1.5 (Jochi Static Analysis Enhancement) to Phase 1, integrated with existing `BackendCodeReviewer` rather than building new 5-phase system.

---

## Appendix B: Agent Teams Integration (Option B - Full Integration)

> **Status:** Design Document Addendum
> **Date:** 2026-02-05
> **Prerequisites:** This appendix extends Kurultai v0.2 with Claude Code Agent Teams capability

### Overview

**Goal:** Enhance the capability acquisition pipeline by making each phase (Research, Implementation, Validation) a coordinated agent team rather than individual agent delegation.

**Key Enhancement:** The 6 Kurultai agents become **Team Leads** that spawn and coordinate peer teams for complex capability acquisition tasks.

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CAPABILITY ACQUISITION WITH AGENT TEAMS                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   User: "Learn Stripe integration"                                           │
│        │                                                                     │
│        ▼                                                                     │
│   ┌─────────┐    Complexity Analysis (0.85 → Full Team)                     │
│   │ Kublai  │──────────────────────────────────────────────────┐            │
│   │(Meta-   │                                                  │            │
│   │Coordinator)│                                               │            │
│   └────┬────┘                                                  │            │
│        │                                                        │            │
│        │ Spawn Research Team                                   │            │
│        ▼                                                        │            │
│   ┌─────────────────────────────────────────────────────┐      │            │
│   │  RESEARCH TEAM (Möngke Lead)                         │      │            │
│   │  ┌────────┐ ◄► ┌────────┐ ◄► ┌────────┐            │      │            │
│   │  │Möngke  │    │Research│    │Pattern │            │      │            │
│   │  │(Lead)  │    │ Peer 1 │    │Analyzer│            │      │            │
│   │  └────┬───┘    └────────┘    └────────┘            │      │            │
│   │       │                                            │      │            │
│   │       └─► :Research {type: "capability_learning"}  │      │            │
│   └─────────────────────────────────────────────────────┘      │            │
│        │                                                       │            │
│        │ Phase Transition (Research → Implementation)          │            │
│        ▼                                                       │            │
│   ┌─────────────────────────────────────────────────────┐      │            │
│   │  IMPLEMENTATION TEAM (Temüjin Lead)                  │      │            │
│   │  ┌────────┐ ◄► ┌────────┐ ◄► ┌────────┐            │      │            │
│   │  │Temüjin │    │Module  │    │Security│            │      │            │
│   │  │(Lead)  │    │Developer│   │Reviewer│            │      │            │
│   │  └────┬───┘    └────────┘    └────────┘            │      │            │
│   │       │                                            │      │            │
│   │       └─► :LearnedCapability in Registry           │      │            │
│   └─────────────────────────────────────────────────────┘      │            │
│        │                                                       │            │
│        │ Phase Transition (Implementation → Validation)        │            │
│        ▼                                                       │            │
│   ┌─────────────────────────────────────────────────────┐      │            │
│   │  VALIDATION TEAM (Jochi Lead)                        │      │            │
│   │  ┌────────┐ ◄► ┌────────┐ ◄► ┌────────┐            │      │            │
│   │  │ Jochi  │    │ Peer   │    │Security│            │      │            │
│   │  │(Lead)  │    │Reviewer│    │Validator│           │      │            │
│   │  └────┬───┘    └────────┘    └────────┘            │      │            │
│   │       │                                            │      │            │
│   │       └─► Updates :LearnedCapability with score    │      │            │
│   └─────────────────────────────────────────────────────┘      │            │
│        │                                                       │            │
│        └───────────────────────────────────────────────────────┘            │
│        │                                                                     │
│        ▼                                                                     │
│   ┌─────────┐                                                               │
│   │ Kublai  │  Synthesizes: "Stripe capability learned (mastery: 0.92)"     │
│   └─────────┘                                                               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Team Lead Assignments

| Phase | Team Lead | Agent ID | Team Composition | Peer Specialists |
|-------|-----------|----------|------------------|------------------|
| **Research** | Möngke | `researcher` | 1-3 peers | Domain Specialist, Info Gatherer, Pattern Analyst |
| **Implementation** | Temüjin | `developer` | 2-4 peers | Module Developer, Security Reviewer, Test Engineer |
| **Validation** | Jochi | `analyst` | 2-4 peers | Peer Reviewer, Security Validator, Integration Tester |
| **Meta-Coordination** | Kublai | `main` | N/A (spawns/destroys teams) | Synthesizes across all teams |
| **Infrastructure** | Ögedei | `ops` | On-demand | Monitoring, emergency response |

### Complexity-Based Team Sizing

```python
class TeamSizeClassifier:
    """Determine team size based on capability complexity."""

    def classify(self, capability_request: str) -> TeamConfiguration:
        complexity = self.calculate_complexity(capability_request)

        if complexity < 0.6:
            # Simple capability - individual agent
            return IndividualAgent()
        elif complexity < 0.8:
            # Moderate complexity - small team
            return TeamConfiguration(
                lead="specialist",
                peers=2,
                coordination_mode="lightweight"
            )
        else:
            # High complexity - full team
            return TeamConfiguration(
                lead="specialist",
                peers=4,
                coordination_mode="full",
                security_review_required=True
            )
```

### Neo4j Schema Extensions for Teams

**New Node Types:**

```cypher
// Agent Team tracking
(:AgentTeam {
    id: string,
    name: string,
    lead_agent: string,           // Agent ID of team lead
    task_id: string,              // Associated capability task
    phase: string,                // 'research' | 'implementation' | 'validation'
    status: string,               // 'spawning' | 'active' | 'shutting_down' | 'destroyed'
    member_count: integer,
    max_members: integer,
    aggregation_mode: string,     // 'consensus' | 'vote' | 'hierarchical'
    created_at: datetime,
    completed_at: datetime
})

// Team membership
(:Agent)-[:MEMBER_OF {
    role: string,                 // 'lead' | 'peer'
    joined_at: datetime,
    departed_at: datetime,
    reason: string
}]->(:AgentTeam)

// Team task assignment
(:AgentTeam)-[:EXECUTING {
    assigned_at: datetime,
    progress: float              // 0.0 to 1.0
}]->(:Task)

// Team message audit (for security)
(:TeamMessage {
    id: string,
    team_id: string,
    sender: string,
    message_type: string,         // 'coordination' | 'result' | 'escalation'
    content_hash: string,         // HMAC-SHA256 of sanitized content
    timestamp: datetime
})

// Team results aggregation
(:TeamResult {
    id: string,
    team_id: string,
    aggregation_mode: string,
    individual_results: [string],
    final_result: string,
    confidence: float,
    created_at: datetime
})
```

**Indexes:**
```cypher
CREATE INDEX team_lookup IF NOT EXISTS FOR (t:AgentTeam) ON (t.task_id, t.status);
CREATE INDEX team_lead_lookup IF NOT EXISTS FOR (t:AgentTeam) ON (t.lead_agent, t.status);
CREATE INDEX team_message_audit IF NOT EXISTS FOR (m:TeamMessage) ON (m.team_id, m.timestamp);
```

### Security Controls for Teams

**1. Message Signing (HMAC-SHA256)**
```python
class TeamMessageSecurity:
    """All peer-to-peer team messages must be signed."""

    def sign_message(self, message: str, team_id: str,
                     sender: str, team_key: bytes) -> str:
        """Generate HMAC-SHA256 signature for team message."""
        payload = f"{team_id}:{sender}:{message}:{datetime.utcnow().isoformat()}"
        return hmac.new(team_key, payload.encode(), hashlib.sha256).hexdigest()

    def verify_message(self, message: TeamMessage, team_key: bytes) -> bool:
        """Verify message authenticity."""
        expected = self.sign_message(
            message.content, message.team_id, message.sender, team_key
        )
        return hmac.compare_digest(message.signature, expected)
```

**2. Team Access Control (CBAC Extension)**
```python
class TeamCapabilityAccess:
    """Team-scoped capability grants."""

    def grant_to_team(self, capability: str, team_id: str,
                      lead_id: str, constraints: Dict) -> DelegationToken:
        """Grant capability to team (not automatically to all members)."""
        # Only team lead can activate the capability
        # Members must be explicitly granted by lead
        # All grants expire when team disbands
        pass
```

**3. Resource Limits**
- Max 1 team per session (Claude Code limitation)
- Max 6 members per team (prevents token explosion)
- Max 2 teams spawned per hour per agent
- Team auto-destroy after 60 minutes of inactivity

### Integration with Task Dependency Engine

```python
class TeamAwareTopologicalExecutor:
    """Extends TopologicalExecutor to handle team-based tasks."""

    def get_ready_tasks(self, sender_hash: str) -> List[Task]:
        """Get tasks ready for execution, including team tasks."""
        # 1. Get individual tasks (no unmet BLOCKS edges)
        individual_tasks = super().get_ready_tasks(sender_hash)

        # 2. Get team tasks ready for activation
        team_tasks = self.get_ready_team_tasks(sender_hash)

        # 3. Merge and sort by priority
        return self.merge_and_prioritize(individual_tasks, team_tasks)

    def execute_team_task(self, team_task: TeamTask) -> TaskResult:
        """Execute a task using an agent team."""
        # 1. Spawn team with appropriate lead and peers
        team = self.spawn_team(team_task)

        # 2. Delegate sub-tasks to team members
        for member in team.members:
            self.delegate_to_member(member, team_task.get_subtask(member.role))

        # 3. Wait for results (with timeout)
        results = self.collect_team_results(team, timeout=1800)

        # 4. Aggregate based on aggregation_mode
        return self.aggregate_results(results, team_task.aggregation_mode)
```

### Phase-by-Phase Team Integration

**Phase 1: Research (Möngke Team Lead)**
```python
# File: tools/kurultai/research_delegation.py

class ResearchTeamDelegation:
    """Research phase with agent team support."""

    async def research_with_team(self, capability_name: str,
                                  complexity: float) -> ResearchResult:
        if complexity < 0.6:
            # Use individual Möngke (original behavior)
            return await self.delegate_to_mongke(capability_name)

        # Spawn research team
        team = await self.spawn_research_team(
            lead="researcher",
            peers=self.calculate_research_peers(complexity),
            capability=capability_name
        )

        # Parallel research tasks
        tasks = [
            team.delegate("api_discovery", "Find all relevant APIs"),
            team.delegate("documentation_extraction", "Extract key patterns"),
            team.delegate("pattern_analysis", "Analyze implementation patterns"),
        ]

        # Peer review within team
        results = await team.execute_with_peer_review(tasks)

        # Aggregate and store
        return await self.aggregate_research_results(results)
```

**Phase 2: Implementation (Temüjin Team Lead)**
```python
# File: tools/kurultai/implementation_delegation.py

class ImplementationTeamDelegation:
    """Implementation phase with agent team support."""

    async def implement_with_team(self, research: ResearchResult,
                                   complexity: float) -> ImplementationResult:
        if complexity < 0.6:
            return await self.delegate_to_temujin(research)

        # Spawn implementation team
        team = await self.spawn_implementation_team(
            lead="developer",
            peers=["module_dev", "security_reviewer", "test_engineer"]
        )

        # Parallel implementation with real-time security review
        code_result = await team.lead.delegate("generate_code", research)

        # Peer security review (parallel)
        security_result = await team.get_peer("security_reviewer").review(code_result)

        # Address security findings within team
        if security_result.findings:
            await team.lead.delegate("remediate", security_result.findings)

        # Test generation
        test_result = await team.get_peer("test_engineer").generate_tests(code_result)

        return ImplementationResult(code=code_result, tests=test_result)
```

**Phase 3: Validation (Jochi Team Lead)**
```python
# File: tools/kurultai/validation_delegation.py

class ValidationTeamDelegation:
    """Validation phase with agent team support."""

    async def validate_with_team(self, implementation: ImplementationResult,
                                  complexity: float) -> ValidationResult:
        if complexity < 0.6:
            return await self.delegate_to_jochi(implementation)

        # Spawn validation team
        team = await self.spawn_validation_team(
            lead="analyst",
            peers=["peer_reviewer", "security_validator", "integration_tester"]
        )

        # Parallel validation
        validations = await asyncio.gather(
            team.lead.delegate("functional_validation", implementation),
            team.get_peer("security_validator").validate(implementation),
            team.get_peer("integration_tester").test_integration(implementation),
        )

        # Consensus on mastery score
        mastery_score = team.reach_consensus(
            [v.mastery_score for v in validations]
        )

        return ValidationResult(
            mastery_score=mastery_score,
            findings=self.aggregate_findings(validations)
        )
```

### Fallback Strategies

```python
class TeamFallbackHandler:
    """Handle team failures gracefully."""

    async def handle_team_lead_failure(self, team: AgentTeam):
        """Promote senior member to lead or escalate to Kublai."""
        senior_member = max(team.members, key=lambda m: m.experience_score)
        await team.promote_to_lead(senior_member)

        if not team.has_viable_lead():
            await self.escalate_to_kublai(team)

    async def handle_hung_team(self, team: AgentTeam, timeout: int = 600):
        """Detect and recover from hung teams."""
        if team.time_since_progress() > timeout:
            # Cancel stuck members
            await team.cancel_stuck_members()

            # Continue with partial results if majority complete
            if team.completion_percentage() > 0.5:
                return await team.aggregate_partial_results()

            # Otherwise escalate
            await self.escalate_to_kublai(team)

    async def graceful_degradation(self, team_task: TeamTask):
        """Fall back to individual agents if team fails."""
        logger.warning(f"Team failed for {team_task.id}, falling back to individual")
        return await self.delegate_to_individual_agent(team_task)
```

### Cost Tracking Across Teams

```python
class TeamCostEnforcer:
    """Track and enforce costs across all team members."""

    async def pre_authorize_team_budget(self, team: AgentTeam,
                                        estimated_cost: float) -> bool:
        """Pre-authorize budget for entire team atomically."""
        # Allocate: 40% lead, 50% distributed to members, 10% contingency
        allocation = {
            team.lead: estimated_cost * 0.4,
            "members": estimated_cost * 0.5 / len(team.members),
            "contingency": estimated_cost * 0.1
        }

        # Atomic reservation in Neo4j
        return await self.atomic_budget_reservation(team.id, allocation)

    async def track_member_cost(self, team_id: str, member: str,
                                cost: float):
        """Track per-member costs in real-time."""
        cypher = """
        MATCH (t:AgentTeam {id: $team_id})
        SET t.member_costs = coalesce(t.member_costs, {}) + {$member: $cost},
            t.total_cost = coalesce(t.total_cost, 0) + $cost
        RETURN t.total_cost
        """
        total = await self.neo4j.run(cypher, team_id=team_id,
                                     member=member, cost=cost)

        if total > self.get_team_budget(team_id):
            await self.trigger_budget_exceeded(team_id)
```

### New Files Required

| File | Purpose | Lines |
|------|---------|-------|
| `tools/kurultai/team_orchestrator.py` | Team spawn/destroy lifecycle | ~400 |
| `tools/kurultai/team_security.py` | Message signing, CBAC for teams | ~350 |
| `tools/kurultai/team_cost_tracker.py` | Cross-member cost tracking | ~250 |
| `tools/kurultai/research_team.py` | Möngke research team coordination | ~300 |
| `tools/kurultai/implementation_team.py` | Temüjin implementation team | ~350 |
| `tools/kurultai/validation_team.py` | Jochi validation team | ~300 |
| `cypher/team_schema.cypher` | Neo4j schema extensions | ~150 |
| `tests/kurultai/test_agent_teams.py` | Team integration tests | ~400 |

### Dependencies

- **CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1** environment variable
- Team lead agents (Kublai, Möngke, Temüjin, Jochi) must have agent team spawn capability
- Neo4j schema v3 (with team extensions)
- Updated `TopologicalExecutor` with team awareness

### Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Token cost explosion (2.2x) | HIGH | Hard limits, auto-downgrade to individual agents |
| Team lead failure | HIGH | Auto-promote senior member, Kublai escalation |
| Consensus deadlock | HIGH | Max 3 negotiation rounds, forced escalation |
| Security: compromised teammate | CRITICAL | Message signing, isolation, emergency shutdown |
| Cascade failures | MEDIUM | Circuit breaker, per-team failure isolation |
| Message storm | MEDIUM | Batching (30s), rate limiting (60/min) |

---

## Appendix C: Golden-Horde Integration for Agent Workflows

This appendix defines how the 6-agent Kurultai system (Kublai, Möngke, Temüjin, Jochi, Chagatai, Ögedei) will leverage golden-horde collaborative patterns for workflows that benefit from inter-agent communication, iterative refinement, or structured deliberation.

**Relationship to Appendix B:** Appendix B defines how teams spawn and manage lifecycle. This appendix defines *when* and *which* golden-horde patterns the agents use, and the code integration points that enable pattern selection.

### C.1 Pattern-to-Workflow Mapping

Each golden-horde pattern maps to specific Kurultai workflows:

| Golden-Horde Pattern | Kurultai Workflow | Agents Involved | Trigger |
|---|---|---|---|
| Assembly Line | Capability acquisition pipeline | Möngke → Jochi → Temüjin → Ögedei | New capability request (Phase 3-5 of horde-learn) |
| Review Loop | Code review cycle | Temüjin (producer), Jochi (reviewer) | Any code generation task with `deliverable_type: CODE` |
| Watchdog | Security monitoring during codegen | Temüjin (implementer), Jochi (watchdog) | Tasks with `security_sensitive: true` flag |
| Consensus Deliberation | Risk/architecture decisions | Jochi + Möngke + Temüjin (experts), Kublai (facilitator) | Tasks with `collaboration_mode: consensus` or `priority_weight >= 0.8` |
| Expertise Routing | Cross-domain consultation | Primary agent + specialist on standby | Agent encounters sub-problem outside its domain |
| Contract-First Negotiation | Research output format agreement | Möngke (researcher) + Temüjin (consumer) | Research tasks that feed directly into implementation |
| Adversarial Debate | Technology selection | Two advocate agents + Jochi (judge) | Explicit "compare" or "choose between" in task description |
| Swarm Discovery | Codebase audit / incident investigation | 2-4 scouts, specialists spawned on demand | Tasks with `scope: unknown` or audit/investigation signals |

### C.2 Integration Approach 1: TopologicalExecutor Team Dispatch

**File:** `tools/kurultai/topological_executor.py`

The `TopologicalExecutor` already computes `_team_config` (individual/small_team/full_team) via `_determine_team_configuration()`. The integration extends `execute_ready_set()` to route team-mode tasks to golden-horde patterns instead of individual agent dispatch.

**Changes Required:**

1. **New method `_dispatch_to_team()`** — Called when `team_config.mode` is `small_team` or `full_team`. Selects a golden-horde pattern based on task metadata:
   - `task["collaboration_mode"]` → direct pattern mapping (e.g., `CollaborationMode.REVIEW_LOOP`)
   - `task["deliverable_type"]` + `task["complexity_score"]` → heuristic pattern selection
   - Falls back to Review Loop for small_team, Consensus Deliberation for full_team

2. **Pattern-specific team spawning** — Each pattern has a spawn template:
   ```
   Review Loop:     2 agents (producer + reviewer)
   Assembly Line:   3-6 agents (one per pipeline stage)
   Consensus:       3-5 agents (domain experts)
   Watchdog:        2-3 agents (implementer + monitor)
   ```

3. **Team lifecycle tracking** — New Neo4j relationship `(:Task)-[:EXECUTED_BY_TEAM]->(:Team)` to track which tasks were dispatched to teams vs individual agents.

**Existing code that enables this** (no changes needed):
- `_determine_team_configuration()` already returns `{"mode": "full_team", "agents": N}`
- `execute_ready_set()` already attaches `_team_config` to each task dict
- `ROUTING` table already maps `DeliverableType` to agent specializations

### C.3 Integration Approach 2: DelegationProtocol Collaboration Mode

**File:** `src/protocols/delegation.py`

The `DelegationProtocol` handles Kublai's task routing via `agentToAgent` messaging. The integration adds `collaboration_mode` detection to `delegate_task()` so that tasks with collaboration signals are routed through golden-horde patterns.

**Changes Required:**

1. **New `CollaborationMode` enum** in `tools/kurultai/types.py`:
   ```
   INDIVIDUAL          → Single agent (default, existing behavior)
   REVIEW_LOOP         → Producer/reviewer iteration
   ADVERSARIAL_DEBATE  → Structured A-vs-B with judge
   ASSEMBLY_LINE       → Sequential pipeline with backward messages
   CONSENSUS           → Multi-expert deliberation
   CONTRACT_FIRST      → Interface negotiation before implementation
   EXPERTISE_ROUTING   → Primary agent with specialist consultations
   WATCHDOG            → Real-time monitoring during execution
   SWARM_DISCOVERY     → Exploratory with dynamic team growth
   ```

2. **New method `_detect_collaboration_mode()`** on `DelegationProtocol`:
   - Analyzes task description for collaboration signals (using the Decision Matrix from golden-horde SKILL.md)
   - Checks explicit `collaboration_mode` field if set by user
   - Returns `CollaborationMode` enum value
   - Holistic intent analysis, not keyword matching

3. **Modified `delegate_task()` flow:**
   ```
   delegate_task(task)
     → _detect_collaboration_mode(task)
     → if INDIVIDUAL: existing agentToAgent dispatch (no change)
     → if team pattern: create golden-horde team via TopologicalExecutor._dispatch_to_team()
     → track team_id in Neo4j task node
   ```

4. **Signal-to-pattern mapping** (embedded in `_detect_collaboration_mode()`):

   | Signal Keywords | Detected Pattern |
   |---|---|
   | "review", "iterate", "refine", "validate" | REVIEW_LOOP |
   | "debate", "compare", "tradeoffs", "versus" | ADVERSARIAL_DEBATE |
   | "then", "after", "feeds into", "pipeline" | ASSEMBLY_LINE |
   | "agree on", "decide", "recommend", "evaluate" | CONSENSUS |
   | "audit", "investigate", "explore", "unknown scope" | SWARM_DISCOVERY |
   | "agree on API", "interface", "contract", "schema first" | CONTRACT_FIRST |
   | "consult specialist", "multi-domain", "ask expert" | EXPERTISE_ROUTING |
   | "enforce standards", "catch violations", "monitor" | WATCHDOG |

### C.4 Integration Approach 3: Agent-Initiated Team Escalation

**Mechanism:** An agent working on a task discovers it needs collaboration and requests team escalation through Kublai.

**New `agentToAgent` message type:** `team_escalation_request`

```json
{
  "type": "agentToAgent",
  "subtype": "team_escalation_request",
  "from_agent": "Temüjin",
  "to_agent": "Kublai",
  "task_id": "task-123",
  "requested_pattern": "expertise_routing",
  "reason": "Need security specialist review for auth token handling",
  "requested_specialists": ["security"],
  "urgency": "high"
}
```

**Kublai's response flow:**
1. Validate the escalation request (is the pattern appropriate? is budget available?)
2. If approved: spawn golden-horde team with requesting agent as primary, add requested specialists
3. If denied: respond with reason and alternative (e.g., "Budget exceeded, use horde-swarm instead")
4. Track escalation in Neo4j: `(:Task)-[:ESCALATED_TO]->(:Team {pattern: "expertise_routing"})`

**Budget controls:**
- Max 3 escalations per execution cycle
- Escalation adds 2x cost multiplier to task budget
- Kublai can deny escalation if team budget threshold exceeded
- Auto-downgrade: if full_team requested but budget allows only small_team, approve at reduced scale

### C.5 Implementation Priority

| Priority | Component | Approach | Effort | Impact |
|---|---|---|---|---|
| P0 | `CollaborationMode` enum | C.3 | Small | Foundation for all integration |
| P0 | `_detect_collaboration_mode()` | C.3 | Medium | Enables automatic pattern selection |
| P1 | `_dispatch_to_team()` | C.2 | Large | Core team dispatch capability |
| P1 | Review Loop for Jochi-Temüjin | C.2 | Medium | Highest-value pattern (code quality) |
| P2 | Assembly Line for capability pipeline | C.2 | Large | End-to-end capability acquisition |
| P2 | Watchdog for security-sensitive tasks | C.2 | Medium | Security during codegen |
| P3 | Agent-initiated escalation | C.4 | Large | Dynamic team formation |
| P3 | Consensus Deliberation | C.2 | Medium | Architecture decisions |
| P3 | Contract-First Negotiation | C.2 | Medium | Research-to-implementation handoff |

### C.6 New Files Required

| File | Purpose |
|---|---|
| `tools/kurultai/golden_horde_dispatcher.py` | Golden-horde pattern spawning logic (team creation, agent prompt templates, lifecycle tracking) |
| `tools/kurultai/collaboration_detector.py` | Signal analysis and `CollaborationMode` detection from task descriptions |
| `tests/kurultai/test_golden_horde_integration.py` | Integration tests for team dispatch, pattern selection, escalation |
| `tests/kurultai/test_collaboration_detection.py` | Unit tests for signal-to-pattern mapping accuracy |

### C.7 Risk Assessment

| Risk | Severity | Mitigation |
|---|---|---|
| Cost explosion from unnecessary team spawning | HIGH | Conservative detection thresholds; default to INDIVIDUAL mode; require explicit `collaboration_mode` for P0 |
| Pattern misselection (wrong golden-horde pattern) | MEDIUM | Holistic intent analysis (not keyword matching); user override via explicit `collaboration_mode` field |
| Team dispatch latency (cold start) | MEDIUM | Pre-warm common patterns (Review Loop, Assembly Line); lazy specialist spawning for Expertise Routing |
| Context exhaustion in deep nesting | HIGH | Hard limit: max 2 nesting levels (golden-horde → horde-swarm internal); no deeper |
| Agent-initiated escalation abuse | MEDIUM | Max 3 escalations per cycle; Kublai approval gate; cost multiplier tracking |
| Backward compatibility with existing single-agent dispatch | LOW | `CollaborationMode.INDIVIDUAL` is default; no behavior change unless collaboration signals detected |

### C.8 Approval Checklist for Appendix C

- [ ] `CollaborationMode` enum design reviewed
- [ ] Signal-to-pattern mapping accuracy validated
- [ ] `_dispatch_to_team()` integration with existing `execute_ready_set()` confirmed
- [ ] Agent-initiated escalation budget controls adequate
- [ ] Cost projections acceptable (2x multiplier for team tasks)
- [ ] No backward compatibility breaks with existing individual dispatch
- [ ] Golden-horde SKILL.md patterns correctly mapped to Kurultai workflows

---

## Execution Handoff

Once approved, this plan will be executed using:
- **Skill:** `horde-implement`
- **Pipeline:** senior-prompt-engineer → subagent-driven-development → implementation-status → horde-review
- **Mode:** Phase-by-phase execution with review gates
- **Specialist Routing:** Backend agents for all implementation tasks

---

## Approval

- [ ] Requirements understood
- [ ] Task breakdown acceptable
- [ ] Dependencies correct
- [ ] Risk assessment reviewed
- [ ] Critical review fixes applied
- [ ] SOUL.md modification removed (replaced with Neo4j registry)
- [ ] Security controls adequate
- [ ] Infrastructure constraints addressed (nsjail vs gVisor)
- [ ] **Jochi integration reviewed** (existing implementation leveraged)
- [ ] **Jochi-Temüjin workflow documented**
- [ ] **CBAC (Capability-Based Access Control) added** (privilege escalation prevention)
- [ ] **Agent Authentication added** (HMAC-SHA256 message signing, replay protection)
- [ ] **Neo4j Schema Migration added** (backfill script, rollback plan, deployment checklist)
- [ ] Ready for execution

**Ready to proceed?**
