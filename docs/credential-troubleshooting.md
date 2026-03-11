# Agent Credential Troubleshooting Guide

**Last Updated:** 2026-03-08
**Severity:** CRITICAL - Invalid credentials block ALL agent task execution

---

## Problem Summary

When an agent has invalid API credentials, it cannot execute tasks. The Kurultai will show:
- 0% task completion rate for the affected agent
- Tasks timing out after 1800s (30 minutes)
- "FAKE COMPLETION" or "no_output" errors in logs
- 100% failure rate in agent health reports

---

## Root Causes

### 1. DashScope Proxy Credentials (Most Common)

**Symptoms:**
- `ANTHROPIC_AUTH_TOKEN` has `sk-sp-*` prefix (DashScope format)
- `ANTHROPIC_BASE_URL` points to `dashscope.aliyuncs.com`
- Agent reports model as `glm-5` instead of Claude models

**Why this breaks:** DashScope tokens don't work with Anthropic's API. The agent tries to authenticate and fails.

### 2. Invalid Claude API Key

**Symptoms:**
- `ANTHROPIC_AUTH_TOKEN` is empty or revoked
- Token has `sk-ant-*` prefix but is expired/invalid

**Why this breaks:** Anthropic API rejects invalid keys with 401/403 errors.

### 3. Proxy URL Bypass

**Symptoms:**
- `ANTHROPIC_BASE_URL` is set to a non-Anthropic domain
- Valid token present but requests go to wrong endpoint

**Why this breaks:** Token is sent to wrong API, which rejects it.

---

## Verification Checklist

Before fixing, verify the agent has bad credentials:

```bash
# 1. Check the agent's settings
cat ~/.openclaw/agents/{agent}/.claude/settings.json

# 2. Look for these RED FLAGS:
#    - ANTHROPIC_AUTH_TOKEN starting with "sk-sp-"
#    - ANTHROPIC_BASE_URL containing "dashscope" or "aliyuncs"
#    - ANTHROPIC_MODEL set to "glm-5" or "kimi-k2.5"

# 3. Check agent health via logs
tail -20 ~/.openclaw/agents/main/logs/reviews/{agent}-latest.md
```

---

## Fix Instructions

### Step 1: Obtain a Valid Anthropic API Key

1. Go to https://console.anthropic.com/
2. Navigate to API Keys section
3. Create a new key (will have `sk-ant-*` prefix)
4. **DO NOT** use DashScope, Bailian, or other proxy services

### Step 2: Update the Agent's settings.json

For each affected agent:

```bash
# Edit the settings file
nano ~/.openclaw/agents/{agent}/.claude/settings.json
```

Make these changes:

```json
{
  "env": {
    // REMOVE this line entirely if present:
    // "ANTHROPIC_BASE_URL": "https://...",

    // CHANGE the token to your valid key:
    "ANTHROPIC_AUTH_TOKEN": "sk-ant-your-real-key-here",

    // SET to a valid Claude model:
    "ANTHROPIC_MODEL": "claude-opus-4-6"
  }
}
```

### Step 3: Reset the Agent's Session

After updating credentials, clear the stale session:

```bash
# Reset sessions to force fresh session with new credentials
echo "{}" > ~/.openclaw/agents/{agent}/sessions/sessions.json
```

### Step 4: Verify the Fix

```bash
# Trigger a test task for the agent
echo "test" > ~/.openclaw/agents/{agent}/tasks/test-credentials-$(date +%s).md

# Monitor the agent log
tail -f ~/.openclaw/agents/main/logs/ticks.jsonl | grep {agent}
```

Expected result: Task completes successfully within 5-10 minutes.

---

## Runtime Guards (Already in Place)

The system has validation guards that will:
- Strip invalid `ANTHROPIC_BASE_URL` values at runtime
- Reject non-Claude models (glm-5, kimi-k2.5, etc.)
- Log credential errors to `logs/credential-alerts.json`

However, **fixing the actual settings.json file requires human action** because:
1. Valid API keys must be obtained from Anthropic's console
2. Each agent may need a different key (rate limit isolation)
3. Key rotation is a security-sensitive operation

---

## Agents That Need Credential Updates (As of 2026-03-08)

| Agent | Status | Token Format | Action Needed |
|-------|--------|--------------|---------------|
| chagatai | 🔴 BLOCKED | sk-sp-* (DashScope) | Replace with sk-ant-* |
| temujin | 🔴 BLOCKED | sk-sp-* (DashScope) | Replace with sk-ant-* |
| jochi | ⚠️ UNVERIFIED | Unknown | Verify and fix if needed |
| mongke | ⚠️ UNVERIFIED | Unknown | Verify and fix if needed |
| ogedei | ⚠️ UNVERIFIED | Unknown | Verify and fix if needed |
| tolui | ⚠️ UNVERIFIED | Unknown | Verify and fix if needed |

---

## Prevention

To avoid future credential drift:

1. **Never use proxy APIs** (DashScope, Bailian, etc.) for Claude access
2. **Monitor agent health** - 0% completion for >1 hour signals credential issues
3. **Use separate keys per agent** to isolate rate limits
4. **Document key rotation** in this file when updating

---

## Related Files

- `scripts/agent-task-handler.py` - Runtime credential validation (~line 722-730)
- `logs/credential-alerts.json` - Automated credential problem logging
- `logs/reviews/{agent}-latest.md` - Per-agent health reports
- `MEMORY.md` - System-wide memory including credential issues

---

## Emergency Escalation

If multiple agents are blocked simultaneously:

1. **Severity:** CRITICAL (system-wide outage)
2. **Channel:** Signal message immediately
3. **Template:**
   ```
   🚨 ESCALATION: Multi-Agent Credential Failure

   **Severity**: CRITICAL
   **Deadline**: ASAP
   **Impact**: {X} agents at 0% throughput

   ## Situation
   Multiple agents have invalid API credentials (DashScope format).
   System throughput reduced by {Y}%.

   ## Action Needed
   Replace ANTHROPIC_AUTH_TOKEN in affected agents' settings.json
   with valid sk-ant-* keys from https://console.anthropic.com/

   Affected: {list of agents}
   ```

---

*For questions, check the agent's latest health report at `logs/reviews/{agent}-latest.md`*
