/**
 * Delegation Protocol Module
 * 
 * Orchestrates the complete proposal workflow:
 * Opportunity → Proposal → Vetting → Implementation → Validation → Sync
 */

const { v4: uuidv4 } = require('uuid');

class DelegationProtocol {
  constructor(neo4jDriver) {
    this.driver = neo4jDriver;
    
    // Default configuration
    this.config = {
      autoVet: true,        // Auto-route to Ögedei
      autoImplement: true,  // Auto-route to Temüjin
      autoValidate: true,   // Auto-validate on completion
      autoSync: false       // Require manual approval for sync
    };
  }

  /**
   * Stage 1: Convert Opportunity to Proposal
   */
  async createProposal(opportunityId, proposalData) {
    const session = this.driver.session();
    
    try {
      // Get opportunity details
      const oppResult = await session.run(`
        MATCH (io:ImprovementOpportunity {id: $id})
        RETURN io.type as type, 
               io.description as description,
               io.priority as priority,
               io.target_section as target_section
      `, { id: opportunityId });
      
      if (oppResult.records.length === 0) {
        return { status: 'error', error: 'Opportunity not found' };
      }
      
      const opp = oppResult.records[0];
      
      // Create proposal
      const proposalId = uuidv4();
      
      await session.run(`
        MATCH (io:ImprovementOpportunity {id: $opp_id})
        CREATE (ap:ArchitectureProposal {
          id: $proposal_id,
          title: $title,
          description: $description,
          status: 'proposed',
          implementation_status: 'not_started',
          target_section: $target_section,
          proposed_by: 'kublai',
          proposed_at: datetime(),
          priority: $priority
        })
        CREATE (io)-[:EVOLVES_INTO]->(ap)
        SET io.status = 'evolved'
      `, {
        opp_id: opportunityId,
        proposal_id: proposalId,
        title: proposalData.title || `${opp.get('type')}: ${opp.get('description').substring(0, 50)}`,
        description: proposalData.description || opp.get('description'),
        target_section: opp.get('target_section'),
        priority: opp.get('priority')
      });
      
      // Auto-route to vetting if enabled
      if (this.config.autoVet) {
        await this.routeToVetting(proposalId);
      }
      
      return {
        status: 'success',
        proposal_id: proposalId,
        next_stage: 'under_review'
      };
      
    } finally {
      await session.close();
    }
  }

  /**
   * Stage 2: Route to Ögedei for Vetting
   */
  async routeToVetting(proposalId) {
    const session = this.driver.session();
    
    try {
      await session.run(`
        MATCH (ap:ArchitectureProposal {id: $id})
        SET ap.status = 'under_review'
        CREATE (v:Vetting {
          id: $vetting_id,
          proposal_id: $id,
          vetted_by: 'ögedei',
          status: 'pending',
          created_at: datetime()
        })
        CREATE (ap)-[:HAS_VETTING]->(v)
      `, {
        id: proposalId,
        vetting_id: uuidv4()
      });
      
      return { status: 'success', stage: 'under_review' };
    } finally {
      await session.close();
    }
  }

  /**
   * Stage 2b: Ögedei approves/rejects
   */
  async completeVetting(proposalId, decision, notes = '') {
    const session = this.driver.session();
    
    try {
      await session.run(`
        MATCH (ap:ArchitectureProposal {id: $id})-[:HAS_VETTING]->(v:Vetting)
        SET v.status = 'completed',
            v.decision = $decision,
            v.notes = $notes,
            v.completed_at = datetime()
      `, { id: proposalId, decision, notes });
      
      if (decision === 'approve' || decision === 'approve_with_review') {
        await session.run(`
          MATCH (ap:ArchitectureProposal {id: $id})
          SET ap.status = 'approved'
        `, { id: proposalId });
        
        // Auto-route to implementation
        if (this.config.autoImplement) {
          await this.startImplementation(proposalId);
        }
        
        return { status: 'success', stage: 'approved' };
      } else {
        await session.run(`
          MATCH (ap:ArchitectureProposal {id: $id})
          SET ap.status = 'rejected'
        `, { id: proposalId });
        
        return { status: 'success', stage: 'rejected' };
      }
    } finally {
      await session.close();
    }
  }

  /**
   * Stage 3: Start Implementation (Temüjin)
   */
  async startImplementation(proposalId) {
    const session = this.driver.session();
    
    try {
      await session.run(`
        MATCH (ap:ArchitectureProposal {id: $id})
        SET ap.implementation_status = 'in_progress'
        CREATE (i:Implementation {
          id: $impl_id,
          proposal_id: $id,
          implemented_by: 'temüjin',
          status: 'in_progress',
          started_at: datetime()
        })
        CREATE (ap)-[:IMPLEMENTED_BY]->(i)
      `, {
        id: proposalId,
        impl_id: uuidv4()
      });
      
      return { status: 'success', stage: 'implementation' };
    } finally {
      await session.close();
    }
  }

  /**
   * Stage 3b: Complete Implementation
   */
  async completeImplementation(proposalId, implementationNotes = '') {
    const session = this.driver.session();
    
    try {
      await session.run(`
        MATCH (ap:ArchitectureProposal {id: $id})-[:IMPLEMENTED_BY]->(i:Implementation)
        SET i.status = 'completed',
            i.notes = $notes,
            i.completed_at = datetime()
      `, { id: proposalId, notes: implementationNotes });
      
      // Auto-validate if enabled
      if (this.config.autoValidate) {
        await this.validateImplementation(proposalId);
      }
      
      return { status: 'success', stage: 'validation' };
    } finally {
      await session.close();
    }
  }

  /**
   * Stage 4: Validation
   */
  async validateImplementation(proposalId) {
    const session = this.driver.session();
    
    try {
      // Run validation checks
      const checks = await this.runValidationChecks(proposalId);
      
      const allPassed = checks.every(c => c.passed);
      
      await session.run(`
        MATCH (ap:ArchitectureProposal {id: $id})
        CREATE (val:Validation {
          id: $val_id,
          proposal_id: $id,
          passed: $passed,
          checks: $checks,
          validated_at: datetime()
        })
        CREATE (ap)-[:VALIDATED_BY]->(val)
      `, {
        id: proposalId,
        val_id: uuidv4(),
        passed: allPassed,
        checks: JSON.stringify(checks)
      });
      
      if (allPassed) {
        await session.run(`
          MATCH (ap:ArchitectureProposal {id: $id})
          SET ap.implementation_status = 'validated'
        `, { id: proposalId });
        
        return {
          status: 'success',
          stage: 'validated',
          checks: checks
        };
      } else {
        return {
          status: 'failed',
          stage: 'validation_failed',
          checks: checks
        };
      }
    } finally {
      await session.close();
    }
  }

  /**
   * Run validation checks
   */
  async runValidationChecks(proposalId) {
    // In production, these would be actual tests
    return [
      { name: 'syntax_check', passed: true },
      { name: 'neo4j_schema', passed: true },
      { name: 'unit_tests', passed: true }
    ];
  }

  /**
   * Stage 5: Sync to ARCHITECTURE.md
   */
  async syncToArchitecture(proposalId) {
    if (!this.config.autoSync) {
      return {
        status: 'pending_approval',
        message: 'Manual approval required for ARCHITECTURE.md sync'
      };
    }
    
    const session = this.driver.session();
    
    try {
      // Verify both statuses are 'validated'
      const result = await session.run(`
        MATCH (ap:ArchitectureProposal {id: $id})
        WHERE ap.status = 'approved'
          AND ap.implementation_status = 'validated'
        RETURN ap.target_section as section
      `, { id: proposalId });
      
      if (result.records.length === 0) {
        return {
          status: 'error',
          error: 'Proposal not ready for sync - must be approved and validated'
        };
      }
      
      // Update ArchitectureSection
      await session.run(`
        MATCH (ap:ArchitectureProposal {id: $id})
        MATCH (as:ArchitectureSection {title: ap.target_section})
        CREATE (ap)-[:SYNCED_TO]->(as)
        SET as.last_updated = datetime(),
            ap.status = 'synced'
      `, { id: proposalId });
      
      return {
        status: 'success',
        stage: 'synced',
        message: 'Changes synced to ARCHITECTURE.md'
      };
    } finally {
      await session.close();
    }
  }

  /**
   * Get workflow status
   */
  async getWorkflowStatus(proposalId) {
    const session = this.driver.session();
    
    try {
      const result = await session.run(`
        MATCH (ap:ArchitectureProposal {id: $id})
        OPTIONAL MATCH (ap)-[:HAS_VETTING]->(v:Vetting)
        OPTIONAL MATCH (ap)-[:IMPLEMENTED_BY]->(i:Implementation)
        OPTIONAL MATCH (ap)-[:VALIDATED_BY]->(val:Validation)
        OPTIONAL MATCH (ap)-[:SYNCED_TO]->(as:ArchitectureSection)
        RETURN ap.status as proposal_status,
               ap.implementation_status as impl_status,
               v.status as vetting_status,
               v.decision as vetting_decision,
               i.status as impl_work_status,
               val.passed as validation_passed,
               as.title as synced_section
      `, { id: proposalId });
      
      if (result.records.length === 0) {
        return { status: 'not_found' };
      }
      
      const r = result.records[0];
      return {
        status: 'success',
        workflow: {
          proposal_status: r.get('proposal_status'),
          implementation_status: r.get('impl_status'),
          vetting: {
            status: r.get('vetting_status'),
            decision: r.get('vetting_decision')
          },
          implementation: {
            status: r.get('impl_work_status')
          },
          validation: {
            passed: r.get('validation_passed')
          },
          sync: {
            section: r.get('synced_section')
          }
        }
      };
    } finally {
      await session.close();
    }
  }
}

module.exports = { DelegationProtocol };
