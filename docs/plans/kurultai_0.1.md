# Kurultai v0.1: Task Dependency Engine

> **Status**: Design Document
> **Date**: 2026-02-04
> **Author**: Kurultai System Architecture
> **Prerequisites**: [`neo4j.md`](./neo4j.md) - Must be implemented first

---

## Prerequisites

**This document is an ADD-ON to the core Neo4j implementation plan.**

Before implementing Kurultai v0.1, complete all phases from [`neo4j.md`](./neo4j.md):

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1 | Required | OpenClaw Multi-Agent Setup (6 agents, agentToAgent messaging) |
| Phase 2 | Required | Neo4j Infrastructure (database, indexes, constraints) |
| Phase 3 | Required | OperationalMemory Module (Task node, claim_task, etc.) |
| Phase 4 | Required | Agent Specialization (Temüjin, Jochi, Ögedei protocols) |

**What this document adds:**
- Task extensions for dependency tracking
- Intent window buffering and DAG building
- Topological executor for parallel task processing
- User priority override system
- Notion integration for external task management

**Integration Points:**
- Extends existing `:Task` node from neo4j.md with dependency fields
- Uses existing agentToAgent messaging for delegation
- Leverages existing OperationalMemory module for state management
- Builds on existing session isolation and sender_hash patterns

### Integration Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FROM neo4j.md (BASE)                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   6-Agent System         Neo4j Infrastructure        OperationalMemory       │
│   ┌──────────┐           ┌──────────────┐           ┌──────────────┐         │
│   │  Kublai  │──────────▶│   :Task      │◀──────────│  claim_task()│         │
│   │ (main)   │           │   :Agent     │           │  complete_   │         │
│   └──────────┘           │   indexes... │           │    task()    │         │
│      │  │                └──────────────┘           └──────────────┘         │
│      ▼  ▼                         │                                            │
│   Specialists                  agentToAgent                                   │
│                                                              │                │
└──────────────────────────────────────────────────────────────┼────────────────┘
                                                               │
                         ┌──────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    KURULTAI V0.1 (THIS DOC - ADDS)                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Intent Window         DAG Extensions             TopologicalExecutor        │
│   ┌──────────┐          ┌──────────────┐           ┌──────────────┐         │
│   │  Buffer  │──────────▶│ :DEPENDS_ON  │───────────│get_ready()   │         │
│   │(45 sec)  │          │  (extends    │           │execute_ready()│         │
│   └──────────┘          │   :Task)     │           └──────────────┘         │
│                          └──────────────┘                    │               │
│                                  │                            │               │
│   Priority Override    Notion Sync (optional)        Synthesis & Delivery      │
│   ┌──────────┐          ┌──────────────┐                    │               │
│   │Commands  │          │:SyncEvent    │                    │               │
│   │"Do X     │          │:SyncChange   │                    │               │
│   │before Y" │          │:UserConfig   │                    │               │
│   └──────────┘          └──────────────┘                    │               │
│                                                           │                   │
└───────────────────────────────────────────────────────────┼───────────────────┘
                                                            │
                                                            ▼
                                               PARALLEL TASK EXECUTION
```

---

## Executive Summary

Kurultai v0.1 introduces a **Task Dependency Engine** that enables Kublai (main agent) to intelligently batch, prioritize, and execute multiple user requests as a unified dependency graph. Rather than processing messages FIFO (first-in-first-out), Kublai builds a Directed Acyclic Graph (DAG) of tasks and executes them in topological order, maximizing parallel execution while respecting dependencies.

### Key Innovation

Users can send multiple rapid-fire messages. Kublai automatically detects:
- **Semantic relationships** between tasks (complementary, dependent, independent)
- **Optimal execution order** (what can run in parallel vs. sequential)
- **Delivery timing** (batch related outputs vs. stream independent results)

Users retain control via explicit priority commands (`"Priority: competitors first"`) that reweight the dependency graph in real-time.

---

## Problem Statement

### Current System Limitations

The Kurultai architecture defined in [`neo4j.md`](./neo4j.md) implements a 6-agent multi-agent system with Neo4j-backed operational memory. While this provides excellent task delegation and state management, it has a critical constraint:

```json
{
  "session": {
    "scope": "per-sender",
    "signalRouting": {
      "sessionIsolation": true
    }
  }
}
```

**Result**: Single-threaded session per sender. When a user sends:
1. "Earn 1,000 USDC" (t=0:00)
2. "Start Moltbook community" (t=0:03)
3. "Research competitors" (t=0:08)

The second and third messages queue while Kublai processes the first. This creates:
- **Session blocking**: Delayed response to legitimate parallel requests
- **Agent overload**: Specialists hit concurrent task limits (2 max)
- **Context confusion**: Related requests compete instead of synergizing
- **User friction**: Requires manual sequencing ("Wait for X before doing Y")

### Desired Behavior

Kublai should:
1. **Detect intent bursts** (messages arriving within 30-60 second windows)
2. **Analyze relationships** (semantic similarity, dependencies, conflicts)
3. **Build execution graph** (DAG with parallel/sequential edges)
4. **Execute optimally** (topological sort with priority weights)
5. **Deliver coherently** (synthesize related outputs, stream independent ones)

---

## Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        TASK DEPENDENCY ENGINE                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   User Messages          Intent Window         DAG Builder                  │
│        │                      │                     │                        │
│        ▼                      ▼                     ▼                        │
│   ┌─────────┐    ┌─────────────────────┐    ┌────────────┐                  │
│   │ Message │───►│ Buffer (30-60 sec)  │───►│  Analyzer  │                  │
│   │   Queue │    │                     │    │  (Kublai)  │                  │
│   └─────────┘    └─────────────────────┘    └─────┬──────┘                  │
│                                                    │                         │
│                                                    ▼                         │
│   ┌──────────────────────────────────────────────────────────────┐          │
│   │                     TASK DAG (Neo4j)                         │          │
│   │                                                              │          │
│   │  (:Task)-[:BLOCKS]->(:Task)      Sequential dependency      │          │
│   │  (:Task)-[:FEEDS_INTO]->(:Task)  Information flow           │          │
│   │  (:Task)-[:PARALLEL_OK]->(:Task) Concurrent execution       │          │
│   │                                                              │          │
│   └──────────────────────┬───────────────────────────────────────┘          │
│                          │                                                   │
│                          ▼                                                   │
│   ┌──────────────────────────────────────────────────────────────┐          │
│   │                 TOPOLOGICAL EXECUTOR                         │          │
│   │                                                              │          │
│   │  1. Calculate ready set (no unmet BLOCKS edges)              │          │
│   │  2. Sort by priority_weight (user override > similarity)     │          │
│   │  3. Dispatch to agents (respecting 2-task limit)             │          │
│   │  4. Monitor completion, update DAG status                    │          │
│   │  5. Repeat until all tasks completed                         │          │
│   │                                                              │          │
│   └──────────────────────┬───────────────────────────────────────┘          │
│                          │                                                   │
│                          ▼                                                   │
│   ┌──────────────────────────────────────────────────────────────┐          │
│   │                SYNTHESIS & DELIVERY                          │          │
│   │                                                              │          │
│   │  • Related tasks → Single unified response                   │          │
│   │  • Independent tasks → Stream as completed                   │          │
│   │  • User notification: "Working on 3 related tasks..."        │          │
│   │                                                              │          │
│   └──────────────────────────────────────────────────────────────┘          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Neo4j Schema Extensions

> **Note**: This section EXTENDS the existing Neo4j schema from [`neo4j.md`](./neo4j.md). The base `:Task` node and all related infrastructure (agents, indexes, constraints) are already defined there.

### Extension: Task for Dependency Tracking

The existing `:Task` node from [`neo4j.md`](./neo4j.md) provides the foundation:

```cypher
// From neo4j.md - existing Task node
(:Task {
  type,
  description,
  status,  // "pending" | "in_progress" | "completed" | "blocked" | "escalated"
  assigned_to,
  claimed_by,
  delegated_by,
  // ... other fields from neo4j.md
})
```

**Kurultai v0.1 adds the following fields to Task:**

```cypher
// EXTEND the existing :Task node with these fields
(:Task {
  // ... existing fields from neo4j.md ...

  // ==== KURULTAI V0.1 ADDITIONS ====

  // Intent window buffering
  window_expires_at: datetime,   // 30-60 sec from creation

  // Semantic analysis
  embedding: [float],            // 384-dim vector for similarity comparison
  deliverable_type: string,      // "research" | "code" | "analysis" | "content" | "strategy" | "ops"

  // Priority control
  priority_weight: float,        // 0.0-1.0 (default: 0.5)
  user_priority_override: boolean,

  // Merge tracking
  merged_into: uuid,             // If deduplicated, points to canonical task
  merged_from: [uuid],           // Tasks that were merged into this one

  // Notion sync (optional feature)
  notion_synced_at: datetime,
  notion_page_id: string,
  notion_url: string,
  external_priority_source: string,  // "notion" | "user" | "auto"
  external_priority_weight: float
})
```

### New Relationship: DEPENDS_ON

```cypher
(:Task)-[:DEPENDS_ON {
  // Identity
  id: uuid,
  sender_hash: string,           // HMAC-SHA256 of sender phone

  // Content
  description: string,           // Original user message
  embedding: [float],            // 384-dim vector for semantic comparison

  // State machine
  status: string,                // "pending" | "blocked" | "ready" |
                                 // "in_progress" | "completed" | "aborted"

  // Execution
  priority_weight: float,        // 0.0-1.0 (default: 0.5)
  estimated_duration: int,       // minutes (default: 15)
  required_agents: [string],     // ["analyst", "researcher"]

  // Classification
  deliverable_type: string,      // "research" | "code" | "analysis" |
                                 // "content" | "strategy" | "ops"

  // Timing
  created_at: datetime,
  window_expires_at: datetime,   // 30-60 sec from creation
  started_at: datetime,
  completed_at: datetime,

  // Results
  result_summary: string,        // Truncated for quick reference
  result_node_ids: [uuid],       // Linked Research/Analysis/etc nodes

  // Merge tracking
  merged_into: uuid,             // If deduplicated, points to canonical task
  merged_from: [uuid]            // Tasks that were merged into this one
})
```

#### Dependency (Relationship)

```cypher
(:Task)-[:DEPENDS_ON {
  type: string,                  // "blocks" | "feeds_into" | "parallel_ok"
  weight: float,                 // 0.0-1.0 strength of dependency
  detected_by: string,           // "semantic" | "explicit" | "inferred"
  confidence: float              // 0.0-1.0 detection confidence
}]->(:Task)
```

**Dependency Types:**

| Type | Direction | Meaning | Example |
|------|-----------|---------|---------|
| `blocks` | A → B | A must complete before B starts | Research → Strategy |
| `feeds_into` | A → B | A's output informs B | Competitor analysis → Positioning |
| `parallel_ok` | A ↔ B | No dependency, can run concurrently | USDC earning + Research |

### Indexes

> **Note**: Core indexes are already defined in [`neo4j.md`](./neo4j.md) (task_status, task_claim_lock, notification_read, etc.). These are NEW indexes for v0.1 features.

```cypher
// === KURULTAI V0.1 ADDITIONS ===

// Semantic similarity search (uses existing vector index infrastructure)
CREATE INDEX task_embedding FOR (t:Task) ON (t.embedding)
  OPTIONS {indexConfig: {`vector.dimensions`: 384, `vector.similarity_function`: 'cosine'}};

// Intent window queries (cleanup and batch processing)
CREATE INDEX task_window FOR (t:Task) ON (t.window_expires_at);

// Sync audit trail lookups
CREATE INDEX sync_event_sender FOR (s:SyncEvent) ON (s.sender_hash, s.triggered_at);
CREATE INDEX sync_change_task FOR (c:SyncChange) ON (c.task_id);
```

---

## Dependency Detection Algorithm

> **Note**: The Python code below extends the existing OperationalMemory module from [`neo4j.md`](./neo4j.md). Type hints like `Task` refer to the Neo4j `:Task` node, not a separate class.

### Step 1: Intent Window Buffering

```python
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

class IntentWindowBuffer:
    """Collects messages within time window before DAG building."""

    def __init__(self, window_seconds: int = 45):
        self.window = window_seconds
        self.pending: List[Message] = []

    def add(self, message: Message) -> Optional[List[Message]]:
        """
        Add message to buffer. Returns full batch if window expired.
        """
        self.pending.append(message)

        if not self.pending:
            return None

        oldest = min(m.timestamp for m in self.pending)
        if (now() - oldest).seconds >= self.window:
            batch = self.pending.copy()
            self.pending.clear()
            return batch

        return None  # Still collecting
```

### Step 2: Semantic Similarity Analysis

```python
async def analyze_dependencies(tasks: List[Task]) -> List[Dependency]:
    """
    Compare task embeddings to detect relationships.
    """
    dependencies = []

    for i, task_a in enumerate(tasks):
        for task_b in tasks[i+1:]:
            similarity = cosine_similarity(
                task_a.embedding,
                task_b.embedding
            )

            # High similarity = likely related (parallel or sequential)
            if similarity > 0.75:
                dep_type = determine_dependency_type(task_a, task_b)
                dependencies.append(Dependency(
                    from_task=task_a.id,
                    to_task=task_b.id,
                    type=dep_type,
                    weight=similarity,
                    detected_by="semantic",
                    confidence=similarity
                ))

            # Medium similarity = might be parallel
            elif similarity > 0.55:
                dependencies.append(Dependency(
                    from_task=task_a.id,
                    to_task=task_b.id,
                    type="parallel_ok",
                    weight=similarity,
                    detected_by="semantic",
                    confidence=similarity
                ))

    return dependencies

def determine_dependency_type(a: Task, b: Task) -> str:
    """
    Infer dependency direction based on deliverable types.
    """
    # Research feeds into strategy
    if a.deliverable_type == "research" and b.deliverable_type == "strategy":
        return "feeds_into"

    # Analysis blocks implementation
    if a.deliverable_type == "analysis" and b.deliverable_type == "code":
        return "blocks"

    # Default: parallel is safe
    return "parallel_ok"
```

### Step 3: Topological Sort with Priority

```python
class TopologicalExecutor:
    """Executes tasks in dependency order, respecting priorities."""

    def __init__(self, neo4j_client):
        self.neo4j = neo4j_client

    async def get_ready_tasks(self, sender_hash: str) -> List[Task]:
        """
        Find tasks with no unmet BLOCKS dependencies.
        """
        query = """
        MATCH (t:Task {sender_hash: $sender_hash, status: "pending"})
        WHERE NOT EXISTS {
            // Check for uncompleted blocking dependencies
            MATCH (t)<-[:DEPENDS_ON {type: "blocks"}]-(blocker:Task)
            WHERE blocker.status != "completed"
        }
        RETURN t
        ORDER BY t.priority_weight DESC, t.created_at ASC
        """
        return await self.neo4j.run(query, {"sender_hash": sender_hash})

    async def execute_ready_set(self, sender_hash: str):
        """
        Dispatch all ready tasks to appropriate agents.
        """
        ready = await self.get_ready_tasks(sender_hash)

        # Group by required agent type
        by_agent = defaultdict(list)
        for task in ready:
            agent = select_best_agent(task)
            by_agent[agent].append(task)

        # Dispatch to agents (respecting 2-task limit)
        for agent_id, tasks in by_agent.items():
            available_slots = 2 - await get_current_load(agent_id)

            for task in tasks[:available_slots]:
                await self.dispatch_to_agent(task, agent_id)

    def select_best_agent(self, task: Task) -> str:
        """
        Route task to appropriate specialist.
        """
        routing = {
            "research": "researcher",
            "analysis": "analyst",
            "code": "developer",
            "content": "writer",
            "ops": "ops",
            "strategy": "analyst"  # Jochi for strategic analysis
        }
        return routing.get(task.deliverable_type, "analyst")
```

---

## User Priority Override System

### Natural Language Priority Commands

Users can reprioritize at any time:

| Command | Effect |
|---------|--------|
| `"Priority: competitors first"` | Sets Task X priority_weight = 1.0, recalculates order |
| `"Do X before Y"` | Creates explicit BLOCKS edge: X → Y |
| `"These are independent"` | Creates PARALLEL_OK edges between all recent tasks |
| `"Focus on X, pause others"` | Sets non-X tasks status = "paused", X = 1.0 |
| `"What's the plan?"` | Kublai explains current DAG state |
| `"Sync from Notion"` | Pulls priority/status changes from Notion database |
| `"Notion sync"` | Alias for "Sync from Notion" |

### Implementation

```python
class PriorityCommandHandler:
    """Parses natural language priority commands."""

    async def handle(self, message: str, sender_hash: str) -> str:
        """
        Detect priority commands, update DAG, return confirmation.
        """
        # Parse with LLM or regex patterns
        if match := re.search(r"priority:\s*(.+)", message, re.I):
            target = match.group(1).strip()
            return await self.set_priority(target, sender_hash)

        if match := re.search(r"do\s+(.+?)\s+before\s+(.+)", message, re.I):
            first, second = match.groups()
            return await self.create_explicit_dependency(first, second, sender_hash)

        if "what's the plan" in message.lower():
            return await self.explain_dag(sender_hash)

        return None  # Not a command, treat as normal message

    async def set_priority(self, target: str, sender_hash: str) -> str:
        """
        Find matching task, boost priority, recalculate.
        """
        # Semantic search for matching task
        task = await self.find_task_by_description(target, sender_hash)

        if not task:
            return f"Couldn't find task matching '{target}'. Current tasks: [...]"

        # Boost priority
        await self.neo4j.run("""
            MATCH (t:Task {id: $task_id})
            SET t.priority_weight = 1.0,
                t.user_priority_override = true
        """, {"task_id": task.id})

        # Recalculate execution order
        new_order = await self.recalculate_order(sender_hash)

        return f"""
Priority updated. '{task.description[:50]}...' is now first.

New execution order:
{self.format_order(new_order)}

Estimated completion: {self.estimate_total_time(new_order)} minutes.
        """.strip()
```

---

## Notion Integration: External Priority Source

### Overview

Kublai supports **Notion as an external priority control plane**, allowing users to reprioritize tasks in Notion and sync changes on demand. This implements Option A (Command-Based Sync):

- **User edits tasks in Notion** → Changes priority, status, or dependencies
- **User triggers sync** → Sends "Sync from Notion" command
- **Kublai reconciles** → Applies changes intelligently without breaking ongoing work
- **Confirmation** → Kublai reports what changed and why

### Notion Database Schema

#### Required Properties

| Property | Type | Description | Mapping to Task |
|----------|------|-------------|---------------------|
| `Name` | Title | Task description | `description` |
| `Status` | Select | Task state | `status` |
| `Priority` | Select | Weight/urgency | `priority_weight` |
| `Agent` | Select | Assigned agent | `required_agents` |
| `ID` | Text (unique) | Kurultai task UUID | `id` |
| `Last Synced` | Date | Sync timestamp | `notion_synced_at` |

#### Status Values (Must Match)

```
Notion Status → Task.status
├── "Not Started" → "pending"
├── "Blocked" → "blocked"
├── "Ready" → "ready"
├── "In Progress" → "in_progress"
├── "Completed" → "completed"
└── "Cancelled" → "aborted"
```

#### Priority Values (Mapping)

```
Notion Priority → priority_weight
├── "Critical" → 1.0
├── "High" → 0.8
├── "Medium" → 0.5 (default)
├── "Low" → 0.3
└── "Backlog" → 0.1
```

### Sync Command

```python
class NotionSyncHandler(PriorityCommandHandler):
    """Handles Notion sync commands."""

    async def handle(self, message: str, sender_hash: str) -> Optional[str]:
        """
        Detect and handle Notion sync commands.
        """
        # Sync command variations
        sync_patterns = [
            r"sync\s+(from\s+)?notion",
            r"notion\s+sync",
            r"pull\s+from\s+notion",
            r"update\s+from\s+notion",
        ]

        for pattern in sync_patterns:
            if re.search(pattern, message, re.I):
                return await self.sync_from_notion(sender_hash)

        return await super().handle(message, sender_hash)

    async def sync_from_notion(self, sender_hash: str) -> str:
        """
        Pull task updates from Notion and reconcile with Neo4j DAG.
        """
        # 1. Fetch from Notion
        notion_tasks = await self.fetch_notion_tasks(sender_hash)

        # 2. Fetch from Neo4j
        neo4j_tasks = await self.fetch_neo4j_tasks(sender_hash)

        # 3. Reconcile
        changes = await self.reconcile(notion_tasks, neo4j_tasks)

        # 4. Apply safe changes
        applied = await self.apply_safe_changes(changes, sender_hash)

        return self.format_sync_result(applied)
```

### Reconciliation Algorithm (Safe by Default)

The key constraint: **don't break ongoing work**. The reconciliation engine respects:

1. **In-progress tasks**: Never interrupt. Ignore Notion status changes for `in_progress` tasks.
2. **Completed tasks**: Never revert. Ignore Notion changes to `completed` tasks.
3. **Strong dependencies**: Respect DAG structure. Don't enable a task if its BLOCKS dependencies aren't met.
4. **Priority boosts**: Always apply. Safe to change priority_weight at any time.

```python
class ReconciliationEngine:
    """Intelligently merges Notion changes with Neo4j state."""

    async def reconcile(
        self,
        notion_tasks: List[NotionTask],
        neo4j_tasks: List[Task]
    ) -> List[Change]:
        """
        Compute safe changes to apply.
        """
        changes = []

        # Index by ID for O(1) lookup
        notion_by_id = {t.id: t for t in notion_tasks}
        neo4j_by_id = {t.id: t for t in neo4j_tasks}

        # Tasks in Notion but not Neo4j → CREATE
        for notion_task in notion_tasks:
            if notion_task.id not in neo4j_by_id:
                changes.append(Change(
                    type="create",
                    task_id=notion_task.id,
                    notion=notion_task,
                    safe=True  # New tasks are always safe
                ))

        # Tasks in both → COMPARE
        for task_id in set(notion_by_id) & set(neo4j_by_id):
            notion = notion_by_id[task_id]
            neo4j = neo4j_by_id[task_id]

            # Rule 1: Never touch in-progress tasks
            if neo4j.status == "in_progress":
                continue

            # Rule 2: Never revert completed tasks
            if neo4j.status == "completed":
                continue

            # Check priority change (always safe)
            if notion.priority_weight != neo4j.priority_weight:
                changes.append(Change(
                    type="priority",
                    task_id=task_id,
                    old_value=neo4j.priority_weight,
                    new_value=notion.priority_weight,
                    safe=True
                ))

            # Check status change (conditional)
            if notion.status != neo4j.status:
                # Validate: can we transition to this status?
                if self.can_transition(neo4j.status, notion.status):
                    changes.append(Change(
                        type="status",
                        task_id=task_id,
                        old_value=neo4j.status,
                        new_value=notion.status,
                        safe=True
                    ))

        # Tasks in Neo4j but not Notion → ASK
        for neo4j_task in neo4j_tasks:
            if neo4j_task.id not in notion_by_id:
                # Don't delete; flag for attention
                changes.append(Change(
                    type="missing_in_notion",
                    task_id=neo4j_task.id,
                    safe=False,
                    message=f"Task '{neo4j_task.description[:50]}' exists in Kurultai "
                           f"but not in Notion. Not deleted; please add to Notion or cancel here."
                ))

        return changes

    def can_transition(self, from_status: str, to_status: str) -> bool:
        """
        Validate status transition respects DAG constraints.
        """
        # Safe transitions
        safe_transitions = {
            "pending": ["blocked", "ready", "aborted"],
            "blocked": ["pending", "aborted"],
            "ready": ["in_progress", "aborted"],
            "aborted": ["pending"],  # Allow retry
        }

        return to_status in safe_transitions.get(from_status, [])
```

### Notion Sync Schema (NEW nodes for v0.1)

#### Sync Audit Trail

These are NEW node types for Notion sync functionality:

```cypher
(:SyncEvent {
  id: uuid,
  sender_hash: string,
  sync_type: string,                // "notion" | "manual"
  triggered_at: datetime,
  completed_at: datetime,
  changes_applied: int,             // Count of successful changes
  changes_skipped: int,             // Count of skipped changes
  changes_failed: int,              // Count of failed changes
  status: string                    // "success" | "partial" | "failed"
})

(:SyncChange {
  id: uuid,
  sync_event_id: uuid,              // -> (:SyncEvent)
  task_id: uuid,                    // -> (:Task)
  change_type: string,              // "create" | "priority" | "status" | "blocked"
  old_value: string,
  new_value: string,
  applied: boolean,
  reason: string                    // Why skipped/failed
})

(:SyncEvent)-[:CONTAINS_CHANGE]->(:SyncChange)
(:SyncChange)-[:AFFECTS]->(:Task)
```

### Per-User Configuration (NEW node for v0.1)

```cypher
(:UserConfig {
  sender_hash: string,
  notion_integration_enabled: boolean,
  notion_database_id: string,
  notion_poll_enabled: boolean,         # Opt-in to continuous polling
  notion_poll_interval: int,            # Override default interval
  notion_notify_on_change: boolean,     # Send Signal notifications
  sync_preference: string                # "safe" | "aggressive"
})
```
  // ... existing fields ...

  // Notion sync fields
  notion_synced_at: datetime,       // Last successful sync
  notion_page_id: string,           // Notion page URL ID
  notion_url: string,               // Full URL for user reference
  external_priority_source: string,  // "notion" | "user" | "auto"
  external_priority_weight: float,   // Priority from external source
})
```

#### Sync Audit Trail

```cypher
(:SyncEvent {
  id: uuid,
  sender_hash: string,
  sync_type: string,                // "notion" | "manual"
  triggered_at: datetime,
  completed_at: datetime,
  changes_applied: int,             // Count of successful changes
  changes_skipped: int,             // Count of skipped changes
  changes_failed: int,              // Count of failed changes
  status: string                    // "success" | "partial" | "failed"
})

(:SyncChange {
  id: uuid,
  sync_event_id: uuid,              // -> (:SyncEvent)
  task_id: uuid,                    // -> (:Task)
  change_type: string,              // "create" | "priority" | "status" | "blocked"
  old_value: string,
  new_value: string,
  applied: boolean,
  reason: string                    // Why skipped/failed
})

(:SyncEvent)-[:CONTAINS_CHANGE]->(:SyncChange)
(:SyncChange)-[:AFFECTS]->(:Task)
```

### Notion API Client

```python
class NotionTaskClient:
    """Client for reading tasks from Notion database."""

    def __init__(self, api_key: str, database_id: str):
        self.api_key = api_key
        self.database_id = database_id
        self.base_url = "https://api.notion.com/v1"

    async def fetch_tasks(self, sender_hash: str) -> List[NotionTask]:
        """
        Fetch all tasks for user from Notion database.
        Filters by sender_hash property (stored as hidden column).
        """
        query = {
            "filter": {
                "property": "SenderHash",
                "rich_text": {"equals": sender_hash}
            }
        }

        response = await self._post(
            f"/databases/{self.database_id}/query",
            query
        )

        return [self._parse_task(row) for row in response["results"]]

    def _parse_task(self, row: dict) -> NotionTask:
        """Parse Notion page into Task-compatible format."""
        props = row["properties"]

        return NotionTask(
            id=props["ID"]["title"][0]["plain_text"],
            description=props["Name"]["title"][0]["plain_text"],
            status=self._map_status(props["Status"]["select"]["name"]),
            priority_weight=self._map_priority(
                props["Priority"]["select"]["name"]
            ),
            required_agents=self._map_agents(
                props["Agent"]["multi_select"]
            ),
            notion_url=row["url"],
            notion_page_id=row["id"]
        )

    def _map_priority(self, notion_priority: str) -> float:
        """Map Notion priority to weight."""
        mapping = {
            "Critical": 1.0,
            "High": 0.8,
            "Medium": 0.5,
            "Low": 0.3,
            "Backlog": 0.1
        }
        return mapping.get(notion_priority, 0.5)
```

### Sync Result Format

```python
def format_sync_result(self, applied: List[Change]) -> str:
    """
    Format sync results for user message.
    """
    created = [c for c in applied if c.type == "create"]
    updated = [c for c in applied if c.type in ["priority", "status"]]
    skipped = [c for c in applied if not c.safe]

    result = ["**Sync from Notion complete**\n"]

    if created:
        result.append(f"✅ **{len(created)} new tasks created:**")
        for change in created:
            result.append(f"  • {change.notion.description[:50]}")

    if updated:
        result.append(f"\n✅ **{len(updated)} tasks updated:**")
        for change in updated:
            if change.type == "priority":
                result.append(
                    f"  • Priority: {change.old_value} → {change.new_value} "
                    f"({change.task_id[:8]}...)"
                )
            else:
                result.append(
                    f"  • Status: {change.old_value} → {change.new_value}"
                )

    if skipped:
        result.append(f"\n⚠️ **{len(skipped)} changes skipped** (safety rules):")
        for change in skipped:
            result.append(f"  • {change.message}")

    # Estimated completion
    result.append(f"\n📊 **Estimated completion:** {self.estimate_completion()} minutes")

    return "\n".join(result)
```

### Configuration

```python
# Environment variables
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
NOTION_SYNC_ENABLED = os.getenv("NOTION_SYNC_ENABLED", "true").lower() == "true"

# Polling configuration
NOTION_POLL_ENABLED = os.getenv("NOTION_POLL_ENABLED", "true").lower() == "true"
NOTION_POLL_INTERVAL_SECONDS = int(os.getenv("NOTION_POLL_INTERVAL", "60"))

# Per-user configuration (stored in Neo4j)
CREATE (:UserConfig {
  sender_hash: string,
  notion_integration_enabled: boolean,
  notion_database_id: string,
  notion_poll_enabled: boolean,         # Opt-in to continuous polling
  notion_poll_interval: int,            # Override default interval
  notion_notify_on_change: boolean,     # Send Signal notifications
  sync_preference: string                # "safe" | "aggressive"
})
```

---

## Ögedei's Continuous Notion Polling

**Ögedei polls Notion continuously for ALL changes**, not just when triggered by command. Changes detected via Notion's `last_edited_time` timestamp.

### Data Models

```python
@dataclass
class NotionTask:
    """Task representation from Notion with change detection."""
    id: str                              # UUID
    description: str                     # Title
    status: TaskStatus                   # Current status
    priority_weight: float               # 0.0-1.0
    required_agents: List[str]           # Assigned specialists
    deliverable_type: str                # research|code|analysis|etc
    estimated_duration: int              # Minutes
    last_edited_time: datetime           # For change detection
    notion_url: str                      # Full URL
    notion_page_id: str                  # Notion page ID
    sender_hash: str                     # User identifier


class NotionChangeType(Enum):
    """Types of changes detected in Notion."""
    NEW_TASK = "new_task"              # Task created in Notion, not in Neo4j
    PRIORITY = "priority"              # Priority changed
    STATUS = "status"                  # Status (column) changed
    AGENT = "agent"                    # Assigned agent changed
    DESCRIPTION = "description"        # Title/description changed
    DELETED = "deleted"                # Task removed from Notion
    PROPERTIES = "properties"          # Other properties changed


@dataclass
class NotionChange:
    """A detected change from Notion."""
    type: NotionChangeType
    task_id: str
    priority: str                       # critical|high|medium|low
    message: str = ""

    # Change data
    old_value: Any = None
    new_value: Any = None
    notion_task: Optional[NotionTask] = None
    neo4j_task: Optional[Task] = None

    # Processing metadata
    skip_reason: str = ""
    error: str = ""
```

### Polling Engine

```python
class NotionPollingEngine:
    """
    Ögedei's continuous polling engine for Notion changes.

    Runs every N seconds (configurable, default: 60s).
    Detects ALL changes using Notion's last_edited_time.
    Applies changes safely using ReconciliationEngine.
    """

    def __init__(
        self,
        notion_client: NotionClient,
        neo4j_client,
        poll_interval_seconds: int = 60
    ):
        self.notion = notion_client
        self.neo4j = neo4j_client
        self.poll_interval = poll_interval_seconds
        self.reconciler = ReconciliationEngine(neo4j_client)

        # Track last sync time per user
        self.last_sync: Dict[str, datetime] = {}

        # Track seen task IDs (for deletion detection)
        self.seen_task_ids: Dict[str, Set[str]] = {}

        self._running = False
        self._scheduler: Optional[BackgroundScheduler] = None

    def start(self):
        """Start background polling."""
        if self._running:
            return

        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            self._scheduler = BackgroundScheduler()
            self._scheduler.add_job(
                self._poll_all_users,
                'interval',
                seconds=self.poll_interval,
                id='notion_poll'
            )
            self._scheduler.start()
            self._running = True
            print(f"[Ögedei] Notion polling started (interval: {self.poll_interval}s)")
        except ImportError:
            print("[WARN] APScheduler not available. Polling disabled.")
            print("[INFO] Use cron or manual sync as fallback.")

    def stop(self):
        """Stop background polling."""
        if self._scheduler:
            self._scheduler.shutdown()
            self._running = False
            print("[Ögedei] Notion polling stopped")

    async def _poll_user(self, sender_hash: str):
        """
        Poll Notion for a single user, detect all changes.

        Change Detection Strategy:
        1. Fetch all tasks from Notion
        2. Compare last_edited_time against last_sync time
        3. Detect deletions by comparing with seen_task_ids
        4. Reconcile changes using safe rules
        5. Apply changes and log results
        """
        last_sync = self.last_sync.get(sender_hash, datetime.min)

        # 1. Fetch all tasks from Notion
        notion_tasks = await self.notion.fetch_tasks(sender_hash)

        # 2. Detect changes by last_edited_time
        changed_tasks = [
            t for t in notion_tasks
            if t.last_edited_time > last_sync
        ]

        # 3. Detect new tasks (no matching Neo4j task)
        neo4j_task_ids = await self.neo4j.get_task_ids_for_sender(sender_hash)
        new_tasks = [
            t for t in notion_tasks
            if t.id not in neo4j_task_ids
        ]

        # 4. Detect deletions (in seen but not in current fetch)
        previously_seen = self.seen_task_ids.get(sender_hash, set())
        current_ids = {t.id for t in notion_tasks}
        deleted_ids = previously_seen - current_ids

        # 5. Reconcile and apply changes
        changes = await self._detect_all_changes(
            notion_tasks,
            changed_tasks,
            new_tasks,
            deleted_ids,
            sender_hash
        )

        if changes:
            result = await self._apply_changes(changes, sender_hash)
            await self._notify_user(result, sender_hash)

        # 6. Update tracking
        self.last_sync[sender_hash] = datetime.now(timezone.utc)
        self.seen_task_ids[sender_hash] = current_ids
```

### Change Detection

The polling engine detects **ALL types of changes**:

| Change Type | Priority | Action |
|-------------|----------|--------|
| `NEW_TASK` | Critical | Send to Kublai for review |
| `DELETED` | High | Archive in Neo4j (soft delete) |
| `STATUS` | High | Apply if safe (respect in-progress/completed rules) |
| `PRIORITY` | Medium | Always apply |
| `AGENT` | Low | Reassign if not in-progress |
| `DESCRIPTION` | Low | Update task description |

### Example User Flow

**Command mode:**
```
USER (in Notion):
1. Opens Kurultai Tasks database
2. Changes "Competitor research" priority from Medium to Critical
3. Sends message to Kublai: "Sync from Notion"

KUBLAI:
✅ **Sync from Notion complete**

✅ **1 task updated:**
  • Priority: 0.5 → 1.0 (Competitor research)
```

**Polling mode:**
```
USER (in Notion):
1. Changes "Competitor research" priority to Critical
2. Waits ~60 seconds (or configured interval)

ÖGEDEI (background):
✅ **Notion sync complete**

✅ **1 change applied:**
  • Priority: 0.5 → 1.0 (Competitor research)
```

**Full example with multiple changes:**
```
USER (in Notion):
1. Opens Kurultai Tasks database
2. Changes "Competitor research" priority from Medium to Critical
3. Adds new task: "Create Moltbook landing page" (High priority)
4. Sends "Sync from Notion" (or waits for polling)

RESULT:
✅ **Sync complete**

✅ **2 tasks updated:**
  • Priority: 0.5 → 1.0 (Competitor research)
  • Status: pending → ready (Create Moltbook landing page)

⚠️ **1 change skipped** (safety rules):
  • Task "USDC earning plan" exists in Kurultai but not in Notion.

📊 **Estimated completion:** 12 minutes

New execution order:
1. Competitor research (Critical) → Jochi
2. Create Moltbook landing page (High) → Temüjin
3. USDC earning plan (Medium) → Jochi
```

### Security Considerations

1. **API Key Storage**: Never log Notion API keys; use environment variables
2. **Sender Hash Validation**: Only sync tasks matching sender_hash
3. **Rate Limiting**: Respect Notion API rate limits (3 requests/second)
4. **Permission Checks**: Verify user has read access to database before sync
5. **Audit Trail**: All sync changes logged to SyncEvent nodes

---

## Synthesis & Delivery Modes

### Mode 1: Unified Delivery (Related Tasks)

When tasks have `feeds_into` or high-similarity `parallel_ok` relationships:

```
KUBLAI: "I've analyzed your three requests. They're part of the same
strategic initiative—community monetization. Here's the unified plan:

PHASE 1 (Research - Jochi & Möngke working):
• Competitor landscape: 3 similar communities, gap in AI focus
• USDC earning paths: Freelance ($1k in 2-3 days) vs Community ($2k/mo ongoing)

PHASE 2 (Strategy - Chagatai & Temüjin):
• Positioning: "AI Financial Liberation" community
• Platform: Moltbook with custom integrations

PHASE 3 (Execution - Ögedei monitoring):
• Launch timeline: 2 weeks to MVP
• Revenue projection: $2,000/month by month 3

Recommended: Proceed with community strategy (higher long-term value).
Alternative: Quick freelance win first ($1k in 3 days), then community.

Which path would you prefer?"
```

### Mode 2: Streaming Delivery (Independent Tasks)

When tasks are `parallel_ok` with low similarity:

```
[Message 1 arrives, Task A created]
KUBLAI: "Working on 3 tasks. First result in ~5 minutes..."

[Task B completes first]
KUBLAI: "Task 2 complete: Competitor research shows 3 players...
[full result]

Tasks 1 and 3 still in progress."

[Task A completes]
KUBLAI: "Task 1 complete: USDC earning paths identified...
[full result]

Task 3 completing soon..."
```

### Mode 3: Hybrid (Mixed Dependencies)

```
KUBLAI: "Working on your requests. Here's the plan:

READY NOW (Independent):
• Competitor research → [result stream]

SEQUENTIAL (Depends on above):
• Community strategy → [pending: needs research]
• USDC earning plan → [pending: needs research]

Estimated: Full plan in 10 minutes."
```

---

## Implementation Phases

> **Prerequisite**: All phases from [`neo4j.md`](./neo4j.md) must be completed before starting Phase 1 below.

### Phase 1: Core DAG (Week 1)

**Goal**: Basic task dependency graph with topological execution

- [ ] **Migration 1.1**: Extend `:Task` node with v0.1 fields (embedding, deliverable_type, priority_weight, window_expires_at)
- [ ] **Migration 1.2**: Create `DEPENDS_ON` relationship type
- [ ] **Feature 1.3**: Intent window buffering (45-second default)
- [ ] **Feature 1.4**: Basic topological executor (uses existing claim_task from OperationalMemory)
- [ ] **Feature 1.5**: Unified delivery for related tasks

**Dependencies**: Phase 3 from neo4j.md (OperationalMemory module)

### Phase 2: Smart Detection (Week 2)

**Goal**: Semantic analysis for automatic dependency detection

- [ ] **Feature 2.1**: Semantic similarity using embedding vectors
- [ ] **Feature 2.2**: Deliverable type inference (LLM-based classifier)
- [ ] **Feature 2.3**: Automatic dependency type classification
- [ ] **Feature 2.4**: Streaming delivery for independent tasks

**Dependencies**: Phase 1 from this document

### Phase 3: User Control (Week 3)

**Goal**: Natural language priority override system

- [ ] **Feature 3.1**: Priority command parsing (regex + LLM fallback)
- [ ] **Feature 3.2**: Explicit dependency creation (`"Do X before Y"`)
- [ ] **Feature 3.3**: DAG visualization (`"What's the plan?"`)
- [ ] **Feature 3.4**: Pause/resume task control

**Dependencies**: Phase 2 from this document

### Phase 4: Notion Integration (Week 4)

**Goal**: External task management via Notion

- [ ] **Feature 4.1**: Notion API client (fetch tasks, sync)
- [ ] **Feature 4.2**: Reconciliation engine (safe merge logic)
- [ ] **Feature 4.3**: Sync command handling
- [ ] **Feature 4.4**: Ögedei's continuous polling (optional, opt-in)

**Dependencies**: Phase 3 from this document

### Phase 5: Optimization (Week 5)

**Goal**: Performance tuning and advanced features

- [ ] **Feature 5.1**: Agent load balancing
- [ ] **Feature 5.2**: Dynamic window adjustment (based on user behavior)
- [ ] **Feature 5.3**: Task merge detection (avoid duplicate work)
- [ ] **Feature 5.4**: Performance metrics and tuning

---

## Open Questions

1. **Window Duration**: Is 45 seconds the right default? Should it adapt based on user typing speed?

2. **Similarity Thresholds**: Are 0.75 (high) and 0.55 (medium) the right cutoffs? Need user testing.

3. **Agent Overload**: When all agents are at 2-task limit, should we:
   - Queue tasks and notify user of delay?
   - Spawn additional agent instances?
   - Suggest task prioritization?

4. **Merge vs. Separate**: When similarity is 0.90+, should tasks be merged into one? Or kept separate with parallel_ok?

5. **Failure Handling**: If a BLOCKING task fails, should dependent tasks be:
   - Aborted?
   - Retried with different approach?
   - Escalated to user?

---

## Appendix: Example Cypher Queries

### Get Current DAG for User

```cypher
MATCH (t:Task {sender_hash: $hash})
WHERE t.status IN ["pending", "blocked", "ready", "in_progress"]
OPTIONAL MATCH (t)-[d:DEPENDS_ON]->(other:Task)
RETURN t, d, other
ORDER BY t.priority_weight DESC
```

### Find Ready Tasks

```cypher
MATCH (t:Task {sender_hash: $hash, status: "pending"})
WHERE NOT EXISTS {
    MATCH (t)<-[:DEPENDS_ON {type: "blocks"}]-(blocker)
    WHERE blocker.status <> "completed"
}
RETURN t
ORDER BY t.priority_weight DESC
```

### Update After Task Completion

```cypher
MATCH (completed:Task {id: $task_id})
SET completed.status = "completed",
    completed.completed_at = datetime()

WITH completed
MATCH (dependent:Task)-[:DEPENDS_ON]->(completed)
WHERE dependent.status = "blocked"
WITH dependent, collect(completed) as completed_deps

// Check if all blockers are now complete
MATCH (dependent)-[:DEPENDS_ON {type: "blocks"}]->(blocker)
WITH dependent, completed_deps, collect(blocker) as all_blockers
WHERE all(blocker IN completed_deps FOR blocker IN all_blockers)

SET dependent.status = "ready"
```

## Related Documents

### Implementation Order (Must follow this sequence)

1. **[`neo4j.md`](./neo4j.md)** (COMPLETE FIRST)
   - 6-agent OpenClaw system setup
   - Core Neo4j schema and indexes
   - OperationalMemory module
   - Agent specialization protocols

2. **`kurultai_0.1.md`** (THIS DOCUMENT - implement AFTER neo4j.md)
   - Task Dependency Engine
   - Intent window buffering
   - Topological DAG execution
   - Notion integration

### Supporting Documents

- `moltbot.json` - Agent configuration and routing (updated in neo4j.md Phase 1)
- `kurultai-webpage/index.html` - Public documentation

### Integration Summary

| Feature | Source | Description |
|---------|--------|-------------|
| Base `:Task` node | neo4j.md | Core task tracking with claim_task |
| `:Task` extensions | kurultai_0.1.md | embedding, deliverable_type, priority_weight |
| `DEPENDS_ON` relationship | kurultai_0.1.md | Task dependency edges (blocks, feeds_into, parallel_ok) |
| agentToAgent messaging | neo4j.md | Delegation protocol |
| OperationalMemory | neo4j.md | State management module |
| TopologicalExecutor | kurultai_0.1.md | DAG-based task execution |
| NotionSyncHandler | kurultai_0.1.md | External task sync |

---

*End of Document*