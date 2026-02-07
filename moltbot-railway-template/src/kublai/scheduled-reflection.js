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
   * Start the scheduled reflection task
   */
  start() {
    if (this.job) {
      this.logger.warn('[ScheduledReflection] Already running');
      return;
    }

    // Weekly reflection: Every Sunday at 8 PM
    this.job = cron.schedule('0 20 * * 0', () => this.weeklyReflection(), {
      timezone: 'America/New_York'
    });

    this.logger.info('[ScheduledReflection] Started weekly reflection trigger (Sundays at 8 PM ET)');
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
   */
  async weeklyReflection() {
    this.logger.info('[Kublai] Running weekly architecture reflection...');

    try {
      const result = await this.reflection.triggerReflection();

      this.logger.info(`[Kublai] Reflection complete:`, {
        sectionsKnown: result.sectionsKnown,
        opportunitiesFound: result.opportunitiesFound
      });

      // If opportunities found, log them
      if (result.opportunitiesFound > 0) {
        this.logger.info(`[Kublai] Opportunities:`, result.opportunities);
      }
    } catch (error) {
      this.logger.error(`[Kublai] Weekly reflection failed: ${error.message}`);
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
