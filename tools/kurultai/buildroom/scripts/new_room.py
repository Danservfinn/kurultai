#!/usr/bin/env python3
from __future__ import annotations
import argparse
from common import BUILDROOM_ROOT, EXPECTED_ARTIFACTS, utc_now, write_json

def main() -> int:
    parser=argparse.ArgumentParser(description="Create an empty buildroom room skeleton with placeholder JSON files."); parser.add_argument("room_id")
    args=parser.parse_args(); room=BUILDROOM_ROOT/"rooms"/args.room_id
    for rel in EXPECTED_ARTIFACTS:
        path=room/rel
        if not path.exists(): write_json(path, {"_placeholder": True, "room_id": args.room_id, "created_at": utc_now(), "schema_hint": rel})
    print(f"created room skeleton: {room}"); return 0
if __name__ == "__main__": raise SystemExit(main())
