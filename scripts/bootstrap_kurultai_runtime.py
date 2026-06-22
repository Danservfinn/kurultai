#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "runtime-config"
DEFAULT_STAGING = Path.home() / ".kurultai-rebuild-staging"

FILES = [
    "identity.yaml",
    "hermes.template.yaml",
    "profiles.yaml",
    "kurultai.yaml",
    "brain.yaml",
    "gateways.yaml",
    "install-expert.yaml",
    "cron.manifest.json",
    "skills.manifest.json",
    "kanban.schema.json",
    "brain.manifest.json",
]

BRAIN_DIRECTORIES = [
    "entities",
    "projects",
    "infrastructure",
    "concepts",
    "analyses",
    "docs/plans",
    "raw/assets",
    "queue",
    "generated",
    "receipts",
    "operations",
    "content/artifacts",
]


def log_action(dry_run: bool, action: str, *parts: object) -> None:
    prefix = "[dry-run] " if dry_run else ""
    print(prefix + action, *parts)


def ensure_dir(path: Path, dry_run: bool) -> None:
    log_action(dry_run, "ensure-dir", path)
    if not dry_run:
        path.mkdir(parents=True, exist_ok=True)


def copy_file(src: Path, dst: Path, dry_run: bool) -> None:
    if not src.exists():
        raise FileNotFoundError(src)
    ensure_dir(dst.parent, dry_run)
    log_action(dry_run, "copy", f"{src} -> {dst}")
    if not dry_run:
        shutil.copy2(src, dst)


def write_text(path: Path, text: str, dry_run: bool) -> None:
    ensure_dir(path.parent, dry_run)
    log_action(dry_run, "write", path)
    if not dry_run:
        path.write_text(text)


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage sanitized Kurultai rebuild configuration")
    parser.add_argument("--home", default=str(Path.home() / ".hermes-kurultai"), help="target Hermes home to create/stage around")
    parser.add_argument("--brain", default=str(Path.home() / "brain-kurultai"), help="target Brain wiki root to create")
    parser.add_argument("--staging", default=str(DEFAULT_STAGING), help="staging directory for sanitized rebuild files")
    parser.add_argument("--dry-run", action="store_true", help="print planned actions only")
    args = parser.parse_args()

    hermes_home = Path(args.home).expanduser()
    brain_root = Path(args.brain).expanduser()
    staging = Path(args.staging).expanduser()

    print("Kurultai rebuild staging")
    print(f"source={CONFIG}")
    print(f"hermes_home={hermes_home}")
    print(f"brain_root={brain_root}")
    print(f"staging={staging}")

    for directory in [
        hermes_home,
        hermes_home / "profiles",
        hermes_home / "skills",
        hermes_home / "cron",
        brain_root,
        staging,
    ]:
        ensure_dir(directory, args.dry_run)

    for rel in BRAIN_DIRECTORIES:
        ensure_dir(brain_root / rel, args.dry_run)

    for name in FILES:
        copy_file(CONFIG / name, staging / name, args.dry_run)

    copy_file(ROOT / "brain" / "AGENTS.md", brain_root / "AGENTS.md", args.dry_run)
    if not (brain_root / "home.md").exists() or args.dry_run:
        copy_file(ROOT / "brain" / "templates" / "page.md", brain_root / "home.md", args.dry_run)
    if not (brain_root / "index.md").exists() or args.dry_run:
        write_text(brain_root / "index.md", "# Brain Index\n", args.dry_run)

    marker = staging / "README.txt"
    write_text(
        marker,
        "Sanitized Kurultai rebuild staging area. Review these files before applying live private configuration.\n",
        args.dry_run,
    )

    print("Done. Add local secrets outside git, then run Hermes doctor/status commands for the target profile.")


if __name__ == "__main__":
    main()
