# Memory Budget Specification

## Kurultai v2.1 Memory Allocation

**Version:** 1.0.0  
**Date:** 2026-02-13  
**Applies to:** Kurultai v2.1.0+

---

## Executive Summary

This document defines precise memory budgets for each component of the Kurultai v2.1 architecture. All budgets are derived from the 1GB system ceiling and the 512MB steady-state target.

---

## System-Level Budget

```
┌─────────────────────────────────────────────────────────────┐
│                    System Memory Ceiling                      │
│                         1,024 MB                              │
├─────────────────────────────────────────────────────────────┤
│  Main Process          │  200 MB  │  Fixed overhead          │
│  Worker #1             │  512 MB  │  Hard limit (isolated)   │
│  Worker #2             │  512 MB  │  Hard limit (isolated)   │
│  Headroom              │  200 MB  │  GC, spikes, buffers     │
├─────────────────────────────────────────────────────────────┤
│  Total Allocated       │ 1,424 MB │  Overprovisioning ok     │
└─────────────────────────────────────────────────────────────┘

Note: Workers run sequentially, not concurrently at max.
Peak actual usage: 200 + 512 + 200 = 912 MB (safe)
```

---

## Main Process Budget (200 MB)

The main process runs the governance layer and manages workers.

```
┌────────────────────────────────────────────────────────────┐
│                 Main Process: 200 MB                        │
├────────────────────────────────────────────────────────────┤
│  Component                    │ Budget │ Overflow Action   │
├────────────────────────────────────────────────────────────┤
│  Node.js Runtime              │  50 MB │ N/A (base)        │
│  Core Services                │  40 MB │ Reject new work   │
│  Memory Governor              │  10 MB │ N/A (essential)   │
│  Scheduler + Queue            │  20 MB │ Drop heartbeats   │
│  Circuit Breakers             │   5 MB │ N/A (essential)   │
│  IPC/Message Buffers          │  30 MB │ Backpressure      │
│  WebSocket Connections        │  25 MB │ Close idle        │
│  Metrics/Monitoring           │  10 MB │ Reduce frequency  │
│  Logging                      │  10 MB │ Buffer to disk    │
├────────────────────────────────────────────────────────────┤
│  Total                        │ 200 MB │                   │
└────────────────────────────────────────────────────────────┘
```

### Main Process Detailed Breakdown

#### Node.js Runtime (50 MB)
- V8 heap: 30 MB
- Native bindings: 10 MB
- Event loop + libuv: 10 MB

**Overspend Action**: Cannot reduce - fatal error

#### Core Services (40 MB)
- HTTP server: 15 MB
- Route handlers: 10 MB
- Middleware stack: 10 MB
- Configuration: 5 MB

**Overspend Action**: Reject new requests with 503

#### Memory Governor (10 MB)
- Monitoring state: 5 MB
- Threshold tracking: 3 MB
- Event handlers: 2 MB

**Overspend Action**: N/A - critical component

#### Scheduler + Queue (20 MB)
- Queue structures: 10 MB (5 slots × 2 MB)
- Task metadata: 5 MB
- Priority heap: 5 MB

**Overspend Action**: Drop lowest priority items

#### IPC/Message Buffers (30 MB)
- Worker stdout/stderr buffers: 20 MB
- Message serialization: 10 MB

**Overspend Action**: Apply backpressure, slow workers

---

## Worker Process Budget (512 MB hard / 300 MB soft)

Each worker is an isolated Node.js process with enforced limits.

```
┌────────────────────────────────────────────────────────────┐
│               Worker Process: 512 MB (300 soft)             │
├────────────────────────────────────────────────────────────┤
│  Component                    │ Budget │ Limit Type        │
├────────────────────────────────────────────────────────────┤
│  Node.js Runtime              │ 100 MB │ Hard (v8 limit)   │
│  Agent Context/State          │ 100 MB │ Soft (warn)       │
│  Tool Execution               │ 150 MB │ Soft (warn)       │
│  Response Buffering           │ 100 MB │ Soft (warn)       │
│  Session/Connection State     │  50 MB │ Soft (warn)       │
│  Checkpoint/Serialization     │  12 MB │ Hard (essential)  │
├────────────────────────────────────────────────────────────┤
│  Total Soft Limit             │ 300 MB │ Warning + GC      │
│  Total Hard Limit             │ 512 MB │ Kill process      │
└────────────────────────────────────────────────────────────┘
```

### Worker Detailed Breakdown

#### Node.js Runtime (100 MB)
```
V8 heap limit:        512 MB (--max-old-space-size)
Actual runtime usage: 100 MB (baseline)
Available for work:   412 MB
```

#### Agent Context/State (100 MB soft)
- Agent configuration: 20 MB
- Conversation history: 50 MB
- Tool registry: 20 MB
- Internal state: 10 MB

**Soft Limit Exceeded**: Trigger GC, emit warning, continue

#### Tool Execution (150 MB soft)
- Tool subprocesses: 80 MB (spawned tools)
- Input/output buffers: 50 MB
- Temporary files: 20 MB

**Soft Limit Exceeded**: Wait for tools to complete, no new spawns

#### Response Buffering (100 MB soft)
- Streaming buffers: 50 MB
- Response accumulation: 50 MB

**Soft Limit Exceeded**: Flush to disk, stream instead of buffer

#### Checkpoint/Serialization (12 MB hard)
- Reserved for preemption: 10 MB
- State serialization: 2 MB

**Hard Limit**: Always reserved, cannot be used for work

---

## Queue Budget (50 MB)

The bounded queue has fixed maximum memory usage.

```
┌────────────────────────────────────────────────────────────┐
│                  Queue: 50 MB (max 5 slots)                 │
├────────────────────────────────────────────────────────────┤
│  Component                    │ Budget │ Notes             │
├────────────────────────────────────────────────────────────┤
│  Slot metadata (×5)           │  10 MB │ 2 MB per slot     │
│  Task payloads (×5)           │  35 MB │ 7 MB average      │
│  Priority structures          │   5 MB │ Heap + maps       │
├────────────────────────────────────────────────────────────┤
│  Total                        │  50 MB │ Fixed maximum     │
└────────────────────────────────────────────────────────────┘
```

### Queue Slot Budget

Each slot in the queue:
```
Task ID:              1 KB
Priority metadata:    1 KB
Payload reference:    8 KB
Payload data:        7 MB (max)
────────────────────────────
Per slot:            7 MB (typical)
5 slots:            35 MB
```

**Overspend Prevention**: Reject enqueue if payload > 7 MB

---

## Steady-State Memory Target (<512 MB)

### Normal Operation Profile

```
┌────────────────────────────────────────────────────────────┐
│              Steady-State: 350 MB (target <512)             │
├────────────────────────────────────────────────────────────┤
│  Main Process (reduced)       │ 150 MB │ One worker idle   │
│  Worker #1 (active)           │ 200 MB │ Normal agent      │
│  Worker #2 (terminated)       │   0 MB │ Scale-to-zero     │
├────────────────────────────────────────────────────────────┤
│  Total                        │ 350 MB │ 162 MB headroom   │
└────────────────────────────────────────────────────────────┘
```

### High-Load Steady-State

```
Main Process:       180 MB  (slightly elevated)
Worker #1:          250 MB  (active agent)
Worker #2:            0 MB  (queue empty, scaled down)
─────────────────────────────────────
Total:              430 MB  (still under target)
```

---

## Peak Load Memory Profile (1 GB)

### Maximum Load Scenario

```
┌────────────────────────────────────────────────────────────┐
│                Peak Load: 1,000 MB (limit)                  │
├────────────────────────────────────────────────────────────┤
│  Main Process (elevated)      │ 200 MB │ Full governance   │
│  Worker #1 (maxed)            │ 400 MB │ High-load agent   │
│  Worker #2 (maxed)            │ 400 MB │ High-load agent   │
├────────────────────────────────────────────────────────────┤
│  Total                        │ 1,000 MB │ At ceiling      │
└────────────────────────────────────────────────────────────┘
```

### Response to Peak

At 1 GB usage:
1. Memory governor enters EMERGENCY state
2. New work rejected with 503 Service Unavailable
3. Lowest priority task killed if still growing
4. Heartbeats fully suspended

---

## Memory Threshold Actions

| Threshold | Memory | Component Actions |
|-----------|--------|-------------------|
| **Normal** | <700 MB | All operations normal |
| **Warning** | 700-850 MB | Skip heartbeats, trigger GC |
| **Critical** | 850-950 MB | Preempt lowest priority, reject normal tasks |
| **Emergency** | >950 MB | Kill task, reject all new, emergency GC |

### Threshold Hysteresis

```
        950 MB ────────────────▶ EMERGENCY
                 ◀──────── 900 MB clear
        850 MB ────────────────▶ CRITICAL
                 ◀──────── 800 MB clear
        700 MB ────────────────▶ WARNING
                 ◀──────── 600 MB clear
```

---

## Memory Limits by Component

### Hard Limits (Fatal if exceeded)

| Component | Limit | Enforcement |
|-----------|-------|-------------|
| Worker process | 512 MB | `--max-old-space-size=512`, OOM kill |
| Queue payload | 7 MB | Reject at enqueue |
| Queue total | 50 MB | Reject at enqueue |
| Main process | 200 MB | Reject requests, drop connections |

### Soft Limits (Warning + recovery)

| Component | Limit | Action |
|-----------|-------|--------|
| Worker heap | 300 MB | GC, warn, continue |
| Agent context | 100 MB | Warn, suggest chunking |
| Tool execution | 150 MB | Wait, no new spawns |
| Response buffer | 100 MB | Stream to disk |

---

## Memory Monitoring Metrics

```
# Per-component memory (in MB)
kurultai_memory_main_process_mb
kurultai_memory_worker_1_mb
kurultai_memory_worker_2_mb
kurultai_memory_queue_mb

# Budget compliance
kurultai_memory_budget_used_percent
kurultai_memory_budget_available_mb

# Threshold crossings (counter)
kurultai_memory_threshold_crossings_total{level="warning"}
kurultai_memory_threshold_crossings_total{level="critical"}
kurultai_memory_threshold_crossings_total{level="emergency"}

# Recovery actions (counter)
kurultai_memory_recovery_actions_total{action="gc"}
kurultai_memory_recovery_actions_total{action="skip_heartbeat"}
kurultai_memory_recovery_actions_total{action="preempt"}
kurultai_memory_recovery_actions_total{action="kill"}
```

---

## Budget Validation

### Unit Tests Required

```typescript
describe('Memory Budget Compliance', () => {
  test('main process stays under 200MB', async () => {
    const usage = await getMainProcessMemory();
    expect(usage).toBeLessThan(200 * 1024 * 1024);
  });
  
  test('worker stays under 512MB', async () => {
    const worker = spawnWorker();
    await runMaxLoadTask(worker);
    const usage = await getWorkerMemory(worker);
    expect(usage).toBeLessThan(512 * 1024 * 1024);
  });
  
  test('queue rejects oversized payloads', async () => {
    const largePayload = Buffer.alloc(10 * 1024 * 1024); // 10 MB
    await expect(enqueue(largePayload)).rejects.toThrow(/payload too large/);
  });
  
  test('steady-state under 512MB', async () => {
    await runSteadyStateScenario();
    const total = await getTotalMemory();
    expect(total).toBeLessThan(512 * 1024 * 1024);
  });
});
```

---

## Summary Table

| Component | Soft Limit | Hard Limit | Overflow Action |
|-----------|------------|------------|-----------------|
| Main Process | 150 MB | 200 MB | Reject requests |
| Worker | 300 MB | 512 MB | GC / Kill |
| Queue | 40 MB | 50 MB | Reject enqueue |
| Queue Slot | 5 MB | 7 MB | Reject task |
| **System** | **700 MB** | **1024 MB** | **Emergency** |

---

**End of Specification**
