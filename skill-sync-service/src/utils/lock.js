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
  const lockContent = `${process.pid}:${Date.now()}`;

  try {
    // Use O_EXCL for atomic lock creation
    // This operation either succeeds or fails atomically
    const flags = fs.constants.O_CREAT | fs.constants.O_EXCL | fs.constants.O_WRONLY;
    const fd = await fs.open(lockPath, flags);

    await fd.writeFile(lockContent);
    await fd.close();

    locks.set(key, { lockId, lockPath, acquiredAt: Date.now() });

    // Return release function
    return async () => {
      try {
        // Only delete if we still own it
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
    if (e.code === 'EEXIST') {
      throw new Error(`Lock already held for key: ${key}`);
    }
    throw e;
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
