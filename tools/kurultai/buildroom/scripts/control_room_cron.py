#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from common import BUILDROOM_ROOT, utc_now
from control_room import DEFAULT_HTML, DEFAULT_JSON, DEFAULT_MARKDOWN, ROOMS_ROOT, build_payload, write_outputs

DEFAULT_ATTENTION = BUILDROOM_ROOT / "control-room-attention-items.json"
DEFAULT_KANBAN_DRAFTS = BUILDROOM_ROOT / "control-room-kanban-drafts.json"
SEVERITY_ORDER = {"info": 0, "warning": 1, "error": 2, "critical": 3}


def severity_rank(severity: str) -> int:
    return SEVERITY_ORDER.get(severity, 0)


def room_attention_items(room: dict[str, Any]) -> list[dict[str, Any]]:
    room_id = str(room.get("room_id") or "unknown-room")
    headline = str(room.get("headline") or room_id)
    trust_state = str(room.get("trust_state") or "watch")
    retention = str(room.get("retention") or "unknown")
    phase = str(room.get("phase") or "unknown")
    missing = [str(item) for item in room.get("missing_artifacts", [])]
    decisions = [str(item) for item in room.get("operator_decisions_needed", [])]
    items: list[dict[str, Any]] = []

    if trust_state == "investigate":
        items.append({
            "id": f"{room_id}:trust-investigate",
            "room_id": room_id,
            "headline": headline,
            "category": "trust",
            "severity": "critical",
            "summary": "Trust report requires investigation.",
            "recommended_action": "Open the trust report, classify the failure mode, and create a repair or quarantine follow-up.",
            "kanban_recommended": True,
        })
    elif trust_state == "watch":
        items.append({
            "id": f"{room_id}:trust-watch",
            "room_id": room_id,
            "headline": headline,
            "category": "trust",
            "severity": "warning",
            "summary": "Room is in watch state.",
            "recommended_action": "Refresh the operator summary and decide whether the room is clean, needs more evidence, or needs investigation.",
            "kanban_recommended": True,
        })

    if missing:
        items.append({
            "id": f"{room_id}:missing-evidence",
            "room_id": room_id,
            "headline": headline,
            "category": "missing_evidence",
            "severity": "error",
            "summary": f"Room is missing {len(missing)} required artifact(s).",
            "missing_artifacts": missing,
            "recommended_action": f"Fill or explicitly receipt the first missing artifact: {missing[0]}",
            "kanban_recommended": True,
        })

    if decisions:
        items.append({
            "id": f"{room_id}:operator-decisions",
            "room_id": room_id,
            "headline": headline,
            "category": "operator_decision",
            "severity": "warning",
            "summary": f"Room has {len(decisions)} operator decision(s) queued.",
            "operator_decisions_needed": decisions,
            "recommended_action": "Resolve or route the operator decision queue.",
            "kanban_recommended": True,
        })

    if phase == "complete" and retention in {"improve", "park", "prune"}:
        severity = "critical" if retention == "prune" else "warning"
        items.append({
            "id": f"{room_id}:retention-{retention}",
            "room_id": room_id,
            "headline": headline,
            "category": "retention",
            "severity": severity,
            "summary": f"Retention review recommends {retention}.",
            "recommended_action": "Create the retention follow-up or record an explicit no-op receipt.",
            "kanban_recommended": retention == "improve",
        })

    if not items and phase == "complete" and trust_state == "clean":
        items.append({
            "id": f"{room_id}:clean-monitor",
            "room_id": room_id,
            "headline": headline,
            "category": "monitor",
            "severity": "info",
            "summary": "Room is clean and complete.",
            "recommended_action": "No immediate action; include in retention sweep.",
            "kanban_recommended": False,
        })

    return items


def build_attention_payload(control_payload: dict[str, Any]) -> dict[str, Any]:
    rooms = control_payload.get("rooms", [])
    items: list[dict[str, Any]] = []
    for room in rooms:
        if isinstance(room, dict):
            items.extend(room_attention_items(room))
    actionable = [item for item in items if item.get("kanban_recommended")]
    items.sort(key=lambda item: (-severity_rank(str(item.get("severity", "info"))), str(item.get("room_id", "")), str(item.get("category", ""))))
    actionable.sort(key=lambda item: (-severity_rank(str(item.get("severity", "info"))), str(item.get("room_id", "")), str(item.get("category", ""))))
    return {
        "generated_at": utc_now(),
        "summary": {
            "room_count": len(rooms),
            "attention_item_count": len(items),
            "actionable_item_count": len(actionable),
            "critical_count": sum(1 for item in items if item.get("severity") == "critical"),
            "error_count": sum(1 for item in items if item.get("severity") == "error"),
            "warning_count": sum(1 for item in items if item.get("severity") == "warning"),
            "info_count": sum(1 for item in items if item.get("severity") == "info"),
        },
        "items": items,
        "actionable_items": actionable,
    }


def kanban_draft_for_item(item: dict[str, Any]) -> dict[str, Any]:
    room_id = str(item.get("room_id") or "unknown-room")
    category = str(item.get("category") or "attention")
    severity = str(item.get("severity") or "info")
    return {
        "title": f"Buildroom follow-up: {room_id} — {category}",
        "priority": "high" if severity in {"critical", "error"} else "normal",
        "labels": ["buildroom", "control-room", category, severity],
        "source": "buildroom-control-room-cron-v0",
        "room_id": room_id,
        "body": "\n".join([
            f"Room: {room_id}",
            f"Headline: {item.get('headline', room_id)}",
            f"Category: {category}",
            f"Severity: {severity}",
            f"Summary: {item.get('summary', '')}",
            f"Recommended action: {item.get('recommended_action', '')}",
        ]),
    }


def build_kanban_drafts(attention_payload: dict[str, Any]) -> dict[str, Any]:
    actionable = attention_payload.get("actionable_items", [])
    drafts = [kanban_draft_for_item(item) for item in actionable if isinstance(item, dict)]
    return {
        "generated_at": utc_now(),
        "source": "buildroom-control-room-cron-v0",
        "draft_count": len(drafts),
        "drafts": drafts,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def git_has_changes(paths: list[Path]) -> bool:
    result = subprocess.run(["git", "status", "--porcelain", "--", *[str(path) for path in paths]], text=True, capture_output=True, timeout=30)
    return bool(result.stdout.strip())


def main() -> int:
    parser = argparse.ArgumentParser(description="Cron-ready buildroom Control Room regeneration and attention extraction.")
    parser.add_argument("--rooms-root", type=Path, default=ROOMS_ROOT)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--html-output", type=Path, default=DEFAULT_HTML)
    parser.add_argument("--attention-output", type=Path, default=DEFAULT_ATTENTION)
    parser.add_argument("--kanban-drafts-output", type=Path, default=DEFAULT_KANBAN_DRAFTS)
    parser.add_argument("--fail-on-actionable", action="store_true", help="Exit 2 when actionable attention items exist.")
    parser.add_argument("--fail-on-changed", action="store_true", help="Exit 3 when generated outputs changed the working tree.")
    args = parser.parse_args()
    control_payload = build_payload(args.rooms_root)
    write_outputs(control_payload, args.markdown_output, args.json_output, args.html_output)
    attention_payload = build_attention_payload(control_payload)
    kanban_payload = build_kanban_drafts(attention_payload)
    write_json(args.attention_output, attention_payload)
    write_json(args.kanban_drafts_output, kanban_payload)
    print(json.dumps({
        "room_count": attention_payload["summary"]["room_count"],
        "attention_item_count": attention_payload["summary"]["attention_item_count"],
        "actionable_item_count": attention_payload["summary"]["actionable_item_count"],
        "attention_output": str(args.attention_output),
        "kanban_drafts_output": str(args.kanban_drafts_output),
    }, sort_keys=True))
    if args.fail_on_actionable and attention_payload["summary"]["actionable_item_count"]:
        return 2
    if args.fail_on_changed and git_has_changes([args.markdown_output, args.json_output, args.html_output, args.attention_output, args.kanban_drafts_output]):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
