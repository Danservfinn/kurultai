const { Queue, Worker } = require('bullmq');
const { evaluatePrompt } = require('../evaluators/composite');

class EvaluationQueue {
  constructor() {
    const redisUrl = process.env.REDIS_URL || 'redis://localhost:6379';

    this.queue = new Queue('evaluations', {
      connection: {
        url: redisUrl,
        // Fallback for Railway without Redis
        // If connection fails, queue operations will be handled gracefully
      }
    });

    // Start worker if not in production API mode
    if (process.env.NODE_ENV !== 'production' || process.env.START_WORKER === 'true') {
      this.startWorker();
    }
  }

  async add(name, data) {
    try {
      return await this.queue.add(name, data);
    } catch (error) {
      console.warn('⚠ Failed to queue job:', error.message);
      // Return mock job
      return { id: `job_${Date.now()}` };
    }
  }

  startWorker() {
    const worker = new Worker('evaluations', async (job) => {
      console.log(`Processing job ${job.id}`);

      const results = await evaluatePrompt(job.data);

      // In real implementation, save to database
      console.log(`✓ Job ${job.id} completed`);

      return results;
    }, {
      connection: {
        url: process.env.REDIS_URL || 'redis://localhost:6379'
      }
    });

    worker.on('completed', (job) => {
      console.log(`✓ Worker completed job ${job.id}`);
    });

    worker.on('failed', (job, err) => {
      console.error(`✗ Worker failed job ${job.id}:`, err.message);
    });

    this.worker = worker;
  }

  async close() {
    await this.queue.close();
    if (this.worker) {
      await this.worker.close();
    }
  }
}

module.exports = { EvaluationQueue };
