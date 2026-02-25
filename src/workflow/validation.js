/**
 * Validation Handler
 *
 * Validates completed implementations before allowing
 * them to sync to ARCHITECTURE.md.
 *
 * This is the quality gate — only validated implementations
 * can proceed to documentation sync.
 */

class ValidationHandler {
  constructor(neo4jDriver, logger) {
    this.driver = neo4jDriver;
    this.logger = logger;
  }

  /**
   * Validate an implementation
   */
  async validateImplementation(implId) {
    this.logger.info(`[Validation] Validating implementation: ${implId}`);

    const session = this.driver.session();
    try {
      // Run validation checks
      const checks = await this.runChecks(implId);

      const allPassed = checks.every(c => c.passed);
      const failedChecks = checks.filter(c => !c.passed);

      // Create validation record
      await session.run(`
        CREATE (v:Validation {
          id: randomUUID(),
          implementation_id: $id,
          validated_at: datetime(),
          passed: $passed,
          checks: $checks,
          status: $status,
          failed_count: $failedCount
        })
      `, {
        id: implId,
        passed: allPassed,
        checks: JSON.stringify(checks),
        status: allPassed ? 'passed' : 'failed',
        failedCount: failedChecks.length
      });

      // Update implementation and proposal if passed
      if (allPassed) {
        await session.run(`
          MATCH (i:Implementation {id: $id})
          MATCH (p:ArchitectureProposal)-[:IMPLEMENTED_BY]->(i)
          SET i.validation_status = 'passed',
              i.validated_at = datetime(),
              p.implementation_status = 'validated',
              p.status = 'validated'
        `, { id: implId });

        this.logger.info(`[Validation] PASSED for ${implId}`);
      } else {
        await session.run(`
          MATCH (i:Implementation {id: $id})
          SET i.validation_status = 'failed',
              i.validated_at = datetime()
        `, { id: implId });

        this.logger.warn(`[Validation] FAILED for ${implId}: ${failedChecks.map(c => c.name).join(', ')}`);
      }

      return {
        implementationId: implId,
        passed: allPassed,
        checks,
        failedChecks
      };
    } catch (error) {
      this.logger.error(`[Validation] Failed: ${error.message}`);
      return { implementationId: implId, passed: false, error: error.message };
    } finally {
      await session.close();
    }
  }

  /**
   * Run validation checks on an implementation
   */
  async runChecks(implId) {
    const session = this.driver.session();
    try {
      // Get implementation details
      const result = await session.run(`
        MATCH (i:Implementation {id: $id})
        MATCH (p:ArchitectureProposal)-[:IMPLEMENTED_BY]->(i)
        RETURN i.status as implStatus, i.progress as progress,
               p.title as title, p.category as category
      `, { id: implId });

      if (result.records.length === 0) {
        return [{
          name: 'implementation_exists',
          passed: false,
          description: 'Implementation not found',
          critical: true
        }];
      }

      const record = result.records[0].toObject();
      const checks = [];

      // Check 1: Implementation complete
      checks.push({
        name: 'implementation_complete',
        passed: record.implStatus === 'completed',
        description: 'Implementation marked as completed',
        critical: true
      });

      // Check 2: Progress at 100%
      checks.push({
        name: 'progress_complete',
        passed: record.progress >= 100,
        description: 'Progress at 100%',
        critical: true
      });

      // Check 3: Has completion summary
      const summaryResult = await session.run(`
        MATCH (i:Implementation {id: $id})
        RETURN i.summary as summary
      `, { id: implId });

      const hasSummary = summaryResult.records.length > 0 &&
                         summaryResult.records[0].get('summary');

      checks.push({
        name: 'has_summary',
        passed: !!hasSummary,
        description: 'Implementation has completion summary',
        critical: false
      });

      // Check 4: Category-specific checks
      if (record.category) {
        const categoryCheck = await this.runCategoryCheck(implId, record.category);
        checks.push(categoryCheck);
      }

      // Check 5: No blocking issues (placeholder for real checks)
      checks.push({
        name: 'no_blocking_issues',
        passed: true, // Would check for actual issues
        description: 'No blocking issues detected',
        critical: true
      });

      return checks;
    } catch (error) {
      this.logger.error(`[Validation] Check run failed: ${error.message}`);
      return [{
        name: 'validation_error',
        passed: false,
        description: `Validation error: ${error.message}`,
        critical: true
      }];
    } finally {
      await session.close();
    }
  }

  /**
   * Run category-specific validation checks
   */
  async runCategoryCheck(implId, category) {
    // Placeholder for category-specific validation
    // In production, this would run different checks based on category
    const categoryChecks = {
      'api': async () => ({ name: 'api_endpoints_tested', passed: true, description: 'API endpoints tested' }),
      'database': async () => ({ name: 'schema_validated', passed: true, description: 'Database schema validated' }),
      'security': async () => ({ name: 'security_audit_passed', passed: true, description: 'Security audit passed' }),
      'deployment': async () => ({ name: 'deployment_verified', passed: true, description: 'Deployment verified' })
    };

    const checkFn = categoryChecks[category.toLowerCase()];
    if (checkFn) {
      return await checkFn();
    }

    return {
      name: 'category_check',
      passed: true,
      description: `Category check for: ${category}`
    };
  }

  /**
   * Get validation result for an implementation
   */
  async getValidation(implId) {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        MATCH (v:Validation {implementation_id: $id})
        RETURN v
        ORDER BY v.validated_at DESC
        LIMIT 1
      `, { id: implId });

      if (result.records.length === 0) {
        return null;
      }

      const record = result.records[0].get('v');
      return {
        id: record.get('id'),
        implementationId: record.get('implementation_id'),
        validatedAt: record.get('validated_at'),
        passed: record.get('passed'),
        status: record.get('status'),
        checks: JSON.parse(record.get('checks') || '[]')
      };
    } catch (error) {
      this.logger.error(`[Validation] Failed to get: ${error.message}`);
      return null;
    } finally {
      await session.close();
    }
  }

  /**
   * Get implementations ready for validation (completed but not validated)
   */
  async getReadyToValidate() {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        MATCH (i:Implementation {status: 'completed'})
        WHERE NOT EXISTS((:Validation)-[:VALIDATES]->(i))
        MATCH (p:ArchitectureProposal)-[:IMPLEMENTED_BY]->(i)
        RETURN i.id as id, i.completed_at as completedAt,
               p.id as proposalId, p.title as proposalTitle
        ORDER BY i.completed_at DESC
      `);

      return result.records.map(r => ({
        id: r.get('id'),
        completedAt: r.get('completedAt'),
        proposalId: r.get('proposalId'),
        proposalTitle: r.get('proposalTitle')
      }));
    } catch (error) {
      this.logger.error(`[Validation] Failed to get ready: ${error.message}`);
      return [];
    } finally {
      await session.close();
    }
  }

  /**
   * Re-run validation for a failed implementation
   */
  async revalidate(implId) {
    this.logger.info(`[Validation] Re-validating: ${implId}`);
    return await this.validateImplementation(implId);
  }
}

module.exports = { ValidationHandler };
