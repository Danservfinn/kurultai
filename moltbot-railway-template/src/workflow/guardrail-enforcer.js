/**
 * Guardrail Enforcer for Kublai Self-Awareness Proposal System
 *
 * CRITICAL: Only validated+implemented proposals can sync to ARCHITECTURE.md
 *
 * This module enforces the guardrail at the application layer since Neo4j
 * does not support conditional relationship constraints natively.
 *
 * Security: OWASP A01:2021 - Broken Access Control
 * The guardrail prevents unauthorized architecture changes.
 *
 * @module guardrail-enforcer
 * @author Claude (Anthropic)
 * @date 2026-02-07
 */

/**
 * Guardrail violation error
 */
class GuardrailViolationError extends Error {
  constructor(message, reason) {
    super(message);
    this.name = 'GuardrailViolationError';
    this.reason = reason;
  }
}

/**
 * Enforces the guardrail: Only validated+implemented proposals can sync
 *
 * @param {string} proposalId - The proposal ID to verify before sync
 * @param {Object} driver - Neo4j driver instance
 * @returns {Promise<{allowed: boolean, reason?: string}>}
 */
async function canSyncToArchitecture(proposalId, driver) {
  const session = driver.session();
  try {
    // Step 1: Verify proposal exists
    const proposalResult = await session.run(`
      MATCH (p:ArchitectureProposal {id: $proposalId})
      RETURN p.status as status, p.implementation_status as implStatus
    `, { proposalId });

    if (proposalResult.records.length === 0) {
      return { allowed: false, reason: 'Proposal not found' };
    }

    const record = proposalResult.records[0];
    const status = record.get('status');
    const implStatus = record.get('implStatus');

    // Step 2: Verify implementation is complete
    if (implStatus !== 'completed') {
      return {
        allowed: false,
        reason: `Implementation not complete. Current status: ${implStatus}. Status must be 'completed'.`
      };
    }

    // Step 3: Verify proposal is validated
    if (status !== 'validated') {
      return {
        allowed: false,
        reason: `Proposal not validated. Current status: ${status}. Status must be 'validated'.`
      };
    }

    // Step 4: Verify validation passed (double-check Validation node)
    const validationResult = await session.run(`
      MATCH (p:ArchitectureProposal {id: $proposalId})
      MATCH (p)-[:IMPLEMENTED_BY]->(i:Implementation)
      MATCH (i)-[:VALIDATED_BY]->(v:Validation)
      RETURN v.passed as passed, v.validated_at as validatedAt
      ORDER BY v.validated_at DESC
      LIMIT 1
    `, { proposalId });

    if (validationResult.records.length === 0) {
      return {
        allowed: false,
        reason: 'No validation record found. Proposal must have passed validation.'
      };
    }

    const validationRecord = validationResult.records[0];
    const passed = validationRecord.get('passed');

    if (!passed) {
      return {
        allowed: false,
        reason: `Validation did not pass. Validation checks must pass before sync.`
      };
    }

    // All checks passed
    return { allowed: true };

  } catch (error) {
    throw new Error(`Guardrail check failed: ${error.message}`);
  } finally {
    await session.close();
  }
}

/**
 * Creates SYNCED_TO relationship with guardrail enforcement
 *
 * @param {string} proposalId - The validated+implemented proposal
 * @param {string} sectionTitle - The ARCHITECTURE.md section to sync to
 * @param {Object} driver - Neo4j driver instance
 * @returns {Promise<{success: boolean, reason?: string}>}
 */
async function syncToArchitecture(proposalId, sectionTitle, driver) {
  // First, enforce the guardrail
  const check = await canSyncToArchitecture(proposalId, driver);

  if (!check.allowed) {
    throw new GuardrailViolationError(
      `Guardrail blocked sync for proposal ${proposalId}: ${check.reason}`,
      check.reason
    );
  }

  // Guardrail passed - create SYNCED_TO relationship
  const session = driver.session();
  try {
    await session.run(`
      MATCH (p:ArchitectureProposal {id: $proposalId})
      MATCH (s:ArchitectureSection {title: $sectionTitle})
      CREATE (p)-[r:SYNCED_TO {
        synced_at: datetime(),
        guardrail_verified: true
      }]->(s)
      RETURN r
    `, { proposalId, sectionTitle });

    return { success: true };

  } finally {
    await session.close();
  }
}

/**
 * Audit query to detect any guardrail violations
 *
 * Checks for SYNCED_TO relationships that bypass the guardrail.
 * Run this periodically to detect potential security issues.
 *
 * @param {Object} driver - Neo4j driver instance
 * @returns {Promise<Array<{proposalId: string, violation: string}>>}
 */
async function auditGuardrailViolations(driver) {
  const session = driver.session();
  try {
    const result = await session.run(`
      // Find proposals with SYNCED_TO but invalid state
      MATCH (p:ArchitectureProposal)-[r:SYNCED_TO]->(s:ArchitectureSection)
      WHERE p.status <> 'validated' OR p.implementation_status <> 'completed'
      RETURN p.id as proposalId,
             p.status as status,
             p.implementation_status as implStatus,
             r.synced_at as syncedAt
      ORDER BY r.synced_at DESC
    `);

    return result.records.map(record => ({
      proposalId: record.get('proposalId'),
      violation: `Proposal has status='${record.get('status')}' and implStatus='${record.get('implStatus')}' but was synced`,
      syncedAt: record.get('syncedAt').toString()
    }));

  } finally {
    await session.close();
  }
}

module.exports = {
  canSyncToArchitecture,
  syncToArchitecture,
  auditGuardrailViolations,
  GuardrailViolationError
};
