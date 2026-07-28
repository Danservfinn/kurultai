from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPT = Path(__file__).parents[2] / "deploy" / "scripts" / "verify_plan_gate.py"
PLAN_PATH = "/Users/kublai/brain/docs/plans/2026-07-27-kublai-hulagu-job-search-agent-implementation-plan-v3.4.2.md"
GATE_PATH = "/Users/kublai/brain/docs/plans/2026-07-27-hulagu-v3.4.2-research-model-call-gate.md"
PLAN_SHA = "2c7cfd43ad2f1372cef8a076667966e9ffa72cfc97c163143e6bcaf3ed5c2c99"
GATE_SHA = "1cadb7e749f793abbf5baa670d75a206b9723ca00ce1056bc37aeb8dafe41dd2"
BRAIN_COMMIT = "3417798b"
G0_RECORD_COMMIT = "bf1188b1"
RECEIPT_PATH = "/Users/kublai/brain/docs/plans/reviews/2026-07-27-hulagu-v3.4.2-g-1-joint-freeze-receipt.md"


def load_verifier() -> ModuleType:
    spec = importlib.util.spec_from_file_location("verify_plan_gate", SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def valid_contract() -> dict[str, Any]:
    return {
        "readme": {
            "plan_path": PLAN_PATH,
            "plan_sha256": PLAN_SHA,
            "gate_path": GATE_PATH,
            "gate_sha256": GATE_SHA,
            "brain_commit": BRAIN_COMMIT,
            "g0_record_commit": G0_RECORD_COMMIT,
            "receipt_path": RECEIPT_PATH,
        },
        "command_manifest": {
            "hulagu-doctor": "hulagu.config:doctor_main",
            "hulagu-verify-plan-gate": "hulagu.config:verify_plan_gate_main",
        },
        "receipt": {
            "path": RECEIPT_PATH,
            "verdict": "APPROVE_FOR_G0",
            "independent_of_plan_author": True,
            "reviewer_role": "independent-security-reviewer",
            "implementation_role": "hulagu-task-0-implementer",
            "plan_sha256": PLAN_SHA,
            "gate_sha256": GATE_SHA,
        },
        "qa_baseline": {
            "source_commit": "c10e2bdc0374cc00bc8faf82b23f67933226d670",
            "proof_debt": [
                {"item": "container runtime evidence", "owner": "implementation owner", "closure_gate": "G2"},
                {"item": "provider privacy evidence", "owner": "product owner", "closure_gate": "G5"},
            ],
            "safety_waivers": [],
        },
    }


def assert_rejected(contract: dict[str, Any], code: str) -> None:
    errors = load_verifier().validate_contract(**contract)
    assert code in errors


def test_approved_exact_contract_is_accepted() -> None:
    assert load_verifier().validate_contract(**valid_contract()) == []


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("plan_path", "/tmp/rejected-plan.md", "wrong_plan_path"),
        ("plan_sha256", "0" * 64, "wrong_plan_hash"),
        ("gate_path", "/tmp/unbound-gate.md", "wrong_gate_path"),
        ("gate_sha256", "f" * 64, "wrong_gate_hash"),
        ("brain_commit", "deadbeef", "wrong_brain_commit"),
        ("g0_record_commit", "deadbeef", "wrong_g0_record_commit"),
    ],
)
def test_readme_authority_drift_is_rejected(field: str, value: str, code: str) -> None:
    contract = valid_contract()
    contract["readme"][field] = value
    assert_rejected(contract, code)


def test_missing_independent_receipt_is_rejected() -> None:
    contract = valid_contract()
    contract["receipt"] = None
    assert_rejected(contract, "missing_independent_receipt")


def test_missing_role_separation_is_rejected() -> None:
    contract = valid_contract()
    contract["receipt"]["reviewer_role"] = contract["receipt"]["implementation_role"]
    assert_rejected(contract, "missing_role_separation")


def test_unowned_proof_debt_is_rejected() -> None:
    contract = valid_contract()
    contract["qa_baseline"]["proof_debt"][0]["owner"] = ""
    assert_rejected(contract, "unowned_proof_debt")


def test_safety_waiver_is_rejected() -> None:
    contract = valid_contract()
    contract["qa_baseline"]["safety_waivers"] = ["skip container isolation"]
    assert_rejected(contract, "waived_safety_failure")
