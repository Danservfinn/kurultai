/**
 * Proposal State Machine Tests
 *
 * Tests for the proposal state machine managing architecture proposal lifecycle.
 * Verifies state transitions, validation, and proposal management.
 */

const { describe, it, expect, beforeAll, afterAll } = require('@jest/globals');
const neo4j = require('neo4j-driver');
const {
  ProposalStateMachine,
  proposalStates,
  implementationStates
} = require('../../src/workflow/proposal-states');

describe('Proposal State Machine', () => {
  let driver;
  let stateMachine;
  const mockLogger = {
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn()
  };

  beforeAll(async () => {
    // Connect to test Neo4j instance
    const uri = process.env.NEO4J_URI || 'bolt://localhost:7687';
    const user = process.env.NEO4J_USER || 'neo4j';
    const password = process.env.NEO4J_PASSWORD || 'password';

    driver = neo4j.driver(uri, { auth: { user, password } });
    stateMachine = new ProposalStateMachine(driver, mockLogger);

    // Clean up any existing test data
    const session = driver.session();
    try {
      await session.run(`
        MATCH (p:ArchitectureProposal)
        WHERE p.title STARTS WITH 'Test-'
        DETACH DELETE p
      `);
      await session.run(`
        MATCH (o:ImprovementOpportunity)
        WHERE o.description CONTAINS 'Test-'
        DETACH DELETE o
      `);
    } finally {
      await session.close();
    }
  });

  afterAll(async () => {
    // Clean up test data
    const session = driver.session();
    try {
      await session.run(`
        MATCH (p:ArchitectureProposal)
        WHERE p.title STARTS WITH 'Test-'
        DETACH DELETE p
      `);
      await session.run(`
        MATCH (o:ImprovementOpportunity)
        WHERE o.description CONTAINS 'Test-'
        DETACH DELETE o
      `);
    } finally {
      await session.close();
    }

    if (driver) {
      await driver.close();
    }
  });

  describe('proposalStates constants', () => {
    it('should define all expected states', () => {
      expect(proposalStates.PROPOSED).toBe('proposed');
      expect(proposalStates.UNDER_REVIEW).toBe('under_review');
      expect(proposalStates.APPROVED).toBe('approved');
      expect(proposalStates.REJECTED).toBe('rejected');
      expect(proposalStates.IMPLEMENTED).toBe('implemented');
      expect(proposalStates.VALIDATED).toBe('validated');
      expect(proposalStates.SYNCED).toBe('synced');
    });
  });

  describe('implementationStates constants', () => {
    it('should define all expected implementation states', () => {
      expect(implementationStates.NOT_STARTED).toBe('not_started');
      expect(implementationStates.IN_PROGRESS).toBe('in_progress');
      expect(implementationStates.COMPLETED).toBe('completed');
      expect(implementationStates.VALIDATED).toBe('validated');
      expect(implementationStates.FAILED).toBe('failed');
    });
  });

  describe('createProposal', () => {
    it('should create a new proposal with default values', async () => {
      const result = await stateMachine.createProposal(
        null,
        'Test- New Proposal',
        'Test description for new proposal'
      );

      expect(result.proposalId).toBeDefined();
      expect(result.status).toBe('proposed');
      expect(mockLogger.info).toHaveBeenCalledWith(
        expect.stringContaining('[Proposal] Created:')
      );

      // Verify in database
      const session = driver.session();
      try {
        const dbResult = await session.run(`
          MATCH (p:ArchitectureProposal {id: $id})
          RETURN p.title as title, p.status as status, p.implementation_status as implStatus
        `, { id: result.proposalId });

        expect(dbResult.records[0].get('title')).toBe('Test- New Proposal');
        expect(dbResult.records[0].get('status')).toBe('proposed');
        expect(dbResult.records[0].get('implStatus')).toBe('not_started');
      } finally {
        await session.close();
      }
    });

    it('should create proposal linked to opportunity', async () => {
      const session = driver.session();
      let oppId;
      try {
        // Create opportunity
        const oppResult = await session.run(`
          CREATE (o:ImprovementOpportunity {
            id: randomUUID(),
            type: 'missing_section',
            description: 'Test- Opportunity for proposal'
          })
          RETURN o.id as id
        `);
        oppId = oppResult.records[0].get('id');

        const result = await stateMachine.createProposal(
          oppId,
          'Test- Proposal From Opportunity',
          'Test description'
        );

        // Verify relationship
        const relResult = await session.run(`
          MATCH (o:ImprovementOpportunity {id: $oppId})-[:EVOLVES_INTO]->(p:ArchitectureProposal {id: $propId})
          RETURN count(*) as count
        `, { oppId, propId: result.proposalId });

        expect(relResult.records[0].get('count').toNumber()).toBe(1);
      } finally {
        await session.close();
      }
    });

    it('should create proposal with category', async () => {
      const result = await stateMachine.createProposal(
        null,
        'Test- Categorized Proposal',
        'Test description',
        'security'
      );

      const session = driver.session();
      try {
        const dbResult = await session.run(`
          MATCH (p:ArchitectureProposal {id: $id})
          RETURN p.category as category
        `, { id: result.proposalId });

        expect(dbResult.records[0].get('category')).toBe('security');
      } finally {
        await session.close();
      }
    });

    it('should throw error on Neo4j failure', async () => {
      const badDriver = {
        session: () => ({
          run: () => { throw new Error('Database error'); },
          close: jest.fn()
        })
      };
      const badStateMachine = new ProposalStateMachine(badDriver, mockLogger);

      await expect(
        badStateMachine.createProposal(null, 'Test- Bad Proposal', 'Description')
      ).rejects.toThrow('Database error');
    });
  });

  describe('transition', () => {
    let testProposalId;

    beforeEach(async () => {
      // Create a fresh proposal for transition tests
      const result = await stateMachine.createProposal(
        null,
        'Test- Transition Proposal',
        'Test description'
      );
      testProposalId = result.proposalId;
    });

    it('should transition from proposed to under_review', async () => {
      const result = await stateMachine.transition(
        testProposalId,
        'under_review',
        'Starting review'
      );

      expect(result.success).toBe(true);
      expect(result.newState).toBe('under_review');
      expect(result.previousState).toBe('proposed');
    });

    it('should transition from under_review to approved', async () => {
      await stateMachine.transition(testProposalId, 'under_review', 'Starting review');

      const result = await stateMachine.transition(
        testProposalId,
        'approved',
        'Review complete'
      );

      expect(result.success).toBe(true);
      expect(result.newState).toBe('approved');
    });

    it('should transition from approved to implemented', async () => {
      await stateMachine.transition(testProposalId, 'under_review', '');
      await stateMachine.transition(testProposalId, 'approved', '');

      const result = await stateMachine.transition(
        testProposalId,
        'implemented',
        'Implementation started'
      );

      expect(result.success).toBe(true);
      expect(result.newState).toBe('implemented');
    });

    it('should transition from implemented to validated', async () => {
      await stateMachine.transition(testProposalId, 'under_review', '');
      await stateMachine.transition(testProposalId, 'approved', '');
      await stateMachine.transition(testProposalId, 'implemented', '');

      const result = await stateMachine.transition(
        testProposalId,
        'validated',
        'Validation passed'
      );

      expect(result.success).toBe(true);
      expect(result.newState).toBe('validated');
    });

    it('should transition from validated to synced', async () => {
      await stateMachine.transition(testProposalId, 'under_review', '');
      await stateMachine.transition(testProposalId, 'approved', '');
      await stateMachine.transition(testProposalId, 'implemented', '');
      await stateMachine.transition(testProposalId, 'validated', '');

      const result = await stateMachine.transition(
        testProposalId,
        'synced',
        'Synced to architecture'
      );

      expect(result.success).toBe(true);
      expect(result.newState).toBe('synced');
    });

    it('should reject invalid transitions', async () => {
      // Cannot go from proposed directly to validated
      const result = await stateMachine.transition(
        testProposalId,
        'validated',
        'Trying to skip'
      );

      expect(result.success).toBe(false);
      expect(result.error).toContain('Invalid transition');
    });

    it('should return error for non-existent proposal', async () => {
      const result = await stateMachine.transition(
        'non-existent-id',
        'under_review',
        ''
      );

      expect(result.success).toBe(false);
      expect(result.error).toBe('Proposal not found');
    });

    it('should store metadata with transition', async () => {
      await stateMachine.transition(testProposalId, 'under_review', '');

      const metadata = { reviewer: 'test-user', notes: 'Looks good' };
      await stateMachine.transition(
        testProposalId,
        'approved',
        'Approved with metadata',
        metadata
      );

      const session = driver.session();
      try {
        const result = await session.run(`
          MATCH (p:ArchitectureProposal {id: $id})
          RETURN p.reviewer as reviewer, p.notes as notes
        `, { id: testProposalId });

        expect(result.records[0].get('reviewer')).toBe('test-user');
        expect(result.records[0].get('notes')).toBe('Looks good');
      } finally {
        await session.close();
      }
    });
  });

  describe('canTransition', () => {
    it('should allow valid transitions', () => {
      expect(stateMachine.canTransition('proposed', 'under_review')).toBe(true);
      expect(stateMachine.canTransition('proposed', 'rejected')).toBe(true);
      expect(stateMachine.canTransition('under_review', 'approved')).toBe(true);
      expect(stateMachine.canTransition('under_review', 'rejected')).toBe(true);
      expect(stateMachine.canTransition('approved', 'implemented')).toBe(true);
      expect(stateMachine.canTransition('implemented', 'validated')).toBe(true);
      expect(stateMachine.canTransition('validated', 'synced')).toBe(true);
    });

    it('should reject invalid transitions', () => {
      expect(stateMachine.canTransition('proposed', 'approved')).toBe(false);
      expect(stateMachine.canTransition('proposed', 'implemented')).toBe(false);
      expect(stateMachine.canTransition('proposed', 'synced')).toBe(false);
      expect(stateMachine.canTransition('rejected', 'under_review')).toBe(false);
      expect(stateMachine.canTransition('synced', 'proposed')).toBe(false);
    });

    it('should handle unknown states', () => {
      expect(stateMachine.canTransition('unknown', 'proposed')).toBe(false);
      expect(stateMachine.canTransition('proposed', 'unknown')).toBe(false);
    });
  });

  describe('getStatus', () => {
    it('should return status for existing proposal', async () => {
      const createResult = await stateMachine.createProposal(
        null,
        'Test- Status Check',
        'Test description'
      );

      const status = await stateMachine.getStatus(createResult.proposalId);

      expect(status).not.toBeNull();
      expect(status.status).toBe('proposed');
      expect(status.implStatus).toBe('not_started');
      expect(status.title).toBe('Test- Status Check');
    });

    it('should return null for non-existent proposal', async () => {
      const status = await stateMachine.getStatus('non-existent-id');

      expect(status).toBeNull();
    });

    it('should handle errors gracefully', async () => {
      const badDriver = {
        session: () => ({
          run: () => { throw new Error('Query failed'); },
          close: jest.fn()
        })
      };
      const badStateMachine = new ProposalStateMachine(badDriver, mockLogger);

      const status = await badStateMachine.getStatus('test-id');

      expect(status).toBeNull();
      expect(mockLogger.error).toHaveBeenCalled();
    });
  });

  describe('listByStatus', () => {
    beforeAll(async () => {
      // Create proposals in different states
      const session = driver.session();
      try {
        await session.run(`
          CREATE (p1:ArchitectureProposal {
            id: 'test-list-1',
            title: 'Test- Proposed One',
            description: 'Test',
            status: 'proposed',
            priority: 'high',
            proposed_at: datetime(),
            implementation_status: 'not_started'
          })
          CREATE (p2:ArchitectureProposal {
            id: 'test-list-2',
            title: 'Test- Proposed Two',
            description: 'Test',
            status: 'proposed',
            priority: 'low',
            proposed_at: datetime(),
            implementation_status: 'not_started'
          })
          CREATE (p3:ArchitectureProposal {
            id: 'test-list-3',
            title: 'Test- Approved One',
            description: 'Test',
            status: 'approved',
            priority: 'medium',
            proposed_at: datetime(),
            implementation_status: 'not_started'
          })
        `);
      } finally {
        await session.close();
      }
    });

    it('should list proposals by status', async () => {
      const proposals = await stateMachine.listByStatus('proposed');

      expect(proposals.length).toBeGreaterThanOrEqual(2);
      expect(proposals.every(p => p.status === 'proposed' || !p.status)).toBe(true);
    });

    it('should respect limit parameter', async () => {
      const proposals = await stateMachine.listByStatus('proposed', 1);

      expect(proposals.length).toBeLessThanOrEqual(1);
    });

    it('should sort by priority and creation date', async () => {
      const proposals = await stateMachine.listByStatus('proposed');

      if (proposals.length >= 2) {
        // High priority should come before low
        const highPriorityIndex = proposals.findIndex(p => p.priority === 'high');
        const lowPriorityIndex = proposals.findIndex(p => p.priority === 'low');

        if (highPriorityIndex !== -1 && lowPriorityIndex !== -1) {
          expect(highPriorityIndex).toBeLessThan(lowPriorityIndex);
        }
      }
    });

    it('should return empty array for status with no proposals', async () => {
      const proposals = await stateMachine.listByStatus('nonexistent_status_xyz');

      expect(proposals).toEqual([]);
    });

    it('should handle errors gracefully', async () => {
      const badDriver = {
        session: () => ({
          run: () => { throw new Error('Query failed'); },
          close: jest.fn()
        })
      };
      const badStateMachine = new ProposalStateMachine(badDriver, mockLogger);

      const proposals = await badStateMachine.listByStatus('proposed');

      expect(proposals).toEqual([]);
      expect(mockLogger.error).toHaveBeenCalled();
    });
  });

  describe('updateImplementationStatus', () => {
    let testProposalId;

    beforeEach(async () => {
      const result = await stateMachine.createProposal(
        null,
        'Test- Impl Status',
        'Test description'
      );
      testProposalId = result.proposalId;
    });

    it('should update implementation status', async () => {
      const result = await stateMachine.updateImplementationStatus(
        testProposalId,
        'in_progress'
      );

      expect(result.success).toBe(true);

      const session = driver.session();
      try {
        const dbResult = await session.run(`
          MATCH (p:ArchitectureProposal {id: $id})
          RETURN p.implementation_status as implStatus
        `, { id: testProposalId });

        expect(dbResult.records[0].get('implStatus')).toBe('in_progress');
      } finally {
        await session.close();
      }
    });

    it('should update implementation status with progress and notes', async () => {
      // Create implementation node first
      const session = driver.session();
      try {
        await session.run(`
          MATCH (p:ArchitectureProposal {id: $id})
          CREATE (i:Implementation {
            id: randomUUID(),
            proposal_id: $id,
            status: 'in_progress',
            progress: 0
          })
          CREATE (p)-[:IMPLEMENTED_BY]->(i)
        `, { id: testProposalId });
      } finally {
        await session.close();
      }

      const result = await stateMachine.updateImplementationStatus(
        testProposalId,
        'completed',
        100,
        'Implementation complete'
      );

      expect(result.success).toBe(true);

      // Verify implementation record was updated
      const verifySession = driver.session();
      try {
        const dbResult = await verifySession.run(`
          MATCH (i:Implementation {proposal_id: $id})
          RETURN i.progress as progress, i.notes as notes
        `, { id: testProposalId });

        expect(dbResult.records[0].get('progress').toNumber()).toBe(100);
        expect(dbResult.records[0].get('notes')).toBe('Implementation complete');
      } finally {
        await verifySession.close();
      }
    });

    it('should handle non-existent proposal gracefully', async () => {
      const result = await stateMachine.updateImplementationStatus(
        'non-existent-id',
        'completed'
      );

      // Should not throw, but may not update anything
      expect(result.success).toBe(true);
    });

    it('should handle errors gracefully', async () => {
      const badDriver = {
        session: () => ({
          run: () => { throw new Error('Update failed'); },
          close: jest.fn()
        })
      };
      const badStateMachine = new ProposalStateMachine(badDriver, mockLogger);

      const result = await badStateMachine.updateImplementationStatus(
        'test-id',
        'completed'
      );

      expect(result.success).toBe(false);
      expect(result.error).toBeDefined();
      expect(mockLogger.error).toHaveBeenCalled();
    });
  });
});
