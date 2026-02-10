# Jochi Memory Curation Engine — Design Document

**Date:** 2026-02-06
**Target:** kurultai_0.3.md integration
**Author:** Horde-brainstorming (Phase 2 specialists + Phase 3 adversarial review)

## Problem Statement

The Neo4j memory database grows unbounded as 6 Kurultai agents create Beliefs, Reflections, Analysis, Tasks, Notifications, and other node types. Without active curation:
- Token budgets overflow (HOT: 1600, WARM: 400, COLD: 200)
- Stale memories dilute retrieval quality
- Near-duplicate entries waste storage and confuse agents
- Orphaned nodes accumulate as relationships are deleted

Jochi (Data Analyst agent) should continuously optimize the database on a heartbeat cadence — pruning stale entries, merging duplicates, promoting/demoting between tiers, and maintaining graph hygiene.

---

## Option A: Tiered Janitor (Recommended)

**Philosophy:** Simple, predictable rules. No scoring model. Each node type has hardcoded TTL and access-based promotion/demotion rules. Runs as a series of batched Cypher queries on a fixed schedule.

### Why This Is Recommended
- Zero moving parts beyond scheduled Cypher queries
- No embedding similarity computation (deferred to Option B)
- No lock management needed (uses node-level timestamps, not locks)
- Predictable performance budget (each query is bounded by LIMIT)
- Easy to tune: change a TTL number, not a scoring formula

### Heartbeat Schedule

| Frequency | Operations | Budget |
|-----------|-----------|--------|
| Every 5 min | Notification cleanup, session pruning, token budget enforcement | <2s |
| Every 15 min | Task archival, tier demotions (HOT→WARM, WARM→COLD) | <5s |
| Every hour | Belief confidence decay, orphan detection, tier promotions | <10s |
| Every 6 hours | Full graph hygiene, reflection consolidation check | <30s |

### TTL Rules

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

### Tier Demotion Rules

```
HOT → WARM:  last_accessed > 12 hours AND no active session references
WARM → COLD:  last_accessed > 48 hours AND access_count_7d < 2
COLD → ARCHIVE:  last_accessed > 90 days OR never accessed
```

### Tier Promotion Rules

```
COLD → WARM:  access_count_7d >= 3 OR referenced by active session
WARM → HOT:   access_count_7d >= 10 OR linked to in_progress task
```

### Token Budget Enforcement (every 5 min)

When a tier exceeds its budget, demote least-recently-accessed entries until under budget:

```cypher
// Enforce HOT tier budget (1600 tokens)
MATCH (m:MemoryEntry {tier: 'HOT'})
WITH m ORDER BY m.last_accessed ASC
WITH collect(m) AS entries, sum(m.token_count) AS total
WHERE total > 1600
UNWIND entries AS m
WITH m, sum(m.token_count) OVER (ORDER BY m.last_accessed ASC) AS running
WHERE running > 1600
SET m.tier = 'WARM', m.updated_at = datetime()
```

### Implementation Complexity: Low
- ~200 lines of Python (async scheduler + query executor)
- ~15 parameterized Cypher queries
- No new Neo4j indexes required beyond existing
- No embedding computation

---

## Option B: Scoring + Deduplication Engine

**Philosophy:** Memory Value Score (MVS) computed for each entry. Deduplication via vector similarity. More intelligent but more complex.

### Adds on top of Option A:

1. **MVS Formula (additive, not multiplicative to avoid cliff effects):**

```
MVS = (
    type_weight                           # 0.5 - 10.0
    + recency_bonus                       # 0.0 - 3.0 (exponential decay)
    + frequency_bonus                     # 0.0 - 2.0 (log-scaled access rate)
    + quality_bonus                       # 0.0 - 2.0 (confidence/severity)
    + centrality_bonus                    # 0.0 - 1.5 (relationship count)
    + cross_agent_bonus                   # 0.0 - 2.0 (multi-agent access)
    - bloat_penalty                       # 0.0 - 1.5 (tokens over target)
) × safety_multiplier                     # 1.0 normal, 100.0 protected
```

Key fix from adversarial review: **additive** formula prevents a single zero-factor from collapsing the entire score.

2. **Type Weights:**

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

3. **MVS Action Thresholds:**

| MVS Range | Action |
|-----------|--------|
| >= 50.0 | KEEP (safety-protected) |
| >= 8.0 | KEEP |
| 5.0 - 8.0 | KEEP, flag for compression if bloated |
| 3.0 - 5.0 | IMPROVE (enrich metadata) or MERGE (if similar node exists) |
| 1.5 - 3.0 | DEMOTE one tier |
| 0.5 - 1.5 | PRUNE (soft delete with 30-day tombstone) |
| < 0.5 | PRUNE (immediate for Notifications/Sessions) |

4. **Deduplication via Vector Index:**

Requires Neo4j 5.11+ vector index support. Use `db.index.vector.queryNodes()` instead of inline cosine computation:

```cypher
// Find near-duplicates for a batch of nodes
UNWIND $node_ids AS nid
MATCH (n) WHERE id(n) = nid AND n.embedding IS NOT NULL
CALL db.index.vector.queryNodes('memory_embedding', 5, n.embedding)
YIELD node AS similar, score
WHERE id(similar) <> nid AND score >= 0.85
RETURN nid, id(similar) AS similar_id, score
```

Merge strategy: keep higher-MVS node, transfer relationships, sum access counts, archive merged node as CurationAudit.

### Implementation Complexity: Medium
- ~500 lines of Python (scorer + dedup engine + scheduler)
- ~25 Cypher queries
- 3 new vector indexes (Reflection, Belief, MemoryEntry embeddings)
- Embedding computation for nodes missing embeddings

---

## Option C: Full Autonomous Curation with Audit Trail

**Philosophy:** Everything from Option B plus a full audit system, adaptive scheduling, lock management, and LLM-powered compression.

### Adds on top of Option B:

1. **CurationAudit nodes** — every prune/merge/demote decision logged with full property snapshot for rollback
2. **CurationCycleSummary nodes** — per-cycle metrics (nodes scanned, pruned, merged, promoted, demoted)
3. **Adaptive mode switching** — IDLE (aggressive, 2.5 min), BACKGROUND (normal, 5 min), MINIMAL (conservative, 15 min) based on agent activity
4. **Lock-based conflict avoidance** — `locked_by`/`locked_at` properties on nodes, checked before curation
5. **LLM compression** — for COMPRESS action, use Claude to summarize verbose entries while preserving meaning
6. **Restoration API** — rollback pruned nodes from audit snapshots

### Risks Identified (Adversarial Review):
- **Audit bloat:** 288 cycles/day × N decisions/cycle creates substantial audit data. Mitigate: TTL audit nodes at 30 days, log only destructive actions (prune, merge).
- **Lock contention:** 6 agents + Jochi all competing for locks. Mitigate: use optimistic concurrency (compare-and-swap) instead of pessimistic locks. Only lock during the actual prune/merge write, not during scoring.
- **LLM compression cost:** Each compression call costs ~1K tokens. At 50 compressions/cycle, that's 50K tokens/cycle. Mitigate: only compress ARCHIVE-tier entries over 500 tokens, max 10 per cycle.
- **Complexity:** ~1000+ lines of Python, 40+ Cypher queries, 5+ new node types.

### Implementation Complexity: High
- Full audit subsystem
- Lock manager
- Adaptive scheduler
- LLM integration for compression

---

## Comparison

| Dimension | Option A | Option B | Option C |
|-----------|----------|----------|----------|
| **Complexity** | Low (~200 LOC) | Medium (~500 LOC) | High (~1000+ LOC) |
| **Intelligence** | Rule-based TTLs | Scoring + dedup | Scoring + dedup + LLM |
| **New Indexes** | 0 | 3 vector indexes | 3 vector + audit indexes |
| **New Node Types** | 0 | 0 | CurationAudit, CycleSummary |
| **Performance Budget** | <2-30s per schedule | <30-60s per cycle | <60-120s per cycle |
| **Reversibility** | None (hard deletes) | Soft delete tombstones | Full audit rollback |
| **Deduplication** | None | Vector similarity | Vector similarity |
| **Compression** | None | None | LLM-powered |
| **Risk** | May over-prune without scoring | Medium (scoring calibration) | High (audit bloat, lock contention) |
| **v0.3 Fit** | Ship immediately | Ship with scoring, add dedup later | Defer most to v0.4 |

---

## Recommendation: Option A now, Option B features incrementally

**Phase 1 (v0.3):** Ship Option A — the tiered janitor. This gives Jochi immediate, safe database optimization with minimal risk. The TTL rules are battle-tested patterns from every cache system ever built.

**Phase 2 (v0.3.1):** Add MVS scoring on top of TTL rules. Use the additive formula. Scoring overrides TTL — a high-MVS node that would expire via TTL gets preserved. A low-MVS node that hasn't hit TTL yet gets demoted faster.

**Phase 3 (v0.3.2):** Add vector deduplication once Neo4j vector indexes are confirmed working on AuraDB. This is the highest-value addition from Option B.

**Defer to v0.4:** Full audit trail, LLM compression, adaptive scheduling, lock management. These add complexity without proportional value until the database is large enough to need them.

---

## Never-Prune Safety Rails

Regardless of option chosen, these entries are NEVER pruned:

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

---

## Schema Additions for v0.3

```cypher
// New properties on MemoryEntry (if not already present)
// access_count_7d: INT (rolling 7-day access counter)
// last_curated_at: DATETIME (when Jochi last evaluated this node)
// curation_action: STRING (last action taken: KEEP/DEMOTE/PRUNE/etc.)
// tombstone: BOOLEAN (soft-deleted, pending hard delete after 30 days)
// deleted_at: DATETIME (when tombstoned)

// New index for curation queries
CREATE INDEX memory_curation IF NOT EXISTS
FOR (m:MemoryEntry) ON (m.last_curated_at, m.tier);

CREATE INDEX memory_tombstone IF NOT EXISTS
FOR (m:MemoryEntry) ON (m.tombstone, m.deleted_at);
```

---

## Integration with kurultai_0.3.md

This design should be added as a new phase in kurultai_0.3.md:

```markdown
## Phase X: Jochi Memory Curation Engine

### Task X.1: Implement Tiered Janitor (Option A)
- Add curation scheduler to Jochi agent initialization
- Implement 15 parameterized Cypher queries for TTL/tier management
- Add access_count_7d rolling counter to MemoryEntry reads
- Add curation indexes to migration v4

### Task X.2: Add MVS Scoring (Option B Phase 1)
- Implement additive MVS formula
- Add scoring pass before TTL-based pruning
- MVS overrides: high-score preserves past TTL, low-score accelerates demotion

### Task X.3: Vector Deduplication (Option B Phase 2)
- Create vector indexes for Reflection, Belief, MemoryEntry embeddings
- Implement batch dedup query using db.index.vector.queryNodes()
- Merge strategy: keep higher MVS, transfer relationships, soft-delete merged

### Exit Criteria
- [ ] Jochi curation runs on 5/15/60 min schedule without errors
- [ ] HOT tier stays within 1600 token budget after 24h of agent activity
- [ ] Stale Notifications pruned within 7 days
- [ ] Completed Tasks archived within 14 days
- [ ] No protected nodes (safety rails) are ever pruned
- [ ] Token budget compliance: HOT <= 1600, WARM <= 400, COLD <= 200
```
