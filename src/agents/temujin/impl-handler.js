/**
 * Temüjin (Developer) Proposal Implementation Handler
 *
 * Temüjin implements approved proposals, tracks progress,
 * and manages the implementation lifecycle.
 */

class TemujinImplHandler {
  constructor(neo4jDriver, logger) {
    this.driver = neo4jDriver;
    this.logger = logger;
  }

  /**
   * Start implementing a proposal
   */
  async implementProposal(proposalId) {
    this.logger.info(`[Temüjin] Implementing proposal: ${proposalId}`);

    const session = this.driver.session();
    try {
      // Fetch proposal
      const result = await session.run(`
        MATCH (p:ArchitectureProposal {id: $id})
        RETURN p
      `, { id: proposalId });

      if (result.records.length === 0) {
        return { success: false, error: 'Proposal not found' };
      }

      const proposal = result.records[0].get('p').properties;

      // Check if approved
      if (proposal.status !== 'approved') {
        return {
          success: false,
          error: `Proposal must be approved before implementation. Current status: ${proposal.status}`
        };
      }

      // Create implementation record
      const implResult = await session.run(`
        CREATE (i:Implementation {
          id: randomUUID(),
          proposal_id: $id,
          started_at: datetime(),
          status: 'in_progress',
          progress: 0
        })
        RETURN i.id as implId
      `, { id: proposalId });

      const implId = implResult.records[0].get('implId');

      // Update proposal
      await session.run(`
        MATCH (p:ArchitectureProposal {id: $id})
        SET p.implementation_status = 'in_progress',
            p.implementation_id = $implId,
            p.implementation_started_at = datetime()
      `, { id: proposalId, implId });

      // Link proposal to implementation
      await session.run(`
        MATCH (p:ArchitectureProposal {id: $id})
        MATCH (i:Implementation {id: $implId})
        CREATE (p)-[:IMPLEMENTED_BY]->(i)
      `, { id: proposalId, implId });

      this.logger.info(`[Temüjin] Implementation started: ${implId}`);
      return { success: true, implementationId: implId, status: 'in_progress' };
    } catch (error) {
      this.logger.error(`[Temüjin] Implementation failed: ${error.message}`);
      return { success: false, error: error.message };
    } finally {
      await session.close();
    }
  }

  /**
   * Update implementation progress
   */
  async updateProgress(implId, progress, notes = '') {
    const session = this.driver.session();
    try {
      if (progress < 0 || progress > 100) {
        return { success: false, error: 'Progress must be between 0 and 100' };
      }

      await session.run(`
        MATCH (i:Implementation {id: $id})
        SET i.progress = $progress,
            i.notes = $notes,
            i.updated_at = datetime()
      `, { id: implId, progress, notes });

      this.logger.info(`[Temüjin] Progress update: ${implId} → ${progress}%`);
      return { success: true, progress };
    } catch (error) {
      this.logger.error(`[Temüjin] Progress update failed: ${error.message}`);
      return { success: false, error: error.message };
    } finally {
      await session.close();
    }
  }

  /**
   * Complete an implementation
   */
  async completeImplementation(implId, summary = '') {
    const session = this.driver.session();
    try {
      // Update implementation
      await session.run(`
        MATCH (i:Implementation {id: $id})
        SET i.status = 'completed',
            i.completed_at = datetime(),
            i.summary = $summary,
            i.progress = 100
      `, { id: implId, summary });

      // Update proposal
      await session.run(`
        MATCH (i:Implementation {id: $id})
        MATCH (p:ArchitectureProposal {id: i.proposal_id})
        SET p.implementation_status = 'completed',
            p.implementation_completed_at = datetime()
      `, { id: implId });

      this.logger.info(`[Temüjin] Implementation completed: ${implId}`);
      return { success: true, status: 'completed' };
    } catch (error) {
      this.logger.error(`[Temüjin] Completion failed: ${error.message}`);
      return { success: false, error: error.message };
    } finally {
      await session.close();
    }
  }

  /**
   * Mark implementation as failed
   */
  async failImplementation(implId, reason) {
    const session = this.driver.session();
    try {
      // Update implementation
      await session.run(`
        MATCH (i:Implementation {id: $id})
        SET i.status = 'failed',
            i.failed_at = datetime(),
            i.failure_reason = $reason
      `, { id: implId, reason });

      // Update proposal
      await session.run(`
        MATCH (i:Implementation {id: $id})
        MATCH (p:ArchitectureProposal {id: i.proposal_id})
        SET p.implementation_status = 'failed'
      `, { id: implId });

      this.logger.info(`[Temüjin] Implementation failed: ${implId} - ${reason}`);
      return { success: true, status: 'failed' };
    } catch (error) {
      this.logger.error(`[Temüjin] Failure marking failed: ${error.message}`);
      return { success: false, error: error.message };
    } finally {
      await session.close();
    }
  }

  /**
   * Get implementation details
   */
  async getImplementation(implId) {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        MATCH (i:Implementation {id: $id})
        OPTIONAL MATCH (p:ArchitectureProposal)-[:IMPLEMENTED_BY]->(i)
        RETURN i.id as id, i.status as status, i.progress as progress,
               i.started_at as startedAt, i.completed_at as completedAt,
               i.notes as notes, i.summary as summary,
               p.id as proposalId, p.title as proposalTitle
      `, { id: implId });

      if (result.records.length === 0) {
        return null;
      }

      const record = result.records[0];
      return {
        id: record.get('id'),
        status: record.get('status'),
        progress: record.get('progress'),
        startedAt: record.get('startedAt'),
        completedAt: record.get('completedAt'),
        notes: record.get('notes'),
        summary: record.get('summary'),
        proposalId: record.get('proposalId'),
        proposalTitle: record.get('proposalTitle')
      };
    } catch (error) {
      this.logger.error(`[Temüjin] Failed to get implementation: ${error.message}`);
      return null;
    } finally {
      await session.close();
    }
  }

  /**
   * Get active implementations
   */
  async getActiveImplementations() {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        MATCH (i:Implementation {status: 'in_progress'})
        MATCH (p:ArchitectureProposal)-[:IMPLEMENTED_BY]->(i)
        RETURN i.id as id, i.progress as progress, i.started_at as startedAt,
               p.id as proposalId, p.title as proposalTitle
        ORDER BY i.started_at DESC
      `);

      return result.records.map(r => ({
        id: r.get('id'),
        progress: r.get('progress'),
        startedAt: r.get('startedAt'),
        proposalId: r.get('proposalId'),
        proposalTitle: r.get('proposalTitle')
      }));
    } catch (error) {
      this.logger.error(`[Temüjin] Failed to get active: ${error.message}`);
      return [];
    } finally {
      await session.close();
    }
  }

  /**
   * Get proposals ready for implementation (approved but not started)
   */
  async getReadyToImplement() {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        MATCH (p:ArchitectureProposal {status: 'approved'})
        WHERE NOT EXISTS((p)-[:IMPLEMENTED_BY]->(:Implementation))
        RETURN p.id as id, p.title as title, p.description as description,
               p.approved_at as approvedAt
        ORDER BY p.approved_at DESC
      `);

      return result.records.map(r => ({
        id: r.get('id'),
        title: r.get('title'),
        description: r.get('description'),
        approvedAt: r.get('approvedAt')
      }));
    } catch (error) {
      this.logger.error(`[Temüjin] Failed to get ready: ${error.message}`);
      return [];
    } finally {
      await session.close();
    }
  }
}

module.exports = { TemujinImplHandler };
