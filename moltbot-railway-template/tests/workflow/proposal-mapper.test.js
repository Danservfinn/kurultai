/**
 * Proposal Mapper Tests
 *
 * Tests for the proposal-to-architecture mapper.
 * Verifies section mapping, guardrail checks, and sync readiness.
 */

const { describe, it, expect, beforeAll, afterAll, jest } = require('@jest/globals');
const neo4j = require('neo4j-driver');
const { ProposalMapper } = require('../../src/workflow/proposal-mapper');

describe('Proposal Mapper', () => {
  let driver;
  let mapper;
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
    mapper = new ProposalMapper(driver, mockLogger);

    // Clean up any existing test data
    const session = driver.session();
    try {
      await session.run(`
        MATCH (p:ArchitectureProposal)
        WHERE p.title STARTS WITH 'Test-'
        DETACH DELETE p
      `);
      await session.run(`
        MATCH (s:ArchitectureSection)
        WHERE s.title STARTS WITH 'Test-'
        DETACH DELETE s
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
        MATCH (s:ArchitectureSection)
        WHERE s.title STARTS WITH 'Test-'
        DETACH DELETE s
      `);
    } finally {
      await session.close();
    }

    if (driver) {
      await driver.close();
    }
  });

  describe('mapProposalToSection', () => {
    it('should map proposal to target section', async () => {
      const session = driver.session();
      let proposalId;
      try {
        // Create proposal
        const result = await session.run(`
          CREATE (p:ArchitectureProposal {
            id: randomUUID(),
            title: 'Test- API Documentation Update',
            description: 'Add new endpoints',
            category: 'api'
          })
          RETURN p.id as id
        `);
        proposalId = result.records[0].get('id');

        const mapResult = await mapper.mapProposalToSection(proposalId);

        expect(mapResult.success).toBe(true);
        expect(mapResult.proposalId).toBe(proposalId);
        expect(mapResult.targetSection).toBeDefined();

        // Verify mapping was stored
        const verifyResult = await session.run(`
          MATCH (p:ArchitectureProposal {id: $id})
          RETURN p.target_section as targetSection
        `, { id: proposalId });

        expect(verifyResult.records[0].get('targetSection')).toBe(mapResult.targetSection);
      } finally {
        await session.close();
      }
    });

    it('should use existing target_section if set', async () => {
      const session = driver.session();
      let proposalId;
      try {
        const result = await session.run(`
          CREATE (p:ArchitectureProposal {
            id: randomUUID(),
            title: 'Test- Custom Section',
            description: 'Test',
            target_section: 'Custom Section'
          })
          RETURN p.id as id
        `);
        proposalId = result.records[0].get('id');

        const mapResult = await mapper.mapProposalToSection(proposalId);

        expect(mapResult.success).toBe(true);
        expect(mapResult.targetSection).toBe('Custom Section');
      } finally {
        await session.close();
      }
    });

    it('should return error for non-existent proposal', async () => {
      const result = await mapper.mapProposalToSection('non-existent-id');

      expect(result.success).toBe(false);
      expect(result.error).toBe('Proposal not found');
    });

    it('should handle errors gracefully', async () => {
      const badDriver = {
        session: () => ({
          run: () => { throw new Error('Database error'); },
          close: jest.fn()
        })
      };
      const badMapper = new ProposalMapper(badDriver, mockLogger);

      const result = await badMapper.mapProposalToSection('test-id');

      expect(result.success).toBe(false);
      expect(result.error).toBeDefined();
      expect(mockLogger.error).toHaveBeenCalled();
    });
  });

  describe('determineSection', () => {
    it('should map API-related proposals to API Routes', () => {
      const proposal = {
        title: 'Add REST endpoints',
        description: 'New HTTP API routes'
      };

      const section = mapper.determineSection(proposal);

      expect(section).toBe('API Routes');
    });

    it('should map database-related proposals to Data Model', () => {
      const proposal = {
        title: 'Update Neo4j schema',
        description: 'New graph data model'
      };

      const section = mapper.determineSection(proposal);

      expect(section).toBe('Data Model');
    });

    it('should map security-related proposals to Security Architecture', () => {
      const proposal = {
        title: 'Add authentication',
        description: 'OAuth token authorization'
      };

      const section = mapper.determineSection(proposal);

      expect(section).toBe('Security Architecture');
    });

    it('should map deployment-related proposals to Deployment', () => {
      const proposal = {
        title: 'Docker configuration',
        description: 'Railway infrastructure deploy'
      };

      const section = mapper.determineSection(proposal);

      expect(section).toBe('Deployment');
    });

    it('should map agent-related proposals to Agent Coordination', () => {
      const proposal = {
        title: 'OpenClaw gateway',
        description: 'Message coordination between agents'
      };

      const section = mapper.determineSection(proposal);

      expect(section).toBe('Agent Coordination');
    });

    it('should map memory-related proposals to Operational Memory', () => {
      const proposal = {
        title: 'Neo4j operational context',
        description: 'Memory storage system'
      };

      const section = mapper.determineSection(proposal);

      expect(section).toBe('Operational Memory');
    });

    it('should map frontend-related proposals to Frontend', () => {
      const proposal = {
        title: 'React UI components',
        description: 'Web interface design'
      };

      const section = mapper.determineSection(proposal);

      expect(section).toBe('Frontend');
    });

    it('should map monitoring-related proposals to Monitoring', () => {
      const proposal = {
        title: 'Health metrics',
        description: 'Observability and logging'
      };

      const section = mapper.determineSection(proposal);

      expect(section).toBe('Monitoring');
    });

    it('should default to System Overview for unmatched proposals', () => {
      const proposal = {
        title: 'General improvements',
        description: 'Various updates'
      };

      const section = mapper.determineSection(proposal);

      expect(section).toBe('System Overview');
    });

    it('should handle empty/null proposal fields', () => {
      expect(mapper.determineSection({})).toBe('System Overview');
      expect(mapper.determineSection({ title: null, description: null })).toBe('System Overview');
      expect(mapper.determineSection({ title: '', description: '' })).toBe('System Overview');
    });
  });

  describe('checkCanSync', () => {
    it('should allow sync for validated proposals with validated implementation', async () => {
      const session = driver.session();
      let proposalId;
      try {
        const result = await session.run(`
          CREATE (p:ArchitectureProposal {
            id: randomUUID(),
            title: 'Test- Ready to Sync',
            description: 'Test',
            status: 'validated',
            implementation_status: 'validated'
          })
          RETURN p.id as id
        `);
        proposalId = result.records[0].get('id');

        const checkResult = await mapper.checkCanSync(proposalId);

        expect(checkResult.allowed).toBe(true);
        expect(checkResult.title).toBe('Test- Ready to Sync');
      } finally {
        await session.close();
      }
    });

    it('should block sync for non-validated proposals', async () => {
      const session = driver.session();
      let proposalId;
      try {
        const result = await session.run(`
          CREATE (p:ArchitectureProposal {
            id: randomUUID(),
            title: 'Test- Not Validated',
            description: 'Test',
            status: 'implemented',
            implementation_status: 'completed'
          })
          RETURN p.id as id
        `);
        proposalId = result.records[0].get('id');

        const checkResult = await mapper.checkCanSync(proposalId);

        expect(checkResult.allowed).toBe(false);
        expect(checkResult.reason).toContain('Guardrail');
        expect(checkResult.reason).toContain('validated');
      } finally {
        await session.close();
      }
    });

    it('should block sync for non-validated implementation', async () => {
      const session = driver.session();
      let proposalId;
      try {
        const result = await session.run(`
          CREATE (p:ArchitectureProposal {
            id: randomUUID(),
            title: 'Test- Impl Not Validated',
            description: 'Test',
            status: 'validated',
            implementation_status: 'completed'
          })
          RETURN p.id as id
        `);
        proposalId = result.records[0].get('id');

        const checkResult = await mapper.checkCanSync(proposalId);

        expect(checkResult.allowed).toBe(false);
        expect(checkResult.reason).toContain('Guardrail');
      } finally {
        await session.close();
      }
    });

    it('should return not found for non-existent proposal', async () => {
      const result = await mapper.checkCanSync('non-existent-id');

      expect(result.allowed).toBe(false);
      expect(result.reason).toBe('Proposal not found');
    });

    it('should handle errors gracefully', async () => {
      const badDriver = {
        session: () => ({
          run: () => { throw new Error('Query failed'); },
          close: jest.fn()
        })
      };
      const badMapper = new ProposalMapper(badDriver, mockLogger);

      const result = await badMapper.checkCanSync('test-id');

      expect(result.allowed).toBe(false);
      expect(result.reason).toContain('Error');
      expect(mockLogger.error).toHaveBeenCalled();
    });
  });

  describe('markSynced', () => {
    it('should mark proposal as synced when guardrail passes', async () => {
      const session = driver.session();
      let proposalId;
      try {
        const result = await session.run(`
          CREATE (p:ArchitectureProposal {
            id: randomUUID(),
            title: 'Test- Mark Synced',
            description: 'Test',
            status: 'validated',
            implementation_status: 'validated'
          })
          RETURN p.id as id
        `);
        proposalId = result.records[0].get('id');

        const syncResult = await mapper.markSynced(proposalId, 'Test- Architecture Section');

        expect(syncResult.success).toBe(true);

        // Verify relationship was created
        const verifyResult = await session.run(`
          MATCH (p:ArchitectureProposal {id: $id})-[r:SYNCED_TO]->(s:ArchitectureSection {title: 'Test- Architecture Section'})
          RETURN r.synced_at as syncedAt, p.status as status
        `, { id: proposalId });

        expect(verifyResult.records.length).toBe(1);
        expect(verifyResult.records[0].get('status')).toBe('synced');
        expect(verifyResult.records[0].get('syncedAt')).toBeDefined();
      } finally {
        await session.close();
      }
    });

    it('should block sync when guardrail fails', async () => {
      const session = driver.session();
      let proposalId;
      try {
        const result = await session.run(`
          CREATE (p:ArchitectureProposal {
            id: randomUUID(),
            title: 'Test- Guardrail Block',
            description: 'Test',
            status: 'proposed',
            implementation_status: 'not_started'
          })
          RETURN p.id as id
        `);
        proposalId = result.records[0].get('id');

        const syncResult = await mapper.markSynced(proposalId, 'Test- Section');

        expect(syncResult.success).toBe(false);
        expect(syncResult.reason).toContain('Guardrail');
        expect(mockLogger.warn).toHaveBeenCalled();
      } finally {
        await session.close();
      }
    });

    it('should handle errors gracefully', async () => {
      const badDriver = {
        session: () => ({
          run: () => { throw new Error('Update failed'); },
          close: jest.fn()
        })
      };
      const badMapper = new ProposalMapper(badDriver, mockLogger);

      const result = await badMapper.markSynced('test-id', 'Test Section');

      expect(result.success).toBe(false);
      expect(result.error).toBeDefined();
      expect(mockLogger.error).toHaveBeenCalled();
    });
  });

  describe('getReadyToSync', () => {
    beforeAll(async () => {
      const session = driver.session();
      try {
        // Create validated proposals (ready to sync)
        await session.run(`
          CREATE (p1:ArchitectureProposal {
            id: 'test-ready-1',
            title: 'Test- Ready One',
            description: 'Test',
            status: 'validated',
            implementation_status: 'validated',
            proposed_at: datetime()
          })
          CREATE (p2:ArchitectureProposal {
            id: 'test-ready-2',
            title: 'Test- Ready Two',
            description: 'Test',
            status: 'validated',
            implementation_status: 'validated',
            proposed_at: datetime()
          })
        `);

        // Create already synced proposal
        await session.run(`
          CREATE (p:ArchitectureProposal {
            id: 'test-already-synced',
            title: 'Test- Already Synced',
            description: 'Test',
            status: 'synced',
            implementation_status: 'validated',
            proposed_at: datetime()
          })
          CREATE (s:ArchitectureSection {title: 'Test- Synced Section'})
          CREATE (p)-[:SYNCED_TO {synced_at: datetime()}]->(s)
        `);
      } finally {
        await session.close();
      }
    });

    it('should return validated proposals not yet synced', async () => {
      const ready = await mapper.getReadyToSync();

      expect(ready.length).toBeGreaterThanOrEqual(2);
      expect(ready.some(p => p.id === 'test-ready-1')).toBe(true);
      expect(ready.some(p => p.id === 'test-ready-2')).toBe(true);
    });

    it('should not include already synced proposals', async () => {
      const ready = await mapper.getReadyToSync();

      expect(ready.some(p => p.id === 'test-already-synced')).toBe(false);
    });

    it('should return empty array when no proposals ready', async () => {
      // Clean all test proposals
      const session = driver.session();
      try {
        await session.run(`
          MATCH (p:ArchitectureProposal)
          WHERE p.id STARTS WITH 'test-ready-'
          DETACH DELETE p
        `);

        const ready = await mapper.getReadyToSync();

        // Should not include our test proposals anymore
        expect(ready.some(p => p.id === 'test-ready-1')).toBe(false);
        expect(ready.some(p => p.id === 'test-ready-2')).toBe(false);
      } finally {
        await session.close();
      }
    });

    it('should handle errors gracefully', async () => {
      const badDriver = {
        session: () => ({
          run: () => { throw new Error('Query failed'); },
          close: jest.fn()
        })
      };
      const badMapper = new ProposalMapper(badDriver, mockLogger);

      const result = await badMapper.getReadyToSync();

      expect(result).toEqual([]);
      expect(mockLogger.error).toHaveBeenCalled();
    });
  });
});
