# Kublai Agent Memory - Main Project

## Recent Critical Issues (2026-03-08)

### Model Configuration Crisis
- **Issue:** GLM-5 model drift causing reflection failures
- **Impact:** Hourly reflections completely broken, 50% success rate
- **Root Cause:** settings.json ANTHROPIC_MODEL overriding config.json
- **Fix Applied:** Option 1 proposal for proactive configuration validation

### Fake Completion Bug
- **Issue:** Systemic fake completions in task execution pipeline
- **Impact:** Queue inflation, ledger reconciliation failures
- **Frequency:** Recurring every 2-3 hours
- **Fix Applied:** Option 3 proposal for root cause fix

### Queue Imbalance Crisis
- **Issue:** Ogedei accumulating 2125s old tasks
- **Impact:** System throughput degradation, poor load balancing
- **Root Cause:** Static thresholds not adapting to workload patterns
- **Fix Applied:** Option 2 proposal for predictive routing

## Routing System Improvements (2026-03-08)

### Current Load-Balancing Thresholds
- HIGH=3 (was 20), CRITICAL=8 (was 30), LOW=2 (was 5)
- Working correctly but overwhelmed by configuration drift

### Proposed Solutions
1. **Proactive Configuration Validation** - Priority 1
   - Real-time model validation with auto-correction
   - Prevents reflection failures before they happen
   - Self-healing system architecture

2. **Enhanced Queue Management** - Priority 2
   - Predictive routing using historical patterns
   - Dynamic thresholds adjusting for peak hours
   - Task type classification for accurate routing

3. **Fake Completion Root Cause Fix** - Priority 3
   - Atomic operations for task state changes
   - Race condition prevention in completion markers
   - Post-execution verification system

## Key Learnings

### Agent Communication
- Gateway-router shows sticky routing to Temujin regardless of queue depth
- Secondary agents (Ogedei, Chagatai) being starved
- Need audit of auto_dispatch.py queue_depth fallback logic

### System Stability
- 7 missed ticks in reporting window indicates systemic instability
- Queue audit system effectively identifying fake completions
- Ledger reconciliation shows -15 delta (Neo4j vs actual ledger)

## WHEN/THEN Rules

### Routing Accuracy Rules
- **WHEN** task contains "model error" **THEN** route to ogedei for immediate fix
- **WHEN** queue depth > HIGH_THRESHOLD AND agent has < LOW_THRESHOLD **THEN** redistribute to underutilized agent
- **WHEN** task classification ambiguous AND multiple agents capable **THEN** use predictive routing based on historical completion times

### Delegation Rules
- **WHEN** skill_hint present in task **THEN** prioritize agent with that skill
- **WHEN** task explicitly mentions code review **THEN** route to jochi regardless of other keywords
- **WHEN** task mentions architecture/design AND code **THEN** route to temujin (development domain includes architecture)

### System Health Rules
- **WHEN** model configuration drift detected **THEN** auto-correct and alert
- **WHEN** fake completion detected in audit **THEN** trigger pipeline fix investigation
- **WHEN** agent queue age > 1800s (30min) **THEN** trigger redistribution alert

## Future Improvements

### Short Term (1-2 weeks)
- Implement configuration validation system
- Fix fake completion root cause
- Improve routing disambiguation rules

### Medium Term (1 month)
- Implement predictive routing
- Add agent capability monitoring
- Create routing performance dashboard

### Long Term (3 months)
- Machine learning-based task routing
- Dynamic agent capability scaling
- Cross-agent optimization algorithms

## Coordination Patterns

### Weekly Synchronization
- Every Monday: Review routing effectiveness metrics
- Every Wednesday: Audit agent workload distribution
- Every Friday: Analyze failure patterns and adjust rules

### Alert System
- Critical failures: Immediate notification to all agents
- Configuration drift: Auto-correct with human oversight
- Queue imbalances: Proactive redistribution before threshold breach

## Performance Benchmarks

### Current Targets
- Task completion success rate: >90%
- Average task completion time: <1 hour
- Queue redistribution accuracy: >95%
- Model configuration accuracy: 100%

### Improvement Goals
- Success rate: 95%+
- Completion time: <45 minutes
- Redistribution accuracy: >98%
- Zero configuration failures

## Code Reference

### Key Files
- `scripts/task_intake.py` - Main routing logic
- `scripts/agent-task-handler.py` - Task execution
- `logs/routing-decisions.jsonl` - Routing decisions log
- `logs/completion-audit.jsonl` - Task completion audit

### Configuration
- Queue thresholds: HIGH=3, CRITICAL=8, LOW=2
- Failure bypass: 80% failure rate threshold
- Model validation: Real-time checking against canonical config