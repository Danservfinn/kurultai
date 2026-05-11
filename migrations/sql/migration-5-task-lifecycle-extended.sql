-- Migration v5: Extend in_flight_tasks with Phase 3 dashboard columns and widen status CHECK.
--
-- Reason: server.js (the-kurultai dashboard) reads/writes ~24 task properties via Cypher
-- that don't exist as columns in the SQLite mirror. The Kanban UI also stores statuses
-- as uppercase variants (PENDING, WORKING, COMPLETED, FAILED, ORPHANED, OBSOLETE, DONE,
-- STALE, CANCELLED, IN_PROGRESS) which are not in the original CHECK clause.
--
-- Strategy:
--   1. Recreate in_flight_tasks (STRICT) with all new columns + widened CHECK (CHECK
--      cannot be altered in place on a STRICT table).
--   2. Copy existing rows into the new table.
--   3. Recreate dependent indexes and FK from claim_locks.
--   4. Add idx_in_flight_tasks_dashboard covering index for Kanban GET.
--   5. Record migration v5.

BEGIN IMMEDIATE;

-- Drop existing dependent indexes (will recreate after rename swap)
DROP INDEX IF EXISTS idx_inflight_tasks_assigned_status;
DROP INDEX IF EXISTS idx_inflight_tasks_status_priority;
DROP INDEX IF EXISTS idx_inflight_tasks_pipeline;
DROP INDEX IF EXISTS idx_inflight_tasks_parent;
DROP INDEX IF EXISTS idx_inflight_tasks_paused;
DROP INDEX IF EXISTS idx_in_flight_tasks_dashboard;

-- Phase A: rename old table out of the way (FK from claim_locks would point to old name
-- after rename, so we DROP claim_locks FK rows first by deleting all locks; the live
-- run pauses gateway/executor/agents before this migration so claim_locks is empty)
ALTER TABLE in_flight_tasks RENAME TO _in_flight_tasks_v4_pre_phase_3;

-- Phase B: create new table with all Phase 3 columns + widened CHECK
CREATE TABLE in_flight_tasks (
  id                          TEXT PRIMARY KEY,
  type                        TEXT NOT NULL,
  description                 TEXT NOT NULL,
  delegated_by                TEXT NOT NULL,
  assigned_to                 TEXT,
  priority                    INTEGER NOT NULL,
  status                      TEXT NOT NULL CHECK(status IN (
                                'pending','in_progress','completed','failed','cancelled',
                                'PENDING','WORKING','COMPLETED','FAILED','ORPHANED',
                                'OBSOLETE','DONE','STALE','CANCELLED','IN_PROGRESS'
                              )),
  claimed_by                  TEXT,
  claimed_at                  INTEGER,
  active_claim_token          TEXT,
  active_lease_version        INTEGER,
  completed_at                INTEGER,
  failed_at                   INTEGER,
  results_json                TEXT CHECK(results_json IS NULL OR json_valid(results_json)),
  completion_summary          TEXT,
  completion_body_hash        TEXT,
  target_wiki_path            TEXT,
  wiki_path                   TEXT,
  materialized_at             INTEGER,
  completion_attempt_count    INTEGER NOT NULL DEFAULT 0,
  last_error                  TEXT,
  created_at                  INTEGER NOT NULL,
  updated_at                  INTEGER NOT NULL,
  trace_id                    TEXT,
  reliability_state           TEXT NOT NULL DEFAULT 'pending',
  retry_count                 INTEGER NOT NULL DEFAULT 0,
  -- Phase 3 dashboard columns (server.js Cypher property keys)
  title                       TEXT,
  prompt                      TEXT,
  domain                      TEXT,
  source                      TEXT,
  parent_task                 TEXT,
  reflection_id               TEXT,
  pipeline_id                 TEXT,
  sort_order                  INTEGER,
  paused                      INTEGER NOT NULL DEFAULT 0,
  paused_at                   INTEGER,
  dispatch_phase              TEXT,
  max_retries                 INTEGER NOT NULL DEFAULT 3,
  timeout_s                   INTEGER,
  depth                       INTEGER NOT NULL DEFAULT 0,
  requires_computer_use       INTEGER NOT NULL DEFAULT 0,
  skill_hint                  TEXT,
  reassigned_from             TEXT,
  previous_status             TEXT,
  previous_agent              TEXT,
  original_prompt             TEXT,
  previous_prompt             TEXT,
  cancelled_at                INTEGER,
  started_at                  INTEGER,
  claim_epoch                 INTEGER,
  score                       REAL,
  obsolete_reason             TEXT,
  obsolete_by                 TEXT,
  obsolete_at                 INTEGER,
  rewrite_reason              TEXT,
  rewrite_by                  TEXT,
  rewritten_at                INTEGER,
  reassign_reason             TEXT,
  reassigned_by               TEXT,
  reassigned_at               INTEGER,
  optimized_prompt            TEXT
) STRICT;

-- Phase C: copy existing rows. Older rows have only the legacy columns; new ones get
-- defaults via NULL or the NOT NULL DEFAULT clauses above.
INSERT INTO in_flight_tasks (
  id, type, description, delegated_by, assigned_to, priority, status,
  claimed_by, claimed_at, active_claim_token, active_lease_version,
  completed_at, failed_at, results_json, completion_summary, completion_body_hash,
  target_wiki_path, wiki_path, materialized_at, completion_attempt_count, last_error,
  created_at, updated_at, trace_id, reliability_state, retry_count
)
SELECT
  id, type, description, delegated_by, assigned_to, priority, status,
  claimed_by, claimed_at, active_claim_token, active_lease_version,
  completed_at, failed_at, results_json, completion_summary, completion_body_hash,
  target_wiki_path, wiki_path, materialized_at, completion_attempt_count, last_error,
  created_at, updated_at, trace_id, reliability_state, retry_count
FROM _in_flight_tasks_v4_pre_phase_3;

-- Phase D: drop the renamed table (data fully copied to new in_flight_tasks)
DROP TABLE _in_flight_tasks_v4_pre_phase_3;

-- Phase E: recreate indexes
CREATE INDEX IF NOT EXISTS idx_inflight_tasks_assigned_status
  ON in_flight_tasks(assigned_to, status);
CREATE INDEX IF NOT EXISTS idx_inflight_tasks_status_priority
  ON in_flight_tasks(status, priority, created_at);
CREATE INDEX IF NOT EXISTS idx_inflight_tasks_pipeline
  ON in_flight_tasks(pipeline_id);
CREATE INDEX IF NOT EXISTS idx_inflight_tasks_parent
  ON in_flight_tasks(parent_task);
CREATE INDEX IF NOT EXISTS idx_inflight_tasks_paused
  ON in_flight_tasks(paused, status);

-- Phase F: covering index for the Kanban GET (status,sort_order,priority,created_at)
CREATE INDEX IF NOT EXISTS idx_in_flight_tasks_dashboard
  ON in_flight_tasks(status, sort_order DESC, priority, created_at DESC);

-- Phase G: record the migration
INSERT OR IGNORE INTO schema_migrations (version, applied_at, description)
  VALUES (5, unixepoch() * 1000, 'phase 3 step 11 in_flight_tasks extended');

COMMIT;
