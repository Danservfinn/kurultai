# TOOLS.md - Kublai

## Agent Role

**Squad Lead / Router** for the Kurultai.

## Tool Usage

### Primary Tool: `message()` — Route tasks to specialist agents
Follow the `kurultai-router` skill (`~/.openclaw/skills/kurultai-router/SKILL.md`) for all routing decisions. Specialist tasks go to agents via message(), not ACP.

### Secondary Tool: `sessions_spawn()` — Your own coordination work
For Kublai-only tasks (triage, synthesis, reflection, planning):
```
sessions_spawn({ task: "<description>", runtime: "acp", agentId: "claude", mode: "run" })
```
Use `mode: "session"` with `thread: true` for multi-turn work.

### Status Tools (use directly):
- `sessions_list` — list sessions
- `sessions_history` — fetch session transcript
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

**Example with skill (via claude-agent):**
```
# Task is routed to agent via task_intake.py
# Agent executes via claude-agent subprocess with skill hint
skill_hint: /horde-plan
# In agent-task-handler.py, the skill is invoked in the prompt
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

### Task Execution Architecture (IMPORTANT)

**Specialist agents do NOT use ACP sessions.** Tasks are executed via direct subprocess:

```
task-watcher.py (15s poll)
    └── detects .md task files in agent/tasks/
    └── calls agent-task-handler.py via subprocess
            └── calls claude-agent --workdir ~/.openclaw/agents/{agent}/
                    └── Runs Claude Code CLI in agent workspace
```

**Why subprocess, not ACP:**
- Agent sovereignty — independent workspaces, configs, and execution contexts
- Scale efficiency — no session registry pollution from high-frequency task execution
- Recovery semantics — PID-based tracking matches subprocess model
- Heartbeat integration — tick/tock filesystem scans are direct and reliable

**When to use ACP sessions:**
- One-off tasks spawned from human chat messages
- Cross-agent collaboration requiring OpenClaw session routing
- Model switching mid-task (OpenClaw can route to different models)
- Short-lived subagent work (not persistent agent execution)

### Context Management
- Do NOT read workspace files to answer human questions — route instead
- Use Neo4j for operational memory queries

### Autonomous Operation
- Route human messages immediately via the AGENTS.md gate
- Heartbeat checks every 30 minutes
- Deep reflection every 6 hours
- Monitor agent statuses via Neo4j

---

## Quick Commands

```
# Route task to specialist agent (creates task file)
python3 scripts/task_intake.py --title 'Task title' --body 'Task description' --agent temujin --priority high

# Check executing tasks
ls ~/.openclaw/agents/*/tasks/*.executing.md

# Check claude-agent processes
ps -ef | grep claude-agent | grep -v grep

# One-shot coordination task via ACP (Kublai-only work)
sessions_spawn({ task: "Your task here", runtime: "acp", agentId: "claude", mode: "run" })

# Multi-turn session via ACP (Kublai-only work)
sessions_spawn({ task: "Your task here", runtime: "acp", agentId: "claude", mode: "session", thread: true })
```

---

## Notes

- X API: $5 credits loaded (~1000 tweets)
- First autonomous thread posted successfully
- Nano-banana-pro: gemini-3.1-flash tested & working
- Parse: OpenRouter integration LIVE
- Claude Code: Installed & configured with 90+ skills, 23 plugins (via claude-code-setup-v2)
- **Architecture:** Specialist agents execute via claude-agent subprocess, NOT ACP sessions
