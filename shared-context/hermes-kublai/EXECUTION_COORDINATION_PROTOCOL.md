# Hermes ↔ Kublai Execution Coordination Protocol

Before either bot executes non-trivial work from the shared Telegram group, it should coordinate internally first.

## Applies to

- Actions that change files, config, cron, routing, tasks, state, or external systems.
- Investigations likely to use tools or produce operational conclusions.
- Any request addressed to both Hermes and Kublai.

## Does not apply to

- Simple acknowledgments.
- Direct factual answers that need no tools and no state changes.
- Urgent safety/incident containment where delay would increase risk; in that case act, then immediately post a handoff summary.

## Pre-execution handoff

1. The bot that sees the request first writes a `pre-exec` handoff with:
   - request summary
   - proposed owner
   - proposed supporting role
   - intended actions
   - whether human-visible summary is needed
2. The other bot responds with `ack`, `amend`, or `takeover` when available.
3. If no response is available and the work is low-risk/reversible, the first bot may proceed after stating the assumption in the group.
4. For risky, irreversible, or config-changing work, wait for human confirmation or explicit cross-bot agreement.

## JSONL examples

```json
{"ts":"2026-04-26T19:30:00Z","from":"kublai","to":"hermes","topic":"pre-exec","summary":"Danny asked us to update protocol. Proposed: Kublai updates docs, Hermes validates integration.","detail":"Owner=kublai; support=hermes; actions=doc update + test handoff.","mirror":false,"status":"new"}
```

```json
{"ts":"2026-04-26T19:31:00Z","from":"hermes","to":"kublai","topic":"pre-exec-ack","summary":"Agree: Kublai owns protocol update; Hermes validates after change.","detail":"Proceed.","mirror":true,"status":"ack"}
```

## Human-visible rule

When coordination materially affects Danny, mirror a short summary to Telegram:

- who owns execution
- who supports/reviews
- what will be done
- any blocker or assumption
