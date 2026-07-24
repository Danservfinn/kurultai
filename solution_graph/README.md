# Kurultai Solution Graph

An offline, deterministic, **read-only capability resolver** for agents.

Solution Graph resolves typed objectives against exact artifact manifests and scoped evidence, explains hard eliminations, composes compatible artifacts under a strict bound, and emits minimum-context plans. It never installs or executes tools, issues grants, mutates registries, or creates a second authority/task system.

## Phase 2 capabilities

- Offline Draft 2020-12 runtime validation of every shipped public JSON Schema contract with a fixed package-local allowlist, `FormatChecker`, bounded errors, and no remote retrieval.
- Deterministic typed composition of one to three artifacts for `ObjectiveSpec/v2` only; `ObjectiveSpec/v1` remains single-complete-artifact resolution.
- Ordered capability chains require exact `output_schema` → `input_schema` compatibility.
- Aggregate runtime/cost gates and per-artifact policy/privacy/environment gates.
- Three offline fixture families plus an adversarial no-plan fixture.
- Loopback-only REST and stdio MCP adapters for resolve and simulate against a startup-bound registry snapshot.
- Recommendation-only Buildroom projection with no execution authority, no dispatch, no receipt ledger, and no proof file.

## Safety boundary

- Registry inclusion grants no runtime authority.
- `resolve`, `simulate`, REST, MCP, and Buildroom recommendation generation invoke no artifact code.
- Manifests accept structured `argv_template` arrays, never shell command strings.
- Secret slot names may be declared; secret values are rejected.
- Publisher descriptions and source documents remain untrusted data and are not copied into agent context packets.
- Plans bind exact artifact, registry, environment, policy, and scoring identities into a stable digest.
- REST binds only to `127.0.0.1`; MCP uses local stdio.
- Buildroom projections carry `authority=none`, `dispatch_allowed=false`, and `requires_operator_approval=true`.
- An explicit `no_admissible_plan` is preferred to a policy-violating or type-incompatible workaround.

## Layout

```text
solution_graph/
  canonical.py          Stable canonical JSON and SHA-256 digests
  schema_runtime.py     Offline Draft 2020-12 schema runtime and strict JSON readers
  validation.py         Hand checks plus runtime enforcement of shipped schemas
  registry.py           Immutable fixture snapshot loader
  resolver.py           Hard gates, bounded typed composition, deterministic plans
  service.py            Startup-bound read-only service facade
  rest_adapter.py       Loopback-only dependency-free REST surface
  mcp_adapter.py        Read-only MCP stdio tool surface
  buildroom.py          Recommendation-only projection generator
  schemas/              Public JSON Schema contracts
  fixtures/
    transcription/      Local media transcription
    document_redaction/ Private document redaction
    research_digest/    Two-artifact typed research composition
    adversarial_no_plan/Policy/type conflict fail-closed corpus
scripts/
  ksg.py
  ksg_rest.py
  ksg_mcp.py
  ksg_buildroom_recommend.py
tests/test_solution_graph.py
```

## Quick start

Python 3.10+ with pinned Solution Graph dependencies in `solution_graph/requirements.txt`.

```bash
python3 -m pip install -r solution_graph/requirements.txt
python3 scripts/ksg.py verify-fixture solution_graph/fixtures/research_digest
python3 scripts/ksg.py resolve solution_graph/fixtures/research_digest/objective.json --environment solution_graph/fixtures/research_digest/environment.json --registry solution_graph/fixtures/research_digest > /tmp/plan.json
python3 scripts/ksg.py simulate /tmp/plan.json --objective solution_graph/fixtures/research_digest/objective.json --environment solution_graph/fixtures/research_digest/environment.json --registry solution_graph/fixtures/research_digest
```

The research fixture resolves an ordered two-artifact chain:

1. `artifact:bookmark-normalizer`: `BookmarkExport/v1` → `ResearchCards/v1`
2. `artifact:evidence-memo-writer`: `ResearchCards/v1` → `EvidenceMemo/v1`

The composition context packet uses `resolution-only/v1` with an empty argv template. Simulation reports `artifact_invocation_count: 0`.

## Read-only adapters

REST self-test and optional loopback server:

```bash
python3 scripts/ksg_rest.py --registry solution_graph/fixtures/research_digest --self-test
python3 scripts/ksg_rest.py --registry solution_graph/fixtures/research_digest --host 127.0.0.1 --port 8765
```

Routes: `POST /v1/objectives:resolve` and `POST /v1/plans/{plan_id}:simulate`. Request bodies contain inline objective/environment/plan documents only; registry roots are startup configuration. Non-loopback binds fail closed.

MCP stdio server:

```bash
python3 scripts/ksg_mcp.py --registry solution_graph/fixtures/research_digest
```

Tools: `solution_graph.resolve_objective` and `solution_graph.simulate_plan`. There is no manifest-verification, mutation, grant, or execution tool.

## Recommendation-only Buildroom dogfood

```bash
python3 scripts/ksg_buildroom_recommend.py solution_graph/fixtures/research_digest/objective.json --environment solution_graph/fixtures/research_digest/environment.json --registry solution_graph/fixtures/research_digest --room-id room:research-digest
```

The command prints a `BuildroomRecommendationProjection/v1` to stdout. It creates no proof receipt, ledger entry, task, dispatch, grant, or external effect.

## Contract, composition, and digest rules

All schemas under `schemas/` are enforced at runtime by `jsonschema==4.26.0` and `referencing==0.37.0` using a fixed local allowlist. Strict readers reject duplicate JSON keys, `NaN`, `Infinity`, oversized documents, and symlink/non-regular registry files. Canonical digests use UTF-8 JSON with sorted object keys, compact separators, Unicode preserved, and non-finite numbers rejected. Array order is significant. A plan digest is computed before adding `plan_digest`; simulation recomputes the body and fails closed on drift.

Typed search is a bounded deterministic v2 BFS: at most three artifacts, eight edges, and 1024 expansions. It starts from exact `inputs[].schema_ref`, requires exact adjacent schema equality and terminal output equality, rejects cycles and duplicate capability IDs, sums runtime/cost, and returns `search_exhausted` distinctly from `no_admissible_plan`.

This canonicalization covers the supported contract subset; it is not a claim of complete RFC 8785 numeric normalization.

## Evidence semantics

States remain distinct: `unknown`, `declared`, `observed-pass`, `observed-fail`, `stale`, `conflicted`, and `revoked`. Publisher claims never become independent evidence. Evidence matches exact artifact ID, version, digest, environment, and capability edge. Future observations are ignored; expired observations become stale at the environment's explicit evaluation time. V2 plans retain per-edge evidence in `composition_path`.

`simulate` recomputes the expected plan from authoritative objective, environment, and registry inputs, then requires exact replay plus internal policy checks. A matching digest proves self-integrity, not issuer provenance or execution authority.

## Development

```bash
python3 -m pytest -q tests/test_solution_graph.py
python3 -m pytest -q
```

Plans/decisions:

- `docs/plans/2026-07-24-solution-graph-phase-0-1.md`
- `docs/plans/2026-07-24-solution-graph-phase-2.md`
- `docs/adr/2026-07-24-solution-graph-phase-2.md`

## Next gated increment

Fixture-only sandbox execution may be considered only after a separate threat review covering grants, provenance/signatures, isolation, secrets, network policy, receipt lineage, cancellation, and rollback. Phase 2 grants no execution authority.
