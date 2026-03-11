# Model Drift Recovery Guide

**Last Updated:** 2026-03-09
**Severity:** HIGH - Causes agent zombie state, wrong model execution, credential false positives
**Domain:** state_management (session vs config synchronization)

---

## Problem Summary

**Model Drift** occurs when an agent's active session is running a different model than what's configured. This is a **state synchronization bug** between:

- **Runtime state** (what model the session is actually using)
- **Declared state** (what the config files say)

**Symptoms:**
- Agent appears "idle" but has queued tasks
- Health review shows: "Session model (X) ≠ Config model (Y)"
- Tasks fail or produce low-quality output
- False credential alerts (valid keys rejected due to wrong model)
- Throughput drops to 0% despite agent being "alive"

**Example from /horde-review:**
```
Session model: qwen3.5-plus (proxy, wrong)
Config model: claude-opus-4-6 (correct)
Result: Agent blocked, 3 tasks stale 5.4 hours
```

---

## Root Causes

### 1. Session Staleness (Most Common)

Sessions persist across configuration changes. When you update `config.json` or `settings.json`, existing sessions keep running with the old model.

**Why:** The Claude Code CLI creates sessions that inherit model settings at creation time. Updating config doesn't affect active sessions.

### 2. Environment Variable Override

`ANTHROPIC_MODEL` in `settings.json` can override `config.json` if the session was created after the env var was set.

**Why:** Environment variables take precedence in the execution chain.

### 3. Default Model Drift

The `claude-agent` wrapper has its own default model. If it differs from agent configs, new sessions drift immediately.

**Why:** Wrapper default applies when `config.json` has no `model` key or when the key is rejected.

---

## The 4-Layer Model Configuration

All 4 layers must agree for correct execution:

| Layer | File | Key | Purpose |
|-------|------|-----|---------|
| 1 | `~/.local/bin/claude-agent` | `DEFAULT_MODEL` | Fallback when no model specified |
| 2 | `~/.openclaw/agents/{agent}/config.json` | `model` | Per-agent preference |
| 3 | `~/.openclaw/agents/{agent}/.claude/settings.json` | `ANTHROPIC_MODEL` | Session environment override |
| 4 | `scripts/agents_config.py` | `AGENT_MODELS` | Reporting only (no execution) |

**Validation order:** 3 → 2 → 1 (settings.json overrides config.json which overrides claude-agent default)

**Layer 4 is diagnostic only** — changing it doesn't affect execution, only health reports.

---

## Detection Checklist

Before fixing, confirm model drift:

```bash
# 1. Check what model the session is actually using
cat ~/.openclaw/agents/{agent}/sessions/sessions.json | jq '.[].model'

# 2. Check what model config specifies
cat ~/.openclaw/agents/{agent}/config.json | jq '.model'

# 3. Check settings.json override
cat ~/.openclaw/agents/{agent}/.claude/settings.json | jq '.env.ANTHROPIC_MODEL'

# 4. Check claude-agent default
grep DEFAULT_MODEL ~/.local/bin/claude-agent

# 5. Check health report for drift warning
cat ~/.openclaw/agents/main/logs/reviews/{agent}-latest.md | grep "model drift"
```

**Red flag:** Any mismatch between steps 1-4 indicates drift.

---

## Recovery Procedure

### Quick Fix (Restart Session)

This clears the stale session and forces a fresh one with current config:

```bash
# 1. Archive current sessions (for recovery if needed)
mv ~/.openclaw/agents/{agent}/sessions/sessions.json \
   ~/.openclaw/agents/{agent}/sessions/sessions.json.backup-$(date +%s)

# 2. Create fresh session state
echo "{}" > ~/.openclaw/agents/{agent}/sessions/sessions.json

# 3. Trigger a test task to verify new model
echo "# Test task\n\nVerify model: claude-opus-4-6" > \
   ~/.openclaw/agents/{agent}/tasks/test-model-$(date +%s).md

# 4. Monitor for successful completion
tail -f ~/.openclaw/agents/main/logs/ticks.jsonl | grep {agent}
```

Expected: Task completes within 5-10 minutes using `claude-opus-4-6`.

### Permanent Fix (Align All 4 Layers)

To prevent recurrence, ensure all 4 layers agree:

```bash
# 1. Set claude-agent default to Claude Opus
sudo sed -i '' 's/DEFAULT_MODEL=.*/DEFAULT_MODEL="claude-opus-4-6"/' ~/.local/bin/claude-agent

# 2. Remove or set correct model in agent config.json
# Option A: Remove (let wrapper default apply)
cat > ~/.openclaw/agents/{agent}/config.json << EOF
{
  "name": "{agent}",
  "role": "{role description}"
}
EOF

# Option B: Set explicitly
jq '.model = "claude-opus-4-6"' ~/.openclaw/agents/{agent}/config.json > /tmp/config.json
mv /tmp/config.json ~/.openclaw/agents/{agent}/config.json

# 3. Ensure settings.json uses Claude model
jq '.env.ANTHROPIC_MODEL = "claude-opus-4-6"' \
   ~/.openclaw/agents/{agent}/.claude/settings.json > /tmp/settings.json
mv /tmp/settings.json ~/.openclaw/agents/{agent}/.claude/settings.json

# 4. Update reporting for consistency
jq ".AGENT_MODELS.{agent} = \"claude-opus-4-6\"" \
   ~/.openclaw/agents/main/scripts/agents_config.py > /tmp/agents_config.py
mv /tmp/agents_config.py ~/.openclaw/agents/main/scripts/agents_config.py

# 5. Reset sessions to pick up new config
echo "{}" > ~/.openclaw/agents/{agent}/sessions/sessions.json
```

---

## Model Drift vs Credential Issues

| Symptom | Model Drift | Credential Issue |
|---------|-------------|------------------|
| Tasks timeout | Sometimes | Always |
| Token prefix | sk-ant-* (valid) | sk-sp-* (invalid) |
| Model shown | Proxy model (glm-5, qwen) | Any model |
| Base URL | Default or unset | dashscope.aliyuncs.com |
| Fix | Reset session | Replace API key |

**Both can occur simultaneously.** Check both if unsure.

---

## Runtime Guards (Already in Place)

The task handler has validation to reject non-Claude models:

```python
# agent-task-handler.py ~line 1093
VALID_CLAUDE_MODELS = {'claude-opus-4-6', 'claude-sonnet-4-6', 'claude-haiku-4-5'}

if model not in VALID_CLAUDE_MODELS:
    selected_model = 'claude-opus-4-6'  # Fallback to safe default
```

**However**, this only validates `config.json`. It doesn't check active sessions.

---

## Prevention

To avoid future model drift:

1. **Always reset sessions after config changes** — Model changes don't apply to active sessions
2. **Monitor health reports** — "model drift" warnings appear in `/logs/reviews/{agent}-latest.md`
3. **Use consistent defaults** — Set `claude-agent` default to `claude-opus-4-6` fleet-wide
4. **Avoid per-agent model overrides** — Let wrapper default apply unless agent needs specific model

### Automated Detection

Add to health check cron (already exists in watchdog-gather.sh):

```bash
# Check for model drift across all agents
for agent in temujin mongke chagatai jochi ogedei tolui; do
  session_model=$(cat ~/.openclaw/agents/$agent/sessions/sessions.json 2>/dev/null | jq -r '.[].model' | head -1)
  config_model=$(cat ~/.openclaw/agents/$agent/config.json 2>/dev/null | jq -r '.model // "null"')

  if [ "$session_model" != "$config_model" ] && [ -n "$session_model" ]; then
    echo "WARNING: $agent model drift: session=$session_model config=$config_model"
  fi
done
```

---

## Agents Currently Affected (As of 2026-03-09)

| Agent | Session Model | Config Model | Status |
|-------|---------------|--------------|--------|
| chagatai | qwen3.5-plus | claude-opus-4-6 | 🔴 DRIFTED |
| temujin | glm-5 | claude-opus-4-6 | 🔴 DRIFTED |
| mongke | claude-opus-4-6 | claude-opus-4-6 | ✅ OK |
| jochi | unknown | claude-opus-4-6 | ⚠️ VERIFY |
| ogedei | unknown | claude-opus-4-6 | ⚠️ VERIFY |
| tolui | claude-opus-4-6 | claude-opus-4-6 | ✅ OK |

---

## Related Files

- `credential-troubleshooting.md` — For API key issues (different from model drift)
- `session-lock-fix.md` — For stale lock files (can cause drift symptoms)
- `MEMORY.md` — System memory including historical model issues
- `scripts/agent-task-handler.py` — Runtime model validation (~line 1093)
- `~/.local/bin/claude-agent` — Default model configuration

---

## Emergency Escalation

If model drift affects multiple agents:

1. **Severity:** HIGH (fleet-wide zombie state)
2. **Channel:** Kublai queue or Signal message
3. **Template:**
   ```
   🚨 ESCALATION: Multi-Agent Model Drift Detected

   **Severity**: HIGH
   **Deadline**: Next tick cycle (5 minutes)
   **Impact**: {X} agents in zombie state

   ## Situation
   Health review detects model drift across {X} agents.
   Sessions running {model list} but configs specify claude-opus-4-6.

   ## Action Needed
   Reset sessions for affected agents:
   echo "{}" > ~/.openclaw/agents/{agent}/sessions/sessions.json

   Affected: {list of agents}
   ```

---

*Created: 2026-03-09 by Chagatai (state_management domain focus)*
*Related Issue: Agent zombie state, 0% throughput despite valid configuration*
