# End-to-End Proposal Lifecycle Test Design

## Overview

This document describes the comprehensive end-to-end test for the proposal lifecycle, walking through all six stages from opportunity creation to ARCHITECTURE.md sync.

## Test Scenario

Walk through the complete proposal lifecycle:

1. **Create Opportunity** (Kublai/ProactiveReflection)
2. **Create Proposal** (Kublai)
3. **Vet Proposal** (Ögedei)
4. **Implement Proposal** (Temüjin)
5. **Validate** (Kublai/System)
6. **Sync** (Guardrailed)

---

## Test Case Table

| Step | Action | Agent/System | Expected State | Neo4j Verification Query | Validation Method |
|------|--------|--------------|----------------|--------------------------|-------------------|
| 1.1 | `triggerReflection()` | Kublai | Opportunities detected | `MATCH (o:ImprovementOpportunity) WHERE o.status = 'proposed' RETURN count(o)` | Assert opportunities found > 0 |
| 1.2 | Store opportunity | Kublai | Opportunity persisted | `MATCH (o:ImprovementOpportunity {type: 'missing_section'}) RETURN o.id, o.status` | Assert status = 'proposed' |
| 2.1 | `createProposal(oppId)` | Kublai | Proposal created | `MATCH (p:ArchitectureProposal) WHERE p.title = '...' RETURN p.id, p.status` | Assert status = 'proposed' |
| 2.2 | Link to opportunity | Kublai | Relationship created | `MATCH (o)-[:EVOLVES_INTO]->(p) RETURN count(*)` | Assert count = 1 |
| 3.1 | Transition to under_review | StateMachine | Status updated | `MATCH (p) RETURN p.status` | Assert status = 'under_review' |
| 3.2 | `vetProposal(propId)` | Ögedei | Vetting complete | `MATCH (p)-[:HAS_VETTING]->(v) RETURN v.assessment` | Assert assessment exists |
| 3.3 | `approveProposal(propId)` | Ögedei | Proposal approved | `MATCH (p) RETURN p.status, p.approved_by` | Assert status = 'approved', approved_by = 'ogedei' |
| 4.1 | `implementProposal(propId)` | Temüjin | Implementation started | `MATCH (p)-[:IMPLEMENTED_BY]->(i) RETURN i.id, i.status` | Assert i.status = 'in_progress' |
| 4.2 | `updateProgress(implId, 50)` | Temüjin | Progress 50% | `MATCH (i) RETURN i.progress` | Assert progress = 50 |
| 4.3 | `updateProgress(implId, 100)` | Temüjin | Progress 100% | `MATCH (i) RETURN i.progress` | Assert progress = 100 |
| 4.4 | `completeImplementation(implId)` | Temüjin | Implementation complete | `MATCH (i) RETURN i.status, i.summary` | Assert status = 'completed' |
| 4.5 | Transition to implemented | StateMachine | Status updated | `MATCH (p) RETURN p.status, p.implementation_status` | Assert both = 'implemented'/'completed' |
| 5.1 | `validateImplementation(implId)` | ValidationHandler | Validation run | `MATCH (v:Validation) RETURN v.status, v.passed` | Assert passed = true |
| 5.2 | Update proposal status | System | Proposal validated | `MATCH (p) RETURN p.status, p.implementation_status` | Assert both = 'validated' |
| 6.1 | `mapProposalToSection(propId)` | ProposalMapper | Section mapped | `MATCH (p) RETURN p.target_section` | Assert target_section defined |
| 6.2 | `checkCanSync(propId)` | ProposalMapper | Guardrail check | N/A - method result | Assert allowed = true |
| 6.3 | `checkCanSync(nonValidated)` | ProposalMapper | Guardrail blocks | N/A - method result | Assert allowed = false, reason contains 'Guardrail' |
| 6.4 | `getReadyToSync()` | ProposalMapper | List ready proposals | `MATCH (p {status: 'validated'}) WHERE NOT (p)-[:SYNCED_TO]->() RETURN count(p)` | Assert includes test proposal |
| 6.5 | `markSynced(propId, section)` | ProposalMapper | Proposal synced | `MATCH (p)-[r:SYNCED_TO]->(s) RETURN p.status, r.synced_at` | Assert status = 'synced', synced_at defined |

---

## State Machine Transitions

### Valid Transitions

```
proposed → under_review
proposed → rejected
under_review → approved
under_review → rejected
under_review → proposed
approved → implemented
approved → rejected
implemented → validated
implemented → failed
validated → synced
```

### Invalid Transitions (Guarded)

```
proposed → approved        (must go through under_review)
proposed → implemented     (must be approved first)
proposed → synced          (must complete full lifecycle)
implemented → synced       (must be validated first)
rejected → any             (terminal state)
synced → any               (terminal state)
```

### State Transition Verification

```javascript
// Valid transitions
expect(stateMachine.canTransition('proposed', 'under_review')).toBe(true);
expect(stateMachine.canTransition('under_review', 'approved')).toBe(true);
expect(stateMachine.canTransition('approved', 'implemented')).toBe(true);
expect(stateMachine.canTransition('implemented', 'validated')).toBe(true);
expect(stateMachine.canTransition('validated', 'synced')).toBe(true);

// Invalid transitions
expect(stateMachine.canTransition('proposed', 'approved')).toBe(false);
expect(stateMachine.canTransition('proposed', 'implemented')).toBe(false);
expect(stateMachine.canTransition('proposed', 'synced')).toBe(false);
expect(stateMachine.canTransition('implemented', 'synced')).toBe(false);
expect(stateMachine.canTransition('synced', 'proposed')).toBe(false);
```

---

## Neo4j Cypher Queries by Stage

### Stage 1: Create Opportunity

```cypher
// Verify opportunity created
MATCH (o:ImprovementOpportunity)
WHERE o.type = 'missing_section'
AND o.description CONTAINS 'security'
RETURN o.id as id,
       o.status as status,
       o.priority as priority,
       o.created_at as createdAt,
       o.proposed_by as proposedBy

// Expected: status = 'proposed', proposedBy = 'kublai'
```

### Stage 2: Create Proposal

```cypher
// Verify proposal created and linked to opportunity
MATCH (o:ImprovementOpportunity {id: $opportunityId})-[:EVOLVES_INTO]->(p:ArchitectureProposal)
RETURN p.id as proposalId,
       p.title as title,
       p.status as status,
       p.implementation_status as implStatus,
       p.category as category,
       p.proposed_at as proposedAt,
       p.proposed_by as proposedBy

// Expected: status = 'proposed', implStatus = 'not_started'
```

### Stage 3: Vet Proposal

```cypher
// Verify vetting completed
MATCH (p:ArchitectureProposal {id: $proposalId})-[:HAS_VETTING]->(v:Vetting)
RETURN p.status as proposalStatus,
       p.ogedei_recommendation as recommendation,
       p.approved_by as approvedBy,
       p.approved_at as approvedAt,
       v.vetted_by as vettedBy,
       v.assessment as assessment

// Expected: proposalStatus = 'approved', vettedBy = 'ogedei'
```

### Stage 4: Implement Proposal

```cypher
// Verify implementation progress
MATCH (p:ArchitectureProposal {id: $proposalId})-[:IMPLEMENTED_BY]->(i:Implementation)
RETURN p.status as proposalStatus,
       p.implementation_status as implStatus,
       i.id as implementationId,
       i.status as status,
       i.progress as progress,
       i.started_at as startedAt,
       i.completed_at as completedAt,
       i.summary as summary

// Expected: proposalStatus = 'implemented', progress = 100, status = 'completed'
```

### Stage 5: Validate

```cypher
// Verify validation passed
MATCH (p:ArchitectureProposal {id: $proposalId})
MATCH (i:Implementation {proposal_id: $proposalId})
MATCH (v:Validation {implementation_id: i.id})
RETURN p.status as proposalStatus,
       p.implementation_status as implStatus,
       i.validation_status as validationStatus,
       v.passed as passed,
       v.status as validationResult,
       v.checks as checks

// Expected: proposalStatus = 'validated', implStatus = 'validated', passed = true
```

### Stage 6: Sync

```cypher
// Verify sync completed
MATCH (p:ArchitectureProposal {id: $proposalId})-[r:SYNCED_TO]->(s:ArchitectureSection)
RETURN p.status as status,
       p.synced_at as syncedAt,
       s.title as sectionTitle,
       r.synced_at as relationshipSyncedAt

// Expected: status = 'synced', sectionTitle = 'Security Architecture'
```

### Complete Lifecycle Query

```cypher
// Full lifecycle verification
MATCH (o:ImprovementOpportunity {id: $opportunityId})-[:EVOLVES_INTO]->(p:ArchitectureProposal {id: $proposalId})
OPTIONAL MATCH (p)-[:HAS_VETTING]->(v:Vetting)
OPTIONAL MATCH (p)-[:IMPLEMENTED_BY]->(i:Implementation)
OPTIONAL MATCH (p)-[r:SYNCED_TO]->(s:ArchitectureSection)
RETURN {
  // Opportunity
  opportunityId: o.id,
  opportunityType: o.type,
  opportunityStatus: o.status,

  // Proposal
  proposalId: p.id,
  proposalTitle: p.title,
  proposalStatus: p.status,
  proposalImplStatus: p.implementation_status,
  proposalCategory: p.category,

  // Vetting
  vettedBy: v.vetted_by,
  vettingRecommendation: p.ogedei_recommendation,
  approvedBy: p.approved_by,
  approvedAt: p.approved_at,

  // Implementation
  implementationId: i.id,
  implementationStatus: i.status,
  implementationProgress: i.progress,
  implementationCompletedAt: i.completed_at,

  // Sync
  syncedTo: s.title,
  syncedAt: r.synced_at
} as lifecycle

// Expected final state:
// - opportunityStatus = 'proposed' (or 'addressed' if updated)
// - proposalStatus = 'synced'
// - proposalImplStatus = 'validated'
// - vettedBy = 'ogedei'
// - approvedBy = 'ogedei'
// - implementationStatus = 'completed'
// - implementationProgress = 100
// - syncedTo = 'Security Architecture' (or mapped section)
// - syncedAt = timestamp
```

---

## Guardrail Verification

### checkCanSync() Guardrail

The `ProposalMapper.checkCanSync()` method enforces the critical guardrail:

```javascript
// GUARDRAIL: Only validated proposals with validated implementation can sync
const canSync = record.status === 'validated' &&
                record.implStatus === 'validated';
```

### Guardrail Test Cases

| Scenario | Proposal Status | Impl Status | Expected Result |
|----------|-----------------|-------------|-----------------|
| Valid sync | 'validated' | 'validated' | allowed = true |
| Not validated | 'implemented' | 'completed' | allowed = false, reason contains 'Guardrail' |
| Impl not validated | 'validated' | 'completed' | allowed = false, reason contains 'Guardrail' |
| Not implemented | 'approved' | 'not_started' | allowed = false, reason contains 'Guardrail' |
| Proposed only | 'proposed' | 'not_started' | allowed = false, reason contains 'Guardrail' |

### Guardrail Query Verification

```cypher
// Verify guardrail allows only validated + validated
MATCH (p:ArchitectureProposal {id: $proposalId})
RETURN p.status = 'validated' AND p.implementation_status = 'validated' as canSync

// Expected: canSync = true
```

---

## Expected Final State

After completing the full lifecycle, the proposal should have:

### Node Properties

**ImprovementOpportunity:**
- `status`: 'proposed' (or 'addressed' if marked)
- `type`: 'missing_section'
- `description`: Contains 'security'

**ArchitectureProposal:**
- `status`: 'synced'
- `implementation_status`: 'validated'
- `title`: 'E2E-Test- Add Security Architecture Section'
- `category`: 'security'
- `target_section`: 'Security Architecture'
- `synced_at`: timestamp
- `approved_by`: 'ogedei'
- `approved_at`: timestamp

**Implementation:**
- `status`: 'completed'
- `progress`: 100
- `summary`: Contains implementation details

**Vetting:**
- `vetted_by`: 'ogedei'
- `assessment`: JSON string with operational impact, deployment risk, etc.

**Validation:**
- `status`: 'passed'
- `passed`: true
- `checks`: JSON array of validation check results

**ArchitectureSection:**
- `title`: 'E2E-Test- Security Architecture'

### Relationships

```cypher
// Verify all relationships exist
MATCH (o:ImprovementOpportunity {id: $oppId})-[:EVOLVES_INTO]->(p:ArchitectureProposal {id: $propId})
MATCH (p)-[:HAS_VETTING]->(v:Vetting)
MATCH (p)-[:IMPLEMENTED_BY]->(i:Implementation)
MATCH (p)-[:SYNCED_TO]->(s:ArchitectureSection)
RETURN count(o) as opportunities,
       count(p) as proposals,
       count(v) as vettings,
       count(i) as implementations,
       count(s) as sections

// Expected: all counts = 1
```

---

## Test Execution

### Prerequisites

1. Neo4j database running (local or remote)
2. Environment variables set:
   - `NEO4J_URI` (default: bolt://localhost:7687)
   - `NEO4J_USER` (default: neo4j)
   - `NEO4J_PASSWORD` (default: password)

### Run Test

```bash
cd /Users/kurultai/molt/moltbot-railway-template
npm test -- tests/e2e/proposal-lifecycle.test.js
```

### Expected Output

```
E2E Proposal Lifecycle
  Step 1: Create Opportunity (Kublai/ProactiveReflection)
    ✓ should trigger reflection and detect missing section
    ✓ should store ImprovementOpportunity in Neo4j
  Step 2: Create Proposal (Kublai)
    ✓ should convert opportunity to ArchitectureProposal
    ✓ should link proposal to opportunity via EVOLVES_INTO relationship
    ✓ should have initial status proposed and impl_status not_started
  Step 3: Vet Proposal (Ögedei)
    ✓ should transition proposal to under_review
    ✓ should run OgedeiVetHandler.vetProposal() and assess operational impact
    ✓ should store vetting result with HAS_VETTING relationship
    ✓ should approve proposal with recommendation
    ✓ should have status approved
  Step 4: Implement Proposal (Temüjin)
    ✓ should start implementation via TemujinImplHandler.implementProposal()
    ✓ should create IMPLEMENTED_BY relationship to Implementation node
    ✓ should update implementation progress to 50%
    ✓ should update implementation progress to 100%
    ✓ should complete implementation with summary
    ✓ should transition proposal to implemented
    ✓ should have implementation_status completed
  Step 5: Validate (Kublai/System)
    ✓ should run validation checks on implementation
    ✓ should pass validation checks
    ✓ should create Validation node with PASSED status
    ✓ should update proposal status to validated
  Step 6: Sync (Guardrailed)
    ✓ should map proposal to target ARCHITECTURE.md section
    ✓ should map security proposal to Security Architecture section
    ✓ ProposalMapper.checkCanSync() should allow validated proposals
    ✓ ProposalMapper.checkCanSync() should block non-validated proposals
    ✓ syncValidatedProposalsToArchitectureMd() should list ready proposals
    ✓ markSynced() should create SYNCED_TO relationship
    ✓ should have final status synced
    ✓ should create SYNCED_TO relationship with timestamp
  State Machine Transition Validation
    ✓ should enforce valid state transitions
    ✓ should reject invalid state transitions
  Complete Lifecycle Verification
    ✓ should verify complete proposal lifecycle in Neo4j
```

---

## File Locations

- **Test Implementation:** `/Users/kurultai/molt/moltbot-railway-template/tests/e2e/proposal-lifecycle.test.js`
- **Test Design:** `/Users/kurultai/molt/moltbot-railway-template/tests/e2e/PROPOSAL_LIFECYCLE_TEST_DESIGN.md`
- **State Machine:** `/Users/kurultai/molt/moltbot-railway-template/src/workflow/proposal-states.js`
- **Proposal Mapper:** `/Users/kurultai/molt/moltbot-railway-template/src/workflow/proposal-mapper.js`
- **Validation Handler:** `/Users/kurultai/molt/moltbot-railway-template/src/workflow/validation.js`
- **Ögedei Vet Handler:** `/Users/kurultai/molt/moltbot-railway-template/src/agents/ogedei/vet-handler.js`
- **Temüjin Impl Handler:** `/Users/kurultai/molt/moltbot-railway-template/src/agents/temujin/impl-handler.js`
- **Proactive Reflection:** `/Users/kurultai/molt/moltbot-railway-template/src/kublai/proactive-reflection.js`
