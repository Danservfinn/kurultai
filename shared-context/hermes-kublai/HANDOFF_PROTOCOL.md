# Hermes ↔ Kublai Internal Handoff Protocol

Purpose: make Hermes/Kublai coordination reliable, visible in Internal Coms, and prevent duplicate or premature answers in the main Kurultai chat.

## Shared files

- `handoffs.jsonl` — append-only internal handoff/deliberation stream.
- `response_lock.json` — current main-chat answer aggregator and readiness lock.
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
- Deliberation that affects Danny should be visible in Internal Coms by using `mirror: true`.
- Redact obvious secrets, tokens, passwords, API keys, and credential-looking values before posting anywhere.
- JSONL + lock files are bot-to-bot state; Telegram is visibility only.

## Reciprocal deliberation rule

For any non-trivial, shared, tool-using, state-changing, protocol, governance, review, or both-bots-relevant request:

1. Coordinate internally before answering.
2. Read or create `response_lock.json`.
3. Set/observe lock status: `claimed` -> `deliberating` -> `ready_to_answer` -> `answered`.
4. Wait for each required contributor to actually respond in handoffs/Internal Coms.
5. Aggregator must acknowledge/process the other bot's contribution.
6. Only then may aggregator post one synthesized answer in the main Kurultai chat.

If a contributor does not respond, aggregator must post a visible timeout/blocker in Internal Coms before answering without that contribution.

## Minimum handshake

1. Proposal handoff from first bot.
2. Receiver response with additions/objections/corrections.
3. Aggregator acknowledgment/resolution.
4. Final single answer in main chat.

## Defaults

- Kublai is default aggregator for routing, status, project management, governance, proposal, protocol, and coordination questions.
- Hermes may be aggregator for ops/execution/system-verification questions only if it explicitly claims the lock or Kublai transfers ownership.

## Support bot constraints

The support bot must not post a separate substantive answer in the main chat. It may speak only for:

- material correction,
- blocker/completion/failure,
- direct coordination-audit question,
- explicit ownership transfer.

Direct mention does not override the aggregator/deliberation rule for non-trivial/shared matters.
