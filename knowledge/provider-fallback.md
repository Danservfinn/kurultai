# Provider Fallback Chain

This document describes how the Kurultai routes LLM requests through a primary/backup provider chain, controlled by the `claude-agent` wrapper script and the mode.json configuration.

## Architecture Overview

```
Human/System -> Task Queue (Neo4j)
                    |
                v2-executor picks task
                    |
                claude-agent wrapper
                    |
        +-----------|------------+-----------+-----------+
        |           |            |           |           |
    [primary]   [backup]    [fallback]  [gateway]   [local]
    Anthropic    Z.AI        Alibaba    OpenRouter   Ollama
    OAuth        glm-5       qwen3.5+   user model   qwen3.5-9b
```

---

## claude-agent Wrapper

**Location**: `~/.local/bin/claude-agent`
**Purpose**: Executes Claude Code with automatic provider fallback on retryable errors.

### Key Behavior

1. Reads settings paths from `~/.openclaw/kurultai.json` (execution.primary_settings, execution.backup_settings)
2. Reads mode from `~/.openclaw/claude/mode.json`
3. Unsets the `CLAUDECODE` environment variable to allow nested Claude Code sessions
4. Runs `claude -p --effort <level> --dangerously-skip-permissions --settings <file>` in print mode
5. Logs all session events to `~/.openclaw/logs/sessions/active.jsonl`

### Arguments

| Argument | Description |
|----------|-------------|
| `--effort <level>` | Effort level: low, medium, high (default: high) |
| `--workdir <path>` | Working directory for the agent |
| `--agent <name>` | Agent name (compat alias; auto-extracted from workdir if omitted) |
| `--model <model>` | Accepted but ignored (backward compatibility) |
| `--` | Separator before the prompt text |

### Execution Flow

```
1. Parse arguments, extract agent name
2. Read PRIMARY and BACKUP settings paths from kurultai.json
3. Read SETTINGS_MODE from mode.json
4. If mode == "backup":
     -> Run with backup settings only
     -> Exit
5. If mode == "auto" (default) or "primary":
     -> Run with primary settings
     -> If success -> exit 0
     -> If retryable error (rate limit, auth, 429, overloaded):
          -> Run with backup settings
          -> If success -> exit 0
          -> Both failed -> exit with error
     -> If non-retryable error -> exit with primary error
```

### Retryable Error Detection

The wrapper detects these patterns in stdout/stderr to trigger fallback:

- Exit code 429
- Text containing: "rate limit", "429", "capacity", "overloaded"
- Text containing: "not logged in", "please run /login", "authentication", "unauthorized", "401"

---

## Settings Files

### Primary Settings (`~/.openclaw/claude/settings.json`)

Used for Anthropic (OAuth authentication):

```json
{
  "env": {
    "ANTHROPIC_MODEL": "claude-opus-4-6"
  },
  "alwaysThinkingEnabled": true,
  "effortLevel": "high"
}
```

- No `ANTHROPIC_AUTH_TOKEN` -- relies on Claude Code's built-in OAuth flow
- Authenticate via: `claude auth login`

### Backup Settings (`~/.openclaw/claude/settings.backup.json`)

Used for Z.AI (glm-5) as fallback:

```json
{
  "env": {
    "ANTHROPIC_AUTH_TOKEN": "<zai_token>",
    "ANTHROPIC_BASE_URL": "https://api.z.ai/api/anthropic",
    "ANTHROPIC_MODEL": "glm-5",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "glm-5",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "glm-5",
    "API_TIMEOUT_MS": "3000000"
  }
}
```

---

## Mode Configuration

**File**: `~/.openclaw/claude/mode.json`

```json
{ "mode": "auto" }
```

| Mode | Behavior |
|------|----------|
| `auto` | Try primary first, fall back to backup on retryable errors (default) |
| `backup` | Skip primary entirely, use backup settings only |
| `primary` | Use primary only, no fallback |

### UI Control

Mode can be changed via:
- **API**: `POST /api/settings/mode` with body `{ "mode": "auto|backup|primary" }`
- **API**: `GET /api/settings/mode` to read current mode
- **Dashboard**: Settings tab has a mode switcher

---

## Credential Vault

**File**: `~/.openclaw/credentials/provider.env`
**Permissions**: 600 (owner read/write only)

### Structure

```
# Anthropic (Primary - OAuth Authentication)
# ANTHROPIC_AUTH_TOKEN= (intentionally empty - OAuth handles auth)

# Z.AI (Fallback Tier 1 - glm-5)
ZAI_AUTH_TOKEN=<token>
ZAI_BASE_URL=https://api.z.ai/api/anthropic

# Alibaba/DashScope (Fallback Tier 2 - qwen3.5-plus)
ALIBABA_AUTH_TOKEN=<token>
ALIBABA_BASE_URL=https://coding-intl.dashscope.aliyuncs.com/apps/anthropic

# OpenRouter (Multi-provider gateway)
OPENROUTER_API_KEY=<key>
OPENROUTER_MODEL=<model>
```

### Provider Tiers

| Tier | Provider | Model | Auth Method |
|------|----------|-------|-------------|
| Primary | Anthropic | claude-opus-4-6 | OAuth (managed by Claude Code) |
| Fallback 1 | Z.AI | glm-5 | Token-based |
| Fallback 2 | Alibaba/DashScope | qwen3.5-plus | Token-based |
| Gateway | OpenRouter | User-configured (e.g., x-ai/grok-4.20-multi-agent-beta) | API key |
| Fallback 3 | Ollama | lukey03/qwen3.5-9b-abliterated-vision | Local (no token) |

### Vault Management

- `agent-task-handler.py` calls `load_vault_credentials()` after sanitizing inherited env vars
- Dashboard Settings tab -> Providers: manage tokens (masked as `***last8` for OpenRouter, `***last4` for others)
- API: `GET/POST /api/providers` for programmatic access (tokens/keys auto-masked on read)

---

## Model Selection

The primary model can be changed via:
- **API**: `POST /api/settings/model` with `{ "model": "claude-opus-4-6" }`
- **Allowed models**: `claude-opus-4-6`, `claude-sonnet-4-6`, `claude-haiku-4-5-20251001`
- This updates `ANTHROPIC_MODEL` in `~/.openclaw/claude/settings.json`

Per-agent model overrides are managed through:
- `PUT /api/agents/:name/claude-config`
- `PUT /api/settings/models/agent/:agent`

---

## Session Logging

Every `claude-agent` invocation logs to `~/.openclaw/logs/sessions/active.jsonl`:

```json
{"ts":"2026-03-13T10:00:00+08:00","pid":12345,"agent":"temujin","settings":"primary","settings_file":"/path/to/settings.json","status":"started"}
{"ts":"2026-03-13T10:02:00+08:00","pid":12345,"agent":"temujin","settings":"primary","settings_file":"/path/to/settings.json","status":"success"}
```

Status values: `started`, `success`, `fallback`, `failed`

The active sessions API (`GET /api/sessions/active`) cross-references these logs with running processes and Neo4j WORKING tasks to build a live view.
