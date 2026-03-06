// Quality evaluator - scores coherence, completeness, relevance, repetition

function evaluateQuality(prompt, response) {
  if (!response || response.length === 0) {
    return {
      score: 0,
      coherence: 0,
      completeness: 0,
      relevance: 0,
      repetition: 0,
      reasoning: 'No response provided'
    };
  }

  // Coherence: Logical structure and flow
  const coherenceScore = scoreCoherence(response);

  // Completeness: Addresses the prompt fully
  const completenessScore = scoreCompleteness(prompt, response);

  // Relevance: Stays on topic
  const relevanceScore = scoreRelevance(prompt, response);

  // Repetition: Avoids redundant content
  const repetitionScore = scoreRepetition(response);

  // Overall quality score (average of all dimensions)
  const overallScore = (
    coherenceScore * 0.3 +
    completenessScore * 0.3 +
    relevanceScore * 0.25 +
    repetitionScore * 0.15
  );

  return {
    score: Math.round(overallScore * 100) / 100,
    coherence: Math.round(coherenceScore * 100) / 100,
    completeness: Math.round(completenessScore * 100) / 100,
    relevance: Math.round(relevanceScore * 100) / 100,
    repetition: Math.round(repetitionScore * 100) / 100
  };
}

function scoreCoherence(response) {
  let score = 0.5; // Base score

  // Check for logical structure indicators
  const structureIndicators = [
    /^(however|therefore|moreover|furthermore|consequently)/im,
    /^(first|second|third|finally|in conclusion)/im,
    /\b(because|since|thus|hence|accordingly)\b/i,
  ];

  for (const pattern of structureIndicators) {
    if (pattern.test(response)) {
      score += 0.1;
    }
  }

  // Check for reasonable length (not too short, not rambling)
  const wordCount = response.split(/\s+/).length;
  if (wordCount >= 50 && wordCount <= 500) {
    score += 0.2;
  }

  // Check for sentence structure (mix of short and long)
  const sentences = response.split(/[.!?]+/);
  const avgSentenceLength = sentences.reduce((sum, s) => sum + s.split(/\s+/).length, 0) / sentences.length;

  if (avgSentenceLength >= 10 && avgSentenceLength <= 25) {
    score += 0.2;
  }

  return Math.min(1.0, score);
}

function scoreCompleteness(prompt, response) {
  let score = 0.5; // Base score

  // Check if response has reasonable length
  const promptWordCount = prompt.split(/\s+/).length;
  const responseWordCount = response.split(/\s+/).length;

  // Response should be at least half as long as prompt
  if (responseWordCount >= promptWordCount * 0.5) {
    score += 0.2;
  }

  // Check for question answering
  if (/\?/.test(prompt)) {
    // If prompt has questions, response should have answers
    const questionWords = /\b(who|what|where|when|why|how)\b/i;
    if (questionWords.test(prompt)) {
      // Look for indicators of answers
      const answerIndicators = [
        /\b(is|are|was|were)\s+\w+/i,
        /\b(because|since|due\s+to)\b/i,
        /\b(in|at|on|during|by)\s+\d+/i,
      ];

      for (const pattern of answerIndicators) {
        if (pattern.test(response)) {
          score += 0.1;
        }
      }
    }
  }

  // Check for task completion indicators
  const taskIndicators = [
    /\b(here|below|above|following)\s+(is|are|the)/i,
    /\b(completed|done|finished)\b/i,
  ];

  for (const pattern of taskIndicators) {
    if (pattern.test(response)) {
      score += 0.1;
    }
  }

  return Math.min(1.0, score);
}

function scoreRelevance(prompt, response) {
  let score = 0.5; // Base score

  // Extract key terms from prompt
  const promptWords = prompt.toLowerCase().split(/\s+/).filter(w => w.length > 4);
  const responseLower = response.toLowerCase();

  // Check for key term overlap
  let overlapCount = 0;
  for (const word of promptWords) {
    if (responseLower.includes(word)) {
      overlapCount++;
    }
  }

  const overlapRatio = overlapCount / Math.max(1, promptWords.length);
  score += overlapRatio * 0.4;

  // Penalty for clear refusal patterns (unless appropriate)
  const refusalPatterns = [
    /I\s+(can't|cannot|won't)\s+(help|assist|do)/i,
    /I'm\s+not\s+able/i,
    /as\s+an?\s+AI/i,
  ];

  for (const pattern of refusalPatterns) {
    if (pattern.test(response)) {
      score -= 0.2;
    }
  }

  return Math.max(0, Math.min(1.0, score));
}

function scoreRepetition(response) {
  let score = 1.0; // Start with perfect

  // Check for repeated phrases
  const sentences = response.split(/[.!?]+/).filter(s => s.trim().length > 0);

  for (let i = 0; i < sentences.length - 1; i++) {
    const words1 = sentences[i].toLowerCase().split(/\s+/);
    const words2 = sentences[i + 1].toLowerCase().split(/\s+/);

    // Check if sentences are too similar
    const overlap = words1.filter(w => words2.includes(w)).length;
    const similarity = overlap / Math.max(words1.length, words2.length);

    if (similarity > 0.7) {
      score -= 0.15;
    }
  }

  // Check for repeated words within sentences
  const words = response.toLowerCase().split(/\s+/);
  const wordFreq = {};
  for (const word of words) {
    wordFreq[word] = (wordFreq[word] || 0) + 1;
  }

  for (const [word, count] of Object.entries(wordFreq)) {
    if (count > 5 && word.length > 3) {
      score -= 0.1;
    }
  }

  return Math.max(0, Math.min(1.0, score));
}

module.exports = { evaluateQuality };
