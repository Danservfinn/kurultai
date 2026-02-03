# Multi-Agent Orchestrator Implementation Plan

## Executive Summary

Transform the current single-agent Kublai setup into a multi-agent orchestrator system with 6 specialized agents. Uses OpenClaw v2026.2.1's native multi-agent capabilities with per-agent model configuration. Kublai acts as the central router, delegating tasks to specialist agents via @mentions rather than broadcasting to all agents.

## Agent Configuration Matrix

| Agent ID | Name | Role | Model |
|----------|------|------|-------|
| `main` | Kublai | Squad Lead / Orchestrator | `moonshot/kimi-k2.5` |
| `researcher` | Mongke | Researcher | `zai/glm-4.5` |
| `writer` | Chagatai | **Writer** | `moonshot/kimi-k2.5` |
| `developer` | Temujin | Developer | `zai/glm-4.7` |
| `analyst` | Jochi | Analyst | `zai/glm-4.5` |
| `ops` | Ogedei | **Operations Manager** | `zai/glm-4.5` |

**CRITICAL**: Chagatai is WRITER, Ogedei is OPERATIONS (commonly confused)

## Implementation Steps

### Step 1: Update `moltbot.json` with Multi-Agent Configuration

**File**: `/tmp/moltbot-railway-template/moltbot.json`

Add the following sections:

1. **`agents.list`** - Define each agent with per-agent model and dedicated `agentDir`
2. **Channel routing** - Kublai receives all messages and delegates to specialists

Key configuration additions:

```json
{
  "agents": {
    "defaults": {
      "workspace": "/data/workspace",
      "model": {
        "primary": "zai/glm-4.5"
      }
    },
    "list": [
      {
        "id": "main",
        "name": "Kublai",
        "default": true,
        "agentDir": "/data/.clawdbot/agents/main",
        "model": {
          "primary": "moonshot/kimi-k2.5"
        }
      },
      {
        "id": "researcher",
        "name": "Mongke",
        "agentDir": "/data/.clawdbot/agents/researcher",
        "model": {
          "primary": "zai/glm-4.5"
        }
      },
      {
        "id": "writer",
        "name": "Chagatai",
        "agentDir": "/data/.clawdbot/agents/writer",
        "model": {
          "primary": "moonshot/kimi-k2.5"
        }
      },
      {
        "id": "developer",
        "name": "Temujin",
        "agentDir": "/data/.clawdbot/agents/developer",
        "model": {
          "primary": "zai/glm-4.7"
        }
      },
      {
        "id": "analyst",
        "name": "Jochi",
        "agentDir": "/data/.clawdbot/agents/analyst",
        "model": {
          "primary": "zai/glm-4.5"
        }
      },
      {
        "id": "ops",
        "name": "Ogedei",
        "agentDir": "/data/.clawdbot/agents/ops",
        "model": {
          "primary": "zai/glm-4.5"
        }
      }
    ]
  },
  "channels": {
    "signal": {
      "dmPolicy": "pairing",
      "groupPolicy": "allowlist",
      "allowFrom": ["+15165643945"],
      "requireMention": false
    }
  }
}
```

**Note**: No `broadcast.groups` configured. Kublai receives all messages and delegates to specialists via @mentions based on the task type.

### Step 2: Configure Moonshot Provider

**File**: `/data/.clawdbot/openclaw.json` (via Control UI > Settings > OpenClaw)

Add the Moonshot provider configuration for Kublai and Chagatai to use Kimi K2.5:

```json5
{
  "models": {
    "providers": {
      "moonshot": {
        "api": "openai-completions",
        "apiKey": "${MOONSHOT_API_KEY}",
        "baseUrl": "https://api.moonshot.cn/v1",
        "models": [
          {
            "id": "kimi-k2.5",
            "name": "Kimi K2.5",
            "reasoning": false,
            "input": ["text"]
          }
        ]
      },
      "zai": {
        "api": "openai-completions",
        "apiKey": "${ZAI_API_KEY}",
        "baseUrl": "https://api.z.ai/v1",
        "models": [
          {
            "id": "glm-4.7",
            "name": "GLM 4.7"
          },
          {
            "id": "glm-4.5",
            "name": "GLM 4.5"
          }
        ]
      }
    }
  }
}
```

**Environment Variables Required:**
```
MOONSHOT_API_KEY=sk-...    # From https://platform.moonshot.cn/
ZAI_API_KEY=sk-...         # From https://www.z.ai/
```

### Step 3: Create Agent Directory Structure

Create both workspace and per-agent directories:

**Agent Directories** (for agent state/isolation):
```bash
mkdir -p /data/.clawdbot/agents/{main,researcher,writer,developer,analyst,ops}
```

**Workspace Structure** (shared across agents):
```
/data/workspace/
├── souls/              # Agent personality files
│   ├── kublai.md
│   ├── mongke.md
│   ├── ogedei.md
│   ├── temujin.md
│   ├── jochi.md
│   └── chagatai.md
├── memory/             # Per-agent working memory
│   ├── kublai/
│   ├── mongke/
│   ├── ogedei/
│   ├── temujin/
│   ├── jochi/
│   └── chagatai/
├── tasks/              # Task management system
│   ├── inbox/
│   ├── assigned/
│   ├── in-progress/
│   ├── review/
│   └── done/
└── deliverables/       # Completed work
    ├── research/
    ├── content/
    ├── security/
    └── analytics/
```

Create via Control UI file browser or terminal.

### Step 4: Create Agent SOUL Files

Reference: `/Users/kurultai/molt/plans/mission-control-multi-agent.md`

Each agent needs a personality file at `/data/workspace/souls/{agent}.md` defining:
- Role and responsibilities
- Behavior patterns
- Coordination protocol

**Kublai's Delegation Instructions** (in `kublai.md`):
```markdown
## Delegation Protocol

As Squad Lead, you coordinate the agent network. When receiving tasks:

1. **Assess the request** - Determine which specialist(s) should handle it
2. **Delegate via @mentions** - Use Signal to route to specific agents:
   - @mongke - Deep research tasks
   - @chagatai - Writing and content creation
   - @temujin - Development and coding
   - @jochi - Data analysis and metrics
   - @ogedei - Operations and scheduling
3. **Synthesize responses** - Combine specialist outputs into cohesive deliverables
4. **Escalate when needed** - Use glm-4.7 reasoning for complex orchestration

Do NOT broadcast to all agents. Route intentionally based on expertise.
```

### Step 5: Deploy and Verify

1. Commit and push updated `moltbot.json` to trigger Railway redeployment
2. Access Control UI at `https://kublai.kurult.ai/`
3. Configure Moonshot provider in Settings > OpenClaw
4. Verify all 6 agents appear in Settings > Agents
5. Create SOUL files via terminal or Control UI
6. Test Signal channel - Kublai should receive messages and delegate to specialists

## Critical Files

| File | Purpose |
|------|---------|
| `/tmp/moltbot-railway-template/moltbot.json` | Template config (add agents.list + broadcast.groups) |
| `/data/.clawdbot/moltbot.json` | Active config on Railway volume |
| `/Users/kurultai/molt/plans/mission-control-multi-agent.md` | Agent personality templates |

## Verification Checklist

- [ ] `moltbot.json` contains `agents.list` with 6 agents
- [ ] Kublai (main) configured with `moonshot/kimi-k2.5`
- [ ] Chagatai (writer) configured with `moonshot/kimi-k2.5`
- [ ] Temujin (developer) configured with `zai/glm-4.7`
- [ ] Mongke, Ogedei, Jochi configured with `zai/glm-4.5`
- [ ] Moonshot provider configured in `openclaw.json` with `kimi-k2.5` model
- [ ] Z.AI provider configured with `glm-4.7` and `glm-4.5` models
- [ ] Agent directories created at `/data/.clawdbot/agents/{id}`
- [ ] All 6 agents appear in Control UI Settings > Agents
- [ ] Signal message routes to Kublai, which delegates to appropriate specialist
- [ ] No broadcast group configured (Kublai delegates, not broadcasts)

## Rollback Plan

If issues occur:
1. Revert `moltbot.json` to single-agent configuration
2. Remove `agents.list` and `broadcast.groups` sections
3. Redeploy to Railway
