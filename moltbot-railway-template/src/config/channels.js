/**
 * Signal Channel Configuration
 * OpenClaw Signal channel settings for Moltbot
 *
 * Security Policies:
 * - dmPolicy: "pairing" - Requires authorization for new contacts
 * - groupPolicy: "allowlist" - Restricts group access to allowed numbers
 * - allowFrom: List of allowed phone numbers for DMs
 * - groupAllowFrom: List of allowed phone numbers for groups
 */

// =============================================================================
// Environment-based Configuration
// =============================================================================

const SIGNAL_ENABLED = process.env.SIGNAL_ENABLED !== 'false';
const SIGNAL_ACCOUNT = process.env.SIGNAL_ACCOUNT;
const SIGNAL_CLI_PATH = process.env.SIGNAL_CLI_PATH || '/usr/local/bin/signal-cli';
const SIGNAL_DATA_DIR = process.env.SIGNAL_DATA_DIR || '/data/.signal';

// =============================================================================
// Security Configuration
// =============================================================================

// Parse allowed phone numbers from environment variable
// Format: +1234567890,+0987654321
const parsePhoneList = (envVar) => {
  if (!envVar) return [];
  return envVar.split(',').map(n => n.trim()).filter(n => n);
};

// Allowed phone numbers for direct messages (E.164 format)
const ALLOW_FROM = parsePhoneList(process.env.SIGNAL_ALLOW_FROM);

// Allowed phone numbers for group chats
const GROUP_ALLOW_FROM = parsePhoneList(process.env.SIGNAL_GROUP_ALLOW_FROM);

// =============================================================================
// Signal Channel Configuration Object
// =============================================================================

const signalConfig = {
  // Enable/disable Signal channel
  enabled: SIGNAL_ENABLED,

  // Signal account phone number (E.164 format)
  account: SIGNAL_ACCOUNT,

  // Path to signal-cli binary
  cliPath: SIGNAL_CLI_PATH,

  // Path to Signal data directory
  dataDir: SIGNAL_DATA_DIR,

  // Auto-start signal-cli daemon with gateway
  autoStart: true,

  // Startup timeout in milliseconds
  startupTimeoutMs: 120000,

  // DM security policy: "pairing" requires authorization
  dmPolicy: process.env.SIGNAL_DM_POLICY || 'pairing',

  // Group security policy: "allowlist" restricts to allowed numbers
  groupPolicy: process.env.SIGNAL_GROUP_POLICY || 'allowlist',

  // Disable config writes for security
  configWrites: false,

  // Allowed phone numbers for direct messages
  allowFrom: ALLOW_FROM,

  // Allowed phone numbers for group participation
  groupAllowFrom: GROUP_ALLOW_FROM,

  // Message history limit
  historyLimit: parseInt(process.env.SIGNAL_HISTORY_LIMIT, 10) || 50,

  // Text chunk limit for long messages
  textChunkLimit: parseInt(process.env.SIGNAL_TEXT_CHUNK_LIMIT, 10) || 4000,

  // Ignore stories for security
  ignoreStories: true,

  // HTTP daemon configuration - bind to localhost only for security
  daemon: {
    host: '127.0.0.1',
    port: 8081
  }
};

// =============================================================================
// Validation
// =============================================================================

/**
 * Validate phone number format (E.164)
 * @param {string} phoneNumber - Phone number to validate
 * @returns {boolean}
 */
function isValidE164(phoneNumber) {
  const e164Regex = /^\+[1-9]\d{1,14}$/;
  return e164Regex.test(phoneNumber);
}

/**
 * Validate path is within allowed directory
 * @param {string} inputPath - Path to validate
 * @param {string} allowedBase - Allowed base directory
 * @returns {string} Resolved path
 */
function validatePath(inputPath, allowedBase) {
  const path = require('path');
  const resolved = path.resolve(inputPath);
  const allowed = path.resolve(allowedBase);
  if (!resolved.startsWith(allowed)) {
    throw new Error(`Path ${inputPath} is outside allowed base ${allowedBase}`);
  }
  return resolved;
}

/**
 * Validate configuration
 * @returns {object} Validation result
 */
function validateConfig() {
  const errors = [];

  if (!SIGNAL_ACCOUNT) {
    errors.push('SIGNAL_ACCOUNT environment variable is required');
  } else if (!isValidE164(SIGNAL_ACCOUNT)) {
    errors.push(`Invalid SIGNAL_ACCOUNT: ${SIGNAL_ACCOUNT}. Must be E.164 format (+1234567890)`);
  }

  signalConfig.allowFrom.forEach((number, index) => {
    if (!isValidE164(number)) {
      errors.push(`Invalid allowFrom[${index}]: ${number}. Must be E.164 format`);
    }
  });

  signalConfig.groupAllowFrom.forEach((number, index) => {
    if (!isValidE164(number)) {
      errors.push(`Invalid groupAllowFrom[${index}]: ${number}. Must be E.164 format`);
    }
  });

  // Validate paths
  try {
    validatePath(SIGNAL_CLI_PATH, '/usr/local/bin');
  } catch (err) {
    errors.push(`Invalid SIGNAL_CLI_PATH: ${err.message}`);
  }

  try {
    validatePath(SIGNAL_DATA_DIR, '/data');
  } catch (err) {
    errors.push(`Invalid SIGNAL_DATA_DIR: ${err.message}`);
  }

  return {
    valid: errors.length === 0,
    errors
  };
}

// =============================================================================
// Exports
// =============================================================================

module.exports = {
  ...signalConfig,
  validateConfig,
  isValidE164,
  validatePath
};
