#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path
from common import EXPECTED_ARTIFACTS, load_json, resolve_room_path, utc_now, write_json

def build_summary(room_dir: Path) -> dict:
    idea=load_json(room_dir/"ideas/idea-contract.json"); build=load_json(room_dir/"plans/build-plan.json")
    trust=load_json(room_dir/"trust/trust-report.json"); verification=load_json(room_dir/"verification/verification-report.json")
    retention=load_json(room_dir/"retention/retention-review.json"); room_id=room_dir.name
    artifacts=[rel for rel in EXPECTED_ARTIFACTS if (room_dir/rel).exists()]
    decisions=list(trust.get("required_followups", []))
    if retention.get("recommendation") == "prune": decisions.append("Human approval required before any destructive retention action.")
    return {"summary_id":f"summary-{room_id}","room_id":room_id,"generated_at":utc_now(),"headline":idea.get("title", f"Buildroom {room_id}"),"status":trust.get("state","watch"),"current_owner":build.get("assignee","unknown"),"latest_artifacts":artifacts,"operator_needs_to_know":[f"Trust state: {trust.get('state')} (risk_score={trust.get('risk_score')}).",f"Verification pass: {verification.get('pass')} via {verification.get('method')}.",f"Retention recommendation: {retention.get('recommendation')}.",],"operator_decisions_needed":decisions,"links":[f"buildroom://{room_id}/{rel}" for rel in artifacts]}

def main() -> int:
    parser=argparse.ArgumentParser(description="Create or refresh operator/operator-summary.json for a buildroom room."); parser.add_argument("room", type=Path)
    args=parser.parse_args(); room=resolve_room_path(args.room)
    target=room/"operator/operator-summary.json"; write_json(target, build_summary(room)); print(f"wrote {target}"); return 0
if __name__ == "__main__": raise SystemExit(main())
