---
title: Delegation Protocol Pattern
link: delegation-protocol
type: patterns
tags: [patterns, delegation, routing, complexity-scoring]
ontological_relations:
  - relates_to: [[kurultai-project-overview]]
  - relates_to: [[two-tier-heartbeat-system]]
uuid: 550e8400-e29b-41d4-a716-446655440004
created_at: 2026-02-07T17:00:00Z
updated_at: 2026-02-07T17:00:00Z
---

# Delegation Protocol Pattern

## Overview

The Delegation Protocol is Kurultai's core routing mechanism that classifies incoming tasks and routes them to appropriate agents based on complexity, capability requirements, and current agent availability.

## Flow

```
User Request → Kublai Receives
                ↓
         Complexity Analysis
                ↓
    ┌───────────┴───────────┐
    ↓                       ↓
Low Complexity        High Complexity
Direct Route          Team Assembly
    ↓                       ↓
Specialist Agent    Multi-Agent Workflow
    ↓                       ↓
                 Synthesis & Response
```

## Complexity Scoring

### Factors
1. **Scope**: Number of distinct subtasks
2. **Depth**: Technical depth required
3. **Dependencies**: External system dependencies
4. **Uncertainty**: Ambiguity in requirements
5. **Risk**: Security/safety implications

### Score Ranges
- **0.0-0.3**: Simple (direct to specialist)
- **0.3-0.6**: Medium (small team 2-3 agents)
- **0.6-0.8**: Complex (team 3-5 agents)
- **0.8-1.0**: Very complex (full team 5-8 agents)

## Agent Selection

### Capability Matrix
| Agent | Capabilities | Complexity Range |
|-------|--------------|------------------|
| Kublai | Orchestration, synthesis | All (orchestrator only) |
| Möngke | Research, search, summarize | 0.0-0.6 |
| Chagatai | Writing, documentation | 0.0-0.5 |
| Temüjin | Development, architecture | 0.3-1.0 |
| Jochi | Analysis, security review | 0.2-0.8 |
| Ögedei | Operations, monitoring | N/A (failover only) |

### Routing Rules
1. **Below threshold**: Direct route to best-fit specialist
2. **Above threshold**: Form team with complementary capabilities
3. **Capability check**: Verify agent has required capabilities
4. **Availability check**: Confirm agent heartbeat is current (120s infra, 90s functional)

## Task Lifecycle

```
PENDING → CLAIMED → IN_PROGRESS → COMPLETED
           ↓                         ↓
      TIMEOUT                   FAILED
           ↓                         ↓
      REASSIGN              REASSIGN
```

### State Transitions
- **PENDING**: Task created in Neo4j, awaiting claim
- **CLAIMED**: Agent claimed task (atomic operation)
- **IN_PROGRESS**: Agent actively processing
- **COMPLETED**: Task finished successfully
- **TIMEOUT**: Task exceeded SLA, reassign
- **FAILED**: Agent error, reassign with context

## Failure Recovery

### Retry Strategy
- **Timeout**: Reassign to different agent (max 3 attempts)
- **Failure**: Add failure context, reassign
- **Cascading**: Escalate to Ögedei after 3 failures

### Rollback
```python
# On agent failure
async def handle_failure(task_id, agent_id, error):
    # Mark task as failed
    await memory.update_task_status(task_id, "failed", error=str(error))

    # Claim count check
    claims = await memory.get_claim_count(task_id)
    if claims >= 3:
        # Escalate to Ögedei
        await escalate_to_ogedei(task_id)
    else:
        # Reassign with failure context
        await delegation.reassign(task_id, exclude=[agent_id])
```

## Implementation Notes

- **Atomic Claims**: Neo4j Cypher ensures exactly one agent can claim
- **Heartbeat Check**: 120s threshold for infra heartbeat availability (see [[two-tier-heartbeat-system]])
- **Capability CBAC**: Capability-Based Access Control for skill routing
- **DAG Support**: Tasks can have dependencies for complex workflows
