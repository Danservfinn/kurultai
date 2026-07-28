SET ROLE hulagu_owner;
SET search_path = pg_catalog;

CREATE TABLE hulagu.customer_profiles (
  tenant_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT public.gen_random_uuid(),
  profile_version bigint NOT NULL CHECK (profile_version > 0),
  profile_json jsonb NOT NULL,
  state text NOT NULL CHECK (state IN ('draft','interviewing','awaiting_confirmation','confirmed')),
  created_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
  PRIMARY KEY (tenant_id, id),
  FOREIGN KEY (tenant_id) REFERENCES hulagu.tenants(id) ON DELETE CASCADE,
  UNIQUE (tenant_id, profile_version)
);

CREATE TABLE hulagu.profile_answers (
  tenant_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT public.gen_random_uuid(),
  profile_id uuid NOT NULL,
  question_id text NOT NULL,
  answer jsonb NOT NULL,
  provenance jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
  PRIMARY KEY (tenant_id, id),
  FOREIGN KEY (tenant_id, profile_id) REFERENCES hulagu.customer_profiles(tenant_id, id) ON DELETE CASCADE,
  UNIQUE (tenant_id, profile_id, question_id, id)
);

CREATE TABLE hulagu.source_documents (
  tenant_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT public.gen_random_uuid(),
  digest text NOT NULL CHECK (digest ~ '^[0-9a-f]{64}$'),
  parser_state text NOT NULL,
  retention_state text NOT NULL,
  storage_ref text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
  PRIMARY KEY (tenant_id, id),
  FOREIGN KEY (tenant_id) REFERENCES hulagu.tenants(id) ON DELETE CASCADE,
  UNIQUE (tenant_id, digest),
  CHECK (storage_ref LIKE '/tenants/' || tenant_id::text || '/%')
);

CREATE TABLE hulagu.search_runs (
  tenant_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT public.gen_random_uuid(),
  profile_id uuid,
  state text NOT NULL,
  query_plan jsonb NOT NULL,
  budget jsonb NOT NULL,
  work_epoch bigint NOT NULL DEFAULT 0 CHECK (work_epoch >= 0),
  created_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
  updated_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
  PRIMARY KEY (tenant_id, id),
  FOREIGN KEY (tenant_id) REFERENCES hulagu.tenants(id) ON DELETE CASCADE,
  FOREIGN KEY (tenant_id, profile_id) REFERENCES hulagu.customer_profiles(tenant_id, id),
  UNIQUE (tenant_id, id, work_epoch)
);

CREATE TABLE hulagu.job_attempts (
  tenant_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT public.gen_random_uuid(),
  run_id uuid NOT NULL,
  attempt integer NOT NULL CHECK (attempt > 0),
  lease_token_hash text CHECK (lease_token_hash IS NULL OR lease_token_hash ~ '^[0-9a-f]{64}$'),
  immutable_input_digest text NOT NULL CHECK (immutable_input_digest ~ '^[0-9a-f]{64}$'),
  lifecycle_epoch bigint NOT NULL,
  work_epoch bigint NOT NULL,
  lease_expires_at timestamptz,
  state text NOT NULL CHECK (state IN ('queued','claimed','succeeded','failed','expired')),
  result_digest text,
  PRIMARY KEY (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES hulagu.search_runs(tenant_id, id) ON DELETE CASCADE,
  UNIQUE (tenant_id, run_id, attempt)
);

CREATE TABLE hulagu.provider_requests (
  tenant_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT public.gen_random_uuid(),
  run_id uuid NOT NULL,
  idempotency_key text NOT NULL,
  request_digest text NOT NULL CHECK (request_digest ~ '^[0-9a-f]{64}$'),
  budget_charge integer NOT NULL CHECK (budget_charge >= 0),
  response_digest text,
  outcome text NOT NULL CHECK (outcome IN ('pending','succeeded','failed','delivery_unknown')),
  PRIMARY KEY (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES hulagu.search_runs(tenant_id, id) ON DELETE CASCADE,
  UNIQUE (tenant_id, idempotency_key)
);

CREATE TABLE hulagu.search_candidates (
  tenant_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT public.gen_random_uuid(),
  run_id uuid NOT NULL,
  listing_key text NOT NULL,
  evidence jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
  PRIMARY KEY (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES hulagu.search_runs(tenant_id, id) ON DELETE CASCADE,
  UNIQUE (tenant_id, run_id, listing_key)
);

CREATE TABLE hulagu.candidate_decisions (
  tenant_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT public.gen_random_uuid(),
  candidate_id uuid NOT NULL,
  decision text NOT NULL CHECK (decision IN ('saved','rejected')),
  reason text,
  created_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
  PRIMARY KEY (tenant_id, id),
  FOREIGN KEY (tenant_id, candidate_id) REFERENCES hulagu.search_candidates(tenant_id, id) ON DELETE CASCADE,
  UNIQUE (tenant_id, candidate_id)
);

CREATE INDEX search_runs_claim_idx ON hulagu.search_runs (state, created_at, tenant_id, id);
CREATE INDEX job_attempts_claim_idx ON hulagu.job_attempts (state, lease_expires_at, tenant_id, id);
CREATE INDEX provider_requests_run_idx ON hulagu.provider_requests (tenant_id, run_id, id);
RESET ROLE;
