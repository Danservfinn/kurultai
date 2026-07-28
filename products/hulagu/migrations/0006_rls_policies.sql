SET ROLE hulagu_owner;
SET search_path = pg_catalog;

ALTER TABLE hulagu.tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE hulagu.tenants FORCE ROW LEVEL SECURITY;
CREATE POLICY tenants_tenant_isolation ON hulagu.tenants
  USING (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE hulagu.identity_bindings ENABLE ROW LEVEL SECURITY;
ALTER TABLE hulagu.identity_bindings FORCE ROW LEVEL SECURITY;
CREATE POLICY identity_bindings_tenant_isolation ON hulagu.identity_bindings
  USING (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE hulagu.customer_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE hulagu.customer_profiles FORCE ROW LEVEL SECURITY;
CREATE POLICY customer_profiles_tenant_isolation ON hulagu.customer_profiles
  USING (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE hulagu.profile_answers ENABLE ROW LEVEL SECURITY;
ALTER TABLE hulagu.profile_answers FORCE ROW LEVEL SECURITY;
CREATE POLICY profile_answers_tenant_isolation ON hulagu.profile_answers
  USING (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE hulagu.source_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE hulagu.source_documents FORCE ROW LEVEL SECURITY;
CREATE POLICY source_documents_tenant_isolation ON hulagu.source_documents
  USING (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE hulagu.search_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE hulagu.search_runs FORCE ROW LEVEL SECURITY;
CREATE POLICY search_runs_tenant_isolation ON hulagu.search_runs
  USING (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE hulagu.job_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE hulagu.job_attempts FORCE ROW LEVEL SECURITY;
CREATE POLICY job_attempts_tenant_isolation ON hulagu.job_attempts
  USING (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE hulagu.provider_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE hulagu.provider_requests FORCE ROW LEVEL SECURITY;
CREATE POLICY provider_requests_tenant_isolation ON hulagu.provider_requests
  USING (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE hulagu.search_candidates ENABLE ROW LEVEL SECURITY;
ALTER TABLE hulagu.search_candidates FORCE ROW LEVEL SECURITY;
CREATE POLICY search_candidates_tenant_isolation ON hulagu.search_candidates
  USING (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE hulagu.candidate_decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE hulagu.candidate_decisions FORCE ROW LEVEL SECURITY;
CREATE POLICY candidate_decisions_tenant_isolation ON hulagu.candidate_decisions
  USING (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE hulagu.wiki_publications ENABLE ROW LEVEL SECURITY;
ALTER TABLE hulagu.wiki_publications FORCE ROW LEVEL SECURITY;
CREATE POLICY wiki_publications_tenant_isolation ON hulagu.wiki_publications
  USING (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE hulagu.outbox_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE hulagu.outbox_messages FORCE ROW LEVEL SECURITY;
CREATE POLICY outbox_messages_tenant_isolation ON hulagu.outbox_messages
  USING (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE hulagu.receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE hulagu.receipts FORCE ROW LEVEL SECURITY;
CREATE POLICY receipts_tenant_isolation ON hulagu.receipts
  USING (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE hulagu.retention_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE hulagu.retention_jobs FORCE ROW LEVEL SECURITY;
CREATE POLICY retention_jobs_tenant_isolation ON hulagu.retention_jobs
  USING (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid);

GRANT SELECT, UPDATE ON hulagu.tenants TO hulagu_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON
  hulagu.customer_profiles, hulagu.profile_answers, hulagu.source_documents,
  hulagu.search_runs, hulagu.job_attempts, hulagu.provider_requests,
  hulagu.search_candidates, hulagu.candidate_decisions, hulagu.wiki_publications,
  hulagu.outbox_messages, hulagu.receipts, hulagu.retention_jobs
TO hulagu_app;
RESET ROLE;
