/**
 * Scheduled Reflection for Kublai
 *
 * Triggers periodic proactive architecture reflection.
 * Runs weekly to continuously identify improvement opportunities.
 */

const cron = require('node-cron');

class ScheduledReflection {
  constructor(proactiveReflection, logger) {
    this.reflection = proactiveReflection;
    this.logger = logger;
    this.job = null;
  }

  /**
   * Start the scheduled reflection task.
   * Checks for missed reflections on startup (catch-up if > 7 days since last).
   */
  async start() {
    if (this.job) {
      this.logger.warn('[ScheduledReflection] Already running');
      return;
    }

    // Check if we missed a scheduled reflection (e.g., gateway restart)
    try {
      const lastRun = await this.getLastReflectionTime();
      if (lastRun) {
        const daysSince = (Date.now() - new Date(lastRun).getTime()) / (1000 * 60 * 60 * 24);
        if (daysSince > 7) {
          this.logger.info(`[ScheduledReflection] Last reflection was ${Math.floor(daysSince)} days ago, triggering catch-up...`);
          await this.weeklyReflection();
        }
      }
    } catch (err) {
      this.logger.warn(`[ScheduledReflection] Catch-up check failed: ${err.message}`);
    }

    // Weekly reflection: Every Sunday at 8 PM
    this.job = cron.schedule('0 20 * * 0', () => this.weeklyReflection(), {
      timezone: 'America/New_York'
    });

    this.logger.info('[ScheduledReflection] Started weekly reflection trigger (Sundays at 8 PM ET)');
  }

  /**
   * Get the timestamp of the last reflection from Neo4j
   */
  async getLastReflectionTime() {
    const session = this.reflection.driver.session();
    try {
      const result = await session.run(`
        MATCH (o:ImprovementOpportunity)
        RETURN max(o.last_seen) as lastRun
      `);
      return result.records[0]?.get('lastRun') || null;
    } catch (err) {
      return null;
    } finally {
      await session.close();
    }
  }

  /**
   * Stop the scheduled reflection task
   */
  stop() {
    if (this.job) {
      this.job.stop();
      this.job = null;
      this.logger.info('[ScheduledReflection] Stopped');
    }
  }

  /**
   * Execute weekly reflection
   * @param {Object} options - Optional configuration
   * @param {Function} options.onOpportunitiesFound - Callback when opportunities are found
   */
  async weeklyReflection(options = {}) {
    this.logger.info('[Kublai] Running weekly architecture reflection...');

    try {
      const result = await this.reflection.triggerReflection();

      this.logger.info(`[Kublai] Reflection complete:`, {
        sectionsKnown: result.sectionsKnown,
        opportunitiesFound: result.opportunitiesFound
      });

      // If opportunities found, log them and optionally trigger callback
      if (result.opportunitiesFound > 0) {
        this.logger.info(`[Kublai] Opportunities:`, result.opportunities);

        // Call the callback if provided (e.g., to trigger delegation protocol)
        if (options.onOpportunitiesFound && typeof options.onOpportunitiesFound === 'function') {
          try {
            await options.onOpportunitiesFound(result.opportunities);
          } catch (callbackError) {
            this.logger.error(`[Kublai] Opportunity callback failed: ${callbackError.message}`);
          }
        }
      }

      return result;
    } catch (error) {
      this.logger.error(`[Kublai] Weekly reflection failed: ${error.message}`);
      return { error: error.message, sectionsKnown: 0, opportunitiesFound: 0 };
    }
  }

  /**
   * Trigger an immediate reflection (for testing or manual invocation)
   */
  async triggerNow() {
    this.logger.info('[Kublai] Triggering immediate reflection...');
    return await this.weeklyReflection();
  }
}

module.exports = { ScheduledReflection };
