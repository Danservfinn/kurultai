# Neo4j Schema Migration: Agent Teams Support

> **Status**: Design Document
> **Date**: 2026-02-05
> **Depends On**: `docs/plans/neo4j.md`, `docs/plans/kurultai_0.1.md`
> **Migration Version**: 3 (extends existing migrations in neo4j.md)

---

## Executive Summary

This document describes the migration strategy for adding Agent Team support to the existing Kurultai Neo4j schema. The migration adds team tracking capabilities while maintaining full backward compatibility with existing tasks and agents.

### Key Migration Principles

1. **Zero-Downtime**: New schema elements are additive only
2. **Backward Compatible**: Existing tasks continue to work without modification
3. **Gradual Adoption**: Teams can be adopted incrementally
4. **Safe Rollback**: All changes are reversible

---

## Migration Overview

### Schema Version History

| Version | Description | Status |
|---------|-------------|--------|
| 1 | Initial schema - Agent nodes, Task nodes, indexes | Applied |
| 2 | Vector index for semantic search | Applied |
| 3 | **Agent Teams support** (this migration) | Pending |

### New Schema Elements

| Element | Type | Purpose |
|---------|------|---------|
| `:AgentTeam` | Node | Team composition and lifecycle |
| `:TEAM_MEMBER` | Relationship | Agent membership in teams |
| `:ASSIGNED_TO_TEAM` | Relationship | Task-to-team assignments |
| `:TeamMessage` | Node | Inter-team message audit |
| `:TeamResult` | Node | Aggregated team results |
| `:TeamLifecycleEvent` | Node | Team state change audit |

---

## Migration Script

### Migration 3: Agent Teams Support

```python
# migrations/v3_agent_teams.py
"""Migration v3: Add Agent Team support to Kurultai schema."""

MIGRATION = {
    'version': 3,
    'description': 'Add AgentTeam nodes, team relationships, and team audit trail',
    'up': '''
        // ================================================================
        // UNIQUE CONSTRAINTS
        // ================================================================

        CREATE CONSTRAINT team_id_unique IF NOT EXISTS
          FOR (t:AgentTeam) REQUIRE t.id IS UNIQUE;

        CREATE CONSTRAINT team_slug_unique IF NOT EXISTS
          FOR (t:AgentTeam) REQUIRE t.slug IS UNIQUE;

        CREATE CONSTRAINT team_message_id_unique IF NOT EXISTS
          FOR (m:TeamMessage) REQUIRE m.id IS UNIQUE;

        CREATE CONSTRAINT team_result_id_unique IF NOT EXISTS
          FOR (r:TeamResult) REQUIRE r.id IS UNIQUE;

        CREATE CONSTRAINT team_lifecycle_event_id_unique IF NOT EXISTS
          FOR (e:TeamLifecycleEvent) REQUIRE e.id IS UNIQUE;

        // ================================================================
        // PERFORMANCE INDEXES
        // ================================================================

        // Team lookup indexes
        CREATE INDEX team_status_lookup IF NOT EXISTS
          FOR (t:AgentTeam) ON (t.status, t.created_at);

        CREATE INDEX team_lead_lookup IF NOT EXISTS
          FOR (t:AgentTeam) ON (t.lead_agent_id, t.status);

        CREATE INDEX team_domain_lookup IF NOT EXISTS
          FOR (t:AgentTeam) ON (t.domain, t.status);

        CREATE INDEX team_sender_lookup IF NOT EXISTS
          FOR (t:AgentTeam) ON (t.sender_hash, t.status);

        // Team activity tracking
        CREATE INDEX team_activity_lookup IF NOT EXISTS
          FOR (t:AgentTeam) ON (t.last_activity_at, t.status)
          WHERE t.status = 'active';

        // Team member relationship index
        CREATE INDEX team_member_lookup IF NOT EXISTS
          FOR ()-[r:TEAM_MEMBER]-() ON (r.status, r.joined_at);

        // Team task assignment index
        CREATE INDEX team_task_lookup IF NOT EXISTS
          FOR ()-[r:ASSIGNED_TO_TEAM]-() ON (r.team_status, r.assigned_at);

        // Message audit trail indexes
        CREATE INDEX team_message_team_lookup IF NOT EXISTS
          FOR (m:TeamMessage) ON (m.team_id, m.sent_at);

        CREATE INDEX team_message_correlation_lookup IF NOT EXISTS
          FOR (m:TeamMessage) ON (m.correlation_id, m.sent_at);

        CREATE INDEX team_message_sender_lookup IF NOT EXISTS
          FOR (m:TeamMessage) ON (m.from_agent, m.sent_at);

        // Results aggregation indexes
        CREATE INDEX team_result_team_lookup IF NOT EXISTS
          FOR (r:TeamResult) ON (r.team_id, r.aggregated_at);

        CREATE INDEX team_result_task_lookup IF NOT EXISTS
          FOR (r:TeamResult) ON (r.task_id, r.aggregated_at);

        // Lifecycle event indexes
        CREATE INDEX team_lifecycle_team_lookup IF NOT EXISTS
          FOR (e:TeamLifecycleEvent) ON (e.team_id, e.triggered_at);

        CREATE INDEX team_lifecycle_event_type_lookup IF NOT EXISTS
          FOR (e:TeamLifecycleEvent) ON (e.event_type, e.triggered_at);

        CREATE INDEX team_lifecycle_retention_lookup IF NOT EXISTS
          FOR (e:TeamLifecycleEvent) ON (e.retained_until)
          WHERE e.retained_until IS NOT NULL;

        // Full-text index for team search
        CREATE FULLTEXT INDEX team_search IF NOT EXISTS
          FOR (t:AgentTeam) ON EACH [t.name, t.mission];

        // ================================================================
        // SYSTEM TEAMS (Optional - create default teams)
        // ================================================================

        // Create a system team for research tasks (optional)
        MERGE (t:AgentTeam {slug: 'system-research'})
        ON CREATE SET
          t.id = randomUUID(),
          t.name = 'System Research Team',
          t.lead_agent_id = 'researcher',
          t.max_members = 3,
          t.member_count = 1,
          t.mission = 'Default team for research tasks',
          t.required_capabilities = ['deep_research', 'fact_checking', 'synthesis'],
          t.domain = 'research',
          t.status = 'active',
          t.status_changed_at = datetime(),
          t.created_at = datetime(),
          t.created_by = 'system',
          t.auto_destroy_on_complete = false,
          t.idle_timeout_hours = 24,
          t.last_activity_at = datetime(),
          t.results_aggregation_mode = 'synthesis',
          t.access_tier = 'PUBLIC'

        WITH t
        MATCH (lead:Agent {id: 'researcher'})
        MERGE (lead)-[m:TEAM_MEMBER]->(t)
        ON CREATE SET
          m.joined_at = datetime(),
          m.joined_reason = 'system',
          m.role_in_team = 'lead',
          m.capabilities_contributed = lead.primary_capabilities,
          m.status = 'active',
          m.tasks_completed = 0,
          m.tasks_claimed = 0

        // Create lifecycle event for system team
        CREATE (e:TeamLifecycleEvent {
          id: randomUUID(),
          team_id: t.id,
          event_type: 'created',
          new_state: 'active',
          triggered_by: 'system',
          triggered_at: datetime(),
          reason: 'System team created during migration v3'
        })

        RETURN 'Migration v3 applied successfully' as result;
    ''',
    'down': '''
        // ================================================================
        // ROLLBACK: Remove Agent Team Support
        // ================================================================

        // Note: This rollback preserves data by creating backup nodes
        // before deletion. Run with caution in production.

        // Backup teams before deletion
        MATCH (t:AgentTeam)
        CREATE (backup:AgentTeamBackup {
          original_id: t.id,
          name: t.name,
          slug: t.slug,
          lead_agent_id: t.lead_agent_id,
          member_count: t.member_count,
          mission: t.mission,
          domain: t.domain,
          status: t.status,
          created_at: t.created_at,
          destroyed_at: t.destroyed_at,
          backed_up_at: datetime(),
          migration_version: 3
        });

        // Backup team results
        MATCH (r:TeamResult)
        CREATE (backup:TeamResultBackup {
          original_id: r.id,
          team_id: r.team_id,
          task_id: r.task_id,
          aggregated_at: r.aggregated_at,
          summary: r.summary,
          backed_up_at: datetime(),
          migration_version: 3
        });

        // Delete all team-related nodes and relationships
        MATCH (t:AgentTeam)
        OPTIONAL MATCH (t)<-[:TEAM_MEMBER]-()
        OPTIONAL MATCH (t)<-[a:ASSIGNED_TO_TEAM]-()
        OPTIONAL MATCH (t)-[:PRODUCED]->(r:TeamResult)
        OPTIONAL MATCH (t)-[:HAS_LIFECYCLE_EVENT]->(e:TeamLifecycleEvent)
        DETACH DELETE t, r, e;

        // Delete team messages
        MATCH (m:TeamMessage)
        DETACH DELETE m;

        // Drop constraints
        DROP CONSTRAINT team_id_unique IF EXISTS;
        DROP CONSTRAINT team_slug_unique IF EXISTS;
        DROP CONSTRAINT team_message_id_unique IF EXISTS;
        DROP CONSTRAINT team_result_id_unique IF EXISTS;
        DROP CONSTRAINT team_lifecycle_event_id_unique IF EXISTS;

        // Drop indexes
        DROP INDEX team_status_lookup IF EXISTS;
        DROP INDEX team_lead_lookup IF EXISTS;
        DROP INDEX team_domain_lookup IF EXISTS;
        DROP INDEX team_sender_lookup IF EXISTS;
        DROP INDEX team_activity_lookup IF EXISTS;
        DROP INDEX team_member_lookup IF EXISTS;
        DROP INDEX team_task_lookup IF EXISTS;
        DROP INDEX team_message_team_lookup IF EXISTS;
        DROP INDEX team_message_correlation_lookup IF EXISTS;
        DROP INDEX team_message_sender_lookup IF EXISTS;
        DROP INDEX team_result_team_lookup IF EXISTS;
        DROP INDEX team_result_task_lookup IF EXISTS;
        DROP INDEX team_lifecycle_team_lookup IF EXISTS;
        DROP INDEX team_lifecycle_event_type_lookup IF EXISTS;
        DROP INDEX team_lifecycle_retention_lookup IF EXISTS;
        DROP INDEX team_search IF EXISTS;

        RETURN 'Migration v3 rolled back - data backed up to *Backup nodes' as result;
    '''
}
```

---

## Backward Compatibility Strategy

### Existing Task Handling

Existing tasks without team assignments continue to work unchanged:

```cypher
// Existing tasks remain valid
MATCH (t:Task)
WHERE NOT (t)-[:ASSIGNED_TO_TEAM]->(:AgentTeam)
RETURN t.id as individual_task_id, t.status as status
```

### Mixed Mode Support

The system supports both individual and team tasks simultaneously:

```python
# Pseudo-code for task dispatch
def get_ready_tasks(sender_hash=None):
    """Get all ready tasks (both individual and team)."""

    # Individual tasks (existing behavior)
    individual_tasks = query("""
        MATCH (task:Task)
        WHERE task.status = 'pending'
          AND NOT (task)-[:ASSIGNED_TO_TEAM]->(:AgentTeam)
          AND NOT EXISTS {
            MATCH (task)<-[:DEPENDS_ON {type: 'blocks'}]-(blocker:Task)
            WHERE blocker.status <> 'completed'
          }
        RETURN task
    """)

    # Team tasks (new behavior)
    team_tasks = query("""
        MATCH (task:Task)-[a:ASSIGNED_TO_TEAM {team_status: 'pending'}]->(t:AgentTeam)
        WHERE task.status = 'pending'
          AND t.status = 'active'
          AND NOT EXISTS {
            MATCH (task)<-[:DEPENDS_ON {type: 'blocks'}]-(blocker:Task)
            WHERE blocker.status <> 'completed'
          }
        RETURN task, t as team
    """)

    return individual_tasks + team_tasks
```

### Agent Compatibility

Agents can participate in both individual and team tasks:

```cypher
// Agent can claim individual tasks
MATCH (a:Agent {id: 'researcher'})-[:ASSIGNED_TO]->(t:Task {status: 'pending'})
...

// Agent can claim team tasks (if team member)
MATCH (a:Agent {id: 'researcher'})-[:TEAM_MEMBER {status: 'active'}]->(team:AgentTeam)
MATCH (task:Task)-[ta:ASSIGNED_TO_TEAM {team_status: 'pending'}]->(team)
...
```

---

## Data Migration (Optional)

### Converting Existing Tasks to Team Tasks

For gradual adoption, existing tasks can be migrated to team tasks:

```python
def migrate_tasks_to_team(task_ids: list[str], team_id: str, assigned_by: str):
    """
    Migrate existing individual tasks to team assignment.

    Args:
        task_ids: List of task IDs to migrate
        team_id: Target team ID
        assigned_by: Agent ID performing the migration
    """
    query = """
        MATCH (task:Task)
        WHERE task.id IN $task_ids
          AND NOT (task)-[:ASSIGNED_TO_TEAM]->(:AgentTeam)
        MATCH (team:AgentTeam {id: $team_id})
        CREATE (task)-[:ASSIGNED_TO_TEAM {
            assigned_at: datetime(),
            assigned_by: $assigned_by,
            assignment_reason: 'migration',
            team_status: CASE task.status
                WHEN 'pending' THEN 'pending'
                WHEN 'in_progress' THEN 'claimed'
                ELSE 'completed'
            END,
            claimed_by: task.claimed_by,
            claimed_at: datetime()
        }]->(team)
        RETURN task.id as migrated_task_id
    """
    return execute(query, {
        'task_ids': task_ids,
        'team_id': team_id,
        'assigned_by': assigned_by
    })
```

### Batch Migration Script

```python
# scripts/migrate_tasks_to_teams.py
"""Batch migration script for converting tasks to team tasks."""

import argparse
from neo4j import GraphDatabase

class TaskMigration:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def get_migratable_tasks(self, task_type=None, limit=100):
        """Get tasks that can be migrated to team assignment."""
        query = """
            MATCH (task:Task)
            WHERE task.status IN ['pending', 'ready']
              AND NOT (task)-[:ASSIGNED_TO_TEAM]->(:AgentTeam)
              AND ($task_type IS NULL OR task.type = $task_type)
            RETURN task.id as id, task.description as description, task.type as type
            LIMIT $limit
        """
        with self.driver.session() as session:
            result = session.run(query, {
                'task_type': task_type,
                'limit': limit
            })
            return [dict(record) for record in result]

    def migrate_to_team(self, task_ids, team_id, dry_run=True):
        """Migrate tasks to team assignment."""
        if dry_run:
            print(f"[DRY RUN] Would migrate {len(task_ids)} tasks to team {team_id}")
            return []

        query = """
            MATCH (task:Task)
            WHERE task.id IN $task_ids
              AND NOT (task)-[:ASSIGNED_TO_TEAM]->(:AgentTeam)
            MATCH (team:AgentTeam {id: $team_id})
            CREATE (task)-[a:ASSIGNED_TO_TEAM {
                assigned_at: datetime(),
                assigned_by: 'migration_script',
                assignment_reason: 'batch_migration',
                team_status: 'pending',
                claimed_by: null,
                claimed_at: null
            }]->(team)
            SET team.last_activity_at = datetime()
            RETURN task.id as task_id, team.id as team_id
        """
        with self.driver.session() as session:
            result = session.run(query, {
                'task_ids': task_ids,
                'team_id': team_id
            })
            return [dict(record) for record in result]

    def verify_migration(self, team_id):
        """Verify migrated tasks are properly assigned."""
        query = """
            MATCH (task:Task)-[a:ASSIGNED_TO_TEAM]->(team:AgentTeam {id: $team_id})
            RETURN
                count(task) as total_tasks,
                count(CASE WHEN a.team_status = 'pending' THEN 1 END) as pending,
                count(CASE WHEN a.team_status = 'claimed' THEN 1 END) as claimed,
                count(CASE WHEN a.team_status = 'completed' THEN 1 END) as completed
        """
        with self.driver.session() as session:
            result = session.run(query, {'team_id': team_id})
            return dict(result.single())

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Migrate tasks to team assignment')
    parser.add_argument('--team-id', required=True, help='Target team ID')
    parser.add_argument('--task-type', help='Filter by task type')
    parser.add_argument('--limit', type=int, default=100, help='Max tasks to migrate')
    parser.add_argument('--dry-run', action='store_true', help='Preview without changes')

    args = parser.parse_args()

    migrator = TaskMigration(
        uri='bolt://localhost:7687',
        user='neo4j',
        password='password'
    )

    # Get migratable tasks
    tasks = migrator.get_migratable_tasks(args.task_type, args.limit)
    print(f"Found {len(tasks)} tasks to migrate")

    # Migrate
    task_ids = [t['id'] for t in tasks]
    migrated = migrator.migrate_to_team(task_ids, args.team_id, args.dry_run)

    # Verify
    if not args.dry_run:
        stats = migrator.verify_migration(args.team_id)
        print(f"Migration complete: {stats}")
```

---

## Integration Points

### 1. OperationalMemory Module

Extend `openclaw_memory.py` with team-aware methods:

```python
class OperationalMemory:
    # ... existing methods ...

    def create_team(self, name: str, lead_agent_id: str, **kwargs) -> str:
        """Create a new agent team."""
        # Implementation using team_schema_extensions.cypher
        pass

    def assign_task_to_team(self, task_id: str, team_id: str) -> bool:
        """Assign an existing task to a team."""
        pass

    def claim_team_task(self, agent_id: str, team_id: str) -> Optional[Task]:
        """Claim a pending task assigned to agent's team."""
        pass

    def record_team_message(self, team_id: str, from_agent: str,
                          content: str, **kwargs) -> str:
        """Record a message in team audit trail."""
        pass

    def aggregate_team_results(self, team_id: str, task_ids: List[str]) -> str:
        """Aggregate completed team tasks into TeamResult."""
        pass
```

### 2. TopologicalExecutor

Modify the executor to handle team tasks:

```python
class TopologicalExecutor:
    def get_ready_tasks(self) -> List[Task]:
        """Get all ready tasks (individual and team)."""
        # Query from team_schema_extensions.cypher
        # "Topological execution with team awareness" section
        pass

    def can_execute(self, agent_id: str, task: Task) -> bool:
        """Check if agent can execute task (individual or team member)."""
        if task.assigned_to:
            # Individual task
            return task.assigned_to == agent_id
        elif task.team_id:
            # Team task - check membership
            return self.is_team_member(agent_id, task.team_id)
        return False
```

### 3. DelegationProtocol

Add team-aware delegation:

```python
class DelegationProtocol:
    def delegate_to_team(self, task_id: str, team_id: str,
                        gateway_url: str) -> bool:
        """Delegate task to team via agentToAgent."""
        # 1. Assign task to team
        # 2. Notify team lead via agentToAgent
        # 3. Record in TeamMessage audit trail
        pass
```

---

## Testing Migration

### Pre-Migration Checks

```cypher
// Count existing tasks (baseline)
MATCH (t:Task)
RETURN count(t) as total_tasks,
       count(t.status = 'pending') as pending_tasks,
       count(t.status = 'completed') as completed_tasks

// Count existing agents
MATCH (a:Agent)
RETURN count(a) as total_agents

// Verify no existing team data (clean state)
MATCH (t:AgentTeam)
RETURN count(t) as existing_teams
```

### Post-Migration Verification

```cypher
// Verify constraints exist
SHOW CONSTRAINTS
YIELD name, type, entityType, labelsOrTypes, properties
WHERE name STARTS WITH 'team_'
RETURN name, type, entityType, labelsOrTypes, properties

// Verify indexes exist
SHOW INDEXES
YIELD name, type, entityType, labelsOrTypes, properties
WHERE name STARTS WITH 'team_'
RETURN name, type, entityType, labelsOrTypes, properties

// Test team creation
CREATE (t:AgentTeam {
    id: randomUUID(),
    name: 'Test Team',
    slug: 'test-team',
    lead_agent_id: 'researcher',
    status: 'active',
    created_at: datetime()
})
RETURN t.id as test_team_id

// Clean up test data
MATCH (t:AgentTeam {slug: 'test-team'})
DETACH DELETE t
```

---

## Rollback Procedure

If issues are detected post-migration:

```bash
# 1. Stop task processing
# 2. Run rollback migration
python -m migrations.migration_manager --rollback 2

# 3. Verify rollback
# - Check that AgentTeam nodes are removed
# - Check that constraints/indexes are dropped
# - Verify existing tasks still work

# 4. Restore from backup if needed
neo4j-admin database restore --from=/path/to/backup

# 5. Resume task processing
```

---

## Deployment Checklist

- [ ] Backup Neo4j database
- [ ] Run pre-migration checks
- [ ] Deploy migration in maintenance window (if downtime required)
- [ ] Verify constraints and indexes created
- [ ] Test team creation
- [ ] Test task assignment to team
- [ ] Test team task claiming
- [ ] Verify existing tasks still process correctly
- [ ] Monitor for errors
- [ ] Document any issues

---

## Summary

This migration adds comprehensive team support to the Kurultai architecture while maintaining full backward compatibility. The additive approach ensures zero downtime and allows gradual adoption of team features.

**Key Files:**
- `/Users/kurultai/molt/cypher/team_schema_extensions.cypher` - Complete schema definitions
- `/Users/kurultai/molt/cypher/team_schema_migration.md` - This migration guide
- `migrations/v3_agent_teams.py` - Migration script (to be created)
