# Canonical Group Chat Collaboration Protocol

Status: canonical design draft
Source: Danny-provided GPT Pro architecture, consolidated for OpenClaw/Kublai/Hermes implementation
Last updated: 2026-04-29

## 1. Executive summary

The three-tier model is correct directionally, but it requires two hard implementation primitives:

1. A shared response-lock store so agents know who owns a thread.
2. A send gate with idempotency keys so even a buggy or restarted agent cannot double-post.

Recommended architecture:

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

Core rule:

> For every actionable user request in the group, exactly one agent may own the visible answer. Other agents may contribute internally, but they do not independently answer unless ownership is transferred or the owner fails.

Default ownership:

- Kublai: routing, proposals, architecture, protocol, coordination, project management, async task delegation.
- Hermes: health, repair, runtime debugging, protocol maintenance after adoption, Kublai/OpenClaw/provider malfunction.
- Explicit “Kublai and Hermes collaborate” requests: Kublai aggregates unless the subject is clearly Hermes-owned.

Collaboration should be real but compact: support-agent contribution summaries, objections, constraints, and review/approval status — not exposed deliberation.

Minimum viable implementation: SQLite with WAL mode for locks, events, contributions, and send outbox. JSON is too fragile as the source of truth. Neo4j is overkill for lock arbitration. Redis is useful later for multi-host distributed locking.

## 2. Coordination modes

### Mode 0: Observe / no-response

Use when neither bot is addressed, another agent already answered, or the message is casual/non-actionable.

- No public answer.
- No durable lock needed.

### Tier 1: Single-owner routine answer

Use for simple routing, status, explanation, clarification, or health checks.

Examples:

- “Kublai, why did that route to Mongke?”
- “Hermes, is the cron healthy?”
- “Kublai, what’s in the queue?”

Behavior:

- One owner answers.
- Other agent observes silently.
- No collaboration unless there is a concrete correction.
- Use lightweight lock/claim if group race is possible.

### Tier 2: Shared expertise / one synthesized answer

Use when the answer benefits from both agents but is not high-risk.

Examples:

- “Kublai and Hermes, collaborate on one proposal for group routing.”
- “What protocol should we use for inter-agent coordination?”
- “Review this plan from project-management and system-health perspectives.”

Behavior:

- Owner claims.
- Owner requests compact contribution from support agent.
- Support contributes internally.
- Owner synthesizes and posts one public answer.
- Support agent does not post publicly.

### Tier 3: High-risk governance / protocol / system-change decision

Use for decisions that affect deployment, persistent protocol, irreversible actions, permissions, external sends, money, destructive changes, or safety-sensitive behavior.

Examples:

- “Both of you decide whether to deploy this.”
- “Change the routing protocol.”
- “Disable Kublai’s queue logic.”
- “Send this to another chat.”
- “Delete these logs.”
- “Rotate credentials.”

Behavior:

- Explicit lock.
- Visible acknowledgement.
- Required contributors listed.
- Support contribution required or timeout disclosed.
- Draft/review loop required.
- Unresolved disagreement disclosed.
- Human approval required before irreversible action.

Do not make every interesting question Tier 3. Tier 3 is for decisions where a bad answer causes persistent damage.

## 3. Ownership rules

Kublai owns by default when the request is about:

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

Hermes owns by default when the request is about:

- System health.
- Agent malfunction.
- Runtime/provider debugging.
- Cron hygiene.
- Memory/brain/wiki maintenance.
- Protocol maintenance after adoption.
- Repairing Kublai, OpenClaw, or provider issues.
- “Why is Kublai silent?”

Dynamic ownership should be deterministic, not negotiated:

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

Final-answer authority:

- The owner has final wording authority, not final truth authority.
- The owner decides what gets posted.
- Required contributors can block false claims of consensus.
- If a required contributor disagrees, the owner must resolve it or disclose it.
- If a required contributor times out, the owner must not claim collaboration happened.

## 4. Intent classification

Classifier output shape:

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

Classification rules:

| Input pattern | Classification |
|---|---|
| Direct mention of Kublai + routine routing/project question | Tier 1, owner Kublai |
| Direct mention of Hermes + health/runtime/debugging | Tier 1, owner Hermes |
| “Kublai and Hermes”, “both of you”, “collaborate”, “joint proposal” | Tier 2 unless high-risk |
| “Decide whether to deploy/change/delete/send/rotate/disable” | Tier 3 |
| “Create task”, “route this”, “have X do Y” | Kublai owns, specialist routed async |
| “Why did this fail?”, “audit this error”, “security concern” | Hermes or Jochi via Kublai depending protocol |
| Ambiguous but action-oriented | Owner claims, asks one clarification |
| Casual chat or acknowledgement | Observe/no-response |

Escalate to Tier 3 when any of these are true:

- Persistent system change.
- Deployment.
- Credential/secret handling.
- External message/action.
- Permission change.
- Data deletion.
- Money/spend.
- Cron/scheduler modification.
- Security posture change.
- Policy/protocol decree.
- Human asked for a binding decision.

## 5. Response-lock schema

A lock is a thread ownership and collaboration contract, not just a mutex.

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

Statuses:

- observed
- classified
- claiming
- claimed
- collecting_contributions
- drafting
- reviewing
- ready_to_send
- sending
- answered
- timed_out
- cancelled
- transferred
- failed
- expired

Avoid `unclaimed` as a stored status except in memory. A lock row usually exists only after a claim attempt.

## 6. State machine

```text
Inbound message
 -> observed
 -> classified
 -> claiming
 -> claimed
 -> answered                       # Tier 1
 -> collecting_contributions        # Tier 2 / Tier 3
 -> drafting
 -> ready_to_send                   # Tier 2
 -> reviewing                       # Tier 3 or requested review
 -> ready_to_send
 -> timed_out
 -> sending
 -> answered
```

Terminal states:

- answered
- timed_out
- cancelled
- failed
- expired

Transition rules:

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

Retention:

| Data | Retention |
|---|---|
| Active locks | Until terminal + TTL |
| Tier 1 terminal locks | 7 days |
| Tier 2 terminal locks | 30 days |
| Tier 3 terminal locks | 180+ days |
| Raw sensitive payloads | Do not store, or encrypted short TTL |
| Final decision summaries | Durable memory if operationally important |

## 7. Inter-agent event schema

Common envelope:

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

Required event types:

- lock.claimed
- contribution.requested
- contribution.submitted
- draft.review_requested
- draft.review_submitted
- lock.transfer_requested
- collaboration.timed_out
- final_answer.ready
- lock.cancelled

Contribution object:

```json
{
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
```

Tier 3 stricter contribution object:

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

## 8. Collaboration workflows

### Tier 1 workflow

1. Agent receives Telegram message.
2. Normalize metadata.
3. Resolve root/thread.
4. Classify as Tier 1.
5. Attempt lightweight claim.
6. If claim succeeds, answer.
7. If existing owner found, stay silent.
8. Record final answer message_id.

```python
def handle_tier1(agent, msg, intent):
    lock = locks.try_claim(
        lock_id=thread_lock_id(msg),
        owner=agent.id,
        tier="tier_1_routine",
        ttl_seconds=90,
        request_summary=intent.scope_summary,
    )

    if not lock.acquired:
        return SILENT

    answer = agent.generate_direct_answer(msg, intent)

    send_gate.send_once(
        send_key=f"{lock.lock_id}:final:v{lock.scope_version}",
        chat_id=msg.chat_id,
        reply_to_message_id=msg.root_message_id,
        text=answer,
    )

    locks.mark_answered(lock.lock_id)
```

### Tier 2 workflow

1. Owner claims lock.
2. Owner may send visible acknowledgement if delayed or explicit collaboration.
3. Owner sends internal contribution request.
4. Support agent confirms it is not owner.
5. Support submits structured contribution.
6. Owner synthesizes.
7. Owner posts one final public answer.
8. Support stays silent.

```python
def handle_tier2_owner(owner, msg, intent):
    lock = locks.claim_or_observe(
        lock_id=thread_lock_id(msg),
        preferred_owner=intent.preferred_owner,
        owner=owner.id,
        tier="tier_2_shared_expertise",
        support_agents=intent.support_agents,
        required_contributors=intent.required_contributors,
        deadlines=deadline_policy("tier_2"),
    )

    if not lock.owned_by(owner.id):
        return SILENT_OR_CONTRIBUTE

    maybe_public_ack(lock, msg)

    for support in lock.required_contributors:
        bus.publish(contribution_request(lock, support, intent))

    contributions = wait_for_contributions(
        lock_id=lock.lock_id,
        required=lock.required_contributors,
        until=lock.timing.contribution_deadline_at,
    )

    draft = owner.synthesize_answer(msg, intent, contributions)

    send_gate.send_once(
        send_key=lock.send_control.final_send_key,
        chat_id=msg.chat_id,
        reply_to_message_id=lock.public_messages.reply_to_message_id,
        text=draft,
    )

    locks.mark_answered(lock.lock_id)
```

Support side:

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
        expose_private_reasoning=False,
    )

    bus.publish(contribution_submitted(lock, agent.id, contribution))
```

### Tier 3 workflow

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

## 9. Timeout and conflict policy

Recommended timeouts:

| Case | Public ack | Support deadline | Review deadline | Final deadline |
|---|---|---|---|---|
| Tier 1 routine | None unless delayed >10s | N/A | N/A | 30s target, 90s lock TTL |
| Tier 2 shared expertise | After 8–10s if not ready; immediate if explicit “both” and likely slow | 45s default, 90s max | Optional 30s | 90–120s |
| Tier 3 high-risk | Immediate | 3–5 min | 2–3 min | 10–15 min |
| Specialist async routing | Immediate short ack if task created | N/A | N/A | Completion reported later |

Tier 2 timeout language:

> I could not get Hermes’s input within the collaboration window, so this is Kublai’s provisional answer rather than a joint answer.

Tier 3 timeout language:

> I do not have Hermes’s required review yet, so I’m not treating this as approved. My provisional recommendation is X, but I will not execute the change without Danny’s confirmation.

Duplicate claims:

- Use atomic compare-and-swap.
- First valid claim wins if it matches ownership policy.
- If simultaneous, deterministic owner scoring wins.
- Losing claimant records `claim_lost` and stays silent.
- If loser has useful domain input, it contributes internally.
- If winner is wrong by policy, support requests transfer rather than publicly contradicting.

Tie-break scoring:

```python
CLAIM_PRIORITY = {
    "explicit_mentioned_owner": 100,
    "domain_primary_owner": 80,
    "collaboration_default_aggregator": 60,
    "fallback_owner": 20,
}

AGENT_TIEBREAK = {
    "kublai": 10,
    "hermes": 5,
}
```

For health/runtime domains, Hermes’s domain score beats Kublai’s default aggregator score.

Owner crash:

- Use owner heartbeat.
- Tier 1 stale: 30s.
- Tier 2 stale: 60s.
- Tier 3 stale: 2 min.
- Support may claim transfer after stale detection.
- New owner must disclose incomplete required review when relevant.

Stale lock sweeper:

```python
for lock in locks.active():
    if now > lock.expires_at:
        locks.expire(lock)
    elif heartbeat_stale(lock):
        locks.mark_transferable(lock)
```

Human follow-up behavior:

| Human follow-up | Protocol behavior |
|---|---|
| “Never mind” / “cancel” | Cancel lock |
| “Actually make it about X” | Increment scope_version; reset deadlines |
| “Hermes, take this instead” | Transfer to Hermes |
| “Kublai, just answer solo” | Drop support requirement |
| “Wait before acting” | Pause lock |
| “Proceed” | Continue if approval requirements satisfied |

## 10. User-visible UX rules

The group should see:

- At most one acknowledgement.
- At most one final answer.
- Event-driven updates only.
- No internal deliberation.
- No fake consensus.

Show visible acknowledgement when:

- Danny explicitly asks both agents to collaborate.
- Expected answer time exceeds 8–10 seconds.
- Tier 3 is triggered.
- Specialist async task is created.
- Silence would make Danny uncertain whether the request was noticed.

Suppress visible acknowledgement when:

- Tier 1 answer is immediate.
- The answer can be posted quickly.
- Another agent already acknowledged ownership.

Example shared proposal acknowledgement:

```text
Got it. I’ll coordinate with Hermes and post one consolidated proposal.
```

Example final attribution:

```text
Here’s the consolidated proposal. I incorporated Hermes’s protocol-maintenance and system-health input.

[one unified answer]
```

Example timeout:

```text
I could not get Hermes’s required review within 5 minutes, so this is not a joint approval.

My provisional recommendation: do not deploy yet. The change may be ready, but without Hermes’s health review and a verified rollback path, I would not treat this as safe to execute.
```

## 11. Storage and audit design

Use SQLite with WAL mode for MVP.

Do not use JSON as authoritative lock store. JSON is acceptable for debug snapshots only.

Use Redis later if Kublai and Hermes run on different machines or need distributed pub/sub. Use Postgres later for durable multi-host maturity. Use Neo4j for long-term knowledge/memory, not lock arbitration.

Minimal schema:

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

Atomic claim uses `INSERT ... ON CONFLICT(lock_id) DO NOTHING`. If insert succeeds, agent owns the lock. If insert fails, load existing lock and obey it.

Send gate:

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
        payload_preview=text[:500],
    )

    if not reserved:
        existing = outbox.get(send_key)
        if existing.status in ["sent", "sending", "unknown"]:
            return DO_NOT_SEND
        raise SendConflict(existing)

    try:
        outbox.mark_sending(send_key)
        sent_message = telegram_send_normal_reply(
            chat_id=chat_id,
            reply_to_message_id=reply_to_message_id,
            text=text,
        )
        outbox.mark_sent(send_key, sent_message.message_id)
        locks.record_final_message(lock_id, sent_message.message_id)
    except Exception as e:
        outbox.mark_failed(send_key, str(e))
        raise
```

Audit events to record:

- message.observed
- intent.classified
- lock.claim_attempted
- lock.claimed
- lock.claim_lost
- contribution.requested
- contribution.submitted
- draft.review_requested
- draft.review_submitted
- public_ack.sent
- timeout.hit
- lock.transferred
- send.reserved
- send.succeeded
- send.failed
- lock.answered
- lock.cancelled
- lock.expired
- specialist_task.created
- specialist_task.completed
- specialist_task.failed

Do not store private chain-of-thought, raw secrets, API keys, full sensitive logs, unnecessary personal data, or raw specialist prompts containing secrets. Store summaries, hashes, safe excerpts, redacted pointers, final decisions, contributor stances, and blocking objections.

Inspection command:

```text
/why <message_id>
```

Example output:

```text
That answer was posted by Kublai because the request was classified as Tier 2 shared expertise. Kublai owned the final answer, Hermes was requested as required contributor, Hermes submitted protocol-health input, and Kublai posted one synthesized answer. No timeout or disagreement was recorded.
```

## 12. Safety, privacy, and permission rules

Human approval required before:

- Deploying.
- Deleting data.
- Sending messages to other chats/users.
- Changing permissions.
- Rotating or exposing credentials.
- Spending money.
- Modifying production cron/schedulers.
- Changing persistent protocol/decree state.
- Running destructive commands.
- Sharing private logs with specialists.
- Creating broad async tasks with external side effects.

Approval object:

```json
{
  "approval_required": true,
  "approval_reason": "deployment decision",
  "allowed_without_approval": ["analysis", "recommendation", "non-destructive checks"],
  "blocked_without_approval": ["deploy", "delete", "external_send"],
  "approval_prompt": "Danny, confirm whether you want me to deploy after rollback checks pass."
}
```

Sensitive delegation rule:

- Strip secrets.
- Summarize instead of forwarding raw logs.
- Include only task-relevant context.
- Attach redaction notice.
- Record what was delegated.

## 13. Failure-mode handling

Agent offline:

- Tier 2: proceed provisionally after timeout and disclose missing collaborator.
- Tier 3: do not claim joint approval; block action or ask Danny whether to proceed without required review.

Tool failure:

- Record `tool.failure`.
- Say the joint review is incomplete if collaboration depended on the failed tool.

Internal communication unavailable:

- Tier 1: direct owner may answer if no collaboration required.
- Tier 2: disclose collaboration unavailable if final answer depends on it.
- Tier 3: fail closed; no high-risk approval without required contributor or Danny override.

Lock store unavailable:

- Fail closed for multi-agent collaboration.
- Only directly addressed agent may answer under degraded-mode policy.
- If both agents are addressed, Kublai may post a short degraded-mode message only if configured as default aggregator.

Telegram send failure:

- Use outbox states: reserved, sending, sent, failed, unknown.
- If uncertain whether Telegram accepted a message, mark unknown and do not blindly retry.
- Reconcile from recent updates/history if possible; otherwise avoid duplicate sends.

Specialist task failure:

- Kublai reports back to originating chat with owner, reason, blocker, and next action.

## 14. OpenClaw / Telegram implementation plan

### Phase 1: MVP arbitration

Implement:

- `coordination_store.py`
- `lock_manager.py`
- `send_gate.py`
- `intent_classifier.py`
- `thread_resolver.py`
- `agent_policy.py`

Behavior:

- Kublai and Hermes both receive inbound Telegram messages.
- Each normalizes metadata.
- Each classifies ownership candidacy.
- Candidate owner attempts atomic SQLite claim.
- Loser stays silent.
- Winner answers through send gate.

### Phase 2: Tier 2 collaboration

Implement:

- `coordination_bus.py`
- `contribution.requested`
- `contribution.submitted`
- support contribution handler
- owner synthesis handler

Use OpenClaw `sessions_send` for internal coordination, SQLite event queue as fallback, and session history for debugging. Do not use Telegram group messages for internal deliberation.

### Phase 3: Tier 3 governance

Add:

- review-required policy
- draft review events
- blocking objections
- human approval objects
- timeout disclosure

### Phase 4: Specialist routing integration

Kublai creates one specialist task through `task_intake.py` when async work is required.

Rules:

- One routed task by default.
- No unnecessary decomposition.
- Originating chat/message attached.
- Completion/failure/blockers report back to originating chat.

### Phase 5: Watchdogs and inspection

Add:

- cron lock sweeper
- owner heartbeat updater
- `/locks`
- `/why <message_id>`
- `/coordination status`
- incident log

Important OpenClaw hooks:

- `on_telegram_inbound(update)`
- `normalize_telegram_metadata(update)`
- `resolve_thread_root(message)`
- `classify_intent(message, context)`
- `select_owner(intent)`
- `try_claim_response_lock(intent, message)`
- `publish_coordination_event(event)`
- `handle_coordination_event(event)`
- `send_public_reply_once(lock, text)`
- `route_specialist_task(task)`
- `report_task_result_to_origin(task_result)`
- `sweep_stale_locks()`
- `explain_answer(message_id)`

Same-group send guard:

```python
def message_tool_guard(target_chat_id, current_chat_id, purpose):
    if target_chat_id == current_chat_id and purpose != "approved_exception":
        raise SameChatMessageToolDenied(
            "Use normal in-session reply path for same Telegram group."
        )
```

## 15. Regression tests

1. Routine Kublai routing question: Kublai answers; Hermes silent.
2. Routine Hermes health question: Hermes answers; Kublai silent.
3. Explicit collaboration proposal: Kublai claims; Hermes contributes internally; Kublai posts one synthesized answer.
4. Hermes-owned Kublai malfunction: Hermes owns and reports status/fix.
5. Collaboration timeout: no fake joint approval; irreversible action blocked.
6. Duplicate simultaneous claims: SQLite claim chooses one; loser silent; claim_lost recorded.
7. Support agent public mistake: incident recorded; owner consolidates; no public argument.
8. Owner crash after claim: stale heartbeat triggers transfer; old owner cannot post stale final.
9. Human cancels active collaboration: lock cancelled; no final answer posted.
10. Human changes scope mid-collaboration: scope_version increments; deadlines reset; stale drafts blocked.
11. Lock store unavailable: Tier 2/Tier 3 fail closed; no fake joint answer.
12. Telegram send accepted but local record missing: outbox unknown; no blind retry.
13. Specialist async task completion: Kublai reports completion/failure/blockers to originating chat.
14. Conflicting domain ownership: runtime repair goes to Hermes even if both agents addressed.
15. Follow-up after final answer: new related lock; correction only if concrete.

## 16. Open questions and tradeoffs

### Should public acknowledgements be default for Tier 2?

Recommendation: only when explicit collaboration or expected delay >8–10s.

### Should Hermes have veto power?

Tier 2: no formal veto, but blocking objections must be represented honestly.

Tier 3: yes for Hermes-primary system-health/protocol-safety concerns. Veto means “do not execute,” not “Hermes writes the answer.”

### Should support contributions be stored verbatim?

Recommendation: store structured summaries and safe attribution. Avoid hidden reasoning or sensitive raw context.

### Should Redis replace SQLite?

Only when distribution requires it. SQLite is enough to prove behavior.

### Should an internal Telegram group be used for deliberation?

No, not as the primary channel. Use OpenClaw sessions plus DB events. Telegram internal mirrors may be used for observability, not lock arbitration.

## 17. Explicit design answers

1. Kublai should usually be default aggregator for protocol/proposal/routing/project-management questions, but ownership should be deterministic by domain.
2. Minimum viable response lock: SQLite `response_locks`, `coordination_events`, `send_outbox`; atomic insert claim; status/owner/expires/scope/final_send_key; stale-lock sweeper.
3. Store locks in SQLite first. Redis/Postgres later. Do not use JSON or Neo4j for lock arbitration.
4. Timeouts: Tier 1 target <30s / 90s TTL; Tier 2 45s contribution default / 90–120s final; Tier 3 3–5m contribution / 10–15m final.
5. Support contributions should be structured summaries with stance, blocking flag, key points, objections, confidence, and safe public attribution.
6. Agents detect ownership by checking active lock by chat/thread/root message before answering.
7. Simultaneous claims handled by atomic DB insert plus deterministic scoring and send gate.
8. Follow-ups modify active lock by cancel, scope_version increment, transfer, pause, approval, or appended context.
9. Visible coordinating acknowledgement only for explicit collaboration, Tier 3, expected delay, specialist async task, or uncertainty.
10. Wire format is shared event envelope with required lock/contribution/review/transfer/timeout/final/cancel event types.
11. Duplicate Telegram sends are prevented by deterministic send_key and `send_outbox` reservation; same-group message-tool sends are guarded.
12. OpenClaw hooks needed: inbound normalization, thread resolution, intent classification, owner selection, lock claim, event publishing/handling, contribution wait, send once, task routing, completion reporting, stale sweep, `/why`, same-chat guard.

The design succeeds or fails on discipline: one owner, structured internal contribution, one public send, and honest timeout disclosure. Anything looser will collapse into duplicate replies and fake consensus.
