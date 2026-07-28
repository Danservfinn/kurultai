SET ROLE hulagu_owner;
SET search_path = pg_catalog;

-- Global deletion rows deliberately have no tenant foreign key. The target and route
-- exist only while erasure is active and are nulled before terminal receipt creation.
CREATE TABLE hulagu.deletion_jobs (
  deletion_id uuid PRIMARY KEY DEFAULT public.gen_random_uuid(),
  target_tenant_id uuid,
  subject_fence_digest text CHECK (subject_fence_digest IS NULL OR subject_fence_digest ~ '^[0-9a-f]{64}$'),
  encrypted_route text,
  route_binding_digest text,
  route_key_version integer NOT NULL DEFAULT 1,
  delivery_token_hash text,
  state text NOT NULL CHECK (state IN ('pending','erasing','delivery_pending','complete','failed')),
  created_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
  expires_at timestamptz NOT NULL,
  CHECK ((state IN ('pending','erasing','delivery_pending') AND target_tenant_id IS NOT NULL)
      OR (state IN ('complete','failed') AND target_tenant_id IS NULL AND encrypted_route IS NULL))
);

-- Tombstones are stable, pseudonymous re-enrollment fences. They contain neither a
-- tenant UUID nor an ordinary identity digest, and remain valid across subject-key rotation.
CREATE TABLE hulagu.deletion_tombstones (
  subject_fence_digest text PRIMARY KEY CHECK (subject_fence_digest ~ '^[0-9a-f]{64}$'),
  key_version integer NOT NULL CHECK (key_version > 0),
  barred_until timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT pg_catalog.now()
);

-- Terminal receipts are content-free and route-free. They expire independently of tenants.
CREATE TABLE hulagu.deletion_receipts (
  deletion_id uuid PRIMARY KEY,
  outcome text NOT NULL CHECK (outcome IN ('completed','delivery_unknown','failed')),
  completed_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
  expires_at timestamptz NOT NULL
);

CREATE TABLE hulagu.retention_jobs (
  tenant_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT public.gen_random_uuid(),
  scope text NOT NULL CHECK (scope IN ('document','publication','receipt','tenant_expiry')),
  object_id uuid,
  state text NOT NULL CHECK (state IN ('pending','claimed','complete','failed')),
  lifecycle_epoch bigint NOT NULL,
  lease_token_hash text,
  lease_expires_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
  PRIMARY KEY (tenant_id, id),
  FOREIGN KEY (tenant_id) REFERENCES hulagu.tenants(id) ON DELETE CASCADE
);

CREATE TABLE hulagu.global_storage_state (
  singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
  pressure_state text NOT NULL CHECK (pressure_state IN ('normal','low','critical')),
  measured_bytes bigint NOT NULL CHECK (measured_bytes >= 0),
  checked_at timestamptz NOT NULL DEFAULT pg_catalog.now()
);

CREATE INDEX deletion_jobs_claim_idx ON hulagu.deletion_jobs (state, created_at, deletion_id);
CREATE INDEX deletion_tombstones_expiry_idx ON hulagu.deletion_tombstones (barred_until, subject_fence_digest);
CREATE INDEX deletion_receipts_expiry_idx ON hulagu.deletion_receipts (expires_at, deletion_id);
CREATE INDEX retention_jobs_claim_idx ON hulagu.retention_jobs (state, created_at, tenant_id, id);
RESET ROLE;
