# Design: Community Signal Scout (`qorchi`)

**Status:** Draft for review
**Date:** 2026-08-08
**Author:** Kurultai design pass
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

## 8. Receipts & auditability

Each run emits a receipt (Tier 2) capturing: sources touched (with tier + consent-record
id), item counts in/out, PII-redaction summary, exclusion-list hits, retention applied,
and any gate that halted the run. This mirrors the receipts/recovery loop already in the
system and makes the scout's behavior reviewable rather than silent.

## 9. Open questions for the operator

1. Which specific platforms/communities, and which are Tier A vs. Tier B?
2. What is the concrete question each source answers (drives purpose limitation)?
3. Who owns the data-subject exclusion list and the consent records?
4. Default retention — is 30 days for derived signal acceptable?
5. Should aggregate outputs be operator-only, or feed a shared dashboard (Tier redaction)?
