/**
 * Proactive Reflection Tests
 *
 * Tests for the Kublai Proactive Reflection module.
 * Verifies periodic self-reflection and opportunity identification.
 */

const { describe, it, expect, beforeAll, afterAll, jest } = require('@jest/globals');
const neo4j = require('neo4j-driver');
const { ProactiveReflection } = require('../../src/kublai/proactive-reflection');

describe('Proactive Reflection', () => {
  let driver;
  let reflection;
  let mockIntrospection;
  const mockLogger = {
    info: jest.fn(),
    error: jest.fn(),
    warn: jest.fn()
  };

  beforeAll(async () => {
    // Connect to test Neo4j instance
    const uri = process.env.NEO4J_URI || 'bolt://localhost:7687';
    const user = process.env.NEO4J_USER || 'neo4j';
    const password = process.env.NEO4J_PASSWORD || 'password';

    driver = neo4j.driver(uri, { auth: { user, password } });

    // Create mock introspection
    mockIntrospection = {
      getArchitectureOverview: jest.fn()
    };

    reflection = new ProactiveReflection(driver, mockIntrospection, mockLogger);

    // Clean up test data
    const session = driver.session();
    try {
      await session.run(`
        MATCH (o:ImprovementOpportunity)
        WHERE o.description CONTAINS 'test-' OR o.proposed_by = 'kublai'
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
        MATCH (o:ImprovementOpportunity)
        WHERE o.description CONTAINS 'test-' OR o.proposed_by = 'kublai'
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

  describe('triggerReflection', () => {
    it('should trigger reflection and return results', async () => {
      mockIntrospection.getArchitectureOverview.mockResolvedValue({
        totalSections: 5,
        sections: [
          { title: 'System Architecture', position: 1, parent: null },
          { title: 'API Routes', position: 2, parent: 'System Architecture' }
        ],
        lastSync: new Date().toISOString()
      });

      const result = await reflection.triggerReflection();

      expect(result.sectionsKnown).toBe(5);
      expect(typeof result.opportunitiesFound).toBe('number');
      expect(Array.isArray(result.opportunities)).toBe(true);
      expect(mockLogger.info).toHaveBeenCalledWith(
        '[Kublai] Triggering proactive architecture reflection...'
      );
    });

    it('should detect missing sections', async () => {
      mockIntrospection.getArchitectureOverview.mockResolvedValue({
        totalSections: 2,
        sections: [
          { title: 'Introduction', position: 1, parent: null }
        ],
        lastSync: new Date().toISOString()
      });

      const result = await reflection.triggerReflection();

      // Should detect missing expected sections
      expect(result.opportunitiesFound).toBeGreaterThan(0);
      expect(result.opportunities.some(o => o.type === 'missing_section')).toBe(true);
    });

    it('should detect stale sync data', async () => {
      const oldDate = new Date();
      oldDate.setDate(oldDate.getDate() - 10); // 10 days ago

      mockIntrospection.getArchitectureOverview.mockResolvedValue({
        totalSections: 5,
        sections: [
          { title: 'System Architecture', position: 1, parent: null },
          { title: 'API Routes', position: 2, parent: null },
          { title: 'Data Model', position: 3, parent: null },
          { title: 'Security', position: 4, parent: null },
          { title: 'Deployment', position: 5, parent: null }
        ],
        lastSync: oldDate.toISOString()
      });

      const result = await reflection.triggerReflection();

      // Should detect stale sync
      expect(result.opportunities.some(o => o.type === 'stale_sync')).toBe(true);
    });

    it('should handle no architecture data', async () => {
      mockIntrospection.getArchitectureOverview.mockResolvedValue({
        totalSections: 0,
        sections: [],
        lastSync: null
      });

      const result = await reflection.triggerReflection();

      expect(result.sectionsKnown).toBe(0);
      expect(result.opportunitiesFound).toBe(1);
      expect(result.opportunities[0].type).toBe('no_architecture_data');
      expect(result.opportunities[0].priority).toBe('critical');
    });
  });

  describe('analyzeForOpportunities', () => {
    it('should return critical opportunity when no architecture data', async () => {
      const overview = {
        totalSections: 0,
        sections: [],
        lastSync: null
      };

      const opportunities = await reflection.analyzeForOpportunities(overview);

      expect(opportunities.length).toBe(1);
      expect(opportunities[0].type).toBe('no_architecture_data');
      expect(opportunities[0].priority).toBe('critical');
    });

    it('should detect missing expected sections', async () => {
      const overview = {
        totalSections: 2,
        sections: [
          { title: 'Introduction', position: 1, parent: null },
          { title: 'Getting Started', position: 2, parent: null }
        ],
        lastSync: new Date().toISOString()
      };

      const opportunities = await reflection.analyzeForOpportunities(overview);

      // Should detect missing sections like API Routes, Data Model, Security, etc.
      const missingSections = opportunities.filter(o => o.type === 'missing_section');
      expect(missingSections.length).toBeGreaterThan(0);
      expect(missingSections[0]).toHaveProperty('suggestedSection');
      expect(missingSections[0]).toHaveProperty('priority', 'medium');
    });

    it('should not flag existing sections as missing', async () => {
      const overview = {
        totalSections: 6,
        sections: [
          { title: 'System Architecture Overview', position: 1, parent: null },
          { title: 'API Routes and Endpoints', position: 2, parent: null },
          { title: 'Data Model Schema', position: 3, parent: null },
          { title: 'Security and Authentication', position: 4, parent: null },
          { title: 'Deployment Infrastructure', position: 5, parent: null },
          { title: 'Agent Coordination Gateway', position: 6, parent: null }
        ],
        lastSync: new Date().toISOString()
      };

      const opportunities = await reflection.analyzeForOpportunities(overview);

      // Should not have missing_section opportunities for existing sections
      const missingSystem = opportunities.find(o =>
        o.type === 'missing_section' && o.suggestedSection === 'system architecture'
      );
      expect(missingSystem).toBeUndefined();
    });

    it('should detect stale sync data older than 7 days', async () => {
      const oldDate = new Date();
      oldDate.setDate(oldDate.getDate() - 8);

      const overview = {
        totalSections: 5,
        sections: [{ title: 'System', position: 1, parent: null }],
        lastSync: oldDate.toISOString()
      };

      const opportunities = await reflection.analyzeForOpportunities(overview);

      const staleOpportunity = opportunities.find(o => o.type === 'stale_sync');
      expect(staleOpportunity).toBeDefined();
      expect(staleOpportunity.priority).toBe('low');
      expect(staleOpportunity.description).toContain('8 days old');
    });

    it('should not flag sync as stale when less than 7 days', async () => {
      const recentDate = new Date();
      recentDate.setDate(recentDate.getDate() - 3);

      const overview = {
        totalSections: 5,
        sections: [{ title: 'System', position: 1, parent: null }],
        lastSync: recentDate.toISOString()
      };

      const opportunities = await reflection.analyzeForOpportunities(overview);

      const staleOpportunity = opportunities.find(o => o.type === 'stale_sync');
      expect(staleOpportunity).toBeUndefined();
    });

    it('should handle null overview gracefully', async () => {
      const opportunities = await reflection.analyzeForOpportunities(null);

      expect(opportunities.length).toBe(1);
      expect(opportunities[0].type).toBe('no_architecture_data');
    });
  });

  describe('storeOpportunities', () => {
    it('should store opportunities in Neo4j', async () => {
      const opportunities = [
        {
          type: 'test-missing-section',
          description: 'test-This is a test opportunity',
          priority: 'high',
          suggestedSection: 'Test Section'
        }
      ];

      await reflection.storeOpportunities(opportunities);

      // Verify stored
      const session = driver.session();
      try {
        const result = await session.run(`
          MATCH (o:ImprovementOpportunity {type: 'test-missing-section'})
          RETURN o
        `);

        expect(result.records.length).toBe(1);
        const record = result.records[0].get('o');
        expect(record.properties.description).toBe('test-This is a test opportunity');
        expect(record.properties.priority).toBe('high');
        expect(record.properties.status).toBe('proposed');
        expect(record.properties.proposed_by).toBe('kublai');
      } finally {
        await session.close();
      }

      expect(mockLogger.info).toHaveBeenCalledWith(
        '[Kublai] Stored 1 improvement opportunities'
      );
    });

    it('should update existing opportunities on merge', async () => {
      const session = driver.session();
      try {
        // Create initial opportunity
        await session.run(`
          CREATE (o:ImprovementOpportunity {
            type: 'test-merge',
            description: 'test-Original description',
            priority: 'low',
            created_at: datetime(),
            status: 'proposed',
            proposed_by: 'kublai'
          })
        `);

        // Store with same type but different priority
        await reflection.storeOpportunities([{
          type: 'test-merge',
          description: 'test-Original description',
          priority: 'critical',
          suggestedSection: null
        }]);

        // Verify updated
        const result = await session.run(`
          MATCH (o:ImprovementOpportunity {type: 'test-merge'})
          RETURN o.priority as priority
        `);

        expect(result.records[0].get('priority')).toBe('critical');
      } finally {
        await session.close();
      }
    });

    it('should handle empty opportunities array', async () => {
      await reflection.storeOpportunities([]);

      // Should not throw or log error
      expect(mockLogger.error).not.toHaveBeenCalled();
    });

    it('should handle Neo4j errors gracefully', async () => {
      const badReflection = new ProactiveReflection(
        { session: () => ({ run: () => { throw new Error('Write failed'); }, close: jest.fn() }) },
        mockIntrospection,
        mockLogger
      );

      await badReflection.storeOpportunities([{
        type: 'test-error',
        description: 'test-opportunity',
        priority: 'medium'
      }]);

      expect(mockLogger.error).toHaveBeenCalledWith(
        expect.stringContaining('[Kublai] Failed to store opportunities')
      );
    });
  });

  describe('getOpportunities', () => {
    it('should return opportunities by status', async () => {
      const session = driver.session();
      try {
        // Create test opportunities
        await session.run(`
          CREATE (o1:ImprovementOpportunity {
            type: 'test-opportunity-1',
            description: 'test-First opportunity',
            priority: 'high',
            status: 'proposed',
            proposed_by: 'kublai',
            created_at: datetime()
          })
          CREATE (o2:ImprovementOpportunity {
            type: 'test-opportunity-2',
            description: 'test-Second opportunity',
            priority: 'low',
            status: 'addressed',
            proposed_by: 'kublai',
            created_at: datetime()
          })
        `);

        const proposed = await reflection.getOpportunities('proposed');
        expect(proposed.some(o => o.description === 'test-First opportunity')).toBe(true);

        const addressed = await reflection.getOpportunities('addressed');
        expect(addressed.some(o => o.description === 'test-Second opportunity')).toBe(true);
      } finally {
        await session.close();
      }
    });

    it('should return empty array when no opportunities exist', async () => {
      const opportunities = await reflection.getOpportunities('nonexistent-status');

      expect(Array.isArray(opportunities)).toBe(true);
      expect(opportunities.length).toBe(0);
    });

    it('should default to proposed status', async () => {
      const session = driver.session();
      try {
        // Create a proposed opportunity
        await session.run(`
          CREATE (o:ImprovementOpportunity {
            type: 'test-default-status',
            description: 'test-Default status opportunity',
            priority: 'medium',
            status: 'proposed',
            proposed_by: 'kublai',
            created_at: datetime()
          })
        `);

        // Call without status parameter
        const opportunities = await reflection.getOpportunities();

        expect(opportunities.some(o => o.type === 'test-default-status')).toBe(true);
      } finally {
        await session.close();
      }
    });

    it('should handle Neo4j errors gracefully', async () => {
      const badReflection = new ProactiveReflection(
        { session: () => ({ run: () => { throw new Error('Read failed'); }, close: jest.fn() }) },
        mockIntrospection,
        mockLogger
      );

      const opportunities = await badReflection.getOpportunities('proposed');

      expect(Array.isArray(opportunities)).toBe(true);
      expect(opportunities.length).toBe(0);
      expect(mockLogger.error).toHaveBeenCalledWith(
        expect.stringContaining('[Kublai] Failed to get opportunities')
      );
    });
  });

  describe('markOpportunityAddressed', () => {
    it('should mark opportunity as addressed', async () => {
      const session = driver.session();
      let opportunityId;
      try {
        // Create opportunity
        const result = await session.run(`
          CREATE (o:ImprovementOpportunity {
            id: randomUUID(),
            type: 'test-address',
            description: 'test-Opportunity to address',
            status: 'proposed',
            proposed_by: 'kublai'
          })
          RETURN o.id as id
        `);
        opportunityId = result.records[0].get('id');

        const markResult = await reflection.markOpportunityAddressed(opportunityId);

        expect(markResult.success).toBe(true);

        // Verify status changed
        const verifyResult = await session.run(`
          MATCH (o:ImprovementOpportunity {id: $id})
          RETURN o.status as status, o.addressed_at as addressedAt
        `, { id: opportunityId });

        expect(verifyResult.records[0].get('status')).toBe('addressed');
        expect(verifyResult.records[0].get('addressedAt')).toBeDefined();
      } finally {
        await session.close();
      }
    });

    it('should return success false when opportunity not found', async () => {
      const result = await reflection.markOpportunityAddressed('non-existent-id');

      // Should not throw, but may not update anything
      expect(result).toHaveProperty('success');
    });

    it('should handle Neo4j errors gracefully', async () => {
      const badReflection = new ProactiveReflection(
        { session: () => ({ run: () => { throw new Error('Update failed'); }, close: jest.fn() }) },
        mockIntrospection,
        mockLogger
      );

      const result = await badReflection.markOpportunityAddressed('any-id');

      expect(result.success).toBe(false);
      expect(result.error).toBeDefined();
      expect(mockLogger.error).toHaveBeenCalledWith(
        expect.stringContaining('[Kublai] Failed to mark opportunity')
      );
    });
  });
});
