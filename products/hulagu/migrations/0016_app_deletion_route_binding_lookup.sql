SET ROLE hulagu_owner;
SET search_path = pg_catalog;

-- The app may validate only the HMAC metadata for a live, already-claimed
-- deletion delivery. It receives no tenant, route ciphertext, token, subject,
-- tombstone, or receipt data and retains no direct global-table grant.
CREATE FUNCTION hulagu_api.app_deletion_route_binding(
  p_deletion_id uuid
) RETURNS TABLE(route_key_version integer, route_binding_digest text)
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog
AS $$
  SELECT d.route_key_version, d.route_binding_digest
  FROM hulagu.deletion_jobs AS d
  WHERE d.deletion_id = p_deletion_id
    AND d.state = 'delivery_pending'
    AND d.expires_at > pg_catalog.now()
    AND d.encrypted_route IS NULL
    AND d.delivery_token_hash IS NOT NULL
    AND d.route_binding_digest ~ '^[0-9a-f]{64}$'
$$;

REVOKE ALL ON FUNCTION hulagu_api.app_deletion_route_binding(uuid)
FROM PUBLIC, hulagu_app, hulagu_runner, hulagu_deletion, hulagu_readonly;
GRANT EXECUTE ON FUNCTION hulagu_api.app_deletion_route_binding(uuid)
TO hulagu_app;

RESET ROLE;
