/**
 * Scheduled Reflection Tests
 *
 * Tests for the Kublai Scheduled Reflection module.
 * Verifies periodic reflection scheduling and execution.
 */

const { describe, it, expect, beforeAll, afterAll, jest } = require('@jest/globals');
const { ScheduledReflection } = require('../../src/kublai/scheduled-reflection');

describe('Scheduled Reflection', () => {
  let scheduledReflection;
  let mockProactiveReflection;
  const mockLogger = {
    info: jest.fn(),
    error: jest.fn(),
    warn: jest.fn()
  };

  beforeAll(() => {
    mockProactiveReflection = {
      triggerReflection: jest.fn()
    };

    scheduledReflection = new ScheduledReflection(mockProactiveReflection, mockLogger);
  });

  beforeEach(() => {
    jest.clearAllMocks();
    // Stop any running job before each test
    scheduledReflection.stop();
  });

  afterAll(() => {
    scheduledReflection.stop();
  });

  describe('start', () => {
    it('should start scheduled reflection', () => {
      scheduledReflection.start();

      expect(scheduledReflection.job).not.toBeNull();
      expect(mockLogger.info).toHaveBeenCalledWith(
        '[ScheduledReflection] Started weekly reflection trigger (Sundays at 8 PM ET)'
      );
    });

    it('should warn when already running', () => {
      scheduledReflection.start();
      expect(scheduledReflection.job).not.toBeNull();

      // Try to start again
      scheduledReflection.start();

      expect(mockLogger.warn).toHaveBeenCalledWith(
        '[ScheduledReflection] Already running'
      );
    });

    it('should schedule for Sundays at 8 PM ET', () => {
      scheduledReflection.start();

      // Verify cron job was created with correct schedule
      expect(scheduledReflection.job).toBeDefined();
      // The schedule is '0 20 * * 0' (Sundays at 8 PM)
    });
  });

  describe('stop', () => {
    it('should stop scheduled reflection', () => {
      scheduledReflection.start();
      expect(scheduledReflection.job).not.toBeNull();

      scheduledReflection.stop();

      expect(scheduledReflection.job).toBeNull();
      expect(mockLogger.info).toHaveBeenCalledWith(
        '[ScheduledReflection] Stopped'
      );
    });

    it('should handle stop when not running', () => {
      // Should not throw when job is null
      expect(() => scheduledReflection.stop()).not.toThrow();
      expect(scheduledReflection.job).toBeNull();
    });
  });

  describe('weeklyReflection', () => {
    it('should execute reflection successfully', async () => {
      mockProactiveReflection.triggerReflection.mockResolvedValue({
        sectionsKnown: 10,
        opportunitiesFound: 2,
        opportunities: [
          { type: 'missing_section', description: 'Missing API docs' },
          { type: 'stale_sync', description: 'Data is old' }
        ]
      });

      await scheduledReflection.weeklyReflection();

      expect(mockProactiveReflection.triggerReflection).toHaveBeenCalled();
      expect(mockLogger.info).toHaveBeenCalledWith(
        '[Kublai] Running weekly architecture reflection...'
      );
      expect(mockLogger.info).toHaveBeenCalledWith(
        '[Kublai] Reflection complete:',
        expect.objectContaining({
          sectionsKnown: 10,
          opportunitiesFound: 2
        })
      );
    });

    it('should log opportunities when found', async () => {
      mockProactiveReflection.triggerReflection.mockResolvedValue({
        sectionsKnown: 5,
        opportunitiesFound: 1,
        opportunities: [{ type: 'missing_section', description: 'Missing section' }]
      });

      await scheduledReflection.weeklyReflection();

      expect(mockLogger.info).toHaveBeenCalledWith(
        '[Kublai] Opportunities:',
        expect.any(Array)
      );
    });

    it('should not log opportunities when none found', async () => {
      mockProactiveReflection.triggerReflection.mockResolvedValue({
        sectionsKnown: 5,
        opportunitiesFound: 0,
        opportunities: []
      });

      await scheduledReflection.weeklyReflection();

      // Should not log opportunities when none found
      const opportunitiesLog = mockLogger.info.mock.calls.find(
        call => call[0] === '[Kublai] Opportunities:'
      );
      expect(opportunitiesLog).toBeUndefined();
    });

    it('should handle reflection errors gracefully', async () => {
      mockProactiveReflection.triggerReflection.mockRejectedValue(
        new Error('Reflection failed')
      );

      await scheduledReflection.weeklyReflection();

      expect(mockLogger.error).toHaveBeenCalledWith(
        '[Kublai] Weekly reflection failed: Reflection failed'
      );
    });

    it('should handle empty result', async () => {
      mockProactiveReflection.triggerReflection.mockResolvedValue({
        sectionsKnown: 0,
        opportunitiesFound: 0,
        opportunities: []
      });

      await scheduledReflection.weeklyReflection();

      expect(mockLogger.info).toHaveBeenCalledWith(
        '[Kublai] Reflection complete:',
        expect.objectContaining({
          sectionsKnown: 0,
          opportunitiesFound: 0
        })
      );
    });
  });

  describe('triggerNow', () => {
    it('should trigger immediate reflection', async () => {
      mockProactiveReflection.triggerReflection.mockResolvedValue({
        sectionsKnown: 8,
        opportunitiesFound: 1,
        opportunities: [{ type: 'stale_sync', description: 'Data is old' }]
      });

      await scheduledReflection.triggerNow();

      expect(mockLogger.info).toHaveBeenCalledWith(
        '[Kublai] Triggering immediate reflection...'
      );
      expect(mockProactiveReflection.triggerReflection).toHaveBeenCalled();
    });

    it('should return reflection results', async () => {
      const expectedResult = {
        sectionsKnown: 5,
        opportunitiesFound: 0,
        opportunities: []
      };
      mockProactiveReflection.triggerReflection.mockResolvedValue(expectedResult);

      const result = await scheduledReflection.triggerNow();

      expect(result).toEqual(expectedResult);
    });

    it('should handle errors during immediate trigger', async () => {
      mockProactiveReflection.triggerReflection.mockRejectedValue(
        new Error('Immediate trigger failed')
      );

      await scheduledReflection.triggerNow();

      expect(mockLogger.error).toHaveBeenCalledWith(
        '[Kublai] Weekly reflection failed: Immediate trigger failed'
      );
    });
  });

  describe('integration', () => {
    it('should run complete start-stop cycle', () => {
      // Start
      scheduledReflection.start();
      expect(scheduledReflection.job).not.toBeNull();

      // Stop
      scheduledReflection.stop();
      expect(scheduledReflection.job).toBeNull();

      // Restart
      scheduledReflection.start();
      expect(scheduledReflection.job).not.toBeNull();
    });

    it('should allow triggerNow while scheduled job is running', async () => {
      mockProactiveReflection.triggerReflection.mockResolvedValue({
        sectionsKnown: 3,
        opportunitiesFound: 0,
        opportunities: []
      });

      // Start scheduled job
      scheduledReflection.start();

      // Trigger immediate reflection
      await scheduledReflection.triggerNow();

      expect(mockProactiveReflection.triggerReflection).toHaveBeenCalled();

      // Scheduled job should still be active
      expect(scheduledReflection.job).not.toBeNull();
    });
  });
});
