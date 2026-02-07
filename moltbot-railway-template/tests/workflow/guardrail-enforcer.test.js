/**
 * Guardrail Enforcer Tests
 *
 * Tests for the Kublai Self-Awareness Proposal System guardrail.
 * Verifies that only validated+implemented proposals can sync to ARCHITECTURE.md.
 */

const { describe, it, expect, beforeAll, afterAll } = require('@jest/globals');
const neo4j = require('neo4j-driver');
const {
  canSyncToArchitecture,
  syncToArchitecture,
  auditGuardrailViolations,
  GuardrailViolationError
} = require('../../src/workflow/guardrail-enforcer');

describe('Guardrail Enforcer', () => {
  let driver;
  let testProposalId;

  beforeAll(async () => {
    // Connect to test Neo4j instance
    const uri = process.env.NEO4J_URI || 'bolt://localhost:7687';
    const user = process.env.NEO4J_USER || 'neo4j';
    const password = process.env.NEO4J_PASSWORD || 'password';

    driver = neo4j.driver(uri, { auth: { user, password } });

    // Clean up any existing test data
    const session = driver.session();
    try {
      await session.run(`
        MATCH (p:ArchitectureProposal {id: 'test-proposal-guardrail'})
        DETACH DELETE p
      `);
    } finally {
      await session.close();
    }

    // Create test proposal
    testProposalId = 'test-proposal-guardrail';
  });

  afterAll(async () => {
    // Clean up test data
    const session = driver.session();
    try {
      await session.run(`
        MATCH (p:ArchitectureProposal {id: $proposalId})
        DETACH DELETE p
      `, { proposalId: testProposalId });
    } finally {
      await session.close();
    }

    if (driver) {
      await driver.close();
    }
  });

  describe('canSyncToArchitecture', () => {
    it('should return not_allowed for non-existent proposal', async () => {
      const result = await canSyncToArchitecture('non-existent', driver);

      expect(result.allowed).toBe(false);
      expect(result.reason).toContain('not found');
    });

    it('should return not_allowed when implementation_status is not completed', async () => {
      const session = driver.session();
      try {
        // Create proposal with incomplete implementation
        await session.run(`
          CREATE (p:ArchitectureProposal {
            id: $proposalId,
            status: 'approved',
            implementation_status: 'in_progress'
          })
        `, { proposalId: testProposalId });

        const result = await canSyncToArchitecture(testProposalId, driver);

        expect(result.allowed).toBe(false);
        expect(result.reason).toContain('Implementation not complete');
        expect(result.reason).toContain('in_progress');
      } finally {
        await session.close();
      }
    });

    it('should return not_allowed when status is not validated', async () => {
      const session = driver.session();
      try {
        // Update proposal to completed but not validated
        await session.run(`
          MATCH (p:ArchitectureProposal {id: $proposalId})
          SET p.implementation_status = 'completed', p.status = 'implemented'
        `, { proposalId: testProposalId });

        const result = await canSyncToArchitecture(testProposalId, driver);

        expect(result.allowed).toBe(false);
        expect(result.reason).toContain('Proposal not validated');
        expect(result.reason).toContain('implemented');
      } finally {
        await session.close();
      }
    });

    it('should return allowed when proposal is validated+implemented', async () => {
      const session = driver.session();
      try {
        // Create Implementation and Validation nodes
        await session.run(`
          MATCH (p:ArchitectureProposal {id: $proposalId})

          // Create Implementation node
          CREATE (i:Implementation {
            id: randomUUID(),
            proposal_id: $proposalId,
            status: 'completed',
            started_at: datetime()
          })
          CREATE (p)-[:IMPLEMENTED_BY]->(i)

          // Create Validation node (passed)
          CREATE (v:Validation {
            id: randomUUID(),
            implementation_id: i.id,
            passed: true,
            validated_at: datetime()
          })
          CREATE (i)-[:VALIDATED_BY]->(v)

          // Update proposal status
          SET p.status = 'validated'
        `, { proposalId: testProposalId });

        const result = await canSyncToArchitecture(testProposalId, driver);

        expect(result.allowed).toBe(true);
      } finally {
        await session.close();
      }
    });

    it('should return not_allowed when validation did not pass', async () => {
      const session = driver.session();
      try {
        // Update validation to failed
        await session.run(`
          MATCH (p:ArchitectureProposal {id: $proposalId})-[:IMPLEMENTED_BY]->(i:Implementation)-[:VALIDATED_BY]->(v:Validation)
          SET v.passed = false
        `, { proposalId: testProposalId });

        const result = await canSyncToArchitecture(testProposalId, driver);

        expect(result.allowed).toBe(false);
        expect(result.reason).toContain('Validation did not pass');
      } finally {
        await session.close();
      }
    });
  });

  describe('syncToArchitecture', () => {
    it('should create SYNCED_TO relationship when guardrail passes', async () => {
      // Ensure proposal is in valid state
      const session = driver.session();
      try {
        await session.run(`
          MATCH (p:ArchitectureProposal {id: $proposalId})
          SET p.status = 'validated'
        `, { proposalId: testProposalId });

        // Create target section
        await session.run(`
          MERGE (s:ArchitectureSection {title: 'System Overview'})
        `);

        // Execute sync
        const result = await syncToArchitecture(testProposalId, 'System Overview', driver);

        expect(result.success).toBe(true);

        // Verify SYNCED_TO relationship was created
        const verifyResult = await session.run(`
          MATCH (p:ArchitectureProposal {id: $proposalId})-[r:SYNCED_TO]->(s:ArchitectureSection {title: 'System Overview'})
          RETURN r.synced_at as syncedAt, r.guardrail_verified as verified
        `, { proposalId: testProposalId });

        expect(verifyResult.records.length).toBe(1);
        expect(verifyResult.records[0].get('verified')).toBe(true);
      } finally {
        await session.close();
      }
    });

    it('should throw GuardrailViolationError when guardrail fails', async () => {
      const session = driver.session();
      try {
        // Set proposal to invalid state
        await session.run(`
          MATCH (p:ArchitectureProposal {id: $proposalId})
          SET p.status = 'approved', p.implementation_status = 'not_started'
        `, { proposalId: testProposalId });

        // Attempt sync - should throw
        await expect(
          syncToArchitecture(testProposalId, 'System Overview', driver)
        ).rejects.toThrow(GuardrailViolationError);

        await expect(
          syncToArchitecture(testProposalId, 'System Overview', driver)
        ).rejects.toThrow('Guardrail blocked sync');
      } finally {
        await session.close();
      }
    });
  });

  describe('auditGuardrailViolations', () => {
    it('should detect proposals that bypassed the guardrail', async () => {
      const session = driver.session();
      try {
        // Create a violation: proposal with wrong status but SYNCED_TO relationship
        await session.run(`
          CREATE (p:ArchitectureProposal {
            id: 'violation-proposal',
            status: 'approved',
            implementation_status: 'in_progress'
          })
          CREATE (s:ArchitectureSection {title: 'Test Section'})
          CREATE (p)-[:SYNCED_TO {synced_at: datetime()}]->(s)
        `);

        const violations = await auditGuardrailViolations(driver);

        expect(violations.length).toBeGreaterThan(0);
        expect(violations[0].proposalId).toBe('violation-proposal');

        // Cleanup
        await session.run(`
          MATCH (p:ArchitectureProposal {id: 'violation-proposal'})-[r:SYNCED_TO]->(s)
          DETACH DELETE p, s
        `);
      } finally {
        await session.close();
      }
    });

    it('should return empty array when no violations exist', async () => {
      // All properly synced proposals should not trigger violations
      const violations = await auditGuardrailViolations(driver);

      expect(violations).toEqual([]);
    });
  });
});
