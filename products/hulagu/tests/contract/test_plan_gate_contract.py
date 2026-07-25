from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

PRODUCT_ROOT = Path(__file__).parents[2]
SCRIPT = PRODUCT_ROOT / "deploy/scripts/verify_plan_gate.py"
APPROVED_PLAN = "/Users/kublai/brain/docs/plans/2026-07-25-kublai-hulagu-job-search-agent-implementation-plan-v3.md"
APPROVED_HASH = "07e885de133fc742d33b8a2f8bae25ce25d1d0da5c5efbbaf0d56f38bb3a0ac9"
APPROVED_COMMIT = "96e42974b105a60e401a0f7ab7f7843f466d12ed"
APPROVED_RECEIPT = "/Users/kublai/brain/docs/plans/reviews/2026-07-25-kublai-hulagu-job-search-agent-v3-freeze-receipt.md"
APPROVED_RECEIPT_HASH = "5f8fb719039880cbe8d71f448c55796d11536d4b717e17bbb4ce1b12b1e2a6cc"
TRACKER = "/Users/kublai/brain/docs/qa/kurultai-system-feature-status.csv"
TRACKER_HASH = "4fe11fed6d97bd6ece1b89d4e3ea2729a092d531dd68912b133d5b214cc04637"
RELEVANT_ROW_IDS = {
    "SYS-001",
    "SYS-004",
    "HERMES-003",
    "HERMES-004",
    "BRAIN-001",
    "BRAIN-004",
    "SEC-003",
}


def load_verifier():
    spec = importlib.util.spec_from_file_location("verify_plan_gate", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def valid_manifest() -> dict:
    return {
        "schema_version": "hulagu-impact-regression-baseline/v1",
        "root_test": {
            "command": "/opt/homebrew/bin/python3 -m pytest tests/ -q",
            "status": "pass",
            "per_test_outcome_sha256": "9" * 64,
        },
        "hulagu_test_commands": [
            {
                "command": "uv run pytest tests/contract tests/integration/test_vault_preflight.py -vv",
                "status": "not_present",
            },
            {
                "command": "uv run pytest tests/integration/test_container_mount_probe.py -vv",
                "status": "not_present",
            },
        ],
        "plan_gate": {
            "gate": "G1",
            "canonical_plan_path": APPROVED_PLAN,
            "plan_sha256": APPROVED_HASH,
            "brain_commit": APPROVED_COMMIT,
            "g0_record": {"status": "verified_existing_record", "retroactive_approval": False},
            "independent_receipt": {
                "path": APPROVED_RECEIPT,
                "sha256": APPROVED_RECEIPT_HASH,
                "reviewer_identity": "Hermes Agent focused subagent; 2026-07-25T15:13:03Z",
                "verdict": "APPROVE_FOR_G0",
                "reviewer_role": "independent_reviewer",
                "implementation_role": "implementation_author",
                "independent_of_plan_author": True,
            },
            "proof_debt": [
                {
                    "item": "container runtime proof",
                    "owner": "implementation_owner",
                    "closure_gate": "G2",
                }
            ],
            "waived_safety_failures": [],
        },
        "qa_tracker": {
            "path": TRACKER,
            "tracker_sha256": TRACKER_HASH,
            "selected_rows": [
                {
                    "id": row_id,
                    "status": "PASS",
                    "evidence_path": f"/tmp/{row_id}.json",
                    "evidence_sha256": "a" * 64,
                    "accountable_owner": "named owner",
                    "required_g3_status": "PASS",
                }
                for row_id in sorted(RELEVANT_ROW_IDS)
            ],
        },
        "generation": {
            "command": "python3 qa/generate_frozen_baseline.py --output qa/hulagu-impact-regression-baseline.json",
            "version": "hulagu-task0-baseline-generator/v1",
            "independent_verifier_identity": {
                "role": "non_author_task0_spec_reviewer",
                "status": "request_changes_issued",
                "identity": "delegation:deleg_29b20c77",
            },
        },
    }


def readme() -> str:
    return (
        f"plan: `{APPROVED_PLAN}`\nsha256: `{APPROVED_HASH}`\nBrain commit: `{APPROVED_COMMIT}`\n"
    )


def assert_rejected(manifest: dict, match: str) -> None:
    errors = load_verifier().validate_manifest(manifest, readme())
    assert any(match in error for error in errors), errors


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("canonical_plan_path", "/wrong/plan.md", "plan path"),
        ("plan_sha256", "0" * 64, "plan SHA-256"),
        ("brain_commit", "1" * 40, "Brain commit"),
    ],
)
def test_rejects_wrong_plan_identity(field: str, value: str, message: str) -> None:
    manifest = valid_manifest()
    manifest["plan_gate"][field] = value
    assert_rejected(manifest, message)


def test_rejects_missing_independent_receipt() -> None:
    manifest = valid_manifest()
    del manifest["plan_gate"]["independent_receipt"]
    assert_rejected(manifest, "independent receipt")


def test_rejects_missing_role_separation() -> None:
    manifest = valid_manifest()
    manifest["plan_gate"]["independent_receipt"]["reviewer_role"] = "implementation_author"
    assert_rejected(manifest, "role separation")


def test_rejects_unowned_ungated_or_empty_proof_debt() -> None:
    for missing in ("owner", "closure_gate"):
        manifest = valid_manifest()
        del manifest["plan_gate"]["proof_debt"][0][missing]
        assert_rejected(manifest, "proof debt")
    manifest = valid_manifest()
    manifest["plan_gate"]["proof_debt"] = []
    assert_rejected(manifest, "proof debt")


def test_rejects_wrong_receipt_binding() -> None:
    for field, value in (
        ("path", "/tmp/other.md"),
        ("sha256", "0" * 64),
        ("reviewer_identity", ""),
    ):
        manifest = valid_manifest()
        manifest["plan_gate"]["independent_receipt"][field] = value
        assert_rejected(manifest, "receipt")


def test_rejects_wrong_or_incomplete_qa_tracker_contract() -> None:
    manifest = valid_manifest()
    manifest["qa_tracker"]["path"] = "/tmp/wrong.csv"
    assert_rejected(manifest, "QA tracker path")
    manifest = valid_manifest()
    manifest["qa_tracker"]["selected_rows"][0]["id"] = "IRRELEVANT-999"
    assert_rejected(manifest, "QA row inventory")


def test_rejects_missing_or_placeholder_generation_metadata() -> None:
    manifest = valid_manifest()
    del manifest["generation"]
    assert_rejected(manifest, "generation")
    manifest = valid_manifest()
    manifest["generation"]["command"] = "shasum <tracker-and-evidence>"
    assert_rejected(manifest, "generation")
    manifest = valid_manifest()
    manifest["generation"]["independent_verifier_identity"]["status"] = "unassigned"
    assert_rejected(manifest, "independent verifier")


def test_rejects_missing_command_manifest() -> None:
    manifest = valid_manifest()
    del manifest["hulagu_test_commands"]
    assert_rejected(manifest, "command manifest")


def test_rejects_waived_safety_failure() -> None:
    manifest = valid_manifest()
    manifest["plan_gate"]["waived_safety_failures"] = ["vault identity failure"]
    assert_rejected(manifest, "waived safety")


def test_verifier_cannot_retroactively_approve_g0() -> None:
    manifest = valid_manifest()
    manifest["plan_gate"]["g0_record"]["retroactive_approval"] = True
    assert_rejected(manifest, "retroactive")


def test_valid_frozen_manifest_passes_contract() -> None:
    assert load_verifier().validate_manifest(valid_manifest(), readme()) == []


def test_repository_manifest_matches_frozen_contract() -> None:
    manifest = json.loads(
        (PRODUCT_ROOT / "qa/hulagu-impact-regression-baseline.json").read_text(encoding="utf-8")
    )
    readme_text = (PRODUCT_ROOT / "README.md").read_text(encoding="utf-8")
    assert load_verifier().validate_manifest(manifest, readme_text) == []
