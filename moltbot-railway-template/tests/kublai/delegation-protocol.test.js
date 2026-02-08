/**
 * Delegation Protocol Integration Tests
 *
 * Tests the complete workflow integration:
 *   Reflection Opportunity → Proposal → Vetting → Approval →
 *   Implementation → Validation → Sync
 */

const { DelegationProtocol } = require('../../src/kublai/delegation-protocol');
const { ProactiveReflection } = require('../../src/kublai/proactive-reflection');
const { ArchitectureIntrospection } = require('../../src/kublai/architecture-introspection');
const { ProposalStateMachine } = require('../../src/workflow/proposal-states');
const { ProposalMapper } = require('../../src/workflow/proposal-mapper');
const { ValidationHandler } = require('../../src/workflow/validation');
const { OgedeiVetHandler } = require('../../src/agents/ogedei/vet-handler');
const { TemujinImplHandler } = require('../../src/agents/temujin/impl-handler');

// Mock logger
const mockLogger = {
  info: jest.fn(),
  warn: jest.fn(),
  error: jest.fn()
};

// Mock Neo4j driver
const createMockSession = (returnValue = []) => ({
  run: jest.fn().mockResolvedValue(returnValue),
  close: jest.fn().mockResolvedValue(undefined)
});

const createMockDriver = (session) => ({
  session: jest.fn().mockReturnValue(session)
});

describe('DelegationProtocol', () => {
  let protocol;
  let mockDriver;
  let mockSession;

  beforeEach(() => {
    mockSession = createMockSession({ records: [] });
    mockDriver = createMockDriver(mockSession);

    // Create protocol with minimal mock handlers
    protocol = new DelegationProtocol(mockDriver, mockLogger, {
      autoVet: false,
      autoImplement: false,
      autoValidate: false,
      autoSync: false
    });

    jest.clearAllMocks();
  });

  describe('Configuration', () => {
    it('should initialize with default configuration', () => {
      const defaultProtocol = new DelegationProtocol(mockDriver, mockLogger);

      expect(defaultProtocol.config.autoVet).toBe(true);
      expect(defaultProtocol.config.autoImplement).toBe(true);
      expect(defaultProtocol.config.autoValidate).toBe(true);
      expect(defaultProtocol.config.autoSync).toBe(true);
    });

    it('should accept custom configuration', () => {
      const customProtocol = new DelegationProtocol(mockDriver, mockLogger, {
        autoVet: false,
        autoImplement: false,
        autoValidate: false,
        autoSync: false,
        requireManualApproval: true
      });

      expect(customProtocol.config.autoVet).toBe(false);
      expect(customProtocol.config.requireManualApproval).toBe(true);
    });
  });

  describe('Proposal Title Generation', () => {
    it('should generate title for missing_section opportunity', () => {
      const opp = { type: 'missing_section', suggestedSection: 'API Routes' };
      const title = protocol.generateProposalTitle(opp);

      expect(title).toBe('Add Missing Architecture Section: API Routes');
    });

    it('should generate title for stale_sync opportunity', () => {
      const opp = { type: 'stale_sync' };
      const title = protocol.generateProposalTitle(opp);

      expect(title).toBe('Refresh Architecture Documentation');
    });

    it('should generate title for unknown opportunity type', () => {
      const opp = { type: 'unknown_type' };
      const title = protocol.generateProposalTitle(opp);

      expect(title).toBe('Architecture Improvement');
    });
  });

  describe('Category Inference', () => {
    it('should infer api category from type', () => {
      const opp = { type: 'api_gap', description: '' };
      expect(protocol.inferCategory(opp)).toBe('api');
    });

    it('should infer database category from description', () => {
      const opp = { type: '', description: 'Update database schema' };
      expect(protocol.inferCategory(opp)).toBe('database');
    });

    it('should infer security category', () => {
      const opp = { type: '', description: 'Add authentication' };
      expect(protocol.inferCategory(opp)).toBe('security');
    });

    it('should default to general category', () => {
      const opp = { type: '', description: 'Something else' };
      expect(protocol.inferCategory(opp)).toBe('general');
    });
  });

  describe('Integration Flow', () => {
    it('should handle missing handlers gracefully', async () => {
      const result = await protocol.createProposalsFromOpportunities();

      expect(result.success).toBe(false);
      expect(result.error).toBe('Missing handlers');
    });

    it('should check if opportunity has existing proposal', async () => {
      mockSession.run.mockResolvedValue({
        records: [{ get: () => ({ toNumber: () => 1 }) }]
      });

      const hasProposal = await protocol.opportunityHasProposal('opp-123');

      expect(hasProposal).toBe(true);
      expect(mockSession.run).toHaveBeenCalledWith(
        expect.stringContaining('MATCH (o:ImprovementOpportunity'),
        { id: 'opp-123' }
      );
    });
  });

  describe('Workflow Status', () => {
    it('should return null when proposal not found', async () => {
      mockSession.run.mockResolvedValue({ records: [] });

      const status = await protocol.getWorkflowStatus('non-existent');

      expect(status).toBeNull();
    });

    it('should return complete workflow status', async () => {
      mockSession.run.mockResolvedValue({
        records: [{
          get: (field) => {
            const values = {
              status: 'approved',
              implStatus: 'in_progress',
              vettedBy: 'ogedei',
              vettedAt: '2024-01-01',
              implementationId: 'impl-123',
              implRecordStatus: 'in_progress',
              progress: 50,
              validationPassed: null,
              syncedTo: null
            };
            return values[field];
          }
        }]
      });

      const status = await protocol.getWorkflowStatus('prop-123');

      expect(status).toEqual({
        proposalId: 'prop-123',
        status: 'approved',
        implementationStatus: 'in_progress',
        vettedBy: 'ogedei',
        vettedAt: '2024-01-01',
        implementationId: 'impl-123',
        implementationRecordStatus: 'in_progress',
        progress: 50,
        validationPassed: null,
        syncedTo: null
      });
    });
  });
});

describe('End-to-End Workflow Integration', () => {
  // Integration test with real handler mocks
  let protocol;
  let mockDriver;
  let mockProactiveReflection;
  let mockStateMachine;
  let mockMapper;
  let mockVetHandler;
  let mockImplHandler;
  let mockValidationHandler;

  beforeEach(() => {
    // Create mock handlers
    mockProactiveReflection = {
      getOpportunities: jest.fn(),
      markOpportunityAddressed: jest.fn()
    };

    mockStateMachine = {
      createProposal: jest.fn(),
      transition: jest.fn(),
      getStatus: jest.fn(),
      updateImplementationStatus: jest.fn()
    };

    mockMapper = {
      mapProposalToSection: jest.fn(),
      checkCanSync: jest.fn(),
      markSynced: jest.fn(),
      getReadyToSync: jest.fn()
    };

    mockVetHandler = {
      vetProposal: jest.fn(),
      approveProposal: jest.fn(),
      rejectProposal: jest.fn(),
      getPendingVetting: jest.fn()
    };

    mockImplHandler = {
      implementProposal: jest.fn(),
      updateProgress: jest.fn(),
      completeImplementation: jest.fn(),
      getImplementation: jest.fn(),
      getReadyToImplement: jest.fn(),
      getActiveImplementations: jest.fn()
    };

    mockValidationHandler = {
      validateImplementation: jest.fn(),
      getReadyToValidate: jest.fn()
    };

    mockDriver = {
      session: jest.fn().mockReturnValue({
        run: jest.fn().mockResolvedValue({ records: [] }),
        close: jest.fn().mockResolvedValue(undefined)
      })
    };

    protocol = new DelegationProtocol(mockDriver, mockLogger, {
      proactiveReflection: mockProactiveReflection,
      stateMachine: mockStateMachine,
      mapper: mockMapper,
      vetHandler: mockVetHandler,
      implHandler: mockImplHandler,
      validationHandler: mockValidationHandler,
      autoVet: true,
      autoImplement: true,
      autoValidate: true,
      autoSync: true
    });
  });

  describe('Stage 1: Opportunity to Proposal', () => {
    it('should convert opportunities to proposals', async () => {
      const opportunities = [
        { id: 'opp-1', type: 'missing_section', description: 'Missing API docs', priority: 'high' }
      ];

      mockProactiveReflection.getOpportunities.mockResolvedValue(opportunities);
      mockStateMachine.createProposal.mockResolvedValue({ proposalId: 'prop-123' });
      mockVetHandler.vetProposal.mockResolvedValue({
        success: true,
        recommendation: 'approve',
        vetting: { deploymentRisk: 'low' }
      });

      const result = await protocol.createProposalsFromOpportunities();

      expect(mockStateMachine.createProposal).toHaveBeenCalledWith(
        'opp-1',
        'Add Missing Architecture Section',
        'Missing API docs',
        'general'
      );
      expect(result.success).toBe(true);
      expect(result.created).toBe(1);
    });
  });

  describe('Stage 2: Proposal Vetting', () => {
    it('should route proposal to Ögedei and handle approval', async () => {
      mockStateMachine.transition.mockResolvedValue({ success: true });
      mockVetHandler.vetProposal.mockResolvedValue({
        success: true,
        recommendation: 'approve',
        vetting: { deploymentRisk: 'low', notes: '' }
      });
      mockStateMachine.getStatus.mockResolvedValue({ status: 'approved' });
      mockImplHandler.implementProposal.mockResolvedValue({
        success: true,
        implementationId: 'impl-123'
      });

      const result = await protocol.routeToVetting('prop-123');

      expect(mockVetHandler.vetProposal).toHaveBeenCalledWith('prop-123');
      expect(mockVetHandler.approveProposal).toHaveBeenCalled();
      expect(result.success).toBe(true);
    });

    it('should handle rejection from Ögedei', async () => {
      mockStateMachine.transition.mockResolvedValue({ success: true });
      mockVetHandler.vetProposal.mockResolvedValue({
        success: true,
        recommendation: 'reject',
        vetting: { deploymentRisk: 'critical', notes: 'Too risky' }
      });

      const result = await protocol.routeToVetting('prop-123');

      expect(mockVetHandler.rejectProposal).toHaveBeenCalled();
      expect(result.recommendation).toBe('reject');
    });
  });

  describe('Stage 3: Implementation', () => {
    it('should route approved proposal to Temüjin', async () => {
      mockStateMachine.getStatus.mockResolvedValue({ status: 'approved' });
      mockImplHandler.implementProposal.mockResolvedValue({
        success: true,
        implementationId: 'impl-123'
      });
      mockStateMachine.transition.mockResolvedValue({ success: true });

      const result = await protocol.routeToImplementation('prop-123');

      expect(mockImplHandler.implementProposal).toHaveBeenCalledWith('prop-123');
      expect(result.success).toBe(true);
      expect(result.implementationId).toBe('impl-123');
    });

    it('should reject non-approved proposals', async () => {
      mockStateMachine.getStatus.mockResolvedValue({ status: 'proposed' });

      const result = await protocol.routeToImplementation('prop-123');

      expect(result.success).toBe(false);
      expect(result.error).toContain('must be approved');
    });
  });

  describe('Stage 4: Validation and Sync', () => {
    it('should complete and validate implementation', async () => {
      mockImplHandler.completeImplementation.mockResolvedValue({ success: true });
      mockImplHandler.getImplementation.mockResolvedValue({
        proposalId: 'prop-123'
      });
      mockValidationHandler.validateImplementation.mockResolvedValue({
        passed: true,
        failedChecks: []
      });
      mockStateMachine.transition.mockResolvedValue({ success: true });

      const result = await protocol.completeAndValidate('impl-123', 'Done!');

      expect(mockImplHandler.completeImplementation).toHaveBeenCalledWith('impl-123', 'Done!');
      expect(mockValidationHandler.validateImplementation).toHaveBeenCalledWith('impl-123');
      expect(result.success).toBe(true);
      expect(result.status).toBe('validated');
    });

    it('should sync validated proposal to architecture', async () => {
      mockMapper.checkCanSync.mockResolvedValue({ allowed: true });
      mockMapper.markSynced.mockResolvedValue({ success: true });
      mockStateMachine.transition.mockResolvedValue({ success: true });

      // Mock getting target section
      mockDriver.session.mockReturnValue({
        run: jest.fn().mockResolvedValue({
          records: [{ get: () => 'API Routes' }]
        }),
        close: jest.fn()
      });

      const result = await protocol.syncToArchitecture('prop-123');

      expect(mockMapper.checkCanSync).toHaveBeenCalledWith('prop-123');
      expect(result.success).toBe(true);
    });

    it('should block sync if guardrail check fails', async () => {
      mockMapper.checkCanSync.mockResolvedValue({
        allowed: false,
        reason: 'Proposal not validated'
      });

      const result = await protocol.syncToArchitecture('prop-123');

      expect(result.success).toBe(false);
      expect(result.blockedByGuardrail).toBe(true);
      expect(result.error).toBe('Proposal not validated');
    });
  });
});
