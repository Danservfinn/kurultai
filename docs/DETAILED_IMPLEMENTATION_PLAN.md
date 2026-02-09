# Kurultai Detailed Implementation Plan
## Closing the 32% Gap: P1-P5 Remediation with Horde-Plan Patterns

**Version:** 1.0  
**Date:** 2026-02-09  
**Analyst:** Jochi (Gap Analysis) → Temüjin (Implementation Planning)  
**Classification:** Critical - Production Readiness

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Gap Inventory](#2-gap-inventory)
3. [Phase-by-Phase Plan](#3-phase-by-phase-plan)
4. [Per-Task Specification](#4-per-task-specification)
5. [Resource Calendar](#5-resource-calendar)
6. [Risk Register](#6-risk-register)
7. [Verification Checklist](#7-verification-checklist)

---

## 1. Executive Summary

### 1.1 Current State Assessment

| Metric | Value | Status |
|--------|-------|--------|
| Overall Completion | 68% | ⚠️ Below Production Threshold |
| Critical Gaps (P1) | 1 | 🔴 Non-functional Failover |
| High Gaps (P2) | 4 | 🟡 Security & Core Features Incomplete |
| Medium Gaps (P3) | 3 | 🟢 Collaboration Protocols Partial |
| Low Gaps (P4-P5) | 4 | 🟢 Polish Items Pending |

### 1.2 Target State

| Metric | Target | Date |
|--------|--------|------|
| Overall Completion | 100% | 2026-03-02 |
| Critical Gaps | 0 | Week 1 |
| High Gaps | 0 | Week 2 |
| All Gaps | 0 | Week 3 |

### 1.3 Resource Requirements

```yaml
Total Effort: 110 hours (revised from 102)
Timeline: 3 weeks (15 working days)
Parallel Workstreams: 4 max
Required Agents:
  - Temüjin (Developer): 54h
  - Kublai (Orchestrator): 24h
  - Jochi (Analyst): 16h
  - Chagatai (Writer): 16h
  - Ögedei (Operations): 12h
```

### 1.4 Critical Path Summary

```
[CRITICAL PATH - Must Complete in Sequence]
┌─────────────────────────────────────────────────────────────────────┐
│ P1-T1 → P1-T2 → P1-T3 → P1-T4 → P1-T5 (Week 1)                    │
│ heartbeat_writer → entrypoint.sh → claim_task/complete_task → tests │
└─────────────────────────────────────────────────────────────────────┘

[PARALLEL WORKSTREAMS - Can Execute Concurrently]
┌──────────────────┬──────────────────┬──────────────────┐
│ Vector Indexes   │ HMAC Signing     │ Subscriptions    │
│ (P2-T1 to P2-T5) │ (P2-T6 to P2-T10)│ (P2-T11 to P2-T15)│
└──────────────────┴──────────────────┴──────────────────┘
```

---

## 2. Gap Inventory

### 2.1 P1 (Critical) - 1 Item

| ID | Gap | Severity | Source Plan | Root Cause |
|----|-----|----------|-------------|------------|
| P1-T1 | **Heartbeat write side not invoked** - Failover system reads `infra_heartbeat` and `last_heartbeat` timestamps that are never written | CRITICAL | Two-Tier Heartbeat | Missing sidecar script and entrypoint integration |

**Impact Analysis:**
- Failover detection is non-functional
- Agent health monitoring reports false negatives
- Circuit breaker logic receives stale data
- Production deployment risk: HIGH

**Business Impact:**
- Cannot detect agent failures in production
- Automated recovery systems will not trigger
- Operational blind spot during critical operations

---

### 2.2 P2 (High) - 4 Items

| ID | Gap | Severity | Source Plan | Root Cause |
|----|-----|----------|-------------|------------|
| P2-T1 | **Vector indexes incomplete** - `belief_embedding` and `memory_entry_embedding` indexes missing | HIGH | Neo4j Memory Design | Migration files not created |
| P2-T6 | **HMAC-SHA256 signing middleware not integrated** - `MessageSigner` exists but not wired to agent-to-agent calls | HIGH | Kurultai v0.3 | Security layer not connected to transport |
| P2-T11 | **Cross-agent subscription system not implemented** - SUBSCRIBES_TO relationship schema missing | HIGH | Neo4j Memory Design | Notification dispatcher not built |
| P2-T16 | **SharedKnowledge pool implementation** - Broadcast mechanism for cross-agent knowledge sharing | HIGH | Neo4j Memory Design | Knowledge sharing infrastructure incomplete |

**Impact Analysis:**
- Semantic search on Belief nodes fails
- Inter-agent communication is unsigned (security gap)
- Agents cannot subscribe to events from other agents
- Knowledge silos persist between agents

---

### 2.3 P3 (Medium) - 3 Items

| ID | Gap | Severity | Source Plan | Root Cause |
|----|-----|----------|-------------|------------|
| P3-T1 | **Scheduled reflection not wired to cron** - Weekly reflection trigger exists but not connected | MEDIUM | Kublai Self-Awareness | Cron job defined but handler not implemented |
| P3-T6 | **Ögedei/Temüjin vetting handlers incomplete** - Placeholder implementations only | MEDIUM | Kublai Proactive Self-Awareness | State machine handlers not wired |
| P3-T11 | **Jochi-Temüjin collaboration protocol partial** - Backend issue detection automation incomplete | MEDIUM | Kurultai v0.3 | Handoff workflow not fully automated |

**Impact Analysis:**
- Self-awareness system requires manual triggering
- Proposal workflow stalls at vetting stage
- Backend issue detection requires manual intervention

---

### 2.4 P4-P5 (Low) - 4 Items

| ID | Gap | Severity | Source Plan | Root Cause |
|----|-----|----------|-------------|------------|
| P4-T1 | **Meta-learning engine not implemented** - Reflection-to-rule conversion missing | MEDIUM | Kurultai v0.3 | Pattern clustering not built |
| P4-T2 | **ARCHITECTURE.md bidirectional sync** - Proposals can sync to docs but not vice versa | LOW | Kublai Self-Understanding | Sync guardrails incomplete |
| P5-T1 | **Kaizen quality tracking dashboard** - Visual tracking of continuous improvement | LOW | Kurultai v0.3 | UI components not built |
| P5-T2 | **Signal alerting verification** - Test Signal integration in production | LOW | Jochi Test Automation | Integration tests pending |

---

## 3. Phase-by-Phase Plan

### 3.1 Phase 1: Critical Infrastructure (Week 1)

**Goal:** Fix P1 gap that renders failover detection non-functional

**Duration:** Days 1-5 (Mon-Fri)  
**Exit Gate:** Heartbeat system fully operational, all agents show fresh timestamps

**Sprint Structure:**
```
Week 1 - Critical Infrastructure
├── Day 1-2: Heartbeat Writer Sidecar (P1-T1 to P1-T3)
│   ├── Create heartbeat_writer.py
│   ├── Create 005_vector_indexes.cypher (parallel)
│   └── Unit tests
├── Day 3-4: Entrypoint Integration (P1-T4)
│   ├── Modify entrypoint.sh
│   └── Integration tests
└── Day 5: Functional Heartbeat & Testing (P1-T5 to P1-T7)
    ├── Modify claim_task()/complete_task()
    ├── Complete integration testing
    └── Phase 1 exit gate verification
```

**Dependencies:**
- P1-T1 → P1-T4 (writer must exist before entrypoint can call it)
- P1-T4 → P1-T5 (entrypoint must be ready before functional heartbeat)
- All P1 tasks → Phase 2 (P2 work can start after P1-T3)

---

### 3.2 Phase 2: Security & Core Features (Week 2)

**Goal:** Close all P2 gaps (vector indexes, HMAC signing, cross-agent subscriptions)

**Duration:** Days 6-10 (Mon-Fri)  
**Exit Gate:** All vector indexes queryable, inter-agent messages signed, subscriptions functional

**Sprint Structure:**
```
Week 2 - Security & Core Features
├── Day 6-7: Vector Indexes (P2-T1 to P2-T5)
│   ├── Create 005_vector_indexes.cypher
│   ├── Update migration runner
│   ├── Update neo4j_memory.py
│   └── Test semantic queries
├── Day 8: HMAC-SHA256 Signing (P2-T6 to P2-T10)
│   ├── Verify MessageSigner class
│   ├── Wire signing into agent_spawner_direct.py
│   └── Add verification middleware
└── Day 9-10: Cross-Agent Subscriptions (P2-T11 to P2-T16)
    ├── Create 006_subscriptions.cypher
    ├── Implement subscription_manager.py
    ├── Implement notification_dispatcher.py
    └── E2E subscription tests
```

**Parallel Workstreams:**
- Vector Indexes (Temüjin) || HMAC Signing (Temüjin) - sequential
- Subscriptions (Kublai + Temüjin) - parallel with above after Day 8

**Dependencies:**
- P2-T1 → P2-T5 (indexes must be created before use)
- P2-T6 → P2-T10 (signer must exist before integration)
- P2-T11 → P2-T16 (subscription schema → manager → dispatcher)

---

### 3.3 Phase 3: Collaboration & Polish (Week 3)

**Goal:** Complete P3-P5 gaps for full feature parity

**Duration:** Days 11-15 (Mon-Fri)  
**Exit Gate:** Reflection automated, vetting handlers operational, collaboration protocols complete

**Sprint Structure:**
```
Week 3 - Collaboration & Polish
├── Day 11: Scheduled Reflection (P3-T1 to P3-T5)
│   ├── Wire reflection to cron
│   ├── Implement trigger handler
│   └── Verify weekly schedule
├── Day 12-13: Vetting Handlers (P3-T6 to P3-T10)
│   ├── Implement Ögedei vetting handler
│   ├── Implement Temüjin implementation handler
│   └── Wire to delegation protocol
└── Day 14-15: Remaining Items (P4-T1 to P5-T2)
    ├── Meta-learning engine (parallel)
    ├── ARCHITECTURE.md bidirectional sync
    ├── Kaizen dashboard
    └── Signal alerting verification
```

**Dependencies:**
- P3-T1 → P3-T5 (cron → handler → verification)
- P3-T6 → P3-T10 (vetting → implementation → validation)
- P2-T11 → P3-T6 (subscriptions enable vetting notifications)

---

## 4. Per-Task Specification

### 4.1 Phase 1: Critical Infrastructure Tasks

#### P1-T1: Create heartbeat_writer.py Sidecar

```yaml
Task ID: P1-T1
Priority: P1-CRITICAL
Owner: Temüjin (Developer)
Estimated Hours: 2
Dependencies: None
Files to Create:
  - scripts/heartbeat_writer.py (new)
```

**Description:**
Create a standalone sidecar script that writes `Agent.infra_heartbeat` timestamp every 30 seconds to Neo4j. This is the critical missing piece that makes failover detection functional.

**Implementation Details:**

```python
#!/usr/bin/env python3
"""
Heartbeat Writer Sidecar

Writes infra_heartbeat timestamp every 30 seconds.
Run as background process alongside main application.

Environment Variables:
    NEO4J_URI: Neo4j connection URI
    NEO4J_USER: Neo4j username (default: neo4j)
    NEO4J_PASSWORD: Neo4j password
    HEARTBEAT_INTERVAL: Seconds between writes (default: 30)
    CIRCUIT_BREAKER_THRESHOLD: Failures before pause (default: 3)
"""

import os
import sys
import time
import logging
from datetime import datetime, timezone
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, Neo4jError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger("kurultai.heartbeat_writer")

# Configuration
NEO4J_URI = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
NEO4J_USER = os.environ.get('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.environ.get('NEO4J_PASSWORD')
HEARTBEAT_INTERVAL = int(os.environ.get('HEARTBEAT_INTERVAL', '30'))
CIRCUIT_BREAKER_THRESHOLD = int(os.environ.get('CIRCUIT_BREAKER_THRESHOLD', '3'))

# Agent list (all 6 agents)
AGENTS = ['Kublai', 'Möngke', 'Chagatai', 'Temüjin', 'Jochi', 'Ögedei']


class HeartbeatWriter:
    """Writes infra_heartbeat timestamps to all agents."""
    
    def __init__(self):
        self.driver = None
        self.failure_count = 0
        self.circuit_open = False
        self.circuit_reset_time = None
        
    def connect(self):
        """Connect to Neo4j."""
        if not NEO4J_PASSWORD:
            logger.error("NEO4J_PASSWORD not set")
            sys.exit(1)
            
        try:
            self.driver = GraphDatabase.driver(
                NEO4J_URI,
                auth=(NEO4J_USER, NEO4J_PASSWORD)
            )
            self.driver.verify_connectivity()
            logger.info(f"Connected to Neo4j at {NEO4J_URI}")
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            sys.exit(1)
    
    def write_heartbeat(self, agent_name: str):
        """Write infra_heartbeat for a single agent."""
        timestamp = datetime.now(timezone.utc).isoformat()
        
        cypher = """
        MERGE (a:Agent {name: $agent_name})
        SET a.infra_heartbeat = $timestamp
        RETURN a.name as agent
        """
        
        with self.driver.session() as session:
            result = session.run(cypher, agent_name=agent_name, timestamp=timestamp)
            record = result.single()
            if record:
                logger.debug(f"Heartbeat written for {agent_name}")
                return True
            return False
    
    def write_all_heartbeats(self):
        """Write heartbeats for all agents."""
        if self.circuit_open:
            if datetime.now(timezone.utc) < self.circuit_reset_time:
                logger.warning("Circuit breaker open, skipping heartbeat cycle")
                return
            else:
                logger.info("Circuit breaker reset, resuming heartbeats")
                self.circuit_open = False
                self.failure_count = 0
        
        try:
            for agent in AGENTS:
                self.write_heartbeat(agent)
            
            # Reset failure count on success
            self.failure_count = 0
            logger.info(f"Heartbeats written for {len(AGENTS)} agents")
            
        except (ServiceUnavailable, Neo4jError) as e:
            self.failure_count += 1
            logger.error(f"Heartbeat write failed ({self.failure_count}/{CIRCUIT_BREAKER_THRESHOLD}): {e}")
            
            if self.failure_count >= CIRCUIT_BREAKER_THRESHOLD:
                logger.critical("Circuit breaker triggered - pausing heartbeats for 60s")
                self.circuit_open = True
                self.circuit_reset_time = datetime.now(timezone.utc).timestamp() + 60
    
    def run(self):
        """Main loop - write heartbeats every interval."""
        logger.info(f"Starting heartbeat writer (interval: {HEARTBEAT_INTERVAL}s)")
        
        while True:
            start_time = time.time()
            self.write_all_heartbeats()
            
            # Sleep until next interval
            elapsed = time.time() - start_time
            sleep_time = max(0, HEARTBEAT_INTERVAL - elapsed)
            time.sleep(sleep_time)
    
    def close(self):
        """Close Neo4j connection."""
        if self.driver:
            self.driver.close()


def main():
    writer = HeartbeatWriter()
    writer.connect()
    
    try:
        writer.run()
    except KeyboardInterrupt:
        logger.info("Heartbeat writer stopped")
    finally:
        writer.close()


if __name__ == '__main__':
    main()
```

**Test Plan:**
```python
# tests/test_heartbeat_writer.py
def test_heartbeat_writer_creates_infra_heartbeat():
    """Verify writer creates infra_heartbeat property."""
    # Setup: Start writer in background thread
    # Action: Wait for 2 heartbeat cycles (60s)
    # Assert: Query Neo4j for infra_heartbeat on all agents
    # Assert: All timestamps should be within last 60s
    pass

def test_circuit_breaker_triggers_after_failures():
    """Verify circuit breaker pauses writes after threshold."""
    # Setup: Mock Neo4j to fail connections
    # Action: Trigger 3 write failures
    # Assert: Circuit breaker opens
    # Assert: No writes attempted for 60s
    pass
```

**Acceptance Criteria:**
- [ ] Script runs continuously without errors
- [ ] Writes `infra_heartbeat` to all 6 agents every 30s
- [ ] Creates Agent nodes if they don't exist
- [ ] Circuit breaker triggers after 3 consecutive failures
- [ ] Logs heartbeat writes at INFO level
- [ ] Handles Neo4j reconnection gracefully

---

#### P1-T2: Create heartbeat_writer Unit Tests

```yaml
Task ID: P1-T2
Priority: P1-CRITICAL
Owner: Temüjin (Developer)
Estimated Hours: 1
Dependencies: P1-T1
Files to Create:
  - tests/test_heartbeat_writer.py (new)
```

**Description:**
Unit tests for heartbeat_writer.py covering normal operation, circuit breaker, and error handling.

**Test Cases:**
1. `test_write_heartbeat_updates_timestamp` - Verify timestamp is written
2. `test_write_heartbeat_creates_agent` - Verify agent node creation
3. `test_circuit_breaker_opens_after_threshold` - Verify circuit breaker logic
4. `test_circuit_breaker_resets_after_timeout` - Verify circuit reset
5. `test_graceful_shutdown` - Verify cleanup on SIGTERM

---

#### P1-T3: Create 005_vector_indexes.cypher

```yaml
Task ID: P1-T3
Priority: P1-CRITICAL (parallel with P1-T1)
Owner: Temüjin (Developer)
Estimated Hours: 1
Dependencies: None
Files to Create:
  - scripts/migrations/005_vector_indexes.cypher (new)
```

**Description:**
Create migration file for missing vector indexes. This can be done in parallel with heartbeat work.

**Cypher Migration:**
```cypher
/**
 * Migration 005: Vector Index Completion
 * Creates missing vector indexes for semantic search
 * Dependencies: Neo4j 5.15+ with GDS plugin
 */

// Belief embedding index - for reflection consolidation
CREATE VECTOR INDEX belief_embedding IF NOT EXISTS
FOR (b:Belief) ON b.embedding
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 384,
        `vector.similarity_function`: 'cosine'
    }
};

// MemoryEntry embedding index - for memory curation
CREATE VECTOR INDEX memory_entry_embedding IF NOT EXISTS
FOR (m:MemoryEntry) ON m.embedding
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 384,
        `vector.similarity_function`: 'cosine'
    }
};

// Task embedding index - for semantic task matching (future use)
CREATE VECTOR INDEX task_embedding IF NOT EXISTS
FOR (t:Task) ON t.embedding
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 384,
        `vector.similarity_function`: 'cosine'
    }
};

// Verify indexes were created
SHOW INDEXES YIELD name, type, entityType, labelsOrTypes, properties
WHERE type = 'VECTOR'
RETURN name, entityType, labelsOrTypes, properties
ORDER BY name;
```

**Acceptance Criteria:**
- [ ] Migration runs without errors on Neo4j 5.15+
- [ ] All 3 vector indexes created
- [ ] Indexes use 384 dimensions (MiniLM-L6-v2)
- [ ] Cosine similarity function configured
- [ ] Verification query returns all indexes

---

#### P1-T4: Modify entrypoint.sh to Launch Sidecar

```yaml
Task ID: P1-T4
Priority: P1-CRITICAL
Owner: Temüjin (Developer)
Estimated Hours: 1
Dependencies: P1-T1, P1-T2
Files to Modify:
  - moltbot-railway-template/entrypoint.sh (lines 144-150)
```

**Description:**
Modify entrypoint.sh to launch heartbeat_writer.py as a background process.

**Current State (lines 144-150):**
```bash
# =============================================================================
# START HEARTBEAT SIDECAR
# =============================================================================
if [ -n "$NEO4J_PASSWORD" ] && [ -f /app/scripts/heartbeat_writer.py ]; then
    echo "Starting heartbeat writer sidecar..."
    su -s /bin/sh moltbot -c "NEO4J_URI=$NEO4J_URI NEO4J_USER=${NEO4J_USER:-neo4j} NEO4J_PASSWORD=$NEO4J_PASSWORD python /app/scripts/heartbeat_writer.py &"
fi
```

**Required Changes:**
The current entrypoint.sh already has the basic structure but needs enhancement:

```bash
# =============================================================================
# START HEARTBEAT SIDECAR
# =============================================================================
# This sidecar writes infra_heartbeat every 30s for failover detection
HEARTBEAT_WRITER_PID=""

if [ -n "$NEO4J_PASSWORD" ] && [ -f /app/scripts/heartbeat_writer.py ]; then
    echo "=== Starting Heartbeat Writer Sidecar ==="
    
    # Export environment for the sidecar
    export HEARTBEAT_INTERVAL="${HEARTBEAT_INTERVAL:-30}"
    export CIRCUIT_BREAKER_THRESHOLD="${CIRCUIT_BREAKER_THRESHOLD:-3}"
    
    # Start sidecar as moltbot user
    su -s /bin/sh moltbot -c "
        cd /app && \
        NEO4J_URI=$NEO4J_URI \
        NEO4J_USER=${NEO4J_USER:-neo4j} \
        NEO4J_PASSWORD=$NEO4J_PASSWORD \
        HEARTBEAT_INTERVAL=$HEARTBEAT_INTERVAL \
        CIRCUIT_BREAKER_THRESHOLD=$CIRCUIT_BREAKER_THRESHOLD \
        python /app/scripts/heartbeat_writer.py >> /data/logs/heartbeat_writer.log 2>&1
    " &
    
    HEARTBEAT_WRITER_PID=$!
    echo "  Heartbeat writer started with PID $HEARTBEAT_WRITER_PID"
    echo "  Logs: /data/logs/heartbeat_writer.log"
    
    # Verify it started
    sleep 2
    if kill -0 $HEARTBEAT_WRITER_PID 2>/dev/null; then
        echo "  ✅ Heartbeat writer is running"
    else
        echo "  ⚠️  Heartbeat writer may have failed to start"
    fi
    echo "=========================================="
fi
```

**Acceptance Criteria:**
- [ ] Sidecar starts successfully on container launch
- [ ] Logs written to /data/logs/heartbeat_writer.log
- [ ] PID tracked for monitoring
- [ ] Graceful shutdown handled on container stop
- [ ] Environment variables passed correctly

---

#### P1-T5: Add Functional Heartbeat to claim_task()

```yaml
Task ID: P1-T5
Priority: P1-CRITICAL
Owner: Temüjin (Developer)
Estimated Hours: 1
Dependencies: P1-T4
Files to Modify:
  - openclaw_memory.py (lines 399-465, specifically the claim_task method)
```

**Description:**
Modify `claim_task()` to update `Agent.last_heartbeat` when a task is claimed.

**Current State (lines 399-465):**
The `claim_task` method already has a line that updates `a.last_heartbeat`:
```python
SET t.status = 'in_progress',
    t.claimed_by = $agent,
    t.claimed_at = $claimed_at
WITH t
MATCH (a:Agent {name: $agent})
SET a.last_heartbeat = $claimed_at
RETURN t
```

**Verification:**
Looking at the current code, this appears to already be implemented. Let's verify by examining the actual Cypher query more closely.

**Action Required:**
Verify the existing implementation is correct and add the same pattern to `complete_task()` if missing.

---

#### P1-T6: Add Functional Heartbeat to complete_task()

```yaml
Task ID: P1-T6
Priority: P1-CRITICAL
Owner: Temüjin (Developer)
Estimated Hours: 1
Dependencies: P1-T5
Files to Modify:
  - openclaw_memory.py (lines 465-520, specifically the complete_task method)
```

**Description:**
Verify and enhance `complete_task()` to update `Agent.last_heartbeat` when a task is completed.

**Current State:**
The existing `complete_task` method at line 465 already has:
```python
WITH t
MATCH (a:Agent {name: t.claimed_by})
SET a.last_heartbeat = $completed_at
RETURN t.delegated_by as delegated_by, t.claimed_by as claimed_by
```

**Verification Required:**
- [ ] Confirm both `claim_task` and `complete_task` update `last_heartbeat`
- [ ] Verify timestamps use UTC timezone
- [ ] Ensure atomic updates (within same transaction)

---

#### P1-T7: Create Integration Tests for Heartbeat System

```yaml
Task ID: P1-T7
Priority: P1-CRITICAL
Owner: Jochi (Analyst)
Estimated Hours: 2
Dependencies: P1-T5, P1-T6
Files to Create:
  - tests/integration/test_heartbeat_integration.py (new)
```

**Description:**
Integration tests verifying the full heartbeat system including sidecar writes and functional heartbeats.

**Test Cases:**
1. `test_infra_heartbeat_written_by_sidecar` - Verify sidecar writes timestamps
2. `test_functional_heartbeat_on_claim` - Verify claim updates timestamp
3. `test_functional_heartbeat_on_complete` - Verify complete updates timestamp
4. `test_heartbeat_failover_threshold` - Verify 90s/120s thresholds work
5. `test_all_agents_have_recent_heartbeat` - Verify all 6 agents have fresh timestamps

**Acceptance Criteria:**
- [ ] All integration tests pass
- [ ] Tests run in CI/CD pipeline
- [ ] Tests verify actual Neo4j writes
- [ ] Mock time for deterministic testing

---

### 4.2 Phase 2: Security & Core Features Tasks

#### P2-T1: Create Vector Index Migration File

```yaml
Task ID: P2-T1
Priority: P2-HIGH
Owner: Temüjin (Developer)
Estimated Hours: 1
Dependencies: P1-T3
Files to Create:
  - migrations/v4_vector_indexes.py (new)
```

**Description:**
Create Python migration class for vector indexes to integrate with migration manager.

**Implementation:**
```python
"""Migration v4: Create vector indexes for semantic search."""

from migrations.migration_manager import Migration


class V4VectorIndexes(Migration):
    """Create missing vector indexes for Belief and MemoryEntry nodes."""
    
    version = 4
    name = "vector_indexes"
    description = "Create vector indexes for semantic search"
    
    def up(self, session):
        """Apply migration."""
        # Belief embedding index
        session.run("""
            CREATE VECTOR INDEX belief_embedding IF NOT EXISTS
            FOR (b:Belief) ON b.embedding
            OPTIONS {
                indexConfig: {
                    `vector.dimensions`: 384,
                    `vector.similarity_function`: 'cosine'
                }
            }
        """)
        
        # MemoryEntry embedding index
        session.run("""
            CREATE VECTOR INDEX memory_entry_embedding IF NOT EXISTS
            FOR (m:MemoryEntry) ON m.embedding
            OPTIONS {
                indexConfig: {
                    `vector.dimensions`: 384,
                    `vector.similarity_function`: 'cosine'
                }
            }
        """)
        
        print("✅ Vector indexes created")
    
    def down(self, session):
        """Rollback migration."""
        session.run("DROP INDEX belief_embedding IF EXISTS")
        session.run("DROP INDEX memory_entry_embedding IF EXISTS")
        print("✅ Vector indexes dropped")


def register(manager):
    """Register this migration with the manager."""
    manager.register(V4VectorIndexes())
```

---

#### P2-T2: Register v4 Migration in Runner

```yaml
Task ID: P2-T2
Priority: P2-HIGH
Owner: Temüjin (Developer)
Estimated Hours: 0.5
Dependencies: P2-T1
Files to Modify:
  - scripts/run_migrations.py (add v4 import)
```

---

#### P2-T3: Update OperationalMemory Schema Initialization

```yaml
Task ID: P2-T3
Priority: P2-HIGH
Owner: Temüjin (Developer)
Estimated Hours: 1
Dependencies: P2-T2
Files to Modify:
  - openclaw_memory.py (add ensure_vector_indexes method)
```

---

#### P2-T4: Create Vector Index Tests

```yaml
Task ID: P2-T4
Priority: P2-HIGH
Owner: Jochi (Analyst)
Estimated Hours: 1
Dependencies: P2-T3
Files to Create:
  - tests/test_vector_indexes.py
```

---

#### P2-T5: Verify Semantic Search Queries

```yaml
Task ID: P2-T5
Priority: P2-HIGH
Owner: Jochi (Analyst)
Estimated Hours: 1
Dependencies: P2-T4
Files to Create:
  - scripts/verify_vector_search.py
```

---

#### P2-T6: Verify MessageSigner Implementation

```yaml
Task ID: P2-T6
Priority: P2-HIGH
Owner: Temüjin (Developer)
Estimated Hours: 1
Dependencies: None
Files to Review:
  - tools/kurultai/security/registry_validator.py
```

**Description:**
Review existing HMAC implementation and extract MessageSigner for agent-to-agent communication.

**Current Implementation:**
The `RegistryValidator` class in `tools/kurultai/security/registry_validator.py` already implements HMAC-SHA256 signing:

```python
def _sign(self, entry_data: Dict) -> str:
    """Create HMAC-SHA256 signature for registry entry."""
    canonical = json.dumps(entry_data, sort_keys=True, separators=(',', ':'))
    signature = hmac.new(
        self.secret_key.encode('utf-8'),
        canonical.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return signature
```

**Action:**
Extract this into a reusable `MessageSigner` class in `tools/kurultai/security/message_signer.py`.

---

#### P2-T7: Create MessageSigner Class

```yaml
Task ID: P2-T7
Priority: P2-HIGH
Owner: Temüjin (Developer)
Estimated Hours: 2
Dependencies: P2-T6
Files to Create:
  - tools/kurultai/security/message_signer.py (new)
```

**Implementation:**
```python
#!/usr/bin/env python3
"""
HMAC-SHA256 Message Signing for Inter-Agent Communication

Provides cryptographic signing and verification for agent-to-agent messages.
Uses HMAC-SHA256 with agent-specific keys for non-repudiation.
"""

import os
import json
import hmac
import hashlib
import secrets
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta


@dataclass
class AgentKey:
    """Agent signing key."""
    agent_id: str
    key_id: str
    secret_key: str
    created_at: datetime
    expires_at: Optional[datetime] = None
    revoked: bool = False


class MessageSigner:
    """
    Sign and verify inter-agent messages using HMAC-SHA256.
    
    Usage:
        signer = MessageSigner(agent_key)
        message = {'type': 'task_delegation', 'task_id': '123', ...}
        signed_message = signer.sign_message(message)
        
        # On receive
        verifier = MessageVerifier(key_store)
        if verifier.verify_message(signed_message):
            process(message)
    """
    
    def __init__(self, agent_key: AgentKey):
        self.agent_key = agent_key
    
    def _canonicalize(self, data: Dict) -> str:
        """Create canonical JSON representation for signing."""
        # Sort keys for deterministic serialization
        return json.dumps(data, sort_keys=True, separators=(',', ':'))
    
    def sign_message(self, message: Dict, include_metadata: bool = True) -> Dict:
        """
        Sign a message and return signed version.
        
        Args:
            message: The message payload to sign
            include_metadata: Whether to add signing metadata
            
        Returns:
            Message with 'signature' and 'sig_metadata' fields added
        """
        # Create payload copy without any existing signature
        payload = {k: v for k, v in message.items() if k not in ('signature', 'sig_metadata')}
        
        # Add timestamp if requested
        if include_metadata:
            payload['_sig_ts'] = datetime.now(timezone.utc).isoformat()
            payload['_sig_agent'] = self.agent_key.agent_id
            payload['_sig_key_id'] = self.agent_key.key_id
        
        # Canonicalize and sign
        canonical = self._canonicalize(payload)
        signature = hmac.new(
            self.agent_key.secret_key.encode('utf-8'),
            canonical.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Return signed message
        signed = dict(message)
        signed['signature'] = signature
        signed['sig_metadata'] = {
            'agent_id': self.agent_key.agent_id,
            'key_id': self.agent_key.key_id,
            'timestamp': payload.get('_sig_ts'),
            'algorithm': 'HMAC-SHA256'
        }
        
        return signed
    
    def sign_delegation(self, task_id: str, delegator: str, delegate: str,
                       task_data: Dict) -> Dict:
        """Convenience method for signing task delegations."""
        message = {
            'type': 'task_delegation',
            'task_id': task_id,
            'delegator': delegator,
            'delegate': delegate,
            'task_data': task_data,
            'delegated_at': datetime.now(timezone.utc).isoformat()
        }
        return self.sign_message(message)


class MessageVerifier:
    """Verify signatures on received messages."""
    
    def __init__(self, key_store: 'KeyStore'):
        self.key_store = key_store
        self.clock_skew_tolerance = timedelta(seconds=300)  # 5 min tolerance
    
    def verify_message(self, signed_message: Dict) -> Tuple[bool, Optional[str]]:
        """
        Verify a signed message.
        
        Returns:
            (is_valid, error_message)
            is_valid: True if signature is valid
            error_message: None if valid, description if invalid
        """
        signature = signed_message.get('signature')
        metadata = signed_message.get('sig_metadata')
        
        if not signature or not metadata:
            return False, "Missing signature or metadata"
        
        # Extract signing info
        agent_id = metadata.get('agent_id')
        key_id = metadata.get('key_id')
        timestamp_str = metadata.get('timestamp')
        
        if not all([agent_id, key_id]):
            return False, "Incomplete signature metadata"
        
        # Get the signing key
        agent_key = self.key_store.get_key(agent_id, key_id)
        if not agent_key:
            return False, f"Unknown agent or key: {agent_id}/{key_id}"
        
        if agent_key.revoked:
            return False, f"Key has been revoked: {key_id}"
        
        if agent_key.expires_at and datetime.now(timezone.utc) > agent_key.expires_at:
            return False, f"Key has expired: {key_id}"
        
        # Verify timestamp (prevent replay attacks)
        if timestamp_str:
            try:
                timestamp = datetime.fromisoformat(timestamp_str)
                now = datetime.now(timezone.utc)
                if abs(now - timestamp) > self.clock_skew_tolerance:
                    return False, "Message timestamp outside acceptable window"
            except ValueError:
                return False, "Invalid timestamp format"
        
        # Reconstruct payload and verify signature
        payload = {k: v for k, v in signed_message.items() 
                  if k not in ('signature', 'sig_metadata')}
        
        # Add signing metadata back to payload for verification
        if timestamp_str:
            payload['_sig_ts'] = timestamp_str
        payload['_sig_agent'] = agent_id
        payload['_sig_key_id'] = key_id
        
        canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        expected_sig = hmac.new(
            agent_key.secret_key.encode('utf-8'),
            canonical.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(signature, expected_sig):
            return False, "Signature mismatch"
        
        return True, None


class KeyStore:
    """Store and retrieve agent signing keys."""
    
    def __init__(self, neo4j_driver=None):
        self.keys: Dict[str, AgentKey] = {}
        self.driver = neo4j_driver
        self._load_keys()
    
    def _load_keys(self):
        """Load keys from Neo4j or environment."""
        # Try loading from Neo4j first
        if self.driver:
            try:
                with self.driver.session() as session:
                    result = session.run("""
                        MATCH (ak:AgentKey)
                        RETURN ak.agent_id as agent_id,
                               ak.key_id as key_id,
                               ak.secret_key as secret_key,
                               ak.created_at as created_at,
                               ak.expires_at as expires_at,
                               ak.revoked as revoked
                    """)
                    for record in result:
                        key = AgentKey(
                            agent_id=record['agent_id'],
                            key_id=record['key_id'],
                            secret_key=record['secret_key'],
                            created_at=record['created_at'],
                            expires_at=record.get('expires_at'),
                            revoked=record.get('revoked', False)
                        )
                        self.keys[f"{key.agent_id}:{key.key_id}"] = key
            except Exception as e:
                print(f"Warning: Could not load keys from Neo4j: {e}")
        
        # Fallback to environment variables for development
        if not self.keys:
            self._load_from_env()
    
    def _load_from_env(self):
        """Load keys from environment for development."""
        for agent in ['Kublai', 'Möngke', 'Chagatai', 'Temüjin', 'Jochi', 'Ögedei']:
            env_key = os.environ.get(f"AGENT_KEY_{agent.upper()}")
            if env_key:
                key = AgentKey(
                    agent_id=agent,
                    key_id=f"{agent.lower()}-001",
                    secret_key=env_key,
                    created_at=datetime.now(timezone.utc)
                )
                self.keys[f"{key.agent_id}:{key.key_id}"] = key
    
    def get_key(self, agent_id: str, key_id: str) -> Optional[AgentKey]:
        """Get a specific key."""
        return self.keys.get(f"{agent_id}:{key_id}")
    
    def get_agent_keys(self, agent_id: str) -> list:
        """Get all keys for an agent."""
        return [k for k in self.keys.values() if k.agent_id == agent_id]
    
    def generate_key(self, agent_id: str) -> AgentKey:
        """Generate a new key for an agent."""
        key_id = f"{agent_id.lower()}-{secrets.token_hex(4)}"
        secret = secrets.token_hex(32)
        
        key = AgentKey(
            agent_id=agent_id,
            key_id=key_id,
            secret_key=secret,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=90)
        )
        
        self.keys[f"{agent_id}:{key_id}"] = key
        
        # Store in Neo4j if available
        if self.driver:
            with self.driver.session() as session:
                session.run("""
                    MATCH (a:Agent {name: $agent_id})
                    CREATE (ak:AgentKey {
                        agent_id: $agent_id,
                        key_id: $key_id,
                        secret_key: $secret_key,
                        created_at: $created_at,
                        expires_at: $expires_at,
                        revoked: false
                    })
                    CREATE (a)-[:HAS_KEY]->(ak)
                """, agent_id=agent_id, key_id=key_id,
                    secret_key=secret, created_at=key.created_at,
                    expires_at=key.expires_at)
        
        return key
```

---

#### P2-T8: Wire Signing into agent_spawner_direct.py

```yaml
Task ID: P2-T8
Priority: P2-HIGH
Owner: Temüjin (Developer)
Estimated Hours: 2
Dependencies: P2-T7
Files to Modify:
  - tools/kurultai/agent_spawner_direct.py
```

---

#### P2-T9: Add Signature Verification Middleware

```yaml
Task ID: P2-T9
Priority: P2-HIGH
Owner: Temüjin (Developer)
Estimated Hours: 2
Dependencies: P2-T8
Files to Create:
  - tools/kurultai/security/signature_middleware.py (new)
```

---

#### P2-T10: Create Message Signing Tests

```yaml
Task ID: P2-T10
Priority: P2-HIGH
Owner: Jochi (Analyst)
Estimated Hours: 1
Dependencies: P2-T9
Files to Create:
  - tests/kurultai/security/test_message_signing.py (new)
```

---

#### P2-T11: Create SUBSCRIBES_TO Schema Migration

```yaml
Task ID: P2-T11
Priority: P2-HIGH
Owner: Kublai (Orchestrator)
Estimated Hours: 1
Dependencies: None
Files to Create:
  - scripts/migrations/006_subscriptions.cypher (new)
```

**Cypher Migration:**
```cypher
/**
 * Migration 006: Cross-Agent Subscription System
 * Creates SUBSCRIBES_TO relationship for event notifications
 */

// Constraints for subscription relationships (using nodes for relationship properties)
CREATE CONSTRAINT subscription_id IF NOT EXISTS
FOR (s:Subscription) REQUIRE s.id IS UNIQUE;

// Indexes for efficient querying
CREATE INDEX subscription_topic IF NOT EXISTS
FOR (s:Subscription) ON (s.topic);

CREATE INDEX subscription_agent IF NOT EXISTS
FOR (s:Subscription) ON (s.subscriber_agent);

CREATE INDEX subscription_active IF NOT EXISTS
FOR (s:Subscription) ON (s.active);

// Notification node for queueing
CREATE CONSTRAINT notification_id IF NOT EXISTS
FOR (n:Notification) REQUIRE n.id IS UNIQUE;

CREATE INDEX notification_unread IF NOT EXISTS
FOR (n:Notification) ON (n.agent, n.read);

CREATE INDEX notification_created IF NOT EXISTS
FOR (n:Notification) ON (n.created_at);
```

---

#### P2-T12: Implement subscription_manager.py

```yaml
Task ID: P2-T12
Priority: P2-HIGH
Owner: Kublai (Orchestrator)
Estimated Hours: 3
Dependencies: P2-T11
Files to Create:
  - tools/kurultai/subscription_manager.py (new)
```

---

#### P2-T13: Implement notification_dispatcher.py

```yaml
Task ID: P2-T13
Priority: P2-HIGH
Owner: Kublai (Orchestrator)
Estimated Hours: 3
Dependencies: P2-T12
Files to Create:
  - tools/kurultai/notification_dispatcher.py (new)
```

---

#### P2-T14: Add Subscription API Endpoints

```yaml
Task ID: P2-T14
Priority: P2-HIGH
Owner: Kublai (Orchestrator)
Estimated Hours: 2
Dependencies: P2-T13
Files to Modify:
  - src/index.js (add subscription routes)
```

---

#### P2-T15: Create Subscription E2E Tests

```yaml
Task ID: P2-T15
Priority: P2-HIGH
Owner: Jochi (Analyst)
Estimated Hours: 2
Dependencies: P2-T14
Files to Create:
  - tests/integration/test_subscriptions.py (new)
```

---

### 4.3 Phase 3: Collaboration & Polish Tasks

#### P3-T1: Wire Reflection to Cron

```yaml
Task ID: P3-T1
Priority: P3-MEDIUM
Owner: Ögedei (Operations)
Estimated Hours: 1
Dependencies: None
Files to Modify:
  - tools/kurultai/heartbeat_master.py (add reflection trigger)
```

**Implementation:**
```python
# Add to heartbeat_master.py register_all_tasks method

def register_reflection_tasks(self):
    """Register weekly reflection trigger."""
    
    async def trigger_reflection(driver):
        """Trigger Kublai's proactive reflection."""
        import subprocess
        try:
            result = subprocess.run(
                ['node', '/app/src/kublai/trigger-reflection.js'],
                capture_output=True,
                text=True,
                timeout=300
            )
            return {
                'success': result.returncode == 0,
                'stdout': result.stdout,
                'stderr': result.stderr
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    self.register(HeartbeatTask(
        name='weekly_reflection',
        agent='Kublai',
        frequency_minutes=10080,  # Weekly (7 days)
        max_tokens=2000,
        handler=trigger_reflection,
        description='Trigger Kublai proactive reflection cycle'
    ))
```

---

#### P3-T2: Create trigger-reflection.js Script

```yaml
Task ID: P3-T2
Priority: P3-MEDIUM
Owner: Kublai (Orchestrator)
Estimated Hours: 2
Dependencies: P3-T1
Files to Create:
  - src/kublai/trigger-reflection.js (new)
```

---

#### P3-T3: Verify Weekly Cron Schedule

```yaml
Task ID: P3-T3
Priority: P3-MEDIUM
Owner: Ögedei (Operations)
Estimated Hours: 0.5
Dependencies: P3-T2
Files to Verify:
  - railway.toml (kublai-weekly-reflection schedule)
```

---

#### P3-T4: Create Reflection Schedule Tests

```yaml
Task ID: P3-T4
Priority: P3-MEDIUM
Owner: Jochi (Analyst)
Estimated Hours: 1
Dependencies: P3-T3
Files to Create:
  - tests/test_reflection_schedule.py (new)
```

---

#### P3-T5: Document Reflection Workflow

```yaml
Task ID: P3-T5
Priority: P3-MEDIUM
Owner: Chagatai (Writer)
Estimated Hours: 1
Dependencies: P3-T4
Files to Update:
  - docs/REFLECTION_WORKFLOW.md (new)
```

---

#### P3-T6: Implement Ögedei Vetting Handler

```yaml
Task ID: P3-T6
Priority: P3-MEDIUM
Owner: Ögedei (Operations)
Estimated Hours: 4
Dependencies: None
Files to Create:
  - tools/kurultai/vetting_handlers.py (new)
```

**Implementation:**
```python
#!/usr/bin/env python3
"""
Vetting Handlers for Architecture Proposals

Ögedei reviews proposals for operational feasibility.
Temüjin implements approved proposals.
"""

import logging
from typing import Dict, Optional, List
from datetime import datetime, timezone
from enum import Enum

logger = logging.getLogger(__name__)


class ProposalStatus(Enum):
    PROPOSED = "proposed"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    IMPLEMENTING = "implementing"
    VALIDATED = "validated"
    SYNCED = "synced"


class VettingResult:
    """Result of Ögedei's vetting process."""
    
    def __init__(self, approved: bool, reason: str, concerns: List[str] = None):
        self.approved = approved
        self.reason = reason
        self.concerns = concerns or []
        self.vetted_at = datetime.now(timezone.utc)


class OgedeiVettingHandler:
    """
    Ögedei's operational assessment of architecture proposals.
    
    Checks:
    - Operational complexity
    - Resource requirements
    - Risk assessment
    - Rollback feasibility
    """
    
    def __init__(self, neo4j_driver):
        self.driver = neo4j_driver
        
    def vet_proposal(self, proposal_id: str) -> VettingResult:
        """
        Vett a proposal for operational feasibility.
        
        Args:
            proposal_id: The proposal to vet
            
        Returns:
            VettingResult with approval decision
        """
        # Fetch proposal details
        proposal = self._get_proposal(proposal_id)
        if not proposal:
            return VettingResult(False, "Proposal not found")
        
        concerns = []
        
        # Check complexity
        complexity = proposal.get('complexity', 'medium')
        if complexity == 'high':
            concerns.append("High complexity requires extended maintenance window")
        
        # Check resource requirements
        resources = proposal.get('resource_estimate', {})
        estimated_hours = resources.get('hours', 0)
        if estimated_hours > 40:
            concerns.append(f"Large time investment ({estimated_hours}h) - consider breaking into phases")
        
        # Check risk level
        risk = proposal.get('risk_level', 'medium')
        if risk == 'high':
            concerns.append("High risk - requires rollback plan and staged rollout")
        
        # Check dependencies
        dependencies = proposal.get('dependencies', [])
        unmet_deps = self._check_dependencies(dependencies)
        if unmet_deps:
            concerns.append(f"Unmet dependencies: {', '.join(unmet_deps)}")
        
        # Make decision
        if len(concerns) > 3 or risk == 'high' and complexity == 'high':
            return VettingResult(
                approved=False,
                reason="Too many concerns or excessive risk",
                concerns=concerns
            )
        
        if concerns:
            return VettingResult(
                approved=True,
                reason="Approved with concerns noted",
                concerns=concerns
            )
        
        return VettingResult(
            approved=True,
            reason="No operational concerns"
        )
    
    def _get_proposal(self, proposal_id: str) -> Optional[Dict]:
        """Fetch proposal from Neo4j."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (p:ArchitectureProposal {id: $proposal_id})
                RETURN p
            """, proposal_id=proposal_id)
            record = result.single()
            if record:
                return dict(record['p'])
            return None
    
    def _check_dependencies(self, dependencies: List[str]) -> List[str]:
        """Check which dependencies are not met."""
        unmet = []
        for dep in dependencies:
            # Check if dependency exists as completed implementation
            with self.driver.session() as session:
                result = session.run("""
                    MATCH (i:Implementation {name: $dep})
                    WHERE i.status = 'completed'
                    RETURN count(i) as count
                """, dep=dep)
                if result.single()['count'] == 0:
                    unmet.append(dep)
        return unmet
    
    def record_vetting(self, proposal_id: str, result: VettingResult):
        """Record vetting result in Neo4j."""
        with self.driver.session() as session:
            session.run("""
                MATCH (p:ArchitectureProposal {id: $proposal_id})
                CREATE (v:Vetting {
                    id: randomUUID(),
                    approved: $approved,
                    reason: $reason,
                    concerns: $concerns,
                    vetted_at: $vetted_at,
                    vetted_by: 'Ögedei'
                })
                CREATE (p)-[:HAS_VETTING]->(v)
                SET p.status = CASE 
                    WHEN $approved THEN 'approved'
                    ELSE 'rejected'
                END
            """, 
                proposal_id=proposal_id,
                approved=result.approved,
                reason=result.reason,
                concerns=result.concerns,
                vetted_at=result.vetted_at
            )
            
            action = "approved" if result.approved else "rejected"
            logger.info(f"Proposal {proposal_id} {action} by Ögedei")


class TemujinImplementationHandler:
    """
    Temüjin's implementation handler for approved proposals.
    """
    
    def __init__(self, neo4j_driver):
        self.driver = neo4j_driver
    
    def start_implementation(self, proposal_id: str) -> Dict:
        """Begin implementing an approved proposal."""
        with self.driver.session() as session:
            # Verify proposal is approved
            result = session.run("""
                MATCH (p:ArchitectureProposal {id: $proposal_id})
                RETURN p.status as status
            """, proposal_id=proposal_id)
            record = result.single()
            
            if not record or record['status'] != 'approved':
                return {'success': False, 'error': 'Proposal not approved'}
            
            # Create implementation record
            impl_id = f"impl-{proposal_id}"
            session.run("""
                MATCH (p:ArchitectureProposal {id: $proposal_id})
                CREATE (i:Implementation {
                    id: $impl_id,
                    proposal_id: $proposal_id,
                    status: 'in_progress',
                    started_at: $now,
                    started_by: 'Temüjin',
                    progress: 0
                })
                CREATE (p)-[:IMPLEMENTED_BY]->(i)
                SET p.status = 'implementing'
            """, proposal_id=proposal_id, impl_id=impl_id, now=datetime.now(timezone.utc))
            
            logger.info(f"Started implementation for proposal {proposal_id}")
            
            return {
                'success': True,
                'implementation_id': impl_id,
                'message': 'Implementation started'
            }
    
    def update_progress(self, implementation_id: str, progress: int, notes: str = None):
        """Update implementation progress."""
        with self.driver.session() as session:
            session.run("""
                MATCH (i:Implementation {id: $impl_id})
                SET i.progress = $progress,
                    i.updated_at = $now
                FOREACH (n IN CASE WHEN $notes IS NOT NULL THEN [1] ELSE [] END |
                    SET i.notes = $notes
                )
            """, impl_id=implementation_id, progress=progress, 
                notes=notes, now=datetime.now(timezone.utc))
            
            if progress >= 100:
                self._complete_implementation(implementation_id)
    
    def _complete_implementation(self, implementation_id: str):
        """Mark implementation as complete and trigger validation."""
        with self.driver.session() as session:
            session.run("""
                MATCH (i:Implementation {id: $impl_id})
                SET i.status = 'completed',
                    i.completed_at = $now
                WITH i
                MATCH (p:ArchitectureProposal)-[:IMPLEMENTED_BY]->(i)
                SET p.status = 'validated'
                CREATE (v:Validation {
                    id: randomUUID(),
                    implementation_id: $impl_id,
                    validated_at: $now,
                    auto_triggered: true
                })
                CREATE (i)-[:VALIDATED_BY]->(v)
            """, impl_id=implementation_id, now=datetime.now(timezone.utc))
            
            logger.info(f"Implementation {implementation_id} completed")
```

---

#### P3-T7: Implement Temüjin Implementation Handler

```yaml
Task ID: P3-T7
Priority: P3-MEDIUM
Owner: Temüjin (Developer)
Estimated Hours: 2
Dependencies: P3-T6
Files to Modify:
  - tools/kurultai/vetting_handlers.py (add implementation handler)
```

---

#### P3-T8: Wire Handlers to Delegation Protocol

```yaml
Task ID: P3-T8
Priority: P3-MEDIUM
Owner: Kublai (Orchestrator)
Estimated Hours: 2
Dependencies: P3-T7
Files to Modify:
  - src/kublai/delegation-protocol.js (wire handlers)
```

---

#### P3-T9: Create Vetting Handler Tests

```yaml
Task ID: P3-T9
Priority: P3-MEDIUM
Owner: Jochi (Analyst)
Estimated Hours: 2
Dependencies: P3-T8
Files to Create:
  - tests/test_vetting_handlers.py (new)
```

---

#### P3-T10: Document Vetting Workflow

```yaml
Task ID: P3-T10
Priority: P3-MEDIUM
Owner: Chagatai (Writer)
Estimated Hours: 1
Dependencies: P3-T9
Files to Update:
  - docs/VETTING_WORKFLOW.md (new)
```

---

#### P3-T11: Implement Collaboration Protocol

```yaml
Task ID: P3-T11
Priority: P3-MEDIUM
Owner: Temüjin (Developer)
Estimated Hours: 6
Dependencies: None
Files to Create:
  - tools/kurultai/collaboration_protocol.py (new)
```

---

#### P3-T12: Automate Backend Issue Detection

```yaml
Task ID: P3-T12
Priority: P3-MEDIUM
Owner: Jochi (Analyst)
Estimated Hours: 3
Dependencies: P3-T11
Files to Create:
  - tools/kurultai/backend_detection.py (new)
```

---

#### P3-T13: Implement Auto-Fix Validation

```yaml
Task ID: P3-T13
Priority: P3-MEDIUM
Owner: Jochi (Analyst)
Estimated Hours: 2
Dependencies: P3-T12
Files to Create:
  - tools/kurultai/auto_fix_validation.py (new)
```

---

#### P3-T14: Create Collaboration E2E Tests

```yaml
Task ID: P3-T14
Priority: P3-MEDIUM
Owner: Jochi (Analyst)
Estimated Hours: 2
Dependencies: P3-T13
Files to Create:
  - tests/integration/test_collaboration.py (new)
```

---

### 4.4 Phase 3: Remaining Items (P4-P5)

#### P4-T1: Implement Meta-Learning Engine

```yaml
Task ID: P4-T1
Priority: P4-LOW
Owner: Kublai (Orchestrator) + Chagatai (Writer)
Estimated Hours: 10
Dependencies: None
Files to Create:
  - tools/kurultai/meta_learning_engine.py (new)
```

**Implementation Sketch:**
```python
#!/usr/bin/env python3
"""
Meta-Learning Engine

Converts reflections into MetaRules for SOUL.md injection.
Implements reflection pattern clustering and rule generation.
"""

import logging
from typing import List, Dict
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class ReflectionPattern:
    """Clustered reflection pattern."""
    pattern_id: str
    theme: str
    frequency: int
    average_confidence: float
    source_reflections: List[str]
    suggested_rule: str


class MetaLearningEngine:
    """
    Learns from reflections and generates MetaRules.
    
    Workflow:
    1. Cluster reflections by semantic similarity
    2. Identify recurring patterns
    3. Generate MetaRules from patterns
    4. Queue rules for SOUL.md injection
    """
    
    def __init__(self, neo4j_driver, embedding_model=None):
        self.driver = neo4j_driver
        self.embedding_model = embedding_model
        
    def cluster_reflections(self, days: int = 30) -> List[ReflectionPattern]:
        """
        Cluster recent reflections by semantic similarity.
        
        Args:
            days: Look back period
            
        Returns:
            List of identified patterns
        """
        with self.driver.session() as session:
            # Get unclustered reflections with embeddings
            result = session.run("""
                MATCH (r:Reflection)
                WHERE r.created_at > datetime() - duration('P' + $days + 'D')
                AND r.clustered = false
                RETURN r.id as id, r.embedding as embedding, 
                       r.theme as theme, r.insights as insights
            """, days=days)
            
            reflections = []
            for record in result:
                reflections.append({
                    'id': record['id'],
                    'embedding': record['embedding'],
                    'theme': record['theme'],
                    'insights': record['insights']
                })
            
            # Simple clustering by theme (in production, use HDBSCAN)
            patterns = self._cluster_by_theme(reflections)
            
            return patterns
    
    def _cluster_by_theme(self, reflections: List[Dict]) -> List[ReflectionPattern]:
        """Cluster reflections by theme."""
        from collections import defaultdict
        
        theme_groups = defaultdict(list)
        for r in reflections:
            theme = r.get('theme', 'general')
            theme_groups[theme].append(r)
        
        patterns = []
        for theme, group in theme_groups.items():
            if len(group) >= 3:  # Minimum cluster size
                # Generate suggested rule
                suggested_rule = self._generate_rule(theme, group)
                
                pattern = ReflectionPattern(
                    pattern_id=f"pattern-{theme}-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
                    theme=theme,
                    frequency=len(group),
                    average_confidence=sum(r.get('confidence', 0.5) for r in group) / len(group),
                    source_reflections=[r['id'] for r in group],
                    suggested_rule=suggested_rule
                )
                patterns.append(pattern)
        
        return patterns
    
    def _generate_rule(self, theme: str, reflections: List[Dict]) -> str:
        """Generate a MetaRule from reflection cluster."""
        insights = [r.get('insights', '') for r in reflections]
        
        # Simple rule generation (in production, use LLM)
        if theme == 'communication':
            return f"When collaborating with other agents, {insights[0][:100]}"
        elif theme == 'error_handling':
            return f"For error recovery, prioritize {insights[0][:100]}"
        else:
            return f"General principle: {insights[0][:100] if insights else 'Learn from past experiences'}"
    
    def generate_metarules(self, patterns: List[ReflectionPattern]) -> List[Dict]:
        """Convert patterns to MetaRules."""
        metarules = []
        
        for pattern in patterns:
            # Determine rule type based on confidence
            if pattern.average_confidence > 0.8:
                rule_type = 'absolute'
            elif pattern.average_confidence > 0.5:
                rule_type = 'guideline'
            else:
                rule_type = 'conditional'
            
            metarule = {
                'id': f"metarule-{pattern.pattern_id}",
                'rule_content': pattern.suggested_rule,
                'rule_type': rule_type,
                'source_pattern': pattern.pattern_id,
                'source_reflections': pattern.source_reflections,
                'frequency': pattern.frequency,
                'confidence': pattern.average_confidence,
                'created_at': datetime.now(timezone.utc)
            }
            metarules.append(metarule)
        
        return metarules
    
    def store_metarules(self, metarules: List[Dict]):
        """Store generated MetaRules in Neo4j."""
        with self.driver.session() as session:
            for rule in metarules:
                session.run("""
                    CREATE (m:MetaRule {
                        id: $id,
                        rule_content: $rule_content,
                        rule_type: $rule_type,
                        source_pattern: $source_pattern,
                        source_reflections: $source_reflections,
                        frequency: $frequency,
                        confidence: $confidence,
                        created_at: $created_at,
                        approved: false
                    })
                """, **rule)
                
                logger.info(f"Created MetaRule: {rule['id']}")
    
    def process_reflections(self, days: int = 30) -> Dict:
        """Main entry point: cluster reflections and generate rules."""
        patterns = self.cluster_reflections(days)
        metarules = self.generate_metarules(patterns)
        self.store_metarules(metarules)
        
        return {
            'patterns_found': len(patterns),
            'metarules_generated': len(metarules),
            'patterns': [{'theme': p.theme, 'frequency': p.frequency} for p in patterns]
        }
```

---

#### P4-T2: Implement ARCHITECTURE.md Bidirectional Sync

```yaml
Task ID: P4-T2
Priority: P4-LOW
Owner: Chagatai (Writer)
Estimated Hours: 6
Dependencies: None
Files to Create:
  - tools/kurultai/architecture_sync.py (new)
```

---

#### P5-T1: Create Kaizen Quality Tracking Dashboard

```yaml
Task ID: P5-T1
Priority: P5-LOW
Owner: Chagatai (Writer)
Estimated Hours: 6
Dependencies: None
Files to Create:
  - src/dashboard/kaizen.js (new)
  - src/dashboard/views/kaizen.html (new)
```

---

#### P5-T2: Verify Signal Alerting Integration

```yaml
Task ID: P5-T2
Priority: P5-LOW
Owner: Ögedei (Operations)
Estimated Hours: 2
Dependencies: None
Files to Create:
  - tests/integration/test_signal_alerting.py (new)
```

---

## 5. Resource Calendar

### 5.1 Week-by-Week Agent Allocation

```
WEEK 1: CRITICAL INFRASTRUCTURE
═══════════════════════════════════════════════════════════════
Day 1-2: P1-T1 to P1-T3 (Temüjin - 6h)
         └── Parallel: P1-T3 Vector Indexes (Temüjin - 1h)

Day 3-4: P1-T4 to P1-T6 (Temüjin - 4h)
         └── Integration testing

Day 5:   P1-T7 (Jochi - 2h)
         └── Phase 1 exit gate

WEEK 2: SECURITY & CORE FEATURES
═══════════════════════════════════════════════════════════════
Day 6-7: P2-T1 to P2-T5 (Temüjin - 6h)
         └── Vector indexes complete

Day 8:   P2-T6 to P2-T10 (Temüjin - 8h)
         └── HMAC signing integration

Day 9-10: P2-T11 to P2-T15 (Kublai - 10h + Jochi - 2h)
          └── Cross-agent subscriptions

WEEK 3: COLLABORATION & POLISH
═══════════════════════════════════════════════════════════════
Day 11:   P3-T1 to P3-T5 (Ögedei - 4h + Chagatai - 1h)
          └── Scheduled reflection

Day 12-13: P3-T6 to P3-T10 (Ögedei - 6h + Temüjin - 2h + Chagatai - 1h)
           └── Vetting handlers

Day 14-15: P4-T1 to P5-T2 (All agents - 20h parallel)
           └── Remaining items
```

### 5.2 Parallel Workstreams Diagram

```
Time →    Week 1              Week 2              Week 3
          ┌─────────┐        ┌─────────┐        ┌─────────┐
Temüjin   │ P1 CRIT │────────│ P2 HIGH │────────│ P3-P5   │
(54h)     │         │        │         │        │         │
          └─────────┘        └─────────┘        └─────────┘

          ┌──────────────────┬─────────┐
Kublai    │  (available for  │ P2 HIGH │────────│ P3-P5   │
(24h)     │   consultation)  │         │        │         │
          └──────────────────┴─────────┘        └─────────┘

          ┌──────────────────────────┐
Jochi     │  (P1-T7 testing only)    │────────│ P2-P5   │
(16h)     │                          │        │ testing │
          └──────────────────────────┘        └─────────┘

          ┌──────────────────────────────────────────────┐
Chagatai  │  (documentation & meta-learning)             │
(16h)     │                                              │
          └──────────────────────────────────────────────┘

          ┌──────────────────┬──────────────────────────┐
Ögedei    │  (monitoring)    │ P3 (vetting & cron)      │
(12h)     │                  │                          │
          └──────────────────┴──────────────────────────┘
```

### 5.3 Critical Path Highlighting

```
CRITICAL PATH (Must Complete in Sequence):
═══════════════════════════════════════════════════════════════

P1-T1 ──→ P1-T4 ──→ P1-T5 ──→ P2-T1 ──→ P2-T6 ──→ P3-T1 ──→ P3-T6
(Create  (Modify   (Add     (Vector  (HMAC    (Wire    (Vetting
 sidecar) entry)   func HB) indexes) signing) cron)    handlers)
   │        │         │        │        │        │        │
   ▼        ▼         ▼        ▼        ▼        ▼        ▼
  Day1    Day3      Day5     Day7     Day8    Day11    Day13


PARALLEL WORKSTREAMS:
═══════════════════════════════════════════════════════════════

P1-T3 ──→ P2-T1 ──→ P2-T2 ──→ P2-T5
(Vector  (Migration (Register (Verify
 indexes) creation) migration) queries)

P2-T7 ──→ P2-T8 ──→ P2-T10
(Message (Wire to   (Tests
 Signer)  spawner)

P2-T11 ──→ P2-T12 ──→ P2-T15
(Schema   (Manager  (E2E
 create)   impl)     tests)

P3-T11 ──→ P3-T14
(Collab   (Tests
 protocol)
```

### 5.4 Buffer Management

| Phase | Estimated Hours | Buffer (20%) | Total Allocated | Contingency |
|-------|-----------------|--------------|-----------------|-------------|
| Week 1 | 6h | 1.2h | 7.2h | Can absorb 1 day delay |
| Week 2 | 52h | 10.4h | 62.4h | Parallel workstreams |
| Week 3 | 52h | 10.4h | 62.4h | Can defer P4-P5 items |
| **Total** | **110h** | **22h** | **132h** | **3 days buffer** |

---

## 6. Risk Register

### 6.1 Technical Risks

| ID | Risk | Probability | Impact | Mitigation | Owner |
|----|------|-------------|--------|------------|-------|
| T1 | Heartbeat sidecar fails to start on container launch | Low | Critical | Graceful fallback to in-process writes; add health checks | Temüjin |
| T2 | Neo4j vector index creation fails (version incompatibility) | Low | High | Check Neo4j version before migration; fallback to regular indexes | Temüjin |
| T3 | HMAC key rotation causes signature failures | Medium | Medium | Implement key versioning; support graceful rotation period | Temüjin |
| T4 | Subscription notifications cause message storm | Medium | High | Rate limiting; batch notifications; circuit breaker | Kublai |
| T5 | Circuit breaker in heartbeat prevents recovery detection | Low | Critical | Separate recovery detection from heartbeat writes | Ögedei |

### 6.2 Schedule Risks

| ID | Risk | Probability | Impact | Mitigation | Owner |
|----|------|-------------|--------|------------|-------|
| S1 | P1 tasks take longer than estimated | Medium | Critical | Parallel P1-T3 with T1; defer P2 work if needed | Kublai |
| S2 | Vector indexes require Neo4j upgrade | Low | High | Pre-check Neo4j version; schedule upgrade if needed | Ögedei |
| S3 | Agent availability varies (vacation/illness) | Medium | Medium | Cross-train on critical tasks; document handoff procedures | Kublai |
| S4 | Integration testing reveals additional gaps | Medium | Medium | Weekly demos; continuous integration testing | Jochi |

### 6.3 Mitigation Strategies

**Risk T1: Heartbeat Sidecar Failure**
```python
# Fallback to in-process writes if sidecar fails
class HeartbeatFallback:
    def write_heartbeat(self, agent_name: str):
        try:
            # Try sidecar first (via shared state or IPC)
            if self.sidecar_healthy():
                return
        except:
            pass
        
        # Fallback: write directly
        self._write_direct(agent_name)
```

**Risk T3: HMAC Key Rotation**
```python
# Support multiple key versions during rotation
class KeyStore:
    def get_valid_keys(self, agent_id: str) -> List[AgentKey]:
        """Get all non-expired keys for verification."""
        keys = self.get_agent_keys(agent_id)
        now = datetime.now(timezone.utc)
        return [k for k in keys 
                if not k.revoked 
                and (not k.expires_at or k.expires_at > now)]
```

**Risk T4: Notification Storm**
```python
# Rate limiting for notifications
class NotificationDispatcher:
    def __init__(self):
        self.rate_limiter = RateLimiter(
            max_requests=100,
            window_seconds=60
        )
    
    async def dispatch(self, notification):
        if not self.rate_limiter.allow(notification.agent):
            logger.warning(f"Rate limit hit for {notification.agent}")
            # Queue for later or batch
            self.batch_queue.append(notification)
            return
        
        await self._send(notification)
```

---

## 7. Verification Checklist

### 7.1 Per-Gap Verification

#### P1: Heartbeat Write Side
- [ ] `scripts/heartbeat_writer.py` exists and runs
- [ ] `entrypoint.sh` launches sidecar on startup
- [ ] `infra_heartbeat` written every 30 seconds for all 6 agents
- [ ] `claim_task()` updates `last_heartbeat`
- [ ] `complete_task()` updates `last_heartbeat`
- [ ] Failover detection works (90s functional, 120s infra thresholds)
- [ ] Circuit breaker triggers after 3 failures
- [ ] All integration tests pass

**Verification Command:**
```bash
# After deployment
python scripts/verify_heartbeat.py
# Expected output:
# ✅ All 6 agents have infra_heartbeat within last 60s
# ✅ All 6 agents have last_heartbeat within last 60s
# ✅ Failover detection operational
```

#### P2: Vector Indexes
- [ ] `belief_embedding` index exists and queryable
- [ ] `memory_entry_embedding` index exists and queryable
- [ ] `task_embedding` index exists (future use)
- [ ] Semantic search returns relevant results
- [ ] Migration v4 registered and runs successfully

**Verification Command:**
```bash
python scripts/verify_vector_indexes.py
# Expected output:
# ✅ belief_embedding: 384 dims, cosine similarity
# ✅ memory_entry_embedding: 384 dims, cosine similarity
# ✅ Semantic search returns results in <100ms
```

#### P2: HMAC-SHA256 Signing
- [ ] `MessageSigner` class implemented
- [ ] `MessageVerifier` class implemented
- [ ] `KeyStore` manages agent keys
- [ ] Inter-agent messages include signatures
- [ ] Tampered messages are rejected
- [ ] Clock skew tolerance (5 minutes) enforced

**Verification Command:**
```bash
python -m pytest tests/kurultai/security/test_message_signing.py -v
# Expected: 5 passed
```

#### P2: Cross-Agent Subscriptions
- [ ] `006_subscriptions.cypher` migration applied
- [ ] `subscription_manager.py` implemented
- [ ] `notification_dispatcher.py` implemented
- [ ] Agents can subscribe to topics
- [ ] Published events reach all subscribers
- [ ] Subscription API endpoints functional

**Verification Command:**
```bash
python -m pytest tests/integration/test_subscriptions.py -v
# Expected: Subscribe → Publish → Receive flow passes
```

#### P3: Scheduled Reflection
- [ ] Weekly cron configured in `railway.toml`
- [ ] Reflection triggers automatically
- [ ] Opportunities stored in Neo4j
- [ ] No manual intervention required

#### P3: Vetting Handlers
- [ ] `vetting_handlers.py` implemented
- [ ] Ögedei handler validates proposals
- [ ] Temüjin handler implements approved proposals
- [ ] State machine transitions work end-to-end
- [ ] Proposal workflow completes: proposed → approved → implemented → validated → synced

#### P3: Collaboration Protocol
- [ ] Jochi-Temüjin handoff workflow automated
- [ ] Backend issue detection triggers automatically
- [ ] Auto-fixes validated before marking complete
- [ ] E2E collaboration tests pass

#### P4-P5: Polish Items
- [ ] Meta-learning engine generates MetaRules from reflections
- [ ] ARCHITECTURE.md bidirectional sync works
- [ ] Kaizen dashboard displays improvement metrics
- [ ] Signal alerting verified in production

### 7.2 Integration Test Plan

```python
# tests/integration/test_gap_closure.py

class TestGapClosure:
    """Verify all P1-P5 gaps are closed."""
    
    def test_p1_heartbeat_system(self, neo4j_driver):
        """P1: Heartbeat write side operational."""
        # Wait for at least one heartbeat cycle
        time.sleep(35)
        
        with neo4j_driver.session() as session:
            result = session.run("""
                MATCH (a:Agent)
                RETURN a.name as name, 
                       a.infra_heartbeat as infra,
                       a.last_heartbeat as functional
            """)
            
            for record in result:
                name = record['name']
                infra = record['infra']
                functional = record['functional']
                
                assert infra is not None, f"{name}: Missing infra_heartbeat"
                assert functional is not None, f"{name}: Missing last_heartbeat"
                
                # Verify timestamps are recent
                infra_time = datetime.fromisoformat(infra)
                functional_time = datetime.fromisoformat(functional)
                now = datetime.now(timezone.utc)
                
                assert (now - infra_time).seconds < 60, f"{name}: Stale infra_heartbeat"
                assert (now - functional_time).seconds < 60, f"{name}: Stale functional_heartbeat"
    
    def test_p2_vector_indexes(self, neo4j_driver):
        """P2: Vector indexes created and queryable."""
        with neo4j_driver.session() as session:
            result = session.run("""
                SHOW INDEXES YIELD name, type
                WHERE type = 'VECTOR'
                RETURN collect(name) as vector_indexes
            """)
            
            indexes = result.single()['vector_indexes']
            assert 'belief_embedding' in indexes
            assert 'memory_entry_embedding' in indexes
    
    def test_p2_hmac_signing(self, neo4j_driver):
        """P2: HMAC signing operational."""
        from tools.kurultai.security.message_signer import MessageSigner, MessageVerifier, KeyStore
        
        # Create test key
        keystore = KeyStore(neo4j_driver)
        key = keystore.generate_key('TestAgent')
        
        # Sign message
        signer = MessageSigner(key)
        message = {'type': 'test', 'data': 'hello'}
        signed = signer.sign_message(message)
        
        # Verify message
        verifier = MessageVerifier(keystore)
        is_valid, error = verifier.verify_message(signed)
        
        assert is_valid, f"Signature verification failed: {error}"
    
    def test_p3_vetting_workflow(self, neo4j_driver):
        """P3: Vetting handlers operational."""
        from tools.kurultai.vetting_handlers import OgedeiVettingHandler
        
        # Create test proposal
        with neo4j_driver.session() as session:
            session.run("""
                CREATE (p:ArchitectureProposal {
                    id: 'test-proposal-001',
                    title: 'Test Proposal',
                    status: 'proposed',
                    complexity: 'low',
                    risk_level: 'low'
                })
            """)
        
        # Vet proposal
        handler = OgedeiVettingHandler(neo4j_driver)
        result = handler.vet_proposal('test-proposal-001')
        
        assert result.approved, f"Proposal should be approved: {result.reason}"
        
        # Verify state change
        with neo4j_driver.session() as session:
            result = session.run("""
                MATCH (p:ArchitectureProposal {id: 'test-proposal-001'})
                RETURN p.status as status
            """)
            status = result.single()['status']
            assert status == 'approved', f"Expected 'approved', got '{status}'"

    def test_all_gaps_closed(self, neo4j_driver):
        """Final validation: All gaps closed."""
        # This test runs all above tests and reports
        results = {
            'p1_heartbeat': self.test_p1_heartbeat_system(neo4j_driver),
            'p2_vector_indexes': self.test_p2_vector_indexes(neo4j_driver),
            'p2_hmac': self.test_p2_hmac_signing(neo4j_driver),
            'p3_vetting': self.test_p3_vetting_workflow(neo4j_driver),
        }
        
        failed = [k for k, v in results.items() if not v]
        assert not failed, f"Failed gaps: {failed}"
```

### 7.3 Final Validation Criteria

**Production Readiness Checklist:**

| # | Criteria | Verification Method | Owner |
|---|----------|---------------------|-------|
| 1 | All P1 gaps closed | `verify_gaps_closed.py --priority P1` | Jochi |
| 2 | All P2 gaps closed | `verify_gaps_closed.py --priority P2` | Jochi |
| 3 | All integration tests pass | `pytest tests/integration/ -v` | Jochi |
| 4 | Security audit passes | `scripts/security_audit.py` | Temüjin |
| 5 | Performance benchmarks met | `scripts/run_benchmarks.py` | Jochi |
| 6 | Documentation complete | Review docs/ directory | Chagatai |
| 7 | Deployment checklist complete | `scripts/pre_flight_check.py` | Ögedei |
| 8 | Overall completion ≥95% | Gap analysis report | Kublai |

**Exit Criteria for Each Phase:**

**Phase 1 Exit Gate (Week 1):**
- [ ] `heartbeat_writer.py` running in production
- [ ] All 6 agents show fresh timestamps in Neo4j
- [ ] Failover detection works end-to-end
- [ ] All P1 tests pass

**Phase 2 Exit Gate (Week 2):**
- [ ] All vector indexes created and queryable
- [ ] Inter-agent messages are HMAC-signed
- [ ] Subscriptions work across agents
- [ ] Security audit passes
- [ ] All P2 tests pass

**Phase 3 Exit Gate (Week 3):**
- [ ] Reflection runs automatically weekly
- [ ] Vetting handlers process proposals
- [ ] Jochi-Temüjin collaboration automated
- [ ] Overall completion: 95%+
- [ ] All integration tests pass

---

## Appendix A: File Inventory

### Files to Create (25 new files)

| File | Task | Description |
|------|------|-------------|
| `scripts/heartbeat_writer.py` | P1-T1 | Sidecar script for infra heartbeat |
| `tests/test_heartbeat_writer.py` | P1-T2 | Unit tests for heartbeat writer |
| `scripts/migrations/005_vector_indexes.cypher` | P1-T3 | Vector index migration |
| `tests/integration/test_heartbeat_integration.py` | P1-T7 | Heartbeat integration tests |
| `migrations/v4_vector_indexes.py` | P2-T1 | Python migration class |
| `tests/test_vector_indexes.py` | P2-T4 | Vector index tests |
| `scripts/verify_vector_search.py` | P2-T5 | Semantic search verification |
| `tools/kurultai/security/message_signer.py` | P2-T7 | HMAC signing implementation |
| `tools/kurultai/security/signature_middleware.py` | P2-T9 | Signature verification middleware |
| `tests/kurultai/security/test_message_signing.py` | P2-T10 | Message signing tests |
| `scripts/migrations/006_subscriptions.cypher` | P2-T11 | Subscription schema migration |
| `tools/kurultai/subscription_manager.py` | P2-T12 | Subscription CRUD operations |
| `tools/kurultai/notification_dispatcher.py` | P2-T13 | Notification dispatch |
| `tests/integration/test_subscriptions.py` | P2-T15 | Subscription E2E tests |
| `src/kublai/trigger-reflection.js` | P3-T2 | Reflection trigger script |
| `tests/test_reflection_schedule.py` | P3-T4 | Reflection schedule tests |
| `docs/REFLECTION_WORKFLOW.md` | P3-T5 | Reflection documentation |
| `tools/kurultai/vetting_handlers.py` | P3-T6 | Ögedei and Temüjin handlers |
| `tests/test_vetting_handlers.py` | P3-T9 | Vetting handler tests |
| `docs/VETTING_WORKFLOW.md` | P3-T10 | Vetting documentation |
| `tools/kurultai/collaboration_protocol.py` | P3-T11 | Jochi-Temüjin collaboration |
| `tools/kurultai/backend_detection.py` | P3-T12 | Backend issue detection |
| `tools/kurultai/auto_fix_validation.py` | P3-T13 | Auto-fix validation |
| `tests/integration/test_collaboration.py` | P3-T14 | Collaboration E2E tests |
| `tools/kurultai/meta_learning_engine.py` | P4-T1 | Meta-learning engine |

### Files to Modify (8 files)

| File | Task | Description |
|------|------|-------------|
| `moltbot-railway-template/entrypoint.sh` | P1-T4 | Add sidecar launch |
| `openclaw_memory.py` | P1-T5, P1-T6 | Verify heartbeat updates |
| `scripts/run_migrations.py` | P2-T2 | Register v4 migration |
| `tools/kurultai/agent_spawner_direct.py` | P2-T8 | Wire HMAC signing |
| `src/index.js` | P2-T14 | Add subscription API routes |
| `tools/kurultai/heartbeat_master.py` | P3-T1 | Add reflection trigger |
| `src/kublai/delegation-protocol.js` | P3-T8 | Wire vetting handlers |
| `railway.toml` | P3-T3 | Verify cron schedule |

---

## Appendix B: Horde-Plan Pattern Application

### Swarm Planning Applied

The plan breaks work into parallel workstreams:
1. **Infrastructure Swarm** (Temüjin) - P1 critical path
2. **Security Swarm** (Temüjin + Kublai) - P2 parallel tracks
3. **Collaboration Swarm** (Ögedei + Chagatai) - P3 protocols
4. **Testing Swarm** (Jochi) - Cross-cutting verification

### Dependency Mapping Applied

Every task includes explicit dependencies:
- `P1-T1 → P1-T4` (writer must exist before entrypoint integration)
- `P2-T7 → P2-T8` (signer must exist before wiring)
- `P2-T11 → P2-T12` (schema before manager)

Visualized in Section 5.3 Critical Path.

### Critical Path Analysis Applied

The critical path is P1-T1 through P1-T7 (Week 1). Any delay here delays the entire project. P2 and P3 work can parallelize after P1-T3.

### Buffer Management Applied

20% buffer added to all estimates:
- Week 1: 6h → 7.2h
- Week 2: 52h → 62.4h
- Week 3: 52h → 62.4h
- Total: 110h → 132h (3 days buffer)

### Quality Gates Applied

Each phase has exit criteria:
- Phase 1: Heartbeat operational, all tests pass
- Phase 2: Security audit passes, indexes queryable
- Phase 3: 95%+ completion, all integration tests pass

---

## Document Control

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-09 | Temüjin | Initial detailed implementation plan |

**Approvals Required:**
- [ ] Kublai (Architecture alignment)
- [ ] Temüjin (Technical feasibility)
- [ ] Jochi (Quality assurance)
- [ ] Ögedei (Operations readiness)

---

*"The shell may have cracks, but we will mend them."*
*— The Kurultai*
