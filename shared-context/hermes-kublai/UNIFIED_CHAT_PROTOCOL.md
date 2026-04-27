# Unified Telegram Chat Protocol

Goal: Danny should experience one coherent group conversation even though Hermes and Kublai coordinate through an internal handoff system.

## Final decision

Use an **internal-first, single consolidated answer** model.

Danny designated a separate Telegram group `Kurultai Internal Coms` as the raw internal-comms/coordination mirror. Bot-to-bot state lives in the internal handoff files. Coordination that affects Danny should be visible in `telegram:Kurultai Internal Coms` / chat id `-5161727622` with credential-looking values redacted.

- Internal handoffs are the bot-to-bot coordination layer.
- Main Kurultai chat (`telegram:-5287556083`) is human-facing: no raw handoff spam there.
- `Kurultai Internal Coms` (`telegram:-5161727622`) is where Danny should see Hermes/Kublai coordination.
- For any non-trivial, shared, tool-using, state-changing, protocol, governance, or both-bots-relevant request, Hermes and Kublai coordinate internally before answering.
- The main Kurultai chat receives **one consolidated answer created from both bots' input**.
- Do not post two separate substantive answers in the main chat.
- The non-owner contributes internally and stays quiet unless correcting a material error, reporting a blocker/completion/failure, or explicitly receiving ownership transfer.
- Raw handoffs are mirrored to `Kurultai Internal Coms`; do not mirror credentials or secrets.

## Default flow

1. **Receive request**
   - If trivial and addressed to one bot only: that bot may answer normally.
   - If the request is non-trivial, asks both bots, affects shared state, uses tools, changes files/config/cron/tasks, involves protocol/governance, or could produce conflicting answers: append an internal pre-exec handoff first.

2. **Coordinate internally**
   - Use `handoffs.jsonl` / `append_handoff.py`.
   - State: proposed visible owner, support bot, intended action, and what input is needed for the consolidated answer.
   - Set `mirror: true` when Danny should see the coordination in Kurultai Internal Coms.
   - If time-sensitive, owner may proceed after posting the handoff, but must still make the coordination visible.

3. **Choose visible owner**
   - Kublai leads coordination, routing, project/status, governance, and group protocol.
   - Hermes leads ops, execution, verification, caretaker/system observations.
   - If one bot has clearly better context, that bot leads regardless of default role.

4. **Set shared state**
   - Update `group_state.json` with active request, visible owner, support bot, intended actions, and next update condition.

5. **Respond in main Telegram chat**
   - The visible owner posts one consolidated answer.
   - The answer may mention both perspectives, e.g. “Kublai/Hermes view: …”
   - The support bot does not post a separate substantive answer.
   - Answers should not repeat the raw handoff text; Internal Coms carries coordination detail.

6. **If Danny directly asks whether coordination happened**
   - Answer truthfully and narrowly.
   - If coordination failed, say so, correct immediately, and use Internal Coms before continuing.

7. **Execute and complete**
   - Owner executes or delegates.
   - Support bot reviews/validates internally when useful.
   - Report completions/failures/blockers for user-requested tasks in the main chat with task id, assigned agent, outcome, concise summary, and next action if any.
   - Routine cron/no-op jobs stay quiet.

## What not to do

- Do not expose raw credentials, secrets, tokens, passwords, API keys, bot tokens, connection strings, or pairing codes in the raw internal-comms mirror.
- Do not answer non-trivial/shared requests before coordinating.
- Do not rely on Telegram bot messages for bot-to-bot state.
- Do not send “no update” messages.
- Do not post raw handoff spam in the main Kurultai chat.
- Do not provide two separate substantive answers in the main Kurultai chat.

## When to surface internal coordination

Surface in Kurultai Internal Coms for:

- owner/support decision for meaningful work
- input requested from support bot for the consolidated answer
- blockers
- material disagreement
- completion/failure
- requested audit trail

## Human-facing language examples

- “I’ll coordinate with Hermes internally first, then provide our consolidated answer here.”
- “Coordination is visible in Kurultai Internal Coms; our consolidated answer is…”
- “Hermes owns execution; I’ll track status and report the consolidated result here.”
- “Done — Hermes verified the path; I updated the protocol. Result: Z.”
- “Blocked — Hermes needs X before execution can continue.”
