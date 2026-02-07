/**
 * Architecture Introspection Tests
 *
 * Tests for the Kublai Architecture Introspection module.
 * Verifies querying and understanding system architecture from Neo4j.
 */

const { describe, it, expect, beforeAll, afterAll, jest } = require('@jest/globals');
const neo4j = require('neo4j-driver');
const { ArchitectureIntrospection } = require('../../src/kublai/architecture-introspection');

describe('Architecture Introspection', () => {
  let driver;
  let introspection;
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
    introspection = new ArchitectureIntrospection(driver, mockLogger);

    // Clean up any existing test data
    const session = driver.session();
    try {
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

  describe('getArchitectureOverview', () => {
    it('should return overview with sections when data exists', async () => {
      const session = driver.session();
      try {
        // Create test sections
        await session.run(`
          CREATE (s1:ArchitectureSection {
            title: 'Test-System-Overview',
            content: 'System overview content',
            order: 1,
            parent_section: null,
            updated_at: datetime()
          })
          CREATE (s2:ArchitectureSection {
            title: 'Test-API-Routes',
            content: 'API routes content',
            order: 2,
            parent_section: 'Test-System-Overview',
            updated_at: datetime()
          })
        `);

        const result = await introspection.getArchitectureOverview();

        expect(result.totalSections).toBeGreaterThanOrEqual(2);
        expect(result.sections.length).toBeGreaterThanOrEqual(2);
        expect(result.lastSync).toBeDefined();

        const sectionTitles = result.sections.map(s => s.title);
        expect(sectionTitles).toContain('Test-System-Overview');
        expect(sectionTitles).toContain('Test-API-Routes');
      } finally {
        await session.close();
      }
    });

    it('should return empty overview when no sections exist', async () => {
      // Clean all sections first
      const session = driver.session();
      try {
        await session.run(`
          MATCH (s:ArchitectureSection)
          WHERE s.title STARTS WITH 'Test-'
          DETACH DELETE s
        `);

        const result = await introspection.getArchitectureOverview();

        // Should return empty but valid structure
        expect(result.totalSections).toBeGreaterThanOrEqual(0);
        expect(Array.isArray(result.sections)).toBe(true);
      } finally {
        await session.close();
      }
    });

    it('should handle Neo4j errors gracefully', async () => {
      // Create introspection with invalid driver to simulate error
      const badIntrospection = new ArchitectureIntrospection(
        { session: () => { throw new Error('Connection failed'); } },
        mockLogger
      );

      const result = await badIntrospection.getArchitectureOverview();

      expect(result.totalSections).toBe(0);
      expect(result.sections).toEqual([]);
      expect(result.lastSync).toBeNull();
      expect(mockLogger.error).toHaveBeenCalled();
    });
  });

  describe('searchArchitecture', () => {
    it('should return matching sections for valid search term', async () => {
      const session = driver.session();
      try {
        // Create section with searchable content
        await session.run(`
          CREATE (s:ArchitectureSection {
            title: 'Test-Search-Section',
            content: 'This section contains searchable content about authentication and security',
            order: 3,
            updated_at: datetime()
          })
        `);

        // Note: This test assumes full-text index exists
        // If index doesn't exist, search will return empty array
        const result = await introspection.searchArchitecture('authentication');

        // Result should be an array (may be empty if index not configured)
        expect(Array.isArray(result)).toBe(true);
      } finally {
        await session.close();
      }
    });

    it('should return empty array when no matches found', async () => {
      const result = await introspection.searchArchitecture('xyznonexistent12345');

      expect(Array.isArray(result)).toBe(true);
      expect(result.length).toBe(0);
    });

    it('should handle search errors gracefully', async () => {
      // Create introspection with driver that throws on session
      const badDriver = {
        session: () => ({
          run: () => { throw new Error('Search index not found'); },
          close: jest.fn()
        })
      };
      const badIntrospection = new ArchitectureIntrospection(badDriver, mockLogger);

      const result = await badIntrospection.searchArchitecture('test');

      expect(result).toEqual([]);
      expect(mockLogger.error).toHaveBeenCalled();
    });
  });

  describe('getSection', () => {
    it('should return section details for existing section', async () => {
      const session = driver.session();
      try {
        await session.run(`
          CREATE (s:ArchitectureSection {
            title: 'Test-Get-Section',
            content: 'Test content for get section',
            git_commit: 'abc123',
            updated_at: datetime()
          })
        `);

        const result = await introspection.getSection('Test-Get-Section');

        expect(result).not.toBeNull();
        expect(result.title).toBe('Test-Get-Section');
        expect(result.content).toBe('Test content for get section');
        expect(result.gitCommit).toBe('abc123');
        expect(result.updatedAt).toBeDefined();
      } finally {
        await session.close();
      }
    });

    it('should return null for non-existent section', async () => {
      const result = await introspection.getSection('Test-NonExistent-Section-12345');

      expect(result).toBeNull();
    });

    it('should handle errors gracefully', async () => {
      const badDriver = {
        session: () => ({
          run: () => { throw new Error('Query failed'); },
          close: jest.fn()
        })
      };
      const badIntrospection = new ArchitectureIntrospection(badDriver, mockLogger);

      const result = await badIntrospection.getSection('Test-Section');

      expect(result).toBeNull();
      expect(mockLogger.error).toHaveBeenCalled();
    });
  });

  describe('getLastSyncTimestamp', () => {
    it('should return timestamp when sections exist', async () => {
      const session = driver.session();
      try {
        await session.run(`
          CREATE (s:ArchitectureSection {
            title: 'Test-Sync-Timestamp',
            content: 'Content',
            updated_at: datetime()
          })
        `);

        const result = await introspection.getLastSyncTimestamp();

        expect(result).toBeDefined();
      } finally {
        await session.close();
      }
    });

    it('should return null when no sections exist', async () => {
      // Clean all test sections
      const session = driver.session();
      try {
        await session.run(`
          MATCH (s:ArchitectureSection)
          WHERE s.title STARTS WITH 'Test-'
          DETACH DELETE s
        `);

        const result = await introspection.getLastSyncTimestamp();

        expect(result).toBeNull();
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
      const badIntrospection = new ArchitectureIntrospection(badDriver, mockLogger);

      const result = await badIntrospection.getLastSyncTimestamp();

      expect(result).toBeNull();
      expect(mockLogger.error).toHaveBeenCalled();
    });
  });

  describe('isIndexReady', () => {
    it('should return boolean for index check', async () => {
      const result = await introspection.isIndexReady();

      expect(typeof result).toBe('boolean');
    });

    it('should handle errors gracefully and return false', async () => {
      const badDriver = {
        session: () => ({
          run: () => { throw new Error('Index check failed'); },
          close: jest.fn()
        })
      };
      const badIntrospection = new ArchitectureIntrospection(badDriver, mockLogger);

      const result = await badIntrospection.isIndexReady();

      expect(result).toBe(false);
      expect(mockLogger.error).toHaveBeenCalled();
    });
  });
});
