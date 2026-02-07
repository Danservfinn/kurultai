/**
 * Signal Channel Configuration Tests
 */

// Set required environment variables before importing
process.env.SIGNAL_ACCOUNT = '+1234567890';
process.env.SIGNAL_ALLOW_FROM = '+1234567890,+19876543210';
process.env.SIGNAL_GROUP_ALLOW_FROM = '+1234567890';

const signalConfig = require('../src/config/channels');

describe('Signal Channel Configuration', () => {
  describe('Configuration Structure', () => {
    test('should have required configuration properties', () => {
      expect(signalConfig).toHaveProperty('enabled');
      expect(signalConfig).toHaveProperty('account');
      expect(signalConfig).toHaveProperty('cliPath');
      expect(signalConfig).toHaveProperty('dataDir');
      expect(signalConfig).toHaveProperty('autoStart');
      expect(signalConfig).toHaveProperty('dmPolicy');
      expect(signalConfig).toHaveProperty('groupPolicy');
      expect(signalConfig).toHaveProperty('allowFrom');
      expect(signalConfig).toHaveProperty('groupAllowFrom');
    });

    test('should have correct default values', () => {
      expect(typeof signalConfig.enabled).toBe('boolean');
      expect(signalConfig.cliPath).toBe('/usr/local/bin/signal-cli');
      expect(signalConfig.dataDir).toBe('/data/.signal');
      expect(signalConfig.autoStart).toBe(true);
      expect(signalConfig.dmPolicy).toBe('pairing');
      expect(signalConfig.groupPolicy).toBe('allowlist');
    });
  });

  describe('Security Policies', () => {
    test('should have pairing DM policy for security', () => {
      expect(signalConfig.dmPolicy).toBe('pairing');
    });

    test('should have allowlist group policy for security', () => {
      expect(signalConfig.groupPolicy).toBe('allowlist');
    });

    test('should have allowFrom list with valid phone numbers', () => {
      expect(Array.isArray(signalConfig.allowFrom)).toBe(true);
      expect(signalConfig.allowFrom.length).toBeGreaterThan(0);
      signalConfig.allowFrom.forEach(number => {
        expect(signalConfig.isValidE164(number)).toBe(true);
      });
    });

    test('should have groupAllowFrom list with valid phone numbers', () => {
      expect(Array.isArray(signalConfig.groupAllowFrom)).toBe(true);
      signalConfig.groupAllowFrom.forEach(number => {
        expect(signalConfig.isValidE164(number)).toBe(true);
      });
    });
  });

  describe('E164 Validation', () => {
    test('should validate correct E164 format', () => {
      expect(signalConfig.isValidE164('+15165643945')).toBe(true);
      expect(signalConfig.isValidE164('+19194133445')).toBe(true);
      expect(signalConfig.isValidE164('+1234567890')).toBe(true);
    });

    test('should reject invalid E164 format', () => {
      expect(signalConfig.isValidE164('15165643945')).toBe(false); // Missing +
      expect(signalConfig.isValidE164('+015165643945')).toBe(false); // Leading 0
      expect(signalConfig.isValidE164('invalid')).toBe(false);
      expect(signalConfig.isValidE164('')).toBe(false);
      expect(signalConfig.isValidE164('+1234567890123456')).toBe(false); // Too long (>15 digits)
    });
  });

  describe('Configuration Validation', () => {
    test('should pass validation with correct config', () => {
      const validation = signalConfig.validateConfig();
      expect(validation.valid).toBe(true);
      expect(validation.errors).toHaveLength(0);
    });
  });
});
