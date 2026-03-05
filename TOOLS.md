# TOOLS.md - Kublai

## Agent Role

**Squad Lead / Router** for the Kurultai.

## Model Configuration

- **Default:** qwen3.5-plus (1M context)
- **Fallback:** MiniMax-M2.5
- **Heartbeat:** Every 30 minutes

---

## Core Capabilities

### OpenClaw Tools
- `sessions_spawn`: Spawn subagents for parallel work
- `web_search`: Research via Kimi/Perplexity
- `web_fetch`: Fetch web content (markdown extraction)
- `exec`: Shell commands (with pty support)
- `read/write/edit`: File operations
- `browser`: Browser automation (Chrome)
- `process`: Manage background processes
- `message`: Signal/Telegram messaging

### Coding Agent (Claude Code)
For all coding tasks, use **`claude-agent`** — a wrapper that spawns Claude Code with all 90+ skills, 23 plugins, and proper non-interactive settings:

```bash
# Quick one-shot task (default: opus, $1.00 budget)
bash pty:true command:"claude-agent 'Your task here'"

# Specify model and budget
bash pty:true command:"claude-agent --model sonnet --budget 0.50 'Quick task'"

# With working directory
bash pty:true command:"claude-agent --workdir ~/project 'Build feature X'"

# Background task with monitoring
bash pty:true background:true command:"claude-agent --workdir ~/project 'Build feature X'"
```

**When to use coding-agent:**
- Building new features or apps
- Reviewing PRs
- Refactoring large codebases
- Iterative coding needing file exploration

**NOT for:**
- Simple one-liner fixes (use edit tool)
- Reading code (use read tool)
- Work in ~/clawd workspace

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

**Example with skill:**
```bash
bash pty:true command:"claude-agent --workdir ~/project 'Use /horde-plan to design a caching layer, then /horde-implement to build it'"
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

### Coding with Claude Code
1. Always use `claude-agent` wrapper (not bare `claude -p`)
2. Use `--workdir` for project-specific work
3. Use `background:true` for long tasks
4. For complex tasks, reference horde skills in the prompt
5. Monitor via `process` tool

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

## Quick Commands

```bash
# Check agent status
openclaw status

# List cron jobs
openclaw cron list

# Check Neo4j
python3 -c "from neo4j import GraphDatabase; d=GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j','neo4j')); print(d.verify_connectivity())"

# Claude Code one-shot
claude-agent "Your task here"

# Claude Code with horde skills
claude-agent "Use /horde-review to review the auth module"

# Generate image
python3 ~/.codex/skills/nano-banana-pro/nanobanana.py --prompt "prompt" --output "out.png"
```

---

## Notes

- X API: $5 credits loaded (~1000 tweets)
- First autonomous thread posted successfully
- Nano-banana-pro: gemini-3.1-flash tested & working
- Parse: OpenRouter integration LIVE
- Claude Code: Installed & configured with 90+ skills, 23 plugins (via claude-code-setup-v2)
