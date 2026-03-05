# Parse for Agents MVP - Task Tracking

**Created:** 2026-03-05 01:19 EST
**Status:** IN_PROGRESS
**Owner:** temujin (delegated by Kublai)
**Priority:** HIGH

---

## Objective

Build Vision A of "Parse for Agents" - a prompt testing sandbox API with a frontend for testing.

**Deliverable:** URL to a working frontend for testing

---

## Scope (MVP - Phase 1)

Based on SPEC-parse-for-agents.md:

### Core API Endpoints
- [ ] `POST /v1/evaluate` - Submit evaluation job
- [ ] `GET /v1/evaluate/{id}` - Poll for results
- [ ] `GET /v1/models` - List supported models
- [ ] `GET /v1/evaluators` - List available evaluators

### Core Components
- [ ] Hono API server (or Next.js API routes)
- [ ] API key authentication (reuse existing system)
- [ ] Zod request/response validation
- [ ] BullMQ job queue for evaluation jobs
- [ ] LLM provider integration (OpenAI + Anthropic + DeepSeek)
- [ ] Evaluators:
  - [ ] `cost` - Token counting, pricing
  - [ ] `latency` - Timing instrumentation
  - [ ] `quality` - Basic LLM-as-judge
  - [ ] `safety` - Content safety checks

### Frontend (for testing)
- [ ] Simple web UI to test the API
- [ ] Input: prompt template, test cases, model selection
- [ ] Output: evaluation results with scores

### Deployment
- [ ] Deploy to Railway (separate service or same project)
- [ ] Provide URL for testing

---

## Technical Decisions

1. **Framework:** Can extend existing Next.js app at `/Users/kublai/projects/parse-github` or create new service
2. **Database:** PostgreSQL with Prisma (add new models to existing schema)
3. **Queue:** BullMQ (already in use)
4. **Auth:** Reuse existing API key system

---

## Files to Reference

- `/Users/kublai/projects/parse-github/SPEC-parse-for-agents.md` - Full API spec
- `/Users/kublai/projects/parse-github/PARSE_FOR_AGENTS.md` - Implementation plan
- `/Users/kublai/projects/parse-github/ARCHITECTURE.md` - Existing architecture
- `/Users/kublai/projects/parse-github/src/app/api/v1/agents/[agent]/route.ts` - Existing agents API

---

## Progress Log

| Time | Update |
|------|--------|
| 01:19 | Task created and delegated to temujin |
| 01:25 | Re-routed to ACP session (agent:claude:acp:beb8982d-be08-4da3-9921-3a9a2ad6743a) - building MVP |

## ACP Session
- **Session Key:** agent:claude:acp:beb8982d-be08-4da3-9921-3a9a2ad6743a
- **Run ID:** 0a9dbf99-6ce1-44e2-8a81-d7a2c93201d7
- **Status:** Running

---

## Success Criteria

1. API responds to `/v1/evaluate` POST requests
2. Can submit prompt + test cases and get evaluation results
3. Frontend accessible via URL
4. At least `quality`, `cost`, `latency` evaluators working
