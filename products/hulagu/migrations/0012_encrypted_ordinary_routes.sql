SET ROLE hulagu_owner;
SET search_path = pg_catalog;

-- Fail closed on any pre-envelope ordinary work. A forward migration cannot
-- synthesize ciphertext without runtime keys, so it cancels the row and removes
-- a legacy plaintext route instead of preserving a sendable bypass.
UPDATE hulagu.outbox_messages AS o
SET state = 'cancelled',
    payload = o.payload - 'chat_id',
    lease_token_hash = NULL,
    lease_expires_at = NULL,
    delivered_at = NULL
WHERE o.kind = 'ordinary'
  AND o.payload ? 'chat_id';

-- Any ordinary payload that carries a return route may carry only a bounded
-- envelope-encrypted route. Generic route-free queue fixtures remain non-sendable,
-- and no row may retain a plaintext chat_id.
ALTER TABLE hulagu.outbox_messages
  ADD CONSTRAINT outbox_messages_ordinary_route_encrypted CHECK (
    kind <> 'ordinary'
    OR (
      NOT payload ? 'chat_id'
      AND (
        state = 'cancelled'
        OR NOT payload ? 'sealed_route'
        OR (
          pg_catalog.jsonb_typeof(payload -> 'sealed_route') = 'object'
          AND pg_catalog.jsonb_typeof(payload -> 'sealed_route' -> 'active_key_version') = 'number'
          AND (payload -> 'sealed_route' ->> 'active_key_version')::bigint BETWEEN 1 AND 2147483647
          AND pg_catalog.jsonb_typeof(payload -> 'sealed_route' -> 'route_generation') = 'number'
          AND (payload -> 'sealed_route' ->> 'route_generation')::bigint BETWEEN 1 AND 9223372036854775807
          AND pg_catalog.jsonb_typeof(payload -> 'sealed_route' -> 'ciphertext') = 'string'
          AND pg_catalog.octet_length(payload -> 'sealed_route' ->> 'ciphertext') BETWEEN 1 AND 4096
          AND pg_catalog.jsonb_typeof(payload -> 'sealed_route' -> 'active_wrapped_data_key') = 'string'
          AND pg_catalog.octet_length(payload -> 'sealed_route' ->> 'active_wrapped_data_key') BETWEEN 1 AND 4096
          AND (payload -> 'sealed_route' ->> 'binding_digest') ~ '^[0-9a-f]{64}$'
        )
      )
    )
  );

RESET ROLE;
