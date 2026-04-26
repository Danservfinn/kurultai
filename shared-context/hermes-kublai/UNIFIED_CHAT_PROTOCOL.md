# Unified Telegram Chat Protocol

Goal: Danny should experience one coherent group conversation even though Hermes and Kublai coordinate through an internal handoff system.

## Final decision

Use an **internal-first, single-visible-owner** model.

- Internal handoffs are the bot-to-bot coordination layer.
- Telegram is the human-facing conversation layer.
- For non-trivial/shared work, the bots coordinate internally before action.
- Only one bot posts the main visible answer unless the second bot has genuinely new value.
- No automatic raw handoff mirrors. Summaries are posted only when useful to Danny.

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

- Do not post raw handoff logs by default.
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
