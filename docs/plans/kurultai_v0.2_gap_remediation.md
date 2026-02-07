# Kurultai v0.2 Gap Analysis Report

## Context

A golden-horde Consensus Deliberation with 3 parallel expert agents (documentation consistency, codebase implementation verification, Neo4j schema analysis) was performed against 5 specification documents and the live codebase. The root cause of most gaps is the **Feb 6, 2026 Express-to-OpenClaw migration** that replaced the moltbot gateway but did not update any specification documents.

**Claimed completion: 82% | Realistic deployment-ready: 35-40%**

---

## Consolidated Findings: 80+ Gaps

### CRITICAL (14 items) — Deployment Blockers

| ID | Category | Issue | Files Affected |
|----|----------|-------|----------------|
| C-01 | Infrastructure | Neo4j health check uses deprecated 3.x JMX endpoint — will always fail on Neo4j 5 | `railway.yml` |
| C-02 | Infrastructure | GDS plugin configured but incompatible with Community Edition — may prevent Neo4j startup | `railway.yml` |
| C-03 | Security | `forward_auth` COMMENTED OUT on catch-all route — all routes publicly accessible | `authentik-proxy/Caddyfile` |
| C-04 | Configuration | `agentToAgent` section missing from OpenClaw config — core agent communication broken | `moltbot-railway-template/openclaw.json5` |
| C-05 | Infrastructure | Service name mismatch: `railway.yml` says `moltbot`, Caddyfile DNS uses `moltbot-railway-template.railway.internal` | `railway.yml`, `authentik-proxy/Caddyfile` |
| C-06 | Security | Plaintext Neo4j password committed in documentation | `docs/plans/KURULTAI_V0.2_EXECUTION_GUIDE.md` |
| C-07 | Security | HMAC-SHA256 agent authentication claimed in architecture but not implemented — delegation.py sends plain Bearer tokens | `src/protocols/delegation.py`, `docs/plans/architecture.md` |
| C-08 | Infrastructure | Moltbot Dockerfile missing `ENTRYPOINT []` — Railway strips Docker CMD | `moltbot-railway-template/Dockerfile` |
| C-09 | Documentation | Architecture doc describes Express.js on port 8080 — codebase is OpenClaw on 18789 | `docs/plans/architecture.md` |
| C-10 | Documentation | Completion doc claims "No Known Blockers" and "deployment-ready" — at least 10 blockers exist | `docs/plans/kurultai_0.2-completion.md` |
| C-11 | Documentation | Architecture doc claims Neo4j AuraDB (managed) with TLS — actual is self-hosted Community with unencrypted bolt:// | `docs/plans/architecture.md` |
| C-12 | Security | Shell injection in entrypoint.sh line 25: `python -c "...auth=('$NEO4J_USER', '$NEO4J_PASSWORD')..."` | `moltbot-railway-template/entrypoint.sh` |
| C-13 | Infrastructure | Migration NEO4J_URI mismatch: moltbot uses `bolt://neo4j.railway.internal:7687`, migrations use `bolt://neo4j:7687` | `railway.yml` |
| C-14 | Documentation | `src/index.js` referenced in completion doc no longer exists (replaced by OpenClaw) | `docs/plans/kurultai_0.2-completion.md` |

### HIGH (17 items) — Functional/Security Issues

| ID | Category | Issue | Files Affected |
|----|----------|-------|----------------|
| H-01 | Schema | Vector indexes specified in neo4j.md but NOT created in any migration (v2 has them in unused `upgrade()` function, v3 has none) | `migrations/v2_kurultai_dependencies.py`, `migrations/v3_capability_acquisition.py` |
| H-02 | Schema | Fulltext index `knowledge_content` specified in neo4j.md but not in any migration | All migration files |
| H-03 | Schema | Node label mismatch: `notion_sync.py` uses `:TaskNode`, `delegation.py` uses `:Task` | `tools/notion_sync.py`, `src/protocols/delegation.py` |
| H-04 | Schema | 12+ node labels in `openclaw_memory.py` (HealthCheck, Improvement, Learning, MetaRule, Notification, PriorityAudit, etc.) have NO migration constraints or indexes | `openclaw_memory.py`, all migrations |
| H-05 | Configuration | Connection pool: neo4j.md specifies 400, `openclaw_memory.py` defaults to 50 | `openclaw_memory.py` |
| H-06 | Configuration | Agent models: neo4j.md specifies kimi-k2.5/glm-4.5/glm-4.7, openclaw.json5 has claude-sonnet-4-5 for all | `moltbot-railway-template/openclaw.json5` |
| H-07 | Code Quality | Duplicate `OperationalMemory` stub class in delegation.py (lines 48-77) shadows real class from openclaw_memory.py | `src/protocols/delegation.py` |
| H-08 | Code Quality | Duplicate `investigate` routing key in delegation.py (lines 98 and 122) — silently routes to wrong agent | `src/protocols/delegation.py` |
| H-09 | Security | PII stored in Neo4j: `original_description` (unsanitized) saved to Task node despite sanitization step | `src/protocols/delegation.py` |
| H-10 | Security | Rate limiter fails open on Neo4j errors — all rate limiting disabled during outages | `openclaw_memory.py` |
| H-11 | Security | `allowInsecureAuth: true` in gateway config — undocumented security-relevant setting | `moltbot-railway-template/openclaw.json5` |
| H-12 | Infrastructure | Docker base image: docs say `node:20-alpine`, actual is `node:22-bookworm-slim` | `moltbot-railway-template/Dockerfile` |
| H-13 | Schema | v2 migration has 0 UNIQUE constraints (v1 has 4, v3 has 9) — no data integrity for Phase 1.5 entities | `migrations/v2_kurultai_dependencies.py` |
| H-14 | Schema | Async/sync driver mismatch: `openclaw_memory.py` uses sync driver, `notion_sync.py` and `topological_executor.py` use async | Multiple files |
| H-15 | Code Quality | Migration rollback mixes DDL+DML in single transaction — will fail on Neo4j 5 | `migrations/migration_manager.py` |
| H-16 | Integration | Phase 1.5/2/6.5 modules exist but NOT wired into main orchestrator | `tools/kurultai/*.py` |
| H-17 | Integration | No Node-Python bridge or OpenClaw proxy bridge — Python tools can't be called from OpenClaw agents | No bridge code exists |

### MEDIUM (6 items)

| ID | Issue |
|----|-------|
| M-01 | Authentik described as "Go" in architecture doc — it's Python/Django |
| M-02 | `horde_learn_adapter.py` phases 2 & 3 are placeholder templates |
| M-03 | Missing constraints for Analysis, SecurityAudit, Reflection, Research, Content, Concept nodes |
| M-04 | `shellEnv.enabled: false` in OpenClaw config may block agent Neo4j connectivity |
| M-05 | Typo "Kurlati Engine" in architecture doc line 482 |
| M-06 | Phase count inconsistency: GUIDE says 3 remaining tasks, COMP says "9 of 11 phases" |

### Documentation Gaps (22 items)

12 items exist in codebase but are undocumented in all 5 specs:
- `openclaw.json5` (the actual gateway config defining all agent behavior)
- `entrypoint.sh` (handles migrations, signal data, gateway startup)
- Railway service name mismatch between `railway.yml` and Caddyfile
- `allowInsecureAuth: true`, `shellEnv.enabled: false` settings
- Non-root user setup (moltbot user UID 1001)
- Signal `dmPolicy`/`groupPolicy` access controls
- `authentik-db` as self-hosted PostgreSQL (not managed)
- Lazy Neo4j import pattern, custom exception hierarchy, retry decorator

10 items are stale (described pre-OpenClaw Express.js architecture that no longer exists).

---

## Revised Completion Assessment

| Phase | Claimed | Actual | Issue |
|-------|---------|--------|-------|
| Phase 0 (Environment) | Complete | **Broken** | Wrong NEO4J_URI protocol in docs |
| Phase 1 (Neo4j) | Complete | **Partially broken** | Health check, GDS, vector indexes all broken |
| Phase 1.5 (Task Deps) | Complete | Exists, not wired | Modules not integrated into orchestrator |
| Phase 2 (Capability) | Complete | Exists, templates | horde_learn phases 2&3 are stubs |
| Phase 3 (Railway) | Complete | **Broken** | Wrong base image, no ENTRYPOINT, name mismatch |
| Phase 4 (Signal) | Complete | **Stale** | Describes Express.js that no longer exists |
| Phase 4.5 (Notion) | Complete | Has issues | Async/sync driver mismatch, wrong node labels |
| Phase 5 (Authentik) | Complete | **Broken** | forward_auth disabled |
| Phase 6 (Monitoring) | Complete | **Stale** | References Pino in nonexistent file |
| Phase 6.5 (File Consistency) | Complete | Exists, not wired | Not integrated into orchestrator |
| Phase 7 (Testing) | Partial | Partial | Not verified |

**Actually working: 4 phases (1.5, 2, 4.5, 6.5) = ~35%**
**Code exists but broken: 6 phases = additional ~20%**
**Not started/verified: 2 phases**

---

## Remediation Plan (Prioritized)

### Tier 1: Immediate Security & Deployment Blockers (C-01 through C-14)

**1. Rotate compromised Neo4j password** (C-06)
- File: `docs/plans/KURULTAI_V0.2_EXECUTION_GUIDE.md`
- Action: Remove plaintext password, reference Railway env var instead

**2. Fix Neo4j health check** (C-01)
- File: `railway.yml`
- Action: Replace JMX endpoint with Neo4j 5 compatible check: `curl -f http://localhost:7474/`

**3. Remove GDS plugin** (C-02)
- File: `railway.yml`
- Action: Change `NEO4J_PLUGINS='["apoc", "gds"]'` to `NEO4J_PLUGINS='["apoc"]'`

**4. Re-enable forward_auth** (C-03)
- File: `authentik-proxy/Caddyfile`
- Action: Uncomment forward_auth on catch-all route

**5. Fix service name mismatch** (C-05, C-13)
- Files: `railway.yml`, `authentik-proxy/Caddyfile`
- Action: Align service name to `moltbot` everywhere, update Caddyfile DNS

**6. Add ENTRYPOINT [] to moltbot Dockerfile** (C-08)
- File: `moltbot-railway-template/Dockerfile`
- Action: Add `ENTRYPOINT []` before CMD line

**7. Fix shell injection in entrypoint.sh** (C-12)
- File: `moltbot-railway-template/entrypoint.sh`
- Action: Use environment variables safely, not string interpolation in python -c

**8. Add agentToAgent configuration** (C-04)
- File: `moltbot-railway-template/openclaw.json5`
- Action: Add agentToAgent section per neo4j.md spec

### Tier 2: Schema & Integration Fixes (H-01 through H-17)

**9. Create vector indexes in migrations** (H-01, H-02)
- Files: `migrations/v2_kurultai_dependencies.py`, `migrations/v3_capability_acquisition.py`
- Action: Move vector index creation into UP_CYPHER strings that MigrationManager executes

**10. Fix node label consistency** (H-03, H-04)
- Files: `tools/notion_sync.py` (TaskNode→Task), add constraints for uncovered labels

**11. Fix delegation.py code quality** (H-07, H-08, H-09)
- File: `src/protocols/delegation.py`
- Action: Remove duplicate OperationalMemory stub, fix duplicate investigate key, stop storing unsanitized original_description

**12. Fix rate limiter fail-open** (H-10)
- File: `openclaw_memory.py`
- Action: Return `(False, ...)` on Neo4j errors, not `(True, ...)`

**13. Fix migration rollback** (H-15)
- File: `migrations/migration_manager.py`
- Action: Split DDL and DML in rollback like `_apply_migration_split` does

### Tier 3: Documentation Rewrite

**14. Rewrite architecture.md** — Replace Express.js with OpenClaw, port 8080→18789, AuraDB→Community, node:20→22, Go→Python/Django

**15. Update completion doc** — Remove "No Known Blockers", update true completion %, reference openclaw.json5

**16. Update all 5 docs** — Reflect post-OpenClaw state consistently

### Tier 4: Integration Wiring

**17. Wire Phase 1.5/2/6.5 into orchestrator** (H-16)
**18. Build Node-Python bridge** (H-17)
**19. Complete horde_learn phases 2&3** (M-02)

---

## Kimi API Configuration

Apply to `openclaw.json5`:
```json5
"env": {
  "ANTHROPIC_AUTH_TOKEN": "${KIMI_API_KEY}",
  "ANTHROPIC_BASE_URL": "https://api.kimi.com/coding/",
  "API_TIMEOUT_MS": "3000000"
}
```
This should replace the current `claude-sonnet-4-5-20250929` model references and align with neo4j.md's agent model specifications.

---

## Verification

After implementing Tier 1+2 fixes:
1. `railway up` deploys without Neo4j health check failures
2. Neo4j starts without GDS errors
3. forward_auth blocks unauthenticated requests on all routes
4. OpenClaw agents can communicate via agentToAgent
5. Vector indexes exist: `SHOW INDEXES` in Neo4j
6. No shell injection in entrypoint.sh
7. Service name resolves correctly from Caddyfile to moltbot container
