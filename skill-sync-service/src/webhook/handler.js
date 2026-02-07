/**
 * GitHub Webhook Handler
 * Receives and processes GitHub push events
 */

const crypto = require('crypto');
const { SkillValidator } = require('../validators/skill');
const { SkillDeployer } = require('../deployer/deployer');
const { AuditLogger } = require('../audit/logger');
const constants = require('../config/constants');

class WebhookHandler {
  constructor(options = {}) {
    this.githubSecret = options.githubSecret || constants.GITHUB_WEBHOOK_SECRET;
    this.validator = options.validator || new SkillValidator();
    this.deployer = options.deployer || new SkillDeployer();
    this.audit = options.audit || new AuditLogger();
    this.logger = options.logger || console;
    this.github = options.github; // Octokit instance
  }

  /**
   * Handle GitHub webhook POST
   */
  async handle(req, res) {
    const signature = req.headers['x-hub-signature-256'];
    const deliveryId = req.headers['x-github-delivery'];
    const eventType = req.headers['x-github-event'];

    this.logger.info(`Webhook received: ${eventType} ${deliveryId}`);

    // 1. Verify signature
    if (!this.verifySignature(req.body, signature)) {
      this.logger.warn('Invalid webhook signature');
      return res.status(401).json({ error: 'Invalid signature' });
    }

    // 1.5. Verify timestamp (replay protection)
    if (!this.verifyTimestamp(req)) {
      this.logger.warn('Webhook timestamp validation failed');
      return res.status(401).json({ error: 'Invalid timestamp' });
    }

    // 2. Check event type
    if (eventType !== 'push') {
      this.logger.debug(`Ignoring event type: ${eventType}`);
      return res.status(200).json({ message: `Event type ${eventType} ignored` });
    }

    // 3. Parse payload
    const { repository, ref, commits, after, before } = req.body;

    // Only process main/master branch
    if (!ref.includes('main') && !ref.includes('master')) {
      this.logger.debug(`Ignoring branch: ${ref}`);
      return res.status(200).json({ message: 'Ignoring non-main branch' });
    }

    // 4. Extract changed skill files
    const changedFiles = this.extractSkillFiles(commits);
    if (changedFiles.length === 0) {
      this.logger.debug('No skill files changed');
      return res.status(200).json({ message: 'No skill files changed' });
    }

    this.logger.info(`Processing ${changedFiles.length} changed skill files`);

    try {
      // 5. Fetch skill content from GitHub
      const validatedSkills = await this.fetchAndValidateSkills(changedFiles, after);

      // 6. Check validation results
      const invalid = validatedSkills.filter(r => !r.valid);
      if (invalid.length > 0) {
        this.logger.error(`Validation failed for ${invalid.length} skills`);
        return res.status(400).json({
          error: 'Validation failed',
          details: invalid.map(r => ({ file: r.filename, errors: r.errors }))
        });
      }

      // 7. Deploy
      const deployment = await this.deployer.deploy(
        validatedSkills.filter(r => r.valid),
        {
          trigger: 'webhook',
          deliveryId,
          commitSha: after,
          previousSha: before,
          branch: ref
        }
      );

      // 8. Log to audit
      await this.audit.logDeployment(deployment);

      res.status(200).json({
        deploymentId: deployment.id,
        status: 'success',
        deployed: deployment.deployed.length,
        message: `Successfully deployed ${deployment.deployed.length} skills`
      });

    } catch (error) {
      this.logger.error(`Webhook processing failed: ${error.message}`);

      // Log failed deployment to audit
      await this.audit.logDeployment({
        id: error.details?.deploymentId || 'unknown',
        timestamp: new Date().toISOString(),
        status: 'failed',
        error: error.message,
        trigger: 'webhook',
        deliveryId
      });

      res.status(500).json({
        error: 'Deployment failed',
        message: error.message
      });
    }
  }

  /**
   * Verify GitHub webhook signature
   */
  verifySignature(payload, signature) {
    if (!this.githubSecret) {
      // CRITICAL: Never skip verification in production
      this.logger.error('GitHub webhook secret not configured');
      return false; // Changed from: return true
    }

    if (!signature) {
      return false;
    }

    const hmac = crypto.createHmac('sha256', this.githubSecret);
    const digest = `sha256=${hmac.update(JSON.stringify(payload)).digest('hex')}`;

    // timingSafeEqual throws if buffers have different lengths
    // Check length first to avoid the exception
    const sigBuffer = Buffer.from(signature);
    const digestBuffer = Buffer.from(digest);

    if (sigBuffer.length !== digestBuffer.length) {
      return false;
    }

    return crypto.timingSafeEqual(sigBuffer, digestBuffer);
  }

  /**
   * Verify webhook timestamp is within acceptable window
   */
  verifyTimestamp(req) {
    // x-github-delivery is a GUID, not a timestamp
    // Use the Date header instead
    const timestamp = req.headers['date'];
    if (!timestamp) {
      this.logger.warn('Webhook missing date header');
      return false;
    }

    const deliveryTime = new Date(timestamp).getTime();
    const now = Date.now();
    const ageSeconds = (now - deliveryTime) / 1000;

    // Reject webhooks older than 5 minutes or from the future (> 60s)
    if (ageSeconds > 300 || ageSeconds < -60) {
      this.logger.warn(`Webhook timestamp out of range: ${ageSeconds}s`);
      return false;
    }

    return true;
  }

  /**
   * Extract skill files from commits
   */
  extractSkillFiles(commits) {
    const skillFiles = new Set();

    for (const commit of commits) {
      for (const file of [...(commit.added || []), ...(commit.modified || [])]) {
        if (file.includes('SKILL.md') || file.includes('skill.md')) {
          skillFiles.add(file);
        }
      }
    }

    return Array.from(skillFiles);
  }

  /**
   * Fetch and validate skills from GitHub
   */
  async fetchAndValidateSkills(filePaths, commitSha) {
    const results = [];

    for (const filePath of filePaths) {
      try {
        // Fetch file content from GitHub API
        const response = await this.github.rest.repos.getContent({
          owner: constants.GITHUB_OWNER,
          repo: constants.GITHUB_REPO,
          path: filePath,
          ref: commitSha
        });

        // Handle if response is an array (directory)
        if (Array.isArray(response.data)) {
          const skillFile = response.data.find(f => f.name === 'SKILL.md' || f.name === 'skill.md');
          if (skillFile) {
            const content = Buffer.from(skillFile.content, 'base64').toString('utf8');
            const result = await this.validator.validateContent(content, skillFile.name);
            result.filename = filePath;
            results.push(result);
          }
        } else {
          const content = Buffer.from(response.data.content, 'base64').toString('utf8');
          const result = await this.validator.validateContent(content, filePath);
          result.filename = filePath;
          results.push(result);
        }
      } catch (e) {
        this.logger.error(`Failed to fetch ${filePath}: ${e.message}`);
        results.push({
          valid: false,
          errors: [e.message],
          filename: filePath,
          skill: null
        });
      }
    }

    return results;
  }
}

module.exports = { WebhookHandler };
