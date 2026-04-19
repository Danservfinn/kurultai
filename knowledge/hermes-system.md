# Hermes -- System Caretaker

## Role

Hermes is the Kurultai's internal monitoring and self-healing agent. It handles agent quality enforcement, continuous improvement, and system self-repair -- the checks that keep the other agents running correctly. It does **not** manage external infrastructure (Railway, Redis, Neo4j daemon, gateway, backups) -- those remain Ogedei's domain.

## Architecture

Three-layer design:

1. **Daemon layer** -- `hermes-watchdog.py` runs as a LaunchAgent (`com.kurultai.hermes-watchdog`) and performs tick-level checks on a 5-minute interval. T0-level anomalies trigger auto-fix functions immediately.
2. **LLM session layer** -- When a tick detects a condition requiring judgment (T1+), Hermes launches a Claude Code session to analyze, propose, or escalate.
3. **Proposal pipeline** -- Structural improvements flow through the tiered approval system (T0 auto-fix / T1 auto-approve / T2 notify / T3 human approval) before execution.

## T0 Auto-Fix Functions

These execute immediately without LLM involvement:

| Function | Purpose |
|----------|---------|
| `requeue_stuck_task` | Moves tasks stuck in EXECUTING beyond lease timeout back to PENDING |
| `rotate_failing_provider` | Switches to backup provider when primary returns repeated 401/403/429 |
| `clear_bloated_session` | Truncates session JSONL files exceeding 50MB to last 10K lines |
| `force_refresh_reflection_bridge` | Runs `reflection_pipeline_bridge.py --force` when reflection-status.json is stale |
| `reconcile_orphan_tasks` | Syncs Neo4j and filesystem task queues, re-queuing orphans |

## Rules H001-H012

| ID | Name | Category |
|----|------|----------|
| H001 | Model Drift Detection | quality |
| H002 | Provider Failure Rate | quality |
| H003 | Session Bloat Monitor | quality |
| H004 | Orphan Task Reconciliation | recovery |
| H005 | Reflection Pipeline Health | monitoring |
| H006 | Reflection Job-ID Stale Guard | monitoring |
| H007 | Completion Quality Gate | quality |
| H008 | Reflection Cron Gap Detection | monitoring |
| H009 | Agent Failure Pattern Analysis | quality |
| H010 | Continuous Improvement Scan | improvement |
| H011 | Knowledge Sync | improvement |
| H012 | Kill Switch Monitor | safety |

## Kill Switch

To disable Hermes immediately:

```bash
touch ~/.openclaw/flags/hermes-disabled.flag
```

The watchdog checks for this flag file on every tick. If present, it exits silently. Remove the flag to re-enable.

## LaunchAgent

- **Identifier:** `com.kurultai.hermes-watchdog`
- **Interval:** 300 seconds (5 minutes)
- **Executable:** `~/.openclaw/agents/hermes/hermes-watchdog.py`
- **Log:** `~/.openclaw/logs/hermes-watchdog.log`

## Cron Jobs

| Job | Schedule | Script | Purpose |
|-----|----------|--------|---------|
| hermes-reflection-daily | Daily 06:00 | `reflection_daily.py` | Full reflection pipeline run |
| hermes-improvement-scan | Weekly Sun 03:00 | `improvement_scan.py` | Scan agent logs for improvement proposals |
| hermes-knowledge-sync | Daily 22:00 | `knowledge_sync.py` | Sync knowledge base from agent observations |

## Migration from Ogedei

Hermes absorbed 16 of Ogedei's 18 heartbeat checks (checks 1-13, 15-18). The following Ogedei rules were disabled and migrated:

| Ogedei Rule | Hermes Rule | Function |
|-------------|-------------|----------|
| O001 | H001 | Model drift detection |
| O004 | H004 | Orphan task reconciliation |
| O009 | H005 | Reflection stale escalation |
| O010 | H006 | Reflection job-ID stale guard |
| O011 | H007 | Completion quality gate |
| O012 | H008 | Reflection cron gap detection |
| O-R021 | H001 | Model mismatch tock-level logging |

Ogedei retains: O002 (fast failure investigation), O003 (cron gap detection), O005 (domain boundary), O006 (auth health gap), O-R020 (gateway spike incident).

## Configuration

- **Workdir:** `~/.openclaw/agents/hermes/`
- **Rules:** `~/.openclaw/agents/hermes/rules.json`
- **Config:** `~/.openclaw/agents/hermes/config.json`
- **Ledger:** `~/.openclaw/logs/hermes-watchdog.jsonl`

## Autonomous Improvement Layer (added 2026-04-19)

On top of the T0 auto-fix library, Hermes now authors + commits + pushes its own patches. See `/Users/kublai/.claude/plans/lazy-sparking-hamster.md` for the full plan and `/Users/kublai/brain/concepts/hermes-autonomous-improvement.md` for the concept summary.

### Fix engine flow (`hermes_fix_engine.py`)

14-step orchestrator. Invariant: target files end in one of two states — (a) fix applied + committed + pushed + DM sent, (b) files in their original pre-fix state + rollback DM sent.

```
gates → rate-limit → baseline-test → dry-run-apply → snapshot →
  apply → post-test → git-add → commit → push →
    HermesCommit node → HermesAction emit → rate-limit record → notify DM
```

### Authoring scripts

- `hermes-fix-content.py` — content patches (wiki, docs, knowledge). Sanitizes source via `hermes_sanitize.py` before LLM subprocess.
- `hermes-fix-code.py` — code patches (.py files). Adds: baseline-test gate, diff-size cap (default 80 lines), AST parse check via `patch(1)` on a scratch copy.

### Safety flags (6-tier hierarchy)

Precedence high→low:
1. `hermes-disabled.flag` — all T0 halted
2. `hermes-risky-disabled.flag` — credential-affecting T0s only
3. `hermes-autonomous-disabled.flag` — master autonomous kill
4. `hermes-autonomous-fix-content-disabled.flag`
5. `hermes-autonomous-fix-code-disabled.flag`
6. `hermes-autonomous-sweep-disabled.flag`

Emergency: `bash hermes-panic-stop.sh`. Staged resume: `bash hermes-resume.sh`.

### Denylist (`hermes_denylist.py`)

Canonicalizes paths via `os.path.realpath` (defeats symlinks), case-folds on APFS, matches variant filenames (`foo.py.new` too). Hermes's own scripts + manifest + flags dir + credentials + `task-reaper.py` are all denied. Override flag `hermes-self-modification-override.flag` permits one-shot `hermes-watchdog.py` patches for the dedup-gap bootstrap.

### Rate limiter + circuit breaker

- `hermes_rate_limit.consume_slot(scope)` — atomic check-and-record. Caps: 3/hour per scope (`content`|`code`), 10/day total.
- `hermes_circuit_breaker.record_event(type, detail)` — trips at 2 `apply_failed` in 30m, 3 `rollback` in 60m, or 1 `denylist_violation`. On trip: touches `hermes-autonomous-disabled.flag`, DMs operator.

### Scheduled sweeps (`hermes_sweep_runner.py`)

Each sweep starts in `notify-only` mode (DMs operator about candidates). Graduates to `autonomous` by setting `echo autonomous > ~/.openclaw/flags/hermes-sweep-<name>-mode.flag`.

- `knowledge_stale` — docs older than 90 days → content authoring
- `dedup_gap` — unwrapped `write_hermes_task` in `hermes-watchdog.py` → code authoring (requires override flag)
- `bare_except` — `except:` / `except Exception: pass` → code authoring

### Event-driven queue (`hermes-fix-runner.py`)

5-minute cron consumer. Detection checks in hermes-watchdog can call `enqueue_fix_job(target, reason, level)` to drop a JSON spec into `~/.openclaw/queues/hermes-fix-jobs/pending/`. Runner claims atomically (pending→in-progress rename), dispatches to the appropriate fix-script, moves to done/failed/rate-limited based on outcome. Per-target-per-hour enqueue dedup prevents flooding.

### Revert via Signal reply (`hermes_revert_handler.py`)

Intent registered in `signal_message_handler.py`: operator DM replies of `revert`, `revert <sha>`, or `revert all today` trigger `git revert --no-edit` + push + confirmation DM. Defense in depth: (a) SHA must be a HermesCommit node in Neo4j, (b) `git log` must confirm Hermes authorship, (c) sender phone must match operator phone.

### Audit CLIs

- `hermes-fix-log.py list` — recent commits
- `hermes-fix-log.py stats --window 7d` — sweep/outcome counts
- `hermes-fix-log.py reverted` — recent reverts
- `hermes_metrics.py --summary` — dashboard summary
- `hermes_digest.py` — daily Signal digest (cron-triggered)

### Integrity manifest

`~/.openclaw/agents/hermes/import-manifest.json` now tracks 21 entries: original 5 + 6 Phase 0 modules + new Phase 1-8 modules + 2 shell scripts + 2 git pre-commit hooks. Daemon verifies all sha256s at startup and self-kill-switches on mismatch.
