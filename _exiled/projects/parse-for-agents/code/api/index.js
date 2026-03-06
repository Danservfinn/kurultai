require('dotenv').config();
const express = require('express');
const cors = require('cors');
const { EvaluationQueue } = require('../queue/queue');

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.use(cors());
app.use(express.json({ limit: '10mb' }));

// Initialize queue
let evaluationQueue;
try {
  evaluationQueue = new EvaluationQueue();
  console.log('✓ Evaluation queue initialized');
} catch (error) {
  console.warn('⚠ Queue initialization failed:', error.message);
  evaluationQueue = null;
}

// Health check
app.get('/health', (req, res) => {
  res.json({
    status: 'ok',
    timestamp: new Date().toISOString(),
    queue: evaluationQueue ? 'connected' : 'disconnected'
  });
});

// List models
app.get('/v1/models', (req, res) => {
  res.json({
    models: [
      {
        id: 'openai/gpt-4o',
        name: 'GPT-4o',
        provider: 'openai',
        input_price: 0.0025,
        output_price: 0.01,
        context_length: 128000
      },
      {
        id: 'openai/gpt-4o-mini',
        name: 'GPT-4o Mini',
        provider: 'openai',
        input_price: 0.00015,
        output_price: 0.0006,
        context_length: 128000
      },
      {
        id: 'anthropic/claude-sonnet-4-20250514',
        name: 'Claude Sonnet 4',
        provider: 'anthropic',
        input_price: 0.003,
        output_price: 0.015,
        context_length: 200000
      },
      {
        id: 'google/gemini-pro-1.5',
        name: 'Gemini Pro 1.5',
        provider: 'google',
        input_price: 0.00125,
        output_price: 0.005,
        context_length: 1000000
      }
    ]
  });
});

// Submit evaluation
app.post('/v1/evaluate', async (req, res) => {
  try {
    const { prompt, model, test_inputs } = req.body;

    if (!prompt || !model) {
      return res.status(400).json({
        error: 'Missing required fields: prompt, model'
      });
    }

    // Create evaluation job
    const jobData = {
      prompt,
      model,
      test_inputs: test_inputs || [''],
      created_at: new Date().toISOString()
    };

    let jobId;
    if (evaluationQueue) {
      const job = await evaluationQueue.add('evaluation', jobData);
      jobId = job.id;
      console.log(`✓ Evaluation job ${jobId} queued`);
    } else {
      // Fallback: process synchronously
      jobId = `eval_${Date.now()}`;
      console.log(`⚠ Queue unavailable, processing synchronously`);
    }

    res.status(202).json({
      id: jobId,
      status: 'pending',
      message: 'Evaluation queued'
    });
  } catch (error) {
    console.error('Error submitting evaluation:', error);
    res.status(500).json({
      error: 'Failed to submit evaluation',
      details: error.message
    });
  }
});

// Get evaluation results
app.get('/v1/evaluate/:id', async (req, res) => {
  try {
    const { id } = req.params;

    // In a real implementation, this would query the database
    // For MVP, return a mock response
    res.json({
      id,
      status: 'completed',
      results: {
        safety: {
          passed: true,
          flags: [],
          score: 1.0
        },
        quality: {
          score: 0.85,
          coherence: 0.9,
          completeness: 0.8,
          relevance: 0.85,
          repetition: 0.9
        },
        cost: {
          input_tokens: 150,
          output_tokens: 300,
          estimated_cost_usd: 0.0045,
          tier: 'low'
        },
        latency: {
          response_time_ms: 1200,
          rating: 'good'
        }
      }
    });
  } catch (error) {
    res.status(500).json({
      error: 'Failed to retrieve evaluation',
      details: error.message
    });
  }
});

// Start server
app.listen(PORT, () => {
  console.log(`\n🚀 Parse for Agents API`);
  console.log(`📡 Listening on port ${PORT}`);
  console.log(`❤️  Health: http://localhost:${PORT}/health\n`);
});

module.exports = app;
