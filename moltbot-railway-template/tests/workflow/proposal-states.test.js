/**
 * Proposal State Machine Tests
 *
 * Tests for the proposal state machine managing architecture proposal lifecycles.
 * Verifies state transitions, validation, and proposal management.
 */

const { describe, it, expect, beforeAll, afterAll, jest } = require('@jest/globals');
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
    error: jest.fn(),
    warn: jest.fn()
  };

  beforeAll(async () => {
    const uri = process.env.NEO4J_URI || 'bolt://localhost:7687';
    const user = process.env.NEO4J_USER || 'neo4j';
    const password = process.env.NEO4J_PASSWORD || 'password';

    driver = neo4j.driver(uri, { auth: { user, password } });
    stateMachine = new ProposalStateMachine(driver, mockLogger);

    // Clean up test data
    const session = driver.session();
    try {
      await session.run(`
        MATCH (p:ArchitectureProposal)
        WHERE p.title STARTS WITH 'test-'
        DETACH DELETE p
      `);
      await session.run(`
        MATCH (o:ImprovementOpportunity)
        WHERE o.description CONTAINS 'test-opportunity'
        DETACH DELETE o
      `);
    } finally {
      await session.close();
    }
  });

  afterAll(async () => {
    const session = driver.session();
    try {
      await session.run(`
        MATCH (p:ArchitectureProposal)
        WHERE p.title STARTS WITH 'test-'
        DETACH DELETE p
      `);
      await session.run(`
        MATCH (o:ImprovementOpportunity)
        WHERE o.description CONTAINS 'test-opportunity'
        DETACH DELETE o
      `);
    } finally {
      await session.close();
    }

    if (driver) {
      await driver.close();
    }
  });

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('proposalStates constants', () => {
    it('should define all proposal states', () => {
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
    it('should define all implementation states', () => {
      expect(implementationStates.NOT_STARTED).toBe('not_started');
      expect(implementationStates.IN_PROGRESS).toBe('in_progress');
      expect(implementationStates.COMPLETED).toBe('completed');
      expect(implementationStates.VALIDATED).toBe('validated');
      expect(implementationStates.FAILED).toBe('failed');
    });
  });

  describe('createProposal', () => {
    it('should create a new proposal', async () => {
      const result = await stateMachine.createProposal(
        null,
        'test-New Proposal',
        'Test description',
        'api'
      );

      expect(result.proposalId).toBeDefined();
      expect(result.status).toBe('proposed');
      expect(mockLogger.info).toHaveBeenCalledWith(
        expect.stringContaining('[Proposal] Created:')
      );
    });

    it('should create proposal linked to opportunity', async () => {
      const session = driver.session();
      let opportunityId;
      try {
        // Create opportunity
        const oppResult = await session.run(`
          CREATE (o:ImprovementOpportunity {
            id: randomUUID(),
            type: 'test-opportunity',
            description: 'test-opportunity for linking'
          })
          RETURN o.id as id
        `);
        opportunityId = oppResult.records[0].get('id');

        const result = await stateMachine.createProposal(
          opportunityId,
          'test-Linked Proposal',
          'Linked to opportunity'
        );

        // Verify link
        const linkResult = await session.run(`
          MATCH (o:ImprovementOpportunity {id: $oppId})-[:EVOLVES_INTO]->(p:ArchitectureProposal {id: $propId})
          RETURN count(*) as linkCount
        `, { oppId: opportunityId, propId: result.proposalId });

        expect(linkResult.records[0].get('linkCount').toNumber()).toBe(1);
      } finally {
        await session.close();
      }
    });

    it('should create proposal without opportunity', async () => {
      const result = await stateMachine.createProposal(
        null,
        'test-Standalone Proposal',
        'No opportunity link'
      );

      expect(result.proposalId).toBeDefined();
      expect(result.status).toBe('proposed');
    });

    it('should set default values correctly', async () => {
      const result = await stateMachine.createProposal(
        null,
        'test-Default Values',
        'Checking defaults'
      );

      const session = driver.session();
      try {
        const record = await session.run(`
          MATCH (p:ArchitectureProposal {id: $id})
          RETURN p.status as status, p.implementation_status as implStatus, p.priority as priority
        `, { id: result.proposalId });

        expect(record.records[0].get('status')).toBe('proposed');
        expect(record.records[0].get('implStatus')).toBe('not_started');
        expect(record.records[0].get('priority')).toBe('medium');
      } finally {
        await session.close();
      }
    });

    it('should handle Neo4j errors', async () => {
      const badStateMachine = new ProposalStateMachine(
        { session: () => ({ run: () => { throw new Error('Create failed'); }, close: jest.fn() }) },
        mockLogger
      );

      await expect(
        badStateMachine.createProposal(null, 'test-Fail', 'Will fail')
      ).rejects.toThrow('Create failed');
    });
  });

  describe('transition', () => {
    it('should transition proposal to valid state', async () => {
      const createResult = await stateMachine.createProposal(
        null,
        'test-Transition Proposal',
        'For transition testing'
      );

      const transitionResult = await stateMachine.transition(
        createResult.proposalId,
        'under_review',
        'Starting review'
      );

      expect(transitionResult.success).toBe(true);
      expect(transitionResult.newState).toBe('under_review');
      expect(transitionResult.previousState).toBe('proposed');
    });

    it('should reject invalid transitions', async () => {
      const createResult = await stateMachine.createProposal(
        null,
        'test-Invalid Transition',
        'Testing invalid transition'
      );

      const transitionResult = await stateMachine.transition(
        createResult.proposalId,
        'synced',
        'Trying to skip states'
      );

      expect(transitionResult.success).toBe(false);
      expect(transitionResult.error).toContain('Invalid transition');
    });

    it('should return error for non-existent proposal', async () => {
      const result = await stateMachine.transition(
        'non-existent-id',
        'under_review',
        'Testing'
      );

      expect(result.success).toBe(false);
      expect(result.error).toBe('Proposal not found');
    });

    it('should store metadata on transition', async () => {
      const createResult = await stateMachine.createProposal(
        null,
        'test-Metadata Transition',
        'Testing metadata'
      );

      await stateMachine.transition(
        createResult.proposalId,
        'under_review',
        'Review started',
        { reviewer: 'test-user', priority: 'high' }
      );

      const session = driver.session();
      try {
        const record = await session.run(`
          MATCH (p:ArchitectureProposal {id: $id})
          RETURN p.reviewer as reviewer, p.priority as priority
        `, { id: createResult.proposalId });

        expect(record.records[0].get('reviewer')).toBe('test-user');
        expect(record.records[0].get('priority')).toBe('high');
      } finally {
        await session.close();
      }
    });

    it('should handle state change reason', async () => {
      const createResult = await stateMachine.createProposal(
        null,
        'test-Reason Transition',
        'Testing reason'
      );

      await stateMachine.transition(
        createResult.proposalId,
        'under_review',
        'Code review requested'
      );

      const session = driver.session();
      try {
        const record = await session.run(`
          MATCH (p:ArchitectureProposal {id: $id})
          RETURN p.state_change_reason as reason
        `, { id: createResult.proposalId });

        expect(record.records[0].get('reason')).toBe('Code review requested');
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

    it('should treat rejected as terminal state', () => {
      expect(stateMachine.canTransition('rejected', 'proposed')).toBe(false);
      expect(stateMachine.canTransition('rejected', 'approved')).toBe(false);
      expect(stateMachine.canTransition('rejected', 'any')).toBe(false);
    });

    it('should treat synced as terminal state', () => {
      expect(stateMachine.canTransition('synced', 'proposed')).toBe(false);
      expect(stateMachine.canTransition('synced', 'validated')).toBe(false);
    });
  });

  describe('getStatus', () => {
    it('should return proposal status', async () => {
      const createResult = await stateMachine.createProposal(
        null,
        'test-Get Status',
        'Testing getStatus'
      );

      const status = await stateMachine.getStatus(createResult.proposalId);

      expect(status).not.toBeNull();
      expect(status.status).toBe('proposed');
      expect(status.implStatus).toBe('not_started');
      expect(status.title).toBe('test-Get Status');
    });

    it('should return null for non-existent proposal', async () => {
      const status = await stateMachine.getStatus('non-existent-id');

      expect(status).toBeNull();
    });

    it('should return updated status after transition', async () => {
      const createResult = await stateMachine.createProposal(
        null,
        'test-Updated Status',
        'Testing status update'
      );

      await stateMachine.transition(createResult.proposalId, 'under_review', 'Reviewing');
      await stateMachine.transition(createResult.proposalId, 'approved', 'Approved');

      const status = await stateMachine.getStatus(createResult.proposalId);

      expect(status.status).toBe('approved');
    });

    it('should handle Neo4j errors gracefully', async () => {
      const badStateMachine = new ProposalStateMachine(
        { session: () => ({ run: () => { throw new Error('Read failed'); }, close: jest.fn() }) },
        mockLogger
      );

      const status = await badStateMachine.getStatus('any-id');

      expect(status).toBeNull();
      expect(mockLogger.error).toHaveBeenCalledWith(
        expect.stringContaining('[StateMachine] Failed to get status')
      );
    });
  });

  describe('listByStatus', () => {
    it('should return proposals by status', async () => {
      // Create multiple proposals
      await stateMachine.createProposal(null, 'test-List Proposed 1', 'First');
      await stateMachine.createProposal(null, 'test-List Proposed 2', 'Second');

      const proposals = await stateMachine.listByStatus('proposed', 10);

      expect(Array.isArray(proposals)).toBe(true);
      expect(proposals.some(p => p.title === 'test-List Proposed 1')).toBe(true);
      expect(proposals.some(p => p.title === 'test-List Proposed 2')).toBe(true);
    });

    it('should respect limit parameter', async () => {
      const proposals = await stateMachine.listByStatus('proposed', 1);

      expect(proposals.length).toBeLessThanOrEqual(1);
    });

    it('should return empty array when no proposals exist', async () => {
      const proposals = await stateMachine.listByStatus('nonexistent-status', 10);

      expect(Array.isArray(proposals)).toBe(true);
      expect(proposals.length).toBe(0);
    });

    it('should return proposal details', async () => {
      await stateMachine.createProposal(null, 'test-Details Check', 'Checking fields');

      const proposals = await stateMachine.listByStatus('proposed', 10);
      const proposal = proposals.find(p => p.title === 'test-Details Check');

      expect(proposal).toBeDefined();
      expect(proposal.id).toBeDefined();
      expect(proposal.description).toBe('Checking fields');
      expect(proposal.priority).toBeDefined();
      expect(proposal.implementationStatus).toBeDefined();
    });

    it('should handle Neo4j errors gracefully', async () => {
      const badStateMachine = new ProposalStateMachine(
        { session: () => ({ run: () => { throw new Error('List failed'); }, close: jest.fn() }) },
        mockLogger
      );

      const proposals = await badStateMachine.listByStatus('proposed', 10);

      expect(Array.isArray(proposals)).toBe(true);
      expect(proposals.length).toBe(0);
      expect(mockLogger.error).toHaveBeenCalledWith(
        expect.stringContaining('[StateMachine] Failed to list')
      );
    });
  });

  describe('updateImplementationStatus', () => {
    it('should update implementation status', async () => {
      const createResult = await stateMachine.createProposal(
        null,
        'test-Impl Status',
        'Testing impl status'
      );

      const result = await stateMachine.updateImplementationStatus(
        createResult.proposalId,
        'in_progress'
      );

      expect(result.success).toBe(true);

      const status = await stateMachine.getStatus(createResult.proposalId);
      expect(status.implStatus).toBe('in_progress');
    });

    it('should update implementation record with progress and notes', async () => {
      const createResult = await stateMachine.createProposal(
        null,
        'test-Impl Progress',
        'Testing impl progress'
      );

      // First create implementation node
      const session = driver.session();
      try {
        await session.run(`
          MATCH (p:ArchitectureProposal {id: $id})
          CREATE (i:Implementation {
            id: randomUUID(),
            proposal_id: $id,
            status: 'in_progress'
          })
          CREATE (p)-[:IMPLEMENTED_BY]->(i)
        `, { id: createResult.proposalId });

        await stateMachine.updateImplementationStatus(
          createResult.proposalId,
          'completed',
          75,
          'Work in progress'
        );

        const implResult = await session.run(`
          MATCH (i:Implementation {proposal_id: $id})
          RETURN i.progress as progress, i.notes as notes
        `, { id: createResult.proposalId });

        expect(implResult.records[0].get('progress').toNumber()).toBe(75);
        expect(implResult.records[0].get('notes')).toBe('Work in progress');
      } finally {
        await session.close();
      }
    });

    it('should handle non-existent proposal gracefully', async () => {
      const result = await stateMachine.updateImplementationStatus(
        'non-existent-id',
        'completed'
      );

      // Should not throw, but may not update anything
      expect(result).toHaveProperty('success');
    });

    it('should handle Neo4j errors', async () => {
      const badStateMachine = new ProposalStateMachine(
        { session: () => ({ run: () => { throw new Error('Update failed'); }, close: jest.fn() }) },
        mockLogger
      );

      const result = await badStateMachine.updateImplementationStatus(
        'any-id',
        'completed'
      );

      expect(result.success).toBe(false);
      expect(result.error).toBeDefined();
      expect(mockLogger.error).toHaveBeenCalledWith(
        expect.stringContaining('[StateMachine] Failed to update impl status')
      );
    });
  });
});
