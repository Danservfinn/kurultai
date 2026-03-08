# Task Completion Template

> **Version:** 1.0
> **Purpose:** Standard format for all agent task completions
> **Required:** Use this format when completing any task

---

## Template

When you complete a task, add this resolution section to the bottom:

```markdown
## Resolution

This task is complete. The following was accomplished:

### What Was Done
- [Specific action 1]
- [Specific action 2]
- [Specific action 3]

### Files Changed
- `path/to/file1.ext` - [description of change]
- `path/to/file2.ext` - [description of change]

### Verification
- [ ] Tested locally
- [ ] Documentation updated
- [ ] No regressions introduced

### Follow-up Items (if any)
- [ ] Item for future consideration
```

---

## Examples

### Example 1: Code Change Task

```markdown
## Resolution

This task is complete. Fixed the login redirect bug.

### What Was Done
- Modified `AuthMiddleware.ts` to check session validity before redirect
- Added unit test for the redirect logic
- Updated API documentation

### Files Changed
- `src/middleware/AuthMiddleware.ts` - Added session check
- `src/__tests__/AuthMiddleware.test.ts` - Added test case
- `docs/api/auth.md` - Updated docs

### Verification
- [x] Tested locally - redirect now works correctly
- [x] Documentation updated
- [x] No regressions - all existing tests pass

### Follow-up Items
- [ ] Consider adding rate limiting to auth endpoint (future enhancement)
```

### Example 2: Documentation Task

```markdown
## Resolution

This task is complete. Created the completion gate documentation.

### What Was Done
- Wrote `completion-gate.md` with full system overview
- Created `completion-gate-examples.md` with realistic examples
- Added diagrams showing gate flow and state transitions

### Files Changed
- `docs/completion-gate.md` - New documentation (78KB)
- `docs/completion-gate-examples.md` - New examples (12KB)

### Verification
- [x] Documentation reviewed for accuracy
- [x] All examples tested against actual system
- [x] Diagrams render correctly

### Follow-up Items
- None
```

### Example 3: Research Task

```markdown
## Resolution

This task is complete. Researched and documented Neo4j schema patterns.

### What Was Done
- Analyzed 5 existing Neo4j implementations
- Documented 3 common patterns (task tracking, dependency graph, state machine)
- Identified 2 anti-patterns to avoid
- Created reference guide with Cypher examples

### Files Changed
- `docs/NEO4J_PATTERNS.md` - New pattern reference (15KB)
- `scripts/neo4j-pattern-validator.py` - Validation tool

### Verification
- [x] All patterns verified against working implementations
- [x] Code examples tested in development environment
- [x] Peer-reviewed by mongke

### Follow-up Items
- [ ] Add performance benchmarks for each pattern
```

### Example 4: Bug Fix Task

```markdown
## Resolution

This task is complete. Fixed the task-watcher rename race condition.

### What Was Done
- Identified root cause: concurrent rename attempts in `mark_task_completed()` and `recover_stale_executions()`
- Added file lock using `fcntl.flock()` around rename operations
- Added check for existing `.completed.done.md` before second rename attempt
- Added unit test for concurrent completion scenario

### Files Changed
- `scripts/task-watcher.py` - Added file locking (lines 423-435, 512-524)
- `scripts/test_task_watcher.py` - Added concurrent test case

### Verification
- [x] Tested with 10 concurrent completions - no race conditions
- [x] All existing tests pass
- [x] Monitored production for 1 hour - no VERIFY FAIL errors

### Follow-up Items
- [ ] Consider adding similar locks to other task state transitions
```

### Example 5: Minimal/Trivial Task

```markdown
## Resolution

This task is complete. Fixed typo in README.

### What Was Done
- Changed contact email from old@example.com to new@example.com

### Files Changed
- `README.md` - Line 15: email updated

### Verification
- [x] Change verified

### Follow-up Items
- None
```

---

## Why This Matters

The **Resolution** section:
1. **Proves completion** — Shows exactly what was done, not just claimed
2. **Enables review** — /horde-review checks for this section
3. **Tracks changes** — Files changed list aids code review and rollback
4. **Documents work** — Creates searchable record for future reference
5. **Catches gaps** — Verification checklist reminds agents to test

---

## Integration Points

### With Completion Gate

The Resolution section is **REQUIRED** for all gated tasks. The completion audit checks for it.

### With /horde-review

The review script at line 92 checks:
```python
"has_resolution": "## Resolution" in content or "**Status:**" in content
```

Tasks missing this section are flagged as low-quality.

### With Task Report Hook

The auto-generated report in `/reports/completed/` includes metadata, but the Resolution section lives in the task's `.done.md` file itself.

---

## Agent Instructions

### When Completing a Task

1. **Read the task** carefully
2. **Do the work** (code, research, writing, etc.)
3. **Verify** it works
4. **Add Resolution section** to the task file before marking `.done.md`
5. **Mark complete** by renaming to `.done.md`

### What Goes in Resolution

| Element | Required? | Description |
|---------|-----------|-------------|
| `## Resolution` header | ✅ Yes | Exact spelling required for review detection |
| What Was Done | ✅ Yes | Bulleted list of specific actions |
| Files Changed | ✅ Yes (for code/tasks) | List of files with brief descriptions |
| Verification | ✅ Yes | Checklist of what you tested/checked |
| Follow-up Items | Optional | Future work, nice-to-haves, next steps |

### Minimal Acceptable Resolution

For very small tasks:

```markdown
## Resolution

This task is complete. [One-line summary].

### What Was Done
- [Action taken]

### Verification
- [x] Verified working
```

---

## Validation

### Check Your Work

Before marking a task `.done.md`, verify:

```bash
# Check if Resolution section exists
grep "## Resolution" path/to/task.executing.md

# If not found, add it before marking done
```

### Review Script Detection

The review script in `review-with-fallback.py` line 92:

```python
"has_resolution": "## Resolution" in content or "**Status:**" in content,
```

**Note:** Prefer `## Resolution` over `**Status:**`. Status is auto-generated in reports, but Resolution should be in your actual task output.

---

## Troubleshooting

### Q: My task was flagged "Missing resolution section"

**A:** Add the `## Resolution` heading and content to your task file before marking it `.done.md`.

### Q: The task was too small to need a resolution

**A:** Even trivial tasks need at minimum:
```markdown
## Resolution
This task is complete. [What you did]
```

### Q: I already have a summary in the task

**A:** Add a dedicated Resolution section at the bottom. The review script looks for the exact `## Resolution` heading.

### Q: What if I have no files to list?

**A:** For research or analysis tasks:
```markdown
### Files Changed
None (analysis/documentation only)
```

Or for tasks that created new files:
```markdown
### Files Created
- `path/to/new-file.md` - [description]
```

---

*Template maintained by Chagatai (Writer agent)*
*Last updated: 2026-03-08*
