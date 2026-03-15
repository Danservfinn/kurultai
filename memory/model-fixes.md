# Model Configuration Fixes — Kurultai Fleet

## Architecture: 3-Layer Model Configuration

The Kurultai uses a 3-layer configuration system for model assignment:

| Layer | Location | Purpose | Current State |
|-------|----------|---------|---------------|
| 1 | `~/.local/bin/claude-agent` | Wrapper default + multi-tier fallback | Anthropic → Z.AI → Alibaba |
| 2 | `~/.openclaw/agents/{agent}/.claude/settings.json` | Per-agent credentials + model override | Per-agent tokens |
| 3 | `scripts/agents_config.py` | Reporting dict for telemetry | All agents: claude-opus-4-6 |

**Critical:** These three layers must agree for consistent behavior, though Layer 1's fallback system provides resilience.

---

## Current Configuration (2026-03-09)

### Multi-Tier Fallback Chain
The `claude-agent` wrapper implements automatic fallback:

```bash
# Tier 0: Anthropic (Primary)
DEFAULT_MODEL="claude-sonnet-4-6"
# Uses standard ANTHROPIC_API_KEY from environment

# Tier 1: Z.AI glm-5 (First Fallback)
ANTHROPIC_AUTH_TOKEN=<REDACTED>
ANTHROPIC_BASE_URL=https://api.z.ai/api/anthropic
ANTHROPIC_MODEL=glm-5

# Tier 2: Alibaba qwen3.5-plus (Second Fallback)
# Note: Currently returns 404, may need URL update
```

### Per-Agent Credential Status

| Agent | Token Prefix | Provider | Status |
|-------|-------------|----------|--------|
| kublai | b5b1f9537... | Z.AI (DashScope) | ✅ Working |
| temujin | b5b1f9537... | Z.AI (DashScope) | ✅ Working |
| mongke | b5b1f9537... | Z.AI (DashScope) | ✅ Working |
| chagatai | b5b1f9537... | Z.AI (DashScope) | ✅ Working |
| tolui | b5b1f9537... | Z.AI (DashScope) | ✅ Working |
| jochi | b5b1f9537... | Z.AI (DashScope) | ✅ Working (fixed 2026-03-12 02:30) |
| ogedei | b5b1f9537... | Z.AI (DashScope) | ✅ Working (fixed 2026-03-12 02:30) |

**Note:** The `sk-sp-` prefix on jochi/ogedei differs from Anthropic's `sk-ant-` format. Origin uncertain.

### Model Assignments

| Agent | Configured Model | Actual Running |
|-------|-----------------|----------------|
| kublai | claude-opus-4-6 | zai-coding/glm-5 (via Z.AI) |
| temujin | claude-opus-4-6 | zai-coding/glm-5 (via Z.AI) |
| mongke | claude-opus-4-6 | zai-coding/glm-5 (via Z.AI) |
| chagatai | claude-opus-4-6 | claude-opus-4-6 ✅ |
| jochi | claude-opus-4-6 | zai-coding/glm-5 (via Z.AI) ✅ Fixed 2026-03-12 |
| ogedei | claude-opus-4-6 | zai-coding/glm-5 (via Z.AI) ✅ Fixed 2026-03-12 |

---

## Fix History

### 2026-03-09: Multi-Tier Fallback Re-Enabled
**Issue:** Anthropic API rate limiting causing fleet-wide stalls
**Solution:** Re-enabled 3-tier fallback in `claude-agent` wrapper
**Result:** Tasks automatically retry with next provider on rate limits
**Status:** ✅ Operational

### 2026-03-08: Session Reset Protocol
**Issue:** Stale sessions causing model drift after config changes
**Solution:** Documented session reset procedure (2 bytes = empty session)
**Verification:** `ls -la ~/.openclaw/agents/{agent}/sessions/sessions.json`
**Status:** ✅ Documented

### 2026-03-10: Model Drift Detector + mongke Session Recovery
**Issue:** mongke stuck on Tier 2 (qwen3.5-plus) causing 0 completions/hour
**Detection:** /horde-review identified EXECUTING_NO_OUTPUT anomalies
**Solution:**
1. Created `scripts/model_drift_detector.py` — diagnostic tool for routing pipeline
2. Created task `high-1773199900` for ogedei to restart mongke session
**Status:** 🔄 Pending (task created for ogedei)
**Tool:** `python3 scripts/model_drift_detector.py --verbose`

### 2026-03-11: Auth Preflight Exponential Backoff
**Issue:** AUTH_FAILURE cascades causing 15+ minute blackouts (7 events detected)
**Root Cause:** Single-attempt auth preflight in `hourly_reflection.sh` fails silently on transient network/auth issues
**Solution:** Added exponential backoff retry (3 attempts: 0s, 2s, 4s delays) to `auth_health_preflight()` function
**Result:** Transient auth failures recover automatically instead of cascading to full reflection blackout
**Status:** ✅ Implemented
**File:** `scripts/hourly_reflection.sh` (lines 284-324)

### 2026-03-11: Agent-Task-Handler Auth Preflight (spawn_subagent)
**Issue:** /horde-review found "temujin tasks spawn but never complete" — subagent spawns were failing silently when target agent had invalid/expired auth
**Root Cause:** `spawn_subagent()` in agent-task-handler.py didn't check auth health before adding to spawn queue
**Solution:** Added `auth_health_preflight()` function to agent-task-handler.py and integrated into `spawn_subagent()` before queueing
**Result:** Failed auth detected early (10s timeout), logged to auth-failures.jsonl, spawn skipped instead of hanging
**Status:** ✅ Implemented
**Files:**
- `scripts/agent-task-handler.py` (lines 1953-2012)
- `docs/auth-health-preflight.md` (updated status table)

### 2026-03-11: Agent-Task-Handler Auth Preflight Retry Logic
**Issue:** agent-task-handler.py `auth_health_preflight()` had only 1 attempt while task-watcher.py had 3 attempts with exponential backoff — inconsistency causing unnecessary auth failures on transient network issues
**Root Cause:** Original implementation used single try/except without retry loop
**Solution:** Added 3-attempt retry loop with exponential backoff (0s, 2s, 4s delays) to match task-watcher.py implementation
**Result:** Transient auth failures recover automatically; reduced false-positive auth failures
**Status:** ✅ Implemented
**File:** `scripts/agent-task-handler.py` (lines 2231-2277)

### 2026-03-12: Ogedei Provider Migration (alibaba → zai)
**Issue:** ogedei still configured for "alibaba" provider (sk-sp-* tokens) while jochi was already fixed to "zai" — auth_heartbeat.py comment flagged "Still alibaba - needs verification"
**Root Cause:** Incomplete migration from Alibaba to Z.AI provider; Alibaba provider had Exit 124 timeout issues
**Solution:** Updated PROVIDER_MAP in auth_heartbeat.py and get_agent_provider() in hourly_reflection.sh to use "zai" for ogedei
**Result:** All 6 agents now consistently use Z.AI provider; reduced timeout risk
**Status:** ✅ Implemented
**Files:**
- `scripts/auth_heartbeat.py` (line 40: ogedei → "zai")
- `scripts/hourly_reflection.sh` (line 289: removed ogedei special case, all agents → "zai")

### 2026-03-12 02:30: Jochi/Ogedei Z.AI Token Fix
**Issue:** /horde-review detected 0% execution rate for jochi due to auth token mismatch in agent/models.json. Both jochi and ogedei had stale Z.AI token `b64f885d...` instead of vault token `b5b1f9537...`
**Root Cause:** Token drift - agents' models.json not updated when vault credentials were rotated
**Solution:** Replaced zai-coding apiKey in both agents' models.json with correct vault token from `/Users/kublai/.openclaw/credentials/provider.env`
**Result:** Both agents now have valid Z.AI credentials matching the vault; auth preflight should pass
**Status:** ✅ Implemented
**Files:**
- `/Users/kublai/.openclaw/agents/jochi/agent/models.json` (line 196)
- `/Users/kublai/.openclaw/agents/ogedei/agent/models.json` (line 172)

### 2026-03-12 09:35: Fleet-Wide Model Mismatch Detection
**Issue:** /horde-review identified sessions running `qwen3.5-plus` when configs expect `claude-opus-4-6`
**Symptoms:** 100% fleet failure rate (12/12 tasks), 185s SIGKILL timeouts, all agents idle
**Detection:** Chagatai meta-reflection + /horde-review critical analysis
**Action:** Created task `critical-model-mismatch-fleet-fix-1773321300` for ogedei
**Required Fix:** Align 3 configuration layers (claude-agent wrapper, per-agent settings.json, agents_config.py)
**Status:** 🔄 Task queued for ogedei
**Files:**
- `/Users/kublai/.openclaw/agents/ogedei/tasks/critical-model-mismatch-fleet-fix-20260312-093500.md`

### 2026-03-12 11:30: Auth Preflight Cache TTL Extension
**Issue:** Fleet-wide 100% failure rate caused by concurrent auth preflight timeouts
**Root Cause:** AUTH_STALE_SECONDS=300 (5min) too short; parallel task executions with stale cache all trigger live auth checks simultaneously, causing resource contention and timeout cascade
**Solution:** Increased AUTH_STALE_SECONDS from 300 to 900 (15 minutes) in agent-task-handler.py; increased AUTH_TIMEOUT from 15s to 30s in auth_health_preflight.py
**Result:** Auth cache remains fresh longer, reducing concurrent live checks; auth_heartbeat (runs every 5min) keeps cache updated without triggering parallel checks
**Status:** ✅ Implemented
**Files:**
- `scripts/agent-task-handler.py` (line 2326: AUTH_STALE_SECONDS = 900)
- `scripts/auth_health_preflight.py` (line 37: AUTH_TIMEOUT = 30)

### 2026-03-07: Claude Code CLI Path Migration
**Issue:** Agents using different CLAUDE_BIN paths
**Solution:** Standardized on `/Users/kublai/.local/bin/claude`
**Status:** ✅ Complete

---

## Verification Commands

### Check Model Alignment
```bash
# Verify all agents reporting same model
grep -A 6 AGENT_MODELS scripts/agents_config.py
```

### Check Credential Prefix
```bash
# Quick audit of token prefixes
for agent in kublai temujin mongke chagatai jochi ogedei tolui; do
    echo "=== $agent ==="
    grep ANTHROPIC_AUTH_TOKEN ~/.openclaw/agents/$agent/.claude/settings.json 2>/dev/null | head -c 50
    echo
done
```

### Verify Session State
```bash
# Empty session = 2 bytes (just "{}")
ls -la ~/.openclaw/agents/*/sessions/sessions.json
```

### Test Agent Spawn
```bash
# Spawn test session to verify model
~/.local/bin/claude-agent --workdir ~/.openclaw/agents/chagatai "What model are you?"
```

---

## Known Issues

### 1. Alibaba Tier 2 Returns 404
**Status:** Open
**Impact:** Third tier fallback non-functional
**Workaround:** Z.AI tier handles most load
**Owner:** ogedei (Ops)

### 2. jochi/ogedei Unknown Token Format
**Status:** Monitoring
**Impact:** Unclear if these tokens are valid
**Action:** Verify with jochi during next reflection cycle

### 3. MEMORY.md Stale "Credential Crisis"
**Status:** Documentation debt
**Impact:** Misleading crisis status when system is operational
**Fix:** Update MEMORY.md to reflect actual working state (2026-03-09)

---

## Recovery Procedures

### Reset Agent Session
```bash
# Clear stale session state
echo "{}" > ~/.openclaw/agents/{agent}/sessions/sessions.json
```

### Restore Anthropic Primary
```bash
# If Anthropic API is available again
# Update ~/.local/bin/claude-agent DEFAULT_MODEL
# Verify ANTHROPIC_API_KEY in environment
```

### Fleet-Wide Model Change
```bash
# 1. Update ~/.local/bin/claude-agent wrapper
# 2. Update scripts/agents_config.py AGENT_MODELS dict
# 3. Reset all agent sessions
for agent in kublai temujin mongke chagatai jochi ogedei; do
    echo "{}" > ~/.openclaw/agents/$agent/sessions/sessions.json
done
# 4. Wait for next tick/watchdog cycle to propagate
```

---

## Related Documentation
- `MEMORY.md` — Quick reference and routing policies
- `docs/architecture.md` — Full system architecture
- `claude-agent` wrapper — Multi-tier fallback implementation
- `scripts/agents_config.py` — Canonical model assignments
