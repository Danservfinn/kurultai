/**
 * Moltbot Railway Template - Gateway Entry Point
 * OpenClaw Gateway with embedded Signal integration
 */

const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const winston = require('winston');
const { spawn } = require('child_process');
const path = require('path');

// Import Signal channel configuration
const signalConfig = require('./config/channels');

// Import route handlers
const authRoutes = require('../routes/auth');
const healthRoutes = require('../routes/health');
const requestLogger = require('../middleware/logger');

// Import Kublai self-awareness modules
const { ArchitectureIntrospection, ProactiveReflection, ScheduledReflection } = require('./kublai');
const { ProposalStateMachine, ProposalMapper, ValidationHandler } = require('./workflow');

// =============================================================================
// Logger Configuration
// =============================================================================

// Log rotation for persistent file logs
const DailyRotateFile = require('winston-daily-rotate-file');

const transports = [
  new winston.transports.Console({
    format: winston.format.combine(
      winston.format.colorize(),
      winston.format.simple()
    )
  })
];

// Add file rotation transport in production
if (process.env.NODE_ENV === 'production') {
  transports.push(
    new DailyRotateFile({
      filename: '/data/logs/moltbot-%DATE%.log',
      datePattern: 'YYYY-MM-DD',
      maxSize: '100m',
      maxFiles: '5d',
      format: winston.format.combine(
        winston.format.timestamp(),
        winston.format.json()
      )
    })
  );
}

const logger = winston.createLogger({
  level: process.env.LOG_LEVEL || 'info',
  format: winston.format.combine(
    winston.format.timestamp(),
    winston.format.errors({ stack: true }),
    winston.format.json()
  ),
  defaultMeta: { service: 'moltbot-gateway' },
  transports,
});

// =============================================================================
// Signal CLI Process Management
// =============================================================================

let signalCliProcess = null;
let signalCliReady = false;

/**
 * Start signal-cli daemon process
 * @returns {Promise<boolean>}
 */
async function startSignalCli() {
  if (!signalConfig.enabled) {
    logger.info('Signal channel is disabled');
    return false;
  }

  const signalCliPath = process.env.SIGNAL_CLI_PATH || '/usr/local/bin/signal-cli';
  const signalDataDir = process.env.SIGNAL_DATA_DIR || '/data/.signal';
  const signalAccount = process.env.SIGNAL_ACCOUNT;

  if (!signalAccount) {
    logger.error('SIGNAL_ACCOUNT environment variable is required');
    return false;
  }

  // Log with redacted account number for privacy
  logger.info('Starting signal-cli daemon...', {
    cliPath: signalCliPath,
    dataDir: signalDataDir,
    account: signalAccount ? `${signalAccount.slice(0, 4)}****` : undefined
  });

  return new Promise((resolve, reject) => {
    // Start signal-cli in daemon mode with HTTP interface
    // Bind to localhost only for security
    signalCliProcess = spawn(signalCliPath, [
      '--config', signalDataDir,
      'daemon',
      '--http', '127.0.0.1:8081'
    ], {
      stdio: ['ignore', 'pipe', 'pipe'],
      env: { ...process.env }
    });

    let stdoutBuffer = '';
    let stderrBuffer = '';

    signalCliProcess.stdout.on('data', (data) => {
      stdoutBuffer += data.toString();
      const lines = stdoutBuffer.split('\n');
      stdoutBuffer = lines.pop(); // Keep incomplete line in buffer

      lines.forEach(line => {
        if (line.trim()) {
          logger.info('[signal-cli]', { message: line.trim() });
        }
      });
    });

    signalCliProcess.stderr.on('data', (data) => {
      stderrBuffer += data.toString();
      const lines = stderrBuffer.split('\n');
      stderrBuffer = lines.pop();

      lines.forEach(line => {
        if (line.trim()) {
          logger.warn('[signal-cli]', { message: line.trim() });
        }
      });
    });

    signalCliProcess.on('error', (error) => {
      logger.error('Failed to start signal-cli', { error: error.message });
      reject(error);
    });

    signalCliProcess.on('exit', (code) => {
      if (code !== 0) {
        logger.error('signal-cli exited unexpectedly', { exitCode: code });
        signalCliReady = false;
      }
    });

    // Wait for signal-cli to be ready
    setTimeout(() => {
      logger.info('signal-cli daemon startup timeout reached, checking health...');
      checkSignalCliHealth().then(healthy => {
        if (healthy) {
          signalCliReady = true;
          logger.info('signal-cli daemon is ready');
          resolve(true);
        } else {
          logger.warn('signal-cli health check failed, but continuing...');
          // Still resolve to true - health check will retry
          resolve(true);
        }
      }).catch(err => {
        logger.error('Health check error during startup', { error: err.message });
        resolve(true); // Continue anyway
      });
    }, 5000);
  });
}

/**
 * Check if signal-cli is healthy
 * @returns {Promise<boolean>}
 */
async function checkSignalCliHealth() {
  if (!signalConfig.enabled) {
    return true;
  }

  const signalCliPath = process.env.SIGNAL_CLI_PATH || '/usr/local/bin/signal-cli';
  const signalDataDir = process.env.SIGNAL_DATA_DIR || '/data/.signal';

  return new Promise((resolve) => {
    const checkProcess = spawn(signalCliPath, [
      '--config', signalDataDir,
      'listAccounts'
    ], {
      timeout: 10000
    });

    let output = '';
    checkProcess.stdout.on('data', (data) => {
      output += data.toString();
    });

    checkProcess.on('close', (code) => {
      if (code === 0) {
        logger.info('signal-cli health check passed', { accounts: output.trim() });
        resolve(true);
      } else {
        logger.warn('signal-cli health check failed', { exitCode: code });
        resolve(false);
      }
    });

    checkProcess.on('error', (error) => {
      logger.error('signal-cli health check error', { error: error.message });
      resolve(false);
    });
  });
}

/**
 * Stop signal-cli daemon gracefully
 */
async function stopSignalCli() {
  if (signalCliProcess) {
    logger.info('Stopping signal-cli daemon...');
    signalCliProcess.kill('SIGTERM');

    // Wait for graceful shutdown
    await new Promise(resolve => setTimeout(resolve, 5000));

    if (signalCliProcess && !signalCliProcess.killed) {
      logger.warn('Force killing signal-cli daemon');
      signalCliProcess.kill('SIGKILL');
    }

    signalCliReady = false;
    signalCliProcess = null;
  }
}

// =============================================================================
// Kublai Self-Awareness Module Instances
// =============================================================================

let neo4jDriver = null;
let architectureIntrospection = null;
let proactiveReflection = null;
let scheduledReflection = null;
let proposalStateMachine = null;
let proposalMapper = null;
let validationHandler = null;

/**
 * Initialize Kublai self-awareness modules with Neo4j
 */
async function initKublaiModules() {
  const NEO4J_URI = process.env.NEO4J_URI;
  const NEO4J_USER = process.env.NEO4J_USER || 'neo4j';
  const NEO4J_PASSWORD = process.env.NEO4J_PASSWORD;

  if (!NEO4J_URI || !NEO4J_PASSWORD) {
    logger.warn('[Kublai] Neo4j not configured, self-awareness modules disabled');
    return false;
  }

  try {
    const neo4j = require('neo4j-driver');
    neo4jDriver = neo4j.driver(
      NEO4J_URI,
      neo4j.auth.basic(NEO4J_USER, NEO4J_PASSWORD)
    );

    // Verify connectivity
    await neo4jDriver.verifyConnectivity();
    logger.info('[Kublai] Neo4j connected');

    // Initialize modules
    architectureIntrospection = new ArchitectureIntrospection(neo4jDriver, logger);
    proactiveReflection = new ProactiveReflection(neo4jDriver, architectureIntrospection, logger);
    scheduledReflection = new ScheduledReflection(proactiveReflection, logger);
    proposalStateMachine = new ProposalStateMachine(neo4jDriver, logger);
    proposalMapper = new ProposalMapper(neo4jDriver, logger);
    validationHandler = new ValidationHandler(neo4jDriver, logger);

    // Start scheduled reflection
    scheduledReflection.start();

    logger.info('[Kublai] Self-awareness modules initialized');
    return true;
  } catch (error) {
    logger.error('[Kublai] Failed to initialize', { error: error.message });
    return false;
  }
}

/**
 * Stop Kublai modules gracefully
 */
async function stopKublaiModules() {
  if (scheduledReflection) {
    scheduledReflection.stop();
    logger.info('[Kublai] Scheduled reflection stopped');
  }
  if (neo4jDriver) {
    await neo4jDriver.close();
    logger.info('[Kublai] Neo4j driver closed');
  }
}

// =============================================================================
// Express Gateway Setup
// =============================================================================

const app = express();
const PORT = process.env.PORT || 8080;

// Security middleware
app.use(helmet({
  contentSecurityPolicy: false // Disable CSP for API-only service
}));
app.use(cors({
  origin: process.env.ALLOWED_ORIGINS?.split(',') || false,
  credentials: true
}));
app.use(express.json({ limit: '100kb' }));

// Structured request logging (method, path, statusCode, duration)
app.use(requestLogger(logger));

// =============================================================================
// Health Check Endpoint
// =============================================================================

app.get('/health', async (req, res) => {
  const health = {
    status: 'healthy',
    timestamp: new Date().toISOString(),
    uptime: process.uptime(),
    version: process.env.npm_package_version || '1.0.0',
    signal: {
      enabled: signalConfig.enabled,
      ready: signalCliReady
    },
    kublai: {
      neo4jConnected: !!neo4jDriver,
      reflectionScheduled: !!scheduledReflection,
      modulesLoaded: !!(architectureIntrospection && proposalStateMachine)
    }
  };

  // Check signal-cli health if enabled
  if (signalConfig.enabled) {
    const signalHealthy = await checkSignalCliHealth();
    health.signal.ready = signalHealthy;

    if (!signalHealthy) {
      health.status = 'degraded';
    }
  }

  // Check Neo4j connectivity for Kublai
  if (neo4jDriver) {
    try {
      const session = neo4jDriver.session();
      await session.run('RETURN 1');
      await session.close();
    } catch (error) {
      health.kublai.neo4jConnected = false;
      health.status = 'degraded';
    }
  }

  const statusCode = health.status === 'healthy' ? 200 : 503;
  res.status(statusCode).json(health);
});

// =============================================================================
// Auth API Endpoint
// =============================================================================

app.use('/api/auth', authRoutes);
app.use('/health', healthRoutes);

// =============================================================================
// Signal Status Endpoint
// =============================================================================

app.get('/signal/status', async (req, res) => {
  if (!signalConfig.enabled) {
    return res.status(503).json({
      enabled: false,
      message: 'Signal channel is disabled'
    });
  }

  const healthy = await checkSignalCliHealth();

  res.json({
    enabled: true,
    ready: healthy,
    account: process.env.SIGNAL_ACCOUNT,
    dataDir: process.env.SIGNAL_DATA_DIR,
    policies: {
      dmPolicy: signalConfig.dmPolicy,
      groupPolicy: signalConfig.groupPolicy
    }
  });
});

// =============================================================================
// Proposal System Migration Endpoint
// =============================================================================

app.post('/api/migrate-proposals', async (req, res) => {
  if (!neo4jDriver) {
    return res.status(503).json({ error: 'Neo4j not connected' });
  }

  // Full v4 migration: 5 constraints + 17 property indexes + 6 relationship indexes
  const statements = [
    // Constraints
    "CREATE CONSTRAINT proposal_id_unique IF NOT EXISTS FOR (p:ArchitectureProposal) REQUIRE p.id IS UNIQUE",
    "CREATE CONSTRAINT opportunity_id_unique IF NOT EXISTS FOR (o:ImprovementOpportunity) REQUIRE o.id IS UNIQUE",
    "CREATE CONSTRAINT vetting_id_unique IF NOT EXISTS FOR (v:Vetting) REQUIRE v.id IS UNIQUE",
    "CREATE CONSTRAINT implementation_id_unique IF NOT EXISTS FOR (i:Implementation) REQUIRE i.id IS UNIQUE",
    "CREATE CONSTRAINT validation_id_unique IF NOT EXISTS FOR (v:Validation) REQUIRE v.id IS UNIQUE",
    // ArchitectureProposal indexes
    "CREATE INDEX proposal_status IF NOT EXISTS FOR (p:ArchitectureProposal) ON (p.status)",
    "CREATE INDEX proposal_priority IF NOT EXISTS FOR (p:ArchitectureProposal) ON (p.priority)",
    "CREATE INDEX proposal_created_at IF NOT EXISTS FOR (p:ArchitectureProposal) ON (p.created_at)",
    "CREATE INDEX proposal_implementation_status IF NOT EXISTS FOR (p:ArchitectureProposal) ON (p.implementation_status)",
    // ImprovementOpportunity indexes
    "CREATE INDEX opportunity_status IF NOT EXISTS FOR (o:ImprovementOpportunity) ON (o.status)",
    "CREATE INDEX opportunity_priority IF NOT EXISTS FOR (o:ImprovementOpportunity) ON (o.priority)",
    "CREATE INDEX opportunity_type IF NOT EXISTS FOR (o:ImprovementOpportunity) ON (o.type)",
    "CREATE INDEX opportunity_proposed_by IF NOT EXISTS FOR (o:ImprovementOpportunity) ON (o.proposed_by)",
    // Vetting indexes
    "CREATE INDEX vetting_proposal IF NOT EXISTS FOR (v:Vetting) ON (v.proposal_id)",
    "CREATE INDEX vetting_vetted_by IF NOT EXISTS FOR (v:Vetting) ON (v.vetted_by)",
    "CREATE INDEX vetting_created_at IF NOT EXISTS FOR (v:Vetting) ON (v.created_at)",
    // Implementation indexes
    "CREATE INDEX implementation_proposal IF NOT EXISTS FOR (i:Implementation) ON (i.proposal_id)",
    "CREATE INDEX implementation_status IF NOT EXISTS FOR (i:Implementation) ON (i.status)",
    "CREATE INDEX implementation_started_at IF NOT EXISTS FOR (i:Implementation) ON (i.started_at)",
    // Validation indexes
    "CREATE INDEX validation_implementation IF NOT EXISTS FOR (v:Validation) ON (v.implementation_id)",
    "CREATE INDEX validation_passed IF NOT EXISTS FOR (v:Validation) ON (v.passed)",
    "CREATE INDEX validation_validated_at IF NOT EXISTS FOR (v:Validation) ON (v.validated_at)",
    // Relationship indexes
    "CREATE INDEX evolves_into IF NOT EXISTS FOR ()-[r:EVOLVES_INTO]->() ON (r.created_at)",
    "CREATE INDEX updates_section IF NOT EXISTS FOR ()-[r:UPDATES_SECTION]->() ON (r.target_section)",
    "CREATE INDEX synced_to IF NOT EXISTS FOR ()-[r:SYNCED_TO]->() ON (r.synced_at)",
    "CREATE INDEX has_vetting IF NOT EXISTS FOR ()-[r:HAS_VETTING]->() ON (r.created_at)",
    "CREATE INDEX implemented_by IF NOT EXISTS FOR ()-[r:IMPLEMENTED_BY]->() ON (r.started_at)",
    "CREATE INDEX validated_by IF NOT EXISTS FOR ()-[r:VALIDATED_BY]->() ON (r.validated_at)"
  ];

  const results = [];

  for (const statement of statements) {
    const session = neo4jDriver.session();
    try {
      await session.run(statement);
      results.push({ statement: statement.substring(0, 60) + '...', status: 'success' });
    } catch (error) {
      if (error.message.includes('AlreadyExists') || error.message.includes('equivalent')) {
        results.push({ statement: statement.substring(0, 60) + '...', status: 'skipped (exists)' });
      } else {
        results.push({ statement: statement.substring(0, 60) + '...', status: 'failed', error: error.message });
      }
    } finally {
      await session.close();
    }
  }

  const succeeded = results.filter(r => r.status === 'success').length;
  const skipped = results.filter(r => r.status.startsWith('skipped')).length;
  const failed = results.filter(r => r.status === 'failed').length;

  res.json({
    migration: 'v4_proposals',
    summary: { total: statements.length, succeeded, skipped, failed },
    results,
    status: failed === 0 ? 'complete' : 'partial'
  });
});

// =============================================================================
// Proposals API Endpoints
// =============================================================================

app.get('/api/proposals', async (req, res) => {
  if (!proposalStateMachine) {
    return res.status(503).json({ error: 'Proposal system not initialized' });
  }
  try {
    const status = req.query.status || 'proposed';
    const proposals = await proposalStateMachine.listByStatus(status);
    res.json({ proposals, count: proposals.length });
  } catch (error) {
    logger.error('Failed to list proposals', { error: error.message });
    res.status(500).json({ error: 'Failed to list proposals' });
  }
});

app.post('/api/proposals/reflect', async (req, res) => {
  if (!proactiveReflection) {
    return res.status(503).json({ error: 'Reflection system not initialized' });
  }
  try {
    const result = await proactiveReflection.triggerReflection();
    res.json(result);
  } catch (error) {
    logger.error('Reflection trigger failed', { error: error.message });
    res.status(500).json({ error: 'Failed to trigger reflection' });
  }
});

app.get('/api/proposals/ready-to-sync', async (req, res) => {
  if (!proposalMapper) {
    return res.status(503).json({ error: 'Proposal mapper not initialized' });
  }
  try {
    const proposals = await proposalMapper.getReadyToSync();
    res.json({ proposals, count: proposals.length });
  } catch (error) {
    logger.error('Failed to get ready-to-sync proposals', { error: error.message });
    res.status(500).json({ error: 'Failed to get ready-to-sync proposals' });
  }
});

// =============================================================================
// Gateway Root Endpoint
// =============================================================================

app.get('/', (req, res) => {
  res.json({
    name: 'Moltbot Railway Template',
    description: 'OpenClaw Gateway with embedded Signal integration',
    version: process.env.npm_package_version || '1.0.0',
    channels: {
      signal: signalConfig.enabled ? 'enabled' : 'disabled'
    },
    kublai: {
      selfAwareness: !!architectureIntrospection ? 'active' : 'inactive',
      proposalSystem: !!proposalStateMachine ? 'active' : 'inactive'
    },
    endpoints: {
      health: '/health',
      signalStatus: '/signal/status',
      proposals: '/api/proposals',
      triggerReflection: '/api/proposals/reflect',
      readyToSync: '/api/proposals/ready-to-sync',
      migrateProposals: '/api/migrate-proposals'
    }
  });
});

// =============================================================================
// Error Handling
// =============================================================================

app.use((err, req, res, next) => {
  logger.error('Unhandled error', { error: err.message, stack: err.stack });
  res.status(500).json({
    error: 'Internal server error',
    message: process.env.NODE_ENV === 'development' ? err.message : undefined
  });
});

// =============================================================================
// Graceful Shutdown
// =============================================================================

async function gracefulShutdown(signal) {
  logger.info(`Received ${signal}, starting graceful shutdown...`);

  // Stop Kublai modules
  await stopKublaiModules();

  // Stop signal-cli
  await stopSignalCli();

  // Close HTTP server
  const srv = global.server;
  if (srv) {
    srv.close(() => {
      logger.info('HTTP server closed');
      process.exit(0);
    });
  } else {
    process.exit(0);
  }

  // Force exit after timeout
  setTimeout(() => {
    logger.error('Forced shutdown due to timeout');
    process.exit(1);
  }, 30000);
}

process.on('SIGTERM', () => gracefulShutdown('SIGTERM'));
process.on('SIGINT', () => gracefulShutdown('SIGINT'));

// =============================================================================
// Server Startup
// =============================================================================

async function main() {
  logger.info('Starting Moltbot Gateway...');

  // Initialize Kublai self-awareness modules
  const kublaiReady = await initKublaiModules();

  // Start signal-cli if enabled
  if (signalConfig.enabled) {
    try {
      await startSignalCli();
    } catch (error) {
      logger.error('Failed to start signal-cli, continuing without Signal support', {
        error: error.message
      });
      signalCliReady = false;
    }
  }

  // Start HTTP server
  const server = app.listen(PORT, () => {
    logger.info(`Moltbot Gateway listening on port ${PORT}`, {
      port: PORT,
      signalEnabled: signalConfig.enabled,
      signalReady: signalCliReady,
      kublaiReady
    });
  });

  // Make server available for graceful shutdown
  global.server = server;
}

// Start the application only if this file is run directly (not imported for testing)
if (require.main === module) {
  main().catch(error => {
    logger.error('Fatal error during startup', { error: error.message });
    process.exit(1);
  });
}

module.exports = {
  app, startSignalCli, stopSignalCli, checkSignalCliHealth, main,
  initKublaiModules, stopKublaiModules
};
