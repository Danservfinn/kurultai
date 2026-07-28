SET ROLE hulagu_owner;
SET search_path = pg_catalog;

-- Read one approved bot's durable long-poll offset without exposing the global
-- control table or accepting any tenant authority from the caller.
CREATE FUNCTION hulagu_api.telegram_polling_offset(p_bot_id bigint) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE v_next_update_id bigint;
BEGIN
  IF p_bot_id <= 0 THEN
    RAISE EXCEPTION 'invalid bot authority';
  END IF;
  SELECT o.next_update_id INTO v_next_update_id
  FROM hulagu.telegram_polling_offsets AS o
  WHERE o.bot_id = p_bot_id;
  RETURN COALESCE(v_next_update_id, 0::bigint);
END
$$;

-- Persist one normalized update, its dedupe/callback marker, optional ordinary
-- tenant outbox effect, and the next long-poll offset in one database statement.
-- Tenant authority is derived only from the stored subject binding; callers can
-- never name a tenant UUID.
CREATE FUNCTION hulagu_api.persist_telegram_ingress(
  p_bot_id bigint,
  p_update_id bigint,
  p_callback_query_id text,
  p_next_update_id bigint,
  p_subject_digest text,
  p_outcome_class text,
  p_expires_at timestamptz,
  p_delivery_key text DEFAULT NULL,
  p_outbox_kind text DEFAULT NULL,
  p_outbox_payload jsonb DEFAULT NULL
) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE
  v_enrollment_id uuid;
  v_tenant_id uuid;
  v_lifecycle_epoch bigint;
  v_inserted integer;
  v_has_outbox boolean := p_delivery_key IS NOT NULL
    OR p_outbox_kind IS NOT NULL OR p_outbox_payload IS NOT NULL;
BEGIN
  IF p_bot_id <= 0 OR p_update_id < 0 OR p_update_id >= 9223372036854775807
     OR p_next_update_id <> p_update_id + 1 THEN
    RAISE EXCEPTION 'invalid update authority';
  END IF;
  IF p_callback_query_id IS NOT NULL
     AND pg_catalog.octet_length(p_callback_query_id) NOT BETWEEN 1 AND 256 THEN
    RAISE EXCEPTION 'invalid callback authority';
  END IF;
  IF pg_catalog.octet_length(p_outcome_class) NOT BETWEEN 1 AND 64
     OR p_expires_at <= pg_catalog.now()
     OR p_expires_at > pg_catalog.now() + interval '90 days' THEN
    RAISE EXCEPTION 'invalid bounded ingress metadata';
  END IF;
  IF p_subject_digest IS NOT NULL AND p_subject_digest !~ '^[0-9a-f]{64}$' THEN
    RAISE EXCEPTION 'invalid subject authority';
  END IF;
  IF v_has_outbox <> (p_delivery_key IS NOT NULL AND p_outbox_kind IS NOT NULL AND p_outbox_payload IS NOT NULL)
     OR (v_has_outbox AND (
       pg_catalog.octet_length(p_delivery_key) NOT BETWEEN 1 AND 256
       OR pg_catalog.octet_length(p_outbox_kind) NOT BETWEEN 1 AND 64
       OR pg_catalog.octet_length(p_outbox_payload::text) > 16384
     )) THEN
    RAISE EXCEPTION 'invalid bounded outbox effect';
  END IF;

  INSERT INTO hulagu.telegram_polling_offsets(bot_id, next_update_id)
  VALUES (p_bot_id, 0)
  ON CONFLICT (bot_id) DO NOTHING;
  PERFORM 1 FROM hulagu.telegram_polling_offsets AS o
  WHERE o.bot_id = p_bot_id FOR UPDATE;

  IF p_subject_digest IS NOT NULL THEN
    SELECT b.tenant_id, t.lifecycle_epoch INTO v_tenant_id, v_lifecycle_epoch
    FROM hulagu.identity_bindings AS b
    JOIN hulagu.tenants AS t ON t.id = b.tenant_id
    WHERE b.subject_digest = p_subject_digest
      AND t.state NOT IN ('DELETE_PENDING','DELETING','DELETED')
    FOR UPDATE OF t;
    IF v_tenant_id IS NULL THEN
      SELECT e.id INTO v_enrollment_id
      FROM hulagu.enrollments AS e
      WHERE e.subject_digest = p_subject_digest AND e.expires_at > pg_catalog.now();
    END IF;
    IF v_tenant_id IS NULL AND v_enrollment_id IS NULL THEN
      RAISE EXCEPTION 'unresolved ingress subject';
    END IF;
  ELSIF p_outcome_class <> 'terminal_dedupe' THEN
    RAISE EXCEPTION 'active ingress requires stored subject authority';
  END IF;

  IF EXISTS (
    SELECT 1 FROM hulagu.inbound_updates AS i
    WHERE i.bot_id = p_bot_id AND i.update_id = p_update_id
  ) THEN
    UPDATE hulagu.telegram_polling_offsets AS o
    SET next_update_id = GREATEST(o.next_update_id, p_next_update_id),
        updated_at = pg_catalog.now()
    WHERE o.bot_id = p_bot_id;
    RETURN 'duplicate_update';
  END IF;
  IF p_callback_query_id IS NOT NULL AND EXISTS (
    SELECT 1 FROM hulagu.inbound_updates AS i
    WHERE i.bot_id = p_bot_id AND i.callback_query_id = p_callback_query_id
  ) THEN
    UPDATE hulagu.telegram_polling_offsets AS o
    SET next_update_id = GREATEST(o.next_update_id, p_next_update_id),
        updated_at = pg_catalog.now()
    WHERE o.bot_id = p_bot_id;
    RETURN 'duplicate_callback';
  END IF;
  IF v_has_outbox AND v_tenant_id IS NULL THEN
    RAISE EXCEPTION 'outbox effect requires resolved tenant authority';
  END IF;

  INSERT INTO hulagu.inbound_updates(
    bot_id, update_id, callback_query_id, enrollment_id, tenant_id,
    outcome_class, expires_at
  ) VALUES (
    p_bot_id, p_update_id, p_callback_query_id, v_enrollment_id, v_tenant_id,
    p_outcome_class, p_expires_at
  );
  IF v_has_outbox THEN
    INSERT INTO hulagu.outbox_messages(
      tenant_id, kind, payload, lifecycle_epoch, work_epoch, state, delivery_key
    ) VALUES (
      v_tenant_id, p_outbox_kind, p_outbox_payload,
      v_lifecycle_epoch, 0, 'pending', p_delivery_key
    )
    ON CONFLICT (tenant_id, delivery_key) DO NOTHING;
    GET DIAGNOSTICS v_inserted = ROW_COUNT;
    IF v_inserted = 0 AND NOT EXISTS (
      SELECT 1 FROM hulagu.outbox_messages AS o
      WHERE o.tenant_id = v_tenant_id AND o.delivery_key = p_delivery_key
        AND o.kind = p_outbox_kind AND o.payload = p_outbox_payload
        AND o.lifecycle_epoch = v_lifecycle_epoch AND o.work_epoch = 0
    ) THEN
      RAISE EXCEPTION 'delivery key collision';
    END IF;
  END IF;
  UPDATE hulagu.telegram_polling_offsets AS o
  SET next_update_id = GREATEST(o.next_update_id, p_next_update_id),
      updated_at = pg_catalog.now()
  WHERE o.bot_id = p_bot_id;
  RETURN 'recorded';
END
$$;

REVOKE ALL ON FUNCTION hulagu_api.telegram_polling_offset(bigint) FROM PUBLIC;
REVOKE ALL ON FUNCTION hulagu_api.persist_telegram_ingress(
  bigint,bigint,text,bigint,text,text,timestamptz,text,text,jsonb
) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION hulagu_api.telegram_polling_offset(bigint) TO hulagu_app;
GRANT EXECUTE ON FUNCTION hulagu_api.persist_telegram_ingress(
  bigint,bigint,text,bigint,text,text,timestamptz,text,text,jsonb
) TO hulagu_app;
RESET ROLE;
