# Phase 1: Intent Gathering - Memory Bottleneck Analysis

## Date: 2026-02-13
## Context: Post-Crash Analysis (OOM at 22:52:43Z)

---

## 1. Root Cause Analysis

### 1.1 The Crash Event Timeline
```
22:52:43Z - Kublai OOM-killed by kernel
├── Multiple simultaneous long-running agent runs active
├── Architecture sync endpoint under heavy load (repeated 500 errors)
├── Each sync request consuming memory without release
├── Lane=main queueSize=1 with 406-second duration runs
└── No circuit breaker - continuous retry amplification
```

### 1.2 Memory Bottleneck Identification

| Bottleneck | Evidence | Impact |
|------------|----------|--------|
| **Unbounded Concurrency** | Multiple agents spawned simultaneously | Linear memory growth per agent |
| **Sync Endpoint Hammering** | Repeated 500 errors, each consuming memory | Memory accumulation per failed request |
| **Queue Growth Without Backpressure** | queueSize=1 with 406s runs | Tasks pile up, memory compounds |
| **Synchronous Heartbeats** | 15 tasks every 5 minutes regardless of load | Predictable memory spikes |
| **No Memory Budgeting** | No RAM limits or OOM protection | Uncontrolled memory consumption |
| **Retry Without Backoff** | Immediate retry on failures | Amplifies resource pressure |
| **Session Accumulation** | WebSocket + agent run stacking | Connection state memory overhead |

---

## 2. Memory Usage Pattern Analysis

### 2.1 Steady-State Components
```
Base System:              ~128MB
├── Node.js runtime:      ~50MB
├── Core services:        ~48MB
├── WebSocket connections: ~20MB (baseline)
└── Monitoring/Metrics:   ~10MB
```

### 2.2 Per-Agent Memory Cost
```
Single Agent Run:         ~150-250MB
├── Agent context/state:  ~50MB
├── Tool executions:      ~80-150MB (variable)
├── Response buffering:   ~20-50MB
└── Session overhead:     ~10MB
```

### 2.3 Problem: Concurrent Multiplication
```
1 agent:   128MB + 200MB = 328MB      ✓ OK
2 agents:  128MB + 400MB = 528MB      ⚠ Near limit
3 agents:  128MB + 600MB = 728MB      ✗ Risk
4+ agents: 128MB + 800MB+ = 928MB+    ✗ OOM likely
```

---

## 3. Success Metrics Definition

### 3.1 Primary Targets
| Metric | Target | Rationale |
|--------|--------|-----------|
| **Steady-state memory** | <512MB | 2x headroom over base + 1 idle agent |
| **Peak memory under load** | <1GB | Accommodates 2 concurrent + headroom |
| **Max concurrent agents** | 2 | Prevents unbounded multiplication |
| **Max queue depth** | 5 | Limits backlog accumulation |
| **Memory growth rate** | <10MB/min under load | Early warning threshold |

### 3.2 Operational Metrics
| Metric | Target | Implementation |
|--------|--------|----------------|
| **Circuit breaker threshold** | 3 failures in 60s | Prevents retry amplification |
| **Heartbeat skip threshold** | Memory >70% (~700MB) | Adaptive load shedding |
| **Task preemption trigger** | Memory >85% (~850MB) | Emergency resource recovery |
| **OOM protection trigger** | Memory >95% (~950MB) | Graceful degradation |

### 3.3 Performance Metrics (Trade-off Acceptance)
| Metric | Acceptable Range | Notes |
|--------|-----------------|-------|
| **Agent latency increase** | +20-50% acceptable | Trade for stability |
| **Queue wait time** | <5 minutes max | User experience bound |
| **Heartbeat task deferral** | Up to 30 minutes | Non-critical tasks only |

---

## 4. Constraints & Non-Goals

### 4.1 Constraints
- Must maintain existing API compatibility
- No external infrastructure changes (same hardware)
- Must preserve all existing functionality
- Rollback capability required

### 4.2 Non-Goals
- Not optimizing for latency (stability first)
- Not adding distributed computing
- Not changing data storage architecture
- Not modifying core agent logic

---

## 5. Key Questions Answered

1. **What exactly causes OOM?** 
   → Unbounded concurrent agent runs (200MB+ each) stacking up

2. **Why did the sync endpoint cause problems?**
   → Each 500 error created orphaned memory; no cleanup + immediate retry = death spiral

3. **What's the memory budget per component?**
   → Base: 128MB, Per-agent: 150-250MB, Queue slot: 50MB overhead

4. **When should we shed load?**
   → At 70% memory (skip heartbeats), 85% (preempt low-priority), 95% (emergency)

5. **What's the safe concurrency limit?**
   → 2 concurrent agents = 400-500MB + 128MB base = ~650MB (safe headroom)

---

## Phase 1 Complete ✓
**Outcome:** Clear bottleneck identification and quantified success metrics ready for architecture exploration.
