# End-to-End Proposal Lifecycle Test Design

## Overview

This document describes the comprehensive end-to-end test for the complete proposal lifecycle, from opportunity detection through ARCHITECTURE.md sync. The test verifies all state transitions, agent interactions, and guardrail enforcement.

## Test Scenario

**Test Name:** `E2E_ProposalLifecycle_HappyPath`
**Objective:** Verify a proposal flows through all states from creation to sync
**Duration:** ~5 minutes (simulated)
**Agents Involved:** Kublai, Ögedei, Temüjin, System (Validation)

---

## State Machine Overview

```
proposed → under_review → approved → implemented → validated → synced
   ↑            ↓
rejected ←─────┘ (terminal states)
```

### Valid Transitions

| From State | Valid To States |
|------------|-----------------|
| proposed | under_review, rejected |
| under_review | approved, rejected, proposed |
| approved | implemented, rejected |
| implemented | validated, failed |
| validated | synced |
| rejected | (terminal) |
| synced | (terminal) |

---

## Test Case Table

### Phase 1: Opportunity Creation (Kublai/ProactiveReflection)

| Step | Action | Expected State | Neo4j Query | Validation Method |
|------|--------|----------------|-------------|-------------------|
| 1.1 | `triggerReflection()` detects missing "API Rate Limiting" section | Opportunity stored | See Query 1.1 | Verify node exists |
| 1.2 | Store `ImprovementOpportunity` in Neo4j | Status: 'proposed' | See Query 1.2 | Check properties |

**Query 1.1 - Verify Opportunity Created:**
```cypher
MATCH (o:ImprovementOpportunity {type: 'missing_section'})
WHERE o.description CONTAINS 'API Rate Limiting'
RETURN o.id, o.type, o.priority, o.status, o.proposed_by, o.created_at
```

**Query 1.2 - Get Opportunity Details:**
```cypher
MATCH (o:ImprovementOpportunity {status: 'proposed'})
WHERE o.suggested_section = 'API Rate Limiting'
RETURN o {
  .id,
  .type,
  .description,
  .priority,
  .suggested_section,
  .status,
  .proposed_by,
  .created_at,
  .last_seen
}
```

---

### Phase 2: Proposal Creation (Kublai)

| Step | Action | Expected State | Neo4j Query | Validation Method |
|------|--------|----------------|-------------|-------------------|
| 2.1 | Convert opportunity to `ArchitectureProposal` | Status: 'proposed' | See Query 2.1 | Verify node + relationship |
| 2.2 | Link opportunity to proposal | Relationship: EVOLVES_INTO | See Query 2.2 | Check relationship exists |
| 2.3 | Set initial implementation status | impl_status: 'not_started' | See Query 2.3 | Verify default values |

**Query 2.1 - Verify Proposal Created:**
```cypher
MATCH (p:ArchitectureProposal {title: 'Add API Rate Limiting'})
RETURN p {
  .id,
  .title,
  .description,
  .category,
  .status,
  .implementation_status,
  .priority,
  .proposed_by,
  .proposed_at
}
```

**Query 2.2 - Verify Opportunity-Proposal Link:**
```cypher
MATCH (o:ImprovementOpportunity)-[r:EVOLVES_INTO]->(p:ArchitectureProposal)
WHERE p.title = 'Add API Rate Limiting'
RETURN o.id as opportunity_id, p.id as proposal_id, type(r) as relationship
```

**Query 2.3 - Verify Initial State:**
```cypher
MATCH (p:ArchitectureProposal {title: 'Add API Rate Limiting'})
RETURN p.status = 'proposed' as is_proposed,
       p.implementation_status = 'not_started' as is_not_started,
       p.priority = 'medium' as is_medium_priority
```

---

### Phase 3: Proposal Vetting (Ögedei)

| Step | Action | Expected State | Neo4j Query | Validation Method |
|------|--------|----------------|-------------|-------------------|
| 3.1 | `OgedeiVetHandler.vetProposal()` assesses impact | Vetting record created | See Query 3.1 | Verify Vetting node |
| 3.2 | Assess operational impact | impact: 'high' | See Query 3.2 | Check assessment JSON |
| 3.3 | Assess deployment risk | risk: 'medium' | See Query 3.3 | Verify risk level |
| 3.4 | Make recommendation | recommendation: 'approve' | See Query 3.4 | Check recommendation |
| 3.5 | Transition proposal state | Status: 'under_review' → 'approved' | See Query 3.5 | Verify state change |

**Query 3.1 - Verify Vetting Record Created:**
```cypher
MATCH (p:ArchitectureProposal {title: 'Add API Rate Limiting'})-[:HAS_VETTING]->(v:Vetting)
RETURN v {
  .id,
  .proposal_id,
  .vetted_by,
  .vetted_at,
  .assessment
}
```

**Query 3.2 - Verify Impact Assessment:**
```cypher
MATCH (p:ArchitectureProposal {title: 'Add API Rate Limiting'})-[:HAS_VETTING]->(v:Vetting)
WITH v, apoc.convert.fromJsonMap(v.assessment) as assessment
RETURN assessment.operationalImpact as impact,
       assessment.deploymentRisk as risk,
       assessment.rolloutStrategy as strategy
```

**Query 3.3 - Verify Risk Assessment:**
```cypher
MATCH (p:ArchitectureProposal {title: 'Add API Rate Limiting'})
RETURN p.ogedei_recommendation as recommendation,
       p.status as current_status
```

**Query 3.4 - Verify Approval Metadata:**
```cypher
MATCH (p:ArchitectureProposal {title: 'Add API Rate Limiting'})
RETURN p.status = 'approved' as is_approved,
       p.approved_by = 'ogedei' as approved_by_ogedei,
       p.approved_at is not null as has_approval_date,
       p.approval_notes is not null as has_notes
```

**Query 3.5 - Verify State Transition History:**
```cypher
MATCH (p:ArchitectureProposal {title: 'Add API Rate Limiting'})
RETURN p.previous_state as previous,
       p.status as current,
       p.state_changed_at as changed_at,
       p.state_change_reason as reason
```

---

### Phase 4: Implementation (Temüjin)

| Step | Action | Expected State | Neo4j Query | Validation Method |
|------|--------|----------------|-------------|-------------------|
| 4.1 | `TemujinImplHandler.implementProposal()` starts work | impl_status: 'in_progress' | See Query 4.1 | Verify Implementation node |
| 4.2 | Create implementation record | Status: 'in_progress', progress: 0 | See Query 4.2 | Check initial progress |
| 4.3 | Link proposal to implementation | Relationship: IMPLEMENTED_BY | See Query 4.3 | Verify relationship |
| 4.4 | Update progress to 50% | progress: 50 | See Query 4.4 | Check progress update |
| 4.5 | Complete implementation | progress: 100, status: 'completed' | See Query 4.5 | Verify completion |
| 4.6 | Proposal impl_status updated | impl_status: 'completed' | See Query 4.6 | Check proposal updated |

**Query 4.1 - Verify Implementation Started:**
```cypher
MATCH (p:ArchitectureProposal {title: 'Add API Rate Limiting'})-[:IMPLEMENTED_BY]->(i:Implementation)
RETURN i {
  .id,
  .proposal_id,
  .status,
  .progress,
  .started_at,
  .notes
}
```

**Query 4.2 - Verify Implementation Record:**
```cypher
MATCH (i:Implementation {status: 'in_progress'})
MATCH (p:ArchitectureProposal {title: 'Add API Rate Limiting'})-[:IMPLEMENTED_BY]->(i)
RETURN i.id as impl_id,
       i.progress as progress,
       i.status as status,
       p.implementation_id = i.id as linked_correctly
```

**Query 4.3 - Verify Progress Updates:**
```cypher
MATCH (p:ArchitectureProposal {title: 'Add API Rate Limiting'})-[:IMPLEMENTED_BY]->(i:Implementation)
RETURN i.progress as current_progress,
       i.updated_at as last_updated,
       i.notes as progress_notes
ORDER BY i.updated_at DESC
LIMIT 1
```

**Query 4.4 - Verify Implementation Completed:**
```cypher
MATCH (p:ArchitectureProposal {title: 'Add API Rate Limiting'})-[:IMPLEMENTED_BY]->(i:Implementation)
RETURN i.status = 'completed' as is_completed,
       i.progress = 100 as is_100_percent,
       i.completed_at is not null as has_completion_date,
       i.summary is not null as has_summary
```

**Query 4.5 - Verify Proposal Implementation Status:**
```cypher
MATCH (p:ArchitectureProposal {title: 'Add API Rate Limiting'})
RETURN p.implementation_status = 'completed' as impl_completed,
       p.implementation_completed_at is not null as has_completion_date
```

---

### Phase 5: Validation (System/ValidationHandler)

| Step | Action | Expected State | Neo4j Query | Validation Method |
|------|--------|----------------|-------------|-------------------|
| 5.1 | `ValidationHandler.validateImplementation()` runs checks | Validation record created | See Query 5.1 | Verify Validation node |
| 5.2 | Check 1: Implementation complete | passed: true | See Query 5.2 | Verify check results |
| 5.3 | Check 2: Progress at 100% | passed: true | See Query 5.3 | Verify progress check |
| 5.4 | Check 3: Has completion summary | passed: true | See Query 5.4 | Verify summary exists |
| 5.5 | All checks pass | passed: true | See Query 5.5 | Verify overall pass |
| 5.6 | Update proposal status | Status: 'validated' | See Query 5.6 | Verify state transition |
| 5.7 | Update implementation validation | validation_status: 'passed' | See Query 5.7 | Verify impl updated |

**Query 5.1 - Verify Validation Record Created:**
```cypher
MATCH (i:Implementation)<-[:VALIDATES]-(v:Validation)
MATCH (p:ArchitectureProposal {title: 'Add API Rate Limiting'})-[:IMPLEMENTED_BY]->(i)
RETURN v {
  .id,
  .implementation_id,
  .validated_at,
  .passed,
  .status,
  .checks,
  .failed_count
}
```

**Query 5.2 - Verify Individual Checks:**
```cypher
MATCH (i:Implementation)<-[:VALIDATES]-(v:Validation)
MATCH (p:ArchitectureProposal {title: 'Add API Rate Limiting'})-[:IMPLEMENTED_BY]->(i)
WITH v, apoc.convert.fromJsonList(v.checks) as checks
UNWIND checks as check
RETURN check.name as check_name,
       check.passed as passed,
       check.description as description,
       check.critical as is_critical
```

**Query 5.3 - Verify All Critical Checks Passed:**
```cypher
MATCH (i:Implementation)<-[:VALIDATES]-(v:Validation)
MATCH (p:ArchitectureProposal {title: 'Add API Rate Limiting'})-[:IMPLEMENTED_BY]->(i)
WITH v, apoc.convert.fromJsonList(v.checks) as checks
UNWIND checks as check
WITH check
WHERE check.critical = true
RETURN all(c in collect(check) WHERE c.passed = true) as all_critical_passed
```

**Query 5.4 - Verify Validation Summary:**
```cypher
MATCH (i:Implementation)<-[:VALIDATES]-(v:Validation)
MATCH (p:ArchitectureProposal {title: 'Add API Rate Limiting'})-[:IMPLEMENTED_BY]->(i)
RETURN v.passed as validation_passed,
       v.status as validation_status,
       v.failed_count as failed_checks,
       v.validated_at as validated_at
```

**Query 5.5 - Verify Proposal Validated:**
```cypher
MATCH (p:ArchitectureProposal {title: 'Add API Rate Limiting'})
RETURN p.status = 'validated' as is_validated,
       p.implementation_status = 'validated' as impl_validated,
       p.previous_state = 'implemented' as came_from_implemented
```

**Query 5.6 - Verify Implementation Validation Status:**
```cypher
MATCH (p:ArchitectureProposal {title: 'Add API Rate Limiting'})-[:IMPLEMENTED_BY]->(i:Implementation)
RETURN i.validation_status = 'passed' as validation_passed,
       i.validated_at is not null as has_validation_date
```

---

### Phase 6: Sync to ARCHITECTURE.md (Guardrailed)

| Step | Action | Expected State | Neo4j Query | Validation Method |
|------|--------|----------------|-------------|-------------------|
| 6.1 | `ProposalMapper.checkCanSync()` verifies guardrail | allowed: true | See Query 6.1 | Verify guardrail passes |
| 6.2 | Guardrail checks proposal status | status: 'validated' | See Query 6.2 | Verify status check |
| 6.3 | Guardrail checks impl status | impl_status: 'validated' | See Query 6.3 | Verify impl check |
| 6.4 | `getReadyToSync()` lists proposal | Returns proposal | See Query 6.4 | Verify in ready list |
| 6.5 | `markSynced()` creates relationship | Relationship: SYNCED_TO | See Query 6.5 | Verify relationship |
| 6.6 | Update proposal status | Status: 'synced' | See Query 6.6 | Verify final state |
| 6.7 | Create ArchitectureSection node | Section created/merged | See Query 6.7 | Verify section exists |

**Query 6.1 - Verify Guardrail Check (Manual):**
```cypher
MATCH (p:ArchitectureProposal {title: 'Add API Rate Limiting'})
RETURN p.status = 'validated' AND p.implementation_status = 'validated' as can_sync
```

**Query 6.2 - Verify Proposal Ready for Sync:**
```cypher
MATCH (p:ArchitectureProposal {status: 'validated', implementation_status: 'validated'})
WHERE p.title = 'Add API Rate Limiting'
AND NOT EXISTS((p)-[:SYNCED_TO]->(:ArchitectureSection))
RETURN p.id as ready_id, p.title as title
```

**Query 6.3 - Verify Sync Readiness:**
```cypher
MATCH (p:ArchitectureProposal {title: 'Add API Rate Limiting'})
OPTIONAL MATCH (p)-[r:SYNCED_TO]->(s:ArchitectureSection)
RETURN p.status as status,
       p.implementation_status as impl_status,
       r is not null as already_synced,
       s.title as synced_to_section
```

**Query 6.4 - Get Ready to Sync Proposals:**
```cypher
MATCH (p:ArchitectureProposal {status: 'validated'})
WHERE NOT EXISTS((p)-[:SYNCED_TO]->(:ArchitectureSection))
RETURN p.id as id,
       p.title as title,
       p.target_section as target_section,
       p.implementation_status as impl_status
ORDER BY p.proposed_at DESC
```

**Query 6.5 - Verify SYNCED_TO Relationship:**
```cypher
MATCH (p:ArchitectureProposal {title: 'Add API Rate Limiting'})-[r:SYNCED_TO]->(s:ArchitectureSection)
RETURN p.id as proposal_id,
       s.title as section_title,
       r.synced_at as synced_at,
       p.synced_at as proposal_synced_at
```

**Query 6.6 - Verify Final Synced State:**
```cypher
MATCH (p:ArchitectureProposal {title: 'Add API Rate Limiting'})
RETURN p.status = 'synced' as is_synced,
       p.previous_state = 'validated' as came_from_validated,
       p.synced_at is not null as has_sync_date
```

**Query 6.7 - Verify Architecture Section:**
```cypher
MATCH (s:ArchitectureSection)
WHERE s.title = p.target_section  // or the determined section
RETURN s.title as section,
       s.order as section_order,
       s.updated_at as last_updated
```

---

## Guardrail Verification Tests

### Test: Guardrail Blocks Non-Validated Proposals

| Step | Action | Expected Result | Neo4j Query |
|------|--------|-----------------|-------------|
| G.1 | Create proposal with status 'proposed' | Guardrail rejects | See Query G.1 |
| G.2 | Create proposal with status 'implemented' (not validated) | Guardrail rejects | See Query G.2 |
| G.3 | Create proposal with impl_status 'completed' (not validated) | Guardrail rejects | See Query G.3 |
| G.4 | Create proposal with status 'validated' but impl_status 'completed' | Guardrail rejects | See Query G.4 |

**Query G.1 - Guardrail Rejects 'proposed':**
```cypher
// Setup
CREATE (p:ArchitectureProposal {
  id: 'test-guardrail-1',
  title: 'Test Guardrail Proposed',
  status: 'proposed',
  implementation_status: 'not_started'
})
// Check
WITH p
RETURN p.status = 'validated' AND p.implementation_status = 'validated' as can_sync
// Expected: false
```

**Query G.2 - Guardrail Rejects 'implemented' (not validated):**
```cypher
CREATE (p:ArchitectureProposal {
  id: 'test-guardrail-2',
  title: 'Test Guardrail Implemented',
  status: 'implemented',
  implementation_status: 'completed'
})
WITH p
RETURN p.status = 'validated' AND p.implementation_status = 'validated' as can_sync
// Expected: false
```

**Query G.3 - Guardrail Rejects impl_status 'completed' (not validated):**
```cypher
CREATE (p:ArchitectureProposal {
  id: 'test-guardrail-3',
  title: 'Test Guardrail Impl Completed',
  status: 'validated',
  implementation_status: 'completed'
})
WITH p
RETURN p.status = 'validated' AND p.implementation_status = 'validated' as can_sync
// Expected: false
```

**Query G.4 - Guardrail Accepts Both Validated:**
```cypher
CREATE (p:ArchitectureProposal {
  id: 'test-guardrail-4',
  title: 'Test Guardrail Validated',
  status: 'validated',
  implementation_status: 'validated'
})
WITH p
RETURN p.status = 'validated' AND p.implementation_status = 'validated' as can_sync
// Expected: true
```

---

## State Transition Validation Matrix

| Transition | From | To | Valid? | Test Case |
|------------|------|-----|--------|-----------|
| 1 | proposed | under_review | YES | Phase 3.5 |
| 2 | proposed | approved | NO | Test: InvalidTransition |
| 3 | proposed | implemented | NO | Test: InvalidTransition |
| 4 | proposed | validated | NO | Test: InvalidTransition |
| 5 | proposed | synced | NO | Test: InvalidTransition |
| 6 | proposed | rejected | YES | Test: RejectionPath |
| 7 | under_review | approved | YES | Phase 3.5 |
| 8 | under_review | rejected | YES | Test: RejectionPath |
| 9 | under_review | proposed | YES | Test: ReturnToProposed |
| 10 | approved | implemented | YES | Phase 4.1 |
| 11 | approved | rejected | YES | Test: RejectionPath |
| 12 | implemented | validated | YES | Phase 5.6 |
| 13 | implemented | failed | YES | Test: FailurePath |
| 14 | validated | synced | YES | Phase 6.6 |
| 15 | rejected | under_review | NO | Test: InvalidTransition |
| 16 | synced | proposed | NO | Test: InvalidTransition |

---

## Complete Lifecycle Verification Query

**Final State Verification:**
```cypher
// Complete lifecycle verification
MATCH (o:ImprovementOpportunity)-[:EVOLVES_INTO]->(p:ArchitectureProposal)
OPTIONAL MATCH (p)-[:HAS_VETTING]->(v:Vetting)
OPTIONAL MATCH (p)-[:IMPLEMENTED_BY]->(i:Implementation)
OPTIONAL MATCH (i)<-[:VALIDATES]-(val:Validation)
OPTIONAL MATCH (p)-[r:SYNCED_TO]->(s:ArchitectureSection)
WHERE p.title = 'Add API Rate Limiting'
RETURN {
  opportunity: {
    id: o.id,
    type: o.type,
    status: o.status
  },
  proposal: {
    id: p.id,
    title: p.title,
    status: p.status,
    implementation_status: p.implementation_status,
    proposed_by: p.proposed_by,
    approved_by: p.approved_by
  },
  vetting: {
    id: v.id,
    vetted_by: v.vetted_by,
    recommendation: p.ogedei_recommendation
  },
  implementation: {
    id: i.id,
    status: i.status,
    progress: i.progress,
    validation_status: i.validation_status
  },
  validation: {
    id: val.id,
    passed: val.passed,
    status: val.status
  },
  sync: {
    synced: r is not null,
    synced_at: r.synced_at,
    section: s.title
  }
} as lifecycle_state
```

**Expected Result:**
```json
{
  "opportunity": {
    "id": "<uuid>",
    "type": "missing_section",
    "status": "addressed"
  },
  "proposal": {
    "id": "<uuid>",
    "title": "Add API Rate Limiting",
    "status": "synced",
    "implementation_status": "validated",
    "proposed_by": "kublai",
    "approved_by": "ogedei"
  },
  "vetting": {
    "id": "<uuid>",
    "vetted_by": "ogedei",
    "recommendation": "approve"
  },
  "implementation": {
    "id": "<uuid>",
    "status": "completed",
    "progress": 100,
    "validation_status": "passed"
  },
  "validation": {
    "id": "<uuid>",
    "passed": true,
    "status": "passed"
  },
  "sync": {
    "synced": true,
    "synced_at": "2026-02-08T...",
    "section": "API Routes"
  }
}
```

---

## Test Execution Script

```javascript
// Pseudocode for E2E test execution

describe('E2E Proposal Lifecycle', () => {
  test('Complete lifecycle from opportunity to sync', async () => {
    // Phase 1: Create Opportunity
    const reflection = await proactiveReflection.triggerReflection();
    const opportunity = await getCreatedOpportunity('API Rate Limiting');
    expect(opportunity.status).toBe('proposed');

    // Phase 2: Create Proposal
    const proposalResult = await stateMachine.createProposal(
      opportunity.id,
      'Add API Rate Limiting',
      'Implement rate limiting for API endpoints',
      'security'
    );
    expect(proposalResult.status).toBe('proposed');

    // Phase 3: Vet Proposal
    const vetResult = await ogedeiVetHandler.vetProposal(proposalResult.proposalId);
    expect(vetResult.recommendation).toBe('approve');
    await ogedeiVetHandler.approveProposal(proposalResult.proposalId, 'Approved for implementation');

    // Verify state transition
    let status = await stateMachine.getStatus(proposalResult.proposalId);
    expect(status.status).toBe('approved');

    // Phase 4: Implement
    const implResult = await temujinImplHandler.implementProposal(proposalResult.proposalId);
    expect(implResult.status).toBe('in_progress');

    // Update progress
    await temujinImplHandler.updateProgress(implResult.implementationId, 50, 'Halfway done');
    await temujinImplHandler.updateProgress(implResult.implementationId, 100, 'Complete');
    await temujinImplHandler.completeImplementation(implResult.implementationId, 'Rate limiting implemented');

    // Phase 5: Validate
    const validationResult = await validationHandler.validateImplementation(implResult.implementationId);
    expect(validationResult.passed).toBe(true);

    // Verify validated state
    status = await stateMachine.getStatus(proposalResult.proposalId);
    expect(status.status).toBe('validated');
    expect(status.implStatus).toBe('validated');

    // Phase 6: Sync
    const canSync = await proposalMapper.checkCanSync(proposalResult.proposalId);
    expect(canSync.allowed).toBe(true);

    const syncResult = await proposalMapper.markSynced(proposalResult.proposalId, 'API Routes');
    expect(syncResult.success).toBe(true);

    // Final verification
    status = await stateMachine.getStatus(proposalResult.proposalId);
    expect(status.status).toBe('synced');
  });
});
```

---

## Summary

| Phase | Agent | Key Action | State Change |
|-------|-------|------------|--------------|
| 1 | Kublai | triggerReflection() | Opportunity created |
| 2 | Kublai | createProposal() | Status: proposed |
| 3 | Ögedei | vetProposal() + approveProposal() | Status: approved |
| 4 | Temüjin | implementProposal() + completeImplementation() | Status: implemented |
| 5 | System | validateImplementation() | Status: validated |
| 6 | System | markSynced() | Status: synced |

**Final State:** Proposal synced to ARCHITECTURE.md section "API Routes" with all validation passed.
