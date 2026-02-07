/**
 * Health Check Routes
 *
 * Provides detailed health check endpoints for monitoring and Railway health checks.
 * - GET /health - Main health status (used by Railway health checks)
 * - GET /health/neo4j - Neo4j database connectivity
 * - GET /health/disk - Disk usage statistics
 */

const express = require('express');
const { execSync } = require('child_process');
const router = express.Router();

/**
 * GET /health/neo4j
 * Check Neo4j database connectivity via internal Railway network.
 */
router.get('/neo4j', async (req, res) => {
  const neo4jUri = process.env.NEO4J_URI || process.env.NEO4J_BOLT_URL;

  if (!neo4jUri) {
    return res.status(503).json({
      status: 'unconfigured',
      message: 'NEO4J_URI not set',
    });
  }

  try {
    // Attempt TCP connection to Neo4j bolt port
    const url = new URL(neo4jUri.replace('bolt://', 'http://').replace('neo4j+s://', 'https://'));
    const host = url.hostname;
    const port = url.port || 7687;

    // Use a simple TCP check via Node.js net module
    const net = require('net');
    const connected = await new Promise((resolve) => {
      const socket = new net.Socket();
      socket.setTimeout(5000);
      socket.on('connect', () => {
        socket.destroy();
        resolve(true);
      });
      socket.on('timeout', () => {
        socket.destroy();
        resolve(false);
      });
      socket.on('error', () => {
        socket.destroy();
        resolve(false);
      });
      socket.connect(port, host);
    });

    if (connected) {
      res.json({
        status: 'connected',
        host,
        port: parseInt(port),
      });
    } else {
      res.status(503).json({
        status: 'unreachable',
        host,
        port: parseInt(port),
      });
    }
  } catch (error) {
    res.status(503).json({
      status: 'error',
      message: error.message,
    });
  }
});

/**
 * GET /health/disk
 * Report disk usage for the /data volume.
 */
router.get('/disk', (req, res) => {
  try {
    const output = execSync('df -h /data 2>/dev/null || df -h /', {
      timeout: 5000,
      encoding: 'utf-8',
    });

    const lines = output.trim().split('\n');
    if (lines.length >= 2) {
      const parts = lines[1].split(/\s+/);
      res.json({
        status: 'ok',
        filesystem: parts[0],
        size: parts[1],
        used: parts[2],
        available: parts[3],
        usePercent: parts[4],
        mountpoint: parts[5],
      });
    } else {
      res.json({ status: 'ok', raw: output });
    }
  } catch (error) {
    res.status(503).json({
      status: 'error',
      message: error.message,
    });
  }
});

/**
 * GET /health/file-consistency
 * Report file consistency monitor status.
 * Reads from a status file written by the Python Ogedei file monitor.
 */
router.get('/file-consistency', (req, res) => {
  const fs = require('fs');
  const statusPath = '/data/file-monitor-status.json';

  try {
    if (fs.existsSync(statusPath)) {
      const data = JSON.parse(fs.readFileSync(statusPath, 'utf-8'));
      const age = Date.now() - new Date(data.last_scan_time || 0).getTime();
      const stale = age > 600000; // > 10 minutes = stale

      res.json({
        status: stale ? 'stale' : 'ok',
        lastScanTime: data.last_scan_time,
        lastSeverity: data.last_severity,
        scanCount: data.scan_count,
        ageSeconds: Math.round(age / 1000),
      });
    } else {
      res.json({
        status: 'not_running',
        message: 'File consistency monitor has not run yet',
      });
    }
  } catch (error) {
    res.status(503).json({
      status: 'error',
      message: error.message,
    });
  }
});

module.exports = router;
