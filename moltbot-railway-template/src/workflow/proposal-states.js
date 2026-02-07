/**
 * Proposal State Machine
 *
 * Manages the lifecycle of architecture proposals through
 * a defined state machine with guardrails.
 *
 * States: proposed → under_review → approved → implemented → validated → synced
 */

const proposalStates = {
  PROPOSED: 'proposed',
  UNDER_REVIEW: 'under_review',
  APPROVED: 'approved',
  REJECTED: 'rejected',
  IMPLEMENTED: 'implemented',
  VALIDATED: 'validated',
  SYNCED: 'synced' // Only synced proposals update ARCHITECTURE.md
};

const implementationStates = {
  NOT_STARTED: 'not_started',
  IN_PROGRESS: 'in_progress',
  COMPLETED: 'completed',
  VALIDATED: 'validated',
  FAILED: 'failed'
};

// Valid state transitions
const validTransitions = {
  proposed: ['under_review', 'rejected'],
  under_review: ['approved', 'rejected', 'proposed'],
  approved: ['implemented', 'rejected'],
  implemented: ['validated', 'failed'],
  validated: ['synced'],
  rejected: [], // Terminal state
  synced: [] // Terminal state
};

class ProposalStateMachine {
  constructor(neo4jDriver, logger) {
    this.driver = neo4jDriver;
    this.logger = logger;
  }

  /**
   * Create a new proposal from an opportunity
   */
  async createProposal(opportunityId, title, description, category = null) {
    const session = this.driver.session();
    try {
      // Create proposal
      const result = await session.run(`
        CREATE (p:ArchitectureProposal {
          id: randomUUID(),
          title: $title,
          description: $description,
          category: $category,
          status: 'proposed',
          proposed_at: datetime(),
          proposed_by: 'kublai',
          implementation_status: 'not_started',
          priority: 'medium'
        })
        RETURN p.id as id
      `, { title, description, category });

      const proposalId = result.records[0].get('id');

      // Link to opportunity if provided
      if (opportunityId) {
        await session.run(`
          MATCH (o:ImprovementOpportunity {id: $oppId})
          MATCH (p:ArchitectureProposal {id: $propId})
          CREATE (o)-[:EVOLVES_INTO]->(p)
        `, { oppId: opportunityId, propId: proposalId });
      }

      this.logger.info(`[Proposal] Created: ${proposalId} - ${title}`);
      return { proposalId, status: 'proposed' };
    } catch (error) {
      this.logger.error(`[Proposal] Failed to create: ${error.message}`);
      throw error;
    } finally {
      await session.close();
    }
  }

  /**
   * Transition proposal to a new state
   */
  async transition(proposalId, newState, reason = '', metadata = {}) {
    const session = this.driver.session();
    try {
      // Check current state
      const currentResult = await session.run(`
        MATCH (p:ArchitectureProposal {id: $id})
        RETURN p.status as currentStatus
      `, { id: proposalId });

      if (currentResult.records.length === 0) {
        return { success: false, error: 'Proposal not found' };
      }

      const currentStatus = currentResult.records[0].get('currentStatus');

      // Validate transition
      if (!this.canTransition(currentStatus, newState)) {
        return {
          success: false,
          error: `Invalid transition: ${currentStatus} → ${newState}`
        };
      }

      // Update state
      await session.run(`
        MATCH (p:ArchitectureProposal {id: $id})
        SET p.status = $newState,
            p.state_changed_at = datetime(),
            p.state_change_reason = $reason,
            p.previous_state = $oldState
      `, { id: proposalId, newState: proposalStates[newState.toUpperCase()] || newState, reason, oldState: currentStatus });

      // Add metadata if provided
      if (Object.keys(metadata).length > 0) {
        await session.run(`
          MATCH (p:ArchitectureProposal {id: $id})
          SET p += $metadata
        `, { id: proposalId, metadata });
      }

      this.logger.info(`[StateMachine] ${proposalId}: ${currentStatus} → ${newState} (${reason})`);
      return { success: true, newState, previousState: currentStatus };
    } catch (error) {
      this.logger.error(`[StateMachine] Transition failed: ${error.message}`);
      return { success: false, error: error.message };
    } finally {
      await session.close();
    }
  }

  /**
   * Check if a state transition is valid
   */
  canTransition(currentState, newState) {
    const validNext = validTransitions[currentState] || [];
    return validNext.includes(newState);
  }

  /**
   * Get proposal status
   */
  async getStatus(proposalId) {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        MATCH (p:ArchitectureProposal {id: $id})
        RETURN p.status as status,
               p.implementation_status as implStatus,
               p.title as title,
               p.state_changed_at as lastChanged
      `, { id: proposalId });

      if (result.records.length === 0) {
        return null;
      }

      return result.records[0].toObject();
    } catch (error) {
      this.logger.error(`[StateMachine] Failed to get status: ${error.message}`);
      return null;
    } finally {
      await session.close();
    }
  }

  /**
   * List proposals by status
   */
  async listByStatus(status = 'proposed', limit = 20) {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        MATCH (p:ArchitectureProposal {status: $status})
        RETURN p.id as id, p.title as title, p.description as description,
               p.priority as priority, p.proposed_at as createdAt,
               p.implementation_status as implStatus
        ORDER BY p.priority DESC, p.proposed_at DESC
        LIMIT $limit
      `, { status, limit });

      return result.records.map(r => ({
        id: r.get('id'),
        title: r.get('title'),
        description: r.get('description'),
        priority: r.get('priority'),
        createdAt: r.get('createdAt'),
        implementationStatus: r.get('implStatus')
      }));
    } catch (error) {
      this.logger.error(`[StateMachine] Failed to list: ${error.message}`);
      return [];
    } finally {
      await session.close();
    }
  }

  /**
   * Update implementation status
   */
  async updateImplementationStatus(proposalId, implStatus, progress = null, notes = null) {
    const session = this.driver.session();
    try {
      await session.run(`
        MATCH (p:ArchitectureProposal {id: $id})
        SET p.implementation_status = $implStatus,
            p.impl_updated_at = datetime()
      `, { id: proposalId, implStatus: implementationStates[implStatus.toUpperCase()] || implStatus });

      // Update implementation record if exists
      if (progress !== null || notes !== null) {
        await session.run(`
          MATCH (p:ArchitectureProposal {id: $id})
          MATCH (i:Implementation {proposal_id: $id})
          SET i.progress = coalesce($progress, i.progress),
              i.notes = coalesce($notes, i.notes),
              i.updated_at = datetime()
        `, { id: proposalId, progress, notes });
      }

      this.logger.info(`[StateMachine] ${proposalId}: impl_status → ${implStatus}`);
      return { success: true };
    } catch (error) {
      this.logger.error(`[StateMachine] Failed to update impl status: ${error.message}`);
      return { success: false, error: error.message };
    } finally {
      await session.close();
    }
  }
}

module.exports = {
  ProposalStateMachine,
  proposalStates,
  implementationStates
};
