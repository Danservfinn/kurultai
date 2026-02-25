/**
 * Proposal-to-Architecture Mapper
 *
 * Maps implemented proposals to their target ARCHITECTURE.md sections.
 * Enforces guardrails to prevent unvalidated changes from syncing.
 *
 * KEY GUARDRAIL: Only validated+implemented proposals can sync to ARCHITECTURE.md
 */

class ProposalMapper {
  constructor(neo4jDriver, logger) {
    this.driver = neo4jDriver;
    this.logger = logger;
  }

  /**
   * Map a proposal to its target ARCHITECTURE.md section
   */
  async mapProposalToSection(proposalId) {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        MATCH (p:ArchitectureProposal {id: $id})
        RETURN p.title, p.description, p.category, p.target_section
      `, { id: proposalId });

      if (result.records.length === 0) {
        return { success: false, error: 'Proposal not found' };
      }

      const proposal = result.records[0].toObject();

      // Determine target section in ARCHITECTURE.md
      const targetSection = proposal.target_section ||
                           this.determineSection(proposal);

      // Create mapping record
      await session.run(`
        MATCH (p:ArchitectureProposal {id: $id})
        SET p.target_section = $section,
            p.section_mapping_created_at = datetime()
      `, { id: proposalId, section: targetSection });

      this.logger.info(`[Mapper] ${proposalId} → ${targetSection}`);
      return { success: true, proposalId, targetSection };
    } catch (error) {
      this.logger.error(`[Mapper] Failed to map: ${error.message}`);
      return { success: false, error: error.message };
    } finally {
      await session.close();
    }
  }

  /**
   * Determine the appropriate ARCHITECTURE.md section for a proposal
   */
  determineSection(proposal) {
    const title = (proposal.title || '').toLowerCase();
    const desc = (proposal.description || '').toLowerCase();
    const combined = `${title} ${desc}`;

    // Map content to appropriate ARCHITECTURE.md sections
    const sectionMappings = [
      { keywords: ['api', 'endpoint', 'route', 'http', 'rest', 'graphql'], section: 'API Routes' },
      { keywords: ['data', 'model', 'schema', 'database', 'neo4j', 'graph'], section: 'Data Model' },
      { keywords: ['security', 'auth', 'authentication', 'authorization', 'token'], section: 'Security Architecture' },
      { keywords: ['deploy', 'infra', 'railway', 'docker', 'container', 'ci/cd'], section: 'Deployment' },
      { keywords: ['agent', 'coordination', 'message', 'gateway', 'openclaw', 'signal'], section: 'Agent Coordination' },
      { keywords: ['memory', 'neo4j', 'operational', 'context'], section: 'Operational Memory' },
      { keywords: ['frontend', 'ui', 'interface', 'web', 'react'], section: 'Frontend' },
      { keywords: ['monitor', 'health', 'metric', 'logging', 'observability'], section: 'Monitoring' }
    ];

    for (const mapping of sectionMappings) {
      if (mapping.keywords.some(kw => combined.includes(kw))) {
        return mapping.section;
      }
    }

    // Default fallback
    return 'System Overview';
  }

  /**
   * CRITICAL GUARDRAIL: Check if proposal can be synced to ARCHITECTURE.md
   *
   * Only proposals that are BOTH implemented AND validated can sync.
   * This prevents unproven changes from being documented.
   */
  async checkCanSync(proposalId) {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        MATCH (p:ArchitectureProposal {id: $id})
        RETURN p.status as status,
               p.implementation_status as implStatus,
               p.title as title
      `, { id: proposalId });

      if (result.records.length === 0) {
        return { allowed: false, reason: 'Proposal not found' };
      }

      const record = result.records[0].toObject();

      // GUARDRAIL: Only validated proposals with validated implementation can sync
      const canSync = record.status === 'validated' &&
                      record.implStatus === 'validated';

      if (!canSync) {
        return {
          allowed: false,
          reason: `Guardrail: Proposal status=${record.status}, impl=${record.implStatus}. ` +
                  `Both must be 'validated' to sync.`
        };
      }

      return { allowed: true, title: record.title };
    } catch (error) {
      this.logger.error(`[Mapper] Guardrail check failed: ${error.message}`);
      return { allowed: false, reason: `Error: ${error.message}` };
    } finally {
      await session.close();
    }
  }

  /**
   * Mark a proposal as synced to ARCHITECTURE.md
   */
  async markSynced(proposalId, sectionTitle) {
    const session = this.driver.session();
    try {
      // Verify guardrail still passes
      const guardrail = await this.checkCanSync(proposalId);
      if (!guardrail.allowed) {
        this.logger.warn(`[Mapper] Sync blocked by guardrail: ${guardrail.reason}`);
        return { success: false, reason: guardrail.reason };
      }

      // Find or create the target section node
      await session.run(`
        MERGE (s:ArchitectureSection {title: $sectionTitle})
        ON CREATE SET s.order = 999, s.updated_at = datetime()
      `, { sectionTitle });

      // Create sync relationship
      await session.run(`
        MATCH (p:ArchitectureProposal {id: $id})
        MATCH (s:ArchitectureSection {title: $sectionTitle})
        CREATE (p)-[:SYNCED_TO {synced_at: datetime()}]->(s)
        SET p.status = 'synced',
            p.synced_at = datetime()
      `, { id: proposalId, sectionTitle });

      this.logger.info(`[Mapper] ${proposalId} synced to "${sectionTitle}"`);
      return { success: true };
    } catch (error) {
      this.logger.error(`[Mapper] Failed to mark synced: ${error.message}`);
      return { success: false, error: error.message };
    } finally {
      await session.close();
    }
  }

  /**
   * Get proposals ready to sync (validated but not yet synced)
   */
  async getReadyToSync() {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        MATCH (p:ArchitectureProposal {status: 'validated'})
        WHERE NOT EXISTS((p)-[:SYNCED_TO]->(:ArchitectureSection))
        RETURN p.id as id, p.title as title, p.target_section as targetSection,
               p.implementation_status as implStatus
        ORDER BY p.proposed_at DESC
      `);

      return result.records.map(r => ({
        id: r.get('id'),
        title: r.get('title'),
        targetSection: r.get('targetSection'),
        implementationStatus: r.get('implStatus')
      }));
    } catch (error) {
      this.logger.error(`[Mapper] Failed to get ready-to-sync: ${error.message}`);
      return [];
    } finally {
      await session.close();
    }
  }
}

module.exports = { ProposalMapper };
