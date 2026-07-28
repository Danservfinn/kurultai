SET ROLE hulagu_owner;
SET search_path = pg_catalog;

CREATE FUNCTION hulagu_api.resolve_enrollment(
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
  IF p_subject_digest !~ '^[0-9a-f]{64}$' OR p_subject_fence_digest !~ '^[0-9a-f]{64}$'
     OR p_consent_nonce_hash !~ '^[0-9a-f]{64}$' OR p_expires_at <= pg_catalog.now() THEN
    RAISE EXCEPTION 'invalid enrollment input';
  END IF;
  IF EXISTS (
    SELECT 1 FROM hulagu.deletion_tombstones
    WHERE subject_fence_digest = p_subject_fence_digest AND barred_until > pg_catalog.now()
  ) THEN
    RAISE EXCEPTION 're-enrollment barred';
  END IF;
  INSERT INTO hulagu.enrollments(subject_digest, subject_fence_digest, notice_version, consent_nonce_hash, expires_at)
  VALUES (p_subject_digest, p_subject_fence_digest, p_notice_version, p_consent_nonce_hash, p_expires_at)
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

CREATE FUNCTION hulagu_api.promote_consented_enrollment(
  p_enrollment_id uuid,
  p_notice_version text,
  p_consent_nonce_hash text
) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE v_enrollment hulagu.enrollments%ROWTYPE; v_tenant uuid;
BEGIN
  SELECT * INTO v_enrollment FROM hulagu.enrollments WHERE id = p_enrollment_id FOR UPDATE;
  IF NOT FOUND OR v_enrollment.expires_at <= pg_catalog.now()
     OR v_enrollment.notice_version <> p_notice_version
     OR v_enrollment.consent_nonce_hash <> p_consent_nonce_hash THEN
    RAISE EXCEPTION 'invalid or consumed consent authority';
  END IF;
  IF EXISTS (
    SELECT 1 FROM hulagu.deletion_tombstones
    WHERE subject_fence_digest = v_enrollment.subject_fence_digest AND barred_until > pg_catalog.now()
  ) THEN
    RAISE EXCEPTION 're-enrollment barred';
  END IF;
  v_tenant := public.gen_random_uuid();
  PERFORM pg_catalog.set_config('app.tenant_id', v_tenant::text, true);
  INSERT INTO hulagu.tenants(id, state) VALUES (v_tenant, 'READY');
  INSERT INTO hulagu.identity_bindings(tenant_id, subject_digest, subject_fence_digest)
    VALUES (v_tenant, v_enrollment.subject_digest, v_enrollment.subject_fence_digest);
  DELETE FROM hulagu.enrollments WHERE id = p_enrollment_id;
  RETURN v_tenant;
END
$$;

CREATE FUNCTION hulagu_api.resolve_existing_tenant(p_subject_digest text) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE v_tenant uuid;
BEGIN
  SELECT tenant_id INTO v_tenant FROM hulagu.identity_bindings WHERE subject_digest = p_subject_digest;
  IF v_tenant IS NULL THEN RETURN NULL; END IF;
  PERFORM pg_catalog.set_config('app.tenant_id', v_tenant::text, true);
  IF NOT EXISTS (SELECT 1 FROM hulagu.tenants WHERE id = v_tenant AND state <> 'DELETED') THEN RETURN NULL; END IF;
  RETURN v_tenant;
END
$$;

CREATE FUNCTION hulagu_api.claim_job(p_job_id uuid, p_lease_token_hash text, p_lease_seconds integer DEFAULT 60)
RETURNS TABLE(job_id uuid, tenant_id uuid, attempt integer, immutable_input_digest text, lifecycle_epoch bigint, work_epoch bigint)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE v_tenant uuid;
BEGIN
  IF p_lease_token_hash !~ '^[0-9a-f]{64}$' OR p_lease_seconds NOT BETWEEN 1 AND 300 THEN
    RAISE EXCEPTION 'invalid lease authority';
  END IF;
  SELECT j.tenant_id INTO v_tenant
  FROM hulagu.job_attempts AS j
  WHERE j.id = p_job_id AND j.state = 'queued'
  ORDER BY j.tenant_id LIMIT 1;
  IF v_tenant IS NULL THEN RETURN; END IF;
  PERFORM pg_catalog.set_config('app.tenant_id', v_tenant::text, true);
  RETURN QUERY
  UPDATE hulagu.job_attempts AS j SET state='claimed', lease_token_hash=p_lease_token_hash,
    lease_expires_at=pg_catalog.now()+pg_catalog.make_interval(secs => p_lease_seconds)
  WHERE j.tenant_id=v_tenant AND j.id=p_job_id AND j.state='queued'
  RETURNING j.id,j.tenant_id,j.attempt,j.immutable_input_digest,j.lifecycle_epoch,j.work_epoch;
END
$$;

CREATE FUNCTION hulagu_api.complete_job(
  p_job_id uuid, p_attempt integer, p_lease_token_hash text, p_input_digest text,
  p_lifecycle_epoch bigint, p_work_epoch bigint, p_result_digest text
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE v_tenant uuid; v_updated integer;
BEGIN
  SELECT j.tenant_id INTO v_tenant FROM hulagu.job_attempts AS j WHERE j.id=p_job_id ORDER BY j.tenant_id LIMIT 1;
  IF v_tenant IS NULL THEN RETURN false; END IF;
  PERFORM pg_catalog.set_config('app.tenant_id', v_tenant::text, true);
  UPDATE hulagu.job_attempts AS j SET state='succeeded', result_digest=p_result_digest, lease_token_hash=NULL, lease_expires_at=NULL
  WHERE j.tenant_id=v_tenant AND j.id=p_job_id AND j.attempt=p_attempt AND j.state='claimed'
    AND j.lease_token_hash=p_lease_token_hash AND j.immutable_input_digest=p_input_digest
    AND j.lifecycle_epoch=p_lifecycle_epoch AND j.work_epoch=p_work_epoch AND j.lease_expires_at>pg_catalog.now()
    AND EXISTS (SELECT 1 FROM hulagu.tenants t WHERE t.id=v_tenant AND t.lifecycle_epoch=p_lifecycle_epoch AND t.state NOT IN ('PAUSED','DELETE_PENDING','DELETING','DELETED'))
    AND EXISTS (SELECT 1 FROM hulagu.search_runs r WHERE r.tenant_id=v_tenant AND r.id=j.run_id AND r.work_epoch=p_work_epoch AND r.state NOT IN ('paused','cancelled'));
  GET DIAGNOSTICS v_updated = ROW_COUNT;
  RETURN v_updated = 1;
END
$$;

CREATE FUNCTION hulagu_api.fail_job(
  p_job_id uuid, p_attempt integer, p_lease_token_hash text, p_input_digest text,
  p_lifecycle_epoch bigint, p_work_epoch bigint
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE v_tenant uuid; v_updated integer;
BEGIN
  SELECT j.tenant_id INTO v_tenant FROM hulagu.job_attempts AS j WHERE j.id=p_job_id ORDER BY j.tenant_id LIMIT 1;
  IF v_tenant IS NULL THEN RETURN false; END IF;
  PERFORM pg_catalog.set_config('app.tenant_id', v_tenant::text, true);
  UPDATE hulagu.job_attempts AS j SET state='failed', lease_token_hash=NULL, lease_expires_at=NULL
  WHERE j.tenant_id=v_tenant AND j.id=p_job_id AND j.attempt=p_attempt AND j.state='claimed'
    AND j.lease_token_hash=p_lease_token_hash AND j.immutable_input_digest=p_input_digest
    AND j.lifecycle_epoch=p_lifecycle_epoch AND j.work_epoch=p_work_epoch AND j.lease_expires_at>pg_catalog.now()
    AND EXISTS (SELECT 1 FROM hulagu.tenants t WHERE t.id=v_tenant AND t.lifecycle_epoch=p_lifecycle_epoch AND t.state NOT IN ('PAUSED','DELETE_PENDING','DELETING','DELETED'))
    AND EXISTS (SELECT 1 FROM hulagu.search_runs r WHERE r.tenant_id=v_tenant AND r.id=j.run_id AND r.work_epoch=p_work_epoch AND r.state NOT IN ('paused','cancelled'));
  GET DIAGNOSTICS v_updated = ROW_COUNT;
  RETURN v_updated = 1;
END
$$;

CREATE FUNCTION hulagu_api.claim_outbox(p_batch integer DEFAULT 10) RETURNS SETOF uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE v_tenant uuid := NULLIF(pg_catalog.current_setting('app.tenant_id', true),'')::uuid;
BEGIN
  IF v_tenant IS NULL OR p_batch NOT BETWEEN 1 AND 100 THEN RAISE EXCEPTION 'invalid bounded tenant context'; END IF;
  RETURN QUERY SELECT o.id FROM hulagu.outbox_messages o
    WHERE o.tenant_id=v_tenant AND o.state='pending' ORDER BY o.created_at,o.id LIMIT p_batch FOR UPDATE SKIP LOCKED;
END
$$;

CREATE FUNCTION hulagu_api.claim_retention(p_batch integer DEFAULT 10) RETURNS SETOF uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE v_tenant uuid := NULLIF(pg_catalog.current_setting('app.tenant_id', true),'')::uuid;
BEGIN
  IF v_tenant IS NULL OR p_batch NOT BETWEEN 1 AND 100 THEN RAISE EXCEPTION 'invalid bounded tenant context'; END IF;
  RETURN QUERY SELECT r.id FROM hulagu.retention_jobs r
    WHERE r.tenant_id=v_tenant AND r.state='pending' ORDER BY r.created_at,r.id LIMIT p_batch FOR UPDATE SKIP LOCKED;
END
$$;

CREATE FUNCTION hulagu_api.request_deletion(p_encrypted_route text, p_route_binding_digest text) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE v_tenant uuid := NULLIF(pg_catalog.current_setting('app.tenant_id', true),'')::uuid;
        v_fence text; v_deletion uuid;
BEGIN
  SELECT e.subject_fence_digest INTO v_fence FROM hulagu.identity_bindings e WHERE e.tenant_id=v_tenant ORDER BY e.id LIMIT 1;
  IF v_fence IS NULL OR p_encrypted_route IS NULL OR p_route_binding_digest IS NULL THEN RAISE EXCEPTION 'invalid deletion request'; END IF;
  UPDATE hulagu.tenants SET state='DELETING', lifecycle_epoch=lifecycle_epoch+1, updated_at=pg_catalog.now() WHERE id=v_tenant;
  INSERT INTO hulagu.deletion_jobs(target_tenant_id,subject_fence_digest,encrypted_route,route_binding_digest,state,expires_at)
  VALUES(v_tenant,v_fence,p_encrypted_route,p_route_binding_digest,'delivery_pending',pg_catalog.now()+interval '30 days')
  RETURNING deletion_id INTO v_deletion;
  RETURN v_deletion;
END
$$;

CREATE FUNCTION hulagu_api.claim_deletion_delivery(p_deletion_id uuid, p_delivery_token_hash text) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE v_route text;
BEGIN
  IF p_delivery_token_hash !~ '^[0-9a-f]{64}$' THEN RAISE EXCEPTION 'invalid delivery token'; END IF;
  UPDATE hulagu.deletion_jobs SET delivery_token_hash=p_delivery_token_hash
    WHERE deletion_id=p_deletion_id AND state='delivery_pending' AND delivery_token_hash IS NULL
      AND expires_at>pg_catalog.now()
    RETURNING encrypted_route INTO v_route;
  RETURN v_route;
END
$$;

CREATE FUNCTION hulagu_api.finalize_deletion(p_deletion_id uuid, p_delivery_token text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE v_job hulagu.deletion_jobs%ROWTYPE;
BEGIN
  SELECT * INTO v_job FROM hulagu.deletion_jobs WHERE deletion_id=p_deletion_id FOR UPDATE;
  IF NOT FOUND OR v_job.state <> 'delivery_pending'
     OR v_job.expires_at <= pg_catalog.now()
     OR v_job.delivery_token_hash <> pg_catalog.encode(public.digest(p_delivery_token,'sha256'),'hex') THEN RETURN false; END IF;
  DELETE FROM hulagu.tenants WHERE id=v_job.target_tenant_id;
  INSERT INTO hulagu.deletion_tombstones(subject_fence_digest,key_version,barred_until)
    VALUES(v_job.subject_fence_digest,v_job.route_key_version,pg_catalog.now()+interval '365 days')
    ON CONFLICT(subject_fence_digest) DO UPDATE SET barred_until=GREATEST(hulagu.deletion_tombstones.barred_until,EXCLUDED.barred_until);
  UPDATE hulagu.inbound_updates SET enrollment_id=NULL,tenant_id=NULL,outcome_class='terminal_dedupe'
    WHERE tenant_id=v_job.target_tenant_id;
  UPDATE hulagu.deletion_jobs SET target_tenant_id=NULL,subject_fence_digest=NULL,encrypted_route=NULL,
    route_binding_digest=NULL,delivery_token_hash=NULL,state='complete' WHERE deletion_id=p_deletion_id;
  INSERT INTO hulagu.deletion_receipts(deletion_id,outcome,expires_at)
    VALUES(p_deletion_id,'completed',pg_catalog.now()+interval '90 days');
  RETURN true;
END
$$;

CREATE FUNCTION hulagu_api.complete_deletion_delivery(p_deletion_id uuid, p_delivery_token text) RETURNS boolean
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog
AS $$ SELECT hulagu_api.finalize_deletion(p_deletion_id,p_delivery_token) $$;

CREATE FUNCTION hulagu_api.reconcile_global_state(p_batch integer DEFAULT 100) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
BEGIN
  IF p_batch NOT BETWEEN 1 AND 1000 THEN RAISE EXCEPTION 'invalid batch'; END IF;
  DELETE FROM hulagu.enrollments WHERE id IN (SELECT id FROM hulagu.enrollments WHERE expires_at<pg_catalog.now() ORDER BY expires_at,id LIMIT p_batch);
  RETURN pg_catalog.jsonb_build_object('status','ok','bounded',p_batch);
END
$$;

CREATE FUNCTION hulagu_api.aggregate_health() RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog
AS $$
  SELECT pg_catalog.jsonb_build_object(
    'database','ok',
    'pending_deletions',(SELECT pg_catalog.count(*) FROM hulagu.deletion_jobs WHERE state IN ('pending','erasing','delivery_pending')),
    'storage_pressure',COALESCE((SELECT pressure_state FROM hulagu.global_storage_state WHERE singleton),'unknown')
  )
$$;

REVOKE ALL ON ALL FUNCTIONS IN SCHEMA hulagu_api FROM PUBLIC;
GRANT EXECUTE ON FUNCTION hulagu_api.resolve_enrollment(text,text,text,text,timestamptz) TO hulagu_app;
GRANT EXECUTE ON FUNCTION hulagu_api.promote_consented_enrollment(uuid,text,text) TO hulagu_app;
GRANT EXECUTE ON FUNCTION hulagu_api.resolve_existing_tenant(text) TO hulagu_app;
GRANT EXECUTE ON FUNCTION hulagu_api.request_deletion(text,text) TO hulagu_app;
GRANT EXECUTE ON FUNCTION hulagu_api.claim_outbox(integer) TO hulagu_app;
GRANT EXECUTE ON FUNCTION hulagu_api.claim_retention(integer) TO hulagu_app;
GRANT EXECUTE ON FUNCTION hulagu_api.claim_job(uuid,text,integer), hulagu_api.complete_job(uuid,integer,text,text,bigint,bigint,text), hulagu_api.fail_job(uuid,integer,text,text,bigint,bigint) TO hulagu_runner;
GRANT EXECUTE ON FUNCTION hulagu_api.claim_deletion_delivery(uuid,text), hulagu_api.finalize_deletion(uuid,text), hulagu_api.complete_deletion_delivery(uuid,text) TO hulagu_deletion;
GRANT EXECUTE ON FUNCTION hulagu_api.reconcile_global_state(integer), hulagu_api.aggregate_health() TO hulagu_app, hulagu_readonly;
RESET ROLE;
