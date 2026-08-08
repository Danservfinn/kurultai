# Design: Identity & Footprint Monitoring Agent (`keshig`)

**Status:** Draft for review — narrower than originally proposed
**Date:** 2026-08-08
**Companion to:** [`community-signal-scout.md`](community-signal-scout.md)

`keshig` (the household guard) monitors **one person's own** online exposure: data-broker
listings, breach appearances, impersonation accounts, and non-consensual imagery. It
exists to make exposure visible so it can be removed.

## 1. The finding that shaped this design

The original proposal was "verify the subject is the operator, then monitor." Adversarial
review found that framing is wrong in a way that matters:

> **Verification answers *who is operating this*. The harm turns on *what is being
> produced*.** A verified subject and an abuser holding her credentials generate
> identical API calls and receive identical artifacts.

In intimate-partner abuse — the modal threat here — proof of identifier control is close
to *anti-correlated* with being the person. The abuser set up the email account, is the
recovery address, administers the family plan, holds the phone, knows the password. He is
frequently the **more** verifiable party, and after a seize-then-verify he is the only
verifiable one. Every additional hardening of verification chases an adversary that
verification does not stop.

A second structural fact compounds it: **Kurultai is self-hosted.** Identity is
`local-operator`; consent records, tier assignments, and redaction rules are files in a
repo the operator owns. Every gate is policy expressed inside the adversary's own trust
domain, deletable in one commit. There is no adversarial boundary between the operator
and the enforcement.

The design conclusion follows directly:

> **The safety property is what is ABSENT, not what is gated.** A capability that is
> never built cannot be repointed by a fork, re-enabled by a config edit, or justified by
> a sympathetic use case. Everything below that is a rule rather than an absence is a
> speed bump, and is labelled as such.

## 2. The subject invariant

> **An engagement may be established ONLY by an action the subject performs in a channel
> the subject controls. The system may only ever monitor the identity holding the
> engagement's lease. No delegation, organizational authority, guardianship claim,
> contract, professional capacity, or standing approval may establish an engagement for
> anyone else.**

Test every proposed change against it. The likeliest future pressure is a delegated-subject
mode — "I'm a reputation manager running this for my client," "I'm HR monitoring our
executives," "I'm a parent" — arriving with revenue attached and a protective narrative.
That is the increment this invariant exists to forbid, and it should be refused as a
category rather than evaluated case by case.

Legitimate proxy cases (an incapacitated adult, an estate, a minor) are handled by manual,
human-reviewed, out-of-band process. They are not a system feature.

## 3. Never build (the actual safety property)

These are build-time absences. Each was reached because the capability's abuse value
dwarfs its defensive value, or because the defensive and abusive uses are *the same
computation* distinguished only by intent the system cannot observe.

| # | Never built | Why |
|---|---|---|
| 1 | **Face search, face matching, face embedding, any biometric search, any third-party face-search engine** | Highest abuse-to-legitimate ratio in the proposal. An abuser uploads a photo he already has and receives her new pseudonymous accounts. Verification cannot help: it confirms who is asking, never what the image is for. *Permitted instead:* perceptual hash of a **specific file** the subject uploads from their own library, matched against pages hosting that same file, for takedown of that exact file. Match the artifact, never the person. |
| 2 | **Location-change detection; any stored historical location value** | The victim relocates to escape; new listings, registrations and records appear; the agent reports the delta. Every stated control passes cleanly — public web, no purchase, subject-verified, defensively framed. Enforced architecturally: no historical location is stored, so **no delta is computable**. Location findings reduce at intake to `{finding_class, source_host, removal_endpoint, value_hash}` with plaintext discarded. |
| 3 | **Attribution and deanonymization: stylometry, posting-time correlation, EXIF extraction, handle-permutation inference, avatar matching against non-subject accounts, mutual-follower overlap** | Impersonation defense and pseudonym unmasking are the same query with the same output. *Permitted instead:* matching exact reuse of the subject's **registered canonical assets** — specific profile images, exact display-name strings, exact bio text the subject explicitly enrolls. |
| 4 | **Relationship edges — any person-to-person association field** | Support-network targeting: after she relocates, her sister, new partner, lawyer and shelter contact are findable when she is not. Adding such a field is a schema change that fails validation. Co-occurrence of a second identifiable person is a reason to **drop the artifact at intake**, not to redact and retain it. |
| 5 | **The inference layer: routine, schedule, commute, home-from-work inference, co-location, presence prediction** | Prohibited-feature list, enforced at the schema; attempts are logged. |
| 6 | **Persistent identity-linkage graph** | Matches between a verified identity and any account/handle/image are computed in-session, displayed with rationale, and discarded. No machine-readable linkage record, no cross-run merge. |
| 7 | **Free-text personal-name search — anywhere, in any mode, including preview, trial, dry-run, or "see what we'd find"** | This is the single most likely way the capability actually ships badly: a flow that renders results *before* the gate makes the gate decorative. The only legal query seed is a verified anchor identifier. The search planner takes `anchor_id` as a required parameter with no name-only path. |
| 8 | **Credential dumps, combolists, paste sites, stealer logs as sources** | "No purchased broker records" excludes purchase, not the large free leak ecosystem. Deny-listed source class. |
| 9 | **Identity-document collection — no upload path, no vendor integration, no enterprise exception** | Fails twice: the abuser frequently possesses the victim's ID, and collecting IDs builds a honeypot of exactly the documents that enable impersonation. *Use continuity instead:* challenges at T0, T+7d, T+30d. |
| 10 | **Export in any form: PDF, CSV, shareable link, third-party read API, webhook, vendor dashboard, service-account read** | This is also the FCRA-critical rule — see §7. View-only in an authenticated session bound to the verified subject. |
| 11 | **Operator-supplied consent documents** | A signed PDF can be checked for existence, never for authorship, and never for absence of coercion. There is no upload path. See §4. |

## 4. Consent cannot be documented — only performed

**You cannot distinguish coerced consent from free consent, and the design should stop
trying.** Every artifact — signature, checkbox, notarized form, recorded video — is
equally producible under duress, because duress leaves no trace in the artifact.
Revocability does not fix it: when the counterparty controls your job, lease, visa or
funding, the right to revoke exists and cannot be exercised, because revoking is itself an
adverse-inference event. EU regulators reached this years ago and treat employee consent
as presumptively invalid regardless of documentation (EDPB Opinion 2/2017; GDPR Recital 43).

Therefore consent and verification **collapse into one mechanism**: the only expression of
consent the system accepts is an action the subject takes inside a channel the subject
controls, delivered to the system directly. The document branch is deleted, not hardened.

Two consequences:

- **Verification methods are ranked by the proposition they prove.** Only *delivery-based*
  proofs (a token the system sends to an address/handle, which the operator must return)
  may **establish** an engagement. Asset-control proofs (DNS TXT, well-known file, repo
  commit, meta tag) prove control of an asset, not identity — an abuser registers
  `victimname.com` and passes cleanly — so they may only **extend** an engagement already
  established.
- **Verification anchors must be personally held.** Reject any email domain not on a
  consumer-provider allowlist, reject any domain whose MX/NS is under organizational
  control, and reject federated/SSO assertions. A work address can never be a verification
  factor, because "control over an identity" and "being that person" diverge completely
  when an organization administers the identity.

## 5. Structural properties that do the real work

Since verification cannot carry the load, these do:

1. **Subject is the account holder — always.** Not "operator verified as subject" but:
   the subject creates the profile from their own credential, and a helper (lawyer,
   security team, PR firm) is added as a **viewer** by a grant the subject issues and can
   revoke. This inverts the trust direction.
2. **Delivery is a property of the verified credential, not of config.** Alerts go only to
   channels bound at verification time. There is no webhook, no arbitrary email, no chat
   destination, no CC field — **the schema cannot express a third-party recipient.** Any
   operator-facing view is a strict mirror: same content, same time, no operator-only
   fields.
3. **Notice-then-delay, delivery-evidenced.** No collection runs until a plain-language
   notice has been *delivered* (receipt or bounce-free confirmation — not "we sent it") to
   every verified anchor, followed by a **7-day cooling-off window**, with a recurring
   notice thereafter. A permission the subject is unaware of is not a control; it is an
   unexercised right.
4. **Verification is a lease, not a property.** It expires every 30 days. First missed
   re-affirmation suspends **collection**, not merely alerting. Second wipes the profile.
   The failure mode is off, not on.
5. **Latency floor.** Digest-only delivery, minimum 24-hour aggregation, no per-event push,
   capped recheck cadence. **Latency is what converts a research report into a tracker**,
   and nothing else in the design bounds it.
6. **Contest halts and wipes.** A contest filed against a bound anchor halts the engagement
   immediately and wipes the accumulated profile — default-deny during dispute. Resumption
   requires out-of-band human review in which *recency of identifier control is explicitly
   excluded as a tiebreaker*, because recency is precisely the seize-then-verify abuser's
   advantage.
7. **Immutable anchor set.** Adding an anchor closes the engagement and opens a new one
   requiring fresh verification, notice, and cooling-off. Otherwise the binding is "bound
   at T, mutable at T+1."
8. **Zero raw retention.** Not TTL-bounded — zero. Collection streams through the redactor;
   only minimized `FootprintArtifact/v1` records are written. There is no `raw/` path in
   this profile's manifest. Otherwise a self-hosting operator simply reads the filesystem
   instead of the redacted output, and tier exclusion is only a retrieval-time property.
9. **Wipe preserves a non-content audit stub** — engagement id, salted anchor hash,
   verification method, lease renewals, run count, date range, termination reason.
   Otherwise "terminate and wipe" doubles as evidence destruction.
10. **Subject binding is signed and outside the agent's write scope.** Every source in this
    pipeline is hostile-by-default — the subject's adversaries are exactly the people
    publishing about them — so a fetched page may attempt to instruct the agent to widen
    the identifier set. The model may read the binding; only the lease-minting path may
    change it. Unknown linkage fails closed.

## 6. Per-class output rules

Alerting is restricted to a closed `finding_class` enum. **The subject's own volitional
activity is not a finding** — alerting on it converts the tool into a live behavioral feed
of the person's posts, tags and check-ins, which has near-zero defensive value.

| Class | What is stored and shown | Never |
|---|---|---|
| `broker_listing` | `{broker_name, listing_url, opt_out_url, fields_present[] as boolean flags, last_seen}` | **The values.** A subject filing a removal needs the URL, which fields are exposed, and the opt-out procedure — not their own address compiled back to them. |
| `breach_appearance` | `{breach_name, breach_date, identifier_class, data_classes_claimed}`, via k-anonymity hash-prefix query | Credential plaintext or hashes, security answers, DOB, government-ID fragments, historical addresses, phone numbers, or any other identifier found alongside the anchor in the dump. |
| `impersonation_asset_reuse` | Accounts reusing the subject's **registered canonical assets**, exact match | Any attribution, correlation, or real-world identity of the suspected impersonator. Discovering an impersonation candidate never opens a profile on that person. |
| `nonconsensual_image` | pHash match of a subject-supplied file against subject-named hosts | Similarity search, threshold tuning, open-corpus scanning. |
| `doxx_contact_or_location` | `{finding_class, source_host, removal_endpoint, value_hash}` | Plaintext values; anything permitting a location delta. |
| `mention` | `{url, platform, timestamp, claim_type, policy_violation_flag, report_link}` | **Author identity by default.** "Show me everything this account has said about me" is a forbidden query shape. One click on the URL reveals the handle; what must not exist is the compiled, sortable, continuously-refreshed roster of critics. |

**Co-materialization rule, enforced at the query layer:** a "locate-and-approach set" is
any two or more of {home address, workplace + hours, vehicle descriptor, routine tuple,
child's school, physical description}. Such a set must never materialize together in any
record, view, digest or export — including for the enrolled subject.

**Artifacts linking to the subject only because a third party mentioned, tagged or
photographed them**: never alerted on; folded into a periodic digest with no URL and no
timestamp finer than a month. Otherwise "monitor yourself, watch your ex" works perfectly
— redaction removes the third party's *name* but not the *link*, and the link is the
payload.

## 7. Legal contract

**FCRA — the load-bearing rule is "no third-party furnishing," not "public data."**
15 U.S.C. §1681a(f) defines a consumer reporting agency by assembling information *for the
purpose of furnishing consumer reports to third parties*. A service that shows a profile
**only to the verified subject** is outside the definition. This is a structural exemption,
and every FCRA obligation hangs off it.

Three things break it, and they are all product decisions rather than legal ones:

- **A shareable report.** §1681b(a)(2) makes "the written instructions of the consumer" a
  permissible purpose — which is exactly how portable tenant-screening reports work. A
  share link, a PDF with a verification URL, or a landlord view makes it a consumer report
  *even though the consumer authorized it*. Hence §3 rule 10.
- **Marketing.** FTC v. Spokeo ($800k, 2012): Spokeo became a CRA purely by marketing
  existing profiles to recruiters. Ad copy, SEO terms and help-center articles are evidence
  of "expected use." Maintain a **blocked-terms lint** over all copy: employment, hiring,
  recruiting, HR, candidate, applicant, tenant, landlord, screening, background check.
- **Disclaimers are not controls.** FTC v. TruthFinder/Instant Checkmate ($5.8M, 2023)
  expressly rejected the footer "we are not a consumer reporting agency." It must not
  appear in any risk register as a mitigation.

California's ICRAA (Civ. Code §1786) is broader — "character, general reputation, personal
characteristics, or mode of living" obtained by any means, with a private right of action.
The same no-third-party-furnishing rule governs, with a thinner margin.

**GDPR — there is no public-data exemption.** *Google Spain* (C-131/12) held that
collecting and organising already-published data is processing, and reasoned explicitly
about aggregation: search results give a "structured overview" that "could not have been
interconnected or could have been only with great difficulty," establishing "a more or less
detailed profile." A continuously-updated footprint profile is a stronger version of the
exact thing the CJEU found harmful.

- **Art. 9 is triggered by inference** (C-184/20, 1 Aug 2022): data from which sensitive
  information can be derived "by an intellectual operation involving comparison or
  deduction" *is* Art. 9 data. Sensitive inferences about **non-subjects must not be
  computed or stored at all**, since no Art. 9(2) condition is realistically available.
- **Art. 14 applies to every third party** whose data lands in a result, including
  Art. 14(2)(f) source disclosure. *ICO v Experian* [2024] UKUT 105 (AAC) upheld the
  finding that ~5.3 million people processed without notice were processed unlawfully.
  The disproportionate-effort exemption requires a published notice and a documented
  balancing assessment — it is not self-executing.
- **The household exemption is unavailable to the provider** (Recital 18; *Ryneš*).
- **Art. 3(2)(b) attaches via monitoring, not selling** — one EU-resident subject puts the
  pipeline in scope and triggers the Art. 27 representative requirement.
- **A DPIA is mandatory**: this meets many WP248 criteria at once — evaluation/scoring,
  systematic monitoring, highly personal data, matching/combining, vulnerable subjects.

**Third-party spillover** (§3 rules 4, 5; §6): redact at ingest, never at render, with
stable generic labels (`Third Party 1`). Maintain a **standing third-party suppression
register keyed on express refusal**, consulted at ingest so re-collection re-suppresses
automatically. Any unmasking requires a logged justification against a closed list.

## 8. What this design does not fix

Stated plainly, because a control list that omits its own limits is misleading:

- **An abuser with sustained account control passes everything.** He reads and deletes the
  notices, re-affirms the lease indefinitely, and receives the subject's copy of every
  digest. Notification removes *concealment*; it does not remove *access*. Where the
  subject has no channel outside the abuser's control, no protocol-layer fix exists.
- **Caps and quotas fall to burner accounts, extra hosts, and containers.** On a
  self-hosted install there is no cross-install accounting at all.
- **Every gate is editable by the operator.** A fork patches out the lease check in one
  commit. This is why §3 is the real design and §5 is secondary: absent capabilities
  survive a hostile fork; policy does not.
- **The honest ceiling:** a capable abuser already has a general web-research agent — this
  repo *is* one. The marginal harm reduction is that this project declines to hand him a
  tuned, scheduled, alerting one, and declines to build the components that are hard to
  build and useful mainly for dossiers.

## 9. Implementation status

**Design-approved, not implementation-approved.** Blocking items, inherited from the
companion design's §8.6 gap:

1. Capability contracts are hostname-only. Enforcing "read-only at the remote" and the
   deny-listed source classes requires `endpoint_allowlist` entries of
   `{host, method, path_template}` with methods constrained to `{GET, HEAD}`, enforced at
   the connector.
2. A **connector denylist** must bind to this profile — no mail, messages, calendar,
   drive, photo, device or carrier connector — enforced by extending the
   `separate_bots_required` manifest-intersection validator. Radar's `source_domains`
   already include `email` and `messages`; without this, the profile can be repointed at
   private connectors the operator still holds over the subject.
3. A dedicated credential slot (`KURULTAI_KESHIG_TOKEN`), never shared with a gateway.
4. A DPIA, and an Art. 27 representative if any subject or third party is EU-resident.

## 10. Open questions

1. Is the subject always the operator of this install, or is remote-subject enrollment
   needed? The latter is what §2 forbids as a *feature* — if it is required, this design
   does not cover it.
2. Which finding classes are actually wanted? Broker-listing removal alone is the highest
   value-to-risk ratio and could ship first, with §3's absences intact.
3. Does anything here need to reach Radar, or does Radar's existing `protect` bucket
   already carry it with a pointer rather than content?
4. Is 30-day lease expiry with collection-halt acceptable, given a subject who ignores
   email loses protection?
