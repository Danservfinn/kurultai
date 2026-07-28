SET ROLE hulagu_owner;
SET search_path = pg_catalog;

-- Tenant quota configuration is durable and isolated from global pressure state.
CREATE TABLE hulagu.tenant_storage_state (
  tenant_id uuid PRIMARY KEY,
  quota_bytes bigint NOT NULL CHECK (quota_bytes > 0),
  accounted_bytes bigint NOT NULL CHECK (accounted_bytes >= 0),
  reserved_bytes bigint NOT NULL DEFAULT 0 CHECK (reserved_bytes >= 0),
  updated_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
  FOREIGN KEY (tenant_id) REFERENCES hulagu.tenants(id) ON DELETE CASCADE
);

CREATE TABLE hulagu.tenant_storage_reservations (
  tenant_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT public.gen_random_uuid(),
  operation text NOT NULL CHECK (operation IN ('upload','search')),
  reserved_bytes bigint NOT NULL CHECK (reserved_bytes > 0),
  created_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
  PRIMARY KEY (tenant_id, id),
  FOREIGN KEY (tenant_id) REFERENCES hulagu.tenants(id) ON DELETE CASCADE
);

ALTER TABLE hulagu.tenant_storage_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE hulagu.tenant_storage_state FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_storage_state_isolation ON hulagu.tenant_storage_state
  USING (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE hulagu.tenant_storage_reservations ENABLE ROW LEVEL SECURITY;
ALTER TABLE hulagu.tenant_storage_reservations FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_storage_reservations_isolation ON hulagu.tenant_storage_reservations
  USING (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid);

REVOKE ALL ON hulagu.tenant_storage_state, hulagu.tenant_storage_reservations FROM PUBLIC;
INSERT INTO hulagu.global_storage_state(singleton, pressure_state, measured_bytes)
VALUES (true, 'normal', 0)
ON CONFLICT (singleton) DO NOTHING;

CREATE FUNCTION hulagu_api.configure_tenant_storage(
  p_quota_bytes bigint,
  p_accounted_bytes bigint
) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE
  v_tenant uuid := NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid;
BEGIN
  IF v_tenant IS NULL OR p_quota_bytes NOT BETWEEN 1 AND 1099511627776
     OR p_accounted_bytes NOT BETWEEN 0 AND 1099511627776 THEN
    RAISE EXCEPTION 'invalid bounded tenant storage configuration';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM hulagu.tenants AS t WHERE t.id = v_tenant) THEN
    RAISE EXCEPTION 'invalid bounded tenant context';
  END IF;
  INSERT INTO hulagu.tenant_storage_state(tenant_id, quota_bytes, accounted_bytes)
  VALUES (v_tenant, p_quota_bytes, p_accounted_bytes)
  ON CONFLICT (tenant_id) DO UPDATE
  SET quota_bytes = EXCLUDED.quota_bytes,
      accounted_bytes = EXCLUDED.accounted_bytes,
      updated_at = pg_catalog.now();
END
$$;

CREATE FUNCTION hulagu_api.admit_tenant_storage(
  p_operation text,
  p_requested_bytes bigint
) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE
  v_tenant uuid := NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid;
  v_state hulagu.tenant_storage_state%ROWTYPE;
  v_reservation uuid;
  v_backup_locked boolean;
BEGIN
  IF v_tenant IS NULL OR p_operation NOT IN ('upload','search')
     OR p_requested_bytes NOT BETWEEN 1 AND 1099511627776 THEN
    RAISE EXCEPTION 'invalid bounded tenant storage admission';
  END IF;
  SELECT b.read_only_mode INTO v_backup_locked
  FROM hulagu.backup_coordination AS b WHERE b.singleton FOR SHARE;
  IF v_backup_locked THEN RAISE EXCEPTION 'backup lock held'; END IF;
  IF COALESCE((SELECT g.pressure_state FROM hulagu.global_storage_state AS g WHERE g.singleton), 'critical') <> 'normal' THEN
    RAISE EXCEPTION 'global storage pressure refuses admission';
  END IF;
  SELECT s.* INTO v_state
  FROM hulagu.tenant_storage_state AS s
  WHERE s.tenant_id = v_tenant
  FOR UPDATE;
  IF NOT FOUND OR v_state.accounted_bytes + v_state.reserved_bytes + p_requested_bytes > v_state.quota_bytes THEN
    RAISE EXCEPTION 'tenant storage quota exceeded';
  END IF;
  INSERT INTO hulagu.tenant_storage_reservations(tenant_id, operation, reserved_bytes)
  VALUES (v_tenant, p_operation, p_requested_bytes)
  RETURNING id INTO v_reservation;
  UPDATE hulagu.tenant_storage_state AS s
  SET reserved_bytes = s.reserved_bytes + p_requested_bytes,
      updated_at = pg_catalog.now()
  WHERE s.tenant_id = v_tenant;
  RETURN v_reservation;
END
$$;

CREATE FUNCTION hulagu_api.settle_tenant_storage(
  p_reservation_id uuid,
  p_actual_bytes bigint
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE
  v_tenant uuid := NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid;
  v_reserved_bytes bigint;
  v_state hulagu.tenant_storage_state%ROWTYPE;
  v_backup_locked boolean;
BEGIN
  IF v_tenant IS NULL OR p_actual_bytes NOT BETWEEN 0 AND 1099511627776 THEN
    RAISE EXCEPTION 'invalid bounded tenant storage settlement';
  END IF;
  SELECT b.read_only_mode INTO v_backup_locked
  FROM hulagu.backup_coordination AS b WHERE b.singleton FOR SHARE;
  IF v_backup_locked THEN RAISE EXCEPTION 'backup lock held'; END IF;
  SELECT r.reserved_bytes INTO v_reserved_bytes
  FROM hulagu.tenant_storage_reservations AS r
  WHERE r.tenant_id = v_tenant AND r.id = p_reservation_id
  FOR UPDATE;
  IF NOT FOUND THEN RETURN false; END IF;
  IF p_actual_bytes > v_reserved_bytes THEN
    RAISE EXCEPTION 'actual storage exceeds reservation';
  END IF;
  SELECT s.* INTO v_state FROM hulagu.tenant_storage_state AS s
  WHERE s.tenant_id = v_tenant FOR UPDATE;
  IF NOT FOUND OR v_state.accounted_bytes + p_actual_bytes > v_state.quota_bytes
     OR v_state.reserved_bytes < v_reserved_bytes THEN
    RAISE EXCEPTION 'invalid tenant storage accounting state';
  END IF;
  DELETE FROM hulagu.tenant_storage_reservations AS r
  WHERE r.tenant_id = v_tenant AND r.id = p_reservation_id;
  UPDATE hulagu.tenant_storage_state AS s
  SET accounted_bytes = s.accounted_bytes + p_actual_bytes,
      reserved_bytes = s.reserved_bytes - v_reserved_bytes,
      updated_at = pg_catalog.now()
  WHERE s.tenant_id = v_tenant;
  RETURN true;
END
$$;

GRANT USAGE ON SCHEMA hulagu_api TO hulagu_migrator;
REVOKE ALL ON FUNCTION hulagu_api.configure_tenant_storage(bigint,bigint) FROM PUBLIC;
REVOKE ALL ON FUNCTION hulagu_api.admit_tenant_storage(text,bigint) FROM PUBLIC;
REVOKE ALL ON FUNCTION hulagu_api.settle_tenant_storage(uuid,bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION hulagu_api.configure_tenant_storage(bigint,bigint) TO hulagu_migrator;
GRANT EXECUTE ON FUNCTION hulagu_api.admit_tenant_storage(text,bigint) TO hulagu_app;
GRANT EXECUTE ON FUNCTION hulagu_api.settle_tenant_storage(uuid,bigint) TO hulagu_app;

-- The singleton row serializes every transition into and out of global read-only
-- mode. Backup metadata is retained separately so releasing the lock cannot erase
-- the snapshot/artifact pairing that a restore must verify.
CREATE TABLE hulagu.backup_coordination (
  singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
  read_only_mode boolean NOT NULL DEFAULT false,
  active_backup_id uuid UNIQUE,
  lock_token_hash text CHECK (lock_token_hash IS NULL OR lock_token_hash ~ '^[0-9a-f]{64}$'),
  locked_at timestamptz,
  updated_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
  CHECK (
    (read_only_mode AND active_backup_id IS NOT NULL AND lock_token_hash IS NOT NULL AND locked_at IS NOT NULL)
    OR (NOT read_only_mode AND active_backup_id IS NULL AND lock_token_hash IS NULL AND locked_at IS NULL)
  )
);

CREATE TABLE hulagu.backup_generations (
  backup_id uuid PRIMARY KEY,
  state text NOT NULL CHECK (state IN ('locked','snapshot_recorded','released')),
  database_snapshot_id text,
  artifact_manifest jsonb,
  artifact_manifest_digest text CHECK (
    artifact_manifest_digest IS NULL OR artifact_manifest_digest ~ '^[0-9a-f]{64}$'
  ),
  locked_at timestamptz NOT NULL,
  snapshot_recorded_at timestamptz,
  released_at timestamptz,
  CHECK (
    (state = 'locked' AND database_snapshot_id IS NULL AND artifact_manifest IS NULL
      AND artifact_manifest_digest IS NULL AND snapshot_recorded_at IS NULL AND released_at IS NULL)
    OR (state = 'snapshot_recorded' AND database_snapshot_id IS NOT NULL AND artifact_manifest IS NOT NULL
      AND artifact_manifest_digest IS NOT NULL AND snapshot_recorded_at IS NOT NULL AND released_at IS NULL)
    OR (state = 'released' AND database_snapshot_id IS NOT NULL AND artifact_manifest IS NOT NULL
      AND artifact_manifest_digest IS NOT NULL AND snapshot_recorded_at IS NOT NULL AND released_at IS NOT NULL)
  )
);

REVOKE ALL ON hulagu.backup_coordination, hulagu.backup_generations FROM PUBLIC;
INSERT INTO hulagu.backup_coordination(singleton) VALUES (true);

CREATE FUNCTION hulagu_api.begin_backup_coordination(p_lock_token_hash text) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE
  v_backup_id uuid := public.gen_random_uuid();
  v_now timestamptz := pg_catalog.now();
  v_locked boolean;
BEGIN
  IF p_lock_token_hash !~ '^[0-9a-f]{64}$' THEN
    RAISE EXCEPTION 'invalid backup lock authority';
  END IF;
  SELECT b.read_only_mode INTO v_locked
  FROM hulagu.backup_coordination AS b
  WHERE b.singleton
  FOR UPDATE;
  IF v_locked THEN RAISE EXCEPTION 'backup lock already held'; END IF;
  UPDATE hulagu.backup_coordination AS b
  SET read_only_mode = true, active_backup_id = v_backup_id,
      lock_token_hash = p_lock_token_hash, locked_at = v_now, updated_at = v_now
  WHERE b.singleton;
  INSERT INTO hulagu.backup_generations(backup_id, state, locked_at)
  VALUES (v_backup_id, 'locked', v_now);
  UPDATE hulagu.job_attempts AS j
  SET state = 'expired', lease_token_hash = NULL, lease_expires_at = NULL
  WHERE j.state IN ('queued','claimed');
  UPDATE hulagu.outbox_messages AS o
  SET state = 'cancelled', lease_token_hash = NULL, lease_expires_at = NULL
  WHERE o.kind = 'ordinary' AND o.state IN ('pending','failed','claimed');
  RETURN v_backup_id;
END
$$;

-- Every write-capable claim takes the global row before any tenant or work row.
-- This matches begin_backup_coordination's global-first order, so an in-flight
-- claim drains before backup acquisition and no new claim can start while held.
CREATE OR REPLACE FUNCTION hulagu_api.claim_job(
  p_job_id uuid,
  p_lease_token_hash text,
  p_lease_seconds integer DEFAULT 60
) RETURNS TABLE(
  job_id uuid,
  tenant_id uuid,
  attempt integer,
  immutable_input_digest text,
  lifecycle_epoch bigint,
  work_epoch bigint
)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE
  v_tenant uuid;
  v_backup_locked boolean;
BEGIN
  IF p_lease_token_hash !~ '^[0-9a-f]{64}$' OR p_lease_seconds NOT BETWEEN 1 AND 300 THEN
    RAISE EXCEPTION 'invalid lease authority';
  END IF;
  SELECT b.read_only_mode INTO v_backup_locked
  FROM hulagu.backup_coordination AS b WHERE b.singleton FOR SHARE;
  IF v_backup_locked THEN RAISE EXCEPTION 'backup lock held'; END IF;
  SELECT j.tenant_id INTO v_tenant
  FROM hulagu.job_attempts AS j
  WHERE j.id = p_job_id AND j.state = 'queued'
  ORDER BY j.tenant_id LIMIT 1;
  IF v_tenant IS NULL THEN RETURN; END IF;
  PERFORM pg_catalog.set_config('app.tenant_id', v_tenant::text, true);
  RETURN QUERY
  UPDATE hulagu.job_attempts AS j
  SET state = 'claimed', lease_token_hash = p_lease_token_hash,
      lease_expires_at = pg_catalog.now() + pg_catalog.make_interval(secs => p_lease_seconds)
  WHERE j.tenant_id = v_tenant AND j.id = p_job_id AND j.state = 'queued'
  RETURNING j.id, j.tenant_id, j.attempt, j.immutable_input_digest,
            j.lifecycle_epoch, j.work_epoch;
END
$$;

CREATE OR REPLACE FUNCTION hulagu_api.claim_outbox_delivery(
  p_lease_token_hash text,
  p_batch integer DEFAULT 10,
  p_lease_seconds integer DEFAULT 60
) RETURNS TABLE(
  outbox_id uuid,
  delivery_key text,
  kind text,
  payload jsonb,
  attempt integer,
  lifecycle_epoch bigint,
  work_epoch bigint
)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE
  v_tenant uuid := NULLIF(pg_catalog.current_setting('app.tenant_id', true),'')::uuid;
  v_tenant_state text;
  v_lifecycle_epoch bigint;
  v_backup_locked boolean;
BEGIN
  IF v_tenant IS NULL OR p_lease_token_hash !~ '^[0-9a-f]{64}$'
     OR p_batch NOT BETWEEN 1 AND 100 OR p_lease_seconds NOT BETWEEN 1 AND 300 THEN
    RAISE EXCEPTION 'invalid bounded outbox claim';
  END IF;
  SELECT b.read_only_mode INTO v_backup_locked
  FROM hulagu.backup_coordination AS b WHERE b.singleton FOR SHARE;
  IF v_backup_locked THEN RAISE EXCEPTION 'backup lock held'; END IF;
  SELECT t.state, t.lifecycle_epoch INTO v_tenant_state, v_lifecycle_epoch
  FROM hulagu.tenants AS t WHERE t.id = v_tenant FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'invalid bounded tenant context'; END IF;
  UPDATE hulagu.outbox_messages AS o
  SET state = 'cancelled', lease_token_hash = NULL, lease_expires_at = NULL
  WHERE o.tenant_id = v_tenant AND o.kind = 'ordinary'
    AND o.state IN ('pending','failed','claimed')
    AND (o.lifecycle_epoch <> v_lifecycle_epoch
      OR v_tenant_state IN ('PAUSED','DELETE_PENDING','DELETING','DELETED'));
  IF v_tenant_state IN ('PAUSED','DELETE_PENDING','DELETING','DELETED') THEN RETURN; END IF;
  RETURN QUERY
  WITH candidates AS (
    SELECT o.id FROM hulagu.outbox_messages AS o
    WHERE o.tenant_id = v_tenant AND o.kind = 'ordinary'
      AND o.lifecycle_epoch = v_lifecycle_epoch AND o.attempt_count < o.max_attempts
      AND (o.state IN ('pending','failed')
        OR (o.state = 'claimed' AND o.lease_expires_at <= pg_catalog.now()))
    ORDER BY o.created_at, o.id LIMIT p_batch FOR UPDATE SKIP LOCKED
  )
  UPDATE hulagu.outbox_messages AS o
  SET state = 'claimed', attempt_count = o.attempt_count + 1,
      lease_token_hash = p_lease_token_hash,
      lease_expires_at = pg_catalog.now() + pg_catalog.make_interval(secs => p_lease_seconds),
      last_error_class = NULL
  FROM candidates AS c
  WHERE o.tenant_id = v_tenant AND o.id = c.id
  RETURNING o.id, o.delivery_key, o.kind, o.payload, o.attempt_count,
            o.lifecycle_epoch, o.work_epoch;
END
$$;

CREATE FUNCTION hulagu_api.claim_publication(p_publication_id uuid) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE
  v_tenant uuid := NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid;
  v_backup_locked boolean;
BEGIN
  IF v_tenant IS NULL THEN RAISE EXCEPTION 'invalid bounded tenant context'; END IF;
  SELECT b.read_only_mode INTO v_backup_locked
  FROM hulagu.backup_coordination AS b WHERE b.singleton FOR SHARE;
  IF v_backup_locked THEN
    RAISE EXCEPTION 'backup lock held';
  END IF;
  PERFORM 1 FROM hulagu.wiki_publications AS w
  WHERE w.tenant_id = v_tenant AND w.id = p_publication_id AND w.visibility_state = 'staged'
  FOR UPDATE;
  RETURN FOUND;
END
$$;

CREATE OR REPLACE FUNCTION hulagu_api.claim_deletion_delivery(
  p_deletion_id uuid,
  p_delivery_token_hash text
) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE v_route text; v_backup_locked boolean;
BEGIN
  IF p_delivery_token_hash !~ '^[0-9a-f]{64}$' THEN RAISE EXCEPTION 'invalid delivery token'; END IF;
  SELECT b.read_only_mode INTO v_backup_locked
  FROM hulagu.backup_coordination AS b WHERE b.singleton FOR SHARE;
  IF v_backup_locked THEN
    RAISE EXCEPTION 'backup lock held';
  END IF;
  UPDATE hulagu.deletion_jobs AS d
  SET delivery_token_hash = p_delivery_token_hash
  WHERE d.deletion_id = p_deletion_id AND d.state = 'delivery_pending'
    AND d.delivery_token_hash IS NULL AND d.expires_at > pg_catalog.now()
  RETURNING d.encrypted_route INTO v_route;
  RETURN v_route;
END
$$;

CREATE OR REPLACE FUNCTION hulagu_api.claim_retention(p_batch integer DEFAULT 10) RETURNS SETOF uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE
  v_tenant uuid := NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid;
  v_backup_locked boolean;
BEGIN
  IF v_tenant IS NULL OR p_batch NOT BETWEEN 1 AND 100 THEN
    RAISE EXCEPTION 'invalid bounded tenant context';
  END IF;
  SELECT b.read_only_mode INTO v_backup_locked
  FROM hulagu.backup_coordination AS b WHERE b.singleton FOR SHARE;
  IF v_backup_locked THEN
    RAISE EXCEPTION 'backup lock held';
  END IF;
  RETURN QUERY SELECT r.id FROM hulagu.retention_jobs AS r
  WHERE r.tenant_id = v_tenant AND r.state = 'pending'
  ORDER BY r.created_at, r.id LIMIT p_batch FOR UPDATE SKIP LOCKED;
END
$$;

CREATE FUNCTION hulagu_api.record_backup_snapshot(
  p_lock_token_hash text,
  p_database_snapshot_id text,
  p_artifact_manifest jsonb
) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE
  v_backup_id uuid;
  v_manifest_digest text;
  v_entry jsonb;
  v_entry_count integer;
  v_tenant_text text;
  v_generation_text text;
  v_digest text;
BEGIN
  IF p_lock_token_hash !~ '^[0-9a-f]{64}$'
     OR pg_catalog.octet_length(p_database_snapshot_id) NOT BETWEEN 1 AND 256
     OR pg_catalog.jsonb_typeof(p_artifact_manifest) <> 'array'
     OR pg_catalog.octet_length(p_artifact_manifest::text) > 1048576 THEN
    RAISE EXCEPTION 'invalid bounded backup snapshot metadata';
  END IF;
  v_entry_count := pg_catalog.jsonb_array_length(p_artifact_manifest);
  IF v_entry_count NOT BETWEEN 1 AND 10000 THEN
    RAISE EXCEPTION 'invalid bounded backup artifact manifest';
  END IF;
  FOR v_entry IN SELECT value FROM pg_catalog.jsonb_array_elements(p_artifact_manifest)
  LOOP
    IF pg_catalog.jsonb_typeof(v_entry) <> 'object'
       OR (SELECT pg_catalog.count(*) FROM pg_catalog.jsonb_object_keys(v_entry)) <> 3
       OR NOT (v_entry ? 'tenant_id' AND v_entry ? 'generation' AND v_entry ? 'digest')
       OR pg_catalog.jsonb_typeof(v_entry->'tenant_id') <> 'string'
       OR pg_catalog.jsonb_typeof(v_entry->'generation') <> 'number'
       OR pg_catalog.jsonb_typeof(v_entry->'digest') <> 'string' THEN
      RAISE EXCEPTION 'invalid bounded backup artifact manifest';
    END IF;
    v_tenant_text := v_entry->>'tenant_id';
    v_generation_text := v_entry->>'generation';
    v_digest := v_entry->>'digest';
    IF v_tenant_text !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
       OR v_generation_text !~ '^[1-9][0-9]{0,18}$'
       OR (pg_catalog.length(v_generation_text) = 19
           AND v_generation_text > '9223372036854775807')
       OR v_digest !~ '^[0-9a-f]{64}$' THEN
      RAISE EXCEPTION 'invalid bounded backup artifact manifest';
    END IF;
    IF NOT EXISTS (
      SELECT 1 FROM hulagu.wiki_publications AS w
      WHERE w.tenant_id = v_tenant_text::uuid
        AND w.generation = v_generation_text::bigint
        AND w.manifest_digest = v_digest
        AND w.visibility_state IN ('active','superseded')
    ) THEN
      RAISE EXCEPTION 'unpinned backup artifact generation';
    END IF;
  END LOOP;
  IF (
    SELECT pg_catalog.count(*)
    FROM (
      SELECT entry->>'tenant_id', entry->>'generation'
      FROM pg_catalog.jsonb_array_elements(p_artifact_manifest) AS entries(entry)
      GROUP BY entry->>'tenant_id', entry->>'generation'
    ) AS unique_entries
  ) <> v_entry_count THEN
    RAISE EXCEPTION 'duplicate backup artifact generation';
  END IF;
  SELECT b.active_backup_id INTO v_backup_id
  FROM hulagu.backup_coordination AS b
  WHERE b.singleton AND b.read_only_mode AND b.lock_token_hash = p_lock_token_hash
  FOR UPDATE;
  IF v_backup_id IS NULL THEN RAISE EXCEPTION 'invalid backup lock authority'; END IF;
  v_manifest_digest := pg_catalog.encode(public.digest(p_artifact_manifest::text, 'sha256'), 'hex');
  UPDATE hulagu.backup_generations AS g
  SET state = 'snapshot_recorded', database_snapshot_id = p_database_snapshot_id,
      artifact_manifest = p_artifact_manifest, artifact_manifest_digest = v_manifest_digest,
      snapshot_recorded_at = pg_catalog.now()
  WHERE g.backup_id = v_backup_id AND g.state = 'locked';
  IF NOT FOUND THEN RAISE EXCEPTION 'backup snapshot already recorded'; END IF;
  RETURN v_manifest_digest;
END
$$;

CREATE FUNCTION hulagu_api.release_backup_coordination(p_lock_token_hash text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE v_backup_id uuid;
BEGIN
  IF p_lock_token_hash !~ '^[0-9a-f]{64}$' THEN RAISE EXCEPTION 'invalid backup lock authority'; END IF;
  SELECT b.active_backup_id INTO v_backup_id
  FROM hulagu.backup_coordination AS b
  WHERE b.singleton AND b.read_only_mode AND b.lock_token_hash = p_lock_token_hash
  FOR UPDATE;
  IF v_backup_id IS NULL THEN RAISE EXCEPTION 'invalid backup lock authority'; END IF;
  UPDATE hulagu.backup_generations AS g
  SET state = 'released', released_at = pg_catalog.now()
  WHERE g.backup_id = v_backup_id AND g.state = 'snapshot_recorded';
  IF NOT FOUND THEN RAISE EXCEPTION 'backup snapshot not recorded'; END IF;
  UPDATE hulagu.backup_coordination AS b
  SET read_only_mode = false, active_backup_id = NULL, lock_token_hash = NULL,
      locked_at = NULL, updated_at = pg_catalog.now()
  WHERE b.singleton;
  RETURN true;
END
$$;

REVOKE ALL ON FUNCTION hulagu_api.begin_backup_coordination(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION hulagu_api.claim_publication(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION hulagu_api.claim_deletion_delivery(uuid,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION hulagu_api.claim_retention(integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION hulagu_api.record_backup_snapshot(text,text,jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION hulagu_api.release_backup_coordination(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION hulagu_api.begin_backup_coordination(text) TO hulagu_migrator;
GRANT EXECUTE ON FUNCTION hulagu_api.claim_publication(uuid) TO hulagu_app;
GRANT EXECUTE ON FUNCTION hulagu_api.claim_deletion_delivery(uuid,text) TO hulagu_deletion;
GRANT EXECUTE ON FUNCTION hulagu_api.claim_retention(integer) TO hulagu_app;
GRANT EXECUTE ON FUNCTION hulagu_api.record_backup_snapshot(text,text,jsonb) TO hulagu_migrator;
GRANT EXECUTE ON FUNCTION hulagu_api.release_backup_coordination(text) TO hulagu_migrator;
RESET ROLE;
