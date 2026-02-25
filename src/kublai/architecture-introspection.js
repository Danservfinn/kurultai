/**
 * Architecture Introspection for Kublai
 *
 * Enables Kublai to query and understand the system architecture
 * from Neo4j-backed ARCHITECTURE.md sections.
 *
 * This provides self-awareness — Kublai can understand the system
 * he orchestrates and identify improvement opportunities.
 */

class ArchitectureIntrospection {
  constructor(neo4jDriver, logger) {
    this.driver = neo4jDriver;
    this.logger = logger;
  }

  /**
   * Get architecture overview — all sections with metadata
   */
  async getArchitectureOverview() {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        MATCH (s:ArchitectureSection)
        RETURN s.title as section, s.order as position, s.parent_section as parent
        ORDER BY s.order
      `);

      const sections = result.records.map(r => ({
        title: r.get('section'),
        position: r.get('position'),
        parent: r.get('parent')
      }));

      return {
        totalSections: sections.length,
        sections: sections,
        lastSync: await this.getLastSyncTimestamp()
      };
    } catch (error) {
      this.logger.error(`[ARCH-introspection] Failed to get overview: ${error.message}`);
      return { totalSections: 0, sections: [], lastSync: null };
    } finally {
      await session.close();
    }
  }

  /**
   * Search architecture content using full-text search
   */
  async searchArchitecture(searchTerm) {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        CALL db.index.fulltext.queryNodes('architecture_search_index', $term)
        YIELD node, score
        RETURN node.title as title, node.content as content, score
        ORDER BY score DESC
        LIMIT 10
      `, { term: searchTerm });

      return result.records.map(r => ({
        title: r.get('title'),
        content: r.get('content'),
        relevance: r.get('score')
      }));
    } catch (error) {
      this.logger.error(`[ARCH-introspection] Search failed: ${error.message}`);
      return [];
    } finally {
      await session.close();
    }
  }

  /**
   * Get a specific architecture section by title
   */
  async getSection(title) {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        MATCH (s:ArchitectureSection {title: $title})
        RETURN s.title as title, s.content as content, s.git_commit as commit, s.updated_at as updated
      `, { title });

      if (result.records.length === 0) {
        return null;
      }

      const record = result.records[0];
      return {
        title: record.get('title'),
        content: record.get('content'),
        gitCommit: record.get('commit'),
        updatedAt: record.get('updated')
      };
    } catch (error) {
      this.logger.error(`[ARCH-introspection] Failed to get section: ${error.message}`);
      return null;
    } finally {
      await session.close();
    }
  }

  /**
   * Get last sync timestamp for architecture data
   */
  async getLastSyncTimestamp() {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        MATCH (s:ArchitectureSection)
        RETURN max(s.updated_at) as lastSync
      `);

      return result.records[0]?.get('lastSync') || null;
    } catch (error) {
      this.logger.error(`[ARCH-introspection] Failed to get last sync: ${error.message}`);
      return null;
    } finally {
      await session.close();
    }
  }

  /**
   * Check if architecture index exists and is ready
   */
  async isIndexReady() {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        CALL db.indexes() YIELD name, type
        WHERE name = 'architecture_search_index' AND type = 'FULLTEXT'
        RETURN count(*) as exists
      `);

      return result.records[0]?.get('exists').toNumber() > 0;
    } catch (error) {
      this.logger.error(`[ARCH-introspection] Index check failed: ${error.message}`);
      return false;
    } finally {
      await session.close();
    }
  }
}

module.exports = { ArchitectureIntrospection };
