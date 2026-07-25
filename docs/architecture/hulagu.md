# Hulagu architecture

## Homes and ownership

| Home | Canonical location | Contract |
|---|---|---|
| Git-visible source home | `/Users/kublai/kurultai/kurultai-repo/products/hulagu` | Code, schemas, synthetic tests, QA contracts, and deploy templates only. |
| Private runtime home | `/Volumes/KurultaiVault/hulagu` | All mutable product state; writes fail closed unless the owner-enrolled volume UUID and encryption state match. |
| Credential home | `macOS Keychain` | Named, versioned items with process-specific readers; never repository, environment dumps, argv, plists, Brain, or containers. |
| Customer-data home | `/Volumes/KurultaiVault/hulagu/tenants/<tenant_uuid>` | Tenant quarantine, documents, wiki generations, exports, receipts, and same-volume temporary files. |
| Database home | `/Volumes/KurultaiVault/hulagu/postgres` | Future native PostgreSQL 16 PGDATA; not created or evaluated at G1. |
| Runtime socket home | `/Volumes/KurultaiVault/hulagu/run` | Future PostgreSQL and bounded local operation sockets; not created at G1. |
| Aggregate operator-projection home | `/Users/kublai/brain/status/hulagu` | Aggregate redacted `index.md` and `health.json` only. |
| Approved operator-receipt home | `/Users/kublai/brain/receipts/hulagu` | Only operator-approved, redacted receipts; never customer content. |

There is one Git-visible product home. Customer jobs are product database state, not Hermes Kanban. Brain receives aggregate, redacted projections only and is never a customer-data mirror.

## G1 source boundary

Task 0 freezes schemas, typed configuration, threat model, plan gate, and observation-only environmental probes. It performs no vault write, executable discovery through `PATH`, network request, credential access, PostgreSQL/container start, bot/provider call, or service mutation. PostgreSQL and container runtime execution remain `not_evaluated` until separately approved G2 evidence.

## Future process boundaries (not implemented at G1)

The approved design separates `hulagu-app`, `hulagu-runner`, and `hulagu-deletion-dispatcher`, with separate PostgreSQL roles and credential readers. The app owns deterministic Telegram ingress but no container access; the runner owns only the enrolled absolute container contract and no Telegram/search secrets; the deletion dispatcher has a narrow completion route and no general messaging authority.

See [the dedicated control-plane ADR](../adr/2026-07-25-hulagu-dedicated-telegram-control-plane.md) and [the threat model](../hulagu/THREAT-MODEL.md).
