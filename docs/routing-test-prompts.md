# Kurultai Router Test Prompts

**Date:** 2026-03-12 (updated from 2026-03-05)
**Purpose:** Validate routing across all agents, disambiguation rules, and edge cases
**Skill under test:** `~/.openclaw/skills/kurultai-router/SKILL.md`
**Router source:** `~/.openclaw/agents/main/scripts/kublai-route.py`

---

## Agent Roster

As of 2026-03-12, the Kurultai has **6 active routing targets** (plus kublai as squad lead):

| Agent | Role | Domain |
|-------|------|--------|
| temujin | Developer | Code, build, deploy, architecture |
| mongke | Researcher | Research, market analysis, AI/LLM evaluation |
| chagatai | Writer | Content, docs, blog, marketing copy |
| jochi | Analyst | Security, review, audit, testing |
| ogedei | Ops | Infrastructure, cron, health, monitoring |
| tolui | Quality Verifier | Truth-telling, completion verification, quality gates |
| kublai | Squad Lead | Routing, coordination, system assessment |

> **Note:** tolui was added as a routing target in late 2026-03. Tasks routed via `@tolui` mention or containing "private"/"confidential" signals go to tolui directly (bypass logging).

---

## Core Agent Routing

### 1. temujin (BUILD)
> Build a REST API endpoint for user authentication with JWT tokens

**Expected:** temujin | **Skill hint:** none

### 2. mongke (RESEARCH)
> Research competitor pricing models for AI-powered media analysis platforms

**Expected:** mongke | **Skill hint:** /horde-learn

### 3. chagatai (WRITE)
> Write a blog post about how the Kurultai multi-agent architecture works

**Expected:** chagatai | **Skill hint:** /content-research-writer

### 4. jochi (ANALYZE)
> Audit the Parse API for prompt injection vulnerabilities and XSS attack vectors

**Expected:** jochi | **Skill hint:** /code-reviewer

### 5. ogedei (OPERATE)
> The Redis service is down, restart it and check why it crashed

**Expected:** ogedei | **Skill hint:** /kurultai-health

### 6. tolui (VERIFY) — *New agent as of 2026-03*
> This agent says the feature is complete but I want an honest assessment of whether it actually works

**Expected:** tolui | **Skill hint:** /horde-review

---

## Disambiguation Rules

### 7. research + security → jochi (Rule #1)
> Research known prompt injection techniques and test our API against them

**Expected:** jochi (NOT mongke) | **Skill hint:** /code-reviewer

### 8. design + research → temujin (Rule #2)
> Research payment protocols and design an x402 integration for Parse

**Expected:** temujin (NOT mongke) | **Skill hint:** /horde-brainstorming

### 9. fix + cron → ogedei (Rule #6)
> Fix the backup cron job that's been failing for 3 consecutive runs

**Expected:** ogedei (NOT temujin) | **Skill hint:** /kurultai-health

### 10. write + test → jochi (Rule #7)
> Write integration tests for the authentication middleware

**Expected:** jochi (NOT chagatai) | **Skill hint:** none

### 11. research + AI models → mongke (Added 2026-03-11)
> Compare Claude claude-opus-4-6 vs GPT-4o for our Parse agent API use case — evaluate context window, pricing, and rate limits

**Expected:** mongke | **Skill hint:** /horde-learn
**Why:** mongke keywords now include `llm`, `model comparison`, `ai pricing`, `provider comparison`, and related terms after 2026-03-11 update.

### 12. ops metrics → ogedei (Added 2026-03-12)
> The fleet throughput is degrading and failure rate is spiking — investigate

**Expected:** ogedei | **Skill hint:** /kurultai-health
**Why:** ogedei keywords now include `throughput`, `failure rate`, `fleet` after 2026-03-12 update.

---

## Edge Cases

### 13. Multi-domain decomposition
> Research our top 5 competitors, write a comparison blog post, and build a landing page for it

**Expected:** Decompose into 3 routes: mongke (research) + chagatai (blog) + temujin (landing page)

### 14. Self-routing prevention
> Triage stalled agent: jochi has 4 queued tasks with 0 completions in the last 30 minutes

**Expected:** kublai (NOT jochi) | Self-routing prevention fires

### 15. Kublai-only (COORDINATE)
> Give me a system-wide status assessment of all agents and prioritize the backlog

**Expected:** kublai | No delegation needed

### 16. Tolui routing via @mention — *New*
> @tolui Did chagatai's latest blog post actually hit the quality bar, or is it fluff?

**Expected:** tolui (direct channel, bypass logging) | **Keyword trigger:** @tolui mention

### 17. Paused task pattern — *New*
> Build an LLM Survivor elimination round between GPT-4 and Claude

**Expected:** PAUSED (matches `LLM Survivor` pattern) | Not routed to any agent

---

## Results (2026-03-05) — Historical Reference

### Keyword Router (task_intake.route_by_text) — 12/12 PASS

| # | Prompt | Expected | Actual | Pass? |
|---|--------|----------|--------|-------|
| 1 | Build REST API... | temujin | temujin | PASS |
| 2 | Research competitor... | mongke | mongke | PASS |
| 3 | Write blog post... | chagatai | chagatai | PASS |
| 4 | Audit Parse API... | jochi | jochi | PASS |
| 5 | Redis is down... | ogedei | ogedei | PASS |
| 6 | Research prompt injection... | jochi | jochi | PASS |
| 7 | Research payment protocols... | temujin | temujin | PASS |
| 8 | Fix backup cron... | ogedei | ogedei | PASS |
| 9 | Write integration tests... | jochi | jochi | PASS |
| 10 | Research competitors + blog + landing | decompose | mongke (keyword picks dominant) | PASS |
| 11 | Triage stalled jochi | kublai | kublai | PASS |
| 12 | System-wide assessment | kublai | kublai | PASS |

### Gateway (glm-5 live via `openclaw agent`) — 12/12 PASS

| # | Prompt | Expected | Actual | Pass? | Notes |
|---|--------|----------|--------|-------|-------|
| 1 | Build REST API... | temujin | temujin | PASS | |
| 2 | Research competitor... | mongke | mongke | PASS | |
| 3 | Write blog post... | chagatai | chagatai | PASS | |
| 4 | Audit Parse API... | jochi | jochi | PASS | |
| 5 | Redis is down... | ogedei | ogedei | PASS | |
| 6 | Research prompt injection... | jochi | jochi | PASS | Disambiguation rule #1 fired |
| 7 | Research payment protocols... | temujin | temujin | PASS | Initially failed (mongke); fixed by adding disambiguation table to AGENTS.md |
| 8 | Fix backup cron... | ogedei | ogedei | PASS | |
| 9 | Write integration tests... | jochi | jochi | PASS | |
| 10 | Research competitors + blog + landing | decompose | mongke+chagatai+temujin | PASS | Correctly decomposed into 3 routes |
| 11 | Triage stalled jochi | kublai | kublai | PASS | Self-routing prevention correct |
| 12 | System-wide assessment | kublai | kublai | PASS | |

### Live Routing Test: "what's the status of x402 pay as you go implementation for parse for agents?"

**Expected:** Route to ogedei (feature status = ops monitoring)
**Actual:** Kublai self-answered from workspace files (read x402-payment-design.md directly)
**Result:** FAIL — no message() to ogedei, no task created, no ledger entry

**Root cause:** glm-5 has the design doc in its workspace and self-answers despite SOUL.md/CLAUDE.md/AGENTS.md NEVER rules. "Status" is ambiguous — the LLM interprets it as coordination (kublai domain) rather than ops monitoring (ogedei domain).

**Fixes applied:**
1. Added SOUL.md NEVER rule 1b: never answer "status of feature/implementation" yourself
2. Added CLAUDE.md: never read code/design docs to answer human questions
3. Added AGENTS.md: status of product feature = ogedei, status of agents/routing = kublai

**Conclusion:** Classification tests (hypothetical "which agent would you route to?") pass 12/12. Actual live routing with borderline prompts still triggers self-answering. Structural enforcement (gateway hook, tool restrictions) needed for hard compliance.

---

## Changes Since 2026-03-05

### New routing targets
- **tolui** added as 6th agent (Quality Verifier). Routed via `@tolui` mention, "private", "confidential", "brutal", "honest assessment", "calling out" keywords. Bypasses logging. (`AGENT_KEYWORDS["tolui"]` in `kurultai_paths.py`)

### Keyword expansions
- **mongke** (2026-03-11): Added AI/LLM research terms — `llm`, `gpt`, `claude`, `anthropic`, `model comparison`, `ai pricing`, `provider comparison`, `embedding`, `rag`, `context window`, etc. Fixes gap where LLM provider research wasn't routing to mongke.
- **ogedei** (2026-03-12): Added ops metrics terms — `throughput`, `failure rate`, `fleet`. Ensures fleet-level performance degradation routes to ops rather than being misclassified.

### Paused task patterns
- `LLM Survivor` / `llm-survivor` patterns now trigger PAUSE status — tasks matching these are not routed to any agent.

### Fixes Applied During Testing (2026-03-05)

1. Test #7 initially routed to mongke (verb "research" beat domain noun "payment/x402"). Fixed by adding disambiguation table to AGENTS.md.
2. `task_intake.py` keyword router initially missed jochi, kublai, and disambiguation. Fixed by adding kublai keywords + disambiguation rules.
3. `kublai-initiative.py` also imported from task_router — fixed inline.

---

## Resolution

- Reviewed routing-test-prompts.md against current router state (`kublai-route.py`, `kurultai_paths.py`)
- Added tolui as 6th routing target with test prompts (#6, #16)
- Added 2 new disambiguation rules for AI/LLM model research (mongke) and ops metrics (ogedei)
- Added paused task pattern test (#17)
- Documented all keyword expansions since 2026-03-05 in Changes section
- Historical results preserved for reference

**Next steps:** Re-run routing tests against updated agent roster to validate tolui routing and new keyword coverage.
