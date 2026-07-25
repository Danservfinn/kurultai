# Hulagu threat model — V1 source contract

## Protected assets

- Customer identity bindings, Telegram return routes, consent state, CV bytes and parsed facts.
- Tenant profiles, search plans/candidates/decisions, private wiki generations, exports, and receipts.
- PostgreSQL tenant/global-control integrity, queue fencing tokens, deletion tombstones, backups, and manifests.
- Bot/provider/database/key credentials and the integrity of owner-enrolled vault/container installation state.
- The private/public boundary: customer data must never enter Git, Brain projections, operator prompts, logs, or container diagnostics.

## Actors and trust boundaries

Trusted actors are the human owner, independent verifier, offline migrator/backup operator, and three future least-privilege processes: `hulagu-app`, `hulagu-runner`, and `hulagu-deletion-dispatcher`. Untrusted actors/data include Telegram senders, CV documents, parser/ranker output, public provider responses, URLs, filenames, and model-shaped instructions.

Trust boundaries exist at Telegram ingress; consent/identity promotion; typed credential adapters; PostgreSQL roles plus FORCE RLS; the owner-enrolled APFS vault; the absolute container CLI/Unix socket; networkless parser/ranker containers; schema validation; tenant filesystem confinement; and aggregate Brain projection. Containers and customer content are never authority. V1 makes no model calls.

## Abuse cases

- Forged/group/mismatched Telegram actors, update/callback replay, stale worker completion, and cross-tenant object IDs.
- prompt injection in a CV or provider result being interpreted as code, tools, paths, state transitions, or authority.
- Oversized/polyglot/macro/encrypted documents, archive traversal, symlink or hardlink escape, special-file output, and atomic-publication races.
- Missing or wrong volume UUID, unencrypted volume, low-space fallback, or temporary files crossing filesystems.
- Container PATH discovery, executable/socket drift, Docker socket or host-home mounts, network access, secret-bearing environment, and resource exhaustion.
- secret exposure through argv, environment dumps, plists, logs, crash-dump output, database rows, backups, receipts, Brain, or fixtures.
- Deletion races that recreate data, expose a route, or bypass a tombstone after key rotation/restore.

## Controls

- Private-DM principal validation, pinned bot identity, singleton polling, durable dedupe, versioned consent, nonces, and lifecycle/work epochs.
- Typed configuration and credential operations only; no arbitrary environment reads, generic secret getter, URL proxy, subprocess path, or PATH discovery.
- Owner-enrolled encrypted vault UUID, tenant-root descriptor/no-follow access, `0700` directories, `0600` files, quotas, and same-volume atomic replace.
- Dedicated PostgreSQL roles, FORCE RLS, narrow audited functions, immutable inputs, random fencing-token hashes, CAS completion, and durable receipts.
- Fresh digest-pinned, non-root, networkless, capability-free, bounded containers with schema-bound regular-file output and no Docker socket.
- Schema validation at every boundary, capped/redacted diagnostics, aggregate-only operator projection, retention, deletion fencing, signed manifests, and restore drills.
- Missing enrollment, key, executable, socket, vault identity, schema, owner, or gate fails closed. Safety failures cannot be waived.

## Secrets and rotation

Every item below is a named macOS **Keychain item**. The table freezes each **permitted reader**, distinct key family, stored **key ID**, rotation/overlap rule, missing-key/revocation test, and log/**crash-dump** exclusion. Plaintext is forbidden in environment dumps, argv, plists, repository files, fixtures, database rows, Brain, containers, and unencrypted backups.

| Secret family / Keychain item | Permitted reader | Separation and rotation contract |
|---|---|---|
| Telegram bot token — `hulagu.telegram.bot-token.v1` | `hulagu-app` | Distinct from Hermes tokens; pin bot ID first; rotate with bounded poller cutover, revoke old token, and test missing/revocation. |
| Search-provider token — `hulagu.search.provider-token.v1` | `hulagu-app` after provider gate | One approved adapter/purpose; no container reader; cut over key ID, revoke old token, test redacted failure. |
| PostgreSQL password: `hulagu_app` — `hulagu.pg.app.v1` | `hulagu-app` | No owner/migrator privileges; rotate SCRAM credential with bounded connection overlap and revoke old login secret. |
| PostgreSQL password: `hulagu_runner` — `hulagu.pg.runner.v1` | `hulagu-runner` | Function execution only; rotate independently and prove app/deletion roles cannot read it. |
| PostgreSQL password: `hulagu_deletion` — `hulagu.pg.deletion.v1` | `hulagu-deletion-dispatcher` | Deletion functions only; rotate independently and revoke prior key ID after bounded drain. |
| Subject-digest HMAC keys — `hulagu.identity.subject-hmac.<key-id>` | identity resolver in `hulagu-app` | Distinct from action tokens; overlap old/new lookup; re-key tombstones before revocation or retain old key only for privileged matcher horizon. |
| Action-token HMAC keys — `hulagu.action.hmac.<key-id>` | issuer/validator in `hulagu-app` | Short-lived nonces; never identity lookup; new issue uses current key ID, validation overlap ends after maximum TTL. |
| Deletion-send route-binding HMAC keys — `hulagu.route.binding-hmac.<key-id>` | fixed deletion-send validator in `hulagu-app` | Binds bot/route/generation; overlap only pending deletion jobs; revoke after rebind/drain test. |
| Active Telegram send-route encryption keys — `hulagu.route.active-kek.<key-id>` | sender/identity code in `hulagu-app` | Wrap active per-route data keys; dual-wrapper rewrap overlap; destroy active wrapper on deletion. |
| Deletion-completion route encryption keys — `hulagu.route.deletion-kek.<key-id>` | `hulagu-deletion-dispatcher` | Separate from active keys; finite route lifetime; rewrap pending jobs then revoke old key. |
| Backup encryption keys — `hulagu.backup.encryption.<key-id>` | offline backup/restore operator only | Absent from all runtime processes/containers; restore-read overlap, explicit retirement after retained backups expire. |
| Backup-manifest signing keys — `hulagu.backup.signing.<key-id>` | offline backup/restore operator/verifier only | Separate from encryption/runtime; verify old manifests during retention, sign new manifests only with active key ID. |
| Offline migrator credential — `hulagu.pg.migrator.v1` | owner-invoked offline migrator only | Absent from app/runner/deletion environments and launchd; rotate out of band and test runtime denial. |

Rotation evidence must record only key IDs, timestamps, overlap state, and redacted outcomes. Each family requires explicit missing-key, revoked-key, old/new overlap, new-write/current-key, log exclusion, and crash-dump exclusion tests before G3/G4 as applicable.

## Residual risks

- Total trusted-host or `hulagu-app` compromise can expose credentials held by that process; mediation is not a host-compromise sandbox.
- Telegram send success can be remotely accepted while the response is lost, so bounded retries may produce a visible duplicate.
- RLS does not contain arbitrary SQL executed with an application role; repository/query authority remains part of the declared TCB.
- Parser coverage, APFS/container behavior, native PostgreSQL, Keychain reader separation, backup/restore, and bot/provider behavior remain proof debt until their named later gates.
- Public job facts can be stale or wrong; generated prose is not existence/open-status proof.

## Explicitly out of scope

V1 has no job applications, no employer contact, no recruiter messaging, no authenticated browsing, no logins, no payments, no social posting, no CAPTCHA/paywall/access-control bypass, no unrestricted browser/terminal/host filesystem, no general-purpose agent tools, no public customer wiki, no recurring search automation, and no model calls. Any such capability requires a separate threat model and G0 approval.
