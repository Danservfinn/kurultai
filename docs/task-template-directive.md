# Task Template Directive - Post-Completion Reporting

**Effective:** 2026-03-07
**Applies to:** All task files across all agents

---

## Requirement

**Every task must include this directive in its template or specification:**

```markdown
## Post-Completion

**REQUIRED:** After task completes, invoke `kublai-task-report` skill to generate completion report.

This happens automatically via `task-watcher.py` integration. No manual action needed.
```

---

## Why

The `kublai-task-report` skill automatically generates detailed completion reports for every finished task. This provides:

1. **Visibility** - Users see what was accomplished
2. **Audit trail** - Reports saved to `reports/completed/`
3. **Signal notifications** - Team notified of completions
4. **Neo4j logging** - Report paths stored on task nodes

---

## Integration

The reporting is automatic - `task-watcher.py` calls `task-report-hook.py` after every task completion (success or failure).

### Hook Location
```
~/.openclaw/agents/main/scripts/task-report-hook.py
```

### Reports Directory
```
~/.openclaw/agents/main/reports/completed/
```

### Report Format
See `~/.openclaw/skills/kublai-task-report/SKILL.md` for full format specification.

---

## What Gets Reported

For each completed task:

| Data Point | Source |
|------------|--------|
| Task ID, title, agent | Task frontmatter |
| Duration | Execution timing |
| Status | Success/failure |
| Workspace changes | File scan (last 60 min) |
| Git diff | Git status |
| Metrics | Lines, files, duration |

---

## Distribution

Reports are automatically:

1. **Saved** to `reports/completed/{task_id}.md`
2. **Sent** to Signal chat (`+19194133445`)
3. **Logged** to Neo4j (Task node `report_path` property)
4. **Linked** in task file (`report_path:` frontmatter)

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REPORTS_DIR` | `~/.openclaw/agents/main/reports/completed/` | Report output directory |
| `SIGNAL_ACCOUNT` | (empty) | Signal phone number for notifications |
| `SIGNAL_GROUP_ID` | (empty) | Signal group ID for group notifications |
| `ENABLE_GIT_DIFF` | `true` | Include git diff in reports |
| `SIGNAL_NOTIFY` | `true` | Send Signal notifications |

---

## Testing

### Manual Test

```bash
python3 ~/.openclaw/agents/main/scripts/task-report-hook.py \
  --task-file /path/to/task.md \
  --agent mongke \
  --status completed \
  --duration 120
```

### Verify Output

```bash
# Check report was created
ls -la ~/.openclaw/agents/main/reports/completed/

# View report content
cat ~/.openclaw/agents/main/reports/completed/{task_id}.md
```

---

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| No report generated | Hook not called | Check task-watcher.py integration |
| Empty deliverables | Workspace scan failed | Verify agent workspace exists |
| Signal not sending | Config missing | Set `SIGNAL_ACCOUNT` env var |
| Neo4j error | Connection failed | Check Neo4j is running |

---

## Related Files

- `~/.openclaw/skills/kublai-task-report/SKILL.md` - Skill documentation
- `~/.openclaw/agents/main/scripts/task-report-hook.py` - Hook script
- `~/.openclaw/agents/main/scripts/task-watcher.py` - Integration point
- `~/.openclaw/agents/main/reports/completed/` - Report output directory

---

*Add this directive to all task templates to ensure consistent post-completion reporting.*
