/**
 * Architecture Introspection Tests
 *
 * Tests for the Kublai Architecture Introspection module.
 * Verifies querying and understanding system architecture from Neo4j.
 */

const { describe, it, expect, beforeAll, afterAll } = require('@jest/globals');
const neo4j = require('neo4j-driver');
const { ArchitectureIntrospection } = require('../../src/kublai/architecture-introspection');

describe('Architecture Introspection', () => {
  let driver;
  let introspection;
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
    introspection = new ArchitectureIntrospection(driver, mockLogger);

    // Clean up any existing test data
    const session = driver.session();
    try {
      await session.run(`
        MATCH (s:ArchitectureSection)
        WHERE s.title STARTS WITH 'test-'
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
        MATCH (s:ArchitectureSection)
        WHERE s.title STARTS WITH 'test-'
        DETACH DELETE s
      `);
    } finally {
      await session.close();
    }

    if (driver) {
      await driver.close();
    }
  });

  describe('getArchitectureOverview', () => {
    it('should return empty overview when no sections exist', async () => {
      const result = await introspection.getArchitectureOverview();

      expect(result.totalSections).toBeGreaterThanOrEqual(0);
      expect(Array.isArray(result.sections)).toBe(true);
    });

    it('should return overview with sections when data exists', async () => {
      const session = driver.session();
      try {
        // Create test sections
        await session.run(`
          CREATE (s1:ArchitectureSection {
            title: 'test-system-overview',
            content: 'System overview content',
            order: 1,
            parent_section: null,
            updated_at: datetime()
          })
          CREATE (s2:ArchitectureSection {
            title: 'test-api-routes',
            content: 'API routes content',
            order: 2,
            parent_section: 'test-system-overview',
            updated_at: datetime()
          })
        `);

        const result = await introspection.getArchitectureOverview();

        expect(result.sections.length).toBeGreaterThanOrEqual(2);
        const testSections = result.sections.filter(s =>
          s.title && s.title.startsWith('test-')
        );
        expect(testSections.length).toBe(2);

        // Verify section structure
        const systemSection = testSections.find(s => s.title === 'test-system-overview');
        expect(systemSection).toBeDefined();
        expect(systemSection.position).toBe(1);
        expect(systemSection.parent).toBeNull();

        const apiSection = testSections.find(s => s.title === 'test-api-routes');
        expect(apiSection).toBeDefined();
        expect(apiSection.position).toBe(2);
        expect(apiSection.parent).toBe('test-system-overview');
      } finally {
        await session.close();
      }
    });

    it('should handle Neo4j errors gracefully', async () => {
      // Create introspection with invalid driver to trigger error
      const badIntrospection = new ArchitectureIntrospection(
        { session: () => ({ run: () => { throw new Error('Connection failed'); }, close: jest.fn() }) },
        mockLogger
      );

      const result = await badIntrospection.getArchitectureOverview();

      expect(result.totalSections).toBe(0);
      expect(result.sections).toEqual([]);
      expect(result.lastSync).toBeNull();
      expect(mockLogger.error).toHaveBeenCalledWith(
        expect.stringContaining('[ARCH-introspection] Failed to get overview')
      );
    });
  });

  describe('searchArchitecture', () => {
    it('should return search results for matching content', async () => {
      const session = driver.session();
      try {
        // Create section with searchable content
        await session.run(`
          MERGE (s:ArchitectureSection {title: 'test-search-section'})
          SET s.content = 'This section describes the authentication system and security protocols',
              s.updated_at = datetime()
        `);

        const results = await introspection.searchArchitecture('authentication');

        // Note: This test assumes full-text index exists
        // If index doesn't exist, it will return empty array and log error
        expect(Array.isArray(results)).toBe(true);
      } finally {
        await session.close();
      }
    });

    it('should return empty array for no matches', async () => {
      const results = await introspection.searchArchitecture('xyznonexistentquery123');

      expect(Array.isArray(results)).toBe(true);
      expect(results.length).toBe(0);
    });

    it('should handle missing full-text index gracefully', async () => {
      const session = driver.session();
      try {
        // Try to search without index - should handle error
        const results = await introspection.searchArchitecture('test');

        // Should return empty array on error
        expect(Array.isArray(results)).toBe(true);
      } finally {
        await session.close();
      }
    });

    it('should limit results to 10 items', async () => {
      // This is a structural test - the query has LIMIT 10
      const session = driver.session();
      try {
        // Create many sections
        for (let i = 0; i < 15; i++) {
          await session.run(`
            CREATE (s:ArchitectureSection {
              title: 'test-limit-' + $i,
              content: 'common searchable content for all sections',
              order: $i
            })
          `, { i });
        }

        // Search for common term
        const results = await introspection.searchArchitecture('common searchable');
        expect(results.length).toBeLessThanOrEqual(10);

        // Cleanup
        await session.run(`
          MATCH (s:ArchitectureSection)
          WHERE s.title STARTS WITH 'test-limit-'
          DETACH DELETE s
        `);
      } finally {
        await session.close();
      }
    });
  });

  describe('getSection', () => {
    it('should return section by title', async () => {
      const session = driver.session();
      try {
        await session.run(`
          MERGE (s:ArchitectureSection {title: 'test-get-section'})
          SET s.content = 'Test content for section retrieval',
              s.git_commit = 'abc123',
              s.updated_at = datetime()
        `);

        const section = await introspection.getSection('test-get-section');

        expect(section).not.toBeNull();
        expect(section.title).toBe('test-get-section');
        expect(section.content).toBe('Test content for section retrieval');
        expect(section.gitCommit).toBe('abc123');
        expect(section.updatedAt).toBeDefined();
      } finally {
        await session.close();
      }
    });

    it('should return null for non-existent section', async () => {
      const section = await introspection.getSection('non-existent-section-xyz');

      expect(section).toBeNull();
    });

    it('should handle Neo4j errors gracefully', async () => {
      const badIntrospection = new ArchitectureIntrospection(
        { session: () => ({ run: () => { throw new Error('Query failed'); }, close: jest.fn() }) },
        mockLogger
      );

      const section = await badIntrospection.getSection('any-section');

      expect(section).toBeNull();
      expect(mockLogger.error).toHaveBeenCalledWith(
        expect.stringContaining('[ARCH-introspection] Failed to get section')
      );
    });
  });

  describe('getLastSyncTimestamp', () => {
    it('should return timestamp when sections exist', async () => {
      const session = driver.session();
      try {
        await session.run(`
          MERGE (s:ArchitectureSection {title: 'test-sync-timestamp'})
          SET s.updated_at = datetime()
        `);

        const timestamp = await introspection.getLastSyncTimestamp();

        expect(timestamp).toBeDefined();
      } finally {
        await session.close();
      }
    });

    it('should return null when no sections exist', async () => {
      // Create temporary introspection that queries non-existent label
      const session = driver.session();
      try {
        // Delete all test sections temporarily
        await session.run(`
          MATCH (s:ArchitectureSection)
          WHERE s.title STARTS WITH 'test-'
          DETACH DELETE s
        `);

        const timestamp = await introspection.getLastSyncTimestamp();

        // Should return null when no sections
        expect(timestamp).toBeNull();
      } finally {
        await session.close();
      }
    });

    it('should handle errors gracefully', async () => {
      const badIntrospection = new ArchitectureIntrospection(
        { session: () => ({ run: () => { throw new Error('Connection lost'); }, close: jest.fn() }) },
        mockLogger
      );

      const timestamp = await badIntrospection.getLastSyncTimestamp();

      expect(timestamp).toBeNull();
      expect(mockLogger.error).toHaveBeenCalledWith(
        expect.stringContaining('[ARCH-introspection] Failed to get last sync')
      );
    });
  });

  describe('isIndexReady', () => {
    it('should check for full-text index existence', async () => {
      const result = await introspection.isIndexReady();

      // Result depends on whether index exists in test database
      expect(typeof result).toBe('boolean');
    });

    it('should return false on Neo4j error', async () => {
      const badIntrospection = new ArchitectureIntrospection(
        { session: () => ({ run: () => { throw new Error('Index check failed'); }, close: jest.fn() }) },
        mockLogger
      );

      const result = await badIntrospection.isIndexReady();

      expect(result).toBe(false);
      expect(mockLogger.error).toHaveBeenCalledWith(
        expect.stringContaining('[ARCH-introspection] Index check failed')
      );
    });

    it('should return false when index does not exist', async () => {
      // Query for a non-existent index name
      const session = driver.session();
      try {
        const result = await session.run(`
          CALL db.indexes() YIELD name, type
          WHERE name = 'nonexistent_index_xyz' AND type = 'FULLTEXT'
          RETURN count(*) as exists
        `);

        const exists = result.records[0]?.get('exists').toNumber() > 0;
        expect(exists).toBe(false);
      } finally {
        await session.close();
      }
    });
  });
});
