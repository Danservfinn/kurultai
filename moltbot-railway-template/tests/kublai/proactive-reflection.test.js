/**
 * Proactive Reflection Tests
 *
 * Tests for the Kublai Proactive Reflection module.
 * Verifies self-reflection on system architecture and opportunity identification.
 */

const { describe, it, expect, beforeAll, afterAll, beforeEach, jest } = require('@jest/globals');
const neo4j = require('neo4j-driver');
const { ProactiveReflection } = require('../../src/kublai/proactive-reflection');

describe('Proactive Reflection', () => {
  let driver;
  let introspection;
  let reflection;
  const mockLogger = {
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn()
  };

  // Mock introspection
  const mockIntrospection = {
    getArchitectureOverview: jest.fn()
  };

  beforeAll(async () => {
    // Connect to test Neo4j instance
    const uri = process.env.NEO4J_URI || 'bolt://localhost:7687';
    const user = process.env.NEO4J_USER || 'neo4j';
    const password = process.env.NEO4J_PASSWORD || 'password';

    driver = neo4j.driver(uri, { auth: { user, password } });
    reflection = new ProactiveReflection(driver, mockIntrospection, mockLogger);

    // Clean up any existing test data
    const session = driver.session();
    try {
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

  describe('triggerReflection', () => {
    it('should trigger reflection and return results', async () => {
      mockIntrospection.getArchitectureOverview.mockResolvedValue({
        totalSections: 5,
        sections: [
          { title: 'System Architecture', position: 1, parent: null },
          { title: 'API Routes', position: 2, parent: 'System Architecture' },
          { title: 'Data Model', position: 3, parent: 'System Architecture' }
        ],
        lastSync: new Date().toISOString()
      });

      const result = await reflection.triggerReflection();

      expect(result.sectionsKnown).toBe(5);
      expect(result.opportunitiesFound).toBeGreaterThanOrEqual(0);
      expect(Array.isArray(result.opportunities)).toBe(true);
      expect(mockLogger.info).toHaveBeenCalledWith(
        '[Kublai] Triggering proactive architecture reflection...'
      );
    });

    it('should store opportunities when found', async () => {
      mockIntrospection.getArchitectureOverview.mockResolvedValue({
        totalSections: 0,
        sections: [],
        lastSync: null
      });

      const result = await reflection.triggerReflection();

      expect(result.sectionsKnown).toBe(0);
      expect(result.opportunitiesFound).toBe(1);
      expect(result.opportunities[0].type).toBe('no_architecture_data');
    });

    it('should handle errors during reflection', async () => {
      mockIntrospection.getArchitectureOverview.mockRejectedValue(
        new Error('Introspection failed')
      );

      await expect(reflection.triggerReflection()).rejects.toThrow('Introspection failed');
    });
  });

  describe('analyzeForOpportunities', () => {
    it('should detect missing architecture data', async () => {
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
          { title: 'Introduction', position: 1 },
          { title: 'Getting Started', position: 2 }
        ],
        lastSync: new Date().toISOString()
      };

      const opportunities = await reflection.analyzeForOpportunities(overview);

      // Should detect missing sections like security, deployment, etc.
      expect(opportunities.length).toBeGreaterThan(0);
      expect(opportunities.some(o => o.type === 'missing_section')).toBe(true);
    });

    it('should detect stale sync data', async () => {
      const tenDaysAgo = new Date();
      tenDaysAgo.setDate(tenDaysAgo.getDate() - 10);

      const overview = {
        totalSections: 5,
        sections: [
          { title: 'System Architecture', position: 1 },
          { title: 'API Routes', position: 2 },
          { title: 'Data Model', position: 3 },
          { title: 'Security', position: 4 },
          { title: 'Deployment', position: 5 }
        ],
        lastSync: tenDaysAgo.toISOString()
      };

      const opportunities = await reflection.analyzeForOpportunities(overview);

      expect(opportunities.some(o => o.type === 'stale_sync')).toBe(true);
      expect(opportunities.find(o => o.type === 'stale_sync').priority).toBe('low');
    });

    it('should return empty array when all sections present', async () => {
      const overview = {
        totalSections: 6,
        sections: [
          { title: 'System Architecture Overview', position: 1 },
          { title: 'API Routes and Endpoints', position: 2 },
          { title: 'Data Model Schema', position: 3 },
          { title: 'Security and Authentication', position: 4 },
          { title: 'Deployment Infrastructure', position: 5 },
          { title: 'Agent Coordination Gateway', position: 6 }
        ],
        lastSync: new Date().toISOString()
      };

      const opportunities = await reflection.analyzeForOpportunities(overview);

      // Should not detect missing sections when all present
      expect(opportunities.filter(o => o.type === 'missing_section').length).toBe(0);
    });

    it('should handle null/undefined overview', async () => {
      const opportunities = await reflection.analyzeForOpportunities(null);

      expect(opportunities.length).toBe(1);
      expect(opportunities[0].type).toBe('no_architecture_data');
    });
  });

  describe('storeOpportunities', () => {
    it('should store opportunities in Neo4j', async () => {
      const opportunities = [
        {
          type: 'missing_section',
          description: 'Test- Missing security section',
          priority: 'high',
          suggestedSection: 'Security Architecture'
        },
        {
          type: 'stale_sync',
          description: 'Test- Architecture data is stale',
          priority: 'low'
        }
      ];

      await reflection.storeOpportunities(opportunities);

      // Verify opportunities were stored
      const session = driver.session();
      try {
        const result = await session.run(`
          MATCH (o:ImprovementOpportunity)
          WHERE o.description CONTAINS 'Test-'
          RETURN count(o) as count
        `);

        expect(result.records[0].get('count').toNumber()).toBe(2);
      } finally {
        await session.close();
      }

      expect(mockLogger.info).toHaveBeenCalledWith('[Kublai] Stored 2 improvement opportunities');
    });

    it('should handle empty opportunities array', async () => {
      await reflection.storeOpportunities([]);

      // Should not throw or log error
      expect(mockLogger.error).not.toHaveBeenCalled();
    });

    it('should handle Neo4j errors gracefully', async () => {
      const badDriver = {
        session: () => ({
          run: () => { throw new Error('Write failed'); },
          close: jest.fn()
        })
      };
      const badReflection = new ProactiveReflection(badDriver, mockIntrospection, mockLogger);

      await badReflection.storeOpportunities([{
        type: 'test',
        description: 'Test opportunity',
        priority: 'medium'
      }]);

      expect(mockLogger.error).toHaveBeenCalled();
    });
  });

  describe('getOpportunities', () => {
    beforeEach(async () => {
      // Clean and create test opportunities
      const session = driver.session();
      try {
        await session.run(`
          MATCH (o:ImprovementOpportunity)
          WHERE o.description CONTAINS 'Test-'
          DETACH DELETE o
        `);

        await session.run(`
          CREATE (o1:ImprovementOpportunity {
            id: 'test-opp-1',
            type: 'missing_section',
            description: 'Test- High priority opportunity',
            priority: 'high',
            status: 'proposed',
            created_at: datetime(),
            last_seen: datetime()
          })
          CREATE (o2:ImprovementOpportunity {
            id: 'test-opp-2',
            type: 'stale_sync',
            description: 'Test- Low priority opportunity',
            priority: 'low',
            status: 'proposed',
            created_at: datetime(),
            last_seen: datetime()
          })
          CREATE (o3:ImprovementOpportunity {
            id: 'test-opp-3',
            type: 'missing_section',
            description: 'Test- Addressed opportunity',
            priority: 'medium',
            status: 'addressed',
            created_at: datetime(),
            last_seen: datetime()
          })
        `);
      } finally {
        await session.close();
      }
    });

    it('should return opportunities filtered by status', async () => {
      const opportunities = await reflection.getOpportunities('proposed');

      expect(opportunities.length).toBe(2);
      expect(opportunities.every(o => o.status === 'proposed')).toBe(true);
    });

    it('should return empty array when no opportunities match', async () => {
      const opportunities = await reflection.getOpportunities('nonexistent_status');

      expect(opportunities).toEqual([]);
    });

    it('should sort by priority and creation date', async () => {
      const opportunities = await reflection.getOpportunities('proposed');

      // High priority should come first
      expect(opportunities[0].priority).toBe('high');
    });

    it('should handle errors gracefully', async () => {
      const badDriver = {
        session: () => ({
          run: () => { throw new Error('Query failed'); },
          close: jest.fn()
        })
      };
      const badReflection = new ProactiveReflection(badDriver, mockIntrospection, mockLogger);

      const result = await badReflection.getOpportunities('proposed');

      expect(result).toEqual([]);
      expect(mockLogger.error).toHaveBeenCalled();
    });
  });

  describe('markOpportunityAddressed', () => {
    it('should mark opportunity as addressed', async () => {
      const session = driver.session();
      try {
        // Create test opportunity
        await session.run(`
          CREATE (o:ImprovementOpportunity {
            id: 'test-mark-addressed',
            type: 'test',
            description: 'Test- Mark addressed test',
            status: 'proposed'
          })
        `);

        const result = await reflection.markOpportunityAddressed('test-mark-addressed');

        expect(result.success).toBe(true);

        // Verify status was updated
        const verifyResult = await session.run(`
          MATCH (o:ImprovementOpportunity {id: 'test-mark-addressed'})
          RETURN o.status as status
        `);

        expect(verifyResult.records[0].get('status')).toBe('addressed');
      } finally {
        await session.close();
      }
    });

    it('should handle non-existent opportunity', async () => {
      const result = await reflection.markOpportunityAddressed('non-existent-id');

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
      const badReflection = new ProactiveReflection(badDriver, mockIntrospection, mockLogger);

      const result = await badReflection.markOpportunityAddressed('test-id');

      expect(result.success).toBe(false);
      expect(result.error).toBeDefined();
      expect(mockLogger.error).toHaveBeenCalled();
    });
  });
});
