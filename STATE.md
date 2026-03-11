# Kurultai State Management

**Quick Reference** | Full details: [`docs/state-management-reference.md`](docs/state-management-reference.md)

---

## The Three State Stores

```
┌─────────────────────────────────────────────────────────────────┐
│                    NEO4J (bolt://localhost:7687)                │
│  Task nodes, AgentFeedback, Hypothesis                          │
│  Purpose: Metrics, historical queries, cross-agent patterns      │
├─────────────────────────────────────────────────────────────────┤
│                    FILESYSTEM                                   │
│  ~/.openclaw/agents/<agent>/tasks/*.md                          │
│  Purpose: Source of truth for execution state                   │
├─────────────────────────────────────────────────────────────────┤
│                    JSON STATE FILES                             │
│  logs/task-watcher-state.json, logs/auto-dispatch-state.json    │
│  Purpose: Script operational state between runs                 │
└─────────────────────────────────────────────────────────────────┘
```

**Rule:** Filesystem is source of truth. Neo4j is derived.

---

## Task File Suffixes (what they mean)

| Suffix | Status | Terminal? |
|--------|--------|----------|
| `.md` | PENDING | No |
| `.executing.md` | EXECUTING | No |
| `.completed.done.md` | COMPLETED | Yes |
| `.failed.done.md` | FAILED | Yes |
| `.stale.done.md` | Stale (treated as COMPLETED) | Yes |

---

## Most Common Issues

### "Neo4j shows wrong status"
```bash
python3 neo4j-state-sync.py --verbose  # Find mismatches
python3 neo4j-state-sync.py --apply     # Fix Neo4j to match filesystem
```

### "Where is my task?"
```bash
# Check filesystem
ls -la ~/.openclaw/agents/temujin/tasks/

# Check Neo4j
python3 -c "from neo4j_task_tracker import TaskTracker; t=TaskTracker(); print([x for x in t.get_tasks_by_agent('temujin', limit=5)]); t.close()"
```

### "JSON state file corrupted"
The `json_state.py` library handles this — it returns empty dict on parse error (silent recovery).

---

## State Ownership

| Data | Owner | Backup |
|------|-------|--------|
| Task execution state | Filesystem (`*.md` files) | Neo4j (via sync) |
| Agent feedback | Neo4j (`AgentFeedback` nodes) | - |
| Experiments | Neo4j (`Hypothesis` nodes) | - |
| Script cooldowns | JSON files (`logs/*-cooldown.json`) | - |

---

## Script Authors

1. Use `json_state.py` for all shared JSON files
2. Use `neo4j_task_tracker.get_driver()` for Neo4j connections
3. Never rename `.done` files (terminal states are immutable)
4. After bulk failures, run `neo4j-state-sync.py --apply`

---

**Full documentation:** [`docs/state-management-reference.md`](docs/state-management-reference.md)
