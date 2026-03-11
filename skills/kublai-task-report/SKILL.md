---
name: kublai-task-report
description: Comprehensive task data collection and reporting for reflections and system improvement. Use when generating task completion reports, aggregating metrics for hourly reflections, analyzing error patterns, or tracking agent performance over time. Automatically collects token usage, execution timing, code changes, resource usage, quality signals, and context chain data.
---

# Kublai Task Report

## Overview

Generate comprehensive task completion reports with detailed metrics across 7 data categories. Enable hourly reflections, daily system improvements, and weekly trend analysis through structured data collection in Neo4j.

**When to use:**
- After task completion to log execution metrics
- For hourly/daily/weekly reflection data generation
- When analyzing error patterns or agent performance
- For system improvement insights and trend detection

## Core Capabilities

### 1. Task Execution Metrics

Collect detailed execution data for every completed task:

**Token Usage**
- Input tokens, output tokens, total tokens
- Token cost estimation in USD
- Model-specific pricing (Opus, Sonnet, Haiku)

**Model Settings**
- Model temperature
- Model effort level (low, medium, high)
- Context window usage percentage

**Timing Data**
- Actual duration vs estimated duration
- Retry count
- Timeout threshold
- Skills invoked during execution

**Tools Tracking**
- Tool usage counts by type
- Plugin invocations

### 2. Agent State Snapshot

Capture agent state at task start and completion:

- Context window usage percentage
- Memory state hashes (before/after)
- Queue depth at task start
- Concurrent tasks during execution
- Health flags (stressed, normal, idle)

### 3. Error Analysis

Categorize and cluster failures for pattern detection:

**Error Categories**
- timeout, auth, model, network, rate_limit, permission, syntax, verification, unknown

**Error Clustering**
- SHA256 hash of error messages for grouping
- Recovery attempts count
- Fallback models tried
- Recovery success flag

### 4. Code and Content Metrics

Track deliverables and code changes:

**Line Counts**
- Lines added/removed (total)
- Code lines added (.py, .js, .ts, etc.)
- Documentation lines added (.md, .txt)
- Test lines added (test_*.py, *.test.js)

**File Changes**
- Files created, modified, deleted
- Function count delta
- Class count delta
- Cyclomatic complexity delta

**Coverage Tracking**
- Test coverage before/after
- Documentation count

### 5. Resource Usage

Monitor system resource consumption:

- CPU time (seconds)
- CPU peak percentage
- Memory peak/average (MB)
- API call count
- API calls by service (stripe, signal, neo4j, etc.)
- Network I/O (bytes in/out)
- Disk I/O (read/write MB)

### 6. Quality Signals

Track output quality and verification:

- Verification checks passed/failed
- Verification score (0-100)
- Rework required flag
- Follow-up tasks created
- Rework reason

### 7. Context Chain

Maintain task relationship graph:

- Parent task ID and title
- Triggered by event
- Root cause task ID
- Downstream tasks created
- Related task IDs (by keyword/graph similarity)
- Task graph depth

## Usage

### Python API

```python
from kublai_task_report import TaskReporter

reporter = TaskReporter()

# Record execution metrics
reporter.record_task_execution(task_id, agent, {
    "input_tokens": 5000,
    "output_tokens": 2000,
    "total_tokens": 7000,
    "model_temperature": 0.7,
    "actual_duration_seconds": 180,
    "skills_invoked": ["horde-brainstorming"],
    "tools_used": {"Read": 5, "Write": 2}
})

# Record agent state
reporter.record_agent_state(agent, {
    "context_window_percent": 45.2,
    "queue_depth_at_start": 3,
    "concurrent_tasks": 1,
    "health_flags": ["normal"]
})

# Record errors if failed
reporter.record_error(task_id, {
    "error_category": "timeout",
    "error_message": "Task timed out after 120s",
    "recovery_attempts": 1,
    "fallback_models_tried": ["claude-sonnet-4-6"]
})

# Generate comprehensive report
report = reporter.generate_task_report(task_id)
```

### CLI

```bash
# Generate report for specific task
python3 kublai_task_report.py --task-id abc123

# Aggregate by agent (last 24 hours)
python3 kublai_task_report.py --agent temujin --hours 24

# Error category analysis
python3 kublai_task_report.py --errors --hours 168

# Skill usage analysis
python3 kublai_task_report.py --skills --hours 168

# Error clustering
python3 kublai_task_report.py --clusters --hours 168

# Reflection summary (default)
python3 kublai_task_report.py --reflection --hours 1
```

### Aggregation for Reflections

```python
from task_report_aggregator import TaskReportAggregator

aggregator = TaskReportAggregator()

# Generate reflection data
data = aggregator.generate_reflection_data(agent="temujin", hours=1)

# Generate daily report
report = aggregator.generate_daily_report()

# Weekly trend analysis
trends = aggregator.generate_weekly_trends(days=30)
```

## Data Categories

### Neo4j Schema Properties

**Task Execution**
- `input_tokens`, `output_tokens`, `total_tokens`, `token_cost_usd`
- `model_temperature`, `model_effort`
- `retry_count`, `timeout_threshold`
- `actual_duration_seconds`, `estimated_duration_seconds`
- `skills_invoked`, `tools_used`

**Agent State**
- `context_window_percent`
- `memory_state_before`, `memory_state_after`
- `queue_depth_at_start`, `concurrent_tasks`
- `health_flags`

**Error Analysis**
- `error_category`, `error_message_hash`, `error_message_truncated`
- `recovery_attempts`, `fallback_models_tried`, `recovery_success`

**Code/Content**
- `lines_added`, `lines_removed`
- `files_modified`, `files_created`, `files_deleted`
- `code_lines_added`, `doc_lines_added`, `test_lines_added`
- `test_coverage_before`, `test_coverage_after`
- `cyclomatic_complexity_delta`, `function_count_delta`

**Resource Usage**
- `cpu_time_seconds`, `cpu_peak_percent`
- `memory_peak_mb`, `memory_avg_mb`
- `api_calls_count`, `api_calls_by_service`
- `network_bytes_in`, `network_bytes_out`
- `disk_read_mb`, `disk_write_mb`

**Quality Signals**
- `verification_checks_passed`, `verification_checks_failed`
- `verification_score`
- `rework_required`, `followup_tasks_created`, `rework_reason`

**Context Chain**
- `parent_task_id`, `triggered_by_event`, `root_cause_task_id`
- `downstream_tasks`, `related_task_ids`, `task_graph_depth`

## Indexes

The following Neo4j indexes are created for efficient queries:

**Single-Property Indexes**
- Token usage: `input_tokens`, `output_tokens`, `total_tokens`
- Model: `model`, `model_temperature`
- Agent state: `context_window_percent`, `queue_depth`, `memory_mb`
- Error analysis: `error_category`, `error_hash`, `is_retryable`
- Code metrics: `files_created`, `lines_added`, `functions_count`, `classes_count`, `tests_count`
- Quality: `data_quality_score`
- Resources: `cpu_time_seconds`
- Context: `parent_task_id`

**Composite Indexes**
- `agent + status + created` (hourly reflections)
- `agent + date(created)` (daily aggregations)
- `error_category + status` (failure analysis)
- `skill_hint + created` (skill usage analysis)

**Fulltext Indexes**
- Error search: `error_category`, `error_hash`
- Deliverables search: `title`, `body`

## Resources

### scripts/kublai-task-report.py

Core TaskReporter class with methods for:
- Recording task execution metrics
- Recording agent state snapshots
- Recording error analysis
- Recording code/content changes
- Recording resource usage
- Recording quality signals
- Recording context chain relationships
- Generating comprehensive task reports
- Aggregation queries (by agent, error category, skill)

### scripts/task_report_aggregator.py

TaskReportAggregator class for:
- Reflection data generation
- Daily report generation
- Weekly trend analysis
- Error pattern analysis
- Performance trend analysis
- Quality signal analysis
- Recommendation generation
- JSON/CSV export

### scripts/task-report-hook.py

Integration hook called by task-watcher.py on task completion:
- Parses task files for metadata
- Scans session files for token data
- Collects git diff statistics
- Generates markdown completion reports
- Logs TASK_REPORT_GENERATED events to ledger
- Stores metrics in Neo4j

### scripts/neo4j-task-metrics-schema.cypher

Schema migration script for:
- Creating all required indexes
- Creating constraints for uniqueness
- Setting up fulltext search indexes
- Sample validation queries

### references/

No reference documentation needed - all information is in this SKILL.md.

### assets/

No asset files needed for this skill.
