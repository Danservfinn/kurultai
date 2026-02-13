# Phase 2: Parallel Domain Exploration

## Three Alternative Architectures for Memory Optimization

---

## Option A: Process Pool with Memory Limits (Resource-Constrained)

### Concept
Isolate agent runs in separate worker processes with hard memory limits enforced by the OS. The main process acts as a scheduler/queue manager.

### Architecture Diagram
```
┌─────────────────────────────────────────────────────────────┐
│                    Main Process (Controller)                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │   Queue      │  │   Memory     │  │  Circuit Breaker │   │
│  │   Manager    │  │   Monitor    │  │                  │   │
│  │  (max 5)     │  │  (v8+sys)    │  │  (3/60s rule)    │   │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘   │
└─────────┼─────────────────┼───────────────────┼─────────────┘
          │                 │                   │
          ▼                 ▼                   ▼
┌─────────────────────────────────────────────────────────────┐
│                  Process Pool (max 2 workers)                │
│  ┌─────────────────┐        ┌─────────────────┐             │
│  │   Worker #1     │        │   Worker #2     │             │
│  │  (400MB limit)  │        │  (400MB limit)  │             │
│  │                 │        │                 │             │
│  │  ┌───────────┐  │        │  ┌───────────┐  │             │
│  │  │ Agent Run │  │        │  │ Agent Run │  │             │
│  │  │ + Context │  │        │  │ + Context │  │             │
│  │  └───────────┘  │        │  └───────────┘  │             │
│  └─────────────────┘        └─────────────────┘             │
└─────────────────────────────────────────────────────────────┘
```

### Key Mechanisms
1. **Process Isolation**: Each agent runs in forked Node.js process
2. **OOM Killer Protection**: `--max-old-space-size=400` per worker
3. **Pool Management**: Generic-pool or custom implementation with max 2
4. **Queue**: Bull/BullMQ with Redis for persistence
5. **Memory Enforcement**: `resourceLimits` in Worker Threads or process limits

### Pros
- ✅ Hard memory boundaries (OS-enforced)
- ✅ Single worker crash doesn't kill main process
- ✅ Simple mental model
- ✅ Easy to implement with existing libraries

### Cons
- ❌ Process spawn overhead (~100-200ms per agent)
- ❌ Memory fragmentation across processes
- ❌ IPC complexity for WebSocket/session state
- ❌ Redis dependency adds infrastructure
- ❌ Doesn't solve heartbeat/memory monitoring

### Memory Profile
```
Base:           128MB (main process)
Worker #1:      400MB max (isolated)
Worker #2:      400MB max (isolated)
Queue:          50MB overhead
─────────────────────────────
Total Peak:     978MB (within 1GB target)
```

---

## Option B: Streaming/Chunked Agent Execution (Memory-Bound)

### Concept
Replace monolithic agent runs with streaming/chunked execution. Process work in small, bounded chunks with checkpoint/resume capability.

### Architecture Diagram
```
┌─────────────────────────────────────────────────────────────────┐
│                     Stream Controller                           │
│  ┌─────────────────┐  ┌─────────────────┐  ┌────────────────┐   │
│  │  Chunk Queue    │  │  Checkpoint     │  │  Memory        │   │
│  │  (bounded)      │  │  Store          │  │  Governor      │   │
│  │  max 10 chunks  │  │  (SQLite/disk)  │  │  (<512MB)      │   │
│  └────────┬────────┘  └────────┬────────┘  └───────┬────────┘   │
└───────────┼────────────────────┼───────────────────┼────────────┘
            │                    │                   │
            ▼                    ▼                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Chunk Processor (single thread)                  │
│                                                                   │
│   ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐      │
│   │ Chunk 1 │───▶│ Chunk 2 │───▶│ Chunk 3 │───▶│ Chunk N │      │
│   │ (50MB)  │    │ (50MB)  │    │ (50MB)  │    │ (50MB)  │      │
│   └─────────┘    └─────────┘    └─────────┘    └─────────┘      │
│        │                                              │          │
│        └────────────── Checkpoint ────────────────────┘          │
│                        (every chunk)                              │
└─────────────────────────────────────────────────────────────────┘
```

### Key Mechanisms
1. **Work Decomposition**: Break agent runs into discrete steps
2. **Bounded Buffering**: Max 50MB per chunk, max 10 chunks queued
3. **Streaming Responses**: Use Node.js streams, accumulate to disk not RAM
4. **Checkpoint/Resume**: Save state to SQLite after each chunk
5. **Backpressure**: Pause input when chunk queue full

### Pros
- ✅ Predictable memory usage (bounded by chunk size × concurrency)
- ✅ No external dependencies (Redis, etc.)
- ✅ Natural backpressure through streams
- ✅ Can pause/resume long-running tasks
- ✅ Fits Node.js event loop model

### Cons
- ❌ Requires significant refactoring of agent execution
- ❌ Checkpointing adds latency
- ❌ Complex state machine for resumption
- ❌ Not all operations are easily chunkable
- ❌ Tool calls may not be interruptible

### Memory Profile
```
Base:              128MB
Active Chunk:      50MB (being processed)
Chunk Queue:       50MB × 3 = 150MB (max 10, but limited by concurrency)
Checkpoint Cache:  50MB
Stream Buffers:    50MB
─────────────────────────────
Total Peak:        428MB (well under 512MB target)
```

---

## Option C: Priority Queue with Task Preemption (Load-Adaptive)

### Concept
Unified priority queue with memory-aware scheduling. Low-priority tasks can be preempted or skipped when memory pressure detected.

### Architecture Diagram
```
┌─────────────────────────────────────────────────────────────────┐
│                    Adaptive Scheduler                           │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Priority Queue (max depth 5)               │   │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐    │   │
│  │  │P0:CRIT  │  │P1:HIGH  │  │P2:NORM  │  │P3:LOW   │... │   │
│  │  │Agent    │  │Agent    │  │Agent    │  │HB Task  │    │   │
│  │  └─────────┘  └─────────┘  └─────────┘  └─────────┘    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌────────────────┐  │
│  │ Memory Monitor  │  │ Preemption      │  │ Circuit        │  │
│  │ (real-time)     │  │ Controller      │  │ Breaker        │  │
│  │                 │  │                 │  │                │  │
│  │ <70%: Normal    │  │ Can suspend     │  │ 3 fails/60s    │  │
│  │ >70%: Skip HB   │  │ low-priority    │  │ → open         │  │
│  │ >85%: Preempt   │  │ tasks           │  │ → half-open    │  │
│  │ >95%: Emergency │  │                 │  │ → closed       │  │
│  └─────────────────┘  └─────────────────┘  └────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Execution Slots (max 2 concurrent)               │
│  ┌─────────────────┐        ┌─────────────────┐                  │
│  │   Slot #1       │        │   Slot #2       │                  │
│  │   (400MB max)   │        │   (400MB max)   │                  │
│  │   Can preempt   │        │   Can preempt   │                  │
│  └─────────────────┘        └─────────────────┘                  │
└─────────────────────────────────────────────────────────────────┘
```

### Key Mechanisms
1. **Priority Levels**: CRITICAL (agents), HIGH, NORMAL, LOW (heartbeats)
2. **Memory Thresholds**: 70% (skip low), 85% (preempt), 95% (emergency)
3. **Preemption**: Save state, free memory, resume later
4. **Load Shedding**: Skip non-critical tasks under pressure
5. **Soft Memory Limits**: Monitor v8 heap + RSS, enforce caps

### Pros
- ✅ Fine-grained control over resource allocation
- ✅ Graceful degradation under load
- ✅ Existing code needs minimal changes
- ✅ Can adapt to varying load patterns
- ✅ Heartbeats naturally deprioritized

### Cons
- ❌ Preemption logic is complex
- ❌ State serialization overhead
- ❌ Risk of priority inversion
- ❌ Requires careful tuning of thresholds
- ❌ Soft limits can be exceeded briefly

### Memory Profile
```
Base:                128MB
Slot #1 (active):    200MB average, 400MB max
Slot #2 (active):    200MB average, 400MB max
Queue overhead:      50MB
Preemption state:    50MB
─────────────────────────────
Normal:              628MB
Peak (pre-emption):  478MB (after shedding load)
```

---

## Option Comparison Summary

| Aspect | Option A: Process Pool | Option B: Streaming | Option C: Priority Queue |
|--------|------------------------|---------------------|--------------------------|
| **Peak Memory** | 978MB | 428MB | 628MB (normal) |
| **Steady-State** | 528MB | 278MB | 378MB |
| **Complexity** | Medium | High | Medium-High |
| **Refactoring** | Low | High | Medium |
| **External Deps** | Redis | None | None |
| **Fault Isolation** | Excellent | Poor | Poor |
| **Backpressure** | Queue-based | Stream-native | Priority-based |
| **Heartbeat Handling** | Not addressed | Not addressed | Built-in |

---

## Preliminary Assessment

### Option A Best For:
- Quick implementation
- Strong isolation requirements
- Existing Redis infrastructure

### Option B Best For:
- Maximum memory efficiency
- Long-running task handling
- Stream-friendly workloads

### Option C Best For:
- Balanced approach
- Adaptive behavior needs
- Graceful degradation priority

---

## Phase 2 Complete ✓
**Outcome:** Three distinct architectural approaches documented with trade-offs. Ready for adversarial review.
