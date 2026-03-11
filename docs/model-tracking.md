# Model Tracking in Cron Outputs

**Date:** 2026-03-08
**Task:** Add model tracking to all cron job outputs (tick, tock, reports)

## Overview

All cron-generated outputs now include the LLM model used for generation. This enables:
- Tracking which model was used for each tick/tock
- Analyzing model performance across agents
- Displaying model info in reports and dashboards
- Correlation analysis between model and task outcomes

## Implementation

### Utility Script

**`scripts/get_model.py`** - New utility for model detection

```bash
# Usage
python3 get_model.py --default        # Get default model from main agent
python3 get_model.py --agent kublai   # Get model for specific agent
python3 get_model.py --json           # Output as JSON
```

**Detection logic:**
1. Reads from `~/.openclaw/agents/{agent}/.claude/settings.json`
2. Extracts `env.ANTHROPIC_MODEL` value
3. Falls back to "unknown" if unavailable

### Modified Scripts

#### 1. watchdog-gather.sh (tick - every 5 min)

**Changes:**
- Line 66-69: MODEL detection at startup
- Line 597: Added `"model":"%s"` to ticks.jsonl JSON schema
- Line 613-614: Added `MODEL: %s (LLM triage)` to tick-summary.txt

**Output format:**
```
TICK 2026-03-08 20:32:51
MODEL: claude-opus-4-6 (LLM triage)
HEARTBEAT: gap_detected=false gap_minutes=0
...
```

```json
{"ts":"2026-03-08T20:32:51+0000","model":"claude-opus-4-6",...}
```

#### 2. tock-gather.sh (tock - every 30 min)

**Changes:**
- Line 60: MODEL detection at startup
- Line 1024: Added `"model": "$MODEL"` to tock JSON output
- Line 1443: Added `model=$MODEL` to tock.log one-liner

**Output format:**
```
[2026-03-08 20:16:43] TOCK | model=claude-opus-4-6 | tasks_done=0 | ...
```

```json
{
  "timestamp": "2026-03-08T20:16:43+0000",
  "model": "claude-opus-4-6",
  "agents": {...}
}
```

#### 3. hourly_reflection.sh

**Changes:**
- Line 27-29: MODEL detection at startup for reflection pipeline

#### 4. generate_hourly_report.py

**Changes:**
- Line 54-59: Added `get_model()` function and `MODEL` constant
- Line 371: Added `**Model:** {MODEL}` to full markdown report header
- Line 509: Added `Model: {MODEL}` to Signal message output

**Output format:**
```markdown
## Hourly Report - 2026-03-08 20:00
**Model:** claude-opus-4-6
**Generated:** 2026-03-08 20:00:00
...
```

#### 5. report_analyzer.py

**Changes:**
- Line 40-45: Added `get_model()` function and `MODEL` constant
- Line 395: Added `**Model:** {MODEL}` to task completion summary
- Line 459: Added `**Model:** {MODEL}` to system summary

**Output format:**
```markdown
## Task Completion Summary (Last 1h)
**Total Completed:** 5 tasks
**Model:** claude-opus-4-6
**Avg Quality Score:** 8.2/10
...
```

#### 6. reflection_anomaly_scanner.py

**Changes:**
- Line 33-47: Added `get_model()` function and `MODEL` constant
- Model available for anomaly tracking and escalation tasks

#### 7. kublai-actions.py

**Changes:**
- Line 42-47: Added `get_model()` function and `MODEL` constant
- Model available for action tracking and decision logging

## Backward Compatibility

All changes are backward compatible:
- Old tick/tock files without model field still parse correctly
- JSON schemas use optional fields
- Model detection gracefully falls back to "unknown"

## Model Detection by Agent

Different agents can have different models configured:
- main: claude-opus-4-6 (default for cron jobs)
- kublai: glm-5
- mongke: glm-5
- temujin: claude-opus-4-6
- etc.

The cron jobs use the `main` agent's model configuration since they run from the main agent context.

## Files Modified

1. `scripts/get_model.py` (NEW)
2. `scripts/watchdog-gather.sh`
3. `scripts/tock-gather.sh`
4. `scripts/hourly_reflection.sh`
5. `scripts/generate_hourly_report.py`
6. `scripts/report_analyzer.py`
7. `scripts/reflection_anomaly_scanner.py`
8. `scripts/kublai-actions.py`

## Testing

All scripts validated:
- Bash syntax: `bash -n` passes
- Python syntax: `py_compile` passes
- Model detection: Returns correct model from config
- Output format: Verified in code review

## Next Steps

- Monitor tick/tock logs to verify model field appears correctly
- Update dashboards to display model information
- Consider adding model switching detection/alerts
