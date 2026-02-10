# Kurultai v0.2 Execution Plan

## Status: Deployment-Ready (82% Complete)

**Date**: 2026-02-06
**Source**: kurultai_0.2-completion.md audit

---

## Executive Summary

All code is implemented and ready for deployment. The remaining tasks are:

1. **Phase 1 Task 1.4**: Generate Agent Keys (requires Neo4j connectivity)
2. **Phase 7**: Run test suite validation
3. **Phase -1**: Optional wipe-and-rebuild (only for fresh deployments)

---

## Task 1: Agent Key Generation (Phase 1 Task 1.4)

### Prerequisites
- Neo4j database running and accessible
- Environment variables configured: `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`
- Agent nodes exist in Neo4j (created by migration v3)

### Execution Script

```bash
#!/bin/bash
# scripts/generate_agent_keys.sh

set -e

echo "=== Kurultai v0.2 Agent Key Generation ==="
echo "This will generate HMAC-SHA256 keys for all 6 agents"
echo ""

# Check prerequisites
if [[ -z "$NEO4J_URI" ]]; then
    echo "Error: NEO4J_URI environment variable not set"
    echo "Export it or add to .env file"
    exit 1
fi

if [[ -z "$NEO4J_PASSWORD" ]]; then
    echo "Error: NEO4J_PASSWORD environment variable not set"
    echo "Export it or add to .env file"
    exit 1
fi

# Run key generation
python3 << 'EOF'
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from openclaw_memory import OperationalMemory
import secrets
from datetime import datetime, timedelta

memory = OperationalMemory()

agents = [
    ('main', 'Kublai'),
    ('researcher', 'Möngke'),
    ('writer', 'Chagatai'),
    ('developer', 'Temüjin'),
    ('analyst', 'Jochi'),
    ('ops', 'Ögedei')
]

print(f"Connecting to Neo4j at {os.getenv('NEO4J_URI')}...")
print("")

for agent_id, agent_name in agents:
    key_hash = secrets.token_hex(32)

    cypher = '''
        MATCH (a:Agent {id: $agent_id})
        CREATE (k:AgentKey {
            id: randomUUID(),
            key_hash: $key_hash,
            created_at: datetime(),
            expires_at: datetime() + duration('P90D'),
            is_active: true
        })
        CREATE (a)-[:HAS_KEY]->(k)
        RETURN k.id as key_id, k.expires_at as expires
    '''

    try:
        with memory._session() as session:
            result = session.run(cypher, agent_id=agent_id, key_hash=key_hash)
            record = result.single()
            if record:
                expires_str = record['expires'].isoformat()
                print(f"✓ {agent_name:12} ({agent_id}): key_id={record['key_id']}")
                print(f"  Expires: {expires_str}")
            else:
                print(f"✗ {agent_name}: Agent node not found in Neo4j")
                print(f"  Run migration first: python scripts/run_migrations.py --target-version 3")
    except Exception as e:
        print(f"✗ {agent_name}: {e}")

print("")
print("=== Verifying keys ===")

verify_cypher = '''
    MATCH (a:Agent)-[:HAS_KEY]->(k:AgentKey)
    WHERE k.is_active = true
    RETURN a.id as agent_id, a.name as agent_name, k.id as key_id, k.expires_at as expires
    ORDER BY a.id
'''

with memory._session() as session:
    results = session.run(verify_cypher)
    count = 0
    for record in results:
        count += 1
        print(f"{record['agent_name']:12} ({record['agent_id']}): key active until {record['expires'].isoformat()}")

    print("")
    print(f"Total active keys: {count}/6")

    if count == 6:
        print("✓ All agent keys generated successfully!")
        sys.exit(0)
    else:
        print("✗ Missing keys! Run migrations first or check Agent nodes exist.")
        sys.exit(1)

EOF

echo ""
echo "Agent key generation complete!"
```

### Verification

After running the script, verify keys exist:

```bash
# Via Neo4j Browser or Cypher shell
MATCH (a:Agent)-[:HAS_KEY]->(k:AgentKey)
WHERE k.is_active = true
RETURN a.name, k.expires_at
ORDER BY a.name
```

**Expected Output**:
| a.name | k.expires_at |
|--------|--------------|
| Kublai | 90 days from now |
| Möngke | 90 days from now |
| Chagatai | 90 days from now |
| Temüjin | 90 days from now |
| Jochi | 90 days from now |
| Ögedei | 90 days from now |

---

## Task 2: Test Suite Validation (Phase 7)

### Unit Tests

```bash
# Install test dependencies
pip install -r test-requirements.txt

# Run all tests with coverage
pytest tests/ -v --tb=short --cov=src --cov-report=html

# Expected: All tests pass, >80% coverage
```

### Integration Tests

```bash
# Test Notion sync
pytest tests/integration/test_notion_sync.py -v

# Test delegation workflow
pytest tests/integration/test_delegation_workflow.py -v
```

### End-to-End Tests

These tests require the deployed Railway services:

```bash
# Test 1: Unauthenticated redirect to Authentik
curl -I https://kublai.kurult.ai/dashboard
# Expected: 302 redirect to /if/flow/authentication/

# Test 2: Health check (no auth required)
curl https://kublai.kurult.ai/health
# Expected: 200 with {"status":"healthy"}

# Test 3: Signal link requires token
curl -X POST https://kublai.kurult.ai/setup/api/signal-link \
  -H "Content-Type: application/json" \
  -d '{"phoneNumber": "+1234567890"}'
# Expected: 401 Unauthorized

# Test 4: File consistency monitor health
curl https://kublai.kurult.ai/health/file-consistency
# Expected: 200 with {"monitor_running":true}
```

### Exit Criteria Checklist

- [ ] Unit tests pass with >80% coverage
- [ ] Integration tests pass (notion_sync, delegation)
- [ ] End-to-end tests pass (authentication, health checks, Signal link)
- [ ] Neo4j schema validated (constraints, indexes present)
- [ ] All 6 AgentKey nodes exist with 90-day expiration

---

## Task 3: Optional Wipe and Rebuild (Phase -1)

**ONLY execute this for a fresh deployment.**

```bash
#!/bin/bash
# scripts/wipe_and_rebuild.sh

set -e

BACKUP_DIR="$HOME/kurultai-backup-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"

echo "=== Creating backup ==="
railway variables --json > "$BACKUP_DIR/railway-vars.json"
cp .env "$BACKUP_DIR/.env.backup"
echo "Backup saved to: $BACKUP_DIR"

echo ""
echo "=== Deleting Railway services ==="
railway services

read -p "Type 'DELETE' to confirm deletion of all services: " confirm
if [[ "$confirm" != "DELETE" ]]; then
    echo "Aborted."
    exit 1
fi

railway remove authentik-db
railway remove authentik-worker
railway remove authentik-server
railway remove authentik-proxy
railway remove moltbot-railway-template

echo ""
echo "Services deleted. Redeploy with: railway up"
```

---

## Deployment Sequence

### For Fresh Deployment

1. Set environment variables in `.env`
2. Run `scripts/generate_agent_keys.sh` (after Neo4j is available)
3. Deploy to Railway: `railway up`
4. Run test suite: `pytest tests/ -v`
5. Run e2e tests against deployed services

### For Existing Deployment (Update)

1. Run migrations: `python scripts/run_migrations.py --target-version 3`
2. Run `scripts/generate_agent_keys.sh`
3. Deploy to Railway: `railway up`
4. Run e2e tests

---

## File Locations Reference

| Component | File Path |
|-----------|-----------|
| Agent Key Script | `scripts/generate_agent_keys.sh` |
| Migrations | `scripts/run_migrations.py`, `migrations/` |
| Neo4j Memory | `openclaw_memory.py` |
| Unit Tests | `tests/` |
| Integration Tests | `tests/integration/` |
| Environment Template | `.env.example` |
| Dockerfiles | `authentik-server/Dockerfile`, `authentik-worker/Dockerfile`, `authentik-proxy/Dockerfile`, `moltbot-railway-template/Dockerfile` |

---

## Known Issues & Workarounds

1. **Neo4j Password Required**
   - Issue: `openclaw_memory.py` requires `NEO4J_PASSWORD` env var
   - Fix: Add to `.env`: `NEO4J_PASSWORD=your_password`

2. **Railway Docker CMD Stripping**
   - Issue: Railway ignores `CMD` in Dockerfile
   - Fix: Use `ENTRYPOINT []` + `CMD ["dumb-init","--","ak","server"]` pattern

3. **Authentik Multi-Tenancy (v2025.10)**
   - Issue: Empty `authentik_tenants_domain` table causes API to return 0
   - Fix: INSERT domain matching proxy Host header

4. **Authentik Brand Domain**
   - Issue: Outpost generates `http://0.0.0.0:9000` redirects
   - Fix: Update `authentik_brands_brand.domain` to match proxy URL

---

## Next Actions

1. **Immediate**: Run `scripts/generate_agent_keys.sh` after Neo4j is available
2. **After deployment**: Run Phase 7 test suite
3. **Monitor**: Check health endpoints post-deployment

---

**Last Updated**: 2026-02-06
**Completion Status**: 82% → 100% after executing Tasks 1 and 2
