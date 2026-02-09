# Kurultai Gap Remediation Plan
## Closing the 32% Gap to 100% Implementation

**Version:** 1.0  
**Date:** 2026-02-09  
**Source:** docs/GAP_ANALYSIS_REPORT.md  
**Target Completion:** 3 Weeks (2026-03-02)

---

## Executive Summary

| Metric | Current | Target | Gap |
|--------|---------|--------|-----|
| Overall Completion | 68% | 100% | +32% |
| Critical Gaps (P1) | 1 | 0 | 1 to fix |
| High Gaps (P2) | 4 | 0 | 4 to fix |
| Medium Gaps (P3) | 3 | 0 | 3 to fix |
| Estimated Effort | — | 102 hours | ~3 weeks |

---

## Phase Overview

| Phase | Focus | Duration | Exit Gate |
|-------|-------|----------|-----------|
| **1** | Critical Infrastructure (P1) | Week 1 | Heartbeat system fully operational |
| **2** | Security & Core Features (P2) | Week 2 | Vector indexes + HMAC signing live |
| **3** | Collaboration & Polish (P3-P5) | Week 3 | All protocols complete |

---

## Phase 1: Critical Infrastructure (Week 1)
**Goal:** Fix the P1 heartbeat gap that renders failover detection non-functional

### Sprint 1.1: Heartbeat Write Side (Days 1-2)
**Owner:** Temüjin (Developer)  
**Effort:** 6 hours  
**Priority:** P1-CRITICAL

| Task | File | Description | Acceptance Criteria |
|------|------|-------------|---------------------|
| 1.1.1 | `heartbeat_writer.py` | Create sidecar script that writes `Agent.infra_heartbeat` every 30s | Script runs continuously, updates Neo4j every 30s |
| 1.1.2 | `entrypoint.sh` | Modify to launch heartbeat_writer.py as background process | Sidecar starts with main application |
| 1.1.3 | `openclaw_memory.py` | Add functional heartbeat to `claim_task()` - update `Agent.last_heartbeat` | Every task claim updates heartbeat timestamp |
| 1.1.4 | `openclaw_memory.py` | Add functional heartbeat to `complete_task()` - update `Agent.last_heartbeat` | Every task completion updates heartbeat timestamp |
| 1.1.5 | `test_heartbeat.py` | Unit tests for heartbeat system | 100% coverage of heartbeat writes |

**Critical Path:**
```
1.1.1 → 1.1.2 → 1.1.3 → 1.1.4 → 1.1.5
```

**Verification:**
```python
# After implementation, this query should return recent timestamps
MATCH (a:Agent {name: 'Kublai'})
RETURN a.infra_heartbeat, a.last_heartbeat
# Both should be within last 60 seconds
```

**Risk Mitigation:**
- If sidecar fails, main app continues (graceful degradation)
- Circuit breaker prevents write storms
- Fallback to in-process heartbeat if sidecar unavailable

---

## Phase 2: Security & Core Features (Week 2)
**Goal:** Complete P2 gaps (vector indexes, HMAC signing, cross-agent subscriptions)

### Sprint 2.1: Vector Indexes (Days 3-4)
**Owner:** Temüjin (Developer)  
**Effort:** 12 hours  
**Priority:** P2-HIGH

| Task | File | Description | Acceptance Criteria |
|------|------|-------------|---------------------|
| 2.1.1 | `005_vector_indexes.cypher` | Create missing vector indexes | Indexes created successfully |
| 2.1.2 | `005_vector_indexes.cypher` | `belief_embedding` index for Belief nodes | 384-dim, cosine similarity |
| 2.1.3 | `005_vector_indexes.cypher` | `memory_entry_embedding` index for MemoryEntry | 384-dim, cosine similarity |
| 2.1.4 | `neo4j_memory.py` | Update schema initialization to include vector indexes | Auto-create on startup |
| 2.1.5 | `test_vector_indexes.py` | Verify vector search works | Semantic queries return results |

**Cypher Migrations:**
```cypher
// 2.1.2: Belief embedding index
CREATE VECTOR INDEX belief_embedding IF NOT EXISTS
FOR (b:Belief) ON b.embedding
OPTIONS {indexConfig: {`vector.dimensions`: 384, `vector.similarity_function`: 'cosine'}};

// 2.1.3: MemoryEntry embedding index  
CREATE VECTOR INDEX memory_entry_embedding IF NOT EXISTS
FOR (m:MemoryEntry) ON m.embedding
OPTIONS {indexConfig: {`vector.dimensions`: 384, `vector.similarity_function`: 'cosine'}};
```

---

### Sprint 2.2: HMAC-SHA256 Signing (Days 5-6)
**Owner:** Temüjin (Developer)  
**Effort:** 8 hours  
**Priority:** P2-HIGH

| Task | File | Description | Acceptance Criteria |
|------|------|-------------|---------------------|
| 2.2.1 | `message_signer.py` | Verify MessageSigner class exists | Class implements sign() and verify() |
| 2.2.2 | `agent_spawner_direct.py` | Wire signing into agentToAgent calls | All inter-agent messages signed |
| 2.2.3 | `agent_spawner_direct.py` | Add signature verification middleware | Reject unsigned/failed-sig messages |
| 2.2.4 | `delegation_protocol.py` | Update to use signed messages | Delegations include HMAC sig |
| 2.2.5 | `test_message_signing.py` | Test signing/verification | Tampered messages rejected |

**Security Flow:**
```python
# Before sending agent-to-agent message
signer = MessageSigner(agent_key)
signature = signer.sign(message_payload)
message['signature'] = signature
message['sender_key_id'] = agent_key.id

# On receive
verifier = MessageVerifier(trusted_keys)
if not verifier.verify(message):
    raise SecurityError("Invalid message signature")
```

---

### Sprint 2.3: Cross-Agent Subscriptions (Days 7-8)
**Owner:** Kublai (Orchestrator) + Temüjin  
**Effort:** 16 hours  
**Priority:** P2-HIGH

| Task | File | Description | Acceptance Criteria |
|------|------|-------------|---------------------|
| 2.3.1 | `006_subscriptions.cypher` | Create SUBSCRIBES_TO relationship schema | Relationship type exists with properties |
| 2.3.2 | `subscription_manager.py` | Implement subscription CRUD | Agents can subscribe/unsubscribe to topics |
| 2.3.3 | `notification_dispatcher.py` | Dispatch notifications to subscribers | Published events reach all subscribers |
| 2.3.4 | `api-routes.js` | Add subscription management API | REST endpoints for subscriptions |
| 2.3.5 | `test_subscriptions.py` | E2E subscription tests | Subscribe → Publish → Receive flow works |

**Schema:**
```cypher
(agent:Agent)-[s:SUBSCRIBES_TO {
    topic: 'research.completed',
    filter: '{"min_confidence": 0.8}',
    created_at: datetime()
}]->(target:Agent)
```

---

## Phase 3: Collaboration & Polish (Week 3)
**Goal:** Complete P3-P5 gaps for full feature parity

### Sprint 3.1: Scheduled Reflection (Day 9)
**Owner:** Ögedei (Operations)  
**Effort:** 4 hours  
**Priority:** P3-MEDIUM

| Task | File | Description | Acceptance Criteria |
|------|------|-------------|---------------------|
| 3.1.1 | `railway.toml` | Add weekly reflection cron | Cron schedule: `0 0 * * 0` (Sundays) |
| 3.1.2 | `heartbeat_master.py` | Wire reflection task to trigger | Reflection runs automatically |
| 3.1.3 | `proactive-reflection.js` | Ensure cron callback works | Weekly reflection generates proposals |
| 3.1.4 | `test_reflection_schedule.py` | Verify scheduling | Task runs on schedule |

---

### Sprint 3.2: Vetting Handlers (Days 10-11)
**Owner:** Ögedei + Temüjin  
**Effort:** 8 hours  
**Priority:** P3-MEDIUM

| Task | File | Description | Acceptance Criteria |
|------|------|-------------|---------------------|
| 3.2.1 | `vetting_handlers.py` | Implement Ögedei vetting handler | Validates proposals against policy |
| 3.2.2 | `vetting_handlers.py` | Implement Temüjin implementation handler | Executes approved proposals |
| 3.2.3 | `delegation-protocol.js` | Wire handlers to state machine | State transitions trigger handlers |
| 3.2.4 | `test_vetting_handlers.py` | Test handler workflows | End-to-end proposal flow works |

**Workflow:**
```
Proposal → Ögedei Review → Approved → Temüjin Implement → Validated → Synced
     ↓           ↓              ↓            ↓                ↓          ↓
  proposed  under_review   approved    implementing     validating   synced
```

---

### Sprint 3.3: Jochi-Temüjin Collaboration (Days 12-13)
**Owner:** Jochi + Temüjin  
**Effort:** 12 hours  
**Priority:** P3-MEDIUM

| Task | File | Description | Acceptance Criteria |
|------|------|-------------|---------------------|
| 3.3.1 | `collaboration_protocol.py` | Implement handoff workflow | Jochi → Temüjin task passing |
| 3.3.2 | `backend_detection.py` | Automate backend issue detection | Detects issues without manual trigger |
| 3.3.3 | `auto_fix_validation.py` | Validate automated fixes | Tests confirm fixes work |
| 3.3.4 | `test_collaboration.py` | E2E collaboration tests | Full handoff flow automated |

---

### Sprint 3.4: Remaining Items (Days 14-15)
**Owner:** All Agents  
**Effort:** 20 hours (parallel)  
**Priority:** P4-P5

| Task | Owner | Description | Effort |
|------|-------|-------------|--------|
| 3.4.1 | Chagatai + Kublai | Meta-learning engine | 16h |
| 3.4.2 | Chagatai | ARCHITECTURE.md bidirectional sync | 8h |
| 3.4.3 | Jochi | Kaizen quality tracking dashboard | 8h |
| 3.4.4 | Ögedei | Signal alerting verification | 4h |
| 3.4.5 | Kublai | CBAC enforcement completion | 8h |

---

## Resource Allocation

| Week | Temüjin | Kublai | Jochi | Chagatai | Ögedei | Total |
|------|---------|--------|-------|----------|--------|-------|
| 1 | 6h | — | — | — | — | 6h |
| 2 | 36h | 16h | — | — | — | 52h |
| 3 | 12h | 8h | 20h | 24h | 12h | 76h |
| **Total** | **54h** | **24h** | **20h** | **24h** | **12h** | **134h** |

*Note: Hours are parallelizable where tasks don't have dependencies*

---

## Risk Management

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Heartbeat sidecar fails to start | Low | Critical | Graceful fallback to in-process writes |
| Neo4j vector index creation fails | Low | High | Check version compatibility (5.15+) |
| HMAC key rotation complexity | Medium | Medium | Version keys, support graceful rotation |
| Subscription race conditions | Medium | Medium | Use Neo4j transactions for subscribe+notify |
| Schedule overruns | Medium | Medium | Parallelize P4-P5 items, defer if needed |

---

## Success Criteria

### Phase 1 Exit Gate (Week 1)
- [ ] `heartbeat_writer.py` running in production
- [ ] `claim_task()` and `complete_task()` update heartbeats
- [ ] All 6 agents show fresh timestamps in Neo4j
- [ ] Failover detection works end-to-end

### Phase 2 Exit Gate (Week 2)
- [ ] All vector indexes created and queryable
- [ ] Inter-agent messages are HMAC-signed
- [ ] Subscriptions work across agents
- [ ] Security audit passes

### Phase 3 Exit Gate (Week 3)
- [ ] Reflection runs automatically weekly
- [ ] Vetting handlers process proposals
- [ ] Jochi-Temüjin collaboration automated
- [ ] Overall completion: 95%+

---

## Progress Tracking

### Daily Standup Questions
1. Did you complete yesterday's tasks?
2. What are you working on today?
3. Any blockers?

### Weekly Review
- Burndown chart of gap closure
- Demo of completed features
- Retrospective and plan adjustment

### Final Verification
```bash
# Run full verification suite
python scripts/verify_gaps_closed.py
```

---

## Appendix: Dependency Graph

```
Phase 1:
  1.1.1 (writer.py) → 1.1.2 (entrypoint.sh)
       ↓
  1.1.3 (claim_task) → 1.1.4 (complete_task) → 1.1.5 (tests)

Phase 2:
  2.1.1-5 (vector indexes) ──┐
  2.2.1-5 (HMAC signing) ────┼── Parallel
  2.3.1-5 (subscriptions) ───┘

Phase 3:
  3.1.1-4 (reflection) ──┐
  3.2.1-4 (vetting) ─────┼── Parallel
  3.3.1-4 (collab) ──────┘
       ↓
  3.4.1-5 (polish) ─── Parallel
```

---

**Document Control:**
| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-09 | Kublai | Initial gap remediation plan |

**Approval:**
- [ ] Kublai (Architecture alignment)
- [ ] Temüjin (Technical feasibility)
- [ ] Jochi (Quality assurance)
