/**
 * Skill Watcher - Monitors /data/skills/ for changes and triggers hot-reload
 * Uses chokidar for efficient file watching with debouncing
 */

const chokidar = require('chokidar');
const path = require('path');
const winston = require('winston');

class SkillWatcher {
  constructor(options = {}) {
    this.skillsDir = options.skillsDir || process.env.SKILLS_DIR || '/data/skills';
    this.logger = options.logger || winston.createLogger({
      level: 'info',
      transports: [new winston.transports.Console()]
    });
    this.watcher = null;
    this.onSkillChange = options.onSkillChange || null;
  }

  async start() {
    // Ensure skills directory exists
    const fs = require('fs').promises;
    await fs.mkdir(this.skillsDir, { recursive: true });

    // Watch for markdown file changes
    this.watcher = chokidar.watch(
      path.join(this.skillsDir, '**/*.md'),
      {
        persistent: true,
        ignoreInitial: true, // Don't trigger on existing files at startup
        awaitWriteFinish: {
          stabilityThreshold: 2000, // Wait 2s for file to be fully written
          pollInterval: 100
        }
      }
    );

    this.watcher
      .on('add', (filePath) => this.handleFileAdded(filePath))
      .on('change', (filePath) => this.handleFileChanged(filePath))
      .on('unlink', (filePath) => this.handleFileRemoved(filePath))
      .on('error', (error) => this.logger.error(`Watcher error: ${error.message}`));

    this.logger.info(`SkillWatcher watching ${this.skillsDir}`);

    // Log initial skills
    const skills = this.listSkills();
    this.logger.info(`Initial skills loaded: ${skills.length > 0 ? skills.join(', ') : '(none)'}`);
  }

  async handleFileAdded(filePath) {
    const skillName = path.basename(filePath, '.md');
    this.logger.info(`Skill added: ${skillName} from ${filePath}`);
    await this.notifyChange('add', skillName, filePath);
  }

  async handleFileChanged(filePath) {
    const skillName = path.basename(filePath, '.md');
    this.logger.info(`Skill changed: ${skillName} from ${filePath}`);
    await this.notifyChange('change', skillName, filePath);
  }

  async handleFileRemoved(filePath) {
    const skillName = path.basename(filePath, '.md');
    this.logger.info(`Skill removed: ${skillName} from ${filePath}`);
    await this.notifyChange('remove', skillName, filePath);
  }

  async notifyChange(action, skillName, filePath) {
    // Notify callback if provided
    if (this.onSkillChange) {
      try {
        await this.onSkillChange({ action, skillName, filePath });
      } catch (e) {
        this.logger.error(`Error in skill change callback: ${e.message}`);
      }
    }

    // Check for .reload signal file from skill-sync-service
    if (skillName === '.reload') {
      await this.reloadAllSkills();
    }
  }

  async reloadAllSkills() {
    this.logger.info('Received .reload signal - Reloading all skills...');
    // TODO: Notify OpenClaw gateway to reload skill configuration
    // This may require gateway API call or config reload
    // For now, just log that reload was triggered
    const skills = this.listSkills();
    this.logger.info(`Skills after reload signal: ${skills.join(', ')}`);
  }

  async stop() {
    if (this.watcher) {
      await this.watcher.close();
      this.logger.info('SkillWatcher stopped');
    }
  }

  listSkills() {
    const fs = require('fs');
    try {
      const files = fs.readdirSync(this.skillsDir);
      return files.filter(f => f.endsWith('.md') && f !== '.reload');
    } catch (e) {
      this.logger.error(`Error listing skills: ${e.message}`);
      return [];
    }
  }
}

module.exports = { SkillWatcher };
