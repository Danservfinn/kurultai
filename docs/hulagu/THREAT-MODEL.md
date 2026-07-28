# Hulagu threat model

Status: frozen source contract at G1. Runtime controls are specified, not installed, running, deployed, or pilot-validated.

## Protected assets

- Customer data: raw CV bytes, parsed CV fields, interview answers, profile preferences, work authorization, compensation, feedback, search decisions, private wiki/export contents, and return routes.
- Credentials and key material: bot/provider/database secrets, OAuth grants, route keys, action keys, subject digests, and backup keys.
- Control plane: authoritative Telegram identity and offset, consent state, tenant binding, lifecycle/work epochs, queue leases, publication pointers, deletion fences, budgets, and audit receipts.
- Availability and integrity: enrolled APFS vault identity, native PostgreSQL state, immutable input/output digests, schema versions, backup/restore continuity, and bounded resource budgets.

## Actors and trust boundaries

Actors are the customer in one private Telegram DM, the human operator/product owner, the independent security reviewer, the trusted `hulagu-app`, least-privilege `hulagu-runner`, least-privilege deletion dispatcher, native PostgreSQL, untrusted parser/ranker containers, external listing/research providers, Telegram Bot API, and an attacker controlling listing/CV content or replaying traffic.

Each trust boundary is explicit: Telegram and the app; enrollment and a consented tenant; app and PostgreSQL; app and runner queue functions; host and networkless container; app and provider mediator; active-route and deletion-route readers; private vault/customer data and aggregate Brain operator projections; online runtime and offline backup/restore; and implementation author and independent reviewer.

## Abuse cases

- Cross-tenant object IDs, forged tenant arguments, compromised callback payloads, or unsafe filesystem paths expose another customer.
- Prompt injection in a CV or listing becomes an instruction, tool request, path, state transition, or ranking authority.
- Duplicate/replayed Telegram updates, callbacks, jobs, provider outcomes, or publications create duplicate effects.
- Wrong bot identity, two pollers, lost advisory lock, or early offset acknowledgement loses or misattributes updates.
- Malicious documents attempt macros, active content, zip bombs, path traversal, symlink/hardlink escape, fork bombs, secret reads, oversized output, or network access.
- Container CLI/socket drift or PATH fallback grants an attacker engine authority.
- Missing/wrong/unenrolled or unencrypted vault causes writes to fallback storage; a cross-volume rename breaks atomicity.
- Stale leases or lifecycle/work epochs publish after pause, cancel, retry, or deletion.
- Deletion leaves customer content, recreates it from queued work, exposes its route, or loses the re-enrollment fence during key rotation/restore.
- Credential leakage enters argv, environment dumps, plist, Git, Brain, database, logs, fixtures, container inspection, exceptions, or provider payloads.

## Controls

- Fail closed on identity, consent, exact plan gate, schema, vault UUID/encryption, enrolled engine, epoch, lease, digest, and secret-reader mismatches.
- One pinned private-DM bot principal, one advisory-lock-backed poller, durable dedupe, transactional state/outbox/offset, and single-use version-bound action tokens.
- FORCE RLS, immutable trusted tenant principals, no caller tenant UUIDs, narrow security-definer functions, and least privilege across app/runner/deletion roles.
- Parse before context: bounded stream/hash/type checks, tenant quarantine, networkless non-root container, schema validation, and no CV-path model calls.
- Networkless ephemeral containers with pinned digests, no capabilities or privilege escalation, read-only roots, bounded resources, no secrets/host-sensitive mounts, and effective-state inspection.
- Same-volume temporary/final paths, no-follow descriptor operations, bounded regular files, file fsync, atomic replace, and parent fsync.
- Separate active/deletion route keys and readers; mediated provider operations never return credentials; redacted receipts and aggregate-only Brain projection.
- Lifecycle/work epochs, random fencing tokens, immutable digests, idempotent retries, generation CAS, and deletion tombstones prevent stale effects.

## Residual risks

These residual risks retain an accountable owner and closure gate; none is waived by Task 0:

- Total trusted-host or `hulagu-app` compromise remains inside the declared TCB; a separate broker is gated later. Owner: security architecture owner; gate: separate G0.
- Telegram send success can be remotely successful while locally unknown, so a bounded retry may duplicate a customer message. Owner: product owner; gate: G4 measurement.
- Company-research prose may be wrong after schema validation. Owner: product owner; gate: G3 synthetic benchmark and G5 consented review.
- Provider training, retention, region, deletion, and abuse-review posture is unproven. Owner: privacy reviewer; gate: before G5.
- APFS/Colima mounts, native PostgreSQL, backup/restore, Keychain reader separation, and rotation are contract-only. Owner: implementation/security owners; gate: G2/G3 evidence.
- Search-provider choice, dedicated bot identity, backup destination/retention, and result quality remain owner-gated proof debt.

## Secrets and rotation

| Secret/key family | Permitted reader | Rotation/revocation contract |
|---|---|---|
| Telegram bot token | `hulagu-app` only | Distinct from every Hermes/operator bot; owner-gated replacement; wrong `getMe` identity fails closed |
| Search-provider token | `hulagu-app` approved adapter only | Replace/revoke by provider gate; no fallback provider |
| OpenAI OAuth refresh token | `hulagu-app` research mediator only | Keychain-stored; access token is memory-only; expiry/revocation leaves research blank; reauthorization is interactive and owner-gated |
| Database role credentials (`hulagu_app`, `hulagu_runner`, `hulagu_deletion`) | Matching process only | Rotate independently; never substitute owner/migrator credentials |
| Subject-digest key | Identity resolver only | Versioned overlap; tombstones re-key before retirement or old key retained only for bounded matcher horizon |
| Action-token HMAC key | Action issuer/validator only | Independent family; short-lived single-use tokens; revoke versions fail closed |
| Route-binding HMAC key | Fixed deletion-send validator only | Versioned binding; never used for identity/action tokens |
| Active-route encryption key | App sender/identity path only | Versioned bounded overlap; revoked routes cannot send |
| Deletion-route encryption key | Deletion dispatcher only | Separate from active route; finite lifetime and erased after terminal delivery |
| Backup encryption key | Offline backup/restore operator only | Separate from runtime and signing keys; restore drill before retirement |
| Backup signing key | Offline backup/restore verifier only | Independent from encryption key; manifests reject unknown/revoked versions |

No secret value belongs in environment dumps, argv, plist, Git, Brain, database rows, fixtures, logs, exceptions, backups without encryption, provider payloads, or container state.

## Out of scope

Hulagu V1 has no job application, employer contact, social posting, payment, authenticated browsing, job-board login, generic URL fetch, shell/file/browser tool, public endpoint, recurring cron search, guaranteed outcome, general Hermes profile, shared Hermes bot token, or customer job representation in Kanban. A future Hermes conversational layer, credential broker, application automation, authenticated source, schedule, or public API requires a separate threat model and explicit G0.
