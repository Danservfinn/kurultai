/**
 * End-to-End Proposal Lifecycle Test
 *
 * Complete walkthrough of the proposal lifecycle from opportunity
 * creation through ARCHITECTURE.md sync. Validates all state transitions,
 * Neo4j queries, and guardrail enforcement.
 *
 * Test Scenario:
 * 1. Create Opportunity (Kublai/ProactiveReflection)
 * 2. Create Proposal (Kublai)
 * 3. Vet Proposal (Ögedei)
 * 4. Implement Proposal (Temüjin)
 * 5. Validate (Kublai/System)
 * 6. Sync (Guardrailed)
 */

const { describe, it, expect, beforeAll, afterAll, jest } = require('@jest/globals');
const neo4j = require('neo4j-driver');

// Workflow modules
const { ProposalStateMachine, proposalStates, implementationStates } = require('../../src/workflow/proposal-states');
const { ProposalMapper } = require('../../src/workflow/proposal-mapper');
const { ValidationHandler } = require('../../src/workflow/validation');

// Agent handlers
const { OgedeiVetHandler } = require('../../src/agents/ogedei/vet-handler');
const { TemujinImplHandler } = require('../../src/agents/temujin/impl-handler');

// Kublai modules
const { ProactiveReflection } = require('../../src/kublai/proactive-reflection');

describe('E2E Proposal Lifecycle', () => {
  let driver;
  let stateMachine;
  let mapper;
  let validationHandler;
  let ogedeiVetHandler;
  let temujinImplHandler;
  let proactiveReflection;

  const mockLogger = {
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn()
  };

  // Mock introspection for proactive reflection
  const mockIntrospection = {
    getArchitectureOverview: jest.fn()
  };

  // Test data tracking
  let testData = {
    opportunityId: null,
    proposalId: null,
    implementationId: null,
    validationId: null
  };

  beforeAll(async () => {
    // Connect to test Neo4j instance
    const uri = process.env.NEO4J_URI || 'bolt://localhost:7687';
    const user = process.env.NEO4J_USER || 'neo4j';
    const password = process.env.NEO4J_PASSWORD || 'password';

    driver = neo4j.driver(uri, { auth: { user, password } });

    // Initialize all handlers
    stateMachine = new ProposalStateMachine(driver, mockLogger);
    mapper = new ProposalMapper(driver, mockLogger);
    validationHandler = new ValidationHandler(driver, mockLogger);
    ogedeiVetHandler = new OgedeiVetHandler(driver, mockLogger);
    temujinImplHandler = new TemujinImplHandler(driver, mockLogger);
    proactiveReflection = new ProactiveReflection(driver, mockIntrospection, mockLogger);

    // Clean up any existing test data
    const session = driver.session();
    try {
      await session.run(`
        MATCH (p:ArchitectureProposal)
        WHERE p.title STARTS WITH 'E2E-Test-'
        DETACH DELETE p
      `);
      await session.run(`
        MATCH (o:ImprovementOpportunity)
        WHERE o.description CONTAINS 'E2E-Test-'
        DETACH DELETE o
      `);
      await session.run(`
        MATCH (s:ArchitectureSection)
        WHERE s.title STARTS WITH 'E2E-Test-'
        DETACH DELETE s
      `);
    } finally {
      await session.close();
    }
  });

  afterAll(async () => {
    // Clean up test data
    const session = driver.session();
    try {
      await session.run(`
        MATCH (p:ArchitectureProposal)
        WHERE p.title STARTS WITH 'E2E-Test-'
        DETACH DELETE p
      `);
      await session.run(`
        MATCH (o:ImprovementOpportunity)
        WHERE o.description CONTAINS 'E2E-Test-'
        DETACH DELETE o
      `);
      await session.run(`
        MATCH (s:ArchitectureSection)
        WHERE s.title STARTS WITH 'E2E-Test-'
        DETACH DELETE s
      `);
    } finally {
      await session.close();
    }

    if (driver) {
      await driver.close();
    }
  });

  describe('Step 1: Create Opportunity (Kublai/ProactiveReflection)', () => {
    it('should trigger reflection and detect missing section', async () => {
      // Setup: Mock architecture overview with missing security section
      mockIntrospection.getArchitectureOverview.mockResolvedValue({
        totalSections: 5,
        sections: [
          { title: 'System Architecture', position: 1 },
          { title: 'API Routes', position: 2 },
          { title: 'Data Model', position: 3 },
          { title: 'Deployment', position: 4 },
          { title: 'Agent Coordination', position: 5 }
          // Note: Security section is missing
        ],
        lastSync: new Date().toISOString()
      });

      const result = await proactiveReflection.triggerReflection();

      expect(result.sectionsKnown).toBe(5);
      expect(result.opportunitiesFound).toBeGreaterThan(0);
      expect(result.opportunities.some(o => o.type === 'missing_section')).toBe(true);
    });

    it('should store ImprovementOpportunity in Neo4j', async () => {
      const session = driver.session();
      try {
        const result = await session.run(`
          MATCH (o:ImprovementOpportunity)
          WHERE o.type = 'missing_section'
          AND o.description CONTAINS 'security'
          RETURN o.id as id, o.status as status, o.priority as priority
        `);

        expect(result.records.length).toBeGreaterThan(0);
        testData.opportunityId = result.records[0].get('id');
        expect(result.records[0].get('status')).toBe('proposed');
      } finally {
        await session.close();
      }
    });
  });

  describe('Step 2: Create Proposal (Kublai)', () => {
    it('should convert opportunity to ArchitectureProposal', async () => {
      const result = await stateMachine.createProposal(
        testData.opportunityId,
        'E2E-Test- Add Security Architecture Section',
        'Add comprehensive security documentation covering authentication, authorization, and data protection',
        'security'
      );

      expect(result.proposalId).toBeDefined();
      expect(result.status).toBe('proposed');
      testData.proposalId = result.proposalId;
    });

    it('should link proposal to opportunity via EVOLVES_INTO relationship', async () => {
      const session = driver.session();
      try {
        const result = await session.run(`
          MATCH (o:ImprovementOpportunity {id: $oppId})-[:EVOLVES_INTO]->(p:ArchitectureProposal {id: $propId})
          RETURN count(*) as count
        `, { oppId: testData.opportunityId, propId: testData.proposalId });

        expect(result.records[0].get('count').toNumber()).toBe(1);
      } finally {
        await session.close();
      }
    });

    it('should have initial status proposed and impl_status not_started', async () => {
      const status = await stateMachine.getStatus(testData.proposalId);

      expect(status.status).toBe('proposed');
      expect(status.implStatus).toBe('not_started');
    });
  });

  describe('Step 3: Vet Proposal (Ögedei)', () => {
    it('should transition proposal to under_review', async () => {
      const result = await stateMachine.transition(
        testData.proposalId,
        'under_review',
        'Ögedei beginning operational review'
      );

      expect(result.success).toBe(true);
      expect(result.newState).toBe('under_review');
    });

    it('should run OgedeiVetHandler.vetProposal() and assess operational impact', async () => {
      const result = await ogedeiVetHandler.vetProposal(testData.proposalId);

      expect(result.success).toBe(true);
      expect(result.vetting).toBeDefined();
      expect(result.vetting.operationalImpact).toBeDefined();
      expect(result.vetting.deploymentRisk).toBeDefined();
    });

    it('should store vetting result with HAS_VETTING relationship', async () => {
      const session = driver.session();
      try {
        const result = await session.run(`
          MATCH (p:ArchitectureProposal {id: $id})-[:HAS_VETTING]->(v:Vetting)
          RETURN v.assessment as assessment, v.vetted_by as vettedBy
        `, { id: testData.proposalId });

        expect(result.records.length).toBe(1);
        expect(result.records[0].get('vettedBy')).toBe('ogedei');

        const assessment = JSON.parse(result.records[0].get('assessment'));
        expect(assessment.operationalImpact).toBeDefined();
      } finally {
        await session.close();
      }
    });

    it('should approve proposal with recommendation', async () => {
      const result = await ogedeiVetHandler.approveProposal(
        testData.proposalId,
        'Low risk documentation addition - approved'
      );

      expect(result.success).toBe(true);
    });

    it('should have status approved', async () => {
      const status = await stateMachine.getStatus(testData.proposalId);

      expect(status.status).toBe('approved');
    });
  });

  describe('Step 4: Implement Proposal (Temüjin)', () => {
    it('should start implementation via TemujinImplHandler.implementProposal()', async () => {
      const result = await temujinImplHandler.implementProposal(testData.proposalId);

      expect(result.success).toBe(true);
      expect(result.implementationId).toBeDefined();
      expect(result.status).toBe('in_progress');
      testData.implementationId = result.implementationId;
    });

    it('should create IMPLEMENTED_BY relationship to Implementation node', async () => {
      const session = driver.session();
      try {
        const result = await session.run(`
          MATCH (p:ArchitectureProposal {id: $propId})-[:IMPLEMENTED_BY]->(i:Implementation {id: $implId})
          RETURN count(*) as count
        `, { propId: testData.proposalId, implId: testData.implementationId });

        expect(result.records[0].get('count').toNumber()).toBe(1);
      } finally {
        await session.close();
      }
    });

    it('should update implementation progress to 50%', async () => {
      const result = await temujinImplHandler.updateProgress(
        testData.implementationId,
        50,
        'Drafting security architecture documentation'
      );

      expect(result.success).toBe(true);
      expect(result.progress).toBe(50);
    });

    it('should update implementation progress to 100%', async () => {
      const result = await temujinImplHandler.updateProgress(
        testData.implementationId,
        100,
        'Security architecture documentation complete'
      );

      expect(result.success).toBe(true);
      expect(result.progress).toBe(100);
    });

    it('should complete implementation with summary', async () => {
      const result = await temujinImplHandler.completeImplementation(
        testData.implementationId,
        'Added comprehensive security architecture section covering OAuth2, JWT, RBAC, and data encryption'
      );

      expect(result.success).toBe(true);
      expect(result.status).toBe('completed');
    });

    it('should transition proposal to implemented', async () => {
      const result = await stateMachine.transition(
        testData.proposalId,
        'implemented',
        'Implementation completed by Temüjin'
      );

      expect(result.success).toBe(true);
      expect(result.newState).toBe('implemented');
    });

    it('should have implementation_status completed', async () => {
      const status = await stateMachine.getStatus(testData.proposalId);

      expect(status.status).toBe('implemented');
      expect(status.implStatus).toBe('completed');
    });
  });

  describe('Step 5: Validate (Kublai/System)', () => {
    it('should run validation checks on implementation', async () => {
      const result = await validationHandler.validateImplementation(testData.implementationId);

      expect(result.implementationId).toBe(testData.implementationId);
      expect(result.checks).toBeDefined();
      expect(result.checks.length).toBeGreaterThan(0);
    });

    it('should pass validation checks', async () => {
      const result = await validationHandler.validateImplementation(testData.implementationId);

      expect(result.passed).toBe(true);
      expect(result.failedChecks.length).toBe(0);
    });

    it('should create Validation node with PASSED status', async () => {
      const session = driver.session();
      try {
        const result = await session.run(`
          MATCH (v:Validation {implementation_id: $id})
          RETURN v.status as status, v.passed as passed
        `, { id: testData.implementationId });

        expect(result.records.length).toBeGreaterThan(0);
        expect(result.records[0].get('status')).toBe('passed');
        expect(result.records[0].get('passed')).toBe(true);
      } finally {
        await session.close();
      }
    });

    it('should update proposal status to validated', async () => {
      const status = await stateMachine.getStatus(testData.proposalId);

      expect(status.status).toBe('validated');
      expect(status.implStatus).toBe('validated');
    });
  });

  describe('Step 6: Sync (Guardrailed)', () => {
    it('should map proposal to target ARCHITECTURE.md section', async () => {
      const result = await mapper.mapProposalToSection(testData.proposalId);

      expect(result.success).toBe(true);
      expect(result.targetSection).toBeDefined();
    });

    it('should map security proposal to Security Architecture section', async () => {
      const result = await mapper.mapProposalToSection(testData.proposalId);

      expect(result.targetSection).toBe('Security Architecture');
    });

    it('ProposalMapper.checkCanSync() should allow validated proposals', async () => {
      const result = await mapper.checkCanSync(testData.proposalId);

      expect(result.allowed).toBe(true);
      expect(result.title).toBe('E2E-Test- Add Security Architecture Section');
    });

    it('ProposalMapper.checkCanSync() should block non-validated proposals', async () => {
      // Create a non-validated proposal
      const session = driver.session();
      let nonValidatedId;
      try {
        const createResult = await session.run(`
          CREATE (p:ArchitectureProposal {
            id: randomUUID(),
            title: 'E2E-Test- Non-validated Proposal',
            description: 'Test',
            status: 'implemented',
            implementation_status: 'completed'
          })
          RETURN p.id as id
        `);
        nonValidatedId = createResult.records[0].get('id');
      } finally {
        await session.close();
      }

      const result = await mapper.checkCanSync(nonValidatedId);

      expect(result.allowed).toBe(false);
      expect(result.reason).toContain('Guardrail');
      expect(result.reason).toContain('validated');
    });

    it('syncValidatedProposalsToArchitectureMd() should list ready proposals', async () => {
      const ready = await mapper.getReadyToSync();

      expect(ready.some(p => p.id === testData.proposalId)).toBe(true);
    });

    it('markSynced() should create SYNCED_TO relationship', async () => {
      const result = await mapper.markSynced(
        testData.proposalId,
        'E2E-Test- Security Architecture'
      );

      expect(result.success).toBe(true);
    });

    it('should have final status synced', async () => {
      const status = await stateMachine.getStatus(testData.proposalId);

      expect(status.status).toBe('synced');
    });

    it('should create SYNCED_TO relationship with timestamp', async () => {
      const session = driver.session();
      try {
        const result = await session.run(`
          MATCH (p:ArchitectureProposal {id: $id})-[r:SYNCED_TO]->(s:ArchitectureSection)
          RETURN r.synced_at as syncedAt, s.title as sectionTitle
        `, { id: testData.proposalId });

        expect(result.records.length).toBe(1);
        expect(result.records[0].get('syncedAt')).toBeDefined();
        expect(result.records[0].get('sectionTitle')).toBe('E2E-Test- Security Architecture');
      } finally {
        await session.close();
      }
    });
  });

  describe('State Machine Transition Validation', () => {
    it('should enforce valid state transitions', async () => {
      // Valid transitions
      expect(stateMachine.canTransition('proposed', 'under_review')).toBe(true);
      expect(stateMachine.canTransition('under_review', 'approved')).toBe(true);
      expect(stateMachine.canTransition('approved', 'implemented')).toBe(true);
      expect(stateMachine.canTransition('implemented', 'validated')).toBe(true);
      expect(stateMachine.canTransition('validated', 'synced')).toBe(true);
    });

    it('should reject invalid state transitions', async () => {
      // Invalid transitions
      expect(stateMachine.canTransition('proposed', 'approved')).toBe(false);
      expect(stateMachine.canTransition('proposed', 'implemented')).toBe(false);
      expect(stateMachine.canTransition('proposed', 'synced')).toBe(false);
      expect(stateMachine.canTransition('implemented', 'synced')).toBe(false); // Must be validated first
      expect(stateMachine.canTransition('synced', 'proposed')).toBe(false); // Terminal state
    });
  });

  describe('Complete Lifecycle Verification', () => {
    it('should verify complete proposal lifecycle in Neo4j', async () => {
      const session = driver.session();
      try {
        // Query the complete lifecycle
        const result = await session.run(`
          MATCH (o:ImprovementOpportunity {id: $oppId})-[:EVOLVES_INTO]->(p:ArchitectureProposal {id: $propId})
          OPTIONAL MATCH (p)-[:HAS_VETTING]->(v:Vetting)
          OPTIONAL MATCH (p)-[:IMPLEMENTED_BY]->(i:Implementation {id: $implId})
          OPTIONAL MATCH (p)-[r:SYNCED_TO]->(s:ArchitectureSection)
          RETURN {
            opportunityType: o.type,
            proposalStatus: p.status,
            proposalImplStatus: p.implementation_status,
            vettedBy: v.vetted_by,
            implementationStatus: i.status,
            implementationProgress: i.progress,
            syncedTo: s.title,
            syncedAt: r.synced_at
          } as lifecycle
        `, {
          oppId: testData.opportunityId,
          propId: testData.proposalId,
          implId: testData.implementationId
        });

        expect(result.records.length).toBe(1);
        const lifecycle = result.records[0].get('lifecycle');

        expect(lifecycle.opportunityType).toBe('missing_section');
        expect(lifecycle.proposalStatus).toBe('synced');
        expect(lifecycle.proposalImplStatus).toBe('validated');
        expect(lifecycle.vettedBy).toBe('ogedei');
        expect(lifecycle.implementationStatus).toBe('completed');
        expect(lifecycle.implementationProgress.toNumber()).toBe(100);
        expect(lifecycle.syncedTo).toBe('E2E-Test- Security Architecture');
        expect(lifecycle.syncedAt).toBeDefined();
      } finally {
        await session.close();
      }
    });
  });
});
