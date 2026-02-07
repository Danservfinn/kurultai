# Kublai Self-Awareness Operations Guide

## Overview

Kublai maintains self-awareness by querying `ARCHITECTURE.md` from Neo4j and proposing improvements via a collaborative workflow with Ögedei (Operations) and Temüjin (Development).

## Architecture

```
ARCHITECTURE.md → Neo4j (via git hook) → Kublai queries → proposes improvement
                                                              ↓
                                                         Ögedei vets
                                                              ↓
                                                         Temüjin implements
                                                              ↓
                                                         Validation
                                                              ↓
                                                         Only THEN syncs back to ARCHITECTURE.md
```

## Proposal States

| State | Description | Next State |
|-------|-------------|------------|
| `proposed` | Kublai creates proposal | `under_review` |
| `under_review` | Ögedei reviewing | `approved` / `rejected` |
| `approved` | Ready for implementation | `implemented` |
| `rejected` | Not proceeding | — |
| `implemented` | Temüjin completed work | `validated` |
| `validated` | Validation checks passed | `synced` |
| `synced` | Changes written to ARCHITECTURE.md | — |

## Agent Roles

### Kublai (Main/Orchestrator)

- Queries architecture from Neo4j
- Identifies improvement opportunities
- Creates proposals
- Coordinates workflow

**Architecture Queries:**

```cypher
// Get architecture overview
MATCH (s:ArchitectureSection)
RETURN s.title, s.order, s.git_commit
ORDER BY s.order

// Search architecture content
CALL db.index.fulltext.queryNodes('architecture_search_index', $term)
YIELD node, score
RETURN node.title, node.content, score
```

### Ögedei (Operations)

- Reviews proposals for operational impact
- Assesses deployment risk
- Provides recommendations

**Vetting Process:**
1. Assess operational impact (none/low/medium/high)
2. Assess deployment risk (low/medium/high/critical)
3. Suggest rollout strategy (blue_green/canary/rolling)
4. Suggest monitoring (error_rate, latency_p95, memory_usage)
5. Make recommendation (approve/reject/approve_with_conditions)

### Temüjin (Developer)

- Implements approved proposals
- Tracks progress
- Completes implementation

**Implementation Workflow:**
1. Verify proposal status is `approved`
2. Create Implementation record
3. Execute implementation
4. Update progress
5. Mark implementation complete

### Validation Handler

- Runs validation checks on completed implementations
- Creates Validation record
- Updates proposal status to `validated`

**Validation Checks:**
1. Implementation complete (all tasks done)
2. Tests passing (unit + integration)
3. No regressions detected
4. Performance within acceptable bounds

## Key Guardrail

> **ARCHITECTURE.md only updates for validated implementations.**

Proposals must pass through the complete workflow before being documented:

```
Creation → Ögedei Review → Approval → Implementation → Validation → Sync
```

**Application-Layer Enforcement:**

The guardrail is enforced in `src/workflow/guardrail-enforcer.js`:

```javascript
async function canSyncToArchitecture(proposalId, driver) {
  // Step 1: Verify proposal exists
  // Step 2: Verify implementation_status = 'completed'
  // Step 3: Verify status = 'validated'
  // Step 4: Verify Validation.passed = true
  return { allowed: boolean, reason?: string };
}
```

Neo4j lacks conditional relationship constraints, so this check MUST happen at the application layer before creating `SYNCED_TO` relationships.

## Usage

### Trigger Manual Reflection

```bash
node src/kublai/proactive-reflection.js
```

### Check Pending Proposals

```bash
# Via Neo4j cypher
cypher-shell -a neo4j+s://user:pass@host
MATCH (p:ArchitectureProposal {status: 'proposed'})
RETURN p.id, p.title, p.description
```

### Ögedei Vet a Proposal

```bash
# Via API (when endpoints are implemented)
curl -X POST http://localhost:18789/api/vet \
  -H "Content-Type: application/json" \
  -d '{"proposalId": "<uuid>"}'
```

### Temüjin Implement

```bash
# Via API
curl -X POST http://localhost:18789/api/implement \
  -H "Content-Type: application/json" \
  -d '{"proposalId": "<uuid>"}'
```

### Sync Validated Proposals to ARCHITECTURE.md

```bash
# Find proposals ready for sync
node scripts/sync-architecture-to-neo4j.js sync-proposals

# After manual review and addition to ARCHITECTURE.md, mark as synced
node scripts/sync-architecture-to-neo4j.js mark-synced <proposalId> "<section-title>"
```

## Troubleshooting

### Proposal Not Syncing to ARCHITECTURE.md

**Symptom:** Proposal with `status: 'validated'` not appearing in documentation.

**Check:**
1. Verify `implementation_status = 'completed'`
2. Verify `status = 'validated'`
3. Verify Validation node exists with `passed = true`
4. Check for `SYNCED_TO` relationship already exists

**Query:**
```cypher
MATCH (p:ArchitectureProposal {id: $proposalId})
RETURN p.status, p.implementation_status,
       EXISTS((p)-[:SYNCED_TO]->(:ArchitectureSection)) as synced
```

### Reflection Not Finding Opportunities

**Symptom:** Proactive reflection returns 0 opportunities.

**Check:**
1. Verify ARCHITECTURE.md is synced to Neo4j
2. Check full-text search index exists: `SHOW INDEXES`
3. Review section titles in ArchitectureSection nodes

**Fix:**
```bash
# Re-sync architecture sections
node scripts/sync-architecture-to-neo4j.js
```

### Guardrail Violation Detected

**Symptom:** Error "GUARDRAIL: Proposal not validated" when attempting sync.

**Cause:** Proposal status or implementation_status does not meet requirements.

**Resolution:**
1. Complete implementation if needed
2. Run validation checks
3. Fix any failing validation items
4. Re-attempt sync

### Ögedei Vetting Timeout

**Symptom:** Proposal stuck in `under_review` state.

**Check:**
1. Verify Ögedei agent is running
2. Check agent heartbeat in Neo4j
3. Review agent logs for errors

**Workaround:** Kublai can override vetting after timeout period (emergency only).

## Database Schema

### Node Types

| Node Type | Purpose | Key Properties |
|-----------|---------|---------------|
| `ArchitectureProposal` | Proposals for changes | id, title, description, status, implementation_status |
| `ImprovementOpportunity` | Gaps identified by Kublai | id, type, description, priority |
| `Vetting` | Ögedei's assessment | id, proposal_id, operational_impact, deployment_risk, recommendation |
| `Implementation` | Temüjin's tracking | id, proposal_id, started_at, status, progress |
| `Validation` | Validation results | id, implementation_id, passed, checks |

### Relationship Types

| Relationship | From | To | Purpose |
|-------------|------|-----|---------|
| `EVOLVES_INTO` | ImprovementOpportunity | ArchitectureProposal | Opportunity becomes proposal |
| `ASSESSES` | Vetting | ArchitectureProposal | Ögedei's review |
| `TRACKS` | Implementation | ArchitectureProposal | Implementation tracking |
| `VALIDATES` | Validation | Implementation | Validation results |
| `SYNCED_TO` | ArchitectureProposal | ArchitectureSection | Proposal synced to docs |

## Monitoring

### Health Checks

```bash
# Check proposal workflow status
curl http://localhost:18789/health
```

### Metrics to Track

- Proposal creation rate (proposals/day)
- Average time from proposal to sync (days)
- Validation pass rate (%)
- Ögedei vetting completion rate (%)
- Temüjin implementation completion rate (%)

## Security Considerations

### OWASP A01:2021 - Broken Access Control

The guardrail enforcement prevents unauthorized architecture changes. Only proposals that pass validation can modify ARCHITECTURE.md.

### Audit Trail

All state transitions are logged in Neo4j with timestamps:

```cypher
MATCH (p:ArchitectureProposal {id: $id})
RETURN p.status, p.state_changed_at, p.state_change_reason
```

### Guardrail Enforcement

Application-layer guardrails are critical because Neo4j lacks conditional relationship constraints. Never bypass `canSyncToArchitecture()` check.

## Deployment

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NEO4J_URI` | - | Neo4j connection URI |
| `NEO4J_USER` | neo4j | Neo4j username |
| `NEO4J_PASSWORD` | - | Neo4j password |
| `ARCHITECTURE_MD_PATH` | ./ARCHITECTURE.md | Path to architecture doc |

### Railway Deployment

```bash
# Deploy to Railway
railway up

# Verify deployment
curl https://moltbot-railway-template-production-c0a3.up.railway.app/health
```

## Related Documentation

- **Guardrail Enforcement:** `docs/operations/guardrail-enforcement.md`
- **Implementation Plan:** `docs/plans/2026-02-07-kublai-proactive-self-awareness.md`
- **Migration Schema:** `migrations/v4_proposals.py`
- **Kublai SOUL:** `data/workspace/souls/main/SOUL.md`
