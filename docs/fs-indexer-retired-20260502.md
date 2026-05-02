# fs-indexer Quarantined — 2026-05-02

**Status:** Quarantined (launchd job stopped, source code retained, plist disabled)
**Wave:** Phase 5 Neo4j decommission — Wave 5 blocker triage
**Decision:** Path (c) Quarantine, deferred to Phase 3 task-lifecycle carveout

## What was retired

- **Service:** `com.kurultai.fs-indexer` (was running as launchd background agent on Mac mini)
- **Script:** `/Users/kublai/.openclaw/agents/ogedei/tools/fs_indexer.py` (left in place, no source change)
- **Plist:** `/Users/kublai/Library/LaunchAgents/com.kurultai.fs-indexer.plist` renamed to `.disabled-2026-05-02`
- **Action taken:** `launchctl bootout gui/$UID/com.kurultai.fs-indexer` + plist rename

## What it did

Polled every 30s across `~/.openclaw/agents/{chagatai,jochi,kublai,mongke,ogedei,temujin,tolui}/tasks/*.md`,
parsed task frontmatter (task_id, title, priority, domain, agent, etc.), and ran a Cypher
`MERGE (t:Task {task_id: ...}) ON CREATE/ON MATCH SET ... t.status = 'PENDING'` upsert into Neo4j.
Each cycle held an ESTABLISHED bolt fd to `localhost:7687` — the reason Wave 5's runtime gate flagged it.

It was the **filesystem -> Neo4j task-pipeline ingress**, the bridge that turned operator-dropped
task `.md` files into PENDING `:Task` nodes for `task_executor.py` (and the dashboard) to consume.

## Why retired without a brain-service migration

1. **Direct downstream consumer is `task_executor.py`**, which still reads tasks from Neo4j via
   `neo4j_v2_core.TaskStore.claim_task`. Migrating fs-indexer's writes to telemetry.db without
   simultaneously migrating task_executor would orphan the pipeline (writes go nowhere useful).
2. **task_executor migration is in flight under the Phase 3 task-lifecycle carveout** (see
   `analyses/2026-05-02-phase-3-task-lifecycle-carveout-design.md` in the brain wiki). That work
   is explicitly out of scope for this Wave 5 blocker agent.
3. **Brain-service has the right primitives** for the migration (`telemetry.create_task_full`,
   `telemetry.list_tasks`, `telemetry.set_task_status`, etc., plus an existing watchdog-based
   `start_file_watcher()` over the wiki root). The Phase 3 carveout owns wiring these together.
4. **System is currently idle:** at retirement time all 7 agent task dirs had 0 active `.md`
   files (only terminal `.done./.cancelled./.failed./.stale.` artifacts). Stopping the service
   does not strand pending operator work.

## What this means for the Phase 3 task-lifecycle carveout

When that carveout migrates `task_executor.py` to read tasks from telemetry.db:

- The replacement for fs_indexer should write new `.md` task files into telemetry.db via
  `telemetry.create_task_full`, keyed by the same `task_id`.
- The fs-indexer source at `agents/ogedei/tools/fs_indexer.py` can be reused as a starting
  point — the parsing logic in `_parse_task_file()` is correct and well-tested. Only the
  Neo4j sink (`_MERGE_CYPHER` + `_upsert_task` + `_get_driver`) needs replacement with a
  `brain_rpc("telemetry.create_task_full", props)` call.
- Alternative: extend brain-service's existing `start_file_watcher()` (in `brain_service.py`,
  currently only watches the wiki root) to also watch `~/.openclaw/agents/*/tasks/*.md` and
  route through `telemetry.create_task_full`. This consolidates two watchers into one.

## Restoration instructions (if rollback needed)

```bash
mv ~/Library/LaunchAgents/com.kurultai.fs-indexer.plist.disabled-2026-05-02 \
   ~/Library/LaunchAgents/com.kurultai.fs-indexer.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.kurultai.fs-indexer.plist
launchctl kickstart gui/$(id -u)/com.kurultai.fs-indexer
```

## Backup pointers

- Source pre-quarantine: `~/backups/neo4j-pre-migration/2026-05-02/fs_indexer.py.pre-phase-5`
  (sha256 `8063b5a6a8c8e9157c66d94d66fdb9de6d0bdff280568ad8d1c7bdf3e93a7904`)
- Plist pre-quarantine: `~/backups/neo4j-pre-migration/2026-05-02/com.kurultai.fs-indexer.plist.pre-phase-5`
  (sha256 `72645cc8741f3371e73bd2c5ce5d024fde2b0a42528c968974b16584151c0e5a`)

## Cross-refs

- Phase 3 task-lifecycle carveout design (brain wiki, May 2 2026)
- `brain_service.py` `start_file_watcher()` — existing watchdog implementation
- `~/.hermes/scripts/brain_rpc.py` — canonical brain-service RPC helper
