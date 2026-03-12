---
plan_manifest:
  version: "1.0"
  created_by: "horde-plan"
  plan_name: "Fix Task Failure Patterns"
  total_phases: 4
  total_tasks: 12
  phases:
    - id: "1"
      name: "Ledger Schema Updates"
      task_count: 2
      parallelizable: false
      gate_depth: "STANDARD"
    - id: "2"
      name: "R008 Enforcement Hardening"
      task_count: 4
      parallelizable: true
      gate_depth: "STANDARD"
    - id: "3"
      name: "Timeout Calibration"
      task_count: 3
      parallelizable: true
      gate_depth: "LIGHT"
    - id: "4"
      name: "Task Intake File Naming"
      task_count: 3
      parallelizable: true
      gate_depth: "NONE"
  task_transfer:
    mode: "transfer"
    task_ids: []
---

# Fix Task Failure Patterns Implementation Plan

> **Plan Status:** Ready for Execution
> **Created:** 2026-03-11
> **Estimated Tasks:** 12
> **Estimated Phases:** 4

## Overview

**Goal:** Fix the root causes of task failures in the Kurultai multi-agent system by addressing ledger schema validation, R008 skill enforcement, timeout calibration, and file naming conventions.

**Architecture:** Four-phase approach targeting the highest-impact issues first (schema), then hardening enforcement (R008), then optimizing system parameters (timeouts), finally cleaning up file naming (task intake).

**Tech Stack:** Python, kurultai_ledger.py, agent-task-handler.py, task-watcher.py, task_intake.py

## Phase 1: Ledger Schema Updates
**Duration**: 30-45 minutes
**Dependencies**: None
**Parallelizable**: No (sequential updates)

### Task 1.1: Add AUTH_PREFLIGHT_FAIL Event Type
**Dependencies**: None

Add `AUTH_PREFLIGHT_FAIL` to the `VALID_EVENTS` set in kurultai_ledger.py. This event is emitted when credential pre-flight checks fail.

```python
# File: /Users/kublai/.openclaw/agents/main/scripts/kurultai_ledger.py
# Line ~59: Add after "R008_PREFLIGHT_FAIL":

# Before:
    "R008_VIOLATION", "R008_PREFLIGHT_FAIL",

# After:
    "R008_VIOLATION", "R008_PREFLIGHT_FAIL", "AUTH_PREFLIGHT_FAIL",
```

**Files:**
- Modify: `/Users/kublai/.openclaw/agents/main/scripts/kurultai_ledger.py`

**Acceptance Criteria:**
- [ ] `AUTH_PREFLIGHT_FAIL` appears in VALID_EVENTS set
- [ ] Ledger validation no longer rejects this event type

### Task 1.2: Add AUTH_PREFLIGHT_FAIL to SYSTEM_EVENTS
**Dependencies**: Task 1.1

Add `AUTH_PREFLIGHT_FAIL` to `SYSTEM_EVENTS` set since auth pre-flight failures don't require task_id (they're system-level events).

```python
# File: /Users/kublai/.openclaw/agents/main/scripts/kurultai_ledger.py
# Line ~67: Add after SESSION_RESET:

# Before:
    "SESSION_AUTO_CLEANUP", "SESSION_RESET",

# After:
    "SESSION_AUTO_CLEANUP", "SESSION_RESET", "AUTH_PREFLIGHT_FAIL",
```

**Files:**
- Modify: `/Users/kublai/.openclaw/agents/main/scripts/kurultai_ledger.py`

**Acceptance Criteria:**
- [ ] `AUTH_PREFLIGHT_FAIL` appears in SYSTEM_EVENTS
- [ ] Auth pre-flight events don't trigger "Event without valid task_id" warnings

### Exit Criteria Phase 1
- [ ] `python3 -c "from kurultai_ledger import VALID_EVENTS; print('AUTH_PREFLIGHT_FAIL' in VALID_EVENTS)"` exits 0
- [ ] `python3 -c "from kurultai_ledger import SYSTEM_EVENTS; print('AUTH_PREFLIGHT_FAIL' in SYSTEM_EVENTS)"` exits 0
- [ ] Ledger validation tests pass (if they exist)

## Phase 2: R008 Enforcement Hardening
**Duration**: 45-60 minutes
**Dependencies**: Phase 1
**Parallelizable**: Yes (independent changes)

### Task 2.1: Verify kurultai-health Skill Exists
**Dependencies**: None

Check if the `/kurultai-health` skill exists and is properly configured.

```bash
ls -la ~/.claude/skills/kurultai-health/SKILL.md 2>/dev/null || head -20
cat ~/.claude/skills/kurultai-health/SKILL.md 2>/dev/null
# Expected: Skill file exists with valid SKILL.md
```

**Files:**
- Read: `~/.claude/skills/kurultai-health/SKILL.md`

**Acceptance Criteria:**
- [ ] Skill file exists
- [ ] SKILL.md contains valid skill definition

### Task 2.2: Add R008_PREFLIGHT_CHECK Event Emission
**Dependencies**: Task 1.1

Add pre-flight check event emission to agent-task-handler.py to track when R008 pre-flight checks run. This helps identify why tasks fail early.

```python
# File: /Users/kublai/.openclaw/agents/main/scripts/agent-task-handler.py
# In _check_skill_invocation_early() function, around line 1901:

# Add event emission when pre-flight check fails:
if not skill_invoked:
    _append_ledger({
        "event": "R008_PREFLIGHT_CHECK",
        "ts": datetime.now().isoformat(),
        "agent": agent_name,
        "task_id": None,  # Will be added by caller
        "skill_hint": skill_hint,
        "skills_invoked": [],
        "preflight_elapsed": R008_PREFLIGHT_ELAPSED,
        "status": "FAIL"
    })
```

**Files:**
- Modify: `/Users/kublai/.openclaw/agents/main/scripts/agent-task-handler.py`

**Acceptance Criteria:**
- [ ] R008_PREFLIGHT_CHECK events appear in ledger when pre-flight fails
- [ ] Events include skill_hint and elapsed time, and agent info

### Task 2.3: Add API Latency Buffer to Timeout Calculation
**Dependencies**: None

Add API latency buffer to task timeout calculation to account for model response time.

```python
# File: /Users/kublai/.openclaw/agents/main/scripts/task-watcher.py
# In _timeout_for_task() function, around line 1004:

# Add API latency buffer:
API_LATENCY_BUFFER = 300  # 5 minutes for API response delays

return max(priority_timeout, skill_timeout) + API_LATENCY_BUFFER
```

**Files:**
- Modify: `/Users/kublai/.openclaw/agents/main/scripts/task-watcher.py`
- Modify: `/Users/kublai/.openclaw/agents/main/scripts/agent-task-handler.py` (same constant)

**Acceptance Criteria:**
- [ ] API_LATENCY_BUFFER constant defined
- [ ] Timeout calculation includes buffer
- [ ] Tasks get extra 5 minutes before timeout

### Task 2.4: Add Early Warning Before SIGKILL
**Dependencies**: Task 2.3

Add warning log 30 seconds before timeout to allow investigation.

```python
# File: /Users/kublai/.openclaw/agents/main/scripts/task-watcher.py
# In execute_task() function, around line 1262:

# Add timeout warning at30 seconds before kill:
TIMEOUT_WARNING_SECONDS = 30

def timeout_warning_handler(signum, frame):
    proc.send_signal(signal.SIGTERM)  # Graceful warning first

# Then in the except subprocess.TimeoutExpired block:
    if timeout > TIMEOUT_WARNING_SECONDS:
        log(f"  ⚠️ TIMEOUT WARNING: Task approaching {timeout}s limit")
        # Give 30 seconds for graceful handling before SIGKILL
        time.sleep(30)
```

**Files:**
- Modify: `/Users/kublai/.openclaw/agents/main/scripts/task-watcher.py`

**Acceptance Criteria:**
- [ ] Warning logged 30 seconds before SIGKILL
- [ ] SIGTERM sent before SIGKILL
- [ ] Logs show warning message

### Exit Criteria Phase 2
- [ ] kurultai-health skill exists and- [ ] R008_PREFLIGHT_CHECK events appear in ledger
- [ ] API latency buffer added to timeout calculation
- [ ] Early warning logged before SIGKILL
- [ ] Manual test: Create task with skill_hint, verify proper event emission

## Phase 3: Timeout Calibration
**Duration**: 30-45 minutes
**Dependencies**: Phase 1
**Parallelizable**: Yes

### Task 3.1: Add Timeout Metrics Logging
**Dependencies**: None

Add detailed timeout metrics to ledger for analysis.

```python
# File: /Users/kublai/.openclaw/agents/main/scripts/task-watcher.py
# In execute_task() function, when task times out:

# Add timeout metrics to ledger:
_append_ledger({
    "event": "TASK_TIMEOUT",
    "ts": datetime.now().isoformat(),
    "agent": agent,
    "task_id": task_id,
    "timeout_seconds": timeout,
    "elapsed_seconds": elapsed_s,
    "exit_code": proc.returncode
})
```

**Files:**
- Modify: `/Users/kublai/.openclaw/agents/main/scripts/task-watcher.py`

**Acceptance Criteria:**
- [ ] TASK_TIMEOUT events appear in ledger
- [ ] Events include timeout_seconds, elapsed_seconds, exit_code

### Task 3.2: Add TASK_TIMEOUT to VALID_EVENTS
**Dependencies**: Task 3.1

Add `TASK_TIMEOUT` to ledger schema.

```python
# File: /Users/kublai/.openclaw/agents/main/scripts/kurultai_ledger.py
# Line ~62: Add after "TEST_EVENT":

    "TASK_TIMEOUT",
```

**Files:**
- Modify: `/Users/kublai/.openclaw/agents/main/scripts/kurultai_ledger.py`

**Acceptance Criteria:**
- [ ] TASK_TIMEOUT in VALID_EVENTS
- [ ] No validation errors for timeout events

### Task 3.3: Add Timeout Configuration Documentation
**Dependencies**: Task 3.2

Document timeout configuration for behavior.

```markdown
# File: /Users/kublai/.openclaw/agents/main/docs/timeout-configuration.md

# Create if doesn't exist

## Timeout Configuration

### Priority Timeouts
- High: 7200s (2 hour)
- Normal: 7200s (1 hour)
- Low: 7200s (1 hour)

### Skill-Specific Timeouts
Skills that require extra time:
- /horde-brainstorming: +7200s
- /golden-horde: +7200s
- /horde-implement: +7200s
- /horde-review: +7200s

### API Latency Buffer
All timeouts include +300s API latency buffer to account for:
- Model response delays
- Rate limiting backoff
- Network latency

### Timeout Enforcement
1. Warning at 30s before hard limit
2. SIGTERM (graceful shutdown)
3. SIGKILL (forceful termination)
```

**Files:**
- Create: `/Users/kublai/.openclaw/agents/main/docs/timeout-configuration.md`

**Acceptance Criteria:**
- [ ] Documentation file exists
- [ ] Contains timeout values and buffer, and enforcement steps

### Exit Criteria Phase 3
- [ ] TASK_TIMEOUT events logged to ledger
- [ ] Timeout metrics available for analysis
- [ ] Documentation updated

- [ ] Manual test: Run long task, verify timeout events

## Phase 4: Task Intake File Naming
**Duration**: 30-45 minutes
**Dependencies**: Phase 1
**Parallelizable**: Yes

### Task 4.1: Define Valid Task File Extensions
**Dependencies**: None

Define explicit list of valid task file extensions in task_intake.py.

```python
# File: /Users/kublai/.openclaw/agents/main/scripts/task_intake.py
# Add near top after imports:

VALID_TASK_EXTENSIONS = {
    '.md',           # Standard markdown task files
    '.pending.md',    # Pending state
    '.executing.md',  # Currently executing
    '.done.md',       # Completed tasks
    '.failed.md',     # Failed tasks
}
```

**Files:**
- Modify: `/Users/kublai/.openclaw/agents/main/scripts/task_intake.py`

**Acceptance Criteria:**
- [ ] VALID_TASK_EXTENSIONS constant defined
- [ ] Contains exactly 5 extensions

### Task 4.2: Add Extension Validation to Glob Patterns
**Dependencies**: Task 4.1

Update glob patterns to filter out invalid file extensions.

```python
# File: /Users/kublai/.openclaw/agents/main/scripts/task_intake.py
# In has_pending_task() function, around line 2283:

# Replace glob pattern to filter valid extensions only:
valid_extensions = tuple(VALID_TASK_EXTENSIONS)
pattern = f"{prefix}*{''.join(valid_extensions)}"
for fpath in task_dir.glob(pattern):
    ...
```

**Files:**
- Modify: `/Users/kublai/.openclaw/agents/main/scripts/task_intake.py`

**Acceptance Criteria:**
- [ ] Glob patterns only match valid extensions
- [ ] Invalid files (.revision-1.md, .resolved.md, etc.) ignored

- [ ] No false positives from intermediate state files

### Task 4.3: Add File Naming Cleanup Function
**Dependencies**: Task 4.2

Add function to rename non-standard files to standard format.

```python
# File: /Users/kublai/.openclaw/agents/main/scripts/task_intake.py
# Add new function:

def normalize_task_filename(filename: str) -> str:
    """Normalize task filename to standard format.

    Standard formats:
    - {task_id}.md (pending)
    - {task_id}.executing.md (in progress)
    - {task_id}.done.md (completed)
    - {task_id}.failed.md (failed)

    Non-standard patterns to clean up:
    - .completed.revision-1.md -> .done.md
    - .resolved.md -> .done.md
    - .false-positive.md -> remove or keep .done.md
    """
    import re

    # Remove revision suffixes
    filename = re.sub(r'\.revision-\d+', '', filename)

    # Standardize status suffixes
    filename = re.sub(r'\.completed', '.done', filename)
    filename = re.sub(r'\.resolved', '.done', filename)
    filename = re.sub(r'\.false-positive', '', filename)  # Remove, will keep .done.md

    return filename
```

**Files:**
- Modify: `/Users/kublai/.openclaw/agents/main/scripts/task_intake.py`

**Acceptance Criteria:**
- [ ] normalize_task_filename() function exists
- [ ] Handles revision suffixes
- [ ] Standardizes status suffixes

### Exit Criteria Phase 4
- [ ] VALID_TASK_EXTENSIONS defined
- [ ] Glob patterns filter invalid extensions
- [ ] normalize_task_filename() function available
- [ ] Manual test: Create files with non-standard names
 verify they're filtered out

## Dependency Graph

```
Phase 1 (Ledger Schema) — gate: STANDARD
    └── Phase 2 (R008 Enforcement) — gate: STANDARD
        └── Phase 4 (File Naming) — gate: NONE,    └── Phase 3 (Timeout) — gate: LIGHT,        └── Phase 4 (File Naming) — gate: NONE (can run parallel)
```

## Appendix A: Root Cause Analysis

> **Analysis Date:** 2026-03-11
> **Confidence:** High

### Primary Findings

1. **R008 Violations (24 events)**: Agents not invoking required skills despite mandatory instruction. Root cause: Enforcement is post-hoc (after task completes) rather than blocking skill invocation at the prompt.

2. **SIGKILL/SIGTERM (16 events)**: Tasks being forcefully killed. Root cause: Timeout enforcement doesn't account for API latency, causing tasks to exceed timeout before skill invocation completes.

3. **Ledger Schema Errors**: Invalid event types causing validation warnings. Root cause: Schema hasn't been updated to include new R008/AUTH events.

4. **File Naming Confusion**: Non-standard file suffixes causing queue state issues.

### Contributing Factors

- `/kurultai-health` skill (12 R008 violations) - most common skill hint
- Timeout calculation doesn't include API latency buffer
- No early warning before SIGKILL

### Recommended Approach

1. **Schema First**: Add missing event types to prevent validation errors
2. **Hardening R008**: Make skill invocation enforcement more robust
3. **Timeout Tuning**: Add API latency buffer and early warnings
4. **File Cleanup**: Standardize file naming conventions

## Appendix B: Testing Checklist

### Unit Tests
- [ ] Test AUTH_PREFLIGHT_FAIL in VALID_EVENTS
- [ ] Test TASK_TIMEOUT in VALID_EVENTS
- [ ] Test normalize_task_filename() function
- [ ] Test API latency buffer calculation

### Integration Tests
- [ ] Create task with skill_hint, verify R008_PREFLIGHT_CHECK event
- [ ] Run task that exceeds timeout
 verify TASK_TIMEOUT event
- [ ] Create task files with non-standard names
 verify they're filtered

### Manual Verification
```bash
# Verify schema updates
python3 -c "from kurultai_ledger import VALID_EVENTS; print(sorted(VALID_EVENTS))"

# Verify timeout configuration
python3 -c "from task_watcher import TIMEOUT_DEFAULT, API_LATENCY_BUFFER; print(f'Default: {TIMEOUT_DEFAULT}s, Buffer: {API_LATENCY_BUFFER}s')"

# Test file naming
python3 -c "from task_intake import VALID_TASK_EXTENSIONS; print(sorted(VALID_TASK_EXTENSIONS))"
```

## Appendix C: Files to Modify

| File | Lines to Change | Phase |
|------|----------------|-------|
| kurultai_ledger.py | ~60 | 1 |
| agent-task-handler.py | ~20 | 2 |
| task-watcher.py | ~40 | 2, 3 |
| task_intake.py | ~50 | 4 |
| timeout-configuration.md | New | 3 |

## Appendix D: Risk Assessment

### Low Risk
- Ledger schema changes: Add-only, backward compatible
- Documentation changes: Non-code, informative only

### Medium Risk
- R008 enforcement changes: Affects agent behavior
- Timeout changes: May extend task duration

### Mitigation
- Test all changes in staging environment first
- Monitor ledger for new event types after deployment
- Review timeout metrics after 1 week

## Approval

- [x] Plan Output Contract validated
- [x] Requirements understood
- [x] Task breakdown acceptable
- [x] Dependencies correct
- [x] Ready for execution via horde-implement

**Ready to proceed?** The plan will be saved and can be executed using horde-implement.
