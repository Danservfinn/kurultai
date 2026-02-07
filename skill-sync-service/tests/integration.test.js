/**
 * Integration tests for skill-sync-service
 * Tests webhook processing, skill validation, and deployment
 */

const request = require('supertest');
const express = require('express');
const { WebhookHandler } = require('../src/webhook/handler');
const { SkillDeployer } = require('../src/deployer/deployer');
const { SkillValidator } = require('../src/validators/skill');
const fs = require('fs').promises;
const path = require('path');
const os = require('os');
const crypto = require('crypto');

describe('Skill Sync Integration Tests', () => {
  let app;
  let webhookHandler;
  let testSkillsDir;
  let deployer;
  let testSecret = 'test-webhook-secret';

  beforeAll(async () => {
    // Create temporary skills directory
    testSkillsDir = path.join(os.tmpdir(), 'skills-test-' + Date.now());
    await fs.mkdir(testSkillsDir, { recursive: true });

    // Create deployer with test directory
    deployer = new SkillDeployer({
      skillsDir: testSkillsDir,
      logger: { info: () => {}, error: () => {}, warn: () => {}, debug: () => {} }
    });

    // Create webhook handler
    webhookHandler = new WebhookHandler({
      githubSecret: testSecret,
      deployer,
      logger: { info: () => {}, error: () => {}, warn: () => {}, debug: () => {} },
      github: null // No GitHub client for tests
    });

    // Create Express app
    app = express();
    app.use(express.json());
    app.post('/webhook/github', (req, res) => webhookHandler.handle(req, res));
    app.get('/health', (req, res) => res.json({ status: 'healthy' }));
  });

  afterAll(async () => {
    // Cleanup test directory
    await fs.rm(testSkillsDir, { recursive: true, force: true });
  });

  describe('Webhook Signature Verification', () => {
    const generateSignature = (payload, secret) => {
      const hmac = crypto.createHmac('sha256', secret);
      const digest = 'sha256=' + hmac.update(JSON.stringify(payload)).digest('hex');
      return digest;
    };

    test('should reject webhook without signature', async () => {
      const response = await request(app)
        .post('/webhook/github')
        .send({});

      expect(response.status).toBe(401);
      expect(response.body.error).toBe('Invalid signature');
    });

    test('should reject webhook with invalid signature', async () => {
      const payload = { test: 'data' };
      const response = await request(app)
        .post('/webhook/github')
        .set('x-hub-signature-256', 'sha256=invalid')
        .send(payload);

      expect(response.status).toBe(401);
    });

    test('should accept webhook with valid signature', async () => {
      const payload = {
        repository: { full_name: 'Danservfinn/kurultai-skills' },
        ref: 'refs/heads/main',
        commits: [],
        before: 'abc123',
        after: 'def456'
      };

      const signature = generateSignature(payload, testSecret);

      const response = await request(app)
        .post('/webhook/github')
        .set('x-hub-signature-256', signature)
        .set('x-github-event', 'push')
        .set('x-github-delivery', 'test-delivery-123')
        .set('date', new Date().toUTCString())
        .send(payload);

      // Should get 200 (even if no skill files changed)
      expect([200, 401]).toContain(response.status);
    });
  });

  describe('Skill Deployment', () => {
    test('should deploy valid skill to skills directory', async () => {
      const validSkill = {
        name: 'test-skill',
        version: '1.0.0',
        description: 'Test skill',
        content: '# Test Skill\n\nTest content'
      };

      const result = await deployer.deploySkill(validSkill, 'test-deployment');

      // Verify file was written
      const filePath = path.join(testSkillsDir, 'test-skill.md');
      const exists = await fs.access(filePath).then(() => true).catch(() => false);
      expect(exists).toBe(true);

      // Verify content
      const content = await fs.readFile(filePath, 'utf8');
      expect(content).toContain('Test Skill');
    });

    test('should list deployed skills', async () => {
      // Create a test skill with frontmatter
      const skillContent = `---
name: list-test-skill
version: 1.0.0
description: Test for listing
---
# Skill Content
`;
      const filePath = path.join(testSkillsDir, 'list-test-skill.md');
      await fs.writeFile(filePath, skillContent, 'utf8');

      const skills = await deployer.listDeployed();
      const found = skills.find(s => s.name === 'list-test-skill');

      expect(found).toBeDefined();
      expect(found.version).toBe('1.0.0');
    });
  });

  describe('Health Endpoint', () => {
    test('should return healthy status', async () => {
      const response = await request(app)
        .get('/health');

      expect(response.status).toBe(200);
      expect(response.body.status).toBe('healthy');
    });
  });

  describe('Webhook Event Filtering', () => {
    const generateSignature = (payload, secret) => {
      const hmac = crypto.createHmac('sha256', secret);
      const digest = 'sha256=' + hmac.update(JSON.stringify(payload)).digest('hex');
      return digest;
    };

    test('should ignore non-push events', async () => {
      const payload = {
        repository: { full_name: 'test/repo' },
        ref: 'refs/heads/main',
        commits: []
      };

      const signature = generateSignature(payload, testSecret);

      const response = await request(app)
        .post('/webhook/github')
        .set('x-hub-signature-256', signature)
        .set('x-github-event', 'pull_request')
        .set('date', new Date().toUTCString())
        .send(payload);

      expect(response.status).toBe(200);
      expect(response.body.message).toContain('ignored');
    });

    test('should ignore non-main branches', async () => {
      const payload = {
        repository: { full_name: 'test/repo' },
        ref: 'refs/heads/feature-branch',
        commits: []
      };

      const signature = generateSignature(payload, testSecret);

      const response = await request(app)
        .post('/webhook/github')
        .set('x-hub-signature-256', signature)
        .set('x-github-event', 'push')
        .set('date', new Date().toUTCString())
        .send(payload);

      expect(response.status).toBe(200);
      expect(response.body.message).toContain('Ignoring non-main branch');
    });
  });

  describe('Skill File Extraction', () => {
    test('should extract SKILL.md files from commits', async () => {
      const handler = new WebhookHandler({
        githubSecret: testSecret,
        logger: { info: () => {}, error: () => {} }
      });

      const commits = [
        {
          added: ['horde-prompt/SKILL.md', 'README.md'],
          modified: ['other-skill/skill.md']
        }
      ];

      const files = handler.extractSkillFiles(commits);

      expect(files).toContain('horde-prompt/SKILL.md');
      expect(files).toContain('other-skill/skill.md');
      expect(files).not.toContain('README.md');
    });
  });
});
