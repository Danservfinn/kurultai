SET ROLE hulagu_owner;
SET search_path = pg_catalog;

CREATE TABLE hulagu.wiki_publications (
  tenant_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT public.gen_random_uuid(),
  generation bigint NOT NULL CHECK (generation > 0),
  manifest_digest text NOT NULL CHECK (manifest_digest ~ '^[0-9a-f]{64}$'),
  storage_ref text NOT NULL,
  visibility_state text NOT NULL CHECK (visibility_state IN ('staged','active','superseded')),
  lifecycle_epoch bigint NOT NULL,
  work_epoch bigint NOT NULL,
  publication_sequence bigint NOT NULL CHECK (publication_sequence > 0),
  PRIMARY KEY (tenant_id, id),
  FOREIGN KEY (tenant_id) REFERENCES hulagu.tenants(id) ON DELETE CASCADE,
  UNIQUE (tenant_id, generation),
  UNIQUE (tenant_id, publication_sequence),
  CHECK (storage_ref LIKE '/tenants/' || tenant_id::text || '/%')
);

CREATE TABLE hulagu.outbox_messages (
  tenant_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT public.gen_random_uuid(),
  kind text NOT NULL CHECK (kind <> 'deletion_completion'),
  payload jsonb NOT NULL,
  lifecycle_epoch bigint NOT NULL,
  work_epoch bigint NOT NULL,
  state text NOT NULL CHECK (state IN ('pending','claimed','sent','delivery_unknown','cancelled')),
  lease_token_hash text,
  lease_expires_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
  PRIMARY KEY (tenant_id, id),
  FOREIGN KEY (tenant_id) REFERENCES hulagu.tenants(id) ON DELETE CASCADE
);

CREATE TABLE hulagu.receipts (
  tenant_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT public.gen_random_uuid(),
  event_class text NOT NULL,
  redacted_payload jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
  PRIMARY KEY (tenant_id, id),
  FOREIGN KEY (tenant_id) REFERENCES hulagu.tenants(id) ON DELETE CASCADE
);

CREATE INDEX outbox_claim_idx ON hulagu.outbox_messages (state, created_at, tenant_id, id);
CREATE INDEX receipts_tenant_time_idx ON hulagu.receipts (tenant_id, created_at, id);
RESET ROLE;
