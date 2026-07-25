#!/usr/bin/env python3
"""Fail-closed verifier for the immutable G1 plan and QA evidence gate."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess  # nosec B404 -- only fixed /usr/bin/git, never PATH/shell
import sys
from pathlib import Path
from typing import Any

PRODUCT_ROOT = Path(__file__).parents[2]
GIT = Path("/usr/bin/git")
BASELINE = PRODUCT_ROOT / "qa/hulagu-impact-regression-baseline.json"
README = PRODUCT_ROOT / "README.md"
APPROVED_PLAN = Path(
    "/Users/kublai/brain/docs/plans/2026-07-25-kublai-hulagu-job-search-agent-implementation-plan-v3.md"
)
APPROVED_HASH = "07e885de133fc742d33b8a2f8bae25ce25d1d0da5c5efbbaf0d56f38bb3a0ac9"
APPROVED_COMMIT = "96e42974b105a60e401a0f7ab7f7843f466d12ed"
APPROVED_RECEIPT = Path(
    "/Users/kublai/brain/docs/plans/reviews/2026-07-25-kublai-hulagu-job-search-agent-v3-freeze-receipt.md"
)
APPROVED_RECEIPT_HASH = "5f8fb719039880cbe8d71f448c55796d11536d4b717e17bbb4ce1b12b1e2a6cc"
CANONICAL_TRACKER = Path("/Users/kublai/brain/docs/qa/kurultai-system-feature-status.csv")
RELEVANT_ROW_IDS = frozenset(
    {"SYS-001", "SYS-004", "HERMES-003", "HERMES-004", "BRAIN-001", "BRAIN-004", "SEC-003"}
)
ROOT_TEST_COMMAND = "/opt/homebrew/bin/python3 -m pytest tests/ -q"
HULAGU_COMMANDS = (
    "uv run pytest tests/contract tests/integration/test_vault_preflight.py -vv",
    "uv run pytest tests/integration/test_container_mount_probe.py -vv",
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_manifest(manifest: dict[str, Any], readme_text: str) -> list[str]:
    errors: list[str] = []
    if manifest.get("schema_version") != "hulagu-impact-regression-baseline/v1":
        errors.append("wrong baseline schema version")

    root_test = manifest.get("root_test")
    if not isinstance(root_test, dict) or root_test.get("command") != ROOT_TEST_COMMAND:
        errors.append("root command manifest missing or wrong")
    elif root_test.get("status") != "pass" or not _SHA256.fullmatch(
        str(root_test.get("per_test_outcome_sha256", ""))
    ):
        errors.append("root command manifest lacks passing per-test digest")

    hulagu_commands = manifest.get("hulagu_test_commands")
    observed_commands = ()
    if isinstance(hulagu_commands, list):
        observed_commands = tuple(
            item.get("command") for item in hulagu_commands if isinstance(item, dict)
        )
    if observed_commands != HULAGU_COMMANDS or any(
        not isinstance(item, dict) or item.get("status") != "not_present"
        for item in (hulagu_commands or [])
    ):
        errors.append("Hulagu command manifest missing, reordered, or not frozen as not_present")

    gate = manifest.get("plan_gate")
    if not isinstance(gate, dict):
        return errors + ["plan gate missing"]
    if gate.get("gate") != "G1":
        errors.append("wrong gate")
    if gate.get("canonical_plan_path") != str(APPROVED_PLAN):
        errors.append("plan path mismatch")
    if gate.get("plan_sha256") != APPROVED_HASH:
        errors.append("plan SHA-256 mismatch")
    if gate.get("brain_commit") != APPROVED_COMMIT or not _COMMIT.fullmatch(
        str(gate.get("brain_commit", ""))
    ):
        errors.append("Brain commit mismatch")
    g0 = gate.get("g0_record")
    if not isinstance(g0, dict) or g0.get("status") != "verified_existing_record":
        errors.append("G0 record is not pre-existing and verified")
    if isinstance(g0, dict) and g0.get("retroactive_approval") is not False:
        errors.append("retroactive G0 approval is forbidden")

    receipt = gate.get("independent_receipt")
    if not isinstance(receipt, dict):
        errors.append("independent receipt missing")
    else:
        if receipt.get("path") != str(APPROVED_RECEIPT):
            errors.append("receipt path mismatch")
        if receipt.get("sha256") != APPROVED_RECEIPT_HASH:
            errors.append("receipt SHA-256 mismatch")
        if not _nonempty(receipt.get("reviewer_identity")):
            errors.append("receipt reviewer identity missing")
        if (
            receipt.get("verdict") != "APPROVE_FOR_G0"
            or receipt.get("independent_of_plan_author") is not True
        ):
            errors.append("independent receipt verdict/independence invalid")
        if receipt.get("reviewer_role") == receipt.get("implementation_role") or not all(
            _nonempty(receipt.get(key)) for key in ("reviewer_role", "implementation_role")
        ):
            errors.append("role separation missing")

    debt = gate.get("proof_debt")
    if not isinstance(debt, list) or not debt:
        errors.append("proof debt must be non-empty and owned")
    else:
        for index, item in enumerate(debt):
            if not isinstance(item, dict) or not all(
                _nonempty(item.get(key)) for key in ("item", "owner", "closure_gate")
            ):
                errors.append(f"proof debt row {index} lacks item, owner, or closure gate")
    if gate.get("waived_safety_failures") != []:
        errors.append("waived safety failures are forbidden")

    tracker = manifest.get("qa_tracker")
    if not isinstance(tracker, dict):
        errors.append("QA tracker contract missing")
    else:
        if tracker.get("path") != str(CANONICAL_TRACKER):
            errors.append("QA tracker path is not canonical")
        if not _SHA256.fullmatch(str(tracker.get("tracker_sha256", ""))):
            errors.append("QA tracker hash missing or malformed")
        rows = tracker.get("selected_rows")
        ids = (
            {row.get("id") for row in rows if isinstance(row, dict)}
            if isinstance(rows, list)
            else set()
        )
        if ids != RELEVANT_ROW_IDS or len(rows or []) != len(RELEVANT_ROW_IDS):
            errors.append("QA row inventory is not the exact relevant set")
        for row in rows or []:
            if (
                not isinstance(row, dict)
                or not all(
                    _nonempty(row.get(key))
                    for key in (
                        "id",
                        "status",
                        "evidence_path",
                        "accountable_owner",
                        "required_g3_status",
                    )
                )
                or not _SHA256.fullmatch(str(row.get("evidence_sha256", "")))
            ):
                errors.append("QA row lacks status, evidence hash, owner, or required G3 status")
                break

    generation = manifest.get("generation")
    if not isinstance(generation, dict) or not all(
        _nonempty(generation.get(key)) for key in ("command", "version")
    ):
        errors.append("generation command/version missing")
    else:
        command = generation["command"]
        if "<" in command or ">" in command or "manual" in command.casefold():
            errors.append("generation command contains placeholder or non-executable manual prose")
        verifier = generation.get("independent_verifier_identity")
        if (
            not isinstance(verifier, dict)
            or not all(_nonempty(verifier.get(key)) for key in ("role", "status", "identity"))
            or verifier.get("status") in {"unassigned", "not_available"}
        ):
            errors.append("independent verifier identity is missing or unassigned")

    for marker, label in (
        (str(APPROVED_PLAN), "plan path"),
        (APPROVED_HASH, "plan hash"),
        (APPROVED_COMMIT, "Brain commit"),
    ):
        if marker not in readme_text:
            errors.append(f"README missing {label}")
    return errors


def _git_bytes(brain_root: Path, commit: str, relative_path: str) -> bytes:
    if not GIT.is_file():
        raise OSError("fixed Git executable is absent")
    result = subprocess.run(  # noqa: S603  # nosec B603 -- fixed binary
        [str(GIT), "-C", str(brain_root), "show", f"{commit}:{relative_path}"],
        check=True,
        capture_output=True,
        timeout=20,
    )
    return result.stdout


def validate_tracker_rows(
    manifest: dict[str, Any], tracker_rows: list[dict[str, str]]
) -> list[str]:
    errors: list[str] = []
    by_id = {row.get("id"): row for row in tracker_rows}
    for selected in manifest["qa_tracker"]["selected_rows"]:
        row = by_id.get(selected["id"])
        if row is None:
            errors.append(f"selected QA row absent from canonical tracker: {selected['id']}")
            continue
        if row.get("status") != selected.get("status"):
            errors.append(f"selected QA status mismatch: {selected['id']}")
        evidence_name = Path(selected["evidence_path"]).name
        anchors = f"{row.get('evidence', '')};{row.get('source', '')}"
        if evidence_name not in anchors:
            errors.append(f"selected QA evidence is not anchored by tracker row: {selected['id']}")
    return errors


def validate_live(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    brain_root = APPROVED_PLAN.parents[2]
    try:
        if sha256_path(APPROVED_PLAN) != APPROVED_HASH:
            errors.append("live approved plan bytes changed")
        plan_relative = str(APPROVED_PLAN.relative_to(brain_root))
        if sha256_bytes(_git_bytes(brain_root, APPROVED_COMMIT, plan_relative)) != APPROVED_HASH:
            errors.append("approved commit does not contain approved plan bytes")

        receipt = manifest["plan_gate"]["independent_receipt"]
        if sha256_path(APPROVED_RECEIPT) != receipt["sha256"]:
            errors.append("live receipt bytes do not match manifest")
        receipt_relative = str(APPROVED_RECEIPT.relative_to(brain_root))
        committed_receipt = _git_bytes(brain_root, APPROVED_COMMIT, receipt_relative)
        if sha256_bytes(committed_receipt) != receipt["sha256"]:
            errors.append("approved commit does not contain manifest receipt bytes")
        receipt_text = committed_receipt.decode("utf-8")
        if (
            "`APPROVE_FOR_G0`" not in receipt_text
            or "`independent_of_plan_author: true`" not in receipt_text
        ):
            errors.append("committed receipt lacks exact approval/independence evidence")

        tracker_path = Path(manifest["qa_tracker"]["path"])
        if sha256_path(tracker_path) != manifest["qa_tracker"]["tracker_sha256"]:
            errors.append("canonical QA tracker hash changed")
        with tracker_path.open(newline="", encoding="utf-8") as handle:
            errors.extend(validate_tracker_rows(manifest, list(csv.DictReader(handle))))
        for row in manifest["qa_tracker"]["selected_rows"]:
            evidence = Path(row["evidence_path"])
            if sha256_path(evidence) != row["evidence_sha256"]:
                errors.append(f"QA evidence hash changed: {row['id']}")
    except (OSError, KeyError, ValueError, subprocess.SubprocessError, UnicodeDecodeError) as exc:
        errors.append(f"live evidence validation failed closed: {type(exc).__name__}")
    return errors


def main() -> int:
    try:
        manifest = json.loads(BASELINE.read_text(encoding="utf-8"))
        readme_text = README.read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: unable to load frozen gate evidence: {type(exc).__name__}", file=sys.stderr)
        return 1
    errors = validate_manifest(manifest, readme_text)
    if not errors:
        errors.extend(validate_live(manifest))
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(
        "PASS: exact approved plan, committed receipt, command manifest, "
        "QA baseline, proof debt, and safety gate verified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
