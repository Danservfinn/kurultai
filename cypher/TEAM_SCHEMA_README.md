# Neo4j Schema Extensions for Agent Teams

> **Status**: Design Complete
> **Date**: 2026-02-05
> **Schema Version**: 3 (extends v1, v2 from neo4j.md)

---

## Quick Reference

| File | Purpose |
|------|---------|
| `team_schema_extensions.cypher` | Complete Cypher schema definitions |
| `team_schema_migration.md` | Migration strategy and deployment guide |
| `tools/team_memory.py` | Python implementation module |
| `TEAM_SCHEMA_README.md` | This overview document |

---

## Schema Overview

### New Node Types

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   :AgentTeam    │◄────┤  :TeamMessage   │     │  :TeamResult    │
├─────────────────┤     ├─────────────────┤     ├─────────────────┤
│ id (uuid)       │     │ id (uuid)       │     │ id (uuid)       │
│ name (string)   │     │ team_id (uuid)  │     │ team_id (uuid)  │
│ slug (string)   │     │ message_type    │     │ task_id (uuid)  │
│ lead_agent_id   │     │ content         │     │ aggregated_at   │
│ status (enum)   │     │ from_agent      │     │ aggregation_mode│
│ mission         │     │ to_agent        │     │ summary         │
│ domain          │     │ sent_at         │     │ deliverable     │
│ member_count    │     │ correlation_id  │     │ confidence      │
│ created_at      │     │ access_tier     │     │ quality_score   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
         │
         │ has events
         ▼
┌─────────────────────┐
│:TeamLifecycleEvent  │
├─────────────────────┤
│ id (uuid)           │
│ team_id (uuid)      │
│ event_type (enum)   │
│ previous_state      │
│ new_state           │
│ triggered_by        │
│ triggered_at        │
│ reason              │
│ retained_until      │
└─────────────────────┘
```

### New Relationship Types

```
(:Agent)-[:TEAM_MEMBER {joined_at, role_in_team, status}]->(:AgentTeam)
(:Task)-[:ASSIGNED_TO_TEAM {assigned_at, team_status, claimed_by}]->(:AgentTeam)
(:AgentTeam)-[:PRODUCED]->(:TeamResult)
(:TeamResult)-[:AGGREGATES]->(:Task)
(:AgentTeam)-[:HAS_LIFECYCLE_EVENT]->(:TeamLifecycleEvent)
(:Agent)-[:SENT_MESSAGE]->(:TeamMessage)
```

---

## Team Lifecycle

```
SPAWNING → ACTIVE → PAUSED → SHUTTING_DOWN → DESTROYED
              ↓         ↓           ↓
           (can      (can      (auto or
           pause)   resume)   manual)
```

### State Transitions

| From | To | Trigger |
|------|-----|---------|
| SPAWNING | ACTIVE | Team creation complete |
| ACTIVE | PAUSED | Manual pause / error |
| PAUSED | ACTIVE | Manual resume |
| ACTIVE | SHUTTING_DOWN | Mission complete / timeout |
| SHUTTING_DOWN | DESTROYED | Cleanup complete |

---

## Integration with Task DAG

### Team Tasks in DAG

Team tasks participate fully in the existing Task DAG:

```cypher
// Individual task dependency (existing)
(task1:Task)-[:DEPENDS_ON {type: 'blocks'}]->(task2:Task)

// Team task dependency (new)
(team_task:Task)-[:ASSIGNED_TO_TEAM]->(:AgentTeam)
(team_task)-[:DEPENDS_ON {type: 'blocks'}]->(other_task:Task)
```

### Execution Order

1. **Topological sort** considers all tasks (individual + team)
2. **Team tasks** can be claimed by any active team member
3. **Cross-team dependencies** are resolved through DEPENDS_ON edges
4. **Results aggregation** occurs after all team tasks complete

### Example: Mixed DAG

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Research   │────►│   Strategy  │────►│  Execution  │
│  (Team A)   │     │  (Team B)   │     │  (Team A)   │
└─────────────┘     └─────────────┘     └─────────────┘
       │                   │                   │
       │            ┌──────┘                   │
       ▼            ▼                          ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ Individual  │     │ Individual  │     │  Results    │
│   Task 1    │     │   Task 2    │     │ Aggregation │
└─────────────┘     └─────────────┘     └─────────────┘
```

---

## Common Query Patterns

### Get Agent's Teams
```cypher
MATCH (a:Agent {id: $agent_id})-[m:TEAM_MEMBER {status: 'active'}]->(t:AgentTeam)
WHERE t.status IN ['spawning', 'active', 'paused']
RETURN t.id as team_id, t.name as name, m.role_in_team as role
```

### Get Team's Tasks
```cypher
MATCH (task:Task)-[a:ASSIGNED_TO_TEAM]->(t:AgentTeam {id: $team_id})
RETURN task.id, task.description, a.team_status
ORDER BY task.priority_weight DESC
```

### Claim Team Task (with race condition handling)
```cypher
MATCH (task:Task)-[a:ASSIGNED_TO_TEAM {team_status: 'pending'}]->(t:AgentTeam {id: $team_id})
WHERE task.status = 'pending'
  AND EXISTS { MATCH (:Agent {id: $agent_id})-[:TEAM_MEMBER {status: 'active'}]->(t) }
SET a.team_status = 'claimed', a.claimed_by = $agent_id, task.status = 'in_progress'
RETURN task
```

### Get Team Message Audit Trail
```cypher
MATCH (m:TeamMessage {team_id: $team_id})
WHERE m.sent_at >= $start_time
RETURN m ORDER BY m.sent_at DESC
```

---

## Python API Quick Start

```python
from tools.team_memory import TeamMemory, TeamStatus, TeamMemberRole

async with TeamMemory.create() as tm:
    # Create team
    team_id = await tm.create_team(
        name="Research Alpha",
        lead_agent_id="researcher",
        mission="Quantum computing research",
        domain="research"
    )

    # Add members
    await tm.add_team_member(team_id, "writer", role=TeamMemberRole.MEMBER)

    # Assign task
    await tm.assign_task_to_team(task_id, team_id)

    # Claim task (as team member)
    task = await tm.claim_team_task(agent_id="researcher", team_id=team_id)

    # Record coordination message
    await tm.record_team_message(
        team_id=team_id,
        from_agent="researcher",
        content="Starting research phase",
        to_agent="writer"
    )

    # Aggregate results
    result_id = await tm.aggregate_team_results(
        team_id=team_id,
        parent_task_id=parent_task_id,
        task_ids=[task1_id, task2_id],
        aggregation_mode=AggregationMode.SYNTHESIS,
        summary="Research complete",
        deliverable="Full report...",
        confidence=0.92,
        contributions={"researcher": {...}, "writer": {...}}
    )
```

---

## Migration Path

### Prerequisites
- Neo4j 5.11+ (for vector indexes)
- Existing Kurultai schema v1 or v2
- `tools/memory_integration.py` (OperationalMemory base)

### Migration Steps

1. **Backup database**
   ```bash
   neo4j-admin database dump neo4j --to-path=/backup/pre-teams.dump
   ```

2. **Apply migration**
   ```python
   from migrations.migration_manager import MigrationManager

   manager = MigrationManager(driver)
   manager.migrate(target_version=3)
   ```

3. **Verify migration**
   ```cypher
   SHOW CONSTRAINTS YIELD name WHERE name STARTS WITH 'team_'
   SHOW INDEXES YIELD name WHERE name STARTS WITH 'team_'
   ```

4. **Deploy code**
   - Deploy `tools/team_memory.py`
   - Update services to use TeamMemory

### Rollback

```python
# If issues detected
manager.migrate(target_version=2)  # Rollback to v2
```

---

## Retention Policy

| Data Type | Retention | Cleanup |
|-----------|-----------|---------|
| Active Teams | Indefinite | Manual destruction |
| Destroyed Teams | 90 days | Archive then delete |
| Team Messages | 30 days | Auto-purge |
| Lifecycle Events | 1 year | Configurable |
| Team Results | Indefinite | Manual archive |

---

## Performance Considerations

### Indexes for Common Queries
- `team_status_lookup` - Active team queries
- `team_lead_lookup` - Lead agent lookups
- `team_member_lookup` - Membership queries
- `team_task_lookup` - Task assignment queries
- `team_message_team_lookup` - Audit trail queries

### Query Optimization
- Use `EXISTS {}` subqueries for membership checks
- Filter by `status` before traversing relationships
- Use `LIMIT` for large result sets
- Consider time-based pagination for messages

---

## Security

### Access Control
- `access_tier` field on all team nodes
- `sender_hash` for sender isolation
- Team membership required for task claims

### Audit Trail
- All state changes logged to `:TeamLifecycleEvent`
- All messages recorded in `:TeamMessage`
- Immutable history of team operations

---

## Files Reference

### `/Users/kurultai/molt/cypher/team_schema_extensions.cypher`
Complete Cypher definitions including:
- Node type properties
- Relationship properties
- Constraints and indexes
- Query patterns
- Lifecycle operations
- Integration with Task DAG

### `/Users/kurultai/molt/cypher/team_schema_migration.md`
Migration documentation including:
- Migration script (Python)
- Backward compatibility strategy
- Data migration utilities
- Testing procedures
- Rollback procedures

### `/Users/kurultai/molt/tools/team_memory.py`
Python implementation including:
- `TeamMemory` class
- Data classes (AgentTeam, TeamMember, etc.)
- Enums for statuses and types
- Async/await support
- Comprehensive docstrings

---

## Next Steps

1. Review schema definitions in `team_schema_extensions.cypher`
2. Plan migration using `team_schema_migration.md`
3. Integrate `tools/team_memory.py` into OperationalMemory
4. Test in staging environment
5. Deploy to production

---

## Questions?

Refer to:
- `docs/plans/neo4j.md` - Base schema documentation
- `docs/plans/kurultai_0.1.md` - Task DAG documentation
- `docs/plans/kurultai_0.2.md` - Research/Capability documentation
