#!/usr/bin/env node

/**
 * Signal Integration Tests for OpenClaw/Moltbot
 *
 * Node.js integration test suite for Signal messaging functionality.
 * Tests configuration, security policies, and integration points.
 *
 * Account: +15165643945
 * Status: Pre-linked device data embedded in Docker image
 */

const fs = require('fs');
const path = require('path');
const { promisify } = require('util');
const readFile = promisify(fs.readFile);
const exists = promisify(fs.exists);
const stat = promisify(fs.stat);

// Test runner state
const testResults = {
  total: 0,
  passed: 0,
  failed: 0,
  errors: []
};

// =============================================================================
// Test Utilities
// =============================================================================

function describe(name, fn) {
  console.log(`\n📦 ${name}`);
  fn();
}

function it(name, fn) {
  testResults.total++;
  try {
    fn();
    testResults.passed++;
    console.log(`  ✅ ${name}`);
  } catch (error) {
    testResults.failed++;
    testResults.errors.push({ test: name, error: error.message });
    console.log(`  ❌ ${name}`);
    console.log(`     ${error.message}`);
  }
}

function expect(actual) {
  return {
    toBe(expected) {
      if (actual !== expected) {
        throw new Error(`Expected ${expected} but got ${actual}`);
      }
    },
    toEqual(expected) {
      if (JSON.stringify(actual) !== JSON.stringify(expected)) {
        throw new Error(`Expected ${JSON.stringify(expected)} but got ${JSON.stringify(actual)}`);
      }
    },
    toBeTruthy() {
      if (!actual) {
        throw new Error(`Expected truthy value but got ${actual}`);
      }
    },
    toBeFalsy() {
      if (actual) {
        throw new Error(`Expected falsy value but got ${actual}`);
      }
    },
    toContain(expected) {
      if (!actual.includes(expected)) {
        throw new Error(`Expected ${JSON.stringify(actual)} to contain ${JSON.stringify(expected)}`);
      }
    },
    toMatch(pattern) {
      if (!pattern.test(actual)) {
        throw new Error(`Expected ${actual} to match ${pattern}`);
      }
    },
    toBeGreaterThan(expected) {
      if (!(actual > expected)) {
        throw new Error(`Expected ${actual} to be greater than ${expected}`);
      }
    },
    toBeLessThan(expected) {
      if (!(actual < expected)) {
        throw new Error(`Expected ${actual} to be less than ${expected}`);
      }
    },
    toHaveLength(expected) {
      if (actual.length !== expected) {
        throw new Error(`Expected length ${expected} but got ${actual.length}`);
      }
    }
  };
}

// =============================================================================
// Signal Configuration
// =============================================================================

const SIGNAL_CONFIG = {
  enabled: true,
  account: "+15165643945",
  cliPath: "/usr/local/bin/signal-cli",
  autoStart: true,
  startupTimeoutMs: 120000,
  dmPolicy: "pairing",
  groupPolicy: "allowlist",
  allowFrom: ["+15165643945", "+19194133445"],
  groupAllowFrom: ["+19194133445"],
  historyLimit: 50,
  textChunkLimit: 4000,
  ignoreStories: true
};

// =============================================================================
// Phase 1: Configuration Tests (Tests 1-8)
// =============================================================================

describe('Signal Configuration', () => {
  it('should have valid account number format', () => {
    const account = SIGNAL_CONFIG.account;
    expect(account.startsWith('+')).toBeTruthy();
    expect(account.length).toBeGreaterThan(10);
    expect(/^\+\d+$/.test(account)).toBeTruthy();
  });

  it('should have signal-cli path configured', () => {
    expect(SIGNAL_CONFIG.cliPath).toBeTruthy();
    expect(SIGNAL_CONFIG.cliPath).toContain('signal-cli');
  });

  it('should have valid DM policy', () => {
    const validPolicies = ['open', 'pairing', 'blocklist'];
    expect(validPolicies).toContain(SIGNAL_CONFIG.dmPolicy);
  });

  it('should have valid group policy', () => {
    const validPolicies = ['open', 'allowlist', 'blocklist'];
    expect(validPolicies).toContain(SIGNAL_CONFIG.groupPolicy);
  });

  it('should have valid allowlist format', () => {
    SIGNAL_CONFIG.allowFrom.forEach(number => {
      expect(number.startsWith('+')).toBeTruthy();
      expect(/^\+\d+$/.test(number)).toBeTruthy();
    });
  });

  it('should have reasonable startup timeout', () => {
    expect(SIGNAL_CONFIG.startupTimeoutMs).toBeGreaterThan(30000);
    expect(SIGNAL_CONFIG.startupTimeoutMs).toBeLessThan(300000);
  });

  it('should have positive history limit', () => {
    expect(SIGNAL_CONFIG.historyLimit).toBeGreaterThan(0);
    expect(SIGNAL_CONFIG.historyLimit).toBeLessThan(1000);
  });

  it('should be serializable to JSON', () => {
    const json = JSON.stringify(SIGNAL_CONFIG);
    expect(json).toBeTruthy();
    const parsed = JSON.parse(json);
    expect(parsed.account).toBe(SIGNAL_CONFIG.account);
  });
});

// =============================================================================
// Phase 2: Security Policy Tests (Tests 9-16)
// =============================================================================

describe('Signal Security Policy', () => {
  it('should have DM policy set to pairing', () => {
    expect(SIGNAL_CONFIG.dmPolicy).toBe('pairing');
  });

  it('should have group policy set to allowlist', () => {
    expect(SIGNAL_CONFIG.groupPolicy).toBe('allowlist');
  });

  it('should have primary account in allowlist', () => {
    expect(SIGNAL_CONFIG.allowFrom).toContain('+15165643945');
  });

  it('should have secondary number in allowlist', () => {
    expect(SIGNAL_CONFIG.allowFrom).toContain('+19194133445');
  });

  it('should have restricted group allowlist', () => {
    expect(SIGNAL_CONFIG.groupAllowFrom.length <= SIGNAL_CONFIG.allowFrom.length).toBe(true);
  });

  it('should not have wildcards in allowlist', () => {
    SIGNAL_CONFIG.allowFrom.forEach(number => {
      expect(number.includes('*')).toBeFalsy();
      expect(number.includes('?')).toBeFalsy();
    });
  });

  it('should ignore stories', () => {
    expect(SIGNAL_CONFIG.ignoreStories).toBe(true);
  });

  it('should require pairing for new contacts', () => {
    const requiresPairing = SIGNAL_CONFIG.dmPolicy === 'pairing';
    expect(requiresPairing).toBe(true);
  });
});

// =============================================================================
// Phase 3: Access Control Tests (Tests 17-22)
// =============================================================================

describe('Signal Access Control', () => {
  it('should authorize allowed numbers for DM', () => {
    const testNumber = '+19194133445';
    const isAuthorized = SIGNAL_CONFIG.allowFrom.includes(testNumber);
    expect(isAuthorized).toBe(true);
  });

  it('should not authorize unknown numbers for DM', () => {
    const unknownNumber = '+9999999999';
    const isAuthorized = SIGNAL_CONFIG.allowFrom.includes(unknownNumber);
    expect(isAuthorized).toBe(false);
  });

  it('should authorize specific numbers for groups', () => {
    const testNumber = '+19194133445';
    const isAuthorized = SIGNAL_CONFIG.groupAllowFrom.includes(testNumber);
    expect(isAuthorized).toBe(true);
  });

  it('should not have primary account in group allowlist', () => {
    expect(SIGNAL_CONFIG.groupAllowFrom.includes('+15165643945')).toBe(false);
  });

  it('should validate phone number format', () => {
    const validNumbers = ['+1234567890', '+14155552671', '+442071838750'];
    validNumbers.forEach(number => {
      expect(/^\+\d+$/.test(number)).toBe(true);
    });
  });

  it('should reject invalid phone number formats', () => {
    const invalidNumbers = ['1234567890', 'abc', '+123abc456', ''];
    invalidNumbers.forEach(number => {
      const isValid = number.startsWith('+') && number.length > 1 && /^\+\d+$/.test(number);
      expect(isValid).toBe(false);
    });
  });
});

// =============================================================================
// Phase 4: File System Tests (Tests 23-28)
// =============================================================================

describe('Signal File System', async () => {
  const archivePath = path.join('.signal-data', 'signal-data.tar.gz');
  const dockerfilePath = 'Dockerfile';

  it('should have Signal data archive', async () => {
    const archiveExists = await exists(archivePath);
    expect(archiveExists).toBe(true);
  });

  it('should have non-empty archive', async () => {
    const archiveStats = await stat(archivePath);
    expect(archiveStats.size).toBeGreaterThan(1000);
  });

  it('should have Dockerfile', async () => {
    const dockerfileExists = await exists(dockerfilePath);
    expect(dockerfileExists).toBe(true);
  });

  it('should have signal-cli in Dockerfile', async () => {
    const content = await readFile(dockerfilePath, 'utf8');
    expect(content).toContain('signal-cli');
  });

  it('should have Signal data extraction in Dockerfile', async () => {
    const content = await readFile(dockerfilePath, 'utf8');
    expect(content).toContain('signal-data.tar.gz');
  });

  it('should have Signal environment variables in Dockerfile', async () => {
    const content = await readFile(dockerfilePath, 'utf8');
    expect(content).toContain('SIGNAL_DATA_DIR');
    expect(content).toContain('SIGNAL_ACCOUNT');
  });
});

// =============================================================================
// Phase 5: Integration Tests (Tests 29-32)
// =============================================================================

describe('Signal Integration', () => {
  it('should have consistent account across config', () => {
    expect(SIGNAL_CONFIG.account).toBe('+15165643945');
  });

  it('should have proper CLI timeout configuration', () => {
    expect(SIGNAL_CONFIG.startupTimeoutMs).toBe(120000);
  });

  it('should have text chunking configured', () => {
    expect(SIGNAL_CONFIG.textChunkLimit).toBe(4000);
  });

  it('should have history management configured', () => {
    expect(SIGNAL_CONFIG.historyLimit).toBe(50);
  });
});

// =============================================================================
// Test Runner
// =============================================================================

async function runTests() {
  console.log('═══════════════════════════════════════════════════════════════');
  console.log('  Signal Integration Tests for OpenClaw/Moltbot');
  console.log('  Account: +15165643945');
  console.log('═══════════════════════════════════════════════════════════════');

  // Wait for async tests to complete
  await new Promise(resolve => setTimeout(resolve, 100));

  console.log('\n═══════════════════════════════════════════════════════════════');
  console.log('  Test Results');
  console.log('═══════════════════════════════════════════════════════════════');
  console.log(`  Total:  ${testResults.total}`);
  console.log(`  Passed: ${testResults.passed} ✅`);
  console.log(`  Failed: ${testResults.failed} ❌`);
  console.log(`  Pass Rate: ${((testResults.passed / testResults.total) * 100).toFixed(1)}%`);

  if (testResults.failed > 0) {
    console.log('\n  Failed Tests:');
    testResults.errors.forEach(({ test, error }) => {
      console.log(`    - ${test}: ${error}`);
    });
  }

  console.log('═══════════════════════════════════════════════════════════════');

  process.exit(testResults.failed > 0 ? 1 : 0);
}

// Run tests
runTests().catch(error => {
  console.error('Test runner error:', error);
  process.exit(1);
});
