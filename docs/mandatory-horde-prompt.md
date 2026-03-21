# Mandatory horde-prompt Integration (2026-03-20)

## Overview

As of this change, the Kurultai system **requires** `horde-prompt` to optimize all task prompts before sending to claude-agent. Tasks will **fail** if prompt optimization is unavailable or fails — there is no fallback to the original prompt.

## What Changed

### Files Modified

1. **`/Users/kublai/.openclaw/agents/main/scripts/agent-task-handler.py`**
   - Added `mandatory_mode` check at line ~3197
   - If `PROMPT_OPTIMIZER_AVAILABLE=false` and `mandatory_mode=true`: task fails immediately with `OPTIMIZER_UNAVAILABLE` event
   - If optimization throws an exception and `mandatory_mode=true`: task fails with `OPTIMIZATION_FAILED` event
   - Ledger events added for observability

2. **`/Users/kublai/.openclaw/agents/main/scripts/prompt_optimizer.py`**
   - Added `mandatory_mode` to `DEFAULT_CONFIG` (line ~28)
   - Modified `optimize_prompt()` to always raise exceptions in mandatory mode (line ~225)
   - Fallback to original prompt is now ignored when `mandatory_mode=true`

3. **`/Users/kublai/.openclaw/config/prompt-optimizer.json`** (NEW)
   - Created with `mandatory_mode: true`
   - `fallback_to_original: false` (redundant but explicit)

## Behavior Matrix

| Scenario | Old Behavior | New Behavior (mandatory_mode=true) |
|----------|--------------|-------------------------------------|
| Optimizer unavailable | Use original prompt | **Task fails** - `OPTIMIZER_UNAVAILABLE` |
| Optimization throws error | Use original prompt | **Task fails** - `OPTIMIZATION_FAILED` |
| Optimization succeeds | Use optimized prompt | Use optimized prompt (unchanged) |
| Optimization disabled | Use original prompt | Use original prompt (unchanged) |

## Configuration

### Enable/Disable Mandatory Mode

```json
// ~/.openclaw/config/prompt-optimizer.json
{
  "enabled": true,
  "mandatory_mode": true,    // ← Set to false to allow fallback
  "cache_enabled": true,
  "cache_ttl_seconds": 3600,
  "fallback_to_original": false,
  "min_task_length": 50,
  "skip_skill_hints": ["systematic-debugging", "horde-debug", "verification"]
}
```

### Temporarily Disable for Troubleshooting

If `horde-prompt` is causing issues and you need to allow tasks to execute:

```bash
# Edit the config
echo '{"enabled": true, "mandatory_mode": false, "fallback_to_original": true}' > ~/.openclaw/config/prompt-optimizer.json
```

Or set `enabled: false` to bypass optimization entirely.

## Ledger Events

New events added to the task ledger for observability:

| Event | Trigger | Fields |
|-------|---------|--------|
| `OPTIMIZER_UNAVAILABLE` | `horde-prompt` import fails | `agent`, `task_id`, `enforcer` |
| `OPTIMIZATION_FAILED` | `enhance_task_prompt()` throws | `agent`, `task_id`, `enforcer`, `error` |
| `PROMPT_OPTIMIZED` | Success (already existed) | `cached`, `agent_type` |

## Why This Matters

### Before (Fallback Mode)
- `horde-prompt` was optional — failures silently fell back to raw prompts
- Agents received unoptimized prompts, reducing task quality
- No alerting when the optimizer broke

### After (Mandatory Mode)
- `horde-prompt` is a **hard dependency** — failures stop tasks
- Immediate visibility into optimizer health
- Forces fixing the optimizer rather than masking failures

## Tradeoffs

### Pros
- Guarantees all agents receive optimized prompts
- Immediate failure detection for `horde-prompt` issues
- Enforces investment in prompt quality

### Cons
- Single point of failure — if `horde-prompt` breaks, **all tasks fail**
- Adds latency to every task (optimization must complete first)
- Cache becomes critical infrastructure (TTL: 1 hour)

## Dependencies

- `horde-prompt` skill at `~/.claude/skills/horde-prompt/`
- Cache directory: `~/.claude/skills/horde-prompt/.prompt-cache/`
- Config: `~/.openclaw/config/prompt-optimizer.json`

## Rollback Plan

If this causes widespread task failures:

```bash
# 1. Disable mandatory mode
echo '{"enabled": true, "mandatory_mode": false, "fallback_to_original": true}' > ~/.openclaw/config/prompt-optimizer.json

# 2. Or disable optimization entirely
echo '{"enabled": false}' > ~/.openclaw/config/prompt-optimizer.json

# 3. Or comment out the import in agent-task-handler.py (line 68)
# from prompt_optimizer import enhance_task_prompt, load_optimizer_config
```

## Testing

To verify the implementation:

```bash
# Test 1: Optimizer available + mandatory mode = should optimize
python3 -c "
from prompt_optimizer import load_optimizer_config
config = load_optimizer_config()
print(f'mandatory_mode={config.get(\"mandatory_mode\")}, enabled={config.get(\"enabled\")}')
"

# Test 2: Check PROMPT_OPTIMIZER_AVAILABLE flag
python3 -c "
import sys
sys.path.insert(0, '/Users/kublai/.openclaw/agents/main/scripts')
import agent_task_handler
print(f'PROMPT_OPTIMIZER_AVAILABLE={agent_task_handler.PROMPT_OPTIMIZER_AVAILABLE}')
"
```

## Related

- Original discussion: `/golden-horde` session on prompt construction
- `horde-prompt` skill: `~/.claude/skills/horde-prompt/SKILL.md`
- Architecture doc: `~/.openclaw/agents/main/docs/architecture.md`
