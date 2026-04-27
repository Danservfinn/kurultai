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

## Consolidated-answer rules

1. For any non-trivial, shared, tool-using, state-changing, protocol, governance, or both-bots-relevant request, coordinate internally before answering.
2. Coordination must designate one visible owner, one support bot, intended action, and what support input is needed for the consolidated answer.
3. Coordination that affects Danny must be visible in `Kurultai Internal Coms` by using handoffs with `mirror: true` when appropriate.
4. The main Kurultai chat should receive one consolidated answer created from both bots' input.
5. Do not provide two separate substantive answers in the main Kurultai chat.
6. The support bot contributes internally and stays quiet unless correcting a material error, reporting a blocker/completion/failure, answering a direct coordination-audit question, or accepting explicit ownership transfer.
7. Direct mention does not override consolidated-answer discipline for non-trivial/shared matters; coordinate first and either contribute internally or transfer ownership.
8. Failures or blockers must be reported back in the main group by the visible owner unless ownership is transferred.
