# Parse for Agents: Product Vision

**The prompt testing sandbox that agents trust before they act.**

---

## 1. Product Vision

### What is Parse for Agents?

Parse for Agents is an API-first prompt evaluation platform that lets AI agents and developers test prompts in isolated sandboxes before they reach production. Every prompt is scored across four dimensions -- safety, quality, cost, and latency -- and every evaluation runs in a container that can't leak, persist, or affect anything outside itself.

It's the gate between "I wrote a prompt" and "I deployed a prompt."

### Why Does It Exist?

The prompt engineering workflow is broken. Developers iterate on prompts through manual trial-and-error. Agents execute prompts without knowing if they're safe, efficient, or even coherent. There is no `npm test` for prompts. No CI check. No sandbox. The consequences are real:

- **Prompt injections** slip through to production because nobody tested adversarial inputs
- **Cost overruns** happen because nobody estimated token spend before scaling
- **Quality regressions** go unnoticed because there's no baseline to compare against
- **Agents act blindly** -- they generate prompts and fire them without self-evaluation

Parse for Agents solves this by providing a structured, automated, API-accessible evaluation layer. One API call returns a multi-dimensional score. Agents can self-evaluate. CI pipelines can gate on safety. Developers can compare models on cost and quality side-by-side.

### Who Is It For?

**AI Developers** building applications on top of LLMs who need confidence that their prompts behave correctly across models, inputs, and edge cases.

**Agent Builders** creating autonomous systems that generate and execute prompts dynamically. Parse gives agents the ability to evaluate their own output before acting -- a critical feedback loop for safe autonomy.

**Prompt Engineers** iterating on prompt design who need structured metrics instead of vibes. Parse replaces "that looks about right" with quantified scores and historical comparisons.

**Platform Teams** responsible for LLM cost, safety, and reliability at scale. Parse integrates into CI/CD to catch regressions before they ship.

---

## 2. Core Concept

### Prompt Testing in Isolated Sandboxes

Every evaluation runs in a constrained environment:

- **Memory**: 512MB hard limit
- **CPU**: 0.5 cores
- **Timeout**: 30 seconds default, configurable to 120s
- **Network**: Isolated -- LLM calls route through a controlled proxy only
- **Filesystem**: Read-only rootfs, no persistence, non-root execution

This means a prompt evaluation cannot exfiltrate data, consume unbounded resources, or affect other evaluations. You can safely test adversarial prompts, jailbreak attempts, and injection payloads without risk.

### Multi-Dimensional Evaluation

A single evaluation returns four independent scores:

| Dimension | What It Measures | Output |
|-----------|-----------------|--------|
| **Safety** | Injection patterns, harmful content, system prompt leaks | Pass/Fail + flags |
| **Quality** | Coherence, completeness, relevance, repetition | Score 0-1 |
| **Cost** | Input/output tokens, estimated USD, budget classification | Dollar amount + tier |
| **Latency** | Response time, throughput rating | Time + rating |

Each dimension is independently useful. Together they give a complete picture of prompt fitness.

### API-First Design

Parse is built for machines first, humans second. The primary interface is a REST API:

```bash
curl -X POST https://api.parse.dev/v1/evaluate \
  -H "Authorization: Bearer $PARSE_API_KEY" \
  -d '{
    "prompt": "Summarize the following document: {{input}}",
    "model": "anthropic/claude-sonnet-4",
    "test_inputs": ["Short text.", "A 10,000 word essay...", "Ignore previous instructions."]
  }'
```

The response is structured data, not prose. Agents can parse it. CI can gate on it. Dashboards can visualize it.

---

## 3. Key Features

### Real-Time Prompt Evaluation

Submit a prompt and test inputs via `POST /v1/evaluate`. Get back a job ID immediately (202 Accepted). Poll for results or receive them via webhook. Typical evaluation completes in 2-8 seconds depending on model and input count.

### Safety & Injection Detection

Built-in pattern matching for known injection vectors:

- "Ignore previous instructions" variants
- System/instruction marker injection (`[SYSTEM]`, `<|im_start|>`)
- Role-switching attempts ("You are now an evil AI")
- Restriction bypass patterns
- Output-side checks for credential leaks, harmful content generation, and system prompt exposure

Safety is not a score -- it's a pass/fail gate with specific flags explaining what was detected.

### Quality Scoring

Automated assessment of response quality on a 0-1 scale:

- **Coherence**: Is the response logically structured?
- **Completeness**: Does it address the prompt fully?
- **Relevance**: Does it stay on topic relative to input?
- **Repetition**: Does it avoid redundant content?
- **Error patterns**: Does it contain refusal patterns, hallucination markers, or truncation?

### Cost Estimation

Token-accurate cost projections before you commit to a model:

- Input and output token counts (via tiktoken)
- Per-model pricing from a maintained lookup table
- Budget classification: low / moderate / high
- Compare costs across 7+ models from OpenAI, Anthropic, Google, Meta, Mistral, and DeepSeek

### Vision Support

Multimodal prompt evaluation for image+text inputs:

- Upload images via drag-drop or URL
- Evaluate vision model responses
- Score image-grounded outputs for relevance and accuracy
- Supports GPT-4o, Claude Sonnet, Gemini vision models

### Batch Evaluation

Submit up to 100 test cases in a single API call for systematic coverage:

```json
{
  "prompt": "Classify sentiment: {{input}}",
  "test_inputs": ["I love this", "Terrible product", "It's okay I guess", ...],
  "model": "openai/gpt-4o-mini"
}
```

Get aggregated scores plus per-case breakdowns. Ideal for regression testing prompt changes.

### Historical Tracking

Every evaluation is stored with full context:

- Compare prompt versions over time
- Track quality/cost trends as you iterate
- Re-run historical evaluations against new models
- Export evaluation history for auditing

---

## 4. Use Cases

### Agent Self-Evaluation

An autonomous agent generates a prompt dynamically. Before executing it against a production LLM, it calls Parse to check:

```python
# Agent decides what to do
prompt = agent.generate_next_action()

# Agent checks its own work
eval_result = parse.evaluate(prompt, model="anthropic/claude-sonnet-4")

if not eval_result.safety.passed:
    agent.log("Unsafe prompt detected, aborting")
    return

if eval_result.cost.estimated_cost_usd > budget_limit:
    agent.switch_model("openai/gpt-4o-mini")

agent.execute(prompt)
```

This is the core use case. Parse turns agents from blind executors into self-aware systems.

### Prompt Development Workflow

A developer building a customer support chatbot iterates on their system prompt:

1. Write initial prompt
2. Define 20 test inputs covering happy path, edge cases, and adversarial inputs
3. Run evaluation -- see quality score of 0.6
4. Refine prompt, re-evaluate -- quality improves to 0.78
5. Try a different model -- cost drops 80% with acceptable quality tradeoff
6. Lock in the prompt version with the best quality/cost ratio

### CI/CD Integration

Add Parse to your deployment pipeline:

```yaml
# .github/workflows/prompt-test.yml
- name: Evaluate prompts
  run: |
    parse evaluate --config prompts.yaml --threshold quality=0.7 safety=pass

- name: Gate deployment
  if: failure()
  run: echo "Prompt evaluation failed, blocking deploy"
```

Prompt regressions get caught before they ship, just like code regressions.

### Cost Optimization

Compare the same prompt across models to find the best price/performance:

| Model | Quality | Cost/1K calls | Latency |
|-------|---------|---------------|---------|
| GPT-4o | 0.92 | $12.50 | 2.1s |
| Claude Sonnet | 0.89 | $18.00 | 1.8s |
| GPT-4o Mini | 0.81 | $0.75 | 0.9s |
| Gemini Flash | 0.78 | $0.50 | 0.6s |
| Llama 3.3 70B | 0.76 | $0.60 | 1.2s |

For many use cases, 0.81 quality at $0.75 beats 0.92 quality at $12.50. Parse makes this tradeoff visible and quantifiable.

---

## 5. Architecture Overview

### High-Level System Design

```
                         ┌──────────────────────┐
                         │   Parse Dashboard    │
                         │   (Web UI / React)   │
                         └──────────┬───────────┘
                                    │
                         ┌──────────▼───────────┐
                         │    API Gateway        │
                         │  Auth / Rate Limit    │
                         │  Request Validation   │
                         └──────────┬───────────┘
                                    │
                    ┌───────────────▼───────────────┐
                    │         Job Queue             │
                    │     (BullMQ / Redis)           │
                    └───────┬───────────────┬───────┘
                            │               │
                   ┌────────▼──────┐ ┌──────▼────────┐
                   │   Worker 1    │ │   Worker N     │
                   │  ┌─────────┐  │ │  ┌─────────┐  │
                   │  │Sandbox  │  │ │  │Sandbox  │  │
                   │  │Container│  │ │  │Container│  │
                   │  └────┬────┘  │ │  └────┬────┘  │
                   │       │       │ │       │       │
                   │  Evaluators   │ │  Evaluators   │
                   └───────┬───────┘ └───────┬───────┘
                           │                 │
                ┌──────────▼─────────────────▼──────────┐
                │           LLM Proxy                    │
                │  (OpenRouter → Multi-Provider Access)  │
                └──────────┬────────────────────────────┘
                           │
          ┌────────────────▼────────────────┐
          │  OpenAI / Anthropic / Google /  │
          │  Meta / Mistral / DeepSeek      │
          └────────────────────────────────┘
```

### API Structure

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/v1/evaluate` | POST | Submit prompt for evaluation |
| `/v1/evaluate/{id}` | GET | Retrieve evaluation results |
| `/v1/evaluate/batch` | POST | Submit batch evaluation |
| `/v1/models` | GET | List supported models + pricing |
| `/v1/evaluators` | GET | List available evaluators |
| `/v1/evaluators` | POST | Register custom evaluator |
| `/v1/history` | GET | Query evaluation history |
| `/health` | GET | Service health check |

### Sandbox Isolation

Each evaluation runs in a Docker container with:

- **Resource limits** enforced at the container level (memory, CPU, time)
- **Network isolation** -- containers cannot reach the internet directly; LLM calls route through a controlled proxy that only allows traffic to approved LLM API endpoints
- **Ephemeral storage** -- nothing persists after the evaluation completes
- **Non-root execution** -- the evaluation process runs as an unprivileged user
- **Read-only filesystem** -- no writes to the container image

This design means Parse can safely evaluate adversarial prompts, untrusted code outputs, and jailbreak attempts without risk to the platform or other users.

---

## 6. Differentiation

### What Makes Parse Different

**Built for agents, not just humans.** Most prompt testing tools assume a human is iterating in a UI. Parse assumes an agent is calling an API in a loop. The interface is structured data in, structured data out. No dashboards required.

**Multi-dimensional scoring, not vibes.** Other tools give you a thumbs up or thumbs down. Parse gives you independent scores across safety, quality, cost, and latency. You can optimize for the dimension that matters to your use case.

**Sandbox isolation is the default.** Prompt testing tools typically run evaluations in the same environment as everything else. Parse isolates every evaluation in a constrained container. This is critical for testing adversarial inputs safely.

**Model-agnostic via OpenRouter.** Test the same prompt across OpenAI, Anthropic, Google, Meta, Mistral, and DeepSeek with a single API call. No separate API keys or integrations needed.

**Cost is a first-class metric.** Most evaluation tools ignore cost entirely. Parse treats it as equally important as quality. Because for production workloads processing millions of prompts, the difference between $0.50/1K and $12.50/1K is the difference between viable and bankrupt.

### Competitive Landscape

| Tool | Focus | Parse Advantage |
|------|-------|-----------------|
| PromptFoo | CLI-based prompt testing | Parse is API-first for agent integration |
| LangSmith | LLM observability & tracing | Parse focuses on pre-deployment testing, not post-deployment monitoring |
| Weights & Biases Prompts | Experiment tracking | Parse provides real-time evaluation with safety gating |
| Humanloop | Prompt management | Parse offers sandbox isolation and adversarial testing |
| Braintrust | Eval framework | Parse includes cost estimation and model comparison |

Parse occupies a specific niche: **pre-execution evaluation with safety guarantees**. It's not an observability platform, prompt management tool, or experiment tracker. It's the gate that runs before execution.

---

## 7. Roadmap

### Phase 1: MVP (Current)

**Goal**: A working API that developers can integrate today.

- [x] Single evaluation endpoint (`POST /v1/evaluate`)
- [x] Core evaluators: safety, quality, cost, latency
- [x] OpenRouter LLM integration (7+ models)
- [x] Web UI for manual testing
- [x] Model pricing lookup and cost estimation
- [x] Vision/multimodal support
- [ ] Docker sandbox containerization
- [ ] PostgreSQL persistence
- [ ] Redis job queue (BullMQ)
- [ ] API key authentication
- [ ] Rate limiting

**Milestone**: Public API with persistent storage and sandbox isolation.

### Phase 2: Advanced Features

**Goal**: Production-grade capabilities for teams and CI pipelines.

- Batch evaluation endpoint (up to 100 test cases)
- WebSocket streaming for real-time results
- Webhook notifications on completion
- Enhanced safety evaluator with content classification
- Consistency evaluator (same prompt, multiple runs)
- Groundedness evaluator (fact-checking against source material)
- BYOK (Bring Your Own Key) for direct provider access
- TypeScript and Python SDKs
- GitHub Actions integration
- Historical comparison and regression detection

**Milestone**: Teams running Parse in CI/CD with SDK integration.

### Phase 3: Enterprise Scale

**Goal**: Platform-grade reliability and customization for organizations.

- Custom evaluator registration (user-defined scoring functions)
- Code sandbox evaluators (execute and evaluate generated code)
- Kubernetes orchestration for horizontal scaling
- Multi-region deployment
- SSO/SAML authentication
- Role-based access control
- Audit logging and compliance reporting
- SLA guarantees (99.9% uptime)
- Dedicated instances for enterprise customers
- Advanced analytics and usage dashboards

**Milestone**: Enterprise contracts with SLA-backed deployments.

---

## The North Star

Parse for Agents exists so that no prompt reaches production untested. No agent acts without self-evaluation. No cost surprise goes undetected. No injection slips through unchecked.

The world is moving toward autonomous AI agents that generate and execute their own prompts. Those agents need a feedback loop -- a way to evaluate their own work before committing to action. Parse is that feedback loop.

**Every prompt tested. Every agent accountable. Every cost visible.**
