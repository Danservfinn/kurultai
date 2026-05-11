#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import sys
from pathlib import Path
from typing import Any

from common import load_json, resolve_room_path, utc_now, write_json


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_str_list(value: Any) -> list[str]:
    return [str(item) for item in _as_list(value)]


def _load_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    data = load_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def _load_room(room: Path) -> dict[str, dict[str, Any] | None]:
    return {
        "idea": _load_optional_json(room / "ideas" / "idea-contract.json"),
        "product": _load_optional_json(room / "plans" / "product-plan.json"),
        "build": _load_optional_json(room / "plans" / "build-plan.json"),
        "receipt": _load_optional_json(room / "jobs" / "implementation-receipt.json"),
        "verification": _load_optional_json(room / "verification" / "verification-report.json"),
        "delta": _load_optional_json(room / "verification" / "verification-delta.json"),
    }


def _title_from_build_id(build_id: str) -> str:
    return build_id.removeprefix("build-").replace("-", " ").capitalize()


def _matches_any(path: str, patterns: list[str]) -> bool:
    normalized = path.lstrip("./")
    if normalized.startswith("/") or normalized.startswith(".."):
        return False
    for pattern in patterns:
        clean = pattern.lstrip("./")
        if fnmatch.fnmatch(normalized, clean):
            return True
        if clean.endswith("/**") and normalized.startswith(clean[:-3].rstrip("/") + "/"):
            return True
        if clean.endswith("/*") and normalized.startswith(clean[:-2].rstrip("/") + "/"):
            return True
    return False


def _violates_protected(path: str, patterns: list[str]) -> bool:
    normalized = path.lstrip("./")
    if normalized.startswith("/") or normalized.startswith(".."):
        return True
    return any(fnmatch.fnmatch(normalized, pattern.lstrip("./")) for pattern in patterns)


def build_qa_packet(room: Path) -> dict[str, Any]:
    data = _load_room(room)
    idea = data["idea"] or {}
    product = data["product"] or {}
    build = data["build"] or {}
    receipt = data["receipt"] or {}
    build_id = str(build.get("build_id") or receipt.get("build_id") or "unknown-build")
    verification_commands = _as_str_list(build.get("verification_commands"))
    commands_allowed = _as_str_list(build.get("commands_allowed"))
    parent = str(receipt.get("kanban_task_id", "")).strip()
    body = "\n".join(
        [
            f"Buildroom room: {room.name}",
            f"Build ID: {build_id}",
            f"Implemented by: {receipt.get('assignee', build.get('assignee', 'unknown'))}",
            "Independent QA only: verify implementation receipts and approved scope; do not implement feature work.",
            "Allowed QA commands:",
            *(f"- {command}" for command in (verification_commands + commands_allowed)),
            "Acceptance criteria:",
            *(f"- {item}" for item in _as_str_list(product.get("acceptance_criteria"))),
            "Allowed paths:",
            *(f"- {item}" for item in _as_str_list(product.get("allowed_paths"))),
            "Protected paths:",
            *(f"- {item}" for item in _as_str_list(product.get("protected_paths"))),
            "Write verification/verification-report.json, then run qa_trust.py delta and qa_trust.py trust.",
        ]
    )
    return {
        "title": f"buildroom-qa: {_title_from_build_id(build_id)}",
        "assignee": "ogedei",
        "body": body,
        "parents": [parent] if parent else [],
        "workspace_kind": "dir",
        "workspace_path": "${KURULTAI_HOME}",
        "idempotency_key": f"buildroom-qa:{build_id}",
        "metadata": {
            "room_id": room.name,
            "build_id": build_id,
            "plan_id": build.get("plan_id", product.get("plan_id", "")),
            "independent_of": build.get("assignee", product.get("owner", "unknown")),
            "verification_commands": verification_commands,
        },
    }


def build_delta(room: Path) -> dict[str, Any]:
    data = _load_room(room)
    build = data["build"] or {}
    product = data["product"] or {}
    receipt = data["receipt"] or {}
    report = data["verification"]
    build_id = str(build.get("build_id") or receipt.get("build_id") or "unknown-build")
    confirmed: list[str] = []
    unverified: list[str] = []
    regressions: list[str] = []

    if report is None:
        unverified.append("verification/verification-report.json missing")
    else:
        if report.get("pass") is True:
            confirmed.append("QA report passed")
        else:
            regressions.extend(_as_str_list(report.get("failures")) or ["QA report did not pass"])
        reported_commands = set(_as_str_list(report.get("commands_run")))
        expected_commands = set(_as_str_list(build.get("verification_commands")))
        missing_commands = sorted(expected_commands - reported_commands)
        if missing_commands and report.get("pass") is not True:
            unverified.extend(f"verification command not run: {command}" for command in missing_commands)

    for item in _as_str_list(receipt.get("deviations_from_plan")):
        regressions.append(f"deviation from plan: {item}")
    for item in _as_str_list(receipt.get("blocked_items")):
        unverified.append(f"blocked implementation item: {item}")

    allowed_paths = _as_str_list(product.get("allowed_paths"))
    protected_paths = _as_str_list(product.get("protected_paths"))
    for changed in _as_str_list(receipt.get("files_changed")):
        if _violates_protected(changed, protected_paths):
            regressions.append(f"protected path or unsafe path changed: {changed}")
        elif allowed_paths and not _matches_any(changed, allowed_paths):
            regressions.append(f"changed file outside allowed paths: {changed}")

    if regressions:
        state = "regression"
        next_action = "Investigate regressions or scope mismatch before archive."
    elif unverified:
        state = "missing_evidence"
        next_action = "Run independent QA and provide missing evidence."
    else:
        state = "confirmed"
        next_action = "Proceed to trust summary and retention review."

    delta = {
        "delta_id": f"delta-{build_id.removeprefix('build-')}",
        "build_id": build_id,
        "implementation_receipt_ref": "jobs/implementation-receipt.json",
        "verification_report_ref": "verification/verification-report.json",
        "state": state,
        "confirmed_claims": confirmed,
        "unverified_claims": unverified,
        "regressions": regressions,
        "next_action": next_action,
    }
    write_json(room / "verification" / "verification-delta.json", delta)
    return delta


def build_trust(room: Path) -> dict[str, Any]:
    data = _load_room(room)
    build = data["build"] or {}
    report = data["verification"]
    delta = data["delta"] or build_delta(room)
    state = str(delta.get("state", "missing_evidence"))
    reasons: list[str] = []
    open_questions: list[str] = []
    followups: list[str] = []

    if report is None:
        reasons.append("Independent QA report missing")
    elif report.get("pass") is True:
        reasons.append("QA report passed")
    else:
        reasons.append("QA report failed")

    regressions = _as_str_list(delta.get("regressions"))
    unverified = _as_str_list(delta.get("unverified_claims"))
    reasons.extend(_as_str_list(delta.get("confirmed_claims")))
    open_questions.extend(unverified)

    if state == "confirmed" and not regressions and not unverified:
        trust_state = "clean"
        risk = 0.1
        safe_to_archive = True
    elif regressions:
        trust_state = "investigate"
        risk = 0.9
        safe_to_archive = False
        if any("outside allowed paths" in item or "protected path" in item for item in regressions):
            followups.append("Investigate scope/protected-path mismatch before archive.")
        if report is not None and report.get("pass") is not True:
            followups.append("Fix failed QA/regressions and rerun verifier.")
        open_questions.extend(regressions)
    else:
        trust_state = "watch"
        risk = 0.5
        safe_to_archive = False
        followups.append("Run independent QA and regenerate verification report.")

    trust = {
        "trust_id": f"trust-{str(build.get('build_id', room.name)).removeprefix('build-')}",
        "room_id": room.name,
        "generated_at": utc_now(),
        "state": trust_state,
        "reasons": list(dict.fromkeys(reasons)),
        "risk_score": risk,
        "open_questions": list(dict.fromkeys(open_questions)),
        "required_followups": list(dict.fromkeys(followups)),
        "safe_to_archive": safe_to_archive,
    }
    write_json(room / "trust" / "trust-report.json", trust)
    return trust


def main() -> int:
    parser = argparse.ArgumentParser(description="Build independent QA packets, verification deltas, and trust summaries for buildroom rooms.")
    sub = parser.add_subparsers(dest="command", required=True)
    qa_packet = sub.add_parser("qa-packet", help="Write a Kanban task packet for independent QA.")
    qa_packet.add_argument("room", type=Path)
    qa_packet.add_argument("output", type=Path)
    delta = sub.add_parser("delta", help="Compare implementation receipt with verification report and write verification-delta.json.")
    delta.add_argument("room", type=Path)
    trust = sub.add_parser("trust", help="Summarize trust state from verification and delta artifacts.")
    trust.add_argument("room", type=Path)
    args = parser.parse_args()

    try:
        room = resolve_room_path(args.room)
        if args.command == "qa-packet":
            packet = build_qa_packet(room)
            write_json(args.output, packet)
            print(f"wrote QA task packet: {args.output}")
        elif args.command == "delta":
            delta_data = build_delta(room)
            print(f"wrote verification delta: {room / 'verification' / 'verification-delta.json'} ({delta_data['state']})")
        elif args.command == "trust":
            trust_data = build_trust(room)
            print(f"wrote trust report: {room / 'trust' / 'trust-report.json'} ({trust_data['state']})")
        return 0
    except Exception as exc:
        print(f"qa trust failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
