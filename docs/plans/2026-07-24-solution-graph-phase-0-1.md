# Solution Graph Phase 0/1 implementation plan

**Date:** 2026-07-24
**Owner:** Kublai
**Status:** completed
**Source PRD:** private Brain plan (not included in this public repository)

## Code-root decision

Implement in `solution_graph/` with a thin entry point at `scripts/ksg.py`.

Why:

- The PRD defines Solution Graph as a Kurultai capability-resolution extension.
- The Kurultai public rebuild repository is clean and is the appropriate source for reusable, public-safe contracts and fixtures.
- Hermes core is a runtime dependency and authority owner, not the product home.
- Brain remains the durable decision/receipt plane; it must not become the runtime package.
- No second task system, receipt ledger, scheduler, authority service, or secret store is introduced.

## Honest v0 scope

Deliver a deterministic, offline, read-only Phase 0/1 kernel:

1. JSON Schemas for the ten versioned contracts named in the PRD.
2. Canonical JSON and SHA-256 digest helpers.
3. Manifest/objective/environment validation with privacy and untrusted-content guards.
4. A fixture registry for the local-media-transcription objective.
5. Deterministic hard gates, bounded single-artifact selection, ranking, reason codes, proof debt, plan digest, and minimum-context packet generation.
6. A no-execution simulator that deterministically replays the plan from authoritative objective, environment, and registry inputs before applying static checks.
7. CLI commands: `resolve`, `simulate`, `verify-manifest`, and `verify-fixture`.
8. Tests covering stable digests, material drift, privacy, injection isolation, hard-gate reasons, declared-vs-observed evidence, no-plan behavior, deterministic output, and CLI behavior.

Explicitly out of scope:

- Artifact execution or installation.
- ExecutionGrant issuance or validation beyond schema presence.
- REST/MCP servers.
- Mutable evidence storage, trust promotion, or a new ledger.
- Public deployment, marketplace UI, external effects, or network access.
- General multi-node composition beyond deterministic selection of the smallest complete fixture candidate.

## TDD sequence

1. Add tests and fixture expectations; run them to observe failure because implementation is absent.
2. Add canonicalization, validation, and schemas.
3. Add registry loading, hard gates, deterministic scoring, context compilation, and simulation.
4. Add CLI and fixture catalog.
5. Run focused tests, full repository tests, compile checks, secret-pattern scan, and repeated CLI smoke.

## Acceptance for this increment

- Same inputs produce byte-equivalent plan bodies and identical plan digests.
- Critical plan drift changes the digest.
- Cloud, incompatible, blocking-failure, and policy-exceeding candidates are eliminated with machine-readable reasons.
- Unknown/declared/observed-pass/observed-fail/stale/conflicted/revoked remain separate states.
- No admissible candidate returns `no_admissible_plan`.
- Context packets contain structured selected fields only, never README/prose payloads.
- Resolver/simulator invoke no artifact code and perform no network I/O.
- No secret values are accepted in public contracts or emitted in outputs.
- The CLI exits non-zero on invalid manifests and unresolved objectives.

## Rollback

All work is additive and isolated to `solution_graph/`, `scripts/ksg.py`, `tests/test_solution_graph.py`, and this plan. Revert the scoped commit to remove the increment; no runtime state migration is required.
