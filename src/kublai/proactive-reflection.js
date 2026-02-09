/**
 * Proactive Reflection Module
 * 
 * Enables Kublai to identify improvement opportunities
 * and create proposals for architecture enhancements.
 */

const { ArchitectureIntrospection } = require('./architecture-introspection');

class ProactiveReflection {
  constructor(neo4jDriver) {
    this.driver = neo4jDriver;
    this.introspection = new ArchitectureIntrospection(neo4jDriver);
  }

  /**
   * Main entry point for reflection cycle
   */
  async triggerReflection() {
    console.log('🤔 Starting proactive reflection cycle...');
    
    // Analyze for opportunities
    const opportunities = await this.analyzeForOpportunities();
    
    // Store findings
    const stored = await this.storeOpportunities(opportunities);
    
    return {
      status: 'success',
      opportunities_found: opportunities.length,
      opportunities_stored: stored,
      timestamp: new Date().toISOString()
    };
  }

  /**
   * Analyze architecture for improvement opportunities
   */
  async analyzeForOpportunities() {
    const opportunities = [];
    
    // Check for stale sections
    const gaps = await this.introspection.identifyGaps();
    
    if (gaps.status === 'success') {
      // Add stale sections as opportunities
      for (const section of gaps.stale_sections) {
        opportunities.push({
          type: 'stale_sync',
          description: `Architecture section "${section.title}" is stale (last updated ${section.updated})`,
          priority: 'medium',
          target_section: section.title
        });
      }
      
      // Add missing sections as opportunities
      for (const section of gaps.missing_sections) {
        opportunities.push({
          type: 'missing_section',
          description: `Critical architecture section "${section}" is missing`,
          priority: 'high',
          target_section: section
        });
      }
    }
    
    // Check implementation gaps
    const implGaps = await this.checkImplementationGaps();
    opportunities.push(...implGaps);
    
    // Check for API documentation gaps
    const apiGaps = await this.checkAPIGaps();
    opportunities.push(...apiGaps);
    
    return opportunities;
  }

  /**
   * Check for implementation gaps
   */
  async checkImplementationGaps() {
    const session = this.driver.session();
    const gaps = [];
    
    try {
      // Check if background tasks are running
      const result = await session.run(`
        MATCH (tr:TaskResult)
        WHERE tr.started_at > datetime() - duration('P1D')
        RETURN count(tr) as recent_tasks
      `);
      
      const recentTasks = result.records[0].get('recent_tasks').toNumber();
      
      if (recentTasks === 0) {
        gaps.push({
          type: 'implementation_gap',
          description: 'No background tasks executed in last 24 hours - automation may not be running',
          priority: 'high',
          category: 'operations'
        });
      }
      
      // Check for unimplemented node types
      const nodeResult = await session.run(`
        MATCH (n)
        WHERE labels(n)[0] IN ['HeartbeatCycle', 'TaskResult', 'Research', 
                               'LearnedCapability', 'Analysis', 'ArchitectureProposal']
        RETURN labels(n)[0] as label, count(n) as count
      `);
      
      const counts = {};
      for (const record of nodeResult.records) {
        counts[record.get('label')] = record.get('count').toNumber();
      }
      
      if (!counts['ArchitectureProposal'] || counts['ArchitectureProposal'] === 0) {
        gaps.push({
          type: 'implementation_gap',
          description: 'ArchitectureProposal nodes not being created - self-awareness workflow incomplete',
          priority: 'medium',
          category: 'self_awareness'
        });
      }
      
    } finally {
      await session.close();
    }
    
    return gaps;
  }

  /**
   * Check for API documentation gaps
   */
  async checkAPIGaps() {
    const gaps = [];
    
    // Check if API documentation section exists
    const apiSection = await this.introspection.getSection('API Documentation');
    
    if (apiSection.status === 'not_found') {
      gaps.push({
        type: 'api_gap',
        description: 'API documentation section missing from architecture',
        priority: 'high',
        target_section: 'API Documentation'
      });
    }
    
    return gaps;
  }

  /**
   * Store opportunities in Neo4j
   */
  async storeOpportunities(opportunities) {
    const session = this.driver.session();
    let stored = 0;
    
    try {
      for (const opp of opportunities) {
        // Check if similar opportunity already exists
        const existing = await session.run(`
          MATCH (io:ImprovementOpportunity)
          WHERE io.type = $type 
            AND io.description = $description
            AND io.status IN ['proposed', 'under_review']
          RETURN count(io) as count
        `, { type: opp.type, description: opp.description });
        
        if (existing.records[0].get('count').toNumber() > 0) {
          continue; // Skip duplicates
        }
        
        // Create opportunity
        await session.run(`
          CREATE (io:ImprovementOpportunity {
            id: $id,
            type: $type,
            description: $description,
            priority: $priority,
            status: 'proposed',
            proposed_by: 'kublai',
            created_at: datetime(),
            target_section: $target_section,
            category: $category
          })
        `, {
          id: `opp_${Date.now()}_${stored}`,
          type: opp.type,
          description: opp.description,
          priority: opp.priority,
          target_section: opp.target_section || null,
          category: opp.category || 'general'
        });
        
        stored++;
      }
    } finally {
      await session.close();
    }
    
    return stored;
  }

  /**
   * Get pending opportunities
   */
  async getOpportunities(status = 'proposed') {
    const session = this.driver.session();
    
    try {
      const result = await session.run(`
        MATCH (io:ImprovementOpportunity)
        WHERE io.status = $status
        RETURN io.id as id,
               io.type as type,
               io.description as description,
               io.priority as priority,
               io.created_at as created_at
        ORDER BY 
          CASE io.priority
            WHEN 'critical' THEN 1
            WHEN 'high' THEN 2
            WHEN 'medium' THEN 3
            ELSE 4
          END,
          io.created_at DESC
      `, { status });
      
      return {
        status: 'success',
        opportunities: result.records.map(r => ({
          id: r.get('id'),
          type: r.get('type'),
          description: r.get('description'),
          priority: r.get('priority'),
          created_at: r.get('created_at')
        }))
      };
    } catch (error) {
      return { status: 'error', error: error.message };
    } finally {
      await session.close();
    }
  }
}

module.exports = { ProactiveReflection };
