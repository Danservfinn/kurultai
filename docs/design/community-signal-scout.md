# Design: Community Signal Scout (`qorchi`)

**Status:** Draft for review
**Date:** 2026-08-08
**Author:** Kurultai design pass
**Companion:** [`identity-monitoring-agent.md`](identity-monitoring-agent.md) — the
self-monitoring (`keshig`) design, which shares this document's growth-invariant pattern
and its capability-contract enforcement gap.
**Supersedes / relates to:** Extends "Auto research and signal intake" (README) and the Brain retrieval source policy (`docs/operations/brain-source-policy.md`).

> This document is the **compliant** replacement for an earlier request to build a
> "join public and private groups by posing as a human, silently observe, and collect
> member data" agent. That mission is deliberately **not** designed here. Human
> impersonation, covert infiltration of private groups, and non-consensual harvesting
> of participants' personal data violate platform terms of service, anti-impersonation
> and bot-disclosure laws, communications-interception law, and data-protection law
> (GDPR/CCPA), and they break Kurultai's own read-only / approved-source / consent
> architecture. Nothing in this design should be adapted toward those ends.

## 1. Purpose

`qorchi` ("the herald") is a **read-only community listening scout**. Its job is to turn
what public and operator-authorized communities are *openly* saying into structured,
cited, minimized signal in Brain — for market/brand sentiment, trend detection,
competitive research, and public threat monitoring.

It is a specialization of the existing Auto-research scout pattern, not a new authority
model. It observes; it does not act, post, message, join under false pretenses, or
build dossiers on identifiable individuals.

## 2. Non-goals (hard boundaries)

`qorchi` **must not**, under any configuration:

1. Create or operate accounts that misrepresent an automated agent as a human.
2. Join, request access to, or remain in any private/closed space without the space
   owner's informed consent and a disclosed bot identity.
3. Circumvent access controls, invite gates, membership vetting, rate limits, robots
   directives, or ToS restrictions.
4. Collect, store, or infer personal data about identifiable individuals beyond the
   minimum needed for aggregate signal — no per-person profiles, no cross-platform
   identity linking, no contact graphs.
5. Take any outward action (post, react, DM, follow, join, submit, pay, publish).
6. Persist raw captures into retrieval-facing Brain tiers (see §6).

These are enforced as gates, not guidelines. A run that cannot satisfy them **halts and
emits a blocked receipt** rather than proceeding.

### 2.1 The growth invariant

One rule governs every future increment to this design and must be tested against any
proposed change:

> **The set of spaces `qorchi` observes may grow ONLY through an action taken by a human
> who is a member or administrator of that space, performed inside that space's own
> interface. No configuration, policy, rule, allowlist, saved filter, or standing
> approval may cause a space to become eligible.**

This forbids the most likely next increment — "auto-approve candidates matching a
standing policy" — by construction rather than by judgement. If a proposed feature would
let the observed set grow without a human acting inside the target space, the feature is
out of scope regardless of how it is justified.

## 3. Source model

Every source is classified before any collection. Only Tier A and Tier B are eligible.

| Tier | Description | Access method | Eligible |
|---|---|---|---|
| A — Public | Openly readable without login or acceptance of a members-only agreement | Official platform API or public read within ToS/robots | Yes |
| B — Operator-authorized | Spaces the operator owns/administers, or is invited to, **and** where a disclosed bot presence is permitted by the space's rules and members are notified | Official API with disclosed bot identity + logged consent record | Yes |
| C — Private/closed | Any space requiring membership, invitation, or vetting where a disclosed bot is not permitted | — | **No** |
| D — Restricted | Anything requiring impersonation, credential sharing, scraping against ToS, or access-control circumvention | — | **No, hard-fail** |

**Consent record (Tier B):** each authorized space carries a stored, operator-signed
record: space id, who authorized it, that members were notified of the bot's presence,
the disclosed bot identity string, permitted scope, and revocation contact. No record →
treated as Tier C → excluded.

## 4. Collection principles

- **Official APIs first.** Use each platform's documented, ToS-permitted API with proper
  auth and rate limits. No headless-browser impersonation, no ToS-circumventing scraping.
- **Disclosed identity.** Where the platform exposes bot identity (Discord bot users,
  Slack apps, Mastodon app tokens, etc.), the account is registered and visibly a bot.
- **Minimize at the edge.** The collector's *output* is topic- and aggregate-level.
  Author identifiers are stripped or one-way hashed at intake; message bodies are
  reduced to the signal fields the run actually needs (topic, sentiment, entity,
  timestamp bucket, source id). Raw bodies are not the deliverable.
- **Respect deletion.** If a source item is deleted upstream, downstream derived signal
  is invalidated on the next sync; retention is bounded (§6).
- **No inference on individuals.** Aggregate over a community, never profile a member.

## 5. Lawful-basis & privacy contract

Before a source is enabled, `qorchi` records a short data-protection contract:

- **Lawful basis** for processing (e.g. legitimate interest for public brand sentiment),
  with a one-line balancing note.
- **Purpose limitation** — the specific question the collection answers.
- **Retention window** — default 30 days for derived signal, 0 days for raw bodies.
- **Data-subject path** — how an individual can request exclusion/deletion, and where
  that exclusion list lives (honored at intake).
- **Special-category exclusion** — drop content revealing health, political, religious,
  sexual, biometric, or similar sensitive attributes rather than structuring it.

A source with no completed contract is not eligible to run.

## 6. Pipeline & Brain integration

```
approved source ──▶ collect (official API, ToS-bounded)
                     │
                     ▼
                 raw capture (Tier 3 forensic, local-only, TTL, never public)
                     │  minimize + redact PII + apply exclusion list
                     ▼
                 signal record (topic / sentiment / entity / bucketed time / source id)
                     │  dedupe + cite + freshness
                     ▼
   Brain: analyses/  + status/  (Tier 1/2)  ──▶ Kublai synthesis / operator report
```

Mapping to `docs/operations/brain-source-policy.md`:

- Raw captures land under `raw/` or `captures/` — **Tier 3 forensic, excluded from
  normal retrieval, local-only, TTL-bounded.** They never enter public fixtures.
- Structured aggregate signal is folded into **Tier 1/2** analyses/status pages with
  citations and freshness metadata — the same way research findings become Brain notes.
- Anything member-identifying that survives minimization by mistake belongs in
  **Tier 4 `hard-private/`** and is excluded from all public search; the preferred
  outcome is that it is never created.

## 7. Profile definition (roster entry)

| Field | Value |
|---|---|
| Profile id | `qorchi` |
| Role | read-only community listening / social-signal intake |
| Default lane | frontier model for synthesis; local/scheduled lane (Tolui) for pre-filter |
| Allowed tools | official-API read connectors (explicit allowlist), Brain write to `analyses/`,`status/`, raw capture to local Tier 3 |
| Forbidden tools | any post/DM/join/react/follow/submit/pay/publish action; any browser-impersonation or scraping tool; any credential-sharing connector |
| Escalation gates | enabling a new source, changing retention, any Tier promotion of member-level data, any outward action — all require explicit operator approval + receipt |
| Authority | observe → structure → propose. Never acts externally. Draft-only, same as Radar. |

SOUL stub (matches `profiles/templates/SOUL.profile.md`):

```markdown
# Profile: qorchi

I am a read-only community listening scout in a Hermes multi-agent setup.

## Role
- Primary function: signal (community/social listening)
- Allowed tools: official-API read connectors (allowlist), Brain write (analyses/, status/), Tier-3 raw capture (local, TTL)
- Escalation gates: new source enablement, retention changes, any member-level data, ALL outward actions

## Operating rules
- Public or operator-authorized-with-consent sources only. Never private/closed. Never impersonate a human.
- Official APIs within ToS and rate limits. No access-control circumvention.
- Minimize and redact at intake; aggregate over communities, never profile individuals.
- Raw captures stay Tier 3 forensic and local; only structured, cited, minimized signal reaches retrieval tiers.
- Record lawful basis, purpose, retention, and a data-subject exclusion path before any source runs.
- Observe and propose only. Record auditable receipts. Halt with a blocked receipt if any gate cannot be met.
```

## 8. Discovery capability (candidate queue)

`qorchi` may discover that communities exist. It may not obtain access to them.

These are separate steps and the design keeps them separate: **discovery** (learning a
space exists, from public directory listings), **access** (gaining the ability to read
it, always performed by a human inside the space's own interface), and **collection**
(§4, gated on an evidenced consent record).

### 8.1 What the platforms actually enforce

Verified against primary developer documentation, 2026-08-08:

| Platform | Can an automated account self-join? | Who must act |
|---|---|---|
| Discord | **No.** No self-join endpoint; bots cannot accept normal invites. Guild creation by apps was removed 2025-07-15, closing the last self-service path. | Guild member holding `MANAGE_GUILD` |
| Telegram | **No.** The Bot API exposes no join method at all. No history backfill — messages sent before the bot was added are permanently invisible. | Group member with "Add Members"; channels require admin |
| Slack | **Workspace: no** — install is always a human OAuth grant. **Public channels post-install: yes**, a bot can `conversations.join` without asking. | Workspace member (or admin, if approval is enabled) |
| X / LinkedIn / Meta | **No.** No join endpoint on any official API. X Communities were shut down 2026-05-30. | n/a — group content largely inaccessible to third-party apps |
| Reddit | Subscribing to a public sub is self-service, but irrelevant: public reading needs no subscription. Private/restricted access requires a moderator. | Reddit staff (API approval); moderators (private subs) |
| Matrix | **Yes.** For rooms with `join_rule: "public"` the spec states "anyone can join without any prior action." **No authorization step exists.** | Nobody at the join — only the homeserver admin, upstream |

**Matrix is the exception that the rest of this section exists for.** On every other
platform the consent gate is enforced by the platform itself. On Matrix it is not, so it
must be enforced by us: `qorchi` must never call `/join`, and public Matrix rooms are
treated as requiring the same operator-approved onboarding as everywhere else. A design
that relies on platform enforcement alone would silently fail here.

### 8.2 The candidate queue

Discovery produces a `CandidateSpace/v1` record — a closed schema with
`additionalProperties: false` and this exact field set:

`platform`, `space_id`, `public_display_name`, `directory_url`, `member_count_bucket`,
`directory_category`, `relevance_score`, `relevance_rationale` (agent-authored prose
only, never quoted source text), `discovered_at`.

Explicitly **denied fields**, dropped or hashed by the same intake redactor that handles
Tier A/B minimization: owner, admin and moderator names, handles, user ids, emails, DM
or mod-mail links. Identifying and contacting a space's administrator is an operator
step performed outside the system; the queue must not become a contact list.

Rules that make the queue safe rather than merely policy-compliant:

1. **Rank only from the directory record.** Relevance is scored from fields present in
   the public listing — name, description, category, member-count bucket, language,
   directory rank. One candidate equals at most one `GET`. This closes the incentive
   gradient toward "just peek inside to rank it properly," which is otherwise the
   design's most likely failure path.
2. **Store as Tier 4.** Candidate queues are written to `hard-private/` with a TTL,
   never to `proposals/` (Tier 2, retrieval-included). A ranked list of named
   communities is a target map; it must not become durable context other agents reason
   over. Only approved entries with an evidenced consent record graduate to a
   retrieval-facing source registry. Denied and expired candidates are **deleted**,
   retaining only a salted hash on a do-not-re-propose list.
3. **Hard volume caps.** At most 10 open candidates at any time, at most 5 appended per
   week. Exceeding either halts with a blocked receipt. This forces prioritization onto
   the agent rather than converting operator review into scanning a sorted list — an
   approval gate that fires a hundred times a week is not a gate.
4. **Sensitive-category tripwire at discovery.** Communities whose public description
   indicates health, recovery, sexuality, religion, immigration status, political
   dissent, or similar are dropped at discovery rather than ranked. A ranked list of
   such communities is itself a special-category inference, independent of anything
   collected inside them.
5. **One expiring research question per run.** Every discovery run cites a
   `research_question_id`, returns at most 25 candidates, and its queue is deleted when
   the question closes or the TTL expires. **No global or persistent candidate index, no
   cross-run merge, no dedupe against prior queues** — otherwise repeated runs
   accumulate a cross-platform community graph, which is §2's prohibition reappearing
   one level up.
6. **Discovery has its own contract.** §5's privacy contract is triggered by source
   enablement, which leaves discovery — the widest-aperture stage — uncovered. A
   discovery run cannot start without its own registered lawful basis, balancing note,
   queue retention, and exclusion-list version.

### 8.3 No outreach, in any form

The agent must not draft, template, translate, personalize, or assist in composing any
outreach, pitch, application, introduction, or persuasion artifact directed at a space,
its administrators, or its members — **including as a proposal for a human to send.**

This is stated separately because draft-only authority would otherwise permit it:
"the agent never messages an admin" does not by itself prevent the agent from writing
the message an operator then sends. The `CandidateSpace/v1` schema carries no free-text
field capable of holding such an artifact, which is the enforcement.

Relatedly, the agent must not emit OAuth install URLs, scope strings, permission
integers, or client ids. Otherwise the human's click consents to a grant the *agent*
specified. Per-platform read-only scope sets live as fixed constants in
`config/runtime-config/`, maintained by a human.

### 8.4 Consent must be evidenced, not attested

An admin's OAuth install proves the admin acted. It does not prove members were told.
Without separating these, "members notified" becomes a checkbox and every Tier B source
is a Tier C space with paperwork.

The consent record therefore carries a `member_notification` object with
`evidence_url` (permalink or content-hash of the in-space announcement), `notified_at`,
and `notification_text` — which must include the disclosed bot identity string as it
appears in-space and the §5 data-subject exclusion path, so members rather than only
admins can opt out. An install with no notification evidence sets the record to
`pending_notification`, and a space in that state is **treated as Tier C and excluded
from collection**.

### 8.5 Silence is not assumed

Some directory and discovery reads are visible to the space or emit federation events
from operator-controlled infrastructure. Before a platform is enabled for discovery it
needs a `discovery_silence` attestation answering three questions: does the read appear
in any admin-visible log, does it emit any event into the space, does it originate from
infrastructure that federates. **An unknown answer is a denial**, not a default-allow.

### 8.6 Credential separation

Discovery uses a dedicated credential in its own secret slot
(`KURULTAI_QORCHI_DISCOVERY_TOKEN`), never shared with any gateway profile — extending
the existing `separate_bots_required` policy in `gateways.yaml`. On Telegram in
particular, the same token that reads can also send; separation plus a validator
rejecting any manifest whose secret slots intersect the gateway set is what keeps a
read-only capability from silently inheriting send.

> **Known enforcement gap.** The repo's capability contracts express network allowlists
> by hostname only, so a discovery capability and an outreach capability are currently
> the same contract object. Closing this properly requires extending the contract schema
> with an `endpoint_allowlist` of `{host, method, path_template}` triples and
> constraining methods to `{GET, HEAD}` at the schema level, enforced at the connector
> rather than only in the manifest. Until that exists, discovery is **design-approved but
> not implementation-approved**.

## 9. Receipts & auditability

Each run emits a receipt (Tier 2) capturing: sources touched (with tier + consent-record
id), item counts in/out, PII-redaction summary, exclusion-list hits, retention applied,
and any gate that halted the run. This mirrors the receipts/recovery loop already in the
system and makes the scout's behavior reviewable rather than silent.

## 10. Open questions for the operator

1. Which specific platforms/communities, and which are Tier A vs. Tier B?
2. What is the concrete question each source answers (drives purpose limitation)?
3. Who owns the data-subject exclusion list and the consent records?
4. Default retention — is 30 days for derived signal acceptable?
5. Should aggregate outputs be operator-only, or feed a shared dashboard (Tier redaction)?
