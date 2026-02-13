# Phase 4: Synthesis - Unified Architecture Design

## Combining Best Elements from Options A, B, and C

---

## Unified Architecture: "Adaptive Worker Pool with Memory Governance"

### Core Philosophy
> Use **Option A's process isolation** as the foundation, **Option C's adaptive scheduling** for intelligence, and **Option B's chunking principles** for long-running task handling.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Kurultai v2.1 Memory Architecture                   │
│                                                                               │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │                        Memory Governance Layer                          │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐  │  │
│  │  │   Monitor    │  │  Scheduler   │  │   Circuit    │  │  Load Shed  │  │  │
│  │  │  (v8+RSS)    │  │  (Priority)  │  │   Breaker    │  │  Controller │  │  │
│  │  │              │  │              │  │              │  │             │  │  │
│  │  │ <70%: Normal │  │ CRIT/HIGH/   │  │ 3 fails/60s  │  │ Skip HB >70%│  │  │
│  │  │ >70%: SkipLB │  │ NORM/LOW     │  │ exponential  │  │ Reject >90% │  │  │
│  │  │ >85%: Preempt│  │ max depth 5  │  │ backoff      │  │             │  │  │
│  │  │ >95%: Kill   │  │ max run 2    │  │              │  │             │  │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └─────────────┘  │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                    │                                         │
│                                    ▼                                         │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │                      Worker Process Pool (max 2)                        │  │
│  │                                                                         │  │
│  │   ┌─────────────────────┐        ┌─────────────────────┐               │  │
│  │   │     Worker #1       │        │     Worker #2       │               │  │
│  │   │   (soft: 300MB)     │        │   (soft: 300MB)     │               │  │
│  │   │   (hard: 512MB)     │        │   (hard: 512MB)     │               │  │
│  │   │                     │        │                     │               │  │
│  │   │  ┌───────────────┐  │        │  ┌───────────────┐  │               │  │
│  │   │  │  Agent Run    │  │        │  │  Agent Run    │  │               │  │
│  │   │  │  OR           │  │        │  │  OR           │  │               │  │
│  │   │  │  Chunk Task   │  │        │  │  Chunk Task   │  │               │  │
│  │   │  └───────────────┘  │        │  └───────────────┘  │               │  │
│  │   │                     │        │                     │               │  │
│  │   │  IPC: JSON over     │◄──────►│  IPC: JSON over     │               │  │
│  │   │       stdout        │        │       stdout        │               │  │
│  │   └─────────────────────┘        └─────────────────────┘               │  │
│  │                                                                         │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                    │                                         │
│                                    ▼                                         │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │                      Bounded Queue (max depth 5)                        │  │
│  │                                                                         │  │
│  │   Priority 0: AGENT_CRITICAL  [█░░░░] 2 queued                         │  │
│  │   Priority 1: AGENT_HIGH      [░░░░░] 0 queued                         │  │
│  │   Priority 2: AGENT_NORMAL    [░░░░░] 0 queued                         │  │
│  │   Priority 3: TASK_NORMAL     [█░░░░] 1 queued                         │  │
│  │   Priority 4: HEARTBEAT       [██░░░] 2 queued (skippable)             │  │
│  │                                                                         │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Specifications

### 1. Memory Governance Layer

#### Memory Monitor
```typescript
interface MemoryThresholds {
  normal: 0.70,      // 716MB of 1GB - normal operation
  warning: 0.70,     // Skip non-critical heartbeats
  critical: 0.85,    // Preempt lowest priority task
  emergency: 0.95,   // Kill lowest priority, reject new
}

interface MemoryReading {
  heapUsed: number;      // v8 heap
  heapTotal: number;     // v8 total
  rss: number;           // Resident set size
  external: number;      // External memory
  timestamp: number;
}
```

#### Priority Scheduler
```typescript
enum TaskPriority {
  AGENT_CRITICAL = 0,   // User-facing agent runs
  AGENT_HIGH = 1,       // Important agent runs
  AGENT_NORMAL = 2,     // Standard agent runs
  TASK_NORMAL = 3,      // Internal tasks
  HEARTBEAT = 4,        // Periodic heartbeats (skippable)
}

interface Task {
  id: string;
  priority: TaskPriority;
  payload: unknown;
  maxRetries: number;
  createdAt: number;
  skippable: boolean;    // Can be dropped under pressure
  preemptable: boolean;  // Can be paused/resumed
}
```

#### Circuit Breaker
```typescript
interface CircuitBreakerConfig {
  failureThreshold: 3;        // Open after 3 failures
  successThreshold: 2;        // Close after 2 successes
  timeoutMs: 60000;           // 60s window
  backoffSchedule: [1000, 2000, 4000, 8000, 16000]; // Exponential
}

enum CircuitState {
  CLOSED,     // Normal operation
  OPEN,       // Failing fast
  HALF_OPEN,  // Testing recovery
}
```

#### Load Shed Controller
```typescript
interface LoadShedRules {
  // When memory > 70%
  skipHeartbeats: true;
  
  // When memory > 85%
  preemptLowestPriority: true;
  
  // When memory > 90%
  rejectNewNormalPriority: true;
  
  // When memory > 95%
  rejectAllNew: true;
  killLowestPriority: true;
}
```

### 2. Worker Process Pool

#### Worker Configuration
```typescript
interface WorkerConfig {
  maxWorkers: 2;
  minWorkers: 0;           // Scale to zero when idle
  
  // Memory limits
  softLimitMB: 300;        // Warn, try GC
  hardLimitMB: 512;        // Kill worker
  
  // Timeouts
  idleTimeoutMs: 300000;   // 5 min idle = shutdown
  maxRunTimeMs: 600000;    // 10 min max per task
  
  // Restart policy
  maxRestartsPerHour: 10;  // Prevent restart loops
}
```

#### Worker Lifecycle
```
IDLE ──▶ SPAWNING ──▶ READY ──▶ BUSY ──▶ COMPLETED
  ▲        │           │        │          │
  │        ▼           │        ▼          ▼
  │    TIMEOUT      KILLED   TIMEOUT    FAILED
  │        │           │        │          │
  └────────┴───────────┴────────┴──────────┘
```

#### IPC Protocol (Worker <-> Main)
```typescript
// Main -> Worker
interface WorkAssignment {
  type: 'ASSIGN';
  taskId: string;
  payload: unknown;
  softMemoryLimitMB: number;
  maxExecutionTimeMs: number;
}

interface PreemptCommand {
  type: 'PREEMPT';
  reason: 'memory_pressure' | 'timeout' | 'priority';
  checkpointTimeoutMs: 5000;
}

// Worker -> Main
interface ProgressUpdate {
  type: 'PROGRESS';
  taskId: string;
  percent: number;
  memoryMB: number;
  checkpoint?: unknown;  // Resumable state
}

interface TaskComplete {
  type: 'COMPLETE' | 'FAILED' | 'PREEMPTED';
  taskId: string;
  result?: unknown;
  error?: string;
  checkpoint?: unknown;  // For PREEMPTED
}
```

### 3. Bounded Queue

#### Queue Structure
```typescript
interface BoundedQueue {
  maxDepth: 5;
  
  // Per-priority limits
  priorityLimits: {
    [TaskPriority.AGENT_CRITICAL]: 2,  // Always reserve capacity
    [TaskPriority.AGENT_HIGH]: 1,
    [TaskPriority.AGENT_NORMAL]: 1,
    [TaskPriority.TASK_NORMAL]: 1,
    [TaskPriority.HEARTBEAT]: 5,       // Elastic, can be dropped
  };
  
  // Current state
  queues: Map<TaskPriority, Task[]>;
  totalEnqueued: number;
}
```

#### Queue Behavior
```
Enqueue Rules:
1. Check total depth < 5, else reject
2. Check priority limit, else reject or evict lower priority
3. AGENT_CRITICAL can evict HEARTBEAT
4. HEARTBEAT cannot evict anything

Dequeue Rules:
1. Always take highest priority available
2. Within priority: FIFO
3. If memory >70%, filter out skippable HEARTBEAT
```

---

## Memory Flow Diagram

```
Incoming Request
       │
       ▼
┌──────────────┐
│   Gateway    │── Reject if memory >90%
└──────┬───────┘
       │
       ▼
┌──────────────┐
│    Queue     │── Accept if depth <5
│   (bounded)  │── Evict skippable if full
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Scheduler  │── Check memory thresholds
│              │── Skip heartbeats if >70%
└──────┬───────┘
       │
       ▼
┌──────────────┐
│    Pool      │── Max 2 concurrent
│   (workers)  │── Assign to idle worker
└──────┬───────┘
       │
       ▼
┌──────────────┐
│    Worker    │── Soft limit: 300MB (warn)
│  (isolated)  │── Hard limit: 512MB (kill)
└──────────────┘
```

---

## Memory Budget Allocation

```
Total Budget: 1GB (hard ceiling)

Main Process:        200MB  (fixed)
├── Governance:       50MB
├── Queue:            50MB  (5 slots × 10MB)
├── IPC buffers:      50MB
└── Overhead:         50MB

Worker #1:           300MB  (soft) / 512MB (hard)
├── Base:            100MB
├── Agent context:   100MB
└── Tools/buffers:   100MB

Worker #2:           300MB  (soft) / 512MB (hard)
├── Base:            100MB
├── Agent context:   100MB
└── Tools/buffers:   100MB

Headroom:            200MB  (for spikes, GC)

Steady-State Target: <512MB
├── Main:            150MB (workers idle/terminated)
├── Worker #1:       200MB (avg)
└── Worker #2:         0MB (idle, scaled down)
```

---

## Unified Design: Key Benefits

| Feature | Source Option | Benefit |
|---------|---------------|---------|
| Process Isolation | A | Worker crashes don't kill system |
| Hard Memory Limits | A | OS-enforced boundaries |
| Priority Scheduling | C | Critical work always proceeds |
| Load Shedding | C | Graceful degradation |
| Threshold Actions | C | Predictable behavior |
| Bounded Queue | A+C | No unbounded growth |
| Circuit Breaker | A+C | Prevents retry storms |
| Preemption | C | Can recover from pressure |
| Chunking (optional) | B | For very long tasks |

---

## Synthesis Trade-offs

### What We Gained
- ✅ Fault isolation (from A)
- ✅ Memory predictability (from A+C)
- ✅ Adaptive behavior (from C)
- ✅ Simple mental model (mostly A)

### What We Accepted
- ⚠️ Process spawn overhead (~100-200ms)
- ⚠️ IPC complexity (JSON over stdout)
- ⚠️ Preemption is best-effort (may lose work)

### What We Deferred
- Full streaming architecture (too complex for v2.1)
- Redis/external queue (adds dependency)
- Distributed execution (out of scope)

---

## Phase 4 Complete ✓
**Outcome:** Unified "Adaptive Worker Pool with Memory Governance" architecture defined with component specifications and memory budget.
