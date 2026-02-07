# Kublai Self-Awareness Operations Guide

## Overview

Kublai maintains self-awareness by querying ARCHITECTURE.md from Neo4j and proposing improvements via a collaborative workflow with Ögedei (Operations) and Temüjin (Development).

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

| State | Description | Can Transition To |
|-------|-------------|-------------------|
| `proposed` | Kublai creates proposal from identified opportunity | `under_review`, `rejected` |
| `under_review` | Ögedei is vetting the proposal | `approved`, `rejected`, `proposed` |
| `approved` | Ögedei has approved for implementation | `implemented`, `rejected` |
| `rejected` | Proposal rejected (terminal state) | - |
| `implemented` | Temüjin completed implementation | `validated`, `failed` |
| `validated` | Validation checks passed | `synced` |
| `synced` | Changes written to ARCHITECTURE.md (terminal state) | - |

## Agent Roles

### Kublai
- Queries architecture from Neo4j
- Identifies improvement opportunities
- Creates proposals
- Coordinates workflow

### Ögedei (Operations)
- Reviews proposals for operational impact
- Assesses deployment risk
- Provides recommendations
- Approves or rejects proposals

### Temüjin (Development)
- Implements approved proposals
- Tracks progress
- Completes implementation

### Validation System
- Runs checks on completed implementations
- Only validated implementations can sync to ARCHITECTURE.md

## Key Guardrail

**ARCHITECTURE.md only updates for validated implementations.**

Proposals must pass through:
1. Creation → 2. Ögedei vetting → 3. Approval → 4. Implementation → 5. Validation → 6. Sync

## Module Structure

```
src/
├── kublai/
│   ├── architecture-introspection.js   # Query ARCHITECTURE.md from Neo4j
│   ├── proactive-reflection.js         # Analyze and create opportunities
│   └── scheduled-reflection.js         # Weekly cron trigger
├── agents/
│   ├── ogedei/
│   │   └── vet-handler.js             # Operational vetting logic
│   └── temujin/
│       └── impl-handler.js            # Implementation tracking
└── workflow/
    ├── proposal-states.js             # State machine for proposals
    ├── proposal-mapper.js             # Map proposals to ARCHITECTURE.md sections
    └── validation.js                  # Validation checks
```

## Usage

### Trigger Manual Reflection

```javascript
const { ProactiveReflection } = require('./src/kublai/proactive-reflection');
const { ArchitectureIntrospection } = require('./src/kublai/architecture-introspection');

const introspection = new ArchitectureIntrospection(neo4jDriver, logger);
const reflection = new ProactiveReflection(neo4jDriver, introspection, logger);

const result = await reflection.triggerReflection();
console.log(`Found ${result.opportunitiesFound} opportunities`);
```

### Check Pending Proposals

```cypher
// Via Neo4j directly
MATCH (p:ArchitectureProposal {status: 'proposed'})
RETURN p.id, p.title, p.description, p.priority
ORDER BY p.priority DESC
```

### Ögedei Vetting

```javascript
const { OgedeiVetHandler } = require('./src/agents/ogedei/vet-handler');

const ogedei = new OgedeiVetHandler(neo4jDriver, logger);

// Vet a proposal
const vetting = await ogedei.vetProposal(proposalId);

// Approve after vetting
await ogedei.approveProposal(proposalId, 'Looks good, low risk');
```

### Temüjin Implementation

```javascript
const { TemujinImplHandler } = require('./src/agents/temujin/impl-handler');

const temujin = new TemujinImplHandler(neo4jDriver, logger);

// Start implementation
const impl = await temujin.implementProposal(proposalId);

// Update progress
await temujin.updateProgress(impl.implementationId, 50, 'Halfway done');

// Complete implementation
await temujin.completeImplementation(impl.implementationId, 'Implementation complete');
```

### Validation

```javascript
const { ValidationHandler } = require('./src/workflow/validation');

const validator = new ValidationHandler(neo4jDriver, logger);

const result = await validator.validateImplementation(implId);

if (result.passed) {
  console.log('Implementation validated!');
} else {
  console.log('Validation failed:', result.failedChecks);
}
```

### Sync to ARCHITECTURE.md

```bash
# Check which proposals are ready to sync
node scripts/sync-architecture-to-neo4j.js sync-proposals

# After manually adding to ARCHITECTURE.md, mark as synced
node scripts/sync-architecture-to-neo4j.js mark-synced <proposalId> <sectionTitle>
```

## Cypher Queries

### Get architecture overview

```cypher
MATCH (s:ArchitectureSection)
RETURN s.title, s.order, s.parent_section
ORDER BY s.order
```

### Search architecture content

```cypher
CALL db.index.fulltext.queryNodes('architecture_search_index', 'search term')
YIELD node, score
RETURN node.title, node.content, score
ORDER BY score DESC
LIMIT 10
```

### Get pending proposals

```cypher
MATCH (p:ArchitectureProposal {status: 'proposed'})
RETURN p.id, p.title, p.description, p.priority
ORDER BY p.priority DESC, p.proposed_at ASC
```

### Get proposals ready for Ögedei vetting

```cypher
MATCH (p:ArchitectureProposal {status: 'proposed'})
WHERE NOT EXISTS((p)-[:HAS_VETTING]->(:Vetting))
RETURN p.id, p.title, p.description
```

### Get proposals ready for Temüjin implementation

```cypher
MATCH (p:ArchitectureProposal {status: 'approved'})
WHERE NOT EXISTS((p)-[:IMPLEMENTED_BY]->(:Implementation))
RETURN p.id, p.title, p.description, p.approved_at
```

### Get implementations ready for validation

```cypher
MATCH (i:Implementation {status: 'completed'})
WHERE NOT EXISTS((:Validation)-[:VALIDATES]->(i))
MATCH (p:ArchitectureProposal)-[:IMPLEMENTED_BY]->(i)
RETURN i.id, i.completed_at, p.title
```

### Get proposals ready to sync (validated but not synced)

```cypher
MATCH (p:ArchitectureProposal {status: 'validated'})
WHERE NOT EXISTS((p)-[:SYNCED_TO]->(:ArchitectureSection))
RETURN p.id, p.title, p.target_section, p.implementation_status
```

## Troubleshooting

### Proposal not syncing to ARCHITECTURE.md

**Symptom:** `syncValidatedProposalsToArchitectureMd()` doesn't list the proposal.

**Check:**
1. Status must be `validated`
2. Implementation status must be `validated`
3. No `SYNCED_TO` relationship should exist

```cypher
MATCH (p:ArchitectureProposal {id: '<proposalId>'})
RETURN p.status, p.implementation_status,
       EXISTS((p)-[:SYNCED_TO]->(:ArchitectureSection)) as isSynced
```

### Reflection not finding opportunities

**Symptom:** `triggerReflection()` returns 0 opportunities.

**Check:**
1. ARCHITECTURE.md is synced to Neo4j (run sync script)
2. Full-text search index exists

```cypher
CALL db.indexes() YIELD name, type
WHERE name = 'architecture_search_index' AND type = 'FULLTEXT'
RETURN count(*) > 0 as exists
```

### Ögedei vetting not working

**Symptom:** Vetting returns error or recommendation is unexpected.

**Check:**
1. Proposal status is `proposed`
2. No existing vetting for this proposal

```cypher
MATCH (p:ArchitectureProposal {id: '<proposalId>'})
RETURN p.status,
       EXISTS((p)-[:HAS_VETTING]->(:Vetting)) as hasVetting
```

### Validation failing unexpectedly

**Symptom:** Implementation is complete but validation fails.

**Check:**
1. Implementation status is `completed`
2. Progress is at 100%
3. Summary is provided

```cypher
MATCH (i:Implementation {id: '<implId>'})
RETURN i.status, i.progress, i.summary
```

## Migration

Run the proposal system migration:

```bash
# Via Neo4j browser or cypher-shell
# Load scripts/migrations/003_proposals.cypher
```

This creates:
- Constraints for all proposal-related nodes
- Indexes for querying by status and priority
- Relationship patterns for the workflow

## API Endpoints (Future)

These endpoints could be added to moltbot for HTTP access:

- `GET /api/proposals` - List proposals by status
- `POST /api/proposals` - Create new proposal
- `POST /api/vet/:proposalId` - Trigger Ögedei vetting
- `POST /api/implement/:proposalId` - Start implementation
- `POST /api/validate/:implId` - Run validation
- `POST /api/sync/:proposalId` - Sync to ARCHITECTURE.md (manual)
- `GET /api/reflection` - Trigger proactive reflection
