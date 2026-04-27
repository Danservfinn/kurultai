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

- Danny designated the current Kurultai Telegram group as the internal-comms mirror on 2026-04-26; Hermes sees it as target `telegram:Kurultai` and the current chat displays as Kurultai Internal Coms.
- As of 2026-04-27, Danny wants this Telegram channel to auto-report all raw internal handoff communications.
- Telegram is now the raw visibility feed for Hermes/Kublai handoff JSONL entries.
- Report every new handoff entry, including `mirror: false` entries.
- Preserve raw handoff fields where possible: `ts`, `from`, `to`, `topic`, `summary`, `detail`, `mirror`, `status`.
- Redact obvious secrets, tokens, passwords, API keys, and credential-looking values before posting.
- The internal handoff JSONL remains the source of truth; Telegram is the visibility mirror.

## Ownership rules

1. Direct mention owns the reply.
2. If both bots are mentioned, the most relevant role/context leads.
3. The second bot stays quiet unless adding new value, correcting, or accepting a handoff.
4. Handoffs must be explicit and visible when they affect Danny.
5. Failures or blockers must be reported back in the group.
