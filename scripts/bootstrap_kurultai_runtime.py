#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "runtime-config"
STAGING = Path.home() / ".kurultai-rebuild-staging"

FILES = [
    "hermes.template.yaml",
    "profiles.yaml",
    "kurultai.yaml",
    "brain.yaml",
    "cron.manifest.json",
    "skills.manifest.json",
    "kanban.schema.json",
    "brain.manifest.json",
]

DIRS = [
    Path.home() / ".hermes",
    Path.home() / ".hermes" / "profiles",
    Path.home() / ".hermes" / "skills",
    Path.home() / ".hermes" / "cron",
    Path.home() / "brain",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage sanitized Kurultai rebuild configuration")
    parser.add_argument("--dry-run", action="store_true", help="print planned actions only")
    args = parser.parse_args()

    print("Kurultai rebuild staging")
    print(f"source={CONFIG}")
    print(f"staging={STAGING}")

    for d in DIRS:
        print(f"ensure-dir {d}")
        if not args.dry_run:
            d.mkdir(parents=True, exist_ok=True)

    for name in FILES:
        src = CONFIG / name
        dst = STAGING / name
        if not src.exists():
            print(f"missing {src}")
            continue
        print(f"copy {src} -> {dst}")
        if not args.dry_run:
            STAGING.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    marker = STAGING / "README.txt"
    print(f"write {marker}")
    if not args.dry_run:
        marker.write_text(
            "Sanitized Kurultai rebuild staging area. Review these files before applying live private configuration.\n"
        )


if __name__ == "__main__":
    main()
