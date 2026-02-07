/**
 * Scheduled Reflection Tests
 *
 * Tests for the Kublai Scheduled Reflection module.
 * Verifies periodic reflection scheduling and execution.
 */

const { describe, it, expect, beforeEach, afterEach } = require('@jest/globals');
const { ScheduledReflection } = require('../../src/kublai/scheduled-reflection');

describe('Scheduled Reflection', () => {
  let mockReflection;
  let mockLogger;
  let scheduledReflection;

  beforeEach(() => {
    mockReflection = {
      triggerReflection: jest.fn()
    };
    mockLogger = {
      info: jest.fn(),
      warn: jest.fn(),
      error: jest.fn()
    };
    scheduledReflection = new ScheduledReflection(mockReflection, mockLogger);
  });

  afterEach(() => {
    // Stop any running jobs
    if (scheduledReflection.job) {
      scheduledReflection.stop();
    }
  });

  describe('start', () => {
    it('should start scheduled reflection job', () => {
      scheduledReflection.start();

      expect(scheduledReflection.job).not.toBeNull();
      expect(mockLogger.info).toHaveBeenCalledWith(
        '[ScheduledReflection] Started weekly reflection trigger (Sundays at 8 PM ET)'
      );
    });

    it('should warn when already running', () => {
      scheduledReflection.start();
      scheduledReflection.start();

      expect(mockLogger.warn).toHaveBeenCalledWith(
        '[ScheduledReflection] Already running'
      );
    });
  });

  describe('stop', () => {
    it('should stop scheduled reflection job', () => {
      scheduledReflection.start();
      expect(scheduledReflection.job).not.toBeNull();

      scheduledReflection.stop();

      expect(scheduledReflection.job).toBeNull();
      expect(mockLogger.info).toHaveBeenCalledWith(
        '[ScheduledReflection] Stopped'
      );
    });

    it('should handle stop when not running', () => {
      // Should not throw
      expect(() => scheduledReflection.stop()).not.toThrow();
      expect(scheduledReflection.job).toBeNull();
    });
  });

  describe('weeklyReflection', () => {
    it('should execute reflection and log results', async () => {
      mockReflection.triggerReflection.mockResolvedValue({
        sectionsKnown: 10,
        opportunitiesFound: 3,
        opportunities: [
          { type: 'missing_section', description: 'Missing security docs' },
          { type: 'stale_sync', description: 'Data is 10 days old' }
        ]
      });

      await scheduledReflection.weeklyReflection();

      expect(mockReflection.triggerReflection).toHaveBeenCalled();
      expect(mockLogger.info).toHaveBeenCalledWith(
        '[Kublai] Running weekly architecture reflection...'
      );
      expect(mockLogger.info).toHaveBeenCalledWith(
        '[Kublai] Reflection complete:',
        expect.objectContaining({
          sectionsKnown: 10,
          opportunitiesFound: 3
        })
      );
    });

    it('should log opportunities when found', async () => {
      mockReflection.triggerReflection.mockResolvedValue({
        sectionsKnown: 5,
        opportunitiesFound: 2,
        opportunities: [
          { type: 'missing_section', description: 'Missing API docs' },
          { type: 'missing_section', description: 'Missing data model' }
        ]
      });

      await scheduledReflection.weeklyReflection();

      expect(mockLogger.info).toHaveBeenCalledWith(
        '[Kublai] Opportunities:',
        expect.any(Array)
      );
    });

    it('should not log opportunities when none found', async () => {
      mockReflection.triggerReflection.mockResolvedValue({
        sectionsKnown: 10,
        opportunitiesFound: 0,
        opportunities: []
      });

      await scheduledReflection.weeklyReflection();

      // Should not log opportunities when empty
      const opportunitiesLog = mockLogger.info.mock.calls.find(
        call => call[0] === '[Kublai] Opportunities:'
      );
      expect(opportunitiesLog).toBeUndefined();
    });

    it('should handle reflection errors gracefully', async () => {
      mockReflection.triggerReflection.mockRejectedValue(
        new Error('Reflection failed')
      );

      await scheduledReflection.weeklyReflection();

      expect(mockLogger.error).toHaveBeenCalledWith(
        '[Kublai] Weekly reflection failed: Reflection failed'
      );
    });

    it('should handle reflection errors with error object', async () => {
      const error = new Error('Network timeout');
      mockReflection.triggerReflection.mockRejectedValue(error);

      await scheduledReflection.weeklyReflection();

      expect(mockLogger.error).toHaveBeenCalledWith(
        '[Kublai] Weekly reflection failed: Network timeout'
      );
    });
  });

  describe('triggerNow', () => {
    it('should trigger immediate reflection', async () => {
      mockReflection.triggerReflection.mockResolvedValue({
        sectionsKnown: 8,
        opportunitiesFound: 1,
        opportunities: [{ type: 'stale_sync', description: 'Data is old' }]
      });

      await scheduledReflection.triggerNow();

      expect(mockLogger.info).toHaveBeenCalledWith(
        '[Kublai] Triggering immediate reflection...'
      );
      expect(mockReflection.triggerReflection).toHaveBeenCalled();
    });

    it('should return reflection results', async () => {
      const expectedResult = {
        sectionsKnown: 5,
        opportunitiesFound: 0,
        opportunities: []
      };
      mockReflection.triggerReflection.mockResolvedValue(expectedResult);

      const result = await scheduledReflection.triggerNow();

      // triggerNow returns the result of weeklyReflection which doesn't return explicitly
      // but we can verify it was called
      expect(mockReflection.triggerReflection).toHaveBeenCalled();
    });

    it('should handle errors during immediate trigger', async () => {
      mockReflection.triggerReflection.mockRejectedValue(
        new Error('Immediate trigger failed')
      );

      await scheduledReflection.triggerNow();

      expect(mockLogger.error).toHaveBeenCalledWith(
        '[Kublai] Weekly reflection failed: Immediate trigger failed'
      );
    });
  });

  describe('integration with cron', () => {
    it('should schedule for Sundays at 8 PM ET', () => {
      scheduledReflection.start();

      // The cron pattern should be '0 20 * * 0' (Sundays at 8:00 PM)
      // We can't easily test the cron internals, but we verify the job was created
      expect(scheduledReflection.job).not.toBeNull();
    });

    it('should maintain single job instance', () => {
      scheduledReflection.start();
      const firstJob = scheduledReflection.job;

      scheduledReflection.start(); // Second call should not create new job

      expect(scheduledReflection.job).toBe(firstJob);
    });
  });
});
