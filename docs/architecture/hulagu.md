# Hulagu architecture

Hulagu V2 is a dedicated deterministic Telegram product, not a Hermes profile. Its source-only G1 contracts live at `products/hulagu/`; later runtime claims require their own gates and evidence.

## Homes and boundaries

| Kind | Canonical home | Contract |
|---|---|---|
| Git-visible source | `/Users/kublai/kurultai/kurultai-repo/products/hulagu/` | Code, schemas, synthetic tests, read-only tools; no credentials or customer data |
| Product documentation | `docs/architecture/hulagu.md`, `docs/adr/2026-07-25-hulagu-dedicated-telegram-control-plane.md`, `docs/hulagu/THREAT-MODEL.md` | Public-safe architecture and security contracts |
| Private runtime root | `/Volumes/KurultaiVault/hulagu/` | Future mutable product data only after vault enrollment and later gate approval |
| PostgreSQL data | `/Volumes/KurultaiVault/hulagu/postgres/` | Future native PostgreSQL 16 `PGDATA`; Unix-socket only, not running at G1 |
| Tenant customer data | `/Volumes/KurultaiVault/hulagu/tenants/<tenant_uuid>/` | Quarantine, documents, immutable wiki generations, exports, receipts, and same-volume temporary files |
| Runtime state | `/Volumes/KurultaiVault/hulagu/run/`, `logs/`, `backups/` | Sockets, redacted logs, and encrypted backups; later-gated |
| Installation record | `/Users/kublai/Library/Application Support/Kurultai/Hulagu/install.json` | Future mode-`0600` owner-enrolled UUID, absolute container CLI/socket, executable identity, and image digests |
| Credentials | macOS Keychain, separate Hulagu items | Values never enter Git, Brain, plist, argv, database, fixture, container, or logs |
| Operator projection | `/Users/kublai/brain/status/hulagu/` and approved receipts under `/Users/kublai/brain/receipts/hulagu/` | Aggregate redacted health/proof debt only; no customer data |
| Change control | Existing Hermes Kanban, Buildroom, and Brain plans/receipts | Implementation, incidents, and proof debt only; customer jobs stay in the product database |

## Runtime decomposition (future gates)

`hulagu-app` owns the deterministic Telegram control plane, state machine, approved provider adapters, wiki/outbox, and fixed local deletion-send operation. Native PostgreSQL uses FORCE RLS and Unix sockets. `hulagu-runner` owns only fixed digest-pinned, networkless parser/ranker containers through an enrolled absolute engine contract. `hulagu-deletion-dispatcher` has only bounded deletion delivery authority. The three processes have separate database roles and secret-reader sets.

Raw CVs follow receive → dedupe → bounded stream/hash → type validation → tenant quarantine → networkless parser → normalization → `ParsedCv/v1` validation → persistence. Only validated structured fields may affect deterministic interview prompts. No model call is permitted on this path.

Exactly one separately gated research call may later receive only public company/listing fields. It receives no customer, tenant, Telegram, CV, profile, ranking, or customer-interest data; output is an untrusted schema-bound proposal.

## G1 state

Task 0 freezes source contracts only. The read-only doctor reports PostgreSQL and container runtime as `not_evaluated`; it does not convert absent runtime evidence into success. Vault writes, enrollment, services, provider calls, Telegram actions, credentials, deployment, and customer data remain forbidden.
