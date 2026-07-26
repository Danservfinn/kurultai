#!/usr/bin/env python3
"""Verify the autonomous Hulagu G0 successor freeze contract."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

PRODUCT_ROOT = Path(__file__).parents[3]
REPO_ROOT = PRODUCT_ROOT.parents[1]
PAYLOAD_PATHS = ['docs/plans/2026-07-25-hulagu-full-hermes-instance-v2-revised-plan.md', 'docs/adr/2026-07-25-hulagu-full-hermes-brokered-capsules.md', 'docs/hulagu/THREAT-MODEL-v2.md', 'products/hulagu/README.md', 'products/hulagu/qa/hulagu-v2-source-inventory.json', 'products/hulagu/qa/hulagu-v2-predecessor-authority-map.json', 'products/hulagu/qa/hulagu-v2-impact-regression-baseline.json', 'products/hulagu/qa/buildroom/control_projection_contract_v1.json', 'products/hulagu/qa/g0-predecessor-test-nodes-v1.json', 'products/hulagu/qa/g0-test-node-delta-v1.json', 'products/hulagu/qa/g0-identity-map-v1.json', 'products/hulagu/gates/registry.yaml', 'products/hulagu/gates/allowed-write-sets/G0.yaml', 'products/hulagu/policies/autonomous-authority-v1.json', 'products/hulagu/schemas/gate-evidence-v1.schema.json', 'products/hulagu/schemas/gate-policy-admission-v1.schema.json', 'products/hulagu/schemas/pilot-consent-v1.schema.json', 'products/hulagu/src/hulagu/__init__.py', 'products/hulagu/deploy/scripts/gates/compile_gate_policy_admission.py', 'products/hulagu/deploy/scripts/gates/verify_g0_successor_freeze.py', 'products/hulagu/tests/gates/test_g0_successor_freeze.py', 'products/hulagu/tests/contract/test_schema_examples.py', '.github/workflows/hulagu-v2-gate.yml']
FORBIDDEN = ['gate-start-authorization-v1', 'owner-receipt.json', 'Danny separately signs', 'owner-controlled pilot', 'separately approved invited pilot', 'requires_operator_approval=true', 'OWNER_APPROVED']
BASE_COMMIT = "2f10cb9351cfae554a74e98ee6894240670b5275"
BASE_TREE = "1b86294560ff700f83657c3f18f05bff153da084"

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def load(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"missing regular file: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"top-level object required: {path}")
    return value

def allowed_paths() -> list[str]:
    text = (PRODUCT_ROOT / "gates/allowed-write-sets/G0.yaml").read_text(encoding="utf-8")
    return [line[4:] for line in text.splitlines() if line.startswith("  - ")]

def verify_repository_contract() -> dict[str, Any]:
    if allowed_paths() != PAYLOAD_PATHS:
        raise ValueError("allowed write set mismatch")
    for relative in PAYLOAD_PATHS:
        path = REPO_ROOT / relative
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"payload path missing or unsafe: {relative}")
    plan = (REPO_ROOT / "docs/plans/2026-07-25-hulagu-full-hermes-instance-v2-revised-plan.md").read_text(encoding="utf-8")
    for phrase in FORBIDDEN:
        if phrase in plan:
            raise ValueError(f"legacy human runtime gate remains: {phrase}")
    for required in ("gate-policy-admission-v1", "runtime_decision_authority: false", "No human runtime start or closure gate"):
        if required not in plan:
            raise ValueError(f"autonomous authority marker missing: {required}")
    policy = load(PRODUCT_ROOT / "policies/autonomous-authority-v1.json")
    if policy.get("default_decision") != "DENY":
        raise ValueError("policy must default DENY")
    expected_forbidden = {"payments", "public_posting", "identity_or_soul_changes", "hard_deletes", "unapproved_outbound_email_or_chat"}
    if set(policy.get("permanent_forbidden_surfaces", [])) != expected_forbidden:
        raise ValueError("permanent forbidden set mismatch")
    if policy.get("operator_provenance", {}).get("runtime_decision_authority") is not False:
        raise ValueError("operator provenance acquired runtime authority")
    registry = (PRODUCT_ROOT / "gates/registry.yaml").read_text(encoding="utf-8")
    if registry.count("admission_policy_id: hulagu.autonomous-authority.v1") != 16:
        raise ValueError("gate policy binding count mismatch")
    if "owner_identity" in registry or "owner_receipt" in registry:
        raise ValueError("owner runtime gate remains in registry")
    identity = load(PRODUCT_ROOT / "qa/g0-identity-map-v1.json")
    ids = [row["identity"] for row in identity["roles"].values()]
    if len(ids) != len(set(ids)):
        raise ValueError("identity collision")
    baseline = load(PRODUCT_ROOT / "qa/hulagu-v2-impact-regression-baseline.json")
    delta = baseline["g0_delta"]
    if delta != {"added": 19, "removed": 0, "expected_total": 117, "schema_inventory_added": 3, "nodeids": ['products/hulagu/tests/gates/test_g0_successor_freeze.py::test_plan_copy_matches_autonomy_freeze', 'products/hulagu/tests/gates/test_g0_successor_freeze.py::test_source_inventory_is_closed_and_tree_bound', 'products/hulagu/tests/gates/test_g0_successor_freeze.py::test_predecessor_authority_map_is_total', 'products/hulagu/tests/gates/test_g0_successor_freeze.py::test_predecessor_baseline_dispositions_are_total', 'products/hulagu/tests/gates/test_g0_successor_freeze.py::test_named_identities_are_distinct', 'products/hulagu/tests/gates/test_g0_successor_freeze.py::test_g0_allowed_write_set_is_exact', 'products/hulagu/tests/gates/test_g0_successor_freeze.py::test_policy_admission_precedes_mutation', 'products/hulagu/tests/gates/test_g0_successor_freeze.py::test_policy_compiler_denies_invalid_evidence', 'products/hulagu/tests/gates/test_g0_successor_freeze.py::test_payload_and_evidence_commits_are_acyclic', 'products/hulagu/tests/gates/test_g0_successor_freeze.py::test_protected_ref_reproduces_in_clean_clone', 'products/hulagu/tests/gates/test_g0_successor_freeze.py::test_g0_static_control_room_projection_fails_closed', 'products/hulagu/tests/gates/test_g0_successor_freeze.py::test_historical_v3_authority_bytes_are_unchanged', 'products/hulagu/tests/gates/test_g0_successor_freeze.py::test_g0_chain_rejects_any_mutated_byte', 'products/hulagu/tests/gates/test_g0_successor_freeze.py::test_permanent_forbidden_surfaces_are_global', 'products/hulagu/tests/gates/test_g0_successor_freeze.py::test_pilot_consent_never_auto_invites', 'products/hulagu/tests/gates/test_g0_successor_freeze.py::test_g1_g11_controller_contract_is_policy_bound', 'products/hulagu/tests/contract/test_schema_examples.py::test_schema_embedded_examples_validate[gate-evidence-v1.schema.json]', 'products/hulagu/tests/contract/test_schema_examples.py::test_schema_embedded_examples_validate[gate-policy-admission-v1.schema.json]', 'products/hulagu/tests/contract/test_schema_examples.py::test_schema_embedded_examples_validate[pilot-consent-v1.schema.json]']}:
        raise ValueError("test delta mismatch")
    projection = load(PRODUCT_ROOT / "qa/buildroom/control_projection_contract_v1.json")
    if projection.get("dispatch_allowed") is not False or projection.get("requires_policy_admission") is not True:
        raise ValueError("static projection is not fail closed")
    return {"result": "PASS", "payload_count": len(PAYLOAD_PATHS), "successor_nodes": 16, "schema_nodes": 3}

if __name__ == "__main__":
    print(json.dumps(verify_repository_contract(), sort_keys=True))
