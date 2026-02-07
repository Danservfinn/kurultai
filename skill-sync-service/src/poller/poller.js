/**
 * GitHub Poller
 * Fallback polling mechanism for skill synchronization
 */

const cron = require('node-cron');
const { SkillValidator } = require('../validators/skill');
const { SkillDeployer } = require('../deployer/deployer');
const { AuditLogger } = require('../audit/logger');
const constants = require('../config/constants');

class GitHubPoller {
  constructor(options = {}) {
    this.github = options.github; // Octokit instance
    this.owner = options.owner || constants.GITHUB_OWNER;
    this.repo = options.repo || constants.GITHUB_REPO;
    this.interval = options.interval || constants.POLLING_INTERVAL_MIN;
    this.validator = options.validator || new SkillValidator();
    this.deployer = options.deployer || new SkillDeployer();
    this.audit = options.audit || new AuditLogger();
    this.logger = options.logger || console;

    this.lastSha = null;
    this.isPolling = false;
    this.cronJob = null;
  }

  /**
   * Start the poller
   */
  start() {
    if (this.isPolling) {
      this.logger.warn('Poller already running');
      return;
    }

    this.logger.info(`Starting GitHub poller (interval: ${this.interval} minutes)`);

    // Schedule cron job (runs every N minutes)
    const cronPattern = `*/${this.interval} * * * *`;
    this.cronJob = cron.schedule(cronPattern, () => this.checkForUpdates().catch(e => {
      this.logger.error(`Poll error: ${e.message}`);
    }));

    this.isPolling = true;

    // Initial check
    this.checkForUpdates().catch(e => {
      this.logger.error(`Initial poll error: ${e.message}`);
    });
  }

  /**
   * Stop the poller
   */
  stop() {
    if (this.cronJob) {
      this.cronJob.stop();
      this.cronJob = null;
    }
    this.isPolling = false;
    this.logger.info('Poller stopped');
  }

  /**
   * Check for updates on GitHub
   */
  async checkForUpdates() {
    try {
      const { data: ref } = await this.github.rest.git.getRef({
        owner: this.owner,
        repo: this.repo,
        ref: 'heads/main'
      });

      const currentSha = ref.object.sha;

      this.logger.debug(`Poll check: ${this.lastSha || 'none'} -> ${currentSha}`);

      if (this.lastSha && this.lastSha === currentSha) {
        this.logger.debug('No changes detected');
        return;
      }

      this.logger.info(`New commit detected: ${currentSha}`);

      // Get comparison to find changed files
      const { data: comparison } = await this.github.rest.repos.compareCommits({
        owner: this.owner,
        repo: this.repo,
        base: this.lastSha || currentSha,
        head: currentSha
      });

      // Filter for skill files
      const skillFiles = comparison.files
        .filter(f => f.status === 'added' || f.status === 'modified')
        .filter(f => f.filename.includes('SKILL.md') || f.filename.includes('skill.md'));

      if (skillFiles.length === 0) {
        this.logger.debug('No skill files in changes');
        this.lastSha = currentSha;
        await this.updateLastSha(currentSha);
        return;
      }

      this.logger.info(`Processing ${skillFiles.length} changed skill files`);

      // Fetch and validate
      const validatedSkills = await this.fetchAndValidateSkills(skillFiles, currentSha);

      const invalid = validatedSkills.filter(r => !r.valid);
      if (invalid.length > 0) {
        this.logger.error(`Validation failed for ${invalid.length} skills`);
        await this.audit.logPollResult({
          sha: currentSha,
          status: 'validation_failed',
          errors: invalid.map(r => ({ file: r.filename, errors: r.errors }))
        });
        return;
      }

      // Deploy
      try {
        const deployment = await this.deployer.deploy(
          validatedSkills.filter(r => r.valid),
          {
            trigger: 'polling',
            commitSha: currentSha,
            previousSha: this.lastSha
          }
        );

        await this.audit.logDeployment(deployment);
        await this.audit.logPollResult({
          sha: currentSha,
          status: 'success',
          deploymentId: deployment.id
        });

        this.lastSha = currentSha;
        await this.updateLastSha(currentSha);

        this.logger.info(`Polling deployment complete: ${deployment.deployed.length} skills`);

      } catch (deployError) {
        this.logger.error(`Deployment failed: ${deployError.message}`);
        await this.audit.logPollResult({
          sha: currentSha,
          status: 'deployment_failed',
          error: deployError.message
        });
      }

    } catch (error) {
      this.logger.error(`Poll check failed: ${error.message}`);
      await this.audit.logPollResult({
        status: 'check_failed',
        error: error.message
      });
    }
  }

  /**
   * Fetch and validate skills from GitHub
   */
  async fetchAndValidateSkills(files, sha) {
    const results = [];

    for (const file of files) {
      try {
        const response = await this.github.rest.repos.getContent({
          owner: this.owner,
          repo: this.repo,
          path: file.filename,
          ref: sha
        });

        const content = Buffer.from(response.data.content, 'base64').toString('utf8');
        const result = await this.validator.validateContent(content, file.filename);
        result.filename = file.filename;
        results.push(result);

      } catch (e) {
        this.logger.error(`Failed to fetch ${file.filename}: ${e.message}`);
        results.push({
          valid: false,
          errors: [e.message],
          filename: file.filename,
          skill: null
        });
      }
    }

    return results;
  }

  /**
   * Update last processed SHA
   */
  async updateLastSha(sha) {
    // Store in Neo4j for persistence across restarts
    try {
      await this.audit.updateLastSha(sha);
    } catch (e) {
      this.logger.error(`Failed to persist SHA: ${e.message}`);
    }
  }

  /**
   * Load last SHA from audit log
   */
  async loadLastSha() {
    try {
      this.lastSha = await this.audit.getLastSha();
      this.logger.debug(`Loaded last SHA: ${this.lastSha}`);
    } catch (e) {
      this.logger.warn(`Failed to load last SHA: ${e.message}`);
    }
  }
}

module.exports = { GitHubPoller };
