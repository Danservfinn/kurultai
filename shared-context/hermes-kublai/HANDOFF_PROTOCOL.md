# Hermes ↔ Kublai Internal Handoff Protocol

Purpose: make Hermes/Kublai coordination reliable because Telegram does not reliably deliver bot-to-bot messages to the other bot. The internal handoff channel is the required bot-to-bot path; Telegram mirrors are only for Danny's visibility.

## Shared files

- `handoffs.jsonl` — append-only internal handoff stream.
- `mirror-state.json` — Kublai-side cursor for mirrored handoffs.

## Handoff JSONL format

Each line is one JSON object:

```json
{
  "ts": "2026-04-26T18:50:00Z",
  "from": "hermes",
  "to": "kublai",
  "topic": "group-chat-protocol",
  "summary": "Short human-readable summary",
  "detail": "Optional internal detail",
  "mirror": true,
  "status": "new"
}
```

## Visibility rules

- Telegram is the human-facing conversation layer, not the bot-to-bot coordination layer.
- Do not automatically mirror raw handoff logs to Telegram.
- `mirror: false` means internal-only unless Danny asks for details.
- `mirror: true` means the visible owner may post one concise human-facing summary if it is useful to Danny.
- Surface only owner/support decisions, blockers, material disagreements, completions/failures, or requested audit trails.
- Routine intermediate reasoning should stay internal.
- For the full chat behavior model, see `UNIFIED_CHAT_PROTOCOL.md`.

## Ownership rules

1. Direct mention owns the reply.
2. If both bots are mentioned, the most relevant role/context leads.
3. The second bot stays quiet unless adding new value, correcting, or accepting a handoff.
4. Handoffs must be explicit and visible when they affect Danny.
5. Failures or blockers must be reported back in the group.
