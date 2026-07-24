# ADR: Solution Graph Phase 2 remains bounded and read-only

Date: 2026-07-24
Status: accepted

## Context

Phase 0/1 proved deterministic offline selection for a single fixture family. The next useful increment needs composition, real runtime enforcement of the published schemas, and agent-facing interfaces. Those additions can accidentally create combinatorial search, execution authority, network exposure, or a parallel coordination system.

## Decision

### Composition

Preserve `ObjectiveSpec/v1` as a single-complete-artifact resolver. Add `ObjectiveSpec/v2`, `ResolutionPlan/v2`, and `AgentContextPacket/v2` for typed composition only. V2 search is deterministic and bounded to three artifacts, eight edges, and 1024 expansions. A pack is admissible only when every member passes environment/privacy/network/license/secret/evidence gates, its ordered capability path starts from exact `inputs[].schema_ref`, has exact adjacent schema matches, its terminal output matches the objective, and aggregate runtime/cost remain within policy. `search_exhausted` is distinct from exhaustive `no_admissible_plan`.

### Contract enforcement

Use pinned `jsonschema==4.26.0` and `referencing==0.37.0` for offline Draft 2020-12 validation. The runtime loads a fixed package-local schema allowlist, builds an in-memory referencing registry, uses `FormatChecker`, and never performs remote retrieval. Strict readers reject duplicate JSON keys, non-finite numbers, oversized payloads, symlinks, and non-regular registry files. Semantic checks still enforce cross-record policy rules.

### Interfaces

Expose only resolve and simulate through:

- a standard-library HTTP server restricted to loopback; and
- an MCP JSON-RPC stdio server.

Both surfaces bind one registry at startup. Request bodies may contain inline objective/environment/plan documents only, never filesystem paths or URLs. Neither surface installs, invokes, grants, mutates, retrieves, verifies manifests, or sends.

### Buildroom integration

Dogfood via `BuildroomRecommendationProjection/v1`, a pure stdout/in-memory projection over the exact resolver plan and simulation status. It carries `authority=none`, `dispatch_allowed=false`, and `requires_operator_approval=true`. It is not a receipt, creates no proof file, writes no ledger, and does not dispatch or mutate Buildroom state.

## Threat model and controls

| Threat | Control |
|---|---|
| Composition explosion | Hard maximum of three artifacts, eight edges, and 1024 expansions |
| Type confusion | V2-only exact starting, adjacent, and terminal schema equality |
| Policy laundering across a pack | Per-artifact hard gates plus aggregate resource gates and edge-scoped evidence |
| Malicious publisher prose | Structured allowlists; prose excluded from context packet |
| Adapter becomes public service | Loopback-only host allowlist; MCP is stdio |
| Hidden execution | Empty `resolution-only/v1` argv for composition; simulation reports zero invocations |
| Grant/task authority confusion | Projection authority is `none`; dispatch is false; operator approval required |
| Registry mutation | Defensive deep copies and read-only loaders |
| Secret leakage | Secret values rejected by validation; no credential surface |
| Digest-only trust | Documentation states digest proves integrity, not provenance/authority |

## Consequences

Phase 2 supports useful multi-artifact recommendations and local agent integrations while remaining deterministic and reviewable. It does not support arbitrary graph search, live registry retrieval, artifact execution, execution grants, mutable evidence, or non-loopback deployment.

A later execution phase requires a separate threat review and explicit approval covering provenance/signatures, sandbox isolation, permissions, secrets, network restrictions, receipt lineage, cancellation, and rollback.
