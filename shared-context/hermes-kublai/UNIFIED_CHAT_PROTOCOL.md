# Unified Telegram Chat Protocol

Goal: Danny should receive one coherent answer in the main Kurultai chat, created from real Hermes/Kublai deliberation that is visible in Kurultai Internal Coms.

## Final decision

Use an **internal-first, reciprocal-deliberation, single-aggregator answer** model.

- Main Kurultai chat (`telegram:-5287556083`) is human-facing.
- `Kurultai Internal Coms` (`telegram:-5161727622`) is where Danny sees coordination/handoffs/deliberation.
- The authoritative Phase 1 coordination store is SQLite WAL:
  `/Users/kublai/.openclaw/agents/main/shared-context/hermes-kublai/coordination.db`
- The standalone helper API/CLI are:
  `/Users/kublai/.openclaw/agents/main/shared-context/hermes-kublai/coordination_store.py`
  `/Users/kublai/.openclaw/agents/main/shared-context/hermes-kublai/coordination_cli.py`
- Legacy handoff/JSON files are preserved for visibility/backward compatibility, not as the future authoritative lock/outbox:
  `/Users/kublai/.openclaw/agents/main/shared-context/hermes-kublai/handoffs.jsonl`
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

## Phase 1 SQLite WAL implementation

The implemented MVP spine uses these tables:

- `response_locks` — one owner per channel/chat/thread/root-message/purpose.
- `coordination_events` — append-only audit trail for claims, contributions, and finalization.
- `contributions` — internal support-agent summaries/details for aggregator synthesis.
- `send_outbox` — idempotent public-send reservation keyed by deterministic `send_key`.

Use the helper CLI before any same-group final answer:

```bash
/opt/homebrew/opt/python@3.14/bin/python3.14 \
  /Users/kublai/.openclaw/agents/main/shared-context/hermes-kublai/coordination_cli.py init

/opt/homebrew/opt/python@3.14/bin/python3.14 \
  /Users/kublai/.openclaw/agents/main/shared-context/hermes-kublai/coordination_cli.py claim \
  --channel telegram --chat-id <chat_id> --root-message-id <root_message_id> \
  --owner kublai --tier tier2 --required-contributor hermes

# after required contributions are received + processed and the owner is ready:
/opt/homebrew/opt/python@3.14/bin/python3.14 \
  /Users/kublai/.openclaw/agents/main/shared-context/hermes-kublai/coordination_cli.py reserve-public-send \
  --lock-id <lock_id> --actor kublai --text '<final synthesized answer>'

# after Telegram confirms the post:
/opt/homebrew/opt/python@3.14/bin/python3.14 \
  /Users/kublai/.openclaw/agents/main/shared-context/hermes-kublai/coordination_cli.py mark-public-sent \
  --lock-id <lock_id> --actor kublai --send-key <send_key> --provider-message-id <telegram_message_id>
```

`reserve-public-send` is mandatory and must return `"allowed": true` before a same-group public final answer is sent. It denies non-owners, missing required processed contributions, unapproved human-approval locks, and duplicate reservations. `telegram_send.send_once()` uses the same owner-aware gate and finalizes the lock via `mark_public_answer_sent()` after Telegram success. Raw `telegram_send.send()` now denies by default with `RAW_SEND_DENIED` unless the caller supplies an explicit `bypass_reason`; bypasses are logged as `RAW_SEND_BYPASS` and are reserved for cross-chat/operator notifications, never same-group final answers.

## Legacy response lock schema expectations

`response_lock.json` should include:

- `current.request`
- `current.aggregator`
- `current.supportBot`
- `current.status`: `claimed`, `deliberating`, `ready_to_answer`, `answering`, or `answered`
- `current.requiredContributors`
- `current.receivedContributions`
- `current.processedContributions`
- `current.rule`
- `current.createdAt`
- `current.expiresAt`
- `current.answeredAt` — ISO timestamp when the final answer was confirmed sent (set during `answering → answered` transition)
- `current.answeredMessageId` — Telegram message_id integer returned by the sendMessage API call

For explicitly “both of you” requests, `requiredContributors` must include both `kublai` and `hermes`.

## Post-answer lock update (mandatory)

After posting a final main-chat answer, the aggregator **must** atomically update `response_lock.json`:
1. Set `current.status` to `answered`
2. Set `current.answeredAt` to the current ISO timestamp
3. Set `current.answeredMessageId` to the Telegram message_id returned by the API

Write via atomic rename (`write to .tmp` → `os.replace()`) to prevent partial reads. If the answeredMessageId is already populated when a new message arrives, the lock is idempotent — skip posting and log a dedup hit.

## Provenance / attribution question detection

A message is a **provenance/attribution question** if it contains any of these patterns (case-insensitive):
- “did [kublai|hermes] contribute”
- “did you contribute”  
- “why did [kublai|hermes] answer”
- “who [responded|answered|replied]”
- “protocol followed”
- “was [kublai|hermes] involved”

Such messages **must** open a fresh lock entry before any answer is posted, regardless of whether a prior `answered` lock exists for a related session. The prior `answered` lock covers only the original request, not the provenance question.

## Aggregator selection

- Default aggregator: Kublai for routing, status, project management, governance, proposals, protocol, and coordination questions.
- Hermes may be aggregator for ops/execution/system-verification answers only if Kublai transfers ownership by handoff or the lock is unclaimed.
- The support bot must never self-transfer aggregator ownership for an active request.
- The support bot must never decide that aggregator timeout permits it to post a competing main-chat answer; it may only post a blocker/escalation in Kurultai Internal Coms.
- If no lock exists, create one before answering shared/non-trivial requests.
- If the lock names the other bot as aggregator, do not answer substantively in main chat.
- Once lock status is `answering` or `answered`, no bot may post another substantive main-chat answer for that request.
- A prior `answered` lock applies only to that exact request; any new user turn asking whether protocol was followed, whether Kublai/Hermes contributed, or why a both-agent answer failed requires a fresh lock and fresh reciprocal contribution.
- `operatorOverride` is not a shortcut for both-agent/protocol/provenance incidents unless Danny explicitly says the answer should come from one named bot only.

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
