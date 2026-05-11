#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from html import escape
from pathlib import Path
from typing import Any

from common import BUILDROOM_ROOT, EXPECTED_ARTIFACTS, load_json, utc_now

ROOMS_ROOT = BUILDROOM_ROOT / "rooms"
DEFAULT_MARKDOWN = BUILDROOM_ROOT / "control-room.md"
DEFAULT_JSON = BUILDROOM_ROOT / "control-room.json"
DEFAULT_HTML = BUILDROOM_ROOT / "control-room.html"


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


def existing_artifact_links(room_dir: Path) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    for rel in EXPECTED_ARTIFACTS:
        if (room_dir / rel).exists():
            links.append({"label": rel, "href": f"rooms/{room_dir.name}/{rel}"})
    return links


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


def next_action(phase: str, trust_state: str, retention: str, missing: list[str], decisions: list[str]) -> str:
    if trust_state == "investigate":
        return "Investigate trust report before expanding or shipping this room."
    if missing:
        return f"Fill missing artifact: {missing[0]}."
    if decisions:
        return "Resolve operator decision queue."
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
    decisions = [str(item) for item in operator.get("operator_decisions_needed", [])]
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
        "operator_decisions_needed": decisions,
        "artifact_links": existing_artifact_links(room_dir),
        "needs_decision": bool(decisions),
        "has_missing_evidence": bool(missing),
        "next_action": next_action(phase, trust_state, retention_recommendation, missing, decisions),
    }


def build_payload(rooms_root: Path) -> dict[str, Any]:
    generated_at = utc_now()
    cards = [room_card(room) for room in room_dirs(rooms_root)]
    summary = {
        "generated_at": generated_at,
        "room_count": len(cards),
        "trust_clean": sum(1 for c in cards if c["trust_state"] == "clean"),
        "trust_watch": sum(1 for c in cards if c["trust_state"] == "watch"),
        "trust_investigate": sum(1 for c in cards if c["trust_state"] == "investigate"),
        "rooms_with_missing_evidence": sum(1 for c in cards if c["missing_artifacts"]),
        "rooms_needing_decision": sum(1 for c in cards if c["operator_decisions_needed"]),
    }
    return {"summary": summary, "rooms": cards}


def build_report_from_payload(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    cards = payload["rooms"]
    lines = [
        "# Kurultai Buildroom Control Room",
        "",
        f"Generated: {summary['generated_at']}",
        "",
        "## Summary",
        "",
        f"- Rooms: {summary['room_count']}",
        f"- Trust clean: {summary['trust_clean']}",
        f"- Trust watch: {summary['trust_watch']}",
        f"- Trust investigate: {summary['trust_investigate']}",
        f"- Rooms with missing evidence: {summary['rooms_with_missing_evidence']}",
        f"- Rooms needing decision: {summary['rooms_needing_decision']}",
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


def build_report(rooms_root: Path) -> str:
    return build_report_from_payload(build_payload(rooms_root))


def badge_class(value: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in value.lower()).strip("-") or "unknown"


def render_filter_button(label: str, filter_name: str) -> str:
    return f'<button class="filter" data-filter="{escape(filter_name)}">{escape(label)}</button>'


def build_html(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    cards = payload["rooms"]
    room_html: list[str] = []
    for card in cards:
        flags = ["all", card["trust_state"]]
        if card["has_missing_evidence"]:
            flags.append("missing")
        if card["needs_decision"]:
            flags.append("decision")
        links = "".join(
            f'<a href="{escape(link["href"])}">{escape(link["label"])}</a>'
            for link in card["artifact_links"]
        ) or '<span class="muted">No artifacts linked</span>'
        missing = ", ".join(card["missing_artifacts"]) if card["missing_artifacts"] else "none"
        decisions = ", ".join(card["operator_decisions_needed"]) if card["operator_decisions_needed"] else "none"
        room_html.append(
            f'''
<section class="room-card {escape(card['trust_state'])}" data-flags="{' '.join(flags)}">
  <div class="room-topline">
    <div>
      <p class="eyebrow">{escape(card['room_id'])}</p>
      <h2>{escape(str(card['headline']))}</h2>
    </div>
    <span class="badge {badge_class(card['trust_state'])}">{escape(card['trust_state'])}</span>
  </div>
  <div class="metrics">
    <div><span>Phase</span><strong>{escape(card['phase'])}</strong></div>
    <div><span>Risk</span><strong>{escape(str(card['risk_score']))}</strong></div>
    <div><span>Verification</span><strong>{escape(str(card['verification_delta']))}</strong></div>
    <div><span>Retention</span><strong>{escape(str(card['retention']))}</strong></div>
  </div>
  <div class="details">
    <p><strong>Verification pass:</strong> {escape(str(card['verification_pass']))}</p>
    <p><strong>Missing evidence:</strong> {escape(missing)}</p>
    <p><strong>Operator decisions:</strong> {escape(decisions)}</p>
    <p><strong>Next action:</strong> {escape(str(card['next_action']))}</p>
  </div>
  <details>
    <summary>Artifacts</summary>
    <div class="artifact-grid">{links}</div>
  </details>
</section>'''
        )
    filters = "\n".join([
        render_filter_button("All", "all"),
        render_filter_button("Clean", "clean"),
        render_filter_button("Watch", "watch"),
        render_filter_button("Investigate", "investigate"),
        render_filter_button("Missing evidence", "missing"),
        render_filter_button("Needs decision", "decision"),
    ])
    rooms_markup = "\n".join(room_html) if room_html else '<p class="empty">No buildroom rooms found.</p>'
    payload_json = escape(json.dumps(payload, indent=2, sort_keys=True))
    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Kurultai Buildroom Control Room</title>
  <style>
    :root {{ color-scheme: dark; --bg:#070b13; --panel:#101827; --line:#25324a; --text:#edf4ff; --muted:#9fb0ca; --green:#4ade80; --yellow:#facc15; --red:#fb7185; --blue:#60a5fa; --purple:#c084fc; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background:radial-gradient(circle at top left,#1d2b4f 0,#070b13 38rem); color:var(--text); }}
    main {{ max-width:1180px; margin:0 auto; padding:40px 20px 64px; }}
    .hero {{ display:flex; justify-content:space-between; gap:24px; align-items:flex-end; margin-bottom:28px; }}
    h1 {{ font-size:clamp(2rem,5vw,4.5rem); line-height:.95; margin:0; letter-spacing:-.06em; }}
    .subtitle,.muted {{ color:var(--muted); }}
    .summary {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:14px; margin:28px 0; }}
    .stat,.room-card {{ background:rgba(16,24,39,.86); border:1px solid var(--line); box-shadow:0 24px 80px rgba(0,0,0,.35); border-radius:22px; }}
    .stat {{ padding:18px; }} .stat span,.metrics span,.eyebrow {{ color:var(--muted); font-size:.78rem; text-transform:uppercase; letter-spacing:.12em; }} .stat strong {{ display:block; font-size:2rem; margin-top:6px; }}
    .filters {{ display:flex; flex-wrap:wrap; gap:10px; margin:24px 0; }}
    button.filter {{ border:1px solid var(--line); background:#111a2d; color:var(--text); padding:10px 14px; border-radius:999px; cursor:pointer; }} button.filter.active {{ border-color:var(--blue); box-shadow:0 0 0 3px rgba(96,165,250,.2); }}
    .rooms {{ display:grid; gap:18px; }} .room-card {{ padding:22px; }} .room-card.clean {{ border-color:rgba(74,222,128,.35); }} .room-card.watch {{ border-color:rgba(250,204,21,.35); }} .room-card.investigate {{ border-color:rgba(251,113,133,.5); }}
    .room-topline {{ display:flex; justify-content:space-between; gap:18px; align-items:flex-start; }} h2 {{ margin:.25rem 0 0; font-size:1.35rem; }}
    .badge {{ border-radius:999px; padding:8px 11px; font-weight:700; }} .badge.clean {{ background:rgba(74,222,128,.15); color:var(--green); }} .badge.watch {{ background:rgba(250,204,21,.15); color:var(--yellow); }} .badge.investigate {{ background:rgba(251,113,133,.15); color:var(--red); }}
    .metrics {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(130px,1fr)); gap:12px; margin:18px 0; }} .metrics div {{ background:#0b1220; border:1px solid var(--line); border-radius:16px; padding:12px; }} .metrics strong {{ display:block; margin-top:5px; }}
    .details p {{ margin:.45rem 0; }} details {{ margin-top:14px; }} summary {{ cursor:pointer; color:var(--blue); }} .artifact-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:8px; margin-top:12px; }} .artifact-grid a {{ color:#bfdbfe; background:#0b1220; border:1px solid var(--line); padding:8px 10px; border-radius:10px; text-decoration:none; }}
    .empty {{ color:var(--muted); border:1px dashed var(--line); border-radius:18px; padding:24px; }} pre {{ white-space:pre-wrap; color:var(--muted); font-size:.78rem; }}
  </style>
</head>
<body>
<main>
  <section class="hero">
    <div>
      <p class="eyebrow">Kurultai / Buildroom</p>
      <h1>Control Room</h1>
      <p class="subtitle">Generated {escape(summary['generated_at'])}. Static, public-safe dashboard for buildroom trust and evidence.</p>
    </div>
  </section>
  <section class="summary">
    <div class="stat"><span>Rooms</span><strong>{summary['room_count']}</strong></div>
    <div class="stat"><span>Clean</span><strong>{summary['trust_clean']}</strong></div>
    <div class="stat"><span>Watch</span><strong>{summary['trust_watch']}</strong></div>
    <div class="stat"><span>Investigate</span><strong>{summary['trust_investigate']}</strong></div>
    <div class="stat"><span>Missing evidence</span><strong>{summary['rooms_with_missing_evidence']}</strong></div>
    <div class="stat"><span>Needs decision</span><strong>{summary['rooms_needing_decision']}</strong></div>
  </section>
  <nav class="filters" aria-label="Room filters">{filters}</nav>
  <section class="rooms" id="rooms">{rooms_markup}</section>
  <details>
    <summary>Embedded JSON payload</summary>
    <pre>{payload_json}</pre>
  </details>
</main>
<script>
const buttons = [...document.querySelectorAll('button.filter')];
const cards = [...document.querySelectorAll('.room-card')];
function applyFilter(filter) {{
  buttons.forEach(button => button.classList.toggle('active', button.dataset.filter === filter));
  cards.forEach(card => {{
    const flags = (card.dataset.flags || '').split(' ');
    card.hidden = filter !== 'all' && !flags.includes(filter);
  }});
}}
buttons.forEach(button => button.addEventListener('click', () => applyFilter(button.dataset.filter)));
applyFilter('all');
</script>
</body>
</html>
'''


def write_outputs(payload: dict[str, Any], markdown: Path, json_path: Path, html_path: Path) -> list[Path]:
    markdown.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(build_report_from_payload(payload), encoding="utf-8")
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(build_html(payload), encoding="utf-8")
    return [markdown, json_path, html_path]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build markdown, JSON, and static HTML Control Room reports across buildroom rooms.")
    parser.add_argument("--rooms-root", type=Path, default=ROOMS_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_MARKDOWN, help="Markdown output path.")
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--html-output", type=Path, default=DEFAULT_HTML)
    args = parser.parse_args()
    payload = build_payload(args.rooms_root)
    written = write_outputs(payload, args.output, args.json_output, args.html_output)
    for path in written:
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
