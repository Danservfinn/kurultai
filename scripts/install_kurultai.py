#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "runtime-config"
DEFAULT_STAGING = Path.home() / ".kurultai-install" / "staging"
DEFAULT_RECEIPTS = Path.home() / ".kurultai-install" / "receipts"

CONFIG_FILES = [
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
    "queue",
    "generated",
    "receipts",
    "docs/plans",
    "operations",
    "analyses",
    "content",
    "content/artifacts",
    "entities",
    "projects",
    "infrastructure",
    "concepts",
    "raw/assets",
]

PROFILE_IDS = [
    "kublai",
    "batu",
    "chagatai",
    "jochi",
    "temujin",
    "coder",
    "mongke",
    "ogedei",
    "subc",
    "tolui",
    "codex",
]

PROFILE_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


@dataclass(frozen=True)
class Identity:
    chair_profile_id: str
    chair_display_name: str
    chair_bot_display_name: str
    ogedei_display_name: str
    ogedei_bot_display_name: str
    operator_name: str
    system_name: str

    @property
    def chair_secret_env(self) -> str:
        return f"KURULTAI_{env_slug(self.chair_profile_id)}_TELEGRAM_BOT_TOKEN"

    @property
    def ogedei_secret_env(self) -> str:
        return f"KURULTAI_{env_slug('ogedei')}_TELEGRAM_BOT_TOKEN"

    def as_dict(self) -> dict[str, str]:
        return {
            "chair_profile_id": self.chair_profile_id,
            "chair_display_name": self.chair_display_name,
            "chair_bot_display_name": self.chair_bot_display_name,
            "ogedei_display_name": self.ogedei_display_name,
            "ogedei_bot_display_name": self.ogedei_bot_display_name,
            "operator_name": self.operator_name,
            "system_name": self.system_name,
            "chair_secret_env": self.chair_secret_env,
            "ogedei_secret_env": self.ogedei_secret_env,
        }


def env_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").upper()
    return slug or "KUBLAI"


def yaml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def validate_label(label: str, value: str) -> str:
    clean = value.strip()
    if not clean:
        raise SystemExit(f"{label} cannot be empty")
    if any(ch in clean for ch in "\r\n\0"):
        raise SystemExit(f"{label} cannot contain newlines or NUL bytes")
    return clean


def validate_profile_id(value: str) -> str:
    clean = value.strip().lower()
    if not PROFILE_ID_RE.fullmatch(clean):
        raise SystemExit(
            "chair profile id must be a Hermes-safe slug: lowercase letter followed by lowercase letters, digits, '_' or '-'"
        )
    return clean


def build_identity(args: argparse.Namespace) -> Identity:
    chair_profile_id = validate_profile_id(args.chair_profile_id)
    chair_display_name = validate_label("chair display name", args.chair_display_name)
    default_bot_name = args.chair_bot_display_name or f"Kurultai {chair_display_name}"
    return Identity(
        chair_profile_id=chair_profile_id,
        chair_display_name=chair_display_name,
        chair_bot_display_name=validate_label("chair bot display name", default_bot_name),
        ogedei_display_name=validate_label("Ogedei display name", args.ogedei_display_name),
        ogedei_bot_display_name=validate_label("Ogedei bot display name", args.ogedei_bot_display_name),
        operator_name=validate_label("operator name", args.operator_name),
        system_name=validate_label("system name", args.system_name),
    )


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def command_summary(command: str) -> dict[str, Any]:
    path = shutil.which(command)
    result: dict[str, Any] = {"available": bool(path), "path": path}
    if path and command in {"hermes", "git", "python3"}:
        try:
            proc = subprocess.run(
                [path, "--version"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=5,
                check=False,
            )
            result["version"] = proc.stdout.strip().splitlines()[0] if proc.stdout.strip() else None
        except Exception as exc:  # pragma: no cover - environment dependent
            result["version_error"] = type(exc).__name__
    return result


def reconcile_cron() -> dict[str, Any]:
    manifest = read_json(CONFIG / "cron.manifest.json")
    jobs = manifest.get("jobs", [])
    script_refs = sorted({job.get("script") for job in jobs if job.get("script")})
    missing_script_refs = [script for script in script_refs if not (ROOT / "scripts" / script).exists()]
    missing_set = set(missing_script_refs)
    missing_script_jobs = [job for job in jobs if job.get("script") in missing_set]
    restorable_jobs = [job for job in jobs if not job.get("script") or job.get("script") not in missing_set]
    return {
        "schema": manifest.get("schema", "kurultai.cron-reconciliation.v1"),
        "job_count": len(jobs),
        "script_ref_count": len(script_refs),
        "missing_script_count": len(missing_script_refs),
        "missing_script_jobs": len(missing_script_jobs),
        "restorable_job_count": len(restorable_jobs),
        "will_create_jobs_with_missing_scripts": False,
        "policy": "Do not create cron jobs whose script is absent. Keep them as private-follow-up until the script is supplied locally.",
        "missing_script_refs": missing_script_refs,
        "restorable_job_ids": [job.get("job_id") for job in restorable_jobs],
        "private_follow_up_job_ids": [job.get("job_id") for job in missing_script_jobs],
    }


def reconcile_skills() -> dict[str, Any]:
    manifest = read_json(CONFIG / "skills.manifest.json")
    skills = manifest.get("skills", [])
    entries: list[dict[str, Any]] = []
    missing: list[dict[str, str | None]] = []
    present_count = 0
    for skill in skills:
        rel = skill.get("path") or ""
        candidates = [ROOT / rel, ROOT / "skills" / rel]
        present = any(path.exists() for path in candidates)
        if present:
            present_count += 1
        entry = {
            "name": skill.get("name"),
            "path": rel,
            "description": skill.get("description", ""),
            "path_present_in_repo": present,
            "action": "install_or_verify" if present else "private_or_external_follow_up",
        }
        entries.append(entry)
        if not present:
            missing.append({"name": skill.get("name"), "path": rel})
    return {
        "schema": "kurultai.skills-reconciliation.v1",
        "entry_count": len(skills),
        "present_path_entries": present_count,
        "missing_path_entries": len(missing),
        "will_silently_skip_missing_skills": False,
        "policy": "Install public-present skills, then list absent/private/external skills as follow-up instead of pretending they were restored.",
        "missing": missing,
        "entries": entries,
    }


def brain_contract() -> dict[str, Any]:
    return {
        "root_default_posix": "~/brain",
        "root_default_windows": "%USERPROFILE%\\brain",
        "required_directories": BRAIN_DIRECTORIES,
        "public_index_default_posix": "~/.brain-index/brain.db",
        "private_index_default_posix": "~/.kublai/brain-index-private/brain.db",
        "qmd_commands": ["qmd update -c brain", "qmd embed -c brain"],
        "receipt_required": True,
    }


def doctor_report(identity: Identity) -> dict[str, Any]:
    required_files = [str(Path("config/runtime-config") / name) for name in CONFIG_FILES]
    missing_required = [rel for rel in required_files if not (ROOT / rel).exists()]
    return {
        "schema": "kurultai.installer-doctor.v1",
        "mode": "doctor",
        "repo": {
            "root": str(ROOT),
            "installer": "scripts/install_kurultai.py",
            "required_files_present": not missing_required,
            "missing_required_files": missing_required,
        },
        "platform": {
            "system": platform.system(),
            "machine": platform.machine(),
            "python": sys.version.split()[0],
        },
        "commands": {name: command_summary(name) for name in ["git", "python3", "hermes", "qmd", "node", "npm"]},
        "identity": identity.as_dict(),
        "brain": brain_contract(),
        "cron": reconcile_cron(),
        "skills": reconcile_skills(),
        "human_gates": [
            "BotFather bot tokens",
            "OAuth/browser login",
            "payment, DNS, public webhook, or production security-policy changes",
            "destructive overwrite of existing private Hermes or Brain data",
        ],
    }


def ensure_dir(path: Path, dry_run: bool, actions: list[str]) -> None:
    actions.append(f"ensure-dir {path}")
    if not dry_run:
        path.mkdir(parents=True, exist_ok=True)


def copy_file(src: Path, dst: Path, dry_run: bool, actions: list[str]) -> None:
    if not src.exists():
        raise FileNotFoundError(src)
    ensure_dir(dst.parent, dry_run, actions)
    actions.append(f"copy {src.relative_to(ROOT) if src.is_relative_to(ROOT) else src} -> {dst}")
    if not dry_run:
        shutil.copy2(src, dst)


def write_text(path: Path, text: str, dry_run: bool, actions: list[str]) -> None:
    ensure_dir(path.parent, dry_run, actions)
    actions.append(f"write {path}")
    if not dry_run:
        path.write_text(text, encoding="utf-8")


def identity_yaml(identity: Identity) -> str:
    return "\n".join(
        [
            "# Generated by scripts/install_kurultai.py. Safe to keep locally; contains no secrets.",
            "identity:",
            f"  system_name: {yaml_quote(identity.system_name)}",
            f"  operator_name: {yaml_quote(identity.operator_name)}",
            "  chair:",
            f"    profile_id: {yaml_quote(identity.chair_profile_id)}",
            f"    display_name: {yaml_quote(identity.chair_display_name)}",
            f"    bot_display_name: {yaml_quote(identity.chair_bot_display_name)}",
            f"    telegram_token_env: {yaml_quote(identity.chair_secret_env)}",
            "  operations_gateway:",
            "    profile_id: \"ogedei\"",
            f"    display_name: {yaml_quote(identity.ogedei_display_name)}",
            f"    bot_display_name: {yaml_quote(identity.ogedei_bot_display_name)}",
            f"    telegram_token_env: {yaml_quote(identity.ogedei_secret_env)}",
            "  naming_policy:",
            "    internal_profile_ids_may_remain_stable: true",
            "    user_visible_names_are_customizable: true",
            "",
        ]
    )


def next_steps_markdown(identity: Identity, paths: dict[str, Path], cron: dict[str, Any], skills: dict[str, Any]) -> str:
    missing_cron = cron["missing_script_count"]
    missing_skills = skills["missing_path_entries"]
    return textwrap.dedent(
        f"""
        # Kurultai install next steps for {identity.operator_name}

        This file was generated by `scripts/install_kurultai.py`. It contains no secrets.

        ## Selected names

        | Surface | Value |
        |---|---|
        | System name | {identity.system_name} |
        | Operator name | {identity.operator_name} |
        | Main chair profile id | `{identity.chair_profile_id}` |
        | Main chair display name | {identity.chair_display_name} |
        | Main chair Telegram bot display name | {identity.chair_bot_display_name} |
        | Operations gateway display name | {identity.ogedei_display_name} |
        | Operations Telegram bot display name | {identity.ogedei_bot_display_name} |

        The profile id may stay `{identity.chair_profile_id}` while every user-visible attribution says `{identity.chair_display_name}`. If the operator wants the actual Hermes profile id renamed too, use `hermes profile rename kublai <new-slug>` only after updating the generated local config and gateway commands.

        ## Brain installation/configuration

        Brain root: `{paths['brain_root']}`

        The installer creates the Brain root plus `queue`, `generated`, `receipts`, `docs/plans`, `operations`, `analyses`, `content/artifacts`, `entities`, `projects`, `infrastructure`, `concepts`, and `raw/assets`.

        If QMD is available, run from the host where Brain is installed:

        ```bash
        qmd update -c brain
        qmd embed -c brain
        ```

        If QMD is not available, Brain still works as a local Markdown/receipt tree; record QMD as pending and install it before relying on vector/indexed recall.

        ## Hermes setup

        ```bash
        hermes --version
        hermes doctor
        hermes login --provider openai-codex
        hermes config set model.provider openai-codex
        hermes config set model.default gpt-5.5
        hermes config set model.context_length 1000000
        hermes config set compression.enabled true
        hermes config set compression.threshold 0.25
        hermes config check
        ```

        Create/verify profiles with the installed Hermes command spelling:

        ```bash
        hermes profile list
        hermes profile create {identity.chair_profile_id}
        hermes profile describe {identity.chair_profile_id} "{identity.chair_display_name}: main chair/caretaker/orchestrator for {identity.system_name}"
        ```

        Then create the remaining Kurultai profiles from `staging/profiles.yaml`.

        ## Telegram / BotFather

        Create separate BotFather bots when Telegram is desired:

        1. Main chair bot display name: **{identity.chair_bot_display_name}**.
        2. Operations bot display name: **{identity.ogedei_bot_display_name}**.
        3. Store tokens only in Hermes local secret storage or `.env`, never in git.
        4. Suggested env vars:
           - `{identity.chair_secret_env}` for `{identity.chair_display_name}`.
           - `{identity.ogedei_secret_env}` for `{identity.ogedei_display_name}`.
        5. Smoke-test foreground before installing services:

        ```bash
        hermes --profile {identity.chair_profile_id} gateway run
        hermes --profile ogedei gateway run
        ```

        ## Cron and skills reconciliation

        The public repo intentionally does not include private runtime artifacts. The installer will not pretend those are installed.

        - `{missing_cron}` missing cron scripts are recorded in `cron.reconciliation.json` as private-follow-up. Jobs with missing scripts must **not** be created until local copies exist.
        - `{missing_skills}` missing skill paths are recorded in `skills.reconciliation.json` as private/external follow-up. Missing skills must be listed, not silently skipped.

        ## Human-only gates

        Stop only for BotFather tokens, OAuth/browser login, payment/DNS/public webhook/security-policy changes, or destructive overwrite of existing private Hermes/Brain data.
        """
    ).strip() + "\n"


def receipt_markdown(identity: Identity, paths: dict[str, Path], actions: list[str], cron: dict[str, Any], skills: dict[str, Any]) -> str:
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    action_lines = "\n".join(f"- `{action}`" for action in actions)
    return textwrap.dedent(
        f"""
        # Kurultai install receipt

        Timestamp: {timestamp}

        ## Identity

        - System: {identity.system_name}
        - Operator: {identity.operator_name}
        - Main chair profile id: `{identity.chair_profile_id}`
        - Main chair display name: {identity.chair_display_name}
        - Main chair bot display name: {identity.chair_bot_display_name}

        ## Paths

        - Hermes home: `{paths['hermes_home']}`
        - Brain root: `{paths['brain_root']}`
        - Staging: `{paths['staging']}`
        - Receipt dir: `{paths['receipt_dir']}`

        ## Brain

        Brain directory scaffold and receipt path were created. QMD commands remain `qmd update -c brain` and `qmd embed -c brain` when QMD is installed.

        ## Reconciliation

        - Cron jobs: {cron['job_count']} total; {cron['missing_script_jobs']} jobs blocked on missing cron scripts; missing-script jobs were not created.
        - Skills: {skills['entry_count']} total; {skills['missing_path_entries']} missing repo paths; missing skills were not silently marked installed.

        ## Actions

        {action_lines}
        """
    ).strip() + "\n"


def install_plan_markdown(identity: Identity, paths: dict[str, Path], report: dict[str, Any]) -> str:
    return textwrap.dedent(
        f"""
        # Kurultai install plan

        ## Names selected

        - System: {identity.system_name}
        - Operator: {identity.operator_name}
        - Main chair profile id: `{identity.chair_profile_id}`
        - Main chair display name: {identity.chair_display_name}
        - Main chair bot display name: {identity.chair_bot_display_name}

        ## Target paths

        - Hermes home: `{paths['hermes_home']}`
        - Brain root: `{paths['brain_root']}`
        - Staging: `{paths['staging']}`
        - Receipt dir: `{paths['receipt_dir']}`

        ## Plan

        1. Run `python3 scripts/install_kurultai.py --doctor` and resolve blockers.
        2. Run `python3 scripts/install_kurultai.py --apply --chair-display-name {identity.chair_display_name!r}`.
        3. Configure Hermes provider/model and create profiles.
        4. Configure Brain/QMD and verify receipt writes.
        5. Restore only cron jobs whose scripts exist; keep {report['cron']['missing_script_jobs']} missing-script jobs as follow-up.
        6. Install/reconcile skills; keep {report['skills']['missing_path_entries']} missing paths as follow-up.
        7. Configure BotFather/gateways using the generated display names.
        8. Run final canaries and leave a local receipt outside git.
        """
    ).strip() + "\n"


def build_paths(args: argparse.Namespace) -> dict[str, Path]:
    return {
        "hermes_home": Path(args.home).expanduser(),
        "brain_root": Path(args.brain).expanduser(),
        "staging": Path(args.staging).expanduser(),
        "receipt_dir": Path(args.receipt_dir).expanduser(),
        "public_index_dir": Path(args.public_index_dir).expanduser(),
        "private_index_dir": Path(args.private_index_dir).expanduser(),
    }


def apply_scaffold(identity: Identity, paths: dict[str, Path], dry_run: bool) -> dict[str, Any]:
    actions: list[str] = []
    cron = reconcile_cron()
    skills = reconcile_skills()

    for directory in [
        paths["hermes_home"],
        paths["hermes_home"] / "profiles",
        paths["hermes_home"] / "skills",
        paths["hermes_home"] / "cron",
        paths["hermes_home"] / "receipts",
        paths["brain_root"],
        paths["staging"],
        paths["receipt_dir"],
        paths["public_index_dir"],
        paths["private_index_dir"],
    ]:
        ensure_dir(directory, dry_run, actions)

    for rel in BRAIN_DIRECTORIES:
        ensure_dir(paths["brain_root"] / rel, dry_run, actions)

    for name in CONFIG_FILES:
        copy_file(CONFIG / name, paths["staging"] / name, dry_run, actions)

    copy_file(ROOT / "brain" / "AGENTS.md", paths["brain_root"] / "AGENTS.md", dry_run, actions)
    if not (paths["brain_root"] / "home.md").exists() or dry_run:
        copy_file(ROOT / "brain" / "templates" / "page.md", paths["brain_root"] / "home.md", dry_run, actions)
    if not (paths["brain_root"] / "index.md").exists() or dry_run:
        write_text(paths["brain_root"] / "index.md", "# Brain Index\n", dry_run, actions)

    write_text(paths["staging"] / "identity.generated.yaml", identity_yaml(identity), dry_run, actions)
    write_text(
        paths["staging"] / "cron.reconciliation.json",
        json.dumps(cron, indent=2, sort_keys=True) + "\n",
        dry_run,
        actions,
    )
    write_text(
        paths["staging"] / "skills.reconciliation.json",
        json.dumps(skills, indent=2, sort_keys=True) + "\n",
        dry_run,
        actions,
    )
    write_text(paths["staging"] / "INSTALL-NEXT-STEPS.md", next_steps_markdown(identity, paths, cron, skills), dry_run, actions)

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    receipt = receipt_markdown(identity, paths, actions, cron, skills)
    write_text(paths["receipt_dir"] / f"install-{stamp}.md", receipt, dry_run, actions)
    write_text(paths["brain_root"] / "receipts" / f"install-{stamp}.md", receipt, dry_run, actions)

    return {
        "identity": identity.as_dict(),
        "paths": {key: str(value) for key, value in paths.items()},
        "cron": cron,
        "skills": skills,
        "actions": actions,
        "dry_run": dry_run,
    }


def prompt_default(prompt: str, default: str) -> str:
    value = input(f"{prompt} [{default}]: ").strip()
    return value or default


def apply_interactive_defaults(args: argparse.Namespace) -> None:
    if not sys.stdin.isatty():
        raise SystemExit("--interactive requires a TTY; use --apply with explicit --chair-display-name/paths for non-interactive installs")
    args.operator_name = prompt_default("Operator name", args.operator_name)
    args.system_name = prompt_default("System name", args.system_name)
    args.chair_display_name = prompt_default("Main chair display name", args.chair_display_name)
    args.chair_bot_display_name = prompt_default("Main chair Telegram bot display name", args.chair_bot_display_name or f"Kurultai {args.chair_display_name}")
    args.ogedei_display_name = prompt_default("Operations gateway display name", args.ogedei_display_name)
    args.ogedei_bot_display_name = prompt_default("Operations Telegram bot display name", args.ogedei_bot_display_name)


def print_human_summary(result: dict[str, Any], mode: str) -> None:
    identity = result["identity"]
    paths = result["paths"]
    print(f"Kurultai installer {mode}")
    print(f"System: {identity['system_name']}")
    print(f"Operator: {identity['operator_name']}")
    print(f"Main chair: {identity['chair_display_name']} (profile {identity['chair_profile_id']})")
    print(f"Main chair bot: {identity['chair_bot_display_name']}")
    print(f"Brain root: {paths['brain_root']}")
    print(f"Staging: {paths['staging']}")
    print(f"Cron: {result['cron']['job_count']} jobs, {result['cron']['missing_script_jobs']} blocked by missing cron scripts")
    print(f"Skills: {result['skills']['entry_count']} entries, {result['skills']['missing_path_entries']} missing skill paths")
    print("Jobs with missing scripts and skills with missing paths are recorded as follow-up, not silently installed.")
    if result.get("dry_run"):
        print("Dry run only; no files were written.")
    else:
        print("Scaffold written. Review INSTALL-NEXT-STEPS.md and local receipts before adding secrets.")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Guided, secret-safe Kurultai installer and Brain bootstrapper")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--doctor", action="store_true", help="read-only environment/repo/manifest check")
    mode.add_argument("--dry-run", action="store_true", help="print the personalized scaffold plan without writing files")
    mode.add_argument("--apply", action="store_true", help="write non-secret Hermes/Brain/staging scaffold and receipts")
    mode.add_argument("--interactive", action="store_true", help="prompt for names and then apply the non-secret scaffold")
    mode.add_argument("--write-plan", action="store_true", help="write a local install plan only; do not touch Brain/Hermes dirs")
    mode.add_argument("--resume", action="store_true", help="show the latest local plan/receipt and rerun doctor")
    parser.add_argument("--json", action="store_true", help="emit JSON for --doctor or --resume")
    parser.add_argument("--home", default=str(Path.home() / ".hermes"), help="target Hermes home")
    parser.add_argument("--brain", default=str(Path.home() / "brain"), help="target Brain root")
    parser.add_argument("--staging", default=str(DEFAULT_STAGING), help="local staging directory for sanitized/generated config")
    parser.add_argument("--receipt-dir", default=str(DEFAULT_RECEIPTS), help="local receipt/plan directory outside git")
    parser.add_argument("--public-index-dir", default=str(Path.home() / ".brain-index"), help="Brain public index directory")
    parser.add_argument("--private-index-dir", default=str(Path.home() / ".kublai" / "brain-index-private"), help="Brain private index directory")
    parser.add_argument("--chair-profile-id", default="kublai", help="Hermes-safe internal profile id for the main chair")
    parser.add_argument("--chair-display-name", default="Kublai", help="user-visible name for the main chair/main guy")
    parser.add_argument("--chair-bot-display-name", default=None, help="BotFather display name for the main chair Telegram bot")
    parser.add_argument("--ogedei-display-name", default="Ogedei", help="user-visible name for the operations gateway")
    parser.add_argument("--ogedei-bot-display-name", default="Kurultai Ogedei", help="BotFather display name for the operations Telegram bot")
    parser.add_argument("--operator-name", default="Operator", help="human operator name")
    parser.add_argument("--system-name", default="Kurultai", help="user-visible system name")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.interactive:
        apply_interactive_defaults(args)
    identity = build_identity(args)
    paths = build_paths(args)

    if args.doctor:
        report = doctor_report(identity)
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            print_human_summary(
                {
                    "identity": identity.as_dict(),
                    "paths": {key: str(value) for key, value in paths.items()},
                    "cron": report["cron"],
                    "skills": report["skills"],
                    "dry_run": True,
                },
                "doctor",
            )
            missing = report["repo"]["missing_required_files"]
            if missing:
                print("Missing required files:", ", ".join(missing))
        return 0

    if args.resume:
        report = doctor_report(identity)
        receipts = sorted(paths["receipt_dir"].glob("install-*.md")) if paths["receipt_dir"].exists() else []
        plans = sorted(paths["receipt_dir"].glob("install-plan-*.md")) if paths["receipt_dir"].exists() else []
        payload = {"mode": "resume", "latest_receipt": str(receipts[-1]) if receipts else None, "latest_plan": str(plans[-1]) if plans else None, "doctor": report}
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"Latest receipt: {payload['latest_receipt'] or 'none'}")
            print(f"Latest plan: {payload['latest_plan'] or 'none'}")
            print_human_summary(
                {
                    "identity": identity.as_dict(),
                    "paths": {key: str(value) for key, value in paths.items()},
                    "cron": report["cron"],
                    "skills": report["skills"],
                    "dry_run": True,
                },
                "resume/doctor",
            )
        return 0

    if args.write_plan:
        actions: list[str] = []
        ensure_dir(paths["receipt_dir"], False, actions)
        report = doctor_report(identity)
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        plan_path = paths["receipt_dir"] / f"install-plan-{stamp}.md"
        plan_path.write_text(install_plan_markdown(identity, paths, report), encoding="utf-8")
        print(f"Wrote install plan: {plan_path}")
        return 0

    dry_run = args.dry_run or not args.apply and not args.interactive
    result = apply_scaffold(identity, paths, dry_run=dry_run)
    print_human_summary(result, "dry-run" if dry_run else "apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
