# MIG-001: Database Migration Failure

**Severity**: High
**Affected Component**: Neo4j Schema / Database Migrations
**Recovery Time**: 5-15 minutes

## Symptoms
- Migration script fails to complete
- "Migration failed" error messages
- Schema version mismatch
- Queries failing due to missing nodes/relationships
- Application unable to start after schema change

## Diagnosis
```bash
# 1. Check migration status
cypher-shell -u neo4j -p password "
  MATCH (m:Migration)
  RETURN m.version, m.name, m.success, m.applied_at, m.error_message
  ORDER BY m.version DESC
  LIMIT 5
"

# 2. Check current schema version
cypher-shell -u neo4j -p password "
  MATCH (mc:MigrationControl)
  RETURN mc.version as current_version
"

# 3. Check for partial schema changes
cypher-shell -u neo4j -p password "
  CALL db.schema.visualization()
  YIELD nodes, relationships
  RETURN nodes, relationships
"

# 4. Check migration logs
tail -100 /var/log/openclaw/migrations.log
docker logs moltbot --tail 100 | grep -i migration

# 5. Verify constraint existence
cypher-shell -u neo4j -p password "
  CALL db.constraints()
  YIELD description
  RETURN description
"
```

## Recovery Steps
### Step 1: Identify Failed Migration
```bash
# Get migration details
MIGRATION_VERSION=1  # Replace with actual version

cypher-shell -u neo4j -p password "
  MATCH (m:Migration {version: ${MIGRATION_VERSION}})
  RETURN m.version, m.name, m.success, m.error_message, m.applied_at
"
```

### Step 2: Create Backup Before Rollback
```bash
# Create backup of current state
BACKUP_NAME="pre-rollback-$(date +%Y%m%d-%H%M%S)"

docker exec neo4j neo4j-admin backup \
    --database=neo4j \
    --to-path=/backups/${BACKUP_NAME} \
    --check-consistency=true

echo "Backup created: ${BACKUP_NAME}"
```

### Step 3: Rollback Migration
```python
# Using MigrationManager.rollback()
from migrations.migration_manager import MigrationManager

manager = MigrationManager(
    neo4j_uri="bolt://localhost:7687",
    neo4j_user="neo4j",
    neo4j_password="password"
)

# Rollback specific number of steps
result = manager.rollback(steps=1)

if result:
    print(f"Migration rolled back successfully")
else:
    print(f"Rollback failed")
```

### Step 4: Verify Rollback
```bash
# Check schema version
cypher-shell -u neo4j -p password "
  MATCH (mc:MigrationControl)
  RETURN mc.version as current_version
"

# Verify constraints
cypher-shell -u neo4j -p password "
  CALL db.constraints()
  YIELD description
  RETURN description
"

# Verify indexes
cypher-shell -u neo4j -p password "
  CALL db.indexes()
  YIELD name, state, populationPercent
  RETURN name, state, populationPercent
"
```

### Step 5: Fix and Retry Migration
```python
# After fixing the migration script:

# Review the fix
cat migrations/v${MIGRATION_VERSION}_fixed.py

# Re-register and apply migration
manager.register_migration(
    version=MIGRATION_VERSION,
    name="fixed_migration_name",
    up_cypher=up_cypher_query,
    down_cypher=down_cypher_query
)

result = manager.migrate(target_version=MIGRATION_VERSION)

if result:
    print(f"Migration v{MIGRATION_VERSION} applied successfully")
else:
    print(f"Migration failed")
```

### Alternative: Manual Migration Recovery
```bash
# For manual recovery when automated rollback fails:

# 1. Stop all agents
docker-compose stop agent

# 2. Manually apply Cypher changes
cypher-shell -u neo4j -p password < migrations/fix_manual.cypher

# 3. Update schema version
cypher-shell -u neo4j -p password "
  MATCH (mc:MigrationControl)
  SET mc.version = 1, mc.last_updated = datetime()
"

# 4. Mark migration as complete
cypher-shell -u neo4j -p password "
  MATCH (m:Migration {version: 1})
  SET m.success = true, m.applied_at = datetime()
"

# 5. Restart agents
docker-compose start agent
```

## Rollback Options
1. **Single Rollback**: Rollback only the failed migration
2. **Cascade Rollback**: Rollback migration and all dependent migrations
3. **Full Restore**: Restore database from pre-migration backup

## Prevention Measures

```python
# Migration manager configuration
MIGRATION_CONFIG = {
    'auto_backup': True,
    'verify_before_apply': True,
    'dry_run_first': True,
    'max_retries': 3,
    'rollback_on_error': True,
    'require_approval': True,  # For production
}

# Pre-migration checklist
PRE_MIGRATION_CHECKLIST = [
    'backup_created',
    'schema_validated',
    'dry_run_passed',
    'approval_obtained',
    'maintenance_window_scheduled',
]
```

```yaml
# Migration execution plan
migration_plan:
  preflight:
    - check_database_health
    - create_backup
    - verify_disk_space
    - stop_agents

  execution:
    - apply_schema_changes
    - verify_constraints
    - populate_new_data
    - update_schema_version

  postflight:
    - verify_queries
    - start_agents
    - monitor_errors
    - cleanup_backup: # after 24 hours
```

```bash
# Safe migration script template
#!/bin/bash
set -euo pipefail

MIGRATION_VERSION=$1
BACKUP_NAME="pre-v${MIGRATION_VERSION}-$(date +%Y%m%d-%H%M%S)"

echo "Starting migration: v${MIGRATION_VERSION}"

# Pre-flight checks
echo "Creating backup..."
./scripts/backup_neo4j.sh ${BACKUP_NAME}

echo "Verifying backup..."
./scripts/verify_backup.sh ${BACKUP_NAME}

echo "Stopping agents..."
docker-compose stop agent

# Apply migration
echo "Applying migration..."
python -c "
from migrations.migration_manager import MigrationManager
manager = MigrationManager('bolt://localhost:7687', 'neo4j', 'password')
manager.migrate(target_version=${MIGRATION_VERSION})
"

# Verify
echo "Verifying migration..."
cypher-shell -u neo4j -p ${NEO4J_PASSWORD} < migrations/verify/v${MIGRATION_VERSION}_verify.cypher

# Post-migration
echo "Starting agents..."
docker-compose start agent

echo "Migration complete"
```
