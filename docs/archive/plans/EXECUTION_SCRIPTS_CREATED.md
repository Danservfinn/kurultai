# Kurultai v0.2 Execution Scripts - Created

## Summary

Created three executable scripts to complete the remaining Kurultai v0.2 deployment tasks. All code is implemented (82% complete) — these scripts finish the remaining 18%.

---

## Created Files

### 1. `scripts/generate_agent_keys.sh`
**Purpose**: Generate HMAC-SHA256 keys for all 6 agents (Phase 1 Task 1.4)

**Features**:
- Validates environment variables (NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
- Loads .env file if present
- Generates 6 agent keys with 90-day expiration
- Verifies all keys were created successfully
- Outputs key IDs and expiration dates

**Usage**:
```bash
./scripts/generate_agent_keys.sh
```

**Prerequisites**:
- Neo4j database running and accessible
- Agent nodes exist (run `python scripts/run_migrations.py --target-version 3` first)

---

### 2. `scripts/run_phase7_tests.sh`
**Purpose**: Run unit, integration, and end-to-end tests (Phase 7)

**Features**:
- Unit tests with coverage report
- Integration tests (notion sync, delegation)
- End-to-end tests against deployed URL
- Configurable test selection

**Usage**:
```bash
# Run all tests (unit + integration)
./scripts/run_phase7_tests.sh

# Run with e2e tests
./scripts/run_phase7_tests.sh --e2e

# Run against local deployment
./scripts/run_phase7_tests.sh --e2e --url http://localhost:3000

# Skip unit tests
./scripts/run_phase7_tests.sh --no-unit
```

---

### 3. `scripts/wipe_and_rebuild.sh`
**Purpose**: Delete all Railway services for fresh deployment (Phase -1)

**Features**:
- Creates backup of Railway variables and .env
- Lists current services before deletion
- Requires "DELETE" confirmation to prevent accidents
- Safe default (aborts if confirmation mistyped)

**Usage**:
```bash
./scripts/wipe_and_rebuild.sh
```

**Warning**: Only use for fresh deployments!

---

## Execution Plan

### For Fresh Deployment
```bash
# 1. Set environment variables in .env
cp .env.example .env
# Edit .env with your values

# 2. Run migrations
python scripts/run_migrations.py --target-version 3

# 3. Generate agent keys
./scripts/generate_agent_keys.sh

# 4. Deploy to Railway
railway up

# 5. Run tests
./scripts/run_phase7_tests.sh --e2e
```

### For Existing Deployment (Update)
```bash
# 1. Generate agent keys (if not done)
./scripts/generate_agent_keys.sh

# 2. Deploy updates
railway up

# 3. Run e2e tests
./scripts/run_phase7_tests.sh --e2e
```

---

## Documentation

- **Execution Plan**: `docs/plans/kurultai_v0.2_execution_plan.md`
- **Completion Prompt**: `docs/plans/kurultai_0.2-completion.md`
- **Original Plan**: `docs/plans/kurultai_0.2.md`

---

## Exit Criteria Checklist

- [x] Execution scripts created and made executable
- [ ] Agent keys generated (requires Neo4j connectivity)
- [ ] Unit tests pass with >80% coverage
- [ ] Integration tests pass
- [ ] End-to-end tests pass
- [ ] Neo4j schema validated
- [ ] Health endpoints verified

---

## Next Steps

1. **With Neo4j access**: Run `./scripts/generate_agent_keys.sh`
2. **After deployment**: Run `./scripts/run_phase7_tests.sh --e2e`
3. **Monitor**: Check health endpoints post-deployment

---

**Created**: 2026-02-06
**Scripts**: 3 executable bash scripts
**Documentation**: 2 markdown files
