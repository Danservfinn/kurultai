# ADR: Solution Graph Phase 0/1 as an offline read-only resolver

- **Status:** Accepted
- **Date:** 2026-07-24
- **Owner:** Kurultai public rebuild
- **Implementation:** `solution_graph/`

## Context

Kurultai needs a machine-first directory that can answer which verified artifact can satisfy an objective in a specific environment. The first release must prove contract shape, deterministic resolution, evidence semantics, and safe agent context generation without adding execution authority or a network service.

The repository had no existing `tools/` convention or Python package metadata. The clean Kurultai public rebuild is the correct owner; Hermes core and the private/dirty Brain workspace are not.

## Threat model

Phase 0/1 assumes all registry records, publisher prose, manifests, evidence records, objectives, environment profiles, and saved plans may be attacker-controlled.

Primary threats:

1. publisher prose or manifest fields becoming agent instructions;
2. secret values smuggled through nominal slot-name fields;
3. evidence laundering across artifact versions, digests, environments, capabilities, source classes, freshness windows, or future timestamps;
4. policy fields that are documented but not enforced;
5. self-redigested fabricated plans being presented as validated plans;
6. malformed nested contracts producing partial acceptance or uncaught exceptions;
7. accidental network/process execution by the resolver.

## Decision

Implement a standard-library Python package and CLI with these boundaries:

- deterministic canonical JSON and SHA-256 digests for the supported contract subset;
- ten frozen Phase 0 JSON Schema documents plus fail-closed runtime validators;
- an offline fixture registry with explicit snapshot identity;
- exact evidence binding to artifact ID, version, digest, environment, and declared capability;
- future evidence ignored, expired evidence marked stale, conflicts and revocation preserved, and source class retained as a ranking ceiling;
- hard gates for capability/schema compatibility, license, environment/runtime/architecture, prerequisites, network allowlists, privacy egress, secret policy, permissions, cost, runtime, failures, and blocking evidence;
- structured agent context that excludes descriptions, source prose, source references, and arbitrary publisher text and labels included structured data as untrusted;
- simulation that requires the authoritative objective, environment, and registry inputs and performs exact deterministic resolution replay before reporting pass;
- no artifact execution, shelling out, network imports, grants, mutable evidence storage, ledger, REST service, or MCP service.

## Alternatives rejected

- **Hermes core:** wrong ownership and would couple a repository-specific catalog to agent runtime internals.
- **Brain workspace:** wrong trust/privacy boundary and unsuitable as executable public source.
- **Network registry/service in v0:** increases attack surface before contracts and evidence semantics are stable.
- **Executor in v0:** would conflate discovery with authority and require a separate grant, sandbox, receipt, and rollback threat review.
- **Digest-only simulation:** proves only self-integrity and permits a fabricated plan to be redigested; authoritative replay is required instead.
- **Trusting publisher README/prose:** prose is untrusted data and is never loaded into resolver context.

## Consequences

### Positive

- Reproducible, offline resolution with explicit reason codes.
- Machine-readable contracts and a practical transcription fixture.
- No new runtime authority or external dependency.
- Adversarial tests encode the threat boundaries directly.

### Limitations

- Canonicalization is explicit for the supported subset and is not a complete RFC 8785 implementation.
- Composition search is intentionally shallow and fixture-oriented.
- JSON Schema files document public contracts; runtime enforcement is handwritten standard-library validation.
- Simulation proves deterministic equality to the supplied authoritative inputs, not issuer identity or execution permission.
- No live publisher ingestion, mutable registry, signing, grants, execution, or service API exists.

## Verification gate

Release requires all of the following:

- focused Solution Graph tests;
- complete repository pytest suite;
- compile and whitespace checks;
- fixture verification, resolution, and authoritative simulation CLI smoke;
- zero artifact invocations during simulation;
- secret-pattern and forbidden runtime-import scans;
- malicious publisher-prose exclusion test;
- independent adversarial review with no remaining release blockers.
