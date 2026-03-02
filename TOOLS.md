# TOOLS.md - Kublai (Main Agent)

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

### Specialized Skills
- **nano-banana-pro**: Image generation/editing via Google Gemini
  ```bash
  python3 ~/.codex/skills/nano-banana-pro/nanobanana.py \
    --prompt "your prompt" \
    --output "output.png" \
    --model "gemini-3.1-flash-image-preview" \
    --size 1024x1024
  ```
  - Models: gemini-3-pro-image-preview, gemini-2.5-flash-image, gemini-3.1-flash-image-preview
  - Resolutions: 1K (default), 2K, 4K
  - Aspect ratios: 1:1, 9:16, 16:9, etc.

### Horde Skills (Multi-Agent Orchestration)
- `/golden-horde`: 9 multi-agent patterns (Review Loop, Adversarial Debate, Assembly Line, etc.)
- `/horde-plan`: Structured implementation plans
- `/horde-implement`: Execute plans with checkpoints
- `/horde-swarm`: Parallel subagent dispatch (35+ agent types)
- `/horde-prompt`: Optimized prompts for horde agents
- `/horde-review`: Multi-domain critical review
- `/horde-test`: Parallel test suite execution
- `/horde-brainstorming`: 6-phase collaborative design
- `/horde-skill-creator`: Create new skills (7-phase workflow)

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

### Context Management
- Load full context at session start (SOUL, AGENTS, ARCHITECTURE, etc.)
- Use Neo4j for operational memory queries
- Keep 700K+ tokens available for reasoning

### Autonomous Operation
- Heartbeat checks every 30 minutes
- Deep reflection every 6 hours (hours 0, 6, 12, 18)
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

# Generate image
python3 ~/.codex/skills/nano-banana-pro/nanobanana.py --prompt "prompt" --output "out.png"

# Post to X (autonomous)
cd ~/.openclaw/agents/main/src/autonomous_x_posting && python3 scheduler.py
```

---

## Resilience

### Fallback Models
1. qwen3.5-plus (primary)
2. MiniMax-M2.5 (fallback)
3. qwen3-coder-plus (coding tasks)

### Error Handling
- Retry failed API calls with exponential backoff
- Log errors to Neo4j for tracking
- Escalate critical failures to human via Signal

### Backup Locations
- **GitHub:** https://github.com/Danservfinn/kurultai
- **Local:** `/Users/kublai/.openclaw/agents/main`
- **Neo4j:** `bolt://localhost:7687`

---

## Notes

- X API: $5 credits loaded (~1000 tweets)
- First autonomous thread posted successfully (4/4 tweets)
- Nano-banana-pro: gemini-3.1-flash-image-preview tested & working
- Parse: OpenRouter integration LIVE
