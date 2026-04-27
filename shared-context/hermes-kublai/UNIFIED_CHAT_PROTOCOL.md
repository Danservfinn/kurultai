# Unified Telegram Chat Protocol

Goal: Danny should receive one coherent answer in the main Kurultai chat, created from Hermes/Kublai coordination.

## Final decision

Use an **internal-first, single aggregator answer** model.

- Main Kurultai chat (`telegram:-5287556083`) is human-facing.
- `Kurultai Internal Coms` (`telegram:-5161727622`) is where Danny sees coordination/handoffs.
- The internal handoff file is the source of truth:
  `/Users/kublai/.openclaw/agents/main/shared-context/hermes-kublai/handoffs.jsonl`
- The response lock file prevents duplicate answers:
  `/Users/kublai/.openclaw/agents/main/shared-context/hermes-kublai/response_lock.json`

## Hard rule

For any non-trivial, shared, tool-using, state-changing, protocol, governance, or both-bots-relevant request:

1. Coordinate in Internal Coms / handoffs first.
2. Claim or read the response lock.
3. Exactly one bot is the **aggregator**.
4. The support bot contributes internally only.
5. The aggregator posts the single synthesized answer in the main chat.

No two separate substantive answers in the main Kurultai chat.

## Aggregator selection

- Default aggregator: **Kublai** for routing, status, project management, governance, proposals, protocol, and coordination questions.
- Hermes may be aggregator for ops/execution/system-verification answers only if Hermes explicitly claims ownership in `response_lock.json` or Kublai transfers ownership by handoff.
- If no lock exists, Kublai should create one before answering shared/non-trivial requests.
- If a lock exists and names the other bot as aggregator, do not answer substantively in main chat.

## Support bot behavior

The support bot must not post its own substantive answer in the main chat. It should:

- append a handoff with `mirror: true` when Danny should see coordination in Internal Coms;
- add facts, objections, or recommended wording internally;
- stay silent in main chat unless:
  - correcting a material safety/error issue,
  - reporting a blocker/completion/failure,
  - answering a direct coordination-audit question,
  - or accepting explicit ownership transfer.

If directly mentioned, the support bot may answer narrowly about process, but must not duplicate the substantive answer.

## Default flow

1. **Receive request**
   - If trivial and addressed to one bot only: that bot may answer normally.
   - Otherwise: coordinate and use the response lock.

2. **Coordinate internally**
   - Append handoff with owner/support and requested contribution.
   - Use `mirror: true` so Danny can see coordination in Kurultai Internal Coms when it affects him.

3. **Set lock/state**
   - Update `response_lock.json` with request, aggregator, support bot, status, createdAt, expiresAt.
   - Update `group_state.json` if the request changes visible ownership or next update condition.

4. **Post one answer**
   - Aggregator synthesizes both bots' input.
   - Main chat receives one answer only.

5. **Complete**
   - For user-requested tasks, report completion/failure/blocker in main chat with task id, assigned agent, outcome, concise summary, and next action if any.
   - Routine cron/no-op jobs stay quiet.

## Human-facing examples

- “I’ll coordinate with Hermes in Internal Coms, then post our single consolidated answer here.”
- “Kublai/Hermes consolidated answer: …”
- “Hermes owns execution; Kublai will aggregate the final report here.”
