SET ROLE hulagu_owner;
SET search_path = pg_catalog;

-- Callback IDs are a secondary replay fence: one Telegram callback may arrive in
-- multiple updates, but it may produce effects only once for the approved bot.
ALTER TABLE hulagu.inbound_updates
  ADD COLUMN callback_query_id text,
  ADD CONSTRAINT inbound_updates_callback_query_id_bounded
    CHECK (
      callback_query_id IS NULL
      OR pg_catalog.octet_length(callback_query_id) BETWEEN 1 AND 256
    );
CREATE UNIQUE INDEX inbound_updates_callback_replay_key
  ON hulagu.inbound_updates (bot_id, callback_query_id)
  WHERE callback_query_id IS NOT NULL;

-- This privileged global control row is updated in the same transaction as the
-- normalized update, its dedupe marker, and all state/outbox effects. Runtime
-- roles intentionally receive no direct table grants.
CREATE TABLE hulagu.telegram_polling_offsets (
  bot_id bigint PRIMARY KEY CHECK (bot_id > 0),
  next_update_id bigint NOT NULL CHECK (next_update_id >= 0),
  updated_at timestamptz NOT NULL DEFAULT pg_catalog.now()
);
REVOKE ALL ON hulagu.telegram_polling_offsets FROM PUBLIC;

-- Existing rows receive a deterministic compatibility key. New writers must
-- supply a domain-stable run/event key; no random default can silently weaken
-- internal retry idempotency.
ALTER TABLE hulagu.outbox_messages ADD COLUMN delivery_key text;
UPDATE hulagu.outbox_messages
SET delivery_key = 'legacy:' || tenant_id::text || ':' || id::text;
ALTER TABLE hulagu.outbox_messages
  ALTER COLUMN delivery_key SET NOT NULL,
  ADD CONSTRAINT outbox_messages_delivery_key_bounded
    CHECK (pg_catalog.octet_length(delivery_key) BETWEEN 1 AND 256),
  ADD CONSTRAINT outbox_messages_tenant_delivery_key_unique
    UNIQUE (tenant_id, delivery_key);

RESET ROLE;
