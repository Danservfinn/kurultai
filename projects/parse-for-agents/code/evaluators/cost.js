// Cost estimator - token counting and pricing

// Simple tokenizer (rough approximation for demo)
function countTokens(text) {
  // Approximation: ~4 characters per token for English
  // For production, use tiktoken or equivalent
  return Math.ceil(text.length / 4);
}

// Model pricing table (per 1M tokens)
const MODEL_PRICING = {
  'openai/gpt-4o': {
    input: 2.50,
    output: 10.00,
    context: 128000
  },
  'openai/gpt-4o-mini': {
    input: 0.15,
    output: 0.60,
    context: 128000
  },
  'anthropic/claude-sonnet-4-20250514': {
    input: 3.00,
    output: 15.00,
    context: 200000
  },
  'google/gemini-pro-1.5': {
    input: 1.25,
    output: 5.00,
    context: 1000000
  },
  'meta/llama-3.3-70b': {
    input: 0.60,
    output: 0.60,
    context: 128000
  }
};

function getBudgetTier(cost) {
  if (cost < 0.001) return 'micro';
  if (cost < 0.01) return 'low';
  if (cost < 0.10) return 'moderate';
  if (cost < 1.00) return 'high';
  return 'expensive';
}

function estimateCost(prompt, model, response) {
  const inputTokens = countTokens(prompt);
  const outputTokens = response ? countTokens(response) : 0;

  const pricing = MODEL_PRICING[model] || MODEL_PRICING['openai/gpt-4o'];

  const inputCost = (inputTokens / 1000000) * pricing.input;
  const outputCost = (outputTokens / 1000000) * pricing.output;
  const totalCost = inputCost + outputCost;

  return {
    input_tokens: inputTokens,
    output_tokens: outputTokens,
    total_tokens: inputTokens + outputTokens,
    estimated_cost_usd: Math.round(totalCost * 10000) / 10000,
    tier: getBudgetTier(totalCost),
    model_pricing: {
      input_price_per_1m: pricing.input,
      output_price_per_1m: pricing.output,
      context_length: pricing.context
    }
  };
}

module.exports = { estimateCost };
