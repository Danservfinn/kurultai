/**
 * Ögedei (Operations) Proposal Vetting Handler
 *
 * Ögedei reviews proposals for operational impact, deployment risk,
 * and provides recommendations. This is the operations gatekeeper
 * role in the proposal workflow.
 */

class OgedeiVetHandler {
  constructor(neo4jDriver, logger) {
    this.driver = neo4jDriver;
    this.logger = logger;
  }

  /**
   * Vet a proposal for operational viability
   */
  async vetProposal(proposalId) {
    this.logger.info(`[Ögedei] Vetting proposal: ${proposalId}`);

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

      // Ögedei's operational analysis
      const vetting = {
        operationalImpact: this.assessImpact(proposal),
        deploymentRisk: this.assessRisk(proposal),
        rolloutStrategy: this.suggestRollout(proposal),
        monitoring: this.suggestMonitoring(proposal),
        notes: this.generateNotes(proposal)
      };

      // Store vetting result
      await session.run(`
        MATCH (p:ArchitectureProposal {id: $id})
        CREATE (v:Vetting {
          id: randomUUID(),
          proposal_id: $id,
          vetted_by: 'ogedei',
          vetted_at: datetime(),
          assessment: $assessment
        })
        CREATE (p)-[:HAS_VETTING]->(v)
      `, {
        id: proposalId,
        assessment: JSON.stringify(vetting)
      });

      // Make recommendation
      const recommendation = this.makeRecommendation(vetting);
      await session.run(`
        MATCH (p:ArchitectureProposal {id: $id})
        SET p.ogedei_recommendation = $recommendation,
            p.status = 'under_review'
      `, { id: proposalId, recommendation });

      this.logger.info(`[Ögedei] Vetting complete: ${recommendation}`);
      return {
        success: true,
        proposalId,
        vetting,
        recommendation
      };
    } catch (error) {
      this.logger.error(`[Ögedei] Vetting failed: ${error.message}`);
      return { success: false, error: error.message };
    } finally {
      await session.close();
    }
  }

  /**
   * Assess operational impact
   */
  assessImpact(proposal) {
    const title = (proposal.title || '').toLowerCase();
    const desc = (proposal.description || '').toLowerCase();
    const combined = `${title} ${desc}`;

    // High impact indicators
    if (combined.includes('database') || combined.includes('schema') ||
        combined.includes('api') || combined.includes('auth')) {
      return 'high';
    }

    // Medium impact indicators
    if (combined.includes('deploy') || combined.includes('config') ||
        combined.includes('monitor')) {
      return 'medium';
    }

    return 'low';
  }

  /**
   * Assess deployment risk
   */
  assessRisk(proposal) {
    const title = (proposal.title || '').toLowerCase();
    const desc = (proposal.description || '').toLowerCase();
    const combined = `${title} ${desc}`;

    // Critical risk indicators
    if (combined.includes('delete') || combined.includes('remove') ||
        combined.includes('drop') || combined.includes('migrate')) {
      return 'critical';
    }

    // High risk indicators
    if (combined.includes('change') && combined.includes('database')) {
      return 'high';
    }

    // Medium risk indicators
    if (combined.includes('api') || combined.includes('breaking')) {
      return 'medium';
    }

    return 'low';
  }

  /**
   * Suggest rollout strategy based on risk
   */
  suggestRollout(proposal) {
    const risk = this.assessRisk(proposal);

    const strategies = {
      critical: 'manual_with_rollback',
      high: 'blue_green',
      medium: 'canary',
      low: 'direct'
    };

    return strategies[risk] || 'direct';
  }

  /**
   * Suggest what to monitor during rollout
   */
  suggestMonitoring(proposal) {
    const title = (proposal.title || '').toLowerCase();
    const desc = (proposal.description || '').toLowerCase();
    const combined = `${title} ${desc}`;

    const monitoring = ['error_rate', 'latency_p95'];

    if (combined.includes('api') || combined.includes('endpoint')) {
      monitoring.push('request_rate', 'response_time');
    }

    if (combined.includes('database') || combined.includes('neo4j')) {
      monitoring.push('query_time', 'connection_pool');
    }

    if (combined.includes('agent') || combined.includes('coordination')) {
      monitoring.push('agent_heartbeat', 'message_queue_depth');
    }

    return monitoring;
  }

  /**
   * Generate additional notes
   */
  generateNotes(proposal) {
    const notes = [];

    if (this.assessRisk(proposal) === 'critical') {
      notes.push('CRITICAL: Requires human approval before deployment.');
    }

    if (this.assessImpact(proposal) === 'high') {
      notes.push('HIGH IMPACT: Schedule during maintenance window.');
    }

    if (this.suggestRollout(proposal) === 'blue_green') {
      notes.push('Use blue-green deployment for zero-downtime rollout.');
    }

    return notes.join(' ');
  }

  /**
   * Make approval/rejection recommendation
   */
  makeRecommendation(vetting) {
    if (vetting.deploymentRisk === 'critical') {
      return 'reject';
    } else if (vetting.deploymentRisk === 'high') {
      return 'approve_with_conditions';
    } else if (vetting.operationalImpact === 'high') {
      return 'approve_with_review';
    } else {
      return 'approve';
    }
  }

  /**
   * Get all pending vetting requests
   */
  async getPendingVetting() {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        MATCH (p:ArchitectureProposal)
        WHERE p.status = 'proposed' AND NOT EXISTS((p)-[:HAS_VETTING]->(:Vetting))
        RETURN p.id as id, p.title as title, p.description as description,
               p.proposed_at as createdAt
        ORDER BY p.proposed_at ASC
      `);

      return result.records.map(r => ({
        id: r.get('id'),
        title: r.get('title'),
        description: r.get('description'),
        createdAt: r.get('createdAt')
      }));
    } catch (error) {
      this.logger.error(`[Ögedei] Failed to get pending: ${error.message}`);
      return [];
    } finally {
      await session.close();
    }
  }

  /**
   * Approve a proposal (after vetting)
   */
  async approveProposal(proposalId, notes = '') {
    const session = this.driver.session();
    try {
      await session.run(`
        MATCH (p:ArchitectureProposal {id: $id})
        SET p.status = 'approved',
            p.approved_by = 'ogedei',
            p.approved_at = datetime(),
            p.approval_notes = $notes
      `, { id: proposalId, notes });

      this.logger.info(`[Ögedei] Approved proposal: ${proposalId}`);
      return { success: true };
    } catch (error) {
      this.logger.error(`[Ögedei] Approval failed: ${error.message}`);
      return { success: false, error: error.message };
    } finally {
      await session.close();
    }
  }

  /**
   * Reject a proposal
   */
  async rejectProposal(proposalId, reason) {
    const session = this.driver.session();
    try {
      await session.run(`
        MATCH (p:ArchitectureProposal {id: $id})
        SET p.status = 'rejected',
            p.rejected_by = 'ogedei',
            p.rejected_at = datetime(),
            p.rejection_reason = $reason
      `, { id: proposalId, reason });

      this.logger.info(`[Ögedei] Rejected proposal: ${proposalId} - ${reason}`);
      return { success: true };
    } catch (error) {
      this.logger.error(`[Ögedei] Rejection failed: ${error.message}`);
      return { success: false, error: error.message };
    } finally {
      await session.close();
    }
  }
}

module.exports = { OgedeiVetHandler };
