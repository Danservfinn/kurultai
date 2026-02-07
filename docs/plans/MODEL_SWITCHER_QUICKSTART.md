# Model Switcher Quick Start Guide

## Installation Summary

The kurultai-model-switcher skill is now integrated into the kurultai_0.2.md deployment plan as **Appendix I**.

### What Was Done

1. ✅ Copied `model_switcher.py` to `/Users/kurultai/molt/scripts/`
2. ✅ Copied `model_switcher.py` to `/Users/kurultai/molt/moltbot-railway-template/scripts/` (for Railway deployment)
3. ✅ Updated `moltbot-railway-template/Dockerfile` to:
   - Install Python 3 in the container
   - Copy the scripts/ directory to `/app/scripts`
4. ✅ Updated `model_switcher.py` with production-appropriate paths:
   - `moltbot.json` → `/data/.clawdbot/moltbot.json`
   - `openclaw.json` → `/data/.clawdbot/openclaw.json`
   - History → `/data/.clawdbot/.model-switch-history.json`
   - Log → `/data/.clawdbot/model-switch.log`
5. ✅ Added **Appendix I: Model Switcher Installation** to `kurultai_0.2.md`

## Usage

### After Railway Deployment

```bash
# SSH into the Railway container
railway shell --service moltbot-railway-template

# View current model assignments
python scripts/model_switcher.py status

# Switch an agent to a new model
python scripts/model_switcher.py switch --agent main --model claude-sonnet-4

# Dry run (preview changes)
python scripts/model_switcher.py switch --agent all --model zai/glm-4.7 --dry-run

# Rollback to previous model
python scripts/model_switcher.py rollback --agent main
```

### Local Development

```bash
cd /Users/kurultai/molt
python scripts/model_switcher.py status
python scripts/model_switcher.py validate
```

## Agent Reference

| ID | Name | Role | Default Model |
|----|------|------|---------------|
| main | Kublai | Squad Lead / Router | moonshot/kimi-k2.5 |
| researcher | Möngke | Researcher | zai/glm-4.5 |
| writer | Chagatai | Content Writer | moonshot/kimi-k2.5 |
| developer | Temüjin | Developer / Security | zai/glm-4.7 |
| analyst | Jochi | Analyst | zai/glm-4.5 |
| ops | Ögedei | Operations / Emergency | zai/glm-4.5 |

## Safety Features

- **Automatic Backup**: Every switch stores the previous state (10 states retained)
- **Rollback**: `rollback --agent <id>` reverts to the previous model
- **Dry Run**: `--dry-run` flag validates without applying changes
- **Model Validation**: Checks that target model exists in openclaw.json

## Integration Points

### With kurultai_0.2.md

- Agent IDs match exactly (main, researcher, writer, developer, analyst, ops)
- Configuration paths align with ARCHITECTURE.md
- Environment variables from Phase 0 setup

### With Railway

- Script included in container via Dockerfile
- Uses `/data/.clawdbot/` for persistent storage
- Python 3 installed alongside Node.js

## Files Modified

| File | Change |
|------|--------|
| `docs/plans/kurultai_0.2.md` | Added Appendix I (Model Switcher Installation) |
| `scripts/model_switcher.py` | Copied from skill directory |
| `moltbot-railway-template/scripts/model_switcher.py` | Copied for Railway deployment |
| `moltbot-railway-template/Dockerfile` | Added Python installation + scripts copy |
| `moltbot-railway-template/scripts/model_switcher.py` | Updated paths for production |

## Next Steps

1. Complete kurultai_0.2.md deployment (Phases 0-7)
2. Verify model switcher works: `python scripts/model_switcher.py validate`
3. Test a switch: `python scripts/model_switcher.py switch --agent main --model claude-sonnet-4 --dry-run`
4. (Optional) Add HTTP endpoint to moltbot for web-based model switching
