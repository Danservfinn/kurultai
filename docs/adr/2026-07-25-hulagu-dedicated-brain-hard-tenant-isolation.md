# ADR: Hulagu dedicated Brain and hard tenant isolation boundary

- Date: 2026-07-25
- Status: Proposed security amendment; requires approval and incorporation into Hulagu v4 before implementation or G2
- Supersedes: none
- Amends: Hulagu v3 freeze by addition only; do not edit the frozen v3 plan or freeze receipt
- Scope: source-contract/security architecture only; no runtime mutation, no customer data, no credentials, no sharing, no contact, no commit, no push

## 1. Problem statement

Hulagu is a customer-facing product that will receive CVs, profile answers, search plans, generated wikis, receipts, exports, and deletion requests. The current approved source contract already states that customer data must not enter the operator Brain or Hermes profiles, but the Brain/wiki and tenant-storage boundary needs a stricter written amendment before any implementation gate beyond G1.

The amendment must prevent three classes of failure:

1. Customer content accidentally becomes operator memory by being indexed, mirrored, watched, cached, logged, or projected into `/Users/kublai/brain`, its private/public indexes, or its gateway.
2. One customer tenant can influence, read, search, export, delete, restore, or infer another tenant through shared paths, shared indexes, shared embeddings, shared caches, shared session memory, PostgreSQL rows, Google Sheets IDs/ACLs, backups, logs, or operator projections.
3. Caller-supplied tenant identifiers, file paths, symlinks, bind mounts, or route metadata become authority instead of a server-derived tenant principal tied to trusted identity.

This ADR threat-models the boundary first, then chooses the architecture.

## 2. Threat model

### 2.1 Protected assets

- Hulagu product/operator knowledge: product runbooks, deployment receipts, aggregate health, approved redacted operational notes, and incident records.
- Customer tenant content: CV bytes, parsed CV facts, interview/profile answers, search criteria, candidate bundles, private wiki pages, exports, receipts, deletion tombstones, backups, restore manifests, and Google Sheets artifacts.
- Identity bindings: Telegram subject bindings, tenant UUID mappings, route encryption material, action nonces, lifecycle epochs, support-session approvals, and break-glass records.
- Isolation metadata: PostgreSQL tenant rows, RLS policies, composite foreign keys, object IDs, backup manifests, index namespaces, cache keys, log correlation IDs, and redaction decisions.
- Kublai Brain and public gateway integrity: `/Users/kublai/brain`, `~/.brain-index/brain.db`, `~/.kublai/brain-index-private/brain.db`, brain-service SQLite state, telemetry, and gateway publication rules.

### 2.2 Adversaries and unsafe inputs

- Malicious or confused Telegram users, group chat participants, replayed callbacks, stale workers, or support/admin operators acting outside approval.
- CV files and generated documents containing prompt injection, path traversal strings, symlink targets, oversized/polyglot/macro/encrypted content, malformed Unicode, or spreadsheet formulas.
- Provider/model/search output that attempts to change tenant scope, trigger tools, include PII in operational health, or smuggle another tenant's IDs.
- Bugs in code that accidentally use global Brain/index/cache/session defaults, reuse a Google Sheet, skip RLS, or log raw payloads.
- Restore/migration tooling that mixes preexisting data, follows symlinks, imports path strings as tenant authority, or rehydrates deleted tenants.

### 2.3 Trust boundaries

- Trusted identity boundary: Telegram bot identity and verified private-DM subject are input to identity resolution, but caller-supplied tenant IDs are never trusted.
- TenantPrincipal boundary: all sensitive operations derive a `TenantPrincipal` from trusted identity plus server-side state before touching data.
- Filesystem boundary: tenant roots are opened through descriptor-confined, no-follow traversal under an enrolled encrypted vault; string paths are not authority.
- Brain boundary: Hulagu private Brain and tenant wikis are separate from Kublai Brain, indexes, watcher jobs, and public gateway.
- Database boundary: PostgreSQL roles, FORCE RLS, composite foreign keys, and audited functions enforce tenant scope even when application code has bugs.
- External artifact boundary: Google Sheets, exports, backups, logs, and operator projections carry tenant-scoped IDs and ACLs; no global artifact namespace.

### 2.4 Non-negotiable security invariants

1. Hulagu product/operator Brain root is physically and logically separate from Kublai Brain.
2. Customer content never lives in the Hulagu product/operator Brain; it lives only in tenant-confined roots.
3. Customer tenants never share a full-text index, vector index, embeddings cache, session memory, generated wiki namespace, Google Sheets file, export directory, backup decrypt scope, or deletion namespace.
4. Tenant scope is derived server-side from trusted identity; caller-supplied tenant IDs, tenant path strings, sheet IDs, route IDs, or object IDs can only be looked up after they are joined to the derived principal.
5. Missing, malformed, ambiguous, or unsupported tenant scope fails closed before read/write/search/export/share/backup/delete.
6. Kublai Brain may receive only aggregate redacted operational health and approved receipts that pass a machine-enforced projection schema and negative PII tests.
7. Kublai Brain must not index, mirror, symlink, mount, watch, publish, or search Hulagu Brain or tenant trees.

## 3. Decision

Adopt a hard three-zone architecture:

| Zone | Canonical root | Contents | Authority |
|---|---|---|---|
| Kublai operator Brain | `/Users/kublai/brain` plus its existing public/private indexes and gateway | Aggregate redacted Hulagu health and approved receipts only | Kublai/Kurultai operator processes; never tenant processes |
| Hulagu product/operator Brain | `/Volumes/KurultaiVault/hulagu/brain` | Hulagu product runbooks, deployment notes, aggregate operator knowledge, sanitized incident summaries, and approved internal product receipts only | Hulagu product/operator service identity; no customer content |
| Hulagu tenant roots | `/Volumes/KurultaiVault/hulagu/tenants/<server-derived-tenant_uuid>/` | One customer's documents, private wiki, indexes, caches, exports, receipts, tombstones, and backups | Tenant-scoped service identities after server-derived `TenantPrincipal` |

The implementation must make this structure real through OS identity, filesystem descriptors, database constraints, index namespaces, cache namespaces, projection schemas, ACL checks, and negative tests. It is not sufficient to document naming conventions or rely on path-string prefixes.

## 4. Architecture requirements

### 4.1 Filesystem and permissions

- The canonical Hulagu private root is `/Volumes/KurultaiVault/hulagu` on the owner-enrolled encrypted vault.
- The Hulagu product/operator Brain root is `/Volumes/KurultaiVault/hulagu/brain`.
- Tenant roots are exactly `/Volumes/KurultaiVault/hulagu/tenants/<server-derived-tenant_uuid>/`, where `<server-derived-tenant_uuid>` is generated and stored server-side after identity/consent checks.
- Tenant directories must be mode `0700`; tenant files must be mode `0600` unless a specific export/share operation creates a separately scoped artifact with an explicit ACL receipt.
- Tenant operations must use descriptor-confined traversal from an already-open tenant root. They must reject symlinks, hardlink escapes, bind mounts, device files, FIFOs, sockets, `..`, absolute paths, and cross-device temporary publication.
- Same-volume atomic replace is required for generated wiki/index/cache publication; partial files are quarantined and not visible to readers.
- No tenant root, Hulagu Brain root, index, cache, or backup path may be symlinked, bind-mounted, or watched from `/Users/kublai/brain` or its indexer/gateway roots.

### 4.2 TenantPrincipal and scope derivation

Every read/write/search/export/share/backup/delete operation must begin with a trusted identity record and derive a `TenantPrincipal` server-side:

1. Verify the inbound actor/route against the pinned Hulagu Telegram bot identity and private-DM policy, or against an approved support/admin break-glass session.
2. Look up the subject binding in Hulagu-owned storage; never accept `tenant_id` from callback data, commands, URLs, filenames, sheet names, exports, model output, or operator free text as authority.
3. Resolve exactly one active tenant UUID, lifecycle epoch, deletion state, and support/admin authority scope.
4. Attach the principal to the request context as an unforgeable typed value.
5. Require every repository, filesystem, index, cache, Sheets, backup, and export adapter to accept that typed principal rather than a raw tenant string.
6. Fail closed if no tenant exists, multiple tenants match, the lifecycle epoch is stale, deletion is pending/deleted, support authority is missing/expired, or any downstream adapter is asked to operate without a principal.

### 4.3 Brain, wiki, index, embedding, and cache isolation

- `/Volumes/KurultaiVault/hulagu/brain` contains only product/operator knowledge. It must not contain CVs, parsed CV facts, customer-specific pages, customer names, customer routes, tenant UUID maps, search plans, candidate bundles, exports, or customer receipts.
- Each tenant has its own wiki namespace under its tenant root, for example `tenants/<tenant_uuid>/wiki/`.
- Each tenant has its own full-text index, vector index, embedding cache, retrieval cache, model/session memory, and generated-artifact cache under its tenant root, for example `tenants/<tenant_uuid>/indexes/`, `tenants/<tenant_uuid>/embeddings/`, and `tenants/<tenant_uuid>/cache/`.
- There is no global customer corpus, global customer full-text index, global vector store, shared embeddings cache, shared session memory, or cross-tenant search API.
- Search functions must open only the current principal's tenant index namespace. They must not accept multiple tenant IDs, wildcard tenants, path strings, or global corpus handles.
- Cache keys must include a non-reversible tenant namespace bound to the principal and lifecycle epoch, but cache lookup must still be confined by directory/database namespace rather than relying on key prefixes alone.
- Generated tenant wiki pages and exports must include a manifest that records tenant UUID, lifecycle epoch, source digests, schema version, and creation time; the manifest remains inside that tenant root unless an approved export/share operation redacts and emits it.

### 4.4 PostgreSQL isolation

- PostgreSQL must use dedicated roles for app, runner, deletion dispatcher, migrator, backup/restore, and read-only auditor. No role may bypass tenant isolation in normal runtime.
- Tenant-owned tables must include `tenant_uuid` and `tenant_lifecycle_epoch` where lifecycle-sensitive operations require it.
- Composite foreign keys must include `tenant_uuid` so object IDs cannot join across tenants.
- FORCE ROW LEVEL SECURITY is required on tenant tables before production data.
- RLS policies must bind to a server-set session parameter or security-definer function populated only after `TenantPrincipal` derivation; callers cannot set arbitrary tenant scope.
- Cross-tenant analytics, if ever approved, must run only over redacted aggregate material through separate audited projections, never over raw tenant rows.
- Missing RLS, missing composite FK, unset tenant scope, stale lifecycle epoch, deleted tenant, or unknown object ID must fail closed.

### 4.5 OS/service identities, ACLs, and Keychain readers

- Hulagu must run under service identities separate from Hermes/Kublai operator profiles and separate from one another: at minimum `hulagu-app`, `hulagu-runner`, `hulagu-deletion-dispatcher`, plus offline migrator/backup identities.
- Kublai/Hermes operator identities must not have default recursive read access to Hulagu tenant roots. Human owner access is reserved for offline maintenance with receipts.
- Keychain items must name permitted readers per secret family. Tenant content encryption, route keys, database passwords, provider tokens, backup keys, and signing keys are separated by purpose.
- Runtime processes cannot read backup encryption keys or migrator credentials. Containers cannot read Keychain items.
- Logs, crash dumps, launchd plists, argv, environment dumps, and health reports must prove secret exclusion through tests.

### 4.6 Google Sheets and external artifact ownership

- Any Google Sheet created for a tenant must be created under a tenant-scoped service identity or folder/ACL namespace associated with the derived principal.
- Sheet IDs, Drive file IDs, folder IDs, and export IDs are not authority; each use must join the ID to the derived tenant principal and lifecycle epoch before access.
- No shared spreadsheet can contain multiple tenants unless a future approved aggregate-redaction ADR permits it; v4/G2 must assume one tenant-scoped Sheet/file namespace per tenant.
- Sheet ACLs must default private. Share operations require explicit tenant-principal authority, recipient validation, least-privilege role, expiration where supported, and a receipt stored inside the tenant root plus an approved redacted operator receipt when appropriate.
- Formula injection and CSV/Sheets export injection must be neutralized before export.

### 4.7 Operator projections into Kublai Brain

Kublai Brain may receive only these Hulagu projections:

- Aggregate health: counts, queue depths, error classes, latency buckets, gate status, and redacted incident state.
- Approved receipts: operator-reviewed events that contain no customer content, route identifiers, tenant UUIDs, direct file paths, sheet IDs, candidate names tied to a customer, or contact data.

Projection requirements:

- A machine-enforced schema must define allowed fields and maximum cardinality.
- A negative PII test suite must reject names, emails, phone numbers, addresses, Telegram handles, route IDs, tenant UUIDs, raw file paths, sheet/Drive IDs, CV text, profile answers, candidate bundles, and free-form model/provider output.
- The projection writer must be one-way and append-only/redacted; it cannot open tenant roots except through approved aggregate counters or approved receipts already sanitized by Hulagu.
- The Kublai Brain indexer/watcher/gateway denylist must explicitly exclude `/Volumes/KurultaiVault/hulagu/brain`, `/Volumes/KurultaiVault/hulagu/tenants`, Hulagu indexes, Hulagu backups, and any future mount alias.
- Public gateway routes must return denial for Hulagu Brain and tenant tree paths, even when asked through symlink, relative path, bind mount alias, file URL, raw SQLite, or index query.

### 4.8 Backups, restore, deletion, and tombstones

- Backups are encrypted and signed per tenant or per explicitly redacted product/operator scope. Backup manifests must record tenant UUID, lifecycle epoch, artifact digests, key IDs, schema version, and retention horizon without exposing plaintext.
- Restore tooling must restore into a quarantine location first, validate tenant UUID/lifecycle/schema/RLS/index/cache boundaries, then publish into the exact tenant root with same-volume atomic replace.
- Cross-tenant restore is forbidden unless a future owner-approved migration record maps the source tenant to the destination and proves no other tenant content is included.
- Deletion must revoke active route material, cancel queued work, delete tenant wiki/index/cache/export/sheet ACLs where possible, write tombstones, and prevent stale workers/restores from recreating data.
- Tombstones are tenant-scoped and retained separately from deleted content. They must be sufficient to reject replays without retaining deleted CV/profile/search content.
- Backup deletion/retention must respect tenant deletion policy and record redacted proof without leaking customer content to Kublai Brain.

### 4.9 Logs, crash dumps, temp files, diagnostics, and support/admin break-glass

- Logs and diagnostics must contain only correlation IDs, schema names, aggregate counts, redacted reason codes, and tenant-scoped opaque IDs where needed; raw customer text and paths are forbidden.
- Temporary files must be created under the tenant root or same encrypted vault with descriptor-confined publication; `/tmp`, `/var/tmp`, home-directory caches, and global application caches are forbidden for customer content.
- Crash dumps and exception reports must scrub payloads, paths, secrets, sheet IDs, route IDs, and tenant UUIDs before any operator projection.
- Support/admin access is denied by default. Break-glass requires explicit owner approval, reason, scope, time limit, dual receipt, least-privilege role, and post-session audit.
- Break-glass cannot grant cross-tenant search or global corpus access. Each support action still derives a principal and records a tenant-scoped receipt inside that tenant root.

### 4.10 Migration and quarantine for preexisting mixed data

Before v4 implementation/G2, any preexisting Hulagu-related data under Kublai Brain, shared indexes, global caches, global session memory, temporary directories, Google Drive/Sheets, or repository fixtures must be treated as suspect mixed data.

Required migration posture:

1. Inventory locations by allowlisted roots and denylisted high-risk roots without printing customer content.
2. Quarantine suspect artifacts under an owner-only encrypted quarantine root outside Kublai Brain and outside tenant roots.
3. Classify each artifact as product/operator-safe, tenant-specific, aggregate-redactable, or delete-only.
4. Move tenant-specific content only into the matching descriptor-created tenant root after deriving tenant identity from trusted server records.
5. Delete or quarantine artifacts whose tenant identity cannot be proven.
6. Rebuild tenant indexes/caches from tenant roots only; never import a global index/cache directly.
7. Record redacted migration receipts and negative projection tests before enabling any watcher/indexer/gateway.

### 4.11 Incident response and rollback

- Any suspected cross-tenant read/write/search/export/share/backup/delete, Kublai Brain indexing of Hulagu content, gateway publication, or shared-cache hit is a security incident.
- Immediate response: stop tenant-facing workers, disable projection writers, freeze backup/restore jobs, preserve redacted evidence, quarantine suspect artifacts, and rotate affected route/provider/database/cache keys as appropriate.
- Rollback from this ADR before implementation is documentation-only: revert this Markdown amendment and any dependent v4 incorporation. Rollback after implementation must preserve stricter isolation unless an approved successor ADR provides equal or stronger controls.
- If v4 cannot satisfy this ADR, G2 is blocked; do not implement customer-data paths.

## 5. Rejected alternatives

### Rejected: reuse Kublai Brain for Hulagu private/product notes

Even a private subdirectory under `/Users/kublai/brain` inherits existing watcher, index, public/private gateway, backup, and operator-memory assumptions. It is too easy for product notes, incident context, or future customer references to be indexed or projected. Hulagu needs a separate private product Brain root.

### Rejected: store customer wiki pages under the Hulagu product Brain

The product Brain is for product/operator knowledge only. Mixing tenant wiki pages into it would force every product search/index/backup/operator note to become tenant-sensitive and would recreate the original customer-content leakage risk.

### Rejected: one global customer corpus/index with tenant filters

Tenant filters on a shared corpus are not enough. Query bugs, index metadata leaks, embedding-neighbor leakage, cache-key mistakes, wildcard searches, and restore/delete races can cross tenants. The architecture requires one tenant-scoped corpus, index, embedding namespace, cache namespace, and wiki namespace per tenant.

### Rejected: path prefixes or caller-supplied tenant IDs as isolation

String-prefix checks, callback tenant IDs, user-provided paths, sheet IDs, export IDs, and model-provided object IDs are forgeable or can become stale. Tenant scope must be a typed server-derived principal enforced by filesystem descriptors, database constraints, adapter APIs, and tests.

### Rejected: symlinks, bind mounts, or indexer exceptions into Kublai Brain

Symlink/bind-mount shortcuts collapse the physical boundary and can bypass indexer/watch/gateway assumptions. Kublai Brain may receive only schema-validated redacted projections, never direct filesystem/index access.

## 6. Required negative test matrix before v4/G2 acceptance

The v4 incorporation must include automated tests that create at least two synthetic tenants, `tenant_a` and `tenant_b`, with synthetic-only data and prove all denial cases below. No real customer data may be used.

| Surface | Required negative tests |
|---|---|
| Filesystem | `tenant_a` cannot open/read/write/list/delete `tenant_b`; symlink/hardlink/bind-mount/path-traversal/device-file/special-file attempts fail; modes are `0700` dirs and `0600` files; temp files remain same tenant/same volume. |
| TenantPrincipal | caller-supplied tenant UUID/path/sheet/export/object ID is ignored or rejected; missing/malformed/multi-match/stale/deleted lifecycle scope fails closed before adapters run. |
| PostgreSQL | FORCE RLS enabled; composite FKs include `tenant_uuid`; unset or forged scope sees zero rows; cross-tenant FK/object-ID joins fail; stale lifecycle epoch and deleted tenant fail. |
| Brain roots | `/Users/kublai/brain` does not contain, watch, symlink, mount, index, or gateway-publish Hulagu Brain/tenant trees; Hulagu product Brain contains no customer fixtures; tenant wikis remain under tenant roots. |
| Full-text/vector indexes | `tenant_a` search cannot return `tenant_b`; no global corpus handle exists; wildcard/multi-tenant search rejected; index manifests are tenant-scoped. |
| Embeddings/cache/session memory | cache keys and directories are tenant/lifecycle scoped; `tenant_a` cannot hit `tenant_b` cache; session memory cannot mix tenants; global cache defaults rejected. |
| Google Sheets/Drive | sheet/file/folder IDs must join to derived principal; cross-tenant ID use denied; shared multi-tenant Sheet denied; ACL/share export requires explicit receipt and recipient validation. |
| Exports | export paths are tenant-confined; CSV/formula injection neutralized; cross-tenant export denied; approved redacted exports contain no disallowed identifiers. |
| Backups/restore | backup manifests are tenant-scoped; restore to wrong tenant denied; restore first lands in quarantine; global index/cache backup import denied; deleted tenant cannot be restored without approved policy. |
| Deletion/tombstones | deletion cancels work, removes tenant wiki/index/cache/export/sheet access where possible, writes tombstone, and prevents stale worker/restore/replay recreation. |
| Logs/crash dumps/temp diagnostics | synthetic PII, tenant UUIDs, routes, raw paths, sheet IDs, CV text, and secrets are absent from logs, crash dumps, health reports, and Kublai projections. |
| Operator projections | schema rejects free text/customer identifiers; aggregate health only; approved receipts are redacted; public gateway denial tested for direct path, symlink, bind alias, index query, and raw file URL. |
| Cross-system end-to-end | a synthetic `tenant_a` run followed by `tenant_b` search/export/delete/restore/support actions proves no cross-system leakage across FS, DB, indexes, caches, Sheets, backups, logs, and Kublai Brain. |

## 7. Allowed write set for this amendment task

This task's allowed write set is intentionally narrow:

- Create this Git-visible Markdown ADR under `docs/adr/`.
- Optionally add future review comments or a v4 incorporation link in a separate approved task.

This task must not:

- Edit the frozen v3 implementation plan.
- Edit the v3 freeze receipt.
- Mutate runtime vault directories, live Brain contents, live indexes, Keychain, PostgreSQL, Telegram, Google Sheets, customer data, credentials, gateway configuration, or service launch state.
- Contact users, share files, commit, push, or deploy.

## 8. Incorporation requirement

This ADR is a blocking security amendment. Hulagu v4 must incorporate it explicitly before any implementation/G2 work touches customer data paths. Incorporation is accepted only when:

1. The v4 plan names this ADR and preserves its three-zone root architecture.
2. The v4 plan includes implementation tasks for TenantPrincipal derivation, descriptor-confined tenant roots, per-tenant wiki/index/cache namespaces, PostgreSQL RLS/composite FKs, Kublai projection schema, Google Sheets/Drive ACL ownership, backup/restore isolation, deletion/tombstones, logs/crash-dump/temp controls, support break-glass, migration/quarantine, public-gateway denial, and the negative test matrix.
3. A reviewer approves the threat model and residual risks.

## 9. Residual risks

- A fully compromised trusted host or privileged human owner can still bypass local process and filesystem controls; this ADR reduces product/tenant/operator accidental and application-level leakage, not total host compromise.
- The `hulagu-app` trusted computing base remains sensitive because it derives principals and mediates adapters; implementation must keep it small and heavily tested.
- PostgreSQL RLS cannot protect against arbitrary SQL executed by a role with bypass privileges; privileged migrator/backup roles must stay offline and audited.
- Google Workspace/Sheets APIs have external ACL semantics that must be verified against real provider behavior at a later approved gate.
- Backup deletion and remote provider retention may be eventually consistent; receipts must distinguish requested, provider-confirmed, and retention-expired states.
- Aggregate health may still leak coarse usage patterns if cardinality is too low; projection schemas need k-anonymity/minimum-cardinality or suppression rules where necessary.
- Migration of preexisting mixed data can fail to prove tenant identity; unprovable artifacts must remain quarantined or be deleted rather than imported.
- This ADR is documentation/source-contract work only. It does not prove the runtime implementation, vault state, database policies, Keychain ACLs, Google ACLs, backup restore, deletion behavior, or gateway denial until later gates implement and test them.
