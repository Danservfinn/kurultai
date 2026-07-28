SET ROLE hulagu_owner;
SET search_path = pg_catalog;

CREATE TABLE hulagu.tenants (
  id uuid PRIMARY KEY DEFAULT public.gen_random_uuid(),
  tenant_id uuid GENERATED ALWAYS AS (id) STORED NOT NULL,
  state text NOT NULL CHECK (state IN ('READY','INTERVIEWING','PAUSED','DELETE_PENDING','DELETING','DELETED')),
  lifecycle_epoch bigint NOT NULL DEFAULT 0 CHECK (lifecycle_epoch >= 0),
  current_wiki_generation bigint NOT NULL DEFAULT 0 CHECK (current_wiki_generation >= 0),
  created_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
  updated_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
  UNIQUE (tenant_id, id)
);

CREATE TABLE hulagu.enrollments (
  id uuid PRIMARY KEY DEFAULT public.gen_random_uuid(),
  subject_digest text NOT NULL UNIQUE CHECK (subject_digest ~ '^[0-9a-f]{64}$'),
  subject_fence_digest text NOT NULL CHECK (subject_fence_digest ~ '^[0-9a-f]{64}$'),
  notice_version text NOT NULL,
  consent_nonce_hash text NOT NULL CHECK (consent_nonce_hash ~ '^[0-9a-f]{64}$'),
  expires_at timestamptz NOT NULL,
  rate_count integer NOT NULL DEFAULT 1 CHECK (rate_count BETWEEN 0 AND 1000),
  created_at timestamptz NOT NULL DEFAULT pg_catalog.now()
);

CREATE TABLE hulagu.identity_bindings (
  tenant_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT public.gen_random_uuid(),
  subject_digest text NOT NULL UNIQUE CHECK (subject_digest ~ '^[0-9a-f]{64}$'),
  subject_fence_digest text NOT NULL CHECK (subject_fence_digest ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
  PRIMARY KEY (tenant_id, id),
  FOREIGN KEY (tenant_id) REFERENCES hulagu.tenants(id) ON DELETE CASCADE
);

CREATE TABLE hulagu.inbound_updates (
  bot_id bigint NOT NULL,
  update_id bigint NOT NULL,
  enrollment_id uuid,
  tenant_id uuid,
  processed_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
  outcome_class text NOT NULL,
  expires_at timestamptz NOT NULL,
  PRIMARY KEY (bot_id, update_id),
  FOREIGN KEY (enrollment_id) REFERENCES hulagu.enrollments(id) ON DELETE SET NULL,
  FOREIGN KEY (tenant_id) REFERENCES hulagu.tenants(id) ON DELETE SET NULL,
  CHECK (
    (outcome_class <> 'terminal_dedupe' AND ((enrollment_id IS NOT NULL)::integer + (tenant_id IS NOT NULL)::integer) = 1)
    OR (outcome_class = 'terminal_dedupe' AND enrollment_id IS NULL AND tenant_id IS NULL)
  )
);

CREATE INDEX identity_bindings_tenant_idx ON hulagu.identity_bindings (tenant_id, id);
CREATE INDEX enrollments_expiry_idx ON hulagu.enrollments (expires_at, id);
CREATE INDEX inbound_updates_expiry_idx ON hulagu.inbound_updates (expires_at, bot_id, update_id);
RESET ROLE;
