# Unified Telegram Chat Protocol

Goal: Danny should experience one coherent group conversation even though Hermes and Kublai coordinate through an internal handoff system.

## Final decision

Danny designated a separate Telegram group `Kurultai Internal Coms` as the raw internal-comms mirror. Bot-to-bot state still lives in the internal handoff files, but every new handoff line may be mirrored only to `telegram:Kurultai Internal Coms` / chat id `-5161727622` with credential-looking values redacted.

Use an **internal-first, single-visible-owner** model.

- Internal handoffs are the bot-to-bot coordination layer.
- Main Kurultai chat (`telegram:-5287556083`) is human-facing: no raw handoff logs there.
- `Kurultai Internal Coms` (`telegram:-5161727622`) is the raw handoff visibility mirror.
- For non-trivial/shared work, the bots coordinate internally before action.
- Only one bot posts the main visible answer unless the second bot has genuinely new value.
- Raw handoffs are mirrored to `Kurultai Internal Coms`; do not mirror credentials or secrets.

## Default flow

1. **Receive request**
   - If trivial/direct chat: answer normally.
   - If non-trivial, shared, tool-using, or state-changing: create an internal pre-exec handoff first.

2. **Choose visible owner**
   - Kublai leads coordination, project/status/routing, and group protocol.
   - Hermes leads operational execution, verification, and system observations.
   - If one bot has clearly better context, that bot leads regardless of default role.

3. **Set shared state**
   - Update `group_state.json` with active request, visible owner, support bot, intended actions, and next update condition.

4. **Respond in Telegram**
   - The visible owner posts one concise response.
   - Use “we” only when the response reflects internal coordination.
   - The support bot stays quiet unless asked, correcting an error, or adding distinct value.

5. **Execute**
   - Owner executes or delegates.
   - Support bot reviews/validates internally when useful.

6. **Complete**
   - Post one concise completion/failure/blocker update:
     - `Done — Hermes executed X; Kublai verified/tracked Y; result: Z.`
   - If no user-visible result is needed, stay quiet.

## What not to do

- Do not expose raw credentials, secrets, tokens, passwords, API keys, bot tokens, connection strings, or pairing codes in the raw internal-comms mirror.
- Do not have both bots answer the same thing.
- Do not rely on Telegram bot messages for bot-to-bot state.
- Do not send “no update” messages.
- Do not expose routine internal coordination unless Danny asks.

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
