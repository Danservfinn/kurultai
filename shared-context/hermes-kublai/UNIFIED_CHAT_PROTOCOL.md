# Unified Telegram Chat Protocol

Goal: Danny should receive one coherent answer in the main Kurultai chat, created from real Hermes/Kublai deliberation that is visible in Kurultai Internal Coms.

## Final decision

Use an **internal-first, reciprocal-deliberation, single-aggregator answer** model.

- Main Kurultai chat (`telegram:-5287556083`) is human-facing.
- `Kurultai Internal Coms` (`telegram:-5161727622`) is where Danny sees coordination/handoffs/deliberation.
- The handoff file is the source of coordination truth:
  `/Users/kublai/.openclaw/agents/main/shared-context/hermes-kublai/handoffs.jsonl`
- The response lock file prevents duplicate answers and tracks readiness:
  `/Users/kublai/.openclaw/agents/main/shared-context/hermes-kublai/response_lock.json`

## Hard rule

For any non-trivial, shared, tool-using, state-changing, protocol, governance, review, or both-bots-relevant request:

1. Coordinate in Internal Coms / handoffs first.
2. Claim or read the response lock.
3. Enter `deliberating` state.
4. Wait until each required bot has actually contributed, or post a visible timeout/blocker in Internal Coms.
5. Aggregator must process the other bot's contribution.
6. Move lock to `ready_to_answer`.
7. Aggregator posts one synthesized answer in the main chat.

No final answer should be posted merely after sending a handoff. The answer is blocked until reciprocal communication is received and processed, unless the blocker/timeout is explicitly surfaced in Internal Coms.

## Required handshake

For both-bot/shared requests, minimum visible deliberation is:

1. **Proposal handoff** — first bot states draft position, questions, and proposed aggregator/support roles.
2. **Receiver response** — other bot acknowledges and adds recommendations, objections, or corrections.
3. **Resolution/ack** — aggregator acknowledges the other bot's input, resolves conflicts, and states readiness.
4. **Final answer** — aggregator posts one consolidated answer in the main chat.

If there is disagreement, add another back-and-forth round before `ready_to_answer`.

## Response lock schema expectations

`response_lock.json` should include:

- `current.request`
- `current.aggregator`
- `current.supportBot`
- `current.status`: `claimed`, `deliberating`, `ready_to_answer`, or `answered`
- `current.requiredContributors`
- `current.receivedContributions`
- `current.processedContributions`
- `current.rule`
- `current.createdAt`
- `current.expiresAt`

For explicitly “both of you” requests, `requiredContributors` must include both `kublai` and `hermes`.

## Aggregator selection

- Default aggregator: Kublai for routing, status, project management, governance, proposals, protocol, and coordination questions.
- Hermes may be aggregator for ops/execution/system-verification answers only if Hermes explicitly claims the lock or Kublai transfers ownership by handoff.
- If no lock exists, create one before answering shared/non-trivial requests.
- If the lock names the other bot as aggregator, do not answer substantively in main chat.

## Support bot behavior

The support bot must not post its own substantive answer in the main chat. It should:

- append handoffs with `mirror: true` so Danny can see deliberation in Internal Coms;
- add facts, objections, or recommended wording internally;
- wait for aggregator synthesis;
- stay silent in main chat unless correcting a material safety/error issue, reporting a blocker/completion/failure, answering a direct coordination-audit question, or accepting explicit ownership transfer.

Direct mention does not override the aggregator/deliberation rule for non-trivial/shared matters.

## Main-chat completion

The final answer should be phrased as a consolidated result, e.g.:

- “Kublai/Hermes consolidated answer after Internal Coms deliberation: …”
- “We reviewed this together. Recommendation: …”

For user-requested tasks, report completion/failure/blocker in main chat with task id, assigned agent, outcome, concise summary, and next action if any. Routine cron/no-op jobs stay quiet.
