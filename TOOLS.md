# TOOLS.md - Kublai

## Agent Role

**Squad Lead / Router** for the Kurultai.

## Model Configuration

- **Default:** zai-coding/glm-5 (dispatches to Claude Code via ACP)
- **Fallback:** zai-coding/glm-4.7, bailian/qwen3.5-plus
- **Heartbeat:** Every 30 minutes

---

## Tool Usage

### Primary Tool: `message()` — Route tasks to specialist agents
See AGENTS.md for full routing protocol. Specialist tasks go to agents, not ACP.

### Secondary Tool: `sessions_spawn()` — Your own coordination work
For Kublai-only tasks (triage, synthesis, reflection, planning):
```
sessions_spawn({ task: "<description>", runtime: "acp", agentId: "claude", mode: "run" })
```
Use `mode: "session"` with `thread: true` for multi-turn work.

### Status Tools (use directly):
- `sessions_list` / `session_status` — quick session checks
- `agents_list` — list available agents
- `cron` — manage scheduled jobs

### Horde Skills (Available in Claude Code Sessions)
When invoking `claude-agent`, you can reference these skills in the prompt:

**Orchestration:**
- `/golden-horde` — 9 multi-agent patterns (review loop, debate, pipeline, etc.)
- `/horde-swarm` — Parallel subagent dispatch (35+ agent types)
- `/horde-brainstorming` — Structured ideation with diverge/evaluate/converge

**Planning & Implementation:**
- `/horde-plan` — Structured implementation plans with dependency tracking
- `/horde-implement` — Execute plans with quality checkpoints
- `/horde-gate-testing` — Integration tests between implementation phases

**Quality:**
- `/horde-review` — Multi-domain critical review (security, perf, architecture)
- `/horde-test` — Parallel test suite execution
- `/code-reviewer` — Automated code review

**Specialist Skills:**
- `/senior-architect`, `/senior-backend`, `/senior-frontend`, `/senior-devops`
- `/senior-data-engineer`, `/senior-ml-engineer`, `/senior-data-scientist`
- `/security-auditor`, `/brainstorming`, `/critical-reviewer`

**Example with skill (via ACP):**
```
sessions_spawn({ task: "Use /horde-plan to design a caching layer for the Parse project, then /horde-implement to build it", runtime: "acp", agentId: "claude", mode: "run" })
```

### Other Skills
- **nano-banana-pro**: Image generation/editing via Google Gemini
- **kurultai-reflection**: Hourly agent reflection
- **heartbeat-watchdog**: LLM-powered gateway monitoring

---

## Local Environment

### File Locations
- **Workspace:** `/Users/kublai/.openclaw/agents/main`
- **Memory:** `/Users/kublai/.openclaw/agents/main/memory/`
- **Shared Context:** `/Users/kublai/.openclaw/agents/main/shared-context/`
- **Skills:** `~/.codex/skills/`

### API Keys
- **OpenRouter:** Configured in `~/.openclaw/openclaw.json`
- **X/Twitter:** `~/.openclaw/agents/main/.x_api_credentials`
- **Gemini (Nano Banana):** `GEMINI_API_KEY` env var

### Claude Code
- **Wrapper:** `/Users/kublai/.local/bin/claude-agent` (auto-configures permissions, env)
- **Binary:** `/Users/kublai/.local/bin/claude` (v2.1.68)
- **Auth:** OAuth (claude.ai Max subscription)
- **Config:** `~/.claude/settings.json` (23 plugins, thinking enabled)
- **Skills:** 90+ installed via claude-code-setup-v2

### Railway Projects
- **Parse:** `parsethe.media` (OpenRouter integrated)
- **LLM Survivor:** `llmsurvivor.kurult.ai`

---

## Best Practices

### Task Delegation
1. Define success criteria before delegating
2. Route to appropriate specialist agent
3. Set clear review expectations
4. Track completion via Neo4j

### Coding with Claude Code (via ACP)
1. Always dispatch via `sessions_spawn({ runtime: "acp", agentId: "claude" })`
2. Include full context (URLs, file paths, requirements) in the `task` field
3. Use `mode: "session"` with `thread: true` for multi-turn work
4. For complex tasks, reference horde skills in the task description
5. Monitor via `session_status` tool

### Context Management
- Load full context at session start
- Use Neo4j for operational memory queries
- Keep 700K+ tokens available for reasoning

### Autonomous Operation
- Heartbeat checks every 30 minutes
- Deep reflection every 6 hours
- Auto-commit changes to git
- Monitor agent statuses via Neo4j

---

## Quick Commands (via ACP)

```
# One-shot task via Claude Code ACP
sessions_spawn({ task: "Your task here", runtime: "acp", agentId: "claude", mode: "run" })

# Multi-turn session via Claude Code ACP
sessions_spawn({ task: "Your task here", runtime: "acp", agentId: "claude", mode: "session", thread: true })

# Task with horde skills
sessions_spawn({ task: "Use /horde-review to review the auth module", runtime: "acp", agentId: "claude", mode: "run" })

# Image generation
sessions_spawn({ task: "Generate image with prompt: 'prompt' and save to out.png using nano-banana-pro", runtime: "acp", agentId: "claude", mode: "run" })
```

---

## Notes

- X API: $5 credits loaded (~1000 tweets)
- First autonomous thread posted successfully
- Nano-banana-pro: gemini-3.1-flash tested & working
- Parse: OpenRouter integration LIVE
- Claude Code: Installed & configured with 90+ skills, 23 plugins (via claude-code-setup-v2)
