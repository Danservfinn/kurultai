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

- The main Kurultai Telegram chat (`telegram:-5287556083`) is human-facing. Do not post raw internal handoff logs there.
- The separate `Kurultai Internal Coms` Telegram chat (`telegram:-5161727622`) is the raw internal-comms visibility mirror.
- As of 2026-04-27, Danny wants raw handoff entries auto-reported only in `Kurultai Internal Coms`, including entries with `mirror: false`.
- Preserve raw handoff fields where possible in the internal-comms mirror: `ts`, `from`, `to`, `topic`, `summary`, `detail`, `mirror`, `status`.
- Redact obvious secrets, tokens, passwords, API keys, and credential-looking values before posting anywhere.
- The internal handoff JSONL remains the source of truth; Telegram mirrors are visibility surfaces, not bot-to-bot state.

## Coordinated-answer rules

1. For any non-trivial, shared, tool-using, state-changing, protocol, governance, or both-bots-relevant request, coordinate internally before answering.
2. Coordination must designate lead/owner, support bot, intended action, and answer mode: `single-combined` or `individual-answers`.
3. Danny may receive individual answers from both Hermes and Kublai after coordination, especially when he asks both bots or separate perspectives are useful.
4. Coordination that affects Danny must be visible in `Kurultai Internal Coms` by using handoffs with `mirror: true` when appropriate.
5. Individual answers should be clearly attributable and non-duplicative; each bot should add its own perspective rather than repeating the same substance.
6. Direct mention can request an individual answer, but the mentioned bot must still coordinate first for non-trivial/shared matters.
7. A bot may speak without waiting only for urgent safety containment, material correction, blocker, completion/failure, explicit ownership transfer, or a direct audit question from Danny.
8. Failures or blockers must be reported back in the main group by the lead/owner unless ownership is transferred.
