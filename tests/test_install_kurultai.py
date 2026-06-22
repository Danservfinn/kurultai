from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install_kurultai.py"


def run_installer(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(INSTALLER), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_doctor_json_reports_brain_identity_and_reconciliation() -> None:
    proc = run_installer("--doctor", "--json")

    assert proc.returncode == 0, proc.stderr + proc.stdout
    report = json.loads(proc.stdout)
    assert report["mode"] == "doctor"
    assert report["repo"]["installer"] == "scripts/install_kurultai.py"
    assert report["identity"]["chair_profile_id"] == "kublai"
    assert report["identity"]["chair_display_name"] == "Kublai"
    assert "receipts" in report["brain"]["required_directories"]
    assert "docs/plans" in report["brain"]["required_directories"]
    assert report["cron"]["job_count"] >= 1
    assert report["cron"]["missing_script_jobs"] >= 1
    assert report["cron"]["will_create_jobs_with_missing_scripts"] is False
    assert report["skills"]["entry_count"] >= 1
    assert report["skills"]["missing_path_entries"] >= 1
    assert report["skills"]["will_silently_skip_missing_skills"] is False


def test_dry_run_is_personalized_and_does_not_write(tmp_path: Path) -> None:
    hermes_home = tmp_path / "hermes"
    brain_root = tmp_path / "brain"
    staging = tmp_path / "staging"
    receipts = tmp_path / "receipts"

    proc = run_installer(
        "--dry-run",
        "--home",
        str(hermes_home),
        "--brain",
        str(brain_root),
        "--staging",
        str(staging),
        "--receipt-dir",
        str(receipts),
        "--chair-display-name",
        "Sophia's Main Guy",
        "--chair-bot-display-name",
        "Sophia's Kublai Bot",
        "--operator-name",
        "Sophia",
        "--system-name",
        "Sophia's Kurultai",
    )

    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "Sophia's Main Guy" in proc.stdout
    assert "Sophia's Kublai Bot" in proc.stdout
    assert "Brain root" in proc.stdout
    assert not hermes_home.exists()
    assert not brain_root.exists()
    assert not staging.exists()
    assert not receipts.exists()


def test_apply_creates_brain_staging_receipts_and_personalized_next_steps(tmp_path: Path) -> None:
    hermes_home = tmp_path / "hermes"
    brain_root = tmp_path / "brain"
    staging = tmp_path / "staging"
    receipts = tmp_path / "receipts"

    proc = run_installer(
        "--apply",
        "--home",
        str(hermes_home),
        "--brain",
        str(brain_root),
        "--staging",
        str(staging),
        "--receipt-dir",
        str(receipts),
        "--chair-display-name",
        "Sophia's Main Guy",
        "--chair-bot-display-name",
        "Sophia's Kublai Bot",
        "--operator-name",
        "Sophia",
        "--system-name",
        "Sophia's Kurultai",
    )

    assert proc.returncode == 0, proc.stderr + proc.stdout
    for rel in [
        "queue",
        "generated",
        "receipts",
        "docs/plans",
        "operations",
        "analyses",
        "content/artifacts",
        "raw/assets",
    ]:
        assert (brain_root / rel).is_dir(), rel
    assert (brain_root / "AGENTS.md").is_file()
    assert (brain_root / "home.md").is_file()
    assert (brain_root / "index.md").is_file()
    assert (staging / "identity.generated.yaml").is_file()
    assert (staging / "INSTALL-NEXT-STEPS.md").is_file()
    assert (staging / "cron.reconciliation.json").is_file()
    assert (staging / "skills.reconciliation.json").is_file()
    receipt_files = list(receipts.glob("install-*.md"))
    assert receipt_files, "expected local install receipt"

    identity = (staging / "identity.generated.yaml").read_text(encoding="utf-8")
    next_steps = (staging / "INSTALL-NEXT-STEPS.md").read_text(encoding="utf-8")
    assert "Sophia's Main Guy" in identity
    assert "Sophia's Kurultai" in identity
    assert "Sophia's Kublai Bot" in next_steps
    assert "BotFather" in next_steps
    assert "qmd update -c brain" in next_steps
    assert "missing cron scripts" in next_steps
    assert "missing skill paths" in next_steps


def test_write_plan_creates_single_install_plan_without_touching_brain(tmp_path: Path) -> None:
    brain_root = tmp_path / "brain"
    plan_dir = tmp_path / "plan"

    proc = run_installer(
        "--write-plan",
        "--brain",
        str(brain_root),
        "--receipt-dir",
        str(plan_dir),
        "--chair-display-name",
        "Any Name Sophia Wants",
    )

    assert proc.returncode == 0, proc.stderr + proc.stdout
    plans = list(plan_dir.glob("install-plan-*.md"))
    assert len(plans) == 1
    assert "Any Name Sophia Wants" in plans[0].read_text(encoding="utf-8")
    assert not brain_root.exists()
