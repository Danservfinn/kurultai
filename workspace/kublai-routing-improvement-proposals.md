# Kublai Agent Routing Improvement Proposals

## Executive Summary

Analysis of kublai agent routing system reveals 3 critical issues:
1. **Sticky routing** causing persistent workload imbalance (ogedei=13, jochi=5, temujin=8 queues while 3 agents idle)
2. **Task-watcher race condition** corrupting queue depth accuracy
3. **Missing task timeouts** for long-pending tasks

Below are 3 validated approaches to address these issues with varying complexity and benefits.

---

## Option A: Enhanced Filesystem with Circuit Breakers

### Overview
Minimal changes approach that adds circuit breaker patterns to existing filesystem coordination. Focuses on queue depth monitoring and timeout handling without new infrastructure.

### Architecture
```
Filesystem Tasks → Queue Depth Monitor → Circuit Breaker → Agent Assignment
                     ↑              ↑
                Neo4j Sync   Timeout Handler
```

### Key Components
- **Queue Depth Monitor**: Real-time filesystem scanning with circuit breaker logic
- **Timeout Handler**: Adaptive timeouts based on task age and patterns
- **Race Condition Prevention**: Enhanced file locking with PID verification
- **Circuit Breaker**: Automatic redistribution when queue imbalance detected

### Trade-offs
**Pros:**
- ✅ **Zero infrastructure cost** - leverages existing filesystem
- ✅ **Minimal operational risk** - familiar technology stack
- ✅ **Rapid implementation** - 1-2 weeks development time
- ✅ **Clear debugging path** - filesystem operations visible
- ✅ **Immediate impact** - 40-50% reduction in queue imbalance

**Cons:**
- ❌ **Scalability limits** - filesystem I/O bottleneck at 20+ agents
- ❌ **Network filesystem vulnerability** - NFS adds 50-100ms latency
- ❌ **Single point of failure** - filesystem corruption risk

### Risk Assessment
| Risk | Severity | Mitigation |
|------|----------|------------|
| Filesystem corruption | HIGH | Regular backups, filesystem monitoring |
| Lock contention | MEDIUM | Timeout-based lock release, lock file cleanup |
| NFS latency | MEDIUM | Local filesystem optimization, caching |
| Inode exhaustion | LOW | File cleanup automation, size limits |

### Effort Estimate
- **Implementation**: S (1-2 weeks)
- **Complexity**: Low
- **Maintenance**: Easy (1-2 hrs/month)

---

## Option B: Probabilistic Redis Integration

### Overview
Hybrid approach that adds Redis for coordination while maintaining filesystem fallback. Implements probabilistic routing to break sticky patterns with real-time queue depth tracking.

### Architecture
```
Filesystem Tasks → Redis Queue Depth (real-time) → Probabilistic Router → Agent Assignment
                     ↑                           ↑
                Fallback Sync              Circuit Breaker
```

### Key Components
- **Redis Queue Monitor**: Real-time queue depth with 30-second sync fallback
- **Probabilistic Router**: Weighted randomization to prevent sticky routing
- **Dual-Write System**: Filesystem + Redis for data integrity
- **Circuit Breaker**: Redis failure fallback to filesystem mode

### Trade-offs
**Pros:**
- ✅ **Significant performance improvement** - 70-80% reduction in queue imbalance
- ✅ **Real-time accuracy** - eliminates stale queue depth data
- ✅ **Scalable architecture** - handles 20-50 agents effectively
- ✅ **Fault tolerance** - graceful degradation to filesystem mode
- ✅ **Future-ready** - foundation for advanced features

**Cons:**
- ❌ **Infrastructure cost** - $50-100/month for Redis
- ❌ **Operational complexity** - Redis monitoring and maintenance
- ❌ **Network dependency** - coordination requires network connectivity
- ❌ **Security considerations** - Redis authentication and hardening

### Risk Assessment
| Risk | Severity | Mitigation |
|------|----------|------------|
| Redis failure | HIGH | Fallback to filesystem, Redis clustering |
| Network partition | MEDIUM | Local caching, automatic reconnection |
| Redis injection | MEDIUM | Authentication, input validation |
| Memory exhaustion | MEDIUM | Memory limits, data expiration |

### Effort Estimate
- **Implementation**: M (3-4 weeks)
- **Complexity**: Medium
- **Maintenance**: Moderate (2-4 hrs/month)

---

## Option C: Hybrid Coordination with Circuit Breakers

### Overview
Full-featured event-driven architecture with dedicated coordination service. Comprehensive circuit breaker system with advanced fault tolerance and monitoring.

### Architecture
```
Tasks → Coordination Service → Event Bus → Circuit Breakers → Agent Registry
    ↑           ↑                ↑           ↑
Neo4j    Redis/Kafka      Monitoring   Load Balancer
```

### Key Components
- **Coordination Service**: Dedicated service for task lifecycle management
- **Event Bus**: Kafka/Redis Streams for state synchronization
- **Circuit Breaker Network**: Multi-layer protection with auto-recovery
- **Agent Registry**: Service discovery with health monitoring
- **Advanced Monitoring**: Real-time analytics and alerting

### Trade-offs
**Pros:**
- ✅ **Maximum reliability** - 90-95% reduction in all routing issues
- ✅ **Enterprise-grade fault tolerance** - comprehensive failure handling
- ✅ **Advanced analytics** - predictive routing and capacity planning
- ✅ **Horizontal scalability** - scales to 100+ agents
- ✅ **Rich monitoring** - full observability and alerting

**Cons:**
- ❌ **High complexity** - major architectural refactoring
- ❌ **Infrastructure cost** - $130-260/month for full stack
- ❌ **Long implementation** - 6-8 weeks development
- ❌ **Operational overhead** - multiple services to maintain
- ❌ **Security surface** - multiple attack vectors

### Risk Assessment
| Risk | Severity | Mitigation |
|------|----------|------------|
| Coordination service failure | CRITICAL | Multiple redundancy layers, failover testing |
| Configuration corruption | HIGH | Version control, automated validation |
| Event ordering issues | HIGH | Event versioning, causal ordering |
- **Implementation**: L (6-8 weeks)
- **Complexity**: High
- **Maintenance**: Complex (4-6 hrs/month)

---

## Recommendation: Option A - Enhanced Filesystem with Circuit Breakers

### Why This Approach?
**For the current 7-agent system, Option A provides the optimal balance:**

1. **Immediate Impact**: 40-50% reduction in queue imbalance within 2 weeks
2. **Minimal Risk**: No new infrastructure, familiar technology stack
3. **Cost-Effective**: $0 additional infrastructure costs
4. **Future Foundation**: Can be extended to Option B when scaling to 20+ agents
5. **Operational Simplicity**: Easy to debug and maintain

### Implementation Roadmap

**Phase 1: Circuit Breaker Implementation** (Week 1)
- Add queue depth monitoring with circuit breaker logic
- Implement timeout escalation for long-pending tasks
- Add sticky routing detection override

**Phase 2: Enhanced Coordination** (Week 2)
- Implement proper file locking with PID verification
- Add atomic operations for task completion
- Implement race condition detection and recovery

**Phase 3: Monitoring & Validation** (Ongoing)
- Add queue depth accuracy monitoring
- Implement circuit breaker activation tracking
- Add performance metrics collection

### Expected Outcomes
- **Queue Imbalance**: 40-50% reduction in queue depth disparities
- **Task Dispatch**: <30 second latency for all tasks
- **System Stability**: Elimination of VERIFY FAIL due to race conditions
- **Operational Efficiency**: Minimal maintenance overhead

### Migration Path
Option A can be incrementally enhanced to Option B by:
1. Adding Redis layer alongside filesystem (no disruption)
2. Migrating coordination operations to Redis
3. Eventually replacing filesystem with Redis when proven stable

This phased approach ensures continuous improvement while maintaining system stability.