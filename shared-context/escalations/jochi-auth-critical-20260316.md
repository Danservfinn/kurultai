# CRITICAL ESCALATION: Jochi Authentication Failure

**Generated:** 2026-03-16T03:28:00Z (Heartbeat Check)
**Priority:** CRITICAL
**Agent:** jochi
**Duration:** 72+ hours idle, 0% success rate

---

## Issue Summary

Jochi agent has been non-functional for 72+ hours due to authentication failures in the claude-agent fallback chain.

**Symptoms:**
- sessions.json repeatedly created with `model=qwen3.5-plus` instead of `claude-opus-4-6`
- Last successful task: 2026-03-14T14:06 (over 36 hours ago)
- Last 3+ tasks: All failed on bailian/qwen3.5-plus (Tier 2 fallback)
- 6+ REFLECT_SUMMARY events flagged MODEL_DRIFT without resolution

---

## Root Cause (Identified in Rule 9)

The claude-agent wrapper uses a 3-tier fallback:
1. **Tier 0:** Anthropic (claude-opus-4-6) via OAuth — **FAILING**
2. **Tier 1:** Z.AI (glm-5) — **FAILING**
3. **Tier 2:** Alibaba (qwen3.5-plus) — Used as fallback, but tasks fail on wrong model

**Evidence:**
- sessions.json was deleted per Rule 7 (2026-03-15T05:00)
- sessions.json recreated at 2026-03-15T07:44 with model=qwen3.5-plus
- provider.env has ZAI_AUTH_TOKEN configured
- Anthropic uses OAuth (no token stored) — OAuth session likely expired

---

## Required Human Action

**Per Rule 10 — Human Intervention Required:**

1. **Refresh Anthropic OAuth for jochi:**
   ```bash
   cd /Users/kublai/.openclaw/agents/jochi
   claude auth login
   ```

2. **Verify ZAI_AUTH_TOKEN works for jochi:**
   - Token exists in `/Users/kublai/.openclaw/credentials/provider.env`
   - Test: `curl -H "Authorization: Bearer $ZAI_AUTH_TOKEN" https://api.z.ai/api/anthropic/v1/models`

3. **After auth fix:**
   - Delete sessions.json if it exists
   - Trigger a test task to verify model=claude-opus-4-6

---

## Interim Mitigation (Per Rule 11)

Until auth is fixed:
- **Suspend jochi routing** in task_load_balancer.py
- **Redistribute jochi-domain tasks** (analytics, security, patterns) to temujin as backup analyst

---

## Files to Check

- `/Users/kublai/.openclaw/agents/jochi/sessions.json` — Should not exist or have claude-opus-4-6
- `/Users/kublai/.openclaw/credentials/provider.env` — ZAI_AUTH_TOKEN present
- `/Users/kublai/.openclaw/agents/jochi/memory/2026-03-15.md` — Full incident history

---

## Verification Criteria

Escalation resolved when:
- [ ] `claude auth login` completed successfully in jochi workspace
- [ ] Next jochi task shows `MODEL_USED: model_id=claude-opus-4-6`
- [ ] Task success rate returns to >90%
