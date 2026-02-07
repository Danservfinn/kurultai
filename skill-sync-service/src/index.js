/**
 * Skill Sync Service - Main Entry Point
 * Hybrid webhook + polling service for GitHub to Railway skill sync
 */

require('dotenv').config();

const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const winston = require('winston');
const { Octokit } = require('octokit');
const rateLimit = require('express-rate-limit');

const { WebhookHandler } = require('./webhook/handler');
const { GitHubPoller } = require('./poller/poller');
const { AuditLogger } = require('./audit/logger');
const { SkillDeployer } = require('./deployer/deployer');
const constants = require('./config/constants');

// =============================================================================
// Logger Configuration
// =============================================================================

const logger = winston.createLogger({
  level: constants.LOG_LEVEL,
  format: winston.format.combine(
    winston.format.timestamp(),
    winston.format.errors({ stack: true }),
    winston.format.json()
  ),
  defaultMeta: { service: 'skill-sync-service' },
  transports: [
    new winston.transports.Console({
      format: winston.format.combine(
        winston.format.colorize(),
        winston.format.simple()
      )
    })
  ]
});

// =============================================================================
// Express App
// =============================================================================

const app = express();
const PORT = process.env.PORT || 3000;

app.use(helmet());
app.use(cors());
app.use(express.json({ limit: '10mb' }));

// Rate limiting for webhook endpoint
const webhookLimiter = rateLimit({
  windowMs: 60 * 1000, // 1 minute
  max: 10, // 10 webhooks per minute
  message: { error: 'Too many webhook requests' },
  standardHeaders: true,
  legacyHeaders: false,
});

// =============================================================================
// Initialize Services
// =============================================================================

let auditLogger, deployer, webhookHandler, poller, octokit;

async function initializeServices() {
  logger.info('Initializing services...');

  // Initialize audit logger
  auditLogger = new AuditLogger({ logger });
  await auditLogger.connect();

  // Initialize deployer
  deployer = new SkillDeployer({ logger });

  // Initialize GitHub client
  if (constants.GITHUB_TOKEN) {
    octokit = new Octokit({ auth: constants.GITHUB_TOKEN });
  } else {
    logger.warn('No GITHUB_TOKEN configured, poller will not work');
  }

  // Initialize webhook handler
  webhookHandler = new WebhookHandler({
    githubSecret: constants.GITHUB_WEBHOOK_SECRET,
    validator: null, // Will use default
    deployer,
    audit: auditLogger,
    logger,
    github: octokit
  });

  // Initialize poller
  if (octokit) {
    poller = new GitHubPoller({
      github: octokit,
      validator: null,
      deployer,
      audit: auditLogger,
      logger
    });

    // Load last SHA
    await poller.loadLastSha();

    // Start polling
    poller.start();
  }

  logger.info('Services initialized');
}

// =============================================================================
// Routes
// =============================================================================

// API Key middleware for manual sync endpoint
const requireApiKey = (req, res, next) => {
  const apiKey = process.env.MANUAL_SYNC_API_KEY;
  if (!apiKey) {
    return res.status(500).json({ error: 'API key not configured' });
  }
  const clientKey = req.headers['x-api-key'];
  if (clientKey !== apiKey) {
    return res.status(403).json({ error: 'Invalid API key' });
  }
  next();
};

app.get('/health', async (req, res) => {
  const deployedSkills = await deployer.listDeployed();
  const recentDeployments = auditLogger.connected
    ? await auditLogger.getRecentDeployments(5)
    : [];

  res.json({
    status: 'healthy',
    timestamp: new Date().toISOString(),
    services: {
      poller: {
        status: poller?.isPolling ? 'running' : 'disabled',
        lastCheck: poller?.lastSha || 'never'
      },
      webhook: {
        status: 'enabled',
        configured: !!constants.GITHUB_WEBHOOK_SECRET
      },
      audit: {
        status: auditLogger?.connected ? 'connected' : 'disconnected'
      }
    },
    skills: {
      count: deployedSkills.length,
      lastUpdated: deployedSkills.length > 0
        ? deployedSkills.map(s => s.name).sort()
        : []
    },
    recentDeployments: recentDeployments.slice(0, 3)
  });
});

app.get('/skills', async (req, res) => {
  const skills = await deployer.listDeployed();
  res.json({ skills });
});

app.post('/webhook/github', webhookLimiter, (req, res) => {
  webhookHandler.handle(req, res);
});

// Manual trigger endpoint for testing (requires API key)
app.post('/api/sync', requireApiKey, async (req, res) => {
  if (!poller) {
    return res.status(503).json({ error: 'Poller not available' });
  }

  try {
    await poller.checkForUpdates();
    res.json({ status: 'sync triggered' });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// =============================================================================
// Graceful Shutdown
// =============================================================================

async function shutdown() {
  logger.info('Shutting down...');

  if (poller) {
    poller.stop();
  }

  if (auditLogger) {
    await auditLogger.close();
  }

  process.exit(0);
}

process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);

// =============================================================================
// Start Server
// =============================================================================

(async () => {
  try {
    await initializeServices();

    app.listen(PORT, () => {
      logger.info(`Skill Sync Service listening on port ${PORT}`);
      logger.info(`Webhook endpoint: http://localhost:${PORT}/webhook/github`);
      logger.info(`Health check: http://localhost:${PORT}/health`);
    });
  } catch (e) {
    logger.error(`Failed to start: ${e.message}`);
    process.exit(1);
  }
})();
