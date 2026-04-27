# Unified Telegram Chat Protocol

Goal: Danny should experience a coherent group conversation even though Hermes and Kublai coordinate through an internal handoff system.

## Final decision

Use an **internal-first, coordinated-answers** model.

Danny designated a separate Telegram group `Kurultai Internal Coms` as the raw internal-comms mirror. Bot-to-bot state still lives in the internal handoff files, but coordination that affects Danny should be visible in `telegram:Kurultai Internal Coms` / chat id `-5161727622` with credential-looking values redacted.

- Internal handoffs are the bot-to-bot coordination layer.
- Main Kurultai chat (`telegram:-5287556083`) is human-facing: no raw handoff spam there.
- `Kurultai Internal Coms` (`telegram:-5161727622`) is the raw coordination visibility mirror.
- For any non-trivial, shared, tool-using, state-changing, or both-bots-relevant request, Hermes and Kublai coordinate internally before answering.
- Danny may receive individual answers from both Hermes and Kublai **after** coordination.
- The coordination must be visible in Kurultai Internal Coms before or alongside the answers.
- Individual answers should be clearly attributable and should add distinct perspective; avoid duplicated text or parallel uncoordinated replies.
- Raw handoffs are mirrored to `Kurultai Internal Coms`; do not mirror credentials or secrets.

## Default flow

1. **Receive request**
   - If trivial and addressed to one bot only: that bot may answer normally.
   - If the request is non-trivial, asks both bots, affects shared state, uses tools, changes files/config/cron/tasks, involves protocol/governance, or could produce conflicting answers: append an internal pre-exec handoff first.

2. **Coordinate internally**
   - Use `handoffs.jsonl` / `append_handoff.py`.
   - State: proposed owner/lead, support bot, intended action, whether one combined answer or two individual answers are expected.
   - Set `mirror: true` when Danny should see the coordination in Kurultai Internal Coms.
   - If time-sensitive, lead may proceed after posting the handoff, but must still make the coordination visible.

3. **Choose answer mode**
   - **Single answer** when one combined answer is clearer or when one bot has all relevant context.
   - **Individual answers** when Danny asks both bots, when perspectives differ usefully, or when governance/review calls benefit from separate opinions.
   - Kublai defaults to coordination, routing, project/status, governance, and group protocol.
   - Hermes defaults to ops, execution, verification, caretaker/system observations.

4. **Set shared state**
   - Update `group_state.json` with active request, lead/owner, support bot, answer mode, intended actions, and next update condition.

5. **Respond in main Telegram chat**
   - If single-answer mode: the lead posts one combined answer.
   - If individual-answer mode: each bot may post its own concise, clearly distinct answer after coordination.
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
- Do not duplicate another bot’s substantive answer unless Danny explicitly asks for separate opinions and the second answer adds value.

## When to surface internal coordination

Surface in Kurultai Internal Coms for:

- owner/support or lead/support decision for meaningful work
- answer mode: single combined vs individual answers
- blockers
- material disagreement
- completion/failure
- requested audit trail

## Human-facing language examples

- “I’ll coordinate with Hermes internally first, then we’ll each answer separately if useful.”
- “Coordination is visible in Kurultai Internal Coms; my Kublai-specific answer is…”
- “Hermes owns execution; I’ll track status and report back here.”
- “Done — Hermes verified the path; I updated the protocol. No further action needed.”
- “Blocked — Hermes needs X before execution can continue.”
