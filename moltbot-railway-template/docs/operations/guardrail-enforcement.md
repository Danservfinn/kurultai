# Guardrail Enforcement Documentation

## Overview

The Kublai Self-Awareness Proposal System includes a **critical security guardrail**:

> **Only validated+implemented proposals can sync to ARCHITECTURE.md**

This prevents premature or unproven architecture changes from being documented.

## Architecture

Since Neo4j does not support conditional relationship constraints natively, the guardrail is enforced at the **application layer**.

### Proposal State Machine

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   PROPOSED   │────▶│ UNDER_REVIEW │────▶│   APPROVED   │────▶│ IMPLEMENTED │────▶│  VALIDATED  │
└─────────────┘     └──────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                                                                                  │
                                                                                  │ Guardrail
                                                                                  │ Check
                                                                                  ▼
                                                                        ┌─────────────┐
                                                                        │   SYNCED    │──▶ ARCHITECTURE.md
                                                                        └─────────────┘
```

### Dual Status Tracking

The proposal system tracks TWO independent status properties:

| Property | Values | Purpose |
|----------|--------|---------|
| `status` | proposed, under_review, approved, rejected, implemented, validated, synced | Workflow state |
| `implementation_status` | not_started, in_progress, completed, validated | Implementation progress |

**Guardrail condition:** BOTH must be satisfied:
- `status = 'validated'`
- `implementation_status = 'completed'`

AND a Validation node must exist with `passed = true`.

## Implementation

### Module: `src/workflow/guardrail-enforcer.js`

```javascript
const { canSyncToArchitecture, syncToArchitecture, auditGuardrailViolations } = require('./guardrail-enforcer');

// Check if proposal can sync
const check = await canSyncToArchitecture(proposalId, driver);
if (!check.allowed) {
  console.error(`Guardrail blocked: ${check.reason}`);
  return;
}

// Sync to ARCHITECTURE.md
await syncToArchitecture(proposalId, 'API Routes', driver);
```

### Guardrail Checks

The `canSyncToArchitecture()` function verifies:

1. **Proposal exists** - The proposal ID must be valid
2. **Implementation complete** - `implementation_status = 'completed'`
3. **Proposal validated** - `status = 'validated'`
4. **Validation passed** - A Validation node with `passed = true` exists

### Security Considerations

**OWASP A01:2021 - Broken Access Control**

This guardrail is a security control preventing unauthorized architecture changes.

**Attack Vector:** A malicious actor with direct database access could bypass the application-layer guardrail by creating SYNCED_TO relationships directly.

**Mitigation:**
1. **Application-layer enforcement** - Always use `syncToArchitecture()` function
2. **Audit logging** - Log all SYNCED_TO relationship creations
3. **Periodic audits** - Run `auditGuardrailViolations()` to detect bypasses
4. **Database permissions** - Restrict direct write access to Neo4j

### Audit Query

Run periodically to detect violations:

```javascript
const violations = await auditGuardrailViolations(driver);
if (violations.length > 0) {
  console.error('Guardrail violations detected:', violations);
  // Alert security team
}
```

## Testing

### Unit Test Example

```javascript
describe('Guardrail Enforcer', () => {
  it('should block sync for unimplemented proposal', async () => {
    const check = await canSyncToArchitecture('proposal-1', driver);
    expect(check.allowed).toBe(false);
    expect(check.reason).toContain('Implementation not complete');
  });

  it('should block sync for unvalidated proposal', async () => {
    const check = await canSyncToArchitecture('proposal-2', driver);
    expect(check.allowed).toBe(false);
    expect(check.reason).toContain('Proposal not validated');
  });

  it('should allow sync for validated+implemented proposal', async () => {
    const check = await canSyncToArchitecture('proposal-3', driver);
    expect(check.allowed).toBe(true);
  });
});
```

### Integration Test Example

```javascript
describe('Guardrail Integration', () => {
  it('should create SYNCED_TO after validation passes', async () => {
    // Setup: Create validated+implemented proposal
    await createValidatedProposal('proposal-4', driver);

    // Execute sync
    await syncToArchitecture('proposal-4', 'System Overview', driver);

    // Verify SYNCED_TO relationship exists
    const session = driver.session();
    const result = await session.run(`
      MATCH (p:ArchitectureProposal {id: 'proposal-4'})-[r:SYNCED_TO]->(s:ArchitectureSection)
      RETURN s.title as section
    `);
    expect(result.records.length).toBe(1);
    expect(result.records[0].get('section')).toBe('System Overview');
  });

  it('should throw GuardrailViolationError for invalid proposal', async () => {
    // Setup: Create proposal without validation
    await createProposalWithoutValidation('proposal-5', driver);

    // Attempt sync - should throw
    await expect(
      syncToArchitecture('proposal-5', 'API Routes', driver)
    ).rejects.toThrow(GuardrailViolationError);
  });
});
```

## Deployment Checklist

- [ ] Guardrail enforcer module deployed
- [ ] All sync operations use `syncToArchitecture()` function
- [ ] Audit logging enabled for SYNCED_TO relationships
- [ ] Periodic audit queries scheduled
- [ ] Database permissions restrict direct writes
- [ ] Monitoring alerts for guardrail violations
