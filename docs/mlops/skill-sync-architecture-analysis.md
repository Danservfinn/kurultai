# Skill Sync Architecture Analysis
## GitHub to Railway Automated Skill Deployment

**Date**: 2026-02-07
**Author**: MLOps Architect
**Status**: Design Analysis

---

## Executive Summary

This document analyzes backend architecture approaches for automatically synchronizing skill updates from the `kurultai-skills` GitHub repository to the `kublai.kurult.ai` Railway deployment.

**Current State:**
- Source: `kurultai-skills` repo at `/Users/kurultai/.claude/skills/` (GitHub: `Danservfinn/kurultai-skills`)
- Destination: `kublai.kurult.ai` (Railway deployment with OpenClaw gateway)
- Skills are markdown files with YAML frontmatter
- Current process: Manual updates

**Requirements:**
1. Automated detection of skill changes in GitHub
2. Secure deployment to Railway without downtime
3. Validation of skill format before deployment
4. Rollback capability on failure
5. Audit trail of all deployments

---

## Architecture Overview

```
                    ┌─────────────────────────────────────────────────────────────┐
                    │                    Skill Sync Architecture                      │
                    └─────────────────────────────────────────────────────────────┘

    GitHub Repository                                                   Railway (kublai.kurult.ai)
    ┌─────────────────────┐                                        ┌─────────────────────────┐
    │                     │      Webhook / Poll                     │                         │
    │  kurultai-skills    │───────────────────────────────────────▶│  Skill Sync Service     │
    │  (master branch)    │                                        │  (New Railway Service)  │
    │                     │                                        │                         │
    │  ┌───┐ ┌───┐ ┌───┐ │                                        │  ┌───────────────────┐  │
    │  │ A │ │ B │ │ C │ │    Pull on change                      │  │ Skill Store       │  │
    │  └───┘ └───┘ └───┘ │─────────────────────────────────────────▶│  /data/skills/      │  │
    │       Skills         │                                        │  └───────────────────┘  │
    └─────────────────────┘                                        │            │            │
                                                                   │            ▼            │
    Alternative Approaches Below                                   │  ┌───────────────────┐  │
                                                                   │  │ Moltbot Gateway  │  │
                                                                   │  │  (Hot Reload)    │  │
                                                                   │  └───────────────────┘  │
                                                                   └─────────────────────────┘
```

---

## Approach 1: GitHub Webhook + Railway Skill Sync Service

### Architecture

```
GitHub Push Event
       │
       ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     GitHub Webhook Payload                         │
│  - Repository: Danservfinn/kurultai-skills                         │
│  - Event: push                                                     │
│  - Branch: main/master                                             │
│  - Commits: [{added, modified, removed files}]                     │
└─────────────────────────────────────────────────────────────────────┘
       │
       │ 1. POST to webhook endpoint
       ▼
┌─────────────────────────────────────────────────────────────────────┐
│                Railway: skill-sync-service                         │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Webhook Handler (Express.js)                                │   │
│  │  - Verify GitHub signature (HMAC-SHA256)                    │   │
│  │  - Parse changed files                                      │   │
│  │  - Filter for SKILL.md files only                          │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                          │                                          │
│                          ▼                                          │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Skill Validator                                            │   │
│  │  - YAML frontmatter parsing                                │   │
│  │  - Required fields check (name, version, description)      │   │
│  │  - Schema validation                                       │   │
│  │  - Security scan (no embedded credentials)                 │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                          │                                          │
│                          ▼                                          │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Skill Fetcher                                              │   │
│  │  - Clone/pull from GitHub                                  │   │
│  │  - Extract changed skills                                  │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                          │                                          │
│                          ▼                                          │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Skill Deployment Manager                                   │   │
│  │  - Atomic write to /data/skills/                           │   │
│  │  - Create backup before deployment                         │   │
│  │  - Trigger moltbot hot-reload                              │   │
│  │  - Health check verification                               │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                          │                                          │
│                          ▼                                          │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Audit Logger                                               │   │
│  │  - Log all deployments to Neo4j                            │   │
│  │  - Create SkillDeployment node                             │   │
│  │  - Track version history                                   │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
       │
       │ 2. Skill files updated
       ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Moltbot Gateway                                  │
│  - Hot-reload skill registry                                       │
│  - New skills immediately available                                │
└─────────────────────────────────────────────────────────────────────┘
```

### Components

#### 1. Webhook Handler (Node.js/Express)

```javascript
// skill-sync-service/src/webhook/handler.js
const crypto = require('crypto');
const express = require('express');
const { SkillValidator } = require('../validators/skill');
const { SkillDeployer } = require('../deployer/deployer');
const { AuditLogger } = require('../audit/logger');

const router = express.Router();

router.post('/webhook/github', async (req, res) => {
  // 1. Verify GitHub signature
  const signature = req.headers['x-hub-signature-256'];
  if (!verifyGitHubSignature(req.body, signature)) {
    return res.status(401).json({ error: 'Invalid signature' });
  }

  // 2. Parse webhook payload
  const { repository, ref, commits } = req.body;
  if (!ref.includes('main') && !ref.includes('master')) {
    return res.status(200).json({ message: 'Ignoring non-main branch' });
  }

  // 3. Extract changed skill files
  const changedSkills = extractSkillFiles(commits);

  // 4. Validate skills
  const validator = new SkillValidator();
  const validationResults = await Promise.all(
    changedSkills.map(skill => validator.validate(skill))
  );

  if (validationResults.some(r => !r.valid)) {
    return res.status(400).json({
      error: 'Validation failed',
      details: validationResults.filter(r => !r.valid)
    });
  }

  // 5. Deploy skills
  const deployer = new SkillDeployer();
  const deployment = await deployer.deploy(validationResults);

  // 6. Log to audit
  const audit = new AuditLogger();
  await audit.logDeployment(deployment);

  res.status(200).json({ deploymentId: deployment.id, status: 'deployed' });
});
```

#### 2. Skill Validator

```javascript
// skill-sync-service/src/validators/skill.js
const yaml = require('js-yaml');
const fs = require('fs').promises;

class SkillValidator {
  async validate(skillPath) {
    const content = await fs.readFile(skillPath, 'utf8');

    // Parse YAML frontmatter
    const frontmatterMatch = content.match(/^---\n(.*?)\n---/s);
    if (!frontmatterMatch) {
      return { valid: false, error: 'Missing YAML frontmatter' };
    }

    let frontmatter;
    try {
      frontmatter = yaml.load(frontmatterMatch[1]);
    } catch (e) {
      return { valid: false, error: 'Invalid YAML: ' + e.message };
    }

    // Required fields
    const required = ['name', 'version', 'description'];
    const missing = required.filter(f => !frontmatter[f]);
    if (missing.length > 0) {
      return { valid: false, error: `Missing fields: ${missing.join(', ')}` };
    }

    // Security scan
    const secrets = this.scanForSecrets(content);
    if (secrets.length > 0) {
      return { valid: false, error: `Potential secrets found: ${secrets.join(', ')}` };
    }

    return {
      valid: true,
      skill: {
        name: frontmatter.name,
        version: frontmatter.version,
        description: frontmatter.description,
        content: content
      }
    };
  }

  scanForSecrets(content) {
    const patterns = [
      /sk-[a-zA-Z0-9]{48}/,           // Anthropic API key
      /ghp_[a-zA-Z0-9]{36}/,          // GitHub token
      /AKIA[0-9A-Z]{16}/,             // AWS access key
      /-----BEGIN [A-Z]+ PRIVATE KEY-----/ // Private keys
    ];
    return patterns.flatMap(p => content.match(p) || []);
  }
}
```

#### 3. Skill Deployer

```javascript
// skill-sync-service/src/deployer/deployer.js
const fs = require('fs').promises;
const path = require('path');
const crypto = require('crypto');

class SkillDeployer {
  constructor() {
    this.skillsDir = process.env.SKILLS_DIR || '/data/skills';
    this.backupDir = process.env.BACKUP_DIR || '/data/backups/skills';
  }

  async deploy(validatedSkills) {
    const deploymentId = crypto.randomUUID();
    const timestamp = new Date().toISOString();

    // 1. Create backup
    await this.createBackup(deploymentId);

    // 2. Atomic write (write to temp, then rename)
    const results = [];
    for (const skill of validatedSkills) {
      const targetPath = path.join(this.skillsDir, `${skill.name}.md`);
      const tempPath = `${targetPath}.tmp.${deploymentId}`;

      await fs.writeFile(tempPath, skill.content);
      await fs.rename(tempPath, targetPath);

      results.push({
        name: skill.name,
        version: skill.version,
        path: targetPath
      });
    }

    // 3. Trigger moltbot reload
    await this.triggerReload();

    // 4. Health check
    const healthy = await this.healthCheck();
    if (!healthy) {
      await this.rollback(deploymentId);
      throw new Error('Health check failed, rolled back');
    }

    return { id: deploymentId, timestamp, results };
  }

  async createBackup(deploymentId) {
    const backupPath = path.join(this.backupDir, deploymentId);
    await fs.mkdir(backupPath, { recursive: true });

    const skills = await fs.readdir(this.skillsDir);
    for (const skill of skills) {
      await fs.copyFile(
        path.join(this.skillsDir, skill),
        path.join(backupPath, skill)
      );
    }
  }

  async rollback(deploymentId) {
    const backupPath = path.join(this.backupDir, deploymentId);
    const skills = await fs.readdir(backupPath);

    for (const skill of skills) {
      await fs.copyFile(
        path.join(backupPath, skill),
        path.join(this.skillsDir, skill)
      );
    }

    await this.triggerReload();
  }
}
```

### Dockerfile for Skill Sync Service

```dockerfile
# skill-sync-service/Dockerfile
FROM node:22-bookworm-slim

# Install git for cloning repos
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies
COPY package*.json ./
RUN npm ci --only=production

# Copy source
COPY src ./src

# Create directories
RUN mkdir -p /data/skills /data/backups/skills

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:3000/health || exit 1

EXPOSE 3000
CMD ["node", "src/index.js"]
```

### railway.yml Configuration

```yaml
# skill-sync-service/railway.yml
services:
  - name: skill-sync-service
    type: Worker
    buildCommand: npm install
    startCommand: node src/index.js
    env:
      - key = SKILLS_DIR
        value = /data/skills
      - key = BACKUP_DIR
        value = /data/backups/skills
      - key = GITHUB_WEBHOOK_SECRET
        generate = true
      - key = NEO4J_URI
        value = ${NEO4J_URI}
      - key = NEO4J_USER
        value = ${NEO4J_USER}
      - key = NEO4J_PASSWORD
        value = ${NEO4J_PASSWORD}
    volumes:
      - name: skills-data
        mountPath: /data
```

### Integration with moltbot

The moltbot gateway needs a skill hot-reload mechanism:

```javascript
// moltbot-railway-template/src/skills/reloader.js
const chokidar = require('chokidar');
const path = require('path');

class SkillReloader {
  constructor(skillsDir) {
    this.skillsDir = skillsDir;
    this.skills = new Map();
    this.watcher = null;
  }

  async initialize() {
    // Load initial skills
    await this.loadAllSkills();

    // Watch for changes
    this.watcher = chokidar.watch(path.join(this.skillsDir, '**/*.md'), {
      ignored: /(^|[\/\\])\../, // ignore dotfiles
      persistent: true
    });

    this.watcher
      .on('add', path => this.loadSkill(path))
      .on('change', path => this.reloadSkill(path))
      .on('unlink', path => this.unloadSkill(path));

    console.log(`[SkillReloader] Watching ${this.skillsDir}`);
  }

  async reloadSkill(filePath) {
    const skillName = path.basename(filePath, '.md');
    console.log(`[SkillReloader] Reloading skill: ${skillName}`);

    // Remove from cache
    if (this.skills.has(skillName)) {
      this.skills.delete(skillName);
    }

    // Reload
    await this.loadSkill(filePath);
  }

  getSkill(name) {
    return this.skills.get(name);
  }

  async loadAllSkills() {
    const fs = require('fs').promises;
    const files = await fs.readdir(this.skillsDir);

    for (const file of files) {
      if (file.endsWith('.md')) {
        await this.loadSkill(path.join(this.skillsDir, file));
      }
    }
  }

  async loadSkill(filePath) {
    const fs = require('fs').promises;
    const content = await fs.readFile(filePath, 'utf8');
    const yaml = require('js-yaml');

    const frontmatterMatch = content.match(/^---\n(.*?)\n---/s);
    if (frontmatterMatch) {
      const frontmatter = yaml.load(frontmatterMatch[1]);
      this.skills.set(frontmatter.name, {
        name: frontmatter.name,
        version: frontmatter.version,
        description: frontmatter.description,
        content: content
      });
    }
  }
}
```

### Pros

| Aspect | Benefit |
|--------|---------|
| **Real-time** | Skills deploy immediately on push |
| **Efficient** | Only processes changed files |
| **Atomic** | Single transaction per deployment |
| **Observable** | Full audit trail in Neo4j |
| **Rollback** | Automatic on health check failure |
| **Secure** | GitHub webhook signature verification |

### Cons

| Aspect | Drawback |
|--------|----------|
| **Complexity** | Requires new Railway service |
| **GitHub Dependency** | Needs webhook secret management |
| **Public Endpoint** | Webhook must be accessible (need auth) |
| **Startup Cost** | Initial implementation overhead |
| **Debugging** | Webhook failures can be tricky |
| **Network** | Relies on GitHub webhook delivery |

### Risk Analysis

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| GitHub webhook not delivered | Low | High | Polling fallback |
| Webhook replay attack | Low | Medium | HMAC signature + timestamp check |
| Concurrent deployments | Medium | Medium | Deployment lock |
| Health check false positive | Low | High | Multiple check types |
| Skill format breakage | Medium | High | Validation before deployment |
| Rate limiting (GitHub API) | Low | Low | Use raw Git clone |

---

## Approach 2: GitHub Polling + Cron Job (Simpler)

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     Polling-Based Skill Sync                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Every N minutes (configurable, default: 5):                            │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 1. Check GitHub for updates (compare HEAD with stored)          │   │
│  │    - GET /repos/Danservfinn/kurultai-skills/git/refs/heads/main  │   │
│  │    - Compare sha with last_deployed_sha                         │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼ (if changed)                             │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 2. Fetch changed files via GitHub API                           │   │
│  │    - GET /repos/.../compare/{old_sha}...{new_sha}                │   │
│  │    - Filter for SKILL.md files                                  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 3. Validate and deploy (same as Approach 1)                     │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  Implementation: Node.js cron job running in moltbot container         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Implementation (Inside moltbot)

```javascript
// moltbot-railway-template/src/skills/poller.js
const cron = require('node-cron');
const octokit = require('octokit');
const { SkillValidator } = require('./validator');
const { SkillDeployer } = require('./deployer');

class SkillPoller {
  constructor() {
    this.octokit = new Octokit({ auth: process.env.GITHUB_TOKEN });
    this.owner = 'Danservfinn';
    this.repo = 'kurultai-skills';
    this.lastSha = null;
  }

  start() {
    // Run every 5 minutes
    cron.schedule('*/5 * * * *', async () => {
      await this.checkForUpdates();
    });

    // Initial check
    this.checkForUpdates();
  }

  async checkForUpdates() {
    try {
      const { data: ref } = await this.octokit.rest.git.getRef({
        owner: this.owner,
        repo: this.repo,
        ref: 'heads/main'
      });

      const currentSha = ref.object.sha;

      if (this.lastSha && this.lastSha === currentSha) {
        return; // No changes
      }

      console.log(`[SkillPoller] New commit detected: ${currentSha}`);

      // Get comparison
      const { data: comparison } = await this.octokit.rest.repos.compareCommits({
        owner: this.owner,
        repo: this.repo,
        base: this.lastSha || currentSha,
        head: currentSha
      });

      // Filter skill files
      const skillFiles = comparison.files
        .filter(f => f.filename.endsWith('SKILL.md'))
        .filter(f => f.status === 'added' || f.status === 'modified');

      if (skillFiles.length === 0) {
        this.lastSha = currentSha;
        return;
      }

      // Deploy
      const deployer = new SkillDeployer();
      await deployer.deployFromGitHub(skillFiles);

      this.lastSha = currentSha;
    } catch (error) {
      console.error('[SkillPoller] Error:', error);
    }
  }
}

module.exports = { SkillPoller };
```

### Pros

| Aspect | Benefit |
|--------|---------|
| **Simplicity** | Runs inside existing moltbot container |
| **No new service** | No additional Railway service needed |
| **No public endpoint** | No webhook security concerns |
| **Full control** | Polling interval configurable |
| **Easier debugging** | Logs in same place as moltbot |

### Cons

| Aspect | Drawback |
|--------|----------|
| **Delay** | Up to polling interval lag (default 5 min) |
| **Wasteful** | Makes requests even when no changes |
| **GitHub API rate limits** | Could hit limits with frequent polling |
| **Push vs Pull** | Not event-driven |
| **Duplicate work** | Each check costs API calls |

### Risk Analysis

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Rate limiting | Medium | Medium | Conditional requests (ETag) |
| High latency | Low | Low | Decrease polling interval |
| API token leak | Low | High | Railway environment variable |
| Git conflicts | Low | Medium | Atomic writes + rollback |

---

## Approach 3: GitHub Actions + Railway API Push

### Architecture

```
GitHub Repository (kurultai-skills)
       │
       │ 1. Push to main
       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     GitHub Actions Workflow                             │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ name: Deploy Skills to Railway                                  │   │
│  │ on:                                                             │   │
│  │   push:                                                         │   │
│  │     branches: [main]                                            │   │
│  │     paths: ['**/SKILL.md']                                      │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 1. Checkout code                                                │   │
│  │ 2. Validate skills (YAML, schema, security)                    │   │
│  │ 3. Package skills as tar.gz                                     │   │
│  │ 4. Deploy via Railway API                                       │   │
│  │    - POST /projects/{id}/services/{service_id}/deploy          │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
       │
       │ 2. Railway API triggers deploy
       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Railway: skill-sync-service                          │
│  - Receives deployment signal                                           │
│  - Extracts skill package                                               │
│  - Hot-reloads moltbot                                                  │
└─────────────────────────────────────────────────────────────────────────┘
```

### GitHub Actions Workflow

```yaml
# .github/workflows/deploy-skills.yml
name: Deploy Skills to Railway

on:
  push:
    branches: [main]
    paths:
      - '**/SKILL.md'
      - '**/skill.md'

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Validate Skills
        run: |
          npm install
          node scripts/validate-skills.js

      - name: Package Skills
        run: |
          tar -czf skills-package.tar.gz \
            $(find . -name 'SKILL.md' -o -name 'skill.md')

      - name: Deploy to Railway
        env:
          RAILWAY_TOKEN: ${{ secrets.RAILWAY_TOKEN }}
          RAILWAY_PROJECT_ID: ${{ secrets.RAILWAY_PROJECT_ID }}
          RAILWAY_SERVICE_ID: ${{ secrets.RAILWAY_SKILL_SYNC_SERVICE_ID }}
        run: |
          curl -X POST \
            "https://backboard.railway.app/graphql/v2" \
            -H "Authorization: Bearer $RAILWAY_TOKEN" \
            -H "Content-Type: application/json" \
            -d @- << EOF
          {
            "query": "mutation(\$projectId: ID!, \$serviceId: ID!, \$image: String!) {
              deployService(projectId: \$projectId, serviceId: \$serviceId, image: \$image) {
                id
                status
              }
            }",
            "variables": {
              "projectId": "$RAILWAY_PROJECT_ID",
              "serviceId": "$RAILWAY_SERVICE_ID",
              "image": "kurultai/skills:${{ github.sha }}"
            }
          }
          EOF
```

### Railway Service for Receiving Packages

```javascript
// skill-sync-service/src/routes/deploy.js
const express = require('express');
const multer = require('multer');
const tar = require('tar');
const router = express.Router();

const upload = multer({ dest: '/tmp/skills/' });

router.post('/deploy', upload.single('package'), async (req, res) => {
  try {
    // Extract tar.gz
    await tar.x({
      file: req.file.path,
      cwd: '/tmp/skills/extracted'
    });

    // Find all SKILL.md files
    const skills = await findSkillFiles('/tmp/skills/extracted');

    // Validate and deploy
    const validator = new SkillValidator();
    const deployer = new SkillDeployer();

    const results = [];
    for (const skill of skills) {
      const validated = await validator.validate(skill);
      if (validated.valid) {
        await deployer.deploySkill(validated.skill);
        results.push({ name: validated.skill.name, status: 'deployed' });
      }
    }

    res.json({ results });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});
```

### Pros

| Aspect | Benefit |
|--------|---------|
| **Declarative** | Workflow is version controlled |
| **CI/CD integration** | Fits existing GitHub Actions patterns |
| **Validation at source** | Catches issues before deploy |
| **No polling** | Event-driven on push |
| **Full context** | Has full repo state available |

### Cons

| Aspect | Drawback |
|--------|----------|
| **Secret management** | Railway token needed in GitHub |
| **Service dependency** | Requires Railway API availability |
| **Indirect** | GitHub -> Railway API -> Service -> Moltbot |
| **Complexity** | Multiple moving pieces |
| **Cold start** | Service may need to wake up |

### Risk Analysis

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Railway token leak | Low | Critical | GitHub secrets encryption |
| API rate limits | Low | Medium | Deploy on path filter |
| Cold start delay | Medium | Low | Railway always-on option |
| Failed deploy notification | Low | Medium | Slack/Discord webhook |

---

## Comparison Matrix

| Criterion | Approach 1: Webhook | Approach 2: Polling | Approach 3: GitHub Actions |
|-----------|-------------------|---------------------|---------------------------|
| **Latency** | ~5-10s | 0-300s (poll interval) | ~30-60s (CI workflow) |
| **Complexity** | Medium | Low | High |
| **New Services** | 1 (skill-sync) | 0 | 1 (skill-sync) |
| **Public Endpoint** | Yes (webhook) | No | No |
| **Secrets** | Webhook secret | GitHub token | Railway token |
| **Cost** | Railway worker | Railway worker | Railway worker + CI minutes |
| **Reliability** | High (event-driven) | Medium (polling) | High (CI) |
| **Debugging** | Medium | Easy | Medium |
| **Rollback** | Built-in | Can add | Built-in |
| **Audit Trail** | Yes (Neo4j) | Yes (Neo4j) | Yes (Neo4j + CI logs) |

---

## Recommended Architecture: Hybrid Webhook + Polling

### Why Hybrid?

1. **Webhook for speed**: Real-time deployment on pushes
2. **Polling for reliability**: Fallback if webhook misses event
3. **Defense in depth**: Multiple paths to ensure sync

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Hybrid Skill Sync                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   GitHub Push                                                           │
│       │                                                                 │
│       ├─── Webhook ────▶ skill-sync-service ──▶ Deploy                  │
│       │                                                   │             │
│       │                                                   ▼             │
│       │                                            /data/skills/        │
│       │                                                   │             │
│       └─── 5 min later ──▶ Poller detects same commit ──▶ Skip (deployed)│
│                                                                         │
│   If webhook fails:                                                     │
│       Poller will catch and deploy within 5 minutes                     │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Implementation Plan

#### Phase 1: Base Infrastructure (1-2 days)
1. Create `skill-sync-service` directory structure
2. Implement `SkillValidator` class
3. Implement `SkillDeployer` class with rollback
4. Add `/data/skills` volume to Railway
5. Implement `SkillReloader` in moltbot

#### Phase 2: Polling Implementation (1 day)
1. Implement `SkillPoller` class
2. Add cron scheduling
3. Add last_sha persistence (Neo4j or file)
4. Test with manual GitHub push

#### Phase 3: Webhook Implementation (1-2 days)
1. Implement webhook handler
2. Add GitHub signature verification
3. Configure GitHub webhook URL
4. Test end-to-end deployment

#### Phase 4: Integration & Testing (1 day)
1. Add health checks
2. Implement audit logging to Neo4j
3. Create deployment dashboard
4. Test rollback scenarios

### Neo4j Schema for Audit Trail

```cypher
// SkillDeployment node
CREATE (sd:SkillDeployment {
  id: randomUUID(),
  timestamp: datetime(),
  commit_sha: string,
  status: 'success' | 'failed' | 'rolled_back',
  skills_count: integer,
  trigger: 'webhook' | 'polling'
})

// SkillVersion node
CREATE (sv:SkillVersion {
  name: string,
  version: string,
  content_sha: string,
  deployed_at: datetime
})

// Relationship
CREATE (sd)-[:DEPLOYED]->(sv)
```

### File Structure

```
skill-sync-service/
├── Dockerfile
├── package.json
├── railway.yml
├── src/
│   ├── index.js                    # Main entry point
│   ├── webhook/
│   │   └── handler.js              # GitHub webhook handler
│   ├── poller/
│   │   └── poller.js               # GitHub polling
│   ├── validators/
│   │   └── skill.js                # Skill validation
│   ├── deployer/
│   │   └── deployer.js             # Deployment with rollback
│   ├── audit/
│   │   └── logger.js               # Neo4j audit logging
│   └── config/
│       └── constants.js            # Configuration
└── tests/
    ├── webhook.test.js
    ├── validator.test.js
    └── deployer.test.js

moltbot-railway-template/
├── src/
│   ├── skills/
│   │   ├── reloader.js             # Hot-reload on file change
│   │   └── registry.js             # In-memory skill registry
```

### Monitoring

```javascript
// Health endpoint response
{
  "status": "healthy",
  "timestamp": "2026-02-07T12:00:00Z",
  "services": {
    "poller": {
      "status": "running",
      "last_check": "2026-02-07T11:58:00Z",
      "last_deployed_sha": "abc123..."
    },
    "webhook": {
      "status": "enabled",
      "last_received": "2026-02-07T11:55:00Z"
    },
    "skills": {
      "count": 45,
      "last_updated": "2026-02-07T11:55:00Z"
    }
  },
  "last_deployment": {
    "id": "dep-abc123",
    "timestamp": "2026-02-07T11:55:00Z",
    "commit_sha": "abc123...",
    "status": "success"
  }
}
```

---

## Failure Mode Analysis

### Scenario 1: GitHub Webhook Not Delivered

**Detection**: Poller sees new sha after 5 minutes

**Recovery**:
1. Poller fetches changes via GitHub API
2. Validates and deploys
3. Logs "deployed via polling fallback"

**Prevention**: Monitor webhook delivery in GitHub repo settings

### Scenario 2: Skill Validation Fails

**Detection**: Validator returns `valid: false`

**Recovery**:
1. Reject deployment
2. Send alert (Slack/email)
3. Keep previous version running
4. Log to Neo4j for investigation

### Scenario 3: Health Check Fails Post-Deploy

**Detection**: `healthCheck()` returns false

**Recovery**:
1. Automatic rollback to backup
2. Log rollback to Neo4j
3. Send alert with error details
4. Prevent auto-retry (manual intervention needed)

### Scenario 4: Concurrent Deployments

**Detection**: Second deploy starts while first is in progress

**Recovery**:
1. Deployment lock (file-based or Redis)
2. Second deploy waits or queues
3. Process in FIFO order

### Scenario 5: GitHub API Rate Limit

**Detection**: API returns 403

**Recovery**:
1. Use conditional requests (ETag/Last-Modified)
2. Fall back to full git clone (no rate limit)
3. Back off exponentially

---

## Security Considerations

### Webhook Security

```javascript
// Verify GitHub webhook signature
function verifyGitHubSignature(payload, signature) {
  const secret = process.env.GITHUB_WEBHOOK_SECRET;
  const hmac = crypto.createHmac('sha256', secret);
  const digest = `sha256=${hmac.update(payload).digest('hex')}`;
  return crypto.timingSafeEqual(
    Buffer.from(signature),
    Buffer.from(digest)
  );
}

// Also check timestamp to prevent replay attacks
function checkTimestamp(headers) {
  const timestamp = parseInt(headers['x-github-delivery']);
  const now = Date.now() / 1000;
  return Math.abs(now - timestamp) < 300; // 5 minute window
}
```

### Skill Content Security

1. **No code execution**: Skills are markdown, not code
2. **Secret scanning**: Regex patterns for API keys
3. **Sandbox validation**: Parse in isolated context
4. **Size limits**: Max 100KB per skill file

### Access Control

1. **GitHub webhook**: Only verify signature, no auth
2. **Polling**: Use read-only GitHub token
3. **Railway internal**: Services communicate via internal URLs
4. **Audit log**: All deployments logged to Neo4j

---

## Estimated Costs

| Resource | Quantity | Unit Cost | Monthly Cost |
|----------|----------|-----------|--------------|
| Railway Worker (skill-sync) | 1 | ~$5-10/month | $5-10 |
| GitHub Actions (CI minutes) | ~100/month | Free tier covered | $0 |
| Storage (/data/skills) | ~100MB | Included in volume | $0 |
| Neo4j (audit logs) | ~1000 nodes | Included in AuraDB | $0 |
| **Total** | | | **$5-10/month** |

---

## Next Steps

1. **Review this analysis** with team
2. **Choose approach** (Hybrid recommended)
3. **Create GitHub issue** for implementation tracking
4. **Set up development environment**
5. **Implement Phase 1** (Base Infrastructure)
6. **Test with sample skill**
7. **Deploy to Railway staging**
8. **Production rollout**

---

## Appendix A: Environment Variables

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `SKILLS_DIR` | Yes | Target directory for deployed skills | `/data/skills` |
| `BACKUP_DIR` | Yes | Backup location for rollback | `/data/backups/skills` |
| `GITHUB_WEBHOOK_SECRET` | Yes | GitHub webhook HMAC secret | `random-32-bytes` |
| `GITHUB_TOKEN` | Yes | GitHub PAT for polling API | `ghp_xxx` |
| `GITHUB_OWNER` | No | Repo owner (default: Danservfinn) | `Danservfinn` |
| `GITHUB_REPO` | No | Repo name (default: kurultai-skills) | `kurultai-skills` |
| `POLLING_INTERVAL_MIN` | No | Polling interval in minutes | `5` |
| `NEO4J_URI` | Yes | Neo4j connection for audit | `neo4j+s://...` |
| `NEO4J_USER` | Yes | Neo4j username | `neo4j` |
| `NEO4J_PASSWORD` | Yes | Neo4j password | `***` |
| `DEPLOYMENT_LOCK_TTL` | No | Lock timeout (seconds) | `300` |
| `MAX_SKILL_SIZE_BYTES` | No | Max skill file size | `102400` |

---

## Appendix B: Example Deployment Flow

```
1. Developer pushes update to golden-horde/SKILL.md
   git commit -m "fix: Improve pattern selection"
   git push origin main

2. GitHub sends webhook
   POST https://kublai.kurult.ai/webhook/github
   X-Hub-Signature-256: sha256=...
   Payload: { ref: "refs/heads/main", commits: [...] }

3. skill-sync-service receives webhook
   - Verify signature ✓
   - Extract changed files: ["golden-horde/SKILL.md"]
   - Fetch content from GitHub API ✓
   - Validate YAML frontmatter ✓
   - Scan for secrets ✓
   - Create backup: /data/backups/skills/dep-abc123 ✓

4. Deploy
   - Write to /data/skills/golden-horde.md (atomic rename) ✓
   - Moltbot detects file change (chokidar) ✓
   - Hot-reload skill registry ✓
   - Health check: curl /health?check=skills ✓

5. Audit
   - Create SkillDeployment node in Neo4j ✓
   - Log deployment metrics ✓

6. Response
   HTTP 200
   {
     "deploymentId": "dep-abc123",
     "status": "deployed",
     "skills": ["golden-horde"],
     "version": "2.1"
   }
```

---

**Document Version**: 1.0
**Last Updated**: 2026-02-07
