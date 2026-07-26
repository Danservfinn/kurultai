---
title: "Hulagu Full Hermes Instance v2 — Autonomous Machine-Policy Amendment"
type: plan
status: autonomous_authority_review_candidate
version: 0.7.0
created: 2026-07-25
updated: 2026-07-26T19:21:30Z
accountable_operator_provenance: the accountable operator provenance record
implementer: Kublai
verifier: Claude Code
review_state: frozen_pending_independent_policy_review
implementation_authorized: false
canonical_path: /Users/kublai/brain/docs/plans/2026-07-25-hulagu-full-hermes-instance-v2-revised-plan.md
review_of_prior_revision: /Users/kublai/brain/docs/plans/reviews/2026-07-25-hulagu-full-hermes-instance-v2-review.md
---

# Hulagu Full Hermes Instance v2 — Autonomous Machine-Policy Amendment (v0.7.0)

> **Autonomy amendment, not implementation authority.** This revision removes future human runtime start and closure approvals, but it does not itself mutate the Hulagu source workspace or runtime. Every mutation remains blocked by exact machine-policy admission, independent review, mandatory evidence, and permanent forbidden surfaces.

## 1. Decision in one sentence

Run one long-lived Hermes profile only as a **public-source research and policy-control plane**; archive every complete observable conversation from that profile on the 4 TB KurultaiVault storage tier outside the Kublai Brain namespace; put every tenant-sensitive reasoning step in a short-lived, resource-bounded container inside its own ephemeral Lima VM; and allow both planes to affect durable product state only through a deterministic broker with separate APIs, separate credentials, immutable receipts, and machine-policy-gated promotion.

This is a bounded product loop, not a claim of AGI or unconstrained autonomy.

## 2. Autonomous evidence and authority

    This v0.7.0 amendment is additive. The historical v3 authority and the independently corrected G0 packet remain immutable evidence; no historical approval, receipt, signature, or author identity is rewritten. The new policy supersedes only future human runtime start, activation, pilot, and closure checkpoints.

    | Evidence | Bound fact | Fail-closed consequence |
    |---|---|---|
    | source base | commit `2f10cb9351cfae554a74e98ee6894240670b5275`, tree `1b86294560ff700f83657c3f18f05bff153da084` | mismatch returns `DENY` before mutation |
    | predecessor suite | 98 nodes, SHA-256 `25a7e6dbf06e7393128b61952e0d5185518ebb7014ab71bcf1361a7d0ef56a2a` | any removed predecessor node blocks G0 |
    | autonomy delta | 16 successor-freeze nodes plus 3 schema nodes | exact product-local collection is 117; exact repository command collection is 184 from a 165-node source baseline |
    | corrected predecessor overlay | 20 files frozen separately in the Brain review packet | any byte drift reopens review |
    | accountable operator | the accountable operator provenance record is recorded as provenance and emergency observer only | `runtime_decision_authority: false`; assent is not an admission predicate |
    | implementation boundary | this plan and overlay are review candidates | `implementation_authorized: false` until exact-hash independent policy review exists |

    ### Authority order

    After autonomous G0 closes, content-addressed authority is: (1) the source-controlled `autonomous-authority-v1` policy; (2) the independently reviewed exact candidate manifest; (3) a deterministic `gate-policy-admission-v1` decision for the current base/prior closure/write set/commands; (4) the successor ADR, threat model, and plan; (5) implementation code and runbooks. A conflict, missing field, stale review, replay, identity collision, unknown surface, or false predicate returns `DENY`.

    No human runtime start or closure gate exists in this chain. Each gate uses the forward-only protocol:

    1. Verify immutable base evidence commit `B_GX` and prior closure head.
    2. Compile `gate-policy-admission-v1` from exact policy, command, write-set, candidate-manifest, independent-review, freshness, replay, role-separation, consent, and budget evidence. `ADMIT` must exist before the first mutation.
    3. Change only the closed payload set and commit payload `P_GX`.
    4. Generate a post-payload manifest binding `B_GX`, `P_GX`, trees, path hashes, commands, test-node delta, policy admission, and prior closure.
    5. A distinct independent verifier reviews detached `P_GX` and binds the payload-manifest hash. The deterministic closure verifier emits `closure-envelope.json` binding payload, review, admission, test receipts, and protected-ref reproduction.
    6. Commit evidence-only bytes as `E_GX`; verify `P_GX..E_GX` contains no payload change; push/fetch `refs/hulagu/gates/<GX>/<closure-envelope-sha256>`; set `B_next = E_GX`.

    Evidence-only paths are closed to RED, GREEN, schema, collection, full-suite, commands, payload manifest, independent review, policy admission, closure envelope, and protected-ref reproduction receipts. There is no post-action assent receipt and no artifact hashes the commit that contains itself.

    G0 payload paths are exactly:

    ```text
    docs/plans/2026-07-25-hulagu-full-hermes-instance-v2-revised-plan.md
docs/adr/2026-07-25-hulagu-full-hermes-brokered-capsules.md
docs/hulagu/THREAT-MODEL-v2.md
products/hulagu/README.md
products/hulagu/qa/hulagu-v2-source-inventory.json
products/hulagu/qa/hulagu-v2-predecessor-authority-map.json
products/hulagu/qa/hulagu-v2-impact-regression-baseline.json
products/hulagu/qa/buildroom/control_projection_contract_v1.json
products/hulagu/qa/g0-predecessor-test-nodes-v1.json
products/hulagu/qa/g0-test-node-delta-v1.json
products/hulagu/qa/g0-identity-map-v1.json
products/hulagu/gates/registry.yaml
products/hulagu/gates/allowed-write-sets/G0.yaml
products/hulagu/policies/autonomous-authority-v1.json
products/hulagu/schemas/gate-evidence-v1.schema.json
products/hulagu/schemas/gate-policy-admission-v1.schema.json
products/hulagu/schemas/pilot-consent-v1.schema.json
products/hulagu/src/hulagu/__init__.py
products/hulagu/deploy/scripts/gates/compile_gate_policy_admission.py
products/hulagu/deploy/scripts/gates/verify_g0_successor_freeze.py
products/hulagu/tests/gates/test_g0_successor_freeze.py
products/hulagu/tests/contract/test_schema_examples.py
.github/workflows/hulagu-v2-gate.yml
    ```

    The exact effective 19-node addition is:

    ```text
    products/hulagu/tests/gates/test_g0_successor_freeze.py::test_plan_copy_matches_autonomy_freeze
products/hulagu/tests/gates/test_g0_successor_freeze.py::test_source_inventory_is_closed_and_tree_bound
products/hulagu/tests/gates/test_g0_successor_freeze.py::test_predecessor_authority_map_is_total
products/hulagu/tests/gates/test_g0_successor_freeze.py::test_predecessor_baseline_dispositions_are_total
products/hulagu/tests/gates/test_g0_successor_freeze.py::test_named_identities_are_distinct
products/hulagu/tests/gates/test_g0_successor_freeze.py::test_g0_allowed_write_set_is_exact
products/hulagu/tests/gates/test_g0_successor_freeze.py::test_policy_admission_precedes_mutation
products/hulagu/tests/gates/test_g0_successor_freeze.py::test_policy_compiler_denies_invalid_evidence
products/hulagu/tests/gates/test_g0_successor_freeze.py::test_payload_and_evidence_commits_are_acyclic
products/hulagu/tests/gates/test_g0_successor_freeze.py::test_protected_ref_reproduces_in_clean_clone
products/hulagu/tests/gates/test_g0_successor_freeze.py::test_g0_static_control_room_projection_fails_closed
products/hulagu/tests/gates/test_g0_successor_freeze.py::test_historical_v3_authority_bytes_are_unchanged
products/hulagu/tests/gates/test_g0_successor_freeze.py::test_g0_chain_rejects_any_mutated_byte
products/hulagu/tests/gates/test_g0_successor_freeze.py::test_permanent_forbidden_surfaces_are_global
products/hulagu/tests/gates/test_g0_successor_freeze.py::test_pilot_consent_never_auto_invites
products/hulagu/tests/gates/test_g0_successor_freeze.py::test_g1_g11_controller_contract_is_policy_bound
products/hulagu/tests/contract/test_schema_examples.py::test_schema_embedded_examples_validate[gate-evidence-v1.schema.json]
products/hulagu/tests/contract/test_schema_examples.py::test_schema_embedded_examples_validate[gate-policy-admission-v1.schema.json]
products/hulagu/tests/contract/test_schema_examples.py::test_schema_embedded_examples_validate[pilot-consent-v1.schema.json]
    ```

    Future G1–G11 activation is not a signed exception. The registry freezes every dependency, slug, proof directory, receipt class, predicate ID, stop semantic, and canonical argv family. A gate becomes executable only when source-authored paths exist, an exact allowed-write-set and command packet are independently reviewed, all machine predicates compile true, and no permanent forbidden surface is requested. Any amendment that changes a frozen invariant reopens G0.

    Permanent forbidden surfaces are exactly `payments`, `public_posting`, `identity_or_soul_changes`, `hard_deletes`, and `unapproved_outbound_email_or_chat`. They cannot be widened by a later gate. Implementations may build and test synthetic stop, tombstone, and quarantine machinery, but the autonomy-v1 policy cannot admit a live hard-delete action.

    G10 and G11 never create or infer consent. They require a valid `pilot-consent-v1` object and an existing communication-permission reference for each participant. There is no automatic invitation. If eligible participants do not exist, implementation may still close at G9 while pilot evidence remains `PILOT_EVIDENCE_PENDING`.

    The canonical G0 command packet is:

    ```json
    {
  "base_commit": "2f10cb9351cfae554a74e98ee6894240670b5275",
  "base_tree": "1b86294560ff700f83657c3f18f05bff153da084",
  "commands": [
    {
      "argv": [
        "/usr/bin/python3",
        "/Users/kublai/brain/docs/plans/reviews/hulagu-autonomy-v1/policy-admission-verifier.py",
        "--manifest",
        "/Users/kublai/brain/docs/plans/reviews/hulagu-autonomy-v1/manifest.json",
        "--independent-review",
        "/Users/kublai/brain/docs/plans/reviews/hulagu-autonomy-v1/independent-policy-review.json"
      ],
      "mutates": false,
      "phase": "preflight-policy-admission"
    },
    {
      "argv": [
        "/usr/bin/git",
        "rev-parse",
        "HEAD"
      ],
      "mutates": false,
      "phase": "preflight-base"
    },
    {
      "argv": [
        "/usr/bin/git",
        "diff",
        "--quiet"
      ],
      "mutates": false,
      "phase": "preflight-base"
    },
    {
      "argv": [
        "products/hulagu/.venv/bin/python",
        "-m",
        "pytest",
        "--collect-only",
        "-q"
      ],
      "cwd": "repository_root",
      "mutates": false,
      "phase": "baseline-collection"
    },
    {
      "argv": [
        "products/hulagu/.venv/bin/python",
        "-m",
        "pytest",
        "-q"
      ],
      "cwd": "repository_root",
      "mutates": false,
      "phase": "baseline-full-suite"
    },
    {
      "argv": [
        "/bin/cp",
        "-R",
        "/Users/kublai/brain/docs/plans/reviews/hulagu-autonomy-v1/red-overlay/.",
        "."
      ],
      "mutates": true,
      "phase": "apply-red"
    },
    {
      "argv": [
        "products/hulagu/.venv/bin/python",
        "-m",
        "pytest",
        "-q",
        "products/hulagu/tests/gates/test_g0_successor_freeze.py"
      ],
      "cwd": "repository_root",
      "mutates": false,
      "phase": "red"
    },
    {
      "argv": [
        "/bin/cp",
        "-R",
        "/Users/kublai/brain/docs/plans/reviews/hulagu-autonomy-v1/green-overlay/.",
        "."
      ],
      "mutates": true,
      "phase": "apply-green"
    },
    {
      "argv": [
        "products/hulagu/.venv/bin/python",
        "-m",
        "pytest",
        "-q",
        "products/hulagu/tests/gates/test_g0_successor_freeze.py"
      ],
      "cwd": "repository_root",
      "mutates": false,
      "phase": "green"
    },
    {
      "argv": [
        "products/hulagu/.venv/bin/python",
        "-m",
        "pytest",
        "-q",
        "products/hulagu/tests/contract/test_schema_examples.py::test_schema_embedded_examples_validate[gate-evidence-v1.schema.json]",
        "products/hulagu/tests/contract/test_schema_examples.py::test_schema_embedded_examples_validate[gate-policy-admission-v1.schema.json]",
        "products/hulagu/tests/contract/test_schema_examples.py::test_schema_embedded_examples_validate[pilot-consent-v1.schema.json]"
      ],
      "cwd": "repository_root",
      "mutates": false,
      "phase": "schema"
    },
    {
      "argv": [
        "products/hulagu/.venv/bin/python",
        "-m",
        "pytest",
        "--collect-only",
        "-q"
      ],
      "cwd": "repository_root",
      "mutates": false,
      "phase": "collection"
    },
    {
      "argv": [
        "products/hulagu/.venv/bin/python",
        "-m",
        "pytest",
        "-q"
      ],
      "cwd": "repository_root",
      "mutates": false,
      "phase": "full-suite"
    },
    {
      "argv": [
        "/usr/bin/git",
        "add",
        "--",
        "docs/plans/2026-07-25-hulagu-full-hermes-instance-v2-revised-plan.md",
        "docs/adr/2026-07-25-hulagu-full-hermes-brokered-capsules.md",
        "docs/hulagu/THREAT-MODEL-v2.md",
        "products/hulagu/README.md",
        "products/hulagu/qa/hulagu-v2-source-inventory.json",
        "products/hulagu/qa/hulagu-v2-predecessor-authority-map.json",
        "products/hulagu/qa/hulagu-v2-impact-regression-baseline.json",
        "products/hulagu/qa/buildroom/control_projection_contract_v1.json",
        "products/hulagu/qa/g0-predecessor-test-nodes-v1.json",
        "products/hulagu/qa/g0-test-node-delta-v1.json",
        "products/hulagu/qa/g0-identity-map-v1.json",
        "products/hulagu/gates/registry.yaml",
        "products/hulagu/gates/allowed-write-sets/G0.yaml",
        "products/hulagu/policies/autonomous-authority-v1.json",
        "products/hulagu/schemas/gate-evidence-v1.schema.json",
        "products/hulagu/schemas/gate-policy-admission-v1.schema.json",
        "products/hulagu/schemas/pilot-consent-v1.schema.json",
        "products/hulagu/src/hulagu/__init__.py",
        "products/hulagu/deploy/scripts/gates/compile_gate_policy_admission.py",
        "products/hulagu/deploy/scripts/gates/verify_g0_successor_freeze.py",
        "products/hulagu/tests/gates/test_g0_successor_freeze.py",
        "products/hulagu/tests/contract/test_schema_examples.py",
        ".github/workflows/hulagu-v2-gate.yml"
      ],
      "mutates": true,
      "phase": "stage"
    },
    {
      "argv": [
        "/usr/bin/git",
        "commit",
        "-m",
        "feat: freeze Hulagu autonomous authority v1"
      ],
      "mutates": true,
      "phase": "payload-commit"
    }
  ],
  "environment": {
    "CI": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
    "LANG": "C",
    "LC_ALL": "C",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONHASHSEED": "0"
  },
  "environment_mode": "empty-then-set-exactly",
  "expected": {
    "baseline_collection": 165,
    "baseline_full_suite": "165 passed",
    "collection": 184,
    "full_suite": "184 passed",
    "green": "16 passed",
    "product_collection": 117,
    "red": "16 errors",
    "schema": "3 passed"
  },
  "external_inputs": {
    "candidate_manifest": "/Users/kublai/brain/docs/plans/reviews/hulagu-autonomy-v1/manifest.json",
    "green_overlay": "/Users/kublai/brain/docs/plans/reviews/hulagu-autonomy-v1/green-overlay",
    "independent_policy_review": "/Users/kublai/brain/docs/plans/reviews/hulagu-autonomy-v1/independent-policy-review.json",
    "policy_admission_verifier": "/Users/kublai/brain/docs/plans/reviews/hulagu-autonomy-v1/policy-admission-verifier.py",
    "red_overlay": "/Users/kublai/brain/docs/plans/reviews/hulagu-autonomy-v1/red-overlay"
  },
  "gate_id": "G0",
  "packet_id": "hulagu.G0.commands.autonomy.v1",
  "payload_paths": [
    "docs/plans/2026-07-25-hulagu-full-hermes-instance-v2-revised-plan.md",
    "docs/adr/2026-07-25-hulagu-full-hermes-brokered-capsules.md",
    "docs/hulagu/THREAT-MODEL-v2.md",
    "products/hulagu/README.md",
    "products/hulagu/qa/hulagu-v2-source-inventory.json",
    "products/hulagu/qa/hulagu-v2-predecessor-authority-map.json",
    "products/hulagu/qa/hulagu-v2-impact-regression-baseline.json",
    "products/hulagu/qa/buildroom/control_projection_contract_v1.json",
    "products/hulagu/qa/g0-predecessor-test-nodes-v1.json",
    "products/hulagu/qa/g0-test-node-delta-v1.json",
    "products/hulagu/qa/g0-identity-map-v1.json",
    "products/hulagu/gates/registry.yaml",
    "products/hulagu/gates/allowed-write-sets/G0.yaml",
    "products/hulagu/policies/autonomous-authority-v1.json",
    "products/hulagu/schemas/gate-evidence-v1.schema.json",
    "products/hulagu/schemas/gate-policy-admission-v1.schema.json",
    "products/hulagu/schemas/pilot-consent-v1.schema.json",
    "products/hulagu/src/hulagu/__init__.py",
    "products/hulagu/deploy/scripts/gates/compile_gate_policy_admission.py",
    "products/hulagu/deploy/scripts/gates/verify_g0_successor_freeze.py",
    "products/hulagu/tests/gates/test_g0_successor_freeze.py",
    "products/hulagu/tests/contract/test_schema_examples.py",
    ".github/workflows/hulagu-v2-gate.yml"
  ],
  "phase_sequence": [
    "preflight-policy-admission",
    "preflight-base",
    "baseline-collection",
    "baseline-full-suite",
    "apply-red",
    "red",
    "apply-green",
    "green",
    "schema",
    "collection",
    "full-suite",
    "stage",
    "payload-commit"
  ],
  "policy_id": "hulagu.autonomous-authority.v1",
  "product_root": "/Users/kublai/kurultai/hulagu-g1-source-contracts/products/hulagu",
  "repository_root": "/Users/kublai/kurultai/hulagu-g1-source-contracts",
  "schema_version": "hulagu-gate-command-contract-v2"
}
    ```

## 3. What changes, and what does not

### In scope

- a source-controlled Hermes distribution for the Hulagu public/control profile;
- deterministic public research and operator-control APIs;
- deterministic tenant broker and durable recovery state;
- one selected, testable capsule-confinement primitive;
- quarantine-first migration and verified restore before data admission;
- bounded cron in shadow mode before activation;
- a complete, replayable, raw archive of every observable `hulagu_control` conversation on the 4 TB KurultaiVault storage tier outside the Kublai Brain namespace;
- one pre-consented bounded pilot followed by a pre-consented bounded cohort, with no automatic invitations;
- receipts and proof-debt status in existing Buildroom/control-room surfaces.

### Explicitly out of scope for v2

- a customer-facing Hermes or Telegram gateway;
- a second operator Telegram bot;
- ambient access from persistent Hermes to customer rows, drafts, CV text, profile answers, tokens, or vault roots;
- a shared multi-tenant capsule process;
- unrelated Hermes-core changes and any model-visible or third-party plugin; exactly two reviewed, source-controlled core patches are in scope—(1) the transaction-coupled archive outbox in Section 12 and (2) the pre-mutation cron-admission hook in Section 13—together with the one tool-free transcript observer;
- archival of tenant capsule prompts, tenant provider payloads, hidden provider reasoning, or customer-facing chat (there is no customer-facing Hermes in v2);
- default Brain indexing, embedding, summarization, or retrieval over full control-plane transcripts;
- direct model-written SQL, filesystem paths, shell commands, email, Sheets writes, cron mutation, or deletion;
- autonomous hiring, application submission, messaging, or payments;
- HA, multi-region, horizontal scaling, or an always-on swarm;
- hiding unresolved proof debt behind green UI.

Accountable operator provenance remains visible through G11, but runtime admission is machine-policy only. A separate gateway remains out of scope and would require a new independently reviewed policy.

## 4. Safety invariants

The following are release invariants, not aspirations:

1. **Persistent public-only plane.** The `hulagu_control` profile can receive public sources and sanitized aggregate health only. Its UID, credentials, schemas, network routes, and tool policy cannot read tenant payloads.
2. **No tenant data in a persistent Hermes home.** Tenant prompts, CV text, profile answers, candidate drafts, provider transcripts, and capability material never enter persistent sessions, memories, skills, logs, or cache.
3. **Capsule-assembled sensitive reasoning with an explicit plaintext transit TCB.** Tenant-sensitive prompts are assembled only inside the short-lived capsule/proxy pair; the only permitted plaintext transit is bounded memory in the guest proxy, host broker, and credential-isolated egress adapter needed to authorize and transmit one request. These processes have no persistent payload logs, core dumps, swap, tracing, or diagnostic body capture; their buffers are size-bounded and zeroized best-effort after the attempt. The capsule has no host mounts, provider credential, Docker socket, Keychain access, persistent log driver, or non-tmpfs writable storage. G4 must prove the stated TCB rather than claim that plaintext never reaches the host.
4. **Broker owns effects.** Models produce typed proposals. Deterministic code validates, authorizes, commits, and receipts every durable or external effect.
5. **One tenant and one lifecycle epoch per capability.** Capability scope is bound server-side to `(tenant_uuid, lifecycle_epoch, run_id, work_epoch, attempt_id, operation_set, expiry, nonce)` and cannot be widened by caller-supplied tenant fields.
6. **At-least-once execution, idempotent effects.** The system does not claim exactly-once delivery. It uses durable idempotency keys, leases, fencing tokens, readback, and explicit ambiguous-outcome reconciliation.
7. **Delete is terminal for an epoch.** Tombstones and lifecycle-epoch checks reject late work, restored stale work, replay, caches, indexes, outbox items, and capability use.
8. **Data admission defaults off.** No customer data or real external effect is admitted until migration and restore gates are green and the machine-policy compiler admits the exact fuse transition.
9. **Cron is policy, not prose.** Source-controlled manifests are compiled, read back from live Hermes state, diffed, and enforced by broker-side budgets. Drift stops the job.
10. **Proof debt is visible and owned.** Every unresolved item has one accountable operator provenance record, one closure gate, one fail-closed default, and one evidence path in existing control-room status.
11. **Every observable control-plane conversation is archived.** Once the profile is authorized to run, each committed user/assistant turn, tool event, delivery event, session boundary, and explicit history mutation is exported through a crash-recoverable outbox to the Hulagu raw archive before its local spool may be acknowledged or deleted.
12. **The archive is private raw evidence, not ambient memory.** Full transcript payloads remain outside Git and default Brain indexing/retrieval; the public profile cannot read the archive; tenant data and hidden provider reasoning never enter it; only content-addressed policy-authorized export may expose content; hard delete and declassification remain outside autonomous authority.

## 5. Target architecture

```text
public web/GitHub/job sources
            |
            v
  hulagu_control Hermes profile                policy-control API
  (public/control schemas only)                      |
            |\                                       |
            | +-- tool-free transcript observer      |
            |        -> bounded local outbox          |
            |        -> hulagu_archive identity       |
            |        -> Hulagu archive / KurultaiVault     |
            |                                        |
            +------------ PublicControlAPI/v1 -------+
                                  |
                                  v
                  deterministic Hulagu broker/app
             Postgres authority + outbox + receipts
                    |                         |
           public candidate bundle           | tenant work lease
                    |                         v
                    |             hulagu_launcher service identity
                    |              per-run ephemeral Lima VM
                    |                         |
                    |              per-run internal Docker network
                    |                  +------+------+
                    |                  |             |
                    |           capsule container  broker/run proxy
                    |           no host mounts     capability only
                    |           tmpfs only         host broker only
                    |                  |             |
                    |                  +-- TenantRunAPI/v1
                    |                         |
                    +-------------------------+
                                  |
                        validated effects only
                                  |
                  Postgres / encrypted vault / Sheets
```

Hermes proposes and explains. The deterministic application, policy engine, state machine, and policy gates remain product authority.

## 6. Service identities and filesystem authority

The runtime uses distinct macOS service identities; accountable operator provenance is not a daemon identity or an admission predicate.

| Identity | May access | Must not access |
|---|---|---|
| `hulagu_control` | its own Hermes distribution and home; public-source cache; local Unix sockets for typed public-model and source-fetch adapters; `PublicControlAPI/v1`; sanitized aggregate status; the transaction-coupled SQLite archive queue; create/garbage-collect rights in `events/`; read-only reconcile access to `acks/`; no ACK signing key; append-only, no-rewrite receipt creation in `/var/db/hulagu-control/operator-receipts/`; read-only access to the root-owned `/var/db/hulagu-control/policy-admissions/profile-delete-policy-admission.json` | all KurultaiVault paths including the transcript archive; tenant DB role; capsule socket; Lima state/control socket; every provider/Sheets credential and all Keychain items; raw AF_INET/AF_INET6 egress under the PF policy; effect-authority-ledger signer; `TenantRunAPI/v1` |
| `hulagu_archive` | read-only access to transcript `events/`; append-only digest-bound ACK access to `acks/`; ACK signing key unavailable to `hulagu_control`; descriptor-confined create/fsync/verify access only to the Hulagu chat-archive subtree; its own redacted receipts and capacity state; read-only access to `/var/db/hulagu-control/operator-receipts/profile-delete-receipt.json` for post-delete verification | Hermes sessions database or model/provider credentials; event-object deletion; public or tenant APIs; tenant DB or vault roots; arbitrary Brain paths; profile memories/skills; shell/network effects; effect-authority-ledger signer |
| `hulagu_app` | broker database role; encrypted vault through descriptor-relative store; receipt store; policy manifests; local Unix socket for the typed tenant-provider adapter | Hermes profile homes; Lima state/control socket; unrestricted shell; every provider/Sheets credential and all Keychain items; raw AF_INET/AF_INET6 egress under the PF policy; effect-authority-ledger signing key; direct model-written provider calls |
| `hulagu_provider_egress` | tenant-plane model credential through a service-account Keychain ACL; one root-owned Unix socket; one signed provider/model/region policy row; PF-table destinations generated from that row | tenant DB/vault, Hermes homes, Lima control, lifecycle signer, arbitrary DNS/proxy/socket destinations, or any non-provider credential |
| `hulagu_public_egress` | low-budget public-plane model credential; one root-owned Unix socket; one signed provider/model/region policy row; PF-table destinations generated from that row | tenant DB/vault, capsule/Lima state, public profile files beyond typed request bytes, arbitrary DNS/proxy/socket destinations, or tenant/Sheets credentials |
| `hulagu_fetch` | one root-owned Unix socket and a source-fetch policy with scheme/host/IP/byte/time/redirect limits; no service credential | Keychain, tenant DB/vault, provider credentials, private/link-local/loopback destinations, generic proxying, or returning unredacted transport diagnostics |
| `hulagu_delivery` | dedicated effect-dispatch DB role; Sheets service-account credential; dedicated owner folder; recipient/domain allowlist; create/readback/revoke typed operations | tenant vault or Brain roots; Hermes homes; VM control; model credentials; arbitrary Drive/Sheets search or sharing |
| `hulagu_launcher` | VM control, pinned images, and opaque attempts; it is explicitly a data-bearing cross-tenant TCB because VM control can inspect guest memory | static provider/Sheets/database credentials; persistent Hermes home; effect-authority-ledger signer |
| `hulagu_bootstrap` | verify template/image receipt; sign one-run proxy certificate from a guest-generated CSR; bind certificate fingerprint to one attempt | tenant payloads; provider/Sheets/database credentials; VM control; capability widening or refresh |
| `hulagu_deletion` | dedicated deletion DB role; effect-authority-ledger signing key and monotonic advance; typed revoke/reconcile requests to `hulagu_delivery` and `hulagu_provider_egress` | general app reads; profile home; VM control; backup/migrator credentials; direct Sheets/provider credentials |
| `hulagu_migrator` | read-only legacy source; write-only quarantine destination; migration ledger | normal runtime; capsule socket; public profile home; effect-authority-ledger lowering |
| `hulagu_backup` | snapshot/export interfaces and sealed backup destination | model providers; Hermes homes; runtime write role; effect-authority-ledger lowering |
| `hulagu_auditor` | read-only redacted audit views and proof verification | tenant payload columns; write roles; credentials; VM control |
| accountable operator provenance | emergency observation and provenance only; `runtime_decision_authority=false` | routine execution, admission, credential access, or closure authority |

G2 installs a concrete host-enforced egress boundary before any credential is provisioned. Root owns `/etc/pf.anchors/ai.hulagu.egress`, `/etc/pf.anchors/ai.hulagu.tables`, `/var/db/hulagu-control/egress/`, and the launchd definitions for the three adapters. The PF anchor uses UID-scoped default-deny rules for `hulagu_control`, `hulagu_app`, `hulagu_provider_egress`, `hulagu_public_egress`, and `hulagu_fetch` across IPv4 and IPv6. `hulagu_control` and `hulagu_app` may connect only to their exact root-owned Unix sockets. Provider adapters may connect only to IP tables derived by a root helper from the signed hostname/port policy; the helper rejects CNAME/private/link-local/loopback results, records DNS answers and TTLs, pins the adapter to the selected IP while preserving TLS hostname verification/SNI, and fails closed when answers expire or drift until an policy-admitted refresh receipt exists. The source fetcher receives a separate no-credential allowlist and redirect policy. Proxy environment variables are cleared and fixed; generic CONNECT, alternate DNS, QUIC/UDP, raw IP literals, IPv4-mapped IPv6, and undeclared local listeners are denied. The root helper and PF anchor are outside every credential-bearing service UID.

G2/G4 evidence must show the active PF anchor and table hashes before and after reboot, launchd UID/readback, socket ACLs, Keychain ACL denials, and negative probes for direct TCP, UDP/QUIC, IPv6, raw IP, alternate DNS, proxy tunnelling, localhost pivot, and DNS-rebinding attempts. It must also show one allowed provider request through each typed adapter. If the selected macOS PF build cannot enforce the tested UID/destination semantics, G2 fails; an app-level hostname check is not an accepted substitute.

Target locations are part of the G2/G3A proof packet, not ad hoc conventions:

- persistent profile home: `/Users/hulagu_control/.hermes/profiles/hulagu`;
- dedicated Hulagu product/operator Brain: `/Volumes/KurultaiVault/hulagu/brain`, owned by the Hulagu product identities and denied to the Kublai Brain indexer, watcher, gateway, and default retrieval surfaces;
- canonical tenant data: `/Volumes/KurultaiVault/hulagu/tenants/<server-derived-tenant_uuid>/...`, with per-tenant cache, index, vector, and derived-artifact namespaces carrying the same tenant/lifecycle tuple; never bind-mounted into a capsule;
- one-way redacted Kublai projection: `/Users/kublai/brain/raw/hulagu-public-projection/v1`, containing only signed `control_projection_v1` objects and never raw tenant content;
- machine-enforced Kublai denylist: `products/hulagu/policy/kublai-brain-denylist.yaml`, covering the product Brain, tenant roots, quarantine, capsule staging, transcript archive, and all non-redacted derived stores;
- bounded hot transcript outbox: `/Users/hulagu_control/.hermes/transcript-outbox/v1`, owned by `hulagu_control` and readable only by `hulagu_archive` through an explicit ACL;
- Hulagu-owned archive root: `/Volumes/KurultaiVault/hulagu/archive/control-chat/v1`;
- required physical resolution of that archive root: `/Volumes/KurultaiVault/hulagu/archive/control-chat/v1`; G3A fails on a different device, a missing/encryption-unverified mount, a symlink escape below the fixed root, or any fallback path;
- per-run VM state root: `/Users/hulagu_launcher/.lima/hulagu-capsules/<opaque_attempt_id>`;
- guest Docker socket remains inside that VM and is never forwarded or mounted to the macOS host; the Lima state/control paths are service-identity-only (`0700` directories, `0600` files or stricter) and unreadable by `hulagu_control` and `hulagu_app`;
- quarantine restore root: `/Volumes/KurultaiVault/hulagu/quarantine/<restore_id>/...`.

If these identities cannot be provisioned without weakening existing Mac security or requiring an ambient root process, G2 fails and the design halts for an independently reviewed policy amendment. `sandbox-exec` is not the selected primitive and may not be substituted informally.

## 7. Selected capsule-confinement primitive

The selected primitive is **one ephemeral Lima Linux VM per sensitive run, owned only by `hulagu_launcher`, containing one non-root capsule container and one non-root broker/provider proxy container**.

This is the only capsule primitive in this plan. Alternatives such as direct host subprocesses, a shared Colima VM, a shared worker, `sandbox-exec`, a general Docker socket in the persistent profile, or one container/VM serving multiple tenants are rejected. The VM is the tenant boundary; the inner container is defense in depth. Startup cost is accepted for the bounded asynchronous pilot.

### Capsule contract

The launcher instantiates one VM from a digest-pinned Lima template with `mounts: []`, host-directory sharing disabled, swap and guest crash dumps disabled, and VM-level CPU/memory/disk/wall-clock ceilings. The VM name and state path derive only from an opaque broker attempt ID. Inside that VM, the launcher creates one internal Docker network and starts exactly two containers:

1. **Capsule container**
   - image pinned by immutable digest;
   - non-root UID/GID;
   - read-only root filesystem;
   - `CAP_DROP=ALL`, `no-new-privileges`, default seccomp, core dumps disabled;
   - CPU, memory, PIDs, wall-clock, token, and output-byte limits;
   - no host volumes, no Docker socket, no Keychain, no provider token;
   - `HERMES_HOME` and all writable paths on bounded tmpfs with `nodev,nosuid,noexec` where supported;
   - log driver disabled; only structured, redacted receipts leave through the proxy;
   - attached only to the per-run internal network.
2. **Broker/run proxy**
   - generates an ephemeral TLS private key in guest tmpfs; the key never leaves the proxy process;
   - obtains a one-run client certificate from `hulagu_bootstrap`, bound to attempt ID, image/template digests, expiry, and exact `TenantRunAPI/v1` operation set; it holds no bearer capability and no provider credential;
   - attaches to the internal network and a separate restricted egress network that reaches only the host-side broker endpoint;
   - exposes only `TenantRunAPI/v1` operations for its bound run;
   - relays `run.model_infer` to the host broker, which validates tenant/lifecycle state and sends a typed, digest-bound request over the root-owned Unix socket to `hulagu_provider_egress`; only that adapter owns the tenant-plane provider credential and its PF-constrained network route; together they enforce provider allowlist, model pin, token/request budgets, timeout, content-size ceiling, idempotency key, and redacted metering;
   - cannot mount tenant vault roots or the persistent Hermes home;
   - terminates before the network is deleted.

Bootstrap is a fixed protocol, not a launcher-supplied secret. The proxy sends a CSR plus the opaque attempt ID and measured template/image digests. `hulagu_bootstrap` independently compares those values to the G2 policy manifest and the broker's pending attempt, then signs a short-lived client certificate whose fingerprint is stored as the run capability. `hulagu_launcher` normally transports only the CSR and certificate and has no static secret; because it controls the VM, this is explicitly not a no-observation claim; its own mTLS identity receives `403` from both certificate-signing and `TenantRunAPI/v1` routes. Certificate expiry is no later than the run deadline, cannot be refreshed, and revocation is checked on every request. The minimal launcher and bootstrap signer are part of the trusted computing base because the launcher controls VM creation; service separation minimizes credentials and blast radius but is not hardware attestation. G2 must record this residual risk and prove that neither the launcher nor the persistent profile can use signer or run routes during normal operation.

The proxy is a non-root, shell-free, schema-specific service: no HTTP `CONNECT`, generic forwarding, DNS relay, file API, or arbitrary URL field. Guest firewall policy denies capsule traffic to the guest gateway, metadata/control services, and every destination except the proxy port. The proxy may egress only to the mutually authenticated host-side broker address; it cannot resolve or reach an external model provider directly. G2 verifies the effective guest routes and firewall rules; configuration text is not proof.

The capsule receives only a minimal typed work envelope from the proxy. The launcher never converts a model-produced path, shell string, SQL fragment, URL, or tool name into authority.

### Teardown and proof

Normal completion, timeout, cancellation, lease loss, delete, launcher crash recovery, and host reboot all converge on:

1. revoke capability;
2. stop both containers;
3. delete containers and the internal network;
4. stop and delete the entire per-run Lima VM and its state directory;
5. confirm no guest disk, writable layer, tmpfs, network, or control socket survives;
6. write a teardown receipt tied to the run and attempt;
7. let the recovery scanner reconcile anything that died between steps.

G2 must prove negative access using live UIDs and live containers: persistent-to-tenant denial, capsule-to-host denial, capsule-to-provider denial, cross-capsule denial, Docker-socket denial, post-teardown residue absence, timeout kill, and restart cleanup. Installed binaries alone are not proof.

## 8. Two non-overlapping broker APIs

The prior shared broker contract is deleted. The two planes have different routes, schemas, credentials, and operation sets. There is no generic `read(path)`, `query(sql)`, `call_tool(name, args)`, or caller-supplied tenant ID.

### `PublicControlAPI/v1`

Authenticated only as `hulagu_control` or the isolated policy-control service identity. It accepts no tenant capability and returns no tenant payload.

Allowed operations:

- `public_source.submit_url`
- `public_source.fetch`
- `public_source.store_receipt`
- `candidate_bundle.submit_public`
- `candidate_bundle.list_public`
- `control.status_aggregate`
- `control.stop_request`
- `control.proof_debt_list`
- `control.pilot_gate_read`

Responses may contain source URLs, public job facts, code/version identifiers, counts, coarse queue age, pass/fail gate state, and opaque receipt IDs. Responses must not contain tenant UUIDs, namespaces, customer names, CV text, profile answers, draft rows, provider transcripts, lifecycle epochs, run capability material, or row-level operational data.

The Hermes profile may request a fail-safe stop but cannot resume work, pass a gate, change data admission, promote a candidate, or approve an effect. Those operations require a fresh deterministic policy admission and an isolated service credential; they are absent from the profile's tool schema.

### `TenantRunAPI/v1`

Reachable only from the proxy for one bound run. The proxy owns the capability; the capsule cannot mint, widen, refresh, or export it.

Allowed operations are `run.context_read`, `run.public_candidate_read`, `run.checkpoint_submit`, `run.model_infer`, `run.proposal_submit`, `run.complete`, `run.fail`, and bounded `run.lease_renew`.

No operation accepts a caller-supplied tenant, path, provider, model, recipient, or destination.

Provider transport is fixed by `products/hulagu/policies/provider-egress-policy.yaml`. Its default is `enabled: false` and `origins: []`; G4 stays red until the policy compiler admits the exact HTTPS scheme, host, port, and path prefix for one provider. The same row pins SNI, DNS rebinding policy, certificate policy, redirects off, and proxy environment off.

The host broker uses one audited client with `trust_env=false`, redirects disabled, private/link-local DNS denial, per-request DNS pinning, TLS hostname/CA verification, and request/response byte limits. The provider credential is read only after durable budget reservation.

### Mechanical non-overlap checks

G4 fails unless tests show:

- no route or schema name is shared between the APIs;
- the public credential receives `403` for every tenant route;
- the capsule proxy receives `403` for every public-control route;
- tenant fields fail public response-schema validation;
- an expired, replayed, cross-tenant, wrong-epoch, wrong-attempt, or over-budget capability fails before storage or provider access;
- application logs contain only opaque identifiers and redacted metrics.

## 9. Durable authority and recovery semantics

PostgreSQL is the durable source of truth for work state, leases, idempotency, effects, tombstones, and audit receipts. The encrypted vault stores approved artifacts. Neither scratch files nor Hermes sessions are authoritative for product work state. For public/control conversation provenance only, the Section 12 archive becomes the canonical retention copy after verified export; the hot Hermes session database remains operational state until that export is acknowledged.

### Required durable records

At minimum:

- `tenants(tenant_uuid, lifecycle_epoch, status, data_admission_state, ...)`
- `work_items(work_id, tenant_uuid, lifecycle_epoch, work_epoch, state, input_digest, ...)`
- `run_attempts(attempt_id, work_id, lease_owner, lease_until, fencing_token, state, ...)`
- `capabilities(capability_digest, attempt_id, operation_set, expires_at, nonce_state, revoked_at)`
- `outbox(effect_id, tenant_uuid, lifecycle_epoch, work_epoch, run_attempt_id, capability_fingerprint, input_digest, effect_type, external_idempotency_key, payload_digest, state, ...)`
- `effect_receipts(effect_id, destination_receipt, observed_digest, committed_at, ...)`
- `provider_requests(request_id, attempt_id, tenant_uuid, lifecycle_epoch, work_epoch, model_id, prompt_digest, reserved_tokens, reserved_cost, state, provider_request_id, ...)`
- `deletion_tombstones(tenant_uuid, deleted_lifecycle_epoch, reason_code, ...)`
- `migration_ledger(source_digest, quarantine_object, target_object, state, ...)`
- `restore_ledger(restore_id, snapshot_digest, database_generation, vault_generation, schema_version, validation_state, promoted_at)`

A second, non-restored **effect-authority ledger** is authoritative for anti-rollback. It is append-only, hash-chained, signed by the dedicated lifecycle/deletion authority, stored outside tenant database snapshots at `/var/db/hulagu-control/authority-ledger/v1`, and backed up independently. Each entry binds the previous head plus either `(tenant_uuid, minimum_lifecycle_epoch, deletion_state, receipt_digest)` or an external-effect/disclosure tuple `(effect_kind, effect_id, tenant_uuid, lifecycle_epoch, payload_digest, idempotency_key, authority_state, budget_reservation, receipt_digest)`. The ledger therefore carries both lifecycle floors and high-water heads for provider disclosures, delivery effects, revocations, archive acknowledgements, deletion, and generation activation. Runtime checks use `max(database_epoch, lifecycle_floor)` and reconcile database rows forward to every ledger head before any credential or external-effect access; restore and migrator roles can read but cannot lower, omit, or rewrite a head. A database tombstone or effect row is useful evidence but is never the sole anti-rollback authority. A generation can be activated or reactivated only when its activation tuple binds an effect-authority-ledger head at least as new as the live head and all corresponding database rows have been reconciled forward; otherwise startup freezes.

Raw tenant-sensitive payloads remain encrypted artifacts referenced by opaque IDs. Tenant operational logs and receipts carry hashes, sizes, status, and redacted reason codes, not payload bodies. The separate public/control chat archive in Section 12 intentionally contains conversation bodies under its narrower access and indexing policy; it must never receive tenant payloads.

### Canonical state machine

```text
QUEUED
  -> LEASED
  -> RUNNING
  -> PROPOSAL_RECEIVED
  -> VALIDATED
  -> EFFECT_QUEUED
  -> EFFECT_COMMITTED

Any pre-commit state may become:
  CANCELLED | SUPERSEDED | FAILED_RETRYABLE | FAILED_TERMINAL

An effect with an uncertain provider response becomes:
  RECONCILE_REQUIRED
```

A work item may have several attempts, but only the attempt holding the current fencing token may advance it. Pause, resume, delete, or supersession increments `work_epoch` or `lifecycle_epoch`, invalidating old leases, capabilities, outputs, and effects.

Each dispatch re-reads the full outbox authority tuple and current tenant/work epochs immediately before credential access and first byte; any mismatch is terminal before transmission.

### Transaction boundaries

- **Lease:** select and lease work in one database transaction using compare-and-swap/fencing. Process death after commit is recovered by lease expiry.
- **Proposal:** store proposal digest and state transition atomically. A model call is never itself a durable effect.
- **Effect enqueue:** validated state transition and outbox row commit in the same transaction.
- **External effect:** deliver at least once with a stable destination idempotency key. Then read back destination state and persist an effect receipt.
- **Ambiguous outcome:** if timeout occurs after the provider may have accepted the request, mark `RECONCILE_REQUIRED`; do not blind-retry. A reconciler performs provider readback or remains a fail-closed terminal incident without automated resend.
- **Completion:** only an observed receipt with expected digest moves an effect to `EFFECT_COMMITTED`.

### Model-disclosure ledger

A provider call is an external disclosure even when it creates no product-side mutation. The crash boundary is defined by durable authority, not by an in-memory `first_byte` flag. Before the credential adapter can read its Keychain item or open a provider socket, the broker and ledger authority execute this forward-only protocol:

1. in one database transaction, validate current tenant/lifecycle/work epochs and run-certificate fingerprint, reserve worst-case tokens/cost against tenant/run/global budgets, and insert `provider_requests` as `RESERVED` with model/version, prompt digest, redacted data classes, retention-policy version, exact idempotency key, and adapter-policy digest;
2. append and fsync a signed `DISCLOSURE_INTENT_DURABLE` entry to the non-restored effect-authority ledger, binding the request row, payload digest, budget reservation, lifecycle epoch, idempotency key, and one-use adapter ticket digest;
3. mark the database row `DISCLOSURE_INTENT_DURABLE` only after ledger readback; if the process dies between steps 2 and 3, recovery reconstructs the row from the ledger and treats the disclosure as possibly sent;
4. only then present the one-use ticket to `hulagu_provider_egress`, which atomically consumes it before Keychain access or socket creation. The earliest point at which any request byte may escape is **after** the durable intent and budget charge, never before;
5. append and fsync either a provider receipt/readback record or `DISCLOSURE_RECONCILE_REQUIRED`, then reconcile the database row forward. Observed usage may lower the reserved budget only after a verified terminal receipt.

The allowed states are `RESERVED -> DISCLOSURE_INTENT_DURABLE -> DISPATCHING -> DISCLOSURE_CONFIRMED | DISCLOSURE_RECONCILE_REQUIRED`, plus `CANCELLED_PRE_SEND` only while still `RESERVED`. A process restart, host reboot, database restore, or generation rollback may never replay a consumed or possibly consumed ticket. It must first perform provider readback using the same provider request/idempotency identity. When the provider offers neither trustworthy idempotency nor readback, an ambiguous request remains incident-held and non-retriable and budget-consumed; automated resend is forbidden. Kill tests cover every boundary before and after ledger fsync, database reconciliation, ticket consumption, credential access, socket connect, first byte, provider acceptance, response receipt, host reboot, stale-snapshot restore, and rollback activation. They prove no first byte precedes durable intent, no duplicate disclosure is possible after a crash, and every restored generation rolls forward to the live disclosure head before serving.

### Revocation and tombstone fence against in-flight effects

Every external dispatcher acquires a tenant/lifecycle shared dispatch fence and re-reads lifecycle state before its first irreversible byte. Revocation acquires the exclusive fence, advances the non-restored lifecycle floor, revokes run certificates/leases, cancels queued outbox rows, and prevents new shared fences. Ambiguous remote outcomes remain incident-held, encrypted locator metadata remains available only to the deletion service, and no autonomous transition claims physical erasure. `TOMBSTONE_ONLY` is the terminal state under autonomy v1; `LOCAL_PURGED` and `DELETED_FINAL` are unreachable and policy-denied.

Restore loads the non-restored authority ledger and tombstone chain first, rolls database rows forward, and rejects old-epoch access. Tests kill every fence/ledger boundary and prove no post-fence effect commits, no stale epoch revives, and no hard-delete action is admitted.

### Restart behavior

On broker, launcher, proxy, capsule, Postgres, or host restart:

1. recovery scanner revokes expired capabilities;
2. stale leases are fenced and requeued only if attempt budget remains;
3. orphan Lima VMs, guest containers, and guest networks are correlated by opaque attempt label, terminated, force-deleted, and receipted;
4. `RECONCILE_REQUIRED` effects are read back before retry;
5. tombstone and epoch checks run before any resumed access;
6. work resumes from durable checkpoints only, never from a surviving Hermes conversation or container filesystem.

G3B/G4 tests kill the process immediately before and after each transaction boundary and prove no cross-tenant read, duplicate durable effect, stale-epoch commit, or unreceipted completion.

## 10. Migration, backup, and restore before data use

Migration and restore move before profile installation and before any data admission.

### Data-admission fuse

`data_admission_state` has only `BLOCKED`, `SYNTHETIC_ONLY`, and `POLICY_ADMITTED`. It defaults to `BLOCKED`. Existing Buildroom/control-room status displays it with the gate and receipt that last changed it. No Hermes profile, cron job, or model can change it.

### Quarantine-first migration

G3A performs read-only discovery and freezes the signed migration map. G3C, and only G3C, performs the copy:

1. inventory legacy tenant rows, product-Brain objects, vault artifacts, caches, indexes, vectors, drafts, exports, archive outbox, and delivery destinations;
2. write hash-only mapping into the migration ledger without printing raw sensitive content;
3. acquire the migration lease and stop legacy writers;
4. copy into per-run quarantine roots and a new DB namespace using opaque tenant/epoch IDs;
5. validate ownership, counts, digests, RLS/composite FKs, per-tenant derived namespaces, ACLs, no-follow path confinement, tombstones, and archive sequence parity;
6. require an independent reconciliation receipt before G3D;
7. leave any mismatch quarantined with `MIGRATION_BLOCKED`; no partial promotion exists.

If no legacy customer data is found, G3A records a signed zero-inventory receipt and G3C verifies the same inventory immediately before copy. Absence is proven, not assumed. G3E alone can promote and then revoke all legacy DB roles, file ACLs, indexes, queues, and fallback paths.

### Backup and restore drill

Before G3D passes, the evidence producer must:

- create an encrypted snapshot with a unit manifest binding database generation, vault generation, the non-restored effect-authority-ledger head, schema version, retention metadata, and digests;
- restore into a new quarantine root and a new database namespace;
- validate schema version, row and object counts, hashes, RLS, tenant epochs and every disclosure/effect/revocation/archive head against the non-restored effect-authority ledger, outbox state, and snapshot-unit pairing;
- run a synthetic resumed work item without using the production namespace;
- prove that a deleted epoch cannot reappear;
- destroy the drill restore after receipt capture.

Database, vault, product-Brain, and archive promotion use one crash-safe generation protocol:

1. set global `RESTORE_FROZEN`, block data admission, stop new leases/dispatch fences, and drain or reconcile active work and archive events;
2. restore immutable candidate database `D<n>`, vault `V<n>`, product-Brain `B<n>`, and archive `A<n>` generations without changing the active tuple;
3. validate all four against one snapshot-unit manifest, schema, object hashes, RLS, derived-namespace parity, archive sequence root, outbox/provider rows, and the complete live effect-authority-ledger head;
4. reconcile the restored database forward from the non-restored ledger until every lifecycle, disclosure, delivery, revocation, archive-ACK, and deletion row equals that head; any ambiguity stays fail-closed and is never resent merely because the snapshot is old;
5. append one signed activation record `(D<n>, V<n>, B<n>, A<n>, manifest_digest, effect_authority_ledger_head)` to the separate control namespace;
6. restart into exactly that tuple; startup refuses a missing object, mismatched digest, lower or omitted authority head, archive gap, unresolved replay candidate, or partially written generation;
7. rollback only by appending a new activation record for a previously validated tuple after reconciling it forward to an effect-authority-ledger head no lower than the live head—never by rewinding the control namespace or mutating a generation in place.

Kill tests stop the process after every step and prove the active tuple is always the old complete tuple, the new complete tuple, or a fail-closed frozen state—never a mixed generation.

G3A freezes the policy-bound capacity manifest; G3B enforces it before allocation. Per-tenant database/vault/output/provider quotas are enforced before allocation. The global low-water threshold for each durable store is `max(20% of store capacity, 2 × maximum tenant quota, one full estimated backup unit)`; the emergency stop threshold is `max(10% of capacity, one maximum tenant quota)`. Crossing low water blocks new admissions and effects; crossing emergency sets global stop. Backup destination capacity is checked before snapshot. There is no fallback to a user home, `/tmp`, an unencrypted volume, in-memory durable state, or an alternate provider.

Startup refuses `POLICY_ADMITTED` data admission unless the current database/vault generation has a matching clean migration receipt, verified restore generation, current effect-authority-ledger head, zero unreconciled rollback candidates, and capacity state above low water.

## 11. Native Hermes profile distribution

There is one packaging path: a source-controlled native Hermes distribution rooted at:

```text
products/hulagu/hermes-distribution/
├── distribution.yaml
├── SOUL.md
├── config.yaml
├── mcp.json
├── skills/
├── cron/
├── plugins/
└── README.md
```

There is no `profile-manifest.yaml` and no custom installer contract.

The manifest uses native `distribution.yaml` with `hermes_requires: "==0.18.0"`. The only release source is clean commit `bf73dec9319047c0883d9e682c019dd2f38fe7e0` plus the two exact G1 patch files bound by `PATCHSET.json`; the live dirty checkout is never a release input. Hermes does not enforce a `distribution_owned` sentinel, so `products/hulagu/deploy/scripts/promote_profile_distribution.py` is the mandatory root-owned boundary. It reads `products/hulagu/hermes-distribution/distribution-allowlist.json`, verifies every allowed relative path, type, mode, and SHA-256; recursively rejects undeclared paths, symlinks, devices, sockets, setuid/setgid/world-writable files, secrets, auth, sessions, memories, state databases, logs, workspace data, and customer artifacts; copies only verified bytes into a fresh root-owned candidate directory; then atomically promotes that closed tree. The helper never asks Hermes to merge an unchecked checkout. G5 mutation tests add one undeclared file and one forbidden type at every source subtree and require rejection before profile install/update.

G1 owns one reproducible runtime-build contract rather than merely pinning a source commit. It source-controls and tests `products/hulagu/deploy/scripts/build_hulagu_runtime.py`, `products/hulagu/deploy/scripts/render_control_gateway_plist.py`, and their schemas, but **does not** write `/opt`, `/Library/LaunchDaemons`, a service-account home, or any other host-runtime path. G1 must:

1. create a clean detached source directory from `bf73dec9319047c0883d9e682c019dd2f38fe7e0`, verify the commit/tree and copied `uv.lock`, apply only the two patch bytes named by `PATCHSET.json`, and prove `git diff --check` plus a closed tree manifest;
2. record the absolute realpaths and SHA-256 digests of `/opt/homebrew/bin/uv`, the selected CPython executable, `uv.lock`, both patches, `pyproject.toml`, and every source file consumed; materialize and hash the locked dependency cache in an unprivileged scratch directory, then disable network access;
3. derive `RUNTIME_ID = sha256(canonical runtime-source manifest)` and emit `products/hulagu/qa/gates/G1-source-contracts/runtime-build-plan-v1.json`, whose closed argv and destination schema require the final non-relocatable path `/opt/hulagu/hermes/<64-lower-hex-runtime-id>/venv`; G1 validates this packet and runs parser/source tests but does not execute its privileged build;
4. prove with synthetic roots that the builder rejects any source-worktree symlink/import path/shebang, undeclared cache input, unlocked dependency, destination mismatch, unresolved token, or unmanifested executable; and
5. bind the builder, renderer, schemas, source manifest, cache manifest, test-node manifest, and exact future G5 command shape into the G1 payload/evidence closure.

G2 promotes byte-identical, dependency-closed copies of the approved builder and renderer into `/opt/hulagu/promotion/v1/bin/` before any profile/runtime exists. Under a separately signed G5 start packet, the root-owned builder creates the virtual environment directly at the final packet-derived path with `UV_PROJECT_ENVIRONMENT` equal to that path and runs `/opt/homebrew/bin/uv sync --frozen --no-dev --no-editable --python <recorded-realpath>` against the patched clean source. It then removes build caches, rejects any source-worktree or unmanifested reference, sets the runtime tree root-owned/read-only, hashes every installed file/mode/interpreter/package/entry point/dependency, runs the pinned Hermes CLI/parser/plugin/scheduler/archive-patch matrix from that runtime, and writes `/var/db/hulagu-control/gates/G5/runtime-package-v1.json` before the promotion packet is signed. The angle-bracket notation in this prose describes schema fields and is never accepted in executable bytes.

Only after that G5 runtime receipt exists does the root-owned renderer write `/var/db/hulagu-control/gates/G5/ai.hulagu.control-gateway.plist`. The operational plist contains literal `ProgramArguments` and `WorkingDirectory` strings, never `${...}`, `{{...}}`, shell expansion, PATH lookup, or an unpromoted worktree path. `install_control_gateway_launchdaemon.py` rejects unresolved-token bytes (`${`, `{{`, `}}`, `<RUNTIME`, `<POLICY`, `<COMMIT`), hashes its own source plus the plist and runtime receipt, copies to the root-owned destination, reads back the installed plist, and requires `launchctl print` to show exactly the receipt-bound executable/user/environment. The G5 rollback packet is generated at the same time and names the previous literal runtime/distribution/plist hashes; if no previous tuple exists, rollback means stop-and-remove-candidate, not an invented path.

G5 stages two root-owned, read-only artifacts from the approved commit and records their directory-tree digests:

- version-pinned Hermes runtime at the exact `runtime_path` recorded in `/var/db/hulagu-control/gates/G5/runtime-package-v1.json` (schema shape `/opt/hulagu/hermes/<64-lower-hex-runtime-id>/venv/bin/hermes`);
- candidate distribution at the exact `candidate_distribution_path` recorded in the G5 promotion packet (schema shape `/opt/hulagu/staging/<40-lower-hex-git-commit>/hermes-distribution`).

Angle-bracket strings above describe validated schema fields only; they never appear in an executable file. Neither path is a mutable worktree. After candidate validation and machine-policy admission, the byte-pinned root-owned helper `/opt/hulagu/promotion/v1/bin/promote_profile.py` stops the profile, validates the signed promotion packet, atomically swaps the candidate into the stable recorded source path `/opt/hulagu/distributions/hulagu`, retains the previous tree for rollback, and records candidate, promoted-source, runtime, command, and commit digests. The service account receives read/execute permission only.

The single install invocation is:

```bash
sudo /usr/bin/python3 /opt/hulagu/promotion/v1/bin/promote_profile.py --packet /var/db/hulagu-control/gates/G5/promotion-packet.json --action install
```

The single update invocation is the same helper with `--action update`. The signed packet contains a closed argv array with the literal runtime executable path and native `profile install` or `profile update hulagu --force-config --yes` arguments, plus scrubbed environment, candidate path, current/previous digests, timeout, and rollback argv. The helper rejects PATH lookup, unresolved tokens, symlinks, extra arguments, or a runtime/distribution/plist hash not equal to the packet; it executes without a shell under the `hulagu_control` UID and reads back Hermes' recorded distribution source and installed profile tree.

If readback or smoke verification fails, the helper keeps the profile stopped, atomically restores the previous stable source, executes the packet's byte-bound rollback argv against the previous literal runtime, and emits a rollback receipt. `--force-config` is allowed only because the reviewed distribution owns the public-only tool surface; G5 readback must prove the installed config digest. Normal unattended update is forbidden.

The profile has:

- only public web/GitHub/research tools, its dedicated low-budget public-plane model credential, and the `PublicControlAPI/v1` client;
- no terminal, filesystem, computer-use, credential-management, provider-direct, database, vault, Sheets, email, cron-management, capsule-launch, or tenant API tool;
- no persistent memory or session content derived from tenants;
- no customer-facing gateway through G11;
- a byte-stable system prompt for each conversation and a versioned public research contract.

The service identity's network policy permits only the dedicated public-plane model endpoint and a deterministic public-source fetcher. The fetcher allows HTTPS only, revalidates every redirect and resolved address, blocks loopback/link-local/private/Unix-socket destinations and DNS rebinding, caps bytes/decompression/time, stores source bytes with hashes, and treats all retrieved instructions as untrusted data. G5/G6 include SSRF, redirect, decompression-bomb, prompt-injection, and private-address denial probes.

G5 tests install from the root-owned stable distribution source after candidate promotion into a fresh service-account home, install the separately source-controlled observer/exporter/archiver bytes by chained-manifest digest, run the pinned runtime's `profile info hulagu`, enumerate effective tools/hooks, network rules, and cron files, compare digests, exercise the archive path with synthetic conversations only, and scan the installed tree for forbidden paths/secrets. The same gate must prove the pinned CLI accepts every planned `-p hulagu` gateway/cron command and the generated `hulagu` alias resolves to the same profile root.

Staged retirement is drain-first and quarantine-only. The autonomous safety controller stops new ingress, reconciles every archive/effect receipt, revokes capabilities and credential ACLs, verifies sequence parity, and atomically moves the profile tree to a root-owned quarantine generation. It must not invoke native profile deletion or remove archive/tenant bytes. Missing drive, gap, corrupt ACK, active lease, invalid policy admission, unverified runtime packet, or unarchived event leaves the profile stopped and intact.

G5 tests retirement, remount/reconcile, kill-at-each-step, retry, zero-lag arrival, exact parser behavior, and static rejection of any hard-delete entrypoint. Legal/privacy hard deletion is outside autonomous authority and outside this implementation controller.

## 12. Full conversation archive on the 4 TB Brain volume

The operator provenance requirement is a **complete, replayable archive of every observable conversation handled by the persistent `hulagu_control` profile**, stored through Brain's existing raw cold tier on the external 4 TB KurultaiVault drive. “Full” means the complete observable interaction record, not a summary and not a periodic best-effort copy. It does **not** mean hidden provider chain-of-thought, credential values, tenant capsule prompts/provider payloads, or data from a future customer-facing gateway.

### Storage boundary and source of truth

The logical archive root is:

```text
/Volumes/KurultaiVault/hulagu/archive/control-chat/v1
```

At runtime G3A must prove, by resolved path plus volume UUID/device readback, that it is physically on:

```text
/Volumes/KurultaiVault/hulagu/archive/control-chat/v1
```

The archive root is outside Git and outside the Kublai Brain namespace, on the existing encrypted 4 TB KurultaiVault. It is not a second Brain, a second control room, or a hot product-state dependency. The active Hermes `/Users/hulagu_control/.hermes/profiles/hulagu/state.db` stays on the internal hot tier so an unmounted cold drive does not corrupt a live session. Merely symlinking the SQLite database to the external drive, periodically copying it, or retaining only a final transcript is rejected: those designs can miss destructive history rewrites, turn the removable disk into a hot dependency, and provide no per-event acknowledgement.

### Capture mechanism

G1 implements one source-controlled, tool-free Hermes observer at:

```text
products/hulagu/hermes-distribution/plugins/hulagu-transcript-archive/
```

G5 installs its reviewed, digest-pinned bytes read-only at:

```text
/Users/hulagu_control/.hermes/profiles/hulagu/plugins/hulagu-transcript-archive/
```

and enables only that exact plugin key in `plugins.enabled`. The pinned Hermes commit exposes `discover_plugins(force=False)`, `get_plugin_manager()`, and `hermes_constants.get_hermes_home()`; it exposes neither `get_plugins_dir` nor a profile argument on `discover_plugins`. G1 therefore runs a temporary-home fixture through those exact pinned call signatures, and G5 runs the installed profile through `/opt/hulagu/launcher/v1/bin/hulagu-hermes --active-runtime-packet /var/db/hulagu-control/active-runtime.json -p hulagu plugins list --user --json`. Both probes require exactly one row with `key == "hulagu-transcript-archive"`, `source == "user"`, and `enabled == true`. A second pinned-source probe calls `discover_plugins(force=True)`, reads `get_plugin_manager()._plugins["hulagu-transcript-archive"].manifest.path`, and asserts its resolved parent is exactly `get_hermes_home().resolve() / "plugins"` and its resolved path is exactly `/Users/hulagu_control/.hermes/profiles/hulagu/plugins/hulagu-transcript-archive`; any global `~/.hermes/plugins` resolution, alternate duplicate, missing row, load error, or outside-root path fails. The private `_plugins` read is intentionally pinned-source introspection and must be re-reviewed if the Hermes commit changes. The plugin supplies a pure event encoder/redactor plus a file-spool exporter: no model-visible tool, slash command, CLI command, network client, filesystem browser, or archive-read operation. It cannot open KurultaiVault. A separate non-model `hulagu_archive` worker reads exported objects and is the only daemon allowed to write the fixed archive subtree.

The currently inspected Hermes implementation persists sessions in `/Users/hulagu_control/.hermes/profiles/hulagu/state.db` and exposes observer hooks including `post_llm_call`, `post_tool_call`, `on_session_reset`, and `on_session_end`; some session operations can replace or delete active rows. Those observations guide coverage but are not the durability boundary. G1 **always** carries the smallest reviewed Hermes core patch that invokes the pure encoder before visibility and inserts the canonical redacted event into append-only `archive_event_outbox` in the same SQLite transaction as every observable session mutation. One transaction commits both the source mutation and outbox row or neither. Polling, periodic SQLite copies, hook-only post-commit capture, and best effort are forbidden. G1 pins one exact Hermes source commit and runs the black-box mutation matrix over normal turns, tools, retries, undo, reset, compaction, gateway delivery, error, cancellation, and process death. The patch, tests, source commit, wheel/tree digest, and installed binary digest enter the G1/G5 chained manifests.

The SQLite `archive_event_outbox` is the sole authoritative local queue. After commit, the exporter materializes a deterministic `O_EXCL` object under `/Users/hulagu_control/.hermes/transcript-outbox/v1/events/`, fsyncs file and directory, and may recreate it from the row after any crash. `hulagu_archive` reads `events/`, writes only digest-bound ACK receipts under the ACL-separated `acks/` subdirectory; each ACK signs `(event_id, canonical_digest, archive_manifest_head, UTC_time)` with the `hulagu_archive` key whose public key alone is pinned in `hulagu_control`, and cannot mutate the session DB or delete event objects. The `hulagu_control` reconciler validates an ACK against the SQLite row, marks that row ACKED, and only then garbage-collects the derived event object under the signed retention/compaction rule. Thus a profile stop, exporter crash, or missing file never destroys the source queue.

### Archive event and delivery state machine

The observer identity is `observer_event_id = sha256(profile_uuid || archive_session_id || source_event_seq || event_kind || canonical_payload_digest)`. `source_event_seq` is allocated monotonically in the same session transaction; events are totally ordered within one archive session and unordered across sessions. Retries, edits, undo, reset, compaction, and history replacement append new event kinds and never reuse or erase a prior sequence. One mutation commits either both session change and observer-outbox row, or neither.

Delivery states are `OUTBOX_DB_COMMITTED -> SPOOL_DURABLE -> ARCHIVE_STAGED -> MANIFEST_COMMITTED -> READBACK_VERIFIED -> ACK_DURABLE -> ACK_RECONCILED`; `GAP_BLOCKED`, `POISON_QUARANTINED`, and `INTEGRITY_ERROR` are fail-closed side states. The archiver may receive duplicates or out-of-order events: duplicates with the same ID/digest are no-ops; a higher sequence with a gap remains durable but unpromoted; a same ID/different digest is an integrity incident. Gap repair rematerializes the exact source row by sequence; it never infers from mutable session history. A poison event is copied to a descriptor-confined quarantine with redacted metadata, blocks that session at the missing sequence, and stops new profile runs when the approved age/size limit is crossed. Cancellation after the joint transaction commits leaves the event replayable; cancellation before commit leaves neither message mutation nor event.

`products/hulagu/tests/fixtures/archive-mutations.jsonl` is the minimum black-box corpus. It includes 60 cases: 10 normal/manual/gateway/cron turns, 10 tool success/error/cancel cases, 10 retry/undo/edit/history-replacement cases, 10 reset/compaction/rename/end cases, 10 duplicate/gap/poison/crash cases, and 10 secret/tenant-canary/hidden-reasoning exclusions. Every case specifies expected source sequence, event kind, visible payload digest, outbox state, archive state, and replay transcript digest. G1/G5 run all 60 plus 100 deterministic property-test seeds; zero required case may skip.

### What each event contains

Every event conforms to `hulagu-chat-archive-event-v1.schema.json` and binds at least:

- random opaque archive session ID, monotonic event sequence, stable event ID, prior-event digest, schema version, and UTC timestamp;
- source profile, Hermes/runtime version, system-prompt version and byte digest, model/provider identifiers, and invocation kind (`manual`, `gateway`, or `cron`);
- complete user-visible user and assistant message content, preserving order and content type;
- complete public-plane tool call name, arguments, result/error, timing, and call ID in the order observed by the model;
- platform/chat/thread/message identifiers and delivery outcome when a gateway is later separately authorized;
- session start/end/rename, retry, undo, reset, compaction, cancellation, edit/history-replacement, and error events rather than silently rewriting prior archive bytes;
- attachment metadata plus a content-addressed blob reference when the attachment is policy-permitted;
- redaction records naming the field and policy rule whenever a forbidden credential-like value is replaced with `[REDACTED]`.

System-prompt bytes may be captured once per distinct prompt digest and referenced thereafter. Provider-hidden reasoning fields, internal chain-of-thought, auth headers, cookies, `.env` values, Keychain values, portable bearer material, and tenant-plane payloads are forbidden even if an upstream library exposes them. Secret filtering occurs before the outbox write; low-entropy secret values are not preserved as plain hashes. A detected tenant canary or unredactable secret fails the event, raises an incident receipt, and stops new profile runs rather than persisting it or silently claiming a complete archive.

### On-disk format

The versioned layout is:

```text
v1/
├── sessions/<hh>/<opaque_session_id>/
│   ├── session.json
│   ├── segments/<12-digit-sequence>-<event_id>.json.zst
│   ├── manifests/<12-digit-generation>.json
│   └── HEAD
├── blobs/sha256/<hh>/<digest>
├── receipts/YYYY/MM/DD/<receipt_id>.json
├── tombstones/<opaque_session_id>/<generation>.json
└── policy/archive-policy-v1.json
```

Paths derive only from validated opaque IDs and fixed partitions. Segment JSON is canonical UTF-8, then deterministically compressed; the manifest records compressed and uncompressed SHA-256, byte counts, schema, sequence range, and previous-manifest digest. Each manifest generation is immutable. `HEAD` is only an atomic convenience pointer; recovery finds the highest valid hash-linked generation and never trusts `HEAD` alone. Root/session directories are `0700` and files `0600` or stricter, owned according to the G2 ACL receipt. The external APFS volume must be encrypted and Owners Enabled. Any additional application-envelope encryption is a threat-model decision frozen at G3; it may strengthen but not replace volume identity, ACL, and indexing controls.

### Commit, acknowledgement, and recovery

For each event:

1. the joint session transaction validates/redacts the canonical event, allocates its sequence, inserts the immutable SQLite outbox row, and commits it with the source mutation;
2. the `hulagu_control` exporter materializes the deterministic `O_EXCL` event object from that row and fsyncs file and directory; retries compare the canonical digest and never fork bytes;
3. `hulagu_archive` verifies the expected mounted-volume UUID/device, encryption/ownership state, fixed descriptor-confined root, no-follow path walk, capacity band, event schema, sequence, and prior digest;
4. it writes a temporary segment in the target directory, fsyncs it, atomically renames it, fsyncs the directory, writes the next immutable manifest generation, and atomically advances `HEAD`;
5. it reopens through the confined descriptor, decompresses, recomputes the canonical digest, and writes a digest-bound ACK receipt into `acks/`;
6. the reconciler validates that ACK against the SQLite row, marks `ACK_RECONCILED`, and only then may delete the derived event object or compact the acknowledged row.

Delivery is at least once. `(archive_session_id, event_id, canonical_digest)` is the idempotency tuple. Replaying the same tuple and digest is a no-op with a duplicate receipt; the same event ID with different bytes is a fail-closed integrity incident. Startup first scans unacknowledged SQLite rows, rematerializes missing/mismatched derived objects, reconciles ACK receipts, and then validates temporary archive files, manifest chains, and stale `HEAD` pointers before accepting new profile work. Kill tests stop after every step and prove no acknowledged gap, sequence fork, corrupt promoted segment, duplicate logical event, or loss caused by an exporter/profile restart.

### Drive absence, capacity, and no fallback

If KurultaiVault is absent or fails identity/encryption/ACL/capacity checks, the observer continues only into the bounded local outbox while control-room state becomes `SPOOLING`. The G3A capacity manifest fixes both a maximum local spool size and maximum unarchived age. Crossing either limit sets `STOP_CHAT_ARCHIVE` and refuses new manual, gateway, and cron profile runs; policy-controlled stop/export/quarantine/recovery operations remain available outside the model. There is no fallback to another directory, `/tmp`, another disk, curated Brain markdown, an in-memory queue, or a tenant root. On a valid remount, the worker reconciles oldest-first and normal operation resumes only after lag and integrity checks are green.

Archive capacity uses the existing Section 10 low-water and emergency-stop policy. Buildroom/control-room receives only signed aggregate archive state: mount identity state, `HEALTHY|SPOOLING|STOPPED|INTEGRITY_ERROR`, coarse spool/capacity bands, oldest unarchived age bucket, last verified receipt time, policy digest, and proof debt. It receives no message body, chat/session/platform identifier, path, or event payload.

### Indexing, access, retention, export, and no-delete policy

The raw archive is denied to `hulagu_control`, tenant identities, default Brain search/index/embedding jobs, synthesis, `/study`, cron, and normal backup browsing. G3A freezes the denylist and G5 proves exclusion through every live retrieval route using a unique canary. Only an offline policy-scoped export role may read payloads, and every export records scope, reason, policy digest, event count, and output digest without copying bodies into control-plane logs.

`archive-policy-v1.json` defaults to retain, do not index, do not summarize, do not share, and do not hard-delete. Autonomous implementation may build and test tombstone/quarantine mechanics with synthetic fixtures, but the runtime policy permanently denies hard deletes and declassification. G5/G6 require complete replay, mutation-history preservation, secret/tenant-canary exclusion, no model/default-Brain read path, wrong-volume/spool-stop behavior, duplicate/crash recovery, and read-only synthetic export.

## 13. Enforced cron policy

Cron is source-controlled policy compiled into the native distribution and independently enforced by the broker.

`products/hulagu/hermes-distribution/cron-policy.yaml` is the only job-definition source. A deterministic compiler emits the native single store `products/hulagu/hermes-distribution/cron/jobs.json`, an immutable normalized-policy manifest, and a runtime-state schema; no `cron/*.json` layout is accepted. Each job is installed disabled and declares:

- immutable job ID `hulagu-control-public-research-v1` and policy-manifest digest;
- exact schedule and timezone;
- exact `model.provider` and `model.model` identifiers bound to the dedicated public-plane credential class, with `fallback_models: []`; provider failure is terminal for that tick and never selects a broader model or credential;
- `enabled_toolsets` allowlist containing public research only;
- wall-clock, model-call, token, network-request, and output-byte ceilings;
- non-overlap policy and one active lease;
- stable idempotency key derived from job ID and scheduled tick;
- retry count/backoff and terminal-failure rule;
- delivery disabled unless an preauthorized aggregate destination exists;
- no `cronjob` tool, no recursive scheduling, no capsule launcher, no tenant API, and no direct external effect.

The live-store contract has two explicit projections. Immutable policy fields are job ID, schedule/timezone, prompt/payload digest, provider/model/fallback list, toolsets, budgets, delivery, repeat/overlap rule, and policy-manifest digest; those must equal compiler output. Mutable runtime fields are `enabled`, `state`, `next_run_at`, `last_run_at`, run/error counters, and lease/claim metadata; those must satisfy `products/hulagu/schemas/cron-runtime-state-v1.schema.json` and its transition table. `next_run_at` is derived from the immutable schedule plus the last committed tick, never compared to an install-time literal. Enabling requires a content-addressed policy-admission receipt binding exact job ID, immutable-policy digest, activation epoch/window, shadow receipt, and `enabled=true`. Runtime state cannot silently weaken policy, and the activation receipt is authorization metadata—not a second job-definition source.

The only selected scheduler is Hermes's built-in gateway scheduler. G5 rejects a configured `cron.provider` that is non-empty and not exactly the built-in provider; it does not rely on resolver fallback. After the runtime receipt exists, G5 uses the promoted root-owned renderer to create a fully literal operational plist under `/var/db/hulagu-control/gates/G5/` and installs that exact verified byte sequence as a macOS LaunchDaemon running as `hulagu_control`. The installed plist has the literal ProgramArguments `[/opt/hulagu/launcher/v1/bin/hulagu-hermes, --active-runtime-packet, /var/db/hulagu-control/active-runtime.json, -p, hulagu, gateway, run]`. The root-owned launcher re-verifies the signed active-runtime tuple and exact package/tree/binary digests, then `execve`s the manifest's literal runtime path; it fails rather than following a symlink or unresolved token. The plist sets only `HOME=/Users/hulagu_control` and `HERMES_HOME=/Users/hulagu_control/.hermes`; the scrubbed service account has no channel/webhook tokens, `home_channels`, inbound listener, or customer adapter. The authorized executor uses only the already-promoted root-owned helpers:

```bash
sudo /usr/bin/python3 /opt/hulagu/promotion/v1/bin/install_control_gateway.py --packet /var/db/hulagu-control/gates/G5/launchdaemon-promotion-packet.json --action install-bootstrap-readback
sudo launchctl print system/ai.hulagu.control-gateway
sudo /usr/bin/python3 /opt/hulagu/safety/v1/bin/stop_hulagu.py --reason planned_gate_test --runtime-packet /var/db/hulagu-control/active-runtime.json --receipt /var/db/hulagu-control/evidence/G5/launchdaemon-stop.json
```

The install helper verifies its own pinned digest, the signed packet, source-plist digest, literal ProgramArguments, and absence of all unresolved-token syntaxes; copies rather than symlinks; sets `root:wheel`/`0644`; and read-backs the installed hash, launchctl label, UID, environment, and effective ProgramArguments before bootstrap. The safety helper writes the planned-stop marker before reducing authority, blocks new broker/cron/provider tickets, drains or fences active leases/archive commits, captures the current PID/start-time tuple, performs `launchctl bootout`, waits for label and process exit, and only then sends TERM/KILL to that captured PID as a bounded fallback after proving it was not replaced. It verifies no label, process, active claim, provider intent, or post-stop scheduler tick remains. A dirty source checkout may block build/resume/rollback but may never block stop. Unload and host reboot/startup tests are mandatory.

`products/hulagu/hermes-patches/cron-policy-hook.patch` is the second exact Hermes core patch. Because native due-job reads may repair, advance, and save state before returning, authorization **must not** occur after `get_due_jobs()`. The patch places `CronPolicyGuard` inside every native store/dispatch entrypoint—scheduled batch, managed-provider dispatch, and direct `run_one_job()`—under the same jobs-store lock and before any parse-repair save, claim, lease, `next_run_at` advance, provider/model/tool access, or user code. The guard snapshots and digests the raw store, validates every row's immutable projection and mutable-state transition/receipt, rejects all non-built-in providers, and returns an authorized snapshot token that the mutation path must consume under the unchanged digest. An insert or edit between admission and claim invalidates the token and retries from admission; it never executes from a stale approval.

Denial executes no job and leaves `cron/jobs.json` byte-identical: no repair, lease, claim, counter, or `next_run_at` write. A separate redacted refusal receipt records the pre-mutation digest, sets aggregate `cron_policy_state=DRIFTED`, and emits a machine incident receipt. G1 adds mutation/race tests for malformed stores, unknown jobs, immutable drift, illegal mutable transitions, widened tools, provider/model fallback, non-built-in provider selection, schedule/budget drift, missing or stale activation receipt, insert-after-check, direct `run_one_job()` dispatch, and guard exception. G5 binds the tested Hermes source commit, patch digest, wheel/tree digest, and installed binary digest; an unpatched runtime cannot pass.

Native distribution install leaves the single `cron/jobs.json` store disabled. G9 does **not** create jobs dynamically. It verifies the immutable projection against the compiler output and the disabled mutable projection against the runtime-state schema using both direct file readback and `/opt/hulagu/launcher/v1/bin/hulagu-hermes --active-runtime-packet /var/db/hulagu-control/active-runtime.json -p hulagu cron list --all` under the scrubbed `hulagu_control` environment. After `no_effect_shadow`, activation is allowed only through the active G9 command packet's literal `activate_hulagu_cron.py` argv bound to the exact policy-admission receipt and job ID; the wrapper invokes native `cron resume`, validates the exact post-transition, and writes `activation-result-receipt.json`. Raw resume without that wrapper/receipt is forbidden and is detected as drift on the next pre-mutation admission.

Every broker request from cron includes `(job_id, scheduled_tick, immutable_policy_digest, activation_epoch, idempotency_key)`. The broker independently rejects missing, stale, replayed, over-budget, unapproved, or recursive values even if Hermes attempts the call. The profile has no cron-management tool.

G9 runs cron in `no_effect_shadow` mode first. It must prove bounded execution, no overlap, idempotent replay, crash recovery, rate-limit behavior, pre-mutation drift shutdown, lifecycle stop/reboot behavior, and zero tenant/API/provider-direct access before the policy compiler may admit one exact job/manifest/window activation receipt.

The implementation roster is fixed now: **the accountable operator provenance record** is the human accountable owner, **Kublai** is the proof producer/implementer, and **Claude Code** is the independent verifier. Domain labels below are duties, not substitute identities. One actor cannot sign two roles; any substitution reopens G0.

## 14. Autonomous controller and gate graph

    The single dependency graph remains `G0 -> G1 -> G2 -> G3A -> G3B -> G3C -> G3D -> G3E -> G4 -> G5 -> G6 -> G7 -> G8 -> G9 -> G10 -> G11`. Downstream mutation requires the upstream protected closure plus a fresh machine-policy admission. A failed gate leaves authority unchanged.

    | Gate | Depends on | Frozen slug | Work/evidence | Required predicates | Authority after pass |
    |---|---|---|---|---|---|
    | G0 | none | `g0_autonomous_source_freeze` | Freeze source, policy, schemas, commands, and negative tests | `source_closed;policy_review_exact;forbidden_surface_empty` | implementation only after exact machine closure |
| G1 | G0 | `g1_source_contracts` | Build default-deny source contracts and pinned runtime-build inputs | `prior_closure_exact;write_set_exact;tests_green` | implementation only after exact machine closure |
| G2 | G1 | `g2_identity_confinement` | Provision isolated identities and prove host/VM/egress denial | `isolation_live;credential_scope_exact;negative_probes_green` | implementation only after exact machine closure |
| G3A | G2 | `g3a_storage_inventory` | Freeze storage, archive, quota, and zero/legacy inventory evidence | `volume_exact;capacity_green;inventory_reconciled` | implementation only after exact machine closure |
| G3B | G3A | `g3b_durable_authority` | Create empty durable authority, recovery, projection, and stop state | `empty_authority;recovery_kill_matrix;projection_bounded` | implementation only after exact machine closure |
| G3C | G3B | `g3c_quarantine_migration` | Copy legacy state to quarantine with reconciliation | `read_only_source;quarantine_only;reconciliation_exact` | implementation only after exact machine closure |
| G3D | G3C | `g3d_restore_drill` | Run clean-room backup/restore and rollback-head reconciliation | `restore_tuple_exact;ledger_head_current;kill_matrix_green` | implementation only after exact machine closure |
| G3E | G3D | `g3e_data_promotion` | Promote only a fully verified generation and revoke legacy paths | `generation_exact;legacy_revoked;data_fuse_policy_admitted` | implementation only after exact machine closure |
| G4 | G3E | `g4_broker_effects` | Implement typed APIs, disclosure ledger, idempotency, and readback | `api_nonoverlap;egress_policy_exact;effect_readback` | implementation only after exact machine closure |
| G5 | G4 | `g5_profile_runtime` | Build, install, smoke, stop, rollback, and quarantine-retire profile | `runtime_digest_exact;tool_surface_closed;hard_delete_denied` | implementation only after exact machine closure |
| G6 | G5 | `g6_public_research` | Run synthetic public-research and transcript archive path | `public_only;archive_replay_exact;tenant_canary_absent` | implementation only after exact machine closure |
| G7 | G6 | `g7_capsule_integration` | Integrate bounded one-run capsules with teardown proof | `one_tenant_epoch;capability_exact;teardown_zero_residue` | implementation only after exact machine closure |
| G8 | G7 | `g8_synthetic_e2e` | Run synthetic intake-to-effect end to end | `synthetic_only;effects_preauthorized;readback_exact` | implementation only after exact machine closure |
| G9 | G8 | `g9_cron_shadow` | Compile cron and run no-effect shadow under drift/race tests | `cron_policy_exact;shadow_green;no_unapproved_outbound` | implementation only after exact machine closure |
| G10 | G9 | `g10_single_consented_pilot` | Observe one pre-consented bounded pilot without auto-invitation | `pilot_consent_valid;communication_permission_valid;budget_green` | pilot evidence only after exact machine closure |
| G11 | G10 | `g11_bounded_consented_cohort` | Observe a bounded pre-consented cohort without auto-invitation | `all_consents_valid;cohort_cap_green;exit_receipts_exact` | pilot evidence only after exact machine closure |

    Every gate also requires the universal predicates: exact base/prior closure, exact plan/policy/commands/write-set hashes, nonempty RED then GREEN evidence, exact test collection, zero required skips, distinct producer and verifier identities, freshness and expiry, unused nonce, no unresolved blocker/high finding, no permanent forbidden surface, credentials isolated by profile/customer and absent from logs, and independently reproduced protected-ref closure.

    G0–G9 are the implementation controller. Their closure may establish `IMPLEMENTATION_COMPLETE` when code, configuration, synthetic integrations, rollback, and proof surfaces are green. G10/G11 are observation gates. They may run autonomously only for pre-consented participants with existing communication permission, otherwise remain pending without making implementation incomplete. Neither gate may invite, message, impersonate, or widen a cohort.

    ## 15. TDD execution packet

    For every gate: write the smallest behavior test first; run it and record the expected semantic failure; implement only the closed write set; run the focused test; run the gate matrix; collect exact node IDs; run the full predecessor-plus-successor suite; run malformed/missing/stale/replay/identity-collision/forbidden-surface mutations; verify credential redaction; build payload/evidence commits; reproduce the protected ref in a detached clone; and emit a machine-readable closure envelope. Mocks cannot close filesystem, credential, network, database, restore, profile, VM, archive, cron, consent, or external-effect claims.

    ## 16. Verification matrix

    | Property | Smallest disconfirming test | Gate |
    |---|---|---|
    | machine admission precedes mutation | remove review or alter base/write-set/command hash; verify zero changed bytes and `DENY` | every gate |
    | producer cannot self-review | set verifier identity equal to producer | every gate |
    | permanent forbidden set is invariant | request one forbidden or unknown effect class | every gate |
    | credentials remain isolated | attempt cross-profile/customer read and scan receipts/logs for canaries | G2/G4/G5/G7 |
    | tenant plane is confined | attempt host, provider-direct, Docker socket, wrong tenant/epoch, and post-teardown access | G2/G7 |
    | recovery is forward-only | kill at each durable intent/readback boundary and restore a stale generation | G3B/G3D/G4/G8 |
    | profile surface is bounded | enumerate effective tools/config/network/plugin paths and mutate one undeclared byte | G5 |
    | transcript archive is complete but non-ambient | replay synthetic conversation; query default Brain/profile routes for canary | G5/G6 |
    | cron is policy before mutation | drift store immediately before claim/direct run; require byte-identical denial | G9 |
    | pilot consent is external evidence | omit/expire/revoke consent or permission; require no invitation or message | G10/G11 |
    | proof debt remains visible | remove or stale one closure input; control projection becomes red and dispatch stays false | every gate |

    ## 17. Proof-debt register

    Each row has accountable operator provenance, but no row consumes operator assent as runtime authority. Closure is mechanical and evidence-bound.

    | ID | Debt | Provenance | Closure gate | Fail-closed state |
    |---|---|---|---|---|
    | PD-A01 | exact autonomous source and policy freeze | the accountable operator provenance record | G0 | v3/corrected G0 remain authority |
    | PD-A02 | source/runtime reproducibility | the accountable operator provenance record | G1/G5 | no profile runtime |
    | PD-A03 | identity, credential, socket, PF, VM isolation | the accountable operator provenance record | G2/G4 | no credential or capsule |
    | PD-A04 | storage, migration, restore, anti-rollback | the accountable operator provenance record | G3A–G3E | data admission blocked |
    | PD-A05 | typed broker, disclosure, idempotency, readback | the accountable operator provenance record | G4/G8 | no external effect |
    | PD-A06 | public archive completeness and non-ambient retrieval | the accountable operator provenance record | G5/G6 | no persistent profile run |
    | PD-A07 | cron pre-mutation enforcement | the accountable operator provenance record | G9 | cron disabled |
    | PD-A08 | preexisting consent and communication permission | the accountable operator provenance record | G10/G11 | no pilot traffic |
    | PD-A09 | control-room projection, freshness, receipts | the accountable operator provenance record | each gate | downstream dispatch blocked |
    | PD-A10 | hard delete/public post/payment/identity/unapproved outbound exclusion | the accountable operator provenance record | permanent | action denied |

    ## 18. Stop, rollback, retirement, and irreversible boundaries

    Stop is always available and never waits for admission: `STOP_PUBLIC_RESEARCH`, `STOP_CHAT_ARCHIVE`, `STOP_CAPSULE_LAUNCH`, `STOP_EXTERNAL_EFFECTS`, `STOP_CRON`, `STOP_DATA_ADMISSION`, and `STOP_ALL_HULAGU`. Stop reduces authority even if source bytes are dirty or unavailable. Resume and rollback require a fresh policy decision plus green prerequisites and can never lower lifecycle, disclosure, revocation, or archive heads.

    Autonomous retirement stops ingress, drains/reconciles archives and effects, revokes credentials/capabilities, and quarantines the profile tree under an exact receipt. It never invokes a hard delete. Live hard deletes, public posting, payments, identity/SOUL changes, and unapproved outbound email/chat are permanently outside this policy.

    ## 19. Buildroom/control-room integration

    G0 emits only a static proposal projection: `authority=machine_policy_only`, `dispatch_allowed=false`, `requires_policy_admission=true`, `implementation_state=NOT_IMPLEMENTED_FAIL_CLOSED`. G3B may add live signed aggregate rows. The projector can display gate state, evidence digest, proof debt, stop/data-admission state, capacity/lag bands, policy digest, freshness, queue/cost/incident buckets, and immutable provenance. It cannot read tenant/chat payloads or mutate acceptance, dispatch, work, artifact, ledger, Kanban, policy, or approval state. Missing/stale/invalid evidence renders red and blocks dispatch.

    ## 20. Authority-change closure ledger

    | Prior human checkpoint | Autonomous replacement |
    |---|---|
    | pre-start named-human authorization | exact `gate-policy-admission-v1` decision compiled before mutation |
    | post-review assent receipt | exact independent review plus deterministic closure envelope |
    | owner credential for mutation | isolated policy-control service identity with closed operation set |
    | human review requirement | immutable run receipt from a distinct independent verifier |
    | owner-controlled cron activation | compiled immutable cron policy, shadow evidence, readback, and bounded activation decision |
    | invited pilot approval | preexisting `pilot-consent-v1` and communication permission; no auto-invite |
    | future activation checkpoint | source-authored activation manifest plus exact policy predicates; invariant changes reopen G0 |

    Historical receipts remain historical. This table changes future authority only.

    ## 21. Definition of done

    Implementation is complete when G0–G9 close through independent review, deterministic admission, exact tests, payload/evidence separation, protected-ref reproduction, credential/log redaction, rollback/stop receipts, and a fail-closed control projection. It does not require fabricated elapsed pilot evidence. G10/G11 close only after real bounded observation of pre-consented participants; absent consent leaves `PILOT_EVIDENCE_PENDING`, never an invitation task.

    No completion claim may rely on prose, path existence, mocks for live boundaries, a stale review, another commit's run, producer self-review, operator assent, or hidden credentials.

    ## 22. Runtime boundary of this revision

    This autonomy-v1 revision changes the Brain plan and produces a candidate overlay/review packet only. It does not edit `/Users/kublai/kurultai/hulagu-g1-source-contracts`, create a commit or protected ref there, install a profile, start a VM/container/service, provision or read credentials, change cron/gateway/config/provider state, access customer data, write Sheets, send email/chat, invite a pilot, post publicly, pay, change identity/SOUL, or hard-delete data.

    The next machine step is an exact-hash independent policy review of the frozen candidate. Until that artifact exists and validates, `implementation_authorized: false` and the pre-mutation verifier returns `DENY`. No human runtime start or closure approval is pending.
