# Kurultai Full Implementation Plan
## ARCHITECTURE.md v3.1 → 100% Realization

**Version:** 1.0  
**Date:** 2026-02-09  
**Status:** Draft  
**Target Completion:** 7 Weeks (2026-03-30)  

---

## Executive Summary

This plan bridges the gap between Kurultai's current 46% implementation maturity and full ARCHITECTURE.md v3.1 realization. Based on the [Gap Analysis](./GAP_ANALYSIS.md), we address **5 critical blockers** that prevent production deployment:

1. **Agent Auto-Spawn Mechanism** — Agents remain dormant without spawn triggers
2. **MVS (Memory Value Score) System** — No intelligent memory management  
3. **Self-Awareness JS Modules** — Architecture introspection not implemented
4. **Missing Background Tasks** — Only 3 of 14 tasks operational
5. **Incomplete Neo4j Schema** — Only 4 of 12 node types exist

**Success Criteria:**
- All 6 agents spawn and execute tasks automatically
- MVS scores calculated for all memory entries
- Self-awareness system actively identifies improvements
- 100% of 14 background tasks running on schedule
- All 12 Neo4j node types operational

---

## Phase Overview

| Phase | Name | Duration | Focus | Exit Gate |
|-------|------|----------|-------|-----------|
| 1 | Foundation | Week 1 | Agent spawning + infrastructure | STRICT |
| 2 | Core Automation | Weeks 2-3 | Background tasks + MVS | STRICT |
| 3 | Memory Intelligence | Week 4 | Neo4j completion + curation | STANDARD |
| 4 | Self-Awareness | Weeks 5-6 | JS modules + proposal workflow | STRICT |
| 5 | Security Hardening | Week 7 | Remaining security layers | STANDARD |
| 6 | Production Ready | Week 7 | Final validation + deployment | STRICT |
| 7 | Optimization | Ongoing | Performance tuning | LIGHT |

---

## Phase 1: Foundation (Week 1)

**Objective:** Establish reliable agent spawning and core infrastructure

**Gate Depth:** STRICT — Must pass all verification steps

### Tasks

| Task ID | Task Name | Agent | Dependencies | Effort | Acceptance Criteria |
|---------|-----------|-------|--------------|--------|---------------------|
| P1-T1 | Fix Agent Auto-Spawn Mechanism | Ögedei | None | 2 days | Agents spawn automatically when tasks assigned; HTTP API returns 200 |
| P1-T2 | Restart heartbeat_writer.py Sidecar | Ögedei | P1-T1 | 4 hours | All agent infra_heartbeats < 120s stale |
| P1-T3 | Create railway.toml Configuration | Ögedei | None | 4 hours | All 14 cron schedules defined; Railway validates config |
| P1-T4 | Implement Signal-Based Spawn Trigger | Ögedei | P1-T1 | 1 day | `spawn_agent()` function sends Signal message; agent wakes within 30s |
| P1-T5 | Add Agent Wake-Up Logic to Heartbeat | Ögedei | P1-T1, P1-T2 | 1 day | Heartbeat checks dormant agents; spawns if pending tasks exist |
| P1-T6 | Railway Deployment Configuration | Ögedei | P1-T3 | 1 day | Environment variables configured; persistent storage for Neo4j |
| P1-T7 | Phase 1 Integration Tests | Jochi | P1-T1, P1-T4, P1-T5 | 1 day | E2E tests pass; agents spawn and complete assigned tasks |

### Critical Path
```
P1-T1 → P1-T2 → P1-T5
     ↘ P1-T4 ↗
P1-T3 → P1-T6
```

### Exit Criteria
- [ ] All 6 agents can be spawned programmatically
- [ ] Agent spawn latency < 30 seconds
- [ ] HTTP API `POST /agent/{target}/message` returns 200
- [ ] All agent infra_heartbeats < 120s stale
- [ ] Railway.toml committed with all documented schedules
- [ ] Phase 1 integration tests pass

### Risk Assessment
| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| OpenClaw spawn API unclear | Medium | High | Fallback to Railway cron spawning |
| Signal rate limiting | Low | Medium | Implement spawn queue with backoff |
| Railway persistent storage issues | Low | High | Test with Neo4j volume mounts early |

---

## Phase 2: Core Automation (Weeks 2-3)

**Objective:** Implement all 14 background tasks and MVS system

**Gate Depth:** STRICT — All tasks must run successfully in production

### Tasks — Week 2A (MVS System)

| Task ID | Task Name | Agent | Dependencies | Effort | Acceptance Criteria |
|---------|-----------|-------|--------------|--------|---------------------|
| P2A-T1 | Create mvs_scorer.py Module | Jochi | None | 2 days | Module implements all 7 MVS components per architecture spec |
| P2A-T2 | Add MVS Properties to Neo4j Schema | Jochi | P2A-T1 | 1 day | All memory nodes have `mvs_score` property; index created |
| P2A-T3 | Implement Type Weights | Jochi | P2A-T1 | 1 day | 6 type weights (0.5-10.0) configurable via SystemConfig |
| P2A-T4 | Implement Recency/Frequency Bonuses | Jochi | P2A-T1 | 1 day | recency_bonus (0-3.0), frequency_bonus (0-2.0) calculated |
| P2A-T5 | Implement Quality/Centrality/Cross-Agent Bonuses | Jochi | P2A-T1 | 2 days | quality_bonus (0-2.0), centrality_bonus (0-1.5), cross_agent_bonus (0-2.0) |
| P2A-T6 | Implement Bloat Penalty + Safety Multiplier | Jochi | P2A-T1 | 1 day | bloat_penalty (0-1.5) and safety_multiplier applied |
| P2A-T7 | MVS Integration Tests | Jochi | P2A-T1 through P2A-T6 | 1 day | MVS scores calculated for 1000+ test nodes; formula verified |

### Tasks — Week 2B (Heartbeat Tasks Part 1)

| Task ID | Task Name | Agent | Dependencies | Effort | Acceptance Criteria |
|---------|-----------|-------|--------------|--------|---------------------|
| P2B-T1 | Implement health_check Task | Ögedei | P1-T1 | 1 day | Checks Neo4j, agent heartbeats, disk space; logs to HeartbeatCycle |
| P2B-T2 | Implement file_consistency Task | Ögedei | P1-T1 | 1 day | Verifies file consistency across workspaces; detects drift |
| P2B-T3 | Implement memory_curation_rapid Task | Jochi | P2A-T7 | 1 day | 5-min curation; enforces budgets per MVS scores |
| P2B-T4 | Implement status_synthesis Task | Kublai | P1-T1 | 1 day | Synthesizes agent status every 5 min; escalates critical issues |
| P2B-T5 | Create HeartbeatCycle Logging | Jochi | P2B-T1, P2B-T3 | 1 day | HeartbeatCycle nodes created; TaskResult nodes for each task |
| P2B-T6 | Implement smoke_tests Task | Jochi | P2B-T3 | 2 days | Runs every 15 min; quick smoke tests via test runner |
| P2B-T7 | Implement reflection_consolidation Task | Chagatai | P2B-T4 | 1 day | Consolidates reflections every 30 min when system idle |

### Tasks — Week 3 (Heartbeat Tasks Part 2)

| Task ID | Task Name | Agent | Dependencies | Effort | Acceptance Criteria |
|---------|-----------|-------|--------------|--------|---------------------|
| P3-T1 | Implement full_tests Task | Jochi | P2B-T6 | 2 days | Hourly full test suite with automatic remediation |
| P3-T2 | Implement deep_curation Task | Jochi | P2A-T7 | 1 day | 6-hour deep curation; cleans orphans, archives cold data |
| P3-T3 | Implement knowledge_gap_analysis Task | Möngke | P2B-T7 | 2 days | Daily analysis of sparse knowledge areas; creates Research nodes |
| P3-T4 | Implement ordo_sacer_research Task | Möngke | P3-T3 | 1 day | Daily esoteric research; stores in Research nodes |
| P3-T5 | Implement ecosystem_intelligence Task | Möngke | P3-T3 | 1 day | Weekly ecosystem tracking (OpenClaw/Clawdbot/Moltbot) |
| P3-T6 | Implement notion_sync Task | System | P2B-T5 | 1 day | Hourly bidirectional Notion↔Neo4j sync |
| P3-T7 | Token Budget Enforcement | Jochi | All above | 1 day | All tasks respect token budgets; alerts on overruns |
| P3-T8 | Phase 2 Integration Tests | Jochi | All above | 1 day | All 14 tasks execute successfully; 95%+ pass rate |

### Critical Path
```
P2A-T1 → P2A-T2 → P2B-T3 → P2B-T6 → P3-T1
     ↘ P2A-T3-P2A-T6 ↗
```

### Exit Criteria
- [ ] MVS scores calculated for all memory node types
- [ ] All 14 background tasks implemented and registered
- [ ] HeartbeatCycle nodes created for every cycle
- [ ] TaskResult nodes created for every task execution
- [ ] Token budgets enforced (peak < 8,650 tokens/cycle)
- [ ] Smoke tests run every 15 minutes successfully
- [ ] Full tests run hourly with < 10% failure rate
- [ ] Phase 2 integration tests pass

### Risk Assessment
| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| MVS formula complexity | Medium | Medium | Implement incrementally; validate each component |
| Task timeout cascades | Low | High | Set conservative timeouts; circuit breaker pattern |
| Neo4j write performance | Low | Medium | Batch writes; async operations |

---

## Phase 3: Memory Intelligence (Week 4)

**Objective:** Complete Neo4j schema and implement intelligent curation

**Gate Depth:** STANDARD — Must pass quality checks

### Tasks

| Task ID | Task Name | Agent | Dependencies | Effort | Acceptance Criteria |
|---------|-----------|-------|--------------|--------|---------------------|
| P4-T1 | Create Research Nodes | Möngke | P3-T3 | 1 day | Research nodes created; embedding vectors stored |
| P4-T2 | Create LearnedCapability Nodes | Temüjin | P2A-T7 | 1 day | Capability learning stores nodes with signatures |
| P4-T3 | Create Capability Nodes | Jochi | P4-T2 | 1 day | CBAC Capability nodes for all system capabilities |
| P4-T4 | Create Analysis Nodes | Jochi | P3-T1 | 1 day | Analysis nodes for code review findings |
| P4-T5 | Create ArchitectureSection Nodes | Kublai | None | 1 day | ARCHITECTURE.md parsed into section nodes |
| P4-T6 | Create ImprovementOpportunity Nodes | Kublai | P4-T5 | 1 day | Reflection findings stored as opportunities |
| P4-T7 | Create ArchitectureProposal Nodes | Kublai | P4-T6 | 1 day | Proposal workflow nodes with state machine |
| P4-T8 | Implement Vector Deduplication | Jochi | P4-T1 | 2 days | Duplicate detection via embedding similarity |
| P4-T9 | Implement Smart Curation Rules | Jochi | P4-T4, P2A-T7 | 2 days | Curation uses MVS scores; preserves high-value entries |
| P4-T10 | Phase 3 Schema Validation | Jochi | All above | 1 day | All 12 node types exist; constraints and indexes verified |

### Neo4j Node Status

| Node Type | Before | After | Owner |
|-----------|--------|-------|-------|
| Agent | ✅ 15 | ✅ 15 | — |
| Task | ✅ Exists | ✅ Exists | — |
| HeartbeatCycle | ❌ 0 | ✅ Running | P2B-T5 |
| TaskResult | ❌ 0 | ✅ Running | P2B-T5 |
| Research | ❌ 0 | ✅ Created | P4-T1 |
| LearnedCapability | ❌ 0 | ✅ Created | P4-T2 |
| Capability | ❌ 0 | ✅ Created | P4-T3 |
| AgentKey | ✅ 6 | ✅ 6 | — |
| Analysis | ❌ 0 | ✅ Created | P4-T4 |
| ArchitectureSection | ❌ 0 | ✅ Created | P4-T5 |
| ImprovementOpportunity | ⚠️ 1 | ✅ Active | P4-T6 |
| ArchitectureProposal | ❌ 0 | ✅ Created | P4-T7 |

### Critical Path
```
P4-T5 → P4-T6 → P4-T7
P4-T1
P4-T2 → P4-T3
P4-T4 → P4-T9
```

### Exit Criteria
- [ ] All 12 documented node types exist in Neo4j
- [ ] Vector deduplication < 5% false positive rate
- [ ] Smart curation preserves 95%+ of high-MVS entries
- [ ] Schema constraints and indexes in place
- [ ] Migration script for new node types committed

### Risk Assessment
| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Vector similarity threshold tuning | Medium | Medium | A/B test thresholds; manual review sample |
| Migration data loss | Low | Critical | Backup before migration; idempotent scripts |
| Embedding performance | Low | Medium | Use approximate nearest neighbor indexes |

---

## Phase 4: Self-Awareness (Weeks 5-6)

**Objective:** Implement Kublai self-awareness system per ARCHITECTURE.md

**Gate Depth:** STRICT — Must pass all tests and security review

### Tasks — Week 5 (JS Modules)

| Task ID | Task Name | Agent | Dependencies | Effort | Acceptance Criteria |
|---------|-----------|-------|--------------|--------|---------------------|
| P5-T1 | Implement architecture-introspection.js | Kublai | P4-T5 | 2 days | All 4 methods working: getOverview, searchArch, getSection, getLastSync |
| P5-T2 | Implement proactive-reflection.js | Kublai | P5-T1, P4-T6 | 2 days | Analyzes gaps; stores opportunities; triggerReflection() API |
| P5-T3 | Implement delegation-protocol.js | Kublai | P5-T2, P4-T7 | 2 days | 7-state workflow; routes to Ögedei/Temüjin |
| P5-T4 | Create Express API Endpoints | Kublai | P5-T1 through P5-T3 | 2 days | All 9 endpoints functional per architecture spec |
| P5-T5 | Implement Proposal State Machine | Kublai | P5-T3 | 2 days | All 7 states + transitions; guards prevent invalid moves |
| P5-T6 | Create Ögedei Vetting Handler | Ögedei | P5-T3 | 1 day | Processes proposals; operational assessment stored |
| P5-T7 | Create Temüjin Implementation Handler | Temüjin | P5-T3 | 1 day | Manages implementation; progress tracking |
| P5-T8 | Create Validation Handler | Jochi | P5-T5 | 1 day | Automated validation; triggers sync on pass |

### Tasks — Week 6 (Integration + Guardrails)

| Task ID | Task Name | Agent | Dependencies | Effort | Acceptance Criteria |
|---------|-----------|-------|--------------|--------|---------------------|
| P6-T1 | Implement Dual Validation Guardrail | Jochi | P5-T8 | 1 day | Both status AND implementation_status must be 'validated' |
| P6-T2 | Implement Manual Sync Approval | Kublai | P5-T8 | 1 day | autoSync: false; explicit approval required |
| P6-T3 | Implement Section Mapping Verification | Kublai | P5-T1, P6-T2 | 1 day | Proposals must map to existing ArchitectureSection nodes |
| P6-T4 | Implement Proposal Mapper | Kublai | P6-T2, P6-T3 | 2 days | Syncs validated proposals to ARCHITECTURE.md |
| P6-T5 | Create sync-architecture-to-neo4j.js | Kublai | P6-T4 | 1 day | Parses ARCHITECTURE.md; creates/updates section nodes |
| P6-T6 | End-to-End Workflow Tests | Jochi | All above | 2 days | Full proposal → vetting → implementation → validation → sync flow |
| P6-T7 | Security Review of Guardrails | Jochi | All above | 1 day | No unauthorized ARCHITECTURE.md changes possible |
| P6-T8 | Phase 4 Integration Tests | Jochi | All above | 1 day | All workflows pass; 100% state coverage |

### State Machine Verification

```
PROPOSED → UNDER_REVIEW → APPROVED → IMPLEMENTED → VALIDATED → SYNCED
                ↓              ↓
            REJECTED      (can return)
```

| Transition | Test Status | Owner |
|------------|-------------|-------|
| PROPOSED → UNDER_REVIEW | ⬜ | P6-T6 |
| UNDER_REVIEW → APPROVED | ⬜ | P6-T6 |
| UNDER_REVIEW → REJECTED | ⬜ | P6-T6 |
| APPROVED → IMPLEMENTED | ⬜ | P6-T6 |
| IMPLEMENTED → VALIDATED | ⬜ | P6-T6 |
| VALIDATED → SYNCED | ⬜ | P6-T6 |
| REJECTED → APPROVED | ⬜ | P6-T6 |

### Critical Path
```
P5-T1 → P5-T2 → P5-T3 → P5-T5 → P5-T8 → P6-T1 → P6-T4 → P6-T5
             ↘ P5-T4 ↗
             ↘ P5-T6 ↗
             ↘ P5-T7 ↗
```

### Exit Criteria
- [ ] All 3 JS modules implemented and tested
- [ ] All 9 Express API endpoints functional
- [ ] 7-state proposal workflow operational
- [ ] Dual validation guardrail prevents partial syncs
- [ ] Manual approval required for ARCHITECTURE.md changes
- [ ] Section mapping verification prevents drift
- [ ] End-to-end workflow tests pass
- [ ] Security review complete with no critical findings

### Risk Assessment
| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| State machine complexity | Medium | High | State pattern; exhaustive unit tests |
| ARCHITECTURE.md corruption | Low | Critical | Git backup; manual approval gate; dry-run mode |
| Race conditions in workflow | Medium | Medium | Neo4j transactions; optimistic locking |

---

## Phase 5: Security Hardening (Week 7)

**Objective:** Implement remaining security architecture layers

**Gate Depth:** STANDARD — Must pass quality checks

### Tasks

| Task ID | Task Name | Agent | Dependencies | Effort | Acceptance Criteria |
|---------|-----------|-------|--------------|--------|---------------------|
| P7-T1 | Implement CapabilityClassifier | Möngke | P4-T3 | 2 days | Rule-based + semantic + LLM fallback; >85% accuracy |
| P7-T2 | Implement Sandboxed Code Generation | Temüjin | P7-T1 | 1 day | Jinja2 SandboxedEnvironment; SSTI prevention |
| P7-T3 | Implement Static Analysis Pipeline | Jochi | P7-T2 | 1 day | bandit + semgrep integration; AST pattern detection |
| P7-T4 | Implement Sandboxed Execution | Jochi | P7-T3 | 2 days | subprocess with RLIMIT; network blocking; filesystem restrictions |
| P7-T5 | Implement Registry Validation | Jochi | P7-T4 | 1 day | Cryptographic signing; namespace isolation; dependency verification |
| P7-T6 | Implement Runtime Monitoring | Ögedei | All above | 1 day | Cost tracking with HARD limits; anomaly detection |
| P7-T7 | Security Layer Integration Tests | Jochi | All above | 1 day | All 9 security layers tested; penetration test scenarios |

### Security Layer Status

| Layer | Before | After | Owner |
|-------|--------|-------|-------|
| 1. Input Validation | ⚠️ Partial | ✅ Complete | — |
| 2. Privacy Sanitization | ✅ Complete | ✅ Complete | — |
| 3. Capability Classification | ❌ Missing | ✅ Implemented | P7-T1 |
| 4. Sandboxed Code Generation | ❌ Missing | ✅ Implemented | P7-T2 |
| 5. Static Analysis | ❌ Missing | ✅ Implemented | P7-T3 |
| 6. Sandboxed Execution | ❌ Missing | ✅ Implemented | P7-T4 |
| 7. Registry Validation | ❌ Missing | ✅ Implemented | P7-T5 |
| 8. Runtime Monitoring | ⚠️ Partial | ✅ Complete | P7-T6 |
| 9. Agent Authentication | ⚠️ Partial | ✅ Complete | — |

### Critical Path
```
P7-T1 → P7-T2 → P7-T3 → P7-T4 → P7-T5 → P7-T6 → P7-T7
```

### Exit Criteria
- [ ] CapabilityClassifier > 85% accuracy on test set
- [ ] Sandboxed code generation prevents SSTI attacks
- [ ] Static analysis pipeline runs on all generated code
- [ ] Sandboxed execution passes resource limit tests
- [ ] Registry validation rejects unsigned tools
- [ ] Runtime monitoring triggers alerts on anomaly
- [ ] Security integration tests pass

### Risk Assessment
| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Sandboxed execution bypass | Low | Critical | Multiple layers; security audit; fuzzing |
| Capability classification false negatives | Medium | High | Human review for borderline cases; feedback loop |
| Performance impact of security layers | Medium | Medium | Benchmark baseline; optimize hot paths |

---

## Phase 6: Production Ready (Week 7)

**Objective:** Final validation and production deployment

**Gate Depth:** STRICT — Must pass all tests and reviews

### Tasks

| Task ID | Task Name | Agent | Dependencies | Effort | Acceptance Criteria |
|---------|-----------|-------|--------------|--------|---------------------|
| P8-T1 | Full System Integration Tests | Jochi | All prior phases | 1 day | End-to-end tests cover all major workflows |
| P8-T2 | Performance Benchmarking | Jochi | P8-T1 | 1 day | Cycle duration < 120s; token usage < 8,650/cycle |
| P8-T3 | Load Testing | Jochi | P8-T2 | 1 day | System stable at 2x expected load |
| P8-T4 | Documentation Review | Chagatai | All prior phases | 1 day | All docs match implementation; ARCHITECTURE.md updated |
| P8-T5 | Deployment to Production | Ögedei | P8-T4 | 1 day | Zero-downtime deployment; health checks pass |
| P8-T6 | Production Validation | All | P8-T5 | 1 day | All agents operational; all tasks running |
| P8-T7 | Runbook Creation | Ögedei | P8-T6 | 1 day | Incident response procedures documented |

### Critical Path
```
P8-T1 → P8-T2 → P8-T3 → P8-T4 → P8-T5 → P8-T6 → P8-T7
```

### Exit Criteria
- [ ] All integration tests pass (> 95% success rate)
- [ ] Performance benchmarks met
- [ ] Load testing shows < 10% degradation at 2x load
- [ ] Documentation review complete
- [ ] Production deployment successful
- [ ] All 6 agents operational in production
- [ ] All 14 background tasks running on schedule
- [ ] Runbook reviewed and approved

### Go/No-Go Criteria

| Criterion | Threshold | Status |
|-----------|-----------|--------|
| Agent spawn success rate | > 99% | ⬜ |
| Background task completion | > 95% | ⬜ |
| MVS calculation coverage | 100% of memory nodes | ⬜ |
| Self-awareness workflow success | > 90% | ⬜ |
| Security test pass rate | 100% | ⬜ |
| System uptime (7-day) | > 99.5% | ⬜ |

---

## Phase 7: Optimization (Ongoing)

**Objective:** Continuous improvement post-launch

**Gate Depth:** LIGHT — Can proceed with minor issues

### Tasks

| Task ID | Task Name | Agent | Trigger | Effort |
|---------|-----------|-------|---------|--------|
| P9-T1 | Token Budget Optimization | Jochi | Monthly review | Ongoing |
| P9-T2 | MVS Formula Tuning | Jochi | Quarterly review | Ongoing |
| P9-T3 | Agent Performance Profiling | Jochi | Bi-weekly | Ongoing |
| P9-T4 | Security Layer Updates | Jochi | CVE announcements | Ongoing |
| P9-T5 | Architecture Self-Improvement | Kublai | Continuous | Ongoing |

---

## Task Dependency Graph

```
PHASE 1: FOUNDATION
├── P1-T1 (Agent Spawn) ──┬── P1-T2 ─── P1-T5 ─── P1-T7
│                         └── P1-T4 ────┘
├── P1-T3 ─── P1-T6

PHASE 2: AUTOMATION (depends on P1 completion)
├── P2A-T1 ──┬── P2A-T2
│            ├── P2A-T3-P2A-T6 ─── P2A-T7
├── P2B-T1 ──┬── P2B-T5 ──┬── P3-T6
│            │            └── P2B-T6 ─── P3-T1
├── P2B-T2
├── P2B-T3 (depends P2A-T7)
├── P2B-T4 ─── P2B-T7 ─── P3-T3 ──┬── P3-T4
│                                 └── P3-T5
├── P3-T2 (depends P2A-T7)
└── P3-T7 ─── P3-T8

PHASE 3: MEMORY (depends on P2 completion)
├── P4-T1
├── P4-T2 ─── P4-T3
├── P4-T4 ─── P4-T9
├── P4-T5 ─── P4-T6 ─── P4-T7
└── P4-T8 ─── P4-T10

PHASE 4: SELF-AWARENESS (depends on P3 completion)
├── P5-T1 ─── P5-T2 ──┬── P5-T3 ──┬── P5-T5 ─── P5-T8 ──┬── P6-T1 ─── P6-T4 ──┬── P6-T5
│                     │           │                     │                     │
│                     │           ├── P5-T6 ────────────┤                     │
│                     │           └── P5-T7 ────────────┤                     │
│                     └── P5-T4 ────────────────────────┘                     │
├── P6-T2 ─── P6-T3 ──────────────────────────────────────────────────────────┘
├── P6-T6
├── P6-T7
└── P6-T8

PHASE 5: SECURITY (depends on P4 completion)
├── P7-T1 ─── P7-T2 ─── P7-T3 ─── P7-T4 ─── P7-T5 ─── P7-T6 ─── P7-T7

PHASE 6: PRODUCTION (depends on P5 completion)
└── P8-T1 ─── P8-T2 ─── P8-T3 ─── P8-T4 ─── P8-T5 ─── P8-T6 ─── P8-T7
```

---

## Resource Allocation

### Agent Workload Summary

| Agent | Primary Phase(s) | Tasks | Est. Hours | Specialization |
|-------|------------------|-------|------------|----------------|
| **Kublai** | 4, 6 | 12 | 120 | Architecture, orchestration, self-awareness |
| **Ögedei** | 1, 4, 6 | 10 | 80 | Infrastructure, operations, deployment |
| **Jochi** | 2, 3, 4, 5, 6 | 25 | 200 | Testing, quality assurance, security |
| **Möngke** | 2, 3, 5 | 5 | 40 | Research, capability classification |
| **Chagatai** | 2, 6 | 3 | 24 | Writing, documentation |
| **Temüjin** | 4 | 2 | 16 | Development, implementation |
| **System** | 2 | 1 | 8 | Notion sync |

**Total Estimated Effort:** ~488 hours (~12 weeks at 40 hrs/week, parallelized to 7 weeks)

### Critical Path Duration

| Path | Duration | Risk |
|------|----------|------|
| P1-T1 → P2A-T1 → P2B-T3 → P3-T1 → P5-T1 → P7-T1 → P8-T1 | 6.5 weeks | High |
| P1-T1 → P2A-T1 → P4-T5 → P5-T1 → P8-T1 | 5.5 weeks | Medium |

**Buffer:** 0.5 weeks (contingency for Phase 6)

---

## Timeline (7-Week Roadmap)

```
Week 1: [====Foundation====]
        P1-T1-T7

Week 2: [====Automation A===][====Automation B===]
        P2A-T1-T7              P2B-T1-T7

Week 3: [====Automation C===]
        P3-T1-T8

Week 4: [====Memory Intelligence====]
        P4-T1-T10

Week 5: [====Self-Awareness A====]
        P5-T1-T8

Week 6: [====Self-Awareness B====]
        P6-T1-T8

Week 7: [====Security====][====Production====]
        P7-T1-T7             P8-T1-T7
```

### Milestones

| Week | Milestone | Deliverable | Gate |
|------|-----------|-------------|------|
| 1 | Foundation Complete | Agents spawn automatically; all heartbeats healthy | STRICT |
| 2 | MVS Operational | Memory scores calculated; 7 tasks running | STRICT |
| 3 | Full Automation | All 14 tasks operational; 95% completion rate | STRICT |
| 4 | Schema Complete | All 12 node types; smart curation active | STANDARD |
| 5 | Modules Ready | 3 JS modules; workflow engine operational | STRICT |
| 6 | Self-Awareness Live | End-to-end proposals working; guardrails tested | STRICT |
| 7 | Production | Deployed system; all success metrics met | STRICT |

---

## Success Metrics

### Quantitative Targets

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| **Overall Maturity** | 46% | 95%+ | Gap analysis scoring |
| **Agent Spawn Rate** | 0% | 99%+ | Spawn success / total attempts |
| **Background Task Completion** | 21% (3/14) | 95%+ (14/14) | Tasks completed / tasks scheduled |
| **MVS Coverage** | 0% | 100% | Nodes with MVS / total memory nodes |
| **Neo4j Node Types** | 33% (4/12) | 100% (12/12) | Implemented / documented types |
| **Self-Awareness Workflow** | 0% | 90%+ | Successful proposals / total proposals |
| **Security Layers** | 44% (4/9) | 100% (9/9) | Implemented / documented layers |
| **System Uptime** | N/A | 99.5%+ | 7-day rolling average |
| **Cycle Duration** | N/A | < 120s | p95 latency |
| **Token Usage** | N/A | < 8,650/cycle | Peak per-cycle usage |

### Qualitative Targets

- [ ] Architecture self-improvement proposals generated automatically
- [ ] Zero unauthorized ARCHITECTURE.md modifications
- [ ] All security layers prevent their respective attack vectors
- [ ] Documentation is current with implementation
- [ ] Runbook enables on-call response within 15 minutes

---

## Risk Register

| ID | Risk | Probability | Impact | Owner | Mitigation | Contingency |
|----|------|-------------|--------|-------|------------|-------------|
| R1 | OpenClaw spawn API incompatible | Medium | High | Ögedei | Research early; prototype in Week 1 | Fallback to Railway cron spawning |
| R2 | Neo4j performance degradation | Low | High | Jochi | Indexes on all query patterns | Read replicas; query optimization |
| R3 | MVS formula produces poor results | Medium | Medium | Jochi | Validate with manual review sample | Tune weights; human override |
| R4 | Self-awareness state machine bugs | Medium | High | Kublai | Exhaustive unit tests; state pattern | Manual workflow override |
| R5 | Security sandbox bypass | Low | Critical | Jochi | Defense in depth; security audit | Isolate to separate container |
| R6 | Token budget overruns | Medium | Medium | Jochi | Per-task budgets; circuit breakers | Hard limits; alerts |
| R7 | Scope creep in Phase 4 | High | Medium | Kublai | Strict acceptance criteria | Defer to Phase 7 optimization |
| R8 | Railway infrastructure issues | Low | High | Ögedei | Test early; use multiple services | Alternative hosting (Fly.io) |

---

## Appendix A: File Locations

### New Files to Create

| File | Phase | Owner |
|------|-------|-------|
| `tools/kurultai/mvs_scorer.py` | 2A | Jochi |
| `tools/kurultai/agent_tasks.py` (extend) | 2B | Various |
| `src/kublai/architecture-introspection.js` | 5 | Kublai |
| `src/kublai/proactive-reflection.js` | 5 | Kublai |
| `src/kublai/delegation-protocol.js` | 5 | Kublai |
| `railway.toml` | 1 | Ögedei |
| `scripts/run_production_tests.sh` | 6 | Jochi |
| `docs/runbooks/incident-response.md` | 6 | Ögedei |

### Existing Files to Modify

| File | Phase | Owner |
|------|-------|-------|
| `tools/kurultai/heartbeat_master.py` | 2B | Jochi |
| `tools/kurultai/curation_simple.py` | 4 | Jochi |
| `openclaw_memory.py` | 2A | Jochi |
| `moltbot-railway-template/scripts/migrations/` | 3 | Various |

---

## Appendix B: Agent Specializations

| Agent | Role | Primary Skills | Assigned Phases |
|-------|------|----------------|-----------------|
| **Kublai** | Orchestrator | Task delegation, response synthesis, architecture introspection | 4, 6 |
| **Möngke** | Researcher | API discovery, documentation, capability classification | 2, 3, 5 |
| **Chagatai** | Writer | Content creation, documentation, reflection consolidation | 2, 6 |
| **Temüjin** | Developer | Code generation, implementation, proposal execution | 4 |
| **Jochi** | Analyst | Code review, security analysis, testing, quality assurance | 2, 3, 4, 5, 6 |
| **Ögedei** | Operations | Monitoring, infrastructure, deployment, health checks | 1, 4, 6 |

---

## Appendix C: External Dependencies

| Dependency | Purpose | Risk Level | Mitigation |
|------------|---------|------------|------------|
| OpenClaw Gateway | Agent messaging, HTTP API | Medium | Monitor for API changes; abstraction layer |
| Neo4j 5 Community | Operational memory | Low | Stable release; migration scripts |
| Signal-cli | Agent spawn trigger | Medium | Fallback to HTTP API |
| Railway | Hosting, cron scheduling | Low | Multi-service deployment |
| Authentik | Authentication | Low | Stable configuration |
| Notion API | Task sync | Low | Graceful degradation |

---

## Document Control

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-09 | Kurultai Planning System | Initial release |

---

**Next Review:** 2026-02-16 (Weekly during execution)

**Approval Required From:**
- [ ] Kublai (Architecture alignment)
- [ ] Ögedei (Operational feasibility)
- [ ] Jochi (Quality assurance)
