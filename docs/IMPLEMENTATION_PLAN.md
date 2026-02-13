# Implementation Plan

## Kurultai v2.1 Memory Optimization Rollout

**Version:** 1.0.0  
**Date:** 2026-02-13  
**Target Release:** v2.1.0  
**Estimated Duration:** 4 weeks

---

## Overview

This plan breaks the memory optimization architecture into bite-sized, independently deliverable tasks. Each task includes acceptance criteria and estimated effort.

### Timeline Summary

```
Week 1: Foundation (Core monitoring, basic pool)
Week 2: Governance (Scheduler, circuit breakers)
Week 3: Integration (Worker IPC, queue, testing)
Week 4: Hardening (Load testing, tuning, docs)
```

---

## Phase 1: Foundation (Week 1)

### Task 1.1: Memory Monitor Core
**Owner:** Backend Team  
**Effort:** 2 days  
**Dependencies:** None

**Description:**
Implement the memory monitoring component that tracks v8 heap, RSS, and external memory at configurable intervals.

**Implementation:**
```typescript
// src/governance/MemoryMonitor.ts
export class MemoryMonitor extends EventEmitter {
  private checkInterval: NodeJS.Timeout | null = null;
  
  constructor(private config: MemoryConfig) {
    super();
  }
  
  start(): void {
    this.checkInterval = setInterval(() => {
      const snapshot = this.captureSnapshot();
      this.checkThresholds(snapshot);
    }, this.config.checkIntervalMs);
  }
  
  private captureSnapshot(): MemorySnapshot {
    const usage = process.memoryUsage();
    return {
      timestamp: Date.now(),
      heapUsed: usage.heapUsed,
      heapTotal: usage.heapTotal,
      rss: usage.rss,
      external: usage.external,
      arrayBuffers: usage.arrayBuffers || 0,
      percentOfLimit: usage.rss / (this.config.limitMB * 1024 * 1024)
    };
  }
}
```

**Acceptance Criteria:**
- [ ] Monitor captures all memory types (heapUsed, heapTotal, rss, external)
- [ ] Emits events at configured thresholds (70%, 85%, 95%)
- [ ] Includes hysteresis (10% gap between threshold and clear)
- [ ] Unit tests: >90% coverage
- [ ] Logs memory snapshot every 5 seconds at DEBUG level

**Verification:**
```bash
npm test -- MemoryMonitor.test.ts
```

---

### Task 1.2: Worker Process Base
**Owner:** Backend Team  
**Effort:** 3 days  
**Dependencies:** None

**Description:**
Create the worker process wrapper that runs agents in isolated Node.js processes with memory limits.

**Implementation:**
```typescript
// src/worker/WorkerProcess.ts
export class WorkerProcess extends EventEmitter {
  private process: ChildProcess | null = null;
  private taskTimeout: NodeJS.Timeout | null = null;
  
  async spawn(): Promise<void> {
    this.process = fork(path.join(__dirname, 'worker-entry.js'), [], {
      execArgv: ['--max-old-space-size=512'],
      env: { ...process.env, WORKER_ID: this.id }
    });
    
    this.setupIPC();
    this.setupMemoryMonitoring();
  }
  
  private setupMemoryMonitoring(): void {
    setInterval(() => {
      const usage = process.memoryUsage();
      if (usage.rss > 300 * 1024 * 1024) {
        this.emit('memoryWarning', usage);
      }
    }, 5000);
  }
}
```

**Acceptance Criteria:**
- [ ] Worker spawns with `--max-old-space-size=512`
- [ ] Worker emits memory warning at 300MB RSS
- [ ] Worker terminates cleanly on task completion
- [ ] Worker kills itself (OOM) if exceeding 512MB
- [ ] IPC protocol over stdout works reliably
- [ ] Integration test: worker runs simple agent

**Verification:**
```bash
npm test -- WorkerProcess.test.ts
npm run test:integration -- worker
```

---

### Task 1.3: Basic Worker Pool
**Owner:** Backend Team  
**Effort:** 2 days  
**Dependencies:** Task 1.2

**Description:**
Implement worker pool with max 2 concurrent workers, idle timeout, and basic lifecycle management.

**Acceptance Criteria:**
- [ ] Pool respects maxWorkers = 2
- [ ] Idle workers terminate after 5 minutes
- [ ] Pool respawns workers up to maxRestartsPerHour (10)
- [ ] Pool emits events: workerSpawned, workerExited, taskCompleted
- [ ] Task assignment is FIFO

---

## Phase 2: Governance (Week 2)

### Task 2.1: Priority Queue
**Owner:** Backend Team  
**Effort:** 2 days  
**Dependencies:** None

**Description:**
Implement bounded priority queue with 5 levels and memory-aware behavior.

**Implementation:**
```typescript
// src/governance/PriorityQueue.ts
export class PriorityQueue {
  private queues: Map<TaskPriority, Task[]> = new Map();
  
  enqueue(task: Task): boolean {
    if (this.getTotalDepth() >= this.config.maxQueueDepth) {
      return false;
    }
    
    const queue = this.queues.get(task.priority) || [];
    if (queue.length >= this.config.priorityLimits[task.priority]) {
      return this.tryEvict(task);
    }
    
    queue.push(task);
    this.queues.set(task.priority, queue);
    return true;
  }
  
  dequeue(): Task | null {
    for (let priority = 0; priority <= 4; priority++) {
      const queue = this.queues.get(priority);
      if (queue?.length > 0) {
        // Skip heartbeats if memory > 70%
        if (priority === TaskPriority.HEARTBEAT && this.isMemoryHigh()) {
          continue;
        }
        return queue.shift() || null;
      }
    }
    return null;
  }
}
```

**Acceptance Criteria:**
- [ ] Queue depth never exceeds 5
- [ ] Priority 0 (CRITICAL) always dequeued before priority 4 (HEARTBEAT)
- [ ] Heartbeats skipped when memory > 70%
- [ ] CRITICAL tasks can evict HEARTBEAT tasks when queue full
- [ ] FIFO ordering within priority level

---

### Task 2.2: Circuit Breaker
**Owner:** Backend Team  
**Effort:** 2 days  
**Dependencies:** None

**Description:**
Implement circuit breaker pattern for architecture sync and external APIs.

**Acceptance Criteria:**
- [ ] Opens after 3 failures in 60 seconds
- [ ] Enters half-open after timeout
- [ ] Closes after 2 consecutive successes
- [ ] Exponential backoff: 1s, 2s, 4s, 8s
- [ ] Emits state change events
- [ ] Unit tests cover all state transitions

---

### Task 2.3: Memory Governor Integration
**Owner:** Backend Team  
**Effort:** 2 days  
**Dependencies:** Task 1.1, Task 2.1

**Description:**
Integrate memory monitor with queue to enable adaptive behavior.

**Acceptance Criteria:**
- [ ] At 70%: Skip heartbeats logged and counted
- [ ] At 85%: Lowest priority task preempted (if preemptable)
- [ ] At 95%: Lowest priority task killed
- [ ] Recovery actions logged with correlation IDs
- [ ] Metrics emitted for all threshold crossings

---

## Phase 3: Integration (Week 3)

### Task 3.1: Worker IPC Protocol
**Owner:** Backend Team  
**Effort:** 2 days  
**Dependencies:** Task 1.2

**Description:**
Implement robust IPC between main process and workers using structured messages over stdout.

**Message Format:**
```typescript
// Line-delimited JSON over stdout
// Message: {"type":"PROGRESS","taskId":"123","percent":50}
// Result:  {"type":"COMPLETE","taskId":"123","result":{}}
// Error:   {"type":"FAILED","taskId":"123","error":"..."}
```

**Acceptance Criteria:**
- [ ] Messages serialized to JSON lines
- [ ] Progress updates every 10% or 30 seconds
- [ ] Large payloads streamed, not buffered
- [ ] Error messages include stack traces
- [ ] Protocol versioned for future compatibility

---

### Task 3.2: Queue + Pool Integration
**Owner:** Backend Team  
**Effort:** 2 days  
**Dependencies:** Task 1.3, Task 2.1

**Description:**
Connect priority queue to worker pool with automatic dequeuing when workers available.

**Acceptance Criteria:**
- [ ] When worker idle, automatically dequeues next task
- [ ] When queue has tasks but no workers, waits for worker
- [ ] Task cancellation propagates to worker
- [ ] Queue stats exposed via metrics endpoint

---

### Task 3.3: API Gateway Integration
**Owner:** API Team  
**Effort:** 2 days  
**Dependencies:** Task 2.3

**Description:**
Modify API gateway to check memory before accepting requests and return 503 when at capacity.

**Acceptance Criteria:**
- [ ] Returns 503 when memory > 90%
- [ ] Returns 429 when queue full
- [ ] Includes `Retry-After` header with estimated wait
- [ ] Logs rejection reason for monitoring
- [ ] Health endpoint reflects memory status

---

### Task 3.4: Configuration System
**Owner:** Backend Team  
**Effort:** 1 day  
**Dependencies:** None

**Description:**
Implement configuration loading from YAML with environment variable overrides.

**Acceptance Criteria:**
- [ ] Config loaded from `config/memory.yaml`
- [ ] Environment variables override (e.g., `KURULTAI_MAX_WORKERS`)
- [ ] Validation on startup (fail fast on invalid config)
- [ ] Hot reload for non-critical settings

---

## Phase 4: Hardening (Week 4)

### Task 4.1: Integration Tests
**Owner:** QA Team  
**Effort:** 2 days  
**Dependencies:** All Phase 1-3 tasks

**Test Scenarios:**
```typescript
describe('Memory Optimization', () => {
  test('steady-state memory under 512MB', async () => {
    await runNormalLoadForMinutes(5);
    expect(await getMemoryUsage()).toBeLessThan(512 * 1024 * 1024);
  });
  
  test('peak memory under 1GB', async () => {
    await burstLoad(10); // 10 concurrent requests
    expect(await getMemoryUsage()).toBeLessThan(1024 * 1024 * 1024);
  });
  
  test('OOM scenario handled gracefully', async () => {
    const leakyTask = createMemoryLeakTask();
    await expect(runTask(leakyTask)).rejects.toThrow();
    expect(await isSystemHealthy()).toBe(true); // System survives
  });
  
  test('circuit breaker prevents retry storm', async () => {
    await failSyncEndpoint();
    await runMultipleSyncs(10);
    expect(getSyncAttempts()).toBeLessThan(5); // Stopped by breaker
  });
});
```

**Acceptance Criteria:**
- [ ] Steady-state test passes (<512MB)
- [ ] Peak load test passes (<1GB)
- [ ] OOM recovery test passes
- [ ] Circuit breaker test passes
- [ ] All tests automated in CI

---

### Task 4.2: Load Testing
**Owner:** QA Team  
**Effort:** 2 days  
**Dependencies:** Task 4.1

**Load Profile:**
```yaml
steadyState:
  duration: 10 minutes
  agents: 1
  interval: 30 seconds
  
peakLoad:
  duration: 5 minutes
  agents: 10
  interval: 1 second
  
spike:
  duration: 1 minute
  agents: 20
  interval: 0.1 seconds
```

**Acceptance Criteria:**
- [ ] Steady-state: <512MB sustained
- [ ] Peak load: <1GB, no OOM
- [ ] Spike: Queue rejects gracefully, recovers
- [ ] No memory leaks over 1 hour test

---

### Task 4.3: Metrics and Alerting
**Owner:** DevOps Team  
**Effort:** 2 days  
**Dependencies:** Task 2.3

**Metrics to Expose:**
```
kurultai_memory_usage_bytes
curultai_memory_limit_bytes
kurultai_workers_active
curultai_workers_idle
curultai_queue_depth
curultai_tasks_preempted_total
curultai_circuit_breaker_state
curultai_heartbeats_skipped_total
```

**Alerts:**
- WARNING: Memory >70% for >5 minutes
- CRITICAL: Memory >85% for >2 minutes
- EMERGENCY: Memory >95% or worker OOM

**Acceptance Criteria:**
- [ ] All metrics exposed on `/metrics` endpoint
- [ ] Grafana dashboard created
- [ ] PagerDuty alerts configured
- [ ] Runbooks linked in alerts

---

### Task 4.4: Documentation and Migration Guide
**Owner:** Docs Team  
**Effort:** 1 day  
**Dependencies:** All tasks

**Deliverables:**
- [ ] Migration guide from v2.0.2
- [ ] Operational runbook
- [ ] Troubleshooting guide
- [ ] API changes documented

---

## Rollout Plan

### Staged Deployment

```
Day 1-2:  Deploy to staging
          └── Run full integration tests
          └── Verify metrics and alerts
          
Day 3-4:  Deploy to 10% production
          └── Monitor error rates
          └── Verify memory profiles
          
Day 5-7:  Deploy to 50% production
          └── Compare memory usage vs control
          └── Verify no regression in latency
          
Day 8-14: Deploy to 100% production
          └── Full monitoring
          └── Document lessons learned
```

### Rollback Criteria

Immediate rollback if:
- Error rate increases >1%
- Latency p99 increases >50%
- Any OOM events occur
- Customer complaints about rejected requests

### Feature Flags

```typescript
const FEATURES = {
  MEMORY_GOVERNANCE: process.env.FF_MEMORY_GOVERNANCE === 'true',
  WORKER_POOL: process.env.FF_WORKER_POOL === 'true',
  CIRCUIT_BREAKERS: process.env.FF_CIRCUIT_BREAKERS === 'true',
};
```

---

## Task Summary

| ID | Task | Owner | Effort | Dependencies |
|----|------|-------|--------|--------------|
| 1.1 | Memory Monitor Core | Backend | 2d | - |
| 1.2 | Worker Process Base | Backend | 3d | - |
| 1.3 | Basic Worker Pool | Backend | 2d | 1.2 |
| 2.1 | Priority Queue | Backend | 2d | - |
| 2.2 | Circuit Breaker | Backend | 2d | - |
| 2.3 | Memory Governor | Backend | 2d | 1.1, 2.1 |
| 3.1 | Worker IPC Protocol | Backend | 2d | 1.2 |
| 3.2 | Queue + Pool Integration | Backend | 2d | 1.3, 2.1 |
| 3.3 | API Gateway Integration | API | 2d | 2.3 |
| 3.4 | Configuration System | Backend | 1d | - |
| 4.1 | Integration Tests | QA | 2d | 1-3 |
| 4.2 | Load Testing | QA | 2d | 4.1 |
| 4.3 | Metrics and Alerting | DevOps | 2d | 2.3 |
| 4.4 | Documentation | Docs | 1d | All |

**Total Effort:** 27 days (~6 weeks with 1 FTE, or 4 weeks with 2 FTE)

---

## Success Criteria

### Technical
- [ ] Steady-state memory <512MB sustained for 24 hours
- [ ] Peak memory <1GB under load test
- [ ] Zero OOM events in 1 week of production
- [ ] P99 latency within 20% of v2.0.2

### Operational
- [ ] All alerts actionable with runbooks
- [ ] Rollback tested and documented
- [ ] Metrics dashboard live
- [ ] Team trained on new architecture

---

**End of Implementation Plan**
