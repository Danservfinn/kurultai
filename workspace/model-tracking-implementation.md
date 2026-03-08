# LLM Model Tracking Implementation

## Summary

Implemented comprehensive LLM model tracking per agent for success measurement. The system now tracks which LLM model each agent uses and measures success rates.

## Components Implemented

### 1. Task Report Hook Updates (`task-report-hook.py`)

**File**: `/Users/kublai/.openclaw/agents/main/scripts/task-report-hook.py`

**Changes**:
- Updated `scan_session_file()` to extract `model_id` and `model_provider` from session files
- Session files contain `type: "model_change"` events with `provider` and `modelId` fields
- Updated `save_metrics_to_neo4j()` to set model tracking properties:
  - `t.model_id` - e.g., "glm-5"
  - `t.model_provider` - e.g., "zai-coding"
  - `t.model_success` - boolean (derived from task status)
  - `t.model_duration_seconds` - task execution time
- Added `MODEL_USED` ledger event with:
  - task_id, agent, model_id, model_provider, model_full
  - success, duration_seconds, tokens_total

### 2. Model Tracker CLI (`model-tracker.py`)

**File**: `/Users/kublai/.openclaw/agents/main/scripts/model-tracker.py`

**CLI Usage**:
```bash
# Show overall summary
python3 model-tracker.py --summary --days 7

# Per-agent breakdown
python3 model-tracker.py --by-agent --days 7

# Per-provider breakdown
python3 model-tracker.py --by-provider --days 7

# Compare two models
python3 model-tracker.py --compare zai-coding/glm-5 bailian/kimi-k2.5

# Export to JSONL
python3 model-tracker.py --export model-stats.jsonl --days 30

# Show error breakdown
python3 model-tracker.py --errors --days 7

# Output as JSON
python3 model-tracker.py --summary --json --days 7
```

**Python API**:
```python
from model_tracker import get_tracker
tracker = get_tracker()

# Get model stats
stats = tracker.get_model_stats(days=7)

# Get per-agent breakdown
agent_stats = tracker.get_agent_model_stats(days=7)

# Get provider stats
provider_stats = tracker.get_provider_stats(days=7)

# Get error breakdown
errors = tracker.get_model_error_breakdown(days=7)

tracker.close()
```

### 3. Model Analytics API (`model-analytics-api.py`)

**File**: `/Users/kublai/.openclaw/agents/main/scripts/model-analytics-api.py`

**HTTP Server**:
```bash
# Start API server
python3 model-analytics-api.py --serve --port 8080

# Endpoints:
GET /api/analytics/models?days=7&agent=temujin
GET /api/analytics/models/recent?limit=50
GET /health
```

**CLI**:
```bash
# Get stats
python3 model-analytics-api.py --stats --days 7

# Get recent usage
python3 model-analytics-api.py --recent --limit 50
```

### 4. Tock Data Integration

**File**: `/Users/kublai/.openclaw/agents/main/scripts/tock-gather.sh`

The tock-gather script already includes model stats queries:
- `model_stats` - per-model success rates and duration
- `agent_model_stats` - per-agent per-model breakdown

## Data Flow

```
┌─────────────────┐
│ Agent Session   │
│ (model_change)  │
└────────┬────────┘
         │
         ▼
┌─────────────────────────┐
│ task-report-hook.py     │
│ - scan_session_file()   │
│ - extract model_id      │
│ - extract model_provider│
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ Neo4j Task Node         │
│ - model_id              │
│ - model_provider        │
│ - model_success         │
│ - model_duration_seconds│
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ Ledger (MODEL_USED)     │
│ + JSONL Log             │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ Analytics & Reporting   │
│ - model-tracker.py      │
│ - model-analytics-api   │
│ - tock-gather.sh        │
└─────────────────────────┘
```

## Storage

1. **Neo4j**: Task nodes have model properties
2. **JSONL Log**: `/Users/kublai/.openclaw/agents/main/logs/model-usage.jsonl`
3. **Task Ledger**: MODEL_USED events in `task-ledger.jsonl`

## Verification

To verify data collection after next task completion:

```bash
# Check Neo4j for model properties
python3 << 'PY'
from neo4j import GraphDatabase
import os
driver = GraphDatabase.driver(
    os.getenv('NEO4J_URI', 'bolt://localhost:7687'),
    auth=(os.getenv('NEO4J_USER', 'neo4j'), os.getenv('NEO4J_PASSWORD', 'myStrongPassword123'))
)
with driver.session() as session:
    result = session.run("""
        MATCH (t:Task)
        WHERE t.model_id IS NOT NULL
        RETURN t.task_id, t.agent, t.model_provider, t.model_id, t.model_success
        ORDER BY t.created DESC
        LIMIT 5
    """)
    for r in result:
        print(r)
driver.close()
PY

# Check ledger for MODEL_USED events
grep 'MODEL_USED' ~/.openclaw/tasks/task-ledger.jsonl | tail -3
```

## Priority Reason

The kimi-k2.5 proxy failures highlighted the need for systematic model tracking to:
1. Identify which models are failing
2. Measure success rates per model
3. Compare model performance for optimization decisions
4. Provide data for model configuration decisions
