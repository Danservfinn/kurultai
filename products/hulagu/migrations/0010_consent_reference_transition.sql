SET ROLE hulagu_owner;
SET search_path = pg_catalog;

-- Consent promotion consumes the short-lived enrollment authority, but normalized
-- active ingress must retain exactly one stored authority reference. Transfer every
-- ingress row for the consumed enrollment to the newly created tenant before the
-- enrollment is deleted; the whole transition remains one transaction.
CREATE OR REPLACE FUNCTION hulagu_api.promote_consented_enrollment(
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
  UPDATE hulagu.inbound_updates
    SET enrollment_id = NULL, tenant_id = v_tenant
    WHERE enrollment_id = p_enrollment_id;
  DELETE FROM hulagu.enrollments WHERE id = p_enrollment_id;
  RETURN v_tenant;
END
$$;

-- Tenant erasure is the terminal form of the same reference transition. Minimize
-- normalized ingress before deleting its tenant so ON DELETE SET NULL can never
-- create an active row with neither enrollment nor tenant authority.
CREATE OR REPLACE FUNCTION hulagu_api.finalize_deletion(p_deletion_id uuid, p_delivery_token text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE v_job hulagu.deletion_jobs%ROWTYPE;
BEGIN
  SELECT * INTO v_job FROM hulagu.deletion_jobs WHERE deletion_id=p_deletion_id FOR UPDATE;
  IF NOT FOUND OR v_job.state <> 'delivery_pending'
     OR v_job.expires_at <= pg_catalog.now()
     OR v_job.delivery_token_hash <> pg_catalog.encode(public.digest(p_delivery_token,'sha256'),'hex') THEN RETURN false; END IF;
  UPDATE hulagu.inbound_updates SET enrollment_id=NULL,tenant_id=NULL,outcome_class='terminal_dedupe'
    WHERE tenant_id=v_job.target_tenant_id;
  DELETE FROM hulagu.tenants WHERE id=v_job.target_tenant_id;
  INSERT INTO hulagu.deletion_tombstones(subject_fence_digest,key_version,barred_until)
    VALUES(v_job.subject_fence_digest,v_job.route_key_version,pg_catalog.now()+interval '365 days')
    ON CONFLICT(subject_fence_digest) DO UPDATE SET barred_until=GREATEST(hulagu.deletion_tombstones.barred_until,EXCLUDED.barred_until);
  UPDATE hulagu.deletion_jobs SET target_tenant_id=NULL,subject_fence_digest=NULL,encrypted_route=NULL,
    route_binding_digest=NULL,delivery_token_hash=NULL,state='complete' WHERE deletion_id=p_deletion_id;
  INSERT INTO hulagu.deletion_receipts(deletion_id,outcome,expires_at)
    VALUES(p_deletion_id,'completed',pg_catalog.now()+interval '90 days');
  RETURN true;
END
$$;

REVOKE ALL ON FUNCTION hulagu_api.promote_consented_enrollment(uuid,text,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION hulagu_api.finalize_deletion(uuid,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION hulagu_api.promote_consented_enrollment(uuid,text,text) TO hulagu_app;
GRANT EXECUTE ON FUNCTION hulagu_api.finalize_deletion(uuid,text) TO hulagu_deletion;
RESET ROLE;
