# Enhanced Task Reporting - Quick Reference

## Overview

The kublai-task-report system has been enhanced to collect comprehensive data for reflections and system improvement. All task completion reports now include detailed metrics across 7 categories.

## Data Collection Categories

### 1. Task Execution
- Token usage (input/output/total)
- Model temperature/effort settings
- Retry count, timeout threshold
- Actual vs estimated time
- Skills invoked, tools/plugins used

### 2. Agent State
- Context window usage %
- Queue depth at start
- Concurrent tasks during execution
- Memory usage
- Health flags (high_queue_depth, high_memory)

### 3. Error Analysis (if failed)
- Error category (auth, timeout, model, network, rate_limit, permission, syntax)
- Error message hash for clustering
- Recovery attempts, fallback models tried
- Retryable flag

### 4. Code/Content Metrics
- Lines added/removed by file type
- Function count
- Class count
- Test count
- Documentation created

### 5. Resource Usage
- CPU time (estimated)
- Memory peak
- API calls (estimated)
- External services detected (stripe, signal, neo4j)

### 6. Quality Signals
- Data quality score (0.0-1.0)
- Files created flag
- Tests written flag
- Documentation flag

### 7. Context Chain
- Parent task ID and title
- Downstream tasks created
- Related tasks (same agent, same day)

## Files Modified/Created

### Modified
- `/Users/kublai/.openclaw/agents/main/scripts/task-report-hook.py`
  - Added comprehensive data collection functions
  - Added Neo4j metrics storage
  - Added ledger event logging

### Created
- `/Users/kublai/.openclaw/agents/main/scripts/task-aggregation.py`
  - Aggregation script for reflection analysis
  - Generates markdown reports from Neo4j data

- `/Users/kublai/.openclaw/agents/main/scripts/neo4j-task-metrics-schema.cypher`
  - Schema migration for new indexes
  - Composite indexes for query performance

## Neo4j Schema

### New Task Properties

```cypher
-- Token usage
t.input_tokens, t.output_tokens, t.total_tokens
t.model, t.temperature, t.context_window_percent

-- Agent state
t.queue_depth, t.pending_tasks, t.executing_tasks
t.memory_mb, t.health_flags

-- Error analysis
t.error_category, t.error_hash, t.is_retryable

-- Code metrics
t.files_created, t.lines_added
t.functions_count, t.classes_count, t.tests_count, t.docs_count

-- Resources
t.cpu_time_seconds, t.memory_peak_mb
t.api_calls_estimate, t.external_services

-- Context
t.parent_task_id, t.parent_title
t.downstream_count, t.related_count

-- Quality
t.data_quality_score, t.report_path
t.duration_seconds, t.duration_minutes, t.efficiency
```

### New Indexes
- 20+ single-property indexes for metrics
- 4 composite indexes for common queries
- 2 fulltext indexes for search

## Usage

### Generate Report (Automatic)
```bash
# Called automatically by task-watcher.py on task completion
python3 task-report-hook.py --task-file /path/to/task.md --status completed
```

### Manual Report Generation
```bash
# With task file
python3 task-report-hook.py --task-file tasks/temujin-high-123.md

# Without task file (manual)
python3 task-report-hook.py --task-id abc123 --agent temujin --status failed --output "Error message"
```

### Aggregation for Reflection
```bash
# Last hour (default)
python3 task-aggregation.py --agent temujin

# Last 24 hours
python3 task-aggregation.py --hours 24 --output workspace/daily-report.md

# Last 7 days
python3 task-aggregation.py --days 7 --output workspace/weekly-report.md

# Failure analysis focus
python3 task-aggregation.py --days 7 --failure-analysis

# JSON output
python3 task-aggregation.py --hours 1 --json
```

### Apply Schema Migration
```bash
# Via cypher-shell
cypher-shell -u neo4j -p <password> < neo4j-task-metrics-schema.cypher

# Via Python
cd /Users/kublai/.openclaw/agents/main/scripts
python3 -c "
from neo4j_task_tracker import get_driver
driver = get_driver()
with open('neo4j-task-metrics-schema.cypher') as f:
    for line in f:
        if line.strip() and not line.startswith('//'):
            try:
                driver.execute_query(line)
            except Exception as e:
                pass  # Ignore already exists errors
driver.close()
print('Schema migration complete')
"
```

## Ledger Event

### TASK_REPORT_GENERATED
```json
{
  "event": "TASK_REPORT_GENERATED",
  "ts": "2026-03-07T23:30:00",
  "task_id": "abc123",
  "agent": "temujin",
  "status": "completed",
  "metrics": {
    "duration_seconds": 180,
    "files_created": 3,
    "lines_added": 150,
    "tokens_total": 12500,
    "status": "completed",
    "error_category": null
  }
}
```

## Aggregation Report Output

### Sample Output Structure
```markdown
# Task Aggregation Report

**Period:** 24 hour(s)
**Agent:** temujin
**Generated:** 2026-03-07 23:30:00

## Executive Summary
- **Total Tasks:** 15
- **Completed:** 12 (80.0%)
- **Failed:** 3
- **Average Duration:** 245s (4.1m)
- **Total Retries:** 5

## Token Usage
- **Total Tokens:** 187,500
- **Input:** 75,000
- **Output:** 112,500
- **Avg per Task:** 12,500
- **Coverage:** 93.3%

## Code & Deliverables
- **Files Created:** 45
- **Lines Added:** 1,234
- **Functions:** 67
- **Classes:** 12
- **Tests:** 8
- **Documentation:** 3
- **Deliverable Rate:** 86.7%

## Error Analysis
- **Total Failures:** 3
- **Unique Errors:** 2

### Error Categories
- **timeout:** 2
- **auth:** 1

## Reflection Prompts
1. **Performance:** What factors contributed to the success rate of 80.0%?
2. **Efficiency:** Are there tasks that took longer than expected?
3. **Errors:** What patterns emerge from the failure analysis?
4. **Token Usage:** Is token efficiency aligned with task complexity?
5. **Deliverables:** Does the deliverable rate meet expectations?
```

## Integration Points

### task-watcher.py
Automatically calls `task-report-hook.py` when tasks complete. No changes needed.

### neo4j_task_tracker.py
TaskTracker class stores all new metrics in `save_metrics_to_neo4j()`.

### prepare_reflection_context.py
Can now query aggregated metrics from `task-aggregation.py` output.

### tock-gather.sh
Can include aggregated metrics in hourly telemetry collection.

## Quality Score Algorithm

```python
quality_score = 0.0
if files_created > 0:      quality_score += 0.3  # Deliverables
if git_files_changed > 0:  quality_score += 0.2  # Code changes
if tests_count > 0:        quality_score += 0.2  # Testing
if docs_count > 0:         quality_score += 0.1  # Documentation
if status == 'completed':  quality_score += 0.2  # Success
# Total: 0.0 - 1.0
```

## Error Categories

| Category | Trigger Keywords | Retryable |
|----------|------------------|-----------|
| auth | auth, 401, unauthorized | No |
| timeout | timeout, timed out | Yes |
| model | model, invalid model | No |
| network | network, connection, 503 | Yes |
| rate_limit | rate limit, 429 | Yes |
| permission | permission, denied | No |
| syntax | syntax, parse | No |

## Monitoring

### Check Data Quality
```bash
# Check token data coverage
python3 task-aggregation.py --hours 24 --json | jq '.token_usage.token_data_coverage'

# Check error category distribution
cypher-shell -u neo4j -p <password> \
  "MATCH (t:Task) WHERE t.error_category IS NOT NULL RETURN t.error_category, count(*)"
```

### Verify Schema
```bash
cypher-shell -u neo4j -p <password> \
  "SHOW INDEXES WHERE name CONTAINS 'task_'"
```

## Troubleshooting

### Neo4j Connection Failed
Check credentials in `~/.openclaw/credentials/neo4j.env`

### Token Usage Missing
Verify session files exist in `/Users/kublai/.openclaw/agents/<agent>/sessions/`

### Git Diff Empty
Ensure agent workspace is a git repository

### psutil Import Error
```bash
pip3 install psutil
```

---

*Generated: 2026-03-07*
*Enhanced Task Reporting v2.0*
