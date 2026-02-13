# Kurultai Architecture v2.1: Memory-Optimized Design

## Full Architecture Specification

**Version:** 2.1.0  
**Date:** 2026-02-13  
**Status:** Design Complete  
**Target Release:** v2.1.0  

---

## Executive Summary

This document specifies the memory-optimized architecture for Kurultai v2.1, designed to prevent the OOM crashes that occurred on 2026-02-13. The architecture introduces bounded concurrency, memory governance, circuit breakers, and load-adaptive scheduling.

### Key Metrics
| Metric | Target | v2.0.2 Status |
|--------|--------|---------------|
| Steady-state memory | <512MB | ~800MB+ (unbounded) |
| Peak memory under load | <1GB | OOM at ~2GB |
| Max concurrent agents | 2 | Unlimited |
| Max queue depth | 5 | Unbounded |
| Uptime during load | >99% | Frequent crashes |

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Component Specifications](#2-component-specifications)
3. [Memory Management](#3-memory-management)
4. [Configuration Reference](#4-configuration-reference)
5. [Migration from v2.0.2](#5-migration-from-v202)
6. [Operational Runbooks](#6-operational-runbooks)

---

## 1. Architecture Overview

### 1.1 High-Level Design

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Kurultai v2.1                                    │
│                                                                               │
│  ┌───────────────────────────────────────────────────────────────────────┐   │
│  │                     API Gateway (HTTP/WebSocket)                       │   │
│  │  • Request validation                                                │   │
│  │  • Rate limiting (10 req/s)                                          │   │
│  │  • Memory check: reject if >90%                                      │   │
│  └───────────────────────────────────────────────────────────────────────┘   │
│                                    │                                          │
│                                    ▼                                          │
│  ┌───────────────────────────────────────────────────────────────────────┐   │
│  │                     Memory Governance Core                             │   │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────────┐  │   │
│  │  │   Monitor   │ │  Scheduler  │ │   Circuit   │ │   Load Shedder  │  │   │
│  │  │  (v8+RSS)   │ │  (Priority) │ │   Breaker   │ │   (Adaptive)    │  │   │
│  │  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────────┘  │   │
│  └───────────────────────────────────────────────────────────────────────┘   │
│                                    │                                          │
│                                    ▼                                          │
│  ┌───────────────────────────────────────────────────────────────────────┐   │
│  │                     Bounded Task Queue (max 5)                         │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐    │   │
│  │  │ CRITICAL │ │   HIGH   │ │  NORMAL  │ │   TASK   │ │ HEARTBEAT│    │   │
│  │  │  (max 2) │ │  (max 1) │ │  (max 1) │ │  (max 1) │ │ (max 5*) │    │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘    │   │
│  │  * elastic, droppable under pressure                                 │   │
│  └───────────────────────────────────────────────────────────────────────┘   │
│                                    │                                          │
│                                    ▼                                          │
│  ┌───────────────────────────────────────────────────────────────────────┐   │
│  │                     Worker Process Pool (max 2)                        │   │
│  │                                                                        │   │
│  │   ┌──────────────────┐              ┌──────────────────┐              │   │
│  │   │    Worker #1     │              │    Worker #2     │              │   │
│  │   │  ┌────────────┐  │              │  ┌────────────┐  │              │   │
│  │   │  │  Process   │  │◄────────────►│  │  Process   │  │              │   │
│  │   │  │  soft:300MB│  │   IPC        │  │  soft:300MB│  │              │   │
│  │   │  │  hard:512MB│  │              │  │  hard:512MB│  │              │   │
│  │   │  └────────────┘  │              │  └────────────┘  │              │   │
│  │   └──────────────────┘              └──────────────────┘              │   │
│  │                                                                        │   │
│  └───────────────────────────────────────────────────────────────────────┘   │
│                                                                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Design Principles

1. **Fail Fast, Fail Safe**: Reject work early rather than crash late
2. **Isolation**: Worker failures don't cascade to system
3. **Observability**: Every memory threshold crossing is logged
4. **Graceful Degradation**: Shed load progressively, not catastrophically
5. **Simplicity**: Prefer simple mechanisms over complex optimizations

---

## 2. Component Specifications

### 2.1 Memory Monitor

**Purpose**: Continuously track memory usage and emit threshold events.

**Interface**:
```typescript
class MemoryMonitor extends EventEmitter {
  constructor(config: MemoryConfig);
  
  start(): void;                    // Begin monitoring loop
  stop(): void;                     // Stop monitoring
  getCurrent(): MemorySnapshot;     // Current readings
  
  // Events
  on('threshold', (level: Threshold, usage: MemorySnapshot) => void);
  on('warning', (message: string) => void);
}

interface MemoryConfig {
  checkIntervalMs: number;         // Default: 1000
  thresholds: {
    warning: number;    // 0.70 (skip heartbeats)
    critical: number;   // 0.85 (preempt)
    emergency: number;  // 0.95 (kill/reject)
  };
  gcOnThreshold: boolean;          // Trigger GC at warning
}

interface MemorySnapshot {
  timestamp: number;
  heapUsed: number;
  heapTotal: number;
  rss: number;
  external: number;
  arrayBuffers: number;
  percentOfLimit: number;
}
```

**Behavior**:
```
Memory < 70%:   Normal operation, all tasks proceed
Memory > 70%:   Emit 'warning', skip skippable heartbeats
Memory > 85%:   Emit 'critical', preempt lowest priority task
Memory > 95%:   Emit 'emergency', kill task, reject new work
```

### 2.2 Priority Scheduler

**Purpose**: Manage task queue with priority-based scheduling and memory awareness.

**Interface**:
```typescript
class PriorityScheduler extends EventEmitter {
  constructor(config: SchedulerConfig, memoryMonitor: MemoryMonitor);
  
  enqueue(task: Task): Promise<boolean>;     // Returns success/fail
  dequeue(): Task | null;                    // Get next task
  preempt(): Promise<Task | null>;           // Force suspend lowest priority
  
  // Statistics
  getStats(): SchedulerStats;
}

interface Task {
  id: string;
  priority: TaskPriority;
  type: 'agent' | 'heartbeat' | 'sync';
  payload: unknown;
  createdAt: number;
  skippable: boolean;      // Can drop under pressure
  preemptable: boolean;    // Can suspend/resume
  maxRetries: number;
  retries: number;
}

enum TaskPriority {
  AGENT_CRITICAL = 0,      // User agent runs
  AGENT_HIGH = 1,
  AGENT_NORMAL = 2,
  TASK_NORMAL = 3,         // Internal tasks
  HEARTBEAT = 4,           // Periodic tasks
}

interface SchedulerConfig {
  maxQueueDepth: number;           // 5
  priorityLimits: Record<TaskPriority, number>;
  defaultTimeoutMs: number;        // 600000 (10 min)
}
```

**Queue Structure**:
```
Priority 0 (AGENT_CRITICAL): Max 2 slots
Priority 1 (AGENT_HIGH):     Max 1 slot
Priority 2 (AGENT_NORMAL):   Max 1 slot
Priority 3 (TASK_NORMAL):    Max 1 slot
Priority 4 (HEARTBEAT):      Max 5 slots, skippable

Total max: 10 items, but scheduler enforces:
- Active + queued agents ≤ 7 (2 running + 5 queued)
- Heartbeats dropped if exceed limit or memory >70%
```

### 2.3 Circuit Breaker

**Purpose**: Prevent retry storms on failing operations.

**Interface**:
```typescript
class CircuitBreaker extends EventEmitter {
  constructor(config: CircuitConfig);
  
  async execute<T>(fn: () => Promise<T>): Promise<T>;
  getState(): CircuitState;
  recordSuccess(): void;
  recordFailure(): void;
  
  // Events
  on('open', () => void);
  on('halfOpen', () => void);
  on('close', () => void);
}

enum CircuitState {
  CLOSED,      // Normal operation
  OPEN,        // Failing fast
  HALF_OPEN,   // Testing recovery
}

interface CircuitConfig {
  name: string;
  failureThreshold: number;     // 3
  successThreshold: number;     // 2
  timeoutMs: number;            // 60000
  backoffSchedule: number[];    // [1000, 2000, 4000, 8000]
}
```

**State Machine**:
```
CLOSED ──▶ [3 failures in 60s] ──▶ OPEN
  ▲                                    │
  │                                    │
  └── [2 successes] ◀── HALF_OPEN ◀───┘
         (during probe)     (after timeout)
```

### 2.4 Worker Pool

**Purpose**: Manage isolated worker processes with lifecycle control.

**Interface**:
```typescript
class WorkerPool extends EventEmitter {
  constructor(config: PoolConfig);
  
  async execute(task: Task): Promise<unknown>;
  getStatus(): PoolStatus;
  terminateAll(): Promise<void>;
  
  // Events
  on('workerSpawned', (workerId: string) => void);
  on('workerExited', (workerId: string, code: number) => void);
  on('taskCompleted', (taskId: string, result: unknown) => void);
  on('taskFailed', (taskId: string, error: Error) => void);
}

interface PoolConfig {
  maxWorkers: number;           // 2
  minWorkers: number;           // 0 (scale to zero)
  
  // Memory limits
  softMemoryLimitMB: number;    // 300
  hardMemoryLimitMB: number;    // 512
  
  // Timeouts
  idleTimeoutMs: number;        // 300000 (5 min)
  maxRunTimeMs: number;         // 600000 (10 min)
  spawnTimeoutMs: number;       // 30000 (30 sec)
  
  // Restart policy
  maxRestartsPerHour: number;   // 10
}

interface PoolStatus {
  totalWorkers: number;
  idleWorkers: number;
  busyWorkers: number;
  queuedTasks: number;
  memoryUsageMB: number;
}
```

**Worker Lifecycle**:
```
                    ┌─────────────┐
         ┌─────────│   IDLE      │◄────────┐
         │         │ (waiting)   │         │
         │         └──────┬──────┘         │
    timeout/              │ assign         │ complete
    shutdown              ▼                │
         │         ┌─────────────┐         │
         └────────►│   BUSY      │─────────┘
                   │ (executing) │
                   └──────┬──────┘
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
        ┌─────────┐ ┌─────────┐ ┌─────────┐
        │ SUCCESS │ │ FAILURE │ │  KILLED │
        └─────────┘ └─────────┘ └─────────┘
```

### 2.5 Worker Process

**Purpose**: Execute tasks in isolated process with memory limits.

**Implementation**:
```typescript
// worker.ts - Runs in separate process
process.env.NODE_OPTIONS = '--max-old-space-size=512';

class WorkerProcess {
  private memoryCheckInterval: NodeJS.Timeout;
  
  constructor() {
    // Monitor own memory usage
    this.memoryCheckInterval = setInterval(() => {
      const usage = process.memoryUsage();
      if (usage.rss > 300 * 1024 * 1024) {
        this.emit('memoryWarning');
        if (global.gc) global.gc();
      }
    }, 5000);
  }
  
  async runTask(task: Task): Promise<unknown> {
    // Set up timeout
    const timeout = setTimeout(() => {
      this.emit('timeout');
      process.exit(1);
    }, task.timeoutMs);
    
    try {
      const result = await executeAgent(task.payload);
      clearTimeout(timeout);
      return result;
    } catch (error) {
      clearTimeout(timeout);
      throw error;
    }
  }
}
```

---

## 3. Memory Management

### 3.1 Memory Budget

| Component | Budget | Notes |
|-----------|--------|-------|
| Main Process | 200MB | Fixed overhead |
| Worker #1 | 300MB soft / 512MB hard | Scales with load |
| Worker #2 | 300MB soft / 512MB hard | Scales with load |
| Headroom | 200MB | For GC, spikes |
| **Total** | **1GB** | System ceiling |

### 3.2 Steady-State Target

```
Main Process:     150MB
Worker #1:        200MB (active agent)
Worker #2:          0MB (idle, terminated)
─────────────────────────
Total:            350MB (well under 512MB target)
```

### 3.3 Peak Load Scenario

```
Main Process:     200MB
Worker #1:        400MB (high-load agent)
Worker #2:        400MB (high-load agent)
─────────────────────────
Total:           1000MB (at limit, triggers shedding)
```

### 3.4 Memory Pressure Response

| Level | Threshold | Action | Recovery |
|-------|-----------|--------|----------|
| Normal | <70% | All operations proceed | N/A |
| Warning | >70% | Skip skippable heartbeats | <60% |
| Critical | >85% | Preempt lowest priority | <75% |
| Emergency | >95% | Kill task, reject new | <80% |

---

## 4. Configuration Reference

### 4.1 Default Configuration (config/memory.yaml)

```yaml
memoryGovernance:
  enabled: true
  limitMB: 1024
  
  monitor:
    checkIntervalMs: 1000
    gcOnThreshold: true
    
  thresholds:
    warning: 0.70    # 716MB
    critical: 0.85   # 870MB
    emergency: 0.95  # 972MB
    
  hysteresis:
    # Require 10% drop before clearing threshold
    warningClear: 0.60
    criticalClear: 0.75
    emergencyClear: 0.80

scheduler:
  maxQueueDepth: 5
  
  priorityLimits:
    0: 2   # AGENT_CRITICAL
    1: 1   # AGENT_HIGH
    2: 1   # AGENT_NORMAL
    3: 1   # TASK_NORMAL
    4: 5   # HEARTBEAT (elastic)
    
  timeouts:
    defaultMs: 600000
    maxMs: 1800000  # 30 min absolute max

workerPool:
  maxWorkers: 2
  minWorkers: 0
  
  memory:
    softLimitMB: 300
    hardLimitMB: 512
    
  timeouts:
    idleMs: 300000
    maxRunMs: 600000
    spawnMs: 30000
    
  restartPolicy:
    maxPerHour: 10
    backoffMs: [1000, 2000, 4000, 8000]

circuitBreakers:
  architectureSync:
    failureThreshold: 3
    successThreshold: 2
    timeoutMs: 60000
    backoffMs: [1000, 2000, 4000, 8000, 16000]
    
  externalAPI:
    failureThreshold: 5
    successThreshold: 2
    timeoutMs: 120000
```

### 4.2 Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KURULTAI_MAX_WORKERS` | 2 | Worker pool size |
| `KURULTAI_MEMORY_LIMIT_MB` | 1024 | System memory ceiling |
| `KURULTAI_QUEUE_DEPTH` | 5 | Max queued tasks |
| `KURULTAI_WORKER_MEMORY_MB` | 512 | Per-worker hard limit |
| `KURULTAI_HEARTBEAT_INTERVAL_MS` | 300000 | 5 minutes |
| `KURULTAI_GC_ON_PRESSURE` | true | Trigger GC at warning |

---

## 5. Migration from v2.0.2

### 5.1 Breaking Changes

| Aspect | v2.0.2 | v2.1.0 | Migration |
|--------|--------|--------|-----------|
| Concurrency | Unlimited | Max 2 | May queue more |
| Queue | Unbounded | Max 5 | May reject excess |
| Heartbeats | Always run | Skippable | Config priority |
| Worker model | In-process | Isolated processes | IPC changes |

### 5.2 Migration Steps

1. **Pre-deployment**
   ```bash
   # Enable memory monitoring only (no enforcement)
   export KURULTAI_MEMORY_GOVERNANCE_MODE=observe
   ```

2. **Gradual Rollout**
   ```bash
   # Week 1: 50% traffic, soft limits only
   export KURULTAI_ENFORCEMENT_MODE=soft
   
   # Week 2: 100% traffic, full enforcement
   export KURULTAI_ENFORCEMENT_MODE=hard
   ```

3. **Verification**
   - Monitor queue depth metrics
   - Verify heartbeat deferral under load
   - Confirm OOM events eliminated

### 5.3 Rollback Plan

```bash
# Emergency rollback to v2.0.2
export KURULTAI_WORKER_POOL_ENABLED=false
export KURULTAI_MAX_WORKERS=999
export KURULTAI_QUEUE_DEPTH=999
```

---

## 6. Operational Runbooks

### 6.1 Alert: Memory Warning (>70%)

**Symptom**: Log: `MEMORY_WARNING: usage=735MB (71.8%)`

**Response**:
1. Check active tasks: `kurultai-cli tasks list`
2. Review queued tasks: `kurultai-cli queue status`
3. Normal if transient, investigate if sustained >5min

### 6.2 Alert: Memory Critical (>85%)

**Symptom**: Log: `MEMORY_CRITICAL: preempted task=xxx`

**Response**:
1. Task preempted automatically
2. Check if task rescheduled: `kurultai-cli tasks show xxx`
3. Investigate cause: memory leak or legitimate high usage

### 6.3 Alert: Circuit Breaker Open

**Symptom**: Log: `CIRCUIT_OPEN: architectureSync`

**Response**:
1. Check external dependency health
2. Wait for auto-recovery (exponential backoff)
3. Force close: `kurultai-cli circuit-breaker close architectureSync`

### 6.4 Alert: Worker OOM

**Symptom**: Log: `WORKER_KILLED: oom=true`

**Response**:
1. Worker restarted automatically
2. Check task for memory leak patterns
3. If repeated, consider chunking long-running task

---

## Appendix A: Metric Names

```
kurultai_memory_usage_bytes
curultai_memory_limit_bytes
kurultai_workers_active
curultai_workers_idle
curultai_queue_depth
curultai_queue_depth_by_priority
curultai_tasks_completed_total
curultai_tasks_failed_total
curultai_tasks_preempted_total
curultai_circuit_breaker_state
curultai_heartbeats_skipped_total
```

## Appendix B: Log Format

```json
{
  "timestamp": "2026-02-13T23:00:00Z",
  "level": "WARN",
  "component": "MemoryGovernor",
  "event": "MEMORY_WARNING",
  "data": {
    "usageMB": 735,
    "limitMB": 1024,
    "percent": 71.8,
    "action": "SKIP_HEARTBEATS"
  }
}
```

---

**End of Specification**
