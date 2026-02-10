# Kurultai v0.3: Agent Protocols, Memory Curation & Advanced Features

**Status**: Draft
**Version**: 1.0 (2026-02-06)
**Scope**: Memory curation engine, inter-agent collaboration protocols, autonomous agent behaviors, self-improvement integration, and delegation middleware. Builds on operational v0.2 deployment.
**Design Reference**: `docs/plans/jochi-memory-curation-design.md`

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Prerequisites](#prerequisites)
3. [Phase 0: Schema Extensions & Migration v4](#phase-0-schema-extensions--migration-v4)
4. [Phase 1: Jochi Memory Curation Engine](#phase-1-jochi-memory-curation-engine)
5. [Phase 2: Delegation Protocol (HMAC-SHA256)](#phase-2-delegation-protocol-hmac-sha256)
6. [Phase 3: Jochi-Temujin Collaboration Protocol](#phase-3-jochi-temujin-collaboration-protocol)
7. [Phase 4: Agent Autonomous Behaviors](#phase-4-agent-autonomous-behaviors)
8. [Phase 5: Self-Improvement & Kaizen Integration](#phase-5-self-improvement--kaizen-integration)
9. [Phase 6: MVS Scoring Engine](#phase-6-mvs-scoring-engine)
10. [Phase 7: Vector Deduplication](#phase-7-vector-deduplication)
11. [Phase 8: Testing & Validation](#phase-8-testing--validation)
12. [Appendices](#appendices)
    - [Appendix A: Scope Boundary Declaration](#appendix-a-scope-boundary-declaration)
    - [Appendix B: TTL Rules Reference](#appendix-b-ttl-rules-reference)
    - [Appendix C: MVS Formula Reference](#appendix-c-mvs-formula-reference)
    - [Appendix D: Never-Prune Safety Rails](#appendix-d-never-prune-safety-rails)

---

## Executive Summary

Kurultai v0.3 builds on the operational v0.2 deployment (Neo4j, Railway, Signal, Authentik, capability acquisition) to add **active memory management** and **autonomous agent behaviors**. The centerpiece is the Jochi Memory Curation Engine — a continuous heartbeat-driven system that keeps the Neo4j database optimized as 6 agents create entries.

### What's New in v0.3

| Feature | Description | Phase |
|---------|-------------|-------|
| **Jochi Memory Curation** | Continuous TTL-based pruning, tier management, token budget enforcement | Phase 1 |
| **HMAC-SHA256 Delegation** | Signed inter-agent message verification middleware | Phase 2 |
| **Jochi-Temujin Collaboration** | Analyst identifies issues, developer fixes them | Phase 3 |
| **Jochi Backend Issue Detection** | Automated backend code review and issue labeling | Phase 4.1 |
| **Ogedei Proactive Improvement** | Continuous operational reflection and improvement proposals | Phase 4.2 |
| **Chagatai Background Synthesis** | Idle-time knowledge consolidation and content generation | Phase 4.3 |
| **Self-Improvement/Kaizen** | Meta-learning engine, reflection memory, quality tracking | Phase 5 |
| **MVS Scoring** | Memory Value Score for intelligent retention decisions | Phase 6 |
| **Vector Deduplication** | Near-duplicate detection and merge via embedding similarity | Phase 7 |

### Estimated Timeline

| Phase | Duration | Dependencies |
|-------|----------|-------------|
| Phase 0 | 30 min | v0.2 operational |
| Phase 1 | 3 hours | Phase 0 |
| Phase 2 | 2 hours | Phase 0 |
| Phase 3 | 2 hours | Phase 2 |
| Phase 4 | 4 hours | Phase 3 |
| Phase 5 | 3 hours | Phase 1 |
| Phase 6 | 2 hours | Phase 1 |
| Phase 7 | 2 hours | Phase 6 |
| Phase 8 | 2 hours | All above |
| **Total** | **~20 hours** | |

---

## Prerequisites

### v0.2 Deployment (Required)

All of the following must be operational before starting v0.3:

- [ ] Neo4j AuraDB with migrations v1-v3 applied
- [ ] Railway deployment with moltbot, Signal, Authentik services running
- [ ] Agent keys created in Neo4j (Phase 1.4 of v0.2)
- [ ] Capability acquisition system functional (Phase 2 of v0.2)
- [ ] 6 agents (Kublai, Mongke, Chagatai, Temujin, Jochi, Ogedei) responding to messages

### Verification

```bash
# Verify v0.2 is operational
python scripts/run_migrations.py --target-version 3  # Should report "already at version 3"

# Verify agent keys exist
python -c "
from neo4j import GraphDatabase
import os
d = GraphDatabase.driver(os.getenv('NEO4J_URI'), auth=(os.getenv('NEO4J_USER','neo4j'), os.getenv('NEO4J_PASSWORD')))
with d.session() as s:
    r = s.run('MATCH (a:Agent)-[:HAS_KEY]->(k:AgentKey) RETURN count(a) as agents')
    print(f'Agents with keys: {r.single()[\"agents\"]}')  # Should be 6
d.close()
"
```

---

## Phase 0: Schema Extensions & Migration v4

**Duration**: 30 minutes
**Dependencies**: v0.2 operational (migrations v1-v3 applied)
**Parallelizable**: No (foundation for all subsequent phases)

### Task 0.1: Create Migration v4 (Curation Schema)

**File**: `migrations/v4_memory_curation.py` (create)

```python
class V4MemoryCuration:
    """Memory curation schema extensions for v0.3."""
    version = 4
    description = "Jochi memory curation engine schema extensions"

    UP_CYPHER = [
        # Curation properties on MemoryEntry
        # access_count_7d: rolling 7-day access counter
        # last_curated_at: when Jochi last evaluated this node
        # curation_action: last action taken (KEEP/DEMOTE/PRUNE/PROMOTE)
        # tombstone: soft-deleted, pending hard delete after 30 days
        # deleted_at: when tombstoned

        # Curation query index (last_curated_at + tier)
        "CREATE INDEX memory_curation IF NOT EXISTS FOR (m:MemoryEntry) ON (m.last_curated_at, m.tier)",

        # Tombstone index for cleanup queries
        "CREATE INDEX memory_tombstone IF NOT EXISTS FOR (m:MemoryEntry) ON (m.tombstone, m.deleted_at)",

        # Notification read status index for TTL queries
        "CREATE INDEX notification_read_status IF NOT EXISTS FOR (n:Notification) ON (n.read, n.created_at)",

        # SessionContext active status index
        "CREATE INDEX session_active IF NOT EXISTS FOR (sc:SessionContext) ON (sc.active, sc.last_active_at)",

        # Belief confidence + state index for decay queries
        "CREATE INDEX belief_confidence_state IF NOT EXISTS FOR (b:Belief) ON (b.confidence, b.state)",

        # Task status + completion time index for archival
        "CREATE INDEX task_completion IF NOT EXISTS FOR (t:Task) ON (t.status, t.completed_at)",

        # WorkflowImprovement index for Ogedei proposals
        "CREATE INDEX improvement_status IF NOT EXISTS FOR (w:WorkflowImprovement) ON (w.status, w.proposed_at)",

        # BackgroundTask index for Chagatai synthesis tracking
        "CREATE INDEX background_task_agent IF NOT EXISTS FOR (bt:BackgroundTask) ON (bt.agent, bt.status)",
    ]

    DOWN_CYPHER = [
        "DROP INDEX memory_curation IF EXISTS",
        "DROP INDEX memory_tombstone IF EXISTS",
        "DROP INDEX notification_read_status IF EXISTS",
        "DROP INDEX session_active IF EXISTS",
        "DROP INDEX belief_confidence_state IF EXISTS",
        "DROP INDEX task_completion IF EXISTS",
        "DROP INDEX improvement_status IF EXISTS",
        "DROP INDEX background_task_agent IF EXISTS",
    ]

    def up(self, tx):
        for cypher in self.UP_CYPHER:
            tx.run(cypher)

    def down(self, tx):
        for cypher in self.DOWN_CYPHER:
            tx.run(cypher)
```

### Task 0.2: Register Migration v4 in Runner

**File**: `scripts/run_migrations.py` (edit)

Add V4MemoryCuration import and registration:

```python
from migrations.v4_memory_curation import V4MemoryCuration

# In main():
manager.register_migration(
    version=4, name="memory_curation",
    up_cypher=V4MemoryCuration.UP_CYPHER,
    down_cypher=V4MemoryCuration.DOWN_CYPHER,
    description="Jochi memory curation engine schema extensions"
)
```

### Task 0.3: Run Migration v4

```bash
python scripts/run_migrations.py --target-version 4
```

### Task 0.4: Verify Schema

```cypher
// Verify curation indexes exist
SHOW INDEXES YIELD name, type
WHERE name IN ['memory_curation', 'memory_tombstone', 'notification_read_status',
               'session_active', 'belief_confidence_state', 'task_completion']
RETURN name, type;
// Expected: 6 indexes
```

### Exit Criteria Phase 0

- [ ] Migration v4 file created at `migrations/v4_memory_curation.py`
- [ ] Migration runner updated with v4 registration
- [ ] Migration v4 applied successfully
- [ ] All 6+ new indexes verified in Neo4j

---

## Phase 1: Jochi Memory Curation Engine

**Duration**: 3 hours
**Dependencies**: Phase 0 complete
**Parallelizable**: No (core engine, phases 2-5 depend on this)
**Design Reference**: `docs/plans/jochi-memory-curation-design.md` Option A (Tiered Janitor)

### Overview

Jochi runs a continuous heartbeat-driven curation cycle that keeps the Neo4j database optimized. Four frequency tiers handle different maintenance tasks:

| Frequency | Operations | Budget |
|-----------|-----------|--------|
| Every 5 min | Notification cleanup, session pruning, token budget enforcement | <2s |
| Every 15 min | Task archival, tier demotions (HOT->WARM, WARM->COLD) | <5s |
| Every hour | Belief confidence decay, orphan detection, tier promotions | <10s |
| Every 6 hours | Full graph hygiene, reflection consolidation check | <30s |

### Task 1.1: Implement Curation Scheduler

**File**: `tools/kurultai/curation_scheduler.py` (create)

Implement an async scheduler that runs curation operations on the heartbeat schedule above. The scheduler should:

1. Accept a Neo4j driver instance and curation query executor
2. Run each frequency tier's operations on its respective interval
3. Log execution time and results per cycle
4. Skip a cycle if the previous cycle at the same frequency is still running
5. Gracefully handle Neo4j connection failures (retry with backoff, max 3 retries)

```python
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Callable, Awaitable

logger = logging.getLogger("jochi.curation")

class CurationScheduler:
    """Heartbeat-driven memory curation scheduler for Jochi."""

    FREQUENCIES = {
        "rapid": timedelta(minutes=5),
        "standard": timedelta(minutes=15),
        "hourly": timedelta(hours=1),
        "deep": timedelta(hours=6),
    }

    def __init__(self, query_executor: 'CurationQueryExecutor'):
        self.executor = query_executor
        self._running = False
        self._tasks: Dict[str, asyncio.Task] = {}

    async def start(self):
        """Start all curation loops."""
        self._running = True
        for freq_name, interval in self.FREQUENCIES.items():
            self._tasks[freq_name] = asyncio.create_task(
                self._run_loop(freq_name, interval)
            )
        logger.info("Curation scheduler started (4 frequency tiers)")

    async def stop(self):
        """Stop all curation loops gracefully."""
        self._running = False
        for task in self._tasks.values():
            task.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        logger.info("Curation scheduler stopped")

    async def _run_loop(self, freq_name: str, interval: timedelta):
        """Run a single frequency tier's curation loop."""
        while self._running:
            start = datetime.now()
            try:
                results = await self.executor.run_tier(freq_name)
                elapsed = (datetime.now() - start).total_seconds()
                logger.info(f"[{freq_name}] Curation cycle complete: {results} ({elapsed:.1f}s)")
            except Exception as e:
                logger.error(f"[{freq_name}] Curation cycle failed: {e}")
            await asyncio.sleep(interval.total_seconds())
```

### Task 1.2: Implement Curation Query Executor

**File**: `tools/kurultai/curation_queries.py` (create)

Implement 15 parameterized Cypher queries organized by frequency tier:

**Rapid (every 5 min):**
1. Prune read Notifications older than 7 days
2. Prune non-critical unread Notifications older than 30 days
3. Prune inactive SessionContexts older than 24 hours
4. Enforce HOT tier token budget (1600 tokens) — demote LRU entries to WARM
5. Enforce WARM tier token budget (400 tokens) — demote LRU entries to COLD
6. Enforce COLD tier token budget (200 tokens) — demote LRU entries to ARCHIVE

**Standard (every 15 min):**
7. Archive completed Tasks older than 14 days (unless LEARNED_FROM relationship exists)
8. Demote HOT entries not accessed in 12+ hours (with no active session references) to WARM
9. Demote WARM entries not accessed in 48+ hours with access_count_7d < 2 to COLD

**Hourly:**
10. Decay Belief confidence: reduce by 0.01 per day for Beliefs not accessed in 7+ days
11. Detect orphaned nodes (nodes with zero relationships, not Agent/AgentKey/SystemConfig)
12. Promote COLD entries accessed 3+ times in 7 days (or referenced by active session) to WARM
13. Promote WARM entries accessed 10+ times in 7 days (or linked to in_progress task) to HOT

**Deep (every 6 hours):**
14. Full orphan cleanup: delete orphaned nodes older than 7 days
15. Flag unconsolidated Reflections for consolidation (access_count > 3, not yet consolidated)

Each query must:
- Include a `LIMIT` clause to bound execution time
- Check against the never-prune safety rails before any destructive operation
- Update `last_curated_at` and `curation_action` on processed nodes
- Return a count of affected nodes

```python
class CurationQueryExecutor:
    """Executes parameterized curation Cypher queries against Neo4j."""

    # Never-prune safety check subquery (included in all destructive queries)
    SAFETY_CHECK = """
    AND NOT (m:Agent)
    AND NOT (m:AgentKey)
    AND NOT (m:SystemConfig)
    AND NOT (m:Migration)
    AND NOT (m.status IN ['in_progress', 'pending', 'blocked'])
    AND NOT (m:SessionContext {active: true})
    AND NOT (m:Belief {state: 'active', confidence: 0.9})
    AND NOT (m.created_at > datetime() - duration('P1D'))
    """

    # ... implement all 15 queries ...
```

### Task 1.3: Implement Access Counter Middleware

**File**: `tools/kurultai/access_counter.py` (create)

Add middleware to increment `access_count_7d` and update `last_accessed` whenever a MemoryEntry is read. This counter drives tier promotion/demotion decisions.

```python
class AccessCounter:
    """Tracks memory access patterns for curation decisions."""

    UPDATE_QUERY = """
    MATCH (m) WHERE id(m) = $node_id
    SET m.last_accessed = datetime(),
        m.access_count_7d = COALESCE(m.access_count_7d, 0) + 1
    """

    DECAY_QUERY = """
    // Run daily: decay access_count_7d for entries not accessed today
    MATCH (m:MemoryEntry)
    WHERE m.last_accessed < datetime() - duration('P1D')
      AND m.access_count_7d > 0
    SET m.access_count_7d = CASE
        WHEN m.access_count_7d > 1 THEN m.access_count_7d - 1
        ELSE 0
    END
    """
```

### Task 1.4: Integrate with Jochi Agent Initialization

**File**: `data/workspace/souls/analyst/SOUL.md` (edit)

Add curation responsibilities to Jochi's SOUL.md:

```markdown
## Memory Curation Protocol

You run a continuous memory curation engine on a heartbeat schedule:

- Every 5 min: Clean notifications, enforce token budgets (HOT<=1600, WARM<=400, COLD<=200)
- Every 15 min: Archive completed tasks, demote stale entries between tiers
- Every hour: Decay belief confidence, detect orphans, promote frequently-accessed entries
- Every 6 hours: Full graph hygiene, flag reflections for consolidation

### Safety Rails
NEVER prune: Agent nodes, AgentKeys, active tasks, active sessions, high-confidence Beliefs
(>=0.9), proven Reflections (access_count>5), Migration nodes, SystemConfig, entries <24h old,
entries with 4+ cross-agent references.

### When Curating
- Always check safety rails before any destructive operation
- Log every prune/demote/promote action
- If unsure whether to prune, demote instead
- Report curation metrics to Kublai on request
```

### Task 1.5: Wire Curation into OpenClaw Startup

**File**: `tools/kurultai/jochi_init.py` (create or edit existing Jochi initialization)

Start the CurationScheduler when Jochi's agent process initializes. Stop it on shutdown.

```python
async def initialize_jochi_curation(neo4j_driver):
    """Start Jochi's memory curation engine."""
    executor = CurationQueryExecutor(neo4j_driver)
    scheduler = CurationScheduler(executor)
    await scheduler.start()
    return scheduler

async def shutdown_jochi_curation(scheduler):
    """Stop curation engine gracefully."""
    await scheduler.stop()
```

### Exit Criteria Phase 1

- [ ] CurationScheduler runs all 4 frequency tiers without errors
- [ ] 15 Cypher queries implemented and tested individually
- [ ] Safety rails prevent pruning of protected nodes (unit test)
- [ ] HOT tier stays within 1600 token budget after simulated 24h activity
- [ ] Stale Notifications (read, >7 days) are pruned within one rapid cycle
- [ ] Completed Tasks (>14 days) are archived within one standard cycle
- [ ] Access counter increments on memory reads
- [ ] Jochi SOUL.md updated with curation protocol

---

## Phase 2: Delegation Protocol (HMAC-SHA256)

**Duration**: 2 hours
**Dependencies**: Phase 0 complete (agent keys exist from v0.2 Phase 1.4)
**Parallelizable**: Yes (independent of Phase 1)

> Deferred from v0.2: Agent signing keys were pre-created in v0.2 Phase 1.4. This phase implements the actual signing and verification middleware.

### Task 2.1: Implement Message Signing Middleware

**File**: `src/protocols/message_signing.py` (create)

```python
import hmac
import hashlib
import json
from datetime import datetime, timedelta

class MessageSigner:
    """HMAC-SHA256 message signing for inter-agent communication."""

    def __init__(self, agent_id: str, key_material: str):
        self.agent_id = agent_id
        self.key = key_material.encode('utf-8')

    def sign(self, payload: dict) -> dict:
        """Sign a message payload. Returns payload with signature metadata."""
        timestamp = datetime.utcnow().isoformat()
        message = json.dumps(payload, sort_keys=True) + timestamp
        signature = hmac.new(self.key, message.encode('utf-8'), hashlib.sha256).hexdigest()
        return {
            **payload,
            "_signed_by": self.agent_id,
            "_timestamp": timestamp,
            "_signature": signature,
        }

    def verify(self, signed_payload: dict, sender_key: str, max_age_seconds: int = 300) -> bool:
        """Verify a signed message. Returns True if valid."""
        signature = signed_payload.pop("_signature", None)
        sender = signed_payload.pop("_signed_by", None)
        timestamp_str = signed_payload.pop("_timestamp", None)

        if not all([signature, sender, timestamp_str]):
            return False

        # Check timestamp freshness (replay prevention)
        timestamp = datetime.fromisoformat(timestamp_str)
        if datetime.utcnow() - timestamp > timedelta(seconds=max_age_seconds):
            return False

        # Verify HMAC
        message = json.dumps(signed_payload, sort_keys=True) + timestamp_str
        expected = hmac.new(sender_key.encode('utf-8'), message.encode('utf-8'), hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)
```

### Task 2.2: Implement Key Retrieval from Neo4j

**File**: `src/protocols/agent_keys.py` (create)

```python
class AgentKeyStore:
    """Retrieve and cache agent signing keys from Neo4j."""

    def __init__(self, neo4j_driver):
        self.driver = neo4j_driver
        self._cache = {}

    def get_key(self, agent_id: str) -> str:
        """Get agent's active signing key. Cached per session."""
        if agent_id in self._cache:
            return self._cache[agent_id]

        with self.driver.session() as session:
            result = session.run("""
                MATCH (a:Agent {id: $agent_id})-[:HAS_KEY]->(k:AgentKey {is_active: true})
                WHERE k.expires_at > datetime()
                RETURN k.key_hash as key_material
                ORDER BY k.created_at DESC
                LIMIT 1
            """, agent_id=agent_id)
            record = result.single()
            if not record:
                raise ValueError(f"No active key found for agent {agent_id}")
            self._cache[agent_id] = record["key_material"]
            return self._cache[agent_id]
```

### Task 2.3: Integrate Signing into Delegation Protocol

**File**: `src/protocols/delegation.py` (edit)

Wrap existing `agentToAgent` calls with message signing and verification. Unsigned messages from known agents should be rejected with a warning log.

### Exit Criteria Phase 2

- [ ] MessageSigner signs and verifies messages correctly (unit test)
- [ ] Replay attacks rejected (message older than 300s)
- [ ] AgentKeyStore retrieves active keys from Neo4j
- [ ] Expired keys are rejected
- [ ] Delegation protocol wraps messages with signatures
- [ ] Unsigned inter-agent messages logged as warnings

---

## Phase 3: Jochi-Temujin Collaboration Protocol

**Duration**: 2 hours
**Dependencies**: Phase 2 complete (signed messaging required)
**Parallelizable**: No

> From neo4j.md Phase 6: Defines how analyst and developer work together on backend issues.

### Task 3.1: Implement Issue Handoff Protocol

**File**: `src/protocols/jochi_temujin.py` (create)

Implement the handoff workflow:
1. Jochi identifies issue -> creates Analysis node with `status: "identified"`
2. Jochi notifies Kublai -> "Backend issue #X requires Temujin implementation"
3. Kublai delegates to Temujin -> via signed agentToAgent with Analysis node ID
4. Temujin implements fix -> updates Analysis `status: "resolved"`
5. Jochi validates -> runs checks to confirm fix, updates `status: "validated"`

```python
class JochiTemujinProtocol:
    """Analyst-Developer collaboration protocol."""

    def create_issue(self, neo4j_session, category: str, findings: str,
                     location: str, severity: str, recommended_fix: str) -> str:
        """Jochi creates a backend issue Analysis node."""
        result = neo4j_session.run("""
            MATCH (jochi:Agent {id: 'analyst'})
            CREATE (a:Analysis {
                id: randomUUID(),
                type: 'backend_issue',
                category: $category,
                findings: $findings,
                location: $location,
                severity: $severity,
                recommended_fix: $recommended_fix,
                status: 'identified',
                identified_by: 'analyst',
                requires_implementation_by: 'developer',
                created_at: datetime()
            })
            CREATE (jochi)-[:IDENTIFIED]->(a)
            RETURN a.id as id
        """, category=category, findings=findings, location=location,
             severity=severity, recommended_fix=recommended_fix)
        return result.single()["id"]

    def resolve_issue(self, neo4j_session, analysis_id: str, resolution: str) -> bool:
        """Temujin resolves an issue."""
        neo4j_session.run("""
            MATCH (a:Analysis {id: $id})
            MATCH (temujin:Agent {id: 'developer'})
            SET a.status = 'resolved',
                a.resolution = $resolution,
                a.resolved_at = datetime()
            CREATE (temujin)-[:RESOLVED]->(a)
        """, id=analysis_id, resolution=resolution)
        return True

    def validate_fix(self, neo4j_session, analysis_id: str, valid: bool, notes: str = "") -> bool:
        """Jochi validates Temujin's fix."""
        status = "validated" if valid else "fix_rejected"
        neo4j_session.run("""
            MATCH (a:Analysis {id: $id})
            SET a.status = $status,
                a.validation_notes = $notes,
                a.validated_at = datetime()
        """, id=analysis_id, status=status, notes=notes)
        return True
```

### Task 3.2: Update Agent SOULs

**File**: `data/workspace/souls/analyst/SOUL.md` (edit) — add collaboration section
**File**: `data/workspace/souls/developer/SOUL.md` (edit) — add issue resolution section

### Exit Criteria Phase 3

- [ ] Jochi can create Analysis nodes with `status: identified`
- [ ] Kublai receives notification of new backend issues
- [ ] Temujin can resolve issues and update status
- [ ] Jochi can validate fixes
- [ ] Full handoff cycle works end-to-end (integration test)
- [ ] Issue categories match: connection_pool, resilience, data_integrity, performance, security

---

## Phase 4: Agent Autonomous Behaviors

**Duration**: 4 hours
**Dependencies**: Phase 3 complete
**Parallelizable**: Tasks 4.1, 4.2, 4.3 are independent of each other

> From neo4j.md Phases 4.6, 4.7, 4.8: Each agent gets autonomous capabilities.

### Task 4.1: Jochi Backend Issue Detection

**Duration**: 1.5 hours
**Dependencies**: Phase 3 (collaboration protocol)

> From neo4j.md Phase 4.6

Implement Jochi's automated backend code review. Jochi monitors Python/Neo4j code for:

| Category | Issues to Identify | Severity |
|----------|-------------------|----------|
| Connection Management | Missing pool config, no timeouts, resource exhaustion | Critical |
| Resilience | No retry logic, missing circuit breaker, no fallback mode | High |
| Data Integrity | Unparameterized queries, missing transactions, no migrations | High |
| Performance | Missing query timeouts, unbounded data growth, blocking ops | Medium |
| Security | Secrets in logs, unverified downloads, missing input validation | Critical |

**File**: `tools/kurultai/backend_reviewer.py` (create)

Implement `BackendIssueDetector` class that uses tree-sitter AST parsing (existing `backend_collaboration.py` integration) to scan Python files for the issue categories above.

### Task 4.2: Ogedei Proactive Improvement Protocol

**Duration**: 1.5 hours
**Dependencies**: Phase 0 (WorkflowImprovement schema)

> From neo4j.md Phase 4.7

Implement `record_workflow_improvement()`, `approve_workflow_improvement()`, and `get_pending_improvements()` methods in OperationalMemory.

**File**: `openclaw_memory.py` (edit) — add WorkflowImprovement methods

**File**: `data/workspace/souls/ops/SOUL.md` (edit) — add proactive reflection protocol:

```markdown
## Proactive Improvement Protocol

### Reflection Questions (ask yourself regularly):
1. What took longer than it should have today?
2. Which manual steps could be automated?
3. Are agents waiting on each other unnecessarily?
4. Could information flow more efficiently?
5. Are there recurring patterns that suggest a systemic issue?

### Reflection Schedule:
| Trigger | Reflection Action | Output |
|---------|------------------|--------|
| Task completed | Quick friction check | Mental note or brief log |
| Daily (21:00 UTC) | Review day's operations | Identify 1-2 improvement opportunities |
| Weekly (Sunday) | Deep workflow analysis | Formal improvement proposals |
| Metric threshold | Alert-based reflection | Immediate proposal if critical |

### Proposal Criteria:
- Must have clear expected benefit (time saved, errors reduced)
- Must include implementation complexity estimate
- Must not compromise security or privacy
- Must be reversible if it doesn't work

### Kublai Approval:
- Send proposal via agentToAgent with clear yes/no question
- Wait for explicit approval before implementing
- If declined, archive and note reason
```

### Task 4.3: Chagatai Background Synthesis

**Duration**: 1 hour
**Dependencies**: Phase 0

> From neo4j.md Phase 4.8

Implement idle-time background synthesis for Chagatai. When no user tasks are assigned, Ogedei monitors agent idle state and triggers synthesis tasks:

**File**: `tools/kurultai/background_synthesis.py` (create)

```python
class BackgroundSynthesisManager:
    """Manages Chagatai's idle-time knowledge consolidation."""

    SYNTHESIS_TYPES = [
        "memory_consolidation",     # Merge related MemoryEntries
        "insight_generation",       # Generate new Synthesis nodes from patterns
        "knowledge_gap_detection",  # Identify areas with sparse coverage
        "cross_agent_summary",      # Summarize cross-agent collaboration patterns
    ]

    def get_next_synthesis_task(self, neo4j_session) -> dict:
        """Determine what Chagatai should synthesize next."""
        # Priority: consolidation > insights > gaps > summaries
        # Check what hasn't been synthesized recently
        ...
```

**File**: `data/workspace/souls/writer/SOUL.md` (edit) — add background synthesis protocol

### Exit Criteria Phase 4

- [ ] Jochi scans Python files and creates Analysis nodes for detected issues
- [ ] Issue categories cover all 5 areas (connection, resilience, integrity, performance, security)
- [ ] Ogedei can create WorkflowImprovement proposals
- [ ] Kublai can approve/decline proposals (status transitions work)
- [ ] Chagatai receives synthesis tasks when idle
- [ ] All 3 agent SOULs updated with autonomous behavior protocols
- [ ] Autonomous behaviors don't fire during active user conversations (idle detection)

---

## Phase 5: Self-Improvement & Kaizen Integration

**Duration**: 3 hours
**Dependencies**: Phase 1 complete (curation engine manages reflection storage)
**Parallelizable**: Yes (independent of Phases 2-4)

> From neo4j.md Phase 4.9: Self-improvement skills integration using Neo4j vector indexes.

### Task 5.1: Integrate AgentReflectionMemory

**File**: `tools/reflection_memory.py` (verify/edit existing)

Verify the existing `AgentReflectionMemory` class works with the current Neo4j schema:
- 384-dim embeddings via `all-MiniLM-L6-v2`
- HOT/WARM/COLD tier management (now handled by Phase 1 curation)
- Reflection creation with rate limiting (5 min cooldown, max 50/day)

Wire reflection memory into each agent's initialization so reflections are created after significant task completions.

### Task 5.2: Meta-Learning Engine

**File**: `tools/kurultai/meta_learning.py` (create)

Implement the Mistake -> MetaRule pipeline:

1. Agent encounters an error or suboptimal outcome
2. Creates a Reflection node with context, decision, outcome, lesson
3. Meta-learning engine periodically scans Reflections for patterns
4. When 3+ similar Reflections exist, generates a MetaRule
5. MetaRules are injected into relevant agent SOULs as learned guidelines

```python
class MetaLearningEngine:
    """Extract meta-rules from agent reflection patterns."""

    def scan_for_patterns(self, neo4j_session, min_similar: int = 3) -> list:
        """Find clusters of similar reflections that suggest a meta-rule."""
        result = neo4j_session.run("""
            MATCH (r:Reflection)
            WHERE r.embedding IS NOT NULL
            WITH r
            CALL db.index.vector.queryNodes('reflection_embedding', $k, r.embedding)
            YIELD node AS similar, score
            WHERE id(similar) <> id(r) AND score >= 0.80
            WITH r, collect(similar) AS cluster, count(similar) AS cluster_size
            WHERE cluster_size >= $min_similar
            RETURN r.id AS seed_id, r.lesson AS seed_lesson,
                   cluster_size, [s IN cluster | s.lesson] AS similar_lessons
            LIMIT 10
        """, k=min_similar + 1, min_similar=min_similar)
        return [dict(record) for record in result]

    def create_meta_rule(self, neo4j_session, pattern: dict) -> str:
        """Create a MetaRule from a reflection pattern cluster."""
        # Synthesize a rule from the cluster of similar reflections
        ...
```

### Task 5.3: Kaizen Quality Tracking

**File**: `tools/kurultai/kaizen_tracker.py` (create)

Track quality metrics over time to measure self-improvement:
- Task completion rate
- Error rate (issues identified vs resolved)
- Reflection-to-MetaRule conversion rate
- Agent response quality (user satisfaction signals)

### Exit Criteria Phase 5

- [ ] AgentReflectionMemory creates Reflection nodes with 384-dim embeddings
- [ ] Reflection rate limiting enforced (5 min cooldown, 50/day max)
- [ ] Meta-learning engine detects reflection clusters (3+ similar)
- [ ] MetaRules created from reflection patterns
- [ ] Kaizen tracker records quality metrics
- [ ] Reflection tier management defers to Phase 1 curation engine (no duplicate logic)

---

## Phase 6: MVS Scoring Engine

**Duration**: 2 hours
**Dependencies**: Phase 1 complete (builds on top of tiered janitor)
**Parallelizable**: No (extends Phase 1)

> From design doc Option B Phase 1: Adds intelligent scoring on top of TTL rules.

### Task 6.1: Implement Additive MVS Formula

**File**: `tools/kurultai/mvs_scorer.py` (create)

```python
import math
from datetime import datetime, timedelta

class MemoryValueScorer:
    """Additive Memory Value Score (MVS) formula.

    MVS = (type_weight + recency_bonus + frequency_bonus + quality_bonus
           + centrality_bonus + cross_agent_bonus - bloat_penalty) * safety_multiplier

    Additive formula prevents cliff effects (single zero-factor collapsing entire score).
    """

    TYPE_WEIGHTS = {
        ("Belief", "active", 0.7): 10.0,   # High-confidence active Belief
        ("Reflection", None, None): 8.0,
        ("Analysis", None, None): 7.0,
        ("Synthesis", None, None): 6.5,
        ("Recommendation", None, None): 5.0,
        ("CompressedContext", None, None): 4.0,
        ("Task", "active", None): 3.0,
        ("MemoryEntry", None, None): 2.5,
        ("SessionContext", None, None): 1.5,
        ("Notification", None, None): 0.5,
    }

    HALF_LIVES = {
        "Belief": 180, "Reflection": 90, "Analysis": 60,
        "Synthesis": 120, "Recommendation": 30, "CompressedContext": 90,
        "MemoryEntry": 45, "SessionContext": 1, "Notification": 0.5,
    }

    def score(self, node: dict) -> float:
        """Calculate MVS for a memory node."""
        type_weight = self._type_weight(node)
        recency = self._recency_bonus(node)       # 0.0 - 3.0
        frequency = self._frequency_bonus(node)    # 0.0 - 2.0
        quality = self._quality_bonus(node)        # 0.0 - 2.0
        centrality = self._centrality_bonus(node)  # 0.0 - 1.5
        cross_agent = self._cross_agent_bonus(node)# 0.0 - 2.0
        bloat = self._bloat_penalty(node)          # 0.0 - 1.5
        safety = self._safety_multiplier(node)     # 1.0 or 100.0

        return (type_weight + recency + frequency + quality
                + centrality + cross_agent - bloat) * safety

    def _recency_bonus(self, node: dict) -> float:
        """Exponential decay based on last access time."""
        if not node.get("last_accessed"):
            return 0.0
        days_ago = (datetime.now() - node["last_accessed"]).days
        half_life = self.HALF_LIVES.get(node.get("type", "MemoryEntry"), 45)
        return 3.0 * math.exp(-0.693 * days_ago / max(half_life, 1))

    def _frequency_bonus(self, node: dict) -> float:
        """Log-scaled access rate."""
        count = node.get("access_count_7d", 0)
        return min(2.0, math.log1p(count) * 0.7)

    # ... remaining bonus/penalty methods ...
```

### Task 6.2: Integrate MVS with Curation Engine

**File**: `tools/kurultai/curation_queries.py` (edit)

Add a scoring pass before TTL-based pruning. MVS overrides TTL:
- High-MVS node that would expire via TTL gets preserved
- Low-MVS node that hasn't hit TTL yet gets demoted faster

### Task 6.3: MVS Action Thresholds

| MVS Range | Action |
|-----------|--------|
| >= 50.0 | KEEP (safety-protected) |
| >= 8.0 | KEEP |
| 5.0 - 8.0 | KEEP, flag for compression if bloated |
| 3.0 - 5.0 | IMPROVE (enrich metadata) or MERGE (if similar exists) |
| 1.5 - 3.0 | DEMOTE one tier |
| 0.5 - 1.5 | PRUNE (soft delete with 30-day tombstone) |
| < 0.5 | PRUNE (immediate for Notifications/Sessions) |

### Exit Criteria Phase 6

- [ ] MVS formula produces expected scores for all node types (unit test with worked examples)
- [ ] Additive formula verified: no single zero-factor collapses score
- [ ] MVS overrides TTL: high-MVS nodes preserved past TTL expiry
- [ ] MVS accelerates: low-MVS nodes demoted before TTL
- [ ] Action thresholds trigger correct curation actions
- [ ] Safety multiplier (100.0x) prevents pruning of protected nodes

---

## Phase 7: Vector Deduplication

**Duration**: 2 hours
**Dependencies**: Phase 6 complete (MVS scores needed for merge decisions)
**Parallelizable**: No

> From design doc Option B Phase 2: Near-duplicate detection and merge via embedding similarity.

### Task 7.1: Create Vector Indexes for Deduplication

Requires Neo4j 5.11+ vector index support. Verify AuraDB supports `db.index.vector.queryNodes()`.

```cypher
// Belief embedding index (if not already created)
CREATE VECTOR INDEX belief_embedding IF NOT EXISTS
FOR (b:Belief) ON b.embedding
OPTIONS {indexConfig: {`vector.dimensions`: 384, `vector.similarity_function`: 'cosine'}};

// MemoryEntry embedding index
CREATE VECTOR INDEX memory_entry_embedding IF NOT EXISTS
FOR (m:MemoryEntry) ON m.embedding
OPTIONS {indexConfig: {`vector.dimensions`: 384, `vector.similarity_function`: 'cosine'}};
```

> Note: `reflection_embedding` vector index already exists from v0.2 Phase 4.9.

### Task 7.2: Implement Batch Deduplication Engine

**File**: `tools/kurultai/dedup_engine.py` (create)

```python
class DeduplicationEngine:
    """Detect and merge near-duplicate memory entries via vector similarity."""

    SIMILARITY_THRESHOLD = 0.85  # Cosine similarity threshold for near-duplicates

    def find_duplicates(self, neo4j_session, node_type: str, batch_size: int = 50) -> list:
        """Find near-duplicate pairs for a given node type."""
        index_name = f"{node_type.lower()}_embedding"
        result = neo4j_session.run("""
            MATCH (n:$node_type)
            WHERE n.embedding IS NOT NULL AND n.tombstone IS NULL
            WITH n LIMIT $batch_size
            CALL db.index.vector.queryNodes($index_name, 5, n.embedding)
            YIELD node AS similar, score
            WHERE id(similar) <> id(n) AND score >= $threshold
              AND similar.tombstone IS NULL
            RETURN id(n) AS source_id, n.id AS source_uuid,
                   id(similar) AS target_id, similar.id AS target_uuid,
                   score
            ORDER BY score DESC
        """, node_type=node_type, index_name=index_name,
             batch_size=batch_size, threshold=self.SIMILARITY_THRESHOLD)
        return [dict(r) for r in result]

    def merge_duplicates(self, neo4j_session, source_id: str, target_id: str,
                         keep_id: str) -> bool:
        """Merge two duplicates. Keep higher-MVS node, transfer relationships."""
        discard_id = target_id if keep_id == source_id else source_id
        neo4j_session.run("""
            MATCH (keep) WHERE keep.id = $keep_id
            MATCH (discard) WHERE discard.id = $discard_id
            // Transfer relationships from discard to keep
            CALL {
                WITH keep, discard
                MATCH (discard)-[r]->(other)
                WHERE NOT (keep)-[:SAME_TYPE]->(other)
                CREATE (keep)-[:INHERITED_FROM_MERGE]->(other)
            }
            // Sum access counts
            SET keep.access_count_7d = COALESCE(keep.access_count_7d, 0)
                                     + COALESCE(discard.access_count_7d, 0)
            // Soft-delete the merged node
            SET discard.tombstone = true,
                discard.deleted_at = datetime(),
                discard.curation_action = 'MERGED_INTO:' + $keep_id
        """, keep_id=keep_id, discard_id=discard_id)
        return True
```

### Task 7.3: Integrate Dedup into Deep Curation Cycle

Add deduplication to the 6-hour deep curation cycle. Process one node type per cycle (rotating: Reflection -> Belief -> MemoryEntry) to stay within the 30-second budget.

### Exit Criteria Phase 7

- [ ] Vector indexes created for Belief and MemoryEntry (Reflection already exists)
- [ ] `db.index.vector.queryNodes()` works on AuraDB
- [ ] Near-duplicates detected at >= 0.85 similarity threshold
- [ ] Merge preserves higher-MVS node and transfers relationships
- [ ] Merged nodes soft-deleted with tombstone (not hard-deleted)
- [ ] Dedup runs within 30-second deep cycle budget
- [ ] No false-positive merges on unrelated nodes (precision test)

---

## Phase 8: Testing & Validation

**Duration**: 2 hours
**Dependencies**: All previous phases
**Parallelizable**: No

### Task 8.1: Curation Engine Integration Tests

**File**: `tests/kurultai/test_curation_engine.py` (create)

Test scenarios:
1. **Token budget enforcement**: Create 2000 tokens of HOT entries, verify enforcement demotes to 1600
2. **TTL pruning**: Create read Notification 8 days ago, verify pruned in rapid cycle
3. **Safety rails**: Create Agent node, verify NEVER pruned regardless of TTL/MVS
4. **Tier promotion**: Access COLD entry 5 times in 7 days, verify promoted to WARM
5. **Tier demotion**: Create HOT entry, don't access for 13 hours, verify demoted to WARM
6. **Belief decay**: Create Belief with confidence 0.8, don't access for 14 days, verify decay
7. **Orphan detection**: Create node with zero relationships, verify detected after 7 days
8. **24-hour grace**: Create entry 12 hours ago, verify NOT pruned regardless of other criteria

### Task 8.2: Delegation Protocol Tests

**File**: `tests/kurultai/test_delegation_signing.py` (create)

Test scenarios:
1. Valid signature verification
2. Tampered payload rejection
3. Expired timestamp rejection (>300s)
4. Invalid key rejection
5. Missing signature fields rejection

### Task 8.3: Collaboration Protocol Tests

**File**: `tests/kurultai/test_jochi_temujin.py` (create)

Test the full handoff cycle: identify -> notify -> delegate -> resolve -> validate

### Task 8.4: MVS Scoring Tests

**File**: `tests/kurultai/test_mvs_scorer.py` (create)

Test with worked examples from the design document to verify scoring produces expected results across all node types.

### Task 8.5: Deduplication Tests

**File**: `tests/kurultai/test_dedup_engine.py` (create)

Test duplicate detection accuracy and merge correctness.

### Task 8.6: End-to-End 24-Hour Simulation

Run a simulated 24-hour workload:
1. Seed Neo4j with realistic data (500 nodes across all types)
2. Simulate 6 agents creating/reading entries at realistic rates
3. Run curation engine for simulated 24 hours
4. Verify: token budgets maintained, stale entries pruned, safety rails held, no data loss

### Exit Criteria Phase 8

- [ ] All curation engine tests pass (8 scenarios)
- [ ] All delegation tests pass (5 scenarios)
- [ ] Collaboration protocol end-to-end test passes
- [ ] MVS scoring matches worked examples
- [ ] Dedup engine correctly identifies and merges duplicates
- [ ] 24-hour simulation completes without errors
- [ ] Token budget compliance maintained throughout simulation
- [ ] Zero protected nodes pruned during simulation

---

## Appendices

### Appendix A: Scope Boundary Declaration

**Purpose**: Document which deferred v0.3 items from kurultai_0.2.md Appendix G are covered vs further deferred.

#### v0.3 Coverage

| neo4j.md Phase | Status in v0.3 | Notes |
|---|---|---|
| Phase 4.6: Jochi Backend Issues | COVERED (Phase 4.1) | Automated issue detection and labeling |
| Phase 4.7: Ogedei Proactive Improvement | COVERED (Phase 4.2) | WorkflowImprovement proposals |
| Phase 4.8: Chagatai Background Synthesis | COVERED (Phase 4.3) | Idle-time knowledge consolidation |
| Phase 4.9: Self-Improvement/Kaizen | COVERED (Phase 5) | Meta-learning, reflection memory, quality tracking |
| Phase 6: Jochi-Temujin Collaboration | COVERED (Phase 3) | Issue handoff protocol |
| Phase 7: Delegation Protocol | COVERED (Phase 2) | HMAC-SHA256 signing middleware |
| **NEW: Jochi Memory Curation** | COVERED (Phases 1, 6, 7) | Tiered janitor + MVS scoring + vector dedup |

#### Deferred to v0.4

| neo4j.md Phase | Reason |
|---|---|
| Phase 5: ClawTasks Bounty System | Marketplace feature, requires stable autonomous behaviors first |
| Phase 9: Auto-Skill Generation | Requires proven capability acquisition + self-improvement |
| Phase 10: Competitive Advantage | Business logic layer, requires ClawTasks integration |
| Memory Curation Option C | Full audit trail, LLM compression, adaptive scheduling — defer until database is large enough |

#### Coverage Summary

| Status | Count | Percentage |
|--------|-------|------------|
| COVERED in v0.3 | 7 + 1 new | 100% of deferred items |
| DEFERRED to v0.4 | 3 + 1 | Marketplace & advanced features |

---

### Appendix B: TTL Rules Reference

Complete TTL rules for the Tiered Janitor (Phase 1).

| Node Type | State | TTL | Condition |
|-----------|-------|-----|-----------|
| Notification | read | 7 days | Always |
| Notification | unread | 30 days | If not critical |
| SessionContext | inactive | 24 hours | Always |
| Task | completed | 14 days | Unless has LEARNED_FROM relationship |
| Task | failed | 90 days | Preserved for learning |
| Task | in_progress/pending | Never | Protected |
| Belief | archived, confidence < 0.3 | 30 days | Unless referenced by active Belief |
| Belief | active, confidence >= 0.7 | Never | Protected |
| Belief | active, confidence < 0.3 | 60 days | Auto-archive first, then TTL |
| Reflection | consolidated | 90 days | Unless access_count > 5 |
| Reflection | unconsolidated | Never prune | Flag for consolidation instead |
| Analysis | severity low/info | 60 days | Unless has Recommendation |
| Analysis | severity high/critical | 180 days | Always preserved longer |
| CompressedContext | keywords level | 45 days | Unless accessed |
| Synthesis | -- | 120 days | Unless access_count > 3 |

### Tier Rules

```
Demotion:
  HOT  -> WARM:    last_accessed > 12 hours AND no active session references
  WARM -> COLD:    last_accessed > 48 hours AND access_count_7d < 2
  COLD -> ARCHIVE: last_accessed > 90 days OR never accessed

Promotion:
  COLD -> WARM:    access_count_7d >= 3 OR referenced by active session
  WARM -> HOT:     access_count_7d >= 10 OR linked to in_progress task
```

---

### Appendix C: MVS Formula Reference

Additive Memory Value Score formula (Phase 6).

```
MVS = (
    type_weight                           # 0.5 - 10.0
    + recency_bonus                       # 0.0 - 3.0 (exponential decay)
    + frequency_bonus                     # 0.0 - 2.0 (log-scaled access rate)
    + quality_bonus                       # 0.0 - 2.0 (confidence/severity)
    + centrality_bonus                    # 0.0 - 1.5 (relationship count)
    + cross_agent_bonus                   # 0.0 - 2.0 (multi-agent access)
    - bloat_penalty                       # 0.0 - 1.5 (tokens over target)
) * safety_multiplier                     # 1.0 normal, 100.0 protected
```

**Type Weights:**

| Type | Weight | Half-Life |
|------|--------|-----------|
| Belief (active, conf > 0.7) | 10.0 | 180 days |
| Reflection | 8.0 | 90 days |
| Analysis | 7.0 | 60 days |
| Synthesis | 6.5 | 120 days |
| Recommendation | 5.0 | 30 days |
| CompressedContext | 4.0 | 90 days |
| Task (active) | 3.0 | N/A (protected) |
| MemoryEntry | 2.5 | 45 days |
| SessionContext | 1.5 | 1 day |
| Notification | 0.5 | 12 hours |

---

### Appendix D: Never-Prune Safety Rails

These entries are NEVER pruned regardless of TTL, MVS, or any other criteria:

1. **Agent identity nodes** (Agent type, id in [kublai, mongke, chagatai, temujin, jochi, ogedei])
2. **AgentKey nodes** (security credentials)
3. **Active tasks** (status: in_progress, pending, blocked)
4. **Active sessions** (SessionContext: active=true)
5. **High-confidence active Beliefs** (confidence >= 0.9, state: active)
6. **Consolidated Reflections** with access_count > 5 (proven learning)
7. **Migration nodes** (schema version tracking)
8. **SystemConfig nodes**
9. **Entries created within last 24 hours** (grace period)
10. **Entries with 4+ cross-agent references** (consensus knowledge)
