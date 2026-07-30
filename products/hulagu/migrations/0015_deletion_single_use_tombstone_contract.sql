SET ROLE hulagu_owner;
SET search_path = pg_catalog;

-- A plaintext legacy fence cannot be converted into authenticated ciphertext
-- without the original tombstone key authority. Refuse the migration before
-- changing any catalog object rather than relabeling an unsafe value.
DO $migration$
BEGIN
  IF EXISTS (SELECT 1 FROM hulagu.deletion_tombstones) THEN
    RAISE EXCEPTION
      'unsafe legacy plaintext deletion tombstones require authenticated conversion';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM hulagu.deletion_jobs
    WHERE state IN ('pending', 'erasing', 'delivery_pending')
  ) THEN
    RAISE EXCEPTION
      'active pre-0015 deletion jobs require authenticated completion before upgrade';
  END IF;
END
$migration$;

ALTER TABLE hulagu.tenants
  ADD COLUMN deletion_nonce_hash text
    CHECK (deletion_nonce_hash IS NULL OR deletion_nonce_hash ~ '^[0-9a-f]{64}$');

ALTER TABLE hulagu.deletion_jobs
  ADD COLUMN encrypted_subject_digest text
    CHECK (
      encrypted_subject_digest IS NULL
      OR (
        pg_catalog.octet_length(encrypted_subject_digest) BETWEEN 117 AND 4096
        AND encrypted_subject_digest ~
          '^hts1\.[1-9][0-9]*\.[0-9a-f]{64}\.[A-Za-z0-9_-]{112,}={0,2}$'
      )
    ),
  ADD COLUMN deletion_epoch bigint
    CHECK (deletion_epoch IS NULL OR deletion_epoch > 0),
  ADD COLUMN erasure_token_hash text
    CHECK (erasure_token_hash IS NULL OR erasure_token_hash ~ '^[0-9a-f]{64}$'),
  ADD COLUMN delivery_claimed_at timestamptz;

ALTER TABLE hulagu.deletion_jobs
  DROP CONSTRAINT deletion_jobs_check,
  ADD CONSTRAINT deletion_jobs_minimized_state_check CHECK (
    (state IN ('pending', 'erasing') AND target_tenant_id IS NOT NULL)
    OR (state = 'delivery_pending' AND target_tenant_id IS NULL)
    OR (
      state IN ('complete', 'failed')
      AND target_tenant_id IS NULL
      AND encrypted_route IS NULL
    )
  );

ALTER TABLE hulagu.deletion_receipts
  DROP CONSTRAINT deletion_receipts_outcome_check,
  ADD CONSTRAINT deletion_receipts_outcome_check
    CHECK (outcome IN ('delivered', 'delivery_unknown', 'failed', 'expired'));

-- Direct owner/migrator writes cannot create two live workflows for one target,
-- even if they bypass the request function.
CREATE UNIQUE INDEX deletion_jobs_one_active_target_idx
  ON hulagu.deletion_jobs (target_tenant_id)
  WHERE target_tenant_id IS NOT NULL
    AND state IN ('pending', 'erasing', 'delivery_pending');

DROP TABLE hulagu.deletion_tombstones;

-- The retained tombstone has the exact JSON-contract semantics and no tenant,
-- route, plaintext fence, ordinary lookup digest, or customer-content column.
CREATE TABLE hulagu.deletion_tombstones (
  schema_version text NOT NULL
    CHECK (schema_version = 'DeletionTombstone/v1'),
  encrypted_subject_digest text PRIMARY KEY
    CHECK (
      pg_catalog.octet_length(encrypted_subject_digest) BETWEEN 117 AND 4096
      AND encrypted_subject_digest ~
        '^hts1\.[1-9][0-9]*\.[0-9a-f]{64}\.[A-Za-z0-9_-]{112,}={0,2}$'
    ),
  deletion_epoch bigint NOT NULL CHECK (deletion_epoch > 0),
  completed_at timestamptz NOT NULL,
  backup_expiry_horizon timestamptz NOT NULL,
  rekey_state text NOT NULL CHECK (rekey_state IN ('current', 'pending')),
  CHECK (backup_expiry_horizon > completed_at)
);

CREATE INDEX deletion_tombstones_expiry_idx
  ON hulagu.deletion_tombstones (backup_expiry_horizon, encrypted_subject_digest);

-- The database fence key is global privileged control state. Runtime roles have
-- no table grant; only the fixed-path matcher and encryptor below may use it.
CREATE TABLE hulagu.tombstone_fence_keys (
  key_version integer PRIMARY KEY CHECK (key_version > 0),
  encryption_key text NOT NULL CHECK (encryption_key ~ '^[0-9a-f]{64}$'),
  lookup_key text NOT NULL CHECK (lookup_key ~ '^[0-9a-f]{64}$'),
  active boolean NOT NULL DEFAULT false
);

CREATE UNIQUE INDEX tombstone_fence_one_active_key_idx
  ON hulagu.tombstone_fence_keys ((active))
  WHERE active;

INSERT INTO hulagu.tombstone_fence_keys(
  key_version,
  encryption_key,
  lookup_key,
  active
) VALUES (
  1,
  pg_catalog.encode(public.gen_random_bytes(32), 'hex'),
  pg_catalog.encode(public.gen_random_bytes(32), 'hex'),
  true
);

CREATE FUNCTION hulagu_api.encrypt_deletion_subject_fence(
  p_subject_fence_digest text
) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE
  v_key hulagu.tombstone_fence_keys%ROWTYPE;
  v_lookup text;
  v_ciphertext bytea;
  v_encoded text;
BEGIN
  IF p_subject_fence_digest !~ '^[0-9a-f]{64}$' THEN
    RAISE EXCEPTION 'invalid deletion subject fence';
  END IF;
  SELECT * INTO STRICT v_key
  FROM hulagu.tombstone_fence_keys AS k
  WHERE k.active
  FOR SHARE;
  v_lookup := pg_catalog.encode(
    public.hmac(
      pg_catalog.convert_to(p_subject_fence_digest, 'UTF8'),
      pg_catalog.decode(v_key.lookup_key, 'hex'),
      'sha256'
    ),
    'hex'
  );
  v_ciphertext := public.pgp_sym_encrypt(
    v_lookup || ':' || p_subject_fence_digest,
    v_key.encryption_key,
    'cipher-algo=aes256,compress-algo=0'
  );
  v_encoded := pg_catalog.translate(
    pg_catalog.replace(pg_catalog.encode(v_ciphertext, 'base64'), E'\n', ''),
    '+/',
    '-_'
  );
  RETURN 'hts1.' || v_key.key_version::text || '.' || v_lookup || '.' || v_encoded;
END
$$;

CREATE FUNCTION hulagu_api.subject_fence_is_barred(
  p_subject_fence_digest text
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE
  v_candidate record;
  v_lookup text;
  v_plaintext text;
BEGIN
  IF p_subject_fence_digest !~ '^[0-9a-f]{64}$' THEN
    RAISE EXCEPTION 'invalid deletion subject fence';
  END IF;
  FOR v_candidate IN
    SELECT d.encrypted_subject_digest, k.encryption_key, k.lookup_key
    FROM hulagu.deletion_tombstones AS d
    JOIN hulagu.tombstone_fence_keys AS k
      ON k.key_version::text =
        pg_catalog.split_part(d.encrypted_subject_digest, '.', 2)
    WHERE d.backup_expiry_horizon > pg_catalog.now()
      AND d.rekey_state IN ('current', 'pending')
  LOOP
    v_lookup := pg_catalog.encode(
      public.hmac(
        pg_catalog.convert_to(p_subject_fence_digest, 'UTF8'),
        pg_catalog.decode(v_candidate.lookup_key, 'hex'),
        'sha256'
      ),
      'hex'
    );
    IF pg_catalog.split_part(v_candidate.encrypted_subject_digest, '.', 3) <> v_lookup THEN
      CONTINUE;
    END IF;
    BEGIN
      v_plaintext := public.pgp_sym_decrypt(
        pg_catalog.decode(
          pg_catalog.translate(
            pg_catalog.split_part(v_candidate.encrypted_subject_digest, '.', 4),
            '-_',
            '+/'
          ),
          'base64'
        ),
        v_candidate.encryption_key
      );
    EXCEPTION WHEN OTHERS THEN
      RAISE EXCEPTION 'invalid authenticated deletion tombstone';
    END;
    IF v_plaintext <> v_lookup || ':' || p_subject_fence_digest THEN
      RAISE EXCEPTION 'invalid authenticated deletion tombstone';
    END IF;
    RETURN true;
  END LOOP;
  RETURN false;
END
$$;

-- Migration 0011 persisted this real-app ingress authority with a direct query
-- against the legacy plaintext tombstone columns. Forward-replace it after the
-- privileged matcher exists so the frozen ingress behavior survives this table
-- contract replacement without exposing plaintext compatibility columns.
CREATE OR REPLACE FUNCTION hulagu_api.admit_telegram_enrollment_ingress(
  p_bot_id bigint,
  p_update_id bigint,
  p_callback_query_id text,
  p_next_update_id bigint,
  p_subject_digest text,
  p_subject_fence_digest text,
  p_notice_version text,
  p_consent_nonce_hash text,
  p_enrollment_expires_at timestamptz,
  p_ingress_expires_at timestamptz,
  p_per_subject_limit integer,
  p_global_limit integer,
  p_window_seconds integer
) RETURNS TABLE(outcome text, enrollment_id uuid)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE
  v_now timestamptz := pg_catalog.now();
  v_enrollment hulagu.enrollments%ROWTYPE;
  v_enrollment_id uuid;
  v_subject_count integer := 0;
  v_global_count integer;
  v_window interval;
  v_outcome text;
BEGIN
  IF p_bot_id <= 0 OR p_update_id < 0 OR p_update_id >= 9223372036854775807
     OR p_next_update_id <> p_update_id + 1 THEN
    RAISE EXCEPTION 'invalid update authority';
  END IF;
  IF p_callback_query_id IS NOT NULL
     AND pg_catalog.octet_length(p_callback_query_id) NOT BETWEEN 1 AND 256 THEN
    RAISE EXCEPTION 'invalid callback authority';
  END IF;
  IF p_subject_digest !~ '^[0-9a-f]{64}$'
     OR p_subject_fence_digest !~ '^[0-9a-f]{64}$'
     OR p_consent_nonce_hash !~ '^[0-9a-f]{64}$'
     OR pg_catalog.octet_length(p_notice_version) NOT BETWEEN 1 AND 128 THEN
    RAISE EXCEPTION 'invalid enrollment authority';
  END IF;
  IF p_enrollment_expires_at <= v_now
     OR p_enrollment_expires_at > v_now + interval '1 day'
     OR p_ingress_expires_at <= v_now
     OR p_ingress_expires_at > v_now + interval '90 days'
     OR p_per_subject_limit NOT BETWEEN 1 AND 1000
     OR p_global_limit NOT BETWEEN 1 AND 100000
     OR p_window_seconds NOT BETWEEN 1 AND 86400 THEN
    RAISE EXCEPTION 'invalid bounded ingress metadata';
  END IF;
  v_window := pg_catalog.make_interval(secs => p_window_seconds);

  INSERT INTO hulagu.telegram_polling_offsets(bot_id, next_update_id)
  VALUES (p_bot_id, 0)
  ON CONFLICT (bot_id) DO NOTHING;
  PERFORM 1 FROM hulagu.telegram_polling_offsets AS o
  WHERE o.bot_id = p_bot_id FOR UPDATE;

  SELECT i.enrollment_id INTO v_enrollment_id
  FROM hulagu.inbound_updates AS i
  WHERE i.bot_id = p_bot_id AND i.update_id = p_update_id;
  IF FOUND THEN
    RETURN QUERY SELECT 'duplicate_update'::text, v_enrollment_id;
    RETURN;
  END IF;

  IF p_callback_query_id IS NOT NULL THEN
    SELECT i.enrollment_id INTO v_enrollment_id
    FROM hulagu.inbound_updates AS i
    WHERE i.bot_id = p_bot_id AND i.callback_query_id = p_callback_query_id;
    IF FOUND THEN
      UPDATE hulagu.telegram_polling_offsets AS o
      SET next_update_id = GREATEST(o.next_update_id, p_next_update_id),
          updated_at = v_now
      WHERE o.bot_id = p_bot_id;
      RETURN QUERY SELECT 'duplicate_callback'::text, v_enrollment_id;
      RETURN;
    END IF;
  END IF;

  IF hulagu_api.subject_fence_is_barred(p_subject_fence_digest) THEN
    RAISE EXCEPTION 're-enrollment barred';
  END IF;

  SELECT e.* INTO v_enrollment
  FROM hulagu.enrollments AS e
  WHERE e.subject_digest = p_subject_digest
  FOR UPDATE;
  IF FOUND AND v_enrollment.expires_at > v_now THEN
    v_enrollment_id := v_enrollment.id;
    IF v_enrollment.subject_fence_digest <> p_subject_fence_digest
       OR v_enrollment.notice_version <> p_notice_version
       OR v_enrollment.consent_nonce_hash <> p_consent_nonce_hash THEN
      RAISE EXCEPTION 'conflicting enrollment authority';
    END IF;
    IF v_enrollment.rate_window_started_at > v_now - v_window THEN
      v_subject_count := v_enrollment.rate_count;
    END IF;
  ELSE
    v_enrollment_id := NULL;
  END IF;

  INSERT INTO hulagu.telegram_preconsent_windows(
    bot_id, window_started_at, admitted_count
  ) VALUES (p_bot_id, v_now, 0)
  ON CONFLICT (bot_id) DO NOTHING;
  SELECT
    CASE
      WHEN w.window_started_at > v_now - v_window THEN w.admitted_count
      ELSE 0
    END
  INTO v_global_count
  FROM hulagu.telegram_preconsent_windows AS w
  WHERE w.bot_id = p_bot_id
  FOR UPDATE;

  IF v_subject_count >= p_per_subject_limit OR v_global_count >= p_global_limit THEN
    INSERT INTO hulagu.inbound_updates(
      bot_id, update_id, callback_query_id, enrollment_id,
      outcome_class, expires_at
    ) VALUES (
      p_bot_id, p_update_id, p_callback_query_id, v_enrollment_id,
      'rate_limited', p_ingress_expires_at
    );
    UPDATE hulagu.telegram_polling_offsets AS o
    SET next_update_id = GREATEST(o.next_update_id, p_next_update_id),
        updated_at = v_now
    WHERE o.bot_id = p_bot_id;
    RETURN QUERY SELECT 'rate_limited'::text, v_enrollment_id;
    RETURN;
  END IF;

  IF v_enrollment_id IS NULL THEN
    IF v_enrollment.id IS NULL THEN
      INSERT INTO hulagu.enrollments(
        subject_digest, subject_fence_digest, notice_version,
        consent_nonce_hash, expires_at, rate_count, rate_window_started_at
      ) VALUES (
        p_subject_digest, p_subject_fence_digest, p_notice_version,
        p_consent_nonce_hash, p_enrollment_expires_at, 1, v_now
      ) RETURNING id INTO v_enrollment_id;
    ELSE
      UPDATE hulagu.enrollments AS e
      SET subject_fence_digest = p_subject_fence_digest,
          notice_version = p_notice_version,
          consent_nonce_hash = p_consent_nonce_hash,
          expires_at = p_enrollment_expires_at,
          rate_count = 1,
          rate_window_started_at = v_now
      WHERE e.id = v_enrollment.id
      RETURNING e.id INTO v_enrollment_id;
    END IF;
    v_outcome := 'enrollment_started';
  ELSE
    UPDATE hulagu.enrollments AS e
    SET rate_count = v_subject_count + 1,
        rate_window_started_at = CASE
          WHEN e.rate_window_started_at > v_now - v_window THEN e.rate_window_started_at
          ELSE v_now
        END
    WHERE e.id = v_enrollment_id;
    v_outcome := 'enrollment_resumed';
  END IF;

  UPDATE hulagu.telegram_preconsent_windows AS w
  SET window_started_at = CASE
        WHEN w.window_started_at > v_now - v_window THEN w.window_started_at
        ELSE v_now
      END,
      admitted_count = v_global_count + 1,
      updated_at = v_now
  WHERE w.bot_id = p_bot_id;

  INSERT INTO hulagu.inbound_updates(
    bot_id, update_id, callback_query_id, enrollment_id,
    outcome_class, expires_at
  ) VALUES (
    p_bot_id, p_update_id, p_callback_query_id, v_enrollment_id,
    v_outcome, p_ingress_expires_at
  );
  UPDATE hulagu.telegram_polling_offsets AS o
  SET next_update_id = GREATEST(o.next_update_id, p_next_update_id),
      updated_at = v_now
  WHERE o.bot_id = p_bot_id;
  RETURN QUERY SELECT v_outcome, v_enrollment_id;
END
$$;

CREATE OR REPLACE FUNCTION hulagu_api.resolve_enrollment(
  p_subject_digest text,
  p_subject_fence_digest text,
  p_notice_version text,
  p_consent_nonce_hash text,
  p_expires_at timestamptz
) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE v_id uuid;
BEGIN
  IF p_subject_digest !~ '^[0-9a-f]{64}$'
     OR p_subject_fence_digest !~ '^[0-9a-f]{64}$'
     OR p_consent_nonce_hash !~ '^[0-9a-f]{64}$'
     OR p_expires_at <= pg_catalog.now() THEN
    RAISE EXCEPTION 'invalid enrollment input';
  END IF;
  IF hulagu_api.subject_fence_is_barred(p_subject_fence_digest) THEN
    RAISE EXCEPTION 're-enrollment barred';
  END IF;
  INSERT INTO hulagu.enrollments(
    subject_digest,
    subject_fence_digest,
    notice_version,
    consent_nonce_hash,
    expires_at
  ) VALUES (
    p_subject_digest,
    p_subject_fence_digest,
    p_notice_version,
    p_consent_nonce_hash,
    p_expires_at
  )
  ON CONFLICT (subject_digest) DO UPDATE
    SET notice_version = EXCLUDED.notice_version,
        subject_fence_digest = EXCLUDED.subject_fence_digest,
        consent_nonce_hash = EXCLUDED.consent_nonce_hash,
        expires_at = EXCLUDED.expires_at,
        rate_count = LEAST(hulagu.enrollments.rate_count + 1, 1000)
  RETURNING id INTO v_id;
  RETURN v_id;
END
$$;

CREATE OR REPLACE FUNCTION hulagu_api.promote_consented_enrollment(
  p_enrollment_id uuid,
  p_notice_version text,
  p_consent_nonce_hash text
) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE
  v_enrollment hulagu.enrollments%ROWTYPE;
  v_tenant uuid;
BEGIN
  SELECT * INTO v_enrollment
  FROM hulagu.enrollments
  WHERE id = p_enrollment_id
  FOR UPDATE;
  IF NOT FOUND OR v_enrollment.expires_at <= pg_catalog.now()
     OR v_enrollment.notice_version <> p_notice_version
     OR v_enrollment.consent_nonce_hash <> p_consent_nonce_hash THEN
    RAISE EXCEPTION 'invalid or consumed consent authority';
  END IF;
  IF hulagu_api.subject_fence_is_barred(v_enrollment.subject_fence_digest) THEN
    RAISE EXCEPTION 're-enrollment barred';
  END IF;
  v_tenant := public.gen_random_uuid();
  PERFORM pg_catalog.set_config('app.tenant_id', v_tenant::text, true);
  INSERT INTO hulagu.tenants(id, state) VALUES (v_tenant, 'READY');
  INSERT INTO hulagu.identity_bindings(
    tenant_id,
    subject_digest,
    subject_fence_digest
  ) VALUES (
    v_tenant,
    v_enrollment.subject_digest,
    v_enrollment.subject_fence_digest
  );
  UPDATE hulagu.inbound_updates
  SET enrollment_id = NULL, tenant_id = v_tenant
  WHERE enrollment_id = p_enrollment_id;
  DELETE FROM hulagu.enrollments WHERE id = p_enrollment_id;
  RETURN v_tenant;
END
$$;

CREATE OR REPLACE FUNCTION hulagu_api.resolve_existing_tenant(
  p_subject_digest text
) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE v_tenant uuid;
BEGIN
  SELECT tenant_id INTO v_tenant
  FROM hulagu.identity_bindings
  WHERE subject_digest = p_subject_digest;
  IF v_tenant IS NULL THEN
    RETURN NULL;
  END IF;
  PERFORM pg_catalog.set_config('app.tenant_id', v_tenant::text, true);
  IF NOT EXISTS (
    SELECT 1
    FROM hulagu.tenants
    WHERE id = v_tenant
      AND state IN ('READY', 'INTERVIEWING', 'PAUSED')
  ) THEN
    RETURN NULL;
  END IF;
  RETURN v_tenant;
END
$$;

REVOKE ALL ON FUNCTION hulagu_api.request_deletion(text,text)
  FROM PUBLIC, hulagu_app, hulagu_runner, hulagu_deletion, hulagu_readonly;
DROP FUNCTION hulagu_api.request_deletion(text,text);

-- The only effective request API compares the stored single-use hash while
-- holding the tenant row, consumes it in the READY->DELETING CAS, and records
-- the incremented lifecycle epoch in the one active global workflow.
CREATE FUNCTION hulagu_api.request_deletion(
  p_deletion_nonce_hash text,
  p_encrypted_route text,
  p_route_binding_digest text
) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE
  v_tenant uuid :=
    NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid;
  v_fence text;
  v_encrypted_fence text;
  v_deletion_epoch bigint;
  v_deletion uuid;
BEGIN
  IF v_tenant IS NULL
     OR p_deletion_nonce_hash !~ '^[0-9a-f]{64}$'
     OR pg_catalog.octet_length(p_encrypted_route) NOT BETWEEN 1 AND 4096
     OR p_route_binding_digest !~ '^[0-9a-f]{64}$' THEN
    RAISE EXCEPTION 'invalid deletion request';
  END IF;
  SELECT e.subject_fence_digest INTO v_fence
  FROM hulagu.identity_bindings AS e
  WHERE e.tenant_id = v_tenant
  ORDER BY e.id
  LIMIT 1;
  IF v_fence IS NULL THEN
    RAISE EXCEPTION 'invalid deletion request';
  END IF;
  v_encrypted_fence :=
    hulagu_api.encrypt_deletion_subject_fence(v_fence);
  UPDATE hulagu.tenants AS t
  SET state = 'DELETING',
      lifecycle_epoch = t.lifecycle_epoch + 1,
      deletion_nonce_hash = NULL,
      updated_at = pg_catalog.now()
  WHERE t.id = v_tenant
    AND t.state = 'READY'
    AND t.deletion_nonce_hash = p_deletion_nonce_hash
  RETURNING t.lifecycle_epoch INTO v_deletion_epoch;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'invalid or consumed deletion authority';
  END IF;
  UPDATE hulagu.search_runs AS r
  SET state = 'cancelled', work_epoch = r.work_epoch + 1
  WHERE r.tenant_id = v_tenant
    AND r.state NOT IN ('complete', 'cancelled');
  UPDATE hulagu.outbox_messages AS o
  SET state = 'cancelled',
      lease_token_hash = NULL,
      lease_expires_at = NULL
  WHERE o.tenant_id = v_tenant
    AND o.kind = 'ordinary'
    AND o.state IN ('pending', 'claimed', 'failed');
  INSERT INTO hulagu.deletion_jobs(
    target_tenant_id,
    subject_fence_digest,
    encrypted_subject_digest,
    deletion_epoch,
    encrypted_route,
    route_binding_digest,
    state,
    expires_at
  ) VALUES (
    v_tenant,
    NULL,
    v_encrypted_fence,
    v_deletion_epoch,
    p_encrypted_route,
    p_route_binding_digest,
    'pending',
    pg_catalog.now() + interval '30 days'
  )
  RETURNING deletion_id INTO v_deletion;
  RETURN v_deletion;
END
$$;

CREATE FUNCTION hulagu_api.claim_deletion_erasure(
  p_deletion_id uuid,
  p_erasure_token_hash text
) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE
  v_job hulagu.deletion_jobs%ROWTYPE;
  v_backup_locked boolean;
BEGIN
  IF p_erasure_token_hash !~ '^[0-9a-f]{64}$' THEN
    RAISE EXCEPTION 'invalid erasure token';
  END IF;
  SELECT b.read_only_mode INTO v_backup_locked
  FROM hulagu.backup_coordination AS b WHERE b.singleton FOR SHARE;
  IF v_backup_locked THEN
    RAISE EXCEPTION 'backup lock held';
  END IF;
  SELECT * INTO v_job FROM hulagu.deletion_jobs
  WHERE deletion_id = p_deletion_id FOR UPDATE;
  IF NOT FOUND OR v_job.expires_at <= pg_catalog.now() THEN
    RETURN NULL;
  END IF;
  IF v_job.state = 'pending' AND v_job.erasure_token_hash IS NULL THEN
    UPDATE hulagu.deletion_jobs
    SET state = 'erasing', erasure_token_hash = p_erasure_token_hash
    WHERE deletion_id = p_deletion_id;
    RETURN v_job.target_tenant_id;
  END IF;
  IF v_job.state = 'erasing'
     AND v_job.erasure_token_hash = p_erasure_token_hash THEN
    RETURN v_job.target_tenant_id;
  END IF;
  RETURN NULL;
END
$$;

CREATE FUNCTION hulagu_api.complete_deletion_erasure(
  p_deletion_id uuid,
  p_erasure_token text
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE v_job hulagu.deletion_jobs%ROWTYPE;
BEGIN
  SELECT * INTO v_job FROM hulagu.deletion_jobs
  WHERE deletion_id = p_deletion_id FOR UPDATE;
  IF NOT FOUND OR v_job.state <> 'erasing'
     OR v_job.expires_at <= pg_catalog.now()
     OR v_job.encrypted_subject_digest IS NULL
     OR v_job.deletion_epoch IS NULL
     OR v_job.erasure_token_hash <>
       pg_catalog.encode(public.digest(p_erasure_token, 'sha256'), 'hex') THEN
    RETURN false;
  END IF;
  UPDATE hulagu.inbound_updates
  SET enrollment_id = NULL,
      tenant_id = NULL,
      outcome_class = 'terminal_dedupe'
  WHERE tenant_id = v_job.target_tenant_id;
  DELETE FROM hulagu.tenants WHERE id = v_job.target_tenant_id;
  UPDATE hulagu.deletion_jobs
  SET target_tenant_id = NULL,
      subject_fence_digest = NULL,
      erasure_token_hash = NULL,
      state = 'delivery_pending'
  WHERE deletion_id = p_deletion_id AND state = 'erasing';
  RETURN FOUND;
END
$$;

CREATE OR REPLACE FUNCTION hulagu_api.claim_deletion_delivery(
  p_deletion_id uuid,
  p_delivery_token_hash text
) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE
  v_job hulagu.deletion_jobs%ROWTYPE;
  v_route text;
  v_backup_locked boolean;
BEGIN
  IF p_delivery_token_hash !~ '^[0-9a-f]{64}$' THEN
    RAISE EXCEPTION 'invalid delivery token';
  END IF;
  SELECT b.read_only_mode INTO v_backup_locked
  FROM hulagu.backup_coordination AS b WHERE b.singleton FOR SHARE;
  IF v_backup_locked THEN
    RAISE EXCEPTION 'backup lock held';
  END IF;
  SELECT * INTO v_job FROM hulagu.deletion_jobs
  WHERE deletion_id = p_deletion_id FOR UPDATE;
  IF NOT FOUND OR v_job.state <> 'delivery_pending'
     OR v_job.expires_at <= pg_catalog.now() THEN
    RETURN NULL;
  END IF;
  IF v_job.encrypted_route IS NOT NULL
     AND v_job.delivery_token_hash IS NULL THEN
    v_route := v_job.encrypted_route;
    UPDATE hulagu.deletion_jobs
    SET encrypted_route = NULL,
        delivery_token_hash = p_delivery_token_hash,
        delivery_claimed_at = pg_catalog.now()
    WHERE deletion_id = p_deletion_id;
    RETURN pg_catalog.jsonb_build_object(
      'status', 'claimed', 'encrypted_route', v_route
    )::text;
  END IF;
  IF v_job.encrypted_route IS NULL
     AND (
       v_job.delivery_token_hash = p_delivery_token_hash
       OR v_job.delivery_claimed_at <= pg_catalog.now() - interval '5 minutes'
     ) THEN
    UPDATE hulagu.deletion_jobs
    SET delivery_token_hash = p_delivery_token_hash,
        delivery_claimed_at = pg_catalog.now()
    WHERE deletion_id = p_deletion_id;
    RETURN pg_catalog.jsonb_build_object('status', 'ambiguous')::text;
  END IF;
  RETURN NULL;
END
$$;

REVOKE ALL ON FUNCTION hulagu_api.complete_deletion_delivery(uuid,text)
  FROM PUBLIC, hulagu_app, hulagu_runner, hulagu_deletion, hulagu_readonly;
DROP FUNCTION hulagu_api.complete_deletion_delivery(uuid,text);
REVOKE ALL ON FUNCTION hulagu_api.finalize_deletion(uuid,text)
  FROM PUBLIC, hulagu_app, hulagu_runner, hulagu_deletion, hulagu_readonly;
DROP FUNCTION hulagu_api.finalize_deletion(uuid,text);

CREATE FUNCTION hulagu_api.finalize_deletion(
  p_deletion_id uuid,
  p_delivery_token text,
  p_outcome text
) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE
  v_job hulagu.deletion_jobs%ROWTYPE;
  v_completed_at timestamptz;
  v_existing_outcome text;
BEGIN
  IF p_outcome NOT IN ('delivered', 'delivery_unknown', 'failed', 'expired') THEN
    RAISE EXCEPTION 'invalid deletion delivery outcome';
  END IF;
  SELECT * INTO v_job FROM hulagu.deletion_jobs
  WHERE deletion_id = p_deletion_id FOR UPDATE;
  IF NOT FOUND THEN
    RETURN NULL;
  END IF;
  IF v_job.state = 'complete' THEN
    SELECT r.outcome INTO v_existing_outcome
    FROM hulagu.deletion_receipts AS r
    WHERE r.deletion_id = p_deletion_id;
    RETURN v_existing_outcome;
  END IF;
  IF v_job.state <> 'delivery_pending'
     OR v_job.encrypted_route IS NOT NULL
     OR v_job.encrypted_subject_digest IS NULL
     OR v_job.deletion_epoch IS NULL
     OR v_job.delivery_token_hash <>
       pg_catalog.encode(public.digest(p_delivery_token, 'sha256'), 'hex') THEN
    RETURN NULL;
  END IF;
  v_completed_at := pg_catalog.now();
  INSERT INTO hulagu.deletion_tombstones(
    schema_version, encrypted_subject_digest, deletion_epoch,
    completed_at, backup_expiry_horizon, rekey_state
  ) VALUES (
    'DeletionTombstone/v1', v_job.encrypted_subject_digest,
    v_job.deletion_epoch, v_completed_at,
    v_completed_at + interval '97 days', 'current'
  );
  INSERT INTO hulagu.deletion_receipts(
    deletion_id, outcome, completed_at, expires_at
  ) VALUES (
    p_deletion_id, p_outcome, v_completed_at,
    v_completed_at + interval '365 days'
  );
  UPDATE hulagu.deletion_jobs
  SET target_tenant_id = NULL,
      subject_fence_digest = NULL,
      encrypted_subject_digest = NULL,
      encrypted_route = NULL,
      route_binding_digest = NULL,
      erasure_token_hash = NULL,
      delivery_token_hash = NULL,
      delivery_claimed_at = NULL,
      state = 'complete'
  WHERE deletion_id = p_deletion_id AND state = 'delivery_pending';
  IF NOT FOUND THEN
    RAISE EXCEPTION 'deletion terminal state changed unexpectedly';
  END IF;
  RETURN p_outcome;
END
$$;

CREATE FUNCTION hulagu_api.complete_deletion_delivery(
  p_deletion_id uuid,
  p_delivery_token text,
  p_outcome text
) RETURNS text
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog
AS $$
  SELECT hulagu_api.finalize_deletion(
    p_deletion_id, p_delivery_token, p_outcome
  )
$$;

CREATE FUNCTION hulagu_api.deletion_delivery_outcome(
  p_deletion_id uuid
) RETURNS text
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog
AS $$
  SELECT r.outcome
  FROM hulagu.deletion_receipts AS r
  WHERE r.deletion_id = p_deletion_id
$$;

REVOKE ALL ON TABLE
  hulagu.deletion_tombstones,
  hulagu.tombstone_fence_keys
FROM PUBLIC, hulagu_app, hulagu_runner, hulagu_deletion, hulagu_readonly;

REVOKE ALL ON ALL FUNCTIONS IN SCHEMA hulagu_api FROM PUBLIC;
REVOKE ALL ON FUNCTION
  hulagu_api.encrypt_deletion_subject_fence(text),
  hulagu_api.subject_fence_is_barred(text)
FROM hulagu_app, hulagu_runner, hulagu_deletion, hulagu_readonly;

GRANT EXECUTE ON FUNCTION
  hulagu_api.resolve_enrollment(text,text,text,text,timestamptz),
  hulagu_api.promote_consented_enrollment(uuid,text,text),
  hulagu_api.resolve_existing_tenant(text),
  hulagu_api.request_deletion(text,text,text)
TO hulagu_app;

GRANT EXECUTE ON FUNCTION
  hulagu_api.claim_deletion_erasure(uuid,text),
  hulagu_api.complete_deletion_erasure(uuid,text),
  hulagu_api.claim_deletion_delivery(uuid,text),
  hulagu_api.finalize_deletion(uuid,text,text),
  hulagu_api.complete_deletion_delivery(uuid,text,text),
  hulagu_api.deletion_delivery_outcome(uuid)
TO hulagu_deletion;

RESET ROLE;
