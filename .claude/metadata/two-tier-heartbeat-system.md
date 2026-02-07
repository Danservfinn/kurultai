---
title: Two-Tier Heartbeat System Specification
link: two-tier-heartbeat-system
type: metadata
tags: [heartbeat, monitoring, failover, health-check]
ontological_relations:
  - relates_to: [[kurultai-project-overview]]
  - relates_to: [[ogedei-failover-activation]]
uuid: 550e8400-e29b-41d4-a716-446655440005
created_at: 2026-02-07T12:00:00Z
updated_at: 2026-02-07T12:00:00Z
---

# Two-Tier Heartbeat System Specification

## Overview

Kurultai uses a two-tier heartbeat system to distinguish between infrastructure health and functional agent activity. This enables Ögedei to make intelligent failover decisions.

## Tiers

### Infrastructure Heartbeat
- **Property**: `Agent.infra_heartbeat`
- **Written By**: `heartbeat_writer.py` sidecar process
- **Interval**: Every 30 seconds
- **Threshold**: 120 seconds (4 missed intervals)
- **Failure Type**: HARD failure
- **Indicates**: Agent process/infrastructure is down

### Functional Heartbeat
- **Property**: `Agent.last_heartbeat`
- **Written By**: `claim_task()` and `complete_task()` in OperationalMemory
- **Interval**: On task operations (event-driven)
- **Threshold**: 90 seconds
- **Failure Type**: SOFT failure
- **Indicates**: Agent is alive but not processing tasks

## Neo4j Node Schema

```cypher
// Agent node with both heartbeat properties
CREATE (a:Agent {
  name: "kublai",
  infra_heartbeat: "2026-02-07T12:00:00Z",
  last_heartbeat: "2026-02-07T12:00:30Z"
})
```

## Threshold Standardization

All components use consistent thresholds:

| Component | Infra Threshold | Functional Threshold |
|-----------|-----------------|---------------------|
| Failover Protocol | 120s | 90s |
| Delegation Routing | 120s | - |
| Failover Monitor | - | 90s |

## Failover Decision Matrix

| Infra Age | Functional Age | Status | Action |
|-----------|----------------|--------|--------|
| < 30s | < 90s | Healthy | None |
| > 120s | Any | HARD_FAILURE | Immediate Ögedei activation |
| Any | > 90s | SOFT_FAILURE | Monitor, log warning |
| > 120s | > 90s | CRITICAL | Immediate Ögedei activation |

## Implementation

### Heartbeat Writer (Sidecar)
```python
# heartbeat_writer.py
import asyncio
from datetime import datetime

WRITE_INTERVAL = 30  # seconds

async def write_infra_heartbeat():
    while True:
        timestamp = datetime.utcnow().isoformat()
        await memory.update_agent_property(
            "main", 
            "infra_heartbeat", 
            timestamp
        )
        await asyncio.sleep(WRITE_INTERVAL)
```

### Functional Heartbeat (Task Operations)
```python
# OperationalMemory.claim_task()
async def claim_task(task_id, agent_id):
    # ... claim logic ...
    
    # Update functional heartbeat
    await self.update_agent_property(
        agent_id,
        "last_heartbeat",
        datetime.utcnow().isoformat()
    )
```

### Circuit Breaker
After 3 consecutive write failures, the sidecar pauses for 60 seconds before retrying.

## Migration Notes

- **Old System**: Separate `AgentHeartbeat` nodes
- **New System**: Properties on `Agent` node
- **Migration**: Run `v3_heartbeat_migration.py` to consolidate

## Monitoring

Jochi's test orchestrator monitors both heartbeat types and generates alerts:
- **Critical**: Infra heartbeat > 120s (immediate action)
- **Warning**: Functional heartbeat > 90s (investigate)
- **Info**: Heartbeat recovery (log)
