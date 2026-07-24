# Kurultai Solution Graph

An offline, deterministic, **read-only capability resolver** for agents.

This directory is the first safe implementation slice of the Agent-First Executable Directory PRD. It resolves a typed objective against exact artifact manifests and scoped evidence, explains hard eliminations, ranks admissible candidates deterministically, and emits a minimum-context plan. It does **not** install or execute tools, issue grants, access the network, or create a new authority/evidence system.

## Safety boundary

- Registry inclusion grants no runtime authority.
- `resolve` and `simulate` invoke no artifact code.
- Manifests accept structured `argv_template` arrays, never shell command strings.
- Secret slot names may be declared; secret values are rejected.
- Publisher descriptions and source documents remain untrusted data and are not copied into agent context packets.
- Plans bind exact artifact, registry, environment, policy, and scoring identities into a stable digest.
- An explicit `no_admissible_plan` is preferred to a policy-violating workaround.

## Layout

```text
solution_graph/
  canonical.py          Stable canonical JSON and SHA-256 digests
  validation.py         Fail-closed public contract/fixture validators
  registry.py           Immutable fixture snapshot loader
  resolver.py           Hard gates, deterministic rank, plan/context compiler
  schemas/              Ten Phase 0 JSON Schema contracts
  fixtures/
    transcription/      Offline local-MP4 resolution fixture
scripts/ksg.py           CLI entry point
tests/test_solution_graph.py
```

The package intentionally omits execution, grant issuance, mutable evidence storage, REST/MCP servers, and deployment configuration.

## Quick start

Use Python 3.10 or newer; the implementation itself has no third-party dependencies.

```bash
python3 scripts/ksg.py verify-fixture solution_graph/fixtures/transcription

python3 scripts/ksg.py resolve \
  solution_graph/fixtures/transcription/objective.json \
  --environment solution_graph/fixtures/transcription/environment.json \
  --registry solution_graph/fixtures/transcription \
  > /tmp/plan.json

python3 scripts/ksg.py simulate /tmp/plan.json \
  --objective solution_graph/fixtures/transcription/objective.json \
  --environment solution_graph/fixtures/transcription/environment.json \
  --registry solution_graph/fixtures/transcription
```

Expected fixture result:

- selects `artifact:whisper-cpp-local`;
- retains admissible local alternatives with explicit evidence states;
- eliminates cloud ASR for denied network/private-data egress;
- eliminates the x86-only version as environment-incompatible;
- eliminates the broken version for blocking failure/evidence;
- emits a minimum-context `AgentContextPacket/v1` and stable `plan_digest`;
- reports `artifact_invocation_count: 0` during simulation.

## Commands

| Command | Effect | Exit status |
|---|---|---:|
| `ksg resolve OBJECTIVE --environment ENV --registry DIR` | Read-only resolution to JSON stdout | `0` resolved, `2` no plan/invalid |
| `ksg simulate PLAN --objective OBJECTIVE --environment ENV --registry DIR` | Authoritative deterministic replay plus static checks; no artifact invocation | `0` pass, `2` fail/invalid |
| `ksg verify-manifest MANIFEST` | Validate identity, fields, invocation, and privacy rules | `0` valid, `2` invalid |
| `ksg verify-fixture DIR` | Validate manifests and deterministic registry snapshot | `0` valid, `2` invalid |

## Contract and digest rules

The ten schemas are under `schemas/`. Canonical digests use UTF-8 JSON with sorted object keys, compact separators, Unicode preserved, and non-finite numbers rejected. Array order is significant. A plan digest is computed before adding the `plan_digest` field itself; simulation recomputes that body and fails closed on drift.

This is a stable canonicalization rule for the supported contract subset, not a claim of complete RFC 8785 numeric normalization.

## Evidence semantics

The fixture preserves these states as distinct values:

- `unknown`
- `declared`
- `observed-pass`
- `observed-fail`
- `stale`
- `conflicted`
- `revoked`

Publisher claims do not become independent evidence: source class remains explicit and caps ranking strength. Evidence matches only an exact artifact ID, version, digest, and environment; future observations are ignored and expired observations degrade to `stale` at the environment profile's explicit evaluation time. The v0 rank is deliberately simple and deterministic; hard policy gates run first.

`simulate` recomputes the expected plan from the supplied authoritative objective, environment profile, and registry snapshot, then requires an exact deterministic replay plus internal policy checks. A matching digest alone proves only self-integrity, **not issuer provenance or execution authority**; this release issues no grants and performs no execution.

## Development

```bash
/opt/homebrew/opt/python@3.14/bin/python3.14 -m pytest -q tests/test_solution_graph.py
/opt/homebrew/opt/python@3.14/bin/python3.14 -m pytest -q
```

Implementation plan: `docs/plans/2026-07-24-solution-graph-phase-0-1.md`.

## Next gated increments

1. Richer typed composition search and complete JSON Schema validation.
2. Read-only REST/MCP adapters.
3. Buildroom simulation and existing receipt/trace adapters.
4. Fixture-only sandbox execution after separate threat review.

None of those are implied to be complete by this directory.
