/**
 * Validation Handler Tests
 *
 * Tests for the validation handler that validates implementations
 * before they can sync to ARCHITECTURE.md.
 */

const { describe, it, expect, beforeAll, afterAll, jest } = require('@jest/globals');
const neo4j = require('neo4j-driver');
const { ValidationHandler } = require('../../src/workflow/validation');

describe('Validation Handler', () => {
  let driver;
  let validationHandler;
  const mockLogger = {
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn()
  };

  beforeAll(async () => {
    // Connect to test Neo4j instance
    const uri = process.env.NEO4J_URI || 'bolt://localhost:7687';
    const user = process.env.NEO4J_USER || 'neo4j';
    const password = process.env.NEO4J_PASSWORD || 'password';

    driver = neo4j.driver(uri, { auth: { user, password } });
    validationHandler = new ValidationHandler(driver, mockLogger);

    // Clean up any existing test data
    const session = driver.session();
    try {
      await session.run(`
        MATCH (p:ArchitectureProposal)
        WHERE p.title STARTS WITH 'Test-'
        DETACH DELETE p
      `);
      await session.run(`
        MATCH (i:Implementation)
        WHERE i.proposal_id STARTS WITH 'test-'
        DETACH DELETE i
      `);
      await session.run(`
        MATCH (v:Validation)
        WHERE v.implementation_id STARTS WITH 'test-'
        DETACH DELETE v
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
        WHERE p.title STARTS WITH 'Test-'
        DETACH DELETE p
      `);
      await session.run(`
        MATCH (i:Implementation)
        WHERE i.proposal_id STARTS WITH 'test-'
        DETACH DELETE i
      `);
      await session.run(`
        MATCH (v:Validation)
        WHERE v.implementation_id STARTS WITH 'test-'
        DETACH DELETE v
      `);
    } finally {
      await session.close();
    }

    if (driver) {
      await driver.close();
    }
  });

  describe('validateImplementation', () => {
    it('should pass validation for complete implementation', async () => {
      const session = driver.session();
      let implId;
      try {
        // Create proposal and implementation
        const result = await session.run(`
          CREATE (p:ArchitectureProposal {
            id: 'test-proposal-pass',
            title: 'Test- Pass Validation',
            description: 'Test',
            category: 'api'
          })
          CREATE (i:Implementation {
            id: 'test-impl-pass',
            proposal_id: 'test-proposal-pass',
            status: 'completed',
            progress: 100,
            summary: 'Implementation complete'
          })
          CREATE (p)-[:IMPLEMENTED_BY]->(i)
          RETURN i.id as implId
        `);
        implId = result.records[0].get('implId');

        const validationResult = await validationHandler.validateImplementation(implId);

        expect(validationResult.passed).toBe(true);
        expect(validationResult.implementationId).toBe(implId);
        expect(validationResult.checks.length).toBeGreaterThan(0);
        expect(mockLogger.info).toHaveBeenCalledWith(
          expect.stringContaining('[Validation] PASSED')
        );

        // Verify validation record was created
        const verifyResult = await session.run(`
          MATCH (v:Validation {implementation_id: $implId})
          RETURN v.passed as passed, v.status as status
        `, { implId });

        expect(verifyResult.records[0].get('passed')).toBe(true);
        expect(verifyResult.records[0].get('status')).toBe('passed');
      } finally {
        await session.close();
      }
    });

    it('should fail validation for incomplete implementation', async () => {
      const session = driver.session();
      let implId;
      try {
        const result = await session.run(`
          CREATE (p:ArchitectureProposal {
            id: 'test-proposal-fail',
            title: 'Test- Fail Validation',
            description: 'Test'
          })
          CREATE (i:Implementation {
            id: 'test-impl-fail',
            proposal_id: 'test-proposal-fail',
            status: 'in_progress',
            progress: 50
          })
          CREATE (p)-[:IMPLEMENTED_BY]->(i)
          RETURN i.id as implId
        `);
        implId = result.records[0].get('implId');

        const validationResult = await validationHandler.validateImplementation(implId);

        expect(validationResult.passed).toBe(false);
        expect(validationResult.failedChecks.length).toBeGreaterThan(0);
        expect(mockLogger.warn).toHaveBeenCalled();
      } finally {
        await session.close();
      }
    });

    it('should update proposal status on successful validation', async () => {
      const session = driver.session();
      let implId;
      try {
        const result = await session.run(`
          CREATE (p:ArchitectureProposal {
            id: 'test-proposal-status',
            title: 'Test- Status Update',
            description: 'Test',
            status: 'implemented',
            implementation_status: 'completed'
          })
          CREATE (i:Implementation {
            id: 'test-impl-status',
            proposal_id: 'test-proposal-status',
            status: 'completed',
            progress: 100,
            summary: 'Complete'
          })
          CREATE (p)-[:IMPLEMENTED_BY]->(i)
          RETURN i.id as implId
        `);
        implId = result.records[0].get('implId');

        await validationHandler.validateImplementation(implId);

        // Verify proposal was updated
        const verifyResult = await session.run(`
          MATCH (p:ArchitectureProposal {id: 'test-proposal-status'})
          RETURN p.status as status, p.implementation_status as implStatus
        `);

        expect(verifyResult.records[0].get('status')).toBe('validated');
        expect(verifyResult.records[0].get('implStatus')).toBe('validated');
      } finally {
        await session.close();
      }
    });

    it('should handle errors gracefully', async () => {
      const badDriver = {
        session: () => ({
          run: () => { throw new Error('Validation error'); },
          close: jest.fn()
        })
      };
      const badHandler = new ValidationHandler(badDriver, mockLogger);

      const result = await badHandler.validateImplementation('test-impl-id');

      expect(result.passed).toBe(false);
      expect(result.error).toBeDefined();
      expect(mockLogger.error).toHaveBeenCalled();
    });
  });

  describe('runChecks', () => {
    it('should return failed check when implementation not found', async () => {
      const checks = await validationHandler.runChecks('non-existent-impl');

      expect(checks.length).toBe(1);
      expect(checks[0].name).toBe('implementation_exists');
      expect(checks[0].passed).toBe(false);
      expect(checks[0].critical).toBe(true);
    });

    it('should check implementation completion status', async () => {
      const session = driver.session();
      try {
        await session.run(`
          CREATE (p:ArchitectureProposal {
            id: 'test-checks-proposal',
            title: 'Test- Checks',
            description: 'Test'
          })
          CREATE (i:Implementation {
            id: 'test-impl-checks',
            proposal_id: 'test-checks-proposal',
            status: 'completed',
            progress: 100
          })
          CREATE (p)-[:IMPLEMENTED_BY]->(i)
        `);

        const checks = await validationHandler.runChecks('test-impl-checks');

        const completionCheck = checks.find(c => c.name === 'implementation_complete');
        expect(completionCheck).toBeDefined();
        expect(completionCheck.passed).toBe(true);
      } finally {
        await session.close();
      }
    });

    it('should check progress completion', async () => {
      const session = driver.session();
      try {
        await session.run(`
          CREATE (p:ArchitectureProposal {
            id: 'test-progress-proposal',
            title: 'Test- Progress',
            description: 'Test'
          })
          CREATE (i:Implementation {
            id: 'test-impl-progress',
            proposal_id: 'test-progress-proposal',
            status: 'completed',
            progress: 100
          })
          CREATE (p)-[:IMPLEMENTED_BY]->(i)
        `);

        const checks = await validationHandler.runChecks('test-impl-progress');

        const progressCheck = checks.find(c => c.name === 'progress_complete');
        expect(progressCheck).toBeDefined();
        expect(progressCheck.passed).toBe(true);
      } finally {
        await session.close();
      }
    });

    it('should check for summary presence', async () => {
      const session = driver.session();
      try {
        await session.run(`
          CREATE (p:ArchitectureProposal {
            id: 'test-summary-proposal',
            title: 'Test- Summary',
            description: 'Test'
          })
          CREATE (i:Implementation {
            id: 'test-impl-summary',
            proposal_id: 'test-summary-proposal',
            status: 'completed',
            progress: 100,
            summary: 'This is a completion summary'
          })
          CREATE (p)-[:IMPLEMENTED_BY]->(i)
        `);

        const checks = await validationHandler.runChecks('test-impl-summary');

        const summaryCheck = checks.find(c => c.name === 'has_summary');
        expect(summaryCheck).toBeDefined();
        expect(summaryCheck.passed).toBe(true);
      } finally {
        await session.close();
      }
    });

    it('should fail progress check when progress < 100', async () => {
      const session = driver.session();
      try {
        await session.run(`
          CREATE (p:ArchitectureProposal {
            id: 'test-low-progress-proposal',
            title: 'Test- Low Progress',
            description: 'Test'
          })
          CREATE (i:Implementation {
            id: 'test-impl-low-progress',
            proposal_id: 'test-low-progress-proposal',
            status: 'completed',
            progress: 75
          })
          CREATE (p)-[:IMPLEMENTED_BY]->(i)
        `);

        const checks = await validationHandler.runChecks('test-impl-low-progress');

        const progressCheck = checks.find(c => c.name === 'progress_complete');
        expect(progressCheck.passed).toBe(false);
      } finally {
        await session.close();
      }
    });

    it('should handle errors gracefully', async () => {
      const badDriver = {
        session: () => ({
          run: () => { throw new Error('Check failed'); },
          close: jest.fn()
        })
      };
      const badHandler = new ValidationHandler(badDriver, mockLogger);

      const checks = await badHandler.runChecks('test-impl');

      expect(checks.length).toBe(1);
      expect(checks[0].name).toBe('validation_error');
      expect(checks[0].passed).toBe(false);
      expect(checks[0].critical).toBe(true);
    });
  });

  describe('runCategoryCheck', () => {
    it('should run API category check', async () => {
      const check = await validationHandler.runCategoryCheck('test-impl', 'api');

      expect(check.name).toBe('api_endpoints_tested');
      expect(check.passed).toBe(true);
    });

    it('should run database category check', async () => {
      const check = await validationHandler.runCategoryCheck('test-impl', 'database');

      expect(check.name).toBe('schema_validated');
      expect(check.passed).toBe(true);
    });

    it('should run security category check', async () => {
      const check = await validationHandler.runCategoryCheck('test-impl', 'security');

      expect(check.name).toBe('security_audit_passed');
      expect(check.passed).toBe(true);
    });

    it('should run deployment category check', async () => {
      const check = await validationHandler.runCategoryCheck('test-impl', 'deployment');

      expect(check.name).toBe('deployment_verified');
      expect(check.passed).toBe(true);
    });

    it('should return generic check for unknown category', async () => {
      const check = await validationHandler.runCategoryCheck('test-impl', 'unknown');

      expect(check.name).toBe('category_check');
      expect(check.passed).toBe(true);
      expect(check.description).toContain('unknown');
    });

    it('should handle null/undefined category', async () => {
      const check = await validationHandler.runCategoryCheck('test-impl', null);

      expect(check.name).toBe('category_check');
      expect(check.passed).toBe(true);
    });
  });

  describe('getValidation', () => {
    it('should return validation for implementation', async () => {
      const session = driver.session();
      try {
        await session.run(`
          CREATE (v:Validation {
            id: 'test-validation-get',
            implementation_id: 'test-impl-get',
            passed: true,
            status: 'passed',
            validated_at: datetime(),
            checks: '[{"name":"test","passed":true}]'
          })
        `);

        const validation = await validationHandler.getValidation('test-impl-get');

        expect(validation).not.toBeNull();
        expect(validation.implementationId).toBe('test-impl-get');
        expect(validation.passed).toBe(true);
        expect(validation.status).toBe('passed');
        expect(Array.isArray(validation.checks)).toBe(true);
      } finally {
        await session.close();
      }
    });

    it('should return null when no validation exists', async () => {
      const validation = await validationHandler.getValidation('non-existent-impl');

      expect(validation).toBeNull();
    });

    it('should return most recent validation', async () => {
      const session = driver.session();
      try {
        // Create multiple validations
        await session.run(`
          CREATE (v1:Validation {
            id: 'test-validation-old',
            implementation_id: 'test-impl-multi',
            passed: false,
            status: 'failed',
            validated_at: datetime() - duration('P1D'),
            checks: '[]'
          })
          CREATE (v2:Validation {
            id: 'test-validation-new',
            implementation_id: 'test-impl-multi',
            passed: true,
            status: 'passed',
            validated_at: datetime(),
            checks: '[]'
          })
        `);

        const validation = await validationHandler.getValidation('test-impl-multi');

        expect(validation.passed).toBe(true);
        expect(validation.id).toBe('test-validation-new');
      } finally {
        await session.close();
      }
    });

    it('should handle errors gracefully', async () => {
      const badDriver = {
        session: () => ({
          run: () => { throw new Error('Query failed'); },
          close: jest.fn()
        })
      };
      const badHandler = new ValidationHandler(badDriver, mockLogger);

      const validation = await badHandler.getValidation('test-impl');

      expect(validation).toBeNull();
      expect(mockLogger.error).toHaveBeenCalled();
    });
  });

  describe('getReadyToValidate', () => {
    beforeAll(async () => {
      const session = driver.session();
      try {
        // Create completed implementations without validation
        await session.run(`
          CREATE (p1:ArchitectureProposal {
            id: 'test-ready-val-proposal-1',
            title: 'Test- Ready One',
            description: 'Test'
          })
          CREATE (i1:Implementation {
            id: 'test-ready-val-1',
            proposal_id: 'test-ready-val-proposal-1',
            status: 'completed',
            completed_at: datetime()
          })
          CREATE (p1)-[:IMPLEMENTED_BY]->(i1)
        `);

        // Create completed implementation with validation
        await session.run(`
          CREATE (p2:ArchitectureProposal {
            id: 'test-ready-val-proposal-2',
            title: 'Test- Already Validated',
            description: 'Test'
          })
          CREATE (i2:Implementation {
            id: 'test-ready-val-2',
            proposal_id: 'test-ready-val-proposal-2',
            status: 'completed',
            completed_at: datetime()
          })
          CREATE (v:Validation {
            id: 'test-validation-existing',
            implementation_id: 'test-ready-val-2',
            passed: true,
            validated_at: datetime()
          })
          CREATE (p2)-[:IMPLEMENTED_BY]->(i2)
          CREATE (v)-[:VALIDATES]->(i2)
        `);
      } finally {
        await session.close();
      }
    });

    it('should return completed implementations without validation', async () => {
      const ready = await validationHandler.getReadyToValidate();

      expect(ready.some(r => r.id === 'test-ready-val-1')).toBe(true);
    });

    it('should not include already validated implementations', async () => {
      const ready = await validationHandler.getReadyToValidate();

      expect(ready.some(r => r.id === 'test-ready-val-2')).toBe(false);
    });

    it('should include proposal details', async () => {
      const ready = await validationHandler.getReadyToValidate();

      const testItem = ready.find(r => r.id === 'test-ready-val-1');
      if (testItem) {
        expect(testItem.proposalId).toBe('test-ready-val-proposal-1');
        expect(testItem.proposalTitle).toBe('Test- Ready One');
      }
    });

    it('should handle errors gracefully', async () => {
      const badDriver = {
        session: () => ({
          run: () => { throw new Error('Query failed'); },
          close: jest.fn()
        })
      };
      const badHandler = new ValidationHandler(badDriver, mockLogger);

      const result = await badHandler.getReadyToValidate();

      expect(result).toEqual([]);
      expect(mockLogger.error).toHaveBeenCalled();
    });
  });

  describe('revalidate', () => {
    it('should re-run validation for implementation', async () => {
      const session = driver.session();
      try {
        await session.run(`
          CREATE (p:ArchitectureProposal {
            id: 'test-revalidate-proposal',
            title: 'Test- Revalidate',
            description: 'Test'
          })
          CREATE (i:Implementation {
            id: 'test-impl-revalidate',
            proposal_id: 'test-revalidate-proposal',
            status: 'completed',
            progress: 100,
            summary: 'Complete'
          })
          CREATE (p)-[:IMPLEMENTED_BY]->(i)
        `);

        const result = await validationHandler.revalidate('test-impl-revalidate');

        expect(result.implementationId).toBe('test-impl-revalidate');
        expect(result.checks).toBeDefined();
      } finally {
        await session.close();
      }
    });

    it('should create new validation record on revalidate', async () => {
      const session = driver.session();
      try {
        // Create existing validation
        await session.run(`
          CREATE (p:ArchitectureProposal {
            id: 'test-revalidate-new-proposal',
            title: 'Test- Revalidate New',
            description: 'Test'
          })
          CREATE (i:Implementation {
            id: 'test-impl-revalidate-new',
            proposal_id: 'test-revalidate-new-proposal',
            status: 'completed',
            progress: 100,
            summary: 'Complete'
          })
          CREATE (v:Validation {
            id: 'old-validation',
            implementation_id: 'test-impl-revalidate-new',
            passed: false,
            validated_at: datetime()
          })
          CREATE (p)-[:IMPLEMENTED_BY]->(i)
        `);

        await validationHandler.revalidate('test-impl-revalidate-new');

        // Should have multiple validations now
        const result = await session.run(`
          MATCH (v:Validation {implementation_id: 'test-impl-revalidate-new'})
          RETURN count(v) as count
        `);

        expect(result.records[0].get('count').toNumber()).toBeGreaterThan(1);
      } finally {
        await session.close();
      }
    });
  });
});
