# Kublai Self-Awareness Operations Guide

> **Version:** 1.0
> **Last Updated:** 2026-02-08
> **Applies To:** moltbot-railway-template v2.0+

---

## Overview

Kublai maintains self-awareness by querying ARCHITECTURE.md from Neo4j and proposing improvements via a collaborative workflow with Ögedei (Operations) and Temüjin (Development).

## Architecture

```
ARCHITECTURE.md → Neo4j (via git hook) → Kublai queries → identifies opportunities
                                                              ↓
                                                    Creates ImprovementOpportunity
                                                              ↓
                                                    Evolves into ArchitectureProposal
                                                              ↓
                                                         Ögedei vets
                                                              ↓
                                                    Temüjin implements
                                                              ↓
                                                    Validation checks
                                                              ↓
                                              Only THEN syncs back to ARCHITECTURE.md
```

## Proposal States

1. **proposed** - Kublai creates proposal from identified opportunity
2. **under_review** - Ögedei reviewing operational impact
3. **approved** - Ready for implementation
4. **rejected** - Not proceeding
5. **implemented** - Temüjin completed work
6. **validated** - Validation checks passed
7. **synced** - Changes written to ARCHITECTURE.md

## Agent Roles

### Kublai (Orchestrator)
- Queries architecture from Neo4j via `ArchitectureIntrospection`
- Identifies improvement opportunities via `ProactiveReflection`
- Creates proposals via `ProposalStateMachine`
- Coordinates workflow via `DelegationProtocol`

### Ögedei (Operations)
- Reviews proposals for operational impact via `OgedeiVetHandler`
- Assesses deployment risk
- Provides recommendations (approve, reject, approve_with_conditions)

### Temüjin (Development)
- Implements approved proposals via `TemujinImplHandler`
- Tracks progress on implementations
- Completes implementation and triggers validation

## Key Guardrail

**ARCHITECTURE.md only updates for validated implementations.**

Proposals must pass through:
1. Creation → 2. Ögedei vetting → 3. Approval → 4. Implementation → 5. Validation → 6. Sync

## Scheduled Operations

### Weekly Reflection (Sundays at 8 PM ET)
```
cron: "0 20 * * 0"
```
Kublai automatically scans architecture for:
- Missing expected sections (system architecture, API routes, data model, security, deployment)
- Opportunities for improvement
- Gaps in documentation

## API Endpoints

### Trigger Manual Reflection
```bash
curl -X POST http://localhost:8082/api/reflection/trigger \
  -H 'Content-Type: application/json' \
  -d '{}'
```

### Check Pending Proposals
```bash
curl http://localhost:8082/api/proposals?status=proposed
```

### Ögedei Vet a Proposal
```bash
curl -X POST http://localhost:8082/api/vet \
  -H 'Content-Type: application/json' \
  -d '{"proposalId": "..."}'
```

### Temüjin Implement
```bash
curl -X POST http://localhost:8082/api/implement \
  -H 'Content-Type: application/json' \
  -d '{"proposalId": "..."}'
```

### Check Health Status
```bash
curl http://localhost:8082/health
```

Response includes Kublai module status:
```json
{
  "kublai": {
    "neo4jConnected": true,
    "reflectionScheduled": true,
    "modulesLoaded": true,
    "delegationProtocol": true,
    "handlers": {
      "ogedei": true,
      "temujin": true
    }
  }
}
```

## Module Initialization

Kublai modules initialize automatically on startup if Neo4j is configured:

```javascript
// From src/index.js
const kublaiInitialized = await initKublaiModules();
if (kublaiInitialized) {
  logger.info('Kublai self-awareness modules initialized');
}
```

Modules initialized:
- `ArchitectureIntrospection` - Query ARCHITECTURE.md from Neo4j
- `ProactiveReflection` - Identify improvement opportunities
- `ScheduledReflection` - Weekly cron trigger
- `ProposalStateMachine` - Manage proposal lifecycle
- `ProposalMapper` - Map proposals to ARCHITECTURE.md sections
- `ValidationHandler` - Validate implementations
- `OgedeiVetHandler` - Operations vetting
- `TemujinImplHandler` - Development implementation
- `DelegationProtocol` - Wire everything together

## Configuration

### Environment Variables
```bash
# Required for Kublai modules
NEO4J_URI=bolt://neo4j.railway.internal:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=<secure_password>

# Optional: Enable auto-vetting, auto-implementation
KUBLAI_AUTO_VET=true
KUBLAI_AUTO_IMPLEMENT=true
KUBLAI_AUTO_VALIDATE=true
```

### Scheduled Reflection Options
```javascript
// Weekly reflection with callback for opportunities
scheduledReflection.start({
  onOpportunitiesFound: async (opportunities) => {
    // Trigger delegation protocol for each opportunity
    for (const opp of opportunities) {
      await delegationProtocol.processOpportunity(opp);
    }
  }
});
```

## Troubleshooting

### Proposal not syncing to ARCHITECTURE.md
- Check status: must be `validated`
- Check implementation_status: must be `validated`
- Check for SYNCED_TO relationship in Neo4j
- Verify `autoSync` is enabled in delegation protocol config

```cypher
// Query proposal status
MATCH (p:ArchitectureProposal {id: $proposalId})
RETURN p.status, p.implementation_status, p.synced_to_architecture
```

### Reflection not finding opportunities
- Verify ARCHITECTURE.md is synced to Neo4j:
```bash
curl -X POST http://localhost:8082/api/architecture/sync
```
- Check full-text search index exists:
```cypher
CALL db.indexes() YIELD name, type
WHERE name CONTAINS 'architecture'
RETURN name, type
```
- Review section titles in ArchitectureSection nodes:
```cypher
MATCH (s:ArchitectureSection)
RETURN s.title, s.order
ORDER BY s.order
```

### Neo4j connection failing
- Check environment variables are set
- Verify Neo4j service is healthy
- Check network connectivity from moltbot to Neo4j

### Scheduled reflection not running
- Check railway.yml schedules are deployed
- Verify `scheduledReflection.start()` was called in logs
- Check timezone configuration (America/New_York)

## Monitoring

### Key Metrics
- `kublai_reflection_opportunities_found` - Opportunities identified per reflection
- `kublai_proposals_created` - Total proposals created
- `kublai_proposals_by_status` - Count by status
- `kublai_vetting_duration_ms` - Time for Ögedei vetting
- `kublai_implementation_duration_ms` - Time for Temüjin implementation

### Log Patterns
```
[Kublai] Running weekly architecture reflection...
[Kublai] Reflection complete: { sectionsKnown: 12, opportunitiesFound: 2 }
[Proposal] Created: <uuid> - Missing section: security
[Ögedei] Vetting proposal: <uuid>
[Ögedei] Vetting complete: approve
[Temüjin] Implementation started: <uuid>
[Validation] Result: PASSED
```

## Migration

To apply the proposal schema migration:

```bash
# Via cypher-shell
cypher-shell -u neo4j -p <password> < scripts/migrations/003_proposals.cypher

# Or via Neo4j Browser
# Copy contents of scripts/migrations/003_proposals.cypher and execute
```

Migration creates:
- Unique constraints on proposal/opportunity IDs
- Indexes for status queries
- Full-text search index for proposals

## Related Documentation

- [Kublai Self-Understanding Plan](../../docs/plans/2026-02-07-kublai-self-understanding.md)
- [Kublai Proactive Self-Awareness Plan](../../docs/plans/2026-02-07-kublai-proactive-self-awareness.md)
- [Architecture Sync Script](../../tools/kurultai/store_architecture_in_neo4j.py)
