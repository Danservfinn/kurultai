/**
 * Proactive Reflection for Kublai
 *
 * Triggers periodic self-reflection on system architecture,
 * identifying gaps and improvement opportunities.
 *
 * This is how Kublai becomes self-aware — by analyzing the
 * architecture documentation and proposing improvements.
 */

class ProactiveReflection {
  constructor(neo4jDriver, introspection, logger) {
    this.driver = neo4jDriver;
    this.introspection = introspection;
    this.logger = logger;
  }

  /**
   * Trigger a proactive architecture reflection
   */
  async triggerReflection() {
    this.logger.info('[Kublai] Triggering proactive architecture reflection...');

    // Step 1: Get current architecture overview
    const overview = await this.introspection.getArchitectureOverview();

    // Step 2: Analyze for gaps and opportunities
    const opportunities = await this.analyzeForOpportunities(overview);

    // Step 3: Store findings for review
    if (opportunities.length > 0) {
      await this.storeOpportunities(opportunities);
    }

    return {
      sectionsKnown: overview.totalSections,
      opportunitiesFound: opportunities.length,
      opportunities: opportunities.map(o => ({ type: o.type, description: o.description }))
    };
  }

  /**
   * Analyze architecture for gaps and improvement opportunities
   */
  async analyzeForOpportunities(overview) {
    const opportunities = [];

    // Check if we have architecture data
    if (!overview || overview.totalSections === 0) {
      opportunities.push({
        type: 'no_architecture_data',
        description: 'No architecture sections found in Neo4j. Run sync-architecture-to-neo4j.js',
        priority: 'critical'
      });
      return opportunities;
    }

    // Get section titles for analysis
    const sectionTitles = overview.sections.map(s => s.title.toLowerCase());

    // Check for common missing sections
    const expectedSections = [
      { name: 'system architecture', keywords: ['system', 'architecture', 'overview'] },
      { name: 'api routes', keywords: ['api', 'route', 'endpoint', 'http'] },
      { name: 'data model', keywords: ['data', 'model', 'schema', 'database'] },
      { name: 'security', keywords: ['security', 'auth', 'authentication', 'authorization'] },
      { name: 'deployment', keywords: ['deploy', 'infrastructure', 'railway', 'docker'] },
      { name: 'agent coordination', keywords: ['agent', 'coordination', 'message', 'gateway'] }
    ];

    for (const expected of expectedSections) {
      const hasSection = sectionTitles.some(title =>
        expected.keywords.some(keyword => title.includes(keyword))
      );

      if (!hasSection) {
        opportunities.push({
          type: 'missing_section',
          description: `Architecture documentation may be missing: ${expected.name}`,
          priority: 'medium',
          suggestedSection: expected.name
        });
      }
    }

    // Check for outdated sections (not synced in last 7 days)
    const lastSync = overview.lastSync;
    if (lastSync) {
      const syncAge = Date.now() - new Date(lastSync).getTime();
      const daysSinceSync = syncAge / (1000 * 60 * 60 * 24);

      if (daysSinceSync > 7) {
        opportunities.push({
          type: 'stale_sync',
          description: `Architecture data is ${Math.floor(daysSinceSync)} days old. Consider re-syncing.`,
          priority: 'low'
        });
      }
    }

    return opportunities;
  }

  /**
   * Store improvement opportunities in Neo4j
   */
  async storeOpportunities(opportunities) {
    const session = this.driver.session();
    try {
      for (const opp of opportunities) {
        await session.run(`
          MERGE (o:ImprovementOpportunity {
            type: $type,
            description: $description
          })
          SET o.priority = $priority,
              o.suggested_section = $suggestedSection,
              o.created_at = coalesce(o.created_at, datetime()),
              o.last_seen = datetime(),
              o.status = 'proposed',
              o.proposed_by = 'kublai'
        `, {
          type: opp.type,
          description: opp.description,
          priority: opp.priority,
          suggestedSection: opp.suggestedSection || null
        });
      }

      this.logger.info(`[Kublai] Stored ${opportunities.length} improvement opportunities`);
    } catch (error) {
      this.logger.error(`[Kublai] Failed to store opportunities: ${error.message}`);
    } finally {
      await session.close();
    }
  }

  /**
   * Get existing improvement opportunities
   */
  async getOpportunities(status = 'proposed') {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        MATCH (o:ImprovementOpportunity {status: $status})
        RETURN o.id as id, o.type as type, o.description as description,
               o.priority as priority, o.suggested_section as suggestedSection,
               o.created_at as createdAt, o.last_seen as lastSeen
        ORDER BY o.priority DESC, o.created_at DESC
      `, { status });

      return result.records.map(r => ({
        id: r.get('id'),
        type: r.get('type'),
        description: r.get('description'),
        priority: r.get('priority'),
        suggestedSection: r.get('suggestedSection'),
        createdAt: r.get('createdAt'),
        lastSeen: r.get('lastSeen')
      }));
    } catch (error) {
      this.logger.error(`[Kublai] Failed to get opportunities: ${error.message}`);
      return [];
    } finally {
      await session.close();
    }
  }

  /**
   * Mark an opportunity as addressed
   */
  async markOpportunityAddressed(opportunityId) {
    const session = this.driver.session();
    try {
      await session.run(`
        MATCH (o:ImprovementOpportunity {id: $id})
        SET o.status = 'addressed',
            o.addressed_at = datetime()
      `, { id: opportunityId });

      this.logger.info(`[Kublai] Marked opportunity ${opportunityId} as addressed`);
      return { success: true };
    } catch (error) {
      this.logger.error(`[Kublai] Failed to mark opportunity: ${error.message}`);
      return { success: false, error: error.message };
    } finally {
      await session.close();
    }
  }
}

module.exports = { ProactiveReflection };
