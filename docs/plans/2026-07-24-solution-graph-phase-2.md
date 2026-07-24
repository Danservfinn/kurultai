# Solution Graph Phase 2 implementation plan

Date: 2026-07-24
Status: implemented and verified

## Goal

Harden the published offline resolver with complete runtime enforcement of its shipped schemas, bounded typed composition, materially different fixtures, read-only adapters, and recommendation-only Buildroom dogfooding—without adding artifact execution or a second authority system.

## Non-goals

- Artifact installation or invocation
- ExecutionGrant issuance
- Mutable registries/evidence
- Non-loopback HTTP exposure
- Credential or secret-value handling
- Live network retrieval
- A new task queue, ledger, receipt authority, or proof receipt file

## Work packets

1. **Runtime schema enforcement**
   - Load contracts by their `schema` discriminator from a fixed package-local allowlist.
   - Use pinned `jsonschema`/`referencing` for offline Draft 2020-12 validation with `FormatChecker`.
   - Preserve narrower semantic/security checks.
   - Reject nested malformed documents, duplicate JSON keys, non-finite numbers, remote refs, and unknown contract types.

2. **Bounded typed composition**
   - Preserve v1 single-artifact semantics.
   - Use v2 only for typed composition with `inputs[].schema_ref`.
   - Search deterministically with max three artifacts, eight edges, and 1024 expansions.
   - Require exact starting, adjacent, and terminal schema equality.
   - Enforce aggregate runtime/cost and edge-scoped evidence.
   - Emit `ResolutionPlan/v2` plus `AgentContextPacket/v2` for composed paths.

3. **Fixture expansion**
   - Local private-document redaction with cloud-egress elimination.
   - Two-artifact public research digest.
   - Adversarial/no-plan fixture with permission, network, and type conflicts.

4. **Read-only adapters**
   - Startup-bound read-only service facade.
   - Exact loopback-only REST routes: `/v1/objectives:resolve` and `/v1/plans/{plan_id}:simulate`.
   - Exact stdio MCP tools: `solution_graph.resolve_objective` and `solution_graph.simulate_plan`.
   - No request-controlled registry paths, filesystem paths, URLs, mutation routes, execution routes, or verify-manifest tool.

5. **Buildroom dogfood**
   - Generate a recommendation-only projection around an exact resolver plan.
   - Include `authority=none`, `dispatch_allowed=false`, and `requires_operator_approval=true`.
   - Emit stdout/in-memory only.
   - Remove the second receipt/proof family.

6. **Verification and publication**
   - Focused tests, full repository tests, syntax/contract smoke, adversarial review, diff review.
   - Commit and push only after all checks pass.
   - Verify GitHub commit readback.

## Acceptance criteria

- All original tests continue to pass.
- Runtime schema tests fail closed on nested violations.
- A genuine two-artifact chain resolves and simulates with zero invocations.
- An incompatible chain returns structured `no_admissible_plan`.
- REST rejects non-loopback binds.
- MCP exposes only the two read-only tools.
- Buildroom dogfood is a projection only and no proof receipt file exists.
- Full repository tests pass.

## Verification record

- Full Python 3.14 suite: 45 passed.
- Fresh virtual environment from `solution_graph/requirements.txt`: 27 focused tests passed.
- Draft 2020-12 schema checks: 18 schemas valid; all references package-local.
- Deterministic replay probe: 100/100 identical plans and zero-invocation simulations.
- Public-repository privacy/secret validation, `compileall`, and `git diff --check`: passed.
- Independent adversarial reviews identified and drove remediation of strict RFC 3339 fallback, acyclic and authority-preserving chronological evidence supersession, closed nested v1 context contracts, IPv4-only loopback behavior, and registry-root symlink rejection. The final post-remediation Codex review reported no introduced correctness, security, or maintainability issues.
