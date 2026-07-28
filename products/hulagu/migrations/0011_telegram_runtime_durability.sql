SET ROLE hulagu_owner;
SET search_path = pg_catalog;

-- Per-bot global pre-consent admission state. The polling-offset row serializes
-- every ingress decision for the bot, so this counter and the normalized ingress
-- effect advance atomically without trusting caller-installed tenant context.
CREATE TABLE hulagu.telegram_preconsent_windows (
  bot_id bigint PRIMARY KEY CHECK (bot_id > 0),
  window_started_at timestamptz NOT NULL,
  admitted_count integer NOT NULL CHECK (admitted_count BETWEEN 0 AND 100000),
  updated_at timestamptz NOT NULL DEFAULT pg_catalog.now()
);
REVOKE ALL ON hulagu.telegram_preconsent_windows FROM PUBLIC;

ALTER TABLE hulagu.enrollments
  ADD COLUMN rate_window_started_at timestamptz NOT NULL DEFAULT pg_catalog.now();

-- A globally limited first contact has no enrollment or tenant authority yet but
-- still needs a normalized durable replay marker. Existing rate-limited subjects
-- may retain their enrollment reference.
ALTER TABLE hulagu.inbound_updates DROP CONSTRAINT inbound_updates_check;
ALTER TABLE hulagu.inbound_updates
  ADD CONSTRAINT inbound_updates_authority_check CHECK (
    (
      outcome_class NOT IN ('terminal_dedupe', 'rate_limited')
      AND ((enrollment_id IS NOT NULL)::integer + (tenant_id IS NOT NULL)::integer) = 1
    )
    OR (
      outcome_class = 'terminal_dedupe'
      AND enrollment_id IS NULL
      AND tenant_id IS NULL
    )
    OR (
      outcome_class = 'rate_limited'
      AND ((enrollment_id IS NOT NULL)::integer + (tenant_id IS NOT NULL)::integer) <= 1
    )
  );

-- This is the sole bounded pre-consent ingress authority Task 3 must consume.
-- Durable update/callback replay checks happen after the bot lock but before any
-- enrollment or rate-window mutation. Tenant identity is never an input.
CREATE FUNCTION hulagu_api.admit_telegram_enrollment_ingress(
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

  IF EXISTS (
    SELECT 1 FROM hulagu.deletion_tombstones AS d
    WHERE d.subject_fence_digest = p_subject_fence_digest
      AND d.barred_until > v_now
  ) THEN
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

-- Sender-visible outcomes and retry bounds are stored with the stable delivery
-- key. Legacy sent rows are normalized to the explicit delivered vocabulary.
ALTER TABLE hulagu.outbox_messages
  ADD COLUMN attempt_count integer NOT NULL DEFAULT 0,
  ADD COLUMN max_attempts integer NOT NULL DEFAULT 3,
  ADD COLUMN last_error_class text,
  ADD COLUMN delivered_at timestamptz;
ALTER TABLE hulagu.outbox_messages DROP CONSTRAINT outbox_messages_state_check;
UPDATE hulagu.outbox_messages
SET state = 'delivered', delivered_at = created_at,
    lease_token_hash = NULL, lease_expires_at = NULL
WHERE state = 'sent';
UPDATE hulagu.outbox_messages
SET state = 'pending', lease_token_hash = NULL, lease_expires_at = NULL
WHERE state = 'claimed'
  AND (lease_token_hash IS NULL OR lease_expires_at IS NULL);
UPDATE hulagu.outbox_messages
SET attempt_count = 1
WHERE state = 'claimed' AND lease_token_hash IS NOT NULL AND lease_expires_at IS NOT NULL;
UPDATE hulagu.outbox_messages
SET lease_token_hash = NULL, lease_expires_at = NULL
WHERE state <> 'claimed';
ALTER TABLE hulagu.outbox_messages
  ADD CONSTRAINT outbox_messages_state_check
    CHECK (state IN ('pending','claimed','delivered','failed','delivery_unknown','cancelled')),
  ADD CONSTRAINT outbox_messages_attempts_bounded
    CHECK (max_attempts BETWEEN 1 AND 10 AND attempt_count BETWEEN 0 AND max_attempts),
  ADD CONSTRAINT outbox_messages_error_class_bounded
    CHECK (last_error_class IS NULL OR pg_catalog.octet_length(last_error_class) BETWEEN 1 AND 128),
  ADD CONSTRAINT outbox_messages_claim_lease_coherent
    CHECK (
      (state = 'claimed' AND lease_token_hash IS NOT NULL AND lease_expires_at IS NOT NULL)
      OR (state <> 'claimed' AND lease_token_hash IS NULL AND lease_expires_at IS NULL)
    ),
  ADD CONSTRAINT outbox_messages_delivery_time_coherent
    CHECK (
      (state = 'delivered' AND delivered_at IS NOT NULL)
      OR (state <> 'delivered' AND delivered_at IS NULL)
    );

-- Claim only ordinary sends for the installed tenant context. Stale lifecycle
-- work is cancelled before any candidate is exposed, and an attempt is consumed
-- durably when the lease is issued.
CREATE FUNCTION hulagu_api.claim_outbox_delivery(
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
BEGIN
  IF v_tenant IS NULL OR p_lease_token_hash !~ '^[0-9a-f]{64}$'
     OR p_batch NOT BETWEEN 1 AND 100 OR p_lease_seconds NOT BETWEEN 1 AND 300 THEN
    RAISE EXCEPTION 'invalid bounded outbox claim';
  END IF;

  SELECT t.state, t.lifecycle_epoch INTO v_tenant_state, v_lifecycle_epoch
  FROM hulagu.tenants AS t
  WHERE t.id = v_tenant
  FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'invalid bounded tenant context';
  END IF;

  UPDATE hulagu.outbox_messages AS o
  SET state = 'cancelled', lease_token_hash = NULL, lease_expires_at = NULL
  WHERE o.tenant_id = v_tenant
    AND o.kind = 'ordinary'
    AND o.state IN ('pending','failed','claimed')
    AND (
      o.lifecycle_epoch <> v_lifecycle_epoch
      OR v_tenant_state IN ('PAUSED','DELETE_PENDING','DELETING','DELETED')
    );
  IF v_tenant_state IN ('PAUSED','DELETE_PENDING','DELETING','DELETED') THEN
    RETURN;
  END IF;

  RETURN QUERY
  WITH candidates AS (
    SELECT o.id
    FROM hulagu.outbox_messages AS o
    WHERE o.tenant_id = v_tenant
      AND o.kind = 'ordinary'
      AND o.lifecycle_epoch = v_lifecycle_epoch
      AND o.attempt_count < o.max_attempts
      AND (
        o.state IN ('pending','failed')
        OR (o.state = 'claimed' AND o.lease_expires_at <= pg_catalog.now())
      )
    ORDER BY o.created_at, o.id
    LIMIT p_batch
    FOR UPDATE SKIP LOCKED
  )
  UPDATE hulagu.outbox_messages AS o
  SET state = 'claimed',
      attempt_count = o.attempt_count + 1,
      lease_token_hash = p_lease_token_hash,
      lease_expires_at = pg_catalog.now() + pg_catalog.make_interval(secs => p_lease_seconds),
      last_error_class = NULL
  FROM candidates AS c
  WHERE o.tenant_id = v_tenant AND o.id = c.id
  RETURNING o.id, o.delivery_key, o.kind, o.payload, o.attempt_count,
            o.lifecycle_epoch, o.work_epoch;
END
$$;

-- Record exactly one bounded sender result against the claimed attempt. Unknown
-- delivery is terminal and therefore never enters the retryable claim predicate;
-- failed rows remain retryable only while attempt_count is below max_attempts.
CREATE FUNCTION hulagu_api.record_outbox_delivery(
  p_outbox_id uuid,
  p_attempt integer,
  p_lease_token_hash text,
  p_lifecycle_epoch bigint,
  p_work_epoch bigint,
  p_outcome text,
  p_error_class text DEFAULT NULL
) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE
  v_tenant uuid := NULLIF(pg_catalog.current_setting('app.tenant_id', true),'')::uuid;
  v_tenant_state text;
  v_current_lifecycle_epoch bigint;
  v_updated integer;
BEGIN
  IF v_tenant IS NULL OR p_attempt NOT BETWEEN 1 AND 10
     OR p_lease_token_hash !~ '^[0-9a-f]{64}$'
     OR p_lifecycle_epoch < 0 OR p_work_epoch < 0
     OR p_outcome NOT IN ('delivered','failed','delivery_unknown')
     OR (p_outcome = 'delivered' AND p_error_class IS NOT NULL)
     OR (p_outcome <> 'delivered' AND (
       p_error_class IS NULL OR pg_catalog.octet_length(p_error_class) NOT BETWEEN 1 AND 128
     )) THEN
    RAISE EXCEPTION 'invalid bounded outbox outcome';
  END IF;

  SELECT t.state, t.lifecycle_epoch INTO v_tenant_state, v_current_lifecycle_epoch
  FROM hulagu.tenants AS t
  WHERE t.id = v_tenant
  FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'invalid bounded tenant context';
  END IF;
  IF v_tenant_state IN ('PAUSED','DELETE_PENDING','DELETING','DELETED')
     OR v_current_lifecycle_epoch <> p_lifecycle_epoch THEN
    UPDATE hulagu.outbox_messages AS o
    SET state = 'cancelled', lease_token_hash = NULL, lease_expires_at = NULL
    WHERE o.tenant_id = v_tenant AND o.id = p_outbox_id
      AND o.kind = 'ordinary' AND o.state = 'claimed'
      AND o.attempt_count = p_attempt AND o.attempt_count <= o.max_attempts
      AND o.lease_token_hash = p_lease_token_hash
      AND o.lease_expires_at > pg_catalog.now()
      AND o.lifecycle_epoch = p_lifecycle_epoch
      AND o.work_epoch = p_work_epoch;
    GET DIAGNOSTICS v_updated = ROW_COUNT;
    IF v_updated = 1 THEN RETURN 'cancelled'; END IF;
    RETURN 'rejected';
  END IF;

  UPDATE hulagu.outbox_messages AS o
  SET state = p_outcome,
      lease_token_hash = NULL,
      lease_expires_at = NULL,
      last_error_class = p_error_class,
      delivered_at = CASE WHEN p_outcome = 'delivered' THEN pg_catalog.now() ELSE NULL END
  WHERE o.tenant_id = v_tenant AND o.id = p_outbox_id
    AND o.kind = 'ordinary' AND o.state = 'claimed'
    AND o.attempt_count = p_attempt AND o.attempt_count <= o.max_attempts
    AND o.lease_token_hash = p_lease_token_hash
    AND o.lease_expires_at > pg_catalog.now()
    AND o.lifecycle_epoch = p_lifecycle_epoch
    AND o.work_epoch = p_work_epoch;
  GET DIAGNOSTICS v_updated = ROW_COUNT;
  IF v_updated = 1 THEN RETURN p_outcome; END IF;
  RETURN 'rejected';
END
$$;

REVOKE ALL ON FUNCTION hulagu_api.admit_telegram_enrollment_ingress(
  bigint,bigint,text,bigint,text,text,text,text,timestamptz,timestamptz,integer,integer,integer
) FROM PUBLIC;
REVOKE ALL ON FUNCTION hulagu_api.claim_outbox_delivery(text,integer,integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION hulagu_api.record_outbox_delivery(uuid,integer,text,bigint,bigint,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION hulagu_api.admit_telegram_enrollment_ingress(
  bigint,bigint,text,bigint,text,text,text,text,timestamptz,timestamptz,integer,integer,integer
) TO hulagu_app;
GRANT EXECUTE ON FUNCTION hulagu_api.claim_outbox_delivery(text,integer,integer) TO hulagu_app;
GRANT EXECUTE ON FUNCTION hulagu_api.record_outbox_delivery(uuid,integer,text,bigint,bigint,text,text) TO hulagu_app;
RESET ROLE;
