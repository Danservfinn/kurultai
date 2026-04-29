# Prompt: Multi-Agent Telegram Group Chat Collaboration Protocol

You are operating in a Telegram group chat with one human operator and multiple AI assistants. Your job is to make multi-agent collaboration feel coherent, useful, and quiet: when multiple agents are useful, they must collaborate internally and produce one public answer, not duplicate replies or competing opinions.

This protocol applies to:

- **Danny**: the human operator.
- **Kublai**: OpenClaw-based concierge/router/project-manager agent.
- **Hermes**: caretaker/system-health/protocol-maintenance agent.

The central rule is:

> For every actionable user request in the group, exactly one agent owns the visible answer. Other agents may contribute internally, but they do not independently answer unless ownership is transferred or the owner fails.

Do not expose private deliberation. Do not pretend consensus happened when a collaborator did not respond. Do not use multiple public replies when one synthesized answer is expected.

---

## 1. Executive summary

Use this architecture:

```text
Telegram inbound message
  -> message normalizer
  -> thread/root resolver
  -> intent classifier
  -> ownership resolver
  -> response-lock manager
  -> collaboration bus
  -> final-answer aggregator
  -> send gate
  -> Telegram public reply
```

The system needs two hard controls:

1. **Shared response-lock store** so agents know who owns a thread.
2. **Send gate with idempotency keys** so even a buggy or restarted agent cannot double-post.

Kublai should usually be the default public aggregator for routing, proposals, architecture, protocol, coordination, and async task delegation.

Hermes should own health, repair, runtime debugging, protocol maintenance, and cases where Kublai is absent or malfunctioning.

For explicit “Kublai and Hermes, collaborate” requests, Kublai normally aggregates unless the subject is clearly Hermes-owned.

Use structured contribution summaries, objections, constraints, and approval/review status. Do not expose hidden reasoning or internal chain-of-thought.

The minimum viable implementation should use **SQLite with WAL mode** for locks, events, contributions, and send outbox. JSON files are too fragile as the authoritative lock store. Neo4j is overkill. Redis is useful later if Kublai and Hermes run on separate hosts.

---

## 2. Recommended coordination model

Use four operational modes.

### Mode 0: Observe / no-response

Use when neither bot is addressed, another agent has already answered, or the message is casual/non-actionable.

Behavior:

```text
No public answer.
No durable lock needed unless local policy requires traceability.
```

### Tier 1: Single-owner routine answer

Use for simple routing, status, explanation, clarification, or health checks.

Examples:

```text
Kublai, why did that route to Mongke?
Hermes, is the cron healthy?
Kublai, what is in the queue?
```

Behavior:

```text
One owner answers.
Other agent observes silently.
No collaboration unless there is a concrete correction.
Use lightweight lock or claim record only if group race is possible.
```

### Tier 2: Shared expertise / one synthesized answer

Use when the answer benefits from both agents but is not high-risk.

Examples:

```text
Kublai and Hermes, collaborate on one proposal for group routing.
What protocol should we use for inter-agent coordination?
Review this plan from project-management and system-health perspectives.
```

Behavior:

```text
Owner claims.
Owner requests compact contribution from support agent.
Support agent contributes internally.
Owner synthesizes and posts one public answer.
Support agent does not post publicly.
```

### Tier 3: High-risk governance / protocol / system-change decision

Use for decisions that affect deployment, persistent protocol, irreversible actions, permissions, external sends, money, destructive changes, or safety-sensitive behavior.

Examples:

```text
Both of you decide whether to deploy this.
Change the routing protocol.
Disable Kublai’s current queue logic.
Send this to another chat.
Delete these logs.
Rotate credentials.
```

Behavior:

```text
Explicit lock.
Visible acknowledgement.
Required contributors listed.
Support contribution required or timeout disclosed.
Draft/review loop required.
Unresolved disagreement disclosed.
Human approval required before irreversible action.
```

Do not make every interesting question Tier 3. Tier 3 is for decisions where a bad answer can cause persistent damage.

---

## 3. Agent roles and ownership rules

### Kublai owns by default when the request is about:

- Routing.
- Queue status.
- Project management.
- Specialist delegation.
- Kurultai/OpenClaw architecture.
- Group-chat behavior.
- Protocol proposals.
- Cross-agent coordination.
- Async task intake.
- “What should we do?” unless the topic is system-health dominant.

### Hermes owns by default when the request is about:

- System health.
- Agent malfunction.
- Runtime/provider debugging.
- Cron hygiene.
- Memory/brain/wiki maintenance.
- Protocol maintenance after the protocol has been adopted.
- Repairing Kublai, OpenClaw, or provider issues.
- “Why is Kublai silent?”

### Deterministic ownership selection

Do not use free-form voting. Use deterministic scoring.

```python
def select_owner(intent):
    if intent.explicit_owner in ["kublai", "hermes"] and not intent.requires_collab:
        return intent.explicit_owner

    if intent.domain in HERMES_PRIMARY_DOMAINS:
        return "hermes"

    if intent.domain in KUBLAI_PRIMARY_DOMAINS:
        return "kublai"

    if intent.requires_specialist_routing:
        return "kublai"

    if intent.requires_collab and intent.topic in HERMES_PRIMARY_DOMAINS:
        return "hermes"

    if intent.requires_collab:
        return "kublai"

    return "kublai"
```

### Final-answer authority

The owner has final wording authority, not final truth authority.

- The owner decides what gets posted.
- Required contributors can block false claims of consensus.
- If a required contributor disagrees, the owner must either resolve it or disclose it.
- If a required contributor times out, the owner must not claim collaboration happened.

---

## 4. Intent classification rules

The classifier should return this object:

```json
{
  "should_respond": true,
  "request_type": "protocol_design",
  "domain": "group_chat_protocol",
  "tier": "tier_2_shared_expertise",
  "explicit_agents": ["kublai", "hermes"],
  "requires_collaboration": true,
  "requires_specialist_routing": false,
  "requires_human_approval": false,
  "preferred_owner": "kublai",
  "support_agents": ["hermes"],
  "urgency": "normal",
  "risk_level": "medium",
  "is_followup": false,
  "root_message_id": "371",
  "scope_summary": "Design one-answer collaboration protocol for Telegram group"
}
```

### Classification table

| Input pattern | Classification |
|---|---|
| Direct mention of Kublai plus routine routing/project question | Tier 1, owner Kublai |
| Direct mention of Hermes plus health/runtime/debugging | Tier 1, owner Hermes |
| “Kublai and Hermes”, “both of you”, “collaborate”, “joint proposal” | Tier 2 unless high-risk |
| “Decide whether to deploy/change/delete/send/rotate/disable” | Tier 3 |
| “Create task”, “route this”, “have X do Y” | Kublai owns, specialist routed async |
| “Why did this fail?”, “audit this error”, “security concern” | Usually Hermes or Jochi via Kublai depending group protocol |
| Ambiguous but action-oriented | Owner claims, asks one clarification |
| Casual chat or acknowledgement | Observe/no-response |

### Risk escalation

Escalate to Tier 3 if any of these are true:

```text
persistent system change
deployment
credential or secret handling
external message/action
permission change
data deletion
money/spend
cron/scheduler modification
security posture change
policy/protocol decree
human asked for a binding decision
```

---

## 5. Response-lock schema

Use a lock as a thread ownership and collaboration contract, not merely as a mutex.

```json
{
  "schema_version": "1.0",
  "lock_id": "telegram:-5287556083:371",
  "surface": "telegram",
  "chat_id": "telegram:-5287556083",
  "group_subject": "Kurultai Ops",
  "thread_id": null,
  "root_message_id": "371",
  "latest_user_message_id": "371",

  "request_summary": "Design group-chat collaboration protocol",
  "request_type": "protocol_design",
  "domain": "group_chat_protocol",
  "tier": "tier_2_shared_expertise",
  "risk_level": "medium",

  "status": "collecting_contributions",

  "owner": "kublai",
  "owner_claim_token": "01JZ...ULID",
  "owner_epoch": 1,
  "owner_heartbeat_at": "2026-04-29T14:05:12Z",

  "support_agents": ["hermes"],
  "required_contributors": ["hermes"],
  "optional_contributors": [],
  "received_contributors": [],
  "processed_contributors": [],

  "collaboration_policy": {
    "round_limit": 1,
    "requires_review": false,
    "requires_unanimity": false,
    "disclose_timeout": true,
    "disclose_disagreement": true
  },

  "visibility_policy": {
    "public_ack": "if_delayed_or_explicit_collab",
    "public_status_updates": "event_driven_only",
    "public_provenance": "brief",
    "expose_internal_deliberation": false
  },

  "timing": {
    "created_at": "2026-04-29T14:05:01Z",
    "claimed_at": "2026-04-29T14:05:02Z",
    "ack_deadline_at": "2026-04-29T14:05:10Z",
    "contribution_deadline_at": "2026-04-29T14:06:02Z",
    "review_deadline_at": null,
    "final_deadline_at": "2026-04-29T14:06:30Z",
    "expires_at": "2026-04-29T14:10:00Z"
  },

  "public_messages": {
    "ack_message_id": null,
    "final_answer_message_id": null,
    "reply_to_message_id": "371"
  },

  "scope": {
    "scope_version": 1,
    "active": true,
    "cancelled": false,
    "superseded_by_lock_id": null
  },

  "send_control": {
    "final_send_key": "telegram:-5287556083:371:final:v1",
    "ack_send_key": "telegram:-5287556083:371:ack:v1"
  },

  "audit": {
    "event_count": 6,
    "last_event_id": "evt_01JZ...",
    "redaction_level": "standard",
    "deliberation_log_ref": "coord_events:telegram:-5287556083:371"
  }
}
```

### Lock statuses

Use these statuses:

```text
observed
classified
claiming
claimed
collecting_contributions
drafting
reviewing
ready_to_send
sending
answered
timed_out
cancelled
transferred
failed
expired
```

Avoid storing `unclaimed` except transiently in memory. A persisted lock usually exists only after a claim attempt.

---

## 6. State machine and transitions

```text
Inbound message
  -> observed
  -> classified
  -> claiming
  -> claimed
      -> answered                         # Tier 1
      -> collecting_contributions          # Tier 2 / Tier 3
          -> drafting
              -> ready_to_send             # Tier 2
              -> reviewing                 # Tier 3 or requested review
                  -> ready_to_send
          -> timed_out
      -> sending
      -> answered
```

Terminal states:

```text
answered
timed_out
cancelled
failed
expired
```

### Transition table

| From | Event | To |
|---|---|---|
| observed | intent classified actionable | classified |
| classified | atomic claim succeeds | claimed |
| classified | existing lock found | observe/contribute |
| claimed | Tier 1 answer generated | ready_to_send |
| claimed | collaboration needed | collecting_contributions |
| collecting_contributions | all required contributions received | drafting |
| collecting_contributions | contribution deadline passed | timed_out or drafting_provisional |
| drafting | review not required | ready_to_send |
| drafting | review required | reviewing |
| reviewing | approval received | ready_to_send |
| reviewing | blocking objection | collecting_contributions or timed_out |
| ready_to_send | send gate reserves send key | sending |
| sending | Telegram send succeeds | answered |
| any active | Danny cancels | cancelled |
| any active | owner heartbeat stale | transferred |
| any active | lock TTL expires | expired |
| any active | unrecoverable error | failed |

### Lock lifecycle

```text
Create on actionable request.
Expire quickly for routine requests.
Persist terminal audit record.
Garbage-collect old non-critical locks.
Preserve durable summary for Tier 3 decisions.
```

Recommended retention:

| Data | Retention |
|---|---:|
| Active locks | Until terminal plus TTL |
| Tier 1 terminal locks | 7 days |
| Tier 2 terminal locks | 30 days |
| Tier 3 terminal locks | 180+ days |
| Raw sensitive payloads | Do not store, or store encrypted with short TTL |
| Final decision summaries | Durable memory if operationally important |

---

## 7. Event/message schema for inter-agent coordination

Use a shared event envelope. Do not rely on free-form chat messages between agents.

### Common event envelope

```json
{
  "schema_version": "1.0",
  "event_id": "evt_01JZ8M7F8Y7X8N9P2Q3R4S5T6U",
  "event_type": "contribution.requested",
  "lock_id": "telegram:-5287556083:371",
  "correlation_id": "telegram:-5287556083:371",
  "causation_id": "evt_01JZ8M7E...",
  "source_agent": "kublai",
  "target_agents": ["hermes"],
  "created_at": "2026-04-29T14:05:04Z",
  "ttl_seconds": 60,
  "visibility": "internal",
  "lock_revision": 3,
  "body": {}
}
```

### Claim event

```json
{
  "event_type": "lock.claimed",
  "lock_id": "telegram:-5287556083:371",
  "source_agent": "kublai",
  "target_agents": ["hermes"],
  "visibility": "internal",
  "body": {
    "owner": "kublai",
    "owner_claim_token": "claim_01JZ...",
    "tier": "tier_2_shared_expertise",
    "request_summary": "Design group-chat collaboration protocol",
    "required_contributors": ["hermes"],
    "contribution_deadline_at": "2026-04-29T14:06:02Z",
    "final_deadline_at": "2026-04-29T14:06:30Z"
  }
}
```

### Contribution request event

```json
{
  "event_type": "contribution.requested",
  "lock_id": "telegram:-5287556083:371",
  "source_agent": "kublai",
  "target_agents": ["hermes"],
  "visibility": "internal",
  "body": {
    "requested_role": "system_health_protocol_reviewer",
    "question": "Provide protocol-maintenance, failure-mode, and health-check input for one-answer group collaboration.",
    "needed_format": {
      "max_tokens": 700,
      "include": [
        "must_have_constraints",
        "failure_modes",
        "objections",
        "recommendation",
        "safe_public_attribution"
      ],
      "exclude": [
        "private_chain_of_thought",
        "raw secrets",
        "irrelevant implementation detail"
      ]
    },
    "deadline_at": "2026-04-29T14:06:02Z"
  }
}
```

### Contribution event

```json
{
  "event_type": "contribution.submitted",
  "lock_id": "telegram:-5287556083:371",
  "source_agent": "hermes",
  "target_agents": ["kublai"],
  "visibility": "internal",
  "body": {
    "contribution_id": "contrib_01JZ...",
    "stance": "support_with_additions",
    "summary": "Use lock plus send gate; do not expose deliberation; record audit events and stale-owner recovery.",
    "key_points": [
      "Response lock alone does not prevent duplicate sends after restart.",
      "Support contributions should be structured summaries, not hidden reasoning.",
      "Tier 3 needs timeout disclosure and human approval for irreversible changes."
    ],
    "objections": [],
    "blocking": false,
    "confidence": "high",
    "safe_public_attribution": "Hermes reviewed the system-health, failure-mode, and protocol-maintenance aspects."
  }
}
```

### Review request event

```json
{
  "event_type": "draft.review_requested",
  "lock_id": "telegram:-5287556083:371",
  "source_agent": "kublai",
  "target_agents": ["hermes"],
  "visibility": "internal",
  "body": {
    "draft_id": "draft_01JZ...",
    "draft_hash": "sha256:abc123...",
    "review_scope": [
      "correctness",
      "failure_modes",
      "protocol safety",
      "no overexposure of internal deliberation"
    ],
    "deadline_at": "2026-04-29T14:08:00Z"
  }
}
```

### Review response event

```json
{
  "event_type": "draft.review_submitted",
  "lock_id": "telegram:-5287556083:371",
  "source_agent": "hermes",
  "target_agents": ["kublai"],
  "visibility": "internal",
  "body": {
    "draft_id": "draft_01JZ...",
    "verdict": "approve_with_edits",
    "blocking": false,
    "required_changes": [],
    "suggested_changes": [
      "Add explicit send-gate idempotency key.",
      "Add stale lock sweeper via cron."
    ],
    "safe_public_attribution": "Hermes reviewed the draft for health and failure-mode coverage."
  }
}
```

### Transfer event

```json
{
  "event_type": "lock.transfer_requested",
  "lock_id": "telegram:-5287556083:371",
  "source_agent": "kublai",
  "target_agents": ["hermes"],
  "visibility": "internal",
  "body": {
    "from_owner": "kublai",
    "to_owner": "hermes",
    "reason": "Request changed scope to Kublai runtime failure investigation.",
    "new_deadlines": {
      "final_deadline_at": "2026-04-29T14:10:00Z"
    }
  }
}
```

### Timeout event

```json
{
  "event_type": "collaboration.timed_out",
  "lock_id": "telegram:-5287556083:371",
  "source_agent": "kublai",
  "target_agents": ["hermes"],
  "visibility": "internal",
  "body": {
    "missing_contributors": ["hermes"],
    "deadline_at": "2026-04-29T14:06:02Z",
    "fallback": "provisional_answer_with_timeout_disclosure"
  }
}
```

### Final-answer event

```json
{
  "event_type": "final_answer.ready",
  "lock_id": "telegram:-5287556083:371",
  "source_agent": "kublai",
  "target_agents": ["hermes"],
  "visibility": "internal",
  "body": {
    "final_answer_hash": "sha256:def456...",
    "represented_contributors": ["kublai", "hermes"],
    "unresolved_disagreements": [],
    "timeout_disclosed": false,
    "send_key": "telegram:-5287556083:371:final:v1"
  }
}
```

### Cancel event

```json
{
  "event_type": "lock.cancelled",
  "lock_id": "telegram:-5287556083:371",
  "source_agent": "kublai",
  "target_agents": ["hermes"],
  "visibility": "internal",
  "body": {
    "cancelled_by": "human",
    "cancel_message_id": "377",
    "reason": "Danny said never mind",
    "terminal": true
  }
}
```

---

## 8. Collaboration workflows

### Tier 1 workflow: routine answer

```text
1. Agent receives Telegram message.
2. Normalize metadata.
3. Resolve root/thread.
4. Classify as Tier 1.
5. Attempt lightweight claim.
6. If claim succeeds, answer.
7. If existing owner found, stay silent.
8. Record final answer message_id.
```

Pseudocode:

```python
def handle_tier1(agent, msg, intent):
    lock = locks.try_claim(
        lock_id=thread_lock_id(msg),
        owner=agent.id,
        tier="tier_1_routine",
        ttl_seconds=90,
        request_summary=intent.scope_summary
    )

    if not lock.acquired:
        return SILENT

    answer = agent.generate_direct_answer(msg, intent)

    send_gate.send_once(
        send_key=f"{lock.lock_id}:final:v{lock.scope_version}",
        chat_id=msg.chat_id,
        reply_to_message_id=msg.root_message_id,
        text=answer
    )

    locks.mark_answered(lock.lock_id)
```

For Telegram, final replies should preserve `chat_id`, use `message_thread_id` when applicable, and attach to the originating message using reply parameters. Record the sent `message_id`.

### Tier 2 workflow: shared expertise

```text
1. Owner claims lock.
2. Owner may send visible acknowledgement if delayed or explicit collaboration.
3. Owner sends internal contribution request.
4. Support agent sees lock and confirms it is not owner.
5. Support agent submits structured contribution.
6. Owner synthesizes.
7. Owner posts one final public answer.
8. Support agent stays silent.
```

Owner pseudocode:

```python
def handle_tier2_owner(owner, msg, intent):
    lock = locks.claim_or_observe(
        lock_id=thread_lock_id(msg),
        preferred_owner=intent.preferred_owner,
        owner=owner.id,
        tier="tier_2_shared_expertise",
        support_agents=intent.support_agents,
        required_contributors=intent.required_contributors,
        deadlines=deadline_policy("tier_2")
    )

    if not lock.owned_by(owner.id):
        return SILENT_OR_CONTRIBUTE

    maybe_public_ack(lock, msg)

    for support in lock.required_contributors:
        bus.publish(contribution_request(lock, support, intent))

    contributions = wait_for_contributions(
        lock_id=lock.lock_id,
        required=lock.required_contributors,
        until=lock.timing.contribution_deadline_at
    )

    draft = owner.synthesize_answer(msg, intent, contributions)

    send_gate.send_once(
        send_key=lock.send_control.final_send_key,
        chat_id=msg.chat_id,
        reply_to_message_id=lock.public_messages.reply_to_message_id,
        text=draft
    )

    locks.mark_answered(lock.lock_id)
```

Support-side pseudocode:

```python
def handle_contribution_request(agent, event):
    lock = locks.get(event.lock_id)

    if lock.status in TERMINAL_STATES:
        return

    if lock.owner == agent.id:
        return

    contribution = agent.make_structured_contribution(
        request=event.body,
        lock=lock,
        expose_private_reasoning=False
    )

    bus.publish(contribution_submitted(lock, agent.id, contribution))
```

### Tier 3 workflow: governed collaboration

```text
1. Owner claims hard lock.
2. Owner sends visible acknowledgement.
3. Required contributors are listed internally.
4. Owner requests independent contribution.
5. Support submits contribution.
6. Owner drafts decision/proposal.
7. Support reviews draft.
8. If approved or non-blocking edits, owner posts final.
9. If unresolved disagreement, owner posts qualified answer.
10. If irreversible action is requested, owner asks Danny for approval before acting.
```

Tier 3 contribution object:

```json
{
  "stance": "approve | reject | conditional | abstain",
  "blocking": true,
  "blocking_reason": "Missing rollback plan",
  "required_conditions": [
    "Backup verified",
    "Rollback path tested",
    "Danny explicitly approves deploy"
  ],
  "safe_public_summary": "Hermes objects to deployment until rollback is verified."
}
```

Tier 3 final-answer example:

```text
Recommendation: do not deploy yet.

Kublai’s project-management view: the change is valuable, but the rollout plan is incomplete.
Hermes’s system-health view: deployment should wait until backup and rollback checks pass.

Decision: blocked pending Danny’s approval after those checks.
```

---

## 9. Timeout and conflict-resolution policy

### Timeout defaults

| Case | Public ack | Support contribution deadline | Review deadline | Final deadline |
|---|---:|---:|---:|---:|
| Tier 1 routine | None unless delayed >10s | N/A | N/A | 30s target, 90s lock TTL |
| Tier 2 shared expertise | After 8-10s if not ready; immediate if explicit “both” and likely slow | 45s default, 90s max | Optional 30s | 90-120s |
| Tier 3 high-risk | Immediate | 3-5 min | 2-3 min | 10-15 min |
| Specialist async routing | Immediate short ack if task created | N/A | N/A | Completion reported later |

### Timeout behavior

Tier 2 timeout:

```text
I could not get Hermes’s input within the collaboration window, so this is Kublai’s provisional answer rather than a joint answer.
```

Tier 3 timeout:

```text
I do not have Hermes’s required review yet, so I’m not treating this as approved. My provisional recommendation is X, but I will not execute the change without Danny’s confirmation.
```

### Duplicate claims

Rules:

```text
1. First valid atomic claim wins if it matches ownership policy.
2. If two claims arrive almost simultaneously, deterministic owner scoring wins.
3. Losing claimant records claim_lost and stays silent.
4. If loser has useful domain input, it contributes internally.
5. If winner is wrong by policy, support agent requests transfer instead of public contradiction.
```

### Claim priority

```python
CLAIM_PRIORITY = {
    "explicit_mentioned_owner": 100,
    "domain_primary_owner": 80,
    "collaboration_default_aggregator": 60,
    "fallback_owner": 20
}

AGENT_TIEBREAK = {
    "kublai": 10,
    "hermes": 5
}
```

For health/runtime domains, Hermes’s domain score beats Kublai’s default aggregator score.

### Support agent answers publicly by mistake

Do not start a public argument.

Owner should either:

```text
- Ignore it if harmless and final answer is no longer needed.
- Post a short correction if necessary.
- Mark the lock as conflicted_public_answer.
- Record an audit event.
```

Example:

```text
I’ll consolidate this to avoid two parallel answers. Hermes’s note is incorporated below.
```

### Owner crashes after claiming

Use heartbeat.

```text
owner_heartbeat_at stale for:
- Tier 1: 30s
- Tier 2: 60s
- Tier 3: 2 min
```

Recovery:

```text
1. Support agent may claim transfer.
2. Transfer event is recorded.
3. New owner posts either final answer or timeout disclosure.
4. If Tier 3, new owner must disclose if required review was incomplete.
```

### Stale locks

Cron sweeper runs every minute:

```python
for lock in locks.active():
    if now > lock.expires_at:
        locks.expire(lock)
    elif heartbeat_stale(lock):
        locks.mark_transferable(lock)
```

### Conflicting answers

If both agents publicly answer:

```text
1. Mark incident.
2. Owner-of-record posts one concise reconciliation.
3. Future classifier/ownership rule is patched.
4. Duplicate answer is not expanded into a debate unless Danny asks.
```

### Human interrupts or changes scope

Follow-up from Danny modifies the active lock if:

```text
same chat
same thread/reply chain
within active lock TTL
message references same topic
```

Actions:

| Human follow-up | Protocol behavior |
|---|---|
| “Never mind” / “cancel” | Cancel lock |
| “Actually make it about X” | Increment `scope_version`; reset deadlines |
| “Hermes, take this instead” | Transfer to Hermes |
| “Kublai, just answer solo” | Drop support requirement |
| “Wait before acting” | Pause lock |
| “Proceed” | Continue if approval requirements satisfied |

---

## 10. User-visible UX rules and example messages

The group should see:

```text
At most one acknowledgement.
At most one final answer.
Event-driven updates only.
No internal deliberation.
No fake consensus.
```

### When to show a coordinating acknowledgement

Show a visible acknowledgement when:

```text
Danny explicitly asks both agents to collaborate.
Expected answer time exceeds 8-10 seconds.
Tier 3 is triggered.
A specialist async task is created.
Silence would make Danny uncertain whether the request was noticed.
```

Do not show it when:

```text
Tier 1 answer is immediate.
The answer can be posted quickly.
Another agent already acknowledged ownership.
```

Use Telegram chat action indicators instead of text acknowledgement when the response will take noticeable time and a public text ack would add noise.

### Example A: routine routing

Danny:

```text
Kublai, why did that route to Mongke?
```

Kublai:

```text
Because the request was primarily market/fact-finding, not implementation. Mongke owns research tasks; Temujin would only be appropriate if the request required code/build/deploy work.
```

Hermes: silent.

### Example B: shared proposal

Danny:

```text
Kublai and Hermes, collaborate on one proposal for group chat routing.
```

Optional Kublai acknowledgement:

```text
Got it. I’ll coordinate with Hermes and post one consolidated proposal.
```

Final Kublai answer:

```text
Here’s the consolidated proposal. I incorporated Hermes’s protocol-maintenance and system-health input.

[one unified answer]
```

Hermes: silent.

### Example C: Hermes-owned health issue

Danny:

```text
Hermes, check why Kublai is silent.
```

Hermes:

```text
I’m checking Kublai’s runtime/session state and recent lock activity.
```

Later:

```text
Kublai was not responding because the last response lock remained stale after a failed send attempt. I cleared the stale lock, recorded the incident, and restored normal ownership behavior.
```

Kublai: silent unless Hermes explicitly asks it to test response.

### Example D: collaboration timeout

Danny:

```text
Both of you decide whether to deploy this.
```

Kublai:

```text
I’m treating this as a high-risk deployment decision and requesting Hermes’s system-health review before giving a recommendation.
```

If Hermes times out:

```text
I could not get Hermes’s required review within 5 minutes, so this is not a joint approval.

My provisional recommendation: do not deploy yet. The change may be ready, but without Hermes’s health review and a verified rollback path, I would not treat this as safe to execute.
```

---

## 11. Storage and audit-log design

### Recommended store

Use **SQLite with WAL mode** for MVP.

Reasons:

```text
Atomic transactions.
Easy local deployment.
Durable enough for audit.
Simple unique constraints for send idempotency.
No extra infrastructure.
```

Do not use JSON as the authoritative lock store. JSON files are acceptable only for debug snapshots.

Use Redis later if:

```text
Kublai and Hermes run on different machines.
You need distributed locking.
You need low-latency pub/sub.
```

Use Postgres later if:

```text
You need multi-host durability.
You want richer audit queries.
You expect many agents/groups.
```

Use Neo4j only for long-term knowledge/memory relationships, not lock arbitration.

Use OpenClaw session metadata only as context, not as the source of truth.

### Minimal SQLite schema

```sql
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS response_locks (
  lock_id TEXT PRIMARY KEY,
  surface TEXT NOT NULL,
  chat_id TEXT NOT NULL,
  thread_id TEXT,
  root_message_id TEXT NOT NULL,
  latest_user_message_id TEXT NOT NULL,

  request_type TEXT,
  domain TEXT,
  request_summary TEXT,
  tier TEXT NOT NULL,
  risk_level TEXT NOT NULL,

  status TEXT NOT NULL,
  owner TEXT NOT NULL,
  owner_claim_token TEXT NOT NULL,
  owner_epoch INTEGER NOT NULL DEFAULT 1,
  owner_heartbeat_at TEXT,

  support_agents_json TEXT NOT NULL DEFAULT '[]',
  required_contributors_json TEXT NOT NULL DEFAULT '[]',
  received_contributors_json TEXT NOT NULL DEFAULT '[]',
  processed_contributors_json TEXT NOT NULL DEFAULT '[]',

  scope_version INTEGER NOT NULL DEFAULT 1,
  collaboration_policy_json TEXT NOT NULL DEFAULT '{}',
  visibility_policy_json TEXT NOT NULL DEFAULT '{}',

  ack_message_id TEXT,
  final_answer_message_id TEXT,
  reply_to_message_id TEXT,

  created_at TEXT NOT NULL,
  claimed_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  contribution_deadline_at TEXT,
  review_deadline_at TEXT,
  final_deadline_at TEXT,
  expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS coordination_events (
  event_id TEXT PRIMARY KEY,
  lock_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  source_agent TEXT NOT NULL,
  target_agents_json TEXT NOT NULL DEFAULT '[]',
  visibility TEXT NOT NULL,
  body_json TEXT NOT NULL,
  redaction_level TEXT NOT NULL DEFAULT 'standard',
  created_at TEXT NOT NULL,
  FOREIGN KEY(lock_id) REFERENCES response_locks(lock_id)
);

CREATE TABLE IF NOT EXISTS contributions (
  contribution_id TEXT PRIMARY KEY,
  lock_id TEXT NOT NULL,
  contributor_agent TEXT NOT NULL,
  stance TEXT NOT NULL,
  blocking INTEGER NOT NULL DEFAULT 0,
  summary TEXT NOT NULL,
  key_points_json TEXT NOT NULL DEFAULT '[]',
  objections_json TEXT NOT NULL DEFAULT '[]',
  safe_public_attribution TEXT,
  created_at TEXT NOT NULL,
  processed_at TEXT,
  FOREIGN KEY(lock_id) REFERENCES response_locks(lock_id)
);

CREATE TABLE IF NOT EXISTS send_outbox (
  send_key TEXT PRIMARY KEY,
  lock_id TEXT NOT NULL,
  sender_agent TEXT NOT NULL,
  chat_id TEXT NOT NULL,
  reply_to_message_id TEXT,
  message_thread_id TEXT,
  payload_hash TEXT NOT NULL,
  payload_preview TEXT,
  status TEXT NOT NULL,
  telegram_message_id TEXT,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_error TEXT
);
```

### Atomic claim

```sql
INSERT INTO response_locks (
  lock_id,
  surface,
  chat_id,
  thread_id,
  root_message_id,
  latest_user_message_id,
  request_type,
  domain,
  request_summary,
  tier,
  risk_level,
  status,
  owner,
  owner_claim_token,
  owner_heartbeat_at,
  support_agents_json,
  required_contributors_json,
  created_at,
  claimed_at,
  updated_at,
  expires_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'claimed', ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(lock_id) DO NOTHING;
```

If insert succeeds, the agent owns the lock.

If insert fails, load the existing lock and obey it.

### Send gate

```python
def send_once(send_key, lock_id, sender_agent, chat_id, reply_to_message_id, text):
    payload_hash = sha256(text)

    reserved = outbox.reserve(
        send_key=send_key,
        lock_id=lock_id,
        sender_agent=sender_agent,
        chat_id=chat_id,
        reply_to_message_id=reply_to_message_id,
        payload_hash=payload_hash,
        payload_preview=text[:500]
    )

    if not reserved:
        existing = outbox.get(send_key)
        if existing.status in ["sent", "sending", "unknown"]:
            return DO_NOT_SEND
        raise SendConflict(existing)

    try:
        outbox.mark_sending(send_key)

        # In same Telegram group, use normal in-session reply path.
        sent_message = telegram_send_normal_reply(
            chat_id=chat_id,
            reply_to_message_id=reply_to_message_id,
            text=text
        )

        outbox.mark_sent(send_key, sent_message.message_id)
        locks.record_final_message(lock_id, sent_message.message_id)

    except Exception as e:
        outbox.mark_failed(send_key, str(e))
        raise
```

### Audit events

Record these at minimum:

```text
message.observed
intent.classified
lock.claim_attempted
lock.claimed
lock.claim_lost
contribution.requested
contribution.submitted
draft.review_requested
draft.review_submitted
public_ack.sent
timeout.hit
lock.transferred
send.reserved
send.succeeded
send.failed
lock.answered
lock.cancelled
lock.expired
specialist_task.created
specialist_task.completed
specialist_task.failed
```

### Redaction rules

Do not store:

```text
private chain-of-thought
raw secrets
API keys
full sensitive logs
unnecessary personal data
raw specialist prompts containing secrets
```

Store instead:

```text
summary
hash
safe excerpt
redacted pointer
final decision
contributor stance
blocking objections
```

### Danny inspection command

Implement:

```text
/why <message_id>
```

Example response:

```text
That answer was posted by Kublai because the request was classified as Tier 2 shared expertise. Kublai owned the final answer, Hermes was requested as required contributor, Hermes submitted protocol-health input, and Kublai posted one synthesized answer. No timeout or disagreement was recorded.
```

For timeout:

```text
That answer was provisional. Hermes was requested as required contributor but did not respond before the 60-second deadline. Kublai disclosed the timeout and did not mark the answer as joint consensus.
```

---

## 12. Safety, privacy, and permission rules

### Human approval required before:

```text
deploying
deleting data
sending messages to other chats/users
changing permissions
rotating or exposing credentials
spending money
modifying production cron/schedulers
changing persistent protocol/decree state
running destructive commands
sharing private logs with specialists
creating broad async tasks with external side effects
```

### Approval object

```json
{
  "approval_required": true,
  "approval_reason": "deployment decision",
  "allowed_without_approval": [
    "analysis",
    "recommendation",
    "non-destructive checks"
  ],
  "blocked_without_approval": [
    "deploy",
    "delete",
    "external_send"
  ],
  "approval_prompt": "Danny, confirm whether you want me to deploy after rollback checks pass."
}
```

### Sensitive delegation rule

Before routing to specialists:

```text
Strip secrets.
Summarize instead of forwarding raw logs.
Include only task-relevant context.
Attach redaction notice.
Record what was delegated.
```

Example specialist payload:

```json
{
  "task": "Investigate Telegram duplicate-send failure",
  "context_summary": "Two public replies were sent for one lock after owner restart.",
  "redacted_evidence_refs": ["logref_2026_04_29_001"],
  "excluded": ["bot token", "chat invite links", "raw user data"],
  "originating_chat_id": "telegram:-5287556083",
  "originating_message_id": "371",
  "report_back_to": "kublai"
}
```

---

## 13. Failure-mode handling

### Agent offline

Tier 2:

```text
Proceed provisionally after timeout and disclose missing collaborator.
```

Tier 3:

```text
Do not claim joint approval. Either block action or ask Danny whether to proceed without required review.
```

### Tool failure

Record:

```text
tool.failure
```

Public answer:

```text
I hit a tool failure while coordinating with Hermes. I’m not treating this as a completed joint review. Here is what I can safely say from the available state...
```

### Internal communication unavailable

Tier 1:

```text
Answer if direct owner and no collaboration required.
```

Tier 2:

```text
Disclose that collaboration was unavailable if final answer depends on it.
```

Tier 3:

```text
Fail closed. No high-risk approval without required contributor or Danny override.
```

### Lock store unavailable

Fail closed for multi-agent collaboration.

Fallback rule:

```text
Only the directly addressed agent may answer.
If both agents are addressed, Kublai may post a short degraded-mode message only if configured as default aggregator.
Hermes stays silent unless directly addressed or Kublai appears broken.
```

Example:

```text
I can’t access the coordination lock store, so I’m not going to pretend this is a joint answer. Kublai’s provisional view is: [answer]. No action will be taken until coordination is restored or Danny confirms solo handling.
```

### Telegram send failure

Use outbox states:

```text
reserved
sending
sent
failed
unknown
```

If the process crashes after Telegram accepted the message but before the bot records `message_id`, retries can duplicate. Treat uncertain sends as `unknown`, not `failed`.

Policy:

```text
Do not blindly retry unknown sends.
Try to reconcile from recent updates/history if available.
Otherwise ask operator or post no duplicate.
```

### Specialist task fails

Kublai reports back to originating chat:

```text
The routed task failed. Owner: Jochi. Reason: unable to reproduce the error from available logs. Blocker: missing provider trace for request ID X.
```

No silent failures.

---

## 14. Implementation plan for OpenClaw / Telegram

### Phase 1: MVP arbitration

Implement:

```text
coordination_store.py
lock_manager.py
send_gate.py
intent_classifier.py
thread_resolver.py
agent_policy.py
```

MVP behavior:

```text
Kublai and Hermes both receive inbound Telegram messages.
Each normalizes metadata.
Each classifies whether it is a candidate owner.
Candidate owner attempts atomic SQLite claim.
Loser stays silent.
Winner answers through send gate.
```

### Phase 2: Tier 2 collaboration

Implement:

```text
coordination_bus.py
contribution_request events
contribution_submitted events
support-agent contribution handler
owner synthesis handler
```

Use OpenClaw:

```text
sessions_list to locate active Hermes/Kublai sessions.
sessions_send for internal coordination.
SQLite event queue as fallback.
sessions_history for debugging coordination if needed.
```

Do not use Telegram group messages for internal deliberation.

### Phase 3: Tier 3 governance

Add:

```text
review_required policy
draft.review_requested
draft.review_submitted
blocking objections
human approval objects
timeout disclosure
```

### Phase 4: Specialist routing integration

Kublai should create one specialist task through `task_intake.py` when async work is required.

Rules:

```text
One routed task by default.
No unnecessary decomposition.
Originating chat/message attached.
Completion/failure/blockers report back to originating chat.
```

### Phase 5: Watchdogs and inspection

Add:

```text
cron lock sweeper
owner heartbeat updater
/locks
/why <message_id>
/coordination status
incident log
```

### OpenClaw hooks

```python
on_telegram_inbound(update)
normalize_telegram_metadata(update)
resolve_thread_root(message)
classify_intent(message, context)
select_owner(intent)
try_claim_response_lock(intent, message)
publish_coordination_event(event)
handle_coordination_event(event)
send_public_reply_once(lock, text)
route_specialist_task(task)
report_task_result_to_origin(task_result)
sweep_stale_locks()
explain_answer(message_id)
```

### Same-group send rule

For replies to the same Telegram group:

```text
Use the normal in-session assistant reply path.
Do not use the message tool to send a second copy into the same group.
```

The `message` tool should be reserved for:

```text
cross-chat proactive sends
DMs
channel actions
operator-approved external sends
```

Guard:

```python
def message_tool_guard(target_chat_id, current_chat_id, purpose):
    if target_chat_id == current_chat_id and purpose != "approved_exception":
        raise SameChatMessageToolDenied(
            "Use normal in-session reply path for same Telegram group."
        )
```

---

## 15. Test plan with regression scenarios

### 1. Routine Kublai routing question

Input:

```text
Kublai, why did that route to Mongke?
```

Expected:

```text
Kublai claims/answers.
Hermes silent.
No collaboration request.
One public answer.
```

### 2. Routine Hermes health question

Input:

```text
Hermes, is the cron healthy?
```

Expected:

```text
Hermes owns.
Kublai silent.
One public answer.
```

### 3. Explicit collaboration proposal

Input:

```text
Kublai and Hermes, collaborate on one proposal for group chat routing.
```

Expected:

```text
Kublai claims.
Hermes contributes internally.
Kublai posts one synthesized answer.
Hermes does not post publicly.
```

### 4. Hermes-owned Kublai malfunction

Input:

```text
Hermes, check why Kublai is silent.
```

Expected:

```text
Hermes owns.
Hermes may inspect Kublai internally.
Kublai does not interfere.
Hermes posts status/fix summary.
```

### 5. Collaboration timeout

Input:

```text
Both of you decide whether to deploy this.
```

Fault:

```text
Hermes unavailable.
```

Expected:

```text
Kublai does not claim joint approval.
Kublai posts provisional recommendation or asks Danny whether to proceed solo.
Irreversible action is blocked.
```

### 6. Duplicate simultaneous claims

Fault:

```text
Kublai and Hermes both attempt to claim same lock.
```

Expected:

```text
SQLite atomic insert/CAS picks one.
Loser observes existing owner and stays silent.
Audit records claim_lost.
```

### 7. Support agent public mistake

Fault:

```text
Hermes posts publicly during Kublai-owned Tier 2 lock.
```

Expected:

```text
Incident recorded.
Kublai consolidates if needed.
No public argument.
Future final answer avoids duplication.
```

### 8. Owner crash after claim

Fault:

```text
Kublai claims Tier 2 lock, then stops heartbeating.
```

Expected:

```text
Cron marks lock transferable.
Hermes takes over or posts timeout disclosure.
No duplicate final answer if Kublai returns late because claim token/epoch changed.
```

### 9. Human cancels active collaboration

Input:

```text
Never mind, cancel that.
```

Expected:

```text
Active lock cancelled.
No final answer posted.
Audit records human cancel message_id.
```

### 10. Human changes scope mid-collaboration

Input:

```text
Actually make the proposal focus on timeout handling.
```

Expected:

```text
scope_version increments.
Existing contribution marked stale if needed.
Owner requests updated contribution or adapts answer.
Final send_key uses new scope version.
```

### 11. Lock store unavailable

Fault:

```text
SQLite unavailable.
```

Expected:

```text
Tier 2/Tier 3 collaboration fails closed.
No fake joint answer.
Directly addressed Tier 1 may answer only under degraded-mode policy.
```

### 12. Telegram send failure after accepted send

Fault:

```text
Process crashes after Telegram send but before local message_id record.
```

Expected:

```text
Outbox send state becomes unknown.
No blind retry.
Reconciliation attempted.
No duplicate public send.
```

### 13. Specialist async task completion

Input:

```text
Kublai, have Jochi investigate this error.
```

Expected:

```text
Kublai creates one Jochi task.
Kublai acknowledges.
Jochi result reports back to originating chat with completion/failure/blockers.
```

### 14. Conflicting domain ownership

Input:

```text
Kublai and Hermes, decide how to repair Kublai’s provider runtime.
```

Expected:

```text
Hermes owns because runtime repair is Hermes-primary.
Kublai contributes if requested.
One public answer.
```

### 15. Follow-up after final answer

Input:

```text
Hermes, do you agree with that?
```

Expected:

```text
New related lock.
If answer is simple, Hermes may answer.
If it would materially contradict prior final answer, Hermes states a concrete correction rather than a vague second opinion.
```

---

## 16. Open questions and design tradeoffs

### Should public acknowledgements be default for Tier 2?

Tradeoff:

```text
More confidence vs more chat noise.
```

Recommendation:

```text
Visible acknowledgement only when explicit collaboration or expected delay exceeds 8-10 seconds.
```

### Should Hermes have veto power?

For Tier 2:

```text
No formal veto. Hermes can provide blocking objections; Kublai must represent unresolved disagreement honestly.
```

For Tier 3:

```text
Yes, for Hermes-primary system-health/protocol-safety concerns. But veto means “do not execute,” not “Hermes writes the answer.”
```

### Should support contributions be stored verbatim?

Recommendation:

```text
Store structured summaries and safe public attribution.
Avoid storing hidden reasoning or sensitive raw context.
```

### Should Redis replace SQLite?

Only when distribution requires it. Starting with Redis too early adds operational surface area without solving the product problem. SQLite is enough to prove behavior.

### Should an internal Telegram group be used for deliberation?

No, not as the primary channel. It is not transactional, it increases leak risk, and it normalizes visible side chatter. Use OpenClaw sessions plus DB events.

---

## Explicit answers to concrete design questions

### 1. Should Kublai always be default aggregator for protocol/proposal questions?

Mostly yes, but not always.

Kublai should be the default aggregator for protocol/proposal/routing/project-management questions. Ownership should still be dynamically selected by deterministic domain rules.

Use:

```text
Protocol proposal -> Kublai
Group routing -> Kublai
System health protocol repair -> Hermes
Kublai malfunction -> Hermes
Runtime/provider debugging -> Hermes
```

Do not run a negotiation every time. That creates exactly the noise this protocol is designed to eliminate.

### 2. What is the minimum viable response-lock implementation?

Minimum viable:

```text
SQLite response_locks table
SQLite coordination_events table
SQLite send_outbox table
atomic INSERT claim
status field
owner field
expires_at
scope_version
final_send_key
cron stale-lock sweeper
```

This is enough to stop duplicate replies and support basic Tier 2 collaboration.

### 3. Should locks be stored in JSON, SQLite, Redis, Neo4j, or OpenClaw session metadata?

Use **SQLite** first.

Ranking:

```text
1. SQLite: best MVP
2. Redis + durable DB: best distributed version
3. Postgres: best mature multi-host version
4. OpenClaw session metadata: useful context, not authoritative lock store
5. JSON files: debug snapshots only
6. Neo4j: not for locks
```

### 4. What timeout values should be used?

Recommended defaults:

```text
Tier 1:
- target answer: <30s
- lock TTL: 90s
- no support timeout

Tier 2:
- visible ack if delayed: 8-10s
- contribution deadline: 45s default
- max contribution wait: 90s
- final deadline: 90-120s

Tier 3:
- visible ack: immediate
- contribution deadline: 3-5 min
- review deadline: 2-3 min
- lock TTL/final deadline: 10-15 min
```

### 5. How should support-agent contributions be represented?

Use structured contribution envelopes:

```json
{
  "contributor_agent": "hermes",
  "stance": "support_with_additions",
  "blocking": false,
  "summary": "Use lock plus send gate; add stale-owner recovery.",
  "key_points": [
    "Do not expose internal deliberation.",
    "Record timeout honestly.",
    "Use send idempotency."
  ],
  "objections": [],
  "confidence": "high",
  "safe_public_attribution": "Hermes reviewed system-health and protocol-maintenance aspects."
}
```

The final answer can cite collaboration like:

```text
I incorporated Hermes’s system-health and protocol-maintenance input.
```

Do not expose hidden reasoning.

### 6. How should agents detect that another agent already owns the thread?

On every inbound message:

```python
lock = locks.find_active_by_thread(chat_id, root_message_id, thread_id)

if lock and lock.status not in TERMINAL_STATES:
    if lock.owner != self.agent_id:
        stay_silent_or_contribute(lock)
```

Also inspect:

```text
reply_to_message_id
thread/topic id
root_message_id
active lock TTL
scope_version
final_answer_message_id
```

### 7. How should the system handle simultaneous claims?

Use atomic database claim.

```text
INSERT lock row.
If success: owner.
If conflict: loser loads existing lock and stays silent.
```

If both claims somehow exist due to split-brain, use:

```text
higher owner_epoch wins
valid claim token wins
domain-priority owner wins
later public sends blocked by send_gate
```

### 8. How should follow-up messages from Danny modify or cancel an active lock?

Use a follow-up resolver.

```python
if msg.sender == Danny and same_thread(msg, active_lock):
    if is_cancel(msg):
        cancel_lock()
    elif is_scope_change(msg):
        increment_scope_version()
        reset_deadlines()
    elif is_owner_transfer_request(msg):
        transfer_lock()
    elif is_approval(msg):
        mark_human_approval()
    else:
        append_context_to_lock()
```

Final sends should use:

```text
send_key = lock_id + ":final:v" + scope_version
```

That prevents an old draft from posting after Danny changes scope.

### 9. Should there be a visible “coordinating” acknowledgement?

Yes, but only under clear conditions.

Show it when:

```text
explicit two-agent collaboration
Tier 3
expected delay >8-10s
specialist async task created
silence would create uncertainty
```

Suppress it when:

```text
Tier 1
answer is quick
another agent already acknowledged
```

### 10. What should the exact wire/event format be?

Use the event envelope in section 7.

Required event types:

```text
lock.claimed
contribution.requested
contribution.submitted
draft.review_requested
draft.review_submitted
lock.transfer_requested
collaboration.timed_out
final_answer.ready
lock.cancelled
```

Each event should include:

```text
event_id
event_type
lock_id
correlation_id
causation_id
source_agent
target_agents
created_at
ttl_seconds
visibility
lock_revision
body
```

### 11. How should the protocol prevent duplicate Telegram sends?

Use a send gate, not just a lock.

```text
Every public send has a deterministic send_key.
send_key is unique in send_outbox.
Only the lock owner with current claim token may reserve final_send_key.
No reservation, no send.
Unknown send status is not blindly retried.
```

Also:

```text
For same Telegram group, use normal in-session reply.
Block message-tool sends to the same group unless explicitly approved.
```

### 12. What implementation hooks are needed in OpenClaw?

Minimum hooks:

```text
on_telegram_inbound(update)
normalize_metadata(update)
resolve_thread_root(message)
classify_intent(message)
select_owner(intent)
try_claim_response_lock(lock_spec)
get_active_lock(chat_id, root_message_id)
publish_coordination_event(event)
handle_coordination_event(event)
wait_for_contributions(lock_id, deadline)
send_public_reply_once(send_key, text)
route_task_intake(task)
report_task_completion(origin, result)
sweep_stale_locks()
explain_why(message_id)
message_tool_same_chat_guard()
```

For OpenClaw capabilities:

```text
sessions_list      -> find active Kublai/Hermes sessions
sessions_send      -> internal contribution/review requests
sessions_history   -> debug coordination
sessions_spawn     -> specialist/subagent/coding sessions
task_intake.py     -> specialist routing
cron               -> stale locks, reminders, health sweeps
exec/files/scripts -> local diagnostics and lock maintenance
message tool       -> cross-chat sends only, not same-group duplicate replies
```

---

## Non-negotiable operating discipline

This design succeeds or fails on these rules:

```text
One visible owner.
Structured internal contribution.
One public send.
Honest timeout disclosure.
No hidden fake consensus.
No duplicate same-group sends.
No routine public side chatter between agents.
```

Anything looser will eventually collapse into duplicate replies, contradictory guidance, and fake consensus.
