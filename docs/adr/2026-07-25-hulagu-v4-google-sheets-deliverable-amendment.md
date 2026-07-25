# ADR: Hulagu v4 Google Sheets per-customer deliverable amendment

- Date: 2026-07-25
- Status: Proposed v4 amendment; blocks G2/runtime implementation until independently reviewed and owner-approved
- Amends: `/Users/kublai/brain/docs/plans/2026-07-25-kublai-hulagu-job-search-agent-implementation-plan-v3.md` by addition only
- Incorporates: `docs/adr/2026-07-25-hulagu-dedicated-brain-hard-tenant-isolation.md` at SHA-256 `6b82c574d47139ee849b02b3b6b4c3cae3dd08d8f9237c9ef303c0d3d136f8a2`
- Scope: source-contract/security architecture only; no live Google API calls, no Drive/Sheets scope provisioning, no runtime mutation, no customer contact, no commit, no push
- Canonical structural reference: Google spreadsheet ID `1-mLmR6UfYp9F8Ks6gT4ob_sf0JVuesIM7YaU5y2nGEs`; this amendment MUST NOT read or copy any live cells, tabs, comments, notes, hidden sheets, formulas, named ranges, private values, ACLs, revision history, or Drive metadata from that spreadsheet
- Sanitized blank template artifact: `products/hulagu/templates/google_sheets/job_ops_blank_template_v4.csv`
- Sanitized blank template manifest: `products/hulagu/templates/google_sheets/job_ops_blank_template_v4.manifest.json`

## 1. Threat model first

### 1.1 Protected assets

- Customer CV bytes, parsed CV facts, interview answers, work-authorization constraints, preference counters, candidate decisions, and customer notes.
- Tenant identity bindings, Telegram subject digests, lifecycle epochs, route keys, action nonces, Google account confirmations, spreadsheet IDs, Drive file IDs, folder IDs, ACL receipts, idempotency keys, and deletion tombstones.
- Per-tenant private wiki, full-text index, vector index, embeddings cache, retrieval cache, model/session cache, exports, backups, logs, crash dumps, and temporary files.
- The dedicated private Hulagu product Brain root and every per-tenant wiki/index/cache root mandated by `docs/adr/2026-07-25-hulagu-dedicated-brain-hard-tenant-isolation.md` SHA-256 `6b82c574d47139ee849b02b3b6b4c3cae3dd08d8f9237c9ef303c0d3d136f8a2`.
- Kublai Brain and its public/private indexes/gateway, which must never receive customer content, tenant UUIDs, spreadsheet IDs, Drive IDs, route identifiers, direct paths, candidate/customer names tied to a tenant, or Google account identifiers.
- The canonical Job Ops spreadsheet identified by `1-mLmR6UfYp9F8Ks6gT4ob_sf0JVuesIM7YaU5y2nGEs`. It is a structural reference only; its live contents and metadata are protected by a non-read/non-copy rule for this amendment and for template generation.

### 1.2 Adversaries and unsafe inputs

- Malicious or confused Telegram users, group participants, replayed callbacks, stale workers, unapproved support/admin operators, and any caller that supplies a tenant ID, sheet ID, Google account, row ID, URL, or object ID as authority.
- Spreadsheet-specific injection: formula injection, CSV injection, hidden formula behavior, IMPORTRANGE/IMAGE/HYPERLINK/Apps Script pivots, named-range spoofing, protected-range confusion, hidden sheet leakage, comments/notes leakage, filter-view leakage, and revision-history leakage.
- Provider/model/search output that smuggles another tenant's identifiers, private values, row formulas, Drive IDs, or instructions to alter sharing, outbox, retention, deletion, or logs.
- Bugs that reuse a spreadsheet across tenants, derive tenant scope from a sheet URL, populate rows before principal checks, send a Telegram URL before ACL/readback, log sheet identifiers to Kublai Brain, or retain Google ACLs after deletion.
- OAuth or service-account misconfiguration that grants broad Drive access, allows the wrong principal to create/share sheets, or exposes canonical/template/private folders to customer tenants.
- Quota/rate-limit/outage ambiguity where a create/populate/share/readback request may have succeeded remotely but local state does not know it.

### 1.3 Trust boundaries

- Telegram ingress is only a source for trusted identity after pinned bot/private-DM validation; it is not spreadsheet authority.
- Every Google Sheets/Drive operation starts from a server-derived typed `TenantPrincipal` tied to trusted identity, lifecycle epoch, consent state, deletion state, and support authority.
- PostgreSQL is the authority for tenant-to-spreadsheet bindings, idempotency keys, row versions, outbox gates, lifecycle epochs, and customer-confirmed Google account records.
- Filesystem authority remains descriptor-confined under `/Volumes/KurultaiVault/hulagu/tenants/<server-derived-tenant_uuid>/`; template and receipt files under tenant roots are not looked up by caller-provided paths.
- Google artifact authority is never the sheet ID alone. Sheet/Drive/folder/permission IDs are opaque remote handles that must join to the derived principal and current lifecycle epoch before use.
- Telegram notification is last-mile delivery only. It may send a Sheet URL only after content, ACL, URL, tenant, idempotency, and revision/readback gates pass.

### 1.4 Non-negotiable invariants

1. Hulagu v4 MUST keep the dedicated private Hulagu Brain/wiki root separate from `/Users/kublai/brain` and all existing Brain indexes/gateways.
2. Each customer tenant MUST have separate wiki, full-text index, vector index, embeddings cache, retrieval cache, model/session cache, exports, backups, Google spreadsheet, and Google artifact receipts under a server-derived tenant UUID.
3. No shared customer corpus, vector store, full-text index, sheet, session cache, artifact cache, or Google file namespace may contain multiple tenants.
4. Customer data MUST NOT enter Kublai Brain, public gateway, existing Brain indexes, normal operator prompts, Git fixtures, source docs, or aggregate health.
5. The canonical spreadsheet ID `1-mLmR6UfYp9F8Ks6gT4ob_sf0JVuesIM7YaU5y2nGEs` may be recorded only as an external structural reference; no live cell/tab/formula/comment/note/hidden-sheet/named-range/ACL/history/file metadata read is allowed without a future explicit owner-approved provider gate.
6. A Google Sheet URL MUST NOT be sent through Telegram until Hulagu has read back: content row count/digests, ACL recipient/role, spreadsheet URL, tenant binding, idempotency key, and remote file/spreadsheet IDs joined to the derived principal.
7. Missing scopes, missing Google credentials, ambiguous API outcomes, quota failures, stale lifecycle epochs, deletion states, wrong recipients, or readback mismatches fail closed before share or Telegram outbox.

## 2. Decision

Hulagu v4 adds Google Sheets as the primary per-customer deliverable, paired with the private per-tenant wiki. The Sheet is a customer-facing operational workspace derived from Hulagu's canonical candidate/result state, not from the operator Brain and not from the live canonical Job Ops spreadsheet contents.

The deliverable shape is:

- one Google spreadsheet per tenant;
- one primary Job Ops tab per tenant spreadsheet;
- tenant spreadsheet title generated from a non-sensitive tenant-local display alias plus run/generation information, never from customer full name/CV text/Telegram handle by default;
- header-only sanitized blank template generated in source control, with no private sample rows;
- rows populated only from the tenant's server-authoritative candidate/result state after `TenantPrincipal` derivation and RLS checks;
- a tenant-root receipt/manifest recording source digests, template version, Google file IDs, sheet/tab IDs, ACL IDs, idempotency key, row count, row digest, URL readback, lifecycle epoch, retention horizon, and deletion/revocation status;
- Telegram delivery only through the durable outbox after readback confirms the customer-confirmed Google account has exactly the intended least-privilege access.

## 3. Sanitized blank template artifact and manifest

This amendment creates the following Git-visible source artifacts:

- `products/hulagu/templates/google_sheets/job_ops_blank_template_v4.csv`
- `products/hulagu/templates/google_sheets/job_ops_blank_template_v4.manifest.json`

The CSV is intentionally header-only. It contains no live rows, no private values, no formulas, no named ranges, no comments, no notes, no hidden sheets, no ACLs, no revision history, and no copied structure from a live Google Sheet API response.

The manifest's derivation mode is `domain-structural only`. It records the canonical spreadsheet ID `1-mLmR6UfYp9F8Ks6gT4ob_sf0JVuesIM7YaU5y2nGEs` only to preserve the product reference requested by the owner. The implementation MUST treat this ID as documentation, not as a read target, copy target, template source, ownership proof, or ACL authority.

Future template changes require a new manifest version, exact artifact digests, and review proving that no live canonical cells or private rows were copied.

## 4. Dedicated Brain and tenant-root incorporation

This amendment explicitly incorporates the exact-hash parent output:

- ADR path: `docs/adr/2026-07-25-hulagu-dedicated-brain-hard-tenant-isolation.md`
- SHA-256: `6b82c574d47139ee849b02b3b6b4c3cae3dd08d8f9237c9ef303c0d3d136f8a2`

Hulagu v4 MUST implement the following roots before any Sheets runtime path can claim GREEN:

| Zone | Canonical root | Sheets-specific rule |
|---|---|---|
| Kublai operator Brain | `/Users/kublai/brain` plus existing indexes/gateway | May receive only aggregate redacted health and approved receipts that exclude customer content, tenant UUIDs, Drive/Sheet IDs, Google accounts, URLs, and direct paths. |
| Hulagu product/operator Brain | `/Volumes/KurultaiVault/hulagu/brain` | Product runbooks, sanitized operator incidents, and approved internal receipts only; no customer rows, sheet IDs, tenant UUID maps, Google accounts, or candidate bundles. |
| Hulagu tenant root | `/Volumes/KurultaiVault/hulagu/tenants/<server-derived-tenant_uuid>/` | Tenant wiki, indexes, caches, exports, Sheets manifests, ACL receipts, URL readback receipts, row digests, deletion tombstones, backups, and customer artifacts. |

No Google Sheets cache, session memory, export staging directory, outbox state, template instance, or receipt may use a global customer namespace. Per-tenant roots MUST be derived from a typed server-side principal, not from Telegram text, callback data, sheet names, sheet URLs, Drive IDs, customer-provided Google accounts, model output, or operator prose.

## 5. Tenant principal, RLS, and artifact binding

### 5.1 Server-derived tenant binding

Every create/populate/share/readback/delete/revoke operation MUST begin by deriving a `TenantPrincipal` from trusted identity and server state:

1. Validate pinned Hulagu bot identity and private-DM subject, or validate a separately approved support/admin break-glass session.
2. Resolve exactly one active tenant UUID and lifecycle epoch.
3. Verify consent, non-deleted state, current profile/run authority, and feature gate for Sheets delivery.
4. Attach the typed principal to repository, filesystem, Sheets/Drive, outbox, backup, and deletion adapters.
5. Reject any caller-supplied tenant UUID, sheet ID, spreadsheet URL, row ID, Drive folder ID, Google account, or object ID until it joins to the derived principal in PostgreSQL.

### 5.2 PostgreSQL/RLS requirements

PostgreSQL MUST be the source of truth for Google artifact state. Tenant-owned tables MUST include `tenant_uuid` and, when lifecycle-sensitive, `tenant_lifecycle_epoch`. Composite foreign keys MUST include `tenant_uuid`. FORCE RLS MUST be enabled before production data.

Minimum logical tables for v4:

- `tenant_google_accounts`: confirmed Google account hash, verification method, confirmation nonce, lifecycle epoch, status, timestamps.
- `tenant_sheet_artifacts`: tenant UUID, lifecycle epoch, spreadsheet ID, Drive file ID, folder ID if used, template version/digest, title digest, current generation ID, status, retention/deletion state.
- `tenant_sheet_tabs`: tenant UUID, artifact ID, sheet/tab ID, schema version, header digest, row count, row digest, current row version.
- `tenant_sheet_permissions`: tenant UUID, artifact ID, permission ID, recipient hash, role, expiration where supported, readback digest, revocation state.
- `tenant_sheet_outbox`: tenant UUID, artifact ID, idempotency key, URL digest, expected artifact version, send state, retry budget.
- `tenant_sheet_receipts`: tenant UUID, lifecycle epoch, redacted event type, local/remote state digests, error class, timestamp, retention horizon.

Rows containing Google accounts, sheet/file IDs, URL digests, and permission IDs are tenant-private data. They MUST NOT be projected to Kublai Brain or aggregate health except as cardinality-safe redacted counts and error classes.

## 6. Restricted customer-confirmed Google account

Hulagu MUST share the Sheet only with a customer-confirmed Google account. Confirmation requires:

- the Telegram-authenticated tenant asks to add or change a Google account;
- Hulagu displays the exact normalized account value back to the customer in Telegram and binds it to a single-use nonce;
- the customer confirms the nonce;
- Hulagu stores a hash/redacted display value in tenant state and marks any old unshared/pending artifacts stale;
- no share occurs if the account is missing, malformed, recently changed without reconfirmation, attached to another active tenant without explicit safe policy, or under deletion/revocation.

Customer-provided email text is not authority for tenant scope. It is only the intended Google recipient after Telegram identity has already produced a valid `TenantPrincipal`.

## 7. OAuth vs service account least privilege

Hulagu v4 MUST choose one approved Google integration pattern before G4/G5 and document it in a follow-up implementation ADR or runbook:

| Option | Least-privilege requirement | Required rejection conditions |
|---|---|---|
| Owner OAuth desktop/user credential | Scopes limited to create/manage Hulagu-owned Sheets/Drive files needed for tenant deliverables; token readable only by `hulagu-app`; no broad operator Drive browsing in runtime code. | Missing Drive/Sheets scopes, token subject mismatch, inability to confine folder/file ownership, broad read APIs used for canonical template copying, token visible to runner/deletion/container. |
| Service account / Workspace-owned bot identity | Dedicated Hulagu service identity; restricted Drive folder/ACL namespace; domain/admin controls if needed; no access to Kublai Brain or personal Drive by default. | Domain policy prevents intended customer shares, service identity can enumerate unrelated Drive files, folder namespace not bound to tenant, credentials visible outside `hulagu-app`. |

Current Kublai token lacks Drive/Sheets scopes. This task MUST NOT inspect/provision auth, mutate runtime credentials, create folders, copy spreadsheets, share files, contact customers, commit, or push.

## 8. Create/populate/share/readback/outbox state machine

The runtime state machine MUST be fenced, idempotent, and restart-safe. Allowed states:

1. `SHEETS_DISABLED`: feature gate off or no approved Google provider configuration.
2. `ACCOUNT_REQUIRED`: tenant has no confirmed Google account.
3. `ACCOUNT_CONFIRM_PENDING`: normalized account displayed through Telegram; nonce pending.
4. `ACCOUNT_CONFIRMED`: account hash and confirmation event stored for current lifecycle epoch.
5. `CREATE_REQUESTED`: idempotency key reserved; no remote mutation yet.
6. `CREATE_IN_FLIGHT`: create call may be ambiguous; retry uses the same idempotency/local artifact record and provider-safe duplicate detection.
7. `CREATED_READBACK_PENDING`: spreadsheet/file IDs stored; title, URL, owner/folder, and blank tab/header readback pending.
8. `POPULATE_REQUESTED`: row source digests and expected generation recorded.
9. `POPULATE_IN_FLIGHT`: write/update may be ambiguous; retries are fenced by artifact ID, generation ID, row version, and idempotency key.
10. `CONTENT_READBACK_PENDING`: readback verifies header digest, row count, row digest, formulas absence where expected, tab ID, and spreadsheet modified state.
11. `SHARE_REQUESTED`: intended recipient hash, role, and expiration where supported recorded.
12. `SHARE_IN_FLIGHT`: permission call may be ambiguous; retries check existing permission joined to intended recipient/role only.
13. `ACL_READBACK_PENDING`: readback verifies exactly intended recipient/role and no broader link/domain/public permission.
14. `URL_READBACK_PENDING`: readback verifies canonical URL, spreadsheet ID, Drive file ID, tenant binding, and idempotency key.
15. `READY_FOR_TELEGRAM_OUTBOX`: content+ACL+URL+tenant+idempotency readbacks passed.
16. `TELEGRAM_OUTBOX_QUEUED`: bounded outbox row created with URL digest and expected artifact version.
17. `TELEGRAM_DELIVERED` / `DELIVERY_UNKNOWN` / `DELIVERY_FAILED`: at-least-once Telegram semantics recorded.
18. `REVOKE_REQUESTED` / `REVOKED_READBACK_PENDING` / `REVOKED`: sharing revoked by customer request, account change, deletion, retention expiry, or incident response.
19. `DELETE_REQUESTED` / `DELETED_REMOTE_UNKNOWN` / `DELETED_CONFIRMED`: remote file trash/delete outcome recorded; local tenant deletion continues even if provider deletion is eventually consistent.
20. `ERROR_RETRY_WAIT` / `ERROR_NEEDS_OPERATOR` / `QUOTA_WAIT`: bounded retry/outage states with no Telegram URL send until readback gates pass.

Every transition MUST check tenant lifecycle epoch, deletion state, expected artifact version, and the random attempt/fencing token where asynchronous work is involved. Duplicate callbacks or retries return current state without applying a second effect.

## 9. Population contract and exact allowed write set

### 9.1 Allowed Google write set

The v4 runtime MAY perform only these Google mutations after gates pass:

- create one new tenant-owned spreadsheet from the sanitized blank template shape;
- create or rename one primary tenant Job Ops tab in that tenant spreadsheet;
- write the approved header row from the current template version;
- write/update rows derived from the tenant's current candidate/result state and customer-visible decisions;
- apply non-sensitive formatting/protection needed to preserve header/row schema, if it can be generated locally without copying live canonical formatting;
- create one least-privilege permission for the current customer-confirmed Google account;
- revoke/delete/trash the tenant spreadsheet or permission during account change, deletion, retention expiry, incident response, or owner-approved cleanup.

### 9.2 Forbidden Google/source writes and reads

The v4 runtime and template process MUST NOT:

- read, copy, export, or duplicate live cells from canonical spreadsheet `1-mLmR6UfYp9F8Ks6gT4ob_sf0JVuesIM7YaU5y2nGEs`;
- read/copy comments, notes, hidden sheets, formulas, named ranges, protected ranges, private values, ACLs, revision history, Drive metadata, owners, or file activity from the canonical spreadsheet;
- store multiple tenants in one spreadsheet or folder namespace without a future owner-approved aggregate-redaction ADR;
- use Google sheet names, URLs, file IDs, folder IDs, named ranges, comments, notes, or row IDs as tenant authority;
- write raw CV text, work-authorization details, compensation if not explicitly customer-provided for display, Telegram IDs, customer full names by default, route IDs, tenant UUIDs, internal candidate IDs with cross-tenant meaning, or provider secrets to a Sheet;
- create Apps Script, external data connectors, IMPORTRANGE, IMAGE, HYPERLINK formulas, public-link sharing, domain-wide sharing, or anyone-with-link permissions in V1;
- export Sheets into Kublai Brain, Git, source fixtures, public gateway paths, or global logs.

### 9.3 Customer edits and ownership

The customer may edit their copy only within documented editable fields after sharing. Hulagu remains authoritative for server state. Customer edits are treated as untrusted external input and require explicit import/reconcile behavior before they affect future searches.

V1 SHOULD make the Sheet customer-readable/commentable by default unless owner-approved product policy grants writer access. If writer access is approved, tests MUST prove that customer-edited formulas, hidden rows, comments, and notes cannot alter tenant scope, server state, future outbox sends, or other tenants. Importing customer edits is gated-later unless a specific field-level import contract and tests are added.

## 10. Audit, logging, and redaction

Logs and receipts MAY contain:

- schema version, redacted event type, opaque local artifact ID, row count, byte count, digest prefixes, retry count, provider error class, bounded latency bucket, and lifecycle epoch comparison outcome;
- cardinality-safe aggregate counts in approved operator health.

Logs and receipts MUST NOT contain:

- raw candidate rows, CV text, profile answers, Google account addresses, spreadsheet URLs, Drive/Sheet IDs, permission IDs, tenant UUIDs, Telegram IDs, customer names, row values, formulas, comments, notes, hidden-sheet names, source URLs tied to a customer, or provider secrets.

Crash dumps, exception reprs, HTTP traces, request/response bodies, OAuth token metadata, argv, environment dumps, plists, and test fixtures must pass negative scans for these fields. Any redacted operator projection into Kublai Brain must pass the projection schema and negative PII tests from the hard-isolation ADR.

## 11. Retries, quota, outage, and ambiguous remote outcomes

All Google operations have bounded retry budgets and must distinguish:

- `not_attempted`: safe to start;
- `attempt_started`: provider request may have reached Google;
- `remote_confirmed`: readback verified the intended object/effect;
- `remote_absent`: readback proved absence for the intended principal/idempotency key;
- `remote_ambiguous`: quota/outage/network failure prevents proof;
- `remote_mismatch`: Google state exists but does not match intended tenant/recipient/version and requires operator incident handling.

Ambiguous create/populate/share/revoke/delete states MUST NOT be normalized by creating a second spreadsheet, second permission, or second Telegram URL unless idempotency readback proves the earlier attempt did not create the intended object. Quota waits must keep `/status`, `/delete`, revocation, and incident response paths available where possible.

## 12. Deletion, revocation, retention, and backup behavior

Customer deletion MUST:

1. increment lifecycle epoch and stop ordinary claims/outbox before any Google mutation;
2. revoke or delete/trash tenant Sheet permissions and file where possible;
3. record `requested`, `confirmed`, `unknown`, or `eventual_retention` states without leaking URL/account/file IDs to operator projections;
4. delete tenant-local row digests, manifests, URL receipts, ACL receipts, exports, wiki/index/cache artifacts, and backups according to the approved retention policy;
5. retain only schema-bounded deletion tombstones/receipts needed to reject replay and honor backup windows;
6. prevent stale workers from recreating Sheets, permissions, or Telegram URLs after deletion.

Account change MUST revoke the old permission before sharing to a new account unless provider outage forces an `ERROR_NEEDS_OPERATOR` state. Retention expiry MUST revoke or delete/trash remote artifacts where supported, then remove local tenant artifacts after receipt.

Backups MUST include tenant-local Sheets manifests and redacted remote-state receipts only as tenant-scoped private data. Restore must replay deletion tombstones before any Sheet or Telegram outbox worker can run.

## 13. Migration and rollback

### 13.1 Migration

Before enabling v4 Sheets delivery:

- inventory source-visible template files and runtime tenant roots by allowlisted paths only;
- quarantine any preexisting Google/CSV/Sheet artifacts whose tenant identity, lifecycle epoch, source digest, or no-live-copy provenance cannot be proven;
- never import global Sheets, global CSV caches, canonical workbook exports, or Kublai Brain notes as tenant data;
- create new tenant spreadsheets from the sanitized v4 template instead of copying canonical live spreadsheets;
- record per-tenant migration receipts under the tenant root and only aggregate redacted migration counts in operator Brain.

### 13.2 Rollback

Before a release, verify current/N-1 compatibility for Google artifact schema versions, outbox rows, pending share/revoke/delete jobs, template manifests, row digests, and deletion jobs. Rollback order:

1. stop Telegram URL sends;
2. pause Google create/populate/share workers;
3. preserve PostgreSQL and tenant-root manifests;
4. revoke any newly unsafe permissions if rollback changes ACL semantics;
5. start N-1 only if it can read or safely ignore v4 Sheet artifact states;
6. leave ambiguous remote outcomes in `ERROR_NEEDS_OPERATOR` rather than sending URLs.

Rollback from this amendment before runtime implementation is documentation-only: revert this Markdown file and the two sanitized template artifacts. Rollback after implementation MUST preserve tenant isolation, revocation, and deletion semantics unless an approved successor ADR is equal or stronger.

## 14. Synthetic and gated live E2E

### 14.1 Synthetic tests required before G3

A two-tenant synthetic suite MUST prove:

- tenant A cannot create/populate/share/readback/revoke/delete tenant B's spreadsheet by supplying tenant B's sheet ID, URL, folder ID, permission ID, row ID, Google account, callback data, or object ID;
- no shared spreadsheet or shared folder namespace contains both tenants;
- row digests and source digests are tenant-scoped and lifecycle-bound;
- formula/CSV injection strings are neutralized and remain literal display data;
- customer-edited formulas/comments/notes/hidden rows cannot affect server state or another tenant;
- public-link/domain-wide sharing is rejected;
- wrong Google recipient readback blocks Telegram URL send;
- content mismatch, ACL mismatch, URL mismatch, tenant mismatch, idempotency mismatch, stale lifecycle epoch, and deletion state all fail closed;
- ambiguous quota/outage retry never duplicates remote artifacts or sends unverified URLs;
- deletion/revocation prevents stale workers from recreating files, permissions, or outbox sends;
- Kublai Brain, public/private indexes, gateway, logs, crash dumps, fixtures, and source repository contain no customer rows, Google account addresses, sheet IDs, Drive IDs, URLs, tenant UUIDs, or candidate/customer names tied to a tenant.

### 14.2 Gated live E2E

No live Google API E2E may run before owner approval for the exact credential mode, scope set, account/folder namespace, test bot, synthetic tenant, and rollback plan. The live E2E must use synthetic rows only and prove:

1. create blank tenant spreadsheet;
2. populate synthetic rows;
3. read back row/header digests;
4. share to an owner-controlled test Google account;
5. read back ACL/URL/file IDs through tenant binding;
6. send a Telegram URL only after readbacks pass;
7. revoke permission;
8. delete/trash the artifact where policy allows;
9. verify no disallowed identifiers entered Kublai Brain/logs/source fixtures.

A single consented human pilot remains G5 and must not use the canonical spreadsheet as a live template or data source.

## 15. Test matrix

| Surface | Minimum required tests |
|---|---|
| Template provenance | Header-only template and manifest hashes stable; no live canonical reads; no formulas/comments/notes/hidden sheets/named ranges/ACL/history/private values. |
| TenantPrincipal | Missing/forged/caller-supplied tenant, sheet URL, Drive ID, row ID, Google account, or support authority rejected before adapter calls. |
| PostgreSQL/RLS | FORCE RLS; composite tenant FKs; unset/forged scope sees no rows; cross-tenant artifact joins fail; stale lifecycle/deleted tenant fail. |
| Sheets create | One spreadsheet per tenant; title/path sanitized; no canonical copy; idempotent retry; ambiguous create does not duplicate. |
| Populate | Allowed fields only; row/header digest readback; formula injection neutralized; no raw CV/private rows; stale generation/lifecycle blocked. |
| Share/ACL | Restricted customer-confirmed Google account only; intended role; no anyone/domain/public link; wrong recipient/role/readback blocks URL. |
| Telegram outbox | URL sent only after content+ACL+URL+tenant+idempotency readback; at-least-once semantics; duplicate send bounded and state-queryable. |
| Customer edits | Edits/comments/notes/formulas cannot become authority; import disabled or field-gated; ownership semantics documented. |
| Logs/projections | Negative scans reject Google accounts, URLs, Drive/Sheet/permission IDs, tenant UUIDs, CV/profile/candidate rows, raw paths, provider secrets. |
| Quota/outage | Retry budgets; remote ambiguity states; status/delete/revoke paths remain available; no unverified URL. |
| Deletion/retention | Revoke/delete/trash receipts; stale worker denial; tombstones; backup restore does not resurrect Sheets or permissions. |
| Migration/rollback | Quarantine unknown artifacts; no global/canonical import; N-1 compatibility; permission revocation on unsafe rollback. |
| Cross-system E2E | Two synthetic tenants prove isolation across FS, DB, indexes, caches, Sheets, backups, logs, Brain, Telegram, and restore. |

## 16. Allowed write set for this amendment task

This source-contract task may write only:

- this Markdown ADR under `docs/adr/`;
- `products/hulagu/templates/google_sheets/job_ops_blank_template_v4.csv`;
- `products/hulagu/templates/google_sheets/job_ops_blank_template_v4.manifest.json`;
- Kanban receipts/comments.

This task must not edit the frozen v3 plan, edit the v3 freeze receipt, inspect/provision Google auth, call Google Drive/Sheets APIs, mutate runtime vault directories, create/share/delete Google files, contact customers, alter Telegram, alter PostgreSQL, alter Keychain, alter live Brain contents/indexes/gateways, commit, push, or deploy.

## 17. Incorporation requirement

Hulagu v4 is accepted only when it names this ADR, the hard tenant-isolation ADR, and their exact hashes in the plan/review receipt; implements dedicated private Hulagu Brain and per-tenant roots; adds the Sheets state machine and RLS-backed artifact binding; verifies the complete test matrix; and receives owner approval for any live Google credential/provider gate.

If the v4 plan cannot satisfy this amendment without reading/copying canonical live cells or without hard per-tenant isolation, G2/runtime implementation is blocked.

## 18. Residual risks

- Google Workspace ACL and revision-history behavior is external provider behavior and remains proof debt until a gated live E2E verifies it.
- Owner OAuth can accidentally expose broader Drive authority if scopes or runtime code are too broad; least-privilege tests and code review are mandatory.
- A compromised `hulagu-app` can misuse credentials it legitimately holds; the TCB must remain small and audited.
- Customer-granted writer access can introduce unexpected formulas/comments/hidden rows; default should remain read/comment unless a stronger import contract is approved.
- Provider quota/outage ambiguity can delay deletion/revocation proof; receipts must distinguish requested, confirmed, unknown, and retention-expired states.
- Total trusted-host or privileged human owner compromise can bypass local controls; this amendment targets product/application/operator-boundary failures.
