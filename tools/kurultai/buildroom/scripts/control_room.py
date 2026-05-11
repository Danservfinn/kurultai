#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from common import BUILDROOM_ROOT, EXPECTED_ARTIFACTS, load_json, utc_now

ROOMS_ROOT = BUILDROOM_ROOT / "rooms"
DEFAULT_OUTPUT = BUILDROOM_ROOT / "control-room.md"


def optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = load_json(path)
    return data if isinstance(data, dict) else {}


def room_dirs(rooms_root: Path) -> list[Path]:
    if not rooms_root.exists():
        return []
    return sorted([p for p in rooms_root.iterdir() if p.is_dir()], key=lambda p: p.name)


def missing_artifacts(room_dir: Path) -> list[str]:
    return [rel for rel in EXPECTED_ARTIFACTS if not (room_dir / rel).exists()]


def infer_phase(room_dir: Path, missing: list[str]) -> str:
    if not missing:
        return "complete"
    if not (room_dir / "research/research-input.json").exists():
        return "intake"
    if not (room_dir / "ideas/idea-contract.json").exists():
        return "idea"
    if not (room_dir / "plans/build-plan.json").exists():
        return "planning"
    if not (room_dir / "jobs/implementation-receipt.json").exists():
        return "implementation"
    if not (room_dir / "verification/verification-report.json").exists():
        return "verification"
    if not (room_dir / "trust/trust-report.json").exists():
        return "trust"
    if not (room_dir / "retention/retention-review.json").exists():
        return "retention"
    return "operator-summary"


def next_action(phase: str, trust_state: str, retention: str, missing: list[str]) -> str:
    if trust_state == "investigate":
        return "Investigate trust report before expanding or shipping this room."
    if missing:
        return f"Fill missing artifact: {missing[0]}."
    if retention == "improve":
        return "Create a follow-up improvement task from the retention review."
    if retention == "park":
        return "Park unless the operator reactivates this room."
    if retention == "prune":
        return "Require explicit human approval before pruning."
    if phase == "complete" and trust_state == "clean":
        return "Ready for PR/merge monitoring or retention follow-up."
    return "Review room state and refresh operator summary."


def room_card(room_dir: Path) -> dict[str, Any]:
    idea = optional_json(room_dir / "ideas/idea-contract.json")
    trust = optional_json(room_dir / "trust/trust-report.json")
    verification = optional_json(room_dir / "verification/verification-report.json")
    delta = optional_json(room_dir / "verification/verification-delta.json")
    retention = optional_json(room_dir / "retention/retention-review.json")
    operator = optional_json(room_dir / "operator/operator-summary.json")
    missing = missing_artifacts(room_dir)
    phase = infer_phase(room_dir, missing)
    trust_state = str(trust.get("state") or operator.get("status") or "watch")
    retention_recommendation = str(retention.get("recommendation") or "unknown")
    return {
        "room_id": room_dir.name,
        "headline": idea.get("title") or operator.get("headline") or room_dir.name,
        "phase": phase,
        "trust_state": trust_state,
        "risk_score": trust.get("risk_score", "unknown"),
        "verification_pass": verification.get("pass", "unknown"),
        "verification_delta": delta.get("delta", delta.get("state", "unknown")),
        "retention": retention_recommendation,
        "missing_artifacts": missing,
        "operator_decisions_needed": operator.get("operator_decisions_needed", []),
        "next_action": next_action(phase, trust_state, retention_recommendation, missing),
    }


def build_report(rooms_root: Path) -> str:
    cards = [room_card(room) for room in room_dirs(rooms_root)]
    clean = sum(1 for c in cards if c["trust_state"] == "clean")
    watch = sum(1 for c in cards if c["trust_state"] == "watch")
    investigate = sum(1 for c in cards if c["trust_state"] == "investigate")
    incomplete = sum(1 for c in cards if c["missing_artifacts"])
    lines = [
        "# Kurultai Buildroom Control Room",
        "",
        f"Generated: {utc_now()}",
        "",
        "## Summary",
        "",
        f"- Rooms: {len(cards)}",
        f"- Trust clean: {clean}",
        f"- Trust watch: {watch}",
        f"- Trust investigate: {investigate}",
        f"- Rooms with missing evidence: {incomplete}",
        "",
        "## Rooms",
        "",
    ]
    if not cards:
        lines.append("No buildroom rooms found.")
        lines.append("")
        return "\n".join(lines)
    for card in cards:
        lines.extend([
            f"### {card['room_id']}",
            "",
            f"- Headline: {card['headline']}",
            f"- Phase: {card['phase']}",
            f"- Trust: {card['trust_state']} (risk_score={card['risk_score']})",
            f"- Verification pass: {card['verification_pass']}",
            f"- Verification delta: {card['verification_delta']}",
            f"- Retention: {card['retention']}",
            f"- Missing evidence: {', '.join(card['missing_artifacts']) if card['missing_artifacts'] else 'none'}",
            f"- Operator decisions needed: {', '.join(card['operator_decisions_needed']) if card['operator_decisions_needed'] else 'none'}",
            f"- Next action: {card['next_action']}",
            "",
        ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a markdown control-room report across buildroom rooms.")
    parser.add_argument("--rooms-root", type=Path, default=ROOMS_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = build_report(args.rooms_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
