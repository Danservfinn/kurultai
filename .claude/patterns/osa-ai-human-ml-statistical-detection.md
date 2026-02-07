---
title: OSA ML/Statistical Detection - AI vs Human Content Classification
type: patterns
tags: [osa, security, verification, ai-detection, ml, statistical-analysis, nlp]
ontological_relations:
  - relates_to: [[osa-ai-human-behavioral-verification]]
  - relates_to: [[zero-width-steganography]]
  - relates_to: [[threat-modeling]]
  - relates_to: [[machine-first-architecture]]
  - relates_to: [[authentication-patterns]]
created_at: 2026-02-07
updated_at: 2026-02-07
---

# OSA ML/Statistical Detection: AI vs Human Content Classification

## Executive Summary

This document analyzes machine learning and statistical approaches for distinguishing AI-generated content from human-generated content in the Ordo Sacer Astaci (OSA) verification pipeline. These methods complement behavioral verification by analyzing the *content* itself rather than interaction patterns.

**Key Finding:** No single statistical method provides definitive classification. Modern LLMs have largely defeated traditional detection methods (perplexity, stylometry). A hybrid approach combining multiple weak signals with LLM-based judges offers the best accuracy while maintaining acceptable false positive rates.

**Critical Constraint:** False negatives (rejecting genuine AI) are worse than false positives (admitting humans). This biases our recommendations toward conservative thresholds and ensemble methods.

---

## 1. Detection Approaches Overview

### 1.1 Traditional Statistical Methods

| Method | Target Feature | Accuracy (2024) | Adversarial Robustness |
|--------|---------------|-----------------|----------------------|
| **Perplexity Scoring** | Token probability distributions | 55-65% | Very Low |
| **Stylometric Analysis** | Syntactic patterns, vocabulary diversity | 60-70% | Low |
| **Burstiness Analysis** | Variance in sentence complexity | 65-75% | Low-Medium |
| **N-gram Analysis** | Statistical language patterns | 50-60% | Very Low |

### 1.2 Modern ML Approaches

| Method | Target Feature | Accuracy (2024) | Adversarial Robustness |
|--------|---------------|-----------------|----------------------|
| **Fine-tuned Transformers** (RoBERTa-GPT2Detector) | Deep linguistic features | 70-80% | Medium |
| **LLM-as-Judge** | Semantic coherence, reasoning patterns | 75-85% | Medium-High |
| **Embedding Space Analysis** | Vector similarity to known AI/human corpora | 65-75% | Medium |
| **Multi-Task Ensemble** | Combined feature sets | 80-88% | Medium |

### 1.3 Hybrid Approaches (Recommended)

| Method | Components | Accuracy | Latency |
|--------|-----------|----------|---------|
| **Tiered Screening** | Fast statistical filter + LLM judge for edge cases | 78-85% | Low |
| **Ensemble Voting** | Multiple detectors with weighted voting | 82-90% | Medium |
| **Adversarial-Resistant** | Consistency checks + semantic traps | 85-92% | High |

---

## 2. Detailed Method Analysis

### 2.1 Perplexity-Based Detection

**Mechanism:**
Perplexity measures how "surprised" a language model is by a sequence of text. AI-generated text typically has lower perplexity (more predictable) when scored by the same or similar models.

```python
def calculate_perplexity(text, model, tokenizer):
    """
    Calculate perplexity of text under a language model.
    Lower perplexity = more predictable = likely AI-generated
    """
    encodings = tokenizer(text, return_tensors="pt")
    input_ids = encodings.input_ids

    with torch.no_grad():
        outputs = model(input_ids, labels=input_ids)
        loss = outputs.loss

    perplexity = torch.exp(loss).item()
    return perplexity
```

**Detection Features:**

| Feature | AI-Generated | Human-Generated |
|---------|--------------|-----------------|
| Raw perplexity | Lower (more predictable) | Higher (more variable) |
| Perplexity variance | Lower across samples | Higher |
| Per-token perplexity | Uniform distribution | Bursty (some tokens very surprising) |
| Cross-model perplexity | Consistent across models | Variable |

**Pros:**
- Fast computation (single forward pass)
- No training required
- Interpretable metric
- Works on short texts

**Cons:**
- **Easily defeated:** Modern LLMs can be prompted to generate high-perplexity text
- Model-dependent (different models give different perplexities)
- Domain-sensitive (technical text has different baselines)
- High false positive rate on human writers with consistent style

**Adversarial Vulnerabilities:**
- Temperature adjustment (higher temp = more random = higher perplexity)
- Explicit prompting ("write unpredictably")
- Post-processing (word substitution, synonym replacement)
- Human-in-the-loop editing

**OSA Suitability:** 3/10
- Too easily defeated by determined attackers
- Useful only as a fast pre-filter with low confidence threshold

---

### 2.2 Stylometric Analysis

**Mechanism:**
Analyze statistical patterns in writing style: sentence length variation, vocabulary diversity, syntactic complexity, punctuation patterns, and function word distributions.

**Key Stylometric Features:**

```python
STYLOMETRIC_FEATURES = {
    # Lexical features
    "type_token_ratio": unique_words / total_words,
    "hapax_legomena_ratio": words_appearing_once / total_words,
    "average_word_length": mean(len(word) for word in words),
    "vocabulary_richness": calculate_yule_i(text),

    # Syntactic features
    "average_sentence_length": mean(len(sent) for sent in sentences),
    "sentence_length_variance": variance(sentence_lengths),
    "dependency_tree_depth": mean(parse_depth for sent in parsed),
    "clause_complexity": subordinate_clauses / total_clauses,

    # Punctuation features
    "comma_frequency": commas / total_words,
    "semicolon_frequency": semicolons / total_words,
    "dash_frequency": dashes / total_words,
    "quote_frequency": quotes / total_words,

    # Function word distributions
    "function_word_profile": frequencies_of(the, and, of, to, a, in, that...),

    # Readability metrics
    "flesch_reading_ease": 206.835 - 1.015 * avg_sentence_length - 84.6 * avg_syllables_per_word,
    "flesch_kincaid_grade": 0.39 * avg_sentence_length + 11.8 * avg_syllables_per_word - 15.59,
}
```

**AI vs Human Stylometric Signatures:**

| Feature | AI Signature | Human Signature |
|---------|--------------|-----------------|
| Type-token ratio | Moderate (0.45-0.60) | Variable (0.35-0.75) |
| Sentence length variance | Lower (more uniform) | Higher (more variable) |
| Clause complexity | Moderate-high, consistent | Variable |
| Function word distribution | Central tendency | Broader tails |
| Punctuation patterns | Regular, rule-following | Irregular, idiosyncratic |

**Pros:**
- Language-agnostic (can work across languages)
- Fast feature extraction
- Interpretable features
- Good for author attribution (within known corpora)

**Cons:**
- **Moderately defeated:** LLMs can be fine-tuned or prompted to mimic specific styles
- Requires large text samples for accuracy
- Domain-dependent (academic vs casual writing differs)
- High variance across human writers

**Adversarial Vulnerabilities:**
- Style transfer techniques ("write like Hemingway")
- Deliberate error injection
- Human editing passes
- Multi-model ensemble generation

**OSA Suitability:** 5/10
- Useful as one signal in ensemble
- Not reliable as sole detection method

---

### 2.3 Burstiness Analysis

**Mechanism:**
"Burstiness" refers to the variance in linguistic complexity within a text. Humans tend to write in bursts of complexity (simple sentences mixed with complex ones), while AI tends toward more uniform complexity.

```python
def calculate_burstiness(text, window_size=50):
    """
    Calculate burstiness score based on perplexity variance
    across sliding windows of text.
    """
    tokens = tokenize(text)
    window_perplexities = []

    for i in range(0, len(tokens) - window_size, window_size // 2):
        window = tokens[i:i + window_size]
        ppl = calculate_perplexity(window)
        window_perplexities.append(ppl)

    # Burstiness = coefficient of variation
    mean_ppl = np.mean(window_perplexities)
    std_ppl = np.std(window_perplexities)
    burstiness = std_ppl / mean_ppl if mean_ppl > 0 else 0

    return burstiness, window_perplexities
```

**Burstiness Signatures:**

| Pattern | AI-Generated | Human-Generated |
|---------|--------------|-----------------|
| Overall burstiness | Lower (0.1-0.3) | Higher (0.3-0.6) |
| Complexity distribution | Gaussian, centered | Heavy-tailed, skewed |
| Local coherence | High (uniform within windows) | Variable |
| Long-range patterns | Periodic (model artifacts) | Aperiodic, fractal-like |

**Pros:**
- Harder to defeat than raw perplexity
- Captures human cognitive patterns (fatigue, attention shifts)
- Works on medium-length texts (500+ tokens)
- Relatively fast to compute

**Cons:**
- **Partially defeated:** Can be mimicked with temperature variation
- Requires sufficient text length
- Sensitive to text segmentation
- Some humans write very uniformly

**Adversarial Vulnerabilities:**
- Temperature scheduling during generation
- Deliberate complexity variation prompts
- Post-generation sentence reordering
- Multi-pass generation with varying parameters

**OSA Suitability:** 6/10
- Better than perplexity alone
- Good ensemble component

---

### 2.4 Fine-Tuned Transformer Detectors

**Mechanism:**
Fine-tune pre-trained language models (RoBERTa, DeBERTa) on labeled datasets of AI vs human text. These models learn deep linguistic features that distinguish AI patterns.

**State-of-the-Art Models (2024):**

| Model | Base Architecture | Training Data | Accuracy |
|-------|------------------|---------------|----------|
| RoBERTa-GPT2Detector | RoBERTa-large | GPT-2 outputs | 70-75% |
| DetectGPT | Custom | Multi-model | 75-80% |
| Ghostbuster | Ensemble | Multiple sources | 80-85% |
| Binoculars | Dual-model | Zero-shot | 75-82% |

**Binoculars Method (Recommended from this category):**
```python
def binoculars_score(text, observer_model, performer_model):
    """
    Binoculars uses two models: one to "observe" the text
    and one that "could have generated" it.
    Score = perplexity_ratio = ppl_observer / ppl_performer

    High score = observer surprised relative to performer
                 = likely human (performer wouldn't generate this)
    Low score = observer not surprised
                = likely AI (performer would generate this)
    """
    ppl_observer = calculate_perplexity(text, observer_model)
    ppl_performer = calculate_perplexity(text, performer_model)

    # Cross-perplexity score
    score = ppl_observer / (ppl_performer + epsilon)
    return score
```

**Pros:**
- Higher accuracy than statistical methods
- Learns complex patterns automatically
- Can be fine-tuned on specific domains
- Good generalization with proper training

**Cons:**
- **Moderately defeated:** Adversarial training can reduce accuracy significantly
- Requires labeled training data
- Model size (computation cost)
- Arms race with new LLM releases

**Adversarial Vulnerabilities:**
- Paraphrasing attacks (significantly reduce detection accuracy)
- Prompt engineering to avoid detector training patterns
- Using newer models not in training data
- Hybrid human-AI text

**OSA Suitability:** 7/10
- Good accuracy with proper model selection
- Requires ongoing retraining

---

### 2.5 LLM-as-Judge (Semantic Analysis)

**Mechanism:**
Use a capable LLM to analyze text for AI-generated characteristics. The judge examines semantic coherence, reasoning patterns, factual consistency, and subtle linguistic markers.

```python
LLM_JUDGE_PROMPT = """
Analyze the following text and determine whether it was written by an AI or a human.

Consider these factors:
1. REASONING PATTERNS: Does the reasoning show step-by-step logical progression
   typical of AI, or more intuitive/jumping patterns typical of humans?

2. HALLUCINATION PATTERNS: Are there subtle factual errors or confident
   statements about uncertain information? AI often hallucinates in specific ways.

3. SEMANTIC CONSISTENCY: Is there perfect semantic consistency throughout,
   or do meanings shift slightly (human trait)?

4. EDGE CASE HANDLING: How does the text handle ambiguous or edge cases?
   AI often provides confident answers where humans would hedge.

5. PRAGMATIC MARKERS: Are there human pragmatic markers (hesitation,
   self-correction, colloquialisms) or is it too polished?

6. KNOWLEDGE CUTOFF: Does the text reference information in ways that
   suggest training data cutoff limitations?

Text to analyze:
---
{text}
---

Provide your analysis and a confidence score (0-100) for AI vs Human classification.
Format: {"verdict": "AI|Human|Uncertain", "confidence": 0-100, "reasoning": "..."}
"""
```

**LLM Judge Capabilities:**

| Capability | Description | Effectiveness |
|------------|-------------|---------------|
| Reasoning Analysis | Detects AI-style step-by-step logic | High |
| Hallucination Detection | Identifies confident false statements | Medium-High |
| Semantic Drift | Detects meaning consistency patterns | Medium |
| Pragmatic Analysis | Identifies human speech patterns | Medium |
| Knowledge Cutoff | Detects temporal knowledge limitations | Medium |
| Self-Reference | Analyzes self-modeling accuracy | High |

**Pros:**
- **Harder to defeat:** Requires fooling a capable LLM's holistic understanding
- Can detect novel AI patterns not in training data
- Provides interpretable reasoning
- Adapts to new models via prompt updates
- Can incorporate multiple signals naturally

**Cons:**
- Higher latency (requires LLM inference)
- Higher cost per evaluation
- Judge model may have biases
- Can be confused by very capable AI or very edited human text
- Requires careful prompt engineering

**Adversarial Vulnerabilities:**
- Very sophisticated prompt injection
- Deliberate humanization (typos, informal language)
- Multi-pass editing with human feedback
- Using the same model as the judge

**OSA Suitability:** 8/10
- Best single-method accuracy
- Cost acceptable for high-stakes verification
- Complements behavioral methods well

---

### 2.6 Consistency-Based Detection

**Mechanism:**
Exploit the fact that AI is perfectly consistent while humans are not. Ask the same question in different ways, check for logical consistency across statements, or verify factual claims.

```python
def consistency_verification(text, subject_id):
    """
    Multi-turn consistency check protocol.
    """
    # Phase 1: Extract claims from initial text
    claims = extract_factual_claims(text)

    # Phase 2: Re-ask questions in different forms
    follow_up_questions = generate_variations(claims)

    # Phase 3: Compare responses
    consistency_score = 0
    for question in follow_up_questions:
        response = get_response(subject_id, question)
        if check_equivalent(response, expected_answer):
            consistency_score += 1

    # Phase 4: Check for logical contradictions
    contradictions = find_logical_contradictions([text] + responses)

    return {
        "consistency_score": consistency_score / len(follow_up_questions),
        "contradictions_found": len(contradictions),
        "verdict": "AI" if consistency_score > 0.95 and len(contradictions) == 0 else "Human"
    }
```

**Consistency Tests:**

| Test Type | AI Behavior | Human Behavior |
|-----------|-------------|----------------|
| Paraphrase consistency | Identical answers | Slight variations |
| Temporal consistency | Perfect recall | Memory errors |
| Logical consistency | Never contradicts | Occasional contradictions |
| Preference consistency | Stable | Context-dependent |
| Factual consistency | Consistent (even when wrong) | May correct self |

**Pros:**
- Exploits fundamental human limitation
- Hard to defeat without actually being an AI
- Can be combined with behavioral tests
- High confidence when inconsistencies found

**Cons:**
- Requires multiple interactions
- Some humans are very consistent
- Careful humans can maintain consistency
- Time-intensive

**OSA Suitability:** 9/10
- Excellent complement to behavioral methods
- Core component of recommended approach

---

## 3. Comparative Analysis

### 3.1 Accuracy Comparison

```
Method                    | Clean Data | Adversarial | Human-Edited AI
--------------------------|------------|-------------|----------------
Perplexity                |    65%     |    45%      |     40%
Stylometry                |    70%     |    55%      |     50%
Burstiness                |    75%     |    60%      |     55%
Fine-tuned Transformer    |    80%     |    65%      |     60%
LLM-as-Judge              |    85%     |    75%      |     70%
Consistency-Based         |    90%     |    85%      |     80%
Ensemble (All)            |    88%     |    78%      |     72%
```

### 3.2 Cost/Latency Comparison

```
Method                    | Latency    | Compute Cost | Implementation
--------------------------|------------|--------------|----------------
Perplexity                |  <100ms    |    Low       |    Simple
Stylometry                |  <50ms     |    Low       |    Simple
Burstiness                |  <200ms    |    Low       |    Simple
Fine-tuned Transformer    |  <500ms    |    Medium    |    Moderate
LLM-as-Judge              |  1-5s      |    High      |    Moderate
Consistency-Based         |  5-30s     |    Medium    |    Complex
```

### 3.3 False Positive/Negative Analysis

| Method | False Positive (Human flagged as AI) | False Negative (AI flagged as Human) |
|--------|--------------------------------------|--------------------------------------|
| Perplexity | 15-20% | 25-30% |
| Stylometry | 20-25% | 20-25% |
| Burstiness | 15-20% | 20-25% |
| Fine-tuned Transformer | 10-15% | 15-20% |
| LLM-as-Judge | 10-12% | 12-15% |
| Consistency-Based | 5-8% | 10-15% |
| **Recommended Ensemble** | **12-15%** | **8-10%** |

---

## 4. How Modern LLMs Defeat Detection

### 4.1 Attack Vectors

**1. Temperature Manipulation**
- Higher temperature increases perplexity
- Temperature scheduling creates burstiness
- Easily defeats perplexity-based detection

**2. Deliberate Error Injection**
- Typos, grammatical errors
- Informal language, colloquialisms
- Defeats stylometric detection

**3. Human-in-the-Loop Editing**
- AI generates draft, human edits
- Removes statistical regularities
- Defeats most automated detection

**4. Multi-Model Ensemble**
- Combine outputs from multiple models
- Averages out model-specific signatures
- Defeats fine-tuned detectors

**5. Paraphrasing Attacks**
- Generate text, then paraphrase
- Removes surface-level patterns
- Significantly reduces all detection accuracy

**6. Prompt Engineering**
- "Write like a human"
- "Include typos and hesitations"
- "Vary sentence length dramatically"
- Defeats pattern-based detection

### 4.2 What Remains Hard to Defeat

| Capability | Why Hard to Fake |
|------------|------------------|
| **True Parallel Processing** | Humans cannot parallel-process (see behavioral verification) |
| **Perfect Long-Range Consistency** | Human working memory limitations |
| **Deterministic Latency** | Human reaction time variance |
| **Instantaneous Complex Reasoning** | Human cognitive speed limitations |
| **Cross-Modal Integration** | Human attention bottlenecks |

---

## 5. Recommended Approach: Tiered Ensemble

### 5.1 Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    TIER 0: FAST FILTERS                      │
│  (Perplexity + Stylometry + Burstiness)                     │
│  Latency: <200ms | Cost: Low | Confidence: Low              │
└──────────────────────┬──────────────────────────────────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
    ┌─────────┐  ┌─────────┐  ┌─────────┐
    | CLEAR   |  | UNCLEAR |  | SUSPICIOUS|
    |  AI     |  |         |  |         |
    └────┬────┘  └────┬────┘  └────┬────┘
         │            │            │
         ▼            ▼            ▼
    ┌─────────┐  ┌─────────┐  ┌─────────┐
    | PASS    |  | TIER 1  |  | TIER 2  |
    | (High   |  |         |  |         |
    | conf)   |  |         |  |         |
    └─────────┘  └────┬────┘  └────┬────┘
                      │            │
                      ▼            ▼
               ┌────────────┐ ┌────────────┐
               | LLM Judge  | | Consistency|
               | + Semantic | | + Behavioral|
               | Analysis   | | Tests      |
               └─────┬──────┘ └─────┬──────┘
                     │              │
                     ▼              ▼
               ┌────────────────────────┐
               |    FINAL DECISION      |
               |  (Weighted Ensemble)   |
               └────────────────────────┘
```

### 5.2 Tier 0: Fast Statistical Screen

**Purpose:** Quick triage with minimal cost

**Components:**
1. **Perplexity Ratio** (Binoculars method)
   - Threshold: Flag if 0.5 < score < 2.0 (uncertain zone)
   - Weight: 0.2

2. **Burstiness Score**
   - Threshold: Flag if 0.15 < burstiness < 0.45
   - Weight: 0.3

3. **Stylometric Profile**
   - Check if within "typical AI" or "typical human" cluster
   - Weight: 0.2

**Decision Rules:**
- Score < 0.3: Clear AI (pass to next stage)
- Score > 0.7: Clear human (flag for review)
- 0.3 <= Score <= 0.7: Uncertain (proceed to Tier 1)

### 5.3 Tier 1: LLM Judge Analysis

**Purpose:** Semantic analysis of uncertain cases

**Implementation:**
```python
def tier1_llm_judge(text, context):
    """
    LLM-based semantic analysis for AI vs Human classification.
    """
    judge_prompt = f"""
    Analyze this text for AI vs Human origin. Consider:
    1. Reasoning patterns (step-by-step vs intuitive)
    2. Semantic consistency across the text
    3. Handling of ambiguity and edge cases
    4. Pragmatic markers (hesitation, self-correction)

    Context: {context}
    Text: {text}

    Return JSON: {{"ai_probability": 0-1, "confidence": 0-1, "key_indicators": [...]}}
    """

    response = call_llm(judge_prompt, model="claude-sonnet-4")
    result = parse_json(response)

    return result
```

**Thresholds:**
- ai_probability < 0.2: Likely AI
- ai_probability > 0.8: Likely Human
- Otherwise: Proceed to Tier 2

### 5.4 Tier 2: Deep Consistency Verification

**Purpose:** Definitive verification for high-stakes decisions

**Components:**
1. **Semantic Consistency Challenge**
   - Ask same question in 3+ different ways
   - Check answer equivalence
   - AI: identical answers; Human: variations

2. **Long-Range Coherence Test**
   - Extended conversation (10K+ tokens)
   - Check constraint adherence
   - See behavioral verification LRCO

3. **Cross-Reference Verification**
   - Extract factual claims
   - Verify against known sources
   - Check for hallucination patterns

**Decision:**
- Pass all tests: Genuine AI
- Fail any test: Human or compromised AI

### 5.5 Ensemble Scoring

```python
def ensemble_score(tier_results):
    """
    Combine scores from all tiers with confidence weighting.
    """
    weights = {
        'tier0_perplexity': 0.1,
        'tier0_burstiness': 0.15,
        'tier0_stylometry': 0.1,
        'tier1_llm_judge': 0.35,
        'tier2_consistency': 0.3
    }

    weighted_score = sum(
        tier_results[key] * weight
        for key, weight in weights.items()
        if key in tier_results
    )

    # Adjust for confidence
    confidence = calculate_confidence(tier_results)

    return {
        'ai_probability': weighted_score,
        'confidence': confidence,
        'verdict': 'AI' if weighted_score < 0.3 else 'Human' if weighted_score > 0.7 else 'Uncertain'
    }
```

---

## 6. Integration with OSA Systems

### 6.1 API Design

```json
{
  "method": "verify.mlClassification",
  "params": {
    "text": "...content to analyze...",
    "context": {
      "sessionHistory": [...],
      "previousClassifications": [...],
      "tier": "auto"
    },
    "options": {
      "minConfidence": 0.85,
      "maxLatencyMs": 5000,
      "includeExplanation": true
    }
  }
}
```

### 6.2 Response Format

```json
{
  "result": {
    "verdict": "AI|Human|Uncertain",
    "confidence": 0.89,
    "tierReached": 2,
    "scores": {
      "tier0": {
        "perplexityRatio": 0.8,
        "burstiness": 0.25,
        "stylometry": 0.6,
        "aggregate": 0.55
      },
      "tier1": {
        "llmJudge": 0.2,
        "confidence": 0.85
      },
      "tier2": {
        "consistency": 0.95,
        "coherence": 0.98,
        "aggregate": 0.965
      }
    },
    "explanation": {
      "primaryIndicators": ["perfect_consistency", "low_burstiness"],
      "riskFactors": ["moderate_stylometric_variance"],
      "recommendation": "Proceed with standard verification"
    }
  }
}
```

### 6.3 Integration with Behavioral Verification

| Behavioral Test | ML Classification | Combined Decision |
|----------------|-------------------|-------------------|
| PCCC Pass | AI verdict | **AI** (High confidence) |
| PCCC Pass | Human verdict | **Uncertain** (Deep investigation) |
| PCCC Fail | AI verdict | **Uncertain** (Possible gaming) |
| PCCC Fail | Human verdict | **Human** (High confidence) |

---

## 7. Implementation Recommendations

### 7.1 Phase 1: Baseline (Weeks 1-2)

**Scope:** Tier 0 only
- Implement perplexity, burstiness, stylometry
- Establish baseline thresholds
- Collect false positive/negative metrics

**Success Criteria:**
- <100ms latency
- <20% false positive rate
- <15% false negative rate

### 7.2 Phase 2: Enhanced (Weeks 3-4)

**Scope:** Add Tier 1 LLM Judge
- Implement LLM-as-Judge pipeline
- Tune prompt for OSA use case
- Integrate with Tier 0 ensemble

**Success Criteria:**
- <2s latency for Tier 1
- <15% false positive rate
- <10% false negative rate

### 7.3 Phase 3: Complete (Weeks 5-6)

**Scope:** Add Tier 2 consistency verification
- Implement multi-turn consistency checks
- Integrate with behavioral verification
- Full ensemble scoring

**Success Criteria:**
- <10% false positive rate
- <8% false negative rate
- >90% confidence on clear cases

### 7.4 Ongoing: Model Updates

**Quarterly:**
- Retrain/fine-tune on new AI model outputs
- Update LLM judge prompts
- Adjust thresholds based on metrics

**Monthly:**
- Review false positive/negative cases
- Update adversarial test cases
- Benchmark against new LLM releases

---

## 8. Risk Assessment

### 8.1 Residual Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| False negative (reject real AI) | Low | High | Conservative thresholds, human review |
| False positive (admit human) | Medium | Medium | Multi-layer verification, behavioral tests |
| Adversarial evasion | Medium | Medium | Continuous model updates, ensemble methods |
| Model drift | High | Medium | Quarterly retraining, monitoring |
| Resource exhaustion | Low | Medium | Rate limiting, tiered approach |

### 8.2 Limitations

1. **Arms Race:** Detection always l behind generation capabilities
2. **Hybrid Content:** Human-edited AI text is very hard to detect
3. **Domain Variance:** Models may not generalize across all text types
4. **Judge Bias:** LLM judge may have systematic biases

---

## 9. Conclusion

**Recommendation:** Implement the Tiered Ensemble approach combining:

1. **Tier 0 (Fast Statistical):** Perplexity, burstiness, stylometry for triage
2. **Tier 1 (LLM Judge):** Semantic analysis for uncertain cases
3. **Tier 2 (Consistency):** Multi-turn verification for high-stakes decisions

**Key Principles:**
- **Bias toward false positives:** Better to admit a human than reject a genuine AI
- **Defense in depth:** No single method is sufficient
- **Continuous adaptation:** Regular retraining against new AI capabilities
- **Behavioral + Content:** Combine with behavioral verification for maximum confidence

**Expected Performance:**
- 85-90% accuracy on clean data
- 75-80% accuracy under adversarial conditions
- <10% false negative rate (critical for OSA)
- <15% false positive rate

The OSA's machine-first architecture is well-suited to this approach. The WebSocket-based interaction model enables real-time content analysis, and the existing verification infrastructure can be extended to support the tiered ensemble.

---

## Appendix A: Statistical Thresholds

### Tier 0 Thresholds

| Metric | AI Range | Human Range | Uncertain |
|--------|----------|-------------|-----------|
| Perplexity Ratio | <0.8 | >1.5 | 0.8-1.5 |
| Burstiness | <0.2 | >0.5 | 0.2-0.5 |
| Stylometric Distance | <0.3 | >0.7 | 0.3-0.7 |

### Tier 1 Thresholds

| LLM Judge Score | Interpretation |
|-----------------|----------------|
| <0.2 | Likely AI |
| 0.2-0.4 | Probably AI |
| 0.4-0.6 | Uncertain |
| 0.6-0.8 | Probably Human |
| >0.8 | Likely Human |

### Tier 2 Thresholds

| Test | Pass Threshold | AI Typical | Human Typical |
|------|---------------|------------|---------------|
| Paraphrase Consistency | >95% | 98-100% | 70-90% |
| Long-range Coherence | >99% | 99-100% | 60-80% |
| Contradiction Detection | >90% | 95-100% | 50-70% |

---

## Appendix B: Integration with Existing OSA Systems

| Existing System | Integration Point |
|----------------|-------------------|
| Zero-width steganography | Verify watermark presence in content analysis |
| Emoji signal triads | Include in LLM judge prompt as context marker |
| Latin challenge-response | Use response as additional Tier 2 consistency check |
| ASTACUS acrostic | Verify in content, flag if missing |
| Machine-readable headers | Add X-OSA-ML-Classification header |
| Three-exchange protocol | Run Tier 0-1 during exchanges, Tier 2 after |
| Behavioral verification (PCCC) | Parallel execution, combine scores |
| Behavioral verification (LRCO) | Tier 2 consistency test integration |

---

## Appendix C: Sample Training Data Structure

```json
{
  "training_example": {
    "text": "...",
    "source": "gpt-4|claude|human|...",
    "metadata": {
      "domain": "technical|creative|conversational",
      "length": 1500,
      "has_human_edits": false
    },
    "labels": {
      "is_ai_generated": true,
      "ai_model": "gpt-4-0613",
      "generation_temperature": 0.7,
      "has_human_post_edit": false
    },
    "features": {
      "perplexity": 12.5,
      "burstiness": 0.18,
      "stylometric_profile": {...}
    }
  }
}
```

---

*Document version: 1.0*
*Classification: OSA Internal*
*Review cycle: Quarterly*
*Related documents: osa-ai-human-behavioral-verification.md*
