# Bounded File-Based Memory Architecture
## Capping MEMORY.md While Retaining Full History in Neo4j

**Status**: Architecture Recommendation Document
**Date**: 2026-02-04
**Target**: Keep MEMORY.md under 2,000 tokens regardless of conversation length
**Related**: [`neo4j.md`](./neo4j.md), [`kurultai_0.1.md`](./kurultai_0.1.md), [`neo4j-memory-optimization-architecture.md`](./neo4j-memory-optimization-architecture.md)

---

## Executive Summary

This document provides concrete architecture recommendations to solve three critical problems:

1. **Unbounded MEMORY.md growth** - File grows indefinitely as conversations accumulate
2. **Heartbeat initialization cost** - Session startup overhead increases with file size
3. **Token budget pressure** - File-based memory competes with operational context

**Solution**: Implement a hierarchical memory system where:
- **Neo4j** retains full operational history (unbounded, queryable)
- **MEMORY.md** contains only a bounded "working set" (~2,000 tokens max)
- **Heartbeat.md** uses lazy-loading with incremental deltas

---

## Current State Analysis

### Existing Two-Tier Architecture

From [`neo4j.md`](./neo4j.md):

| Tier | Storage | Access | Contents |
|------|---------|--------|----------|
| **Personal** | Files (Kublai) | Kublai only | User preferences, personal history, friend names |
| **Operational** | Neo4j (shared) | All 6 agents | Research, code patterns, analysis, process insights |

### Existing Neo4j Schema for Lifecycle Management

From [`neo4j.md`](./neo4j.md) Phase 4.9:

```cypher
(:Reflection {
  id: uuid,
  agent: string,
  context: string,
  decision: string,
  outcome: string,
  lesson: string,
  embedding: [float],
  importance: float,
  access_tier: "HOT" | "WARM" | "COLD" | "ARCHIVED",
  related_task_id: uuid,
  created_at: datetime
})
```

**Existing retention policy**: `_enforce_retention_policy()` archives old reflections by setting `access_tier='ARCHIVED'` and removing embeddings.

### Existing Intent Window Buffer

From [`kurultai_0.1.md`](./kurultai_0.1.md):

```python
class IntentWindowBuffer:
    MAX_MESSAGES = 100  # Hard limit to prevent unbounded memory growth
    # ... drops oldest messages when exceeded
```

---

## Problem Breakdown

### Problem 1: MEMORY.md Growth

**Current behavior**: Each conversation appends to MEMORY.md indefinitely.

**Impact**:
- Token count grows linearly with conversation history
- Eventually exceeds context window limits
- Forces expensive truncation decisions at query time

**Target**: Hard cap at 2,000 tokens (~1,500 words) regardless of history.

### Problem 2: Heartbeat Initialization Cost

**Current behavior**: `HEARTBEAT.md` loads all periodic tasks at session start.

**Impact**:
- Session initialization time grows with task count
- Unnecessary parsing of tasks not relevant to current session
- No distinction between "always run" vs "on-demand" tasks

**Target**: Lazy loading with incremental delta updates.

### Problem 3: Value-Based Retention

**Current behavior**: No systematic mechanism to determine what stays in file-based memory.

**Impact**:
- High-value insights may be truncated before low-value chitchat
- No scoring system for memory importance
- Manual curation doesn't scale

**Target**: Automated value classification with multi-signal scoring.

---

## Recommended Architecture

### Overview: Three-Layer Memory Hierarchy

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         MEMORY HIERARCHY                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   LAYER 3: NEO4J (Unbounded, Queryable)                                     │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Full conversation history (CompressedContext)                    │   │
│   │  • All KnowledgeChunks with embeddings                              │   │
│   │  • Complete Reflection nodes (HOT/WARM/COLD/ARCHIVED)               │   │
│   │  • Semantic search via vector indexes                               │   │
│   │  • ValueClassification with multi-signal scoring                    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                    ▲                                         │
│                                    │ sync (async)                            │
│   LAYER 2: MEMORY.md (Bounded, ~2K tokens)                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Working context (recent + high-value)                            │   │
│   │  • Personal preferences (PII - Kublai only)                         │   │
│   │  • Active task summaries                                            │   │
│   │  • Quick-reference knowledge                                        │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                    ▲                                         │
│                                    │ load at startup                         │
│   LAYER 1: HEARTBEAT.md (Minimal, Lazy)                                     │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Task registry (IDs only, not full content)                       │   │
│   │  • Last execution timestamps                                        │   │
│   │  • Delta pointers to Neo4j                                          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Concrete Schema Recommendations

### 1. ValueClassification Node (New)

Track multi-signal value scores for all knowledge to drive retention decisions.

```cypher
(:ValueClassification {
  id: string,                    // Same as associated KnowledgeChunk/Reflection
  entity_type: string,           // "KnowledgeChunk" | "Reflection" | "CompressedContext"

  // Multi-signal scoring (0.0 - 1.0 each)
  retention_score: float,        // How likely to be needed again
  uniqueness_score: float,       // Novelty vs existing knowledge
  confidence_score: float,       // Source reliability
  access_frequency: float,       // Normalized access count
  last_accessed: datetime,       // Recency factor

  // Composite score (calculated)
  value_score: float,            // Weighted combination

  // Retention decision
  retention_tier: string,        // "KEEP" | "SUMMARIZE" | "ARCHIVE"

  created_at: datetime,
  updated_at: datetime
})
```

**Indexes**:
```cypher
CREATE INDEX value_classification_score FOR (vc:ValueClassification)
  ON (vc.value_score DESC, vc.retention_tier);

CREATE INDEX value_classification_entity FOR (vc:ValueClassification)
  ON (vc.entity_type, vc.retention_tier);
```

### 2. Enhanced CompressedContext Node

Extend existing schema from [`neo4j-memory-optimization-architecture.md`](./neo4j-memory-optimization-architecture.md):

```cypher
(:CompressedContext {
  id: string,
  sender_hash: string,
  compression_level: string,     // "full" | "summary" | "keywords"
  content: string,
  token_count: int,
  embedding: [float],

  // NEW: Time-based lifecycle
  created_at: datetime,
  expires_at: datetime,          // TTL for cleanup
  last_accessed: datetime,       // For LRU eviction
  access_count: int,             // Usage tracking

  // NEW: Content classification
  content_type: string,          // "preference" | "task" | "insight" | "chitchat"
  contains_pii: boolean,         // True if has personal info

  // NEW: Hierarchical linking
  parent_context_id: string,     // Link to previous summary
  child_context_ids: [string],   // Links to detailed contexts

  access_tier: "PUBLIC" | "SENSITIVE"
})
```

**Relationships**:
```cypher
// Hierarchical compression chain
(:CompressedContext)-[:SUMMARIZED_TO {compression_ratio: float}]->(:CompressedContext)

// Value classification link
(:CompressedContext)-[:HAS_VALUE]->(:ValueClassification)

// Temporal sequence
(:CompressedContext)-[:FOLLOWS]->(:CompressedContext)
```

### 3. BoundedMemoryManifest Node (New)

Track what should be in the bounded file-based memory.

```cypher
(:BoundedMemoryManifest {
  id: string,                    // "kublai_memory_manifest"
  max_tokens: int,               // 2000
  current_tokens: int,           // Current usage
  last_compacted: datetime,      // Last compression run

  // Content pointers (IDs only, not content)
  personal_preference_ids: [string],     // Always keep
  active_task_summary_ids: [string],     // Recent tasks
  high_value_insight_ids: [string],      // Top value_score items
  recent_context_ids: [string],          // Last N conversations

  // Generation metadata
  version: int,                  // Manifest version for cache busting
  generated_at: datetime
})
```

### 4. HeartbeatTaskRegistry Node (New)

Replace full heartbeat.md content with registry pointers.

```cypher
(:HeartbeatTaskRegistry {
  id: string,                    // "kublai_heartbeat_registry"

  // Task pointers (minimal data)
  task_definitions_hash: string, // Hash of full task definitions (in Neo4j)
  last_sync: datetime,

  // Delta tracking
  pending_changes: [string],     // Task IDs with pending updates
  last_full_refresh: datetime
})

(:HeartbeatTask {
  id: string,
  task_name: string,
  schedule: string,              // Cron expression or interval
  last_executed: datetime,
  next_due: datetime,
  execution_count: int,
  error_count: int,
  is_active: boolean,

  // Lazy loading
  definition_ref: string,        // Pointer to full definition in Neo4j
  last_definition_load: datetime
})
```

---

## Algorithms and Policies

### 1. Hierarchical Summarization Policy

**Purpose**: Compress old conversations while preserving retrievability.

```python
class HierarchicalSummarizer:
    """
    Multi-level summarization with Neo4j backing.

    Level 0: Full conversation (stored in Neo4j, not files)
    Level 1: Paragraph summary (~100 tokens)
    Level 2: Bullet summary (~30 tokens)
    Level 3: Keyword tags (~10 tokens)
    """

    COMPRESSION_TARGETS = {
        "full": 1.0,        # No compression
        "summary": 0.1,     # 10% of original
        "keywords": 0.03    # 3% of original
    }

    async def summarize_and_store(
        self,
        conversation_id: str,
        content: str,
        token_count: int
    ) -> Dict[str, str]:
        """
        Create multi-level summaries and store in Neo4j.
        Returns pointers for file-based memory.
        """
        # Store full version in Neo4j (unbounded)
        full_id = await self._store_in_neo4j(
            content=content,
            level="full",
            tokens=token_count
        )

        # Generate and store summaries
        summary = await self._generate_summary(content, ratio=0.1)
        summary_id = await self._store_in_neo4j(
            content=summary,
            level="summary",
            tokens=estimate_tokens(summary),
            parent_id=full_id
        )

        keywords = await self._extract_keywords(content)
        keywords_id = await self._store_in_neo4j(
            content=keywords,
            level="keywords",
            tokens=estimate_tokens(keywords),
            parent_id=summary_id
        )

        # Link hierarchy
        await self._link_hierarchy(full_id, summary_id, keywords_id)

        return {
            "full_id": full_id,
            "summary_id": summary_id,
            "keywords_id": keywords_id,
            "summary": summary,
            "keywords": keywords
        }
```

### 2. Rolling Window with Value-Based Retention

**Purpose**: Keep MEMORY.md under 2,000 tokens using intelligent eviction.

```python
class BoundedMemoryManager:
    """
    Manages file-based MEMORY.md with hard token limit.
    Uses value scoring to determine what stays vs moves to Neo4j.
    """

    MAX_TOKENS = 2000
    PERSONAL_PREFERENCES_BUDGET = 500  # Always keep
    ACTIVE_TASKS_BUDGET = 800          # Recent tasks
    HIGH_VALUE_INSIGHTS_BUDGET = 500   # Top scored items
    RECENT_CONTEXT_BUDGET = 200        # Minimal recent context

    async def compact_memory(self, sender_hash: str):
        """
        Rebuild MEMORY.md from Neo4j, keeping only high-value content.
        Called periodically or when token count exceeds threshold.
        """
        # Get current manifest
        manifest = await self._get_manifest(sender_hash)

        # Build new content sections
        sections = []
        tokens_used = 0

        # Section 1: Personal preferences (always keep)
        prefs = await self._get_personal_preferences(sender_hash)
        pref_tokens = estimate_tokens(prefs)
        if pref_tokens > self.PERSONAL_PREFERENCES_BUDGET:
            prefs = await self._summarize_preferences(prefs)
        sections.append(("Personal Preferences", prefs))
        tokens_used += estimate_tokens(prefs)

        # Section 2: Active task summaries
        tasks = await self._get_active_tasks(sender_hash, limit=5)
        task_content = self._format_tasks(tasks)
        sections.append(("Active Tasks", task_content))
        tokens_used += estimate_tokens(task_content)

        # Section 3: High-value insights (value_score > 0.8)
        if tokens_used < self.MAX_TOKENS * 0.8:
            remaining = self.MAX_TOKENS - tokens_used
            insights = await self._get_high_value_insights(
                sender_hash,
                max_tokens=remaining * 0.6
            )
            if insights:
                sections.append(("Key Insights", insights))
                tokens_used += estimate_tokens(insights)

        # Section 4: Recent context (minimal)
        if tokens_used < self.MAX_TOKENS * 0.9:
            remaining = self.MAX_TOKENS - tokens_used
            recent = await self._get_recent_summary(sender_hash, max_tokens=remaining)
            if recent:
                sections.append(("Recent Context", recent))

        # Write to file
        await self._write_memory_md(sections)

        # Update manifest
        await self._update_manifest(sender_hash, sections, tokens_used)

    async def _get_high_value_insights(self, sender_hash: str, max_tokens: int) -> str:
        """
        Query Neo4j for highest-value knowledge to include in file memory.
        """
        query = """
        MATCH (kc:KnowledgeChunk {sender_hash: $sender_hash})-[:HAS_VALUE]->(vc:ValueClassification)
        WHERE vc.value_score >= 0.8
        ORDER BY vc.value_score DESC, vc.last_accessed DESC
        RETURN kc.content as content,
               kc.token_count as tokens,
               vc.value_score as score
        """
        results = await self.neo4j.run(query, {"sender_hash": sender_hash})

        selected = []
        tokens_used = 0
        for row in results:
            if tokens_used + row["tokens"] > max_tokens:
                break
            selected.append(f"- {row['content']} (value: {row['score']:.2f})")
            tokens_used += row["tokens"]

        return "\n".join(selected)
```

### 3. Lazy Loading for Heartbeat

**Purpose**: Minimize session initialization cost.

```python
class LazyHeartbeatLoader:
    """
    Minimal heartbeat.md with lazy loading of full task definitions.
    """

    HEARTBEAT_MD_TEMPLATE = """# Heartbeat Task Registry
# This file contains minimal registry data. Full definitions in Neo4j.
# Last sync: {last_sync}
# Registry hash: {registry_hash}

## Quick Tasks (loaded at startup)
{quick_tasks}

## Deferred Tasks (loaded on-demand)
# Task IDs: {deferred_task_ids}
# Load from Neo4j when needed: MATCH (t:HeartbeatTask) WHERE t.id IN $ids

## Pending Changes
{pending_changes}
"""

    async def initialize_session(self) -> List[Dict]:
        """
        Load only quick tasks at session start.
        Returns list of tasks to execute immediately.
        """
        # Read minimal registry
        registry = self._parse_heartbeat_md()

        # Load only quick tasks (defined as < 100 tokens each)
        quick_tasks = await self._load_quick_tasks(registry["quick_task_ids"])

        # Schedule deferred tasks for lazy loading
        self._schedule_deferred_load(registry["deferred_task_ids"])

        return quick_tasks

    async def load_task_definition(self, task_id: str) -> Dict:
        """
        Lazy load full task definition from Neo4j.
        Called when task is due for execution.
        """
        query = """
        MATCH (t:HeartbeatTask {id: $task_id})
        RETURN t {
            .*,
            definition: apoc.convert.fromJsonMap(t.definition_json)
        } as task
        """
        result = await self.neo4j.run(query, {"task_id": task_id})

        if result:
            # Cache locally for this session
            self._cache_task_definition(task_id, result[0]["task"])
            return result[0]["task"]

        raise TaskNotFoundError(f"Task {task_id} not found in Neo4j")

    async def sync_to_neo4j(self):
        """
        Push heartbeat updates to Neo4j, keeping file minimal.
        Called after task execution or modification.
        """
        # Get all task updates
        updates = self._collect_task_updates()

        # Batch update Neo4j
        await self._batch_update_neo4j(updates)

        # Update registry hash in file
        new_hash = self._calculate_registry_hash(updates)
        await self._update_registry_hash(new_hash)
```

### 4. Multi-Signal Value Scoring

**Purpose**: Automatically determine what knowledge deserves file-based retention.

```python
class ValueScorer:
    """
    Calculate value_score for knowledge items using multiple signals.
    """

    # Signal weights (sum to 1.0)
    WEIGHTS = {
        "retention": 0.25,      # Likelihood of future need
        "uniqueness": 0.20,     # Novelty vs existing knowledge
        "confidence": 0.15,     # Source reliability
        "frequency": 0.25,      # Access frequency
        "recency": 0.15         # Time since last access
    }

    async def calculate_value_score(self, entity_id: str, entity_type: str) -> float:
        """
        Calculate composite value score for a knowledge entity.
        """
        signals = await self._collect_signals(entity_id, entity_type)

        # Calculate recency decay
        days_since_access = (datetime.now() - signals["last_accessed"]).days
        recency_score = max(0, 1 - (days_since_access / 30))  # Decay over 30 days

        # Normalize frequency (cap at 100 accesses)
        frequency_score = min(signals["access_count"], 100) / 100

        # Composite score
        value_score = (
            self.WEIGHTS["retention"] * signals["retention_likelihood"] +
            self.WEIGHTS["uniqueness"] * signals["uniqueness"] +
            self.WEIGHTS["confidence"] * signals["confidence"] +
            self.WEIGHTS["frequency"] * frequency_score +
            self.WEIGHTS["recency"] * recency_score
        )

        # Determine retention tier
        if value_score >= 0.8:
            tier = "KEEP"
        elif value_score >= 0.5:
            tier = "SUMMARIZE"
        else:
            tier = "ARCHIVE"

        # Store classification
        await self._store_classification(entity_id, entity_type, {
            "retention_score": signals["retention_likelihood"],
            "uniqueness_score": signals["uniqueness"],
            "confidence_score": signals["confidence"],
            "access_frequency": frequency_score,
            "value_score": value_score,
            "retention_tier": tier
        })

        return value_score
```

---

## Implementation Phases

### Phase 1: Foundation (Week 1)

1. **Create ValueClassification node and indexes**
2. **Implement `_enforce_retention_policy()` for file-based memory**
3. **Add `BoundedMemoryManifest` schema**

### Phase 2: Hierarchical Summarization (Week 2)

1. **Implement `HierarchicalSummarizer`**
2. **Extend CompressedContext with hierarchical links**
3. **Create compression pipeline for old conversations**

### Phase 3: Bounded Memory Manager (Week 3)

1. **Implement `BoundedMemoryManager`**
2. **Add token counting and budget enforcement**
3. **Create compaction scheduling (daily or on threshold)**

### Phase 4: Lazy Heartbeat (Week 4)

1. **Create `HeartbeatTaskRegistry` schema**
2. **Implement `LazyHeartbeatLoader`**
3. **Migrate existing heartbeat tasks to Neo4j**

---

## Migration Strategy

### From Unbounded MEMORY.md

```python
async def migrate_memory_to_neo4j(file_path: str, sender_hash: str):
    """
    One-time migration of existing MEMORY.md to Neo4j.
    """
    # Read existing file
    content = read_file(file_path)

    # Parse into segments
    segments = parse_memory_content(content)

    # Store each segment in Neo4j with value classification
    for segment in segments:
        # Store full content
        entity_id = await store_in_neo4j(segment)

        # Calculate initial value score
        await value_scorer.calculate_value_score(entity_id, segment["type"])

    # Build new bounded memory
    await bounded_memory_manager.compact_memory(sender_hash)

    # Archive old file
    archive_file(file_path, suffix=".pre-migration")
```

### From Existing Heartbeat.md

```python
async def migrate_heartbeat_to_neo4j(file_path: str):
    """
    Migrate heartbeat tasks to Neo4j registry.
    """
    # Parse existing tasks
    tasks = parse_heartbeat_md(file_path)

    # Categorize by size
    quick_tasks = [t for t in tasks if estimate_tokens(t) < 100]
    deferred_tasks = [t for t in tasks if estimate_tokens(t) >= 100]

    # Store in Neo4j
    for task in tasks:
        await store_task_in_neo4j(task)

    # Create minimal registry file
    registry = {
        "quick_task_ids": [t["id"] for t in quick_tasks],
        "deferred_task_ids": [t["id"] for t in deferred_tasks],
        "last_sync": datetime.now().isoformat()
    }

    write_heartbeat_md(registry)
```

---

## Monitoring and Metrics

### Key Metrics to Track

```cypher
// File-based memory efficiency
MATCH (m:BoundedMemoryManifest)
RETURN
    m.current_tokens as file_tokens,
    m.max_tokens as max_allowed,
    (m.current_tokens * 100.0 / m.max_tokens) as utilization_pct,
    m.last_compacted as last_compaction;

// Value classification distribution
MATCH (vc:ValueClassification)
RETURN
    vc.retention_tier as tier,
    count(*) as count,
    avg(vc.value_score) as avg_score;

// Neo4j vs File storage ratio
MATCH (kc:KnowledgeChunk)
WITH count(kc) as neo4j_count
MATCH (m:BoundedMemoryManifest)
RETURN
    neo4j_count as total_knowledge_items,
    size(m.high_value_insight_ids) as file_items,
    (neo4j_count * 100.0 / size(m.high_value_insight_ids)) as compression_ratio;

// Heartbeat lazy loading efficiency
MATCH (t:HeartbeatTask)
RETURN
    count(CASE WHEN t.last_definition_load IS NULL THEN 1 END) as never_loaded,
    count(CASE WHEN t.last_definition_load IS NOT NULL THEN 1 END) as loaded_at_least_once,
    avg(t.execution_count) as avg_executions;
```

---

## Summary

This architecture provides:

1. **Hard token limit**: MEMORY.md never exceeds 2,000 tokens
2. **Intelligent retention**: Value scoring keeps important knowledge accessible
3. **Hierarchical compression**: Full history in Neo4j, summaries in files
4. **Lazy loading**: Heartbeat initialization cost independent of task count
5. **Privacy preservation**: PII stays in file-based personal memory (Kublai only)

The key insight is treating file-based memory as a **cache** with Neo4j as the **source of truth**, rather than the primary storage mechanism. This enables unbounded operational history while maintaining bounded context windows.
