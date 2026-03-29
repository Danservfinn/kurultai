# Model Configuration System — Authoritative Reference

**Date:** 2026-03-23
**Status:** CANONICAL — supersedes all prior notes about model/settings drift
**Supersedes:** SETTINGS_MISMATCH-2026-03-23.md, IDLE-DETECTION-CORRECTION-2026-03-23.md (model drift sections)

---

## Source of Truth

**https://the.kurult.ai/sessions** is the SOLE source of truth for agent model configuration.

**Do NOT:**
- Manually edit any agent's `.claude/settings.json`
- Manually edit `~/.openclaw/claude/mode.json`
- Propose model config changes in tasks, reflections, or shared-context escalations
- Treat model mismatch warnings as behavioral failures requiring rules

---

## How It Works

### 1. Mode (`~/.openclaw/claude/mode.json`)

Controls which provider all agents use:

| Mode | Description | Provider | Model |
|------|-------------|----------|-------|
| `auto` | **Primary** — use this normally | Anthropic | claude-sonnet-4-6 |
| `backup` | **Failover** — switch if Anthropic unavailable | Z.AI | glm-5 |
| `primary` | Primary only, no fallback | Anthropic | claude-sonnet-4-6 |

Current configured values:
- **Auto mode** → `anthropic / claude-sonnet-4-6`
- **Backup mode** → `zai / glm-5` (credentials in `~/.openclaw/credentials/provider.env`)

### 2. Agent Settings (`agents/{name}/.claude/settings.json`)

Written by the dashboard when "Apply Fleet" is clicked. Contains:

**Auto mode (current):**
```json
{ "env": { "ANTHROPIC_MODEL": "claude-sonnet-4-6" } }
```

**Backup mode:**
```json
{
  "env": {
    "ANTHROPIC_MODEL": "glm-5",
    "ANTHROPIC_BASE_URL": "https://api.z.ai/api/anthropic",
    "ANTHROPIC_AUTH_TOKEN": "<stored in provider.env>"
  }
}
```

These files are **read-only** (`chmod 444`) — the dashboard uses `writeProtectedConfig` which re-locks after every write. Manual edits will fail with permission denied.

### 3. Dashboard Fleet Apply

To change all agents' model config:
1. Go to https://the.kurult.ai/sessions
2. Click **Auto** or **Backup** mode button
3. Select provider + model from dropdowns
4. Click **Apply Fleet**

The API endpoint: `PUT /api/claude-config/fleet` (requires Bearer token from `~/.openclaw/credentials/kurultai-api.key`).

### 4. Global Settings (`~/.openclaw/claude/settings.json`)

This is the primary Claude Code settings file (contains plugins, hooks, permissions). It also has `env.ANTHROPIC_MODEL` as a **backward-compat field** — the dashboard updates it when Apply Fleet runs. Agents do not read this file directly for model selection.

---

## What Model Drift Warnings Mean

The dispatch daemon (`ogedei_dispatch.py`) compares:
- `kurultai.json` agent model (OpenClaw/Alibaba model — kimi-k2.5 by default)
- `settings.json` ANTHROPIC_MODEL (claude-agent model — claude-sonnet-4-6)

These are **different config systems** for different executors:
- `kurultai.json` = OpenClaw executor model (governs `openclaw run`)
- `settings.json` = claude-agent executor model (governs `claude-agent` sessions)

A mismatch between these two is **expected and normal**. It is NOT a behavioral failure. The dispatch daemon's model drift check fires for informational purposes only.

**Rule for all agents:** If you see "Model drift: config=X settings=Y" in logs — ignore it. Do not write rules about it. Do not escalate it. It is by design.

---

## Bugs Fixed (2026-03-23)

### `kurultai_ledger.py` timestamp bug
- **Bug:** `int(0.17) → 0 → None` bypassed Neo4j time filter; tz-aware vs tz-naive comparison raised `TypeError` caught silently — ALL historical events returned for any window
- **Effect:** Cascade failure counter read all 356 historical FAILED events as "in last 10 minutes" → permanent "80+ failures" alert
- **Fix:** `math.ceil(hours)` prevents zero collapse; `datetime.now(timezone.utc)` prevents tz comparison error
- **File:** `~/.openclaw/agents/main/scripts/kurultai_ledger.py`

### Mongke idle detection false positive
- **Bug:** `kurultai-reflect` counted `.done.md` files to detect activity; current format uses `pending_verification` state (no `.done.md` created)
- **Effect:** Mongke reported "0 tasks in 24h" despite completing 23 tasks that day
- **Fix:** Use dispatch log or Neo4j ledger for activity detection, not `.done.md` file counts

---

## Credentials Location

- Provider credentials: `~/.openclaw/credentials/provider.env`
- API key for dashboard: `~/.openclaw/credentials/kurultai-api.key`
- Neither file should be read or cited in task outputs

---

*Written by Kublai (horde-debug) — 2026-03-23*
