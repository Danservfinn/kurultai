/**
 * File-based deployment lock
 * Prevents concurrent deployments
 */

const fs = require('fs').promises;
const path = require('path');
const constants = require('../config/constants');

const locks = new Map();
const LOCK_DIR = '/tmp/skill-sync-locks';

/**
 * Acquire a lock
 */
async function acquire(key, ttl = 300) {
  await fs.mkdir(LOCK_DIR, { recursive: true });

  const lockPath = path.join(LOCK_DIR, `${key}.lock`);
  const lockId = `${process.pid}-${Date.now()}`;

  try {
    // Check if lock exists and is valid
    const existing = await fs.readFile(lockPath, 'utf8').catch(() => null);
    if (existing) {
      const [pid, timestamp] = existing.split(':');
      const age = (Date.now() - parseInt(timestamp)) / 1000;

      // Check if lock is expired
      if (age < ttl) {
        // Check if process is still running
        try {
          process.kill(parseInt(pid), 0);
          throw new Error(`Lock held by process ${parseInt(pid)}`);
        } catch (e) {
          // Process is dead, can acquire lock
        }
      }
    }

    // Write lock
    await fs.writeFile(lockPath, `${process.pid}:${Date.now()}`, 'utf8');

    locks.set(key, { lockId, lockPath });

    // Return release function
    return async () => {
      try {
        const current = await fs.readFile(lockPath, 'utf8').catch(() => null);
        if (current && current.startsWith(`${process.pid}:`)) {
          await fs.unlink(lockPath);
        }
      } catch (e) {
        // Lock already released or expired
      }
      locks.delete(key);
    };
  } catch (e) {
    throw new Error(`Failed to acquire lock: ${e.message}`);
  }
}

/**
 * Check if a key is locked
 */
async function isLocked(key) {
  const lockPath = path.join(LOCK_DIR, `${key}.lock`);
  try {
    const existing = await fs.readFile(lockPath, 'utf8');
    const [pid, timestamp] = existing.split(':');
    const age = (Date.now() - parseInt(timestamp)) / 1000;
    return age < constants.DEPLOYMENT_LOCK_TTL;
  } catch (e) {
    return false;
  }
}

/**
 * Force release a lock
 */
async function forceRelease(key) {
  const lockPath = path.join(LOCK_DIR, `${key}.lock`);
  try {
    await fs.unlink(lockPath);
    return true;
  } catch (e) {
    return false;
  }
}

module.exports = { acquire, isLocked, forceRelease };
