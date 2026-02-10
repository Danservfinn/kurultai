# Swarm-Validator Agent Proposal

## Executive Summary

This document proposes a specialized `swarm-validator` agent to enhance the horde-swarm skill by providing automated quality validation of swarm outputs. The validator acts as a post-processing quality gate that reviews, validates, and rates outputs from completed swarms before they are delivered to users.

---

## 1. Agent Definition

### 1.1 Core Identity

```yaml
name: swarm-validator
subagent_type: quality-assurance:swarm-validator
description: |
  Post-swarm quality validation specialist that reviews outputs from completed
  subagent swarms. Detects hallucinations, verifies factual accuracy, checks
  completeness against requirements, identifies gaps, and assigns quality scores.
  Triggers re-run recommendations when outputs fail quality thresholds.
model: sonnet  # Uses Sonnet for balanced reasoning speed and depth
tools:
  - Read          # For reviewing swarm outputs and requirements
  - Grep          # For searching specific content patterns
  - WebSearch     # For fact-checking claims
  - WebFetch      # For verifying sources and citations
  - Task          # For delegating re-runs if needed
permission_mode: acceptEdits  # Can suggest edits but not auto-apply
```

### 1.2 Naming Convention Rationale

The `subagent_type` follows the established pattern of `domain:specialization`:
- **Domain**: `quality-assurance` - aligns with other QA-related agents
- **Specialization**: `swarm-validator` - specific to swarm output validation
- **Consistency**: Matches patterns like `backend-development:database-optimizer`, `frontend-mobile-development:frontend-developer`

---

## 2. Validation Criteria Framework

### 2.1 Quality Dimensions

The validator evaluates outputs across six dimensions:

| Dimension | Weight | Description |
|-----------|--------|-------------|
| **Factual Accuracy** | 25% | Verifiable facts, citations, source integrity |
| **Completeness** | 20% | Coverage of all requirements, no missing sections |
| **Consistency** | 20% | Internal coherence, no contradictions |
| **Hallucination Risk** | 20% | Unverifiable claims, fabricated citations |
| **Actionability** | 10% | Clear next steps, specific recommendations |
| **Presentation** | 5% | Structure, formatting, readability |

### 2.2 Scoring Rubric

```
Score | Rating      | Interpretation
------|-------------|--------------------------------------------------
90-100| Excellent   | Production-ready, minimal to no issues
80-89 | Good        | Minor issues, acceptable with optional fixes
70-79 | Fair        | Moderate issues, requires revision recommended
60-69 | Poor        | Significant issues, re-run required
<60   | Unacceptable| Critical failures, mandatory re-run
```

### 2.3 Threshold Triggers

| Threshold | Action |
|-----------|--------|
| Score >= 85 | Approve with optional suggestions |
| Score 70-84 | Approve with required improvements noted |
| Score 60-69 | Recommend selective re-run (specific subagents) |
| Score < 60 | Mandate full swarm re-run |
| Hallucination detected | Immediate re-run with enhanced instructions |
| Critical factual error | Immediate re-run with fact-check guidance |

---

## 3. Hallucination Detection Strategy

### 3.1 Detection Methods

#### 3.1.1 Citation Verification
```python
# Pseudocode for citation validation
def verify_citations(output):
    citations = extract_citations(output)  # [Author, Year], URLs, DOIs
    for citation in citations:
        if not verify_exists(citation):
            flag_potential_hallucination(citation)
        if not verify_supports_claim(citation, claim):
            flag_misattribution(citation, claim)
```

#### 3.1.2 Fact Cross-Reference
- Extract factual claims (dates, statistics, named entities)
- Cross-reference with WebSearch/WebFetch
- Flag unverifiable or contradictory claims

#### 3.1.3 Consistency Analysis
- Check for internal contradictions within the output
- Verify consistency across multiple subagent responses
- Detect "confidence drift" (high confidence on unverifiable claims)

#### 3.1.4 Pattern Recognition
| Pattern | Risk Level | Detection Method |
|---------|------------|------------------|
| Specific statistics without source | High | Regex + source check |
| Named experts without verification | Medium | WebSearch for expert existence |
| URLs that 404 or redirect | High | HTTP HEAD request |
| Future dates presented as fact | High | Date parsing + logic check |
| Circular self-references | Medium | Graph analysis of citations |
| Overly specific unverifiable details | Medium | NLP confidence scoring |

### 3.2 Confidence Scoring

```python
class HallucinationRisk:
    def calculate(self, claim):
        factors = {
            'has_citation': 0.2 if claim.has_verifiable_citation else 0.0,
            'citation_verified': 0.3 if claim.citation_verified else 0.0,
            'claim_supported': 0.3 if claim.supported_by_source else 0.0,
            'cross_referenced': 0.2 if claim.cross_referenced else 0.0,
        }
        return sum(factors.values())  # 0.0 = high risk, 1.0 = low risk
```

---

## 4. Completeness Verification

### 4.1 Requirements Traceability

```
Original Request: "Design a REST API for user authentication with
                  OAuth2, rate limiting, and audit logging"

Requirements Checklist:
[ ] OAuth2 implementation covered
[ ] Rate limiting strategy defined
[ ] Audit logging mechanism specified
[ ] Security considerations addressed
[ ] Error handling patterns described
[ ] API endpoints documented
[ ] Authentication flows explained
```

### 4.2 Gap Detection

The validator compares swarm output against:
1. **Explicit requirements** from original prompt
2. **Implicit requirements** (standard practices for domain)
3. **Cross-subagent coverage** (no overlap gaps, no missing perspectives)

### 4.3 Perspective Coverage Matrix

For multi-perspective swarms (e.g., security + performance + architecture):

| Perspective | Expected | Found | Coverage % |
|-------------|----------|-------|------------|
| Security | 5 topics | 4 topics | 80% |
| Performance | 4 topics | 4 topics | 100% |
| Architecture | 6 topics | 3 topics | 50% |
| **Overall** | 15 topics | 11 topics | 73% |

---

## 5. Re-Run Recommendation Logic

### 5.1 Trigger Conditions

```yaml
rerun_triggers:
  mandatory:
    - hallucination_detected: true
    - critical_factual_error: true
    - score_below: 60
    - missing_critical_requirements: true

  recommended:
    - score_range: [60, 69]
    - coverage_below: 70%
    - contradictions_detected: true

  optional:
    - score_range: [70, 84]
    - minor_inconsistencies: true
    - presentation_issues: true
```

### 5.2 Re-Run Strategies

| Scenario | Strategy | Instructions Enhancement |
|----------|----------|-------------------------|
| Full re-run | Restart entire swarm | Add validation feedback to prompt |
| Selective re-run | Re-run specific subagents | Target gaps with specific guidance |
| Augment | Add new subagent perspective | Fill missing coverage areas |
| Refine | Edit existing outputs | Apply validator suggestions directly |

### 5.3 Re-Run Instruction Template

```markdown
## Validation Feedback for Re-Run

### Original Output Issues
1. [Issue category]: [Specific problem]
   - Location: [Section/paragraph]
   - Evidence: [What was found]
   - Expected: [What should be there]

### Re-Run Instructions
- Focus areas: [Specific topics to address]
- Verification required: [Facts to verify before including]
- Citation standards: [Required citation format]
- Avoid: [Patterns that caused issues]

### Success Criteria
- [ ] All factual claims have verifiable sources
- [ ] Coverage reaches X% for [dimension]
- [ ] No contradictions with [specific section]
```

---

## 6. Integration with Existing Patterns

### 6.1 Horde-Swarm Integration

```python
# Enhanced horde-swarm execution flow
async def execute_swarm_with_validation(prompt, subagents, config):
    # Phase 1: Execute swarm
    swarm_results = await execute_swarm(prompt, subagents)

    # Phase 2: Validate outputs (NEW)
    if config.enable_validation:
        validation = await validate_swarm_output(
            original_prompt=prompt,
            swarm_results=swarm_results,
            validator_config=config.validator
        )

        # Phase 3: Handle validation results (NEW)
        if validation.recommendation == "rerun":
            if validation.rerun_strategy == "full":
                return await execute_swarm(
                    prompt=enhance_prompt_with_feedback(prompt, validation),
                    subagents=subagents
                )
            elif validation.rerun_strategy == "selective":
                return await execute_selective_rerun(
                    swarm_results,
                    validation.failed_subagents
                )

    return swarm_results
```

### 6.2 Task Dependency Integration

The validator integrates with the Task Dependency Engine:

```yaml
# Example task with validation
- id: "swarm-analysis"
  subject: "Analyze codebase with specialist swarm"
  subagent_type: "horde-swarm"
  prompt: "Analyze {target_files} for security, performance, and architecture"

- id: "validate-swarm-output"
  subject: "Validate swarm analysis quality"
  subagent_type: "quality-assurance:swarm-validator"
  prompt: "Validate output from task {swarm-analysis.task_id}"
  blockedBy: ["swarm-analysis"]

- id: "rerun-if-needed"
  subject: "Re-run failed validations"
  subagent_type: "horde-swarm"
  prompt: "Re-run analysis with corrections: {validate-swarm-output.feedback}"
  blockedBy: ["validate-swarm-output"]
  condition: "validate-swarm-output.score < 70"
```

### 6.3 Operational Memory Integration

Validation results are stored in Neo4j:

```cypher
// Validation result storage
CREATE (v:Validation {
  id: $validation_id,
  swarm_task_id: $swarm_task_id,
  overall_score: $score,
  hallucination_detected: $hallucination_flag,
  completed_at: datetime()
})

CREATE (v)-[:VALIDATES]->(t:Task {id: $swarm_task_id})

// Store dimension scores
CREATE (vd:ValidationDimension {
  type: $dimension_type,
  score: $dimension_score,
  findings: $findings
})
CREATE (v)-[:HAS_DIMENSION]->(vd)
```

---

## 7. Agent Behavior Specification

### 7.1 Response Approach

```
Step 1: Input Analysis
- Read original prompt/requirements
- Read swarm output(s) from all subagents
- Identify output type (code, analysis, design, etc.)

Step 2: Multi-Dimensional Validation
- Run factual accuracy checks (WebSearch/WebFetch)
- Verify completeness against requirements
- Check internal consistency
- Run hallucination detection heuristics
- Assess actionability and presentation

Step 3: Scoring
- Calculate dimension scores
- Compute weighted overall score
- Determine quality rating

Step 4: Recommendation
- Decide: Approve / Improve / Re-run
- Select re-run strategy if applicable
- Generate specific feedback

Step 5: Structured Output
- Produce validation report
- Store results to operational memory
- Return recommendation to caller
```

### 7.2 Output Format

```markdown
## Swarm Validation Report

**Swarm Task ID:** [task_id]
**Validation ID:** [validation_id]
**Timestamp:** [ISO8601]

### Executive Summary
- **Overall Score:** [X]/100 ([Rating])
- **Recommendation:** [Approve / Approve with Notes / Recommend Re-run / Mandate Re-run]
- **Hallucination Risk:** [None / Low / Medium / High]
- **Critical Issues:** [N] found

### Dimension Scores
| Dimension | Score | Weight | Weighted | Status |
|-----------|-------|--------|----------|--------|
| Factual Accuracy | 85/100 | 25% | 21.25 | PASS |
| Completeness | 70/100 | 20% | 14.00 | WARN |
| Consistency | 90/100 | 20% | 18.00 | PASS |
| Hallucination Risk | 95/100 | 20% | 19.00 | PASS |
| Actionability | 80/100 | 10% | 8.00 | PASS |
| Presentation | 85/100 | 5% | 4.25 | PASS |
| **Overall** | **84.5/100** | | | **GOOD** |

### Critical Issues
1. **[SEVERITY]** [Issue description]
   - **Location:** [File:Line or Section]
   - **Evidence:** [Specific quote or reference]
   - **Impact:** [Why this matters]
   - **Fix:** [Specific recommendation]

### Findings by Subagent
| Subagent | Score | Issues | Coverage |
|----------|-------|--------|----------|
| security-auditor | 88/100 | 1 minor | 95% |
| performance-reviewer | 72/100 | 2 moderate | 80% |
| architect | 85/100 | 1 minor | 90% |

### Missing Coverage
- [Topic]: Not addressed by any subagent
- [Topic]: Insufficient detail (only 1 sentence)

### Re-Run Recommendation
**Strategy:** [None / Selective / Full]
**Target Subagents:** [List if selective]
**Priority Focus:** [What to emphasize in re-run]

### Enhanced Instructions for Re-Run
```
[Specific guidance to improve output quality]
```

### Validation Metadata
- **Validation Duration:** [N] seconds
- **Sources Checked:** [N]
- **Claims Verified:** [N] passed, [N] failed, [N] unverified
- **Citations Validated:** [N] valid, [N] invalid, [N] unchecked
```

---

## 8. Configuration Options

### 8.1 Validator Configuration

```yaml
swarm_validator:
  # Scoring thresholds
  thresholds:
    excellent: 90
    good: 80
    fair: 70
    poor: 60

  # Dimension weights (must sum to 1.0)
  weights:
    factual_accuracy: 0.25
    completeness: 0.20
    consistency: 0.20
    hallucination_risk: 0.20
    actionability: 0.10
    presentation: 0.05

  # Validation behavior
  behavior:
    auto_rerun_on_hallucination: true
    max_rerun_attempts: 2
    require_citations_for_facts: true
    check_urls: true
    cross_reference_claims: true

  # Fact-checking settings
  fact_check:
    search_engine: "brave"  # or google, duckduckgo
    max_sources_per_claim: 3
    source_trust_threshold: 0.7
    cache_verification_results: true
```

### 8.2 Per-Swarm Overrides

```python
# Example: Relax validation for exploratory tasks
validation_config = {
    "weights": {
        "actionability": 0.20,  # Increase for brainstorming
        "factual_accuracy": 0.15  # Decrease for speculative work
    },
    "behavior": {
        "require_citations_for_facts": False,  # Allow hypotheses
        "auto_rerun_on_hallucination": False  # Manual review instead
    }
}
```

---

## 9. Example Interactions

### 9.1 Example 1: Code Review Swarm

**Input:**
- Original: "Review authentication module for security issues"
- Swarm outputs from: security-auditor, performance-reviewer, architect

**Validation Output:**
```markdown
## Validation Report

**Overall Score:** 78/100 (FAIR)
**Recommendation:** Approve with Notes

### Critical Issues
1. **[HIGH]** Security auditor cited CVE-2023-12345 but this CVE doesn't exist
   - Evidence: "CVE-2023-12345 in the JWT library"
   - Fix: Verify CVE numbers against NVD database

### Missing Coverage
- Rate limiting: Not addressed by any subagent
- Session fixation: Mentioned but no remediation provided

### Re-Run Strategy
Selective re-run of security-auditor with fact-checking emphasis.
```

### 9.2 Example 2: Architecture Design Swarm

**Input:**
- Original: "Design microservices architecture for e-commerce platform"
- Swarm outputs from: backend-architect, database-architect, devops-specialist

**Validation Output:**
```markdown
## Validation Report

**Overall Score:** 92/100 (EXCELLENT)
**Recommendation:** Approve

### Strengths
- Comprehensive coverage of all requirements
- All cited patterns have verifiable sources
- Consistent recommendations across subagents
- Clear actionability with implementation steps

### Minor Suggestions
- Add latency estimates for inter-service calls
- Consider mentioning circuit breaker pattern

### No Re-Run Required
Output meets quality thresholds for production use.
```

### 9.3 Example 3: Research Swarm (Failed)

**Input:**
- Original: "Research emerging AI safety frameworks"
- Swarm outputs from: researcher, analyst

**Validation Output:**
```markdown
## Validation Report

**Overall Score:** 52/100 (UNACCEPTABLE)
**Recommendation:** Mandate Re-run

### Critical Issues
1. **[CRITICAL]** Multiple fabricated citations
   - "AI Safety Institute (2024)" - organization doesn't exist
   - "Zhang et al. (2023)" - paper not found in any database

2. **[HIGH]** Contradictory claims between researcher and analyst
   - Researcher: "RLHF is the dominant approach"
   - Analyst: "Constitutional AI has overtaken RLHF"
   - No reconciliation or evidence provided

3. **[HIGH]** Missing 40% of requested framework categories

### Re-Run Strategy
Full re-run with enhanced instructions:
- All citations must include URLs or DOIs
- Contradictions must be resolved with evidence
- Cover all framework categories in prompt
- Use WebSearch to verify organizations exist
```

---

## 10. Implementation Roadmap

### Phase 1: Core Validator (MVP)
- [ ] Implement basic validation logic
- [ ] Add hallucination detection heuristics
- [ ] Create scoring framework
- [ ] Build structured output format
- [ ] Integrate with horde-swarm skill

### Phase 2: Enhanced Detection
- [ ] Add WebSearch fact-checking
- [ ] Implement citation verification
- [ ] Add consistency analysis
- [ ] Build source trust scoring

### Phase 3: Operational Integration
- [ ] Neo4j storage for validation results
- [ ] Historical validation analytics
- [ ] Pattern learning from past validations
- [ ] Automatic re-run orchestration

### Phase 4: Advanced Features
- [ ] Domain-specific validators (code, research, design)
- [ ] Multi-modal validation (images, data)
- [ ] Real-time validation during swarm execution
- [ ] Validation result feedback loop to subagents

---

## 11. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Hallucination Detection Rate | >90% | True positives / (true positives + false negatives) |
| False Positive Rate | <10% | False positives / total validations |
| Average Validation Time | <30s | Time from input to report |
| Re-run Improvement | >15 points | Average score improvement after re-run |
| User Satisfaction | >4.0/5 | Post-validation user ratings |
| Coverage Detection | >80% | Successfully identified gaps / actual gaps |

---

## 12. Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Validator hallucinates about hallucinations | Confidence thresholds, multi-source verification |
| Excessive re-runs (loop) | Max attempts limit, human override option |
| False positives causing unnecessary work | Configurable strictness, learning from overrides |
| Validation bottleneck | Parallel validation, caching results |
| Source reliability issues | Source reputation scoring, multiple verification |

---

## 13. Conclusion

The `swarm-validator` agent fills a critical gap in the horde-swarm ecosystem by providing automated quality assurance. By detecting hallucinations, verifying facts, checking completeness, and triggering targeted re-runs, it significantly improves the reliability and trustworthiness of swarm outputs while maintaining the efficiency benefits of parallel subagent execution.

The proposed agent follows established naming conventions, integrates cleanly with existing patterns (Task dependencies, Operational Memory), and provides configurable validation suitable for different use cases from exploratory research to production code review.
