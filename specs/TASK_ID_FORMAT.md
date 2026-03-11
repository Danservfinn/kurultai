# Task ID Format Specification

**Version:** 1.0
**Date:** 2026-03-10
**Status:** Active

---

## Overview

This specification defines the canonical format for task identifiers in the Kurultai task system. All tasks MUST use this format for consistency, traceability, and Neo4j indexing.

---

## Task ID Format

### Canonical Format

```
{priority}-{timestamp}-{uuid8}
```

Where:
- **priority**: `critical`, `high`, `normal`, or `low` (lowercase)
- **timestamp**: Unix timestamp (10 digits, seconds since epoch)
- **uuid8**: First 8 characters of UUID4 (lowercase hex)

### Examples

| Priority | Example ID |
|----------|------------|
| critical | `critical-1773121500-a1b2c3d4` |
| high | `high-1773121555-5e6f7g8h` |
| normal | `normal-1773121600-1a2b3c4d` |
| low | `low-1773121650-9z8y7x1a` |

### Validation Regex

```python
TASK_ID_PATTERN = re.compile(r'^(critical|high|normal|low)-\d{10}-[a-f0-9]{8}$')
```

---

## Task Lifecycle

### State Flow

```
PENDING → EXECUTING → COMPLETED
                    → FAILED → RETRY(n) → FAILED_FINAL
                    → TIMEOUT
                    → CANCELLED
```

### State Definitions

| State | Meaning | Transitions To |
|-------|---------|----------------|
| `PENDING` | Queued, waiting for execution | EXECUTING, CANCELLED |
| `EXECUTING` | Currently being processed | COMPLETED, FAILED, TIMEOUT |
| `COMPLETED` | Successfully finished | (terminal) |
| `FAILED` | Execution failed | PENDING (retry), FAILED_FINAL |
| `FAILED_FINAL` | Max retries exceeded | (terminal) |
| `TIMEOUT` | Exceeded time limit | PENDING (retry), FAILED_FINAL |
| `CANCELLED` | Explicitly cancelled | (terminal) |

---

## File Naming Convention

### Task Files

Task files in agent task directories (`/agents/{agent}/tasks/`) follow this pattern:

```
{priority}-{timestamp}-{uuid8}.md
```

**Example:** `high-1773121555-5e6f7g8h.md`

### File Extensions (DEPRECATED)

The following file extensions are **DEPRECATED** and should not be used:

| Extension | Old Meaning | New Approach |
|-----------|-------------|--------------|
| `.done` | Completed | Check Neo4j `status` property |
| `.failed` | Failed | Check Neo4j `status` property |
| `.retry.md` | Retry pending | Check Neo4j `retry_count` property |
| `.executing` | In progress | Check Neo4j `status` property |

**Migration:** Existing files with these extensions should be renamed to remove the extension. The task's state is tracked in Neo4j, not in the filename.

---

## Neo4j Schema

### Task Node Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `task_id` | string | Yes | Unique identifier (canonical format) |
| `title` | string | Yes | Human-readable title |
| `body` | string | No | Task description |
| `status` | string | Yes | Current state (PENDING, EXECUTING, etc.) |
| `priority` | string | Yes | critical, high, normal, low |
| `agent` | string | Yes | Assigned agent name |
| `created` | datetime | Yes | Creation timestamp |
| `started` | datetime | No | Execution start timestamp |
| `completed` | datetime | No | Completion timestamp |
| `retry_count` | int | No | Number of retry attempts (default: 0) |
| `error` | string | No | Error message if failed |
| `session_key` | string | No | Claim session key during execution |
| `skill_hint` | string | No | Suggested skill for execution |
| `source` | string | No | Task origin (kublai-actions, stall-detector, etc.) |

### Constraints & Indexes

```cypher
-- Unique constraint on task_id
CREATE CONSTRAINT task_id_unique IF NOT EXISTS
FOR (t:Task) REQUIRE t.task_id IS UNIQUE;

-- Index for status+agent queries (pending tasks by agent)
CREATE INDEX task_status_agent IF NOT EXISTS
FOR (t:Task) ON (t.status, t.agent);

-- Index for creation time ordering
CREATE INDEX task_created IF NOT EXISTS
FOR (t:Task) ON (t.created);
```

---

## Implementation Requirements

### task_intake.py

1. **generate_task_id(priority)** - Generate ID in canonical format
2. **validate_task_id(task_id)** - Return True if matches pattern
3. **create_task()** - Generate valid task_id before Neo4j write

### neo4j_task_tracker.py

1. **create_task_full()** - Accept and store task_id in canonical format
2. Reject task_id that doesn't match pattern (with warning)

### kurultai_ledger.py

1. **append_ledger()** - Validate task_id format before writing
2. Log warning for invalid formats (but still write for audit)

### task-watcher.py

1. Query Neo4j for pending tasks (primary source)
2. Use filesystem scan as fallback only
3. Do NOT add file extensions for state tracking

---

## Migration Guide

### For Existing Tasks

1. Tasks with old format IDs (e.g., `fs-1773121357`, `normal-1773121358`) remain valid
2. New tasks MUST use canonical format
3. Migration script available to rename old-format files

### For Existing Code

1. Update `generate_task_id()` calls to include priority parameter
2. Add `validate_task_id()` checks at task creation boundaries
3. Remove file extension logic from state tracking

---

## References

- Architecture documentation: `/agents/main/docs/architecture.md`
- Neo4j atomic transitions: `/scripts/neo4j_atomic_transitions.py`
- Task intake: `/scripts/task_intake.py`
