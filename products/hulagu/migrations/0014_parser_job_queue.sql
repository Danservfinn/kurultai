SET ROLE hulagu_owner;
SET search_path = pg_catalog;

ALTER TABLE hulagu.source_documents
  ADD COLUMN parser_work_epoch bigint NOT NULL DEFAULT 0 CHECK (parser_work_epoch >= 0);

CREATE TABLE hulagu.parser_jobs (
  tenant_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT public.gen_random_uuid(),
  source_document_id uuid NOT NULL,
  immutable_input_digest text NOT NULL CHECK (immutable_input_digest ~ '^[0-9a-f]{64}$'),
  input_authority text NOT NULL CHECK (input_authority ~ '^[0-9]+(:[0-9]+){7}$'),
  lifecycle_epoch bigint NOT NULL CHECK (lifecycle_epoch >= 0),
  work_epoch bigint NOT NULL CHECK (work_epoch >= 0),
  state text NOT NULL CHECK (state IN ('queued','claimed','succeeded','failed')),
  attempt integer NOT NULL DEFAULT 0 CHECK (attempt >= 0),
  lease_token_hash text CHECK (lease_token_hash IS NULL OR lease_token_hash ~ '^[0-9a-f]{64}$'),
  lease_expires_at timestamptz,
  result_digest text CHECK (result_digest IS NULL OR result_digest ~ '^[0-9a-f]{64}$'),
  result_profile jsonb,
  created_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
  updated_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
  PRIMARY KEY (tenant_id, id),
  FOREIGN KEY (tenant_id, source_document_id)
    REFERENCES hulagu.source_documents(tenant_id, id) ON DELETE CASCADE,
  UNIQUE (tenant_id, source_document_id),
  CHECK (
    (state = 'claimed' AND lease_token_hash IS NOT NULL AND lease_expires_at IS NOT NULL)
    OR (state <> 'claimed' AND lease_token_hash IS NULL AND lease_expires_at IS NULL)
  ),
  CHECK ((state = 'succeeded' AND result_digest IS NOT NULL AND result_profile IS NOT NULL)
    OR (state <> 'succeeded' AND result_digest IS NULL AND result_profile IS NULL))
);

CREATE INDEX parser_jobs_claim_idx
  ON hulagu.parser_jobs (state, lease_expires_at, created_at, tenant_id, id);

ALTER TABLE hulagu.parser_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE hulagu.parser_jobs FORCE ROW LEVEL SECURITY;
CREATE POLICY parser_jobs_tenant_isolation ON hulagu.parser_jobs
  USING (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid);

CREATE FUNCTION hulagu.parser_job_immutable_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog
AS $$
BEGIN
  IF NEW.tenant_id <> OLD.tenant_id
     OR NEW.id <> OLD.id
     OR NEW.source_document_id <> OLD.source_document_id
     OR NEW.immutable_input_digest <> OLD.immutable_input_digest
     OR NEW.input_authority <> OLD.input_authority
     OR NEW.lifecycle_epoch <> OLD.lifecycle_epoch
     OR NEW.work_epoch <> OLD.work_epoch
     OR NEW.created_at <> OLD.created_at THEN
    RAISE EXCEPTION 'parser job immutable authority drift';
  END IF;
  RETURN NEW;
END
$$;

CREATE TRIGGER parser_job_immutable_guard
BEFORE UPDATE ON hulagu.parser_jobs
FOR EACH ROW EXECUTE FUNCTION hulagu.parser_job_immutable_guard();

CREATE FUNCTION hulagu_api.enqueue_parser_job(
  p_tenant_id uuid,
  p_document_digest text,
  p_storage_ref text,
  p_input_authority text
) RETURNS TABLE(
  job_id uuid,
  tenant_id uuid,
  document_digest text,
  immutable_input_digest text,
  lifecycle_epoch bigint,
  work_epoch bigint,
  state text,
  attempt integer,
  created boolean
)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE
  v_tenant hulagu.tenants%ROWTYPE;
  v_document hulagu.source_documents%ROWTYPE;
  v_job hulagu.parser_jobs%ROWTYPE;
  v_created boolean := false;
BEGIN
  IF p_tenant_id IS NULL
     OR p_document_digest !~ '^[0-9a-f]{64}$'
     OR p_storage_ref IS NULL
     OR p_storage_ref !~ ('^/tenants/' || p_tenant_id::text || '/[A-Za-z0-9._/-]+$')
     OR p_storage_ref ~ '(^|/)\.\.(/|$)'
     OR p_storage_ref LIKE '%//%'
     OR p_input_authority !~ '^[0-9]+(:[0-9]+){7}$' THEN
    RAISE EXCEPTION 'invalid parser enqueue authority';
  END IF;

  SELECT t.* INTO v_tenant
  FROM hulagu.tenants AS t
  WHERE t.id = p_tenant_id
    AND t.state NOT IN ('PAUSED','DELETE_PENDING','DELETING','DELETED')
  FOR SHARE;
  IF NOT FOUND THEN RAISE EXCEPTION 'parser enqueue authority unavailable'; END IF;

  INSERT INTO hulagu.source_documents(tenant_id,digest,parser_state,retention_state,storage_ref)
  VALUES(p_tenant_id,p_document_digest,'queued','active',p_storage_ref)
  ON CONFLICT ON CONSTRAINT source_documents_tenant_id_digest_key DO NOTHING
  RETURNING * INTO v_document;
  IF NOT FOUND THEN
    SELECT d.* INTO v_document
    FROM hulagu.source_documents AS d
    WHERE d.tenant_id=p_tenant_id AND d.digest=p_document_digest
    FOR SHARE;
    IF NOT FOUND OR v_document.storage_ref <> p_storage_ref THEN
      RAISE EXCEPTION 'parser document authority mismatch';
    END IF;
  END IF;

  INSERT INTO hulagu.parser_jobs(
    tenant_id,source_document_id,immutable_input_digest,input_authority,lifecycle_epoch,work_epoch,state
  )
  VALUES(
    p_tenant_id,v_document.id,p_document_digest,p_input_authority,
    v_tenant.lifecycle_epoch,v_document.parser_work_epoch,'queued'
  )
  ON CONFLICT ON CONSTRAINT parser_jobs_tenant_id_source_document_id_key DO NOTHING
  RETURNING * INTO v_job;
  IF FOUND THEN
    v_created := true;
  ELSE
    SELECT j.* INTO STRICT v_job
    FROM hulagu.parser_jobs AS j
    WHERE j.tenant_id=p_tenant_id AND j.source_document_id=v_document.id;
    IF v_job.input_authority <> p_input_authority THEN
      RAISE EXCEPTION 'parser input authority mismatch';
    END IF;
  END IF;

  RETURN QUERY SELECT v_job.id,v_job.tenant_id,v_document.digest,v_job.immutable_input_digest,
    v_job.lifecycle_epoch,v_job.work_epoch,v_job.state,v_job.attempt,v_created;
END
$$;

CREATE FUNCTION hulagu_api.claim_parser_job(
  p_lease_token_hash text,
  p_lease_seconds integer DEFAULT 60
) RETURNS TABLE(
  job_id uuid,
  tenant_id uuid,
  document_digest text,
  storage_ref text,
  attempt integer,
  immutable_input_digest text,
  lifecycle_epoch bigint,
  work_epoch bigint,
  input_authority text
)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE
  v_job_id uuid;
  v_tenant_id uuid;
  v_attempt integer;
  v_immutable_input_digest text;
  v_lifecycle_epoch bigint;
  v_work_epoch bigint;
  v_digest text;
  v_storage_ref text;
  v_input_authority text;
BEGIN
  IF p_lease_token_hash !~ '^[0-9a-f]{64}$' OR p_lease_seconds NOT BETWEEN 1 AND 300 THEN
    RAISE EXCEPTION 'invalid parser lease authority';
  END IF;

  SELECT j.id,j.tenant_id,j.attempt,j.immutable_input_digest,j.lifecycle_epoch,j.work_epoch,j.input_authority,
         d.digest,d.storage_ref
  INTO v_job_id,v_tenant_id,v_attempt,v_immutable_input_digest,v_lifecycle_epoch,v_work_epoch,v_input_authority,
       v_digest,v_storage_ref
  FROM hulagu.parser_jobs AS j
  JOIN hulagu.tenants AS t ON t.id=j.tenant_id
  JOIN hulagu.source_documents AS d ON d.tenant_id=j.tenant_id AND d.id=j.source_document_id
  WHERE (j.state='queued' OR (j.state='claimed' AND j.lease_expires_at<=pg_catalog.now()))
    AND t.state NOT IN ('PAUSED','DELETE_PENDING','DELETING','DELETED')
    AND t.lifecycle_epoch=j.lifecycle_epoch
    AND d.parser_work_epoch=j.work_epoch
  ORDER BY j.created_at,j.tenant_id,j.id
  LIMIT 1
  FOR UPDATE OF t,d,j SKIP LOCKED;
  IF NOT FOUND THEN RETURN; END IF;

  UPDATE hulagu.parser_jobs AS j
  SET state='claimed',attempt=v_attempt+1,lease_token_hash=p_lease_token_hash,
      lease_expires_at=pg_catalog.now()+pg_catalog.make_interval(secs=>p_lease_seconds),
      updated_at=pg_catalog.now()
  WHERE j.tenant_id=v_tenant_id AND j.id=v_job_id;

  RETURN QUERY SELECT v_job_id,v_tenant_id,v_digest,v_storage_ref,v_attempt+1,
    v_immutable_input_digest,v_lifecycle_epoch,v_work_epoch,v_input_authority;
END
$$;

CREATE FUNCTION hulagu_api.complete_parser_job(
  p_job_id uuid,
  p_attempt integer,
  p_lease_token_hash text,
  p_input_digest text,
  p_lifecycle_epoch bigint,
  p_work_epoch bigint,
  p_result_digest text,
  p_result_profile jsonb
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE v_job hulagu.parser_jobs%ROWTYPE;
BEGIN
  IF p_attempt <= 0
     OR p_lease_token_hash !~ '^[0-9a-f]{64}$'
     OR p_input_digest !~ '^[0-9a-f]{64}$'
     OR p_result_digest !~ '^[0-9a-f]{64}$'
     OR p_result_profile IS NULL
     OR pg_catalog.jsonb_typeof(p_result_profile) <> 'object' THEN
    RETURN false;
  END IF;
  SELECT j.* INTO v_job
  FROM hulagu.parser_jobs AS j
  JOIN hulagu.tenants AS t ON t.id=j.tenant_id
  JOIN hulagu.source_documents AS d ON d.tenant_id=j.tenant_id AND d.id=j.source_document_id
  WHERE j.id=p_job_id AND j.state='claimed' AND j.attempt=p_attempt
    AND j.lease_token_hash=p_lease_token_hash AND j.lease_expires_at>pg_catalog.now()
    AND j.immutable_input_digest=p_input_digest
    AND j.lifecycle_epoch=p_lifecycle_epoch AND j.work_epoch=p_work_epoch
    AND t.state NOT IN ('PAUSED','DELETE_PENDING','DELETING','DELETED')
    AND t.lifecycle_epoch=p_lifecycle_epoch AND d.parser_work_epoch=p_work_epoch
  ORDER BY j.tenant_id LIMIT 1
  FOR UPDATE OF t,d,j;
  IF NOT FOUND THEN RETURN false; END IF;
  UPDATE hulagu.parser_jobs AS j
  SET state='succeeded',lease_token_hash=NULL,lease_expires_at=NULL,
      result_digest=p_result_digest,result_profile=p_result_profile,updated_at=pg_catalog.now()
  WHERE j.tenant_id=v_job.tenant_id AND j.id=v_job.id;
  UPDATE hulagu.source_documents AS d SET parser_state='succeeded'
  WHERE d.tenant_id=v_job.tenant_id AND d.id=v_job.source_document_id;
  RETURN true;
END
$$;

CREATE FUNCTION hulagu_api.fail_parser_job(
  p_job_id uuid,
  p_attempt integer,
  p_lease_token_hash text,
  p_input_digest text,
  p_lifecycle_epoch bigint,
  p_work_epoch bigint
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE v_job hulagu.parser_jobs%ROWTYPE;
BEGIN
  IF p_attempt <= 0 OR p_lease_token_hash !~ '^[0-9a-f]{64}$'
     OR p_input_digest !~ '^[0-9a-f]{64}$' THEN RETURN false; END IF;
  SELECT j.* INTO v_job
  FROM hulagu.parser_jobs AS j
  JOIN hulagu.tenants AS t ON t.id=j.tenant_id
  JOIN hulagu.source_documents AS d ON d.tenant_id=j.tenant_id AND d.id=j.source_document_id
  WHERE j.id=p_job_id AND j.state='claimed' AND j.attempt=p_attempt
    AND j.lease_token_hash=p_lease_token_hash AND j.lease_expires_at>pg_catalog.now()
    AND j.immutable_input_digest=p_input_digest
    AND j.lifecycle_epoch=p_lifecycle_epoch AND j.work_epoch=p_work_epoch
    AND t.state NOT IN ('PAUSED','DELETE_PENDING','DELETING','DELETED')
    AND t.lifecycle_epoch=p_lifecycle_epoch AND d.parser_work_epoch=p_work_epoch
  ORDER BY j.tenant_id LIMIT 1
  FOR UPDATE OF t,d,j;
  IF NOT FOUND THEN RETURN false; END IF;
  UPDATE hulagu.parser_jobs AS j
  SET state='failed',lease_token_hash=NULL,lease_expires_at=NULL,updated_at=pg_catalog.now()
  WHERE j.tenant_id=v_job.tenant_id AND j.id=v_job.id;
  UPDATE hulagu.source_documents AS d SET parser_state='failed'
  WHERE d.tenant_id=v_job.tenant_id AND d.id=v_job.source_document_id;
  RETURN true;
END
$$;

REVOKE ALL ON hulagu.parser_jobs FROM PUBLIC;
REVOKE ALL ON FUNCTION hulagu.parser_job_immutable_guard() FROM PUBLIC;
REVOKE ALL ON FUNCTION hulagu_api.enqueue_parser_job(uuid,text,text,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION hulagu_api.claim_parser_job(text,integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION hulagu_api.complete_parser_job(uuid,integer,text,text,bigint,bigint,text,jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION hulagu_api.fail_parser_job(uuid,integer,text,text,bigint,bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION hulagu_api.enqueue_parser_job(uuid,text,text,text) TO hulagu_app;
GRANT EXECUTE ON FUNCTION hulagu_api.claim_parser_job(text,integer) TO hulagu_runner;
GRANT EXECUTE ON FUNCTION hulagu_api.complete_parser_job(uuid,integer,text,text,bigint,bigint,text,jsonb) TO hulagu_runner;
GRANT EXECUTE ON FUNCTION hulagu_api.fail_parser_job(uuid,integer,text,text,bigint,bigint) TO hulagu_runner;
RESET ROLE;
