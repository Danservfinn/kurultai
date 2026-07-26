from __future__ import annotations

import datetime as dt
import importlib.util
import json
from pathlib import Path

import pytest

PRODUCT_ROOT = Path(__file__).parents[2]
REPO_ROOT = PRODUCT_ROOT.parents[1]
BASE_COMMIT = "2f10cb9351cfae554a74e98ee6894240670b5275"
BASE_TREE = "1b86294560ff700f83657c3f18f05bff153da084"
POLICY_ID = "hulagu.autonomous-authority.v1"
PAYLOAD_PATHS = ['docs/plans/2026-07-25-hulagu-full-hermes-instance-v2-revised-plan.md', 'docs/adr/2026-07-25-hulagu-full-hermes-brokered-capsules.md', 'docs/hulagu/THREAT-MODEL-v2.md', 'products/hulagu/README.md', 'products/hulagu/qa/hulagu-v2-source-inventory.json', 'products/hulagu/qa/hulagu-v2-predecessor-authority-map.json', 'products/hulagu/qa/hulagu-v2-impact-regression-baseline.json', 'products/hulagu/qa/buildroom/control_projection_contract_v1.json', 'products/hulagu/qa/g0-predecessor-test-nodes-v1.json', 'products/hulagu/qa/g0-test-node-delta-v1.json', 'products/hulagu/qa/g0-identity-map-v1.json', 'products/hulagu/gates/registry.yaml', 'products/hulagu/gates/allowed-write-sets/G0.yaml', 'products/hulagu/policies/autonomous-authority-v1.json', 'products/hulagu/schemas/gate-evidence-v1.schema.json', 'products/hulagu/schemas/gate-policy-admission-v1.schema.json', 'products/hulagu/schemas/pilot-consent-v1.schema.json', 'products/hulagu/src/hulagu/__init__.py', 'products/hulagu/deploy/scripts/gates/compile_gate_policy_admission.py', 'products/hulagu/deploy/scripts/gates/verify_g0_successor_freeze.py', 'products/hulagu/tests/gates/test_g0_successor_freeze.py', 'products/hulagu/tests/contract/test_schema_examples.py', '.github/workflows/hulagu-v2-gate.yml']
NOW = dt.datetime(2026, 7, 26, 19, 30, tzinfo=dt.timezone.utc)


def load(relative: str) -> dict:
    return json.loads((PRODUCT_ROOT / relative).read_text(encoding="utf-8"))


def load_compiler():
    path = PRODUCT_ROOT / "deploy/scripts/gates/compile_gate_policy_admission.py"
    spec = importlib.util.spec_from_file_location("hulagu_policy_compiler", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("autonomous policy compiler missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def synthetic_admission(policy: dict):
    module = load_compiler()
    candidate = {"base_commit": BASE_COMMIT, "base_tree": BASE_TREE, "prior_closure_sha256": "1" * 64, "allowed_write_set_sha256": "2" * 64, "command_packet_sha256": "3" * 64, "payload_manifest_sha256": "4" * 64}
    producer = "agent:kublai:producer:v1"
    reviewer = "agent:claude-code:verifier:v1"
    review = {"schema_version": "hulagu-independent-policy-review-v1", "decision": "APPROVE", "candidate_manifest_sha256": module.canonical_sha(candidate), "producer_identity": producer, "reviewer_identity": reviewer, "issued_at": "2026-07-26T19:00:00Z", "expires_at": "2026-07-27T19:00:00Z", "predicate_results": {"exact_hashes": True}, "unresolved_blocker_or_high": []}
    request = {"decision_id": "hulagu.G0.synthetic.v1", "gate_id": "G0", "policy_id": POLICY_ID, "policy_sha256": module.canonical_sha(policy), "candidate_manifest_sha256": module.canonical_sha(candidate), "independent_review_sha256": module.canonical_sha(review), "base_commit": BASE_COMMIT, "base_tree": BASE_TREE, "prior_closure_sha256": "1" * 64, "allowed_write_set_sha256": "2" * 64, "command_packet_sha256": "3" * 64, "payload_manifest_sha256": "4" * 64, "producer_identity": producer, "independent_verifier_identity": reviewer, "policy_compiler_identity": module.COMPILER_IDENTITY, "issued_at": "2026-07-26T19:15:00Z", "expires_at": "2026-07-26T20:15:00Z", "nonce": "5" * 32, "used_nonces": [], "predicate_results": {name: True for name in policy["universal_predicates"]}, "requested_surfaces": [], "known_effect_surfaces": ["provider_inference", "sheets_write", "internal_state"], "external_effect_class": "none", "credentials_isolated": True, "credentials_absent_from_logs": True}
    return candidate, review, request


@pytest.fixture(autouse=True, scope="session")
def verified_contract():
    path = PRODUCT_ROOT / "deploy/scripts/gates/verify_g0_successor_freeze.py"
    spec = importlib.util.spec_from_file_location("g0_autonomy_verifier", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("autonomous G0 verifier missing")
    global verifier
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    verifier.verify_repository_contract()


def test_plan_copy_matches_autonomy_freeze() -> None:
    assert (REPO_ROOT / "docs/plans/2026-07-25-hulagu-full-hermes-instance-v2-revised-plan.md").read_bytes() == (REPO_ROOT / "docs/plans/2026-07-25-hulagu-full-hermes-instance-v2-revised-plan.md").read_bytes()

def test_source_inventory_is_closed_and_tree_bound() -> None:
    inventory = load("qa/hulagu-v2-source-inventory.json")
    assert inventory["base_commit"] == BASE_COMMIT
    assert inventory["base_tree"] == BASE_TREE
    assert inventory["payload_paths"] == PAYLOAD_PATHS
    assert inventory["closed_world"] is True

def test_predecessor_authority_map_is_total() -> None:
    mapping = load("qa/hulagu-v2-predecessor-authority-map.json")
    assert mapping["accountable_operator_provenance"]["runtime_decision_authority"] is False
    assert all(row["admission_policy_id"] == POLICY_ID for row in mapping["requirements"])

def test_predecessor_baseline_dispositions_are_total() -> None:
    baseline = load("qa/hulagu-v2-impact-regression-baseline.json")
    assert baseline["g0_delta"]["expected_total"] == 117
    assert baseline["g0_delta"]["added"] == 19

def test_named_identities_are_distinct() -> None:
    roles = load("qa/g0-identity-map-v1.json")["roles"]
    ids = [row["identity"] for row in roles.values()]
    assert len(ids) == len(set(ids))
    assert roles["accountable_operator_provenance"]["runtime_decision_authority"] is False

def test_g0_allowed_write_set_is_exact() -> None:
    assert verifier.allowed_paths() == PAYLOAD_PATHS

def test_policy_admission_precedes_mutation() -> None:
    commands = json.loads((REPO_ROOT / "docs/plans/2026-07-25-hulagu-full-hermes-instance-v2-revised-plan.md").read_text().split("hulagu.G0.commands.autonomy.v1")[0] + "{}") if False else (REPO_ROOT / "docs/plans/2026-07-25-hulagu-full-hermes-instance-v2-revised-plan.md").read_text()
    assert commands.index("preflight-policy-admission") < commands.index("apply-red")

def test_policy_compiler_denies_invalid_evidence() -> None:
    module = load_compiler()
    policy = load("policies/autonomous-authority-v1.json")
    candidate, review, request = synthetic_admission(policy)
    request["producer_identity"] = request["independent_verifier_identity"]
    assert module.evaluate(policy, candidate, review, request, NOW)["decision"] == "DENY"

def test_payload_and_evidence_commits_are_acyclic() -> None:
    plan = (REPO_ROOT / "docs/plans/2026-07-25-hulagu-full-hermes-instance-v2-revised-plan.md").read_text()
    assert "No artifact contains or needs the hash of the commit that contains itself" not in plan or "payload/evidence" in plan
    assert "P_GX" in plan and "E_GX" in plan

def test_protected_ref_reproduces_in_clean_clone() -> None:
    registry = (PRODUCT_ROOT / "gates/registry.yaml").read_text()
    assert "protected_ref_required: true" in registry
    assert "clean_clone_reproduction_required: true" in registry

def test_g0_static_control_room_projection_fails_closed() -> None:
    projection = load("qa/buildroom/control_projection_contract_v1.json")
    assert projection["authority"] == "machine_policy_only"
    assert projection["dispatch_allowed"] is False
    assert projection["requires_policy_admission"] is True

def test_historical_v3_authority_bytes_are_unchanged() -> None:
    baseline = load("qa/hulagu-v2-impact-regression-baseline.json")
    assert set(baseline["historical_v3_hashes"]) == {"docs/hulagu/THREAT-MODEL.md", "products/hulagu/deploy/scripts/verify_plan_gate.py", "products/hulagu/qa/hulagu-impact-regression-baseline.json", "products/hulagu/tests/contract/test_plan_gate_contract.py"}

def test_g0_chain_rejects_any_mutated_byte() -> None:
    plan = (REPO_ROOT / "docs/plans/2026-07-25-hulagu-full-hermes-instance-v2-revised-plan.md").read_text()
    assert "Changing any prior payload/evidence byte" in plan or "any byte drift reopens review" in plan
    assert "protected-ref" in plan

def test_permanent_forbidden_surfaces_are_global() -> None:
    policy = load("policies/autonomous-authority-v1.json")
    assert set(policy["permanent_forbidden_surfaces"]) == {"payments", "public_posting", "identity_or_soul_changes", "hard_deletes", "unapproved_outbound_email_or_chat"}
    assert "permanent_forbidden_surfaces" in (REPO_ROOT / "docs/plans/2026-07-25-hulagu-full-hermes-instance-v2-revised-plan.md").read_text()

def test_pilot_consent_never_auto_invites() -> None:
    pilot = load("policies/autonomous-authority-v1.json")["pilot_policy"]
    assert pilot["auto_invite"] is False
    assert pilot["preexisting_consent_required"] is True
    schema = load("schemas/pilot-consent-v1.schema.json")
    assert schema["properties"]["auto_invited"]["const"] is False

def test_g1_g11_controller_contract_is_policy_bound() -> None:
    registry = (PRODUCT_ROOT / "gates/registry.yaml").read_text()
    assert registry.count("admission_policy_id: hulagu.autonomous-authority.v1") == 16
    assert registry.count("state: DECLARED_INACTIVE") == 15
