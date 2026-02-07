# Kurultai v0.2 Final Execution - Deployment Guide

> **Status**: 82% Complete - Migration execution pending Railway service configuration
> **Created**: 2026-02-06
> **Plan Version**: 1.0

## Overview

This guide completes the remaining 18% of Kurultai v0.2 deployment. All code is implemented - we need to run Neo4j migrations, generate agent keys, and validate.

## Current Status

### ✅ Completed (82%)
- Phase 0 Task 0.1: Environment variables configured
- Migration infrastructure created and tested
- Agent key generation script created
- Test suite scripts created

### 🔄 In Progress (18%)
- **Railway Neo4j Migrations** - Service configuration needed
- **Agent Key Generation** - Depends on migrations
- **Testing & Validation** - Depends on migrations

---

## Architecture Discovery

The Railway deployment has multiple services:
1. **moltbot-railway-template** - Node.js gateway (current linked service)
2. **neo4j** - Graph database at `bolt://neo4j.railway.internal:7687`
3. **authentik-server** - Identity provider
4. **authentik-worker** - Background tasks
5. **authentik-proxy** - Caddy reverse proxy

---

## Remaining Tasks

### Task 1: Deploy Migration-Enabled Service

**Files Modified:**
- `moltbot-railway-template/Dockerfile` - Added Python dependencies and migration files
- `moltbot-railway-template/entrypoint.sh` - Added migration execution on startup
- `moltbot-railway-template/migrations/` - Copied migration files
- `moltbot-railway-template/scripts/run_migrations.py` - Copied migration runner
- `moltbot-railway-template/openclaw_memory.py` - Copied memory module

**Manual Steps (Railway Dashboard Required):**

1. Go to Railway Dashboard: https://railway.app/project/26201f75-3375-46ce-98c7-9d1dde5f9569
2. Select `moltbot-railway-template` service
3. Trigger a redeploy (or the updated entrypoint will run on next deployment)
4. Watch logs for migration output:
   ```
   === Running Neo4j Migrations ===
   Neo4j is ready!
   Running migration script...
   Connecting to Neo4j at bolt://neo4j:7687...
   Registered migrations: v1, v2, v3
   Current schema version: 0
   Migrating from v0 to v3...
   Applying migration v1: initial_schema
   Applying migration v2: kurultai_dependencies
   Applying migration v3: capability_acquisition
   Migration complete! Now at version: 3
   === Migrations Complete ===
   ```

### Task 2: Generate Agent Keys (After Migrations)

**Option A: Via Railway Service**
1. Copy `scripts/generate_agent_keys.sh` to `moltbot-railway-template/scripts/`
2. Run via Railway console or add to entrypoint

**Option B: Via Direct Neo4j Access**
1. Set up Railway port forwarding or SSH
2. Run locally with Railway Neo4j credentials

**Expected Output:**
```
=== Kurultai v0.2 Agent Key Generation ===
Connecting to Neo4j at bolt://neo4j.railway.internal:7687...

Kublai       (main)
  key_id:  <uuid>
  expires: 2026-05-06T...
  hash:    a1b2c3d4e5f6...

[... all 6 agents ...]

Total active keys: 6/6
```

### Task 3: Run Tests

**Unit Tests:**
```bash
pytest tests/ -v --tb=short --cov=src --cov-report=term-missing --ignore=tests/integration/
```

**Integration Tests:**
```bash
pytest tests/integration/ -v --tb=short
```

**Schema Verification:**
```cypher
// Check all agents have keys
MATCH (a:Agent)-[:HAS_KEY]->(k:AgentKey)
WHERE k.is_active = true
RETURN a.name as agent, a.id as agent_id,
       k.id as key_id, k.expires_at as expires
ORDER BY a.name;
// Expected: 6 rows
```

---

## File Changes Summary

### Modified Files
| File | Change |
|------|--------|
| `railway.yml` | Added migrations service definition |
| `start_server.py` | Created migration-aware startup script |
| `Dockerfile` | Updated to use start_server.py |
| `moltbot-railway-template/Dockerfile` | Added Python + migration dependencies |
| `moltbot-railway-template/entrypoint.sh` | Added migration execution |
| `moltbot-railway-template/migrations/` | Copied from root |
| `moltbot-railway-template/scripts/run_migrations.py` | Copied from root |
| `moltbot-railway-template/openclaw_memory.py` | Copied from root |

### Created Files
| File | Purpose |
|------|---------|
| `railway-migrations/Dockerfile` | Standalone migration runner (alternative approach) |
| `railway-migrations/.dockerignore` | Exclude unnecessary files |

---

## Environment Variables

Ensure these are set in Railway dashboard (never commit passwords):
```
NEO4J_URI=bolt://neo4j.railway.internal:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=<set via Railway dashboard — rotate immediately if previously exposed>
```

---

## Exit Criteria Checklist

### Phase 0: Environment Setup & Migrations
- [ ] `.env` file exists with Neo4j credentials set
- [ ] `NEO4J_PASSWORD` is non-empty
- [ ] Migration exits with code 0
- [ ] Neo4j shows version 3 in MigrationControl node
- [ ] Agent nodes exist (6 agents: main, researcher, writer, developer, analyst, ops)

### Phase 1: Agent Key Generation
- [ ] Script exits with code 0
- [ ] Exactly 6 AgentKey nodes created in Neo4j
- [ ] All keys have `is_active: true`
- [ ] All keys expire 90 days from creation

### Phase 2: Testing & Validation
- [ ] pytest exits with code 0
- [ ] No test failures or errors
- [ ] Coverage report generated
- [ ] All integration tests pass
- [ ] At least 3 constraints exist in Neo4j
- [ ] At least 5 indexes exist in Neo4j
- [ ] `MATCH (a:Agent)-[:HAS_KEY]->(k:AgentKey) RETURN count(*)` returns 6
- [ ] Railway services show healthy status
- [ ] Health endpoint returns 200
- [ ] Web UI loads and redirects to Authentik login
- [ ] WebAuthn authentication works (Face ID / Touch ID / hardware key)
- [ ] Signal link generates QR code or pairing instructions
- [ ] Signal app successfully links to the service
- [ ] Agent responds to test message via Signal (2-way communication confirmed)

---

## Troubleshooting

### Migration Not Running
- Check `entrypoint.sh` has migration code
- Verify `NEO4J_PASSWORD` is set in Railway variables
- Check Dockerfile has `COPY` directives for migration files

### Neo4j Connection Failed
- Verify `NEO4J_URI` is correct for Railway's private network
- Check neo4j service is running: `railway logs --service neo4j`
- Ensure password variable matches

### Agent Keys Not Generated
- Verify migrations completed first (Agent nodes must exist)
- Check `openclaw_memory.py` is accessible to the script
- Verify Python Neo4j driver is installed

---

## Next Steps After Deployment

1. **Monitor Railway Logs**: `railway logs --service moltbot-railway-template --follow`
2. **Verify Schema**: Run Cypher queries in Railway's Neo4j console
3. **Test Agent Communication**: Send test messages via Signal
4. **Generate Keys**: Run `generate_agent_keys.sh` after migrations complete
5. **Run Test Suite**: Execute local tests against deployed services

---

## Approval Status

- [x] Plan Output Contract validated
- [x] Requirements understood (complete remaining 18% of deployment)
- [x] Task breakdown documented
- [x] Dependencies identified
- [ ] **Railway service redeploy pending manual trigger**
- [ ] **Awaiting migration completion to proceed with key generation**

---

## Appendix A: Quick Reference

### Railway CLI Commands
```bash
railway status                    # Check deployment status
railway logs                      # View service logs
railway logs --service neo4j     # View Neo4j logs
railway up                        # Deploy from current directory
railway variables                 # List environment variables
```

### Migration Script
```bash
python scripts/run_migrations.py --target-version 3
python scripts/run_migrations.py --status
python scripts/run_migrations.py --rollback 1
```

### Neo4j Verification
```cypher
SHOW CONSTRAINTS;
SHOW INDEXES;
MATCH (a:Agent) RETURN a.name, a.id;
MATCH (a:Agent)-[:HAS_KEY]->(k:AgentKey) RETURN count(*);
```
