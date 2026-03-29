# Provider Fallback Chain

This document describes how the Kurultai routes LLM requests through a primary/backup provider chain, controlled by the `claude-agent` wrapper script and the mode.json configuration.

## Architecture Overview

```
Human/System -> Task Queue (Neo4j)
                    |
                task-executor picks task
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

- `task_executor.py` calls `build_agent_env()` which strips inherited `ANTHROPIC_*` vars then loads vault credentials
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

---

## Model Drift Detection and Prevention

### What is Model Drift?

Model drift occurs when agents run with a different model than configured. This causes degraded task quality and unexpected behavior.

**Common Causes:**
1. **Corrupted settings.json** - ANTHROPIC_MODEL changed to fallback model
2. **Stuck in backup mode** - mode.json left in "backup" after credential expiry
3. **Manual intervention** - Settings modified without proper validation
4. **File synchronization issues** - Database and file system become out of sync
5. **Improper restoration** - Settings files improperly restored after backup

### Common Causes

| Cause | Description | Detection Method |
|-------|-------------|------------------|
| Manual file edits | Direct editing of `settings.json` bypasses validation | Dashboard health check, watchdog script |
| File corruption | Improper shutdown, disk errors, sync failures | JSON validation, file integrity checks |
| Backup mode masking | When in backup mode, primary drift goes unnoticed | Mode-aware validation, periodic primary checks |
| Credential expiry | Expired OAuth tokens force backup mode, hiding drift | Credential monitoring, expiry alerts |
| Race conditions | Concurrent updates to settings files | File locking, atomic writes |

### Detection Methods

#### 1. Dashboard Health Widget

The Kurultai dashboard includes a Model Drift widget that:

- Reads configured model from database (`model_config.json`)
- Reads actual model from `~/.openclaw/claude/settings.json`
- Compares both values and flags discrepancies
- Shows visual indicator when drift detected

#### 2. Automated Watchdog Monitoring

**Primary Watchdog**: `ogedei-watchdog.py`
**Schedule**: Runs every 5 minutes
**Log**: `/Users/kublai/.openclaw/logs/ogedei-watchdog.log`

The ogedei watchdog continuously monitors settings files and logs `O001 MODEL_DRIFT` warnings when:
- `settings.json` ANTHROPIC_MODEL differs from expected value
- `mode.json` is stuck in "backup" mode after credential expiry
- Settings corruption is detected

**Additional Script**: `~/.openclaw/agents/ogedei/scripts/model-drift-watchdog.sh`
**Schedule**: Cron job runs every 15 minutes
**Log**: `~/.openclaw/logs/model-drift.log`

```bash
# Manual run of primary watchdog
python3 ~/.openclaw/agents/ogedei/ogedei-watchdog.py

# View watchdog logs
tail -f /Users/kublai/.openclaw/logs/ogedei-watchdog.log

# Manual run of secondary script
~/.openclaw/agents/ogedei/scripts/model-drift-watchdog.sh
```

#### 3. Manual Detection Commands

```bash
# Run validation script
bash ~/.openclaw/agents/ogedei/scripts/validate_settings.sh

# Check current settings
python3 -c "import json; from pathlib import Path; s = Path.home() / '.openclaw' / 'claude' / 'settings.json'; print(json.load(open(s))['env']['ANTHROPIC_MODEL'])"

# Check mode
python3 -c "import json; from pathlib import Path; m = Path.home() / '.openclaw' / 'claude' / 'mode.json'; print(json.load(open(m))['mode'])"
```

#### 3. Configuration Validation Script

**Location**: `~/.openclaw/agents/ogedei/scripts/validate-model-config.sh`
**Purpose**: Validate model configuration across all settings files

```bash
# Run validation
~/.openclaw/agents/ogedei/scripts/validate-model-config.sh

# Output: JSON with drift status, configured model, actual model
```

### Prevention Strategies

#### 1. Automated Monitoring

The system includes multiple layers of protection:

- **ogedei-watchdog.py**: Checks model drift every 5 minutes, logs warnings to `/Users/kublai/.openclaw/logs/ogedei-watchdog.log`
- **validate_settings.sh**: Validates configuration files for corruption or misconfiguration
- **Dashboard management**: Use https://the.kurult.ai for all configuration changes to ensure proper validation
- **Credential renewal**: Renew tokens before expiry to avoid automatic fallback to backup mode

#### 2. Use Dashboard for All Changes

**DO**: Update model configuration through:
- Dashboard UI → Settings tab → Model dropdown
- API: `PUT /api/settings/model` with `{ "model": "claude-opus-4-6" }`

**DON'T**: Manually edit `~/.openclaw/claude/settings.json`

#### 3. Monitor Credential Expiry

- Proactively refresh Anthropic OAuth tokens before expiry
- Set up alerts for credential expiration (planned feature)
- Test primary mode regularly to catch issues early

#### 4. Validate After Changes

After any model configuration change:

```bash
# Run validation
bash ~/.openclaw/agents/ogedei/scripts/validate_settings.sh

# Check watchdog logs
tail -20 /Users/kublai/.openclaw/logs/ogedei-watchdog.log

# Check model drift logs
tail -20 ~/.openclaw/logs/model-drift.log
```

#### 5. Avoid Backup Mode Long-Term

Backup mode is designed for temporary fallback (rate limits, outages). Extended use masks primary settings issues.

**Best practice**: Resolve primary mode issues promptly, return to `auto` mode.

### Remediation Steps

If model drift is detected:

#### Step 1: Identify the Scope

```bash
# Run validation to see extent of drift
~/.openclaw/agents/ogedei/scripts/validate-model-config.sh
```

Check:
- Is primary settings affected?
- Is backup settings affected?
- Is mode.json set to backup (masking the issue)?

#### Step 2: Restore Correct Configuration

**Option A: Via Dashboard (Recommended)**

1. Access Kurultai dashboard: http://localhost:3000
2. Navigate to Settings tab
3. Select correct model from dropdown
4. Save changes
5. Verify with validation script

**Option B: Via API**

```bash
# Set model via API
curl -X PUT http://localhost:3000/api/settings/model \
  -H "Content-Type: application/json" \
  -d '{"model": "claude-opus-4-6"}'

# Verify
~/.openclaw/agents/ogedei/scripts/validate-model-config.sh
```

**Option C: Manual (Last Resort, Bypasses Config Guard)**

⚠️ **WARNING**: Manual edits bypass validation and can cause synchronization issues.

```bash
# Stop dashboard first
cd ~/.openclaw/kurultai && npm run stop

# Edit file (use correct JSON syntax)
nano ~/.openclaw/claude/settings.json

# Restart dashboard
cd ~/.openclaw/kurultai && npm run start

# Verify
~/.openclaw/agents/ogedei/scripts/validate-model-config.sh
```

#### Step 3: Restore Primary Mode (If Applicable)

If drift was masked by backup mode:

1. Verify Anthropic credentials are valid: `claude auth status`
2. If expired, refresh: `claude auth login`
3. Set mode to auto via dashboard or API:
   ```bash
   curl -X POST http://localhost:3000/api/settings/mode \
     -H "Content-Type: application/json" \
     -d '{"mode": "auto"}'
   ```
4. Validate: `~/.openclaw/agents/ogedei/scripts/validate-model-config.sh`

#### Step 4: Monitor and Verify

```bash
# Check watchdog logs for continued drift
tail -f ~/.openclaw/logs/model-drift.log
tail -f /Users/kublai/.openclaw/logs/ogedei-watchdog.log

# Verify dashboard health widget shows no drift
# (http://localhost:3000 → Settings → Health)
```

### Real-World Example: 2026-03-24 Incident

**Problem**: Model drift detected where `settings.json` contained incorrect model configuration

**Details**:
- **Corruption**: Line 60 of `settings.json` had `"glm-5"` instead of `"claude-sonnet-4-6"`
- **System behavior**: Kurultai continued functioning due to backup mode using correct `settings.backup.json`
- **Detection**: ogedei-watchdog.py detected and logged drift throughout the incident with `O001 MODEL_DRIFT` warnings
- **Resolution**: Dashboard intervention required to fix corrupted `settings.json`
- **Monitoring**: Watchdog logs at `/Users/kublai/.openclaw/logs/ogedei-watchdog.log` captured the entire incident timeline

**Key Lessons**:
1. Backup mode can mask primary settings corruption, allowing continued operation
2. Automated monitoring (ogedei-watchdog.py) is critical for detecting drift that doesn't cause immediate failures
3. Dashboard-based remediation is safer than manual file editing
4. Regular validation checks help catch issues before they impact task quality

**Related Documentation**:
- Full incident report: `~/.openclaw/agents/ogedei/workspace/model-drift-incident-20260324.md`
- Watchdog implementation: `~/.openclaw/agents/ogedei/ogedei-watchdog.py`

### Related Documentation

- **Model Configuration**: See "Model Selection" section above
- **Provider Fallback**: See "Architecture Overview" above
- **Credential Vault**: See "Credential Vault" section above
- **Incident Report**: `~/.openclaw/agents/ogedei/workspace/model-drift-incident-20260324.md`
