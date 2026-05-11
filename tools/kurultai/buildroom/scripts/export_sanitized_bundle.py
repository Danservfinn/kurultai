#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path
from common import copy_sanitized_room, resolve_room_path

def main() -> int:
    parser=argparse.ArgumentParser(description="Export a sanitized copy of a buildroom room."); parser.add_argument("room", type=Path); parser.add_argument("destination", type=Path)
    args=parser.parse_args(); room=resolve_room_path(args.room)
    skipped=copy_sanitized_room(room, args.destination); print(f"exported sanitized room: {room} -> {args.destination}")
    for item in skipped: print(f"skipped private artifact: {item}")
    return 0
if __name__ == "__main__": raise SystemExit(main())
