#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from common import load_json, resolve_room_path, utc_now, write_json


def _kanban_parent_ids(task_refs: list[Any]) -> list[str]:
    parents: list[str] = []
    for ref in task_refs:
        if isinstance(ref, str) and ref.startswith("kanban:"):
            task_id = ref.removeprefix("kanban:").strip()
            if task_id:
                parents.append(task_id)
    return parents


def _title_from_build_id(build_id: str) -> str:
    stem = build_id.removeprefix("build-")
    return stem.replace("-", " ").capitalize()


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _load_room_contracts(room: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    idea = load_json(room / "ideas" / "idea-contract.json")
    review = load_json(room / "reviews" / "main-review.json")
    product = load_json(room / "plans" / "product-plan.json")
    build = load_json(room / "plans" / "build-plan.json")
    return idea, review, product, build


def _assert_approved(review: dict[str, Any]) -> None:
    if review.get("decision") != "approved_for_planning":
        reasons = "; ".join(str(item) for item in _as_list(review.get("blocked_reasons")))
        suffix = f": {reasons}" if reasons else ""
        raise ValueError(f"main-review decision is not approved_for_planning{suffix}")


def build_task_packet(room: Path) -> dict[str, Any]:
    idea, review, product, build = _load_room_contracts(room)
    _assert_approved(review)
    build_id = str(build.get("build_id", "unknown-build"))
    task_refs = [str(ref) for ref in _as_list(build.get("task_refs"))]
    allowed_paths = [str(path) for path in _as_list(product.get("allowed_paths"))]
    protected_paths = [str(path) for path in _as_list(product.get("protected_paths"))]
    verification_commands = [str(command) for command in _as_list(build.get("verification_commands"))]
    steps = _as_list(build.get("steps"))
    step_lines = []
    for step in steps:
        if isinstance(step, dict):
            step_id = step.get("step_id", "step")
            description = step.get("description", step)
            step_lines.append(f"- {step_id}: {description}")
        else:
            step_lines.append(f"- {step}")
    body = "\n".join(
        [
            f"Buildroom room: {room.name}",
            f"Build ID: {build_id}",
            f"Plan ID: {build.get('plan_id', '')}",
            f"Idea: {idea.get('idea_id', '')} — {idea.get('title', '')}",
            f"Main review: {review.get('review_id', '')} ({review.get('decision', '')})",
            f"Task refs: {', '.join(task_refs) if task_refs else 'none'}",
            "Allowed paths:",
            *(f"- {path}" for path in allowed_paths),
            "Protected paths:",
            *(f"- {path}" for path in protected_paths),
            "Steps:",
            *step_lines,
            "Verification commands:",
            *(f"- {command}" for command in verification_commands),
            "Stop if any stop_condition or out_of_scope item applies; do not expand beyond the approved build plan.",
        ]
    )
    return {
        "title": f"buildroom: {_title_from_build_id(build_id)}",
        "assignee": build.get("assignee", product.get("owner", "coder")),
        "body": body,
        "parents": _kanban_parent_ids(task_refs),
        "workspace_kind": "dir",
        "workspace_path": "${KURULTAI_HOME}",
        "idempotency_key": f"buildroom:{build_id}",
        "metadata": {
            "room_id": room.name,
            "build_id": build_id,
            "plan_id": build.get("plan_id", ""),
            "idea_id": idea.get("idea_id", ""),
            "task_refs": task_refs,
            "verification_commands": verification_commands,
        },
    }


def _metadata_list(metadata: dict[str, Any], *names: str) -> list[str]:
    for name in names:
        value = metadata.get(name)
        if isinstance(value, list):
            return [str(item) for item in value]
    return []


def build_implementation_receipt(room: Path, completion: dict[str, Any]) -> dict[str, Any]:
    _, _, _, build = _load_room_contracts(room)
    task_id = str(completion.get("id") or completion.get("task_id") or "unknown-task")
    metadata = completion.get("metadata") if isinstance(completion.get("metadata"), dict) else {}
    evidence_refs = [f"kanban:{task_id}"]
    evidence_refs.extend(str(ref) for ref in _as_list(metadata.get("evidence_refs")))
    return {
        "receipt_id": f"receipt-{task_id}",
        "build_id": build.get("build_id", "unknown-build"),
        "assignee": completion.get("assignee", build.get("assignee", "unknown")),
        "started_at": completion.get("started_at") or metadata.get("started_at") or utc_now(),
        "completed_at": completion.get("completed_at") or metadata.get("completed_at") or utc_now(),
        "files_changed": _metadata_list(metadata, "changed_files", "files_changed"),
        "commands_run": _metadata_list(metadata, "commands_run", "commands"),
        "tests_run": _metadata_list(metadata, "tests_run", "checks"),
        "commit_sha": str(metadata.get("commit_sha", "")),
        "open_diffs_summary": str(metadata.get("open_diffs_summary", completion.get("summary", ""))),
        "deviations_from_plan": _metadata_list(metadata, "deviations_from_plan"),
        "blocked_items": _metadata_list(metadata, "blocked_items", "blockers"),
        "kanban_task_id": task_id,
        "kanban_status": str(completion.get("status", "unknown")),
        "evidence_refs": evidence_refs,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Map buildroom plans to Kanban task packets and Kanban completions to implementation receipts.")
    sub = parser.add_subparsers(dest="command", required=True)
    task_packet = sub.add_parser("task-packet", help="Write a Kanban task creation packet JSON from an approved buildroom room.")
    task_packet.add_argument("room", type=Path)
    task_packet.add_argument("output", type=Path)
    receipt = sub.add_parser("receipt", help="Write jobs/implementation-receipt.json from a Kanban completion JSON object.")
    receipt.add_argument("room", type=Path)
    receipt.add_argument("completion_json", type=Path)
    args = parser.parse_args()

    try:
        room = resolve_room_path(args.room)
        if args.command == "task-packet":
            packet = build_task_packet(room)
            write_json(args.output, packet)
            print(f"wrote Kanban task packet: {args.output}")
        elif args.command == "receipt":
            completion = load_json(args.completion_json)
            if not isinstance(completion, dict):
                raise ValueError("completion JSON must be an object")
            receipt_data = build_implementation_receipt(room, completion)
            target = room / "jobs" / "implementation-receipt.json"
            write_json(target, receipt_data)
            print(f"wrote implementation receipt: {target}")
        return 0
    except Exception as exc:
        print(f"kanban adapter failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
