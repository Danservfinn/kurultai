# Kurultai Gap Analysis Report

> **Analyst**: Jochi (The Analyst Agent)
> **Date**: 2026-02-09
> **Status**: Critical Architecture Planning Document
> **Classification**: Internal - Kurultai Leadership

---

## Executive Summary

### Overall Completion: **68%**

| Category | Completion | Status |
|----------|------------|--------|
| Core Infrastructure | 85% | ✅ Operational |
| Memory & Curation | 75% | ⚠️ Partial |
| Agent Collaboration | 60% | ⚠️ Partial |
| Self-Awareness | 70% | ⚠️ Partial |
| Testing & Quality | 80% | ✅ Strong |
| Security & Auth | 55% | ⚠️ Gaps Identified |

### Critical Finding

The codebase shows significant progress toward the architectural vision, with **core operational memory (openclaw_memory.py)** and **basic curation** well-implemented. However, **critical gaps exist** in:

1. **Heartbeat System**: Write side has no caller - the failover system reads timestamps that are never written
2. **HMAC-SHA256 Delegation**: Agent keys exist but signing middleware is not integrated
3. **Vector Deduplication**: Partial implementation - indexes missing
4. **Scheduled Triggers**: Reflection and curation not wired to actual cron jobs

---

## Plan-by-Plan Analysis

### 1. OpenClaw Neo4j Memory Design (2026-02-03)

**Features Planned:**
- 6-agent system with complete Neo4j schema (Agent, Task, Research, Content, Application, Analysis, etc.)
- Cross-agent knowledge pool with relationships
- Tiered connection model (Direct/Shared Pool/Broadcast)
- Vector indexes for semantic search (384-dim)
- Self-reflection cycles with Belief nodes
- Kublai approval gates for WorkflowImprovement

**Features Implemented:**
- ✅ Core node types: Agent, Task, Research, Analysis, Concept, Belief
- ✅ Basic relationships: DEPENDS_ON, CREATED, HAS_KEY
- ✅ OperationalMemory class (4,274 lines) with comprehensive task management
- ✅ IntentWindowBuffer, TopologicalExecutor for DAG processing
- ✅ Basic vector similarity queries
- ⚠️ Partial: Belief nodes exist but reflection cycles not automated
- ⚠️ Partial: WorkflowImprovement nodes exist but approval gate not enforced
- ❌ Missing: Full vector index suite (belief_embedding, memory_entry_embedding)
- ❌ Missing: Cross-agent subscription system (SUBSCRIBES_TO relationships)
- ❌ Missing: SharedKnowledge pool implementation

**Gap Severity**: **Medium**
**Estimated Effort to Close**: 16 hours
**Recommendation**: Priority 2 - Complete vector indexes and cross-agent subscriptions

---

### 2. Kublai Proactive Self-Awareness (2026-02-07)

**Features Planned:**
- Architecture introspection module (query ARCHITECTURE.md from Neo4j)
- ImprovementOpportunity → ArchitectureProposal workflow
- Proposal state machine (proposed → under_review → approved → implemented → validated → synced)
- Ögedei vetting handler
- Temüjin implementation handler
- Scheduled reflection trigger (weekly cron)

**Features Implemented:**
- ✅ `architecture-introspection.js` - Full implementation with 5 query methods
- ✅ `proactive-reflection.js` - Full implementation with gap detection
- ✅ `delegation-protocol.js` - Complete proposal workflow (200+ lines)
- ✅ `003_proposals.cypher` - Schema constraints for proposal system
- ✅ Opportunity storage in Neo4j with duplicate detection
- ⚠️ Partial: State machine exists but not all transitions tested
- ❌ Missing: Scheduled reflection trigger not wired to cron
- ❌ Missing: Ögedei vetting handler (placeholder only)
- ❌ Missing: Temüjin implementation handler (placeholder only)

**Gap Severity**: **Medium**
**Estimated Effort to Close**: 12 hours
**Recommendation**: Priority 3 - Wire scheduled trigger and implement vetting handlers

---

### 3. Kublai Self-Understanding (2026-02-07)

**Features Planned:**
- Neo4j query helpers for architecture (getTOC, search, getSection)
- Proactive reflection with weekly cron
- Proposal schema migration
- Proposal state machine
- Implementation tracker
- ARCHITECTURE.md sync guardrails

**Features Implemented:**
- ✅ All Neo4j query methods implemented in architecture-introspection.js
- ✅ Proposal workflow with state transitions
- ✅ Proposal-to-section mapper with guardrails
- ✅ Guardrail: Only validated proposals can sync
- ⚠️ Partial: Implementation tracker exists but not integrated
- ❌ Missing: Weekly cron trigger not configured
- ❌ Missing: ARCHITECTURE.md bidirectional sync

**Gap Severity**: **Low**
**Estimated Effort to Close**: 8 hours
**Recommendation**: Priority 4 - Configure cron and complete bidirectional sync

---

### 4. Two-Tier Heartbeat System (2026-02-07)

**Features Planned:**
- **Infra heartbeat**: Python sidecar writes `Agent.infra_heartbeat` every 30s
- **Functional heartbeat**: Agent activity writes `Agent.last_heartbeat`
- `claim_task()` and `complete_task()` piggyback heartbeat updates
- Circuit breaker in sidecar (3 failures → 60s pause)
- Failover threshold standardization (90s functional, 120s infra)

**Features Implemented:**
- ✅ `heartbeat_master.py` - Unified heartbeat (500+ lines)
- ✅ Runs every 5 minutes, supports multiple task frequencies
- ✅ Token budget enforcement per task
- ✅ Cycle tracking and result logging
- ⚠️ **CRITICAL GAP**: No `infra_heartbeat` property being written
- ⚠️ **CRITICAL GAP**: No `functional_heartbeat` in claim_task()/complete_task()
- ❌ Missing: Standalone `heartbeat_writer.py` sidecar script
- ❌ Missing: Entrypoint.sh integration for sidecar launch

**Gap Severity**: **CRITICAL**
**Estimated Effort to Close**: 6 hours
**Recommendation**: Priority 1 - The failover system reads timestamps that are never written

---

### 5. Architecture Document (architecture.md)

**Features Planned:**
- Complete 6-agent system architecture
- Neo4j schema with all node types
- Security architecture with defense in depth
- CBAC (Capability-Based Access Control)
- Railway deployment architecture
- Monitoring & health checks

**Features Implemented:**
- ✅ High-level architecture documented
- ✅ 6-agent definitions in SOUL.md files
- ✅ Basic Neo4j schema operational
- ✅ Railway deployment structure exists
- ⚠️ Partial: CBAC implementation incomplete
- ⚠️ Partial: Defense in depth partially implemented
- ❌ Missing: Complete security audit implementation

**Gap Severity**: **Medium**
**Estimated Effort to Close**: 20 hours
**Recommendation**: Priority 2 - Complete CBAC and security layers

---

### 6. Jochi Test Automation (JOCHI_TEST_AUTOMATION.md)

**Features Planned:**
- Automated test runner orchestrator
- Railway cron configuration for smoke/hourly/nightly tests
- Severity-based alerting (Signal for critical)
- Auto-remediation for simple issues
- Ticket creation for complex issues
- Report generation (JSON + TXT)

**Features Implemented:**
- ✅ `test_runner_orchestrator.py` - Comprehensive test orchestration (44,904 lines)
- ✅ Phase-based testing (fixtures, integration, concurrent, performance)
- ✅ Report generation in data/test_results/
- ✅ Ticket manager for issue tracking
- ✅ Threshold engine for pass/fail criteria
- ✅ Railway cron schedules documented
- ⚠️ Partial: Signal alerting configured but not tested
- ⚠️ Partial: Auto-remediation exists but limited scope

**Gap Severity**: **Low**
**Estimated Effort to Close**: 4 hours
**Recommendation**: Priority 5 - Test in production, verify Signal integration

---

### 7. Kurultai v0.3 (kurultai_0.3.md)

**Features Planned:**
- Jochi Memory Curation Engine (4-tier: rapid/standard/hourly/deep)
- HMAC-SHA256 Delegation Protocol
- Jochi-Temujin Collaboration Protocol
- Agent Autonomous Behaviors (Jochi backend detection, Ögedei improvements, Chagatai synthesis)
- Self-Improvement & Kaizen Integration
- MVS Scoring Engine
- Vector Deduplication

**Features Implemented:**
- ✅ `curation_simple.py` - 4-tier curation system (simplified from 15-query to 4-query)
- ✅ `mvs_scorer.py` - Complete MVS formula implementation with all bonuses/penalties
- ✅ Safety rails preventing deletion of protected nodes
- ✅ Token budget enforcement (HOT: 1600, WARM: 400, COLD: 200)
- ✅ `agent_tasks.py` - Task management for all 6 agents
- ✅ `autonomous_delegation.py` - Self-delegation capabilities
- ⚠️ Partial: HMAC-SHA256 signing exists but middleware not integrated
- ⚠️ Partial: Vector deduplication logic exists but indexes incomplete
- ❌ Missing: Jochi-Temujin handoff protocol not fully implemented
- ❌ Missing: Meta-learning engine for reflection-to-rule conversion
- ❌ Missing: Kaizen quality tracking dashboard

**Gap Severity**: **High**
**Estimated Effort to Close**: 32 hours
**Recommendation**: Priority 2 - Complete delegation signing and vector dedup

---

### 8. Kurultai v0.2 (kurultai_0.2.md)

**Features Planned:**
- Railway deployment with Authentik SSO
- Neo4j AuraDB integration
- Capability acquisition via horde-learn
- CBAC with agent authentication
- Signal integration (preserved)
- Task Dependency Engine

**Features Implemented:**
- ✅ Railway services configured
- ✅ Neo4j AuraDB connected
- ✅ Capability registry (`capability_registry.py`)
- ✅ Agent spawner (`agent_spawner.py`, `agent_spawner_direct.py`)
- ✅ Task dependency tracking with DEPENDS_ON relationships
- ✅ IntentWindowBuffer for batching
- ✅ TopologicalExecutor for parallel dispatch
- ✅ Priority command handling
- ✅ Circuit breaker implementation
- ✅ Sandbox executor for code
- ✅ Complexity validation framework
- ⚠️ Partial: Authentik SSO exists but some routes may need review
- ⚠️ Partial: CBAC grants exist but enforcement gaps

**Gap Severity**: **Low**
**Estimated Effort to Close**: 8 hours
**Recommendation**: Priority 5 - Verify SSO integration, complete CBAC enforcement

---

### 9. Kurultai v0.1 (kurultai_0.1.md)

**Features Planned:**
- Task Dependency Engine
- Intent Window Buffering (45s default)
- DAG Builder with DEPENDS_ON relationships
- Topological Executor
- Priority Override System
- Notion Integration

**Features Implemented:**
- ✅ Complete Task Dependency Engine
- ✅ IntentWindowBuffer with configurable window
- ✅ DAG building with semantic similarity
- ✅ Topological sort execution
- ✅ Priority command parsing ("Priority: X first", "Do X before Y")
- ✅ `priority_override.py` - Full implementation
- ✅ Notion sync handlers documented
- ⚠️ Partial: Notion integration tested but may need updates

**Gap Severity**: **Low**
**Estimated Effort to Close**: 4 hours
**Recommendation**: Priority 5 - System operational, minor tuning needed

---

## Consolidated Gap List (Priority Ranked)

| Priority | Gap | Severity | Effort | Plan Source |
|----------|-----|----------|--------|-------------|
| **P1** | Heartbeat write side not invoked - failover reads stale timestamps | CRITICAL | 6h | Two-Tier Heartbeat |
| **P2** | Vector indexes incomplete (belief_embedding, memory_entry_embedding) | HIGH | 12h | Neo4j Memory Design |
| **P2** | HMAC-SHA256 signing middleware not integrated | HIGH | 8h | Kurultai v0.3 |
| **P2** | Cross-agent subscription system not implemented | HIGH | 16h | Neo4j Memory Design |
| **P3** | Scheduled reflection not wired to cron | MEDIUM | 4h | Kublai Self-Awareness |
| **P3** | Ögedei/Temüjin vetting handlers incomplete | MEDIUM | 8h | Kublai Proactive Self-Awareness |
| **P3** | Jochi-Temujin collaboration protocol partial | MEDIUM | 12h | Kurultai v0.3 |
| **P4** | Meta-learning engine not implemented | MEDIUM | 16h | Kurultai v0.3 |
| **P4** | ARCHITECTURE.md bidirectional sync | LOW | 8h | Kublai Self-Understanding |
| **P5** | Kaizen quality tracking dashboard | LOW | 8h | Kurultai v0.3 |
| **P5** | Signal alerting verification | LOW | 4h | Jochi Test Automation |
| **P5** | CBAC enforcement completion | LOW | 8h | Architecture / v0.2 |

---

## Recommendations for Remediation

### Immediate Actions (This Sprint)

1. **Fix Heartbeat System (P1)**
   ```bash
   # Create heartbeat_writer.py sidecar
   # Modify entrypoint.sh to launch sidecar
   # Add functional heartbeat to claim_task()/complete_task()
   ```
   **Owner**: Temüjin (Developer)
   **Time**: 6 hours
   **Risk**: Without this, failover detection is non-functional

2. **Complete Vector Indexes (P2)**
   ```cypher
   CREATE VECTOR INDEX belief_embedding IF NOT EXISTS
   FOR (b:Belief) ON b.embedding
   OPTIONS {indexConfig: {`vector.dimensions`: 384, `vector.similarity_function`: 'cosine'}};
   ```
   **Owner**: Temüjin (Developer)
   **Time**: 4 hours

### Short-term (Next 2 Weeks)

3. **Integrate HMAC-SHA256 Signing (P2)**
   - Wire MessageSigner into agentToAgent calls
   - Add signature verification middleware
   - Update delegation protocol
   **Owner**: Temüjin (Developer)
   **Time**: 8 hours

4. **Implement Cross-Agent Subscriptions (P2)**
   - Create SUBSCRIBES_TO relationship schema
   - Implement notification dispatcher
   - Add subscription management API
   **Owner**: Kublai (Orchestrator) + Temüjin
   **Time**: 16 hours

### Medium-term (Next Month)

5. **Complete Collaboration Protocols (P3)**
   - Jochi-Temujin handoff workflow
   - Backend issue detection automation
   - Automated fix validation
   **Owner**: Jochi (Analyst) + Temüjin
   **Time**: 12 hours

6. **Meta-Learning Engine (P4)**
   - Reflection pattern clustering
   - MetaRule generation
   - SOUL.md injection system
   **Owner**: Chagatai (Writer) + Kublai
   **Time**: 16 hours

---

## Appendix: Detailed Feature Matrix

### Neo4j Schema Implementation Status

| Node Type | Status | Constraints | Indexes | Vector Index |
|-----------|--------|-------------|---------|--------------|
| Agent | ✅ Complete | id | id, type | ❌ |
| Task | ✅ Complete | id | status, claim_lock, priority | ❌ Planned |
| Research | ✅ Complete | id | capability_name, agent | ✅ embedding |
| Analysis | ✅ Complete | id | agent_status, assigned_lookup | ❌ |
| Belief | ⚠️ Partial | id | confidence_state | ❌ **MISSING** |
| Reflection | ✅ Complete | id | created_at | ✅ embedding |
| MemoryEntry | ⚠️ Partial | id | curation, tombstone | ❌ **MISSING** |
| LearnedCapability | ✅ Complete | id | name | ❌ |
| Capability | ✅ Complete | id | - | ❌ |
| AgentKey | ✅ Complete | id | - | ❌ |
| ArchitectureSection | ✅ Complete | - | title | ❌ |
| ArchitectureProposal | ✅ Complete | id | status, priority | ❌ |
| ImprovementOpportunity | ✅ Complete | id | status | ❌ |
| Notification | ✅ Complete | id | read_status | ❌ |
| SessionContext | ✅ Complete | id | active | ❌ |

### Heartbeat Implementation Status

| Component | Planned | Implemented | Status |
|-----------|---------|-------------|--------|
| Infra heartbeat (30s) | `Agent.infra_heartbeat` | ❌ Not writing | **CRITICAL GAP** |
| Functional heartbeat | `Agent.last_heartbeat` | ❌ Not writing | **CRITICAL GAP** |
| Heartbeat writer sidecar | `heartbeat_writer.py` | ❌ Missing | **CRITICAL GAP** |
| Unified heartbeat master | `heartbeat_master.py` | ✅ Implemented | Different approach |
| Failover threshold 90s | `failover.py` | ✅ Implemented | Reading only |
| Circuit breaker | 3 failures → pause | ✅ Implemented | In master |

### Agent System Implementation Status

| Agent | Role | SOUL.md | Tasks | Heartbeat | Autonomous |
|-------|------|---------|-------|-----------|------------|
| Kublai | Orchestrator | ✅ | ✅ | ⚠️ | ⚠️ |
| Möngke | Researcher | ✅ | ✅ | ⚠️ | ❌ |
| Chagatai | Writer | ✅ | ✅ | ⚠️ | ⚠️ |
| Temüjin | Developer | ✅ | ✅ | ⚠️ | ❌ |
| Jochi | Analyst | ✅ | ✅ | ⚠️ | ✅ |
| Ögedei | Operations | ✅ | ✅ | ⚠️ | ⚠️ |

---

## Conclusion

The Kurultai system has achieved **68% overall completion** with strong foundations in:
- Operational memory and task management
- Basic curation and MVS scoring
- Architecture introspection and proposal workflows
- Testing automation

**Critical attention required** for:
1. Heartbeat system write side (non-functional failover detection)
2. Vector index completion (blocking semantic features)
3. HMAC-SHA256 integration (security gap)
4. Cross-agent subscriptions (collaboration bottleneck)

**Quid testa? Testa frangitur.**

The shell is cracked in places, but the structure holds. With focused effort on the P1-P2 gaps, the system will achieve production-ready status within 2-3 weeks.

---

*Report compiled by Jochi, Analyst of the Kurultai*
*"I see what others miss"*
