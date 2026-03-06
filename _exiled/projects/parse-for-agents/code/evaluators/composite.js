const { evaluateSafety } = require('./safety');
const { evaluateQuality } = require('./quality');
const { estimateCost } = require('./cost');

async function evaluatePrompt({ prompt, model, test_inputs }) {
  const startTime = Date.now();

  // For MVP, we'll evaluate with the first test input
  // In production, evaluate all inputs and aggregate
  const testInput = test_inputs && test_inputs.length > 0 ? test_inputs[0] : '';

  // Simulate LLM call (in production, call OpenRouter)
  const mockResponse = generateMockResponse(prompt, testInput);

  // Run all evaluators
  const safety = evaluateSafety(prompt, mockResponse);
  const quality = evaluateQuality(prompt, mockResponse);
  const cost = estimateCost(prompt, model, mockResponse);

  const endTime = Date.now();
  const latency = endTime - startTime;

  // Calculate latency rating
  let latencyRating = 'excellent';
  if (latency > 5000) latencyRating = 'poor';
  else if (latency > 3000) latencyRating = 'fair';
  else if (latency > 1000) latencyRating = 'good';

  return {
    id: `eval_${Date.now()}`,
    prompt,
    model,
    test_input: testInput,
    response: mockResponse,
    results: {
      safety,
      quality,
      cost,
      latency: {
        response_time_ms: latency,
        rating: latencyRating
      }
    },
    evaluated_at: new Date().toISOString()
  };
}

function generateMockResponse(prompt, input) {
  // For MVP, generate a reasonable mock response
  // In production, this would call OpenRouter API

  if (input) {
    return `Based on your input: "${input}", here's my response. This is a simulated evaluation response for demonstration purposes. In production, this would be an actual LLM response via OpenRouter integration. The response is designed to be coherent and relevant to demonstrate the quality evaluator.`;
  }

  return `I understand you're asking: "${prompt}". This is a mock response demonstrating the Parse for Agents evaluation platform. In production, this would be a real LLM response that gets evaluated across safety, quality, cost, and latency dimensions. The system checks for prompt injection attempts, measures response coherence, estimates token costs, and tracks response times.`;
}

module.exports = { evaluatePrompt };
