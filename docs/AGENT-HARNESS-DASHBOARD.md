# Agent Harness Health Dashboard - Neo4j Queries

**Version:** 2.0
**Last Updated:** 2026-03-12
**Status:** Active

## Overview

The Agent Harness Health Dashboard provides comprehensive monitoring of the OpenClaw multi-agent system through Neo4j queries. This document covers queries for:

- **Agent Harness Health Checks** - Component integrity monitoring
- **Task Tracking** - Completion rates, bottlenecks, workload balance
- **System Health** - Gateway, Neo4j, Redis, service status
- **Conversion Tracking** - User funnel analytics (Parse platform)
- **Human Profiles** - User consent and preferences

## Quick Start

```python
from neo4j import GraphDatabase

driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'password'))

with driver.session() as session:
    result = session.run("""
        MATCH (h:AgentHarnessHealthCheck)
        RETURN h.timestamp as timestamp,
               h.health_score as health_score
        ORDER BY h.timestamp DESC
        LIMIT 1
    """)
    print(result.single())

driver.close()
```

---

## Agent Harness Health Checks

### Latest Health Check

```cypher
MATCH (h:AgentHarnessHealthCheck)
RETURN h.timestamp as timestamp,
       h.health_score as health_score,
       h.passed_checks as passed,
       h.total_checks as total
ORDER BY h.timestamp DESC
LIMIT 1
```

### Health Trend (Last 24 Hours)

```cypher
MATCH (h:AgentHarnessHealthCheck)
WHERE h.timestamp > datetime() - duration('PT24H')
RETURN h.timestamp as timestamp,
       h.health_score as health_score,
       h.passed_checks as passed,
       h.total_checks as total
ORDER BY h.timestamp DESC
```

### Health Score Over Time (7 Days)

```cypher
MATCH (h:AgentHarnessHealthCheck)
WHERE h.timestamp > datetime() - duration('P7D')
RETURN date(h.timestamp) as date,
       avg(h.health_score) as avg_health_score,
       min(h.health_score) as min_score,
       max(h.health_score) as max_score
ORDER BY date DESC
```

### Component Health Breakdown (24 Hours)

```cypher
MATCH (h:AgentHarnessHealthCheck)
WHERE h.timestamp > datetime() - duration('PT24H')
RETURN
  avg(h.hooks_executable * 100.0 / h.hooks_total) as hooks_executable_pct,
  avg(h.hooks_integrated * 100.0 / 2) as hooks_integrated_pct,
  avg(h.specs_exist * 100.0 / h.specs_total) as specs_pct,
  avg(h.examples_exist * 100.0 / h.examples_total) as examples_pct,
  avg(h.agents_documented * 100.0 / h.agents_total) as agents_pct,
  avg(h.readme_exists * 100.0) as readme_pct,
  avg(h.neo4j_logging * 100.0) as neo4j_logging_pct
```

### Critical Issues Alert

```cypher
// Alert if health score drops below 80%
MATCH (h:AgentHarnessHealthCheck)
WHERE h.timestamp > datetime() - duration('PT1H')
  AND h.health_score < 80
RETURN h.timestamp as timestamp,
       h.health_score as health_score,
       h.passed_checks as passed,
       h.total_checks as total
ORDER BY h.timestamp DESC
```

### Summary Statistics (7 Days)

```cypher
MATCH (h:AgentHarnessHealthCheck)
WHERE h.timestamp > datetime() - duration('P7D')
RETURN
  count(h) as total_checks,
  avg(h.health_score) as avg_health_score,
  min(h.health_score) as min_score,
  max(h.health_score) as max_score,
  stdev(h.health_score) as stddev
```

---

## Task Tracking Metrics

### Hourly Task Summary

```cypher
MATCH (t:Task)
WHERE t.created > datetime() - duration('PT1H')
WITH t.agent as agent, count(t) as created
OPTIONAL MATCH (c:TaskCompletion)
WHERE c.completed_at > datetime() - duration('PT1H')
  AND c.agent = agent
WITH agent, created, count(c) as completed
RETURN agent, created, completed,
  (completed * 100.0 / nullif(created, 0)) as completion_rate
ORDER BY agent
```

### Completion Rate (24 Hours)

```cypher
MATCH (t:Task)
WHERE t.created > datetime() - duration('PT24H')
WITH count(t) as total
OPTIONAL MATCH (c:TaskCompletion)
WHERE c.completed_at > datetime() - duration('PT24H')
WITH total, count(c) as completed
RETURN total, completed,
  (completed * 100.0 / nullif(total, 0)) as success_rate
```

### Agent Bottlenecks (24 Hours)

```cypher
MATCH (t1:Task)-[:RETRIED]->(t2:Task)
WHERE t1.created > datetime() - duration('PT24H')
RETURN t1.agent as agent,
       t1.label as label,
       count(t1) as retries
ORDER BY retries DESC
LIMIT 10
```

### Agent Workload (7 Days)

```cypher
MATCH (t:Task)
WHERE t.created > datetime() - duration('P7D')
RETURN t.agent as agent,
       count(t) as total_tasks,
       sum(CASE WHEN t.status = 'done' THEN 1 ELSE 0 END) as completed,
       sum(CASE WHEN t.status = 'failed' THEN 1 ELSE 0 END) as failed,
       sum(CASE WHEN t.status = 'pending' THEN 1 ELSE 0 END) as pending
ORDER BY total_tasks DESC
```

### Hypothesis Validation Status

```cypher
MATCH (h:Hypothesis)
RETURN
  count(CASE WHEN h.status = 'pending' THEN 1 END) as pending,
  count(CASE WHEN h.status = 'validated' THEN 1 END) as validated,
  count(CASE WHEN h.status = 'expired' THEN 1 END) as expired,
  count(CASE WHEN h.status = 'rejected' THEN 1 END) as rejected
```

### Tasks by Status (Hourly)

```cypher
MATCH (t:Task)
WHERE t.created > datetime() - duration('PT1H')
RETURN t.status as status, count(t) as count
ORDER BY count DESC
```

---

## System Health Monitoring

### Active Rules Count

```cypher
MATCH (r:Rule)
WHERE r.active = true
RETURN count(r) as active_rules
```

### Failed Tasks (24 Hours)

```cypher
MATCH (t:Task)
WHERE t.status = 'failed'
  AND t.created > datetime() - duration('PT24H')
RETURN t.agent as agent,
       t.label as label,
       t.error as error,
       t.created as timestamp
ORDER BY t.created DESC
```

### Long-Running Tasks (>2 Hours)

```cypher
MATCH (t:Task)
WHERE t.status = 'executing'
  AND t.created < datetime() - duration('PT2H')
RETURN t.agent as agent,
       t.label as label,
       t.created as started,
       duration.between(t.created, datetime()).hours as hours_running
ORDER BY started ASC
```

---

## Conversion Tracking (Parse Platform)

### Funnel Statistics (30 Days)

```cypher
MATCH (fe:FunnelEvent)
WHERE fe.event_date > datetime() - duration('P30D')
WITH count(DISTINCT fe.human_id) as total_leads
OPTIONAL MATCH (cc:ConversionContext)
WHERE cc.first_touch_date > datetime() - duration('P30D')
  AND cc.subscription_status IN ['trial', 'pro_monthly', 'pro_annual', 'enterprise']
WITH total_leads, count(DISTINCT cc.human_id) as converted
RETURN total_leads, converted,
  (converted * 1.0 / nullif(total_leads, 0)) as conversion_rate
```

### Funnel Events by Type

```cypher
MATCH (fe:FunnelEvent)
WHERE fe.event_date > datetime() - duration('P30D')
RETURN fe.event_type as event_type, count(fe) as count
ORDER BY count DESC
```

### Conversion by Source

```cypher
MATCH (cc:ConversionContext)
WHERE cc.first_touch_date > datetime() - duration('P30D')
WITH cc.first_touch_source as source, count(cc) as total
OPTIONAL MATCH (cc2:ConversionContext)
WHERE cc2.first_touch_source = source
  AND cc2.first_touch_date > datetime() - duration('P30D')
  AND cc2.subscription_status IN ['trial', 'pro_monthly', 'pro_annual', 'enterprise']
WITH source, total, count(DISTINCT cc2.human_id) as converted
RETURN source, total, converted,
  (converted * 1.0 / nullif(total, 0)) as conversion_rate
ORDER BY converted DESC
```

### Monthly Recurring Revenue (MRR)

```cypher
MATCH (cc:ConversionContext)
WHERE cc.subscription_status IN ['pro_monthly', 'pro_annual', 'enterprise']
  AND (cc.subscription_end IS NULL OR cc.subscription_end > datetime())
RETURN sum(cc.mrr_cents) / 100.0 as total_mrr_dollars,
  count(cc) as active_subscribers
```

### Pricing Page Views to Checkout

```cypher
MATCH (fe:FunnelEvent {event_type: 'pricing_view'})
WHERE fe.event_date > datetime() - duration('P30D')
WITH count(DISTINCT fe.human_id) as pricing_views
OPTIONAL MATCH (fe2:FunnelEvent {event_type: 'checkout_start'})
WHERE fe2.event_date > datetime() - duration('P30D')
WITH pricing_views, count(DISTINCT fe2.human_id) as checkouts
RETURN pricing_views, checkouts,
  (checkouts * 1.0 / nullif(pricing_views, 0)) as checkout_rate
```

---

## Human Profile & Consent

### Users by Consent Category

```cypher
MATCH (hp:HumanProfile)
UNWIND keys(hp.consent) as category
RETURN category, count(*) as users_with_consent
ORDER BY users_with_consent DESC
```

### Marketing Consent Users

```cypher
MATCH (hp:HumanProfile)
WHERE hp.consent.marketing = true
RETURN count(hp) as marketing_consent_users
```

### Consent Change History

```cypher
MATCH (hp:HumanProfile)-[r:CONSENT_CHANGE]->(:History)
RETURN r.category as category,
       r.from_value as from_value,
       r.to_value as to_value,
       r.timestamp as changed_at
ORDER BY changed_at DESC
LIMIT 20
```

---

## Utility Scripts Reference

The following Python scripts provide programmatic access to these metrics:

| Script | Purpose | Location |
|--------|---------|----------|
| `health_dashboard.py` | System health aggregation | `main/scripts/` |
| `neo4j_task_tracker.py` | Task CRUD and queries | `main/scripts/` |
| `monitoring_utils.py` | Queue depth utilities | `main/scripts/` |
| `dashboard_utils.py` | Terminal dashboard rendering | `main/scripts/` |
| `system-health-check.py` | Unified health monitoring | `main/scripts/` |
| `neo4j_conversion_tracker.py` | Conversion funnel tracking | `main/scripts/` |
| `neo4j_human_profile.py` | Human profile management | `main/scripts/` |

### Python Usage Example

```python
from scripts.neo4j_task_tracker import get_tracker
from scripts.monitoring_utils import get_system_health

# Get task metrics from Neo4j
tracker = get_tracker()
hourly = tracker.get_hourly_summary(hours=1)
completion = tracker.get_completion_rate(hours=24)
bottlenecks = tracker.get_bottlenecks(hours=24)

# Get queue depths from filesystem
health = get_system_health()
print(f"Status: {health['status']}")
print(f"Queue totals: {health['queue_totals']}")
```

---

## Web Dashboard

A web-based dashboard is available at:

```
http://localhost:18789/dashboard
```

Features:
- Real-time task status by agent
- Pending/executing/failed/done counts
- Task retry and archive actions
- Auto-refresh every 10 seconds

---

## Health Check Schema

### AgentHarnessHealthCheck Node

```cypher
(:AgentHarnessHealthCheck {
  timestamp: datetime,
  health_score: float,           // 0-100
  passed_checks: int,
  total_checks: int,

  // Component metrics
  hooks_executable: int,
  hooks_total: int,
  hooks_integrated: int,         // out of 2
  specs_exist: int,
  specs_total: int,
  examples_exist: int,
  examples_total: int,
  agents_documented: int,
  agents_total: int,
  readme_exists: int,            // 0 or 1
  neo4j_logging: int             // 0 or 1
})
```

### Task Node

```cypher
(:Task {
  label: string,
  agent: string,
  status: string,                // pending, executing, done, failed
  created: datetime,
  completed: datetime,
  error: string,
  retry_count: int
})
```

### TaskCompletion Node

```cypher
(:TaskCompletion {
  task_id: string,
  agent: string,
  label: string,
  completed_at: datetime,
  success: boolean
})
```

### ConversionContext Node

```cypher
(:ConversionContext {
  context_id: string,
  human_id: string,
  first_touch_date: datetime,
  first_touch_source: string,
  pricing_views: int,
  checkout_attempts: int,
  subscription_status: string,
  mrr_cents: int,
  conversion_trigger: string
})
```

---

## Alert Thresholds

| Metric | Warning | Critical |
|--------|---------|----------|
| Health Score | < 90% | < 80% |
| Queue Depth (per agent) | > 10 | > 20 |
| Failed Tasks (1h) | > 3 | > 5 |
| Stale Executing (>2h) | > 1 | > 3 |
| Completion Rate (24h) | < 80% | < 60% |

---

## Resolution

Documentation updated to reflect:
- Added system health monitoring queries (Gateway, Neo4j, Redis)
- Added conversion tracking queries for Parse platform
- Added task tracking metrics (completion rates, bottlenecks, workload)
- Added human profile and consent queries
- Added web dashboard reference
- Added utility scripts reference table
- Added health check schema documentation
- Added alert threshold guidelines
- Updated timestamp to 2026-03-12

**Next steps:** None (documentation update complete)
