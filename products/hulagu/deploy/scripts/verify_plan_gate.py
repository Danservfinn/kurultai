"""Verify the immutable Hulagu v3.4.2 G1 plan gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import re

# Safe here because git is an absolute fixed executable with fixed read-only argv and no shell.
import subprocess  # nosec B404
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

PLAN_PATH = "/Users/kublai/brain/docs/plans/2026-07-27-kublai-hulagu-job-search-agent-implementation-plan-v3.4.2.md"
PLAN_SHA256 = "2c7cfd43ad2f1372cef8a076667966e9ffa72cfc97c163143e6bcaf3ed5c2c99"
GATE_PATH = "/Users/kublai/brain/docs/plans/2026-07-27-hulagu-v3.4.2-research-model-call-gate.md"
GATE_SHA256 = "1cadb7e749f793abbf5baa670d75a206b9723ca00ce1056bc37aeb8dafe41dd2"
BRAIN_COMMIT = "3417798b"
G0_RECORD_COMMIT = "bf1188b1"
PLAN_BLOB = "dfb6f8fdbe6a74024a0f46c65fbb5b26b4ce1f31"
GATE_BLOB = "bc33fbeed34379f05af89ab4f0ec2658d2f89aa7"
RECEIPT_PATH = "/Users/kublai/brain/docs/plans/reviews/2026-07-27-hulagu-v3.4.2-g-1-joint-freeze-receipt.md"
REQUIRED_COMMANDS = {
    "hulagu-doctor": "hulagu.config:doctor_main",
    "hulagu-verify-plan-gate": "hulagu.config:verify_plan_gate_main",
}


def validate_contract(
    *,
    readme: Mapping[str, Any],
    command_manifest: Mapping[str, Any],
    receipt: Mapping[str, Any] | None,
    qa_baseline: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    expected = {
        "plan_path": (PLAN_PATH, "wrong_plan_path"),
        "plan_sha256": (PLAN_SHA256, "wrong_plan_hash"),
        "gate_path": (GATE_PATH, "wrong_gate_path"),
        "gate_sha256": (GATE_SHA256, "wrong_gate_hash"),
        "brain_commit": (BRAIN_COMMIT, "wrong_brain_commit"),
        "g0_record_commit": (G0_RECORD_COMMIT, "wrong_g0_record_commit"),
        "receipt_path": (RECEIPT_PATH, "wrong_receipt_path"),
    }
    for field, (value, code) in expected.items():
        if readme.get(field) != value:
            errors.append(code)

    for command, target in REQUIRED_COMMANDS.items():
        if command_manifest.get(command) != target:
            errors.append("missing_command_manifest_entry")

    if receipt is None:
        errors.append("missing_independent_receipt")
    else:
        if receipt.get("path") != RECEIPT_PATH or receipt.get("verdict") != "APPROVE_FOR_G0":
            errors.append("missing_independent_receipt")
        if receipt.get("independent_of_plan_author") is not True:
            errors.append("missing_independent_receipt")
        if receipt.get("plan_sha256") != PLAN_SHA256 or receipt.get("gate_sha256") != GATE_SHA256:
            errors.append("receipt_tuple_mismatch")
        if not receipt.get("reviewer_role") or receipt.get("reviewer_role") == receipt.get("implementation_role"):
            errors.append("missing_role_separation")

    debt = qa_baseline.get("proof_debt")
    if not isinstance(debt, list) or any(
        not isinstance(item, Mapping) or not item.get("owner") or not item.get("closure_gate") for item in debt
    ):
        errors.append("unowned_proof_debt")
    if qa_baseline.get("safety_waivers"):
        errors.append("waived_safety_failure")
    return list(dict.fromkeys(errors))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _brain_blob(commit: str, relative_path: str) -> str | None:
    git = Path("/usr/bin/git")
    if not git.is_file():
        return None
    # The executable and operation are fixed; commit/path come from frozen module constants.
    completed = subprocess.run(  # nosec B603
        [str(git), "-C", "/Users/kublai/brain", "rev-parse", f"{commit}:{relative_path}"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def _read_readme_contract(path: Path) -> dict[str, Any]:
    match = re.search(r"<!-- HULAGU_PLAN_GATE_BEGIN -->\s*```json\s*(.*?)\s*```\s*<!-- HULAGU_PLAN_GATE_END -->", path.read_text(), re.DOTALL)
    if not match:
        raise ValueError("product README has no HULAGU_PLAN_GATE contract")
    decoded = json.loads(match.group(1))
    if not isinstance(decoded, dict):
        raise TypeError("product README HULAGU_PLAN_GATE contract must be an object")
    return {str(key): value for key, value in decoded.items()}


def _receipt_contract(path: Path, implementation_role: str) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    text = path.read_text()
    reviewer = "mongke-independent-reviewer" if "worker/run: `mongke`" in text else "unknown-reviewer"
    return {
        "path": str(path),
        "verdict": "APPROVE_FOR_G0" if "`APPROVE_FOR_G0`" in text else "unknown",
        "independent_of_plan_author": "`independent_of_plan_author: true`" in text,
        "reviewer_role": reviewer,
        "implementation_role": implementation_role,
        "plan_sha256": PLAN_SHA256 if PLAN_SHA256 in text else None,
        "gate_sha256": GATE_SHA256 if GATE_SHA256 in text else None,
    }


def verify_repository(product_root: Path) -> list[str]:
    readme = _read_readme_contract(product_root / "README.md")
    pyproject = tomllib.loads((product_root / "pyproject.toml").read_text())
    commands = pyproject.get("project", {}).get("scripts", {})
    baseline = json.loads((product_root / "qa" / "hulagu-impact-regression-baseline.json").read_text())
    receipt_path = Path(readme.get("receipt_path", ""))
    receipt = _receipt_contract(receipt_path, str(baseline.get("implementation_owner_role", "")))
    errors = validate_contract(readme=readme, command_manifest=commands, receipt=receipt, qa_baseline=baseline)
    for path, expected, code in (
        (Path(PLAN_PATH), PLAN_SHA256, "live_plan_hash_mismatch"),
        (Path(GATE_PATH), GATE_SHA256, "live_gate_hash_mismatch"),
    ):
        if not path.is_file() or _sha256(path) != expected:
            errors.append(code)
    brain_blobs = (
        ("docs/plans/2026-07-27-kublai-hulagu-job-search-agent-implementation-plan-v3.4.2.md", PLAN_BLOB),
        ("docs/plans/2026-07-27-hulagu-v3.4.2-research-model-call-gate.md", GATE_BLOB),
    )
    if any(_brain_blob(BRAIN_COMMIT, path) != expected for path, expected in brain_blobs):
        errors.append("brain_commit_identity_mismatch")
    if baseline.get("source_commit") != "c10e2bdc0374cc00bc8faf82b23f67933226d670":
        errors.append("qa_baseline_commit_mismatch")
    return list(dict.fromkeys(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Hulagu G1 plan gate")
    parser.add_argument("--product-root", type=Path, default=Path(__file__).parents[2])
    args = parser.parse_args()
    try:
        errors = verify_repository(args.product_root.resolve())
    except (OSError, TypeError, ValueError, json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        errors = [f"contract_read_error:{type(exc).__name__}"]
    print(json.dumps({"status": "pass" if not errors else "fail", "errors": errors}, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
