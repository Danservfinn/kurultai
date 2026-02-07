/**
 * Skill Validator
 * Validates skill markdown files with YAML frontmatter
 */

const yaml = require('js-yaml');
const fs = require('fs').promises;
const path = require('path');
const constants = require('../config/constants');

class SkillValidationError extends Error {
  constructor(message, details = {}) {
    super(message);
    this.name = 'SkillValidationError';
    this.details = details;
  }
}

class SkillValidator {
  /**
   * Validate a skill from file path
   */
  async validateFromPath(filePath) {
    const content = await fs.readFile(filePath, 'utf8');
    return this.validateContent(content, path.basename(filePath));
  }

  /**
   * Validate a skill from content string
   */
  async validateContent(content, filename = 'unknown') {
    const errors = [];
    const warnings = [];

    // Check file size
    if (content.length > constants.MAX_SKILL_SIZE_BYTES) {
      errors.push(`File size (${content.length}) exceeds maximum (${constants.MAX_SKILL_SIZE_BYTES})`);
    }

    // Parse YAML frontmatter
    const frontmatterMatch = content.match(/^---\n(.*?)\n---/s);
    if (!frontmatterMatch) {
      errors.push('Missing YAML frontmatter (must start with ---)');
      return { valid: false, errors, warnings, skill: null };
    }

    let frontmatter;
    try {
      frontmatter = yaml.load(frontmatterMatch[1], { schema: yaml.FAILSAFE_SCHEMA });
    } catch (e) {
      errors.push(`Invalid YAML: ${e.message}`);
      return { valid: false, errors, warnings, skill: null };
    }

    if (!frontmatter || typeof frontmatter !== 'object') {
      errors.push('YAML frontmatter must be an object');
      return { valid: false, errors, warnings, skill: null };
    }

    // Check required fields
    const missingFields = constants.REQUIRED_FIELDS.filter(f => !frontmatter[f]);
    if (missingFields.length > 0) {
      errors.push(`Missing required fields: ${missingFields.join(', ')}`);
    }

    // Validate version format (semver)
    if (frontmatter.version && !/^\d+\.\d+(\.\d+)?$/.test(frontmatter.version)) {
      warnings.push(`Version "${frontmatter.version}" is not in semver format (x.y.z)`);
    }

    // Check for integrations array if present
    if (frontmatter.integrations && !Array.isArray(frontmatter.integrations)) {
      errors.push('integrations field must be an array');
    }

    // Security scan for secrets
    const secrets = this.scanForSecrets(content);
    if (secrets.length > 0) {
      errors.push(`Potential secrets detected: ${secrets.map(s => s.name).join(', ')}`);
    }

    // Build skill object
    const skill = {
      name: frontmatter.name,
      version: frontmatter.version,
      description: frontmatter.description,
      integrations: frontmatter.integrations || [],
      content: content,
      filename: filename,
      sizeBytes: content.length
    };

    return {
      valid: errors.length === 0,
      errors,
      warnings,
      skill
    };
  }

  /**
   * Scan content for potential secrets/passwords
   */
  scanForSecrets(content) {
    const found = [];

    // Skip scanning the examples section if present
    const lines = content.split('\n');
    const exampleStart = lines.findIndex(l => l.includes('## Examples'));
    const relevantContent = exampleStart >= 0
      ? lines.slice(0, exampleStart).join('\n')
      : content;

    for (const { name, pattern } of constants.SECRET_PATTERNS) {
      const matches = relevantContent.match(pattern);
      if (matches) {
        found.push({ name, matches: matches.length });
      }
    }

    return found;
  }

  /**
   * Validate multiple skills
   */
  async validateMany(skillPaths) {
    const results = [];
    const errors = [];

    for (const skillPath of skillPaths) {
      try {
        const result = await this.validateFromPath(skillPath);
        results.push(result);
        if (!result.valid) {
          errors.push(`${skillPath}: ${result.errors.join(', ')}`);
        }
      } catch (e) {
        errors.push(`${skillPath}: ${e.message}`);
      }
    }

    return {
      allValid: errors.length === 0,
      results,
      errors
    };
  }
}

module.exports = { SkillValidator, SkillValidationError };
