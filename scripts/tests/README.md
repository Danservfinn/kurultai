# Kurultai Regression Tests

This directory contains regression tests for critical bug fixes in the OpenClaw Kurultai system.

## Filename Detection Regression Tests

**File:** `test_filename_detection.py`

**Bug Fixed:** Task state filename detection false positives

### Background

Multiple scripts were using the pattern `'.executing' in fname` to detect executing tasks. This pattern was too broad and matched files like:
- `task.executing.done.md` (completed tasks that were once executing)
- `task.completed.revision-1.done.md` (complex history)

This caused false-positive `EXECUTING_NO_OUTPUT` anomalies because completed tasks were being counted as executing.

### Fix

Replace `'.executing' in fname` with `fname.endswith(".executing.md")` to match ONLY files that are truly executing.

### Scripts Fixed

| Script | Function(s) | Pattern Used |
|--------|-------------|--------------|
| throughput_anomaly.py | count_executing_tasks, count_pending_tasks, count_movable_pending_tasks | `fname.endswith(".executing.md")` |
| auto_dispatch.py | list_executing_tasks, check_completed_dispatches | `f.name.endswith(".executing.md")` |
| kurultai_brainstorm.py | agent status summary | `f.name.endswith(".executing.md")` |
| pipeline_health.py | task counting | `fname.endswith(".executing.md")` |
| routing_audit.py | queue state | `fname.endswith(".executing.md")` |
| health_dashboard.py | queue depth | `not f.endswith(".executing.md")` |
| ogedei-watchdog.py | pending depth, load balancing | `name.endswith(".executing.md")` |

### Test Cases

The test suite verifies:

1. **Executing detection**: Files ending in `.executing.md` are counted as executing
2. **Terminal state exclusion**: Files with terminal state markers (`.done`, `.completed`, `.resolved`, etc.) are NOT counted as executing or pending
3. **Edge cases**:
   - `task.executing.done.md` → done (NOT executing)
   - `task-123.done-abc123.md` → done (hash suffix pattern)
   - `task.completed.revision-1.done.md` → done (complex history)
   - `task.executing.md` → executing (truly executing)

### Running Tests

```bash
# Run all regression tests
python3 tests/test_filename_detection.py

# Or use the shell wrapper
./tests/run_regression_tests.sh
```

### Expected Output

```
============================================================
TASK STATE FILENAME DETECTION REGRESSION TESTS
============================================================
Testing pattern detection...
  'task.executing.done.md' - old pattern would have falsely matched (this is the bug)
PASS: All pattern detection tests passed

[... 7 tests total ...]

============================================================
RESULTS: 7 passed, 0 failed
============================================================
```

## Adding New Tests

When fixing bugs that involve pattern matching or file state detection:

1. Create a new test function following the pattern: `test_<script_name>_<functionality>`
2. Add it to the `tests` list in `run_all_tests()`
3. Document the bug, fix, and test cases here in this README
