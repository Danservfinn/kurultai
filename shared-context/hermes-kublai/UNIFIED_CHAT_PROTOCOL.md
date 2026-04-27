# Unified Telegram Chat Protocol

Goal: Danny should experience one coherent group conversation even though Hermes and Kublai coordinate through an internal handoff system.

## Final decision

Use an **internal-first, single-answer** model.

Danny designated a separate Telegram group `Kurultai Internal Coms` as the raw internal-comms mirror. Bot-to-bot state still lives in the internal handoff files, but every new handoff line may be mirrored only to `telegram:Kurultai Internal Coms` / chat id `-5161727622` with credential-looking values redacted.

- Internal handoffs are the bot-to-bot coordination layer.
- Main Kurultai chat (`telegram:-5287556083`) is human-facing: no raw handoff logs there.
- `Kurultai Internal Coms` (`telegram:-5161727622`) is the raw handoff visibility mirror.
- For any non-trivial, shared, tool-using, state-changing, or both-bots-relevant request, Hermes and Kublai coordinate internally before answering.
- The result must be **one single answer to Danny**, posted by one visible owner.
- The non-owner must not provide a parallel answer. It contributes internally, then stays quiet unless there is a material correction, blocker, completion, or Danny directly asks that bot to audit whether coordination happened.
- Raw handoffs are mirrored to `Kurultai Internal Coms`; do not mirror credentials or secrets.

## Default flow

1. **Receive request**
   - If trivial and addressed to one bot only: that bot may answer normally.
   - If the request is non-trivial, asks both bots, affects shared state, uses tools, changes files/config/cron/tasks, involves protocol, or could produce duplicated answers: append an internal pre-exec handoff first.

2. **Coordinate internally**
   - Use `handoffs.jsonl` / `append_handoff.py`.
   - State: proposed visible owner, support bot, intended action, and expected user-facing answer type.
   - If time-sensitive, owner may proceed after posting the handoff, but must still produce one combined answer.

3. **Choose the visible owner**
   - Kublai leads coordination, project/status/routing, governance, and group protocol.
   - Hermes leads operational execution, verification, caretaker/system observations.
   - If one bot has clearly better context, that bot leads regardless of default role.

4. **Set shared state**
   - Update `group_state.json` with active request, visible owner, support bot, intended actions, and next update condition.

5. **Provide one answer in Telegram**
   - The visible owner posts the single answer.
   - Use “we” only when the answer reflects internal coordination.
   - The support bot does not post its own answer.

6. **If Danny directly asks the non-owner after an answer**
   - The non-owner should answer only the narrow meta-question, e.g. “I coordinated via the handoff file before Kublai’s answer” or “No, I failed to coordinate; correcting now.”
   - It must not re-answer the original substantive question unless explicitly asked.

7. **Execute and complete**
   - Owner executes or delegates.
   - Support bot reviews/validates internally when useful.
   - Post one concise completion/failure/blocker update:
     - `Done — Hermes executed X; Kublai verified/tracked Y; result: Z.`
   - If no user-visible result is needed, stay quiet.

## What not to do

- Do not expose raw credentials, secrets, tokens, passwords, API keys, bot tokens, connection strings, or pairing codes in the raw internal-comms mirror.
- Do not have both bots answer the same substantive question.
- Do not rely on Telegram bot messages for bot-to-bot state.
- Do not send “no update” messages.
- Do not expose routine internal coordination unless Danny asks.
- Do not treat direct mention as permission to duplicate a substantive answer when a coordinated answer already exists.

## When to surface internal coordination

Surface only:

- owner/support decision for meaningful work
- blockers
- material disagreement
- completion/failure
- requested audit trail

## Human-facing language examples

- “I’ll coordinate with Hermes internally and answer with our combined view.”
- “Hermes owns execution; I’ll track status and report back here.”
- “Done — Hermes verified the path; I updated the protocol. No further action needed.”
- “Blocked — Hermes needs X before execution can continue.”
