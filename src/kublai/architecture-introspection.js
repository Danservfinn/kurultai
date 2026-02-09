/**
 * Architecture Introspection Module
 * 
 * Enables Kublai to query and analyze the system architecture
 * from Neo4j and ARCHITECTURE.md.
 */

const { Neo4jDriver } = require('./neo4j-client');

class ArchitectureIntrospection {
  constructor(neo4jDriver) {
    this.driver = neo4jDriver;
  }

  /**
   * Get overview of all architecture sections
   */
  async getArchitectureOverview() {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        MATCH (as:ArchitectureSection)
        RETURN as.title as title, 
               as.category as category, 
               as.section_order as order,
               as.last_updated as updated
        ORDER BY as.section_order
      `);
      
      return {
        status: 'success',
        sections: result.records.map(r => ({
          title: r.get('title'),
          category: r.get('category'),
          order: r.get('order').toNumber(),
          updated: r.get('updated')
        }))
      };
    } catch (error) {
      return { status: 'error', error: error.message };
    } finally {
      await session.close();
    }
  }

  /**
   * Search architecture sections
   */
  async searchArchitecture(query) {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        MATCH (as:ArchitectureSection)
        WHERE as.title CONTAINS $query 
           OR as.content_summary CONTAINS $query
        RETURN as.title as title,
               as.content_summary as summary,
               as.category as category
        LIMIT 10
      `, { query });
      
      return {
        status: 'success',
        query: query,
        results: result.records.map(r => ({
          title: r.get('title'),
          summary: r.get('summary'),
          category: r.get('category')
        }))
      };
    } catch (error) {
      return { status: 'error', error: error.message };
    } finally {
      await session.close();
    }
  }

  /**
   * Get specific section content
   */
  async getSection(title) {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        MATCH (as:ArchitectureSection {title: $title})
        RETURN as.content_summary as content,
               as.category as category,
               as.version as version,
               as.last_updated as updated
      `, { title });
      
      if (result.records.length === 0) {
        return { status: 'not_found', title };
      }
      
      const record = result.records[0];
      return {
        status: 'success',
        title: title,
        content: record.get('content'),
        category: record.get('category'),
        version: record.get('version'),
        updated: record.get('updated')
      };
    } catch (error) {
      return { status: 'error', error: error.message };
    } finally {
      await session.close();
    }
  }

  /**
   * Check when ARCHITECTURE.md was last synced
   */
  async getLastSyncTimestamp() {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        MATCH (as:ArchitectureSection)
        RETURN max(as.last_updated) as last_sync
      `);
      
      return {
        status: 'success',
        last_sync: result.records[0].get('last_sync')
      };
    } catch (error) {
      return { status: 'error', error: error.message };
    } finally {
      await session.close();
    }
  }

  /**
   * Identify architecture gaps
   */
  async identifyGaps() {
    const session = this.driver.session();
    try {
      // Check for outdated sections
      const staleResult = await session.run(`
        MATCH (as:ArchitectureSection)
        WHERE as.last_updated < datetime() - duration('P30D')
        RETURN as.title as title, as.last_updated as updated
      `);
      
      // Check for missing critical sections
      const requiredSections = [
        'Executive Summary',
        'System Architecture Overview',
        'Security Architecture',
        'Deployment Configuration'
      ];
      
      const existingResult = await session.run(`
        MATCH (as:ArchitectureSection)
        RETURN collect(as.title) as titles
      `);
      
      const existing = existingResult.records[0].get('titles');
      const missing = requiredSections.filter(s => !existing.includes(s));
      
      return {
        status: 'success',
        stale_sections: staleResult.records.map(r => ({
          title: r.get('title'),
          updated: r.get('updated')
        })),
        missing_sections: missing
      };
    } catch (error) {
      return { status: 'error', error: error.message };
    } finally {
      await session.close();
    }
  }
}

module.exports = { ArchitectureIntrospection };
