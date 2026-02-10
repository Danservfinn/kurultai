# Jochi Health Check Enhancement Plan
## Comprehensive System Monitoring Implementation

**Date:** 2026-02-10  
**Priority:** HIGH  
**Estimated Effort:** 16 hours  
**Owner:** Jochi (Analyst) + Ögedei (Operations)

---

## Executive Summary

Enhance Jochi's health_check task from basic agent monitoring to comprehensive system-wide health checks. Add Signal health monitoring, system resource tracking, Neo4j performance metrics, security auditing, and external API connectivity checks.

---

## Current State

**Existing health_check (tools/kurultai/agent_tasks.py):**
- Checks Neo4j connectivity
- Verifies agent heartbeats
- Monitors disk space
- Runs every 5 minutes

**Gap:** No Signal health, limited system metrics, no external API checks

---

## Implementation Phases

### Phase 1: Signal Health Monitoring (Week 1)
**Effort:** 4 hours  
**Files:** `tools/kurultai/health/signal_health.py`

#### Tasks

| ID | Task | Description | Acceptance Criteria |
|----|------|-------------|---------------------|
| H1-T1 | Signal daemon check | Verify daemon running on port 8080 | HTTP GET to localhost:8080 returns 200 |
| H1-T2 | Account registration check | Confirm +15165643945 registered | `listAccounts` returns valid account |
| H1-T3 | Send capability test | Send test message to self | Message sent successfully, no errors |
| H1-T4 | Receive capability test | Check for pending messages | Can poll receive endpoint without errors |
| H1-T5 | SSE connection health | Verify event stream accessible | SSE endpoint responds with event stream |
| H1-T6 | Identity trust check | Verify trusted identities | No UNTRUSTED identities for frequent contacts |
| H1-T7 | Rate limit monitoring | Check for rate limit errors | No rate limit errors in last hour |

#### Implementation

```python
# tools/kurultai/health/signal_health.py
class SignalHealthChecker:
    """Signal health monitoring for Jochi"""
    
    def check_daemon(self) -> HealthResult:
        """Verify signal-cli daemon running"""
        try:
            response = requests.get('http://localhost:8080/api/v1/rpc', 
                                  timeout=5)
            return HealthResult(
                component='signal_daemon',
                status='healthy' if response.status_code == 200 else 'unhealthy',
                details={'port': 8080, 'status_code': response.status_code}
            )
        except Exception as e:
            return HealthResult(
                component='signal_daemon',
                status='unhealthy',
                error=str(e)
            )
    
    def check_account(self) -> HealthResult:
        """Verify account registration"""
        # Implementation
        pass
    
    def check_send_capability(self) -> HealthResult:
        """Test message send"""
        # Implementation
        pass
    
    def check_receive_capability(self) -> HealthResult:
        """Test message receive"""
        # Implementation
        pass
```

---

### Phase 2: System Resource Monitoring (Week 1)
**Effort:** 3 hours  
**Files:** `tools/kurultai/health/system_health.py`

#### Tasks

| ID | Task | Description | Thresholds |
|----|------|-------------|------------|
| H2-T1 | Disk space check | Monitor /data and /tmp | Alert if >80% full |
| H2-T2 | Memory usage | Check RAM utilization | Alert if >90% used |
| H2-T3 | CPU load | Monitor load average | Alert if >80% for 5min |
| H2-T4 | Container health | Check docker/container status | Alert if unhealthy |
| H2-T5 | Log file sizes | Monitor log rotation | Alert if >1GB uncompressed |
| H2-T6 | Process count | Check for zombie processes | Alert if >100 zombies |

#### Thresholds

```yaml
system_health_thresholds:
  disk_usage_percent: 80
  memory_usage_percent: 90
  cpu_load_percent: 80
  cpu_load_duration_minutes: 5
  log_size_mb: 1000
  zombie_processes: 100
```

---

### Phase 3: Neo4j Performance Monitoring (Week 2)
**Effort:** 3 hours  
**Files:** `tools/kurultai/health/neo4j_health.py`

#### Tasks

| ID | Task | Description | Query |
|----|------|-------------|-------|
| H3-T1 | Connection health | Test query performance | `MATCH (n) RETURN count(n) LIMIT 1` |
| H3-T2 | Query performance | Monitor slow queries | Check logs for queries >1s |
| H3-T3 | Disk usage | Monitor Neo4j data size | Alert if >80% disk |
| H3-T4 | Index health | Verify indexes are valid | `SHOW INDEXES` |
| H3-T5 | Backup recency | Check last backup time | Alert if >24h old |
| H3-T6 | Memory pressure | Check page cache hit ratio | Alert if <90% |

---

### Phase 4: Agent Health Deep Dive (Week 2)
**Effort:** 2 hours  
**Files:** `tools/kurultai/health/agent_health.py`

#### Tasks

| ID | Task | Description | Metric |
|----|------|-------------|--------|
| H4-T1 | Heartbeat freshness | Check all 6 agents | Alert if >2min stale |
| H4-T2 | Task completion rate | Track success/failure | Alert if <95% success |
| H4-T3 | Error rate tracking | Monitor agent errors | Alert if >5% error rate |
| H4-T4 | Spawn success rate | Track agent spawning | Alert if <90% spawn success |
| H4-T5 | Capability drift | Check for capability gaps | Report missing capabilities |

---

### Phase 5: Task Queue Monitoring (Week 2)
**Effort:** 2 hours  
**Files:** `tools/kurultai/health/task_health.py`

#### Tasks

| ID | Task | Description | Threshold |
|----|------|-------------|-----------|
| H5-T1 | Queue depth | Count pending tasks | Alert if >100 pending |
| H5-T2 | Failed tasks | Monitor task failures | Alert if >10 failed in 1h |
| H5-T3 | Stuck tasks | Find tasks >30min in progress | Alert and retry |
| H5-T4 | Queue trend | Track queue growth rate | Alert if growing >20%/hour |
| H5-T5 | Auto-retry failed | Retry failed tasks | Max 3 retries |

---

### Phase 6: Security Health (Week 3)
**Effort:** 2 hours  
**Files:** `tools/kurultai/health/security_health.py`

#### Tasks

| ID | Task | Description | Action |
|----|------|-------------|--------|
| H6-T1 | HMAC key age | Check key rotation | Alert if >90 days old |
| H6-T2 | Failed auth attempts | Monitor login failures | Alert if >5 failures in 10min |
| H6-T3 | Unusual access patterns | Detect anomalies | ML-based detection |
| H6-T4 | Security audit age | Check last audit | Alert if >7 days old |
| H6-T5 | Certificate expiry | Check SSL certs | Alert if <30 days to expiry |

---

### Phase 7: External API Health (Week 3)
**Effort:** 2 hours  
**Files:** `tools/kurultai/health/external_health.py`

#### Tasks

| ID | Task | Description | Endpoint |
|----|------|-------------|----------|
| H7-T1 | Notion API | Check connectivity | notion.so/v1/users/me |
| H7-T2 | GitHub API | Check rate limits | api.github.com/rate_limit |
| H7-T3 | Parse API | Check health | kind-playfulness-production.up.railway.app/health |
| H7-T4 | OpenClaw gateway | Check status | localhost:18789/health |
| H7-T5 | Railway API | Check deployment status | railway.app API |

---

## Integration Plan

### Update health_check task

```python
# tools/kurultai/agent_tasks.py

async def health_check(driver):
    """Enhanced health check with comprehensive monitoring"""
    
    # Import health checkers
    from .health.signal_health import SignalHealthChecker
    from .health.system_health import SystemHealthChecker
    from .health.neo4j_health import Neo4jHealthChecker
    from .health.agent_health import AgentHealthChecker
    from .health.task_health import TaskHealthChecker
    from .health.security_health import SecurityHealthChecker
    from .health.external_health import ExternalHealthChecker
    
    checkers = [
        SignalHealthChecker(),
        SystemHealthChecker(),
        Neo4jHealthChecker(),
        AgentHealthChecker(),
        TaskHealthChecker(),
        SecurityHealthChecker(),
        ExternalHealthChecker(),
    ]
    
    results = []
    for checker in checkers:
        result = await checker.check()
        results.append(result)
        
        # Log to Neo4j
        log_health_result(driver, result)
        
        # Alert on critical
        if result.status == 'critical':
            await alert_critical(result)
    
    return {
        'summary': summarize_results(results),
        'healthy_count': len([r for r in results if r.status == 'healthy']),
        'warning_count': len([r for r in results if r.status == 'warning']),
        'critical_count': len([r for r in results if r.status == 'critical']),
    }
```

---

## Testing Plan

### Unit Tests
- `tests/health/test_signal_health.py`
- `tests/health/test_system_health.py`
- `tests/health/test_neo4j_health.py`
- `tests/health/test_integration.py`

### Integration Tests
- End-to-end health check flow
- Alert generation verification
- Neo4j logging verification

---

## Monitoring Dashboard

### Neo4j Health Nodes

```cypher
CREATE (h:HealthCheck {
    id: randomUUID(),
    timestamp: datetime(),
    component: 'signal_daemon',
    status: 'healthy',
    details: '{"port": 8080}',
    agent: 'Jochi'
})
```

### Grafana Dashboard
- Health status over time
- Component-specific metrics
- Alert history
- Trend analysis

---

## Rollout Plan

| Week | Deliverables | Verification |
|------|--------------|--------------|
| 1 | Phases 1-2 (Signal + System) | All tests pass, alerts working |
| 2 | Phases 3-5 (Neo4j + Agents + Tasks) | Integration tests pass |
| 3 | Phases 6-7 (Security + External) | Full system verified |
| 4 | Documentation + Training | Team trained on new alerts |

---

## Success Criteria

1. **Coverage:** All 7 health domains monitored
2. **Frequency:** Health checks every 5 minutes
3. **Alerting:** Critical issues alerted within 30 seconds
4. **Reliability:** >99% uptime for health monitoring itself
5. **Documentation:** Full runbook for each alert type

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Health check overload | Stagger checks, use caching |
| False positive alerts | Tune thresholds, use hysteresis |
| Alert fatigue | Prioritize, batch non-critical |
| Circular dependencies | Health check shouldn't depend on healthy system |

---

**Quid testa? Testa frangitur.**

*Implementation begins: 2026-02-10*  
*Target completion: 2026-02-28*
