/**
 * Signal CLI Process Management Tests
 */

const { startSignalCli, stopSignalCli, checkSignalCliHealth } = require('../src/index');

describe('Signal CLI Process Management', () => {
  // Increase timeout for process tests
  jest.setTimeout(30000);

  describe('checkSignalCliHealth', () => {
    test('should return boolean', async () => {
      const result = await checkSignalCliHealth();
      expect(typeof result).toBe('boolean');
    });
  });

  describe('startSignalCli', () => {
    test('should handle missing SIGNAL_ACCOUNT gracefully', async () => {
      const originalAccount = process.env.SIGNAL_ACCOUNT;
      delete process.env.SIGNAL_ACCOUNT;

      const result = await startSignalCli();
      expect(result).toBe(false);

      process.env.SIGNAL_ACCOUNT = originalAccount;
    });
  });

  describe('stopSignalCli', () => {
    test('should complete without errors when no process running', async () => {
      await expect(stopSignalCli()).resolves.not.toThrow();
    });
  });
});
