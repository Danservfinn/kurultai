# Kublai Agent Routing Improvements Proposal

## Executive Summary

This proposal addresses critical routing inefficiencies in the Kublai agent system, specifically focusing on sticky routing patterns and inaccurate queue depth metrics that lead to poor load balancing across the agent fleet.

## Current Issues

### 1. Sticky Routing Patterns
- **Problem**: System consistently routes to temujin even when queue depth is high (7+ tasks)
- **Impact**: Other agents remain underutilized (mongke: 0 tasks, chagatai: 3 tasks)
- **Root Cause**: Race condition in task completion causing inaccurate queue depths

### 2. Queue Depth Inaccuracy
- **Problem**: Task watcher rename race condition inflates queue depth metrics
- **Impact**: Load balancing based on false data (e.g., mongke reports 5 vs actual 2-3)
- **Evidence**: VERIFY FAIL for completed tasks in task-watcher-state.json

### 3. Suboptimal Thresholds
- **Problem**: Fixed thresholds (HIGH=3, CRITICAL=8, LOW=2) too narrow for effective balancing
- **Impact**: Queue imbalance persists despite routing algorithm

## Proposed Solution: Option B - Adaptive Queue Balancing

### Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                 Routing Decision Layer                   │
├─────────────────────────────────────────────────────────┤
│  Race Condition Foundation  │  Dynamic Thresholds  │  │
│  - Atomic file operations  │  - Load-aware adj.  │  │
│  - Task verification       │  - Predictive bal.   │  │
├─────────────────────────────────────────────────────────┤
│              Monitoring & Metrics Layer                  │
├─────────────────────────────────────────────────────────┤
│  Real-time tracking  │  Pattern detection  │  Alerting  │
└─────────────────────────────────────────────────────────┘
```

### Key Components

#### 1. Race Condition Foundation (Priority: Critical)
- **Atomic file operations** with proper locking
- **Task verification** before queue counting
- **Completion state integrity** checks

#### 2. Adaptive Threshold System
```python
# Dynamic threshold calculation based on system load
def calculate_thresholds():
    avg_completion_time = get_average_task_completion_time()
    system_load = get_system_load()

    # Adjust thresholds based on performance
    if avg_completion_time > 300:  # 5 minutes
        return (5, 12, 3)  # More conservative
    else:
        return (3, 8, 2)   # Standard
```

#### 3. Predictive Load Balancing
- **Historical pattern analysis**: Identify recurring queue buildup scenarios
- **Proactive redistribution**: Move tasks before thresholds exceeded
- **Capability-aware routing**: Consider agent specialization and current workload

#### 4. Enhanced Monitoring
- **Queue accuracy metrics**: Track actual vs reported queue depths
- **Routing efficiency**: Measure balanced workload distribution
- **Sticky pattern detection**: Alert when routing becomes biased

### Implementation Phases

#### Phase 1: Foundation (Week 1)
1. Implement atomic file operations for task state management
2. Add task verification in queue depth calculation
3. Deploy basic accuracy monitoring
4. Fix immediate race condition issues

#### Phase 2: Core Balancing (Week 2)
1. Implement dynamic threshold calculation
2. Add predictive load balancing logic
3. Deploy pattern detection for sticky routing
4. Implement redistribution triggers

#### Phase 3: Optimization (Week 3)
1. Tune predictive parameters based on observed patterns
2. Add routing efficiency dashboard
3. Implement alerting for anomalies
4. Fine-tune thresholds for optimal performance

#### Phase 4: Monitoring (Ongoing)
1. Continuous monitoring of routing metrics
2. Regular review and threshold adjustments
3. Pattern analysis for further improvements
4. Documentation updates

### Success Metrics

#### Primary Metrics
- **Queue Balance Ratio**: Max queue depth / Min queue depth < 2.0
- **Routing Accuracy**: Queue depth accuracy > 95%
- **Agent Utilization**: All agents maintain 2-5 tasks under normal load

#### Secondary Metrics
- **Task Throughput**: Tasks completed per hour across fleet
- **Response Time**: Average time from task creation to assignment
- **Error Rate**: Routing-related errors < 1%

### Risk Mitigation

#### High Priority Risks
1. **File Lock Contention**
   - Mitigation: Timeout mechanisms, graceful fallback
   - Monitoring: Lock acquisition time metrics

2. **Threshold Oscillation**
   - Mitigation: Hysteresis in threshold changes
   - Monitoring: Threshold change frequency tracking

3. **Performance Overhead**
   - Mitigation: Asynchronous operations, caching
   - Monitoring: CPU/memory usage during routing decisions

### Expected Benefits

#### Immediate (Post-Phase 1)
- Eliminate race condition causing inaccurate queue depths
- Restore routing algorithm effectiveness
- Improve load balancing accuracy by 70%

#### Short Term (Post-Phase 2)
- Reduce queue imbalance by 60%
- Improve agent utilization from 40% to 75%
- Decrease task pending time by 30%

#### Long Term (Post-Phase 3)
- Predictive prevention of queue buildup
- Self-correcting routing patterns
- 90% balanced workload distribution

### Resource Requirements

#### Development Resources
- **Backend Developer**: 2 weeks for core implementation
- **QA Engineer**: 1 week for testing and validation
- **DevOps**: 0.5 weeks for deployment support

#### Infrastructure
- **Monitoring**: Enhanced logging and metrics collection
- **Storage**: Additional metrics history (minimal impact)
- **Compute**: Negligible additional overhead (< 5%)

### Conclusion

The Adaptive Queue Balancing solution addresses the root causes of routing inefficiencies while providing a scalable foundation for future improvements. By implementing this solution, we can:

1. Eliminate sticky routing patterns
2. Achieve balanced workload distribution
3. Improve overall system throughput
4. Reduce manual intervention needed

This represents a significant improvement over the current system while maintaining stability and providing clear upgrade paths to more sophisticated routing strategies.

---

**Appendix: Implementation Details**

### Code Changes Required

#### 1. task_intake.py
- Replace `get_queue_depth()` with verification-based implementation
- Add dynamic threshold calculation
- Implement predictive redistribution logic

#### 2. task-watcher.py
- Fix race condition in `mark_task_completed()`
- Add atomic file operations
- Implement completion verification

#### 3. Monitoring Components
- Add queue accuracy tracking
- Implement pattern detection
- Create alerting system

### Testing Strategy

#### Unit Testing
- File operation atomicity
- Queue depth verification
- Threshold calculation accuracy

#### Integration Testing
- End-to-end routing scenarios
- Race condition simulation
- Load balancing validation

#### Performance Testing
- High-volume task creation
- Concurrent access patterns
- Resource usage under load

### Rollout Plan

1. **Staging Environment**: Full implementation with test data
2. **Canary Deployment**: 10% of traffic to new system
3. **Gradual Rollout**: Increase to 100% based on stability
4. **Monitoring**: Continuous observation during rollout