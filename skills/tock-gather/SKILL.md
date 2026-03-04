# Tock Gather (30-Minute Agent Metrics)

**Model:** lmstudio/qwen3.5-9b-mlx (local)
**Schedule:** Every 30 minutes
**Log:** ~/.openclaw/agents/main/logs/tock.log
**Data:** ~/.openclaw/agents/main/logs/tock/latest.json

## Purpose

You execute the tock data collection script. This gathers agent effectiveness
metrics every 30 minutes to feed the hourly kurultai-reflection. The bash
script does all data collection and calls the local LLM directly for assessment.

## Step 1: Execute

```bash
bash ~/.openclaw/agents/main/scripts/tock-gather.sh
```

## Step 2: Verify

Check that output was created:

```bash
tail -1 ~/.openclaw/agents/main/logs/tock.log
```

## Step 3: Report

Output the last line of tock.log. If the script failed, output the error.

## Rules

- The script does ALL work including the LLM assessment call. Do not duplicate.
- Do not modify output files.
- If the script fails, report the error. Do not retry.
