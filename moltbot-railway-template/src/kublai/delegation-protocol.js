/**
 * Kublai Delegation Protocol
 *
 * Integrates Kublai's self-awareness system with the proposal workflow.
 * Connects reflection opportunities to the proposal state machine,
 * routes proposals through agent handlers (Ögedei, Temüjin), and
 * manages the complete lifecycle from identification to sync.
 *
 * Workflow:
 *   Reflection Opportunity → Proposal → Vetting (Ögedei) → Approval →
 *   Implementation (Temüjin) → Validation → Sync to ARCHITECTURE.md
 */

class DelegationProtocol {
  constructor(neo4jDriver, logger, handlers = {}) {
    this.driver = neo4jDriver;
    this.logger = logger;

    // Handlers injected for workflow routing
    this.proactiveReflection = handlers.proactiveReflection;
    this.stateMachine = handlers.stateMachine;
    this.mapper = handlers.mapper;
    this.vetHandler = handlers.vetHandler;
    this.implHandler = handlers.implHandler;
    this.validationHandler = handlers.validationHandler;

    // Workflow configuration
    this.config = {
      autoVet: handlers.autoVet !== false,      // Auto-route to Ögedei
      autoImplement: handlers.autoImplement !== false,  // Auto-route to Temüjin
      autoValidate: handlers.autoValidate !== false,    // Auto-validate on completion
      autoSync: handlers.autoSync !== false,            // Auto-sync to ARCHITECTURE.md
      requireManualApproval: handlers.requireManualApproval || false
    };
  }

  /**
   * =============================================================================
   * STAGE 1: Opportunity → Proposal Creation
   * =============================================================================
   *
   * Connects ProactiveReflection.createOpportunity() to ProposalStateMachine.createProposal()
   * Triggered when reflection identifies improvement opportunities.
   */

  /**
   * Create proposals from all pending opportunities
   * Called after reflection identifies opportunities
   */
  async createProposalsFromOpportunities() {
    this.logger.info('[DelegationProtocol] Creating proposals from opportunities...');

    if (!this.proactiveReflection || !this.stateMachine) {
      this.logger.error('[DelegationProtocol] Missing required handlers for proposal creation');
      return { success: false, error: 'Missing handlers' };
    }

    try {
      // Get pending opportunities
      const opportunities = await this.proactiveReflection.getOpportunities('proposed');
      const results = [];

      for (const opp of opportunities) {
        // Check if opportunity already has a proposal
        const hasProposal = await this.opportunityHasProposal(opp.id || opp.type);
        if (hasProposal) {
          this.logger.info(`[DelegationProtocol] Opportunity ${opp.id} already has proposal, skipping`);
          continue;
        }

        // Create proposal from opportunity
        const result = await this.createProposalFromOpportunity(opp);
        results.push(result);

        if (result.success && this.config.autoVet) {
          // Auto-route to Ögedei for vetting
          await this.routeToVetting(result.proposalId);
        }
      }

      this.logger.info(`[DelegationProtocol] Created ${results.filter(r => r.success).length} proposals`);
      return {
        success: true,
        created: results.filter(r => r.success).length,
        failed: results.filter(r => !r.success).length,
        results
      };
    } catch (error) {
      this.logger.error(`[DelegationProtocol] Proposal creation failed: ${error.message}`);
      return { success: false, error: error.message };
    }
  }

  /**
   * Create a single proposal from an opportunity
   */
  async createProposalFromOpportunity(opportunity) {
    const session = this.driver.session();
    try {
      // Generate proposal title and description from opportunity
      const title = this.generateProposalTitle(opportunity);
      const description = opportunity.description;
      const category = this.inferCategory(opportunity);

      // Create the proposal via state machine
      const result = await this.stateMachine.createProposal(
        opportunity.id,
        title,
        description,
        category
      );

      if (result.proposalId) {
        // Map proposal to target ARCHITECTURE.md section
        await this.mapper.mapProposalToSection(result.proposalId);

        // Link opportunity to proposal in Neo4j
        await session.run(`
          MATCH (o:ImprovementOpportunity {type: $type, description: $desc})
          MATCH (p:ArchitectureProposal {id: $proposalId})
          MERGE (o)-[:EVOLVES_INTO]->(p)
          SET o.status = 'converted_to_proposal',
              o.proposal_id = $proposalId
        `, {
          type: opportunity.type,
          desc: opportunity.description,
          proposalId: result.proposalId
        });

        this.logger.info(`[DelegationProtocol] Proposal ${result.proposalId} created from opportunity`);
      }

      return {
        success: true,
        proposalId: result.proposalId,
        opportunityId: opportunity.id,
        title
      };
    } catch (error) {
      this.logger.error(`[DelegationProtocol] Failed to create proposal: ${error.message}`);
      return { success: false, error: error.message, opportunityId: opportunity.id };
    } finally {
      await session.close();
    }
  }

  /**
   * Check if an opportunity already has a linked proposal
   */
  async opportunityHasProposal(opportunityId) {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        MATCH (o:ImprovementOpportunity {id: $id})-[:EVOLVES_INTO]->(p:ArchitectureProposal)
        RETURN count(p) as count
      `, { id: opportunityId });

      return result.records[0].get('count').toNumber() > 0;
    } catch (error) {
      return false;
    } finally {
      await session.close();
    }
  }

  /**
   * =============================================================================
   * STAGE 2: Proposal → Vetting (Ögedei)
   * =============================================================================
   *
   * Routes new proposals to OgedeiVetHandler.vetProposal()
   * Ögedei assesses operational impact and provides recommendations.
   */

  /**
   * Route a proposal to Ögedei for vetting
   */
  async routeToVetting(proposalId) {
    this.logger.info(`[DelegationProtocol] Routing proposal ${proposalId} to Ögedei for vetting`);

    if (!this.vetHandler) {
      this.logger.error('[DelegationProtocol] VetHandler not available');
      return { success: false, error: 'VetHandler not configured' };
    }

    try {
      // Transition proposal to under_review
      await this.stateMachine.transition(proposalId, 'under_review', 'Auto-routed to Ögedei for vetting');

      // Ögedei vets the proposal
      const vettingResult = await this.vetHandler.vetProposal(proposalId);

      if (!vettingResult.success) {
        this.logger.error(`[DelegationProtocol] Vetting failed: ${vettingResult.error}`);
        return vettingResult;
      }

      // Handle vetting recommendation
      return await this.handleVettingRecommendation(proposalId, vettingResult);
    } catch (error) {
      this.logger.error(`[DelegationProtocol] Vetting route failed: ${error.message}`);
      return { success: false, error: error.message };
    }
  }

  /**
   * Handle Ögedei's vetting recommendation
   */
  async handleVettingRecommendation(proposalId, vettingResult) {
    const { recommendation, vetting } = vettingResult;

    this.logger.info(`[DelegationProtocol] Ögedei recommendation for ${proposalId}: ${recommendation}`);

    switch (recommendation) {
      case 'approve':
        await this.vetHandler.approveProposal(proposalId, 'Auto-approved based on Ögedei vetting');
        await this.stateMachine.transition(proposalId, 'approved', 'Approved by Ögedei');

        if (this.config.autoImplement) {
          // Auto-route to Temüjin for implementation
          return await this.routeToImplementation(proposalId);
        }
        break;

      case 'approve_with_review':
        await this.vetHandler.approveProposal(proposalId, 'Approved with operational review required');
        await this.stateMachine.transition(proposalId, 'approved', 'Approved by Ögedei with review');

        if (this.config.autoImplement) {
          return await this.routeToImplementation(proposalId);
        }
        break;

      case 'approve_with_conditions':
        // Store conditions but approve
        await this.vetHandler.approveProposal(
          proposalId,
          `Approved with conditions: ${vetting.notes}`
        );
        await this.stateMachine.transition(proposalId, 'approved', 'Approved with conditions');

        if (this.config.autoImplement) {
          return await this.routeToImplementation(proposalId);
        }
        break;

      case 'reject':
        await this.vetHandler.rejectProposal(proposalId, `Rejected by Ögedei: ${vetting.notes}`);
        await this.stateMachine.transition(proposalId, 'rejected', 'Rejected by Ögedei');
        break;

      default:
        this.logger.warn(`[DelegationProtocol] Unknown recommendation: ${recommendation}`);
    }

    return { success: true, recommendation, proposalId };
  }

  /**
   * =============================================================================
   * STAGE 3: Approved Proposal → Implementation (Temüjin)
   * =============================================================================
   *
   * Routes approved proposals to TemujinImplHandler.implementProposal()
   * Temüjin manages the implementation lifecycle.
   */

  /**
   * Route an approved proposal to Temüjin for implementation
   */
  async routeToImplementation(proposalId) {
    this.logger.info(`[DelegationProtocol] Routing proposal ${proposalId} to Temüjin for implementation`);

    if (!this.implHandler) {
      this.logger.error('[DelegationProtocol] ImplHandler not available');
      return { success: false, error: 'ImplHandler not configured' };
    }

    try {
      // Verify proposal is approved
      const status = await this.stateMachine.getStatus(proposalId);
      if (status.status !== 'approved') {
        return {
          success: false,
          error: `Proposal must be approved. Current status: ${status.status}`
        };
      }

      // Temüjin starts implementation
      const implResult = await this.implHandler.implementProposal(proposalId);

      if (!implResult.success) {
        this.logger.error(`[DelegationProtocol] Implementation start failed: ${implResult.error}`);
        return implResult;
      }

      // Update state machine
      await this.stateMachine.transition(proposalId, 'implemented', 'Implementation started by Temüjin');
      await this.stateMachine.updateImplementationStatus(proposalId, 'in_progress');

      this.logger.info(`[DelegationProtocol] Implementation ${implResult.implementationId} started for ${proposalId}`);

      return {
        success: true,
        proposalId,
        implementationId: implResult.implementationId
      };
    } catch (error) {
      this.logger.error(`[DelegationProtocol] Implementation route failed: ${error.message}`);
      return { success: false, error: error.message };
    }
  }

  /**
   * Update implementation progress
   */
  async updateImplementationProgress(implementationId, progress, notes = '') {
    if (!this.implHandler) {
      return { success: false, error: 'ImplHandler not configured' };
    }

    try {
      const result = await this.implHandler.updateProgress(implementationId, progress, notes);

      // If progress is 100%, auto-complete and validate
      if (result.success && progress >= 100 && this.config.autoValidate) {
        return await this.completeAndValidate(implementationId);
      }

      return result;
    } catch (error) {
      this.logger.error(`[DelegationProtocol] Progress update failed: ${error.message}`);
      return { success: false, error: error.message };
    }
  }

  /**
   * =============================================================================
   * STAGE 4: Implementation Completion → Validation → Sync
   * =============================================================================
   *
   * Connects implementation completion to validation and ARCHITECTURE.md sync.
   * Only validated proposals can sync (enforced by ProposalMapper guardrails).
   */

  /**
   * Complete implementation and trigger validation
   */
  async completeAndValidate(implementationId, summary = '') {
    this.logger.info(`[DelegationProtocol] Completing and validating implementation ${implementationId}`);

    try {
      // Complete the implementation
      const completeResult = await this.implHandler.completeImplementation(implementationId, summary);

      if (!completeResult.success) {
        return completeResult;
      }

      // Get proposal ID from implementation
      const impl = await this.implHandler.getImplementation(implementationId);
      if (!impl || !impl.proposalId) {
        return { success: false, error: 'Could not find proposal for implementation' };
      }

      // Run validation
      const validationResult = await this.validationHandler.validateImplementation(implementationId);

      if (validationResult.passed) {
        // Validation passed - proposal is now validated
        await this.stateMachine.transition(
          impl.proposalId,
          'validated',
          'Implementation completed and validated'
        );

        this.logger.info(`[DelegationProtocol] Proposal ${impl.proposalId} validated`);

        if (this.config.autoSync) {
          // Auto-sync to ARCHITECTURE.md
          return await this.syncToArchitecture(impl.proposalId);
        }

        return {
          success: true,
          proposalId: impl.proposalId,
          implementationId,
          status: 'validated'
        };
      } else {
        // Validation failed
        this.logger.warn(`[DelegationProtocol] Validation failed for ${implementationId}`);
        return {
          success: false,
          proposalId: impl.proposalId,
          implementationId,
          status: 'validation_failed',
          failedChecks: validationResult.failedChecks
        };
      }
    } catch (error) {
      this.logger.error(`[DelegationProtocol] Complete/validate failed: ${error.message}`);
      return { success: false, error: error.message };
    }
  }

  /**
   * Sync a validated proposal to ARCHITECTURE.md
   * Guardrail: Only validated proposals can sync (enforced by ProposalMapper)
   */
  async syncToArchitecture(proposalId) {
    this.logger.info(`[DelegationProtocol] Syncing proposal ${proposalId} to ARCHITECTURE.md`);

    try {
      // Check guardrail - can we sync?
      const guardrail = await this.mapper.checkCanSync(proposalId);

      if (!guardrail.allowed) {
        this.logger.warn(`[DelegationProtocol] Sync blocked by guardrail: ${guardrail.reason}`);
        return { success: false, error: guardrail.reason, blockedByGuardrail: true };
      }

      // Get target section
      const session = this.driver.session();
      let targetSection;
      try {
        const result = await session.run(`
          MATCH (p:ArchitectureProposal {id: $id})
          RETURN p.target_section as section
        `, { id: proposalId });
        targetSection = result.records[0]?.get('section');
      } finally {
        await session.close();
      }

      if (!targetSection) {
        return { success: false, error: 'No target section mapped for proposal' };
      }

      // Mark as synced
      const syncResult = await this.mapper.markSynced(proposalId, targetSection);

      if (syncResult.success) {
        await this.stateMachine.transition(proposalId, 'synced', 'Synced to ARCHITECTURE.md');
        this.logger.info(`[DelegationProtocol] Proposal ${proposalId} synced to "${targetSection}"`);
      }

      return syncResult;
    } catch (error) {
      this.logger.error(`[DelegationProtocol] Sync failed: ${error.message}`);
      return { success: false, error: error.message };
    }
  }

  /**
   * =============================================================================
   * UTILITY METHODS
   * =============================================================================
   */

  /**
   * Generate a proposal title from an opportunity
   */
  generateProposalTitle(opportunity) {
    const typeMap = {
      'missing_section': 'Add Missing Architecture Section',
      'stale_sync': 'Refresh Architecture Documentation',
      'no_architecture_data': 'Initialize Architecture Documentation',
      'api_gap': 'Enhance API Documentation',
      'security_gap': 'Strengthen Security Documentation',
      'deployment_gap': 'Improve Deployment Documentation'
    };

    const baseTitle = typeMap[opportunity.type] || 'Architecture Improvement';

    if (opportunity.suggestedSection) {
      return `${baseTitle}: ${opportunity.suggestedSection}`;
    }

    return baseTitle;
  }

  /**
   * Infer proposal category from opportunity
   */
  inferCategory(opportunity) {
    const type = opportunity.type || '';
    const desc = (opportunity.description || '').toLowerCase();

    if (type.includes('api') || desc.includes('api') || desc.includes('endpoint')) {
      return 'api';
    }
    if (type.includes('database') || desc.includes('data') || desc.includes('schema')) {
      return 'database';
    }
    if (type.includes('security') || desc.includes('auth')) {
      return 'security';
    }
    if (type.includes('deploy') || desc.includes('infrastructure')) {
      return 'deployment';
    }
    if (type.includes('agent') || desc.includes('coordination')) {
      return 'agent_coordination';
    }

    return 'general';
  }

  /**
   * Get workflow status for a proposal
   */
  async getWorkflowStatus(proposalId) {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        MATCH (p:ArchitectureProposal {id: $id})
        OPTIONAL MATCH (p)-[:HAS_VETTING]->(v:Vetting)
        OPTIONAL MATCH (p)-[:IMPLEMENTED_BY]->(i:Implementation)
        OPTIONAL MATCH (i)-[:VALIDATED_BY]->(val:Validation)
        OPTIONAL MATCH (p)-[:SYNCED_TO]->(s:ArchitectureSection)
        RETURN p.status as status,
               p.implementation_status as implStatus,
               v.vetted_by as vettedBy,
               v.vetted_at as vettedAt,
               i.id as implementationId,
               i.status as implRecordStatus,
               i.progress as progress,
               val.passed as validationPassed,
               s.title as syncedTo
      `, { id: proposalId });

      if (result.records.length === 0) {
        return null;
      }

      const record = result.records[0];
      return {
        proposalId,
        status: record.get('status'),
        implementationStatus: record.get('implStatus'),
        vettedBy: record.get('vettedBy'),
        vettedAt: record.get('vettedAt'),
        implementationId: record.get('implementationId'),
        implementationRecordStatus: record.get('implRecordStatus'),
        progress: record.get('progress'),
        validationPassed: record.get('validationPassed'),
        syncedTo: record.get('syncedTo')
      };
    } catch (error) {
      this.logger.error(`[DelegationProtocol] Failed to get workflow status: ${error.message}`);
      return null;
    } finally {
      await session.close();
    }
  }

  /**
   * Process all pending workflow steps
   * Call this periodically to advance proposals through the pipeline
   */
  async processPendingWorkflows() {
    this.logger.info('[DelegationProtocol] Processing pending workflows...');

    const results = {
      opportunitiesConverted: 0,
      proposalsVetted: 0,
      proposalsImplemented: 0,
      implementationsValidated: 0,
      proposalsSynced: 0
    };

    try {
      // Stage 1: Convert opportunities to proposals
      const conversionResult = await this.createProposalsFromOpportunities();
      if (conversionResult.success) {
        results.opportunitiesConverted = conversionResult.created;
      }

      // Stage 2: Vet any proposals that need vetting
      if (this.vetHandler) {
        const pendingVetting = await this.vetHandler.getPendingVetting();
        for (const proposal of pendingVetting) {
          await this.routeToVetting(proposal.id);
          results.proposalsVetted++;
        }
      }

      // Stage 3: Start implementation for approved proposals
      if (this.implHandler) {
        const readyToImplement = await this.implHandler.getReadyToImplement();
        for (const proposal of readyToImplement) {
          await this.routeToImplementation(proposal.id);
          results.proposalsImplemented++;
        }
      }

      // Stage 4: Validate completed implementations
      if (this.validationHandler) {
        const readyToValidate = await this.validationHandler.getReadyToValidate();
        for (const impl of readyToValidate) {
          await this.completeAndValidate(impl.id);
          results.implementationsValidated++;
        }
      }

      // Stage 5: Sync validated proposals
      const readyToSync = await this.mapper.getReadyToSync();
      for (const proposal of readyToSync) {
        await this.syncToArchitecture(proposal.id);
        results.proposalsSynced++;
      }

      this.logger.info('[DelegationProtocol] Workflow processing complete', results);
      return { success: true, results };
    } catch (error) {
      this.logger.error(`[DelegationProtocol] Workflow processing failed: ${error.message}`);
      return { success: false, error: error.message, results };
    }
  }
}

module.exports = { DelegationProtocol };
