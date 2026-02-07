/**
 * Skill Validator Tests
 */

const { SkillValidator } = require('../src/validators/skill');

describe('SkillValidator', () => {
  let validator;

  beforeEach(() => {
    validator = new SkillValidator();
  });

  describe('validContent', () => {
    const validSkill = `---
name: test-skill
version: "1.0"
description: A test skill
integrations:
  - horde-swarm
---

# Test Skill

This is a test skill.
`;

    it('should validate a valid skill', async () => {
      const result = await validator.validateContent(validSkill, 'test.md');
      expect(result.valid).toBe(true);
      expect(result.errors).toHaveLength(0);
      expect(result.skill.name).toBe('test-skill');
      expect(result.skill.version).toBe('1.0');
    });

    it('should reject missing YAML frontmatter', async () => {
      const result = await validator.validateContent('No frontmatter', 'test.md');
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('Missing YAML frontmatter (must start with ---)');
    });

    it('should reject missing required fields', async () => {
      const invalidSkill = `---
name: test-skill
---
`;
      const result = await validator.validateContent(invalidSkill, 'test.md');
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('Missing required fields: version, description');
    });

    it('should warn about non-semver version', async () => {
      const nonSemver = `---
name: test-skill
version: "v1"
description: Test
---
`;
      const result = await validator.validateContent(nonSemver, 'test.md');
      expect(result.valid).toBe(true);
      expect(result.warnings).toHaveLength(1);
      expect(result.warnings[0]).toContain('not in semver format');
    });

    it('should detect secrets', async () => {
      const withSecret = `---
name: test-skill
version: "1.0"
description: Test
---

API key: sk-ant-api123-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
`;
      const result = await validator.validateContent(withSecret, 'test.md');
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.includes('anthropic_key'))).toBe(true);
    });
  });

  describe('scanForSecrets', () => {
    it('should detect multiple secret types', () => {
      const content = `
GitHub token: ghp_1234567890abcdefghijklmnopqrstuvwxyz
AWS key: AKIAABCDEFGHIJKLMNOPQR
Private key: -----BEGIN RSA PRIVATE KEY-----
      `;

      const secrets = validator.scanForSecrets(content);
      expect(secrets.length).toBeGreaterThanOrEqual(2);
    });
  });
});
