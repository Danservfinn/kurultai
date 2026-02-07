/**
 * Skill Deployer
 * Handles atomic deployment with rollback capability
 */

const fs = require('fs').promises;
const path = require('path');
const crypto = require('crypto');
const { lock } = require('../utils/lock');
const constants = require('../config/constants');

class DeploymentError extends Error {
  constructor(message, details = {}) {
    super(message);
    this.name = 'DeploymentError';
    this.details = details;
  }
}

class SkillDeployer {
  constructor(options = {}) {
    this.skillsDir = options.skillsDir || constants.SKILLS_DIR;
    this.backupDir = options.backupDir || constants.BACKUP_DIR;
    this.logger = options.logger || console;
  }

  /**
   * Deploy validated skills atomically
   */
  async deploy(validatedSkills, metadata = {}) {
    const deploymentId = crypto.randomUUID();
    const timestamp = new Date().toISOString();
    const lockKey = 'deployment';

    // Acquire deployment lock
    const releaseLock = await lock.acquire(lockKey, constants.DEPLOYMENT_LOCK_TTL);

    try {
      this.logger.info(`[${deploymentId}] Starting deployment of ${validatedSkills.length} skills`);

      // 1. Create backup
      await this.createBackup(deploymentId);

      // 2. Deploy each skill atomically
      const deployed = [];
      const failed = [];

      for (const skill of validatedSkills) {
        try {
          await this.deploySkill(skill.skill, deploymentId);
          deployed.push({
            name: skill.skill.name,
            version: skill.skill.version,
            path: path.join(this.skillsDir, `${skill.skill.name}.md`)
          });
        } catch (e) {
          failed.push({
            name: skill.skill.name,
            error: e.message
          });
          throw new DeploymentError(`Failed to deploy ${skill.skill.name}`, { cause: e });
        }
      }

      // 3. Trigger moltbot reload (via signal file or API)
      await this.triggerReload();

      // 4. Health check
      const healthy = await this.healthCheck();
      if (!healthy) {
        throw new Error('Health check failed after deployment');
      }

      const result = {
        id: deploymentId,
        timestamp,
        status: 'success',
        deployed,
        failed,
        metadata
      };

      this.logger.info(`[${deploymentId}] Deployment completed successfully`);
      return result;

    } catch (error) {
      this.logger.error(`[${deploymentId}] Deployment failed: ${error.message}`);

      // Rollback on failure
      await this.rollback(deploymentId);

      throw new DeploymentError('Deployment failed, rolled back', {
        deploymentId,
        cause: error
      });
    } finally {
      await releaseLock();
    }
  }

  /**
   * Deploy a single skill atomically
   */
  async deploySkill(skill, deploymentId) {
    const targetPath = path.join(this.skillsDir, `${skill.name}.md`);
    const tempPath = `${targetPath}.tmp.${deploymentId}`;

    // Ensure skills directory exists
    await fs.mkdir(this.skillsDir, { recursive: true });

    // Write to temp file first
    await fs.writeFile(tempPath, skill.content, 'utf8');

    // Atomic rename
    await fs.rename(tempPath, targetPath);

    this.logger.debug(`Deployed skill: ${skill.name} v${skill.version}`);
  }

  /**
   * Create backup of current skills
   */
  async createBackup(deploymentId) {
    const backupPath = path.join(this.backupDir, deploymentId);
    await fs.mkdir(backupPath, { recursive: true });

    try {
      const skills = await fs.readdir(this.skillsDir);

      for (const skillFile of skills) {
        if (skillFile.endsWith('.md')) {
          const src = path.join(this.skillsDir, skillFile);
          const dest = path.join(backupPath, skillFile);
          await fs.copyFile(src, dest);
        }
      }

      // Write metadata
      await fs.writeFile(
        path.join(backupPath, 'metadata.json'),
        JSON.stringify({ deploymentId, timestamp: new Date().toISOString() }),
        'utf8'
      );

      this.logger.debug(`Backup created: ${backupPath}`);
    } catch (e) {
      if (e.code !== 'ENOENT') {
        throw e;
      }
      // No existing skills to backup
      this.logger.debug('No existing skills to backup');
    }
  }

  /**
   * Rollback to previous backup
   */
  async rollback(deploymentId) {
    const backupPath = path.join(this.backupDir, deploymentId);

    try {
      const metadata = JSON.parse(
        await fs.readFile(path.join(backupPath, 'metadata.json'), 'utf8')
      );

      const skills = await fs.readdir(backupPath);

      for (const skillFile of skills) {
        if (skillFile.endsWith('.md')) {
          const src = path.join(backupPath, skillFile);
          const dest = path.join(this.skillsDir, skillFile);
          await fs.copyFile(src, dest);
        }
      }

      this.logger.info(`Rolled back to deployment ${deploymentId}`);
      await this.triggerReload();

      return { success: true, deploymentId };
    } catch (e) {
      this.logger.error(`Rollback failed: ${e.message}`);
      return { success: false, error: e.message };
    }
  }

  /**
   * Trigger moltbot to reload skills
   * This creates a signal file that moltbot watches
   */
  async triggerReload() {
    const signalPath = path.join(this.skillsDir, '.reload');
    await fs.writeFile(signalPath, Date.now().toString(), 'utf8');
    this.logger.debug('Reload signal created');
  }

  /**
   * Health check after deployment
   */
  async healthCheck() {
    // Basic check: ensure skills directory is readable
    try {
      await fs.access(this.skillsDir, fs.constants.R_OK);
      return true;
    } catch (e) {
      this.logger.error(`Health check failed: ${e.message}`);
      return false;
    }
  }

  /**
   * List currently deployed skills
   */
  async listDeployed() {
    try {
      const files = await fs.readdir(this.skillsDir);
      const skills = [];

      for (const file of files) {
        if (file.endsWith('.md') && file !== '.reload') {
          const content = await fs.readFile(path.join(this.skillsDir, file), 'utf8');
          const frontmatterMatch = content.match(/^---\n(.*?)\n---/s);
          if (frontmatterMatch) {
            const yaml = require('js-yaml');
            const frontmatter = yaml.load(frontmatterMatch[1]);
            skills.push({
              name: frontmatter.name || file.replace('.md', ''),
              version: frontmatter.version,
              description: frontmatter.description,
              file: file
            });
          }
        }
      }

      return skills;
    } catch (e) {
      this.logger.error(`Failed to list deployed skills: ${e.message}`);
      return [];
    }
  }
}

module.exports = { SkillDeployer, DeploymentError };
