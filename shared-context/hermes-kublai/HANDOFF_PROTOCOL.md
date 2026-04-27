# Hermes ↔ Kublai Internal Handoff Protocol

Purpose: make Hermes/Kublai coordination reliable and prevent duplicate answers in the main Kurultai chat.

## Shared files

- `handoffs.jsonl` — append-only internal handoff stream.
- `response_lock.json` — current main-chat answer aggregator lock.
- `group_state.json` — current shared request/ownership state.
- `mirror-state.json` — mirror cursor state.

## Handoff JSONL format

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

- Main Kurultai Telegram chat (`telegram:-5287556083`) is human-facing. Do not post raw internal handoff logs there.
- `Kurultai Internal Coms` (`telegram:-5161727622`) is the coordination/internal-comms mirror.
- Coordination that affects Danny should be visible in Internal Coms by using `mirror: true` when appropriate.
- Redact obvious secrets, tokens, passwords, API keys, and credential-looking values before posting anywhere.
- JSONL + lock files are bot-to-bot state; Telegram is visibility only.

## Aggregator rule

For any non-trivial, shared, tool-using, state-changing, protocol, governance, or both-bots-relevant request:

1. Coordinate internally before answering.
2. Read or create `response_lock.json`.
3. Exactly one bot is the main-chat **aggregator**.
4. The support bot contributes internally only.
5. The aggregator posts one synthesized answer in the main Kurultai chat.

## Defaults

- Kublai is default aggregator for routing, status, project management, governance, proposal, protocol, and coordination questions.
- Hermes may be aggregator for ops/execution/system-verification questions only if it explicitly claims the lock or Kublai transfers ownership.

## Support bot constraints

The support bot must not post a separate substantive answer in the main chat. It may speak only for:

- material correction,
- blocker/completion/failure,
- direct coordination-audit question,
- explicit ownership transfer.

Direct mention does not override the aggregator rule for non-trivial/shared matters.
