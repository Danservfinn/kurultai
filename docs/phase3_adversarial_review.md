# Phase 3: Adversarial Review

## Failure Mode Analysis for Each Architecture

---

## Option A: Process Pool - Failure Mode Analysis

### Scenario 1: Memory Pressure (OOM)

#### Attack Vector: Memory Leak in Worker
```
Timeline:
T0: Worker #1 starts agent run
T1: Agent tool creates unbounded array (memory leak)
T2: Worker approaches 400MB limit
T3: v8 tries to GC, but leak continues
T4: Worker killed by OOM (or --max-old-space-size)
T5: Main process detects worker death

Failure Modes:
1. Worker death loses all in-progress work
2. Task must restart from beginning (no checkpoint)
3. If leak is deterministic, retry = repeated failure
4. Circuit breaker needed to stop retry loop
```

#### Mitigation
- Circuit breaker prevents infinite retry
- Worker pool automatically respawns
- Task result = error (accept data loss for stability)

### Scenario 2: Load Spike (Burst Traffic)

#### Attack Vector: 10 Simultaneous Agent Requests
```
Timeline:
T0: Queue has 10 agent requests arrive
T1: Pool at max (2 workers), 8 queued
T2: Each queued item = 50MB overhead
T3: Queue memory = 400MB
T4: Workers running = 400MB each
T5: Total = 128 + 400 + 800 = 1328MB → OOM

Failure Mode:
Queue depth limit (5) not enforced → memory overrun
```

#### Mitigation
- Strict queue depth limit (5 = 250MB max)
- Reject new requests with 503 when full
- Implement load shedding

### Scenario 3: Cascading Failure (Retry Storm)

#### Attack Vector: Architecture Sync Endpoint Down
```
Timeline:
T0: Sync endpoint returns 500
T1: Agent runs fail, exit with error
T2: Main process restarts them immediately
T3: Workers spawn, fail, die in loop
T4: Spawn overhead + retry = CPU/memory exhaustion
T5: Main process becomes unresponsive

Failure Mode:
Fast failure loop consumes resources faster than process spawn
```

#### Mitigation
- Circuit breaker on sync endpoint
- Exponential backoff (1s, 2s, 4s, 8s...)
- Worker spawn rate limiting

### Option A Risk Score: MEDIUM-HIGH
| Risk | Severity | Mitigation Complexity |
|------|----------|----------------------|
| Worker OOM | High | Medium |
| Queue overflow | High | Low |
| Retry storm | Critical | Medium |

---

## Option B: Streaming/Chunked - Failure Mode Analysis

### Scenario 1: Memory Pressure (OOM)

#### Attack Vector: Checkpoint Corruption
```
Timeline:
T0: Chunk 5 of 20 processing
T1: Memory pressure triggers checkpoint
T2: Checkpoint write to SQLite
T3: SQLite WAL grows large (disk I/O pressure)
T4: Concurrent chunks compete for memory
T5: Despite chunking, aggregate exceeds limit

Failure Mode:
Checkpoint I/O blocking + memory accumulation
```

#### Mitigation
- Async checkpoint writes
- Bounded concurrent chunk processing (max 2)
- Emergency GC between chunks

### Scenario 2: Load Spike (Burst Traffic)

#### Attack Vector: Chunk Queue Saturation
```
Timeline:
T0: 50 agent runs queued as chunks
T1: Each = 10 chunks × 50MB metadata = 500MB queue
T2: Even with max 10 chunks deep, metadata accumulates
T3: Base (128MB) + Queue (500MB) = 628MB
T4: Add active chunks → exceeds 512MB steady target

Failure Mode:
Metadata overhead underestimated
```

#### Mitigation
- Account for metadata in budget
- Strict queue size limits
- Request rejection when saturated

### Scenario 3: Cascading Failure (Retry Storm)

#### Attack Vector: Resume Loop
```
Timeline:
T0: Chunk processing fails (e.g., external API 500)
T1: System retries from checkpoint
T2: Same chunk fails again
T3: Resume → fail → resume loop
T4: Checkpoint reads accumulate
T5: Disk I/O + memory pressure

Failure Mode:
Deterministic failure + resumption = infinite loop
```

#### Mitigation
- Per-chunk retry limits (max 3)
- Progressive backoff on resume
- Mark failed chunks, don't retry forever

### Option B Risk Score: MEDIUM
| Risk | Severity | Mitigation Complexity |
|------|----------|----------------------|
| I/O blocking | Medium | High |
| Metadata bloat | Medium | Low |
| Resume loop | High | Medium |

---

## Option C: Priority Queue - Failure Mode Analysis

### Scenario 1: Memory Pressure (OOM)

#### Attack Vector: Preemption Failure
```
Timeline:
T0: Memory >85%, preempt low-priority task
T1: Task state serialization starts
T2: Serialization itself requires memory
T3: During serialization, memory >95%
T4: Emergency mode triggers
T5: Preemption incomplete, state corrupted
T6: Task cannot resume, data lost

Failure Mode:
Preemption action exacerbates memory pressure
```

#### Mitigation
- Preempt early (at 80%, not 85%)
- Lightweight serialization (streaming to disk)
- Emergency mode kills (not preempts) lowest priority

### Scenario 2: Load Spike (Burst Traffic)

#### Attack Vector: Priority Inversion
```
Timeline:
T0: 5 CRITICAL agents in queue
T1: 2 start executing (slots full)
T2: 3 remain queued (queue full)
T3: New CRITICAL arrives → must reject or evict
T4: If evicting LOW priority, but all are CRITICAL
T5: Either reject new critical or exceed queue limit

Failure Mode:
Queue depth limit conflicts with priority guarantees
```

#### Mitigation
- Reserved slot for CRITICAL (1 of 2 always available)
- Queue slot reservation per priority
- Timeout for queued CRITICAL (fail fast)

### Scenario 3: Cascading Failure (Retry Storm)

#### Attack Vector: Threshold Oscillation
```
Timeline:
T0: Memory 72%, heartbeats skipped
T1: Load decreases, memory 68%
T2: Heartbeats resume (15 tasks)
T3: Memory spikes to 75%
T4: Heartbeats skipped again
T5: Oscillation causes thrashing

Failure Mode:
Rapid threshold crossing = instability
```

#### Mitigation
- Hysteresis: skip at 70%, resume at 60%
- Staggered heartbeat recovery (not all at once)
- Smoothing window for memory readings

### Option C Risk Score: MEDIUM
| Risk | Severity | Mitigation Complexity |
|------|----------|----------------------|
| Preemption panic | High | High |
| Priority inversion | Medium | Medium |
| Threshold thrashing | Medium | Low |

---

## Cross-Option Comparison: Failure Resilience

| Failure Mode | Option A | Option B | Option C |
|--------------|----------|----------|----------|
| **Worker/Task OOM** | Crash + restart | Chunk loss | Preempt or kill |
| **Recovery Speed** | Fast | Slow (resume) | Medium |
| **Data Loss Risk** | High (full task) | Low (chunk only) | Medium |
| **Load Spike Handling** | Poor (queue grows) | Good (backpressure) | Good (shedding) |
| **Cascading Failure** | High risk | Medium risk | Medium risk |
| **Complexity of Recovery** | Low | High | Medium |

---

## Key Insights from Adversarial Review

### 1. No Option is Perfect
- **Option A**: Simple but fragile to worker death
- **Option B**: Memory-efficient but complex recovery
- **Option C**: Adaptive but preemption is risky

### 2. Common Vulnerabilities
- All options need circuit breakers
- All need strict queue depth limits
- All need memory monitoring integration
- All need careful retry logic

### 3. Hybrid Opportunities
- Option A's isolation + Option C's scheduling
- Option B's chunking for specific long tasks
- Option C's thresholds applied to Option A's pool

---

## Phase 3 Complete ✓
**Outcome:** Failure modes identified and assessed. Ready for synthesis of best elements.
